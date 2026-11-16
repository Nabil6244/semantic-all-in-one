"""Render a 2D cut-out cartoon story from a voiced timeline.

python3 cartoon2d/render.py <story.json> [--stills t1,t2,...] [--out file.mp4]
story.json = {"timeline": ".../timeline.json", "background": "...png", "floor_y": 0.86,
              "cast": {"molly": {"dir": "cartoon2d/cast/molly", "x": 0.33, "height": 0.62}, ...},
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
sys.path.insert(0, str(Path(__file__).resolve().parent))
import hook  # noqa: E402
import games  # noqa: E402
import scenery  # noqa: E402
import places  # noqa: E402
import fx  # noqa: E402
import story_fx  # noqa: E402
import storycheck  # noqa: E402
OUT_W, OUT_H, FPS = 1920, 1080, 25
WORLD_W, WORLD_H = 2560, 1440
SS = 3                                          # supersampling for drawn mouths / lids
SHUTTER = 0.012                                 # motion blur: smear = speed x this (s); ~ a 1/80 s shutter, kept light
FONT = "/System/Library/Fonts/Supplemental/Arial Rounded Bold.ttf"
# vibrant kids-TV colour: the Flow art comes out pale/pastel. Vibrance lifts the dull colours most (skin is guarded by the
# low red balance, so faces and Bobo's fur stay natural), plus a little contrast and deeper mid-tones. Applied in the encode.
# Stage C finish: crisper outlines (a light unsharp on brightness only). A highlight glow and a vignette were tried and
# dulled the colours, so they are left out. Story "grade" can still replace it all (false = the art's own colours).
GRADE = ("vibrance=intensity=0.18:rbal=0.6:gbal=1.2:bbal=1.3,eq=contrast=1.07:saturation=1.06:gamma=0.95,"
         "unsharp=5:5:0.45:5:5:0")
ENCODE = ["-c:v", "libx264", "-preset", "slow", "-tune", "animation", "-crf", "17"]   # flat colours + lines: animation tune
WHO = []                                        # cast ids in story order (filled by load)
HOST = "molly"
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
    global HOST
    st = json.loads(Path(story_path).read_text())
    tl = json.loads((ROOT / st["timeline"]).read_text())
    G["story"], G["tl"] = st, tl
    G["hook"] = hook.windows(st, tl)
    WHO[:] = list(st["cast"])
    HOST = st.get("host", WHO[0])
    places = st.get("places") or {"main": {"background": st["background"], "floor_y": st["floor_y"],
                                            "spots": {w: c["x"] for w, c in st["cast"].items()}}}
    G["places"] = {}
    for name, pl in places.items():
        G["places"][name] = {"bg": Image.open(ROOT / pl["background"]).convert("RGB").resize((WORLD_W, WORLD_H), Image.LANCZOS),
                             "floor": pl["floor_y"] * WORLD_H, "spots": {w: x * WORLD_W for w, x in pl["spots"].items()}}
        if st.get("scenery", True):                    # living place: depth parallax, clouds, leaves, water, light
            G["places"][name]["scene"] = scenery.prepare(G["places"][name]["bg"], pl["floor_y"], G["places"][name]["spots"],
                                                         outdoor=pl.get("outdoor"))
    G["start_place"] = st.get("start_place", next(iter(places)))
    first = G["places"][G["start_place"]]
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
        for shp, by_side in (rig.get("hand_shapes") or {}).items():
            for sd, h in by_side.items():
                G.setdefault("hs", {})[(who, shp, sd)] = Image.open(d / h["file"]).convert("RGBA")
        G["cast"][who] = {"rig": rig, "parts": parts, "k": k, "x": first["spots"][who], "floor": first["floor"],
                          "char_h": char_h, "top": top, "flip": c.get("flip", False), "H": H,
                          "tilt": c.get("tilt", 1.0), "hop": c.get("hop", 0.16), "listen": c.get("listen", 3.0),
                          "hold_side": c.get("hold_side", "sr")}
        sj = d / "side" / "side.json"
        if sj.exists() and st.get("side_views", True):   # profile for walking / running (cartoon2d/side.py)
            info = json.loads(sj.read_text())
            leg = Image.open(d / "side" / "leg.png").convert("RGBA")
            far = Image.eval(leg.convert("RGB"), lambda v: int(v * 0.8)).convert("RGBA")
            far.putalpha(leg.getchannel("A"))
            G["cast"][who]["side"] = {"info": info, "upper": Image.open(d / "side" / "upper.png").convert("RGBA"), "leg": leg,
                                      "far": far, "k": c["height"] * WORLD_H / info["height"]}
    dirs = st.get("props", "cartoon2d/art/props")
    dirs = [ROOT / d for d in (dirs if isinstance(dirs, list) else [dirs])]
    names = set()
    for ln in tl["lines"]:
        if ln.get("pic"):
            names.add(ln["pic"])
        for v in (ln.get("hold") or {}).values():
            names.add(v)
        if ln.get("give"):
            names.add(ln["give"]["pic"])
    names |= games.pics(tl)
    names |= {ln["find"]["pic"] for ln in tl["lines"] if ln.get("find")}
    G["pics"] = {}
    for n in sorted(names):
        f = next((d / f"{n}.png" for d in dirs if (d / f"{n}.png").exists()), None)
        if f is None:
            raise FileNotFoundError(f"picture {n}.png not found in {dirs}")
        G["pics"][n] = sticker(Image.open(f))
    plan()
    plan_fx()


def sticker(img):
    """White background -> transparent (border flood), keep the sticker's own white outline."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import rig as rigmod
    return rigmod.cutout(img.convert("RGB"), thresh=246)


# ------------------------------------------------------------------ planning: acts, cameras, cards
def speakers(ln):
    return [ln["who"]] + list(ln.get("with") or [])


def default_cam(ln):
    sp = speakers(ln)
    kids = G["story"].get("kids", [])
    if len(sp) > 2 or ln.get("also") and HOST in sp:
        return "group"
    if all(w in kids for w in sp):
        return "kids"
    if sp == [HOST]:
        return "host"
    return f"cu:{sp[0]}" if len(sp) == 1 else "group"


def plan():
    tl, st = G["tl"], G["story"]
    lines = tl["lines"]
    total = tl["total"]
    acts = {w: [] for w in WHO}
    beats = []
    for ln in lines:
        a = ln.get("act") or "talk"
        for w in speakers(ln):
            acts[w].append((ln["start"], ln["end"], a, True))
        for w, a2 in (ln.get("also") or {}).items():
            acts[w].append((ln["start"], ln["end"], a2, False))
        if ln.get("chant"):
            beats += ln.get("beats", [])
            for w in WHO:                              # everybody claps on the beat through a song unless told otherwise
                if w not in speakers(ln) and w not in (ln.get("also") or {}):
                    acts[w].append((ln["start"], ln["end"], "beatclap", False))
    for w in WHO:
        acts[w].sort(key=lambda x: (x[0], x[1]))
    G["acts"], G["beats"] = acts, sorted(beats)
    # places: a change happens in the pause before its line, with a circle wipe
    changes = []
    for ln in lines:
        if ln.get("place"):
            changes.append((max(0.0, ln["start"] - 0.45), ln["place"]))
    G["place_changes"] = changes
    # moves: line field go / run {who: target}; target = world fraction 0..1, "home" (own spot) or a cast name (go beside them)
    G["moves"] = {w: [] for w in WHO}
    place, place_t = G["start_place"], 0.0
    pos = dict(G["places"][place]["spots"])
    busy = {w: 0.0 for w in WHO}
    for ln in lines:
        if ln.get("place") and ln["place"] != place:
            place, place_t = ln["place"], max(0.0, ln["start"] - 0.45)
            pos = dict(G["places"][place]["spots"])
        for kind in ("go", "run"):
            for w, tgt in (ln.get(kind) or {}).items():
                spots = G["places"][place]["spots"]
                if tgt == "home":
                    x1 = spots[w]
                elif isinstance(tgt, str):
                    side = 1 if pos[w] > pos[tgt] else -1
                    hs = G["story"]["cast"]
                    x1 = pos[tgt] + side * 0.3 * (hs[w]["height"] + hs[tgt]["height"]) * WORLD_H   # side by side, not overlapping
                else:
                    x1 = float(tgt) * WORLD_W
                x1 = min(max(x1, 0.06 * WORLD_W), 0.94 * WORLD_W)
                speed = (0.11 if kind == "go" else 0.24) * WORLD_W
                t0 = max(ln["start"] + 0.1, busy[w])
                t1 = t0 + max(0.6, abs(x1 - pos[w]) / speed)
                G["moves"][w].append({"t0": t0, "t1": t1, "x0": pos[w], "x1": x1, "kind": "walk" if kind == "go" else "run",
                                      "place_t": place_t})
                pos[w], busy[w] = x1, t1
    # blinks
    G["blinks"] = {}
    for i, w in enumerate(WHO):
        r = random.Random(11 + 7 * i)
        t, out = r.uniform(0.8, 2.0), []
        while t < total:
            out.append(t)
            t += r.uniform(2.4, 4.6)
        G["blinks"][w] = out
    # mouth cue tracks (lines spoken together carry one track per speaker)
    G["cues"] = {w: [] for w in WHO}
    for ln in lines:
        by = ln.get("cues_by") or {ln["who"]: ln["cues"]}
        for w, cs in by.items():
            for c in cs:
                G["cues"][w].append((c["t0"], c["t1"], c["shape"]))
    for w in WHO:
        G["cues"][w].sort()
    # cameras: speaker-led, explicit cam wins, no shot shorter than ~1.6 s; a place change always cuts to the group
    shots, cur, last = [(0.0, lines[0].get("cam", "group") if lines else "group")], None, 0.0
    cur = shots[0][1]
    ch_t = [c[0] for c in changes]
    for ln in lines:
        want = ln.get("cam") or default_cam(ln)
        min_len = 0.8 if "cam" in ln else 1.6
        t = max(0.0, ln["start"] - 0.15)
        if ln.get("place"):
            want, min_len = ln.get("cam", "group"), 0.0
        if want != cur and t - last >= min_len:
            shots.append((t, want))
            cur, last = want, t
    if cur != "group" and total - 2.0 - last > 1.6:
        shots.append((total - 2.0, "group"))
    G["shots"] = shots
    del ch_t
    # cards: numbers / colour words; pictures stay up through the answers until the host speaks again
    cards = []
    for i, ln in enumerate(lines):
        if ln.get("card"):
            t0 = ln["start"] + float(ln.get("card_at", 0.0)) * (ln["end"] - ln["start"])
            t1 = max(ln["end"] + 0.7, t0 + 1.2)
            if i + 1 < len(lines) and (lines[i + 1].get("card") or lines[i + 1].get("pic")):
                t1 = min(t1, lines[i + 1]["start"] - 0.02)
            cards.append({"t0": t0, "t1": t1, "text": ln["card"]})
        if ln.get("pic"):
            nxt = next((l2 for l2 in lines[i + 1:] if l2["who"] == HOST or l2.get("pic") or l2.get("card") or l2.get("place")), None)
            t1 = (nxt["start"] - 0.1) if nxt else ln["end"] + 4
            cards.append({"t0": ln["start"] + 0.3, "t1": max(ln["start"] + 2.0, min(t1, ln["start"] + 10)), "pic": ln["pic"]})
        for w in ln.get("words") or []:                 # song words flash their colour card
            key = w["text"].strip(".,!?").lower()
            if key in (ln.get("word_cards") or {}):
                cards.append({"t0": w["t0"], "t1": w["t0"] + 0.85, "text": ln["word_cards"][key]})
    G["cards"] = cards
    # props held in hands, handed over
    holds, flights, open_ = [], [], {}
    for ln in lines:
        for w in (ln.get("drop") or []):
            if w in open_:
                h = open_.pop(w); h["t1"] = ln["start"]; holds.append(h)
        if ln.get("give"):
            g = ln["give"]
            tg = ln["start"] + 0.35
            if g["from"] in open_:
                h = open_.pop(g["from"]); h["t1"] = tg; holds.append(h)
            flights.append({"pic": g["pic"], "from": g["from"], "to": g["to"], "t0": tg, "t1": tg + 0.75})
            open_[g["to"]] = {"who": g["to"], "pic": g["pic"], "t0": tg + 0.75}
        for w, pic in (ln.get("hold") or {}).items():
            if w in open_:
                h = open_.pop(w); h["t1"] = ln["start"]; holds.append(h)
            open_[w] = {"who": w, "pic": pic, "t0": ln["start"]}
    for h in open_.values():
        h["t1"] = total + 1
        holds.append(h)
    G["games"] = games.plan(G["tl"])
    for b in G["games"]["ball"]:                       # a ball in play is not in anybody's hand
        for w in ([b["from"]] if b["kind"] == "throw" else [b["who"]]):
            for h in list(holds):
                if h["who"] == w and h["pic"] == b["pic"] and h["t0"] < b["t0"] < h["t1"]:
                    holds.remove(h)
                    holds.append(dict(h, t1=b["t0"]))
                    if b["kind"] == "dribble":
                        holds.append(dict(h, t0=b["t1"]))
        if b["kind"] == "throw":                       # the catcher keeps it
            holds.append({"who": b["to"], "pic": b["pic"], "t0": b["t1"],
                          "t1": min([h2["t0"] for h2 in holds if h2["who"] == b["to"] and h2["t0"] > b["t1"]] +
                                    [g2["t0"] for g2 in G["games"]["ball"] if g2 is not b and g2["t0"] > b["t1"]
                                     and b["to"] in (g2.get("from"), g2.get("who"))] +
                                    [f2["t0"] for f2 in flights if f2["from"] == b["to"] and f2["t0"] > b["t1"]] +    # handed over
                                    [ln2["start"] for ln2 in lines if ln2["start"] > b["t1"] and                      # dropped / place
                                     (b["to"] in (ln2.get("drop") or []) or ln2.get("place"))] + [total + 1])})
    G["holds"], G["flights"] = holds, flights
    # title / end cards
    G["titles"] = []
    for ln in lines:
        if ln.get("title"):
            G["titles"].append({"t0": ln["start"], "t1": ln["start"] + 2.6, "text": ln["title"], "kind": "title"})
        if ln.get("endcard"):
            G["titles"].append({"t0": ln["end"] + 0.3, "t1": total, "text": ln["endcard"], "kind": "end"})


def x_at(who, t):
    """World x of a character at t: its spot in the current place, moved by 'go' / 'run' lines (eased)."""
    x = G["cast"][who]["spot"]
    for m in G["moves"].get(who, []):
        if m["t0"] > t or m["place_t"] > t:
            break
        if m["place_t"] < G["cur_place_t"]:
            continue
        if t >= m["t1"]:
            x = m["x1"]
        else:
            q = (t - m["t0"]) / (m["t1"] - m["t0"])
            x = m["x0"] + (m["x1"] - m["x0"]) * (q * q * (3 - 2 * q) * 0.35 + q * 0.65)
    return x


def moving(who, t):
    """(kind, distance covered, direction, weight) while a character walks or runs, else None."""
    for m in G["moves"].get(who, []):
        if m["t0"] - 0.15 <= t <= m["t1"] + 0.2 and m["place_t"] >= G["cur_place_t"]:
            q = min(smooth((t - m["t0"] + 0.15) / 0.2), 1 - smooth((t - m["t1"]) / 0.2))
            tt = min(max(t, m["t0"]), m["t1"])
            dist = abs(x_at(who, tt) - m["x0"])
            return m["kind"], dist, (1 if m["x1"] > m["x0"] else -1), q
    return None


def place_at(t):
    name = G["start_place"]
    for tc, n in G["place_changes"]:
        if t >= tc:
            name = n
    return name


HOP_ACTS = ("cheer", "jump", "bounce", "frog", "kangaroo", "bunny", "tumble")
SPARKLE_ACTS = ("cheer", "yay", "thumbs_up")


def plan_fx():
    """Stage B: landing times (dust), sparkle windows, full-screen effects (line "fx") and the transition of each place
    change (line "tr", else iris / star / push / page in turn)."""
    G["cur_place_t"] = 0.0
    G["landings"], G["sparkle"], G["screen_fx"], G["tr_kind"] = [], [], [], {}
    for who in WHO:
        for (t0, t1, act, _) in G["acts"][who]:
            if act in SPARKLE_ACTS:
                G["sparkle"].append((who, t0, t1 + 0.6))
            if act not in HOP_ACTS:
                continue
            prev, t = 0.0, t0
            while t < t1 + 1.6:
                h = pose_at(who, t)["hop"]
                if prev > 0.012 and h <= 0.004:
                    G["landings"].append((t, who, prev))
                prev, t = h, t + 0.02
    for i, ln in enumerate(G["tl"]["lines"]):
        if ln.get("fx"):
            G["screen_fx"].append((ln["start"], max(1.0, ln["end"] - ln["start"] + 0.5), ln["fx"], i))
    # hidden objects: shown in their place from the arrival there, found on the line that says "found"
    G["finds"] = []
    for ln in G["tl"]["lines"]:
        f = ln.get("find")
        if f:
            pl = place_at(ln["start"])
            arr = max([tc for tc, n in G["place_changes"] if n == pl and tc <= ln["start"]] or [0.0])
            fd = next((l2["start"] for l2 in G["tl"]["lines"] if l2.get("found") == f["pic"] and l2["start"] >= ln["start"]), None)
            G["finds"].append({**f, "place": pl, "t0": arr, "found": fd, "size": f.get("size", 0.09)})
    G["maps"] = [(ln["start"] - 0.1, ln["end"] + 0.5, ln["map"]) for ln in G["tl"]["lines"] if ln.get("map") is not None]
    ends = [ln["start"] for ln in G["tl"]["lines"] if ln.get("endcard")]
    G["end_screen"] = max(ends[-1], G["tl"]["total"] - 20.0) if ends and G["story"].get("end_screen", True) else None
    k = 0
    for tc, n in G["place_changes"]:
        ln = next((l for l in G["tl"]["lines"] if l.get("place") == n and abs(max(0.0, l["start"] - 0.45) - tc) < 0.01), {})
        G["tr_kind"][tc] = ln.get("tr") or fx.TRANSITIONS[k % len(fx.TRANSITIONS)]
        k += 1


def transition_at(t, half=0.4):
    prev = G["start_place"]
    for tc, n in G["place_changes"]:
        if tc - half <= t < tc + half and n != prev:
            return prev, n, smooth((t - (tc - half)) / (2 * half)), G.get("tr_kind", {}).get(tc, "iris")
        if t >= tc:
            prev = n
    return None


def set_place(name):
    pl = G["places"][name]
    for w in WHO:
        G["cast"][w]["x"] = G["cast"][w]["spot"] = pl["spots"][w]
        G["cast"][w]["floor"] = pl["floor"]
    G["bg"] = pl["bg"]
    G["scene"] = pl.get("scene")


# ------------------------------------------------------------------ poses
REST = {"u_sl": 0.0, "l_sl": 0.0, "u_sr": 0.0, "l_sr": 0.0, "head": 0.0, "hop": 0.0, "sx": 1.0, "sy": 1.0, "bob": 0.0,
        "spin": 0.0, "dx": 0.0, "sway": 0.0,
        # legs: hip swing / knee bend in 'outward' degrees, lift = knee toward camera (0..1), squat 0..1, lean deg (+ = to screen right)
        "h_sl": 0.0, "k_sl": 0.0, "f_sl": 0.0, "h_sr": 0.0, "k_sr": 0.0, "f_sr": 0.0, "squat": 0.0, "lean": 0.0}
LEGS = ("h_sl", "k_sl", "f_sl", "h_sr", "k_sr", "f_sr", "squat")


def outer_side(who):
    """The arm on the side away from the rest of the cast (never crosses a neighbour)."""
    xs = [G["cast"][w]["x"] for w in WHO if w != who]
    return "sr" if G["cast"][who]["x"] >= sum(xs) / len(xs) else "sl"


def inner_side(who):
    return "sl" if outer_side(who) == "sr" else "sr"


def arm(side, upper, lower):
    """Angles in 'outward/up' terms; sl (screen-left) outward is clockwise, so its sign flips."""
    s = 1 if side == "sr" else -1
    return {f"u_{side}": s * upper, f"l_{side}": s * lower}


def leg(side, hip, knee=0.0, lift=0.0):
    s = 1 if side == "sr" else -1
    return {f"h_{side}": s * hip, f"k_{side}": s * knee, f"f_{side}": lift}


def hop_legs(lt, dur, n):
    """Legs through a hop: crouch before take-off, knees tucked in the air, a soft squat on landing."""
    per = max(0.42, dur / n)
    k = int(lt // per)
    if lt < 0 or k >= n:
        q = (lt - n * per) / 0.22 if lt >= 0 else 9
        return (0.45 * (1 - q) if 0 <= q < 1 else 0.0), 0.0
    p = (lt - k * per) / per
    if p < 0.18:
        return 0.55 * math.sin(math.pi * p / 0.18 * 0.5), 0.0           # crouch
    q = (p - 0.18) / 0.82
    tuck = 0.38 * math.sin(math.pi * q)
    land = 0.4 * max(0.0, (q - 0.86) / 0.14)
    return land, tuck


def gait(kind, ph):
    """One walking / running cycle at phase ph (radians): alternate knees up, arms swing, body bobs."""
    run = kind == "run"
    a = math.sin(ph)
    p = {}
    p.update(leg("sl", 4 * max(0, a), 0, (0.55 if run else 0.36) * max(0, a)))
    p.update(leg("sr", 4 * max(0, -a), 0, (0.55 if run else 0.36) * max(0, -a)))
    p.update(arm("sl", (30 if run else 14) + (22 if run else 12) * a, 60 if run else 18))
    p.update(arm("sr", (30 if run else 14) - (22 if run else 12) * a, 60 if run else 18))
    p["squat"] = (0.22 if run else 0.14) * (1 - abs(a))          # hips dip as the feet pass (feet stay on the floor)
    p["hop"] = 0.02 * abs(a) if run else 0.0
    p["head"] = 2.0 * a
    return p


def hops(lt, dur, n, height):
    """n hops spread over dur; returns (lift 0..1 * height, squash)."""
    per = max(0.42, dur / n)
    k = int(lt // per)
    if lt < 0:
        return 0.0, 1.0, 1.0
    if k >= n:                                    # the last landing squashes too, then springs back
        q = (lt - n * per) / 0.18
        if q >= 1:
            return 0.0, 1.0, 1.0
        return 0.0, 1.0 + 0.08 * math.sin(math.pi * q), 1.0 - 0.13 * math.sin(math.pi * q)
    p = (lt - k * per) / per
    air = 0.18
    if p < air:                                   # crouch (landing of the hop before, take-off of this one)
        q = p / air
        return 0.0, 1.0 + 0.09 * math.sin(math.pi * q), 1.0 - 0.14 * math.sin(math.pi * q)
    q = (p - air) / (1 - air)
    lift = 4 * q * (1 - q) * height
    st = 1.0 + 0.09 * math.sin(math.pi * q) * (1 - q) * 1.6   # stretched going up, round again at the top
    return lift, 1.0 / st ** 0.5, st


def beat_phase(t):
    """Seconds since the last song beat (big number when no song)."""
    b = G["beats"]
    import bisect
    i = bisect.bisect_right(b, t) - 1
    return t - b[i] if i >= 0 else 99.0


def act_pose(who, act, lt, dur, speaking, t=0.0):
    p = {}
    c = G["cast"][who]
    if act == "wave":
        p.update(arm(outer_side(who), 72, 88 + 20 * math.sin(2 * math.pi * 2.6 * lt)))
        p["head"] = 3 * math.sin(2 * math.pi * 0.9 * lt)
    elif act in ("cheer", "jump"):
        p.update(arm("sl", 128, 28))
        p.update(arm("sr", 128, 28))
        n = 1 if act == "cheer" else max(1, round(dur / 0.62))
        hd = 0.6 if act == "cheer" else max(dur, 0.6)
        lift, sx, sy = hops(lt - 0.05, hd, n, c["hop"])
        sq, tuck = hop_legs(lt - 0.05, hd, n)
        p.update({"hop": lift, "sx": sx, "sy": sy, "squat": sq})
        p.update(leg("sl", 6 * tuck / 0.38, 0, tuck)); p.update(leg("sr", 6 * tuck / 0.38, 0, tuck))
    elif act == "open":
        e = 6 * math.sin(2 * math.pi * 0.8 * lt)
        p.update(arm("sl", 38 + e, 42))
        p.update(arm("sr", 38 - e, 42))
    elif act == "point":
        p.update(arm(inner_side(who), 78, 6))
        p.update(arm(outer_side(who), 14, 20))
    elif act == "count":
        p.update(arm(outer_side(who), 30, 110 + 8 * math.sin(2 * math.pi * 2 * lt)))
        p["head"] = 4 * math.sin(math.pi * min(lt / 0.5, 1))
    elif act in ("clap", "beatclap"):
        if act == "beatclap":
            ph = beat_phase(t)
            closed = ph < 0.16
            p["bob"] = 7 * max(0.0, 1 - ph / 0.25)
        else:
            closed = (math.sin(2 * math.pi * 2.4 * lt) > 0)
            p["bob"] = 6 * abs(math.sin(2 * math.pi * 2.4 * lt))
        inward = -128 if closed else -88
        p.update(arm("sl", 38, inward))
        p.update(arm("sr", 38, inward))
    elif act in ("giggle", "laugh"):
        p.update(arm("sl", 10, -135))
        p.update(arm("sr", 10, -135))
        f = 3.2 if act == "giggle" else 4.0
        p["head"] = 6 * math.sin(2 * math.pi * f * lt)
        p["bob"] = (8 if act == "giggle" else 12) * abs(math.sin(2 * math.pi * f * lt))
    elif act == "tumble":                          # rolls in from the side, spins, lands with a squash
        q = min(lt / 0.75, 1.0)
        p["dx"] = (1 - smooth(q)) * 0.9 * (1 if outer_side(who) == "sr" else -1)
        p["spin"] = -360 * smooth(q) * (1 if outer_side(who) == "sr" else -1)
        p["hop"] = 4 * q * (1 - q) * 0.35 if q < 1 else 0.0
        if 0.75 <= lt < 1.05:
            k = (lt - 0.75) / 0.3
            p["sy"], p["sx"] = 1 - 0.18 * math.sin(math.pi * k), 1 + 0.12 * math.sin(math.pi * k)
            p["squat"] = 0.6 * math.sin(math.pi * k)
        p.update(arm("sl", 120, 30))
        p.update(arm("sr", 120, 30))
        if lt > 1.05:
            p["sway"] = 6 * math.sin(2 * math.pi * 2.5 * (lt - 1.05)) * max(0.0, 1 - (lt - 1.05) / 1.2)
    elif act == "sneeze":                          # a-a-a ... CHOO
        wind = min(lt / max(dur * 0.7, 0.3), 1.0)
        if lt < dur * 0.7:
            p["head"] = 10 * smooth(wind) * (1 if outer_side(who) == "sl" else -1)
            p["sy"] = 1 + 0.05 * smooth(wind)
            p.update(arm("sl", 30 * wind, 40 * wind))
            p.update(arm("sr", 30 * wind, 40 * wind))
        else:
            k = min((lt - dur * 0.7) / 0.25, 1.0)
            p["head"] = -12 * (1 - k) * (1 if outer_side(who) == "sl" else -1)
            p["sy"], p["sx"] = 1 - 0.12 * (1 - k), 1 + 0.08 * (1 - k)
            p["bob"] = 14 * (1 - k)
    elif act == "wobble":
        p["sway"] = 7 * math.sin(2 * math.pi * 3.0 * lt)
        p.update(leg("sl", 8 + 6 * math.sin(2 * math.pi * 3 * lt), -10)); p.update(leg("sr", 8 - 6 * math.sin(2 * math.pi * 3 * lt), -10))
        p.update(arm("sl", 60 + 15 * math.sin(2 * math.pi * 3 * lt), 20))
        p.update(arm("sr", 60 - 15 * math.sin(2 * math.pi * 3 * lt), 20))
    elif act == "march":
        ph = 2 * math.pi * 1.8 * lt
        p["hop"] = 0.03 * abs(math.sin(ph))
        p.update(arm("sl", 25 + 20 * math.sin(ph), 30))
        p.update(arm("sr", 25 - 20 * math.sin(ph), 30))
        p["head"] = 2 * math.sin(ph)
        p.update(leg("sl", 0, 0, 0.45 * max(0, math.sin(ph)))); p.update(leg("sr", 0, 0, 0.45 * max(0, -math.sin(ph))))
    elif act in ("walk", "run"):                     # walking / running on the spot (a "go"/"run" line moves them)
        p.update(gait(act, 2 * math.pi * (1.9 if act == "walk" else 3.0) * lt))
    elif act == "bounce":                            # trampoline / bouncy-castle bounces: high, arms swing up, knees tuck
        n = max(1, round(dur / 0.75))
        per = max(0.6, dur / n)
        lift, sx, sy = hops(lt, n * per, n, 0.21)
        sq, tuck = hop_legs(lt, n * per, n)
        u = (lt % per) / per
        p.update({"hop": lift, "sx": sx, "sy": sy, "squat": sq})
        p.update(leg("sl", 8 * tuck / 0.38, 0, tuck)); p.update(leg("sr", 8 * tuck / 0.38, 0, tuck))
        up = 150 * math.sin(math.pi * min(u / 0.6, 1)) if lt < n * per else 0
        p.update(arm("sl", 20 + up * 0.8, 20)); p.update(arm("sr", 20 + up * 0.8, 20))
        if int(lt // per) == n - 1 and n >= 3:          # the last bounce of a long run gets a spin
            p["spin"] = 360 * smooth(min(max((u - 0.2) / 0.55, 0), 1)) * (1 if WHO.index(who) % 2 else -1)
    elif act == "frog":                              # deep squat, big leap with legs out, squat landing
        cyc = 1.5
        u = (lt % cyc) / cyc
        if u < 0.4:
            p["squat"] = 0.95 * smooth(u / 0.25)
            p.update(arm("sl", 10, -20)); p.update(arm("sr", 10, -20))
        else:
            v = (u - 0.4) / 0.6
            p["hop"] = 4 * v * (1 - v) * 0.24
            p.update(leg("sl", 28 * math.sin(math.pi * v), -20 * math.sin(math.pi * v)))
            p.update(leg("sr", 28 * math.sin(math.pi * v), -20 * math.sin(math.pi * v)))
            p.update(arm("sl", 110 * math.sin(math.pi * v), 20)); p.update(arm("sr", 110 * math.sin(math.pi * v), 20))
            p["squat"] = 0.6 * max(0.0, (v - 0.85) / 0.15)
    elif act == "kangaroo":                          # big bounding hops, paws tucked in front
        n = max(1, round(dur / 0.6))
        lift, sx, sy = hops(lt, max(dur, 0.6), n, 0.22)
        sq, tuck = hop_legs(lt, max(dur, 0.6), n)
        p.update({"hop": lift, "sx": sx, "sy": sy, "squat": sq})
        p.update(leg("sl", 0, 0, tuck * 0.6)); p.update(leg("sr", 0, 0, tuck * 0.6))
        p.update(arm("sl", 45, -115)); p.update(arm("sr", 45, -115))
    elif act == "bunny":                             # quick little hops, hands up as bunny ears
        n = max(1, round(dur / 0.42))
        lift, sx, sy = hops(lt, max(dur, 0.42), n, 0.07)
        sq, _ = hop_legs(lt, max(dur, 0.42), n)
        p.update({"hop": lift, "sx": sx, "sy": sy, "squat": sq * 0.5})
        p.update(arm("sl", 165, 25 + 10 * math.sin(2 * math.pi * 4 * lt))); p.update(arm("sr", 165, 25 - 10 * math.sin(2 * math.pi * 4 * lt)))
    elif act == "spin":                              # turn all the way round
        p["spin"] = 360 * smooth(min(lt / 0.9, 1)) * (1 if WHO.index(who) % 2 else -1)
        p.update(arm("sl", 80, 10)); p.update(arm("sr", 80, 10))
    elif act == "hands_up":
        p.update(arm("sl", 165, 10)); p.update(arm("sr", 165, 10))
        p["head"] = 3 * math.sin(2 * math.pi * 0.8 * lt)
    elif act == "touch_head":
        p.update(arm("sl", 150, 105)); p.update(arm("sr", 150, 105))
    elif act == "touch_toes":
        q = smooth(min(lt / 0.4, 1))
        p["squat"] = 0.8 * q
        p.update(arm("sl", 8 * q, -25 * q)); p.update(arm("sr", 8 * q, -25 * q))
        p["head"] = 0
    elif act == "catch":
        p.update(arm("sl", 55, 45)); p.update(arm("sr", 55, 45))
    elif act == "thumbs_up":                         # "good job!": forearm up, thumb up
        p.update(arm(outer_side(who), 30, 100 + 4 * math.sin(2 * math.pi * 1.5 * lt)))
        p["head"] = 4
    elif act == "yay":                               # fist pumps
        ph = abs(math.sin(2 * math.pi * 1.6 * lt))
        p.update(arm("sl", 120 + 30 * ph, 40)); p.update(arm("sr", 120 + 30 * ph, 40))
        p["bob"] = 6 * ph
    elif act == "squat":                             # crouch down low ("small like a mouse!") and pop back up
        q = smooth(min(lt / 0.35, 1)) * (1 - smooth((lt - dur + 0.1) / 0.3))
        p["squat"] = 0.9 * q
        p.update(arm("sl", 20 * q, 40 * q)); p.update(arm("sr", 20 * q, 40 * q))
    elif act == "stomp":                             # big stomps, left - right
        ph = 2 * math.pi * 1.6 * lt
        p.update(leg("sl", 8 * max(0, math.sin(ph)), 0, 0.6 * max(0, math.sin(ph))))
        p.update(leg("sr", 8 * max(0, -math.sin(ph)), 0, 0.6 * max(0, -math.sin(ph))))
        p["bob"] = -6 * abs(math.sin(ph)); p["squat"] = 0.25 * (1 - abs(math.sin(ph)))
        p.update(arm("sl", 40, 70)); p.update(arm("sr", 40, 70))
    elif act == "kick":                              # wind up, kick out to the side (toward the ball), back down
        side = inner_side(who)
        q = math.sin(math.pi * min(max((lt - 0.15) / 0.55, 0), 1))
        wind = 0.3 * math.sin(math.pi * min(lt / 0.15, 1)) if lt < 0.15 else 0.0
        p.update(leg(side, 34 * q - 6 * wind, -18 * q, 0.25 * q + wind))
        p["lean"] = (-6 if side == "sr" else 6) * q
        p.update(arm(side, 25 * q, 30)); p.update(arm("sl" if side == "sr" else "sr", 45 * q, 40))
    elif act in ("dance", "freeze"):
        tt = 0.21 if act == "freeze" else lt
        ph = 2 * math.pi * 1.3 * tt
        p["sway"] = 6 * math.sin(ph)
        p["bob"] = 10 * abs(math.sin(ph))
        p.update(arm("sl", 100 + 30 * math.sin(ph), 30))
        p.update(arm("sr", 100 - 30 * math.sin(ph), 30))
        p["head"] = 5 * math.sin(ph)
        p["squat"] = 0.22 * abs(math.sin(ph))          # knees bounce with the beat
        p.update(leg("sl", 10 * max(0, math.sin(ph)), 0, 0.2 * max(0, math.sin(ph))))
        p.update(leg("sr", 10 * max(0, -math.sin(ph)), 0, 0.2 * max(0, -math.sin(ph))))
        p["lean"] = 4 * math.sin(ph)
    elif act in ("silly", "shrug"):
        p.update(arm("sl", 32, 75))
        p.update(arm("sr", 32, 75))
        p["head"] = 8 * math.sin(math.pi * min(lt / 0.4, 1)) * (1 if outer_side(who) == "sr" else -1)
    elif act == "think":
        p.update(arm(inner_side(who), 12, -150))
        p["head"] = 5
    elif act == "give":
        p.update(arm(inner_side(who), 70, 10))
    else:                                         # talk: a small presenting hand that moves with the words
        side = outer_side(who)
        p.update(arm(side, 18 + 6 * math.sin(2 * math.pi * 0.7 * lt), 34 + 10 * math.sin(2 * math.pi * 1.1 * lt)))
    if speaking and "head" not in p:
        p["head"] = 2.2 * math.sin(2 * math.pi * 1.25 * lt)
    return p


ADDITIVE = ("sway", "spin", "dx")


def pose_at(who, t):
    base = dict(REST)
    for h in G["holds"]:                            # holding a prop: that hand comes up in front
        if h["who"] == who and h["t0"] <= t < h["t1"]:
            base.update(arm(G["cast"][who]["hold_side"], 22, 70))
    out = dict(base)
    acc, wsum = {}, {}                              # overlapping acts are blended (weighted mean), never added up:
    for (t0, t1, act, speaking) in G["acts"][who]:  # two dance lines in a row used to double the arm swing (arms broke)
        if t < t0 - 0.3 or t > t1 + 1.6:
            continue
        w = smooth((t - (t0 - 0.25)) / 0.25) * (1 - smooth((t - (t1 + 0.15)) / 0.3))
        if act in ("tumble", "sneeze"):              # these run their own clock past the line end
            w = 1.0 if t0 - 0.05 <= t <= t1 + 1.4 else 0.0
        w_hop = 1.0 if act in ("cheer", "jump", "tumble") else w
        if w <= 0 and w_hop <= 0:
            continue
        p = act_pose(who, act, t - t0, t1 - t0, speaking, t)
        for k, v in p.items():
            ww = w_hop if k in ("hop", "sx", "sy", "dx", "spin") or (k in LEGS and act in ("cheer", "jump", "tumble")) else w
            if ww <= 0:
                continue
            acc[k] = acc.get(k, 0.0) + (v - base[k]) * ww
            wsum[k] = wsum.get(k, 0.0) + ww
    for k, d in acc.items():
        out[k] = base[k] + d / max(1.0, wsum[k])
    # the holding arm stays on its prop whatever the act does (a laugh/clap pose used to pull a balloon over the face);
    # a balloon is held out to the side so it floats beside the head, not in front of it
    for h in G["holds"]:
        if h["who"] == who and h["t0"] <= t < h["t1"]:
            ball = h["pic"].startswith("balloon")
            q = smooth((t - h["t0"]) / 0.35)
            for k, v in arm(G["cast"][who]["hold_side"], 38 if ball else 22, 40 if ball else 70).items():
                out[k] = out[k] + (v - out[k]) * q
    gm = G.get("games") or {}
    for b in gm.get("ball", []):
        side = G["cast"][who]["hold_side"]
        if b["kind"] == "dribble" and b["who"] == who and b["t0"] - 0.2 <= t <= b["t1"] + 0.2:
            u = ((t - b["t0"]) % b["per"]) / b["per"]
            out.update(arm(side, 24, 46 + 30 * math.cos(2 * math.pi * u)))
            out["squat"] = max(out["squat"], 0.18)
        if b["kind"] == "throw":
            if b["from"] == who and b["t0"] - 0.35 <= t <= b["t0"] + 0.25:      # wind up high, release forward
                q = (t - (b["t0"] - 0.35)) / 0.6
                out.update(arm(side, 140 - 90 * smooth(q), 20 + 30 * smooth(q)))
                out["lean"] += (5 if G["cast"][b["to"]]["x"] > G["cast"][who]["x"] else -5) * math.sin(math.pi * q)
            if b["to"] == who and b["t1"] - 0.6 <= t <= b["t1"] + 0.15:          # ready to catch
                q = smooth((t - (b["t1"] - 0.6)) / 0.3)
                for sd in ("sl", "sr"):
                    for k, v in arm(sd, 55, 45).items():
                        out[k] = out[k] + (v - out[k]) * q
    for hd in gm.get("hide", []):
        if hd["who"] == who and hd["t0"] <= t <= hd["t1"]:
            q = smooth((t - hd["t0"]) / 0.4) * (1 - smooth((t - hd["t1"] + 0.3) / 0.3))
            u = ((t - hd["t0"]) % 2.6) / 2.6
            peek = math.sin(math.pi * min(max((u - 0.55) / 0.35, 0), 1))
            out["squat"] = out["squat"] + (0.95 - out["squat"]) * q
            out["hop"] = out["hop"] + 0.07 * peek * q
            out["head"] += 8 * peek * q
            out.update(arm("sl", 10 * q, -30 * q)); out.update(arm("sr", 10 * q, -30 * q))
    for tu in gm.get("turn", []):
        if tu["t0"] <= t <= tu["t1"]:                   # waiting for the child: face the camera, an encouraging lean in
            q = smooth((t - tu["t0"]) / 0.3) * (1 - smooth((t - tu["t1"] + 0.2) / 0.2))
            out["head"] *= 1 - q
            out["squat"] = max(out["squat"], 0.12 * q)
    # listening: lean the head toward whoever speaks
    spk = next((ln["who"] for ln in G["tl"]["lines"] if ln["start"] - 0.1 <= t <= ln["end"] + 0.2), None)
    if spk and spk != who and who not in next((speakers(ln) for ln in G["tl"]["lines"] if ln["start"] - 0.1 <= t <= ln["end"] + 0.2), []):
        sign = 1 if (G["cast"][spk]["x"] > G["cast"][who]["x"]) else -1
        out["head"] += sign * -abs(G["cast"][who]["listen"])
    # walking / running between spots: the gait follows the distance covered, so feet never skate
    mv = moving(who, t)
    if mv:
        kind, dist, direction, q = mv
        stride = (0.10 if kind == "walk" else 0.16) * G["cast"][who]["char_h"] * G["cast"][who]["k"]
        g = gait(kind, math.pi * dist / stride)
        for k, v in g.items():
            out[k] = out[k] + (v - REST[k]) * q
        out["lean"] += direction * (4 if kind == "walk" else 9) * q
    # idle: a slow weight shift from foot to foot (one knee relaxes), so nobody stands like a cut-out
    ws = math.sin(2 * math.pi * t / 6.3 + 2.1 * WHO.index(who))
    out["lean"] += 1.1 * ws
    rs = "sl" if ws > 0 else "sr"
    out.update({f"k_{rs}": out[f"k_{rs}"] + (1 if rs == "sr" else -1) * -5 * abs(ws)})
    # idle breathing
    ph = 1.3 * WHO.index(who)
    out["sy"] *= 1.0 + 0.006 * math.sin(2 * math.pi * t / 3.2 + ph)
    out["sway"] += 0.8 * math.sin(2 * math.pi * t / 4.1 + ph)
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


FACE_OF_ACT = {"cheer": "happy", "laugh": "happy", "giggle": "happy", "jump": "happy", "bounce": "happy", "dance": "happy",
               "clap": "happy", "beatclap": "happy", "wave": "happy", "silly": "happy", "bunny": "happy", "kangaroo": "happy",
               "frog": "happy", "march": "happy", "spin": "happy", "tumble": "surprised", "catch": "surprised", "think": "think",
               "wobble": "surprised"}


def face_at(who, t):
    """Expression and eye look (lx, ly in -1..1, quantised) at t."""
    expr = None
    cur = None
    for ln in G["tl"]["lines"]:
        if ln["start"] - 0.1 <= t <= ln["end"] + 0.3:
            cur = ln
            f = ln.get("face")
            if isinstance(f, dict) and who in f:
                expr = f[who]
            elif isinstance(f, str) and who in speakers(ln):
                expr = f
            if expr is None:
                a = ln.get("act") if who in speakers(ln) else (ln.get("also") or {}).get(who)
                expr = FACE_OF_ACT.get(a)
            break
    # where the eyes look: at the ball in play, else at whoever talks, else at the camera
    lx, ly = 0.0, 0.0
    me = G["cast"][who]["x"]
    for b in (G.get("games") or {}).get("ball", []):
        if b["t0"] <= t <= b["t1"] and who not in (b.get("from"), b.get("who")):
            tgt = b.get("to") if isinstance(b.get("to"), str) else None
            src = b.get("from") or b.get("who")
            q = (t - b["t0"]) / (b["t1"] - b["t0"])
            bx = G["cast"][src]["x"] + ((G["cast"][tgt]["x"] if tgt else me) - G["cast"][src]["x"]) * q
            lx = max(-1.0, min(1.0, (bx - me) / 300))
            break
    else:
        if cur and who not in speakers(cur):
            spk = cur["who"]
            lx = 1.0 if G["cast"][spk]["x"] > me else -1.0
    if any(tu["t0"] <= t <= tu["t1"] for tu in (G.get("games") or {}).get("turn", [])):
        lx = 0.0                                       # your turn: everybody looks at the child
    if expr == "think":
        lx, ly = (0.6 if lx >= 0 else -0.6), -1.0
    return expr, round(lx * 2) / 2, round(ly * 2) / 2


@lru_cache(maxsize=12)
def sclera(who):
    """The white of the eye (None when the picture's eyes have no white: then the eyes don't move)."""
    c = G["cast"][who]
    rig = c["rig"]
    src = np.asarray(Image.open(ROOT / G["story"]["cast"][who]["dir"] / "source.png").convert("RGB")).astype(int)
    vals = []
    for cx, cy, rx, ry in rig["eyes"]:
        for a in np.linspace(0, 2 * math.pi, 48, endpoint=False):
            x, y = int(cx + 0.78 * rx * math.cos(a)), int(cy + 0.78 * ry * math.sin(a))
            px = src[y, x]
            if px.min() > 205:
                vals.append(px)
    return tuple(int(v) for v in np.median(vals, 0)) if len(vals) >= 6 else None


@lru_cache(maxsize=256)
def face_head(who, shape, blink_q, expr=None, lx=0.0, ly=0.0):
    c = G["cast"][who]
    rig = c["rig"]
    head = c["parts"]["head"].copy()
    ox, oy = rig["parts"]["head"]["offset"]
    skin, line = tuple(rig["skin"]), tuple(rig["line"])
    W, H = head.size
    big = head.resize((W * SS, H * SS), Image.BICUBIC)
    d = ImageDraw.Draw(big)
    lid = tuple(rig.get("lid", skin))
    wh = sclera(who)
    for cx, cy, rx, ry in rig["eyes"]:
        cx, cy, rx, ry = (cx - ox) * SS, (cy - oy) * SS, rx * SS, ry * SS
        if (lx or ly) and wh and blink_q < 0.99:         # look: the iris slides inside the eye; the eye outline stays put
            r = 0.62 * min(rx, ry)
            box = (int(cx - r), int(cy - r), int(cx + r), int(cy + r))
            iris = big.crop(box)
            m_in = Image.new("L", big.size, 0)
            ImageDraw.Draw(m_in).ellipse([cx - rx * 0.8, cy - ry * 0.8, cx + rx * 0.8, cy + ry * 0.8], fill=255)
            layer = Image.new("RGBA", big.size, wh + (255,))
            cm = Image.new("L", iris.size, 0)
            ImageDraw.Draw(cm).ellipse([0, 0, iris.width - 1, iris.height - 1], fill=255)
            layer.paste(iris, (int(box[0] + lx * rx * 0.24), int(box[1] + ly * ry * 0.2)), cm)
            big.paste(layer, (0, 0), m_in)
        lw = max(2, int(rx * 0.16))
        if expr == "happy" and blink_q < 0.5:            # smiling eyes: the lower lids push up in a curve
            m = Image.new("L", big.size, 0)
            ImageDraw.Draw(m).ellipse([cx - rx * 1.15, cy + ry * 0.35, cx + rx * 1.15, cy + ry * 2.2], fill=255)
            em = Image.new("L", big.size, 0)
            ImageDraw.Draw(em).ellipse([cx - rx * 1.05, cy - ry * 1.05, cx + rx * 1.05, cy + ry * 1.12], fill=255)
            big.paste(lid + (255,), (0, 0), Image.fromarray(np.minimum(np.asarray(m), np.asarray(em))))
            d.arc([cx - rx * 1.15, cy + ry * 0.35, cx + rx * 1.15, cy + ry * 2.2], 200, 340, fill=line + (255,), width=lw)
        elif expr == "sad" and blink_q < 0.5:            # worried: the outer top of each eye droops
            outer = 1 if cx > (rig["mouth"]["c"][0] - ox) * SS else -1
            tri = [(cx - outer * rx * 0.3, cy - ry * 1.15), (cx + outer * rx * 1.2, cy - ry * 1.15), (cx + outer * rx * 1.2, cy + ry * 0.05)]
            m = Image.new("L", big.size, 0)
            ImageDraw.Draw(m).polygon(tri, fill=255)
            em = Image.new("L", big.size, 0)
            ImageDraw.Draw(em).ellipse([cx - rx * 1.08, cy - ry * 1.08, cx + rx * 1.08, cy + ry * 1.08], fill=255)
            big.paste(lid + (255,), (0, 0), Image.fromarray(np.minimum(np.asarray(m), np.asarray(em))))
            d.line([(cx - outer * rx * 0.3, cy - ry * 1.0), (cx + outer * rx * 1.05, cy + ry * 0.05)], fill=line + (255,), width=lw)
        elif expr == "surprised" and blink_q < 0.5:      # wide eyes: the whole eye grows a little
            e = big.crop((int(cx - rx * 1.2), int(cy - ry * 1.2), int(cx + rx * 1.2), int(cy + ry * 1.2)))
            e2 = e.resize((int(e.width * 1.16), int(e.height * 1.16)), Image.BICUBIC)
            mk = Image.new("L", e2.size, 0)
            ImageDraw.Draw(mk).ellipse([e2.width * 0.08, e2.height * 0.08, e2.width * 0.92, e2.height * 0.92], fill=255)
            mk = mk.filter(ImageFilter.GaussianBlur(3 * SS))
            big.paste(e2, (int(cx - e2.width / 2), int(cy - e2.height / 2)), mk)
    if shape not in MOUTHS and expr in ("surprised", "sad", "think"):   # a mouth for the feeling when not talking
        mo = rig["mouth"]
        mx, my = (mo["c"][0] - ox) * SS, (mo["c"][1] - oy) * SS
        mw, mh = mo["w"] * SS, mo["h"] * SS
        lw = max(2, int(mw * 0.06))
        d.ellipse([mx - mw * 0.62, my - mh * 0.9, mx + mw * 0.62, my + mh * 0.9], fill=skin + (255,))
        if expr == "surprised":
            d.ellipse([mx - mw * 0.17, my - mh * 0.55, mx + mw * 0.17, my + mh * 0.9], fill=(110, 30, 40, 255), outline=line + (255,), width=lw)
        elif expr == "sad":
            d.arc([mx - mw * 0.3, my, mx + mw * 0.3, my + mh * 1.4], 200, 340, fill=line + (255,), width=lw)
        else:
            d.line([(mx - mw * 0.2, my + mh * 0.1), (mx + mw * 0.22, my - mh * 0.12)], fill=line + (255,), width=lw)
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
            big.paste(tuple(rig.get("lid", skin)) + (255,), (0, 0), m)
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
    return big.reduce(SS) if big.size == (W * SS, H * SS) else big.resize((W, H), Image.LANCZOS)


# ------------------------------------------------------------------ drawing
def shrunk(img, f):
    """LANCZOS copy of img at scale f. Stored on the image object itself, so a copy can never be handed to another
    picture (keying by id() did exactly that once a freed mouth image's id was reused)."""
    cache = getattr(img, "_shrunk", None)
    if cache is None:
        cache = img._shrunk = {}
    im = cache.get(f)
    if im is None:
        if len(cache) > 40:
            cache.clear()
        im = cache[f] = img.resize((max(1, int(img.width * f)), max(1, int(img.height * f))), Image.LANCZOS)
    return im


def draw_shadows(frame, ovals, blur=6):
    """Soft floor shadows, blurred only inside a padded box around the ovals (same pixels as blurring a full-frame
    layer: everything outside the box is empty, and the box is padded past the frame edge like the full layer)."""
    vis = [o for o in ovals if o[2] > 0 and o[0] < OUT_W and o[3] > 0 and o[1] < OUT_H]
    if not vis:
        return
    pad = blur * 4
    bx0 = max(0, int(min(o[0] for o in vis)) - pad)
    by0 = max(0, int(min(o[1] for o in vis)) - pad)
    bx1 = min(OUT_W, int(max(o[2] for o in vis)) + pad + 1)
    by1 = min(OUT_H, int(max(o[3] for o in vis)) + pad + 1)
    layer = Image.new("RGBA", (bx1 - bx0, by1 - by0), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for o in vis:
        d.ellipse([o[0] - bx0, o[1] - by0, o[2] - bx0, o[3] - by0], fill=(40, 20, 40, 70))
    frame.alpha_composite(layer.filter(ImageFilter.GaussianBlur(blur)), (bx0, by0))


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
        f = round(max(sc * 1.4, 0.05) * 50) / 50   # 2 % steps: one cached copy serves a whole slow push-in
        src = shrunk(img, f)
        Mi = np.diag([src.width / w, src.height / h, 1.0]) @ Mi     # the exact scale is still applied by the transform
    data = (Mi[0, 0], Mi[0, 1], Mi[0, 2], Mi[1, 0], Mi[1, 1], Mi[1, 2])
    pm = getattr(src, "_premul", None)             # premultiplied copy, made once per picture (same pixels every time)
    if pm is None:
        pm = src._premul = src.convert("RGBa")
    out = pm.transform((x1c - x0c, y1c - y0c), Image.AFFINE, data, resample=Image.BICUBIC).convert("RGBA")
    canvas.alpha_composite(out, (x0c, y0c))
    del inv


def cam_rect(t, start=False):
    """The camera at t (start=True: the same shot at its first frame, the depth reference). With living scenery every
    shot drifts a little sideways while it pushes in (direction alternates shot to shot), and the first wide shot in a new
    place glides across it, so the place's depth shows."""
    shots = G["shots"]
    k = max(i for i, s_ in enumerate(shots) if s_[0] <= t)
    t0, name = shots[k]
    t1 = shots[k + 1][0] if k + 1 < len(shots) else G["tl"]["total"]
    prog = 0.0 if start else smooth((t - t0) / max(t1 - t0, 0.1))
    live = G.get("scene") is not None and G["story"].get("camera_life", True)
    dirn = 1 if k % 2 else -1
    drift = dirn * (2 * prog - 1) if live else 0.0
    c = G["cast"]
    if name == "group" and live and any(-0.2 <= t0 - tc <= 1.2 for tc, _ in G["place_changes"]):
        w = WORLD_W * (0.9 - 0.04 * prog)                 # arriving: a slow glide across the new place
        cx, cy = WORLD_W / 2 - drift * WORLD_W * 0.045, WORLD_H / 2 + 20
    elif name == "group":
        w = WORLD_W * ((0.95 - 0.05 * prog) if live else (1.0 - 0.06 * prog))
        cx, cy = WORLD_W / 2 + drift * WORLD_W * 0.018, WORLD_H / 2 + 20
    elif name == "host":
        h = c[HOST]
        w = h["char_h"] * h["k"] * 1.55 * (1.0 - 0.05 * prog)
        cx = h["x"] + w * 0.16                         # host left of centre: cards sit on the right
        cy = h["floor"] - h["char_h"] * h["k"] * 0.62
    elif name == "kids":
        kids = G["story"].get("kids", WHO[1:3])
        xs = [c[w]["x"] for w in kids]
        kx, span = sum(xs) / len(xs), max(xs) - min(xs)
        hh = max(c[w]["char_h"] * c[w]["k"] for w in kids)
        w = max(span * 2.3, hh * 1.95) * (1.0 - 0.05 * prog)
        cx = kx - w * 0.06                             # kids a little right of centre: room for cards on the left
        cy = c[kids[0]]["floor"] - hh * 0.56
    else:                                              # cu:<who>: waist-up close-up, a little off centre
        who = name.split(":", 1)[1]
        h = c[who]
        hp = h["char_h"] * h["k"]
        w = hp * 1.3 * (1.0 - 0.05 * prog)
        cx = h["x"] + w * 0.14 * (1 if outer_side(who) == "sl" else -1)
        cy = h["floor"] - hp * 0.68
        if tramp_for(who, t):                          # on the trampoline: lifted + bouncing, so frame wider and higher
            w = hp * 2.0 * (1.0 - 0.04 * prog)
            cy = h["floor"] - hp * 0.86
    if name != "group":
        cx += drift * w * 0.025
    h_ = w * OUT_H / OUT_W
    cx = min(max(cx, w / 2), WORLD_W - w / 2)
    cy = min(max(cy, h_ / 2), WORLD_H - h_ / 2)
    return cx - w / 2, cy - h_ / 2, w, name


@lru_cache(maxsize=64)
def card_img(text, size):
    colours = {"PINK": (255, 105, 180), "BLUE": (40, 120, 230), "RED": (230, 60, 60), "YELLOW": (250, 200, 20),
               "GREEN": (60, 180, 80), "PURPLE": (150, 80, 210), "ORANGE": (255, 140, 30)}
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


def card_spot(t, cam, size, width=None, taken=()):
    def ov(a, b):
        return max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
    boxes = char_boxes(t)
    pref = {"host": (1400, 420), "kids": (330, 400), "group": (960, 260)}.get(cam, (1450, 380) if cam.startswith("cu:") else (960, 300))
    best = None
    hw = (width or size * 1.2) / 2 + 12                # half the real card width, plus a margin from the frame edge
    for x in range(int(hw) + 20, OUT_W - int(hw) - 19, 40):
        for y in (220, 300, 380, 460):
            r = (x - hw, y - size / 2, x + hw, y + size / 2)
            sc = sum(3 * ov(r, h) + ov(r, b) for h, b in boxes) + 40 * math.hypot(x - pref[0], y - pref[1])
            sc += sum(8 * ov(r, tk) for tk in taken)          # never on top of another card / picture on screen
            if best is None or sc < best[0]:
                best = (sc, x, y)
    return best[1], best[2]


def draw_cards(frame, t, cam):
    taken = []
    for cd in sorted(G["cards"], key=lambda c: "pic" not in c):     # pictures first, word cards find the free space
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
        full = (G["pics"][cd["pic"]].width * 470 / G["pics"][cd["pic"]].height) if "pic" in cd else card_img(cd["text"], 260).width
        sz = 470 if "pic" in cd else 300
        cx, cy = card_spot(t, cam, sz, full * 1.18, tuple(taken))
        taken.append((cx - full * 0.6, cy - sz / 2, cx + full * 0.6, cy + sz / 2))
        frame.alpha_composite(im, (int(cx - im.width / 2), int(cy + bob - im.height / 2)))


LINE_W = 5.5                                    # outline thickness in source pixels (matches the art)


HAND_OF_ACT = {"wave": ("open", "outer"), "point": ("point", "inner"), "count": ("point", "outer"), "thumbs_up": ("thumb", "outer"),
               "yay": ("fist", "both"), "cheer": ("open", "both"), "jump": ("open", "both"), "hands_up": ("open", "both"),
               "bounce": ("open", "both"), "dance": ("open", "both"), "bunny": ("open", "both"), "frog": ("open", "both"),
               "open": ("open", "both"), "catch": ("open", "both")}


def hand_shape(who, side, t):
    """Which hand picture a side uses at t: None = the character's own relaxed hand."""
    if (who, "open", side) not in G.get("hs", {}):
        return None
    for h in G["holds"]:
        if h["who"] == who and h["t0"] <= t < h["t1"] and G["cast"][who]["hold_side"] == side:
            return None
    for ln in G["tl"]["lines"]:
        if ln["start"] - 0.1 <= t <= ln["end"] + 0.15:
            hd = (ln.get("hand") or {}).get(who)
            if isinstance(hd, dict):
                return hd.get(side)
            if isinstance(hd, str):
                return hd
            a = ln.get("act") if who in speakers(ln) else (ln.get("also") or {}).get(who)
            if a in HAND_OF_ACT:
                shp, which = HAND_OF_ACT[a]
                if which == "both" or side == (outer_side(who) if which == "outer" else inner_side(who)):
                    return shp
            return None
    return None


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
    cv = cv.reduce(K)                               # exact 2x box average (premultiplied): same look, much faster
    frame.alpha_composite(cv, (x0c, y0c))
    # the hand: a hand-shape picture (thumbs up, fist, point, open), or the character's own hand turned with the forearm
    shp = pz.get("_hs", {}).get(side) if isinstance(pz.get("_hs"), dict) else None
    if shp:
        hs = rig["hand_shapes"][shp][side]
        v = (pts[3] - pts[2]) / max(np.linalg.norm(pts[3] - pts[2]), 1e-6)
        ang = math.degrees(math.atan2(v[0], -v[1]))                 # forearm direction, clockwise from straight up
        if shp in ("thumb", "fist"):
            ang *= 0.25                                              # a thumbs-up / fist stays (almost) upright
        wq = pts[3] - v * fw * sc * 0.15
        Mh = T(*wq) @ R(-ang) @ np.diag([sc, sc, 1.0]) @ T(-hs["wrist"][0], -hs["wrist"][1])
        place(frame, G["hs"][(rig["_who"], shp, side)], Mh)
        return
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
        cv2_ = cv2_.reduce(2)
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
    cv = cv.reduce(K)                               # exact 2x box average (premultiplied): same look, much faster
    frame.alpha_composite(cv, (x0c, y0c))
    del saved


def crosses_body(pz, side):
    """Forearm folded inward (clap, giggle): it must be drawn in front of the body."""
    s = 1 if side == "sr" else -1
    return s * pz[f"l_{side}"] < -40


def motion(who, t, pz, dt=0.07):
    """How fast a character moves now: sideways and up (character heights per second) and turns (degrees per second)."""
    pp = pose_at(who, t - dt)
    vx = (x_at(who, t) - x_at(who, t - dt)) / (G["cast"][who]["char_h"] * G["cast"][who]["k"] * dt) + (pz["dx"] - pp["dx"]) / dt
    vy = (pz["hop"] - pp["hop"]) / dt
    vr = (pz["head"] + pz["sway"] + pz["lean"] - pp["head"] - pp["sway"] - pp["lean"]) / dt
    return vx, vy, vr


def side_amount(who, t):
    """0..1 how far a character has turned to its side view for a walk / run across the place (short steps stay
    facing front), the direction, and the move."""
    if "side" not in G["cast"][who]:
        return 0.0, 0, None
    for m in G["moves"].get(who, []):
        if m["place_t"] < G["cur_place_t"] or abs(m["x1"] - m["x0"]) < 0.06 * WORLD_W:
            continue
        if m["t0"] - 0.1 <= t <= m["t1"] + 0.25:
            u = min(smooth((t - m["t0"] + 0.1) / 0.22), 1 - smooth((t - m["t1"]) / 0.22))
            return u, (1 if m["x1"] > m["x0"] else -1), m
    return 0.0, 0, None


def draw_side(frame, C, who, t, sxf, dirn, m):
    """The profile walk: legs swing from the hip (far leg darker, behind), the body dips as a leg reaches out, leans in."""
    c = G["cast"][who]
    sd, info = c["side"], c["side"]["info"]
    run = m["kind"] == "run"
    stride = (0.10 if not run else 0.16) * c["char_h"] * c["k"]
    dist = abs(x_at(who, min(max(t, m["t0"]), m["t1"])) - m["x0"])
    ph = math.pi * dist / stride
    th = (34 if run else 24) * math.sin(ph)
    drop = info["leg_len"] * (1 - math.cos(math.radians(abs(th)))) - (0.02 * info["height"] * abs(math.cos(ph)) if run else 0)
    fx_, fy_ = info["feet"]
    hip = info["hip"]
    M = (C @ T(c["x"], c["floor"]) @ S(sd["k"] * sxf * dirn, sd["k"]) @ about((fx_, fy_), R(-(7 if run else 3)))
         @ T(-fx_, -fy_ + drop))
    lo = T(*info["leg_offset"])
    place(frame, sd["far"], M @ about(hip, R(-th)) @ lo)
    place(frame, sd["leg"], M @ about(hip, R(th)) @ lo)
    place(frame, sd["upper"], M)
    hp = M @ [hip[0] + 0.12 * info["height"] * 0.3, hip[1] - 0.05 * info["height"], 1]
    return hp[:2]


def char_matrix(who, pose):
    c = G["cast"][who]
    rig = c["rig"]
    f = rig["feet"]
    k = c["k"]
    mid = (f[0], f[1] - c["char_h"] * 0.5)
    root = (T(c["x"] + pose.get("dx", 0) * c["char_h"] * k, c["floor"] - pose["hop"] * c["char_h"] * k - pose["bob"]) @ S(k)
            @ R(pose.get("sway", 0)) @ S(pose["sx"], pose["sy"]) @ T(-f[0], -f[1]) @ about(mid, R(pose.get("spin", 0))))
    if c["flip"]:
        root = root @ about(f, S(-1, 1))
    return root


def draw_prop(frame, pic, x, y, height, t, balloon):
    base = G["pics"][pic]
    h = max(8, int(height))
    im = base.resize((max(1, int(base.width * h / base.height)), h), Image.LANCZOS)
    if balloon:                                       # string end in the hand, balloon floats above and bobs
        rot = 4 * math.sin(2 * math.pi * 0.7 * t)
        im = im.rotate(rot, resample=Image.BICUBIC, expand=True, center=(im.width / 2, im.height))
        frame.alpha_composite(im, (int(x - im.width / 2), int(y - im.height + 4)))
    else:
        frame.alpha_composite(im, (int(x - im.width / 2), int(y - im.height * 0.6)))


@lru_cache(maxsize=16)
def title_img(text, kind, letters=True):
    font = ImageFont.truetype(FONT, 104 if kind == "title" else 88)
    lines = text.split("\n")
    cols = [(255, 90, 90), (255, 165, 40), (60, 170, 90), (60, 140, 240), (170, 90, 230)]
    W = max(font.getbbox(l)[2] for l in lines) + 160
    H = 150 * len(lines) + 90
    im = Image.new("RGBA", (W + 30, H + 30), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([18, 24, W + 18, H + 24], radius=70, fill=(0, 0, 0, 70))
    d.rounded_rectangle([8, 8, W + 8, H + 8], radius=70, fill=(255, 255, 255, 255))
    d.rounded_rectangle([22, 22, W - 6, H - 6], radius=58, fill=(255, 246, 214, 255))
    y = 45 + 75
    k = 0
    for ln in lines:                                   # rainbow letters
        x = (W + 16 - font.getbbox(ln)[2]) / 2
        for ch in ln:
            col = cols[k % len(cols)] if ch.strip() else (0, 0, 0)
            if letters:
                d.text((x, y), ch, font=font, fill=col + (255,), anchor="lm", stroke_width=6, stroke_fill=(255, 255, 255, 255))
            x += font.getlength(ch)
            k += 1 if ch.strip() else 0
        y += 150
    return im


@lru_cache(maxsize=8)
def title_parts(text, kind):
    """The title card without letters, and each letter as its own little picture with its resting place on the card."""
    font = ImageFont.truetype(FONT, 104 if kind == "title" else 88)
    bg = title_img(text, kind, letters=False)
    lines = text.split("\n")
    cols = [(255, 90, 90), (255, 165, 40), (60, 170, 90), (60, 140, 240), (170, 90, 230)]
    W = max(font.getbbox(l)[2] for l in lines) + 160
    letters, y, k = [], 45 + 75, 0
    for ln in lines:
        x = (W + 16 - font.getbbox(ln)[2]) / 2
        for ch in ln:
            if ch.strip():
                im = Image.new("RGBA", (int(font.getlength(ch)) + 40, 190), (0, 0, 0, 0))
                ImageDraw.Draw(im).text((20, 95), ch, font=font, fill=cols[k % len(cols)] + (255,), anchor="lm",
                                        stroke_width=6, stroke_fill=(255, 255, 255, 255))
                letters.append((im, x - 20, y - 95))
                k += 1
            x += font.getlength(ch)
        y += 150
    return bg, letters


def draw_titles(frame, t):
    """Title cards pop in, then the letters drop in one by one with a bounce; a few stars twinkle once they land."""
    for tt in G["titles"]:
        if not (tt["t0"] <= t <= tt["t1"]):
            continue
        a, out = t - tt["t0"], tt["t1"] - t
        s_ = 1.12 * smooth(a / 0.2) if a < 0.2 else 1.12 - 0.12 * smooth((a - 0.2) / 0.15)
        s_ *= smooth(out / 0.25) if out < 0.25 else 1.0
        if s_ <= 0.02:
            continue
        bg, letters = title_parts(tt["text"], tt["kind"])
        im = bg.copy()
        for i, (li, lx, ly) in enumerate(letters):
            q = (a - 0.15 - 0.045 * i) / 0.35
            if q <= 0:
                continue
            q = min(q, 1.0)
            back = 1 + 2.7 * (q - 1) ** 3 + 1.7 * (q - 1) ** 2          # ease out with a little overshoot
            dy = -80 * (1 - back)
            sc = 0.5 + 0.5 * back
            lw, lh = max(1, int(li.width * sc)), max(1, int(li.height * sc))
            im.alpha_composite(li.resize((lw, lh), Image.BICUBIC) if sc != 1 else li,
                               (int(lx + (li.width - lw) / 2), int(ly + dy + (li.height - lh) / 2)))
        done = 0.15 + 0.045 * len(letters) + 0.35
        if a > done:
            fx.sparkles(im, (40, 20, im.width - 40, im.height - 20), t, len(tt["text"]))
        im = im.resize((max(1, int(im.width * s_)), max(1, int(im.height * s_))), Image.BICUBIC)
        y = OUT_H * (0.42 if tt["kind"] == "title" else 0.36) + 8 * math.sin(2 * math.pi * 0.6 * a)
        frame.alpha_composite(im, (int(OUT_W / 2 - im.width / 2), int(y - im.height / 2)))


# ------------------------------------------------------------------ games: drawn props (no art files needed)
LINE = (70, 45, 30)


@lru_cache(maxsize=64)
def tramp_img(w, dip):
    """A kids' trampoline seen from the front: blue padded rim, dark mat (dips when someone lands), little legs."""
    k = 2
    W, H = w * k, int(w * 0.42) * k
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    lw = max(2, int(W * 0.012))
    rim_h = H * 0.42
    for fx in (0.1, 0.3, 0.7, 0.9):                                   # legs
        x = W * fx
        d.rounded_rectangle([x - W * 0.018, rim_h * 0.5, x + W * 0.018, H - lw], radius=W * 0.01, fill=(90, 95, 110), outline=LINE, width=lw)
    d.ellipse([lw, lw, W - lw, rim_h], fill=(70, 150, 245), outline=LINE, width=lw)                 # padded rim
    dp = dip * k
    d.ellipse([W * 0.09, rim_h * 0.18 + dp * 0.5, W * 0.91, rim_h * 0.82 + dp], fill=(45, 50, 80), outline=LINE, width=lw)  # mat
    d.arc([W * 0.2, rim_h * 0.28 + dp * 0.5, W * 0.8, rim_h * 0.7 + dp], 200, 340, fill=(255, 255, 255, 90), width=lw)
    return im.resize((w, H // k), Image.LANCZOS)


@lru_cache(maxsize=16)
def box_img(w, h):
    """A big toy box to hide behind: red with a yellow lid band and a star."""
    k = 2
    W, H = w * k, h * k
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    lw = max(3, int(W * 0.014))
    d.rounded_rectangle([lw, H * 0.12, W - lw, H - lw], radius=W * 0.05, fill=(235, 70, 70), outline=LINE, width=lw)
    d.rounded_rectangle([0, 0, W, H * 0.2], radius=W * 0.05, fill=(255, 205, 40), outline=LINE, width=lw)
    cx, cy, r = W / 2, H * 0.58, min(W, H) * 0.2
    pts = [(cx + (r if i % 2 == 0 else r * 0.45) * math.sin(math.pi * i / 5), cy - (r if i % 2 == 0 else r * 0.45) * math.cos(math.pi * i / 5)) for i in range(10)]
    d.polygon(pts, fill=(255, 230, 90), outline=LINE, width=lw)
    return im.resize((w, h), Image.LANCZOS)


def tramp_for(who, t):
    for tr in (G.get("games") or {}).get("tramp", []):
        if tr["who"] == who and tr["t0"] <= t <= tr["t1"]:
            return tr
    return None


def ball_at(b, t, hands, feet, z):
    """Screen position, squash and spin of a ball in play, or None."""
    if not (b["t0"] <= t <= b["t1"] + (0.6 if b["kind"] == "kick" else 0)):
        return None
    if b["kind"] == "throw":
        side_a, side_b = G["cast"][b["from"]]["hold_side"], G["cast"][b["to"]]["hold_side"]
        a, e = np.array(hands[(b["from"], side_a)]), np.array(hands[(b["to"], side_b)])
        fy = feet[b["to"]][1]
        pts = [b["t0"]] + b["hits"] + [b["t1"]]
        n = len(pts) - 1
        q = (t - b["t0"]) / (b["t1"] - b["t0"])
        x = a[0] + (e[0] - a[0]) * q
        j = min(int((t - b["t0"]) / ((b["t1"] - b["t0"]) / n)), n - 1)
        u = (t - pts[j]) / (pts[j + 1] - pts[j])
        y0 = a[1] if j == 0 else fy
        y1 = e[1] if j == n - 1 else fy
        top = min(y0, y1) - 150 * z
        y = (1 - u) ** 2 * y0 + 2 * u * (1 - u) * top + u ** 2 * y1
    elif b["kind"] == "dribble":
        side = G["cast"][b["who"]]["hold_side"]
        hx, hy = hands[(b["who"], side)]
        fy = feet[b["who"]][1]
        u = ((t - b["t0"]) % b["per"]) / b["per"]
        x, y = hx, hy + (fy - hy) * math.sin(math.pi * u) ** 0.7
    else:                                                # kick: along the floor with shrinking hops, then rolls to a stop
        fx, fy = feet[b["who"]]
        tgt = b.get("to")
        if isinstance(tgt, str) and tgt in feet:
            ex = feet[tgt][0]
        else:
            ex = ((float(tgt) if tgt is not None else 0.8) * WORLD_W - G["cam_x0"]) * z
        q = min((t - b["t0"]) / (b["t1"] - b["t0"]), 1.0)
        x = fx + (ex - fx) * (1 - (1 - q) ** 1.6)
        pts = [b["t0"]] + b["hits"]
        y = fy
        for j in range(len(pts) - 1):
            if pts[j] <= t < pts[j + 1]:
                u = (t - pts[j]) / (pts[j + 1] - pts[j])
                y = fy - 4 * u * (1 - u) * 110 * z * (0.5 ** j)
    sq = 1.0
    for h in b["hits"]:
        if abs(t - h) < 0.05:
            sq = 1 - 0.25 * (1 - abs(t - h) / 0.05)
    return x, y, sq, (t - b["t0"]) * 540


def draw_ball(frame, pic, x, y, d, sq, rot):
    base = G["pics"][pic]
    im = base.resize((max(1, int(d)), max(1, int(d * base.height / base.width))), Image.LANCZOS).rotate(rot % 360, resample=Image.BICUBIC)
    if sq < 1:
        im = im.resize((int(im.width / sq ** 0.5), max(1, int(im.height * sq))), Image.BICUBIC)
    frame.alpha_composite(im, (int(x - im.width / 2), int(y - im.height)))


def draw_balloon_game(frame, bl, t, z):
    n = len(bl["colors"])
    rng = random.Random(int(bl["t0"] * 100))
    for i, col in enumerate(bl["colors"]):
        x = OUT_W * (0.22 + 0.56 * (i + 0.5) / n) + rng.uniform(-40, 40)
        rise = smooth(min((t - bl["t0"] - 0.15 * i) / 1.3, 1.0))
        y = OUT_H * (1.12 - 0.72 * rise) + 14 * math.sin(2 * math.pi * 0.6 * t + i)
        pop = bl["pops"][i] if i < len(bl["pops"]) else None
        h = int(OUT_H * 0.26)
        if pop is None or t < pop:
            draw_prop(frame, f"balloon_{col}", x, y + h, h, t + i, True)
        elif t < pop + 0.8:                               # burst star + confetti falling
            a = (t - pop) / 0.8
            d = ImageDraw.Draw(frame)
            if a < 0.25:
                r = h * 0.3 * (0.6 + a * 2)
                pts = [(x + (r if j % 2 == 0 else r * 0.4) * math.sin(math.pi * j / 6), y + h * 0.3 - (r if j % 2 == 0 else r * 0.4) * math.cos(math.pi * j / 6)) for j in range(12)]
                d.polygon(pts, fill=(255, 245, 160, int(255 * (1 - a * 4))))
            cr = random.Random(i * 31 + int(pop * 10))
            for _ in range(26):
                ang, sp = cr.uniform(0, 2 * math.pi), cr.uniform(200, 520)
                cx = x + math.cos(ang) * sp * a
                cy = y + h * 0.3 + math.sin(ang) * sp * a + 500 * a * a
                cc = cr.choice([(255, 80, 80), (60, 150, 240), (255, 205, 40), (90, 200, 110), (180, 100, 240)])
                w_ = 9 + cr.randint(0, 6)
                d.rectangle([cx, cy, cx + w_, cy + w_ * 0.6], fill=cc + (int(255 * (1 - a ** 2)),))


def leg_mats(rig, side, pz):
    """Thigh and shin matrices (source px) for one leg: hip swing, knee bend, knee lift (foreshortened thigh), squat."""
    L = rig["legs"][side]
    H, K, A = (np.array(L[k], float) for k in ("H", "K", "A"))
    s = 1 if side == "sr" else -1
    th = math.radians(40 * pz["squat"])
    h = pz[f"h_{side}"] + s * math.degrees(th)                   # squat: knees out, feet stay under the hips
    k = pz[f"k_{side}"] - s * 2 * math.degrees(th)
    f = min(max(pz[f"f_{side}"], 0.0), 0.8)
    Mt = about(H, R(h)) @ about(H, S(1 + 0.05 * f, 1 - 0.55 * f))
    K2 = (Mt @ [*K, 1])[:2]
    Ms = T(K2[0] - K[0], K2[1] - K[1]) @ about(K, R(h + k)) @ about(K, S(1, 1 - 0.1 * f))
    return Mt, Ms


def squat_drop(rig, pz):
    if not rig.get("legs"):
        return 0.0
    L = next(iter(rig["legs"].values()))
    th = math.radians(40 * pz["squat"])
    return (L["Lu"] + L["Ll"]) * (1 - math.cos(th)) * 0.9


def compose(t, place_name):
    set_place(place_name)
    G["cur_place_t"] = max([c0 for c0, nm in G["place_changes"] if nm == place_name and c0 <= t + 0.5] or [0.0])
    for w in WHO:
        G["cast"][w]["x"] = x_at(w, t)
    x0, y0, w, cam = cam_rect(t)
    z = OUT_W / w
    P_ = G.get("scene")
    if P_ is not None:
        rx0, ry0, rw, _ = cam_rect(t, start=True)
        frame = scenery.view(P_, (x0, y0, w), (rx0, ry0, rw), t)
        scenery.life(P_, frame, (x0, y0, w), (rx0, ry0, rw), t)
    else:
        frame = G["bg"].crop((int(x0), int(y0), int(x0 + w), int(y0 + w * OUT_H / OUT_W))).resize((OUT_W, OUT_H), Image.BICUBIC).convert("RGBA")
    C = S(z) @ T(-x0, -y0)
    poses = {who: pose_at(who, t) for who in WHO}
    for who in WHO:
        poses[who]["_hs"] = {sd: hand_shape(who, sd, t) for sd in ("sl", "sr")}
    G["cam_x0"] = x0
    for who in WHO:                                     # standing on a trampoline: the mat is their floor (it dips on landing)
        if tramp_for(who, t):
            c = G["cast"][who]
            ch = c["char_h"] * c["k"]
            dip = ch * 0.05 * poses[who]["squat"] if poses[who]["hop"] < 0.005 else 0.0
            tw = int(ch * 0.9 * z)
            timg = tramp_img(tw, int(dip * z))
            frame.alpha_composite(timg, (int((c["x"] - x0) * z - tw / 2), int((c["floor"] - y0) * z - timg.height)))
            c["floor"] = c["floor"] - tw / z * 0.42 * 0.3 + dip
    ovals = []
    for who in WHO:
        c = G["cast"][who]
        pz = poses[who]
        sw = c["char_h"] * c["k"] * 0.22 * z * (1 - 0.35 * min(pz["hop"] / 0.16, 1))
        px, py = (c["x"] + pz["dx"] * c["char_h"] * c["k"] - x0) * z, (c["floor"] - y0) * z
        ovals.append([px - sw, py - sw * 0.16, px + sw, py + sw * 0.16])
    for f in G.get("finds", []):                        # can you find it? (in the place, behind the characters)
        if f["place"] == place_name and t >= f["t0"] - 0.5:
            sx, sy = (f["x"] * WORLD_W - x0) * z, (f["y"] * WORLD_H - y0) * z
            story_fx.draw_find(frame, G["pics"][f["pic"]], t, f["found"], sx, sy, f["size"] * WORLD_H * z)
    draw_shadows(frame, ovals)
    scene_frame = frame
    if P_ is not None:                                  # characters + what they hold on their own layer, lit by the place
        frame = Image.new("RGBA", scene_frame.size, (0, 0, 0, 0))
    order = sorted(WHO, key=lambda w: (G["cast"][w]["floor"], -G["cast"][w]["char_h"] * G["cast"][w]["k"]))
    hands = {}
    for who in order:
      main_layer = frame
      try:
        c = G["cast"][who]
        rig, pz = c["rig"], poses[who]
        vx, vy, vr = motion(who, t, pz)                 # also drives follow-through below
        chs = c["char_h"] * c["k"] * z
        blur = (abs(vx) * chs * SHUTTER, abs(vy) * chs * SHUTTER)
        if max(blur) >= 2.5:                            # fast move: draw this character alone, then smear it a little
            frame = Image.new("RGBA", main_layer.size, (0, 0, 0, 0))
        su, sdir, smove = side_amount(who, t)
        if su >= 0.5:                                   # turned: the side view walks (the turn opens it out)
            hp = draw_side(frame, C, who, t, min(1.0, 0.3 + 1.4 * (su - 0.5)), sdir, smove)
            hands[(who, "sl")] = hands[(who, "sr")] = hp
            continue
        if su > 0:                                      # turning: the front view narrows first
            pz = dict(pz)
            pz["sx"] *= max(0.3, 1 - 1.4 * su)
        Mf = C @ char_matrix(who, pz)
        P = rig["parts"]
        legs = rig.get("legs") or {}
        drop = squat_drop(rig, pz)
        Ml = Mf @ T(0, drop)
        if legs:                                        # legs behind the body: shin, then thigh (its stub hides under the hips)
            hc = [(legs["sl"]["H"][0] + legs["sr"]["H"][0]) / 2, legs["sl"]["H"][1]]
            M = Ml @ about(hc, R(-pz["lean"]))
            spread = min(1.0, 3 * pz["squat"] + (abs(pz["h_sl"]) + abs(pz["h_sr"])) / 20)
            if "crotch" in P and spread > 0.02:
                cimg = c["parts"]["crotch"]
                if spread < 0.98:
                    cimg = cimg.copy(); cimg.putalpha(cimg.getchannel("A").point(lambda v: int(v * spread)))
                place(frame, cimg, M @ T(*P["crotch"]["offset"]))
            for side in ("sl", "sr"):
                Mt, Ms = leg_mats(rig, side, pz)
                place(frame, c["parts"][f"shin_{side}"], Ml @ Ms @ T(*P[f"shin_{side}"]["offset"]))
                place(frame, c["parts"][f"thigh_{side}"], Ml @ Mt @ T(*P[f"thigh_{side}"]["offset"]))
        else:
            M = Ml
        Mh = M @ about(P["head"]["pivot"], R(pz["head"] * c["tilt"]))     # hair crossing the neck cut limits the tilt
        off = lambda n: T(*P[n]["offset"])
        front = [sd_ for sd_ in ("sl", "sr") if crosses_body(pz, sd_)]
        for side in ("sl", "sr"):
            if side not in front:
                draw_arm(frame, M, rig, side, pz, "back")
            else:                                      # sleeve + upper arm behind; forearm and hand in front later
                draw_arm_upper_only(frame, M, rig, side, pz)
            Wp = arm_points(rig, side, pz)[3]
            hands[(who, side)] = (M @ [*Wp, 1])[:2]
        # follow-through: hair / ears / hem lag behind the move (vx, vy, vr from motion() above)
        sgn = -1 if c["flip"] else 1
        body_img, Mb = c["parts"]["body"], M @ off("body")
        bx = -max(-0.02, min(0.02, vx * 0.02)) * body_img.width * sgn
        if abs(bx) > 0.8:
            body_img, m_ = fx.follow(body_img, bx, 0.0, top=False)
            Mb = Mb @ T(-m_, -m_)
        place(frame, body_img, Mb)
        bq = blink_at(who, t)
        mo = mouth_at(who, t)
        expr, lx, ly = face_at(who, t)
        head_img = face_head(who, mo, bq, expr, lx, ly) if (bq or mo in MOUTHS or expr or lx or ly) else c["parts"]["head"]
        Mhd = Mh @ off("head")
        hw, hh = head_img.size
        hx = -max(-0.035, min(0.035, vx * 0.03 + vr * 0.0006)) * hw * sgn
        hy = max(-0.035, min(0.035, vy * 0.025)) * hh
        if abs(hx) > 0.8 or abs(hy) > 0.8:
            head_img, m_ = fx.follow(head_img, hx, hy, top=True)
            Mhd = Mhd @ T(-m_, -m_)
        place(frame, head_img, Mhd)
        for side in front:
            draw_arm(frame, M, rig, side, pz, "front")
        for hd in (G.get("games") or {}).get("hide", []):
            if hd["who"] == who and hd["t0"] <= t <= hd["t1"]:   # the toy box in front of whoever hides
                ch = c["char_h"] * c["k"]
                bw, bh = int(ch * 0.78 * z), int(ch * 0.6 * z)
                slide = smooth((t - hd["t0"]) / 0.35) * (1 - smooth((t - hd["t1"] + 0.25) / 0.25))
                bx = (c["x"] - x0) * z - bw / 2
                by = (c["floor"] - y0) * z - bh * slide + 6
                frame.alpha_composite(box_img(bw, bh), (int(bx), int(by)))
      finally:
        if frame is not main_layer:
            main_layer.alpha_composite(fx.motion_blur(frame, *blur))
            frame = main_layer
    # props in hands, and props flying from one hand to another
    for h in G["holds"]:
        if h["t0"] <= t < h["t1"]:
            c = G["cast"][h["who"]]
            x, y = hands[(h["who"], c["hold_side"])]
            ball = h["pic"].startswith("balloon")
            if ball:                                   # string leans outward: the balloon floats clear of the head
                x += (1 if c["hold_side"] == "sr" else -1) * (-1 if c["flip"] else 1) * c["char_h"] * c["k"] * z * 0.06
            draw_prop(frame, h["pic"], x, y, c["char_h"] * c["k"] * z * (0.42 if ball else 0.22), t, ball)
    for f in G["flights"]:
        if f["t0"] <= t < f["t1"]:
            q = smooth((t - f["t0"]) / (f["t1"] - f["t0"]))
            a = hands[(f["from"], G["cast"][f["from"]]["hold_side"])]
            b = hands[(f["to"], G["cast"][f["to"]]["hold_side"])]
            x = a[0] + (b[0] - a[0]) * q
            y = a[1] + (b[1] - a[1]) * q - math.sin(math.pi * q) * 120 * z
            c = G["cast"][f["to"]]
            ball = f["pic"].startswith("balloon")
            draw_prop(frame, f["pic"], x, y, c["char_h"] * c["k"] * z * (0.42 if ball else 0.22), t, ball)
    gm = G.get("games") or {}
    feet = {w: ((G["cast"][w]["x"] - x0) * z, (G["cast"][w]["floor"] - y0) * z) for w in WHO}
    for b in gm.get("ball", []):
        bp = ball_at(b, t, hands, feet, z)
        if bp:
            who = b.get("from") or b.get("who")
            c = G["cast"][who]
            d = c["char_h"] * c["k"] * z * 0.21
            fy = feet[b.get("to") if b["kind"] == "throw" else who][1]
            sh = max(0.3, 1 - (fy - bp[1]) / (400 * z))       # a little floor shadow, smaller as the ball goes up
            ImageDraw.Draw(frame).ellipse([bp[0] - d * 0.45 * sh, fy - d * 0.08 * sh, bp[0] + d * 0.45 * sh, fy + d * 0.08 * sh],
                                          fill=(0, 0, 0, int(60 * sh)))
            draw_ball(frame, b["pic"], bp[0], bp[1] + d * 0.5, d, bp[2], bp[3])
    for bl in gm.get("balloons", []):
        if bl["t0"] <= t <= bl["t1"]:
            draw_balloon_game(frame, bl, t, z)
    for (tl_, who, ht) in G.get("landings", []):        # dust where feet land
        if 0 <= t - tl_ < 0.45:
            c = G["cast"][who]
            ch = c["char_h"] * c["k"] * z
            fx.dust(frame, (c["x"] - x0) * z, (c["floor"] - y0) * z, (t - tl_) / 0.45, ch * min(1.0, 0.45 + ht * 3))
    for (who, s0, s1) in G.get("sparkle", []):          # twinkles round a happy character
        if s0 <= t <= s1:
            c = G["cast"][who]
            ch = c["char_h"] * c["k"] * z
            px, py = (c["x"] - x0) * z, (c["floor"] - y0) * z
            fx.sparkles(frame, (px - 0.35 * ch, py - 1.05 * ch, px + 0.35 * ch, py), t, hash(who) % 997 + int(s0))
    if P_ is not None:
        scene_frame.alpha_composite(scenery.light(P_, frame, z))
        frame = scene_frame
    for (s0, dur, kind, seed) in G.get("screen_fx", []):
        if s0 <= t <= s0 + dur + 5.0:
            fx.screen_fx(frame, kind, t - s0, dur, seed)
    draw_cards(frame, t, cam)
    draw_titles(frame, t)
    for tu in gm.get("turn", []):
        if tu["t0"] <= t <= tu["t1"]:
            b = badge("Your turn!", (60, 150, 240))
            pop = smooth((t - tu["t0"]) / 0.25) * (1 + 0.05 * math.sin(2 * math.pi * 1.6 * t))
            bb = b.resize((max(1, int(b.width * pop)), max(1, int(b.height * pop))), Image.BICUBIC)
            frame.alpha_composite(bb, (int(OUT_W / 2 - bb.width / 2), int(OUT_H * 0.06)))
            story_fx.countdown(frame, t, tu["t0"], tu["t1"], OUT_W / 2, int(OUT_H * 0.06) + bb.height + 70)
    fs = G.get("finds") or []
    if fs and G["story"].get("collection", True):       # the found objects collected at the top right
        got = [G["pics"][f["pic"]] for f in fs if f["found"] is not None and t >= f["found"] + 1.4]
        if t >= fs[0]["t0"]:
            story_fx.collection(frame, got, len(fs), None)
    for m0, m1, k in G.get("maps", []):                 # the treasure map pops up over the scene
        if m0 <= t <= m1:
            a = t - m0
            s_ = smooth(a / 0.3) * (1 - smooth((t - m1 + 0.3) / 0.3))
            if s_ > 0.02:
                dim = Image.new("RGBA", frame.size, (40, 25, 10, int(110 * s_)))
                frame.alpha_composite(dim)
                card = story_fx.map_card(G["story"].get("map_stops", []), k, a, G["cast"]["bobo"]["parts"]["head"] if "bobo" in G["cast"]
                                         else G["cast"][HOST]["parts"]["head"], G["story"].get("map_title", "Bobo's map!"))
                cw, ch_ = int(card.width * s_), int(card.height * s_)
                frame.alpha_composite(card.resize((max(1, cw), max(1, ch_)), Image.BICUBIC), (int(OUT_W / 2 - cw / 2), int(OUT_H / 2 - ch_ / 2)))
    return frame


@lru_cache(maxsize=4)
def wipe_mask(r):
    m = Image.new("L", (OUT_W, OUT_H), 0)
    ImageDraw.Draw(m).ellipse([OUT_W / 2 - r, OUT_H / 2 - r, OUT_W / 2 + r, OUT_H / 2 + r], fill=255)
    return m


def graded(im):
    """One picture through the same colour grade as the video (stills, thumbnails), so checks match the film."""
    grade = G["story"].get("grade", GRADE)
    if not grade:
        return im
    im = im.convert("RGB")
    raw = subprocess.run(["ffmpeg", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{im.width}x{im.height}", "-i", "-",
                          "-vf", grade, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], input=im.tobytes(), capture_output=True, check=True).stdout
    return Image.frombytes("RGB", im.size, raw)


def hook_badge():
    return badge("Coming up!", (230, 40, 60))


@lru_cache(maxsize=8)
def badge(text, ink):
    font = ImageFont.truetype(FONT, 64)
    w = int(font.getlength(text)) + 90
    im = Image.new("RGBA", (w + 16, 130), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([10, 14, w + 10, 124], radius=50, fill=(0, 0, 0, 70))
    d.rounded_rectangle([4, 4, w + 4, 114], radius=50, fill=(255, 255, 255, 255))
    d.rounded_rectangle([14, 14, w - 6, 104], radius=42, fill=(255, 214, 40, 255))
    d.text((w / 2 + 4, 60), text, font=font, fill=ink + (255,), anchor="mm", stroke_width=5, stroke_fill=(255, 255, 255, 255))
    return im


def render_frame(fi):
    """Output frame fi: the hook teaser first (moments cut from later in the episode), then the episode itself."""
    t = fi / FPS
    L = hook.length(G["hook"])
    if t >= L:
        return episode_frame(t - L)
    src = hook.source_time(t, G["hook"])
    im = episode_frame(src).convert("RGBA")
    a = t
    for _, d in G["hook"]:                             # time into this clip
        if a < d:
            break
        a -= d
    if a < 0.12:                                       # a quick white flash on every cut: the teaser feels fast
        im = Image.blend(im, Image.new("RGBA", im.size, (255, 255, 255, 255)), 0.55 * (1 - a / 0.12))
    b = hook_badge()
    pop = smooth(t / 0.25)
    bb = b.resize((max(1, int(b.width * pop)), max(1, int(b.height * pop))), Image.BICUBIC) if pop < 1 else b
    im.alpha_composite(bb, (60, 50))
    return im.convert("RGB")


def episode_frame(t):
    es = G.get("end_screen")
    if es is not None and t >= es:                      # the last 20 s: room for YouTube's end-screen boxes
        return story_fx.end_screen(_episode_frame(t).convert("RGBA"), (t - es) / 0.8, G["story"].get("end_text", "Watch next!")).convert("RGB")
    return _episode_frame(t)


def _episode_frame(t):
    tr = transition_at(t)
    if tr is None:
        return compose(t, place_at(t)).convert("RGB")
    old, new, q, kind = tr
    return fx.transition(compose(t, old), compose(t, new), q, kind).convert("RGB")


def _init(story_path):
    load(story_path)


def _frame_bytes(fi):
    return render_frame(fi).tobytes()


def _episode_bytes(fi):
    return episode_frame(fi / FPS).tobytes()


def main():
    story = sys.argv[1]
    args = sys.argv[2:]
    load(story)
    st = G["story"]
    build = ROOT / st.get("build", "cartoon2d/build/story1")
    build.mkdir(parents=True, exist_ok=True)
    if "--stills" in args:
        ts = [float(x) for x in args[args.index("--stills") + 1].split(",")]
        ims = [graded(episode_frame(t) if t >= 0 else render_frame(int(round(-t * FPS)))) for t in ts]   # -t = hook time
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
    if "--clip" in args:                             # a test clip: episode seconds a..b with the episode's own mix
        c0, c1 = (float(x) for x in args[args.index("--clip") + 1].split(","))
        out = build / f"clip_{int(c0)}_{int(c1)}.mp4"
        frames = range(int(c0 * FPS), int(c1 * FPS))
        ff = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{OUT_W}x{OUT_H}", "-r", str(FPS),
                               "-i", "-", "-ss", str(c0), "-t", str(c1 - c0), "-i", str(build / "final_mix.wav"),
                               *(["-vf", st.get("grade", GRADE)] if st.get("grade", GRADE) else []), *ENCODE, "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest", str(out)], stdin=subprocess.PIPE)
        with Pool(7, initializer=_init, initargs=(story,)) as pool:
            for b_ in pool.imap(_episode_bytes, frames, chunksize=4):
                ff.stdin.write(b_)
        ff.stdin.close()
        ff.wait()
        print("CLIP", out, ff.returncode)
        return
    out = ROOT / (args[args.index("--out") + 1] if "--out" in args else f"{st.get('build', 'cartoon2d/build/story1')}/video_silent.mp4")
    probs = (storycheck.problems(st, G["tl"]) if st.get("storycheck")  # story bible + retention rules (+ the place rules)
             else places.problems(st, G["tl"]))      # new place every ~2 min, backgrounds new to the show
    if probs and "--allow-place-rules" not in args:
        for p_ in probs:
            print("PLACE RULE", p_, flush=True)
        sys.exit("render refused: fix the places (or pass --allow-place-rules for an old episode)")
    grade = st.get("grade", GRADE)                   # story "grade": false = the art's own colours
    n = int((G["tl"]["total"] + hook.length(G["hook"])) * FPS)
    print("HOOK", G["hook"], flush=True)
    ff = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{OUT_W}x{OUT_H}", "-r", str(FPS),
                           "-i", "-", *(["-vf", grade] if grade else []), *ENCODE, "-pix_fmt", "yuv420p",
                           "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", str(out)], stdin=subprocess.PIPE)
    with Pool(7, initializer=_init, initargs=(story,)) as pool:
        for i, b in enumerate(pool.imap(_frame_bytes, range(n), chunksize=6)):
            ff.stdin.write(b)
            if i % 250 == 0:
                print("FRAME", i, "/", n, flush=True)
    ff.stdin.close()
    ff.wait()
    print("VIDEO", out, ff.returncode)
    if ff.returncode == 0 and "--out" not in args:
        places.register(st, G["tl"])


if __name__ == "__main__":
    main()
