"""Outcome permutation, chronology and diversity checks for hybrid retrieval."""
import copy
import json
import unittest

import numpy as np
import pandas as pd

import relevance_retrieval as retrieval


def row(meeting, day, text="Elect Ada Example as Director", company="c1", item="1", vote="FOR", board="FOR"):
    return {"meeting_id": meeting, "item_no": item, "company_id": company, "company": company,
            "meeting_date": day, "proposal_text": text, "proponent": "Management",
            "mgmt_rec": board, "nbim_vote": vote, "rationale": "SECRET_RATIONALE", "category": "SECRET_CATEGORY"}


def vectors(n):
    result = np.zeros((n, 384), dtype=np.float32)
    result[:, 0] = 1
    return result


class HybridHistoryTests(unittest.TestCase):
    def setUp(self):
        self.reference = pd.DataFrame([
            row("old", "2023-01-01", vote="MOT"), row("prior", "2024-01-04"),
            row("cutoff", "2024-01-05"), row("now", "2024-01-10"),
            row("same-day-company", "2024-01-10"), row("future", "2024-02-01")])
        self.query = pd.DataFrame([row("now", "2024-01-10")])

    def index(self, reference=None, **kwargs):
        reference = self.reference if reference is None else reference
        return retrieval.HybridHistoryRetriever(**kwargs).fit(reference, vectors(len(reference)))

    def test_strict_time_margin_own_meeting_and_allowlist(self):
        result = self.index().retrieve(self.query, vectors(1))[0]
        self.assertEqual({m["meeting_id"] for m in result["matches"]}, {"old", "prior"})
        self.assertEqual(result["cutoff"], "2024-01-05")
        self.assertNotIn("SECRET", json.dumps(result))
        self.assertNotIn("nbim_vote", result["query"])
        self.assertEqual(result["audit"]["cutoff_violations"], 0)
        self.assertEqual(result["audit"]["max_selected_date"], "2024-01-04")
        own_with_earlier_date = pd.DataFrame([row("now", "2023-01-01")])
        self.assertEqual(self.index(own_with_earlier_date).retrieve(self.query, vectors(1))[0]["matches"], [])

    def test_query_labels_and_current_future_history_labels_do_not_change_any_input(self):
        before = self.index().retrieve(self.query, vectors(1))
        altered = self.reference.copy()
        altered.loc[altered.meeting_date >= "2024-01-05", "nbim_vote"] = "MOT"
        query = self.query.assign(nbim_vote="AVSTÅ", rationale="different secret", category="different category")
        after = self.index(altered).retrieve(query, vectors(1))
        self.assertEqual(before, after)
        np.testing.assert_allclose(retrieval.features_from_results(before)[0],
                                   retrieval.features_from_results(after)[0], equal_nan=True)

    def test_past_label_permutation_changes_aggregation_but_not_selection(self):
        first = self.index()
        second = self.index(self.reference.assign(nbim_vote="AVSTÅ"))
        self.assertEqual(first.select(self.query, vectors(1)), second.select(self.query, vectors(1)))
        self.assertFalse(np.allclose(first.features(self.query, vectors(1))[0],
                                    second.features(self.query, vectors(1))[0], equal_nan=True))

    def test_future_text_is_not_fitted_into_lexical_statistics(self):
        before = self.index().retrieve(self.query, vectors(1))[0]
        altered = self.reference.copy()
        altered.loc[altered.meeting_date >= "2024-01-05", "proposal_text"] = "new future words director salary" * 100
        after = self.index(altered).retrieve(self.query, vectors(1))[0]
        self.assertEqual(before, after)
        self.assertFalse(self.index().configuration["vocabulary_or_idf_fit"])

    def test_deterministic_input_order_and_no_minority_balancing(self):
        reference = pd.DataFrame([row(f"m-{i:02d}", "2023-01-01", text=f"Director candidate name{i}",
                                      company=f"c{i % 3}", vote="MOT" if i == 17 else "FOR") for i in range(25)])
        first = self.index(reference).retrieve(self.query, vectors(1))
        reordered = self.index(reference.sample(frac=1, random_state=4)).retrieve(self.query, vectors(1))
        self.assertEqual(first, reordered)
        altered = reference.assign(nbim_vote="MOT")
        changed = self.index(altered).retrieve(self.query, vectors(1))
        first_without_votes = copy.deepcopy(first)
        changed_without_votes = copy.deepcopy(changed)
        for result in first_without_votes + changed_without_votes:
            for match in result["matches"]:
                del match["nbim_vote"]
        self.assertEqual(first_without_votes, changed_without_votes)

    def test_duplicate_text_diversity_preserves_two_recent_examples_per_pool(self):
        reference = pd.DataFrame([row(f"duplicate-{i:02d}", f"2023-01-{i + 1:02d}") for i in range(10)] +
                                 [row(f"different-{i:02d}", "2023-02-01", text=f"Unique business resolution number {i}")
                                  for i in range(10)])
        result = self.index(reference).retrieve(self.query, vectors(1))[0]
        for scope in ("global", "company"):
            matches = [m for m in result["matches"] if scope in m["selection"]]
            duplicate = [m["meeting_id"] for m in matches if m["proposal_text"] == self.query.proposal_text.iloc[0]]
            self.assertEqual(duplicate, ["duplicate-09", "duplicate-08"])
            self.assertEqual(len(matches), 8)
        self.assertGreater(result["audit"]["global_duplicate_skips"], 0)
        self.assertEqual(len({m["id"] for m in result["matches"]}), len(result["matches"]))

    def test_lexical_match_can_break_a_dense_tie_without_using_vote(self):
        reference = pd.DataFrame([row("a", "2023-01-01", text="Approve executive compensation", vote="MOT"),
                                 row("b", "2023-01-01", text="Elect Ada Example as Director")])
        result = self.index(reference).retrieve(self.query, vectors(1), k_global=1, k_company=1)[0]
        self.assertEqual(result["matches"][0]["meeting_id"], "b")
        self.assertAlmostEqual(result["matches"][0]["lexical_similarity"], 1.)

    def test_historical_conflict_uses_only_selected_past_votes(self):
        reference = pd.DataFrame([row("past1", "2023-01-01", vote="FOR"),
                                 row("past2", "2023-02-01", vote="MOT")])
        features, names = self.index(reference).features(self.query, vectors(1))
        self.assertEqual(features.shape, (1, len(retrieval.FEATURE_NAMES)))
        self.assertEqual(features[0, names.index("hybrid_exact_company_conflicting_votes")], 1.)
        self.assertEqual(features[0, names.index("hybrid_exact_all_against_board_mean")], .5)
        self.assertEqual(features[0, names.index("hybrid_all_first_against_board")], 1.)

    def test_no_history_retains_zero_counts_and_missing_rates(self):
        reference = pd.DataFrame([row("future", "2025-01-01")])
        values, names = self.index(reference).features(self.query, vectors(1))
        self.assertEqual(values.shape, (1, 48))
        self.assertEqual(values[0, names.index("hybrid_all_count_log")], 0.)
        self.assertTrue(np.isnan(values[0, names.index("hybrid_all_against_board_mean")]))

    def test_preflight_rejects_leaked_fields_and_temporal_violations(self):
        original = self.index().retrieve(self.query, vectors(1))[0]
        for location in ("query", "matches"):
            changed = copy.deepcopy(original)
            (changed["query"] if location == "query" else changed["matches"][0])["rationale"] = "SECRET"
            with self.assertRaises(ValueError):
                retrieval.validate_result(changed)
        for day in ("2024-01-05", "2024-01-10", "2025-01-01"):
            changed = copy.deepcopy(original)
            changed["matches"][0]["meeting_date"] = day
            with self.assertRaises(ValueError):
                retrieval.features_from_results([changed])

    def test_invalid_index_configuration_and_embeddings_fail_closed(self):
        for kwargs in ({"dense_weight": float("nan")}, {"dense_weight": 1.1}, {"dense_weight": True},
                       {"max_per_text": 0}, {"max_per_text": 1.5}):
            with self.assertRaises(ValueError):
                self.index(**kwargs)
        for reference in (self.reference.assign(nbim_vote=""), self.reference.assign(mgmt_rec=""),
                          pd.concat([self.reference, self.reference.iloc[:1]])):
            with self.assertRaises(ValueError):
                self.index(reference)
        with self.assertRaises(ValueError):
            retrieval.HybridHistoryRetriever().fit(self.reference, np.zeros((6, 384)))
        with self.assertRaises(ValueError):
            self.index().retrieve(self.query, np.full((1, 384), np.nan))
        with self.assertRaises(ValueError):
            self.index().retrieve(self.query, vectors(1), k_global=0)


if __name__ == "__main__":
    unittest.main()
