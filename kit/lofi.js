/*
 * lofi.js - the lo-fi journey board kit.
 *
 * The board file holds only content (wf-* tags). On DOMContentLoaded this script:
 *   1. checks the tags, ids and journeys                       (checkTags, readLinks, readJourneys)
 *   2. renders every wf-* component from its attributes        (upgrade)
 *   3. puts regions left to right and cells on a CSS grid      (layoutRegion, attachNotes)
 *   4. builds the side panel and the toolbar                   (buildPanel, buildTools)
 *   5. routes each wf-link as a right-angle arrow or two stubs (routeAll)
 *   6. wires journey hover and pin, #journey=N, zoom and pan   (show, pin, zoomTo, panTo)
 *
 * window.wf.ready resolves when all of that is done; window.wf.problems() lists what is wrong.
 */
(function () {
  'use strict';

  // ---------- Tunables ----------
  const STUB = 18;      // an arrow runs straight this far out of a screen before it may bend
  const STUB_RUN = 8;   // a stub link runs this much further before it stops
  const CLEAR = 10;     // arrows keep at least this far from screens, labels and notes
  const BEND = 60;      // routing cost of one bend, in px of extra length
  const SHARED = 4;     // cost multiplier for running on top of an earlier arrow
  const RADIUS = 6;     // corner radius where an arrow bends

  // Every kit tag. kit/reference.md documents exactly these; a test checks that the two match.
  const TAGS = [
    'wf-board', 'wf-problem', 'wf-summary', 'wf-journey', 'wf-region', 'wf-screen', 'wf-decision',
    'wf-link', 'wf-note', 'wf-question', 'wf-prose',
    'wf-header', 'wf-tabbar', 'wf-sidebar', 'wf-tabs', 'wf-menu', 'wf-list', 'wf-row', 'wf-card',
    'wf-avatar', 'wf-image', 'wf-chart', 'wf-stat', 'wf-table', 'wf-badge', 'wf-empty', 'wf-input',
    'wf-search', 'wf-select', 'wf-textarea', 'wf-check', 'wf-radio', 'wf-toggle', 'wf-button',
    'wf-modal', 'wf-sheet', 'wf-toast', 'wf-cols',
  ];

  const NS = 'http://www.w3.org/2000/svg';
  const SIDES = ['right', 'bottom', 'left', 'top'];         // index = direction of travel when leaving that side
  const STEP = [[1, 0], [0, 1], [-1, 0], [0, -1]];
  const WARN_ICON = '<svg viewBox="0 0 16 16"><path d="M8 1.5 15 14H1z" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/><path d="M8 6v4M8 11.6v.4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>';

  // The one board on the page. problems: found once while reading; geo: found after each layout.
  const S = { zoom: 1, links: [], journeys: [], pinned: null, cells: new Map(), problems: [], geo: [] };

  let resolveReady;
  window.wf = {
    tags: TAGS.slice(),
    ready: new Promise((resolve) => { resolveReady = resolve; }),
    problems() {
      const all = S.problems.concat(S.geo);
      const q = S.world ? $$('wf-question', S.world).length : 0;
      if (q) all.push({ level: 'info', code: 'open-questions', message: `${q} open question${q === 1 ? '' : 's'}` });
      return all.map((p) => ({ ...p }));
    },
  };

  // ---------- Small helpers ----------
  const $$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));
  const attr = (el, name, fallback = '') => el.getAttribute(name) ?? fallback;
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const split = (el, name) => attr(el, name).split(',').map((s) => s.trim()).filter(Boolean);
  const num = (el, name) => Math.max(1, parseInt(attr(el, name, '1'), 10) || 1);
  const nodeOf = (el) => el && el.closest('wf-screen, wf-decision');
  const nameOf = (node) => attr(node, 'name') || node.id;
  const report = (level, code, message) => S.problems.push({ level, code, message });
  function h(tag, cls, html) {
    const el = document.createElement(tag);
    if (cls) el.className = cls;
    if (html != null) el.innerHTML = html;
    return el;
  }
  function svg(tag, attrs) {
    const el = document.createElementNS(NS, tag);
    for (const k in attrs) el.setAttribute(k, attrs[k]);
    return el;
  }

  // ---------- 1. Checks on the source ----------
  function checkTags(board) {
    const known = new Set(TAGS);
    const unknown = new Set($$('*').map((el) => el.localName).filter((t) => t.startsWith('wf-') && !known.has(t)));
    for (const t of unknown) report('error', 'unknown-tag', `<${t}> is not a kit tag`);
    for (const el of $$('wf-region, wf-link, wf-journey, wf-prose, wf-problem, wf-summary', board)) {
      if (el.parentElement !== board) report('error', 'misplaced-tag', `<${el.localName}> must sit directly inside <wf-board>`);
    }
    const count = new Map();
    for (const el of [board, ...$$('[id]', board)]) if (el.id) count.set(el.id, (count.get(el.id) || 0) + 1);
    for (const [id, n] of count) if (n > 1) report('error', 'duplicate-id', `id "${id}" is used ${n} times`);
  }

  // ---------- 2. Components ----------
  // Each entry renders one tag from its attributes. Container tags keep the children the author wrote.
  const itemsHtml = (el, inner) => {
    const active = attr(el, 'active');
    return split(el, 'items').map((t) => `<span${t === active ? ' class="on"' : ''}>${inner(esc(t))}</span>`).join('');
  };
  const named = (el) => {
    if (el.hasAttribute('name')) el.insertAdjacentHTML('afterbegin', `<b class="wf-title">${esc(attr(el, 'name'))}</b>`);
  };
  const field = (el, boxClass) => {
    const value = attr(el, 'value');
    const label = attr(el, 'label');
    el.innerHTML = (label ? `<small>${esc(label)}</small>` : '') +
      `<span class="wf-box ${boxClass}${value ? '' : ' wf-ph'}">${esc(value || attr(el, 'placeholder'))}</span>`;
  };
  const marker = (el) => el.insertAdjacentHTML('afterbegin', '<i></i>');

  const RENDER = {
    'wf-header': (el) => {
      el.innerHTML = (el.hasAttribute('back') ? '<i class="wf-back"></i>' : '') +
        `<b>${esc(attr(el, 'name'))}</b><i class="wf-av"></i>`;
    },
    'wf-tabbar': (el) => { el.innerHTML = itemsHtml(el, (t) => `<i></i>${t}`); },
    'wf-sidebar': (el) => { el.innerHTML = itemsHtml(el, (t) => `<i></i>${t}`); },
    'wf-tabs': (el) => { el.innerHTML = itemsHtml(el, (t) => t); },
    'wf-menu': (el) => { el.innerHTML = itemsHtml(el, (t) => `${t}<i class="wf-chev"></i>`); },
    'wf-row': (el) => el.insertAdjacentHTML('afterbegin',
      (el.hasAttribute('avatar') ? '<i class="wf-av"></i>' : '') +
      (el.hasAttribute('thumb') ? '<i class="wf-thumb"></i>' : '') +
      `<span class="wf-row-text"><b>${esc(attr(el, 'name'))}</b><small>${esc(attr(el, 'meta'))}</small></span>`),
    'wf-card': named,
    'wf-modal': named,
    'wf-sheet': named,
    'wf-avatar': (el) => { el.innerHTML = `<i class="wf-av"></i><small>${esc(attr(el, 'name'))}</small>`; },
    'wf-image': (el) => { el.innerHTML = `<span>${esc(attr(el, 'label', 'photo'))}</span>`; },
    'wf-chart': (el, i) => { el.innerHTML = chart(attr(el, 'kind', 'line'), `${el.id}${i}`); },
    'wf-stat': (el) => { el.innerHTML = `<b>${esc(attr(el, 'value'))}</b><small>${esc(attr(el, 'label'))}</small>`; },
    'wf-table': (el) => {
      // One row per line, cells split by "|", the first line is the header. A cell starting with "~" is struck out.
      const rows = el.textContent.split('\n').map((s) => s.trim()).filter(Boolean).map((r) => r.split('|').map((c) => c.trim()));
      const cell = (c) => (c.startsWith('~') ? `<span class="off">${esc(c.slice(1))}</span>` : `<span>${esc(c)}</span>`);
      el.style.setProperty('--cols', rows.length ? rows[0].length : 1);
      el.innerHTML = (rows[0] || []).map((c) => `<b>${esc(c)}</b>`).join('') + rows.slice(1).flat().map(cell).join('');
    },
    'wf-empty': marker,
    'wf-input': (el) => field(el, ''),
    'wf-select': (el) => field(el, 'wf-select-box'),
    'wf-textarea': (el) => field(el, 'wf-area'),
    'wf-search': (el) => {
      const value = attr(el, 'value');
      el.innerHTML = `<i class="wf-mag"></i><span${value ? '' : ' class="wf-ph"'}>${esc(value || attr(el, 'placeholder'))}</span>`;
    },
    'wf-check': marker,
    'wf-radio': marker,
    'wf-toggle': marker,
    'wf-question': (el) => el.insertAdjacentHTML('afterbegin', WARN_ICON),
    'wf-decision': (el) => {
      el.innerHTML = '<svg viewBox="0 0 100 60" preserveAspectRatio="none"><polygon points="50,1 99,30 50,59 1,30" vector-effect="non-scaling-stroke"/></svg>' +
        `<span>${esc(attr(el, 'name') || el.textContent.trim())}</span>`;
    },
  };

  // A rough squiggle or bar row. Seeded from the element so it is stable across reloads.
  function chart(kind, seed) {
    let s = 7;
    for (const ch of seed) s = (s * 31 + ch.charCodeAt(0)) >>> 0;
    const rnd = () => ((s = (Math.imul(s, 1103515245) + 12345) >>> 0) / 4294967296);
    if (kind === 'bar') {
      const bars = Array.from({ length: 9 }, (_, i) => {
        const v = 6 + rnd() * 22;
        return `<rect x="${i * 11 + 1}" y="${30 - v}" width="7" height="${v}" rx="1"/>`;
      });
      return `<svg viewBox="0 0 100 30" preserveAspectRatio="none">${bars.join('')}</svg>`;
    }
    const pts = Array.from({ length: 11 }, (_, i) => `${i * 10},${(4 + rnd() * 22).toFixed(1)}`);
    return `<svg viewBox="0 0 100 30" preserveAspectRatio="none"><polyline points="${pts.join(' ')}" vector-effect="non-scaling-stroke"/></svg>`;
  }

  function upgrade(board) {
    for (const tag in RENDER) $$(tag, board).forEach((el, i) => RENDER[tag](el, i));
  }

  // ---------- 3. Regions and grid cells ----------
  function layoutRegion(region, n) {
    region.dataset.n = n;
    const grid = h('div', 'wf-grid');
    const taken = new Map();   // "col,row" -> name of the item there
    region.place = (cell, el, what) => {
      const col = num(el, 'col'), row = num(el, 'row'), key = `${col},${row}`;
      if (taken.has(key)) {
        report('error', 'cell-taken', `region ${region.id || n}: ${taken.get(key)} and ${what} both sit at col ${col}, row ${row}`);
        S.sameCell.push(cell);
      }
      taken.set(key, what);
      cell.style.gridColumn = col;
      cell.style.gridRow = row;
      grid.append(cell);
    };
    for (const el of Array.from(region.children)) {
      if (!el.matches('wf-screen, wf-decision')) continue;
      const screen = el.matches('wf-screen');
      const cell = h('div', screen ? 'wf-cell' : 'wf-cell wf-cell-decision');
      if (screen) cell.append(h('div', 'wf-label', esc(nameOf(el)) + (el.hasAttribute('new') ? '<span class="wf-new">new</span>' : '')));
      cell.append(el);
      S.cells.set(el, cell);
      region.place(cell, el, el.id || nameOf(el));
    }
    region.notes = $$(':scope > wf-note, :scope > wf-question', region);
    region.replaceChildren(h('div', 'wf-region-head', `<span class="wf-num">${n}</span>${esc(attr(region, 'name'))}`), grid);
  }

  // A note or question with "for" sits under that screen; one without takes its own col and row.
  function attachNotes(regions) {
    for (const region of regions) {
      for (const el of region.notes) {
        const target = attr(el, 'for');
        const node = target && nodeOf(document.getElementById(target));
        if (node && S.cells.has(node)) { S.cells.get(node).append(el); continue; }
        if (target) report('error', 'missing-id', `${el.localName.slice(3)} for="${target}": no screen or decision has id "${target}"`);
        const cell = h('div', 'wf-cell wf-free');
        cell.append(el);
        region.place(cell, el, `a ${el.localName.slice(3)}`);
      }
    }
  }

  // ---------- Links and journeys (data) ----------
  function readLinks(board) {
    return $$(':scope > wf-link', board).map((el, i) => {
      const ids = [attr(el, 'from'), attr(el, 'to')];
      const tag = `link ${ids[0]} -> ${ids[1]}`;
      const [from, to] = ids.map((id) => id && document.getElementById(id));
      const wrong = [from, to].map((x, k) => (!x ? `no element has id "${ids[k]}"`
        : !S.cells.has(nodeOf(x)) ? `"${ids[k]}" is not a screen, a decision, or inside one` : null)).filter(Boolean);
      for (const w of wrong) report('error', 'missing-id', `${tag}: ${w}`);
      if (wrong.length) return null;
      const fromNode = nodeOf(from), toNode = nodeOf(to);
      const dist = Math.abs(fromNode.closest('wf-region').dataset.n - toNode.closest('wf-region').dataset.n);
      const stub = el.getAttribute('stub');
      return {
        id: el.id || `link-${i + 1}`, named: !!el.id, tag, label: attr(el, 'label'), from, to, fromNode, toNode,
        exitAttr: attr(el, 'exit') || null, enterAttr: attr(el, 'enter') || null,
        stub: stub === null ? dist >= 2 : stub !== 'false',
      };
    }).filter(Boolean);
  }

  function readJourneys(board, links) {
    return $$(':scope > wf-journey', board).map((el, i) => {
      const j = { n: i + 1, name: attr(el, 'name'), path: [] };
      const tag = `journey ${j.n} "${j.name}"`;
      j.steps = split(el, 'steps').map((s) => {
        const [id, via] = s.split('@').map((t) => t.trim());
        const node = nodeOf(document.getElementById(id));
        if (!node) report('error', 'missing-id', `${tag}: no screen or decision has id "${id}"`);
        const viaOk = !via || links.some((L) => L.named && L.id === via);
        if (!viaOk) report('error', 'missing-id', `${tag}: no link has id "${via}"`);
        return { id, via, node, ok: !!node && viaOk };
      });
      j.nodes = new Set(j.steps.map((s) => s.node).filter(Boolean));
      for (let k = 1; k < j.steps.length; k++) {
        const a = j.steps[k - 1], b = j.steps[k];
        if (!a.ok || !b.ok) continue;
        const joins = (L, x, y) => L.fromNode === x && L.toNode === y;
        let found = links.filter((L) => joins(L, a.node, b.node));
        if (!found.length) found = links.filter((L) => joins(L, b.node, a.node));
        if (b.via) found = found.filter((L) => L.id === b.via);
        if (found.length === 1) j.path.push({ link: found[0], n: k });
        else if (!found.length) report('error', 'no-link', `${tag}: no link from ${a.id} to ${b.id}${b.via ? ` named "${b.via}"` : ''}`);
        else report('error', 'ambiguous-step', `${tag}: ${found.length} links join ${a.id} and ${b.id}; write the step as ${b.id}@<link-id>`);
      }
      return j;
    });
  }

  function checkScreens() {
    const linked = new Set(S.links.flatMap((L) => [L.fromNode, L.toNode]));
    const inJourney = new Set(S.journeys.flatMap((j) => [...j.nodes]));
    for (const scr of $$('wf-screen', S.world)) {
      const name = scr.id || nameOf(scr);
      if (!linked.has(scr)) report('warn', 'unreached-screen', `screen ${name}: no link reaches or leaves it`);
      if (!inJourney.has(scr)) report('warn', 'screen-not-in-journey', `screen ${name}: no journey uses it`);
      const primaries = scr.querySelectorAll('wf-button[primary]').length;
      if (primaries > 1) report('warn', 'two-primaries', `screen ${name}: ${primaries} primary buttons; keep one`);
    }
  }

  // ---------- 4. Panel and toolbar ----------
  function buildPanel(board, regions) {
    const panel = h('aside', 'lofi-panel');
    panel.append(h('h1', null, esc(attr(board, 'name'))), h('div', 'lofi-h', 'Journeys'));
    const list = h('ol', 'lofi-journeys');
    for (const j of S.journeys) {
      j.li = h('li', null, `<span class="lofi-jn">${j.n}</span><span>${esc(j.name)}<span class="lofi-dots">${'<i></i>'.repeat(j.steps.length)}</span></span>`);
      j.li.addEventListener('mouseenter', () => show(j));
      j.li.addEventListener('mouseleave', () => show(S.pinned));
      j.li.addEventListener('click', () => pin(S.pinned === j ? null : j));
      list.append(j.li);
    }
    panel.append(list);

    const summary = board.querySelector(':scope > wf-summary');
    if (summary) panel.append(h('p', 'lofi-summary', summary.innerHTML));
    const problem = board.querySelector(':scope > wf-problem');
    if (problem) panel.append(h('details', null, `<summary>Problem</summary>${problem.innerHTML}`));

    const ids = new Set(regions.map((r) => r.id));
    for (const prose of $$(':scope > wf-prose', board)) {
      const id = attr(prose, 'region');
      if (!ids.has(id)) report('error', 'missing-id', `prose region="${id}": no region has id "${id}"`);
    }
    for (const region of regions) {
      const sec = h('section', 'lofi-section', `<h3><span class="wf-num">${region.dataset.n}</span>${esc(attr(region, 'name'))}</h3>`);
      for (const prose of $$(':scope > wf-prose', board)) if (region.id && attr(prose, 'region') === region.id) sec.insertAdjacentHTML('beforeend', prose.innerHTML);
      panel.append(sec);
    }

    const questions = $$('wf-question', S.world);
    if (questions.length) {
      panel.append(h('div', 'lofi-h', 'Open questions'));
      const ql = h('ol', 'lofi-questions');
      for (const q of questions) {
        const li = h('li', null, `<span class="wf-num">${q.closest('wf-region').dataset.n}</span><span>${esc(q.textContent.trim())}</span>`);
        li.addEventListener('click', () => panTo(q));
        ql.append(li);
      }
      panel.append(ql);
    }
    return panel;
  }

  function buildTools(board) {
    const tools = h('div', 'lofi-tools',
      '<button data-act="fit">Fit</button><button data-act="one">100%</button><span class="lofi-zoom"></span><span class="lofi-sep"></span>' +
      '<button data-hide="hide-notes">Notes</button><button data-hide="hide-screens">Screens</button><button data-hide="no-panel">Panel</button>' +
      '<button class="lofi-badge" data-act="problems" hidden></button>');
    tools.addEventListener('click', (e) => {
      const b = e.target.closest('button');
      if (!b) return;
      if (b.dataset.act === 'fit') fit();
      if (b.dataset.act === 'one') zoomTo(1);
      if (b.dataset.act === 'problems') console.table(window.wf.problems());
      if (b.dataset.hide) {
        b.classList.toggle('off', board.classList.toggle(b.dataset.hide));
        if (b.dataset.hide === 'hide-screens') relayout();   // arrows move from elements to frame edges
      }
    });
    return tools;
  }

  function updateBadge() {
    const n = window.wf.problems().filter((p) => p.level !== 'info').length;
    S.badge.hidden = !n;
    S.badge.textContent = `${n} problem${n === 1 ? '' : 's'}`;
  }

  // ---------- Zoom and pan ----------
  function zoomTo(z, cx, cy) {
    const c = S.canvas, r = c.getBoundingClientRect();
    if (cx == null) { cx = r.left + c.clientWidth / 2; cy = r.top + c.clientHeight / 2; }
    // Keep the world point under (cx, cy) in place.
    const wx = (c.scrollLeft + cx - r.left - S.sizer.offsetLeft) / S.zoom;
    const wy = (c.scrollTop + cy - r.top - S.sizer.offsetTop) / S.zoom;
    S.zoom = Math.min(2, Math.max(0.15, z));
    S.world.style.transform = `scale(${S.zoom})`;
    S.sizer.style.width = `${S.world.offsetWidth * S.zoom}px`;
    S.sizer.style.height = `${S.world.offsetHeight * S.zoom}px`;
    c.scrollLeft = wx * S.zoom + S.sizer.offsetLeft - (cx - r.left);
    c.scrollTop = wy * S.zoom + S.sizer.offsetTop - (cy - r.top);
    S.zoomLabel.textContent = `${Math.round(S.zoom * 100)}%`;
  }
  function fit() {
    const c = S.canvas;
    zoomTo(Math.min((c.clientWidth - 24) / S.world.offsetWidth, (c.clientHeight - 24) / S.world.offsetHeight, 1));
  }
  // Centre an element on the canvas, at 100% if the board is zoomed out further than that.
  function panTo(el) {
    if (S.zoom < 1) zoomTo(1);
    const b = measure(el), c = S.canvas;
    c.scrollTo({
      left: S.sizer.offsetLeft + ((b.l + b.r) / 2) * S.zoom - c.clientWidth / 2,
      top: S.sizer.offsetTop + ((b.t + b.b) / 2) * S.zoom - c.clientHeight / 2,
      behavior: 'smooth',
    });
  }
  function wirePan() {
    const c = S.canvas;
    let drag = null;
    c.addEventListener('pointerdown', (e) => {
      if (e.button !== 0 || e.target.closest('.wf-stublabel')) return;
      drag = { x: e.clientX, y: e.clientY, l: c.scrollLeft, t: c.scrollTop, id: e.pointerId };
    });
    c.addEventListener('pointermove', (e) => {
      if (!drag || e.pointerId !== drag.id) return;
      if (!c.hasPointerCapture(e.pointerId)) {
        if (Math.hypot(e.clientX - drag.x, e.clientY - drag.y) < 4) return;
        c.setPointerCapture(e.pointerId);
        c.classList.add('dragging');
      }
      c.scrollLeft = drag.l - (e.clientX - drag.x);
      c.scrollTop = drag.t - (e.clientY - drag.y);
    });
    const end = () => { drag = null; c.classList.remove('dragging'); };
    c.addEventListener('pointerup', end);
    c.addEventListener('pointercancel', end);
    c.addEventListener('wheel', (e) => {
      if (!e.ctrlKey && !e.metaKey) return;
      e.preventDefault();
      zoomTo(S.zoom * Math.exp(-e.deltaY * 0.01), e.clientX, e.clientY);
    }, { passive: false });
  }

  // ---------- 5. Arrow routing ----------
  // Boxes are {l, t, r, b} in world px (unscaled), measured from the rendered page.
  function measure(el) {
    const o = S.world.getBoundingClientRect(), r = el.getBoundingClientRect(), z = S.zoom;
    return { l: (r.left - o.left) / z, t: (r.top - o.top) / z, r: (r.right - o.left) / z, b: (r.bottom - o.top) / z };
  }
  // A screen's box includes its label above it, so arrows do not run through the label.
  function nodeBox(node) {
    const b = measure(node);
    const label = node.previousElementSibling;
    if (label && label.classList.contains('wf-label')) b.t = measure(label).t;
    return b;
  }
  // Default sides: go sideways when the boxes clear each other horizontally, else up or down.
  function defaultSides(a, b) {
    if (b.l >= a.r + 2 * STUB) return ['right', 'left'];
    if (b.r <= a.l - 2 * STUB) return ['left', 'right'];
    return b.t >= a.b ? ['bottom', 'top'] : ['top', 'bottom'];
  }
  const overlaps = (a, b) => a.l < b.r && b.l < a.r && a.t < b.b && b.t < a.b;
  const center = (b) => ({ x: (b.l + b.r) / 2, y: (b.t + b.b) / 2 });
  const move = (p, side, d) => { const [dx, dy] = STEP[SIDES.indexOf(side)]; return { x: p.x + dx * d, y: p.y + dy * d }; };

  // Each link end gets a port on its anchor element (p0) and a point just outside its node (p1).
  // Ends that share an anchor and a side are spread along that side, ordered to avoid crossings.
  // With Screens hidden, the anchor is always the screen itself.
  function placePorts(links) {
    const frames = S.board.classList.contains('hide-screens');
    const groups = new Map();
    for (const L of links) {
      const from = frames ? L.fromNode : L.from, to = frames ? L.toNode : L.to;
      L.A = nodeBox(L.fromNode);
      L.B = nodeBox(L.toNode);
      const [exit, enter] = defaultSides(L.A, L.B);
      L.exit = L.exitAttr || exit;
      L.enter = L.enterAttr || enter;
      // A control inside a screen only leaves sideways; going up or down would cross the screen's content.
      if (!L.exitAttr && from !== L.fromNode && (L.exit === 'top' || L.exit === 'bottom')) {
        L.exit = center(L.B).x >= center(L.A).x ? 'right' : 'left';
      }
      if (!L.enterAttr && to !== L.toNode && (L.enter === 'top' || L.enter === 'bottom')) {
        L.enter = center(L.A).x >= center(L.B).x ? 'right' : 'left';
      }
      for (const end of [{ L, key: 'p', el: from, side: L.exit, node: L.A, other: L.B },
                         { L, key: 'q', el: to, side: L.enter, node: L.B, other: L.A }]) {
        if (!groups.has(end.el)) groups.set(end.el, {});
        (groups.get(end.el)[end.side] ||= []).push(end);
      }
    }
    for (const bySide of groups.values()) {
      for (const side in bySide) {
        const ends = bySide[side];
        const along = side === 'top' || side === 'bottom' ? 'x' : 'y';
        ends.sort((a, b) => center(a.other)[along] - center(b.other)[along]);
        ends.forEach((e, k) => {
          const box = measure(e.el);
          const f = e.el.matches('wf-decision') ? 0.5 : (k + 1) / (ends.length + 1);
          const x = Math.round(side === 'left' ? box.l : side === 'right' ? box.r : box.l + (box.r - box.l) * f);
          const y = Math.round(side === 'top' ? box.t : side === 'bottom' ? box.b : box.t + (box.b - box.t) * f);
          const n = e.node;
          const out = {
            x: side === 'right' ? Math.round(n.r + STUB) : side === 'left' ? Math.round(n.l - STUB) : x,
            y: side === 'bottom' ? Math.round(n.b + STUB) : side === 'top' ? Math.round(n.t - STUB) : y,
          };
          e.L[e.key] = [{ x, y }, out];
        });
      }
    }
  }

  // A sparse routing grid: lanes just outside every obstacle, the middle of every gap,
  // every port, and a ring around everything. Nodes inside an obstacle (grown by CLEAR) are closed.
  function makeGrid(obstacles, points) {
    const xs = new Set(), ys = new Set();
    const lane = 2 * CLEAR;
    for (const o of obstacles) { xs.add(o.l - lane); xs.add(o.r + lane); ys.add(o.t - lane); ys.add(o.b + lane); }
    for (const p of points) { xs.add(p.x); ys.add(p.y); }
    const withMidpoints = (set) => {
      const v = [...set].map(Math.round).sort((a, b) => a - b);
      const out = new Set(v);
      for (let i = 1; i < v.length; i++) if (v[i] - v[i - 1] > 2 * lane) out.add(Math.round((v[i] + v[i - 1]) / 2));
      out.add(v[0] - 60);
      out.add(v[v.length - 1] + 60);
      return [...out].sort((a, b) => a - b);
    };
    const X = withMidpoints(xs), Y = withMidpoints(ys);
    const nx = X.length, ny = Y.length;
    const grown = obstacles.map((o) => ({ l: o.l - CLEAR, t: o.t - CLEAR, r: o.r + CLEAR, b: o.b + CLEAR }));
    const open = new Uint8Array(nx * ny);
    for (let j = 0; j < ny; j++) for (let i = 0; i < nx; i++) {
      open[j * nx + i] = grown.some((o) => o.l < X[i] && X[i] < o.r && o.t < Y[j] && Y[j] < o.b) ? 0 : 1;
    }
    // hOk[n]: edge from node n to its right neighbour is clear. vOk[n]: edge to the node below.
    const hOk = new Uint8Array(nx * ny), vOk = new Uint8Array(nx * ny);
    for (let j = 0; j < ny; j++) for (let i = 0; i < nx; i++) {
      const n = j * nx + i;
      if (i + 1 < nx && open[n] && open[n + 1]) {
        hOk[n] = grown.some((o) => o.t < Y[j] && Y[j] < o.b && X[i] < o.r && X[i + 1] > o.l) ? 0 : 1;
      }
      if (j + 1 < ny && open[n] && open[n + nx]) {
        vOk[n] = grown.some((o) => o.l < X[i] && X[i] < o.r && Y[j] < o.b && Y[j + 1] > o.t) ? 0 : 1;
      }
    }
    const at = (p) => Y.indexOf(p.y) * nx + X.indexOf(p.x);
    return { X, Y, nx, ny, hOk, vOk, at };
  }

  class Heap {
    constructor() { this.k = []; this.v = []; }
    get size() { return this.k.length; }
    push(key, val) {
      const k = this.k, v = this.v;
      let i = k.length;
      k.push(key); v.push(val);
      while (i > 0) {
        const p = (i - 1) >> 1;
        if (k[p] <= key) break;
        k[i] = k[p]; v[i] = v[p]; i = p;
      }
      k[i] = key; v[i] = val;
    }
    pop() {
      const k = this.k, v = this.v, top = v[0], lk = k.pop(), lv = v.pop();
      if (k.length) {
        let i = 0;
        for (;;) {
          let c = 2 * i + 1;
          if (c >= k.length) break;
          if (c + 1 < k.length && k[c + 1] < k[c]) c++;
          if (k[c] >= lk) break;
          k[i] = k[c]; v[i] = v[c]; i = c;
        }
        k[i] = lk; v[i] = lv;
      }
      return top;
    }
  }

  // Dijkstra over (grid node, direction of travel). Cost = length, plus BEND per turn,
  // with edges an earlier arrow used costing SHARED times more. Returns grid points or null.
  function shortest(g, s, sDir, t, tDir, used) {
    const N = g.nx * g.ny;
    const dist = new Float64Array(N * 4).fill(Infinity);
    const prev = new Int32Array(N * 4).fill(-1);
    const done = new Uint8Array(N * 4);
    const heap = new Heap();
    dist[s * 4 + sDir] = 0;
    heap.push(0, s * 4 + sDir);
    while (heap.size) {
      const st = heap.pop();
      if (done[st]) continue;
      done[st] = 1;
      const n = st >> 2, dir = st & 3, i = n % g.nx, j = (n - i) / g.nx;
      for (let nd = 0; nd < 4; nd++) {
        if (nd === (dir + 2) % 4) continue;
        let m, edge;
        if (nd === 0) { if (i + 1 >= g.nx || !g.hOk[n]) continue; m = n + 1; edge = n; }
        else if (nd === 2) { if (i === 0 || !g.hOk[n - 1]) continue; m = n - 1; edge = n - 1; }
        else if (nd === 1) { if (j + 1 >= g.ny || !g.vOk[n]) continue; m = n + g.nx; edge = N + n; }
        else { if (j === 0 || !g.vOk[n - g.nx]) continue; m = n - g.nx; edge = N + n - g.nx; }
        const len = Math.abs(g.X[m % g.nx] - g.X[i]) + Math.abs(g.Y[(m - (m % g.nx)) / g.nx] - g.Y[j]);
        const cost = dist[st] + len * (used.has(edge) ? SHARED : 1) + (nd === dir ? 0 : BEND);
        const ms = m * 4 + nd;
        if (cost < dist[ms]) { dist[ms] = cost; prev[ms] = st; heap.push(cost, ms); }
      }
    }
    let best = -1, bestCost = Infinity;
    for (let d = 0; d < 4; d++) {
      const c = dist[t * 4 + d] + (d === tDir ? 0 : BEND);
      if (c < bestCost) { bestCost = c; best = t * 4 + d; }
    }
    if (best < 0) return null;
    const nodes = [];
    for (let st = best; st >= 0; st = prev[st]) nodes.push(st >> 2);
    nodes.reverse();
    for (let k = 1; k < nodes.length; k++) {
      const a = Math.min(nodes[k - 1], nodes[k]), b = Math.max(nodes[k - 1], nodes[k]);
      used.add(b - a === 1 ? a : N + a);
    }
    return nodes.map((n) => ({ x: g.X[n % g.nx], y: g.Y[(n - (n % g.nx)) / g.nx] }));
  }

  // Drop repeated points and points in the middle of a straight run.
  function simplify(pts) {
    const out = [];
    for (const p of pts) {
      const a = out[out.length - 2], b = out[out.length - 1];
      if (b && b.x === p.x && b.y === p.y) continue;
      if (a && ((a.x === b.x && b.x === p.x) || (a.y === b.y && b.y === p.y))) out.pop();
      out.push(p);
    }
    return out;
  }

  function pathData(pts) {
    let d = `M${pts[0].x},${pts[0].y}`;
    for (let k = 1; k < pts.length - 1; k++) {
      const a = pts[k - 1], b = pts[k], c = pts[k + 1];
      const r = Math.min(RADIUS, Math.hypot(b.x - a.x, b.y - a.y) / 2, Math.hypot(c.x - b.x, c.y - b.y) / 2);
      const toward = (p, q) => { const len = Math.hypot(q.x - p.x, q.y - p.y) || 1; return { x: p.x + (q.x - p.x) * r / len, y: p.y + (q.y - p.y) * r / len }; };
      const p = toward(b, a), q = toward(b, c);
      d += ` L${p.x},${p.y} Q${b.x},${b.y} ${q.x},${q.y}`;
    }
    const last = pts[pts.length - 1];
    return `${d} L${last.x},${last.y}`;
  }

  // ---------- Labels ----------
  const segments = (pts) => pts.slice(1).map((b, k) => ({ a: pts[k], b }));
  const lineBox = ({ a, b }) => ({ l: Math.min(a.x, b.x) - 1, r: Math.max(a.x, b.x) + 1, t: Math.min(a.y, b.y) - 1, b: Math.max(a.y, b.y) + 1 });

  // Candidate centres for a label on a full arrow: centred on a horizontal run, or beside a vertical run,
  // longest run first, sliding out from the middle of the run.
  function* arrowSpots(pts, w, ht) {
    const segs = segments(pts).map((s) => ({ ...s, len: Math.abs(s.b.x - s.a.x) + Math.abs(s.b.y - s.a.y) }))
      .sort((s1, s2) => s2.len - s1.len);
    for (const { a, b, len } of segs) {
      const flat = a.y === b.y;
      const room = len - (flat ? w : ht) - 2 * RADIUS;   // how far the label centre may slide along this run
      for (let off = 0; off <= room / 2; off += 6) {
        for (const along of [len / 2 - off, len / 2 + off]) {
          const x = a.x + Math.sign(b.x - a.x) * along, y = a.y + Math.sign(b.y - a.y) * along;
          if (flat) yield { x, y };
          else for (const s of [1, -1]) yield { x: x + s * (w / 2 + 4), y };
        }
      }
    }
  }

  // Candidate centres for a stub label: just past the end of the stub, so the line runs into or out of it,
  // then above or below the stub.
  function* stubSpots(part, w, ht) {
    const { inner, outer, side } = part;
    if (side === 'left' || side === 'right') {
      const d = side === 'right' ? 1 : -1;
      yield { x: outer.x + d * (w / 2 + 4), y: outer.y };
      yield { x: inner.x + d * (w / 2), y: outer.y - ht / 2 - 3 };
      yield { x: inner.x + d * (w / 2), y: outer.y + ht / 2 + 3 };
    } else {
      const d = side === 'bottom' ? 1 : -1;
      yield { x: outer.x, y: outer.y + d * (ht / 2 + 4) };
      yield { x: outer.x + w / 2 + 5, y: inner.y + d * (ht / 2) };
      yield { x: outer.x - w / 2 - 5, y: inner.y + d * (ht / 2) };
    }
  }

  // Put a label at the first candidate where it covers no screen, note, earlier label or other arrow.
  function placeLabel(part, taken, otherLines, regionBoxes) {
    const el = part.labelEl, w = el.offsetWidth, ht = el.offsetHeight;
    const rectAt = (x, y) => ({ l: x - w / 2 - 2, r: x + w / 2 + 2, t: y - ht / 2 - 2, b: y + ht / 2 + 2 });
    let spot = null;
    let first = null;
    for (const p of part.kind === 'full' ? arrowSpots(part.points, w, ht) : stubSpots(part, w, ht)) {
      const r = rectAt(p.x, p.y);
      first ||= { ...p, r };
      if (taken.some((o) => overlaps(o, r)) || otherLines.some((o) => overlaps(o, r))) continue;
      spot = { ...p, r };
      break;
    }
    if (!spot) {
      const { a, b } = segments(part.points)[0];
      spot = first || { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2, r: rectAt((a.x + b.x) / 2, (a.y + b.y) / 2) };
    }
    taken.push(spot.r);
    el.style.left = `${spot.x}px`;
    el.style.top = `${spot.y}px`;
    el.classList.toggle('in-region', regionBoxes.some((g) => g.l < spot.x && spot.x < g.r && g.t < spot.y && spot.y < g.b));
  }

  // Stubs go first: their labels have the fewest places to go, and full arrows then route around them.
  function routeAll() {
    const links = S.links;
    S.svg.setAttribute('width', S.world.offsetWidth);
    S.svg.setAttribute('height', S.world.offsetHeight);
    if (!links.length) return;
    const obstacles = $$('wf-screen, wf-decision', S.world).map(nodeBox)
      .concat($$('wf-note, wf-question', S.world).map(measure));
    placePorts(links);
    const stubs = links.filter((L) => L.stub), full = links.filter((L) => !L.stub);
    for (const L of stubs) {
      const [out, inn] = L.parts;
      Object.assign(out, { side: L.exit, inner: L.p[1], outer: move(L.p[1], L.exit, STUB_RUN), start: L.p[0] });
      out.points = simplify([L.p[0], out.inner, out.outer]);
      Object.assign(inn, { side: L.enter, inner: L.q[1], outer: move(L.q[1], L.enter, STUB_RUN) });
      inn.points = simplify([inn.outer, inn.inner, L.q[0]]);
      inn.start = inn.outer;
    }
    // Labels also keep clear of the spots where journey step markers appear (the start of each arrow).
    const markers = links.map((L) => (L.stub ? [L.p[0], L.parts[1].outer] : [L.p[0]]))
      .flat().map((p) => ({ l: p.x - 9, r: p.x + 9, t: p.y - 9, b: p.y + 9 }));
    const taken = obstacles.concat(markers);
    const regionBoxes = $$('.wf-grid', S.world).map(measure);
    const stubParts = stubs.flatMap((L) => L.parts);
    const stubLines = (except) => stubParts.filter((p) => p.link !== except).flatMap((p) => segments(p.points).map(lineBox));
    for (const part of stubParts.filter((p) => p.labelEl)) placeLabel(part, taken, stubLines(part.link), regionBoxes);

    const g = full.length && makeGrid(obstacles.concat(taken.slice(obstacles.length + markers.length)),
      full.flatMap((L) => [L.p[1], L.q[1]]));
    const used = new Set();
    const span = (L) => Math.abs(L.p[1].x - L.q[1].x) + Math.abs(L.p[1].y - L.q[1].y);
    for (const L of full.slice().sort((a, b) => span(a) - span(b))) {
      const outDir = SIDES.indexOf(L.exit), inDir = (SIDES.indexOf(L.enter) + 2) % 4;
      const mid = shortest(g, g.at(L.p[1]), outDir, g.at(L.q[1]), inDir, used);
      const inner = mid || [L.p[1], { x: L.p[1].x, y: L.q[1].y }, L.q[1]];   // no clear route: a plain elbow
      const part = L.parts[0];
      part.points = simplify([L.p[0], ...inner, L.q[0]]);
      part.start = L.p[0];
    }
    const parts = links.flatMap((L) => L.parts);
    for (const part of parts) {
      part.pathEl.setAttribute('d', pathData(part.points));
      if (part.hitEl) part.hitEl.setAttribute('d', pathData(part.points));
    }
    for (const part of parts.filter((p) => p.labelEl && p.kind === 'full')) {
      const otherLines = parts.filter((p) => p.link !== part.link).flatMap((p) => segments(p.points).map(lineBox));
      placeLabel(part, taken, otherLines, regionBoxes);
    }
  }

  // ---------- Checks on the drawn board ----------
  function checkGeometry() {
    const P = [];
    const add = (level, code, message) => P.push({ level, code, message });
    const nodes = $$('wf-screen, wf-decision', S.world);
    const box = new Map(nodes.map((n) => [n, measure(n)]));
    const sameCell = (a, b) => S.sameCell.includes(S.cells.get(a)) || S.sameCell.includes(S.cells.get(b));
    for (let i = 0; i < nodes.length; i++) {
      for (let k = i + 1; k < nodes.length; k++) {
        const a = nodes[i], b = nodes[k];
        if (overlaps(box.get(a), box.get(b)) && !sameCell(a, b)) add('error', 'overlap', `${a.id || nameOf(a)} and ${b.id || nameOf(b)} overlap`);
      }
    }

    // Text that does not fit: report the innermost parts that overflow, once each.
    for (const node of nodes) {
      const over = [];
      for (const el of [node, ...node.querySelectorAll('*')]) {
        if (!(el instanceof HTMLElement) || !el.textContent.trim()) continue;   // icons draw outside their box on purpose
        const cs = getComputedStyle(el);
        if (cs.display === 'inline' || cs.display === 'none' || cs.textOverflow === 'ellipsis') continue;
        if (/auto|scroll/.test(cs.overflowX + cs.overflowY)) continue;
        const by = Math.max(el.scrollWidth - el.clientWidth, el.scrollHeight - el.clientHeight);
        if (by > 1) over.push({ el, by });
      }
      for (const o of over) {
        if (over.some((x) => x !== o && o.el.contains(x.el))) continue;
        const what = o.el === node ? 'the content' : `<${o.el.localName}>`;
        add('error', 'overflow', `${node.localName.slice(3)} ${node.id || nameOf(node)}: ${what} overflows by ${Math.round(o.by)}px`);
      }
    }

    for (const L of S.links) {
      const crossed = new Set();
      for (const part of L.parts) {
        for (const s of segments(part.points)) {
          const line = { l: Math.min(s.a.x, s.b.x), r: Math.max(s.a.x, s.b.x), t: Math.min(s.a.y, s.b.y), b: Math.max(s.a.y, s.b.y) };
          line.r += line.r === line.l ? 0.5 : 0; line.b += line.b === line.t ? 0.5 : 0;
          for (const n of nodes) {
            if (n === L.fromNode || n === L.toNode) continue;
            const o = box.get(n);
            if (overlaps(line, { l: o.l + 1, r: o.r - 1, t: o.t + 1, b: o.b - 1 })) crossed.add(n);
          }
        }
      }
      for (const n of crossed) add('error', 'arrow-crosses-screen', `${L.tag}: arrow crosses ${n.localName.slice(3)} ${n.id || nameOf(n)}`);
    }

    const labels = S.links.flatMap((L) => L.parts.filter((p) => p.labelEl).map((p) => ({ L, el: p.labelEl, r: measure(p.labelEl) })));
    const notes = $$('wf-note, wf-question', S.world).map(measure);
    labels.forEach((a, i) => {
      const what = labels.slice(i + 1).some((b) => overlaps(a.r, b.r)) ? 'another label'
        : notes.some((n) => overlaps(a.r, n)) ? 'a note' : null;
      if (what) add('warn', 'label-overlap', `${a.L.tag}: label "${a.el.textContent}" overlaps ${what}`);
    });
    S.geo = P;
  }

  // ---------- 6. Journey focus ----------
  // j is a journey, or {nodes, path} for a hovered stub, or null for no focus.
  function show(j) {
    S.board.classList.toggle('lofi-focus', !!j);
    const nodes = j ? j.nodes : new Set();
    const on = new Map(j ? j.path.map((p) => [p.link, p.n]) : []);
    for (const [node, cell] of S.cells) cell.classList.toggle('on', nodes.has(node));
    S.steps.replaceChildren();
    for (const L of S.links) {
      const isOn = on.has(L);
      for (const part of L.parts) {
        part.pathEl.classList.toggle('on', isOn);
        part.pathEl.setAttribute('marker-end', `url(#${isOn ? 'lofi-arrow-on' : 'lofi-arrow'})`);
        if (isOn) S.paths.append(part.pathEl);  // draw blue arrows on top
        if (part.labelEl) part.labelEl.classList.toggle('on', isOn);
        if (isOn && on.get(L) != null && part.start) {
          const g = svg('g', {});
          g.append(svg('circle', { cx: part.start.x, cy: part.start.y, r: 8 }), svg('text', { x: part.start.x, y: part.start.y }));
          g.lastChild.textContent = on.get(L);
          S.steps.append(g);
        }
      }
    }
    for (const x of S.journeys) {
      x.li.classList.toggle('on', x === j);
      x.li.classList.toggle('pinned', x === S.pinned);
    }
  }

  function pin(j) {
    S.pinned = j;
    show(j);
    history.replaceState(null, '', j ? `#journey=${j.n}` : location.pathname + location.search);
  }

  // ---------- Wiring ----------
  function makeParts(L, labels) {
    const kinds = L.stub ? ['out', 'in'] : ['full'];
    L.parts = kinds.map((kind) => {
      const part = { kind, link: L };
      part.pathEl = svg('path', { class: `wf-arrow${L.stub ? ' wf-stub' : ''}`, 'marker-end': 'url(#lofi-arrow)' });
      S.paths.append(part.pathEl);
      const text = kind === 'out' ? `${L.label ? `${L.label} ` : ''}to ${nameOf(L.toNode)}`
        : kind === 'in' ? `from ${nameOf(L.fromNode)}` : L.label;
      if (text) {
        part.labelEl = h('div', `wf-linklabel${L.stub ? ' wf-stublabel' : ''}`, esc(text));
        labels.append(part.labelEl);
      }
      if (L.stub) {
        // Hover either stub: both stubs and both ends light up. Click: go to the other end.
        part.hitEl = svg('path', { class: 'wf-stub-hit' });
        S.svg.append(part.hitEl);
        const focus = { nodes: new Set([L.fromNode, L.toNode]), path: [{ link: L, n: null }] };
        for (const el of [part.hitEl, part.labelEl]) {
          el.addEventListener('mouseenter', () => show(focus));
          el.addEventListener('mouseleave', () => show(S.pinned));
          el.addEventListener('click', () => panTo(kind === 'out' ? L.toNode : L.fromNode));
        }
      }
      return part;
    });
  }

  // Route the arrows, restore the journey focus, and check the drawn board.
  function redraw() {
    routeAll();
    show(S.pinned);
    checkGeometry();
    updateBadge();
  }

  let queued = false;
  function relayout() {
    if (queued) return;
    queued = true;
    requestAnimationFrame(() => {
      queued = false;
      redraw();
    });
  }

  function init(board) {
    S.board = board;
    S.sameCell = [];
    checkTags(board);
    upgrade(board);

    S.world = h('div', 'lofi-world');
    S.canvas = h('div', 'lofi-canvas');
    S.sizer = h('div', 'lofi-sizer');
    S.sizer.append(S.world);
    S.canvas.append(S.sizer);
    board.append(S.canvas);
    const regions = $$(':scope > wf-region', board);
    regions.forEach((region, i) => { layoutRegion(region, i + 1); S.world.append(region); });
    attachNotes(regions);

    S.svg = svg('svg', { class: 'lofi-links' });
    const arrowHead = (id) => `<marker id="${id}" viewBox="0 0 8 8" refX="7.5" refY="4" markerWidth="8" markerHeight="8" ` +
      'markerUnits="userSpaceOnUse" orient="auto"><path d="M0,0.5 L8,4 L0,7.5 z"/></marker>';
    S.svg.innerHTML = `<defs>${arrowHead('lofi-arrow')}${arrowHead('lofi-arrow-on')}</defs><g class="lofi-paths"></g><g class="lofi-steps"></g>`;
    S.paths = S.svg.querySelector('.lofi-paths');
    S.steps = S.svg.querySelector('.lofi-steps');
    const labels = h('div', 'lofi-labels');
    S.world.append(S.svg, labels);

    S.links = readLinks(board);
    for (const L of S.links) makeParts(L, labels);
    S.journeys = readJourneys(board, S.links);
    checkScreens();

    const tools = buildTools(board);
    S.zoomLabel = tools.querySelector('.lofi-zoom');
    S.badge = tools.querySelector('.lofi-badge');
    board.append(buildPanel(board, regions), tools);

    wirePan();
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape') pin(null); });
    fit();
    routeAll();
    const m = location.hash.match(/journey=(\d+)/);
    const j = m && S.journeys[Number(m[1]) - 1];
    if (j) pin(j); else show(null);
  }

  // Lay out, then wait for fonts and one frame, then route and check again with final sizes.
  async function start() {
    try {
      const board = document.querySelector('wf-board');
      if (board) {
        init(board);
        await document.fonts.ready;
        await new Promise((r) => requestAnimationFrame(r));
        fit();
        redraw();
        new ResizeObserver(relayout).observe(S.world);
        window.addEventListener('resize', relayout);
      }
    } catch (e) {
      setTimeout(() => { throw e; });   // surfaces as a page error; ready still resolves
    }
    resolveReady();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
  else start();
})();
