"""F1 selection, frozen-cache provenance, and use of the new decision threshold."""
import itertools
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import joblib
import numpy as np
import pandas as pd

import f1_experiment as experiment
from rag_eval import fingerprint
from vector_experiment import FIELDS, digest


def row(item="1", date="2024-02-01", vote="MOT"):
    return {"meeting_id": "meeting-" + date, "item_no": item, "company_id": "company", "meeting_date": date,
            "company": "Example", "proposal_text": "Elect Director Example Person", "mgmt_rec": "FOR",
            "proponent": "Management", "nbim_vote": vote}


def brute_force(labels, scores):
    candidates = []
    for threshold in sorted({float(value) for value in scores if value is not None and np.isfinite(value)}):
        predicted = [value is not None and np.isfinite(value) and value >= threshold for value in scores]
        tp = sum(bool(y) and bool(p) for y, p in zip(labels, predicted))
        fp = sum(not bool(y) and bool(p) for y, p in zip(labels, predicted))
        fn = sum(bool(y) and not bool(p) for y, p in zip(labels, predicted))
        precision = tp / (tp + fp)
        f1 = 2 * tp / (2 * tp + fp + fn)
        candidates.append((f1, precision, threshold, tp, fp, fn))
    return max(candidates)


class F1Selection(unittest.TestCase):
    def test_all_score_ties_match_independent_brute_force(self):
        # Several thousand tied-score/label combinations also test stable grouping.
        for labels in itertools.product((False, True), repeat=4):
            if not any(labels):
                continue
            for scores in itertools.product((.1, .4, .9), repeat=4):
                expected = brute_force(labels, scores)
                actual = experiment.best_f1(labels, scores)
                self.assertEqual(actual["threshold"], expected[2])
                self.assertAlmostEqual(actual["metrics"]["f1"], expected[0])
                self.assertEqual((actual["metrics"]["tp"], actual["metrics"]["fp"], actual["metrics"]["fn"]), expected[3:])

    def test_missing_scores_remain_in_recall_and_coverage_denominators(self):
        result = experiment.best_f1([True, True, False, False], [.8, None, .1, float("nan")])
        self.assertEqual(result["threshold"], .8)
        self.assertEqual(result["metrics"]["fn"], 1)
        self.assertEqual(result["metrics"]["recall"], .5)
        self.assertEqual(result["metrics"]["recommendation_coverage"], .5)

    def test_invalid_or_unidentifiable_selection_is_rejected(self):
        for labels, scores in (([], []), ([False, False], [.1, .2]), ([True], [None]),
                               ([True, False], [.1]), ([2, 0], [.1, .2]), ([[True]], [[.1]])):
            with self.subTest(labels=labels, scores=scores), self.assertRaises((ValueError, TypeError)):
                experiment.best_f1(labels, scores)

    def test_model_ties_use_declared_order_not_incomparable_threshold_scale(self):
        frame = pd.DataFrame([row("1", "2020-02-01", "MOT"), row("2", "2020-02-01", "FOR")])
        frame["first"] = [.2, .1]
        frame["second"] = [.9, .8]
        configs = [{"name": "first"}, {"name": "second"}]
        candidates = experiment.rank_candidates(frame, configs)
        self.assertEqual([c["config"]["name"] for c in candidates], ["first", "second"])
        self.assertEqual(candidates[0]["validation_per_year"][0]["year"], 2020)
        self.assertEqual(candidates[0]["validation"]["f1"], 1.0)


class F1Artifacts(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)

    def test_compatibility_allows_unrelated_reporting_but_rejects_used_function_change(self):
        source = "SOURCE = ROOT / 'data/real_votes.csv'\nTARGET = 'against_board'\ndef measure(a): return a\ndef load_temporal(a): return a\ndef sizes(a): return len(a)\ndef run(): return 'old report'\n"
        archived, current = self.base / "old.py", self.base / "new.py"
        archived.write_text(source)
        current.write_text(source.replace("'old report'", "'new report'"))
        self.assertTrue(experiment.same_board_dependencies(archived, current))
        current.write_text(source.replace("return len(a)", "return len(a) + 1"))
        self.assertFalse(experiment.same_board_dependencies(archived, current))
        current.write_text(source.replace("TARGET = 'against_board'", "TARGET = 'mot'"))
        self.assertFalse(experiment.same_board_dependencies(archived, current))
        current.write_text("import replacement_module as metrics\n" + source)
        self.assertFalse(experiment.same_board_dependencies(archived, current))

    def test_previous_artifacts_and_target_must_match(self):
        for name in experiment.REQUIRED_PREVIOUS:
            (self.base / name).write_bytes(b"original")
        summary = {"target": "against_board", "artifacts": {name: digest(self.base / name) for name in experiment.REQUIRED_PREVIOUS}, "source_hashes": {}}
        path = self.base / "summary.json"
        path.write_text(json.dumps(summary))
        self.assertEqual(experiment.validate_previous(self.base), summary)
        (self.base / "validation.csv").write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "Artifact changed"):
            experiment.validate_previous(self.base)
        summary["target"] = "mot"
        path.write_text(json.dumps(summary))
        with self.assertRaisesRegex(ValueError, "required target"):
            experiment.validate_previous(self.base)

    def test_path_escape_and_missing_manifest_entries_are_rejected(self):
        outside = self.base.parent / (self.base.name + "-outside")
        outside.write_text("outside")
        self.addCleanup(outside.unlink)
        with self.assertRaisesRegex(ValueError, "unsafe"):
            experiment.checked_path(self.base, "../" + outside.name, digest(outside))
        (self.base / "summary.json").write_text(json.dumps({"target": "against_board", "artifacts": {}, "source_hashes": {}}))
        with self.assertRaisesRegex(ValueError, "required"):
            experiment.validate_previous(self.base)

    def test_cohort_validation_rejects_new_years_changed_labels_and_meeting_overlap(self):
        fit = pd.DataFrame([row(date="2020-02-01")])
        expected = pd.DataFrame([row(date="2024-02-01")])
        validation, calibration = fit.copy(), expected.copy()
        validation["actual_disagreement"] = True
        calibration["actual_disagreement"] = True
        experiment.check_cohorts(validation, calibration, fit, expected)
        bad = validation.copy()
        bad["actual_disagreement"] = False
        with self.assertRaisesRegex(ValueError, "disagreement labels"):
            experiment.check_cohorts(bad, calibration, fit, expected)
        bad = calibration.copy()
        bad["meeting_date"] = "2026-10-01"
        with self.assertRaisesRegex(ValueError, "cohort"):
            experiment.check_cohorts(validation, bad, fit, expected)
        bad_expected, bad_calibration = expected.copy(), calibration.copy()
        bad_expected["meeting_id"] = bad_calibration["meeting_id"] = fit.meeting_id.iloc[0]
        with self.assertRaisesRegex(ValueError, "Meeting overlap"):
            experiment.check_cohorts(validation, bad_calibration, fit, bad_expected)

    def test_reuse_rejects_wrong_winner_or_wrong_saved_target(self):
        config = {"name": "one", "kind": "boost"}
        source = self.base / "learner.joblib"
        joblib.dump({"target": "against_board", "config": config}, source)
        old = {"selected_config": config, "artifacts": {"learner.joblib": digest(source)}}
        output = self.base / "output"
        output.mkdir()
        with self.assertRaisesRegex(ValueError, "selected another model"):
            experiment.reuse_learner(self.base, old, {"name": "other"}, output)
        self.assertFalse((output / "learner.joblib").exists())
        self.assertEqual(experiment.reuse_learner(self.base, old, config, output), digest(source))
        self.assertEqual((output / "learner.joblib").read_bytes(), source.read_bytes())
        joblib.dump({"target": "mot", "config": config}, source)
        old["artifacts"]["learner.joblib"] = digest(source)
        with self.assertRaisesRegex(ValueError, "target/configuration"):
            experiment.reuse_learner(self.base, old, config, output)

    def test_predict_uses_new_threshold_and_input_excludes_fresh_label_columns(self):
        config = {"name": "test"}
        frame = pd.DataFrame([{**row(), "actual_disagreement": True, "score": .23,
                               "threshold": .24, "prediction": "WITH_BOARD", "error": "FN"}])
        frame.to_csv(self.base / "calibration.csv", index=False)
        np.savez(self.base / "calibration-inputs.npz", history=np.zeros((1, 59)), vectors=np.ones((1, 384)))
        joblib.dump({"target": "against_board", "config": config}, self.base / "learner.joblib")
        names = ["calibration.csv", "calibration-inputs.npz", "learner.joblib"]
        summary = {"target": "against_board", "objective": "maximize_f1", "selected_config": config,
                   "selected_threshold": .24, "artifacts": {name: digest(self.base / name) for name in names}, "source_hashes": {}}
        summary["record_id"] = fingerprint(summary)
        (self.base / "summary.json").write_text(json.dumps(summary))
        with patch.object(experiment.vote_learner, "predict", return_value=np.array([.23])) as predict:
            result = experiment.predict(self.base, row()["meeting_id"], "1")
        self.assertEqual(result["threshold"], .24)
        self.assertEqual(result["prediction"], "WITH_BOARD")
        self.assertEqual(set(predict.call_args.args[1].columns), set(FIELDS) - {"nbim_vote"})
        summary["selected_threshold"] = .22
        (self.base / "summary.json").write_text(json.dumps(summary))
        with self.assertRaisesRegex(ValueError, "summary changed"):
            experiment.predict(self.base, row()["meeting_id"], "1")


if __name__ == "__main__":
    unittest.main()
