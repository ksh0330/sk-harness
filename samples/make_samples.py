"""Synthetic fab-like data with deliberately injected defects (no real data, fixed seed).

Run:  python samples/make_samples.py [output_dir]
Each injected defect is listed in DEFECTS so a profiling/checking tool can be scored against it.
"""

import csv
import json
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

DEFECTS = [
    "lots.csv: cp949 encoding with Korean headers; duplicated lot_id LOT0007; wafer_qty 'N/A' and 0; "
    "status written as HOLD/Hold/'hold '; due_date in two formats; zero-padded route code",
    "history.csv: UTF-8 BOM; eqp_id ETCH09 not in equipment; 'etch01' lower-case; lot LOT9999 not in lots; "
    "one track_out before track_in; one overlapping run on ETCH01/A",
    "fdc.csv: sentinel -999 in temperature; 'ERR' in pressure; rf_power spikes; a 2-hour gap; 3 duplicated rows",
    "yield.json: records under key 'wafers'; yield on a 0-1 scale for one lot and 0-100 for the rest; missing keys",
    "schedule_bad.csv: LOT0003 scheduled twice, LOT0005 missing, overlap on CVD01, end before start",
]


def write_csv(path, header, rows, encoding="utf-8"):
    with open(path, "w", newline="", encoding=encoding) as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def main(out):
    rng = random.Random(20261111)
    out.mkdir(parents=True, exist_ok=True)
    start = datetime(2026, 11, 1, 8, 0, 0)

    equipment = [("ETCH01", "ETCH", 2), ("ETCH02", "ETCH", 2), ("ETCH03", "ETCH", 2), ("CVD01", "CVD", 1),
                 ("CVD02", "CVD", 1), ("PHOTO01", "PHOTO", 1), ("PHOTO02", "PHOTO", 1), ("CMP01", "CMP", 1)]
    write_csv(out / "equipment.csv", ["eqp_id", "eqp_type", "chamber_count"], equipment)

    lots = []
    for n in range(1, 41):
        due = start + timedelta(days=rng.randint(2, 9))
        lots.append([f"LOT{n:04d}", rng.choice(["DRAM-A", "DRAM-B", "NAND-X"]), 25, rng.choice([1, 2, 3]),
                     due.strftime("%Y-%m-%d"), rng.choice(["WAIT", "RUN", "HOLD", "DONE"]), f"{rng.randint(1, 20):03d}"])
    lots[6][5], lots[11][5], lots[19][5] = "Hold", "hold ", "HOLD"
    lots[3][2], lots[8][2] = "N/A", 0
    lots[14][4] = (start + timedelta(days=4)).strftime("%Y/%m/%d")
    lots.append(list(lots[6]))  # duplicated key LOT0007
    write_csv(out / "lots.csv", ["lot_id", "제품", "wafer_qty", "priority", "due_date", "status", "route"], lots, "cp949")

    history, clock = [], {}
    steps = [("PHOTO", ["PHOTO01", "PHOTO02"]), ("ETCH", ["ETCH01", "ETCH02", "ETCH03"]), ("CVD", ["CVD01", "CVD02"]), ("CMP", ["CMP01"])]
    for lot in lots[:30]:
        moment = start + timedelta(minutes=rng.randint(0, 120))
        for step, choices in steps:
            eqp = rng.choice(choices)
            chamber = rng.choice("AB") if step == "ETCH" else "A"
            begin = max(moment, clock.get((eqp, chamber), start))
            end = begin + timedelta(minutes=rng.randint(20, 55))
            clock[(eqp, chamber)] = end
            history.append([lot[0], step, eqp, chamber, begin.strftime("%Y-%m-%d %H:%M:%S"),
                            end.strftime("%Y-%m-%d %H:%M:%S"), f"RCP-{step}-{rng.randint(1, 3)}"])
            moment = end + timedelta(minutes=rng.randint(5, 30))
    history[5][2] = "ETCH09"
    history[9][2] = history[9][2].lower() if history[9][2].startswith("ETCH") else "etch01"
    history[17][5] = "2026-11-01 00:00:00"
    first_a = next(row for row in history if row[2] == "ETCH01" and row[3] == "A")
    history.append(["LOT0031", "ETCH", "ETCH01", "A", first_a[4], first_a[5], "RCP-ETCH-1"])
    history.append(["LOT9999", "CMP", "CMP01", "A", "2026-11-02 10:00:00", "2026-11-02 10:30:00", "RCP-CMP-1"])
    write_csv(out / "history.csv", ["lot_id", "step", "eqp_id", "chamber", "track_in", "track_out", "recipe"],
              history, "utf-8-sig")

    fdc = []
    for eqp, base in (("ETCH01", 65.0), ("ETCH02", 68.0)):
        for minute in range(0, 600, 2):
            if eqp == "ETCH01" and 240 <= minute < 360:
                continue  # 2-hour gap
            stamp = (start + timedelta(minutes=minute)).strftime("%Y-%m-%d %H:%M:%S")
            fdc.append([eqp, "A", stamp, round(rng.gauss(base, 0.8), 2), round(rng.gauss(12.0, 0.15), 3),
                        round(rng.gauss(500, 6), 1)])
    for index in (30, 31, 200):
        fdc[index][3] = -999
    fdc[77][4] = "ERR"
    fdc[120][5], fdc[400][5] = 912.4, 15.0
    fdc += [list(fdc[10]), list(fdc[10]), list(fdc[350])]
    write_csv(out / "fdc.csv", ["eqp_id", "chamber", "ts", "temperature", "pressure", "rf_power"], fdc)

    wafers = []
    for lot in lots[:12]:
        for wafer in range(1, 6):
            value = max(40.0, min(99.5, rng.gauss(91, 4)))
            record = {"lot_id": lot[0], "wafer_no": wafer,
                      "yield_pct": round(value / 100, 4) if lot[0] == "LOT0002" else round(value, 2),
                      "bin": {"good": int(value * 6), "fail": 600 - int(value * 6)}}
            if lot[0] == "LOT0004" and wafer == 3:
                del record["yield_pct"]
            wafers.append(record)
    with open(out / "yield.json", "w", encoding="utf-8") as handle:
        json.dump({"generated": "2026-11-05", "wafers": wafers}, handle, ensure_ascii=False, indent=1)

    def plan(rows):
        return [[lot, eqp, (start + timedelta(minutes=a)).strftime("%Y-%m-%d %H:%M"),
                 (start + timedelta(minutes=b)).strftime("%Y-%m-%d %H:%M")] for lot, eqp, a, b in rows]

    good = [("LOT0001", "CVD01", 0, 40), ("LOT0002", "CVD01", 40, 80), ("LOT0003", "CVD02", 0, 45),
            ("LOT0004", "CVD02", 45, 90), ("LOT0005", "CVD01", 80, 130)]
    bad = [("LOT0001", "CVD01", 0, 40), ("LOT0002", "CVD01", 30, 80), ("LOT0003", "CVD02", 0, 45),
           ("LOT0003", "CVD02", 45, 90), ("LOT0004", "CVD01", 130, 120)]
    write_csv(out / "schedule_lots.csv", ["lot_id"], [[f"LOT{n:04d}"] for n in range(1, 6)])
    write_csv(out / "schedule_ok.csv", ["lot_id", "eqp_id", "start", "end"], plan(good))
    write_csv(out / "schedule_bad.csv", ["lot_id", "eqp_id", "start", "end"], plan(bad))

    def rules(schedule):
        return {"tables": {"plan": schedule, "lots": "schedule_lots.csv", "eqp": "equipment.csv"},
                "rules": [{"rule": "not_null", "table": "plan", "columns": ["lot_id", "eqp_id", "start", "end"]},
                          {"rule": "same_keys", "table": "plan", "columns": ["lot_id"], "ref_table": "lots"},
                          {"rule": "fk", "table": "plan", "columns": ["eqp_id"], "ref_table": "eqp"},
                          {"rule": "order", "table": "plan", "columns": ["start", "end"], "strict": True},
                          {"rule": "no_overlap", "table": "plan", "group": ["eqp_id"], "start": "start", "end": "end"}]}

    for name, schedule in (("rules_ok.json", "schedule_ok.csv"), ("rules_bad.json", "schedule_bad.csv")):
        with open(out / name, "w", encoding="utf-8") as handle:
            json.dump(rules(schedule), handle, indent=2)
    print(f"wrote samples to {out}")
    for line in DEFECTS:
        print(" -", line)


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent / "data")
