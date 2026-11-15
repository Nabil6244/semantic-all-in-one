"""Toon Tales shot builder (Blender side): one shot json -> numbered PNG frames.

Run: blender -b --factory-startup --python toontales/shots/shot.py -- <shot.json> <frames dir>

shot.json (written by the driver / later by the plan step):
  set        "mine" (built set) or "stage" with backdrop = painted place picture (sets/backdrop.py)
  fps, size  30, [1080, 1920]
  dur        seconds
  cast       [{"id": "walt", "mark": "A"}, ...]                marks come from the set kit
  lines      [{"who", "start", "dur", "cues": [{t0, t1, shape}]}]  Rhubarb cues, line-relative
  actions    [{"who", "do", "t0", "dur"?, "blend"?, "params"?, "eyes"?, "mouth"?}]
             do = any library action or static pose (toontales/library); blends in from the previous
             action over `blend` s (0.2); moving actions (walk/run) leave the character at the new spot.
             Old form {"pose", "t0", "t1"} still works (blend over t0..t1, then hold).
  faces      [{"who", "eyes"?, "mouth"?, "t0", "t1"}]          expression overrides
  camera     {"from": {target, dist, yaw, pitch, lens}, "to": {...}, "drift": metres}
Every frame is driven from Python (pose, face, bob, camera) so mouths/eyes are exact per frame.
"""
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

HERE = Path(__file__).resolve().parent
TT = HERE.parent
sys.path[:0] = [str(TT), str(TT / "cast"), str(TT / "library"), str(TT / "props")]
import actions as A  # noqa: E402
import fx  # noqa: E402
import props as P  # noqa: E402
import puppet  # noqa: E402
from sets import ambient, backdrop, mine  # noqa: E402

SETS = {"mine": mine}
FACES = TT / "build" / "faces"
FX_DIR = TT / "build" / "fx"
CAST = TT / "cast" / "cast.json"
TALK_OPEN = set("BCDEFGH")  # Rhubarb shapes with the jaw open (A/X closed)
BLINKABLE = {"open", "half", "wide", "worried", "angry", "sly", "sad", "up", "look_l", "look_r"}


def _smooth(x):
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def _scene(fps, size, samples=32):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    puppet._engine()
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.exposure = 0.2
    sc.render.fps = fps
    sc.render.resolution_x, sc.render.resolution_y = size
    sc.render.image_settings.file_format = "PNG"
    try:
        sc.eevee.taa_render_samples = samples
        sc.eevee.use_shadows = True
        sc.eevee.shadow_pool_size = "1024"
    except Exception:
        pass
    bpy.ops.object.camera_add()
    cam = bpy.context.active_object
    sc.camera = cam
    cam.data.sensor_fit = "VERTICAL"
    return sc, cam


def _ease(kind, x, dur):
    if kind == "out_fast":  # crash zoom: most of the move in the first ~0.3 s
        return 1 - (1 - min(1.0, x * dur / 0.3)) ** 3
    return _smooth(x)


def _prop_frame(pr, chars, t):
    """Held props follow the right hand; picked-up props wait on the floor until the grab; thrown ones fly."""
    who = pr["spec"].get("held_by") or pr["spec"].get("picked_by")
    ch = chars.get(who)
    if ch is None:
        return
    acts = ch["_acts"]
    grab = next((a["t0"] + 0.5 * a["dur"] for a in acts if a["do"] == "pick_up"), None)
    if pr["spec"].get("picked_by") and grab is not None and t < grab:
        pr["obj"].location = pr["home"]
        return
    hand = puppet.hand_world(ch, "R") + Vector((0, -0.04, -0.05))
    rel = next((a["t0"] + 0.72 * a["dur"] for a in acts if a["do"] == "throw"), None)
    if rel is not None and t >= rel:
        if "release" not in pr:
            pr["release"] = hand.copy()
        dt = t - rel
        pr["obj"].location = pr["release"] + Vector((3.0 * dt, 0.8 * dt, 1.8 * dt - 4.9 * dt * dt))
        pr["obj"].rotation_euler.y = 9 * dt
        return
    pr["obj"].location = hand


def _cam_at(cam, a, b, k, t, drift):
    p = {key: a[key] if not isinstance(a[key], list) else list(a[key]) for key in a}
    for key in ("dist", "yaw", "pitch", "lens"):
        p[key] = a[key] + (b[key] - a[key]) * k
    tgt = [x + (y - x) * k for x, y in zip(a["target"], b["target"])]
    # slow hand-held drift so the frame is never fully still
    tgt[0] += drift * math.sin(t * 1.3)
    tgt[2] += drift * 0.6 * math.sin(t * 0.9 + 1.0)
    puppet.aim(cam, tgt, p["dist"], yaw=p["yaw"], pitch=p["pitch"], lens=p["lens"])


def _norm_acts(acts):
    out = []
    for a in sorted(acts, key=lambda a: a["t0"]):
        a = dict(a)
        if "do" not in a:                       # old {"pose", t0, t1} form
            a["do"] = a["pose"]
            a["blend"] = max(0.01, a.get("t1", a["t0"]) - a["t0"])
        a.setdefault("dur", A.ACTIONS[a["do"]][1])
        a.setdefault("blend", 0.2)
        a.setdefault("params", {})
        out.append(a)
    return out


def _state(acts, t, m):
    """Library state for one character at shot time t (with root offsets carried between actions)."""
    if not acts or t < acts[0]["t0"]:
        return A.pose("idle"), {}
    i = max(j for j, a in enumerate(acts) if a["t0"] <= t)
    base = [0.0, 0.0]
    bases = []
    for a in acts:
        bases.append(list(base))
        dx, dy = A.final_root(a["do"], a["dur"], m, a["params"])
        base[0] += dx
        base[1] += dy

    def at(j, tt):
        a = acts[j]
        st = A.state_at(a["do"], tt - a["t0"], a["dur"], m, a["params"])
        st["root"][0] += bases[j][0]
        st["root"][1] += bases[j][1]
        return st

    cur = acts[i]
    st = at(i, t)
    k = (t - cur["t0"]) / cur["blend"]
    if k < 1:
        prev = at(i - 1, cur["t0"]) if i > 0 else A.pose("idle")
        st = A.blend(prev, st, A.smooth(k))
    return st, cur


def render_shot(shot, out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    fps = shot.get("fps", 30)
    sc, cam = _scene(fps, shot.get("size", [1080, 1920]), shot.get("samples", 32))
    marks = backdrop.build(shot["backdrop"]) if shot.get("backdrop") else SETS[shot["set"]].build()
    props = []
    for i, spec in enumerate(shot.get("props", [])):
        o = P.build(spec, i)
        props.append({"spec": spec, "obj": o, "home": o.location.copy()})
    cfgs = {c["id"]: c for c in json.loads(CAST.read_text())["characters"]}
    chars = {}
    for i, c in enumerate(shot["cast"]):
        x, y = marks["cast"][c["mark"]]
        chars[c["id"]] = puppet.build(cfgs[c["id"]], FACES, out, at=(x, y, 0))
        ch = chars[c["id"]]
        ch["_blink_off"] = 0.9 + i * 1.3
        ch["_m"] = puppet.metrics(ch)
        ch["_acts"] = _norm_acts([a for a in shot.get("actions", []) if a["who"] == c["id"]])
    sprites = fx.build(chars, FX_DIR, {})
    amb = ambient.build(shot.get("ambient", "dust" if shot.get("backdrop") else "none"), seed=len(shot.get("id", "")))
    n = int(round(shot["dur"] * fps))
    cm = shot["camera"]
    only = shot.get("frames")  # optional subset for checks
    for f in range(n):
        if only and f not in only:
            continue
        t = f / fps
        for cid, ch in chars.items():
            st, act = _state(ch["_acts"], t, ch["_m"])
            eyes = act.get("eyes", st["eyes"]) if act else st["eyes"]
            mouth = act.get("mouth", st["mouth"]) if act else st["mouth"]
            for fo in shot.get("faces", []):
                if fo["who"] == cid and fo["t0"] <= t < fo["t1"]:
                    eyes = fo.get("eyes", eyes)
                    mouth = fo.get("mouth", mouth)
            talking, shape = False, "X"
            for ln in shot.get("lines", []):
                if ln["who"] == cid and ln["start"] <= t < ln["start"] + ln["dur"]:
                    talking = True
                    lt = t - ln["start"]
                    shape = next((c["shape"] for c in ln["cues"] if c["t0"] <= lt < c["t1"]), "X")
            if talking:
                mouth = shape
            # blink: 3 frames every ~3.1 s, only on plain open-type eyes
            ph = (t + ch["_blink_off"]) % 3.1
            if ph < 3 / fps and eyes in BLINKABLE:
                eyes = "closed"
            st["eyes"], st["mouth"] = eyes, mouth
            bob = 0.006 * math.sin(2 * math.pi * (t + ch["_blink_off"]) / 2.4)
            if talking and shape in TALK_OPEN:
                bob += 0.01
            puppet.apply_state(ch, st, bob=bob)
        if props or sprites:
            bpy.context.view_layer.update()
            for pr in props:
                _prop_frame(pr, chars, t)
            fx.step(sprites, chars, t)
        ambient.step(amb, t)
        _cam_at(cam, cm["from"], cm["to"], _ease(cm.get("ease", "inout"), t / shot["dur"], shot["dur"]), t,
                cm.get("drift", 0.01))
        sc.render.filepath = str(out / f"f{f:04d}.png")
        bpy.ops.render.render(write_still=True)
        print("FRAME", f + 1, "/", n, flush=True)
    print("SHOT DONE", out, flush=True)


def main(argv):
    """<shot.json> <frames dir>   or   --batch <batch.json> ([{"shot": path, "out": dir}, ...])"""
    if argv and argv[0] == "--batch":
        jobs = json.loads(Path(argv[1]).read_text())
        for i, job in enumerate(jobs):
            print(f"BATCH {i + 1}/{len(jobs)}", job["out"], flush=True)
            render_shot(json.loads(Path(job["shot"]).read_text()), job["out"])
            Path(job["out"], "DONE").write_text("ok")
        return
    render_shot(json.loads(Path(argv[0]).read_text()), argv[1])


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
