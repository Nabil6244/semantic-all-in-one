"""Rainbow playland set (built once, reused by every kids video): procedural, no downloads.
Bright indoor soft-play room: painted sky/hills mural with a rainbow, sun and clouds, ball pit, four-lane slide tower,
foam blocks, number tunnel, hopscotch, stepping stones, baskets, toy train + bus, cubby shelves, bunting, windows,
big wall letters / numbers / shapes. Camera looks +Y; the cast stands around y=0.
Run: blender -b --python sets/playland.py -- <out dir> [render]
"""
import math
import random
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Euler, Matrix, Vector

args = sys.argv[sys.argv.index("--") + 1:]
OUT = Path(args[0])
OUT.mkdir(parents=True, exist_ok=True)
RENDER = "render" in args
rnd = random.Random(7)

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
SET = bpy.data.collections.new("SET-playland")
sc.collection.children.link(SET)

PAL = {"red": "#ff4b4b", "orange": "#ff9a2e", "yellow": "#ffd93b", "green": "#5ccf4f", "teal": "#2ec4b6", "blue": "#3a8dff",
       "purple": "#9b5de5", "pink": "#ff70a6", "white": "#ffffff", "cream": "#fff4dc", "sky": "#9fd8ff", "mint": "#b9f2d0"}
BRIGHT = ["red", "orange", "yellow", "green", "teal", "blue", "purple", "pink"]
_mats = {}


def lin(h):
    h = h.lstrip("#")
    return tuple((int(h[i:i + 2], 16) / 255) ** 2.2 for i in (0, 2, 4)) + (1.0,)


def mat(col, rough=0.45, coat=0.3, emit=0.0):
    hexcol = PAL.get(col, col)
    key = (hexcol, rough, coat, emit)
    if key in _mats:
        return _mats[key]
    m = bpy.data.materials.new(f"M-{col}")
    m.use_nodes = True
    p = m.node_tree.nodes["Principled BSDF"]
    p.inputs["Base Color"].default_value = lin(hexcol)
    p.inputs["Roughness"].default_value = rough
    p.inputs["Coat Weight"].default_value = coat
    if emit:
        p.inputs["Emission Color"].default_value = lin(hexcol)
        p.inputs["Emission Strength"].default_value = emit
    _mats[key] = m
    return m


def link(o, m=None, bevel=0.0, smooth=True):
    SET.objects.link(o)
    if m:
        o.data.materials.append(m)
    if bevel:
        b = o.modifiers.new("bevel", "BEVEL")
        b.width, b.segments, b.limit_method = bevel, 3, "ANGLE"
    if smooth and o.type == "MESH":
        for f in o.data.polygons:
            f.use_smooth = True
        if hasattr(o.data, "set_sharp_from_angle"):
            o.data.set_sharp_from_angle(angle=math.radians(40))
    return o


def mesh_obj(name, build):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    build(bm)
    bm.to_mesh(me)
    bm.free()
    return bpy.data.objects.new(name, me)


def box(name, size, loc, col, bevel=0.04, rot=(0, 0, 0)):
    o = mesh_obj(name, lambda bm: bmesh.ops.create_cube(bm, size=1.0))
    o.scale, o.location, o.rotation_euler = size, loc, rot
    return link(o, mat(col), bevel)


def cyl(name, r, h, loc, col, rot=(0, 0, 0), seg=32, bevel=0.03, r2=None):
    o = mesh_obj(name, lambda bm: bmesh.ops.create_cone(bm, cap_ends=True, segments=seg, radius1=r, radius2=r if r2 is None else r2, depth=h))
    o.location, o.rotation_euler = loc, rot
    return link(o, mat(col), bevel)


def sphere(name, r, loc, col, scale=(1, 1, 1), seg=24, rough=0.5):
    o = mesh_obj(name, lambda bm: bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=seg // 2, radius=r))
    o.location, o.scale = loc, scale
    return link(o, mat(col, rough))


def text(body, loc, col, size=0.5, rot=(math.radians(90), 0, 0), extrude=0.04, bevel=0.01):
    cu = bpy.data.curves.new(f"T-{body}", "FONT")
    cu.body, cu.size, cu.extrude, cu.bevel_depth = body, size, extrude, bevel
    cu.align_x, cu.align_y = "CENTER", "CENTER"
    o = bpy.data.objects.new(f"T-{body}", cu)
    o.location, o.rotation_euler = loc, rot
    SET.objects.link(o)
    o.data.materials.append(mat(col, 0.35))
    return o


def prism(name, pts2d, depth, loc, col, rot=(0, 0, 0), bevel=0.02):
    """Extrude a 2D outline (x, z) by depth along Y."""
    def b(bm):
        vs = [bm.verts.new((x, 0, z)) for x, z in pts2d]
        f = bm.faces.new(vs)
        r = bmesh.ops.extrude_face_region(bm, geom=[f])
        bmesh.ops.translate(bm, verts=[e for e in r["geom"] if isinstance(e, bmesh.types.BMVert)], vec=(0, depth, 0))
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    o = mesh_obj(name, b)
    o.location, o.rotation_euler = loc, rot
    return link(o, mat(col), bevel, smooth=False)


def star_pts(r1, r2, n=5):
    return [((r1 if i % 2 == 0 else r2) * math.sin(i * math.pi / n), (r1 if i % 2 == 0 else r2) * math.cos(i * math.pi / n)) for i in range(2 * n)]


def heart_pts(s, n=40):
    out = []
    for i in range(n):
        t = 2 * math.pi * i / n
        x = 16 * math.sin(t) ** 3
        z = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
        out.append((x * s / 17, z * s / 17))
    return out


def circle_pts(r, n=40):
    return [(r * math.cos(2 * math.pi * i / n), r * math.sin(2 * math.pi * i / n)) for i in range(n)]


# ================= room =================
W, D, H = 16.0, 12.0, 4.6          # x span, y span, height
BACK, LEFT, RIGHT = 6.0, -8.0, 8.0


def floor_tiles():
    cols = ["mint", "#ffe7a3", "#cfe8ff", "#ffd1e3", "#d8f5b0"]
    t = 1.0
    for ix in range(-8, 8):
        for iy in range(-6, 6):
            c = cols[(ix * 3 + iy * 2) % len(cols)]
            box(f"tile{ix}_{iy}", (t * 0.985, t * 0.985, 0.06), (ix + 0.5, iy + 0.5, -0.03), c, 0.012)


floor_tiles()
# walls: sky gradient on the back wall, soft blue sides
wall_m = bpy.data.materials.new("M-skywall")
wall_m.use_nodes = True
nt = wall_m.node_tree
p = nt.nodes["Principled BSDF"]
tc = nt.nodes.new("ShaderNodeTexCoord")
sep = nt.nodes.new("ShaderNodeSeparateXYZ")
ramp = nt.nodes.new("ShaderNodeValToRGB")
ramp.color_ramp.elements[0].color = lin("#d9f2ff")
ramp.color_ramp.elements[1].color = lin("#5fb6ff")
nt.links.new(tc.outputs["Object"], sep.inputs[0])
mr = nt.nodes.new("ShaderNodeMapRange")
mr.inputs["From Min"].default_value, mr.inputs["From Max"].default_value = 0.0, 1.0   # object coords run 0..1 up the wall
nt.links.new(sep.outputs["Z"], mr.inputs["Value"])
nt.links.new(mr.outputs["Result"], ramp.inputs["Fac"])
nt.links.new(ramp.outputs["Color"], p.inputs["Base Color"])
p.inputs["Roughness"].default_value = 0.9
for name, size, loc in (("wall_back", (W, 0.1, H), (0, BACK + 0.05, H / 2)), ("wall_left", (0.1, D, H), (LEFT - 0.05, 0, H / 2)),
                        ("wall_right", (0.1, D, H), (RIGHT + 0.05, 0, H / 2))):
    o = box(name, size, loc, "sky", 0)
    o.data.materials[0] = wall_m
    o.data.transform(Matrix.Translation((0, 0, 0.5)))      # unit cube base at z=0, so the wall stands on the floor
    o.location.z = 0
box("ceiling", (W, D, 0.1), (0, 0, H), "white", 0)
# soft padded skirting all round
for name, size, loc, c in (("pad_back", (W, 0.25, 0.6), (0, BACK - 0.12, 0.3), "teal"), ("pad_left", (0.25, D, 0.6), (LEFT + 0.12, 0, 0.3), "purple"),
                           ("pad_right", (0.25, D, 0.6), (RIGHT - 0.12, 0, 0.3), "purple")):
    box(name, size, loc, c, 0.08)

# ================= back-wall mural =================
wy = BACK - 0.02
for i, (cx, r, c) in enumerate(((-6, 3.2, "#7ad36b"), (-1.5, 2.6, "#5cc45a"), (3.5, 3.4, "#8ee07c"), (7.5, 2.4, "#6bd06a"))):
    o = sphere(f"hill{i}", r, (cx, wy - 0.05, -r * 0.55), c, (1.0, 0.04, 0.75), 48, 0.85)
# rainbow on the wall
RB = ["red", "orange", "yellow", "green", "blue", "purple"]
for i, c in enumerate(RB):
    R1 = 3.2 - i * 0.28
    pts = [(R1 * math.cos(a), R1 * math.sin(a)) for a in [math.pi * k / 48 for k in range(49)]] + \
          [((R1 - 0.26) * math.cos(a), (R1 - 0.26) * math.sin(a)) for a in [math.pi * k / 48 for k in range(48, -1, -1)]]
    prism(f"wall_rainbow{i}", pts, 0.05, (0.0, wy - 0.06, 0.55), c, bevel=0.0)
# sun with rays
sphere("sun", 0.55, (-5.8, wy - 0.1, 3.5), "yellow", (1, 0.15, 1), 32)
for k in range(12):
    a = 2 * math.pi * k / 12
    prism(f"ray{k}", [(-0.07, 0), (0.07, 0), (0, 0.35)], 0.04, (-5.8 + 0.75 * math.sin(a), wy - 0.08, 3.5 + 0.75 * math.cos(a)), "orange",
          rot=(0, a, 0), bevel=0.0)
# clouds
for i, (cx, cz, s) in enumerate(((-3.2, 3.8, 1.0), (2.8, 3.95, 1.2), (6.2, 3.3, 0.9), (-7.0, 2.4, 0.7))):
    for j, (dx, dz, r) in enumerate(((-0.35, 0, 0.32), (0, 0.12, 0.42), (0.38, 0.02, 0.34), (0.15, -0.12, 0.3), (-0.15, -0.1, 0.3))):
        sphere(f"cloud{i}_{j}", r * s, (cx + dx * s, wy - 0.15, cz + dz * s), "white", (1, 0.3, 0.85), 24, 0.9)
# trees painted on the hills
for i, (tx, tz) in enumerate(((-6.8, 1.2), (5.6, 1.4), (7.2, 1.0))):
    cyl(f"trunk{i}", 0.09, 0.9, (tx, wy - 0.12, tz), "#a0642b", bevel=0)
    for j, (dx, dz, r) in enumerate(((0, 0.75, 0.42), (-0.28, 0.55, 0.3), (0.28, 0.55, 0.3))):
        sphere(f"crown{i}_{j}", r, (tx + dx, wy - 0.16, tz + dz), "#3fae49", (1, 0.35, 1), 24, 0.8)

# ================= big wall letters, numbers and shapes =================
for i, (ch, c) in enumerate(zip("ABC", ("red", "blue", "green"))):
    text(ch, (-5.3 + i * 0.85, wy - 0.12, 2.15), c, 0.85, extrude=0.06)
for i, (ch, c) in enumerate(zip("123", ("orange", "purple", "pink"))):
    text(ch, (-1.1 + i * 1.1, wy - 0.12, 3.95), c, 0.7, extrude=0.06)      # 1 2 3 above the rainbow
sx = LEFT + 0.03
for i, (pts, c) in enumerate(((star_pts(0.42, 0.18), "yellow"), (heart_pts(0.4), "red"), (circle_pts(0.36), "blue"),
                              ([(-0.4, -0.32), (0.4, -0.32), (0, 0.38)], "green"), ([(-0.33, -0.33), (0.33, -0.33), (0.33, 0.33), (-0.33, 0.33)], "orange"))):
    prism(f"shape{i}", pts, 0.06, (sx, -3.6 + i * 1.25, 2.9), c, rot=(0, 0, math.radians(90)))
for i, ch in enumerate("DEFG"):
    text(ch, (RIGHT - 0.04, -3.0 + i * 1.1, 3.0), BRIGHT[(i * 3) % 8], 0.7, rot=(math.radians(90), 0, math.radians(-90)), extrude=0.05)

# windows on the right wall
for i, wy2 in enumerate((-2.2, 1.4)):
    box(f"win_frame{i}", (0.12, 1.7, 1.4), (RIGHT - 0.02, wy2, 2.4), "white", 0.03)
    pane = box(f"win_pane{i}", (0.13, 1.5, 1.2), (RIGHT - 0.03, wy2, 2.4), "#bfe9ff", 0)
    pane.data.materials[0] = mat("#cdeeff", 0.1, 0, emit=1.2)
    box(f"win_bar{i}", (0.14, 0.06, 1.2), (RIGHT - 0.04, wy2, 2.4), "white", 0)

# bunting across the room
for line, (y, sag) in enumerate(((1.5, 0.45), (4.2, 0.35), (-1.6, 0.5))):
    n = 26
    for k in range(n):
        t = k / (n - 1)
        x = LEFT + 0.3 + t * (W - 0.6)
        z = H - 0.35 - sag * 4 * t * (1 - t)
        c = BRIGHT[(k + line * 3) % 8]
        prism(f"flag{line}_{k}", [(-0.16, 0), (0.16, 0), (0, -0.34)], 0.015, (x, y, z), c, bevel=0.0)

# ================= ball pit (left back) =================
PX, PY, PR = -4.4, 2.6, 1.7
ring = mesh_obj("pit_ring", lambda bm: bmesh.ops.create_cone(bm, cap_ends=False, segments=64, radius1=PR + 0.25, radius2=PR + 0.25, depth=0.6))
link(ring, mat("teal"), 0)
ring.location = (PX, PY, 0.3)
sol = ring.modifiers.new("thick", "SOLIDIFY")
sol.thickness = 0.35
bev = ring.modifiers.new("bev", "BEVEL")
bev.width, bev.segments = 0.12, 4
cyl("pit_floor", PR + 0.1, 0.05, (PX, PY, 0.03), "blue", bevel=0)
ball_cols = ["red", "yellow", "green", "blue", "orange", "pink", "purple", "teal"]


def balls(bm):
    r = 0.085
    for layer in range(4):
        z = 0.1 + layer * 0.13
        rr = PR - 0.05 - layer * 0.05
        n = int(math.pi * rr * rr / (r * 2.05) ** 2)
        for _ in range(n):
            a, d = rnd.random() * 2 * math.pi, math.sqrt(rnd.random()) * rr
            c = (PX + d * math.cos(a), PY + d * math.sin(a), z + rnd.uniform(-0.03, 0.05) + (0.12 if d < rr * 0.5 else 0) * (layer == 3))
            res = bmesh.ops.create_uvsphere(bm, u_segments=12, v_segments=8, radius=r)
            bmesh.ops.translate(bm, verts=res["verts"], vec=c)
            mi = rnd.randrange(len(ball_cols))
            for f in {f for v in res["verts"] for f in v.link_faces}:
                f.material_index = mi
                f.smooth = True


pit_balls = mesh_obj("pit_balls", balls)
SET.objects.link(pit_balls)
for c in ball_cols:
    pit_balls.data.materials.append(mat(c, 0.25, 0.6))
# loose balls on the floor
for i in range(40):
    a, d = rnd.random() * 2 * math.pi, rnd.uniform(2.0, 3.4)
    sphere(f"loose{i}", 0.085, (PX + d * math.cos(a) * 1.1, PY - abs(d * math.sin(a)) * 0.8, 0.085), rnd.choice(ball_cols), seg=16, rough=0.25)

# ================= four-lane slide tower (right back) =================
TX, TY, TH = 3.6, 3.6, 1.6
box("tower_deck", (3.0, 1.4, 0.15), (TX, TY + 0.4, TH), "yellow", 0.04)
for dx in (-1.45, 1.45):
    for dy in (-0.25, 1.05):
        cyl(f"post{dx}_{dy}", 0.08, TH + 1.2, (TX + dx, TY + dy, (TH + 1.2) / 2), "red", bevel=0.01)
prism("tower_roof", [(-1.7, 0), (1.7, 0), (0, 0.9)], 1.6, (TX, TY - 0.4, TH + 1.2), "blue")
for k in range(4):   # back steps
    box(f"step{k}", (0.9, 0.35, 0.12), (TX + 2.0, TY + 0.7 - k * 0.0, 0.2 + k * 0.38), BRIGHT[k * 2], 0.03)
    box(f"step_riser{k}", (0.9, 0.35, 0.2 + k * 0.38), (TX + 2.0, TY + 0.7, (0.2 + k * 0.38) / 2), "white", 0.02)
lane_cols = ["red", "yellow", "green", "blue"]
for li, c in enumerate(lane_cols):
    lx = TX - 1.1 + li * 0.73
    L = 3.0

    def slide(bm, lx=lx, L=L, wave=li % 2):
        w, rim = 0.6, 0.16
        prof = [(-w / 2, rim), (-w / 2, 0.0), (-w / 2 + 0.08, -0.06), (w / 2 - 0.08, -0.06), (w / 2, 0.0), (w / 2, rim)]
        rows = []
        n = 40
        for i in range(n + 1):
            s = i / n
            y = TY - 0.3 - s * L
            z = TH * (0.5 + 0.5 * math.cos(math.pi * min(s * 1.05, 1.0))) + (0.12 * math.sin(s * math.pi * 3) * (1 - s) if wave else 0) + 0.08
            rows.append([bm.verts.new((lx + px, y, z + pz)) for px, pz in prof])
        for a, b in zip(rows, rows[1:]):
            for j in range(len(prof) - 1):
                bm.faces.new((a[j], a[j + 1], b[j + 1], b[j]))
    o = mesh_obj(f"slide{li}", slide)
    link(o, mat(c, 0.25, 0.8))
    o.modifiers.new("thick", "SOLIDIFY").thickness = 0.04
    o.modifiers.new("smooth", "SUBSURF").levels = 1

# ================= rainbow arch gateway (centre back) =================
for i, c in enumerate(RB):
    R1 = 2.25 - i * 0.16
    me = bpy.data.meshes.new(f"arch{i}")
    bm = bmesh.new()
    seg, ring_n, rr = 48, 12, 0.075
    rings = []
    for a in range(seg + 1):
        th = math.pi * a / seg
        cxz = (R1 * math.cos(th), R1 * math.sin(th))
        rings.append([bm.verts.new((cxz[0] + rr * math.cos(ph) * math.cos(th), rr * math.sin(ph), cxz[1] + rr * math.cos(ph) * math.sin(th)))
                      for ph in [2 * math.pi * k / ring_n for k in range(ring_n)]])
    for a, b in zip(rings, rings[1:]):
        for k in range(ring_n):
            bm.faces.new((a[k], a[(k + 1) % ring_n], b[(k + 1) % ring_n], b[k]))
    bm.to_mesh(me)
    bm.free()
    tor = bpy.data.objects.new(f"arch{i}", me)
    tor.location = (0.0, 4.4, 0.0)
    link(tor, mat(c, 0.35, 0.5))
    tor.scale = (1.0, 1.6, 1.0)
for dx in (-2.25, 2.25):
    cyl(f"arch_cloud{dx}", 0.42, 0.5, (dx, 4.4, 0.25), "white", bevel=0.15)

# ================= foam blocks, tunnel, stepping stones, hopscotch =================
blocks = [((1.0, 0.6, 0.45), (-6.4, -0.6, 0.225), "orange", 0.3), ((0.6, 0.6, 0.6), (-6.1, 0.3, 0.3), "blue", -0.2),
          ((0.6, 0.6, 0.6), (-6.1, 0.3, 0.9), "yellow", 0.15), ((0.7, 0.45, 0.35), (6.2, -0.4, 0.175), "pink", 0.5),
          ((0.5, 0.5, 0.5), (6.6, 0.4, 0.25), "green", -0.3), ((0.5, 0.5, 0.5), (6.6, 0.4, 0.75), "red", 0.2),
          ((0.45, 0.45, 0.45), (-2.6, 0.9, 0.225), "purple", 0.4)]
for i, (sz, loc, c, rz) in enumerate(blocks):
    box(f"foam{i}", sz, loc, c, 0.06, rot=(0, 0, rz))
for i, c in enumerate(("teal", "orange", "pink")):   # foam wedges / ramps
    prism(f"wedge{i}", [(-0.4, 0), (0.4, 0), (-0.4, 0.4)], 0.6, (-7.1 + i * 0.0, -2.6 + i * 0.75, 0.0), c, rot=(0, 0, math.radians(-90)))
cyl("roll_a", 0.28, 0.9, (5.3, 1.3, 0.28), "purple", rot=(math.radians(90), 0, 0.4), bevel=0.06)
cyl("roll_b", 0.28, 0.9, (5.6, 1.6, 0.84), "yellow", rot=(math.radians(90), 0, 0.2), bevel=0.06)

# number tunnel (front right) with 1-5 on it
TNX, TNY = 3.4, -0.9
for k in range(5):
    seg_o = mesh_obj(f"tunnel{k}", lambda bm: bmesh.ops.create_cone(bm, cap_ends=False, segments=48, radius1=0.55, radius2=0.55, depth=0.3))
    seg_o.location, seg_o.rotation_euler = (TNX - 0.6 + k * 0.3, TNY, 0.55), (0, math.radians(90), 0)
    link(seg_o, mat(BRIGHT[k * 2 % 8], 0.5))
    seg_o.modifiers.new("thick", "SOLIDIFY").thickness = 0.06
    text(str(k + 1), (TNX - 0.6 + k * 0.3, TNY - 0.57, 0.62), "white", 0.24, extrude=0.015, bevel=0.004)

# stepping stones + hopscotch (front floor)
for i in range(7):
    a = i * 0.9
    cyl(f"stone{i}", 0.26, 0.08, (-5.2 + i * 0.62, -2.9 + 0.35 * math.sin(a), 0.04), BRIGHT[i % 8], bevel=0.03)
hop = [(0, 0), (0, 1), (-0.5, 2), (0.5, 2), (0, 3), (-0.5, 4), (0.5, 4), (0, 5)]
for i, (hx, hy) in enumerate(hop):
    box(f"hop{i}", (0.48, 0.48, 0.02), (3.0 + hx * 1.0, -3.6 + hy * 0.5, 0.01), "white", 0.01)
    text(str(i + 1), (3.0 + hx * 1.0, -3.6 + hy * 0.5, 0.03), BRIGHT[i % 8], 0.3, rot=(0, 0, 0), extrude=0.008, bevel=0.003)

# baskets with balls (table at front left, like the reference)
box("table_top", (1.8, 0.8, 0.08), (-2.9, -1.4, 0.55), "#e9f7ff", 0.03)
for dx in (-0.8, 0.8):
    for dy in (-0.32, 0.32):
        cyl(f"tleg{dx}{dy}", 0.05, 0.55, (-2.9 + dx, -1.4 + dy, 0.275), "yellow", bevel=0.01)
for i, c in enumerate(("red", "yellow", "green")):
    bx = -3.45 + i * 0.55
    bk = mesh_obj(f"basket{i}", lambda bm: bmesh.ops.create_cone(bm, cap_ends=False, segments=24, radius1=0.2, radius2=0.24, depth=0.26))
    bk.location = (bx, -1.4, 0.72)
    link(bk, mat(c, 0.4))
    wf = bk.modifiers.new("weave", "WIREFRAME")
    wf.thickness = 0.02
    cyl(f"basket_base{i}", 0.2, 0.02, (bx, -1.4, 0.6), c, bevel=0)
    for j in range(3):
        sphere(f"bball{i}_{j}", 0.075, (bx + rnd.uniform(-0.07, 0.07), -1.4 + rnd.uniform(-0.07, 0.07), 0.67 + j * 0.06), rnd.choice(ball_cols), seg=16, rough=0.25)

# cubby shelves with bins (left wall)
box("cubby", (0.45, 2.4, 1.3), (LEFT + 0.5, -1.2, 0.65), "white", 0.03)
for r in range(2):
    for cidx in range(4):
        box(f"bin{r}{cidx}", (0.42, 0.52, 0.5), (LEFT + 0.48, -2.1 + cidx * 0.6, 0.35 + r * 0.6), BRIGHT[(r * 4 + cidx) % 8], 0.05)

# ================= toys: train, bus, teddy =================
def wheel(name, loc, c="red"):
    cyl(name, 0.1, 0.06, loc, c, rot=(0, math.radians(90), 0), bevel=0.015)


TRX, TRY = -3.0, -3.3
box("train_engine", (0.55, 0.32, 0.26), (TRX, TRY, 0.25), "red", 0.05)
box("train_cab", (0.26, 0.34, 0.3), (TRX - 0.15, TRY, 0.52), "blue", 0.04)
box("train_cab_roof", (0.32, 0.4, 0.05), (TRX - 0.15, TRY, 0.69), "yellow", 0.02)
cyl("train_boiler", 0.13, 0.32, (TRX + 0.14, TRY, 0.48), "green", rot=(0, math.radians(90), 0), bevel=0.02)
cyl("train_chimney", 0.05, 0.14, (TRX + 0.22, TRY, 0.66), "yellow", bevel=0.01)
for k, c in enumerate(("yellow", "teal")):
    cx = TRX - 0.7 - k * 0.62
    box(f"wagon{k}", (0.5, 0.3, 0.22), (cx, TRY, 0.23), c, 0.04)
    for j in range(3):
        sphere(f"cargo{k}{j}", 0.07, (cx - 0.14 + j * 0.14, TRY, 0.4), BRIGHT[(k * 3 + j) % 8], seg=16, rough=0.3)
    for wx in (-0.16, 0.16):
        for wy3 in (-0.17, 0.17):
            wheel(f"ww{k}{wx}{wy3}", (cx + wx, TRY + wy3, 0.1), "#333333")
for wx in (-0.18, 0.18):
    for wy3 in (-0.18, 0.18):
        wheel(f"ew{wx}{wy3}", (TRX + wx, TRY + wy3, 0.1))
# toy bus
BX, BY = 6.4, -2.3
box("bus_body", (0.9, 0.42, 0.42), (BX, BY, 0.33), "#ffc21a", 0.06, rot=(0, 0, 0.5))
for k in range(4):
    box(f"bus_win{k}", (0.15, 0.43, 0.12), (BX - 0.3 + k * 0.2, BY, 0.43), "#bfe9ff", 0.01, rot=(0, 0, 0.5))
# teddy bear on the cubby
TB = Vector((LEFT + 0.55, -0.4, 1.45))
sphere("teddy_body", 0.2, TB, "#c68b59", (1, 0.9, 1.1), 24, 0.95)
sphere("teddy_head", 0.15, TB + Vector((0, 0, 0.3)), "#c68b59", seg=24, rough=0.95)
for dx in (-0.1, 0.1):
    sphere(f"teddy_ear{dx}", 0.06, TB + Vector((dx, 0, 0.43)), "#a8703f", seg=16, rough=0.95)
# potted bushes
for i, (x, y) in enumerate(((-7.3, 4.8), (7.3, 4.8), (-7.3, -3.6))):
    cyl(f"pot{i}", 0.3, 0.5, (x, y, 0.25), "orange", r2=0.38, bevel=0.03)
    sphere(f"bush{i}", 0.5, (x, y, 0.85), "#47b84a", seg=24, rough=0.8)


# ================= more: rug, ABC cubes, block tower, balloons, hanging stars, crayons, hoops, rocking horse =================
rug = mesh_obj("rug", lambda bm: bmesh.ops.create_circle(bm, cap_ends=True, segments=64, radius=1.0))
link(rug, None, 0, smooth=False)
rug.location, rug.scale = (0.2, -1.2, 0.012), (2.2, 1.5, 1)
rug.data.materials.append(mat("#ffe08a", 0.95, 0))
for i, c in enumerate(("pink", "teal", "yellow")):      # concentric rug rings
    rr = mesh_obj(f"rug_ring{i}", lambda bm, k=i: bmesh.ops.create_circle(bm, cap_ends=True, segments=64, radius=0.8 - k * 0.25))
    link(rr, mat(c, 0.95, 0), 0, smooth=False)
    rr.location, rr.scale = (0.2, -1.2, 0.014 + i * 0.002), (2.2, 1.5, 1)
for i, (ch, c) in enumerate(zip("ABCDEF", ("red", "blue", "green", "orange", "purple", "pink"))):   # alphabet cubes
    x, z = -6.6 + (i % 3) * 0.42, 0.2 + (i // 3) * 0.4
    if i >= 3:
        x += 0.2
    box(f"abc{i}", (0.38, 0.38, 0.38), (x, -1.9, z), "cream", 0.04, rot=(0, 0, 0.15 * (i % 2)))
    text(ch, (x, -1.9 - 0.2, z), c, 0.28, extrude=0.02, bevel=0.004)
for i in range(7):                                        # wobbly block tower
    box(f"tower_block{i}", (0.32, 0.32, 0.22), (2.6 + 0.02 * math.sin(i * 1.7), 1.2, 0.11 + i * 0.22), BRIGHT[i % 8], 0.03, rot=(0, 0, 0.25 * math.sin(i)))
for gi, (gx, gy) in enumerate(((-2.4, 4.3), (2.4, 4.3), (-7.0, 1.2))):   # balloon bunches
    for k in range(5):
        a = 2 * math.pi * k / 5
        bpos = Vector((gx + 0.25 * math.cos(a), gy + 0.2 * math.sin(a), 2.2 + 0.25 * math.sin(a * 2) + (0.3 if k == 0 else 0)))
        sphere(f"balloon{gi}{k}", 0.24, bpos, BRIGHT[(gi * 2 + k) % 8], (1, 1, 1.18), 24, 0.15)
        s_ = mesh_obj(f"string{gi}{k}", lambda bm, p0=bpos, p1=Vector((gx, gy, 0.5)): bm.edges.new((bm.verts.new(p0 - Vector((0, 0, 0.28))), bm.verts.new(p1))))
        link(s_, mat("white"), 0, smooth=False)
        sk = s_.modifiers.new("skin", "WIREFRAME") if False else None
    cyl(f"balloon_weight{gi}", 0.08, 0.12, (gx, gy, 0.5), "pink", bevel=0.02)
for k in range(9):                                        # stars hanging from the ceiling
    x, y = -6 + k * 1.5, rnd.uniform(-1.0, 3.5)
    z = H - 0.9 - rnd.uniform(0, 0.6)
    prism(f"hang_star{k}", star_pts(0.22, 0.1), 0.04, (x, y, z), ["yellow", "pink", "teal", "orange"][k % 4], rot=(0, 0, rnd.uniform(-0.4, 0.4)))
    st = mesh_obj(f"hang_line{k}", lambda bm, x=x, y=y, z=z: bm.edges.new((bm.verts.new((x, y, z + 0.22)), bm.verts.new((x, y, H)))))
    link(st, mat("white"), 0, smooth=False)
for i, c in enumerate(("red", "orange", "yellow", "green", "blue", "purple")):   # giant crayons on the right wall
    y0 = -3.6 + i * 0.32
    cyl(f"crayon{i}", 0.1, 1.2, (RIGHT - 0.2, y0, 1.25), c, bevel=0.01)
    cyl(f"crayon_tip{i}", 0.1, 0.22, (RIGHT - 0.2, y0, 1.96), c, r2=0.0, bevel=0.0)
    cyl(f"crayon_band{i}", 0.103, 0.12, (RIGHT - 0.2, y0, 1.35), "white", bevel=0.0)
for i, c in enumerate(("pink", "green", "yellow")):        # hula hoops lying and leaning
    hoop = mesh_obj(f"hoop{i}", lambda bm: None)
    me = bpy.data.meshes.new(f"hoop{i}")
    hoop = bpy.data.objects.new(f"hoop{i}", me)
    bm = bmesh.new()
    bmesh.ops.create_circle(bm, segments=64, radius=0.45)
    bm.to_mesh(me)
    bm.free()
    link(hoop, mat(c, 0.3, 0.5), 0, smooth=False)
    hoop.location = (-1.8 + i * 0.25, 2.2 + i * 0.1, 0.03 + i * 0.03) if i < 2 else (6.9, 2.8, 0.45)
    if i == 2:
        hoop.rotation_euler = (math.radians(75), 0, math.radians(90))
    sk = hoop.modifiers.new("skin", "SKIN")
    for v in hoop.data.skin_vertices[0].data:
        v.radius = (0.025, 0.025)
    hoop.modifiers.new("smooth", "SUBSURF").levels = 1
# rocking horse
RH = Vector((-4.6, -0.2, 0))
arc = mesh_obj("rocker", lambda bm: None)
me = bpy.data.meshes.new("rocker")
bm = bmesh.new()
prev = None
for k in range(21):
    t = -1 + k / 10
    v = bm.verts.new((RH.x + t * 0.55, RH.y, 0.06 + 0.12 * t * t))
    if prev:
        bm.edges.new((prev, v))
    prev = v
bm.to_mesh(me)
bm.free()
for dy in (-0.16, 0.16):
    ro = bpy.data.objects.new(f"rocker{dy}", me)
    ro.location.y = dy
    link(ro, mat("red", 0.4), 0, smooth=False)
    skm = ro.modifiers.new("skin", "SKIN")
    for v in ro.data.skin_vertices[0].data:
        v.radius = (0.035, 0.035)
box("horse_body", (0.6, 0.24, 0.26), RH + Vector((0, 0, 0.52)), "white", 0.1)
box("horse_saddle", (0.25, 0.27, 0.06), RH + Vector((-0.02, 0, 0.67)), "red", 0.02)
cyl("horse_neck", 0.09, 0.32, RH + Vector((0.3, 0, 0.72)), "white", rot=(0, math.radians(35), 0), bevel=0.02)
box("horse_head", (0.28, 0.17, 0.16), RH + Vector((0.44, 0, 0.88)), "white", 0.06)
box("horse_mane", (0.22, 0.05, 0.1), RH + Vector((0.27, 0, 0.9)), "orange", 0.02, rot=(0, math.radians(35), 0))
for dx in (-0.2, 0.2):
    for dy in (-0.09, 0.09):
        cyl(f"horse_leg{dx}{dy}", 0.035, 0.38, RH + Vector((dx, dy, 0.3)), "white", bevel=0.01)

# ================= light, world, camera =================
w = bpy.data.worlds.new("w")
sc.world = w
w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = lin("#cfeaff")
w.node_tree.nodes["Background"].inputs[1].default_value = 0.9
for name, rot, en, col in (("sun", (50, 0, -30), 3.2, "#fff1d6"), ("fill", (70, 0, 140), 0.8, "#d6ecff")):
    ld = bpy.data.lights.new(name, "SUN")
    ld.energy, ld.angle, ld.color = en, math.radians(8), lin(col)[:3]
    lo = bpy.data.objects.new(name, ld)
    SET.objects.link(lo)
    lo.rotation_euler = [math.radians(a) for a in rot]
for i, x in enumerate((-4.5, 0, 4.5)):
    ld = bpy.data.lights.new(f"ceil{i}", "AREA")
    ld.energy, ld.size, ld.color = 380, 3.0, lin("#fff6e8")[:3]
    lo = bpy.data.objects.new(f"ceil{i}", ld)
    SET.objects.link(lo)
    lo.location = (x, 0.5, H - 0.15)

cd = bpy.data.cameras.new("CAM-wide")
cam = bpy.data.objects.new("CAM-wide", cd)
SET.objects.link(cam)
cd.lens = 24
cam.location = (0, -7.6, 1.6)
cam.rotation_euler = Euler((math.radians(86), 0, 0), "XYZ")
sc.camera = cam
sc.render.engine = "BLENDER_EEVEE"
sc.view_settings.view_transform = "Standard"         # saturated kids-show colour (AgX greys it out)
sc.view_settings.exposure = -0.55

try:
    sc.eevee.use_raytracing = True
    sc.eevee.use_shadows = True
except AttributeError:
    pass
sc.render.resolution_x, sc.render.resolution_y = 1280, 720
bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "playland.blend"))
print("OBJECTS", len(SET.objects))
if RENDER:
    sc.render.filepath = str(OUT / "wide.png")
    bpy.ops.render.render(write_still=True)
    print("RENDERED", OUT / "wide.png")
