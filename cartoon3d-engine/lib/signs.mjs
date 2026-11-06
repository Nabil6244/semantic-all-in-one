// Which hand sign goes on which spoken or sung word. A key word gets its sign exactly when it is said; a row can name its own signs too.
export const WORD_SIGNS = {
  open: 'open', shut: 'shut', clap: 'clap', clapping: 'clap', lap: 'lap', creep: 'creep', crawl: 'creep', chin: 'chin', mouth: 'mouth',
  mama: 'mama', mommy: 'mama', dada: 'dada', daddy: 'dada', fingers: 'fingers', finger: 'fingers', toes: 'toes', belly: 'belly', tummy: 'belly',
  knees: 'knees', nose: 'nose', spider: 'spider', rain: 'rain', washed: 'wash', sun: 'sun', wheels: 'wheels', round: 'wheels', beep: 'beep', swish: 'swish', wipers: 'swish',
};
// Move signs need time to travel; a word's own length is too short for them.
const MIN_HOLD = { creep: 1.4, spider: 1.6, rain: 1.3, wash: 0.9, sun: 1.2, wheels: 1.2, swish: 1.2, belly: 1.0 };
const clean = (w) => String(w).toLowerCase().replace(/[^a-z]/g, '');

/** lines = [{ t0, t1, words:[{text,t0,t1}], sign?:'name' }]. Returns signs sorted by time: [{ t0, t1, sign, word }]. */
export function signsForLines(lines, names, beat = 0.5) {
  const out = [];
  for (const l of lines) {
    if (l.sign && names.includes(l.sign)) { out.push({ t0: l.t0, t1: l.t1, sign: l.sign, word: null, beat }); continue; }
    for (const w of l.words || []) {
      const sign = WORD_SIGNS[clean(w.text)];
      if (!sign || !names.includes(sign)) continue;
      const prev = out.at(-1);
      if (prev && prev.sign === sign && w.t0 - prev.t1 < 0.6) { prev.t1 = w.t1 + 0.1; continue; }   // "clap, clap, clap" is one sign that keeps going
      out.push({ t0: w.t0, t1: Math.max(w.t1 + 0.1, w.t0 + (MIN_HOLD[sign] || 0.4)), sign, word: clean(w.text), beat });
    }
  }
  for (let i = 0; i + 1 < out.length; i++) out[i].t1 = Math.min(out[i].t1, out[i + 1].t0 - 0.02);   // the next word's sign always gets its moment
  return out;
}
