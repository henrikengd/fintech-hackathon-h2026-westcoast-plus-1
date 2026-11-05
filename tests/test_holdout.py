"""Frozen dataset invariants; no network, private data, or model calls."""
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import unittest
from unittest.mock import patch
import tempfile

from voting_assistant.contracts import Agenda

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("prepare_holdout", ROOT / "scripts/prepare_holdout.py")
holdout = importlib.util.module_from_spec(spec)
spec.loader.exec_module(holdout)


class HoldoutTests(unittest.TestCase):
    def test_frozen_mapping_is_complete_temporal_and_label_separate(self):
        plan = json.loads(holdout.PLAN.read_text())
        freeze = json.loads(holdout.FREEZE.read_text())
        assert sha256(holdout.PLAN.read_bytes()).hexdigest() == freeze["plan_sha256"]
        assert len(plan["meetings"]) == 3
        assert plan["development_meetings"] == ["ccc-2025-05-22", "sprinklr-2025-06-12"]
        choices, mot = 0, 0
        for meeting in plan["meetings"]:
            assert "2025-06-12" < meeting["meeting_date"] < "2026-01-01"
            assert meeting["source"]["document_date"] <= meeting["meeting_date"]
            reference = holdout.checked_reference(meeting)
            assert sha256(holdout.encoded(reference)).hexdigest() == freeze["test_references"][meeting["meeting_id"]]
            ids = [p["proposal_id"] for p in meeting["proposals"]]
            assert ids == [m["public_nbim_proposal_id"] for m in meeting["mapping"]]
            assert len(ids) == len(set(ids)) == meeting["completeness"]["separate_vote_choices"]
            for proposal in meeting["proposals"]:
                assert set(proposal) == {"proposal_id", "original_text", "proposal_type", "evidence_pages"}
                assert proposal["evidence_pages"] == sorted(set(proposal["evidence_pages"]))
            choices += len(ids)
            mot += sum(v["vote"] == "MOT" for v in reference["votes"])
        assert (choices, mot) == (21, 1)
        assert plan["counts"]["comparable_references"] == choices


    def test_source_checksum_checked_before_extraction(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        tmp_path = Path(temp.name)
        meeting = json.loads(holdout.PLAN.read_text())["meetings"][0]
        (tmp_path / meeting["source_file"]).write_bytes(b"different PDF edition")
        with patch.object(holdout.subprocess, "run", side_effect=AssertionError("must not extract changed PDF")):
            with self.assertRaisesRegex(ValueError, "checksum changed"):
                holdout.build_agenda(meeting, tmp_path)


    def test_agenda_extraction_excludes_all_reference_fields(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        tmp_path = Path(temp.name)
        meeting = json.loads(holdout.PLAN.read_text())["meetings"][0]
        raw = b"test pinned PDF"
        (tmp_path / meeting["source_file"]).write_bytes(raw)
        meeting["source"]["sha256"] = sha256(raw).hexdigest()
        pages = "\f".join(f" Source page {n}   facts\n complete conditions " for n in range(1, 30))
        with patch.object(holdout.subprocess, "run", return_value=SimpleNamespace(stdout=pages.encode())):
            agenda = holdout.build_agenda(meeting, tmp_path)
        Agenda.model_validate(agenda)
        from voting_assistant.assessment import _facts, _user_input
        parsed = Agenda.model_validate(agenda)
        model_input = json.loads(_user_input(parsed, _facts(parsed)))
        assert set(model_input) == {"meeting_date", "shared_excerpts", "proposals"}
        assert len(model_input["proposals"]) == 4
        payload = json.dumps(agenda)
        for forbidden in ("nbim_vote", "board_recommendation", "rationale_text", "against_board", "Vote rationale:"):
            assert forbidden not in payload
        assert agenda["proposals"][0]["sources"][0]["quote"] == "Source page 1 facts\ncomplete conditions"


    def test_historical_policy_has_identical_archived_bytes_before_and_after_meetings(self):
        evidence = json.loads((ROOT / "data/policies/nbim-2025-historical-evidence.json").read_text())
        captures = [s for s in evidence["sources"] if "web.archive.org/web/" in s["url"] and s["url"].endswith(".pdf")]
        assert len(captures) >= 3
        assert min(s["document_date"] for s in captures) < "2025-06-18"
        assert max(s["document_date"] for s in captures) > "2025-07-02"
        assert {s["sha256"] for s in captures} == {holdout.POLICY_HASH}
