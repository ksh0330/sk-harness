"""HTTP smoke test: start the server, wait until it answers, probe endpoints, always stop it.

spec.json:
  {"serve": ["python", "app/server.py", "--port", "8765"],      (optional; omit to test a running server)
   "base": "http://127.0.0.1:8765", "wait": "/api/health", "timeout": 20,
   "checks": [{"path": "/api/lots", "status": 200, "json_has": ["items.0.lot_id"], "json_len_min": {"items": 1}},
              {"method": "POST", "path": "/api/x", "json": {"a": 1}, "status": 201, "json_equals": {"ok": true}},
              {"path": "/", "contains": ["<title", "app.js"]}]}
"""

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

from . import util

_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # never route localhost via a proxy


def request(method, url, body=None, headers=None, timeout=10):
    """(status, text, seconds). status is None when nothing answered."""
    data = None
    headers = dict(headers or {})
    if body is not None:
        data = json.dumps(body).encode("utf-8") if not isinstance(body, (bytes, str)) else (
            body.encode("utf-8") if isinstance(body, str) else body)
        headers.setdefault("Content-Type", "application/json")
    started = time.time()
    try:
        with _OPENER.open(urllib.request.Request(url, data=data, method=method, headers=headers), timeout=timeout) as reply:
            return reply.status, util.decode(reply.read()), time.time() - started
    except urllib.error.HTTPError as exc:
        return exc.code, util.decode(exc.read()), time.time() - started
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return None, str(getattr(exc, "reason", exc)), time.time() - started


def dig(value, path):
    """Follow 'a.b.0.c' through dicts and lists; raises KeyError when the path does not exist."""
    for part in [p for p in str(path).split(".") if p != ""]:
        if isinstance(value, list):
            try:
                value = value[int(part)]
            except (ValueError, IndexError):
                raise KeyError(path) from None
        elif isinstance(value, dict) and part in value:
            value = value[part]
        else:
            raise KeyError(path)
    return value


def evaluate(check, status, text, seconds):
    """List of human-readable failures for one probe (empty = pass)."""
    problems = []
    if status is None:
        return [f"no response: {text}"]
    expected = check.get("status", 200)
    if status != expected:
        problems.append(f"status {status}, expected {expected}; body starts {text[:120]!r}")
    for needle in _list(check.get("contains")):
        if needle not in text:
            problems.append(f"body does not contain {needle!r}")
    for needle in _list(check.get("not_contains")):
        if needle in text:
            problems.append(f"body contains forbidden {needle!r}")
    if "max_ms" in check and seconds * 1000 > check["max_ms"]:
        problems.append(f"took {seconds * 1000:.0f} ms, limit {check['max_ms']} ms")
    if {"json_has", "json_equals", "json_len_min"} & check.keys():
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return problems + [f"body is not JSON: {text[:120]!r}"]
        for path in _list(check.get("json_has")):
            try:
                dig(payload, path)
            except KeyError:
                problems.append(f"JSON has no {path!r}")
        for path, wanted in (check.get("json_equals") or {}).items():
            try:
                actual = dig(payload, path)
                if actual != wanted:
                    problems.append(f"JSON {path!r} is {actual!r}, expected {wanted!r}")
            except KeyError:
                problems.append(f"JSON has no {path!r}")
        for path, minimum in (check.get("json_len_min") or {}).items():
            try:
                actual = dig(payload, path)
                if not hasattr(actual, "__len__") or len(actual) < minimum:
                    problems.append(f"JSON {path or '(root)'!r} has length {len(actual) if hasattr(actual, '__len__') else 'n/a'}, need >= {minimum}")
            except KeyError:
                problems.append(f"JSON has no {path!r}")
    return problems


def _list(value):
    return [] if value is None else [value] if isinstance(value, str) else list(value)


def run(spec_path):
    """Returns True when every probe passed. Prints one line per probe."""
    spec_path = Path(spec_path)
    with open(spec_path, encoding="utf-8-sig") as handle:
        spec = json.load(handle)
    base = spec.get("base", "").rstrip("/")
    if not base.startswith(("http://", "https://")) or not spec.get("checks"):
        print('SMOKE: FAIL  spec needs "base" (http://host:port) and a non-empty "checks" list')
        return False
    wait_url = base + spec.get("wait", "/")
    proc = log = None
    failures = 0
    try:
        if spec.get("serve"):
            status, _, _ = request("GET", wait_url, timeout=2)
            if status is not None and not spec.get("reuse"):
                print(f"SMOKE: FAIL  {base} already answers BEFORE the server was started: an old process holds "
                      f'the port, so results would not come from the current code. Stop it or change the port '
                      f'(set "reuse": true only if that is intended).')
                return False
            log_path = spec_path.with_suffix(".server.log")
            log = open(log_path, "w", encoding="utf-8", errors="replace")
            proc = util.popen_group(spec["serve"], cwd=spec.get("cwd") or None, stdout=log, stderr=log)
            deadline = time.time() + spec.get("timeout", 20)
            while True:
                status, _, _ = request("GET", wait_url, timeout=2)
                if status is not None:
                    break
                if proc.poll() is not None or time.time() > deadline:
                    log.flush()
                    tail = "\n    ".join(util.decode(log_path.read_bytes()).splitlines()[-15:])
                    reason = f"server exited with code {proc.returncode}" if proc.poll() is not None else "timeout waiting for the server"
                    print(f"SMOKE: FAIL  {reason} ({wait_url}). Server log tail:\n    {tail}")
                    return False
                time.sleep(0.3)
        for check in spec["checks"]:
            method = check.get("method", "GET").upper()
            url = check.get("url") or base + check.get("path", "/")
            status, text, seconds = request(method, url, check.get("json", check.get("body")), check.get("headers"),
                                            check.get("timeout", 10))
            problems = evaluate(check, status, text, seconds)
            failures += bool(problems)
            print(f"[{'FAIL' if problems else 'PASS'}] {method} {url} -> {status} in {seconds * 1000:.0f} ms")
            for problem in problems:
                print(f"    {problem}")
    finally:
        if proc:
            util.kill_tree(proc)
        if log:
            log.close()
    total = len(spec["checks"])
    print(f"SMOKE: {'FAIL' if failures else 'PASS'}  passed={total - failures} failed={failures}"
          + (" (server stopped)" if proc else ""))
    return not failures
