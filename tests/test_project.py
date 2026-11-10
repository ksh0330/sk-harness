"""init, the web scaffold, the smoke runner, checkpoints, and both ways of launching the kit."""

import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from support import KIT, REPO, TempCase, hx


def free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


class Base(TempCase):
    def hx(self, *args, expect=0):
        code, out = hx(*args, cwd=self.dir)
        if expect is not None:
            self.assertEqual(code, expect, out)
        return out


class Init(Base):
    def test_init_deploys_codex_files_and_never_overwrites_user_files(self):
        self.write("AGENTS.md", "기존 과제 지침\n")
        out = self.hx("init", "--deadline", "16:00")
        self.assertIn("kept existing AGENTS.md (differs, not modified)", out)
        self.assertIn(".agents/skills/hx-main/SKILL.md 를 읽고", out)       # how to start when the task owns AGENTS.md
        self.assertEqual((self.dir / "AGENTS.md").read_text(encoding="utf-8"), "기존 과제 지침\n")
        self.assertFalse((self.dir / "CLAUDE.md").exists())               # Codex only: nothing Claude-specific
        self.assertFalse((self.dir / ".codex").exists())                  # hooks are opt-in
        for name in ("hx-main", "hx-design", "hx-mediator", "hx-ship"):
            skill = (self.dir / ".agents" / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
            self.assertTrue(skill.startswith(f"---\nname: {name}\ndescription: "), name)
            self.assertNotIn("{HX}", skill)
        guide = (self.dir / ".hx" / "GUIDE.md").read_text(encoding="utf-8")
        self.assertNotIn("{HX}", guide)
        self.assertIn(KIT.as_posix(), guide)
        self.assertNotIn('--watch "src/*,data/*', guide)                   # broad patterns also watch outputs
        self.assertIn("임의로 채우지 않고 사용자에게", guide)
        main = (self.dir / ".agents" / "skills" / "hx-main" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("Never include files the command writes", main)
        self.assertIn("## Personal and submission information", main)
        self.assertTrue((self.dir / ".hx" / "DOMAIN.md").is_file())
        self.assertIn("# 작업 보드", (self.dir / "collab" / "BOARD.md").read_text(encoding="utf-8"))
        self.assertTrue((self.dir / "collab" / "INBOX.md").is_file())
        learning = self.dir / "collab" / "LEARNING.md"
        self.assertIn("# 구현 이해와 학습 기록", learning.read_text(encoding="utf-8"))
        learning.write_text("내가 이해한 실제 구현과 근거\n", encoding="utf-8")
        config = json.loads((self.dir / ".hx" / "config.json").read_text(encoding="utf-8"))
        self.assertEqual((config["deadline"], config["phase"]), ("16:00", "analyze"))
        (self.dir / ".agents" / "skills" / "hx-ship" / "SKILL.md").write_text("내가 고친 스킬", encoding="utf-8")
        out = self.hx("init", "--hooks")                                  # idempotent, keeps the deadline and edits
        self.assertNotIn("created .agents", out)
        self.assertIn("kept existing .agents/skills/hx-ship/SKILL.md", out)
        self.assertIn("kept existing collab/LEARNING.md", out)
        self.assertEqual(learning.read_text(encoding="utf-8"), "내가 이해한 실제 구현과 근거\n")
        self.assertEqual(json.loads((self.dir / ".hx" / "config.json").read_text(encoding="utf-8"))["deadline"], "16:00")
        hooks = json.loads((self.dir / ".codex" / "hooks.json").read_text(encoding="utf-8"))["hooks"]
        self.assertEqual(sorted(hooks), ["PostToolUse", "PreToolUse", "SessionStart", "Stop", "UserPromptSubmit"])
        self.assertIn(KIT.as_posix() + '" hook stop', hooks["Stop"][0]["hooks"][0]["command"])
        self.assertIn("/hooks", out)
        self.assertIn("deadline must look like", self.hx("init", "--deadline", "4pm", expect=2))
        self.assertFalse((self.dir / ".git").exists())                    # no git without --git

    def test_init_path_and_file_conflicts_preserve_supplied_material(self):
        original = {"TASK.md": "제공 과제\n", "data/input.csv": "id,value\n1,10\n",
                    "AGENTS.md": "기존 지침\n", "collab/LEARNING.md": "기존 학습 기록\n"}
        for name, content in original.items():
            self.write(name, content)
        before = {name: (self.dir / name).read_bytes() for name in original}
        self.write(".hx", "reserved task file\n")
        self.hx("init", expect=2)
        self.assertEqual((self.dir / ".hx").read_bytes(), b"reserved task file\n")
        self.hx("--root", self.dir / "TASK.md", "init", expect=2)
        for name, content in before.items():
            self.assertEqual((self.dir / name).read_bytes(), content, name)
        self.assertFalse((self.dir / ".agents").exists())

    def test_fresh_folder_gets_agents_file_and_root_is_found_from_subfolders(self):
        self.hx("init")
        agents = (self.dir / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn(".agents/skills/hx-main/SKILL.md", agents)
        self.assertIn("hx-mediator", agents)
        self.assertIn(KIT.as_posix(), agents)
        (self.dir / "deep" / "er").mkdir(parents=True)
        code, out = hx("req", "add", "x", cwd=self.dir / "deep" / "er")
        self.assertEqual(code, 0, out)
        self.assertTrue((self.dir / ".hx" / "reqs.json").is_file())
        self.assertFalse((self.dir / "deep" / "er" / ".hx").exists())

    def test_both_launch_forms_and_doctor(self):
        env = dict(os.environ, PYTHONPATH=str(REPO), PYTHONDONTWRITEBYTECODE="1")
        as_module = subprocess.run([sys.executable, "-m", "hx", "--version"], cwd=self.dir, env=env, capture_output=True, text=True)
        self.assertEqual((as_module.returncode, as_module.stdout.strip()), (0, "hx 1.0"))
        self.assertEqual(self.hx("--version").strip(), "hx 1.0")
        out = self.hx("doctor")
        for expected in ("python   3.", "tools", "python modules", "loopback can bind 127.0.0.1", "network  not probed", "DOCTOR: OK"):
            self.assertIn(expected, out)
        self.assertFalse((self.dir / ".hx").exists())                     # looking around creates nothing


class AppAndSmoke(Base):
    def setUp(self):
        super().setUp()
        self.port = free_port()
        self.hx("new", "app", "--dir", "board", "--port", self.port)

    def spec(self, **changes):
        spec = json.loads((self.dir / "smoke_board.json").read_text(encoding="utf-8"))
        spec.update(changes)
        (self.dir / "smoke.json").write_text(json.dumps(spec), encoding="utf-8")

    def test_scaffold_passes_its_own_tests_and_smoke_and_frees_the_port(self):
        self.assertIn("refusing to overwrite", self.hx("new", "app", "--dir", "board", expect=2))
        self.assertIn("simple identifier", self.hx("new", "app", "--dir", "../x", expect=2))
        self.hx("init")
        out = self.hx("run", "--name", "board-unit", "--", "python", "-m", "unittest", "tests.test_board")
        self.assertIn("Ran 5 tests", out)
        out = self.hx("smoke", "smoke_board.json")
        self.assertIn("SMOKE: PASS  passed=5 failed=0 (server stopped)", out)
        with self.assertRaises(OSError):                                  # the server really is gone
            socket.create_connection(("127.0.0.1", self.port), timeout=3).close()
        page = (self.dir / "board" / "static" / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("http://", page.replace("http://www.w3.org", ""))  # no CDN or external asset
        self.assertNotIn("https://", page)

    def test_failed_expectations_are_listed(self):
        self.spec(checks=[{"path": "/api/items", "status": 200, "json_len_min": {"items": 5}, "json_equals": {"count": 99}},
                          {"path": "/api/nope", "status": 200},
                          {"path": "/", "contains": "<title>", "not_contains": "<html", "json_has": ["x"]},
                          {"path": "/api/health", "json_has": ["ok", "missing.key"]}])
        out = self.hx("smoke", "smoke.json", expect=1)
        for expected in ("JSON 'items' has length 1, need >= 5", "JSON 'count' is 1, expected 99", "status 404, expected 200",
                         "body contains forbidden '<html'", "body is not JSON", "JSON has no 'missing.key'",
                         "SMOKE: FAIL  passed=0 failed=4 (server stopped)"):
            self.assertIn(expected, out)

    def test_server_that_dies_is_reported_with_its_log(self):
        self.spec(serve=["python", "-c", "raise SystemExit('boom: config missing')"], timeout=10)
        out = self.hx("smoke", "smoke.json", expect=1)
        self.assertIn("SMOKE: FAIL  server exited with code 1", out)
        self.assertIn("boom: config missing", out)

    def test_port_already_in_use_is_not_mistaken_for_the_new_server(self):
        class Old(BaseHTTPRequestHandler):
            def do_GET(self):
                body = b'{"ok": true}'
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        old = HTTPServer(("127.0.0.1", self.port), Old)
        thread = threading.Thread(target=old.serve_forever, daemon=True)
        thread.start()
        try:
            out = self.hx("smoke", "smoke_board.json", expect=1)
            self.assertIn("already answers BEFORE the server was started", out)
        finally:
            old.shutdown()
            old.server_close()
        self.write("empty.json", "{}")
        self.assertIn('spec needs "base"', self.hx("smoke", "empty.json", expect=1))


@unittest.skipUnless(shutil.which("git"), "git is required for checkpoints")
class Checkpoints(Base):
    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.dir), *args], capture_output=True, text=True, encoding="utf-8").stdout.strip()

    def setUp(self):
        super().setUp()
        self.write("README.md", "# 과제\n")
        out = self.hx("init", "--git")
        self.assertIn("baseline commit", out)
        self.assertEqual(self.git("tag", "--list"), "hx-base")
        self.assertIn("README.md", self.git("show", "--name-only", "--format=", "hx-base"))   # the task as received is preserved
        self.write("calc.py", "def add(a, b):\n    return a + b\n")
        self.write("test_calc.py", "import unittest, calc\n\nclass T(unittest.TestCase):\n    def test_add(self):\n        self.assertEqual(calc.add(2, 3), 5)\n")
        self.hx("req", "add", "덧셈")
        self.hx("run", "--name", "unit", "--req", "R1", "--done", "--", "python", "-m", "unittest", "test_calc")

    def test_snap_tags_a_verified_state_and_back_restores_it_without_losing_work(self):
        out = self.hx("snap", "덧셈 MVP")
        self.assertIn("SNAP: hx-ok-1 at", out)
        self.assertIn("calc.py", out)                                     # says exactly what was committed
        self.assertEqual(self.git("tag", "--list", "hx-ok-*"), "hx-ok-1")
        self.assertEqual(self.git("status", "--porcelain", "--", "calc.py", "test_calc.py"), "")
        self.assertEqual(self.git("log", "-1", "--format=%s"), "[hx-ok 1] 덧셈 MVP (analyze, MUST 1/1)")
        self.assertIn("[hx-ok 1] 덧셈 MVP", self.hx("status"))
        self.write("calc.py", "def add(a, b):\n    return a * b  # broken experiment\n")
        self.write("experiment.py", "x = 1\n")
        self.hx("regress", expect=1)
        self.assertIn("not a verified state: failing=['unit']", self.hx("snap", "should refuse", expect=2))
        self.assertIn("SNAP: wip commit", self.hx("snap", "--wip", "실험 중"))
        self.assertEqual(self.git("tag", "--list", "hx-ok-*"), "hx-ok-1")  # wip gets no ok-tag
        self.write("calc.py", "def add(a, b):\n    return None  # worse\n")
        plan = self.hx("back", expect=2)
        self.assertIn("dry run only", plan)
        self.assertRegex(plan, r"1 later commit\(s\) and \d+ uncommitted change\(s\)")
        self.assertIn("return None", (self.dir / "calc.py").read_text(encoding="utf-8"))   # dry run changed nothing
        done = self.hx("back", "--yes")
        self.assertIn("BACK done", done)
        self.assertEqual((self.dir / "calc.py").read_text(encoding="utf-8"), "def add(a, b):\n    return a + b\n")
        self.assertFalse((self.dir / "experiment.py").exists())
        branch = next(line.strip() for line in self.git("branch", "--list").splitlines() if "hx-abandoned" in line)
        self.assertIn("return None", self.git("show", f"{branch}:calc.py"))          # the abandoned work is recoverable
        self.assertIn("x = 1", self.git("show", f"{branch}:experiment.py"))
        self.assertIn("source changed after the proof", self.hx("gate", expect=1))   # must re-verify after returning
        self.hx("regress")
        self.assertIn("GATE: PASS", self.hx("gate"))
        self.assertIn("SNAP: hx-ok-2 at", self.hx("snap", "복귀 후 재검증"))
        self.assertIn("unknown checkpoint 'hx-ok-9'", self.hx("back", "--to", "hx-ok-9", expect=2))

    def test_snapshot_leaves_out_dependencies_huge_files_secrets_and_a_nested_kit(self):
        self.write("node_modules/pkg/index.js", "x")
        self.write(".env", "API_KEY=abc\n")
        with open(self.dir / "big.bin", "wb") as handle:
            handle.truncate(26 * 1024 * 1024)
        before = self.git("config", "--local", "--list")
        out = self.hx("snap", "초기")
        self.assertIn("1 file(s) over 25 MB left out of the snapshot: ['big.bin']", out)
        tracked = self.git("ls-files")
        for absent in ("node_modules", "big.bin", ".env", ".hx/run"):
            self.assertNotIn(absent, tracked)
        self.assertIn("calc.py", tracked)
        self.assertIn(".hx/evidence.jsonl", tracked)                       # the process record is part of the snapshot
        self.assertIn("collab/BOARD.md", tracked)
        self.assertEqual(self.git("config", "--local", "--list"), before)
        self.assertEqual(self.git("remote"), "")

    def test_kit_cloned_inside_the_task_is_not_committed_into_it(self):
        clone = self.dir / "hx-kit"
        shutil.copytree(KIT, clone / "hx", ignore=shutil.ignore_patterns("__pycache__"))
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        run = subprocess.run([sys.executable, str(clone / "hx"), "snap", "--wip", "키트 포함 확인"], cwd=self.dir, env=env,
                             capture_output=True)
        self.assertEqual(run.returncode, 0, run.stdout.decode("utf-8", "replace") + run.stderr.decode("utf-8", "replace"))
        self.assertNotIn("hx-kit", self.git("ls-files"))
        self.assertIn("calc.py", self.git("ls-files"))

    def test_refuses_inside_a_parent_repo(self):
        nested = self.dir / "task"
        nested.mkdir()
        code, out = hx("init", cwd=nested)
        self.assertEqual(code, 0, out)
        code, out = hx("snap", "x", cwd=nested)
        self.assertEqual(code, 2)
        self.assertIn("sits inside another repository", out)
        code, out = hx("init", "--git", cwd=nested)
        self.assertIn("already inside a git repository", out)
        self.assertFalse((nested / ".git").exists())

    def test_existing_repository_is_tagged_not_rewritten(self):
        import tempfile
        from pathlib import Path
        other = Path(tempfile.mkdtemp(prefix="hxgiven-")).resolve()        # its own top-level repository
        self.addCleanup(shutil.rmtree, other, True)
        (other / "README.md").write_text("given task\n", encoding="utf-8")
        for args in (["init"], ["add", "-A"], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-m", "organiser commit"]):
            subprocess.run(["git", "-C", str(other), *args], capture_output=True, check=True)
        code, out = hx("init", "--git", cwd=other)
        self.assertEqual(code, 0, out)
        self.assertIn("existing repository kept as is", out)
        log = subprocess.run(["git", "-C", str(other), "log", "--format=%s"], capture_output=True, text=True).stdout.split("\n")
        self.assertEqual(log[0], "organiser commit")                       # nothing was committed on top


class NoRepo(Base):
    def test_snap_without_git_repo_explains_what_to_do(self):
        self.hx("init")
        out = self.hx("snap", "x", expect=2)
        self.assertTrue("hx init --git" in out or "inside another repository" in out, out)


if __name__ == "__main__":
    unittest.main()
