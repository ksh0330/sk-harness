"""Black-box checks for the evaluator using hand-written schedules."""

import csv
import subprocess
import sys
import unittest

from support import REPO, TempCase


EVALUATOR = REPO / "practice" / "evaluate_pm.py"
SOURCE_DATA = REPO / "practice" / "tasks" / "pm-assign" / "data"
ASSIGNMENT_HEADER = ("job_id", "eng_id", "start", "end")
UNASSIGNED_HEADER = ("job_id", "reason")

# E1 has back-to-back work in B2 and then exactly 15 minutes from B2 to B1.
# E2 has a cross-midnight job that intersects the optional break.
VALID_ASSIGNMENTS = [
    ("J11", "E1", "2026-11-11 22:00", "2026-11-11 23:30"),
    ("J15", "E1", "2026-11-11 23:30", "2026-11-12 01:30"),
    ("J14", "E1", "2026-11-12 02:00", "2026-11-12 04:00"),
    ("J16", "E1", "2026-11-12 04:15", "2026-11-12 05:45"),
    ("J19", "E2", "2026-11-11 22:00", "2026-11-11 23:00"),
    ("J06", "E2", "2026-11-11 23:15", "2026-11-12 00:15"),
    ("J12", "E2", "2026-11-12 01:00", "2026-11-12 02:30"),
    ("J03", "E3", "2026-11-11 22:00", "2026-11-12 00:30"),
    ("J13", "E3", "2026-11-12 00:45", "2026-11-12 01:45"),
    ("J20", "E3", "2026-11-12 03:00", "2026-11-12 05:00"),
    ("J05", "E4", "2026-11-11 22:00", "2026-11-11 23:30"),
    ("J01", "E4", "2026-11-11 23:45", "2026-11-12 01:45"),
]
VALID_UNASSIGNED = [
    ("J02", "이 일정에서는 다른 작업을 우선 배정"),
    ("J04", "이 일정에서는 다른 작업을 우선 배정"),
    ("J07", "LITHO 가능 인원 없음"),
    ("J08", "이 일정에서는 다른 작업을 우선 배정"),
    ("J09", "작업 가능 시간 역전"),
    ("J10", "이 일정에서는 다른 작업을 우선 배정"),
    ("J17", "이 일정에서는 다른 작업을 우선 배정"),
    ("J18", "이 일정에서는 다른 작업을 우선 배정"),
]


class PracticeEvaluatorTests(TempCase):
    def setUp(self):
        super().setUp()
        data_dir = self.dir / "data"
        data_dir.mkdir()
        (self.dir / "out").mkdir()
        for name in ("pm_jobs.csv", "engineers.csv"):
            (data_dir / name).write_bytes((SOURCE_DATA / name).read_bytes())
        self.write_outputs()

    def write_outputs(self, assignments=VALID_ASSIGNMENTS, unassigned=VALID_UNASSIGNED):
        outputs = (
            ("assignments.csv", ASSIGNMENT_HEADER, reversed(assignments)),
            ("unassigned.csv", UNASSIGNED_HEADER, unassigned),
        )
        for name, header, rows in outputs:
            with (self.dir / "out" / name).open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(header)
                writer.writerows(rows)

    def run_evaluator(self, *options):
        result = subprocess.run(
            [sys.executable, "-B", str(EVALUATOR), str(self.dir), *options],
            capture_output=True, timeout=10, check=False,
        )
        self.assertEqual(result.stderr, b"")
        return result.returncode, result.stdout.decode("utf-8")

    def assert_invalid(self, *violations, options=()):
        status, output = self.run_evaluator(*options)
        self.assertEqual(status, 1, output)
        self.assertIn("weighted_score=unverified", output)
        for violation in violations:
            self.assertIn(violation, output)

    def test_valid_schedule_counts_j15_once_and_preserves_inputs(self):
        inputs = {path: path.read_bytes() for path in (self.dir / "data").iterdir()}
        status, output = self.run_evaluator()
        self.assertEqual(status, 0, output)
        self.assertIn("assigned=12/20 weighted_score=44", output)
        self.assertEqual({path: path.read_bytes() for path in inputs}, inputs)

    def test_optional_break_rejects_crossing_midnight_and_allows_work_at_one(self):
        self.assert_invalid("[e2_break] J06", options=("--e2-block",))
        assignments = [
            ("J06", "E2", "2026-11-12 02:30", "2026-11-12 03:30") if row[0] == "J06" else row
            for row in VALID_ASSIGNMENTS
        ]
        self.write_outputs(assignments)
        status, output = self.run_evaluator("--e2-block")
        self.assertEqual(status, 0, output)
        self.assertIn("weighted_score=44", output)

    def test_rejects_bad_coverage_even_when_other_rows_are_valid(self):
        assignments = VALID_ASSIGNMENTS + [VALID_ASSIGNMENTS[1], ("PHANTOM", "E1", "", "")]
        unassigned = VALID_UNASSIGNED[1:] + [
            ("J15", "두 결과에 있음"), ("J15", "한 번 더 기록"), ("NO_SUCH_JOB", "허위 행"),
        ]
        self.write_outputs(assignments, unassigned)
        self.assert_invalid(
            "[duplicate_assignment] J15", "[duplicate_unassigned] J15", "[both] J15",
            "[unknown_job] 'PHANTOM'", "[unknown_job] 'NO_SUCH_JOB'", "[missing_job] J02",
        )

    def test_rejects_invalid_individual_bookings(self):
        cases = (
            (("J06", "E99", "2026-11-11 23:15", "2026-11-12 00:15"), "[unknown_engineer] J06"),
            (("J06", "E3", "2026-11-11 23:15", "2026-11-12 00:15"), "[skill] J06"),
            (("J06", "E2", "2026-11-11 23:15", "2026-11-12 0:15"), "[datetime] J06"),
            (("J06", "E2", "2026-11-11 23:15", "2026-11-11 00:15"), "[interval] J06"),
            (("J12", "E2", "2026-11-12 01:00", "2026-11-12 01:30"), "[duration] J12"),
            (("J14", "E1", "2026-11-12 01:59", "2026-11-12 03:59"), "[window] J14"),
            (("J20", "E3", "2026-11-12 03:01", "2026-11-12 05:01"), "[window] J20"),
            (("J06", "E4", "2026-11-12 01:01", "2026-11-12 02:01"), "[shift] J06"),
        )
        for change, violation in cases:
            with self.subTest(violation=violation):
                self.write_outputs([change if row[0] == change[0] else row for row in VALID_ASSIGNMENTS])
                self.assert_invalid(violation)

    def test_rejects_same_bay_overlap_and_insufficient_move_time(self):
        changes = {
            "J15": ("J15", "E1", "2026-11-11 23:29", "2026-11-12 01:29"),
            "J16": ("J16", "E1", "2026-11-12 04:14", "2026-11-12 05:44"),
        }
        self.write_outputs([changes.get(row[0], row) for row in VALID_ASSIGNMENTS])
        self.assert_invalid("[overlap] E1 J11/J15", "[bay_transfer] E1 J14/J16")

    def test_requires_both_infeasible_jobs_to_be_reported_unassigned(self):
        assignments = VALID_ASSIGNMENTS + [
            ("J07", "E2", "2026-11-12 03:00", "2026-11-12 05:00"),
            ("J09", "E3", "2026-11-12 04:45", "2026-11-12 05:45"),
        ]
        self.write_outputs(assignments, [row for row in VALID_UNASSIGNED if row[0] not in {"J07", "J09"}])
        self.assert_invalid("[skill] J07", "[window] J09", "[required_unassigned] J07", "[required_unassigned] J09")

    def test_requires_reason_and_shows_infeasible_job_reasons_for_manual_review(self):
        self.write_outputs(unassigned=[(job_id, "  " if job_id == "J09" else reason)
                                       for job_id, reason in VALID_UNASSIGNED])
        self.assert_invalid("[missing_reason] J09")
        self.write_outputs(unassigned=[(job_id, "alternate explanation" if job_id == "J09" else reason)
                                       for job_id, reason in VALID_UNASSIGNED])
        status, output = self.run_evaluator()
        self.assertEqual(status, 0, output)
        self.assertIn("J09 제출 사유 'alternate explanation'", output)
        self.assertIn("시작 가능 시각이 완료 마감보다 늦은 입력 오류", output)

    def test_rejects_input_mutation(self):
        path = self.dir / "data" / "pm_jobs.csv"
        altered = path.read_bytes().replace(b",etch,", b",ETCH,")
        path.write_bytes(altered)
        self.assert_invalid("[input_changed]")
        self.assertEqual(path.read_bytes(), altered)

    def test_accepts_exact_source_data_with_lf_and_crlf(self):
        for line_end in (b"\n", b"\r\n"):
            with self.subTest(line_end=line_end):
                for path in (self.dir / "data").iterdir():
                    lines = path.read_bytes().replace(b"\r\n", b"\n")
                    path.write_bytes(lines.replace(b"\n", line_end))
                status, output = self.run_evaluator()
                self.assertEqual(status, 0, output)

    def test_help_prints_with_the_windows_pipe_encoding(self):
        status, output = self.run_evaluator("--help")
        self.assertEqual(status, 0, output)
        self.assertIn("--e2-block", output)

    def test_rejects_bad_output_columns(self):
        self.write("out/assignments.csv", "job_id,eng_id,start,end,extra\n")
        self.assert_invalid("[header]")
        self.write("out/assignments.csv", "job_id,eng_id,start,end\nJ01,E2,2026-11-11 22:00\n")
        self.assert_invalid("[columns]")


if __name__ == "__main__":
    unittest.main()
