from datetime import date
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from pydantic import BaseModel, Field

from voting_assistant.cli import CliError
from voting_assistant.contracts import Agenda, Assessment, MeetingReference, Proposal, Source, Vote
from voting_assistant.evaluation import Manifest, Meeting, load_manifest, run_evaluation, summarize


class StubRun(BaseModel):
    status: str
    assessments: list[Assessment]
    cost_usd: Decimal
    errors: list[str] = Field(default_factory=list)


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)
        self.output = self.directory / "report.json"
        self.source = Source(
            document="Fictional notice", document_date=date(2025, 1, 1),
            version="v1", sha256="a" * 64, page=1,
        )
        self.manifest = Manifest(version=1, dataset_kind="synthetic", meetings=[])
        self.meeting = self.meeting_for("first", date(2025, 1, 2))

    def meeting_for(self, meeting_id, day, split="test"):
        agenda = Agenda(
            meeting_id=meeting_id, company_id="issuer", meeting_date=day,
            document_source=self.source,
            proposals=[
                Proposal(proposal_id=proposal_id, original_text="Fictional proposal", sources=[self.source])
                for proposal_id in ("p1", "p2", "p3", "p4")
            ],
        )
        reference = MeetingReference.model_validate({
            "meeting_id": meeting_id,
            "source": self.source.model_dump(),
            "vote_semantics": "synthetic",
            "votes": [
                {"proposal_id": "p1", "vote": "MOT", "board_recommendation": "FOR"},
                {"proposal_id": "p2", "vote": "MOT", "board_recommendation": "MOT"},
                {"proposal_id": "p3", "vote": "FOR", "board_recommendation": "FOR"},
                {"proposal_id": "p4", "vote": None},
            ],
        })
        return Meeting(split, agenda, reference)

    def result(self, proposal_id, vote):
        return Assessment(
            proposal_id=proposal_id, status="assessed" if vote else "manual_review",
            recommendation=vote, rationale="Test result",
            policy_sources=[self.source] if vote else [],
            factual_sources=[self.source] if vote else [],
            missing_information=[] if vote else ["Relevant facts"],
            uncertainty_reason=None if vote else "Facts missing",
        )

    def complete_run(self, agenda):
        return StubRun(
            status="complete",
            assessments=[self.result(p.proposal_id, Vote.MOT) for p in agenda.proposals],
            cost_usd=Decimal("0.02"),
        )

    def write_manifest(self, meetings, dataset_kind="synthetic"):
        def write(name, payload):
            path = self.directory / name
            raw = payload.encode()
            path.write_bytes(raw)
            return {"path": name, "sha256": hashlib.sha256(raw).hexdigest()}

        entries = []
        for index, meeting in enumerate(meetings):
            entries.append({
                "split": meeting.split,
                "agenda": write(f"agenda-{index}.json", meeting.agenda.model_dump_json()),
                "reference": write(f"ref-{index}.json", meeting.reference.model_dump_json()),
            })
        path = self.directory / "manifest.json"
        path.write_text(json.dumps({"version": 1, "dataset_kind": dataset_kind, "meetings": entries}))
        return path

    def test_manual_review_and_missing_output_remain_in_mot_denominator(self):
        report = summarize([self.meeting], {"first": {
            "status": "partial",
            "assessments": [self.result("p1", None).model_dump(), self.result("p3", Vote.MOT).model_dump()],
        }})
        self.assertEqual(report["status"], "partial")
        self.assertEqual(report["manual_review"], 1)
        self.assertEqual(report["missing_output"], 2)
        self.assertEqual(report["missing_reference"], 1)
        self.assertEqual(report["recommendation_coverage"], 0.25)
        self.assertEqual(report["model"], {
            "tp": 0, "fp": 1, "tn": 0, "fn": 2,
            "scored": 3, "reference_mot": 2, "mot_precision": 0.0, "mot_recall": 0.0,
        })
        self.assertEqual(report["baseline"]["name"], "stem_som_styret")
        self.assertEqual(report["baseline"]["mot_recall"], 0.5)

    def test_missing_board_uses_explicit_fallback_and_empty_is_undefined(self):
        self.meeting.reference.votes[0].board_recommendation = None
        report = summarize([self.meeting], {})
        self.assertEqual(report["baseline"]["name"], "aldri_mot")
        self.assertIsNone(report["baseline"]["mot_precision"])
        self.assertEqual(report["baseline"]["missing_board_for_scored"], 1)
        empty = summarize([], {})
        self.assertIsNone(empty["model"]["mot_recall"])
        self.assertIsNone(empty["recommendation_coverage"])
        self.assertEqual(empty["status"], "partial")

    def test_manifest_rejects_hash_change_and_reference_mismatch(self):
        path = self.write_manifest([self.meeting])
        self.assertEqual(load_manifest(path)[1][0].agenda.meeting_id, "first")
        (path.parent / "ref-0.json").write_text("{}")
        with self.assertRaisesRegex(CliError, "checksum"):
            load_manifest(path)
        self.meeting.reference.votes.pop()
        path = self.write_manifest([self.meeting])
        with self.assertRaisesRegex(CliError, "proposal IDs"):
            load_manifest(path)

    def test_manifest_rejects_future_source_overlap_and_duplicate_meeting(self):
        second = self.meeting_for("second", date(2025, 1, 3), "development")
        with self.assertRaisesRegex(CliError, "later than"):
            load_manifest(self.write_manifest([self.meeting, second]))
        with self.assertRaisesRegex(CliError, "more than once"):
            load_manifest(self.write_manifest([self.meeting, self.meeting]))
        self.meeting.agenda.proposals[0].sources[0].document_date = date(2025, 1, 4)
        with self.assertRaisesRegex(CliError, "after the meeting"):
            load_manifest(self.write_manifest([self.meeting]))

    def test_verified_nbim_requires_a_known_reference_semantics(self):
        self.meeting.reference.vote_semantics = "unverified"
        with self.assertRaisesRegex(CliError, "verified vote semantics"):
            load_manifest(self.write_manifest([self.meeting], "nbim_verified"))
        self.meeting.reference.vote_semantics = "voting_intention"
        _, meetings, _ = load_manifest(self.write_manifest([self.meeting], "nbim_verified"))
        self.assertEqual(
            summarize(meetings, {})["reference_semantics_by_meeting"], {"voting_intention": 1}
        )

    def test_resume_keeps_reserved_spend_and_reuses_only_complete_meetings(self):
        second = self.meeting_for("second", date(2025, 1, 3))
        calls = []

        def interrupted(agenda, remaining, reserve):
            self.assertIsInstance(agenda, Agenda)
            self.assertNotIn("vote_semantics", agenda.model_dump())
            calls.append((agenda.meeting_id, remaining))
            reserve(Decimal("0.10"))
            if agenda.meeting_id == "second":
                self.assertEqual(json.loads(self.output.read_text())["spent_usd"], "0.12")
                raise KeyboardInterrupt
            return self.complete_run(agenda)

        arguments = dict(
            manifest=self.manifest, meetings=[self.meeting, second],
            manifest_sha256="a" * 64, output=self.output, max_cost_usd=Decimal("1"), config={"model": "stub"},
        )
        with self.assertRaises(KeyboardInterrupt):
            run_evaluation(assessor=interrupted, **arguments)
        with self.assertRaisesRegex(CliError, "output exists"):
            run_evaluation(assessor=interrupted, **arguments)
        with self.assertRaisesRegex(CliError, "configuration differs"):
            run_evaluation(
                assessor=interrupted, resume=True, **{**arguments, "config": {"model": "new"}}
            )

        def resumed(agenda, remaining, reserve):
            calls.append((agenda.meeting_id, remaining))
            return self.complete_run(agenda)

        report = run_evaluation(assessor=resumed, resume=True, **arguments)
        self.assertEqual(calls, [
            ("first", Decimal("1")), ("second", Decimal("0.98")), ("second", Decimal("0.88"))
        ])
        self.assertEqual(report["spent_usd"], "0.14")
        self.assertEqual(report["metrics"]["status"], "complete")

    def test_skipped_and_failed_meetings_keep_all_proposal_ids(self):
        def fail(agenda, remaining, reserve):
            raise RuntimeError("details must not reach the report")

        for budget in (Decimal("0"), Decimal("1")):
            with self.subTest(budget=budget):
                report = run_evaluation(
                    self.manifest, [self.meeting], "a" * 64,
                    self.output.with_suffix(f".{budget}.json"),
                    assessor=fail, max_cost_usd=budget, config={},
                )
                result = report["runs"]["first"]
                self.assertEqual(report["metrics"]["status"], "partial")
                self.assertEqual(
                    [item["proposal_id"] for item in result["assessments"]],
                    [proposal.proposal_id for proposal in self.meeting.agenda.proposals],
                )
                self.assertTrue(all(item["status"] == "manual_review" for item in result["assessments"]))
                self.assertNotIn("details must not reach", json.dumps(result))

    def test_invalid_completed_run_cannot_mark_report_complete(self):
        def wrong_order(agenda, remaining, reserve):
            run = self.complete_run(agenda)
            run.assessments.reverse()
            return run

        report = run_evaluation(
            self.manifest, [self.meeting], "a" * 64, self.output,
            assessor=wrong_order, max_cost_usd=Decimal("1"), config={},
        )
        self.assertEqual(report["runs"]["first"]["status"], "partial")
        self.assertEqual(report["metrics"]["status"], "partial")
