from argparse import Namespace
from datetime import date
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from voting_assistant.cli import CliError
from voting_assistant.retrieval import PolicyIndex, build_index


class PolicyIndexTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        directory = Path(temporary.name)
        self.manifest = directory / "manifest.json"
        self.index = directory / "index.json"
        self.source = directory / "policy.txt"
        text = (
            "Voting policy\n"
            "Audit appointment\n"
            "Review auditor independence.\n"
            "Board election\n"
            "Check that candidates are named.\n\f"
            "Assess time commitments.\n"
        ).encode("utf-8")
        self.source.write_bytes(text)
        self.manifest.write_text(json.dumps({
            "corpus_kind": "synthetic",
            "documents": [{
                "document": "Synthetic policy",
                "path": self.source.name,
                "policy_version": "synthetic-1",
                "document_date": "2025-01-01",
                "valid_from": "2025-01-01",
                "valid_until": "2026-01-01",
                "sha256": sha256(text).hexdigest(),
                "sections": [
                    {
                        "guideline_id": "auditor",
                        "section": "Audit appointment",
                        "page": 1,
                        "start": "Audit appointment",
                        "stop": "Board election",
                    },
                    {
                        "guideline_id": "board-election",
                        "section": "Board election",
                        "page": 1,
                        "end_page": 2,
                        "start": "Board election",
                    },
                ],
            }],
        }))

    def build(self) -> PolicyIndex:
        build_index(Namespace(manifest=self.manifest, output=self.index))
        return PolicyIndex.load(self.index)

    def test_reproducible_index_and_complete_section(self):
        index = self.build()
        snapshot = self.index.read_bytes()
        self.build()
        self.assertEqual(snapshot, self.index.read_bytes())
        self.assertEqual(index.corpus_kind, "synthetic")
        board = index.get("board-election", "synthetic-1")
        self.assertEqual(board["status"], "ok")
        self.assertIn("Assess time commitments.", board["guideline"]["text"])
        audit = index.get("auditor", "synthetic-1")
        self.assertNotIn("Board election", audit["guideline"]["text"])
        self.assertEqual(audit["guideline"]["source"]["page"], 1)

    def test_search_preserves_dates_and_explicit_failure_states(self):
        index = self.build()
        valid_date = date(2025, 7, 1)
        result = index.search("revisorvalg", valid_date, 1)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["results"][0]["guideline_id"], "auditor")
        self.assertEqual(index.search("revisorvalg", date(2026, 1, 1))["status"], "no_valid_version")
        self.assertEqual(index.search("blorfnax", valid_date)["status"], "no_matching_rules")
        self.assertEqual(index.get("auditor", "unavailable")["status"], "unknown_version")
        self.assertEqual(index.get("unknown", "synthetic-1")["status"], "unknown_guideline")

    def test_refuses_wrong_source_hash_and_leaves_previous_index(self):
        self.build()
        previous = self.index.read_bytes()
        self.source.write_text("Changed")
        with self.assertRaisesRegex(CliError, "Feil SHA-256"):
            self.build()
        self.assertEqual(previous, self.index.read_bytes())

    def test_refuses_modified_index_metadata(self):
        self.build()
        data = json.loads(self.index.read_bytes())
        data["corpus_kind"] = "nbim"
        self.index.write_text(json.dumps(data))
        with self.assertRaisesRegex(CliError, "kontrollsummen"):
            PolicyIndex.load(self.index)

    def test_nbim_manifest_cannot_use_synthetic_text(self):
        manifest = json.loads(self.manifest.read_bytes())
        manifest["corpus_kind"] = "nbim"
        self.manifest.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(CliError, "offisiell HTTPS"):
            self.build()
