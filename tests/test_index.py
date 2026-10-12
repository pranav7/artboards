import re

from conftest import make_group

from artboards import index


def main_page(home):
    return index.render_main(index.read_groups(home))


def history_page(home):
    return index.render_history(index.read_groups(home))


def group_order(page):
    return re.findall(r'<span class="name">([^<]*)</span>', page)


def test_bands_open_then_pending_then_rest_newest_first(home):
    make_group(home, "agreed-new", {"title": "agreed new", "artboards": [{"file": "a.html", "state": "agreed"}]},
               files={"a.html": "x"}, age_days=0)
    make_group(home, "pending-old", {"title": "pending old", "artboards": [{"file": "a.html", "state": "pending"}]},
               files={"a.html": "x"}, age_days=3)
    make_group(home, "pending-new", {"title": "pending new", "artboards": [{"file": "a.html", "state": "agreed"}]},
               files={"a.html": "x", "unlisted.html": "x"}, age_days=1)
    make_group(home, "open-old", {"title": "open old", "artboards": [
        {"file": "a.html", "state": "agreed"}, {"file": "b.html", "state": "open"}]},
               files={"a.html": "x", "b.html": "x"}, age_days=5)
    make_group(home, "dropped-open", {"title": "dropped open", "artboards": [
        {"file": "a.html", "state": "agreed"}, {"file": "b.html", "state": "dropped"}]},
               files={"a.html": "x", "b.html": "x"}, age_days=0.5)
    assert group_order(main_page(home)) == ["open old", "pending new", "pending old", "agreed new", "dropped open"]


def test_main_hides_closed_and_dropped_history_shows_them(home):
    make_group(home, "live", {"title": "Live", "artboards": [
        {"file": "1.html", "title": "first", "state": "open"},
        {"file": "2.html", "title": "replaced draft", "state": "dropped"}]},
               files={"1.html": "x", "2.html": "x"})
    make_group(home, "done", {"title": "Done", "active": False,
                              "closed": {"reason": "pr-merged", "at": "2026-10-01T10:00:00Z", "detail": "PR #12 merged 1 Oct"},
                              "artboards": [{"file": "1.html", "title": "old one", "state": "dropped"}]},
               files={"1.html": "x"})
    make_group(home, "older", {"title": "Older", "active": False,
                               "closed": {"reason": "idle", "at": "2026-09-01T10:00:00Z"}},
               files={"1.html": "x"})
    main = main_page(home)
    assert group_order(main) == ["Live"]
    assert "replaced draft" not in main
    assert '<a href="/history">2 closed groups</a>' in main

    history = history_page(home)
    assert group_order(history) == ["Done", "Older"]
    assert "PR #12 merged 1 Oct" in history and "no change for 7 days" in history
    assert 'class="row dropped"' in history and "old one" in history
    assert '<a href="/">' in history


def test_note_is_clamped_with_full_text_in_title(home):
    note = "line one. " * 30
    make_group(home, "g", {"title": "G", "artboards": [{"file": "a.html", "state": "open", "note": note}]},
               files={"a.html": "x"})
    page = main_page(home)
    assert f'title="{note}"' in page
    assert f'<span class="note">{note}</span>' in page
    assert "-webkit-line-clamp:2" in index.CSS


def test_state_tokens_are_padded(home):
    make_group(home, "g", {"title": "G", "artboards": [{"file": "a.html", "state": "open"}]}, files={"a.html": "x"})
    assert '<span class="tok st-open">open   </span>' in main_page(home)


def test_html_is_escaped(home):
    make_group(home, "g&<x>", {"title": "<script>alert(1)</script>", "repo": "r\"q", "branch": "a&b",
                               "artboards": [{"file": "a b.html", "title": "<b>", "state": "open", "note": "\"quoted\" <i>"}]},
               files={"a b.html": "x"})
    page = main_page(home)
    assert "<script>alert" not in page and "&lt;script&gt;alert(1)&lt;/script&gt;" in page
    assert "<b>" not in page and "<i>" not in page
    assert 'title="&quot;quoted&quot; &lt;i&gt;"' in page
    assert 'href="/g%26%3Cx%3E/a%20b.html"' in page
    assert "r&quot;q" in page and "a&amp;b" in page


def test_malformed_meta_is_tolerated(home):
    make_group(home, "broken", raw_meta="{nope", files={"a.html": "x"})
    make_group(home, "list-meta", raw_meta="[1]", files={"a.html": "x"})
    make_group(home, "bad-rows", {"title": "Bad rows", "artboards": "not a list"}, files={"a.html": "x"})
    page = main_page(home)
    assert sorted(group_order(page)) == ["Bad rows", "broken", "list-meta"]


def test_empty_state(home):
    make_group(home, "no-files", {"title": "No files"})
    page = main_page(home)
    assert "Nothing to review." in page and "/history" not in page
    assert "No closed groups." in history_page(home)


def test_one_bad_group_is_skipped(home, monkeypatch, capsys):
    make_group(home, "good", {"title": "Good"}, files={"a.html": "x"})
    make_group(home, "bad", {"title": "Bad"}, files={"a.html": "x"})
    real = index.read_group

    def flaky(folder):
        if folder.name == "bad":
            raise RuntimeError("boom")
        return real(folder)

    monkeypatch.setattr(index, "read_group", flaky)
    assert group_order(main_page(home)) == ["Good"]
    assert "skipped bad: boom" in capsys.readouterr().err


def test_page_has_theme_tokens_and_background():
    page = index.render_main([])
    assert "IBM+Plex+Mono" in page
    assert "@media (prefers-color-scheme: dark)" in page
    assert re.search(r"body\{[^}]*background:var\(--ground\)", page)
    assert chr(0x2014) not in page  # no em dashes
