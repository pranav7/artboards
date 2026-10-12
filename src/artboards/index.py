"""The main page ("/", a review queue) and the history page ("/history"), rendered in memory.

One bad group never breaks a page: it is skipped with a warning on stderr.
"""
import html
import sys
import time
from urllib.parse import quote

from . import meta as m
from . import paths

STATE_WIDTH = max(len(s) for s in m.STATES)  # pad tokens so titles align


# ---------------------------------------------------------------- collecting

def read_group(folder):
    """One group as a dict, or None when it has no artboards."""
    meta = m.read_meta(folder)
    rows = m.board_rows(folder, meta)
    if not rows:
        return None
    closed = meta.get("closed") if isinstance(meta.get("closed"), dict) else {}
    closed_at = m.parse_iso(closed.get("at"))
    newest = max(r["mtime"] for r in rows)
    return {
        "key": folder.name,
        "title": str(meta.get("title") or folder.name),
        "session": str(meta.get("session") or ""),
        "repo": str(meta.get("repo") or ""),
        "branch": str(meta.get("branch") or ""),
        "active": m.is_active(meta),
        "reason": m.close_text(meta),
        "closed_at": closed_at.timestamp() if closed_at else newest,
        "newest": newest,
        "rows": rows,
    }


def read_groups(root=None):
    groups = []
    for folder in m.group_folders(root or paths.data_dir()):
        try:
            group = read_group(folder)
        except Exception as exc:  # one bad group never takes the page down
            print(f"artboards: skipped {folder.name}: {exc}", file=sys.stderr, flush=True)
            continue
        if group:
            groups.append(group)
    return groups


def band(rows):
    """0 when any row is open, 1 when any is pending, else 2."""
    states = {r["state"] for r in rows}
    return 0 if "open" in states else 1 if "pending" in states else 2


# ----------------------------------------------------------------- rendering

CSS = """
:root{
  --ground:#fbfaf9; --surface:#ffffff; --ink:#1c1917; --dim:#78716c;
  --faint:#a8a29e; --rule:#e7e5e4; --accent:#6d4aff;
  --agreed:#15803d; --pending:#b45309; --open:#a16207; --dropped:#a8a29e;
  --tag-bg:#efeeec;
}
@media (prefers-color-scheme: dark){
  :root{
    --ground:#0d0d0f; --surface:#15151a; --ink:#e7e5e4; --dim:#8b8781;
    --faint:#52525b; --rule:#27272a; --accent:#a78bfa;
    --agreed:#4ade80; --pending:#fbbf24; --open:#facc15; --dropped:#52525b;
    --tag-bg:#202024;
  }
}
*{box-sizing:border-box}
body{
  margin:0; background:var(--ground); color:var(--ink);
  font:500 13px/1.55 "IBM Plex Mono", ui-monospace, SFMono-Regular, 'SF Mono', Menlo, monospace;
  font-variant-numeric:tabular-nums;
}
a{color:inherit}
.page{display:flex; flex-direction:column; gap:40px; padding:72px 32px 96px}
.head{display:flex; flex-direction:column; gap:6px}
h1{margin:0; font-size:15px; font-weight:600; letter-spacing:.01em}
.meta{margin:0; font-size:11.5px; font-weight:500; color:var(--dim)}
.bit{white-space:nowrap}
.sep{color:var(--faint)}
.groups{display:grid; grid-template-columns:repeat(auto-fill, minmax(min(100%, 64ch), 1fr)); gap:34px 48px; align-items:start}
.group{display:flex; flex-direction:column; gap:12px; border-top:1px solid var(--rule); padding-top:16px}
.group-head{display:flex; flex-direction:column; gap:4px}
.group-title{display:flex; align-items:baseline; flex-wrap:wrap; gap:8px}
.name{font-size:13px; font-weight:600}
.act{margin-left:auto; font:inherit; font-size:11.5px; color:var(--dim); background:none; border:1px solid var(--rule); border-radius:4px; padding:1px 8px; cursor:pointer}
.act:hover{color:var(--ink); border-color:var(--dim)}
.act:focus-visible{outline:1.5px solid var(--accent); outline-offset:1px}
.act:disabled{opacity:.5; cursor:default}
.pill{display:inline-flex; align-items:center; padding:1px 8px; border-radius:999px}
.tag{font-size:11.5px; font-weight:500; color:var(--dim); background:var(--tag-bg)}
.rows{display:flex; flex-direction:column; gap:1px}
.row{
  display:grid; grid-template-columns:auto 1fr auto; column-gap:12px; row-gap:1px;
  padding:5px 8px; margin:0 -8px; border-radius:3px;
  color:var(--ink); text-decoration:none;
}
.row:hover{background:var(--surface)}
.row:focus-visible{outline:1.5px solid var(--accent); outline-offset:1px}
@media (prefers-reduced-motion: no-preference){
  .row{transition:background-color 120ms ease}
}
.row.dropped{opacity:.55}
.tok{white-space:pre; font-weight:500}
.tok.st-agreed{color:var(--agreed)}
.tok.st-pending{color:var(--pending)}
.tok.st-open{color:var(--open)}
.tok.st-dropped{color:var(--dropped)}
.title{font-weight:500}
.when{font-size:11.5px; font-weight:500; color:var(--dim); white-space:nowrap; align-self:baseline}
.note{
  grid-column:2 / 4; font-size:11.5px; font-weight:500; color:var(--dim);
  display:-webkit-box; -webkit-box-orient:vertical; -webkit-line-clamp:2; line-clamp:2; overflow:hidden;
}
.foot{border-top:1px solid var(--rule); padding-top:16px}
.foot a, .head a{color:var(--dim); text-underline-offset:3px}
.foot a:hover, .head a:hover{color:var(--ink)}
.empty{margin:0; color:var(--dim)}
"""


# Archive and Reopen post to the server, then reload. The page works without it.
SCRIPT = """
document.addEventListener('click', async (event) => {
  const button = event.target.closest('button[data-action]');
  if (!button) return;
  button.disabled = true;
  const url = '/_api/' + button.dataset.action + '/' + encodeURIComponent(button.dataset.key);
  const response = await fetch(url, { method: 'POST' }).catch(() => null);
  if (response && response.ok) location.reload();
  else { button.disabled = false; button.textContent = 'Failed, try again'; }
});
"""


def when(ts):
    return time.strftime("%d %b %H:%M", time.localtime(ts)).lower() if ts else ""


def plural(n, word):
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def esc(value):
    return html.escape(str(value), quote=True)


def href(group, row):
    return esc(f"/{quote(group['key'])}/{quote(row['path'].name)}")


def bit_span(text, first):
    """One meta-line field. Each carries its own leading separator and never wraps inside,
    so a line break lands between fields."""
    sep = "" if first else '<span class="sep">·</span> '
    return f'<span class="bit">{sep}{esc(text)}</span>'


def render_row(group, row):
    state = row["state"]
    token = f'<span class="tok st-{state}">{state.ljust(STATE_WIDTH)}</span>'
    note = f'<span class="note">{esc(row["note"])}</span>' if row["note"] else ""
    tip = f' title="{esc(row["note"])}"' if row["note"] else ""
    return (f'<a class="row {state}" href="{href(group, row)}"{tip}>{token}'
            f'<span class="title">{esc(row["title"])}</span>'
            f'<span class="when">{when(row["mtime"])}</span>{note}</a>')


def render_group(group, rows, bits, action):
    tags = "".join(f'<span class="tag pill">{esc(group[k])}</span>' for k in ("repo", "branch") if group[k])
    line = " ".join(bit_span(b, first=(i == 0)) for i, b in enumerate(b for b in bits if b))
    button = (f'<button type="button" class="act" data-action="{action}" data-key="{esc(group["key"])}">'
              f'{action.capitalize()}</button>')
    return ('<section class="group"><div class="group-head">'
            f'<div class="group-title"><span class="name">{esc(group["title"])}</span>{tags}{button}</div>'
            f'<p class="meta">{line}</p></div>'
            f'<div class="rows">{"".join(render_row(group, r) for r in rows)}</div></section>')


def page(title, lead, body):
    return ('<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{esc(title)}</title>'
            '<link rel="preconnect" href="https://fonts.googleapis.com">'
            '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
            '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
            'family=IBM+Plex+Mono:wght@400;500;600&display=swap">'
            f'<style>{CSS}</style></head><body><main class="page">'
            f'<div class="head"><h1>{esc(title)}</h1>{lead}</div>'
            f'{body}</main><script>{SCRIPT}</script></body></html>\n')


def render_main(groups):
    """Active groups with something to show: open first, then pending, then the rest; newest
    change first within each band. Dropped rows are hidden."""
    shown = []
    for group in groups:
        if not group["active"]:
            continue
        rows = [r for r in group["rows"] if r["state"] != "dropped"]
        if rows:
            shown.append((group, rows))
    shown.sort(key=lambda gr: (band(gr[1]), -gr[0]["newest"]))
    closed = sum(1 for g in groups if not g["active"])

    if shown:
        boards = sum(len(rows) for _, rows in shown)
        lead = f'<p class="meta">{plural(len(shown), "group")} · {plural(boards, "artboard")}</p>'
        body = ('<div class="groups">'
                + "".join(render_group(g, rows, [g["session"], f'last change {when(g["newest"])}'], "archive")
                          for g, rows in shown)
                + "</div>")
    else:
        lead = ""
        body = '<p class="empty">Nothing to review.</p>'
    if closed:
        body += f'<p class="meta foot"><a href="/history">{plural(closed, "closed group")}</a></p>'
    return page("artboards", lead, body)


def render_history(groups):
    """Closed groups, newest close first, with the reason and every row (dropped dimmed)."""
    closed = sorted((g for g in groups if not g["active"]), key=lambda g: -g["closed_at"])
    lead = '<p class="meta"><a href="/">back to the review queue</a></p>'
    if closed:
        body = ('<div class="groups">'
                + "".join(render_group(g, g["rows"], [g["reason"], g["session"], f'last change {when(g["newest"])}'],
                                       "reopen")
                          for g in closed)
                + "</div>")
    else:
        body = '<p class="empty">No closed groups.</p>'
    return page("artboards history", lead, body)
