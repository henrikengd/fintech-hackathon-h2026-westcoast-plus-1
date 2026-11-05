"""Focused checks of target semantics and training-only historical context."""
import boot  # noqa: F401
import unittest
import tempfile
from pathlib import Path
import json

import joblib
import numpy as np
import pandas as pd

from mot_experiment import MotScreen, file_hash, group_folds, history_features, load_development, load_screen, metrics, normalized, select_threshold


def rows():
    return pd.DataFrame([
        {"meeting_id": str(i), "item_no": "1", "company_id": "a", "company": "Example", "meeting_date": day,
         "proposal_text": "Elect Director Ada Example", "mgmt_rec": "FOR", "proponent": "Management", "nbim_vote": vote}
        for i, (day, vote) in enumerate((("2020-01-01", "MOT"), ("2020-01-05", "FOR"), ("2021-01-01", "FOR")))
    ])


class MotExperiment(unittest.TestCase):
    def test_history_excludes_current_future_and_disallowed_validation_rows(self):
        frame = normalized(rows())
        record = frame.iloc[[0, 2]]
        features = history_features(frame, record)
        np.testing.assert_array_equal(features[0], np.zeros(7))
        np.testing.assert_array_equal(features[1], np.zeros(7))
        self.assertEqual(features[2, 1], 1.0)
        self.assertEqual(features[2, 3], 1.0)
        changed = record.copy()
        changed.loc[2, "mot"] = 1
        np.testing.assert_array_equal(features, history_features(frame, changed))
        np.testing.assert_array_equal(history_features(frame, frame.iloc[[2]]), np.zeros((3, 7)))

    def test_literal_mot_scores_do_not_mean_disagreement_with_board(self):
        result = metrics([1, 1, 0, 0], [1.0, 0.0, 1.0, 0.0])
        self.assertEqual((result["tp"], result["fp"], result["fn"], result["tn"]), (1, 1, 1, 1))
        self.assertEqual(result["precision"], .5)
        self.assertEqual(result["recall"], .5)
        self.assertEqual(result["f1"], .5)
        self.assertIsNone(metrics([1, 0], [0.0, 0.0])["precision"])

    def test_threshold_optimizes_f1_with_explicit_precision_constraint(self):
        target, score = [1, 0, 1, 0], [.9, .8, .7, .1]
        threshold = select_threshold(target, score)
        self.assertEqual(threshold, .7)
        self.assertEqual(metrics(target, score, threshold)["f1"], .8)
        self.assertEqual(select_threshold(target, score, minimum_precision=.9), .9)

    def test_grouped_folds_cover_each_proposal_once_without_meeting_overlap(self):
        frames = []
        for i in range(20):
            meeting = rows().iloc[:2].copy()
            meeting["company_id"] = str(i)
            meeting["meeting_date"] = f"2020-02-{i+1:02d}"
            meeting["meeting_id"] = [f"{i}a", f"{i}b"]
            frames.append(meeting)
        data = normalized(pd.concat(frames, ignore_index=True))
        folds = group_folds(data)
        checked = []
        for fit, check in folds:
            a = set(map(tuple, data.iloc[fit][["company_id", "meeting_date"]].values))
            b = set(map(tuple, data.iloc[check][["company_id", "meeting_date"]].values))
            self.assertFalse(a & b)
            checked.extend(check)
        self.assertEqual(sorted(checked), list(range(len(data))))

    def test_saved_components_load_outside_the_training_cli(self):
        frame = normalized(rows())
        model = MotScreen("word").fit(frame)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "screen.joblib"
            joblib.dump({"variant": "word", "components": model.__dict__, "threshold": .6}, path)
            restored, threshold = load_screen(path)
        self.assertEqual(threshold, .6)
        np.testing.assert_allclose(model.score(frame, frame), restored.score(frame, frame))

    def test_loader_excludes_reserved_groups_unknown_votes_and_later_years(self):
        source = rows()
        development = source.iloc[[0]].assign(meeting_id="dev", meeting_date="2024-05-01")
        later = source.iloc[[0]].assign(meeting_id="future", meeting_date="2025-05-01", nbim_vote="DO_NOT_SCORE")
        unknown = source.iloc[[0]].assign(meeting_id="unknown", meeting_date="2024-04-01", nbim_vote="")
        reserved = source.iloc[[0]].assign(meeting_id="reserved", meeting_date="2024-06-01", nbim_vote="DO_NOT_READ")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            pd.concat([source, development, later, unknown]).to_csv(root / "train.csv", index=False)
            reserved.to_csv(root / "test.csv", index=False)
            manifest = {"dataset_id": "fixture", "source_sha256": "source", "files": {name: file_hash(root / name) for name in ("train.csv", "test.csv")}}
            (root / "manifest.json").write_text(json.dumps(manifest))
            fit, check, info = load_development(root)
            self.assertEqual(set(fit["meeting_id"]), {"0", "1", "2"})
            self.assertEqual(list(check["meeting_id"]), ["dev"])
            self.assertEqual(info["unscored_missing_vote"], 1)


if __name__ == "__main__":
    unittest.main()
