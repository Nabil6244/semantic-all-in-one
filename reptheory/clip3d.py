"""3D body clips for Rep Theory: the Health Cinema body model (skin, muscle, skeleton, organs; Z-Anatomy, already in ~/HealthCinemaTools/bench) drawn by its Three.js renderer, with the camera on the
body part the narration is about and that part's muscle layer glowing. The region comes from the beat's own words, so any script gets a clip for whatever it names; a beat that names no body part gets none.
Clips are cached by Health Cinema's render cache (spec + model + code hash), so the same region/view/length is rendered once."""
from __future__ import annotations
import json, os, re, tempfile
from pathlib import Path
from typing import Optional, Tuple

from health_cinema import bodymap as BM, render_journey as RJ

ASSET_REL = "assets/reptheory_3d"      # shipped with the app: body_gym.glb + anchors_gym.json (+ NOTICE.txt / LICENSE_Z-Anatomy.txt: Z-Anatomy, CC BY-SA 4.0)

def _roots():
    try:
        from health_cinema.assets import roots      # the app's shared roots (dev checkout, PyInstaller bundle, next to the executable)
        return roots()
    except Exception: return [Path(__file__).resolve().parent.parent]

def model_dirs():
    """Folders searched for the gym body, best first: REP_THEORY_3D_DIR (exact, when set), the model that ships with the app, a per-user folder, then the local model library it is built in."""
    env = os.environ.get("REP_THEORY_3D_DIR")
    if env: return [Path(env).expanduser()]
    return [r / ASSET_REL for r in _roots()] + [Path.home() / ".semantic_yt_studio" / "rep_theory" / "3d", Path.home() / "HealthCinemaTools" / "bench"]

def model_paths():
    for d in model_dirs():
        if (d / "body_gym.glb").is_file() and (d / "anchors_gym.json").is_file(): return d / "body_gym.glb", d / "anchors_gym.json"
    return None, None

MODEL, ANCHORS = model_paths()
_legacy = Path.home() / "HealthCinemaTools" / "rep_theory_clips"      # the dev machine's existing clip library keeps being used; any other machine gets its own folder
CACHE = _legacy if _legacy.is_dir() else Path.home() / ".semantic_yt_studio" / "rep_theory" / "clips"
# muscle group (a Layer_M_<group> of the model) -> (regex on the narration, label, seen from the back?, camera scale when it is the first group)
GROUPS = {
    "biceps": (r"\b(biceps?|brachialis)\b", "Biceps", False, "close"), "triceps": (r"\b(triceps?)\b", "Triceps", True, "close"),
    "deltoid": (r"\b(deltoids?|delts?|shoulders?(?! blades?))\b", "Shoulders", False, "close"), "chest": (r"\b(chest|pecs?|pectorals?|pectoralis)\b", "Chest", False, "region"),
    "lats": (r"\b(lats?|latissimus|teres major)\b", "Lats", True, "region"), "traps": (r"\b(traps?|trapezius|rhomboids?|shoulder blades?|scapula\w*|upper back|levator)\b", "Upper back", True, "region"),
    "rotator_cuff": (r"\b(rotator cuff|supraspinatus|infraspinatus|subscapularis)\b", "Rotator cuff", True, "close"), "serratus": (r"\b(serratus)\b", "Serratus", False, "region"),
    "abs": (r"\b(abs|abdominals?|abdominal|core|six[- ]?pack|obliques?|rectus abdominis)\b", "Core", False, "region"),
    "erectors": (r"\b(erector\w*|lower back|spinal erectors?|lumbar)\b", "Lower back", True, "region"), "glutes": (r"\b(glutes?|gluteus|butt|buttocks)\b", "Glutes", True, "region"),
    "quads": (r"\b(quads?|quadriceps|thighs?|vastus)\b", "Quads", False, "region"), "hamstrings": (r"\b(hamstrings?)\b", "Hamstrings", True, "region"),
    "adductors": (r"\b(adductors?|inner thighs?|groin)\b", "Adductors", False, "region"), "calves": (r"\b(calf|calves|gastrocnemius|soleus)\b", "Calves", True, "close"),
    "shins": (r"\b(shins?|tibialis)\b", "Shins", False, "close"), "forearm_flexors": (r"\b(forearms?|grip|wrist flexors?|wrists?|fingers?|hands?)\b", "Forearm", False, "close"),
    "forearm_extensors": (r"\b(wrist extensors?|forearm extensors?)\b", "Forearm extensors", True, "close"), "hip_flexors": (r"\b(hip flexors?|psoas|iliopsoas)\b", "Hip flexors", False, "region"),
    "neck": (r"\b(neck|sternocleidomastoid)\b", "Neck", False, "close"),
}
# an exercise named with no muscle: the muscles that do the work (standard exercise science; the clip says "worked in <exercise>", it is approximate for a person's own form)
EXERCISE = (
    (r"\b(push[- ]?ups?|press[- ]?ups?|bench press|dips?)\b", ("chest", "triceps", "deltoid"), "Push-up"), (r"\b(pull[- ]?ups?|chin[- ]?ups?|rows?|lat pulldowns?)\b", ("lats", "biceps", "traps"), "Pull-up"),
    (r"\b(squats?|lunges?|leg press)\b", ("quads", "glutes", "hamstrings"), "Squat"), (r"\b(deadlifts?|hip thrusts?|good mornings?)\b", ("glutes", "hamstrings", "erectors"), "Deadlift"),
    (r"\b(planks?|crunch(es)?|sit[- ]?ups?|leg raises?)\b", ("abs", "hip_flexors"), "Plank"), (r"\b(curls?)\b", ("biceps", "forearm_flexors"), "Curl"),
    (r"\b(overhead press|shoulder press|lateral raises?)\b", ("deltoid", "triceps", "traps"), "Press"), (r"\b(calf raises?)\b", ("calves",), "Calf raise"),
)

def groups_for(text: str):
    """[(group, label, back, scale)] named in the beat, in the order spoken; if none is named, the movers of an exercise it names (flagged `by_exercise`), else []."""
    hits = sorted(((m.start(), g) for g, (rx, *_r) in GROUPS.items() for m in [re.search(rx, text, re.I)] if m))
    if hits: return [(g, *GROUPS[g][1:]) for _, g in hits], False
    for rx, gs, name in EXERCISE:
        if re.search(rx, text, re.I): return [(g, *GROUPS[g][1:]) for g in gs], name
    return [], False

def available() -> bool:
    """The 3D gym body (body_gym.glb + anchors_gym.json, built once by health_cinema/bench/prep_muscles.py and build_gym_body.py) and the Three.js renderer are present."""
    try:
        from health_cinema import assets
        return model_paths()[0] is not None and not assets.missing_threejs_files()
    except Exception: return False

def region_for(text: str):
    got, _ = groups_for(text); return got[0][:1] + got[0][3:4] + got[0][2:3] + got[0][1:2] if got else None      # (group, scale, back, label)

STYLES = ("push", "orbit", "side", "xray")      # camera / look variants, so the same muscle is never shown the same way twice in a row

def spec_for(text: str, seconds: float, anchors: dict, style: str = "push"):
    gs, by_ex = groups_for(text)
    if not gs: return None
    D = float(seconds); gs = gs[:4]
    def anc(g): return f"m_{g}_r" if f"m_{g}_r" in anchors else f"m_{g}"
    gs = [x for x in gs if anc(x[0]) in anchors]
    if not gs: return None
    first = gs[0]; back = first[2]; anchors = dict(anchors)
    if len(gs) > 1:      # several muscles in one beat: the camera frames all of them (one box around the groups), seen from the side the first one is on
        bx = [anchors[anc(x[0])] for x in gs]; mn = [min(b["min"][i] for b in bx) for i in range(3)]; mx = [max(b["max"][i] for b in bx) for i in range(3)]
        anchors["m_union"] = {"min": mn, "max": mx, "center": [(a + b) / 2 for a, b in zip(mn, mx)]}; region, scale = "m_union", "region"
    else: region, scale = anc(first[0]), first[3]
    beat = {"t0": 0.0, "t1": D, "text": text, "region": region, "scale": scale, "focus": "body", "effect": "none", "label": "", "card_type": "none", "card_ref": "", "card_prompt": "", "card_at": None}
    spec = BM.build_spec([beat], anchors, D, cards_enabled=False); allg = list(GROUPS)
    named = {x[0]: i for i, x in enumerate(gs)}; step = min(1.2, D * 0.25 / max(1, len(gs)))
    xr = style == "xray"      # x-ray: the skin disappears and the skeleton comes up behind the muscles
    lay, glow, labels = {"Layer_Skeleton": [[0, 0.34 if xr else 0.08], [D, 0.34 if xr else 0.08]], "Layer_Skin": [[0, 0.03 if xr else 0.10], [D, 0.03 if xr else 0.10]]}, [{"id": "g_skin", "layer": "Layer_Skin", "color": [0.42, 0.78, 1.0], "rim": 1.4, "power": 2.4, "fill": 0.02, "strength": [[0, 1.0], [D, 1.0]]}], []
    for g in allg:      # every group is drawn dim (a muscular figure), the named ones come forward one by one as they are spoken
        n = f"Layer_M_{g}"
        if g in named: t = 0.3 + named[g] * step; lay[n] = [[0, 0.16], [t, 0.16], [t + 0.7, 1.0], [D, 1.0]]; glow.append({"id": f"g_{g}", "layer": n, "color": [1.0, 0.3, 0.12], "rim": 1.6, "power": 2.2, "fill": 0.05, "strength": [[0, 0.0], [t, 0.0], [t + 0.8, 1.0], [D, 1.0]]})
        else: lay[n] = [[0, 0.16], [D, 0.16]]
    for g, label, *_r in gs:
        t = 0.9 + named[g] * step; labels.append({"id": f"l_{g}", "text": label, "anchor": anc(g), "offset": [0, 0, 0], "t0": round(t, 2), "t1": round(max(t + 0.5, D - 0.2), 2), "side": "right" if named[g] % 2 == 0 else "left"})
    if by_ex: labels.append({"id": "l_ex", "text": f"Worked in the {by_ex.lower()}", "anchor": anc(gs[-1][0]), "offset": [0, 0, -0.06], "t0": round(0.6 + len(gs) * step, 2), "t1": round(max(1.5, D - 0.2), 2), "side": "left"})
    spec["layers"] = lay; spec["layer_order"] = ["Layer_Skeleton"] + [f"Layer_M_{g}" for g in allg] + ["Layer_Skin"]; spec["glow"] = glow; spec["labels"] = labels; spec["highlights"] = []; spec["tints"] = {}
    if "m_union" in anchors: spec.setdefault("anchor_overrides", {})["m_union"] = {"center": anchors["m_union"]["center"]}
    if back:
        for k in spec["camera"]: k["az"] = k["az"] + 180
    ks = spec["camera"]
    if style == "orbit" and len(ks) > 1:      # the camera sweeps around the muscle across the whole clip
        base = ks[0]["az"]
        for i, k in enumerate(ks): k["az"] = round(base - 30 + 70 * i / (len(ks) - 1), 2)
    elif style == "side":      # a profile view with a slow drift
        for i, k in enumerate(ks): k["az"] = round(k["az"] + 70 + 8 * i, 2)
    spec["label_scale"] = 1.5      # the clip is shown at about 60% of the frame width: labels are drawn bigger so they read at the size they are seen
    return spec, " + ".join(x[1] for x in gs)

def clip_for(text: str, seconds: float, W: int = 1920, H: int = 1080, fps: int = 24, log=print, style: str = "push") -> Optional[dict]:
    MODEL, ANCHORS = model_paths()      # looked up now, not at import: a folder set or installed later is found
    if MODEL is None: log("[REP THEORY 3D] gym body model not found (health_cinema/bench/prep_muscles.py + build_gym_body.py)"); return None
    import math
    seconds = min(12.0, max(2.0, 2.0 * math.ceil(seconds / 2.0)))      # lengths in 2 s steps: a clip made for one video is reused by any later scene on the same muscles that is no longer than it (the clip's last frame holds)
    anchors = BM.load_anchors(ANCHORS); got = spec_for(text, seconds, anchors, style)
    if not got: return None
    spec, label = got; tmp = Path(tempfile.mkdtemp(prefix="rt3d_")); sp = tmp / "spec.json"; sp.write_text(json.dumps(spec))
    r = RJ.render_journey(sp, ANCHORS, MODEL, W, H, fps, CACHE, on_line=lambda s: None); r["label"] = label; return r

def frames_for(clip_path: str) -> list:
    """The clip as numbered JPEGs next to it (extracted once), so the compositor can pick the frame for any time."""
    import subprocess
    from . import engine as E
    d = Path(clip_path).parent / "jpg"
    if not (d.exists() and any(d.glob("f*.jpg"))):
        d.mkdir(exist_ok=True); subprocess.run([E._ff(), "-y", "-v", "error", "-i", clip_path, "-q:v", "2", str(d / "f%04d.jpg")], check=True, timeout=600)
    return sorted(str(x) for x in d.glob("f*.jpg"))

def prepare(scenes: list, log=print, max_clips: int = 12, fps: int = 24, mix: bool = False, directed: bool = False) -> dict:
    """Gives scenes about a body part their 3D clip: kind "clip3d", the clip's frames in sc["clip3d"]. Tier boards, equations, made-up data and scenes with no body part keep what they had."""
    from . import beat_art as BA
    stat = {"rendered": 0, "reused": 0, "skipped": 0, "failed": 0}; n = 0; prev3d = False
    for sc in scenes:
        txt = sc.get("muscle") or sc.get("text", ""); was3d, prev3d = prev3d, False      # the scenes CSV's muscle column, when filled, says which muscle the clip shows
        if sc.get("directed_look"):      # the scenes CSV chose this scene's look: a clip only where it asked for 3D, whatever the spacing and count rules say
            if sc.get("look") != "3d": stat["skipped"] += 1; continue
        elif directed and not sc.get("want3d"): stat["skipped"] += 1; continue      # the variety director chose which scenes get a 3D clip
        asked = bool(sc.get("directed_look"))
        if mix and was3d and region_for(txt) and not asked: sc["want_picture"] = True; stat["skipped"] += 1; continue      # mixed with Flow pictures: a 3D scene is never followed by another, the next body-part scene gets its Flow picture
        if sc["kind"] in BA.SKIP_KINDS or BA.SYNTH_RX.search(sc.get("text", "")) or not region_for(txt) or (n >= max_clips and not (directed or asked)): stat["skipped"] += 1; continue
        dur = sc["end"] - sc["start"]
        if dur < 2.0: stat["skipped"] += 1; continue
        try:
            r = clip_for(txt, dur, fps=fps, log=log, style=sc.get("cam3d", "push"))
            if not r: stat["skipped"] += 1; continue
            sc["clip3d"] = {"frames": frames_for(r["path"]), "label": r["label"], "fps": fps, "clip": r["path"]}; n += 1; prev3d = True
            stat["reused" if r["cache_hit"] else "rendered"] += 1
            sc["decisions"].append(f"3D body clip ({r['label']}): {sc['kind']} -> clip3d"); sc["was_kind"] = sc["kind"]; sc["kind"] = "clip3d"; sc["art"] = ""; sc["prop"] = ""
        except Exception as ex:
            stat["failed"] += 1; log(f"[REP THEORY 3D] {type(ex).__name__}: {ex}; that scene keeps its previous treatment")
    return stat
