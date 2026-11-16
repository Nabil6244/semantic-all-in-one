"""GTA 6 launch: full "Leonida vs the real Florida" video (~4-5 min).

Game footage = Rockstar Trailer 1, Trailer 2 and Launch Trailer (muted).
Real footage = free Pexels Florida clips. Graphics, map and music are made here.
Run:  python3 gta6_launch/build_full.py
"""
import asyncio, json, math, subprocess, sys, wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_test20 as base  # shared look: fonts, pills, synthwave, glitch
from build_test20 import (W, H, FPS, PINK, TEAL, NAVY, WHITE, F_HEAD, F_TAG,
                          font, shadow_text, pill, run, dur)

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
FOOT = ROOT / "footage"
WORK = ROOT / "work_full"
OUT = ROOT / "out"
WORK.mkdir(exist_ok=True); OUT.mkdir(exist_ok=True)
VOICE = "en-US-AndrewNeural"

TR = {
    "T1": FOOT / "trailer/gta6_trailer1.mp4",
    "T2": FOOT / "trailer/gta6_trailer2.mp4",
    "TL": FOOT / "trailer/gta6_launch_trailer.mp4",
}
# detected cuts (+ a few hand-added ends where a title or fade starts)
CUTS = {
    "T1": [2.7, 5.0, 6.5, 8.5, 10.9, 13.4, 18.4, 19.2, 21.7, 23.3, 24.8, 27.4, 29.0, 30.0, 32.6,
           34.1, 35.7, 37.4, 39.8, 41.3, 42.4, 43.9, 45.5, 46.5, 47.5, 48.6, 49.9, 52.2, 54.0,
           55.0, 57.3, 59.5, 60.5, 62.5, 63.6, 64.6, 65.6, 66.7, 67.7, 68.7, 70.3, 72.8, 76.5],
    "T2": [0.17, 8.13, 9.80, 11.47, 13.67, 18.83, 23.27, 33.20, 34.60, 38.37, 41.60, 45.27, 49.83,
           51.87, 60.57, 63.10, 66.20, 75.90, 76.67, 79.50, 81.40, 83.10, 85.10, 86.00, 88.23,
           89.50, 90.37, 92.00, 96.13, 97.67, 98.47, 99.67, 111.30, 117.10, 117.93, 118.83,
           119.63, 125.77, 126.73, 129.37, 134.40, 138.13, 140.03, 141.83, 143.73, 147.30,
           152.5, 155.9],
    "TL": [2.0, 6.3, 9.3, 11.2, 13.5, 14.5, 17.0, 20.5, 25.7, 27.2, 28.7, 32.1, 33.0, 34.4, 35.8,
           37.3, 38.3, 39.8, 41.7, 44.4, 46.3, 54.5, 56.4, 57.8, 59.2, 62.5, 63.4, 66.4, 67.9,
           72.1, 73.1, 79.6, 85.0, 88.0],
}


def P(i):
    return f"P{i}"


def src_path(k):
    return TR[k] if k in TR else FOOT / f"stock/pexels_{k[1:]}.mp4"


# ---------------- script ----------------
# shot kinds:
#  ("g", src, in)                       game footage, "IN GAME" chip
#  ("r", src, in)                       real footage, "REAL LIFE" chip
#  ("s", (src,in), (src,in), L, R)      split screen game | real
#  ("h", src, in, head, sub)            big headline over footage
#  ("c", src, in, num, title)           chapter card
#  ("m", region)                        Florida map
# a shot may end with {"end": t} to allow crossing a trailer cut
LINES = [
    ("In three days, GTA six finally drops.",
     [("h", "T1", 2.75, "NOV 19", "GTA VI  ·  3 DAYS TO LAUNCH")]),
    ("But the state where it all happens, Leonida, is not made up.",
     [("h", "T1", 10.95, "IS LEONIDA REAL?", None)]),
    ("Almost every road, beach and swamp in the trailers has a real twin in Florida.",
     [("s", ("T1", 21.75), (P(11243172), 6.0), "LEONIDA", "FLORIDA"),
      ("g", "TL", 2.1)]),
    ("So we put them side by side. Here are the six regions of Leonida, and the real places behind them.",
     [("m", "all")]),

    ("Region one. Vice City.", [("c", "T1", 39.85, "01", "VICE CITY")]),
    ("Vice City is Miami. The highways, the skyline, even the green exit signs match.",
     [("m", "vice"), ("s", ("T1", 23.35), (P(37694375), 3.0), "VICE CITY", "MIAMI")]),
    ("Glass towers, palm trees, and planes coming in low over downtown, just like the real thing.",
     [("s", ("T2", 34.7), (P(31004828), 2.0), "DOWNTOWN VICE", "DOWNTOWN MIAMI")]),
    ("Then there's the beach. Vice Beach is Miami Beach, down to the lifeguard towers and the hotel strip behind the sand.",
     [("s", ("TL", 54.6), (P(4135117), 2.0), "VICE BEACH", "MIAMI BEACH"),
      ("s", ("T2", 38.45), (P(11094699), 8.0), "VICE BEACH", "SOUTH BEACH")]),
    ("At night, the neon strip comes alive. Art deco hotels, glowing signs, and slow cars cruising past the crowds.",
     [("s", ("T1", 30.05), (P(32438231), 2.0), "NEON STRIP", "OCEAN DRIVE"),
      ("r", P(36032432), 0.0)]),
    ("The clubs are pure Miami nightlife too.",
     [("s", ("T1", 27.45), (P(34059053), 0.0), "VICE NIGHTS", "MIAMI NIGHTS")]),
    ("Even the marinas are packed with yachts, just like the real ones off Miami Beach.",
     [("s", ("T2", 79.55), (P(11094699), 4.0), "VICE MARINA", "MIAMI MARINA")]),

    ("Region two. The Leonida Keys.", [("c", "T2", 6.1, "02", "LEONIDA KEYS")]),
    ("These are the Florida Keys: a chain of small islands hanging off the bottom of the state, linked by long bridges.",
     [("m", "keys"), ("s", ("T1", 35.75), (P(33959669), 3.0), "LEONIDA KEYS", "SEVEN MILE BRIDGE")]),
    ("In the trailer, locals live right on the water, in old houses with beat-up pickups out front.",
     [("g", "T2", 8.2), ("s", ("T2", 11.5), (P(10587225), 0.0), "KEYS LOCALS", "FLORIDA PICKUP")]),
    ("And out on the water, it's jet skis and speedboats, exactly like a summer weekend down south.",
     [("s", ("T2", 140.05), (P(35077123), 5.0), "LEONIDA WATERS", "FLORIDA WATERS"),
      ("s", ("T1", 8.55), (P(11243172), 1.0), "SPEEDBOATS", "FLORIDA COAST")]),

    ("Region three. Grassrivers.", [("c", "T1", 19.25, "03", "GRASSRIVERS")]),
    ("Grassrivers is the Everglades: endless sawgrass, mangroves, and slow brown water.",
     [("m", "grass"), ("s", ("T1", 20.0), (P(34338326), 10.0), "GRASSRIVERS", "EVERGLADES")]),
    ("The trailer even shows an airboat chase through the swamp, with a helicopter right on its tail.",
     [("s", ("T2", 138.2, {"end": 140.0}), (P(11840880), 0.0), "AIRBOAT CHASE", "REAL AIRBOAT")]),
    ("And of course, alligators. In Leonida they turn up in swimming pools. In Florida, that actually happens.",
     [("s", ("T1", 41.35), (P(11841042), 0.0), "POOL GATOR", "EVERGLADES GATOR"),
      ("r", P(39177553), 4.0)]),

    ("Region four. Ambrosia.", [("c", "T1", 68.75, "04", "AMBROSIA")]),
    ("Ambrosia is farm country, built around a sugar refinery. Fans point to the sugar towns around Lake Okeechobee.",
     [("m", "ambrosia"), ("s", ("T1", 59.55), (P(40799964), 5.0), "AMBROSIA", "SUGAR COUNTRY")]),
    ("It's flat, dusty and wide open. The kind of place where bikers own the back roads.",
     [("r", P(40799964), 22.0), ("g", "TL", 18.0), ("r", P(3057602), 1.0)]),

    ("Region five. Port Gellhorn.", [("c", "T2", 125.8, "05", "PORT GELLHORN")]),
    ("Up on the Gulf coast, Port Gellhorn feels like Florida's Panhandle: faded beach towns, old motels and cheap neon.",
     [("m", "port"), ("s", ("T2", 126.8), (P(31040643), 5.0), "PORT GELLHORN", "PANAMA CITY BEACH")]),
    ("It's the forgotten side of the state, far from the Miami glamour.",
     [("g", "T1", 72.85), ("r", P(31040643), 22.0)]),

    ("Region six. Mount Kalaga National Park.", [("c", "T1", 50.0, "06", "MOUNT KALAGA")]),
    ("Here's the twist. Florida has no real mountains. So Rockstar invented one, with forests, trails and hunting grounds.",
     [("m", "kalaga"), ("s", ("T1", 52.25), (P(31149971), 3.0), "MOUNT KALAGA", "REAL WILDS")]),
    ("It's the one part of Leonida that's more fantasy than Florida.",
     [("g", "T1", 55.05)]),

    ("And then there's the part Rockstar copied most closely: the headlines.",
     [("c", "T1", 65.65, "07", "THE HEADLINES")]),
    ("The trailers are full of viral phone videos, police chases and mugshots, a parody of the stories Florida is famous for online.",
     [("g", "T1", 63.65), ("s", ("TL", 68.0), (P(32538553), 3.0), "LEONIDA POLICE", "FLORIDA POLICE"),
      ("r", P(7714378), 2.0)]),
    ("In Leonida, Florida Man is basically a game mechanic.",
     [("g", "T1", 43.95)]),

    ("So how big is all this? Fans who mapped the trailers estimate Leonida is roughly twice the size of GTA five's map.",
     [("m", "size"), ("h", "TL", 46.4, "~2× GTA V", "FAN ESTIMATE FROM TRAILER MAPPING")]),
    ("That would make it the biggest world Rockstar has ever built.",
     [("g", "TL", 44.45)]),

    ("GTA six launches November nineteenth, on PlayStation five and Xbox Series X and S. There's no PC date yet.",
     [("g", "TL", 80.0), ("h", "T2", 152.95, "NOV 19", "PS5  ·  XBOX SERIES X|S  ·  NO PC DATE YET")]),
    ("When it's out, we'll drive every region and compare it with the real Florida, shot by shot. Subscribe so you don't miss it.",
     [("h", P(3770584), 6.0, "THE REAL LEONIDA", "FULL MAP BREAKDOWN  ·  SUBSCRIBE")]),
]


# ---------------- voice ----------------
async def _tts(text, path):
    import edge_tts
    await edge_tts.Communicate(text, VOICE, rate="+6%").save(str(path))


def make_voice():
    for i, (line, _) in enumerate(LINES):
        mp3 = WORK / f"vo{i:02d}.mp3"
        for attempt in range(5):
            if mp3.exists() and mp3.stat().st_size > 0:
                break
            text = line if attempt < 3 else line.replace("?", ",").replace(":", ",")
            try:
                asyncio.run(_tts(text, mp3))
            except Exception as e:
                print("voice retry", i, e)
                mp3.unlink(missing_ok=True)


def timeline():
    """Each line: voice at vo_at; its shots split the line's time by weight."""
    t, shots, vo = 0.35, [], []
    for i, (line, sh) in enumerate(LINES):
        is_chap = sh[0][0] == "c"
        if is_chap and i:
            t += 0.45  # breath before a chapter
        d = dur(WORK / f"vo{i:02d}.mp3")
        vo.append((WORK / f"vo{i:02d}.mp3", t))
        start = 0.0 if i == 0 else t - 0.15
        span_end = t + d + 0.32
        weights = [0.75 if s[0] == "m" and len(sh) > 1 else 1.0 for s in sh]
        tot = sum(weights)
        a = start
        for s, w in zip(sh, weights):
            shots.append(dict(spec=s, start=a, chapter=is_chap))
            a += (span_end - start) * w / tot
        t = span_end
    total = t + 2.2  # hold the end card
    for k, s in enumerate(shots):
        nxt = shots[k + 1]["start"] if k + 1 < len(shots) else total
        s["len"] = round(nxt - s["start"], 3)
    return shots, vo, total


# ---------------- footage helpers ----------------
def avail(k, t_in, end=None):
    if end:
        return end - t_in
    if k in CUTS:
        nxt = [c for c in CUTS[k] if c > t_in + 0.05]
        return (nxt[0] if nxt else dur(src_path(k))) - t_in - 0.06
    return dur(src_path(k)) - t_in - 0.05


def clip_filter(k, t_in, L, end=None, label="x"):
    """Input args + filter that yields exactly L s from (k, t_in) without crossing a cut."""
    a = avail(k, t_in, end)
    slow = max(0.45, min(1.0, a / L))
    take = min(a, L * slow)
    hold = max(0.0, L - take / slow)
    inp = ["-ss", f"{t_in:.3f}", "-t", f"{take:.3f}", "-i", str(src_path(k))]
    f = f"setpts=(PTS-STARTPTS)/{slow:.4f},fps={FPS}"
    if hold > 0.01:
        f += f",tpad=stop_mode=clone:stop_duration={hold + 0.1:.3f}"
    return inp, f


GLITCH = base.GLITCH
EASE_IN = "pow(max(0,1-(t-{d})/0.4),2)"


def band(img, top, strength=180):
    b = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(b)
    for y in range(top, H):
        a = int(strength * ((y - top) / (H - top)) ** 1.5)
        d.line([(0, y), (W, y)], fill=NAVY + (a,))
    img.alpha_composite(b)


def chip_png(kind, path):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    if kind == "g":
        pill(img, (60, 56), "IN GAME", PINK, 38)
    else:
        pill(img, (60, 56), "REAL LIFE", (0, 150, 150), 38)
    img.save(path)


def head_png(head, sub, path):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    band(img, H // 2)
    big = 210 if len(head) < 10 else 170
    f = font(F_HEAD, big)
    shadow_text(img, (W // 2, 760), head, f)
    tw = ImageDraw.Draw(img).textlength(head, font=f)
    ImageDraw.Draw(img).rectangle((W // 2 - tw / 2, 850, W // 2 + tw / 2, 862), fill=PINK)
    if sub:
        shadow_text(img, (W // 2, 925), sub, font(F_TAG, 44), fill=(255, 220, 235))
    pill(img, (60, 56), "GTA VI", PINK, 38)
    img.save(path)


def chapter_png(num, title, path):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dark = Image.new("RGBA", (W, H), NAVY + (120,))
    img.alpha_composite(dark)
    d = ImageDraw.Draw(img)
    fn = font(F_HEAD, 300)
    shadow_text(img, (150, 640), num, fn, fill=PINK, anchor="ls")
    nw = d.textlength(num, font=fn)
    d.rectangle((150 + nw + 40, 380, 150 + nw + 52, 640), fill=WHITE)
    shadow_text(img, (150 + nw + 90, 560), title, font(F_HEAD, 170), anchor="ls")
    shadow_text(img, (150 + nw + 94, 630), "REGION OF LEONIDA" if num in "010203040506" and len(num) == 2 and int(num) <= 6 else "LEONIDA = FLORIDA",
                font(F_TAG, 40), fill=TEAL, anchor="ls")
    img.save(path)


def split_png(L, R, path):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle((W // 2 - 5, 0, W // 2 + 5, H), fill=PINK + (255,))
    pill(img, (60, 56), "IN GAME", PINK, 38)
    pill(img, (W - 60, 56), "REAL LIFE", (0, 150, 150), 38, anchor="rt")
    band(img, H - 330, 190)
    f = font(F_HEAD, 112)
    eq = "  =  "
    wg, we, wr = (d.textlength(t, font=f) for t in (L, eq, R))
    x = W / 2 - (wg + we + wr) / 2
    shadow_text(img, (x, 990), L, f, anchor="ls")
    shadow_text(img, (x + wg, 990), eq, f, fill=PINK, anchor="ls")
    shadow_text(img, (x + wg + we, 990), R, f, fill=TEAL, anchor="ls")
    img.save(path)


def encode(inputs, fc, L, out):
    run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", fc, "-map", "[v]",
         "-t", f"{L:.3f}", "-r", str(FPS), "-c:v", "libx264", "-preset", "fast", "-crf", "17",
         "-pix_fmt", "yuv420p", "-an", str(out)])


def render_shot(i, s):
    out = WORK / f"shot{i:03d}.mp4"
    spec, L = s["spec"], s["len"]
    kind = spec[0]
    png = WORK / f"ov{i:03d}.png"
    cover = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}"
    push = (f"scale=w='trunc({W}*(1+0.06*t/{L})/2)*2':h=-2:eval=frame,crop={W}:{H},setsar=1")
    if kind == "m":
        return render_map(i, spec[1], L, out)
    if kind == "s":
        g, r, lab_l, lab_r = spec[1], spec[2], spec[3], spec[4]
        split_png(lab_l, lab_r, png)
        g_end = g[2]["end"] if len(g) > 2 else None
        gi, gf = clip_filter(g[0], g[1], L, g_end)
        ri, rf = clip_filter(r[0], r[1], L)
        half = f"scale=-2:{H},crop={W//2}:{H},setsar=1"
        fc = (f"[0:v]{gf},{half}[g];[2:v]{rf},{half}[r];"
              f"color=c=black:s={W}x{H}:r={FPS}:d={L}[base];"
              f"[base][g]overlay=0:0[b1];"
              f"[b1][r]overlay=x='{W//2}+{W//2}*pow(max(0,1-(t-0.25)/0.45),3)':y=0[b2];"
              f"[1:v]format=rgba,fade=in:st=0.3:d=0.3:alpha=1[ov];[b2][ov]overlay=0:0,{GLITCH}[v]")
        encode([*gi, "-loop", "1", "-t", f"{L:.3f}", "-i", str(png), *ri], fc, L, out)
        return out
    k, t_in = spec[1], spec[2]
    if kind in ("g", "r"):
        chip_png(kind, png); delay = 0.1
    elif kind == "h":
        head_png(spec[3], spec[4], png); delay = 0.15
    else:
        chapter_png(spec[3], spec[4], png); delay = 0.05
    ci, cf = clip_filter(k, t_in, L)
    yoff = "0" if kind in ("g", "r") else f"60*{EASE_IN.format(d=delay)}"
    fc = (f"[0:v]{cf},{cover},{push}[bg];"
          f"[1:v]format=rgba,fade=in:st={delay}:d=0.35:alpha=1[ov];"
          f"[bg][ov]overlay=x=0:y='{yoff}',{GLITCH}[v]")
    encode([*ci, "-loop", "1", "-t", f"{L:.3f}", "-i", str(png)], fc, L, out)
    return out


# ---------------- Florida map ----------------
# hand-traced outline (lon, lat), good enough for a stylised map
FL = [(-87.60, 31.00), (-85.00, 31.00), (-85.00, 30.70), (-84.30, 30.68), (-83.00, 30.60),
      (-82.20, 30.57), (-82.05, 30.36), (-81.95, 30.78), (-81.45, 30.71), (-81.40, 30.30),
      (-81.25, 29.90), (-81.00, 29.20), (-80.60, 28.60), (-80.55, 28.05), (-80.35, 27.50),
      (-80.05, 26.90), (-80.05, 26.30), (-80.12, 25.80), (-80.30, 25.40), (-80.45, 25.20),
      (-80.90, 25.15), (-81.10, 25.30), (-81.35, 25.80), (-81.80, 26.10), (-81.95, 26.50),
      (-82.25, 26.90), (-82.60, 27.40), (-82.75, 27.80), (-82.70, 28.30), (-82.65, 28.80),
      (-83.00, 29.10), (-83.40, 29.60), (-83.95, 30.00), (-84.30, 30.05), (-84.90, 29.75),
      (-85.30, 29.70), (-85.40, 29.95), (-85.80, 30.20), (-86.50, 30.40), (-87.20, 30.35),
      (-87.50, 30.30)]
KEYS = [(-80.42 - 0.07 * k, 25.15 - 0.032 * k - 0.0012 * k * k) for k in range(20)]
REG = {  # key: (lon, lat, Leonida name, real name)
    "vice": (-80.19, 25.77, "VICE CITY", "MIAMI"),
    "keys": (-81.10, 24.72, "LEONIDA KEYS", "FLORIDA KEYS"),
    "grass": (-80.95, 25.55, "GRASSRIVERS", "EVERGLADES"),
    "ambrosia": (-80.93, 26.75, "AMBROSIA", "LAKE OKEECHOBEE AREA"),
    "port": (-85.66, 30.16, "PORT GELLHORN", "PANHANDLE"),
    "kalaga": (-82.20, 29.90, "MOUNT KALAGA", "NORTH FLORIDA WILDS"),
}
ORDER = ["vice", "keys", "grass", "ambrosia", "port", "kalaga"]
LON0, LON1, LAT0, LAT1 = -88.6, -78.6, 24.0, 31.6
MW, MH = 3840, 2160
_COS = math.cos(math.radians(27.5))


def proj(lon, lat):
    # fit both axes into the 16:9 canvas with the cos-lat correction
    sx = MW / ((LON1 - LON0) * _COS)
    sy = MH / (LAT1 - LAT0)
    s = min(sx, sy)
    cx = (MW - (LON1 - LON0) * _COS * s) / 2
    return cx + (lon - LON0) * _COS * s, (LAT1 - lat) * s


_BASE = None


def base_map():
    global _BASE
    if _BASE is not None:
        return _BASE
    img = Image.new("RGB", (MW, MH), (8, 12, 32))
    d = ImageDraw.Draw(img)
    for y in range(MH):  # sea gradient
        c = int(18 + 14 * y / MH)
        d.line([(0, y), (MW, y)], fill=(8, c - 4, c + 22))
    for gx in range(0, MW, 160):
        d.line([(gx, 0), (gx, MH)], fill=(22, 34, 66), width=2)
    for gy in range(0, MH, 160):
        d.line([(0, gy), (MW, gy)], fill=(22, 34, 66), width=2)
    pts = [proj(*p) for p in FL]
    glow = Image.new("RGB", (MW, MH), (0, 0, 0))
    ImageDraw.Draw(glow).line(pts + [pts[0]], fill=PINK, width=34, joint="curve")
    glow = glow.filter(ImageFilter.GaussianBlur(26))
    img = Image.blend(img, Image.composite(glow, img, glow.convert("L").point(lambda v: 255 if v > 8 else 0)), 0.55)
    d = ImageDraw.Draw(img)
    d.polygon(pts, fill=(30, 38, 78))
    d.line(pts + [pts[0]], fill=PINK, width=7, joint="curve")
    lx, ly = proj(-80.83, 26.95)
    d.ellipse((lx - 46, ly - 52, lx + 46, ly + 52), fill=(20, 110, 140), outline=TEAL, width=4)
    for (x, y) in (proj(*k) for k in KEYS):
        d.ellipse((x - 9, y - 6, x + 9, y + 6), fill=(30, 38, 78), outline=PINK, width=4)
    shadow_text_rgb = ImageDraw.Draw(img)
    gx, gy = proj(-86.6, 27.4)
    shadow_text_rgb.text((gx, gy), "GULF OF MEXICO", font=font(F_TAG, 64), fill=(60, 90, 140), anchor="mm")
    ax, ay = proj(-79.4, 28.8)
    shadow_text_rgb.text((ax, ay), "ATLANTIC", font=font(F_TAG, 64), fill=(60, 90, 140), anchor="mm")
    _BASE = img
    return img


def ease(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def render_map(i, which, L, out):
    m = base_map()
    n = int(round(L * FPS))
    full_c, full_z = (MW / 2, MH / 2), 1.0
    if which in REG:
        lon, lat = REG[which][:2]
        tc, tz = proj(lon, lat), 2.6
    else:
        tc, tz = full_c, 1.0
    proc = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
         "-r", str(FPS), "-i", "-", "-vf", base.GLITCH, "-c:v", "libx264", "-preset", "fast",
         "-crf", "17", "-pix_fmt", "yuv420p", str(out)], stdin=subprocess.PIPE)
    f_big, f_small = font(F_HEAD, 64), font(F_TAG, 30)
    for f in range(n):
        t = f / FPS
        k = ease((t - 0.2) / 1.6)
        z = full_z + (tz - full_z) * k
        if which == "all":
            z = 1.0 + 0.05 * t / L
        if which == "size":
            z = 1.15 - 0.15 * ease(t / 1.5)
        cx = full_c[0] + (tc[0] - full_c[0]) * k
        cy = full_c[1] + (tc[1] - full_c[1]) * k
        cw, ch = MW / z, MH / z
        x0 = min(max(0, cx - cw / 2), MW - cw); y0 = min(max(0, cy - ch / 2), MH - ch)
        frame = m.crop((int(x0), int(y0), int(x0 + cw), int(y0 + ch))).resize((W, H), Image.BILINEAR)
        frame = frame.convert("RGBA")
        d = ImageDraw.Draw(frame)
        sc = W / cw

        def to_scr(lon, lat):
            px, py = proj(lon, lat)
            return (px - x0) * sc, (py - y0) * sc

        keys = ORDER if which in ("all", "size") else [which]
        for j, key in enumerate(keys):
            appear = 0.5 + j * 0.55 if which == "all" else (1.2 if which in REG else 0.3)
            if t < appear:
                continue
            p = ease((t - appear) / 0.35)
            lon, lat, gname, rname = REG[key]
            x, y = to_scr(lon, lat)
            r = 16 * p + 5 * math.sin(t * 5) * p
            d.ellipse((x - r - 10, y - r - 10, x + r + 10, y + r + 10), outline=PINK + (int(150 * p),), width=4)
            d.ellipse((x - r, y - r, x + r, y + r), fill=PINK + (255,), outline=WHITE, width=4)
            if which == "size":
                continue
            fb = f_big if which in REG else font(F_HEAD, 46)
            fs = f_small if which in REG else font(F_TAG, 24)
            side = -1 if key in ("port", "kalaga", "grass") and which == "all" else 1
            tx = x + side * 34
            anchor_l = "ls" if side > 0 else "rs"
            a = int(255 * p)
            d.text((tx + 3, y + 5), gname, font=fb, fill=(0, 0, 0, a // 2), anchor=anchor_l)
            d.text((tx, y + 2), gname, font=fb, fill=WHITE + (a,), anchor=anchor_l)
            d.text((tx, y + 34 if which in REG else y + 26), "= " + rname, font=fs, fill=TEAL + (a,),
                   anchor="lt" if side > 0 else "rt")
        if which == "size" and t > 0.6:
            p = ease((t - 0.6) / 0.4)
            ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            shadow_text(ov, (W // 2, 200), "LEONIDA  ≈  2× GTA V", font(F_HEAD, 130))
            ov.putalpha(ov.getchannel("A").point(lambda v: int(v * p)))
            frame.alpha_composite(ov)
        if which == "all":
            pill(frame, (60, 56), "THE STATE OF LEONIDA", PINK, 38)
        proc.stdin.write(frame.convert("RGB").tobytes())
    proc.stdin.close(); proc.wait()
    if proc.returncode:
        raise RuntimeError("map encode failed")
    return out


# ---------------- music ----------------
def music(total, path):
    raw = WORK / "sw_raw.wav"
    if not raw.exists():
        base.synthwave(40.0, raw)
    with wave.open(str(raw)) as w:
        sr = w.getframerate()
        x = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32767
    bar = 60 / 108 * 4
    a, b = int(4 * bar * sr), int(12 * bar * sr)   # 8 bars, seamless (pattern repeats every 4 bars)
    loop = x[a:b]
    n = int(total * sr)
    y = np.tile(loop, n // len(loop) + 1)[:n]
    t = np.arange(n) / sr
    y *= np.minimum(1, t / 1.5) * np.minimum(1, (total - t) / 3.0)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((np.clip(y, -1, 1) * 32767).astype(np.int16).tobytes())


# ---------------- assemble ----------------
def final(shot_files, shots, vo, total):
    lst = WORK / "concat.txt"
    lst.write_text("".join(f"file '{p}'\n" for p in shot_files))
    silent = WORK / "video.mp4"
    run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
         "-vf", "eq=saturation=1.1:contrast=1.04,colorbalance=rs=-0.03:bs=0.05:rh=0.05:bh=-0.03,vignette=PI/5",
         "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
         "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", str(silent)])
    mus = WORK / "music.wav"
    music(total, mus)
    whoosh = REPO / "assets/bundled-sfx/wall/whoosh.wav"
    impact = REPO / "assets/bundled-sfx/impact/impact_001.opus"
    # voice track: one long concat with silence, built by adelay in chunks
    ins, parts = [], []
    for j, (p, at) in enumerate(vo):
        ins += ["-i", str(p)]
        parts.append(f"[{j}:a]aresample=48000,adelay={int(at*1000)}:all=1,volume=1.6[v{j}]")
    parts.append("".join(f"[v{j}]" for j in range(len(vo))) +
                 f"amix=inputs={len(vo)}:normalize=0,apad=whole_dur={total}[vo]")
    vo_wav = WORK / "voice.wav"
    run(["ffmpeg", "-v", "error", "-y", *ins, "-filter_complex", ";".join(parts),
         "-map", "[vo]", "-ac", "1", "-ar", "48000", str(vo_wav)])
    hits = [s["start"] for s in shots if s["chapter"] or s["spec"][0] == "m"]
    ins = ["-i", str(vo_wav), "-i", str(mus)]
    parts, tags = [], []
    for j, h in enumerate(hits):
        ins += ["-i", str(whoosh)]
        parts.append(f"[{j+2}:a]aresample=48000,adelay={max(0, int(h*1000)-150)}:all=1,volume=0.32[w{j}]")
        tags.append(f"[w{j}]")
    chap = [s["start"] for s in shots if s["chapter"]]
    base_i = 2 + len(hits)
    for j, h in enumerate(chap):
        ins += ["-i", str(impact)]
        parts.append(f"[{base_i+j}:a]aresample=48000,adelay={int(h*1000)+60}:all=1,volume=0.4[i{j}]")
        tags.append(f"[i{j}]")
    parts.append("[0:a]asplit=2[vo][sc]")
    parts.append("[1:a]aresample=48000,volume=0.5[m]")
    parts.append("[m][sc]sidechaincompress=threshold=0.03:ratio=6:attack=20:release=400[duck]")
    parts.append(f"[vo][duck]{''.join(tags)}amix=inputs={len(tags)+2}:normalize=0,"
                 f"alimiter=limit=0.9,atrim=0:{total}[a]")
    mix = WORK / "mix.wav"
    run(["ffmpeg", "-v", "error", "-y", *ins, "-filter_complex", ";".join(parts),
         "-map", "[a]", "-ar", "48000", "-ac", "2", str(mix)])
    out = OUT / "gta6_leonida_vs_florida_full.mp4"
    run(["ffmpeg", "-v", "error", "-y", "-i", str(silent), "-i", str(mix), "-map", "0:v", "-map", "1:a",
         "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-t", f"{total:.3f}", "-movflags", "+faststart", str(out)])
    return out


if __name__ == "__main__":
    make_voice()
    shots, vo, total = timeline()
    print(f"{len(shots)} shots, {total:.1f} s")
    only = [int(a) for a in sys.argv[1:]]
    files = []
    for i, s in enumerate(shots):
        f = WORK / f"shot{i:03d}.mp4"
        if not only or i in only or not f.exists():
            render_shot(i, s)
        files.append(f)
    print(final(files, shots, vo, total), dur(OUT / "gta6_leonida_vs_florida_full.mp4"))
