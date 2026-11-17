"""Blender scene: a wooden paint board in a sunny park, five buckets pour five colours, then a toy car drives in.

blender -b -P toycolors/scene_paint.py -- OUT_DIR [--still SECONDS] [--fast]
Writes OUT_DIR/f_0001.png ... (or one still). Every time comes from toycolors/timeline.py.
"""
import math
import os
import random
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from toycolors import kit, timeline as T  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = os.path.abspath(argv[0] if argv else "toycolors/out/frames")
STILL = [float(s) for s in argv[argv.index("--still") + 1].split(",")] if "--still" in argv else None
FAST = "--fast" in argv

rng = random.Random(7)


def F(t):
    return int(round(t * T.FPS)) + 1


# ---------------------------------------------------------------- scene reset
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = kit.setup_render(fast=FAST, fps=T.FPS)
sc.frame_start, sc.frame_end = 1, F(T.DURATION) - 1


# ---------------------------------------------------------------- helpers
def mat(name, rgb, rough=0.45, spec=0.5, coat=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1)
    b.inputs["Roughness"].default_value = rough
    if "Coat Weight" in b.inputs:
        b.inputs["Coat Weight"].default_value = coat
    return m


def wood_mat():
    m = mat("wood", (0.62, 0.40, 0.20), rough=0.6)
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    tex = nt.nodes.new("ShaderNodeTexWave")
    tex.inputs["Scale"].default_value = 5.0
    tex.inputs["Distortion"].default_value = 1.5
    tex.inputs["Detail"].default_value = 1.0
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.56, 0.34, 0.15, 1)
    ramp.color_ramp.elements[1].color = (0.68, 0.45, 0.22, 1)
    nt.links.new(tex.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], b.inputs["Base Color"])
    return m


def smooth(ob, bevel=0.0, segs=4):
    if bevel:
        md = ob.modifiers.new("bevel", "BEVEL")
        md.width, md.segments = bevel, segs
        md.limit_method = "ANGLE"
    for p in ob.data.polygons:
        p.use_smooth = True
    return ob


def box(name, loc, size, m, bevel=0.03):
    bpy.ops.mesh.primitive_cube_add(location=loc)
    ob = bpy.context.object
    ob.name = name
    ob.scale = (size[0] / 2, size[1] / 2, size[2] / 2)
    bpy.ops.object.transform_apply(scale=True)
    ob.data.materials.append(m)
    return smooth(ob, bevel)


def cyl(name, loc, r, h, m, verts=40, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r, depth=h, location=loc, rotation=rot)
    ob = bpy.context.object
    ob.name = name
    ob.data.materials.append(m)
    return smooth(ob)


def _fcurves(action):
    if hasattr(action, "fcurves") and action.fcurves is not None:
        try:
            return list(action.fcurves)
        except TypeError:
            pass
    out = []                                         # Blender 5 layered actions
    for layer in action.layers:
        for strip in layer.strips:
            for bag in strip.channelbags:
                out += list(bag.fcurves)
    return out


def color_key(m, frame, rgb):
    sock = m.node_tree.nodes["Principled BSDF"].inputs["Base Color"]
    sock.default_value = (*rgb, 1)
    sock.keyframe_insert("default_value", frame=frame)


# ---------------------------------------------------------------- world (kit park: sky, sun, grass tufts, hills, trees)
kit.park_world(keep_out=[(-3.2, 3.2, -1.0, 1.2)])

# little white fence posts left and right, like a play garden
fence_m = mat("fence", (0.95, 0.95, 0.92), rough=0.5)
for side in (-1, 1):
    for k in range(7):
        box(f"post{side}{k}", (side * (4.6 + k * 0.7), 3.5 - k * 0.15, 0.35), (0.12, 0.12, 0.7), fence_m, 0.03)
    box(f"rail{side}", (side * (4.6 + 2.1), 3.05, 0.5), (4.4, 0.06, 0.09), fence_m, 0.02)

# ---------------------------------------------------------------- the wooden paint board
wood = wood_mat()
SLOT_W, GAP, DEPTH = 0.95, 0.14, 1.2
xs = [(i - 2) * (SLOT_W + GAP) for i in range(5)]
W = 5 * SLOT_W + 6 * GAP
box("board_base", (0, 0, 0.05), (W, DEPTH + 2 * GAP, 0.10), wood, 0.03)
for k in range(6):
    x = -W / 2 + GAP / 2 + k * (SLOT_W + GAP)
    box(f"divider{k}", (x, 0, 0.17), (GAP, DEPTH + 2 * GAP, 0.24), wood, 0.035)
for sy in (-1, 1):
    box(f"rim{sy}", (0, sy * (DEPTH / 2 + GAP / 2), 0.17), (W, GAP, 0.24), wood, 0.035)
# a tall back panel, like the reference board
box("back_panel", (0, DEPTH / 2 + GAP + 0.06, 0.95), (W, 0.12, 1.9), wood, 0.04)

# each slot gets a thin coloured outline strip on the back panel so kids see where each colour goes
fills, buckets, streams, pivots, paint_in, splashes = [], [], [], [], [], []
for i, (name, rgb) in enumerate(T.COLOURS):
    x = xs[i]
    pm = mat(f"paint_{name}", rgb, rough=0.12, coat=0.6)

    # paint fill: origin on the slot floor so scaling Z raises the surface
    bpy.ops.mesh.primitive_cube_add(location=(0, 0, 0.5))
    fl = bpy.context.object
    fl.name = f"fill_{name}"
    fl.scale = (SLOT_W / 2 - 0.01, DEPTH / 2 - 0.01, 0.5)
    bpy.ops.object.transform_apply(location=True, scale=True)
    fl.location = (x, 0, 0.06)         # starts hidden under the board floor
    fl.scale = (1, 1, 0.001)
    fl.data.materials.append(pm)
    smooth(fl, 0.04, 3)
    fills.append(fl)

    # bucket: pivot sits on the front top lip; the bucket tilts forward to pour
    piv = bpy.data.objects.new(f"pivot_{name}", None)
    sc.collection.objects.link(piv)
    piv.location = (x, 0.12, 1.95)
    bm = mat(f"bucket_{name}", tuple(min(1, c * 1.1 + 0.05) for c in rgb), rough=0.35)
    bk = cyl(f"bucket_{name}", (0, 0.34, -0.30), 0.34, 0.60, bm)
    # open top: a darker paint disk just under the rim
    inner = cyl(f"bucket_paint_{name}", (0, 0.34, -0.06), 0.30, 0.02, pm)
    rim = None
    bpy.ops.mesh.primitive_torus_add(major_radius=0.34, minor_radius=0.035, location=(0, 0.34, 0.0))
    rim = bpy.context.object
    rim.data.materials.append(bm)
    smooth(rim)
    handle_m = mat(f"handle_{name}", (0.9, 0.9, 0.9), rough=0.3)
    bpy.ops.mesh.primitive_torus_add(major_radius=0.36, minor_radius=0.02, location=(0, 0.34, 0.05),
                                     rotation=(0, math.radians(90), 0))
    hd = bpy.context.object
    hd.data.materials.append(handle_m)
    smooth(hd)
    for ob in (bk, inner, rim, hd):
        ob.parent = piv
    pivots.append(piv)
    paint_in.append(inner)

    # stream: origin at the top, grows downward to the slot
    bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=0.06, depth=1.0, location=(0, 0, -0.5))
    st = bpy.context.object
    st.name = f"stream_{name}"
    bpy.ops.object.transform_apply(location=True)
    st.location = (x, 0.02, 1.90)
    st.scale = (1, 1, 0.0)
    st.data.materials.append(pm)
    smooth(st)
    streams.append(st)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.2, location=(x, 0.02, 0.2))
    sp = bpy.context.object
    sp.name = f"splash_{name}"
    sp.scale = (0, 0, 0)
    sp.data.materials.append(pm)
    smooth(sp)
    splashes.append(sp)

# ---------------------------------------------------------------- animation of the five pours
TILT = math.radians(105)
STREAM_LEN = 1.90 - 0.18
for i, (name, rgb) in enumerate(T.COLOURS):
    t = T.colour_start(i)
    piv, st, fl, inner = pivots[i], streams[i], fills[i], paint_in[i]
    for f, ang in [(F(t), 0), (F(t + 0.6), TILT), (F(t + 3.3), TILT), (F(t + 3.9), 0)]:
        piv.rotation_euler = (ang, 0, 0)
        piv.keyframe_insert("rotation_euler", frame=f)
    # paint leaves the bucket
    for f, s in [(F(t + 0.5), 1.0), (F(t + 3.2), 0.05)]:
        inner.scale = (s, s, 1)
        inner.keyframe_insert("scale", frame=f)
    # stream grows down, wobbles while pouring, then thins out
    seq = [(F(t + 0.50), (1, 1, 0)), (F(t + 0.75), (1, 1, STREAM_LEN))]
    tt = t + 0.75
    while tt < t + 3.0:
        w = 1.0 + 0.18 * math.sin(tt * 9)
        seq.append((F(tt), (w, w, STREAM_LEN)))
        tt += 0.25
    seq += [(F(t + 3.15), (0.3, 0.3, STREAM_LEN)), (F(t + 3.3), (0, 0, STREAM_LEN))]
    for f, s in seq:
        st.scale = s
        st.keyframe_insert("scale", frame=f)
    sp = splashes[i]
    for f, sc3 in [(F(t + 0.72), (0, 0, 0)), (F(t + 0.85), (1.3, 1.3, 0.45))] + \
            [(F(t + 0.85 + k * 0.25), (1.2 + 0.2 * (k % 2), 1.3 - 0.2 * (k % 2), 0.4)) for k in range(1, 9)] + \
            [(F(t + 3.3), (0.5, 0.5, 0.2)), (F(t + 3.45), (0, 0, 0))]:
        sp.scale = sc3
        sp.keyframe_insert("scale", frame=f)
    for f, z in [(F(t + 0.72), 0.13), (F(t + 3.2), 0.24)]:      # splash rides up with the paint surface
        sp.location.z = z
        sp.keyframe_insert("location", index=2, frame=f)
    # slot fills, with a small settle bounce at the end
    for f, z in [(F(t + 0.72), 0.001), (F(t + 3.2), 0.17), (F(t + 3.45), 0.185), (F(t + 3.7), 0.17)]:
        fl.scale = (1, 1, z)
        fl.keyframe_insert("scale", frame=f)

# ---------------------------------------------------------------- toy car for the outro (kit car with a face)
o = T.OUTRO
cv = kit.vehicle("car", T.COLOURS[0][1], loc=(9.0, -1.9, 0), yaw=math.radians(180), name="outro_car")
car, car_m = cv.root, cv.body_mats[0]
car.scale = (0.95, 0.95, 0.95)
for f, x in [(F(o - 0.6), 9.0), (F(o + 0.4), 0.0)]:
    car.location = (x, -1.9, 0)
    car.keyframe_insert("location", frame=f)
# little hop when it stops, and on the last word
for f, z in [(F(o + 0.4), 0), (F(o + 0.55), 0.18), (F(o + 0.75), 0),
             (F(o + 4 * T.BEAT), 0), (F(o + 4 * T.BEAT + 0.18), 0.25), (F(o + 4 * T.BEAT + 0.42), 0)]:
    car.location = (car.location.x, -1.9, z)
    car.keyframe_insert("location", index=2, frame=f)
kit.roll_wheels(cv, F(o - 0.6), F(o + 0.4), 9.0)
# once parked it turns three-quarters toward the camera so its face reads
for f, yaw in [(F(o + 0.45), 180), (F(o + 0.95), 235)]:
    car.rotation_euler = (0, 0, math.radians(yaw))
    car.keyframe_insert("rotation_euler", index=2, frame=f)
# eyes look toward the camera once parked, and blink on the beat
for lk in cv.looks:
    lk.rotation_euler = (0, 0, 0)
    lk.keyframe_insert("rotation_euler", frame=F(o + 0.4))
    lk.rotation_euler = (math.radians(-8), math.radians(14), 0)
    lk.keyframe_insert("rotation_euler", frame=F(o + 0.7))
kit.blink(cv, F(o + 2 * T.BEAT))
kit.blink(cv, F(o + 6 * T.BEAT))

# colour change on each sung word
for k, tw in enumerate(T.outro_word_times()):
    color_key(car_m, F(tw), T.COLOURS[k][1])
for fc in _fcurves(car_m.node_tree.animation_data.action):
    for kp in fc.keyframe_points:
        kp.interpolation = "CONSTANT"

# ---------------------------------------------------------------- camera: slow push, then follows each bucket
bpy.ops.object.camera_add()
cam = bpy.context.object
sc.camera = cam
cam.data.lens = 32
aim = bpy.data.objects.new("aim", None)
sc.collection.objects.link(aim)
tc = cam.constraints.new("TRACK_TO")
tc.target, tc.track_axis, tc.up_axis = aim, "TRACK_NEGATIVE_Z", "UP_Y"

shots = [(0.0, (0.0, -8.8, 2.5), (0.0, 0.6, 1.1)),
         (T.BLOCK - 0.3, (0.0, -7.4, 2.7), (0.0, 0.3, 0.9))]
for i in range(len(T.COLOURS)):
    t, x = T.colour_start(i), xs[i]
    shots += [(t + 0.2, (x * 0.45, -6.4, 2.7), (x * 0.7, 0.2, 1.0)),
              (t + T.BLOCK - 0.6, (x * 0.5, -6.1, 2.6), (x * 0.75, 0.2, 0.95))]
shots += [(T.OUTRO + 0.1, (1.2, -7.6, 2.0), (0.0, -0.6, 0.8)),
          (T.DURATION, (0.4, -6.4, 1.7), (0.0, -0.8, 0.8))]
for t, cl, al in shots:
    cam.location, aim.location = cl, al
    cam.keyframe_insert("location", frame=F(t))
    aim.keyframe_insert("location", frame=F(t))

# ---------------------------------------------------------------- render
os.makedirs(OUT, exist_ok=True)
sc.render.image_settings.file_format = "PNG"
if STILL is not None:
    for s in STILL:
        sc.frame_set(F(s))
        sc.render.filepath = os.path.join(OUT, f"still_{s:05.2f}.png")
        bpy.ops.render.render(write_still=True)
else:
    sc.render.filepath = os.path.join(OUT, "f_")
    bpy.ops.render.render(animation=True)
