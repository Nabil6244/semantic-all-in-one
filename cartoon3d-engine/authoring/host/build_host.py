"""Build the preschool host in Blender with MPFB (offline authoring only; the app never needs Blender to render).

Run:  Blender -b -noaudio --python cartoon3d-engine/authoring/host/build_host.py -- --stage 1 [--preview]
Stage 1: body proportions, original face shaping, default rig (163 bones, 30 finger bones, face bones),
         Microsoft visemes + Meta visemes + ARKit face units as shape keys. Saves build/host_stage1.blend.
Later stages add skin/eyes/hair/clothes (need the MakeHuman CC0 system pack) and export the GLB.
All MakeHuman/MPFB assets used are CC0; MPFB code is GPL but outputs are ours.
"""
import importlib
import math
import os
import sys

import bpy
import mathutils

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(os.path.dirname(HERE), "build")
os.makedirs(BUILD, exist_ok=True)
ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(name, default=None):
    return ARGS[ARGS.index(name) + 1] if name in ARGS else default


def svc(name):
    return importlib.import_module(f"bl_ext.user_default.mpfb.services.{name}")


HumanService = svc("humanservice").HumanService
TargetService = svc("targetservice").TargetService
FaceService = svc("faceservice").FaceService

# Her own look: young adult woman, friendly soft proportions. Values are MakeHuman macro sliders (0..1).
MACROS = {"gender": 0.0, "age": 0.52, "muscle": 0.45, "weight": 0.48, "proportions": 0.7, "height": 0.42,
          "cupsize": 0.4, "firmness": 0.55, "race": {"asian": 0.2, "caucasian": 0.6, "african": 0.2}}

# Original face: slightly larger warm eyes, fuller round cheeks, soft small chin, wide smile line.
# Only targets that exist in this MPFB install are applied (checked below), so a missing one never breaks the build.
FACE = {
    "l-eye-scale-incr": 0.28, "r-eye-scale-incr": 0.28,
    "l-eye-corner2-up": 0.25, "r-eye-corner2-up": 0.25,
    "l-cheek-volume-incr": 0.35, "r-cheek-volume-incr": 0.35,
    "l-cheek-bones-incr": 0.15, "r-cheek-bones-incr": 0.15,
    "chin-width-decr": 0.2, "chin-prominent-decr": 0.15, "chin-height-decr": 0.1,
    "eyebrows-trans-up": 0.2, "eyebrows-angle-up": 0.15,
    "nose-scale-horiz-decr": 0.15, "nose-scale-vert-decr": 0.1, "nose-point-width-decr": 0.2,
    "mouth-scale-horiz-incr": 0.2, "mouth-lowerlip-volume-incr": 0.15, "mouth-upperlip-volume-incr": 0.1,
    "head-round": 0.2,
}


USER_DATA = os.path.expanduser("~/Library/Application Support/Blender/5.2/extensions/.user/user_default/mpfb/data")
BODYPARTS = [("Eyes", "eyes/high-poly/high-poly.mhclo"), ("Eyebrows", "eyebrows/eyebrow010/eyebrow010.mhclo"),
             ("Eyelashes", "eyelashes/eyelashes02/eyelashes02.mhclo"), ("Teeth", "teeth/teeth_base/teeth_base.mhclo"),
             ("Tongue", "tongue/tongue01/tongue01.mhclo"), ("Hair", "hair/ponytail01/ponytail01.mhclo")]
SKIN = "skins/young_caucasian_female/young_caucasian_female.mhmat"
EYE_TEX = "eyes/materials/brown_eye.png"
HAIR_TINT = (0.07, 0.045, 0.03)  # dark brown
SKIN_TINT = (0.97, 0.86, 0.78)  # a little warmer than the pale base texture


def tint_images(obj, rgb, mix=1.0):
    """Darken/recolour an asset's diffuse texture by multiplying it with a colour (glTF-safe: bakes into base colour)."""
    for slot in obj.material_slots:
        m = slot.material
        if not m or not m.use_nodes:
            continue
        nt = m.node_tree
        bsdf = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
        if not bsdf:
            continue
        link = next((l for l in nt.links if l.to_socket == bsdf.inputs["Base Color"]), None)
        mul = nt.nodes.new("ShaderNodeMix"); mul.data_type = "RGBA"; mul.blend_type = "MULTIPLY"
        mul.inputs[0].default_value = mix; mul.inputs[7].default_value = (*rgb, 1)
        if link:
            nt.links.new(link.from_socket, mul.inputs[6])
        else:
            mul.inputs[6].default_value = bsdf.inputs["Base Color"].default_value
        nt.links.new(mul.outputs[2], bsdf.inputs["Base Color"])


def swap_texture(obj, png):
    img = bpy.data.images.load(png, check_existing=True)
    for slot in obj.material_slots:
        if slot.material and slot.material.use_nodes:
            for n in slot.material.node_tree.nodes:
                if n.type == "TEX_IMAGE" and n.image and "eye" in n.image.name.lower():
                    n.image = img


def stage2():
    body, rig = stage1()
    HumanService.set_character_skin(os.path.join(USER_DATA, SKIN), body, skin_type="MAKESKIN")
    parts = {}
    for kind, rel in BODYPARTS:
        parts[kind] = HumanService.add_mhclo_asset(os.path.join(USER_DATA, rel), body, asset_type=kind, subdiv_levels=1, material_type="MAKESKIN")
        print("REPORT added", kind, parts[kind].name if parts[kind] else None)
    if parts.get("Eyes"):
        swap_texture(parts["Eyes"], os.path.join(USER_DATA, EYE_TEX))
    if parts.get("Hair"):
        tint_images(parts["Hair"], HAIR_TINT)
    tint_images(body, SKIN_TINT)
    out = os.path.join(BUILD, "host_stage2.blend")
    bpy.ops.wm.save_as_mainfile(filepath=out)
    print("SAVED", out)
    return body, rig


def clear_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def stage1():
    clear_scene()
    body = HumanService.create_human(macro_detail_dict=MACROS)
    body.name = "host_body"
    stack, missing = [], []
    for name, value in FACE.items():
        if TargetService.target_full_path(name):
            stack.append({"target": name, "value": value})
        else:
            missing.append(name)
    if stack:
        TargetService.bulk_load_targets(body, stack)
    print("face targets applied:", len(stack), "missing:", missing)
    rig = HumanService.add_builtin_rig(body, "default")
    rig.name = "host_rig"
    FaceService.load_targets(body, load_microsoft_visemes=True, load_meta_visemes=True, load_arkit_faceunits=True)
    keys = [k.name for k in body.data.shape_keys.key_blocks] if body.data.shape_keys else []
    bones = [b.name for b in rig.data.bones]
    fingers = [b for b in bones if any(k in b.lower() for k in ("finger", "thumb"))]
    print("REPORT bones=%d finger_bones=%d shape_keys=%d" % (len(bones), len(fingers), len(keys)))
    print("REPORT sample keys:", [k for k in keys if any(s in k.lower() for s in ("viseme", "blink", "smile", "jawopen", "sil", "aa"))][:20])
    out = os.path.join(BUILD, "host_stage1.blend")
    bpy.ops.wm.save_as_mainfile(filepath=out)
    print("SAVED", out)
    return body, rig


def preview(body, tag, clay_only=True):
    """Clay-render the face front and 3/4 so the face shape can be judged before skin/hair go on."""
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x, scene.render.resolution_y = 900, 1100
    scene.view_settings.view_transform = "AgX"; scene.view_settings.exposure = -0.35
    world = bpy.data.worlds.new("w"); scene.world = world; world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (0.55, 0.6, 0.66, 1); world.node_tree.nodes["Background"].inputs[1].default_value = 0.6
    clay = bpy.data.materials.new("clay"); clay.use_nodes = True
    bsdf = clay.node_tree.nodes["Principled BSDF"]; bsdf.inputs["Base Color"].default_value = (0.8, 0.66, 0.58, 1); bsdf.inputs["Roughness"].default_value = 0.6
    smile = float(arg("--smile", "0"))
    if smile and body.data.shape_keys:
        for k in ("mouthSmileLeft", "mouthSmileRight"):
            kb = body.data.shape_keys.key_blocks.get(k)
            if kb: kb.value = smile
    for o in scene.objects:
        if o.type == "MESH" and clay_only:
            o.data.materials.clear(); o.data.materials.append(clay)
    rig = bpy.data.objects.get("host_rig")
    hb = rig.data.bones.get("head") if rig else None
    head_z = (rig.matrix_world @ ((hb.head_local + hb.tail_local) / 2)).z if hb else 1.55
    for name, ang in (("front", 0), ("threeq", 35)):
        cam_data = bpy.data.cameras.new(name); cam_data.lens = 85
        cam = bpy.data.objects.new(name, cam_data); scene.collection.objects.link(cam)
        r = 0.95; a = math.radians(ang)
        cam.location = (r * math.sin(a), -r * math.cos(a), head_z)
        cam.rotation_euler = (math.radians(90), 0, a)
        scene.camera = cam
        if name == "front":
            for nm, en, loc, size in (("key", 45, (0.9, -1.1, head_z + 0.5), 1.5), ("fill", 18, (-1.1, -0.9, head_z + 0.1), 2.0), ("rim", 30, (-0.4, 1.0, head_z + 0.6), 0.8)):
                L = bpy.data.lights.new(nm, "AREA"); L.energy = en; L.size = size
                lo = bpy.data.objects.new(nm, L); scene.collection.objects.link(lo); lo.location = loc
                d = mathutils.Vector((0, 0, head_z)) - mathutils.Vector(loc); lo.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
        scene.render.filepath = os.path.join(BUILD, f"preview_{tag}_{name}.png")
        bpy.ops.render.render(write_still=True)
        print("PREVIEW", scene.render.filepath)


if __name__ == "__main__":
    stage = arg("--stage", "1")
    if stage == "1":
        b, r = stage1()
        if "--preview" in ARGS:
            preview(b, "s1")
    elif stage == "2":
        b, r = stage2()
        if "--preview" in ARGS:
            preview(b, "s2", clay_only=False)
