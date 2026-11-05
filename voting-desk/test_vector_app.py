"""Read-only vector explorer boundaries and truthful historical-neighbor display."""
import csv
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import rag_app
import vector_app


def proposal(item="1"):
    return {"meeting_id": "123", "item_no": item, "company": "Example Corp", "meeting_date": "2024-04-01",
            "proposal_text": "Approve executive compensation", "mgmt_rec": "FOR", "proponent": "Management",
            "score": 0, "prediction": "MOT", "history_count": 500, "neighbor_count": 10,
            "neighbor_vote_counts": {"FOR": 9, "MOT": 1, "AVSTÅ": 0}, "conflicting_votes": True,
            "neighbors": [{"company": "Older Company", "meeting_date": "2023-01-01", "proposal_text": f"Historical proposal {i}",
                           "nbim_vote": "FOR", "similarity": .8, "weight": .02} for i in range(8)]}


class VectorRendering(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)

    def save(self, items=None, summary=None):
        (self.base / "summary.json").write_text(json.dumps(summary if summary is not None else {"selected_threshold": 0}), encoding="utf-8")
        (self.base / "neighbors.json").write_text(json.dumps({"items": items if items is not None else [proposal()]}), encoding="utf-8")
        with (self.base / "development.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["meeting_id", "item_no", "nbim_vote"])
            writer.writeheader()
            writer.writerow({"meeting_id": "123", "item_no": "1", "nbim_vote": "FOR"})

    def test_missing_incomplete_and_invalid_json_artifacts_are_pending(self):
        self.assertIn("ikke klare", vector_app.render_body(base=self.base)[1])
        self.save(summary={})
        self.assertIn("ikke klare", vector_app.render_body(base=self.base)[1])
        self.save()
        (self.base / "neighbors.json").write_text("{unfinished", encoding="utf-8")
        self.assertEqual(vector_app.render_body(base=self.base)[0], 200)
        self.assertIn("ikke klare", vector_app.render_body(base=self.base)[1])

    def test_search_is_limited_to_twenty_and_does_not_read_outcome_labels(self):
        self.save([proposal(str(i)) for i in range(25)])
        with patch.object(vector_app, "outcome") as outcome:
            code, html = vector_app.render_body(query="example compensation", base=self.base)
            self.assertEqual(code, 200)
            self.assertIn("Viser 20 av 25 treff", html)
            self.assertEqual(html.count('href="/vector?meeting='), 20)
            self.assertNotIn('item=24"', html)
            self.assertNotIn("fasit til etterkontroll", html)
            outcome.assert_not_called()

    def test_detail_displays_only_five_neighbors_but_explains_all_ten(self):
        self.save()
        code, html = vector_app.render_body(meeting="123", item="1", base=self.base)
        self.assertEqual(code, 200)
        self.assertIn("10 naboer ble brukt av 500", html)
        self.assertIn("Historisk sak", html)
        self.assertIn("Historical proposal 4", html)
        self.assertNotIn("Historical proposal 5", html)
        self.assertIn("Modellens klassifikasjon: MOT", html)
        self.assertIn("Rå modellskår: <strong>0</strong>", html)
        self.assertIn("terskel for MOT: <strong>0</strong>", html)
        self.assertIn("Skår lik eller over terskelen gir MOT", html)
        self.assertIn("ikke en kalibrert sannsynlighet", html)
        self.assertIn("Registrert NBIM-stemme: <strong>FOR</strong>", html)
        self.assertGreater(html.index("fasit til etterkontroll"), html.index("Historiske saker bak klassifikasjonen"))

    def test_sources_and_query_are_escaped_and_extra_fields_are_never_exported(self):
        item = proposal()
        item["company"] = '<script>alert("company")</script>'
        item["neighbors"][0]["proposal_text"] = '<img src=x onerror="alert(1)">'
        item["api_key"] = "SECRET_SENTINEL"
        item["raw_bundle"] = "RAW_SENTINEL"
        self.save([item])
        html = vector_app.render_body(meeting="123", item="1", base=self.base)[1]
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("&lt;img", html)
        for forbidden in ("<script>", "<img src", "SECRET_SENTINEL", "RAW_SENTINEL", "file://"):
            self.assertNotIn(forbidden, html)
        search = vector_app.render_body(query='"><script>alert(1)</script>', base=self.base)[1]
        self.assertNotIn('<script>', search)
        self.assertIn('&quot;&gt;&lt;script&gt;', search)

    def test_invalid_identifiers_never_become_file_paths(self):
        with patch.object(vector_app, "read_snapshots") as read:
            for values in ({"meeting": "../.env", "item": "1"}, {"meeting": "123"}, {"item": "1"}, {"query": "x" * 201}):
                with self.subTest(values=values):
                    self.assertEqual(vector_app.render_body(base=self.base, **values)[0], 400)
            read.assert_not_called()

    def test_unknown_duplicate_and_missing_history_details_are_explicit(self):
        self.save()
        self.assertEqual(vector_app.render_body(meeting="missing", item="1", base=self.base)[0], 404)
        self.save([proposal(), proposal()])
        self.assertEqual(vector_app.render_body(meeting="123", item="1", base=self.base)[0], 503)
        item = {**proposal(), "score": None, "prediction": "UNKNOWN", "neighbors": []}
        self.save([item])
        (self.base / "development.csv").unlink()
        html = vector_app.render_body(meeting="123", item="1", base=self.base)[1]
        self.assertIn("Ukjent · ingen klassifikasjon", html)
        self.assertIn("Rå modellskår: <strong>—</strong>", html)
        self.assertIn("Ingen historiske naboer", html)
        self.assertIn("Ikke tilgjengelig", html)


class VectorRoute(unittest.TestCase):
    def handler(self, path):
        handler = object.__new__(rag_app.Handler)
        handler.path = path
        handler.server = SimpleNamespace(server_port=8502, index=Mock())
        handler.headers = {"Host": "127.0.0.1:8502"}
        handler.send, handler.reply = Mock(), Mock()
        return handler

    def test_route_forwards_only_search_and_item_identifiers(self):
        handler = self.handler("/vector?q=Tesla&path=.env&generate=true")
        with patch.object(vector_app, "render_body", return_value=(200, "<main>Saved results</main>")) as render:
            handler.do_GET()
            render.assert_called_once_with(query="Tesla", meeting="", item="")
        self.assertEqual(handler.send.call_args.args[0], 200)
        handler.server.index.search.assert_not_called()

    def test_artifact_paths_are_not_download_endpoints(self):
        handler = self.handler("/vector-experiment-v1/neighbors.json")
        handler.do_GET()
        self.assertEqual(handler.reply.call_args.args[0], 404)


if __name__ == "__main__":
    unittest.main()
