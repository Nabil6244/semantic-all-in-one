"""Put the approved cast into the playland set and render test shots.
Cast: host (redhead, build/cast/redhead_v8/host.blend), Hoorain (build/cast/hoorain_v6/hoorain.blend),
Noraiz (build/cast/noraiz_v4/noraiz_rigged.blend). Each is appended under its own empty (CH-*) so it can be
scaled/placed as one; lowest point lands on the floor.
Run: blender -b <playland.blend> --python sets/compose.py -- <authoring dir> <out dir>
"""
import math
import sys
from pathlib import Path

import bpy
from mathutils import Euler, Vector

root, out = [Path(a) for a in sys.argv[sys.argv.index("--") + 1:][:2]]
out.mkdir(parents=True, exist_ok=True)
sc = bpy.context.scene
CAST = [  # name, blend, target height (m), floor position, yaw (deg, + turns toward camera-left)
    ("host", root / "build/cast/redhead_v8/host.blend", 1.62, (-0.7, -2.2), 12),
    ("hoorain", root / "build/cast/hoorain_v6/hoorain.blend", 1.0, (0.3, -2.3), -8),
    ("noraiz", root / "build/cast/noraiz_v4/noraiz_rigged.blend", 0.88, (1.0, -2.1), -18),
]


def append_all(blend):
    with bpy.data.libraries.load(str(blend), link=False) as (src, dst):
        dst.objects = [n for n in src.objects]
    objs = [o for o in dst.objects if o is not None and o.type not in ("CAMERA", "LIGHT")]
    for o in dst.objects:
        if o is not None and o.type in ("CAMERA", "LIGHT"):
            bpy.data.objects.remove(o, do_unlink=True)
    col = bpy.data.collections.new(f"CH-{blend.stem}")
    sc.collection.children.link(col)
    for o in objs:
        col.objects.link(o)
        if o.name.startswith(("WGT", "cs_", "bone_shape")) or o.type in ("EMPTY",) and o.name.startswith("cs"):
            o.hide_render = o.hide_viewport = True        # rig control shapes: hidden in their own file's collections
    return objs, col


def fix_missing_images():
    """Appended images keep paths relative to their source file: re-find each by name under downloads/ and build/."""
    import os
    index = {}
    for base in (root / "downloads", root / "build" / "cast"):
        for d, _, files in os.walk(base):
            for f in files:
                index.setdefault(f.lower(), os.path.join(d, f))
    fixed = 0
    for img in bpy.data.images:
        if img.packed_file or not img.filepath:
            continue
        if not os.path.exists(bpy.path.abspath(img.filepath)):
            hit = index.get(os.path.basename(img.filepath.replace("\\", "/")).lower())
            if hit:
                img.filepath = hit
                img.reload()
                fixed += 1
    print("IMAGES_FIXED", fixed)


def visible_points(objs):
    dg = bpy.context.evaluated_depsgraph_get()
    P = []
    for o in objs:
        if o.type == "MESH" and not o.hide_render and any(m.type == "ARMATURE" for m in o.modifiers):   # skinned body parts only
            e = o.evaluated_get(dg)
            m = e.to_mesh()
            P += [o.matrix_world @ v.co for v in m.vertices]
            e.to_mesh_clear()
    return [p for p in P if abs(p.z) < 50]          # drop CC occlusion shells parked far away


def aim(rig, pb, d_world):
    head = rig.matrix_world @ pb.head
    cur = (rig.matrix_world @ pb.tail - head).normalized()
    r = cur.rotation_difference(Vector(d_world).normalized())
    q = rig.matrix_world.to_quaternion()
    r = q.inverted() @ r @ q
    m = pb.matrix.copy()
    loc = m.to_translation()
    m.translation = (0, 0, 0)
    new = r.to_matrix().to_4x4() @ m
    new.translation = loc
    pb.matrix = new
    bpy.context.view_layer.update()


holders = {}
for name, blend, height, (x, y), yaw in CAST:
    objs, col = append_all(blend)
    holder = bpy.data.objects.new(f"CH-{name}", None)
    col.objects.link(holder)
    for o in objs:
        if o.parent is None:
            o.parent = holder
    bpy.context.view_layer.update()
    # pose fixes that were only applied in sheet scripts
    if name == "noraiz":
        rig = bpy.data.objects["noraiz_rig"]
        for s, side in ((1, "L"), (-1, "R")):
            aim(rig, rig.pose.bones[f"upper_arm.{side}"], (s * 0.38, 0.02, -0.92))
            aim(rig, rig.pose.bones[f"forearm.{side}"], (s * 0.22, -0.18, -0.96))
        face = bpy.data.objects["face_geo"]
        face.data.shape_keys.key_blocks["smile"].value = 0.7
    if name == "hoorain":
        rig = next(o for o in objs if o.type == "ARMATURE" and o.name.startswith("rig"))
        pbs = rig.pose.bones
        for side, s in (("l", 1), ("r", -1)):
            ik = pbs.get(f"c_hand_ik.{side}")
            if ik is not None and "ik_fk_switch" in ik.keys():
                ik["ik_fk_switch"] = 1.0                  # Auto-Rig Pro: 1 = FK arms
            bpy.context.view_layer.update()
            if f"c_arm_fk.{side}" in pbs:
                aim(rig, pbs[f"c_arm_fk.{side}"], (s * 0.32, 0.03, -0.95))
                aim(rig, pbs[f"c_forearm_fk.{side}"], (s * 0.15, -0.2, -0.97))
        print("HOORAIN_ARMS", [n for n in ("c_arm_fk.l", "c_forearm_fk.l") if n in pbs])
    P = visible_points(objs)
    h = max(p.z for p in P) - min(p.z for p in P)
    k = height / h
    holder.scale = (k, k, k)
    bpy.context.view_layer.update()
    P = visible_points(objs)
    cx = sum(p.x for p in P) / len(P)
    cy = sum(p.y for p in P) / len(P)
    holder.location = (x - cx, y - cy, -min(p.z for p in P))
    holder.rotation_euler = Euler((0, 0, math.radians(yaw)), "XYZ")
    bpy.context.view_layer.update()
    P = visible_points(objs)
    print("PLACED", name, "h", round(max(p.z for p in P) - min(p.z for p in P), 3), "floor", round(min(p.z for p in P), 3),
          "at", round(sum(p.x for p in P) / len(P), 2), round(sum(p.y for p in P) / len(P), 2))
    holders[name] = holder

fix_missing_images()

# cameras: wide (set camera) + group two-shot
cam_w = bpy.data.objects["CAM-wide"]
cd = bpy.data.cameras.new("CAM-group")
cam_g = bpy.data.objects.new("CAM-group", cd)
sc.collection.objects.link(cam_g)
cd.lens = 32
cam_g.location = (0.1, -5.6, 1.1)
cam_g.rotation_euler = Euler((math.radians(86), 0, 0), "XYZ")
cd.dof.use_dof = True
cd.dof.focus_distance = 3.4
cd.dof.aperture_fstop = 2.8
sc.render.resolution_x, sc.render.resolution_y = 1280, 720
for cam, name in ((cam_w, "wide_cast"), (cam_g, "group")):
    sc.camera = cam
    sc.render.filepath = str(out / f"{name}.png")
    bpy.ops.render.render(write_still=True)
bpy.ops.wm.save_as_mainfile(filepath=str(out / "scene.blend"))
print("DONE", out)
