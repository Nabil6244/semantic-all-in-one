"""The Health Cinema 3D library: which body part lives in which model, and a generic journey builder so a new organ is DATA, not a new hand-made template.

  model  = a GLB with Layer_* groups + an anchors file (named boxes), prepared once from Z-Anatomy (health_cinema/bench/prep_*.py)
  organ  = an entry in ORGANS: its model, the anchor that frames it, the layer(s) that ARE the organ, the layers that give context, and its labels
  shot   = orbit | zoom | peel | isolate | cutaway: reusable camera + layer behaviours applied to any organ
Template ids: the four hand-authored journeys (heart_journey, chest_journey, brain_journey, eye_journey) and generated ones `auto:<organ>:<shot>`.
Nothing here invents anatomy: an organ whose model/anchor/layer is missing from the prepared files simply has no template (the planner then uses footage)."""
from __future__ import annotations
import json, math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

MODEL_FILES = {"chest": ("chest.glb", "anchors.json"), "head": ("head.glb", "anchors_head.json"), "abdomen": ("abdomen.glb", "anchors_abdomen.json"), "msk": ("msk.glb", "anchors_msk.json")}
AUTHORED = {"heart": ("heart_journey", "chest"), "lungs": ("chest_journey", "chest"), "brain": ("brain_journey", "head"), "eye": ("eye_journey", "head")}
SHOTS = ("orbit", "zoom", "peel", "isolate", "cutaway", "fatty", "inflamed")      # fatty / inflamed: the organ changes colour as the condition develops (illustration)
DURATION = 12.0
FILL_MAX = 0.84      # the tightest an organ is framed: leaves a margin all round, so a close-up never crops it

@dataclass(frozen=True)
class Organ:
    model: str
    anchor: str                          # anchor that frames the organ
    hero: Tuple[str, ...]                # layers that are the organ itself
    context: Tuple[str, ...] = ()        # layers shown around it, faded out as the shot reveals the organ
    labels: Tuple[tuple, ...] = ()      # (text, anchor) or (text, anchor, (dx, dz)) pairs; skipped when the anchor is not in the model
    aliases: Tuple[str, ...] = ()
    az: float = 0.0                      # preferred viewing azimuth (deg)
    ctx_floor: float = 0.0               # context layers never fade below this (a joint is read against its bones)
    frame: Tuple[str, ...] = ()          # tighter boxes to frame and label the organ by, best first, when the model has them (the stomach's own box, not stomach + oesophagus)

ORGANS: Dict[str, Organ] = {
    "liver": Organ("abdomen", "liver_only", ("Layer_Liver",), ("Layer_Skeleton", "Layer_Stomach", "Layer_Intestines"), (("Liver", "liver_only"), ("Gallbladder", "gallbladder")), ("fatty liver", "hepatic", "cirrhosis")),
    "gallbladder": Organ("abdomen", "gallbladder", ("Layer_Liver",), ("Layer_Skeleton",), (("Gallbladder", "gallbladder"),), ("gallstones", "bile")),
    "pancreas": Organ("abdomen", "pancreas", ("Layer_Pancreas",), ("Layer_Skeleton", "Layer_Stomach", "Layer_Intestines", "Layer_Liver"), (("Pancreas", "pancreas"),), ("insulin", "diabetes", "blood sugar", "glucose")),
    "stomach": Organ("abdomen", "stomach", ("Layer_Stomach",), ("Layer_Skeleton", "Layer_Intestines", "Layer_Liver"), (("Stomach", "stomach"),), ("gastric", "digestion", "acid reflux", "ulcer"),
                     frame=("obj:Stomach.001", "obj:Stomach")),      # the 'stomach' anchor also holds the oesophagus up to the neck
    "intestines": Organ("abdomen", "intestines", ("Layer_Intestines",), ("Layer_Skeleton", "Layer_Stomach", "Layer_Liver"), (("Intestines", "intestines"),), ("gut", "bowel", "colon", "digestive", "microbiome", "small intestine", "large intestine")),
    "spleen": Organ("abdomen", "spleen", ("Layer_Spleen",), ("Layer_Skeleton", "Layer_Stomach"), (("Spleen", "spleen"),), ("immune",)),
    "kidney": Organ("abdomen", "kidneys", ("Layer_Urinary",), ("Layer_Skeleton", "Layer_Intestines", "Layer_Liver", "Layer_Bladder"), (("Right kidney", "kidney_r"), ("Left kidney", "kidney_l")),
                    ("kidneys", "renal", "kidney stones", "kidney disease", "dialysis", "urinary system", "ureter"), az=0),      # BodyParts3D kidneys (CC BY 4.0), prep_kidney.py: the Z-Anatomy kidney is CC BY-NC
    "bladder": Organ("abdomen", "bladder", ("Layer_Bladder",), ("Layer_Skeleton",), (("Bladder", "bladder"),), ("urinary",)),
    "abdomen": Organ("abdomen", "abdomen", ("Layer_Liver", "Layer_Stomach", "Layer_Intestines", "Layer_Pancreas", "Layer_Spleen"), ("Layer_Skeleton",), (("Liver", "liver_only"), ("Stomach", "stomach"), ("Pancreas", "pancreas")), ("digestive system", "digestive tract", "abdominal")),
    "knee": Organ("msk", "knee_l", ("Layer_Menisci", "Layer_Ligaments"), ("Layer_Skeleton",), (("Meniscus", "knee_l", (-0.025, -0.005)), ("Cruciate ligaments", "knee_l", (0.025, 0.012))), ("kneecap", "knee joint", "knees", "acl", "meniscus", "osteoarthritis"), az=-25, ctx_floor=0.32),
    "hip": Organ("msk", "hip_l", ("Layer_Ligaments",), ("Layer_Skeleton",), (("Hip joint", "hip_l"),), ("hip joint", "hips", "hip replacement"), az=-25, ctx_floor=0.32),
    "shoulder": Organ("msk", "shoulder_l", ("Layer_Ligaments",), ("Layer_Skeleton",), (("Shoulder joint", "shoulder_l"),), ("rotator cuff", "shoulders"), az=-20, ctx_floor=0.32),
    "elbow": Organ("msk", "elbow_l", ("Layer_Ligaments",), ("Layer_Skeleton",), (("Elbow joint", "elbow_l"),), ("elbows",), ctx_floor=0.32),
    "spine": Organ("msk", "spine", ("Layer_Discs",), ("Layer_Skeleton",), (("Spinal discs", "discs"),), ("back pain", "vertebrae", "vertebral column", "disc", "backbone", "lumbar", "sciatica"), ctx_floor=0.32),
    "skeleton": Organ("msk", "skeleton", ("Layer_Skeleton",), (), (), ("bones", "bone density", "osteoporosis", "skeletal")),
}

@dataclass(frozen=True)
class Micro:
    """A procedural illustration (health_cinema/threejs/procedural.js): no model, always available where the Three.js renderer is."""
    kind: str
    tracks: Tuple[Tuple[str, tuple], ...]            # (track name, keyframes as fractions of the duration -> value)
    labels: Tuple[tuple, ...]                        # (text, anchor, t0 fraction)
    target: str
    dist: float
    aliases: Tuple[str, ...]
    params: tuple = ()
    auto: Tuple[str, ...] = ()                       # aliases specific enough to pick this scene from narration without a CSV row (everything else needs `organ` in the CSV)

MICRO: Dict[str, Micro] = {
    "blood_flow": Micro("blood_flow", (("flow", ((0, 1.0), (1, 1.0))),), (("Artery wall", "vessel_wall", 0.25), ("Blood flow", "flow_in", 0.45)), "origin", 3.4, ("blood flow", "bloodstream", "red blood cells", "blood cells", "circulation", "blood vessels")),
    "plaque": Micro("plaque", (("flow", ((0, 1.0), (1, 1.0))), ("plaque", ((0, 0.0), (0.12, 0.0), (0.8, 1.0), (1, 1.0)))), (("Fatty plaque builds up", "plaque_site", 0.5), ("Narrowed channel", "origin", 0.78)), "plaque_site", 3.4,
                    ("plaque", "atherosclerosis", "clogged arteries", "narrowed arteries", "cholesterol", "hardening of the arteries", "blocked artery"), auto=("atherosclerosis", "plaque", "clogged arteries", "narrowed arteries", "hardening of the arteries")),
    "clot": Micro("clot", (("flow", ((0, 1.0), (1, 1.0))), ("clot", ((0, 0.0), (0.15, 0.0), (0.75, 1.0), (1, 1.0)))), (("Blood clot forms", "clot_site", 0.5), ("Flow blocked", "flow_in", 0.82)), "origin", 3.0,
             ("blood clot", "clots", "thrombosis", "thrombus", "embolism", "ischemic stroke"), auto=("blood clot", "thrombosis", "thrombus")),
    "cell": Micro("cell", (("lipid", ((0, 0.0), (1, 0.0))),), (("Nucleus", "nucleus", 0.3), ("Cell membrane", "membrane", 0.55)), "cell", 3.3, ("cell", "cells", "mitochondria", "cell membrane", "cellular")),
    "fatty_cell": Micro("cell", (("lipid", ((0, 0.0), (0.15, 0.0), (0.85, 1.0), (1, 1.0))),), (("Nucleus", "nucleus", 0.12, 0.45), ("Fat droplets", "droplets", 0.62)), "cell", 3.3, ("fat droplets", "lipid droplets", "fatty cells", "hepatocytes"), auto=("fat droplets", "lipid droplets")),
}

# How each generated organ moves (spec `pulse` / `flow`, see journey.pulse_scales and threejs/page.js), so no organ scene is a still model whatever the video is about.
# Kinds: breath = rides the breathing (abdominal organs move with the diaphragm); perfusion = a blood wave through the organ once per heartbeat;
# peristalsis = a slow digestive wave over the gut wall; load = a joint's soft parts compress a little with each step (walking cadence).
# Each entry: (kind, layers or None for the organ's own layers). These are illustrations of real rhythms (resting breath and heart rate, walking pace).
LIFE: Dict[str, Tuple[Tuple[str, Optional[Tuple[str, ...]]], ...]] = {
    "liver": (("breath", None), ("perfusion", None)), "gallbladder": (("breath", None),), "pancreas": (("breath", None), ("perfusion", None)),
    "stomach": (("breath", None), ("peristalsis", None)), "intestines": (("breath", None), ("peristalsis", None)), "spleen": (("breath", None), ("perfusion", None)),
    "kidney": (("breath", None), ("perfusion", None)), "bladder": (("breath", None),),
    "abdomen": (("breath", None), ("peristalsis", ("Layer_Stomach", "Layer_Intestines")), ("perfusion", ("Layer_Liver", "Layer_Spleen"))),
    "knee": (("load", None),), "hip": (("load", None),), "shoulder": (("load", None),), "elbow": (("load", None),), "spine": (("load", None),),
}
BREATH, HEART, STEPS = 14, 64, 52      # per minute: resting breath, resting heart, a slow walking step on one leg

def life_for(organ: str, anchor: str, hero: List[str], D: float) -> dict:
    """The organ's `pulse` and `flow` spec entries (empty for an organ with no rhythm, such as the whole skeleton)."""
    pulse, flow = [], []
    for kind, only in LIFE.get(organ, ()):
        ls = [l for l in (only or hero) if l in hero]
        if not ls: continue
        if kind == "breath": pulse.append({"layers": ls, "anchor": anchor, "rate": BREATH, "amount": 0.014, "shape": "breath"})
        elif kind == "load": pulse.append({"layers": ls, "anchor": anchor, "rate": STEPS, "amount": 0.03, "shape": "beat", "per_object": True})      # each meniscus, ligament, disc about its own centre: a layer holds both sides
        else:
            for l in ls:      # one wave per layer (page.js keeps one wave per layer)
                cfg = {"perfusion": {"rate": HEART, "speed": 0.07, "sharp": 10, "reach": 0.1, "inner": 0.01, "color": [1.0, 0.45, 0.35], "gain": 0.35},      # a ripple a few cm apart, never a flush of the whole organ
                       "peristalsis": {"rate": 8, "speed": 0.03, "sharp": 3, "reach": 0.3, "color": [1.0, 0.7, 0.6], "gain": 0.45}}[kind]
                flow.append({"id": f"{kind}_{l}", "layer": l, "origin": anchor, **{k: v for k, v in cfg.items() if k != "gain"},
                             "strength": [[0, 0.0], [1.4, 0.0], [2.6, cfg["gain"]], [D, cfg["gain"]]]})
    return {"pulse": pulse, "flow": flow}

# colours of the organs in the prepared models, so a pathology shot can move them toward a condition (key = layer or "layer:object")
BASE_TINT = {"liver": ("Layer_Liver:Liver", (0.50, 0.14, 0.10)), "pancreas": ("Layer_Pancreas", (0.90, 0.70, 0.45)), "stomach": ("Layer_Stomach:Stomach", (0.86, 0.46, 0.42)),
             "intestines": ("Layer_Intestines", (0.88, 0.58, 0.52)), "spleen": ("Layer_Spleen", (0.45, 0.10, 0.22))}
CONDITION = {"fatty": ((0.90, 0.72, 0.32), "Fat builds up", ("liver", "pancreas")), "inflamed": ((0.80, 0.10, 0.08), "Inflamed tissue", tuple(BASE_TINT))}

def organ_key(name: str) -> Optional[str]:
    """'knee', 'knees', 'fatty liver', 'bone density' -> the library key, or None."""
    n = (name or "").strip().lower()
    if n in AUTHORED or n in ORGANS or n in MICRO: return n
    from . import conditions as CN
    if n.replace(" ", "_") in CN.CONDITIONS: return n.replace(" ", "_")      # a condition's own name beats another entry's extra word (insulin -> the insulin scene, not the pancreas)
    for k, o in ORGANS.items():
        if n in o.aliases: return k
    for k, m in MICRO.items():
        if n in m.aliases: return k
    return CN.key_for(n)      # condition scenes (cellulitis, asthma, osteoporosis ...): drawn fresh per video

def find_organ(text: str) -> Optional[str]:
    """The library body part or pathology a sentence is about (longest matching name or alias, whole words), or None. Procedural scenes (plaque, clot ...) are
    only picked on their specific `auto` phrases here; any other wording needs an explicit `organ` in the scenes CSV."""
    import re
    low = (text or "").lower(); best, blen = None, 0
    from . import conditions as CN
    for k, o in list(CN.CONDITIONS.items()) + list(ORGANS.items()) + list(MICRO.items()):      # a condition scene wins a tie: it shows what the sentence says happens
        for name in ((k.replace("_", " "),) + o.aliases) if k in ORGANS else o.auto:
            if len(name) > blen and re.search(r"\b" + re.escape(name) + r"s?\b", low): best, blen = k, len(name)
    return best

def model_of(template: str) -> Optional[str]:
    """The model kind a template id needs (chest/head/abdomen/msk)."""
    for tpl, model in AUTHORED.values():
        if template == tpl: return model
    if template.startswith("body:"): return "body"
    if template.startswith("auto:"):
        o = ORGANS.get(template.split(":")[1]); return o.model if o else None
    if template.startswith("micro:"): return "micro" if template.split(":")[1] in MICRO else None
    if template.startswith("cond:"):
        from . import conditions as CN
        return "micro" if template.split(":")[1] in CN.CONDITIONS else None      # no model file: the page draws it (shares the procedural scenes' anchors file)
    return None

def parse(template: str) -> Tuple[str, str]:
    p = template.split(":"); return p[1], (p[2] if len(p) > 2 else "peel")

def pick_shot(text: str, organ: str) -> str:
    """A camera move that suits the narration (rules, no model): opening/overview -> zoom, 'inside/layers/beneath' -> peel, damage/disease words -> isolate."""
    t = (text or "").lower()
    if organ in ("liver", "pancreas") and any(w in t for w in ("fat ", "fatty", "fat builds", "fat build")): return "fatty"
    if organ in BASE_TINT and "inflam" in t: return "inflamed"
    if organ not in ORGANS: return "orbit"
    if any(w in t for w in ("damage", "scar", "inflam", "wear", "worn", "disease", "blocked", "build up", "builds up", "fat ", "fatty", "degenerat")): return "isolate"
    if any(w in t for w in ("inside", "layer", "beneath", "under the", "deep", "within")): return "peel"
    if any(w in t for w in ("where", "located", "sits", "begins", "overview", "whole")): return "zoom"
    return "orbit" if ORGANS[organ].context == () else "peel"

def template_for(organ: str, ready: Callable[[str], bool], shot: Optional[str] = None, text: str = "") -> Optional[str]:
    """Template id for a body part when its model is installed (`ready(template)`), else None. Hand-authored journeys win for heart/lungs/brain/eye."""
    k = organ_key(organ)
    if not k: return None
    if k in MICRO: tpl = f"micro:{k}:{shot if shot in ('orbit', 'zoom') else 'orbit'}"; return tpl if ready(tpl) else None
    from . import conditions as CN
    if k in CN.CONDITIONS: tpl = f"cond:{k}:{shot if shot in ('orbit', 'zoom') else 'orbit'}"; return tpl if ready(tpl) else None
    if k in AUTHORED: tpl = AUTHORED[k][0]; return tpl if ready(tpl) else None
    sh = shot if shot in SHOTS else pick_shot(text, k); tpl = f"auto:{k}:{sh}"
    return tpl if ready(tpl) else None

def available(ready: Callable[[str], bool]) -> Dict[str, List[str]]:
    """organ -> shots that can be rendered right now (for reports and for the planner's prompts)."""
    out: Dict[str, List[str]] = {}
    from . import conditions as CN
    for k in list(AUTHORED) + list(ORGANS) + list(MICRO) + list(CN.CONDITIONS):
        t = AUTHORED[k][0] if k in AUTHORED else f"micro:{k}:orbit" if k in MICRO else f"cond:{k}:orbit" if k in CN.CONDITIONS else f"auto:{k}:orbit"
        if ready(t): out[k] = [AUTHORED[k][0]] if k in AUTHORED else ["orbit", "zoom"] if k in MICRO or k in CN.CONDITIONS else [x for x in SHOTS if x not in ("cutaway", "fatty", "inflamed") or (x in CONDITION and k in CONDITION[x][2])]      # cutaway is accepted in a CSV but is a peel until a cut layer is prepared
    return out

def _diag(b: dict) -> float: return math.sqrt(sum((b["max"][i] - b["min"][i]) ** 2 for i in range(3)))

def apply_variant(spec: dict, variant: int) -> dict:
    """A repeat of the same template in one video must not look like the same clip: the camera comes in from a different side and height. (Procedural scenes also
    re-seed their contents, see procedural.js.) variant 0 leaves the spec untouched, so first uses keep their cached renders."""
    if not variant: return spec
    off = [0, 32, -32, 58, -58][variant % 5]; spec["id"] = f"{spec.get('id', '')}_var{variant}"
    for c in spec["camera"]: c["az"] = c["az"] + off; c["el"] = c["el"] + 2 * (variant % 3)
    if "procedural" in spec: spec["procedural"]["variant"] = variant
    return spec

def _build_micro(template: str, anchors_path: str) -> dict:
    _, key, shot = (template.split(":") + ["orbit"])[:3]; m = MICRO[key]
    A = json.loads(Path(anchors_path).read_text(encoding="utf-8"))["anchors"]
    if m.target not in A: raise KeyError(f"no '{m.target}' anchor for {key}")
    D = DURATION; fov = 30.0; d = m.dist
    cam = [(0, d * 1.15, -30, 8), (D * 0.5, d, -6, 10), (D, d * 0.82, 22, 8)] if shot != "zoom" else [(0, d * 1.5, -12, 8), (D, d * 0.7, 6, 10)]
    tracks = {n: [[round(t * D, 2), v] for t, v in keys] for n, keys in m.tracks}
    if shot == "zoom" and key in ("plaque", "clot"):      # the second look at a condition starts from an advanced stage (a story's "later" beat), not from nothing
        n = "plaque" if key == "plaque" else "clot"; tracks[n] = [[0.0, 0.65], [round(D * 0.9, 2), 1.0], [D, 1.0]]
    labels = [{"id": f"l{i}", "text": text, "anchor": an, "offset": [0, 0, 0], "t0": round(D * lb[2], 2), "t1": round(D * lb[3], 2) if len(lb) > 3 else round(D - 0.6, 2), "side": "right" if i % 2 == 0 else "left"} for i, lb in enumerate(m.labels) for text, an in [lb[:2]] if an in A]
    return {"id": f"{template}_v1", "profile": "medical_cinema", "duration": D, "background": [0.012, 0.016, 0.03], "no_model": True, "camera": [{"t": round(t, 2), "target": m.target, "dist": round(dd, 3), "az": az, "el": el, "fov": fov} for t, dd, az, el in cam],
            "layers": {}, "layer_order": [], "prepass_always": [], "highlights": [], "glow": [], "bloom": {"strength": 0.3, "radius": 0.5, "threshold": 1.0}, "labels": labels, "exposure": 0.85, "theme": "cell" if m.kind == "cell" else "blood", "fog_density": 0.35,
            "tracks": tracks, "procedural": {"kind": m.kind, "radius": 0.5, "length": 8, "illustration": "Conceptual illustration, not to scale."}}

def build_spec(template: str, anchors_path: str) -> dict:
    if template.startswith("cond:"):
        from . import conditions as CN
        return CN.build_spec(template)
    if template.startswith("micro:"): return _build_micro(template, anchors_path)
    """A journey spec (same format as templates/*.json) for `auto:<organ>:<shot>` from the model's anchors file. Distances come from the organ's own size."""
    organ, shot = parse(template); o = ORGANS[organ]
    data = json.loads(Path(anchors_path).read_text(encoding="utf-8")); A, layers = data["anchors"], data["layers"]
    if o.anchor not in A: raise KeyError(f"model has no '{o.anchor}' anchor for {organ}")
    at = next((x for x in o.frame if x in A), o.anchor)      # the box the camera frames and the labels point at
    hero = [l for l in o.hero if l in layers]; ctx = [l for l in o.context if l in layers]
    if not hero: raise KeyError(f"model has none of the layers {o.hero} for {organ}")
    D = DURATION; fov = 30.0; a0 = o.az
    cond = shot if shot in CONDITION and organ in CONDITION[shot][2] and organ in BASE_TINT else None
    if shot == "cutaway" or shot in ("fatty", "inflamed"): shot = "peel" if shot == "cutaway" or not cond else "isolate"
    # how much of the frame the organ fills (its larger screen side), measured through the projection when the camera is placed (journey.fit_dist):
    # a wide opening that shows the organ in its surroundings, ending on a close-up that never crops it. Without context layers the opening is already close.
    w0 = 0.46 if ctx else 0.62
    cam = {"orbit": [(0, w0, a0 - 38, 10), (D * 0.5, 0.70, a0, 12), (D, FILL_MAX, a0 + 36, 9)],
           "zoom": [(0, w0 * 0.85, a0 - 10, 8), (D * 0.45, 0.60, a0 + 6, 10), (D, FILL_MAX, a0 + 12, 8)],
           "peel": [(0, w0 + 0.06, a0 - 22, 9), (D * 0.4, 0.68, a0 - 4, 10), (D, FILL_MAX - 0.04, a0 + 24, 8)],
           "isolate": [(0, 0.60, a0 - 28, 10), (D * 0.55, 0.78, a0 + 4, 11), (D, FILL_MAX, a0 + 30, 9)]}[shot]
    camera = [{"t": round(t, 2), "target": at, "fill": f, "az": az, "el": el, "fov": fov} for t, f, az, el in cam]
    la: Dict[str, list] = {}
    for h in hero: la[h] = [[0, 0.0], [0.9, 1.0], [D, 1.0]]
    for c in ctx:
        f = o.ctx_floor
        la[c] = {"orbit": [[0, max(0.30, f)], [D, max(0.10, f)]], "zoom": [[0, 0.65], [D * 0.5, max(0.35, f)], [D, max(0.12, f)]], "peel": [[0, 0.9], [D * 0.18, 0.9], [D * 0.5, f], [D, f]],
                 "isolate": [[0, f], [1.2, max(0.12, f)], [D, max(0.12, f)]]}[shot]
    glow = [{"id": f"g_{h}", "layer": h, "color": [0.72, 0.86, 1.0], "rim": 0.9, "power": 2.2, "fill": 0.0, "strength": [[0, 0], [1.4, 1.0], [D, 1.0]]} for h in hero]
    named = [(x[0], at if x[1] == o.anchor else x[1]) + tuple(x[2:]) for x in o.labels]      # a label on the organ's anchor points at its framing box
    labels = [{"id": f"l{i}", "text": x[0], "anchor": x[1], "offset": [(x[2][0] if len(x) > 2 else 0.0), -(A[x[1]]["max"][1] - A[x[1]]["min"][1]) / 2 - 0.004, (x[2][1] if len(x) > 2 else 0.0)],
               "t0": round(3.0 + 1.2 * i, 2), "t1": round(D - 0.8, 2), "side": "right" if i % 2 == 0 else "left", "layer": hero[min(i, len(hero) - 1)]} for i, x in enumerate([x for x in named if x[1] in A])]
    tints = {}
    if cond:      # the organ drifts from its healthy colour toward the condition's, with a label when the change is visible
        key, base = BASE_TINT[organ]; target, text, _ = CONDITION[cond]
        tints[key] = [[0, list(base)], [2.0, list(base)], [round(D * 0.78, 2), list(target)], [D, list(target)]]
        labels = [{"id": "cond", "text": text, "anchor": at, "offset": [-(A[at]["max"][0] - A[at]["min"][0]) * 0.12, -(A[at]["max"][1] - A[at]["min"][1]) / 2 - 0.004, (A[at]["max"][2] - A[at]["min"][2]) * 0.1], "t0": round(D * 0.5, 2), "t1": round(D - 0.6, 2), "side": "right", "layer": hero[0]}]
    return {"id": f"{template}_v1", "profile": "medical_cinema", "duration": D, "background": [0.012, 0.016, 0.03], "camera": camera, "layers": la, "tints": tints,
            "layer_order": hero + [c for c in ctx if c not in hero], "prepass_always": ctx[:1] + hero, "double_sided": hero,      # an organ is drawn from both sides: a patch of the model with inward-facing triangles (the stomach's front wall) must not show as a hole "highlights": [], "glow": glow, "bloom": {"strength": 0.35, "radius": 0.5, "threshold": 1.0},
            "labels": labels, "exposure": 0.62, **life_for(organ, at, hero, D)}
