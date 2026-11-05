"""Describe a fixed development result; no model training, threshold choice or APIs.

  python vote_diagnostics.py

Writes a separate diagnostics directory. Document availability means that matching
indexed metadata passes the strict publication-date cutoff; it does not establish
that the document contains a required fact or supports the observed NBIM vote.
"""
import argparse
from datetime import date, timedelta
from hashlib import sha256
import json
from pathlib import Path
import sqlite3

import numpy as np
import pandas as pd

import vote_features

ROOT = Path(__file__).resolve().parent
DEFAULT_INPUT = ROOT / "data/local-rag/vote-learning-v2"
DEFAULT_OUTPUT = ROOT / "data/local-rag/vote-learning-v2-diagnostics"
DEFAULT_DB = ROOT / "data/local-rag/development-2024.sqlite"
FACT_TASKS = {
    "director": ["candidate identity and independence", "CEO and chair roles", "committee membership and chairs",
                 "meeting attendance", "outside board positions"],
    "pay": ["vesting periods", "award dilution and limits", "performance conditions and measurement periods",
            "award structure and maximum remuneration"],
    "auditor": ["auditor identity and tenure", "audit and non-audit fees", "independence and conflicts"],
    "capital": ["transaction size and dilution", "price and discount", "pre-emption rights", "authorization duration", "use of proceeds"],
    "shareholder": ["full shareholder proposal text", "board response", "requested action and material company impacts"],
    "other": ["full proposal text", "board response", "applicable voting rule and its required facts"],
}


def file_hash(path):
    digest = sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def required_facts(family):
    return {"status": "pending_fact_review", "family": family,
            "facts_to_verify": FACT_TASKS.get(family, FACT_TASKS["other"]),
            "interpretation": "Review hypotheses only; no rule violation or source support has been established."}


def confusion(frame):
    y = frame["nbim_vote"].eq("MOT").to_numpy()
    predicted = frame["predicted_mot"].to_numpy(dtype=bool)
    tp, fp, fn, tn = [int(mask.sum()) for mask in (y & predicted, ~y & predicted, y & ~predicted, ~y & ~predicted)]
    missing = int(frame["score"].isna().sum())
    return {"rows": len(frame), "mot": int(y.sum()), "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / (tp + fn) if tp + fn else None,
            "missing_scores": missing, "missing_score_share": missing / len(frame) if len(frame) else None}


def cluster_bootstrap(frame, draws=1000, seed=2026):
    """Resample complete company/date groups, including TN and missing-score rows."""
    if frame.empty or draws < 1:
        raise ValueError("Bootstrap needs nonempty data and at least one draw")
    keys = ("rows", "tp", "fp", "fn", "tn", "missing_scores")
    clusters = [confusion(part) for _, part in frame.groupby(["company_id", "meeting_date"], sort=True, dropna=False)]
    counts = np.asarray([[item[key] for key in keys] for item in clusters], dtype=np.int64)
    selected = np.random.default_rng(seed).integers(0, len(clusters), size=(draws, len(clusters)))
    totals = counts[selected].sum(axis=1)
    result = {"method": "95% percentile cluster bootstrap, company_id/meeting_date groups",
              "draws": draws, "seed": seed, "clusters": len(clusters), "point": confusion(frame),
              "row_count_range": [int(totals[:, 0].min()), int(totals[:, 0].max())],
              "note": "Conditional on the fixed model and threshold; does not include model-selection uncertainty. Undefined denominators are reported and excluded from interval percentiles."}
    for metric, denominator in (("precision", totals[:, 1] + totals[:, 2]), ("recall", totals[:, 1] + totals[:, 3])):
        valid = denominator > 0
        sampled = totals[valid, 1] / denominator[valid]
        result[metric] = {"lower": float(np.quantile(sampled, .025)) if len(sampled) else None,
                          "upper": float(np.quantile(sampled, .975)) if len(sampled) else None,
                          "valid_draws": int(valid.sum()), "undefined_draws": int((~valid).sum())}
    return result


def document_inventory(db):
    path = Path(db).resolve()
    if not path.is_file():
        raise FileNotFoundError("Document database is absent; availability cannot be assessed")
    inventory = {}
    # Read metadata fields only, without document text, embeddings or a writable DB connection.
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as connection:
        records = connection.execute("""SELECT id, meeting_id,
            json_extract(data,'$.company_id'), json_extract(data,'$.meeting_date'),
            json_extract(data,'$.filed'), json_extract(data,'$.url'), json_extract(data,'$.sha256')
            FROM documents ORDER BY meeting_id, id""")
        for identifier, meeting, company, meeting_date, filed, url, source_hash in records:
            inventory.setdefault(str(meeting), []).append({"document_id": identifier, "company_id": str(company),
                "meeting_date": meeting_date, "filed": filed, "url": url, "source_sha256": source_hash})
    return inventory


def source_status(row, inventory):
    cutoff = (date.fromisoformat(row["meeting_date"]) - timedelta(days=5)).isoformat()
    documents = []
    for document in inventory.get(row["meeting_id"], []):
        reason = None
        if document["company_id"] != row["company_id"] or document["meeting_date"] != row["meeting_date"]:
            reason = "meeting_metadata_mismatch"
        else:
            try:
                if date.fromisoformat(document["filed"]).isoformat() >= cutoff:
                    reason = "filed_at_or_after_exclusive_cutoff"
            except (TypeError, ValueError):
                reason = "publication_date_unknown_or_invalid"
        documents.append({**document, "decision_cutoff_exclusive": cutoff, "eligible": reason is None, "exclusion_reason": reason})
    eligible = sum(document["eligible"] for document in documents)
    return {"source_document_available": bool(eligible), "indexed_document_count": len(documents),
            "eligible_document_count": eligible, "decision_cutoff_exclusive": cutoff, "source_documents": documents}


def coverage(frame):
    available = int(frame["source_document_available"].sum())
    return {"rows": len(frame), "with_eligible_documents": available, "without_eligible_documents": len(frame) - available,
            "document_coverage": available / len(frame) if len(frame) else None}


def run(source=DEFAULT_INPUT, output=DEFAULT_OUTPUT, db=DEFAULT_DB, draws=1000, seed=2026):
    source, output = Path(source), Path(output)
    if output.exists():
        raise FileExistsError("Diagnostics directory already exists; choose a new output")
    summary = json.loads((source / "summary.json").read_text())
    if file_hash(source / "development.csv") != summary["artifacts"]["development.csv"]:
        raise ValueError("Development predictions no longer match the experiment manifest")
    frame = pd.read_csv(source / "development.csv", dtype=str, keep_default_na=False)
    if frame.empty or not frame["meeting_date"].str.startswith("2024-").all():
        raise ValueError("Diagnostics require the fixed 2024 development cohort")
    if frame.duplicated(["meeting_id", "item_no"]).any() or not frame["nbim_vote"].isin(["FOR", "MOT", "AVSTÅ"]).all():
        raise ValueError("Duplicate proposal identities or unknown evaluation labels")
    threshold = float(summary["selected_threshold"])
    if not np.isfinite(threshold) or not np.allclose(pd.to_numeric(frame["threshold"], errors="raise"), threshold, rtol=0, atol=1e-14):
        raise ValueError("Prediction thresholds differ from the fixed selected threshold")
    frame["score"] = pd.to_numeric(frame["score"].replace("", np.nan), errors="raise")
    if np.isinf(frame["score"].to_numpy()).any():
        raise ValueError("Infinite prediction scores")
    frame["predicted_mot"] = frame["score"].ge(threshold)
    frame["error"] = np.select([frame["predicted_mot"] & frame["nbim_vote"].ne("MOT"),
                               ~frame["predicted_mot"] & frame["nbim_vote"].eq("MOT")], ["FP", "FN"], "")
    measured = confusion(frame)
    if any(measured[key] != summary["development_selected"][key] for key in ("tp", "fp", "fn", "tn")):
        raise ValueError("Saved scores disagree with the selected experiment's confusion counts")
    frame["safe_family"] = frame["proposal_text"].map(vote_features.proposal_family)
    inventory = document_inventory(db)
    statuses = [source_status(row, inventory) for row in frame.to_dict("records")]
    frame["source_document_available"] = [status["source_document_available"] for status in statuses]
    errors = frame.loc[frame["error"].ne("")]
    error_rows = []
    for index, row in errors.iterrows():
        task = required_facts(row["safe_family"])
        error_rows.append({**{key: row[key] for key in ("meeting_id", "item_no", "company_id", "meeting_date", "company", "proposal_text", "safe_family", "score", "nbim_vote", "error")},
            "threshold": threshold, "predicted_mot": bool(row["predicted_mot"]),
            **{key: value for key, value in statuses[index].items() if key != "source_documents"},
            "source_documents": json.dumps(statuses[index]["source_documents"], ensure_ascii=False),
            "review_status": task["status"], "facts_to_verify": json.dumps(task["facts_to_verify"], ensure_ascii=False),
            "interpretation": task["interpretation"]})
    report = {"experiment": "FIXED_MODEL_ERROR_AND_DATA_DIAGNOSTICS", "model": summary["selected_config"],
              "threshold": threshold, "evaluation_kind": "EXPLORATORY_2024_DEVELOPMENT", "metrics": measured,
              "source": str(source.resolve()), "source_summary_sha256": file_hash(source / "summary.json"),
              "source_predictions_sha256": file_hash(source / "development.csv"), "document_database_sha256": file_hash(db),
              "diagnostics_code_sha256": file_hash(__file__), "family_code_sha256": file_hash(vote_features.__file__),
              "bootstrap": cluster_bootstrap(frame, draws=draws, seed=seed),
              "by_family": {family: {**confusion(part), **coverage(part)} for family, part in frame.groupby("safe_family", sort=True)},
              "documents": {"all": coverage(frame), "errors": coverage(errors), "actual_mot": coverage(frame.loc[frame["nbim_vote"].eq("MOT")]),
                            "false_negatives": coverage(frame.loc[frame["error"].eq("FN")]), "false_positives": coverage(frame.loc[frame["error"].eq("FP")])},
              "required_fact_tasks": {family: required_facts(family) for family in sorted(FACT_TASKS)},
              "caveats": ["The fixed model and threshold are not changed or selected by this report.",
                          "2024 has been used for development; intervals do not establish unseen-test performance.",
                          "Document availability measures indexed meeting/date-matched pre-cutoff documents, not fact coverage, factual correctness or rule violations.",
                          "Required facts are pending review hypotheses; they are not extracted or verified facts.",
                          "Missing scores remain in denominators and cannot count as MOT recommendations."]}
    output.mkdir(parents=True, exist_ok=False)
    pd.DataFrame(error_rows).to_csv(output / "error-review.csv", index=False)
    (output / "diagnostics.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    args = parser.parse_args()
    report = run(args.source, args.output, args.db)
    print(json.dumps({key: report[key] for key in ("model", "threshold", "metrics", "bootstrap", "by_family", "documents")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
