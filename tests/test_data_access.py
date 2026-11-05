import csv
import hashlib
import tempfile
import unittest
from datetime import date
from pathlib import Path

from voting_assistant.data_access import load_organizer_reference


class OrganizerReferenceTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "real_votes.csv"
        self.columns = [
            "meeting_id", "company_id", "meeting_date", "item_no",
            "nbim_vote_raw", "nbim_vote", "rationale_text", "mgmt_rec",
        ]
        self.rows = [
            ["export-1", "issuer-1", "2025-05-22", "2", "Withhold", "MOT", "private", "MOT"],
            ["export-1", "issuer-1", "2025-05-22", "1", "None", "", "private", "MOT"],
        ]

    def load(self, **overrides):
        with self.path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(self.columns)
            writer.writerows(self.rows)
        arguments = {
            "sha256": hashlib.sha256(self.path.read_bytes()).hexdigest(),
            "export_version": "test",
            "received_on": date(2026, 11, 5),
            "meeting_id": "public-agenda-1",
            "source_meeting_id": "export-1",
            "company_id": "issuer-1",
            "meeting_date": date(2025, 5, 22),
            "proposal_crosswalk": {"1": "first", "2": "second"},
            "board_recommendations": {"second": "FOR"},
        }
        arguments.update(overrides)
        return load_organizer_reference(self.path, **arguments)

    def test_import_preserves_raw_vote_and_provenance_but_drops_sensitive_columns(self):
        result = self.load()
        self.assertEqual(result["meeting_id"], "public-agenda-1")
        self.assertEqual(result["vote_semantics"], "unverified")
        self.assertEqual(result["votes"], [
            {"proposal_id": "first", "vote": None, "raw_vote": "None", "board_recommendation": None},
            {"proposal_id": "second", "vote": "MOT", "raw_vote": "Withhold", "board_recommendation": "FOR"},
        ])
        self.assertNotIn("private", repr(result))

    def test_duplicate_and_missing_rows_are_rejected(self):
        duplicate = self.rows.pop()
        with self.assertRaisesRegex(ValueError, "entire proposal crosswalk"):
            self.load()
        self.rows.extend([duplicate, duplicate])
        with self.assertRaisesRegex(ValueError, "repeated item"):
            self.load()

    def test_reject_changed_file_npx_schema_and_inconsistent_normalization(self):
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            self.load(sha256="0" * 64)
        self.columns.append("n_funds")
        with self.assertRaisesRegex(ValueError, "real_votes.csv schema"):
            self.load()
        self.columns.pop()
        self.rows[0][5] = "FOR"
        with self.assertRaisesRegex(ValueError, "differs from raw vote"):
            self.load()

    def test_reject_mismatched_company_and_date(self):
        with self.assertRaisesRegex(ValueError, "Meeting identity mismatch"):
            self.load(company_id="another-issuer")
        with self.assertRaisesRegex(ValueError, "Meeting identity mismatch"):
            self.load(meeting_date=date(2025, 5, 23))
