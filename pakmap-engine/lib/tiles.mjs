// Tile fetch + disk cache for imagery providers (node side). Same cache idea as
// map-engine, but keyed by provider so providers never share files, and 404s
// (outside a layer's coverage) are remembered instead of re-asked.
import fs from 'node:fs';
import https from 'node:https';
import path from 'node:path';

export function tileUrl(provider, z, x, y) {
  return provider.urlTemplate.replace('{z}', z).replace('{x}', x).replace('{y}', y);
}

export function cachePath(cacheDir, provider, z, x, y) {
  const ext = provider.format === 'png' ? 'png' : 'jpg';
  return path.join(cacheDir, 'pakmap_imagery', provider.id, String(z), String(y), `${x}.${ext}`);
}

function get(url) {
  return new Promise((resolve, reject) => {
    const req = https.get(url, { timeout: 20000, headers: { 'User-Agent': 'semantic-yt-studio-pakmap/0.1' } }, (res) => {
      if (res.statusCode !== 200) { res.resume(); return resolve({ status: res.statusCode, body: null }); }
      const chunks = [];
      res.on('data', (c) => chunks.push(c));
      res.on('end', () => resolve({ status: 200, body: Buffer.concat(chunks) }));
    });
    req.on('error', reject);
    req.on('timeout', () => req.destroy(new Error('timeout')));
  });
}

/** Returns a Buffer, or null when the layer has no tile there. Throws on network trouble after retries. */
export async function fetchTile(provider, z, x, y, cacheDir, fetcher = get) {
  const file = cachePath(cacheDir, provider, z, x, y);
  if (fs.existsSync(file)) return fs.readFileSync(file);
  if (fs.existsSync(`${file}.none`)) return null;
  let last;
  for (let attempt = 0; attempt < 4; attempt++) {
    try {
      const { status, body } = await fetcher(tileUrl(provider, z, x, y));
      if (status === 404) { fs.mkdirSync(path.dirname(file), { recursive: true }); fs.writeFileSync(`${file}.none`, ''); return null; }
      if (status === 200 && body) {
        fs.mkdirSync(path.dirname(file), { recursive: true });
        const tmp = `${file}.${process.pid}.tmp`;
        fs.writeFileSync(tmp, body); fs.renameSync(tmp, file);
        return body;
      }
      last = new Error(`HTTP ${status}`);
      if (status < 500) break;
    } catch (err) { last = err; }
    await new Promise((r) => setTimeout(r, 400 * (attempt + 1)));
  }
  throw new Error(`tile ${provider.id} ${z}/${y}/${x}: ${last && last.message}`);
}
