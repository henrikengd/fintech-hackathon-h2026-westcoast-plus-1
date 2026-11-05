"""Offline scoring, frozen-artifact and paid-request cache checks."""
import boot  # noqa: F401
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

import claude_board_experiment as experiment


def row(meeting, item, board, actual, score=.9):
    return {"meeting_id": meeting, "item_no": item, "company_id": "company",
            "company": "Company", "meeting_date": "2024-06-01",
            "proposal_text": "Elect a director", "proponent": "Management",
            "mgmt_rec": board, "nbim_vote": actual, "local_score": score}


class ClaudeBoardExperimentTests(unittest.TestCase):
    def fixture(self, folder, rows=None):
        base = Path(folder)
        rows = rows if rows is not None else [row("one", "1", "MOT", "FOR"),
                                             row("two", "1", "FOR", "MOT")]
        frame = pd.DataFrame(rows)
        frame.to_csv(base / "evaluation-labels.csv", index=False)
        (base / "bundles").mkdir()
        ids = list(frame.meeting_id.drop_duplicates())
        hashes = {}
        for mid in ids:
            bundle = {"meeting": {"meeting_id": mid}, "proposals": [
                {"item": str(r["item_no"]), "board_recommendation": r["mgmt_rec"]}
                for r in rows if r["meeting_id"] == mid]}
            path = base / "bundles" / f"{mid}.json"
            experiment.immutable_json(path, bundle)
            hashes[mid] = experiment.digest(path)
        plan = {"target": "against_board", "test_evaluated": False,
                "evaluation_kind": "EXPOSED_2024_DEVELOPMENT", "scope": "historical_votes_only",
                "settings": {"model": experiment.PRICE["model"], "effort": "low", "source_hashes": {}},
                "meeting_ids": ids, "bundle_sha256": hashes,
                "evaluation_labels_sha256": experiment.digest(base / "evaluation-labels.csv"),
                "local_thresholds": {"at_calibration_threshold": .5, "at_validation_threshold": .8},
                "cohort": {"rows": len(rows), "meetings": len(ids),
                           "positive": int(frame.nbim_vote.ne(frame.mgmt_rec).sum())},
                "history_policy": "strict_before_meeting_minus_5_days", "comparison_limits": []}
        plan["plan_id"] = experiment.fingerprint(plan)
        experiment.immutable_json(base / "plan.json", plan)
        return base, plan

    def response(self, base, plan, mid, items=None, status="completed"):
        record = {"meeting_id": mid, "plan_id": plan["plan_id"],
                  "bundle_sha256": plan["bundle_sha256"][mid], "status": status,
                  "elapsed_seconds": 1., "usage": {"input_tokens": 10, "output_tokens": 5}}
        if status == "completed":
            record["result"] = {"items": items or []}
        else:
            record["error"] = {"type": "FixtureError", "status_code": 500}
        record["record_id"] = experiment.fingerprint(record)
        path = base / "responses" / f"{mid}.json"
        experiment.immutable_json(path, record)
        return path

    def test_scoring_uses_vote_direction_and_preserves_unknown_predictions(self):
        rows = pd.DataFrame([
            row("a", "1", "MOT", "FOR"),  # Disagreement without MOT.
            row("a", "2", "MOT", "MOT"),  # MOT without disagreement.
            row("a", "3", "FOR", "AVSTÅ"),
            row("a", "4", "FOR", "MOT"),
            row("a", "5", "FOR", "FOR"),
        ])
        predictions = {("a", "1"): {"vote": "FOR", "against_board": False},
                       ("a", "2"): {"vote": "MOT", "against_board": True},
                       ("a", "3"): {"vote": "AVSTÅ"},
                       ("a", "4"): {"vote": None},
                       ("a", "5"): {"vote": "INVALID"}}
        score = experiment.score_rows(rows, predictions)
        self.assertEqual((score["tp"], score["fp"], score["fn"], score["tn"]), (2, 0, 1, 2))
        self.assertEqual((score["covered"], score["uncovered"]), (3, 2))
        self.assertEqual(score["recall"], 2 / 3)
        mot = experiment.score_rows(rows, predictions, "mot")
        self.assertEqual((mot["tp"], mot["fp"], mot["fn"]), (1, 0, 1))
        self.assertEqual(mot["recall"], .5)

    def test_report_keeps_failed_and_interrupted_calls_in_same_row_denominators(self):
        rows = [row("one", "1", "MOT", "FOR"), row("one", "2", "FOR", "MOT"),
                row("two", "1", "FOR", "MOT"), row("three", "1", "FOR", "MOT"),
                row("four", "1", "FOR", "MOT")]
        with tempfile.TemporaryDirectory() as folder:
            base, plan = self.fixture(folder, rows)
            self.response(base, plan, "one", [{"item": "1", "vote": "FOR", "against_board": True},
                                              {"item": "2", "vote": None, "against_board": None}])
            self.response(base, plan, "two", status="failed")
            experiment.immutable_json(base / "requests" / "three.json", {"interrupted": True})
            report = experiment.report(base)
        self.assertEqual((report["attempted_meetings"], report["completed_meetings"],
                          report["failed_meetings"], report["pending_or_interrupted_meetings"],
                          report["unattempted_meetings"]), (3, 1, 1, 1, 1))
        self.assertEqual(report["attempted_rows"], 4)
        self.assertFalse(report["complete"])
        score = report["claude"]["disagreement"]
        self.assertEqual((score["n"], score["tp"], score["fn"], score["uncovered"]), (4, 1, 3, 3))
        self.assertEqual(score["recall"], .25)
        for result in report["same_rows_local"].values():
            self.assertEqual((result["n"], result["positive"], result["tp"]), (4, 4, 4))
        self.assertEqual(report["usage"]["input_tokens"], 20)
        self.assertEqual(report["api_calls"], 3)

    def test_empty_report_does_not_present_full_cohort_as_scored(self):
        with tempfile.TemporaryDirectory() as folder:
            base, _ = self.fixture(folder)
            report = experiment.report(base)
        self.assertEqual(report["cohort"]["rows"], 2)
        self.assertEqual(report["attempted_rows"], 0)
        self.assertEqual(report["unattempted_meetings"], 2)
        self.assertIsNone(report["claude"]["disagreement"]["recall"])
        self.assertFalse(report["complete"])

    def test_plan_bundle_labels_and_response_tampering_are_rejected(self):
        for target in ("plan.json", "bundles/one.json", "evaluation-labels.csv", "responses/one.json"):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as folder:
                base, plan = self.fixture(folder)
                self.response(base, plan, "one", [{"item": "1", "vote": "FOR"}])
                path = base / target
                if target.endswith(".csv"):
                    path.write_text(path.read_text().replace(".9", ".1"))
                else:
                    value = json.loads(path.read_text())
                    value["tampered"] = True
                    path.write_text(json.dumps(value))
                with self.assertRaises(ValueError):
                    experiment.report(base)

    def test_cached_calls_are_not_repeated_and_interrupted_request_blocks_payment(self):
        with tempfile.TemporaryDirectory() as folder:
            base, _ = self.fixture(folder)

            def generated(bundle, **kwargs):
                return {"items": [{"item": p["item"], "vote": "FOR", "against_board": p["board_recommendation"] != "FOR"}
                                  for p in bundle["proposals"]], "usage": {"input_tokens": 12, "output_tokens": 7}}

            with patch.dict(experiment.os.environ, {"ANTHROPIC_API_KEY": "offline-fixture"}), \
                    patch.object(experiment.anthropic, "Anthropic") as client, \
                    patch.object(experiment.context, "generate_review", side_effect=generated) as generate, \
                    redirect_stdout(io.StringIO()):
                first = experiment.run(base, limit=1, workers=1)
                self.assertEqual(first["completed_meetings"], 1)
                second = experiment.run(base, limit=1, workers=1)
                self.assertEqual(second["completed_meetings"], 1)
                self.assertEqual(generate.call_count, 1)
                client.assert_called_once_with(max_retries=0, timeout=180.0)
                experiment.immutable_json(base / "requests" / "two.json", {"interrupted": True})
                with self.assertRaisesRegex(ValueError, "interrupted"):
                    experiment.run(base, workers=1)
                self.assertEqual(generate.call_count, 1)
            self.assertFalse((base / "running.lock").exists())

    def test_rate_limit_stops_later_calls_and_retains_failure(self):
        class RateLimited(Exception):
            status_code = 429

        with tempfile.TemporaryDirectory() as folder:
            base, _ = self.fixture(folder)
            with patch.dict(experiment.os.environ, {"ANTHROPIC_API_KEY": "offline-fixture"}), \
                    patch.object(experiment.anthropic, "Anthropic"), \
                    patch.object(experiment.context, "generate_review", side_effect=RateLimited("do not persist me")) as generate, \
                    redirect_stdout(io.StringIO()):
                report = experiment.run(base, workers=1)
            self.assertEqual(generate.call_count, 1)
            self.assertEqual((report["failed_meetings"], report["unattempted_meetings"]), (1, 1))
            self.assertEqual(report["claude"]["disagreement"]["fn"], 1)
            self.assertNotIn("do not persist me", (base / "responses" / "one.json").read_text())
            self.assertFalse((base / "running.lock").exists())


if __name__ == "__main__":
    unittest.main()
