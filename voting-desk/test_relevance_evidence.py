"""Leakage and source-integrity regression tests for dated meeting evidence."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from local_rag import create_index
from rag_corpus import extract_html, chunk_document
import relevance_evidence as evidence


class Embedder:
    @staticmethod
    def vector(text):
        text = text.lower()
        return [1.0 + ("independ" in text), 1.0 + ("compensation" in text), 1.0 + ("audit" in text)]

    def passage_embed(self, texts, batch_size=32):
        return (self.vector(text) for text in texts)

    def query_embed(self, texts, batch_size=32):
        return (self.vector(text) for text in texts)


def make_corpus(directory, meetings=("a",)):
    documents, chunks = [], []
    for meeting in meetings:
        raw = ("<h2>Director information</h2><p>Ada Example is independent and attended all board meetings.</p>"
               "<p>Compensation vesting requires sustained performance over three years.</p>"
               "<p>Audit fees exceed non-audit fees. The audit committee has three independent directors.</p>")
        path = directory / (meeting + ".html")
        path.write_text(raw)
        text, blocks = extract_html(raw)
        doc = {"id": "doc-" + meeting, "meeting_id": meeting, "company_id": "company-" + meeting,
               "company": "Company " + meeting, "meeting_date": "2024-06-10" if meeting == "a" else "2026-06-10",
               "filed": "2024-05-01" if meeting == "a" else "2026-05-01",
               "url": "https://www.sec.gov/Archives/edgar/data/123/" + meeting + ".html",
               "file": str(path), "sha256": sha256(raw.encode()).hexdigest(), "text": text}
        documents.append(doc)
        chunks.extend(chunk_document(doc, blocks, target_words=18, overlap_words=3))
    return {"documents": documents, "chunks": chunks, "skipped": []}


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.path = self.root / "index.sqlite"
        self.corpus = make_corpus(self.root)
        create_index(self.corpus, self.path, embedder=Embedder())
        self.row = {"meeting_id": "a", "company_id": "company-a", "company": "Company a",
                    "meeting_date": "2024-06-10", "item_no": "1", "proposal_text": "Elect Ada Example as director"}

    def retriever(self, path=None):
        obj = evidence.EvidenceRetriever(path or self.path, embedder=Embedder())
        self.addCleanup(obj.close)
        return obj

    def test_actual_quotes_and_provenance(self):
        bundle = self.retriever().retrieve(self.row)
        self.assertTrue(bundle["passages"])
        source = self.corpus["documents"][0]
        for passage in bundle["passages"]:
            self.assertEqual(passage["text"], source["text"][passage["start"]:passage["end"]])
            self.assertEqual(passage["sha256"], source["sha256"])
        self.assertEqual(bundle["rules"], [])
        self.assertIn(evidence.POLICY_GAP, bundle["missing"])
        evidence.validate_evidence(bundle)

    def test_current_labels_rationale_and_category_do_not_change_context(self):
        retriever = self.retriever()
        before = retriever.retrieve(self.row)
        after = retriever.retrieve({**self.row, "nbim_vote": "LEAK", "against_board": "LEAK",
                                    "rationale_text": "SECRET", "proposal_type": "SECRET"})
        self.assertEqual(before, after)
        self.assertNotIn("SECRET", json.dumps(after))

    def test_future_meetings_cannot_change_earlier_ranking(self):
        before = self.retriever().retrieve(self.row)
        path = self.root / "expanded.sqlite"
        create_index(make_corpus(self.root, ("a", "future")), path, embedder=Embedder())
        after = self.retriever(path).retrieve(self.row)
        self.assertEqual(before, after)

    def test_other_company_and_changed_date_are_rejected_even_after_cache(self):
        retriever = self.retriever()
        retriever.retrieve(self.row)
        for update in ({"company_id": "other"}, {"meeting_date": "2024-06-11"}):
            with self.subTest(update=update), self.assertRaises(ValueError):
                retriever.retrieve({**self.row, **update})

    def test_unavailable_filings_have_explicit_missing_evidence(self):
        result = self.retriever().retrieve({**self.row, "meeting_id": "unknown"})
        self.assertEqual(result["passages"], [])
        self.assertEqual(len(result["missing"]), 2)

    def test_source_file_tampering_rejected(self):
        Path(self.corpus["documents"][0]["file"]).write_text("Changed source")
        with self.assertRaisesRegex(ValueError, "bytes changed"):
            self.retriever().retrieve(self.row)

    def test_changed_index_quote_rejected(self):
        with sqlite3.connect(self.path) as con:
            key, raw = con.execute("SELECT id,data FROM chunks LIMIT 1").fetchone()
            data = json.loads(raw)
            data["text"] = "Altered quote"
            con.execute("UPDATE chunks SET data=? WHERE id=?", (json.dumps(data), key))
        with self.assertRaisesRegex(ValueError, "exact source offsets"):
            self.retriever().retrieve(self.row)

    def test_outbound_date_at_five_day_boundary_rejected(self):
        bundle = self.retriever().retrieve(self.row)
        bundle["passages"][0]["filed"] = "2024-06-05"
        with self.assertRaisesRegex(ValueError, "cutoff"):
            evidence.validate_evidence(bundle)

    def test_outcome_fields_and_undated_policy_rejected_outbound(self):
        bundle = self.retriever().retrieve(self.row)
        changed = deepcopy(bundle)
        changed["passages"][0]["nbim_vote"] = "FOR"
        with self.assertRaises(ValueError):
            evidence.validate_evidence(changed)
        changed = deepcopy(bundle)
        changed["rules"] = [{"quote": "Current rules", "source": "rules.json"}]
        with self.assertRaises(ValueError):
            evidence.validate_evidence(changed)

    def test_outbound_exact_quote_revalidated_against_source(self):
        retriever = self.retriever()
        bundle = retriever.retrieve(self.row)
        bundle["passages"][0]["text"] = "x" * len(bundle["passages"][0]["text"])
        with self.assertRaisesRegex(ValueError, "verified source passage"):
            retriever.validate(bundle)

    def test_duplicate_inputs_rejected_and_batch_matches_single(self):
        retriever = self.retriever()
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            retriever.retrieve_many([self.row, self.row])
        bundles = retriever.retrieve_many([self.row])
        self.assertEqual(bundles["a:1"], retriever.retrieve(self.row))
        self.assertEqual(evidence.coverage(bundles)["proposals_with_filings"], 1)

    def test_build_cli_preserves_existing_index(self):
        before = self.path.read_bytes()
        with patch("sys.stderr"), self.assertRaises(SystemExit):
            evidence.main(["--build", "--index", str(self.path)])
        self.assertEqual(before, self.path.read_bytes())

    def test_build_cli_uses_only_2024_corpus(self):
        path = self.root / "new.sqlite"
        info = {"documents": 1, "chunks": 3, "by_year": {"2024": 1}, "skipped": []}
        with patch("rag_corpus.build_corpus", return_value=self.corpus) as build, \
                patch("relevance_evidence.build_evidence_index", return_value=info) as create, patch("builtins.print"):
            evidence.main(["--build", "--index", str(path)])
        build.assert_called_once_with(year="2024")
        create.assert_called_once_with(self.corpus, path, [value for value in evidence.DEFAULT_REUSE if value.is_file()])

    def mark_cache_model(self):
        with sqlite3.connect(self.path) as con:
            info = json.loads(con.execute("SELECT value FROM metadata").fetchone()[0])
            info.update(model=evidence.MODEL, model_assets={"fake.onnx": "verified"})
            con.execute("UPDATE metadata SET value=?", (json.dumps(info),))

    def test_verified_cache_reuse_preserves_sources_and_records_provenance(self):
        self.mark_cache_model()
        source = self.path.read_bytes()
        model = Embedder()
        with patch.object(model, "passage_embed", side_effect=AssertionError("No new embeddings needed")), \
                patch("relevance_evidence.load_model", return_value=model), \
                patch("relevance_evidence.model_fingerprint", return_value={"fake.onnx": "verified"}), patch("builtins.print"):
            info = evidence.build_evidence_index(self.corpus, self.root / "reused.sqlite", [self.path])
        self.assertEqual(info["embedding_reuse"]["reused_chunks"], len(self.corpus["chunks"]))
        self.assertEqual(info["embedding_reuse"]["newly_embedded_chunks"], 0)
        self.assertEqual(info["embedding_reuse"]["source_indexes"][0]["sha256"], sha256(source).hexdigest())
        self.assertEqual(self.path.read_bytes(), source)

    def test_mismatched_model_cache_rejected(self):
        with patch("relevance_evidence.load_model", return_value=Embedder()), \
                patch("relevance_evidence.model_fingerprint", return_value={"different.onnx": "different"}):
            with self.assertRaisesRegex(ValueError, "model assets"):
                evidence.build_evidence_index(self.corpus, self.root / "reused.sqlite", [self.path])

    def test_changed_cached_document_is_recomputed_instead_of_reused(self):
        self.mark_cache_model()
        with sqlite3.connect(self.path) as con:
            key, raw = con.execute("SELECT id,data FROM documents LIMIT 1").fetchone()
            document = json.loads(raw)
            document["text"] = "Different source content"
            con.execute("UPDATE documents SET data=? WHERE id=?", (json.dumps(document), key))
        with patch("relevance_evidence.load_model", return_value=Embedder()), \
                patch("relevance_evidence.model_fingerprint", return_value={"fake.onnx": "verified"}), patch("builtins.print"):
            info = evidence.build_evidence_index(self.corpus, self.root / "recomputed.sqlite", [self.path])
        self.assertEqual(info["embedding_reuse"]["reused_chunks"], 0)
        self.assertEqual(info["embedding_reuse"]["newly_embedded_chunks"], len(self.corpus["chunks"]))


if __name__ == "__main__":
    unittest.main()
