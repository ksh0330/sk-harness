import subprocess
import sys
import unittest

from support import REPO, TempCase, hx

from hx import profile
from hx.tableio import load_table


def findings(report, column=None):
    return " | ".join(message for _, name, message in report["findings"] if column is None or name == column)


class ColumnProfiling(TempCase):
    def table(self, text, name="t.csv"):
        return profile.profile_table(load_table(self.write(name, text)))

    def column(self, report, name):
        return next(c for c in report["columns"] if c["name"] == name)

    def test_types_and_missing_tokens(self):
        report = self.table("i,f,d,b,s,e,code\n1,1.5,2026-11-01,Y,abc,,007\n2,N/A,2026-11-02,N,def,,012\n3,2,2026-11-03,y,ghi,,100\n")
        self.assertEqual([c["dtype"] for c in report["columns"]], ["int", "float", "datetime", "bool", "str", "empty", "str"])
        self.assertEqual(self.column(report, "f")["missing"], 1)
        self.assertIn("'N/A'", findings(report, "f"))
        self.assertIn("entirely empty", findings(report, "e"))
        self.assertIn("zero-padded", findings(report, "code"))

    def test_text_hidden_in_a_numeric_column_is_high(self):
        rows = "\n".join(str(60 + n % 7) for n in range(40))
        report = self.table(f"temp\n{rows}\nERR\nERR\n-\n")
        column = self.column(report, "temp")
        self.assertEqual((column["dtype"], column["missing"]), ("int~", 1))
        self.assertEqual(report["findings"][0][0], "high")
        self.assertIn("2 non-numeric", findings(report, "temp"))
        self.assertIn("'ERR'×2", findings(report, "temp"))

    def test_sentinel_outlier_negative_and_thousands(self):
        rows = "\n".join(f"{65 + (n % 9) * 0.1:.1f},{20 + n % 5}" for n in range(60))
        report = self.table(f"temperature,wafer_qty\n{rows}\n-999,25\n65.2,-3\n250.0,\"1,200\"\n")
        temperature = findings(report, "temperature")
        self.assertIn("sentinel", temperature)
        self.assertIn("[-999]", temperature)
        self.assertIn("extreme outlier", temperature)
        quantity = findings(report, "wafer_qty")
        self.assertIn("negative", quantity)
        self.assertIn("thousands separators", quantity)

    def test_category_variants_whitespace_and_mixed_dates(self):
        report = self.table("status,when\nHOLD,2026-11-01\nHold,2026-11-02\n hold ,2026/11/03\nRUN,2026-11-04\nRUN_1,2026-11-05\nRUN-1,2026-11-06\n")
        status = findings(report, "status")
        self.assertIn("2 categories are written in several ways", status)
        self.assertIn("whitespace", status)
        self.assertIn("2 date formats are mixed", findings(report, "when"))

    def test_percent_scale_mix_and_future_date(self):
        rows = "\n".join(f"{90 + n % 8},2026-10-{1 + n % 28:02d}" for n in range(30)) + "\n0.91,2026-10-05\n0.88,2026-10-06\n0.93,2099-01-01\n"
        report = self.table(f"yield_pct,measured_date\n{rows}")
        self.assertIn("mix a 0–1 scale and a 0–100 scale", findings(report, "yield_pct"))
        self.assertIn("future timestamp", findings(report, "measured_date"))

    def test_duplicates_and_keys(self):
        report = self.table("lot_id,wafer_no,v\nL1,1,5\nL1,2,6\nL2,1,7\nL2,1,7\n")
        self.assertEqual(report["duplicates"], 1)
        self.assertIn("fully duplicated", findings(report))
        clean = self.table("lot_id,wafer_no,v\nL1,1,5\nL1,2,6\nL2,1,7\n", "c.csv")
        self.assertEqual(clean["keys"], [["v"]])
        composite = self.table("lot_id,wafer_no,v\nL1,1,5\nL1,2,5\nL2,1,5\nL2,2,5\n", "d.csv")
        self.assertEqual(composite["keys"], [["lot_id", "wafer_no"]])

    def test_id_with_accidental_repeat(self):
        rows = "\n".join(f"LOT{n:04d},x" for n in range(60))
        report = self.table(f"lot_id,v\n{rows}\nLOT0007,y\n")
        self.assertIn("looks like an ID but 1 value(s) repeat", findings(report, "lot_id"))

    def test_gap_inside_one_group_is_found(self):
        lines = ["eqp_id,ts,v"]
        for minute in range(0, 120, 2):
            lines.append(f"E1,2026-11-01 08:{minute % 60:02d}:00,1" if minute < 60 else f"E1,2026-11-01 09:{minute % 60:02d}:00,1")
            if not 20 <= minute < 80:
                hour, rest = divmod(minute, 60)
                lines.append(f"E2,2026-11-01 {8 + hour:02d}:{rest:02d}:00,1")
        report = self.table("\n".join(lines) + "\n")
        self.assertIn("eqp_id=E2: gap of 1:02:00", findings(report, "ts"))
        self.assertNotIn("eqp_id=E1", findings(report, "ts"))


class Relations(TempCase):
    def test_orphans_case_hint_and_duplicate_parent(self):
        parent = load_table(self.write("eqp.csv", "eqp_id,type\nETCH01,E\nETCH02,E\nCVD01,C\n"))
        child = load_table(self.write("run.csv", "run_no,eqp_id\n1,ETCH01\n2,etch02\n3,ETCH09\n4,ETCH01\n"))
        tables = [child, parent]
        found = profile.relations(tables, [profile.profile_table(t) for t in tables])
        self.assertEqual(len(found), 1)
        self.assertEqual((found[0]["child"], found[0]["parent"]), ("run.eqp_id", "eqp.eqp_id"))
        self.assertEqual((found[0]["orphans"], found[0]["case_fixable"], found[0]["unused_parents"]), (2, 1, 2))
        text = profile.render_relations(found)
        self.assertIn("[HIGH]", text)
        self.assertIn("1 would match ignoring case", text)

    def test_parent_with_one_duplicate_still_counts_as_the_key(self):
        rows = "\n".join(f"LOT{n:04d},25" for n in range(40))
        parent = load_table(self.write("lots.csv", f"lot_id,qty\n{rows}\nLOT0003,25\n"))
        child = load_table(self.write("hist.csv", "lot_id,step\nLOT0001,A\nLOT0001,B\nLOT9999,A\n"))
        found = profile.relations([parent, child], [profile.profile_table(parent), profile.profile_table(child)])
        self.assertEqual([(f["child"], f["orphans"], f["examples"]) for f in found], [("hist.lot_id", 1, ["LOT9999"])])


class InjectedDefects(TempCase):
    def test_every_injected_sample_defect_is_reported(self):
        """Scores the profiler against samples/make_samples.py: each planted defect must surface."""
        data = self.dir / "data"
        subprocess.run([sys.executable, str(REPO / "samples" / "make_samples.py"), str(data)], check=True, capture_output=True)
        code, out = hx("profile", data / "equipment.csv", data / "lots.csv", data / "history.csv", data / "fdc.csv",
                       data / "yield.json", cwd=self.dir)
        self.assertEqual(code, 0, out)
        for expected in ("encoding='cp949'", "제품", "lot_id: looks like an ID but 1 value(s) repeat: 'LOT0007'×2",
                         "wafer_qty: 1 missing", "'N/A'×1", "wafer_qty: 1 zero value", "['HOLD', 'Hold', 'hold']",
                         "due_date: 2 date formats are mixed", "zero-padded digit code",
                         "encoding='utf-8-sig'", "['ETCH09', 'etch01']; 1 would match ignoring case",
                         "history.lot_id → lots.lot_id: 1 of 32 value(s) have NO parent, e.g. ['LOT9999']",
                         "temperature: possible sentinel/placeholder value(s) [-999]",
                         "pressure: 1 non-numeric value(s) in a numeric column: 'ERR'×1",
                         "'912.4'", "eqp_id=ETCH01: gap of 2:02:00", "3 fully duplicated row(s)",
                         "records taken from top-level key 'wafers'", "yield_pct: values mix a 0–1 scale",
                         "1 record(s) lack some keys"):
            self.assertIn(expected, out)
        self.assertTrue((self.dir / ".hx" / "profile" / "lots.json").is_file())
        self.assertRegex(out, r"PROFILE: tables=5 high=\d+ med=\d+")


if __name__ == "__main__":
    unittest.main()
