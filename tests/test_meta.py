import json
import os
import subprocess

import pytest

from artboards import cli
from artboards import meta as m

# Captured from the standalone CLI this package replaced. Existing groups depend on them.
KEY_VECTORS = [
    ("workspace-1", "Borrow flow", "workspace-1--borrow-flow--18566ef8"),
    ("dotfiles", "Lo-fi journey board prototype", "dotfiles--lo-fi-journey-board-prototype--0dd34565"),
    ("workspace-2", "Search results: empty state", "workspace-2--search-results-empty-state--3e3899b7"),
    ("", "", "untitled--untitled--5ba93c9d"),
    ("Café", "  ---Ünïcode Title!! ", "caf--n-code-title--e62a0dd7"),
    ("tool-app", "Return flow (PR 2)", "tool-app--return-flow-pr-2--eb681777"),
    ("x" * 50, "A very long title that goes beyond forty characters for sure",
     "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx--a-very-long-title-that-goes-beyond-forty--96990a2a"),
]

SLUG_VECTORS = [
    ("Hello World", "hello-world"),
    ("--a--b--", "a-b"),
    ("", "untitled"),
    ("ÄÖÜ", "untitled"),
    ("a" * 45, "a" * 40),
    ("abc-" * 12, "abc-abc-abc-abc-abc-abc-abc-abc-abc-abc"),
]


@pytest.mark.parametrize("session,title,key", KEY_VECTORS)
def test_group_key_is_unchanged(session, title, key):
    assert m.group_key(session, title) == key


@pytest.mark.parametrize("text,expected", SLUG_VECTORS)
def test_slug_is_unchanged(text, expected):
    assert m.slug(text) == expected


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def repos(tmp_path):
    """A main checkout on main, a linked worktree on a feature branch, and a plain folder."""
    main = tmp_path / "tool-app"
    main.mkdir()
    git(main, "init", "-q", "-b", "main")
    git(main, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", "commit", "-q", "--allow-empty", "-m", "x")
    git(main, "worktree", "add", "-q", "-b", "feature/borrow", str(tmp_path / "wt1"))
    (main / "sub").mkdir()
    (tmp_path / "plain").mkdir()
    return tmp_path


def test_caller_context_matches_old_tool(repos):
    main = str((repos / "tool-app").resolve())
    assert m.caller_context(repos / "tool-app") == {
        "session": "tool-app", "workspace": "main", "repo": "tool-app", "repo_path": main, "branch": "main"}
    assert m.caller_context(repos / "tool-app" / "sub") == {
        "session": "tool-app", "workspace": "main", "repo": "tool-app", "repo_path": main, "branch": "main"}
    assert m.caller_context(repos / "wt1") == {
        "session": "wt1", "workspace": "wt1", "repo": "tool-app", "repo_path": main, "branch": "feature/borrow"}


def test_caller_context_outside_git(repos, monkeypatch):
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(repos))
    assert m.caller_context(repos / "plain") == {
        "session": "plain", "workspace": "main", "repo": "plain", "repo_path": "", "branch": ""}


def test_init_writes_new_fields_and_resumes(home, repos, monkeypatch, capsys):
    monkeypatch.chdir(repos / "wt1")
    with pytest.raises(SystemExit) as done:
        cli.main(["init", "Borrow flow"])
    assert done.value.code == 0
    folder = home / m.group_key("wt1", "Borrow flow")
    assert capsys.readouterr().out.strip() == str(folder)
    meta = json.loads((folder / "meta.json").read_text())
    assert list(meta) == ["session", "workspace", "repo", "repo_path", "branch", "title", "created", "active", "artboards"]
    assert meta["repo_path"] == str((repos / "tool-app").resolve())
    assert meta["branch"] == "feature/borrow"
    assert m.parse_iso(meta["created"]) is not None
    assert meta["active"] is True and meta["artboards"] == []

    # init again resumes: it keeps the list, and refreshes meta.json so tidy sees the group in use
    meta["artboards"] = [{"file": "1-a.html", "state": "open"}]
    (folder / "meta.json").write_text(json.dumps(meta))
    os.utime(folder / "meta.json", (1, 1))
    with pytest.raises(SystemExit):
        cli.main(["init", "Borrow flow"])
    assert json.loads((folder / "meta.json").read_text())["artboards"] == meta["artboards"]
    assert (folder / "meta.json").stat().st_mtime > 1

    # init on a closed group opens it again
    meta.update(active=False, closed={"reason": "idle", "at": m.now_iso(), "detail": "no change for 7 days"})
    (folder / "meta.json").write_text(json.dumps(meta))
    with pytest.raises(SystemExit):
        cli.main(["init", "Borrow flow"])
    reopened = json.loads((folder / "meta.json").read_text())
    assert reopened["active"] is True and reopened["keep"] is True and "closed" not in reopened
    assert "reopened" in capsys.readouterr().err


def test_read_meta_tolerates_bad_files(tmp_path):
    assert m.read_meta(tmp_path) == {}
    (tmp_path / "meta.json").write_text("{not json")
    assert m.load_meta(tmp_path) == ({}, False)
    (tmp_path / "meta.json").write_text("[1, 2]")
    assert m.load_meta(tmp_path) == ({}, False)


def test_board_rows_order_states_and_unlisted(tmp_path):
    for name in ("b.html", "a.html", "c.html", "index.html"):
        (tmp_path / name).write_text("x")
    meta = {"artboards": [
        {"file": "b.html", "state": "open", "title": "B"},
        {"file": "gone.html", "state": "agreed"},
        {"file": "a.html", "state": "weird"},
        {"file": "b.html", "state": "agreed"},
        "not a dict",
    ]}
    rows = m.board_rows(tmp_path, meta)
    assert [(r["path"].name, r["state"]) for r in rows] == [("b.html", "open"), ("a.html", "pending"), ("c.html", "pending")]
    assert rows[0]["title"] == "B" and rows[2]["title"] == "c"


def test_archive_and_activate(home, capsys):
    folder = home / "g"
    folder.mkdir()
    (folder / "meta.json").write_text(json.dumps({"title": "G", "active": True}))
    with pytest.raises(SystemExit):
        cli.main(["archive", "g"])
    meta = json.loads((folder / "meta.json").read_text())
    assert meta["active"] is False and meta["closed"]["reason"] == "by-hand"
    assert meta["closed"]["detail"] == "closed by hand"
    with pytest.raises(SystemExit):
        cli.main(["activate", "g"])
    meta = json.loads((folder / "meta.json").read_text())
    assert meta["active"] is True and meta["keep"] is True and "closed" not in meta
    assert m.parse_iso(meta["reopened"]) is not None
    with pytest.raises(SystemExit) as done:
        cli.main(["archive", "nope"])
    assert "no artboards group" in str(done.value.code)


def test_list_lines(home, capsys):
    from conftest import make_group
    make_group(home, "a--one--1", {"title": "One", "artboards": [
        {"file": "1.html", "state": "open"}, {"file": "2.html", "state": "dropped"}]},
        files={"1.html": "x", "2.html": "x", "3.html": "x"})
    make_group(home, "b--two--2", {"title": "Two", "active": False,
                                   "closed": {"reason": "pr-merged", "detail": "PR #4 merged 2 Oct"}},
               files={"1.html": "x"})
    with pytest.raises(SystemExit):
        cli.main(["list"])
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith("active a--one--1") and out[0].endswith("One  (1 pending, 1 open)")
    assert out[1].startswith("closed b--two--2") and out[1].endswith("(1 pending)  PR #4 merged 2 Oct")
