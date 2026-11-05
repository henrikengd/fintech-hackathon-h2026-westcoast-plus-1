"""Source rendering and request-boundary tests for the local evidence explorer."""
import boot  # noqa: F401
import http.client
from http.server import HTTPServer
import json
import threading
import unittest
from unittest.mock import patch

import rag_app


DOCUMENT = {
    "id": "doc-1", "company": "Example <Company>", "meeting_date": "2024-06-01",
    "filed": "2024-04-01", "url": "https://www.sec.gov/example?a=1&b=2",
    "text": "Before <script>alert(1)</script> after",
}


class FakeIndex:
    def __init__(self):
        self.calls = []

    def status(self):
        return {"documents": 1, "chunks": 2, "model": "test"}

    def meetings(self):
        return [{"meeting_id": "123", "company": "Example", "meeting_date": "2024-06-01"}]

    def search(self, query, meeting_id, **kwargs):
        self.calls.append((query, meeting_id, kwargs))
        return [{"text": "evidence"}]

    def document(self, document_id):
        return DOCUMENT if document_id == "doc-1" else None


class SourceRendering(unittest.TestCase):
    def test_source_text_and_metadata_are_escaped_without_changing_selection(self):
        html = rag_app.source_page(DOCUMENT, 7, 32)
        self.assertIn('<mark id="excerpt">&lt;script&gt;alert(1)&lt;/script&gt;</mark>', html)
        self.assertIn("Example &lt;Company&gt;", html)
        self.assertNotIn("<script>alert", html)
        self.assertIn("?a=1&amp;b=2", html)

    def test_only_https_sec_links_are_clickable(self):
        for url in ("javascript:alert(1)", "https://sec.gov.evil.test/file", "https://user@www.sec.gov/file", "http://www.sec.gov/file", "https://sec.gov:8080/file"):
            with self.subTest(url=url):
                self.assertFalse(rag_app.safe_sec_url(url))
                self.assertNotIn("Originaldokument hos SEC", rag_app.source_page({**DOCUMENT, "url": url}))
        self.assertTrue(rag_app.safe_sec_url("https://www.sec.gov/Archives/file.htm"))

    def test_out_of_range_or_reversed_offsets_are_rejected(self):
        for start, end in ((-1, 2), (3, 2), (0, 1000)):
            with self.subTest(start=start, end=end), self.assertRaises(ValueError):
                rag_app.source_page(DOCUMENT, start, end)


class Requests(unittest.TestCase):
    def setUp(self):
        self.server = HTTPServer(("127.0.0.1", 0), rag_app.Handler)
        self.server.index = FakeIndex()
        self.worker = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": .01}, daemon=True)
        self.worker.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def request(self, path, host=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        connection.request("GET", path, headers={"Host": host} if host else {})
        response = connection.getresponse()
        status, body = response.status, response.read().decode()
        connection.close()
        return status, body

    def test_home_and_metadata_do_not_trigger_search(self):
        self.assertEqual(self.request("/")[0], 200)
        self.assertEqual(json.loads(self.request("/status")[1])["documents"], 1)
        self.assertEqual(len(json.loads(self.request("/meetings")[1])), 1)
        self.assertEqual(self.server.index.calls, [])

    def test_evaluation_route_is_read_only_and_ignores_user_file_paths(self):
        with patch.object(rag_app.rag_results, "render_body", return_value="<main>Aggregate results</main>") as render:
            status, body = self.request("/evaluation?path=.env&generate=true")
            self.assertEqual(status, 200)
            self.assertIn("Aggregate results", body)
            render.assert_called_once_with()
        self.assertEqual(self.server.index.calls, [])
        self.assertIn('href="/evaluation"', self.request("/")[1])

    def test_invalid_search_cannot_reach_the_index(self):
        for suffix in ("k=0", "k=21", "k=abc", "mode=bad", "meeting_id=missing", "q="):
            key = suffix.split("=")[0]
            args = {"q": "independence", "meeting_id": "123", "mode": "hybrid", "k": "5"}
            args.pop(key)
            path = "/search?" + "&".join(f"{k}={v}" for k, v in args.items()) + "&" + suffix
            with self.subTest(suffix=suffix):
                self.assertEqual(self.request(path)[0], 400)
        self.assertEqual(self.server.index.calls, [])

    def test_valid_search_is_scoped_to_the_selected_meeting(self):
        status, body = self.request("/search?q=independence&meeting_id=123&mode=keyword&k=5")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {"hits": [{"text": "evidence"}]})
        self.assertEqual(self.server.index.calls, [("independence", "123", {"k": 5, "mode": "keyword"})])

    def test_rebinding_and_unknown_documents_are_rejected(self):
        self.assertEqual(self.request("/status", "evil.test")[0], 403)
        self.assertEqual(self.request("/source?id=missing")[0], 404)
        self.assertEqual(self.request("/source?id=doc-1&start=1000&end=1001")[0], 400)


if __name__ == "__main__":
    unittest.main()
