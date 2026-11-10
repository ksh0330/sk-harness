"""Environment diagnosis: what can this machine actually run right now, offline?"""

import importlib.util
import locale
import os
import platform
import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

TOOLS = ("git", "node", "npm", "codex", "claude", "bash", "curl", "sqlite3", "docker")
# module -> what to do when it is missing
MODULES = {
    "pandas": "use csv/json from the standard library or `hx profile`",
    "numpy": "use statistics/math",
    "scipy": "no scipy.optimize/stats: write simple heuristics",
    "sklearn": "no scikit-learn: z-score/IQR/EWMA rules instead of ML models",
    "matplotlib": "no PNG charts: emit inline SVG/HTML",
    "plotly": "no plotly",
    "openpyxl": "pandas.read_excel fails: read .xlsx with hx.tableio.load_table (built in); writing .xlsx is NOT possible, export CSV",
    "xlrd": "legacy .xls unreadable: ask for .xlsx/.csv",
    "pytest": "use `python -m unittest`",
    "flask": "use http.server (`hx new app` scaffold)",
    "fastapi": "use http.server (`hx new app` scaffold)",
    "uvicorn": "needed by fastapi",
    "streamlit": "no streamlit: static HTML + http.server",
    "requests": "use urllib.request",
    "ortools": "no CP-SAT: use scipy.optimize.milp/linear_sum_assignment or a greedy + local search",
    "pulp": "no PuLP: scipy.optimize.milp",
    "networkx": "write BFS/DFS/topological sort by hand",
    "statsmodels": "no ARIMA/SPC helpers: rolling mean/EWMA by hand",
    "xgboost": "use sklearn HistGradientBoosting*",
    "lightgbm": "use sklearn HistGradientBoosting*",
    "torch": "no deep learning",
    "yaml": "use JSON for config",
}
HOSTS = ("pypi.org", "registry.npmjs.org", "github.com", "api.openai.com", "api.anthropic.com", "cdn.jsdelivr.net")


def _version(command):
    path = shutil.which(command)
    if not path:
        return None
    try:
        result = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=15,
                                encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL)
        return (result.stdout or result.stderr).strip().splitlines()[0][:60] if (result.stdout or result.stderr).strip() else "found"
    except (OSError, subprocess.SubprocessError, IndexError):
        return "found (version check failed)"


def run(net=False):
    """Prints the report; returns the number of problems that block basic work."""
    problems = 0
    print(f"python   {platform.python_version()} ({sys.executable})")
    if sys.version_info < (3, 10):
        print("  !! Python 3.10+ is required by hx")
        problems += 1
    print(f"platform {platform.platform()}  cwd={Path.cwd()}")
    print(f"encoding stdout={sys.stdout.encoding} locale={locale.getpreferredencoding(False)} "
          f"PYTHONUTF8={os.environ.get('PYTHONUTF8', '-')}")
    if locale.getpreferredencoding(False).lower().replace("-", "") not in ("utf8", "utf8sig"):
        print("  -> open(path) without encoding= uses the locale codec here: ALWAYS pass encoding='utf-8' "
              "(or 'utf-8-sig' for CSV that Excel will open)")
    print("tools")
    for tool in TOOLS:
        print(f"  {tool:<8} {_version(tool) or 'NOT FOUND'}")
    print("python modules")
    present, absent = [], []
    for module in MODULES:
        (present if importlib.util.find_spec(module) else absent).append(module)
    print(f"  available: {', '.join(present) or '-'}")
    for module in absent:
        print(f"  MISSING {module:<11} -> {MODULES[module]}")
    try:
        with tempfile.NamedTemporaryFile(dir=".", prefix=".hx-write-test-", delete=True):
            pass
        print("write    current directory is writable")
    except OSError as exc:
        print(f"write    !! cannot write here: {exc}")
        problems += 1
    try:
        with socket.socket() as server:
            server.bind(("127.0.0.1", 0))
            print(f"loopback can bind 127.0.0.1 (e.g. port {server.getsockname()[1]}): local web demo is possible")
    except OSError as exc:
        print(f"loopback !! cannot bind a local port: {exc}")
        problems += 1
    free = shutil.disk_usage(".").free / 2 ** 30
    print(f"disk     {free:.1f} GiB free")
    if net:
        print("network  (TCP 443 reachability only; nothing is sent)")
        for host in HOSTS:
            try:
                with socket.create_connection((host, 443), timeout=4):
                    print(f"  {host:<22} reachable")
            except OSError as exc:
                print(f"  {host:<22} BLOCKED/unreachable ({type(exc).__name__})")
    else:
        print("network  not probed (add --net at the venue to see which hosts are reachable)")
    print(f"DOCTOR: {'FAIL' if problems else 'OK'}  blocking_problems={problems}")
    return problems
