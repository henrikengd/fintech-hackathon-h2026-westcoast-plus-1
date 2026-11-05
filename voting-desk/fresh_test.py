"""A frozen, label-blind comparison on genuinely new meetings.

Prepare reads ballots and old history only. Fresh reference outcomes are opened
only by score(), after both prediction streams have been sealed.
"""
import boot  # noqa: F401
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time

import anthropic
import joblib
import numpy as np
import pandas as pd

import fresh_inference
import local_rag
from board_experiment import measure
from claude_board_experiment import checked_path, usage_cost
from rag_eval import immutable_json, fingerprint
from vector_experiment import ROOT, digest, embedding_matrix
from vector_model import META_FIELDS, KEY, VOTES, _metadata
from vote_targets import known_target, target_labels

OUTPUT = ROOT / "data/local-rag/fresh-test-2026-10-v1"
SOURCE_FILES = ("fresh_test.py", "fresh_inference.py", "claude_board_context.py", "vote_features.py",
                "vote_learner.py", "vector_model.py", "vector_experiment.py", "vote_targets.py",
                "board_experiment.py", "claude_board_experiment.py", "rag_eval.py", "local_rag.py",
                "boot.py", "desk.py", "mot_experiment.py", "vote_experiment.py", "rag_review.py")
PREFLIGHT_ARTIFACTS = {"selection-policy.json", "locked-settings.json", "history.csv", "models/learner.joblib"}


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def now():
    return datetime.now(timezone.utc).isoformat()


def signed(value):
    return {**value, "record_id": fingerprint(value)}


def checked_json(path):
    value = read_json(path)
    if fingerprint({k: v for k, v in value.items() if k != "record_id"}) != value.get("record_id"):
        raise ValueError("Immutable record changed")
    return value


def read_frame(path, fields):
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, strict=True)
        if set(reader.fieldnames or []) != set(fields) or len(reader.fieldnames or []) != len(fields):
            raise ValueError("Unexpected CSV fields; ballots must not contain fresh outcomes")
        rows = list(reader)
    if any(None in row or any(v is None for v in row.values()) for row in rows):
        raise ValueError("Malformed CSV row")
    return pd.DataFrame(rows, columns=fields)


def validate_ballots(query, history, policy):
    query = _metadata(query)
    if query.empty or not query.mgmt_rec.isin([*VOTES, ""]).all():
        raise ValueError("Empty cohort or unrecognized board recommendation")
    if not query.meeting_date.between(policy["date_start"], policy["date_end"]).all():
        raise ValueError("New cohort is outside the frozen date window")
    if not set(query.company_id) <= set(policy["company_ids"]):
        raise ValueError("New cohort contains a company outside the frozen sampling frame")
    old_ids = set(history.meeting_id) | set(policy["excluded_meeting_ids"])
    old_groups = set(zip(history.company_id, history.meeting_date)) | {
        tuple(group) for group in policy["excluded_company_dates"]}
    if set(query.meeting_id) & old_ids or set(zip(query.company_id, query.meeting_date)) & old_groups:
        raise ValueError("Previously exposed meeting or company/date group in fresh cohort")
    if query.groupby("meeting_id")[["company_id", "company", "meeting_date"]].nunique().gt(1).any().any():
        raise ValueError("A meeting spans inconsistent metadata")
    return query.sort_values(["meeting_date", *KEY], kind="stable").reset_index(drop=True)


def load_frozen(output=OUTPUT, check_code=True):
    output = Path(output)
    plan = checked_json(output / "freeze.json")
    for relative, expected in plan["artifacts"].items():
        checked_path(output, relative, expected)
    if check_code:
        for name, expected in plan["code"].items():
            if digest(ROOT / name) != expected:
                raise ValueError("Prediction code changed after freezing")
    if local_rag.model_fingerprint() != plan["settings"]["embedding_assets"]:
        raise ValueError("Embedding weights changed after freezing")
    return plan


def capture_commitment(ballots_csv, output, policy):
    """Commit the captured source bytes without parsing fresh reference outcomes."""
    if not policy.get("source_access"):
        return None, []
    capture = read_json(output / "source-capture.json")
    expected = capture.get("references_sha256", "")
    if len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected):
        raise ValueError("Source capture has no valid fresh reference commitment")
    if digest(ballots_csv) != capture.get("ballots_sha256"):
        raise ValueError("Ballots differ from the committed source capture")
    for name, checksum in capture.get("raw_artifacts", {}).items():
        checked_path(output, name, checksum)
    return expected, ["source-capture.json", *capture.get("raw_artifacts", {})]


def prepare(ballots_csv, output=OUTPUT):
    output = Path(output)
    if (output / "freeze.json").exists():
        raise ValueError("A frozen cohort already exists; do not replace it")
    policy = read_json(output / "selection-policy.json")
    settings = read_json(output / "locked-settings.json")
    preflight = read_json(output / "preflight-freeze.json")
    if not set(SOURCE_FILES) <= set(preflight["code"]):
        raise ValueError("Preflight does not freeze all prediction code before fresh source access")
    if not PREFLIGHT_ARTIFACTS <= set(preflight["artifacts"]):
        raise ValueError("Preflight must freeze the selection policy, locked settings, history, and model")
    for name, expected in preflight["code"].items():
        if digest(ROOT / name) != expected:
            raise ValueError("Code changed after the preflight freeze")
    for name, expected in preflight["artifacts"].items():
        checked_path(output, name, expected)
    reference_commitment, capture_artifacts = capture_commitment(ballots_csv, output, policy)
    if digest(output / "models/learner.joblib") != settings["learner_sha256"] or digest(output / "history.csv") != settings["history_sha256"]:
        raise ValueError("Model or history differs from the previously locked snapshot")
    if (settings["system"] != fresh_inference.SYSTEM or settings["schema"] != fresh_inference.Drafts.model_json_schema()
            or settings.get("history_global_k", 8) != 8 or settings.get("history_company_k", 8) != 8):
        raise ValueError("Claude settings differ from the previously frozen model")
    if local_rag.model_fingerprint() != settings["embedding_assets"]:
        raise ValueError("Embedding assets differ from the locked settings")
    history = read_frame(output / "history.csv", [*META_FIELDS, "nbim_vote"])
    if history.empty or not known_target(history, "against_board").all():
        raise ValueError("Historical reference needs known votes and board recommendations")
    if not history.meeting_date.le(policy["history_cutoff"]).all():
        raise ValueError("Historical reference crosses the frozen history cutoff")
    query = validate_ballots(read_frame(ballots_csv, META_FIELDS), history, policy)
    discovery_path = output / "discovery.json"
    if policy.get("enumeration_complete_required"):
        discovery = read_json(discovery_path)
        if discovery.get("complete") is not True or discovery.get("company_queries_completed") != len(policy["company_queries"]):
            raise ValueError("The frozen company universe has not been fully enumerated")
        candidates = discovery["candidates"]
        expected = {str(row["meeting_id"]): (str(row["company_id"]), row["meeting_date"]) for row in candidates}
        actual = {row.meeting_id: (row.company_id, row.meeting_date) for row in query.itertuples()}
        if len(expected) != len(candidates) or actual != expected:
            raise ValueError("Ballots do not cover exactly all predeclared fresh candidate meetings")
    if policy["history_cutoff"] >= policy["date_start"]:
        raise ValueError("Frozen historical pool must precede the new test period")
    model = joblib.load(output / "models/learner.joblib")
    if model.get("target") != "against_board" or model.get("config") != fresh_inference.LOCAL_CONFIG:
        raise ValueError("Wrong frozen local model")
    if not isinstance(settings["local_threshold"], (float, int)) or not 0 <= settings["local_threshold"] <= 1:
        raise ValueError("Invalid frozen decision threshold")
    # Nothing in this function opens a fresh reference/outcome file.
    reference_vectors, reference_embedding = embedding_matrix(history[META_FIELDS])
    query_vectors, query_embedding = embedding_matrix(query)
    bundles = fresh_inference.build_bundles(history, query, reference_vectors, query_vectors)
    ballot_path = output / "ballots.csv"
    if ballot_path.exists():
        if Path(ballots_csv).resolve() != ballot_path.resolve():
            raise ValueError("Ballot snapshot already exists")
        existing = read_frame(ballot_path, META_FIELDS)
        if existing.to_dict("records") != query.to_dict("records"):
            raise ValueError("Existing ballot snapshot is not canonically ordered")
    else:
        with ballot_path.open("x", encoding="utf-8", newline="") as handle:
            query.to_csv(handle, index=False)
    with (output / "vectors.npz").open("xb") as handle:
        np.savez_compressed(handle, reference=reference_vectors, query=query_vectors)
    bundle_paths = {}
    for bundle in bundles:
        mid = bundle["meeting"]["meeting_id"]
        path = output / "bundles" / f"{mid}.json"
        immutable_json(path, bundle)
        bundle_paths[mid] = str(path.relative_to(output))
    (output / "source").mkdir(exist_ok=True)
    code = {}
    for name in SOURCE_FILES:
        code[name] = digest(ROOT / name)
        with (output / "source" / name).open("xb") as handle:
            handle.write((ROOT / name).read_bytes())
    artifact_names = ["selection-policy.json", "locked-settings.json", "preflight-freeze.json", "history.csv", "models/learner.joblib",
                      "ballots.csv", "vectors.npz", *bundle_paths.values(), *(f"source/{name}" for name in code), *capture_artifacts]
    if policy.get("enumeration_complete_required"):
        artifact_names.append("discovery.json")
    plan = signed({"created_at": now(), "evaluation_kind": "FROZEN_NEW_MEETINGS", "target": "against_board",
                   "policy": policy, "settings": settings, "code": code, "reference_commitment": reference_commitment,
                   "artifacts": {name: digest(output / name) for name in artifact_names},
                   "cohort": {"rows": len(query), "meetings": len(bundles),
                              "company_date_groups": len(query[["company_id", "meeting_date"]].drop_duplicates())},
                   "meeting_ids": [bundle["meeting"]["meeting_id"] for bundle in bundles], "bundles": bundle_paths,
                   "reference_embedding": reference_embedding, "query_embedding": query_embedding,
                   "history_policy": "fixed old-data snapshot; strict five-day cutoff; entire fresh cohort excluded",
                   "fresh_outcomes_used": False})
    immutable_json(output / "freeze.json", plan)
    return status(output)


def _prediction_files(output, plan):
    return ["local-predictions.json", *(f"responses/{mid}.json" for mid in plan["meeting_ids"])]


def seal_predictions(output=OUTPUT):
    output = Path(output)
    plan = load_frozen(output)
    names = _prediction_files(output, plan)
    if not all((output / name).exists() for name in names):
        return None
    for name in names:
        value = checked_json(output / name)
        if value["freeze_id"] != plan["record_id"]:
            raise ValueError("Prediction belongs to a different frozen cohort")
    path = output / "prediction-seal.json"
    if path.exists():
        seal = checked_json(path)
        for name, expected in seal["artifacts"].items():
            checked_path(output, name, expected)
        return seal
    seal = signed({"sealed_at": now(), "freeze_id": plan["record_id"],
                   "artifacts": {name: digest(output / name) for name in names}, "fresh_outcomes_used": False})
    immutable_json(path, seal)
    return seal


def predict_local(output=OUTPUT):
    output = Path(output)
    plan = load_frozen(output)
    path = output / "local-predictions.json"
    if path.exists():
        result = checked_json(path)
        if result["freeze_id"] != plan["record_id"]:
            raise ValueError("Local prediction cohort changed")
        seal_predictions(output)
        return result
    query = read_frame(output / "ballots.csv", META_FIELDS)
    history = read_frame(output / "history.csv", [*META_FIELDS, "nbim_vote"])
    state = joblib.load(output / "models/learner.joblib")
    with np.load(output / "vectors.npz", allow_pickle=False) as vectors:
        scores = fresh_inference.local_predict(state, query, vectors["query"], history, vectors["reference"])
    if len(scores) != len(query):
        raise ValueError("Local predictions do not cover the entire cohort")
    threshold = plan["settings"]["local_threshold"]
    items = [{"meeting_id": row["meeting_id"], "item_no": row["item_no"],
              "score": float(value) if np.isfinite(value) else None,
              "against_board": bool(value >= threshold) if np.isfinite(value) else None}
             for row, value in zip(query.to_dict("records"), scores)]
    result = signed({"freeze_id": plan["record_id"], "created_at": now(), "threshold": threshold,
                     "items": items, "fresh_outcomes_used": False})
    immutable_json(path, result)
    seal_predictions(output)
    return result


def predict_claude(output=OUTPUT, workers=4, limit=None):
    output = Path(output)
    plan = load_frozen(output)
    if not os.getenv("ANTHROPIC_API_KEY", "").strip():
        raise ValueError("ANTHROPIC_API_KEY is missing")
    if not 1 <= workers <= 4 or (limit is not None and not 1 <= limit <= len(plan["meeting_ids"])):
        raise ValueError("Invalid workers or meeting limit")
    lock = output / "running.lock"
    with lock.open("x") as handle:
        handle.write(now())
    try:
        todo = []
        for mid in plan["meeting_ids"][:limit]:
            if (output / "responses" / f"{mid}.json").exists():
                record = checked_json(output / "responses" / f"{mid}.json")
                if record["freeze_id"] != plan["record_id"]:
                    raise ValueError("Response belongs to another frozen cohort")
            elif (output / "requests" / f"{mid}.json").exists():
                raise ValueError("Interrupted request; inspect it rather than paying twice")
            else:
                todo.append(mid)

        def call(mid):
            bundle_path = output / plan["bundles"][mid]
            bundle = read_json(bundle_path)
            record = {"meeting_id": mid, "freeze_id": plan["record_id"], "bundle_sha256": digest(bundle_path), "started_at": now()}
            immutable_json(output / "requests" / f"{mid}.json", signed(record))
            start = time.monotonic()
            try:
                with anthropic.Anthropic(max_retries=0, timeout=180.) as client:
                    result = fresh_inference.generate_review(bundle, client=client,
                        model=plan["settings"]["model"], effort=plan["settings"]["effort"])
                record.update(status="completed", result=result, usage=result.get("usage", {}))
            except Exception as error:
                record.update(status="failed", error={"type": type(error).__name__, "status_code": getattr(error, "status_code", None),
                              "category": getattr(error, "category", None)}, usage=getattr(error, "usage", {}))
                if isinstance(getattr(error, "response", None), dict):
                    record["rejected_response"] = error.response
            record["elapsed_seconds"] = round(time.monotonic() - start, 3)
            record = signed(record)
            immutable_json(output / "responses" / f"{mid}.json", record)
            return record

        with ThreadPoolExecutor(max_workers=workers) as pool:
            for start in range(0, len(todo), workers):
                stop = False
                for future in as_completed([pool.submit(call, mid) for mid in todo[start:start + workers]]):
                    record = future.result()
                    print(f"{record['meeting_id']}: {record['status']}", flush=True)
                    stop |= record.get("error", {}).get("status_code") in (401, 403, 429)
                if stop:
                    break
    finally:
        lock.unlink(missing_ok=True)
    seal_predictions(output)
    return status(output)


def status(output=OUTPUT):
    output = Path(output)
    plan = load_frozen(output)
    completed = failed = pending = 0
    for mid in plan["meeting_ids"]:
        path = output / "responses" / f"{mid}.json"
        if path.exists():
            record = checked_json(path)
            completed += record["status"] == "completed"
            failed += record["status"] == "failed"
        elif (output / "requests" / f"{mid}.json").exists():
            pending += 1
    return {"freeze_id": plan["record_id"], "cohort": plan["cohort"], "local_completed": (output / "local-predictions.json").exists(),
            "claude_completed": completed, "claude_failed": failed, "claude_interrupted_or_pending": pending,
            "claude_unattempted": len(plan["meeting_ids"]) - completed - failed - pending,
            "predictions_sealed": (output / "prediction-seal.json").exists(), "scored": (output / "report.json").exists()}


def score(references_csv, output=OUTPUT):
    output = Path(output)
    plan = load_frozen(output)
    seal_path = output / "prediction-seal.json"
    if not seal_path.exists():
        raise ValueError("Both models must finish and predictions must be sealed before opening fresh outcomes")
    seal = checked_json(seal_path)
    if seal["freeze_id"] != plan["record_id"] or set(seal["artifacts"]) != set(_prediction_files(output, plan)):
        raise ValueError("Incomplete prediction seal")
    for name, expected in seal["artifacts"].items():
        checked_path(output, name, expected)
    if (output / "report.json").exists():
        raise ValueError("This frozen cohort has already been scored; preserve its original report")
    if plan.get("reference_commitment") and digest(references_csv) != plan["reference_commitment"]:
        raise ValueError("Fresh references differ from the source commitment made before prediction")
    # The first fresh-target access in the entire workflow occurs below this gate.
    labels = read_frame(references_csv, [*KEY, "nbim_vote"])
    query = read_frame(output / "ballots.csv", META_FIELDS)
    if labels.duplicated(KEY).any() or set(map(tuple, labels[KEY].values)) != set(map(tuple, query[KEY].values)):
        raise ValueError("Reference outcomes must cover exactly the frozen ballot cohort")
    if not labels.nbim_vote.isin([*VOTES, ""]).all():
        raise ValueError("Unexpected reference vote encoding")
    frame = query.merge(labels, on=KEY, how="left", validate="one_to_one")
    local = checked_json(output / "local-predictions.json")
    local_map = {(r["meeting_id"], r["item_no"]): r["score"] for r in local["items"]}
    claude, failures, usage = {}, [], {}
    for mid in plan["meeting_ids"]:
        record = checked_json(output / "responses" / f"{mid}.json")
        if record["status"] == "completed":
            for item in record["result"]["items"]:
                claude[mid, str(item["item"])] = item["vote"]
        else:
            failures.append({"meeting_id": mid, **record["error"]})
        for key, value in record.get("usage", {}).items():
            if isinstance(value, int) and not isinstance(value, bool):
                usage[key] = usage.get(key, 0) + value
    eligible = known_target(frame, "against_board")
    scored = frame.loc[eligible]
    y = target_labels(scored, "against_board")
    local_scores = [local_map.get((r.meeting_id, r.item_no)) for r in scored.itertuples()]
    claude_scores = [None if claude.get((r.meeting_id, r.item_no)) not in VOTES else
                     float(claude[r.meeting_id, r.item_no] != r.mgmt_rec) for r in scored.itertuples()]
    mot_rows = frame.loc[known_target(frame, "mot")]
    mot_scores = [None if claude.get((r.meeting_id, r.item_no)) not in VOTES else
                  float(claude[r.meeting_id, r.item_no] == "MOT") for r in mot_rows.itertuples()]
    result = signed({"freeze_id": plan["record_id"], "prediction_seal_sha256": digest(seal_path), "scored_at": now(),
                     "evaluation_kind": "FROZEN_NEW_MEETINGS", "target": "against_board", "cohort": plan["cohort"],
                     "known_disagreement_rows": int(eligible.sum()), "unknown_nbim": int(frame.nbim_vote.eq("").sum()),
                     "known_nbim_unknown_board": int((frame.nbim_vote.ne("") & frame.mgmt_rec.eq("")).sum()),
                     "local": measure(y, local_scores, plan["settings"]["local_threshold"]),
                     "claude": measure(y, claude_scores, .5), "claude_literal_mot": measure(target_labels(mot_rows, "mot"), mot_scores, .5),
                     "local_threshold": plan["settings"]["local_threshold"], "claude_model": plan["settings"]["model"],
                     "failed_meetings": failures, "api_attempts": len(plan["meeting_ids"]), "usage": usage,
                     "estimated_usd": usage_cost(usage, plan["settings"]["model"]), "references_sha256": digest(references_csv),
                     "limits": ["Previously exposed company universe and one calendar month; not a global representative sample.",
                                "Historical meeting dates approximate information availability.",
                                "No fresh test outcomes entered either model or historical context.",
                                "Unknown reference/board values are reported and excluded only after prediction.",
                                "Failures remain in recall denominators for known target outcomes."]})
    with (output / "evaluation-labels.csv").open("xb") as handle:
        handle.write(Path(references_csv).read_bytes())
    immutable_json(output / "report.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "local", "claude", "score", "status"))
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--ballots", type=Path)
    parser.add_argument("--references", type=Path)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    if args.command == "prepare":
        if args.ballots is None:
            parser.error("prepare requires --ballots")
        result = prepare(args.ballots, args.output)
    elif args.command == "score":
        if args.references is None:
            parser.error("score requires --references")
        result = score(args.references, args.output)
    elif args.command == "local":
        result = predict_local(args.output)
    elif args.command == "claude":
        result = predict_claude(args.output, args.workers, args.limit)
    else:
        result = status(args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
