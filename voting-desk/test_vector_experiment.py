"""Offline checks of temporal selection, reserved partitions and saved predictions."""
import boot  # noqa: F401
from contextlib import redirect_stdout
import inspect
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

import vector_experiment as experiment
from vector_model import DIMENSION, VectorVoteModel, input_text


def row(meeting, year, vote="FOR", item="1", company="company-a"):
    return {"meeting_id": meeting, "item_no": item, "company_id": company, "company": company,
            "meeting_date": f"{year}-06-01", "proposal_text": f"Proposal {item}",
            "mgmt_rec": "FOR", "proponent": "Management", "nbim_vote": vote}


def yearly_rows():
    return pd.DataFrame([row(str(year), year, vote, str(item))
                         for year in range(2019, 2025)
                         for item, vote in ((1, "MOT"), (2, "FOR"))])


def vectors(count):
    matrix = np.zeros((count, DIMENSION), dtype=np.float32)
    matrix[:, 0] = 1
    return matrix


def write_split(path, train, test):
    train.to_csv(path / "train.csv", index=False)
    test.to_csv(path / "test.csv", index=False)
    (path / "source.csv").write_text("fixture source identity\n")
    manifest = {"dataset_id": "fixture", "source": {"path": "source.csv"},
                "source_sha256": experiment.digest(path / "source.csv"),
                "files": {name: experiment.digest(path / name) for name in ("train.csv", "test.csv")}}
    (path / "manifest.json").write_text(json.dumps(manifest))
    return manifest


class VectorExperimentTests(unittest.TestCase):
    def test_missing_scores_remain_false_negatives_at_zero_threshold(self):
        result = experiment.metrics([True, True, False, False], [None, 0.0, np.nan, 0.0], 0.0)
        self.assertEqual((result["tp"], result["fp"], result["fn"], result["tn"]), (1, 1, 1, 1))
        self.assertEqual(result["precision"], .5)
        self.assertEqual(result["recall"], .5)
        self.assertEqual(result["false_positive_rate"], .5)
        self.assertEqual((result["covered"], result["uncovered"]), (2, 2))
        self.assertEqual(result["recommendation_coverage"], .5)
        self.assertEqual(result["predicted_mot_share"], .5)
        self.assertIsNone(experiment.metrics([True], [None], 0)["precision"])

    def test_threshold_enforces_recall_and_keeps_tied_scores_together(self):
        labels, scores = [True, False, True, False], [.9, .8, .7, .1]
        self.assertEqual(experiment.select_threshold(labels, scores, .85), .7)
        self.assertEqual(experiment.select_threshold(labels, scores, .5), .9)
        # Equal precision is resolved by higher recall; no row inside a score tie can be split off.
        self.assertEqual(experiment.select_threshold([True, False, True, False], [.9, .9, .2, .2], .5), .2)
        self.assertIsNone(experiment.select_threshold([True, True, False], [.9, None, .1], .85))
        self.assertIsNone(experiment.select_threshold([False], [.8]))
        self.assertIsNone(experiment.select_threshold([True], [None]))
        self.assertEqual(experiment.select_threshold([True, False], [0, 0], 1), 0)
        for invalid in (0, -1, 1.01, np.nan):
            with self.subTest(target=invalid), self.assertRaises(ValueError):
                experiment.select_threshold(labels, scores, invalid)

    def test_forward_folds_keep_meetings_together_and_never_validate_2024(self):
        frame = yearly_rows().sample(frac=1, random_state=17).reset_index(drop=True)
        checked = []
        for year, fit, check in experiment.forward_folds(frame):
            training, validation = frame.iloc[fit], frame.iloc[check]
            self.assertTrue(training.meeting_date.lt(f"{year}-01-01").all())
            self.assertEqual(set(validation.meeting_date.str[:4]), {str(year)})
            self.assertFalse(set(training.meeting_id) & set(validation.meeting_id))
            self.assertFalse(set(map(tuple, training[experiment.GROUP].values))
                             & set(map(tuple, validation[experiment.GROUP].values)))
            self.assertEqual(len(validation), 2)
            checked.extend(check)
        expected = frame.index[frame.meeting_date.str[:4].isin(["2020", "2021", "2022", "2023"])]
        self.assertEqual(sorted(checked), sorted(expected))
        with self.assertRaisesRegex(ValueError, "Missing temporal fold 2022"):
            experiment.forward_folds(frame.loc[~frame.meeting_date.str.startswith("2022")])

    def test_loader_filters_years_before_interpreting_labels_and_ignores_test_labels(self):
        train = pd.concat([yearly_rows(), pd.DataFrame([
            row("future", 2025, "DO_NOT_USE"), row("older", 2018, "DO_NOT_USE"),
            row("unknown", 2024, "", company="unknown-company")])], ignore_index=True)
        reserved = pd.DataFrame([row("reserved", 2026, "DO_NOT_READ")])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            manifest = write_split(path, train, reserved)
            fit, dev, provenance = experiment.load_development(path)
        self.assertEqual(set(fit.meeting_date.str[:4]), {str(year) for year in range(2019, 2024)})
        self.assertEqual(set(dev.meeting_id), {"2024"})
        self.assertEqual(len(fit), 10)
        self.assertEqual(len(dev), 2)
        self.assertEqual(provenance["unknown_labels_excluded"], 1)
        self.assertEqual(provenance["source_sha256"], manifest["source_sha256"])
        self.assertEqual(provenance["split_test_sha256"], manifest["files"]["test.csv"])

    def test_loader_rejects_source_changes_partition_changes_and_reserved_groups(self):
        train = yearly_rows()
        reserved = pd.DataFrame([row("reserved", 2026, "DO_NOT_READ")])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            for changed in ("source.csv", "train.csv", "test.csv"):
                write_split(path, train, reserved)
                with (path / changed).open("a") as handle:
                    handle.write("changed\n")
                with self.subTest(changed=changed), self.assertRaisesRegex(ValueError, "hash mismatch"):
                    experiment.load_development(path)
            for overlap in (row("2024", 2026, "DO_NOT_READ", item="unseen"),
                            row("different-id", 2024, "DO_NOT_READ")):
                write_split(path, train, pd.DataFrame([overlap]))
                with self.subTest(overlap=overlap), self.assertRaisesRegex(ValueError, "Reserved test meeting overlaps"):
                    experiment.load_development(path)

    def test_cached_embedding_identity_is_label_blind_and_checks_saved_bytes(self):
        frame = yearly_rows().iloc[:2].copy()
        texts = [input_text(record) for record in frame.to_dict("records")]
        metadata = {"model": experiment.local_rag.MODEL, "assets": "fixture-assets",
                    "inputs_sha256": experiment.identity(texts),
                    "encoder_source": experiment.identity(inspect.getsource(input_text)),
                    "encoding": "symmetric passage_embed on allowlisted ballot inputs"}
        key = experiment.identity(metadata)
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(experiment.local_rag, "model_fingerprint", return_value="fixture-assets"), \
                patch.object(experiment.local_rag, "load_model", side_effect=AssertionError("No embedding calls")):
            path = Path(folder)
            np.savez_compressed(path / f"{key}.npz", vectors=vectors(len(frame)))
            (path / f"{key}.json").write_text(json.dumps({
                "identity": metadata, "vectors_sha256": experiment.digest(path / f"{key}.npz")}))
            original = frame.copy(deep=True)
            first, identity = experiment.embedding_matrix(frame, path)
            frame["nbim_vote"] = ["AVSTÅ", "MOT"]
            frame["rationale"] = "DO_NOT_EMBED"
            second, changed_identity = experiment.embedding_matrix(frame, path)
            np.testing.assert_array_equal(first, second)
            self.assertEqual(identity, changed_identity)
            pd.testing.assert_frame_equal(frame.drop(columns="rationale").drop(columns="nbim_vote"),
                                          original.drop(columns="nbim_vote"))
            with (path / f"{key}.npz").open("ab") as handle:
                handle.write(b"changed")
            with self.assertRaisesRegex(ValueError, "Embedding cache mismatch"):
                experiment.embedding_matrix(frame, path)

    def test_run_selects_from_forward_validation_before_one_development_prediction(self):
        frame = yearly_rows()
        fit, original_dev = frame.iloc[:-2].reset_index(drop=True), frame.iloc[-2:].reset_index(drop=True)
        real_select = experiment.select_threshold
        selections = []
        with tempfile.TemporaryDirectory() as folder:
            for version in range(2):
                output = Path(folder) / str(version)
                dev = original_dev.copy()
                if version:
                    dev["nbim_vote"] = ["FOR", "MOT"]
                development_calls = []
                selection_labels = []

                class RecordingModel:
                    def fit(self, records, embedded):
                        self.training = records.copy()
                        self_test.assertTrue(records.meeting_date.lt("2024-01-01").all())
                        return self

                    def predict(self, records, embedded, k, company_weight, neighbor_limit):
                        self_test.assertLess(self.training.meeting_date.max(), records.meeting_date.min())
                        if records.meeting_date.str.startswith("2024").any():
                            self_test.assertTrue((output / "selection.json").exists())
                            self_test.assertEqual(len(selection_labels), len(experiment.CONFIGS))
                            development_calls.append(records.meeting_id.tolist())
                        good = k == 8 and company_weight == 1
                        return [{"score": (.9 if item == "1" else .2) if good else .7}
                                for item in records.item_no]

                    def save(self, path):
                        Path(path).mkdir()
                        (Path(path) / "stub.json").write_text("{}")

                def checked_selection(labels, scores, target_recall):
                    self.assertEqual(len(labels), 8)
                    self.assertEqual(labels.tolist(), fit.iloc[2:].nbim_vote.eq("MOT").tolist())
                    selection_labels.append(labels.tolist())
                    return real_select(labels, scores, target_recall)

                self_test = self
                with patch.object(experiment, "load_development", return_value=(fit, dev, {"dataset_id": "fixture"})), \
                        patch.object(experiment, "embedding_matrix", return_value=(vectors(len(frame)), {})), \
                        patch.object(experiment, "VectorVoteModel", RecordingModel), \
                        patch.object(experiment, "select_threshold", side_effect=checked_selection), \
                        patch.object(experiment, "cached_reference", return_value=None), \
                        patch.object(experiment, "old_text_reference", return_value=None), redirect_stdout(io.StringIO()):
                    summary = experiment.run(output=output)
                self.assertEqual(len(development_calls), 1)
                self.assertEqual(summary["selected_config"], {"k": 8, "company_weight": 1.0})
                selections.append(json.loads((output / "selection.json").read_text()))
                self.assertEqual(summary["development_selected"]["recall"], 1.0 if not version else 0.0)
            self.assertEqual(selections[0], selections[1])

    def test_saved_prediction_verifies_artifacts_and_does_not_modify_query_or_use_labels(self):
        fit = pd.DataFrame([row("history", 2020, "MOT")])
        dev = pd.DataFrame([row("query", 2024, "UNAVAILABLE")])
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(experiment.local_rag, "load_model", side_effect=AssertionError("No embedding calls")):
            path = Path(folder)
            VectorVoteModel().fit(fit, vectors(1)).save(path / "model")
            dev.to_csv(path / "development.csv", index=False)
            np.savez_compressed(path / "development-vectors.npz", vectors=vectors(1))
            summary = {"selected_config": {"k": 8, "company_weight": 1.0}, "selected_threshold": .5,
                       "artifacts": {str(item.relative_to(path)): experiment.digest(item)
                                     for item in path.rglob("*") if item.is_file()}}
            (path / "summary.json").write_text(json.dumps(summary))
            before = {str(item): item.read_bytes() for item in path.rglob("*") if item.is_file()}
            prediction = experiment.predict(path, "query", "1")
            self.assertEqual(prediction["prediction"], "MOT")
            self.assertEqual(prediction["score"], 1)
            self.assertEqual(prediction["neighbors"][0]["meeting_id"], "history")
            self.assertEqual(prediction["api_calls"], 0)
            self.assertEqual(before, {str(item): item.read_bytes() for item in path.rglob("*") if item.is_file()})
            with self.assertRaisesRegex(ValueError, "Select one proposal"):
                experiment.predict(path, "missing", "1")
            with (path / "development-vectors.npz").open("ab") as handle:
                handle.write(b"changed")
            with self.assertRaisesRegex(ValueError, "Saved experiment artifact changed"):
                experiment.predict(path, "query", "1")


if __name__ == "__main__":
    unittest.main()
