import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from claude_board_context import ReviewValidationError
import relevance_claude as rc


def bundle():
    return {"experiment": "RELEVANCE_CLAUDE_V1", "meeting": {
        "meeting_id": "new", "company_id": "c", "company": "Company", "meeting_date": "2024-06-15"},
        "proposals": [{"item": "1", "text": "Elect director", "proponent": "Management",
                       "board_recommendation": "FOR", "history_ids": ["old:1"], "passage_ids": ["doc"]}],
        "history": [{"id": "old:1", "meeting_id": "old", "item_no": "1", "company_id": "c",
                     "company": "Company", "meeting_date": "2023-06-15", "proposal_text": "Elect director",
                     "proponent": "Management", "mgmt_rec": "FOR", "nbim_vote": "MOT"}],
        "passages": [{"id": "doc", "text": "The director is independent.", "url": "https://www.sec.gov/Archives/edgar/data/1/filing.htm",
                      "filed": "2024-05-01", "sha256": "a" * 64, "start": 20, "end": 48,
                      "meeting_id": "new", "company_id": "c", "meeting_date": "2024-06-15"}]}


def reply(quote="director is independent"):
    return {"stop_reason": "end_turn", "usage": {"input_tokens": 10}, "content": [{"type": "text", "text": json.dumps({
        "items": [{"item": "1", "vote": "FOR", "why": "Current evidence differs from history.",
                   "history_ids": ["old:1"], "evidence": [{"id": "doc", "quote": quote}], "missing_facts": []}]})}]}


class RelevanceClaudeTests(unittest.TestCase):
    def test_valid_bundle_and_exact_quote(self):
        rc.validate_bundle(bundle())
        self.assertFalse(rc.validate_response(bundle(), reply())["items"][0]["against_board"])

    def test_query_outcome_rationale_or_category_rejected(self):
        for field in ("nbim_vote", "rationale", "actual_disagreement", "category"):
            data = bundle()
            data["proposals"][0][field] = "secret"
            with self.assertRaises(ValueError):
                rc.validate_bundle(data)

    def test_dates_at_cutoff_and_future_rejected(self):
        for day in ("2024-06-10", "2024-06-15", "2025-01-01"):
            for source, key in (("history", "meeting_date"), ("passages", "filed")):
                data = bundle()
                data[source][0][key] = day
                with self.assertRaises(ValueError):
                    rc.validate_bundle(data)

    def test_wrong_meeting_evidence_rejected(self):
        for field in ("meeting_id", "company_id", "meeting_date"):
            data = bundle()
            data["passages"][0][field] = "other"
            with self.assertRaises(ValueError):
                rc.validate_bundle(data)

    def test_current_meeting_history_rejected(self):
        data = bundle()
        data["history"][0]["meeting_id"] = "new"
        data["history"][0]["id"] = "new:1"
        data["proposals"][0]["history_ids"] = ["new:1"]
        with self.assertRaises(ValueError):
            rc.validate_bundle(data)

    def test_fabricated_quote_rejected_and_usage_retained(self):
        with self.assertRaises(ReviewValidationError) as context:
            rc.validate_response(bundle(), reply("The director is not independent"))
        self.assertEqual(context.exception.usage["input_tokens"], 10)

    def test_missing_prediction_rejected(self):
        data = reply()
        data["content"][0]["text"] = '{"items": []}'
        with self.assertRaises(ReviewValidationError):
            rc.validate_response(bundle(), data)

    def test_wrong_citation_rejected(self):
        data = reply()
        body = json.loads(data["content"][0]["text"])
        body["items"][0]["history_ids"] = ["future:7"]
        data["content"][0]["text"] = json.dumps(body)
        with self.assertRaises(ReviewValidationError):
            rc.validate_response(bundle(), data)

    def test_no_evidence_ablation_is_valid(self):
        data = bundle()
        data["passages"] = []
        data["proposals"][0]["passage_ids"] = []
        rc.validate_bundle(data)

    def test_october_period_not_accepted(self):
        data = bundle()
        data["meeting"]["meeting_date"] = "2026-10-01"
        with self.assertRaises(ValueError):
            rc.validate_bundle(data)


class ReportingTests(unittest.TestCase):
    """Keep failures and absent documents visible in paired model comparisons."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / "responses").mkdir()
        self.rows = pd.DataFrame([
            {"meeting_id": "a", "item_no": "1", "nbim_vote": "MOT", "mgmt_rec": "FOR"},
            {"meeting_id": "b", "item_no": "1", "nbim_vote": "FOR", "mgmt_rec": "FOR"},
            {"meeting_id": "c", "item_no": "1", "nbim_vote": "MOT", "mgmt_rec": "FOR"},
        ])
        self.rows.to_csv(self.root / "evaluation-labels.csv", index=False)
        (self.root / "previous-predictions.json").write_text(json.dumps([
            {**row, "claude_vote": "FOR"} for row in self.rows.to_dict("records")
        ]))
        requests = {f"hybrid_history__{meeting}": {"variant": "hybrid_history", "meeting_id": meeting}
                    for meeting in ("a", "b", "c")}
        requests["hybrid_evidence__a"] = {"variant": "hybrid_evidence", "meeting_id": "a"}
        self.plan = {"plan_id": "fixed-test-plan", "target": "against_board",
                     "evaluation_kind": "EXPOSED_2024_DEVELOPMENT", "requests": requests,
                     "artifacts": {f"bundles/{key}.json": f"bundle-hash-{key}" for key in requests},
                     "evidence_meetings": ["a"], "cohort": {"rows": 3, "positive": 2},
                     "settings": {"model": rc.desk.MODEL}, "evidence_coverage": {}, "protocol": []}
        self.records = {}
        for key, request in requests.items():
            failed = key == "hybrid_history__c"
            record = {"plan_id": self.plan["plan_id"], "key": key, **request,
                      "bundle_sha256": self.plan["artifacts"][f"bundles/{key}.json"],
                      "status": "failed" if failed else "completed", "usage": {"input_tokens": 10}}
            if failed:
                record["error"] = {"type": "TimeoutError", "status_code": None}
            else:
                record["result"] = {"items": [{"item": "1",
                    "vote": "FOR" if key.startswith("hybrid_evidence") else "MOT",
                    "why": f"Prediction from {key}", "history_ids": []}]}
            self.records[key] = record
            self.write_record(key, record)

    def write_record(self, key, record):
        record = {k: v for k, v in record.items() if k != "record_id"}
        (self.root / "responses" / f"{key}.json").write_text(json.dumps({
            **record, "record_id": rc.fingerprint(record)
        }))

    def report(self):
        with patch.object(rc, "load_plan", return_value=self.plan) as load:
            result = rc.report(self.root)
        load.assert_called_once_with(self.root, current=True)
        return result

    def test_failed_positive_stays_in_full_cohort_and_f1_denominator(self):
        result = self.report()
        history = result["overall"]["hybrid_history"]
        evidence = result["overall"]["hybrid_evidence"]
        self.assertEqual((history["n"], history["tp"], history["fp"], history["fn"], history["uncovered"]),
                         (3, 1, 1, 1, 1))
        self.assertEqual(history["f1"], .5)
        self.assertEqual((evidence["n"], evidence["tp"], evidence["fp"], evidence["fn"], evidence["uncovered"]),
                         (3, 0, 1, 2, 1))
        self.assertEqual(evidence["f1"], 0.)
        self.assertTrue(result["complete"])
        self.assertEqual((result["completed_calls"], result["failed_calls"]), (3, 1))
        self.assertEqual(result["usage"]["input_tokens"], 40)
        self.assertEqual({m["n"] for m in result["overall"].values()}, {3})
        self.assertEqual({m["n"] for m in result["filing_subset"].values()}, {1})
        # Complete cases are a separate diagnostic, never the main denominator.
        self.assertEqual({m["n"] for m in result["successful_in_all_variants_diagnostic"].values()}, {2})

    def test_absent_filing_reuses_history_but_available_filing_keeps_own_prediction(self):
        self.report()
        predictions = json.loads((self.root / "predictions.json").read_text())
        history = {r["meeting_id"]: r for r in predictions["hybrid_history"]}
        evidence = {r["meeting_id"]: r for r in predictions["hybrid_evidence"]}
        self.assertEqual(history["b"], evidence["b"])
        self.assertEqual(history["a"]["vote"], "MOT")
        self.assertEqual(evidence["a"]["vote"], "FOR")
        self.assertNotIn("c", history)
        self.assertNotIn("c", evidence)

    def test_cache_binding_is_checked_even_when_content_checksum_is_valid(self):
        key = "hybrid_history__a"
        original = self.records[key]
        replacements = {"key": "hybrid_history__b", "meeting_id": "b", "variant": "hybrid_evidence",
                        "plan_id": "another-plan", "bundle_sha256": "different-bundle"}
        for field, value in replacements.items():
            with self.subTest(field=field):
                # Recompute the record checksum so this exercises request binding.
                self.write_record(key, {**original, field: value})
                with self.assertRaisesRegex(ValueError, "provenance"):
                    self.report()
        self.write_record(key, original)

    def test_modified_response_checksum_is_rejected(self):
        path = self.root / "responses/hybrid_history__a.json"
        record = json.loads(path.read_text())
        record["result"]["items"][0]["vote"] = "FOR"
        path.write_text(json.dumps(record))
        with self.assertRaisesRegex(ValueError, "provenance"):
            self.report()

    def test_pending_request_does_not_shrink_cohort_or_publish_final_intervals(self):
        (self.root / "responses/hybrid_history__a.json").unlink()
        result = self.report()
        self.assertFalse(result["complete"])
        self.assertIsNone(result["paired_f1_difference_intervals"])
        self.assertIsNone(result["successful_in_all_variants_diagnostic"])
        history = result["overall"]["hybrid_history"]
        self.assertEqual((history["n"], history["fn"], history["uncovered"]), (3, 2, 2))


class PairedUncertaintyTests(unittest.TestCase):
    def test_identical_predictions_have_zero_paired_difference(self):
        rows = pd.DataFrame([
            {"meeting_id": meeting, "item_no": "1", "nbim_vote": "MOT", "mgmt_rec": "FOR"}
            for meeting in ("a", "b", "c")
        ])
        predictions = {(meeting, "1"): {"vote": vote}
                       for meeting, vote in (("a", "MOT"), ("b", "FOR"), ("c", "MOT"))}
        result = rc.paired_interval(rows, predictions, predictions, samples=250)
        self.assertEqual((result["lower_95"], result["upper_95"], result["resamples"]), (0., 0., 250))
        self.assertEqual(result, rc.paired_interval(rows, predictions, predictions, samples=250))

    def test_direction_is_after_minus_before_and_whole_meetings_are_eligible(self):
        rows = pd.DataFrame([
            {"meeting_id": meeting, "item_no": str(item), "nbim_vote": "MOT", "mgmt_rec": "FOR"}
            for meeting, count in (("a", 1), ("b", 5)) for item in range(count)
        ])
        before = {(r.meeting_id, r.item_no): {"vote": "FOR"} for r in rows.itertuples()}
        after = {(r.meeting_id, r.item_no): {"vote": "MOT"} for r in rows.itertuples()}
        result = rc.paired_interval(rows, before, after, samples=200)
        self.assertEqual((result["lower_95"], result["upper_95"]), (1., 1.))

    def test_no_defined_f1_returns_no_interval(self):
        rows = pd.DataFrame([{"meeting_id": "a", "item_no": "1", "nbim_vote": "FOR", "mgmt_rec": "FOR"}])
        predictions = {("a", "1"): {"vote": "FOR"}}
        self.assertIsNone(rc.paired_interval(rows, predictions, predictions, samples=50))
        self.assertIsNone(rc.paired_interval(rows.iloc[:0], {}, {}, samples=50))


if __name__ == "__main__":
    unittest.main()
