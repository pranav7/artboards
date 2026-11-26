/*
 * clickthrough.js - the click-through kit.
 *
 * A click-through shows an app at its real size in a frame, one state at a time, with a side
 * panel that says what to click next and what is new. The file holds only content:
 *   <template ct-head>  the app's own <style> and <link> elements, plus <ct-html> and <ct-body>,
 *                       whose attributes go on the app's <html> and <body>
 *   <ct-step>           one state: the panel text (ct-hint, ct-new, ct-note, ct-question) and the
 *                       app markup for that state in a <template>
 * The app renders in an iframe. Its CSS, media queries and vh units see the frame's real size,
 * and the kit's CSS and the app's CSS never meet. On DOMContentLoaded this script:
 *   1. reads the steps and checks the tags, ids, moves and hints   (checkTags, readFlow, checkSteps)
 *   2. builds the frame and the side panel                           (build, buildPanel)
 *   3. shows the step that #step=<id> names, or the first step       (show)
 * In the frame, a click on an element with data-go="<id>" shows that step. A ring marks each
 * control that the step's hint names with <ct-control>. Attributes that capture writes:
 * data-scroll-top and data-scroll-left (scroll offsets) and data-top-layer (an open popover or
 * modal dialog).
 *
 * window.ct.ready resolves when the first step is on screen. window.ct.problems() resolves to
 * the list of problems; it renders each step in a hidden frame to measure it.
 */
(function () {
  'use strict';

  // Every kit tag. skills/artboard/clickthrough.md documents exactly these; a test checks that.
  const TAGS = ['ct-flow', 'ct-intro', 'ct-step', 'ct-hint', 'ct-control', 'ct-new', 'ct-note',
    'ct-question', 'ct-html', 'ct-body'];
  // The parent each tag must have. ct-control may sit anywhere inside its ct-hint.
  const PARENT = {
    'ct-intro': 'ct-flow', 'ct-step': 'ct-flow', 'ct-hint': 'ct-step', 'ct-new': 'ct-step',
    'ct-note': 'ct-step', 'ct-question': 'ct-step', 'ct-control': 'ct-hint',
  };
  // The elements a hint can name. The name of one is its data-control, aria-label or title, else its text.
  const CONTROLS = '[data-control], [data-go], button, a, [role], input, select, textarea, label, summary';
  const PAD = 24;       // space around the frame and the panel
  const GAP = 24;       // space between the frame and the panel
  const PANEL = 340;    // panel width
  const RING = 4;       // the ring sits this far outside the control it marks
  const SETTLE_MS = 3000;   // the longest wait for images to decode

  const S = { steps: [], byId: new Map(), problems: [], current: null, controls: [], scale: 1 };

  let resolveReady;
  window.ct = {
    tags: TAGS.slice(),
    steps: [],                       // step ids, in order
    size: { width: 0, height: 0 },   // the page size that shows the frame at 100%
    get current() { return S.current ? S.current.id : null; },
    ready: new Promise((resolve) => { resolveReady = resolve; }),
    go(id) {
      const step = S.byId.get(String(id));
      if (!step) return Promise.reject(new Error('no step has id "' + id + '"'));
      show(step);
      return settle();
    },
    async problems() {
      await window.ct.ready;
      const all = S.problems.concat(S.doc ? await measure() : []);
      const q = S.steps.reduce((n, s) => n + s.questions.length, 0);
      if (q) all.push({ level: 'info', code: 'open-questions', message: q + ' open question' + (q === 1 ? '' : 's') });
      return all.map((p) => ({ ...p }));
    },
  };

  // ---------- Small helpers ----------
  const $ = (sel, root) => (root || document).querySelector(sel);
  const $$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));
  const attr = (el, name, fallback = '') => el.getAttribute(name) ?? fallback;
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const norm = (s) => String(s || '').replace(/\s+/g, ' ').trim().toLowerCase();
  const report = (level, code, message) => S.problems.push({ level, code, message });
  const label = (step) => 'step ' + step.id + (step.name !== step.id ? ' "' + step.name + '"' : '');
  const frame = () => new Promise((resolve) => requestAnimationFrame(() => resolve()));
  function h(tag, cls) {
    const el = document.createElement(tag);
    if (cls) el.className = cls;
    return el;
  }
  function size(el, name, fallback) {
    const n = parseInt(attr(el, name), 10);
    return n > 0 ? n : fallback;
  }

  // ---------- 1. Read and check ----------
  function checkTags() {
    for (const el of $$('*')) {
      const tag = el.localName;
      if (!tag.startsWith('ct-') || tag === 'ct-flow') continue;
      if (!TAGS.includes(tag)) report('error', 'unknown-tag', '<' + tag + '> is not a kit tag');
      else if (!PARENT[tag]) report('error', 'misplaced-tag', '<' + tag + '> goes inside <template ct-head>');
      else if (tag === 'ct-control' ? !el.closest('ct-hint') : el.parentElement.localName !== PARENT[tag]) {
        report('error', 'misplaced-tag', '<' + tag + '> must be ' + (tag === 'ct-control' ? 'inside' : 'directly inside') +
          ' <' + PARENT[tag] + '>');
      }
    }
    if ($$('ct-flow').length > 1) report('error', 'misplaced-tag', 'the file has more than one <ct-flow>');
  }

  // Kit tags inside a template: only <ct-html> and <ct-body>, and only in the head template.
  function checkTemplate(content, where, allowed) {
    for (const el of $$('*', content)) {
      const tag = el.localName;
      if (!tag.startsWith('ct-') || allowed.includes(tag)) continue;
      if (!TAGS.includes(tag)) report('error', 'unknown-tag', '<' + tag + '> in ' + where + ' is not a kit tag');
      else report('error', 'misplaced-tag', '<' + tag + '> is inside ' + where +
        (PARENT[tag] ? '; put it directly inside <' + PARENT[tag] + '>' : ''));
    }
  }

  function readFlow(flow) {
    S.name = attr(flow, 'name') || document.title || 'Click-through';
    S.width = size(flow, 'width', 1440);
    S.height = size(flow, 'height', 900);
    const intro = $(':scope > ct-intro', flow);
    S.intro = intro ? intro.innerHTML.trim() : '';

    const head = $(':scope > template[ct-head]', flow);
    S.head = head ? head.content.cloneNode(true) : document.createDocumentFragment();
    checkTemplate(S.head, 'the head template', ['ct-html', 'ct-body']);
    const attrsOf = (tag) => {
      const el = $(tag, S.head);
      if (!el) return [];
      el.remove();
      return Array.from(el.attributes, (a) => [a.name, a.value]);
    };
    S.htmlAttrs = attrsOf('ct-html');
    S.bodyAttrs = attrsOf('ct-body');

    $$(':scope > ct-step', flow).forEach(readStep);
    if (!S.steps.length) report('error', 'missing-step', 'the flow has no <ct-step>');
    window.ct.steps = S.steps.map((s) => s.id);
    window.ct.size = { width: 2 * PAD + S.width + GAP + PANEL, height: 2 * PAD + S.height };
  }

  function readStep(el, i) {
    const id = attr(el, 'id').trim();
    const part = (tag) => { const p = $(':scope > ' + tag, el); return p ? p.innerHTML.trim() : ''; };
    const tpl = $(':scope > template', el);
    const step = {
      id: id || '(' + (i + 1) + ')',
      name: attr(el, 'name').trim() || id || 'Step ' + (i + 1),
      isNew: el.hasAttribute('new'),
      branch: el.hasAttribute('branch'),
      base: attr(el, 'base').trim(),
      hint: $(':scope > ct-hint', el),
      news: part('ct-new'),
      note: part('ct-note'),
      questions: $$(':scope > ct-question', el).map((q) => q.innerHTML.trim()),
      content: tpl ? tpl.content : document.createDocumentFragment(),
    };
    if (!id) report('error', 'missing-id', 'step ' + (i + 1) + ' ("' + step.name + '") has no id');
    else if (S.byId.has(id)) report('error', 'duplicate-id', 'two steps have id "' + id + '"');
    if (!S.byId.has(step.id)) S.byId.set(step.id, step);
    checkTemplate(step.content, 'the app markup of ' + label(step), []);
    S.steps.push(step);
  }

  // The steps whose markup the frame shows for a step: its base steps first, then the step.
  function chain(step) {
    const out = [];
    for (let s = step; s && !out.includes(s); s = S.byId.get(s.base)) out.unshift(s);
    return out;
  }

  // The markup of a step, base steps included, as an inert fragment.
  function markup(step) {
    const box = document.createElement('template');
    for (const s of chain(step)) box.content.append(s.content.cloneNode(true));
    return box.content;
  }

  function controlName(el) {
    for (const name of ['data-control', 'aria-label', 'title']) if (el.hasAttribute(name)) return el.getAttribute(name);
    if (el.localName === 'input') return el.value || attr(el, 'placeholder');
    return el.textContent;
  }

  // The control that a hint names: one with data-control first, then one with data-go, then the
  // innermost. Of two such controls, the last one: a step's own markup comes after its base's,
  // so a button in a dialog wins over a button with the same name under the dialog.
  function findControl(root, text) {
    const want = norm(text);
    if (!want) return null;
    const hits = $$(CONTROLS, root).filter((el) => norm(controlName(el)) === want);
    return hits.findLast((el) => el.hasAttribute('data-control')) ||
      hits.findLast((el) => el.hasAttribute('data-go')) ||
      hits.findLast((el) => !hits.some((other) => other !== el && el.contains(other))) || null;
  }

  function checkSteps() {
    for (const step of S.steps) {
      if (step.base && !S.byId.has(step.base)) {
        report('error', 'missing-step', label(step) + ': base="' + step.base + '" names no step');
        step.base = '';
      }
    }
    // Follow the bases until one repeats. A loop is reported once, on the first of its steps.
    for (const step of S.steps) {
      const path = [step];
      let s = S.byId.get(step.base);
      while (s && !path.includes(s)) {
        path.push(s);
        s = S.byId.get(s.base);
      }
      if (s === step) {
        report('error', 'base-loop', label(step) + ': its base steps go round in a loop (' +
          path.concat(step).map((p) => p.id).join(' > ') + ')');
        step.base = '';
      }
    }

    for (const step of S.steps) {
      const root = markup(step);
      step.moves = new Set();
      const named = new Set();
      for (const el of $$('[data-go]', root)) {
        const to = attr(el, 'data-go').trim();
        if (!S.byId.has(to)) {
          if (!named.has(to)) report('error', 'missing-step', label(step) + ': data-go="' + to + '" names no step');
          named.add(to);
        } else if (to !== step.id) {
          step.moves.add(to);
        }
      }
      for (const c of step.hint ? $$('ct-control', step.hint) : []) {
        if (!findControl(root, c.textContent)) {
          report('error', 'missing-control', label(step) + ': the hint names "' + c.textContent.trim() +
            '", but no control in the step has that name');
        }
      }
    }

    // Walk the moves from the first step. A step the walk does not find cannot be reached by clicking.
    const reached = new Set();
    const todo = S.steps.slice(0, 1).map((s) => s.id);
    while (todo.length) {
      const id = todo.pop();
      if (reached.has(id)) continue;
      reached.add(id);
      todo.push(...S.byId.get(id).moves);
    }
    S.steps.forEach((step, i) => {
      const last = i === S.steps.length - 1;
      if (!reached.has(step.id)) report('error', 'unreached-step', label(step) + ': no move leads to it from the first step');
      if (!last && !step.moves.size) report('error', 'dead-end', label(step) + ': no data-go leads on from it. Only the last step may end the flow');
      if (!last && !(step.hint && step.hint.textContent.trim())) report('warn', 'no-hint', label(step) + ' has no hint: say what to click next in <ct-hint>');
    });
  }

  // ---------- 2. Frame and panel ----------
  // An empty standards-mode document in the iframe, with the app's head and <html> and <body> attributes.
  function openDoc(iframe) {
    const doc = iframe.contentDocument;
    doc.open();
    doc.write('<!doctype html><html><head><meta charset="utf-8"></head><body></body></html>');
    doc.close();
    const put = (el, pairs) => pairs.forEach(([k, v]) => { try { el.setAttribute(k, v); } catch (e) { /* a name the DOM refuses */ } });
    put(doc.documentElement, S.htmlAttrs);
    put(doc.body, S.bodyAttrs);
    doc.head.append(doc.importNode(S.head, true));
    const kit = doc.createElement('style');
    kit.textContent = '[data-go] { cursor: pointer; }';
    doc.head.append(kit);
    return doc;
  }

  // Put a step's markup in a frame document, and scroll each element that a capture saw scrolled.
  function fill(doc, step) {
    doc.body.replaceChildren(...chain(step).map((s) => doc.importNode(s.content, true)));
    for (const el of $$('[data-scroll-top], [data-scroll-left]', doc)) {
      el.scrollTop = Number(attr(el, 'data-scroll-top', '0')) || 0;
      el.scrollLeft = Number(attr(el, 'data-scroll-left', '0')) || 0;
    }
    // A data-go element that is not a link, button or field gets keyboard focus too.
    for (const el of $$('[data-go]', doc)) {
      if (!el.matches('a[href], button, input, select, textarea, [tabindex]')) el.tabIndex = 0;
    }
    // Capture marks an open popover or modal dialog, because no attribute keeps it in the top layer.
    for (const el of $$('[data-top-layer]', doc)) {
      try {
        if (attr(el, 'data-top-layer') === 'modal') {
          el.removeAttribute('open');
          el.showModal();
        } else {
          el.showPopover();
        }
      } catch (e) { /* not a dialog or a popover */ }
    }
  }

  // Resolves when each linked stylesheet of a frame document has loaded or failed.
  function sheetsLoaded(doc) {
    const pending = $$('link[rel~="stylesheet"]', doc).filter((link) => !link.sheet).map((link) =>
      new Promise((resolve) => {
        link.addEventListener('load', resolve, { once: true });
        link.addEventListener('error', resolve, { once: true });
      }));
    return Promise.race([Promise.all(pending), new Promise((r) => setTimeout(r, SETTLE_MS))]);
  }

  function build(flow) {
    const shell = h('div', 'ct-shell');
    S.stage = h('div', 'ct-stage');
    S.frame = h('div', 'ct-frame');
    S.frame.style.width = S.width + 'px';
    S.frame.style.height = S.height + 'px';
    S.iframe = h('iframe');
    S.iframe.title = S.name;
    S.rings = h('div', 'ct-rings');
    S.frame.append(S.iframe, S.rings);
    S.stage.append(S.frame);
    S.panel = buildPanel();
    shell.append(S.stage, S.panel);
    flow.append(shell);

    S.doc = openDoc(S.iframe);
    const doc = S.doc;
    doc.addEventListener('click', (e) => {
      const go = e.target.closest && e.target.closest('[data-go]');
      // Links and forms in captured markup lead out of the click-through. Only data-go moves.
      if (go || (e.target.closest && e.target.closest('a[href]'))) e.preventDefault();
      const step = go && S.byId.get(attr(go, 'data-go').trim());
      if (step && step !== S.current) show(step);
    });
    doc.addEventListener('submit', (e) => e.preventDefault());
    doc.addEventListener('keydown', onKey);
    for (const type of ['scroll', 'load', 'animationend', 'transitionend']) doc.addEventListener(type, placeRings, true);
    doc.fonts.addEventListener('loadingdone', placeRings);
    new doc.defaultView.ResizeObserver(placeRings).observe(doc.documentElement);

    document.addEventListener('keydown', onKey);
    window.addEventListener('resize', fit);
    window.addEventListener('hashchange', () => {
      const step = stepFromHash();
      if (step && step !== S.current) show(step);
    });
    fit();
  }

  function buildPanel() {
    const panel = h('aside', 'ct-panel');
    panel.setAttribute('aria-label', 'Steps');
    const item = (s, i) => '<li><button type="button" class="ct-step' + (s.branch ? ' is-branch' : '') +
      '" data-index="' + i + '"><span class="ct-num">' + esc(s.id) + '</span><span class="ct-name">' + esc(s.name) +
      '</span>' + (s.isNew ? '<span class="ct-tag">new</span>' : '') + '</button></li>';
    panel.innerHTML =
      '<h1 class="ct-title">' + esc(S.name) + '</h1>' +
      (S.intro ? '<div class="ct-intro">' + S.intro + '</div>' : '') +
      '<ol class="ct-steps">' + S.steps.map(item).join('') + '</ol>' +
      '<div class="ct-tools"><button type="button" class="ct-restart">Restart</button>' +
      '<span class="ct-scale"></span><span><kbd>J</kbd> next <kbd>K</kbd> back</span></div>' +
      '<section class="ct-current" aria-live="polite"></section>';
    panel.addEventListener('click', (e) => {
      const b = e.target.closest('button');
      if (!b) return;
      if (b.classList.contains('ct-restart')) show(S.steps[0]);
      else if (b.dataset.index) show(S.steps[Number(b.dataset.index)]);
    });
    return panel;
  }

  function renderPanel(step) {
    $$('.ct-step', S.panel).forEach((b) => {
      const on = S.steps[Number(b.dataset.index)] === step;
      b.classList.toggle('is-current', on);
      b.setAttribute('aria-current', on ? 'step' : 'false');
    });
    const hint = step.hint && step.hint.textContent.trim() ? step.hint.innerHTML.trim() : '';
    $('.ct-current', S.panel).innerHTML =
      (hint ? '<p class="ct-hint">' + hint + '</p>' : '') +
      (step.news ? '<h2 class="ct-h">What is new</h2><div class="ct-new">' + step.news + '</div>' : '') +
      (step.note ? '<div class="ct-note">' + step.note + '</div>' : '') +
      (step.questions.length ? '<h2 class="ct-h">Open questions</h2><ul class="ct-questions">' +
        step.questions.map((q) => '<li>' + q + '</li>').join('') + '</ul>' : '');
  }

  // Scale the frame down when the window is too narrow for the frame and the panel. Never up.
  function fit() {
    const room = document.documentElement.clientWidth - 2 * PAD - GAP - PANEL;
    S.scale = Math.max(0.25, Math.min(1, room / S.width));
    S.frame.style.transform = S.scale < 1 ? 'scale(' + S.scale + ')' : '';
    S.stage.style.width = S.width * S.scale + 'px';
    S.stage.style.height = S.height * S.scale + 'px';
    $('.ct-scale', S.panel).textContent = S.scale < 1 ? 'Shown at ' + Math.round(S.scale * 100) + '%' : '';
  }

  // ---------- 3. Moves and the ring ----------
  function show(step) {
    if (!step) return;
    S.current = step;
    fill(S.doc, step);
    renderPanel(step);
    const hash = '#step=' + encodeURIComponent(step.id);
    if (location.hash !== hash) history.replaceState(null, '', hash);
    S.controls = (step.hint ? $$('ct-control', step.hint) : [])
      .map((c) => findControl(S.doc.body, c.textContent)).filter(Boolean);
    if (S.controls.length) reveal(S.controls[0]);
    placeRings();
  }

  function stepFromHash() {
    const m = location.hash.match(/[#&]step=([^&]*)/);
    if (!m) return null;
    try { return S.byId.get(decodeURIComponent(m[1])) || null; } catch (e) { return null; }
  }

  function move(by) {
    const i = S.steps.indexOf(S.current) + by;
    if (i >= 0 && i < S.steps.length) show(S.steps[i]);
  }

  function onKey(e) {
    if (e.defaultPrevented || e.metaKey || e.ctrlKey || e.altKey) return;
    const t = e.target;
    if (t && (t.isContentEditable || /^(input|textarea|select)$/.test(t.localName || ''))) return;
    const key = e.key.toLowerCase();
    if (key === 'j' || key === 'k') {
      e.preventDefault();
      move(key === 'j' ? 1 : -1);
    } else if ((key === 'enter' || key === ' ') && t && t.matches && t.matches('[data-go]:not(a[href], button)')) {
      e.preventDefault();
      t.click();
    }
  }

  // Scroll the frame's own scroll boxes until a control is in view. Never scroll the page around the frame.
  function reveal(el) {
    const view = S.doc.defaultView;
    const root = S.doc.scrollingElement || S.doc.documentElement;
    for (let p = el.parentElement; p; p = p.parentElement) {
      const isRoot = p === root;
      if (!isRoot && !/(auto|scroll|overlay)/.test(view.getComputedStyle(p).overflowY)) continue;
      if (p.scrollHeight <= p.clientHeight + 1) continue;
      const r = el.getBoundingClientRect();
      const top = isRoot ? 0 : p.getBoundingClientRect().top + p.clientTop;
      const bottom = isRoot ? view.innerHeight : top + p.clientHeight;
      if (r.top < top) p.scrollTop -= top - r.top + PAD;
      else if (r.bottom > bottom) p.scrollTop += Math.min(r.bottom - bottom + PAD, r.top - top - PAD);
    }
  }

  // One ring around each control that the hint names, in frame coordinates. A ring stays inside
  // the frame, so a control as wide as the frame still shows all four sides of its ring.
  function placeRings() {
    if (!S.rings) return;
    const view = S.doc.defaultView;
    const boxes = S.controls.filter((el) => el.isConnected).map((el) => {
      const r = el.getBoundingClientRect();
      if (!r.width && !r.height) return null;
      const left = Math.max(0, r.left - RING);
      const top = Math.max(0, r.top - RING);
      const right = Math.min(S.width, r.right + RING);
      const bottom = Math.min(S.height, r.bottom + RING);
      if (right <= left || bottom <= top) return null;
      const radius = parseFloat(view.getComputedStyle(el).borderTopLeftRadius) || 0;
      return { left, top, width: right - left, height: bottom - top, radius: radius ? radius + RING : 0 };
    }).filter(Boolean);
    while (S.rings.children.length > boxes.length) S.rings.lastChild.remove();
    while (S.rings.children.length < boxes.length) S.rings.append(h('div', 'ct-ring'));
    boxes.forEach((b, i) => {
      const s = S.rings.children[i].style;
      s.left = b.left + 'px';
      s.top = b.top + 'px';
      s.width = b.width + 'px';
      s.height = b.height + 'px';
      s.borderRadius = b.radius + 'px';
    });
  }

  // Fonts loaded, images decoded, and each entry animation at its end, so a measure or a
  // screenshot sees the final state. A looping animation cannot finish, and keeps running.
  async function settleDoc(doc) {
    await doc.fonts.ready;
    const images = $$('img', doc).map((img) => img.decode().catch(() => {}));
    await Promise.race([Promise.all(images), new Promise((r) => setTimeout(r, SETTLE_MS))]);
    for (const a of doc.getAnimations()) {
      try { a.finish(); } catch (e) { /* an infinite animation */ }
    }
    await frame();
  }

  async function settle() {
    fit();
    await settleDoc(S.doc);
    placeRings();
  }

  // ---------- Problems that need layout ----------
  function describe(el) {
    const cls = Array.from(el.classList).slice(0, 2).map((c) => '.' + c).join('');
    const text = (el.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 30);
    return el.localName + (el.id ? '#' + el.id : '') + cls + (text ? ' "' + text + '"' : '');
  }

  // The outermost elements that reach past the frame, skipping what a clipping box hides.
  function overflowing(doc) {
    const view = doc.defaultView;
    const out = [];
    const walk = (el) => {
      for (const c of el.children) {
        if (out.length >= 3) return;
        const r = c.getBoundingClientRect();
        if (r.right > S.width + 1 || r.bottom > S.height + 1) out.push(c);
        else if (view.getComputedStyle(c).overflow === 'visible') walk(c);
      }
    };
    walk(doc.body);
    return out;
  }

  // Render each step in a hidden frame of the same size, and report a step whose content does not fit.
  async function measure() {
    const out = [];
    const probe = h('iframe');
    probe.setAttribute('aria-hidden', 'true');
    probe.style.cssText = 'position: fixed; left: ' + -(S.width + 1000) + 'px; top: 0; width: ' + S.width +
      'px; height: ' + S.height + 'px; border: 0; visibility: hidden;';
    document.body.append(probe);
    try {
      const doc = openDoc(probe);
      await sheetsLoaded(doc);
      for (const step of S.steps) {
        fill(doc, step);
        await settleDoc(doc);
        const root = doc.scrollingElement || doc.documentElement;
        const right = root.scrollWidth - S.width;
        const down = root.scrollHeight - S.height;
        if (right > 1 || down > 1) {
          const by = [right > 1 && right + 'px to the right', down > 1 && down + 'px down'].filter(Boolean).join(' and ');
          const els = overflowing(doc).map(describe);
          out.push({ level: 'warn', code: 'frame-overflow', message: label(step) + ': the content runs ' + by +
            ' past the ' + S.width + ' x ' + S.height + ' frame' + (els.length ? ' (' + els.join(', ') + ')' : '') });
        }
      }
    } finally {
      probe.remove();
    }
    return out;
  }

  // ---------- Start ----------
  async function start() {
    try {
      const flow = document.querySelector('ct-flow');
      if (flow) {
        checkTags();
        readFlow(flow);
        checkSteps();
        build(flow);
        await sheetsLoaded(S.doc);
        const first = stepFromHash() || S.steps[0];
        if (first) {
          show(first);
          await settle();
        }
      }
    } catch (e) {
      setTimeout(() => { throw e; });   // surfaces as a page error; ready still resolves
    }
    resolveReady();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
  else start();
})();
