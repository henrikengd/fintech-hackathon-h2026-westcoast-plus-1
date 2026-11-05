"""Target identity, calibration honesty, and aggregate-only rendering."""
import json
from pathlib import Path
import tempfile
import unittest

import board_results


def metrics(precision=.6, recall=.5, n=100, positive=20):
    return {"n": n, "positive": positive, "precision": precision, "recall": recall,
            "f1": .54, "tp": 10, "fp": 7, "fn": 10, "tn": 73}


def summary():
    return {"target": "against_board", "positive_class": "NBIM != mgmt_rec", "api_calls": 0,
            "fit_period": "2019–2023", "calibration_period": "2024", "test_period": "2025–2026",
            "test_evaluated": False, "fit": {"rows": 1000, "positive": 50},
            "calibration": {"rows": 100, "positive": 20}, "selected_config": {"name": "Local model"},
            "selected_threshold": .5, "model_selection_validation": metrics(.3, .4, 80, 10),
            "calibration_selected": metrics(), "calibration_at_validation_threshold": metrics(.7, .4),
            "calibration_no_disagreement": {**metrics(None, 0), "tp": 0, "fp": 0, "fn": 20},
            "history_policy": "walk_forward_5d", "rules_used": False}


class BoardResults(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)

    def render(self, data=None):
        if data is not None:
            (self.base / "summary.json").write_text(json.dumps(data), encoding="utf-8")
        return board_results.render_section(self.base)

    def test_absent_or_partial_artifact_is_explicit_without_changing_target(self):
        html = self.render()
        self.assertIn("NBIM ≠ styrets anbefaling", html)
        self.assertIn("ikke lagret ennå", html)
        (self.base / "summary.json").write_text("{unfinished", encoding="utf-8")
        self.assertIn("Rapporten kan ikke leses", self.render())
        self.assertIn("riktig måldefinisjon", self.render({"target": "literal_mot"}))

    def test_primary_target_examples_and_chronological_boundaries_are_clear(self):
        html = self.render(summary())
        self.assertIn("styret anbefaler MOT og NBIM stemmer FOR → avvik", html)
        self.assertIn("Styret anbefaler MOT og NBIM stemmer MOT → ikke avvik", html)
        self.assertIn("Testsettet er ikke kjørt på nytt", html)
        self.assertIn("tilpasset måling på kalibreringsdata", html)
        self.assertIn("De samme utfallene brukes til å velge terskel", html)
        self.assertIn("tidligere stemmer fra 2024 kan brukes", html)
        self.assertIn("mer enn fem dager eldre", html)
        self.assertIn("Denne lokale modellen bruker ikke retningslinjer", html)
        self.assertIn("1000 saker, hvorav 50 faktiske avvik", html)

    def test_calibration_and_model_selection_validation_are_not_pooled(self):
        html = self.render(summary())
        self.assertIn("samme 100 kalibreringssaker", html)
        self.assertIn("Modellvalg · eget valideringsutvalg", html)
        self.assertIn("30,0 %", html)
        self.assertIn("60,0 %", html)
        self.assertIn("Ingen avvik · følg alltid styret", html)
        self.assertIn("<td>—</td>", html)
        self.assertIn("<td>0,0 %</td>", html)

    def test_old_percentage_targets_are_retired_and_history_is_preserved(self):
        for p, r in ((.85, .9), (.9, .85), (.85, .85), (.84, 1)):
            data = summary()
            data["calibration_selected"] = metrics(p, r)
            with self.subTest(p=p, r=r):
                html = self.render(data)
                self.assertIn("tidligere balansevalg", html)
                self.assertIn("Det aktive modellvalget prioriterer nå F1", html)
                self.assertNotIn("Det felles målet", html)
                self.assertNotIn("ligger begge strengt over", html)

    def test_nonfinite_missing_and_invalid_metrics_cannot_imply_success(self):
        for value in (None, float("nan"), float("inf"), True, -.1, 1.1):
            data = summary()
            data["calibration_selected"]["precision"] = value
            with self.subTest(value=value):
                html = self.render(data)
                self.assertIn("<td>—</td>", html)
                self.assertNotIn("ligger begge strengt over", html)

    def test_references_require_same_n_and_positive_count(self):
        data = summary()
        data["calibration_at_validation_threshold"] = metrics(.987, n=99)
        data["calibration_no_disagreement"] = metrics(.986, positive=21)
        html = self.render(data)
        self.assertNotIn("98,7 %", html)
        self.assertNotIn("98,6 %", html)
        self.assertIn("Referanser med et annet eller ukjent antall", html)

    def test_literal_mot_auxiliary_and_raw_fields_are_not_mislabeled_as_primary(self):
        data = summary()
        data["historical_vote_reference"] = {"against_board": metrics(.234), "mot": {**metrics(.987), "mot": 8}, "note": "PRIVATE_NOTE"}
        data["calibration_mot_auxiliary"] = {"precision": .986, "raw_votes": "RAW_VOTES"}
        data["secret"] = "SECRET_SENTINEL"
        html = self.render(data)
        self.assertIn("23,4 %", html)
        primary_table = html.split("<table>", 1)[1].split("</table>", 1)[0]
        self.assertNotIn("98,7 %", primary_table)
        self.assertIn("98,7 %", html)
        self.assertIn("MOT målt separat · tidligere agents lagrede stemmer", html)
        self.assertIn("MOT-precision og MOT-recall er ikke definert for denne binære modellen", html)
        for forbidden in ("98,6 %", "RAW_VOTES", "SECRET_SENTINEL", "PRIVATE_NOTE", "<form", "<script", "file://"):
            self.assertNotIn(forbidden, html)
        self.assertIn("MOT-måling inngår ikke i denne avvikstabellen", html)

    def test_metadata_is_escaped_and_test_status_is_not_invented(self):
        data = summary()
        data["selected_config"]["name"] = "<script>bad()</script>"
        data["calibration_period"] = "<img src=x>"
        data["test_evaluated"] = None
        html = self.render(data)
        self.assertNotIn("<script>", html)
        self.assertNotIn("<img src", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("Teststatus er ikke oppgitt", html)
        self.assertNotIn("Testsettet er ikke kjørt på nytt", html)
        data["test_evaluated"] = True
        self.assertIn("markerer testsettet som evaluert", self.render(data))


if __name__ == "__main__":
    unittest.main()
