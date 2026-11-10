"""Requirement ledger + evidence log + gate.

A requirement counts as proven only when a real command was run through `hx run`, exited 0,
actually executed tests, and no source file changed afterwards. The gate recomputes this from
the log every time, so a claim of "done" cannot outlive the code it was true for.
"""

import collections
import functools
import json
import re
import subprocess
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import util

KINDS = ("MUST", "SHOULD", "COULD")
STATUSES = ("todo", "doing", "done", "dropped")
ZERO_TESTS = re.compile(r"Ran 0 tests|collected 0 items|no tests ran|No tests found|\b0 passing\b|Tests:\s+0 total", re.I)
SKIPPED = re.compile(r"skipped=(\d+)|(\d+) skipped")
SUMMARY = re.compile(r"^(Ran \d+ tests? in .*|OK( \(.*\))?|FAILED \(.*\)|=+ .*(passed|failed|error).* =+|"
                     r"Tests:\s+\d+.*|\d+ passing.*|\d+ failing.*|(CHECK|GATE|SMOKE): .*)$")
TRIVIAL = {"echo", "true", "exit", "rem", ":", "dir", "ls", "pwd", "cd", "type", "cat"}
ORDER = ("FAIL", "STALE", "WEAK", "NONE")


def _locked(function):
    """Read-modify-write of the ledger under the cross-process lock."""
    @functools.wraps(function)
    def wrapper(root, *args, **kwargs):
        with util.lock(root):
            return function(root, *args, **kwargs)
    return wrapper


# ---------------------------------------------------------------- requirements

def load_reqs(root):
    return util.read_json(Path(root) / util.STATE / "reqs.json", {"items": []})


def save_reqs(root, data):
    util.write_json(util.state_dir(root) / "reqs.json", data)


def _next_id(items, prefix):
    numbers = [int(item["id"][1:]) for item in items if item["id"].startswith(prefix) and item["id"][1:].isdigit()]
    return f"{prefix}{max(numbers, default=0) + 1}"


@_locked
def add_req(root, kind, text, accept=""):
    kind = kind.upper()
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}")
    if not text.strip():
        raise ValueError("requirement text is empty")
    data = load_reqs(root)
    item = {"id": _next_id(data["items"], "R"), "kind": kind, "text": text.strip(), "accept": accept.strip(),
            "status": "todo", "note": "", "created": util.stamp()}
    data["items"].append(item)
    save_reqs(root, data)
    return item


@_locked
def add_question(root, text, assume="", to="user", why=""):
    """A question for the user, or (to="dm") one the user must put to the task's stakeholder."""
    if to not in ("user", "dm"):
        raise ValueError("--to must be user or dm")
    if not text.strip():
        raise ValueError("question text is empty")
    data = load_reqs(root)
    item = {"id": _next_id(data["items"], "Q"), "kind": "QUESTION", "text": text.strip(), "assume": assume.strip(),
            "to": to, "why": why.strip(), "answer": "", "source": "", "status": "open", "created": util.stamp()}
    data["items"].append(item)
    save_reqs(root, data)
    return item


def _marker(root, name):
    """Timestamp written by the agent hooks (e.g. when the user last spoke); None when hooks are not installed."""
    try:
        return float((Path(root) / util.STATE / "run" / name).read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


@_locked
def add_decision(root, title, options, recommend="", why="", impact=""):
    """A choice that belongs to the user: recorded as pending until the user answers."""
    if not title.strip() or len(options) < 2:
        raise ValueError("a decision needs a title and at least two --option values")
    data = load_reqs(root)
    item = {"id": _next_id(data["items"], "D"), "kind": "DECISION", "text": title.strip(), "options": [o.strip() for o in options],
            "recommend": recommend.strip(), "why": why.strip(), "impact": impact.strip(), "owner": "user",
            "status": "pending", "choice": "", "note": "", "created": util.stamp(), "created_ts": time.time()}
    data["items"].append(item)
    save_reqs(root, data)
    return item


@_locked
def log_decision(root, title, choice, why=""):
    """A small, reversible choice the agent made on its own, kept for the record."""
    if not title.strip() or not choice.strip():
        raise ValueError("give the decision title and --choice")
    data = load_reqs(root)
    item = {"id": _next_id(data["items"], "D"), "kind": "DECISION", "text": title.strip(), "options": [], "recommend": "",
            "why": why.strip(), "impact": "", "owner": "ai", "status": "decided", "choice": choice.strip(), "note": "",
            "created": util.stamp(), "created_ts": time.time()}
    data["items"].append(item)
    save_reqs(root, data)
    return item


@_locked
def decide(root, item_id, choice, note=""):
    """Record the user's answer. With hooks installed it is refused until the user has actually spoken."""
    data = load_reqs(root)
    item = find_item(data, item_id)
    if item["kind"] != "DECISION" or item["owner"] != "user":
        raise ValueError(f"{item_id} is not a user decision")
    choice = choice.strip()
    matches = [option for option in item["options"]
               if choice.casefold() in (option.casefold(), option.partition(":")[0].strip().casefold())]
    if not choice or len(matches) != 1:
        raise ValueError("--choice must name exactly one recorded option (full text or its label before ':')")
    spoke = _marker(root, "last_user_prompt")
    if spoke is not None and spoke < item["created_ts"]:
        raise ValueError(f"{item['id']} was raised after the user's last message, so the user cannot have answered it yet. "
                         f"Show `hx brief` to the user, stop, and record the choice after they reply.")
    # A timestamp proves only that a prompt arrived, never what the user approved.
    item.update(status="decided", choice=choice, note=note.strip(), decided=util.stamp(),
                confirmed=False, prompt_observed=spoke is not None)
    save_reqs(root, data)
    return item


@_locked
def add_feedback(root, text):
    if not text.strip():
        raise ValueError("feedback text is empty")
    data = load_reqs(root)
    item = {"id": _next_id(data["items"], "F"), "kind": "FEEDBACK", "text": text.strip(), "status": "open", "note": "",
            "created": util.stamp()}
    data["items"].append(item)
    save_reqs(root, data)
    return item


@_locked
def close_feedback(root, item_id, note):
    data = load_reqs(root)
    item = find_item(data, item_id)
    if item["kind"] != "FEEDBACK":
        raise ValueError(f"{item_id} is not feedback")
    if not note.strip():
        raise ValueError("--note must say what changed (requirement/decision ids, or why nothing changed)")
    item.update(status="done", note=note.strip(), updated=util.stamp())
    save_reqs(root, data)
    return item


def add_from_file(root, path):
    """One item per line: 'MUST: text => acceptance', 'SHOULD: ...', 'COULD: ...', 'Q: question => assumption'."""
    parsed = []
    with open(path, encoding="utf-8-sig") as handle:
        lines = handle.read().splitlines()
    for number, line in enumerate(lines, 1):  # validate the whole file before adding anything
        line = line.strip().lstrip("-* ").strip()
        if not line or line.startswith("#"):
            continue
        head, _, body = line.partition(":")
        text, _, extra = body.partition("=>")
        kind = head.strip().upper()
        if kind not in KINDS + ("Q", "QUESTION") or not text.strip():
            raise ValueError(f"{path}:{number}: line must look like 'MUST: text => acceptance' "
                             f"(MUST/SHOULD/COULD/Q), got {line[:40]!r}; nothing was added")
        parsed.append((kind, text, extra))
    return [add_req(root, kind, text, extra) if kind in KINDS else add_question(root, text, extra)
            for kind, text, extra in parsed]


def find_item(data, item_id):
    for item in data["items"]:
        if item["id"].lower() == item_id.lower():
            return item
    raise ValueError(f"no such id {item_id!r}; known: {[item['id'] for item in data['items']]}")


@_locked
def set_req(root, item_id, status=None, note=None, text=None, accept=None, kind=None, decision=None):
    data = load_reqs(root)
    item = find_item(data, item_id)
    if item["kind"] not in KINDS:
        raise ValueError("use `hx answer` for questions, `hx decide` for decisions, `hx feedback` for feedback")
    cut = item["kind"] == "MUST" and (status == "dropped" or (kind and kind.upper() != "MUST"))
    if cut:  # giving up a MUST changes what is delivered: that is the user's call, not the agent's
        approved = next((d for d in data["items"] if decision and d["id"].lower() == decision.lower()), None)
        if not approved or approved["kind"] != "DECISION" or approved["owner"] != "user" or approved["status"] != "decided":
            raise ValueError(f"{item['id']} is a MUST: dropping or downgrading it needs the user's decision. "
                             f"`hx decide add ...`, show `hx brief`, then repeat with --decision D<n> once decided.")
        item["decision"] = approved["id"]
    if status:
        if status not in STATUSES:
            raise ValueError(f"status must be one of {STATUSES}")
        item["status"] = status
    if kind:
        if kind.upper() not in KINDS:
            raise ValueError(f"kind must be one of {KINDS}")
        item["kind"] = kind.upper()
    for key, value in (("note", note), ("text", text), ("accept", accept)):
        if value is not None:
            item[key] = value.strip()
    item["updated"] = util.stamp()
    save_reqs(root, data)
    return item


@_locked
def answer(root, item_id, text, source=None):
    """Record an answer verbatim. source says who actually gave it: the user or the stakeholder (dm)."""
    data = load_reqs(root)
    item = find_item(data, item_id)
    if item["kind"] != "QUESTION":
        raise ValueError(f"{item_id} is not a question")
    if not text.strip():
        raise ValueError("answer text is empty")
    item["answer"], item["status"], item["updated"] = text.strip(), "answered", util.stamp()
    item["source"] = source or item.get("to", "user")
    save_reqs(root, data)
    return item


# ---------------------------------------------------------------- evidence

def load_checks(root):
    return util.read_json(Path(root) / util.STATE / "checks.json", {})


def load_evidence(root):
    path = Path(root) / util.STATE / "evidence.jsonl"
    if not path.is_file():
        return []
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _first_word(cmd):
    words = cmd.split() if isinstance(cmd, str) else list(cmd)
    return Path(words[0]).stem.lower() if words else ""


def run_check(root, name, cmd, reqs=None, timeout=600, expect=None, metrics=None, tail=30, cwd=None, save=True, watch=None, record=True):
    """Run a command, keep its full log, and append an evidence record. Returns the record."""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,40}", name):
        raise ValueError("check name: letters, digits, _ . - (max 41 chars)")
    root = Path(root)
    checks = load_checks(root)
    previous = checks.get(name, {})
    reqs = sorted(set(reqs)) if reqs is not None else previous.get("reqs", [])
    known = {item["id"] for item in load_reqs(root)["items"]}
    unknown = [req for req in reqs if req not in known]
    if unknown:
        raise ValueError(f"unknown requirement id(s) {unknown}; known: {sorted(known)}")
    cwd = Path(cwd or Path.cwd()).resolve()
    watch = list(watch) if watch is not None else previous.get("watch", [])
    before_fingerprint = util.source_fingerprint(root, watch)
    with util.lock(root):
        counter = util.state_dir(root, "run") / "evidence-seq.json"
        existing_max = max((entry["id"] for entry in load_evidence(root)), default=0)
        evidence_id = max(util.read_json(counter, 0), existing_max) + 1
        if record:
            util.write_json(counter, evidence_id)
    log_path = (util.state_dir(root, "logs") / f"{evidence_id:03d}-{name}.log" if record
                else util.state_dir(root, "run") / f"norecord-{name}-{uuid.uuid4().hex}.log")
    shown = cmd if isinstance(cmd, str) else subprocess.list2cmdline(cmd)
    lines, kept = collections.deque(maxlen=max(tail, 60)), []
    started, exit_code, flags = time.time(), None, []
    with open(log_path, "w", encoding="utf-8", newline="\n") as log:
        log.write(f"$ {shown}\n# cwd={cwd}\n# started={util.stamp()}\n")
        try:
            proc = util.popen_group(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        except OSError as exc:
            message = f"cannot start command: {exc}"
            log.write(message + "\n")
            lines.append(message)
            kept.append(message)
            exit_code = 127
        else:
            def pump():
                size = 0
                for raw in proc.stdout:
                    text = util.decode(raw).rstrip("\r\n")
                    log.write(text + "\n")
                    lines.append(text)
                    if size < 2_000_000:
                        kept.append(text)
                        size += len(text)

            reader = threading.Thread(target=pump, daemon=True)
            reader.start()
            try:
                exit_code = proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                util.kill_tree(proc)
                exit_code = 124
                flags.append("timeout")
            except KeyboardInterrupt:
                util.kill_tree(proc)
                raise
            reader.join(timeout=10)
            proc.stdout.close()
        duration = time.time() - started
        log.write(f"# exit={exit_code} duration={duration:.1f}s\n")
    output = "\n".join(kept)
    if ZERO_TESTS.search(output):
        flags.append("zero_tests")
    if expect and not re.search(expect, output, re.M):
        flags.append("expect_missing")
    if _first_word(cmd) in TRIVIAL:
        flags.append("weak")
    values = {}
    for metric, pattern in (metrics or {}).items():
        found = re.findall(pattern, output, re.M)
        if found:
            last = found[-1] if isinstance(found[-1], str) else found[-1][0]
            try:
                values[metric] = float(last)
            except ValueError:
                flags.append(f"metric_unparsed:{metric}")
        else:
            flags.append(f"metric_missing:{metric}")
    skipped = sum(int(a or b) for a, b in SKIPPED.findall(output))
    unittest_totals = re.findall(r"Ran (\d+) tests? in", output)
    if skipped and ((unittest_totals and skipped >= int(unittest_totals[-1])) or
                    (not unittest_totals and re.search(r"=+\s+\d+ skipped(?:, \d+ deselected)? in .*=+", output))):
        flags.append("all_skipped")
    summary = [line.strip() for line in kept if SUMMARY.match(line.strip())][-2:]
    after_fingerprint = util.source_fingerprint(root, watch)
    if before_fingerprint != after_fingerprint:
        flags.append("source_changed_during_run")
    ok = exit_code == 0 and not {"zero_tests", "all_skipped", "expect_missing", "timeout", "source_changed_during_run"} & set(flags)
    entry = {"id": evidence_id, "name": name, "time": util.stamp(), "end": time.time(), "cmd": cmd,
             "cwd": util.rel(cwd, root), "exit": exit_code, "ok": ok, "dur": round(duration, 2), "reqs": reqs,
             "log": util.rel(log_path, root), "flags": flags, "metrics": values, "skipped": skipped,
             "summary": " / ".join(summary), "fingerprint": after_fingerprint, "watch": watch}
    record_data = record
    if record_data:
        with util.lock(root):
            evidence_path = util.state_dir(root) / "evidence.jsonl"
            previous_text = evidence_path.read_text(encoding="utf-8") if evidence_path.exists() else ""
            util.write_text(evidence_path, previous_text + json.dumps(entry, ensure_ascii=False) + "\n")
            if save:
                checks = load_checks(root)
                checks[name] = {"cmd": cmd, "cwd": entry["cwd"], "reqs": reqs, "timeout": timeout,
                                "expect": expect, "metrics": metrics or {}, "watch": watch}
                util.write_json(util.state_dir(root) / "checks.json", checks)
    record = entry
    if tail:
        for line in list(lines)[-(tail if ok else max(tail, 60)):]:
            print(line)
    print(f"HX-RUN #{evidence_id} {name}: {'PASS' if ok else 'FAIL'} exit={exit_code} dur={duration:.1f}s"
          + (f" flags={','.join(flags)}" if flags else "") + (f" skipped={skipped}" if skipped else "")
          + (f" metrics={values}" if values else "") + f" reqs={','.join(reqs) or '-'} log={record['log']}")
    if "zero_tests" in flags:
        print("  -> the command ran ZERO tests; exit code 0 proves nothing (wrong path or discovery pattern?)")
    if "weak" in flags:
        print("  -> trivial command: it does not exercise the product and will not count as proof")
    return record


@_locked
def forget(root, name):
    checks = load_checks(root)
    if name not in checks:
        raise ValueError(f"no such check {name!r}; known: {sorted(checks)}")
    del checks[name]
    util.write_json(util.state_dir(root) / "checks.json", checks)


def regress(root, only=None, tail=0, stale=False, record=True):
    """Re-run saved checks from their original directory (all, --only some, or just those not currently PASS)."""
    root = Path(root)
    checks = load_checks(root)
    names = [name for name in checks if not only or name in only]
    if stale:
        states = compute(root)["states"]
        names = [name for name in names if states[name] != "PASS"]
        if not names:
            print("REGRESS: PASS  nothing is stale or failing")
            return []
    missing = sorted(set(only or []) - set(checks))
    if missing:
        raise ValueError(f"no such check(s) {missing}; known: {sorted(checks)}")
    if not names:
        print("REGRESS: nothing to run (no checks saved yet; create them with `hx run --name ...`)")
        return []
    failed = []
    for name in names:
        check = checks[name]
        result = run_check(root, name, check["cmd"], check.get("reqs"), check.get("timeout", 600), check.get("expect"),
                           check.get("metrics"), tail=tail, cwd=root / check.get("cwd", "."), save=False,
                           watch=check.get("watch"), record=record)
        if not result["ok"]:
            failed.append(name)
    print(f"REGRESS{'' if record else ' (not recorded)'}: {'FAIL' if failed else 'PASS'}  ran={len(names)} failed={len(failed)}"
          + (f" -> {', '.join(failed)} (see logs)" if failed else ""))
    return failed


# ---------------------------------------------------------------- state, status, gate

def check_state(record, source_time, fingerprint=None):
    if record is None:
        return "NONE"
    if not record["ok"]:
        return "FAIL"
    if "weak" in record["flags"]:
        return "WEAK"
    if "fingerprint" in record and record["fingerprint"] != fingerprint:
        return "STALE"
    if record["end"] < source_time - 1.0:
        return "STALE"
    return "PASS"


def compute(root):
    data, checks = load_reqs(root), load_checks(root)
    evidence = load_evidence(root)
    latest = {record["name"]: record for record in evidence}
    source_time, source_path = util.source_mtime(root)
    scoped = {}
    for check in checks.values():  # a check with --watch only goes stale when files matching its globs change
        watch = tuple(check.get("watch") or ())
        if watch and watch not in scoped:
            scoped[watch] = util.source_mtime(root, watch)[0]
    fingerprints = {}
    for check in checks.values():
        watch = tuple(check.get("watch") or ())
        if watch not in fingerprints:
            fingerprints[watch] = util.source_fingerprint(root, watch)
    states = {name: check_state(latest.get(name), scoped.get(tuple(check.get("watch") or ()), source_time),
                               fingerprints[tuple(check.get("watch") or ())])
              for name, check in checks.items()}
    proof = {}
    for item in data["items"]:
        if item["kind"] not in KINDS:
            continue
        linked = [name for name, check in checks.items() if item["id"] in check.get("reqs", [])]
        bad = [states[name] for name in linked if states[name] != "PASS"]
        state = "NONE" if not linked else next((s for s in ORDER if s in bad), "PASS")
        proof[item["id"]] = (state, linked)
    return {"items": data["items"], "checks": checks, "latest": latest, "states": states, "proof": proof,
            "evidence": evidence, "source_path": source_path}


def time_left(root):
    """(minutes or None, advice). The advice encodes the time-box rules for the final."""
    deadline = (util.read_json(Path(root) / util.STATE / "config.json", {}) or {}).get("deadline")
    if not deadline:
        return None, "no deadline set (hx init --deadline 16:00)"
    try:
        hour, minute = map(int, deadline.split(":"))
    except ValueError:
        return None, f"bad deadline {deadline!r}"
    # The deadline is Korean wall-clock time; a cloud workspace often runs in UTC, so never trust the local zone.
    current = datetime.now(timezone(timedelta(hours=9)))
    minutes = int((current.replace(hour=hour, minute=minute, second=0, microsecond=0) - current).total_seconds() // 60)
    if minutes < 0:
        advice = "DEADLINE PASSED. Change nothing; submit the last hx-ok snapshot."
    elif minutes < 15:
        advice = "Prioritize final verification and packaging. Inspect `hx back` before any user-authorized recovery."
    elif minutes < 45:
        advice = "Final pass only: `hx gate --final`, README/run instructions, deliverable packaging. No new features."
    elif minutes < 90:
        advice = "FEATURE FREEZE: fix failures, re-run regress, snapshot. Do not start anything new."
    elif minutes < 180:
        advice = "Finish and prove every MUST before touching SHOULD/COULD. Snapshot each green state."
    else:
        advice = "Get a thin end-to-end path working first (input -> core logic -> output), then deepen."
    return minutes, f"{minutes // 60}h{minutes % 60:02d}m left until {deadline} KST. {advice}" if minutes >= 0 else advice


def render_status(root):
    state = compute(root)
    reqs = [item for item in state["items"] if item["kind"] in KINDS]
    questions = [item for item in state["items"] if item["kind"] == "QUESTION"]
    decisions = [item for item in state["items"] if item["kind"] == "DECISION"]
    feedback = [item for item in state["items"] if item["kind"] == "FEEDBACK"]
    must = [item for item in reqs if item["kind"] == "MUST" and item["status"] != "dropped"]
    proven = sum(1 for item in must if item["status"] == "done" and state["proof"][item["id"]][0] == "PASS")
    lines = [f"# hx status  {util.stamp()}", f"time: {time_left(root)[1]}", "",
             f"## Requirements (MUST proven {proven}/{len(must)})",
             "| id | kind | status | proof | checks | requirement | acceptance |", "|---|---|---|---|---|---|---|"]
    for item in reqs:
        proof, linked = state["proof"][item["id"]]
        lines.append(f"| {item['id']} | {item['kind']} | {item['status']} | {proof} | {', '.join(linked) or '-'} | "
                     f"{util.short(item['text'], 70)} | {util.short(item['accept'], 50) or '-'} |")
    if not reqs:
        lines.append("| - | - | - | - | - | (none recorded: `hx req add`) | - |")
    lines += ["", "## Checks", "| check | state | exit | when | sec | result | command |", "|---|---|---|---|---|---|---|"]
    for name, check in state["checks"].items():
        record = state["latest"].get(name)
        shown = check["cmd"] if isinstance(check["cmd"], str) else subprocess.list2cmdline(check["cmd"])
        if record:
            result = " ".join(filter(None, [record["summary"], ",".join(record["flags"]),
                                            f"skipped={record['skipped']}" if record["skipped"] else ""]))
            lines.append(f"| {name} | {state['states'][name]} | {record['exit']} | {record['time'][11:19]} | {record['dur']} | "
                         f"{util.short(result, 60) or '-'} | `{util.short(shown, 60)}` |")
        else:
            lines.append(f"| {name} | NONE | - | - | - | never run | `{util.short(shown, 60)}` |")
    if not state["checks"]:
        lines.append("| - | - | - | - | - | (none: `hx run --name NAME --req R1 -- <command>`) | - |")
    history = {}
    for record in state["evidence"]:
        for metric, value in record.get("metrics", {}).items():
            history.setdefault(f"{record['name']}.{metric}", []).append(value)
    if history:
        lines += ["", "## Metrics (first -> latest, over all runs)"]
        lines += [f"- {metric}: first={values[0]:g} latest={values[-1]:g} min={min(values):g} max={max(values):g} runs={len(values)}"
                  for metric, values in history.items()]
    if questions:
        lines += ["", "## Questions and assumptions"]
        for item in questions:
            detail = f"answer: {item['answer']}" if item["status"] == "answered" else f"OPEN; assuming: {item['assume'] or '(nothing recorded)'}"
            lines.append(f"- {item['id']}{' [DM]' if item.get('to') == 'dm' else ''} {item['text']} -> {detail}")
    reviews = [item for item in state["items"] if item["kind"] == "REVIEW"]
    if reviews:
        lines += ["", "## Review items (mediator)"]
        lines += [f"- {item['id']} [{item['severity']}] {item['status'].upper()}: {util.short(item['text'], 90)}"
                  + (f" | ask: {util.short(item['ask'], 60)}" if item["ask"] else "") for item in reviews]
    if decisions:
        lines += ["", "## Decisions"]
        for item in decisions:
            if item["status"] == "pending":
                lines.append(f"- {item['id']} PENDING (user): {item['text']} | options: {' / '.join(item['options'])} | "
                             f"recommended: {item['recommend'] or '-'}")
            else:
                who = "AI" if item["owner"] == "ai" else "user" if item.get("confirmed") else "user (recorded by the agent)"
                lines.append(f"- {item['id']} decided by {who}: {item['text']} -> {item['choice']}"
                             + (f" ({item['note'] or item['why']})" if item["note"] or item["why"] else ""))
    if feedback:
        lines += ["", "## Feedback"]
        lines += [f"- {item['id']} {item['status'].upper()}: {util.short(item['text'], 90)}" + (f" -> {item['note']}" if item["note"] else "")
                  for item in feedback]
    if any(value == "STALE" for value in state["states"].values()) and state["source_path"]:
        lines += ["", f"STALE = source changed after the proof ran (newest: {util.rel(state['source_path'], root)}). Run `hx regress`."]
    return "\n".join(lines) + "\n", state


def gate_eval(root):
    """(blocks, warns, status text) without printing or running anything."""
    text, state = render_status(root)
    blocks, warns = [], []
    reqs = [item for item in state["items"] if item["kind"] in KINDS]
    if not any(item["kind"] == "MUST" for item in reqs):
        blocks.append("no MUST requirement is recorded: nothing can be claimed complete")
    for item in reqs:
        proof, linked = state["proof"][item["id"]]
        label = f"{item['id']} [{item['kind']}] {util.short(item['text'], 50)}"
        if item["status"] == "dropped":
            if item["kind"] == "MUST":
                warns.append(f"{label}: MUST was dropped under {item.get('decision', 'no decision')} "
                             f"({item['note'] or 'no reason recorded'}); disclose it")
            continue
        problem = None
        if item["status"] != "done":
            problem = f"status={item['status']}" + (f" although its proof passes: if it is complete, "
                                                    f"`hx req set {item['id']} --status done`" if proof == "PASS" else "")
        elif proof != "PASS":
            problem = {"NONE": "marked done but no check is linked (hx run --req)",
                       "FAIL": f"latest proof FAILED ({', '.join(linked)})",
                       "STALE": f"source changed after the proof ({', '.join(linked)}); re-run",
                       "WEAK": "only a trivial command was offered as proof"}[proof]
        if problem:
            (blocks if item["kind"] == "MUST" else warns).append(f"{label}: {problem}")
    for name, value in state["states"].items():
        if value == "FAIL":
            blocks.append(f"check {name} is failing (regression?) log={state['latest'][name]['log']}")
        elif value == "STALE" and not state["checks"][name].get("reqs"):
            warns.append(f"check {name} is stale; re-run `hx regress`")
        record = state["latest"].get(name)
        if record and record.get("skipped"):
            warns.append(f"check {name} skipped {record['skipped']} test(s): say so, do not call them passed")
    for item in state["items"]:
        if item["kind"] == "DECISION" and item["status"] == "pending":
            blocks.append(f"{item['id']} awaits the user's decision: {util.short(item['text'], 60)} (show `hx brief`)")
        if item["kind"] == "FEEDBACK" and item["status"] == "open":
            blocks.append(f"{item['id']} user feedback not yet handled: {util.short(item['text'], 60)} "
                          f"(apply it, then `hx feedback done {item['id']} --note ...`)")
        if item["kind"] == "REVIEW" and item["status"] == "open":
            (blocks if item["severity"] == "high" else warns).append(
                f"{item['id']} review item open [{item['severity']}]: {util.short(item['text'], 60)}")
        if item["kind"] == "REVIEW" and item["status"] == "handled" and item["severity"] == "high":
            blocks.append(f"{item['id']} high review is handled but awaits independent verification and close")
        if item["kind"] == "QUESTION" and item["status"] == "open":
            warns.append(f"{item['id']} unanswered: {util.short(item['text'], 50)} -> "
                         + (f"assuming {util.short(item['assume'], 50)!r}; state the assumption in the deliverable"
                            if item["assume"] else "NO assumption recorded"))
    return blocks, warns, text


def gate(root, final=False):
    """Mechanical completion check. Returns True when nothing blocks."""
    if final:
        regress(root)
    blocks, warns, text = gate_eval(root)
    report = text + "\n## Gate\n" + "".join(f"- BLOCK {line}\n" for line in blocks) + "".join(f"- WARN {line}\n" for line in warns)
    report += f"\nGATE: {'FAIL' if blocks else 'PASS'}  blocking={len(blocks)} warnings={len(warns)}\n"
    util.write_text(util.state_dir(root) / "STATUS.md", report)
    for line in blocks:
        print(f"BLOCK {line}")
    for line in warns:
        print(f"WARN  {line}")
    print(f"GATE: {'FAIL' if blocks else 'PASS'}  blocking={len(blocks)} warnings={len(warns)}  (full table: {util.STATE}/STATUS.md)")
    return not blocks


def brief(root):
    """What the user must look at before the agent goes on: understanding, open questions, pending decisions."""
    items = load_reqs(root)["items"]
    reqs = [item for item in items if item["kind"] in KINDS and item["status"] != "dropped"]
    lines = ["# 결정 요청", "", f"## 내가 이해한 과제 (요구사항 {len(reqs)}개)"]
    lines += [f"- {item['id']} [{item['kind']}] {item['text']}" + (f"  (확인 방법: {item['accept']})" if item["accept"] else "")
              for item in reqs] or ["- (아직 등록된 요구사항 없음)"]
    questions = [item for item in items if item["kind"] == "QUESTION" and item["status"] == "open"]
    if questions:
        lines += ["", "## 확인이 필요한 질문 (가정은 승인이 아니며, 중요한 답이 없으면 대기)"]
        lines += [f"- {item['id']} {item['text']}  → 가정: {item['assume'] or '(없음)'}" for item in questions]
    pending = [item for item in items if item["kind"] == "DECISION" and item["status"] == "pending"]
    if pending:
        lines += ["", "## 사용자가 정해야 할 사항"]
        for item in pending:
            lines.append(f"### {item['id']} {item['text']}")
            lines += [f"- {option}" for option in item["options"]]
            lines.append(f"- 권장: {item['recommend'] or '(없음)'}" + (f" — {item['why']}" if item["why"] else ""))
            if item["impact"]:
                lines.append(f"- 영향: {item['impact']}")
        example = ", ".join(f"{item['id']}=권장안" for item in pending[:2])
        if any(item["assume"] for item in questions):
            example += ", 명시된 가정은 각각 확인"
        if any(not item["assume"] for item in questions):
            example += ", 미답변 질문은 답변 대기"
        lines += ["", f"답하는 방법 예: {example}"]
    else:
        lines += ["", "정해야 할 사항 없음: 위 이해와 가정이 맞으면 그대로 진행합니다."]
    text = "\n".join(lines) + "\n"
    util.write_text(util.state_dir(root) / "BRIEF.md", text)
    return text, len(pending), len(questions)
