"""Known-good checkpoints on top of git: `snap` tags a verified state, `back` returns to it.

Nothing is ever discarded: `back` first commits the broken tree and leaves it on a branch.
Only local commands are used (no push, no remote, no config writes).
"""

import os
import subprocess
import time
from pathlib import Path

from . import ledger, util

EXCLUDES = ["node_modules/", ".venv/", "venv/", "__pycache__/", "*.pyc", ".pytest_cache/", ".ipynb_checkpoints/",
            "dist/", "build/", ".next/", ".hx/run/", ".env", ".env.*", "*.pem", "*.key"]
BIG = 25 * 1024 * 1024


class SnapError(RuntimeError):
    pass


def git(root, *args, check=True):
    try:
        result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=120)
    except FileNotFoundError:
        raise SnapError("git is not installed or not on PATH") from None
    if check and result.returncode:
        raise SnapError(f"git {' '.join(args[:2])} failed: {(result.stderr or result.stdout).strip()[:300]}")
    return result


def is_repo_root(root):
    result = git(root, "rev-parse", "--show-toplevel", check=False)
    if result.returncode:
        return False, None
    top = Path(result.stdout.strip())
    try:
        return os.path.samefile(top, root), top
    except OSError:
        return False, top


def require_repo(root):
    same, top = is_repo_root(root)
    if top is None:
        raise SnapError(f"{root} is not a git repository. Run `hx init --git` here (local only, no remote).")
    if not same:
        raise SnapError(f"{root} sits inside another repository ({top}). Snapshots would touch that repository; "
                        f"run hx from {top} or `git init` in the task folder.")


def init_repo(root):
    """Local repository plus a baseline commit of the task exactly as received (tag hx-base)."""
    same, top = is_repo_root(root)
    if top is not None and not same:
        return f"already inside a git repository ({top}); not initialising another"
    created = top is None
    if created:
        git(root, "init")
    if git(root, "rev-parse", "--verify", "hx-base", check=False).returncode == 0:
        return "git: baseline hx-base already exists"
    has_head = git(root, "rev-parse", "--verify", "HEAD", check=False).returncode == 0
    if has_head and not created:
        git(root, "tag", "hx-base")
        return "git: existing repository kept as is; current commit tagged hx-base (nothing committed)"
    head, staged = commit_all(root, "[hx-base] task as received")
    git(root, "tag", "hx-base")
    return f"git: repository initialised, baseline commit {head} ({len(staged)} file(s)) tagged hx-base (local only, no remote)"


def _identity(root):
    """Per-command identity when none is configured; never writes git config."""
    if git(root, "config", "user.name", check=False).stdout.strip() and git(root, "config", "user.email", check=False).stdout.strip():
        return []
    return ["-c", "user.name=hx", "-c", "user.email=hx@localhost"]


def _protect(root):
    """Keep dependency folders and huge data files out of snapshots via .git/info/exclude (local, untracked)."""
    exclude = Path(root) / ".git" / "info" / "exclude"
    exclude.parent.mkdir(parents=True, exist_ok=True)
    current = exclude.read_text(encoding="utf-8", errors="replace") if exclude.is_file() else ""
    wanted = [pattern for pattern in EXCLUDES if pattern not in current.splitlines()]
    try:  # a kit cloned inside the task folder is a nested repository: never commit it into the task
        inside = "/" + util.KIT.parent.resolve().relative_to(Path(root).resolve()).as_posix() + "/"
        if inside != "/./" and inside not in current.splitlines():
            wanted.append(inside)
    except ValueError:
        pass
    skipped = []
    listing = git(root, "ls-files", "--others", "--exclude-standard", "-z").stdout
    for name in filter(None, listing.split("\0")):
        try:
            if (Path(root) / name).stat().st_size > BIG:
                wanted.append("/" + name)
                skipped.append(name)
        except OSError:
            pass
    if wanted:
        with open(exclude, "a", encoding="utf-8", newline="\n") as handle:
            handle.write(("" if current.endswith("\n") or not current else "\n") + "\n".join(wanted) + "\n")
    return skipped


def tags(root):
    listing = git(root, "tag", "--list", "hx-ok-*", check=False).stdout.split()
    return sorted(listing, key=lambda tag: int(tag.rsplit("-", 1)[1]) if tag.rsplit("-", 1)[1].isdigit() else 0)


def commit_all(root, message):
    """Stage everything that is not excluded and commit it. Returns (short hash or None, staged paths)."""
    require_repo(root)
    require_clean_index(root)
    _protect(root)
    git(root, "add", "-A")
    staged = [line for line in git(root, "diff", "--cached", "--name-only").stdout.splitlines() if line]
    has_head = git(root, "rev-parse", "--verify", "HEAD", check=False).returncode == 0
    if not staged and has_head:
        return None, []
    git(root, *_identity(root), "commit", "--allow-empty", "-m", message)
    return git(root, "rev-parse", "--short", "HEAD").stdout.strip(), staged


def require_clean_index(root):
    """Never absorb a user's pre-existing staged work into an automatic checkpoint."""
    if git(root, "diff", "--cached", "--name-only").stdout.strip():
        raise SnapError("the index already contains staged changes; preserve them and create a scoped Git commit manually")


def snap(root, label="", wip=False):
    require_repo(root)
    state = ledger.compute(root)
    failing = sorted(name for name, value in state["states"].items() if value == "FAIL")
    stale = sorted(name for name, value in state["states"].items() if value == "STALE")
    if not wip and (failing or stale):
        raise SnapError(f"not a verified state: failing={failing} stale={stale}. Run `hx regress` and fix, "
                        f"or save work in progress with `hx snap --wip` (no ok-tag).")
    if not wip and (not state["checks"] or any(value != "PASS" for value in state["states"].values())):
        raise SnapError("no substantive passing evidence for a verified checkpoint; use `hx snap --wip`")
    skipped = _protect(root)
    known = tags(root)
    number = int(known[-1].rsplit("-", 1)[1]) + 1 if known else 1
    must = [item for item in state["items"] if item["kind"] == "MUST" and item["status"] != "dropped"]
    proven = sum(1 for item in must if item["status"] == "done" and state["proof"][item["id"]][0] == "PASS")
    from . import collab
    progress = f" ({collab.phase(root)}, MUST {proven}/{len(must)})"
    message = (f"[hx-wip] {label}".strip() if wip else f"[hx-ok {number}] {label}".strip()) + progress
    _, staged = commit_all(root, message)
    head = git(root, "rev-parse", "--short", "HEAD").stdout.strip()
    lines = [f"SNAP: {'wip commit' if wip else f'hx-ok-{number}'} at {head} ({message})"]
    if staged:
        lines.append(f"  committed {len(staged)} file(s): {', '.join(staged[:12])}" + (" ..." if len(staged) > 12 else ""))
    else:
        lines.append("  nothing new to commit; the checkpoint points at the existing commit")
    if not wip:
        git(root, "tag", f"hx-ok-{number}")
        if not state["checks"]:
            lines.append("  note: no checks exist yet, so this checkpoint is not backed by any test evidence")
    if skipped:
        lines.append(f"  note: {len(skipped)} file(s) over 25 MB left out of the snapshot: {skipped[:5]}")
    return "\n".join(lines)


def back(root, to=None, yes=False):
    require_repo(root)
    known = tags(root)
    target = to or (known[-1] if known else None)
    if not target:
        raise SnapError("no hx-ok checkpoint exists yet (create one with `hx snap`)")
    if git(root, "rev-parse", "--verify", f"{target}^{{commit}}", check=False).returncode:
        raise SnapError(f"unknown checkpoint {target!r}; available: {known}")
    dirty = git(root, "status", "--porcelain").stdout.strip()
    ahead = git(root, "rev-list", "--count", f"{target}..HEAD").stdout.strip()
    branch = f"hx-abandoned-{time.strftime('%H%M%S')}"
    plan = (f"BACK plan: return the working tree to {target}; {ahead} later commit(s) and "
            f"{len(dirty.splitlines())} uncommitted change(s) will be preserved on branch {branch}")
    if not yes:
        return plan + "\n  dry run only. Re-run with --yes to do it."
    _protect(root)
    if dirty:
        git(root, "add", "-A")
        git(root, *_identity(root), "commit", "-m", f"[hx-abandoned] state before returning to {target}")
    git(root, "branch", branch)
    git(root, "reset", "--hard", target)
    return (plan.replace("BACK plan:", "BACK done:") +
            f"\n  recover anything from it with: git checkout {branch} -- <path>"
            f"\n  proofs are now stale by design: run `hx regress` before trusting this state")
