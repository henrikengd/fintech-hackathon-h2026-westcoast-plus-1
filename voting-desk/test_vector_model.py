"""Offline checks for chronological local vote decisions and artifact provenance."""
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
import pandas as pd

from vector_model import DIMENSION, INPUT_FIELDS, META_FIELDS, VectorVoteModel, input_text


def row(meeting="a", date="2020-01-01", company="company-a", vote="FOR", item="1"):
    return {"meeting_id": meeting, "item_no": item, "company_id": company, "company": company,
            "meeting_date": date, "proposal_text": "Elect director Ada Example", "mgmt_rec": "FOR",
            "proponent": "Management", "nbim_vote": vote}


def vectors(count):
    result = np.zeros((count, DIMENSION), dtype=np.float32)
    result[:, 0] = 1
    return result


class VectorModelTests(unittest.TestCase):
    def test_embedding_input_never_reads_labels_names_or_rationales(self):
        source = row()
        expected = input_text(source)
        source.update(nbim_vote="MOT", company="DO_NOT_EMBED_COMPANY", rationale="DO_NOT_EMBED_RATIONALE",
                      proposal_type="DO_NOT_EMBED_TYPE", meeting_id="DO_NOT_EMBED_ID")
        self.assertEqual(input_text(source), expected)
        self.assertEqual(input_text({**source, "proponent": None}), expected.replace("proponent: Management", "proponent: "))
        self.assertTrue(all(name in expected for name in INPUT_FIELDS))
        self.assertNotIn("DO_NOT_EMBED", input_text(source))

    def test_strict_cutoff_excludes_future_same_meeting_and_company_date(self):
        references = pd.DataFrame([
            row("eligible", "2024-01-04", vote="MOT"),
            row("cutoff", "2024-01-05", vote="FOR"),
            row("recent", "2024-01-09", vote="FOR"),
            row("other-id-same-group", "2024-01-10", vote="FOR"),
            row("future", "2024-01-11", vote="FOR"),
            row("query", "2020-01-01", vote="FOR"),
        ])
        model = VectorVoteModel().fit(references, vectors(len(references)))
        result = model.predict(pd.DataFrame([row("query", "2024-01-10")]), vectors(1))[0]
        self.assertEqual(result["score"], 1)
        self.assertEqual(result["history_count"], 1)
        self.assertEqual([n["meeting_id"] for n in result["neighbors"]], ["eligible"])

    def test_no_history_is_unscored_and_unknown_query_labels_are_ignored(self):
        model = VectorVoteModel().fit(pd.DataFrame([row()]), vectors(1))
        result = model.predict(pd.DataFrame([row("query", "2019-01-01", vote="UNKNOWN")]), vectors(1))[0]
        self.assertIsNone(result["score"])
        self.assertEqual(result["neighbor_count"], 0)
        self.assertEqual(result["history_count"], 0)
        self.assertEqual(result["neighbor_vote_counts"], {"FOR": 0, "MOT": 0, "AVSTÅ": 0})
        self.assertFalse(result["conflicting_votes"])

    def test_only_fit_references_are_available_and_query_votes_never_affect_score(self):
        source = pd.DataFrame([row("fit", vote="FOR"), row("withheld", vote="MOT")])
        model = VectorVoteModel().fit(source.iloc[:1], vectors(1))
        query = pd.DataFrame([row("query", "2024-01-01", vote="FOR")])
        before = model.predict(query, vectors(1))
        query["nbim_vote"] = "MOT"
        self.assertEqual(model.predict(query, vectors(1)), before)
        self.assertEqual(before[0]["score"], 0)
        self.assertEqual([n["meeting_id"] for n in before[0]["neighbors"]], ["fit"])

    def test_same_company_weight_changes_votes_not_neighbor_selection(self):
        source = pd.DataFrame([row("a", vote="FOR"), row("b", company="other", vote="MOT")])
        model = VectorVoteModel().fit(source, vectors(2))
        query = pd.DataFrame([row("query", "2024-01-01")])
        plain = model.predict(query, vectors(1), k=2)[0]
        weighted = model.predict(query, vectors(1), k=2, company_weight=4)[0]
        self.assertEqual(plain["score"], .5)
        self.assertEqual(weighted["score"], .2)
        self.assertEqual([n["meeting_id"] for n in plain["neighbors"]], [n["meeting_id"] for n in weighted["neighbors"]])
        self.assertEqual(weighted["neighbor_vote_counts"], {"FOR": 1, "MOT": 1, "AVSTÅ": 0})
        self.assertTrue(weighted["conflicting_votes"])
        self.assertEqual(weighted["neighbors"][0]["weight"], 4)

    def test_cosine_ranking_and_similarity_weights_are_label_blind(self):
        source = pd.DataFrame([row("close", vote="MOT"), row("far", vote="FOR")])
        embedded = vectors(2)
        embedded[1, :2] = [0, 1]
        model = VectorVoteModel().fit(source, embedded)
        query = pd.DataFrame([row("query", "2024-01-01")])
        result = model.predict(query, vectors(1), k=2)[0]
        self.assertEqual(result["neighbors"][0]["meeting_id"], "close")
        self.assertAlmostEqual(result["score"], 1 / (1 + np.exp(-10)))
        top = model.predict(query, vectors(1), k=1)[0]
        self.assertEqual(top["score"], 1)
        self.assertEqual(top["history_count"], 2)
        source["nbim_vote"] = ["FOR", "MOT"]
        changed = VectorVoteModel().fit(source, embedded).predict(query, vectors(1), k=2)[0]
        self.assertEqual([n["weight"] for n in result["neighbors"]], [n["weight"] for n in changed["neighbors"]])

    def test_cosine_ties_are_deterministic_across_fit_order(self):
        source = pd.DataFrame([row("b", vote="MOT"), row("a", vote="FOR")])
        query = pd.DataFrame([row("query", "2024-01-01")])
        first = VectorVoteModel().fit(source, vectors(2)).predict(query, vectors(1), k=1)
        second = VectorVoteModel().fit(source.iloc[::-1], vectors(2)).predict(query, vectors(1), k=1)
        self.assertEqual(first, second)
        self.assertEqual(first[0]["neighbors"][0]["meeting_id"], "a")

    def test_exact_ties_prefer_same_company_then_recent_date_then_identity(self):
        source = pd.DataFrame([row("other-recent", "2023-01-01", company="other", vote="MOT"),
                               row("same-old", "2020-01-01", vote="FOR"),
                               row("same-recent-b", "2022-01-01", vote="MOT"),
                               row("same-recent-a", "2022-01-01", vote="FOR")])
        query = pd.DataFrame([row("query", "2024-01-01")])
        result = VectorVoteModel().fit(source, vectors(4)).predict(query, vectors(1), k=4)[0]
        self.assertEqual([n["meeting_id"] for n in result["neighbors"]],
                         ["same-recent-a", "same-recent-b", "same-old", "other-recent"])

    def test_neighbor_output_limit_does_not_change_votes_or_counts(self):
        source = pd.DataFrame([row("a", vote="FOR"), row("b", vote="MOT")])
        query = pd.DataFrame([row("query", "2024-01-01")])
        model = VectorVoteModel().fit(source, vectors(2))
        full = model.predict(query, vectors(1), k=2)[0]
        for limit in (0, 1):
            result = model.predict(query, vectors(1), k=2, neighbor_limit=limit)[0]
            self.assertEqual(len(result["neighbors"]), limit)
            self.assertEqual({key: value for key, value in full.items() if key != "neighbors"},
                             {key: value for key, value in result.items() if key != "neighbors"})
        with self.assertRaises(ValueError):
            model.predict(query, vectors(1), neighbor_limit=-1)

    def test_batches_preserve_query_order_and_empty_queries_work(self):
        model = VectorVoteModel().fit(pd.DataFrame([row(vote="MOT")]), vectors(1))
        query = pd.DataFrame([row(f"query-{i}", "2019-01-01" if i == 256 else "2024-01-01") for i in range(258)])
        result = model.predict(query, vectors(len(query)))
        self.assertEqual(len(result), 258)
        self.assertEqual(result[255]["score"], 1)
        self.assertIsNone(result[256]["score"])
        self.assertEqual(result[257]["score"], 1)
        self.assertEqual(model.predict(query.iloc[:0], vectors(0)), [])

    def test_fit_rejects_missing_unknown_votes_duplicate_ids_and_bad_dates(self):
        for vote in (None, np.nan, "", "UNKNOWN"):
            with self.subTest(vote=vote), self.assertRaises(ValueError):
                VectorVoteModel().fit(pd.DataFrame([row(vote=vote)]), vectors(1))
        for source in (pd.DataFrame([row(), row()]), pd.DataFrame([row(date="invalid")]),
                       pd.DataFrame([row(company="")]), pd.DataFrame([row()]).drop(columns="nbim_vote")):
            with self.subTest(source=source), self.assertRaises(ValueError):
                VectorVoteModel().fit(source, vectors(len(source)))
        model = VectorVoteModel().fit(pd.DataFrame([row(vote="AVSTÅ")]), vectors(1))
        self.assertEqual(model.predict(pd.DataFrame([row("query", "2024-01-01")]), vectors(1))[0]["score"], 0)

    def test_bad_vectors_and_parameters_fail_and_normalization_handles_scale(self):
        source = pd.DataFrame([row()])
        for embedded in (np.zeros((1, DIMENSION)), np.ones((1, DIMENSION - 1)), vectors(2),
                         np.full((1, DIMENSION), np.nan), np.full((1, DIMENSION), np.inf)):
            with self.subTest(shape=embedded.shape), self.assertRaises(ValueError):
                VectorVoteModel().fit(source, embedded)
        model = VectorVoteModel().fit(source, vectors(1).astype(np.float64) * 1e300)
        np.testing.assert_array_equal(model.embeddings, vectors(1))
        query = pd.DataFrame([row("query", "2024-01-01")])
        for k in (0, -1, 1.5, True):
            with self.subTest(k=k), self.assertRaises(ValueError):
                model.predict(query, vectors(1), k=k)
        for weight in (0, -1, np.nan, np.inf, True):
            with self.subTest(weight=weight), self.assertRaises(ValueError):
                model.predict(query, vectors(1), company_weight=weight)
        with self.assertRaises(ValueError):
            VectorVoteModel().predict(query, vectors(1))

    def test_fit_snapshots_only_safe_metadata_and_separates_labels(self):
        source = pd.DataFrame([row()]).assign(rationale="secret", proposal_type="derived")
        embedded = vectors(1)
        model = VectorVoteModel().fit(source, embedded)
        source.loc[0, "nbim_vote"] = "MOT"
        embedded[:] = 0
        self.assertEqual(list(model.metadata.columns), META_FIELDS)
        self.assertEqual(model.labels.tolist(), ["FOR"])
        np.testing.assert_array_equal(model.embeddings, vectors(1))

    def test_save_load_verifies_all_files_and_rejects_overwrite(self):
        source = pd.DataFrame([row("b", vote="MOT"), row("a", vote="FOR")])
        model = VectorVoteModel().fit(source, vectors(2))
        query = pd.DataFrame([row("query", "2024-01-01")])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "model"
            model.save(path)
            self.assertEqual(model.predict(query, vectors(1)), VectorVoteModel.load(path).predict(query, vectors(1)))
            self.assertNotIn("nbim_vote", (path / "metadata.json").read_text())
            with self.assertRaises(FileExistsError):
                model.save(path)
            for name in ("metadata.json", "labels.json", "embeddings.npy"):
                original = (path / name).read_bytes()
                (path / name).write_bytes(original + b"tampered")
                with self.subTest(name=name), self.assertRaises(ValueError):
                    VectorVoteModel.load(path)
                (path / name).write_bytes(original)
            manifest = json.loads((path / "manifest.json").read_text())
            manifest["embedding_model"] = "different"
            (path / "manifest.json").write_text(json.dumps(manifest))
            with self.assertRaises(ValueError):
                VectorVoteModel.load(path)


if __name__ == "__main__":
    unittest.main()
