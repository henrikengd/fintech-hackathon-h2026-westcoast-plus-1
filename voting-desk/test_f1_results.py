"""F1-first display without test reuse, mismatched cohorts, or invented metrics."""
import json
from pathlib import Path
import tempfile
import unittest

import f1_results
import rag_results


def metrics(f1=.6, n=100, positive=20):
    return {"n": n, "positive": positive, "precision": .75, "recall": .5,
            "f1": f1, "tp": 10, "fp": 3, "fn": 10, "tn": 77}


def report():
    validation = metrics(.51, 80, 15)
    return {"objective": "maximize_f1", "target": "against_board", "evaluation_kind": "EXPOSED_2024_CALIBRATION",
            "test_evaluated": False, "october_test_unchanged": True, "selected_config": {"name": "semantic-history-boost"},
            "selected_threshold": .24, "validation_threshold": .27, "model_reused": True, "api_calls": 0,
            "calibration": {"rows": 100, "positive": 20}, "calibration_selected": metrics(.62),
            "calibration_at_validation_threshold": metrics(.61), "model_selection_validation": validation,
            "candidates": [{"rank": 1, "config": {"name": "semantic-history-boost"}, "threshold": .27, "validation": validation},
                           {"rank": 2, "config": {"name": "text-history-0.3"}, "threshold": .3, "validation": metrics(.46, 80, 15)}],
            "comparators": {"previous_balanced": {"threshold": .22, "metrics": metrics(.60)},
                            "cached_claude": {"model": "claude-sonnet-5-5", "metrics": metrics(.57), "failed_meetings": 5, "complete": True},
                            "follow_board": {"metrics": {**metrics(0), "precision": None, "recall": 0, "tp": 0, "fp": 0, "fn": 20}}}}


class F1Results(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)

    def render(self, data=None):
        if data is not None:
            (self.base / "summary.json").write_text(json.dumps(data), encoding="utf-8")
        return f1_results.render_section(self.base)

    def test_missing_malformed_and_wrong_protocol_never_show_scores(self):
        self.assertIn("ikke lagret ennå", self.render())
        (self.base / "summary.json").write_text("{unfinished", encoding="utf-8")
        self.assertIn("kan ikke leses", self.render())
        for value in ([], "not an object", 1):
            self.assertNotIn("<table>", self.render(value))
        for key, value in (("objective", "balanced"), ("target", "mot"),
                           ("evaluation_kind", "FROZEN_NEW_MEETINGS"), ("test_evaluated", True), ("october_test_unchanged", None)):
            data = report()
            data[key] = value
            with self.subTest(key=key):
                html = self.render(data)
                self.assertIn("Ingen sammenligning vises", html)
                self.assertNotIn("62,0 %", html)

    def test_primary_table_puts_f1_first_and_labels_calibration_as_exposed(self):
        html = self.render(report())
        primary = html.split("<table>", 1)[1].split("</table>", 1)[0]
        self.assertLess(primary.index(">F1<"), primary.index(">Precision<"))
        for expected in ("harmoniske gjennomsnittet", "samme ferdigtrente modellen", "modellvektene er uendret",
                         "ikke en ny uavhengig test", "uten at terskelen er tilpasset 2024-utfallene", "Samme 100 saker fra 2024 med 20 faktiske avvik",
                         "F1-terskel fra 2020–2023", "F1-terskel valgt på 2024", "62,0 %", "61,0 %", "57,0 %",
                         "5 feilede møter beholdes", "ikke endret Claude-prompten", "ikke testet på oktober",
                         "oktoberutfallene er ikke brukt", "annen måldefinisjon", "Nye API-kall: 0"):
            self.assertIn(expected, html)
        self.assertNotIn("85", html)

    def test_primary_cohort_counts_and_actual_positive_counts_must_match(self):
        for section, key, value in (("calibration", "rows", 99), ("calibration", "positive", 19),
                                    ("calibration_at_validation_threshold", "n", 99),
                                    ("calibration_at_validation_threshold", "positive", True)):
            data = report()
            data[section][key] = value
            self.assertIn("Måleutvalgene stemmer ikke overens", self.render(data))
        for key in ("calibration_selected", "calibration_at_validation_threshold", "calibration"):
            for value in (None, [], 1):
                data = report()
                data[key] = value
                self.assertNotIn("<table>", self.render(data))

    def test_incompatible_comparators_and_candidate_cohorts_are_omitted(self):
        data = report()
        data["comparators"]["cached_claude"]["metrics"].update(n=99, f1=.987)
        data["comparators"]["previous_balanced"]["metrics"].update(positive=21, f1=.986)
        data["candidates"][1]["validation"].update(positive=16, f1=.985)
        html = self.render(data)
        self.assertIn("Referanser med andre eller ukjente nevnere", html)
        for forbidden in ("98,7 %", "98,6 %", "98,5 %", "text-history-0.3", "5 feilede møter"):
            self.assertNotIn(forbidden, html)
        self.assertIn("Modellvalg på 80 saker med 15 avvik", html)
        data = report()
        data["comparators"]["cached_claude"]["complete"] = False
        html = self.render(data)
        self.assertIn("ufullførte Claude-kjøringer", html)
        self.assertNotIn("57,0 %", html)
        self.assertNotIn("5 feilede møter", html)

    def test_invalid_metrics_are_dashes_and_raw_fields_are_never_rendered(self):
        data = report()
        data["selected_config"]["name"] = "<script>bad()</script>"
        data["candidates"][0]["config"]["name"] = "<img src=x>"
        data.update(secret="SECRET_SENTINEL", raw_responses="REPLY_SENTINEL", prompt="PROMPT_SENTINEL")
        for value in (None, float("nan"), float("inf"), True, -.1, 1.1):
            data["calibration_selected"]["f1"] = value
            html = self.render(data)
            self.assertIn("F1 etter terskelvalg på 2024: <strong>—</strong>", html)
            self.assertIn("&lt;script&gt;", html)
            self.assertIn("&lt;img", html)
            for forbidden in ("<script", "<img", "<form", "SECRET_SENTINEL", "REPLY_SENTINEL", "PROMPT_SENTINEL"):
                self.assertNotIn(forbidden, html)

    def test_full_page_orders_active_f1_then_october_then_collapsed_history(self):
        f1 = self.base / "f1-board-v1"
        f1.mkdir()
        (f1 / "summary.json").write_text(json.dumps(report()), encoding="utf-8")
        fresh = self.base / "fresh-test-2026-10-v1"
        fresh.mkdir()
        (fresh / "selection-policy.json").write_text(json.dumps({"date_start": "2026-10-01", "date_end": "2026-10-31"}))
        html = rag_results.render_body(self.base)
        self.assertLess(html.index("<h2>Aktivt modellvalg"), html.index("<h2>Nye møter"))
        history = html.index("<details><summary>Tidligere modellforsøk og målinger")
        self.assertLess(html.index("<h2>Nye møter"), history)
        self.assertNotIn("85", html[:history])
        self.assertIn("Tidligere prosentmål er avsluttet", html[history:])
        self.assertIn("Aktivt F1-valg: Tilgjengelig", html)


if __name__ == "__main__":
    unittest.main()
