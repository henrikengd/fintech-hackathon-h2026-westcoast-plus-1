"""Fixed-result diagnostics: complete meeting resampling, missingness and source dates."""
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

import numpy as np
import pandas as pd

from vote_diagnostics import (cluster_bootstrap, confusion, coverage, document_inventory,
                              file_hash, required_facts, run, source_status)


def bootstrap_rows():
    # A has a TP and an unanswered MOT; B a FP; C eight TNs. Whole groups must stay together.
    return pd.DataFrame({"company_id": ["a", "a", "b"] + ["c"] * 8,
        "meeting_date": ["2024-01-10"] * 11, "nbim_vote": ["MOT", "MOT"] + ["FOR"] * 9,
        "predicted_mot": [True, False, True] + [False] * 8, "score": [.9, np.nan, .8] + [.1] * 8})


class VoteDiagnosticsTests(unittest.TestCase):
    def test_bootstrap_resamples_complete_clusters_and_retains_missing_negatives(self):
        frame = bootstrap_rows()
        result = cluster_bootstrap(frame, draws=1000, seed=42)
        self.assertEqual(result["clusters"], 3)
        self.assertEqual(result["point"]["rows"], 11)
        self.assertEqual(result["point"]["tp"], 1)
        self.assertEqual(result["point"]["fp"], 1)
        self.assertEqual(result["point"]["fn"], 1)
        self.assertEqual(result["point"]["tn"], 8)
        self.assertEqual(result["point"]["missing_score_share"], 1 / 11)
        # Independently expand sampled cluster multiplicities; incorrect row-wise resampling differs.
        chosen = np.random.default_rng(42).integers(0, 3, size=(1000, 3))
        a, b, c = [(chosen == group).sum(axis=1) for group in range(3)]
        row_counts = 2 * a + b + 8 * c
        self.assertEqual(result["row_count_range"], [int(row_counts.min()), int(row_counts.max())])
        precision = a[a + b > 0] / (a + b)[a + b > 0]
        self.assertEqual(result["precision"]["undefined_draws"], int((a + b == 0).sum()))
        self.assertEqual(result["precision"]["lower"], float(np.quantile(precision, .025)))
        self.assertEqual(result["precision"]["upper"], float(np.quantile(precision, .975)))
        self.assertEqual(result["recall"]["lower"], .5)
        self.assertEqual(result["recall"]["upper"], .5)
        self.assertEqual(result, cluster_bootstrap(frame, draws=1000, seed=42))

    def test_missing_group_keys_are_not_silently_dropped_and_empty_denominators_are_explicit(self):
        frame = bootstrap_rows().iloc[[1]].copy()
        frame["company_id"] = np.nan
        result = cluster_bootstrap(frame, draws=10)
        self.assertEqual(result["clusters"], 1)
        self.assertEqual(result["precision"]["valid_draws"], 0)
        self.assertIsNone(result["precision"]["lower"])
        self.assertEqual(result["recall"]["upper"], 0)
        self.assertEqual(result["point"]["missing_score_share"], 1)

    def test_family_review_tasks_are_pending_hypotheses_and_cover_required_facts(self):
        expectations = {"director": ["independence", "CEO", "committee", "attendance", "outside board"],
                        "pay": ["vesting", "dilution", "performance"], "capital": ["price", "pre-emption", "duration"],
                        "shareholder": ["full shareholder proposal", "board response"]}
        for family, terms in expectations.items():
            task = required_facts(family)
            self.assertEqual(task["status"], "pending_fact_review")
            for term in terms:
                self.assertIn(term.lower(), " ".join(task["facts_to_verify"]).lower())
            self.assertIn("no rule violation", task["interpretation"])
        self.assertEqual(required_facts("unrecognized")["facts_to_verify"], required_facts("other")["facts_to_verify"])

    def test_source_cutoff_is_strict_and_metadata_must_match(self):
        row = {"meeting_id": "m", "company_id": "c", "meeting_date": "2024-01-10"}
        base = {"document_id": "doc", "company_id": "c", "meeting_date": "2024-01-10", "url": "https://example.com/source", "filed": "2024-01-04"}
        result = source_status(row, {"m": [base, {**base, "filed": "2024-01-05"}, {**base, "filed": None}, {**base, "company_id": "other"}]})
        self.assertTrue(result["source_document_available"])
        self.assertEqual(result["eligible_document_count"], 1)
        self.assertEqual(result["decision_cutoff_exclusive"], "2024-01-05")
        self.assertEqual(result["source_documents"][1]["exclusion_reason"], "filed_at_or_after_exclusive_cutoff")
        self.assertFalse(source_status(row, {})["source_document_available"])

    def test_document_coverage_has_explicit_missing_rate(self):
        result = coverage(pd.DataFrame({"source_document_available": [True, False, False]}))
        self.assertEqual(result["document_coverage"], 1 / 3)
        self.assertEqual(result["without_eligible_documents"], 2)

    def test_report_preserves_fixed_source_and_errors_with_safe_families(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source, output, db = root / "experiment", root / "diagnostics", root / "documents.sqlite"
            source.mkdir()
            frame = pd.DataFrame([
                {"meeting_id": "m", "item_no": "1", "company_id": "c", "company": "Company", "meeting_date": "2024-01-10",
                 "proposal_text": "Elect Ada Example as Director", "nbim_vote": "MOT", "score": .1, "threshold": .5, "family": "UNTRUSTED"},
                {"meeting_id": "m", "item_no": "2", "company_id": "c", "company": "Company", "meeting_date": "2024-01-10",
                 "proposal_text": "Approve Remuneration", "nbim_vote": "FOR", "score": .9, "threshold": .5, "family": "UNTRUSTED"}])
            frame.to_csv(source / "development.csv", index=False)
            summary = {"selected_config": {"name": "fixture"}, "selected_threshold": .5,
                       "development_selected": {"tp": 0, "fp": 1, "fn": 1, "tn": 0},
                       "artifacts": {"development.csv": file_hash(source / "development.csv")}}
            (source / "summary.json").write_text(json.dumps(summary))
            with sqlite3.connect(db) as connection:
                connection.execute("CREATE TABLE documents (id TEXT, meeting_id TEXT, data TEXT)")
                document = {"company_id": "c", "meeting_date": "2024-01-10", "filed": "2024-01-04", "url": "https://example.com/meeting", "text": "DO_NOT_EXPORT"}
                connection.execute("INSERT INTO documents VALUES (?,?,?)", ("doc", "m", json.dumps(document)))
            before = {str(path): file_hash(path) for path in (db, source / "development.csv", source / "summary.json")}
            result = run(source, output, db, draws=20)
            self.assertEqual(result["metrics"]["fn"], 1)
            self.assertEqual(result["documents"]["errors"]["document_coverage"], 1)
            errors = pd.read_csv(output / "error-review.csv")
            self.assertEqual(set(errors.safe_family), {"director", "pay"})
            self.assertEqual(len(errors), 2)
            self.assertNotIn("DO_NOT_EXPORT", (output / "error-review.csv").read_text())
            self.assertEqual(before, {path: file_hash(path) for path in before})
            with self.assertRaises(FileExistsError):
                run(source, output, db)
            self.assertEqual(document_inventory(db)["m"][0]["filed"], "2024-01-04")


if __name__ == "__main__":
    unittest.main()
