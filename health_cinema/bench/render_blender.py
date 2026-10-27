"""Blender backend: renders journey frames (frames.json from journey.py) of chest.blend to PNGs.
Run: Blender -b chest.blend --python render_blender.py -- frames.json OUT_DIR W H ENGINE SAMPLES [first last]"""
import json, math, sys, time
import bpy
from mathutils import Vector

a = sys.argv[sys.argv.index("--") + 1:]
spec_frames = json.load(open(a[0])); OUT = a[1]; W, H = int(a[2]), int(a[3]); ENGINE = a[4]; SAMPLES = int(a[5])
first = int(a[6]) if len(a) > 6 else 0; last = int(a[7]) if len(a) > 7 else len(spec_frames["frames"])
spec, frames = spec_frames["spec"], spec_frames["frames"]; anchors = spec_frames["anchors"]
sc = bpy.context.scene
sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = W, H, 100
sc.render.use_freestyle = False; sc.use_nodes = False; sc.render.use_compositing = False; sc.render.use_sequencer = False
for vl in sc.view_layers: vl.use_freestyle = False
sc.render.image_settings.file_format = "PNG"; sc.render.film_transparent = False
if ENGINE == "EEVEE":
    sc.render.engine = "BLENDER_EEVEE_NEXT"; sc.eevee.taa_render_samples = SAMPLES
else:
    sc.render.engine = "CYCLES"; sc.cycles.samples = SAMPLES; sc.cycles.use_denoising = True; sc.cycles.device = "CPU"
    sc.cycles.max_bounces = 6; sc.cycles.transparent_max_bounces = 16
sc.view_settings.view_transform = "AgX"; sc.view_settings.look = "AgX - Medium High Contrast"
w = bpy.data.worlds.new("hc_world"); sc.world = w; w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = (*spec["background"], 1); w.node_tree.nodes["Background"].inputs[1].default_value = 1.0

layers = {e.name: list(e.children) for e in bpy.data.objects if e.type == "EMPTY" and e.name.startswith("Layer_")}
mats = {}   # layer -> list of principled inputs (Alpha)
for ln, objs in layers.items():
    cache = {}
    for o in objs:
        for i, m in enumerate(o.data.materials):
            if (ln, m.name) not in cache:
                c = m.copy(); c.name = f"{m.name}__{ln}"; c.surface_render_method = "BLENDED"; cache[(ln, m.name)] = c
            o.data.materials[i] = cache[(ln, m.name)]
    mats[ln] = [m.node_tree.nodes["Principled BSDF"] for m in cache.values()]

# highlight ellipsoids
hl = {}
for h in spec.get("highlights", []):
    c = anchors[h["anchor"]]["center"]
    bpy.ops.mesh.primitive_uv_sphere_add(radius=1, segments=48, ring_count=24, location=[c[i] + h["offset"][i] for i in range(3)])
    o = bpy.context.object; o.scale = h["scale"]; o.name = "HL_" + h["id"]
    m = bpy.data.materials.new("HL"); m.use_nodes = True; m.surface_render_method = "BLENDED"
    nt = m.node_tree; nt.nodes.clear(); em = nt.nodes.new("ShaderNodeEmission"); tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mix = nt.nodes.new("ShaderNodeMixShader"); out = nt.nodes.new("ShaderNodeOutputMaterial")
    em.inputs[0].default_value = (*h["color"], 1)
    nt.links.new(em.outputs[0], mix.inputs[2]); nt.links.new(tr.outputs[0], mix.inputs[1]); nt.links.new(mix.outputs[0], out.inputs[0])
    o.data.materials.append(m); hl[h["id"]] = (o, em, mix)

cam_d = bpy.data.cameras.new("cam"); cam_d.sensor_fit = "VERTICAL"; cam = bpy.data.objects.new("cam", cam_d); sc.collection.objects.link(cam); sc.camera = cam
suns = []
for name, energy, rot in (("key", 3.2, (-0.7, 0.0, 0.6)), ("fill", 0.9, (-0.3, 0.0, -0.9)), ("rim", 2.4, (0.4, 0.0, 3.1))):
    L = bpy.data.lights.new(name, "SUN"); L.energy = energy; L.angle = math.radians(25)
    o = bpy.data.objects.new(name, L); sc.collection.objects.link(o); suns.append((o, rot))

t0 = time.time(); times = []
for fr in frames[first:last]:
    t1 = time.time()
    cp, lk = Vector(fr["cam"]), Vector(fr["look"])
    cam.location = cp; cam.rotation_euler = (lk - cp).to_track_quat("-Z", "Y").to_euler(); cam_d.angle_y = math.radians(fr["fov"])
    cam_d.clip_start = 0.02; cam_d.clip_end = 30
    bpy.context.view_layer.update()
    q = cam.matrix_world.to_quaternion()
    for o, rot in suns:
        o.rotation_euler = (q @ __import__("mathutils").Euler(rot).to_quaternion()).to_euler()
    for ln, objs in layers.items():
        al = fr["alpha"].get(ln, 0.0)
        for o in objs: o.hide_render = al < 0.01
        for b in mats[ln]: b.inputs["Alpha"].default_value = al
    for hid, (o, em, mix) in hl.items():
        s = fr["highlight"].get(hid, 0.0); o.hide_render = s < 0.01
        em.inputs[1].default_value = 6.0 * s; mix.inputs[0].default_value = (spec.get('highlight_opacity', 0.3)) * s
    sc.render.filepath = f"{OUT}/f{fr['i']:05d}.png"
    bpy.ops.render.render(write_still=True)
    times.append(time.time() - t1)
print("RENDER frames", len(times), "total", round(time.time() - t0, 1), "avg", round(sum(times) / len(times), 2), "first", round(times[0], 2))
