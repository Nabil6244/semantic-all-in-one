"""New host (2026-11-15): Canino3d 'Free Stylized Cartoon Girl Rigged Character' (Sketchfab, CC-BY: credit
"Free Stylized Cartoon Girl Rigged Character by Canino3d, CC-BY"). Character Creator base: same face keys as the old lead.
Step 1: import, resting smile, arms down, look sheet. Step 2: coral tee + denim overalls from her body, white sneakers.
Run: blender -b --python cast/redhead_restyle.py -- <MJ.fbx> <out dir>
"""
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

fbx, out = sys.argv[sys.argv.index("--") + 1:][:2]
OUT = Path(out)
OUT.mkdir(parents=True, exist_ok=True)
SMILE = {"Mouth_Smile": 0.8, "Mouth_Smile_L": 0.3, "Mouth_Smile_R": 0.3, "Cheek_Raise_L": 0.25, "Cheek_Raise_R": 0.25,
         "Eye_Squint_L": 0.2, "Eye_Squint_R": 0.2, "Mouth_Lips_Part": 0.3, "Brow_Raise_Inner_L": 0.2, "Brow_Raise_Inner_R": 0.2}

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=fbx)
sc = bpy.context.scene
rig = next(o for o in bpy.data.objects if o.type == "ARMATURE")
# her FBX skeleton 'rest' has the arms hanging down while the mesh was bound in the imported A-pose (frame 1 of its
# action): make that imported pose the rest pose (meshes untouched), or every rotation bends the mesh the wrong way
bpy.context.view_layer.update()
bpy.context.view_layer.objects.active = rig
bpy.ops.object.mode_set(mode="POSE")
bpy.ops.pose.armature_apply(selected=False)
bpy.ops.object.mode_set(mode="OBJECT")
for o in bpy.data.objects:
    if o.animation_data:
        o.animation_data_clear()
for pb in rig.pose.bones:
    pb.location, pb.rotation_quaternion, pb.rotation_euler, pb.scale = (0, 0, 0), (1, 0, 0, 0), (0, 0, 0), (1, 1, 1)
    if o.type == "MESH" and o.data.shape_keys and o.data.shape_keys.animation_data:
        o.data.shape_keys.animation_data_clear()
print("BONES", [b.name for b in rig.data.bones][:40])
for n in ("CC_Base_EyeOcclusion", "CC_Base_TearLine"):
    if n in bpy.data.objects:
        bpy.data.objects[n].hide_render = True
for o in bpy.data.objects:
    if o.type == "MESH" and o.data.shape_keys:
        kb = o.data.shape_keys.key_blocks
        for k, v in SMILE.items():
            if k in kb:
                kb[k].value = v
for img in bpy.data.images:           # textures sit next to source/ in textures/
    if img.filepath and not Path(bpy.path.abspath(img.filepath)).exists():
        cand = Path(fbx).resolve().parent.parent / "textures" / Path(img.filepath.replace("\\", "/")).name
        if cand.exists():
            img.filepath = str(cand)
            img.reload()

# --- kids-show outfit: coral tee + denim overalls cut from her own body surface (keeps the skin weights), white sneakers ---
import bmesh
from mathutils.bvhtree import BVHTree

TEE, DENIM, CUFF, POCKET = "#ff7a5c", "#2c4a72", "#5b7aa6", "#263f62"
body = bpy.data.objects["CC_Base_Body"]
for n in ("Top_Top_lambert2_0", "Outfit_Japan_Skirt_Model", "Outfit_Japan_Panties_Model"):   # crop top, mini skirt, underwear off
    if n in bpy.data.objects:
        bpy.data.objects.remove(bpy.data.objects[n], do_unlink=True)


def lin(h):
    h = h.lstrip("#")
    return tuple((int(h[i:i + 2], 16) / 255) ** 2.2 for i in (0, 2, 4)) + (1.0,)


def bh(name):
    return rig.matrix_world @ rig.data.bones[name].head_local


waist_z, spine2_z, neck_z = bh("CC_Base_Waist").z, bh("CC_Base_Spine02").z, bh("CC_Base_NeckTwist01").z
sh_x, el_x, wr_x = abs(bh("CC_Base_L_Upperarm").x), abs(bh("CC_Base_L_Forearm").x), abs(bh("CC_Base_L_Hand").x)
ankle_z = bh("CC_Base_L_Foot").z
knee_z = bh("CC_Base_L_Calf").z
chest_z = spine2_z + 0.55 * (neck_z - spine2_z)
neckline_z = neck_z - 0.05                  # crew neck below the head-weighted skin: clean edge
sleeve_x = sh_x + 0.42 * (el_x - sh_x)
hem_z = ankle_z + 0.035                       # trousers stop just above the sneaker collar
belt_z = waist_z + 0.035                      # overall trousers ride a little above her natural waist
mw = body.matrix_world
cy = sum((mw @ v.co).y for v in body.data.vertices) / len(body.data.vertices)
print("LANDMARKS waist", round(waist_z, 3), "chest", round(chest_z, 3), "neck", round(neck_z, 3), "sleeve_x", round(sleeve_x, 3), "ankle", round(ankle_z, 3))
skip_groups = {i for i, g in enumerate(body.vertex_groups) if any(k in g.name for k in ("Hand", "Finger", "Thumb", "Index", "Mid", "Ring", "Pinky", "Head", "Jaw", "Eye", "Tongue", "Teeth"))}


def material(name, hexcol, rough=0.85, noise_fac=0.12, scale=450):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    p = nt.nodes["Principled BSDF"]
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = scale
    mix = nt.nodes.new("ShaderNodeMixRGB")
    mix.blend_type, mix.inputs["Fac"].default_value = "MULTIPLY", noise_fac
    mix.inputs["Color1"].default_value = lin(hexcol)
    nt.links.new(noise.outputs["Color"], mix.inputs["Color2"])
    nt.links.new(mix.outputs["Color"], p.inputs["Base Color"])
    p.inputs["Roughness"].default_value = rough
    return m


def piece(name, keep, push_m, mat, solid_m=0.003, planes=(), subdiv=1, drape=False, straight=0.0):
    """Copy of the body, cut to `keep(world centre)` along straight `planes`, pushed out along normals, solidified."""
    o = body.copy()
    o.data = body.data.copy()
    o.name = name
    sc.collection.objects.link(o)
    o.shape_key_clear()
    for m in [m for m in o.modifiers if m.type != "ARMATURE"]:
        o.modifiers.remove(m)
    bm = bmesh.new()
    bm.from_mesh(o.data)
    if subdiv:
        bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=subdiv, use_grid_fill=True)
    m4 = o.matrix_world
    inv = m4.inverted()
    for co, no in planes:
        bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], plane_co=inv @ Vector(co),
                               plane_no=(inv.to_3x3().transposed().inverted() @ Vector(no)).normalized(), dist=1e-6)
    defl = bm.verts.layers.deform.verify()
    def skin_only(f):
        return any(any(g in skip_groups and w > 0.3 for g, w in v[defl].items()) for v in f.verts)
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if skin_only(f) or not keep(m4 @ f.calc_center_median())], context="FACES")
    bm.normal_update()
    scale = m4.to_scale()[0]
    for v in bm.verts:
        v.co += v.normal * (push_m / scale)
    if straight:   # straight-leg overalls: below the crotch every leg is at least a straight tube (knees/calves don't show)
        for v in bm.verts:
            w = m4 @ v.co
            if w.z > crotch_z:
                continue
            side = "L" if w.x > 0 else "R"
            hip, knee, ank = (bh(f"CC_Base_{side}_Thigh"), bh(f"CC_Base_{side}_Calf"), bh(f"CC_Base_{side}_Foot"))
            a, b = (knee, hip) if w.z > knee.z else (ank, knee)
            t = min(max((w.z - a.z) / max(b.z - a.z, 1e-4), 0.0), 1.0)
            c = a.lerp(b, t)
            r_t = straight * (0.82 + 0.18 * min(max((w.z - hem_z) / max(crotch_z - hem_z, 1e-4), 0.0), 1.0))
            d = Vector((w.x - c.x, w.y - c.y, 0.0))
            ease = min(max((crotch_z - w.z) / 0.06, 0.0), 1.0)          # blend in just under the crotch
            if d.length < r_t and d.length > 1e-5:
                d2 = d.normalized() * (d.length + (r_t - d.length) * ease)
                v.co = inv @ Vector((c.x + d2.x, c.y + d2.y, w.z))
    if drape:   # front panel hangs straight down from the bust like real cloth, eased back into the waistband
        front = [(v, m4 @ v.co) for v in bm.verts if (m4 @ v.co).y < cy]
        BIN = 0.02
        lo_x = min(w.x for _, w in front)
        nb = int((max(w.x for _, w in front) - lo_x) / BIN) + 2
        prof = {}                                   # per x-bin: (z, y) samples, most forward y seen at or above each height
        for _, w in front:
            prof.setdefault(int((w.x - lo_x) / BIN), []).append((w.z, w.y))
        def ahead(i, z):                            # most forward y in bin i among points higher than z
            ys = [y for zz, y in prof.get(i, []) if zz >= z]
            return min(ys) if ys else None
        for v, w in front:
            f = (w.x - lo_x) / BIN - 0.5
            i0 = max(0, int(math.floor(f)))
            t = min(max(f - i0, 0.0), 1.0)
            a0, a1 = ahead(i0, w.z), ahead(i0 + 1, w.z)
            if a0 is None and a1 is None:
                continue
            a0 = a1 if a0 is None else a0
            a1 = a0 if a1 is None else a1
            target = min(w.y, a0 * (1 - t) + a1 * t)
            ease = min(max((w.z - (belt_z + 0.01)) / 0.09, 0.0), 1.0)      # bottom 9 cm meets the waistband
            edge = min(max((BIB_X - abs(w.x)) / 0.025, 0.0), 1.0)          # outer 2.5 cm keeps her shape: no side walls
            y = w.y + (target - w.y) * ease * edge
            v.co = inv @ Vector((w.x, y, w.z))
    bm.to_mesh(o.data)
    bm.free()
    o.data.materials.clear()
    o.data.materials.append(mat)
    sol = o.modifiers.new("solid", "SOLIDIFY")
    sol.thickness, sol.offset = solid_m / scale, 1
    o.modifiers.move(len(o.modifiers) - 1, 0)          # solidify in rest shape, then the armature bends it
    for f in o.data.polygons:
        f.use_smooth = True
    print("PIECE", name, len(o.data.polygons))
    return o


BIB_X, S0, S1 = 0.085, 0.05, 0.075
X = lambda x: ((x, 0, 0), (1, 0, 0))
Z = lambda z: ((0, 0, z), (0, 0, 1))
Y = lambda y: ((0, y, 0), (0, 1, 0))
m_tee, m_denim = material("tee", TEE), material("denim", DENIM, 0.9, 0.25, 600)
m_cuff, m_pocket = material("cuff", CUFF, 0.9, 0.25, 600), material("pocket", POCKET, 0.9, 0.25, 600)

# tee: crew neck, short sleeves, tucked below the overall waist
piece("host_tee", lambda c: c.z < neckline_z and c.z > waist_z - 0.06 and abs(c.x) < sleeve_x, 0.004, m_tee,
      planes=[Z(neckline_z), Z(waist_z - 0.06), X(sleeve_x), X(-sleeve_x)])
# overall trousers: belt to ankle, straight cut hem + a rolled lighter cuff
crotch_z = bh("CC_Base_L_Thigh").z - 0.07
piece("host_trousers", lambda c: hem_z < c.z < belt_z, 0.016, m_denim, 0.004, planes=[Z(hem_z), Z(belt_z)],
      straight=0.088)                                                     # straight roomy overall legs
piece("host_cuffs", lambda c: hem_z < c.z < hem_z + 0.045, 0.02, m_cuff, 0.004, planes=[Z(hem_z), Z(hem_z + 0.045)], straight=0.098)
# waistband all round
piece("host_band", lambda c: belt_z - 0.035 < c.z < belt_z + 0.005 and abs(c.x) < sh_x, 0.026, m_denim, 0.004,
      planes=[Z(belt_z - 0.035), Z(belt_z + 0.005)])
# bib on the front, straps over the shoulders down the back
piece("host_bib", lambda c: (belt_z - 0.02 < c.z < chest_z and c.y < cy and abs(c.x) < BIB_X) or
      (S0 < abs(c.x) < S1 and (c.z >= chest_z - 0.01 or (c.y > cy and c.z > belt_z - 0.02))), 0.012, m_denim, drape=True,
      planes=[X(BIB_X), X(-BIB_X), X(S0), X(-S0), X(S1), X(-S1), Z(belt_z - 0.02), Z(chest_z), Y(cy)])
pz0, pz1 = chest_z - 0.12, chest_z - 0.03
piece("host_pocket", lambda c: pz0 < c.z < pz1 and c.y < cy and abs(c.x) < 0.055, 0.0155, m_pocket, 0.002, drape=True,
      planes=[X(0.055), X(-0.055), Z(pz0), Z(pz1), Y(cy)])
# buttons where the straps meet the bib
silver = material("buttons", "#c9ced6", 0.3, 0.0)
silver.node_tree.nodes["Principled BSDF"].inputs["Metallic"].default_value = 1.0
dg0 = bpy.context.evaluated_depsgraph_get()
bib = bpy.data.objects["host_bib"]
bt_tree, binv = BVHTree.FromObject(bib, dg0), bib.matrix_world.inverted()
for i, x in enumerate((0.0625, -0.0625)):
    hit = bt_tree.ray_cast(binv @ Vector((x, cy - 0.5, chest_z - 0.015)), (binv.to_3x3() @ Vector((0, 1, 0))).normalized())
    if hit[0] is None:
        continue
    bpy.ops.mesh.primitive_cylinder_add(vertices=20, radius=0.007, depth=0.004, location=bib.matrix_world @ hit[0] - Vector((0, 0.002, 0)),
                                        rotation=(math.radians(90), 0, 0))
    b = bpy.context.object
    b.name = f"host_button_{i}"
    b.data.materials.append(silver)
    keep_mw = b.matrix_world.copy()
    b.parent, b.parent_type, b.parent_bone = rig, "BONE", "CC_Base_Spine02"
    b.matrix_world = keep_mw

# sneakers: her boots in clean white canvas
for o in bpy.data.objects:
    if o.type == "MESH" and o.name.startswith("Boot"):
        for m in o.data.materials:
            p = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
            for k in ("Base Color", "Metallic", "Roughness"):
                for l in list(p.inputs[k].links):
                    m.node_tree.links.remove(l)
            p.inputs["Base Color"].default_value = lin("#f3f2ee")
            p.inputs["Metallic"].default_value, p.inputs["Roughness"].default_value = 0.0, 0.7

# hide the body skin under the clothes so it cannot poke through when she moves
dg = bpy.context.evaluated_depsgraph_get()
trees = [(BVHTree.FromObject(bpy.data.objects[n], dg), bpy.data.objects[n].matrix_world) for n in ("host_tee", "host_trousers", "host_bib", "host_band")]
hide = []
for v in body.data.vertices:
    if any(g.group in skip_groups and g.weight > 0.3 for g in v.groups):
        continue
    wp = mw @ v.co
    for tree, gmw in trees:
        hit = tree.find_nearest(gmw.inverted() @ wp)
        if hit[0] is not None and (gmw @ hit[0] - wp).length < 0.02:
            hide.append(v.index)
            break
vg = body.vertex_groups.new(name="covered")
vg.add(hide, 1.0, "REPLACE")
mk = body.modifiers.new("hide_covered", "MASK")
mk.vertex_group, mk.invert_vertex_group = "covered", True
print("HIDDEN_SKIN_VERTS", len(hide))


def aim(pb, target_world, d_world):
    """Turn the bone so its child joint (not its tail: FBX tails point anywhere) lies along d_world."""
    head = rig.matrix_world @ pb.head
    cur = (target_world() - head).normalized()
    r_world = cur.rotation_difference(Vector(d_world).normalized())
    q = rig.matrix_world.to_quaternion()
    r = q.inverted() @ r_world @ q
    m = pb.matrix.copy()
    loc = m.to_translation()
    m.translation = (0, 0, 0)
    new = r.to_matrix().to_4x4() @ m
    new.translation = loc
    pb.matrix = new
    bpy.context.view_layer.update()


pbs = rig.pose.bones
for side, sgn in (("L", 1), ("R", -1)):
    ua = next((pbs[n] for n in (f"CC_Base_{side}_Upperarm", f"{side}_Upperarm") if n in pbs), None)
    fa = next((pbs[n] for n in (f"CC_Base_{side}_Forearm", f"{side}_Forearm") if n in pbs), None)
    hand = pbs[f"CC_Base_{side}_Hand"]
    if ua and fa:
        aim(ua, lambda: rig.matrix_world @ fa.head, (sgn * 0.30, 0.03, -0.95))
        aim(fa, lambda: rig.matrix_world @ hand.head, (sgn * 0.16, -0.22, -0.96))
    print("ARMS", side, bool(ua), bool(fa))

# --- brighter, fresher skin: her textures read dim/brown on camera ---
SKIN_GRADE = dict(val=1.13, sat=0.92)      # natural bright (1.28 read pale/flat on camera)
for m in bpy.data.materials:
    if m.name.startswith(("Std_Skin", "Std_Nails")) and m.use_nodes and not m.get("graded"):
        nt = m.node_tree
        p = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
        lk = p.inputs["Base Color"].links
        if lk:
            src = lk[0].from_socket
            nt.links.remove(lk[0])
            hsv = nt.nodes.new("ShaderNodeHueSaturation")
            hsv.inputs["Value"].default_value, hsv.inputs["Saturation"].default_value = SKIN_GRADE["val"], SKIN_GRADE["sat"]
            nt.links.new(src, hsv.inputs["Color"])
            nt.links.new(hsv.outputs["Color"], p.inputs["Base Color"])
        m["graded"] = True

# --- sheet ---
dg = bpy.context.evaluated_depsgraph_get()
e = body.evaluated_get(dg)
me = e.to_mesh()
P = [body.matrix_world @ v.co for v in me.vertices]
e.to_mesh_clear()
zmin, zmax = min(p.z for p in P), max(p.z for p in P)
cx, cy, H = sum(p.x for p in P) / len(P), sum(p.y for p in P) / len(P), zmax - zmin
print("HEIGHT", round(H, 3))
sc.render.engine = "BLENDER_EEVEE"
sc.view_settings.view_transform = "Standard"
w = bpy.data.worlds.new("w")
sc.world = w
w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = (0.86, 0.82, 0.76, 1)
w.node_tree.nodes["Background"].inputs[1].default_value = 0.8
for n, rot, en in (("key", (55, 0, -35), 3.0), ("fill", (65, 0, 40), 1.2), ("rim", (60, 0, 170), 2.0)):
    ld = bpy.data.lights.new(n, "SUN")
    ld.energy = en
    lo = bpy.data.objects.new(n, ld)
    sc.collection.objects.link(lo)
    lo.rotation_euler = [math.radians(a) for a in rot]
cd = bpy.data.cameras.new("c")
cam = bpy.data.objects.new("c", cd)
sc.collection.objects.link(cam)
sc.camera = cam


def shot(name, center, fh, res, yaw=0, lens=55):
    cd.lens, cd.sensor_fit, cd.sensor_height = lens, "VERTICAL", 24
    d, a = fh * lens / 24, math.radians(yaw)
    cam.location = center + Vector((math.sin(a) * d, -math.cos(a) * d, 0))
    cam.rotation_euler = (math.radians(90), 0, a)
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.filepath = str(OUT / f"{name}.png")
    bpy.ops.render.render(write_still=True)


mid = Vector((cx, cy, zmin + H / 2))
shot("front", mid, H * 1.1, (640, 1000))
shot("threeq", mid, H * 1.1, (640, 1000), yaw=-35)
shot("side", mid, H * 1.1, (640, 1000), yaw=-90)
face = Vector((cx, cy, zmax - H * 0.075))
shot("face", face, H * 0.17, (800, 800), yaw=-12)
bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "host.blend"))
