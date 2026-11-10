"""`hx init` (prepare a task folder for the main and mediator Codex sessions) and `hx new app`.
User files are never overwritten: anything that already exists is kept and reported."""

import json
import re
from pathlib import Path

from . import collab, hooks, snap, util

TEMPLATES = util.KIT / "templates"
AGENTS = """<!-- HX-BEGIN -->
# 작업 지침 (hx)

이 폴더에서는 사용자와 함께 과제를 푼다. 네가 메인 세션이면 `hx-main` 스킬(`.agents/skills/hx-main/SKILL.md`)을, 사용자가 중재·검토 세션이라고 하면 `hx-mediator` 스킬을 먼저 읽고 따른다. 스킬 목록에 보이지 않으면 그 파일을 직접 읽는다. 과제 README와 과제가 준 지침이 이 문서보다 우선한다.

어느 세션이든 지킬 것:

- 답에 따라 만드는 것이 달라지는 사항(요구사항 해석, 스택·알고리즘, 범위 축소)은 사용자에게 선택지와 권장안을 보여 주고 기다린다. 대신 정하지 않는다. 그 밖의 조회·구현·테스트는 묻지 않고 진행한다.
- 분석 결과와 접근 방식을 사용자가 확인하기 전에는 제품 코드를 만들지 않는다.
- 의미 있는 상태마다 커밋한다(`hx snap`). push, 강제 초기화, 삭제, 도구 설치·업데이트는 사용자 승인 없이 하지 않는다.
- "완료"는 실제 실행 증거와 `hx gate` PASS로만 말한다.
- 현재 상태는 `collab/BOARD.md`(hx가 자동 생성), 사용자와 중재 세션이 남기는 메모는 `collab/INBOX.md`에 있다.

hx 실행: `{HX}` (명령 목록: `.hx/GUIDE.md`)
<!-- HX-END -->
"""


def _create(path, text, created, kept):
    if path.exists():
        if path.read_text(encoding="utf-8", errors="replace") != text:
            kept.append(path)
        return False
    util.write_text(path, text)
    created.append(path)
    return True


def init(root, deadline=None, with_git=False, agents=True, with_hooks=False):
    root = Path(root)
    if deadline and not re.fullmatch(r"([01]?\d|2[0-3]):[0-5]\d", deadline):
        raise ValueError("deadline must look like 16:00 (Korean time)")
    state = util.state_dir(root)
    config = util.read_json(state / "config.json", {}) or {}
    config.setdefault("created", util.stamp())
    config.setdefault("phase", "analyze")
    if deadline:
        config["deadline"] = deadline
    config["kit"] = str(util.KIT)
    util.write_json(state / "config.json", config)
    command = util.kit_cmd()
    # Files inside .hx belong to the kit and are refreshed; everything else is created only if absent.
    util.write_text(state / "GUIDE.md", (TEMPLATES / "GUIDE.md").read_text(encoding="utf-8").replace("{HX}", command))
    util.write_text(state / "DOMAIN.md", (TEMPLATES / "DOMAIN.md").read_text(encoding="utf-8"))
    created, kept, lines = [], [], []
    if agents:
        _create(root / "AGENTS.md", AGENTS.replace("{HX}", command), created, kept)
        for skill in sorted((TEMPLATES / "skills").iterdir()):
            text = (skill / "SKILL.md").read_text(encoding="utf-8").replace("{HX}", command)
            _create(root / ".agents" / "skills" / skill.name / "SKILL.md", text, created, kept)
    if with_hooks:
        _create(root / ".codex" / "hooks.json", json.dumps(hooks.config_json(command), ensure_ascii=False, indent=2) + "\n", created, kept)
    collab.write_board(root)
    if with_git:
        lines.append(snap.init_repo(root))
    lines.append(f"hx initialised in {root}  (deadline: {config.get('deadline', 'not set')} KST, phase: {config['phase']})")
    lines.extend(f"  created {util.rel(path, root)}" for path in created)
    for path in kept:
        lines.append(f"  kept existing {util.rel(path, root)} (differs, not modified)")
    if any(path.name == "AGENTS.md" for path in kept):
        lines.append("  the task has its own AGENTS.md: start the main session with "
                     "\"먼저 .agents/skills/hx-main/SKILL.md 를 읽고 그 절차로 진행해\"")
    if with_hooks:
        lines.append("  hooks: open Codex in this folder and approve them once with /hooks (they are skipped until trusted)")
    lines.append(f"hx command: {command}")
    lines.append("shared state: collab/BOARD.md (generated)  notes to the main session: collab/INBOX.md")
    return "\n".join(lines)


def new_app(root, folder="app", port=8765):
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,30}", folder):
        raise ValueError("--dir must be a simple identifier such as app or dashboard")
    root, source = Path(root), TEMPLATES / "app"
    plan = [(source / "server.py", root / folder / "server.py"),
            (source / "index.html", root / folder / "static" / "index.html"),
            (source / "test_app.py", root / "tests" / f"test_{folder}.py"),
            (source / "smoke.json", root / f"smoke_{folder}.json")]
    existing = [util.rel(target, root) for _, target in plan if target.exists()]
    if existing:
        raise ValueError(f"refusing to overwrite {existing}; choose another --dir")
    for origin, target in plan:
        text = origin.read_text(encoding="utf-8").replace("__APP__", folder).replace("8765", str(port))
        util.write_text(target, text)
    # A real package: a bare folder would lose to any installed module of the same name.
    if not (root / folder / "__init__.py").exists():
        util.write_text(root / folder / "__init__.py", "")
    command = util.kit_cmd()
    return "\n".join([
        f"created {', '.join(util.rel(target, root) for _, target in plan)}",
        "standard library only: no pip install, no CDN, works offline",
        f"run:   python {folder}/server.py --port {port}    then open http://127.0.0.1:{port}/",
        f"test:  {command} run --name {folder}-unit -- python -m unittest tests.test_{folder} -v",
        f"smoke: {command} run --name {folder}-smoke -- {command} smoke smoke_{folder}.json"])
