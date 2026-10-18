// Batch renderer: gfx-core templates -> transparent PNG frame sequences, drawn in Playwright Chromium (the browser pakMap/Hybrid use) with the same
// gfx-core modules, without the map. One browser for the whole job.
//
//   node render.mjs <job.json>
//   job = { width, height, fps, playwright_dir?, browser_channel?, items: [{ key, dir, template, slots?, len, cues?, images?, dy?, scale?, anchor? }]; scale = uniform scale about anchor [x, y] (fractions of the frame); dy = move the whole graphic by that share of the frame height (negative = up); also writes dir/envelope.png }
//   writes dir/00001.png ... and dir/meta.json = { frames, fps, width, height, box (anything drawn), ink (opaque parts), band_max (strongest alpha in the caption area) }, then prints JSON lines:
//   {event:'item_done', key, frames, box, ms} | {event:'item_error', key, message} | {event:'progress', done, total} | {event:'done', ok, failed}
// One item failing never stops the others. Exit code 0 unless the browser itself could not start.
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const GFX = path.join(HERE, '..', 'gfx-core');
const FONTS = path.join(HERE, '..', 'pakmap-engine', 'assets', 'fonts');
const emit = (o) => process.stdout.write(JSON.stringify(o) + '\n');
const TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript', '.ttf': 'font/ttf', '.json': 'application/json' };

function loadPlaywright(job) {
  for (const dir of [job.playwright_dir, path.join(HERE, '..', 'flow-engine')].filter(Boolean)) {
    try { return createRequire(path.join(dir, 'package.json'))('playwright'); } catch { /* next */ }
  }
  throw new Error('Playwright not found (expected in flow-engine/node_modules).');
}

function serve(images) {
  const server = http.createServer((req, res) => {
    try {
      const p = decodeURIComponent(req.url.split('?')[0]);
      let file = null;
      if (p === '/' || p === '/index.html') file = path.join(HERE, 'page.html');
      else if (p === '/page.js') file = path.join(HERE, 'page.js');
      else if (/^\/gfx\/lib\/[\w-]+\.mjs$/.test(p) || /^\/gfx\/fonts\/[\w.-]+\.ttf$/.test(p)) file = path.join(GFX, p.slice(5));
      else if (/^\/fonts\/[\w.-]+\.ttf$/.test(p)) file = path.join(FONTS, p.slice(7));
      else if (/^\/img\/\d+$/.test(p)) file = images[Number(p.slice(5))];
      if (!file || !fs.existsSync(file)) { res.writeHead(404); return res.end(); }
      res.writeHead(200, { 'Content-Type': TYPES[path.extname(file)] || 'application/octet-stream' });
      fs.createReadStream(file).pipe(res);
    } catch (e) { res.writeHead(500); res.end(String(e && e.message || e)); }
  });
  return new Promise((resolve) => server.listen(0, '127.0.0.1', () => resolve(server)));
}

async function main() {
  const job = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
  const { width, height, fps } = job;
  const images = [];   // every image any item names, served as /img/<n>
  const items = job.items || [];
  const server = await serve(images);
  const origin = `http://127.0.0.1:${server.address().port}`;
  let browser = null;
  let ok = 0, failed = 0;
  try {
    const { chromium } = loadPlaywright(job);
    const opts = { headless: true, args: ['--hide-scrollbars'] };
    if (job.browser_channel) opts.channel = job.browser_channel;
    browser = await chromium.launch(opts);
    const page = await browser.newPage({ viewport: { width, height } });
    const pageErrors = [];
    page.on('pageerror', (e) => pageErrors.push(String(e)));
    await page.goto(`${origin}/index.html`);
    await page.waitForFunction(() => window.__ready === true, null, { timeout: 60000 });
    await page.evaluate(([w, h]) => window.setup(w, h), [width, height]);
    for (let n = 0; n < items.length; n++) {
      const it = items[n];
      const t0 = Date.now();
      try {
        const imageUrls = {};
        for (const [name, file] of Object.entries(it.images || {})) { images.push(file); imageUrls[name] = `${origin}/img/${images.length - 1}`; }
        const len = Number(it.len), frames = Math.max(1, Math.round(len * fps));
        fs.mkdirSync(it.dir, { recursive: true });
        pageErrors.length = 0;
        const warnings = await page.evaluate(([t, s, l, c, im, d, k, ax, ay]) => window.begin(t, s, l, c, im, d, k, ax, ay), [it.template, it.slots || {}, len, it.cues || {}, imageUrls, it.dy || 0, it.scale || 1, (it.anchor || [0, 0])[0], (it.anchor || [0, 0])[1]]);
        let box = null, ink = null, bandMax = 0, entryFrame = null;
        const merge = (a, b) => (b ? (a ? [Math.min(a[0], b[0]), Math.min(a[1], b[1]), Math.max(a[2], b[2]), Math.max(a[3], b[3])] : b) : a);
        for (let i = 0; i < frames; i++) {
          const r = await page.evaluate(([t, scan, w]) => window.frame(t, scan, w), [i / fps, i % 4 === 0 || i === frames - 1, entryFrame === null && i < 90]);
          fs.writeFileSync(path.join(it.dir, `${String(i + 1).padStart(5, '0')}.png`), Buffer.from(r.png, 'base64'));
          if (r.entry && entryFrame === null) entryFrame = i;
          box = merge(box, r.box); ink = merge(ink, r.ink); if (r.band > bandMax) bandMax = r.band;
        }
        if (pageErrors.length) throw new Error(pageErrors[0]);
        if (!box) throw new Error('the template drew nothing');
        fs.writeFileSync(path.join(it.dir, 'envelope.png'), Buffer.from(await page.evaluate(() => window.envelope()), 'base64'));
        fs.writeFileSync(path.join(it.dir, 'meta.json'), JSON.stringify({ frames, fps, width, height, box, ink, band_max: bandMax, entry_s: entryFrame === null ? null : entryFrame / fps, warnings }));
        emit({ event: 'item_done', key: it.key, frames, box, ink, band_max: bandMax, entry_s: entryFrame === null ? null : entryFrame / fps, warnings, ms: Date.now() - t0 });
        ok++;
      } catch (e) {
        emit({ event: 'item_error', key: it.key, message: String((e && e.message) || e).split('\n')[0] });
        failed++;
      }
      emit({ event: 'progress', done: n + 1, total: items.length });
    }
  } finally {
    if (browser) await browser.close().catch(() => {});
    server.close();
  }
  emit({ event: 'done', ok, failed });
}

main().catch((e) => { emit({ event: 'error', message: String((e && e.message) || e).split('\n')[0] }); process.exit(1); });
