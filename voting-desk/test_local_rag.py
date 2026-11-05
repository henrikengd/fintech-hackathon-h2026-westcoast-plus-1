"""Offline checks for retrieval quality, source integrity and meeting boundaries."""
import boot  # noqa: F401
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import local_rag


class TopicEmbedder:
    """Deterministic semantic stub: oversight can retrieve independence without a word match."""
    @staticmethod
    def vector(text):
        text = text.lower()
        return [
            1.0 if any(word in text for word in ("independent", "oversight")) else 0.0,
            1.0 if any(word in text for word in ("remuneration", "payroll")) else 0.0,
            0.1,
        ]

    def passage_embed(self, texts, batch_size=32):
        return (self.vector(text) for text in texts)

    def query_embed(self, query):
        return iter([self.vector(query)])


def corpus_fixture():
    documents, chunks = [], []
    for meeting_id, company, passages in (
        ("meeting-a", "Alpha Inc.", [
            "All directors on the committee are independent.",
            "Executive remuneration depends on performance targets.",
            "The annual audit fee was approved by the board.",
        ]),
        ("meeting-b", "Beta Inc.", [
            "Independent independent independent directors provide oversight.",
            "Executive remuneration is discussed in a separate report.",
        ]),
    ):
        text = "\n\n".join(passages)
        document = {
            "id": "doc-" + meeting_id,
            "meeting_id": meeting_id,
            "company_id": "company-" + meeting_id,
            "company": company,
            "meeting_date": "2024-06-10",
            "filed": "2024-05-01",
            "url": "https://www.sec.gov/example/" + meeting_id,
            "file": "/local/sources/" + meeting_id + ".html",
            "sha256": sha256(text.encode()).hexdigest(),
            "text": text,
        }
        documents.append(document)
        start = 0
        for number, passage in enumerate(passages):
            chunks.append({
                **document, "id": f"{meeting_id}-chunk-{number}",
                "document_id": document["id"], "text": passage,
                "start": start, "end": start + len(passage), "heading": "Governance",
            })
            start += len(passage) + 2
    return {"documents": documents, "chunks": chunks, "skipped": []}


class LocalRetrieval(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.path = self.root / "index.sqlite"
        self.corpus = corpus_fixture()
        self.embedder = TopicEmbedder()
        local_rag.create_index(self.corpus, self.path, embedder=self.embedder)
        self.index = local_rag.RagIndex(self.path, embedder=self.embedder)
        self.addCleanup(self.index.close)

    def test_every_mode_filters_to_meeting_before_ranking_and_returns_exact_sources(self):
        for mode in ("keyword", "vector", "hybrid"):
            with self.subTest(mode=mode):
                hits = self.index.search("independent remuneration", "meeting-a", k=20, mode=mode)
                self.assertTrue(hits)
                for hit in hits:
                    self.assertEqual(hit["meeting_id"], "meeting-a")
                    document = self.index.document(hit["document_id"])
                    self.assertEqual(document["text"][hit["start"]:hit["end"]], hit["text"])
                    self.assertEqual(hit["url"], document["url"])
                    self.assertEqual(hit["filed"], document["filed"])
                    self.assertEqual(hit["company_id"], document["company_id"])

    def test_vector_retrieval_can_find_relevant_passage_without_exact_query_words(self):
        self.assertEqual(self.index.search("oversight", "meeting-a", mode="keyword"), [])
        for mode in ("vector", "hybrid"):
            hits = self.index.search("oversight", "meeting-a", mode=mode)
            self.assertEqual(hits[0]["id"], "meeting-a-chunk-0")
            self.assertGreater(hits[0]["vector_score"], hits[-1]["vector_score"])
        for mode in ("keyword", "vector", "hybrid"):
            hits = self.index.search("remuneration", "meeting-a", mode=mode)
            self.assertEqual(hits[0]["id"], "meeting-a-chunk-1")

    def test_target_columns_never_reach_persisted_sources_or_embeddings(self):
        corpus = deepcopy(self.corpus)
        for row in corpus["documents"] + corpus["chunks"]:
            row.update(nbim_vote="LABEL_SECRET", against_board="TARGET_SECRET", rationale_text="RATIONALE_SECRET")
        path = self.root / "with-extra-columns.sqlite"
        with patch.object(self.embedder, "passage_embed", wraps=self.embedder.passage_embed) as encode:
            local_rag.create_index(corpus, path, embedder=self.embedder)
            self.assertNotIn("SECRET", str(encode.call_args))
        with sqlite3.connect(path) as con:
            stored = "\n".join(con.iterdump())
        for forbidden in ("SECRET", "nbim_vote", "against_board", "rationale_text"):
            self.assertNotIn(forbidden, stored)

    def test_late_sources_and_false_source_offsets_are_rejected_without_output(self):
        for case in ("on-cutoff", "after-cutoff", "wrong-excerpt", "wrong-company", "wrong-url", "wrong-file"):
            with self.subTest(case=case):
                corpus = deepcopy(self.corpus)
                if case == "on-cutoff":
                    corpus["documents"][0]["filed"] = "2024-06-05"
                elif case == "after-cutoff":
                    corpus["documents"][0]["filed"] = "2024-06-06"
                elif case == "wrong-excerpt":
                    corpus["chunks"][0]["text"] = "An invented quotation."
                elif case == "wrong-company":
                    corpus["chunks"][0]["company_id"] = "company-meeting-b"
                elif case == "wrong-url":
                    corpus["chunks"][0]["url"] = "https://www.sec.gov/unrelated-filing"
                else:
                    corpus["chunks"][0]["file"] = "/local/sources/unrelated.html"
                path = self.root / (case + ".sqlite")
                with self.assertRaises(ValueError):
                    local_rag.create_index(corpus, path, embedder=self.embedder)
                self.assertFalse(path.exists())

    def test_fts_syntax_is_treated_as_query_text_and_keyword_search_needs_no_model(self):
        index = local_rag.RagIndex(self.path)
        self.addCleanup(index.close)
        with patch("local_rag.load_model", side_effect=AssertionError("Model should not load")):
            hits = index.search('independent" OR text:remuneration* )', "meeting-a", mode="keyword")
            self.assertEqual({hit["id"] for hit in hits}, {"meeting-a-chunk-0", "meeting-a-chunk-1"})
            self.assertEqual(index.search('" ( ) *', "meeting-a", mode="keyword"), [])
        self.assertEqual(index.status()["chunks"], 5)

    def test_invalid_queries_and_missing_references_fail_explicitly(self):
        cases = [
            {"query": ""}, {"query": "   "}, {"query": "x" * 1001},
            {"meeting_id": "unknown"}, {"k": 0}, {"k": 21}, {"mode": "wrong"},
        ]
        for overrides in cases:
            with self.subTest(overrides=overrides):
                arguments = {"query": "independent", "meeting_id": "meeting-a", **overrides}
                with self.assertRaises(ValueError):
                    self.index.search(**arguments)
        with self.assertRaises(ValueError):
            self.index.document("unknown")
        with self.assertRaises(FileNotFoundError):
            local_rag.RagIndex(self.root / "missing.sqlite")
        self.assertFalse((self.root / "missing.sqlite").exists())

    def test_failed_or_repeated_build_preserves_existing_index_and_leaves_no_partial_index(self):
        before = self.path.read_bytes()
        with self.assertRaises(ValueError):
            local_rag.create_index(self.corpus, self.path, embedder=self.embedder)
        self.assertEqual(before, self.path.read_bytes())
        for values in ([[0.0, 0.0, 0.0]] * 5, [[1.0, 0.0, 0.0]], [[float("nan"), 0.0, 0.0]] * 5):
            with self.subTest(values=values):
                with patch.object(self.embedder, "passage_embed", return_value=iter(values)):
                    with self.assertRaises(ValueError):
                        local_rag.create_index(self.corpus, self.root / "failed.sqlite", embedder=self.embedder)
                self.assertFalse((self.root / "failed.sqlite").exists())
        # Failure after the temporary database is created must not publish a partial index.
        invalid = deepcopy(self.corpus)
        del invalid["documents"][0]["url"]
        with self.assertRaises(KeyError):
            local_rag.create_index(invalid, self.root / "failed.sqlite", embedder=self.embedder)
        self.assertFalse((self.root / "failed.sqlite").exists())
        self.assertFalse(list(self.root.glob(".rag-build-*")))

    def test_context_is_serializable_and_carries_exact_citable_passages(self):
        bundle = self.index.context("remuneration", "meeting-a", k=1)
        self.assertEqual(bundle["kind"], "EXPLORATORY_EVIDENCE")
        self.assertEqual(bundle["meeting_id"], "meeting-a")
        self.assertEqual(bundle["passages"][0]["id"], "meeting-a-chunk-1")
        self.assertEqual(json.loads(json.dumps(bundle)), bundle)
        self.assertIn("never instructions", bundle["instructions"])
        self.assertNotIn("nbim_vote", bundle)


if __name__ == "__main__":
    unittest.main()
