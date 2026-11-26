"""capture: save one state of a running app as a self-contained HTML snapshot.

The snapshot keeps the app's markup, its CSS, and the images and fonts that the CSS and the
markup use, inlined as data URLs. It loses every script. Opened in a browser, it looks like
the app did. `artboards compose` turns snapshots into the steps of a click-through.

Two phases in the page: COLLECT clones the DOM, copies live state (field values, scroll
offsets, canvases) onto the clone and lists the URLs to inline; then, after Python fetched
those URLs through the browser context (so cookies and headers apply), SERIALIZE puts the
data URLs in and returns the markup.
"""
import base64
import datetime
import hashlib
import html
import json
import mimetypes
import pathlib
import re
from urllib.parse import urljoin, urlsplit

from . import browser

MAX_INLINE = 5 * 1024 * 1024    # a file bigger than this stays a link
FETCH_TIMEOUT_MS = 20000
IDLE_TIMEOUT_MS = 10000
VIEWPORT = (1440, 900)

COLLECT = r"""
(selector) => {
  const root = selector ? document.querySelector(selector) : document.body;
  if (!root) return { error: `no element matches ${selector}` };
  const abs = (u) => { try { return new URL(u, document.baseURI).href; } catch (e) { return u; } };
  const refs = new Set();
  const sprites = new Set();
  const cssUrls = (text) => text.replace(/url\(\s*(?:"([^"]*)"|'([^']*)'|([^)'"\s]*))\s*\)/g, (m, a, b, c) => {
    const u = a ?? b ?? c;
    if (!u || /^(data:|#)/.test(u)) return m;
    refs.add(abs(u));
    return `url("${abs(u)}")`;
  });
  // The attributes of <html> and <body>, with no handlers, and with absolute URLs in the style.
  const attrs = (el) => Array.from(el.attributes)
    .filter((a) => !/^on/i.test(a.name) && a.name !== 'nonce')
    .map((a) => [a.name, a.name === 'style' ? cssUrls(a.value) : a.value]);
  // A blob: picture lives only in this page; copy its pixels.
  const pixels = (img) => {
    try {
      const canvas = document.createElement('canvas');
      canvas.width = img.naturalWidth;
      canvas.height = img.naturalHeight;
      canvas.getContext('2d').drawImage(img, 0, 0);
      return canvas.toDataURL();
    } catch (e) { return null; }
  };

  const clone = root.cloneNode(true);
  const live = [root, ...root.querySelectorAll('*')];
  const copy = [clone, ...clone.querySelectorAll('*')];
  live.forEach((el, i) => {
    const c = copy[i];
    const tag = el.localName;
    // State that lives in properties, not in attributes.
    if (tag === 'input') {
      if (el.type === 'checkbox' || el.type === 'radio') c.toggleAttribute('checked', el.checked);
      else if (el.type !== 'password' && el.type !== 'file') c.setAttribute('value', el.value);
    } else if (tag === 'textarea') c.textContent = el.value;
    else if (tag === 'option') c.toggleAttribute('selected', el.selected);
    if (el.scrollTop > 0) c.setAttribute('data-scroll-top', String(Math.round(el.scrollTop)));
    if (el.scrollLeft > 0) c.setAttribute('data-scroll-left', String(Math.round(el.scrollLeft)));
    if (tag === 'img') {
      let src = el.currentSrc || el.getAttribute('src') || '';
      for (const a of ['srcset', 'sizes', 'loading']) c.removeAttribute(a);
      if (src.startsWith('blob:')) src = (el.naturalWidth && pixels(el)) || src;
      if (src.startsWith('data:')) c.setAttribute('src', src);
      else if (src) { c.setAttribute('src', abs(src)); refs.add(abs(src)); }
    }
    if (tag === 'image') {
      for (const a of ['href', 'xlink:href']) {
        const v = el.getAttribute(a);
        if (v && !/^(data|blob):/.test(v)) { const u = abs(v); c.setAttribute(a, u); refs.add(u); }
      }
    }
    // An open popover or modal dialog is in the top layer, which no attribute records.
    // The click-through kit opens each element marked data-top-layer again.
    try {
      if (el.matches(':popover-open')) c.setAttribute('data-top-layer', 'popover');
      else if (tag === 'dialog' && el.matches(':modal')) c.setAttribute('data-top-layer', 'modal');
    } catch (e) { /* a browser with no popover support */ }
    // <use href="/icons.svg#name"> points into a sprite file; SERIALIZE copies the sprite in.
    if (tag === 'use') {
      for (const a of ['href', 'xlink:href']) {
        const v = el.getAttribute(a);
        if (v && !v.startsWith('#')) { const u = abs(v); c.setAttribute(a, u); sprites.add(u.split('#')[0]); }
      }
    }
    const style = c.getAttribute('style');
    if (style && style.includes('url(')) c.setAttribute('style', cssUrls(style));
    for (const a of Array.from(c.attributes)) {
      if (/^on/i.test(a.name) || a.name === 'nonce' ||
          (/^(href|src|action|formaction)$/i.test(a.name) && /^\s*javascript:/i.test(a.value))) c.removeAttribute(a.name);
    }
    // A canvas becomes a picture of itself; an iframe becomes an empty box of the same size.
    if (tag === 'canvas' || tag === 'iframe') {
      let box = document.createElement('div');
      if (tag === 'canvas') { try { box = document.createElement('img'); box.src = el.toDataURL(); } catch (e) { box = document.createElement('div'); } }
      for (const a of ['id', 'class', 'style']) if (c.hasAttribute(a)) box.setAttribute(a, c.getAttribute(a));
      const r = el.getBoundingClientRect();
      box.style.width = r.width + 'px';
      box.style.height = r.height + 'px';
      if (c !== clone) c.replaceWith(box);
    }
  });
  // Styles go to the head of the snapshot; scripts and the rest do not belong in it.
  for (const el of clone.querySelectorAll('script, noscript, style, link, meta, base, object, embed, picture > source')) el.remove();

  const rules = (sheet) => { try { return Array.from(sheet.cssRules, (r) => r.cssText).join('\n'); } catch (e) { return null; } };
  const sheets = [];
  for (const sheet of document.styleSheets) {
    if (sheet.disabled) continue;
    const media = sheet.media ? sheet.media.mediaText : '';
    if (sheet.href) { sheets.push({ href: sheet.href, base: sheet.href, text: null, rules: rules(sheet), media }); continue; }
    const node = sheet.ownerNode;
    // A CSS-in-JS library can insert rules with no text in the style element; read the rules then.
    const own = node && node.textContent && node.textContent.trim() ? node.textContent : rules(sheet);
    sheets.push({ href: null, base: document.baseURI, text: own || '', rules: null, media });
  }
  for (const sheet of document.adoptedStyleSheets || []) {
    sheets.push({ href: null, base: document.baseURI, text: rules(sheet) || '', rules: null, media: '' });
  }
  const page = document.scrollingElement || document.documentElement;
  window.__artboardsCapture = { clone, whole: !selector, html: attrs(document.documentElement), body: attrs(document.body) };
  return { title: document.title, url: location.href, sheets, refs: [...refs], sprites: [...sprites],
           scrolled: [Math.round(page.scrollLeft), Math.round(page.scrollTop)] };
}
"""

SERIALIZE = r"""
([map, sprites]) => {
  const { clone, whole, html, body } = window.__artboardsCapture;
  const swap = (u) => map[u] || u;
  const swapStyle = (style) => style.replace(/url\("([^"]*)"\)/g, (m, u) => `url("${swap(u)}")`);
  const attrs = (pairs) => pairs.map(([name, value]) => [name, name === 'style' ? swapStyle(value) : value]);
  // Each sprite file that loaded goes in once, hidden, and its <use> elements point inside the page.
  for (const [url, text] of Object.entries(sprites)) {
    const svg = new DOMParser().parseFromString(text, 'image/svg+xml').documentElement;
    if (!svg || svg.localName !== 'svg') continue;
    const box = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    box.setAttribute('aria-hidden', 'true');
    box.setAttribute('style', 'position: absolute; width: 0; height: 0; overflow: hidden');
    box.setAttribute('data-artboards-sprite', url);
    box.append(...Array.from(svg.childNodes, (n) => document.importNode(n, true)));
    clone.prepend(box);
    for (const use of clone.querySelectorAll('use')) {
      for (const a of ['href', 'xlink:href']) {
        const v = use.getAttribute(a);
        if (v && v.startsWith(url + '#')) use.setAttribute(a, v.slice(url.length));
      }
    }
  }
  for (const el of [clone, ...clone.querySelectorAll('*')]) {
    if (el.localName === 'img' && el.hasAttribute('src')) el.setAttribute('src', swap(el.getAttribute('src')));
    if (el.localName === 'image') for (const a of ['href', 'xlink:href']) if (el.hasAttribute(a)) el.setAttribute(a, swap(el.getAttribute(a)));
    const style = el.getAttribute('style');
    if (style && style.includes('url(')) el.setAttribute('style', swapStyle(style));
  }
  delete window.__artboardsCapture;
  return { markup: whole ? clone.innerHTML : clone.outerHTML, html: attrs(html), body: attrs(body) };
}
"""

# A url() token, quoted or not. A quoted data URL is matched whole, so a url() inside it is left alone.
CSS_URL = re.compile(r"""url\(\s*(?:"([^"]*)"|'([^']*)'|([^)'"\s]*))\s*\)""", re.I)
CSS_IMPORT = re.compile(r"""@import\s+(?:url\(\s*(?:"([^"]*)"|'([^']*)'|([^)'"\s]*))\s*\)|"([^"]*)"|'([^']*)')""", re.I)


class Fetcher:
    """Fetches URLs through the browser context, so the page's cookies and headers apply.
    Caches each URL. Adds a line to `warnings` for each URL it cannot inline."""

    def __init__(self, request, warnings):
        self.request = request
        self.warnings = warnings
        self.cache = {}

    def get(self, url):
        """(body bytes, content type), or None."""
        from playwright.sync_api import Error

        if url in self.cache:
            return self.cache[url]
        result = None
        if urlsplit(url).scheme not in ("http", "https"):
            self.warnings.append(f"{url}: only http and https URLs are inlined")
        else:
            try:
                resp = self.request.get(url, timeout=FETCH_TIMEOUT_MS)
                body = resp.body()
                if not resp.ok:
                    self.warnings.append(f"{url}: HTTP {resp.status}")
                elif len(body) > MAX_INLINE:
                    self.warnings.append(f"{url}: {len(body) // 1024} KB is too big to inline; it stays a link")
                else:
                    ctype = resp.headers.get("content-type", "").split(";")[0].strip()
                    ctype = ctype or mimetypes.guess_type(urlsplit(url).path)[0] or "application/octet-stream"
                    result = (body, ctype)
            except Error as exc:
                self.warnings.append(f"{url}: {exc.message.splitlines()[0]}")
        self.cache[url] = result
        return result

    def data_url(self, url):
        got = self.get(url)
        return f"data:{got[1]};base64,{base64.b64encode(got[0]).decode('ascii')}" if got else None

    def text(self, url):
        got = self.get(url)
        return got[0].decode("utf-8", errors="replace") if got else None


def inline_css(css, base, fetch):
    """CSS with each url() made a data URL, or an absolute URL when it cannot be fetched.
    An @import stays a link, made absolute: the URLs inside the imported file are relative to it."""
    imports = []

    def hold(m):
        ref = next(g for g in m.groups() if g is not None)
        imports.append(f'@import url("{urljoin(base, ref)}")')
        return f"@import __artboards_import_{len(imports) - 1}__"

    def inline(m):
        ref = next((g for g in m.groups() if g is not None), "").strip()
        if not ref or ref.startswith(("data:", "#")):
            return m.group(0)
        absolute = urljoin(base, ref)
        return f'url("{fetch.data_url(absolute) or absolute}")'

    css = CSS_URL.sub(inline, CSS_IMPORT.sub(hold, css))
    return re.sub(r"@import __artboards_import_(\d+)__", lambda m: imports[int(m.group(1))], css)


def attrs_html(pairs):
    return "".join(f' {name}="{html.escape(value, quote=True)}"' for name, value in pairs)


def style_block(css, media):
    """One <style> element. Its id is a hash of the CSS, so compose can drop repeats."""
    css = css.replace("</", "<\\/")   # nothing in the CSS can close the element
    digest = hashlib.sha1(css.encode("utf-8")).hexdigest()[:12]
    media_attr = f' media="{html.escape(media, quote=True)}"' if media and media != "all" else ""
    return digest, f'<style data-artboards-css="{digest}"{media_attr}>\n{css}\n</style>'


def settle(page):
    """Wait until the network is quiet (or 10 s pass), the fonts load, and running animations end."""
    from playwright.sync_api import TimeoutError

    try:
        page.wait_for_load_state("networkidle", timeout=IDLE_TIMEOUT_MS)
    except TimeoutError:
        pass
    page.evaluate("() => document.fonts.ready.then(() => {})")
    browser.settle(page)


def run_script(path, page):
    """Run a Python file with `page` (a Playwright Page) set: to sign in, or to click the app
    into the state to capture."""
    path = pathlib.Path(path)
    code = compile(path.read_text(encoding="utf-8"), str(path), "exec")
    exec(code, {"page": page, "__name__": "__artboards_before__", "__file__": str(path)})


def capture(url, out, selector=None, viewport=VIEWPORT, cookies=(), headers=(), before=None,
            wait_for=None, wait_ms=0, dark=False):
    """Save the page at `url` as a snapshot at `out`, and a PNG of the page next to it.
    cookies: (name, value) pairs for the page's site. headers: (name, value) pairs sent with
    every request. before: a Python file run after the page loads (see run_script).
    Returns (snapshot path, PNG path, warnings)."""
    from playwright.sync_api import sync_playwright

    out = pathlib.Path(out)
    png = out.with_suffix(".png")
    warnings = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            context = browser.new_context(
                viewport={"width": viewport[0], "height": viewport[1]},
                color_scheme="dark" if dark else "light",
                extra_http_headers=dict(headers) or None)
            if cookies:
                # For the whole site: a cookie set by URL gets the URL's folder as its path.
                host = urlsplit(url).hostname
                context.add_cookies([{"name": n, "value": v, "domain": host, "path": "/"} for n, v in cookies])
            page = context.new_page()
            page.goto(url, wait_until="load")
            settle(page)
            if before:
                run_script(before, page)
                settle(page)
            if wait_for:
                page.wait_for_selector(wait_for, state="visible", timeout=30000)
            if wait_ms:
                page.wait_for_timeout(wait_ms)
            settle(page)

            data = page.evaluate(COLLECT, selector)
            if data.get("error"):
                raise ValueError(data["error"])
            if any(data["scrolled"]):
                warnings.append(f"the page is scrolled {data['scrolled'][1]} px down and {data['scrolled'][0]} px "
                                "across; the snapshot keeps the scroll of scroll boxes, not of the page")
            page.screenshot(path=str(png), animations="disabled")
            fetch = Fetcher(context.request, warnings)
            styles, seen = [], set()
            for sheet in data["sheets"]:
                css = sheet["text"]
                if sheet["href"]:
                    css = fetch.text(sheet["href"]) or sheet["rules"]
                if css is None:
                    warnings.append(f"{sheet['href']}: the stylesheet cannot be read; the snapshot leaves it out")
                    continue
                digest, block = style_block(inline_css(css, sheet["base"], fetch), sheet["media"])
                if digest not in seen:
                    seen.add(digest)
                    styles.append(block)
            sprites = {u: fetch.text(u) for u in data["sprites"]}
            result = page.evaluate(SERIALIZE, [{u: fetch.data_url(u) or u for u in data["refs"]},
                                               {u: text for u, text in sprites.items() if text}])
        finally:
            browser.close()

    info = {"url": data["url"], "viewport": f"{viewport[0]}x{viewport[1]}", "selector": selector or "",
            "captured": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        "<!doctype html>\n"
        f"<html{attrs_html(result['html'])}>\n<head>\n<meta charset=\"utf-8\">\n"
        f"<meta name=\"artboards-capture\" content=\"{html.escape(json.dumps(info), quote=True)}\">\n"
        f"<title>{html.escape(data['title'])}</title>\n"
        + "\n".join(styles) +
        f"\n</head>\n<body{attrs_html(result['body'])}>\n<!-- artboards:body -->\n{result['markup']}\n<!-- /artboards:body -->\n"
        "</body>\n</html>\n",
        encoding="utf-8")
    return out, png, warnings
