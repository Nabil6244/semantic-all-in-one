"""direct(): narration words (+ script) -> a Hybrid plan whose board beats are explainer clips. Never raises; failures come back as problems with plan=None."""

from __future__ import annotations

import hashlib
import json
import re
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


OPT_OMIT_WHEN_OFF = ("scene_intel", "scene_flow_share", "flow_only", "flow_backdrops", "scene_notes", "alive", "meaning", "recipes", "continuity", "animate", "pictures", "motion", "numbers", "maplines", "variety", "budget", "fill", "sound", "dialogue", "scenes2", "mapoverlay", "camera", "texture")        # opt-in switches: absent from the report while off, so a disabled report is unchanged


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
    return f"board_{hashlib.sha256(blob.encode()).hexdigest()[:16]}.{'mov' if background == 'alpha' else 'mp4'}"      # a see-through board is an RGBA QuickTime clip


def direct(words: Sequence[Word], script: Optional[str] = None, options: Optional[DirectorOptions] = None, *, duration: Optional[float] = None,
           materialize: bool = True, log: Callable[[str], None] = lambda m: None) -> DirectorResult:
    opt = options or DirectorOptions()
    try:
        return _direct(words, script, opt, duration, materialize, log)
    except Exception as exc:                                              # never raise into the application
        return DirectorResult(None, {"exception": traceback.format_exc(limit=6)}, [f"the explainer director failed: {exc!r}"], [])

# pakMap's own fill roles in the order countries meet them: bright red, gold, purple, orange, then green and blue (which sit weakly on satellite land and sea; the dark "primary" brown is never used)
_FEATURE_WORDS = {"river", "sea", "ocean", "gulf", "bay", "lake", "mountains", "desert", "the"}


def _same_feature(a: str, b: str) -> bool:
    """'Nile River' and 'Nile' (or 'Adriatic Sea' and 'Adriatic') name one place."""
    k = lambda n: " ".join(w for w in n.lower().split() if w not in _FEATURE_WORDS)
    return a != b and k(a) != "" and k(a) == k(b)


_ZONE_LATEST_S = 0.55                         # a zone label never starts later than this after its word (the relevance gate allows +0.6 s; the camera may arrive up to 0.5 s late)
def _plain_first_map(b, words) -> Optional[Dict[str, Any]]:
    """The opening map with nothing drawn on it: where the camera starts, at the beat's first place. None when even that cannot be built."""
    try:
        pl = b.places[0]
        frame = ("continental" if FR._is_continent(pl.name) else "country") if pl.kind in ("country", "region") else "region"
        beat, _ev, probs = make_map_beat(b.id, b.start, b.end, words, camera_start={"place": pl.name, "frame": frame}, purpose="map: " + pl.name, geo_intent="where " + pl.name + " is", strict=False)
        if probs:
            return None
        beat["camera"] = [c for c in beat.get("camera", []) if c.get("action") == "start"] or [{"action": "start", "place": pl.name, "frame": frame}]
        return beat
    except Exception:
        return None


FILL_PALETTE = ("red", "featured", "orange", "green", "compare", "accent", "water", "primary")      # strong colours first: the engine draws fills at ~45 % and purple reads as pale pink over desert; the last two only past six countries
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
        if opt.flow_only:                               # Flow only: the card is drawn for this moment of the story (its period), not a photograph of the place today
            from . import compose_pictures as CPX_
            from .. import scene_intel as SI_
            src = "flow_image"
            spec_ = SI_.SceneSpec(place=" ".join(w.capitalize() for w in query.split()), year=CPX_.era_of_beat(words, b)["year"], architecture="specific")
            q_asset = SI_.flow_prompt(spec_)
            seen_ = info.setdefault("flow_card_prompts", [])
            if q_asset.lower() in seen_:                # the same request gives the same picture: one card per prompt in a video
                continue
            seen_.append(q_asset.lower())
            if b.id not in info.setdefault("scene_flow_beats", []):
                info["scene_flow_beats"].append(b.id)
        card = {"asset": f"{src}:{q_asset}", "t": round(t, 3), "label": label, "reason": f"shows {query}: the narration says it here"}
        if place:
            card["place"] = _place_point(place)
        out.append(card)
    return out


def _place_point(name: str) -> str:
    """The place the map shows, as "lat,lon": a card's leader line is resolved as a point, and a bare "York" as a point is York, Pennsylvania (the map shows York, England)."""
    try:
        from pakmap import geo as _g
        loc = _g.resolve(name, prefer="area")
        return f"{loc.lat:.3f},{loc.lon:.3f}"
    except Exception:
        return name


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


_SPECIFIC_KINDS = ("city", "admin1", "country", "county")
_SCENE_PEOPLE = frozenset((LX.PEOPLE_WORDS - {"people", "population", "everyone", "crowd"}) | {"merchants", "merchant", "traders", "sailors", "soldiers", "armies", "army", "invaders", "crusaders", "settlers", "explorers", "refugees"})


SET_MAX_USES = 2               # one library cartoon set (the beach with the boat) at most this often in a video: past it the beat is drawn for its own moment by Flow
SCENE_SHOTS = ("wide establishing view", "street-level view among the people", "close-up of a telling detail", "high aerial view", "view from the water", "interior view",
               "evening view with lamplight", "crowd in motion")      # the same place and period seen again is seen another way; past the last one the beat stays a board


SEEN_AGAIN = ("in early morning light", "in flat overcast midday light", "in low late-afternoon sun", "at blue hour just after sunset", "under a clearing sky after a storm",
              "seen from a little higher up", "seen from further back")


def _uniq(items) -> List[str]:
    out: List[str] = []
    for x in items:
        if x not in out:
            out.append(x)
    return out


def story_place(beats) -> str:
    """The place the story is about: the town, state or country spoken in the most beats (seas and continents are where it happens, not what it is about). "" when none is spoken."""
    n: Dict[str, int] = {}
    for b in beats:
        for name in {h.name for h in b.places if h.kind in _SPECIFIC_KINDS}:
            n[name] = n.get(name, 0) + 1
    return max(n, key=lambda k: (n[k], -list(n).index(k))) if n else ""


def beat_place(beats, k: int) -> str:
    """The place beat k is about: the first town, state or country it speaks, else the last one spoken in the two beats before it. "" when none."""
    for j in range(k, max(-1, k - 3), -1):
        hits = [h for h in beats[j].places if h.kind in _SPECIFIC_KINDS]
        if hits:
            return hits[0].name if j == k else hits[-1].name
    return ""


PLATE_RUN = 3                  # one background plate is kept for at most this many board beats in a row (same place and period); then the camera "moves" to another framing. 3 since beats became 3-4 s, so a plate still lasts ~10 s and the Flow picture count does not grow
PAPER_EVERY = 3                # Flow backdrops: every third board beat stays on the plain board background (grey, paper...) so the look keeps its own surface between pictures


def bare_board(cues) -> bool:
    """Nothing on the board but the presenter (and clears): on plain paper that is an empty screen."""
    return not any(c.kind not in ("narrator", "clear") and (c.text or c.asset or (c.params or {}).get("style")) for c in cues)


def keeps_paper(n_board: int) -> bool:
    """True for the board beat that stays on the plain background: the 3rd, 6th, 9th... board beat (counted from 0, so the first board is always on a picture)."""
    return n_board % PAPER_EVERY == PAPER_EVERY - 1


PLATE_LOOK = "empty scene with no people and no text, calm composition, soft focus, open quiet space on the right side"


DRESSED_FROM = {"soldier": 1750, "officer": 1750, "guard": 1750, "revolutionary": 1750, "police": 1820, "worker": 1800, "doctor": 1850, "judge": 1700, "merchant": 1780, "sailor": 1850,
                "farmer": 1800, "woman": 1800, "priest": 1600}      # the kit's clothes (top hat, sailor stripes, Napoleonic uniform...) belong to this year or later; the king's crown and robe fit any time
CAST_SHOTS = ("eye-level street view", "eye-level view on the waterfront", "eye-level view of a square", "eye-level view inside a workshop", "eye-level view at the edge of the water",
              "eye-level view at dusk", "eye-level view of a courtyard", "eye-level view of a market")
CAST_LOOK = "empty scene with no people and no text, open level ground across the lower third where figures can stand"


def cast_plate_prompt(spec, state: Dict[str, Any]) -> str:
    """The Flow picture a cartoon cast stands on: the beat's place, period and things (never its people: the characters are the people), seen at eye level with open ground at the bottom,
    framed differently each time the same place and period comes back."""
    from .. import scene_intel as SI
    key = (spec.region or spec.place or spec.place_type, None if spec.year is None else int(spec.year) // 50 * 50)
    n = state.setdefault(key, 0)
    state[key] = n + 1
    turn = state.get("_turn", 0)                     # the framing also turns across the video, so two different places do not both open on the same street view
    state["_turn"] = turn + 1
    from . import lexicon_v2 as LV
    things = [o for o in spec.objects if o in LX.CONCRETE and o not in LV.CHARACTER_OF and o not in _SCENE_PEOPLE]      # the plate has no people: "armies" stay out of it, the characters bring them
    plate = SI.SceneSpec(place=spec.place, place_type=spec.place_type, region=spec.region, year=spec.year, architecture=spec.architecture, objects=things,
                         background=CAST_SHOTS[(n + turn) % len(CAST_SHOTS)],
                         atmosphere=CAST_LOOK + (f", {SEEN_AGAIN[(n // len(CAST_SHOTS) - 1) % len(SEEN_AGAIN)]}" if n >= len(CAST_SHOTS) else ""))     # never "variation N": Flow drew panels for it
    return SI.flow_prompt(plate)


HEAL_ROUNDS = 3


def beats_named(problems: Sequence[str], ids: Sequence[str]) -> List[str]:
    """The beats the problems are about ("beat e125: ...", "e125: ..."), in plan order. A problem that names no beat cannot be healed by folding."""
    known = set(ids)
    hit = {m for p in problems for m in re.findall(r"\b(e\d+)\b", str(p)) if m in known}
    if any(not (set(re.findall(r"\b(e\d+)\b", str(p))) & known) for p in problems):
        return []
    return [i for i in ids if i in hit]


def fold_beats(plan: Dict[str, Any], bad: Sequence[str]) -> Dict[str, str]:
    """Each bad beat is removed and its time given to the beat before it (or after it, for the first beat): the picture or board of the neighbour simply plays on.
    -> {beat id: what happened}. The plan keeps at least one beat and still covers the whole narration."""
    beats_ = plan["beats"]
    out: Dict[str, str] = {}
    for bid in bad:
        ids = [b_["id"] for b_ in beats_]
        if bid not in ids or len(beats_) < 2:
            continue
        k = ids.index(bid)
        gone = beats_.pop(k)
        if k > 0:
            beats_[k - 1]["end"] = gone["end"]
            out[bid] = f"had a problem, so its time is given to {beats_[k - 1]['id']}"
        else:
            beats_[0]["start"] = gone["start"]
            out[bid] = f"had a problem, so its time is given to {beats_[0]['id']}"
    return out


def spoken_subject(subject: str, words, start: float, end: float) -> str:
    """The board clip's subject as words the beat really says: the composer's subject when it is a quote of the beat, else the beat's own first words. A board is drawn from
    its own narration, so it always has a spoken subject (an empty one, from an icon with no label, used to stop the whole plan)."""
    from ..beats.relevance import beat_tokens, find_phrase
    tk = beat_tokens(words, start, end)
    if (subject or "").strip() and find_phrase(tk, subject) is not None:
        return subject
    toks = [t["tok"] for t in tk]
    content = [t for t in toks if t not in LX.STOP] or toks
    return content[0] if content else (subject or "")


NOT_SUBJECT = frozenset("""thing things way ways time times part parts kind lot lots fact case point reason story question answer world country people everyone someone something
nothing everything year years decade decades century day days percent number numbers million billion thousand hundred sleep reality matter problem idea like per across inside onto via
goes look looks needs need takes make makes gets turns comes runs says seems keeps puts sets stands holds shows means becomes remains far deeper global total single entire
called named known covers cover covered used using based two three four five six seven eight nine ten eleven twelve twenty thirty forty fifty sixty seventy eighty ninety dozen half week weeks month months hour hours minute minutes""".split())
SUBJECT_JOIN = frozenset(("and", "of"))
NOUN_END = ("tion", "sion", "ment", "ness", "ity", "ure", "ist", "ery", "age", "ance", "ence", "ine", "ide", "ium", "ony", "ite", "ore", "ill", "ank", "ine", "ant", "ter", "tor", "or")


def _nounish(t: str, cased: Dict[str, str]) -> bool:
    return t in LX.CONCRETE or t in cased or t.endswith(NOUN_END) or (len(t) > 3 and t.endswith("s") and not t.endswith(("ss", "us", "is")))


def narrated_subject(words, start: float, end: float, cased: Optional[Dict[str, str]] = None) -> str:
    """What this stretch of narration is about, in its own words, for its picture: the best run of 1 to 4 content words ending on a noun ("ultra sensitive infrared detectors",
    "tents and uniforms", "chinese smelters"). Verbs, numbers and filler never make a subject; a run with a thing a picture can show (LX.CONCRETE) or a name wins. "" when nothing is picturable."""
    from ..beats.relevance import beat_tokens
    toks = [t["tok"] for t in beat_tokens(words, start, end)]
    cased = cased or {}

    def content(t: str) -> bool:
        return (t.isalpha() and len(t) > 2 and t not in LX.STOP and t not in LX.WEAK and t not in NOT_SUBJECT and t not in LX.DANGLING_END
                and not (len(t) > 4 and (t.endswith("ed") or t.endswith("ing")) and t not in cased) and not (len(t) > 4 and t.endswith("ly")))

    def modifier(t: str) -> bool:
        return t.isalpha() and len(t) > 4 and t.endswith(("ed", "ing")) and t not in LX.STOP and t not in NOT_SUBJECT

    best, best_sc = "", 0.0
    for e, last in enumerate(toks):              # every run of up to 4 content words that ends on a noun ("create ultra sensitive infrared detectors" -> "ultra sensitive infrared detectors")
        if not content(last) or not _nounish(last, cased):
            continue
        run = [last]
        k = e - 1
        while k >= 0 and len([t for t in run if t not in SUBJECT_JOIN]) < 4:
            if (content(toks[k]) or modifier(toks[k])) and not _verb_start(toks[k]):     # "infrared", "refined" before a noun describe it
                run.insert(0, toks[k])
            elif toks[k] in SUBJECT_JOIN and k > 0 and content(toks[k - 1]) and _nounish(toks[k - 1], cased):
                run.insert(0, toks[k])
            else:
                break
            k -= 1
        n = len([t for t in run if t not in SUBJECT_JOIN])
        sc = 1.5 * n + 1.0 * any(t in LX.CONCRETE for t in run) + 1.5 * any(t in cased for t in run)
        if sc > best_sc and (n > 1 or last in LX.CONCRETE or last in cased):
            best, best_sc = " ".join(cased.get(t, t) for t in run), sc
    return best


VERB_START = frozenset("create creates combine combines build builds use uses produce produces make makes ship ships send sends buy buys sell sells".split())


def _verb_start(t: str) -> bool:
    return t in VERB_START


def narrated_spec(spec, subject: str):
    """A CSV scene's spec showing what the narration says right now: the scene keeps its place, period, people and their looks; the thing in the picture is the narration's subject
    (the scene row's own activity, objects and backdrop describe the whole scene, so they step aside while the narration names something else)."""
    if subject:
        spec.objects = [subject]
        spec.activity = spec.background = ""
    return spec


def plate_stage(side: str) -> str:
    """The part of a background plate the narrator and the board stand in front of: open calm ground on the narrator's side, a quiet uncluttered area for the words on the other."""
    other = "right" if side == "left" else "left"
    return (f"one single continuous picture with no panels, borders or split frames; open calm ground in the near foreground toward the {side} with nothing on it, where a presenter "
            f"will stand; quiet uncluttered sky or ground toward the {other} for words; any people stay small in the middle distance; no text")


def backdrop_prompt(beats, k: int, words, main: str, state: Dict[str, Any], notes: Sequence[Dict[str, Any]] = (), side: str = "left", cased: Optional[Dict[str, str]] = None) -> str:
    """The Flow background plate behind board beat k, made for what this stretch of narration is about: the CSV scene note over the beat when there is one (its place, period,
    people, activity, objects, mood), else the beat's place, period and the concrete things it names. Composed as a stage for the narrator (plate_stage). The same subject keeps its
    plate for PLATE_RUN beats, then the camera moves to another framing. "" when the beat names no place, no period and nothing to show (a topic with no setting keeps paper)."""
    from ..beats.relevance import beat_tokens
    from . import compose_pictures as CPX
    from .. import scene_intel as SI
    b = beats[k]
    mid = (b.start + b.end) / 2.0
    note = " ; ".join(n["text"] for n in notes if n.get("start", 0.0) - 1e-6 <= mid < n.get("end", 0.0) + 1e-6)
    year = CPX.era_of_beat(words, b)["year"]
    spec = SI.from_notes(note) if note else None
    if spec is not None:
        if spec.year is None:
            spec.year = year
        subject = narrated_subject(words, b.start, b.end, cased)        # the scene row says where and who; the narration says what the picture shows now
        narrated_spec(spec, subject)
        key = ("note", note, subject.lower())
    else:
        region = beat_place(beats, k) or main
        subject = narrated_subject(words, b.start, b.end, cased)       # no CSV scene: the narration says both where and what ("Abrams tank fires" and "heat seeking missile locks" were one "Idaho" picture)
        objs = _uniq(([subject] if subject else []) + [t["tok"] for t in beat_tokens(words, b.start, b.end) if t["tok"] in LX.CONCRETE and t["tok"] not in _SCENE_PEOPLE])[:3]
        if not region and year is None and not objs:
            return ""
        spec = SI.SceneSpec(region=region, year=year, architecture="specific" if region else "generic", objects=objs)
        key = (region, None if year is None else int(year) // 50 * 50, subject.lower())          # the same subject keeps its picture; a new one gets its own
    if key == state.get("key") and state.get("run", 0) < PLATE_RUN:
        state["run"] += 1
        return state["prompt"]
    n = state.setdefault("shots", {}).get(key, 0)
    state["shots"][key] = n + 1
    if n or not spec.background:                    # the note's own backdrop first; a second plate of the same subject is another framing of it
        spec.background = ", ".join(x for x in (spec.background if n == 0 else "", SCENE_SHOTS[n % len(SCENE_SHOTS)]) if x)
    spec.atmosphere = ", ".join(x for x in (spec.atmosphere, plate_stage(side)) if x)
    prompt = SI.flow_prompt(spec)
    if n >= len(SCENE_SHOTS):                       # every framing used: the subject is seen again at another hour, never the same request twice ("variation 4" made Flow draw several side by side)
        prompt = prompt.replace(". flat 2D", f", {SEEN_AGAIN[(n // len(SCENE_SHOTS) - 1) % len(SEEN_AGAIN)]}. flat 2D", 1)
    state.update(key=key, run=1, prompt=prompt)
    return prompt


def scene_intel_pass(beats, words, opt: DirectorOptions, SI, cased: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Read every cartoon beat (its words, then the CSV scene note over it when there is one) and turn the ones the library cannot show truthfully into Flow image beats, up to
    `opt.scene_flow_share` of the runtime. Returns the per-beat record for the report. Never raises: a beat that cannot be read stays as it was."""
    from ..beats.relevance import beat_tokens
    from . import compose_pictures as CPX
    total = sum(b.end - b.start for b in beats) or 1.0
    used, rec = 0.0, {}
    main = story_place(beats)
    prompts: set = set()
    set_uses: Dict[str, int] = {}
    seen_scene: Dict[Tuple[str, Optional[int]], int] = {}
    cast_seen: Dict[Tuple[str, Optional[int]], int] = {}
    mix = {"cast": 0, "flow": 0}
    from . import lexicon_v2 as LV
    for k, b in enumerate(beats):
        restock = opt.flow_only and b.kind == "footage"      # Flow only: a picture or footage beat (a stock search, or a bare Flow keyword) gets a picture made for its moment instead
        if b.kind != "cartoon" and not restock:
            continue
        try:
            text = " ".join(s_.text for s_ in b.sents)
            spec = SI.from_words(text)
            if restock:
                spec.route = "flow"
            era = CPX.era_of_beat(words, b)            # the beat's own period, else the last one spoken shortly before it: never the first year of the whole video ("1204" over the 5th century)
            if era["year"] is not None:
                spec.year = era["year"]
            here = beat_place(beats, k) or main            # what the picture is OF: the place this beat (or the story just before it) is about, and the people and things it names
            if here and not spec.region:
                spec.region, spec.architecture = here, "specific"
            toks = [t["tok"] for t in beat_tokens(words, b.start, b.end)]
            spec.people = spec.people or _uniq(t for t in toks if t in _SCENE_PEOPLE)[:2]
            subject = [t for t in (b.picture_query or "").lower().split() if t in toks and t not in LX.STOP] if restock else []      # the stock search's own spoken subject ("ports") leads
            said = narrated_subject(words, b.start, b.end, cased)
            spec.objects = spec.objects or _uniq(subject + ([said] if said else []) + [t for t in toks if t in LX.CONCRETE and t not in _SCENE_PEOPLE])[:3]
            mid = (b.start + b.end) / 2
            note = " ; ".join(n["text"] for n in opt.scene_notes if n["start"] - 1e-6 <= mid < n["end"] + 1e-6)
            noted = SI.from_notes(note, spec)
            if noted is not None:                   # a CSV scene: its place, period and cast, showing what this beat's narration names
                spec = narrated_spec(noted, narrated_subject(words, b.start, b.end, cased))
            d = SI.decide(spec)
            if d.route == "compose" and set_uses.get(d.set_name, 0) >= SET_MAX_USES:      # the audience has seen this set enough: this moment gets its own picture
                b.notes.append(f"cartoon set {d.set_name!r} already used {SET_MAX_USES} times: drawn by Flow instead")
                spec.route = "flow"
                d = SI.decide(spec)
                d.reasons.append(f"the library set was used {SET_MAX_USES} times already")
            elif d.route == "compose":
                set_uses[d.set_name] = set_uses.get(d.set_name, 0) + 1
            entry = {"route": d.route, "set": d.set_name, "reasons": d.reasons, "source": spec.source, "year": spec.year, "place_type": spec.place_type, "region": spec.region}
            cast = [c for c, _i in LV.characters_for(toks)] if opt.flow_backdrops else []
            if cast and spec.year is not None and any(spec.year < DRESSED_FROM.get(c, -10 ** 6) for c in cast):      # a Napoleonic uniform in 1204 is wrong: Flow draws the people of that time instead
                entry["reasons"] = list(entry["reasons"]) + [f"the characters' clothes ({', '.join(cast)}) are later than {spec.year}: a full picture instead"]
                cast = []
            if cast and mix["cast"] < mix["flow"]:          # the words name who is there (merchants, soldiers, the doge): those characters stand on a picture of the place; never more often than full pictures, so the two alternate
                mix["cast"] += 1
                b.plate = cast_plate_prompt(spec, cast_seen)
                b.kind, b.source, b.picture_query = "cartoon", "", ""
                entry.update(route="cast on a Flow picture", prompt=b.plate, cast=cast)
                rec[b.id] = entry
                continue
            if d.route == "flow":
                key = (spec.region or spec.place or spec.place_type, None if spec.year is None else int(spec.year) // 50 * 50)
                n_seen = seen_scene.get(key, 0)
                if n_seen >= len(SCENE_SHOTS):              # every way of seeing this place in this period is used: a board, not a near-copy
                    entry["route"] = "board (scene seen in every framing already)"
                    b.notes.append(f"{key[0]} around {key[1]} already shown {n_seen} times: board instead of another picture of it")
                    b.kind, b.source, b.picture_query = "board", "", ""
                    rec[b.id] = entry
                    continue
                spec.background = ", ".join(x for x in (spec.background, SCENE_SHOTS[n_seen]) if x)
                prompt = SI.flow_prompt(spec)
                if prompt.lower() in prompts:               # the same request twice gives the same picture twice: say what this beat shows, in its own words
                    extra = [t for t in toks if t not in LX.STOP and t not in LX.WEAK and len(t) > 3 and t not in prompt.lower()][:3]
                    if extra:
                        spec.activity = (spec.activity + ", " if spec.activity else "") + "showing " + " ".join(extra)
                        prompt = SI.flow_prompt(spec)
                if prompt.lower() in prompts:
                    entry["route"] = ("board" if restock else "cartoon") + " (same Flow request as an earlier beat)"
                    b.notes.append("scene would repeat an earlier Flow image word for word: kept as a " + ("board" if restock else "cartoon"))
                    if restock:
                        b.kind, b.source, b.picture_query = "board", "", ""
                    rec[b.id] = entry
                    continue
                if opt.flow_only or (used + (b.end - b.start)) / total <= opt.scene_flow_share:
                    used += b.end - b.start
                    prompts.add(prompt.lower())
                    seen_scene[key] = n_seen + 1
                    mix["flow"] += 1
                    b.kind, b.source, b.picture_query = "footage", "flow_image", prompt
                    entry["prompt"] = b.picture_query
                else:
                    entry["route"] = "cartoon (Flow share reached)"
                    b.notes.append("scene needs a Flow image but the share of runtime is used up: kept as a cartoon")
            rec[b.id] = entry
        except Exception as exc:
            b.notes.append(f"scene reading failed, beat unchanged: {exc}")
    return rec


def _direct(words, script, opt: DirectorOptions, duration, materialize, log) -> DirectorResult:
    from anchor_clock import join_number_words
    words = join_number_words(words)            # Whisper's "6" "500" / "300" "0" are one spoken number: every card, chart and badge reads 6500 / 300000
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
    for k_, v_ in SG.spelling(words, script).items():      # a misheard word is shown as the script writes it
        cased.setdefault(k_, v_)
    if SL.lowercase_text(script, words):           # speech-to-text writes "mercia", "viking": the names the CSV gives (its places and scene notes) are written as the CSV writes them
        heard = SL.place_words(words)                # and the countries and states the narration names ("america", "idaho"), CSV or not
        for k_, v_ in SG.vocab_casing(words, list(opt.places) + [n.get("text", "") for n in opt.scene_notes] + list(heard)).items():
            cased.setdefault(k_, v_)
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
        info["scene_intel"] = scene_intel_pass(beats, words, opt, SI, cased)
    for b in beats:
        if b.kind == "map":
            try:
                pl = b.places[0]
                all_hits = [h for h in b.places if h.match]
                all_hits = [h for h in all_hits if not any(o is not h and _same_feature(o.name, h.name) and len(o.name) > len(h.name) for o in all_hits)]      # "Nile" and "Nile River" are one place: one label, not two on top of each other
                hits = all_hits[:8] if len(all_hits) >= 4 else all_hits[:3]          # a sentence that lists many countries is drawn whole (up to 8) on one world view
                bstart = b.start + (opt.dissolve_s / 2)
                cam = FR.plan_camera([{"name": h.name, "t": h.match["start"]} for h in hits], bstart, b.end, first_map, cur_view)
                _i = beats.index(b)
                if not first_map and _i and beats[_i - 1].kind != "map" and cam["moves"] and cam["moves"][0]["action"] == "fly_to":      # the map comes in after a full-screen board: the camera sat still at its old (globe) view meanwhile, so the first move is a cut, not a flight through the globe
                    cam["moves"][0].update(t=round(b.start, 3), dur=0.04)
                    if len(cam["moves"]) > 1 and cam["moves"][1]["action"] == "push_in":      # the push-in follows the cut at once instead of waiting for the flight that is no longer there
                        p_ = cam["moves"][1]
                        p_.update(t=round(b.start + 0.15, 3), dur=round(min(3.0, p_["t"] + p_["dur"] - b.start - 0.15), 3))
                for rj in cam["rejected"]:
                    b.notes.append(f"{rj['place']} is not drawn: {rj['reason']}")
                    info["map_layers_rejected"].append({"beat": b.id, **rj})
                shown = [h for h in hits if h.name not in {r_["place"] for r_ in cam["rejected"]}]
                for note in cam["notes"]:
                    b.notes.append("camera: " + note)
                markers, fills, zones = [], [], []
                drawn: set = set()                      # the places that really got a fill or a marker on this map (a relation line joins only these)
                label_boxes: List[Tuple[str, Tuple[float, float, float, float]]] = []
                lead = None                             # the first place with an outline is coloured as soon as the camera is there, not seconds later when its name is spoken
                for h in shown:
                    wait = max(0.0, cam["ready"].get(h.name, 0.0) - h.match["start"])      # the layer waits until the camera is where the place can be seen
                    if wait > 0.5:
                        b.notes.append(f"{h.name} is not drawn: the camera is ready at {cam['ready'][h.name]:.1f} s, long after the word at {h.match['start']:.1f} s")
                        info["map_layers_rejected"].append({"beat": b.id, "place": h.name, "reason": "the camera cannot show it in time"})
                        continue
                    if h.kind == "country" or (h.is_area and h.kind in ("admin1", "region", "county") and not FR._is_continent(h.name)):      # every place with a real outline is coloured in (a state, a province, the Balkans); a continent stays a label, a sea has no outline
                        if h.name not in country_roles:
                            country_roles[h.name] = FILL_PALETTE[len(country_roles) % len(FILL_PALETTE)]
                        early = 0.0
                        if lead is None and not cam.get("wide"):        # a world-view list of countries keeps each colour on its own word
                            lead = h.name
                            early = min(0.0, max(bstart + 0.2, cam["ready"].get(h.name, 0.0)) - h.match["start"])
                        fills.append({"place": h.name, "offset_s": round(wait + early, 3), "role": country_roles[h.name]})
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
                        zones.append({"place": h.name, "offset_s": round(wait + early + 0.3 if early < 0 else min(max(0.3, wait + 0.3), _ZONE_LATEST_S), 3)})
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
                plain = _plain_first_map(b, words) if first_map else None      # the plan needs exactly one camera start: the first map is kept as a plain map (camera only) rather than lost
                if plain is not None:
                    b.notes.append(f"map layers could not be built, plain map instead: {exc}")
                    plan_beats.append(plain)
                    beat_notes[b.id] = {"kind": "map", "places": [h.name for h in b.places]}
                    cur_view, first_map = None, False
                    continue
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
    queued: list = []                           # board clips drawn after the plan (board/jobs.py)
    dossier_hist: List[bool] = []
    from . import compose_pictures as CPX_r                              # only period pictures (the ones likely to be refused) get a drawn stand-in: a 40-minute video has dozens of picture beats
    plate_main, plate_state = (story_place(beats), {}) if opt.flow_backdrops else ("", {})
    n_board = 0                                 # board beats seen so far (keeps_paper)
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
        if b.kind == "cartoon" and b.plate:                  # the cast on a Flow picture: no library set, no continuity stand-ins
            from .compose_cartoon import author_cartoon
            br = author_cartoon(b.id, b.start, b.end, b.sents, words, cased, opt, table, roles, variant=k, scene=b.scene_hint, on_plate=True)
        elif b.kind == "cartoon":
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
        from .onscreen import drop_icons_out_of_sense, finish_texts
        n_fin = finish_texts(br.cues)            # whichever composer wrote a phrase, it ends as a finished thought ("buried on the" -> "buried")
        from .onscreen import finish_phrase
        for ph_ in br.phrases:                    # the report says what the screen shows
            if (ph_.get("phrase") or "").strip():
                ph_["phrase"] = finish_phrase(ph_["phrase"])
        n_off = drop_icons_out_of_sense(br.cues, words, b.start, b.end)      # "crushed ore" gets no battle swords, "the United States" no castle
        if n_fin:
            info.setdefault("texts_finished", []).append(b.id)
        if n_off:
            info.setdefault("icons_out_of_sense", []).append(b.id)
        if n_fin or n_off:
            resolved = CP.gate(br, b.id, b.start, b.end, words, opt)
        plate = ""
        if opt.flow_backdrops and b.kind == "board" and saved_pic is None:      # the narrator and the cards stand in front of a picture of the story's place and period, not on paper
            n_board += 1
            side_ = next((c.params.get("side") for c in br.cues if c.kind == "narrator" and (c.params or {}).get("side")), "left")
            paper = keeps_paper(n_board - 1) and not bare_board(br.cues)      # paper only carries a board that shows something; a presenter alone stands in front of a picture
            plate = "" if paper else backdrop_prompt(beats, k, words, plate_main, plate_state, opt.scene_notes, side_, cased)
            if plate:
                beat_bg = "alpha"
        elif b.kind == "cartoon" and b.plate:
            plate, beat_bg = b.plate, "alpha"
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
                kw = dict(dissolve_s=opt.dissolve_s, fps=opt.fps, size=opt.size, strict=False, beat_id=b.id, background=beat_bg,
                          camera="off" if plate else opt.camera, texture=False if plate else opt.texture)
                # the layout runs now (its problems belong to the plan); the drawing is queued and done in parallel just before the render (board/jobs.py)
                bb = build_board_clip(br.cues, words, b.start, b.end, f, draw=False, **kw)
                if bb.problems:
                    br.problems += bb.problems
                queued.append({"cues": br.cues, "beat_start": b.start, "beat_end": b.end, "out_path": str(f), **kw})
            built = True
        beat = {"id": b.id, "mode": "footage", "start": b.start, "end": b.end, "purpose": f"explainer {'cartoon' if b.kind == 'cartoon' else 'board'}: {b.sents[0].label}",
                "footage": {"clips": [{"asset": clip_path, "reason": "explainer board clip drawn from this beat's own narration"}]}}
        if plate:                                       # the plan shows the Flow plate (moving slowly); the see-through board is laid over it after the render (integration.post_render)
            beat = {"id": b.id, "mode": "footage", "start": b.start, "end": b.end, "purpose": f"explainer {'cartoon' if b.kind == 'cartoon' else 'board'} over a picture: {b.sents[0].label}",
                    "footage": {"clips": [{"asset": "flow_image:" + plate, "kenburns": True, "reason": "the place and period this part of the story is about, behind the narrator"}]}}
            info.setdefault("scene_flow_beats", []).append(b.id)
        plan_beats[k] = beat
        if saved_pic is not None:
            from .. import fallbacks as FB
            FB.record(out_dir, b.picture_query, clip_path)
            plan_beats[k], b.kind = saved_pic, "footage"
            board_info[b.id] = {"cues": len(br.cues), "stand_in_for": b.picture_query, "clip": name, "built": built}
            continue
        evidence_subjects[b.id] = {"0": [spoken_subject(br.subject, words, b.start, b.end)]}
        board_info[b.id] = {"cues": len(br.cues), "kinds": sorted({c.kind for c in br.cues}), "dropped": br.dropped, "rescued": br.rescued, "lost": br.lost, "repairs": br.repairs, "still_gap_s": round(br.still_gap_s, 2), "still_gap_all_s": round(br.still_gap_all_s, 2), "still_gap_strict_s": round(br.still_gap_strict_s, 2),
                            **({"board_overlay": {"mov": clip_path, "start": b.start, "end": b.end, "plate": plate}} if plate else {}),
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
    if materialize:
        from ..board import jobs as BJ
        try:
            BJ.queue(out_dir, words, queued)
            if not opt.defer_boards:
                BJ.ensure_built(out_dir, log)
        except Exception as exc:        # a queue that cannot be saved: draw them now, one pool, so the plan never depends on it
            log(f"[Explainer] the board queue could not be saved ({str(exc)[:100]}); drawing the boards now")
            BJ.run(words, queued, log)
    plan = assemble_plan(total, plan_beats, {"dissolve_s": float(opt.dissolve_s)})
    fx_budget = motion_state["budget"].summary() if "budget" in motion_state else None
    # ---- gates ----
    def gates(plan_):
        probs: List[str] = []
        warns: List[str] = []
        rep_ = check_plan(plan_, words, subjects=evidence_subjects, base_dir=Path(opt.work_dir) / "explainer" if opt.work_dir else None,
                          allow_sources=LX.FOOTAGE_SOURCES if (opt.footage_share > 0 or opt.pictures or info.get("scene_flow_beats")) else (), composed=info.get("scene_flow_beats", ())) if materialize else None
        if rep_ is not None:
            late = [q["out_path"] for q in queued]       # a board clip still waiting in the queue is not a missing file
            probs += [p for p in rep_.problems if not (late and "file not found" in str(p) and any(q in str(p) for q in late))]
            warns += rep_.warnings
        else:
            from hybrid.plan import HybridPlan, PlanError, validate_plan
            try:
                probs += validate_plan(HybridPlan.from_dict(json.loads(json.dumps(plan_))))
            except PlanError as e:
                probs += e.problems
        probs += [f"{bid}: {p}" for bid, v in board_info.items() for p in v["problems"]]
        edit_: Dict[str, Any] = {}
        try:                                                              # the application's own editorial validator: its errors are what "Check plan" would block rendering on
            from hybrid.plan import HybridPlan
            from hybrid.validate import validate as hybrid_validate
            fnd = hybrid_validate(HybridPlan.from_dict(json.loads(json.dumps(plan_))))
            edit_ = {"errors": [f.message for f in fnd if f.severity == "error" and f.code != "technical"], "technical": [f.message for f in fnd if f.code == "technical"],
                     "warnings": [f.message for f in fnd if f.severity == "warning"]}
            probs += [f"hybrid.validate: {m}" for m in edit_["errors"]]          # technical findings are validate_plan's, already reported above
            warns += [f"hybrid.validate: {m}" for m in edit_["warnings"]]
        except Exception as exc:
            warns.append(f"hybrid.validate could not run: {exc!r}")
        return probs, warns, edit_, rep_

    probs_, warns_, editorial, rep = gates(plan)
    for _round in range(HEAL_ROUNDS):     # a problem on one beat never withholds the whole video: that beat is folded into its neighbour and the plan is checked again
        bad = beats_named(probs_, [bb["id"] for bb in plan["beats"]])
        if not bad or len(bad) > max(3, len(plan["beats"]) // 10):
            break
        healed = fold_beats(plan, bad)
        if not healed:
            break
        for bid, why in healed.items():
            board_info.pop(bid, None)
            evidence_subjects.pop(bid, None)
            res.warnings.append(f"{bid}: {why}")
        info.setdefault("healed_beats", []).extend(sorted(healed))
        log(f"[Explainer] {len(healed)} beat(s) with a problem folded into their neighbours: " + ", ".join(sorted(healed)))
        probs_, warns_, editorial, rep = gates(plan)
    res.problems += probs_
    res.warnings += warns_
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
