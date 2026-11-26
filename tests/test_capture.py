"""capture and compose against a small app on localhost."""
import base64
import http.server
import re
import threading

import pytest
from artboards import browser, capture, compose

# A 1x1 PNG.
PIXEL = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")

INDEX = """<!doctype html>
<html class="theme" lang="en">
<head>
<title>Test app</title>
<link rel="stylesheet" href="/css/app.css">
<link rel="stylesheet" href="/css/private.css">
<style>.title { color: rgb(1, 2, 3); }</style>
</head>
<body class="app-body" onload="void 0" nonce="n1" style="background: url(/img/logo.png) no-repeat">
<div id="root"></div>
<div id="pop" popover>A popover</div>
<script>
  document.getElementById('root').innerHTML =
    '<main class="panel"><h1 class="title">Hello</h1>' +
    '<input id="name"><input type="checkbox" id="agree"><textarea id="note"></textarea>' +
    '<div class="list" style="height: 50px; overflow: auto"><div style="height: 300px">rows</div></div>' +
    '<img src="/img/logo.png" alt="logo"><a href="javascript:alert(1)" onclick="go()">bad link</a>' +
    '<button data-testid="next" style="background-image: url(/img/logo.png)">Next</button>' +
    '<canvas id="chart" width="10" height="10"></canvas><img id="inline" src="data:image/gif;base64,R0lGODlhAQABAAAAACw=">' +
    '<img id="blobbed"></main>' +
    '<aside class="side">Side</aside>';
  document.getElementById('name').value = 'Ada';
  document.getElementById('agree').checked = true;
  document.getElementById('note').value = 'A note';
  document.querySelector('.list').scrollTop = 40;
  document.getElementById('chart').getContext('2d').fillRect(0, 0, 10, 10);
  const sheet = new CSSStyleSheet();
  sheet.replaceSync('.adopted { color: rgb(4, 5, 6); }');
  document.adoptedStyleSheets = [sheet];
  const png = Uint8Array.from(atob('PIXEL'), (c) => c.charCodeAt(0));
  document.getElementById('blobbed').src = URL.createObjectURL(new Blob([png], {type: 'image/png'}));
  document.getElementById('pop').showPopover();
</script>
</body>
</html>
"""
APP_CSS = """@import "/css/extra.css";
.panel { background: url(../img/logo.png) no-repeat; }
.mask { mask: url("data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg'><path d='url(x)'/></svg>"); }
.missing { background: url(/img/missing.png); }
"""


@pytest.fixture(scope="module")
def app():
    """The test app on a free port. The private stylesheet needs the cookie session=ok; every
    request records its X-Test header in app.seen."""
    seen = []
    files = {
        "/": ("text/html", INDEX.replace("PIXEL", base64.b64encode(PIXEL).decode()).encode()),
        "/deep/page": ("text/html", INDEX.replace("PIXEL", base64.b64encode(PIXEL).decode()).encode()),
        "/css/app.css": ("text/css", APP_CSS.encode()),
        "/css/extra.css": ("text/css", b".extra { color: rgb(7, 8, 9); }"),
        "/css/private.css": ("text/css", b".private { color: rgb(10, 11, 12); }"),
        "/img/logo.png": ("image/png", PIXEL),
    }

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append(self.headers.get("X-Test"))
            path = self.path.split("?")[0]
            if path not in files or (path == "/css/private.css" and "session=ok" not in (self.headers.get("Cookie") or "")):
                self.send_error(404 if path not in files else 403)
                return
            ctype, body = files[path]
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    server.url = f"http://127.0.0.1:{server.server_address[1]}"
    server.seen = seen
    yield server
    server.shutdown()


@pytest.fixture(scope="module")
def snap(app, tmp_path_factory):
    out = tmp_path_factory.mktemp("snap") / "home.html"
    result = capture.capture(app.url + "/", out, viewport=(800, 600), cookies=[("session", "ok")],
                             headers=[("X-Test", "hello")])
    return out, result


def test_capture_writes_a_snapshot_and_a_png(snap):
    out, (path, png, warnings) = snap
    assert path == out and png == out.with_suffix(".png") and png.stat().st_size > 1000
    assert [w for w in warnings if "missing.png" not in w] == [], warnings
    assert any("missing.png: HTTP 404" in w for w in warnings)


def test_capture_drops_scripts_and_handlers(snap):
    text = snap[0].read_text()
    body = text.split("<!-- artboards:body -->")[1]
    assert "<script" not in text and "onclick" not in text and "javascript:" not in text
    assert "<link" not in text and "<style" not in body
    assert '<h1 class="title">Hello</h1>' in body   # what the script drew stays


def test_capture_keeps_live_state(snap):
    body = snap[0].read_text().split("<!-- artboards:body -->")[1]
    assert 'value="Ada"' in body
    assert re.search(r'<input type="checkbox" id="agree" checked', body)
    assert ">A note</textarea>" in body
    assert 'data-scroll-top="40"' in body
    assert "<canvas" not in body and re.search(r'<img src="data:image/png;base64,[^"]+" id="chart"', body)
    assert 'data-testid="next"' in body   # data attributes stay
    assert re.search(r'<img id="inline" src="data:image/gif;base64,R0lGODlhAQABAAAAACw=">', body)
    assert "blob:" not in body and re.search(r'<img id="blobbed" src="data:image/png;base64,', body)
    assert '<div id="pop" popover="" data-top-layer="popover">' in body


def test_capture_inlines_css_images_and_fonts(snap, app):
    text = snap[0].read_text()
    assert '<html class="theme" lang="en">' in text
    assert re.search(r'<body class="app-body" style="background: url\(&quot;data:image/png;base64,[^&]+&quot;\) no-repeat">', text)
    assert re.search(r'<img src="data:image/png;base64,[^"]+" alt="logo">', text)
    assert 'url(&quot;data:image/png;base64,' in text   # the inline style attribute
    assert re.search(r'\.panel \{ background: url\("data:image/png;base64,', text)
    assert f'@import url("{app.url}/css/extra.css")' in text   # an @import stays a link, made absolute
    assert "<path d='url(x)'/>" in text                         # a url() inside a data URL is left alone
    for rule in [".title { color: rgb(1, 2, 3); }", ".private { color: rgb(10, 11, 12); }", ".adopted"]:
        assert rule in text, rule
    assert "hello" in app.seen


def test_snapshot_looks_like_the_app_offline(snap):
    """Opened from disk, the snapshot has the app's styles."""
    with browser.chromium() as b:
        page = browser.open_page(b, snap[0])
        colors = page.evaluate("""() => ['.title', '.adopted'].map((s) => {
            const el = document.createElement('p'); el.className = s.slice(1); document.body.append(el);
            return getComputedStyle(el).color; })""")
        page.close()
    assert colors == ["rgb(1, 2, 3)", "rgb(4, 5, 6)"]


def test_cookies_reach_the_whole_site(app, tmp_path):
    """A cookie given for a page in a folder still goes with requests outside that folder."""
    out, _, warnings = capture.capture(app.url + "/deep/page", tmp_path / "deep.html", viewport=(800, 600),
                                       cookies=[("session", "ok")])
    assert ".private { color: rgb(10, 11, 12); }" in out.read_text()
    assert not any("private.css" in w for w in warnings), warnings


def test_capture_one_element(app, tmp_path):
    out, _, _ = capture.capture(app.url + "/", tmp_path / "main.html", selector="main", viewport=(800, 600))
    body = out.read_text().split("<!-- artboards:body -->")[1]
    assert body.lstrip().startswith('<main class="panel">') and "Side" not in body
    with pytest.raises(ValueError, match="no element matches nav"):
        capture.capture(app.url + "/", tmp_path / "nav.html", selector="nav", viewport=(800, 600))


def test_capture_runs_a_script_first(app, tmp_path):
    script = tmp_path / "before.py"
    script.write_text("page.fill('#name', 'Grace')\n"
                      "page.evaluate(\"document.body.dataset.state = 'open'\")\n"
                      "page.evaluate(\"document.body.style.height = '3000px'; window.scrollTo(0, 500)\")\n")
    out, _, warnings = capture.capture(app.url + "/", tmp_path / "after.html", before=script, viewport=(800, 600))
    text = out.read_text()
    assert 'value="Grace"' in text and 'data-state="open"' in text
    assert any(w.startswith("the page is scrolled 500 px down") for w in warnings), warnings


def test_inline_css_without_a_browser():
    class Fake:
        def data_url(self, url):
            return "data:x" if url.endswith("ok.png") else None

    css = '@import url(a.css) screen; .a { background: url(ok.png) } .b { background: url("../gone.png") }'
    assert capture.inline_css(css, "http://h/css/app.css", Fake()) == (
        '@import url("http://h/css/a.css") screen; .a { background: url("data:x") } '
        '.b { background: url("http://h/gone.png") }')


def test_compose_writes_one_step_per_snapshot(app, snap, tmp_path):
    second, _, _ = capture.capture(app.url + "/", tmp_path / "second-state.html", viewport=(800, 600),
                                   cookies=[("session", "ok")])
    out, warnings = compose.compose(tmp_path / "flow.html", [snap[0], second], title="Test flow")
    assert warnings == []
    text = out.read_text()
    hashes = re.findall(r'<style data-artboards-css="([0-9a-f]+)"', text)
    assert hashes and len(hashes) == len(set(hashes))
    assert re.findall(r'<ct-step id="(\d+)" name="([^"]+)"', text) == [("1", "home"), ("2", "second state")]
    assert '<ct-flow name="Test flow" width="800" height="600">' in text
    assert '<ct-html class="theme" lang="en"></ct-html>' in text
    assert '<ct-body class="app-body" style="background: url(&quot;data:image/png;base64,' in text

    with browser.chromium() as b:
        problems = browser.check_page(b, out)
        # No moves yet: step 1 leads nowhere and nothing leads to step 2.
        assert {(p["level"], p["code"]) for p in problems} == {
            ("error", "dead-end"), ("error", "unreached-step"), ("warn", "no-hint")}, problems
        out.write_text(text.replace('data-testid="next"', 'data-go="2"', 1))
        problems = browser.check_page(b, out)
        assert [p["code"] for p in problems] == ["no-hint"], problems
        page = browser.open_page(b, out)
        page.evaluate("() => window.ct.ready")
        color = page.frame_locator(".ct-frame iframe").locator(".title").evaluate("el => getComputedStyle(el).color")
        page.close()
    assert color == "rgb(1, 2, 3)"

    with pytest.raises(FileExistsError, match="--add"):
        compose.compose(out, [snap[0]])
    compose.compose(out, [snap[0]], add=True)
    added = out.read_text()
    assert re.findall(r'<ct-step id="(\d+)"', added) == ["1", "2", "3"]
    assert re.findall(r'<style data-artboards-css="([0-9a-f]+)"', added) == hashes


def test_compose_warns_when_the_body_attributes_differ(snap, tmp_path):
    """An open modal can set pointer-events: none on the body; every step gets the first body."""
    other = tmp_path / "dialog-open.html"
    other.write_text(snap[0].read_text().replace('<body class="app-body"', '<body class="app-body" data-scroll-locked="1"', 1))
    _, warnings = compose.compose(tmp_path / "flow.html", [snap[0], other])
    assert len(warnings) == 1 and warnings[0].startswith("dialog-open.html: its <body> attributes differ from those of home.html")


def test_compose_refuses_a_file_that_is_not_a_snapshot(tmp_path):
    page = tmp_path / "page.html"
    page.write_text("<!doctype html><body>hi</body>")
    with pytest.raises(ValueError, match="not a snapshot"):
        compose.compose(tmp_path / "flow.html", [page])
