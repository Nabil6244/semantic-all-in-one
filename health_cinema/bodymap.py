"""Body-map scenes for Health Cinema: one continuous 3D shot of a whole body whose camera, anatomical highlights, labels, illustration cards and effects follow the narration.

The CSV directs every beat (columns body_region, body_scale, body_focus, body_effect, card_type, card_ref, card_prompt, card_at, body_label; see scenes_csv.py). Nothing is invented at
render time: `validate` checks each beat against the body's real anchors and the illustration library BEFORE rendering, and `build_spec` turns the checked beats into the journey spec
(camera keys, layer alphas, highlights, labels, cards, procedural tracks) that journey.py samples and the Three.js page draws.

Coordinates: Blender frame (metres, Z up, front -Y, left = +X) as in anchors_body.json (prepared by bench/prep_body.py from the models already in the library).
Illustration rules: the effects (`skin_layers`, `spread`) are conceptual illustrations, labelled as such on screen; cards are labelled as generated illustrations, never clinical photographs."""
from __future__ import annotations
import json, math
from pathlib import Path
from typing import Dict, List, Optional

from . import illustrations as ILL

SCALES = ("whole", "region", "close")
FOCI = ("body", "skin", "vessels", "organ")
EFFECTS = ("none", "skin_layers", "spread", "fatty", "inflamed")      # fatty / inflamed: the organ drifts toward the condition's colour (library.CONDITION), an illustration of the change
CARD_TYPES = ("none", "lesion", "microscopic", "mechanism", "anatomy", "treatment", "test")
FOV = 30.0
CARD_DEFAULT_AT = 0.8
# layer alphas per focus: the body reads as a restrained hologram, the focus brings its own structure forward
LAYERS = {"body": {"Layer_Skin": 0.40, "Layer_Skeleton": 0.22}, "skin": {"Layer_Skin": 0.52, "Layer_Skeleton": 0.05},
          "vessels": {"Layer_Skin": 0.14, "Layer_Skeleton": 0.2, "Layer_Vessels": 0.4, "Layer_Heart": 0.5, "Layer_Lungs": 0.1}}
# organ focus: region anchor -> (the organ's own layers, context layers shown faintly around it). Every organ of the merged body model (bench/prep_body.py) that has an anchor.
_ABD = ("Layer_Liver", "Layer_Stomach", "Layer_Intestines", "Layer_Pancreas", "Layer_Spleen", "Layer_Bladder", "Layer_Urinary")
ORGANS = {"heart": (("Layer_Heart",), ("Layer_Vessels", "Layer_Lungs")), "lungs": (("Layer_Lungs",), ("Layer_Heart",)),
          "liver": (("Layer_Liver",), ("Layer_Stomach", "Layer_Intestines", "Layer_Pancreas")), "liver_only": (("Layer_Liver",), ("Layer_Stomach", "Layer_Intestines", "Layer_Pancreas")),
          "gallbladder": (("Layer_Liver",), ("Layer_Stomach", "Layer_Intestines")), "pancreas": (("Layer_Pancreas",), ("Layer_Stomach", "Layer_Liver", "Layer_Intestines", "Layer_Spleen")),
          "stomach": (("Layer_Stomach",), ("Layer_Liver", "Layer_Intestines", "Layer_Pancreas")), "intestines": (("Layer_Intestines",), ("Layer_Stomach", "Layer_Liver", "Layer_Bladder")),
          "spleen": (("Layer_Spleen",), ("Layer_Stomach", "Layer_Liver")), "bladder": (("Layer_Bladder",), ("Layer_Intestines",)),
          "kidneys": (("Layer_Urinary",), ("Layer_Liver", "Layer_Intestines", "Layer_Spleen", "Layer_Bladder")), "kidney_l": (("Layer_Urinary",), ("Layer_Spleen", "Layer_Intestines")),
          "kidney_r": (("Layer_Urinary",), ("Layer_Liver", "Layer_Intestines")), "urinary": (("Layer_Urinary", "Layer_Bladder"), ("Layer_Intestines",)),
          "abdomen": (_ABD, ()), "brain": (("Layer_Cortex", "Layer_Cerebellum"), ()), "cortex": (("Layer_Cortex",), ("Layer_Cerebellum",)), "cerebellum": (("Layer_Cerebellum",), ("Layer_Cortex",)),
          "eyes": (("Layer_Eyes",), ()), "eye_l": (("Layer_Eyes",), ()), "eye_r": (("Layer_Eyes",), ())}
REGION_ORGAN = {"liver": "liver", "liver_only": "liver", "pancreas": "pancreas", "stomach": "stomach", "intestines": "intestines", "spleen": "spleen"}      # regions the condition tint (library.BASE_TINT) knows
LAYER_ORDER = ["Layer_Cerebellum", "Layer_Cortex", "Layer_Eyes", "Layer_HeadArteries", "Layer_Urinary", "Layer_Bladder", "Layer_Pancreas", "Layer_Spleen", "Layer_AbdVessels", "Layer_Liver", "Layer_Stomach",
               "Layer_Intestines", "Layer_Heart", "Layer_Vessels", "Layer_Lungs", "Layer_Skeleton", "Layer_Skin"]      # innermost first (compositing order)
TINT = {"Layer_Skin": [0.46, 0.72, 1.0], "Layer_Skeleton": [0.82, 0.92, 1.0]}
LABEL_FOR_REGION = {"forearm_l": "Forearm", "forearm_r": "Forearm", "liver_only": "Liver", "kidneys": "Kidneys", "body": ""}

def _label_for(reg: str) -> str:
    if reg in LABEL_FOR_REGION: return LABEL_FOR_REGION[reg]
    base, side = (reg[:-2], {"_l": "Left ", "_r": "Right "}[reg[-2:]]) if reg.endswith(("_l", "_r")) else (reg, "")
    return (side + base.replace("_", " ")).strip().capitalize() if not side else side + base.replace("_", " ")

def layer_alphas(b: dict) -> Dict[str, float]:
    """Layer opacity for a beat's focus. `organ` shows the region's own organ layers strongly and its neighbours faintly, over a faint body."""
    if b["focus"] != "organ": return LAYERS[b["focus"]]
    hero, ctx = ORGANS.get(b["region"], ((), ()))
    out = {"Layer_Skin": 0.10, "Layer_Skeleton": 0.2}; out.update({n: 0.26 for n in ctx}); out.update({n: 0.95 for n in hero}); return out

def route_chain(reg: str, A: dict):
    """(anchor, camera distance) stops for the illustrative route from a lesion on `reg` to the heart, along real anchors: an arm goes up through elbow-side upper arm and shoulder, a leg through the thigh,
    hip and abdomen, a trunk region goes straight in."""
    side = reg[-2:] if reg.endswith(("_l", "_r")) else "_l"; kind = reg.rsplit("_", 1)[0] if reg.endswith(("_l", "_r")) else reg
    if kind in ("forearm", "hand", "upper_arm"): chain = [(f"{reg}.skin", 0.5)] + ([(f"forearm{side}", 0.55)] if kind in ("hand", "forearm") else []) + [(f"upper_arm{side}", 0.62), (f"shoulder{side}", 0.7), ("heart", 0.8)]
    elif kind in ("thigh", "shin", "foot"): chain = [(f"{reg}.skin", 0.6), (f"thigh{side}", 0.8), (f"hip{side}", 0.9), ("abdomen", 1.0), ("heart", 0.9)]
    else: chain = [(f"{reg}.skin", 0.6), ("heart", 0.8)]
    return [(a, d) for a, d in chain if a in A or a.endswith(".skin")]

def _tb(p): return [p[0], p[2], -p[1]]           # Blender (Z up, front -Y) -> three.js (Y up)

def _diag_hw(b):
    h = b["max"][2] - b["min"][2]; w = max(b["max"][0] - b["min"][0], b["max"][1] - b["min"][1]); return h, w

def fit_dist(b, fov=FOV, margin=0.85):
    k = 2 * math.tan(math.radians(fov / 2)) * margin; h, w = _diag_hw(b); return max(h / k, w / (k * 16 / 9))

def load_anchors(path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))["anchors"]

# ---- beats ---------------------------------------------------------------------------------------------------------------------------------------
def beats_from_rows(rows: List[dict], scene_start: float) -> List[dict]:
    """Directed rows (dscene hints + times) -> beats with times relative to the scene start. `rows`: [{start, end, text, hint}]."""
    out = []
    for r in rows:
        h = r.get("hint") or {}
        out.append({"t0": round(float(r["start"]) - scene_start, 3), "t1": round(float(r["end"]) - scene_start, 3), "text": r.get("text", ""), "region": h.get("body_region") or "",
                    "scale": h.get("body_scale") or "region", "focus": h.get("body_focus") or "body", "effect": h.get("body_effect") or "none", "label": h.get("body_label") or "",
                    "card_type": h.get("card_type") or "none", "card_ref": h.get("card_ref") or "", "card_prompt": h.get("card_prompt") or "", "card_at": h.get("card_at")})
    return out

def validate(beats: List[dict], anchors: dict) -> Dict[str, list]:
    """Everything that would make a beat unrenderable or misleading, found before any frame is drawn. errors: the scene cannot be built; warnings: it can, with a fallback."""
    errors, warns, need = [], [], []
    if not beats: errors.append("no beats"); return {"errors": errors, "warnings": warns, "missing_illustrations": need}
    prev_end = 0.0
    for i, b in enumerate(beats, 1):
        w = f"beat {i}"
        if b["region"] not in anchors: errors.append(f"{w}: body_region '{b['region']}' is not an anchor of the body (try: {', '.join(sorted(k for k in anchors if not k.startswith('obj:'))[:12])} ...)")
        if b["scale"] not in SCALES: errors.append(f"{w}: body_scale '{b['scale']}' must be one of {', '.join(SCALES)}")
        if b["focus"] not in FOCI: errors.append(f"{w}: body_focus '{b['focus']}' must be one of {', '.join(FOCI)}")
        if b["effect"] not in EFFECTS: errors.append(f"{w}: body_effect '{b['effect']}' must be one of {', '.join(EFFECTS)}")
        if b["card_type"] not in CARD_TYPES: errors.append(f"{w}: card_type '{b['card_type']}' must be one of {', '.join(CARD_TYPES)}")
        if b["t1"] - b["t0"] < 1.5: warns.append(f"{w}: only {b['t1'] - b['t0']:.1f}s long; the camera move will be quick")
        if b["t0"] < prev_end - 0.05: errors.append(f"{w}: starts before the previous beat ends")
        prev_end = b["t1"]
        if b["focus"] == "organ" and b["region"] in anchors and b["region"] not in ORGANS: errors.append(f"{w}: body_focus=organ needs an organ region ({', '.join(sorted(ORGANS))}), not '{b['region']}'")
        if b["effect"] in ("fatty", "inflamed"):
            from . import library as _lib
            org = REGION_ORGAN.get(b["region"])
            if b["focus"] != "organ" or not org or org not in _lib.CONDITION[b["effect"]][2]: errors.append(f"{w}: body_effect={b['effect']} needs body_focus=organ on {', '.join(k for k in REGION_ORGAN if REGION_ORGAN[k] in _lib.CONDITION[b['effect']][2])}")
        if b["effect"] == "skin_layers" and b["region"] in anchors and "surface" not in anchors[b["region"]]: errors.append(f"{w}: skin_layers needs a region on the skin surface (forearm_l, thigh_l ...), not '{b['region']}'")
        if b["effect"] == "spread" and not any(x["effect"] == "skin_layers" for x in beats[:i - 1]): errors.append(f"{w}: spread needs an earlier skin_layers beat (it starts from that lesion)")
        if b["card_type"] != "none":
            if not (b["card_ref"] or b["card_prompt"]): errors.append(f"{w}: a {b['card_type']} card needs card_ref (an illustration id) or card_prompt (what to generate)")
            elif not ILL.find(b["card_ref"]):
                need.append({"beat": i, "ref": b["card_ref"], "topic": b.get("label") or b["region"], "view": b["card_type"], "kind": b["card_type"], "prompt": b["card_prompt"]})
                warns.append(f"{w}: illustration '{b['card_ref'] or b['card_prompt'][:40]}' is not in the library yet; the beat is built without the card until it is generated")
            if b["card_type"] != "none" and b["effect"] == "none" and b["scale"] == "whole": warns.append(f"{w}: a card on a whole-body shot has little room to point at anything")
    return {"errors": errors, "warnings": warns, "missing_illustrations": need}

# ---- spec ----------------------------------------------------------------------------------------------------------------------------------------
def _keys(pairs): return [[round(t, 3), v] for t, v in pairs]

def build_spec(beats: List[dict], anchors: dict, duration: float, *, cards_enabled: bool = True) -> dict:
    """The journey spec for one continuous body-map shot. `duration` is the scene length in seconds; the beats must lie inside it."""
    A = {k: v for k, v in anchors.items()}; ov: Dict[str, dict] = {}
    D = float(duration); beats = [dict(b, t1=min(b["t1"], D)) for b in beats]; beats[-1]["t1"] = D
    surf = lambda reg: A[reg]["surface"]
    cam, layers, hl, labels, cards, tracks = [], {}, [], [], [], {"skin": [], "infection": [], "spread": [], "route": [], "entry": []}
    block_at = None; block_side = 1; skin_beat = None
    # camera: one key when the move to the beat's view has arrived, one a little before the beat ends (a slow drift, never a freeze)
    az_base = {"whole": -22.0, "region": 8.0, "close": -6.0}
    for i, b in enumerate(beats):
        reg = b["region"]; dur = b["t1"] - b["t0"]; arrive = b["t0"] + min(0.5 * dur, 1.8) if i else 0.0
        target, off = reg, [0, 0, 0]
        if b["effect"] == "skin_layers":
            sp = surf(reg); sgn = 1 if sp[0] >= 0 else -1; ov[f"{reg}.skin"] = {"center": sp}; block_at = sp; block_side = sgn; skin_beat = i
            ov[f"{reg}.view"] = {"center": [sp[0] + 0.05 * sgn, sp[1], sp[2]]}; target = f"{reg}.view"
        box = A[reg]
        if b["scale"] == "whole": d0 = fit_dist(A["body"], margin=0.95) * 0.98; d1 = d0 * 0.9
        elif b["scale"] == "region": d0 = max(0.55, fit_dist(box) * 1.7); d1 = d0 * 0.86
        else: d0 = 0.66 if b["effect"] == "skin_layers" else max(0.36, fit_dist(box) * 0.62); d1 = d0 * 0.9
        az0 = az_base[b["scale"]] + (6 if i % 2 else 0); az1 = az0 + (14 if b["scale"] != "close" else 8); el = {"whole": 6, "region": 9, "close": 14}[b["scale"]]
        if b["effect"] == "spread":
            route = [(tg, dd) for tg, dd in route_chain(beats[skin_beat]["region"], A) if tg in A or tg in ov]
            for j, (tgt, dd) in enumerate(route):      # the move starts at the lesion on the first frame of the beat (no waiting for the route) and follows it to the heart
                cam.append({"t": round(b["t0"] + 0.1 + (dur - 0.6) * j / max(1, len(route) - 1), 3), "target": tgt, "dist": round(dd, 3), "az": az0 + 5 * j, "el": 10, "fov": FOV})
            continue
        if i == 0: cam.append({"t": 0.0, "target": target, "dist": round(d0 * 1.12, 3), "az": az0 - 6, "el": el, "fov": FOV})
        else: cam.append({"t": round(arrive, 3), "target": target, "dist": round(d0, 3), "az": az0, "el": el, "fov": FOV})
        cam.append({"t": round(b["t1"] - 0.25, 3), "target": target, "dist": round(d1, 3), "az": az1, "el": el, "fov": FOV})
    cam.sort(key=lambda k: k["t"]); cam = [k for n, k in enumerate(cam) if n == 0 or k["t"] > cam[n - 1]["t"] + 1e-3]
    if cam[-1]["t"] < D: cam.append(dict(cam[-1], t=round(D, 3)))
    # layers
    names = sorted({n for b in beats for n in layer_alphas(b)}, key=LAYER_ORDER.index)
    for n in names:
        pairs = [(0.0, layer_alphas(beats[0]).get(n, 0.0))]
        for i, b in enumerate(beats[1:], 1): prev = layer_alphas(beats[i - 1]).get(n, 0.0); pairs += [(b["t0"], prev), (b["t0"] + 1.2, layer_alphas(b).get(n, 0.0))]
        pairs.append((D, pairs[-1][1])); layers[n] = _keys(pairs)
    # highlight: the beat's region glows softly when the camera arrives, until the effect takes over
    for i, b in enumerate(beats):
        if b["scale"] != "whole" and b["effect"] != "spread" and b["region"] in A and b["focus"] in ("body", "skin", "organ"):
            bx = A[b["region"]]; sc = [max(0.02, (bx["max"][j] - bx["min"][j]) / 2) * 0.9 for j in range(3)]; t0 = b["t0"] + (0.6 if i else 0.2)
            end = beats[i + 1]["t0"] + 0.8 if i + 1 < len(beats) else b["t1"]
            hl.append({"id": f"hl{i}", "anchor": b["region"], "color": [1.0, 0.36, 0.26] if b["focus"] != "organ" else [1.0, 0.25, 0.3], "offset": [0, 0, 0], "scale": [round(x, 4) for x in sc],
                       "strength": _keys([(0, 0), (t0, 0), (t0 + 0.9, 0.8), (max(t0 + 1.0, end - 0.9), 0.45), (end, 0)])})
    # tracks (procedural effects)
    for i, b in enumerate(beats):
        if b["effect"] == "skin_layers":
            t0, t1 = b["t0"], b["t1"]; tracks["skin"] += [(t0, 0.0), (t0 + 1.4, 1.0)]; tracks["infection"] += [(t0, 0.0), (t0 + 0.9, 0.0), (t1 - 0.4, 1.0)]
        if b["effect"] == "spread":
            t0, t1 = b["t0"], b["t1"]; tracks["skin"] += [(t0 + 0.5, 1.0), (t0 + 1.5, 0.0)]; tracks["entry"] += [(t0, 0.0), (t0 + 0.9, 1.0)]
            tracks["route"] += [(t0 + 0.3, 0.0), (t0 + 1.0, 1.0)]; tracks["spread"] += [(t0 + 0.6, 0.0), (t1 - 0.4, 1.0)]
    for k in list(tracks):
        v = tracks[k]
        if not v: tracks[k] = _keys([(0, 0.0), (D, 0.0)]); continue
        v = sorted(v); out = [(0.0, 0.0)] if v[0][0] > 0 else []; out += v; out.append((D, out[-1][1])); tracks[k] = _keys(out)
    # labels (layer names of the skin block are placed on the block's real rotated corners; see _block_anchors)
    for i, b in enumerate(beats):
        text = b["label"] or _label_for(b["region"])
        if text and b["effect"] not in ("spread", "fatty", "inflamed"):      # a condition beat gets one combined label below (name + what changes), never two that collide
            anchor = f"{b['region']}.skin" if f"{b['region']}.skin" in ov else b["region"]; off = [0.0, -(A[b["region"]]["max"][1] - A[b["region"]]["min"][1]) / 2 - 0.004, 0.0] if anchor == b["region"] else [0, 0, 0]
            labels.append({"id": f"b{i}", "text": text, "anchor": anchor, "offset": off, "t0": round(b["t0"] + (1.3 if i else 0.6), 2), "t1": round(b["t1"] - 0.3, 2), "side": "left" if i % 2 else "right"})
    procedural = {"kind": "bodymap", "seed": 5}
    if block_at is not None:
        blk = _block_anchors(block_at, block_side); ov.update(blk["anchors"]); procedural.update({"at": [round(x, 4) for x in _tb(block_at)], "lift": blk["lift"], "block": blk["size"], "offset": [round(blk["offset"][0], 4), 0.0, 0.0]})
        sb = next(b for b in beats if b["effect"] == "skin_layers"); t0 = sb["t0"] + 2.3
        for nm, an in (("Epidermis", "blk.epidermis"), ("Dermis", "blk.dermis"), ("Subcutaneous fat", "blk.fat")):
            labels.append({"id": nm.lower().split()[0], "text": nm, "anchor": an, "offset": [0, 0, 0], "t0": round(t0 + 0.55 * ["Epidermis", "Dermis", "Subcutaneous fat"].index(nm), 2), "t1": round(min(D, sb["t1"] + 0.4) - 0.3, 2), "side": "right" if block_side > 0 else "left"})
        sp_b = next((b for b in beats if b["effect"] == "spread"), None)
        if sp_b:
            chain = [a for a, _ in route_chain(sb["region"], A)]; pts = [[block_at[0], block_at[1] + 0.012, block_at[2]]] + [A[a]["center"] for a in chain if a in A and not a.endswith(".skin")]
            if len(pts) > 3: pts.insert(-1, [(pts[-2][j] + pts[-1][j]) / 2 for j in range(3)])
            procedural["path"] = [[round(x, 4) for x in _tb(p)] for p in pts]
            labels.append({"id": "route", "text": "Illustrative route: not literal anatomy", "anchor": next(a for a in reversed(chain) if a in A and a != "heart"), "offset": [0, -0.03, 0.04], "t0": round(sp_b["t0"] + 1.2, 2), "t1": round(sp_b["t1"] - 0.3, 2), "side": "left"})
    # cards
    if cards_enabled:
        for i, b in enumerate(beats):
            if b["card_type"] == "none": continue
            e = ILL.find(b["card_ref"])
            if not e: continue
            t0 = b["t0"] + float(b["card_at"] if b.get("card_at") not in (None, "") else CARD_DEFAULT_AT); t1 = min(D - 0.05, b["t1"] + 0.1)      # the card leaves (fades over its last 0.5 s) with its beat, so it never trails into the next camera move
            anchor = f"{b['region']}.skin" if f"{b['region']}.skin" in ov else b["region"]
            cards.append({"id": f"c{i}", "image": e["path"], "sha256": e["sha256"], "title": e.get("title") or (e.get("topic") or "").capitalize(), "tag": "ILLUSTRATION",
                          "foot": "AI-generated medical illustration, not a clinical photograph" if e["source"] == "flow" else "Illustration" if e["source"] == "supplied" else "PLACEHOLDER: layout test only",
                          "anchor": anchor, "t0": round(t0, 2), "t1": round(t1, 2), "side": "left" if block_at is not None else "right"})
    glow = [{"id": "g_skin", "layer": "Layer_Skin", "color": [0.42, 0.78, 1.0], "rim": 1.5, "power": 2.3, "fill": 0.03, "strength": [[0, 1.0], [D, 1.0]]}]
    heroes: Dict[str, float] = {}
    for b in beats:
        if b["focus"] == "organ":
            for n in ORGANS.get(b["region"], ((), ()))[0]: heroes.setdefault(n, b["t0"])
    for n, t in heroes.items(): glow.append({"id": f"g_{n}", "layer": n, "color": [1.0, 0.3, 0.3] if n in ("Layer_Heart", "Layer_Cortex") else [0.55, 0.85, 1.0], "rim": 1.2, "power": 2.2, "fill": 0.1, "strength": _keys([(0, 0), (t + 0.5, 0), (t + 1.8, 1.0), (D, 1.0)])})
    tints = {k: [[0, v], [D, v]] for k, v in TINT.items() if k in layers}
    from . import library as _lib
    for b in beats:      # a condition beat moves the organ's colour from healthy to the condition's (the colour change is an illustration), with its label
        if b["effect"] in ("fatty", "inflamed"):
            key, base = _lib.BASE_TINT[REGION_ORGAN[b["region"]]]; target, text, _ = _lib.CONDITION[b["effect"]]
            tints[key] = [[0, list(base)], [round(b["t0"] + 0.8, 2), list(base)], [round(max(b["t0"] + 1.5, b["t1"] - 0.8), 2), list(target)], [D, list(target)]]
            labels.append({"id": f"cond{b['t0']}", "text": b["label"] or f"{_label_for(b['region'])}: {text.lower()}", "anchor": b["region"], "offset": [-(A[b["region"]]["max"][0] - A[b["region"]]["min"][0]) * 0.12, -(A[b["region"]]["max"][1] - A[b["region"]]["min"][1]) / 2 - 0.004, 0.0], "t0": round(b["t0"] + 1.2, 2), "t1": round(b["t1"] - 0.3, 2), "side": "left"})
    return {"id": "bodymap_v1", "profile": "medical_cinema", "duration": D, "background": [0.012, 0.016, 0.03], "camera": cam, "layers": layers, "tints": tints, "layer_order": [n for n in LAYER_ORDER if n in layers],
            "prepass_always": ["Layer_Skin"], "highlights": hl, "highlight_opacity": 0.2, "highlight_additive": True, "glow": glow, "bloom": {"strength": 0.32, "radius": 0.5, "threshold": 0.92}, "labels": labels, "cards": cards, "tracks": tracks,
            "procedural": procedural, "anchor_overrides": ov, "exposure": 0.8, "theme": "organ", "fog_density": 0.18, "motes": 160, "sway": 0.008}

def _block_anchors(at, sgn=1):
    """The skin-tissue block floats LIFT in front of the skin spot, tilted; its layer labels point at the middle of each layer on the cut face, computed with the same transform bodymap.js uses."""
    W, Dp, H, lift, th, off = 0.16, 0.1, 0.07, 0.05, 0.5, 0.14 * sgn; fr = [("epidermis", 0.0), ("dermis", 0.30), ("fat", 0.82)]; out = {}
    ct, st = math.cos(th), math.sin(th); base = _tb(at)
    for name, f in fr:
        x, y, z = W / 2 * sgn, -Dp * f, H / 2             # the outer end of the layer's cut face (away from the body, so its label sits in empty space)
        y2, z2 = y * ct - z * st, y * st + z * ct; p3 = [base[0] + off + x, base[1] + y2, base[2] + lift + z2]
        out[f"blk.{name}"] = {"center": [round(p3[0], 4), round(-p3[2], 4), round(p3[1], 4)]}
    return {"anchors": out, "lift": lift, "size": [W, Dp, H], "offset": [off, 0, 0]}
