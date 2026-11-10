import json
import os
import time
import unittest

from support import TempCase, hx

PASSING = "import unittest\nimport calc\n\nclass T(unittest.TestCase):\n    def test_add(self):\n        self.assertEqual(calc.add(2, 3), 5)\n"


class Ledger(TempCase):
    def setUp(self):
        super().setUp()
        self.hx("init", "--deadline", "23:59")
        self.write("calc.py", "def add(a, b):\n    return a + b\n")
        self.write("test_calc.py", PASSING)

    def hx(self, *args, expect=0):
        code, out = hx(*args, cwd=self.dir)
        if expect is not None:
            self.assertEqual(code, expect, out)
        return out

    def evidence(self):
        with open(self.dir / ".hx" / "evidence.jsonl", encoding="utf-8") as handle:
            return [json.loads(line) for line in handle]

    def test_requirements_questions_and_bulk_import(self):
        self.assertIn("added R1 [MUST] 스케줄을 CSV로 출력", self.hx("req", "add", "스케줄을 CSV로 출력", "--accept", "out/plan.csv 존재"))
        self.assertIn("no --accept", self.hx("req", "add", "대시보드", "--kind", "could"))
        self.write("reqs.txt", "# 원문 3.1절\nMUST: 설비별 시간이 겹치지 않는다 => hx check no_overlap 위반 0\n"
                               "- SHOULD: 납기 지연 최소화\nQ: 시간 단위는 분인가? => 분으로 가정\n\n")
        out = self.hx("req", "add", "--file", "reqs.txt")
        self.assertIn("added R3 [MUST] 설비별 시간이 겹치지 않는다", out)
        self.assertIn("added Q1 [QUESTION]", out)
        self.assertIn("REQ: 3 item(s) added", out)
        self.assertIn("added Q2 (for the user)", self.hx("ask", "제출 형식?"))
        self.hx("answer", "Q1", "분 단위 맞음")
        self.hx("req", "set", "R2", "--status", "dropped", "--note", "시간 부족")
        listing = self.hx("req", "list")
        for expected in ("| R1 | MUST | todo | NONE |", "| R2 | COULD | dropped |", "hx check no_overlap 위반 0",
                         "Q1 시간 단위는 분인가? -> answer: 분 단위 맞음", "Q2 제출 형식? -> OPEN; assuming: (nothing recorded)",
                         "left until 23:59"):
            self.assertIn(expected, listing)
        self.write("bad.txt", "MUST: ok\nwhatever this is\n")
        self.assertIn("bad.txt:2", self.hx("req", "add", "--file", "bad.txt", expect=2))
        self.assertEqual(len(json.loads((self.dir / ".hx" / "reqs.json").read_text(encoding="utf-8"))["items"]), 6)  # bad file added nothing
        self.assertIn("no such id", self.hx("req", "set", "R99", "--status", "done", expect=2))
        self.assertIn("use `hx answer`", self.hx("req", "set", "Q1", "--status", "done", expect=2))

    def test_passing_run_is_recorded_with_log_and_proves_the_requirement(self):
        self.hx("req", "add", "덧셈", "--accept", "add(2,3)=5")
        out = self.hx("run", "--name", "unit", "--req", "R1", "--done", "--", "python", "-m", "unittest", "test_calc", "-v")
        self.assertRegex(out, r"HX-RUN #1 unit: PASS exit=0 dur=\d+\.\ds reqs=R1 log=\.hx/logs/001-unit\.log")
        self.assertIn("marked done: R1", out)
        record = self.evidence()[0]
        self.assertEqual((record["ok"], record["exit"], record["reqs"], record["flags"]), (True, 0, ["R1"], []))
        self.assertIn("Ran 1 test", record["summary"])
        log = (self.dir / ".hx" / "logs" / "001-unit.log").read_text(encoding="utf-8")
        self.assertIn("test_add", log)
        self.assertIn("# exit=0", log)
        self.assertIn("GATE: PASS  blocking=0", self.hx("gate"))

    def test_failure_keeps_the_exit_code_and_blocks_the_gate(self):
        self.hx("req", "add", "덧셈")
        self.write("calc.py", "def add(a, b):\n    return a - b\n")
        out = self.hx("run", "--name", "unit", "--req", "R1", "--done", "--", "python", "-m", "unittest", "test_calc", expect=1)
        self.assertIn("HX-RUN #1 unit: FAIL exit=1", out)
        self.assertIn("AssertionError: -1 != 5", out)
        self.assertNotIn("marked done", out)
        out = self.hx("gate", expect=1)
        self.assertIn("BLOCK R1 [MUST] 덧셈: status=todo", out)
        self.assertIn("BLOCK check unit is failing", out)

    def test_zero_tests_expectation_weak_and_missing_command_do_not_count(self):
        self.hx("req", "add", "A")
        out = self.hx("run", "--name", "none", "--req", "R1", "--", "python", "-m", "unittest", "discover", "-s", ".", "-p", "nomatch*.py", expect=None)
        self.assertIn("flags=zero_tests", out)
        self.assertIn("ran ZERO tests", out)
        self.assertFalse(self.evidence()[-1]["ok"])
        out = self.hx("run", "--name", "exp", "--expect", r"ALL \d+ ROWS VALID", "--", "python", "-c", "print('done')", expect=1)
        self.assertIn("flags=expect_missing", out)
        self.hx("run", "--name", "exp", "--expect", r"ALL \d+ ROWS VALID", "--", "python", "-c", "print('ALL 12 ROWS VALID')")
        out = self.hx("run", "--name", "weak", "--req", "R1", "--done", "--sh", "echo all good")
        self.assertIn("flags=weak", out)
        self.assertNotIn("marked done", out)
        out = self.hx("run", "--name", "ghost", "--", "definitely-not-a-command-xyz", expect=127)
        self.assertIn("cannot start command", out)
        self.hx("forget", "none")
        self.hx("forget", "ghost")
        self.hx("req", "set", "R1", "--status", "done")
        self.assertIn("only a trivial command was offered as proof", self.hx("gate", expect=1))

    def test_timeout_kills_the_process_tree(self):
        started = time.time()
        out = self.hx("run", "--name", "slow", "--timeout", "2", "--", "python", "-c", "import time; print('start', flush=True); time.sleep(60)", expect=124)
        self.assertLess(time.time() - started, 30)
        self.assertIn("flags=timeout", out)
        self.assertIn("start", (self.dir / ".hx" / "logs" / "001-slow.log").read_text(encoding="utf-8"))

    def test_metrics_and_korean_output_round_trip(self):
        script = "print('수율 예측 F1: 0.61'); print('F1: 0.74')"
        out = self.hx("run", "--name", "model", "--metric", r"f1=F1: ([0-9.]+)", "--metric", r"auc=AUC: ([0-9.]+)", "--", "python", "-c", script)
        self.assertIn("수율 예측 F1: 0.61", out)                       # child UTF-8 output survives the pipe
        self.assertIn("metrics={'f1': 0.74}", out)
        self.assertIn("metric_missing:auc", out)
        self.hx("run", "--name", "model", "--metric", r"f1=^F1: ([0-9.]+)$", "--", "python", "-c", "print('warmup'); print('F1: 0.80')")
        self.assertIn("model.f1: first=0.74 latest=0.8 min=0.74 max=0.8 runs=2", self.hx("status"))

    def test_stale_proof_is_detected_and_regress_restores_it(self):
        self.hx("req", "add", "덧셈")
        self.hx("run", "--name", "unit", "--req", "R1", "--done", "--", "python", "-m", "unittest", "test_calc")
        self.assertIn("GATE: PASS", self.hx("gate"))
        future = time.time() + 5
        os.utime(self.dir / "calc.py", (future, future))               # source edited after the proof
        out = self.hx("gate", expect=1)
        self.assertIn("BLOCK R1 [MUST] 덧셈: source changed after the proof (unit); re-run", out)
        self.assertIn("STALE = source changed after the proof ran (newest: calc.py)", (self.dir / ".hx" / "STATUS.md").read_text(encoding="utf-8"))
        os.utime(self.dir / "calc.py", None)
        (self.dir / "notes.md").write_text("docs do not invalidate proofs", encoding="utf-8")
        time.sleep(1.2)
        self.assertIn("REGRESS: PASS  ran=1 failed=0", self.hx("regress"))
        self.assertIn("GATE: PASS", self.hx("gate"))
        self.assertEqual(len(self.evidence()), 2)

    def test_regress_runs_from_the_original_directory_and_reports_failures(self):
        self.write("sub/test_here.py", "import os, unittest\n\nclass T(unittest.TestCase):\n    def test_cwd(self):\n"
                                       "        self.assertEqual(os.path.basename(os.getcwd()), 'sub')\n")
        code, out = hx("run", "--name", "sub", "--", "python", "-m", "unittest", "test_here", cwd=self.dir / "sub")
        self.assertEqual(code, 0, out)
        self.hx("run", "--name", "unit", "--", "python", "-m", "unittest", "test_calc")
        self.assertIn("REGRESS: PASS  ran=2 failed=0", self.hx("regress"))
        self.write("calc.py", "def add(a, b):\n    return 0\n")
        out = self.hx("regress", expect=1)
        self.assertIn("REGRESS: FAIL  ran=2 failed=1 -> unit", out)
        self.assertIn("REGRESS: PASS  ran=1 failed=0", self.hx("regress", "--only", "sub"))
        self.assertIn("no such check", self.hx("regress", "--only", "nope", expect=2))

    def test_gate_rules(self):
        self.assertIn("no MUST requirement is recorded", self.hx("gate", expect=1))
        self.hx("req", "add", "핵심")
        self.hx("req", "add", "부가", "--kind", "should")
        self.hx("req", "add", "포기한 필수")
        self.hx("req", "set", "R1", "--status", "done")
        self.hx("req", "set", "R2", "--status", "done")
        self.assertIn("needs the user's decision", self.hx("req", "set", "R3", "--status", "dropped", "--note", "데이터 미제공", expect=2))
        self.assertIn("needs the user's decision", self.hx("req", "set", "R3", "--kind", "could", expect=2))
        self.hx("decide", "add", "R3 제외", "--option", "A: 제외", "--option", "B: 축소 구현", "--recommend", "A")
        self.assertIn("needs the user's decision", self.hx("req", "set", "R3", "--status", "dropped", "--decision", "D1", expect=2))  # still pending
        self.hx("decide", "set", "D1", "--choice", "A", "--note", "빼자")
        self.hx("req", "set", "R3", "--status", "dropped", "--note", "데이터 미제공", "--decision", "D1")
        self.hx("ask", "지표는?", "--assume", "F1")
        out = self.hx("req", "set", "R1", "--status", "done")
        self.assertIn("proof is NONE", out)
        out = self.hx("gate", expect=1)
        for expected in ("BLOCK R1 [MUST] 핵심: marked done but no check is linked", "WARN  R2 [SHOULD] 부가: marked done but no check",
                         "WARN  R3 [MUST] 포기한 필수: MUST was dropped under D1 (데이터 미제공); disclose it",
                         "WARN  Q1 unanswered: 지표는? -> assuming 'F1'", "GATE: FAIL  blocking=1 warnings=3"):
            self.assertIn(expected, out)
        self.hx("run", "--name", "unit", "--req", "R1", "--", "python", "-m", "unittest", "test_calc")
        self.assertIn("GATE: PASS  blocking=0 warnings=3", self.hx("gate", "--final"))
        self.assertEqual(len(self.evidence()), 2)                        # --final re-ran the check
        self.assertIn("unknown requirement id(s) ['R9']", self.hx("run", "--name", "x", "--req", "R9", "--", "python", "-V", expect=2))
        self.assertIn("exactly one", self.hx("run", "--name", "x", expect=2))
        self.assertIn("only used by `hx run`", self.hx("gate", "--", "x", expect=2))

    def test_skipped_tests_are_surfaced(self):
        self.write("test_skip.py", "import unittest\n\nclass T(unittest.TestCase):\n    @unittest.skip('no device')\n"
                                   "    def test_a(self):\n        pass\n    def test_b(self):\n        pass\n")
        self.hx("req", "add", "A")
        out = self.hx("run", "--name", "skip", "--req", "R1", "--done", "--", "python", "-m", "unittest", "test_skip")
        self.assertIn("skipped=1", out)
        self.assertIn("WARN  check skip skipped 1 test(s)", self.hx("gate"))


if __name__ == "__main__":
    unittest.main()
