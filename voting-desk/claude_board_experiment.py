"""Compare Claude with the frozen local classifier on the same exposed 2024 rows.

`prepare` is offline. `run` makes paid requests, once per meeting, with immutable
request caches. Only earlier historical votes are retrieved; no holdout is scored.
"""
import boot  # noqa: F401
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import time

import anthropic
import numpy as np
import pandas as pd

import board_experiment
import claude_board_context as context
import desk
from rag_eval import atomic_json, immutable_json, fingerprint
from vector_experiment import digest, embedding_matrix, ROOT
from vote_targets import target_labels

OUTPUT = ROOT / "data/local-rag/claude-board-v1"
LOCAL = board_experiment.OUTPUT
SOURCES = ("claude_board_context.py", "claude_board_experiment.py", "board_experiment.py",
           "vector_experiment.py", "vector_model.py", "vote_targets.py", "local_rag.py", "rag_eval.py")
PRICE = {"model": "claude-sonnet-5-5", "input_per_million": 2.0,
         "output_per_million": 10.0, "cache_read_per_million": .10,
         "cache_write_per_million": 2.5,
         "source": "https://www.anthropic.com/claude-sonnet-5-5", "checked": "2026-11-05"}


def now():
    return datetime.now(timezone.utc).isoformat()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def checked_path(base, relative, expected):
    path = (Path(base) / relative).resolve()
    if not path.is_relative_to(Path(base).resolve()) or digest(path) != expected:
        raise ValueError("Experiment artifact changed or unsafe path")
    return path


def prepare(output=OUTPUT, local=LOCAL):
    output, local = Path(output), Path(local)
    if output.exists():
        raise ValueError("Output already exists; run/report it or choose a new experiment directory")
    fit, calibration, provenance = board_experiment.load_temporal()
    baseline = read_json(local / "summary.json")
    if baseline.get("target") != "against_board":
        raise ValueError("Local baseline must predict disagreement")
    for name, expected in baseline["artifacts"].items():
        checked_path(local, name, expected)
    saved = pd.read_csv(local / "calibration.csv", dtype=str, keep_default_na=False)
    identity = ["meeting_id", "item_no", "company_id", "meeting_date", "nbim_vote", "mgmt_rec"]
    if saved[identity].to_dict("records") != calibration[identity].to_dict("records"):
        raise ValueError("Local baseline and new Claude cohort do not match")
    reference = pd.concat([fit, calibration], ignore_index=True)
    vectors, embedding = embedding_matrix(reference)
    bundles = context.build_bundles(fit, calibration, vectors)
    expected_ids = list(calibration.meeting_id.drop_duplicates())
    if [bundle["meeting"]["meeting_id"] for bundle in bundles] != expected_ids:
        raise ValueError("Prepared meetings differ from calibration cohort")
    output.mkdir(parents=True)
    (output / "bundles").mkdir()
    (output / "source").mkdir()
    for name in SOURCES:
        shutil.copy2(ROOT / name, output / "source" / name)
    gold = calibration.copy()
    gold["local_score"] = saved["score"]
    gold.to_csv(output / "evaluation-labels.csv", index=False)
    bundle_hashes = {}
    for bundle in bundles:
        mid = bundle["meeting"]["meeting_id"]
        path = output / "bundles" / f"{mid}.json"
        immutable_json(path, bundle)
        bundle_hashes[mid] = digest(path)
    settings = {"model": desk.MODEL, "effort": desk.EFFORT, "system": context.SYSTEM,
                "schema": context.Drafts.model_json_schema(), "history_global_k": 8,
                "history_company_k": 8, "decision": "derive disagreement from predicted vote; no Claude score threshold",
                "source_hashes": {name: digest(ROOT / name) for name in SOURCES}}
    plan = {"created_at": now(), "target": "against_board", "evaluation_kind": "EXPOSED_2024_DEVELOPMENT",
            "scope": "historical_votes_only", "settings": settings,
            "history_policy": "strict_before_meeting_minus_5_days", "test_evaluated": False,
            "cohort": {"rows": len(calibration), "meetings": len(bundles),
                       "positive": int(target_labels(calibration, "against_board").sum())},
            "meeting_ids": expected_ids, "bundle_sha256": bundle_hashes,
            "evaluation_labels_sha256": digest(output / "evaluation-labels.csv"),
            "local_summary_sha256": digest(local / "summary.json"),
            "local_thresholds": {"at_calibration_threshold": baseline["selected_threshold"],
                                 "at_validation_threshold": baseline["validation_threshold"]},
            "source_provenance": provenance, "embedding": embedding, "pricing": PRICE,
            "comparison_limits": ["The same rows and as-of history pool are used, but learning and input representations differ.",
                                  "The local calibrated threshold was chosen using 2024 outcomes; Claude's prompt is fixed before this run.",
                                  "No rules or filing passages are supplied. Predictions are historical analogies, not policy-backed recommendations.",
                                  "The pretrained Claude and BGE knowledge is not restricted to pre-2024.",
                                  "Earlier same-year true outcomes enter history only after the strict five-day lag; model outputs are not fed back.",
                                  "2024 has been exposed in earlier development; this is not an independent test."]}
    plan["plan_id"] = fingerprint(plan)
    immutable_json(output / "plan.json", plan)
    return report(output)


def load_plan(output, check_current=False):
    output = Path(output)
    plan = read_json(output / "plan.json")
    if plan.get("target") != "against_board" or plan.get("test_evaluated") is not False:
        raise ValueError("Unexpected experiment target or period")
    if fingerprint({k: v for k, v in plan.items() if k != "plan_id"}) != plan["plan_id"]:
        raise ValueError("Plan identity changed")
    checked_path(output, "evaluation-labels.csv", plan["evaluation_labels_sha256"])
    for mid, expected in plan["bundle_sha256"].items():
        checked_path(output, f"bundles/{mid}.json", expected)
    for name, expected in plan["settings"]["source_hashes"].items():
        checked_path(output, f"source/{name}", expected)
        if check_current and digest(ROOT / name) != expected:
            raise ValueError("Generation code changed; start a separate experiment")
    return plan


def usage_cost(usage, model):
    if model != PRICE["model"]:
        return None
    return sum((usage.get(field) or 0) * rate for field, rate in (
        ("input_tokens", PRICE["input_per_million"]), ("output_tokens", PRICE["output_per_million"]),
        ("cache_read_input_tokens", PRICE["cache_read_per_million"]),
        ("cache_creation_input_tokens", PRICE["cache_write_per_million"]))) / 1_000_000


def score_rows(rows, predictions, target="against_board"):
    labels = target_labels(rows, target)
    scores = []
    for row in rows.to_dict("records"):
        vote = predictions.get((row["meeting_id"], row["item_no"]), {}).get("vote")
        scores.append(None if vote not in ("FOR", "MOT", "AVSTÅ") else
                      float(vote != row["mgmt_rec"] if target == "against_board" else vote == "MOT"))
    return board_experiment.measure(labels, scores, .5)


def report(output=OUTPUT):
    output = Path(output)
    plan = load_plan(output)
    labels = pd.read_csv(output / "evaluation-labels.csv", dtype=str, keep_default_na=False)
    attempted, completed, failures, pending, predictions, usage = set(), set(), [], [], {}, {}
    exports = []
    elapsed = 0
    for mid in plan["meeting_ids"]:
        path = output / "responses" / f"{mid}.json"
        if not path.exists():
            if (output / "requests" / f"{mid}.json").exists():
                attempted.add(mid)
                pending.append(mid)
            continue
        record = read_json(path)
        if fingerprint({key: value for key, value in record.items() if key != "record_id"}) != record.get("record_id"):
            raise ValueError("Cached response content changed")
        if record["plan_id"] != plan["plan_id"] or record["bundle_sha256"] != plan["bundle_sha256"][mid] or record["meeting_id"] != mid:
            raise ValueError("Response belongs to another request")
        attempted.add(mid)
        elapsed += record["elapsed_seconds"]
        if record["status"] == "completed":
            completed.add(mid)
            for item in record["result"]["items"]:
                predictions[mid, str(item["item"])] = item
        else:
            failures.append({"meeting_id": mid, **record["error"]})
        for field, value in record.get("usage", {}).items():
            if isinstance(value, int) and not isinstance(value, bool):
                usage[field] = usage.get(field, 0) + value
    selected = labels.loc[labels.meeting_id.isin(attempted)].reset_index(drop=True)
    truth = target_labels(selected, "against_board")
    local_scores = pd.to_numeric(selected.local_score).to_numpy()
    for row in selected.to_dict("records"):
        prediction = predictions.get((row["meeting_id"], row["item_no"]), {})
        exports.append({**row, "claude_vote": prediction.get("vote"),
                        "claude_disagreement": prediction.get("against_board"),
                        "claude_why": prediction.get("why"), "history_ids": prediction.get("history_ids", [])})
    result = {"plan_id": plan["plan_id"], "target": plan["target"], "model": plan["settings"]["model"],
              "evaluation_kind": plan["evaluation_kind"], "scope": plan["scope"],
              "cohort": plan["cohort"], "attempted_meetings": len(attempted), "completed_meetings": len(completed),
              "failed_meetings": len(failures), "pending_or_interrupted_meetings": len(pending),
              "unattempted_meetings": len(plan["meeting_ids"]) - len(attempted), "attempted_rows": len(selected),
              "complete": len(completed) + len(failures) == len(plan["meeting_ids"]),
              "claude": {"disagreement": score_rows(selected, predictions), "literal_mot": score_rows(selected, predictions, "mot")},
              "same_rows_local": {name: board_experiment.measure(truth, local_scores, threshold)
                                  for name, threshold in plan["local_thresholds"].items()},
              "usage": usage, "api_calls": len(attempted), "estimated_usd": usage_cost(usage, plan["settings"]["model"]),
              "usage_note": "Recorded usage includes validated and rejected responses when returned. Transport failures may incur unreported charges; price estimate is not an invoice.",
              "failures": failures, "pending_meeting_ids": pending, "elapsed_call_seconds": elapsed,
              "history_policy": plan["history_policy"], "test_evaluated": False,
              "comparison_limits": plan["comparison_limits"], "updated_at": now()}
    atomic_json(output / "predictions.json", exports)
    atomic_json(output / "report.json", result)
    return result


def run(output=OUTPUT, limit=None, workers=4):
    output = Path(output)
    plan = load_plan(output, check_current=True)
    if not os.getenv("ANTHROPIC_API_KEY", "").strip():
        raise ValueError("ANTHROPIC_API_KEY is missing")
    if not 1 <= workers <= 4 or (limit is not None and not 1 <= limit <= len(plan["meeting_ids"])):
        raise ValueError("Invalid workers or meeting limit")
    lock = output / "running.lock"
    with lock.open("x") as handle:
        handle.write(now())
    try:
        selected = plan["meeting_ids"][:limit]
        todo = [mid for mid in selected if not (output / "responses" / f"{mid}.json").exists()]
        if any((output / "requests" / f"{mid}.json").exists() for mid in todo):
            raise ValueError("A request was interrupted; inspect it rather than silently paying twice")

        def call(mid):
            bundle = read_json(output / "bundles" / f"{mid}.json")
            record = {"meeting_id": mid, "plan_id": plan["plan_id"], "bundle_sha256": plan["bundle_sha256"][mid], "started_at": now()}
            immutable_json(output / "requests" / f"{mid}.json", record)
            started = time.monotonic()
            try:
                with anthropic.Anthropic(max_retries=0, timeout=180.0) as client:
                    result = context.generate_review(bundle, client=client, model=plan["settings"]["model"], effort=plan["settings"]["effort"])
                record.update(status="completed", result=result, usage=result.get("usage", {}))
            except Exception as error:
                record.update(status="failed", error={"type": type(error).__name__, "status_code": getattr(error, "status_code", None)},
                              usage=getattr(error, "usage", {}))
            record["elapsed_seconds"] = round(time.monotonic() - started, 3)
            record["record_id"] = fingerprint(record)
            immutable_json(output / "responses" / f"{mid}.json", record)
            return record

        with ThreadPoolExecutor(max_workers=workers) as pool:
            for start in range(0, len(todo), workers):
                batch = [pool.submit(call, mid) for mid in todo[start:start + workers]]
                stop = False
                for future in as_completed(batch):
                    record = future.result()
                    print(f"{record['meeting_id']}: {record['status']} ({record['elapsed_seconds']}s)", flush=True)
                    stop |= record.get("error", {}).get("status_code") in (401, 403, 429)
                status = report(output)
                print(json.dumps({key: status[key] for key in ("completed_meetings", "failed_meetings", "unattempted_meetings", "estimated_usd")}), flush=True)
                if stop:
                    break
    finally:
        lock.unlink(missing_ok=True)
    return report(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "run", "report"))
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    result = run(args.output, args.limit, args.workers) if args.command == "run" else globals()[args.command](args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
