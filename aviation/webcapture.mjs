// Aviation web capture: node webcapture.mjs <spec.json>
// spec: {url, outdir, wants:[scroll|elements], key_sentence, timeout_ms, playwright_dir?}
// ONE throwaway headless Chromium per page. Overlays are hidden with CSS (never accepted). It reads the page text and meta, checks for a
// blank page / cookie wall / paywall, highlights the key sentence in yellow and writes:
//   scroll_strip.png  a tall strip of the page from some way above the sentence to it (aviation/webcapture.py turns it into the mp4)
//   el_*.png          lead photo, Wikipedia infobox, fleet tables
// Prints one JSON line: {ok, reason, site, title, date, text, found, strip:{path,start,end,w,h}|null, elements:[{kind,path,caption,w,h}]}
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const spec = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const W = 1280, VH = 720;

function loadPlaywright() {
  const candidates = [spec.playwright_dir, path.join(HERE, '..', 'flow-engine')].filter(Boolean);
  for (const dir of candidates) {
    try { return createRequire(path.join(dir, 'package.json'))('playwright'); } catch { /* next */ }
  }
  throw new Error('Playwright not found (expected in flow-engine/node_modules).');
}

const HIDE_CSS = `
  [id*="cookie" i],[class*="cookie" i],[id*="consent" i],[class*="consent" i],[class*="gdpr" i],[id*="gdpr" i],
  [class*="paywall" i],[id*="paywall" i],[class*="newsletter" i],[class*="modal" i],[aria-modal="true"],[role="dialog"],
  iframe[src*="consent" i],iframe[src*="cmp" i],#onetrust-banner-sdk,.fc-consent-root,#didomi-host,.qc-cmp2-container
  { display:none !important; visibility:hidden !important; }
  html,body{ overflow:auto !important; position:static !important; }`;

(async () => {
  const out = { ok: false, reason: '', site: '', title: '', date: '', text: '', found: false, strip: null, elements: [], og_image: '' };
  const wants = new Set(spec.wants || []);
  let browser;
  try {
    fs.mkdirSync(spec.outdir, { recursive: true });
    const { chromium } = loadPlaywright();
    browser = await chromium.launch({ headless: true });
    const ctx = await browser.newContext({ viewport: { width: W, height: VH }, locale: 'en-US' });
    const page = await ctx.newPage();
    const resp = await page.goto(spec.url, { waitUntil: 'domcontentloaded', timeout: spec.timeout_ms || 25000 });
    if (resp && resp.status() >= 400) throw new Error(`HTTP ${resp.status()}`);
    await page.waitForTimeout(1200);
    // rendered text BEFORE hiding: a cookie wall shows only its notice
    const rawLen = await page.evaluate(() => (document.body ? document.body.innerText : '').trim().length);
    await page.addStyleTag({ content: HIDE_CSS });
    await page.evaluate(() => {
      for (const el of Array.from(document.querySelectorAll('body *'))) {
        const cs = getComputedStyle(el);
        if ((cs.position === 'fixed' || cs.position === 'sticky') && (parseInt(cs.zIndex || '0', 10) > 10 || el.offsetHeight > 120)) {
          el.style.setProperty('display', 'none', 'important');
        }
      }
    });
    // lazy images: walk the page once
    await page.evaluate(async () => {
      const h = document.documentElement.scrollHeight;
      for (let y = 0; y < Math.min(h, 12000); y += 900) { window.scrollTo(0, y); await new Promise(r => setTimeout(r, 60)); }
      window.scrollTo(0, 0);
    });
    await page.waitForTimeout(250);
    const info = await page.evaluate(() => {
      const m = (sel) => { const e = document.querySelector(sel); return e ? (e.getAttribute('content') || '').trim() : ''; };
      const h1 = document.querySelector('h1');
      return { site: m('meta[property="og:site_name"]') || location.hostname.replace(/^www\./, '') || 'local page',
               title: m('meta[property="og:title"]') || (h1 && h1.innerText.trim()) || document.title || '',
               date: m('meta[property="article:published_time"]') || m('meta[name="date"]') || m('meta[itemprop="datePublished"]'),
               og_image: m('meta[property="og:image"]'),
               text: (document.body ? document.body.innerText : '').replace(/[ \t]+/g, ' ').replace(/\n\s*\n+/g, '\n').trim() };
    });
    out.site = info.site; out.title = info.title; out.date = info.date; out.og_image = info.og_image;
    out.text = info.text.slice(0, 60000);
    const n = info.text.length;
    const low = info.text.toLowerCase();
    if (n < 150) {
      out.reason = rawLen > n ? 'cookie wall (only the consent notice)' : 'blank page';
      throw new Error(out.reason);
    }
    if (n < 700 && /cookie|consent|gdpr/.test((await page.content()).toLowerCase()) && /accept|agree|cookies/.test(low) && rawLen > n * 1.5) {
      out.reason = 'cookie wall'; throw new Error(out.reason);
    }
    if (n < 2500 && /(subscribe to (continue|read|unlock)|sign in to read|already a subscriber|create a free account to (continue|read)|you have reached your (free )?article limit|to continue reading)/.test(low)) {
      out.reason = 'paywall'; throw new Error(out.reason);
    }

    if (wants.has('scroll')) {
      const key = (spec.key_sentence || '').trim();
      const hit = await page.evaluate((key) => {
        const norm = (s) => s.toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
        const nk = norm(key);
        if (!nk) return null;
        const mark = (el, text) => {
          // wrap the sentence inside one text node when it sits in one; else tint the whole element
          const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
          const kw = key.split(/\s+/).slice(0, 7).join(' ').toLowerCase();
          let node;
          while ((node = walker.nextNode())) {
            const v = node.nodeValue; const i = v.toLowerCase().indexOf(kw);
            if (i >= 0) {
              const j = Math.min(v.length, i + key.length);
              const r = document.createRange(); r.setStart(node, i); r.setEnd(node, j);
              const mk = document.createElement('mark');
              mk.setAttribute('data-hl', '1');
              mk.style.cssText = 'background:#ffeb3b !important;color:#000 !important;padding:2px 0;';
              r.surroundContents(mk);
              return mk;
            }
          }
          el.style.cssText += ';background:#ffeb3b !important;color:#000 !important;';
          el.setAttribute('data-hl', '1');
          return el;
        };
        const els = Array.from(document.querySelectorAll('p,li,h1,h2,h3,h4,td,dd,blockquote,figcaption,span,div'))
          .filter(e => e.offsetHeight > 0);
        // smallest element whose text holds the whole sentence
        let best = null;
        for (const e of els) {
          const t = norm(e.innerText || '');
          if (t.includes(nk) && (!best || t.length < best.len)) best = { e, len: t.length };
        }
        let how = 'exact';
        if (!best) {
          // best word overlap (>= 60%) among the small blocks
          const kws = new Set(nk.split(' ').filter(w => w.length > 3));
          let bs = 0;
          for (const e of els) {
            if (e.children.length > 6) continue;
            const ws = new Set(norm(e.innerText || '').split(' '));
            let h = 0; for (const w of kws) if (ws.has(w)) h++;
            const sc = kws.size ? h / kws.size : 0;
            if (sc > bs && sc >= 0.6) { bs = sc; best = { e, len: ws.size }; }
          }
          how = 'overlap';
        }
        if (!best) return null;
        const mk = mark(best.e, key);
        const r = mk.getBoundingClientRect();
        return { y: r.top + window.scrollY, h: r.height, how };
      }, key);
      const total = await page.evaluate(() => document.documentElement.scrollHeight);
      out.found = !!hit;
      let end;
      if (hit) end = Math.max(0, Math.min(total - VH, Math.round(hit.y + hit.h / 2 - VH / 2)));
      else end = Math.max(0, Math.min(total - VH, 1500));
      let start = Math.max(0, end - 2400);
      if (end - start < 200) end = Math.max(start, Math.min(total - VH, start + 160));
      const p = path.join(spec.outdir, 'scroll_strip.png');
      await page.evaluate(() => window.scrollTo(0, 0));
      await page.screenshot({ path: p, clip: { x: 0, y: start, width: W, height: Math.min(8000, end - start + VH, total - start) }, fullPage: true });
      out.strip = { path: p, start, end, w: W, h: Math.min(8000, end - start + VH, total - start) };
    }

    if (wants.has('elements')) {
      const cands = await page.evaluate(() => {
        const items = [];
        const vis = (e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && getComputedStyle(e).visibility !== 'hidden'; };
        const og = (document.querySelector('meta[property="og:image"]') || {}).content || '';
        const base = (u) => (u || '').split('?')[0].split('/').pop();
        const imgs = Array.from(document.querySelectorAll('img')).filter(vis).map(e => ({ e, r: e.getBoundingClientRect() }))
          .filter(o => o.r.width >= 300 && o.r.height >= 150);
        let lead = imgs.find(o => og && base(o.e.currentSrc || o.e.src) === base(og)) || imgs[0];
        const fig = (e) => { const f = e.closest('figure'); const c = f && f.querySelector('figcaption'); return (c && c.innerText.trim()) || e.alt || e.title || ''; };
        if (lead) { lead.e.setAttribute('data-wc', 'lead'); items.push({ kind: 'lead', sel: '[data-wc="lead"]', caption: fig(lead.e), src: lead.e.currentSrc || lead.e.src }); }
        // the article's own photos (Wikipedia thumbs / figures): up to 4, not inside the infobox (that is usually the logo)
        let np = 0;
        for (const e of Array.from(document.querySelectorAll('figure img, .thumb img, .mw-file-element'))) {
          if (np >= 4 || e === (lead && lead.e) || e.closest('table.infobox') || !vis(e)) continue;
          const r = e.getBoundingClientRect();
          if (r.width < 220 || r.height < 120) continue;
          e.setAttribute('data-wc', 'photo' + np);
          items.push({ kind: 'photo', sel: '[data-wc="photo' + np + '"]', caption: fig(e), src: e.currentSrc || e.src });
          np++;
        }
        const ib = document.querySelector('table.infobox');
        if (ib && vis(ib)) { ib.setAttribute('data-wc', 'infobox'); const c = ib.querySelector('caption,th'); items.push({ kind: 'infobox', sel: '[data-wc="infobox"]', caption: (c && c.innerText.trim()) || '' }); }
        let k = 0;
        for (const t of Array.from(document.querySelectorAll('table'))) {
          if (t === ib || t.classList.contains('infobox') || !vis(t) || k >= 2) continue;
          const head = (t.querySelector('thead') || t.rows[0] || t).innerText.toLowerCase();
          const cap = (t.querySelector('caption') || {}).innerText || '';
          if (/aircraft|fleet|in service/.test(head + ' ' + cap.toLowerCase()) && t.rows.length >= 2) {
            t.setAttribute('data-wc', 'table' + k);
            items.push({ kind: 'table', sel: `[data-wc="table${k}"]`, caption: cap.trim() || (head.split('\n')[0] || '').trim() });
            k++;
          }
        }
        return items;
      });
      let i = 0;
      for (const c of cands) {
        try {
          const loc = page.locator(c.sel).first();
          const box = await loc.boundingBox();
          const p = path.join(spec.outdir, `el_${i}_${c.kind}.png`);
          if (box && box.height > 2400) {
            await loc.scrollIntoViewIfNeeded();
            await page.screenshot({ path: p, clip: { x: box.x, y: box.y + await page.evaluate(() => window.scrollY), width: box.width, height: 2400 }, fullPage: true });
          } else {
            await loc.screenshot({ path: p, timeout: 8000 });
          }
          out.elements.push({ kind: c.kind, path: p, caption: c.caption.slice(0, 300), w: Math.round(box ? box.width : 0), h: Math.round(box ? Math.min(box.height, 2400) : 0) });
          i++;
        } catch { /* skip this element */ }
      }
      // lead photo not in the DOM (og:image only): fetch the file itself
      if (!out.elements.some(e => e.kind === 'lead') && info.og_image && /^https?:/.test(info.og_image)) {
        try {
          const r = await ctx.request.get(info.og_image, { timeout: 8000 });
          if (r.ok()) {
            const ct = r.headers()['content-type'] || '';
            const ext = /png/.test(ct) ? 'png' : 'jpg';
            const p = path.join(spec.outdir, `el_${i}_lead.${ext}`);
            fs.writeFileSync(p, await r.body());
            out.elements.push({ kind: 'lead', path: p, caption: info.title, w: 0, h: 0 });
          }
        } catch { /* none */ }
      }
    }
    out.ok = true;
  } catch (e) {
    if (!out.reason) out.reason = String(e && e.message || e).slice(0, 300);
  } finally {
    if (browser) await browser.close().catch(() => {});
  }
  process.stdout.write(JSON.stringify(out) + '\n');
})();
