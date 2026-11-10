"""The Flow asset library (docs/rep_theory/PLAN_NEXT_GRAPHICS.md, Phase 5, layer 3): things code cannot draw well (an x-ray forearm, the shoulder blades from behind, a brain and
spinal cord, a backpack, a bathroom scale ...) are asked of Flow as one clean art asset with no text, under a fixed name and a fixed prompt. The picture id is the asset's
name, so the first script that needs it pays the Flow cost and every later video reuses the stored picture (the same rule as the pose library).
A picture scene whose words name an asset's subject gets that asset instead of a picture made from its sentence; the code still draws the labels, arrows and red reveal on top
(picture.py). The same asset is not shown again within REUSE_GAP_S. The CSV `graphic` cell can ask for one by name ("asset: xray forearm")."""
from __future__ import annotations
import re
from typing import Dict, List, Optional


VERSION = "v1"
REUSE_GAP_S = 30.0
_INK = ("Manga ink illustration, greyscale with white highlights, solid pure black background (#000000), no text, no letters, no numbers, no logos, no watermark, no border, "
        "the subject on one side of the frame (about 60%) with the other side empty black")

# name -> (words that call for it, what Flow draws, the part painted red or "")
CATALOGUE: Dict[str, tuple] = {
    "xray_forearm": (r"\b(?:forearm|wrist)s?\b[^.!?]{0,40}\b(?:tendons?|bones?|ligaments?)\b|\b(?:tendons?|bones?|ligaments?)\b[^.!?]{0,40}\b(?:forearm|wrist)s?\b", "an x-ray view of a human forearm and wrist: the bones visible through translucent skin", "the tendons"),
    "xray_elbow": (r"\belbows?\b[^.!?]{0,40}\b(?:tendons?|joint|ligaments?|bones?)\b|\b(?:tendons?|joint|ligaments?)\b[^.!?]{0,40}\belbows?\b", "an x-ray view of a bent human elbow: upper arm and forearm bones visible through translucent skin", "the elbow tendons"),
    "xray_knee": (r"\bknees?\b[^.!?]{0,40}\b(?:tendons?|joint|ligaments?|cartilage|bones?)\b|\b(?:tendons?|ligaments?|cartilage)\b[^.!?]{0,40}\bknees?\b", "an x-ray side view of a human knee joint: thigh and shin bones visible through translucent skin", "the knee ligaments and patellar tendon"),
    "xray_shoulder": (r"\b(?:rotator cuff|shoulder joint|shoulder capsule)\b", "an x-ray front view of a human shoulder joint: collarbone, shoulder blade and upper arm bone visible through translucent skin", "the rotator cuff"),
    "back_shoulder_blades": (r"\b(?:shoulder blades?|scapulae?|scapular|serratus)\b", "a man's bare upper back seen from behind, the shoulder blades and the muscles around them clearly shaped", "the serratus and the muscles around the shoulder blades"),
    "brain_spine": (r"\b(?:brain|nervous system|spinal cord|nerves?|motor units?)\b", "a human silhouette in profile with the brain and spinal cord drawn inside it, nerves branching into one arm", "the brain and spinal cord"),
    "hands_top": (r"\b(?:hand placement|fingers spread|spread your fingers|hands flat|fingers (?:pointing|turned) (?:out|back|sideways))\b", "two hands placed flat on the floor seen from directly above, fingers spread", ""),
    "obj_backpack": (r"\b(?:backpack|weight vest|weighted vest)\b", "a single heavy hiking backpack standing on its own", ""),
    "obj_scale": (r"\b(?:bathroom scale|on the scale|weigh yourself|weighing yourself)\b", "a single bathroom scale seen at an angle from above", ""),
    "obj_plate": (r"\b(?:plate of food|your plate|dinner plate|meal prep)\b", "a single plate of food seen from above: grilled chicken, rice and vegetables", ""),
    "obj_water": (r"\b(?:glass of water|water bottle|bottle of water)\b", "a single glass of water with a water bottle beside it", ""),
    "obj_bucket": (r"\bbuckets?\b", "a single metal bucket full of water", ""),
    "mock_phone": (r"\b(?:your phone|phone timer|on your phone|an app)\b", "a smartphone lying at an angle with a blank glowing screen", ""),
    "mock_book": (r"\b(?:e-?book|the book|my book|my guide|my program)\b", "a thick paperback training book lying at an angle with a blank cover", ""),
}
RX = {k: re.compile(v[0], re.I) for k, v in CATALOGUE.items()}

def norm(name: str) -> str:
    """'xray forearm', 'X-ray forearm', 'obj backpack' -> the catalogue key, or ''."""
    k = re.sub(r"[^a-z0-9]+", "_", str(name or "").lower().replace("x-ray", "xray")).strip("_")
    if k in CATALOGUE: return k
    return next((c for c in CATALOGUE if c.split("_", 1)[-1] == k or c.endswith("_" + k)), "")

def match(text: str) -> str:
    """The asset whose subject the sentence names (the earliest in the sentence), or ''."""
    best = None
    for k, rx in RX.items():
        m = rx.search(text or "")
        if m and (best is None or m.start() < best[1]): best = (k, m.start())
    return best[0] if best else ""

def art_id(name: str) -> str: return f"asset_{name}_{VERSION}"

def prompt(name: str) -> str:
    _rx, subject, red = CATALOGUE[name]
    return f"{subject[0].upper() + subject[1:]}. {_INK}." + (f" Paint {red} glowing red over the ink; everything else stays greyscale." if red else " Greyscale only, no colour.")

def plan(scenes: List[dict]) -> int:
    """Gives each picture scene that names an asset's subject (or whose CSV row asked for one) its library asset. Returns how many scenes got one."""
    from . import theme as T
    if T.THEME in T.NO_GYM: return 0      # Cat / Carl Jung / Elder Health draw every picture in their own style; these assets are manga ink on black (pipeline check 2026-11-10: an x-ray knee in an Elder video)
    seen: Dict[str, float] = {}; n = 0; prev = None
    for sc in scenes:
        if sc.get("same_picture") and prev is not None and prev.get("asset") and sc.get("look") == "flow": sc["asset"] = prev["asset"]; prev = sc; continue      # a long asset shot cut in two: the same asset, re-framed
        prev = sc
        if sc.get("look") != "flow" or sc.get("hook"): continue
        g = sc.get("graphic_csv") or {}
        name = norm(g.get("name", "")) if g.get("kind") == "asset" else ""
        if not name and (sc.get("flow_prompt") and sc.get("directed_look")): continue      # the CSV described its own picture: it wins
        name = name or match(sc.get("script_text") or sc.get("text", ""))
        if not name or float(sc["start"]) - seen.get(name, -1e9) < REUSE_GAP_S: continue
        sc["asset"] = name; seen[name] = float(sc["end"]); sc.pop("reuses_picture", None); sc["decisions"].append(f"asset: library picture {name} (made once through Flow, reused by every video)"); n += 1
    return n
