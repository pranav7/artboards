"""The click-through kit in headless Chromium: its checks, its moves, and shot."""
import re
import struct

import pytest
from conftest import FIXTURES, REPO, require

from artboards import browser, paths

CT_ERRORS = ["unknown-tag", "misplaced-tag", "missing-id", "duplicate-id", "missing-step", "base-loop",
             "unreached-step", "dead-end", "missing-control"]
CT_WARNS = ["no-hint", "frame-overflow"]
CLEAN = FIXTURES / "ct-clean.html"
EXAMPLE = REPO / "examples" / "tool-library" / "3-Borrow-click-through.html"


@pytest.fixture(scope="module")
def chrome():
    with browser.chromium() as b:
        yield b


@pytest.fixture
def flow(chrome):
    """The clean fixture, open and ready."""
    page = browser.open_page(chrome, require(CLEAN))
    page.evaluate("() => window.ct.ready")
    yield page
    page.close()


def codes(problems, level=None):
    return {p["code"] for p in problems if level is None or p["level"] == level}


def current(page):
    return page.evaluate("() => window.ct.current")


def frame(page):
    return page.frame_locator(".ct-frame iframe")


def png_size(path):
    return struct.unpack(">II", path.read_bytes()[16:24])


def test_clean_has_only_the_question_count(chrome):
    problems = browser.check_page(chrome, require(CLEAN))
    assert [(p["level"], p["code"], p["message"]) for p in problems] == [("info", "open-questions", "1 open question")]


@pytest.mark.parametrize("code", CT_ERRORS)
def test_broken_flow_yields_its_error(chrome, code):
    problems = browser.check_page(chrome, require(FIXTURES / f"ct-{code}.html"))
    assert codes(problems, "error") == {code}, problems
    assert codes(problems, "warn") == set(), problems


@pytest.mark.parametrize("code", CT_WARNS)
def test_broken_flow_yields_its_warning(chrome, code):
    problems = browser.check_page(chrome, require(FIXTURES / f"ct-{code}.html"))
    assert codes(problems, "warn") == {code}, problems
    assert codes(problems, "error") == set(), problems


def test_example_click_through_has_no_problems(chrome):
    problems = browser.check_page(chrome, require(EXAMPLE))
    assert codes(problems) <= {"open-questions"}, problems


def test_frame_is_the_apps_own_document(flow):
    """Standards mode, the attributes of ct-html and ct-body, and the captured scroll offset."""
    doc = flow.evaluate("""() => {
        const d = document.querySelector('.ct-frame iframe').contentDocument;
        return {mode: d.compatMode, html: d.documentElement.className, body: d.body.className,
                scroll: d.querySelector('.list').scrollTop};
    }""")
    assert doc == {"mode": "CSS1Compat", "html": "theme-light", "body": "app", "scroll": 20}


def test_frame_has_the_real_size_whatever_the_window(chrome, tmp_path):
    """Media queries and vh units inside the frame see the frame, even when the window is too
    narrow and the frame is scaled down."""
    page_file = tmp_path / "size.html"
    page_file.write_text(CLEAN.read_text().replace(
        "</style>", ".probe { height: 100vh; } @media (min-width: 600px) { .probe { color: rgb(255, 0, 0); } }</style>"
    ).replace('<div class="bar">Books', '<div class="probe"></div><div class="bar">Books'))
    page = browser.open_page(chrome, page_file, width=500)
    page.evaluate("() => window.ct.ready")
    got = page.evaluate("""() => {
        const d = document.querySelector('.ct-frame iframe').contentDocument;
        const probe = d.querySelector('.probe');
        return {color: d.defaultView.getComputedStyle(probe).color, height: probe.getBoundingClientRect().height,
                scaled: document.querySelector('.ct-frame').style.transform};
    }""")
    page.close()
    assert got["color"] == "rgb(255, 0, 0)" and got["height"] == 400
    assert got["scaled"].startswith("scale(0.")


def test_data_go_moves_and_links_do_not_navigate(flow):
    url = flow.url
    assert current(flow) == "1"
    frame(flow).locator("[data-control=Dune]").click()
    assert current(flow) == "2" and flow.url.endswith("#step=2")
    frame(flow).get_by_role("link", name="Books").click()   # an <a href> with data-go
    assert current(flow) == "1" and flow.url.split("#")[0] == url.split("#")[0]


def test_j_and_k_step_through_in_order_but_not_while_typing(flow):
    flow.keyboard.press("j")
    flow.keyboard.press("j")
    assert current(flow) == "2b"
    flow.keyboard.press("k")
    assert current(flow) == "2"
    flow.locator(".ct-restart").click()
    assert current(flow) == "1"
    frame(flow).locator(".search").click()
    flow.keyboard.press("j")
    assert current(flow) == "1"


def test_panel_lists_the_steps(flow):
    steps = flow.evaluate("""() => [...document.querySelectorAll('.ct-step')].map((b) =>
        [b.querySelector('.ct-num').textContent, b.classList.contains('is-branch'), !!b.querySelector('.ct-tag')])""")
    assert steps == [["1", False, False], ["2", False, True], ["2b", True, True], ["3", False, False]]
    flow.locator(".ct-step[data-index='3']").click()
    assert current(flow) == "3"
    assert flow.locator(".ct-step.is-current .ct-name").inner_text() == "Saved"


def test_deep_link_shows_a_base_step_under_its_own_markup(chrome):
    page = browser.open_page(chrome, require(CLEAN), hash="step=2b")
    page.evaluate("() => window.ct.ready")
    assert current(page) == "2b"
    assert frame(page).get_by_role("button", name="Save", exact=True).count() == 1   # from base step 2
    assert frame(page).locator(".toast").count() == 1
    assert "Two ways to save" not in page.locator(".ct-current").inner_text()
    assert "A toast confirms the save." in page.locator(".ct-current").inner_text()
    page.close()


def test_a_ring_marks_each_control_the_hint_names(flow):
    flow.evaluate("() => window.ct.go('2')")
    rings = flow.evaluate("""() => {
        const d = document.querySelector('.ct-frame iframe').contentDocument;
        const boxes = [...d.querySelectorAll('button')].map((b) => b.getBoundingClientRect());
        return [...document.querySelectorAll('.ct-ring')].map((r, i) => {
            const b = boxes[i];
            return parseFloat(r.style.left) < b.left && parseFloat(r.style.left) + parseFloat(r.style.width) > b.right;
        });
    }""")
    assert rings == [True, True]
    flow.evaluate("() => window.ct.go('3')")
    assert flow.locator(".ct-ring").count() == 0


def test_go_to_a_missing_step_rejects(flow):
    with pytest.raises(Exception, match='no step has id "9"'):
        flow.evaluate("() => window.ct.go('9')")


def test_shot_one_step_at_full_size(chrome, tmp_path):
    flow = tmp_path / "flow.html"
    flow.write_text(CLEAN.read_text())
    out = browser.shot(f"{flow}#step=2b", browser=chrome)
    assert out == tmp_path / "flow-step-2b.png"
    width, height = png_size(out)
    assert width == 24 + 640 + 24 + 340 + 24 and height >= 24 + 400 + 24
    with pytest.raises(ValueError, match="has no step '9'"):
        browser.shot(f"{flow}#step=9", browser=chrome)


def test_shot_every_step(chrome, tmp_path):
    outs = browser.shot_steps(require(CLEAN), out_dir=tmp_path / "shots", browser=chrome)
    assert [p.name for p in outs] == ["ct-clean-step-1.png", "ct-clean-step-2.png", "ct-clean-step-2b.png",
                                      "ct-clean-step-3.png"]
    assert all(p.stat().st_size > 1000 for p in outs)
    with pytest.raises(ValueError, match="not a click-through"):
        browser.shot_steps(require(FIXTURES / "lofi-clean.html"), out_dir=tmp_path, browser=chrome)


def test_export_inlines_the_click_through_kit(chrome, tmp_path):
    flow = tmp_path / "flow.html"
    flow.write_text(CLEAN.read_text())
    text = browser.export(flow).read_text()
    assert "/_kit/" not in text
    assert codes(browser.check_page(chrome, tmp_path / "flow.export.html", route=False)) == {"open-questions"}


def test_kit_tags_are_documented(flow):
    """Tags in clickthrough.js (window.ct.tags) equal the tags in the guide's tag table."""
    guide = require(paths.SKILL_DIR / "clickthrough.md").read_text()
    documented = re.findall(r"^\|\s*`<?(ct-[a-z-]+)", guide, flags=re.M)
    assert documented, "clickthrough.md documents no tags"
    assert sorted(set(flow.evaluate("() => window.ct.tags"))) == sorted(set(documented))
    assert len(documented) == len(set(documented)), "a tag is documented twice"


# Pages written here, for behaviour that the fixtures do not show.

def flow_file(tmp_path, steps, css="", head=""):
    """A click-through of a 400 x 300 frame with the given steps and app CSS."""
    path = tmp_path / "flow.html"
    path.write_text(f"""<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="/_kit/clickthrough.css"><script src="/_kit/clickthrough.js"></script></head>
<body><ct-flow name="Test" width="400" height="300">
<template ct-head>{head}<style>body {{ margin: 0; background: #fff; }} {css}</style></template>
{steps}</ct-flow></body></html>""")
    return path


def open_flow(chrome, path, hash=""):
    page = browser.open_page(chrome, path, hash=hash)
    page.evaluate("() => window.ct.ready")
    return page


def test_the_ring_marks_the_control_in_the_overlay(chrome, tmp_path):
    """A dialog step has a button with the same name as a button under the dialog."""
    path = flow_file(tmp_path, """
      <ct-step id="1" name="Page"><ct-hint>Click <ct-control>Delete</ct-control>.</ct-hint>
        <template><button data-go="2">Delete</button></template></ct-step>
      <ct-step id="2" name="Confirm" base="1"><ct-hint>Click <ct-control>Delete</ct-control>.</ct-hint>
        <template><div class="dialog"><button data-go="3">Delete</button></div></template></ct-step>
      <ct-step id="3" name="Done"><ct-hint>The end.</ct-hint><template><p>Done</p></template></ct-step>""",
        css=".dialog { position: fixed; left: 200px; top: 150px; }")
    page = open_flow(chrome, path, "step=2")
    left = page.evaluate("() => parseFloat(document.querySelector('.ct-ring').style.left)")
    page.close()
    assert 190 < left < 200


def test_linked_app_css_loads_before_the_first_step(chrome, tmp_path):
    (tmp_path / "app.css").write_text(".wrap { height: 100px; overflow: auto; } .inner { height: 3000px; }")
    path = flow_file(tmp_path, """
      <ct-step id="1" name="Long list"><ct-hint>Click <ct-control>Go</ct-control>.</ct-hint>
        <template><div class="wrap" data-scroll-top="2500"><div class="inner"></div>
          <button data-go="2">Go</button></div></template></ct-step>
      <ct-step id="2" name="Done"><ct-hint>The end.</ct-hint><template><p>Done</p></template></ct-step>""",
        head='<link rel="stylesheet" href="app.css">')
    page = open_flow(chrome, path)
    got = page.evaluate("""() => [document.querySelector('.ct-frame iframe').contentDocument.querySelector('.wrap').scrollTop,
                                  document.querySelectorAll('.ct-ring').length]""")
    page.close()
    assert got[0] > 2000 and got[1] == 1   # the ring reveal scrolls the button into view


def test_entry_animations_end_before_a_shot_and_a_paused_one_does_not_block(chrome, tmp_path):
    path = flow_file(tmp_path, """
      <ct-step id="1" name="Toast"><ct-hint>Click <ct-control>Next</ct-control>.</ct-hint>
        <template><p class="enter">Deleted</p><p class="paused">Loading</p><button data-go="2">Next</button></template></ct-step>
      <ct-step id="2" name="Done"><ct-hint>The end.</ct-hint><template><p>Done</p></template></ct-step>""",
        css="@keyframes fade { from { opacity: 0; } } .enter { animation: fade 3s; } "
            ".paused { animation: fade 1s paused; }")
    page = open_flow(chrome, path)
    opacity = page.frame_locator(".ct-frame iframe").locator(".enter").evaluate("el => getComputedStyle(el).opacity")
    page.close()
    assert opacity == "1"
    assert png_size(browser.shot(str(path), out=tmp_path / "shot.png", browser=chrome))[0] > 0


def test_enter_on_a_link_without_href_moves(chrome, tmp_path):
    path = flow_file(tmp_path, """
      <ct-step id="1" name="Start"><ct-hint>Click <ct-control>Next</ct-control>.</ct-hint>
        <template><a data-go="2">Next</a></template></ct-step>
      <ct-step id="2" name="Done"><ct-hint>The end.</ct-hint><template><p>Done</p></template></ct-step>""")
    page = open_flow(chrome, path)
    page.frame_locator(".ct-frame iframe").locator("a").focus()
    page.keyboard.press("Enter")
    assert current(page) == "2"
    page.close()


def test_a_captured_popover_opens_again(chrome, tmp_path):
    path = flow_file(tmp_path, """
      <ct-step id="1" name="Menu"><ct-hint>Click <ct-control>Rename</ct-control>.</ct-hint>
        <template><div id="menu" popover data-top-layer="popover"><button data-go="2">Rename</button></div></template></ct-step>
      <ct-step id="2" name="Done"><ct-hint>The end.</ct-hint><template><p>Done</p></template></ct-step>""")
    page = open_flow(chrome, path)
    is_open = page.evaluate("() => document.querySelector('.ct-frame iframe').contentDocument.querySelector('#menu').matches(':popover-open')")
    rings = page.locator(".ct-ring").count()
    page.close()
    assert is_open and rings == 1


def test_shot_every_step_refuses_ids_that_give_one_file_name(chrome, tmp_path):
    path = flow_file(tmp_path, """
      <ct-step id="a.b" name="One"><ct-hint>Click <ct-control>Next</ct-control>.</ct-hint>
        <template><button data-go="a-b">Next</button></template></ct-step>
      <ct-step id="a-b" name="Two"><ct-hint>The end.</ct-hint><template><p>Done</p></template></ct-step>""")
    with pytest.raises(ValueError, match="two steps get the file name flow-step-a-b.png"):
        browser.shot_steps(path, out_dir=tmp_path, browser=chrome)
