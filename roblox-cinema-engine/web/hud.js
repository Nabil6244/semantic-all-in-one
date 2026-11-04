// On-screen text: subtitles with the spoken word lit, date tile, place tag, chapter card, statistic callouts, map labels and the
// music credit. Plain DOM over the canvas; every element is a pure function of the film time t (frames render in any order).
const $ = (tag, cls, parent) => { const e = document.createElement(tag); if (cls) e.className = cls; if (parent) parent.appendChild(e); return e; };
const fade = (t, a, b, f = 0.3) => Math.max(0, Math.min(1, Math.min((t - a) / f, (b - t) / f)));
const find = (list, t, fn) => { for (const x of list) if (fn(x, t)) return x; return null; };

export function makeHud(root, hud, opts = {}) {
  const el = {
    sub: $('div', 'sub', root), date: $('div', 'date', root), place: $('div', 'place', root), chapter: $('div', 'chapter', root),
    stat: $('div', 'stat', root), note: $('div', 'note', root), label: $('div', 'label', root), credit: $('div', 'credit', root), pins: $('div', 'pins', root),
  };
  el.chapter.innerHTML = '<div class="k"></div><div class="h"></div><div class="d"></div>';
  el.stat.innerHTML = '<div class="v"></div><div class="l"></div>';
  el.place.innerHTML = '<div class="h"></div><div class="s"></div>';
  const last = {}; // what each element currently shows, so the DOM is only touched on change
  const setText = (e, key, text) => { if (last[key] !== text) { last[key] = text; e.textContent = text; } };
  const show = (e, key, o) => { const v = o.toFixed(2); if (last[key + 'o'] !== v) { last[key + 'o'] = v; e.style.opacity = v; e.style.display = o > 0.003 ? 'block' : 'none'; } };
  let subCard = null, subSpans = [], pinPool = [];
  const duration = opts.duration || 1e9;

  function update(t, ctx = {}) {
    // subtitles: the card that spans t; words up to the spoken one are bright
    const card = find(hud.subtitles, t, (c, tt) => tt >= c.t0 - 0.05 && tt < c.t1);
    if (card !== subCard) {
      subCard = card; el.sub.textContent = ''; subSpans = [];
      if (card) {
        let wi = 0;
        for (const line of card.lines) { const L = $('div', 'line', el.sub); for (const w of line.split(' ')) { const s = $('span', 'w', L); s.textContent = w + ' '; subSpans.push(s); wi++; } }
      }
    }
    if (card) {
      const starts = card.words.map((w) => w.start); let on = 0;
      for (let i = 0; i < starts.length; i++) if (t >= starts[i] - 0.02) on = i;
      subSpans.forEach((s, i) => { const lit = i <= on; if (s._lit !== lit) { s._lit = lit; s.classList.toggle('on', lit); } });
    }
    show(el.sub, 'sub', card ? fade(t, card.t0 - 0.05, card.t1, 0.14) : 0);

    const d = find(hud.dates, t, (x, tt) => tt >= x.t0 && tt < x.t0 + 4.8);
    if (d) setText(el.date, 'date', d.label);
    show(el.date, 'date', d ? fade(t, d.t0, d.t0 + 4.8, 0.45) : 0);

    const p = find(hud.places, t, (x, tt) => tt >= x.t0 && tt < x.t1);
    if (p) { setText(el.place.firstChild, 'ph', p.label); setText(el.place.lastChild, 'ps', p.sub || ''); }
    show(el.place, 'place', p ? fade(t, p.t0, p.t1, 0.4) : 0);

    const c = find(hud.chapters, t, (x, tt) => tt >= x.t0 && tt < x.t1);
    if (c) { setText(el.chapter.children[0], 'ck', `CHAPTER ${c.index}`); setText(el.chapter.children[1], 'ch', c.title); setText(el.chapter.children[2], 'cd', c.date || ''); }
    show(el.chapter, 'chapter', c ? fade(t, c.t0, c.t1, 0.5) : 0);

    const st = find(hud.stats, t, (x, tt) => tt >= x.t0 && tt < x.t1);
    if (st) { setText(el.stat.children[0], 'sv', st.value); setText(el.stat.children[1], 'sl', st.label); }
    show(el.stat, 'stat', st && !c ? fade(t, st.t0, st.t1, 0.4) : 0);   // a chapter card has the screen to itself

    const lb = find(hud.labels, t, (x, tt) => tt >= x.t0 && tt < x.t1 && x.kind !== 'note'), nt = find(hud.labels, t, (x, tt) => tt >= x.t0 && tt < x.t1 && x.kind === 'note');
    if (lb) setText(el.label, 'lb', lb.text);
    show(el.label, 'label', lb ? fade(t, lb.t0, lb.t1, 0.4) : 0);
    if (nt) setText(el.note, 'nt', nt.text);
    show(el.note, 'note', nt ? fade(t, nt.t0, nt.t1, 0.5) * 0.85 : 0);

    // map pin labels follow their pins on screen
    const pins = ctx.pins || [];
    while (pinPool.length < pins.length) pinPool.push($('div', 'pin', el.pins));
    pinPool.forEach((e, i) => { const q = pins[i]; if (!q) { if (e._on) { e.style.display = 'none'; e._on = false; } return; } e._on = true; e.style.display = 'block'; if (e._t !== q.text) { e._t = q.text; e.textContent = q.text; } e.style.transform = `translate(${q.x.toFixed(1)}px, ${q.y.toFixed(1)}px) translate(-50%, -100%)`; });

    if (hud.credit) { setText(el.credit, 'cr', hud.credit); show(el.credit, 'credit', fade(t, duration - 6.2, duration - 0.2, 0.6)); } else show(el.credit, 'credit', 0);
  }
  return { update, active: (t) => ({ sub: !!find(hud.subtitles, t, (c, tt) => tt >= c.t0 && tt < c.t1) }) };
}
