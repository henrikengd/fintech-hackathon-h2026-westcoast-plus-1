"""Offline checks for evaluation boundaries, honest denominators and immutable caches."""
from contextlib import ExitStack
import csv
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import rag_eval


def ballot(meeting, item, gold, board="FOR", year="2024", company=None):
    return {"meeting_id": meeting, "item_no": item, "nbim_vote": gold, "mgmt_rec": board,
            "meeting_date": f"{year}-05-01", "company_id": company or meeting,
            "company": "Example " + meeting, "proposal_text": "Proposal " + item}


def write_csv(path, rows):
    fields = list(rows[0]) if rows else list(ballot("", "", ""))
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


class ScoringTests(unittest.TestCase):
    def test_literal_mot_and_missing_predictions(self):
        rows = [ballot("a", "1", "MOT", "MOT"), ballot("a", "2", "FOR", "MOT"),
                ballot("b", "1", "MOT"), ballot("b", "2", "")]
        result = rag_eval.score_votes(rows, {("a", "1"): "MOT", ("a", "2"): "MOT", ("b", "2"): "MOT"})
        self.assertEqual((result["tp"], result["fp"], result["fn"]), (1, 1, 1))
        self.assertEqual(result["known_votes"], 3)
        self.assertEqual(result["unknown_labels_excluded"], 1)
        self.assertEqual(result["precision"], .5)
        self.assertEqual(result["recall"], .5)
        self.assertAlmostEqual(result["recommendation_coverage"], 2 / 3)

    def test_no_mot_predictions_precision_is_undefined(self):
        result = rag_eval.score_votes([ballot("a", "1", "MOT")], {})
        self.assertIsNone(result["precision"])
        self.assertEqual(result["recall"], 0)
        self.assertEqual(result["f1"], 0)
        self.assertEqual(result["manual_review"], 1)

    def test_quote_and_handoff_metrics_are_separate(self):
        rows = [ballot("a", "1", "FOR"), ballot("a", "2", "MOT")]
        result = rag_eval.score_votes(rows, {("a", "1"): {
            "vote": "MOT", "rule_quote_verified": True,
            "evidence": [{"quote_verified": True}, {"quote_verified": False}],
            "requires_manual_review": True}})
        self.assertEqual(result["precision"], 0)
        self.assertEqual(result["verified_rule_quote_coverage"], .5)
        self.assertEqual(result["verified_evidence_coverage"], 0)
        self.assertEqual(result["manual_review"], 2)

    def test_rejected_response_has_zero_accepted_citation_coverage(self):
        predictions = rag_eval.prediction_map([{
            "meeting_id": "a", "status": "failed", "bundle": {"proposals": [{"item": "1"}]}}])
        result = rag_eval.score_votes([ballot("a", "1", "MOT")], predictions)
        self.assertEqual(result["fn"], 1)
        self.assertEqual(result["verified_rule_quote_coverage"], 0)
        self.assertEqual(result["verified_evidence_coverage"], 0)
        self.assertEqual(result["manual_review_share"], 1)


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source, self.train, self.test = (self.root / name for name in ("source.csv", "train.csv", "test.csv"))
        self.db = self.root / "index.sqlite"
        self.db.write_bytes(b"fixed index identity")
        self.rows = [ballot("a", "1", "MOT"), ballot("a", "2", "FOR"),
                     ballot("b", "1", "MOT"), ballot("b", "2", "")]
        for path in (self.source, self.train):
            write_csv(path, self.rows)
        write_csv(self.test, [ballot("reserved", "1", "MOT", year="2025")])
        self.output = self.root / "evaluation"
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.multiple(rag_eval, VOTES=self.source, TRAIN=self.train, TEST=self.test))
        self.index = self.stack.enter_context(patch.object(rag_eval, "RagIndex"))
        self.index.return_value.meetings.side_effect = lambda: [
            {"meeting_id": "a", "meeting_date": "2024-05-01", "company": "Example a"},
            {"meeting_id": "b", "meeting_date": "2024-05-01", "company": "Example b"}]
        self.stack.enter_context(patch.object(rag_eval, "baseline_predictions", side_effect=lambda rows: {
            "follow_board": {rag_eval.key(row): row["mgmt_rec"] for row in rows}}))

    def prepare(self, mid, **kwargs):
        return {"meeting": {"meeting_id": mid}, "query_mode": kwargs["mode"],
                "proposals": [{"item": row["item_no"]} for row in self.rows if row["meeting_id"] == mid],
                "passages": [{"text": "Fixed public source"}]}

    @staticmethod
    def generate(bundle):
        return {"items": [{"item": p["item"], "vote": "MOT", "rule_quote_verified": True,
                           "evidence": [{"quote_verified": True}], "requires_manual_review": False}
                          for p in bundle["proposals"]], "usage": {"input_tokens": 100, "output_tokens": 20}}

    def model_mocks(self):
        self.stack.enter_context(patch.dict(os.environ, {"ANTHROPIC_API_KEY": "fake-test-key"}))
        self.stack.enter_context(patch.object(rag_eval.rag_review, "prepare_bundle", side_effect=self.prepare))
        return self.stack.enter_context(patch.object(rag_eval.rag_review, "generate_review", side_effect=self.generate))

    def test_allowed_cohort_has_stable_identity(self):
        data = rag_eval.load_evaluation(self.db)
        self.assertEqual(len(data["rows"]), 4)
        self.assertEqual(data["data_id"], rag_eval.load_evaluation(self.db)["data_id"])

    def test_rejects_any_reserved_meeting_or_missing_training_item(self):
        write_csv(self.test, [self.rows[0]])
        with self.assertRaisesRegex(ValueError, "reserved"):
            rag_eval.load_evaluation(self.db)
        write_csv(self.test, [])
        write_csv(self.train, self.rows[:-1])
        with self.assertRaisesRegex(ValueError, "reserved"):
            rag_eval.load_evaluation(self.db)

    def test_rejects_same_company_date_under_another_meeting_id(self):
        write_csv(self.test, [ballot("other-id", "1", "FOR", company="a")])
        with self.assertRaisesRegex(ValueError, "company/date"):
            rag_eval.load_evaluation(self.db)

    def test_rejects_later_year_without_using_its_labels(self):
        changed = [{**row, "meeting_date": "2025-05-01"} for row in self.rows]
        write_csv(self.source, changed)
        write_csv(self.train, changed)
        with self.assertRaisesRegex(ValueError, "2024"):
            rag_eval.load_evaluation(self.db)

    def test_missing_key_never_prepares_or_generates(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": " "}), patch.object(rag_eval.rag_review, "prepare_bundle") as prepare:
            with self.assertRaisesRegex(ValueError, "API_KEY is missing"):
                rag_eval.run("keyword", self.db, self.output)
            prepare.assert_not_called()

    def test_cache_reused_and_changed_prompt_creates_new_immutable_record(self):
        generate = self.model_mocks()
        rag_eval.run("keyword", self.db, self.output, limit=1)
        original = next((self.output / "cache").rglob("*.json"))
        contents = original.read_bytes()
        rag_eval.run("keyword", self.db, self.output, limit=1)
        self.assertEqual(generate.call_count, 1)
        with patch.object(rag_eval.rag_review, "SYSTEM", "changed prompt"):
            rag_eval.run("keyword", self.db, self.output, limit=1)
        self.assertEqual(generate.call_count, 2)
        self.assertEqual(len(list((self.output / "cache").rglob("*.json"))), 2)
        self.assertEqual(original.read_bytes(), contents)

    def test_failed_meeting_kept_in_main_scores_but_paired_subset_explicit(self):
        generate = self.model_mocks()
        rag_eval.run("keyword", self.db, self.output)

        def sometimes_fails(bundle):
            if bundle["meeting"]["meeting_id"] == "b":
                raise RuntimeError("secret credential must not be logged")
            return self.generate(bundle)

        generate.side_effect = sometimes_fails
        result = rag_eval.run("hybrid", self.db, self.output)
        hybrid = next(r for r in result["runs"] if r["mode"] == "hybrid")
        self.assertEqual((hybrid["completed_meetings"], hybrid["failed_meetings"]), (1, 1))
        self.assertEqual(hybrid["metrics"]["known_votes"], 3)
        self.assertEqual(hybrid["metrics"]["fn"], 1)
        self.assertEqual(result["paired_completed"][0]["common_completed_meetings"], 1)
        self.assertEqual(result["paired_completed"][0]["left_metrics"]["known_votes"], 2)
        for path in self.output.rglob("*.json"):
            self.assertNotIn("secret credential", path.read_text())
        before = generate.call_count
        self.assertEqual(rag_eval.report(self.db, self.output), result)
        self.assertEqual(generate.call_count, before)

    def test_dataset_change_cannot_reuse_output(self):
        data = rag_eval.load_evaluation(self.db)
        rag_eval.bind_output(self.output, data)
        self.db.write_bytes(b"new index identity")
        with self.assertRaisesRegex(ValueError, "another dataset"):
            rag_eval.bind_output(self.output, rag_eval.load_evaluation(self.db))

    def test_meeting_strategy_keeps_generation_identity_and_compares_same_mode(self):
        generate = self.model_mocks()
        rag_eval.run("hybrid", self.db, self.output, limit=1)

        def enriched(mid, **kwargs):
            return {**self.prepare(mid, **kwargs), "shared_context": "Extra meeting-wide source facts"}

        module = SimpleNamespace(prepare_bundle=enriched)
        original_hash = rag_eval.file_hash
        version = ["enrichment-v1"]
        with patch.dict(sys.modules, {"rag_review_enriched": module}), patch.object(
            rag_eval, "file_hash", side_effect=lambda path: version[0] if Path(path).name == "rag_review_enriched.py" else original_hash(path)
        ):
            result = rag_eval.run("hybrid", self.db, self.output, limit=1, strategy="meeting")
            self.assertEqual({r["strategy"] for r in result["runs"]}, {"proposal", "meeting"})
            self.assertEqual(len({r["generation_id"] for r in result["runs"]}), 1)
            self.assertEqual(len(result["paired_completed"]), 1)
            pair = result["paired_completed"][0]
            self.assertEqual((pair["left"], pair["right"]), ("hybrid", "hybrid"))
            self.assertEqual({pair["left_strategy"], pair["right_strategy"]}, {"proposal", "meeting"})
            self.assertEqual(pair["common_completed_meetings"], 1)
            rag_eval.run("hybrid", self.db, self.output, limit=1, strategy="meeting")
            self.assertEqual(generate.call_count, 2)
            version[0] = "enrichment-v2"
            changed = rag_eval.run("hybrid", self.db, self.output, limit=1, strategy="meeting")
            self.assertEqual(generate.call_count, 3)
            self.assertEqual(len(changed["runs"]), 3)
            self.assertEqual(len({r["generation_id"] for r in changed["runs"]}), 1)

    def test_legacy_proposal_cache_reused_and_combined_with_new_records(self):
        generate = self.model_mocks()
        data = rag_eval.load_evaluation(self.db)
        rag_eval.bind_output(self.output, data)
        generation = rag_eval.generation_settings()
        generation_id = rag_eval.fingerprint(generation)[:16]
        config_id = rag_eval.fingerprint({"generation_id": generation_id, "mode": "hybrid"})[:16]
        bundle = self.prepare("a", mode="hybrid")
        cache_key = rag_eval.fingerprint({"data_id": data["data_id"], "bundle": bundle, "settings": generation})
        old_path = self.output / "cache" / "hybrid" / config_id / "a" / f"{cache_key}.json"
        old_record = {"cache_key": cache_key, "data_id": data["data_id"], "mode": "hybrid",
                      "config_id": config_id, "generation_id": generation_id, "settings": generation,
                      "meeting_id": "a", "created_at": "2026-11-05T00:00:00Z", "bundle": bundle,
                      "status": "completed", "result": self.generate(bundle), "elapsed_seconds": 1}
        rag_eval.immutable_json(old_path, old_record)
        original = old_path.read_bytes()
        result = rag_eval.run("hybrid", self.db, self.output)
        self.assertEqual(generate.call_count, 1)
        self.assertEqual(old_path.read_bytes(), original)
        self.assertEqual(len(result["runs"]), 1)
        self.assertEqual(result["runs"][0]["strategy"], "proposal")
        self.assertEqual(result["runs"][0]["completed_meetings"], 2)

    def test_immutable_json_never_overwrites_and_leaves_no_partial_file(self):
        path = self.root / "cache.json"
        rag_eval.immutable_json(path, {"first": True})
        with self.assertRaises(FileExistsError):
            rag_eval.immutable_json(path, {"first": False})
        self.assertEqual(json.loads(path.read_text()), {"first": True})
        self.assertEqual(len(list(self.root.glob("tmp*"))), 0)


if __name__ == "__main__":
    unittest.main()
