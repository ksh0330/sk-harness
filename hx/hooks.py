"""Codex lifecycle hooks (optional). One entry point: `hx hook <event>` reads the hook JSON on stdin.

The hooks only surface state and stop a few specific mistakes; none of them keeps the agent working while
it is correctly waiting for the user. Every handler fails open: a broken hook must never block the session.
"""

import hashlib
import json
import re
import sys
import time
from pathlib import Path

from . import collab, ledger, util

RISKY = [(r"\bgit\s+push\b", "git push (publishes outside the workspace)"),
         (r"\bgit\s+reset\s+--hard\b", "git reset --hard (discards work; use `hx back`, which keeps it on a branch)"),
         (r"\bgit\s+clean\s+-[a-zA-Z]*f", "git clean -f (deletes untracked files)"),
         (r"\bgit\s+(checkout|restore)\s+(--\s+)?\.(\s|$)", "discarding all working-tree changes"),
         (r"\bgit\s+branch\s+-D\b", "git branch -D (deletes a branch)"),
         (r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*f?\s+(/|~|\.\.|\.git)(\s|/|$)", "recursive delete outside the project or of .git"),
         (r"\b(npm|pnpm|yarn)\s+publish\b|\bdocker\s+push\b|\b(vercel|netlify|firebase)\s+deploy\b", "external deployment/publish"),
         (r"\bcodex\s+update\b|\bnpm\s+(i|install)\s+-g\b|\bapt(-get)?\s+install\b|\bpip3?\s+install\s+--upgrade\s+pip\b",
          "updating or installing system tools (forbidden by the contest rules unless the organisers allow it)")]
DONE_CLAIM = re.compile(r"완료했|완료됐|완료되었|완료입니다|모두 완료|작업 완료|제출 준비|마쳤습니다|끝났습니다|"
                        r"\b(all done|is complete|are complete|completed|finished|ready (to|for) submi)", re.I)
DOC_PREFIXES = ("collab/", "docs/", "notes/", "scratch/", "tmp/", ".hx/", ".agents/", ".codex/")
DOC_SUFFIXES = (".md", ".txt", ".rst")


def _find_root(payload):
    start = Path(payload.get("cwd") or ".").resolve()
    for folder in (start, *start.parents):
        if (folder / util.STATE / "config.json").is_file():
            return folder
    return None


def _mark(root, name):
    util.write_text(util.state_dir(root, "run") / name, repr(time.time()))


def _context(event, text):
    return json.dumps({"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}}, ensure_ascii=False)


def _summary(root):
    state, must, proven = collab._must_state(root)
    todo = collab.user_todo(root)
    lines = [f"[hx] 단계 {collab.phase(root)} · {ledger.time_left(root)[1]}",
             f"[hx] MUST 증명 {len(proven)}/{len(must)} · 검사 " + (", ".join(f"{n}={s}" for n, s in state["states"].items()) or "없음")]
    if todo:
        lines.append("[hx] 사용자 답을 기다리는 항목: " + "; ".join(f"{item_id}({kind})" for kind, item_id, _ in todo)
                     + " — 답 없이 대신 정하지 말 것. 답이 오면 hx decide set / hx answer 로 기록")
    opened = [item["id"] for item in state["items"] if item["kind"] in ("REVIEW", "FEEDBACK") and item["status"] == "open"]
    if opened:
        lines.append("[hx] 처리할 검토·피드백: " + ", ".join(opened) + " (collab/BOARD.md)")
    if collab.inbox_unread(root)[0]:
        lines.append("[hx] collab/INBOX.md에 읽지 않은 내용이 있다: `hx inbox`")
    return lines


def session_start(root, payload):
    lines = _summary(root) + ["[hx] 절차는 hx-main 스킬(.agents/skills/hx-main/SKILL.md), 현재 상태는 collab/BOARD.md"]
    return 0, _context("SessionStart", "\n".join(lines)), ""


def user_prompt(root, payload):
    _mark(root, "last_user_prompt")
    lines = _summary(root)
    return 0, _context("UserPromptSubmit", "\n".join(lines)), ""


def _command_text(payload):
    data = payload.get("tool_input") or {}
    value = data.get("command") or data.get("cmd") or data.get("input") or data.get("patch") or ""
    return " ".join(map(str, value)) if isinstance(value, list) else str(value)


def _patched_files(payload):
    data = payload.get("tool_input") or {}
    files = [str(data[key]) for key in ("file_path", "path") if data.get(key)]
    files += re.findall(r"^\*\*\* (?:Add|Update|Delete) File: (.+)$", _command_text(payload), re.M)
    return [name.strip() for name in files]


def _deny(reason):
    return 0, json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                                  "permissionDecisionReason": reason}}, ensure_ascii=False), ""


def pre_tool(root, payload):
    tool = str(payload.get("tool_name") or "")
    text = _command_text(payload)
    if tool.lower() in ("apply_patch", "edit", "write"):
        if collab.phase(root) in ("analyze", "design"):
            product = []
            for name in _patched_files(payload):
                relative = name.replace("\\", "/")
                try:
                    relative = Path(name).resolve().relative_to(Path(root).resolve()).as_posix()
                except (ValueError, OSError):
                    pass
                if not relative.startswith(DOC_PREFIXES) and not relative.lower().endswith(DOC_SUFFIXES):
                    product.append(relative)
            if product:
                return _deny(f"단계가 아직 {collab.phase(root)}이다: 사용자가 분석과 접근 방식을 확인하기 전에는 제품 코드({', '.join(product[:3])})를 "
                             f"만들지 않는다. `hx brief`를 보여 주고 답을 받은 뒤 `hx phase next`로 넘어가라. 탐색용 스크립트는 scratch/ 아래에 둔다.")
        return 0, "", ""
    for pattern, label in RISKY:
        if re.search(pattern, text):
            allowed = util.read_json(util.state_dir(root, "run") / "allow.json", {}) or {}
            if allowed.get("pattern") == pattern and time.time() - allowed.get("ts", 0) < 600:
                (util.state_dir(root, "run") / "allow.json").unlink()
                return 0, "", ""
            util.write_json(util.state_dir(root, "run") / "denied.json", {"pattern": pattern, "label": label, "ts": time.time()})
            return _deny(f"사용자 승인이 필요한 명령이다: {label}. 왜 필요한지 사용자에게 설명하고 멈춰라. "
                         f"사용자가 허락하면 `hx allow`를 실행한 뒤 같은 명령을 다시 시도한다.")
    return 0, "", ""


def allow(root):
    """Called by the agent after the user approved the last denied command; refused unless the user spoke since."""
    denied = util.read_json(util.state_dir(root, "run") / "denied.json")
    if not denied:
        raise ValueError("no command is waiting for approval")
    spoke = ledger._marker(root, "last_user_prompt")
    if spoke is None or spoke < denied["ts"]:
        raise ValueError("the user has not replied since the command was blocked: ask them and wait")
    util.write_json(util.state_dir(root, "run") / "allow.json", {"pattern": denied["pattern"], "ts": time.time()})
    return denied["label"]


def post_tool(root, payload):
    problems = []
    for name in _patched_files(payload):
        path = Path(name) if Path(name).is_absolute() else Path(payload.get("cwd") or root) / name
        if not path.is_file() or path.stat().st_size > 2_000_000:
            continue
        try:
            source = path.read_text(encoding="utf-8-sig")
            if path.suffix == ".py":
                compile(source, str(path), "exec")
            elif path.suffix == ".json":
                json.loads(source)
        except SyntaxError as exc:
            problems.append(f"{name}:{exc.lineno}: SyntaxError: {exc.msg}")
        except json.JSONDecodeError as exc:
            problems.append(f"{name}:{exc.lineno}: invalid JSON: {exc.msg}")
        except (OSError, UnicodeDecodeError, ValueError):
            pass
    if problems:
        return 2, "", "hx: the file just written does not parse; fix it before continuing:\n" + "\n".join(problems)
    return 0, "", ""


def stop(root, payload):
    """Waiting for the user is a legitimate way to end a turn: show what is waiting, never block it.
    Block only a claim of completion that the gate contradicts, and only once per set of blockers."""
    todo = collab.user_todo(root)
    if todo:
        message = "hx: 사용자 답을 기다리는 항목 — " + " / ".join(f"[{kind}] {item_id} {util.short(text, 90)}" for kind, item_id, text in todo[:6])
        return 0, json.dumps({"systemMessage": message}, ensure_ascii=False), ""
    if payload.get("stop_hook_active"):
        return 0, "", ""
    last = str(payload.get("last_assistant_message") or "")
    notes = []
    facts = collab.git_facts(root)
    if facts.get("repo") and len(facts["dirty"]) >= 3 and (not facts["last"] or time.time() - float(facts["last"]["time"]) > 30 * 60):
        notes.append(f"커밋 안 된 파일 {len(facts['dirty'])}개, 체크포인트가 30분 넘게 없음 (hx snap)")
    if DONE_CLAIM.search(last):
        blocks, _, _ = ledger.gate_eval(root)
        digest = hashlib.sha1("\n".join(blocks).encode("utf-8")).hexdigest()
        seen = util.state_dir(root, "run") / "stop_seen"
        if blocks and (not seen.is_file() or seen.read_text(encoding="utf-8") != digest):
            util.write_text(seen, digest)
            reason = ("완료라고 했지만 hx gate가 막는 항목이 있다:\n- " + "\n- ".join(blocks[:8]) +
                      "\n해결하거나, 해결할 수 없으면 무엇이 남았는지 사용자에게 그대로 알리고 멈춰라.")
            return 0, json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False), ""
    if notes:
        return 0, json.dumps({"systemMessage": "hx: " + "; ".join(notes)}, ensure_ascii=False), ""
    return 0, "", ""


HANDLERS = {"session-start": session_start, "user-prompt": user_prompt, "pre-tool": pre_tool, "post-tool": post_tool, "stop": stop}


def main(event):
    try:
        raw = sys.stdin.buffer.read()
        payload = json.loads(raw.decode("utf-8")) if raw.strip() else {}
    except (ValueError, OSError):
        payload = {}
    try:
        root = _find_root(payload)
        if root is None or event not in HANDLERS:
            return 0
        if (util.state_dir(root, "run") / "hook_debug").is_file():
            with open(util.state_dir(root, "run") / "hooks.log", "a", encoding="utf-8") as handle:
                handle.write(json.dumps({"event": event, "payload": payload}, ensure_ascii=False)[:6000] + "\n")
        code, out, err = HANDLERS[event](root, payload)
    except Exception as exc:  # fail open: a hook bug must not stall the session
        print(f"hx hook {event}: ignored error {type(exc).__name__}: {exc}", file=sys.stderr)
        return 0
    if out:
        print(out)
    if err:
        print(err, file=sys.stderr)
    return code


def config_json(command):
    """The .codex/hooks.json content. `command` is how to call this kit, e.g. 'python3 "/work/hx-kit/hx"'."""
    def handler(event, timeout=15):
        return {"type": "command", "command": f"{command} hook {event}", "timeout": timeout}
    return {"description": "hx collaboration hooks (state injection, approval for risky commands, completion check)",
            "hooks": {"SessionStart": [{"hooks": [handler("session-start")]}],
                      "UserPromptSubmit": [{"hooks": [handler("user-prompt")]}],
                      "PreToolUse": [{"matcher": "Bash", "hooks": [handler("pre-tool")]},
                                     {"matcher": "apply_patch", "hooks": [handler("pre-tool")]}],
                      "PostToolUse": [{"matcher": "apply_patch", "hooks": [handler("post-tool")]}],
                      "Stop": [{"hooks": [handler("stop")]}]}}
