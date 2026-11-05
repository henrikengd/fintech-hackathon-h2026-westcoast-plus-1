import json
from pathlib import Path
import tempfile
import unittest

import relevance_results as rr


class RelevanceResultsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def save(self, path, value):
        target = self.base / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(value))

    def test_absent_artifacts_add_no_section(self):
        self.assertEqual(rr.render_section(self.base), "")

    def test_incomplete_claude_scores_are_hidden(self):
        self.save("relevance-claude-v1/report.json", {"target": "against_board", "test_evaluated": False,
                  "evaluation_kind": "EXPOSED_2024_DEVELOPMENT", "complete": False,
                  "completed_calls": 7, "failed_calls": 1, "planned_calls": 20,
                  "overall": {"previous_claude": {"f1": .999}}})
        html = rr.render_section(self.base)
        self.assertIn("7 vellykkede", html)
        self.assertNotIn("99,9", html)

    def test_matched_full_and_filing_cohorts_separate(self):
        metric = {"n": 100, "positive": 8, "f1": .6, "precision": .5, "recall": .75, "tp": 6, "fp": 6, "fn": 2}
        subset = {**metric, "n": 20}
        self.save("relevance-claude-v1/report.json", {"target": "against_board", "test_evaluated": False,
                  "evaluation_kind": "EXPOSED_2024_DEVELOPMENT", "complete": True,
                  "overall": {name: metric for name in ("previous_claude", "hybrid_history", "hybrid_evidence")},
                  "filing_subset": {name: subset for name in ("previous_claude", "hybrid_history", "hybrid_evidence")}})
        html = rr.render_section(self.base)
        self.assertIn("100 saker", html)
        self.assertIn("20 saker", html)
        self.assertIn("ikke en ny urørt test", html)
        self.assertEqual(html.count("60,0 %"), 6)

    def test_local_selected_name_escaped(self):
        self.save("relevance-board-v1/summary.json", {"target": "against_board", "test_evaluated": False,
                  "evaluation_kind": "EXPOSED_2024_CALIBRATION", "selected_config": {"name": "<script>"}})
        html = rr.render_section(self.base)
        self.assertIn("&lt;script&gt;", html)
        self.assertNotIn("<script>", html)


if __name__ == "__main__":
    unittest.main()
