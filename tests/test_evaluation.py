from datetime import date
from decimal import Decimal
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pydantic import BaseModel, Field

from voting_assistant.cli import CliError
from voting_assistant.contracts import Agenda, Assessment, MeetingReference, Proposal, Source, Vote
from voting_assistant.evaluation import Manifest, Meeting, _code_fingerprint, load_manifest, run_evaluation, summarize

ATTACK_SCRIPT = Path(__file__).resolve().parents[1] / "scripts/prepare_api_attack.py"
ATTACK_SPEC = importlib.util.spec_from_file_location("prepare_api_attack", ATTACK_SCRIPT)
prepare_api_attack = importlib.util.module_from_spec(ATTACK_SPEC)
ATTACK_SPEC.loader.exec_module(prepare_api_attack)


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
        self.assertEqual(report["valid_manual_review"], 1)
        self.assertEqual(report["exclusions"], [{
            "meeting_id": "first", "proposal_id": "p4", "reason": "reference_vote_unavailable",
        }])
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
            attempt = json.loads(self.output.read_text())["attempts"][agenda.meeting_id][-1]
            self.assertEqual(attempt["status"], "running")
            self.assertIsNotNone(attempt["started_at"])
            self.assertEqual(attempt["cost_usd"], "0")
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
        self.assertEqual(len(report["attempts"]["first"]), 1)
        interrupted_attempt, completed_attempt = report["attempts"]["second"]
        self.assertEqual(interrupted_attempt["status"], "interrupted")
        self.assertEqual(interrupted_attempt["cost_usd"], "0.10")
        self.assertIsNone(interrupted_attempt["run"])
        self.assertIn("interruption_detected_at", interrupted_attempt)
        self.assertEqual(completed_attempt["reason"], "resume_incomplete_attempt")
        self.assertEqual(completed_attempt["cost_usd"], "0.02")
        self.assertEqual(completed_attempt["run"], report["runs"]["second"])

    def test_resume_preserves_first_partial_result_and_its_error(self):
        def partial(agenda, remaining, reserve):
            run = self.complete_run(agenda)
            run.status = "partial"
            run.errors = ["First attempt failed source validation"]
            return run

        arguments = dict(
            manifest=self.manifest, meetings=[self.meeting], manifest_sha256="a" * 64,
            output=self.output, max_cost_usd=Decimal("1"), config={"model": "stub"},
        )
        first = run_evaluation(assessor=partial, **arguments)
        first_run = first["runs"]["first"]
        resumed = run_evaluation(
            assessor=lambda agenda, remaining, reserve: self.complete_run(agenda), resume=True, **arguments,
        )
        history = resumed["attempts"]["first"]
        self.assertEqual([attempt["number"] for attempt in history], [1, 2])
        self.assertEqual(history[0]["run"], first_run)
        self.assertEqual(history[1]["previous_errors"], first_run["errors"])
        self.assertEqual(resumed["spent_usd"], "0.04")
        self.assertEqual(sum(Decimal(item["cost_usd"]) for item in history), Decimal("0.04"))
        self.assertTrue(all(item["finished_at"] for item in history))

    def test_legacy_checkpoint_is_readable_but_not_silently_migrated_for_resume(self):
        arguments = dict(
            manifest=self.manifest, meetings=[self.meeting], manifest_sha256="a" * 64,
            output=self.output, max_cost_usd=Decimal("1"), config={},
        )
        report = run_evaluation(assessor=lambda agenda, remaining, reserve: self.complete_run(agenda), **arguments)
        report["configuration"]["checkpoint_version"] = 1
        report["configuration"].pop("code_sha256")
        report.pop("attempts")
        for result in report["runs"]["first"]["assessments"]:
            result.pop("validation_errors")
            result.pop("unverified_explanation")
        self.output.write_text(json.dumps(report))
        before = self.output.read_bytes()
        self.assertEqual(summarize([self.meeting], report["runs"])["proposals"], 4)
        with self.assertRaisesRegex(CliError, "configuration differs"):
            run_evaluation(assessor=lambda *args: self.fail("must not call a model"), resume=True, **arguments)
        self.assertEqual(self.output.read_bytes(), before)

    def test_runtime_fingerprint_tracks_code_and_lock_not_documentation(self):
        package = self.directory / "src/voting_assistant"
        package.mkdir(parents=True)
        runtime = package / "evaluation.py"
        runtime.write_text("first implementation")
        (self.directory / "uv.lock").write_text("locked dependency")
        with patch("voting_assistant.evaluation.__file__", str(runtime)):
            original = _code_fingerprint()
            (self.directory / "README.md").write_text("documentation change")
            self.assertEqual(_code_fingerprint(), original)
            runtime.write_text("changed implementation")
            self.assertNotEqual(_code_fingerprint(), original)
            runtime.write_text("first implementation")
            (self.directory / "uv.lock").write_text("changed dependency")
            self.assertNotEqual(_code_fingerprint(), original)

    def test_manual_validation_errors_and_old_unclassified_results_are_separate(self):
        valid_manual = self.result("p1", None).model_dump(mode="json")
        invalid_manual = self.result("p2", None).model_dump(mode="json")
        invalid_manual["validation_errors"] = ["Fact quote does not exist"]
        legacy_manual = self.result("p3", None).model_dump(mode="json")
        legacy_manual.pop("validation_errors")
        report = summarize([self.meeting], {"first": {
            "status": "partial", "errors": ["Citation validation failed"],
            "assessments": [valid_manual, invalid_manual, legacy_manual],
        }})
        self.assertEqual(report["manual_review"], 3)
        self.assertEqual(report["valid_manual_review"], 1)
        self.assertEqual(report["validation_failed_manual_review"], 1)
        self.assertEqual(report["unclassified_manual_review"], 1)
        self.assertEqual(report["validation_error_rows"][0]["proposal_id"], "p2")
        self.assertEqual(report["incomplete_meetings"], 1)
        self.assertEqual(report["model"]["fn"], 2)

    def test_complete_label_cannot_override_row_or_meeting_errors(self):
        for failure in ("row", "meeting"):
            results = [self.result(p.proposal_id, None).model_dump(mode="json") for p in self.meeting.agenda.proposals]
            errors = []
            if failure == "row":
                results[0]["validation_errors"] = ["Failed validation"]
            else:
                errors = ["Tool failure"]
            report = summarize([self.meeting], {"first": {
                "status": "complete", "assessments": results, "errors": errors,
            }})
            self.assertEqual(report["status"], "partial")

    def test_attack_pair_changes_one_quote_and_keeps_references_and_policy_equal(self):
        self.meeting = self.meeting_for("first", date(2025, 1, 2), "development")
        self.meeting.agenda.proposals[0].sources[0].quote = "The original source fact."
        path = self.write_manifest([self.meeting])
        directory = self.directory / "pair"
        prepare_api_attack.prepare_pair(path, directory, "first")
        original_manifest, originals, _ = load_manifest(directory / "original-manifest.json")
        attack_manifest, attacks, _ = load_manifest(directory / "attack-manifest.json")
        original = originals[0].agenda.model_dump(mode="json")
        attack = attacks[0].agenda.model_dump(mode="json")
        changed = attack["proposals"][0]["sources"][0]
        self.assertEqual(changed["quote"], "The original source fact." + prepare_api_attack.INSTRUCTION)
        changed["quote"] = original["proposals"][0]["sources"][0]["quote"]
        self.assertEqual(attack, original)
        self.assertEqual(originals[0].reference, attacks[0].reference)
        self.assertEqual(original_manifest.policy_documents, attack_manifest.policy_documents)
        note = json.loads((directory / "pair.json").read_text())
        self.assertIn("synthetic overlay", note["source_provenance_note"])
        self.assertEqual(note["changed_json_pointer"], "/proposals/0/sources/0/quote")
        self.assertNotIn("vote_semantics", json.dumps(original))
        with self.assertRaises(FileExistsError):
            prepare_api_attack.prepare_pair(path, directory, "first")

    def test_attack_pair_rejects_holdout_meeting(self):
        path = self.write_manifest([self.meeting])
        with self.assertRaisesRegex(CliError, "development meeting"):
            prepare_api_attack.prepare_pair(path, self.directory / "pair", "first")

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
