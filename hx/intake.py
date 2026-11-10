"""`hx intake`: one look at an unfamiliar task folder. Documents are turned into text, data files are
profiled, existing code and tooling are listed. `hx ship`: the submission report and last-minute lints."""

import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from . import collab, ledger, profile, util
from .tableio import _LOADERS, TableError, load_table

DOC_EXT = {".md", ".txt", ".rst", ".pdf", ".docx", ".pptx", ".hwpx", ".hwp", ".html", ".htm"}
DATA_EXT = set(_LOADERS) - {".txt", ".log", ".dat"} | {".xls"}
MARKERS = {"package.json": "Node project", "requirements.txt": "Python requirements", "pyproject.toml": "Python project",
           "Dockerfile": "Docker", "docker-compose.yml": "Docker Compose", "Makefile": "Makefile", "pom.xml": "Maven (Java)",
           "build.gradle": "Gradle", "go.mod": "Go module", "Cargo.toml": "Rust crate", "manage.py": "Django",
           "vite.config.js": "Vite", "vite.config.ts": "Vite", "next.config.js": "Next.js", "tsconfig.json": "TypeScript"}


def _xml_text(archive, member, paragraph, run):
    """Text of one XML part: one line per paragraph element, concatenating its text runs."""
    lines = []
    with archive.open(member) as stream:
        for _, node in ET.iterparse(stream):
            if node.tag.rsplit("}", 1)[-1] == paragraph:
                text = "".join(part.text or "" for part in node.iter() if part.tag.rsplit("}", 1)[-1] == run)
                if text.strip():
                    lines.append(text)
                node.clear()
    return lines


def extract_text(path):
    """(text, note). Never raises: an unreadable document yields an empty text and the reason."""
    path, suffix = Path(path), Path(path).suffix.lower()
    try:
        if suffix in (".md", ".txt", ".rst", ".html", ".htm"):
            text = util.decode(path.read_bytes())
            return (re.sub(r"<[^>]+>", " ", text) if suffix.startswith(".htm") else text), ""
        if suffix == ".pdf":
            try:
                import pypdf
                return "\n\n".join(page.extract_text() or "" for page in pypdf.PdfReader(str(path)).pages), "pypdf"
            except ImportError:
                pass
            try:
                import fitz
                with fitz.open(str(path)) as document:
                    return "\n\n".join(page.get_text() for page in document), "PyMuPDF"
            except ImportError:
                return "", "no PDF library here (pypdf/PyMuPDF): ask the user to paste the text into docs/PROBLEM.md"
        if suffix in (".docx", ".pptx", ".hwpx"):
            with zipfile.ZipFile(path) as archive:
                names = archive.namelist()
                if suffix == ".docx":
                    parts, paragraph, run = ["word/document.xml"], "p", "t"
                elif suffix == ".pptx":
                    parts = sorted((n for n in names if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)),
                                   key=lambda n: int(re.findall(r"\d+", n)[-1]))
                    paragraph, run = "p", "t"
                else:
                    parts, paragraph, run = sorted(n for n in names if re.fullmatch(r"Contents/section\d+\.xml", n)), "p", "t"
                lines = []
                for part in parts:
                    if part in names:
                        lines += _xml_text(archive, part, paragraph, run) + [""]
                return "\n".join(lines), ""
        if suffix == ".hwp":
            return "", "binary .hwp cannot be read here: ask the user to export it as PDF or paste the text into docs/PROBLEM.md"
    except Exception as exc:  # a broken document must not stop the intake
        return "", f"could not read ({type(exc).__name__}: {exc})"
    return "", "unsupported document type"


def _walk(root, limit=4000):
    files = []
    for folder, dirs, names in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in util.SKIP_DIRS and not d.startswith(".")
                         and not (Path(folder) / d / "hx" / "cli.py").is_file())  # skip a cloned kit
        for name in sorted(names):
            path = Path(folder) / name
            files.append(path)
            if len(files) >= limit:
                return files
    return files


def intake(root, max_data=12):
    root = Path(root)
    files = [path for path in _walk(root) if collab.BOARD.parts[0] not in path.relative_to(root).parts[:1]]
    out = util.state_dir(root, "intake")
    lines = [f"# Intake  {util.stamp()}", f"folder: {root}  files: {len(files)}", "", "## Documents (read these first)"]
    docs = [path for path in files if path.suffix.lower() in DOC_EXT]
    for path in docs:
        relative = path.relative_to(root).as_posix()
        text, note = extract_text(path)
        if path.suffix.lower() in (".md", ".txt", ".rst"):
            lines.append(f"- {relative}  ({len(text)} chars)")
        elif text.strip():
            target = out / (relative.replace("/", "__") + ".txt")
            util.write_text(target, text)
            lines.append(f"- {relative}  -> text extracted to {util.rel(target, root)} ({len(text)} chars{', ' + note if note else ''})")
        else:
            lines.append(f"- {relative}  !! NOT READABLE: {note}")
    if not docs:
        lines.append("- none found: where is the task statement? ask the user")
    lines += ["", "## Data files"]
    data = [path for path in files if path.suffix.lower() in DATA_EXT]
    tables, profiles = [], []
    for path in data[:max_data]:
        relative = path.relative_to(root).as_posix()
        try:
            table = load_table(path, max_rows=50000)
        except TableError as exc:
            lines.append(f"- {relative}  !! {exc}")
            continue
        report = profile.profile_table(table)
        tables.append(table)
        profiles.append(report)
        high = [f"{column + ': ' if column else ''}{message}" for level, column, message in report["findings"] if level == "high"]
        medium = sum(1 for level, _, _ in report["findings"] if level == "med")
        lines.append(f"- {relative}  rows={report['rows']} cols={len(report['columns'])} [{', '.join(c['name'] for c in report['columns'][:12])}"
                     f"{', ...' if len(report['columns']) > 12 else ''}]  high={len(high)} med={medium}")
        lines += [f"    HIGH {util.short(text, 150)}" for text in high[:3]]
    if len(data) > max_data:
        lines.append(f"- ... and {len(data) - max_data} more data file(s) not profiled")
    if len(tables) > 1:
        names = set()
        for table in tables:
            base, n = table.name, 2
            while table.name in names:
                table.name, n = f"{base}_{n}", n + 1
            names.add(table.name)
        broken = [item for item in profile.relations(tables, profiles) if item.get("orphans")]
        lines += [f"- reference broken: {item['child']} -> {item['parent']}: {item['orphans']} value(s) without parent, e.g. {item['examples'][:3]}"
                  for item in broken]
    if data:
        lines.append("  full detail: hx profile <files>")
    else:
        lines.append("- none found")
    lines += ["", "## Existing code and tooling"]
    found = [f"{name} ({label})" for name, label in MARKERS.items() if (root / name).is_file()]
    code = {}
    for path in files:
        if path.suffix.lower() in util.CODE_EXT and path.suffix.lower() not in (".json", ".yaml", ".yml", ".toml", ".ini", ".cfg"):
            code[path.suffix.lower()] = code.get(path.suffix.lower(), 0) + 1
    tests = sorted({path.relative_to(root).parts[0] for path in files if re.search(r"(^|[\\/])tests?([\\/]|$)", str(path.relative_to(root)))})
    lines.append("- project markers: " + (", ".join(found) or "none (empty project: the stack is ours to choose with the user)"))
    lines.append("- source files: " + (", ".join(f"{count}×{ext}" for ext, count in sorted(code.items(), key=lambda kv: -kv[1])) or "none"))
    lines.append("- test folders: " + (", ".join(tests) or "none"))
    lines.append(f"- AGENTS.md present: {(root / 'AGENTS.md').is_file()}  README present: {any((root / n).is_file() for n in ('README.md', 'README', 'readme.md'))}")
    lines += ["", "## Environment"]
    tools = {name: bool(shutil.which(name)) for name in ("git", "node", "npm", "python3", "python", "docker", "sqlite3")}
    lines.append(f"- python {sys.version.split()[0]}; tools: " + ", ".join(f"{name}={'yes' if ok else 'NO'}" for name, ok in tools.items()))
    import importlib.util
    modules = ("pandas", "numpy", "scipy", "sklearn", "matplotlib", "openpyxl", "flask", "fastapi", "pytest", "ortools", "torch")
    lines.append("- python modules: " + ", ".join(f"{name}={'yes' if importlib.util.find_spec(name) else 'NO'}" for name in modules))
    facts = collab.git_facts(root)
    lines.append("- git: " + (f"branch {facts['branch']}, {facts['commits']} commit(s), {len(facts['dirty'])} uncommitted file(s)"
                              if facts["repo"] else "not a repository (hx init --git)"))
    lines += ["", "Next: read the documents, record requirements (hx req add), questions (hx ask), then show `hx brief` to the user."]
    text = "\n".join(lines) + "\n"
    util.write_text(util.state_dir(root) / "INTAKE.md", text)
    return text


# ---------------------------------------------------------------- ship

SECRETS = [(r"sk-[A-Za-z0-9_-]{20,}", "API key (sk-...)"), (r"AKIA[0-9A-Z]{16}", "AWS access key"),
           (r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "private key"),
           (r"(?i)(api[_-]?key|secret|token|passwd|password)\s*[:=]\s*[\"'][A-Za-z0-9_\-/+]{16,}[\"']", "hard-coded credential")]
LOCAL_PATH = re.compile(r"[A-Za-z]:\\\\?Users\\\\?|/home/[a-z0-9_]+/|/Users/[A-Za-z0-9_]+/")
EXTERNAL = re.compile(r"https?://(?!localhost|127\.0\.0\.1|0\.0\.0\.0|www\.w3\.org|example\.)([A-Za-z0-9.-]+\.[a-z]{2,})")


def _shown(command):
    return command if isinstance(command, str) else subprocess.list2cmdline(command)


def lint(root):
    """(blocking, warnings) found in the project's own text files."""
    root, blocking, warnings, hosts, local = Path(root), [], [], {}, []
    for path in _walk(root):
        suffix = path.suffix.lower()
        if suffix not in util.CODE_EXT | {".json", ".md", ".env", ".txt"} or path.stat().st_size > 1_000_000:
            continue
        relative = path.relative_to(root).as_posix()
        try:
            text = util.decode(path.read_bytes())
        except OSError:
            continue
        for number, line in enumerate(text.splitlines(), 1):
            for pattern, label in SECRETS:
                if re.search(pattern, line):
                    blocking.append(f"{relative}:{number}: looks like a {label}; remove it before submitting")
                    break
            if suffix in util.CODE_EXT and suffix != ".md":
                if LOCAL_PATH.search(line) or str(util.KIT.parent) in line:
                    local.append(f"{relative}:{number}")
                if suffix in (".html", ".js", ".jsx", ".ts", ".tsx", ".css", ".vue", ".py"):
                    for host in EXTERNAL.findall(line):
                        hosts.setdefault(host, f"{relative}:{number}")
    if local:
        warnings.append(f"machine-specific absolute path in {len(local)} place(s), e.g. {', '.join(local[:3])}: it will not exist on the judge's machine")
    if hosts:
        warnings.append("the product refers to external hosts (" + ", ".join(f"{host} at {where}" for host, where in list(hosts.items())[:5])
                        + "): it breaks without that network access")
    readme = next((root / name for name in ("README.md", "README", "readme.md") if (root / name).is_file()), None)
    if readme is None:
        warnings.append("no README: the judge needs the run command, the approach and the verification result")
    elif not re.search(r"```|^\s*(python3?|node|npm|sh|bash|\./)\s", util.decode(readme.read_bytes()), re.M):
        warnings.append("README shows no command to run the result")
    return blocking, warnings


def ship(root, rerun=True):
    """Final check + collab/REPORT.md tying each requirement to its proof, decision and commit. Returns ok."""
    root = Path(root)
    if rerun:
        ledger.regress(root)
    blocks, warns, _ = ledger.gate_eval(root)
    secret_blocks, lint_warns = lint(root)
    facts = collab.git_facts(root)
    if facts.get("repo"):
        if facts["dirty"]:
            lint_warns.append(f"{len(facts['dirty'])} file(s) are not committed ({', '.join(facts['dirty'][:5])}): `hx snap` after this report")
        if not any(c["subject"].startswith("[hx-ok") for c in facts["checkpoints"][:1]):
            lint_warns.append("the latest commit is not a verified checkpoint (hx-ok)")
    state = ledger.compute(root)
    items = state["items"]
    ok = not blocks and not secret_blocks
    lines = ["# 제출 보고서", "", f"- 생성: {util.stamp()} · 판정: **{'제출 가능' if ok else '미완료 항목 있음'}** "
             f"(막는 항목 {len(blocks) + len(secret_blocks)}개, 경고 {len(warns) + len(lint_warns)}개)"]
    if facts.get("repo"):
        lines.append(f"- Git: 브랜치 `{facts['branch']}` · HEAD `{facts['head']}` · 커밋 {facts['commits']}개")
    lines += ["", "## 요구사항과 증거", "| id | 종류 | 요구사항 | 확인 방법 | 상태 | 증명 | 검사 (명령) | 로그 |", "|---|---|---|---|---|---|---|---|"]
    for item in items:
        if item["kind"] not in ledger.KINDS:
            continue
        proof, linked = state["proof"][item["id"]]
        commands = "; ".join(f"{name}: `{util.short(_shown(state['checks'][name]['cmd']), 60)}`" for name in linked)
        logs = ", ".join(state["latest"][name]["log"] for name in linked if name in state["latest"])
        lines.append(f"| {item['id']} | {item['kind']} | {util.short(item['text'], 80)} | {util.short(item['accept'], 60) or '-'} | {item['status']} | "
                     f"{proof} | {commands or '-'} | {logs or '-'} |")
    decisions = [item for item in items if item["kind"] == "DECISION"]
    if decisions:
        lines += ["", "## 결정"]
        for item in decisions:
            who = "AI 자율" if item["owner"] == "ai" else "사용자"
            options = (" (검토한 대안: " + " / ".join(item["options"]) + ")") if item.get("options") else ""
            lines.append(f"- {item['id']} [{who}] {item['text']} → {item['choice'] or '미결정'}{options}" + (f" · {item['note'] or item['why']}" if item["note"] or item["why"] else ""))
    questions = [item for item in items if item["kind"] == "QUESTION"]
    if questions:
        lines += ["", "## 질문·답변·가정"]
        for item in questions:
            if item["status"] == "answered":
                lines.append(f"- {item['id']} {item['text']} → [{'담당자' if item.get('source') == 'dm' else '사용자'} 답변] {item['answer']}")
            else:
                lines.append(f"- {item['id']} {item['text']} → 답변 없음, **가정**: {item['assume'] or '(없음)'}")
    history = {}
    for record in state["evidence"]:
        for metric, value in record.get("metrics", {}).items():
            history.setdefault(f"{record['name']}.{metric}", []).append(value)
    if history:
        lines += ["", "## 지표"]
        lines += [f"- {name}: 처음 {values[0]:g} → 최종 {values[-1]:g} (실행 {len(values)}회)" for name, values in history.items()]
    dropped = [item for item in items if item["kind"] in ledger.KINDS and item["status"] == "dropped"]
    problems = blocks + secret_blocks
    if dropped or problems or warns or lint_warns:
        lines += ["", "## 남은 문제와 한계"]
        lines += [f"- [미완료] {text}" for text in problems]
        lines += [f"- [제외] {item['id']} {item['text']}: {item['note'] or '사유 미기록'}" for item in dropped]
        lines += [f"- [경고] {text}" for text in warns + lint_warns]
    if facts.get("repo") and facts["checkpoints"]:
        lines += ["", "## 체크포인트"]
        lines += [f"- `{commit['hash']}` {commit['subject']}" for commit in facts["checkpoints"][:15]]
    lines += ["", "## 다시 검증하는 방법"]
    for name, check in state["checks"].items():
        lines.append(f"- {name}: `{_shown(check['cmd'])}`" + (f" (작업 폴더: {check['cwd']})" if check.get("cwd") not in (None, ".", "") else ""))
    util.write_text(root / "collab" / "REPORT.md", "\n".join(lines) + "\n")
    for text in problems:
        print(f"BLOCK {text}")
    for text in warns + lint_warns:
        print(f"WARN  {text}")
    print(f"SHIP: {'READY' if ok else 'NOT READY'}  blocking={len(problems)} warnings={len(warns) + len(lint_warns)}  report=collab/REPORT.md")
    return ok
