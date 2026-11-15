"""Toon Tales action library (pure Python, no Blender): timed moves for any character in any story.

A *state* is everything a puppet needs for one frame:
  arm   [L, R] each [[ex, ez, ey], [hx, hz, hy]]   arm lengths from the shoulder (x out, z up), y metres or None
  foot  [L, R] each [fx, fz]                         leg lengths from the rest hip (fz -1 = floor)
  up    [dx, dz]  upper body offset m  (squat < 0)    head [dx, dz] extra head offset m
  tilt  lean degrees (+ = screen-right)              root [dx, dy, dz, roll_deg] whole-character offset
  eyes, mouth   face picture names
Static poses come from poses.json; actions are functions of local time that return a state.

    st = actions.state_at("walk", u, T, metrics, {"to": [1.5, 0]})
    st = actions.blend(a, b, k)

metrics (from puppet.metrics(ch)): arm_len, leg_len, shoulder_z, hip_z, head_r, body_w.
Every action lists: dur (default seconds), moves (True when it ends somewhere else), about (for the planner).
"""
import copy
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
POSES = json.loads((HERE / "poses.json").read_text())["poses"]
FOOT_REST = [[0.04, -1.0], [0.04, -1.0]]
NEUTRAL = {"up": [0.0, 0.0], "head": [0.0, 0.0], "tilt": 0.0, "root": [0.0, 0.0, 0.0, 0.0],
           "eyes": "open", "mouth": "X"}


def _arm(a):
    return [[float(v) for v in a[0][:2]] + [a[0][2] if len(a[0]) > 2 else None],
            [float(v) for v in a[1][:2]] + [a[1][2] if len(a[1]) > 2 else None]]


def pose(name):
    """Full state for a static pose (missing fields filled with neutral values)."""
    p = POSES[name]
    st = copy.deepcopy(NEUTRAL)
    st["arm"] = [_arm(p["arm"][0]), _arm(p["arm"][1])]
    st["foot"] = copy.deepcopy(p.get("foot", FOOT_REST))
    for k in ("up", "head"):
        if k in p:
            st[k] = list(p[k])
    st["tilt"] = float(p.get("tilt", 0.0))
    st["eyes"] = p.get("eyes", "open")
    st["mouth"] = p.get("mouth", "X")
    return st


def _num(a, b, k):
    if isinstance(a, list):
        return [_num(x, y, k) for x, y in zip(a, b)]
    if a is None or b is None:
        if a is None and b is None:
            return None
        a = -0.02 if a is None else a
        b = -0.02 if b is None else b
    return a + (b - a) * k


def blend(a, b, k):
    """Numeric blend a->b; faces switch at the halfway point."""
    k = max(0.0, min(1.0, k))
    out = {key: _num(a[key], b[key], k) for key in ("arm", "foot", "up", "head", "tilt", "root")}
    src = b if k >= 0.5 else a
    out["eyes"], out["mouth"] = src["eyes"], src["mouth"]
    return out


def smooth(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def _seg(u, t0, t1):
    return smooth((u - t0) / max(1e-6, t1 - t0))


# ---------------------------------------------------------------- actions


def _hold(name):
    def fn(u, T, m, p):
        return pose(p.get("pose", name))
    return fn


def _walk(freq, lift, lean, arm_swing, base="idle", eyes=None):
    def fn(u, T, m, p):
        st = pose(p.get("pose", base))
        to = p.get("to", [1.2, 0.0])
        # constant speed with soft start/stop
        ramp = min(0.25, T / 4)
        lin = (u - ramp / 2) / max(1e-6, T - ramp) if T > ramp else u / T
        k = smooth(lin) * 0.15 + max(0.0, min(1.0, lin)) * 0.85
        st["root"] = [to[0] * k, to[1] * k, 0.0, 0.0]
        moving = 0.0 < u < T
        ph = 2 * math.pi * freq * u
        if moving:
            for i, sgn in ((0, 1), (1, -1)):
                st["foot"][i][1] = -1.0 + lift * max(0.0, math.sin(ph) * sgn)
                st["arm"][i][1][1] += arm_swing * math.sin(ph) * -sgn
                st["arm"][i][0][1] += arm_swing * 0.5 * math.sin(ph) * -sgn
            st["up"][1] += 0.025 * abs(math.sin(ph)) - 0.012
            d = 1 if to[0] >= 0 else -1
            st["tilt"] = st["tilt"] + lean * d
        if eyes:
            st["eyes"] = eyes
        return st
    return fn


def _jump(u, T, m, p):
    h = p.get("height", 0.45)
    a, b = 0.28 * T, 0.78 * T
    if u < a:                                   # anticipation squat, arms back
        k = _seg(u, 0, a)
        st = blend(pose("idle"), pose("cower"), k * 0.5)
        st["up"][1] = -0.14 * k
        st["eyes"], st["mouth"] = "closed", "grit"
    elif u < b:                                 # in the air
        k = (u - a) / (b - a)
        st = pose("cheer")
        st["root"][2] = h * 4 * k * (1 - k)
        st["foot"] = [[0.10, -0.92], [0.10, -0.92]]
    else:                                       # land, squash, recover
        k = _seg(u, b, T)
        st = blend(pose("cheer"), pose("idle"), k)
        st["up"][1] = -0.12 * (1 - k)
        st["eyes"], st["mouth"] = "happy", "grin"
    return st


def _fall(u, T, m, p):
    side = 1 if p.get("side", "right") == "right" else -1
    a = 0.22 * T
    if u < a:                                   # flail
        st = pose("shock")
        w = math.sin(2 * math.pi * 7 * u) * 0.25
        st["arm"][0][1][1] += w
        st["arm"][1][1][1] -= w
        st["tilt"] = side * 10 * _seg(u, 0, a)
        return st
    k = min(1.0, ((u - a) / (0.45 * T)) ** 2)   # gravity: accelerate into the floor
    land = a + 0.45 * T
    st = pose("dizzy")
    st["foot"] = [[0.06, -1.0], [0.06, -1.0]]
    ang = 90 * k
    if u > land:                                # small bounce after the hit
        b = (u - land) / max(1e-6, T - land)
        ang = 90 - 6 * math.sin(math.pi * min(1.0, b * 2)) * (1 - b)
    st["root"] = [0.0, 0.0, m["head_r"] * math.sin(math.radians(ang)), side * ang]
    st["eyes"] = "shock" if k < 1 else "dizzy"
    return st


def _bonk(u, T, m, p):
    st = pose("dizzy")
    hit = 0.08
    if u < hit:
        k = u / hit
        st["up"][1] = -0.10 * k
        st["head"][1] = -0.05 * k
        st["eyes"], st["mouth"] = "shock", "grit"
    else:
        d = u - hit
        osc = math.exp(-5 * d) * math.cos(2 * math.pi * 3.5 * d)
        st["up"][1] = -0.10 * osc
        st["head"][1] = -0.05 * osc
        st["head"][0] = 0.02 * math.sin(2 * math.pi * 2 * d) * (1 - min(1, d / T))
        st["tilt"] = 6 * math.sin(2 * math.pi * 1.2 * d)
    return st


def _head_move(axis, amp, freq, base="idle"):
    def fn(u, T, m, p):
        st = pose(p.get("pose", base))
        env = math.sin(math.pi * min(1.0, u / T))
        st["head"][axis] += amp * math.sin(2 * math.pi * freq * u) * env
        if "eyes" in p:
            st["eyes"] = p["eyes"]
        return st
    return fn


def _laugh(u, T, m, p):
    st = pose(p.get("pose", "hips"))
    st["eyes"], st["mouth"] = "happy", "laugh"
    st["up"][1] += 0.018 * abs(math.sin(2 * math.pi * 4.5 * u))
    st["head"][1] += 0.012 * math.sin(2 * math.pi * 9 * u)
    st["tilt"] = -4 + 3 * math.sin(2 * math.pi * 1.1 * u)
    return st


def _throw(u, T, m, p):
    a, b = 0.55 * T, 0.72 * T
    wind = pose("idle")
    wind["arm"][1] = [[0.30, 0.30, 0.10], [0.05, 0.85, 0.12]]
    wind["tilt"] = -6
    wind["eyes"], wind["mouth"] = "angry", "grit"
    rel = pose("point")
    rel["arm"][1] = [[0.50, 0.05, -0.10], [0.98, 0.0, -0.25]]
    rel["tilt"] = 7
    rel["eyes"], rel["mouth"] = "wide", "o_shock"
    if u < a:
        return blend(pose("idle"), wind, _seg(u, 0, a * 0.8))
    if u < b:
        return blend(wind, rel, _seg(u, a, b))
    out = blend(rel, pose("point"), _seg(u, b, T) * 0.4)
    out["eyes"], out["mouth"] = "open", "smile"
    return out


def _pick_up(u, T, m, p):
    down = pose("idle")
    sq = 0.26
    down["up"][1] = -sq
    down["tilt"] = 4
    floor_dz = (0.10 - (m["shoulder_z"] - sq)) / m["arm_len"]
    down["arm"][1] = [[0.42, max(-0.6, floor_dz * 0.45)], [0.30, max(-1.0, floor_dz)]]
    down["foot"] = [[0.16, -1.0], [0.16, -1.0]]
    down["eyes"], down["mouth"] = "half", "flat"
    end = pose(p.get("end", "hold"))
    if u < 0.4 * T:
        return blend(pose("idle"), down, _seg(u, 0, 0.4 * T))
    if u < 0.55 * T:
        return down
    return blend(down, end, _seg(u, 0.55 * T, T))


def _scratch(u, T, m, p):
    st = pose("scratch")
    st["arm"][1][1][1] += 0.06 * math.sin(2 * math.pi * 6 * u)
    st["arm"][1][1][0] += 0.04 * math.cos(2 * math.pi * 6 * u)
    return st


def _tremble(u, T, m, p):
    st = pose(p.get("pose", "cower"))
    st["up"][0] += 0.012 * math.sin(2 * math.pi * 13 * u)
    st["head"][0] += 0.008 * math.sin(2 * math.pi * 11 * u + 1)
    return st


def _explain(u, T, m, p):
    """Talking gestures for narration-style lines: alternates open hands every ~0.8 s."""
    a, b = pose("present"), pose("explain")
    mirror = pose("present")
    mirror["arm"] = [copy.deepcopy(a["arm"][1]), copy.deepcopy(pose("idle")["arm"][1])]
    seq = [a, b, mirror, b]
    i = int(u / 0.8)
    k = smooth((u % 0.8) / 0.3)
    st = blend(seq[(i - 1) % 4] if i else pose("idle"), seq[i % 4], k)
    st["mouth"] = "X"
    return st


def _celebrate(u, T, m, p):
    st = pose("cheer")
    st["root"][2] = 0.10 * abs(math.sin(2 * math.pi * 1.8 * u))
    st["arm"][0][1][1] += 0.08 * math.sin(2 * math.pi * 3.6 * u)
    st["arm"][1][1][1] -= 0.08 * math.sin(2 * math.pi * 3.6 * u)
    return st


def _look_around(u, T, m, p):
    st = pose(p.get("pose", "sneak"))
    seq = ["look_l", "look_l", "look_r", "look_r", "up"]
    st["eyes"] = seq[min(len(seq) - 1, int(u / T * len(seq)))]
    st["head"][0] += 0.02 * math.sin(2 * math.pi * u / T * 1.5)
    return st


def _sigh(u, T, m, p):
    st = blend(pose("idle"), pose("sad"), _seg(u, 0.1 * T, 0.6 * T))
    st["up"][1] += 0.02 * math.sin(math.pi * min(1.0, u / (0.4 * T)))
    return st


ACTIONS = {
    # name: (function, default seconds, moves, about)
    "walk":        (_walk(1.9, 0.16, 3, 0.10), 1.6, True, "walk to a spot; params to=[dx, dy] metres"),
    "run":         (_walk(3.2, 0.28, 9, 0.22, base="sneak", eyes="wide"), 1.0, True, "run; params to=[dx, dy]"),
    "sneak_walk":  (_walk(1.2, 0.14, 2, 0.04, base="sneak"), 2.0, True, "tiptoe; params to=[dx, dy]"),
    "jump":        (_jump, 0.9, False, "jump on the spot; params height"),
    "celebrate":   (_celebrate, 1.4, False, "hop with both arms up"),
    "fall":        (_fall, 1.1, False, "fall over sideways and lie dizzy; params side=left|right"),
    "bonk":        (_bonk, 0.9, False, "hit on the head: squash, wobble, dizzy"),
    "nod":         (_head_move(1, 0.03, 2.6), 0.8, False, "nod yes; params pose"),
    "shake_head":  (_head_move(0, 0.035, 3.2), 0.9, False, "shake head no; params pose"),
    "laugh":       (_laugh, 1.2, False, "belly laugh; params pose"),
    "throw":       (_throw, 0.8, False, "wind up and throw with the right hand"),
    "pick_up":     (_pick_up, 1.3, False, "squat, grab from the floor, stand holding; params end"),
    "scratch_head": (_scratch, 1.0, False, "puzzled head scratch"),
    "tremble":     (_tremble, 1.0, False, "shake with fear; params pose"),
    "explain":     (_explain, 2.4, False, "open-hand talking gestures"),
    "look_around": (_look_around, 1.4, False, "glance left, right, up"),
    "sigh":        (_sigh, 1.2, False, "slump into sadness"),
}
HOLDS = set()  # names that only hold a static pose (they move while blending in, then stay still)
for _name in POSES:
    if _name not in ACTIONS:
        ACTIONS[_name] = (_hold(_name), 1.0, False, f"hold the '{_name}' pose")
        HOLDS.add(_name)


def state_at(name, u, T, m, params=None):
    fn = ACTIONS[name][0]
    st = fn(max(0.0, min(u, T)), T, m, params or {})
    st["arm"] = [_arm(a) for a in st["arm"]]  # always [x, z, y-or-None] per joint
    return st


def final_root(name, T, m, params=None):
    """Where an action leaves the character (dx, dy) — later actions start from there."""
    if not ACTIONS[name][2]:
        return 0.0, 0.0
    st = state_at(name, T, T, m, params)
    return st["root"][0], st["root"][1]
