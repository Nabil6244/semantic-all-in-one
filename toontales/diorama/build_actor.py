"""Build Channel 3's realistic builder with MPFB (CC0 MakeHuman assets) and save it as a .blend the diorama
engine appends at render time. Blender + MPFB are needed only to author this once.

    blender -b --factory-startup --addons bl_ext.user_default.mpfb --python toontales/diorama/build_actor.py -- [--preview]

Output: assets/diorama/cast/builder.blend with one collection "builder" (rig "builder_rig" = MPFB game_engine
rig, body + clothes skinned to it, a yellow hard hat on the head bone, hidden unless the shot asks for it).
"""
import importlib
import math
import os
import sys

import bpy

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(ROOT, "assets", "diorama", "cast")
os.makedirs(OUT, exist_ok=True)
ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
DATA = os.path.expanduser("~/Library/Application Support/Blender/5.2/extensions/.user/user_default/mpfb/data")


def svc(name):
    return importlib.import_module(f"bl_ext.user_default.mpfb.services.{name}")


# A fit working man in his thirties (MakeHuman macro sliders 0..1)
MACROS = {"gender": 1.0, "age": 0.55, "muscle": 0.6, "weight": 0.52, "proportions": 0.65, "height": 0.55,
          "race": {"asian": 0.15, "caucasian": 0.65, "african": 0.2}}
PARTS = [("Eyes", "eyes/high-poly/high-poly.mhclo"), ("Eyebrows", "eyebrows/eyebrow001/eyebrow001.mhclo"),
         ("Eyelashes", "eyelashes/eyelashes01/eyelashes01.mhclo"), ("Teeth", "teeth/teeth_base/teeth_base.mhclo"),
         ("Hair", "hair/short02/short02.mhclo"),
         ("Clothes", "clothes/male_casualsuit05/male_casualsuit05.mhclo"), ("Clothes", "clothes/shoes02/shoes02.mhclo")]
SKIN = "skins/young_caucasian_male/young_caucasian_male.mhmat"


def _first(path_glob_dir, ext):
    d = os.path.join(DATA, path_glob_dir)
    for f in sorted(os.listdir(d)):
        if f.endswith(ext):
            return os.path.join(d, f)
    return None


def hard_hat(rig):
    """Yellow safety helmet: half sphere shell + brim, parented to the head bone."""
    head = next((b for b in rig.data.bones if b.name.lower() == "head"), None)
    hz = (rig.matrix_world @ head.tail_local).z if head else 1.75
    hy = (rig.matrix_world @ head.tail_local).y if head else 0.0
    cz = hz - 0.103  # head bone tail is the top of the skull: the shell's rim sits around the brow
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.128, segments=40, ring_count=20, location=(0, hy - 0.012, cz))
    shell = bpy.context.active_object
    shell.scale = (1.0, 1.14, 0.9)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="DESELECT")
    bpy.ops.object.mode_set(mode="OBJECT")
    for v in shell.data.vertices:  # keep the top half
        v.select = v.co.z < -0.005
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.delete(type="VERT")
    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.mesh.primitive_cylinder_add(radius=0.142, depth=0.01, vertices=40, location=(0, hy - 0.03, cz + 0.002))
    brim = bpy.context.active_object
    brim.scale = (1.0, 1.18, 1.0)
    bpy.ops.mesh.primitive_cylinder_add(radius=0.011, depth=0.24, vertices=12, location=(0, hy - 0.012, cz + 0.108),
                                        rotation=(math.radians(90), 0, 0))
    ridge = bpy.context.active_object
    ridge.scale = (1.0, 1.0, 0.55)
    m = bpy.data.materials.new("hardhat_yellow")
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (0.95, 0.72, 0.05, 1)
    b.inputs["Roughness"].default_value = 0.35
    for o in (shell, brim, ridge):
        o.data.materials.append(m)
    bpy.ops.object.select_all(action="DESELECT")
    for o in (shell, brim, ridge):
        o.select_set(True)
    bpy.context.view_layer.objects.active = shell
    bpy.ops.object.join()
    hat = bpy.context.active_object
    hat.name = "builder_hardhat"
    bpy.ops.object.shade_smooth()
    if head:
        mw = hat.matrix_world.copy()
        hat.parent = rig
        hat.parent_type = "BONE"
        hat.parent_bone = head.name
        hat.matrix_world = mw
    return hat


def build():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    HS = svc("humanservice").HumanService
    body = HS.create_human(macro_detail_dict=MACROS)
    body.name = "builder_body"
    rig = HS.add_builtin_rig(body, "game_engine")
    rig.name = "builder_rig"
    HS.set_character_skin(os.path.join(DATA, SKIN), body, skin_type="MAKESKIN")
    for kind, rel in PARTS:
        o = HS.add_mhclo_asset(os.path.join(DATA, rel), body, asset_type=kind, subdiv_levels=0, material_type="MAKESKIN")
        print("PART", kind, o.name if o else None, flush=True)
    hat = hard_hat(rig)
    col = bpy.data.collections.new("builder")
    bpy.context.scene.collection.children.link(col)
    for o in list(bpy.context.scene.objects):
        for c in list(o.users_collection):
            c.objects.unlink(o)
        col.objects.link(o)
    print("BONES", [b.name for b in rig.data.bones], flush=True)
    print("HEIGHT", round(max((body.matrix_world @ v.co).z for v in body.data.vertices), 3), flush=True)
    out = os.path.join(OUT, "builder.blend")
    bpy.ops.wm.save_as_mainfile(filepath=out)
    print("SAVED", out, flush=True)
    return rig, hat


if __name__ == "__main__":
    build()
