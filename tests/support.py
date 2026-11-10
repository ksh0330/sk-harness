"""Test helpers: run the kit exactly as a user would (a separate process, piped output)."""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
KIT = REPO / "hx"
sys.path.insert(0, str(REPO))


def hx(*args, cwd, timeout=120, stdin=None):
    """(exit code, combined output decoded as UTF-8). Decoding strictly proves piped output is UTF-8."""
    env = {key: value for key, value in os.environ.items() if key not in ("PYTHONUTF8", "PYTHONIOENCODING")}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run([sys.executable, str(KIT), *map(str, args)], cwd=cwd, env=env, timeout=timeout,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            input=stdin.encode("utf-8") if isinstance(stdin, str) else stdin,
                            stdin=subprocess.DEVNULL if stdin is None else None)
    return result.returncode, result.stdout.decode("utf-8")


class TempCase(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="hxtest-")).resolve()
        self.addCleanup(shutil.rmtree, self.dir, True)

    def write(self, name, text, encoding="utf-8"):
        path = self.dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding=encoding, newline="") as handle:
            handle.write(text)
        return path
