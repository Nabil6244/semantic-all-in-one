"""Car parts built in Blender from simple shapes, in the toon look (cel bands + outlines from world.py):
engines (inline / V, any cylinder count, cutaway front with pumping pistons), turbos (spinning compressor wheel),
superchargers (roots blower or electric), engine stands, a garage tile floor, a tool pegboard, a drag-strip start
tree and a FINISH gantry. No model files, so every channel video gets them for free.

A world piece uses one with "m": "@<kind>" plus its options, e.g.
  {"m": "@engine", "at": [0, 3, 1.1], "rot": 20, "s": 1.0, "id": "eng", "cyl": 8, "layout": "V", "induction": "turbo",
   "cutaway": true, "block": [0.62, 0.64, 0.68], "cover": [0.85, 0.22, 0.16], "run": 1.5}
Sizes are real metres (a V8 is ~0.8 m long); "s" scales the whole part.
Animated parts: pistons pump and wheels/pulleys spin at "run" revolutions a second (a turbo wheel spins 6x that).
A shot move {"id": "eng", "run_to": 4, "t0": 1, "t1": 2} revs a part up (or down to 0) over the move.
"""
import math

import bpy

KINDS = ("engine", "turbo", "supercharger", "stand", "tiles", "pegboard", "start_tree", "finish", "box", "strip", "clock", "motor")
STEEL = [0.72, 0.74, 0.78]
DARK = [0.16, 0.16, 0.19]
ORANGE = [0.95, 0.42, 0.14]


def _mat(color, name=None, emit=False):
    """A plain material world._toonify turns into cel bands (emit=True: a glowing lamp, left as is)."""
    key = name or ("lamp_" if emit else "part_") + "_".join(str(round(c, 2)) for c in color)
    if emit:
        key = "toon_" + key  # toon_* materials are not re-shaded
    m = bpy.data.materials.get(key)
    if m:
        return m
    m = bpy.data.materials.new(key)
    m.use_nodes = True
    nt = m.node_tree
    if emit:
        nt.nodes.clear()
        e = nt.nodes.new("ShaderNodeEmission")
        e.inputs["Color"].default_value = (*color, 1)
        e.inputs["Strength"].default_value = 1.6
        o = nt.nodes.new("ShaderNodeOutputMaterial")
        nt.links.new(e.outputs[0], o.inputs[0])
    else:
        b = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
        b.inputs["Base Color"].default_value = (*color, 1)
    return m


def _obj(o, parent, color, emit=False, name=None):
    o.data.materials.clear()
    o.data.materials.append(_mat(color, emit=emit))
    o.parent = parent
    if name:
        o.name = name
    return o


def box(parent, size, at, color, rot=(0, 0, 0), bevel=0.0, name=None):
    bpy.ops.mesh.primitive_cube_add(size=1, location=at, rotation=rot)
    o = bpy.context.active_object
    o.scale = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bevel:
        m = o.modifiers.new("bevel", "BEVEL")
        m.width, m.segments = bevel, 2
    return _obj(o, parent, color, name=name)


def cyl(parent, r, depth, at, color, rot=(0, 0, 0), verts=24, emit=False, name=None):
    bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=depth, location=at, rotation=rot, vertices=verts)
    return _obj(bpy.context.active_object, parent, color, emit=emit, name=name)


def pipe(parent, pts, r, color):
    """A bent tube through 3D points (headers, intercooler pipes)."""
    cu = bpy.data.curves.new("pipe", "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth, cu.bevel_resolution = r, 3
    sp = cu.splines.new("BEZIER")
    sp.bezier_points.add(len(pts) - 1)
    for bp, p in zip(sp.bezier_points, pts):
        bp.co = p
        bp.handle_left_type = bp.handle_right_type = "AUTO"
    o = bpy.data.objects.new("pipe", cu)
    bpy.context.scene.collection.objects.link(o)
    bpy.context.view_layer.objects.active = o
    o.select_set(True)
    bpy.ops.object.convert(target="MESH")
    o = bpy.context.active_object
    return _obj(o, parent, color)


def text(parent, body, at, size, color, rot=(math.radians(90), 0, 0), extrude=0.02):
    cu = bpy.data.curves.new("txt", "FONT")
    cu.body = body
    cu.align_x, cu.align_y = "CENTER", "CENTER"
    cu.size, cu.extrude = size, extrude
    o = bpy.data.objects.new("txt", cu)
    bpy.context.scene.collection.objects.link(o)
    o.location, o.rotation_euler = at, rot
    bpy.context.view_layer.objects.active = o
    o.select_set(True)
    bpy.ops.object.convert(target="MESH")
    o = bpy.context.active_object
    return _obj(o, parent, color)


def _root(name):
    r = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(r)
    return r


# ---------------------------------------------------------------- engine
def engine(spec, anims):
    """Engine on its own origin (bottom centre of the oil pan), crank along x, front (pulleys) at -x."""
    root = _root("engine")
    n = int(spec.get("cyl", 8))
    lay = spec.get("layout", "V" if n >= 6 else "I")
    blk, cov = spec.get("block", STEEL), spec.get("cover", [0.85, 0.22, 0.16])
    per = n // 2 if lay == "V" else n
    pitch = 0.11 * spec.get("bore", 1.0)
    L = per * pitch + 0.16
    run = spec.get("run", 0.0)
    box(root, (L, 0.36, 0.14), (0, 0, 0.07), DARK, bevel=0.02)                     # oil pan
    box(root, (L, 0.42, 0.26), (0, 0, 0.27), blk, bevel=0.015)                      # crankcase
    banks = [(-1, math.radians(45)), (1, math.radians(-45))] if lay == "V" else [(0, 0.0)]
    pistons = []
    for side, tilt in banks:
        # a bank: cylinder block, head, valve cover, set at the bank angle
        bank = _root("bank")
        bank.parent = root
        bank.location = (0, side * 0.13, 0.36)
        bank.rotation_euler = (tilt, 0, 0)
        box(bank, (L, 0.28, 0.30), (0, 0, 0.15), blk, bevel=0.015)
        box(bank, (L, 0.30, 0.09), (0, 0, 0.345), blk, bevel=0.012)
        box(bank, (L - 0.04, 0.24, 0.08), (0, 0, 0.43), cov, bevel=0.03)
        text(bank, spec.get("badge", ""), (0, 0, 0.475), 0.06, [0.95, 0.95, 0.95], rot=(0, 0, 0)) if spec.get("badge") else None
        for k in range(per):
            x = -L / 2 + 0.08 + pitch * (k + 0.5)
            cyl(bank, 0.012, 0.03, (x, 0.05, 0.47), DARK, verts=8)              # cover bolts
        if spec.get("cutaway"):  # the face toward the camera (-y on an inline, outer face on a V) is open
            face = -0.145 if side <= 0 else 0.145
            for k in range(per):
                x = -L / 2 + 0.08 + pitch * (k + 0.5)
                box(bank, (pitch * 0.82, 0.01, 0.26), (x, face, 0.16), DARK)           # bore
                p = box(bank, (pitch * 0.74, 0.02, 0.07), (x, face * 1.04, 0.2), [0.85, 0.86, 0.9], bevel=0.008)
                rings = box(p, (pitch * 0.75, 0.022, 0.008), (x, face * 1.04, 0.215), DARK)
                rod = box(bank, (0.02, 0.015, 0.16), (x, face * 1.02, 0.1), [0.6, 0.6, 0.64])
                ph = (k * 2 + (0 if side <= 0 else 1)) * math.pi / max(1, per) * (1 if lay == "V" else 2)
                pistons.append({"obj": p, "rod": rod, "z0": 0.2, "rz0": 0.1, "ph": ph, "rings": rings})
    # intake: plenum on a V (with throttle body), runners on an inline
    if lay == "V":
        box(root, (L * 0.86, 0.2, 0.12), (0, 0, 0.86), blk, bevel=0.03)
        cyl(root, 0.06, 0.08, (-L * 0.43 - 0.04, 0, 0.86), DARK, rot=(0, math.radians(90), 0))
    else:
        box(root, (L * 0.8, 0.1, 0.08), (0, 0.06, 0.92), blk, bevel=0.03)                 # plenum on top
        for k in range(per):
            x = -L / 2 + 0.08 + pitch * (k + 0.5)
            pipe(root, [(x, 0.1, 0.8), (x, 0.08, 0.86), (x, 0.06, 0.9)], 0.02, blk)
    # exhaust headers: one tube per cylinder sweeping down and back into a collector
    for side, tilt in banks:
        sy = side if side else 1  # inline: exhaust on the back (+y), the cutaway face (-y) stays clear
        for k in range(per):
            x = -L / 2 + 0.08 + pitch * (k + 0.5)
            y0 = sy * (0.36 if lay == "V" else 0.15)
            pipe(root, [(x, y0, 0.62 if lay == "V" else 0.62), (x, sy * 0.46, 0.5), (L * 0.35, sy * 0.5, 0.2),
                        (L * 0.55, sy * 0.5, 0.12)], 0.022, [0.78, 0.76, 0.72])
    # front: pulleys + belt run
    spin = []
    for (y, z, r) in [(0, 0.22, 0.09), (0.16, 0.55, 0.05), (-0.16, 0.55, 0.05), (0.0, 0.62, 0.045)]:
        w = cyl(root, r, 0.04, (-L / 2 - 0.03, y, z), [0.28, 0.28, 0.32], rot=(0, math.radians(90), 0))
        box(w, (0.045, r * 1.6, 0.012), (-L / 2 - 0.035, y, z), [0.85, 0.85, 0.88])  # spoke so the spin reads
        spin.append({"obj": w, "axis": 0, "mul": 1.0})
    ind = spec.get("induction", "none")
    if ind in ("turbo", "twin_turbo"):
        sides = [-1, 1] if ind == "twin_turbo" else [-1]
        for sy in sides:
            t = turbo({"size": spec.get("turbo_size", 1.0)}, anims, standalone=False)
            t.parent = root
            t.location = (L * 0.55 + 0.12, sy * 0.52, 0.26)
            t.rotation_euler = (0, 0, math.radians(90 if sy < 0 else -90))
    elif ind in ("supercharger", "electric"):
        s = supercharger({"electric": ind == "electric"}, anims, standalone=False)
        s.parent = root
        s.location = (0, 0, 0.92 if lay == "V" else 0.7)
    anims.append({"kind": "engine", "pistons": pistons, "spin": spin, "run": run, "stroke": 0.035})
    return root


# ---------------------------------------------------------------- turbo / supercharger
def turbo(spec, anims, standalone=True):
    """Snail housing (compressor side) with an open intake showing a spinning wheel, turbine side behind."""
    root = _root("turbo")
    k = spec.get("size", 1.0)
    bpy.ops.mesh.primitive_torus_add(major_radius=0.13 * k, minor_radius=0.07 * k, location=(0, 0, 0.2 * k),
                                     rotation=(math.radians(90), 0, 0))
    _obj(bpy.context.active_object, root, STEEL)
    cyl(root, 0.1 * k, 0.12 * k, (0, 0, 0.2 * k), STEEL, rot=(math.radians(90), 0, 0))
    cyl(root, 0.085 * k, 0.13 * k, (0, -0.02 * k, 0.2 * k), DARK, rot=(math.radians(90), 0, 0))     # intake mouth
    wheel = _root("wheel")
    wheel.parent = root
    wheel.location = (0, -0.075 * k, 0.2 * k)
    for b in range(8):  # compressor blades
        a = b * math.pi / 4
        bl = box(None, (0.012 * k, 0.012 * k, 0.15 * k), (0, 0, 0), [0.95, 0.78, 0.25],
                 rot=(0, a + 0.35, 0))
        bl.parent = wheel
        bl.location = (math.sin(a) * 0.04 * k, 0, math.cos(a) * 0.04 * k)
        bl.rotation_euler = (0, a, 0)
    cyl(wheel, 0.022 * k, 0.03 * k, (0, 0, 0), STEEL, rot=(math.radians(90), 0, 0))
    pipe(root, [(0.13 * k, 0, 0.27 * k), (0.25 * k, 0, 0.33 * k), (0.3 * k, 0, 0.5 * k)], 0.05 * k, STEEL)  # outlet
    bpy.ops.mesh.primitive_torus_add(major_radius=0.1 * k, minor_radius=0.06 * k, location=(0, 0.16 * k, 0.2 * k),
                                     rotation=(math.radians(90), 0, 0))
    _obj(bpy.context.active_object, root, [0.34, 0.33, 0.36])                                # hot turbine side: cast iron
    bpy.ops.mesh.primitive_torus_add(major_radius=0.155 * k, minor_radius=0.014 * k, location=(0, 0.2 * k, 0.2 * k),
                                     rotation=(math.radians(90), 0, 0))
    _obj(bpy.context.active_object, root, [1.0, 0.42, 0.1], emit=True)                       # glowing rim: reads as "hot"
    cyl(root, 0.05 * k, 0.03 * k, (0, 0.235 * k, 0.2 * k), [1.0, 0.55, 0.15], rot=(math.radians(90), 0, 0))
    if standalone:
        box(root, (0.1 * k, 0.1 * k, 0.1 * k), (0, 0.16 * k, 0.07 * k), DARK)
    anims.append({"kind": "spin", "obj": wheel, "axis": 1, "mul": 6.0, "run": spec.get("run", 0.0)})
    return root


def supercharger(spec, anims, standalone=True):
    """Roots blower on the intake (ribbed case, front pulley) or an electric one (motor can, cable)."""
    root = _root("supercharger")
    case = [0.82, 0.83, 0.86]
    box(root, (0.56, 0.26, 0.16), (0, 0, 0.08), case, bevel=0.05)
    for i in range(7):
        box(root, (0.5, 0.012, 0.03), (0, -0.09 + i * 0.03, 0.17), case)
    box(root, (0.22, 0.16, 0.04), (0.08, 0, 0.18), DARK, bevel=0.01)                         # scoop
    if spec.get("electric"):
        m = cyl(root, 0.09, 0.2, (-0.38, 0, 0.1), [0.22, 0.42, 0.95], rot=(0, math.radians(90), 0))
        for i in range(4):
            cyl(root, 0.093, 0.012, (-0.32 - i * 0.04, 0, 0.1), DARK, rot=(0, math.radians(90), 0))
        pipe(root, [(-0.48, 0, 0.1), (-0.56, 0.1, 0.02), (-0.6, 0.3, -0.2)], 0.012, [0.95, 0.2, 0.15])
        fan = _root("fan")
        fan.parent = root
        fan.location = (-0.49, 0, 0.1)
        for b in range(4):
            bl = box(None, (0.006, 0.02, 0.14), (0, 0, 0), [0.95, 0.95, 0.98])
            bl.parent = fan
            bl.rotation_euler = (b * math.pi / 4, 0, 0)
        anims.append({"kind": "spin", "obj": fan, "axis": 0, "mul": 4.0, "run": spec.get("run", 0.0)})
    else:
        p = cyl(root, 0.075, 0.04, (-0.3, 0, 0.08), [0.28, 0.28, 0.32], rot=(0, math.radians(90), 0))
        box(p, (0.045, 0.12, 0.012), (-0.305, 0, 0.08), [0.85, 0.85, 0.88])
        anims.append({"kind": "spin", "obj": p, "axis": 0, "mul": 1.5, "run": spec.get("run", 0.0)})
    return root


def motor(spec, anims):
    """Electric motor-generator: blue can with cooling fins, copper windings in a cut window, spinning shaft, orange cable."""
    root = _root("motor")
    blue, copper = spec.get("color", [0.2, 0.42, 0.95]), [0.85, 0.48, 0.2]
    cyl(root, 0.2, 0.5, (0, 0, 0.22), blue, rot=(0, math.radians(90), 0))
    for i in range(7):
        cyl(root, 0.215, 0.018, (-0.2 + i * 0.066, 0, 0.22), DARK, rot=(0, math.radians(90), 0))
    cyl(root, 0.205, 0.05, (0.27, 0, 0.22), STEEL, rot=(0, math.radians(90), 0))              # end bell
    box(root, (0.26, 0.05, 0.16), (0, -0.19, 0.22), copper, bevel=0.01)                         # windings window
    for i in range(6):
        box(root, (0.012, 0.055, 0.15), (-0.11 + i * 0.044, -0.2, 0.22), [0.6, 0.3, 0.12])
    shaft = _root("shaft")
    shaft.parent = root
    shaft.location = (-0.3, 0, 0.22)
    cyl(shaft, 0.03, 0.12, (0, 0, 0), STEEL, rot=(0, math.radians(90), 0))
    for b in range(3):
        bl = box(None, (0.01, 0.03, 0.2), (0, 0, 0), [0.95, 0.95, 0.98])
        bl.parent = shaft
        bl.location = (-0.05, 0, 0)
        bl.rotation_euler = (b * math.pi / 3, 0, 0)
    box(root, (0.4, 0.3, 0.04), (0, 0, 0.02), DARK)                                             # mount feet
    pipe(root, [(0.15, 0.17, 0.32), (0.25, 0.35, 0.3), (0.35, 0.5, 0.05)], 0.025, [1.0, 0.45, 0.08])  # HV cable
    anims.append({"kind": "spin", "obj": shaft, "axis": 0, "mul": 4.0, "run": spec.get("run", 0.0)})
    return root


# ---------------------------------------------------------------- garage / strip props
def stand(spec, anims):
    """Orange engine stand: cross feet, post, top plate at height h (put the engine at z = h)."""
    root = _root("stand")
    h = spec.get("h", 1.0)
    c = spec.get("color", ORANGE)
    box(root, (0.9, 0.12, 0.08), (0, 0, 0.04), c, bevel=0.01)
    box(root, (0.12, 0.9, 0.08), (0, 0, 0.04), c, bevel=0.01)
    box(root, (0.12, 0.12, h - 0.1), (0, 0, (h - 0.1) / 2 + 0.06), c, bevel=0.01)
    box(root, (0.7, 0.5, 0.05), (0, 0, h - 0.025), c, bevel=0.01)
    return root


def tiles(spec, anims):
    """Square floor tiles with grout lines (w x d metres, tile size t)."""
    root = _root("tiles")
    w, d, t = spec.get("w", 24), spec.get("d", 20), spec.get("t", 0.9)
    c, g = spec.get("color", [0.93, 0.90, 0.86]), spec.get("grout", [0.70, 0.66, 0.62])
    box(root, (w, d, 0.02), (0, d / 2 - 6, 0.0), g)
    for i in range(int(w / t)):
        for j in range(int(d / t)):
            shade = c if (i + j) % 2 else [v * 0.97 for v in c]
            box(root, (t * 0.94, t * 0.94, 0.02), (-w / 2 + t * (i + 0.5), -6 + t * (j + 0.5), 0.012), shade)
    return root


def pegboard(spec, anims):
    """Wall board with hanging tool shapes (wrenches, a hammer)."""
    root = _root("pegboard")
    w, h = spec.get("w", 2.4), spec.get("h", 1.3)
    box(root, (w, 0.04, h), (0, 0, h / 2), [0.80, 0.62, 0.40])
    for i in range(12):
        x = -w / 2 + 0.2 + i * (w - 0.4) / 11
        ln = 0.3 + 0.08 * ((i * 7) % 5)
        box(root, (0.04, 0.03, ln), (x, -0.04, h * 0.85 - ln / 2), [0.34, 0.34, 0.38] if i % 3 else [0.85, 0.2, 0.15])
    return root


def start_tree(spec, anims):
    """Drag-strip start lights on a pole: two amber, one green lit."""
    root = _root("start_tree")
    box(root, (0.12, 0.12, 2.6), (0, 0, 1.3), DARK)
    box(root, (0.5, 0.2, 1.1), (0, 0, 2.9), DARK, bevel=0.03)
    for i, col in enumerate([[1.0, 0.75, 0.1], [1.0, 0.75, 0.1], [0.2, 1.0, 0.3]]):
        for dx in (-0.12, 0.12):
            cyl(root, 0.08, 0.05, (dx, -0.11, 3.25 - i * 0.3), col, rot=(math.radians(90), 0, 0), emit=True)
    return root


def finish(spec, anims):
    """FINISH gantry over the strip: two posts and a red banner with white letters."""
    root = _root("finish")
    w = spec.get("w", 16)
    for x in (-w / 2, w / 2):
        box(root, (0.3, 0.3, 6.5), (x, 0, 3.25), [0.9, 0.9, 0.92])
    box(root, (w, 0.3, 1.4), (0, 0, 6.2), spec.get("color", [0.85, 0.12, 0.12]), bevel=0.05)
    text(root, spec.get("text", "FINISH"), (0, -0.17, 6.2), 0.95, [1, 1, 1])
    return root


def strip(spec, anims):
    """Drag strip running down +y from y0: asphalt, yellow centre line, white edge lines, grey shoulders."""
    root = _root("strip")
    w, ln, y0 = spec.get("w", 8.0), spec.get("len", 220.0), spec.get("y0", -15.0)
    yc = y0 + ln / 2
    box(root, (w + 2.4, ln, 0.02), (0, yc, 0.005), [0.62, 0.62, 0.64])                       # shoulder
    box(root, (w, ln, 0.02), (0, yc, 0.012), [0.24, 0.25, 0.28])                               # asphalt
    for x in (-w / 2 + 0.25, w / 2 - 0.25):
        box(root, (0.18, ln, 0.02), (x, yc, 0.02), [0.96, 0.96, 0.96])
    box(root, (0.16, ln, 0.02), (0, yc, 0.02), [1.0, 0.82, 0.12])
    box(root, (w, 0.5, 0.02), (0, 0.6, 0.022), [0.96, 0.96, 0.96])                             # start line
    for i in range(int(w / 0.5)):                                                             # chequered finish
        for j in range(2):
            if (i + j) % 2:
                box(root, (0.5, 0.5, 0.02), (-w / 2 + 0.25 + i * 0.5, spec.get("finish_y", 150) - 0.5 + j * 0.5, 0.022),
                    [0.96, 0.96, 0.96])
    return root


def clock(spec, anims):
    """Big public clock face on its own origin (centre of the face), facing -y: cream dial, black ring, hour ticks,
    hour + minute hand ("hour", "min"), and optional second minute hand ("min2", red) for another town's time. Hands sweep at "run"
    (minute-hand turns a second) when the part runs."""
    root = _root("clock")
    r = spec.get("r", 1.0)
    rot = (math.radians(90), 0, 0)
    cyl(root, r * 1.12, 0.14, (0, 0.02, 0), spec.get("frame", [0.55, 0.42, 0.22]), rot=rot, verts=48)
    cyl(root, r, 0.16, (0, 0, 0), [0.98, 0.94, 0.80], rot=rot, verts=48)
    for k in range(12):
        a = k * math.pi / 6
        big = k % 3 == 0
        box(root, (0.05 * r if big else 0.03 * r, 0.02, 0.18 * r if big else 0.1 * r),
            (math.sin(a) * r * 0.82, -0.09, math.cos(a) * r * 0.82), DARK, rot=(0, a, 0))
    hands = [("h", (spec.get("hour", 3) % 12 + spec.get("min", 0) / 60) / 12, 0.5, 0.07, DARK, 1 / 12),
             ("m", spec.get("min", 0) / 60, 0.8, 0.045, DARK, 1.0)]
    if spec.get("min2") is not None:
        hands.append(("m2", spec["min2"] / 60, 0.86, 0.035, [0.85, 0.12, 0.1], 1.0))
    for i, (name, frac, ln, w, col, mul) in enumerate(hands):
        piv = _root(f"hand_{name}")
        piv.parent = root
        piv.location = (0, -0.1 - i * 0.02, 0)
        hand = box(piv, (w * r, 0.015, ln * r), (0, 0, ln * r * 0.42), col)
        piv.rotation_euler = (0, frac * 2 * math.pi, 0)
        anims.append({"kind": "spin", "obj": piv, "axis": 1, "mul": mul, "off": frac * 2 * math.pi,
                      "run": spec.get("run", 0.0)})
    cyl(root, 0.06 * r, 0.06, (0, -0.16, 0), DARK, rot=rot)
    return root


def plain_box(spec, anims):
    return box(_root("box"), spec.get("size", (1, 1, 1)), (0, 0, spec.get("size", (1, 1, 1))[2] / 2),
               spec.get("color", ORANGE), bevel=0.02)


BUILD = {"engine": engine, "turbo": turbo, "supercharger": supercharger, "stand": stand, "tiles": tiles,
         "pegboard": pegboard, "start_tree": start_tree, "finish": finish, "box": plain_box, "strip": strip, "clock": clock, "motor": motor}


def build(spec):
    """spec: the world piece (m = "@kind"). Returns (root, anims)."""
    kind = spec["m"][1:]
    if kind not in BUILD:
        raise KeyError(f"part '@{kind}' unknown (have: {', '.join('@' + k for k in KINDS)})")
    anims = []
    root = BUILD[kind](spec, anims)
    for a in anims:
        a["base"] = a.get("run", 0.0) or spec.get("run", 0.0)
    return root, anims


def animate(anims, run, t, dt):
    """Advance spinning wheels and pistons. run: this part's current revs/s."""
    for a in anims:
        a["phase"] = a.get("phase", 0.0) + 2 * math.pi * run * dt
        ph = a["phase"]
        if a["kind"] == "spin":
            r = a["obj"].rotation_euler
            r[a["axis"]] = a.get("off", 0.0) + ph * a["mul"]
        elif a["kind"] == "engine":
            for s in a["spin"]:
                s["obj"].rotation_euler[s["axis"]] = ph * s["mul"]
            for p in a["pistons"]:
                dz = a["stroke"] * math.sin(ph + p["ph"])
                p["obj"].location.z = p["z0"] + dz
                p["rod"].location.z = p["rz0"] + dz * 0.8
