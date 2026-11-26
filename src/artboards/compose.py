"""compose: write a click-through from snapshots that `artboards capture` saved, one step each.

The click-through gets the CSS of every snapshot once (a style block with the same hash is
kept once), the <html> and <body> attributes of the first snapshot, and one <ct-step> per
snapshot with an empty hint. The author then adds the moves (data-go), the hints and the
panel text. --add appends steps to a click-through that exists.

The <html> and <body> attributes apply to every step. An open dialog can change them, for
example pointer-events: none on the body, so compose warns when the snapshots disagree.
"""
import html
import json
import pathlib
import re

STYLE = re.compile(r'<style data-artboards-css="([0-9a-f]+)"[^>]*>.*?</style>', re.S)
BODY = re.compile(r"<!-- artboards:body -->\n?(.*?)\n?<!-- /artboards:body -->", re.S)
CAPTURE_META = re.compile(r'<meta name="artboards-capture" content="([^"]*)">')
STEP_ID = re.compile(r'<ct-step\b[^>]*?\bid="(\d+)"')

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{title}</title>
<link rel="stylesheet" href="/_kit/clickthrough.css">
<script src="/_kit/clickthrough.js"></script>
</head>
<body>
<ct-flow name="{title}" width="{width}" height="{height}">
<ct-intro></ct-intro>

<template ct-head>
<ct-html{html_attrs}></ct-html>
<ct-body{body_attrs}></ct-body>
{styles}
</template>
{steps}</ct-flow>
</body>
</html>
"""

STEP = """
<ct-step id="{id}" name="{name}">
<ct-hint></ct-hint>
<ct-new></ct-new>
<template>
{markup}
</template>
</ct-step>
"""


def tag_attrs(text, tag):
    """The attribute text of the first <tag ...> in text, such as ' class="dark"'."""
    m = re.search(rf"<{tag}((?:\s[^>]*)?)>", text, re.I)
    return m.group(1) if m else ""


def read_snapshot(path):
    """The parts of a snapshot that a click-through needs."""
    path = pathlib.Path(path)
    text = path.read_text(encoding="utf-8")
    body = BODY.search(text)
    if not body:
        raise ValueError(f"{path.name} is not a snapshot from `artboards capture`")
    meta = CAPTURE_META.search(text)
    info = json.loads(html.unescape(meta.group(1))) if meta else {}
    return {
        "name": path.stem.replace("-", " ").replace("_", " "),
        "viewport": info.get("viewport", ""),
        "html_attrs": tag_attrs(text, "html"),
        "body_attrs": tag_attrs(text, "body"),
        "styles": [(m.group(1), m.group(0)) for m in STYLE.finditer(text)],
        "markup": body.group(1),
    }


def new_styles(snaps, have=()):
    """Style blocks in first-seen order, each hash once, minus the hashes in have."""
    seen, out = set(have), []
    for snap in snaps:
        for digest, block in snap["styles"]:
            if digest not in seen:
                seen.add(digest)
                out.append(block)
    return out


def steps_html(snaps, first_id):
    return "".join(STEP.format(id=first_id + i, name=html.escape(s["name"], quote=True), markup=s["markup"])
                   for i, s in enumerate(snaps))


def attr_warnings(snaps, names):
    """A line for each snapshot whose <html> or <body> attributes differ from the first one's."""
    lines = []
    for snap, name in zip(snaps[1:], names[1:]):
        for tag in ("html", "body"):
            if snap[f"{tag}_attrs"] != snaps[0][f"{tag}_attrs"]:
                lines.append(f"{name}: its <{tag}> attributes differ from those of {names[0]}, "
                             f"and the click-through uses those of {names[0]}:{snap[f'{tag}_attrs'] or ' none'}")
    return lines


def compose(out, snapshots, title="Click-through", add=False):
    """Write a click-through at out with one step per snapshot. With add, append the steps and
    any new CSS to the click-through at out. Returns (out, warnings)."""
    out = pathlib.Path(out)
    snaps = [read_snapshot(s) for s in snapshots]
    warnings = attr_warnings(snaps, [pathlib.Path(s).name for s in snapshots])
    if add:
        text = out.read_text(encoding="utf-8")
        head = text.find("<template ct-head>")
        head_end = text.find("</template>", head)
        flow_end = text.rfind("</ct-flow>")
        if head < 0 or head_end < 0 or flow_end < head_end:
            raise ValueError(f"{out.name} has no <template ct-head> and </ct-flow>; it was not made by compose")
        styles = new_styles(snaps, have=re.findall(r'data-artboards-css="([0-9a-f]+)"', text))
        first_id = max((int(n) for n in STEP_ID.findall(text)), default=0) + 1
        text = (text[:head_end] + "".join(s + "\n" for s in styles) + text[head_end:flow_end]
                + steps_html(snaps, first_id) + text[flow_end:])
    else:
        if out.exists():
            raise FileExistsError(f"{out} exists. Add --add to append steps to it")
        width, _, height = snaps[0]["viewport"].partition("x")
        text = PAGE.format(
            title=html.escape(title, quote=True),
            width=width if width.isdigit() else 1440,
            height=height if height.isdigit() else 900,
            html_attrs=snaps[0]["html_attrs"],
            body_attrs=snaps[0]["body_attrs"],
            styles="\n".join(new_styles(snaps)),
            steps=steps_html(snaps, 1))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    return out, warnings
