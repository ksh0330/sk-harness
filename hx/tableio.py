"""Dependency-free table loading: CSV/TSV, JSON/JSONL, XLSX, SQLite (Parquet if pyarrow exists).

Every cell is kept as raw text (or None) so that profiling sees what is really in the file:
'007', ' N/A', '1,234' and '2026/11/11' must not be silently coerced the way pandas would.
"""

import csv
import json
import re
import sqlite3
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

MISSING_TOKENS = frozenset({"na", "n/a", "nan", "null", "none", "nil", "-", "--", "?", "#n/a", "#na", "<na>",
                            "(null)", "missing", "#null!", "#div/0!", "#value!", "#ref!", "#num!", "#name?"})


class TableError(ValueError):
    pass


class Table:
    def __init__(self, name, path, columns, rows, lines, notes, meta):
        self.name, self.path, self.columns, self.rows = name, str(path), columns, rows
        self.lines = lines          # source line/row number of each data row, for error messages
        self.notes = notes          # [(level, message)] produced while loading
        self.meta = meta

    def index(self, column):
        try:
            return self.columns.index(column)
        except ValueError:
            raise TableError(f"{self.name}: no column {column!r}; columns={self.columns}") from None

    def col(self, column):
        i = self.index(column)
        return [row[i] for row in self.rows]


def is_missing(value):
    if value is None:
        return True
    text = value.strip()
    return not text or text.lower() in MISSING_TOKENS


# ---------------------------------------------------------------- value parsing

_NUM = re.compile(r"[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$")
THOUSANDS = re.compile(r"[+-]?\d{1,3}(,\d{3})+(\.\d+)?$")
_STRPTIME = ("%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M", "%Y/%m/%d", "%Y.%m.%d %H:%M:%S", "%Y.%m.%d",
             "%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M", "%m/%d/%Y", "%d-%b-%Y", "%d-%b-%y",
             "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z",
             "%Y-%m-%d %I:%M:%S %p", "%m/%d/%Y %I:%M:%S %p", "%Y%m%d %H%M%S", "%Y%m%d %H:%M:%S")


def parse_number(text):
    """int/float for plain numeric text, else None. Zero-padded digit codes ('007') are not numbers."""
    if not _NUM.match(text):
        return None
    body = text.lstrip("+-")
    if body.isdigit():
        if len(body) > 1 and body[0] == "0":
            return None
        return int(text)
    return float(text)


def _naive(moment):
    if moment.tzinfo is not None:
        moment = moment.astimezone(timezone.utc).replace(tzinfo=None)
    return moment


def parse_dt(text, prefer=None, digits=False):
    """(naive datetime, strptime format or 'iso') or None. All-digit forms only when digits=True."""
    size = len(text)
    if size < 8 or size > 35 or not text[0].isdigit():
        return None
    if text.isdigit():
        fmt = {8: "%Y%m%d", 14: "%Y%m%d%H%M%S"}.get(size) if digits else None
        if fmt:
            try:
                moment = datetime.strptime(text, fmt)
                if 1990 <= moment.year <= 2100:
                    return moment, fmt
            except ValueError:
                pass
        return None
    if not any(mark in text for mark in "-/.:"):
        return None
    if prefer and prefer != "iso":
        try:
            return _naive(datetime.strptime(text, prefer)), prefer
        except ValueError:
            pass
    if text[4:5] == "-":
        try:
            return _naive(datetime.fromisoformat(text[:-1] + "+00:00" if text.endswith("Z") else text)), "iso"
        except ValueError:
            pass
    for fmt in _STRPTIME:
        try:
            return _naive(datetime.strptime(text, fmt)), fmt
        except ValueError:
            pass
    return None


def comparable(value):
    """('n', float) | ('d', datetime) | ('s', str) for a present value, None for a missing one."""
    if is_missing(value):
        return None
    text = value.strip()
    number = parse_number(text)
    if number is not None:
        return "n", float(number)
    moment = parse_dt(text)
    if moment:
        return "d", moment[0]
    return "s", text


# ---------------------------------------------------------------- shared assembly

def _stringify(value):
    if value is None or isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, (datetime,)):
        return value.isoformat(sep=" ")
    if isinstance(value, bytes):
        return value.hex()
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(value)


def _filled(cell):
    return cell is not None and str(cell).strip() != ""


def _assemble(name, path, raw, lines, notes, meta, header_row, max_rows):
    """Pick the header row, clean column names, pad ragged rows, drop blank rows."""
    if not raw:
        raise TableError(f"{path}: no rows")
    if header_row:
        head = header_row - 1
        if not 0 <= head < len(raw):
            raise TableError(f"{path}: --header-row {header_row} is outside the file")
    else:
        widths = [sum(map(_filled, row)) for row in raw[:30]]
        if not any(widths):
            raise TableError(f"{path}: the first rows are all blank")
        need = max(widths) * 0.5
        head = next(i for i, width in enumerate(widths) if width >= need and width)
        if head:
            notes.append(("med", f"skipped {head} leading row(s) before the header (title/preamble); "
                                 f"override with --header-row"))
    width = max(len(row) for row in raw[head:])
    header, columns, seen = list(raw[head]) + [None] * (width - len(raw[head])), [], {}
    renamed = []
    for position, cell in enumerate(header, 1):
        label = (str(cell) if cell is not None else "").replace("﻿", "").strip()
        if not label:
            label = f"col_{position}"
            renamed.append(label)
        if label in seen:
            seen[label] += 1
            label = f"{label}__{seen[label]}"
            renamed.append(label)
        else:
            seen[label] = 1
        columns.append(label)
    if renamed:
        notes.append(("med", f"blank or duplicate header names were renamed: {renamed[:6]}"))
    if columns and all(parse_number(c) is not None for c in columns):
        notes.append(("high", "every header cell is numeric: the file probably has NO header row"))
    rows, row_lines, ragged, blank = [], [], [], 0
    for row, line in zip(raw[head + 1:], lines[head + 1:]):
        if not any(map(_filled, row)):
            blank += 1
            continue
        if meta.get("format") == "csv" and len(row) != len(raw[head]):
            ragged.append(line)
        if len(row) != width:
            row = list(row) + [None] * (width - len(row))
        rows.append(row)
        row_lines.append(line)
    if ragged:
        notes.append(("high", f"{len(ragged)} row(s) have a different field count than the header "
                              f"(unquoted delimiter or broken row?), e.g. line {ragged[:5]}"))
    if blank:
        notes.append(("info", f"{blank} blank row(s) ignored"))
    if max_rows and len(rows) > max_rows:
        rows, row_lines = rows[:max_rows], row_lines[:max_rows]
        meta["truncated"] = True
    if meta.get("truncated"):
        notes.append(("med", f"only the first {len(rows)} rows were read (--max-rows); totals are partial"))
    return Table(name, path, columns, rows, row_lines, notes, meta)


# ---------------------------------------------------------------- CSV

def sniff_encoding(path):
    with open(path, "rb") as handle:
        head = handle.read(1 << 20)
    if head.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    if head.startswith((b"\xff\xfe", b"\xfe\xff")):
        return "utf-16"
    cut = head.rfind(b"\n")
    sample = head[:cut] if cut > 0 else head
    for encoding in ("utf-8", "cp949"):
        try:
            sample.decode(encoding)
            return encoding
        except UnicodeDecodeError:
            pass
    return "latin-1"


def sniff_delimiter(lines):
    best, best_score = ",", 0.0
    for delimiter in (",", "\t", ";", "|"):
        try:
            counts = [len(row) for row in csv.reader(lines, delimiter=delimiter) if row]
        except csv.Error:
            continue
        if not counts:
            continue
        mode = max(set(counts), key=counts.count)
        score = (mode - 1) * counts.count(mode) / len(counts)
        if score > best_score:
            best, best_score = delimiter, score
    return best


def _load_csv(path, name, opts):
    encoding = opts.get("encoding") or sniff_encoding(path)
    notes, meta = [], {"format": "csv", "encoding": encoding}
    with open(path, newline="", encoding=encoding, errors="replace") as handle:
        sample = [line for line in (handle.readline() for _ in range(30)) if line]
    delimiter = opts.get("delimiter") or ("\t" if path.suffix.lower() == ".tsv" else sniff_delimiter(sample))
    meta["delimiter"] = delimiter
    csv.field_size_limit(2 ** 31 - 1)
    cap = opts["max_rows"] + 31 if opts.get("max_rows") else None
    raw, lines = [], []
    try:
        with open(path, newline="", encoding=encoding, errors="replace") as handle:
            reader = csv.reader(handle, delimiter=delimiter)
            for row in reader:
                if cap and len(raw) >= cap:
                    meta["truncated"] = True
                    break
                raw.append(row)
                lines.append(reader.line_num)
    except csv.Error as exc:
        raise TableError(f"{path}: CSV parse error near line {len(raw) + 1}: {exc}") from None
    broken = sum(1 for row in raw for cell in row if "�" in cell)
    if broken:
        notes.append(("high", f"{broken} cell(s) could not be decoded as {encoding}; "
                              f"retry with --encoding cp949 or --encoding utf-8"))
    return _assemble(name, path, raw, lines, notes, meta, opts.get("header_row"), opts.get("max_rows"))


# ---------------------------------------------------------------- JSON

def _flatten(record, prefix="", depth=0, out=None):
    out = {} if out is None else out
    for key, value in record.items():
        label = f"{prefix}{key}"
        if isinstance(value, dict) and value and depth < 3:
            _flatten(value, label + ".", depth + 1, out)
        else:
            out[label] = _stringify(value)
    return out


def _records(obj, notes):
    if isinstance(obj, dict):
        lists = [(key, value) for key, value in obj.items()
                 if isinstance(value, list) and value and all(isinstance(item, dict) for item in value[:20])]
        if len(lists) == 1:
            notes.append(("info", f"records taken from top-level key {lists[0][0]!r}; "
                                  f"other keys: {[k for k in obj if k != lists[0][0]][:8]}"))
            obj = lists[0][1]
        elif len(lists) > 1:
            raise TableError(f"several record lists found {[k for k, _ in lists]}; use file.json#key")
        elif obj and all(isinstance(value, dict) for value in obj.values()):
            notes.append(("info", "top-level object maps key -> record; the key is exposed as column _key"))
            obj = [{"_key": key, **value} for key, value in obj.items()]
        else:
            obj = [obj]
    if not isinstance(obj, list):
        raise TableError("JSON root must be a list of records or an object containing one")
    return [item if isinstance(item, dict) else {"value": item} for item in obj]


def _table_from_records(path, name, records, notes, meta, opts):
    if not records:
        raise TableError(f"{path}: no records")
    flat, columns, seen = [], [], set()
    for record in records:
        row = _flatten(record)
        flat.append(row)
        for key in row:
            if key not in seen:
                seen.add(key)
                columns.append(key)
    raw = [columns] + [[row.get(column) for column in columns] for row in flat]
    partial = sum(1 for row in flat if len(row) != len(columns))
    if partial:
        notes.append(("info", f"{partial} record(s) lack some keys (shown as missing)"))
    return _assemble(name, path, raw, list(range(len(raw))), notes, meta, 1, opts.get("max_rows"))


def _read_text(path):
    data = Path(path).read_bytes()
    for encoding in ("utf-8-sig", "cp949"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            pass
    return data.decode("utf-8", errors="replace")


def _load_json(path, name, opts):
    notes, meta = [], {"format": "json"}
    try:
        obj = json.loads(_read_text(path))
    except json.JSONDecodeError as exc:
        raise TableError(f"{path}: invalid JSON at line {exc.lineno} col {exc.colno}: {exc.msg}") from None
    if opts.get("sheet"):
        if not isinstance(obj, dict) or opts["sheet"] not in obj:
            raise TableError(f"{path}: no top-level key {opts['sheet']!r}")
        obj = obj[opts["sheet"]]
    return _table_from_records(path, name, _records(obj, notes), notes, meta, opts)


def _load_jsonl(path, name, opts):
    notes, meta, records, bad = [], {"format": "jsonl"}, [], []
    for number, line in enumerate(_read_text(path).splitlines(), 1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            bad.append(number)
            continue
        records.append(item if isinstance(item, dict) else {"value": item})
    if bad:
        notes.append(("high", f"{len(bad)} line(s) are not valid JSON and were skipped, e.g. line {bad[:5]}"))
    return _table_from_records(path, name, records, notes, meta, opts)


# ---------------------------------------------------------------- XLSX (zip + XML, no openpyxl)

_DATE_FORMAT_IDS = set(range(14, 23)) | set(range(27, 37)) | {45, 46, 47} | set(range(50, 59))


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def _column_index(reference):
    index = 0
    for char in reference:
        if not char.isalpha():
            break
        index = index * 26 + ord(char.upper()) - 64
    return index - 1


def _serial_to_text(serial, date1904):
    base = datetime(1904, 1, 1) if date1904 else datetime(1899, 12, 30)
    moment = base + timedelta(seconds=round(serial * 86400))
    if serial < 1:
        return moment.strftime("%H:%M:%S")
    return moment.strftime("%Y-%m-%d") if moment.time() == datetime.min.time() else moment.strftime("%Y-%m-%d %H:%M:%S")


def _xml(archive, member):
    with archive.open(member) as stream:  # close explicitly: an open member keeps the file locked on Windows
        return ET.parse(stream).getroot()


def _shared_strings(archive):
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    strings = []
    with archive.open("xl/sharedStrings.xml") as stream:
        for _, node in ET.iterparse(stream):
            if _local(node.tag) != "si":
                continue
            parts = []
            for child in node:
                tag = _local(child.tag)
                if tag == "t":
                    parts.append(child.text or "")
                elif tag == "r":  # rich text run; phonetic runs (rPh) are deliberately ignored
                    parts.extend(t.text or "" for t in child if _local(t.tag) == "t")
            strings.append("".join(parts))
            node.clear()
    return strings


def _date_styles(archive):
    if "xl/styles.xml" not in archive.namelist():
        return set()
    root = _xml(archive, "xl/styles.xml")
    custom, styles = {}, set()
    for node in root.iter():
        if _local(node.tag) == "numFmt":
            code = re.sub(r'"[^"]*"|\[[^\]]*\]|\\.', "", node.get("formatCode", ""))
            custom[int(node.get("numFmtId", "0"))] = bool(re.search(r"[ymdhs]", code, re.I)) and "general" not in code.lower()
    for node in root.iter():
        if _local(node.tag) == "cellXfs":
            for position, xf in enumerate(node):
                fmt = int(xf.get("numFmtId", "0"))
                if custom.get(fmt, fmt in _DATE_FORMAT_IDS):
                    styles.add(position)
    return styles


def xlsx_sheets(path):
    with zipfile.ZipFile(path) as archive:
        return [name for name, _ in _workbook(archive)[0]]


def _workbook(archive):
    root = _xml(archive, "xl/workbook.xml")
    targets = {}
    for node in _xml(archive, "xl/_rels/workbook.xml.rels"):
        target = node.get("Target", "")
        targets[node.get("Id")] = target.lstrip("/") if target.startswith("/") else "xl/" + target
    sheets, date1904 = [], False
    for node in root.iter():
        tag = _local(node.tag)
        if tag == "workbookPr":
            date1904 = node.get("date1904") in ("1", "true")
        elif tag == "sheet":
            rid = next((value for key, value in node.attrib.items() if _local(key) == "id"), None)
            sheets.append((node.get("name"), targets.get(rid)))
    return sheets, date1904


def _load_xlsx(path, name, opts):
    notes, meta = [], {"format": "xlsx"}
    try:
        archive = zipfile.ZipFile(path)
    except zipfile.BadZipFile:
        raise TableError(f"{path}: not a valid .xlsx (password-protected or an old .xls renamed?)") from None
    with archive:
        sheets, date1904 = _workbook(archive)
        wanted = opts.get("sheet")
        if wanted is None:
            sheet_name, target = sheets[0]
        elif str(wanted).isdigit() and 1 <= int(wanted) <= len(sheets):
            sheet_name, target = sheets[int(wanted) - 1]
        else:
            match = [item for item in sheets if item[0] == wanted]
            if not match:
                raise TableError(f"{path}: no sheet {wanted!r}; sheets={[s for s, _ in sheets]}")
            sheet_name, target = match[0]
        meta["sheet"], meta["sheets"] = sheet_name, [s for s, _ in sheets]
        if len(sheets) > 1:
            notes.append(("info", f"workbook has {len(sheets)} sheets {meta['sheets']}; this is {sheet_name!r} "
                                  f"(select another with file.xlsx#SheetName)"))
        strings, date_styles = _shared_strings(archive), _date_styles(archive)
        raw, lines, merged, uncached = [], [], 0, 0
        cap = opts["max_rows"] + 31 if opts.get("max_rows") else None
        with archive.open(target) as stream:
            for _, node in ET.iterparse(stream):
                tag = _local(node.tag)
                if tag == "mergeCell":
                    merged += 1
                if tag != "row":
                    continue
                if cap and len(raw) >= cap:
                    meta["truncated"] = True
                    break
                cells, position = {}, -1
                for cell in node:
                    if _local(cell.tag) != "c":
                        continue
                    position = _column_index(cell.get("r")) if cell.get("r") else position + 1
                    kind, value, formula = cell.get("t", "n"), None, False
                    for child in cell:
                        child_tag = _local(child.tag)
                        if child_tag == "v":
                            value = child.text
                        elif child_tag == "f":
                            formula = True
                        elif child_tag == "is":
                            value = "".join(t.text or "" for t in child.iter() if _local(t.tag) == "t")
                    if value is None:
                        uncached += formula
                        continue
                    if kind == "s":
                        value = strings[int(value)]
                    elif kind == "b":
                        value = "true" if value == "1" else "false"
                    elif kind == "n" and int(cell.get("s", "0")) in date_styles:
                        try:
                            value = _serial_to_text(float(value), date1904)
                        except (ValueError, OverflowError):
                            pass
                    elif kind == "n" and value.endswith(".0"):
                        value = value[:-2]
                    cells[position] = value
                if cells:
                    width = max(cells) + 1
                    raw.append([cells.get(i) for i in range(width)])
                    lines.append(int(node.get("r", len(raw))))
                node.clear()
    if merged:
        notes.append(("med", f"{merged} merged cell range(s): only the top-left cell holds the value"))
    if uncached:
        notes.append(("med", f"{uncached} formula cell(s) have no cached value (file never opened in Excel?)"))
    return _assemble(name, path, raw, lines, notes, meta, opts.get("header_row"), opts.get("max_rows"))


# ---------------------------------------------------------------- SQLite / Parquet

def _load_sqlite(path, name, opts):
    notes, meta = [], {"format": "sqlite"}
    connection = sqlite3.connect(f"{Path(path).resolve().as_uri()}?mode=ro", uri=True)
    try:
        tables = [row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%'")]
        wanted = opts.get("sheet") or (tables[0] if len(tables) == 1 else None)
        if wanted not in tables:
            raise TableError(f"{path}: choose a table with file.db#table; tables={tables}")
        meta["sheet"], meta["sheets"] = wanted, tables
        limit = f" LIMIT {int(opts['max_rows']) + 1}" if opts.get("max_rows") else ""
        cursor = connection.execute(f'SELECT * FROM "{wanted}"{limit}')
        raw = [[column[0] for column in cursor.description]]
        raw.extend([_stringify(value) for value in row] for row in cursor)
    except sqlite3.DatabaseError as exc:
        raise TableError(f"{path}: {exc}") from None
    finally:
        connection.close()
    return _assemble(name, path, raw, list(range(len(raw))), notes, meta, 1, opts.get("max_rows"))


def _load_parquet(path, name, opts):
    try:
        import pyarrow.parquet as parquet
    except ImportError:
        raise TableError(f"{path}: parquet needs pyarrow, which is not installed; convert to CSV") from None
    return _table_from_records(path, name, parquet.read_table(path).to_pylist(), [], {"format": "parquet"}, opts)


_LOADERS = {".csv": _load_csv, ".tsv": _load_csv, ".txt": _load_csv, ".dat": _load_csv, ".log": _load_csv,
            ".json": _load_json, ".jsonl": _load_jsonl, ".ndjson": _load_jsonl,
            ".xlsx": _load_xlsx, ".xlsm": _load_xlsx,
            ".db": _load_sqlite, ".sqlite": _load_sqlite, ".sqlite3": _load_sqlite, ".parquet": _load_parquet}


def split_spec(spec):
    """'file.xlsx#Sheet2' -> (path, 'Sheet2'); a plain existing path is returned untouched."""
    spec = str(spec)
    if "#" in spec and not Path(spec).exists():
        file, part = spec.rsplit("#", 1)
        return Path(file), part
    return Path(spec), None


def load_table(spec, name=None, max_rows=None, encoding=None, delimiter=None, header_row=None):
    path, part = split_spec(spec)
    if not path.is_file():
        raise TableError(f"file not found: {path}")
    suffix = path.suffix.lower()
    if suffix == ".xls":
        raise TableError(f"{path}: legacy .xls is not supported without xlrd; save it as .xlsx or .csv")
    loader = _LOADERS.get(suffix)
    if loader is None:
        raise TableError(f"{path}: unsupported extension {suffix!r}; supported: {sorted(_LOADERS)}")
    if path.stat().st_size == 0:
        raise TableError(f"{path}: file is empty")
    label = name or (path.stem + (f"_{part}" if part else ""))
    opts = {"max_rows": max_rows, "encoding": encoding, "delimiter": delimiter,
            "header_row": header_row, "sheet": part}
    try:
        return loader(path, label, opts)
    except (KeyError, ET.ParseError, zipfile.BadZipFile, UnicodeError) as exc:
        raise TableError(f"{path}: cannot read ({type(exc).__name__}: {exc})") from None
