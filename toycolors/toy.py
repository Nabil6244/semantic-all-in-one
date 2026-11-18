"""Chibi toy vehicles and the toy playground world (graphics pass 2, see REFERENCE.md "Gap study 2").

Vehicles are cab-forward toys whose cab is a big head: eyes sit inside a light-blue windscreen, a body-coloured upper
lid shapes each eye, irises are layered (dark ring, colour, light band, pupil, two shines), and a real mouth with
tongue and teeth sits on the front body. Every vehicle faces +X from its root empty and sits on z=0.

    from toycolors import toy
    toy.grade(); toy.playground(); v = toy.chibi("fire", (0.85, 0.04, 0.03), name="Rolly", loc=(0, 0, 0))
"""
import math

import bpy
import bmesh
from mathutils import Vector

from toycolors import kit

NAMES = {"fire": "Rolly", "bus": "Toot", "dump": "Bumpy", "tanker": "Splash", "crane": "Hooky", "car": "Zip"}


# ================================================================ look
def grade(punch=True):
    """Standard view, slightly under-exposed so toy colours stay saturated instead of washing toward white."""
    vs = bpy.context.scene.view_settings
    try:
        vs.view_transform = "Standard"
        vs.look = "None"
    except TypeError:
        vs.view_transform = "Standard"
    vs.exposure = -0.45


def plastic(name, rgb, rough=0.3):
    """Soft glossy toy plastic: clear coat, a touch of sheen and subsurface so it doesn't read as hard paint."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1)
    b.inputs["Roughness"].default_value = rough
    for k, val in [("Coat Weight", 0.18), ("Coat Roughness", 0.1), ("Sheen Weight", 0.0),
                   ("Subsurface Weight", 0.06), ("Subsurface Scale", 0.02)]:
        if k in b.inputs:
            b.inputs[k].default_value = val
    if "Subsurface Radius" in b.inputs:
        b.inputs["Subsurface Radius"].default_value = rgb
    return m


def soft(ob, levels=2):
    """Pillow-soft toy shape: subdivision on top of the bevel. TOY_SOFT caps the level (speed tests)."""
    import os
    levels = min(levels, int(os.environ.get("TOY_SOFT", levels)))
    if levels <= 0:
        return ob
    md = ob.modifiers.new("soft", "SUBSURF")
    md.levels = md.render_levels = levels
    return ob


def sbox(name, loc, size, m, bevel, parent, rot=(0, 0, 0)):
    return soft(kit.box(name, loc, size, m, bevel, parent, rot), 2)


def panel(name, center, axis, w, h, r, m, parent, target, offset=0.012):
    """Rounded-rectangle panel (windscreen, window) that wraps onto the curved body `target`.
    The outline is a smooth curve (no stepped edges); the inside is subdivided so it can bend with the body.
    axis 'x' = faces +X (front), 'y' = faces the side it sits on."""
    pts = []
    for cx_, cy_, a0 in [(w / 2 - r, h / 2 - r, 0), (-w / 2 + r, h / 2 - r, 90), (-w / 2 + r, -h / 2 + r, 180),
                         (w / 2 - r, -h / 2 + r, 270)]:
        for k in range(13):
            a = math.radians(a0 + 90 * k / 12)
            pts.append((cx_ + r * math.cos(a), cy_ + r * math.sin(a)))
    bm = bmesh.new()
    cx, cy, cz = center
    s_ = 1 if cy > 0 else -1
    vs = [bm.verts.new((cx + 0.05, cy + a, cz + b) if axis == "x" else (cx + a, cy + s_ * 0.05, cz + b)) for a, b in pts]
    f = bm.faces.new(vs)
    bmesh.ops.triangulate(bm, faces=[f])
    bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=6, use_grid_fill=True)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    ob.data.materials.append(m)
    ob.parent = parent
    sw = ob.modifiers.new("hug", "SHRINKWRAP")
    sw.target, sw.wrap_method, sw.offset = target, "NEAREST_SURFACEPOINT", offset
    so = ob.modifiers.new("thick", "SOLIDIFY")
    so.thickness, so.offset = 0.02, 1.0
    for p in ob.data.polygons:
        p.use_smooth = True
    return ob


# ================================================================ face
def _iris_mat(rgb, r):
    m = bpy.data.materials.new("iris_layered")
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Roughness"].default_value = 0.15
    if "Coat Weight" in b.inputs:
        b.inputs["Coat Weight"].default_value = 1.0
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (1 / r, 1 / r, 1 / r)
    gr = nt.nodes.new("ShaderNodeTexGradient")
    gr.gradient_type = "SPHERICAL"
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    els = ramp.color_ramp.elements
    els[0].position, els[0].color = 0.0, (*[c * 0.15 for c in rgb], 1)          # dark limbal ring at the edge
    els[1].position, els[1].color = 0.12, (*rgb, 1)
    e = els.new(0.45)
    e.color = (*[min(1, c * 0.6 + 0.45) for c in rgb], 1)                         # light band
    e = els.new(0.75)
    e.color = (*[c * 0.7 for c in rgb], 1)
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    nt.links.new(mp.outputs["Vector"], gr.inputs["Vector"])
    nt.links.new(gr.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], b.inputs["Base Color"])
    return m


def _disc(name, loc, r, m, parent, depth=0.004):
    return kit.cyl(name, loc, r, depth, m, verts=40, rot=(0, math.pi / 2, 0), parent=parent)


def eyes(v, panel_x, cy, cz, er, gap, body_m, iris=(0.15, 0.45, 0.85), parent=None):
    """Two eyes set into a windscreen whose front face is at x=panel_x. er = eye radius."""
    P = parent or v.root
    white = kit.mat("eye_white2", (0.98, 0.98, 0.98), rough=0.2, coat=1.0)
    pupil = kit.mat("pupil2", (0.005, 0.005, 0.01), rough=0.1, coat=1.0)
    shine = kit.mat("shine2", (1, 1, 1), rough=0.1, emit=6.0)
    im = _iris_mat(iris, er * 0.62)
    depth = 0.38                                                   # eye bulge, as a share of the radius
    v.looks, v.lids = [], []
    for sy in (-1, 1):
        y = cy + sy * gap
        c = Vector((panel_x - er * depth * 0.4, y, cz))
        kit.sphere("eye", c, er, white, scale=(depth, 1.0, 1.12), parent=P)
        look = kit.empty("look", c, P)
        front = er * depth + 0.002
        iris_o = _disc("iris", (front, 0, 0), er * 0.62, im, look)
        _disc("pupil", (front + 0.002, 0, 0), er * 0.32, pupil, look)
        _disc("shine_big", (front + 0.004, -sy * er * 0.16, er * 0.18), er * 0.12, shine, look)
        _disc("shine_small", (front + 0.004, sy * er * 0.12, -er * 0.2), er * 0.055, shine, look)
        v.looks.append(look)
        # body-coloured upper lid cuts the top of the eye into a friendly lens shape; move it down to blink
        lid = kit.empty("lid", (c.x, y, cz + er * 0.88), P)
        kit.sphere("eyelid2", (0, 0, 0), er * 1.03, body_m, scale=(depth * 1.03, 1.03, 0.4), parent=lid)
        v.lids.append(lid)
    v.eye_z, v.eye_r = cz, er


def mouth(v, x, cy, cz, w, h, lip_m, parent=None):
    """D-shaped open smile on the front face (plane x): dark inside, pink tongue, teeth strip, lip outline."""
    P = parent or v.root
    inside = kit.mat("mouth_in", (0.22, 0.02, 0.03), rough=0.5)
    tongue = kit.mat("tongue", (0.95, 0.35, 0.40), rough=0.4, coat=0.5)
    teeth = kit.mat("teeth", (0.98, 0.97, 0.94), rough=0.3)
    pts = []
    n = 24
    for i in range(n + 1):                                        # bottom: half ellipse
        a = math.pi * i / n
        pts.append((cy + (w / 2) * math.cos(a), cz - h * math.sin(a)))
    for i in range(1, n):                                         # top edge: corners curl up into a smile
        u = 1 - 2 * i / n
        pts.append((cy - (w / 2) * u, cz + 0.22 * h * u * u))
    bm = bmesh.new()
    vs = [bm.verts.new((x, py, pz)) for py, pz in pts]
    f = bm.faces.new(vs)
    ext = bmesh.ops.extrude_face_region(bm, geom=[f])
    for e in ext["geom"]:
        if isinstance(e, bmesh.types.BMVert):
            e.co.x -= 0.05
    me = bpy.data.meshes.new("mouth")
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new("mouth", me)
    bpy.context.scene.collection.objects.link(ob)
    ob.data.materials.append(inside)
    ob.parent = P
    kit.sphere("tongue", (x + 0.004, cy, cz - h * 0.68), w * 0.26, tongue, scale=(0.25, 1.25, 0.55), parent=P)
    kit.box("teeth", (x + 0.006, cy, cz - h * 0.08), (0.012, w * 0.62, h * 0.18), teeth, 0.005, P)
    # lip outline
    cu = bpy.data.curves.new("lip", "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = h * 0.07
    cu.bevel_resolution = 3
    sp = cu.splines.new("POLY")
    sp.points.add(len(pts) - 1)
    for p, (py, pz) in zip(sp.points, pts):
        p.co = (x + 0.006, py, pz, 1)
    sp.use_cyclic_u = True
    lo = bpy.data.objects.new("lip", cu)
    bpy.context.scene.collection.objects.link(lo)
    lo.data.materials.append(lip_m)
    lo.parent = P


def decal(text, loc, rot, size, parent, rgb=(1, 1, 1), outline=(0.1, 0.1, 0.1)):
    cu = bpy.data.curves.new("decal", "FONT")
    cu.body = text
    cu.size = size
    cu.extrude = 0.006
    cu.bevel_depth = 0.004
    cu.align_x, cu.align_y = "CENTER", "CENTER"
    ob = bpy.data.objects.new("decal", cu)
    bpy.context.scene.collection.objects.link(ob)
    ob.data.materials.append(kit.mat("decal_" + "%.2f%.2f%.2f" % rgb, rgb, rough=0.35))
    ob.location, ob.rotation_euler = loc, rot
    ob.parent = parent
    return ob


def star(name, loc, r, side, m, parent):
    """A chunky five-point star decal standing on a body side (side = -1 or +1 in Y)."""
    bm = bmesh.new()
    pts = []
    for k in range(10):
        a = math.pi / 2 + k * math.pi / 5
        rr = r if k % 2 == 0 else r * 0.48
        pts.append((loc[0] + rr * math.cos(a), loc[2] + rr * math.sin(a)))
    vs = [bm.verts.new((x, loc[1], z)) for x, z in pts]
    f = bm.faces.new(vs)
    ext = bmesh.ops.extrude_face_region(bm, geom=[f])
    for e in ext["geom"]:
        if isinstance(e, bmesh.types.BMVert):
            e.co.y += side * 0.012
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    ob.data.materials.append(m)
    ob.parent = parent
    bev = ob.modifiers.new("soft", "BEVEL")
    bev.width, bev.segments = 0.004, 2
    return ob


def side_art(kind, up, lower):
    """Side decals like the reference toys: a white swoosh stripe hugging the lower body and a star near the back."""
    white = kit.mat("decal_white", (0.97, 0.97, 0.95), rough=0.3, coat=0.6)
    gold = kit.mat("decal_star", (1.0, 0.82, 0.12), rough=0.25, coat=0.8)
    for sy in (-1, 1):
        if kind == "bus":
            star(f"star{sy}", (-0.62, sy * 0.548, 0.5), 0.13, sy, gold, up)
            continue
        panel("side_stripe", (-0.12, sy * 0.53, 0.4), "y", 1.35, 0.07, 0.03, white, up, lower, offset=0.006)
        star(f"star{sy}", (-0.46, sy * 0.535, 0.64), 0.12, sy, gold, up)


def blink(v, t_frame, dur=5):
    for lid in v.lids:
        z0 = lid.location.z
        for f, z in [(t_frame, z0), (t_frame + dur // 2, v.eye_z + 0.02), (t_frame + dur, z0)]:
            lid.location.z = z
            lid.keyframe_insert("location", index=2, frame=f)


# ================================================================ chibi vehicles
def chibi(kind, rgb, loc=(0, 0, 0), yaw=0.0, name=None, monster=False, iris=(0.15, 0.45, 0.85), rim=None,
          decal_name=True, art=True):
    """kind: fire, bus, dump, tanker, crane, car. monster=True lifts it on huge tyres with a coloured chassis."""
    root = kit.empty(name or kind, loc)
    root.rotation_euler = (0, 0, yaw)
    v = kit.Vehicle(kind, root)
    body = plastic(f"{kind}_body", rgb)
    v.body_mats.append(body)
    dark = plastic(f"{kind}_trim", tuple(c * 0.35 for c in rgb), rough=0.4)
    grey = plastic("bumper_grey", (0.12, 0.12, 0.14), rough=0.45)
    glass = kit.mat("windscreen2", (0.50, 0.78, 0.96), rough=0.04, coat=1.0)
    lift = 0.42 if monster else 0.0
    wr, ww = (0.5, 0.44) if monster else (0.33, 0.28)
    rim_m = rim or plastic(f"{kind}_rim", rgb if monster else (0.95, 0.95, 0.95), rough=0.25)
    R = root
    up = kit.empty("body_up", (0, 0, lift), R)        # everything above the wheels hangs off this
    v.parts["up"] = up
    L = 1.75
    if kind == "bus":
        cab = sbox("bus_body", (0, 0, 0.98), (2.3, 1.08, 1.32), body, 0.34, up)
        for sy in (-1, 1):
            for k in range(3):
                panel("bus_win", (-0.75 + k * 0.48, sy * 0.54, 1.25), "y", 0.38, 0.36, 0.08, glass, up, cab)
            kit.box("bus_stripe", (-0.1, sy * 0.545, 0.78), (1.9, 0.012, 0.05), dark, 0.0, up)
        front = 1.15
        panel_z, panel_h = 1.28, 0.55
        roof_z = 1.64
    else:
        lower = sbox("lower_body", (0, 0, 0.58), (L, 1.06, 0.58), body, 0.2, up)  # flat front keeps the mouth seated
        cab = sbox("cab", (0.47, 0, 1.12), (0.86, 1.06, 0.92), body, 0.33, up)
        front = 0.9
        panel_z, panel_h = 1.24, 0.5
        roof_z = 1.58
        _rear(kind, v, body, dark, up)
        for sy in (-1, 1):
            panel("cab_side_win", (0.5, sy * 0.54, 1.27), "y", 0.42, 0.32, 0.09, glass, up, cab)
            kit.box("door_line", (0.2, sy * 0.533, 0.95), (0.012, 0.012, 0.5), dark, 0.0, up)
            sbox("door_handle", (0.32, sy * 0.545, 0.95), (0.1, 0.03, 0.035), grey, 0.012, up)
    # windscreen panel the eyes sit in
    panel("windscreen", (front, 0, panel_z), "x", 0.9, panel_h, 0.16, glass, up, cab)
    eyes(v, front + 0.02, 0, panel_z - 0.01, 0.2, 0.215, body, iris, parent=up)
    mouth(v, front + 0.005 if kind != "bus" else front + 0.01, 0, 0.74, 0.44, 0.19, dark, parent=up)
    for sy in (-1, 1):
        kit.headlight(f"lamp{sy}", (front - 0.01, sy * 0.38, 0.75), 0.075, up)
        # mirror on a stalk
        stalk = kit.cyl("mirror_stalk", (front - 0.02, sy * 0.6, panel_z + 0.08), 0.018, 0.22, grey, verts=8,
                        rot=(math.radians(90), 0, 0), parent=up)
        sbox("mirror", (front + 0.02, sy * 0.72, panel_z + 0.02), (0.07, 0.06, 0.24), grey, 0.025, up)
    sbox("bumper", (front + 0.06, 0, 0.38), (0.13, 1.1, 0.15), grey, 0.06, up)
    # roof beacon
    kit.cyl("beacon_base", (front - 0.45, 0, roof_z + 0.02), 0.08, 0.04, grey, verts=20, parent=up)
    kit.sphere("beacon", (front - 0.45, 0, roof_z + 0.06), 0.075,
               kit.mat("beacon_glow", (1.0, 0.45, 0.05), rough=0.15, emit=3.0), scale=(1, 1, 0.9), parent=up, segs=20)
    if decal_name:
        nm = NAMES.get(kind, kind.title()) if name is None else name
        for sy in (-1, 1):
            decal(nm, (front - 0.42 if kind != "bus" else -0.2, sy * 0.545, 0.62 if kind != "bus" else 0.6),
                  (math.radians(90), 0, math.radians(0 if sy < 0 else 180)), 0.2, up)
    if art:
        side_art(kind, up, cab if kind == "bus" else lower)
    # wheels
    xs = (-0.62, 0.62) if kind != "bus" else (-0.75, 0.75)
    wy = 0.66 if monster else 0.5
    for wx in xs:
        for sy in (-1, 1):
            v.wheels.append(toy_wheel("wheel", (wx, sy * wy, wr), wr, ww, rim_m, R, monster=monster))
    if monster:
        frame = plastic("chassis_blue", (0.05, 0.25, 0.85), rough=0.35)
        spring = plastic("spring_green", (0.35, 0.85, 0.1), rough=0.3)
        shock = plastic("shock_red", (0.85, 0.05, 0.05), rough=0.3)
        sbox("frame", (0, 0, wr + 0.05), (1.8, 0.5, 0.12), frame, 0.04, R)
        for wx in xs:
            sbox("axle", (wx, 0, wr), (0.1, wy * 2 - 0.3, 0.1), frame, 0.03, R)
            for sy in (-1, 1):
                kit.cyl("shock", (wx, sy * 0.32, wr + 0.28), 0.035, 0.45, shock, verts=12, parent=R)
                for t in range(5):
                    kit.cyl("coil", (wx, sy * 0.32, wr + 0.1 + t * 0.075), 0.08, 0.025, spring, verts=16, parent=R)
    return v


def _rear(kind, v, body, dark, up):
    white = plastic("stripe_white", (0.97, 0.97, 0.97), rough=0.35)
    chrome = kit.chrome()
    if kind == "fire":
        sbox("fire_box", (-0.45, 0, 1.12), (0.86, 1.04, 0.62), body, 0.16, up)
        for sy in (-1, 1):
            kit.box("fire_stripe", (-0.45, sy * 0.525, 0.98), (0.8, 0.01, 0.06), white, 0.0, up)
            kit.cyl("hose_reel", (-0.45, sy * 0.54, 1.18), 0.15, 0.06, white, verts=24, rot=(math.radians(90), 0, 0),
                    parent=up, bevel=0.02)
        for sy in (-0.22, 0.22):
            kit.box("ladder_rail", (-0.2, sy, 1.62), (1.4, 0.05, 0.05), chrome, 0.015, up)
        for k in range(8):
            kit.box("ladder_rung", (-0.82 + k * 0.17, 0, 1.62), (0.03, 0.44, 0.03), chrome, 0.008, up)
    elif kind == "dump":
        piv = kit.empty("bed_pivot", (-0.88, 0, 0.88), up)
        bed = plastic("dump_bed", tuple(min(1, c * 0.85) for c in body.node_tree.nodes["Principled BSDF"]
                                        .inputs["Base Color"].default_value[:3]), rough=0.3)
        v.body_mats.append(bed)
        sbox("bed_floor", (0.44, 0, 0.04), (0.92, 1.04, 0.08), bed, 0.03, piv)
        for sy in (-1, 1):
            sbox("bed_side", (0.44, sy * 0.5, 0.28), (0.92, 0.07, 0.5), bed, 0.03, piv)
        sbox("bed_back", (0.02, 0, 0.25), (0.07, 1.04, 0.44), bed, 0.03, piv)
        sbox("bed_front", (0.88, 0, 0.36), (0.08, 1.04, 0.66), bed, 0.03, piv)
        v.parts["bed"] = piv
    elif kind == "tanker":
        t = kit.cyl("tank", (-0.42, 0, 1.18), 0.38, 0.9, body, verts=48, rot=(0, math.radians(90), 0), parent=up,
                    bevel=0.12)
        soft(t, 1)
        for x in (-0.72, -0.12):
            kit.cyl("tank_band", (x, 0, 1.18), 0.39, 0.05, chrome, verts=48, rot=(0, math.radians(90), 0), parent=up)
        kit.cyl("tank_hatch", (-0.42, 0, 1.58), 0.12, 0.06, chrome, verts=24, parent=up, bevel=0.02)
    elif kind == "crane":
        sbox("crane_deck", (-0.45, 0, 0.92), (0.86, 1.0, 0.12), dark, 0.03, up)
        turret = kit.empty("turret", (-0.45, 0, 1.0), up)
        sbox("turret_box", (0, 0, 0.18), (0.5, 0.6, 0.36), body, 0.08, turret)
        boom = kit.empty("boom", (0.1, 0, 0.32), turret)
        boom.rotation_euler = (0, math.radians(-28), 0)
        yel = plastic("boom_yellow", (1.0, 0.75, 0.05), rough=0.3)
        for sy in (-0.12, 0.12):
            kit.box("boom_rail", (0.75, sy, 0), (1.5, 0.05, 0.08), yel, 0.02, boom)
        for k in range(7):
            kit.box("boom_strut", (0.15 + k * 0.2, 0, 0), (0.03, 0.26, 0.06), yel, 0.01, boom)
        v.parts["turret"], v.parts["boom"] = turret, boom
    elif kind == "car":
        pass


# ================================================================ playground world
def slide(name, x, y_top, colour, height=3.0, length=5.5, width=1.1):
    """A curved toy slide coming down toward -Y, with a U-shaped chute."""
    n_along, n_across = 48, 18
    verts, faces = [], []
    for i in range(n_along + 1):
        s = i / n_along
        y = y_top - length * s
        if s < 0.85:
            z = 0.12 + (height - 0.12) * (math.cos(math.pi * s / 0.85) + 1) / 2
        else:
            z = 0.12
        for j in range(n_across + 1):
            u = -1 + 2 * j / n_across
            verts.append((x + u * width / 2, y, z + 0.32 * u ** 4))
    for i in range(n_along):
        for j in range(n_across):
            a = i * (n_across + 1) + j
            faces.append((a, a + 1, a + n_across + 2, a + n_across + 1))
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    ob.data.materials.append(plastic(f"slide_{name}", colour, rough=0.22))
    md = ob.modifiers.new("thick", "SOLIDIFY")
    md.thickness = 0.08
    soft(ob, 1)
    for p in ob.data.polygons:
        p.use_smooth = True
    # tower and ladder at the top
    tower_m = plastic("tower", (0.98, 0.98, 0.98), rough=0.35)
    sbox("tower", (x, y_top + 0.45, height / 2), (width + 0.2, 0.9, height), tower_m, 0.1, None)
    return ob


def playground(colours=None, floor=(0.62, 0.21, 0.02), slides=True, size=(34, 20)):
    """Toy playground: glossy brown platform, giant slides in each colour, bright green ground, soft sky,
    and a studio light rig (warm key, cool fill, rim)."""
    sc = bpy.context.scene
    w = bpy.data.worlds.new("pg_sky")
    sc.world = w
    w.use_nodes = True
    nt = w.node_tree
    bg = nt.nodes["Background"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.5                   # horizon
    ramp.color_ramp.elements[0].color = (0.30, 0.68, 1.0, 1)
    ramp.color_ramp.elements[1].position = 0.75
    ramp.color_ramp.elements[1].color = (0.03, 0.30, 1.0, 1)
    nt.links.new(tc.outputs["Generated"], sep.inputs[0])
    nt.links.new(sep.outputs["Z"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bg.inputs["Color"])
    bg.inputs["Strength"].default_value = 0.8                    # sky fill: lower, its blue cooled the whole frame (measured)

    green = plastic("pg_grass", (0.18, 0.62, 0.04), rough=0.55)
    bpy.ops.mesh.primitive_plane_add(size=400, location=(0, 0, -0.26))
    bpy.context.object.data.materials.append(green)
    floor_m = plastic("pg_floor", floor, rough=0.5)
    fb = floor_m.node_tree.nodes["Principled BSDF"]
    if "Coat Weight" in fb.inputs:
        fb.inputs["Coat Weight"].default_value = 0.0      # a soft sheen, not a mirror
    sbox("platform", (0, 2, -0.13), (size[0], size[1], 0.26), floor_m, 0.12, None)
    cols = colours or [(0.85, 0.04, 0.03), (0.98, 0.75, 0.02), (0.15, 0.65, 0.05), (0.04, 0.25, 0.9),
                       (1.0, 0.42, 0.02)]
    for i, c in enumerate(cols if slides else []):
        slide(f"slide{i}", -6 + i * 1.35, 9.5, c)
    # far hills and round trees, soft in the depth of field
    hill = plastic("pg_hill", (0.12, 0.55, 0.05), rough=0.6)
    for x, y, s in [(-30, 45, 16), (0, 55, 22), (32, 48, 18)]:
        kit.sphere("hill", (x, y, -s * 0.5), 1, hill, scale=(s * 1.5, s * 0.8, s))
    leaves = kit.ramp_mat("pg_leaves", (0.10, 0.45, 0.04), (0.35, 0.75, 0.10), rough=0.5, kind="instance")
    trunk = kit.mat("trunk", (0.32, 0.17, 0.07), rough=0.8)
    import random
    rng = random.Random(5)
    for i in range(18):
        x = rng.uniform(-30, 30)
        kit.tree((x, rng.uniform(16, 30)), rng.uniform(1.2, 1.9), trunk, leaves, rng)
    lights()


def lights():
    """Warm key, cool fill and a rim light: the bright, soft toy-commercial look."""
    bpy.ops.object.light_add(type="SUN", rotation=(math.radians(50), math.radians(8), math.radians(-40)))
    sun = bpy.context.object
    sun.data.energy = 2.8
    sun.data.angle = math.radians(18)                  # soft shadow edges
    sun.data.color = (1.0, 0.84, 0.62)                 # golden sun: the reference is warm (R-B +0.28 vs ours +0.06)
    for name, loc, energy, size, col in [("key", (-6, -8, 7), 900, 6, (1.0, 0.86, 0.68)),
                                         ("fill", (8, -6, 3), 650, 9, (1.0, 0.94, 0.86)),
                                         ("rim", (2, 9, 5), 600, 5, (1.0, 0.92, 0.80))]:
        bpy.ops.object.light_add(type="AREA", location=loc)
        L = bpy.context.object
        L.name = name
        L.data.energy, L.data.size, L.data.color = energy, size, col
        L.data.use_shadow = name == "key"                # fill and rim only add light; their shadows cost time
        c = L.constraints.new("TRACK_TO")
        tgt = kit.empty(f"{name}_aim", (0, 0, 0.8))
        c.target, c.track_axis, c.up_axis = tgt, "TRACK_NEGATIVE_Z", "UP_Y"


# ================================================================ graphics pass 3: smooth tyres, spoked rims, balls
def tyre_mesh(name, r, w, monster=False, n_around=None):
    """One smooth rubber tyre with directional chevron tread, built as a revolved grid (axis along local Y).
    Tread blocks are raised parts of the same surface, so subdivision keeps them soft like the reference toys."""
    import os
    lite = os.environ.get("TOY_TYRE", "lite") == "lite"
    n_a = n_around or ((120 if monster else 100) if lite else (220 if monster else 180))
    n_u = 12 if lite else 22
    blocks = 14 if monster else 20
    depth = r * (0.12 if monster else 0.07)
    inner = r * 0.62
    rows = []                                      # each row: (y, radius function of angle)
    for j in range(n_u + 1):
        u = -1 + 2 * j / n_u
        rows.append(u)
    verts, faces = [], []
    ring = []
    for u in rows:
        shoulder = r * 0.18 * abs(u) ** 5          # rounded shoulders
        for i in range(n_a):
            a = 2 * math.pi * i / n_a
            ph = (a * blocks / (2 * math.pi) + 0.45 * abs(u)) % 1.0     # chevron: phase bends with |u|
            on = ph < (0.5 if monster else 0.55) and abs(u) < 0.92
            rad = r - depth - shoulder + (depth if on else 0)
            verts.append((rad * math.cos(a), u * w / 2, rad * math.sin(a)))
        ring.append(len(rows))
    # sidewalls down to the rim on both sides
    for u in (1.0, -1.0):
        for k, frac in enumerate((0.86, 0.72)):
            rad = inner + (r - depth - r * 0.18 - inner) * frac
            yy = u * w / 2 * (0.96 - 0.04 * k)
            for i in range(n_a):
                a = 2 * math.pi * i / n_a
                verts.append((rad * math.cos(a), yy, rad * math.sin(a)))
    n_rows = n_u + 1
    def idx(row, i):
        return row * n_a + (i % n_a)
    for row in range(n_rows - 1):
        for i in range(n_a):
            faces.append((idx(row, i), idx(row, i + 1), idx(row + 1, i + 1), idx(row + 1, i)))
    # +side: last tread row -> sidewall rows n_rows, n_rows+1 ; -side: first tread row -> n_rows+2, n_rows+3
    for a_row, b_row in [(n_rows - 1, n_rows), (n_rows, n_rows + 1), (0, n_rows + 2), (n_rows + 2, n_rows + 3)]:
        for i in range(n_a):
            faces.append((idx(a_row, i), idx(b_row, i), idx(b_row, i + 1), idx(a_row, i + 1)))
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.validate()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    ob.data.materials.append(plastic("tyre_rubber", (0.035, 0.035, 0.04), rough=0.62))
    soft(ob, 1)
    for p in ob.data.polygons:
        p.use_smooth = True
    return ob


def toy_wheel(name, loc, r, w, rim_m, parent, monster=False):
    """Smooth tread tyre + deep coloured dish rim with six spokes + chrome cap. Spin about local Y to roll."""
    hub = kit.empty(name, loc, parent)
    hub["r"] = r                                    # rolling radius for kit.roll_wheels
    ty = tyre_mesh(name + "_tyre", r, w, monster)
    ty.parent = hub
    dish = kit.cyl(name + "_dish", (0, 0, 0), r * 0.63, w * 0.92, rim_m, verts=48, rot=(math.pi / 2, 0, 0),
                   parent=hub, bevel=r * 0.05)
    soft(dish, 1)
    dark = plastic("rim_shadow", (0.05, 0.05, 0.06), rough=0.5)
    cap = kit.chrome()
    for sy in (-1, 1):
        y = sy * w * 0.47
        kit.cyl(name + "_well", (0, y, 0), r * 0.48, 0.012, dark, verts=40, rot=(math.pi / 2, 0, 0), parent=hub)
        for k in range(6):
            a = 2 * math.pi * k / 6
            sp = sbox(name + "_spoke", (math.cos(a) * r * 0.27, y + sy * 0.006, math.sin(a) * r * 0.27),
                      (r * 0.42, 0.03, r * 0.13), rim_m, 0.02, hub, rot=(0, -a, 0))
        kit.cyl(name + "_cap", (0, y + sy * 0.02, 0), r * 0.15, 0.04, cap, verts=24, rot=(math.pi / 2, 0, 0),
                parent=hub, bevel=0.012)
    return hub


def ball(colour, loc, r=0.45, parent=None, name="ball"):
    """Toy football: coloured ball with smooth black pentagons at the 12 icosahedron points (drawn in the shader,
    so the edges stay clean at any distance)."""
    bpy.ops.mesh.primitive_uv_sphere_add(segments=64, ring_count=32, radius=r, location=loc)
    ob = bpy.context.object
    ob.name = name
    for p in ob.data.polygons:
        p.use_smooth = True
    m = plastic(f"ball_{'%.2f%.2f%.2f' % colour}", colour, rough=0.35)
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    nrm = nt.nodes.new("ShaderNodeVectorMath")
    nrm.operation = "NORMALIZE"
    nt.links.new(tc.outputs["Object"], nrm.inputs[0])
    phi = (1 + 5 ** 0.5) / 2
    poles = [Vector(v).normalized() for v in
             [(0, 1, phi), (0, -1, phi), (0, 1, -phi), (0, -1, -phi), (1, phi, 0), (-1, phi, 0), (1, -phi, 0),
              (-1, -phi, 0), (phi, 0, 1), (-phi, 0, 1), (phi, 0, -1), (-phi, 0, -1)]]
    best = None
    for q in poles:
        d = nt.nodes.new("ShaderNodeVectorMath")
        d.operation = "DOT_PRODUCT"
        d.inputs[1].default_value = tuple(q)
        nt.links.new(nrm.outputs[0], d.inputs[0])
        out = d.outputs["Value"]
        if best is not None:
            mx = nt.nodes.new("ShaderNodeMath")
            mx.operation = "MAXIMUM"
            nt.links.new(best, mx.inputs[0])
            nt.links.new(out, mx.inputs[1])
            out = mx.outputs[0]
        best = out
    # hexagon centres (dodecahedron points): a point is black when it is nearer a pole than any hexagon centre,
    # which gives real straight-edged pentagons (a Voronoi split on the sphere)
    # the 20 hexagon centres are the icosahedron's face centres: every trio of mutually neighbouring poles
    import itertools
    near = math.cos(math.radians(64))
    hexes = [(a + b + c).normalized() for a, b, c in itertools.combinations(poles, 3)
             if a.dot(b) > near and b.dot(c) > near and a.dot(c) > near]
    hbest = None
    for q in hexes:
        d = nt.nodes.new("ShaderNodeVectorMath")
        d.operation = "DOT_PRODUCT"
        d.inputs[1].default_value = tuple(q)
        nt.links.new(nrm.outputs[0], d.inputs[0])
        out = d.outputs["Value"]
        if hbest is not None:
            mx = nt.nodes.new("ShaderNodeMath")
            mx.operation = "MAXIMUM"
            nt.links.new(hbest, mx.inputs[0])
            nt.links.new(out, mx.inputs[1])
            out = mx.outputs[0]
        hbest = out
    diff = nt.nodes.new("ShaderNodeMath")
    diff.operation = "SUBTRACT"
    nt.links.new(best, diff.inputs[0])
    nt.links.new(hbest, diff.inputs[1])
    edge = nt.nodes.new("ShaderNodeMapRange")          # crisp straight pentagon edge
    edge.inputs["From Min"].default_value = 0.0
    edge.inputs["From Max"].default_value = 0.006
    nt.links.new(diff.outputs[0], edge.inputs["Value"])
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    a_in, b_in = [i_ for i_ in mix.inputs if i_.type == "RGBA"][:2]
    a_in.default_value, b_in.default_value = (*colour, 1), (0.015, 0.015, 0.02, 1)
    nt.links.new(edge.outputs["Result"], mix.inputs["Factor"])
    nt.links.new([o for o in mix.outputs if o.type == "RGBA"][0], b.inputs["Base Color"])
    ob.data.materials.append(m)
    if parent is not None:
        ob.parent = parent
    return ob


# ================================================================ one entry point for templates
SPOKEN = {"car": "car", "bus": "bus", "dump": "dump truck", "monster": "monster truck", "tanker": "water truck",
          "crane": "crane truck", "fire": "fire truck"}
TOP = {"car": 1.62, "bus": 1.68, "dump": 1.62, "tanker": 1.62, "crane": 1.62, "fire": 1.7, "monster": 2.05}


def vehicle(kind, rgb, loc=(0, 0, 0), yaw=0.0, name=None, rim=None, iris=None, **_):
    """Template-facing builder: 'monster' is a chibi car on monster tyres; the rest are chibi kinds.
    The name argument is the object name; the body decal keeps the toy's own name (NAMES)."""
    eye = iris or (0.30, 0.18, 0.08)
    if kind == "monster":
        v = chibi("car", rgb, loc=loc, yaw=yaw, name=None, monster=True, rim=rim, iris=eye)
    else:
        v = chibi(kind, rgb, loc=loc, yaw=yaw, name=None, rim=rim, iris=eye)
    if name:
        v.root.name = name
    return v
