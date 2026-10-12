"""check, shot and export in headless Chromium. Boards and fixtures come from the kit side of
the repo; a test skips when its file is not there yet."""
import re
import shutil

import pytest
from conftest import EXAMPLE_BOARD, FIXTURES, require

from artboards import browser, paths

LOFI_ERRORS = ["unknown-tag", "misplaced-tag", "duplicate-id", "missing-id", "no-link", "ambiguous-step", "cell-taken",
               "overlap", "overflow", "arrow-crosses-screen"]
LOFI_WARNS = ["label-overlap", "unreached-screen", "screen-not-in-journey", "two-primaries"]


@pytest.fixture(scope="module")
def chrome():
    with browser.chromium() as b:
        yield b


def codes(problems, level=None):
    return {p["code"] for p in problems if level is None or p["level"] == level}


def errors(problems):
    return [p for p in problems if p["level"] == "error"]


def test_clean_board_has_no_errors(chrome):
    problems = browser.check_page(chrome, require(FIXTURES / "lofi-clean.html"))
    assert errors(problems) == []


def test_example_board_has_no_errors(chrome):
    problems = browser.check_page(chrome, require(EXAMPLE_BOARD))
    assert errors(problems) == []


@pytest.mark.parametrize("code", LOFI_ERRORS)
def test_broken_board_yields_its_error(chrome, code):
    problems = browser.check_page(chrome, require(FIXTURES / f"lofi-{code}.html"))
    assert code in codes(problems, "error"), problems
    assert codes(problems, "error") == {code}, problems


@pytest.mark.parametrize("code", LOFI_WARNS)
def test_broken_board_yields_its_warning(chrome, code):
    problems = browser.check_page(chrome, require(FIXTURES / f"lofi-{code}.html"))
    assert code in codes(problems, "warn"), problems
    assert errors(problems) == [], problems


def test_open_questions_info(chrome):
    problems = browser.check_page(chrome, require(EXAMPLE_BOARD))
    if "wf-question" not in EXAMPLE_BOARD.read_text():
        pytest.skip("the example board has no open questions")
    info = [p for p in problems if p["code"] == "open-questions"]
    assert info and info[0]["level"] == "info" and re.fullmatch(r"\d+ open questions?", info[0]["message"])


def test_hifi_clean(chrome):
    assert errors(browser.check_page(chrome, require(FIXTURES / "hifi-clean.html"))) == []


@pytest.mark.parametrize("code", ["dark-only-token", "transparent-body"])
def test_hifi_fixture_yields_its_error(chrome, code):
    problems = browser.check_page(chrome, require(FIXTURES / f"hifi-{code}.html"))
    assert codes(problems, "error") == {code}, problems


# Hi-fi checks against pages written here, so they run without the kit side.

def hifi(tmp_path, css, body="<p>hi</p>"):
    path = tmp_path / "page.html"
    path.write_text(f"<!doctype html><html><head><style>{css}</style></head><body>{body}</body></html>")
    return path


def test_hifi_checks_inline(chrome, tmp_path):
    good = ":root{--bg:#fff} @media (prefers-color-scheme: dark){:root{--bg:#000}} body{background:var(--bg)}"
    assert browser.check_page(chrome, hifi(tmp_path, good)) == []

    dark_only = (":root{--bg:#fff} @media (prefers-color-scheme: dark){:root{--bg:#000; --line:#333}}"
                 " body{background:var(--bg)}")
    problems = browser.check_page(chrome, hifi(tmp_path, dark_only))
    assert [(p["code"], p["message"]) for p in problems] == [
        ("dark-only-token", "token --line is set for dark mode only; set it on :root too")]

    assert codes(browser.check_page(chrome, hifi(tmp_path, "p{color:red}"))) == {"transparent-body"}


def test_hifi_overflow_warn(chrome, tmp_path):
    css = "body{background:#fff} .box{width:40px; white-space:nowrap}"
    problems = browser.check_page(chrome, hifi(tmp_path, css, '<div class="box">a long line of text here</div>'))
    assert [(p["level"], p["code"]) for p in problems] == [("warn", "overflow")]
    assert problems[0]["message"].startswith('div.box "a long line of text here" overflows its box by')


def test_console_error_is_an_error(chrome, tmp_path):
    path = hifi(tmp_path, "body{background:#fff}", "<script>console.error('bad thing'); null.x</script>")
    problems = browser.check_page(chrome, path)
    assert [p["code"] for p in problems] == ["console-error", "console-error"]
    assert any("bad thing" in p["message"] for p in problems)


def test_board_without_kit_reports_kit_missing(chrome, tmp_path):
    path = tmp_path / "board.html"
    path.write_text("<!doctype html><body><wf-board name='x'></wf-board></body>")
    assert codes(browser.check_page(chrome, path)) == {"kit-missing"}


def test_shot_writes_png(chrome, tmp_path):
    board = tmp_path / "board.html"
    if EXAMPLE_BOARD.exists():
        shutil.copy(EXAMPLE_BOARD, board)
    else:
        board.write_text("<!doctype html><body style='background:#fff'><h1>hi</h1></body>")
    out = browser.shot(str(board), browser=chrome)
    assert out == tmp_path / "board.png" and out.stat().st_size > 1000
    assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    dark = browser.shot(f"{board}#journey=2", dark=True, width=800, browser=chrome)
    assert dark == tmp_path / "board-journey-2-dark.png" and dark.stat().st_size > 1000


def test_shot_names():
    from pathlib import Path
    assert browser.shot_path(Path("a/b.html"), "", False) == Path("a/b.png")
    assert browser.shot_path(Path("a/b.html"), "", True) == Path("a/b-dark.png")
    assert browser.shot_path(Path("a/b.html"), "journey=3", False) == Path("a/b-journey-3.png")
    assert browser.split_hash("x/b.html#journey=3") == (Path("x/b.html"), "journey=3")


def test_export_inlines_kit_and_checks_clean_without_routing(chrome, tmp_path):
    require(paths.KIT_DIR / "lofi.js")
    board = tmp_path / "board.html"
    shutil.copy(require(EXAMPLE_BOARD), board)
    out = browser.export(board)
    assert out == tmp_path / "board.export.html"
    text = out.read_text()
    assert "/_kit/" not in text
    assert "<style>" in text and "<script>" in text
    assert errors(browser.check_page(chrome, out, route=False)) == []


def test_export_with_fake_kit(tmp_path, monkeypatch):
    kit = tmp_path / "kit"
    kit.mkdir()
    (kit / "lofi.css").write_text("wf-board{display:block}")
    (kit / "lofi.js").write_text("const s = '</script>'; window.wf = {};")
    monkeypatch.setattr(paths, "KIT_DIR", kit)
    board = tmp_path / "b.html"
    board.write_text('<head><link rel="stylesheet" href="/_kit/lofi.css">\n<script src="/_kit/lofi.js"></script></head>'
                     '<body><wf-board name="x"></wf-board></body>')
    text = browser.export(board, out=tmp_path / "out.html").read_text()
    assert "/_kit/" not in text
    assert "<style>\nwf-board{display:block}\n</style>" in text
    assert "const s = '<\\/script>'; window.wf = {};" in text


def test_export_copies_hifi_unchanged(tmp_path):
    page = tmp_path / "hifi.html"
    page.write_text("<!doctype html><body style='background:#fff'>x</body>")
    assert browser.export(page).read_text() == page.read_text()


def test_kit_reference_in_sync(chrome):
    """Tags registered in lofi.js (window.wf.tags) equal the tags documented in reference.md."""
    reference = require(paths.KIT_DIR / "reference.md").read_text()
    require(paths.KIT_DIR / "lofi.js")
    documented = re.findall(r"^\|\s*`(wf-[a-z0-9-]+)`", reference, flags=re.M)
    assert documented, "reference.md documents no tags"
    page = browser.open_page(chrome, require(FIXTURES / "lofi-clean.html"))
    registered = page.evaluate("() => window.wf && window.wf.tags")
    page.close()
    assert registered, "lofi.js does not expose window.wf.tags"
    assert sorted(set(registered)) == sorted(set(documented))
    assert len(documented) == len(set(documented)), "a tag is documented twice"


def test_kit_failure_is_one_error(chrome):
    problems = browser.check_page(chrome, require(FIXTURES / "lofi-kit-error.html"), route=False)
    assert [p["code"] for p in problems] == ["kit-error"], problems
