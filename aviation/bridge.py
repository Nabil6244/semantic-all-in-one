"""Aviation plan -> the shared renderer's timeline (cinematic_explainer.render: Shot list + Layer list + card_table).

    build_timeline(plan, scenes, pick_clip, black, map_extra=None) -> (shots, layers, report)
    card_table() -> {layer name: fn(t, dur, params)}   pass to render(..., card_table=card_table())

pick_clip(slot) -> {"path", "seek", "source"?, "duration"?} or None. The slot is the planner's footage dict (queries, cut, mode,
scene, start, end); the footage director decides with aviation.footage.clip_ok. It is called once per slot, in time order.
- full-frame cards (map, article, end card, document) sit on a black base clip (made once with ffmpeg, kept at `black`)
- a slot with no usable clip never goes black: it becomes a fact card of its own sentence (picture from the nearest clip if any,
  else the plain typeset page)
- a card whose picture is 'from footage' takes a frame of the nearest clip
- every borrowed clip gets the 'Source: X' tag when its source is known
The base shots are contiguous from 0 to the end; any hole is filled with black and counted in the report.
"""

from __future__ import annotations

import math
import subprocess
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from cinematic_explainer.render import Layer, Shot

_TABLE: Dict[str, Any] = {}


def card_table() -> Dict[str, Any]:
    if not _TABLE:
        from cinematic_explainer.war.graphics_lib import lay_document

        from . import cards, flightmap, gfx, gfx_air, hud
        _TABLE.update({
            "flightmap.lay_flight_map": flightmap.lay_flight_map,
            "hud.lay_hud": hud.lay_hud, "hud.lay_radio": hud.lay_radio,
            "cards.lay_article": cards.lay_article, "cards.lay_collage": cards.lay_collage, "cards.tag_source": cards.tag_source,
            "gfx.lay_counters": gfx.lay_counters, "gfx.lay_weather": gfx.lay_weather, "gfx.lay_place_title": gfx.lay_place_title,
            "gfx.lay_sheet": gfx.lay_sheet, "gfx.lay_altitude": gfx.lay_altitude, "gfx.lay_end_card": gfx.lay_end_card,
            "war.lay_document": lay_document,
            "gfx_air.lay_fleet": gfx_air.lay_fleet, "gfx_air.lay_network": gfx_air.lay_network, "gfx_air.lay_seats": gfx_air.lay_seats,
            "gfx_air.lay_change": gfx_air.lay_change, "gfx_air.lay_big_number": gfx_air.lay_big_number,
            "gfx_air.lay_timeline": gfx_air.lay_timeline, "gfx_air.lay_crew": gfx_air.lay_crew, "gfx_air.lay_gauge": gfx_air.lay_gauge,
            "gfx_air.lay_runway": gfx_air.lay_runway, "gfx_air.lay_approach": gfx_air.lay_approach,
            "gfx_air.lay_descent": gfx_air.lay_descent, "gfx_air.lay_title": gfx_air.lay_title,
        })
        from . import dossier, gfx_flight, retention, stage, transitions
        _TABLE.update(dossier.CARDS)
        _TABLE.update({
            "transitions.lay_out": transitions.lay_out,
            "stage.lay_stage": stage.lay_stage, "retention.lay_rehook": retention.lay_rehook,
            "gfx_flight.lay_instrument": gfx_flight.lay_instrument, "gfx_flight.lay_pip": gfx_flight.lay_pip,
            "gfx_flight.lay_speed_tape": gfx_flight.lay_speed_tape, "gfx_flight.lay_report": gfx_flight.lay_report,
        })
    return _TABLE


def _duration(path: str) -> float:
    try:
        return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                                             timeout=30).strip())
    except Exception:
        return 0.0


def ensure_black(path: str, seconds: float) -> str:
    p = Path(path)
    need = math.ceil(seconds) + 1
    if p.exists() and _duration(str(p)) >= need:
        return str(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c=black:s=1280x720:r=30:d={need}",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(p)], check=True, timeout=600)
    return str(p)


def build_timeline(plan: Any, scenes: Sequence[Dict[str, Any]], pick_clip: Callable[[dict], Optional[dict]], black: str,
                   map_extra: Optional[Dict[str, Any]] = None) -> Tuple[List[Shot], List[Layer], Dict[str, Any]]:
    text_of = {s.get("scene_no"): str(s.get("text") or "") for s in scenes}
    scene_of = {s.get("scene_no"): s for s in scenes}
    total = max([float(s["end"]) for s in scenes] + [0.0])
    base: List[Tuple[float, float, Optional[dict]]] = []          # (start, end, clip or None=black)
    layers: List[Layer] = []
    report = {"missing_footage": 0, "holes": 0, "clips": 0}
    pending_cards: List[Layer] = []

    for s in plan.shots:
        a, b = float(s["start"]), float(s["end"])
        if s.get("kind") == "footage":
            clip = pick_clip(dict(s))
            if clip and clip.get("duration") is not None:
                seek = float(clip.get("seek", 0.0))
                if float(clip["duration"]) - seek < b - a:
                    seek = max(0.0, float(clip["duration"]) - (b - a))
                    clip = dict(clip, seek=seek) if float(clip["duration"]) >= b - a else None
            if clip:
                base.append((a, b, clip))
                report["clips"] += 1
                if clip.get("source"):
                    layers.append(Layer("cards.tag_source", a, b, {"source": clip["source"]}))
            else:
                report["missing_footage"] += 1
                base.append((a, b, None))
                ly = Layer("cards.lay_article", a, b, {"fact": text_of.get(s.get("scene"), ""), "image_from": "footage", "_fallback": True,
                                                       "_scene": s.get("scene")})
                layers.append(ly)
                pending_cards.append(ly)
            continue
        params = dict(s.get("params") or {})
        if s.get("layer") == "flightmap.lay_flight_map" and map_extra:
            params.update(map_extra)
        if s.get("layer") == "cards.lay_article":
            params.setdefault("_scene", s.get("scene"))
        ly = Layer(s["layer"], a, b, params)
        layers.append(ly)
        if params.get("image_from") == "footage":
            own = pick_clip({"kind": "footage", "scene": s.get("scene"), "start": a, "end": b, "mode": s.get("mode"), "queries": []})
            if own:                                    # the card shows its own sentence's clip, not whatever clip is nearest
                params["video"] = own["path"]
                params["at"] = float(own.get("seek", 0.0)) + 0.5
        if s.get("full_frame"):
            base.append((a, b, None))
        if params.get("image_from") == "footage":
            pending_cards.append(ly)

    # merge fallback cards of the same sentence into one card (no flicker between slots)
    merged: List[Layer] = []
    for ly in layers:
        if ly.params.get("_fallback") and merged and merged[-1].params.get("_fallback") and \
                merged[-1].params.get("fact") == ly.params.get("fact") and abs(merged[-1].end - ly.start) < 1e-6:
            merged[-1].end = ly.end
            pending_cards = [c for c in pending_cards if c is not ly]
            continue
        merged.append(ly)
    layers = merged

    # pictures for cards: a frame of the nearest clip in time
    clips = sorted(((a, b, c) for a, b, c in base if c), key=lambda x: x[0])
    for ly in pending_cards:
        if ly.params.get("video"):
            ly.params.pop("image_from", None)
            ly.params.pop("_fallback", None)
            continue
        # no clip of its own: never a picture borrowed from another scene (an engraving and a meal tray once sat under Emirates'
        # profit figures) and never a text-only blue card either: the line becomes a short sticker-stage beat (its airline's
        # aircraft sticker, its own words as the caption, its year). An article with its own page keeps the typeset page.
        fb = ly.params.pop("_fallback", None)
        ly.params.pop("image_from", None)
        if fb or (ly.kind == "cards.lay_article" and ly.params.get("fact") and not ly.params.get("page")
                  and not ly.params.get("image")):    # a fact card with no picture of its own: the same stage beat
            from . import story as ST
            ly.kind = "stage.lay_stage"
            ly.params = ST.fallback_stage(str(ly.params.get("fact") or ""), ly.end - ly.start, scene=scene_of.get(ly.params.get("_scene")))

    # any fact card still without a picture (the planner's own number / fact cards never ask for one): the same stage beat
    from . import story as ST
    for ly in layers:
        if ly.kind == "cards.lay_article" and ly.params.get("fact") and not any(ly.params.get(k) for k in ("page", "image", "video")):
            ly.kind = "stage.lay_stage"
            ly.params = ST.fallback_stage(str(ly.params.get("fact") or ""), ly.end - ly.start, scene=scene_of.get(ly.params.get("_scene")))

    # contiguous base shots, holes filled with black
    base.sort(key=lambda x: x[0])
    longest_black = max([b - a for a, b, c in base if c is None] + [1.0])
    filled: List[Tuple[float, float, Optional[dict]]] = []
    t = 0.0
    for a, b, c in base:
        if a > t + 1e-6:
            filled.append((t, a, None))
            report["holes"] += 1
            longest_black = max(longest_black, a - t)
        if b <= t + 1e-6:
            continue
        filled.append((max(a, t), b, c))
        t = b
    if t < total - 1e-6:
        filled.append((t, total, None))
        report["holes"] += 1
        longest_black = max(longest_black, total - t)
    black_path = ensure_black(black, longest_black) if any(c is None for _, _, c in filled) else black
    shots = [Shot(c["path"] if c else black_path, a, b, float(c.get("seek", 0.0)) if c else 0.0) for a, b, c in filled]
    return shots, layers, report
