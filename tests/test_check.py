import json
import subprocess
import sys
import unittest

from support import REPO, TempCase, hx

from hx import check, profile
from hx.tableio import load_table


class Rules(TempCase):
    def setUp(self):
        super().setUp()
        self.write("lots.csv", "lot_id,qty,status,due\nL1,25,WAIT,2026-11-05\nL2,24,RUN,2026-11-06\nL3,,HOLD,2026-11-07\n"
                               "L3,30,hold,2026-11-08\nL5,abc,DONE,2026-11-09\n")
        self.write("eqp.csv", "eqp_id\nE1\nE2\n")
        self.write("plan.csv", "lot_id,eqp_id,start,end,qty_in,qty_out\n"
                               "L1,E1,2026-11-01 08:00,2026-11-01 09:00,25,25\n"
                               "L2,E1,2026-11-01 08:30,2026-11-01 09:30,24,26\n"
                               "L3,e2,2026-11-01 10:00,2026-11-01 09:00,25,\n"
                               "L9,E3,2026-11-01 11:00,2026-11-01 12:00,25,20\n")
        self.tables = {"tables": {"lots": "lots.csv", "eqp": "eqp.csv", "plan": "plan.csv"}}

    def run_rule(self, **rule):
        results, failed = check.run_rules({**self.tables, "rules": [rule]}, self.dir)
        return results[0], failed

    def assert_rule(self, status, violations, contains, **rule):
        result, failed = self.run_rule(**rule)
        self.assertEqual((result["status"], result["violations"]), (status, violations), result)
        self.assertEqual(failed, status in ("FAIL", "ERROR"))
        for text in contains:
            self.assertIn(text, " | ".join(result["examples"]))

    def test_column_level_rules(self):
        self.assert_rule("PASS", 0, [], rule="required_columns", table="lots", columns=["lot_id", "qty"])
        self.assert_rule("FAIL", 1, ["missing column 'priority'"], rule="required_columns", table="lots", columns=["lot_id", "priority"])
        self.assert_rule("FAIL", 1, ["line 4: qty is missing"], rule="not_null", table="lots", columns=["lot_id", "qty"])
        self.assert_rule("FAIL", 1, ["line 5: ('L3',) duplicates line 4"], rule="unique", table="lots", columns=["lot_id"])
        self.assert_rule("FAIL", 1, ["qty='abc' is not int"], rule="type", table="lots", column="qty", type="int")
        self.assert_rule("PASS", 0, [], rule="type", table="lots", column="due", type="datetime")
        self.assert_rule("FAIL", 2, ["qty='30' outside [1, 25]", "not comparable"], rule="range", table="lots", column="qty", min=1, max=25)
        self.assert_rule("FAIL", 1, ["due='2026-11-09'"], rule="range", table="lots", column="due", max="2026-11-08")
        self.assert_rule("FAIL", 1, ["status='hold' ×1"], rule="enum", table="lots", column="status", values=["WAIT", "RUN", "HOLD", "DONE"])
        self.assert_rule("PASS", 0, [], rule="regex", table="lots", column="lot_id", pattern=r"L\d")
        self.assert_rule("FAIL", 5, [], rule="regex", table="lots", column="lot_id", pattern=r"LOT\d+")

    def test_cross_table_rules(self):
        self.assert_rule("FAIL", 2, ["1 of these would match ignoring upper/lower case", "('E3',) not found in eqp"],
                         rule="fk", table="plan", columns=["eqp_id"], ref_table="eqp")
        self.assert_rule("FAIL", 2, ["('L9',) is in plan but not in lots", "('L5',) is in lots but missing from plan"],
                         rule="same_keys", table="plan", columns=["lot_id"], ref_table="lots")
        self.assert_rule("FAIL", 1, ["plan has 4 rows but lots has 5"], rule="row_count", table="plan", equals_table="lots")
        self.assert_rule("PASS", 0, [], rule="row_count", table="plan", min=4, max=4)
        self.assert_rule("ERROR", 1, ["non-numeric 'abc'"], rule="conserve", table="plan", column="qty_in",
                         ref_table="lots", ref_column="qty")

    def test_conservation_with_tolerance(self):
        self.write("a.csv", "q\n10\n15.5\n")
        self.write("b.csv", "q\n25.4\n")
        tables = {"tables": {"a": "a.csv", "b": "b.csv"}}
        strict, _ = check.run_rules({**tables, "rules": [{"rule": "conserve", "table": "a", "column": "q", "ref_table": "b"}]}, self.dir)
        loose, _ = check.run_rules({**tables, "rules": [{"rule": "conserve", "table": "a", "column": "q", "ref_table": "b", "tol": 0.2}]}, self.dir)
        self.assertEqual((strict[0]["status"], loose[0]["status"]), ("FAIL", "PASS"))
        self.assertIn("sum(a.q)=25.5 but sum(b.q)=25.4", strict[0]["examples"][0])

    def test_schedule_rules(self):
        self.assert_rule("FAIL", 1, ["line 4:", "out of order"], rule="order", table="plan", columns=["start", "end"])
        self.assert_rule("FAIL", 2, ["line 4: end is before start", "line 3 overlaps line 2 in group {'eqp_id': 'E1'}"],
                         rule="no_overlap", table="plan", group=["eqp_id"], start="start", end="end")
        self.write("touch.csv", "m,s,e\nA,0,10\nA,10,20\nB,5,15\nA,20,20\n")
        result, failed = check.run_rules({"tables": {"t": "touch.csv"}, "rules": [
            {"rule": "no_overlap", "table": "t", "group": ["m"], "start": "s", "end": "e"},
            {"rule": "order", "table": "t", "columns": ["s", "e"], "strict": True}]}, self.dir)
        self.assertEqual([r["status"] for r in result], ["PASS", "FAIL"])  # touching intervals are fine; zero length is not strict
        self.write("log.csv", "eqp,ts\nA,2026-11-01 08:00\nB,2026-11-01 07:00\nA,2026-11-01 08:05\nA,2026-11-01 08:04\nB,2026-11-01 07:00\n")
        loose, _ = check.run_rules({"tables": {"log": "log.csv"}, "rules": [{"rule": "monotonic", "table": "log", "group": ["eqp"], "column": "ts"}]}, self.dir)
        strict, _ = check.run_rules({"tables": {"log": "log.csv"}, "rules": [{"rule": "monotonic", "table": "log", "group": ["eqp"], "column": "ts", "strict": True}]}, self.dir)
        self.assertEqual((loose[0]["violations"], strict[0]["violations"]), (1, 2))
        self.assertIn("line 5: ts='2026-11-01 08:04' goes backwards after line 4", loose[0]["examples"][0])

    def test_row_expression(self):
        self.assert_rule("FAIL", 2, ["line 3: false for {qty_in=24, qty_out=26}", "line 4: cannot evaluate (TypeError"],
                         rule="expr", table="plan", expr="qty_out <= qty_in")
        self.assert_rule("PASS", 0, [], rule="expr", table="plan", expr="row['lot_id'].startswith('L') and len(eqp_id) == 2")
        self.assert_rule("FAIL", 1, ["line 4"], rule="expr", table="plan", expr="dt(end) > dt(start)")
        self.assert_rule("ERROR", 1, ["may not contain"], rule="expr", table="plan", expr="__import__('os')")
        self.assert_rule("ERROR", 1, ["name 'nope' is not defined", "columns="], rule="expr", table="plan", expr="nope > 1")
        self.assert_rule("ERROR", 1, ["bad expression"], rule="expr", table="plan", expr="qty_in >")

    def test_lookup_into_another_table_and_union_of_outputs(self):
        self.write("jobs.csv", "lot_id,proc_min,eligible\nL1,30,E1|E2\nL2,45,E2\nL3,20,E1\nL4,10,E1\n")
        self.write("out.csv", "lot_id,eqp_id,start_min,end_min\nL1,E1,0,30\nL2,E1,30,70\nL7,E1,70,80\n")
        self.write("rejected.csv", "lot_id,reason\nL3,no data\nL1,twice\n")
        config = {"tables": {"jobs": "jobs.csv", "out": "out.csv", "all": ["out.csv", "rejected.csv"]}, "rules": [
            {"rule": "expr", "table": "out", "expr": "end_min - start_min == ref('jobs', 'lot_id', lot_id, 'proc_min')"},
            {"rule": "expr", "table": "out", "expr": "eqp_id in (ref('jobs', 'lot_id', lot_id, 'eligible') or '').split('|')"},
            {"rule": "same_keys", "table": "all", "columns": ["lot_id"], "ref_table": "jobs"},
            {"rule": "expr", "table": "out", "expr": "ref('nope', 'lot_id', lot_id, 'proc_min')"}]}
        results, failed = check.run_rules(config, self.dir)
        self.assertTrue(failed)
        self.assertEqual([(r["status"], r["violations"]) for r in results], [("FAIL", 2), ("FAIL", 2), ("FAIL", 3), ("ERROR", 1)])
        self.assertIn("line 3: false for {lot_id='L2', start_min=30, end_min=70}", results[0]["examples"][0])
        self.assertIn("line 4", results[0]["examples"][1])                 # unknown lot: lookup gives None
        joined = " | ".join(results[2]["examples"])
        for expected in ("('L1',) appears 2 times in all", "('L7',) is in all but not in jobs", "('L4',) is in jobs but missing from all"):
            self.assertIn(expected, joined)
        self.assertIn("ref(): unknown table 'nope'", results[3]["examples"][0])

    def test_misconfiguration_never_passes(self):
        self.assert_rule("ERROR", 1, ["unknown rule 'uniq'"], rule="uniq", table="lots")
        self.assert_rule("ERROR", 1, ["unknown table 'lot'"], rule="unique", table="lot", columns=["lot_id"])
        self.assert_rule("ERROR", 1, ["no column 'lotid'"], rule="unique", table="lots", columns=["lotid"])
        self.assert_rule("ERROR", 1, ["missing option 'columns'"], rule="unique", table="lots")
        self.assert_rule("ERROR", 1, ["range needs min and/or max"], rule="range", table="lots", column="qty")
        results, failed = check.run_rules({"tables": {"x": "nope.csv"}, "rules": []}, self.dir)
        self.assertTrue(failed)
        self.assertIn("file not found", results[0]["examples"][0])

    def test_warn_level_reports_without_failing(self):
        result, failed = self.run_rule(rule="enum", table="lots", column="status", values=["WAIT"], level="warn")
        self.assertEqual((result["status"], failed), ("WARN", False))


class DraftAndCli(TempCase):
    def test_draft_describes_the_data_and_passes_on_it(self):
        rows = "\n".join(f"LOT{n:03d},{20 + n % 6},{'RUN' if n % 2 else 'WAIT'},E{1 + n % 2}" for n in range(30))
        self.write("lots.csv", f"lot_id,qty,status,eqp_id\n{rows}\n")
        self.write("eqp.csv", "eqp_id,area\nE1,A\nE2,B\nE3,B\n")
        code, out = hx("check", "--draft", "lots.csv", "eqp.csv", "-o", "rules.json", cwd=self.dir)
        self.assertEqual(code, 0, out)
        spec = json.loads((self.dir / "rules.json").read_text(encoding="utf-8"))
        kinds = [(rule["rule"], rule["table"], rule.get("column") or tuple(rule.get("columns", []))) for rule in spec["rules"]]
        for expected in (("unique", "lots", ("lot_id",)), ("type", "lots", "qty"), ("range", "lots", "qty"),
                         ("enum", "lots", "status"), ("fk", "lots", ("eqp_id",))):
            self.assertIn(expected, kinds)
        self.assertEqual(hx("check", "rules.json", cwd=self.dir)[0], 0)
        code, out = hx("check", "--draft", "lots.csv", "-o", "rules.json", cwd=self.dir)
        self.assertEqual(code, 2)
        self.assertIn("exists", out)
        # The same rules now catch a later bad delivery of the file.
        self.write("lots.csv", f"lot_id,qty,status,eqp_id\n{rows}\nLOT001,99,BROKEN,E9\n")
        code, out = hx("check", "rules.json", cwd=self.dir)
        self.assertEqual(code, 1)
        for expected in ("[FAIL] unique lots", "[FAIL] fk lots", "[WARN] range lots qty", "[WARN] enum lots status", "CHECK: FAIL"):
            self.assertIn(expected, out)

    def test_sample_schedules_and_bad_rules_file(self):
        data = self.dir / "data"
        subprocess.run([sys.executable, str(REPO / "samples" / "make_samples.py"), str(data)], check=True, capture_output=True)
        self.assertEqual(hx("check", data / "rules_ok.json", cwd=self.dir)[0], 0)   # paths relative to the rules file
        code, out = hx("check", data / "rules_bad.json", cwd=self.dir)
        self.assertEqual(code, 1)
        for expected in ("('LOT0003',) appears 2 times", "('LOT0005',) is in lots but missing", "overlaps line 2 in group {'eqp_id': 'CVD01'}"):
            self.assertIn(expected, out)
        self.write("broken.json", "{not json")
        self.write("shape.json", "[1, 2]")
        for name, expected in (("broken.json", "invalid JSON"), ("shape.json", "expected"), ("absent.json", "not found")):
            code, out = hx("check", name, cwd=self.dir)
            self.assertEqual(code, 2, out)
            self.assertIn(expected, out)


if __name__ == "__main__":
    unittest.main()
