"""Condition scenes: 3D illustrations of what a narration describes, built fresh for every video (threejs/conditions.js draws them).

A scene is a template id `cond:<name>:<shot>` (shot: orbit | zoom). Each entry in CONDITIONS names the drawing (kind + condition), the words that pick it
from a sentence, its labels and where they point. The drawing is seeded per video and scene (spec.procedural.seed, set by the variety director), so the
same condition in two videos is never the same clip. Positions are given here once, in the scene's own frame, and passed to the page as anchors: the
drawing places its parts there and the labels point at them, so a label always sits on what it names. Everything shown is a conceptual illustration.

Coordinates below are three.js scene units (Y up, the camera starts in front at +Z); anchors are stored the way the journey sampler expects them
(Blender frame: x, -z, y)."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

DURATION = 12.0


@dataclass(frozen=True)
class Cond:
    kind: str                                   # the drawing in conditions.js
    condition: str = ""                         # its variant (skin: cellulitis, abscess ...; alveoli: pneumonia, emphysema)
    aliases: Tuple[str, ...] = ()               # words a CSV `organ` cell may use
    auto: Tuple[str, ...] = ()                  # phrases specific enough to pick the scene from narration alone
    labels: Tuple[Tuple[str, str, float], ...] = ()      # (text, point, appears at this fraction of the shot)
    params: Tuple[Tuple[str, object], ...] = ()
    theme: str = "cell"
    el: float = 14.0                            # camera height (degrees): the skin block is seen from above its cut face


SKIN_LABELS = (("Epidermis", "epidermis", 0.12), ("Dermis", "dermis", 0.2), ("Fat", "fat", 0.28))
CONDITIONS: Dict[str, Cond] = {
    "cellulitis": Cond("skin", "cellulitis", ("cellulitis", "skin infection", "bacterial skin infection"), ("cellulitis", "skin infection"), SKIN_LABELS + (("Bacteria spread in the dermis", "lesion", 0.5),), theme="crimson", el=24),
    "abscess": Cond("skin", "abscess", ("abscess", "boil", "boils", "skin abscess"), ("abscess", "boil"), SKIN_LABELS + (("Pus collects in a pocket", "lesion", 0.55),), theme="crimson", el=24),
    "burn": Cond("skin", "burn", ("burn", "burns", "scald", "second-degree burn", "skin burn"), ("burn", "burns", "scald"), SKIN_LABELS + (("Blisters form", "lesion", 0.55),), (("degree", 2),), theme="amber", el=26),
    "burn_severe": Cond("skin", "burn", ("third-degree burn", "severe burn", "full-thickness burn"), ("third-degree burn", "severe burn"), SKIN_LABELS + (("Damage reaches the dermis", "lesion", 0.55),), (("degree", 3),), theme="amber", el=26),
    "acne": Cond("skin", "acne", ("acne", "pimple", "pimples", "blackhead", "blackheads", "clogged pores", "whitehead"), ("acne", "pimple", "pimples", "clogged pores"), SKIN_LABELS + (("Oil plugs the pore", "lesion", 0.4),), theme="violet", el=24),
    "eczema": Cond("skin", "eczema", ("eczema", "atopic dermatitis", "dermatitis", "dry cracked skin"), ("eczema", "atopic dermatitis"), SKIN_LABELS + (("Skin barrier cracks", "lesion", 0.5),), theme="amber", el=30),
    "fungal_skin": Cond("skin", "fungal", ("fungal infection", "fungal skin infection", "ringworm", "athlete's foot", "tinea"), ("fungal infection", "ringworm", "athlete's foot"), SKIN_LABELS + (("Fungal threads spread", "lesion", 0.5),), theme="emerald", el=30),
    "psoriasis": Cond("skin", "psoriasis", ("psoriasis", "plaque psoriasis", "scaly skin"), ("psoriasis",), SKIN_LABELS + (("Skin cells pile up", "lesion", 0.5),), theme="violet", el=30),
    "wound_healing": Cond("skin", "wound", ("wound healing", "wound", "wounds", "cut heals", "healing wound"), ("wound healing", "wounds heal"), SKIN_LABELS + (("New tissue closes the wound", "lesion", 0.55),), theme="teal", el=26),
    "virus_infection": Cond("virus", "", ("virus", "viruses", "viral infection", "coronavirus", "flu virus", "infects cells"), ("viral infection", "the virus", "a virus", "viruses"), (("Host cell", "cell_edge", 0.1), ("Virus enters the cell", "entry", 0.4), ("New virus copies", "copies", 0.75)), theme="violet"),
    "immune_response": Cond("immune", "", ("immune response", "white blood cells", "immune system", "immune cells", "phagocytes", "macrophages"), ("white blood cells", "immune cells", "immune response"), (("Bacteria", "bacteria", 0.1), ("White blood cells engulf them", "attack", 0.45)), theme="teal"),
    "insulin": Cond("insulin", "", ("insulin", "glucose uptake", "blood sugar", "insulin receptors"), ("insulin",), (("Insulin", "insulin", 0.15), ("Receptor", "receptor", 0.25), ("Glucose enters the cell", "glucose", 0.55)), (("resistance", 0.0),), theme="ocean"),
    "insulin_resistance": Cond("insulin", "", ("insulin resistance", "type 2 diabetes", "insulin resistant"), ("insulin resistance", "type 2 diabetes"), (("Insulin", "insulin", 0.15), ("Receptor", "receptor", 0.25), ("Little glucose gets in", "glucose", 0.6)), (("resistance", 0.7),), theme="amber"),
    "nerve_signal": Cond("neuron", "", ("neuron", "neurons", "nerve signal", "nerve cells", "synapse", "neurotransmitter", "dopamine", "serotonin"), ("neurons", "nerve signal", "synapse", "neurotransmitters"), (("Neuron", "neuron", 0.1), ("Signal crosses the synapse", "synapse", 0.4)), theme="violet"),
    "cancer_growth": Cond("cancer", "", ("cancer", "tumour", "tumor", "cancer cells", "malignant", "metastasis"), ("cancer cells", "tumour", "tumor"), (("Normal cell", "normal", 0.1), ("Abnormal cells multiply", "tumour", 0.35), ("New blood vessel", "vessel", 0.7)), theme="crimson"),
    "asthma": Cond("airway", "", ("asthma", "asthma attack", "airway narrowing", "bronchospasm", "wheezing"), ("asthma", "airways narrow", "bronchospasm"), (("Airway muscle tightens", "muscle", 0.3), ("Mucus", "mucus", 0.6)), theme="teal"),
    "alveoli": Cond("alveoli", "", ("alveoli", "air sacs", "gas exchange", "oxygen exchange"), ("alveoli", "air sacs", "gas exchange"), (("Air sacs (alveoli)", "sacs", 0.15), ("Capillaries", "capillaries", 0.35)), theme="ocean"),
    "pneumonia": Cond("alveoli", "pneumonia", ("pneumonia", "lung infection", "fluid in the lungs"), ("pneumonia", "lung infection"), (("Air sacs (alveoli)", "sacs", 0.15), ("Sacs fill with fluid", "fluid", 0.5)), theme="steel"),
    "emphysema": Cond("alveoli", "emphysema", ("emphysema", "copd", "chronic obstructive pulmonary disease"), ("emphysema", "copd"), (("Air sacs (alveoli)", "sacs", 0.15), ("Walls break down", "fluid", 0.5)), theme="steel"),
    "osteoporosis": Cond("bone", "", ("osteoporosis", "bone loss", "brittle bones", "weak bones", "bone thinning"), ("osteoporosis", "bone loss", "brittle bones"), (("Spongy bone", "lattice", 0.15), ("Struts thin and break", "loss", 0.55)), theme="steel"),
    "arthritis": Cond("joint", "", ("arthritis", "osteoarthritis", "cartilage loss", "joint wear", "worn cartilage"), ("arthritis", "osteoarthritis", "cartilage wears"), (("Cartilage", "cartilage", 0.15), ("Bone spurs", "spur", 0.6)), theme="amber"),
    "aneurysm": Cond("aneurysm", "", ("aneurysm", "aortic aneurysm", "bulging artery"), ("aneurysm",), (("Artery wall", "wall", 0.15), ("The wall bulges", "bulge", 0.5)), theme="crimson"),
}

# where each drawing's parts are (three.js units); `subject` is the box the camera frames
_SKIN = {"subject": ((-1.45, -0.85, -0.75), (1.45, 0.75, 0.75)), "epidermis": (1.15, 0.49, 0.66), "dermis": (1.15, 0.12, 0.66), "fat": (1.15, -0.45, 0.66), "lesion": (0.0, 0.55, 0.2)}
POINTS: Dict[str, Dict[str, tuple]] = {
    "skin": _SKIN,
    "virus": {"subject": ((-1.7, -1.4, -1.2), (1.7, 1.6, 1.2)), "cell": (0.0, -0.2, 0.0), "cell_edge": (0.62, -0.35, 0.62), "entry": (0.0, 0.7, 0.2), "copies": (0.55, -0.1, 0.55)},
    "immune": {"subject": ((-1.4, -1.0, -0.9), (1.9, 1.0, 0.9)), "bacteria": (0.3, 0.0, 0.0), "attack": (0.55, 0.3, 0.3)},
    "insulin": {"subject": ((-2.2, -0.9, -0.9), (2.2, 1.7, 0.9)), "insulin": (-0.8, 0.25, 0.0), "receptor": (-0.8, -0.05, 0.1), "glucose": (0.9, 0.9, 0.0)},
    "neuron": {"subject": ((-3.0, -1.0, -0.8), (1.8, 1.0, 0.8)), "neuron": (-2.5, 0.3, 0.3), "axon_start": (-2.2, 0.3, 0.0), "synapse": (1.0, 0.0, 0.0)},
    "cancer": {"subject": ((-1.5, -1.1, -1.0), (1.6, 1.1, 1.0)), "normal": (1.3, 0.2, 0.0), "tumour": (0.0, 0.0, 0.0), "vessel": (-1.2, -0.6, -0.1)},
    "airway": {"subject": ((-2.3, -0.8, -0.8), (2.3, 0.8, 0.8)), "muscle": (0.0, 0.66, 0.0), "mucus": (0.6, -0.1, 0.25)},
    "alveoli": {"subject": ((-1.3, -1.3, -1.3), (1.3, 2.2, 1.3)), "cluster": (0.0, 0.0, 0.0), "sacs": (0.78, 0.0, 0.0), "capillaries": (-1.05, 0.3, 0.0), "fluid": (0.0, -0.78, 0.2)},
    "bone": {"subject": ((-1.4, -1.3, -1.0), (1.4, 1.3, 1.0)), "lattice": (0.3, 0.3, 0.5), "loss": (-0.4, -0.3, 0.5)},
    "joint": {"subject": ((-1.3, -2.3, -1.3), (1.3, 2.3, 1.3)), "cartilage": (0.88, 0.18, 0.0), "spur": (-0.9, -0.25, 0.0)},
    "aneurysm": {"subject": ((-2.5, -1.2, -1.2), (2.5, 1.2, 1.2)), "wall": (-1.8, 0.5, 0.0), "bulge": (0.0, 1.0, 0.0)},
}


def _blender(p) -> List[float]:
    return [round(p[0], 4), round(-p[2], 4), round(p[1], 4)]


def anchors_for(kind: str) -> Dict[str, dict]:
    out = {}
    for name, v in POINTS[kind].items():
        if name == "subject":
            lo, hi = _blender(v[0]), _blender(v[1]); mn = [min(lo[i], hi[i]) for i in range(3)]; mx = [max(lo[i], hi[i]) for i in range(3)]
            out["subject"] = {"min": mn, "max": mx, "center": [(mn[i] + mx[i]) / 2 for i in range(3)]}
        else:
            c = _blender(v); out[f"c_{name}"] = {"center": c, "min": [x - 0.05 for x in c], "max": [x + 0.05 for x in c]}
    return out


def key_for(name: str) -> Optional[str]:
    n = (name or "").strip().lower().replace("_", " ")
    for k, c in CONDITIONS.items():
        if n == k.replace("_", " ") or n in c.aliases: return k
    return None


def build_spec(template: str, seed: int = 1) -> dict:
    """The journey spec of `cond:<name>:<shot>`. No model file: the page draws everything (conditions.js)."""
    _, name, *rest = template.split(":"); shot = (rest or ["orbit"])[0]; c = CONDITIONS[name]; D = DURATION
    ov = anchors_for(c.kind)
    cam = ([(0, 0.62, -26, c.el - 4), (D * 0.5, 0.74, -4, c.el), (D, 0.8, 22, c.el - 2)] if shot != "zoom" else [(0, 0.5, -10, c.el), (D * 0.55, 0.7, 4, c.el + 2), (D, 0.84, 10, c.el)])
    labels = [{"id": f"l{i}", "text": text, "anchor": f"c_{pt}", "offset": [0, 0, 0], "t0": round(D * t0, 2), "t1": round(D - 0.6, 2), "side": "right" if POINTS[c.kind][pt][0] >= 0 else "left"}
              for i, (text, pt, t0) in enumerate(c.labels) if pt in POINTS[c.kind]]
    return {"id": f"{template}_v1", "profile": "medical_cinema", "duration": D, "background": [0.012, 0.016, 0.03], "no_model": True,
            "camera": [{"t": round(t, 2), "target": "subject", "fill": f, "az": az, "el": el, "fov": 30.0} for t, f, az, el in cam],
            "layers": {}, "layer_order": [], "prepass_always": [], "highlights": [], "glow": [], "bloom": {"strength": 0.32, "radius": 0.5, "threshold": 0.95},
            "labels": labels, "exposure": 0.74, "theme": c.theme, "fog_density": 0.25, "anchor_overrides": ov,
            "tracks": {"prog": [[0.0, 0.0], [round(D * 0.1, 2), 0.0], [round(D * 0.85, 2), 1.0], [D, 1.0]]},
            "procedural": {"kit": "conditions", "kind": c.kind, "condition": c.condition, "seed": int(seed), **dict(c.params), "illustration": "Conceptual illustration, not to scale."}}
