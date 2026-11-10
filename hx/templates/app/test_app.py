"""Starts the real server on a free port and talks to it over HTTP (no mocks)."""

import json
import sys
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from __APP__ import server  # noqa: E402


def call(base, method, path, body=None, raw=None):
    data = raw if raw is not None else (json.dumps(body).encode("utf-8") if body is not None else None)
    request = urllib.request.Request(base + path, data=data, method=method, headers={"Content-Type": "application/json"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=10) as reply:
            return reply.status, reply.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8")


class AppTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = server.make_server("127.0.0.1", 0)
        cls.base = f"http://127.0.0.1:{cls.httpd.server_port}"
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join(timeout=5)

    def test_health(self):
        self.assertEqual(call(self.base, "GET", "/api/health"), (200, '{"ok": true}'))

    def test_add_then_list_round_trip(self):
        status, text = call(self.base, "POST", "/api/items", {"name": "웨이퍼 A", "value": "12.5"})
        self.assertEqual(status, 201)
        created = json.loads(text)
        status, text = call(self.base, "GET", "/api/items")
        self.assertEqual(status, 200)
        self.assertIn(created, json.loads(text)["items"])

    def test_bad_input_is_rejected_with_a_reason(self):
        for body in ({}, {"name": "  "}, {"name": "x", "value": "abc"}, [1, 2]):
            status, text = call(self.base, "POST", "/api/items", body)
            self.assertEqual(status, 400, body)
            self.assertTrue(json.loads(text)["error"])
        self.assertEqual(call(self.base, "POST", "/api/items", raw=b"{not json")[0], 400)

    def test_unknown_route_and_wrong_method(self):
        self.assertEqual(call(self.base, "GET", "/api/nope")[0], 404)
        self.assertEqual(call(self.base, "DELETE", "/api/items")[0], 405)

    def test_page_is_served_and_path_escape_is_blocked(self):
        status, text = call(self.base, "GET", "/")
        self.assertEqual(status, 200)
        self.assertIn("<title>", text)
        self.assertEqual(call(self.base, "GET", "/../server.py")[0], 404)


if __name__ == "__main__":
    unittest.main()
