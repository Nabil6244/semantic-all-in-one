"""Mixed pace: AI scenes (stills with a slow push, a few clips) and our 3D shots in one What If spec.

    plan_mixed(data, pack, results, ...) -> spec

`pack` is product_trailer.scenepack.plan_scene_pack(); `results` is what generate_scene_pack() returned ({scene n: {"status", "path"}}) plus,
optionally, {"clips": {scene n: path}}. A scene whose picture is missing or failed becomes a 3D lineup shot, so a film never stops on a
Flow failure. The chip and anything with numbers stay 3D. One caption per shot, a title shot first, "Introducing" + name, then the card.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

SHOT_S = 6.0
ROOMS = ["loft", "gallery", "studio", "terrace"]
POSES = ["back", "front", "mixed", "fan"]
LOOK = {"saturate": 0.97, "contrast": 1.04, "lift": "#05070B", "vignette": 0.22, "grain": 0.025}
DRIFT_IN = {"from": 1.0, "to": 1.07, "fx": 0.5, "fy": 0.5}
DRIFT_OUT = {"from": 1.07, "to": 1.0, "fx": 0.5, "fy": 0.5}
INTRO_S, CARD_S = 6.0, 4.0


def _caption(f: Dict[str, Any]) -> str:
    return " ".join(p for p in (f.get("kicker"), f.get("value") or str(f.get("feature", "")).title(), f.get("sub")) if p)


def plan_mixed(data: Dict[str, Any], pack: Dict[str, Any], results: Optional[Dict[Any, Any]] = None, *, media_dir: Optional[Path] = None,
               width: int = 1920, height: int = 1080, fps: int = 30, shot_s: float = SHOT_S, edges: Optional[Sequence[float]] = None) -> Dict[str, Any]:
    prod = data.get("product") or {}
    phone = pack.get("phone") or prod.get("phone") or "galaxy s27 ultra"
    cols = list(pack.get("colours") or [])
    results = results or {}
    clips = results.get("clips", {}) if isinstance(results.get("clips"), dict) else {}
    shots: List[Dict[str, Any]] = []
    layers: List[Dict[str, Any]] = []
    notes: List[str] = []
    t = 0.0
    media = Path(media_dir) if media_dir else None

    def add(shot: Dict[str, Any], length: float) -> Dict[str, Any]:
        nonlocal t
        s = {"id": f"s{len(shots) + 1:02d}", "start": round(t, 3), "end": round(t + length, 3), "exit": "cut", **shot}
        shots.append(s)
        t += length
        return s

    def lineup(i: int, **extra) -> Dict[str, Any]:
        return {"kind": "product", "object": "lineup", "phone": phone, "colors": cols, "room": ROOMS[i % len(ROOMS)], "pose": POSES[i % len(POSES)],
                "wordmark": prod.get("wordmark", ""), "push": [7.4, 6.5] if i % 2 == 0 else [6.5, 7.4], "seed": 11 + i, **extra}

    # a title shot: the lineup turning from backs to fronts
    s0 = add(lineup(0, pose="back", turn=[0.45, 0.8]), INTRO_S)
    layers.append({"type": "pt_caption", "text": prod.get("name") or phone.title(), "start": 0.8, "end": INTRO_S - 0.4})

    scenes = pack.get("scenes", [])
    for k, sc in enumerate(scenes):
        length = shot_s if edges is None or k + 1 >= len(edges) else max(2.0, float(edges[k + 1]) - float(edges[k]))
        n = sc["n"]
        feat = data["features"][k] if k < len(data.get("features", [])) else {"feature": sc.get("feature"), "value": sc.get("caption")}
        res = results.get(n) or {}
        pic = res.get("path") if res.get("status") == "done" else None
        if sc["source"] == "3d":
            if str(sc.get("feature", "")).lower() in ("chip", "performance", "processor", "cpu", "gpu", "soc"):
                s = add({"kind": "product", "object": "chip", "move": "chip", "label": str(feat.get("value") or "Chip").upper(), "sublabel": "Reported",
                         "glow": "#3ac8ff", "heat": [0.0, 0.3], "seed": 31 + k}, length)
            else:
                s = add(lineup(k + 1), length)
        elif pic and Path(pic).is_file():
            clip = clips.get(n) if sc["source"] == "ai_clip" else None
            if clip and Path(clip).is_file():
                name = f"scene_{n:03d}_clip{Path(clip).suffix or '.mp4'}"
                _copy(clip, media, name)
                s = add({"kind": "video", "file": name, "loop": True}, length)
            else:
                name = f"scene_{n:03d}{Path(pic).suffix or '.png'}"
                _copy(pic, media, name)
                s = add({"kind": "image", "file": name, "fit": "cover", "drift": dict(DRIFT_IN if k % 2 == 0 else DRIFT_OUT)}, length)
        else:
            notes.append(f"scene {n} ({sc.get('type') or 'AI'}) had no picture: a 3D lineup shot was used")
            s = add(lineup(k + 1), length)
        layers.append({"type": "pt_caption", "text": _caption(feat), "start": round(s["start"] + 0.6, 3), "end": round(s["end"] - 0.4, 3)})

    sr = add(lineup(len(scenes) + 1, pose="front", frame_side="right"), INTRO_S)
    layers.append({"type": "pt_reveal", "kicker": prod.get("intro", "Introducing"), "name": prod.get("name", ""), "side": "left",
                   "start": round(sr["start"] + 0.3, 3), "end": round(sr["end"] - 0.1, 3)})
    card = [x for x in (prod.get("disclaimer"),) if x]
    if card:
        shots.append({"id": f"s{len(shots) + 1:02d}", "start": round(t, 3), "end": round(t + CARD_S, 3), "kind": "black", "exit": "cut"})
        layers.append({"type": "pt_card", "lines": card, "start": round(t + 0.2, 3), "end": round(t + CARD_S, 3)})
        t += CARD_S
    spec = {"width": int(width), "height": int(height), "fps": int(fps), "duration": round(t, 3), "look": dict(LOOK), "shots": shots, "layers": layers,
            "whatif": {"title": prod.get("name", "Product film"), "notes": notes}, "product_trailer": {"pace": "mixed", "product": prod}}
    if media:
        spec["media_dir"] = str(media)
    return spec


def _copy(src, media: Optional[Path], name: str) -> None:
    if media is None:
        return
    media.mkdir(parents=True, exist_ok=True)
    dst = media / name
    if not dst.exists() or dst.stat().st_size != Path(src).stat().st_size:
        shutil.copyfile(src, dst)
