"""The artboards command line. Run `artboards -h`."""
import argparse
import os
import sys
import urllib.error
import urllib.request

from . import meta as m
from . import paths
from .index import plural


def group_dir(key):
    folder = paths.data_dir() / key
    if not key or key.startswith(".") or "/" in key or not folder.is_dir():
        sys.exit(f"no artboards group {key!r}")
    return folder


def cmd_init(args):
    ctx = m.caller_context(os.getcwd())
    folder = paths.data_dir() / m.group_key(ctx["session"], args.title)
    if not folder.exists():
        folder.mkdir(parents=True)
        m.write_meta(folder, {**ctx, "title": args.title, "created": m.now_iso(), "active": True, "artboards": []})
    else:
        meta, ok = m.load_meta(folder)
        if ok:
            if not m.is_active(meta):
                m.reopen(meta)
                print(f"reopened {folder.name}", file=sys.stderr)
            # Rewriting marks the group as in use, so tidy does not remove it before the first artboard.
            m.write_meta(folder, meta)
    print(folder)


def cmd_list(args):
    folders = m.group_folders(paths.data_dir())
    if not folders:
        print("no artboards groups")
        return
    for folder in folders:
        meta = m.read_meta(folder)
        active = m.is_active(meta)
        line = (f"{'active' if active else 'closed':<6} {folder.name:<58} {meta.get('title') or folder.name}"
                f"  ({m.state_counts(m.board_rows(folder, meta))})")
        if not active:
            line += f"  {m.close_text(meta)}"
        print(line)


def server_code(port):
    """The HTTP code the server answers / with, or None when nothing answers."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=2) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except (urllib.error.URLError, OSError):
        return None


def cmd_status(args):
    port = paths.port()
    print(f"data dir: {paths.data_dir()}")
    print(f"repo:     {paths.REPO_ROOT}")
    print(f"kit dir:  {paths.KIT_DIR}")
    code = server_code(port)
    if code is None:
        print(f"server:   down, nothing answers on port {port}. Start it with `artboards serve`.")
    else:
        print(f"server:   up on http://localhost:{port}/ (HTTP {code})")


def cmd_serve(args):
    from . import server

    paths.data_dir().mkdir(parents=True, exist_ok=True)
    server.serve()


def cmd_archive(args):
    folder = group_dir(args.key)
    meta = m.read_meta(folder)
    meta["active"] = False
    meta["closed"] = {"reason": "by-hand", "at": m.now_iso(), "detail": "closed by hand"}
    m.write_meta(folder, meta)
    print(f"closed {args.key}")


def cmd_activate(args):
    folder = group_dir(args.key)
    meta = m.read_meta(folder)
    m.reopen(meta)
    m.write_meta(folder, meta)
    print(f"activated {args.key}")


def cmd_tidy(args):
    from . import tidy

    lines, summary = tidy.run(dry_run=args.dry_run)
    for line in lines:
        print(line)
    print(summary)


def cmd_guide(args):
    path = paths.KIT_DIR / "reference.md" if args.mode == "lofi" else paths.SKILL_DIR / "hifi.md"
    try:
        sys.stdout.write(path.read_text(encoding="utf-8"))
    except OSError:
        sys.exit(f"cannot read {path}")


def cmd_check(args):
    from . import browser

    missing = [f for f in args.files if not os.path.isfile(f)]
    if missing:
        sys.exit(f"no such file: {', '.join(missing)}")
    failed = False
    for path, problems in browser.check(args.files).items():
        for p in problems:
            print(f"{p['level']:<6} {p['message']}")
        errors = sum(p["level"] == "error" for p in problems)
        warns = sum(p["level"] == "warn" for p in problems)
        print(f"{os.path.basename(path)}: {plural(errors, 'error')}, {plural(warns, 'warning')}")
        failed = failed or errors > 0
    return 1 if failed else 0


def cmd_shot(args):
    from . import browser

    try:
        out = browser.shot(args.file, dark=args.dark, width=args.width, out=args.output)
    except FileNotFoundError as exc:
        sys.exit(str(exc))
    print(out)


def cmd_export(args):
    from . import browser

    if not os.path.isfile(args.file):
        sys.exit(f"no such file: {args.file}")
    try:
        out = browser.export(args.file, out=args.output)
    except (OSError, ValueError) as exc:
        sys.exit(str(exc))
    print(out)


def parser():
    p = argparse.ArgumentParser(
        prog="artboards",
        description="Local HTML artboards for UI design reviews: lo-fi journey boards and hi-fi screens.")
    sub = p.add_subparsers(dest="command", metavar="<command>", required=True)

    s = sub.add_parser("init", help="create or resume the group for this checkout; prints its folder")
    s.add_argument("title", help="the group title, for example \"Borrow flow\"")
    s.set_defaults(func=cmd_init)

    s = sub.add_parser("list", help="one line per group")
    s.set_defaults(func=cmd_list)

    s = sub.add_parser("status", help="show the data dir, the kit dir, and whether the server is up")
    s.set_defaults(func=cmd_status)

    s = sub.add_parser("serve", help="run the server in the foreground")
    s.set_defaults(func=cmd_serve)

    s = sub.add_parser("archive", help="close a group by hand")
    s.add_argument("key", help="the group key, as `artboards list` shows it")
    s.set_defaults(func=cmd_archive)

    s = sub.add_parser("activate", help="open a closed group again and keep it open")
    s.add_argument("key", help="the group key, as `artboards list` shows it")
    s.set_defaults(func=cmd_activate)

    s = sub.add_parser("tidy", help="close groups that are done; remove dead folders")
    s.add_argument("--dry-run", action="store_true", help="print what would change, change nothing")
    s.set_defaults(func=cmd_tidy)

    s = sub.add_parser("guide", help="print the lo-fi tag reference or the hi-fi guide")
    s.add_argument("mode", nargs="?", choices=("lofi", "hifi"), default="lofi")
    s.set_defaults(func=cmd_guide)

    s = sub.add_parser("check", help="check boards for problems; exit 1 on any error")
    s.add_argument("files", nargs="+", metavar="file")
    s.set_defaults(func=cmd_check)

    s = sub.add_parser("shot", help="save a full-page PNG of a board")
    s.add_argument("file", help="the board; add #journey=N to pin a journey")
    s.add_argument("--dark", action="store_true", help="use the dark color scheme")
    s.add_argument("--width", type=int, default=1600, help="viewport width in px (default 1600)")
    s.add_argument("-o", "--output", help="PNG path (default: next to the board)")
    s.set_defaults(func=cmd_shot)

    s = sub.add_parser("export", help="write one self-contained HTML file with the kit inlined")
    s.add_argument("file")
    s.add_argument("-o", "--output", help="HTML path (default: <name>.export.html next to it)")
    s.set_defaults(func=cmd_export)
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    sys.exit(args.func(args) or 0)
