"""Entry point for both `python -m hx` and `python path/to/hx`."""

import os
import sys

if __package__ in (None, ""):  # executed as a directory: make the package importable
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hx.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
