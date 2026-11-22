"""Flat cartoon mini scenes (docs/food_files/IMPROVEMENT_PLAN.md, Phase 4): simple flat people acting out a moment in a
flat place, like the reference's "man carrying a turkey out of the grocery store" or "sick kid in a classroom".

Places: ~20 flat vector backgrounds, each made ONCE by Flow from one strict style prompt and kept for every video
(no per-video asset work). Until Flow has made one, a code-drawn backdrop of the same colours stands in.
People: drawn in code every frame (round head, rounded body, two-part arms and legs) so they can move: stand, walk, run,
carry, eat, sick, fall, point, cheer, sit, shock, wave, talk. Props are the Food Files icons, held or placed.

CSV (shot = scene2d, place = one of PLACES, rows = what happens, ";" between parts):
    "man: carry turkey; say = HEAVY!"
    "kid: sick; kid: sick; kid: sick; count; label = 4 KIDS HOSPITALIZED"
    "kid: sick; list = SHORTNESS OF BREATH | NAUSEA; monitor"
  who: kid | man | woman | doctor | worker | teen | old    action: see ACTIONS    then an optional prop (an icon name)
  say = text (a speech bubble)  list = A | B (red-cross list)  monitor (a heartbeat monitor)  count (1 2 3 under people)
  label = text (a pill at the bottom)
"""
import math
import re

from PIL import Image, ImageDraw

from . import icons, look as L

STYLE = ("Flat vector illustration background for an explainer video, simple clean shapes, no outlines on the background, "
         "soft muted colours with one warm accent, gentle flat shading, wide 16:9 view at eye level, the lower third is an "
         "empty floor or ground where characters will stand, no people, no animals, no text, no letters, no logos")
PLACES = {
    "classroom": "a school classroom with a green chalkboard, a window and a few desks pushed to the sides",
    "kitchen": "a home kitchen with cabinets, a fridge, a stove and a counter",
    "store": "the front of a small grocery store on a street, red and white awning, windows with shelves inside",
    "supermarket": "a supermarket aisle with shelves of colourful packaged food on both sides",
    "street": "a quiet town street with houses, a sidewalk and a road",
    "night_road": "a highway at night with street lamps, a dark blue sky and a full moon",
    "hospital": "a hospital room with a bed, a window, a curtain and a heart monitor on a stand",
    "doctor_office": "a doctor's office with an examination bed, a desk and a poster of the body on the wall",
    "living_room": "a cosy living room with a sofa, a lamp, a rug and a TV",
    "dining_room": "a dining room with a long table set for a family dinner, a window and a cabinet",
    "factory": "inside a food factory with conveyor belts, steel machines and big mixing vats",
    "lab": "a science lab with benches, test tubes, beakers and a microscope",
    "courtroom": "a courtroom with a judge's bench, wooden panels and a flag stand without a flag",
    "office": "a company boardroom with a long table, chairs and a big window with a city skyline",
    "playground": "a school playground with a slide, swings and grass",
    "backyard": "a backyard with a fence, grass, a barbecue grill and a tree",
    "candy_shop": "an old-fashioned candy shop with glass jars of colourful sweets on wooden shelves",
    "market_1850": "a Victorian English market street in the 1850s with stalls, cobblestones and brick buildings",
    "restaurant": "a fast food restaurant counter with menu boards (blank), a till and stools",
    "news_studio": "a TV news studio with a desk, screens (blank) and blue studio lights",
}
# a code-drawn stand-in per place: (wall top, wall bottom, floor) colours
TINTS = {"classroom": ((80, 120, 110), (60, 95, 88), (150, 110, 80)), "kitchen": ((236, 220, 190), (220, 200, 165), (170, 130, 95)),
         "store": ((170, 210, 235), (150, 195, 225), (120, 120, 128)), "street": ((170, 210, 235), (150, 195, 225), (110, 110, 118)),
         "night_road": ((20, 30, 60), (30, 40, 75), (50, 50, 60)), "hospital": ((214, 232, 236), (196, 220, 226), (170, 185, 190)),
         "factory": ((120, 126, 136), (100, 106, 116), (80, 84, 90)), "market_1850": ((200, 180, 150), (170, 150, 120), (120, 110, 100))}
WHO = {"kid": dict(shirt=(70, 130, 220), hair=(70, 45, 30), h=0.62, skin=(240, 200, 160)),
       "teen": dict(shirt=(220, 80, 80), hair=(40, 30, 25), h=0.80, skin=(225, 180, 140)),
       "man": dict(shirt=(70, 120, 90), hair=(60, 40, 30), h=1.0, skin=(240, 200, 160)),
       "woman": dict(shirt=(200, 80, 150), hair=(120, 60, 30), h=0.94, skin=(230, 190, 150), long_hair=True),
       "doctor": dict(shirt=(250, 250, 250), hair=(90, 70, 50), h=1.0, skin=(220, 175, 135), coat=True),
       "worker": dict(shirt=(240, 150, 40), hair=(50, 35, 25), h=1.0, skin=(200, 150, 110), cap=True),
       "old": dict(shirt=(150, 120, 170), hair=(220, 220, 220), h=0.92, skin=(240, 205, 170))}
ACTIONS = ("stand", "walk", "run", "carry", "eat", "sick", "fall", "point", "cheer", "sit", "shock", "wave", "talk")
INK = (34, 28, 30, 255)


def place_key(name):
    return "place2d_" + re.sub(r"[^a-z0-9_]", "", str(name or "").lower())


def place_prompt(name):
    return f"{STYLE}. The place: {PLACES.get(name, name)}."


def norm_place(name):
    n = re.sub(r"[^a-z0-9_]", "_", str(name or "").strip().lower()).strip("_")
    if n in PLACES:
        return n
    for k in PLACES:
        if k in n or n in k:
            return k
    return n or "street"


def parse(rows_text):
    """'man: carry turkey; say = HEAVY!; count' -> {"actors": [...], "say", "list", "monitor", "count", "label"}."""
    out = {"actors": [], "say": "", "list": [], "monitor": False, "count": False, "label": ""}
    for part in str(rows_text or "").split(";"):
        p = part.strip()
        if not p:
            continue
        low = p.lower()
        if low == "monitor":
            out["monitor"] = True
        elif low == "count":
            out["count"] = True
        elif "=" in p and low.split("=")[0].strip() in ("say", "list", "label"):
            k, _, v = p.partition("=")
            k = k.strip().lower()
            out[k] = [x.strip() for x in v.split("|") if x.strip()] if k == "list" else v.strip()
        elif ":" in p:
            who, _, act = p.partition(":")
            words = act.split()
            action = words[0].lower() if words and words[0].lower() in ACTIONS else "stand"
            prop = " ".join(words[1:] if words and words[0].lower() in ACTIONS else words)
            out["actors"].append({"who": who.strip().lower() if who.strip().lower() in WHO else "man", "action": action,
                                  "prop": icons.key_of(prop) if prop else None})
    return out


# ------------------------------------------------------------------ backdrop
def backdrop(name, size):
    """The code-drawn stand-in for a place (Flow's picture replaces it once made)."""
    W, H = size
    top, bot, floor = TINTS.get(name, ((200, 214, 226), (180, 196, 210), (150, 130, 110)))
    im = Image.new("RGB", size, top)
    d = ImageDraw.Draw(im)
    fy = int(H * 0.70)
    for y in range(fy):
        k = y / max(1, fy)
        d.line((0, y, W, y), fill=tuple(int(a + (b - a) * k) for a, b in zip(top, bot)))
    d.rectangle((0, fy, W, H), fill=floor)
    d.line((0, fy, W, fy), fill=tuple(max(0, c - 30) for c in floor), width=max(2, H // 200))
    if name == "night_road":
        d.ellipse((W * 0.82, H * 0.10, W * 0.88, H * 0.10 + W * 0.06), fill=(245, 240, 210))
    return im.convert("RGBA")


# ------------------------------------------------------------------ people
def _pose(action, ph, t):
    """Joint angles in degrees, both arms in the same mirrored sense: arm = how far the upper arm swings OUT from hanging
    straight down (negative = in front of the body), elbow = how far the forearm bends back IN toward the body.
    -> (left arm, left elbow, right arm, right elbow, left leg, right leg, knee bend, body lean, drop 0..1)."""
    s = math.sin(ph)
    if action == "walk":
        return (10 + 8 * s, 15, 10 - 8 * s, 15, -22 * s, 22 * s, abs(s) * 20, -3, 0)
    if action == "carry":                                 # both forearms across the belly, holding the prop
        return (-15, 95, -15, 95, -20 * s, 20 * s, abs(s) * 16, -4, 0)
    if action == "run":
        return (35 + 15 * s, 80, 35 - 15 * s, 80, -40 * s, 40 * s, abs(s) * 45, -10, 0)
    if action == "eat":                                   # right hand up to the mouth and back
        k = (math.sin(t * 6) + 1) / 2
        return (10, 0, -15, 125 + 25 * k, 4, -4, 0, 0, 0)
    if action == "sick":                                  # hands on the belly, swaying
        return (12, 105, 12, 105, 6, -6, 10, 6 * math.sin(t * 3), 0)
    if action == "fall":
        return (70, 20, 70, 20, 20, -10, 10, 0, 1)
    if action == "point":
        return (8, 0, 95, 0, 4, -4, 0, 0, 0)
    if action == "cheer":
        k = math.sin(t * 8) * 10
        return (160 + k, -15, 160 - k, -15, 8, -8, 0, 0, 0)
    if action == "sit":
        return (15, 70, 15, 70, -85, -85, 90, 0, 0)
    if action == "shock":                                 # hands up beside the head
        return (140, -45, 140, -45, 12, -12, 0, -6, 0)
    if action == "wave":
        return (8, 0, 150, -30 + 40 * math.sin(t * 10), 4, -4, 0, 0, 0)
    if action == "talk":
        return (20 + 10 * math.sin(t * 4), 60, 20 + 10 * math.sin(t * 4 + 1), 60, 4, -4, 0, 0, 0)
    return (8, 0, 8, 0, 4, -4, 0, 0, 0)


def _limb(d, x, y, a1, l1, a2, l2, w, col):
    r1, r2 = math.radians(a1), math.radians(a1 + a2)
    x1, y1 = x + l1 * math.sin(r1), y + l1 * math.cos(r1)
    x2, y2 = x1 + l2 * math.sin(r2), y1 + l2 * math.cos(r2)
    d.line((x, y, x1, y1, x2, y2), fill=INK, width=int(w + 4), joint="curve")
    d.line((x, y, x1, y1, x2, y2), fill=col, width=int(w), joint="curve")
    return x2, y2


def person(who, action, t, unit, prop=None, phase=0.0):
    """One flat person as an RGBA image standing on its bottom centre. unit = the height of a grown-up in pixels."""
    spec = WHO.get(who, WHO["man"])
    h = unit * spec["h"]
    S = 2                                   # drawn at 2x and scaled down for clean edges
    Wp, Hp = int(h * 1.5 * S), int(h * 1.35 * S)
    im = Image.new("RGBA", (Wp, Hp), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    la, le, ra, re_, ll, rl, knee, lean, drop = _pose(action, t * (7 if action == "run" else 5) + phase, t)
    k = h * S
    head_r = k * 0.11 * (1.15 if who == "kid" else 1)
    leg = k * 0.42 * (0.9 if who == "kid" else 1)
    torso = k * 0.34
    cx, ground = Wp / 2, Hp - k * 0.04
    hip_y = ground - leg * math.cos(math.radians(knee * 0.3))
    sh_y = hip_y - torso
    lean_x = math.sin(math.radians(lean)) * torso
    pants = (60, 70, 100) if who != "kid" else (60, 80, 140)
    lw = k * 0.075
    for a, sign in ((ll, -1), (rl, 1)):            # legs
        fx, fy = _limb(d, cx + sign * k * 0.04, hip_y, a, leg * 0.52, -knee if a > 0 else knee * 0.4, leg * 0.5, lw, pants)
        d.ellipse((fx - lw * 0.9, fy - lw * 0.5, fx + lw * 0.9, fy + lw * 0.5), fill=INK)
    body = [(cx - k * 0.12, hip_y), (cx + k * 0.12, hip_y), (cx + k * 0.13 + lean_x, sh_y), (cx - k * 0.13 + lean_x, sh_y)]
    d.polygon(body, fill=spec["shirt"] + (255,), outline=INK, width=int(S * 2))
    if spec.get("coat"):
        d.line((cx + lean_x / 2, sh_y + 4, cx, hip_y), fill=INK, width=int(S * 2))
    sx = cx + lean_x
    hand = None
    for a, e, sign in ((la, le, -1), (ra, re_, 1)):   # arms (left first, then right; the prop goes in the right hand)
        # mirrored: "out" is -x for the left arm and +x for the right; the elbow bends back toward the body
        hx, hy = _limb(d, sx + sign * k * 0.12, sh_y + k * 0.03, sign * a, k * 0.20, -sign * e, k * 0.19, lw * 0.85,
                       spec["shirt"] if not spec.get("coat") else (250, 250, 250))
        d.ellipse((hx - lw * 0.55, hy - lw * 0.55, hx + lw * 0.55, hy + lw * 0.55), fill=spec["skin"] + (255,), outline=INK,
                  width=int(S * 1.5))
        if sign > 0:
            hand = (hx, hy)
    hx0, hy0 = sx, sh_y - head_r * 1.05
    face = spec["skin"] if action != "sick" else (170, 210, 140)
    d.ellipse((hx0 - head_r, hy0 - head_r, hx0 + head_r, hy0 + head_r), fill=face + (255,), outline=INK, width=int(S * 2))
    d.chord((hx0 - head_r, hy0 - head_r * 1.08, hx0 + head_r, hy0 + head_r * 0.5), 180, 360, fill=spec["hair"] + (255,),
            outline=INK, width=int(S * 2))
    if spec.get("long_hair"):
        d.rectangle((hx0 - head_r, hy0 - head_r * 0.1, hx0 - head_r * 0.7, hy0 + head_r * 1.1), fill=spec["hair"] + (255,))
        d.rectangle((hx0 + head_r * 0.7, hy0 - head_r * 0.1, hx0 + head_r, hy0 + head_r * 1.1), fill=spec["hair"] + (255,))
    if spec.get("cap"):
        d.chord((hx0 - head_r * 1.05, hy0 - head_r * 1.2, hx0 + head_r * 1.05, hy0 + head_r * 0.2), 180, 360, fill=(220, 60, 50, 255),
                outline=INK, width=int(S * 2))
    er = head_r * 0.12
    for ex in (-0.35, 0.35):
        d.ellipse((hx0 + ex * head_r - er, hy0 - er, hx0 + ex * head_r + er, hy0 + er), fill=INK)
    if action in ("shock", "fall"):
        d.ellipse((hx0 - er * 1.6, hy0 + head_r * 0.35, hx0 + er * 1.6, hy0 + head_r * 0.7), fill=INK)
    elif action in ("cheer", "talk", "eat"):
        d.chord((hx0 - head_r * 0.35, hy0 + head_r * 0.15, hx0 + head_r * 0.35, hy0 + head_r * 0.6), 0, 180, fill=INK)
    elif action == "sick":
        d.arc((hx0 - head_r * 0.3, hy0 + head_r * 0.35, hx0 + head_r * 0.3, hy0 + head_r * 0.75), 200, 340, fill=INK, width=int(S * 2))
    else:
        d.arc((hx0 - head_r * 0.3, hy0 + head_r * 0.1, hx0 + head_r * 0.3, hy0 + head_r * 0.5), 20, 160, fill=INK, width=int(S * 2))
    if prop and hand:
        ic = icons.icon(prop, int(k * (0.42 if action == "carry" else 0.26)))
        if ic is not None:
            px, py = (int(sx - ic.width / 2), int(sh_y + k * 0.02)) if action == "carry" else (int(hand[0] - ic.width / 2), int(hand[1] - ic.height * 0.8))
            im.alpha_composite(ic, (max(0, min(Wp - ic.width, px)), max(0, min(Hp - ic.height, py))))
    if drop:          # lying down: rotate on a canvas that grows to fit, then trim to the body
        im = im.rotate(-80 * drop, resample=Image.BICUBIC, expand=True)
        box = im.getbbox()
        if box:
            im = im.crop(box)
        return im.resize((max(1, im.width // S), max(1, im.height // S)), Image.LANCZOS)
    return im.resize((Wp // S, Hp // S), Image.LANCZOS)


# ------------------------------------------------------------------ scene
def draw(lay, card, t, t0, t1, size, bg, font_fn, pill_fn):
    """Draw one frame of a mini scene onto `lay` (RGBA, full frame). bg = the place picture (RGBA) or None."""
    W, H = size
    u = H / 1080.0
    f = max(0.0, min(1.0, (t - t0) / max(0.1, t1 - t0)))
    base = bg if bg is not None else backdrop(card.get("place", ""), size)
    z = 1.0 + 0.04 * f                       # a slow push-in so the scene breathes
    w2, h2 = W / z, H / z
    lay.alpha_composite(base.transform(size, Image.EXTENT, ((W - w2) / 2, (H - h2) / 2, (W + w2) / 2, (H + h2) / 2), Image.BILINEAR))
    d = ImageDraw.Draw(lay)
    actors = card.get("actors") or []
    n = max(1, len(actors))
    unit = H * (0.58 if n <= 2 else 0.48)
    ground = H * 0.90
    spread = min(W * 0.62, n * unit * 0.55)
    x_left = W * (0.36 if card.get("list") or card.get("monitor") else 0.5) - spread / 2
    tops = []
    for j, a in enumerate(actors):
        at = a.get("at", t0 + 0.15 * j)
        appear = max(0.0, min(1.0, (t - at) / 0.3))
        if appear <= 0:
            continue
        tl = t - at
        x = x_left + (spread * (j + 0.5) / n)
        if a["action"] in ("walk", "carry", "run"):        # walkers cross part of the frame
            speed = (0.10 if a["action"] != "run" else 0.22) * W
            x = x - speed * 0.8 + speed * tl / max(1.0, t1 - at) * 1.6
        im = person(a["who"], a["action"], tl, unit, a.get("prop"), phase=j * 1.3)
        y_off = (1 - appear) * 40 * u
        lay.alpha_composite(im, (int(x - im.width / 2), int(ground - im.height + y_off)))
        tops.append((x, ground - unit * WHO.get(a["who"], WHO["man"])["h"]))
        if card.get("count"):
            d.text((x, ground + 40 * u), str(j + 1), font=font_fn(L.TITLE_FONT, 56 * u), fill=L.YELLOW + (int(255 * appear),), anchor="mm")
    if card.get("say") and tops and t - t0 > 0.6:
        bx, by = tops[0][0] + unit * 0.30, tops[0][1] - 30 * u
        txt = str(card["say"]).upper()
        ft = font_fn(L.HAND_FONT, 64 * u)
        tw = d.textlength(txt, font=ft)
        a = max(0.0, min(1.0, (t - t0 - 0.6) / 0.25))
        d.rounded_rectangle((bx, by - 70 * u, bx + tw + 60 * u, by + 20 * u), radius=40 * u, fill=(255, 255, 255, int(240 * a)),
                            outline=INK, width=int(4 * u))
        d.polygon([(bx + 30 * u, by + 18 * u), (bx + 70 * u, by + 18 * u), (bx + 10 * u, by + 60 * u)], fill=(255, 255, 255, int(240 * a)))
        d.text((bx + 30 * u, by - 25 * u), txt, font=ft, fill=L.RED + (int(255 * a),), anchor="lm")
    if card.get("list"):
        y = H * (0.46 if card.get("monitor") else 0.30)    # under the monitor when there is one
        for j, item in enumerate(card["list"]):
            a = max(0.0, min(1.0, (t - t0 - 0.5 - 0.45 * j) / 0.3))
            if a <= 0:
                continue
            x = W * 0.66
            r = 28 * u
            d.ellipse((x - r, y - r, x + r, y + r), fill=L.RED + (int(255 * a),))
            d.line((x - r * .45, y - r * .45, x + r * .45, y + r * .45), fill=(255, 255, 255, int(255 * a)), width=int(7 * u))
            d.line((x + r * .45, y - r * .45, x - r * .45, y + r * .45), fill=(255, 255, 255, int(255 * a)), width=int(7 * u))
            d.text((x + r * 1.6, y), item.upper(), font=font_fn(L.TITLE_FONT, 60 * u), fill=(255, 255, 255, int(255 * a)), anchor="lm",
                   stroke_width=int(4 * u), stroke_fill=(20, 16, 16, int(255 * a)))
            y += 100 * u
    if card.get("monitor"):
        mx, my, mw, mh = W * 0.62, H * 0.12, W * 0.30, H * 0.22
        d.rounded_rectangle((mx, my, mx + mw, my + mh), radius=14 * u, fill=(20, 26, 30, 240), outline=(120, 130, 140, 255), width=int(6 * u))
        pts = []
        for i in range(60):
            xx = mx + 14 * u + (mw - 28 * u) * i / 59
            ph = (i / 59 * 3 + t * 1.4) % 1.0
            yy = my + mh * 0.55 - (mh * 0.35 if 0.45 < ph < 0.5 else (-mh * 0.12 if 0.5 < ph < 0.54 else 0))
            pts.append((xx, yy))
        d.line(pts, fill=(80, 230, 120, 255), width=int(5 * u))
    if card.get("label"):
        a = max(0.0, min(1.0, (t - t0 - 1.0) / 0.3))
        pill_fn(d, (W / 2, H * 0.08 + 0 * u), str(card["label"]).upper(), font_fn(L.TITLE_FONT, 50 * u), L.WHITE, L.RED + (int(255 * a),))
