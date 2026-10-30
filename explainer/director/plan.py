"""direct(): narration words (+ script) -> a Hybrid plan whose board beats are explainer clips. Never raises; failures come back as problems with plan=None."""

from __future__ import annotations

import hashlib
import json
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from ..beats import assemble_plan, check_plan, make_archive_beat, make_map_beat
from ..beats import framing as FR
from ..board import build_board_clip
from ..board.dry import dry_build
from ..board.cues import SCHEMA_VERSION
from ..narrator import rig
from . import compose as CP
from . import lexicon as LX
from . import pacing as PC
from . import segment as SG
from . import select as SL
from .options import EXPLAINER_VERSION, DirectorOptions

Word = Tuple[str, float, float]


@dataclass
class DirectorResult:
    plan: Optional[Dict[str, Any]]
    report: Dict[str, Any] = field(default_factory=dict)
    problems: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def _cue_key(c) -> Dict[str, Any]:
    return {"id": c.id, "kind": c.kind, "anchor": c.anchor, "text": c.text, "role": c.role, "offset_s": c.offset_s, "asset": c.asset, "src": c.src, "dst": c.dst,
            "slot": c.slot, "pos": c.pos, "params": c.params, "cps": c.cps}


OPT_OMIT_WHEN_OFF = ("scene_intel", "scene_flow_share", "scene_notes", "alive", "meaning", "recipes", "continuity", "animate", "pictures", "motion", "numbers", "maplines", "variety", "budget", "fill", "sound", "dialogue", "scenes2", "mapoverlay", "camera", "texture")        # opt-in switches: absent from the report while off, so a disabled report is unchanged


def _finish_key(opt: DirectorOptions) -> Dict[str, Any]:
    """The opt-in camera and texture are part of a board clip's identity; both off adds nothing, so every earlier clip name stays."""
    out: Dict[str, Any] = {}
    if getattr(opt, "camera", "off") not in ("off", "", None, False):
        out["camera"] = opt.camera
    if getattr(opt, "texture", False):
        from ..motion import texture as _TX
        out["texture"] = [str(opt.texture), _TX.manifest_digest()]
    return out


def clip_name(cues, beat_words, start: float, end: float, opt: DirectorOptions, beat_id: str, background: Optional[str] = None) -> str:
    background = opt.background if background is None else background
    nstyle = next(((c.params or {}).get("style", "cartoon") for c in cues if c.kind == "narrator" and (c.params or {}).get("action") == "show"), "cartoon")
    man = rig.load_assets(nstyle).manifest_sha256 if any(c.kind == "narrator" for c in cues) else ""
    if any(c.kind == "visual" and (c.params or {}).get("style") in ("set", "figure", "crowd", "prop") for c in cues):      # the cartoon kit: an edited asset must not reuse an old clip
        from ..cartoon import kit
        man += kit.manifest()["layers_digest"]
        from ..cartoon import characters as _ch
        if any((c.params or {}).get("cast") in _ch.types() or (c.params or {}).get("kind") in _ch.types() for c in cues if c.kind == "visual"):      # a character: an edited pack must not reuse an old clip
            man += _ch.layers_digest()
    if any(c.kind == "visual" and (c.params or {}).get("style") == "stamp" and (c.params or {}).get("texture") for c in cues):      # the motion kit: an edited texture must not reuse an old clip
        from ..motion import sprites as MS
        man += hashlib.sha256(json.dumps(MS.manifest().get("masks", {}), sort_keys=True).encode()).hexdigest()[:16]
    blob = json.dumps({"v": EXPLAINER_VERSION, "schema": SCHEMA_VERSION, "assets": man, "id": beat_id, "cues": [_cue_key(c) for c in cues], "words": [[w[0], round(w[1], 4), round(w[2], 4)] for w in beat_words],
                       "start": round(start, 4), "end": round(end, 4), "dissolve": opt.dissolve_s, "fps": opt.fps, "size": list(opt.size),
                       **({"bg": background} if background != "grey" else {}), **_finish_key(opt)}, sort_keys=True, default=str)
    return f"board_{hashlib.sha256(blob.encode()).hexdigest()[:16]}.mp4"


def direct(words: Sequence[Word], script: Optional[str] = None, options: Optional[DirectorOptions] = None, *, duration: Optional[float] = None,
           materialize: bool = True, log: Callable[[str], None] = lambda m: None) -> DirectorResult:
    opt = options or DirectorOptions()
    try:
        return _direct(words, script, opt, duration, materialize, log)
    except Exception as exc:                                              # never raise into the application
        return DirectorResult(None, {"exception": traceback.format_exc(limit=6)}, [f"the explainer director failed: {exc!r}"], [])

# pakMap's own fill roles in the order countries meet them: bright red, gold, purple, orange, then green and blue (which sit weakly on satellite land and sea; the dark "primary" brown is never used)
FILL_PALETTE = ("red", "featured", "accent", "orange", "green", "compare", "water", "primary")      # the last two only when a video fills more than six countries
MAX_TEXT_LAYERS = 5               # pakMap's renderer rule: at most five text objects (marker or zone label, caption, stat, title) on screen at once
LABEL_HOLD_S = 2.2
LABEL_MIN_S = 0.8


def _cap_text_layers(beat: Dict[str, Any], info: Dict[str, Any], beat_id: str) -> None:
    """On a world view every country is filled, but each zone label stays only about 2 s, and the labels alive together never push the text layers on screen past the renderer's five (captions,
    statistics and markers count too). A label that cannot keep its place for at least 0.8 s is left out and the reason recorded; its country stays filled in its own colour."""
    end = float(beat["end"])
    lays = beat.get("layers", [])

    def stop(l: Dict[str, Any]) -> float:
        u = l.get("until", "beat_end")
        e = end if u == "beat_end" else float(u)
        return min(e, l["t"] + float(l["hold"])) if l.get("hold") else e

    others = [l for l in lays if l["type"] in ("marker", "caption", "stat", "hud_title")]
    weight = lambda l: (2 if l.get("sub") else 1) if l["type"] in ("marker", "hud_title") else 1
    labels = sorted((l for l in lays if l["type"] == "zone_label"), key=lambda l: (l["t"], l["id"]))
    keep: List[Dict[str, Any]] = []
    for l in labels:
        t0 = float(l["t"])
        t1 = min(end, t0 + LABEL_HOLD_S)
        marks = [t0] + [x["t"] for x in others if t0 < x["t"] < t1]
        room_o = max(sum(weight(x) for x in others if x["t"] <= m + 1e-9 and stop(x) > m + 1e-9) for m in marks)
        cap = MAX_TEXT_LAYERS - room_o
        alive = [k for k in keep if stop(k) > t0 + 1e-9]
        l["until"] = round(t1, 3)
        while len(alive) >= max(cap, 0) and alive:
            first = alive.pop(0)
            if t0 - first["t"] >= LABEL_MIN_S:
                first["until"] = round(t0, 3)
            else:                                      # the earliest label has not been up long enough: this one yields instead
                alive.insert(0, first)
                break
        if len(alive) >= max(cap, 0) or t1 - t0 < LABEL_MIN_S:
            lays.remove(l)
            info.setdefault("map_labels_skipped", []).append({"beat": beat_id, "place": l.get("place"), "reason": f"the renderer allows {MAX_TEXT_LAYERS} text layers on screen at once; this label would be the {len(alive) + room_o + 1}th"})
            continue
        keep.append(l)
    for k in keep:                                     # a label shortened above keeps at least LABEL_MIN_S (guaranteed by the test above)
        if stop(k) - k["t"] < LABEL_MIN_S - 1e-9:
            lays.remove(k)
            info.setdefault("map_labels_skipped", []).append({"beat": beat_id, "place": k.get("place"), "reason": "it could not stay on screen long enough"})


_QUANTITY = ("million", "billion", "thousand", "trillion", "percent", "hundred")


WATER_KINDS = ("sea", "ocean", "gulf", "strait", "bay", "water")      # a body of water is the map itself, not a photograph
CARD_MIN_BEAT_S = 3.5
CARD_MAX_SAME = 2


def _map_cards(b, words, hits, info: Dict[str, Any], opt, n_labels: int = 0) -> List[Dict[str, Any]]:
    """Small photo cards for a map beat (Hybrid's own `support` and `more_cards`: a card on the map with a leader line to its place): each named person or event spoken in the beat (a portrait, a
    painting) and each specific place (a city, an island, a river; a country or a continent is already the map). Every query word is spoken inside the beat, the card appears on the first of
    them and stays to the end of the beat; one subject is not carded more than twice in a video, and a beat shows at most three."""
    from ..beats.relevance import beat_tokens as _bt, toks as _toks
    from .lexicon import FOOTAGE_STILL_SOURCES
    if b.dur < CARD_MIN_BEAT_S or b.start < 1.0:      # the opening map stays clean
        return []
    tk = _bt(words, b.start, b.end)
    btoks = [t["tok"] for t in tk]
    named = set(info.get("named_subjects", ()))
    lead = next((h.name for h in hits if h.kind not in ("region",) and h.name.lower() not in {"republic", "europe", "asia"}), "")      # the place a person's card points to
    wants: List[Tuple[str, str, str]] = []              # (query, label, leader place)
    i = 0
    if opt.pictures:                                    # opt-in: full names from the script ("Napoleon Bonaparte"), at most two cards with a name caption, the second only when the beat is long and the map is not crowded with labels
        from . import compose_pictures as CPX
        pic = info.get("pictures", {})
        wants = [(q_, l_, lead) for q_, l_ in CPX.map_card_names(btoks, pic.get("phrases", []), named, pic.get("cased", {}), info.setdefault("map_card_count", {}))]
        i = len(btoks)
        water = {w for h in hits if h.kind in WATER_KINDS for w in (h.name.lower(), h.name.lower().replace(" sea", ""))}
        wants = [w_ for w_ in wants if w_[0].lower() not in water]
    while i < len(btoks):
        if btoks[i] in named:
            q = [btoks[i]] + ([btoks[i + 1]] if i + 1 < len(btoks) and btoks[i + 1] in named else [])
            wants.append((" ".join(q), " ".join(q).upper(), lead))
            i += len(q)
        else:
            i += 1
    for h in hits:
        if h.kind not in ("country", "region", "county", *WATER_KINDS) and h.name.lower() not in {"republic", "europe", "asia"}:      # a body of water is the map itself, not a photograph
            wants.append((h.name.lower(), h.name.upper(), h.name))
    src = opt.footage_source if opt.footage_source in FOOTAGE_STILL_SOURCES else "stock_image"
    used = info.setdefault("map_card_count", {})
    out: List[Dict[str, Any]] = []
    last_t = -9.0
    for query, label, place in wants:
        if len(out) >= (2 if opt.pictures else 3) or (opt.pictures and len(out) == 1 and (b.dur < 5.0 or n_labels > 2)) or any(c["asset"] == f"{src}:{query}" for c in out) or used.get(query.lower() if opt.pictures else query, 0) >= CARD_MAX_SAME or not _toks(query):
            continue
        first = next((t for t in tk if t["tok"] == _toks(query)[0]), None)
        if first is None:
            continue
        t = max(b.start + 0.4, float(first["start"]) - 0.2, last_t + 0.9)
        if t > b.end - 1.2:
            continue
        uk = query.lower() if opt.pictures else query
        used[uk] = used.get(uk, 0) + 1
        last_t = t
        q_asset = query
        if opt.pictures:                                # a narration before 1800: a stock photograph of a place is the modern one, so the search asks for old art (only when the relevance gate accepts the era words)
            from . import compose_pictures as CPX_
            era_ = CPX_.era_of_beat(words, b)
            mod_ = CPX_.era_modifier(era_["year"])
            if mod_ and CPX_.relevance_accepts_era():
                q_asset = query + " " + " ".join(mod_)
        card = {"asset": f"{src}:{q_asset}", "t": round(t, 3), "label": label, "reason": f"shows {query}: the narration says it here"}
        if place:
            card["place"] = place
        out.append(card)
    return out


def _stats_for(b, words) -> List[Dict[str, Any]]:
    """At most one statistic for a map beat: a whole number spoken with a quantity word ("40 million people", "30 percent"), never a year. Its words are quoted from the narration."""
    from ..beats.relevance import beat_tokens
    tk = beat_tokens(words, b.start, b.end)
    for i, t in enumerate(tk[:-1]):
        if t["tok"].isdigit() and tk[i + 1]["tok"] in _QUANTITY and int(t["tok"]) < 1000 and int(t["tok"]) > 0:
            unit = [tk[i + 1]["tok"]]
            if tk[i + 1]["tok"] != "percent" and i + 2 < len(tk) and tk[i + 2]["tok"] not in LX.STOP and tk[i + 2]["tok"] not in LX.WEAK and not tk[i + 2]["tok"].isdigit():
                unit.append(tk[i + 2]["tok"])
            return [{"anchor_word": t["tok"], "unit": " ".join(unit), "value": int(t["tok"]), "occurrence": 1}]
    return []


def scene_intel_pass(beats, words, opt: DirectorOptions, SI) -> Dict[str, Any]:
    """Read every cartoon beat (its words, then the CSV scene note over it when there is one) and turn the ones the library cannot show truthfully into Flow image beats, up to
    `opt.scene_flow_share` of the runtime. Returns the per-beat record for the report. Never raises: a beat that cannot be read stays as it was."""
    full = " ".join(str(w[0]) for w in words)
    ctx = SI.from_words(full).year
    total = sum(b.end - b.start for b in beats) or 1.0
    used, rec = 0.0, {}
    for b in beats:
        if b.kind != "cartoon":
            continue
        try:
            text = " ".join(s_.text for s_ in b.sents)
            spec = SI.from_words(text, context_year=ctx)
            mid = (b.start + b.end) / 2
            note = " ; ".join(n["text"] for n in opt.scene_notes if n["start"] - 1e-6 <= mid < n["end"] + 1e-6)
            spec = SI.from_notes(note, spec) or spec
            d = SI.decide(spec)
            entry = {"route": d.route, "set": d.set_name, "reasons": d.reasons, "source": spec.source, "year": spec.year, "place_type": spec.place_type}
            if d.route == "flow":
                if (used + (b.end - b.start)) / total <= opt.scene_flow_share:
                    used += b.end - b.start
                    b.kind, b.source, b.picture_query = "footage", "flow_image", SI.flow_prompt(spec)
                    entry["prompt"] = b.picture_query
                else:
                    entry["route"] = "cartoon (Flow share reached)"
                    b.notes.append("scene needs a Flow image but the share of runtime is used up: kept as a cartoon")
            rec[b.id] = entry
        except Exception as exc:
            b.notes.append(f"scene reading failed, beat unchanged: {exc}")
    return rec


def _direct(words, script, opt: DirectorOptions, duration, materialize, log) -> DirectorResult:
    words = [(str(w[0]), float(w[1]), float(w[2])) for w in words]
    res = DirectorResult(None)
    if not words:
        res.problems.append("no narration words")
        return res
    total = float(duration) if duration else words[-1][2] + 0.3
    sents = SG.sentences(words, script, total, opt.split_over_s)
    if not sents:
        res.problems.append("no sentences found in the narration")
        return res
    from ..board import backdrops as _BD
    if opt.background not in _BD.STYLES:
        res.problems.append(f"unknown background {opt.background!r} (use {', '.join(_BD.STYLES)})")
        return res
    if opt.narrator_style not in ("serious", "cartoon"):
        res.problems.append(f"unknown narrator style {opt.narrator_style!r} (serious or cartoon)")
        return res
    if (opt.footage_share > 0 or opt.pictures) and opt.footage_source not in LX.FOOTAGE_SOURCES:
        res.problems.append(f"unknown footage source {opt.footage_source!r} (use one of {', '.join(LX.FOOTAGE_SOURCES)})")
        return res
    SG.label_sentences(sents, words, script)
    SG.compute_breaks(sents, words)
    cased = SG.casing(script)
    table = {**LX.ICONS, **{k.lower(): v for k, v in opt.metaphors.items()}}
    if opt.scenes2:
        try:
            from .compose_cartoon import _v2_ready
            if _v2_ready():
                from . import lexicon_v2 as LV2
                table = {**LX.ICONS, **LV2.scenes2_tables()["icons"], **{k.lower(): v for k, v in opt.metaphors.items()}}
        except Exception as exc:                 # never stop: the v1 table is used
            info_scenes2 = f"scenes2 icons not merged: {exc}"
            res.warnings.append(info_scenes2)
    roles = {k.lower(): v for k, v in opt.roles.items()}
    beats = SL.group(sents, total, opt)
    info = SL.choose_kinds(beats, words, script, total, opt)
    res.warnings += info.pop("warnings", [])
    out_dir = Path(opt.work_dir) / "explainer" if opt.work_dir else None
    if materialize and out_dir is None:
        res.problems.append("work_dir is needed to write the board clips")
        return res
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)
        from ..beats import map_narrator as MN
        (MN.write_marker(out_dir, opt.narrator_style) if opt.narrator else MN.clear_marker(out_dir))      # the presenter over the map stretches is laid on after the map is drawn

    # ---- narrator runs over board beats (kinds are final after map/archive building, so build those first) ----
    plan_beats: List[Dict[str, Any]] = []
    sentence_ends = {s_.widx[-1] for s_ in sents}                  # a phrase never runs across the end of a sentence, in a repair as in the first pass
    evidence_subjects: Dict[str, Dict[str, List[str]]] = {}
    beat_notes: Dict[str, Any] = {}
    motion_state: Dict[str, Any] = {"stamps": [], "plates": []}
    if opt.budget:
        from ..motion.budget import Budget
        motion_state["budget"] = Budget()
    first_map = True
    cur_view = None
    country_roles: Dict[str, str] = {}      # each filled country keeps one colour for the whole video (the same recurring-metaphor rule as the picture roles)
    map_places_done = set()
    info.setdefault("map_layers_rejected", [])
    if opt.scene_intel:                                  # opt-in: read each cartoon beat; what the library cannot show truthfully becomes a Flow image beat (capped by share of runtime)
        from .. import scene_intel as SI
        info["scene_intel"] = scene_intel_pass(beats, words, opt, SI)
    for b in beats:
        if b.kind == "map":
            try:
                pl = b.places[0]
                all_hits = [h for h in b.places if h.match]
                hits = all_hits[:8] if len(all_hits) >= 4 else all_hits[:3]          # a sentence that lists many countries is drawn whole (up to 8) on one world view
                bstart = b.start + (opt.dissolve_s / 2)
                cam = FR.plan_camera([{"name": h.name, "t": h.match["start"]} for h in hits], bstart, b.end, first_map, cur_view)
                _i = beats.index(b)
                if not first_map and _i and beats[_i - 1].kind != "map" and cam["moves"] and cam["moves"][0]["action"] == "fly_to":      # the map comes in after a full-screen board: the camera sat still at its old (globe) view meanwhile, so the first move is a cut, not a flight through the globe
                    cam["moves"][0].update(t=round(b.start, 3), dur=0.04)
                for rj in cam["rejected"]:
                    b.notes.append(f"{rj['place']} is not drawn: {rj['reason']}")
                    info["map_layers_rejected"].append({"beat": b.id, **rj})
                shown = [h for h in hits if h.name not in {r_["place"] for r_ in cam["rejected"]}]
                for note in cam["notes"]:
                    b.notes.append("camera: " + note)
                markers, fills, zones = [], [], []
                drawn: set = set()                      # the places that really got a fill or a marker on this map (a relation line joins only these)
                label_boxes: List[Tuple[str, Tuple[float, float, float, float]]] = []
                for h in shown:
                    wait = max(0.0, cam["ready"].get(h.name, 0.0) - h.match["start"])      # the layer waits until the camera is where the place can be seen
                    if wait > 0.5:
                        b.notes.append(f"{h.name} is not drawn: the camera is ready at {cam['ready'][h.name]:.1f} s, long after the word at {h.match['start']:.1f} s")
                        info["map_layers_rejected"].append({"beat": b.id, "place": h.name, "reason": "the camera cannot show it in time"})
                        continue
                    if h.kind == "country":
                        if h.name not in country_roles:
                            country_roles[h.name] = FILL_PALETTE[len(country_roles) % len(FILL_PALETTE)]
                        fills.append({"place": h.name, "offset_s": round(wait, 3), "role": country_roles[h.name]})
                        drawn.add(h.name)
                        if cam.get("wide") and cam.get("view"):          # on a world view the names must not pile up: a label that would sit on an earlier one is left out, and why is recorded
                            try:
                                from ..beats import framing as _fr
                                loc = _fr._geo().resolve(h.name)
                                cx, cy = _fr.project(loc.lon, loc.lat, cam["view"])
                                lw = 15 * len(h.name) + 30
                                box = (cx - lw / 2 - 6, cy - 24, cx + lw / 2 + 6, cy + 24)
                                clash = next((n_ for n_, o_ in label_boxes if not (box[2] < o_[0] or o_[2] < box[0] or box[3] < o_[1] or o_[3] < box[1])), None)
                                if clash or not (60 <= cx <= 1860 and 60 <= cy <= 1020):
                                    why = f"its label would sit on the label of {clash}" if clash else "its centre is too near the edge of the frame for a label"
                                    info.setdefault("map_labels_skipped", []).append({"beat": b.id, "place": h.name, "reason": why})
                                    b.notes.append(f"{h.name} is outlined but not labelled: {why}")
                                    continue
                                label_boxes.append((h.name, box))
                            except Exception:
                                pass
                        zones.append({"place": h.name, "offset_s": round(max(0.3, wait + 0.3), 3)})
                    else:
                        markers.append({"place": h.name, "offset_s": round(max(0.1, wait), 3)})
                        drawn.add(h.name)
                map_lines: List[Dict[str, Any]] = []
                if opt.maplines:
                    from .compose_maplines import relation_lines
                    map_lines, ln_notes = relation_lines([h for h in shown if h.name in drawn], cam, words, sents, {h.name: max(0.0, cam["ready"].get(h.name, 0.0) - h.match["start"]) for h in shown})
                    b.notes += ln_notes
                    if map_lines and "budget" in motion_state:
                        ok_b, why_b = motion_state["budget"].allow("line", b.start)
                        if ok_b:
                            motion_state["budget"].commit("line", b.start)
                        else:
                            b.notes.append("map line not drawn: " + why_b)
                            map_lines = []
                stats = _stats_for(b, words)
                frame = ("continental" if FR._is_continent(pl.name) else "country") if pl.kind in ("country", "region") else "region"
                if not hits:                                    # no place with a spoken word (the arbitrary opening map): its own camera, nothing to draw
                    cam = {"start": {"place": pl.name, "frame": frame} if first_map else None, "moves": [{"action": "fly_to", "t": round(bstart + 0.05, 3), "dur": 2.0, "place": pl.name, "frame": frame}] if not first_map else [], "view": None}
                caps: List[Dict[str, Any]] = []
                for _round in range(3):          # still-time repair for maps: a whole-phrase caption of the words inside the longest gap (the camera drift is not counted as a change)
                    beat, ev, probs = make_map_beat(b.id, b.start, b.end, words, camera_start=cam["start"] if first_map else None, fills=fills, markers=markers, zone_labels=zones, lines=map_lines,
                                                    stats=stats, camera_steps=cam["moves"], captions=caps, purpose="map: " + ", ".join(h.name for h in b.places),
                                                    geo_intent="where " + pl.name + " is", strict=False)
                    if probs:
                        b.notes += probs
                        raise ValueError("; ".join(probs))
                    ts = sorted({b.start, b.end, *[l["t"] for l in beat.get("layers", [])], *[c["t"] for c in beat.get("camera", []) if c["action"] != "start"]})
                    gap, a0, a1 = max((y - x, x, y) for x, y in zip(ts, ts[1:]))
                    if gap <= opt.max_still_s:
                        break
                    # a map caption layer is one whole phrase that must stay up long enough to read (Hybrid's own editorial check wants about 2 s before the beat ends)
                    cands_ = CP.best_phrases([i for i, w in enumerate(words) if a0 + 0.6 <= w[1] <= min(a1 - 0.5, b.end - 2.6)], words, cased, table, sentence_ends | set().union(*[s_.breaks for s_ in sents]), k=1, max_words=6,
                                             min_score=4.0, min_words=2, strict_edges=True)
                    kp = cands_[0] if cands_ else None
                    if kp is None or any(kp.text.lower() in c_["text"].lower() for c_ in caps):      # a phrase already on screen is not repeated as a fragment
                        break
                    occ = 1 + sum(1 for w in words if b.start - 1e-6 <= w[1] < words[kp.first][1] - 1e-9 and SG.norm(w[0]) == kp.tokens[0])
                    caps.append({"text": kp.text, "anchor_word": kp.tokens[0], "occurrence": occ})
                    b.notes.append(f"map still-time repair: caption {kp.text!r} inside a {gap:.1f} s gap")
                if first_map and not pl.match:
                    beat["camera"] = [{"action": "start", "place": pl.name, "frame": frame}]
                if cam.get("wide"):
                    _cap_text_layers(beat, info, b.id)
                bad = FR.check_framing({"beats": [x for x in plan_beats if x and x.get("mode") in ("map", "map_footage")] + [beat]}) if hits else []
                if bad:                                         # the geometry said it fits and the check says it does not: never render it, say so
                    raise ValueError("camera framing: " + "; ".join(bad))
                cur_view = cam.get("view") or cur_view
                if opt.footage_share > 0 or opt.pictures:       # the picture sources are on: the map gets small photo cards of who and what the sentence names (map_footage)
                    cards = _map_cards(b, words, hits, info, opt, n_labels=sum(1 for l_ in beat.get("layers", []) if l_.get("type") in ("marker", "zone_label")))
                    if cards:
                        beat["mode"], beat["support"] = "map_footage", cards[0]
                        if len(cards) > 1:
                            beat["more_cards"] = cards[1:]
                        beat["footage_intent"] = cards[0]["reason"]
                        b.notes.append("photo cards: " + ", ".join(c["asset"] for c in cards))
                        info.setdefault("map_cards", {})[b.id] = [c["asset"] for c in cards]
                plan_beats.append(beat)
                beat_notes[b.id] = {"kind": "map", "places": [h.name for h in b.places]}
                if opt.mapoverlay:
                    try:
                        from ..beats import overlay as OV
                        ov = OV.plan_overlay(beat, words, OV.suggest_cues(beat))
                        beat_notes[b.id]["overlay"] = ov
                    except Exception as exc:         # never stop: the map is used without an overlay
                        b.notes.append(f"map overlay not planned: {type(exc).__name__}: {str(exc)[:80]}")
                first_map = False
                map_places_done.update(h.name for h in b.places)
            except Exception as exc:
                b.notes.append(f"map beat could not be built, board beat instead: {exc}")
                b.kind = "board"
                plan_beats.append(None)
        elif b.kind == "archive":
            try:
                beat, ev, probs = make_archive_beat(b.id, b.start, b.end, words, [{"asset": b.archive["asset"], "reason": b.archive["reason"], "subject": b.archive["subjects"], "kenburns": True}],
                                                    purpose="archive: " + b.archive["subjects"][0], strict=False)
                if probs:
                    raise ValueError("; ".join(probs))
                plan_beats.append(beat)
                evidence_subjects.update(ev["subjects"])
                beat_notes[b.id] = {"kind": "archive", "asset": b.archive["asset"], "subjects": b.archive["subjects"]}
            except Exception as exc:
                b.notes.append(f"archive beat could not be built, board beat instead: {exc}")
                b.kind, b.archive = "board", None
                plan_beats.append(None)
        elif b.kind == "footage":
            try:
                from ..beats.footage import CAPTION_MIN_READ_S, make_footage_beat, pick_query
                from ..beats.relevance import beat_tokens as _bt
                btoks = [t["tok"] for t in _bt(words, b.start, b.end)]
                pq = None
                src_ = b.source or opt.footage_source
                scene_flow = opt.scene_intel and src_ == "flow_image" and bool(b.picture_query)
                if scene_flow:
                    pq = (b.picture_query, 0)
                    info.setdefault("scene_flow_beats", []).append(b.id)
                if opt.pictures and not scene_flow:              # opt-in: the query of the picture pass, else a better one (full names, only spoken words, no vague words) than the first keyword
                    from . import compose_pictures as CPX
                    _pic = info.get("pictures", {})
                    bq = None
                    if b.picture_query:
                        pq = (b.picture_query, 0)
                    else:
                        bq = CPX.build_query(btoks, _pic.get("phrases", []), set(info.get("named_subjects", ())), _pic.get("cased", {}), avoid=info.setdefault("footage_query_count", {}))
                        if bq is not None and not bq["vague"]:
                            pq = (bq["query"], 0)
                            info["footage_query_count"][bq["query"].lower()] = info["footage_query_count"].get(bq["query"].lower(), 0) + 1
                nm = [t for t in btoks if t in set(info.get("named_subjects", ()))] if pq is None else []
                if nm:                                           # a named person or event (Napoleon Bonaparte, Elba, Waterloo) is searched by its name, before any filmable noun
                    i0 = btoks.index(nm[0])
                    q = [btoks[i0]] + ([btoks[i0 + 1]] if i0 + 1 < len(btoks) and btoks[i0 + 1] in nm else [])
                    pq = (" ".join(q), i0)
                if pq is not None and not opt.pictures and not scene_flow:          # one subject's picture is not shown over and over: the third beat on the same query falls back to a filmable noun, or stays a board
                    _used = info.setdefault("footage_query_count", {})
                    _used[pq[0]] = _used.get(pq[0], 0) + 1
                    if _used[pq[0]] > 2:
                        pq = None
                if pq is None:
                    pq = pick_query(btoks, LX.CONCRETE_STRONG, LX.STOP, LX.CONCRETE_WEAK)
                if pq is None:
                    raise ValueError("no word a camera can film")
                allidx = [g for s_ in b.sents for g in s_.widx if b.start - 1e-6 <= words[g][1] < b.end - 1e-6]
                brk = sentence_ends | set().union(*[s_.breaks for s_ in b.sents])
                cands_ = CP.best_phrases(allidx, words, cased, table, brk, k=3, max_words=6, fit=lambda t: len(t) <= 56, min_score=3.0, min_words=2)
                cap = next((c_ for c_ in cands_ if words[c_.first][1] <= b.end - CAPTION_MIN_READ_S), None)
                if cap is None:
                    raise ValueError("no phrase to show over the clip early enough to read")
                beat = make_footage_beat(b.id, b.start, b.end, words, source=src_, query=pq[0], caption={"text": cap.text, "t": words[cap.first][1]}, still_sources=LX.FOOTAGE_STILL_SOURCES)
                plan_beats.append(beat)
                beat_notes[b.id] = {"kind": "footage", "source": src_, "query": pq[0], "caption": cap.text}
                info.setdefault("footage_queries", {})[b.id] = f"{src_}:{pq[0]}"
            except Exception as exc:
                b.notes.append(f"footage beat could not be built, board beat instead: {exc}")
                b.kind = "board"
                plan_beats.append(None)
        else:
            plan_beats.append(None)
    modes = PC.plan_narrator([(b.kind, b.start, b.end) for b in beats], opt)

    # ---- board beats ----
    all_events: List[float] = []
    strict_events: List[float] = []
    narrator_spans: List[Tuple[float, float]] = []
    metaphor_uses: List[Dict[str, str]] = []
    carry = "idle"
    board_info: Dict[str, Any] = {}
    pic_metrics: Dict[str, Any] = {}
    motion_rec: Dict[str, Any] = {}
    numbers_rec: Dict[str, Any] = {}
    variety_rec: Dict[str, Any] = {}
    fill_rec: Dict[str, Any] = {}
    recipe_rec: Dict[str, Any] = {}
    animate_rec: Dict[str, Any] = {}
    dialogue_rec: Dict[str, Any] = {}
    creg, continuity_rec = None, {}                                  # opt.continuity: the scene registry and its per-beat decisions
    if opt.continuity:
        from .scene_registry import SceneRegistry
        creg = SceneRegistry()
    dlg_state = None
    sig_hist: List[Tuple[str, ...]] = []        # the picture-layout family of each board beat so far (opt.variety)
    dossier_hist: List[bool] = []
    from . import compose_pictures as CPX_r                              # only period pictures (the ones likely to be refused) get a drawn stand-in: a 40-minute video has dozens of picture beats
    for k, b in enumerate(beats):
        saved_pic = None
        if plan_beats[k] is not None and b.kind == "footage" and b.picture_query and opt.pictures and materialize and CPX_r.request_year(b.picture_query) is not None:
            saved_pic, plan_beats[k], b.kind = plan_beats[k], None, "board"        # the picture beat keeps its place, but the board it replaced is drawn too: the stand-in if no picture can be had
        if plan_beats[k] is not None:
            beat = plan_beats[k]
            if b.kind == "map":
                evs_ = [b.start] + [l["t"] for l in beat.get("layers", [])] + [c["t"] for c in beat.get("camera", []) if c["action"] != "start"]
            elif b.kind == "footage":
                evs_ = [b.start] + [l["t"] for l in beat.get("layers", [])]
            else:
                evs_ = [b.start]
            all_events += evs_
            strict_events += evs_
            continue
        bw = [w for w in words if b.start - 1e-6 <= w[1] < b.end - 1e-6]
        if b.kind == "cartoon":
            from .compose_cartoon import author_cartoon
            if creg is not None:
                from .compose_cartoon import continuity_plan
                continuity_rec[b.id] = continuity_plan(creg, b, words, opt, roles, k)
                br = author_cartoon(b.id, b.start, b.end, b.sents, words, cased, opt, table, roles, variant=k, scene=b.scene_hint, plan=continuity_rec[b.id])
                try:                                                    # the set the composer really drew (harbour -> shallows when something blocks the way) is what the registry remembers
                    drawn = next(((c.params or {}).get("set") for c in br.cues if c.kind == "visual" and (c.params or {}).get("style") == "set"), None)
                    rec_ = continuity_rec[b.id]
                    if drawn and drawn != rec_.get("scene"):
                        rec_.setdefault("reasons", []).append(f"drawn as {drawn} (the words make {rec_.get('scene')} the shallows)")
                        rec_["scene"] = drawn
                        rec_["ident"] = rec_["ident"].replace(f"{rec_['ident'].split('|')[0]}|", f"{drawn}|", 1)
                        for h_ in reversed(creg.history):
                            if h_.get("id") == b.id:
                                h_["scene"], h_["ident"] = drawn, rec_["ident"]
                                break
                except Exception:
                    pass
            else:
                br = author_cartoon(b.id, b.start, b.end, b.sents, words, cased, opt, table, roles, variant=k, scene=b.scene_hint)
        elif opt.look == "reference":
            br = None
            if opt.recipes and b.kind == "board":                       # opt-in: a cause, a comparison, a count, a rank order, dated events or numbers get a multi-element composition
                from .compose_recipes import author_recipe
                try:
                    br = author_recipe(b.id, b.start, b.end, b.sents, words, cased, opt, table, roles, modes[k], carry, variant=k, idea=b.idea)
                except Exception:                                      # never stop: the beat keeps its ordinary composition
                    br = None
                if br is not None:
                    recipe_rec[b.id] = {"recipe": getattr(br, "recipe", ""), "idea": b.idea}
            if br is None:
                from .compose_ref import author_ref
                br = author_ref(b.id, b.start, b.end, b.sents, words, cased, opt, table, roles, modes[k], carry, variant=k)
        else:
            br = CP.author(b.id, b.start, b.end, b.sents, words, cased, opt, table, roles, modes[k], carry)
        beat_bg = opt.background
        if opt.variety and opt.look == "reference" and b.kind != "cartoon":
            from .compose_variety import variety_pass
            br, beat_bg, variety_rec[b.id] = variety_pass(br, b, k, words, cased, opt, table, roles, modes[k], carry, sig_hist, dossier_hist)
        resolved = CP.gate(br, b.id, b.start, b.end, words, opt)
        if b.kind == "cartoon":                 # a cartoon beat has no repair: its elements arrive on spread-out words; the gaps are measured and reported
            ev_s, ev_a = CP.change_events(resolved, b.start, b.end, strict=True), CP.change_events(resolved, b.start, b.end)
            br.still_gap_strict_s = br.still_gap_s = max(y - x for x, y in zip(ev_s, ev_s[1:]))
            br.still_gap_all_s = max(y - x for x, y in zip(ev_a, ev_a[1:]))
        elif opt.look == "reference":
            from .compose_ref import repair_still_ref
            from .compose_ref import rescue_text_ref
            rescue_text_ref(br, b.id, b.start, b.end, b.sents, words, cased, opt, table, resolved)
            resolved = CP.gate(br, b.id, b.start, b.end, words, opt)
            resolved = repair_still_ref(br, b.id, b.start, b.end, words, cased, opt, resolved, table, roles, set().union(*[s_.breaks for s_ in b.sents]) | sentence_ends)
        else:
            resolved = CP.repair_still(br, b.id, b.start, b.end, words, cased, opt, resolved, table, roles, set().union(*[s_.breaks for s_ in b.sents]) | sentence_ends)
        if (opt.motion or opt.numbers) and opt.look == "reference" and b.kind != "cartoon":
            if opt.motion:
                from .compose_motion import motion_pass
                motion_rec[b.id] = motion_pass(br, b.id, b.start, b.end, b.sents, words, opt, motion_state)
            if opt.numbers:
                from .compose_numbers import numbers_pass
                numbers_rec[b.id] = numbers_pass(br, b.id, b.start, b.end, b.sents, words, opt, motion_state)
            resolved = CP.gate(br, b.id, b.start, b.end, words, opt)
        if opt.fill and opt.look == "reference" and b.kind != "cartoon":
            from .compose_fill import fill_pass
            fill_rec[b.id] = fill_pass(br, b.id, b.start, b.end, b.sents, words, cased, opt, table, roles)
            resolved = CP.gate(br, b.id, b.start, b.end, words, opt)
            if fill_rec[b.id].get("changed"):
                ev_s = CP.change_events(resolved, b.start, b.end, strict=True)
                ev_a = CP.change_events(resolved, b.start, b.end)
                br.still_gap_strict_s = br.still_gap_s = max(y - x for x, y in zip(ev_s, ev_s[1:]))
                br.still_gap_all_s = max(y - x for x, y in zip(ev_a, ev_a[1:]))
        if opt.dialogue and opt.look == "reference":
            from .compose_dialogue import dialogue_pass, new_state
            if dlg_state is None:
                dlg_state = new_state()
            try:
                dialogue_rec[b.id] = dialogue_pass(br, b.id, b.start, b.end, b.sents, words, opt, dlg_state)
            except Exception as exc:             # never stop: the beat keeps its cues
                dialogue_rec[b.id] = {"bubbles": [], "spots": [], "poses": [], "skipped": [f"dialogue pass failed: {type(exc).__name__}: {str(exc)[:80]}"]}
            resolved = CP.gate(br, b.id, b.start, b.end, words, opt)
        if opt.animate and (opt.look == "reference" or b.kind == "cartoon"):
            from .compose_anim import animate_pass
            _hist = creg.history if creg is not None else []
            animate_rec[b.id] = animate_pass(br, b.id, b.start, b.end, b.sents, words, opt, variant=k, kind="cartoon" if b.kind == "cartoon" else "board", continuity=continuity_rec.get(b.id),
                                             prev_cast=(_hist[-2]["cast"] if b.kind == "cartoon" and len(_hist) > 1 else None))
            resolved = CP.gate(br, b.id, b.start, b.end, words, opt)
        carry = br.last_pose
        if creg is not None and b.kind != "cartoon":
            creg.note_board(b.id, b.start, b.end, sorted({p_["as"] for p_ in br.phrases}))
        _p, _r, _items = dry_build(br.cues, words, b.start, b.end, dissolve_s=opt.dissolve_s, fps=opt.fps, beat_id=b.id)
        CONTENT = 1104 * 780.0                                         # the content area right of the narrator zone, inside the margins (x 720..1824, y 110..890)
        pts = sorted({0.0, *[it.onset for it in _items if it.kind not in ("narrator", "arrow") and it.style != "set"]})
        peak = 0.0
        for t_ in pts:
            tot = 0.0
            for it in _items:
                if it.kind in ("narrator", "arrow") or it.style == "set" or it.onset > t_ + 1e-9 or (it.hide_at is not None and it.hide_at <= t_ + 1e-9):
                    continue
                rr = it.rect if it.rect != (0, 0, 0, 0) else it.bbox
                tot += max(0, rr[2] - rr[0]) * max(0, rr[3] - rr[1]) if it.kind != "title" else 760 * 170
            peak = max(peak, tot)
        br.peak_occupancy = round(min(1.0, peak / CONTENT), 3)
        if opt.pictures and b.kind == "board":
            from . import compose_pictures as CPX
            pic_metrics[b.id] = CPX.thin_beat_metrics(_items, b.dur)
        all_events += CP.change_events(resolved, b.start, b.end)
        strict_events += CP.change_events(resolved, b.start, b.end, strict=True)
        if modes[k] != "none" and any(c.kind == "narrator" for c in br.cues):
            narrator_spans.append((b.start, b.end))
        metaphor_uses += br.metaphor_uses
        name = clip_name(br.cues, bw, b.start, b.end, opt, b.id, beat_bg)
        clip_path = str((out_dir / name).resolve()) if out_dir else f"explainer/{name}"
        built = False
        if materialize:
            f = out_dir / name
            if not (f.is_file() and f.stat().st_size > 0):
                bb = build_board_clip(br.cues, words, b.start, b.end, f, dissolve_s=opt.dissolve_s, fps=opt.fps, size=opt.size, strict=False, beat_id=b.id, background=beat_bg, camera=opt.camera, texture=opt.texture)
                if bb.problems:
                    br.problems += bb.problems
            built = True
        beat = {"id": b.id, "mode": "footage", "start": b.start, "end": b.end, "purpose": f"explainer {'cartoon' if b.kind == 'cartoon' else 'board'}: {b.sents[0].label}",
                "footage": {"clips": [{"asset": clip_path, "reason": "explainer board clip drawn from this beat's own narration"}]}}
        plan_beats[k] = beat
        if saved_pic is not None:
            from .. import fallbacks as FB
            FB.record(out_dir, b.picture_query, clip_path)
            plan_beats[k], b.kind = saved_pic, "footage"
            board_info[b.id] = {"cues": len(br.cues), "stand_in_for": b.picture_query, "clip": name, "built": built}
            continue
        evidence_subjects[b.id] = {"0": [br.subject]}
        board_info[b.id] = {"cues": len(br.cues), "kinds": sorted({c.kind for c in br.cues}), "dropped": br.dropped, "rescued": br.rescued, "lost": br.lost, "repairs": br.repairs, "still_gap_s": round(br.still_gap_s, 2), "still_gap_all_s": round(br.still_gap_all_s, 2), "still_gap_strict_s": round(br.still_gap_strict_s, 2),
                            "narrator": modes[k], "labels": [s.label for s in b.sents], "phrases": br.phrases, "peak_occupancy_share": br.peak_occupancy, "clip": name, "built": built, "problems": br.problems, "cue_specs": [_cue_key(c) for c in br.cues],
                            "layout": [{"cue": r.cue.id, "kind": r.cue.kind, "slot": r.slot, "font_px": r.font_px, "lines": r.lines, "first_frame": r.first_frame} for r in resolved if not r.problems and r.cue.kind not in ("clear", "narrator")]}
    for bid_, rec_ in motion_rec.items():
        board_info[bid_]["motion"] = rec_
    for bid_, rec_ in numbers_rec.items():
        board_info[bid_]["numbers"] = rec_
    for bid_, rec_ in variety_rec.items():
        board_info[bid_]["variety"] = rec_
    for bid_, rec_ in fill_rec.items():
        board_info[bid_]["fill"] = rec_
    for bid_, rec_ in recipe_rec.items():
        board_info[bid_]["recipe"] = rec_
    for bid_, rec_ in animate_rec.items():
        board_info[bid_]["animate"] = rec_
    for bid_, rec_ in continuity_rec.items():
        board_info[bid_]["continuity"] = rec_
    for bid_, rec_ in dialogue_rec.items():
        board_info[bid_]["dialogue"] = rec_
    plan = assemble_plan(total, plan_beats, {"dissolve_s": float(opt.dissolve_s)})
    fx_budget = motion_state["budget"].summary() if "budget" in motion_state else None
    # ---- gates ----
    rep = check_plan(plan, words, subjects=evidence_subjects, base_dir=Path(opt.work_dir) / "explainer" if opt.work_dir else None,
                     allow_sources=LX.FOOTAGE_SOURCES if (opt.footage_share > 0 or opt.pictures or info.get("scene_flow_beats")) else (), composed=info.get("scene_flow_beats", ())) if materialize else None
    if rep is not None:
        res.problems += rep.problems
        res.warnings += rep.warnings
    else:
        from hybrid.plan import HybridPlan, PlanError, validate_plan
        try:
            res.problems += validate_plan(HybridPlan.from_dict(json.loads(json.dumps(plan))))
        except PlanError as e:
            res.problems += e.problems
    res.problems += [f"{bid}: {p}" for bid, v in board_info.items() for p in v["problems"]]
    editorial: Dict[str, Any] = {}
    try:                                                              # the application's own editorial validator: its errors are what "Check plan" would block rendering on
        from hybrid.plan import HybridPlan
        from hybrid.validate import validate as hybrid_validate
        fnd = hybrid_validate(HybridPlan.from_dict(json.loads(json.dumps(plan))))
        editorial = {"errors": [f.message for f in fnd if f.severity == "error" and f.code != "technical"], "technical": [f.message for f in fnd if f.code == "technical"],
                     "warnings": [f.message for f in fnd if f.severity == "warning"]}
        res.problems += [f"hybrid.validate: {m}" for m in editorial["errors"]]          # technical findings are validate_plan's, already reported above
        res.warnings += [f"hybrid.validate: {m}" for m in editorial["warnings"]]
    except Exception as exc:
        res.warnings.append(f"hybrid.validate could not run: {exc!r}")
    pic_rec = info.pop("pictures", None) if opt.pictures else None
    if pic_rec is not None:
        pic_rec.pop("cased", None)
        pic_rec["board_metrics"] = pic_metrics
        pic_rec["thin_boards_left"] = sorted(k_ for k_, v_ in pic_metrics.items() if v_["thin"])
    kinds = [{"id": b.id, "kind": b.kind, "start": b.start, "end": b.end} for b in beats]
    # ---- report ----
    story = {}
    for tag, pred in (("hook", lambda s: s.label == "hook"), ("question", lambda s: s.is_question), ("twist", lambda s: s.label == "twist"), ("conclusion", lambda s: s.label == "conclusion")):
        hit = next((s for s in sents if pred(s)), None)
        story[tag] = {"present": hit is not None, "sentence": None if hit is None else hit.index, "at_s": None if hit is None else round(hit.start, 2), "trigger": None if hit is None else hit.trigger,
                     "explicit": None if hit is None else (True if tag == "question" else hit.explicit if tag != "hook" else False), "basis": ("position: the first sentence" if tag == "hook" else "a cue word or phrase in the narration or script punctuation")}
    story["hook_within_30s"] = story["hook"]["present"] and story["hook"]["at_s"] <= 30.0
    story["question_within_120s"] = story["question"]["present"] and story["question"]["at_s"] <= 120.0
    res.report = {"explainer_version": EXPLAINER_VERSION, "options": {k: v for k, v in opt.__dict__.items() if k not in ("places",) and not (k in OPT_OMIT_WHEN_OFF and (not v or v == "off"))}, "duration_s": round(total, 3), "sentences": len(sents),
                  "sentence_labels": [{"i": s.index, "label": s.label, "trigger": s.trigger, "start": round(s.start, 2), "end": round(s.end, 2), "text": s.text[:160], "words": len(s.widx)} for s in sents],
                  "selection": {**info, "beats": kinds, "notes": {b.id: b.notes for b in beats if b.notes}}, "beat_details": {**beat_notes, **board_info}, "story": story,
                  "pacing": PC.metrics([{"kind": b.kind, "start": b.start, "end": b.end} for b in beats], all_events, narrator_spans, total, opt, strict_events),
                  "metaphors": PC.metaphor_report(metaphor_uses), "change_events_s": [round(e, 3) for e in sorted(all_events)], "meaningful_change_events_s": [round(e, 3) for e in sorted(strict_events)], "relevance_records": len(rep.records) if rep else 0, "hybrid_validate": editorial, "validate_plan_problems": rep.validate_plan_problems if rep else []}
    if pic_rec is not None:
        res.report["pictures"] = pic_rec
    if fx_budget is not None:
        res.report["fx_budget"] = fx_budget
    if creg is not None:
        res.report["continuity"] = creg.to_dict()
    if opt.scene_intel and info.get("scene_intel") is not None:
        res.report["scene_intel"] = info["scene_intel"]
    res.plan = plan if not res.problems else None
    if out_dir is not None and not res.problems:           # what the render step needs after the map is drawn: the sound plan (explainer.integration.build_sound) and the map overlays
        try:
            (out_dir / "render_report.json").write_text(json.dumps({"report": {k: v for k, v in res.report.items() if k != "candidate_plan"}, "words": [list(w) for w in words], "total": total}, default=str), encoding="utf-8")
        except Exception:
            pass
    if res.problems:
        res.report["plan_withheld"] = "a gate failed: nothing is installed"
        res.report["candidate_plan"] = plan
    return res
