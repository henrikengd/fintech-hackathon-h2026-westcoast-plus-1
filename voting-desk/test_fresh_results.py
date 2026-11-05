"""Read-only fresh-test aggregates, matching denominators and honest limitations."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import fresh_results
import rag_results


def metrics(precision=.5):
    return {"n": 10, "positive": 2, "tp": 1, "fp": 1, "fn": 1, "tn": 7,
            "precision": precision, "recall": .5, "f1": .5,
            "covered": 8, "uncovered": 2, "recommendation_coverage": .8}


def report():
    return {"evaluation_kind": "FROZEN_NEW_MEETINGS", "target": "against_board",
            "cohort": {"rows": 12, "meetings": 3}, "known_disagreement_rows": 10,
            "unknown_nbim": 1, "known_nbim_unknown_board": 1,
            "local": metrics(.75), "claude": metrics(),
            "claude_literal_mot": {"n": 11, "precision": .987, "recall": .9, "f1": .94},
            "failed_meetings": [{"meeting_id": "failed", "reason": "PRIVATE_FAILURE_DETAIL"}],
            "claude_model": "claude-sonnet-5-5", "local_threshold": .225399,
            "api_attempts": 3}


class FreshResults(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.policy = {"date_start": "2026-10-01", "date_end": "2026-10-31"}
        self.save("selection-policy.json", self.policy)

    def save(self, name, data):
        (self.base / name).write_text(json.dumps(data), encoding="utf-8")

    def render(self, data=None):
        if data is not None:
            self.save("report.json", data)
        return fresh_results.render_section(self.base)

    def test_missing_report_has_complete_pending_section_and_no_invented_score(self):
        html = self.render()
        self.assertIn("Ingen ny testscore er publisert ennå", html)
        self.assertIn("Resultatene fra 2024 nedenfor er fortsatt utviklingsmålinger", html)
        self.assertTrue(html.endswith("</p></section>"))
        self.assertNotIn("<table>", html)
        (self.base / "selection-policy.json").unlink()
        self.assertEqual(self.render(), "")

    def test_malformed_policy_and_report_are_safe_readable_states(self):
        (self.base / "selection-policy.json").write_text("{unfinished", encoding="utf-8")
        self.assertIn("Testprotokollen kan ikke leses", self.render())
        for value in (None, [], "not an object", 1):
            with self.subTest(policy=value):
                self.save("selection-policy.json", value)
                self.assertIn("Testprotokollen har ugyldig format", self.render())
        self.save("selection-policy.json", self.policy)
        (self.base / "report.json").write_text("{unfinished", encoding="utf-8")
        self.assertIn("Testrapporten kan ikke leses", self.render())
        for value in (None, [], "not an object", 1):
            with self.subTest(report=value):
                self.save("report.json", value)
                self.assertNotIn("<table>", self.render())

    def test_wrong_target_or_development_report_never_becomes_new_test(self):
        for field, value in (("target", "mot"), ("evaluation_kind", "EXPOSED_2024_DEVELOPMENT")):
            data = report()
            data[field] = value
            html = self.render(data)
            self.assertIn("ikke riktig testtype og måldefinisjon", html)
            self.assertNotIn("75,0 %", html)

    def test_denominators_and_unknown_label_partition_must_match(self):
        edits = [("local", "n", 11), ("claude", "positive", 3), ("claude", "n", True),
                 ("cohort", "rows", 13), ("cohort", "meetings", 0)]
        for section, field, value in edits:
            data = report()
            data[section][field] = value
            with self.subTest(section=section, field=field, value=value):
                html = self.render(data)
                self.assertIn("Sammenligningen er utelatt", html)
                self.assertNotIn("<table>", html)
        for key in ("local", "claude", "cohort"):
            for value in (None, [], 1):
                data = report()
                data[key] = value
                self.assertIn("Sammenligningen er utelatt", self.render(data))
        for key in ("known_disagreement_rows", "unknown_nbim", "known_nbim_unknown_board"):
            for value in (None, -1, True):
                data = report()
                data[key] = value
                self.assertIn("Sammenligningen er utelatt", self.render(data))

    def test_low_positive_count_failed_coverage_and_scope_are_explained(self):
        html = self.render(report())
        for text in ("12 forslag fra 3 møter", "10 forslag har kjent", "2 faktiske avvik",
                     "Lite grunnlag for å vurdere recall", "bare 2 faktiske avvik", "stor usikkerhet om F1",
                     "Prediksjonsdekning blant de 10 målbare forslagene", "Claude 80,0 %",
                     "1 Claude-møter ga ikke et godkjent svar", "Saker uten prediksjon beholdes i målingen",
                     "teller som oversett avvik", "Ingen nye testutfall inngår i historikken",
                     "ikke et representativt utvalg", "publiserte stemmeintensjoner"):
            self.assertIn(text, html)
        self.assertNotIn("PRIVATE_FAILURE_DETAIL", html)
        self.assertNotIn("målet er nådd", html)
        self.assertNotIn("85 %", html)
        self.assertIn("Den nye F1-terskelen er ikke testet", html)

    def test_undefined_and_invalid_metrics_are_dashes_not_zero(self):
        for value in (None, float("nan"), float("inf"), -.1, 1.1, True):
            data = report()
            for section in ("local", "claude"):
                data[section].update(precision=value, recall=value, f1=value)
            with self.subTest(value=value):
                html = self.render(data)
                self.assertIn("<td>—</td><td>—</td><td>—</td>", html)
                self.assertIn("En strek betyr", html)
                self.assertNotIn("<td>0,0 %</td>", html)
        data = report()
        for section in ("local", "claude"):
            data[section].update(positive=0, tp=0, fn=0, precision=None, recall=None, f1=None)
        self.assertIn("0 faktiske avvik", self.render(data))

    def test_empty_scorable_cohort_keeps_full_forecast_count_visible(self):
        data = report()
        data.update(known_disagreement_rows=0, unknown_nbim=11, known_nbim_unknown_board=1)
        for section in ("local", "claude"):
            data[section] = {"n": 0, "positive": 0, "precision": None, "recall": None, "f1": None}
        html = self.render(data)
        self.assertIn("12 forslag fra 3 møter", html)
        self.assertIn("0 forslag har kjent", html)
        self.assertIn("lokal modell —, Claude —", html)
        self.assertNotIn("MOT målt separat", html)

    def test_mot_is_separate_and_requires_its_correct_known_vote_count(self):
        data = report()
        html = self.render(data)
        primary = html.split("<table>", 1)[1].split("</table>", 1)[0]
        self.assertNotIn("98,7 %", primary)
        self.assertIn("MOT målt separat · Claude", html)
        self.assertIn("98,7 %", html)
        self.assertIn("11 forslag med kjent NBIM-stemme", html)
        for value in (None, [], {"n": 10, "precision": .987}):
            data["claude_literal_mot"] = value
            self.assertNotIn("MOT målt separat", self.render(data))

    def test_only_escaped_aggregate_fields_and_protocol_are_read(self):
        data = report()
        data.update(claude_model="<script>unsafe()</script>", local_threshold="<img src=x>",
                    api_key="SECRET_SENTINEL", bundles=["PROMPT_SENTINEL"], raw_reply="REPLY_SENTINEL")
        self.policy["date_start"] = "<svg onload=alert(1)>"
        self.save("selection-policy.json", self.policy)
        self.save("report.json", data)
        original_read = Path.read_text
        reads = []

        def read(path, *args, **kwargs):
            reads.append(path.name)
            return original_read(path, *args, **kwargs)

        with patch.object(Path, "read_text", read), patch.object(Path, "write_text", side_effect=AssertionError("Read-only view")):
            html = self.render()
        self.assertEqual(reads, ["selection-policy.json", "report.json"])
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("&lt;svg", html)
        self.assertIn("&lt;img", html)
        for forbidden in ("<script", "<svg", "<img", "<form", "SECRET_SENTINEL", "PROMPT_SENTINEL", "REPLY_SENTINEL"):
            self.assertNotIn(forbidden, html)

    def test_full_page_places_fresh_results_before_old_2024_calibration(self):
        fresh = self.base / "fresh-test-2026-10-v1"
        fresh.mkdir()
        (fresh / "selection-policy.json").write_text(json.dumps(self.policy), encoding="utf-8")
        (fresh / "report.json").write_text(json.dumps(report()), encoding="utf-8")
        html = rag_results.render_body(self.base)
        self.assertLess(html.index("<h2>Nye møter"), html.index("<h2>Kalibrering og utviklingsmålinger · 2024"))
        self.assertLess(html.index("<h2>Kalibrering og utviklingsmålinger · 2024"), html.index("<h2>Avvik fra styrets anbefaling"))
        self.assertIn("Kalibrering og utviklingsmålinger er ikke en ny, uavhengig sluttest", html)
        self.assertIn("Nye møter · låst test: Tilgjengelig", html)


if __name__ == "__main__":
    unittest.main()
