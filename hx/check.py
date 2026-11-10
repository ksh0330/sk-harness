"""Rule-based integrity checks over one or more tables (inputs, and the outputs your code produced).

rules.json:
  {"tables": {"lots": "data/lots.csv", "plan": "out/schedule.csv", "all": ["out/schedule.csv", "out/rejected.csv"]},
   "rules": [{"rule": "unique", "table": "lots", "columns": ["lot_id"]}, ...]}
Every rule may carry "level": "warn" (reported, never fails the run) and "name".
"""

import json
import re
from collections import Counter
from pathlib import Path

from .tableio import TableError, comparable, is_missing, load_table, parse_dt, parse_number


class RuleError(ValueError):
    """The rule itself is wrong (unknown table/column/option). Reported as ERROR, never as PASS."""


def _need(rule, *keys):
    for key in keys:
        if key not in rule:
            raise RuleError(f"missing option {key!r}")
    return [rule[key] for key in keys]


def _table(tables, rule, key="table"):
    name = rule.get(key)
    if name not in tables:
        raise RuleError(f"unknown {key} {name!r}; tables={sorted(tables)}")
    return tables[name]


def _columns(table, names):
    try:
        return [table.index(name) for name in ([names] if isinstance(names, str) else names)]
    except TableError as exc:
        raise RuleError(str(exc)) from None


def _key(row, indexes):
    values = tuple(None if is_missing(row[i]) else row[i].strip() for i in indexes)
    return None if any(value is None for value in values) else values


def _where(table, i):
    return f"line {table.lines[i]}"


def r_required_columns(tables, rule):
    table = _table(tables, rule)
    missing = [name for name in _need(rule, "columns")[0] if name not in table.columns]
    return len(missing), [f"missing column {name!r}" for name in missing]


def r_not_null(tables, rule):
    table = _table(tables, rule)
    names, bad = _need(rule, "columns")[0], []
    names = [names] if isinstance(names, str) else names
    for name, index in zip(names, _columns(table, names)):
        bad.extend(f"{_where(table, i)}: {name} is missing ({row[index]!r})"
                   for i, row in enumerate(table.rows) if is_missing(row[index]))
    return len(bad), bad


def r_unique(tables, rule):
    table = _table(tables, rule)
    indexes = _columns(table, _need(rule, "columns")[0])
    first, bad = {}, []
    for i, row in enumerate(table.rows):
        key = _key(row, indexes)
        if key is None:
            continue
        if key in first:
            bad.append(f"{_where(table, i)}: {key} duplicates {_where(table, first[key])}")
        else:
            first[key] = i
    return len(bad), bad


def r_type(tables, rule):
    table = _table(tables, rule)
    column, kind = _need(rule, "column", "type")
    index = _columns(table, column)[0]
    tests = {"int": lambda s: isinstance(parse_number(s), int),
             "float": lambda s: parse_number(s) is not None,
             "number": lambda s: parse_number(s) is not None,
             "datetime": lambda s: parse_dt(s, digits=True) is not None,
             "str": lambda s: True}
    if kind not in tests:
        raise RuleError(f"type must be one of {sorted(tests)}")
    bad = [f"{_where(table, i)}: {column}={row[index]!r} is not {kind}" for i, row in enumerate(table.rows)
           if not is_missing(row[index]) and not tests[kind](row[index].strip())]
    return len(bad), bad


def _bound(value):
    parsed = comparable(str(value))
    if parsed is None:
        raise RuleError(f"bound {value!r} is empty")
    return parsed


def r_range(tables, rule):
    table = _table(tables, rule)
    column = _need(rule, "column")[0]
    index = _columns(table, column)[0]
    low = _bound(rule["min"]) if "min" in rule else None
    high = _bound(rule["max"]) if "max" in rule else None
    if low is None and high is None:
        raise RuleError("range needs min and/or max")
    bad = []
    for i, row in enumerate(table.rows):
        value = comparable(row[index]) if row[index] is not None else None
        if value is None:
            continue
        kind = (low or high)[0]
        if value[0] != kind:
            bad.append(f"{_where(table, i)}: {column}={row[index]!r} is not comparable with the bound")
        elif (low and value[1] < low[1]) or (high and value[1] > high[1]):
            bad.append(f"{_where(table, i)}: {column}={row[index]!r} outside [{rule.get('min', '')}, {rule.get('max', '')}]")
    return len(bad), bad


def r_enum(tables, rule):
    table = _table(tables, rule)
    column, allowed = _need(rule, "column", "values")
    index, allowed = _columns(table, column)[0], {str(value) for value in allowed}
    wrong = Counter(row[index].strip() for row in table.rows
                    if not is_missing(row[index]) and row[index].strip() not in allowed)
    return sum(wrong.values()), [f"{column}={value!r} ×{count} not in allowed set" for value, count in wrong.most_common()]


def r_regex(tables, rule):
    table = _table(tables, rule)
    column, pattern = _need(rule, "column", "pattern")
    index = _columns(table, column)[0]
    try:
        compiled = re.compile(pattern)
    except re.error as exc:
        raise RuleError(f"bad pattern: {exc}") from None
    bad = [f"{_where(table, i)}: {column}={row[index]!r} does not match" for i, row in enumerate(table.rows)
           if not is_missing(row[index]) and not compiled.fullmatch(row[index].strip())]
    return len(bad), bad


def _reference(tables, rule):
    table, ref = _table(tables, rule), _table(tables, rule, "ref_table")
    columns = _need(rule, "columns")[0]
    indexes = _columns(table, columns)
    ref_indexes = _columns(ref, rule.get("ref_columns", columns))
    if len(indexes) != len(ref_indexes):
        raise RuleError("columns and ref_columns differ in length")
    return table, ref, indexes, ref_indexes


def r_fk(tables, rule):
    table, ref, indexes, ref_indexes = _reference(tables, rule)
    parents = {_key(row, ref_indexes) for row in ref.rows}
    folded = {tuple(part.casefold() for part in key) for key in parents if key}
    bad, near = [], 0
    for i, row in enumerate(table.rows):
        key = _key(row, indexes)
        if key is not None and key not in parents:
            near += tuple(part.casefold() for part in key) in folded
            bad.append(f"{_where(table, i)}: {key} not found in {ref.name}")
    if near:
        bad.insert(0, f"note: {near} of these would match ignoring upper/lower case")
    return len(bad) - bool(near), bad


def r_same_keys(tables, rule):
    """Both tables must contain exactly the same key set, each key once (e.g. every lot scheduled once)."""
    table, ref, indexes, ref_indexes = _reference(tables, rule)
    mine = Counter(_key(row, indexes) for row in table.rows)
    theirs = {_key(row, ref_indexes) for row in ref.rows}
    mine.pop(None, None)
    theirs.discard(None)
    bad = [f"{key} appears {count} times in {table.name}" for key, count in mine.items() if count > 1]
    bad += [f"{key} is in {table.name} but not in {ref.name}" for key in sorted(set(mine) - theirs)]
    bad += [f"{key} is in {ref.name} but missing from {table.name}" for key in sorted(theirs - set(mine))]
    return len(bad), bad


def _pair(table, i, row, columns, indexes):
    values = [comparable(row[index]) if row[index] is not None else None for index in indexes]
    if any(value is None for value in values):
        return None, None
    if len({value[0] for value in values}) != 1:
        return None, f"{_where(table, i)}: {dict(zip(columns, (row[k] for k in indexes)))} are not comparable"
    return [value[1] for value in values], None


def r_order(tables, rule):
    """columns[0] <= columns[1] <= ... on every row (use "strict": true for <)."""
    table = _table(tables, rule)
    columns = _need(rule, "columns")[0]
    indexes, strict, bad = _columns(table, columns), rule.get("strict", False), []
    for i, row in enumerate(table.rows):
        values, problem = _pair(table, i, row, columns, indexes)
        if problem:
            bad.append(problem)
        elif values and any(b < a or (strict and b == a) for a, b in zip(values, values[1:])):
            bad.append(f"{_where(table, i)}: {dict(zip(columns, (row[k] for k in indexes)))} out of order")
    return len(bad), bad


def r_no_overlap(tables, rule):
    """Within each group (e.g. one machine) the [start, end) intervals must not overlap."""
    table = _table(tables, rule)
    start, end = _need(rule, "start", "end")
    group = rule.get("group", [])
    group_idx, pair_idx = _columns(table, group), _columns(table, [start, end])
    buckets, bad = {}, []
    for i, row in enumerate(table.rows):
        values, problem = _pair(table, i, row, [start, end], pair_idx)
        if problem:
            bad.append(problem)
        elif values:
            if values[1] < values[0]:
                bad.append(f"{_where(table, i)}: {end} is before {start}")
            buckets.setdefault(tuple(row[k] for k in group_idx), []).append((values[0], values[1], i))
    for key, spans in buckets.items():
        spans.sort(key=lambda span: (span[0], span[1]))
        latest_end, latest_i = spans[0][1], spans[0][2]
        for begin, finish, i in spans[1:]:
            if begin < latest_end:
                bad.append(f"{_where(table, i)} overlaps {_where(table, latest_i)} in group {dict(zip(group, key))}")
            if finish > latest_end:
                latest_end, latest_i = finish, i
    return len(bad), bad


def r_monotonic(tables, rule):
    """Values never decrease in file order within each group ("strict": true forbids ties)."""
    table = _table(tables, rule)
    column = _need(rule, "column")[0]
    index, group_idx, strict = _columns(table, column)[0], _columns(table, rule.get("group", [])), rule.get("strict", False)
    last, bad = {}, []
    for i, row in enumerate(table.rows):
        value = comparable(row[index]) if row[index] is not None else None
        if value is None:
            continue
        key = tuple(row[k] for k in group_idx)
        previous = last.get(key)
        if previous and previous[0][0] == value[0] and (value[1] < previous[0][1] or (strict and value[1] == previous[0][1])):
            bad.append(f"{_where(table, i)}: {column}={row[index]!r} goes backwards after {_where(table, previous[1])}")
        last[key] = (value, i)
    return len(bad), bad


def _total(table, column):
    index, total = _columns(table, column)[0], 0.0
    for i, row in enumerate(table.rows):
        if is_missing(row[index]):
            continue
        number = parse_number(row[index].strip())
        if number is None:
            raise RuleError(f"{table.name}.{column} has non-numeric {row[index]!r} at {_where(table, i)}")
        total += number
    return total


def r_conserve(tables, rule):
    """sum(table.column) must equal sum(ref_table.ref_column) within "tol" (nothing lost or invented)."""
    table, ref = _table(tables, rule), _table(tables, rule, "ref_table")
    column = _need(rule, "column")[0]
    left, right = _total(table, column), _total(ref, rule.get("ref_column", column))
    if abs(left - right) > float(rule.get("tol", 1e-9)):
        return 1, [f"sum({table.name}.{column})={left:g} but sum({ref.name}.{rule.get('ref_column', column)})={right:g}"]
    return 0, []


def r_row_count(tables, rule):
    table = _table(tables, rule)
    rows, bad = len(table.rows), []
    if "min" in rule and rows < rule["min"]:
        bad.append(f"{table.name} has {rows} rows, fewer than {rule['min']}")
    if "max" in rule and rows > rule["max"]:
        bad.append(f"{table.name} has {rows} rows, more than {rule['max']}")
    if "equals_table" in rule:
        other = _table(tables, rule, "equals_table")
        if rows != len(other.rows):
            bad.append(f"{table.name} has {rows} rows but {other.name} has {len(other.rows)}")
    if not {"min", "max", "equals_table"} & rule.keys():
        raise RuleError("row_count needs min, max or equals_table")
    return len(bad), bad


_SAFE = {"abs": abs, "min": min, "max": max, "len": len, "round": round, "float": float, "int": int, "str": str,
         "dt": lambda text: (parse_dt(str(text), digits=True) or (None,))[0], "__builtins__": {}}


def _cell(cell):
    if is_missing(cell):
        return None
    number = parse_number(cell.strip())
    return cell.strip() if number is None else number


def _lookup(tables):
    """ref("lots", "lot_id", lot_id, "proc_min"): the value of another table's column for a matching key."""
    cache = {}

    def ref(table_name, key_column, key, column):
        if table_name not in tables:
            raise RuleError(f"ref(): unknown table {table_name!r}; tables={sorted(tables)}")
        other = tables[table_name]
        if (table_name, key_column) not in cache:
            index, k = {}, _columns(other, key_column)[0]
            for row in other.rows:
                index.setdefault(_cell(row[k]), row)  # first match wins; use a unique rule to forbid duplicates
            cache[table_name, key_column] = index
        row = cache[table_name, key_column].get(key)
        return None if row is None else _cell(row[_columns(other, column)[0]])

    return ref


def r_expr(tables, rule):
    """A Python expression that must be true on every row; columns are variables (numbers auto-converted),
    row["any name"] reaches columns that are not identifiers, dt(x) parses a timestamp,
    ref(table, key_column, key, column) looks a value up in another table."""
    table = _table(tables, rule)
    source = _need(rule, "expr")[0]
    if "__" in source or "import" in source:
        raise RuleError("expression may not contain '__' or 'import'")
    try:
        code = compile(source, "<rule>", "eval")
    except SyntaxError as exc:
        raise RuleError(f"bad expression: {exc.msg}") from None
    bad, names = [], dict(_SAFE, ref=_lookup(tables))
    for i, row in enumerate(table.rows):
        values = {name: _cell(cell) for name, cell in zip(table.columns, row)}
        scope = {name: value for name, value in values.items() if name.isidentifier()}
        scope["row"] = values
        try:
            if not eval(code, names, scope):  # noqa: S307 - local rules file written by the operator
                bad.append(f"{_where(table, i)}: false for {{{', '.join(f'{k}={v!r}' for k, v in values.items() if k in source)}}}")
        except RuleError:
            raise
        except NameError as exc:
            raise RuleError(f"{exc}; columns={table.columns}") from None
        except Exception as exc:  # a None operand etc. is a data problem on that row
            bad.append(f"{_where(table, i)}: cannot evaluate ({type(exc).__name__}: {exc})")
    return len(bad), bad


RULES = {name[2:]: function for name, function in list(globals().items()) if name.startswith("r_")}


def load_tables(spec, base):
    """Paths are tried relative to the rules file first, then relative to the current directory."""
    def one(name, path):
        file = str(path).rsplit("#", 1)[0] if "#" in str(path) else str(path)
        return load_table(Path(base) / str(path) if (Path(base) / file).exists() else path, name=name)

    tables = {}
    for name, path in spec.items():
        if not isinstance(path, list):
            tables[name] = one(name, path)
            continue
        # A list is a union of files over their common columns, e.g. scheduled + rejected = everything.
        parts = [one(name, item) for item in path]
        if not parts:
            raise TableError(f"table {name!r}: empty file list")
        columns = [c for c in parts[0].columns if all(c in part.columns for part in parts)]
        if not columns:
            raise TableError(f"table {name!r}: the files share no column")
        merged = parts[0]
        merged.rows = [[row[part.index(c)] for c in columns] for part in parts for row in part.rows]
        merged.lines = [line for part in parts for line in part.lines]
        merged.columns = columns
        tables[name] = merged
    return tables


def run_rules(config, base="."):
    """Returns (results, failed). A misconfigured rule is an ERROR and counts as failed."""
    try:
        tables = load_tables(config.get("tables", {}), base)
    except TableError as exc:
        return [{"name": "load tables", "status": "ERROR", "level": "error", "violations": 1, "examples": [str(exc)]}], True
    results, failed = [], False
    for rule in config.get("rules", []):
        kind, level = rule.get("rule"), rule.get("level", "error")
        label = rule.get("name") or " ".join(
            str(part) for part in (kind, rule.get("table"), rule.get("column") or rule.get("columns") or rule.get("expr") or "") if part)
        try:
            if kind not in RULES:
                raise RuleError(f"unknown rule {kind!r}; available: {sorted(RULES)}")
            count, examples = RULES[kind](tables, rule)
            status = "PASS" if count == 0 else "FAIL" if level == "error" else "WARN"
        except RuleError as exc:
            count, examples, status = 1, [f"rule misconfigured: {exc}"], "ERROR"
        failed = failed or status in ("FAIL", "ERROR")
        results.append({"name": label, "status": status, "level": level, "violations": count, "examples": examples[:5]})
    return results, failed


def render(results):
    lines = []
    for item in results:
        lines.append(f"[{item['status']}] {item['name']}" + (f"  ({item['violations']} violation(s))" if item["violations"] else ""))
        lines.extend(f"    {example}" for example in item["examples"])
    tally = Counter(item["status"] for item in results)
    lines.append(f"CHECK: {'FAIL' if tally['FAIL'] or tally['ERROR'] else 'PASS'}  "
                 f"pass={tally['PASS']} fail={tally['FAIL']} error={tally['ERROR']} warn={tally['WARN']}")
    return "\n".join(lines)


def draft(tables, profiles, relations):
    """Starter rules inferred from the data. They describe what IS, not what MUST be: edit them."""
    spec = {"_note": "DRAFT inferred from the data. Replace with the business rules from the problem statement; "
                     "range/enum start as warn because observed values are not a specification.",
            "tables": {table.name: table.path.replace("\\", "/") for table in tables}, "rules": []}
    rules = spec["rules"]
    for table, profile in zip(tables, profiles):
        rules.append({"rule": "required_columns", "table": table.name, "columns": table.columns})
        for key in profile["keys"][:1]:
            rules.append({"rule": "unique", "table": table.name, "columns": key})
        full = [c["name"] for c in profile["columns"] if not c["missing"]]
        if full:
            rules.append({"rule": "not_null", "table": table.name, "columns": full})
        for column in profile["columns"]:
            dtype, stats = column["dtype"], column.get("stats") or {}
            if dtype in ("int", "float", "datetime"):
                rules.append({"rule": "type", "table": table.name, "column": column["name"], "type": dtype})
            if dtype in ("int", "float") and not column["unique"]:
                rules.append({"rule": "range", "table": table.name, "column": column["name"],
                              "min": stats["min"], "max": stats["max"], "level": "warn"})
            if dtype == "str" and 1 < column["distinct"] <= 12 and column["n"] >= 20:
                rules.append({"rule": "enum", "table": table.name, "column": column["name"],
                              "values": sorted(value for value, _ in column["top"]) if column["distinct"] <= 5
                              else sorted({v.strip() for v in table.col(column["name"]) if not is_missing(v)}), "level": "warn"})
    for item in relations:
        if not item.get("shared"):
            child, parent = item["child"].split(".", 1), item["parent"].split(".", 1)
            rules.append({"rule": "fk", "table": child[0], "columns": [child[1]],
                          "ref_table": parent[0], "ref_columns": [parent[1]]})
    return spec


def read_rules(path):
    try:
        with open(path, encoding="utf-8-sig") as handle:
            config = json.load(handle)
    except FileNotFoundError:
        raise TableError(f"rules file not found: {path}") from None
    except json.JSONDecodeError as exc:
        raise TableError(f"{path}: invalid JSON at line {exc.lineno}: {exc.msg}") from None
    if not isinstance(config, dict) or not isinstance(config.get("rules"), list) or not isinstance(config.get("tables"), dict):
        raise TableError(f'{path}: expected {{"tables": {{name: path}}, "rules": [...]}}')
    return config
