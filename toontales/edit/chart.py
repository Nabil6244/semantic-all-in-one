"""Toon Tales trading screen: a full-frame animated trading-platform shot (PIL frames -> mp4), no Blender.

A plan shot with "screen": {...} becomes this clip instead of a 3D shot:
  pair      "EUR/USD"            tf "M5"
  path      [0.55, 0.62, 0.40]   price waypoints (0 = bottom of the chart, 1 = top) the live price follows
                                 over the shot; candles form live, a new one every CANDLE s
  entry     0.55  side "BUY"|"SELL"  lots "0.10"      entry line + open-position row
  sl, tp    0.45 / 0.72          stop-loss / take-profit lines; "no_sl": true crosses the stop out
  balance   [1000, 950]          account balance at the start / end of the shot (ticks between)
  pl        [0, -50]             open P/L start / end (green or red)
  banner    "MARGIN CALL"        big card that slams in at banner_at (fraction of the shot, 0.55)
  seed      int                  history shape (same seed = same past candles)
The layout keeps the bottom third clear for captions: header, chart (y 12-62 %), then the positions panel.

Library: chart.make(spec, dur, out_mp4, size=(1080, 1920))
"""
import hashlib
import json
import math
import random
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FPS = 30
CANDLE = 0.22                      # seconds per new candle while the shot plays
VISIBLE = 30                       # candles on screen
FONTS = Path("/System/Library/Fonts/Supplemental")
BG, GRID, AXIS = (14, 18, 26), (32, 38, 50), (120, 130, 150)
UP, DOWN = (38, 196, 120), (232, 62, 70)
BLUE, GOLD = (70, 150, 255), (255, 206, 64)
LO, HI = 1.0780, 1.0920            # price range shown (EUR/USD-like)
VERSION = "c2"


def _font(name, size):
    try:
        return ImageFont.truetype(str(FONTS / name), size)
    except OSError:
        return ImageFont.load_default()


def _price(v):
    return LO + (HI - LO) * v


def _series(spec, n_frames):
    """History closes (VISIBLE-1 candles) ending at path[0], then the live price for every frame."""
    rnd = random.Random(spec.get("seed", 7))
    path = spec.get("path", [0.5, 0.5])
    hist, v = [], path[0] + rnd.uniform(-0.18, 0.18)
    for _ in range(VISIBLE + 4):
        v += (path[0] - v) * 0.1 + rnd.gauss(0, 0.035)
        hist.append(min(0.95, max(0.05, v)))
    hist[-1] = path[0]
    live = []
    for f in range(n_frames):
        x = f / max(1, n_frames - 1) * (len(path) - 1)
        i = min(int(x), len(path) - 2) if len(path) > 1 else 0
        k = x - i
        k = k * k * (3 - 2 * k)
        base = path[i] + (path[min(i + 1, len(path) - 1)] - path[i]) * k
        live.append(min(0.97, max(0.03, base + 0.012 * math.sin(f * 1.7) + rnd.gauss(0, 0.004))))
    return hist, live


def _candles(hist, live, f, fpc):
    """OHLC list (0..1) at frame f: history candles, then one candle per fpc frames of live price."""
    out = []
    prev = hist[0]
    rnd = random.Random(3)
    for c in hist[1:]:
        hi = max(prev, c) + abs(rnd.gauss(0, 0.015))
        lo = min(prev, c) - abs(rnd.gauss(0, 0.015))
        out.append((prev, hi, lo, c))
        prev = c
    start = 0
    while start <= f:
        seg = live[start:min(f, start + fpc - 1) + 1]
        o = prev
        out.append((o, max([o] + seg), min([o] + seg), seg[-1]))
        prev = seg[-1]
        start += fpc
    return out[-VISIBLE:]


def _lerp(a, b, k):
    return a + (b - a) * k


def frame(spec, hist, live, f, n, size):
    W, H = size
    s = W / 1080
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    k = f / max(1, n - 1)
    fb, fm, fs = _font("Arial Bold.ttf", int(46 * s)), _font("Arial Bold.ttf", int(34 * s)), _font("Arial.ttf", int(28 * s))
    # header: pair + timeframe, balance, P/L
    d.rectangle([0, 0, W, int(0.11 * H)], fill=(20, 26, 38))
    d.text((int(40 * s), int(0.035 * H)), f"{spec.get('pair', 'EUR/USD')}  ·  {spec.get('tf', 'M5')}", font=fb,
           fill=(235, 240, 250))
    bal = spec.get("balance", [1000, 1000])
    pl = spec.get("pl", [0, 0])
    bv, pv = _lerp(bal[0], bal[-1], k), _lerp(pl[0], pl[-1], k)
    d.text((int(40 * s), int(0.072 * H)), f"BALANCE  ${bv:,.0f}", font=fm, fill=GOLD)
    pcol = UP if pv >= 0 else DOWN
    d.text((W - int(40 * s), int(0.072 * H)), f"P/L  {'+' if pv >= 0 else '-'}${abs(pv):,.0f}", font=fm, fill=pcol,
           anchor="ra")
    # chart area
    x0, x1, y0, y1 = int(30 * s), W - int(170 * s), int(0.13 * H), int(0.62 * H)
    for g in range(7):
        y = y0 + (y1 - y0) * g / 6
        d.line([(x0, y), (x1, y)], fill=GRID, width=1)
        gv = spec["_rng"][1] - (spec["_rng"][1] - spec["_rng"][0]) * g / 6
        d.text((x1 + int(14 * s), y), f"{_price(gv):.4f}", font=fs, fill=AXIS, anchor="lm")

    vlo, vhi = spec["_rng"]

    def py(v):
        return y1 - (y1 - y0) * (v - vlo) / (vhi - vlo)

    fpc = max(1, int(CANDLE * FPS))
    cs = _candles(hist, live, f, fpc)
    cw = (x1 - x0) / VISIBLE
    for i, (o, h, l, c) in enumerate(cs):
        cx = x0 + cw * (i + 0.5)
        col = UP if c >= o else DOWN
        d.line([(cx, py(h)), (cx, py(l))], fill=col, width=max(2, int(3 * s)))
        top, bot = py(max(o, c)), py(min(o, c))
        d.rectangle([cx - cw * 0.34, top, cx + cw * 0.34, max(bot, top + 2)], fill=col)

    def hline(v, col, label, dash=True):
        y = py(v)
        for xx in range(x0, x1, int(26 * s) if dash else 1):
            d.line([(xx, y), (min(x1, xx + int(16 * s)), y)], fill=col, width=max(2, int(4 * s)))
        d.rectangle([x1 - int(230 * s), y - int(22 * s), x1, y + int(22 * s)], fill=col)
        d.text((x1 - int(115 * s), y), label, font=fs, fill=(255, 255, 255), anchor="mm")

    if spec.get("tp") is not None:
        hline(spec["tp"], UP, "TAKE PROFIT")
    if spec.get("entry") is not None:
        hline(spec["entry"], BLUE, f"{spec.get('side', 'BUY')} {spec.get('lots', '0.10')}")
    if spec.get("sl") is not None:
        hline(spec["sl"], DOWN, "STOP LOSS")
    if spec.get("no_sl"):
        y = py(max(0.08, (spec.get("entry") or 0.5) - 0.18))
        d.text(((x0 + x1) / 2, y), "NO STOP LOSS", font=fb, fill=DOWN, anchor="mm")
        bb = d.textbbox(((x0 + x1) / 2, y), "NO STOP LOSS", font=fb, anchor="mm")
        d.line([(bb[0] - 10, bb[3]), (bb[2] + 10, bb[1])], fill=DOWN, width=int(8 * s))
    # live price tag
    v = live[f]
    lc = UP if len(cs) < 2 or cs[-1][3] >= cs[-1][0] else DOWN
    d.rectangle([x1, py(v) - int(24 * s), W, py(v) + int(24 * s)], fill=lc)
    d.text((x1 + int(14 * s), py(v)), f"{_price(v):.4f}", font=fm, fill=(255, 255, 255), anchor="lm")
    # positions panel (sits above the caption line)
    if spec.get("entry") is not None:
        py0 = int(0.635 * H)
        d.rectangle([0, py0, W, py0 + int(0.045 * H)], fill=(20, 26, 38))
        d.text((int(40 * s), py0 + int(0.0225 * H)), f"{spec.get('pair', 'EUR/USD')}  {spec.get('side', 'BUY')} "
               f"{spec.get('lots', '0.10')}", font=fm, fill=(220, 226, 240), anchor="lm")
        d.text((W - int(40 * s), py0 + int(0.0225 * H)), f"{'+' if pv >= 0 else '-'}${abs(pv):,.0f}", font=fm,
               fill=pcol, anchor="rm")
    # red flash + banner
    ban = spec.get("banner")
    at = spec.get("banner_at", 0.55)
    if ban and k >= at:
        kk = min(1.0, (k - at) / 0.06)
        if kk < 1 or (f // 4) % 2 == 0:
            ov = Image.new("RGB", (W, H), (180, 0, 10))
            im = Image.blend(im, ov, 0.18 if kk >= 1 else 0.35)
            d = ImageDraw.Draw(im)
        fbig = _font("Impact.ttf", int(150 * s * (1.3 - 0.3 * kk)))
        cy = int(0.37 * H)
        bb = d.textbbox((W / 2, cy), ban, font=fbig, anchor="mm")
        d.rounded_rectangle([bb[0] - 40 * s, bb[1] - 30 * s, bb[2] + 40 * s, bb[3] + 30 * s], radius=int(24 * s),
                            fill=(200, 20, 30), outline=(255, 255, 255), width=int(8 * s))
        d.text((W / 2, cy), ban, font=fbig, anchor="mm", fill=(255, 255, 255))
    return im


def make(spec, dur, out, size=(1080, 1920)):
    out = Path(out)
    key = hashlib.sha1(json.dumps([spec, round(dur, 3), size, VERSION], sort_keys=True).encode()).hexdigest()[:16]
    if out.exists() and out.with_suffix(".key").exists() and out.with_suffix(".key").read_text() == key:
        return out
    n = max(1, int(round(dur * FPS)))
    hist, live = _series(spec, n)
    lv = hist[-VISIBLE:] + live + [spec[k] for k in ("entry", "sl", "tp") if spec.get(k) is not None]
    pad = (max(lv) - min(lv)) * 0.12 + 0.02           # zoom to the move so candles fill the chart
    spec = dict(spec, _rng=(min(lv) - pad, max(lv) + pad))
    W, H = size
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                          "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "16",
                          "-preset", "medium", "-color_primaries", "bt709", "-color_trc", "bt709",
                          "-colorspace", "bt709", str(out)], stdin=subprocess.PIPE)
    for f in range(n):
        im = frame(spec, hist, live, f, n, size)
        z = 1.0 + 0.04 * f / max(1, n - 1)          # slow push-in on the screen
        if z > 1.001:
            cw, ch = int(W / z), int(H / z)
            im = im.crop(((W - cw) // 2, int((H - ch) * 0.35), (W - cw) // 2 + cw, int((H - ch) * 0.35) + ch)).resize(
                (W, H), Image.BICUBIC)
        p.stdin.write(im.tobytes())
    p.stdin.close()
    if p.wait():
        raise RuntimeError("ffmpeg failed on chart clip")
    out.with_suffix(".key").write_text(key)
    return out


if __name__ == "__main__":
    import sys
    spec = {"pair": "EUR/USD", "path": [0.55, 0.62, 0.30], "entry": 0.55, "sl": 0.45, "tp": 0.75, "balance": [1000, 950],
            "pl": [0, -50], "banner": "STOP LOSS HIT", "banner_at": 0.7, "lots": "0.10"}
    print(make(spec, 2.4, sys.argv[1]))
