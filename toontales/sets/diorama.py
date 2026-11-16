"""Realistic cut-away diorama (Channel 3 'World In A Box' look), run inside Blender.

A layout with "engine": "diorama" is built here instead of the cel-shaded toon world: PBR materials from the
CC0 Poly Haven textures in assets/diorama (fetch: python3 -m toontales.diorama.fetch_polyhaven), an HDRI sky,
a sun with soft shadows, no outlines. The ground is a slice cut along y = 0 so the camera, at -y, looks into it.

Pieces ("m"):
  "@slice"  {"x": [x0, x1], "y": [y0, y1], "top": 0, "layers": [["grass", .15], ["soil", 1.6], ["gravel", .6],
             ["rock", 4]], "cuts": [{"shape": "cyl", "at": [x, y], "r": .8, "z0": -6, "z1": 1},
             {"shape": "box", "at": [x, y, z], "size": [w, d, h]}]}           layered ground, holes cut out
  "@shaft"  {"at": [x, y], "r": .8, "wall": .25, "z0": -6, "z1": .6, "mat": "stone"}  lined shaft, front half cut away
  "@water"  {"at": [x, y, z0], "size": [w, d], "r"?: round, "level": h}        water body; moves "level_to" fill/drain
  "@room"   {"at": [x, y, z], "size": [w, d, h], "floor": "wood_floor", "walls": "plaster", "ceiling": false,
             "open": ["front"]}                                               open-front room
  "@house"  "@room" keys + "roof": "roof", "pitch": 30                         room with a gable roof
  "@beam"   {"a": [x, y, z], "b": [x, y, z], "t": .14, "mat": "planks"}       post / rafter / plank between two points
  "@box"    {"at": [x, y, z], "size": [w, d, h], "mat"?: key, "color"?: rgb}  z is the bottom
  other     a pack model (sets/world.py index) with its own materials, not toon-shaded
Any piece may have "id" (a mover) and "show_at" (hidden until then: a build step appearing).
Shot moves (on top of world.step's to/from/rot_to): {"id", "level_to", "t0", "t1"} water level,
{"id", "grow": "up"|"all", "from"?, "to"?, "t0", "t1"} a piece scales (a wall rising, soil dug away),
{"id", "show": t} / {"id", "hide": t} a piece pops in or out.
"""
import math
from pathlib import Path

import bmesh
import bpy
from mathutils import Matrix, Vector

from sets import objects, world

ROOT = Path(__file__).resolve().parents[2]
TEX = ROOT / "assets" / "diorama" / "textures"
HDRI = ROOT / "assets" / "diorama" / "hdri"
TILE = {"grass": 4.0, "soil": 1.6, "gravel": 1.6, "rock": 4.0, "stone": 1.6, "brick": 1.6, "planks": 2.0,
        "wood_floor": 2.0, "plaster": 2.5, "tile": 1.6, "sand": 2.5, "wet_sand": 2.5, "concrete": 2.5, "roof": 2.0,
        "metal": 1.5, "bark": 1.2, "cobble": 2.0, "walnut": 0.8, "oak": 0.8}
GRADE = {"rock": (0.18, 0.5), "grass": (1.25, 0.8), "soil": (0.85, 0.9), "plaster": (0.6, 1.35)}  # (saturation, value): grey bedrock, lusher grass
MODELS = ROOT / "assets" / "diorama" / "models"
_MATS = {}


# ---------------------------------------------------------------- materials
def pbr(key, tint=None):
    """Box-projected PBR material from the Poly Haven texture set 'key' (metre-true: tile size per TILE)."""
    name = f"dio_{key}" + (f"_{'_'.join(str(round(c, 2)) for c in tint)}" if tint else "")
    if name in _MATS:
        return _MATS[name]
    d = TEX / key
    if not (d / "diff.jpg").exists():
        raise FileNotFoundError(f"texture '{key}' missing in {TEX} (run python3 -m toontales.diorama.fetch_polyhaven)")
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    s = 1.0 / TILE.get(key, 2.0)
    mp.inputs["Scale"].default_value = (s, s, s)
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])

    def img(fname, data):
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image = bpy.data.images.load(str(d / fname), check_existing=True)
        if data:
            n.image.colorspace_settings.name = "Non-Color"
        n.projection = "BOX"
        n.projection_blend = 0.2
        nt.links.new(mp.outputs["Vector"], n.inputs["Vector"])
        return n
    diff = img("diff.jpg", False)
    col = diff.outputs["Color"]
    if key in GRADE:
        hsv = nt.nodes.new("ShaderNodeHueSaturation")
        hsv.inputs["Saturation"].default_value, hsv.inputs["Value"].default_value = GRADE[key]
        nt.links.new(col, hsv.inputs["Color"])
        col = hsv.outputs["Color"]
    if tint:
        mix = nt.nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        mix.blend_type = "MULTIPLY"
        mix.inputs["Factor"].default_value = 1.0
        mix.inputs[7].default_value = (*tint, 1)
        nt.links.new(col, mix.inputs[6])
        col = mix.outputs[2]
    nt.links.new(col, bsdf.inputs["Base Color"])
    nt.links.new(img("rough.jpg", True).outputs["Color"], bsdf.inputs["Roughness"])
    bump = nt.nodes.new("ShaderNodeBump")  # box projection has no tangents: bump from the colour reads well
    bump.inputs["Strength"].default_value = 0.35
    bump.inputs["Distance"].default_value = 0.02
    nt.links.new(diff.outputs["Color"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    _MATS[name] = m
    return m


def flat(color, rough=0.6, metal=0.0):
    name = "dio_flat_" + "_".join(str(round(c, 2)) for c in color) + f"_{rough}_{metal}"
    if name in _MATS:
        return _MATS[name]
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    _MATS[name] = m
    return m


def water_mat():
    if "dio_water" in _MATS:
        return _MATS["dio_water"]
    m = bpy.data.materials.new("dio_water")
    m.use_nodes = True
    nt = m.node_tree
    b = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    b.inputs["Base Color"].default_value = (0.16, 0.55, 0.68, 1)
    b.inputs["Roughness"].default_value = 0.04
    b.inputs["IOR"].default_value = 1.33
    b.inputs["Alpha"].default_value = 0.72
    for k in ("Transmission Weight", "Transmission"):
        if k in b.inputs:
            b.inputs[k].default_value = 0.35
            break
    # gentle ripples on the surface
    tc = nt.nodes.new("ShaderNodeTexCoord")
    wave = nt.nodes.new("ShaderNodeTexNoise")
    wave.inputs["Scale"].default_value = 3.0
    nt.links.new(tc.outputs["Object"], wave.inputs["Vector"])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.12
    nt.links.new(wave.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])
    for attr, val in (("surface_render_method", "BLENDED"), ("blend_method", "BLEND")):
        try:
            setattr(m, attr, val)
        except Exception:
            pass
    try:
        m.use_backface_culling = False
        m.show_transparent_back = False
    except Exception:
        pass
    _MATS["dio_water"] = m
    return m


def _mat_for(p, key="mat", default="concrete"):
    if p.get("color") and not p.get(key):
        return flat(p["color"], p.get("rough", 0.6), p.get("metal", 0.0))
    if p.get(key) in objects.FINISH or p.get(key) in ("glass", "cork"):  # glass / metals / paints (Channel 5)
        return objects.finish(p[key], p.get("color"))
    return pbr(p.get(key, default), p.get("tint"))


# ---------------------------------------------------------------- meshes
def _link(o, parent=None):
    if parent is not None:
        o.parent = parent
    return o


def box(size, center, mat, parent=None, name="box"):
    """Axis box with real dimensions baked into the mesh (object coords = metres, so textures stay true)."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=size, verts=bm.verts)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(o)
    o.location = center
    o.data.materials.append(mat)
    return _link(o, parent)


def cylinder(r, depth, center, mat, verts=48, parent=None, name="cyl"):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=verts, radius1=r, radius2=r, depth=depth)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(o)
    o.location = center
    o.data.materials.append(mat)
    return _link(o, parent)


def _cut(target, cutter):
    """Boolean difference, applied; the cutter is removed."""
    if target.data.materials:  # the new cut faces take the cutter's material: make it the target's own
        cutter.data.materials.clear()
        cutter.data.materials.append(target.data.materials[0])
    mod = target.modifiers.new("cut", "BOOLEAN")
    mod.operation = "DIFFERENCE"
    mod.object = cutter
    try:
        mod.solver = "EXACT"
    except Exception:
        pass
    bpy.context.view_layer.objects.active = target
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(target.evaluated_get(dg))
    target.modifiers.remove(mod)
    old = target.data
    target.data = me
    if old.users == 0:
        bpy.data.meshes.remove(old)


def _cutter(c):
    if c.get("shape", "box") == "cyl":
        z0, z1 = c.get("z0", -50.0), c.get("z1", 5.0)
        return cylinder(c["r"], z1 - z0, (c["at"][0], c["at"][1], (z0 + z1) / 2), flat([1, 0, 1]), name="cutter")
    sx, sy, sz = c["size"]
    x, y, z = c["at"]
    return box((sx, sy, sz), (x, y, z + sz / 2), flat([1, 0, 1]), name="cutter")


def _root(name):
    o = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(o)
    return o


def ground_slice(p):
    """Layered ground block from y0 (the cut face) back to y1; each band its own texture; cuts are holes."""
    root = _root("slice")
    x0, x1 = p.get("x", [-30, 30])
    y0, y1 = p.get("y", [0, 60])
    z = p.get("top", 0.0)
    for key, depth in p.get("layers", [["grass", 0.15], ["soil", 1.6], ["gravel", 0.6], ["rock", 5.0]]):
        o = box((x1 - x0, y1 - y0, depth), ((x0 + x1) / 2, (y0 + y1) / 2, z - depth / 2), pbr(key), root, key)
        for c in p.get("cuts", []):
            k = _cutter(c)
            _cut(o, k)
            bpy.data.objects.remove(k, do_unlink=True)
        z -= depth
    return root


def shaft(p):
    """A lined round shaft (a well): tube from z0 up to z1 (a little above ground: the well lip), front half removed."""
    root = _root("shaft")
    x, y = p["at"]
    r, w = p.get("r", 0.8), p.get("wall", 0.25)
    z0, z1 = p.get("z0", -6.0), p.get("z1", 0.6)
    tube = cylinder(r + w, z1 - z0, (x, y, (z0 + z1) / 2), pbr(p.get("mat", "stone")), parent=root, name="tube")
    inner = cylinder(r, z1 - z0 + 2, (x, y, (z0 + z1) / 2), flat([1, 0, 1]), name="cutter")
    _cut(tube, inner)
    bpy.data.objects.remove(inner, do_unlink=True)
    if p.get("cutaway", True):  # the slice face is y = 0: show the inside like the reference
        front = box((2 * (r + w) + 1, r + w + 1, z1 - z0 + 2), (x, y - (r + w + 1) / 2 + p.get("cut_at", 0.0),
                                                              (z0 + z1) / 2), flat([1, 0, 1]), name="cutter")
        _cut(tube, front)
        bpy.data.objects.remove(front, do_unlink=True)
    return root


def water(p):
    """Water body with its origin at the bottom, so scaling z is the level (fill/drain)."""
    x, y, z0 = p["at"]
    lvl = max(0.001, p.get("level", 1.0))
    if p.get("r"):
        me_o = cylinder(p["r"], 1.0, (0, 0, 0.5), water_mat(), name="water")
    else:
        w, d = p["size"]
        me_o = box((w, d, 1.0), (0, 0, 0.5), water_mat(), name="water")
    # bake the half-unit offset into the mesh so the origin sits on the bottom face
    me_o.data.transform(Matrix.Translation((0, 0, 0.5)))
    me_o.location = (x, y, z0)
    if p.get("r") and p.get("cutaway", True):  # a well's water is sliced flat at the face like the shaft
        r = p["r"]
        front = box((2 * r + 1, r + 1, 3.0), (x, y - (r + 1) / 2 + p.get("cut_at", 0.0), z0 + 0.5), flat([1, 0, 1]),
                    name="cutter")
        _cut(me_o, front)
        bpy.data.objects.remove(front, do_unlink=True)
    me_o.scale = (1, 1, lvl)
    me_o["level"] = lvl
    _water_seen(me_o)
    return me_o


def room(p, roof=False):
    """Open-front room: floor, back wall, side walls, optional ceiling; 'open' lists the sides left off."""
    root = _root("room")
    x, y, z = p["at"]
    w, d, h = p["size"]
    t = p.get("wall_t", 0.15)
    opens = set(p.get("open", ["front"]))
    walls = pbr(p.get("walls", "plaster"), p.get("wall_tint"))
    box((w, d, t), (x, y, z - t / 2), pbr(p.get("floor", "wood_floor")), root, "floor")
    if "back" not in opens:
        box((w, t, h), (x, y + d / 2 - t / 2, z + h / 2), walls, root, "wall_back")
    if "left" not in opens:
        box((t, d, h), (x - w / 2 + t / 2, y, z + h / 2), walls, root, "wall_left")
    if "right" not in opens:
        box((t, d, h), (x + w / 2 - t / 2, y, z + h / 2), walls, root, "wall_right")
    if "front" not in opens:
        box((w, t, h), (x, y - d / 2 + t / 2, z + h / 2), walls, root, "wall_front")
    if p.get("light", True):  # reference interiors are bright and white: a soft ceiling panel fills the open room
        bpy.ops.object.light_add(type="AREA", location=(x, y, z + h - 0.05))
        lt = bpy.context.active_object
        lt.data.shape = "RECTANGLE"
        lt.data.size, lt.data.size_y = w * 0.8, d * 0.8
        lt.data.energy = p.get("light_w", 55.0) * w * d
        lt.data.color = (1.0, 0.96, 0.9)
        lt.parent = root
    if p.get("ceiling") and not roof:
        box((w, d, t), (x, y, z + h + t / 2), walls, root, "ceiling")
    if roof:
        pitch = math.radians(p.get("pitch", 30))
        half = w / 2 + 0.35
        run = half / math.cos(pitch)
        rise = half * math.tan(pitch)
        rm = pbr(p.get("roof", "roof"))
        for side in (-1, 1):
            o = box((run, d + 0.6, 0.12), (x + side * half / 2, y, z + h + rise / 2 + 0.06), rm, root, "roof")
            o.rotation_euler = (0, side * pitch, 0)  # each slab rises toward the ridge
        # gable fill at the back so the attic reads as a solid roof from the open front
        me = bpy.data.meshes.new("gable")
        yb = y + d / 2 - t / 2
        me.from_pydata([(x - w / 2, yb, z + h), (x + w / 2, yb, z + h), (x, yb, z + h + rise * (w / 2) / half)], [],
                       [(0, 1, 2)])
        g = bpy.data.objects.new("gable", me)
        bpy.context.scene.collection.objects.link(g)
        g.data.materials.append(walls)
        g.parent = root
        box((w + 0.2, 0.22, 0.22), (x, y - d / 2 + 0.11, z + h + 0.11), pbr("planks"), root, "eave")  # front beam
    return root


def beam(p):
    a, b = p["a"], p["b"]
    t = p.get("t", 0.14)
    vec = [b[i] - a[i] for i in range(3)]
    L = math.sqrt(sum(v * v for v in vec)) or 0.01
    o = box((t, t, L), [(a[i] + b[i]) / 2 for i in range(3)], _mat_for(p, default="planks"), name="beam")
    o.rotation_mode = "QUATERNION"
    o.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(Vector(vec).normalized())
    return o


def plain_box(p):
    """"tilt": degrees about x (a roof slope falling toward +y for positive tilt)."""
    sx, sy, sz = p["size"]
    x, y, z = p["at"]
    o = box((sx, sy, sz), (x, y, z), _mat_for(p))
    o.data.transform(Matrix.Translation((0, 0, sz / 2)))  # origin on the bottom face: "grow" rises from the floor
    if p.get("tilt"):
        o.rotation_euler.x = math.radians(p["tilt"])
    return o


_PH = {}


def ph_model(pid):
    """Import a Poly Haven glTF once; later uses get a linked copy. Returns a root empty."""
    path = MODELS / pid / f"{pid}_1k.gltf"
    if not path.exists():
        raise FileNotFoundError(f"model '{pid}' missing ({path}); run python3 -m toontales.diorama.fetch_polyhaven")
    if pid in _PH:
        return world._copy_tree(_PH[pid])
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    roots = [o for o in bpy.data.objects if o not in before and o.parent is None]
    root = _root(f"ph_{pid}")
    for o in roots:
        o.parent = root
    _PH[pid] = root
    return root


BUILD = {"slice": ground_slice, "shaft": shaft, "water": water, "room": room,
         "house": lambda p: room(p, roof=True), "beam": beam, "box": plain_box}
KINDS = tuple(BUILD)


# ---------------------------------------------------------------- scene
def _sky(name="day", strength=1.0, yaw=0.0):
    w = bpy.data.worlds.new("dio_sky")
    bpy.context.scene.world = w
    w.use_nodes = True
    nt = w.node_tree
    bg = next(n for n in nt.nodes if n.type == "BACKGROUND")
    env = nt.nodes.new("ShaderNodeTexEnvironment")
    env.image = bpy.data.images.load(str(HDRI / f"{name}.hdr"), check_existing=True)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Rotation"].default_value = (0, 0, math.radians(yaw))
    nt.links.new(tc.outputs["Generated"], mp.inputs["Vector"])
    nt.links.new(mp.outputs["Vector"], env.inputs["Vector"])
    nt.links.new(env.outputs["Color"], bg.inputs["Color"])
    bg.inputs["Strength"].default_value = strength


def _sun(pitch, yaw, energy=3.5):
    bpy.ops.object.light_add(type="SUN", rotation=(math.radians(90 - pitch), 0, math.radians(yaw)))
    s = bpy.context.active_object
    s.data.energy = energy
    s.data.color = (1.0, 0.97, 0.92)
    try:
        s.data.angle = math.radians(3)
    except Exception:
        pass


def _realistic():
    sc = bpy.context.scene
    for vt in ("AgX", "Filmic"):
        try:
            sc.view_settings.view_transform = vt
            break
        except Exception:
            continue
    try:
        sc.view_settings.look = "AgX - Medium High Contrast" if sc.view_settings.view_transform == "AgX" else "None"
    except Exception:
        pass
    sc.view_settings.exposure = 0.0
    ee = sc.eevee
    for attr, val in (("use_raytracing", True), ("use_shadows", True), ("shadow_ray_count", 2),
                      ("use_gtao", True), ("gtao_distance", 0.6), ("shadow_pool_size", "1024")):
        try:
            setattr(ee, attr, val)
        except Exception:
            pass


def build(layout, seed=0):
    """Same contract as world.build: {"cast": marks, "movers": {id: {...}}}."""
    L = world.load_layout(layout)
    _MATS.clear()
    _PH.clear()
    world._CACHE.clear()
    _realistic()
    _sky(L.get("hdri", "day"), L.get("sky_strength", 1.0), L.get("sky_yaw", 0.0))
    if L.get("sun", [42, 30]):  # a studio layout sets "sun": null and lights itself
        _sun(*L.get("sun", [42, 30]))
    for lt in L.get("lights", []):  # {"at", "aim", "size", "w", "color"}: studio area lights
        bpy.ops.object.light_add(type="AREA", location=tuple(lt["at"]))
        o = bpy.context.active_object
        o.data.size = lt.get("size", 1.0)
        o.data.energy = lt.get("w", 100.0)
        o.data.color = tuple(lt.get("color", [1.0, 0.95, 0.88]))
        d = Vector(lt.get("aim", [0, 0, 0])) - Vector(lt["at"])
        o.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    objects._M.clear()
    movers, riders = {}, []
    for i, p in enumerate(L.get("pieces", [])):
        kind = p["m"][1:] if p["m"].startswith("@") else None
        if kind:
            if kind not in BUILD and kind not in objects.BUILD:
                raise KeyError(f"diorama piece '@{kind}' unknown (have: {', '.join('@' + k for k in KINDS + objects.KINDS)})")
            if kind in BUILD:
                o = BUILD[kind](p)
            else:  # close-up objects (Channel 5): bottles, caps, coins, magnets, tile walls
                o = objects.place(objects.BUILD[kind](p), p)
        elif p["m"].startswith("ph:"):  # a CC0 Poly Haven model (fetch_polyhaven MODELS)
            o = ph_model(p["m"][3:])
            o.location = tuple(p.get("at", (0, 0, 0)))
            o.rotation_mode = "XYZ"
            o.rotation_euler = (0, 0, math.radians(p.get("rot", 0.0)))
            s = p.get("s", 1.0)
            o.scale = (s, s, s)
        else:  # a pack model with its own colours
            o = world._load(p["m"])
            o.location = tuple(p.get("at", (0, 0, 0)))
            o.rotation_mode = "XYZ"
            o.rotation_euler = (0, 0, math.radians(p.get("rot", 0.0)))
            s = p.get("s", 1.0) * world.PACK_SCALE.get(world.pack_of(p["m"]), 1.0)
            o.scale = (s, s, s)
        if p.get("rot") is not None and kind and o.type == "MESH" and o.rotation_mode == "XYZ":
            o.rotation_euler.z = math.radians(p["rot"])
        key = p.get("id") or f"_p{i}"
        movers[key] = {"obj": o, "home": o.location.copy(), "rot0": o.rotation_euler.z if o.rotation_mode == "XYZ" else 0.0,
                       "scale0": tuple(o.scale), "show_at": p.get("show_at"), "level": o.get("level")}
        if p.get("show_at") is not None:
            _show(o, False)
        if p.get("ride"):  # rides on another piece (a coin in a scale pan): parented after everything is built
            riders.append((o, p["ride"]))
    bpy.context.view_layer.update()
    for o, rid in riders:
        if rid in movers:
            mw = o.matrix_world.copy()
            o.parent = movers[rid]["obj"]
            o.matrix_world = mw
    import json
    kits = json.loads((Path(__file__).resolve().parent / "kits.json").read_text())["kits"]
    return {"cast": dict(L.get("marks") or kits["stage"]["marks"]), "movers": movers, "dof": L.get("dof")}


def _water_seen(o):
    """An (almost) empty water body is hidden: a 1 mm sheet still reads as a blue floor from above."""
    on = o.scale.z >= 0.02
    o.hide_render = not on
    o.hide_viewport = not on


def _show(o, on):
    for ob in [o] + list(o.children_recursive):
        ob.hide_render = not on
        ob.hide_viewport = not on


def step(W, moves, t):
    """world.step (to/from, rot_to, tilt) plus water levels, pieces growing in and build steps appearing."""
    world.step(W, [m for m in (moves or []) if isinstance(m.get("to"), list) or "run_to" in m], t)  # grow "to" is a size
    for pid, m in W["movers"].items():
        if m.get("show_at") is not None:
            _show(m["obj"], t >= m["show_at"])
    for mv in moves or []:
        m = W["movers"].get(mv["id"])
        if not m:
            continue
        if t < mv.get("t0", 0):
            if mv.get("grow"):  # before it starts the piece holds its starting size
                g = max(0.001, mv.get("from", 0.0))
                s0 = m["scale0"]
                m["obj"].scale = (s0[0], s0[1], s0[2] * g) if mv["grow"] == "up" else tuple(c * g for c in s0)
            if "level_to" in mv and m.get("level") is not None:
                m["obj"].scale.z = max(0.001, mv.get("level_from", m["level"]))
                _water_seen(m["obj"])
            continue
        k = world._ease((t - mv.get("t0", 0)) / max(0.01, mv.get("t1", 1) - mv.get("t0", 0)), mv.get("ease", "inout"))
        if "level_to" in mv and m.get("level") is not None:
            a = mv.get("level_from", m["level"])
            m["obj"].scale.z = max(0.001, a + (mv["level_to"] - a) * k)
            _water_seen(m["obj"])
        if mv.get("grow"):  # "up": height only (a wall rising, soil dug away with from 1 to 0), else all axes
            s0 = m["scale0"]
            g = max(0.001, mv.get("from", 0.0) + (mv.get("to", 1.0) - mv.get("from", 0.0)) * k)
            m["obj"].scale = (s0[0], s0[1], s0[2] * g) if mv["grow"] == "up" else tuple(c * g for c in s0)
    for mv in moves or []:  # {"id", "show": t} / {"id", "hide": t}: a piece pops in or out at t (a lid fitted)
        m = W["movers"].get(mv["id"])
        if m and ("show" in mv or "hide" in mv):
            on = (t >= mv["show"]) if "show" in mv else (t < mv["hide"])
            _show(m["obj"], on)
