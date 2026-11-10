"""The collaboration layer: user decisions, stakeholder questions, feedback, phases, the shared board,
the mediator's audit and review items, hooks, intake and the submission report."""

import json
import os
import shutil
import subprocess
import sys
import threading
import time
import unittest
import zipfile

from support import KIT, TempCase, hx

CALC = "def add(a, b):\n    return a + b\n"
TEST = "import unittest, calc\n\nclass T(unittest.TestCase):\n    def test_add(self):\n        self.assertEqual(calc.add(2, 3), 5)\n"


class Base(TempCase):
    git_repo = False

    def setUp(self):
        super().setUp()
        self.write("README.md", "# 과제: 덧셈기\n입력 두 수를 더한다.\n")
        self.hx("init", "--deadline", "23:59", *(["--git"] if self.git_repo else []))

    def hx(self, *args, expect=0, stdin=None):
        code, out = hx(*args, cwd=self.dir, stdin=stdin)
        if expect is not None:
            self.assertEqual(code, expect, out)
        return out

    def hook(self, event, **payload):
        code, out = hx("hook", event, cwd=self.dir, stdin=json.dumps({"cwd": str(self.dir), **payload}))
        return code, out.strip()

    def board(self):
        return (self.dir / "collab" / "BOARD.md").read_text(encoding="utf-8")

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.dir), *args], capture_output=True, text=True, encoding="utf-8").stdout.strip()

    def user_speaks(self):
        """What the UserPromptSubmit hook does when the real user sends a message."""
        time.sleep(0.05)
        self.hook("user-prompt", prompt="...")
        time.sleep(0.05)


class Decisions(Base):
    def test_decision_waits_for_the_user_and_blocks_completion_until_answered(self):
        self.hx("req", "add", "덧셈", "--accept", "add(2,3)=5")
        self.assertIn("at least two --option", self.hx("decide", "add", "스택", "--option", "A: 파이썬", expect=2))
        out = self.hx("decide", "add", "핵심 알고리즘", "--option", "A: 탐욕 30분", "--option", "B: MILP 90분",
                      "--recommend", "A", "--why", "시간 안에 확실히 끝남", "--impact", "B는 미완성 위험")
        self.assertIn("added D1 (pending, the user decides)", out)
        self.assertIn("hx brief", out)
        brief = self.hx("brief")
        for expected in ("## 내가 이해한 과제 (요구사항 1개)", "R1 [MUST] 덧셈  (확인 방법: add(2,3)=5)", "### D1 핵심 알고리즘",
                         "- A: 탐욕 30분", "- B: MILP 90분", "- 권장: A — 시간 안에 확실히 끝남", "- 영향: B는 미완성 위험",
                         "BRIEF: 1 decision(s) and 0 question(s) for the user", "end your turn and wait"):
            self.assertIn(expected, brief)
        self.assertIn("[결정] D1: 핵심 알고리즘 — 선택지: A: 탐욕 30분 / B: MILP 90분 · 권장: A", self.board())
        self.assertIn("BLOCK D1 awaits the user's decision", self.hx("gate", expect=1))
        self.hx("decide", "set", "D1", "--choice", "A", "--note", "A로 가자")
        self.assertIn("D1 [사용자(에이전트가 기록)] 핵심 알고리즘 → **A** · A로 가자", self.board())
        self.assertNotIn("D1 awaits", self.hx("gate", expect=1))
        out = self.hx("decide", "log", "CSV 인코딩", "--choice", "utf-8-sig", "--why", "엑셀 호환")
        self.assertIn("logged D2 (decided by the agent)", out)
        self.assertIn("D2 [AI 자율] CSV 인코딩 → **utf-8-sig**", self.board())
        self.assertIn("is not a user decision", self.hx("decide", "set", "D2", "--choice", "x", expect=2))

    def test_with_hooks_the_agent_cannot_answer_its_own_question(self):
        self.user_speaks()                                               # the user's first message
        self.hx("decide", "add", "범위", "--option", "A: 전체", "--option", "B: 축소")
        out = self.hx("decide", "set", "D1", "--choice", "A", "--note", "내가 정함", expect=2)
        self.assertIn("was raised after the user's last message", out)
        self.user_speaks()                                               # now the user really replied
        self.assertIn("D1 decided by the user: A", self.hx("decide", "set", "D1", "--choice", "A", "--note", "A로"))
        self.assertIn("D1 [사용자(에이전트가 기록)] 범위 → **A**", self.board())
        decision = json.loads((self.dir / ".hx" / "reqs.json").read_text(encoding="utf-8"))["items"][-1]
        self.assertFalse(decision["confirmed"])
        self.assertTrue(decision["prompt_observed"])

    def test_stakeholder_questions_feedback_and_inbox(self):
        out = self.hx("ask", "음수 입력도 더해야 합니까?", "--to", "dm", "--why", "입력 검증 범위가 달라짐", "--assume", "음수 허용")
        self.assertIn("added Q1 (for the stakeholder, via the user)", out)
        self.hx("ask", "출력 소수 자릿수?", "--assume", "2자리")
        board = self.board()
        self.assertIn('[담당자에게 질문] Q1: "음수 입력도 더해야 합니까?" · 이유: 입력 검증 범위가 달라짐 · 답이 없으면: 음수 허용', board)
        self.assertIn("[질문] Q2: 출력 소수 자릿수? · 답이 없으면: 2자리", board)
        out = self.hx("answer", "Q1", "음수는 오류로 처리해 주세요")
        self.assertIn("answered by the stakeholder (DM)", out)
        self.assertIn("Q1 [담당자] 음수 입력도 더해야 합니까? → 음수는 오류로 처리해 주세요", self.board())
        self.assertNotIn("[담당자에게 질문] Q1", self.board())
        self.assertIn("added F1", self.hx("feedback", "add", "결과를 JSON으로도 내보내 줘"))
        self.hx("req", "add", "덧셈")
        self.assertIn("BLOCK F1 user feedback not yet handled", self.hx("gate", expect=1))
        self.assertIn("--note", self.hx("feedback", "done", "F1", "--note", " ", expect=2))
        self.hx("feedback", "done", "F1", "--note", "R2 추가")
        self.assertNotIn("F1 user feedback", self.hx("gate", expect=1))
        self.assertEqual(self.hx("inbox").strip(), "INBOX: nothing new")
        with open(self.dir / "collab" / "INBOX.md", "a", encoding="utf-8") as handle:
            handle.write("\n## 담당자 DM 답변 14:02\n단위는 분입니다.\n")
        self.assertIn("INBOX에 메인 세션이 아직 읽지 않은 내용", self.hx("status") and (self.hx("now", "작업 중"), self.board())[1])
        out = self.hx("inbox")
        self.assertIn("단위는 분입니다.", out)
        self.assertNotIn("맨 아래에 이어서", out)                          # only the new part, not the file header
        self.assertEqual(self.hx("inbox").strip(), "INBOX: nothing new")
        self.assertNotIn("읽지 않은", self.board())


class Phases(Base):
    git_repo = True

    def test_phases_enforce_asking_first_and_commit_at_each_boundary(self):
        out = self.hx("phase")
        self.assertIn("PHASE: analyze", out)
        self.assertIn("no MUST requirement recorded", out)
        out = self.hx("phase", "next", expect=2)
        for expected in ("cannot close phase 'analyze'", "no MUST requirement", "has not been shown the analysis", "--user-said"):
            self.assertIn(expected, out)
        self.hx("req", "add", "덧셈", "--accept", "add(2,3)=5")
        self.hx("decide", "add", "입력 형식", "--option", "A: CLI 인자", "--option", "B: 파일")
        self.hx("brief")
        out = self.hx("phase", "next", "--user-said", "네 그렇게", expect=2)
        self.assertIn("user decision(s) still pending: D1", out)
        self.hx("decide", "set", "D1", "--choice", "A", "--note", "CLI로")
        out = self.hx("phase", "next", "--user-said", "네 그렇게 진행하세요", "--note", "요구 1개, 결정 1개")
        self.assertIn("PHASE: analyze -> design", out)
        self.assertRegex(out, r"checkpoint [0-9a-f]{7,} \(\d+ file\(s\)\)")
        self.assertEqual(self.git("log", "-1", "--format=%s"), "[hx-phase] analyze done -> design: 요구 1개, 결정 1개")
        self.assertIn(".hx/reqs.json", self.git("show", "--name-only", "--format=", "HEAD"))   # analysis is committed before any code
        self.assertIn('analyze → design · 요구 1개, 결정 1개 · 사용자: "네 그렇게 진행하세요"', self.board())
        self.assertIn("PHASE: design -> build", self.hx("phase", "next"))    # D1 had two options and the user chose
        self.write("calc.py", CALC)
        out = self.hx("phase", "next", expect=2)
        self.assertIn("MUST not yet done and proven: R1", out)
        self.write("test_calc.py", TEST)
        self.hx("run", "--name", "unit", "--req", "R1", "--done", "--", "python", "-m", "unittest", "test_calc")
        self.assertIn("PHASE: build -> verify", self.hx("phase", "next"))
        self.assertIn("calc.py", self.git("show", "--name-only", "--format=", "HEAD"))
        self.assertIn("PHASE: now design", self.hx("phase", "set", "design", "--note", "담당자 답변으로 요구 변경"))
        self.assertIn("--note must say why", self.hx("phase", "set", "build", expect=2))

    def test_design_needs_a_real_choice_between_approaches_and_force_is_recorded(self):
        self.hx("req", "add", "덧셈")
        self.hx("brief")
        self.hx("phase", "next", "--user-said", "좋아요")
        self.hx("decide", "log", "언어", "--choice", "python")             # the agent's own log is not a user choice
        out = self.hx("phase", "next", expect=2)
        self.assertIn("no approach decision yet: compare at least two approaches", out)
        self.assertIn("PHASE: design -> build", self.hx("phase", "next", "--force", "사용자: 시간 없으니 바로 구현해"))
        audit = self.hx("audit")
        self.assertIn("[MED] phase design was closed with --force (사용자: 시간 없으니 바로 구현해)", audit)
        self.assertIn("[HIGH] work moved past analysis without a single decision put to the user", audit)
        self.assertIn("**강제 진행**", self.board())


class Mediator(Base):
    git_repo = True

    def test_audit_finds_what_the_main_session_did_not_say(self):
        self.hx("req", "add", "덧셈", "--accept", "add(2,3)=5")
        self.hx("req", "add", "뺄셈")
        self.hx("req", "set", "R2", "--status", "done")
        self.write("calc.py", CALC)
        self.write("test_calc.py", TEST)
        self.write("extra.py", "x = 1\n")
        self.hx("run", "--name", "unit", "--req", "R1", "--done", "--", "python", "-m", "unittest", "test_calc")
        self.hx("phase", "set", "build", "--note", "테스트용")
        before = {path: path.read_bytes() for path in (self.dir / ".hx").glob("*.json*")}
        audit = self.hx("audit")
        for expected in ("phase    build (3/5)", "uncommitted_files=3", "uncommitted: calc.py, extra.py, test_calc.py",
                         "reqs     MUST proven 1/2; checks unit=PASS",
                         "[HIGH] R2 is marked done but its proof is NONE (no check linked): 뺄셈",
                         "[HIGH] work moved past analysis without a single decision put to the user",
                         "[MED] phase is build but there is no verified checkpoint (hx-ok) yet",
                         "[LOW] no question or assumption was ever recorded"):
            self.assertIn(expected, audit)
        self.assertRegex(audit, r"AUDIT: \d+ finding\(s\)  high=2")
        self.assertEqual(before, {path: path.read_bytes() for path in (self.dir / ".hx").glob("*.json*")})  # audit wrote nothing
        future = time.time() + 5
        os.utime(self.dir / "calc.py", (future, future))
        self.assertIn("[MED] check unit passed before the latest source change and was not re-run", self.hx("audit"))
        os.utime(self.dir / "calc.py", None)
        (self.dir / "collab" / "BOARD.md").write_text(self.board().replace("덧셈", "곱셈"), encoding="utf-8")
        self.assertIn("collab/BOARD.md differs from the ledger", self.hx("audit"))

    def test_review_items_travel_from_mediator_to_main_and_back(self):
        self.hx("req", "add", "덧셈")
        out = self.hx("review", "add", "분석 산출물이 커밋되지 않음", "--severity", "high", "--evidence", "git log: hx-base뿐",
                      "--ask", "hx snap --wip으로 보존")
        self.assertIn("added V1 [high] open", out)
        self.hx("review", "add", "README에 실행 방법 없음", "--severity", "low")
        prompt = self.hx("review", "prompt")
        for expected in ("중재 세션의 검토 의견을 처리해", "- V1 [high] 분석 산출물이 커밋되지 않음", "근거: git log: hx-base뿐",
                         "요청: hx snap --wip으로 보존", "- V2 [low] README에 실행 방법 없음", "hx review done <id>"):
            self.assertIn(expected, prompt)
        self.assertIn("| V1 | high | open | 분석 산출물이 커밋되지 않음 | git log: hx-base뿐 | hx snap --wip으로 보존 | - |", self.board())
        gate = self.hx("gate", expect=1)
        self.assertIn("BLOCK V1 review item open [high]", gate)
        self.assertIn("WARN  V2 review item open [low]", gate)
        self.assertIn("--note must say what was done", self.hx("review", "done", "V1", expect=2))
        self.hx("review", "done", "V1", "--note", "hx snap --wip 실행, 커밋 abc1234")
        self.assertIn("[LOW] V1 was handled by the main session; verify and `hx review close V1`", self.hx("audit"))
        self.hx("review", "reopen", "V1", "--note", "커밋에 계획 문서가 빠짐")
        self.assertIn("| V1 | high | open |", self.board())
        self.assertIn("handled: hx snap --wip 실행, 커밋 abc1234 \\| open: 커밋에 계획 문서가 빠짐", self.board())
        self.hx("review", "done", "V1", "--note", "문서 포함 재커밋")
        self.hx("review", "close", "V1")
        self.assertNotIn("V1 review item", self.hx("gate", expect=1))
        self.assertNotIn("V1", self.hx("review", "prompt"))

    def test_unrecorded_rerun_and_scoped_staleness(self):
        self.write("calc.py", CALC)
        self.write("test_calc.py", TEST)
        self.write("web/page.py", "TITLE = 'x'\n")
        self.hx("run", "--name", "unit", "--watch", "calc.py,test_*.py", "--", "python", "-m", "unittest", "test_calc")
        self.hx("run", "--name", "all", "--", "python", "-m", "unittest", "test_calc")
        evidence = (self.dir / ".hx" / "evidence.jsonl").read_bytes()
        out = self.hx("regress", "--no-record")
        self.assertIn("REGRESS (not recorded): PASS  ran=2 failed=0", out)
        self.assertEqual(evidence, (self.dir / ".hx" / "evidence.jsonl").read_bytes())
        future = time.time() + 5
        os.utime(self.dir / "web" / "page.py", (future, future))          # unrelated to what `unit` watches
        status = self.hx("status")
        self.assertIn("| unit | PASS |", status)
        self.assertIn("| all | STALE |", status)
        out = self.hx("regress", "--stale")
        self.assertIn("ran=1 failed=0", out)
        self.assertIn("HX-RUN #3 all", out)

    def test_two_sessions_writing_at_once_lose_nothing(self):
        errors = []

        def add(kind, count):
            for n in range(count):
                args = ("req", "add", f"요구 {n}") if kind == "main" else ("review", "add", f"의견 {n}")
                code, out = hx(*args, cwd=self.dir)
                if code:
                    errors.append(out)

        threads = [threading.Thread(target=add, args=("main", 8)), threading.Thread(target=add, args=("mediator", 8))]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(errors, [])
        items = json.loads((self.dir / ".hx" / "reqs.json").read_text(encoding="utf-8"))["items"]
        self.assertEqual(sorted(item["id"] for item in items), sorted([f"R{n}" for n in range(1, 9)] + [f"V{n}" for n in range(1, 9)]))


class Hooks(Base):
    git_repo = True

    def context(self, out):
        return json.loads(out)["hookSpecificOutput"]["additionalContext"]

    def test_session_start_and_prompt_inject_state_and_record_that_the_user_spoke(self):
        self.hx("req", "add", "덧셈")
        self.hx("decide", "add", "범위", "--option", "A: 전체", "--option", "B: 축소")
        code, out = self.hook("session-start", source="startup")
        self.assertEqual(code, 0)
        text = self.context(out)
        for expected in ("[hx] 단계 analyze", "MUST 증명 0/1", "사용자 답을 기다리는 항목: D1(결정)", "대신 정하지 말 것", "hx-main"):
            self.assertIn(expected, text)
        self.assertFalse((self.dir / ".hx" / "run" / "last_user_prompt").exists())
        code, out = self.hook("user-prompt", prompt="A로 해")
        self.assertIn("D1(결정)", self.context(out))
        self.assertTrue((self.dir / ".hx" / "run" / "last_user_prompt").is_file())

    def test_stop_never_blocks_while_waiting_for_the_user(self):
        self.hx("req", "add", "덧셈")
        self.hx("decide", "add", "범위", "--option", "A: 전체", "--option", "B: 축소")
        code, out = self.hook("stop", last_assistant_message="분석을 완료했습니다. 아래 결정을 부탁드립니다.")
        reply = json.loads(out)
        self.assertEqual(code, 0)
        self.assertNotIn("decision", reply)                               # waiting for the user is a valid stop
        self.assertIn("사용자 답을 기다리는 항목 — [결정] D1 범위", reply["systemMessage"])

    def test_stop_blocks_an_unfounded_completion_claim_once(self):
        self.hx("req", "add", "덧셈")
        code, out = self.hook("stop", last_assistant_message="구현을 진행 중입니다. 다음은 테스트입니다.")
        self.assertEqual((code, out), (0, ""))                            # ordinary stop: nothing to say
        code, out = self.hook("stop", last_assistant_message="모든 작업을 완료했습니다.")
        reply = json.loads(out)
        self.assertEqual(reply["decision"], "block")
        self.assertIn("R1 [MUST] 덧셈: status=todo", reply["reason"])
        code, out = self.hook("stop", last_assistant_message="모든 작업을 완료했습니다.")
        self.assertEqual(out, "")                                         # same blockers: do not loop
        code, out = self.hook("stop", last_assistant_message="All done.", stop_hook_active=True)
        self.assertEqual(out, "")

    def test_pre_tool_keeps_product_code_out_of_the_analysis_phase(self):
        patch = "*** Begin Patch\n*** Add File: src/solver.py\n+x = 1\n*** End Patch"
        code, out = self.hook("pre-tool", tool_name="apply_patch", tool_input={"command": patch})
        decision = json.loads(out)["hookSpecificOutput"]
        self.assertEqual(decision["permissionDecision"], "deny")
        self.assertIn("src/solver.py", decision["permissionDecisionReason"])
        self.assertIn("hx brief", decision["permissionDecisionReason"])
        for allowed in ("docs/PLAN.md", "scratch/explore.py", "notes.md"):
            patch = f"*** Begin Patch\n*** Add File: {allowed}\n+x\n*** End Patch"
            self.assertEqual(self.hook("pre-tool", tool_name="apply_patch", tool_input={"command": patch}), (0, ""), allowed)
        self.hx("phase", "set", "build", "--note", "테스트")
        patch = "*** Begin Patch\n*** Update File: src/solver.py\n*** End Patch"
        self.assertEqual(self.hook("pre-tool", tool_name="apply_patch", tool_input={"command": patch}), (0, ""))

    def test_pre_tool_asks_for_approval_before_risky_commands(self):
        for command in ("git push origin main", "git reset --hard HEAD~3", "git clean -fd", "rm -rf .git", "codex update",
                        "cd app && git push"):
            code, out = self.hook("pre-tool", tool_name="Bash", tool_input={"command": command})
            self.assertEqual(json.loads(out)["hookSpecificOutput"]["permissionDecision"], "deny", command)
        for command in ("git status", "git commit -m x", "rm -rf build", "python -m unittest", "git log --oneline", "git reset --soft HEAD~1"):
            self.assertEqual(self.hook("pre-tool", tool_name="Bash", tool_input={"command": command}), (0, ""), command)
        self.hook("pre-tool", tool_name="Bash", tool_input={"command": "git push"})
        self.assertIn("has not replied since", self.hx("allow", expect=2))
        self.user_speaks()
        self.assertIn("allowed once: git push", self.hx("allow"))
        self.assertEqual(self.hook("pre-tool", tool_name="Bash", tool_input={"command": "git push"}), (0, ""))
        code, out = self.hook("pre-tool", tool_name="Bash", tool_input={"command": "git push"})
        self.assertIn("deny", out)                                         # the approval was for one use

    def test_post_tool_reports_a_file_that_does_not_parse(self):
        self.write("bad.py", "def f(:\n    pass\n")
        self.write("ok.py", "x = 1\n")
        self.write("bad.json", '{"a": 1,}')
        patch = "*** Begin Patch\n*** Add File: bad.py\n*** Add File: ok.py\n*** Add File: bad.json\n*** End Patch"
        code, out = self.hook("post-tool", tool_name="apply_patch", tool_input={"command": patch})
        self.assertEqual(code, 2)
        self.assertIn("bad.py:1: SyntaxError", out)
        self.assertIn("bad.json:1: invalid JSON", out)
        self.assertNotIn("ok.py", out)

    def test_hooks_fail_open(self):
        code, out = hx("hook", "stop", cwd=self.dir, stdin="this is not json")
        self.assertEqual((code, out.strip()), (0, ""))
        outside = self.dir.parent
        code, out = hx("hook", "session-start", cwd=outside, stdin=json.dumps({"cwd": str(outside)}))
        self.assertEqual((code, out.strip()), (0, ""))                    # not an hx project: stay silent


class IntakeAndShip(Base):
    git_repo = True

    def make_docx(self, name, paragraphs):
        body = "".join(f"<w:p><w:r><w:t>{text}</w:t></w:r></w:p>" for text in paragraphs)
        (self.dir / name).parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(self.dir / name, "w") as archive:
            archive.writestr("word/document.xml", f'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>{body}</w:body></w:document>')

    def test_intake_reads_documents_data_and_tooling_in_one_pass(self):
        self.make_docx("docs/과제.docx", ["설비별 LOT 배정", "납기 지연을 최소화한다"])
        with zipfile.ZipFile(self.dir / "docs" / "발표.pptx", "w") as archive:
            archive.writestr("ppt/slides/slide1.xml", '<p:sld xmlns:p="p" xmlns:a="a"><a:p><a:r><a:t>평가 기준: TWT</a:t></a:r></a:p></p:sld>')
        with zipfile.ZipFile(self.dir / "docs" / "안내.hwpx", "w") as archive:
            archive.writestr("Contents/section0.xml", '<hs:sec xmlns:hs="s" xmlns:hp="p"><hp:p><hp:run><hp:t>제출은 16시까지</hp:t></hp:run></hp:p></hs:sec>')
        self.write("docs/old.hwp", "binary")
        self.write("data/lots.csv", "lot_id,eqp_id,qty\nL1,E1,25\nL2,E9,abc\n" + "".join(f"L{n},E1,{n}\n" for n in range(3, 40)))
        self.write("data/eqp.csv", "eqp_id\nE1\nE2\n")
        self.write("package.json", "{}")
        self.write("src/app.js", "console.log(1)\n")
        out = self.hx("intake")
        for expected in ("docs/과제.docx  -> text extracted to .hx/intake/docs__과제.docx.txt", "docs/발표.pptx  -> text extracted",
                         "docs/안내.hwpx  -> text extracted", "docs/old.hwp  !! NOT READABLE: binary .hwp", "README.md",
                         "data/lots.csv  rows=39 cols=3 [lot_id, eqp_id, qty]  high=1",
                         "HIGH qty: 1 non-numeric value(s) in a numeric column",
                         "reference broken: lots.eqp_id -> eqp.eqp_id: 1 value(s) without parent, e.g. ['E9']",
                         "project markers: package.json (Node project)", "1×.js", "git: branch"):
            self.assertIn(expected, out)
        self.assertEqual((self.dir / ".hx" / "intake" / "docs__과제.docx.txt").read_text(encoding="utf-8").split("\n")[:2],
                         ["설비별 LOT 배정", "납기 지연을 최소화한다"])
        self.assertIn("평가 기준: TWT", (self.dir / ".hx" / "intake" / "docs__발표.pptx.txt").read_text(encoding="utf-8"))
        self.assertIn("제출은 16시까지", (self.dir / ".hx" / "intake" / "docs__안내.hwpx.txt").read_text(encoding="utf-8"))
        self.assertNotIn("collab/", out)                                   # hx's own files are not task material

    def test_ship_ties_requirements_to_proof_and_catches_last_minute_problems(self):
        self.hx("req", "add", "덧셈", "--accept", "add(2,3)=5")
        self.hx("req", "add", "보고서", "--kind", "should")
        self.hx("ask", "음수 허용?", "--assume", "허용")
        self.hx("decide", "add", "방식", "--option", "A: 내장 연산", "--option", "B: 직접 구현", "--recommend", "A")
        self.hx("decide", "set", "D1", "--choice", "A", "--note", "A")
        self.write("calc.py", CALC + 'API_KEY = "sk-abcdefghijklmnopqrstuvwxyz123456"\nDATA = "C:\\\\Users\\\\me\\\\data.csv"\n')
        self.write("test_calc.py", TEST)
        self.write("page.html", '<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>\n')
        self.hx("run", "--name", "unit", "--req", "R1", "--done", "--metric", r"n=Ran (\d+) test", "--", "python", "-m", "unittest", "test_calc")
        out = self.hx("ship", expect=1)
        for expected in ("BLOCK calc.py:3: looks like a API key (sk-...)", "machine-specific absolute path in 1 place(s), e.g. calc.py:4",
                         "external hosts (cdn.jsdelivr.net at page.html:1)", "README shows no command to run the result",
                         "file(s) are not committed", "SHIP: NOT READY  blocking=1"):
            self.assertIn(expected, out)
        self.write("calc.py", CALC)
        self.write("page.html", "<p>offline</p>\n")
        self.write("README.md", "# 덧셈기\n\n```\npython -m unittest test_calc\n```\n")
        self.hx("regress")
        self.hx("snap", "제출 상태")
        out = self.hx("ship")
        self.assertIn("SHIP: READY  blocking=0", out)
        report = (self.dir / "collab" / "REPORT.md").read_text(encoding="utf-8")
        for expected in ("판정: **제출 가능**", "| R1 | MUST | 덧셈 | add(2,3)=5 | done | PASS | unit: `python -m unittest test_calc` | .hx/logs/",
                         "| R2 | SHOULD | 보고서 | - | todo | NONE |", "- D1 [사용자] 방식 → A (검토한 대안: A: 내장 연산 / B: 직접 구현)",
                         "- Q1 음수 허용? → 답변 없음, **가정**: 허용", "- unit.n: 처음 1 → 최종 1", "[hx-ok 1] 제출 상태",
                         "## 다시 검증하는 방법", "- unit: `python -m unittest test_calc`"):
            self.assertIn(expected, report)


if __name__ == "__main__":
    unittest.main()
