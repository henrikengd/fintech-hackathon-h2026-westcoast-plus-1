"""Temporal model selection and deployment of the predeclared hybrid ablation."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

import relevance_experiment as experiment
from vector_experiment import FIELDS
import vote_features


def row(year=2020, item="1", vote="MOT", month="02"):
    return {"meeting_id": f"m-{year}-{month}", "item_no": item, "company_id": "company",
            "meeting_date": f"{year}-{month}-01", "company": "Example", "proposal_text": "Elect Example Person",
            "mgmt_rec": "FOR", "proponent": "Management", "nbim_vote": vote}


def matrix(count):
    result = np.zeros((count, 384))
    result[:, 0] = 1
    return result


class SelectionSafety(unittest.TestCase):
    def test_selection_rejects_calibration_rows_and_missing_candidates(self):
        frame = pd.DataFrame([row(item="1"), row(item="2", vote="FOR")])
        scores = {config["name"]: np.array([.8, .2]) for config in experiment.CONFIGS}
        actual = experiment.selection_rows(frame, scores)
        self.assertEqual(actual[0]["config"], experiment.BASELINE)
        changed = frame.copy()
        changed["meeting_date"] = "2024-02-01"
        with self.assertRaisesRegex(ValueError, "2020–2023"):
            experiment.selection_rows(changed, scores)
        with self.assertRaisesRegex(ValueError, "candidate cohort"):
            experiment.selection_rows(frame, {"one": [.8, .2]})

    def test_audit_rejects_own_meeting_cutoff_future_and_duplicate_identity(self):
        query = pd.DataFrame([row(year=2024)])
        historical = {**row(year=2023), "id": "old:1"}
        valid = [{"meeting_id": query.iloc[0].meeting_id, "item_no": "1", "matches": [historical]}]
        self.assertEqual(experiment.audit_retrieval(query, valid)["temporal_violations"], 0)
        for changed in ({**historical, "meeting_date": "2024-01-27"},
                        {**historical, "meeting_date": "2024-02-02"},
                        {**historical, "meeting_id": query.iloc[0].meeting_id}):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                experiment.audit_retrieval(query, [{**valid[0], "matches": [changed]}])
        with self.assertRaisesRegex(ValueError, "duplicate"):
            experiment.audit_retrieval(query, [{**valid[0], "matches": [historical, historical]}])

    def test_model_fit_uses_training_only_transform_and_checks_prediction_schema(self):
        frame = pd.DataFrame([row(item=str(i), vote="MOT" if i % 2 else "FOR") for i in range(30)])
        history = np.zeros((len(frame), len(vote_features.FEATURE_NAMES)))
        retrieved = np.arange(len(frame), dtype=float)[:, None]
        config = experiment.CONFIGS[-1]
        state = experiment.fit(config, frame, history, retrieved, matrix(len(frame)), ["new_feature"])
        mean_before = state["transform"][1].mean_.copy()
        result = experiment.predict_scores(state, history[:1], np.array([[100000.]]), matrix(1), ["new_feature"])
        self.assertEqual(result.shape, (1,))
        np.testing.assert_array_equal(state["transform"][1].mean_, mean_before)
        with self.assertRaisesRegex(ValueError, "schema"):
            experiment.predict_scores(state, history[:1], np.array([[1.]]), matrix(1), ["another_feature"])
        state["target"] = "mot"
        with self.assertRaisesRegex(ValueError, "target"):
            experiment.predict_scores(state, history[:1], np.array([[1.]]), matrix(1), ["new_feature"])

    def test_input_dimensions_and_nonfinite_values_are_checked(self):
        history = np.zeros((1, len(vote_features.FEATURE_NAMES)))
        for retrieval, embeddings in (([[1.], [2.]], matrix(1)), ([[float("inf")]], matrix(1)), ([[1.]], np.zeros((1, 3)))):
            with self.assertRaises(ValueError):
                experiment.numeric_inputs(history, retrieval, embeddings, True)

    def test_retrieval_call_does_not_receive_current_vote(self):
        query = pd.DataFrame([row(year=2024)])
        reference = pd.DataFrame([row(year=2023)])
        with patch.object(experiment.relevance_retrieval, "HybridHistoryRetriever") as factory, \
                patch.object(experiment.relevance_retrieval, "features_from_results", return_value=(np.zeros((1, 1)), ["new"])):
            retriever = factory.return_value.fit.return_value
            retriever.retrieve.return_value = []
            experiment.retrieve(query, matrix(1), reference, matrix(1))
            self.assertNotIn("nbim_vote", retriever.retrieve.call_args.args[0].columns)
            self.assertIn("nbim_vote", factory.return_value.fit.call_args.args[0].columns)


class WorkflowSafety(unittest.TestCase):
    def test_calibration_labels_cannot_change_model_selection_and_plan_precedes_models(self):
        fit_frame = pd.DataFrame([row(year, item, vote) for year in range(2019, 2024)
                                  for item, vote in (("1", "MOT"), ("2", "FOR"))])
        base_calibration = pd.DataFrame([row(2024, "1", "MOT", "02"), row(2024, "2", "FOR", "03")])
        selected = []
        thresholds = []
        with tempfile.TemporaryDirectory() as directory:
            previous = Path(directory) / "previous"
            previous.mkdir()
            (previous / "summary.json").write_text("{}")
            archived = fit_frame[fit_frame.meeting_date.ge("2020-01-01")].copy()
            archived[experiment.BASELINE["name"]] = .5
            archived.to_csv(previous / "validation.csv", index=False)
            for variant in range(2):
                output = Path(directory) / str(variant)
                calibration = base_calibration.copy()
                if variant:
                    calibration["nbim_vote"] = ["FOR", "MOT"]
                cached_calibration = calibration.copy()
                cached_calibration["score"] = [.4, .3]
                cached_calibration.to_csv(previous / "calibration.csv", index=False)

                def fake_features(query, qvec, reference, rvec, target):
                    self.assertTrue((output / "plan.json").exists())
                    self.assertNotIn("nbim_vote", query)
                    if query.meeting_date.str.startswith("2024").any():
                        self.assertTrue((output / "selection.json").exists())
                    values = np.zeros((len(query), len(vote_features.FEATURE_NAMES)))
                    values[:, 0] = query.item_no.eq("1").to_numpy(dtype=float)
                    return values, vote_features.feature_names(target)

                def fake_retrieve(query, qvec, reference, rvec):
                    self.assertTrue(reference.meeting_date.lt("2025-01-01").all())
                    results = [{"meeting_id": row.meeting_id, "item_no": row.item_no, "matches": []}
                               for row in query.itertuples()]
                    return np.zeros((len(query), 1)), ["new"], results

                def fake_fit(config, frame, history, retrieved, vectors, names):
                    self.assertTrue((output / "plan.json").exists())
                    self.assertTrue(frame.meeting_date.lt("2024-01-01").all())
                    return {"config": config, "target": experiment.TARGET}

                def fake_predict(state, history, retrieved, vectors, names):
                    return np.where(history[:, 0] == 1, .9, .1)

                with patch.object(experiment.f1_experiment, "validate_previous", return_value={"artifacts": {}}), \
                        patch.object(experiment.board_experiment, "load_temporal", return_value=(fit_frame, calibration, {"source_sha256": "fixture"})), \
                        patch.object(experiment, "embedding_matrix", return_value=(matrix(len(fit_frame) + len(calibration)), {})), \
                        patch.object(experiment.vote_features, "features", side_effect=fake_features), \
                        patch.object(experiment, "retrieve", side_effect=fake_retrieve), \
                        patch.object(experiment, "fit", side_effect=fake_fit), \
                        patch.object(experiment, "predict_scores", side_effect=fake_predict), redirect_stdout(io.StringIO()):
                    summary = experiment.run(output, previous)
                selected.append(json.loads((output / "selection.json").read_text())["selected"])
                thresholds.append(summary["selected_threshold"])
                self.assertFalse(summary["test_evaluated"])
                self.assertFalse(summary["october_inputs_used"])
                self.assertEqual(summary["selected_config"], experiment.CONFIGS[1])
                self.assertEqual(summary["calibration"]["rows"], 2)
                self.assertEqual(len(summary["comparisons"]), len(experiment.CONFIGS))
                with self.assertRaisesRegex(ValueError, "Output exists"):
                    experiment.run(output, previous)
            self.assertEqual(selected[0], selected[1])
            self.assertEqual(thresholds, [.9, .1])


if __name__ == "__main__":
    unittest.main()
