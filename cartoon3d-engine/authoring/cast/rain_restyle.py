"""New host: Blender Studio 'Rain' (CC-BY, credit "Rain (c) Blender Studio, CC-BY"). Step 1: fair skin, look sheet.
Run: blender -b -y "<rain_v3.2.blend>" --python cast/rain_restyle.py -- <out dir>
(-y is safe here: the file's scripts are only the CloudRig UI and an Eevee settings snippet, reviewed 2026-11-14.)
"""
import math
import sys

import bpy
from mathutils import Vector

out = sys.argv[sys.argv.index("--") + 1]
sc = bpy.context.scene

# --- fair skin: her diffuse texture through a lighter, less saturated, slightly peach grade (body+head share MAT-rain.body) ---
SKIN = dict(sat=0.8, val=1.6, peach=(1.0, 0.84, 0.80, 1.0), peach_fac=0.15)   # fair but warm: lower sat greys her out
for mname in ("MAT-rain.body", "MAT-rain.hands"):
    nt = bpy.data.materials[mname].node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    link = bsdf.inputs["Base Color"].links[0]          # their own graded colour (texture + cheek/lip mix) -> grade it lighter
    src = link.from_socket
    nt.links.remove(link)
    hsv = nt.nodes.new("ShaderNodeHueSaturation")
    hsv.inputs["Saturation"].default_value, hsv.inputs["Value"].default_value = SKIN["sat"], SKIN["val"]
    mix = nt.nodes.new("ShaderNodeMixRGB")
    mix.blend_type, mix.inputs["Fac"].default_value = "MULTIPLY", SKIN["peach_fac"]
    mix.inputs["Color2"].default_value = SKIN["peach"]
    nt.links.new(src, hsv.inputs["Color"])
    nt.links.new(hsv.outputs["Color"], mix.inputs["Color1"])
    nt.links.new(mix.outputs["Color"], bsdf.inputs["Base Color"])
    print("SKIN", mname, flush=True)

# --- sheet ---
for o in list(sc.objects):
    if o.type in ("CAMERA", "LIGHT"):
        bpy.data.objects.remove(o)
dg = bpy.context.evaluated_depsgraph_get()


def pts(o):
    e = o.evaluated_get(dg)
    m = e.to_mesh()
    p = [o.matrix_world @ v.co for v in m.vertices]
    e.to_mesh_clear()
    return p


allp = pts(bpy.data.objects["GEO-rain-body"]) + pts(bpy.data.objects["GEO-rain-head"])
zmin, zmax = min(p.z for p in allp), max(p.z for p in allp)
cx, cy, H = sum(p.x for p in allp) / len(allp), sum(p.y for p in allp) / len(allp), zmax - zmin
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
    sc.render.filepath = f"{out}/{name}.png"
    bpy.ops.render.render(write_still=True)


hp = pts(bpy.data.objects["GEO-rain-head"])
hz0, hz1 = min(p.z for p in hp), max(p.z for p in hp)
shot("front", Vector((cx, cy, zmin + H / 2)), H * 1.1, (640, 1000))
shot("face", Vector((cx, cy, (hz0 + hz1) / 2)), (hz1 - hz0) * 1.5, (800, 800), yaw=-15)
bpy.ops.wm.save_as_mainfile(filepath=f"{out}/rain.blend")
