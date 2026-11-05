"""Test export: blender -b build/host_stage3c.blend --python host/export_glb.py. Writes build/host_test.glb (no animations yet)."""
import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stage3_common import BUILD

out = os.path.join(BUILD, "host_test.glb")
bpy.ops.export_scene.gltf(filepath=out, export_format="GLB", use_selection=False, export_apply=False, export_skins=True, export_morph=True,
                          export_morph_normal=True, export_try_sparse_sk=True, export_animations=False, export_image_format="AUTO", export_yup=True, export_def_bones=False)
print("GLB", out, os.path.getsize(out) // 1024, "KB")
