import json
import sqlite3
import unittest
import zipfile
from datetime import datetime

from support import REPO, TempCase

from hx.tableio import TableError, comparable, load_table, parse_dt, parse_number

SHEET = """<?xml version="1.0" encoding="UTF-8"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>
<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c><c r="D1" t="inlineStr"><is><t>note</t></is></c></row>
<row r="2"><c r="A2" t="s"><v>2</v></c><c r="B2" s="1"><v>46327.5</v></c><c r="C2"><v>12.0</v></c><c r="D2" t="b"><v>1</v></c></row>
<row r="4"><c r="A4" t="s"><v>3</v></c><c r="B4" s="1"><v>46328</v></c><c r="D4"><f>1/0</f></c></row>
</sheetData></worksheet>"""


def make_xlsx(path):
    """A minimal workbook written by hand: shared strings (one with a phonetic run), a date style, a gap column."""
    files = {
        "[Content_Types].xml": "<Types xmlns='http://schemas.openxmlformats.org/package/2006/content-types'/>",
        "xl/workbook.xml": "<workbook xmlns='http://schemas.openxmlformats.org/spreadsheetml/2006/main' "
                           "xmlns:r='http://schemas.openxmlformats.org/officeDocument/2006/relationships'>"
                           "<sheets><sheet name='S1' sheetId='1' r:id='rId1'/><sheet name='S2' sheetId='2' r:id='rId2'/></sheets></workbook>",
        "xl/_rels/workbook.xml.rels": "<Relationships xmlns='http://schemas.openxmlformats.org/package/2006/relationships'>"
                                      "<Relationship Id='rId1' Target='worksheets/sheet1.xml'/>"
                                      "<Relationship Id='rId2' Target='/xl/worksheets/sheet2.xml'/></Relationships>",
        "xl/sharedStrings.xml": "<sst xmlns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'>"
                                "<si><t>lot_id</t></si><si><t>측정일</t></si>"
                                "<si><r><t>LOT</t></r><r><t>0001</t></r><rPh><t>IGNORED</t></rPh></si><si><t>0002</t></si></sst>",
        "xl/styles.xml": "<styleSheet xmlns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'>"
                         "<numFmts><numFmt numFmtId='164' formatCode='yyyy\\-mm\\-dd\\ hh:mm'/></numFmts>"
                         "<cellXfs><xf numFmtId='0'/><xf numFmtId='164'/></cellXfs></styleSheet>",
        "xl/worksheets/sheet1.xml": SHEET,
        "xl/worksheets/sheet2.xml": SHEET.replace("<v>0</v>", "<v>1</v>", 1),
    }
    with zipfile.ZipFile(path, "w") as archive:
        for name, text in files.items():
            archive.writestr(name, text)


class ValueParsing(unittest.TestCase):
    def test_numbers_keep_codes_as_text(self):
        self.assertEqual([parse_number(t) for t in ("12", "+5", "-0.5", ".5", "5.", "1e3", "0", "0.0")],
                         [12, 5, -0.5, 0.5, 5.0, 1000.0, 0, 0.0])
        for text in ("007", "0123", "1_000", "1,234", "nan", "inf", "12a", "", "--1", "1.2.3"):
            self.assertIsNone(parse_number(text), text)

    def test_dates_in_common_factory_formats(self):
        expected = datetime(2026, 11, 11, 9, 30)
        for text in ("2026-11-11 09:30:00", "2026-11-11T09:30:00", "2026/11/11 09:30", "2026.11.11 09:30:00",
                     "11/11/2026 09:30", "2026-11-11T00:30:00Z", "2026-11-11T09:30:00+0900"):
            got = parse_dt(text)
            self.assertIsNotNone(got, text)
            self.assertEqual(got[0], datetime(2026, 11, 11, 0, 30) if "Z" in text or "+0900" in text else expected, text)
        self.assertIsNone(parse_dt("20261111"))                      # digits are a number unless asked
        self.assertEqual(parse_dt("20261111", digits=True)[0], datetime(2026, 11, 11))
        self.assertIsNone(parse_dt("99999999", digits=True))
        for text in ("EQP-01", "12-AB-34", "2026-13-45", "1.5", "LOT0001"):
            self.assertIsNone(parse_dt(text), text)

    def test_comparable_kinds(self):
        self.assertEqual(comparable(" 3 "), ("n", 3.0))
        self.assertEqual(comparable("2026-11-11")[0], "d")
        self.assertEqual(comparable("007"), ("s", "007"))
        self.assertIsNone(comparable(" N/A "))


class Loading(TempCase):
    def test_cp949_korean_csv_and_bom(self):
        table = load_table(self.write("a.csv", "설비,온도\r\n식각1,65.5\r\n", "cp949"))
        self.assertEqual((table.columns, table.rows, table.meta["encoding"]), (["설비", "온도"], [["식각1", "65.5"]], "cp949"))
        table = load_table(self.write("b.csv", "id,v\n1,2\n", "utf-8-sig"))
        self.assertEqual(table.columns, ["id", "v"])  # no BOM glued to the first header

    def test_delimiters_are_sniffed(self):
        for name, sep in (("t.txt", "\t"), ("s.csv", ";"), ("p.dat", "|")):
            table = load_table(self.write(name, sep.join("abc") + "\n" + sep.join(["1", "x,y", "3"]) + "\n"))
            self.assertEqual((table.columns, table.rows[0][1]), (["a", "b", "c"], "x,y"), name)

    def test_quoted_newline_keeps_line_numbers(self):
        table = load_table(self.write("q.csv", 'id,note\n1,"two\nlines"\n2,ok\n'))
        self.assertEqual((table.rows[0][1], table.lines), ("two\nlines", [3, 4]))

    def test_title_rows_ragged_rows_and_header_repairs(self):
        table = load_table(self.write("t.csv", "Weekly report,,,\n,,,\nid,,id,v\n1,a,b,2\n3,c\n\n4,d,e,5,EXTRA\n"))
        self.assertEqual(table.columns, ["id", "col_2", "id__2", "v", "col_5"])
        self.assertEqual(len(table.rows), 3)
        notes = " | ".join(message for _, message in table.notes)
        for expected in ("skipped 2 leading", "renamed", "different field count", "blank row"):
            self.assertIn(expected, notes)
        forced = load_table(self.write("h.csv", "x,y\n1,2\n3,4\n"), header_row=2)
        self.assertEqual(forced.columns, ["1", "2"])
        self.assertIn("NO header", forced.notes[0][1])

    def test_errors_are_explicit(self):
        cases = {"missing.csv": "not found", "empty.csv": "empty", "data.xls": ".xls", "x.bin": "unsupported"}
        self.write("empty.csv", "")
        self.write("data.xls", "x")
        self.write("x.bin", "x")
        for name, expected in cases.items():
            with self.assertRaisesRegex(TableError, expected):
                load_table(self.dir / name)
        with self.assertRaisesRegex(TableError, "invalid JSON at line 2"):
            load_table(self.write("bad.json", '[{"a": 1},\n{oops}]'))
        with self.assertRaisesRegex(TableError, "not a valid .xlsx"):
            load_table(self.write("fake.xlsx", "plain text"))

    def test_max_rows_truncation_is_reported(self):
        table = load_table(self.write("big.csv", "n\n" + "\n".join(map(str, range(500))) + "\n"), max_rows=100)
        self.assertEqual(len(table.rows), 100)
        self.assertTrue(any("first 100 rows" in message for _, message in table.notes))

    def test_json_shapes(self):
        listed = load_table(self.write("l.json", json.dumps([{"a": 1, "n": {"x": True, "y": None}}, {"a": 2.5, "tags": [1, 2]}])))
        self.assertEqual(listed.columns, ["a", "n.x", "n.y", "tags"])
        self.assertEqual(listed.rows, [["1", "true", None, None], ["2.5", None, None, "[1, 2]"]])
        keyed = load_table(self.write("k.json", json.dumps({"meta": "m", "wafers": [{"w": 1}, {"w": 2}]})))
        self.assertEqual((keyed.columns, len(keyed.rows)), (["w"], 2))
        mapped = load_table(self.write("m.json", json.dumps({"E1": {"t": 1}, "E2": {"t": 2}})))
        self.assertEqual(mapped.rows, [["E1", "1"], ["E2", "2"]])
        picked = load_table(str(self.write("two.json", json.dumps({"a": [{"x": 1}], "b": [{"y": 2}]}))) + "#b")
        self.assertEqual(picked.columns, ["y"])
        with self.assertRaisesRegex(TableError, "several record lists"):
            load_table(self.dir / "two.json")

    def test_jsonl_skips_and_reports_bad_lines(self):
        table = load_table(self.write("e.jsonl", '{"a": 1}\nnot json\n\n{"a": 2, "b": "x"}\n'))
        self.assertEqual(table.rows, [["1", None], ["2", "x"]])
        self.assertIn("line [2]", table.notes[0][1])

    def test_handmade_xlsx(self):
        make_xlsx(self.dir / "w.xlsx")
        table = load_table(self.dir / "w.xlsx")
        self.assertEqual(table.columns, ["lot_id", "측정일", "col_3", "note"])
        self.assertEqual(table.rows, [["LOT0001", "2026-11-01 12:00:00", "12", "true"], ["0002", "2026-11-02", None, None]])
        self.assertEqual(table.lines, [2, 4])
        notes = " | ".join(message for _, message in table.notes)
        self.assertIn("2 sheets", notes)
        self.assertIn("no cached value", notes)
        self.assertEqual(load_table(str(self.dir / "w.xlsx") + "#S2").meta["sheet"], "S2")
        self.assertEqual(load_table(str(self.dir / "w.xlsx") + "#2").meta["sheet"], "S2")
        with self.assertRaisesRegex(TableError, "no sheet 'nope'"):
            load_table(str(self.dir / "w.xlsx") + "#nope")

    def test_workbook_saved_by_real_excel(self):
        sample = REPO / "samples" / "data" / "yield_summary.xlsx"
        if not sample.is_file():
            self.skipTest("samples/data/yield_summary.xlsx was not generated on this machine")
        table = load_table(sample)
        self.assertEqual(table.columns, ["lot_id", "측정일", "수율(%)", "설비", "비고"])
        self.assertEqual(table.rows[0], ["LOT0001", "2026-11-01", "93.5", "ETCH01", "정상"])
        self.assertEqual(table.rows[4][0], "0005")                       # text-formatted code survives
        self.assertAlmostEqual(float(table.rows[5][2]), 70.555, places=3)  # cached formula result
        raw = load_table(str(sample) + "#raw")
        self.assertEqual(raw.rows[0], ["1", "2026-11-01 08:45:00", "101.5"])

    def test_sqlite_is_read_only(self):
        path = self.dir / "mes.db"
        connection = sqlite3.connect(path)
        connection.execute("CREATE TABLE lot (lot_id TEXT, qty INTEGER, w REAL)")
        connection.executemany("INSERT INTO lot VALUES (?, ?, ?)", [("L1", 25, 1.5), ("L2", None, 2.0)])
        connection.commit()
        connection.close()
        table = load_table(path)
        self.assertEqual(table.rows, [["L1", "25", "1.5"], ["L2", None, "2.0"]])
        connection = sqlite3.connect(path)
        connection.execute("CREATE TABLE other (x)")
        connection.commit()
        connection.close()
        with self.assertRaisesRegex(TableError, "choose a table"):
            load_table(path)
        self.assertEqual(load_table(str(path) + "#lot").columns, ["lot_id", "qty", "w"])


if __name__ == "__main__":
    unittest.main()
