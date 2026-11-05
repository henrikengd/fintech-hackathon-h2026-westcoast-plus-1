"""Offline checks of strict operating targets, temporal isolation and saved learners."""
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

import vote_experiment as experiment
import vote_features
import vote_learner
from test_vector_experiment import row, vectors, yearly_rows


class VoteExperimentTests(unittest.TestCase):
    def test_operating_targets_are_strictly_above_eighty_five_percent(self):
        at_precision_boundary = experiment.threshold_options([True] * 17 + [False] * 3, [.5] * 20)
        self.assertEqual(at_precision_boundary["balanced"]["validation"]["precision"], .85)
        self.assertIsNone(at_precision_boundary["precision"]["threshold"])
        self.assertEqual(at_precision_boundary["recall"]["validation"]["recall"], 1)
        at_recall_boundary = experiment.threshold_options([True] * 20 + [False], [.9] * 17 + [None] * 3 + [.1])
        self.assertEqual(at_recall_boundary["balanced"]["validation"]["recall"], .85)
        self.assertIsNone(at_recall_boundary["recall"]["threshold"])
        self.assertEqual(at_recall_boundary["precision"]["validation"]["precision"], 1)

    def test_missing_positive_scores_remain_false_negatives_in_every_operating_point(self):
        options = experiment.threshold_options([True, True, False], [None, 0, 0])
        measured = options["balanced"]["validation"]
        self.assertEqual(options["balanced"]["threshold"], 0)
        self.assertEqual((measured["tp"], measured["fp"], measured["fn"], measured["tn"]), (1, 1, 1, 0))
        self.assertEqual(measured["recall"], .5)
        self.assertEqual(measured["uncovered"], 1)
        self.assertIsNone(options["precision"]["threshold"])
        self.assertIsNone(options["recall"]["threshold"])

    def test_ties_are_indivisible_and_balanced_selection_maximizes_worst_metric(self):
        options = experiment.threshold_options([True, False, True, False], [.9, .9, .2, .2])
        self.assertEqual(options["balanced"]["threshold"], .2)
        self.assertEqual(options["balanced"]["validation"]["predicted_mot"], 4)
        # Both thresholds have min(P,R)=.5; F1 favors taking both positive cases.
        self.assertAlmostEqual(options["balanced"]["validation"]["f1"], 2 / 3)
        self.assertIsNone(options["precision"]["threshold"])
        for labels, scores in (([True], []), ([False], [.5]), ([True], [None])):
            with self.subTest(labels=labels, scores=scores), self.assertRaises(ValueError):
                experiment.threshold_options(labels, scores)
        for target in (0, 1, -1, np.nan):
            with self.subTest(target=target), self.assertRaises(ValueError):
                experiment.threshold_options([True, False], [.9, .1], target)

    def test_precomputed_training_history_matches_fold_only_references(self):
        fit = yearly_rows().iloc[:-2].reset_index(drop=True)
        embedded = vectors(len(fit))
        all_history, names = vote_features.features(fit, embedded, fit, embedded)
        for year, train, check in experiment.forward_folds(fit):
            folded, folded_names = vote_features.features(fit.iloc[train], embedded[train], fit.iloc[train], embedded[train])
            self.assertEqual(names, folded_names)
            np.testing.assert_allclose(all_history[train], folded, equal_nan=True)
            changed = fit.copy()
            changed.loc[changed.meeting_date.ge(f"{year}-01-01"), "nbim_vote"] = "MOT"
            changed_history, _ = vote_features.features(fit.iloc[train], embedded[train], changed, embedded)
            np.testing.assert_allclose(all_history[train], changed_history, equal_nan=True)
            # Validation may read previous years, but its own labels are never inputs.
            query = fit.iloc[check].copy()
            before, _ = vote_features.features(query, embedded[check], fit.iloc[train], embedded[train])
            query["nbim_vote"] = "DO_NOT_READ"
            query["rationale_text"] = "DO_NOT_READ"
            after, _ = vote_features.features(query, embedded[check], fit.iloc[train], embedded[train])
            np.testing.assert_allclose(before, after, equal_nan=True)

    def test_warmup_is_reference_history_but_never_supervised_training(self):
        frame = yearly_rows().iloc[:-2].reset_index(drop=True)
        eligible, folds = experiment.learning_folds(frame)
        self.assertEqual(set(frame.iloc[eligible].meeting_date.str[:4]), {"2020", "2021", "2022", "2023"})
        self.assertEqual([year for year, _, _, _ in folds], [2021, 2022, 2023])
        for year, train, reference, check in folds:
            self.assertTrue(frame.iloc[train].meeting_date.gt("2019-12-31").all())
            self.assertTrue(frame.iloc[reference].meeting_date.lt(f"{year}-01-01").all())
            self.assertTrue(set(train).issubset(reference))
            self.assertEqual(set(reference) - set(train), {0, 1})
            self.assertEqual(set(frame.iloc[check].meeting_date.str[:4]), {str(year)})
            self.assertFalse(set(reference) & set(check))
        all_rows, original = experiment.learning_folds(frame, warmup_year=None)
        self.assertEqual(all_rows.tolist(), list(range(len(frame))))
        self.assertEqual([year for year, _, _, _ in original], [2020, 2021, 2022, 2023])
        for _, train, reference, _ in original:
            np.testing.assert_array_equal(train, reference)
        with self.assertRaisesRegex(ValueError, "No supervised years"):
            experiment.learning_folds(frame, warmup_year=2023)

    def test_bounded_history_caps_counts_and_age_without_mutating_or_imputing(self):
        history = np.zeros((2, len(vote_features.FEATURE_NAMES)))
        count = vote_features.FEATURE_NAMES.index("company_count_log")
        meetings = vote_features.FEATURE_NAMES.index("company_meetings_log")
        age = vote_features.FEATURE_NAMES.index("company_latest_age_years")
        mean = vote_features.FEATURE_NAMES.index("company_mot_mean")
        history[:, [count, meetings]] = [[np.log1p(500), np.log1p(100)], [np.log1p(3), np.nan]]
        history[:, age] = [8, np.nan]
        history[:, mean] = [.7, np.nan]
        original = history.copy()
        bounded = vote_learner.bounded_history(history)
        np.testing.assert_array_equal(history, original)
        np.testing.assert_allclose(bounded[0, [count, meetings]], np.log1p(50))
        self.assertEqual(bounded[0, age], 3)
        self.assertEqual(bounded[1, count], np.log1p(3))
        np.testing.assert_array_equal(bounded[:, mean], history[:, mean])
        self.assertTrue(np.isnan(bounded[1, [meetings, age, mean]]).all())
        with self.assertRaisesRegex(ValueError, "declared historical feature columns"):
            vote_learner.bounded_history(np.zeros((2, 4)))

    def test_run_locks_plan_and_selection_before_development_and_ignores_its_labels(self):
        frame = yearly_rows()
        fit, original_dev = frame.iloc[:-2].reset_index(drop=True), frame.iloc[-2:].reset_index(drop=True)
        selections = []
        with tempfile.TemporaryDirectory() as folder:
            for version in range(2):
                output = Path(folder) / str(version)
                dev = original_dev.copy()
                if version:
                    dev["nbim_vote"] = ["FOR", "MOT"]
                calls = {"fit": 0, "development": 0, "thresholds": 0}
                real_options = experiment.threshold_options

                def fake_features(query, embedded, reference, reference_vectors):
                    self.assertTrue((output / "plan.json").exists())
                    self.assertTrue(reference.meeting_date.lt("2024-01-01").all())
                    return np.zeros((len(query), 2)), ["fixture_a", "fixture_b"]

                def fake_fit(config, training, history, embedded):
                    calls["fit"] += 1
                    self.assertTrue(training.meeting_date.lt("2024-01-01").all())
                    return {"config": config, "latest_training": training.meeting_date.max()}

                def fake_predict(model, query, history, embedded):
                    self.assertLess(model["latest_training"], query.meeting_date.min())
                    if query.meeting_date.str.startswith("2024").any():
                        self.assertTrue((output / "selection.json").exists())
                        self.assertEqual(calls["thresholds"], len(vote_learner.CONFIGS))
                        calls["development"] += 1
                    # The first two configurations tie; declared order must choose the first.
                    good = model["config"]["name"] in [config["name"] for config in vote_learner.CONFIGS[:2]]
                    return np.asarray([(.9 if item == "1" else .1) if good else .5 for item in query.item_no])

                def checked_options(labels, scores):
                    self.assertEqual(labels.tolist(), fit.iloc[2:].nbim_vote.eq("MOT").tolist())
                    calls["thresholds"] += 1
                    return real_options(labels, scores)

                with patch.object(experiment, "load_development", return_value=(fit, dev, {"dataset_id": "fixture"})), \
                        patch.object(experiment, "embedding_matrix", return_value=(vectors(len(frame)), {})), \
                        patch.object(vote_features, "features", side_effect=fake_features), \
                        patch.object(vote_learner, "fit", side_effect=fake_fit), \
                        patch.object(vote_learner, "predict", side_effect=fake_predict), \
                        patch.object(experiment, "threshold_options", side_effect=checked_options), \
                        patch.object(experiment, "old_vector_reference", return_value=None), \
                        patch.object(experiment, "old_text_reference", return_value=None), \
                        patch.object(experiment, "cached_reference", return_value=None), redirect_stdout(io.StringIO()):
                    summary = experiment.run(output=output, warmup_year=None)
                self.assertEqual(calls["fit"], 4 * len(vote_learner.CONFIGS) + 1)
                self.assertEqual(calls["development"], 1)
                self.assertEqual(summary["selected_config"], vote_learner.CONFIGS[0])
                self.assertEqual(summary["development_selected"]["recall"], 1 if version == 0 else 0)
                selections.append(json.loads((output / "selection.json").read_text()))
            self.assertEqual(selections[0], selections[1])

    def test_all_declared_learners_fit_and_ignore_query_labels(self):
        frame = pd.DataFrame([row(str(i), 2020, "MOT" if i % 2 else "FOR", str(i % 2 + 1)) for i in range(30)])
        history = np.random.default_rng(41).normal(size=(len(frame), len(vote_features.FEATURE_NAMES)))
        history[:3, 0] = np.nan
        embedded = vectors(len(frame))
        query = frame.iloc[:2].copy()
        query["nbim_vote"] = "DO_NOT_READ"
        query["rationale_text"] = "DO_NOT_READ"
        for config in vote_learner.CONFIGS:
            with self.subTest(config=config["name"]):
                model = vote_learner.fit(config, frame, history, embedded)
                # Parallel tree summation can vary at 1e-16. Keep this strict
                # label-invariance check deterministic without changing learners.
                if hasattr(model["model"], "n_jobs"):
                    model["model"].n_jobs = 1
                expected = vote_learner.predict(model, frame.iloc[:2], history[:2], embedded[:2])
                changed = vote_learner.predict(model, query, history[:2], embedded[:2])
                np.testing.assert_array_equal(expected, changed)
                self.assertTrue(np.isfinite(expected).all())
                self.assertTrue(((expected >= 0) & (expected <= 1)).all())

    def test_legacy_learners_preserve_identity_preprocessing_and_reject_unknown_versions(self):
        frame = yearly_rows().iloc[:-2].reset_index(drop=True)
        frame["nbim_vote"] = np.where(np.arange(len(frame)) < 5, "FOR", "MOT")
        history = np.zeros((len(frame), len(vote_features.FEATURE_NAMES)))
        history[:, vote_features.FEATURE_NAMES.index("company_count_log")] = np.arange(len(frame))
        embedded = vectors(len(frame))
        # Recreate a v1 state trained on raw history, before preprocessing was versioned.
        with patch.object(vote_learner, "bounded_history", side_effect=lambda values: np.array(values, copy=True)):
            legacy = vote_learner.fit(vote_learner.CONFIGS[0], frame, history, embedded)
        self.assertEqual(legacy.pop("history_transform"), "capped-counts-50-ages-3-v1")
        query, inputs = frame.iloc[-2:], history[-2:]
        expected = legacy["model"].predict_proba(legacy["numeric"].transform(inputs))[:, 1]
        actual = vote_learner.predict(legacy, query, inputs, embedded[-2:])
        np.testing.assert_array_equal(actual, expected)
        explicitly_raw = vote_learner.predict({**legacy, "history_transform": "identity"}, query, inputs, embedded[-2:])
        np.testing.assert_array_equal(explicitly_raw, expected)
        wrongly_capped = vote_learner.predict({**legacy, "history_transform": "capped-counts-50-ages-3-v1"},
                                             query, inputs, embedded[-2:])
        self.assertFalse(np.allclose(wrongly_capped, expected))
        with self.assertRaisesRegex(ValueError, "Unknown historical preprocessing version"):
            vote_learner.predict({**legacy, "history_transform": "future-unknown"}, query, inputs, embedded[-2:])

    def test_saved_learner_reloads_without_label_input_and_checks_artifact_hashes(self):
        frame = yearly_rows().iloc[:-2].reset_index(drop=True)
        embedded = vectors(len(frame))
        history = np.zeros((len(frame), len(vote_features.FEATURE_NAMES)))
        history[:, :2] = np.column_stack([np.arange(len(frame)), np.tile([0, 1], len(frame) // 2)])
        model = vote_learner.fit(vote_learner.CONFIGS[0], frame, history, embedded)
        query = yearly_rows().iloc[[-2]].copy()
        query["nbim_vote"] = "DO_NOT_READ"
        query["score"], query["threshold"], query["prediction"], query["error"] = "unused", .5, "unused", "unused"
        expected = float(vote_learner.predict(model, query, history[:1], embedded[:1])[0])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            query.to_csv(path / "development.csv", index=False)
            np.savez_compressed(path / "development-inputs.npz", history=history[:1], vectors=embedded[:1])
            joblib.dump(model, path / "learner.joblib")
            summary = {"selected_threshold": .5, "artifacts": {
                str(item.relative_to(path)): experiment.digest(item) for item in path.iterdir()}}
            (path / "summary.json").write_text(json.dumps(summary))
            before = {str(item): item.read_bytes() for item in path.iterdir()}
            with patch.object(experiment, "embedding_matrix", side_effect=AssertionError("No embedding calls")):
                restored = experiment.predict(path, "2024", "1")
            self.assertEqual(restored["score"], expected)
            self.assertEqual(restored["api_calls"], 0)
            self.assertEqual(before, {str(item): item.read_bytes() for item in path.iterdir()})
            with (path / "learner.joblib").open("ab") as handle:
                handle.write(b"changed")
            with self.assertRaisesRegex(ValueError, "Saved artifact changed"):
                experiment.predict(path, "2024", "1")


if __name__ == "__main__":
    unittest.main()
