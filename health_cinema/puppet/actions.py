"""Action clips for the paper-cutout puppets: pure pose generators, no drawing.

A pose is a flat dict of joint angles in degrees (limbs: 0 = hanging straight down, positive = swung forward; lean/head: positive = forward) plus a few
layout keys: hip_x, hip_h (ground frame, units), squash, xscale, head_xs, torso_xs (torso twist), sh_dx/sh_dy (shoulder offset: shoulder rotation / shrug),
coat, scarf, speed, prop {name, mode, x, y}, seat {x, y}.
Legs a/b are the far/near side (suffix a/b): tha/sha/fta thigh/shin/foot, uaa/faa/haa upper arm/forearm/hand.
Cyclic actions (walk, run, walk_phone, carry_box_walk) take a phase in cycles: pass `phase` to tie the feet to a world distance, or leave None to drive them
by time; stride() says how many world units one cycle covers (the renderer scrolls the ground by that so the planted foot never slides).
Motion principles used throughout: ease in/out, anticipation before big moves, overshoot + settle after them (spring), secondary parts (head, forearm,
hand) lag the part that drives them (follow-through), weight shows as a hip dip + a little squash at each footfall.
"""
from __future__ import annotations
import math
from typing import Callable, Dict, Optional

PROP_DIMS = {"box": (118, 86), "parcel": (96, 62), "briefcase": (82, 72), "phone": (22, 44), "stool": (130, 16), "clipboard": (46, 64), "newspaper": (70, 54)}
CARRY = ("box", "parcel")
HELD = ("briefcase", "phone", "clipboard", "newspaper")
DEFAULT_D = dict(thigh=118, shin=114, foot_h=22, foot_len=70, torso=160, sh_frac=0.9, uarm=90, farm=80, hand=38, neck=14, hr=45)
BASE = dict(hip_x=0.0, lean=0.0, head=0.0, head_xs=1.0, tha=0.0, sha=0.0, fta=0.0, thb=0.0, shb=0.0, ftb=0.0, uaa=0.0, faa=0.0, haa=0.0,
            uab=0.0, fab=0.0, hab=0.0, squash=0.0, xscale=1.0, torso_xs=1.0, sh_dx=0.0, sh_dy=0.0, coat=0.0, scarf=0.0, speed=0.0)
sin, cos, rad, deg, pi = math.sin, math.cos, math.radians, math.degrees, math.pi


def clamp01(u): return min(1.0, max(0.0, u))
def ease(u): u = clamp01(u); return u * u * (3 - 2 * u)
def ease_io(u): u = clamp01(u); return 4 * u ** 3 if u < 0.5 else 1 - (-2 * u + 2) ** 3 / 2
def spring(u, f=0.95, damp=4.2):
    """0 -> 1 with overshoot and a settle (damped spring); u in 0..1."""
    u = ease(clamp01(u))
    return 1.0 if u >= 1 else 1 - math.exp(-damp * u) * cos(2 * pi * f * u) * (1 - u ** 8)
def lerp(a, b, k): return a + (b - a) * k
def base_pose(): return dict(BASE)


def keys(u, kf, fn=ease):
    """Piecewise value over keyframes [(u, v), ...] with `fn` easing inside each segment."""
    if u <= kf[0][0]: return kf[0][1]
    for (u0, v0), (u1, v1) in zip(kf, kf[1:]):
        if u <= u1: return lerp(v0, v1, fn((u - u0) / max(1e-6, u1 - u0)))
    return kf[-1][1]


def blend(p0: dict, p1: dict, k: float) -> dict:
    out = dict(p1 if k >= 0.5 else p0)
    for key, v in p0.items():
        w = p1.get(key)
        if isinstance(v, (int, float)) and isinstance(w, (int, float)): out[key] = lerp(v, w, k)
    return out


def ik2(a, b, dx, dy, bend=1):
    """Two-bone IK: root at origin, target (dx, dy) with y down. Returns (upper, lower) absolute angles from straight down, degrees."""
    r = min(max(math.hypot(dx, dy), abs(a - b) + 1e-3), a + b - 1e-3)
    th = math.atan2(dx, dy) + bend * math.acos(max(-1, min(1, (a * a + r * r - b * b) / (2 * a * r))))
    kx, ky = a * sin(th), a * cos(th)
    return deg(th), deg(math.atan2(dx - kx, dy - ky))


def leg_len(d): return d["thigh"] + d["shin"]
def stand_h(d): return 0.975 * leg_len(d) + d["foot_h"]


def shoulder_pos(d, pose):
    l = rad(pose["lean"]); fr = d["torso"] * d["sh_frac"]
    return pose["hip_x"] + 4 * cos(l) + fr * sin(l) + pose.get("sh_dx", 0.0), -pose["hip_h"] - fr * cos(l) + 4 * sin(l) + pose.get("sh_dy", 0.0)


def head_pos(d, pose):
    """Approximate chin / face-front point (ground frame) for hand-to-face gestures."""
    l = rad(pose["lean"]); T = d["torso"] + d["neck"] + d["hr"] * 0.62
    return pose["hip_x"] + T * sin(l) + d["hr"] * 0.72 + 6, -pose["hip_h"] - T * cos(l) + 10


def stand_legs(d, pose, h, hip_x=0.0, fa=-13.0, fb=15.0, lift_a=0.0, lift_b=0.0):
    pose["hip_x"], pose["hip_h"] = hip_x, h
    dy = h - d["foot_h"]
    pose["tha"], pose["sha"] = ik2(d["thigh"], d["shin"], fa - hip_x, dy - lift_a)
    pose["thb"], pose["shb"] = ik2(d["thigh"], d["shin"], fb - hip_x, dy - lift_b)
    return pose


def arm_to(d, pose, side, sx, sy, wx, wy, bend=-1):
    pose["ua" + side], pose["fa" + side] = ik2(d["uarm"], d["farm"], wx - sx, wy - sy, bend)


def carry_arms(d, pose, name):
    sx, sy = shoulder_pos(d, pose); bw, bh = PROP_DIMS[name]
    cx, cy = sx + 14 + bw / 2, sy + bh * 0.55
    arm_to(d, pose, "b", sx, sy, cx - 20, cy + bh * 0.3); arm_to(d, pose, "a", sx, sy, cx + 5, cy + bh * 0.26)
    pose["hab"] = pose["haa"] = 10
    pose["prop"] = dict(name=name, mode="at", x=cx, y=cy)


def apply_prop(d, pose, p, swing=0.3):
    name = p.get("prop")
    if not name: return pose
    if name in CARRY: carry_arms(d, pose, name)
    elif name == "briefcase":
        pose["uab"] = 3 + swing * 0.3 * pose["uab"]; pose["fab"] = pose["uab"] + 6; pose["prop"] = dict(name=name, mode="hand")
    elif name == "phone":
        pose["uab"], pose["fab"], pose["hab"] = 52, 138, 8; pose["prop"] = dict(name=name, mode="hand", follow=True)
    elif name == "clipboard":       # held against the chest with the near hand, other arm relaxed
        pose["uab"], pose["fab"], pose["hab"] = 34, 112, -4; pose["prop"] = dict(name=name, mode="hand", follow=True)
    elif name == "newspaper":       # folded, held out in front to read
        pose["uab"], pose["fab"], pose["hab"] = 44, 100, -8; pose["uaa"], pose["faa"] = 30, 96
        pose["prop"] = dict(name=name, mode="hand", follow=True)
    return pose


# ---- gaits
def gait(d, ph, duty, s, dy0, bob, lift, air_amp=0.0, hx=0.0, dip=0.0):
    a, b, fh = d["thigh"], d["shin"], d["foot_h"]
    pose = base_pose()
    dy = dy0 + bob * (0.5 + 0.5 * cos(4 * pi * (ph - duty / 2))) - dip
    m = -s * (1 - duty) / duty
    pose["hip_x"] = hx
    for key, off in (("b", 0.0), ("a", 0.5)):
        u = (ph + off) % 1.0
        if u < duty: x, y, ang = s / 2 - s * u / duty, 0.0, 0.0
        else:
            w = (u - duty) / (1 - duty)
            x = (2 * w**3 - 3 * w**2 + 1) * (-s / 2) + (w**3 - 2 * w**2 + w) * m + (-2 * w**3 + 3 * w**2) * (s / 2) + (w**3 - w**2) * m
            y = lift * sin(pi * w) ** 1.1
            ang = -26 * (1 - w) ** 3 * min(1.0, w * 6) + 70 * w * w * (1 - w)
            f_ = rad(ang); y = max(y, max(-px * sin(f_) + fh * cos(f_) for px in (-14, d["foot_len"] - 14)) - fh)
        pose["th" + key], pose["sh" + key] = ik2(a, b, x - hx, dy - y); pose["ft" + key] = ang
    air = 0.0
    if air_amp:
        u = ph % 0.5
        if u > duty: air = air_amp * sin(pi * (u - duty) / (0.5 - duty))
    pose["hip_h"] = dy + fh + air
    return pose


def _footfall(ph, duty, amp, decay=9.0):
    """Impact pulse 0..amp right after each heel strike (twice per cycle), decaying; used for squash + hip dip."""
    u = (ph * 2) % 1.0
    return amp * math.exp(-decay * u) * (1 - math.exp(-60 * u))


def _arms_swing(d, pose, ph, amp, bend0, bend_k, lag=0.07):
    """Counter-swing; forearm follows the upper arm a moment late and folds more on the forward swing (follow-through)."""
    for s_, sg in (("b", -1), ("a", 1)):
        pose["ua" + s_] = sg * amp * cos(2 * pi * ph)
        lagged = sg * amp * cos(2 * pi * (ph - lag))
        pose["fa" + s_] = lagged + bend0 + bend_k * max(0.0, pose["ua" + s_]) / 25
        pose["ha" + s_] = 6 * sin(2 * pi * (ph - 0.18) * 1) * sg


def walk(t, p, d, phase=None):
    L = leg_len(d); ph = phase if phase is not None else t / p.get("period", 0.95) + p.get("phase0", 0.0)
    fp = _footfall(ph, 0.62, 1.0)
    pose = gait(d, ph, 0.62, 0.66 * L * p.get("step_scale", 1.0), 0.93 * L, 0.05 * L, 0.085 * L, hx=3.5 * cos(2 * pi * ph - 0.4), dip=5.0 * fp)   # weight drops into each step
    pose.update(speed=1.0)
    pose["lean"] = 4.5 + 1.1 * sin(4 * pi * ph + 0.6) + 0.8 * fp
    pose["head"] = -3.0 + 1.6 * sin(4 * pi * (ph - 0.1)) - 1.2 * fp - 0.35 * (pose["lean"] - 4.5)   # head lags, stays level-ish
    _arms_swing(d, pose, ph, 25, 14, 14)
    pose["squash"] = 0.004 * cos(4 * pi * ph) + 0.014 * fp
    pose["torso_xs"] = 1.0 - 0.03 * abs(cos(2 * pi * ph))         # shoulders turn against the hips
    return apply_prop(d, pose, p)


def run(t, p, d, phase=None):
    L = leg_len(d); ph = phase if phase is not None else t / p.get("period", 0.62) + p.get("phase0", 0.0)
    fp = _footfall(ph, 0.36, 1.0, 12)
    pose = gait(d, ph, 0.36, 1.0 * L * p.get("step_scale", 1.0), 0.84 * L, 0.03 * L, 0.2 * L, 0.1 * L, hx=5 * cos(2 * pi * ph - 0.5), dip=6.0 * fp)
    pose.update(speed=1.7)
    pose["lean"] = 16.0 + 1.5 * sin(4 * pi * ph + 0.4)
    pose["head"] = -12.0 + 2.0 * sin(4 * pi * (ph - 0.12))
    for s_, sg in (("b", -1), ("a", 1)):
        pose["ua" + s_] = sg * 52 * cos(2 * pi * ph)
        pose["fa" + s_] = sg * 52 * cos(2 * pi * (ph - 0.09)) + 84 + 8 * (1 if sg * cos(2 * pi * ph) < 0 else 0)
        pose["ha" + s_] = -10 * sg * sin(2 * pi * ph)
    pose["squash"] = 0.012 * (cos(4 * pi * ph) - 0.3) + 0.022 * fp
    pose["torso_xs"] = 1.0 - 0.05 * abs(cos(2 * pi * ph))
    return apply_prop(d, pose, p, 0.1)


def walk_phone(t, p, d, phase=None):
    """Walking while reading a phone: head down, slower shorter steps, one hand holds the phone up, the other arm hangs."""
    L = leg_len(d); ph = phase if phase is not None else t / p.get("period", 1.1) + p.get("phase0", 0.0)
    fp = _footfall(ph, 0.64, 1.0)
    pose = gait(d, ph, 0.64, 0.58 * L * p.get("step_scale", 1.0), 0.94 * L, 0.035 * L, 0.07 * L, hx=2.5 * cos(2 * pi * ph - 0.4), dip=3.5 * fp)
    pose.update(speed=0.8)
    pose["lean"] = 7.0 + 0.8 * sin(4 * pi * ph); pose["head"] = 17 + 1.2 * sin(4 * pi * (ph - 0.1)) + 2.0 * sin(2 * pi * t / 2.7)
    pose["squash"] = 0.003 * cos(4 * pi * ph) + 0.01 * fp
    pose["uaa"] = 14 * cos(2 * pi * ph); pose["faa"] = pose["uaa"] + 12
    pose["uab"], pose["fab"], pose["hab"] = 48 + 1.5 * sin(4 * pi * ph), 132, 6
    pose["prop"] = dict(name=p.get("prop") or "phone", mode="hand", follow=True)
    return pose


def carry_box_walk(t, p, d, phase=None):
    """Walking with a box/parcel held in both arms: shorter, heavier steps, leaning back against the load."""
    L = leg_len(d); ph = phase if phase is not None else t / p.get("period", 1.05) + p.get("phase0", 0.0)
    fp = _footfall(ph, 0.64, 1.0)
    pose = gait(d, ph, 0.64, 0.54 * L * p.get("step_scale", 1.0), 0.93 * L, 0.04 * L, 0.07 * L, hx=3.0 * cos(2 * pi * ph - 0.4), dip=6.0 * fp)
    pose.update(speed=0.85)
    pose["lean"] = -2.5 + 1.0 * sin(4 * pi * ph + 0.5) + 1.2 * fp; pose["head"] = 1.0 + 1.5 * sin(4 * pi * (ph - 0.12)) - 1.5 * fp
    pose["squash"] = 0.004 * cos(4 * pi * ph) + 0.018 * fp
    name = p.get("prop") if p.get("prop") in CARRY else "box"
    carry_arms(d, pose, name)
    bw, bh = PROP_DIMS[name]; pr = pose["prop"]; pr["y"] += 3.0 * fp - 1.5 * sin(4 * pi * ph)    # the box bobs a little behind the body
    return pose


def stride(d, p, name="walk"):
    L = leg_len(d); sc = p.get("step_scale", 1.0)
    if name == "run": return 1.0 * L * sc / 0.36
    if name == "walk_phone": return 0.58 * L * sc / 0.64
    if name == "carry_box_walk": return 0.54 * L * sc / 0.64
    return 0.66 * L * sc / 0.62


# ---- standing family
def idle(t, p, d, phase=None):
    br, sw = sin(2 * pi * t / 3.4), sin(2 * pi * t / 5.3)
    pose = stand_legs(d, base_pose(), stand_h(d) - 1.6 * br, 3.0 * sw)
    brl = sin(2 * pi * t / 3.4 - 0.6)                                # breathing: chest leads, shoulders and head follow late
    pose.update(lean=2.0 + 1.0 * br + 0.5 * sw, head=-2 + 1.3 * sin(2 * pi * t / 4.1) - 0.8 * brl, squash=0.008 * br)
    pose["sh_dy"] = -1.6 * brl
    pose["uaa"] = 4 + 2 * br; pose["faa"] = pose["uaa"] + 10 + 1.5 * sin(2 * pi * t / 3.4 - 1.0); pose["uab"] = -3 - 1.5 * br; pose["fab"] = pose["uab"] + 8 + 1.5 * sin(2 * pi * t / 3.4 - 1.0)
    return apply_prop(d, pose, p)


def look_around(t, p, d, phase=None):
    """Head turns (profile flips through frontal to the other side) with a small anticipation dip; the body follows only a little."""
    D = p.get("duration", 3.0); u = t / D
    kf = [(0, 0), (.08, -6), (.34, 118), (.46, 112), (.52, 112), (.7, 24), (.78, 24), (.95, 0), (1, 0)]
    yaw = keys(u, kf, ease_io)
    pose = idle(t, p, d); pose["head_xs"] = cos(rad(yaw)); pose["head"] += 3.2 * sin(rad(yaw)); pose["lean"] += 1.5 * sin(rad(max(yaw, 0)))
    pose["torso_xs"] = 1 - 0.05 * sin(rad(clamp01(yaw / 100) * 90)); pose["sh_dx"] = 3.0 * sin(rad(min(yaw, 100)))
    return pose


def point(t, p, d, phase=None):
    """Anticipation (arm tucks, body gathers), reach with overshoot, hold with a slow drift, relax. The pointing shoulder turns toward the target."""
    D = p.get("duration", 1.8); u = t / D; s_ = "a" if p.get("prop") else "b"
    ang = p.get("angle", 82)
    gather = sin(pi * clamp01(u / 0.14)) * (u < 0.14)
    k = keys(u, [(0.0, 0.0), (0.14, 0.0)], ease)
    k = (spring((u - 0.14) / 0.4) if u > 0.14 else 0.0) * (1 - ease((u - 0.8) / 0.2))
    pose = idle(t, p, d)
    pose["ua" + s_] = lerp(pose["ua" + s_], ang + 3 * sin(t * 2.0) * k, k) - 18 * gather
    pose["fa" + s_] = lerp(pose["fa" + s_], ang + 3, k + 0.0) - 8 * gather + 6 * (k - ease(k)) * 0
    pose["ha" + s_] = 0
    pose["lean"] += 3.5 * k - 2.0 * gather; pose["head"] -= 2 * k
    pose["torso_xs"] = 1 - 0.1 * k; pose["sh_dx"] = 9 * k; pose["sh_dy"] = 1.0 * gather
    pose["squash"] += 0.02 * gather
    return pose


def wave(t, p, d, phase=None):
    D = p.get("duration", 2.2); u = t / D; s_ = "a" if p.get("prop") else "b"
    k = (spring((u - 0.05) / 0.4) if u > 0.05 else 0.0) * (1 - ease((u - 0.82) / 0.18))
    osc = sin(2 * pi * 2.6 * t) * k
    pose = idle(t, p, d)
    pose["ua" + s_] = lerp(pose["ua" + s_], 142, k) + 4 * sin(2 * pi * 2.6 * t - 0.5) * k
    pose["fa" + s_] = lerp(pose["fa" + s_], 150, k) + 28 * sin(2 * pi * 2.6 * t - 0.9) * k      # forearm and hand follow the upper arm late
    pose["ha" + s_] = 14 * sin(2 * pi * 2.6 * t - 1.5) * k
    pose["head"] += 5 * k; pose["lean"] -= 1.5 * k; pose["sh_dy"] = -3 * k; pose["sh_dx"] = 2 * k
    return pose


def turn(t, p, d, phase=None):
    D = p.get("duration", 0.8); u = t / D
    pose = idle(t, p, d); pose["xscale"] = cos(pi * ease_io(u)); pose["head_xs"] = cos(pi * ease(u * 1.4)); pose["squash"] += 0.02 * sin(pi * u)
    pose["lean"] += 3 * sin(pi * clamp01(u))
    return pose


def shrug(t, p, d, phase=None):
    """Shoulders lift, hands open out, head tilts, a beat of hold, then everything drops with a small settle."""
    D = p.get("duration", 1.8); u = t / D
    up = keys(u, [(0, 0), (0.1, -0.12), (0.3, 1.0), (0.62, 1.0), (0.78, -0.1), (0.9, 0.04), (1, 0)], ease)
    q = max(0.0, up)
    pose = idle(t, p, d)
    pose["sh_dy"] += -16 * up; pose["head"] += -4 * q + 6 * max(0, -up); pose["lean"] += -2 * q
    for s_ in "ab":
        pose["ua" + s_] = lerp(pose["ua" + s_], 24, q); pose["fa" + s_] = lerp(pose["fa" + s_], 96, q); pose["ha" + s_] = lerp(0, -22, q)
    pose["squash"] += 0.015 * (-up)
    pose["head_xs"] = 1 - 0.05 * q
    return pose


def think(t, p, d, phase=None):
    """Hand to chin, other arm braces the elbow, head tilts and weight shifts onto one leg; slow breath and tiny chin taps."""
    D = p.get("duration", 3.0); u = t / D
    k = ease_io(u / 0.22) if u < 0.5 else 1 - ease_io((u - 0.82) / 0.18)
    k = clamp01(k) if u < 0.82 else clamp01(1 - ease_io((u - 0.82) / 0.18))
    pose = idle(t, p, d)
    pose["head"] += 6 * k + 1.2 * sin(2 * pi * t / 2.3) * k; pose["lean"] += -1.5 * k
    sx, sy = shoulder_pos(d, pose); hx_, hy_ = head_pos(d, pose)
    tx, ty = hx_ - 4 + 1.5 * sin(2 * pi * t * 1.3) * k, hy_ + 2
    ub, fb = ik2(d["uarm"], d["farm"], tx - sx, ty - sy, -1)
    pose["uab"], pose["fab"] = lerp(pose["uab"], ub, k), lerp(pose["fab"], fb, k); pose["hab"] = lerp(pose["hab"], 40, k)
    ua, fa = ik2(d["uarm"], d["farm"], sx + 30 - sx, sy + 0.72 * d["uarm"] + 20 - sy, -1)
    pose["uaa"], pose["faa"] = lerp(pose["uaa"], ua, k), lerp(pose["faa"], fa, k)
    pose["hip_x"] += 5 * k; pose["sh_dy"] += 1.5 * k
    return pose


def knock(t, p, d, phase=None):
    """Raise a fist to door height (anticipation pull-back first), knock `knocks` times with the forearm leading and the shoulder following."""
    D = p.get("duration", 2.4); u = t / D; n = int(p.get("knocks", 3))
    up = (spring((u - 0.06) / 0.28) if u > 0.06 else 0.0) * (1 - ease((u - 0.86) / 0.14))
    pose = idle(t, p, d)
    kt = clamp01((u - 0.3) / 0.46); hit = 0.0
    if 0 < kt < 1: ph = (kt * n) % 1.0; hit = sin(pi * min(1.0, ph * 1.6)) ** 2 if ph < 0.625 else 0.0
    sx, sy = shoulder_pos(d, pose)
    tx, ty = sx + 0.78 * (d["uarm"] + d["farm"]) * 0.98 - 12 * hit, sy - 4
    ub, fb = ik2(d["uarm"], d["farm"], tx - sx, ty - sy, -1)
    pose["uab"] = lerp(pose["uab"], ub - 6 * (1 - up) * 0 + 4 * hit, up); pose["fab"] = lerp(pose["fab"], fb + 6 * hit, up); pose["hab"] = lerp(pose["hab"], 6, up)
    pose["lean"] += 4 * up + 1.8 * hit; pose["head"] += 2 * up; pose["sh_dx"] = 5 * up + 2.5 * hit; pose["squash"] += 0.01 * hit
    pose["torso_xs"] = 1 - 0.05 * up
    return pose


def lean_on_wall(t, p, d, phase=None):
    """Lean back against a wall behind the figure (its back at ~x=-wall_dx), one foot crossed forward, a hand in a pocket, easing in and out."""
    D = p.get("duration", 3.0); u = t / D
    k = ease_io(u / 0.25) if u < 0.5 else 1 - ease_io((u - 0.85) / 0.15)
    k = clamp01(k)
    br = sin(2 * pi * t / 3.6)
    pose = idle(t, p, d)
    h = stand_h(d) - 3 * k
    stand_legs(d, pose, h, lerp(pose["hip_x"], 16, k), fa=lerp(-13, -10, k), fb=lerp(15, 52, k), lift_b=2 * k)
    pose["lean"] = lerp(pose["lean"], -13 + 0.8 * br, k); pose["head"] = lerp(pose["head"], 12 + 1.5 * sin(2 * pi * t / 4.4), k)
    sx, sy = shoulder_pos(d, pose)
    ua, fa = ik2(d["uarm"], d["farm"], 38, 0.62 * d["torso"] + 4, -1)        # hand to the near pocket
    ub, fb_ = ik2(d["uarm"], d["farm"], 0, 0.5 * d["torso"], -1)
    pose["uab"], pose["fab"] = lerp(pose["uab"], ua, k), lerp(pose["fab"], fa, k)
    pose["uaa"], pose["faa"] = lerp(pose["uaa"], 10, k), lerp(pose["faa"], 30, k)
    pose["sh_dy"] += 2 * k
    return pose


def _grab_pose(d, p, name, bx, u):
    """Shared by pick_up / put_down: returns the pose at progress u (0 = standing, ends carrying the box at chest height)."""
    bw, bh = PROP_DIMS[name]; L = leg_len(d)
    # anticipation: tiny rock back/up, then the knees bend; the lift ends with a bracing lean back and a settle
    q = keys(u, [(0.0, 0.0), (0.07, -0.05), (0.32, 1.0), (0.45, 1.0), (0.62, 0.58), (0.84, 0.0), (0.93, -0.03), (1.0, 0.0)], ease)
    pose = idle(0.0, {}, d); pose["uab"] = pose["uaa"] = pose["fab"] = pose["faa"] = 0
    qq = max(q, 0.0)
    stand_legs(d, pose, lerp(stand_h(d), 0.52 * L + d["foot_h"], qq) + (4 if q < 0 else 0), -45 * qq)
    carry = clamp01((u - 0.45) / 0.45)
    pose["lean"] = 6 + 62 * qq - 7 * q * (q < 0) - 5 * ease(clamp01((u - 0.8) / 0.12)) * (1 if u < 0.95 else 1 - (u - 0.95) / 0.05)
    pose["head"] = -0.5 * pose["lean"] - 6 * qq * (1 - carry); pose["squash"] = 0.03 * qq
    sx, sy = shoulder_pos(d, pose)
    gw = {"b": (-bw * .45, -bh * .55), "a": (-bw * .45 + 8, -bh * .75)}
    cg = (bx, -bh / 2.0)
    cc = (sx + 14 + bw / 2, sy + bh * 0.55)
    cw = {"b": (-20, bh * 0.3), "a": (5, bh * 0.26)}
    if u < 0.45:
        k = ease(u / 0.32)
        for s_ in "ab": arm_to(d, pose, s_, sx, sy, lerp(sx, cg[0] + gw[s_][0], k), lerp(sy + 0.97 * (d["uarm"] + d["farm"]), cg[1] + gw[s_][1], k))
        c = cg
    else:
        k = ease((u - 0.45) / 0.45); c = (lerp(cg[0], cc[0], k), lerp(cg[1], cc[1], k))
        for s_ in "ab": arm_to(d, pose, s_, sx, sy, c[0] + lerp(gw[s_][0], cw[s_][0], k), c[1] + lerp(gw[s_][1], cw[s_][1], k))
    pose["hab"] = pose["haa"] = 10 * min(1.0, qq * 2)
    pose["prop"] = dict(name=name, mode="at", x=c[0], y=c[1])
    return pose


def pick_up(t, p, d, phase=None):
    D = p.get("duration", 2.0); name = p.get("prop") if p.get("prop") in CARRY else "box"
    return _grab_pose(d, p, name, p.get("box_x", 150), clamp01(t / D))


def put_down(t, p, d, phase=None):
    D = p.get("duration", 2.0); return pick_up(D - t, p, d)


def sit(t, p, d, phase=None):
    D = p.get("duration", 2.2); u = t / D; q = ease_io(u / 0.55); L = leg_len(d)
    pose = idle(t, p, d); hs = d["foot_h"] + 0.62 * L
    stand_legs(d, pose, lerp(stand_h(d), hs, q) + 3 * sin(pi * q) * 0, -80 * q)
    pose["lean"] = 2 + 5 * q + 4 * sin(pi * min(1, q)) * (u < 0.6); pose["uaa"], pose["faa"] = lerp(4, 18, q), lerp(14, 85, q); pose["uab"], pose["fab"] = lerp(-3, 22, q), lerp(5, 92, q)
    pose["seat"] = dict(x=-80.0, y=-(hs - 12)); pose["squash"] += 0.012 * sin(pi * min(1, q))
    return apply_prop(d, pose, p) if p.get("prop") in ("phone",) else pose


def stop(t, p, d, phase=None):
    D = p.get("duration", 0.9); u = min(1.0, t / D); cyc = p.get("cycles", D / (2 * 0.95))
    g = 1 - (1 - u) ** 2
    pose = walk(t, p, d, p.get("phase0", 0.0) + cyc * g)
    idl = idle(t, p, d)
    out = blend(pose, idl, ease((u - 0.6) / 0.4)); out["speed"] = 1 - u
    out["lean"] += 3.0 * sin(pi * clamp01(u * 0.9)) * (1 - u)      # weight rocks forward then settles as the body brakes
    return out


def stop_travel(t, p, d):
    D = p.get("duration", 0.9); u = min(1.0, t / D); cyc = p.get("cycles", D / (2 * 0.95))
    return stride(d, p) * cyc * (1 - (1 - u) ** 2)


class Action:
    def __init__(self, name, fn, dur, period=None, cyclic=False):
        self.name, self.fn, self.dur, self.period, self._cyc = name, fn, dur, period, cyclic
    @property
    def cyclic(self): return bool(self._cyc)
    def duration(self, params=None): return float((params or {}).get("duration", self.dur))
    def pose_at(self, t, params=None, dims=None, phase=None):
        return self.fn(t, params or {}, dims or DEFAULT_D, phase)
    def stride(self, dims, params=None): return stride(dims or DEFAULT_D, params or {}, self.name) if self.cyclic else None


_ACTIONS: Dict[str, Action] = {a.name: a for a in [
    Action("walk", walk, 2.0, 0.95, True), Action("run", run, 2.0, 0.62, True), Action("stand_idle", idle, 3.0), Action("look_around", look_around, 3.0),
    Action("point", point, 1.8), Action("turn", turn, 0.8), Action("pick_up", pick_up, 2.0), Action("put_down", put_down, 2.0),
    Action("wave", wave, 2.2), Action("stop", stop, 0.9), Action("sit", sit, 2.2),
    Action("walk_phone", walk_phone, 2.0, 1.1, True), Action("carry_box_walk", carry_box_walk, 2.0, 1.05, True), Action("knock", knock, 2.4),
    Action("shrug", shrug, 1.8), Action("think", think, 3.0), Action("lean", lean_on_wall, 3.0)]}


def get(name: str) -> Action:
    if name not in _ACTIONS: raise KeyError(f"unknown puppet action {name!r}; have {sorted(_ACTIONS)}")
    return _ACTIONS[name]


def names(): return list(_ACTIONS)
