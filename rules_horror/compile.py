"""Beats -> a What If engine spec: one black shot per beat and rh_* layers on top, hard cuts (no fades), grain and vignette from `look`."""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Dict, List

HARD = {"fade_in": 0, "fade_out": 0}


GROUND = {"bedroom": 0.80, "hallway": 0.80, "house_section": 0.84, "yard": 0.80, "door": 0.88, "window": 0.88, "classroom": 0.82, "stairs": 0.84,
          "hall_lit": 0.80, "street": 0.80, "cutaway": 0.84, "cabin": 0.90, "store": 0.90, "bathroom": 0.84, "kitchen": 0.84, "hall_mirror": 0.80}
SET_LAYERS = tuple(GROUND)


def stage_media(plan: Dict[str, Any], media_dir: Path) -> Dict[str, str]:
    """Copy every picture the plan uses into media_dir under a short name: {original path: name}. A missing file is skipped (its figure is drawn instead)."""
    media_dir = Path(media_dir)
    media_dir.mkdir(parents=True, exist_ok=True)
    out: Dict[str, str] = {}
    for b in plan["beats"]:
        for f in b["figures"]:
            p = f.get("picture")
            if p and p not in out and Path(p).is_file():
                name = f"p{len(out) + 1}{Path(p).suffix.lower() or '.png'}"
                shutil.copy(p, media_dir / name)
                out[p] = name
    return out


def compile_spec(pl: Dict[str, Any], *, width: int = 1280, height: int = 720, fps: int = 24, look: Dict[str, Any] | None = None,
                 media: Dict[str, str] | None = None, media_dir: Path | None = None, scheme: str = "mono", card_style: str | None = None) -> Dict[str, Any]:
    """scheme: mono (white on black), dark (night colour), colour (lit interiors, hazard rule cards) or story (each shot takes its mood from the narration: night, warm, cold, red, day, dawn)."""
    media = media or {}
    scheme = scheme if scheme in ("mono", "dark", "colour", "deep", "story") else "mono"
    last_set, last_mood = "house_section", None
    shots: List[Dict[str, Any]] = []
    layers: List[Dict[str, Any]] = []
    for i, b in enumerate(pl["beats"]):
        shots.append({"id": f"b{i}", "start": b["start"], "end": b["end"], "kind": "black"})
        win = {"start": b["start"], "end": b["end"], **HARD}
        if scheme == "story" and b.get("mood"):
            win = {**win, "mood": b["mood"]}
        cam = b["cam"]
        if scheme != "mono" and not b["card"]:
            layers.append({"type": "rh_bg", **win})
        if b["card"]:
            if card_style == "dim":            # the card is laid over the last scene, darkened (the plane, cinema and pencil-test references)
                bwin = {**win, **({"mood": last_mood} if scheme == "story" and last_mood else {})}
                if scheme != "mono":
                    layers.append({"type": "rh_bg", **bwin})
                layers.append({"type": "rh_set", "set": last_set, "cam": cam, **bwin})
            layers.append({"type": "rh_rulecard", "text": b["card"]["text"], **({"number": b["card"]["number"]} if b["card"]["number"] else {}),
                           **({"style": card_style} if card_style else {}), **win})
        else:
            if b["set"] in SET_LAYERS:
                layers.append({"type": "rh_set", "set": b["set"], "cam": cam, **win})
                last_set, last_mood = b["set"], b.get("mood")
            for L in b.get("layers", []):
                layers.append({**L, "cam": cam, **win})
            for f in b["figures"]:
                if f.get("picture"):
                    name = media.get(f["picture"])
                    if name and f.get("mode") == "full":
                        layers.append({"type": "rh_picture", "file": name, "mode": "full", "cam": cam, **win})
                        continue
                    if name:
                        g = f.get("ground") or GROUND.get(b["set"], 0.8)
                        layers.append({"type": "rh_picture", "file": name, "mode": "subject", "x": f["x"], "ground": g,
                                       "height": round(min(0.97, f["size"] / 0.8), 3), "cam": cam, **win})
                        if f.get("tag"):
                            layers.append({"type": "rh_mark", "kind": "tag", "text": f["tag"], "x": f["x"], "y": round(g - f["size"] * 1.05, 3), "cam": cam,
                                           "color": "red", **win})
                        continue
                    f = {k: v for k, v in f.items() if k not in ("picture", "mode")}      # the file is missing: the code figure
                d = {k: v for k, v in f.items() if k not in ("subject", "picture", "mode", "cam_focus", "cam_zoom")}
                if d.get("animal"):
                    layers.append({"type": "rh_animal", "cam": cam, **d, **win})
                    if d.get("tag"):
                        layers.append({"type": "rh_mark", "kind": "tag", "text": d["tag"], "x": d["x"], "y": round(max(0.06, d["ground"] - d["size"] * 1.08), 3), "cam": cam, "color": "red", **win})
                    continue
                layers.append({"type": "rh_figure", "set": b["set"] if b["set"] != "none" else "door", "cam": cam, **d, **win})
            for m in b["marks"]:
                layers.append({"type": "rh_mark", "cam": cam, **m, **win})
            for c in b["captions"]:
                layers.append({"type": "rh_caption", "text": c["text"], "start": round(c["start"], 3), "end": round(c["end"], 3), **HARD})
        if b["glitch"]:
            bursts = [{"at": b["start"], "dur": 0.3, "amount": 1.0}]
            if b["end"] - b["start"] > 1.6:
                bursts.append({"at": round(b["end"] - 0.35, 3), "dur": 0.3, "amount": 0.8})
            layers.append({"type": "rh_glitch", "bursts": bursts, "start": b["start"], "end": b["end"], **HARD})
    layers.sort(key=lambda L: 1 if L["type"] == "rh_glitch" else 0)       # glitch last so it tears everything drawn before it
    spec = {"width": width, "height": height, "fps": fps, "duration": pl["duration"], "shots": shots, "layers": layers,
            "look": {"lift": "#000000", "saturate": 1, "contrast": 1, "vignette": 0.34, "grain": 0.05, **(look or {})}, "rh": {"scheme": scheme}}
    if media_dir:
        spec["media_dir"] = str(media_dir)
    return spec
