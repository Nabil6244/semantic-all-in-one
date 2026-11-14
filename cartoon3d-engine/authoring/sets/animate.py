"""Animate a playland scene from a timeline (sets/scene_audio.py): lip sync from Rhubarb cues, blinks, gestures
(host waves / opens arms / looks at the speaker, kids cheer and hop), idle sway, camera cuts + slow push-ins.
Run: blender -b <scene.blend> --python sets/animate.py -- <timeline.json> <out dir> [frames|preview|timing|quality]\n(quality = the slow ray-traced look, ~8 s/frame; default is the fast look)
"""
import json
import math
import random
import sys
from pathlib import Path

import bpy
from mathutils import Euler, Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mocap  # noqa: E402
ARMS = ("arm", "Arm", "hand", "Hand", "Forearm", "forearm")

args = sys.argv[sys.argv.index("--") + 1:]
TL = json.loads(Path(args[0]).read_text())
OUT = Path(args[1])
OUT.mkdir(parents=True, exist_ok=True)
MODE = args[2] if len(args) > 2 else "frames"
FPS = 25
sc = bpy.context.scene
sc.render.fps = FPS
sc.frame_start, sc.frame_end = 1, int(TL["total"] * FPS)
rnd = random.Random(3)
F = lambda t: 1 + round(t * FPS)
O = bpy.data.objects

# ---------------- mouth shape tables (Rhubarb A-H, X) ----------------
HOST_V = {"A": {"Explosive": 0.6}, "B": {"Lip_Open": 0.9, "Wide": 0.35, "Open": 0.3}, "C": {"Open": 0.75, "Wide": 0.45},
          "D": {"Open": 1.0, "Lip_Open": 0.4}, "E": {"Open": 0.65, "Tight_O": 0.55}, "F": {"Tight_O": 1.0}, "G": {"Dental_Lip": 1.0},
          "H": {"Open": 0.6, "Lip_Open": 0.6}, "X": {}}      # ~1.6x: v3 read as mumbling
KID_V = {"A": {"mouthClose": 0.3}, "B": {"jawOpen": 0.28}, "C": {"jawOpen": 0.55, "mouthStretchLeft": 0.25, "mouthStretchRight": 0.25},
         "D": {"jawOpen": 0.85}, "E": {"jawOpen": 0.5, "mouthFunnel": 0.5}, "F": {"mouthPucker": 0.9, "jawOpen": 0.18},
         "G": {"mouthRollLower": 0.3, "jawOpen": 0.18}, "H": {"jawOpen": 0.5}, "X": {}}
BOY_V = {"A": (0, {}), "B": (10, {"mouth_wide": 0.3}), "C": (19, {"mouth_wide": 0.45}), "D": (28, {}), "E": (16, {"mouth_oo": 0.6}),
         "F": (7, {"mouth_oo": 1.0}), "G": (7, {"mouth_wide": 0.3}), "H": (14, {}), "X": (0, {})}

lines = {w: [l for l in TL["lines"] if l["who"] == w] for w in ("host", "hoorain", "noraiz")}
STORY = False      # per-line story acts are not built for the 3D path (kids stories moved to cartoon2d/); Scene 1 code runs


def cue_track(who):
    """[(frame, shape)] with X between lines; each cue keyed at its start and held, 2-frame blends."""
    out = []
    for ln in lines[who]:
        for c in ln["cues"]:
            out.append((F(c["t0"]), c["shape"]))
        out.append((F(ln["end"]), "X"))
    return out


def key_shapes(keyblocks_by_name, table, track, base):
    """keyblocks_by_name: name -> [KeyBlock,...]; base: name -> resting value."""
    names = {n for v in table.values() for n in v} & set(keyblocks_by_name)
    for n in names:
        for kb in keyblocks_by_name[n]:
            kb.value = base.get(n, 0.0)
            kb.keyframe_insert("value", frame=1)
    prev = None
    for fr, shape in track:
        vals = table.get(shape, {})
        for n in names:
            v = base.get(n, 0.0) + vals.get(n, 0.0) * (1 - 0.35 * (n in ("mouthClose",)))
            for kb in keyblocks_by_name[n]:
                if prev is not None:      # hold the previous shape until 2 frames before the change
                    kb.value = kb.value
                    kb.keyframe_insert("value", frame=max(1, fr - 2))
                kb.value = min(v, 1.0)
                kb.keyframe_insert("value", frame=fr)
        prev = shape


def blink_times(total, seed):
    r = random.Random(seed)
    t, out = r.uniform(0.6, 1.6), []
    while t < total - 0.3:
        out.append(t)
        t += r.uniform(2.2, 4.2)
    return out


def key_blink(kbs, total, seed, peak=1.0, base=0.0):
    for kb in kbs:
        kb.value = base
        kb.keyframe_insert("value", frame=1)
    for t in blink_times(total, seed):
        for fr, v in ((F(t) - 1, base), (F(t) + 1, peak), (F(t) + 3, peak * 0.6), (F(t) + 5, base)):
            for kb in kbs:
                kb.value = v
                kb.keyframe_insert("value", frame=fr)


# ---------------- pose helpers ----------------
def aim(rig, pb, d_world):
    head = rig.matrix_world @ pb.head
    cur = (rig.matrix_world @ pb.tail - head).normalized()
    r = cur.rotation_difference(Vector(d_world).normalized())
    q = rig.matrix_world.to_quaternion()
    r = q.inverted() @ r @ q
    m = pb.matrix.copy()
    loc = m.to_translation()
    m.translation = (0, 0, 0)
    new = r.to_matrix().to_4x4() @ m
    new.translation = loc
    pb.matrix = new
    bpy.context.view_layer.update()


def key_pose(rig, frame, dirs, base):
    """dirs: [(bone, world dir)] applied in order from the base pose; keys rotation of every bone in base."""
    for n, m in base.items():
        rig.pose.bones[n].matrix_basis = m.copy()
    bpy.context.view_layer.update()
    for item in dirs:
        if item[0] == "roll":                       # twist a bone about its own length (palm toward camera)
            _, n, deg = item
            pb = rig.pose.bones[n]
            m = pb.matrix.copy()
            axis = m.to_3x3().col[1].normalized()
            from mathutils import Matrix
            rot = Matrix.Rotation(math.radians(deg), 4, axis)
            loc = m.to_translation()
            m.translation = (0, 0, 0)
            m = rot @ m
            m.translation = loc
            pb.matrix = m
            bpy.context.view_layer.update()
        else:
            n, d = item
            aim(rig, rig.pose.bones[n], d)
    for n in base:
        pb = rig.pose.bones[n]
        pb.keyframe_insert("rotation_quaternion" if pb.rotation_mode == "QUATERNION" else "rotation_euler", frame=frame)


def snapshot(rig, names):
    return {n: rig.pose.bones[n].matrix_basis.copy() for n in names}


def look(rig, bone, frame, yaw_deg, pitch_deg=0.0, axis_up="Y"):
    """Small head turn on top of the bone's current rest: rotate about world Z (yaw) via a delta euler on the bone."""
    pb = rig.pose.bones[bone]
    pb.rotation_mode = "XYZ"
    pb.rotation_euler = Euler((math.radians(pitch_deg), math.radians(yaw_deg), 0), "XYZ") if axis_up == "Y" else \
        Euler((math.radians(pitch_deg), 0, math.radians(yaw_deg)), "XYZ")
    pb.keyframe_insert("rotation_euler", frame=frame)


def hop(holder, t, height, dur=0.45):
    z0 = holder.location.z
    for k in range(0, 7):
        s = k / 6
        holder.location.z = z0 + height * 4 * s * (1 - s)
        holder.keyframe_insert("location", index=2, frame=F(t + s * dur))
    holder.location.z = z0


def sway(holder, total, amp_deg, period, phase):
    r0 = holder.rotation_euler.z
    t = 0.0
    while t <= total:
        holder.rotation_euler.z = r0 + math.radians(amp_deg) * math.sin(2 * math.pi * t / period + phase)
        holder.keyframe_insert("rotation_euler", index=2, frame=F(t))
        t += period / 4
    holder.rotation_euler.z = r0


total = TL["total"]
host_rig, boy_rig = O["Armature"], O["noraiz_rig"]
hoo_rig = next(o for o in bpy.data.collections["CH-hoorain"].objects if o.type == "ARMATURE" and o.name.startswith("rig"))
H = {n: O[f"CH-{n}"] for n in ("host", "hoorain", "noraiz")}

# ================= HOST =================
body = next(o for o in bpy.data.collections["CH-host"].objects if o.name.startswith("CC_Base_Body"))
hkb = body.data.shape_keys.key_blocks
key_shapes({n: [hkb[n]] for n in hkb.keys()}, HOST_V, cue_track("host"), {})
jaw = host_rig.pose.bones["CC_Base_JawRoot"]
jaw.rotation_mode = "XYZ"
openness = {"A": 0, "B": 5, "C": 11, "D": 18, "E": 9, "F": 3, "G": 3, "H": 9, "X": 0}
jaw.keyframe_insert("rotation_euler", frame=1)
for fr, shp in cue_track("host"):
    jaw.keyframe_insert("rotation_euler", frame=max(1, fr - 2))
    jaw.rotation_euler = Euler((0, 0, math.radians(openness[shp])), "XYZ")
    jaw.keyframe_insert("rotation_euler", frame=fr)
blink_k = [hkb[n] for n in ("Eye_Blink_L", "Eye_Blink_R") if n in hkb]
key_blink(blink_k, total, 11)
# smile breathes with speech
for n, v in (("Mouth_Smile", 1.0), ("Mouth_Smile_L", 0.35), ("Mouth_Smile_R", 0.35), ("Cheek_Raise_L", 0.35), ("Cheek_Raise_R", 0.35)):
    if n in hkb:                      # friendly host: the smile stays under every talking mouth shape
        hkb[n].value = v
        hkb[n].keyframe_insert("value", frame=1)
# arms: wave on "Hi friends", open arms on "ready to play", point toward kids while they speak
ARM_BONES = [f"CC_Base_{s}_{b}" for s in ("L", "R") for b in ("Upperarm", "Forearm", "Hand")]
for n in ARM_BONES:
    host_rig.pose.bones[n].rotation_mode = "QUATERNION"
base = snapshot(host_rig, ARM_BONES)
if not STORY:      # Scene 1: wave, open arms, point, head looks
    rest = []
    l0 = lines["host"][0]
    l1 = lines["host"][1]
    key_pose(host_rig, 1, rest, base)
    key_pose(host_rig, F(l0["start"] - 0.2), rest, base)
    WAVE_ROLL = float(__import__("os").environ.get("WAVE_ROLL", "-80"))
    wave_up = [("CC_Base_R_Upperarm", (-0.62, -0.15, 0.45)), ("CC_Base_R_Forearm", (-0.15, -0.2, 0.97)),
               ("CC_Base_R_Hand", (-0.12, -0.25, 0.96)), ("roll", "CC_Base_R_Hand", WAVE_ROLL)]
    # wave: CMU 111_37 (a real person waving), arms only so the head looks stay ours
    mocap.apply(host_rig, "host", mocap.CLIPS / "111_37.bvh", 0.25, min(2.2, l0["end"] - l0["start"] - 0.7), F(l0["start"] + 0.1),
                holder=H["host"], blend=0.3, only=ARMS)
    key_pose(host_rig, F(l0["end"] - 0.3), rest, base)
    open_arms = [("CC_Base_L_Upperarm", (0.4, -0.28, -0.87)), ("CC_Base_L_Forearm", (0.35, -0.9, 0.2)),       # relaxed "presenting", elbows in
                 ("CC_Base_R_Upperarm", (-0.4, -0.28, -0.87)), ("CC_Base_R_Forearm", (-0.35, -0.9, 0.2))]
    key_pose(host_rig, F(l1["start"] + 0.9), open_arms, base)
    key_pose(host_rig, F(l1["end"] - 0.1), open_arms, base)
    key_pose(host_rig, F(l1["end"] + 0.4), rest, base)
    point = [("CC_Base_L_Upperarm", (0.45, -0.35, -0.82)), ("CC_Base_L_Forearm", (0.6, -0.65, -0.45))]   # low point: stays out of the kids' shot
    kid_t0 = lines["hoorain"][0]["start"]
    key_pose(host_rig, F(kid_t0 + 0.1), point, base)
    key_pose(host_rig, F(lines["noraiz"][0]["end"]), point, base)
    key_pose(host_rig, F(lines["noraiz"][0]["end"] + 0.5), rest, base)
    # head: to camera while talking, toward the kids (her left) when they talk, small nods
    head = host_rig.pose.bones["CC_Base_Head"]
    head.rotation_mode = "XYZ"
    for t_, yaw, pitch in ((0, 0, 0), (l0["start"] + 0.4, 0, -4), (l0["start"] + 1.0, 0, 3), (l0["end"], 0, 0), (l1["start"] + 0.5, 4, -3),
                           (l1["end"] - 0.2, 0, 2), (kid_t0 + 0.2, -18, -6), (lines["noraiz"][0]["start"], -26, -8),
                           (lines["noraiz"][0]["end"] + 0.3, -20, -4), (total, -6, 0)):
        head.rotation_euler = Euler((math.radians(pitch), math.radians(yaw), 0), "XYZ")
        head.keyframe_insert("rotation_euler", frame=F(t_))

# ================= HOORAIN =================
kb_by = {}
base_h = {}
dg = bpy.context.evaluated_depsgraph_get()
for o in bpy.data.collections["CH-hoorain"].objects:
    if o.type == "MESH" and o.data.shape_keys and "jawOpen" in o.data.shape_keys.key_blocks and "Tongue" not in o.name:
        sk = o.data.shape_keys
        ev = o.evaluated_get(dg).data.shape_keys if o.evaluated_get(dg).data.shape_keys else sk
        for n in list(KID_V["D"]) + ["mouthClose", "mouthFunnel", "mouthPucker", "mouthRollLower", "mouthStretchLeft", "mouthStretchRight",
                                     "eyeBlinkLeft", "eyeBlinkRight"]:
            if n not in sk.key_blocks:
                continue
            base_h.setdefault(n, sk.key_blocks[n].value)
            if sk.animation_data:
                d = sk.animation_data.drivers.find(f'key_blocks["{n}"].value')
                if d:
                    sk.animation_data.drivers.remove(d)     # mouth + blink now keyed directly (face rig keeps the smile)
            kb_by.setdefault(n, []).append(sk.key_blocks[n])
print("HOORAIN_KEYS", sorted(kb_by), {k: round(v, 2) for k, v in base_h.items() if v})
key_shapes(kb_by, KID_V, cue_track("hoorain"), base_h)
key_blink(kb_by.get("eyeBlinkLeft", []) + kb_by.get("eyeBlinkRight", []), total, 23, 1.0, base_h.get("eyeBlinkLeft", 0.0))
hp = hoo_rig.pose.bones
hb = [n for n in ("c_arm_fk.l", "c_forearm_fk.l", "c_arm_fk.r", "c_forearm_fk.r") if n in hp]
for n in hb:
    hp[n].rotation_mode = "QUATERNION"
hbase = snapshot(hoo_rig, hb)
if not STORY:      # Scene 1: Hoorain's 'Yay' cheer
    yay_t = lines["hoorain"][0]["start"]
    cheer = [("c_arm_fk.l", (0.75, -0.25, 0.6)), ("c_forearm_fk.l", (0.55, -0.3, 0.78)),        # wide V, hands clear of the head
             ("c_arm_fk.r", (-0.75, -0.25, 0.6)), ("c_forearm_fk.r", (-0.55, -0.3, 0.78))]
    key_pose(hoo_rig, 1, [], hbase)
    key_pose(hoo_rig, F(yay_t - 0.15), [], hbase)
    mocap.apply(hoo_rig, "hoorain", mocap.CLIPS / "79_69.bvh", 3.0, 1.4, F(yay_t - 0.05), holder=H["hoorain"], blend=0.25, only=ARMS)
    key_pose(hoo_rig, F(yay_t + 1.9), [], hbase)
    hop(H["hoorain"], yay_t + 0.05, 0.12)
sway(H["hoorain"], total, 3, 3.1, 0.4)

# ================= NORAIZ =================
fk = O["face_geo"].data.shape_keys.key_blocks
bj = boy_rig.pose.bones["jaw"]
bj.rotation_mode = "XYZ"
key_shapes({n: [fk[n]] for n in ("mouth_wide", "mouth_oo")}, {k: v[1] for k, v in BOY_V.items()}, cue_track("noraiz"), {})
bj.keyframe_insert("rotation_euler", frame=1)
for fr, shp in cue_track("noraiz"):
    bj.keyframe_insert("rotation_euler", frame=max(1, fr - 2))
    bj.rotation_euler = Euler((math.radians(BOY_V[shp][0]), 0, 0), "XYZ")
    bj.keyframe_insert("rotation_euler", frame=fr)
key_blink([fk["blink.L"], fk["blink.R"]], total, 37)
bp = boy_rig.pose.bones
bb = ["upper_arm.L", "forearm.L", "upper_arm.R", "forearm.R"]
for n in bb:
    bp[n].rotation_mode = "QUATERNION"
bbase = snapshot(boy_rig, bb)
if not STORY:      # Scene 1: counts on his fingers, jump, glance
    nl = lines["noraiz"][0]
    words = [nl["start"] + f * (nl["end"] - nl["start"]) for f in (0.08, 0.3, 0.52, 0.82)]   # one, two, three, jump
    key_pose(boy_rig, 1, [], bbase)
    for k, wt in enumerate(words[:3]):                  # counts on his fingers: right arm bounces up a little each number
        key_pose(boy_rig, F(wt), [("upper_arm.R", (-0.5, -0.45, -0.2)), ("forearm.R", (-0.2, -0.6, 0.45 + 0.15 * k))], bbase)
        hop(H["noraiz"], wt, 0.03, 0.25)
    key_pose(boy_rig, F(words[3] - 0.45), [], bbase)
    mocap.apply(boy_rig, "noraiz", mocap.CLIPS / "49_02.bvh", 4.45, 1.35, F(words[3] - 0.35), holder=H["noraiz"], blend=0.15,
                only=("__no_bones__",), root_bounce=3.5)
    up = [("upper_arm.L", (0.45, -0.15, 0.88)), ("forearm.L", (0.25, -0.15, 0.96)), ("upper_arm.R", (-0.45, -0.15, 0.88)), ("forearm.R", (-0.25, -0.15, 0.96))]
    key_pose(boy_rig, F(words[3] - 0.1), up, bbase)
    key_pose(boy_rig, F(words[3] + 0.9), up, bbase)
    key_pose(boy_rig, F(words[3] + 1.4), [], bbase)
    bh = bp["head"]
    bh.rotation_mode = "XYZ"
    for t_, ang in ((0, 0), (yay_t, 8), (nl["start"], 0), (total, 0)):     # glances at his sister when she cheers
        bh.rotation_euler = Euler((0, 0, math.radians(ang)), "XYZ")
        bh.keyframe_insert("rotation_euler", frame=F(t_))
sway(H["noraiz"], total, 4, 2.6, 1.7)
sway(H["host"], total, 1.5, 4.0, 0.0)

# ================= soft front "beauty" light on the cast (no shadows, so it costs almost nothing) =================
bl = bpy.data.lights.new("beauty", "AREA")
bl.energy, bl.size, bl.color, bl.use_shadow = 140, 3.5, (1.0, 0.95, 0.9), False
blo = bpy.data.objects.new("beauty", bl)
sc.collection.objects.link(blo)
blo.location, blo.rotation_euler = (0.0, -4.2, 2.2), Euler((math.radians(68), 0, 0), "XYZ")

# ================= cameras =================
cg = O["CAM-group"]
cd = bpy.data.cameras.new("CAM-host")
ch = bpy.data.objects.new("CAM-host", cd)
sc.collection.objects.link(ch)
cd.lens, ch.location, ch.rotation_euler = 52, (-0.68, -4.6, 1.52), Euler((math.radians(88), 0, math.radians(-2)), "XYZ")   # host only: no bow in the corner
cd.dof.use_dof, cd.dof.focus_distance, cd.dof.aperture_fstop = True, 2.45, 2.2
ck_d = bpy.data.cameras.new("CAM-kids")
ck = bpy.data.objects.new("CAM-kids", ck_d)
sc.collection.objects.link(ck)
ck_d.lens, ck.location, ck.rotation_euler = 36, (0.7, -4.4, 0.82), Euler((math.radians(88), 0, 0), "XYZ")   # both kids fully in frame
ck_d.dof.use_dof, ck_d.dof.focus_distance, ck_d.dof.aperture_fstop = True, 2.2, 2.2
if not STORY:      # Scene 1's own shot list
    shots = [(0, cg), (l0["start"] + 0.1, ch), (l1["start"] + 0.6, cg), (yay_t - 0.1, ck), (nl["end"] + 0.4, cg)]
for t_, cam in shots:
    m = sc.timeline_markers.new(cam.name, frame=F(t_))
    m.camera = cam
for cam, push in ((cg, 0.35), (ch, 0.25), (ck, 0.3)):   # slow push-in all the way through
    y0 = cam.location.y
    cam.keyframe_insert("location", index=1, frame=1)
    cam.location.y = y0 + push
    cam.keyframe_insert("location", index=1, frame=sc.frame_end)
    cam.location.y = y0
for o in [cg, ch, ck]:
    if o.animation_data and o.animation_data.action:
        for fc in getattr(o.animation_data.action, "fcurves", []):
            for kp in fc.keyframe_points:
                kp.interpolation = "LINEAR"

# ================= render =================
sc.render.resolution_x, sc.render.resolution_y = 1280, 720


def merge_set():
    """~650 static set props -> one mesh per material: modifiers baked, text turned into mesh, then joined."""
    setc = bpy.data.collections.get("SET-playland")
    if setc is None:
        return
    objs = [o for o in setc.objects if o.type in ("MESH", "FONT") and not (o.animation_data and o.animation_data.action)]
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.hide_set(False)
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.convert(target="MESH")               # applies bevel/solidify/subsurf/skin/wireframe, text -> mesh
    meshes = [o for o in setc.objects if o.type == "MESH" and o.select_get()]
    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    bpy.ops.object.join()
    print("SET_MERGED", len(meshes), "->", bpy.context.view_layer.objects.active.name,
          len(bpy.context.view_layer.objects.active.data.polygons), "faces")


FAST = MODE != "quality"
if FAST:      # speed: a bright cartoon room looks the same without ray tracing; heavy extras off
    merge_set()
    ee = sc.eevee
    for o in bpy.data.objects:          # only the main sun casts shadows (grounds the cast); fills and ceiling panels don't
        if o.type == "LIGHT" and o.name != "sun":
            o.data.use_shadow = False
        if o.type == "LIGHT" and o.data.type == "AREA":
            o.data.specular_factor = 0.1     # big square panels mirrored in glossy eyes read as a grey square glare
    for attr, val in (("use_raytracing", False), ("taa_render_samples", 6), ("use_shadow_jitter_viewport", False),
                      ("shadow_ray_count", 1), ("shadow_step_count", 4), ("use_fast_gi", False)):
        if hasattr(ee, attr):
            setattr(ee, attr, val)
    sc.view_settings.exposure = -0.72                    # v3 floors/walls clipped near white in close-ups
    sc.render.use_simplify = True
    sc.render.simplify_subdivision_render = 1           # characters smoothed once, not twice
    sc.render.use_persistent_data = True                 # keep the scene loaded between frames
    import os as _os
    PROBE_RT = _os.environ.get("RT", "off") == "probe"      # tested: probe RT turns CC eyes milky and costs 1.7 s/frame
    if PROBE_RT and hasattr(ee, "ray_tracing_method"):   # cheap ray tracing (light probes only): CC eyes refract right again
        ee.use_raytracing = True
        ee.ray_tracing_method = "PROBE"
    for o in bpy.data.objects:                           # CC eye-shadow shells read as dark sunken eyes without ray tracing
        if PROBE_RT:
            break
        if o.name.startswith("CC_Base_EyeOcclusion"):
            o.hide_render = True
    # Hoorain's CC layered eye shader needs ray tracing for its whites: fast cartoon eye from her own iris texture
    import os as _os2
    kid_eye_dir = Path(__file__).resolve().parent.parent / "downloads" / "kid_tex" / "Texture" / "Little Kid.fbm"
    for o in bpy.data.objects:
        if o.type != "MESH" or not o.name.startswith("CC_Base_Eye.") or "CH-hoorain" not in [c.name for c in o.users_collection]:
            continue
        for slot in o.material_slots:
            m = slot.material
            if not m or m.get("fast_eye"):
                continue
            side = "R" if "_R" in m.name else "L"
            lens = "Cornea" in m.name                         # her iris + pupil live on the lens layer
            tex_path = kid_eye_dir / (f"Std_Cornea_{side}_Diffuse.jpg" if lens else f"Std_Eye_{side}_Diffuse.jpg")
            if not tex_path.exists():
                continue
            nt = m.node_tree
            nt.nodes.clear()
            outn, p = nt.nodes.new("ShaderNodeOutputMaterial"), nt.nodes.new("ShaderNodeBsdfPrincipled")
            tx = nt.nodes.new("ShaderNodeTexImage")
            tx.image = bpy.data.images.load(str(tex_path), check_existing=True)
            if lens:                                          # iris ~15% smaller about the eye centre (v3 read doll-like)
                uvn, mp_ = nt.nodes.new("ShaderNodeTexCoord"), nt.nodes.new("ShaderNodeMapping")
                k_ = 1.18
                mp_.inputs["Scale"].default_value = (k_, k_, 1.0)
                mp_.inputs["Location"].default_value = (0.5 - 0.5 * k_, 0.5 - 0.5 * k_, 0.0)
                nt.links.new(uvn.outputs["UV"], mp_.inputs["Vector"])
                nt.links.new(mp_.outputs["Vector"], tx.inputs["Vector"])
            bw = nt.nodes.new("ShaderNodeRGBToBW")
            ramp = nt.nodes.new("ShaderNodeValToRGB")                 # bright background -> 0 (white), iris/pupil -> 1
            ramp.color_ramp.elements[0].position, ramp.color_ramp.elements[1].position = 0.62, 0.72
            ramp.color_ramp.elements[0].color, ramp.color_ramp.elements[1].color = (1, 1, 1, 1), (0, 0, 0, 1)
            mix = nt.nodes.new("ShaderNodeMixRGB")
            mix.inputs["Color2"].default_value = (0.93, 0.93, 0.95, 1)   # clean eye white
            nt.links.new(tx.outputs["Color"], bw.inputs["Color"])
            nt.links.new(bw.outputs["Val"], ramp.inputs["Fac"])
            nt.links.new(ramp.outputs["Color"], mix.inputs["Fac"])
            nt.links.new(tx.outputs["Color"], mix.inputs["Color1"])
            nt.links.new(mix.outputs["Color"], p.inputs["Base Color"])
            p.inputs["Roughness"].default_value = 0.3
            p.inputs["Coat Weight"].default_value = 1.0
            p.inputs["Coat Roughness"].default_value = 0.03
            if lens:      # lens: iris where the texture is dark, see-through elsewhere (white eyeball shows)
                tr, ms = nt.nodes.new("ShaderNodeBsdfTransparent"), nt.nodes.new("ShaderNodeMixShader")
                nt.links.new(ramp.outputs["Color"], ms.inputs["Fac"])       # ramp: iris (dark texels) -> 1 = solid
                nt.links.new(tr.outputs[0], ms.inputs[1])
                nt.links.new(p.outputs["BSDF"], ms.inputs[2])
                nt.links.new(ms.outputs[0], outn.inputs["Surface"])
                mix.inputs["Fac"].default_value = 0.0
                nt.links.remove(ramp.outputs["Color"].links[0]) if any(l.to_node == mix for l in ramp.outputs["Color"].links) else None
                nt.links.new(tx.outputs["Color"], mix.inputs["Color1"])
            else:         # eyeball: clean white
                for l in list(mix.inputs["Fac"].links):
                    nt.links.remove(l)
                mix.inputs["Fac"].default_value = 1.0
                nt.links.new(p.outputs["BSDF"], outn.inputs["Surface"])
            if hasattr(m, "surface_render_method"):
                m.surface_render_method = "BLENDED" if lens else "DITHERED"
            m["fast_eye"] = True
            m["fast_lens"] = True
            print("FAST_EYE", o.name, m.name)
    for cam_name in ("CAM-kids", "CAM-group", "CAM-host"):      # tiny lights by each camera = round catch-lights in the eyes
        cam = bpy.data.objects.get(cam_name)
        if cam is None or bpy.data.objects.get(f"catch_{cam_name}"):
            continue
        ld = bpy.data.lights.new(f"catch_{cam_name}", "POINT")
        ld.energy, ld.shadow_soft_size, ld.use_shadow = 5, 0.02, False
        lo = bpy.data.objects.new(f"catch_{cam_name}", ld)
        sc.collection.objects.link(lo)
        lo.parent, lo.location = cam, (0.12, 0.25, 0.0)
    for o in bpy.data.objects:
        if o.type == "MESH":
            for m in o.data.materials:
                if m and "Cornea" in m.name and not m.get("fast_lens") and not PROBE_RT:
                    # CC lens shader needs ray-traced refraction; without it the eye goes milky: clear gloss instead
                    nt = m.node_tree
                    outn = next(n for n in nt.nodes if n.type == "OUTPUT_MATERIAL")
                    tr, gl, mix = nt.nodes.new("ShaderNodeBsdfTransparent"), nt.nodes.new("ShaderNodeBsdfGlossy"), nt.nodes.new("ShaderNodeMixShader")
                    gl.inputs["Roughness"].default_value = 0.05
                    mix.inputs["Fac"].default_value = 0.0      # fully clear: the eye's own coat gives the shine (no square glare)
                    nt.links.new(tr.outputs[0], mix.inputs[1])
                    nt.links.new(gl.outputs[0], mix.inputs[2])
                    nt.links.new(mix.outputs[0], outn.inputs["Surface"])
                    if hasattr(m, "surface_render_method"):
                        m.surface_render_method = "BLENDED"
                    m["fast_lens"] = True
                if m and m.use_nodes and not any(k in m.name for k in ("Eye", "Cornea", "Iris")):
                    for n in m.node_tree.nodes:
                        if n.type == "BSDF_PRINCIPLED" and n.inputs["Subsurface Weight"].default_value > 0:
                            n.inputs["Subsurface Weight"].default_value = 0.0     # SSS pass off; skin colour unchanged
else:
    sc.eevee.taa_render_samples = 24
bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "scene_anim.blend"))
print("FRAMES", sc.frame_start, sc.frame_end)
if MODE == "timing":       # render 3 frames and report seconds per frame
    import time
    for fr in (60, 200, 340):
        t0 = time.time()
        sc.frame_set(fr)
        t1 = time.time()
        sc.render.filepath = str(OUT / f"timing_{fr:04d}.png")
        bpy.ops.render.render(write_still=True)
        print("FRAME_SECONDS", fr, "pose", round(t1 - t0, 2), "render", round(time.time() - t1, 2))
    import os
    for hide in filter(None, os.environ.get("HIDE", "").split(",")):
        for o in bpy.data.collections[f"CH-{hide}"].all_objects:
            o.hide_render = True
            o.hide_viewport = True
    if os.environ.get("SAMPLES"):
        sc.eevee.taa_render_samples = int(os.environ["SAMPLES"])
    if os.environ.get("NOSHADOW"):
        sc.eevee.use_shadows = False
    sc.frame_start, sc.frame_end = 180, 199
    sc.render.filepath = str(OUT / "timing_anim" / "f_")
    t0 = time.time()
    bpy.ops.render.render(animation=True)
    print("ANIM_20_FRAMES", round(time.time() - t0, 2), "s ->", round((time.time() - t0) / 20, 2), "s/frame")
    for res in ():
        sc.render.resolution_percentage = res
        t0 = time.time()
        bpy.ops.render.render(write_still=False)
        print("HALF_RES_RENDER", round(time.time() - t0, 2))
        sc.render.resolution_percentage = 100
elif MODE == "preview":       # a few stills to check poses
    for t_ in [float(x) for x in __import__("os").environ.get("PREVIEW_T", "").split(",") if x] or \
              (l0["start"] + 0.9, l1["start"] + 1.2, yay_t + 0.4, words[1], words[3] + 0.3):
        sc.frame_set(F(t_))
        sc.render.filepath = str(OUT / f"still_{F(t_):04d}.png")
        bpy.ops.render.render(write_still=True)
else:
    sc.render.image_settings.file_format = "PNG"
    sc.render.filepath = str(OUT / "frames" / "f_")
    bpy.ops.render.render(animation=True)
print("DONE")
