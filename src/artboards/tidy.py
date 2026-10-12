"""Close groups that no longer need review, and remove dead group folders.

A group with active != false is closed by the FIRST rule that matches:
  1. pr-merged  - its branch has a merged PR, merged after the group was created
  2. all-agreed - every artboard is agreed or dropped
  3. idle       - no artboard file changed for 7 days, and the group was not reopened in that time
keep=true (set by `artboards activate`) skips rules 1 and 2.

Removal: a symlinked group whose target is gone is unlinked; a real group folder with
nothing in it but meta.json, older than a day, is deleted. Nothing else is ever deleted.
A rule that hits an error is skipped; a group is never closed because of an error.
"""
import datetime
import json
import os
import pathlib
import shutil
import subprocess
import sys
import time

from . import meta as m
from . import paths

IDLE_DAYS = 7
EMPTY_DAYS = 1
GH_TIMEOUT = 15
IGNORED_FILES = {"meta.json", ".DS_Store"}


def gh_merged_prs(repo_path, branch):
    """Merged PRs for a head branch as [{"number", "mergedAt"}], or None on any error.
    Tests replace this function."""
    if not shutil.which("gh"):
        return None
    try:
        out = subprocess.run(
            ["gh", "pr", "list", "--head", branch, "--state", "merged",
             "--json", "number,mergedAt", "--limit", "5"],
            cwd=repo_path, capture_output=True, text=True, timeout=GH_TIMEOUT, check=True,
        )
        prs = json.loads(out.stdout)
    except (subprocess.SubprocessError, OSError, ValueError):
        return None
    return prs if isinstance(prs, list) else None


def default_branches(repo_path):
    """The repo's default branch from origin/HEAD, or {main, master} when git cannot say."""
    ref = m.run_git(["symbolic-ref", "--quiet", "refs/remotes/origin/HEAD"], repo_path)
    prefix = "refs/remotes/origin/"
    return {ref[len(prefix):]} if ref.startswith(prefix) else {"main", "master"}


def short_date(dt):
    """12 Oct, in local time."""
    local = dt.astimezone()
    return f"{local.day} {local.strftime('%b')}"


def group_created(meta, files):
    """meta's created time, else the oldest artboard file's mtime, else None."""
    created = m.parse_iso(meta.get("created"))
    if created:
        return created
    times = [t for t in map(m.mtime, files) if t]
    if times:
        return datetime.datetime.fromtimestamp(min(times), datetime.timezone.utc)
    return None


def rule_pr_merged(meta, files, cache):
    repo_path, branch = meta.get("repo_path"), meta.get("branch")
    if not (isinstance(repo_path, str) and repo_path and isinstance(branch, str) and branch):
        return None
    if not pathlib.Path(repo_path).is_dir():
        return None
    created = group_created(meta, files)
    if created is None:
        return None
    key = (repo_path, branch)
    if key not in cache:
        cache[key] = None if branch in default_branches(repo_path) else gh_merged_prs(repo_path, branch)
    merged = []
    for pr in cache[key] or []:
        if not isinstance(pr, dict):
            continue
        at = m.parse_iso(pr.get("mergedAt"))
        if at and at > created and isinstance(pr.get("number"), int):
            merged.append((at, pr["number"]))
    if not merged:
        return None
    at, number = max(merged)
    return f"PR #{number} merged {short_date(at)}"


def rule_all_agreed(rows):
    if rows and all(r["state"] in ("agreed", "dropped") for r in rows):
        return "all agreed"
    return None


def rule_idle(meta, files, now):
    """Measured from the newest artboard file, or from `reopened` when that is later."""
    times = [m.mtime(p) for p in files]
    if not times:
        return None
    reopened = m.parse_iso(meta.get("reopened"))
    last = max(max(times), reopened.timestamp() if reopened else 0)
    if now - last > IDLE_DAYS * 86400:
        return f"no change for {IDLE_DAYS} days"
    return None


def close_reason(meta, folder, now, cache):
    """(reason, detail) of the first rule that matches, or None."""
    files = m.board_files(folder)
    keep = meta.get("keep") is True
    if not keep:
        detail = rule_pr_merged(meta, files, cache)
        if detail:
            return "pr-merged", detail
        detail = rule_all_agreed(m.board_rows(folder, meta))
        if detail:
            return "all-agreed", detail
    detail = rule_idle(meta, files, now)
    if detail:
        return "idle", detail
    return None


def target_missing(link):
    """True when a symlink's target is gone. A target we may not read (EACCES, or macOS privacy
    rules under launchd) is not gone, so its group is never removed."""
    try:
        link.stat()
    except (FileNotFoundError, NotADirectoryError):
        return True
    except OSError:
        return False
    return False


def removal(folder, now):
    """Why a group folder should be removed, or None."""
    if folder.is_symlink():
        return "broken symlink" if target_missing(folder) else None
    if not folder.is_dir():
        return None
    try:
        names = os.listdir(folder)
    except OSError:
        return None
    if any(name not in IGNORED_FILES for name in names):
        return None
    meta_path = folder / "meta.json"
    age_from = m.mtime(meta_path) if meta_path.exists() else m.mtime(folder)
    if age_from and now - age_from > EMPTY_DAYS * 86400:
        return "empty folder"
    return None


def candidates(root):
    """Every non-hidden entry that is a dir, a symlink to a dir, or a broken symlink."""
    try:
        entries = sorted(pathlib.Path(root).iterdir(), key=lambda p: p.name.lower())
    except OSError as exc:
        print(f"artboards: cannot read {root}: {exc}", file=sys.stderr, flush=True)
        return []
    return [p for p in entries if not p.name.startswith(".") and (os.path.isdir(p) or p.is_symlink())]


def run(dry_run=False, root=None, now=None):
    """Apply the rules. Returns (action lines, summary line)."""
    root = pathlib.Path(root or paths.data_dir())
    now = now if now is not None else time.time()
    cache = {}
    lines, closed, removed = [], 0, 0
    for folder in candidates(root):
        try:
            why = removal(folder, now)
            if why:
                if not dry_run:
                    if folder.is_symlink():
                        folder.unlink()
                    else:
                        shutil.rmtree(folder)
                lines.append(f"removed {folder.name}  {why}")
                removed += 1
                continue
            if not os.path.isdir(folder):
                continue
            meta, ok = m.load_meta(folder)
            if not ok or not m.is_active(meta):
                continue
            found = close_reason(meta, folder, now, cache)
            if not found:
                continue
            reason, detail = found
            if not dry_run:
                meta["active"] = False
                meta["closed"] = {"reason": reason, "at": m.now_iso(), "detail": detail}
                m.write_meta(folder, meta)
            lines.append(f"closed  {folder.name}  {detail}")
            closed += 1
        except Exception as exc:  # one bad group never stops the run
            print(f"artboards tidy: skipped {folder.name}: {exc}", file=sys.stderr, flush=True)
    summary = f"tidy: {closed} closed, {removed} removed"
    if dry_run:
        summary += " (dry run, nothing changed)"
    return lines, summary
