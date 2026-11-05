import unittest
from unittest.mock import patch

import rag_review_enriched as enriched


class SharedEvidence(unittest.TestCase):
    def test_topic_questions_do_not_depend_on_votes_or_company(self):
        proposals = [{"text": "Elect Director Jane Doe"},
                     {"text": "Advisory Vote on Executive Compensation"},
                     {"text": "Ratify Auditors"}]
        self.assertEqual(enriched.shared_queries(proposals), list(
            enriched.BOARD_QUERIES + enriched.PAY_QUERIES + enriched.AUDITOR_QUERIES))
        self.assertEqual(enriched.shared_queries([{"text": "Approve routine minutes"}]), [])

    def test_shared_search_is_scoped_deduplicated_and_leaves_original_inputs(self):
        class Index:
            def search(self, query, meeting_id, k, mode):
                self.args.append((meeting_id, k, mode))
                return [dict(id="p1", document_id="d", text="evidence", url="https://example.test",
                             filed="2024-01-01", start=0, end=8, heading="Board",
                             meeting_id="m", company_id="c", meeting_date="2024-03-01")]
        index = Index()
        index.args = []
        original = dict(meeting={"meeting_id": "m", "company_id": "c", "meeting_date": "2024-03-01"},
                        proposals=[{"text": "Elect Director Jane Doe"}], passages=[], rules=[{"id": "rule"}])
        with patch.object(enriched.rag_review, "prepare_bundle", return_value=original):
            result = enriched.prepare_bundle("m", mode="keyword", index=index)
        self.assertEqual(index.args, [("m", 3, "keyword")] * len(enriched.BOARD_QUERIES))
        self.assertEqual(len(result["passages"]), 1)
        self.assertEqual(result["rules"], [{"id": "rule"}])
        self.assertEqual(result["query_strategy"], "meeting")
        self.assertEqual(len(result["shared_searches"]), len(enriched.BOARD_QUERIES))

    def test_cross_meeting_shared_evidence_is_rejected(self):
        class Index:
            def search(self, *args, **kwargs):
                return [{"meeting_id": "WRONG"}]
        bundle = dict(meeting={"meeting_id": "m", "company_id": "c", "meeting_date": "2024-03-01"},
                      proposals=[{"text": "Elect Director"}], passages=[])
        with patch.object(enriched.rag_review, "prepare_bundle", return_value=bundle):
            with self.assertRaisesRegex(ValueError, "another meeting"):
                enriched.prepare_bundle("m", index=Index())


if __name__ == "__main__":
    unittest.main()
