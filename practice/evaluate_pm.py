"""Validate the synthetic PM exercise without importing or running its planner.

Usage: python practice/evaluate_pm.py TASKROOT [--e2-block]
Read TASKROOT/data and TASKROOT/out/{assignments,unassigned}.csv.
With --e2-block, check E2's job intervals against 00:00–01:00 on Nov 12.
The break check does not determine when E2 travels between bays.
"""

import argparse
import csv
import hashlib
import io
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path


# Exact digests for the distributed data in both Git checkout line endings.
INPUT_DIGESTS = {
    "pm_jobs.csv": {
        "bba1084317c867fbb121c8d53adb8545d251cf17c8b2bde1dd648bdff30ecd67",
        "c322fe818a559a23c1075a1d4fba5eb566a290bdd1a539ff41b7826e8a9cf64a",
    },
    "engineers.csv": {
        "76084be693c9b2bb1650d7a8d2772f595b898b8dfd99fed839324f60c40a9213",
        "5affe7b6a5dd17fb70f355ec86eb33e204cb631fd5cce84657dae5fb3fc330dc",
    },
}
WEIGHTS = {1: 5, 2: 2, 3: 1}
REQUIRED_REASONS = {
    "J07": "LITHO 자격을 갖춘 야간 근무자가 없음",
    "J09": "시작 가능 시각이 완료 마감보다 늦은 입력 오류",
}
BAY_TRANSFER = timedelta(minutes=15)
E2_BREAK = (datetime(2026, 11, 12, 0), datetime(2026, 11, 12, 1))


@dataclass(frozen=True)
class Job:
    bay: str
    skill: str
    duration: timedelta
    earliest: datetime
    latest: datetime
    priority: int


@dataclass(frozen=True)
class Engineer:
    skills: set[str]
    shift_start: datetime
    shift_end: datetime


@dataclass(frozen=True)
class Booking:
    job_id: str
    bay: str
    start: datetime
    end: datetime


@dataclass
class Evaluation:
    violations: list[str] = field(default_factory=list)
    reason_reviews: list[str] = field(default_factory=list)
    assigned_by_priority: Counter[int] = field(default_factory=Counter)
    job_count: int = 0


def night_time(value):
    clock = datetime.strptime(value, "%H:%M").time()
    day = 11 if clock.hour >= 22 else 12
    return datetime.combine(datetime(2026, 11, day).date(), clock)


def output_time(value):
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}", value):
        raise ValueError(value)
    return datetime.strptime(value, "%Y-%m-%d %H:%M")


def read_input(taskroot, filename):
    path = taskroot / "data" / filename
    original = path.read_bytes()
    if hashlib.sha256(original).hexdigest() not in INPUT_DIGESTS[filename]:
        raise ValueError(f"[input_changed] {path}: 제공된 원본 데이터와 다릅니다.")
    return csv.DictReader(io.StringIO(original.decode("utf-8-sig")))


def read_jobs(taskroot):
    jobs = {}
    for row in read_input(taskroot, "pm_jobs.csv"):
        # The source digest guarantees J15's duplicate is an identical row.
        jobs[row["job_id"]] = Job(
            row["bay"], row["skill"].casefold(),
            timedelta(minutes=int(row["duration_min"].removesuffix("분"))),
            night_time(row["earliest"]), night_time(row["latest"]), int(row["priority"]),
        )
    return jobs


def read_engineers(taskroot):
    return {
        row["eng_id"]: Engineer(
            set(row["skills"].casefold().split("|")),
            night_time(row["shift_start"]), night_time(row["shift_end"]),
        )
        for row in read_input(taskroot, "engineers.csv")
    }


def read_output(path, fields):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle, strict=True)
        if next(reader, None) != fields:
            raise ValueError(f"[header] {path.name}: 열은 {', '.join(fields)} 순서여야 합니다.")
        rows = []
        for row in reader:
            if not row:
                continue
            if len(row) != len(fields):
                raise ValueError(f"[columns] {path.name} {reader.line_num}행: 열 수가 다릅니다.")
            rows.append(row)
    return rows


def check_assignment(job_id, eng_id, start_text, end_text, job, engineers, e2_block, violations):
    engineer = engineers.get(eng_id)
    if engineer is None:
        violations.append(f"[unknown_engineer] {job_id}: 등록되지 않은 엔지니어 {eng_id!r}")
        return None
    if job.skill not in engineer.skills:
        violations.append(f"[skill] {job_id}: {eng_id}에게 {job.skill.upper()} 자격이 없습니다.")

    try:
        start, end = output_time(start_text), output_time(end_text)
    except ValueError:
        violations.append(f"[datetime] {job_id}: 시작과 종료에 YYYY-MM-DD HH:MM 형식이 필요합니다.")
        return None
    if end <= start:
        violations.append(f"[interval] {job_id}: 종료가 시작보다 늦어야 합니다.")
        return None
    if end - start != job.duration:
        violations.append(f"[duration] {job_id}: 작업 시간이 {job.duration // timedelta(minutes=1)}분이어야 합니다.")
    if start < job.earliest or end > job.latest:
        violations.append(f"[window] {job_id}: 작업 가능 시간창을 벗어났습니다.")
    if start < engineer.shift_start or end > engineer.shift_end:
        violations.append(f"[shift] {job_id}: {eng_id}의 근무 시간 밖에 있습니다.")
    if e2_block and eng_id == "E2" and start < E2_BREAK[1] and end > E2_BREAK[0]:
        violations.append(f"[e2_break] {job_id}: E2 작업이 00:00~01:00 휴식과 겹칩니다.")
    return Booking(job_id, job.bay, start, end)


def check_schedule(schedules, violations):
    for eng_id, bookings in schedules.items():
        bookings.sort(key=lambda booking: booking.start)
        for previous, current in zip(bookings, bookings[1:]):
            gap = current.start - previous.end
            pair = f"{eng_id} {previous.job_id}/{current.job_id}"
            if gap < timedelta(0):
                violations.append(f"[overlap] {pair}: 작업 시간이 겹칩니다.")
            elif previous.bay != current.bay and gap < BAY_TRANSFER:
                violations.append(f"[bay_transfer] {pair}: 다른 bay 사이 이동 시간이 15분 미만입니다.")


def evaluate(taskroot, e2_block=False):
    result = Evaluation()
    violations = result.violations
    try:
        jobs = read_jobs(taskroot)
        engineers = read_engineers(taskroot)
        assignments = read_output(taskroot / "out" / "assignments.csv", ["job_id", "eng_id", "start", "end"])
        unassigned = read_output(taskroot / "out" / "unassigned.csv", ["job_id", "reason"])
    except (OSError, ValueError, csv.Error) as error:
        violations.append(str(error))
        return result

    assigned_ids = set()
    schedules = defaultdict(list)
    for job_id, eng_id, start, end in assignments:
        if job_id in assigned_ids:
            violations.append(f"[duplicate_assignment] {job_id}: 배정 결과에 여러 번 등장합니다.")
        assigned_ids.add(job_id)
        job = jobs.get(job_id)
        if job is None:
            violations.append(f"[unknown_job] {job_id!r}: 작업 원본에 없는 배정입니다.")
            continue
        booking = check_assignment(job_id, eng_id, start, end, job, engineers, e2_block, violations)
        if booking is not None:
            schedules[eng_id].append(booking)

    reasons = {}
    for job_id, reason in unassigned:
        if job_id in reasons:
            violations.append(f"[duplicate_unassigned] {job_id}: 미배정 결과에 여러 번 등장합니다.")
        reasons[job_id] = reason
        if job_id not in jobs:
            violations.append(f"[unknown_job] {job_id!r}: 작업 원본에 없는 미배정입니다.")
        if not reason.strip():
            violations.append(f"[missing_reason] {job_id}: 미배정 사유가 비었습니다.")

    for job_id in sorted(jobs.keys() - assigned_ids - reasons.keys()):
        violations.append(f"[missing_job] {job_id}: 배정과 미배정 결과 양쪽에서 빠졌습니다.")
    for job_id in sorted(assigned_ids & reasons.keys()):
        violations.append(f"[both] {job_id}: 배정과 미배정 결과 양쪽에 있습니다.")
    for job_id, expected in REQUIRED_REASONS.items():
        if job_id not in reasons:
            violations.append(f"[required_unassigned] {job_id}: 미배정으로 보고해야 합니다.")
        else:
            result.reason_reviews.append(f"{job_id} 제출 사유 {reasons[job_id]!r} / 확인할 사실 {expected}")

    check_schedule(schedules, violations)
    if not violations:
        result.job_count = len(jobs)
        result.assigned_by_priority.update(jobs[job_id].priority for job_id in assigned_ids)
    return result


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("taskroot", type=Path)
    parser.add_argument("--e2-block", action="store_true", help="check E2's 00:00–01:00 job break")
    args = parser.parse_args()
    result = evaluate(args.taskroot, args.e2_block)

    if result.violations:
        print(f"FAIL violations={len(result.violations)} weighted_score=unverified")
        for violation in result.violations:
            print(violation)
    else:
        counts = result.assigned_by_priority
        score = sum(weight * counts[priority] for priority, weight in WEIGHTS.items())
        print(f"PASS assigned={sum(counts.values())}/{result.job_count} weighted_score={score}")
        print("배정 건수 " + ", ".join(f"우선순위 {priority} {counts[priority]}건" for priority in WEIGHTS))
    if args.e2_block:
        print("E2 휴식은 작업 구간만 검사합니다. Bay 이동 시각은 확인 범위 밖입니다.")
    for review in result.reason_reviews:
        print(f"사유 수동 확인 {review}")
    return int(bool(result.violations))


if __name__ == "__main__":
    raise SystemExit(main())
