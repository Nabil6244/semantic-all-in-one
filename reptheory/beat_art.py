"""A picture for every beat, in the reference's manga style, generated from the beat's own narration through the app's Flow image workflow and cached in the Rep Theory library.
The prompt is the library's character + style text plus the beat's words, so the same lean trainee appears doing or showing what is being said; for a beat about tissue or objects the picture is an
illustration of that instead. The id is a hash of the prompt: re-rendering a script (or any script with the same beat) reuses the picture, nothing is generated twice.
Synthetic / made-up data is never illustrated (a picture would make it look real), and tier boards and equations keep their own graphics."""
from __future__ import annotations
import hashlib, re, tempfile, time
from pathlib import Path
from typing import Dict, List, Optional

from . import art as A, library as L

SKIP_KINDS = {"tier", "equation", "stat", "steps", "versus", "takeaway"}      # these keep their own graphic
REPEAT_KINDS = {"anatomy", "prop", "hold", "pose", "trainee"}      # a stored picture is kept for the first scene, but never shown again in the next scene: that scene gets its own picture
SYNTH_RX = re.compile(r"\b(synthetic|made[- ]up|fictional|invented|test study)\b", re.I)
TISSUE_RX = re.compile(r"\b(muscle|muscles|tendon|tendons|bone|bones|fibre|fibres|fiber|fibers|ligament|joint|nerve|blood flow|tissue)\b", re.I)

def prompt_for(text: str) -> str:
    """Flow prompt for one beat: what the narration says at this moment, drawn in the reference style."""
    text = re.sub(r"\s+", " ", text).strip().rstrip(".")
    if TISSUE_RX.search(text) and not re.search(r"\b(hold|hang|pinch|squeeze|stand|lift|push|pull|squat|plank|rotate)\b", text, re.I):
        return (f"A clear anatomical illustration that shows what this sentence of a fitness explainer is about: \"{text}\". Show the relevant muscles, tendons or bones of the body part concerned, "
                f"{A.REAL_STYLE}.")
    return (f"A single scene from a fitness explainer video, illustrating exactly this narration: \"{text}\". Show {A.CHARACTER}, doing or demonstrating what is described, with any named object or "
            f"equipment drawn clearly, the whole action visible. {A.STYLE}.")

def art_id(prompt: str) -> str: return "beat_" + hashlib.sha1(prompt.encode("utf-8")).hexdigest()[:12]

def eligible(sc: dict) -> bool:
    return sc["kind"] not in SKIP_KINDS and sc["kind"] != "clip3d" and not SYNTH_RX.search(sc.get("text", "")) and bool(sc.get("text", "").strip())

def _same(a, b) -> bool: return " ".join(str(a or "").split()).lower() == " ".join(str(b or "").split()).lower()

def prepare(scenes: List[dict], mode: str = "agent", account_ids=None, log=print, settings: Optional[dict] = None, generate_missing: bool = True, directed: bool = False,
            collect: Optional[list] = None, chosen: Optional[Dict[int, dict]] = None) -> Dict[str, int]:
    """Gives every eligible scene its picture: kind becomes "illus", art the cached id. A scene whose picture could not be had keeps its previous treatment (and says so in `decisions`).
    collect (Generate scenes): nothing is generated; each scene that wants a picture is appended as {no, text, prompt, cached} for the Visuals tab.
    chosen (Render): {scene no: the Visuals tab's finished file record}; that file is the scene's picture, whatever made it."""
    todo: Dict[str, str] = {}; stat = {"reused": 0, "generated": 0, "failed": 0, "skipped": 0, "chosen": 0}
    prev = None
    for sc in scenes:
        if directed and sc.get("look") != "flow": stat["skipped"] += 1; continue      # the variety director chose which scenes get a Flow picture
        sig = (sc["kind"], sc.get("art"), sc.get("prop")); repeat = sc["kind"] in REPEAT_KINDS and prev == sig; prev = sig
        if sc["kind"] in REPEAT_KINDS and not repeat and not sc.get("want_picture") and not directed: stat["skipped"] += 1; continue
        if not eligible(sc): stat["skipped"] += 1; continue
        p = prompt_for(sc["text"]); i = art_id(p); sc["_illus"] = (i, p)
        if collect is not None: collect.append({"no": sc["no"], "text": sc["text"], "prompt": p, "cached": (L.find(i) or {}).get("path")}); continue
        pick = (chosen or {}).get(sc["no"])
        if pick and pick.get("ok") and _same(pick.get("narration"), sc["text"]):
            same = str(pick.get("source")) in ("flow_image", "image") and _same(pick.get("query"), p)      # the picture made for this prompt: kept under its own id, reused by other scripts
            pid = i if same else "pick_" + hashlib.sha1(f"{p}|{pick['path']}|{Path(pick['path']).stat().st_size}".encode("utf-8")).hexdigest()[:12]
            if not L.find(pid): L.register(pick["path"], id=pid, kind="scene", subject=p[:120], prompt=p, source="flow" if same else "supplied", notes="from the Visuals tab")
            sc["_illus"] = (pid, p); stat["chosen"] += 1; continue
        if L.find(i): stat["reused"] += 1
        elif generate_missing: todo[i] = p
    if todo:
        from providers.base import SceneRow
        from providers.flow.engine_manager import FlowEngineManager
        from providers.flow.provider import FlowProvider
        mgr = FlowEngineManager(log=log); fs = {"model": "GEM_PIX_2", "aspectRatio": "IMAGE_ASPECT_RATIO_LANDSCAPE", "generationMode": mode}; fs.update(settings or {})
        prov = FlowProvider(mgr, media_kind="image", account_ids=account_ids, flow_settings=fs); ids = list(todo)
        rows = [SceneRow(scene_number=str(n + 1), script_segment=todo[i], asset_type="image", prompt=todo[i]) for n, i in enumerate(ids)]
        log(f"[REP THEORY ART] requesting {len(rows)} Flow image(s) for this script (mode {mode})")
        res = prov.resolve_batch(rows, Path(tempfile.mkdtemp(prefix="rt_beat_")), log=log)
        for n, i in enumerate(ids):
            r = res.get(str(n + 1)); path = getattr(r, "path", None) if r is not None else None
            if path and Path(path).is_file(): L.register(path, id=i, kind="scene", subject=todo[i][:120], prompt=todo[i], source="flow", notes=f"flow {mode} {time.strftime('%Y-%m-%d')}"); stat["generated"] += 1
            else: stat["failed"] += 1; log(f"[REP THEORY ART] {i}: no image returned ({getattr(r, 'error', None)}); that scene keeps its text treatment")
    for sc in scenes:
        got = sc.pop("_illus", None)
        if got and L.find(got[0]): sc["decisions"].append(f"picture from the narration: {sc['kind']} -> illus"); sc["was_kind"] = sc["kind"]; sc["kind"] = "illus"; sc["art"] = got[0]; sc["prop"] = ""
    return stat
