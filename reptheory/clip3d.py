"""3D body clips for Rep Theory: the Health Cinema body model (skin, muscle, skeleton, organs; Z-Anatomy, already in ~/HealthCinemaTools/bench) drawn by its Three.js renderer, with the camera on the
body part the narration is about and that part's muscle layer glowing. The region comes from the beat's own words, so any script gets a clip for whatever it names; a beat that names no body part gets none.
Clips are cached by Health Cinema's render cache (spec + model + code hash), so the same region/view/length is rendered once."""
from __future__ import annotations
import json, re, tempfile
from pathlib import Path
from typing import Optional, Tuple

from health_cinema import bodymap as BM, render_journey as RJ

BENCH = Path.home() / "HealthCinemaTools" / "bench"
MODEL, ANCHORS = BENCH / "body.glb", BENCH / "anchors_body.json"
CACHE = Path.home() / "HealthCinemaTools" / "rep_theory_clips"
# (regex on the narration, anchor, camera scale, back view?, label). First match wins; more specific first.
REGIONS = (
    (r"\b(forearms?|wrists?|grip|fingers?|hands?)\b", "forearm_r", "close", False, "Forearm"),
    (r"\b(biceps?|triceps?|upper arms?|arms?|elbows?)\b", "upper_arm_r", "close", False, "Arm"),
    (r"\b(lats?|latissimus|scapula\w*|shoulder blades?|trapezius|traps|upper back|back)\b", "spine", "region", True, "Back"),
    (r"\b(shoulders?|delts?|deltoids?)\b", "shoulder_r", "region", False, "Shoulder"),
    (r"\b(chest|pecs?|pectorals?)\b", "chest", "region", False, "Chest"),
    (r"\b(core|abs|abdominals?|abdomen|belly|plank)\b", "abdomen", "region", False, "Core"),
    (r"\b(glutes?|hips?|pelvis)\b", "pelvis", "region", True, "Glutes"),
    (r"\b(quads?|quadriceps|thighs?|hamstrings?|squats?|legs?)\b", "thigh_r", "region", False, "Thigh"),
    (r"\b(calf|calves|shins?|ankles?)\b", "shin_r", "close", False, "Calf"),
    (r"\b(spine|neck)\b", "neck", "region", True, "Neck"),
    (r"\b(push[- ]?ups?|pull[- ]?ups?|whole body|full body|body)\b", "body", "whole", False, ""),
)

def region_for(text: str) -> Optional[Tuple[str, str, bool, str]]:
    for rx, anchor, scale, back, label in REGIONS:
        if re.search(rx, text, re.I): return anchor, scale, back, label
    return None

def spec_for(text: str, seconds: float, anchors: dict):
    got = region_for(text)
    if not got: return None
    anchor, scale, back, label = got
    if anchor not in anchors: return None
    beat = {"t0": 0.0, "t1": float(seconds), "text": text, "region": anchor, "scale": scale, "focus": "body", "effect": "none", "label": label, "card_type": "none", "card_ref": "", "card_prompt": "", "card_at": None}
    spec = BM.build_spec([beat], anchors, float(seconds), cards_enabled=False)
    D = float(seconds)
    # the model's Layer_Muscle holds the chest muscles only (pectorals, serratus, intercostals, diaphragm): for the chest and core that layer is the hero; for every other region the skeleton and joints are
    # real anatomy and the region is marked on them, so the clip says "this body part", not "this muscle" (reported as approximate by the caller)
    muscle = anchor in ("chest", "abdomen")
    spec["layers"] = {"Layer_Skin": [[0, 0.18], [D, 0.18]], "Layer_Muscle": [[0, 0.62 if muscle else 0.0], [D, 0.62 if muscle else 0.0]], "Layer_Skeleton": [[0, 0.1 if muscle else 0.34], [D, 0.1 if muscle else 0.34]]}
    spec["layer_order"] = ["Layer_Muscle", "Layer_Skeleton", "Layer_Skin"]; spec["tints"] = {"Layer_Skin": [[0, [0.46, 0.72, 1.0]], [D, [0.46, 0.72, 1.0]]]}
    spec["glow"] = [{"id": "g_skin", "layer": "Layer_Skin", "color": [0.42, 0.78, 1.0], "rim": 1.5, "power": 2.3, "fill": 0.03, "strength": [[0, 1.0], [D, 1.0]]},
                    {"id": "g_muscle", "layer": "Layer_Muscle", "color": [1.0, 0.42, 0.22], "rim": 1.2, "power": 2.0, "fill": 0.12, "strength": [[0, 0.0], [0.6, 1.0], [D, 1.0]]}]
    if back:
        for k in spec["camera"]: k["az"] = k["az"] + 180
    return spec, label

def clip_for(text: str, seconds: float, W: int = 1920, H: int = 1080, fps: int = 24, log=print) -> Optional[dict]:
    if not MODEL.exists() or not ANCHORS.exists(): log("[REP THEORY 3D] body model not found"); return None
    anchors = BM.load_anchors(ANCHORS); got = spec_for(text, round(seconds, 1), anchors)
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

def prepare(scenes: list, log=print, max_clips: int = 12, fps: int = 24) -> dict:
    """Gives scenes about a body part their 3D clip: kind "clip3d", the clip's frames in sc["clip3d"]. Tier boards, equations, made-up data and scenes with no body part keep what they had."""
    from . import beat_art as BA
    stat = {"rendered": 0, "reused": 0, "skipped": 0, "failed": 0}; n = 0
    for sc in scenes:
        txt = sc.get("text", "")
        if sc["kind"] in BA.SKIP_KINDS or BA.SYNTH_RX.search(txt) or not region_for(txt) or n >= max_clips: stat["skipped"] += 1; continue
        dur = sc["end"] - sc["start"]
        if dur < 2.0: stat["skipped"] += 1; continue
        try:
            r = clip_for(txt, dur, fps=fps, log=log)
            if not r: stat["skipped"] += 1; continue
            sc["clip3d"] = {"frames": frames_for(r["path"]), "label": r["label"], "fps": fps, "clip": r["path"]}; n += 1
            stat["reused" if r["cache_hit"] else "rendered"] += 1
            sc["decisions"].append(f"3D body clip ({r['label']}): {sc['kind']} -> clip3d"); sc["was_kind"] = sc["kind"]; sc["kind"] = "clip3d"; sc["art"] = ""; sc["prop"] = ""
        except Exception as ex:
            stat["failed"] += 1; log(f"[REP THEORY 3D] {type(ex).__name__}: {ex}; that scene keeps its previous treatment")
    return stat
