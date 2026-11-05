"""Offline regression and isolation tests for frozen fresh-cohort adapters."""
import copy
import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import numpy as np
import pandas as pd

import claude_board_context as old
import fresh_inference as fresh
import vote_features
from vector_model import META_FIELDS


def row(mid, day, company="c1", vote="FOR", board="FOR", item="1"):
    return {"meeting_id": mid, "item_no": item, "company_id": company, "company": company,
            "meeting_date": day, "proposal_text": "Elect Ada Example as Director",
            "proponent": "Management", "mgmt_rec": board, "nbim_vote": vote}


def vectors(n):
    matrix = np.zeros((n, 384), dtype=np.float32)
    matrix[:, 0] = 1
    return matrix


def query(records):
    return pd.DataFrame(records)[META_FIELDS]


class FreshInferenceTests(unittest.TestCase):
    def setUp(self):
        self.reference = pd.DataFrame([row("history", "2023-01-01", vote="MOT")])
        self.query = query([row("fresh", "2026-10-10")])

    def bundle(self, reference=None, current=None):
        reference = self.reference if reference is None else reference
        current = self.query if current is None else current
        return fresh.build_bundles(reference, current, vectors(len(reference)), vectors(len(current)))[0]

    def reply(self, bundle, vote="MOT"):
        return {"stop_reason": "end_turn", "model": "claude-sonnet-5-5",
                "usage": {"input_tokens": 20, "output_tokens": 10},
                "content": [{"type": "text", "text": json.dumps({"items": [{"item": p["item"], "vote": vote,
                    "why": "Earlier votes are similar.", "history_ids": p["history_ids"][:1]} for p in bundle["proposals"]]})}]}

    def test_exact_old_2024_bundle_and_generation_settings(self):
        fit = pd.DataFrame([row(f"old-{i:02d}", f"2023-02-{i+1:02d}", company=f"c{i%3}") for i in range(25)])
        cal = pd.DataFrame([row("query", "2024-04-01", item="1"), row("query", "2024-04-01", item="2")])
        matrix = np.random.default_rng(17).normal(size=(len(fit) + len(cal), 384)).astype(np.float32)
        original = old.build_bundles(fit, cal, matrix)
        actual = fresh.build_bundles(pd.concat([fit, cal], ignore_index=True), cal[META_FIELDS], matrix, matrix[len(fit):])
        self.assertEqual(actual, original)
        self.assertEqual(fresh.SYSTEM, old.SYSTEM)
        self.assertEqual(fresh.Drafts.model_json_schema(), old.Drafts.model_json_schema())
        client = SimpleNamespace(messages=SimpleNamespace(create=Mock(return_value=SimpleNamespace(model_dump=lambda: self.reply(actual[0])))))
        fresh.generate_review(actual[0], client, model="claude-sonnet-5-5", effort="medium")
        params = client.messages.create.call_args.kwargs
        self.assertEqual(params["system"], old.SYSTEM)
        self.assertEqual(params["max_tokens"], 1000 + 220 * len(cal))
        self.assertEqual(params["output_config"]["effort"], "medium")
        self.assertEqual(json.loads(params["messages"][0]["content"]), actual[0])
        self.assertNotIn("tools", params)

    def test_entire_query_cohort_and_company_date_aliases_are_excluded(self):
        current = query([row("early-test", "2026-08-01"), row("later-test", "2026-10-10")])
        reference = pd.DataFrame([row("past", "2026-07-01"), row("early-test", "2026-08-01", vote="SECRET"),
                                  row("alias", "2026-08-01", vote="SECRET"), row("later-test", "2026-10-10", vote="SECRET")])
        bundles = fresh.build_bundles(reference, current, vectors(len(reference)), vectors(len(current)))
        for bundle in bundles:
            self.assertEqual([r["meeting_id"] for r in bundle["history"]], ["past"])
            self.assertNotIn("SECRET", json.dumps(bundle))

    def test_exact_cutoff_future_and_own_meeting_are_excluded(self):
        reference = pd.DataFrame([row("allowed", "2026-10-04"), row("cutoff", "2026-10-05"),
                                  row("future", "2026-10-11"), row("fresh", "2020-01-01")])
        self.assertEqual([r["meeting_id"] for r in self.bundle(reference)["history"]], ["allowed"])

    def test_no_query_outcome_or_extra_fields_can_reach_context(self):
        for field in ("nbim_vote", "rationale", "proposal_type", "local_score"):
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "allowlist"):
                self.bundle(current=self.query.assign(**{field: "SECRET"}))
        for field in ("nbim_vote", "rationale", "local_score"):
            bundle = self.bundle()
            bundle["proposals"][0][field] = "SECRET"
            with self.assertRaisesRegex(ValueError, "proposal fields"):
                fresh.validate_bundle(bundle)

    def test_reference_permutation_and_label_changes_cannot_change_rankings(self):
        reference = pd.DataFrame([row(f"old-{i:02d}", "2023-01-01", company=f"c{i%3}") for i in range(25)])
        before = self.bundle(reference)
        after = self.bundle(reference.sample(frac=1, random_state=21).reset_index(drop=True))
        self.assertEqual(before, after)
        changed = self.bundle(reference.assign(nbim_vote="MOT"))
        self.assertEqual(before["proposals"], changed["proposals"])

    def test_unknown_board_preserves_vote_but_no_disagreement_target(self):
        bundle = self.bundle(current=self.query.assign(mgmt_rec=""))
        item = fresh.validate_response(bundle, self.reply(bundle, "MOT"))["items"][0]
        self.assertEqual(item["vote"], "MOT")
        self.assertIsNone(item["against_board"])
        for vote, expected in (("FOR", True), ("MOT", False), (None, None)):
            other = copy.deepcopy(bundle)
            other["proposals"][0]["board_recommendation"] = "MOT"
            result = fresh.validate_response(other, self.reply(other, vote))
            self.assertIs(result["items"][0]["against_board"], expected)

    def test_validation_failures_preserve_raw_response_usage_and_category(self):
        bundle = self.bundle()
        cases = []
        incomplete = self.reply(bundle)
        incomplete["stop_reason"] = "max_tokens"
        cases.append((incomplete, "incomplete_response"))
        bad_schema = self.reply(bundle)
        bad_schema["content"][0]["text"] = "not json"
        cases.append((bad_schema, "invalid_response_schema"))
        for change, category in ((lambda draft: draft.update(item="wrong"), "proposal_identity_mismatch"),
                                 (lambda draft: draft.update(history_ids=["invented:1"]), "invalid_history_citation"),
                                 (lambda draft: draft.update(why=""), "empty_explanation")):
            reply = self.reply(bundle)
            parsed = json.loads(reply["content"][0]["text"])
            change(parsed["items"][0])
            reply["content"][0]["text"] = json.dumps(parsed)
            cases.append((reply, category))
        for reply, category in cases:
            with self.subTest(category=category), self.assertRaises(fresh.ReviewValidationError) as caught:
                fresh.validate_response(bundle, reply)
            self.assertEqual(caught.exception.category, category)
            self.assertIs(caught.exception.response, reply)
            self.assertEqual(caught.exception.usage, reply["usage"])
            self.assertEqual(caught.exception.stop_reason, reply["stop_reason"])

    def test_explicit_cohort_checks_detect_injected_earlier_test_history(self):
        bundle = self.bundle()
        mid = bundle["history"][0]["meeting_id"]
        entry = bundle["history"][0]
        with self.assertRaisesRegex(ValueError, "boundaries"):
            fresh.validate_bundle(bundle, forbidden_meetings={mid})
        with self.assertRaisesRegex(ValueError, "boundaries"):
            fresh.validate_bundle(bundle, forbidden_groups={(entry["company_id"], entry["meeting_date"])})

    def state(self):
        return {"target": "against_board", "config": dict(fresh.LOCAL_CONFIG),
                "feature_names": vote_features.feature_names("against_board"),
                "history_transform": "capped-counts-50-ages-3-v1"}

    def test_local_prediction_uses_frozen_features_without_any_fit(self):
        state = self.state()
        expected, names = vote_features.features(self.query, vectors(1), self.reference, vectors(1), target="against_board")
        with patch.object(fresh.vote_learner, "fit", side_effect=AssertionError("Must not fit")), \
             patch.object(fresh.vote_learner, "predict", return_value=np.array([.8])) as predict:
            scores, history, actual_names = fresh.local_predict(state, self.query, vectors(1), self.reference, vectors(1), return_features=True)
        np.testing.assert_equal(scores, [.8])
        np.testing.assert_equal(history, expected)
        self.assertEqual(actual_names, names)
        self.assertIs(predict.call_args.args[0], state)
        self.assertNotIn("nbim_vote", predict.call_args.args[1].columns)
        with patch.object(fresh.vote_learner, "predict", return_value=np.array([.8])):
            score = fresh.local_predict(state, self.query.assign(mgmt_rec=""), vectors(1), self.reference, vectors(1))
        self.assertTrue(np.isnan(score[0]))

    def test_local_rejects_wrong_model_and_cohort_labels_do_not_change_features(self):
        for key, value in (("target", "mot"), ("config", {}), ("feature_names", []), ("history_transform", "identity")):
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "frozen"):
                fresh.local_predict({**self.state(), key: value}, self.query, vectors(1), self.reference, vectors(1))
        current = query([row("early-test", "2026-08-01"), row("fresh", "2026-10-10")])
        reference = pd.concat([self.reference, pd.DataFrame([row("early-test", "2026-08-01", vote="SECRET")])], ignore_index=True)
        with patch.object(fresh.vote_learner, "predict", return_value=np.array([.2, .8])):
            _, before, _ = fresh.local_predict(self.state(), current, vectors(2), reference, vectors(2), return_features=True)
            _, after, _ = fresh.local_predict(self.state(), current, vectors(2), self.reference, vectors(1), return_features=True)
        np.testing.assert_equal(before, after)

    def test_bad_metadata_and_vectors_are_rejected(self):
        for current in (self.query.assign(meeting_date="bad"), self.query.assign(mgmt_rec="AGAINST"),
                        pd.concat([self.query, self.query]), self.query.iloc[:0]):
            with self.assertRaises(ValueError):
                self.bundle(current=current)
        for matrix in (np.zeros((1, 384)), np.ones((1, 383)), np.full((1, 384), np.nan)):
            with self.assertRaises(ValueError):
                fresh.build_bundles(self.reference, self.query, vectors(1), matrix)


if __name__ == "__main__":
    unittest.main()
