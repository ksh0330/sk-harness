"""스케줄러 검증. 규칙 검사는 scheduler 내부 함수를 재사용하지 않고 입력·출력 파일만 보고 다시 계산한다."""

import csv
import itertools
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import scheduler  # noqa: E402

HEADER = "lot_id,product,proc_min,due_min,priority,eligible\n"
EQP = "eqp_id,available_from_min\nE1,0\nE2,10\n"


def rows(path):
    with open(path, newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


class Case(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data, self.out = Path(self.tmp.name) / "data", Path(self.tmp.name) / "out"
        self.data.mkdir()

    def run_cli(self, lots, equipment=EQP):
        (self.data / "lots.csv").write_text(HEADER + lots, encoding="utf-8")
        (self.data / "equipment.csv").write_text(equipment, encoding="utf-8")
        result = subprocess.run([sys.executable, str(ROOT / "scheduler.py"), str(self.data), str(self.out)],
                                capture_output=True, text=True, encoding="utf-8")
        return result, rows(self.out / "schedule.csv") if (self.out / "schedule.csv").exists() else None

    def verify(self, data_dir, out_dir):
        """규칙 1~4를 파일만으로 독립 검증하고 TWT를 다시 계산해 돌려준다."""
        lots = {}
        for row in rows(Path(data_dir) / "lots.csv"):
            lots.setdefault(row["lot_id"].strip(), row)
        equipment = {row["eqp_id"]: int(row["available_from_min"]) for row in rows(Path(data_dir) / "equipment.csv")}
        plan, rejected = rows(Path(out_dir) / "schedule.csv"), rows(Path(out_dir) / "rejected.csv")
        accounted = [row["lot_id"] for row in plan] + [row["lot_id"] for row in rejected]
        self.assertEqual(sorted(accounted), sorted(lots), "규칙 1: 모든 lot이 정확히 한 번")
        total, busy = 0, {}
        for row in plan:
            lot, start, end = lots[row["lot_id"]], int(row["start_min"]), int(row["end_min"])
            allowed = [name.strip().upper() for name in lot["eligible"].split("|")]
            self.assertIn(row["eqp_id"], allowed, f"규칙 2: {row}")
            self.assertGreaterEqual(start, equipment[row["eqp_id"]], f"규칙 4 시작 시각: {row}")
            self.assertEqual(end - start, int(lot["proc_min"]), f"규칙 4 처리 시간: {row}")
            busy.setdefault(row["eqp_id"], []).append((start, end))
            total += {1: 3, 2: 2, 3: 1}[int(lot["priority"])] * max(0, end - int(lot["due_min"]))
        for eqp, spans in busy.items():
            spans.sort()
            for (_, first_end), (next_start, _) in zip(spans, spans[1:]):
                self.assertLessEqual(first_end, next_start, f"규칙 3: {eqp} 겹침")
        for row in rejected:
            self.assertTrue(row["reason"].strip(), f"규칙 5: 이유 없음 {row}")
        return total, plan, rejected

    def test_provided_data_satisfies_every_rule_and_beats_fifo(self):
        result = subprocess.run([sys.executable, str(ROOT / "scheduler.py"), str(ROOT / "data"), str(self.out)],
                                capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        total, plan, rejected = self.verify(ROOT / "data", self.out)
        self.assertEqual({row["lot_id"] for row in rejected}, {"LOT007", "LOT008", "LOT014"})
        self.assertEqual(sum(row["lot_id"] == "LOT006" for row in plan), 1)              # 중복 행은 한 번만
        self.assertEqual(next(row["eqp_id"] for row in plan if row["lot_id"] == "LOT013"), "ETCH01")   # ' etch01'
        self.assertEqual(next(row["eqp_id"] for row in plan if row["lot_id"] == "LOT009"), "ETCH02")   # ETCH09 무시
        printed = dict(part.split("=") for part in result.stdout.split() if "=" in part)
        self.assertEqual(int(printed["TWT"]), total, "출력한 TWT가 파일에서 다시 계산한 값과 같아야 한다")
        self.assertLess(total, int(printed["TWT_FIFO"]))
        print(f"TWT_FIFO={printed['TWT_FIFO']} TWT={total}")

    def test_invalid_lots_are_rejected_with_reasons(self):
        result, plan = self.run_cli("A,P,N/A,10,1,E1\nB,P,,10,1,E1\nC,P,-5,10,1,E1\nD,P,10,10,1,E9\nE,P,10,x,1,E1\n"
                                    "F,P,10,10,7,E1\nG,P,10,10,1,\nH,P,10,10,1,E1\nH,P,10,10,1,E1\nH,P,99,10,1,E1\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([row["lot_id"] for row in plan], ["H"])
        rejected = rows(self.out / "rejected.csv")
        self.assertEqual([row["lot_id"] for row in rejected], ["A", "B", "C", "D", "E", "F", "G"])
        self.assertIn("WARN H:", result.stdout)                     # 내용이 다른 중복은 첫 행만 쓰고 경고
        self.assertEqual(int(plan[0]["end_min"]) - int(plan[0]["start_min"]), 10)
        self.verify(self.data, self.out)

    def test_empty_and_fully_rejected_inputs_still_produce_files(self):
        for lots in ("", "A,P,0,10,1,E1\n"):
            result, plan = self.run_cli(lots)
            self.assertEqual((result.returncode, plan), (0, []), result.stderr)
            self.assertIn("TWT=0", result.stdout)

    def test_missing_input_is_an_error_not_an_empty_result(self):
        result = subprocess.run([sys.executable, str(ROOT / "scheduler.py"), str(self.data / "nope"), str(self.out)],
                                capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 2)
        self.assertFalse((self.out / "schedule.csv").exists())
        self.assertEqual(subprocess.run([sys.executable, str(ROOT / "scheduler.py")], capture_output=True).returncode, 2)

    def test_equipment_availability_and_eligibility_are_respected(self):
        result, plan = self.run_cli("A,P,30,100,1,E2\nB,P,20,100,1,E2\nC,P,5,100,2,e1 | E2\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.verify(self.data, self.out)
        self.assertEqual(min(int(row["start_min"]) for row in plan if row["eqp_id"] == "E2"), 10)

    def test_result_is_deterministic(self):
        lots = "".join(f"L{n},P,{10 + (n * 7) % 23},{30 + (n * 13) % 90},{1 + n % 3},E1|E2\n" for n in range(12))
        first, _ = self.run_cli(lots)
        text = (self.out / "schedule.csv").read_text(encoding="utf-8-sig")
        second, _ = self.run_cli(lots)
        self.assertEqual((first.stdout, text), (second.stdout, (self.out / "schedule.csv").read_text(encoding="utf-8-sig")))

    def test_never_worse_than_fifo_and_never_better_than_the_true_optimum(self):
        lots = [{"lot_id": f"L{n}", "proc": 10 + (n * 7) % 23, "due": 20 + (n * 13) % 50, "weight": 1 + n % 3,
                 "eligible": ["E1", "E2"] if n % 2 else ["E1"]} for n in range(6)]
        equipment = {"E1": 0, "E2": 10}
        plan, scores = scheduler.solve(lots, equipment)
        optimum = min(scheduler.twt(scheduler.build(list(order), equipment), lots) for order in itertools.permutations(lots))
        self.assertLessEqual(scores["LOCAL"], min(scores["FIFO"], scores["EDD"], scores["WSLACK"]))
        self.assertGreaterEqual(scores["LOCAL"], optimum)
        self.assertEqual(scheduler.twt(plan, lots), scores["LOCAL"])


if __name__ == "__main__":
    unittest.main()
