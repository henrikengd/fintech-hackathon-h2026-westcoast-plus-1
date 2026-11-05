"""Offline protocol checks for literal board disagreement and as-of calibration."""
import boot  # noqa: F401
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import joblib
import numpy as np
import pandas as pd

import board_experiment as experiment
import vote_features
import vote_learner
from vote_targets import known_target, target_labels
from test_vector_experiment import row, vectors, yearly_rows


class BoardExperimentTests(unittest.TestCase):
    def test_loader_uses_whole_pre2025_source_and_checks_dates_before_target_access(self):
        records = yearly_rows().to_dict("records")
        records += [{**row("previously-mixed-test", 2023, "FOR"), "mgmt_rec": "MOT"},
                    {**row("unknown-board", 2024, "MOT"), "mgmt_rec": ""},
                    row("unknown-vote", 2024, "")]

        class FutureRow(dict):
            def __getitem__(self, key):
                if key in ("nbim_vote", "mgmt_rec", "proposal_text", "rationale_text", "proposal_type"):
                    raise AssertionError("Later-period target/content accessed")
                return super().__getitem__(key)

            def get(self, key, default=None):
                if key == "injection_flag":
                    raise AssertionError("Later-period non-identity field accessed")
                return super().get(key, default)

        records.append(FutureRow({**row("heldout", 2025, "INVALID_DO_NOT_READ"), "injection_flag": "1"}))
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "votes.csv"
            source.write_text("fixture source; no mixed-split files exist")
            with patch.object(experiment.csv, "DictReader", return_value=iter(records)):
                fit, calibration, provenance = experiment.load_temporal(source)
        self.assertIn("previously-mixed-test", fit.meeting_id.tolist())
        self.assertEqual(len(fit), 11)
        self.assertEqual(len(calibration), 2)
        self.assertEqual(provenance["excluded_unknown_labels"]["calibration"],
                         {"unknown_nbim": 1, "known_nbim_unknown_board": 1})
        self.assertEqual(provenance["source_inventory"]["old_test"], {"rows": 1, "meetings": 1})
        self.assertFalse(provenance["mixed_80_20_used"])
        self.assertFalse(provenance["test_labels_read"])
        self.assertTrue(provenance["supersedes_mixed_split_for_this_experiment"])
        selected = fit.loc[fit.meeting_id.eq("previously-mixed-test")]
        self.assertTrue(target_labels(selected, "against_board")[0])
        self.assertEqual(selected.nbim_vote.iloc[0], "FOR")

    def test_loader_rejects_bad_identities_dates_and_pre2025_votes(self):
        base = yearly_rows().to_dict("records")
        invalid_cases = [
            ([*base, row("heldout", 2025), row("heldout", 2026)], "duplicate proposal identity"),
            ([*base, row("2019", 2025, item="different")], "spans company/date"),
            ([*base[:-1], {**base[-1], "meeting_date": "2024-6-01"}], "YYYY-MM-DD"),
            ([*base[:-1], {**base[-1], "mgmt_rec": "INVALID"}], "Unexpected vote label"),
            ([*base[:-1], {**base[-1], "injection_flag": "1"}], "Injection fixtures"),
        ]
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "votes.csv"
            for records, error in invalid_cases:
                pd.DataFrame(records).fillna("").assign(injection_flag=lambda df: df.get("injection_flag", "0").replace("", "0")
                                                      if "injection_flag" in df else "0").to_csv(source, index=False)
                with self.subTest(error=error), self.assertRaisesRegex(ValueError, error):
                    experiment.load_temporal(source)

    def test_disagreement_targets_and_metric_names_do_not_mean_literal_mot(self):
        frame = pd.DataFrame([
            {**row("a", 2020, "FOR"), "mgmt_rec": "MOT"},
            {**row("b", 2020, "MOT"), "mgmt_rec": "MOT"},
            {**row("c", 2020, "AVSTÅ"), "mgmt_rec": "FOR"},
            {**row("d", 2020, "MOT"), "mgmt_rec": ""},
        ])
        self.assertEqual(known_target(frame, "against_board").tolist(), [True, True, True, False])
        with self.assertRaisesRegex(ValueError, "known votes"):
            target_labels(frame, "against_board")
        labels = target_labels(frame.iloc[:3], "against_board")
        self.assertEqual(labels.tolist(), [True, False, True])
        measured = experiment.measure(labels, [None, 0, 0], 0)
        self.assertEqual((measured["tp"], measured["fp"], measured["fn"]), (1, 1, 1))
        self.assertEqual(measured["positive"], 2)
        self.assertEqual(measured["predicted_positive"], 2)
        self.assertFalse({"mot", "predicted_mot", "predicted_mot_share"} & measured.keys())
        selected = experiment.options(labels, [None, 0, 0])
        self.assertIsNone(selected["recall"]["threshold"])
        self.assertEqual(selected["balanced"]["metrics"]["fn"], 1)
        self.assertNotIn("mot", selected["balanced"]["metrics"])

    def test_walk_forward_history_admits_earlier_same_year_but_excludes_own_cutoff_and_future(self):
        reference = pd.DataFrame([
            {**row("past", 2024, "FOR"), "meeting_date": "2024-01-04", "mgmt_rec": "MOT"},
            {**row("cutoff", 2024, "MOT"), "meeting_date": "2024-01-05"},
            {**row("own", 2020, "MOT"), "meeting_date": "2020-01-01"},
            {**row("future", 2024, "MOT"), "meeting_date": "2024-01-11"},
        ])
        query = pd.DataFrame([{**row("own", 2024), "meeting_date": "2024-01-10"}]).drop(columns="nbim_vote")
        before, names = vote_features.features(query, vectors(1), reference, vectors(4), target="against_board")
        self.assertEqual(before[0, names.index("history_count_log")], np.log1p(1))
        self.assertEqual(before[0, names.index("company_against_board_mean")], 1)
        changed = reference.copy()
        changed.loc[1:, "nbim_vote"] = "FOR"
        after, _ = vote_features.features(query, vectors(1), changed, vectors(4), target="against_board")
        np.testing.assert_allclose(before, after, equal_nan=True)
        changed.loc[0, "nbim_vote"] = "MOT"  # Now agrees with its MOT board recommendation.
        admitted, _ = vote_features.features(query, vectors(1), changed, vectors(4), target="against_board")
        self.assertEqual(admitted[0, names.index("company_against_board_mean")], 0)
        self.assertIn("board_mot", names)
        self.assertNotIn("company_mot_mean", names)

    def test_model_selection_precedes_calibration_while_threshold_and_past_context_can_change(self):
        fit = yearly_rows().iloc[:-2].reset_index(drop=True)
        calibration = pd.DataFrame([{**row(f"cal-{i}", 2024, "MOT" if i == 1 else "FOR", str(i)),
                                     "meeting_date": f"2024-{i:02d}-01"} for i in range(1, 5)])
        selections, thresholds, contexts = [], [], []
        actual_features = vote_features.features
        actual_options = experiment.options
        with tempfile.TemporaryDirectory() as folder:
            for version in range(3):
                output = Path(folder) / str(version)
                cal = calibration.copy()
                if version == 1:
                    cal["nbim_vote"] = ["FOR", "MOT", "FOR", "FOR"]
                elif version == 2:
                    cal["nbim_vote"] = ["FOR", "FOR", "FOR", "MOT"]
                calls = {"fit": 0, "calibration": 0, "options": 0}

                def checked_embeddings(frame):
                    self.assertTrue((output / "plan.json").exists())
                    return vectors(len(frame)), {}

                def checked_features(query, embedded, reference, reference_vectors, target):
                    self.assertNotIn("nbim_vote", query.columns)
                    self.assertEqual(target, "against_board")
                    self.assertTrue(reference.meeting_date.lt("2025-01-01").all())
                    result = actual_features(query, embedded, reference, reference_vectors, target=target)
                    if query.meeting_date.str.startswith("2024").any():
                        self.assertTrue((output / "selection.json").exists())
                        self.assertEqual(set(reference.meeting_id), set(fit.meeting_id) | set(cal.meeting_id))
                        contexts.append(result[0])
                    return result

                def fake_fit(config, training, history, embedded, target):
                    calls["fit"] += 1
                    self.assertTrue((output / "plan.json").exists())
                    self.assertTrue(training.meeting_date.lt("2024-01-01").all())
                    self.assertEqual(target, "against_board")
                    return {"config": config, "target": target, "latest_training": training.meeting_date.max()}

                def fake_predict(model, query, history, embedded):
                    self.assertNotIn("nbim_vote", query.columns)
                    self.assertLess(model["latest_training"], query.meeting_date.min())
                    if query.meeting_date.str.startswith("2024").any():
                        self.assertTrue((output / "selection.json").exists())
                        self.assertEqual(calls["options"], len(vote_learner.CONFIGS))
                        calls["calibration"] += 1
                        return np.array([.9, .7, .5, np.nan])
                    good = model["config"]["name"] == vote_learner.CONFIGS[0]["name"]
                    return np.array([(.9 if item == "1" else .1) if good else .5 for item in query.item_no])

                def checked_options(labels, scores):
                    if calls["options"] < len(vote_learner.CONFIGS):
                        np.testing.assert_array_equal(labels, target_labels(fit.iloc[2:], "against_board"))
                    calls["options"] += 1
                    return actual_options(labels, scores)

                with patch.object(experiment, "load_temporal", return_value=(fit, cal, {"protocol": "fixture"})), \
                        patch.object(experiment, "embedding_matrix", side_effect=checked_embeddings), \
                        patch.object(vote_features, "features", side_effect=checked_features), \
                        patch.object(vote_learner, "fit", side_effect=fake_fit), \
                        patch.object(vote_learner, "predict", side_effect=fake_predict), \
                        patch.object(experiment, "options", side_effect=checked_options), \
                        patch.object(experiment, "historical_reference", return_value=None), redirect_stdout(io.StringIO()):
                    summary = experiment.run(output=output)
                self.assertEqual(calls["fit"], len(vote_learner.CONFIGS) * 4 + 1)
                self.assertEqual(calls["calibration"], 1)
                self.assertEqual(calls["options"], len(vote_learner.CONFIGS) + 1)
                self.assertFalse(summary["test_evaluated"])
                self.assertEqual(summary["literal_mot_new_model"]["status"], "not_defined")
                selections.append(json.loads((output / "selection.json").read_text()))
                thresholds.append(summary["selected_threshold"])
                if version == 2:
                    saved = pd.read_csv(output / "calibration.csv")
                    self.assertEqual(saved.iloc[-1]["prediction"], "UNKNOWN")
                    self.assertEqual(saved.iloc[-1]["error"], "FN")
                    self.assertEqual(summary["calibration_selected"]["fn"], 1)
            self.assertEqual(selections[0], selections[1])
            self.assertEqual(selections[0], selections[2])
            self.assertEqual(thresholds, [.9, .7, .9])
            np.testing.assert_allclose(contexts[0][0], contexts[1][0], equal_nan=True)
            mean = vote_features.feature_names("against_board").index("company_against_board_mean")
            self.assertNotEqual(contexts[0][1, mean], contexts[1][1, mean])

    def test_saved_disagreement_model_replays_and_rejects_literal_mot_artifacts(self):
        fit = yearly_rows().iloc[:-2].reset_index(drop=True)
        fit["mgmt_rec"] = np.where(fit.item_no.eq("1"), "MOT", "FOR")
        fit.loc[fit.index % 3 == 0, "mgmt_rec"] = "AVSTÅ"
        history, _ = vote_features.features(fit.drop(columns="nbim_vote"), vectors(len(fit)), fit, vectors(len(fit)), target="against_board")
        state = vote_learner.fit(vote_learner.CONFIGS[0], fit, history, vectors(len(fit)), target="against_board")
        query = yearly_rows().iloc[[-2]].copy()
        query["nbim_vote"], query["actual_disagreement"] = "DO_NOT_READ", "DO_NOT_READ"
        query["score"], query["threshold"], query["prediction"], query["error"] = "unused", .5, "unused", "unused"
        expected = float(vote_learner.predict(state, query.drop(columns="nbim_vote"), history[-1:], vectors(1))[0])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            query.to_csv(path / "calibration.csv", index=False)
            np.savez_compressed(path / "calibration-inputs.npz", history=history[-1:], vectors=vectors(1))
            joblib.dump(state, path / "learner.joblib")
            summary = {"selected_threshold": .5, "artifacts": {item.name: experiment.digest(item) for item in path.iterdir()}}
            (path / "summary.json").write_text(json.dumps(summary))
            before = {str(item): item.read_bytes() for item in path.iterdir()}
            replayed = experiment.predict(path, "2024", "1")
            self.assertEqual(replayed["score"], expected)
            self.assertEqual(replayed["target"], "against_board")
            self.assertIsNone(replayed["vote_recommendation"])
            self.assertEqual(before, {str(item): item.read_bytes() for item in path.iterdir()})
            state["target"] = "mot"
            joblib.dump(state, path / "learner.joblib")
            summary["artifacts"]["learner.joblib"] = experiment.digest(path / "learner.joblib")
            (path / "summary.json").write_text(json.dumps(summary))
            with self.assertRaisesRegex(ValueError, "not a board-disagreement model"):
                experiment.predict(path, "2024", "1")


if __name__ == "__main__":
    unittest.main()
