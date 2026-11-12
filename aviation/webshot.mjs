// Aviation website screenshot: node webshot.mjs <spec.json>
// spec: {url, out, width, height, timeout_ms, playwright_dir?}
// A throwaway headless Chromium (Playwright from flow-engine) opens the page, hides fixed overlays (cookie bars, pop-ups, sign-up
// walls) with CSS - it never clicks "accept" - and screenshots the top of the article around its headline. Prints one JSON line:
// {ok, path, site, title, date, headline_box:[x,y,w,h] (in the shot), reason}
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const spec = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));

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
  const out = { ok: false, path: spec.out, site: '', title: '', date: '', headline_box: null, reason: '' };
  let browser;
  try {
    const { chromium } = loadPlaywright();
    browser = await chromium.launch({ headless: true });
    const ctx = await browser.newContext({ viewport: { width: spec.width || 1280, height: spec.height || 1600 }, locale: 'en-US' });
    const page = await ctx.newPage();
    const resp = await page.goto(spec.url, { waitUntil: 'domcontentloaded', timeout: spec.timeout_ms || 25000 });
    if (resp && resp.status() >= 400) throw new Error(`HTTP ${resp.status()}`);
    await page.waitForTimeout(1800);
    await page.addStyleTag({ content: HIDE_CSS });
    // anything still pinned over the page (position fixed / sticky, high z-index or tall) goes too
    await page.evaluate(() => {
      for (const el of Array.from(document.querySelectorAll('body *'))) {
        const cs = getComputedStyle(el);
        if ((cs.position === 'fixed' || cs.position === 'sticky') && (parseInt(cs.zIndex || '0', 10) > 10 || el.offsetHeight > 120)) {
          el.style.setProperty('display', 'none', 'important');
        }
      }
      window.scrollTo(0, 0);
    });
    await page.waitForTimeout(300);
    const meta = await page.evaluate(() => {
      const m = (sel) => { const e = document.querySelector(sel); return e ? (e.getAttribute('content') || '').trim() : ''; };
      // the headline: the heading whose words best match the page's own title tag (a site's logo is often its first <h1>)
      const want = (m('meta[property="og:title"]') || document.title || '').toLowerCase();
      const words = new Set(want.split(/[^a-z0-9]+/).filter(w => w.length > 2));
      const score = (el) => { const ws = (el.innerText || '').toLowerCase().split(/[^a-z0-9]+/).filter(w => w.length > 2);
                              if (!ws.length) return 0; let hit = 0; for (const w of ws) if (words.has(w)) hit++;
                              return hit / Math.max(words.size, ws.length); };
      const cands = Array.from(document.querySelectorAll('h1, h2, [itemprop="headline"], [class*="headline" i], [class*="entry-title" i], [class*="article-title" i]'))
        .filter(el => el.offsetHeight > 0 && (el.innerText || '').trim().length > 8);
      let h1 = null, best = 0;
      for (const el of cands) { const sc = score(el); if (sc > best) { best = sc; h1 = el; } }
      if (!h1 || best < 0.3) h1 = document.querySelector('h1');
      const r = h1 ? h1.getBoundingClientRect() : null;
      return { site: m('meta[property="og:site_name"]') || location.hostname.replace(/^www\./, ''),
               title: (h1 && best >= 0.3 && h1.innerText.trim()) || m('meta[property="og:title"]') || (h1 && h1.innerText.trim()) || document.title,
               date: m('meta[property="article:published_time"]') || m('meta[name="date"]') || m('meta[itemprop="datePublished"]'),
               box: r ? [r.left, r.top + window.scrollY, r.width, r.height] : null };
    });
    const top = meta.box ? Math.max(0, meta.box[1] - 160) : 0;
    const h = spec.height || 1600;
    const total = await page.evaluate(() => document.documentElement.scrollHeight);
    const clipH = Math.max(400, Math.min(h, total - top));
    await page.screenshot({ path: spec.out, clip: { x: 0, y: top, width: spec.width || 1280, height: clipH }, fullPage: true });
    out.ok = true;
    out.site = meta.site; out.title = meta.title; out.date = meta.date;
    out.headline_box = meta.box ? [meta.box[0], meta.box[1] - top, meta.box[2], meta.box[3]] : null;
  } catch (e) {
    out.reason = String(e && e.message || e).slice(0, 300);
  } finally {
    if (browser) await browser.close().catch(() => {});
  }
  process.stdout.write(JSON.stringify(out) + '\n');
})();
