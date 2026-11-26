"""check, shot and export: Playwright and headless Chromium.

A board opens by file:// URL; requests for /_kit/<file> are answered from kit/, so these
commands work on a board anywhere on disk, with or without the server.
Three kinds of artboard: a lo-fi board (<wf-board>, kit global window.wf), a click-through
(<ct-flow>, kit global window.ct), and a hi-fi page, which has no kit.
Only this module and capture.py import Playwright, and only inside functions.
"""
import contextlib
import pathlib
import re
from urllib.parse import unquote, urlsplit

from . import paths

LEVELS = ("error", "warn", "info")
READY_TIMEOUT_MS = 15000
PROBLEMS_TIMEOUT_MS = 60000
SETTLE_TIMEOUT_MS = 5000
SHOT_HEIGHT = 1100
# The root tag of each kit, the global that the kit sets, and the name of the kit in messages.
KITS = {"wf-board": "wf", "ct-flow": "ct"}
KIT_NAMES = {"wf": "lo-fi", "ct": "click-through"}
KIT_REF = re.compile(r"""(?:src|href)\s*=\s*["']?/_kit/""", re.I)

# Generic checks for a hi-fi page (no wf-board). Returns problems in the kit's shape.
HIFI_CHECKS = r"""
() => {
  const problems = [];
  const base = new Set(), dark = new Set(), widthSelectors = [];
  const tokens = (style, set) => { for (let i = 0; i < style.length; i++) if (style[i].startsWith('--')) set.add(style[i]); };
  const isDark = rule => /prefers-color-scheme\s*:\s*dark/.test(rule.conditionText || (rule.media && rule.media.mediaText) || '');
  const walk = (rules, inMedia, inDark) => {
    for (const rule of rules) {
      if (rule instanceof CSSMediaRule) { walk(rule.cssRules, true, inDark || isDark(rule)); continue; }
      if (rule instanceof CSSStyleRule) {
        if (inDark) tokens(rule.style, dark);
        else if (!inMedia) tokens(rule.style, base);
        const w = rule.style.getPropertyValue('width');
        if (w && w !== 'auto') widthSelectors.push(rule.selectorText);
      }
      if (rule.cssRules && rule.cssRules.length) walk(rule.cssRules, inMedia, inDark);
    }
  };
  for (const sheet of document.styleSheets) {
    let rules;
    try { rules = sheet.cssRules; } catch (e) { continue; }  // a cross-origin font sheet
    walk(rules, false, false);
  }
  for (const name of [...dark].sort()) {
    if (!base.has(name)) problems.push({level: 'error', code: 'dark-only-token',
      message: `token ${name} is set for dark mode only; set it on :root too`});
  }

  const bg = getComputedStyle(document.body).backgroundColor;
  if (bg === 'transparent' || bg === 'rgba(0, 0, 0, 0)') problems.push({level: 'error',
    code: 'transparent-body', message: 'body has no background color; set one so dark mode works'});

  const explicitWidth = el => !!el.style.width || widthSelectors.some(s => { try { return el.matches(s); } catch (e) { return false; } });
  const flagged = [];
  for (const el of document.body.querySelectorAll('*')) {
    if (!(el instanceof HTMLElement)) continue;
    const cs = getComputedStyle(el);
    if (cs.display === 'inline' || cs.display === 'none' || cs.overflowX !== 'visible') continue;
    if (cs.whiteSpace !== 'nowrap' && cs.whiteSpace !== 'pre' && !explicitWidth(el)) continue;
    const over = el.scrollWidth - el.clientWidth;
    if (el.clientWidth > 0 && over > 1) flagged.push([el, over]);
  }
  // keep the innermost element when a parent overflows only because a child does
  const inner = flagged.filter(([el]) => !flagged.some(([other]) => other !== el && el.contains(other)));
  for (const [el, over] of inner.slice(0, 10)) {
    const name = el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') + (el.classList.length ? '.' + [...el.classList].join('.') : '');
    const text = (el.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 40);
    problems.push({level: 'warn', code: 'overflow', message: `${name} "${text}" overflows its box by ${over}px`});
  }
  return problems;
}
"""


@contextlib.contextmanager
def chromium(browser=None):
    """A headless Chromium; the given one when there is one (Playwright cannot nest)."""
    if browser is not None:
        yield browser
        return
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            yield browser
        finally:
            browser.close()


def route_kit(route):
    """Answer /_kit/<file> from the kit dir."""
    name = unquote(urlsplit(route.request.url).path).split("/_kit/", 1)[-1]
    path = (paths.KIT_DIR / name).resolve()
    try:
        path.relative_to(paths.KIT_DIR.resolve())
        body = path.read_bytes()
    except (ValueError, OSError):
        return route.fulfill(status=404, body="not found")
    ctype = "text/css" if path.suffix == ".css" else "text/javascript" if path.suffix == ".js" else None
    route.fulfill(status=200, body=body, content_type=ctype)


def open_page(browser, path, hash="", dark=False, width=1600, route=True, errors=None):
    """A new page with the board loaded. Console errors and page errors go into `errors`."""
    page = browser.new_page(viewport={"width": width, "height": SHOT_HEIGHT},
                            color_scheme="dark" if dark else "light", reduced_motion="reduce")
    if errors is not None:
        page.on("console", lambda msg: msg.type == "error" and errors.append(f"console: {msg.text}"))
        page.on("pageerror", lambda exc: errors.append(f"page error: {exc}"))
    if route:
        page.route("**/_kit/**", route_kit)
    url = pathlib.Path(path).resolve().as_uri() + (f"#{hash}" if hash else "")
    page.goto(url, wait_until="load")
    return page


def kit_of(page):
    """The global of the kit that draws the page: 'wf' or 'ct'. None for a hi-fi page."""
    return page.evaluate(
        "kits => { const tag = Object.keys(kits).find((t) => document.querySelector(t)); return tag ? kits[tag] : null; }",
        KITS)


def wait_ready(page, kit):
    """True when the kit's ready resolved in time. False when the kit is missing or too slow."""
    return page.evaluate(
        """([kit, ms]) => (window[kit] && window[kit].ready)
              ? Promise.race([Promise.resolve(window[kit].ready).then(() => true),
                              new Promise(r => setTimeout(() => r(false), ms))])
              : false""",
        [kit, READY_TIMEOUT_MS],
    )


def normalize(raw):
    """Problems in a fixed shape, whatever the page returned."""
    out = []
    for p in raw if isinstance(raw, list) else []:
        if not isinstance(p, dict):
            continue
        level = p.get("level") if p.get("level") in LEVELS else "error"
        out.append({"level": level, "code": str(p.get("code") or ""), "message": str(p.get("message") or "")})
    return out


def kit_problems(page, kit):
    """The kit's problems() once its ready resolves. problems() may return a promise.
    A kit that fails or hangs is one error."""
    from playwright.sync_api import Error

    try:
        if not wait_ready(page, kit):
            return [{"level": "error", "code": "not-ready",
                     "message": f"{kit}.ready did not resolve in {READY_TIMEOUT_MS // 1000} s"}]
        return normalize(page.evaluate(
            """([kit, ms]) => Promise.race([
                 Promise.resolve(window[kit].problems()),
                 new Promise((_, no) => setTimeout(() => no(new Error(`problems() did not finish in ${ms / 1000} s`)), ms))])""",
            [kit, PROBLEMS_TIMEOUT_MS]))
    except Error as exc:
        return [{"level": "error", "code": "kit-error", "message": f"the kit failed: {exc.message.splitlines()[0]}"}]


def check_page(browser, path, route=True):
    """The problems one file has, as [{level, code, message}]."""
    errors = []
    page = open_page(browser, path, route=route, errors=errors)
    try:
        kit = kit_of(page)
        if kit is None:
            problems = normalize(page.evaluate(HIFI_CHECKS))
        elif not page.evaluate("k => !!(window[k] && window[k].ready && window[k].problems)", kit):
            problems = [{"level": "error", "code": "kit-missing",
                         "message": f"the {KIT_NAMES[kit]} kit did not load: window.{kit} is missing"}]
        else:
            problems = kit_problems(page, kit)
    finally:
        page.close()
    # A failure repeats each time a click-through renders a step; report each message once.
    problems += [{"level": "error", "code": "console-error", "message": e} for e in dict.fromkeys(errors)]
    return sorted(problems, key=lambda p: LEVELS.index(p["level"]))


def check(files, route=True):
    """{path: problems} for each file, in one browser."""
    with chromium() as browser:
        return {f: check_page(browser, f, route=route) for f in files}


def split_hash(spec):
    """'board.html#journey=2' -> (Path('board.html'), 'journey=2'). A file whose real name has a
    '#' wins over the split."""
    if "#" in spec and not pathlib.Path(spec).exists():
        name, _, hash = spec.partition("#")
        return pathlib.Path(name), hash
    return pathlib.Path(spec), ""


def shot_path(path, hash, dark):
    """board.png, board-dark.png, board-journey-2.png, board-journey-2-dark.png"""
    suffix = ""
    match = re.fullmatch(r"journey=(\d+)", hash)
    if match:
        suffix += f"-journey-{match.group(1)}"
    elif hash:
        suffix += "-" + re.sub(r"[^A-Za-z0-9]+", "-", hash).strip("-")
    if dark:
        suffix += "-dark"
    return path.with_name(f"{path.stem}{suffix}.png")


def settle(page):
    """Wait up to 5 s for the running CSS transitions and finite animations to end. A pinned
    journey fades the other screens with a transition; shoot the end state. A looping or a
    paused animation does not end, so do not wait for it."""
    page.evaluate("""ms => Promise.race([
        Promise.all(document.getAnimations()
            .filter((a) => a.playState === 'running' && a.effect && a.effect.getComputedTiming().endTime !== Infinity)
            .map((a) => a.finished.catch(() => {}))),
        new Promise((resolve) => setTimeout(resolve, ms))])""", SETTLE_TIMEOUT_MS)


def show_frame_at_full_size(page):
    """Size the viewport so the frame of a click-through shows at 100%, then let the kit settle."""
    page.set_viewport_size(page.evaluate("() => window.ct.size"))
    page.evaluate("() => window.ct.go(window.ct.current)")


def shot(spec, dark=False, width=1600, out=None, browser=None):
    """Full-page PNG of a board. A click-through is shot at the size that shows its frame at
    100%, on the step that #step=<id> names. Returns the PNG path."""
    path, hash = split_hash(spec)
    if not path.is_file():
        raise FileNotFoundError(f"no such file: {path}")
    out = pathlib.Path(out) if out else shot_path(path, hash, dark)
    with chromium(browser) as b:
        page = open_page(b, path, hash=hash, dark=dark, width=width)
        try:
            kit = kit_of(page)
            if kit:
                wait_ready(page, kit)
            else:
                page.wait_for_timeout(500)
            if kit == "ct":
                step = re.fullmatch(r"step=(.+)", hash)
                if step and unquote(step.group(1)) not in page.evaluate("() => window.ct.steps"):
                    raise ValueError(f"{path.name} has no step {unquote(step.group(1))!r}")
                show_frame_at_full_size(page)
            settle(page)
            page.screenshot(path=str(out), full_page=True, animations="disabled")
        finally:
            page.close()
    return out


def shot_steps(file, dark=False, out_dir=None, browser=None):
    """One full-page PNG for each step of a click-through, named like `shot file#step=<id>`.
    The PNGs go in out_dir, or next to the file. Returns the PNG paths in step order."""
    path = pathlib.Path(file)
    if not path.is_file():
        raise FileNotFoundError(f"no such file: {path}")
    folder = pathlib.Path(out_dir) if out_dir else path.parent
    folder.mkdir(parents=True, exist_ok=True)
    outs = []
    with chromium(browser) as b:
        page = open_page(b, path, dark=dark)
        try:
            if kit_of(page) != "ct":
                raise ValueError(f"{path.name} is not a click-through: it has no <ct-flow>")
            wait_ready(page, "ct")
            steps = page.evaluate("() => window.ct.steps")
            names = [shot_path(path, f"step={step}", dark).name for step in steps]
            same = sorted({name for name in names if names.count(name) > 1})
            if same:
                raise ValueError(f"two steps get the file name {same[0]}: give them ids that differ in a letter or a digit")
            show_frame_at_full_size(page)
            for step, name in zip(steps, names):
                page.evaluate("id => window.ct.go(id)", step)
                settle(page)
                page.screenshot(path=str(folder / name), full_page=True, animations="disabled")
                outs.append(folder / name)
        finally:
            page.close()
    return outs


def inline_kit(text):
    """The board's text with every /_kit/<file> stylesheet and script inlined."""
    def kit_text(name, closing):
        body = (paths.KIT_DIR / name).read_text(encoding="utf-8")
        return body.replace(closing, closing.replace("</", "<\\/"))

    text = re.sub(
        r"""<link\b[^>]*\bhref\s*=\s*["']/_kit/([\w.-]+\.css)["'][^>]*>""",
        lambda mt: f"<style>\n{kit_text(mt.group(1), '</style')}\n</style>", text, flags=re.I)
    return re.sub(
        r"""<script\b[^>]*\bsrc\s*=\s*["']/_kit/([\w.-]+\.js)["'][^>]*>\s*</script>""",
        lambda mt: f"<script>\n{kit_text(mt.group(1), '</script')}\n</script>", text, flags=re.I)


def export(path, out=None):
    """One self-contained HTML file. A file with no /_kit/ reference is copied unchanged.
    Returns the output path."""
    path = pathlib.Path(path)
    out = pathlib.Path(out) if out else path.with_name(f"{path.stem}.export.html")
    text = path.read_text(encoding="utf-8")
    result = inline_kit(text) if KIT_REF.search(text) else text
    if KIT_REF.search(result):
        raise ValueError(f"{path.name}: a /_kit/ reference is left after inlining")
    out.write_text(result, encoding="utf-8")
    return out
