"""Stickman skeleton: proportions, pose blending and forward kinematics.

Units: 1.0 = figure height. Screen space is y-down. Angles are degrees.
Limb angles are measured from straight down; a + angle swings the limb toward the
way the figure faces. Knee bend (kn_*) folds the shin backward like a real knee.
Elbow bend (el_*) turns the forearm further forward from the upper arm.
rot turns the whole body about the pelvis (lying, falling, bowing); + tips it forward.
_b = the back limb, _f = the front limb (relative to facing).
"""
import math

HEAD_R = 0.12
NECK = 0.04
TORSO = 0.30
SHOULDER_DROP = 0.05
UPPER_ARM = 0.17
FOREARM = 0.16
THIGH = 0.22
SHIN = 0.22

ANGLES = ("rot", "lean", "head", "sh_b", "el_b", "sh_f", "el_f", "hip_b", "kn_b", "hip_f", "kn_f")
FACE = ("mouth", "eyes")

NEUTRAL = {
    "rot": 0.0, "lean": 2.0, "head": 0.0,
    "sh_b": -12.0, "el_b": 10.0, "sh_f": 12.0, "el_f": 10.0,
    "hip_b": -6.0, "kn_b": 3.0, "hip_f": 6.0, "kn_f": 3.0,
    "mouth": "smile", "eyes": "open",
}


def make(**kw):
    p = dict(NEUTRAL)
    p.update(kw)
    return p


def blend(a, b, k):
    """Angles move from a to b by k (k may overshoot 1 a little); the face switches halfway."""
    out = {n: a[n] + (b[n] - a[n]) * k for n in ANGLES}
    for n in FACE:
        out[n] = b[n] if k >= 0.5 else a[n]
    return out


def _down(deg, f):
    r = math.radians(deg)
    return (math.sin(r) * f, math.cos(r))


def _add(p, v, s):
    return (p[0] + v[0] * s, p[1] + v[1] * s)


def fk(pose, facing=1):
    """Joint positions relative to the pelvis, in figure-height units."""
    f = 1 if facing >= 0 else -1
    pelvis = (0.0, 0.0)
    lean = math.radians(pose["lean"])
    up = (math.sin(lean) * f, -math.cos(lean))
    neck = _add(pelvis, up, TORSO)
    shoulder = _add(pelvis, up, TORSO - SHOULDER_DROP)
    tilt = math.radians(pose["lean"] + pose["head"])
    head = _add(neck, (math.sin(tilt) * f, -math.cos(tilt)), NECK + HEAD_R)
    j = {"pelvis": pelvis, "neck": neck, "shoulder": shoulder, "head": head}
    for s in ("b", "f"):
        sh = pose["sh_" + s]
        elbow = _add(shoulder, _down(sh, f), UPPER_ARM)
        j["elbow_" + s] = elbow
        j["hand_" + s] = _add(elbow, _down(sh + pose["el_" + s], f), FOREARM)
        hip = pose["hip_" + s]
        knee = _add(pelvis, _down(hip, f), THIGH)
        j["knee_" + s] = knee
        j["foot_" + s] = _add(knee, _down(hip - pose["kn_" + s], f), SHIN)
    rot = pose.get("rot", 0.0)
    if rot:                                   # whole body turns about the pelvis (+ = tips forward)
        a = math.radians(rot * f)
        c, s_ = math.cos(a), math.sin(a)
        j = {k: (x * c - y * s_, x * s_ + y * c) for k, (x, y) in j.items()}
    return j


def lowest(j):
    """Lowest point of the figure (largest y), counting the head's round bottom."""
    return max(max(y for k, (x, y) in j.items() if k != "head"), j["head"][1] + HEAD_R)
