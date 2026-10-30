"""Blender (background) prep of the gym muscles: Z-Anatomy Startup.blend ("4: Muscular system") -> muscles.glb (one Layer_M_<group> empty per training muscle group, left and right) + anchors_muscles.json.
Same world frame as the other prepared models (metres, Z up, front -Y), so muscles.glb can be merged into the body without moving anything (see build_gym_body.py).
Run: Blender -b Startup.blend --python prep_muscles.py -- OUT_DIR       Derived from CC BY-SA 4.0 material (Z-Anatomy): local use until licensing is resolved, as for the other models."""
import json, sys, time
import bpy
from mathutils import Vector

OUT = sys.argv[sys.argv.index("--") + 1]; t0 = time.time()
# group -> (substrings of the Z-Anatomy object names, sided: one anchor per side)
GROUPS = {
    "biceps": (("biceps brachii", "brachialis", "coracobrachialis"), True), "triceps": (("triceps brachii", "anconeus"), True),
    "deltoid": (("deltoid muscle",), True), "chest": (("pectoralis",), False), "lats": (("latissimus", "teres major"), False),
    "traps": (("trapezius", "rhomboid", "levator scapulae"), False), "rotator_cuff": (("supraspinatus", "infraspinatus", "teres minor", "subscapularis"), True),
    "serratus": (("serratus anterior",), True), "abs": (("rectus abdominis", "abdominal oblique", "transversus abdominis", "pyramidalis"), False),
    "erectors": (("longissimus thoracis", "iliocostalis lumborum", "iliocostalis thoracis", "spinalis thoracis", "multifidus lumborum", "quadratus lumborum"), False),
    "glutes": (("gluteus", "piriformis"), True), "quads": (("rectus femoris", "vastus", "sartorius", "tensor fasciae latae"), True),
    "hamstrings": (("semitendinosus", "semimembranosus", "head of biceps femoris"), True), "adductors": (("adductor longus", "adductor magnus", "adductor brevis", "gracilis", "pectineus"), True),
    "calves": (("gastrocnemius", "soleus", "plantaris"), True), "shins": (("tibialis anterior", "fibularis", "extensor digitorum longus", "extensor hallucis longus"), True),
    "forearm_flexors": (("flexor carpi", "flexor digitorum", "palmaris longus", "pronator teres", "flexor pollicis longus"), True),
    "forearm_extensors": (("extensor carpi", "extensor digitorum.", "extensor digiti", "brachioradialis", "supinator", "extensor indicis", "extensor pollicis", "abductor pollicis longus"), True),
    "hip_flexors": (("psoas major", "iliacus", "iliopsoas"), True), "neck": (("sternocleidomastoid", "scalenus", "splenius"), True),
}
BAD = ("(", "fascia", "bursa", "sheath", "retinaculum", "septum", "ligament", "aponeurosis", "tract", "tendon of", "tendinous", "compartment", "muscles.j", "part of muscular", "tarsus", "trochlea")

def find(c, name):
    if c.name == name: return c
    for ch in c.children:
        r = find(ch, name)
        if r: return r
root = bpy.context.scene.collection; mc = find(root, "4: Muscular system")
def mat(rgb):
    m = bpy.data.materials.new("HC_gym_muscle"); m.use_nodes = True; b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1); b.inputs["Roughness"].default_value = 0.5; return m
M = mat((0.62, 0.16, 0.12))
def dup(o):
    n = o.copy(); n.data = o.data.copy(); n.name = o.name; bpy.context.scene.collection.objects.link(n); n.parent = None; n.matrix_world = o.matrix_world.copy(); return n
def decimate(o, r):
    md = o.modifiers.new("d", "DECIMATE"); md.ratio = r
    with bpy.context.temp_override(object=o, active_object=o): bpy.ops.object.modifier_apply(modifier=md.name)
def bb(objs):
    p = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]; mn = [min(q[i] for q in p) for i in range(3)]; mx = [max(q[i] for q in p) for i in range(3)]
    return {"min": mn, "max": mx, "center": [(a + b) / 2 for a, b in zip(mn, mx)]}
cand = [o for o in mc.all_objects if o.type == "MESH" and len(o.data.polygons) > 20 and not any(k in o.name.lower() for k in BAD)]
L, taken, A = {}, set(), {}
for g, (keys, sided) in GROUPS.items():
    objs = [o for o in cand if o.name not in taken and any(k in o.name.lower() for k in keys)]
    if not objs: print("EMPTY", g); continue
    mine, side = [], {}
    for o in objs:
        taken.add(o.name); n = dup(o); decimate(n, 0.3); n.data.materials.clear(); n.data.materials.append(M)
        for p in n.data.polygons: p.use_smooth = True
        mine.append(n); side[n.name] = o.name.rsplit('.', 1)[-1]
    e = bpy.data.objects.new("Layer_M_" + g, None); bpy.context.scene.collection.objects.link(e)
    for o in mine: mw = o.matrix_world.copy(); o.parent = e; o.matrix_world = mw
    L[g] = mine; A[g] = bb(mine)
    if sided:
        for s in ("r", "l"):
            part = [o for o in mine if side[o.name] == s]
            if part: A[f"{g}_{s}"] = bb(part)
    print("GROUP", g, len(mine), sum(len(o.data.polygons) for o in mine))
for o in list(bpy.data.objects):      # nothing from the atlas but the copies and their layer empties
    if o.name not in {x.name for v in L.values() for x in v} and not o.name.startswith("Layer_M_"): bpy.data.objects.remove(o, do_unlink=True)
for c in list(bpy.data.collections): bpy.data.collections.remove(c)
json.dump({"anchors": A, "groups": {g: [o.name for o in v] for g, v in L.items()}}, open(OUT + "/anchors_muscles.json", "w"), indent=1)
bpy.ops.object.select_all(action="SELECT")
bpy.ops.export_scene.gltf(filepath=OUT + "/muscles.glb", export_format="GLB", use_selection=False, export_apply=True, export_materials="EXPORT", export_cameras=False, export_lights=False, export_yup=True)
print("MUSCLES done sec", round(time.time() - t0, 1))
