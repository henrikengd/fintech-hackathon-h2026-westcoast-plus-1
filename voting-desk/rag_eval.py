"""Evaluate local RAG on eligible 2024 development meetings; never tune on held-out meetings."""
import boot  # noqa: F401
import argparse
from collections import defaultdict
import csv
from datetime import datetime, timezone
from hashlib import sha256
import importlib
import itertools
import json
import os
from pathlib import Path
import tempfile
import time

import desk
from local_rag import RagIndex
import rag_review


ROOT = Path(__file__).resolve().parent
DEFAULT_DB = ROOT / "data/local-rag/development-2024.sqlite"
OUTPUT = ROOT / "data/local-rag/rag-evaluation-v1"
VOTES = ROOT / "data/real_votes.csv"
TRAIN = ROOT / "data/mixed-80-20/train.csv"
TEST = ROOT / "data/mixed-80-20/test.csv"
LEGACY = ROOT / "results/items_val.csv"
AGENT = ROOT / "results/raw/agent_val.jsonl"
VALID_VOTES = {"FOR", "MOT", "AVSTÅ"}


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def fingerprint(value):
    return sha256(canonical(value).encode()).hexdigest()


def file_hash(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def read_csv(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def key(row):
    return str(row["meeting_id"]), str(row.get("item_no", row.get("item", "")))


def load_evaluation(db=DEFAULT_DB):
    """Select the indexed cohort only after validating both meeting and company/date boundaries."""
    index = RagIndex(db)
    try:
        meetings = index.meetings()
    finally:
        index.close()
    ids = {m["meeting_id"] for m in meetings}
    if not ids or len(ids) > 22 or len(ids) != len(meetings):
        raise ValueError("This experiment requires 1–22 distinct indexed development meetings")
    source, train, test = read_csv(VOTES), read_csv(TRAIN), read_csv(TEST)
    rows = [row for row in source if row["meeting_id"] in ids]
    keys = {key(row) for row in rows}
    train_keys, test_keys = {key(row) for row in train}, {key(row) for row in test}
    test_meetings = {r["meeting_id"] for r in test}
    test_groups = {(r["company_id"], r["meeting_date"]) for r in test}
    if not rows or len(keys) != len(rows) or {r["meeting_id"] for r in rows} != ids:
        raise ValueError("Missing or duplicate source proposals in indexed meetings")
    if not keys <= train_keys or keys & test_keys or ids & test_meetings:
        raise ValueError("An indexed meeting belongs to the reserved mixed-year test set")
    if any((r["company_id"], r["meeting_date"]) in test_groups for r in rows):
        raise ValueError("An indexed company/date group overlaps the reserved test set")
    if any(not r["meeting_date"].startswith("2024-") for r in rows):
        raise ValueError("Only 2024 development meetings may be evaluated here")
    by_meeting = {r["meeting_id"]: r for r in rows}
    if any(m["meeting_date"] != by_meeting[m["meeting_id"]]["meeting_date"] for m in meetings):
        raise ValueError("Index and ballot meeting dates disagree")
    if any(r["nbim_vote"] not in VALID_VOTES | {""} for r in rows):
        raise ValueError("Unknown target encoding")
    rows.sort(key=lambda r: (r["meeting_date"], r["meeting_id"], r["item_no"]))
    meetings.sort(key=lambda m: (m["meeting_date"], m["meeting_id"]))
    identity = {"source_sha256": file_hash(VOTES), "train_sha256": file_hash(TRAIN),
                "test_sha256": file_hash(TEST), "index_sha256": file_hash(db),
                "meeting_ids": [m["meeting_id"] for m in meetings], "row_keys_sha256": fingerprint(sorted(keys))}
    return {"rows": rows, "meetings": meetings, "identity": identity, "data_id": fingerprint(identity)[:16]}


def score_votes(rows, predmap):
    """Literal MOT scoring. Missing predictions remain false negatives for known MOT labels."""
    known = [r for r in rows if r["nbim_vote"] in VALID_VOTES]
    tp = fp = fn = predicted = nulls = 0
    rules = evidence = manual = 0
    rule_observed = evidence_observed = manual_observed = 0
    legacy_flags = {"fact_needed": 0, "injection_suspected": 0}
    legacy_observed = 0
    for row in known:
        item = predmap.get(key(row))
        item = {"vote": item} if isinstance(item, str) else (item or {})
        vote, positive = item.get("vote"), row["nbim_vote"] == "MOT"
        tp += vote == "MOT" and positive
        fp += vote == "MOT" and not positive
        fn += vote != "MOT" and positive
        predicted += vote in VALID_VOTES
        nulls += vote not in VALID_VOTES
        if "rule_quote_verified" in item:
            rule_observed += 1
            rules += item["rule_quote_verified"] is True
        if "evidence" in item:
            evidence_observed += 1
            evidence += bool(item["evidence"]) and all(e.get("quote_verified") is True for e in item["evidence"])
        if "requires_manual_review" in item:
            manual_observed += 1
            manual += bool(item["requires_manual_review"])
        elif vote not in VALID_VOTES:
            manual += 1
        if "legacy_fact_needed" in item:
            legacy_observed += 1
            for flag in legacy_flags:
                legacy_flags[flag] += bool(item.get("legacy_" + flag))
    n = len(known)
    return {"rows": len(rows), "known_votes": n, "unknown_labels_excluded": len(rows) - n,
            "mot": sum(r["nbim_vote"] == "MOT" for r in known), "tp": tp, "fp": fp, "fn": fn,
            "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / (tp + fn) if tp + fn else None,
            "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None,
            "recommendations": predicted, "recommendation_coverage": predicted / n if n else None,
            "null_or_failed_predictions": nulls,
            "verified_rule_quotes": rules if rule_observed else None,
            "verified_rule_quote_coverage": rules / n if n and rule_observed else None,
            "verified_evidence": evidence if evidence_observed else None,
            "verified_evidence_coverage": evidence / n if n and evidence_observed else None,
            "manual_review": manual if manual_observed or nulls else None,
            "manual_review_share": manual / n if n and (manual_observed or nulls) else None,
            "legacy_sparse_flags": {**legacy_flags, "observed_rows": legacy_observed,
                                    "note": "Saved legacy flags only; not reconstructed routing"} if legacy_observed else None,
            "coverage_denominator": "known NBIM votes only, including missing and failed predictions",
            "note": "Citation checks measure quote presence, not logical support. Missing outputs are retained in vote-score denominators."}


def baseline_predictions(rows):
    selected = {r["meeting_id"] for r in rows}
    board = {key(r): {"vote": r["mgmt_rec"]} for r in rows}
    old = {key(r): {"vote": r["draft"], "rule_quote_verified": r.get("cited") == "True",
                    "requires_manual_review": r.get("lane") == desk.UNCLEAR}
           for r in read_csv(LEGACY) if r["meeting_id"] in selected}
    agent = {}
    with Path(AGENT).open(encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            if record["meeting_id"] not in selected:
                continue
            for item in record.get("items") or []:
                agent[(record["meeting_id"], str(item["item"]))] = {
                    "vote": item["vote"], "rule_quote_verified": desk.verified(item, next(r["meeting_date"] for r in rows if r["meeting_id"] == record["meeting_id"])),
                    "evidence": [{"quote_verified": bool(item.get("evidence_ok"))}] if item.get("evidence_quote") else [],
                    "legacy_fact_needed": bool(item.get("fact_needed")),
                    "legacy_injection_suspected": bool(item.get("injection_suspected"))}
    return {"follow_board": board, "legacy_cached_system": old, "legacy_cached_document_agent": agent}


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.replace(path)


def immutable_json(path, value):
    """Publish a complete durable cache record without replacing an existing record."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        try:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    try:
        os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def bind_output(output, data):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    path = output / "dataset.json"
    value = {"data_id": data["data_id"], "identity": data["identity"], "meetings": data["meetings"],
             "rows": len(data["rows"]), "scope": "2024 development only; no reserved mixed-year test meetings"}
    if path.exists() and json.loads(path.read_text()) != value:
        raise ValueError("Output belongs to another dataset; choose a new --output")
    if not path.exists():
        immutable_json(path, value)
    return output


def baseline(db=DEFAULT_DB, output=OUTPUT):
    data = load_evaluation(db)
    output = bind_output(output, data)
    result = {"data_id": data["data_id"], "meetings": len(data["meetings"]),
              "methods": {name: score_votes(data["rows"], values) for name, values in baseline_predictions(data["rows"]).items()},
              "interpretation": "Legacy systems differ in prompts, history and generation. They are contextual baselines, not controlled retrieval comparisons. Cached document-agent fact/injection flags are sparse and do not reconstruct its historical routing; manual-review share is unavailable."}
    atomic_json(output / "baseline.json", result)
    return result


def generation_settings():
    return {"model": desk.MODEL, "effort": desk.EFFORT, "system": rag_review.SYSTEM,
            "schema": rag_review.Drafts.model_json_schema(),
            "code": {name: file_hash(ROOT / name) for name in ("rag_review.py", "local_rag.py", "desk.py")}}


def retrieval_settings(strategy):
    return {"strategy": strategy, "code": {"rag_review_enriched.py": file_hash(ROOT / "rag_review_enriched.py")}
            if strategy == "meeting" else {}}


def configuration_id(generation_id, mode, retrieval):
    return fingerprint({"generation_id": generation_id, "mode": mode, "retrieval": retrieval})[:16]


def run(mode, db=DEFAULT_DB, output=OUTPUT, limit=None, strategy="proposal"):
    if strategy not in ("proposal", "meeting") or mode not in ("keyword", "hybrid", "vector") or (limit is not None and not 1 <= limit <= 22):
        raise ValueError("Choose a supported mode and a limit between 1 and 22")
    if not os.getenv("ANTHROPIC_API_KEY", "").strip():
        raise ValueError("ANTHROPIC_API_KEY is missing; add it to the ignored voting-desk/.env before running paid evaluations")
    data = load_evaluation(db)
    output = bind_output(output, data)
    generation = generation_settings()
    generation_id = fingerprint(generation)[:16]
    retrieval = retrieval_settings(strategy)
    settings = {"generation": generation, "retrieval": retrieval}
    config_id = configuration_id(generation_id, mode, retrieval)
    prepare = rag_review.prepare_bundle if strategy == "proposal" else importlib.import_module("rag_review_enriched").prepare_bundle
    index = RagIndex(db)
    try:
        for meeting in data["meetings"][:limit]:
            mid = meeting["meeting_id"]
            bundle = prepare(mid, db=db, mode=mode, index=index)
            cache_key = fingerprint({"data_id": data["data_id"], "bundle": bundle, "settings": settings})
            path = output / "cache" / mode / config_id / mid / f"{cache_key}.json"
            candidates = [(path, cache_key)]
            if strategy == "proposal":
                # Reuse exact earlier proposal calls without changing or duplicating their records.
                old_config = fingerprint({"generation_id": generation_id, "mode": mode})[:16]
                old_key = fingerprint({"data_id": data["data_id"], "bundle": bundle, "settings": generation})
                candidates.append((output / "cache" / mode / old_config / mid / f"{old_key}.json", old_key))
            existing = next(((candidate, expected) for candidate, expected in candidates if candidate.exists()), None)
            if existing:
                cached = json.loads(existing[0].read_text())
                if cached["cache_key"] != existing[1]:
                    raise ValueError("Cache identity mismatch")
                print(f"{strategy}/{mode} {mid}: reused {cached['status']}", flush=True)
                continue
            record = {"cache_key": cache_key, "data_id": data["data_id"], "mode": mode,
                      "strategy": strategy,
                      "config_id": config_id, "generation_id": generation_id, "settings": settings,
                      "meeting_id": mid, "created_at": datetime.now(timezone.utc).isoformat(), "bundle": bundle}
            start = time.monotonic()
            try:
                record.update(status="completed", result=rag_review.generate_review(bundle))
            except Exception as error:
                # Never persist the exception string: provider errors can contain credential fragments.
                record.update(status="failed", error={"type": type(error).__name__, "status_code": getattr(error, "status_code", None)})
            record["elapsed_seconds"] = round(time.monotonic() - start, 3)
            immutable_json(path, record)
            print(f"{strategy}/{mode} {mid}: {record['status']} ({record['elapsed_seconds']}s)", flush=True)
            report(db, output)
            if record["status"] == "failed" and record["error"]["status_code"] in (401, 403, 429):
                break
    finally:
        index.close()
    return report(db, output)


def prediction_map(records):
    predictions = {}
    for record in records:
        items = record["result"]["items"] if record["status"] == "completed" else [
            {"item": proposal["item"], "vote": None, "rule_quote_verified": False,
             "evidence": [], "requires_manual_review": True}
            for proposal in record["bundle"]["proposals"]]
        predictions.update({(record["meeting_id"], str(item["item"])): item for item in items})
    return predictions


def report(db=DEFAULT_DB, output=OUTPUT):
    data = load_evaluation(db)
    output = bind_output(output, data)
    groups = defaultdict(dict)
    for path in sorted((output / "cache").glob("*/*/*/*.json")):
        record = json.loads(path.read_text())
        if record["data_id"] != data["data_id"] or record["meeting_id"] not in {m["meeting_id"] for m in data["meetings"]}:
            raise ValueError("Cached predictions use a different dataset")
        strategy = record.get("strategy", "proposal")
        # Old and new proposal cache layouts describe the same retrieval configuration.
        config_id = record["config_id"] if "retrieval" in record["settings"] else configuration_id(
            record["generation_id"], record["mode"], {"strategy": "proposal", "code": {}})
        group = groups[(record["mode"], strategy, config_id, record["generation_id"])]
        old = group.get(record["meeting_id"])
        if old is None or record["created_at"] > old["created_at"]:
            group[record["meeting_id"]] = record
    legacy = baseline_predictions(data["rows"])
    results, exports = [], []
    for (mode, strategy, config_id, generation_id), by_meeting in sorted(groups.items()):
        records = list(by_meeting.values())
        attempted, completed = set(by_meeting), {r["meeting_id"] for r in records if r["status"] == "completed"}
        rows = [r for r in data["rows"] if r["meeting_id"] in attempted]
        pred = prediction_map(records)
        usage = defaultdict(int)
        for record in records:
            for field, value in record.get("result", {}).get("usage", {}).items():
                if isinstance(value, int):
                    usage[field] += value
        results.append({"mode": mode, "strategy": strategy, "config_id": config_id, "generation_id": generation_id,
                        "attempted_meetings": len(attempted), "completed_meetings": len(completed),
                        "failed_meetings": len(attempted - completed), "pending_meetings": len(data["meetings"]) - len(attempted),
                        "metrics": score_votes(rows, pred), "same_rows_baselines": {name: score_votes(rows, values) for name, values in legacy.items()},
                        "usage": dict(usage), "usage_note": "Usage is available only for completed, validated responses; failed requests may also incur charges.",
                        "elapsed_seconds": sum(r["elapsed_seconds"] for r in records)})
        for row in rows:
            item = pred.get(key(row), {})
            exports.append({"mode": mode, "strategy": strategy, "config_id": config_id, "meeting_id": row["meeting_id"], "item": row["item_no"],
                            "company": row["company"], "proposal_text": row["proposal_text"], "nbim_vote": row["nbim_vote"],
                            "prediction": item.get("vote"), "call_status": by_meeting[row["meeting_id"]]["status"],
                            "requires_manual_review": item.get("requires_manual_review", True)})
    pairs = []
    for left, right in itertools.combinations(sorted(groups), 2):
        if left[:2] == right[:2] or left[3] != right[3]:
            continue
        a, b = groups[left], groups[right]
        common = {mid for mid in set(a) & set(b) if a[mid]["status"] == b[mid]["status"] == "completed"}
        rows = [r for r in data["rows"] if r["meeting_id"] in common]
        pairs.append({"left": left[0], "right": right[0], "left_strategy": left[1], "right_strategy": right[1],
                      "left_config_id": left[2], "right_config_id": right[2], "generation_id": left[3],
                      "common_completed_meetings": len(common), "meeting_ids": sorted(common),
                      "excluded_from_pair": len(data["meetings"]) - len(common),
                      "left_metrics": score_votes(rows, prediction_map(a.values())),
                      "right_metrics": score_votes(rows, prediction_map(b.values())),
                      "note": "Paired complete-call subset only. Main mode metrics above retain failed attempted calls."})
    result = {"data_id": data["data_id"], "cohort_meetings": len(data["meetings"]), "cohort_rows": len(data["rows"]),
              "runs": results, "paired_completed": pairs, "evaluation_kind": "EXPLORATORY_DEVELOPMENT",
              "no_holdout_claim": "All scores concern previously used 2024 development records; this is not a fresh final test."}
    atomic_json(output / "report.json", result)
    atomic_json(output / "predictions.json", exports)
    if exports:
        with (output / "predictions.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(exports[0]))
            writer.writeheader()
            writer.writerows(exports)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("baseline", "run", "report"))
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--mode", choices=("keyword", "hybrid", "vector"), default="hybrid")
    parser.add_argument("--strategy", choices=("proposal", "meeting"), default="proposal")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args(argv)
    result = run(args.mode, args.db, args.output, args.limit, args.strategy) if args.command == "run" else globals()[args.command](args.db, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
