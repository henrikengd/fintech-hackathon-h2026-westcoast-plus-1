"""Offline regression checks for fair, source-checked retrieval comparisons."""
from copy import deepcopy
import csv
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import local_rag
import rag_retrieval_eval as evaluation
from test_local_rag import TopicEmbedder, corpus_fixture


def write_partition(path, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["meeting_id", "company_id", "meeting_date"])
        writer.writeheader()
        writer.writerows({key: row[key] for key in writer.fieldnames} for row in rows)


class RankingTests(unittest.TestCase):
    def test_alternation_keeps_original_ranks_deduplicates_and_exhausts_one_list(self):
        hits = lambda names: [{"id": name} for name in names]
        result = evaluation.alternating(hits(["a", "b", "c", "d", "e"]), hits(["a", "x", "b"]), k=5)
        self.assertEqual([h["id"] for h in result], ["a", "b", "x", "c", "d"])
        self.assertEqual(evaluation.alternating([], hits(["a", "b"])), hits(["a", "b"]))

    def test_stopwords_change_only_experimental_keyword_branch(self):
        query = "What is the director independence of First Horizon?"
        calls = []

        class Retriever:
            def search(self, text, meeting_id, k, mode):
                calls.append((text, meeting_id, k, mode))
                return []

        result = evaluation.retrieve(Retriever(), query, "m1")
        self.assertEqual(set(result), set(evaluation.METHODS))
        self.assertEqual(calls, [
            (query, "m1", 20, "vector"),
            ("director independence First Horizon", "m1", 20, "keyword"),
            (query, "m1", 5, "keyword"),
            (query, "m1", 5, "hybrid"),
        ])


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.db = self.root / "index.sqlite"
        corpus = corpus_fixture()
        embedder = TopicEmbedder()
        local_rag.create_index(corpus, self.db, embedder=embedder)
        self.index = local_rag.RagIndex(self.db, embedder=embedder)
        self.addCleanup(self.index.close)
        self.train, self.test = self.root / "train.csv", self.root / "test.csv"
        write_partition(self.train, corpus["documents"])
        write_partition(self.test, [])
        patched = patch.multiple(evaluation, TRAIN=self.train, TEST=self.test)
        patched.start()
        self.addCleanup(patched.stop)
        self.cases = {"schema_version": 1, "purpose": "Development anchors", "cases": [
            {"id": "independence", "meeting_id": "meeting-a", "question": "independent directors",
             "expected_quote": "All directors on the committee are independent.",
             "source_document_id": "doc-meeting-a", "queries": ["oversight", "independent committee"]},
            {"id": "cross-chunk", "meeting_id": "meeting-a", "question": "remuneration",
             "expected_quote": "independent.\n\nExecutive remuneration", "source_document_id": "doc-meeting-a",
             "queries": ["payroll"]},
        ]}

    def test_source_checks_reject_changed_quote_identity_or_citation(self):
        hit = self.index.search("independent", "meeting-a", mode="keyword")[0]
        self.assertTrue(evaluation.source_check(self.index, hit, "meeting-a")["valid"])
        for overrides in ({"text": "fabricated quote"}, {"document_id": "unknown"},
                          {"meeting_id": "meeting-b"}, {"url": "https://wrong.example"}):
            with self.subTest(overrides=overrides):
                self.assertFalse(evaluation.source_check(self.index, {**hit, **overrides}, "meeting-a")["valid"])

    def test_hit_rate_mrr_missing_anchor_and_variants_have_honest_denominators(self):
        result = evaluation.evaluate(self.index, self.cases)
        for method in evaluation.METHODS:
            metric = result["primary_questions"]["summary"][method]
            self.assertEqual(metric["queries"], 2)
            self.assertEqual(metric["anchor_hits_at_5"], 1)
            self.assertEqual(metric["anchor_hit_at_5"], .5)
            self.assertEqual(metric["mrr_at_5"], .5)
            self.assertEqual(metric["source_quote_validity"], 1)
            self.assertEqual(result["sensitivity_query_variants"]["summary"][method]["queries"], 3)
        checks = result["anchor_checks"]
        self.assertTrue(all(c["source_exact_quote_valid"] for c in checks))
        self.assertTrue(checks[0]["anchor_contained_in_any_chunk"])
        self.assertFalse(checks[1]["anchor_contained_in_any_chunk"])
        self.assertIn("not general retrieval recall", result["caveat"])

    def test_case_identity_is_stable_and_changes_with_annotations(self):
        first = evaluation.evaluate(self.index, self.cases, include_variants=False)
        second = evaluation.evaluate(self.index, self.cases, include_variants=False)
        self.assertEqual(first["data_id"], second["data_id"])
        self.assertEqual(first["config_id"], second["config_id"])
        self.assertEqual(first["primary_questions"], second["primary_questions"])
        changed = deepcopy(self.cases)
        changed["cases"][0]["question"] = "independent committee"
        self.assertNotEqual(first["data_id"], evaluation.evaluate(self.index, changed)["data_id"])
        identity = first["source_dataset_identity"]
        self.assertEqual(identity["index_sha256"], evaluation.file_hash(self.db))
        self.assertEqual(len(identity["all_index_source_hashes"]), 2)

    def test_invalid_anchor_is_rejected_before_any_search(self):
        changed = deepcopy(self.cases)
        changed["cases"][0]["expected_quote"] = "This quotation does not exist."
        with patch.object(self.index, "search", side_effect=AssertionError("No search should start")):
            with self.assertRaisesRegex(ValueError, "absent from source"):
                evaluation.evaluate(self.index, changed)

    def test_reserved_company_date_is_rejected_even_under_different_meeting_id(self):
        write_partition(self.test, [{"meeting_id": "another-meeting", "company_id": "company-meeting-a", "meeting_date": "2024-06-10"}])
        with self.assertRaisesRegex(ValueError, "reserved"):
            evaluation.evaluate(self.index, self.cases)

    def test_cases_validate_unique_ids_and_reports_never_overwrite(self):
        path = self.root / "cases.json"
        path.write_text(json.dumps(self.cases))
        self.assertEqual(evaluation.load_cases(path), self.cases)
        changed = deepcopy(self.cases)
        changed["cases"][1]["id"] = changed["cases"][0]["id"]
        path.write_text(json.dumps(changed))
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            evaluation.load_cases(path)
        result = evaluation.evaluate(self.index, self.cases, include_variants=False)
        report = self.root / "report.json"
        evaluation.save_report(report, result)
        before = report.read_bytes()
        with self.assertRaises(FileExistsError):
            evaluation.save_report(report, {"overwrite": True})
        self.assertEqual(before, report.read_bytes())
        self.assertFalse(list(self.root.glob("tmp*")))


if __name__ == "__main__":
    unittest.main()
