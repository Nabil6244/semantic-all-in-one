// Number formatting for stat chips and counters: "12.6M", "17,700", "-67.7 C",
// "1/5", "2c", "9,300 KM", "M8.8". A format is a pattern with ONE number
// placeholder made of 0 # , and .0s; everything around it is literal text.
//
//   "#,##0 KM"  -> 9300 -> "9,300 KM"        "0.0M"   -> 12.6 -> "12.6M"
//   "0/5"       -> 1    -> "1/5"             "M0.0"   -> 8.8  -> "M8.8"
//   "0.0 °C" -> -67.7 -> "−67.7 °C"   (negative numbers get a real minus sign)

const MINUS = '−';

export function parseFormat(fmt) {
  const text = String(fmt ?? '0');
  const m = text.match(/[#0,]*0(?:\.0+)?/);
  if (!m) throw new Error(`format has no number placeholder (use 0, #,##0 or 0.0): ${JSON.stringify(text)}`);
  const body = m[0];
  const dot = body.indexOf('.');
  return {
    prefix: text.slice(0, m.index),
    suffix: text.slice(m.index + body.length),
    decimals: dot < 0 ? 0 : body.length - dot - 1,
    grouping: body.includes(','),
  };
}

export function formatValue(value, fmt) {
  const f = typeof fmt === 'string' || fmt == null ? parseFormat(fmt) : fmt;
  const rounded = Number(Math.abs(value).toFixed(f.decimals));
  let digits = rounded.toFixed(f.decimals);
  if (f.grouping) {
    const [int, frac] = digits.split('.');
    digits = int.replace(/\B(?=(\d{3})+(?!\d))/g, ',') + (frac !== undefined ? `.${frac}` : '');
  }
  const sign = value < 0 && rounded !== 0 ? MINUS : '';
  return `${f.prefix}${sign}${digits}${f.suffix}`;
}

const easeOut = (t) => 1 - Math.pow(1 - t, 3);

/** Counter value at time t: eases out into `to` with no overshoot. */
export function counterAt(t, { from, to, t0, dur }) {
  if (from === to || dur <= 0) return to;
  const k = Math.max(0, Math.min(1, (t - t0) / dur));
  return from + (to - from) * easeOut(k);
}
