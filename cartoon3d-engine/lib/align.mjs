// Match lesson lines to a recorded voice-over: the script's words against the transcript's timed words (pure, no I/O).
// A global alignment (match 0, near-match 0.4, substitute 1, skip 1) tolerates dropped, added or misheard words.
// Returns one entry per line: { t0, t1, words: [{text, t0, t1}] } in seconds on the recording, or null when no word of the line was found.

const norm = (w) => String(w).toLowerCase().replace(/[^a-z0-9']/g, '').replace(/'/g, '');
const NUM = { one: '1', two: '2', three: '3', four: '4', five: '5', six: '6', seven: '7', eight: '8', nine: '9', ten: '10' };
const key = (w) => { const n = norm(w); return NUM[n] || n; };

function lev(a, b) {
  if (a === b) return 0;
  const m = a.length, n = b.length; if (!m || !n) return Math.max(m, n);
  let prev = Array.from({ length: n + 1 }, (_, j) => j);
  for (let i = 1; i <= m; i++) {
    const cur = [i];
    for (let j = 1; j <= n; j++) cur[j] = Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
    prev = cur;
  }
  return prev[n];
}
const cost = (a, b) => (a === b ? 0 : a.length >= 3 && b.length >= 3 && lev(a, b) <= Math.max(1, Math.floor(Math.min(a.length, b.length) / 4)) ? 0.4 : 1);

export function alignLines(lineTexts, spoken) {
  const S = [];                                                         // script tokens: { k, line, text }
  lineTexts.forEach((text, line) => text.split(/\s+/).filter((w) => key(w)).forEach((w) => S.push({ k: key(w), line, text: w })));
  const T = spoken.filter((w) => key(w.text)).map((w) => ({ ...w, k: key(w.text) }));
  const n = S.length, m = T.length, D = Array.from({ length: n + 1 }, () => new Float64Array(m + 1)), B = Array.from({ length: n + 1 }, () => new Uint8Array(m + 1));
  for (let i = 1; i <= n; i++) { D[i][0] = i; B[i][0] = 1; }
  for (let j = 1; j <= m; j++) { D[0][j] = j; B[0][j] = 2; }
  for (let i = 1; i <= n; i++) for (let j = 1; j <= m; j++) {
    const d = D[i - 1][j - 1] + cost(S[i - 1].k, T[j - 1].k), up = D[i - 1][j] + 1, left = D[i][j - 1] + 1;
    if (d <= up && d <= left) { D[i][j] = d; B[i][j] = 0; } else if (up <= left) { D[i][j] = up; B[i][j] = 1; } else { D[i][j] = left; B[i][j] = 2; }
  }
  const hit = new Array(n).fill(null);
  for (let i = n, j = m; i > 0 || j > 0;) {
    const b = B[i][j];
    if (b === 0) { if (cost(S[i - 1].k, T[j - 1].k) < 1) hit[i - 1] = T[j - 1]; i--; j--; } else if (b === 1) i--; else j--;
  }
  return lineTexts.map((_, line) => {
    const idx = S.map((s, i) => i).filter((i) => S[i].line === line), found = idx.filter((i) => hit[i]);
    if (!found.length) return null;
    const t0 = hit[found[0]].t0, t1 = hit[found.at(-1)].t1;
    // script words keep their own spelling; unmatched ones share the time between matched neighbours
    const words = idx.map((i, k) => {
      if (hit[i]) return { text: S[i].text, t0: hit[i].t0, t1: hit[i].t1 };
      const before = idx.slice(0, k).reverse().find((x) => hit[x]), after = idx.slice(k + 1).find((x) => hit[x]);
      const a = before !== undefined ? hit[before].t1 : t0, b = after !== undefined ? hit[after].t0 : t1;
      return { text: S[i].text, t0: a, t1: Math.max(a, b) };
    });
    return { t0, t1, words };
  });
}

// Lines the recording did not contain sit between their neighbours (or after the last found line).
// Each gets a normal speaking length for its words (0.38 s a word, 0.8 s at least), never past the next found line.
export function fillMissing(timed, duration, lineTexts = []) {
  const out = timed.slice();
  for (let i = 0; i < out.length; i++) {
    if (out[i]) continue;
    const prev = out.slice(0, i).reverse().find(Boolean), next = out.slice(i + 1).find(Boolean);
    const a = prev ? prev.t1 + 0.2 : 0.3, b = next ? next.t0 - 0.2 : Math.max(a + 1.5, duration - 0.3);
    const n = String(lineTexts[i] || '').split(/\s+/).filter(Boolean).length || 3;
    out[i] = { t0: a, t1: Math.max(a + 0.3, Math.min(b, a + Math.max(0.8, n * 0.38))), words: [], missing: true };
  }
  return out;
}
