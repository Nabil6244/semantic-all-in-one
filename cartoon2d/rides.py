"""Play rides for cartoon2d (Kids Channel 3 play adventures): slide, swing, train and ball pit.

A script line carries them as games (see games.py), timed from that line:
  {"type": "slide", "who": who}              hop up to the top of a slide beside them, sit, "wheee" down to their spot
  {"type": "swing", "who": who | [..]}        each sits on a swing at their spot and swings for the whole line
  {"type": "train", "who": [riders]}          a toy train chugs in from the left with the riders in its carriages,
                                              stops in the middle, then chugs off to the right (whole line);
                                              the riders leave with it, or with "off": true they hop back down to
                                              their spots before it leaves empty (the story goes on with them here)
  {"type": "pit",   "who": who | [..]}        each sinks into a ball pit at their spot, balls bounce up (whole line)
The rides are drawn in code in the show's flat style (bright fills, dark-brown outline), like the trampoline and toy box,
so their shape is exact: the rider follows the chute / the swing seat / the carriage.

render.py calls: place(G, t) after the positions are set (moves x / floor), pose(G, who, t, out, arm) in pose_at,
draw_back(...) before the characters and draw_front(...) right after each character.
"""
import math

from PIL import Image, ImageDraw

LINE = (70, 45, 30)
SLIDE_T = 3.4            # hop up 0.6, sit 0.5, slide 1.3, stand up 1.0
TRAIN_IN, TRAIN_OUT = 2.2, 2.0
HOP_OFF = 0.7            # riders hop down from their carriages before an "off" train leaves
TRAIN_BACK = 0.09        # the track runs a little behind the standing characters (they no longer look in its way)


def smooth(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


def plan_line(ev, g, lines, i, total):
    """games.plan hook: one ride event per rider (train: one event with all riders).
    "lines": n keeps a swing / pit / train going through the next n-1 lines too (the host talks over the ride)."""
    k = g["type"]
    ln = lines[i]
    who = g["who"] if isinstance(g["who"], list) else [g["who"]]
    t0 = ln["start"] + float(g.get("at", 0.0))
    n = max(1, int(g.get("lines", 1)))
    nxt = lines[i + n]["start"] if i + n < len(lines) else total
    if k == "slide":
        for w in who:
            ev["ride"].append({"kind": "slide", "who": w, "t0": t0, "t1": t0 + SLIDE_T})
    elif k == "train":
        t1 = max(nxt - 0.1, t0 + TRAIN_IN + TRAIN_OUT + 1.0)
        # riders are already aboard when a new place opens on this line; after the train leaves they are gone with it
        # until the next place (they used to pop back onto their spots)
        gone = next((l2["start"] - 0.45 for l2 in lines[i + 1:] if l2.get("place")), total + 1)
        off = bool(g.get("off"))
        ev["ride"].append({"kind": "train", "who": who, "t0": t0 - (0.5 if ln.get("place") else 0.2), "t1": t1,
                           "gone_until": 0 if off else gone, "off": off})
    else:                                               # swing / pit: the whole line, into the pause after it
        t1 = max(nxt - 0.1, t0 + 2.5)
        for w in who:
            ev["ride"].append({"kind": k, "who": w, "t0": t0 - 0.3, "t1": t1})


def sfx(ev):
    """Ride sounds for the mixer: whoosh down the slide, a soft whoosh at each swing, the train's bell + chuffs, ball pops."""
    out = []
    for r in ev.get("ride", []):
        if r["kind"] == "slide":
            out.append({"t": r["t0"] + 0.05, "name": "boing", "gain_db": -12})
            out.append({"t": r["t0"] + 1.1, "name": "whoosh", "gain_db": -6})
        elif r["kind"] == "swing":
            t = r["t0"] + 1.0
            while t < r["t1"] - 0.5:
                out.append({"t": t, "name": "whoosh", "gain_db": -17})
                t += 1.05
        elif r["kind"] == "train":
            out.append({"t": r["t0"] + 0.25, "name": "whistle", "gain_db": -9})
            out.append({"t": r["t0"] + TRAIN_IN, "name": "ding_3", "gain_db": -10})
            t = r["t0"] + 0.2
            while t < r["t1"]:
                moving = t < r["t0"] + TRAIN_IN or t > r["t1"] - TRAIN_OUT
                if moving:
                    out.append({"t": t, "name": "chuff", "gain_db": -13})
                t += 0.32
            out.append({"t": r["t1"] - TRAIN_OUT - 0.2, "name": "whistle", "gain_db": -10})
        elif r["kind"] == "pit":
            out.append({"t": r["t0"] + 0.35, "name": "burst", "gain_db": -12})
            t = r["t0"] + 0.9
            while t < r["t1"] - 0.3:
                out.append({"t": t, "name": "pop", "gain_db": -15})
                t += 0.55
    return out


def active(G, who, t):
    for r in (G.get("games") or {}).get("ride", []):
        if r["t0"] <= t <= r["t1"] and (who == r["who"] or (isinstance(r["who"], list) and who in r["who"])):
            return r
    return None


def hip_h(G, w):
    """Hip height above the feet (world px): sitting puts the hips on the seat, the thighs toward the camera."""
    c = G["cast"][w]
    rig = c["rig"]
    legs = rig.get("legs") or {}
    if "sl" not in legs:
        return 0.42 * _ch(G, w)
    return (rig["feet"][1] - legs["sl"]["H"][1]) * c["k"]


def slide_sit(a):
    return smooth((a - 0.45) / 0.3) * (1 - smooth((a - 2.4) / 0.4))


def _ch(G, w):
    c = G["cast"][w]
    return c["char_h"] * c["k"]


# ------------------------------------------------------------------ geometry (world px)
def slide_geo(X, F, ch):
    top = (X - 0.95 * ch, F - 0.72 * ch)               # where the chute starts (platform edge)
    bot = (X - 0.05 * ch, F - 0.07 * ch)
    return top, bot


def chute(top, bot, s):
    """Point on the chute at s (0 top .. 1 bottom): steep first, flat at the end."""
    x = top[0] + (bot[0] - top[0]) * s
    y = top[1] + (bot[1] - top[1]) * (1 - (1 - s) ** 2)
    return x, y


def swing_geo(X, F, ch, t, r):
    P = (X, F - 1.32 * ch)
    L = 1.02 * ch
    q = smooth((t - r["t0"]) / 1.2) * (1 - smooth((t - r["t1"] + 0.9) / 0.9))
    th = math.radians(24) * q * math.sin(2 * math.pi * (t - r["t0"]) / 2.1)
    seat = (P[0] + L * math.sin(th), P[1] + L * math.cos(th))
    return P, L, th, seat


def train_x(G, r, t, world_w):
    """Front of the engine (world x) at t: in from the left, stop with the riders in the middle, off to the right."""
    riders = r["who"]
    xs = [G["places_spots"][w] for w in riders]
    chm = max(_ch(G, w) for w in riders)
    car = 0.82 * chm
    stop = sum(xs) / len(xs) + (len(riders) / 2) * car + 0.55 * chm          # riders' cars centred on their spots
    start, end = -0.2 * world_w, 1.6 * world_w
    a = t - r["t0"]
    b = r["t1"] - t
    if a < TRAIN_IN:
        q = smooth(a / TRAIN_IN)
        return start + (stop - start) * (1 - (1 - q) ** 2), chm, car
    if b < TRAIN_OUT:
        q = 1 - b / TRAIN_OUT
        return stop + (end - stop) * q * q, chm, car
    return stop, chm, car


# ------------------------------------------------------------------ positions + poses
def place(G, t, world_w):
    """Move riders: x and floor follow the ride (called each frame after x_at / set_place)."""
    G.setdefault("places_spots", {})
    for w in G["cast"]:
        G["places_spots"][w] = G["cast"][w]["x"]
        G["cast"][w]["_floor0"] = G["cast"][w]["floor"]
    for r in (G.get("games") or {}).get("ride", []):
        if r["kind"] == "train" and r["t1"] < t < r.get("gone_until", 0):
            for w in r["who"]:                          # rode away: off the stage until the next place
                G["cast"][w]["x"] = 3 * world_w
            continue
        if not (r["t0"] <= t <= r["t1"]):
            continue
        if r["kind"] == "train":
            fx, chm, car = train_x(G, r, t, world_w)
            left = r["t1"] - TRAIN_OUT - t                  # time until it pulls away
            if r.get("off") and left < 0:
                continue                                    # hopped off: standing on their own spots again
            for i, w in enumerate(r["who"]):
                c = G["cast"][w]
                X, F = c["x"], c["floor"]
                cx, cy = fx - 1.1 * chm - (i + 0.5) * car, F - (0.12 + TRAIN_BACK) * chm   # on the carriage floor
                if r.get("off") and left < HOP_OFF:     # a cartoon hop down to their spot
                    q = smooth(1 - left / HOP_OFF)
                    c["x"] = cx + (X - cx) * q
                    c["floor"] = cy + (F - cy) * q - math.sin(math.pi * q) * 0.3 * chm
                else:
                    c["x"], c["floor"] = cx, cy
            continue
        w = r["who"]
        c = G["cast"][w]
        ch, X, F = _ch(G, w), c["x"], c["floor"]
        a = t - r["t0"]
        if r["kind"] == "slide":
            top, bot = slide_geo(X, F, ch)
            sitd = slide_sit(a) * 0.92 * hip_h(G, w)          # sitting: the hips come down onto the chute
            if a < 0.6:                                 # a big cartoon hop up to the top
                q = smooth(a / 0.6)
                c["x"] = X + (top[0] - X) * q
                c["floor"] = F + (top[1] - F) * q - math.sin(math.pi * q) * 0.35 * ch
            elif a < 1.1:
                c["x"], c["floor"] = top[0], top[1] + sitd
            elif a < 2.4:
                s = ((a - 1.1) / 1.3) ** 1.6
                x, y = chute(top, bot, s)
                c["x"], c["floor"] = x, y + sitd
            else:
                q = smooth((a - 2.4) / 0.5)
                c["x"], c["floor"] = bot[0] + 0.05 * ch * q, bot[1] + (F - bot[1]) * q + sitd
        elif r["kind"] == "swing":
            P, L, th, seat = swing_geo(X, F, ch, t, r)
            c["x"], c["floor"] = seat[0], seat[1] + 0.9 * hip_h(G, w) * smooth(a / 0.4)
        elif r["kind"] == "pit":
            q = smooth(a / 0.6) * (1 - smooth((t - r["t1"] + 0.5) / 0.5))
            c["floor"] = F + (0.28 + 0.04 * math.sin(2 * math.pi * 1.6 * a)) * ch * q


def pose(G, who, t, out, arm):
    """Ride poses on top of the act: sitting on the slide / swing, hands up on the way down, holding the chains."""
    r = active(G, who, t)
    if not r:
        return
    a = t - r["t0"]
    if r["kind"] == "slide":
        sit = slide_sit(a)
        out["hop"] = 0.0
        out["squat"] = out["squat"] * (1 - sit)
        for sd in ("sl", "sr"):                         # thighs toward the camera, shins hanging: sitting, seen from the front
            out[f"f_{sd}"] = 0.8 * sit
            out[f"h_{sd}"] = out[f"h_{sd}"] * (1 - sit)
            out[f"k_{sd}"] = out[f"k_{sd}"] * (1 - sit)
        if 1.1 <= a < 2.6:
            for k, v in {**arm("sl", 150, 15), **arm("sr", 150, 15)}.items():
                out[k] = v
        out["lean"] = out.get("lean", 0.0) + 10 * sit * (1 if 1.1 <= a < 2.4 else 0.3)
    elif r["kind"] == "swing":
        c = G["cast"][who]
        P, L, th, seat = swing_geo(0.0, 0.0, c["char_h"] * c["k"], t, r)          # only the angle is used here
        q = smooth(a / 0.4)
        out["hop"] = 0.0
        out["squat"] = out["squat"] * (1 - q)
        for sd in ("sl", "sr"):
            out[f"f_{sd}"] = 0.8 * q
            out[f"h_{sd}"] = (1 if sd == "sr" else -1) * 4 * math.sin(2 * math.pi * (t - r["t0"]) / 2.1) * q   # little leg kicks
        out["sway"] = out.get("sway", 0.0) - math.degrees(th) * 0.9
        for k, v in {**arm("sl", 28, 112), **arm("sr", 28, 112)}.items():
            out[k] = out[k] + (v - out[k]) * q
    elif r["kind"] == "train":
        if r.get("off") and r["t1"] - t < TRAIN_OUT + HOP_OFF:
            return                                      # hopping off / off: their own act
        out["hop"] = 0.0
        out["squat"] = 0.0
        if r["t1"] - t < TRAIN_OUT or t - r["t0"] < TRAIN_IN:                       # waving while it moves
            sd = "sr"
            for k, v in arm(sd, 150, 25 + 20 * math.sin(2 * math.pi * 2.4 * t)).items():
                out[k] = v
    elif r["kind"] == "pit":
        out["hop"] = min(out["hop"], 0.02)


# ------------------------------------------------------------------ drawing
def _pad(d, box, r, fill, lw):
    d.rounded_rectangle(box, radius=r, fill=fill, outline=LINE, width=lw)


def stay(G, t):
    """(arrive, leave) of the place stay that holds t (from render's place_changes)."""
    ch = sorted(G.get("place_changes") or [(0.0, None)])
    a = max([tc for tc, _ in ch if tc <= t] or [0.0])
    b = min([tc for tc, _ in ch if tc > t] or [1e9])
    return a, b


def _frames_now(G, t):
    """The slide / swing rides whose frame stands in the current place at t: one per (rider, kind), the one that is
    riding now if any, else the stay's first (a swing then hangs still)."""
    a, b = stay(G, t)
    pick = {}
    for r in (G.get("games") or {}).get("ride", []):
        if r["kind"] not in ("slide", "swing") or not (a <= r["t0"] < b):
            continue
        key = (r["who"], r["kind"])
        if key not in pick or (r["t0"] <= t <= r["t1"] + 0.4):
            pick[key] = r
    return list(pick.values())


def anchor(G, kind, who, t):
    """World point (bottom centre) for a goal item that sits ON a ride frame: the slide's platform (the rider who goes
    up takes it along: on their lap down the chute, then beside them at the bottom), or under the swing frame."""
    c = G["cast"][who]
    ch, X, F = _ch(G, who), G["places_spots"][who], c["_floor0"]
    if kind == "slide":
        a, b = stay(G, t)
        rs = [r for r in (G.get("games") or {}).get("ride", []) if r["kind"] == "slide" and r["who"] == who
              and a <= r["t0"] <= t]
        if rs:
            r = rs[-1]
            if t <= r["t1"] and t - r["t0"] > 0.6:              # picked up at the top, held on the lap
                return c["x"] + 0.12 * ch, c["floor"] - 0.28 * ch
            if t > r["t1"]:                                     # down safe, beside the rider
                return X + 0.3 * ch, F
        top, _ = slide_geo(X, F, ch)
        return top[0] - 0.16 * ch, top[1] - 0.02 * ch
    return X + 0.55 * ch, F                                     # under the swing frame, past the seat's reach


def _left_train(r, t):
    """An "off" train after its riders hopped down: its empty carriages go behind everybody."""
    return r["kind"] == "train" and r.get("off") and r["t1"] - t < TRAIN_OUT + 0.5 * HOP_OFF


def draw_back(frame, G, t, z, x0, y0):
    """Slide and swing frames (behind the characters). They are the place's play things, so they stand there for the
    whole stay in that place (a slide is there before anyone slides down it); one frame per rider and ride.
    Also the empty carriages of an "off" train pulling away."""
    for r in (G.get("games") or {}).get("ride", []):
        if r["kind"] == "train" and r["t0"] <= t <= r["t1"] and _left_train(r, t):
            S = lambda p: ((p[0] - x0) * z, (p[1] - y0) * z)    # noqa: E731
            layer = Image.new("RGBA", frame.size, (0, 0, 0, 0))
            d = ImageDraw.Draw(layer)
            for w in r["who"]:
                ch = _ch(G, w)
                _front(d, G, r, w, G["cast"][w], ch, S, max(3, int(ch * z * 0.012)), t, z)
            frame.alpha_composite(layer)
    for r in _frames_now(G, t):
        w = r["who"]
        c = G["cast"][w]
        ch, X, F = _ch(G, w), G["places_spots"][w], c["_floor0"]
        fade = 1.0
        S = lambda p: ((p[0] - x0) * z, (p[1] - y0) * z)            # noqa: E731
        lw = max(3, int(ch * z * 0.012))
        layer = Image.new("RGBA", frame.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        if r["kind"] == "slide":
            top, bot = slide_geo(X, F, ch)
            px = top[0] - 0.28 * ch
            # ladder: two rails + rungs, platform with a little rail
            for rx in (px - 0.07 * ch, px + 0.07 * ch):
                a_, b_ = S((rx, top[1] - 0.02 * ch)), S((rx, F))
                d.line([a_, b_], fill=LINE, width=lw * 3)
                d.line([a_, b_], fill=(60, 160, 240), width=lw)
            for k in range(1, 6):
                y = top[1] + (F - top[1]) * k / 6
                d.line([S((px - 0.07 * ch, y)), S((px + 0.07 * ch, y))], fill=LINE, width=lw * 2)
            _pad(d, [*S((px - 0.12 * ch, top[1] - 0.02 * ch)), *S((top[0] + 0.04 * ch, top[1] + 0.06 * ch))], lw, (255, 205, 40), lw)
            # chute: a thick yellow band with red sides, following the curve
            _chute(d, S, top, bot, ch, lw, False)
            # legs under the chute
            for s in (0.35, 0.75):
                x, y = chute(top, bot, s)
                d.line([S((x, y + 0.04 * ch)), S((x, F))], fill=LINE, width=lw * 3)
                d.line([S((x, y + 0.04 * ch)), S((x, F))], fill=(60, 160, 240), width=lw)
        else:
            P, L, th, seat = swing_geo(X, F, ch, t, r)
            bx0, bx1 = X - 0.75 * ch, X + 0.75 * ch
            for x in (bx0, bx1):                        # A-frame legs
                for dxl in (-0.22, 0.22):
                    d.line([S((x, P[1])), S((x + dxl * ch, F))], fill=LINE, width=lw * 3)
                    d.line([S((x, P[1])), S((x + dxl * ch, F))], fill=(60, 180, 90), width=lw)
            _pad(d, [*S((bx0 - 0.04 * ch, P[1] - 0.035 * ch)), *S((bx1 + 0.04 * ch, P[1] + 0.035 * ch))], lw * 2, (240, 70, 70), lw)
        if fade < 1:
            layer.putalpha(layer.getchannel("A").point(lambda v: int(v * fade)))
        frame.alpha_composite(layer)


def _chute(d, S, top, bot, ch, lw, front):
    """The chute band; in front of a sitting rider it is a deep side wall that hides the legs (sitting IN the slide)."""
    pts = [chute(top, bot, i / 24) for i in range(25)]
    up = [S((x, y - 0.035 * ch)) for x, y in pts]
    dn = [S((x, y + (0.2 if front else 0.045) * ch)) for x, y in pts]
    d.polygon(up + dn[::-1], fill=(240, 70, 70), outline=LINE, width=lw)
    d.line(up, fill=(255, 220, 90), width=max(2, int(lw * 1.6)))
    if front:
        d.line([S((x, y + 0.08 * ch)) for x, y in pts], fill=(200, 50, 55), width=max(2, lw))


def draw_front(frame, G, who, t, z, x0, y0):
    """In front of the rider: swing chains + seat, the ball pit's front wall, the train carriage (and the engine)."""
    r = active(G, who, t)
    if not r or _left_train(r, t):
        return
    c = G["cast"][who]
    ch = _ch(G, who)
    S = lambda p: ((p[0] - x0) * z, (p[1] - y0) * z)            # noqa: E731
    lw = max(3, int(ch * z * 0.012))
    layer = Image.new("RGBA", frame.size, (0, 0, 0, 0))           # own layer: the smoke is see-through
    d = ImageDraw.Draw(layer)
    _front(d, G, r, who, c, ch, S, lw, t, z)
    frame.alpha_composite(layer)


def _front(d, G, r, who, c, ch, S, lw, t, z):
    if r["kind"] == "slide":
        a = t - r["t0"]
        if 0.45 < a < 2.7:                              # sitting on it: the side wall in front of the legs
            top, bot = slide_geo(G["places_spots"][who], c["_floor0"], ch)
            _chute(d, S, top, bot, ch, lw, True)
            px = top[0] - 0.28 * ch
            _pad(d, [*S((px - 0.12 * ch, top[1] - 0.02 * ch)), *S((top[0] + 0.04 * ch, top[1] + 0.2 * ch))], lw, (255, 205, 40), lw)
        return
    if r["kind"] == "swing":
        X, F = G["places_spots"][who], c["_floor0"]
        P, L, th, seat = swing_geo(X, F, ch, t, r)
        ux, uy = math.cos(th), -math.sin(th)
        for s_ in (-1, 1):
            top = (P[0] + s_ * 0.24 * ch, P[1])
            end = (seat[0] + s_ * 0.24 * ch * ux, seat[1] + s_ * 0.24 * ch * uy)
            d.line([S(top), S(end)], fill=LINE, width=lw * 2)
            d.line([S(top), S(end)], fill=(200, 200, 210), width=max(2, lw // 2))
        a_ = (seat[0] - 0.3 * ch * ux, seat[1] - 0.3 * ch * uy)
        b_ = (seat[0] + 0.3 * ch * ux, seat[1] + 0.3 * ch * uy)
        d.line([S(a_), S(b_)], fill=LINE, width=int(lw * 4.5))
        d.line([S(a_), S(b_)], fill=(255, 150, 40), width=int(lw * 2.5))
    elif r["kind"] == "pit":
        X, F = G["places_spots"][who], c["_floor0"]
        a = t - r["t0"]
        q = smooth(a / 0.4) * (1 - smooth((t - r["t1"]) / 0.4))
        if q <= 0:
            return
        w, h = 0.95 * ch, 0.36 * ch
        others = [G["places_spots"][r2["who"]] for r2 in (G.get("games") or {}).get("ride", [])
                  if r2["kind"] == "pit" and r2["who"] != who and r2["t0"] <= t <= r2["t1"]]
        if others:                                      # pits side by side never overlap
            w = min(w, 0.96 * min(abs(o - X) for o in others))
        cols = [(240, 70, 70), (60, 150, 240), (255, 205, 40), (70, 190, 90), (190, 100, 220), (255, 140, 40)]
        rnd = (hash(who) % 97) / 97.0
        top = F - h
        # balls heaped on top (in front of the rider's waist), then the padded wall
        for i in range(26):
            u = ((i * 0.618 + rnd) % 1.0)
            bx = X - w * 0.46 + w * 0.92 * u
            by = top - 0.02 * ch - 0.06 * ch * math.sin(math.pi * u) * (1 + 0.15 * math.sin(2 * math.pi * (1.3 * a + u)))
            rr = 0.055 * ch * z
            p = S((bx, by))
            d.ellipse([p[0] - rr, p[1] - rr, p[0] + rr, p[1] + rr], fill=cols[i % len(cols)], outline=LINE, width=max(2, lw // 2))
        for j in range(5):                              # balls popping up
            ph = (a * 0.9 + j / 5.0) % 1.0
            bx = X - w * 0.35 + w * 0.7 * ((j * 0.37 + rnd) % 1.0)
            by = top - 0.05 * ch - math.sin(math.pi * ph) * 0.45 * ch
            rr = 0.05 * ch * z
            p = S((bx, by))
            d.ellipse([p[0] - rr, p[1] - rr, p[0] + rr, p[1] + rr], fill=cols[(j + 2) % len(cols)], outline=LINE, width=max(2, lw // 2))
        _pad(d, [*S((X - w / 2, top)), *S((X + w / 2, F + 0.02 * ch))], int(0.06 * ch * z), (60, 150, 240), lw)
        _pad(d, [*S((X - w / 2 - 0.02 * ch, top - 0.03 * ch)), *S((X + w / 2 + 0.02 * ch, top + 0.06 * ch))], int(0.04 * ch * z), (255, 205, 40), lw)
    elif r["kind"] == "train":
        fx, chm, car = train_x(G, r, t, 2560)
        i = r["who"].index(who)
        F = c["_floor0"] - TRAIN_BACK * chm
        cx = fx - 1.1 * chm - (i + 0.5) * car
        h = 0.42 * ch                                   # waist-high on its rider (toddlers showed only their heads)
        cols = [(240, 70, 70), (60, 150, 240), (255, 205, 40), (70, 190, 90)]
        body = [*S((cx - car * 0.46, F - h - 0.12 * chm)), *S((cx + car * 0.46, F - 0.12 * chm))]
        _pad(d, body, int(0.04 * chm * z), cols[i % len(cols)], lw)
        d.line([S((cx - car * 0.42, F - h - 0.06 * chm)), S((cx + car * 0.42, F - h - 0.06 * chm))], fill=(255, 255, 255), width=lw)
        _wheels(d, S, cx, F, chm, car, t, fx, lw)
        if i < len(r["who"]) - 1:                       # coupling to the next carriage
            d.line([S((cx - car * 0.5, F - 0.2 * chm)), S((cx - car * 0.46, F - 0.2 * chm))], fill=LINE, width=lw * 2)
        if i == 0:                                      # the engine, in front of the first carriage
            _engine(d, S, fx, F, chm, t, lw, z)


def _wheels(d, S, cx, F, chm, car, t, fx, lw):
    rr = 0.1 * chm
    for wx in (cx - car * 0.27, cx + car * 0.27):
        p = S((wx, F - rr))
        R_ = (S((wx + rr, F))[0] - p[0])
        d.ellipse([p[0] - R_, p[1] - R_, p[0] + R_, p[1] + R_], fill=(60, 60, 70), outline=LINE, width=lw)
        ang = fx / max(rr, 1)
        d.line([p, (p[0] + R_ * 0.8 * math.cos(ang), p[1] + R_ * 0.8 * math.sin(ang))], fill=(220, 220, 230), width=max(2, lw // 2))


def _engine(d, S, fx, F, chm, t, lw, z):
    L_ = 1.0 * chm
    x1 = fx - 0.05 * chm
    x0 = x1 - L_
    _pad(d, [*S((x0, F - 0.62 * chm)), *S((x0 + 0.38 * L_, F - 0.12 * chm))], int(0.03 * chm * z), (240, 70, 70), lw)      # cab
    _pad(d, [*S((x0 + 0.02 * L_, F - 0.5 * chm)), *S((x0 + 0.34 * L_, F - 0.36 * chm))], int(0.02 * chm * z), (190, 230, 255), lw)  # window
    _pad(d, [*S((x0 - 0.04 * L_, F - 0.68 * chm)), *S((x0 + 0.42 * L_, F - 0.6 * chm))], int(0.02 * chm * z), (60, 150, 240), lw)   # roof
    _pad(d, [*S((x0 + 0.36 * L_, F - 0.4 * chm)), *S((x1, F - 0.12 * chm))], int(0.08 * chm * z), (60, 150, 240), lw)      # boiler
    _pad(d, [*S((x0 + 0.72 * L_, F - 0.58 * chm)), *S((x0 + 0.84 * L_, F - 0.4 * chm))], int(0.02 * chm * z), (60, 60, 70), lw)  # chimney
    p = S((x1, F - 0.27 * chm))
    rr = 0.05 * chm * z
    d.ellipse([p[0] - rr, p[1] - rr, p[0] + rr, p[1] + rr], fill=(255, 220, 90), outline=LINE, width=lw)                 # lamp
    for wx in (x0 + 0.2 * L_, x0 + 0.55 * L_, x0 + 0.85 * L_):
        _wheels(d, S, wx, F, chm, 0.0, t, fx, lw)
    for k in range(4):                                  # smoke puffs drifting back
        ph = (t * 1.2 + k / 4.0) % 1.0
        sx = x0 + 0.78 * L_ - ph * 0.9 * chm
        sy = F - 0.62 * chm - ph * 0.45 * chm
        rr = (0.06 + 0.08 * ph) * chm * z
        q = S((sx, sy))
        a = int(230 * (1 - ph))
        d.ellipse([q[0] - rr, q[1] - rr, q[0] + rr, q[1] + rr], fill=(245, 245, 250, a))
