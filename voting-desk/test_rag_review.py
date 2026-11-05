"""No-network checks for the optional source-backed Claude experiment."""
import boot  # noqa: F401
import csv
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import rag_review


class StubIndex:
    def __init__(self):
        self.calls = []

    def search(self, query, meeting_id, k, mode):
        self.calls.append((query, meeting_id, k, mode))
        return [{"id": "chunk-a", "document_id": "doc-a", "meeting_id": "m1", "company_id": "c1",
                 "meeting_date": "2024-06-20", "text": "Ada Smith is an independent director.",
                 "url": "https://www.sec.gov/example", "filed": "2024-05-10", "start": 0, "end": 42, "heading": "Board"}]


class RagReview(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / "votes.csv"
        self.row = dict(zip(rag_review.BALLOT_FIELDS, ("m1", "1", "Elect Director Ada Smith", "Management", "FOR", "c1", "Example Inc.", "US", "DM", "2024-06-20")))
        self.row.update(nbim_vote="TARGET_SECRET", rationale_text="RATIONALE_SECRET", against_board="TARGET_SECRET")
        self.write()
        self.index = StubIndex()

    def write(self):
        with self.path.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(self.row))
            writer.writeheader()
            writer.writerow(self.row)

    def bundle(self):
        return rag_review.prepare_bundle("m1", votes_csv=self.path, index=self.index)

    def draft(self, bundle):
        rule = bundle["rules"][0]
        return {"item": "1", "vote": "FOR", "rule_id": rule["id"], "rule_quote": rule["quote"],
                "why": "Source states independence.", "missing_facts": [],
                "evidence": [{"chunk_id": "chunk-a", "quote": "Ada Smith is an independent director."}]}

    def test_preparation_excludes_targets_and_uses_per_proposal_fact_query(self):
        with patch.object(rag_review.desk, "client", side_effect=AssertionError("No paid call")):
            bundle = self.bundle()
        self.assertNotIn("SECRET", json.dumps(bundle))
        self.assertEqual(bundle["proposals"][0]["chunk_ids"], ["chunk-a"])
        self.assertIn("independence", self.index.calls[0][0])
        self.assertEqual(self.index.calls[0][1:], ("m1", 3, "hybrid"))
        self.assertFalse(bundle["model_evaluated"])
        self.row["nbim_vote"], self.row["rationale_text"] = "OTHER", "OTHER"
        self.write()
        self.assertEqual(bundle, self.bundle())

    def test_evidence_from_another_meeting_is_rejected(self):
        self.index.search = Mock(return_value=[{**self.index.search("x", "m1", 3, "hybrid")[0], "meeting_id": "other"}])
        with self.assertRaises(ValueError):
            self.bundle()

    def test_missing_quotes_unknown_chunks_and_missing_facts_require_manual_review(self):
        bundle = self.bundle()
        draft = self.draft(bundle)
        self.assertFalse(rag_review.validate_drafts(bundle, [draft])[0]["requires_manual_review"])
        for evidence in ([], [{"chunk_id": "missing", "quote": "Ada Smith"}], [{"chunk_id": "chunk-a", "quote": "non-independent"}]):
            result = rag_review.validate_drafts(bundle, [{**draft, "evidence": evidence}])[0]
            self.assertTrue(result["requires_manual_review"])
        missing = rag_review.validate_drafts(bundle, [{**draft, "missing_facts": ["Other board seats"]}])[0]
        self.assertTrue(missing["requires_manual_review"])
        no_rule = rag_review.validate_drafts(bundle, [{**draft, "rule_id": "unavailable", "rule_quote": "Made up"}])[0]
        self.assertTrue(no_rule["requires_manual_review"])

    def test_missing_or_duplicate_proposals_are_rejected(self):
        bundle = self.bundle()
        for drafts in ([], [self.draft(bundle), self.draft(bundle)]):
            with self.assertRaises(ValueError):
                rag_review.validate_drafts(bundle, drafts)

    def test_generate_is_one_mocked_call_and_reports_usage_and_citation_limits(self):
        bundle = self.bundle()
        payload = {"stop_reason": "end_turn", "content": [{"type": "text", "text": json.dumps({"items": [self.draft(bundle)]})}],
                   "usage": {"input_tokens": 123, "output_tokens": 45}}
        client = SimpleNamespace(messages=SimpleNamespace(create=Mock(return_value=SimpleNamespace(model_dump=lambda: payload))))
        result = rag_review.generate_review(bundle, client)
        client.messages.create.assert_called_once()
        self.assertEqual(result["usage"], payload["usage"])
        self.assertTrue(result["requires_human_signoff"])
        self.assertFalse(result["model_evaluated"])
        self.assertTrue(result["items"][0]["evidence"][0]["quote_verified"])
        self.assertIn("does not establish logical support", result["citation_check"])
        payload["stop_reason"] = "max_tokens"
        with self.assertRaises(ValueError):
            rag_review.generate_review(bundle, client)

    def test_cli_without_generate_only_prepares_evidence(self):
        bundle = self.bundle()
        with patch.object(rag_review, "prepare_bundle", return_value=bundle), patch.object(rag_review, "generate_review") as generate, patch("sys.stdout", new_callable=io.StringIO) as output:
            rag_review.main(["--meeting", "m1"])
        generate.assert_not_called()
        self.assertEqual(json.loads(output.getvalue()), bundle)


if __name__ == "__main__":
    unittest.main()
