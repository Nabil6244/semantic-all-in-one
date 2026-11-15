"""Toon Tales living backgrounds (Blender side): moving particles in front of and behind the cast.

Kinds: dust (warm motes drifting, default), rain (falling streaks), embers (rising sparks), snow,
leaves (tumbling), none. A place picks its kind in the plan: "places": {"room": {"prompt": ..., "ambient": "rain"}}.
Particles are driven per frame from Python (no keyframes), so they work with the shot driver as is.

Library use: st = ambient.build("dust", seed); per frame: ambient.step(st, t)
"""
import math
import random

import bpy

VOL = {"x": (-2.6, 2.6), "y": (-1.6, 2.6), "z": (0.0, 3.4)}
KINDS = {  # count, radius range, colour, emission, (vx, vz) metres/s, wobble, shape
    "dust": (60, (0.008, 0.018), (255, 236, 196), 2.2, (0.04, 0.03), 0.12, "dot"),
    "rain": (90, (0.004, 0.006), (200, 220, 255), 1.2, (-0.3, -6.5), 0.0, "streak"),
    "embers": (40, (0.01, 0.02), (255, 150, 60), 6.0, (0.05, 0.45), 0.18, "dot"),
    "snow": (80, (0.012, 0.024), (255, 255, 255), 1.6, (0.1, -0.5), 0.2, "dot"),
    "leaves": (18, (0.03, 0.05), (196, 128, 52), 0.8, (0.6, -0.4), 0.35, "leaf"),
}


def _srgb(c):
    def f(v):
        v = v / 255.0
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    return (f(c[0]), f(c[1]), f(c[2]), 1.0)


def build(kind="dust", seed=1):
    if kind in (None, "none") or kind not in KINDS:
        return []
    n, (r0, r1), col, emit, (vx, vz), wob, shape = KINDS[kind]
    m = bpy.data.materials.new(f"AMB_{kind}")
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = _srgb(col)
    b.inputs["Emission Color"].default_value = _srgb(col)
    b.inputs["Emission Strength"].default_value = emit
    rnd = random.Random(seed)
    out = []
    for i in range(n):
        r = rnd.uniform(r0, r1)
        if shape == "streak":
            bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=0.28, vertices=6)
            o = bpy.context.active_object
            o.rotation_euler = (0, math.atan2(-vx, -vz), 0)
        elif shape == "leaf":
            bpy.ops.mesh.primitive_plane_add(size=r * 2)
            o = bpy.context.active_object
        else:
            bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=r)
            o = bpy.context.active_object
        o.name = f"amb_{kind}_{i}"
        o.data.materials.append(m)
        o.visible_shadow = False
        p0 = [rnd.uniform(*VOL["x"]), rnd.uniform(*VOL["y"]), rnd.uniform(*VOL["z"])]
        sp = rnd.uniform(0.7, 1.3)
        out.append({"o": o, "p0": p0, "v": (vx * sp, vz * sp), "wob": wob, "ph": rnd.uniform(0, 6.28),
                    "leaf": shape == "leaf"})
    return out


def _wrap(v, lo, hi):
    return lo + (v - lo) % (hi - lo)


def step(parts, t):
    for p in parts:
        x = p["p0"][0] + p["v"][0] * t + p["wob"] * math.sin(t * 0.9 + p["ph"])
        z = p["p0"][2] + p["v"][1] * t + p["wob"] * 0.6 * math.sin(t * 1.3 + p["ph"] * 1.7)
        p["o"].location = (_wrap(x, *VOL["x"]), p["p0"][1], _wrap(z, *VOL["z"]))
        if p["leaf"]:
            p["o"].rotation_euler = (t * 3 + p["ph"], t * 2, t * 1.5)
