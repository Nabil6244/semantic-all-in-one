"""Build a map beat (plan data) from place names and the narration words of its own window. Every layer's time is the spoken start of its place plus an offset, and the
word match that supports it is returned as evidence. Raises PlanBuildError (strict) or returns the problems (non-strict). Draws nothing."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..captions.timing import resolve_caption
from .relevance import PlanBuildError, Word, beat_tokens, find_phrase, toks, _resolvable

MARKER_OFFSET_S, FILL_OFFSET_S, LINE_OFFSET_S = 0.1, 0.0, 0.0


def make_map_beat(beat_id: str, start: float, end: float, words: Sequence[Word], *, camera_start: Optional[Dict[str, str]] = None, fly_to: Sequence[Dict[str, Any]] = (),
                  markers: Sequence[Dict[str, Any]] = (), fills: Sequence[Dict[str, Any]] = (), lines: Sequence[Dict[str, Any]] = (), captions: Sequence[Dict[str, Any]] = (),
                  purpose: str = "", geo_intent: str = "", strict: bool = True, resolve_offline: bool = True, camera_steps: Sequence[Dict[str, Any]] = (),
                  zone_labels: Sequence[Dict[str, Any]] = (), stats: Sequence[Dict[str, Any]] = (), direction_cues: bool = True) -> Tuple[Dict[str, Any], Dict[str, Any], List[str]]:
    """Returns (beat dict in the Hybrid plan schema, evidence, problems). Item dicts:
    marker  {place, label=None (default PLACE), occurrence=1, offset_s=0.1, until='beat_end'}      fill {place, role='subject', occurrence, offset_s, until}
    line    {places=[a, b], kind, offset_s, until}                                              caption {text, anchor_word, occurrence=1, offset_s=0.0, role}
    fly_to  {place, dur=2.0, frame='region', t=None (default: the place's spoken start)}          camera_start {place, frame}
    camera_steps  [{action: fly_to|pull_back|push_in, t, dur, place?, frame?, zoom_delta?}] taken as given (explainer.beats.framing chooses them)
    zone_label {place, label=None (default PLACE), occurrence=1, offset_s=0.3}      stat {anchor_word, occurrence=1, value, unit (spoken words after the number, e.g. 'million people'), offset_s=0.0}"""
    tk = beat_tokens(words, start, end)
    problems: List[str] = []
    layers: List[Dict[str, Any]] = []
    camera: List[Dict[str, Any]] = []
    ev: Dict[str, Any] = {"beat": beat_id, "layers": [], "camera": []}
    if camera_start:
        camera.append({"action": "start", "place": camera_start["place"], "frame": camera_start.get("frame", "country")})
    n = 0

    def place_match(place: str, occ: int, what: str):
        m = find_phrase(tk, place, occ)
        if m is None:
            problems.append(f"beat {beat_id}: {what}: the place {place!r} is not spoken inside this beat's narration ({start:g} to {end:g} s)")
            return None
        if resolve_offline:
            ok, why = _resolvable(place)
            if not ok:
                problems.append(f"beat {beat_id}: {what}: the offline place lookup cannot find {place!r} ({why})")
                return None
        return m

    _seen_water: set = set()
    _mk: list = []
    for mk in markers:                                      # "Adriatic" and "Adriatic Sea" are one place: one marker, not two stacked on the same point
        _k = " ".join(w for w in str(mk["place"]).lower().split() if w not in ("sea", "ocean", "gulf", "bay"))
        if _k in _seen_water and _k != str(mk["place"]).lower():
            continue
        _seen_water.add(_k)
        _mk.append(mk)
    markers = [m_ for m_ in _mk if not any(o is not m_ and " ".join(w for w in str(o["place"]).lower().split() if w not in ("sea", "ocean", "gulf", "bay")) == " ".join(w for w in str(m_["place"]).lower().split() if w not in ("sea", "ocean", "gulf", "bay")) and len(str(o["place"])) > len(str(m_["place"])) for o in _mk)]
    for mk in markers:
        n += 1
        m = place_match(mk["place"], int(mk.get("occurrence", 1)), f"marker {n}")
        if m is None:
            continue
        t = round(m["start"] + float(mk.get("offset_s", MARKER_OFFSET_S)), 4)
        lay = {"id": f"{beat_id}_marker{n}", "type": "marker", "t": t, "place": mk["place"], "label": mk.get("label") or mk["place"].upper(), "until": mk.get("until", "beat_end")}
        layers.append(lay)
        ev["layers"].append({"layer": lay["id"], "type": "marker", "match": m, "t": t})
    for fl in fills:
        n += 1
        m = place_match(fl["place"], int(fl.get("occurrence", 1)), f"fill {n}")
        if m is None:
            continue
        t = round(m["start"] + float(fl.get("offset_s", FILL_OFFSET_S)), 4)
        lay = {"id": f"{beat_id}_fill{n}", "type": "fill", "t": t, "place": fl["place"], "role": fl.get("role", "subject"), "until": fl.get("until", "beat_end")}
        layers.append(lay)
        ev["layers"].append({"layer": lay["id"], "type": "fill", "match": m, "t": t})
    for ln in lines:
        n += 1
        ms = [place_match(p, 1, f"line {n}") for p in ln["places"]]
        if any(m is None for m in ms):
            continue
        t = round(max(m["start"] for m in ms) + float(ln.get("offset_s", LINE_OFFSET_S)), 4)
        lay = {"id": f"{beat_id}_line{n}", "type": "line", "t": t, "places": list(ln["places"]), "kind": ln["kind"], "until": ln.get("until", "beat_end")}
        layers.append(lay)
        ev["layers"].append({"layer": lay["id"], "type": "line", "matches": ms, "t": t})
    for cp in captions:
        n += 1
        a = find_phrase(tk, cp["anchor_word"], int(cp.get("occurrence", 1)))
        if a is None:
            problems.append(f"beat {beat_id}: caption {n}: the anchor word {cp['anchor_word']!r} is not spoken inside this beat")
            continue
        win = [i for i, (_w, s, _e) in enumerate(words) if s >= a["start"] - 1e-6 and s < end - 1e-6]
        ct = resolve_caption(f"{beat_id}_caption{n}", cp["text"], "words", a["start"], words, win, 0, None, end, end, 30)
        if ct.problems or ct.rung >= 3:
            problems.append(f"beat {beat_id}: caption {n}: {cp['text']!r} is not supported by the narration of this beat (rung {ct.rung}: {', '.join(ct.problems) or 'no phrase word spoken'})")
            continue
        t = round(ct.reveal_times[0] + float(cp.get("offset_s", 0.0)), 4)
        lay = {"id": f"{beat_id}_caption{n}", "type": "caption", "t": t, "text": cp["text"], "until": cp.get("until", "beat_end")}
        layers.append(lay)
        ev["layers"].append({"layer": lay["id"], "type": "caption", "caption": ct.to_dict(), "t": t})
    caps_ = sorted((l for l in layers if l["type"] == "caption"), key=lambda l: l["t"])
    for a_, b_ in zip(caps_, caps_[1:]):                     # one caption at a time: a later phrase replaces the one before it, they are never drawn on top of each other
        if b_["t"] - a_["t"] >= 0.5 and a_.get("until") == "beat_end":
            a_["until"] = round(b_["t"], 4)
    for zl in zone_labels:
        n += 1
        m = place_match(zl["place"], int(zl.get("occurrence", 1)), f"zone label {n}")
        if m is None:
            continue
        t = round(m["start"] + float(zl.get("offset_s", 0.3)), 4)
        lay = {"id": f"{beat_id}_zone{n}", "type": "zone_label", "t": t, "place": zl["place"], "label": zl.get("label") or zl["place"].upper(), "until": zl.get("until", "beat_end")}
        layers.append(lay)
        ev["layers"].append({"layer": lay["id"], "type": "zone_label", "match": m, "t": t})
    if direction_cues:
        from .geography import direction_cue
        from .framing import _geo
        for ly in list(layers):                                  # "look east across the Adriatic": the named water or region gets a flow line across it in that direction
            if ly["type"] not in ("marker", "zone_label", "fill") or any(x["id"].endswith("_dir1") for x in layers):
                continue
            m = find_phrase(tk, ly["place"], 1)
            cue = direction_cue(tk, ly["place"], m, _geo().resolve) if m else None
            if cue:
                n += 1
                lay = {"id": f"{beat_id}_dir1", "type": "line", "t": max(float(start), cue["t"]), "places": cue["places"], "kind": "flow", "until": "beat_end"}
                layers.append(lay)
                ev["layers"].append({"layer": lay["id"], "type": "line", "direction": cue["direction"], "toward": ly["place"], "t": lay["t"]})
    for st in stats:
        n += 1
        phrase = f"{st['anchor_word']} {st.get('unit', '')}".strip()
        m = find_phrase(tk, phrase, int(st.get("occurrence", 1)))
        if m is None:
            problems.append(f"beat {beat_id}: stat {n}: {phrase!r} is not spoken inside this beat's narration")
            continue
        t = round(m["start"] + float(st.get("offset_s", 0.0)), 4)
        unit = str(st.get("unit", "")).upper()
        lay = {"id": f"{beat_id}_stat{n}", "type": "stat", "t": t, "from": 0.0, "to": float(st["value"]), "format": ("0%" if unit == "PERCENT" else f"0 {unit}".strip()), "anchor": st.get("anchor", "br"),
               "until": st.get("until", "beat_end")}
        layers.append(lay)
        ev["layers"].append({"layer": lay["id"], "type": "stat", "match": m, "t": t, "value": float(st["value"]), "unit": unit})
    for cs in camera_steps:
        camera.append(dict(cs))
        ev["camera"].append({"place": cs.get("place", ""), "t": float(cs["t"]), "action": cs["action"]})
    for fl in fly_to:
        n += 1
        t = fl.get("t")
        if t is None:
            m = place_match(fl["place"], 1, f"fly_to {n}")
            if m is None:
                continue
            t = round(m["start"], 4)
        camera.append({"action": "fly_to", "t": float(t), "dur": float(fl.get("dur", 2.0)), "place": fl["place"], "frame": fl.get("frame", "region")})
        ev["camera"].append({"place": fl["place"], "t": float(t)})
    beat = {"id": beat_id, "mode": "map", "start": float(start), "end": float(end), "purpose": purpose, "geo_intent": geo_intent, "camera": camera, "layers": layers}
    beat = {k: v for k, v in beat.items() if v not in ("", [], None)}
    if problems and strict:
        raise PlanBuildError(problems)
    return beat, ev, problems
