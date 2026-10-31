"""Part targeting: when a sentence names a part of the organ on screen (the valves, a coronary artery, the retina, the L4-L5 disc ...), that scene's camera ends
on that part and labels it. A video about one organ shows twenty different things instead of the same organ twenty times.

PARTS maps words to named objects of the prepared models (`obj:<name>` anchors and region anchors). A part is used only when the scene's model has it and the
layer that holds it is still on screen at the end of the shot; otherwise the scene is left as it was. Nothing here invents a position: every target is a
real object of the model."""
from __future__ import annotations
import json, math, re
from typing import Dict, List, Optional, Tuple

# (pattern, label, anchors in order of preference)
PARTS: List[Tuple[str, str, Tuple[str, ...]]] = [
    # heart (chest model)
    (r"\bleft ventricle", "Left ventricle", ("obj:Left ventricle",)),
    (r"\bright ventricle", "Right ventricle", ("obj:Right ventricle",)),
    (r"\bleft atri(um|al)", "Left atrium", ("obj:Left atrium",)),
    (r"\bright atri(um|al)", "Right atrium", ("obj:Right atrium",)),
    (r"\bventricles?\b", "Ventricles", ("obj:Left ventricle",)),
    (r"\batria\b|\batrium\b|\batrial\b", "Atria", ("obj:Left atrium",)),
    (r"\bmitral\b", "Mitral valve", ("obj:Posterior leaflet of left atrioventricular valve",)),
    (r"\btricuspid\b", "Tricuspid valve", ("obj:Septal leaflet of right atrioventricular valve",)),
    (r"\bpulmonary valve", "Pulmonary valve", ("obj:Anterior semilunar leaflet of pulmonary valve",)),
    (r"\baortic valve|\bheart valves?\b|\bvalves?\b", "Heart valves", ("obj:Non-coronary leaflet", "obj:Right coronary leaflet")),
    (r"\bcoronary arter(y|ies)|\bcoronary\b", "Coronary arteries", ("obj:Left coronary artery", "obj:Right coronary artery")),
    (r"\bpulmonary arter(y|ies)|\bpulmonary trunk", "Pulmonary artery", ("obj:Pulmonary trunk",)),
    (r"\bpulmonary veins?", "Pulmonary veins", ("obj:Left superior pulmonary vein",)),
    (r"\bvena cava", "Vena cava", ("obj:Superior vena cava",)),
    (r"\babdominal aorta", "Abdominal aorta", ("obj:Abdominal aorta.001",)),
    (r"\baortic arch", "Aortic arch", ("obj:Aortic arch",)),
    (r"\baorta\b", "Aorta", ("obj:Ascending aorta", "obj:Aortic arch", "obj:Abdominal aorta.001")),
    (r"\bpapillary", "Papillary muscles", ("obj:Inferior papillary muscle of left ventricle",)),
    # brain and eye (head model)
    (r"\bcircle of willis", "Circle of Willis", ("circle_of_willis",)),
    (r"\bmiddle cerebral", "Middle cerebral artery", ("obj:Middle cerebral artery (M1-segment).l",)),
    (r"\banterior cerebral", "Anterior cerebral artery", ("obj:Anterior cerebral artery.l",)),
    (r"\bposterior cerebral", "Posterior cerebral artery", ("obj:Posterior cerebral artery.l",)),
    (r"\bbasilar|\bvertebral arter", "Basilar artery", ("obj:Basilar artery",)),
    (r"\bcarotids?\b", "Carotid artery", ("obj:Internal carotid artery.l", "carotid_l")),
    (r"\bcerebellum|\bbalance and coordination", "Cerebellum", ("cerebellum",)),
    (r"\bcortex\b|\bcerebral cortex", "Cerebral cortex", ("cortex",)),
    (r"\bretina", "Retina", ("obj:Retina.l",)),
    (r"\blens\b|\bcataracts?\b", "Lens", ("obj:Lens.l",)),
    (r"\bcornea", "Cornea", ("obj:Cornea.l",)),
    (r"\boptic nerve|\bglaucoma", "Optic nerve", ("obj:Optic nerve (II).l",)),
    # abdomen
    (r"\boesophag|\besophag|\bfood pipe|\bacid reflux|\bheartburn", "Oesophagus", ("obj:Oesophagus.001",)),
    (r"\bduoden", "Duodenum", ("obj:Duodenum.001",)),
    (r"\bappendi(x|citis)", "Appendix", ("obj:Vermiform appendix.001",)),
    (r"\bsigmoid", "Sigmoid colon", ("obj:Sigmoid colon.001",)),
    (r"\bcolon\b|\blarge intestine|\bbowel cancer", "Colon", ("obj:Transverse colon.001", "obj:Ascending colon.001")),
    (r"\bsmall intestine|\bjejunum", "Small intestine", ("obj:Jejunum.001",)),
    (r"\bhepatic veins?|\bportal vein", "Hepatic veins", ("obj:Hepatic veins.001",)),
    (r"\bsplenic arter", "Splenic artery", ("obj:Splenic artery.001",)),
    # spine and knee (msk model)
    (r"\bl4\b|\bl5\b|\blumbar disc|\blower back disc|\bsciatica|\bslipped disc|\bherniated disc", "Lumbar disc (L4-L5)", ("obj:Intervertebral disc L4-L5.001",)),
    (r"\bcervical|\bneck disc", "Cervical disc (C5-C6)", ("obj:Intervertebral disc C5-C6.001",)),
    (r"\bmedial meniscus", "Medial meniscus", ("obj:Medial meniscus.l.001",)),
    (r"\blateral meniscus", "Lateral meniscus", ("obj:Lateral meniscus.l.001",)),
]
END_FILL = 0.55      # how much of the frame the part fills when the camera arrives, at most
CONTEXT = 3.0        # ... and never closer than a view of three times the part's size around it: a valve or a disc is seen in place, never from inside the organ


def find(text: str, anchors: Dict[str, dict]) -> Optional[Tuple[str, str]]:
    """(label, anchor) of the first part the sentence names that this model has, else None."""
    low = (text or "").lower()
    for pat, label, refs in PARTS:
        if re.search(pat, low):
            for ref in refs:
                if ref in anchors and "min" in anchors[ref]: return label, ref
    return None


def _centre(b): return [(b["min"][i] + b["max"][i]) / 2 for i in range(3)]
def _diag(b): return math.sqrt(sum((b["max"][i] - b["min"][i]) ** 2 for i in range(3)))


def _layer_of(obj: str, layers: Dict[str, List[str]]) -> Optional[str]:
    name = obj[4:] if obj.startswith("obj:") else None
    if not name: return None
    for ln, objs in layers.items():
        if name in objs: return ln
    return None


def _alpha_at_end(spec: dict, layer: str) -> float:
    keys = spec.get("layers", {}).get(layer)
    return float(keys[-1][1]) if keys else 0.0


def focus(spec: dict, text: str, anchors_path: str) -> dict:
    """The spec with its last part retargeted to the part the sentence names (a new dict), or the spec unchanged."""
    try:
        from pathlib import Path
        data = json.loads(Path(anchors_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return spec
    A, layers = data.get("anchors", {}), data.get("layers", {})
    hit = find(text, A)
    if not hit: return spec
    label, ref = hit
    ln = _layer_of(ref, layers)
    if ln and _alpha_at_end(spec, ln) < 0.3:      # the part's layer is gone by the end: not shown (but the heart's cut-away still shows its chambers)
        if not (ln == "Layer_Heart" and _alpha_at_end(spec, "Layer_HeartCut") >= 0.3): return spec
    if spec.get("camera") and spec["camera"][-1].get("target") == ref: return spec
    s = json.loads(json.dumps(spec)); D = float(s["duration"]); cam = s["camera"]
    keep = [k for k in cam if k["t"] <= D * 0.55] or cam[:1]
    last = cam[-1]; az, el, fov = last["az"], last["el"], last["fov"]
    pb = A[ref]; pc = _centre(pb); organ = A.get(keep[-1]["target"]) or A.get(last["target"])
    if organ and "min" in organ:      # look from the side the part is on (organ centre -> part): a surface part faces the camera instead of hiding behind the organ
        oc = _centre(organ); v = [pc[i] - oc[i] for i in range(3)]; n = math.sqrt(sum(x * x for x in v))
        if n > 0.15 * _diag(organ):
            az = math.degrees(math.atan2(v[0], -v[1])); el = max(-10.0, min(35.0, math.degrees(math.asin(max(-1.0, min(1.0, v[2] / n))))))
            if abs(((az - last["az"] + 180) % 360) - 180) > 120: az = last["az"] + (120 if ((az - last["az"]) % 360) < 180 else -120)      # never swing round more than a third of a turn
    ctx = max(1.25, min(CONTEXT, 0.12 / max(1e-4, _diag(pb))))      # tiny parts get three times their size around them, long ones (the oesophagus) just a margin
    keep += [{"t": round(D * 0.75, 3), "target": ref, "fill": round(END_FILL * 0.85, 3), "az": az - 10, "el": el, "fov": fov, "context_scale": ctx + 0.6},
             {"t": D, "target": ref, "fill": END_FILL, "az": az + 6, "el": el + 2, "fov": fov, "context_scale": ctx}]
    s["camera"] = keep
    for l in s.get("labels", []): l["t1"] = min(l["t1"], round(D * 0.68, 3))      # the organ's own labels clear before the part's label comes in
    s.setdefault("labels", []).append({"id": "part", "text": label, "anchor": ref, "offset": [0, 0, 0], "t0": round(D * 0.74, 3), "t1": round(D - 0.4, 3), "side": "right"})
    s["id"] = f"{s.get('id', '')}_part_{re.sub(r'[^a-z0-9]+', '_', label.lower())}"; s["part"] = label
    return s
