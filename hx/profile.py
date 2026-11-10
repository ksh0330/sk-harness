"""Data profiling: schema, types, missing, duplicates, outliers, keys and cross-file references.

The output is a short list of findings an agent must resolve before writing logic on top of the data.
"""

import re
import statistics
from collections import Counter
from datetime import timedelta
from itertools import combinations

from . import util
from .tableio import MISSING_TOKENS, THOUSANDS, parse_dt, parse_number

BOOLS = {"true", "false", "yes", "no", "y", "n", "t", "f"}
SENTINELS = (-9999, -999, -99, -1, 999, 9999, 99999, 999999)
ID_HINT = re.compile(r"(id|_no|_key|_code|_num)$", re.I)
DATE_HINT = re.compile(r"date|time|timestamp|(^|_)(dt|ts)$|일자|일시|시각|시간", re.I)
NONNEG_HINT = re.compile(r"qty|quantity|count|cnt|yield|duration|thick|proc|_(min|sec|ms|hr|hours?)$|수량|수율|시간", re.I)
PCT_HINT = re.compile(r"yield|pct|percent|(?<![a-z])ratio(?![a-z])|수율|비율", re.I)
LEVELS = {"high": 0, "med": 1, "info": 2}


def quantile(ordered, q):
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * q
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def fmt(number):
    if isinstance(number, float) and not number.is_integer():
        return f"{number:.6g}"
    return str(int(number))


def _examples(counter, limit=4):
    return ", ".join(f"{util.short(value, 20)!r}×{count}" for value, count in counter.most_common(limit))


def profile_column(name, values):
    """Classify distinct values once (fast on repetitive manufacturing data), then derive stats."""
    flags, present, empties, padded, tokens = [], [], 0, 0, Counter()
    for value in values:
        if value is None:
            empties += 1
            continue
        text = value.strip()
        if not text:
            empties += 1
        elif text.lower() in MISSING_TOKENS:
            tokens[text] += 1
        else:
            padded += text != value
            present.append(text)
    counts = Counter(present)
    total, missing = len(values), empties + sum(tokens.values())
    info = {"name": name, "n": total, "missing": missing, "distinct": len(counts),
            "unique": bool(present) and len(counts) == len(present) and not missing}

    date_hint = bool(DATE_HINT.search(name))
    kinds, numbers, moments, formats = Counter(), {}, {}, Counter()
    non_numeric, non_date, thousands, zero_padded = Counter(), Counter(), 0, 0
    prefer, date_failures = None, 0
    for text, count in counts.items():
        parsed = None
        if date_hint and text.isdigit() and len(text) in (8, 14):
            parsed = parse_dt(text, digits=True)
        number = None if parsed else parse_number(text)
        if number is None and not parsed and THOUSANDS.match(text):
            number = float(text.replace(",", ""))
            number = int(number) if number.is_integer() else number
            thousands += count
        if number is not None:
            kinds["float" if isinstance(number, float) else "int"] += count
            numbers[text] = number
            non_date[text] += count
            continue
        non_numeric[text] += count
        if not parsed and text.lower() not in BOOLS and (date_failures < 50 or moments):
            parsed = parse_dt(text, prefer)
            date_failures += parsed is None
        if parsed:
            kinds["datetime"] += count
            moments[text] = parsed[0]
            formats[re.sub(r"\d", "9", text)] += count
            prefer = parsed[1]
            continue
        non_date[text] += count
        if text.lower() in BOOLS:
            kinds["bool"] += count
        else:
            kinds["str"] += count
            zero_padded += count if text.isdigit() and text[0] == "0" else 0

    filled = len(present)
    numeric = kinds["int"] + kinds["float"]
    if not filled:
        dtype = "empty"
    elif numeric == filled:
        dtype = "float" if kinds["float"] else "int"
    elif kinds["datetime"] == filled:
        dtype = "datetime"
    elif kinds["bool"] == filled:
        dtype = "bool"
    elif numeric / filled >= 0.9:
        dtype = "float~" if kinds["float"] else "int~"
        flags.append(("high", f"{filled - numeric} non-numeric value(s) in a numeric column: {_examples(non_numeric)}"))
    elif kinds["datetime"] / filled >= 0.9:
        dtype = "datetime~"
        flags.append(("high", f"{filled - kinds['datetime']} value(s) are not dates: {_examples(non_date)}"))
    else:
        dtype = "str"
    info["dtype"] = dtype
    # A key with a few accidental duplicates must still be recognised as the parent side of a reference.
    info["keyish"] = info["unique"] or bool(ID_HINT.search(name) and filled and len(counts) >= 0.95 * filled and len(counts) > 1)
    info["top"] = [[value, count] for value, count in counts.most_common(5)]

    if not filled:
        flags.append(("med", "column is entirely empty"))
    elif missing:
        rate = missing / total
        level = "high" if rate >= 0.5 else "med" if rate >= 0.05 else "info"
        detail = f" (tokens: {_examples(tokens)})" if tokens else ""
        flags.append((level, f"{missing} missing ({rate:.1%}){detail}"))
    if padded:
        flags.append(("med", f"{padded} value(s) have leading/trailing whitespace (strip before joining/grouping)"))
    if thousands:
        flags.append(("med", f"{thousands} value(s) use thousands separators like '1,234' (float() will fail)"))
    if zero_padded:
        flags.append(("info", f"{zero_padded} zero-padded digit code(s) like {next(t for t in counts if t.isdigit() and t[0] == '0')!r}: "
                              f"keep as text, never cast to int"))
    if filled > 1 and len(counts) == 1:
        flags.append(("info", f"constant value {util.short(present[0], 20)!r}"))

    if dtype.startswith(("int", "float")):
        ordered = sorted(numbers[text] for text in present if text in numbers)
        info["stats"] = _numeric_stats(name, ordered, flags)
    elif dtype.startswith("datetime"):
        info["stats"] = _date_stats([moments[text] for text in present if text in moments], formats, flags)
    elif dtype == "str":
        lengths = [len(text) for text in counts]
        info["stats"] = {"min_len": min(lengths), "max_len": max(lengths)}
        for mark in "|;":
            if sum(count for text, count in counts.items() if mark in text) >= 0.2 * filled:
                items = sorted({part.strip() for text in counts for part in text.split(mark) if part.strip()})
                flags.append(("info", f"cells hold lists separated by {mark!r} ({len(items)} distinct item(s), e.g. "
                                      f"{items[:6]}): split before validating or joining"))
                break
        if 1 < len(counts) <= 5000:
            groups = {}
            for text in counts:
                groups.setdefault(re.sub(r"[\s\-_]", "", text).casefold(), []).append(text)
            variants = [forms for forms in groups.values() if len(forms) > 1]
            if variants:
                flags.append(("med", f"{len(variants)} categor{'y is' if len(variants) == 1 else 'ies are'} written in several ways "
                                     f"(case/space/-/_), e.g. {variants[0][:3]}"))
    if dtype in ("int", "str") and ID_HINT.search(name) and filled > len(counts) >= 0.95 * filled:
        repeated = Counter({text: count for text, count in counts.items() if count > 1})
        flags.append(("med", f"looks like an ID but {len(repeated)} value(s) repeat: {_examples(repeated)}"))
    info["flags"] = flags
    return info


def _numeric_stats(name, ordered, flags):
    count = len(ordered)
    q1, median, q3 = (quantile(ordered, q) for q in (0.25, 0.5, 0.75))
    spread = q3 - q1
    stats = {"min": ordered[0], "q1": q1, "median": median, "q3": q3, "max": ordered[-1],
             "mean": statistics.fmean(ordered), "std": statistics.pstdev(ordered) if count > 1 else 0.0,
             "zeros": sum(1 for x in ordered if x == 0), "negatives": sum(1 for x in ordered if x < 0)}
    if spread > 0:
        low, high = q1 - 1.5 * spread, q3 + 1.5 * spread
        outliers = [x for x in ordered if x < low or x > high]
        far = [x for x in outliers if x < q1 - 3 * spread or x > q3 + 3 * spread]
        stats["outliers_iqr"], stats["outliers_far"] = len(outliers), len(far)
        if far:
            edge = sorted(set(far), key=lambda x: -abs(x - median))[:4]
            flags.append(("med", f"{len(far)} extreme outlier(s) beyond 3×IQR (of {len(outliers)} beyond 1.5×IQR), "
                                 f"e.g. {[fmt(x) for x in edge]}; decide: real excursion, sensor fault or unit error"))
        elif len(outliers) > 0.01 * count:
            flags.append(("info", f"{len(outliers)} value(s) beyond 1.5×IQR ({len(outliers) / count:.1%})"))
    suspects = [s for s in SENTINELS if s in (ordered[0], ordered[-1]) and (spread == 0 or abs(s - median) > 3 * spread)
                and ordered.count(s) >= 1 and count > 5]
    if suspects:
        flags.append(("med", f"possible sentinel/placeholder value(s) {suspects} at the edge of the range "
                             f"(often means 'no reading')"))
    if NONNEG_HINT.search(name):
        if stats["negatives"]:
            flags.append(("med", f"{stats['negatives']} negative value(s) in a quantity-like column"))
        if 0 < stats["zeros"] <= 0.05 * count:
            flags.append(("info", f"{stats['zeros']} zero value(s) in a quantity-like column (real zero or missing?)"))
    if PCT_HINT.search(name):
        if ordered[-1] > 100:
            flags.append(("med", f"max {fmt(ordered[-1])} exceeds 100 in a ratio/percent-like column"))
        small = sum(1 for x in ordered if 0 <= x <= 1)
        if 0.05 * count <= small <= 0.95 * count and ordered[-1] > 1.5:
            flags.append(("med", "values mix a 0–1 scale and a 0–100 scale (unit inconsistency?)"))
    return stats


def _date_stats(sequence, formats, flags):
    stats = {"min": str(min(sequence)), "max": str(max(sequence))}
    if len(formats) > 1:
        shapes = Counter()
        for shape, count in formats.items():
            shapes[re.sub(r"\.9+", "", shape)] += count  # fractional seconds are not a different format
        if len(shapes) > 1:
            flags.append(("med", f"{len(shapes)} date formats are mixed: {_examples(shapes, 3)}"))
    if any(re.match(r"99/99/9999", shape) for shape in formats):
        flags.append(("info", "dates like 03/04/2026 are read as month/day; confirm the day/month order"))
    backwards = sum(1 for a, b in zip(sequence, sequence[1:]) if b < a)
    stats["sorted"] = backwards == 0
    if 0 < backwards <= max(1, 0.05 * len(sequence)):  # a log that is almost sorted: the exceptions matter
        flags.append(("med", f"mostly time-ordered but {backwards} backward step(s): out-of-order or mis-stamped records"))
    if max(sequence) > util.now().replace(tzinfo=None) + timedelta(days=1):
        flags.append(("med", f"future timestamp(s) up to {max(sequence)}"))
    if min(sequence).year < 1990:
        flags.append(("med", f"implausibly old timestamp {min(sequence)} (default/placeholder date?)"))
    distinct = sorted(set(sequence))
    if len(distinct) >= 10:
        gaps = [(b - a, a) for a, b in zip(distinct, distinct[1:])]
        typical = statistics.median(gap for gap, _ in gaps)
        widest, start = max(gaps)
        stats["median_interval"], stats["max_gap"] = str(typical), str(widest)
        if typical.total_seconds() > 0 and widest > typical * 10:
            flags.append(("info", f"largest gap {widest} after {start} (typical interval {typical}): missing period?"))
    return stats


def _group_gaps(table, columns):
    """A sensor log looks continuous overall while one machine is silent: look for gaps per group."""
    found = []
    times = [c["name"] for c in columns if c["dtype"] == "datetime"][:2]
    groups = [c["name"] for c in columns if c["dtype"] == "str" and 2 <= c["distinct"] <= 50 and ID_HINT.search(c["name"])][:2]
    for time_column in times:
        ti = table.index(time_column)
        for group_column in groups:
            gi, series = table.index(group_column), {}
            for row in table.rows:
                parsed = parse_dt(row[ti].strip(), digits=True) if row[ti] else None
                if parsed and row[gi]:
                    series.setdefault(row[gi].strip(), set()).add(parsed[0])
            for key, moments in series.items():
                ordered = sorted(moments)
                if len(ordered) < 10:
                    continue
                gaps = [(b - a, a) for a, b in zip(ordered, ordered[1:])]
                typical = statistics.median(gap for gap, _ in gaps)
                widest, start = max(gaps)
                if typical.total_seconds() > 0 and widest > typical * 10:
                    found.append(("med", time_column, f"{group_column}={key}: gap of {widest} after {start} "
                                                      f"(typical interval {typical}); data missing for that period?"))
    return found[:8]


def profile_table(table):
    columns = [profile_column(name, table.col(name)) for name in table.columns]
    rows = len(table.rows)
    findings = [(level, "", message) for level, message in table.notes]
    seen, duplicates, first = set(), 0, None
    for row, line in zip(table.rows, table.lines):
        key = tuple(row)
        if key in seen:
            duplicates += 1
            first = first or line
        seen.add(key)
    if duplicates:
        findings.append(("med", "", f"{duplicates} fully duplicated row(s), first at line/row {first}"))
    keys = [[c["name"]] for c in columns if c["unique"] and not c["dtype"].startswith("float")]
    if not keys and rows > 1:
        strong = sorted((c for c in columns if not c["missing"] and c["dtype"] in ("int", "str", "datetime")),
                        key=lambda c: -c["distinct"])[:8]
        for a, b in combinations(strong, 2):
            ia, ib = table.index(a["name"]), table.index(b["name"])
            if len({(row[ia], row[ib]) for row in table.rows}) == rows:
                keys.append([a["name"], b["name"]])
                if len(keys) == 3:
                    break
        if not keys:
            findings.append(("info", "", "no single or two-column unique key found (rows may not be addressable)"))
    for column in columns:
        findings.extend((level, column["name"], message) for level, message in column["flags"])
    findings.extend(_group_gaps(table, columns))
    findings.sort(key=lambda item: LEVELS[item[0]])
    return {"name": table.name, "path": table.path, "rows": rows, "meta": table.meta, "duplicates": duplicates,
            "keys": keys, "columns": columns, "findings": [list(item) for item in findings]}


def _norm(name):
    return re.sub(r"[^0-9a-z가-힣]", "", name.lower())


def _values(table, column):
    return {value.strip() for value in table.col(column)
            if value is not None and value.strip() and value.strip().lower() not in MISSING_TOKENS}


def relations(tables, profiles):
    """Same-named columns across files: which side is the key, and which values have no partner."""
    found = []
    for (ta, pa), (tb, pb) in combinations(list(zip(tables, profiles)), 2):
        names_b = {_norm(c["name"]): c for c in pb["columns"]}
        for ca in pa["columns"]:
            cb = names_b.get(_norm(ca["name"]))
            if not cb or "float" in (ca["dtype"][:5], cb["dtype"][:5]) or min(ca["distinct"], cb["distinct"]) < 2:
                continue
            va, vb = _values(ta, ca["name"]), _values(tb, cb["name"])
            if not va & vb:
                continue
            for child, parent, vc, vp, cc, cp in ((ta, tb, va, vb, ca, cb), (tb, ta, vb, va, cb, ca)):
                if not cp["keyish"] or (cc["keyish"] and child is tb):
                    continue  # a reference must point at a key; report key-to-key pairs once
                orphans = sorted(vc - vp)
                folded = {value.casefold() for value in vp}
                fixable = sum(1 for value in orphans if value.casefold() in folded)
                found.append({"child": f"{child.name}.{cc['name']}", "parent": f"{parent.name}.{cp['name']}",
                              "orphans": len(orphans), "examples": orphans[:5], "case_fixable": fixable,
                              "unused_parents": len(vp - vc), "child_values": len(vc)})
            if not ca["keyish"] and not cb["keyish"] and ID_HINT.search(ca["name"]):
                found.append({"child": f"{ta.name}.{ca['name']}", "parent": f"{tb.name}.{cb['name']}", "shared": True,
                              "overlap": len(va & vb), "only_left": len(va - vb), "only_right": len(vb - va)})
    return found


def render(profile):
    meta = profile["meta"]
    extra = " ".join(f"{key}={meta[key]!r}" for key in ("encoding", "delimiter", "sheet") if meta.get(key))
    keys = ", ".join("+".join(key) for key in profile["keys"]) or "none"
    lines = [f"## {profile['name']}  ({profile['path']})",
             f"rows={profile['rows']} cols={len(profile['columns'])} duplicate_rows={profile['duplicates']} "
             f"key_candidates={keys} {extra}".rstrip(), "",
             "| column | type | missing | distinct | summary |", "|---|---|---|---|---|"]
    for column in profile["columns"]:
        stats, dtype = column.get("stats") or {}, column["dtype"]
        if dtype.startswith(("int", "float")) and stats:
            summary = (f"min={fmt(stats['min'])} q1={fmt(stats['q1'])} med={fmt(stats['median'])} "
                       f"q3={fmt(stats['q3'])} max={fmt(stats['max'])} mean={stats['mean']:.4g} sd={stats['std']:.4g}")
        elif dtype.startswith("datetime") and stats:
            summary = f"{stats['min']} → {stats['max']}" + (f" step≈{stats['median_interval']}" if "median_interval" in stats else "")
        else:
            summary = " ".join(f"{util.short(value, 16)}({count})" for value, count in column["top"][:4])
            if column["unique"]:
                summary += " (unique)"
        rate = f" ({column['missing'] / column['n']:.0%})" if column["missing"] and column["n"] else ""
        lines.append(f"| {util.short(column['name'], 30)} | {dtype} | {column['missing']}{rate} | {column['distinct']} | {summary} |")
    lines.append("")
    if profile["findings"]:
        lines.append("Findings:")
        lines.extend(f"- [{level.upper()}] {column + ': ' if column else ''}{message}"
                     for level, column, message in profile["findings"])
    else:
        lines.append("Findings: none")
    return "\n".join(lines)


def render_relations(found):
    if not found:
        return ""
    lines = ["## Cross-file references (same-named columns)"]
    for item in found:
        if item.get("shared"):
            lines.append(f"- [INFO] {item['child']} ~ {item['parent']}: neither side is unique; shared={item['overlap']} "
                         f"only-left={item['only_left']} only-right={item['only_right']}")
            continue
        if item["orphans"]:
            hint = f"; {item['case_fixable']} would match ignoring case" if item["case_fixable"] else ""
            lines.append(f"- [HIGH] {item['child']} → {item['parent']}: {item['orphans']} of {item['child_values']} "
                         f"value(s) have NO parent, e.g. {item['examples']}{hint}")
        else:
            lines.append(f"- [OK] {item['child']} → {item['parent']}: every value has a parent "
                         f"({item['unused_parents']} parent key(s) unused)")
    return "\n".join(lines)
