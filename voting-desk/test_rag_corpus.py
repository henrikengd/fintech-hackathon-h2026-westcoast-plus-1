"""Integrity checks for source extraction and local RAG corpus boundaries."""
import csv
from pathlib import Path
import tempfile
import unittest

import rag_corpus


class ExtractedSources(unittest.TestCase):
    def test_visible_paragraphs_tables_and_headings_keep_source_offsets(self):
        raw = """<html><head><title>Hidden title</title></head><body>
        <h2>Board independence</h2><p>Directors are <b>independent</b> &amp; experienced.</p>
        <table><tr><th>Name</th><th>Attendance</th></tr>
        <tr><td><p>Ada Smith</p></td><td>95%</td></tr></table>
        <script>secret_script</script><style>secret_style</style>
        <div style="display: none"><p>secret_hidden</p></div>
        <ix:hidden><ix:nonNumeric>secret_xbrl</ix:nonNumeric></ix:hidden>
        <span aria-hidden="true">secret_aria</span><span hidden>secret_attribute</span>
        <p>Visible final paragraph.</p></body></html>"""
        text, blocks = rag_corpus.extract_html(raw)
        self.assertIn("Directors are independent & experienced.", text)
        self.assertIn("Name | Attendance", text)
        self.assertIn("Ada Smith | 95%", text)
        self.assertNotIn("secret", text)
        self.assertNotIn("Hidden title", text)
        self.assertIn("Visible final paragraph.", text)
        for block in blocks:
            self.assertEqual(text[block["start"]:block["end"]], block["text"])
            self.assertEqual(block["heading"], "Board independence")

    def test_chunk_offsets_cover_text_with_overlap_and_stable_ids(self):
        paragraphs = [" ".join(f"term{group}_{i}" for i in range(90)) for group in range(6)]
        text, blocks = rag_corpus.extract_html("<h2>Pay</h2>" + "".join(f"<p>{p}</p>" for p in paragraphs))
        document = {"id": "doc1", "text": text, "company_id": "company1", "meeting_id": "meeting1"}
        chunks = rag_corpus.chunk_document(document, blocks)
        self.assertGreater(len(chunks), 2)
        self.assertEqual(chunks, rag_corpus.chunk_document(document, blocks))
        self.assertEqual(len({chunk["id"] for chunk in chunks}), len(chunks))
        self.assertEqual(chunks[0]["start"], 0)
        self.assertEqual(chunks[-1]["end"], len(text))
        for chunk in chunks:
            self.assertEqual(chunk["text"], text[chunk["start"]:chunk["end"]])
            self.assertLessEqual(len(chunk["text"].split()), 180)
        for before, after in zip(chunks, chunks[1:]):
            self.assertLess(after["start"], before["end"])


def write_csv(path, columns, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


class CorpusBoundaries(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.index, self.votes = self.root / "index.csv", self.root / "votes.csv"
        self.rows, self.ballots = [], []
        for meeting_id, day, filed, file in (
            ("a", "2024-06-10", "2024-05-01", "a.html"),
            ("b", "2025-06-10", "2025-05-01", "b.html"),
            ("missing", "2024-06-10", "2024-05-01", "missing.html"),
            ("late", "2024-06-10", "2024-06-05", "late.html"),
        ):
            self.rows.append({"meeting_id": meeting_id, "meeting_date": day, "filed": filed, "file": file, "url": "https://www.sec.gov/example/" + file})
            self.ballots.append({"meeting_id": meeting_id, "meeting_date": day, "company_id": "c1", "company": "Example Inc.",
                                 "nbim_vote": "LABEL_SECRET", "rationale_text": "RATIONALE_SECRET", "against_board": "TARGET_SECRET"})
            if meeting_id != "missing":
                (self.root / file).write_text("<h2>Board</h2><p>Ada Smith is independent.</p>", encoding="utf-8")
        self.save()

    def save(self):
        write_csv(self.index, list(self.rows[0]), self.rows)
        write_csv(self.votes, list(self.ballots[0]), self.ballots)

    def test_default_pilot_excludes_later_year_and_labels_reports_unavailable_sources(self):
        corpus = rag_corpus.build_corpus(self.index, self.votes)
        self.assertEqual([doc["meeting_id"] for doc in corpus["documents"]], ["a"])
        self.assertEqual({row["meeting_id"] for row in corpus["skipped"]}, {"missing", "late"})
        self.assertNotIn("SECRET", str(corpus))
        self.assertTrue(corpus["chunks"])
        doc = corpus["documents"][0]
        self.assertEqual(Path(doc["file"]), (self.root / "a.html").resolve())
        self.assertEqual(len(doc["sha256"]), 64)
        self.assertEqual(corpus, rag_corpus.build_corpus(self.index, self.votes))

    def test_explicit_meetings_override_default_year_and_report_unknown_ids(self):
        corpus = rag_corpus.build_corpus(self.index, self.votes, meeting_ids=["b", "unknown"])
        self.assertEqual([doc["meeting_id"] for doc in corpus["documents"]], ["b"])
        self.assertEqual(corpus["skipped"][0]["meeting_id"], "unknown")

    def test_mutating_vote_targets_cannot_change_corpus(self):
        before = rag_corpus.build_corpus(self.index, self.votes)
        for ballot in self.ballots:
            ballot.update(nbim_vote="DIFFERENT", rationale_text="CHANGED", against_board="CHANGED")
        self.save()
        self.assertEqual(before, rag_corpus.build_corpus(self.index, self.votes))

    def test_conflicting_meeting_identity_is_rejected(self):
        self.ballots.append({**self.ballots[0], "company_id": "another-company"})
        self.save()
        with self.assertRaises(ValueError):
            rag_corpus.build_corpus(self.index, self.votes)

    def test_unknown_company_and_path_escape_are_not_indexed(self):
        self.rows[0]["file"] = "../outside.html"
        self.ballots[1]["company_id"] = ""
        self.save()
        corpus = rag_corpus.build_corpus(self.index, self.votes, year=None)
        self.assertEqual(corpus["documents"], [])
        self.assertEqual(len(corpus["skipped"]), 4)


if __name__ == "__main__":
    unittest.main()
