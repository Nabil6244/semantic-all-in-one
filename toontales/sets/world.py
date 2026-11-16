"""Toon world: a real 3D cartoon place built from free CC0 model packs (Kenney, assets/toon_world/kenney), drawn
with flat cel shading and black outlines, under a bright sky. Replaces the painted stage for "world" places.

A world layout (toontales/sets/worlds/<name>.json):
  {"ground": [r,g,b], "sky": {"top": [r,g,b], "low": [r,g,b]}, "sun": [pitch, yaw],
   "pieces": [{"m": "truck", "at": [x, y, z], "rot": deg, "s": scale, "id": "rig"?}, ...],
   "rows":   [{"m": ["tree-large", "tree-small"], "from": [x, y], "to": [x, y], "n": 8, "jitter": 0.4}, ...]}
Model names are file stems from any pack ("truck", "road-straight", "building-type-a", "tree_pineRoundA");
a "pack/name" form picks one pack when two share a stem. Puppets stand on the marks of the stage kit
(x -1.6..1.6, y -0.2..1.8), so a layout keeps that strip clear and builds around and behind it.
Movers: pieces with an "id" can be moved per shot: shot["moves"] = [{"id", "to": [x, y, z], "t0", "t1", "ease"?,
"rot_to"?}] (step(world, t) each frame).
"""
import json
import math
import random
from pathlib import Path

import bpy

try:
    from sets import parts
except ImportError:  # imported as toontales.sets.world
    from . import parts

ROOT = Path(__file__).resolve().parents[2]
PACKS = ROOT / "assets" / "toon_world" / "kenney"
WORLDS = Path(__file__).resolve().parent / "worlds"
OUTLINE = 0.03  # outline thickness in metres (world size)
# The packs use different units: scale each so a puppet (~1.9 m) fits: a truck ~6.5 m long, a road tile 7 m,
# a house ~8 m wide, a tree ~5 m tall. "s" in a layout multiplies this.
PACK_SCALE = {"car-kit": 2.2, "city-kit-roads": 7.0, "city-kit-suburban": 6.0, "city-kit-commercial": 6.0,
              "nature-kit": 3.0, "furniture-kit": 2.4, "fantasy-town-kit": 3.5, "graveyard-kit": 2.4,
              "survival-kit": 3.0, "train-kit": 2.6}
LIGHT = {"lit": [1.0, 1.0, 1.0], "shade": [0.60, 0.62, 0.80]}  # cel bands; a layout "light" tints them (dusk, lamp)
_INDEX = None
_CACHE = {}


def index():
    """stem -> glb path over every pack (first pack wins on a clash; "pack/stem" always works)."""
    global _INDEX
    if _INDEX is None:
        _INDEX = {}
        for g in sorted(PACKS.glob("*/Models/*/*.glb")):
            pack = g.parts[len(PACKS.parts)]
            _INDEX.setdefault(g.stem, g)
            _INDEX[f"{pack}/{g.stem}"] = g
    return _INDEX


def _toon_material(src, tint=None, mode="multiply"):
    """Cel shading: the model's own colour (texture or flat), lit in two hard bands. tint multiplies the colour
    (mode "color": takes the tint's hue and keeps the model's light/dark, so a repainted car stays bright)."""
    name = f"toon_{src.name}" + (f"_{'_'.join(str(round(c, 2)) for c in tint)}_{mode[0]}" if tint else "")
    if name in bpy.data.materials:
        return bpy.data.materials[name]
    m = bpy.data.materials.new(name)
    m["src"] = src.name  # a tinted copy of this model starts from the original, not from this toon one
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    color_sock, color_val = None, (0.8, 0.8, 0.8, 1)
    bsdf = next((n for n in src.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None) if src.use_nodes else None
    tex = None
    if bsdf:
        inp = bsdf.inputs["Base Color"]
        color_val = tuple(inp.default_value)
        if inp.is_linked:
            ln = inp.links[0].from_node
            if ln.type == "TEX_IMAGE":
                tex = nt.nodes.new("ShaderNodeTexImage")
                tex.image = ln.image
                tex.interpolation = "Closest"
                color_sock = tex.outputs["Color"]
    if color_sock is None:
        rgb = nt.nodes.new("ShaderNodeRGB")
        rgb.outputs[0].default_value = color_val
        color_sock = rgb.outputs[0]
    diff = nt.nodes.new("ShaderNodeBsdfDiffuse")
    diff.inputs["Color"].default_value = (1, 1, 1, 1)
    s2r = nt.nodes.new("ShaderNodeShaderToRGB")
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.interpolation = "CONSTANT"
    ramp.color_ramp.elements[0].position = 0.0
    ramp.color_ramp.elements[0].color = (*LIGHT["shade"], 1)   # shadow band: cool, not black
    ramp.color_ramp.elements[1].position = 0.42
    ramp.color_ramp.elements[1].color = (*LIGHT["lit"], 1)
    sat = nt.nodes.new("ShaderNodeHueSaturation")
    sat.inputs["Saturation"].default_value = 1.2
    sat.inputs["Value"].default_value = 0.92
    mul = nt.nodes.new("ShaderNodeMix")
    mul.data_type = "RGBA"
    mul.blend_type = "MULTIPLY"
    mul.inputs["Factor"].default_value = 1.0
    emit = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(diff.outputs[0], s2r.inputs[0])
    nt.links.new(s2r.outputs["Color"], ramp.inputs["Fac"])
    if tint:
        tm = nt.nodes.new("ShaderNodeMix")
        tm.data_type = "RGBA"
        tm.blend_type = "COLOR" if mode == "color" else "MULTIPLY"
        tm.inputs["Factor"].default_value = 1.0
        tm.inputs[7].default_value = (*tint, 1)
        nt.links.new(color_sock, tm.inputs[6])
        color_sock = tm.outputs[2]
    nt.links.new(color_sock, sat.inputs["Color"])
    nt.links.new(sat.outputs["Color"], mul.inputs[6])
    nt.links.new(ramp.outputs["Color"], mul.inputs[7])
    nt.links.new(mul.outputs[2], emit.inputs["Color"])
    nt.links.new(emit.outputs[0], out.inputs[0])
    return m


def _outline_material():
    m = bpy.data.materials.get("toon_outline")
    if m:
        return m
    m = bpy.data.materials.new("toon_outline")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    e = nt.nodes.new("ShaderNodeEmission")
    e.inputs["Color"].default_value = (0.04, 0.04, 0.06, 1)
    o = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(e.outputs[0], o.inputs[0])
    m.use_backface_culling = True
    return m


def _toonify(obj, scale, tint=None, mode="multiply"):
    if obj.type != "MESH":
        return
    mats = obj.data.materials
    for i, mt in enumerate(list(mats)):
        if not mt or mt.name == "toon_outline":
            continue
        base = bpy.data.materials.get(mt.get("src", "")) if mt.name.startswith("toon_") else mt
        if base is not None and (tint or not mt.name.startswith("toon_")):
            mats[i] = _toon_material(base, tint, mode)
    if obj.modifiers.get("outline"):  # a copy of a model that already has its outline shell
        return
    if obj.dimensions.z * scale < 0.15 or obj.name.split("/")[-1].startswith(("wall", "floor", "paneling")):
        return  # flat pieces (floor, road, rug) and room walls (thin, normals face in): an outline shell covers them
    mats.append(_outline_material())
    sol = obj.modifiers.new("outline", "SOLIDIFY")
    sol.thickness = -OUTLINE / max(scale, 0.05)  # object space: divide the world thickness by the scale
    sol.offset = 1.0
    sol.use_flip_normals = True
    sol.use_rim = False
    sol.material_offset = len(mats) - 1


def _load(name):
    """Import one model once; later uses copy it (shared mesh). Returns the root object (an empty or a mesh)."""
    path = index().get(name)
    if path is None:
        raise KeyError(f"model '{name}' is not in the toon world packs")
    if name in _CACHE:
        src = _CACHE[name]
        return _copy_tree(src)
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    new = [o for o in bpy.data.objects if o not in before]
    roots = [o for o in new if o.parent is None]
    if len(roots) == 1:
        root = roots[0]
    else:
        root = bpy.data.objects.new(f"m_{name}", None)
        bpy.context.scene.collection.objects.link(root)
        for o in roots:
            o.parent = root
    _CACHE[name] = root
    root["toon_src"] = True
    return root


def _copy_tree(src):
    def cp(o, parent):
        n = o.copy()
        if o.data is not None:
            n.data = o.data  # shared mesh: cheap
        bpy.context.scene.collection.objects.link(n)
        n.parent = parent
        for c in o.children:
            cp(c, n)
        return n
    root = cp(src, None)
    root.matrix_world = src.matrix_world.copy()
    return root


def _meshes(root):
    out = [root] if root.type == "MESH" else []
    for c in root.children_recursive:
        if c.type == "MESH":
            out.append(c)
    return out


def pack_of(name):
    p = index()[name]
    return p.parts[len(PACKS.parts)]


UNTINTED = ("wheel", "tire", "tyre")


def place(name, at=(0, 0, 0), rot=0.0, s=1.0, tint=None, mode="multiply"):
    s = s * PACK_SCALE.get(pack_of(name), 1.0)
    if tint:  # tinted pieces need their own mesh copy (materials live on the mesh)
        root = _load(name)
        for o in _meshes(root):
            o.data = o.data.copy()
        root["toon_done"] = False
    else:
        root = _load(name)
    root.location = at
    root.rotation_mode = "XYZ"
    root.rotation_euler = (0, 0, math.radians(rot))
    root.scale = (s, s, s)
    if not root.get("toon_done"):
        for o in _meshes(root):  # wheels/tyres keep their own colour: a repaint is for the body
            keep = tint and any(w in o.name.lower() for w in UNTINTED)
            _toonify(o, s, None if keep else tint, mode)
        root["toon_done"] = True
    return root


def _sky(top, low):
    w = bpy.data.worlds.new("toon_sky")
    bpy.context.scene.world = w
    w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.45  # horizon sits near the middle of a 9:16 frame
    ramp.color_ramp.elements[0].color = (*low, 1)
    ramp.color_ramp.elements[1].position = 0.92
    ramp.color_ramp.elements[1].color = (*top, 1)
    bg = nt.nodes.new("ShaderNodeBackground")
    bg.inputs["Strength"].default_value = 1.0
    out = nt.nodes.new("ShaderNodeOutputWorld")
    nt.links.new(tc.outputs["Window"], sep.inputs[0])
    nt.links.new(sep.outputs["Y"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bg.inputs["Color"])
    nt.links.new(bg.outputs[0], out.inputs[0])


def _clouds(rng, n=7):
    mat = bpy.data.materials.new("toon_cloud")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    e = nt.nodes.new("ShaderNodeEmission")
    e.inputs["Color"].default_value = (1, 1, 1, 1)
    o = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(e.outputs[0], o.inputs[0])
    for i in range(n):
        x, y, z = rng.uniform(-40, 40), rng.uniform(55, 90), rng.uniform(14, 30)
        for k in range(rng.randint(3, 5)):
            r = rng.uniform(2.5, 5.0)
            bpy.ops.mesh.primitive_uv_sphere_add(radius=r, location=(x + k * r * 1.1 - 4, y, z + rng.uniform(-0.6, 0.6)),
                                                 segments=16, ring_count=8)
            c = bpy.context.active_object
            c.scale = (1.2, 0.5, 0.55)
            c.data.materials.append(mat)


def _ground(color, size=400):
    bpy.ops.mesh.primitive_plane_add(size=size, location=(0, size / 2 - 20, -0.005))
    g = bpy.context.active_object
    m = bpy.data.materials.new("toon_ground")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    e = nt.nodes.new("ShaderNodeEmission")
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 0.06
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.interpolation = "CONSTANT"
    ramp.color_ramp.elements[0].color = (*[c * 0.9 for c in color], 1)
    ramp.color_ramp.elements[1].position = 0.5
    ramp.color_ramp.elements[1].color = (*color, 1)
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], e.inputs["Color"])
    o = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(e.outputs[0], o.inputs[0])
    g.data.materials.append(m)
    return g


def _sun(pitch, yaw):
    bpy.ops.object.light_add(type="SUN", rotation=(math.radians(90 - pitch), 0, math.radians(yaw)))
    sun = bpy.context.active_object
    sun.data.energy = 3.0
    try:
        sun.data.angle = math.radians(2)
    except Exception:
        pass
    return sun


def load_layout(name):
    if isinstance(name, dict):
        return name
    return json.loads((WORLDS / f"{name}.json").read_text())


def build(layout, seed=0):
    """Build the world. Returns the marks (same shape as the stage kit) plus the movable pieces by id."""
    L = load_layout(layout)
    _CACHE.clear()  # a batch run resets the scene between shots: cached objects are gone
    LIGHT.update({"lit": [1.0, 1.0, 1.0], "shade": [0.60, 0.62, 0.80]}, **(L.get("light") or {}))
    sc = bpy.context.scene
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.exposure = 0.0
    rng = random.Random(seed or 7)
    sky = L.get("sky", {})
    _sky(sky.get("top", [0.30, 0.62, 0.98]), sky.get("low", [0.78, 0.90, 1.0]))
    _ground(L.get("ground", [0.62, 0.78, 0.38]))
    _sun(*L.get("sun", [48, 35]))
    if L.get("clouds", True):
        _clouds(rng)
    movers, riders = {}, []
    for p in L.get("pieces", []):
        if p["m"].startswith("@"):  # a car part built from shapes (sets/parts.py)
            o, anims = parts.build(p)
            o.location = tuple(p.get("at", (0, 0, 0)))
            o.rotation_mode = "XYZ"
            o.rotation_euler = (0, 0, math.radians(p.get("rot", 0.0)))
            s = p.get("s", 1.0)
            o.scale = (s, s, s)
            for m in _meshes(o):
                _toonify(m, s)
            key = p.get("id") or f"_part{len(movers)}"
            movers[key] = {"obj": o, "home": o.location.copy(), "rot0": o.rotation_euler.z, "anims": anims,
                           "run": p.get("run", 0.0)}
            continue
        stem = p["m"].split("/")[-1]  # "pack/name": paint keys match the name
        tint = p.get("tint") or next((v for k, v in L.get("paint", {}).items() if stem.startswith(k)), None)
        o = place(p["m"], tuple(p.get("at", (0, 0, 0))), p.get("rot", 0.0), p.get("s", 1.0), tint,
                  p.get("tint_mode", "multiply"))
        if p.get("id"):
            movers[p["id"]] = {"obj": o, "home": o.location.copy(), "rot0": o.rotation_euler.z}
        if p.get("ride"):  # rides along with another mover (carriages behind a locomotive)
            riders.append((o, p["ride"]))
    bpy.context.view_layer.update()
    for o, rid in riders:
        if rid in movers:
            par = movers[rid]["obj"]
            mw = o.matrix_world.copy()
            o.parent = par
            o.matrix_world = mw
    for r in L.get("rows", []):
        names = r["m"] if isinstance(r["m"], list) else [r["m"]]
        n = r.get("n", 6)
        for i in range(n):
            k = i / max(1, n - 1)
            x = r["from"][0] + (r["to"][0] - r["from"][0]) * k + rng.uniform(-1, 1) * r.get("jitter", 0.3)
            y = r["from"][1] + (r["to"][1] - r["from"][1]) * k + rng.uniform(-1, 1) * r.get("jitter", 0.3)
            s = r.get("s", 1.0) * rng.uniform(0.85, 1.15)
            place(rng.choice(names), (x, y, 0), r.get("rot", rng.uniform(0, 360)), s)
    kits = json.loads((Path(__file__).resolve().parent / "kits.json").read_text())["kits"]
    return {"cast": dict(kits["stage"]["marks"]), "movers": movers}


def _ease(x, kind="inout"):
    x = min(1.0, max(0.0, x))
    if kind == "in":
        return x * x
    if kind == "out":
        return 1 - (1 - x) * (1 - x)
    if kind == "linear":
        return x
    return x * x * (3 - 2 * x)


def step(world, moves, t):
    """Move pieces by id along their shot moves (last move wins; a piece holds its end spot after t1).
    Parts with anims spin/pump at their run speed; a move with "run_to" ramps it over t0..t1."""
    dt = max(0.0, t - world.get("_t", t))
    world["_t"] = t
    for pid, m in world["movers"].items():
        if not m.get("anims"):
            continue
        run = m["run"]
        for mv in moves or []:
            if mv["id"] == pid and "run_to" in mv and t >= mv["t0"]:
                k = _ease((t - mv["t0"]) / max(0.01, mv["t1"] - mv["t0"]), mv.get("ease", "inout"))
                run = m["run"] + (mv["run_to"] - m["run"]) * k
        parts.animate(m["anims"], run, t, dt)
    for mv in moves or []:
        if "to" not in mv:
            continue
        m = world["movers"].get(mv["id"])
        if not m or t < mv["t0"]:
            continue
        k = _ease((t - mv["t0"]) / max(0.01, mv["t1"] - mv["t0"]), mv.get("ease", "inout"))
        a = mv.get("from") or list(m["home"])
        b = mv["to"]
        m["obj"].location = [a[i] + (b[i] - a[i]) * k for i in range(3)]
        if "tilt_to" in mv:  # degrees about the piece y axis (lifts one end of a road tile)
            t0 = math.radians(mv["tilt_from"]) if "tilt_from" in mv else m.setdefault("tilt0", m["obj"].rotation_euler.y)
            m["obj"].rotation_euler.y = t0 + (math.radians(mv["tilt_to"]) - t0) * k
        if "rot_to" in mv:
            r0 = m["rot0"]
            m["obj"].rotation_euler.z = r0 + (math.radians(mv["rot_to"]) - r0) * k
