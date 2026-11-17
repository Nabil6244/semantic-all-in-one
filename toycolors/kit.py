"""Reusable Blender kit for Toy Vehicles Colours: render setup, sunny park world, and toy vehicles with faces.

Import inside Blender (after sys.path holds the repo root):
    from toycolors import kit
    kit.setup_render(fast=True); kit.park_world(); v = kit.vehicle("bus", (0.95, 0.7, 0.05), loc=(0, 0, 0))
Every vehicle faces +X from its root empty, sits on z=0, and returns a Vehicle with .root, .body_mats, .wheels.
Look rules: toycolors/REFERENCE.md.
"""
import math
import random

import bpy
from mathutils import Matrix, Vector

_rng = random.Random(11)


# ================================================================ render
def setup_render(fast=False, fps=24):
    sc = bpy.context.scene
    for eng in ("BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"):
        try:
            sc.render.engine = eng
            break
        except TypeError:
            pass
    sc.render.resolution_x, sc.render.resolution_y = (1280, 720) if fast else (1920, 1080)
    sc.render.fps = fps
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.look = "None"
    sc.view_settings.exposure = 0.0
    ev = sc.eevee
    sc.render.filter_size = 1.3                                 # a touch smoother edges, like the reference
    import os
    samples = int(os.environ.get("TOY_SAMPLES", 16 if fast else 24))     # speed pass: 24 looks like 96 after grade
    rt = os.environ.get("TOY_RT", "0") == "1"                          # raytracing off: 3x faster, same look
    for attr, val in [("taa_render_samples", samples), ("use_shadows", True),
                      ("use_raytracing", rt), ("shadow_ray_count", int(os.environ.get("TOY_SHRAYS", 1))), ("shadow_step_count", int(os.environ.get("TOY_SHSTEPS", 4))),
                      ("fast_gi_distance", 2.0), ("use_fast_gi", True)]:
        try:
            setattr(ev, attr, val)
        except (AttributeError, TypeError):
            pass
    return sc


def camera(loc, aim, lens=35, dof_target=None, fstop=2.8):
    bpy.ops.object.camera_add(location=loc)
    cam = bpy.context.object
    bpy.context.scene.camera = cam
    cam.data.lens = lens
    cam.data.clip_end = 400
    tgt = bpy.data.objects.new("cam_aim", None)
    bpy.context.scene.collection.objects.link(tgt)
    tgt.location = aim
    c = cam.constraints.new("TRACK_TO")
    c.target, c.track_axis, c.up_axis = tgt, "TRACK_NEGATIVE_Z", "UP_Y"
    if dof_target is not None:
        cam.data.dof.use_dof = True
        cam.data.dof.focus_object = dof_target
        cam.data.dof.aperture_fstop = fstop
    return cam, tgt


# ================================================================ materials
_MATS = {}


def _bsdf(m):
    m.use_nodes = True
    return m.node_tree.nodes["Principled BSDF"]


def mat(name, rgb, rough=0.4, metal=0.0, coat=0.0, emit=0.0):
    key = (name, tuple(round(c, 3) for c in rgb), rough, metal, coat, emit)
    if key in _MATS:
        return _MATS[key]
    m = bpy.data.materials.new(name)
    b = _bsdf(m)
    b.inputs["Base Color"].default_value = (*rgb, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if "Coat Weight" in b.inputs:
        b.inputs["Coat Weight"].default_value = coat
        b.inputs["Coat Roughness"].default_value = 0.05
    if emit:
        b.inputs["Emission Color"].default_value = (*rgb, 1)
        b.inputs["Emission Strength"].default_value = emit
    _MATS[key] = m
    return m


def toy_paint(name, rgb):
    """Glossy toy body paint; not cached, so each vehicle can change colour on its own."""
    m = bpy.data.materials.new(name)
    b = _bsdf(m)
    b.inputs["Base Color"].default_value = (*rgb, 1)
    b.inputs["Roughness"].default_value = 0.28
    if "Coat Weight" in b.inputs:
        b.inputs["Coat Weight"].default_value = 0.9
        b.inputs["Coat Roughness"].default_value = 0.04
    return m


def chrome():
    return mat("chrome", (0.85, 0.86, 0.9), rough=0.12, metal=1.0)


def rubber():
    return mat("rubber", (0.025, 0.025, 0.03), rough=0.75)


def glass():
    return mat("glass", (0.06, 0.16, 0.30), rough=0.04, coat=1.0)


def ramp_mat(name, c0, c1, scale=1.0, rough=0.8, kind="noise"):
    m = bpy.data.materials.new(name)
    b = _bsdf(m)
    b.inputs["Roughness"].default_value = rough
    nt = m.node_tree
    if kind == "noise":
        t = nt.nodes.new("ShaderNodeTexNoise")
        t.inputs["Scale"].default_value = scale
        out = t.outputs["Fac"]
    elif kind == "instance":                      # per-object / per-instance tint
        t = nt.nodes.new("ShaderNodeObjectInfo")
        out = t.outputs["Random"]
    else:                                         # wood grain bands
        t = nt.nodes.new("ShaderNodeTexWave")
        t.inputs["Scale"].default_value = scale
        t.inputs["Distortion"].default_value = 1.5
        out = t.outputs["Fac"]
    r = nt.nodes.new("ShaderNodeValToRGB")
    r.color_ramp.elements[0].color = (*c0, 1)
    r.color_ramp.elements[1].color = (*c1, 1)
    nt.links.new(out, r.inputs["Fac"])
    nt.links.new(r.outputs["Color"], b.inputs["Base Color"])
    return m


# ================================================================ mesh helpers
def _smooth(ob, bevel=0.0, segs=4):
    if bevel:
        md = ob.modifiers.new("bevel", "BEVEL")
        md.width, md.segments = bevel, segs
        md.limit_method = "ANGLE"
    for p in ob.data.polygons:
        p.use_smooth = True
    return ob


def _link(ob, parent):
    if parent is not None:
        ob.parent = parent
    return ob


def box(name, loc, size, m, bevel=0.03, parent=None, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(location=loc, rotation=rot)
    ob = bpy.context.object
    ob.name = name
    ob.scale = (size[0] / 2, size[1] / 2, size[2] / 2)
    bpy.ops.object.transform_apply(scale=True)
    ob.data.materials.append(m)
    return _link(_smooth(ob, min(bevel, min(size) * 0.49)), parent)


def cyl(name, loc, r, h, m, verts=40, rot=(0, 0, 0), parent=None, bevel=0.0):
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r, depth=h, location=loc, rotation=rot)
    ob = bpy.context.object
    ob.name = name
    ob.data.materials.append(m)
    return _link(_smooth(ob, bevel, 3), parent)


def sphere(name, loc, r, m, scale=(1, 1, 1), parent=None, segs=32):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segs, ring_count=segs // 2, radius=r, location=loc)
    ob = bpy.context.object
    ob.name = name
    ob.scale = scale
    ob.data.materials.append(m)
    return _link(_smooth(ob), parent)


def empty(name, loc=(0, 0, 0), parent=None):
    e = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(e)
    e.location = loc
    return _link(e, parent)


def frame_from(normal, up=(0, 0, 1)):
    """Rotation whose local +Z is `normal` and local +Y points as close to `up` as possible."""
    z = Vector(normal).normalized()
    y = (Vector(up) - z * z.dot(Vector(up))).normalized()
    x = y.cross(z)
    return Matrix((x, y, z)).transposed().to_euler()


# ================================================================ world
def park_world(grass_radius=22.0, density=28.0, trees=34, seed=3, sand=False, keep_out=()):
    """Sunny toy park: gradient sky + clouds, sun, grass with real tufts, hills, round trees.
    keep_out: [(xmin, xmax, ymin, ymax)] rectangles with no grass (under boards and props)."""
    rng = random.Random(seed)
    sc = bpy.context.scene
    w = bpy.data.worlds.new("sky")
    sc.world = w
    w.use_nodes = True
    nt = w.node_tree
    bg = nt.nodes["Background"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.0                   # view direction Z: 0 at the horizon
    ramp.color_ramp.elements[0].color = (0.62, 0.84, 1.0, 1)     # light horizon
    ramp.color_ramp.elements[1].position = 0.4
    ramp.color_ramp.elements[1].color = (0.10, 0.38, 1.0, 1)     # deep blue overhead
    nt.links.new(tc.outputs["Generated"], sep.inputs[0])
    nt.links.new(sep.outputs["Z"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bg.inputs["Color"])
    bg.inputs["Strength"].default_value = 0.6                    # light the sky casts on the toys
    # the camera sees a brighter sky than the light it gives, so the sky reads blue without washing out the set
    seen = nt.nodes.new("ShaderNodeBackground")
    seen.inputs["Strength"].default_value = 1.0
    nt.links.new(ramp.outputs["Color"], seen.inputs["Color"])
    lp = nt.nodes.new("ShaderNodeLightPath")
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(lp.outputs["Is Camera Ray"], mix.inputs["Fac"])
    nt.links.new(bg.outputs[0], mix.inputs[1])
    nt.links.new(seen.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], nt.nodes["World Output"].inputs["Surface"])

    bpy.ops.object.light_add(type="SUN", rotation=(math.radians(48), math.radians(12), math.radians(-30)))
    sun = bpy.context.object
    sun.data.energy = 4.2
    sun.data.angle = math.radians(6)
    sun.data.color = (1.0, 0.97, 0.92)

    # ground: sand yard or grass
    gm = (ramp_mat("sand", (0.80, 0.62, 0.38), (0.90, 0.74, 0.50), scale=0.8, rough=0.95) if sand else
          ramp_mat("ground", (0.12, 0.38, 0.04), (0.22, 0.52, 0.07), scale=0.35, rough=0.95))
    bpy.ops.mesh.primitive_plane_add(size=300)
    ground = bpy.context.object
    ground.name = "ground"
    ground.data.materials.append(gm)

    if not sand:
        _grass(grass_radius, density, seed, keep_out)

    hill = ramp_mat("hill", (0.13, 0.45, 0.05), (0.22, 0.58, 0.08), scale=0.08, rough=0.95)
    for x, y, s in [(-40, 70, 30), (10, 85, 40), (55, 65, 26), (-80, 50, 24), (90, 45, 22)]:
        sphere("hill", (x, y, -s * 0.62), 1, hill, scale=(s * 1.4, s * 0.7, s))

    trunk = mat("trunk", (0.32, 0.17, 0.07), rough=0.8)
    leaves = ramp_mat("leaves", (0.07, 0.34, 0.03), (0.30, 0.62, 0.08), rough=0.6, kind="instance")
    for i in range(trees):
        a = math.radians(rng.uniform(-80, 80))
        r = rng.uniform(13, 30)
        tree((r * math.sin(a), r * math.cos(a) + 4), rng.uniform(0.9, 1.6), trunk, leaves, rng)

    cloud = mat("cloud", (1, 1, 1), rough=1.0, emit=0.6)
    for i in range(7):
        cx, cy, cz = rng.uniform(-90, 90), rng.uniform(110, 150), rng.uniform(22, 40)
        for k in range(4):
            sphere("cloud", (cx + k * 5 - 7, cy, cz + rng.uniform(-1, 2)), rng.uniform(4, 6.5), cloud,
                   scale=(1.3, 0.6, 0.8), segs=16)
    return ground, sun


def _grass(radius, density, seed, keep_out=()):
    """Grass tufts instanced over a disc in front of the camera with geometry nodes (fast in EEVEE)."""
    blade_m = ramp_mat("blade", (0.10, 0.36, 0.03), (0.28, 0.62, 0.09), rough=0.7, kind="instance")
    # one tuft: 7 thin bent blades
    verts, faces = [], []
    rng = random.Random(seed)
    for b in range(7):
        a = rng.uniform(0, 2 * math.pi)
        h = rng.uniform(0.07, 0.13)
        lean = rng.uniform(0.01, 0.04)
        dx, dy = math.cos(a), math.sin(a)
        px, py = -dy * 0.008, dx * 0.008
        bx, by = dx * 0.015, dy * 0.015
        i = len(verts)
        verts += [(bx - px, by - py, 0), (bx + px, by + py, 0), (bx + dx * lean, by + dy * lean, h)]
        faces.append((i, i + 1, i + 2))
    me = bpy.data.meshes.new("tuft")
    me.from_pydata(verts, [], faces)
    tuft = bpy.data.objects.new("tuft", me)
    bpy.context.scene.collection.objects.link(tuft)
    tuft.data.materials.append(blade_m)
    tuft.hide_render = True
    tuft.hide_viewport = True

    import bmesh
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=int(radius * 4), y_subdivisions=int(radius * 4), size=radius * 2,
                                    location=(0, 2, 0.001))
    area = bpy.context.object
    area.name = "grass_area"
    bm = bmesh.new()
    bm.from_mesh(area.data)
    gone = []
    for fc in bm.faces:
        c = fc.calc_center_median()
        wx, wy = c.x, c.y + 2
        if c.x ** 2 + c.y ** 2 > radius ** 2 or any(x0 <= wx <= x1 and y0 <= wy <= y1 for x0, x1, y0, y1 in keep_out):
            gone.append(fc)
    bmesh.ops.delete(bm, geom=gone, context="FACES")
    bm.to_mesh(area.data)
    bm.free()
    area.data.materials.append(blade_m)
    ng = bpy.data.node_groups.new("grass_scatter", "GeometryNodeTree")
    ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    n = ng.nodes
    gi, go = n.new("NodeGroupInput"), n.new("NodeGroupOutput")
    dist = n.new("GeometryNodeDistributePointsOnFaces")
    dist.inputs["Density"].default_value = density
    oi = n.new("GeometryNodeObjectInfo")
    oi.inputs["Object"].default_value = tuft
    inst = n.new("GeometryNodeInstanceOnPoints")
    rot = n.new("FunctionNodeRandomValue")
    rot.data_type = "FLOAT_VECTOR"
    [i for i in rot.inputs if i.type == "VECTOR" and i.name == "Max"][0].default_value = (0.15, 0.15, 6.28)
    scl = n.new("FunctionNodeRandomValue")
    scl.data_type = "FLOAT"
    fmin, fmax = [i for i in scl.inputs if i.type == "VALUE" and i.name in ("Min", "Max")][:2]
    fmin.default_value, fmax.default_value = 0.7, 1.6
    fout = [o for o in scl.outputs if o.type == "VALUE"][0]
    L = ng.links.new
    L(gi.outputs[0], dist.inputs["Mesh"])
    L(dist.outputs["Points"], inst.inputs["Points"])
    L(oi.outputs["Geometry"], inst.inputs["Instance"])
    L([o for o in rot.outputs if o.type == "VECTOR"][0], inst.inputs["Rotation"])
    L(fout, inst.inputs["Scale"])
    L(inst.outputs["Instances"], go.inputs[0])
    md = area.modifiers.new("grass", "NODES")
    md.node_group = ng
    return area


def tree(xy, s, trunk_m, leaf_m, rng):
    x, y = xy
    cyl("trunk", (x, y, 0.9 * s), 0.18 * s, 1.8 * s, trunk_m, verts=12)
    for k in range(rng.randint(3, 5)):
        ox, oy, oz = rng.uniform(-0.6, 0.6) * s, rng.uniform(-0.4, 0.4) * s, rng.uniform(-0.2, 0.7) * s
        sphere("leaf", (x + ox, y + oy, 2.5 * s + oz), rng.uniform(0.85, 1.25) * s, leaf_m, segs=24)


# ================================================================ vehicle parts
class Vehicle:
    def __init__(self, kind, root):
        self.kind, self.root = kind, root
        self.body_mats, self.wheels, self.parts = [], [], {}


def wheel(name, loc, r, w, rim_m, parent, monster=False):
    """Tyre with tread blocks, coloured rim and chrome hub. Rolls by rotating the returned empty about local Y."""
    hub = empty(name, loc, parent)
    tyre = cyl(name + "_tyre", (0, 0, 0), r * 0.9, w, rubber(), verts=48, rot=(math.pi / 2, 0, 0), parent=hub,
               bevel=r * 0.28)
    n = 22 if not monster else 16
    lug = (r * 0.26, w * (0.48 if monster else 0.92), r * (0.16 if monster else 0.1))
    for k in range(n):
        a = 2 * math.pi * k / n
        for side in ((-1, 1) if monster else (0,)):
            off = side * w * 0.26 + (0 if not monster else 0)
            aa = a + (side * math.pi / n if monster else 0)
            box(name + "_lug", (math.cos(aa) * r * 0.9, off, math.sin(aa) * r * 0.9), lug, rubber(), bevel=lug[2] * 0.4,
                parent=hub, rot=(0, -aa + math.pi / 2, 0))
    rim = cyl(name + "_rim", (0, 0, 0), r * 0.56, w * 1.04, rim_m, verts=40, rot=(math.pi / 2, 0, 0), parent=hub,
              bevel=r * 0.05)
    for sy in (-1, 1):
        cyl(name + "_cap", (0, sy * w * 0.53, 0), r * 0.22, w * 0.06, chrome(), verts=24, rot=(math.pi / 2, 0, 0),
            parent=hub, bevel=r * 0.03)
        for b in range(5):
            a = 2 * math.pi * b / 5
            cyl(name + "_bolt", (math.cos(a) * r * 0.36, sy * w * 0.53, math.sin(a) * r * 0.36), r * 0.04,
                w * 0.06, chrome(), verts=8, rot=(math.pi / 2, 0, 0), parent=hub)
    return hub


def face(parent, center, normal, size, iris=(0.12, 0.30, 0.75), smile_at=None, smile_w=None, up=(0, 0, 1),
         lid_m=None):
    """Two big cartoon eyes on a windscreen (centre, outward normal, eye radius) and an optional smile.
    Returns the eye pupils' parent empties (rotate them to make the eyes look around) and the eyelids (scale Z to blink)."""
    fr = empty("face", center, parent)
    fr.rotation_euler = frame_from(normal, up)
    white = mat("eye_white", (0.97, 0.97, 0.97), rough=0.25)
    iris_m = mat("iris", iris, rough=0.2)
    pupil = mat("pupil", (0.01, 0.01, 0.01), rough=0.15)
    shine = mat("shine", (1, 1, 1), rough=0.1, emit=3.0)
    looks, lids = [], []
    for sx in (-1, 1):
        e = empty("eye", (sx * size * 1.05, size * 0.35, 0), fr)
        sphere("sclera", (0, 0, 0), size, white, scale=(1, 1.12, 0.32), parent=e)
        look = empty("look", (0, 0, 0), e)
        sphere("iris", (0, -size * 0.05, size * 0.26), size * 0.52, iris_m, scale=(1, 1, 0.25),
               parent=look)
        sphere("pupil", (0, -size * 0.05, size * 0.33), size * 0.30, pupil, scale=(1, 1, 0.2),
               parent=look)
        sphere("shine", (size * 0.14, size * 0.12, size * 0.40), size * 0.11, shine,
               scale=(1, 1, 0.4), parent=look, segs=12)
        looks.append(look)
        lid = empty("lid", (0, size * 1.12, 0), e)   # pivot at the top of the eye: scale Y 0 = open, 1 = shut
        sphere("eyelid", (0, -size * 1.12, 0), size * 1.04, lid_m or white, scale=(1, 1.12, 0.52), parent=lid)
        lid.scale = (1, 0.001, 1)
        lids.append(lid)
    if smile_at:
        m = _smile(fr, (0, -size * 0.95, size * 0.05), size * 1.15, (0, 0, 1))
        m.rotation_euler = (0, 0, 0)                   # already in the face frame
    return looks, lids


def _smile(parent, center, width, normal):
    cu = bpy.data.curves.new("smile", "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = width * 0.06
    cu.bevel_resolution = 4
    sp = cu.splines.new("BEZIER")
    sp.bezier_points.add(2)
    pts = [(-width / 2, width * 0.12, 0), (0, -width * 0.18, 0), (width / 2, width * 0.12, 0)]
    for p, co in zip(sp.bezier_points, pts):
        p.co = co
        p.handle_left_type = p.handle_right_type = "AUTO"
    ob = bpy.data.objects.new("smile", cu)
    bpy.context.scene.collection.objects.link(ob)
    ob.data.materials.append(mat("mouth", (0.05, 0.02, 0.02), rough=0.4))
    ob.location = center
    ob.rotation_euler = frame_from(normal, (0, 0, 1))     # curve drawn in local XY: across and up on the face
    return _link(ob, parent)


def headlight(name, loc, r, parent, normal=(1, 0, 0)):
    rot = frame_from(normal)
    cyl(name + "_ring", loc, r * 1.2, r * 0.5, chrome(), verts=24, rot=rot, parent=parent, bevel=r * 0.15)
    off = Vector(normal).normalized() * r * 0.22
    sphere(name, Vector(loc) + off, r, mat("lamp", (1.0, 0.95, 0.75), rough=0.1, emit=2.0), scale=(1, 1, 0.45),
           parent=parent, segs=20).rotation_euler = rot


def grille(name, loc, w, h, parent, slats=4):
    box(name, loc, (0.06, w, h), chrome(), bevel=0.03, parent=parent)
    for k in range(slats):
        z = loc[2] - h / 2 + h * (k + 0.5) / slats
        box(name + "_slat", (loc[0] + 0.035, loc[1], z), (0.03, w * 0.86, h / slats * 0.35), rubber(), bevel=0.01,
            parent=parent)


# ================================================================ vehicles
def vehicle(kind, rgb, loc=(0, 0, 0), yaw=0.0, name=None, iris=(0.12, 0.30, 0.75), smile=True, rim=None):
    """kind: car, bus, dump, monster, van, fire. Glossy toy body in `rgb`, big face on the windscreen."""
    root = empty(name or kind, loc)
    root.rotation_euler = (0, 0, yaw)
    v = Vehicle(kind, root)
    paint = toy_paint(f"{kind}_paint", rgb)
    v.body_mats.append(paint)
    rim_m = rim or mat("rim_white", (0.95, 0.95, 0.95), rough=0.25)
    getattr(_BUILD, kind)(v, paint, rim_m, iris, smile)
    return v


class _BUILD:
    @staticmethod
    def car(v, paint, rim_m, iris, smile):
        R = v.root
        box("body", (0, 0, 0.55), (2.1, 1.1, 0.5), paint, 0.16, R)
        box("cab", (-0.15, 0, 1.0), (1.15, 0.98, 0.5), paint, 0.2, R)
        box("glass_side", (-0.18, 0, 1.03), (0.95, 1.0, 0.3), glass(), 0.08, R)
        # windscreen leans back; the face sits on it
        ws = box("windscreen", (0.47, 0, 1.0), (0.06, 0.86, 0.42), glass(), 0.03, R, rot=(0, math.radians(-28), 0))
        n = Vector((math.cos(math.radians(28)), 0, math.sin(math.radians(28))))
        v.looks, v.lids = face(R, (0.52, 0, 1.0), n, 0.17, iris, smile_at=smile, lid_m=paint)
        grille("grille", (1.06, 0, 0.5), 0.5, 0.2, R)
        for sy in (-1, 1):
            headlight(f"lamp{sy}", (1.05, sy * 0.38, 0.58), 0.09, R)
            box(f"mirror{sy}", (0.35, sy * 0.58, 0.95), (0.12, 0.1, 0.08), paint, 0.03, R)
        box("bumper_f", (1.1, 0, 0.32), (0.12, 1.12, 0.12), chrome(), 0.05, R)
        box("bumper_r", (-1.1, 0, 0.32), (0.12, 1.12, 0.12), chrome(), 0.05, R)
        for wx in (-0.68, 0.68):
            for wy in (-0.55, 0.55):
                v.wheels.append(wheel("wheel", (wx, wy, 0.34), 0.34, 0.24, rim_m, R))

    @staticmethod
    def bus(v, paint, rim_m, iris, smile):
        R = v.root
        L, W, H = 4.6, 1.4, 1.5
        box("body", (0, 0, 0.35 + H / 2), (L, W, H), paint, 0.2, R)
        box("roof", (0, 0, 0.35 + H + 0.04), (L - 0.3, W - 0.2, 0.1), paint, 0.05, R)
        stripe = mat("stripe", (0.05, 0.05, 0.05), rough=0.4)
        for sy in (-1, 1):
            box(f"stripe{sy}", (0, sy * (W / 2 + 0.005), 0.75), (L - 0.2, 0.02, 0.06), stripe, 0.01, R)
            for k in range(5):
                box(f"win{sy}{k}", (-1.65 + k * 0.72, sy * (W / 2 + 0.005), 1.38), (0.6, 0.03, 0.5), glass(), 0.05, R)
        box("windscreen", (L / 2 + 0.005, 0, 1.35), (0.04, W - 0.25, 0.62), glass(), 0.05, R)
        v.looks, v.lids = face(R, (L / 2 + 0.03, 0, 1.36), (1, 0, 0), 0.24, iris, smile_at=smile, lid_m=paint)
        grille("grille", (L / 2 + 0.01, 0, 0.72), 0.7, 0.28, R)
        box("bumper_f", (L / 2 + 0.06, 0, 0.38), (0.14, W + 0.04, 0.16), chrome(), 0.05, R)
        box("bumper_r", (-L / 2 - 0.06, 0, 0.38), (0.14, W + 0.04, 0.16), chrome(), 0.05, R)
        for sy in (-1, 1):
            headlight(f"lamp{sy}", (L / 2 + 0.01, sy * 0.52, 0.72), 0.1, R)
            box(f"mirror{sy}", (L / 2 - 0.1, sy * 0.85, 1.4), (0.06, 0.06, 0.32), rubber(), 0.02, R)
        box("stop_sign", (1.2, -W / 2 - 0.06, 1.15), (0.3, 0.03, 0.3), mat("stop", (0.8, 0.03, 0.03), 0.3), 0.12, R)
        for wx in (-1.45, 1.45):
            for wy in (-0.62, 0.62):
                v.wheels.append(wheel("wheel", (wx, wy, 0.4), 0.4, 0.28, rim_m, R))

    @staticmethod
    def dump(v, paint, rim_m, iris, smile):
        R = v.root
        grey = mat("chassis", (0.18, 0.18, 0.2), rough=0.5)
        box("chassis", (-0.3, 0, 0.62), (4.0, 1.0, 0.25), grey, 0.04, R)
        box("cab", (1.25, 0, 1.25), (1.1, 1.5, 1.15), paint, 0.2, R)
        box("hood", (1.95, 0, 0.95), (0.6, 1.3, 0.55), paint, 0.18, R)
        box("windscreen", (1.81, 0, 1.52), (0.04, 1.25, 0.5), glass(), 0.04, R, rot=(0, math.radians(-10), 0))
        v.looks, v.lids = face(R, (1.84, 0, 1.52), (math.cos(math.radians(10)), 0, math.sin(math.radians(10))), 0.22, iris, smile_at=smile, lid_m=paint)
        grille("grille", (2.26, 0, 0.95), 0.9, 0.42, R, slats=5)
        box("bumper_f", (2.32, 0, 0.55), (0.16, 1.5, 0.18), chrome(), 0.05, R)
        for sy in (-1, 1):
            headlight(f"lamp{sy}", (2.26, sy * 0.58, 1.08), 0.1, R)
            cyl(f"stack{sy}", (0.66, sy * 0.68, 1.6), 0.07, 1.2, chrome(), verts=16, parent=R)
        # dump bed on a pivot at its back edge, tilt it with v.parts["bed"].rotation_euler.y
        piv = empty("bed_pivot", (-2.2, 0, 0.8), R)
        bed_m = toy_paint("bed_paint", tuple(min(1, c * 0.85) for c in paint.node_tree.nodes["Principled BSDF"]
                                             .inputs["Base Color"].default_value[:3]))
        v.body_mats.append(bed_m)
        box("bed_floor", (1.35, 0, 0.1), (2.7, 1.55, 0.14), bed_m, 0.04, piv)
        for sy in (-1, 1):
            box(f"bed_side{sy}", (1.35, sy * 0.74, 0.55), (2.7, 0.1, 0.9), bed_m, 0.05, piv)
        box("bed_front", (2.65, 0, 0.65), (0.12, 1.55, 1.1), bed_m, 0.05, piv)
        box("bed_back", (0.02, 0, 0.5), (0.1, 1.55, 0.8), bed_m, 0.05, piv)
        v.parts["bed"] = piv
        for wx in (1.6, -1.1, -1.95):
            for wy in (-0.68, 0.68):
                v.wheels.append(wheel("wheel", (wx, wy, 0.46), 0.46, 0.34, rim_m, R))

    @staticmethod
    def monster(v, paint, rim_m, iris, smile):
        R = v.root
        lift = 1.25
        box("body", (0, 0, lift + 0.3), (2.3, 1.3, 0.55), paint, 0.18, R)
        box("cab", (-0.25, 0, lift + 0.82), (1.2, 1.2, 0.6), paint, 0.2, R)
        box("windscreen", (0.37, 0, lift + 0.82), (0.05, 1.05, 0.46), glass(), 0.03, R, rot=(0, math.radians(-25), 0))
        n = Vector((math.cos(math.radians(25)), 0, math.sin(math.radians(25))))
        v.looks, v.lids = face(R, (0.42, 0, lift + 0.82), n, 0.21, iris, smile_at=smile, lid_m=paint)
        grille("grille", (1.16, 0, lift + 0.28), 0.6, 0.26, R)
        box("bumper_f", (1.22, 0, lift + 0.02), (0.14, 1.3, 0.14), chrome(), 0.05, R)
        box("lightbar", (-0.25, 0, lift + 1.17), (0.3, 1.0, 0.1), rubber(), 0.03, R)
        for sy in (-1, 1):
            headlight(f"lamp{sy}", (1.16, sy * 0.45, lift + 0.36), 0.1, R)
            for k in (-1, 0, 1):
                sphere(f"roof_lamp{k}", (-0.18, k * 0.3, lift + 1.25), 0.06, mat("amber", (1, 0.6, 0.1), 0.2, emit=1.5),
                       parent=R, segs=12)
        springm = mat("spring", (0.95, 0.75, 0.05), rough=0.3)
        for wx in (-0.85, 0.85):
            for wy in (-0.85, 0.85):
                cyl("strut", (wx, wy * 0.8, lift - 0.15), 0.05, 0.75, chrome(), verts=12, parent=R)
                for t in range(5):
                    cyl("coil", (wx, wy * 0.8, lift - 0.45 + t * 0.13), 0.12, 0.04, springm, verts=16, parent=R)
                v.wheels.append(wheel("wheel", (wx, wy * 1.05, 0.68), 0.68, 0.6, rim_m, R, monster=True))

    @staticmethod
    def van(v, paint, rim_m, iris, smile):
        """Ambulance-style van: white-ish body comes from rgb, red cross stripe and a light bar."""
        R = v.root
        box("body", (-0.3, 0, 1.2), (3.2, 1.45, 1.6), paint, 0.22, R)
        box("nose", (1.55, 0, 0.82), (0.7, 1.4, 0.8), paint, 0.2, R)
        box("windscreen", (1.32, 0, 1.48), (0.05, 1.25, 0.62), glass(), 0.04, R, rot=(0, math.radians(-32), 0))
        n = Vector((math.cos(math.radians(32)), 0, math.sin(math.radians(32))))
        v.looks, v.lids = face(R, (1.38, 0, 1.48), n, 0.22, iris, smile_at=smile, lid_m=paint)
        grille("grille", (1.91, 0, 0.78), 0.6, 0.24, R)
        red = mat("cross", (0.85, 0.04, 0.04), rough=0.35)
        for sy in (-1, 1):
            box(f"band{sy}", (-0.3, sy * 0.73, 1.05), (3.1, 0.02, 0.16), red, 0.01, R)
            box(f"cross_h{sy}", (-0.6, sy * 0.735, 1.5), (0.5, 0.02, 0.15), red, 0.01, R)
            box(f"cross_v{sy}", (-0.6, sy * 0.735, 1.5), (0.15, 0.02, 0.5), red, 0.01, R)
            headlight(f"lamp{sy}", (1.9, sy * 0.5, 0.92), 0.1, R)
        box("lightbar", (0.8, 0, 2.06), (0.35, 1.0, 0.14), red, 0.05, R)
        box("bumper_f", (1.95, 0, 0.42), (0.14, 1.45, 0.16), chrome(), 0.05, R)
        for wx in (-1.25, 1.25):
            for wy in (-0.66, 0.66):
                v.wheels.append(wheel("wheel", (wx, wy, 0.4), 0.4, 0.28, rim_m, R))

    @staticmethod
    def fire(v, paint, rim_m, iris, smile):
        R = v.root
        box("body", (-0.6, 0, 1.15), (3.6, 1.5, 1.3), paint, 0.18, R)
        box("cab", (1.75, 0, 1.25), (1.1, 1.5, 1.5), paint, 0.2, R)
        box("windscreen", (2.31, 0, 1.55), (0.04, 1.3, 0.6), glass(), 0.04, R)
        v.looks, v.lids = face(R, (2.34, 0, 1.56), (1, 0, 0), 0.23, iris, smile_at=smile, lid_m=paint)
        grille("grille", (2.31, 0, 0.88), 0.8, 0.32, R)
        box("bumper_f", (2.38, 0, 0.45), (0.16, 1.5, 0.18), chrome(), 0.05, R)
        for sy in (-1, 1):
            headlight(f"lamp{sy}", (2.31, sy * 0.55, 1.05), 0.1, R)
            for k in range(4):
                box(f"locker{sy}{k}", (-2.0 + k * 0.85, sy * 0.755, 1.1), (0.7, 0.02, 0.8), chrome(), 0.04, R)
        box("lightbar", (1.75, 0, 2.06), (0.35, 1.2, 0.14), mat("blue_l", (0.1, 0.3, 1.0), 0.2, emit=2.0), 0.05, R)
        # ladder on the roof
        for sy in (-0.35, 0.35):
            box("rail", (-0.6, sy, 1.95), (3.4, 0.07, 0.07), chrome(), 0.02, R)
        for k in range(12):
            box("rung", (-2.2 + k * 0.29, 0, 1.95), (0.04, 0.7, 0.04), chrome(), 0.01, R)
        for wx in (1.7, -1.3, -2.0):
            for wy in (-0.68, 0.68):
                v.wheels.append(wheel("wheel", (wx, wy, 0.45), 0.45, 0.32, rim_m, R))


# ================================================================ animation helpers
def roll_wheels(v, frame0, frame1, distance):
    """Spin the wheels to match `distance` metres travelled between two frames."""
    for w in v.wheels:
        r = w.get("r") or (w.children[0].dimensions.x / 2 / 0.9 if w.children else 0.4)
        for f, a in [(frame0, 0.0), (frame1, distance / max(r, 0.05))]:
            w.rotation_euler = (0, a, 0)
            w.keyframe_insert("rotation_euler", frame=f)


def blink(v, frame, dur=4):
    if hasattr(v, "eye_z"):                     # chibi toys blink by lowering the lid
        from toycolors import toy
        return toy.blink(v, frame, dur + 1)
    for lid in v.lids:
        for f, s in [(frame, 0.0), (frame + dur // 2, 1.0), (frame + dur, 0.0)]:
            lid.scale = (1, max(s, 0.001), 1)
            lid.keyframe_insert("scale", frame=f)


# ================================================================ colour change and props for templates
def wipe(paint, to_rgb, axis="Z"):
    """Turn a toy paint into a two-colour paint split at a world-space plane: new colour where position.axis > threshold.
    Returns the threshold Value node; keyframe node.outputs[0].default_value to move the paint front."""
    nt = paint.node_tree
    b = nt.nodes["Principled BSDF"]
    old = tuple(b.inputs["Base Color"].default_value)
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    thr = nt.nodes.new("ShaderNodeValue")
    thr.outputs[0].default_value = 99.0
    cmp = nt.nodes.new("ShaderNodeMath")
    cmp.operation = "GREATER_THAN"
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    a_in, b_in = [i for i in mix.inputs if i.type == "RGBA"][:2]
    a_in.default_value, b_in.default_value = old, (*to_rgb, 1)
    nt.links.new(geo.outputs["Position"], sep.inputs[0])
    nt.links.new(sep.outputs[axis], cmp.inputs[0])
    nt.links.new(thr.outputs[0], cmp.inputs[1])
    nt.links.new(cmp.outputs[0], mix.inputs["Factor"])
    nt.links.new([o for o in mix.outputs if o.type == "RGBA"][0], b.inputs["Base Color"])
    return thr


def key_value(node, frame, value):
    node.outputs[0].default_value = value
    node.outputs[0].keyframe_insert("default_value", frame=frame)


def road(x0, x1, y=0.0, width=3.2, dashes=True):
    asphalt = ramp_mat("asphalt", (0.16, 0.16, 0.18), (0.22, 0.22, 0.24), scale=6.0, rough=0.85)
    box("road", ((x0 + x1) / 2, y, 0.012), (x1 - x0, width, 0.02), asphalt, 0.005)
    edge = mat("road_edge", (0.95, 0.95, 0.95), rough=0.5)
    for sy in (-1, 1):
        box("road_edge", ((x0 + x1) / 2, y + sy * (width / 2 - 0.12), 0.024), (x1 - x0, 0.1, 0.004), edge, 0.0)
    if dashes:
        yel = mat("road_dash", (1.0, 0.78, 0.05), rough=0.5)
        x = x0 + 0.5
        while x < x1 - 1:
            box("dash", (x + 0.6, y, 0.024), (1.2, 0.14, 0.004), yel, 0.0)
            x += 2.4


def polka_mat(name, rgb, dot=(1, 1, 1), scale=4.0):
    """Surprise-egg plastic: colour with white dots."""
    m = toy_paint(name, rgb)
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    vor = nt.nodes.new("ShaderNodeTexVoronoi")
    vor.inputs["Scale"].default_value = scale
    vor.inputs["Randomness"].default_value = 0.5
    cmp = nt.nodes.new("ShaderNodeMath")
    cmp.operation = "LESS_THAN"
    cmp.inputs[1].default_value = 0.16
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    a_in, b_in = [i for i in mix.inputs if i.type == "RGBA"][:2]
    a_in.default_value, b_in.default_value = (*rgb, 1), (*dot, 1)
    nt.links.new(vor.outputs["Distance"], cmp.inputs[0])
    nt.links.new(cmp.outputs[0], mix.inputs["Factor"])
    nt.links.new([o for o in mix.outputs if o.type == "RGBA"][0], b.inputs["Base Color"])
    return m


def egg_halves(loc, radius, height_scale, m, cut_z):
    """A surprise egg split at local height cut_z (zigzag crack). Returns (top, bottom) with origins at the crack."""
    import bmesh
    halves = []
    for keep_top in (True, False):
        bm = bmesh.new()
        bmesh.ops.create_uvsphere(bm, u_segments=48, v_segments=32, radius=radius)
        for v in bm.verts:
            v.co.z *= height_scale
        # zigzag crack: push the cut height up and down around the egg
        def crack_z(v):
            a = math.atan2(v.co.y, v.co.x)
            return cut_z + 0.08 * radius * (1 if int((a + math.pi) / (2 * math.pi) * 16) % 2 else -1)
        gone = [v for v in bm.verts if (v.co.z < crack_z(v)) == keep_top]
        bmesh.ops.delete(bm, geom=gone, context="VERTS")
        for v in bm.verts:
            v.co.z -= cut_z
        me = bpy.data.meshes.new("egg_top" if keep_top else "egg_bottom")
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new(me.name, me)
        bpy.context.scene.collection.objects.link(ob)
        ob.location = (loc[0], loc[1], loc[2] + cut_z)
        ob.data.materials.append(m)
        md = ob.modifiers.new("shell", "SOLIDIFY")
        md.thickness = radius * 0.05
        inner = mat("egg_inside", (1, 1, 1), rough=0.5)
        ob.data.materials.append(inner)
        md.material_offset = 1
        _smooth(ob)
        halves.append(ob)
    return halves
