// The two clocks. Story time is the narration (seconds into the video). Universe time is the date in space: it decides
// where every body is, how it is turned, and what the mission clock reads. spec.clock maps one to the other:
//
//   { "keys": [ { "t": 0, "utc": "1969-07-16T13:32:00Z" }, { "t": 8, "utc": "1969-07-16T15:53:00Z" } ],
//     "met_zero": "1969-07-16T13:32:00Z" }
//
// Between two keys universe time moves smoothly (a fast-forward eases in and out); before the first and after the last key
// it runs at real time. One key holds the date; no key = now (a fixed default so renders are repeatable).
// A run of fast-forwards (a launch beat flowing into the orbit beat) does NOT stop at the keys between them: time keeps its
// speed through each key (monotone cubic, never running backwards) and only eases at the ends of the run -- a craft that
// paused at every beat boundary would read as the picture getting stuck.
const smooth = (x) => { const k = Math.min(1, Math.max(0, x)); return k * k * k * (k * (6 * k - 15) + 10); };

export function createClock(spec = {}) {
  const keys = (spec.keys || []).map((k) => ({ t: k.t, ms: Date.parse(k.utc) })).sort((a, b) => a.t - b.t);
  if (keys.some((k) => Number.isNaN(k.ms))) throw new Error('clock: every key needs utc as an ISO date, e.g. 1969-07-16T13:32:00Z');
  if (!keys.length) keys.push({ t: 0, ms: Date.parse(spec.utc || '2025-01-01T00:00:00Z') });
  const metZero = spec.met_zero ? Date.parse(spec.met_zero) : null;
  // each segment's kind and each key's speed (ms of universe per narration second) where two fast-forwards meet
  const ffwd = (i) => { const a = keys[i], b = keys[i + 1]; return b && b.t - a.t >= 0.5 && b.ms - a.ms > (b.t - a.t) * 1000 * 1.01; };
  const rate = (i) => (keys[i + 1].ms - keys[i].ms) / (keys[i + 1].t - keys[i].t);
  const speed = keys.map((k, i) => (i > 0 && ffwd(i - 1) && ffwd(i) ? 2 / (1 / rate(i - 1) + 1 / rate(i)) : 0));
  const utcMs = (t) => {
    if (t <= keys[0].t) return keys[0].ms + (t - keys[0].t) * 1000;
    for (let i = 1; i < keys.length; i++) {
      const a = keys[i - 1], b = keys[i];
      if (t <= b.t) {
        const realtime = a.ms + (t - a.t) * 1000;
        if (b.ms - a.ms <= (b.t - a.t) * 1000 * 1.01) return Math.min(realtime, b.ms);    // real time or slower: just run
        const x = (t - a.t) / (b.t - a.t), va = speed[i - 1], vb = speed[i];
        if (!va && !vb) return a.ms + (b.ms - a.ms) * smooth(x);                            // a fast-forward on its own
        const h = b.t - a.t, x2 = x * x, x3 = x2 * x;                                        // part of a run: Hermite
        return (2 * x3 - 3 * x2 + 1) * a.ms + (x3 - 2 * x2 + x) * h * va + (-2 * x3 + 3 * x2) * b.ms + (x3 - x2) * h * vb;
      }
    }
    const last = keys[keys.length - 1];
    return last.ms + (t - last.t) * 1000;
  };
  return {
    utc: (t) => new Date(utcMs(t)),
    /** Mission elapsed time "T+ HHH:MM:SS" (null without met_zero). */
    met: (t) => {
      if (metZero == null) return null;
      const s = Math.max(0, Math.floor((utcMs(t) - metZero) / 1000));
      return `T+ ${String(Math.floor(s / 3600)).padStart(2, '0')}:${String(Math.floor((s % 3600) / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
    },
  };
}
