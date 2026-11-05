"""Offline guards for a new held-out cohort and sealed-prediction scoring."""
import boot  # noqa: F401
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

import numpy as np
import pandas as pd

import fresh_test as experiment
from vector_model import META_FIELDS, KEY


def row(mid="new", item="1", day="2026-10-08", board="FOR", company="company"):
    return {"meeting_id": mid, "item_no": item, "company_id": company,
            "meeting_date": day, "company": "Company", "proposal_text": "Elect a director",
            "mgmt_rec": board, "proponent": "Management"}


class FreshTestTests(unittest.TestCase):
    def policy(self):
        return {"date_start": "2026-10-01", "date_end": "2026-10-31", "history_cutoff": "2026-09-30",
                "company_ids": ["company"], "excluded_meeting_ids": ["old"],
                "excluded_company_dates": [["company", "2026-09-01"]]}

    def fixture(self, base, rows=None):
        rows = rows or [row("a", board="MOT"), row("b", board="FOR")]
        pd.DataFrame(rows, columns=META_FIELDS).to_csv(base / "ballots.csv", index=False)
        ids = list(dict.fromkeys(r["meeting_id"] for r in rows))
        plan = {"record_id": "frozen", "meeting_ids": ids,
                "cohort": {"rows": len(rows), "meetings": len(ids)},
                "settings": {"local_threshold": .5, "model": "mock-model", "effort": "low"},
                "bundles": {mid: f"bundles/{mid}.json" for mid in ids}}
        for mid in ids:
            experiment.immutable_json(base / plan["bundles"][mid], {"meeting": {"meeting_id": mid},
                "proposals": [{"item": r["item_no"]} for r in rows if r["meeting_id"] == mid]})
        return plan

    def local(self, base, rows):
        value = experiment.signed({"freeze_id": "frozen", "items": [
            {"meeting_id": r["meeting_id"], "item_no": r["item_no"], "score": r.get("local_score", .9)} for r in rows]})
        experiment.immutable_json(base / "local-predictions.json", value)

    def response(self, base, mid, items=None, failed=False):
        value = {"freeze_id": "frozen", "meeting_id": mid, "usage": {"input_tokens": 1, "output_tokens": 1}}
        if failed:
            value.update(status="failed", error={"type": "FixtureFailure", "status_code": 500})
        else:
            value.update(status="completed", result={"items": items or []})
        experiment.immutable_json(base / "responses" / f"{mid}.json", experiment.signed(value))

    def test_ballot_fields_reject_current_targets_before_any_embedding(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "ballots.csv"
            pd.DataFrame([{**row(), "nbim_vote": "MOT"}]).to_csv(source, index=False)
            with self.assertRaisesRegex(ValueError, "fresh outcomes"):
                experiment.read_frame(source, META_FIELDS)
            pd.DataFrame([row()], columns=META_FIELDS).to_csv(source, index=False)
            self.assertEqual(experiment.read_frame(source, META_FIELDS).iloc[0].meeting_id, "new")

    def test_preflight_requires_frozen_policy_settings_history_and_model(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            for filename in ("selection-policy.json", "locked-settings.json"):
                (base / filename).write_text("{}")
            (base / "preflight-freeze.json").write_text(json.dumps({
                "code": dict.fromkeys(experiment.SOURCE_FILES, "unused"), "artifacts": {}}))
            with patch.object(experiment, "read_frame") as read, self.assertRaisesRegex(ValueError, "Preflight must freeze"):
                experiment.prepare(base / "unopened-ballots.csv", base)
            read.assert_not_called()

    def test_capture_commits_ballots_and_raw_sources_without_parsing_references(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            ballots = base / "source-ballots.csv"
            pd.DataFrame([row()], columns=META_FIELDS).to_csv(ballots, index=False)
            raw = base / "raw.json"
            raw.write_text('{"fresh_outcome":"not parsed"}')
            capture = {"references_sha256": "a" * 64, "ballots_sha256": experiment.digest(ballots),
                       "raw_artifacts": {"raw.json": experiment.digest(raw)}}
            (base / "source-capture.json").write_text(json.dumps(capture))
            with patch.object(experiment, "read_frame") as read:
                commitment, artifacts = experiment.capture_commitment(ballots, base, {"source_access": "fixture"})
            read.assert_not_called()
            self.assertEqual(commitment, "a" * 64)
            self.assertEqual(artifacts, ["source-capture.json", "raw.json"])
            ballots.write_text("modified")
            with self.assertRaisesRegex(ValueError, "Ballots differ"):
                experiment.capture_commitment(ballots, base, {"source_access": "fixture"})

    def test_prepare_freezes_and_predicts_a_label_blind_synthetic_cohort(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            (base / "models").mkdir()
            (base / "models/learner.joblib").write_bytes(b"synthetic model")
            pd.DataFrame([{**row("old", day="2026-09-01"), "nbim_vote": "MOT"}]).to_csv(base / "history.csv", index=False)
            ballots = base / "source-ballots.csv"
            pd.DataFrame([row()], columns=META_FIELDS).to_csv(ballots, index=False)
            policy = {**self.policy(), "source_access": "fixture", "enumeration_complete_required": True,
                      "company_queries": [{"company_id": "company", "company": "Company"}]}
            settings = {"embedding_assets": {"fixture": "weights"}, "local_threshold": .5, "model": "mock-model", "effort": "low",
                        "system": experiment.fresh_inference.SYSTEM, "schema": experiment.fresh_inference.Drafts.model_json_schema(),
                        "history_sha256": experiment.digest(base / "history.csv"),
                        "learner_sha256": experiment.digest(base / "models/learner.joblib")}
            for name, value in [("selection-policy.json", policy), ("locked-settings.json", settings),
                                ("discovery.json", {"complete": True, "company_queries_completed": 1, "candidates": [row()]})]:
                experiment.immutable_json(base / name, value)
            experiment.immutable_json(base / "source-capture.json", {"references_sha256": "a" * 64,
                "ballots_sha256": experiment.digest(ballots), "raw_artifacts": {}})
            experiment.immutable_json(base / "preflight-freeze.json", {
                "code": {name: experiment.digest(experiment.ROOT / name) for name in experiment.SOURCE_FILES},
                "artifacts": {name: experiment.digest(base / name) for name in experiment.PREFLIGHT_ARTIFACTS}})
            state = {"target": "against_board", "config": experiment.fresh_inference.LOCAL_CONFIG}
            def embeddings(frame):
                return np.ones((len(frame), experiment.fresh_inference.DIMENSION), dtype=np.float32), {"fixture": True}
            with patch.object(experiment.local_rag, "model_fingerprint", return_value=settings["embedding_assets"]), \
                 patch.object(experiment.joblib, "load", return_value=state), \
                 patch.object(experiment, "embedding_matrix", side_effect=embeddings), \
                 patch.object(experiment.fresh_inference, "local_predict", return_value=np.array([.9])):
                prepared = experiment.prepare(ballots, base)
                self.assertEqual(prepared["cohort"]["rows"], 1)
                self.assertFalse(prepared["predictions_sealed"])
                frozen = experiment.load_frozen(base)
                self.assertEqual(frozen["reference_commitment"], "a" * 64)
                self.assertIn("source-capture.json", frozen["artifacts"])
                predictions = experiment.predict_local(base)
                self.assertEqual(predictions["items"][0]["against_board"], True)
                self.assertFalse((base / "prediction-seal.json").exists())
                with self.assertRaisesRegex(ValueError, "already exists"):
                    experiment.prepare(ballots, base)
                (base / "locked-settings.json").write_text("{}")
                with self.assertRaisesRegex(ValueError, "artifact changed"):
                    experiment.load_frozen(base)

    def test_cohort_date_identity_group_and_company_boundaries(self):
        history = pd.DataFrame([{**row("old", day="2026-09-01"), "nbim_vote": "MOT"}])
        query = pd.DataFrame([row()], columns=META_FIELDS)
        self.assertEqual(len(experiment.validate_ballots(query, history, self.policy())), 1)
        for changes, message in [({"meeting_date": "2026-09-30"}, "date window"),
                                 ({"meeting_id": "old"}, "Previously exposed"),
                                 ({"company_id": "unknown"}, "sampling frame")]:
            with self.subTest(changes=changes), self.assertRaisesRegex(ValueError, message):
                experiment.validate_ballots(query.assign(**changes), history, self.policy())
        policy = self.policy()
        policy["excluded_company_dates"].append(["company", "2026-10-08"])
        with self.assertRaisesRegex(ValueError, "company/date group"):
            experiment.validate_ballots(query, history, policy)

    def test_fresh_reference_file_is_not_opened_before_both_streams_seal(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            plan = self.fixture(base)
            with patch.object(experiment, "load_frozen", return_value=plan), patch.object(experiment, "read_frame") as read:
                with self.assertRaisesRegex(ValueError, "before opening fresh outcomes"):
                    experiment.score(base / "must-not-read.csv", base)
                read.assert_not_called()
            self.response(base, "a", [{"item": "1", "vote": "FOR"}])
            self.response(base, "b", failed=True)
            with patch.object(experiment, "load_frozen", return_value=plan):
                self.assertIsNone(experiment.seal_predictions(base))

    def test_scoring_retains_failures_and_unknowns_without_wrong_disagreement_semantics(self):
        rows = [row("a", "1", board="MOT"), row("a", "2", board="MOT"), row("b", board="FOR"),
                row("c", "1", board=""), row("c", "2", board="FOR")]
        labels = ["FOR", "MOT", "MOT", "MOT", ""]
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            plan = self.fixture(base, rows)
            self.local(base, [{**r, "local_score": (.9 if i in (0, 2) else .1)} for i, r in enumerate(rows)])
            self.response(base, "a", [{"item": "1", "vote": "FOR"}, {"item": "2", "vote": "MOT"}])
            self.response(base, "b", failed=True)
            self.response(base, "c", [{"item": "1", "vote": "MOT"}, {"item": "2", "vote": "FOR"}])
            references = base / "unopened-reference.csv"
            pd.DataFrame([{**{k: r[k] for k in KEY}, "nbim_vote": label} for r, label in zip(rows, labels)]).to_csv(references, index=False)
            with patch.object(experiment, "load_frozen", return_value=plan):
                self.assertIsNotNone(experiment.seal_predictions(base))
                result = experiment.score(references, base)
                with self.assertRaisesRegex(ValueError, "already been scored"):
                    experiment.score(references, base)
            self.assertEqual(result["known_disagreement_rows"], 3)
            self.assertEqual((result["unknown_nbim"], result["known_nbim_unknown_board"]), (1, 1))
            self.assertEqual((result["claude"]["tp"], result["claude"]["fn"], result["claude"]["tn"]), (1, 1, 1))
            self.assertEqual((result["local"]["tp"], result["local"]["fn"]), (2, 0))
            self.assertEqual(result["claude_literal_mot"]["n"], 4)
            self.assertEqual(result["claude_literal_mot"]["positive"], 3)

    def test_tampered_predictions_are_rejected_before_reference_access(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            rows = [row("a"), row("b")]
            plan = self.fixture(base, rows)
            self.local(base, rows)
            self.response(base, "a", [{"item": "1", "vote": "FOR"}])
            self.response(base, "b", failed=True)
            with patch.object(experiment, "load_frozen", return_value=plan):
                experiment.seal_predictions(base)
                (base / "responses/b.json").write_text('{}')
                with patch.object(experiment, "read_frame") as read, self.assertRaisesRegex(ValueError, "artifact changed"):
                    experiment.score(base / "do-not-read.csv", base)
                read.assert_not_called()

    def test_changed_reference_commitment_is_rejected_before_parsing_outcomes(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            rows = [row("a"), row("b")]
            plan = self.fixture(base, rows)
            plan["reference_commitment"] = "a" * 64
            self.local(base, rows)
            self.response(base, "a", [{"item": "1", "vote": "FOR"}])
            self.response(base, "b", failed=True)
            references = base / "changed-reference.csv"
            references.write_text("do not parse this")
            with patch.object(experiment, "load_frozen", return_value=plan):
                experiment.seal_predictions(base)
                with patch.object(experiment, "read_frame") as read, self.assertRaisesRegex(ValueError, "source commitment"):
                    experiment.score(references, base)
                read.assert_not_called()

    def test_paid_runner_uses_frozen_settings_and_reuses_failure_without_retry(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            rows = [row("a"), row("b")]
            plan = self.fixture(base, rows)
            self.local(base, rows)
            result = {"items": [{"item": "1", "vote": "FOR"}], "usage": {"input_tokens": 8, "output_tokens": 4}}
            failure = type("TransportFailure", (Exception,), {"status_code": 500})("DO_NOT_SAVE_SECRET")
            client = Mock()
            client.__enter__ = Mock(return_value=client)
            client.__exit__ = Mock(return_value=False)
            with patch.object(experiment, "load_frozen", return_value=plan), patch.dict(experiment.os.environ, {"ANTHROPIC_API_KEY": "fixture"}), \
                 patch.object(experiment.anthropic, "Anthropic", return_value=client) as create, \
                 patch.object(experiment.fresh_inference, "generate_review", side_effect=[result, failure]) as call, redirect_stdout(io.StringIO()):
                first = experiment.predict_claude(base, workers=1)
                second = experiment.predict_claude(base, workers=1)
            self.assertEqual((first["claude_completed"], first["claude_failed"]), (1, 1))
            self.assertTrue(second["predictions_sealed"])
            self.assertEqual(call.call_count, 2)
            self.assertEqual(create.call_count, 2)
            self.assertEqual(call.call_args.kwargs["model"], "mock-model")
            self.assertEqual(call.call_args.kwargs["effort"], "low")
            self.assertNotIn("DO_NOT_SAVE_SECRET", (base / "responses/b.json").read_text())


if __name__ == "__main__":
    unittest.main()
