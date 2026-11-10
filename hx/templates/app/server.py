"""Minimal JSON API + static page. Standard library only: runs offline, nothing to install.

Add an endpoint: write `def handler(query, body)` returning a JSON-able value (or `(status, value)`),
raise ApiError(status, message) for bad input, and register it in ROUTES.
"""

import argparse
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

STATIC = Path(__file__).resolve().parent / "static"
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
         ".css": "text/css; charset=utf-8", ".json": "application/json; charset=utf-8",
         ".svg": "image/svg+xml", ".png": "image/png", ".csv": "text/csv; charset=utf-8"}
LOCK = threading.Lock()
ITEMS = [{"id": 1, "name": "sample", "value": 3.5}]  # placeholder data layer: replace with yours


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status, self.message = status, message


def health(query, body):
    return {"ok": True}


def list_items(query, body):
    with LOCK:
        return {"count": len(ITEMS), "items": list(ITEMS)}


def add_item(query, body):
    if not isinstance(body, dict) or not isinstance(body.get("name"), str) or not body["name"].strip():
        raise ApiError(400, "name is required")
    try:
        value = float(body.get("value", 0))
    except (TypeError, ValueError):
        raise ApiError(400, "value must be a number") from None
    with LOCK:
        item = {"id": max((entry["id"] for entry in ITEMS), default=0) + 1, "name": body["name"].strip(), "value": value}
        ITEMS.append(item)
    return 201, item


ROUTES = {("GET", "/api/health"): health,
          ("GET", "/api/items"): list_items,
          ("POST", "/api/items"): add_item}


class Handler(BaseHTTPRequestHandler):
    server_version = "hxapp/1.0"

    def log_message(self, format, *args):  # keep test output readable
        pass

    def _send(self, status, payload, content_type=TYPES[".json"]):
        data = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _static(self, path):
        target = (STATIC / (path.lstrip("/") or "index.html")).resolve()
        if STATIC.resolve() not in target.parents or not target.is_file():
            raise ApiError(404, "not found")
        self._send(200, target.read_bytes(), TYPES.get(target.suffix.lower(), "application/octet-stream"))

    def _handle(self, method):
        url = urlparse(self.path)
        try:
            route = ROUTES.get((method, url.path))
            if route is None:
                if any(path == url.path for _, path in ROUTES):
                    raise ApiError(405, f"{method} is not allowed on {url.path}")
                if method == "GET" and not url.path.startswith("/api/"):
                    return self._static(url.path)
                raise ApiError(404, f"no route {method} {url.path}")
            body = None
            if method != "GET":
                length = int(self.headers.get("Content-Length") or 0)
                if length > 5_000_000:
                    raise ApiError(413, "request body too large")
                raw = self.rfile.read(length)
                try:
                    body = json.loads(raw.decode("utf-8")) if raw else None
                except (ValueError, UnicodeDecodeError):
                    raise ApiError(400, "body must be valid JSON") from None
            result = route(parse_qs(url.query), body)
            status, payload = result if isinstance(result, tuple) else (200, result)
            self._send(status, payload)
        except ApiError as exc:
            self._send(exc.status, {"error": exc.message})
        except Exception as exc:  # a crash must still answer, with the reason
            self._send(500, {"error": f"{type(exc).__name__}: {exc}"})

    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")

    def do_PUT(self):
        self._handle("PUT")

    def do_DELETE(self):
        self._handle("DELETE")


def make_server(host="127.0.0.1", port=8765):
    return ThreadingHTTPServer((host, port), Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = make_server(args.host, args.port)
    print(f"serving http://{args.host}:{server.server_port}/  (Ctrl+C to stop)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
