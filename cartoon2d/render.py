"""Render a 2D cut-out cartoon story from a voiced timeline.

python3 cartoon2d/render.py <story.json> [--stills t1,t2,...] [--out file.mp4]
story.json = {"timeline": ".../timeline.json", "background": "...png", "floor_y": 0.86,
              "cast": {"host": {"dir": "cartoon2d/cast/host", "x": 0.33, "height": 0.62}, ...},
              "music": "playroom", "props": "cartoon2d/art/props"}
Timeline lines (from cartoon3d-engine/authoring/sets/scene_audio.py) carry who/start/end/cues and the story fields
act, also, cam, card, card_at, pic, sfx.
"""
import json
import math
import random
import subprocess
import sys
from functools import lru_cache
from multiprocessing import Pool
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT_W, OUT_H, FPS = 1920, 1080, 25
WORLD_W, WORLD_H = 2560, 1440
SS = 3                                          # supersampling for drawn mouths / lids
FONT = "/System/Library/Fonts/Supplemental/Arial Rounded Bold.ttf"
WHO = ("host", "hoorain", "noraiz")
G = {}                                          # per-process globals (loaded once per worker)


# ------------------------------------------------------------------ maths
def T(x, y):
    return np.array([[1, 0, x], [0, 1, y], [0, 0, 1]], float)


def R(deg):
    """Visual counter-clockwise rotation in y-down screen space."""
    a = math.radians(-deg)
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]], float)


def S(sx, sy=None):
    return np.diag([sx, sx if sy is None else sy, 1.0])


def about(p, M):
    return T(p[0], p[1]) @ M @ T(-p[0], -p[1])


def smooth(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


# ------------------------------------------------------------------ loading
def load(story_path):
    st = json.loads(Path(story_path).read_text())
    tl = json.loads((ROOT / st["timeline"]).read_text())
    G["story"], G["tl"] = st, tl
    bg = Image.open(ROOT / st["background"]).convert("RGB").resize((WORLD_W, WORLD_H), Image.LANCZOS)
    G["bg"] = bg
    G["cast"] = {}
    for who, c in st["cast"].items():
        d = ROOT / c["dir"]
        rig = json.loads((d / "rig.json").read_text())
        parts = {n: Image.open(d / p["file"]).convert("RGBA") for n, p in rig["parts"].items()}
        H = rig["size"][1]
        top = min(p["offset"][1] for p in rig["parts"].values())
        char_h = rig["feet"][1] - top
        k = c["height"] * WORLD_H / char_h                        # source px -> world px
        rig["_who"] = who
        for sd in ("sl", "sr"):
            G.setdefault("cast_hands", {})[(who, sd)] = parts[f"hand_{sd}"]
        G["cast"][who] = {"rig": rig, "parts": parts, "k": k, "x": c["x"] * WORLD_W, "floor": st["floor_y"] * WORLD_H,
                          "char_h": char_h, "top": top, "flip": c.get("flip", False), "H": H,
                          "tilt": c.get("tilt", 1.0)}
    props = ROOT / st.get("props", "cartoon2d/art/props")
    G["pics"] = {}
    for ln in tl["lines"]:
        if ln.get("pic") and ln["pic"] not in G["pics"]:
            G["pics"][ln["pic"]] = sticker(Image.open(props / f"{ln['pic']}.png"))
    plan()


def sticker(img):
    """White background -> transparent (border flood), keep the sticker's own white outline."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import rig as rigmod
    return rigmod.cutout(img.convert("RGB"), thresh=246)


# ------------------------------------------------------------------ planning: acts, cameras, cards
def plan():
    tl, st = G["tl"], G["story"]
    lines = tl["lines"]
    total = tl["total"]
    acts = {w: [] for w in WHO}
    for ln in lines:
        a = ln.get("act") or "talk"
        acts[ln["who"]].append((ln["start"], ln["end"], a, True))
        for w, a2 in (ln.get("also") or {}).items():
            acts[w].append((ln["start"], ln["end"], a2, False))
    for w in WHO:
        acts[w].sort()
    G["acts"] = acts
    # blinks
    G["blinks"] = {}
    for i, w in enumerate(WHO):
        r = random.Random(11 + 7 * i)
        t, out = r.uniform(0.8, 2.0), []
        while t < total:
            out.append(t)
            t += r.uniform(2.4, 4.6)
        G["blinks"][w] = out
    # mouth cue tracks
    G["cues"] = {w: [] for w in WHO}
    for ln in lines:
        for c in ln["cues"]:
            G["cues"][ln["who"]].append((c["t0"], c["t1"], c["shape"]))
    # cameras
    shots, cur, last = [(0.0, "group")], "group", 0.0
    for ln in lines:
        if "cam" in ln:
            want, min_len = ln["cam"], 0.8
        elif ln["who"] == "host":
            want, min_len = ("group" if ln.get("also") else "host"), 1.6
        else:
            want, min_len = "kids", 1.6
        t = max(0.0, ln["start"] - 0.15)
        if want != cur and t - last >= min_len:
            shots.append((t, want))
            cur, last = want, t
    if cur != "group" and total - 1.6 - last > 1.6:
        shots.append((total - 1.6, "group"))             # end on the whole cast
    G["shots"] = shots
    # cards: numbers / colour words; pictures stay up through the answers until the host speaks again
    cards = []
    for i, ln in enumerate(lines):
        if ln.get("card"):
            t0 = ln["start"] + float(ln.get("card_at", 0.0)) * (ln["end"] - ln["start"])
            t1 = max(ln["end"] + 0.7, t0 + 1.2)
            if i + 1 < len(lines) and lines[i + 1].get("card"):
                t1 = min(t1, lines[i + 1]["start"] - 0.02)
            cards.append({"t0": t0, "t1": t1, "text": ln["card"]})
        if ln.get("pic"):
            nxt = next((l2 for l2 in lines[i + 1:] if l2["who"] == "host"), None)
            t1 = (nxt["start"] - 0.1) if nxt else ln["end"] + 4
            cards.append({"t0": ln["start"] + 0.3, "t1": min(t1, ln["start"] + 9), "pic": ln["pic"]})
    G["cards"] = cards


# ------------------------------------------------------------------ poses
REST = {"u_sl": 0.0, "l_sl": 0.0, "u_sr": 0.0, "l_sr": 0.0, "head": 0.0, "hop": 0.0, "sx": 1.0, "sy": 1.0, "bob": 0.0}


def arm(side, upper, lower):
    """Angles in 'outward/up' terms; sl (screen-left) outward is clockwise, so its sign flips."""
    s = 1 if side == "sr" else -1
    return {f"u_{side}": s * upper, f"l_{side}": s * lower}


def hops(lt, dur, n, height):
    """n hops spread over dur; returns (lift 0..1 * height, squash)."""
    per = max(0.42, dur / n)
    k = int(lt // per)
    if k >= n or lt < 0:
        return 0.0, 1.0, 1.0
    p = (lt - k * per) / per
    air = 0.18
    if p < air:                                   # crouch
        q = p / air
        return 0.0, 1.0 + 0.06 * math.sin(math.pi * q), 1.0 - 0.10 * math.sin(math.pi * q)
    q = (p - air) / (1 - air)
    lift = 4 * q * (1 - q) * height
    st = 1.0 + 0.05 * math.sin(math.pi * q)
    return lift, 1.0 / st ** 0.5, st


def act_pose(who, act, lt, dur, speaking):
    p = {}
    if act == "wave":
        side = "sr" if who == "noraiz" else "sl"           # the arm away from the others: never crosses a neighbour
        p.update(arm(side, 72, 88 + 20 * math.sin(2 * math.pi * 2.6 * lt)))
        p["head"] = 3 * math.sin(2 * math.pi * 0.9 * lt)
    elif act in ("cheer", "jump"):
        p.update(arm("sl", 128, 28))
        p.update(arm("sr", 128, 28))
        n = 1 if act == "cheer" else max(1, round(dur / 0.62))
        lift, sx, sy = hops(lt - 0.05, (0.6 if act == "cheer" else max(dur, 0.6)), n, 0.10 if who == "host" else 0.16)
        p.update({"hop": lift, "sx": sx, "sy": sy})
    elif act == "open":
        e = 6 * math.sin(2 * math.pi * 0.8 * lt)
        p.update(arm("sl", 38 + e, 42))
        p.update(arm("sr", 38 - e, 42))
    elif act == "point":
        side = "sr" if who == "host" else "sl"
        p.update(arm(side, 78, 6))
        p.update(arm("sl" if side == "sr" else "sr", 14, 20))
    elif act == "count":
        p.update(arm("sr", 30, 110 + 8 * math.sin(2 * math.pi * 2 * lt)))
        p["head"] = 4 * math.sin(math.pi * min(lt / 0.5, 1))
    elif act == "clap":
        closed = (math.sin(2 * math.pi * 2.4 * lt) > 0)
        inward = -128 if closed else -88
        p.update(arm("sl", 38, inward))
        p.update(arm("sr", 38, inward))
        p["bob"] = 6 * abs(math.sin(2 * math.pi * 2.4 * lt))
    elif act == "giggle":
        p.update(arm("sl", 10, -135))
        p.update(arm("sr", 10, -135))
        p["head"] = 6 * math.sin(2 * math.pi * 3.2 * lt)
        p["bob"] = 8 * abs(math.sin(2 * math.pi * 3.2 * lt))
    else:                                         # talk: a small presenting hand that moves with the words
        side = "sr" if who != "noraiz" else "sl"
        p.update(arm(side, 18 + 6 * math.sin(2 * math.pi * 0.7 * lt), 34 + 10 * math.sin(2 * math.pi * 1.1 * lt)))
    if speaking and "head" not in p:
        p["head"] = 2.2 * math.sin(2 * math.pi * 1.25 * lt)
    return p


def pose_at(who, t):
    out = dict(REST)
    for (t0, t1, act, speaking) in G["acts"][who]:
        if t < t0 - 0.3 or t > t1 + 0.5:
            continue
        w = smooth((t - (t0 - 0.25)) / 0.25) * (1 - smooth((t - (t1 + 0.15)) / 0.3))
        if act in ("cheer", "jump"):                 # hops are timed from the line start; no fading of the lift itself
            w_hop = 1.0
        else:
            w_hop = w
        p = act_pose(who, act, t - t0, t1 - t0, speaking)
        for k, v in p.items():
            ww = w_hop if k in ("hop", "sx", "sy") else w
            out[k] = out[k] + (v - REST[k]) * ww
    # listening: lean the head toward whoever speaks
    spk = next((ln["who"] for ln in G["tl"]["lines"] if ln["start"] - 0.1 <= t <= ln["end"] + 0.2), None)
    if spk and spk != who:
        tilt = {"host": -3.5, "hoorain": 3.0, "noraiz": 3.0}
        sign = 1 if (G["cast"][spk]["x"] > G["cast"][who]["x"]) else -1
        out["head"] += sign * -abs(tilt[who])
    # idle breathing
    ph = {"host": 0.0, "hoorain": 1.3, "noraiz": 2.6}[who]
    out["sy"] *= 1.0 + 0.006 * math.sin(2 * math.pi * t / 3.2 + ph)
    out["sway"] = 0.8 * math.sin(2 * math.pi * t / 4.1 + ph)
    return out


def mouth_at(who, t):
    for t0, t1, shape in G["cues"][who]:
        if t0 <= t < t1:
            return shape
    return "X"


def blink_at(who, t):
    for b in G["blinks"][who]:
        d = t - b
        if 0 <= d < 0.05 or 0.13 <= d < 0.18:
            return 0.55
        if 0.05 <= d < 0.13:
            return 1.0
    return 0.0


# ------------------------------------------------------------------ face drawing (on the head part)
MOUTHS = {  # (width factor, open height factor, teeth, tongue)
    "B": (0.70, 0.20, True, False), "C": (0.80, 0.36, True, True), "D": (0.92, 0.58, True, True),
    "E": (0.58, 0.46, False, True), "F": (0.34, 0.30, False, False), "G": (0.72, 0.18, True, False),
    "H": (0.78, 0.40, True, True),
}


@lru_cache(maxsize=256)
def face_head(who, shape, blink_q):
    c = G["cast"][who]
    rig = c["rig"]
    head = c["parts"]["head"].copy()
    ox, oy = rig["parts"]["head"]["offset"]
    skin, line = tuple(rig["skin"]), tuple(rig["line"])
    W, H = head.size
    big = head.resize((W * SS, H * SS), Image.BICUBIC)
    d = ImageDraw.Draw(big)
    if blink_q > 0:
        for cx, cy, rx, ry in rig["eyes"]:
            cx, cy = (cx - ox) * SS, (cy - oy) * SS
            rx, ry = rx * SS * 1.12, ry * SS * 1.12
            lid_bottom = cy - ry + 2 * ry * blink_q
            # lid: skin from the top of the eye down to lid_bottom, clipped to the eye ellipse
            m = Image.new("L", big.size, 0)
            md = ImageDraw.Draw(m)
            md.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=255)
            md.rectangle([0, 0, big.width, cy - ry - 2], fill=0)
            md.rectangle([0, lid_bottom, big.width, big.height], fill=0)
            big.paste(skin + (255,), (0, 0), m)
            lw = max(2, int(rx * 0.16))
            if blink_q >= 0.99:                        # closed: a soft smiling lash curve
                d.arc([cx - rx * 0.95, cy - ry * 0.55, cx + rx * 0.95, cy + ry * 0.75], 200, 340, fill=line + (255,), width=lw)
            else:
                d.line([(cx - rx * 0.92, lid_bottom), (cx + rx * 0.92, lid_bottom)], fill=line + (255,), width=lw)
    if shape in MOUTHS:
        mo = rig["mouth"]
        mx, my = (mo["c"][0] - ox) * SS, (mo["c"][1] - oy) * SS
        mw, mh = mo["w"] * SS, mo["h"] * SS
        fw, fh, teeth, tongue = MOUTHS[shape]
        # cover the drawn closed mouth with skin
        d.ellipse([mx - mw * 0.62, my - mh * 0.9, mx + mw * 0.62, my + mh * 0.9], fill=skin + (255,))
        w2 = mw * fw / 2
        hgt = max(mw * fh, 4 * SS)
        top = my - hgt * 0.22
        lw = max(2, int(mw * 0.06))
        if shape in ("E", "F"):
            box = [mx - w2, top, mx + w2, top + hgt]
            d.ellipse(box, fill=(110, 30, 40, 255), outline=line + (255,), width=lw)
            if tongue:
                d.ellipse([mx - w2 * 0.6, top + hgt * 0.55, mx + w2 * 0.6, top + hgt * 1.0], fill=(236, 110, 120, 255))
                d.ellipse(box, outline=line + (255,), width=lw)
        else:
            # smiling open mouth: gently curved top lip, round bottom
            pts = []
            lift = lambda u: -hgt * 0.14 * (2 * u - 1) ** 2          # corners curl up: a smile
            for i in range(25):
                u = i / 24
                pts.append((mx - w2 + 2 * w2 * u, top + lift(u)))
            for i in range(25):
                u = 1 - i / 24
                pts.append((mx - w2 + 2 * w2 * u, top + lift(u) + hgt * math.sin(math.pi * u) ** 0.8))
            d.polygon(pts, fill=(110, 30, 40, 255))
            m = Image.new("L", big.size, 0)
            ImageDraw.Draw(m).polygon(pts, fill=255)
            if tongue:
                tg = Image.new("RGBA", big.size, (0, 0, 0, 0))
                ImageDraw.Draw(tg).ellipse([mx - w2 * 0.55, top + hgt * 0.55, mx + w2 * 0.55, top + hgt * 1.35], fill=(236, 110, 120, 255))
                big.paste(tg, (0, 0), Image.fromarray((np.asarray(m) > 0).astype(np.uint8) * np.asarray(tg)[..., 3]))
            if teeth:
                tt = Image.new("RGBA", big.size, (0, 0, 0, 0))
                ImageDraw.Draw(tt).rectangle([mx - w2, top - hgt, mx + w2, top + hgt * 0.24], fill=(255, 255, 255, 255))
                big.paste(tt, (0, 0), Image.fromarray((np.asarray(m) > 0).astype(np.uint8) * np.asarray(tt)[..., 3]))
            d.line(pts + [pts[0]], fill=line + (255,), width=lw, joint="curve")
    return big.resize((W, H), Image.LANCZOS)


# ------------------------------------------------------------------ drawing
def place(canvas, img, M):
    """Draw img (RGBA) on canvas with the affine M (image px -> canvas px), only over its own bounding box."""
    w, h = img.size
    corners = M @ np.array([[0, w, w, 0], [0, 0, h, h], [1, 1, 1, 1]], float)
    x0, y0 = int(math.floor(corners[0].min())), int(math.floor(corners[1].min()))
    x1, y1 = int(math.ceil(corners[0].max())), int(math.ceil(corners[1].max()))
    x0c, y0c, x1c, y1c = max(0, x0), max(0, y0), min(canvas.width, x1), min(canvas.height, y1)
    if x1c <= x0c or y1c <= y0c:
        return
    inv = np.linalg.inv(T(x0c, y0c) @ np.eye(3))
    Mi = np.linalg.inv(M) @ T(x0c, y0c)
    sc = math.hypot(M[0, 0], M[1, 0])
    src = img
    if sc < 0.7:                                   # big downscale: pre-shrink so bicubic does not alias
        f = max(sc * 1.4, 0.05)
        src = img.resize((max(1, int(w * f)), max(1, int(h * f))), Image.LANCZOS)
        Mi = S(f) @ Mi
    data = (Mi[0, 0], Mi[0, 1], Mi[0, 2], Mi[1, 0], Mi[1, 1], Mi[1, 2])
    out = src.convert("RGBa").transform((x1c - x0c, y1c - y0c), Image.AFFINE, data, resample=Image.BICUBIC).convert("RGBA")
    canvas.alpha_composite(out, (x0c, y0c))
    del inv


def cam_rect(t):
    shots = G["shots"]
    k = max(i for i, s in enumerate(shots) if s[0] <= t)
    t0, name = shots[k]
    t1 = shots[k + 1][0] if k + 1 < len(shots) else G["tl"]["total"]
    prog = smooth((t - t0) / max(t1 - t0, 0.1))
    c = G["cast"]
    if name == "group":
        w = WORLD_W * (1.0 - 0.06 * prog)
        cx, cy = WORLD_W / 2, WORLD_H / 2 + 20
    elif name == "host":
        h = c["host"]
        w = h["char_h"] * h["k"] * 1.55 * (1.0 - 0.05 * prog)
        cx = h["x"] + w * 0.16                         # host left of centre: cards sit on the right
        cy = h["floor"] - h["char_h"] * h["k"] * 0.62
    else:
        kx = (c["hoorain"]["x"] + c["noraiz"]["x"]) / 2
        span = abs(c["hoorain"]["x"] - c["noraiz"]["x"])
        hh = max(c["hoorain"]["char_h"] * c["hoorain"]["k"], c["noraiz"]["char_h"] * c["noraiz"]["k"])
        w = max(span * 2.3, hh * 1.95) * (1.0 - 0.05 * prog)
        cx = kx - w * 0.06                             # kids a little right of centre: room for cards on the left
        cy = c["hoorain"]["floor"] - hh * 0.56
    h_ = w * OUT_H / OUT_W
    cx = min(max(cx, w / 2), WORLD_W - w / 2)
    cy = min(max(cy, h_ / 2), WORLD_H - h_ / 2)
    return cx - w / 2, cy - h_ / 2, w, name


@lru_cache(maxsize=64)
def card_img(text, size):
    colours = {"PINK": (255, 105, 180), "BLUE": (40, 120, 230), "RED": (230, 60, 60)}
    nums = [(255, 90, 90), (255, 165, 40), (60, 190, 90), (60, 150, 240), (170, 90, 230)]
    col = colours.get(text) or (nums[(int(text) - 1) % 5] if text.isdigit() else (255, 150, 40))
    font = ImageFont.truetype(FONT, int(size * (0.62 if text.isdigit() else 0.34)))
    tw = font.getbbox(text)[2] - font.getbbox(text)[0]
    W = max(size, int(tw + size * 0.5))
    im = Image.new("RGBA", (W + 24, size + 24), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([12, 18, W + 12, size + 18], radius=size // 4, fill=(0, 0, 0, 70))
    d.rounded_rectangle([8, 8, W + 8, size + 8], radius=size // 4, fill=(255, 255, 255, 255))
    d.rounded_rectangle([18, 18, W - 2, size - 2], radius=size // 5, fill=col + (255,))
    d.text(((W + 16) / 2, (size + 16) / 2), text, font=font, fill=(255, 255, 255, 255), anchor="mm",
           stroke_width=max(3, size // 40), stroke_fill=tuple(int(v * 0.55) for v in col) + (255,))
    return im.filter(ImageFilter.SMOOTH)


def char_boxes(t):
    """Each character's head box and body box in output pixels for the camera at time t."""
    x0, y0, w, _ = cam_rect(t)
    z = OUT_W / w
    out = []
    for who in WHO:
        c = G["cast"][who]
        hpx = c["char_h"] * c["k"]
        cx, fl = c["x"], c["floor"]
        head = ((cx - hpx * 0.26 - x0) * z, (fl - hpx * 1.08 - y0) * z, (cx + hpx * 0.26 - x0) * z, (fl - hpx * 0.62 - y0) * z)
        body = ((cx - hpx * 0.30 - x0) * z, (fl - hpx * 0.62 - y0) * z, (cx + hpx * 0.30 - x0) * z, (fl - y0) * z)
        out.append((head, body))
    return out


def card_spot(t, cam, size):
    def ov(a, b):
        return max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
    boxes = char_boxes(t)
    pref = {"host": (1400, 420), "kids": (330, 400), "group": (960, 260)}[cam]
    best = None
    for x in range(int(size * 0.6) + 20, OUT_W - int(size * 0.6) - 19, 40):
        for y in (220, 300, 380, 460):
            r = (x - size * 0.6, y - size / 2, x + size * 0.6, y + size / 2)
            sc = sum(3 * ov(r, h) + ov(r, b) for h, b in boxes) + 40 * math.hypot(x - pref[0], y - pref[1])
            if best is None or sc < best[0]:
                best = (sc, x, y)
    return best[1], best[2]


def draw_cards(frame, t, cam):
    for cd in G["cards"]:
        if not (cd["t0"] <= t <= cd["t1"]):
            continue
        a = t - cd["t0"]
        out = cd["t1"] - t
        s = (0.0 if a < 0 else (1.18 * smooth(a / 0.16) if a < 0.16 else 1.18 - 0.18 * smooth((a - 0.16) / 0.12)))
        s *= smooth(out / 0.18) if out < 0.18 else 1.0
        if s <= 0.02:
            continue
        if "pic" in cd:
            base = G["pics"][cd["pic"]]
            size = 470
            im = base.resize((int(base.width * size / base.height), size), Image.LANCZOS)
        else:
            im = card_img(cd["text"], 260)
        im = im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))), Image.BICUBIC)
        bob = 8 * math.sin(2 * math.pi * 0.8 * a)
        cx, cy = card_spot(t, cam, 470 if "pic" in cd else 300)
        frame.alpha_composite(im, (int(cx - im.width / 2), int(cy + bob - im.height / 2)))


LINE_W = 5.5                                    # outline thickness in source pixels (matches the art)


def arm_points(rig, side, pz):
    """Shoulder, sleeve end, elbow, wrist in source px after the pose; also the forearm angle change."""
    a = rig["arms"][side]
    S, E, W, SE = (np.array(a[k], float) for k in ("S", "E", "W", "SE"))
    ru, rl = pz[f"u_{side}"], pz[f"l_{side}"]
    Mu = about(S, R(ru))
    E2 = (Mu @ [*E, 1])[:2]
    SE2 = (Mu @ [*SE, 1])[:2]
    W1 = (Mu @ [*W, 1])[:2]
    W2 = (about(E2, R(rl)) @ [*W1, 1])[:2]
    return S, SE2, E2, W2, ru + rl


def draw_arm(frame, M, rig, side, pz, part):
    """part: 'back' = sleeve + upper + forearm (behind the body); 'front' = forearm + hand again, over the body."""
    a = rig["arms"][side]
    S, SE, E, W, rot = arm_points(rig, side, pz)
    sc = math.sqrt(abs(np.linalg.det(M[:2, :2])))
    pts = [(M @ [*q, 1])[:2] for q in (S, SE, E, W)]
    fw = a["fw"]
    uw = min(a["uw"], fw * 1.15)
    sw = max(a["sw"], uw + 8)
    lw = LINE_W
    xs, ys = [q[0] for q in pts], [q[1] for q in pts]
    pad = sw * sc + 8
    x0, y0 = int(min(xs) - pad), int(min(ys) - pad)
    x1, y1 = int(max(xs) + pad), int(max(ys) + pad)
    x0c, y0c, x1c, y1c = max(0, x0), max(0, y0), min(frame.width, x1), min(frame.height, y1)
    if x1c <= x0c or y1c <= y0c:
        return
    K = 2                                           # supersample the tubes
    cv = Image.new("RGBA", ((x1c - x0c) * K, (y1c - y0c) * K), (0, 0, 0, 0))
    d = ImageDraw.Draw(cv)
    P = [((q[0] - x0c) * K, (q[1] - y0c) * K) for q in pts]
    s_, se_, e_, w_ = P
    line = tuple(rig["line"]) + (255,)
    skin, sleeve = tuple(a["skin"]) + (255,), tuple(a["sleeve"]) + (255,)
    k = sc * K

    def seg(p0, p1, wd, col):
        d.line([p0, p1], fill=col, width=max(1, int(wd * k)))
        r = wd * k / 2
        for q in (p0, p1):
            d.ellipse([q[0] - r, q[1] - r, q[0] + r, q[1] + r], fill=col)
    if part == "back":
        seg(e_, w_, fw, line)
        seg(se_, e_, uw, line)
        seg(e_, w_, fw - 2 * lw, skin)
        seg(se_, e_, uw - 2 * lw, skin)
        # sleeve: a wider tube from the shoulder to the hem, with its own outline and hem line
        seg(s_, se_, sw, line)
        seg(s_, se_, sw - 2 * lw, sleeve)
    else:
        seg(e_, w_, fw, line)
        seg(e_, w_, fw - 2 * lw, skin)
        r = (uw - 2 * lw) * k / 2                    # elbow fill hides the forearm cap outline inside the upper arm
        d.ellipse([e_[0] - r, e_[1] - r, e_[0] + r, e_[1] + r], fill=skin)
    cv = cv.resize((x1c - x0c, y1c - y0c), Image.LANCZOS)
    frame.alpha_composite(cv, (x0c, y0c))
    # the hand from the picture, turned with the forearm
    hp = rig["parts"][f"hand_{side}"]
    Wsrc = np.array(a["W"], float)
    Mh = M @ T(*W) @ R(rot) @ T(-Wsrc[0], -Wsrc[1]) @ T(*hp["offset"])
    place(frame, G["cast_hands"][(rig["_who"], side)], Mh)
    # cover the hand's cut wrist edge with a short stroke of forearm skin
    wq = pts[3]
    eq = pts[2]
    v = (wq - eq) / max(np.linalg.norm(wq - eq), 1e-6)
    p0 = wq - v * fw * sc * 0.55
    p1 = wq + v * fw * sc * 0.05
    bx0, by0 = int(min(p0[0], p1[0]) - fw * sc), int(min(p0[1], p1[1]) - fw * sc)
    cw, ch = int(abs(p0[0] - p1[0]) + 2 * fw * sc) + 2, int(abs(p0[1] - p1[1]) + 2 * fw * sc) + 2
    if cw > 2 and ch > 2:
        cv2_ = Image.new("RGBA", (cw * 2, ch * 2), (0, 0, 0, 0))
        dd = ImageDraw.Draw(cv2_)
        q0, q1 = ((p0[0] - bx0) * 2, (p0[1] - by0) * 2), ((p1[0] - bx0) * 2, (p1[1] - by0) * 2)
        dd.line([q0, q1], fill=skin, width=max(1, int((fw - 2 * lw - 1) * sc * 2)))
        cv2_ = cv2_.resize((cw, ch), Image.LANCZOS)
        frame.alpha_composite(cv2_, (bx0, by0)) if bx0 >= 0 and by0 >= 0 else frame.paste(cv2_, (bx0, by0), cv2_)


def draw_arm_upper_only(frame, M, rig, side, pz):
    a = rig["arms"][side]
    saved = dict(a)
    S, SE, E, W, rot = arm_points(rig, side, pz)
    # draw sleeve + upper arm only: reuse draw_arm's back pass with a zero-length forearm and no hand
    sc = math.sqrt(abs(np.linalg.det(M[:2, :2])))
    pts = [(M @ [*q, 1])[:2] for q in (S, SE, E)]
    uw = min(a["uw"], a["fw"] * 1.15)
    sw = max(a["sw"], uw + 8)
    pad = sw * sc + 8
    xs, ys = [q[0] for q in pts], [q[1] for q in pts]
    x0c, y0c = max(0, int(min(xs) - pad)), max(0, int(min(ys) - pad))
    x1c, y1c = min(frame.width, int(max(xs) + pad)), min(frame.height, int(max(ys) + pad))
    if x1c <= x0c or y1c <= y0c:
        return
    K = 2
    cv = Image.new("RGBA", ((x1c - x0c) * K, (y1c - y0c) * K), (0, 0, 0, 0))
    d = ImageDraw.Draw(cv)
    s_, se_, e_ = [((q[0] - x0c) * K, (q[1] - y0c) * K) for q in pts]
    k = sc * K
    line = tuple(rig["line"]) + (255,)

    def seg(p0, p1, wd, col):
        d.line([p0, p1], fill=col, width=max(1, int(wd * k)))
        r = wd * k / 2
        for q in (p0, p1):
            d.ellipse([q[0] - r, q[1] - r, q[0] + r, q[1] + r], fill=col)
    seg(se_, e_, uw, line)
    seg(se_, e_, uw - 2 * LINE_W, tuple(a["skin"]) + (255,))
    seg(s_, se_, sw, line)
    seg(s_, se_, sw - 2 * LINE_W, tuple(a["sleeve"]) + (255,))
    cv = cv.resize((x1c - x0c, y1c - y0c), Image.LANCZOS)
    frame.alpha_composite(cv, (x0c, y0c))
    del saved


def crosses_body(pz, side):
    """Forearm folded inward (clap, giggle): it must be drawn in front of the body."""
    s = 1 if side == "sr" else -1
    return s * pz[f"l_{side}"] < -40


def char_matrix(who, pose):
    c = G["cast"][who]
    rig = c["rig"]
    f = rig["feet"]
    k = c["k"]
    root = T(c["x"], c["floor"] - pose["hop"] * c["char_h"] * k - pose["bob"]) @ S(k) @ R(pose.get("sway", 0)) @ S(pose["sx"], pose["sy"]) @ T(-f[0], -f[1])
    if c["flip"]:
        root = root @ about(f, S(-1, 1))
    return root


def render_frame(fi):
    t = fi / FPS
    x0, y0, w, cam = cam_rect(t)
    z = OUT_W / w
    frame = G["bg"].crop((int(x0), int(y0), int(x0 + w), int(y0 + w * OUT_H / OUT_W))).resize((OUT_W, OUT_H), Image.BICUBIC).convert("RGBA")
    C = S(z) @ T(-x0, -y0)
    shadow_layer = Image.new("RGBA", (OUT_W, OUT_H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow_layer)
    poses = {who: pose_at(who, t) for who in WHO}
    for who in WHO:
        c = G["cast"][who]
        sw = c["char_h"] * c["k"] * 0.22 * z * (1 - 0.35 * min(poses[who]["hop"] / 0.16, 1))
        px, py = (c["x"] - x0) * z, (c["floor"] - y0) * z
        sd.ellipse([px - sw, py - sw * 0.16, px + sw, py + sw * 0.16], fill=(40, 20, 40, 70))
    frame.alpha_composite(shadow_layer.filter(ImageFilter.GaussianBlur(6)))
    order = sorted(WHO, key=lambda w: G["cast"][w]["floor"])
    for who in order:
        c = G["cast"][who]
        rig, pz = c["rig"], poses[who]
        M = C @ char_matrix(who, pz)
        P = rig["parts"]
        Mh = M @ about(P["head"]["pivot"], R(pz["head"] * c["tilt"]))     # hair crossing the neck cut limits the tilt
        off = lambda n: T(*P[n]["offset"])
        front = [sd for sd in ("sl", "sr") if crosses_body(pz, sd)]
        for side in ("sl", "sr"):
            if side not in front:
                draw_arm(frame, M, rig, side, pz, "back")
            else:                                      # sleeve + upper arm behind; forearm and hand in front later
                draw_arm_upper_only(frame, M, rig, side, pz)
        place(frame, c["parts"]["body"], M @ off("body"))
        bq = blink_at(who, t)
        head_img = face_head(who, mouth_at(who, t), bq) if (bq or mouth_at(who, t) in MOUTHS) else c["parts"]["head"]
        place(frame, head_img, Mh @ off("head"))
        for side in front:
            draw_arm(frame, M, rig, side, pz, "front")
    draw_cards(frame, t, cam)
    return frame.convert("RGB")


def _init(story_path):
    load(story_path)


def _frame_bytes(fi):
    return render_frame(fi).tobytes()


def main():
    story = sys.argv[1]
    args = sys.argv[2:]
    load(story)
    st = G["story"]
    build = ROOT / st.get("build", "cartoon2d/build/story1")
    build.mkdir(parents=True, exist_ok=True)
    if "--stills" in args:
        ts = [float(x) for x in args[args.index("--stills") + 1].split(",")]
        ims = [render_frame(int(round(t * FPS))) for t in ts]
        cols = 3
        th = [im.resize((640, 360), Image.LANCZOS) for im in ims]
        sheet = Image.new("RGB", (640 * cols, 360 * math.ceil(len(th) / cols)), "white")
        for i, im in enumerate(th):
            ImageDraw.Draw(im).text((10, 8), f"{ts[i]:.1f}s", fill=(0, 0, 0))
            sheet.paste(im, ((i % cols) * 640, (i // cols) * 360))
        sheet.save(build / "stills.jpg", quality=88)
        for t, im in zip(ts, ims):
            im.save(build / f"still_{t:06.2f}.jpg", quality=90)
        print("STILLS", build / "stills.jpg")
        return
    out = ROOT / (args[args.index("--out") + 1] if "--out" in args else f"{st.get('build', 'cartoon2d/build/story1')}/video_silent.mp4")
    n = int(G["tl"]["total"] * FPS)
    ff = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{OUT_W}x{OUT_H}", "-r", str(FPS),
                           "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
                           "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", str(out)], stdin=subprocess.PIPE)
    with Pool(7, initializer=_init, initargs=(story,)) as pool:
        for i, b in enumerate(pool.imap(_frame_bytes, range(n), chunksize=6)):
            ff.stdin.write(b)
            if i % 250 == 0:
                print("FRAME", i, "/", n, flush=True)
    ff.stdin.close()
    ff.wait()
    print("VIDEO", out, ff.returncode)


if __name__ == "__main__":
    main()
