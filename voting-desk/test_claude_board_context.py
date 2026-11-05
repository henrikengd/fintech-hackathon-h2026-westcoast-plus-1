"""No-network chronology, retrieval and schema checks for Claude history input."""
import copy
import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

import numpy as np
import pandas as pd

import claude_board_context as context


def row(meeting, day, company="c1", vote="FOR", board="FOR", item="1"):
    return {"meeting_id": meeting, "item_no": item, "company_id": company, "company": company,
            "meeting_date": day, "proposal_text": "Elect Ada Example as Director", "proponent": "Management",
            "mgmt_rec": board, "nbim_vote": vote, "rationale": "SECRET_RATIONALE", "score": "SECRET_LOCAL_SCORE"}


def vectors(n):
    values = np.zeros((n, 384), dtype=np.float32)
    values[:, 0] = 1
    return values


class ClaudeBoardContextTests(unittest.TestCase):
    def setUp(self):
        self.fit = pd.DataFrame([row("fit", "2023-01-01", vote="MOT")])
        self.cal = pd.DataFrame([row("early", "2024-01-01"), row("boundary", "2024-01-05"),
                                 row("query", "2024-01-10"), row("later", "2024-02-01")])

    def build(self, fit=None, cal=None, matrix=None):
        fit = self.fit if fit is None else fit
        cal = self.cal if cal is None else cal
        return context.build_bundles(fit, cal, vectors(len(fit) + len(cal)) if matrix is None else matrix)

    def query(self):
        return next(bundle for bundle in self.build() if bundle["meeting"]["meeting_id"] == "query")

    def reply(self, bundle, vote="MOT"):
        draft = {"item": "1", "vote": vote, "why": "Earlier supplied votes inform this forecast.",
                 "history_ids": bundle["proposals"][0]["history_ids"][:1]}
        return {"stop_reason": "end_turn", "model": "mock", "usage": {"input_tokens": 123, "output_tokens": 45},
                "content": [{"type": "text", "text": json.dumps({"items": [draft]})}]}

    def test_asof_excludes_current_exact_cutoff_and_future(self):
        bundle = self.query()
        self.assertEqual({entry["meeting_id"] for entry in bundle["history"]}, {"fit", "early"})
        self.assertNotIn("SECRET", json.dumps(bundle))
        self.assertNotIn("nbim_vote", bundle["proposals"][0])
        self.assertNotIn("rules", bundle)

    def test_own_and_future_labels_do_not_change_earlier_context(self):
        before = self.query()
        altered = self.cal.copy()
        altered.loc[altered.meeting_id.isin(["boundary", "query", "later"]), "nbim_vote"] = "AVSTÅ"
        after = next(bundle for bundle in self.build(cal=altered) if bundle["meeting"]["meeting_id"] == "query")
        self.assertEqual(before, after)
        # That same known outcome is allowed as context after the lag has passed.
        later = next(bundle for bundle in self.build(cal=altered) if bundle["meeting"]["meeting_id"] == "later")
        self.assertEqual(next(entry["nbim_vote"] for entry in later["history"] if entry["meeting_id"] == "query"), "AVSTÅ")

    def test_selection_is_label_blind_and_deterministic_under_row_permutation(self):
        fit = pd.DataFrame([row(f"fit-{i:02d}", "2023-01-01", company=f"c{i % 3}") for i in range(25)])
        cal = pd.DataFrame([row("query", "2024-01-10")])
        first = self.build(fit, cal)
        shuffled = fit.sample(frac=1, random_state=2).reset_index(drop=True)
        self.assertEqual(first, self.build(shuffled, cal))
        changed = fit.assign(nbim_vote="MOT")
        second = self.build(changed, cal)
        self.assertEqual(first[0]["proposals"], second[0]["proposals"])
        matches = first[0]["proposals"][0]["history_matches"]
        self.assertEqual(sum("global" in m["selection"] for m in matches), 8)
        self.assertEqual(sum("company" in m["selection"] for m in matches), 8)

    def test_history_deduplicated_but_similarity_stays_per_proposal(self):
        cal = pd.DataFrame([row("query", "2024-01-10", item="1"), row("query", "2024-01-10", item="2")])
        matrix = vectors(3)
        matrix[2, :2] = [0, 1]
        bundle = self.build(cal=cal, matrix=matrix)[0]
        self.assertEqual(len(bundle["history"]), 1)
        self.assertEqual([p["history_matches"][0]["cosine_similarity"] for p in bundle["proposals"]], [1.0, 0.0])

    def test_invalid_period_identity_votes_and_vectors_are_rejected(self):
        for cal in (self.cal.assign(meeting_date="2025-01-01"), self.cal.assign(mgmt_rec=""),
                    self.cal.assign(nbim_vote=""), pd.concat([self.cal, self.cal.iloc[:1]])):
            with self.assertRaises(ValueError):
                self.build(cal=cal)
        for matrix in (np.zeros((5, 384)), np.full((5, 384), np.nan), vectors(4), np.ones((5, 383))):
            with self.assertRaises(ValueError):
                self.build(matrix=matrix)
        inconsistent = self.cal.copy()
        inconsistent.loc[1, "meeting_id"] = "early"
        inconsistent.loc[1, "item_no"] = "2"
        with self.assertRaises(ValueError):
            self.build(cal=inconsistent)

    def test_preflight_rejects_extra_fields_and_cross_cutoff_history(self):
        bundle = self.query()
        for poison in ("nbim_vote", "rationale", "local_model_score"):
            altered = copy.deepcopy(bundle)
            altered["proposals"][0][poison] = "SECRET"
            with self.assertRaises(ValueError):
                context.validate_bundle(altered)
        altered = copy.deepcopy(bundle)
        altered["history"][0]["meeting_date"] = "2024-01-05"
        with self.assertRaises(ValueError):
            context.validate_bundle(altered)

    def test_against_board_is_derived_from_votes_and_null_stays_missing(self):
        bundle = self.query()
        bundle["proposals"][0]["board_recommendation"] = "MOT"
        for vote, expected in (("FOR", True), ("MOT", False), ("AVSTÅ", True), (None, None)):
            result = context.validate_response(bundle, self.reply(bundle, vote))
            self.assertIs(result["items"][0]["against_board"], expected)
            self.assertTrue(result["items"][0]["history_ids_verified"])

    def test_incomplete_and_bad_provenance_preserve_usage_on_failure(self):
        bundle = self.query()
        reply = self.reply(bundle)
        drafts = json.loads(reply["content"][0]["text"])["items"]
        cases = [[], drafts * 2, [{**drafts[0], "history_ids": ["invented:1"]}],
                 [{**drafts[0], "vote": "AGAINST"}], [{**drafts[0], "why": ""}]]
        for items in cases:
            reply["content"][0]["text"] = json.dumps({"items": items})
            with self.assertRaises(context.ReviewValidationError) as error:
                context.validate_response(bundle, reply)
            self.assertEqual(error.exception.usage, reply["usage"])
        reply["stop_reason"] = "max_tokens"
        with self.assertRaises(context.ReviewValidationError) as error:
            context.validate_response(bundle, reply)
        self.assertEqual(error.exception.stop_reason, "max_tokens")

    def test_generation_makes_one_mocked_call_with_allowlisted_context(self):
        bundle = self.query()
        reply = self.reply(bundle)
        create = Mock(return_value=SimpleNamespace(model_dump=lambda: reply))
        client = SimpleNamespace(messages=SimpleNamespace(create=create))
        result = context.generate_review(bundle, client, model="mock-model", effort="low")
        create.assert_called_once()
        params = create.call_args.kwargs
        self.assertEqual(params["model"], "mock-model")
        self.assertEqual(json.loads(params["messages"][0]["content"]), bundle)
        self.assertNotIn("tools", params)
        self.assertEqual(result["usage"], reply["usage"])


if __name__ == "__main__":
    unittest.main()
