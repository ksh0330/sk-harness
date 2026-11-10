"""Collaboration state shared by the main session, the mediator session and the user.

Everything both sessions need lives in the ledger (.hx) and is rendered into collab/BOARD.md, so nobody
hand-edits a shared file. Free-form notes from the user or the mediator go to collab/INBOX.md (append only);
`hx inbox` shows the main session what it has not read yet. Git facts are read from git itself, never copied.
"""

import subprocess
import time
from datetime import datetime
from pathlib import Path

from . import ledger, util

PHASES = ("analyze", "design", "build", "verify", "ship")
PHASE_KO = {"analyze": "분석", "design": "설계", "build": "구현", "verify": "검증", "ship": "제출"}
SEVERITIES = ("high", "med", "low")
BOARD = Path("collab") / "BOARD.md"
INBOX = Path("collab") / "INBOX.md"
INBOX_HEAD = ("# INBOX — 사용자와 중재 세션이 메인 세션에 남기는 메모\n\n"
              "맨 아래에 이어서 적는다(기존 내용은 고치지 않는다). 담당자 DM 답변, 긴 요청, 수정 지시를 그대로 붙여넣고\n"
              "메인 세션에 \"INBOX 읽어\"라고 말하면 된다. 메인 세션은 `hx inbox`로 읽지 않은 부분만 확인한다.\n")


def config(root):
    return util.read_json(Path(root) / util.STATE / "config.json", {}) or {}


def save_config(root, data):
    util.write_json(util.state_dir(root) / "config.json", data)


def phase(root):
    return config(root).get("phase", "analyze")


# ---------------------------------------------------------------- git facts (read only)

def _git(root, *args):
    try:
        result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, encoding="utf-8",
                                errors="replace", timeout=30, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout if result.returncode == 0 else None


def git_facts(root):
    """Branch, head, work not yet committed (ignoring hx's own state files) and hx checkpoints, straight from git."""
    top = _git(root, "rev-parse", "--show-toplevel")
    if top is None:
        return {"repo": False}
    porcelain = _git(root, "status", "--porcelain", "--untracked-files=all") or ""
    dirty = [line[3:] for line in porcelain.splitlines()
             if line[3:].strip('"').split("/")[0] != util.STATE and line[3:].strip('"') != BOARD.as_posix()]
    log = _git(root, "log", "-200", "--format=%h|%ct|%s") or ""
    commits = [dict(zip(("hash", "time", "subject"), line.split("|", 2))) for line in log.splitlines() if line.count("|") >= 2]
    checkpoints = [commit for commit in commits if commit["subject"].startswith("[hx")]
    return {"repo": True, "branch": (_git(root, "rev-parse", "--abbrev-ref", "HEAD") or "?").strip(),
            "head": commits[0]["hash"] if commits else None, "commits": len(commits), "dirty": dirty,
            "checkpoints": checkpoints, "last": checkpoints[0] if checkpoints else None}


def _ago(timestamp):
    minutes = int((time.time() - float(timestamp)) // 60)
    return f"{minutes}분 전" if minutes < 120 else f"{minutes // 60}시간 {minutes % 60}분 전"


# ---------------------------------------------------------------- phases

def _must_state(root):
    state = ledger.compute(root)
    must = [item for item in state["items"] if item["kind"] == "MUST" and item["status"] != "dropped"]
    proven = [item for item in must if item["status"] == "done" and state["proof"][item["id"]][0] == "PASS"]
    return state, must, proven


def phase_blockers(root, user_said=""):
    """Why the current phase cannot be closed yet (empty list = ready)."""
    cfg, current = config(root), phase(root)
    items = ledger.load_reqs(root)["items"]
    pending = [item["id"] for item in items if item["kind"] == "DECISION" and item["status"] == "pending"]
    reasons = []
    if pending:
        reasons.append(f"user decision(s) still pending: {', '.join(pending)} (show `hx brief`, wait for the answer)")
    if current == "analyze":
        if not any(item["kind"] == "MUST" for item in items):
            reasons.append("no MUST requirement recorded (`hx req add`)")
        if not cfg.get("brief_ts"):
            reasons.append("the user has not been shown the analysis yet (`hx brief`, then stop and wait)")
        spoke = ledger._marker(root, "last_user_prompt")
        if cfg.get("brief_ts") and spoke is not None and spoke < cfg["brief_ts"]:
            reasons.append("the user has not replied since the last `hx brief`")
        if not user_said.strip():
            reasons.append("quote the user's confirmation with --user-said \"...\" (their words, not yours)")
    elif current == "design":
        chosen = [item for item in items if item["kind"] == "DECISION" and item["owner"] == "user"
                  and item["status"] == "decided" and len(item.get("options", [])) >= 2]
        if not chosen:
            reasons.append("no approach decision yet: compare at least two approaches with `hx decide add`, "
                           "let the user choose, record it with `hx decide set`")
    elif current == "build":
        _, must, proven = _must_state(root)
        missing = [item["id"] for item in must if item not in proven]
        if missing:
            reasons.append(f"MUST not yet done and proven: {', '.join(missing)}")
    elif current == "verify":
        if any(item["kind"] == "REVIEW" and item["status"] != "closed" and item["severity"] == "high" for item in items):
            reasons.append("a high-severity review item is still open or awaiting independent verification")
    return reasons


def phase_next(root, note="", user_said="", force=""):
    current = phase(root)
    if current == PHASES[-1]:
        raise ValueError("already in the last phase (ship)")
    reasons = phase_blockers(root, user_said)
    if reasons and not force.strip():
        raise ValueError("cannot close phase '" + current + "':\n  - " + "\n  - ".join(reasons)
                         + "\n  (only if the user explicitly agreed to skip this: --force \"their words\")")
    with util.lock(root):
        cfg = config(root)
        target = PHASES[PHASES.index(current) + 1]
        cfg["phase"] = target
        cfg.setdefault("phases", []).append({"from": current, "to": target, "time": util.stamp(), "note": note.strip(),
                                             "user_said": user_said.strip(), "forced": force.strip(), "skipped": reasons if force.strip() else []})
        save_config(root, cfg)
    return current, target


def phase_set(root, target, note):
    if target not in PHASES:
        raise ValueError(f"phase must be one of {PHASES}")
    if not note.strip():
        raise ValueError("--note must say why the work is moving to this phase")
    with util.lock(root):
        cfg = config(root)
        cfg.setdefault("phases", []).append({"from": cfg.get("phase", "analyze"), "to": target, "time": util.stamp(),
                                             "note": note.strip(), "user_said": "", "forced": "", "skipped": []})
        cfg["phase"] = target
        save_config(root, cfg)
    return target


def set_now(root, doing, upcoming=None):
    with util.lock(root):
        cfg = config(root)
        cfg["now"] = {"doing": doing.strip(), "next": (upcoming or "").strip(), "ts": time.time()}
        save_config(root, cfg)


def mark_brief(root):
    with util.lock(root):
        cfg = config(root)
        cfg["brief_ts"] = time.time()
        save_config(root, cfg)


# ---------------------------------------------------------------- inbox

def inbox_unread(root):
    """(text not yet read, new offset). A shrunken file (someone edited instead of appending) is shown whole."""
    path = Path(root) / INBOX
    if not path.is_file():
        return "", 0
    data = path.read_bytes()
    start = min(config(root).get("inbox_offset", len(INBOX_HEAD.encode("utf-8"))), len(data))
    if len(data) < config(root).get("inbox_offset", 0):
        start = 0
    return util.decode(data[start:]).strip(), len(data)


def inbox_read(root):
    text, size = inbox_unread(root)
    with util.lock(root):
        cfg = config(root)
        cfg["inbox_offset"] = size
        save_config(root, cfg)
    return text


# ---------------------------------------------------------------- review items (mediator -> main)

def review_add(root, text, severity="med", evidence="", ask=""):
    if severity not in SEVERITIES:
        raise ValueError(f"severity must be one of {SEVERITIES}")
    if not text.strip():
        raise ValueError("review text is empty")
    with util.lock(root):
        data = ledger.load_reqs(root)
        item = {"id": ledger._next_id(data["items"], "V"), "kind": "REVIEW", "text": text.strip(), "severity": severity,
                "evidence": evidence.strip(), "ask": ask.strip(), "status": "open", "note": "", "created": util.stamp()}
        data["items"].append(item)
        ledger.save_reqs(root, data)
    return item


def review_set(root, item_id, status, note=""):
    """open -> handled (main fixed it, says how) -> closed (mediator verified) or back to open (reopened)."""
    with util.lock(root):
        data = ledger.load_reqs(root)
        item = ledger.find_item(data, item_id)
        if item["kind"] != "REVIEW":
            raise ValueError(f"{item_id} is not a review item")
        if status not in ("open", "handled", "closed"):
            raise ValueError("review status must be open, handled or closed")
        if status == "closed" and item["status"] != "handled":
            raise ValueError("only a handled review can be independently closed")
        if status in ("handled", "open") and not note.strip():
            raise ValueError("--note must say what was done (file/commit/test) or why it is reopened")
        item["status"] = status
        item["note"] = (item["note"] + " | " if item["note"] else "") + f"{status}: {note.strip()}" if note.strip() else item["note"]
        item["updated"] = util.stamp()
        ledger.save_reqs(root, data)
    return item


def review_prompt(root):
    """A prompt the user can paste into the main session to hand over the open review items."""
    items = [item for item in ledger.load_reqs(root)["items"] if item["kind"] == "REVIEW" and item["status"] == "open"]
    if not items:
        return "열린 검토 의견이 없습니다."
    lines = ["중재 세션의 검토 의견을 처리해. collab/BOARD.md의 '검토 의견'에도 같은 내용이 있다.", ""]
    for item in items:
        lines.append(f"- {item['id']} [{item['severity']}] {item['text']}")
        if item["evidence"]:
            lines.append(f"  근거: {item['evidence']}")
        if item["ask"]:
            lines.append(f"  요청: {item['ask']}")
    lines += ["", "각 항목마다 사실인지 먼저 직접 확인하고, 맞으면 고친 뒤 관련 검사를 다시 돌려. 내 결정이 필요한 것은 "
              "`hx decide add`로 올리고 멈춰. 처리한 항목은 `hx review done <id> --note \"무엇을 바꿨는지, 커밋\"`으로 기록해."]
    return "\n".join(lines)


# ---------------------------------------------------------------- board

def user_todo(root):
    """Everything that is waiting on the user, as (kind, id, text) tuples."""
    todo = []
    for item in ledger.load_reqs(root)["items"]:
        if item["kind"] == "DECISION" and item["status"] == "pending":
            todo.append(("결정", item["id"], f"{item['text']} — 선택지: {' / '.join(item['options'])} · 권장: {item['recommend'] or '-'}"
                         + (f" ({item['why']})" if item["why"] else "")))
        elif item["kind"] == "QUESTION" and item["status"] == "open" and item.get("to") == "dm":
            todo.append(("담당자에게 질문", item["id"], f"\"{item['text']}\"" + (f" · 이유: {item['why']}" if item.get("why") else "")
                         + (f" · 답이 없으면: {item['assume']}" if item["assume"] else "")))
        elif item["kind"] == "QUESTION" and item["status"] == "open":
            todo.append(("질문", item["id"], f"{item['text']}" + (f" · 답이 없으면: {item['assume']}" if item["assume"] else "")))
    return todo


def render_board(root):
    root = Path(root)
    state, must, proven = _must_state(root)
    cfg, facts, items = config(root), git_facts(root), state["items"]
    now = cfg.get("now") or {}
    lines = ["# 작업 보드", "", "> hx가 자동으로 만든다. 직접 고치지 말 것. 메인 세션에 남길 말은 `collab/INBOX.md` 맨 아래에 적는다.", "",
             f"- 단계: **{PHASE_KO[phase(root)]}** ({PHASES.index(phase(root)) + 1}/{len(PHASES)}) · {ledger.time_left(root)[1]}",
             f"- 지금: {now.get('doing') or '(기록 없음: `hx now`)'}" + (f" ({_ago(now['ts'])} 기록)" if now.get("ts") else "")
             + (f" · 다음: {now['next']}" if now.get("next") else "")]
    if facts["repo"]:
        last = facts["last"]
        lines.append(f"- Git: 브랜치 `{facts['branch']}` · HEAD `{facts['head'] or '커밋 없음'}` · 커밋 {facts['commits']}개 · "
                     f"커밋 안 된 파일 {len(facts['dirty'])}개 · 마지막 체크포인트 "
                     + (f"`{last['hash']}` {_ago(last['time'])} ({last['subject']})" if last else "없음"))
    else:
        lines.append("- Git: 저장소 아님 (`hx init --git`)")
    unread = inbox_unread(root)[0]
    if unread:
        lines.append(f"- INBOX에 메인 세션이 아직 읽지 않은 내용 {len(unread.splitlines())}줄")
    lines += ["", "## 사용자가 할 일"]
    lines += [f"- [{kind}] {item_id}: {text}" for kind, item_id, text in user_todo(root)] or ["- 없음"]
    lines += ["", f"## 요구사항 (MUST 증명 {len(proven)}/{len(must)})", "| id | 종류 | 상태 | 증명 | 요구사항 | 확인 방법 |", "|---|---|---|---|---|---|"]
    for item in items:
        if item["kind"] in ledger.KINDS:
            proof, linked = state["proof"][item["id"]]
            lines.append(f"| {item['id']} | {item['kind']} | {item['status']} | {proof}{' (' + ', '.join(linked) + ')' if linked else ''} | "
                         f"{util.short(item['text'], 80)} | {util.short(item['accept'], 60) or '-'} |")
    decisions = [item for item in items if item["kind"] == "DECISION" and item["status"] == "decided"]
    if decisions:
        lines += ["", "## 결정 기록"]
        for item in decisions:
            who = "AI 자율" if item["owner"] == "ai" else "사용자" if item.get("confirmed") else "사용자(에이전트가 기록)"
            lines.append(f"- {item['id']} [{who}] {item['text']} → **{item['choice']}**" + (f" · {item['note'] or item['why']}" if item["note"] or item["why"] else ""))
    answered = [item for item in items if item["kind"] == "QUESTION" and item["status"] == "answered"]
    if answered:
        lines += ["", "## 받은 답변"]
        lines += [f"- {item['id']} [{'담당자' if item.get('source') == 'dm' else '사용자'}] {item['text']} → {item['answer']}" for item in answered]
    reviews = [item for item in items if item["kind"] == "REVIEW"]
    if reviews:
        lines += ["", "## 검토 의견 (중재 세션)", "| id | 심각도 | 상태 | 내용 | 근거 | 요청 | 처리 |", "|---|---|---|---|---|---|---|"]
        lines += [f"| {item['id']} | {item['severity']} | {item['status']} | {util.short(item['text'], 90)} | {util.short(item['evidence'], 60) or '-'} | "
                  f"{util.short(item['ask'], 60) or '-'} | {util.short(item['note'], 80) or '-'} |" for item in reviews]
    feedback = [item for item in items if item["kind"] == "FEEDBACK"]
    if feedback:
        lines += ["", "## 사용자 피드백"]
        lines += [f"- {item['id']} [{item['status']}] {util.short(item['text'], 100)}" + (f" → {item['note']}" if item["note"] else "") for item in feedback]
    if facts["repo"] and facts["checkpoints"]:
        lines += ["", "## 체크포인트 (git에서 읽음)", "| 커밋 | 시각 | 내용 |", "|---|---|---|"]
        lines += [f"| `{commit['hash']}` | {datetime.fromtimestamp(float(commit['time'])).strftime('%H:%M')} | {util.short(commit['subject'], 90)} |"
                  for commit in facts["checkpoints"][:12]]
    if state["checks"]:
        lines += ["", "## 검사", "| 이름 | 상태 | 마지막 실행 | 결과 |", "|---|---|---|---|"]
        for name in state["checks"]:
            record = state["latest"].get(name)
            lines.append(f"| {name} | {state['states'][name]} | {record['time'][11:19] if record else '-'} | "
                         f"{util.short((record or {}).get('summary') or ', '.join((record or {}).get('flags', [])), 60) or '-'} |")
    history = cfg.get("phases") or []
    if history:
        lines += ["", "## 단계 이력"]
        lines += [f"- {entry['time'][11:16]} {entry['from']} → {entry['to']}" + (f" · {entry['note']}" if entry["note"] else "")
                  + (f" · 사용자: \"{entry['user_said']}\"" if entry["user_said"] else "")
                  + (f" · **강제 진행**: {entry['forced']} (건너뜀: {'; '.join(entry['skipped'])})" if entry["forced"] else "") for entry in history]
    return "\n".join(lines) + "\n"


def write_board(root):
    """Refresh collab/BOARD.md and create the inbox if missing. Only the body is compared, so idle runs do not rewrite."""
    root = Path(root)
    if not (root / util.STATE / "config.json").is_file():
        return
    with util.lock(root):
        if not (root / INBOX).is_file():
            util.write_text(root / INBOX, INBOX_HEAD)
        content = render_board(root)
        board = root / BOARD
        if not board.is_file() or board.read_text(encoding="utf-8") != content:
            util.write_text(board, content)


# ---------------------------------------------------------------- audit (for the mediator; changes nothing)

def audit(root):
    """Facts and discrepancies between what the ledger says and what git/files/evidence show. Returns findings."""
    root = Path(root)
    state, must, proven = _must_state(root)
    cfg, facts, items, findings = config(root), git_facts(root), state["items"], []
    current = phase(root)
    now = cfg.get("now") or {}
    print(f"phase    {current} ({PHASES.index(current) + 1}/{len(PHASES)})   {ledger.time_left(root)[1]}")
    print(f"now      {now.get('doing') or '(nothing recorded)'}" + (f"  [{_ago(now['ts'])}]" if now.get("ts") else ""))
    if facts["repo"]:
        last = facts["last"]
        print(f"git      branch={facts['branch']} head={facts['head']} commits={facts['commits']} uncommitted_files={len(facts['dirty'])} "
              f"last_checkpoint={(last['hash'] + ' ' + _ago(last['time'])) if last else 'none'}")
        if facts["dirty"]:
            print("         uncommitted: " + ", ".join(facts["dirty"][:8]) + (" ..." if len(facts["dirty"]) > 8 else ""))
        if not facts["commits"]:
            findings.append(("high", "no commit exists at all: nothing is preserved (hx snap --wip, or hx phase next)"))
        elif len(facts["dirty"]) >= 3 and (not last or time.time() - float(last["time"]) > 30 * 60):
            findings.append(("med", f"{len(facts['dirty'])} file(s) changed and no checkpoint for "
                                    f"{_ago(last['time']) if last else 'the whole session'}: a checkpoint is overdue"))
        if current in ("build", "verify", "ship") and not any(c["subject"].startswith("[hx-ok") for c in facts["checkpoints"]):
            findings.append(("med", f"phase is {current} but there is no verified checkpoint (hx-ok) yet"))
    else:
        print("git      not a repository")
        findings.append(("high", "the task folder is not a git repository: no history, no recovery point"))
    print(f"reqs     MUST proven {len(proven)}/{len(must)}; checks " + (", ".join(f"{n}={s}" for n, s in state["states"].items()) or "none"))
    for item in items:
        if item["kind"] in ledger.KINDS and item["status"] == "done":
            proof, linked = state["proof"][item["id"]]
            if proof != "PASS":
                findings.append(("high", f"{item['id']} is marked done but its proof is {proof}"
                                         + (f" ({', '.join(linked)})" if linked else " (no check linked)") + f": {util.short(item['text'], 60)}"))
    for name, value in state["states"].items():
        if value == "FAIL":
            findings.append(("high", f"check {name} is failing: {state['latest'][name]['log']}"))
        elif value == "STALE":
            findings.append(("med", f"check {name} passed before the latest source change and was not re-run"))
    for item in items:
        if item["kind"] == "DECISION" and item["status"] == "pending":
            findings.append(("med", f"{item['id']} waits for the user: {util.short(item['text'], 70)}"))
        if item["kind"] == "DECISION" and item["owner"] == "user" and item["status"] == "decided" and not item.get("confirmed"):
            findings.append(("low", f"{item['id']} is recorded as the user's choice ({util.short(item['choice'], 40)}); "
                                    f"verify the recorded quote against the conversation, because a hook cannot prove consent"))
        if item["kind"] == "QUESTION" and item["status"] == "open":
            target = "stakeholder (DM)" if item.get("to") == "dm" else "user"
            findings.append(("low", f"{item['id']} unanswered question for the {target}; working assumption: {item['assume'] or 'NONE'}"))
        if item["kind"] == "FEEDBACK" and item["status"] == "open":
            findings.append(("med", f"{item['id']} user feedback not handled: {util.short(item['text'], 70)}"))
        if item["kind"] == "REVIEW" and item["status"] == "open":
            findings.append(("med" if item["severity"] != "high" else "high", f"{item['id']} review item still open: {util.short(item['text'], 70)}"))
        if item["kind"] == "REVIEW" and item["status"] == "handled":
            findings.append(("low", f"{item['id']} was handled by the main session; verify and `hx review close {item['id']}`: {item['note']}"))
    if current != "analyze" and not any(item["kind"] == "DECISION" and item["owner"] == "user" for item in items):
        findings.append(("high", "work moved past analysis without a single decision put to the user"))
    if current in ("build", "verify", "ship") and not any(item["kind"] == "QUESTION" for item in items):
        findings.append(("low", "no question or assumption was ever recorded: was the task really free of ambiguity?"))
    for entry in cfg.get("phases") or []:
        if entry.get("forced"):
            findings.append(("med", f"phase {entry['from']} was closed with --force ({entry['forced']}); skipped: {'; '.join(entry['skipped'])}"))
    if inbox_unread(root)[0]:
        findings.append(("med", "collab/INBOX.md has content the main session has not read (`hx inbox`)"))
    if now.get("ts") and time.time() - now["ts"] > 45 * 60:
        findings.append(("low", f"the main session's 'now' note is {_ago(now['ts'])} old"))
    board = root / BOARD
    if board.is_file():
        def body(text):
            return [line for line in text.splitlines() if not line.startswith(("- 단계:", "- 지금:", "- Git:"))]
        if body(board.read_text(encoding="utf-8")) != body(render_board(root)):
            findings.append(("low", "collab/BOARD.md differs from the ledger (hand-edited or stale); any hx command refreshes it"))
    order = {"high": 0, "med": 1, "low": 2}
    findings.sort(key=lambda finding: order[finding[0]])
    for level, text in findings:
        print(f"[{level.upper()}] {text}")
    print(f"AUDIT: {len(findings)} finding(s)  high={sum(1 for f in findings if f[0] == 'high')}")
    return findings
