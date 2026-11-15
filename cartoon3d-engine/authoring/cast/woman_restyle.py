"""Adult lead (CGTrader 'game rigged girl', Character Creator body): fantasy outfit off, kids-show outfit on (tee + denim
overalls cut from her own body mesh, so they keep its skin weights and move with the rig), resting smile, arms down; sheet.
Run: blender -b --disable-autoexec --python cast/woman_restyle.py -- <goni.fbx> <out dir>
"""
import math
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Quaternion, Vector

fbx, out = sys.argv[sys.argv.index("--") + 1:][:2]
OUT = Path(out)
OUT.mkdir(parents=True, exist_ok=True)

DENIM = "#2c4a72"         # one mid-wash denim for jeans, bib, band and pocket, so the overalls read as one garment
OUTFIT = {"Tunic": "#ff7a5c", "Rocker_Jeans": DENIM, "Boots": "#f4f3ef"}   # coral tee, denim legs, boots -> white sneakers; folds kept from normal maps
SMILE = {"Mouth_Smile": 1.0, "Mouth_Smile_L": 0.8, "Mouth_Smile_R": 0.8, "Mouth_Widen": 0.3, "Cheek_Raise_L": 0.3, "Cheek_Raise_R": 0.3, "Cheek_Suck": 0.2,
         "Eye_Squint_L": 0.4, "Eye_Squint_R": 0.4, "Mouth_Lips_Part": 0.6, "Mouth_Top_Lip_Up": 0.3, "Mouth_Bottom_Lip_Down": 0.25,
         "Brow_Raise_Inner_L": 0.3, "Brow_Raise_Inner_R": 0.3, "Brow_Raise_Outer_L": 0.15, "Brow_Raise_Outer_R": 0.15}
FACE_TEX = Path(__file__).resolve().parent.parent / "build" / "cast" / "tex" / "head_friendly.png"   # cast/soften_face.py output

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=fbx)
sc = bpy.context.scene
rig = next(o for o in bpy.data.objects if o.type == "ARMATURE")
body = bpy.data.objects["CC_Base_Body"]
for o in bpy.data.objects:
    if o.animation_data:
        o.animation_data_clear()
    if o.type == "MESH" and o.data.shape_keys and o.data.shape_keys.animation_data:
        o.data.shape_keys.animation_data_clear()
for n in ("CC_Base_EyeOcclusion", "CC_Base_TearLine"):      # see-through shells that render as pale bands in Eevee/Three.js
    if n in bpy.data.objects:
        bpy.data.objects[n].hide_render = True
for n in ("Tasset",):
    bpy.data.objects.remove(bpy.data.objects[n], do_unlink=True)


def lin(h):
    h = h.lstrip("#")
    return tuple((int(h[i:i + 2], 16) / 255) ** 2.2 for i in (0, 2, 4)) + (1.0,)


def fabric(name, hexcol, rough=0.85, weave=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    p = nt.nodes["Principled BSDF"]
    p.inputs["Roughness"].default_value = rough
    if weave:
        noise = nt.nodes.new("ShaderNodeTexNoise")
        noise.inputs["Scale"].default_value = 900
        ramp = nt.nodes.new("ShaderNodeMixRGB")
        ramp.blend_type = "MULTIPLY"
        ramp.inputs["Fac"].default_value = weave
        ramp.inputs["Color1"].default_value = lin(hexcol)
        nt.links.new(noise.outputs["Color"], ramp.inputs["Color2"])
        nt.links.new(ramp.outputs["Color"], p.inputs["Base Color"])
    else:
        p.inputs["Base Color"].default_value = lin(hexcol)
    return m


# --- recolour her own clothes: flat colour + a soft fabric noise, the original normal map keeps the folds ---
for name, hexcol in OUTFIT.items():
    o = bpy.data.objects[name]
    for m in o.data.materials:
        nt = m.node_tree
        p = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
        for l in list(p.inputs["Base Color"].links):
            nt.links.remove(l)
        noise = nt.nodes.new("ShaderNodeTexNoise")
        noise.inputs["Scale"].default_value = 400
        mix = nt.nodes.new("ShaderNodeMixRGB")
        mix.blend_type = "MULTIPLY"
        mix.inputs["Fac"].default_value = 0.25 if hexcol == DENIM else 0.12
        mix.inputs["Color1"].default_value = lin(hexcol)
        nt.links.new(noise.outputs["Color"], mix.inputs["Color2"])
        nt.links.new(mix.outputs["Color"], p.inputs["Base Color"])
        p.inputs["Roughness"].default_value = 0.9 if hexcol == DENIM else 0.85
        for l in list(p.inputs["Roughness"].links):
            nt.links.remove(l)
        for l in list(p.inputs["Alpha"].links):
            nt.links.remove(l)
        p.inputs["Alpha"].default_value = 1.0
        if hasattr(m, "blend_method"):
            m.blend_method = "OPAQUE"
        for k in ("Metallic",):
            for l in list(p.inputs[k].links):
                nt.links.remove(l)
            p.inputs[k].default_value = 0.0
mw = body.matrix_world
cy = sum((mw @ v.co).y for v in body.data.vertices) / len(body.data.vertices)

# --- overalls: tee cut short + tucked; bib, straps, pocket cut from the top's own surface (finely subdivided), buttons ---
import bmesh


def bh(name):
    return rig.matrix_world @ rig.data.bones[name].head_local


waist_z, spine2_z, neck_z = bh("CC_Base_Waist").z, bh("CC_Base_Spine02").z, bh("CC_Base_NeckTwist01").z
sh_x, el_x = abs(bh("CC_Base_L_Upperarm").x), abs(bh("CC_Base_L_Forearm").x)
chest_z = spine2_z + 0.55 * (neck_z - spine2_z)
sleeve_x = sh_x + 0.4 * (el_x - sh_x)
print("LANDMARKS", round(waist_z, 3), round(chest_z, 3), round(neck_z, 3), round(sleeve_x, 3))
jeans = bpy.data.objects["Rocker_Jeans"]
jeans_top = max((jeans.matrix_world @ v.co).z for v in jeans.data.vertices)
jw = [jeans.matrix_world @ v.co for v in jeans.data.vertices]
jcy = sum(p.y for p in jw) / len(jw)
jeans_front_top = max(p.z for p in jw if p.y < jcy and abs(p.x) < 0.06)
print("JEANS_TOP", round(jeans_top, 3), "front", round(jeans_front_top, 3))
tunic = bpy.data.objects["Tunic"]
tw = tunic.matrix_world
tcy = sum((tw @ v.co).y for v in tunic.data.vertices) / len(tunic.data.vertices)


def cut(obj, keep, subdiv=0, planes=()):
    """planes: (world point, world normal) lines to slice along first, so the kept region has straight edges."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    if subdiv:
        bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=subdiv, use_grid_fill=True)
    m = obj.matrix_world
    inv = m.inverted()
    for co, no in planes:
        geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
        bmesh.ops.bisect_plane(bm, geom=geom, plane_co=inv @ Vector(co), plane_no=(inv.to_3x3().transposed().inverted() @ Vector(no)).normalized(), dist=1e-6)
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if not keep(m @ f.calc_center_median())], context="FACES")
    bm.to_mesh(obj.data)
    bm.free()


cut(tunic, lambda c: abs(c.x) < sleeve_x and c.z > jeans_top - 0.03, subdiv=1,
    planes=[((sleeve_x, 0, 0), (1, 0, 0)), ((-sleeve_x, 0, 0), (1, 0, 0)), ((0, 0, jeans_top - 0.03), (0, 0, 1))])      # short sleeves, tucked hem


def piece(name, keep, push_m, hexcol, solid_m=0.003, subdiv=2, planes=(), src=None):
    src = src or tunic
    o = src.copy()
    o.data = src.data.copy()
    o.name = name
    sc.collection.objects.link(o)
    o.shape_key_clear()
    cut(o, keep, subdiv, planes)
    scale = o.matrix_world.to_scale()[0]
    bm = bmesh.new()
    bm.from_mesh(o.data)
    bm.normal_update()
    for v in bm.verts:
        v.co += v.normal * (push_m / scale)
    bm.to_mesh(o.data)
    bm.free()
    m = bpy.data.materials.new(name + "_m")
    m.use_nodes = True
    nt = m.node_tree
    p = nt.nodes["Principled BSDF"]
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 500
    mix = nt.nodes.new("ShaderNodeMixRGB")
    mix.blend_type, mix.inputs["Fac"].default_value = "MULTIPLY", 0.25
    mix.inputs["Color1"].default_value = lin(hexcol)
    nt.links.new(noise.outputs["Color"], mix.inputs["Color2"])
    nt.links.new(mix.outputs["Color"], p.inputs["Base Color"])
    p.inputs["Roughness"].default_value = 0.9
    o.data.materials.clear()
    o.data.materials.append(m)
    sol = o.modifiers.new("solid", "SOLIDIFY")
    sol.thickness, sol.offset = solid_m / scale, 1
    for f in o.data.polygons:
        f.use_smooth = True
    return o


BIB_X, STRAP_X0, STRAP_X1 = 0.105, 0.062, 0.092
band_lo = jeans_top - 0.028                     # just above the tee's tucked hem cut
band_hi = max(jeans_top, jeans_front_top) + 0.02
bib_bot = band_lo                               # bib runs down into the waistband: no tee gap between bib and trousers


def in_bib(c):
    return bib_bot < c.z < chest_z and c.y < tcy and abs(c.x) < BIB_X


def in_strap(c):
    return STRAP_X0 < abs(c.x) < STRAP_X1 and ((c.z >= chest_z - 0.01) or (c.y > tcy and c.z > bib_bot))


BIB_PLANES = [((x, 0, 0), (1, 0, 0)) for x in (BIB_X, -BIB_X, STRAP_X0, -STRAP_X0, STRAP_X1, -STRAP_X1)] + \
             [((0, 0, z), (0, 0, 1)) for z in (bib_bot, chest_z)] + [((0, tcy, 0), (0, 1, 0))]
piece("lead_bib", lambda c: in_bib(c) or in_strap(c), 0.007, DENIM, planes=BIB_PLANES)
# waistband all round: one denim band over the bib foot and the jeans top, the seam that makes it one pair of overalls
# cut from the body surface (continuous there) and pushed past the tee and jeans; reaches down over the jeans' lower front rise
band_bot = jeans_front_top - 0.012
piece("lead_band", lambda c: band_bot < c.z < band_hi and abs(c.x) < 0.22,   # hip width: not the resting fingertips
      0.018, DENIM, 0.004, subdiv=1, src=body,
      planes=[((0, 0, band_bot), (0, 0, 1)), ((0, 0, band_hi), (0, 0, 1))])
pz0, pz1 = chest_z - 0.14, chest_z - 0.035
piece("lead_pocket", lambda c: pz0 < c.z < pz1 and c.y < tcy and abs(c.x) < 0.068, 0.011, "#263f62", 0.002,
      planes=[((0.068, 0, 0), (1, 0, 0)), ((-0.068, 0, 0), (1, 0, 0)), ((0, 0, pz0), (0, 0, 1)), ((0, 0, pz1), (0, 0, 1)), ((0, tcy, 0), (0, 1, 0))])
# buttons at the strap ends and the waist sides, riding the spine bone
silver = bpy.data.materials.new("lead_buttons")
silver.use_nodes = True
sp = silver.node_tree.nodes["Principled BSDF"]
sp.inputs["Base Color"].default_value = lin("#c9ced6")
sp.inputs["Metallic"].default_value, sp.inputs["Roughness"].default_value = 1.0, 0.3
from mathutils.bvhtree import BVHTree as _BVH
dg0 = bpy.context.evaluated_depsgraph_get()
bib = bpy.data.objects["lead_bib"]
btree = _BVH.FromObject(bib, dg0)
binv = bib.matrix_world.inverted()
for i, (x, z) in enumerate([(0.077, chest_z - 0.018), (-0.077, chest_z - 0.018), (0.095, band_hi + 0.012), (-0.095, band_hi + 0.012)]):
    hit = btree.ray_cast(binv @ Vector((x, tcy - 0.5, z)), (binv.to_3x3() @ Vector((0, 1, 0))).normalized())
    if hit[0] is None:
        continue
    loc = bib.matrix_world @ hit[0]
    bpy.ops.mesh.primitive_cylinder_add(vertices=20, radius=0.008, depth=0.004, location=loc - Vector((0, 0.003, 0)), rotation=(math.radians(90), 0, 0))
    bt = bpy.context.object
    bt.name = f"lead_button_{i}"
    bt.data.materials.append(silver)
    mwb = bt.matrix_world.copy()
    bt.parent, bt.parent_type, bt.parent_bone = rig, "BONE", ("CC_Base_Spine02" if z > waist_z + 0.05 else "CC_Base_Waist")
    bt.matrix_world = mwb

# --- hide body skin under the clothes so it cannot poke through ---
from mathutils.bvhtree import BVHTree
dg = bpy.context.evaluated_depsgraph_get()
keep_groups = {i for i, g in enumerate(body.vertex_groups) if any(k in g.name for k in ("Hand", "Thumb", "Index", "Mid", "Ring", "Pinky", "Foot", "Toe", "Head", "Jaw", "Neck"))}
trees = [(BVHTree.FromObject(bpy.data.objects[n], dg), bpy.data.objects[n].matrix_world.inverted(), bpy.data.objects[n].matrix_world) for n in ("Tunic", "Rocker_Jeans", "Boots", "lead_bib", "lead_band")]
hide = []
for v in body.data.vertices:
    if any(g.group in keep_groups and g.weight > 0.3 for g in v.groups):
        continue
    wp = mw @ v.co
    if abs(wp.x) > sleeve_x - 0.05 and wp.z > waist_z:
        continue
    for tree, inv, gmw in trees:
        hit = tree.find_nearest(inv @ wp)
        if hit[0] is not None and (gmw @ hit[0] - wp).length < 0.03:
            hide.append(v.index)
            break
covered = body.vertex_groups.new(name="covered")
covered.add(hide, 1.0, "REPLACE")
mk = body.modifiers.new("hide_covered", "MASK")
mk.vertex_group, mk.invert_vertex_group = "covered", True
print("HIDDEN_SKIN_VERTS", len(hide))

# --- slimmer cheekbones: soft inward pull of the cheekbone area (rest shape and every face key alike) ---
CHEEK = dict(pull=0.009, radius=0.048, drop=0.045, out=0.066, smile_keep=1.0, hi_pull=0.0, hi_radius=0.04, hi_drop=0.018, hi_out=0.07)
FACE_NORMAL = 0.75    # the head normal map bakes in bony cheek detail; softer reads friendlier     # metres: inward pull, falloff, below the eyes, from centre
eyes = [rig.matrix_world @ rig.data.bones[n].head_local for n in ("CC_Base_L_Eye", "CC_Base_R_Eye") if n in rig.data.bones]
if eyes:
    ez = sum(e.z for e in eyes) / len(eyes)
    ey = sum(e.y for e in eyes) / len(eyes)
    inv = mw.inverted()
    import math as _m
    deltas = {}
    for v in body.data.vertices:
        wp = mw @ v.co
        if wp.z < ez - 0.09 or wp.z > ez + 0.02:
            continue
        for sgn in (1, -1):
            c = Vector((sgn * CHEEK["out"], ey + 0.005, ez - CHEEK["drop"]))
            d = (wp - c).length
            if d < CHEEK["radius"] * 2.5:
                w = _m.exp(-(d / CHEEK["radius"]) ** 2)
                de = min((wp - e).length for e in eyes)                  # leave the lids alone: eyeballs/lashes do not move
                w *= min(1.0, max(0.0, (de - 0.028) / 0.022)) ** 2
                c2 = Vector((sgn * CHEEK["hi_out"], ey + 0.012, ez - CHEEK["hi_drop"]))          # the bony arch at eye level, by the ears
                w2 = _m.exp(-((wp - c2).length / CHEEK["hi_radius"]) ** 2) * min(1.0, max(0.0, (de - 0.028) / 0.022)) ** 2
                pull = CHEEK["pull"] * w + CHEEK["hi_pull"] * w2
                deltas[v.index] = deltas.get(v.index, Vector()) + (inv.to_3x3() @ Vector((-sgn * pull, 0.3 * CHEEK["pull"] * w, 0)))
    # the smile keys bunch the cheeks up and out: keep only part of their movement on the cheekbone, full movement at the mouth
    kbs = body.data.shape_keys.key_blocks
    basis = kbs["Basis"]
    calm = {}
    for i in deltas:
        wp = mw @ body.data.vertices[i].co
        w = max(_m.exp(-((wp - Vector((sgn * CHEEK["out"], ey + 0.005, ez - CHEEK["drop"]))).length / CHEEK["radius"]) ** 2) for sgn in (1, -1))
        calm[i] = w
    for kname in ("Mouth_Smile", "Mouth_Smile_L", "Mouth_Smile_R", "Cheek_Raise_L", "Cheek_Raise_R", "Mouth_Widen"):
        if kname in kbs:
            kd = kbs[kname].data
            for i, w in calm.items():
                kd[i].co = basis.data[i].co + (kd[i].co - basis.data[i].co) * (1 - (1 - CHEEK["smile_keep"]) * w)
    for kbk in kbs:
        for i, dv in deltas.items():
            kbk.data[i].co += dv
    print("CHEEK_VERTS", len(deltas), "eye_z", round(ez, 3))

# --- friendly face texture (no smoky eyes, soft rose lips) ---
if FACE_TEX.exists():
    hm = bpy.data.materials["Std_Skin_Head"]
    for n in hm.node_tree.nodes:
        if n.type == "TEX_IMAGE" and n.image and n.image.name.startswith("Std_Skin_Head_Diffuse"):
            n.image = bpy.data.images.load(str(FACE_TEX))
    print("FACE_TEX", FACE_TEX.name)
for n in bpy.data.materials["Std_Skin_Head"].node_tree.nodes:
    if n.type == "NORMAL_MAP":
        n.inputs["Strength"].default_value = FACE_NORMAL

# --- resting smile ---
kb = body.data.shape_keys.key_blocks
for k, v in SMILE.items():
    if k in kb:
        kb[k].value = v

# --- arms down (T-pose -> relaxed), aimed in world space ---
def aim(pb, d_world):
    head = rig.matrix_world @ pb.head
    cur = (rig.matrix_world @ pb.tail - head).normalized()
    r_world = cur.rotation_difference(Vector(d_world).normalized())
    obj_rot = rig.matrix_world.to_quaternion()
    r_arm = obj_rot.inverted() @ r_world @ obj_rot
    m = pb.matrix.copy()
    loc = m.to_translation()
    m.translation = (0, 0, 0)
    new = r_arm.to_matrix().to_4x4() @ m
    new.translation = loc
    pb.matrix = new
    bpy.context.view_layer.update()


for side, sgn in (("L", 1), ("R", -1)):
    aim(rig.pose.bones[f"CC_Base_{side}_Upperarm"], (sgn * 0.36, 0.02, -0.93))
    aim(rig.pose.bones[f"CC_Base_{side}_Forearm"], (sgn * 0.22, -0.28, -0.93))
for n in ("CC_Base_L_Hand", "CC_Base_R_Hand"):
    print("HAND", n, tuple(round(x, 3) for x in rig.matrix_world @ rig.pose.bones[n].head))
bpy.context.view_layer.update()

# --- sheet ---
sc.render.engine = "BLENDER_EEVEE"
sc.view_settings.view_transform = "Standard"
sc.render.film_transparent = False
w = bpy.data.worlds.new("w")
sc.world = w
w.use_nodes = True
bg = next(n for n in w.node_tree.nodes if n.type == "BACKGROUND")
bg.inputs["Color"].default_value = (0.86, 0.82, 0.76, 1)
bg.inputs["Strength"].default_value = 0.8
for name, rot, en in (("key", (55, 0, -35), 3.0), ("fill", (65, 0, 40), 1.2), ("rim", (60, 0, 170), 2.0)):
    ld = bpy.data.lights.new(name, "SUN")
    ld.energy, ld.angle = en, math.radians(12)
    lo = bpy.data.objects.new(name, ld)
    sc.collection.objects.link(lo)
    lo.rotation_euler = tuple(math.radians(a) for a in rot)
cd = bpy.data.cameras.new("cam")
cam = bpy.data.objects.new("cam", cd)
sc.collection.objects.link(cam)
sc.camera = cam

top = max((mw @ v.co).z for v in body.data.vertices)
bot = 0.0
H = top - bot
cx = sum((mw @ v.co).x for v in body.data.vertices) / len(body.data.vertices)


def shot(name, center, frame_h, res, yaw=0.0, lens=55):
    cd.lens, cd.sensor_fit, cd.sensor_height = lens, "VERTICAL", 24
    d = frame_h * lens / 24
    a = math.radians(yaw)
    cam.location = center + Vector((math.sin(a) * d, -math.cos(a) * d, 0))
    cam.rotation_euler = (math.radians(90), 0, a)
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.filepath = str(OUT / f"{name}.png")
    bpy.ops.render.render(write_still=True)


mid = Vector((cx, cy, H / 2))
shot("front", mid, H * 1.1, (640, 1000))
shot("threeq", mid, H * 1.1, (640, 1000), yaw=-35)
shot("side", mid, H * 1.1, (640, 1000), yaw=-90)
shot("back", mid, H * 1.1, (640, 1000), yaw=180)
face = Vector((cx, cy, top - H * 0.075))
shot("face", face, H * 0.16, (800, 800), yaw=-12)
shot("face_front", face, H * 0.16, (800, 800))
bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "lead.blend"))
print("DONE", OUT)
