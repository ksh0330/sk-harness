"""Shared helpers: state directory, JSON files, time, console encoding, process control."""

import fnmatch
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

STATE = ".hx"
KIT = Path(__file__).resolve().parent

# Directories that never count as project source and are never walked.
SKIP_DIRS = {".git", STATE, "node_modules", ".venv", "venv", "env", "__pycache__", "dist", "build",
             ".next", ".idea", ".vscode", ".pytest_cache", ".mypy_cache", ".ipynb_checkpoints", "site-packages"}
CODE_EXT = {".py", ".ipynb", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".html", ".css", ".vue", ".svelte",
            ".sql", ".sh", ".ps1", ".bat", ".cmd", ".java", ".kt", ".go", ".rs", ".c", ".cpp", ".h", ".cs",
            ".yaml", ".yml", ".toml", ".ini", ".cfg"}
DATA_EXT = {".csv", ".tsv", ".json", ".jsonl", ".xlsx", ".xls", ".parquet", ".npy", ".npz"}


def setup_console():
    """Agents read piped output as UTF-8; a Windows pipe defaults to cp949 and garbles Korean."""
    for stream in (sys.stdout, sys.stderr):
        try:
            if not stream.isatty() and (stream.encoding or "").lower().replace("-", "") != "utf8":
                stream.reconfigure(encoding="utf-8", errors="replace")
            else:
                stream.reconfigure(errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


def find_root(explicit=None):
    """Explicit --root, else the nearest ancestor that was initialised, else the current directory."""
    if explicit:
        return Path(explicit).resolve()
    here = Path.cwd().resolve()
    for folder in (here, *here.parents):
        if (folder / STATE / "config.json").is_file():
            return folder
    return here


def state_dir(root, *parts):
    path = Path(root) / STATE
    for part in parts:
        path = path / part
    path.mkdir(parents=True, exist_ok=True)
    return path


_HELD = set()


@contextmanager
def lock(root, timeout=10):
    """Serialise ledger updates between the main and the mediator session (re-entrant within one process)."""
    path = state_dir(root, "run") / "lock"
    owner = (str(path.resolve()), threading.get_ident())
    if owner in _HELD:
        yield
        return
    started = time.time()
    while True:
        try:
            handle = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            if time.time() - started > timeout:
                raise OSError("the hx ledger is locked; retry, or inspect the lock owner before removing an abandoned lock") from None
            time.sleep(0.05)
    os.write(handle, f"pid={os.getpid()} thread={threading.get_ident()}\n".encode("ascii"))
    _HELD.add(owner)
    try:
        yield
    finally:
        _HELD.discard(owner)
        os.close(handle)
        try:
            os.remove(path)
        except OSError:
            pass


def read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        return default


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def write_text(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def now():
    return datetime.now().astimezone()


def stamp():
    return now().isoformat(timespec="seconds")


def rel(path, root):
    try:
        return Path(path).resolve().relative_to(Path(root).resolve()).as_posix()
    except ValueError:
        return str(path)


def python_cmd():
    """How to call this interpreter from a shell, preferring the short portable name."""
    for name in ("python", "python3"):
        found = shutil.which(name)
        try:
            if found and os.path.samefile(found, sys.executable):
                return name
        except OSError:
            pass
    return f'"{sys.executable}"'


def kit_cmd():
    """Forward slashes work in bash, PowerShell and cmd alike, and survive being embedded in JSON."""
    return f'{python_cmd()} "{KIT.as_posix()}"'


def resolve_argv(argv):
    """Make a list command runnable on Windows (npm -> npm.cmd) and on Linux (python -> python3)."""
    argv = list(argv)
    found = shutil.which(argv[0])
    if found:
        argv[0] = found
    elif argv[0] in ("python", "python3", "py"):
        argv[0] = sys.executable
    return argv


def kill_tree(proc):
    """Terminate a process and its children; a lone terminate() leaves servers behind on Windows."""
    if proc.poll() is not None:
        return
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True, timeout=15)
        else:
            import signal
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


def popen_group(cmd, **kwargs):
    """Start a child in its own process group so kill_tree can stop everything it spawned."""
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1", PYTHONUNBUFFERED="1")
    env.update(kwargs.pop("env", None) or {})
    shell = isinstance(cmd, str)
    return subprocess.Popen(cmd if shell else resolve_argv(cmd), shell=shell, env=env,
                            stdin=subprocess.DEVNULL, **kwargs)


def decode(data):
    for encoding in ("utf-8", "cp949"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            pass
    return data.decode("utf-8", errors="replace")


def source_mtime(root, patterns=None, limit=20000):
    """Newest modification time among source files (or files matching the glob patterns); detects stale evidence."""
    newest, newest_path, seen = 0.0, None, 0
    for folder, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            if patterns:
                relative = os.path.relpath(os.path.join(folder, name), root).replace(os.sep, "/")
                if not any(fnmatch.fnmatch(relative, pattern) for pattern in patterns):
                    continue
            elif os.path.splitext(name)[1].lower() not in CODE_EXT:
                continue
            seen += 1
            if seen > limit:
                return newest, newest_path
            try:
                modified = os.path.getmtime(os.path.join(folder, name))
            except OSError:
                continue
            if modified > newest:
                newest, newest_path = modified, os.path.join(folder, name)
    return newest, newest_path


def short(value, width=28):
    text = str(value).replace("\n", " ").replace("|", "\\|")  # keeps markdown tables intact, value still readable
    return text if len(text) <= width else text[:width - 1] + "…"


def source_fingerprint(root, patterns=None):
    """Hash source and input contents with paths, detecting deletion and preserved mtimes.

    Explicit watch patterns define a check's dependency scope. Generated logs and
    state are excluded. Errors are propagated rather than certifying a partial scan.
    """
    return fingerprint_of(source_hashes(root, patterns))


def fingerprint_of(hashes):
    digest = hashlib.sha256()
    for relative, content in hashes.items():
        digest.update(relative.encode("utf-8") + b"\0")
        digest.update(content)
    return digest.hexdigest()


def source_hashes(root, patterns=None):
    """Per-file content digests in walk order; source_fingerprint combines them."""
    hashes = {}
    for folder, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for name in sorted(files):
            path = Path(folder) / name
            relative = path.relative_to(root).as_posix()
            if patterns:
                if not any(fnmatch.fnmatch(relative, pattern) for pattern in patterns):
                    continue
            elif path.suffix.lower() not in CODE_EXT | DATA_EXT:
                continue
            content_hash = hashlib.sha256()
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    content_hash.update(chunk)
            hashes[relative] = content_hash.digest()
    return hashes
