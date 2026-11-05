"""Target semantics, leakage protection and backwards-compatible local learners."""
import unittest

import numpy as np
import pandas as pd

import vote_features
import vote_learner
from vote_targets import known_target, target_labels


def row(meeting="a", date="2020-01-01", nbim="MOT", board="FOR"):
    return {"meeting_id": meeting, "item_no": "1", "company_id": "company-a", "company": "Company A",
            "meeting_date": date, "proposal_text": "Elect Ada Example as Director", "mgmt_rec": board,
            "proponent": "Management", "nbim_vote": nbim}


def vectors(count):
    result = np.zeros((count, 384), dtype=np.float32)
    result[:, 0] = 1
    return result


class VoteTargetTests(unittest.TestCase):
    def test_against_board_is_known_inequality_in_both_directions_and_includes_abstentions(self):
        pairs = [("MOT", "FOR", True), ("FOR", "MOT", True), ("MOT", "MOT", False),
                 ("FOR", "FOR", False), ("AVSTÅ", "FOR", True), ("FOR", "AVSTÅ", True),
                 ("AVSTÅ", "MOT", True), ("MOT", "AVSTÅ", True), ("AVSTÅ", "AVSTÅ", False)]
        frame = pd.DataFrame([row(str(i), nbim=nbim, board=board) for i, (nbim, board, _) in enumerate(pairs)])
        self.assertTrue(known_target(frame, "against_board").all())
        np.testing.assert_array_equal(target_labels(frame, "against_board"), [expected for _, _, expected in pairs])
        np.testing.assert_array_equal(target_labels(frame), frame.nbim_vote.eq("MOT"))

    def test_missing_votes_are_explicitly_excluded_never_inequality_positives(self):
        frame = pd.DataFrame([row("valid"), row("missing-board", board=""), row("missing-nbim", nbim=""),
                              row("null-board", board=None), row("nan-nbim", nbim=np.nan), row("unknown-board", board="UNKNOWN")],
                             index=[10, 20, 30, 40, 50, 60])
        mask = known_target(frame, "against_board")
        self.assertEqual(mask.index.tolist(), [10, 20, 30, 40, 50, 60])
        self.assertEqual(mask.tolist(), [True, False, False, False, False, False])
        self.assertEqual(known_target(frame).tolist(), [True, True, False, True, False, True])
        with self.assertRaises(ValueError):
            target_labels(frame, "against_board")
        np.testing.assert_array_equal(target_labels(frame.loc[mask], "against_board"), [True])
        with self.assertRaises(ValueError):
            known_target(frame.drop(columns="mgmt_rec"), "against_board")
        with self.assertRaises(ValueError):
            target_labels(frame, "unknown-target")

    def test_features_aggregate_chosen_target_and_keep_actual_reference_votes_intact(self):
        query = pd.DataFrame([row("query", "2024-01-01", nbim="DO_NOT_READ", board="MOT")])
        for nbim, board, expected in (("MOT", "FOR", 1), ("FOR", "MOT", 1), ("MOT", "MOT", 0), ("AVSTÅ", "AVSTÅ", 0)):
            with self.subTest(nbim=nbim, board=board):
                reference = pd.DataFrame([row(nbim=nbim, board=board)])
                original = reference.copy(deep=True)
                H, names = vote_features.features(query.drop(columns="nbim_vote"), vectors(1), reference, vectors(1), target="against_board")
                values = dict(zip(names, H[0]))
                self.assertEqual(values["company_against_board_mean"], expected)
                self.assertEqual(values["exact_company_last_against_board"], expected)
                self.assertEqual(values["semantic_global_top1_against_board_mean"], expected)
                self.assertEqual(values["board_mot"], 1)
                pd.testing.assert_frame_equal(reference, original)
                changed, _ = vote_features.features(query, vectors(1), reference, vectors(1), target="against_board")
                np.testing.assert_allclose(H, changed, equal_nan=True)
        with self.assertRaises(ValueError):
            vote_features.features(query, vectors(1), pd.DataFrame([row(board="")]), vectors(1), target="against_board")

    def test_against_board_history_excludes_cutoff_future_same_meeting_and_same_group(self):
        query = pd.DataFrame([row("query", "2024-01-10")])
        allowed = row("allowed", "2024-01-04", nbim="FOR", board="MOT")
        reference = pd.DataFrame([allowed, row("cutoff", "2024-01-05", nbim="MOT", board="MOT"),
                                  row("future", "2024-01-11", nbim="MOT", board="MOT"),
                                  row("same-group", "2024-01-10", nbim="MOT", board="MOT"),
                                  row("query", "2020-01-01", nbim="MOT", board="MOT")])
        actual, names = vote_features.features(query, vectors(1), reference, vectors(len(reference)), target="against_board")
        expected, _ = vote_features.features(query, vectors(1), reference.iloc[:1], vectors(1), target="against_board")
        np.testing.assert_allclose(actual, expected, equal_nan=True)
        self.assertEqual(actual[0, names.index("company_against_board_mean")], 1)

    def test_feature_names_positions_and_bounded_transform_remain_compatible(self):
        original = vote_features.feature_names()
        changed = vote_features.feature_names("against_board")
        self.assertEqual(original, vote_features.FEATURE_NAMES)
        self.assertEqual(len(set(changed)), 59)
        self.assertIn("top_not_against_board_similarity", changed)
        for before, after in zip(original, changed):
            if before.startswith("board_") or before.endswith("count_log"):
                self.assertEqual(before, after)
            if before.endswith("age_years"):
                self.assertTrue(after.endswith("age_years"))
        H = np.ones((2, 59)) * 10
        bounded = vote_learner.bounded_history(H)
        for index, name in enumerate(changed):
            if name.endswith("count_log") or name.endswith("meetings_log"):
                self.assertEqual(bounded[0, index], np.log1p(50))
            elif name.endswith("age_years"):
                self.assertEqual(bounded[0, index], 3)

    def test_default_feature_values_and_learner_predictions_remain_literal_mot(self):
        frame = pd.DataFrame([row(str(i), nbim="MOT" if i % 2 else "FOR", board="MOT" if i % 3 else "FOR") for i in range(12)])
        query = pd.DataFrame([row("query", "2024-01-01")])
        default, names = vote_features.features(query, vectors(1), frame, vectors(len(frame)))
        explicit, explicit_names = vote_features.features(query, vectors(1), frame, vectors(len(frame)), target="mot")
        np.testing.assert_allclose(default, explicit, equal_nan=True)
        self.assertEqual(names, explicit_names)
        self.assertEqual(default[0, names.index("company_mot_mean")], .5)
        history = np.random.default_rng(41).normal(size=(len(frame), 59))
        config = vote_learner.CONFIGS[0]
        first = vote_learner.fit(config, frame, history, vectors(len(frame)))
        second = vote_learner.fit(config, frame, history, vectors(len(frame)), target="mot")
        self.assertEqual(first["target"], "mot")
        np.testing.assert_allclose(vote_learner.predict(first, frame, history, vectors(len(frame))),
                                   vote_learner.predict(second, frame, history, vectors(len(frame))))
        legacy = {key: value for key, value in first.items() if key not in ("target", "feature_names")}
        np.testing.assert_allclose(vote_learner.predict(first, frame, history, vectors(len(frame))),
                                   vote_learner.predict(legacy, frame, history, vectors(len(frame))))

    def test_against_board_learner_records_target_and_predict_ignores_query_votes(self):
        frame = pd.DataFrame([row(str(i), nbim="FOR" if i % 2 else "MOT", board="MOT") for i in range(12)])
        history = np.zeros((len(frame), 59))
        history[:, 13] = target_labels(frame, "against_board").astype(float)
        state = vote_learner.fit(vote_learner.CONFIGS[0], frame, history, vectors(len(frame)), target="against_board")
        self.assertEqual(state["target"], "against_board")
        self.assertIn("company_against_board_mean", state["feature_names"])
        before = vote_learner.predict(state, frame, history, vectors(len(frame)))
        after = vote_learner.predict(state, frame.drop(columns="nbim_vote"), history, vectors(len(frame)))
        np.testing.assert_allclose(before, after)
        self.assertGreater(before[1], before[0])
        with self.assertRaises(ValueError):
            vote_learner.fit(vote_learner.CONFIGS[0], frame.assign(mgmt_rec=""), history, vectors(len(frame)), target="against_board")
        with self.assertRaises(ValueError):
            vote_learner.predict({**state, "target": "invalid"}, frame, history, vectors(len(frame)))


if __name__ == "__main__":
    unittest.main()
