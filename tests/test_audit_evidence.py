"""Independent regressions for evidence integrity and collaboration failure modes."""

import contextlib
import io
import json
import os
import subprocess
import sys
import threading
import time
import unittest

from support import REPO, TempCase
from hx import collab, ledger, util, project, snap


class EvidenceAudit(TempCase):
    def test_brief_does_not_imply_approval_for_an_unanswered_question(self):
        ledger.add_question(self.dir, "Which priority is urgent?", to="dm")
        ledger.add_decision(self.dir, "Approach", ["A: baseline", "B: solver"])
        text, _, questions = ledger.brief(self.dir)
        self.assertEqual(questions, 1)
        self.assertNotIn("답이 없으면 가정대로 진행", text)
        self.assertIn("중요한 답이 없으면 대기", text)
        self.assertNotIn("질문은 가정 유지", text)
        self.assertIn("미답변 질문은 답변 대기", text)

    def run_check(self, name="unit", command=None, **kwargs):
        command = command or [sys.executable, "-m", "unittest", "test_value"]
        with contextlib.redirect_stdout(io.StringIO()):
            return ledger.run_check(self.dir, name, command, cwd=self.dir, tail=0, **kwargs)

    def prepare(self):
        ledger.add_req(self.dir, "MUST", "Read the configured input value")
        self.write("value.py", "VALUE = 1\n")
        self.write("input.csv", "id,value\n1,10\n")
        self.write("rules.json", '{"allowed": true}\n')
        self.write("test_value.py", "import unittest, value\nclass T(unittest.TestCase):\n"
                   "    def test_value(self): self.assertEqual(value.VALUE, 1)\n")
        self.run_check(reqs=["R1"])
        ledger.set_req(self.dir, "R1", status="done")
        self.assertEqual(ledger.gate_eval(self.dir)[0], [])

    def test_parallel_runs_keep_all_ids_logs_and_check_definitions(self):
        program = ("import sys; from pathlib import Path; from hx import ledger; "
                   "ledger.run_check(Path(sys.argv[1]),sys.argv[2],"
                   "[sys.executable,'-c','import time; time.sleep(.3); print(42)'],"
                   "cwd=Path(sys.argv[1]),tail=0)")
        procs = [subprocess.Popen([sys.executable, "-c", program, str(self.dir), name],
                                 cwd=REPO, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                 for name in ("alpha", "alpha", "beta", "beta")]
        for proc in procs:
            out, err = proc.communicate(timeout=30)
            self.assertEqual(proc.returncode, 0, (out, err))
        records = ledger.load_evidence(self.dir)
        self.assertEqual(len(records), 4)
        self.assertEqual(len({record["id"] for record in records}), 4)
        self.assertEqual(len({record["log"] for record in records}), 4)
        self.assertEqual(set(ledger.load_checks(self.dir)), {"alpha", "beta"})
        for record in records:
            self.assertIn("42\n", (self.dir / record["log"]).read_text(encoding="utf-8"))

    def test_all_skipped_tests_cannot_prove_a_requirement(self):
        ledger.add_req(self.dir, "MUST", "Run a substantive test")
        self.write("test_value.py", "import unittest\nclass T(unittest.TestCase):\n"
                   "    @unittest.skip('device unavailable')\n"
                   "    def test_value(self): self.fail()\n")
        result = self.run_check(reqs=["R1"])
        self.assertFalse(result["ok"])
        self.assertIn("all_skipped", result["flags"])
        ledger.set_req(self.dir, "R1", status="done")
        self.assertTrue(ledger.gate_eval(self.dir)[0])

    def test_zero_discovered_tests_still_fail(self):
        result = self.run_check(command=[sys.executable, "-m", "unittest", "discover", "-p", "missing_*.py"])
        self.assertFalse(result["ok"])
        self.assertIn("zero_tests", result["flags"])

    def test_deleted_source_invalidates_a_passing_check(self):
        self.prepare()
        (self.dir / "value.py").unlink()
        self.assertEqual(ledger.compute(self.dir)["states"]["unit"], "STALE")
        self.assertTrue(ledger.gate_eval(self.dir)[0])

    def test_data_and_rules_changes_invalidate_even_with_preserved_mtime(self):
        self.prepare()
        for name, replacement in (("input.csv", "id,value\n1,99\n"),
                                  ("rules.json", '{"allowed":false}\n')):
            with self.subTest(name=name):
                path = self.dir / name
                original, stat = path.read_bytes(), path.stat()
                path.write_text(replacement, encoding="utf-8")
                os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
                self.assertEqual(ledger.compute(self.dir)["states"]["unit"], "STALE")
                path.write_bytes(original)
                os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
                self.assertEqual(ledger.compute(self.dir)["states"]["unit"], "PASS")

    def test_scoped_fingerprint_ignores_unrelated_files(self):
        self.prepare()
        self.run_check(watch=["value.py", "test_value.py"])
        self.write("input.csv", "unrelated scoped dependency\n")
        self.assertEqual(ledger.compute(self.dir)["states"]["unit"], "PASS")
        (self.dir / "value.py").unlink()
        self.assertEqual(ledger.compute(self.dir)["states"]["unit"], "STALE")

    def test_legacy_evidence_remains_readable(self):
        self.prepare()
        records = ledger.load_evidence(self.dir)
        records[0].pop("fingerprint")
        util.write_text(self.dir / ".hx" / "evidence.jsonl", json.dumps(records[0]) + "\n")
        self.assertEqual(ledger.compute(self.dir)["states"]["unit"], "PASS")

    def test_blank_or_unlisted_choices_are_rejected_and_prompt_is_not_approval(self):
        decision = ledger.add_decision(self.dir, "Choose approach", ["A: baseline", "B: optimizer"])
        for choice in ("", " ", "C", "unrecorded approach"):
            with self.subTest(choice=choice), self.assertRaises(ValueError):
                ledger.decide(self.dir, decision["id"], choice)
        util.write_text(util.state_dir(self.dir, "run") / "last_user_prompt", repr(time.time()))
        item = ledger.decide(self.dir, decision["id"], "A", "A로 해")
        self.assertTrue(item["prompt_observed"])
        self.assertFalse(item["confirmed"])

    def test_handled_high_review_requires_independent_close(self):
        self.prepare()
        item = collab.review_add(self.dir, "Core result needs verification", severity="high")
        collab.review_set(self.dir, item["id"], "handled", "Main reports a fix")
        self.assertTrue(any("independent verification" in block for block in ledger.gate_eval(self.dir)[0]))
        collab.review_set(self.dir, item["id"], "closed", "Mediator reran the independent check")
        self.assertEqual(ledger.gate_eval(self.dir)[0], [])

    def test_lock_excludes_other_threads_and_allows_same_thread_nesting(self):
        held, attempt, entered = threading.Event(), threading.Event(), threading.Event()

        def worker():
            held.wait(5)
            attempt.set()
            with util.lock(self.dir):
                entered.set()

        thread = threading.Thread(target=worker)
        thread.start()
        with util.lock(self.dir):
            with util.lock(self.dir):
                held.set()
                self.assertTrue(attempt.wait(5))
                self.assertFalse(entered.wait(.2))
        thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertTrue(entered.is_set())

    def test_read_only_audit_and_status_do_not_create_state(self):
        self.write("README.md", "Existing task\n")
        before = sorted(path.relative_to(self.dir).as_posix() for path in self.dir.rglob("*"))
        with contextlib.redirect_stdout(io.StringIO()):
            collab.audit(self.dir)
            ledger.render_status(self.dir)
        after = sorted(path.relative_to(self.dir).as_posix() for path in self.dir.rglob("*"))
        self.assertEqual(before, after)

    def test_dependency_changes_during_a_run_are_not_certified(self):
        self.write("value.py", "VALUE = 1\n")
        result = self.run_check(command=[sys.executable, "-c",
            "from pathlib import Path; Path('value.py').write_text('VALUE = 2\\n'); print('ok')"])
        self.assertFalse(result["ok"])
        self.assertIn("source_changed_during_run", result["flags"])

    def test_unanswered_question_without_an_assumption_blocks_completion(self):
        self.prepare()
        ledger.add_question(self.dir, "What is the objective?", to="dm")
        self.assertTrue(any("Q1 unanswered" in block for block in ledger.gate_eval(self.dir)[0]))

    def test_review_cannot_skip_the_handled_state(self):
        item = collab.review_add(self.dir, "Reproduce the defect", severity="high")
        with self.assertRaises(ValueError):
            collab.review_set(self.dir, item["id"], "closed")

    def test_checkpoint_without_tests_is_wip_only(self):
        project.init(self.dir, with_git=True)
        with self.assertRaises(snap.SnapError):
            snap.snap(self.dir, "Unverified")
        snap.snap(self.dir, "Initial analysis", wip=True)
        self.assertEqual(snap.tags(self.dir), [])

    def test_automatic_checkpoint_preserves_existing_index(self):
        project.init(self.dir, with_git=True)
        self.write("other.txt", "User's staged work\n")
        snap.git(self.dir, "add", "--", "other.txt")
        before = snap.git(self.dir, "diff", "--cached", "--binary").stdout
        self.write("mine.txt", "Current work\n")
        head = snap.git(self.dir, "rev-parse", "HEAD").stdout
        with self.assertRaises(snap.SnapError):
            snap.snap(self.dir, "Must refuse", wip=True)
        self.assertEqual(snap.git(self.dir, "diff", "--cached", "--binary").stdout, before)
        self.assertEqual(snap.git(self.dir, "rev-parse", "HEAD").stdout, head)


if __name__ == "__main__":
    unittest.main()
