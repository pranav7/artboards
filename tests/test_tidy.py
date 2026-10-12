import json
import os

import pytest
from conftest import age, make_group

from artboards import tidy


@pytest.fixture
def gh(monkeypatch):
    """Fake gh: maps a branch to the PR list it returns (None = an error). Records calls."""
    answers, calls = {}, []

    def fake(repo_path, branch):
        calls.append((repo_path, branch))
        return answers.get(branch, [])

    monkeypatch.setattr(tidy, "gh_merged_prs", fake)
    fake.answers, fake.calls = answers, calls
    return fake


def meta_of(folder):
    return json.loads((folder / "meta.json").read_text())


def git_meta(repo, branch="feature/x", **extra):
    return {"title": "T", "repo_path": str(repo), "branch": branch, "created": "2026-10-01T12:00:00Z",
            "artboards": [{"file": "a.html", "state": "open"}], **extra}


def test_pr_merged_after_created_closes(home, tmp_path, gh):
    gh.answers["feature/x"] = [{"number": 7, "mergedAt": "2026-09-01T00:00:00Z"},
                               {"number": 12, "mergedAt": "2026-10-05T10:00:00Z"}]
    folder = make_group(home, "g", git_meta(tmp_path), files={"a.html": "x"})
    lines, summary = tidy.run(root=home)
    assert lines == ["closed  g  PR #12 merged 5 Oct"]
    assert summary == "tidy: 1 closed, 0 removed"
    meta = meta_of(folder)
    assert meta["active"] is False
    assert meta["closed"]["reason"] == "pr-merged" and meta["closed"]["detail"] == "PR #12 merged 5 Oct"
    assert meta["title"] == "T"  # the rest of meta is kept


def test_merged_before_created_does_not_close(home, tmp_path, gh):
    gh.answers["feature/x"] = [{"number": 7, "mergedAt": "2026-09-30T00:00:00Z"}]
    folder = make_group(home, "g", git_meta(tmp_path), files={"a.html": "x"})
    assert tidy.run(root=home)[0] == []
    assert meta_of(folder).get("active") is not False


def test_created_falls_back_to_oldest_file(home, tmp_path, gh):
    gh.answers["feature/x"] = [{"number": 3, "mergedAt": "2000-01-01T00:00:00Z"}]
    meta = git_meta(tmp_path)
    del meta["created"]
    make_group(home, "g", meta, files={"a.html": "x"})
    assert tidy.run(root=home)[0] == []


def test_gh_error_never_closes(home, tmp_path, gh):
    gh.answers["feature/x"] = None
    make_group(home, "g", git_meta(tmp_path), files={"a.html": "x"})
    assert tidy.run(root=home)[0] == []


def test_default_branch_and_missing_fields_skip_gh(home, tmp_path, gh):
    make_group(home, "on-main", git_meta(tmp_path, branch="main"), files={"a.html": "x"})
    make_group(home, "on-master", git_meta(tmp_path, branch="master"), files={"a.html": "x"})
    make_group(home, "no-repo", git_meta(tmp_path, repo_path=""), files={"a.html": "x"})
    make_group(home, "gone-repo", git_meta(tmp_path / "gone"), files={"a.html": "x"})
    legacy = git_meta(tmp_path)
    del legacy["repo_path"]
    make_group(home, "legacy", legacy, files={"a.html": "x"})
    assert tidy.run(root=home)[0] == []
    assert gh.calls == []


def test_gh_results_are_cached_per_repo_and_branch(home, tmp_path, gh):
    make_group(home, "g1", git_meta(tmp_path), files={"a.html": "x"})
    make_group(home, "g2", git_meta(tmp_path), files={"a.html": "x"})
    tidy.run(root=home)
    assert gh.calls == [(str(tmp_path), "feature/x")]


def test_all_agreed_closes(home, gh):
    folder = make_group(home, "g", {"artboards": [
        {"file": "a.html", "state": "agreed"}, {"file": "b.html", "state": "dropped"}]},
                        files={"a.html": "x", "b.html": "x"})
    assert tidy.run(root=home)[0] == ["closed  g  all agreed"]
    assert meta_of(folder)["closed"]["reason"] == "all-agreed"


def test_unlisted_file_blocks_all_agreed(home, gh):
    make_group(home, "g", {"artboards": [{"file": "a.html", "state": "agreed"}]},
               files={"a.html": "x", "new.html": "x"})
    assert tidy.run(root=home)[0] == []


def test_idle_closes(home, gh):
    folder = make_group(home, "g", {"artboards": [{"file": "a.html", "state": "open"}]},
                        files={"a.html": "x"}, age_days=8)
    assert tidy.run(root=home)[0] == ["closed  g  no change for 7 days"]
    assert meta_of(folder)["closed"]["reason"] == "idle"


def test_first_matching_rule_wins(home, tmp_path, gh):
    gh.answers["feature/x"] = [{"number": 2, "mergedAt": "2026-10-05T10:00:00Z"}]
    meta = git_meta(tmp_path)
    meta["artboards"][0]["state"] = "agreed"
    make_group(home, "g", meta, files={"a.html": "x"}, age_days=30)
    assert tidy.run(root=home)[0] == ["closed  g  PR #2 merged 5 Oct"]


def test_keep_skips_rules_one_and_two_not_idle(home, tmp_path, gh):
    gh.answers["feature/x"] = [{"number": 2, "mergedAt": "2026-10-05T10:00:00Z"}]
    meta = git_meta(tmp_path, keep=True)
    meta["artboards"][0]["state"] = "agreed"
    make_group(home, "kept", meta, files={"a.html": "x"})
    make_group(home, "kept-idle", git_meta(tmp_path, keep=True), files={"a.html": "x"}, age_days=8)
    assert tidy.run(root=home)[0] == ["closed  kept-idle  no change for 7 days"]


def test_closed_groups_are_left_alone(home, gh):
    folder = make_group(home, "g", {"active": False, "artboards": [{"file": "a.html", "state": "agreed"}]},
                        files={"a.html": "x"}, age_days=30)
    before = (folder / "meta.json").read_text()
    assert tidy.run(root=home)[0] == []
    assert (folder / "meta.json").read_text() == before


def test_malformed_meta_is_never_overwritten(home, gh):
    folder = make_group(home, "g", raw_meta="{broken", files={"a.html": "x"}, age_days=30)
    assert tidy.run(root=home)[0] == []
    assert (folder / "meta.json").read_text() == "{broken"


def test_broken_symlink_is_unlinked(home, tmp_path, gh):
    target = tmp_path / "elsewhere"
    target.mkdir()
    (home / "linked").symlink_to(target)
    target.rmdir()
    assert tidy.run(root=home)[0] == ["removed linked  broken symlink"]
    assert not os.path.lexists(home / "linked")


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads any folder")
def test_unreadable_symlink_target_is_kept(home, tmp_path, gh):
    """A target we may not read (macOS privacy rules under launchd) is not a broken symlink."""
    from artboards import index
    locked = tmp_path / "locked"
    (locked / "docs").mkdir(parents=True)
    (locked / "docs" / "a.html").write_text("x")
    (home / "linked").symlink_to(locked / "docs")
    make_group(home, "g", {"title": "Readable"}, files={"a.html": "x"})
    locked.chmod(0)
    try:
        assert tidy.run(root=home)[0] == []
        assert os.path.lexists(home / "linked")
        assert [g["key"] for g in index.read_groups(home)] == ["g"]
    finally:
        locked.chmod(0o755)


def test_empty_folder_removal(home, gh):
    old = make_group(home, "old-empty", {"title": "x"})
    age(old / "meta.json", 2)
    fresh = make_group(home, "new-empty", {"title": "x"})
    bare = home / "bare"
    bare.mkdir()
    age(bare, 2)
    pngs = make_group(home, "old-pngs", {"title": "x"}, files={"shot.png": "x"}, age_days=30)
    age(pngs / "meta.json", 30)
    lines, _ = tidy.run(root=home)
    assert sorted(lines) == ["removed bare  empty folder", "removed old-empty  empty folder"]
    assert not old.exists() and not bare.exists()
    assert fresh.exists() and pngs.exists()


def test_empty_symlinked_folder_is_kept(home, tmp_path, gh):
    target = tmp_path / "docs"
    target.mkdir()
    (target / "meta.json").write_text("{}")
    age(target / "meta.json", 5)
    (home / "linked").symlink_to(target)
    assert tidy.run(root=home)[0] == []
    assert (target / "meta.json").exists()


def test_dry_run_changes_nothing(home, tmp_path, gh):
    target = tmp_path / "elsewhere"
    target.mkdir()
    (home / "linked").symlink_to(target)
    target.rmdir()
    old = make_group(home, "old-empty", {"title": "x"})
    age(old / "meta.json", 2)
    idle = make_group(home, "idle", {"artboards": [{"file": "a.html", "state": "open"}]},
                      files={"a.html": "x"}, age_days=8)
    before = (idle / "meta.json").read_text()
    lines, summary = tidy.run(dry_run=True, root=home)
    assert len(lines) == 3
    assert summary == "tidy: 1 closed, 2 removed (dry run, nothing changed)"
    assert os.path.lexists(home / "linked") and old.exists()
    assert (idle / "meta.json").read_text() == before


def test_cli_tidy_prints_lines_and_summary(home, gh, capsys):
    from artboards import cli
    make_group(home, "g", {"artboards": [{"file": "a.html", "state": "agreed"}]}, files={"a.html": "x"})
    with pytest.raises(SystemExit):
        cli.main(["tidy", "--dry-run"])
    assert capsys.readouterr().out == "closed  g  all agreed\ntidy: 1 closed, 0 removed (dry run, nothing changed)\n"


def test_real_gh_function_returns_none_without_gh(monkeypatch, tmp_path):
    monkeypatch.setenv("PATH", str(tmp_path))
    assert tidy.gh_merged_prs(str(tmp_path), "feature/x") is None


def test_real_gh_function_parses_fake_gh(monkeypatch, tmp_path):
    fake = tmp_path / "gh"
    fake.write_text('#!/bin/sh\necho \'[{"number": 9, "mergedAt": "2026-10-05T10:00:00Z"}]\'\n')
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")
    assert tidy.gh_merged_prs(str(tmp_path), "feature/x") == [{"number": 9, "mergedAt": "2026-10-05T10:00:00Z"}]
    fake.write_text("#!/bin/sh\nexit 1\n")
    assert tidy.gh_merged_prs(str(tmp_path), "feature/x") is None


def test_activate_resets_the_idle_clock(home, gh, monkeypatch):
    from artboards import cli
    folder = make_group(home, "g", {"active": False, "closed": {"reason": "idle"},
                                    "artboards": [{"file": "a.html", "state": "open"}]},
                        files={"a.html": "x"}, age_days=30)
    with pytest.raises(SystemExit):
        cli.main(["activate", "g"])
    reopened = meta_of(folder)["reopened"]
    assert tidy.run(root=home)[0] == []
    assert meta_of(folder)["active"] is True

    later = tidy.m.parse_iso(reopened).timestamp() + 8 * 86400
    assert tidy.run(root=home, now=later)[0] == ["closed  g  no change for 7 days"]
    assert meta_of(folder)["closed"]["reason"] == "idle"
