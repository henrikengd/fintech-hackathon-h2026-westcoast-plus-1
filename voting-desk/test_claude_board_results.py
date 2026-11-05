"""Matched denominators, partial runs and honest labels in the Claude comparison."""
import json
from pathlib import Path
import tempfile
import unittest

import claude_board_results
import rag_results


def metrics(n=100, positive=20, precision=.6):
    return {"n": n, "positive": positive, "precision": precision, "recall": .5, "f1": .54,
            "tp": 10, "fp": 7, "fn": 10, "tn": 73, "covered": 95, "uncovered": 5,
            "recommendation_coverage": .95}


def report():
    return {"target": "against_board", "model": "claude-sonnet-5-5",
            "evaluation_kind": "EXPOSED_2024_DEVELOPMENT", "scope": "historical_votes_only",
            "cohort": {"rows": 200, "meetings": 20, "positive": 40},
            "attempted_meetings": 10, "completed_meetings": 9, "failed_meetings": 1,
            "unattempted_meetings": 10, "attempted_rows": 100, "complete": False,
            "claude": {"disagreement": metrics(), "literal_mot": metrics(precision=.987)},
            "same_rows_local": {"at_calibration_threshold": metrics(precision=.7),
                                "at_validation_threshold": metrics(precision=.65)},
            "usage": {"input_tokens": 12345, "output_tokens": 1234}, "api_calls": 10,
            "estimated_usd": .04, "history_policy": "strict_before_meeting_minus_5_days",
            "test_evaluated": False}


class ClaudeBoardResults(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)

    def render(self, data=None):
        if data is not None:
            (self.base / "report.json").write_text(json.dumps(data), encoding="utf-8")
        return claude_board_results.render_section(self.base)

    def test_missing_invalid_and_wrong_target_reports_do_not_show_scores(self):
        self.assertIn("ikke lagret ennå", self.render())
        (self.base / "report.json").write_text("{unfinished", encoding="utf-8")
        self.assertIn("kan ikke leses nå", self.render())
        for field, value in (("target", "mot"), ("evaluation_kind", "FINAL_TEST"), ("scope", "documents")):
            data = report()
            data[field] = value
            with self.subTest(field=field):
                html = self.render(data)
                self.assertIn("Ingen sammenligning vises", html)
                self.assertNotIn("60,0 %", html)

    def test_partial_run_uses_only_attempted_rows_including_failures(self):
        html = self.render(report())
        self.assertIn("Foreløpige resultater", html)
        self.assertIn("9 / 20 møter har fullførte svar", html)
        self.assertIn("1 møter feilet og 10 er ikke forsøkt", html)
        self.assertIn("samme 100 forsøkte saker", html)
        self.assertNotIn("samme 200", html)
        self.assertIn("beholdes i målingen", html)
        self.assertIn("falskt negativt", html)
        self.assertIn("ikke er forsøkt, inngår ikke", html)
        self.assertIn("Et nullsvar betyr ukjent", html)

    def test_full_run_does_not_hide_failed_calls_or_become_final_test(self):
        data = report()
        data.update(attempted_meetings=20, completed_meetings=19, unattempted_meetings=0,
                    complete=True, attempted_rows=200)
        for group in (data["claude"], data["same_rows_local"]):
            for value in group.values():
                value.update(n=200, positive=40)
        html = self.render(data)
        self.assertIn("Alle møter er forsøkt", html)
        self.assertIn("19 / 20 møter", html)
        self.assertIn("1 møter feilet", html)
        self.assertIn("ikke en uavhengig sluttest", html)
        self.assertIn("2025–2026 er ikke kjørt på nytt", html)
        data["unattempted_meetings"] = 5
        html = self.render(data)
        self.assertIn("ufullstendig eller motstridende", html)
        self.assertNotIn("Alle møter er forsøkt", html)

    def test_local_references_require_same_denominators_and_target_counts(self):
        data = report()
        data["same_rows_local"]["at_calibration_threshold"].update(n=200, precision=.991)
        data["same_rows_local"]["at_validation_threshold"].update(positive=21, precision=.992)
        html = self.render(data)
        self.assertIn("er utelatt", html)
        self.assertNotIn("99,1 %", html)
        self.assertNotIn("99,2 %", html)
        data["attempted_rows"] = 200
        html = self.render(data)
        self.assertIn("Ingen sammenlignbar måling", html)
        self.assertNotIn("60,0 %", html)

    def test_mot_remains_separate_and_no_guideline_grounding_is_claimed(self):
        html = self.render(report())
        primary = html.split("<table>", 1)[1].split("</table>", 1)[0]
        self.assertIn("60,0 %", primary)
        self.assertNotIn("98,7 %", primary)
        self.assertIn("MOT målt separat · Claude", html)
        self.assertIn("98,7 %", html)
        self.assertIn("ikke innkallinger eller retningslinjer", html)
        self.assertIn("ikke kildebelagte stemmeanbefalinger", html)
        self.assertIn("mer enn fem dager eldre", html)
        self.assertIn("allerede valgt med 2024-utfallene", html)
        self.assertNotIn("85 prosent er nådd", html)

    def test_only_escaped_allowlisted_aggregates_are_exposed(self):
        data = report()
        data.update(model="<script>alert(1)</script>", api_key="SECRET_SENTINEL",
                    bundles=["PROMPT_SENTINEL"], raw_reply="REPLY_SENTINEL")
        data["claude"]["disagreement"]["precision"] = None
        html = self.render(data)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("<td>—</td>", html)
        for forbidden in ("<script", "<form", "file://", "SECRET_SENTINEL", "PROMPT_SENTINEL", "REPLY_SENTINEL"):
            self.assertNotIn(forbidden, html)

    def test_absent_or_nonfinite_cost_and_unknown_test_status_are_not_invented(self):
        for invalid in (None, float("nan"), float("inf"), -1, True):
            data = report()
            data.update(estimated_usd=invalid, test_evaluated=None)
            with self.subTest(invalid=invalid):
                html = self.render(data)
                self.assertNotIn("Beregnet API-kostnad:", html)
                self.assertNotIn("2025–2026 er ikke kjørt", html)
                self.assertIn("Ingen testscore vises", html)

    def test_results_page_wires_new_section_between_active_and_older_models(self):
        path = self.base / "claude-board-v1"
        path.mkdir()
        (path / "report.json").write_text(json.dumps(report()), encoding="utf-8")
        html = rag_results.render_body(self.base)
        self.assertLess(html.index("Avvik fra styrets anbefaling · tidligere balansevalg"),
                        html.index("Claude + lokalt søk i historiske stemmer"))
        self.assertLess(html.index("Claude + lokalt søk i historiske stemmer"),
                        html.index("Tidligere forsøk · MOT på forslaget"))
        self.assertIn("Claude med historiske treff: Tilgjengelig", html)


if __name__ == "__main__":
    unittest.main()
