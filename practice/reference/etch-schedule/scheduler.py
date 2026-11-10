"""식각 공정 LOT 투입 계획.  실행: python scheduler.py data out

방법: 정렬 규칙 여러 개(FIFO·EDD·가중 여유)로 리스트 스케줄링을 만들고, 가장 좋은 순서에서
인접 교환·재삽입 국소 탐색으로 가중 납기 지연 합(TWT)을 줄인다. 난수를 쓰지 않아 결과가 재현된다.
"""

import csv
import sys
from pathlib import Path

WEIGHT = {1: 3, 2: 2, 3: 1}


def read_rows(path):
    with open(path, newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def to_int(text):
    try:
        return int(str(text).strip())
    except (TypeError, ValueError):
        return None


def load(data_dir):
    """(lots, rejected, equipment). 완전 중복 행은 한 번만, 오류 lot은 이유와 함께 rejected로."""
    equipment = {}
    for row in read_rows(Path(data_dir) / "equipment.csv"):
        start = to_int(row.get("available_from_min"))
        if row.get("eqp_id", "").strip() and start is not None:
            equipment[row["eqp_id"].strip().upper()] = start
    lots, rejected, seen_rows, seen_ids = [], [], set(), set()
    for row in read_rows(Path(data_dir) / "lots.csv"):
        signature = tuple((value or "").strip() for value in row.values())
        if signature in seen_rows:
            continue                                   # 규칙 5: 완전히 같은 행은 한 번만
        seen_rows.add(signature)
        lot_id = (row.get("lot_id") or "").strip()
        if not lot_id:
            continue
        if lot_id in seen_ids:
            # 규칙 1 때문에 같은 lot을 rejected에도 적을 수 없다: 첫 행을 쓰고 경고만 남긴다.
            print(f"WARN {lot_id}: 같은 lot_id가 다른 내용으로 다시 나옴, 첫 행만 사용")
            continue
        seen_ids.add(lot_id)
        proc, due, priority = to_int(row.get("proc_min")), to_int(row.get("due_min")), to_int(row.get("priority"))
        names = [name.strip().upper() for name in (row.get("eligible") or "").split("|") if name.strip()]
        usable = [name for name in names if name in equipment]     # 가정 Q1·Q3: 대소문자·공백 무시, 있는 설비만
        if proc is None or proc <= 0:                               # 가정 Q2: 0 이하는 처리 시간 없음
            rejected.append((lot_id, f"처리 시간 없음(proc_min={row.get('proc_min')!r})"))
        elif not usable:
            rejected.append((lot_id, f"투입 가능한 설비가 설비 목록에 없음(eligible={row.get('eligible')!r})"))
        elif due is None or priority not in WEIGHT:
            rejected.append((lot_id, f"납기 또는 우선순위 값 오류(due_min={row.get('due_min')!r}, priority={row.get('priority')!r})"))
        else:
            lots.append({"lot_id": lot_id, "proc": proc, "due": due, "weight": WEIGHT[priority], "eligible": usable})
    return lots, rejected, equipment


def build(order, equipment):
    """주어진 순서대로, 각 lot을 가장 빨리 끝낼 수 있는 자격 설비에 붙인다."""
    free, plan = dict(equipment), []
    for lot in order:
        eqp = min(lot["eligible"], key=lambda name: (free[name] + lot["proc"], name))
        start = free[eqp]
        free[eqp] = start + lot["proc"]
        plan.append((lot["lot_id"], eqp, start, free[eqp]))
    return plan


def twt(plan, lots):
    info = {lot["lot_id"]: lot for lot in lots}
    return sum(info[lot_id]["weight"] * max(0, end - info[lot_id]["due"]) for lot_id, _, _, end in plan)


def solve(lots, equipment):
    """(plan, {규칙 이름: TWT}). FIFO는 비교 기준(baseline)으로 항상 계산한다."""
    orders = {"FIFO": list(lots),
              "EDD": sorted(lots, key=lambda lot: (lot["due"], lot["lot_id"])),
              "WSLACK": sorted(lots, key=lambda lot: ((lot["due"] - lot["proc"]) / lot["weight"], lot["lot_id"]))}
    scores = {name: twt(build(order, equipment), lots) for name, order in orders.items()}
    best_name = min(scores, key=lambda name: (scores[name], name))
    order, best = list(orders[best_name]), scores[best_name]
    improved = True
    while improved:                                                 # 재삽입 국소 탐색: 개선이 없을 때까지
        improved = False
        for i in range(len(order)):
            for j in range(len(order)):
                if i == j:
                    continue
                trial = order[:i] + order[i + 1:]
                trial.insert(j, order[i])
                score = twt(build(trial, equipment), lots)
                if score < best:
                    order, best, improved = trial, score, True
                    break
            if improved:
                break
    scores["LOCAL"] = best
    return build(order, equipment), scores


def write(path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def main(argv):
    if len(argv) != 3:
        print("usage: python scheduler.py <data_dir> <out_dir>", file=sys.stderr)
        return 2
    try:
        lots, rejected, equipment = load(argv[1])
    except (OSError, KeyError) as exc:
        print(f"입력을 읽을 수 없습니다: {exc}", file=sys.stderr)
        return 2
    plan, scores = solve(lots, equipment)
    out = Path(argv[2])
    write(out / "schedule.csv", ["lot_id", "eqp_id", "start_min", "end_min"], sorted(plan, key=lambda row: (row[1], row[2])))
    write(out / "rejected.csv", ["lot_id", "reason"], rejected)
    print(f"scheduled={len(plan)} rejected={len(rejected)}")
    print(f"TWT_FIFO={scores['FIFO']} TWT_EDD={scores['EDD']} TWT_WSLACK={scores['WSLACK']}")
    print(f"TWT={scores['LOCAL']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
