// A 2D context for node (tests, tools/check_spec.mjs): accepts every canvas call, draws nothing, and records any NaN / Infinity argument
// (a broken number that would silently draw nothing in the browser).
export function mockCanvas(W = 1280, H = 720) {
  const bad = [];
  const grad = { addColorStop() {} };
  const target = { canvas: { width: W, height: H }, globalAlpha: 1, lineWidth: 1, measureText: (s) => ({ width: String(s).length * 12 }),
    createRadialGradient: () => grad, createLinearGradient: () => grad, createPattern: () => ({}), getLineDash: () => [],
    createImageData: (w, h) => ({ data: new Uint8ClampedArray(w * h * 4), width: w, height: h }) };
  const g = new Proxy(target, {
    get(o, k) {
      if (k in o) return o[k];
      return (...args) => { for (const a of args) if (typeof a === 'number' && !Number.isFinite(a)) bad.push(`${String(k)}(${args.map(String).join(', ').slice(0, 80)})`); };
    },
    set(o, k, v) { if (typeof v === 'number' && !Number.isFinite(v)) bad.push(`${String(k)} = ${v}`); o[k] = v; return true; },
  });
  return { g, bad };
}
