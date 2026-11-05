"""No-network leakage, chronology and aggregation checks for supervised features."""
import unittest

import numpy as np
import pandas as pd

from vote_features import FEATURE_NAMES, features, named_person, normalize_text, proposal_family


def row(meeting="a", date="2020-01-01", company="company-a", vote="FOR", text="Elect Ada Example as Director"):
    return {"meeting_id": meeting, "item_no": "1", "company_id": company, "company": company,
            "meeting_date": date, "proposal_text": text, "mgmt_rec": "FOR", "proponent": "Management", "nbim_vote": vote}


def vectors(count):
    result = np.zeros((count, 384), dtype=np.float32)
    result[:, 0] = 1
    return result


def values(query, reference, X=None, R=None):
    matrix, names = features(query, vectors(len(query)) if X is None else X,
                             reference, vectors(len(reference)) if R is None else R)
    return matrix, [dict(zip(names, item)) for item in matrix]


class VoteFeatureTests(unittest.TestCase):
    def test_query_votes_rationales_and_supplied_categories_are_not_read(self):
        query = pd.DataFrame([row("query", "2024-01-01")])
        reference = pd.DataFrame([row(vote="MOT")])
        first, _ = values(query, reference)
        query["nbim_vote"] = "SECRET_LABEL"
        query["rationale"] = "SECRET_REASON"
        query["proposal_type"] = "SECRET_DERIVED_CATEGORY"
        second, _ = values(query, reference.assign(rationale="ignored", proposal_type="ignored"))
        third, _ = values(query.drop(columns=["nbim_vote", "rationale", "proposal_type"]), reference)
        np.testing.assert_allclose(first, second, equal_nan=True)
        np.testing.assert_allclose(first, third, equal_nan=True)

    def test_every_historical_feature_excludes_cutoff_future_current_and_own_meeting(self):
        query = pd.DataFrame([row("query", "2024-01-10")])
        allowed = row("allowed", "2024-01-04", vote="MOT")
        reference = pd.DataFrame([allowed, row("cutoff", "2024-01-05"), row("current", "2024-01-10"),
                                  row("future", "2024-01-11"), row("query", "2019-01-01")])
        first, _ = values(query, reference)
        expected, _ = values(query, pd.DataFrame([allowed]))
        np.testing.assert_allclose(first, expected, equal_nan=True)
        reference.loc[1:, "nbim_vote"] = "MOT"
        reference.loc[1:, "proposal_text"] = "Approve New Remuneration Policy"
        changed_vectors = vectors(len(reference))
        changed_vectors[1:, :2] = [0, 1]
        changed, _ = values(query, reference, R=changed_vectors)
        np.testing.assert_allclose(first, changed, equal_nan=True)

    def test_only_supplied_fit_rows_can_contribute(self):
        query = pd.DataFrame([row("query", "2024-01-01")])
        source = pd.DataFrame([row("fit", vote="FOR"), row("withheld", vote="MOT")])
        _, result = values(query, source.iloc[:1])
        self.assertEqual(result[0]["company_mot_mean"], 0)
        self.assertEqual(result[0]["semantic_global_top20_mot_mean"], 0)
        self.assertTrue(np.isnan(result[0]["top_mot_similarity"]))
        self.assertEqual(result[0]["history_count_log"], np.log1p(1))

    def test_history_recency_person_and_exact_text_features_have_expected_values(self):
        query = pd.DataFrame([row("query", "2024-01-01")])
        reference = pd.DataFrame([row("old", "2021-01-01", vote="FOR"), row("recent", "2023-12-01", vote="MOT")])
        _, result = values(query, reference)
        result = result[0]
        self.assertEqual(result["company_mot_mean"], .5)
        self.assertEqual(result["company_365d_mot_mean"], 1)
        self.assertEqual(result["company_365d_count_log"], np.log1p(1))
        self.assertEqual(result["company_meetings_log"], np.log1p(2))
        self.assertEqual(result["exact_company_last_mot"], 1)
        self.assertEqual(result["person_company_last_mot"], 1)
        self.assertEqual(result["exact_company_last_age_years"], 31 / 365.25)
        self.assertEqual(result["person_company_count_log"], np.log1p(2))
        self.assertEqual(result["semantic_global_top20_mot_mean"], .5)
        self.assertGreater(result["semantic_global_top20_recency_mot_mean"], .85)
        self.assertGreater(result["family_company_recency_mot_mean"], .85)

    def test_semantic_similarity_margin_and_distance_counts(self):
        query = pd.DataFrame([row("query", "2024-01-01")])
        reference = pd.DataFrame([row("positive", vote="MOT"), row("negative", vote="FOR")])
        embedded = vectors(2)
        embedded[1, :2] = [0, 1]
        _, result = values(query, reference, R=embedded)
        result = result[0]
        self.assertEqual(result["top_mot_similarity"], 1)
        self.assertEqual(result["top_nonmot_similarity"], 0)
        self.assertEqual(result["mot_similarity_margin"], 1)
        self.assertEqual(result["similarity_090_count_log"], np.log1p(1))
        self.assertEqual(result["similarity_090_mot_mean"], 1)
        self.assertAlmostEqual(result["semantic_global_top5_mot_mean"], 1 / (1 + np.exp(-10)))

    def test_global_company_and_family_history_stay_separate(self):
        query = pd.DataFrame([row("query", "2024-01-01")])
        reference = pd.DataFrame([row("own", vote="FOR"), row("other", company="other", vote="MOT"),
                                  row("pay", vote="MOT", text="Approve Remuneration Report")])
        _, result = values(query, reference)
        result = result[0]
        self.assertEqual(result["company_mot_mean"], .5)
        self.assertEqual(result["family_company_mot_mean"], 0)
        self.assertEqual(result["family_global_mot_mean"], .5)
        self.assertEqual(result["exact_company_mot_mean"], 0)
        self.assertEqual(result["exact_global_mot_mean"], .5)
        self.assertEqual(result["person_company_mot_mean"], 0)

    def test_exact_ties_are_label_blind_and_stable_under_reference_reordering(self):
        query = pd.DataFrame([row("query", "2024-01-01")])
        reference = pd.DataFrame([row("other", "2023-12-01", company="other", vote="MOT"),
                                  row("own-old", "2021-01-01", vote="MOT"), row("own-recent", "2023-01-01", vote="FOR")])
        first, result = values(query, reference)
        second, _ = values(query, reference.iloc[::-1])
        np.testing.assert_allclose(first, second, equal_nan=True)
        self.assertEqual(result[0]["semantic_global_top1_mot_mean"], 0)
        self.assertEqual(result[0]["semantic_company_top1_mot_mean"], 0)

    def test_missing_history_uses_zero_counts_and_nan_rates(self):
        query = pd.DataFrame([row("query", "2019-01-01", text="Approve Ordinary Business")])
        reference = pd.DataFrame([row()])
        _, result = values(query, reference)
        result = result[0]
        self.assertEqual(result["history_count_log"], 0)
        self.assertEqual(result["person_company_count_log"], 0)
        self.assertEqual(result["has_named_person"], 0)
        self.assertTrue(np.isnan(result["company_mot_mean"]))
        self.assertTrue(np.isnan(result["semantic_global_top1_mot_mean"]))
        self.assertEqual(result["board_for"], 1)
        self.assertEqual(result["family_other"], 1)
        empty, _ = values(query.iloc[:0], reference)
        self.assertEqual(empty.shape, (0, len(FEATURE_NAMES)))
        no_reference, _ = values(query, reference.iloc[:0])
        self.assertEqual(no_reference.shape, (1, len(FEATURE_NAMES)))

    def test_text_families_and_names_are_derived_from_text_only(self):
        self.assertEqual(normalize_text("  RE-ELECT  Ada, Example! "), "re elect ada example")
        for text, family in (("Approve Director Remuneration", "pay"), ("Ratify Independent Auditor", "auditor"),
                             ("Elect Ada Example as Director", "director"), ("Authorize Share Repurchase", "capital"),
                             ("Shareholder Proposal on Climate", "shareholder")):
            self.assertEqual(proposal_family(text), family)
        for text in ("Elect Ada Example as Director", "Re-elect Director Ada Example", "Appoint Statutory Auditor Ada Example"):
            self.assertEqual(named_person(text), "ada example")
        for text in ("Elect Director", "Elect Three Inside Directors (Bundled)", "Appoint KPMG LLP as External Auditor", "Approve Compensation"):
            self.assertEqual(named_person(text), "")

    def test_invalid_votes_vectors_dates_and_duplicate_keys_fail(self):
        query = pd.DataFrame([row("query", "2024-01-01")])
        reference = pd.DataFrame([row()])
        for vote in ("", None, np.nan, "UNKNOWN"):
            with self.subTest(vote=vote), self.assertRaises(ValueError):
                values(query, reference.assign(nbim_vote=vote))
        for changed in (reference.assign(meeting_date="invalid"), pd.concat([reference, reference])):
            with self.assertRaises(ValueError):
                values(query, changed)
        for embedded in (np.zeros((1, 384)), np.ones((1, 383)), np.full((1, 384), np.inf)):
            with self.assertRaises(ValueError):
                values(query, reference, X=embedded)

    def test_batching_keeps_query_order_and_feature_names_stable(self):
        reference = pd.DataFrame([row(vote="MOT")])
        query = pd.DataFrame([row(f"query-{i}", "2019-01-01" if i == 256 else "2024-01-01") for i in range(258)])
        matrix, result = values(query, reference)
        self.assertEqual(matrix.shape, (258, 59))
        self.assertEqual(len(set(FEATURE_NAMES)), 59)
        self.assertEqual(result[255]["company_mot_mean"], 1)
        self.assertTrue(np.isnan(result[256]["company_mot_mean"]))
        self.assertEqual(result[257]["company_mot_mean"], 1)
        self.assertFalse(np.isinf(matrix).any())


if __name__ == "__main__":
    unittest.main()
