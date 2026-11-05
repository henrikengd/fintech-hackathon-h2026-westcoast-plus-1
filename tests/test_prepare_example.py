"""Regressions for development selection and evidence lost in the first pilot."""

from hashlib import sha256
import importlib.util
from pathlib import Path
from subprocess import CompletedProcess
import tempfile
import unittest
from unittest.mock import patch

from voting_assistant.evaluation import load_manifest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/prepare_example.py"
SPEC = importlib.util.spec_from_file_location("prepare_example", SCRIPT)
prepare_example = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prepare_example)


class PrepareExampleTests(unittest.TestCase):
    def test_both_development_meetings_selected_with_independence_and_committee_evidence(self):
        # A fake Poppler result avoids depending on a downloaded copyrighted PDF.
        pages = [f"Source page {number}" for number in range(1, 62)]
        pages[15] = "Hauser and Haverty are independent. Thomas is not independent."
        pages[17] = "Audit committee members are independent. Hauser is the chair."
        pages[18] = "Haverty serves on the compensation committee. KPMG independence was discussed."
        pages[19] = "Nominating committee membership and independence."
        pages[60] = "Fiscal 2025 (USD thousands): tax fees 277, total fees 3170."
        extracted = CompletedProcess([], 0, stdout="\f".join(pages).encode())
        with tempfile.TemporaryDirectory() as temp:
            proxy = Path(temp) / "source.pdf"
            proxy.write_bytes(b"mock PDF")
            output = Path(temp) / "prepared"
            with patch.object(prepare_example, "PROXY_SHA256", sha256(proxy.read_bytes()).hexdigest()), \
                 patch.object(prepare_example.subprocess, "run", return_value=extracted):
                prepare_example.prepare(proxy, output, "development")
            manifest, meetings, _ = load_manifest(output / "manifest.json")
            selected = [item for item in meetings if item.split == manifest.split]
            self.assertEqual([item.agenda.meeting_id for item in selected], [
                "ccc-2025-05-22", "sprinklr-2025-06-12",
            ])
            proposals = selected[1].agenda.proposals
            self.assertEqual([item.proposal_id for item in proposals], ["1a", "1b", "1c", "2", "3"])
            for proposal in proposals[:3]:
                evidence = {source.page: source.quote for source in proposal.sources}
                self.assertEqual(evidence[16], pages[15])
                self.assertEqual(evidence[18], pages[17])
                self.assertEqual(evidence[19], pages[18])
                self.assertEqual(evidence[20], pages[19])
            auditor = {source.page: source.quote for source in proposals[4].sources}
            self.assertEqual(auditor[19], pages[18])
            self.assertEqual(auditor[61], pages[60])

    def test_development_examples_cannot_be_prepared_as_test(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, "development meetings"):
                prepare_example.prepare(Path(temp) / "unused.pdf", Path(temp) / "out", "test")


if __name__ == "__main__":
    unittest.main()
