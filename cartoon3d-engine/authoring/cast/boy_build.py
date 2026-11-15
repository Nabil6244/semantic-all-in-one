"""Noraiz (little brother): CGTrader 3DCartoon 'Cartoon Boy Rigged' (Editorial licence, user's pick 2026-11-15).
His rig and 33 face targets only exist in a binary Maya scene, so this builds him in Blender from Boy.fbx:
textures from the Maya SourceImages, subdivision, our own skeleton fitted to his parts, skin weights, face shapes.
Run: blender -b --python cast/boy_build.py -- <Boy.fbx> <SourceImages dir> <out dir>
"""
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

fbx, tex_dir, out = sys.argv[sys.argv.index("--") + 1:][:3]
TEX, OUT = Path(tex_dir).resolve(), Path(out)
OUT.mkdir(parents=True, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=fbx)
sc = bpy.context.scene

# --- flatten: every mesh unparented with its world transform baked in, empties removed ---
meshes = [o for o in bpy.data.objects if o.type == "MESH"]
for o in meshes:
    mw = o.matrix_world.copy()
    o.parent = None
    o.matrix_world = mw
for o in [o for o in bpy.data.objects if o.type != "MESH"]:
    bpy.data.objects.remove(o, do_unlink=True)
for o in meshes:
    o.data.transform(o.matrix_world)
    o.matrix_world.identity()
M = {o.name: o for o in meshes}

# --- textures (the FBX points at a missing fff.fbm folder) ---
TEXMAP = {"Face": "Boy_face_mid.jpg", "Body": "Boy_body_mid.jpg", "Teeth": "Boy_body_mid.jpg", "cloth": "Boy_yifu_color.jpg",
          "Belt": "Boy_yifu_color.jpg", "BeltHead": "Boy_yifu_color.jpg", "Trousers": "Boy_kuzi_color.jpg",
          "shose": "Boy_kuzi_color.jpg", "Hair": "Boy_hair_color.jpg", "Iris": "Boy_eye_color.jpg", "Eye": "Boy_eye_color.jpg"}
ROUGH = {"Face": 0.55, "Body": 0.6, "Teeth": 0.3, "Iris": 0.15, "Eye": 0.15, "Hair": 0.7}
done = set()
for o in meshes:
    for m in o.data.materials:
        if not m or m.name in done:
            continue
        done.add(m.name)
        key = m.name.split("_M1")[0]
        if key not in TEXMAP:
            print("NO_TEX", m.name)
            continue
        m.use_nodes = True
        nt = m.node_tree
        nt.nodes.clear()
        outn = nt.nodes.new("ShaderNodeOutputMaterial")
        p = nt.nodes.new("ShaderNodeBsdfPrincipled")
        img = nt.nodes.new("ShaderNodeTexImage")
        img.image = bpy.data.images.load(str(TEX / TEXMAP[key]), check_existing=True)
        nt.links.new(img.outputs["Color"], p.inputs["Base Color"])
        nt.links.new(p.outputs["BSDF"], outn.inputs["Surface"])
        p.inputs["Roughness"].default_value = ROUGH.get(key, 0.8)
        if key in ("Face", "Body"):     # soft skin, a touch fairer/cooler than the warm Maya texture
            p.inputs["Subsurface Weight"].default_value = 0.15
            p.inputs["Subsurface Radius"].default_value = (0.02, 0.008, 0.005)
            hsv = nt.nodes.new("ShaderNodeHueSaturation")
            hsv.inputs["Saturation"].default_value, hsv.inputs["Value"].default_value = 0.82, 1.12
            nt.links.new(img.outputs["Color"], hsv.inputs["Color"])
            nt.links.new(hsv.outputs["Color"], p.inputs["Base Color"])
        if key == "Iris":               # outer eye shell was a clear cornea in Maya: glossy, see-through
            for l in list(p.inputs["Base Color"].links):
                nt.links.remove(l)
            p.inputs["Alpha"].default_value = 0.0
            p.inputs["Roughness"].default_value = 0.0
            p.inputs["Coat Weight"].default_value = 1.0
            if hasattr(m, "surface_render_method"):
                m.surface_render_method = "BLENDED"
for o in meshes:
    for f in o.data.polygons:
        f.use_smooth = True


def bbox(o):
    P = [v.co for v in o.data.vertices]
    return Vector([min(p[i] for p in P) for i in range(3)]), Vector([max(p[i] for p in P) for i in range(3)])


# --- skeleton fitted to his parts (front is -Y, Z up) ---
arm0, arm1 = bbox(M["L_arm_geo"])
leg0, leg1 = bbox(M["L_leg_geo"])
sh0, sh1 = bbox(M["L_shoe_geo"])
pants0, pants1 = bbox(M["pants_geo"])
cloth0, cloth1 = bbox(M["cloth_geo"])
face0, face1 = bbox(M["face_geo"])
eyeL = sum(bbox(M["polySurface168.001"]), Vector()) / 2
eyeR = sum(bbox(M["polySurface168"]), Vector()) / 2
tooth0, tooth1 = bbox(M["tooth_up_geo"])
arm_z = (arm0.z + arm1.z) / 2
arm_y = (arm0.y + arm1.y) / 2
hand_x = arm1.x - 0.085                            # mitten-like hands: last ~8.5 cm of the arm part
elbow_x = arm0.x + 0.48 * (hand_x - arm0.x)
sh_x = arm0.x - 0.03
leg_x = (leg0.x + leg1.x) / 2
hip_z, ankle_z = pants1.z - 0.045, sh1.z - 0.01
knee_z = (hip_z + ankle_z) / 2 + 0.01
neck_z = cloth1.z - 0.01
mouth_z = (tooth0.z + tooth1.z) / 2
print("FIT arm", round(arm0.x, 3), round(elbow_x, 3), round(hand_x, 3), "z", round(arm_z, 3), "hip", round(hip_z, 3), "knee", round(knee_z, 3),
      "ankle", round(ankle_z, 3), "neck", round(neck_z, 3), "mouth", round(mouth_z, 3))

arm_data = bpy.data.armatures.new("noraiz_rig")
rig = bpy.data.objects.new("noraiz_rig", arm_data)
sc.collection.objects.link(rig)
bpy.context.view_layer.objects.active = rig
bpy.ops.object.mode_set(mode="EDIT")
eb = arm_data.edit_bones


def bone(name, head, tail, parent=None, deform=True, roll=0.0):
    b = eb.new(name)
    b.head, b.tail, b.roll = Vector(head), Vector(tail), roll
    if parent:
        b.parent = eb[parent]
    b.use_deform = deform
    return b


bone("root", (0, 0, 0), (0, 0.15, 0), deform=False)
bone("hips", (0, 0.01, hip_z - 0.04), (0, 0.01, hip_z + 0.08), "root")
bone("spine", (0, 0.01, hip_z + 0.08), (0, 0.0, (hip_z + neck_z) / 2 + 0.06), "hips")
bone("chest", (0, 0.0, (hip_z + neck_z) / 2 + 0.06), (0, 0.0, neck_z), "spine")
bone("neck", (0, 0.0, neck_z), (0, 0.0, neck_z + 0.07), "chest")
bone("head", (0, 0.0, neck_z + 0.07), (0, 0.0, face1.z), "neck")
bone("jaw", (0, -0.01, mouth_z + 0.06), (0, face0.y + 0.03, face0.z + 0.12), "head")
for side, s in (("L", 1), ("R", -1)):
    e = eyeL if s > 0 else eyeR
    bone(f"eye.{side}", e, e + Vector((0, -0.08, 0)), "head")
    bone(f"shoulder.{side}", (s * 0.05, arm_y, arm_z + 0.02), (s * sh_x, arm_y, arm_z), "chest")
    bone(f"upper_arm.{side}", (s * sh_x, arm_y, arm_z), (s * elbow_x, arm_y + 0.005, arm_z), f"shoulder.{side}")
    bone(f"forearm.{side}", (s * elbow_x, arm_y + 0.005, arm_z), (s * hand_x, arm_y, arm_z), f"upper_arm.{side}")
    bone(f"hand.{side}", (s * hand_x, arm_y, arm_z), (s * arm1.x, arm_y, arm_z), f"forearm.{side}")
    bone(f"thigh.{side}", (s * leg_x, 0.01, hip_z), (s * leg_x, 0.0, knee_z), "hips")
    bone(f"shin.{side}", (s * leg_x, 0.0, knee_z), (s * leg_x, 0.01, ankle_z), f"thigh.{side}")
    bone(f"foot.{side}", (s * leg_x, 0.01, ankle_z), (s * leg_x, sh0.y + 0.03, 0.02), f"shin.{side}")
for b in eb:   # connect chains where head meets parent tail
    if b.parent and (b.head - b.parent.tail).length < 1e-4:
        b.use_connect = True
bpy.ops.object.mode_set(mode="OBJECT")

# --- skin: heat weights for body parts, hand-built weights for the head ---
RIGID = {"hair_geo": "head", "L_brow_geo": "head", "R_brow_geo": "head", "tooth_up_geo": "head",
         "tooth_down_geo": "jaw", "gum_down_geo": "jaw", "tongue_geo": "jaw",
         "polySurface167": "eye.R", "polySurface168": "eye.R", "polySurface167.001": "eye.L", "polySurface168.001": "eye.L",
         "L_shoe_geo": "foot.L", "R_shoe_geo": "foot.R", "braces_sign_geo": "chest"}


def add_arm_mod(o):
    md = o.modifiers.new("rig", "ARMATURE")
    md.object = rig
    o.parent = rig


for n, b in RIGID.items():
    o = M[n]
    o.vertex_groups.new(name=b).add(range(len(o.data.vertices)), 1.0, "REPLACE")
    add_arm_mod(o)

auto = [M[n] for n in ("cloth_geo", "braces_geo", "pants_geo", "L_arm_geo", "R_arm_geo", "L_leg_geo", "R_leg_geo")]
bpy.ops.object.select_all(action="DESELECT")
for o in auto:
    o.select_set(True)
rig.select_set(True)
bpy.context.view_layer.objects.active = rig
bpy.ops.object.parent_set(type="ARMATURE_AUTO")
for o in auto:
    print("AUTO", o.name, len(o.vertex_groups))

# head/neck: head 1.0, blend to neck under the jaw line, jaw region below the mouth corners
face = M["face_geo"]
vg = {n: face.vertex_groups.new(name=n) for n in ("head", "neck", "jaw")}
jaw_pivot = Vector((0, -0.01, mouth_z + 0.06))
for v in face.data.vertices:
    p = v.co
    nk = min(max((neck_z + 0.07 - p.z) / 0.07, 0.0), 1.0)                  # neck blend at the base
    below = min(max((mouth_z + 0.005 - p.z) / 0.03, 0.0), 1.0)              # under the lip line
    front = min(max((-p.y - 0.02) / 0.08, 0.0), 1.0)                        # face side, not the back of the head
    side = min(max((0.20 - abs(p.x)) / 0.07, 0.0), 1.0)                    # fades out towards the cheeks/ears
    j = below * front * side * (1 - nk)
    vg["jaw"].add([v.index], j, "REPLACE")
    vg["neck"].add([v.index], nk, "REPLACE")
    vg["head"].add([v.index], max(0.0, 1 - j - nk), "REPLACE")
add_arm_mod(face)

# --- face shapes (his artist's 33 Maya targets are unreadable here, so the core set is rebuilt) ---
def smooth(t):
    t = min(max(t, 0.0), 1.0)
    return t * t * (3 - 2 * t)


face.shape_key_add(name="Basis")
base = [v.co.copy() for v in face.data.vertices]
eye_r = (bbox(M["polySurface168"])[1].x - bbox(M["polySurface168"])[0].x) / 2
corner_x = tooth1.x + 0.012                      # lip corners sit just outside the teeth
corners = {}
for sgn in (1, -1):
    near = [p for p in base if abs(p.x - sgn * corner_x) < 0.012 and abs(p.z - mouth_z) < 0.012]
    corners[sgn] = min(near, key=lambda p: p.y)     # front-most skin at the corner
print("FACE eye_r", round(eye_r, 3), "corner_x", round(corner_x, 3), "mouth_z", round(mouth_z, 3))


def key(name, fn):
    k = face.shape_key_add(name=name, from_mix=False)
    k.value = 0.0                                   # new keys start ON in Blender 5: rest face must be clean
    for i, p in enumerate(base):
        d = fn(p)
        if d is not None:
            k.data[i].co = p + d
    return k


def lid(side):
    c = eyeL if side > 0 else eyeR
    R = eye_r + 0.011                                      # lid rides clear of the eyeball

    def fn(p):
        rel = p - c
        dxz = math.hypot(rel.x, rel.z)
        if p.y > c.y or dxz > R * 1.55 or rel.z < -0.004 * 0:   # front of the eye, upper half only
            return None
        if rel.z < 0:
            return None
        w = smooth(1 - (dxz - R * 0.75) / (R * 0.8))        # rim moves fully, brow area barely
        tz = -0.40 * R                                     # lid edge closes below centre: no white sliver
        nz = rel.z + (tz - rel.z) * w
        nx = rel.x * (1 - 0.15 * w)
        ny_sq = max(R * R - nx * nx - nz * nz, 0.0)
        ny = -math.sqrt(ny_sq) - 0.004                    # ride over the eyeball surface
        tgt = Vector((nx, ny, nz))
        return (tgt - rel) * w
    return fn


def corner_pull(dz, dx_out, dy=0.0, radius=0.055, both=True):
    def fn(p):
        out = Vector()
        hit = False
        for s, c in corners.items():
            d = (p - c).length
            if d < radius and p.y < c.y + 0.05:
                w = smooth(1 - d / radius)
                out += Vector((s * dx_out, dy, dz)) * w
                hit = True
        return out if hit else None
    return fn


key("smile", corner_pull(0.026, 0.013, 0.005, 0.065))
key("mouth_wide", corner_pull(0.002, 0.016))
key("mouth_oo", corner_pull(0.0, -0.032, -0.016, 0.065))
key("frown", corner_pull(-0.012, 0.002))
key("blink.L", lid(1))
key("blink.R", lid(-1))


def brow(p):
    if p.z < eyeL.z + eye_r * 0.9 or p.y > eyeL.y + 0.02 or abs(p.x) > 0.2:
        return None
    w = smooth(1 - abs(p.z - (eyeL.z + eye_r * 1.6)) / 0.05)
    return Vector((0, 0, 0.012 * w)) if w > 0 else None


key("brow_up", brow)
for b in ("L_brow_geo", "R_brow_geo"):      # brows follow brow_up through a matching key on the brow pieces
    o = M[b]
    o.shape_key_add(name="Basis")
    k = o.shape_key_add(name="brow_up", from_mix=False)
    k.value = 0.0
    for i, v in enumerate(o.data.vertices):
        k.data[i].co = v.co + Vector((0, 0, 0.012))
print("KEYS", [k.name for k in face.data.shape_keys.key_blocks])


for o in meshes:   # smooth after the rig bends them
    sd = o.modifiers.new("smooth", "SUBSURF")
    sd.levels, sd.render_levels = 1, 2

bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "noraiz_rigged.blend"))
print("SAVED", OUT / "noraiz_rigged.blend")
