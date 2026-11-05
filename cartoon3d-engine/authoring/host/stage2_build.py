"""Stage 2: optimise hair, make materials glTF-safe, export a bust test GLB.
Run: blender -b build/revisions/c6_gate1/cand_c6.blend --python host/stage2_build.py -- s1
Only writes to build/stage2/."""
import math
import os
import sys

import bpy
import numpy as np
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stage3_common import BUILD, lin, material, shot

TAG = sys.argv[sys.argv.index("--") + 1]
OUT = os.path.join(BUILD, "stage2", TAG); os.makedirs(OUT, exist_ok=True)
HAIR_RATIO = 0.03; RES = 2048
s = bpy.context.scene
hair = bpy.data.objects["concept_hair"]

# ---- low hair
low = hair.copy(); low.data = hair.data.copy(); low.name = "host_hair_low"; s.collection.objects.link(low)
for o in bpy.context.selected_objects:
    o.select_set(False)
bpy.context.view_layer.objects.active = low; low.select_set(True)
m = low.modifiers.new("dec", "DECIMATE"); m.ratio = HAIR_RATIO; m.use_collapse_triangulate = True
bpy.ops.object.modifier_apply(modifier=m.name)
me = low.data; print("REPORT hair low tris", len(me.polygons))
for l in list(me.uv_layers):
    me.uv_layers.remove(l)
bpy.ops.object.mode_set(mode="EDIT"); bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.uv.smart_project(angle_limit=math.radians(60), island_margin=0.006)
bpy.ops.object.mode_set(mode="OBJECT")
me.polygons.foreach_set("use_smooth", np.ones(len(me.polygons), bool))
col = bpy.data.images.new("hair_low_col", RES, RES); nrm = bpy.data.images.new("hair_low_nrm", RES, RES); nrm.colorspace_settings.name = "Non-Color"
hm = bpy.data.materials.new("hair_low"); hm.use_nodes = True; nt = hm.node_tree
bs = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"); bs.inputs["Roughness"].default_value = 0.42
tc = nt.nodes.new("ShaderNodeTexImage"); tc.image = col
tn = nt.nodes.new("ShaderNodeTexImage"); tn.image = nrm
me.materials.clear(); me.materials.append(hm)
s.render.engine = "CYCLES"; s.cycles.samples = 1; s.cycles.device = "CPU"
for o in bpy.context.selected_objects:
    o.select_set(False)
hair.hide_render = False; hair.select_set(True); low.select_set(True); bpy.context.view_layer.objects.active = low
b = s.render.bake; b.use_selected_to_active = True; b.cage_extrusion = 0.009; b.max_ray_distance = 0.02; b.margin = 10
b.use_pass_direct = False; b.use_pass_indirect = False; b.use_pass_color = True
nt.nodes.active = tc; bpy.ops.object.bake(type="DIFFUSE"); print("REPORT baked hair colour")
nt.nodes.active = tn; bpy.ops.object.bake(type="NORMAL", normal_space="TANGENT"); print("REPORT baked hair normal")
for img, n in ((col, "hair_col.png"), (nrm, "hair_nrm.png")):
    img.filepath_raw = os.path.join(OUT, n); img.file_format = "PNG"; img.save()
nt.links.new(tc.outputs[0], bs.inputs["Base Color"])
nm = nt.nodes.new("ShaderNodeNormalMap"); nm.inputs[0].default_value = 1.0
nt.links.new(tn.outputs[0], nm.inputs[1]); nt.links.new(nm.outputs[0], bs.inputs["Normal"])
hair.hide_render = True

# ---- skin: no subsurface (glTF has none), add a roughness map
head = bpy.data.objects["cand_head"]; sm = head.data.materials[0]; nt = sm.node_tree
bs = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"); bs.inputs["Subsurface Weight"].default_value = 0
img = next(n.image for n in nt.nodes if n.type == "TEX_IMAGE")
W, H = img.size; px = np.zeros(W * H * 4, np.float32); img.pixels.foreach_get(px); px = px.reshape(H, W, 4)
lip = np.clip(((px[..., 0] - px[..., 1]) - 0.28) / 0.12, 0, 1)
rng = np.random.default_rng(5); noise = rng.standard_normal((H // 8, W // 8)); noise = np.kron(noise, np.ones((8, 8)))[:H, :W]
rough = np.clip(0.54 - 0.24 * lip + 0.012 * noise, 0, 1)
ri = bpy.data.images.new("skin_rough", W, H, alpha=False); ri.colorspace_settings.name = "Non-Color"
ri.pixels.foreach_set(np.dstack([rough * 0, rough, rough * 0, np.ones_like(rough)]).astype(np.float32).ravel())
ri.filepath_raw = os.path.join(OUT, "skin_rough.png"); ri.file_format = "PNG"; ri.save()
# glTF has no subsurface: a low self-glow from the skin texture keeps shadows on the face warm and soft
bt = next(n for n in nt.nodes if n.type == "TEX_IMAGE")
nt.links.new(bt.outputs[0], bs.inputs["Emission Color"]); bs.inputs["Emission Strength"].default_value = 0.14
rn = nt.nodes.new("ShaderNodeTexImage"); rn.image = ri
sp = nt.nodes.new("ShaderNodeSeparateColor"); nt.links.new(rn.outputs[0], sp.inputs[0]); nt.links.new(sp.outputs[1], bs.inputs["Roughness"])

bpy.ops.wm.save_as_mainfile(filepath=os.path.join(BUILD, "stage2", f"stage2_{TAG}.blend"), copy=True)

# ---- export
keep = ["cand_head", "cand_teeth_up", "cand_teeth_low", "cand_tongue", "cand_mouth", "concept_eyes", "concept_brows", "concept_band", "concept_tie", "host_hair_low",
        "host_tee", "host_overalls", "host_pocket", "host_strap_L", "host_strap_R", "host_buttons", "host_stitch"]
for o in bpy.context.selected_objects:
    o.select_set(False)
for n in keep:
    bpy.data.objects[n].select_set(True)
out = os.path.join(OUT, "bust.glb")
bpy.ops.export_scene.gltf(filepath=out, export_format="GLB", use_selection=True, export_apply=False, export_skins=False, export_morph=True, export_morph_normal=True,
                          export_try_sparse_sk=True, export_animations=False, export_image_format="AUTO", export_yup=True)
print("REPORT glb KB", os.path.getsize(out) // 1024)
tri = 0
for n in keep:
    o = bpy.data.objects[n]; t = sum(len(p.vertices) - 2 for p in o.data.polygons); tri += t
print("REPORT export tris", tri, {n: sum(len(p.vertices) - 2 for p in bpy.data.objects[n].data.polygons) for n in keep[:10]})

# ---- Blender view of exactly what was exported
s.render.engine = "BLENDER_EEVEE"; s.render.film_transparent = True
s.view_settings.view_transform = "Standard"; s.view_settings.look = "None"; s.view_settings.exposure = 0
for kx, vx in (("use_raytracing", True), ("taa_render_samples", 32)):
    if hasattr(s.eevee, kx):
        setattr(s.eevee, kx, vx)
w = bpy.data.worlds.get("portrait") or bpy.data.worlds.new("portrait"); s.world = w; w.use_nodes = True
b0 = w.node_tree.nodes["Background"]; b0.inputs[0].default_value = lin("#e9e4de"); b0.inputs[1].default_value = 0.44
if "p_key" not in bpy.data.objects:
    TG0 = Vector((0, -0.05, 1.475))
    for nme, en, off, size, colr in (("p_key", 24, (-0.85, -1.15, 0.65), 1.4, (1, .95, .89)), ("p_fill", 8, (1.1, -1.1, 0.05), 1.8, (.94, .96, 1)),
                                     ("p_hair", 16, (0.65, 0.95, 0.75), 0.8, (1, .97, .93)), ("p_bounce", 3, (0, -0.8, -0.7), 1.2, (1, .86, .76))):
        Lg = bpy.data.lights.new(nme, "AREA"); Lg.energy = en; Lg.size = size; Lg.color = colr
        o = bpy.data.objects.new(nme, Lg); s.collection.objects.link(o); o.location = TG0 + Vector(off)
        o.rotation_euler = (TG0 - o.location).to_track_quat("-Z", "Y").to_euler()
KO = [bpy.data.objects[n] for n in ("cand_head", "cand_teeth_up", "cand_teeth_low", "cand_tongue", "cand_mouth")]


def setk(**v):
    for o in KO:
        for k in o.data.shape_keys.key_blocks[1:]:
            k.value = v.get(k.name, 0)


TG = (0, -0.05, 1.475)
for name, az, kv in (("front_neutral", 0, {}), ("q_neutral", 35, {}), ("side_neutral", 90, {}), ("front_smile", 0, {"smile": 1}), ("q_smile", 35, {"smile": 1})):
    setk(**kv); a = dict(target=TG, dist=1.58, lens=85, res=(800, 950))
    if name.startswith("side"):
        a["target"] = (0.1, 0.035, 1.43)
    shot(os.path.join(OUT, name + ".png"), azimuth=az, **a)
print("STAGE2 DONE")
