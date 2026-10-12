"""meta.json, group keys, caller context, and the rows a group renders.

Every reader here tolerates a missing or malformed meta.json and never raises.
"""
import datetime
import hashlib
import json
import os
import pathlib
import subprocess
import sys

STATES = ("agreed", "pending", "open", "dropped")
DEFAULT_STATE = "pending"


def run_git(args, cwd):
    """git's stdout, stripped, or "" on any failure."""
    try:
        out = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)
        return out.stdout.strip()
    except (subprocess.CalledProcessError, OSError):
        return ""


def slug(text):
    """Lowercase, [a-z0-9] only, other runs collapse to one "-", 40 chars max."""
    out = []
    dash = True  # seeded true so a leading non-alnum run never emits a leading "-"
    for ch in text.lower():
        if ch.isascii() and ch.isalnum():
            out.append(ch)
            dash = False
        elif not dash:
            out.append("-")
            dash = True
    result = "".join(out).strip("-")
    if len(result) > 40:
        result = result[:40].rstrip("-")
    return result or "untitled"


def group_key(session, title):
    """<session-slug>--<title-slug>--<8 hex>. The hex is a stable hash of session and title,
    so re-running init with the same title in the same checkout resumes the group."""
    digest = hashlib.sha1((session + "\x00" + title).encode("utf-8")).hexdigest()[:8]
    return f"{slug(session)}--{slug(title)}--{digest}"


def caller_context(cwd):
    """session, workspace, repo, repo_path and branch, from the caller's cwd only.

    session   - basename of the checkout the caller stands in (git's toplevel).
    repo      - basename of the main checkout, resolved through a linked worktree via git's
                common dir, so every worktree of one repo agrees on it.
    repo_path - absolute path of that main checkout; "" outside git.
    workspace - "main" when the caller's checkout is the main checkout, else the session.
    branch    - the current branch; "" outside git or on a detached HEAD.
    """
    toplevel = run_git(["rev-parse", "--show-toplevel"], cwd)
    if not toplevel:
        name = pathlib.Path(cwd).name
        return {"session": name, "workspace": "main", "repo": name, "repo_path": "", "branch": ""}

    session = pathlib.Path(toplevel).name
    git_dir = run_git(["rev-parse", "--path-format=absolute", "--git-dir"], cwd)
    common_dir = run_git(["rev-parse", "--path-format=absolute", "--git-common-dir"], cwd)
    repo_root = pathlib.Path(common_dir).parent if common_dir else pathlib.Path(toplevel)
    is_linked_worktree = bool(git_dir) and bool(common_dir) and git_dir != common_dir
    return {
        "session": session,
        "workspace": session if is_linked_worktree else "main",
        "repo": repo_root.name,
        "repo_path": str(repo_root),
        "branch": run_git(["branch", "--show-current"], cwd),
    }


def load_meta(folder):
    """(meta, ok). meta is {} when meta.json is missing or malformed; ok is False only when
    the file exists but cannot be used, so callers know not to overwrite it."""
    path = pathlib.Path(folder) / "meta.json"
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}, True
    except OSError as exc:
        print(f"artboards: cannot read {path}: {exc}", file=sys.stderr, flush=True)
        return {}, False
    try:
        meta = json.loads(text)
    except ValueError as exc:
        print(f"artboards: bad meta.json in {pathlib.Path(folder).name}: {exc}", file=sys.stderr, flush=True)
        return {}, False
    if not isinstance(meta, dict):
        print(f"artboards: meta.json in {pathlib.Path(folder).name} is not an object", file=sys.stderr, flush=True)
        return {}, False
    return meta, True


def read_meta(folder):
    return load_meta(folder)[0]


def write_meta(folder, meta):
    """Write through a temp file and rename, so a reader never sees half a file."""
    path = pathlib.Path(folder) / "meta.json"
    tmp = path.with_name(f".meta.json.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(value):
    """A timezone-aware datetime, or None. A naive value is read as UTC."""
    if not isinstance(value, str) or not value:
        return None
    try:
        dt = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=datetime.timezone.utc)


def mtime(path):
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def board_files(folder):
    """Every artboard file in a group folder, alphabetical. index.html is not an artboard."""
    try:
        files = [p for p in pathlib.Path(folder).glob("*.html") if p.name != "index.html" and p.is_file()]
    except OSError:
        return []
    return sorted(files, key=lambda p: p.name.lower())


def stem(path):
    """Main.dc.html -> Main"""
    return path.name[: -len(".dc.html")] if path.name.endswith(".dc.html") else path.stem


def board_rows(folder, meta):
    """The rows a group renders, dropped included: listed files in array order, then any file
    on disk that meta does not list, as pending. A listed file missing on disk is skipped."""
    on_disk = {p.name: p for p in board_files(folder)}
    entries = meta.get("artboards")
    if not isinstance(entries, list):
        entries = []

    rows, claimed = [], set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        name = entry.get("file")
        path = on_disk.get(name) if isinstance(name, str) else None
        if path is None or name in claimed:
            continue
        claimed.add(name)
        state = entry.get("state")
        note = entry.get("note")
        rows.append({
            "path": path,
            "title": str(entry.get("title") or stem(path)),
            "state": state if state in STATES else DEFAULT_STATE,
            "note": str(note) if note else "",
            "mtime": mtime(path),
        })
    for name, path in on_disk.items():
        if name not in claimed:
            rows.append({"path": path, "title": stem(path), "state": DEFAULT_STATE, "note": "", "mtime": mtime(path)})
    return rows


def state_counts(rows):
    """'1 open, 2 pending' in STATES order, dropped left out."""
    counts = {state: 0 for state in STATES if state != "dropped"}
    for row in rows:
        if row["state"] in counts:
            counts[row["state"]] += 1
    parts = [f"{n} {state}" for state, n in counts.items() if n]
    return ", ".join(parts) if parts else "no artboards"


def group_folders(root):
    """Group folders (real dirs or symlinks to dirs), sorted by name. Hidden entries skipped.
    os.path.isdir, not Path.is_dir: it is False (not an error) for a target we may not read."""
    try:
        entries = list(pathlib.Path(root).iterdir())
    except OSError as exc:
        print(f"artboards: cannot read {root}: {exc}", file=sys.stderr, flush=True)
        return []
    return sorted((p for p in entries if not p.name.startswith(".") and os.path.isdir(p)), key=lambda p: p.name.lower())


def reopen(meta):
    """Open a closed group again. keep stops tidy from closing it on the same evidence."""
    meta["active"] = True
    meta["keep"] = True
    meta["reopened"] = now_iso()
    meta.pop("closed", None)


def is_active(meta):
    return meta.get("active") is not False


CLOSE_TEXT = {
    "pr-merged": "PR merged",
    "all-agreed": "all agreed",
    "idle": "no change for 7 days",
    "by-hand": "closed by hand",
}


def close_text(meta):
    """The reason a closed group was closed, as plain text."""
    closed = meta.get("closed")
    if not isinstance(closed, dict):
        return "closed"
    detail = closed.get("detail")
    if isinstance(detail, str) and detail:
        return detail
    return CLOSE_TEXT.get(closed.get("reason"), "closed")
