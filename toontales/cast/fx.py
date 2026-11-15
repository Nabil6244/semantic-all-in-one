"""Toon Tales reaction FX (Blender side): cartoon sprites that pop next to a character during an action.

Automatic from the shot's actions (no plan work): fear -> sweat, anger -> vein mark, shock -> burst,
money/joy -> sparkles, running -> speed lines, puzzled -> "?", dizzy/bonk -> stars.
Sprites are flat unlit planes facing the camera side (-Y), placed from the head each frame; they pop in,
pulse a little and vanish when the action is over. Pictures come from cast/fx_art.py.

Library use: st = fx.build(chars, acts_by_char, fx_dir); per frame: fx.step(st, chars, t)
"""
import math

import bpy
from mathutils import Vector

import puppet

# action -> (sprite, offset from head centre in head radii (x, z), size in head radii, min seconds shown)
RULES = {
    "tremble": ("sweat", (0.95, 0.35), 0.9, 1.0), "plead": ("sweat", (0.95, 0.35), 0.9, 1.0),
    "cower": ("sweat", (0.95, 0.35), 0.9, 1.0),
    "angry": ("anger", (0.8, 0.85), 0.8, 1.2),
    "shock": ("burst", (0.0, 0.0), 3.4, 0.7), "jump": ("burst", (0.0, 0.0), 3.0, 0.5),
    "money": ("sparkle", (0.0, 0.8), 2.6, 1.2), "celebrate": ("sparkle", (0.0, 0.9), 2.8, 1.2),
    "fist_pump": ("sparkle", (0.2, 0.8), 2.4, 1.0), "cheer": ("sparkle", (0.0, 0.9), 2.8, 1.0),
    "run": ("speed", (0.0, -1.6), 2.4, 0.0),
    "think": ("question", (0.9, 1.1), 0.9, 1.2), "scratch_head": ("question", (0.9, 1.1), 0.9, 1.0),
    "scratch": ("question", (0.9, 1.1), 0.9, 1.0),
    "dizzy": ("stars", (0.0, 1.15), 2.2, 1.4), "bonk": ("stars", (0.0, 1.15), 2.2, 1.4),
}


def _mat(name, path):
    return puppet.mat_decal(f"FX_{name}", bpy.data.images.load(str(path), check_existing=True))


def build(chars, fx_dir, durs):
    """chars: {id: ch with _acts}; durs: action name -> default seconds. Returns the list of live sprites."""
    mats, out = {}, []
    for cid, ch in chars.items():
        r = ch["cfg"]["head_r"]
        for a in ch["_acts"]:
            rule = RULES.get(a["do"])
            if not rule:
                continue
            name, off, size, hold = rule
            if name not in mats:
                mats[name] = _mat(name, fx_dir / f"{name}.png")
            bpy.ops.mesh.primitive_plane_add(size=1.0, rotation=(math.pi / 2, 0, 0))
            o = bpy.context.active_object
            o.name = f"FX_{cid}_{name}_{len(out)}"
            o.data.materials.append(mats[name])
            o.visible_shadow = False
            o.hide_render = True
            t0 = a["t0"]
            out.append({"obj": o, "who": cid, "name": name, "off": off, "size": size * r, "t0": t0,
                        "t1": t0 + max(hold, a.get("dur", durs.get(a["do"], 1.0))), "prev": None})
    return out


def step(sprites, chars, t):
    for sp in sprites:
        o = sp["obj"]
        on = sp["t0"] <= t < sp["t1"]
        o.hide_render = not on
        if not on:
            continue
        ch = chars[sp["who"]]
        r = ch["cfg"]["head_r"]
        ho = ch["head"]  # object origin sits at the character's base: use the mesh's own centre
        head = ho.matrix_world @ (sum((Vector(c) for c in ho.bound_box), Vector()) / 8)
        k = min(1.0, (t - sp["t0"]) / 0.1)            # pop in over 0.1 s with a small overshoot
        pop = 1.0 + 0.25 * math.sin(k * math.pi) if k < 1 else 1.0
        pulse = 1.0 + 0.06 * math.sin((t - sp["t0"]) * 14)
        s = sp["size"] * pop * pulse
        loc = head + Vector((sp["off"][0] * r, -r * 1.05, sp["off"][1] * r))
        if sp["name"] == "sweat":                     # drops slide down a little
            loc.z -= 0.25 * r * ((t - sp["t0"]) % 0.8)
        if sp["name"] == "speed":                     # lines trail behind the runner
            root = ch["root"].matrix_world.translation
            vx = 0.0 if sp["prev"] is None else root.x - sp["prev"]
            sp["prev"] = root.x
            side = -1 if vx < 0 else 1
            loc = Vector((root.x - side * 0.55, root.y - 0.05, root.z + 0.55))
            o.scale = (s * side, s * 0.6, s)
            o.location = loc
            continue
        if sp["name"] == "stars":
            o.rotation_euler = (math.pi / 2, 0, 0)
            loc.x += 0.08 * math.sin(t * 9)
        o.scale = (s, s, s)
        o.location = loc
