"""War Documentary direction pass: after the planner has chosen its cards, this adds the art direction on top, with restraint.

It runs once at the end of planner.plan() (config key "direction", default True; False reproduces the old plans exactly) and only ever
ADDS layers and shot treatments or swaps a plain number card for the big-number card. It never removes a card, never touches portraits,
equipment or credits, and every decision is logged in the scene's Decision (flags "dir:<rule>") and in plan.stats["direction"].

Rules (each fires only when the narration gives a reason; nothing decorates every sentence):
 1 footage treatment  slow push/pan varied shot to shot, cold grade for generic/illustrative footage, light vignette+grain, 0.4 s dissolve
                      between different adjacent clips (hard cut across a topic change, a map or a card boundary)
 2 tactical map       >=2 named places, or a place with strike/advance language -> tac_map (tactical); country-to-country context -> political
 3 claim stamp        'claimed', 'reportedly', 'unverified', 'denied' ... -> kit_stamp with the matching status
 4 emphasis tag       the point of a section (topic change, 'the key', 'the problem') -> kit_tag, at most one per 25 s
 5 big number         a headline figure (>=1000 or a percent) without a named claimant -> kit_bignum instead of stat_number, at most one per 40 s
 6 enumeration        3-5 short items -> kit_recap; ordinal items ('first ... second ...') -> kit_chips
 7 sticker / scale    a generic object named in the narration over missing or generic footage -> kit_sticker; 'N soldiers in single file' -> kit_scale
 8 section ribbon    'Now', 'Meanwhile', 'Later' ... at a topic change -> kit_ribbon, at most one per 60 s
 9 provenance badge   generic / illustrative / AI / archive / user footage -> kit_badge (replaces the equivalent old illustrative chip)
10 variety            the same decoration kind never appears in consecutive scenes; nothing is added over an existing card
11 no empty stretch   a scene without footage gets a truthful element at least every ~6 s, or the gap is logged
12 map build          a stretch of scenes without footage gets one political map that builds with the narration (map_build.py; config "map_build")
13 speaker / chapter  a named person with a role -> kit_speaker over footage (a white card on a map); 'Chapter 1, ...' -> kit_chapter
14 ratio / versus     'eight in ten X' -> kit_bignum '8 in 10'; '18 compared with 6', '106 for and 18 against' -> kit_versus
16 icons / flag      two to four things named over missing footage, no place -> kit_icons; a chapter opener -> a waving stripe flag before it
15 cuts and grade     a footage shot over 7 s is cut into 3-6 s shots; every clip but the user's own gets one film grade (config "split_shots",
                      "film_grade")
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..render import Layer, Shot
from . import semantics as S

FPS = 25
SOFT = {"kicker", "status_chip", "kit_badge", "kit_grain"}          # never block a decoration
DIM = {"kit_sticker", "kit_scale", "kit_recap", "kit_bignum"}
MOTIONS = ["push_in", "pan_right", "push_out", "pan_left"]

_CLAIM = re.compile(r"\b(claimed|claims|reportedly|allegedly|according to|unverified|cannot be verified|can't be verified|could not be verified|"
                    r"denied|denies|disputed|unconfirmed)\b", re.IGNORECASE)
_UNVERIFIED = re.compile(r"unverified|cannot be verified|can't be verified|could not be verified|reportedly|allegedly|unconfirmed", re.IGNORECASE)
_DISPUTED = re.compile(r"denied|denies|disputed", re.IGNORECASE)
_STRIKE = re.compile(r"\b(strike|strikes|struck|hit|hits|attack|attacked|attacks|advance|advanced|advancing|offensive|shelled|bombed|targeted|"
                     r"launched|drone|drones)\b", re.IGNORECASE)
_POINT = re.compile(r"\b(the key|the problem|what matters|the challenge|the question|the answer|the reason|the difference)\b", re.IGNORECASE)
_TOPIC = re.compile(r"^\W*(now|meanwhile|later|next|then|part\b|chapter\b|a year later|months later|weeks later|that changed|but then)\b", re.IGNORECASE)
_RIBBON_TEXT = {"now": "NOW", "meanwhile": "MEANWHILE", "later": "LATER", "next": "NEXT", "then": "THEN", "part": "NEXT", "chapter": "NEXT",
                "a year later": "A YEAR LATER", "months later": "MONTHS LATER", "weeks later": "WEEKS LATER"}
_STICKERS = [(r"\bdrones?\b", "drone", "DRONES"), (r"\b(tanks?|armou?r(?:ed)?)\b", "tank", "ARMOUR"), (r"\btrucks?\b", "truck", "TRUCKS"),
             (r"\b(missiles?|rockets?)\b", "missile", "MISSILES"), (r"\b(winter|snow|freezing|frozen|cold)\b", "snowflake", "WINTER"),
             (r"\b(pipes?|pipelines?|tunnels?)\b", "pipe", "PIPES"), (r"\b(fires?|burning|blaze)\b", "flame", "FIRE"),
             (r"\b(howitzers?|artillery|self-propelled)\b", "howitzer", "ARTILLERY"), (r"\b(himars|mlrs|rocket launchers?|grad|multiple launch)\b", "mlrs", "ROCKET LAUNCHERS"),
             (r"\b(armou?red personnel carriers?|apcs?|ifvs?|infantry fighting vehicles?|bradley|bmp)\b", "apc", "ARMOURED VEHICLES"),
             (r"\b(helicopters?|choppers?)\b", "helicopter", "HELICOPTERS"), (r"\b(jets?|fighters?|aircraft|warplanes?|bombers?|f-16s?)\b", "jet", "AIRCRAFT"),
             (r"\b(warships?|navy|fleet|frigates?|cruisers?|ships?)\b", "ship", "NAVAL"), (r"\b(radars?)\b", "radar", "RADAR"),
             (r"\b(patriot|pantsir|s-300|s-400|air defen[cs]e)\b", "aa_launcher", "AIR DEFENCE"), (r"\b(ammunition|ammo|munitions?)\b", "crate", "AMMUNITION"),
             (r"\b(shells?|shelling|shelled)\b", "shell", "SHELLS"), (r"\b(bombs?|bombing|bombed|glide bombs?)\b", "bomb", "BOMBS"),
             (r"\b(fuel|diesel|petrol|oil)\b", "barrel", "FUEL"), (r"\b(trains?|railways?|rail)\b", "train", "RAIL"),
             (r"\b(convoys?|columns?)\b", "convoy", "CONVOYS"), (r"\b(mortars?)\b", "mortar", "MORTARS"),
             (r"\b(rifles?|small arms|machine guns?)\b", "rifle", "SMALL ARMS"), (r"\b(medics?|wounded|field hospitals?)\b", "medic", "MEDICAL"),
             (r"\b(fpv|kamikaze drones?|loitering munitions?)\b", "fpv", "FPV DRONES"), (r"\b(soldiers?|troops?|infantry|men)\b", "soldier", "TROOPS"),
             (r"\b(binoculars?|reconnaissance|scouts?|observers?)\b", "binoculars", "RECON")]
_STICKERS.sort(key=lambda t: 0 if t[1] in ("fpv", "mlrs", "howitzer", "apc", "aa_launcher") else 1)   # specific systems before generic words
_NUMWORD = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "twelve": 12, "fifteen": 15, "twenty": 20}
_SCALE = re.compile(r"\b(\d{1,2}|" + "|".join(_NUMWORD) + r")\s+(soldiers|men)\b[^.]{0,60}\b(single file|in a row|in a line|one after another)", re.IGNORECASE)
_ORDINAL = re.compile(r"\b(first|second|third|fourth)\b", re.IGNORECASE)


def _phrase(sentence: str) -> str:
    """3-6 words that end on a natural boundary (comma, 'and', 'because' ...), taken verbatim from the sentence; '' when there is none."""
    for piece in re.split(r",|;|:| because | while | and | but | which | that | so ", sentence.strip()):
        w = piece.strip(" .\"'").split()
        if 3 <= len(w) <= 6 and w[-1].lower() not in {"of", "the", "a", "an", "to", "in", "on", "at", "with", "for", "by", "as", "from"}:
            return " ".join(w)
    return ""


_STOP_END = {"of", "the", "a", "an", "to", "in", "on", "at", "with", "for", "by", "as", "from", "and", "or", "but", "that", "which", "is", "are", "was",
             "were", "its", "their", "his", "her", "this", "these", "those"}


def _phrase_or_lead(sentence: str) -> str:
    """_phrase, else the sentence's first 3-6 words ending on a content word (verbatim): a long sentence with no comma still gives a tag."""
    h = _phrase(sentence)
    if h:
        return h
    w = sentence.strip(" .\"'").split()
    for n in range(min(6, len(w)), 2, -1):
        if w[n - 1].strip(",;:").lower() not in _STOP_END:
            return " ".join(w[:n]).rstrip(",;:")
    return ""


def fr(t: float) -> float:
    return round(float(t) * FPS) / FPS


# ------------------------------------------------------------------------------------------------ time helpers ---------------------
class _Busy:
    def __init__(self, layers: Sequence[Layer]) -> None:
        self.items: List[Tuple[float, float, str]] = [(ly.start, ly.end, ly.kind) for ly in layers if ly.kind not in SOFT]

    def add(self, a: float, b: float, kind: str) -> None:
        self.items.append((a, b, kind))

    def free(self, a: float, b: float, need: float, *, ignore: Sequence[str] = (), margin: float = 0.25) -> Optional[Tuple[float, float]]:
        """Earliest sub-window of [a, b] at least `need` long that touches no busy interval (with a small margin)."""
        iv = sorted((s - margin, e + margin) for s, e, k in self.items if k not in ignore and e > a and s < b)
        cur = a
        for s, e in iv:
            if s - cur >= need - 1e-9:
                return fr(cur), fr(min(b, max(cur + need, s)))
            cur = max(cur, e)
        if b - cur >= need - 1e-9:
            return fr(cur), fr(b)
        return None

    def kinds_in(self, a: float, b: float) -> List[str]:
        return [k for s, e, k in self.items if e > a and s < b]


# ------------------------------------------------------------------------------------------------ footage ------------------------
def _meta_class(meta: Dict[str, Any]) -> str:
    """ai | user | archive | illustrative | stock | '' (verified/own event footage)."""
    meta = meta or {}
    prov = str(meta.get("provider") or meta.get("source") or "").lower()
    if meta.get("user_supplied") or meta.get("kind") == "user":
        return "user"
    if meta.get("kind") == "generated" or prov in ("flow", "flow_video", "flow_image") or "generated" in prov:
        return "ai"
    if prov in ("nasa", "archive", "commons", "wikimedia") or "archive" in prov:
        return "archive"
    if meta.get("mismatch") or meta.get("generic") or meta.get("footage_class") == "illustrative":
        return "illustrative"
    if meta.get("stock_relevant"):
        return "stock"
    return ""


def _grade(cls: str, film: bool = False) -> str:
    if cls == "user":
        return "neutral"                       # the user's own clip is shown as they gave it
    if film:
        return "warm_archive" if cls == "archive" else "film"
    return "neutral" if cls == "" else "cold"


CUT_MIN, CUT_MAX, SPLIT_OVER = 3.0, 6.0, 7.0      # a footage scene longer than SPLIT_OVER s is cut into shots of CUT_MIN..CUT_MAX s


def _clip_seconds(path: str) -> Optional[float]:
    import subprocess

    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", path], capture_output=True,
                           text=True, timeout=15)
        return float(r.stdout.strip())
    except Exception:
        return None


def _split_long_shots(plan: Any, meta_by_start: Dict[float, Dict[str, Any]], counts: Dict[str, int], probe=_clip_seconds) -> None:
    """Rule 15 (REFERENCE_PATTERNS item 18): one clip never holds the screen for 10 s. A long footage shot becomes 3-6 s cuts; when the clip is
    long enough each cut shows a different moment of it (spread over the clip), otherwise the clip runs on and the cut is a change of framing."""
    out: List[Shot] = []
    lengths: Dict[str, Optional[float]] = {}
    for sh in sorted(plan.shots, key=lambda s: s.start):
        dur = sh.end - sh.start
        if dur <= SPLIT_OVER:
            out.append(sh)
            continue
        n = max(2, int(round(dur / ((CUT_MIN + CUT_MAX) / 2))))
        if sh.path not in lengths:
            lengths[sh.path] = probe(sh.path)
        clip_len = lengths[sh.path]
        piece = dur / n
        spread = clip_len is not None and clip_len - sh.seek >= dur + 2.0
        meta = meta_by_start.get(fr(sh.start)) or {}
        for i in range(n):
            a, b = fr(sh.start + i * piece), fr(sh.end if i == n - 1 else sh.start + (i + 1) * piece)
            seek = sh.seek + (i * (clip_len - sh.seek - piece - 0.5) / max(1, n - 1) if spread else (a - sh.start))
            out.append(Shot(sh.path, a, b, round(max(0.0, seek), 3), dissolve_in=sh.dissolve_in if i == 0 else 0.0))
            meta_by_start.setdefault(a, meta)
        counts["split_shots"] = counts.get("split_shots", 0) + 1
    plan.shots[:] = out


def _treat_shots(plan: Any, meta_by_start: Dict[float, Dict[str, Any]], hard_cuts: Sequence[float], full_spans: Sequence[Tuple[float, float]],
                 counts: Dict[str, int], film: bool = False) -> None:
    prev: Optional[Shot] = None
    last_motion = ""
    n = 0
    for sh in sorted(plan.shots, key=lambda s: s.start):
        meta = meta_by_start.get(fr(sh.start)) or {}
        cls = _meta_class(meta)
        motion = MOTIONS[n % len(MOTIONS)]
        if motion == last_motion:
            motion = MOTIONS[(n + 1) % len(MOTIONS)]
        n += 1
        last_motion = motion
        dur = sh.end - sh.start
        z1 = 1.04 if dur < 4 else 1.06
        sh.treat = {"motion": motion, "z0": 1.0, "z1": z1, "grade": _grade(cls, film), "vignette": 0.25, "grain": 0.3, "blur_fill": "auto"}
        counts["treated_shots"] = counts.get("treated_shots", 0) + 1
        if prev is not None and abs(prev.end - sh.start) < 1.0 / FPS and prev.path != sh.path and dur >= 1.6 and (prev.end - prev.start) >= 1.6:
            cut = any(abs(sh.start - c) < 0.2 for c in hard_cuts)
            boundary_card = any(a - 0.05 <= sh.start <= b + 0.05 for a, b in full_spans)
            if not cut and not boundary_card:
                sh.dissolve_in = 0.4
                counts["dissolves"] = counts.get("dissolves", 0) + 1
        prev = sh


# ------------------------------------------------------------------------------------------------ sentence rules ------------------
def _sent_window(A: Any, sent: Any, st: float, en: float, lead: float = 0.3, tail: float = 0.8) -> Tuple[float, float]:
    a = max(st, A.time_at(sent.span[0]) - lead)
    b = min(en, A.end_time_of(sent.span) + tail)
    return fr(a), fr(max(a, b))


class _Extra:
    kind, country = "place", False

    def __init__(self, name: str, span: Tuple[int, int]) -> None:
        self.name, self.span, self.id, self.entry = name, span, name.lower(), None


def _places(sent: Any) -> List[Any]:
    seen, out = set(), []
    for e in sent.entities:
        if e.kind == "place" and not e.country and e.name.lower() not in seen:
            seen.add(e.name.lower())
            out.append(e)
    try:                                  # towns the catalogue lacks (Ryazan, Kupiansk ...) that the tactical map can place exactly
        from .maps_tactical import resolve_place

        pos = []
        for e in out:
            h0, _w = resolve_place(e.name)
            if h0:
                pos.append((h0["lat"], h0["lon"]))
        for m in re.finditer(r"\b([A-Z][a-z]+(?:\s[A-Z][a-z]+)?)\b", sent.text):
            nm = m.group(1)
            if nm.lower() in seen:
                continue
            hit, _why = resolve_place(nm)
            if hit and not any(abs(hit["lat"] - a) < 0.3 and abs(hit["lon"] - b) < 0.3 for a, b in pos):
                seen.add(nm.lower())
                pos.append((hit["lat"], hit["lon"]))
                out.append(_Extra(nm, (m.start(), m.end())))
    except Exception:
        pass
    return out


def _countries(sent: Any) -> List[Any]:
    seen, out = set(), []
    for e in sent.entities:
        if e.kind == "place" and e.country and e.name.lower() not in seen:
            seen.add(e.name.lower())
            out.append(e)
    return out


def _items(text: str) -> List[str]:
    """3-5 short list items joined by commas and 'and' ('tunnels, scooters, civilian clothes and human cover'), else []."""
    m = re.search(r"(?:[:;]|\b(?:include|includes|including|such as|were|was|are|is|of)\b)\s+([^.]+?)\.?$", text.strip(), re.IGNORECASE)
    tail = m.group(1) if m else text
    parts = [p.strip(" ,") for p in re.split(r",\s*(?:and\s+)?|\s+and\s+", tail) if p.strip(" ,")]
    if 3 <= len(parts) <= 5 and all(1 <= len(p.split()) <= 4 for p in parts):
        return parts
    return []


def _tac_params(sent: Any, places: List[Any], countries: List[Any], political: bool) -> Dict[str, Any]:
    p: Dict[str, Any] = {"theme": "political" if political else "tactical", "places": [{"name": e.name} for e in places[:5]], "routes": [], "glyphs": [],
                         "chips": []}
    if political and not places:
        p["places"] = []
        p["frame"] = "ukraine"
    mo = sent.motion
    if mo is not None and not political:
        o, d = mo[0], mo[1]
        if o.kind == "place" and d.kind == "place" and o.name != d.name:
            p["routes"].append({"from": o.name, "to": d.name, "style": "arrow", "start": 1.0})
    if _STRIKE.search(sent.text) and not political:
        for e in places[:3]:
            p["glyphs"].append({"place": e.name, "kind": "ring"})
        nm = "drone" if re.search(r"\bdrones?\b", sent.text, re.IGNORECASE) else "missile" if re.search(r"\b(missiles?|rockets?)\b", sent.text, re.IGNORECASE) else ""
        if nm and places:
            p["glyphs"].append({"place": places[0].name, "kind": "sticker", "name": nm, "start": 1.8})     # the named weapon beside the first place, symbolic
    for n in sent.numbers[:2]:
        if n.complete and not n.is_year:
            p["chips"].append({"title": n.raw, "sub": n.unit or "as stated in the narration", "variant": "dark"})
    if not places and not political:
        return {}
    p["places"] = [{"name": e.name, "kind": "pin"} for e in places[:5]] if not political else p["places"]
    return p


def _no_empty_stretch(plan: Any, rows: Sequence[Dict[str, Any]], cat: Any, log_by_no: Dict[str, Any], counts: Dict[str, int], notes: List[str]) -> None:
    """Rule 11: wherever no footage is on screen, something truthful (a card, map, sticker or the narration's own words as a tag) appears at
    least every ~6 s. Where nothing truthful exists the stretch is logged, never filled with invention."""
    total = max((r["_end"] for r in rows), default=0.0)
    plate: List[Tuple[float, float]] = []
    cur = 0.0
    for sh in sorted(plan.shots, key=lambda s: s.start):
        if sh.start - cur > 0.04:
            plate.append((cur, sh.start))
        cur = max(cur, sh.end)
    if total - cur > 0.04:
        plate.append((cur, total))
    busy = _Busy(plan.layers)
    flip = 0
    for g0, g1 in plate:
        t = g0
        while g1 - t >= 3.6:
            slot = busy.free(t, g1, 3.6, margin=0.0, ignore=("shot_headline",))
            if slot is None:
                break
            w0 = slot[0]
            row = next((r for r in rows if r["_start"] - 0.01 <= w0 < r["_end"]), None)
            h = ""
            if row:
                A2 = S.analyze_scene(str(row.get("text") or ""), cat, row.get("words"), row["_start"], row["_end"])
                sent = next((x for x in A2.sentences if A2.time_at(x.span[0]) - 0.2 <= w0 + 0.6 <= A2.end_time_of(x.span) + 0.6), A2.sentences[-1] if A2.sentences else None)
                h = _phrase_or_lead(sent.text) if sent is not None else ""
            dec = log_by_no.get(str(row["_no"])) if row else None
            if not h or dec is None:
                notes.append(f"nothing truthful to show at {w0:.1f}s")
                if dec is not None:
                    dec.flags.append("dir:empty_stretch")
                t = w0 + 3.6
                continue
            a = fr(w0 + 0.6)
            ly = Layer("kit_tag", a, fr(a + 3.2), {"text": h, "pos": "top-left" if flip % 2 == 0 else "lower-left", "style": "hook"}, dim=False)
            flip += 1
            plan.layers.append(ly)
            busy.add(ly.start, ly.end, "kit_tag")
            dec.flags.append("dir:fallback_tag")
            dec.candidates.append({"kind": "kit_tag", "score": 0.0, "reason": "direction: no footage here, the narration's own words as a tag", "accepted": True,
                                   "start": ly.start, "end": ly.end})
            counts["fallback_tags"] = counts.get("fallback_tags", 0) + 1
            t = ly.end



# ------------------------------------------------------------------------------------------------ layout choice -----------------------
# What the narration means picks the composition. Existing planner layers are upgraded in place (params only restated, nothing invented):
# quotation -> figure hero, named system -> equipment hero, number -> stat split, dated events -> timeline, claim -> claim layout.
# Supply language that names two or more chain links -> logistics diagram. Two full-frame compositions never meet within FULL_GAP s.
LAYOUT_KINDS = {"lay_figure_hero", "lay_figure_pair", "lay_equipment_hero", "lay_equipment_compare", "lay_stat_split", "lay_timeline", "lay_claim",
                "lay_logistics"}
FULL_KINDS = {"map_card", "timeline", "split_compare", "tac_map", "tac_route", "stat_compare", "kit_icons", "kit_flag"} | LAYOUT_KINDS
FULL_GAP = 1.2
_LOGISTICS = [(r"\brefiner(?:y|ies)\b", "Refinery", "flame"), (r"\b(?:pipeline|pipelines)\b", "Pipeline", "pipe"), (r"\b(?:rail|railway|railways|train|trains)\b", "Rail", "truck"),
              (r"\b(?:trucks?|convoys?)\b", "Trucks", "truck"), (r"\b(?:depot|depots|warehouse|warehouses|stockpiles?)\b", "Depot", "shield"),
              (r"\b(?:fuel|oil|diesel|petrol)\b", "Fuel", "flame"), (r"\b(?:ammunition|shells?)\b", "Ammunition", "missile"),
              (r"\b(?:front|frontline|front line)\b", "Front", "soldier")]
_LOGI_TRIGGER = re.compile(r"\b(supply|supplies|supplied|logistics|resupply|fuel|ammunition|pipeline|exports?|imports?|economy|sanctions?|revenue)\b", re.IGNORECASE)


def _near_full(spans: Sequence[Tuple[float, float]], a: float, b: float) -> bool:
    return any(y > a - FULL_GAP and x < b + FULL_GAP for x, y in spans)


def _logistics_nodes(text: str) -> List[Dict[str, str]]:
    hits = []
    for rx, label, icon in _LOGISTICS:
        m = re.search(rx, text, re.IGNORECASE)
        if m:
            hits.append((m.start(), label, icon))
    hits.sort()
    seen, nodes = set(), []
    for _pos, label, icon in hits:
        if label not in seen:
            seen.add(label)
            nodes.append({"label": label, "icon": icon})
    return nodes[:4]


def _choose_layouts(plan: Any, rows: Sequence[Dict[str, Any]], cat: Any, log_by_no: Dict[str, Any], counts: Dict[str, int]) -> List[Tuple[float, float]]:
    """Returns the full-frame spans after the pass (maps included) so later decoration respects them."""
    def logged(layer: Any, kind: str, why: str) -> None:
        for r in rows:
            if r["_start"] - 0.01 <= layer.start < r["_end"] + 0.01:
                dec = log_by_no.get(str(r["_no"]))
                if dec is not None:
                    dec.flags.append("dir:layout_" + kind)
                    dec.candidates.append({"kind": kind, "score": 0.0, "reason": "direction: " + why, "accepted": True, "start": layer.start, "end": layer.end})
                break

    spans = sorted((ly.start, ly.end) for ly in plan.layers if ly.kind in FULL_KINDS)

    def drop_kicker(ly: Any) -> None:
        plan.layers[:] = [x for x in plan.layers if not (x.kind == "kicker" and abs(x.start - ly.start) < 0.01 and abs(x.end - ly.end) < 0.01)]

    def convert(ly: Any, kind: str, params: Dict[str, Any], why: str) -> bool:
        others = [s for s in spans if not (abs(s[0] - ly.start) < 1e-6 and abs(s[1] - ly.end) < 1e-6)]
        if _near_full(others, ly.start, ly.end):
            counts["layout_skipped_adjacent"] = counts.get("layout_skipped_adjacent", 0) + 1
            return False
        ly.kind, ly.params, ly.dim = kind, params, True
        drop_kicker(ly)
        if (ly.start, ly.end) not in spans:
            spans.append((ly.start, ly.end))
        counts[kind] = counts.get(kind, 0) + 1
        logged(ly, kind, why)
        return True

    last_big = -999.0
    for ly in sorted(plan.layers, key=lambda x: x.start):
        p = dict(ly.params or {})
        if ly.kind == "figure_card" and p.get("name"):
            convert(ly, "lay_figure_hero", p, "a named person speaks: portrait, name, role, then the statement")
        elif ly.kind == "equipment_card" and p.get("name") and not p.get("generic"):
            p["image_credit"] = p.get("image_credit") or ""
            convert(ly, "lay_equipment_hero", p, "a named system: photo or labelled silhouette with its sourced specs")
        elif ly.kind == "stat_number" and p.get("value") is not None:
            big = (isinstance(p.get("value"), (int, float)) and p.get("value", 0) >= 1000) or p.get("unit") == "%"
            if big and not p.get("claimant") and ly.start - last_big >= 40.0:
                last_big = ly.start               # the headline figure goes large (big-number pass); later numbers get the split layout
                continue
            convert(ly, "lay_stat_split", p, "a stated figure: the number, then what it measures")
        elif ly.kind == "timeline" and len(p.get("events") or []) >= 2:
            items = [{"date": str(e.get("date", "")), "text": str(e.get("label", ""))} for e in p["events"] if isinstance(e, dict) and e.get("date")]
            if len(items) >= 2:
                convert(ly, "lay_timeline", {"title": p.get("title") or "Key dates", "items": items[:6], "times": p.get("times"), "status": p.get("status")},
                        "dated events in the narration's own order")
        elif ly.kind == "evidence_card" and str(p.get("kind")) == "claim" and p.get("words"):
            words = [str(w) for w in p["words"]]
            mk = p.get("mark")
            hl = " ".join(words[mk[0]:mk[1] + 1]) if mk and 0 <= mk[0] <= mk[1] < len(words) else ""
            convert(ly, "lay_claim", {"claim": " ".join(words), "claimant": p.get("claimant") or p.get("outlet") or "", "date": p.get("date") or "", "highlight": hl,
                                      "status": p.get("status") or "claimed", "source": p.get("outlet") or ""}, "a claim: attributed, never stated as fact")

    # supply / economy language naming at least two chain links
    for r in rows:
        dec = log_by_no.get(str(r["_no"]))
        if dec is None:
            continue
        A = S.analyze_scene(str(r.get("text") or ""), cat, r.get("words"), r["_start"], r["_end"])
        for sent in A.sentences:
            if not _LOGI_TRIGGER.search(sent.text):
                continue
            nodes = _logistics_nodes(sent.text)
            if len(nodes) < 2:
                continue
            a, b = _sent_window(A, sent, r["_start"], r["_end"])
            b = max(b, a + 4.2)
            if b > r["_end"] + 0.5 or _near_full(spans, a, b) or any(l.start < b and l.end > a for l in plan.layers if l.kind not in ("kicker", "shot_headline", "status_chip", "kit_badge")):
                continue
            ly = Layer("lay_logistics", fr(a), fr(b), {"title": "Supply chain", "nodes": nodes, "links": []}, dim=True)
            plan.layers.append(ly)
            spans.append((ly.start, ly.end))
            counts["lay_logistics"] = counts.get("lay_logistics", 0) + 1
            logged(ly, "lay_logistics", "supply language naming " + ", ".join(n["label"] for n in nodes))
            break
    # a stat or claim layout leaves half the frame open: the named thing (drones, tanks ...) stands there as a sticker, in the empty half
    for ly in [x for x in plan.layers if x.kind in ("lay_stat_split", "lay_claim")]:
        row = next((r for r in rows if r["_start"] - 0.01 <= ly.start < r["_end"] + 0.01), None)
        text = str((row or {}).get("text") or "")
        for rx, name, lab in _STICKERS:
            mm = re.search(rx, text, re.IGNORECASE)
            if mm:
                if name == "drone" and re.search(r"\benemy\s+drones?\b", text, re.IGNORECASE):
                    lab = "ENEMY DRONES"
                a = fr(ly.start + 1.0)
                plan.layers.append(Layer("kit_sticker", a, fr(max(a + 2.4, ly.end - 0.3)), {"name": name, "x": 0.72, "y": 0.5, "size": 300, "label": lab,
                                                                                         "label_style": "tape"}, dim=False))
                counts["layout_sticker"] = counts.get("layout_sticker", 0) + 1
                break
    return sorted((ly.start, ly.end) for ly in plan.layers if ly.kind in FULL_KINDS)


def _extend_into_plate(plan: Any, rows: Sequence[Dict[str, Any]], max_extra: float = 3.0) -> None:
    """Wherever no footage is on screen and no full-frame composition covers the plate, the composition before the gap stays up (its own motion
    carries it) until the next shot or next composition, at most max_extra s longer; failing that the next one starts earlier (layouts only,
    because a map's reveal is timed to the narration). The narration's end is never passed."""
    total = max((r["_end"] for r in rows), default=0.0)
    cover = (LAYOUT_KINDS | {"tac_map", "tac_route", "timeline", "map_card"})
    for _ in range(1):                       # one short hold per gap: a card never stays up through the next sentence's subject
        spans = sorted([(sh.start, sh.end) for sh in plan.shots] + [(ly.start, ly.end) for ly in plan.layers if ly.kind in FULL_KINDS])
        gaps, cur = [], 0.0
        for x, y in spans:
            if x - cur > 0.6:
                gaps.append((cur, x))
            cur = max(cur, y)
        if total - cur > 0.6:
            gaps.append((cur, total))
        if not gaps:
            return
        moved = False
        for g0, g1 in gaps:
            prev = [ly for ly in plan.layers if ly.kind in cover and abs(ly.end - g0) < 0.05]
            if prev and prev[0].kind in cover:
                nxt_starts = [ly.start for ly in plan.layers if ly is not prev[0] and ly.start >= g0 - 0.01
                              and ly.kind not in ("kit_badge", "kicker", "shot_headline", "status_chip")]
                limit = min([g1, g0 + max_extra] + [x - 0.35 for x in nxt_starts])   # never into the next card
                if limit - g0 < 0.4:
                    continue
                prev[0].end = fr(limit)
                moved = True
                continue
            nxt = [ly for ly in plan.layers if ly.kind in LAYOUT_KINDS and abs(ly.start - g1) < 0.05]
            if nxt:
                nxt[0].start = fr(max(g0, g1 - max_extra))
                moved = True
        if not moved:
            return


def _chapter_flag(rows: Sequence[Dict[str, Any]], row: Dict[str, Any], cat: Any) -> str:
    """The flag of the first country the chapter's opening (its row and the next two) names, if it is a stripe flag; else Ukraine when the
    video is about Ukraine; else '' (no flag is ever guessed)."""
    from .cards_kit import FLAGS
    from .maps_tactical import G

    i = next((k for k, x in enumerate(rows) if x is row), 0)
    for x in rows[i:i + 3]:
        A = S.analyze_scene(str(x.get("text") or ""), cat, x.get("words"), x["_start"], x["_end"])
        for sent in A.sentences:
            for c in _countries(sent):
                f = G.find_country(c.name)
                if f is not None and f.iso in FLAGS:
                    return f.iso
    every = " ".join(str(x.get("text") or "") for x in rows)
    return "UKR" if re.search(r"\bukrain", every, re.IGNORECASE) else ""


_ICON_LINK_VS = re.compile(r"\b(vs|versus|against|than|compared)\b", re.IGNORECASE)
_ICON_LINK_ARROW = re.compile(r"\b(into|then|leads?|turns?|becomes?|so|sent|shipped|moved|feeds?|empt\w*|drain\w*|forc\w*)\b", re.IGNORECASE)


def _icon_scenes(plan: Any, rows: Sequence[Dict[str, Any]], cat: Any, log_by_no: Dict[str, Any], counts: Dict[str, int], maps_rebuilt: bool = False) -> None:
    """Rule 16 (REFERENCE_PATTERNS item 19): a sentence over missing footage that names two to four things the icon set has (drones, air
    defence, ammunition ...) and no place becomes flat icons on a blurred plate, labelled with the narration's own words, linked by an arrow
    (one leads to the next) or VS. At most one per 30 s; never over another full-frame card."""
    last = -999.0
    block = FULL_KINDS - ({"tac_map", "tac_route", "map_card"} if maps_rebuilt else set())     # short maps give way: map_build redraws them
    for r in rows:
        dec = log_by_no.get(str(r["_no"]))
        if dec is None or "no_footage" not in dec.flags or not str(r.get("text") or "").strip():
            continue
        A = S.analyze_scene(str(r.get("text") or ""), cat, r.get("words"), r["_start"], r["_end"])
        for sent in A.sentences:
            if _places(sent) or _countries(sent):
                continue                                   # a place belongs on the map
            found: List[Tuple[int, str, str]] = []
            for rx, name, _lab in _STICKERS:
                mm = re.search(rx, sent.text, re.IGNORECASE)
                if mm and name not in [f[1] for f in found] and not any(f[0] <= mm.start() < f[0] + 12 for f in found):
                    found.append((mm.start(), name, mm.group(0)))
            if not 2 <= len(found) <= 4:
                continue
            found.sort()
            a, b = _sent_window(A, sent, r["_start"], r["_end"])
            b = max(b, a + 3.6)
            if a - last < 30.0 or any(ly.kind in block and ly.start < b and ly.end > a for ly in plan.layers):
                continue
            icons = [{"name": nm, "label": word, "start": fr(max(0.3, A.time_at(sent.span[0] + pos) - a))} for pos, nm, word in found]
            link = "vs" if _ICON_LINK_VS.search(sent.text) else "arrow" if _ICON_LINK_ARROW.search(sent.text) else ""
            plan.layers.append(Layer("kit_icons", fr(a), fr(min(b, a + 6.0)), {"icons": icons, "link": link, "title": _phrase(sent.text), "seed": int(r["_no"]) if str(r["_no"]).isdigit() else 0}, dim=False))
            dec.flags.append("dir:icons")
            dec.candidates.append({"kind": "kit_icons", "score": 0.0, "reason": f"direction: {len(icons)} things named, no place: icon explainer",
                                   "accepted": True, "start": fr(a), "end": fr(min(b, a + 6.0))})
            counts["icons"] = counts.get("icons", 0) + 1
            last = a
            break


def _speakers(plan: Any, rows: Sequence[Dict[str, Any]], cat: Any, log_by_no: Dict[str, Any], counts: Dict[str, int]) -> None:
    """Rule 13: a named person introduced with a role over footage gets a speaker card (name, role) top right for 4 s, in the narration's words.
    On a building map the same person is a white card in the stack (map_build.card_for); a card already in that corner is never covered."""
    from .map_build import speaker_of

    corner = ("kit_stamp", "kit_chips", "kit_speaker", "evidence_card", "figure_card") + tuple(FULL_KINDS)
    for r in rows:
        dec = log_by_no.get(str(r["_no"]))
        if dec is None or "no_footage" in dec.flags or not str(r.get("text") or "").strip():
            continue
        A = S.analyze_scene(str(r.get("text") or ""), cat, r.get("words"), r["_start"], r["_end"])
        for sent in A.sentences:
            spk = speaker_of(sent.text)
            if not spk:
                continue
            a = fr(max(r["_start"], A.time_at(sent.span[0]) + 0.2))
            b = fr(min(r["_end"] + 0.5, a + 4.0))
            if b - a < 1.5 or any(ly.kind in corner and ly.start < b and ly.end > a for ly in plan.layers):
                continue
            plan.layers.append(Layer("kit_speaker", a, b, {"name": spk[0], "role": spk[1]}, dim=False))
            dec.flags.append("dir:speaker")
            dec.candidates.append({"kind": "kit_speaker", "score": 0.0, "reason": f"direction: {spk[0]} introduced as {spk[1]}", "accepted": True, "start": a, "end": b})
            counts["speaker"] = counts.get("speaker", 0) + 1
            break


def _ratios_and_versus(plan: Any, rows: Sequence[Dict[str, Any]], cat: Any, log_by_no: Dict[str, Any], counts: Dict[str, int]) -> None:
    """Rule 14: 'eight in ten X' -> the big-number card '8 in 10' with what it counts; two figures set against each other ('18 compared with
    6', '106 for and 18 against', 'from 6 to 18') -> kit_versus. A plain number card at the same moment is replaced (this one says more);
    a layout or other full-frame card is never covered. At most one per 20 s."""
    from .map_build import ratio_of, versus_of

    block = FULL_KINDS - {"tac_map", "tac_route", "map_card"}
    last = -999.0
    for r in rows:
        dec = log_by_no.get(str(r["_no"]))
        if dec is None or not str(r.get("text") or "").strip():
            continue
        A = S.analyze_scene(str(r.get("text") or ""), cat, r.get("words"), r["_start"], r["_end"])
        for sent in A.sentences:
            vs = versus_of(sent.text)
            rt = None if vs else ratio_of(sent.text)
            if not (vs or rt):
                continue
            a = fr(max(r["_start"], A.time_at(sent.span[0]) + 0.2))
            b = fr(min(r["_end"] + 0.5, a + 4.2))
            if b - a < 2.0 or a - last < 20.0 or any(ly.kind in block and ly.start < b and ly.end > a for ly in plan.layers):
                continue
            plan.layers[:] = [ly for ly in plan.layers if not (ly.kind in ("stat_number", "kit_bignum", "kicker") and ly.start < b and ly.end > a)]
            if vs:
                plan.layers.append(Layer("kit_versus", a, b, dict(vs, title=""), dim=True))
            else:
                plan.layers.append(Layer("kit_bignum", a, b, {"value": rt["value"], "label": rt["label"].upper(), "sub": rt["sub"], "colour": "yellow",
                                                              "count": False}, dim=True))
            rule = "versus" if vs else "ratio"
            dec.flags.append("dir:" + rule)
            dec.candidates.append({"kind": "kit_versus" if vs else "kit_bignum", "score": 0.0, "reason": f"direction: {rule} stated in the narration",
                                   "accepted": True, "start": a, "end": b})
            counts[rule] = counts.get(rule, 0) + 1
            last = a
            break


# ------------------------------------------------------------------------------------------------ the pass ----------------------------
def apply(plan: Any, rows: Sequence[Dict[str, Any]], cfg: Dict[str, Any], cat: Any) -> Dict[str, Any]:
    counts: Dict[str, int] = {}
    log_by_no = {str(d.scene_no): d for d in plan.log}
    rows = sorted(rows, key=lambda r: (r["_start"], str(r["_no"])))
    meta_by_start = {fr(r["_start"]): (r.get("footage_meta") or {}) for r in rows}
    layout_spans: List[Tuple[float, float]] = []
    if cfg.get("layouts", True):
        layout_spans = _choose_layouts(plan, rows, cat, log_by_no, counts)
    busy = _Busy(plan.layers)
    new_layers: List[Layer] = []

    def add(kind: str, a: float, b: float, params: Dict[str, Any], dec: Any, rule: str, why: str, scene_end: float, dim: Optional[bool] = None) -> bool:
        a, b = fr(a), fr(min(b, scene_end + 0.5))
        if b - a < 0.8:
            return False
        ly = Layer(kind, a, b, params, dim=(kind in DIM) if dim is None else dim)
        new_layers.append(ly)
        busy.add(a, b, kind)
        dec.flags.append("dir:" + rule)
        dec.candidates.append({"kind": kind, "score": 0.0, "reason": f"direction: {why}", "accepted": True, "start": a, "end": b})
        counts[rule] = counts.get(rule, 0) + 1
        return True

    last_kind = ""
    last_at: Dict[str, float] = {}
    ribbon_cuts: List[float] = []
    full_spans = [(ly.start, ly.end) for ly in plan.layers if ly.kind in FULL_KINDS]
    first_scene = True
    gap_notes: List[str] = []

    for r in rows:
        no, st, en = r["_no"], r["_start"], r["_end"]
        dec = log_by_no.get(str(no))
        text = str(r.get("text") or "")
        if dec is None or not text.strip():
            first_scene = False
            continue
        has_footage = "no_footage" not in dec.flags
        meta = r.get("footage_meta") or {}
        cls = _meta_class(meta) if "no_footage" not in dec.flags else ""
        A = S.analyze_scene(text, cat, r.get("words"), st, en)
        picked: Optional[str] = None

        # ---- 8 ribbon (topic change) -----------------------------------------------------------------------------------------
        first = A.sentences[0] if A.sentences else None
        topic_change = bool(first and _TOPIC.search(first.text))
        from .map_build import chapter_of

        chap = chapter_of(first.text) if first else None
        if chap:                          # a chapter opener: yellow chip and subtitle over whatever is on screen
            a0 = max(st, A.time_at(first.span[0]))
            iso = _chapter_flag(rows, r, cat) if cfg.get("flags", True) and a0 >= 1.0 else ""
            if iso:                       # the flag waves for a moment before the chapter opens
                add("kit_flag", a0 - 0.9, a0, {"iso3": iso}, dec, "flag", f"{iso} flag before {chap[0].title()}", en, dim=False)
            plan.layers[:] = [ly for ly in plan.layers if not (ly.kind in ("stat_number", "kit_bignum", "lay_stat_split", "kicker")      # 'Chapter 2' is
                                                                and ly.start < a0 + 3.6 and ly.end > a0 and st - 0.01 <= ly.start < en)]  # not a statistic
            if add("kit_chapter", a0, a0 + 3.6, {"label": chap[0], "sub": chap[1]}, dec, "chapter", f"'{chap[0].title()}' opens a chapter", en + 3.0, dim=False):
                last_at["kit_ribbon"] = st
                ribbon_cuts.append(st)
        elif topic_change and not first_scene and st - last_at.get("kit_ribbon", -999) >= 60.0:
            m = _TOPIC.search(first.text)
            key = m.group(1).lower()
            label = _RIBBON_TEXT.get(key, "NEXT")
            slot = busy.free(st, min(en, st + 1.6), 1.2, ignore=("shot_headline",))
            if slot and add("kit_ribbon", slot[0], slot[0] + 1.3, {"text": label, "colour": "red"}, dec, "ribbon", f"topic change ('{key}')", en, dim=False):
                last_at["kit_ribbon"] = st
                ribbon_cuts.append(st)

        # ---- 5 big number (swap of an accepted stat_number) ------------------------------------------------------------------------
        for ly in plan.layers:
            if ly.kind == "stat_number" and st - 0.01 <= ly.start < en and st - last_at.get("kit_bignum", -999) >= 40.0 and last_kind != "kit_bignum":
                p = ly.params or {}
                big = (isinstance(p.get("value"), (int, float)) and p.get("value", 0) >= 1000) or p.get("unit") == "%"
                if big and not p.get("claimant"):
                    shown = str(p.get("shown") or p.get("value"))
                    ly.kind = "kit_bignum"
                    ly.dim = True
                    ly.params = {"value": shown if not isinstance(p.get("value"), int) or p.get("suffix") else p["value"], "label": str(p.get("label") or "").upper(),
                                 "sub": str(p.get("sub") or ""), "colour": p.get("colour") or "yellow"}
                    if p.get("suffix") == "%":
                        ly.params["value"] = shown
                    plan.layers[:] = [x for x in plan.layers if not (x.kind == "kicker" and abs(x.start - ly.start) < 0.01 and abs(x.end - ly.end) < 0.01)]
                    dec.flags.append("dir:bignum")
                    dec.candidates.append({"kind": "kit_bignum", "score": 0.0, "reason": "direction: headline figure shown large", "accepted": True,
                                           "start": ly.start, "end": ly.end})
                    counts["bignum"] = counts.get("bignum", 0) + 1
                    last_at["kit_bignum"] = st
                    picked = picked or "kit_bignum"
                    break

        # ---- per sentence proposals (at most one more decoration per scene) ----------------------------------------------------------
        proposals: List[Tuple[int, str, float, float, Dict[str, Any], str, str, Optional[bool]]] = []
        for sent in A.sentences:
            a, b = _sent_window(A, sent, st, en)
            # 3 claim stamp
            m = _CLAIM.search(sent.text)
            if m and not sent.citation:      # a cited source already gets its own evidence card
                status = "unverified" if _UNVERIFIED.search(sent.text) else "disputed" if _DISPUTED.search(sent.text) else "claimed"
                ka = max(a, A.time_at(sent.span[0] + m.start()) - 0.2)
                proposals.append((1, "kit_stamp", ka, min(en, ka + 4.5), {"status": status, "pos": "upper-right"}, "stamp", f"'{m.group(0)}' marks a {status} statement", None))
            # 2 tactical map
            pl, co = _places(sent), _countries(sent)
            moving = bool(sent.motion) or bool(_STRIKE.search(sent.text))
            if len(pl) >= 2 or (pl and moving):
                p = _tac_params(sent, pl, co, False)
                if p:
                    proposals.append((2, "tac_map", a, max(b, a + 4.2), p, "tacmap", f"{len(pl)} named place(s) with movement/strike language" if moving else f"{len(pl)} named places", False))
            elif len(pl) == 1 and not has_footage:
                p1 = _tac_params(sent, pl, co, False)
                if p1:
                    proposals.append((4, "tac_map", a, max(b, a + 4.0), p1, "tacmap", "one named place and no footage: a location map", False))
            elif len(co) >= 2 and not pl:
                proposals.append((4, "tac_map", a, max(b, a + 4.0), _tac_params(sent, [], co, True), "tacmap", "country-to-country context", False))
            # 6 enumeration
            if _ORDINAL.search(sent.text) and len(_ORDINAL.findall(sent.text)) >= 2:
                segs = [s_.strip(" ,;") for s_ in re.split(r"\b(?:first|second|third|fourth)\b", sent.text, flags=re.IGNORECASE)[1:] if s_.strip(" ,;")]
                if 2 <= len(segs) <= 4:
                    chips = [{"title": f"{i + 1} · " + " ".join(sg.split()[:6]).rstrip(",."), "sub": "", "variant": ("red" if i == 0 else "dark")} for i, sg in enumerate(segs)]
                    proposals.append((3, "kit_chips", a, max(b, a + 4.0), {"chips": chips, "side": "right"}, "enum", "ordinal items", None))
            else:
                its = _items(sent.text)
                if its:
                    proposals.append((3, "kit_recap", a, max(b, a + 4.0), {"items": [i[:1].upper() + i[1:] for i in its]}, "enum", f"{len(its)} short list items", True))
            # 7 scale / sticker
            ms = _SCALE.search(sent.text)
            if ms and (cls in ("", "ai", "illustrative", "stock", "archive") or not has_footage):
                nraw = ms.group(1).lower()
                n_ = int(nraw) if nraw.isdigit() else _NUMWORD.get(nraw, 0)
                if 2 <= n_ <= 20:
                    proposals.append((3, "kit_scale", a, max(b, a + 3.6), {"n": n_, "label": f"{n_} {ms.group(2).upper()} · SINGLE FILE", "bar": "pipe"}, "scale", "stated count in single file", True))
            if not has_footage or cls in ("ai", "illustrative", "stock"):
                for rx, name, lab in _STICKERS:
                    mm = re.search(rx, sent.text, re.IGNORECASE)
                    if mm:
                        ka = max(a, A.time_at(sent.span[0] + mm.start()) - 0.3)
                        proposals.append((5, "kit_sticker", ka, max(min(b, ka + 3.2), ka + 2.4), {"name": name, "x": 0.68, "y": 0.46, "size": 260, "label": lab, "label_style": "tape"}, "sticker",
                                          f"'{mm.group(0)}' named over {'missing' if not has_footage else 'generic'} footage", True))
                        break
            # 4 emphasis tag
            idx = sent.index
            if (idx == 0 and topic_change and not first_scene) or _POINT.search(sent.text):
                h = _phrase(sent.text)
                if h:
                    proposals.append((6, "kit_tag", max(a, st + 0.3), min(b, max(a, st + 0.3) + 3.0), {"text": h, "pos": "top-left", "style": "hook"}, "tag", "the point of a section", False))

        proposals.sort(key=lambda x: x[0])
        # an existing plain map card of this scene (no territorial control layer, no snapshot) is upgraded in place to the tactical map
        tac = next((x for x in proposals if x[1] == "tac_map"), None)
        if tac is not None and picked is None:
            old = next((ly for ly in plan.layers if ly.kind == "map_card" and st - 0.01 <= ly.start < en
                        and not ((ly.params or {}).get("control") or (ly.params or {}).get("snapshot"))), None)
            if old is not None and last_kind != "tac_map":
                old.kind, old.params, old.dim = "tac_map", tac[4], False
                dec.flags.append("dir:tacmap")
                dec.candidates.append({"kind": "tac_map", "score": 0.0, "reason": "direction: " + tac[6] + " (replaces the plain map card)", "accepted": True,
                                       "start": old.start, "end": old.end})
                counts["tacmap"] = counts.get("tacmap", 0) + 1
                last_at["tac_map"] = st
                picked = "tac_map"
        proposals = [x for x in proposals if not (picked == "tac_map" and x[1] == "tac_map")]
        for pri, kind, a, b, params, rule, why, dim in proposals:
            if picked is not None and kind != "kit_stamp":
                break
            if kind == last_kind:
                continue
            if kind == "kit_tag" and st - last_at.get("kit_tag", -999) < 25.0:
                continue
            ign = ("shot_headline",) if kind in ("kit_stamp", "kit_sticker", "kit_scale", "kit_recap", "kit_chips", "kit_tag") else ()
            need = {"tac_map": 3.6, "kit_stamp": 1.4, "kit_tag": 2.0, "kit_recap": 3.0, "kit_chips": 3.0, "kit_sticker": 2.2, "kit_scale": 3.0}.get(kind, 2.0)
            slot = busy.free(a, min(b + (1.0 if kind in ("tac_map", "kit_recap", "kit_chips") else 0.0), en + 0.5), need, ignore=ign)
            if not slot:
                continue
            end = slot[1] if kind != "kit_stamp" else min(slot[1], slot[0] + 2.6)
            if kind == "tac_map" and _near_full([sp for sp in full_spans], slot[0], end):
                continue                                  # no two full-frame compositions back to back
            if kind == "kit_tag" and has_footage and cfg.get("layouts", True):
                kind, params, rule = "lay_inset", {"caption": params["text"], "caption_sub": "", "notes": []}, "inset"
            if add(kind, slot[0], end, params, dec, rule, why, en, dim=dim):
                last_at[kind] = st
                if kind == "tac_map":
                    full_spans.append((slot[0], end))
                picked = picked or kind
                if kind != "kit_stamp":
                    break

        if picked and picked != "kit_stamp":
            last_kind = picked
        first_scene = False

    plan.layers.extend(new_layers)
    looks = ("night", "blueprint", "table")                                   # maps differ from one to the next unless the caller pins a look
    for i, ly in enumerate(sorted((x for x in plan.layers if x.kind in ("tac_map", "tac_route")), key=lambda x: x.start)):
        if isinstance(ly.params, dict) and not ly.params.get("look") and ly.params.get("theme") != "political":
            ly.params["look"] = cfg.get("map_look") or looks[i % 3]
    if cfg.get("icons", True):
        _icon_scenes(plan, rows, cat, log_by_no, counts, maps_rebuilt=bool(cfg.get("map_build", True)))
    if cfg.get("map_build", True):     # one map that builds across each stretch without footage (map_build.py)
        from . import map_build as _mb

        _mb.build(plan, rows, cat, log_by_no, counts, gap_notes, tuple(FULL_KINDS - {"tac_map", "tac_route", "map_card"}))
    _speakers(plan, rows, cat, log_by_no, counts)
    _ratios_and_versus(plan, rows, cat, log_by_no, counts)
    if cfg.get("layouts", True):
        _extend_into_plate(plan, rows)
    for ov in [x for x in plan.layers if x.kind in ("kit_stamp",)]:       # a stamp lands on the footage or plate, never on top of a layout panel
        for lay in plan.layers:
            if lay.kind in LAYOUT_KINDS and lay.start < ov.start < lay.end and ov.start - lay.start >= 3.0:
                lay.end = fr(ov.start - 0.15)
    _no_empty_stretch(plan, rows, cat, log_by_no, counts, gap_notes)

    # ---- 9 badges (replace the equivalent old illustrative chip) ---------------------------------------------------------------------
    for r in rows:
        dec = log_by_no.get(str(r["_no"]))
        path = r.get("footage")
        if not path or dec is None or "no_footage" in dec.flags:
            continue
        cls = _meta_class(r.get("footage_meta") or {})
        if cls not in ("ai", "user", "archive", "illustrative", "stock"):
            continue
        st, en = r["_start"], r["_end"]
        chips = [ly for ly in plan.layers if ly.kind == "status_chip" and ly.start >= st - 0.01 and ly.end <= en + 0.6]
        if chips and not all(str((c.params or {}).get("text", "")).upper().startswith("ILLUSTRATIVE") for c in chips):
            continue                      # a disputed / recycled chip is a different statement: keep it, skip the badge
        plan.layers[:] = [ly for ly in plan.layers if ly not in chips]
        kind = {"ai": "ai", "user": "user", "archive": "archive", "illustrative": "illustrative", "stock": "illustrative"}[cls]
        a0, b0 = fr(st + 0.3), fr(max(st + 0.3, en - 0.2))
        cuts = sorted((x, y) for x, y in full_spans if y > a0 and x < b0)      # not drawn over an opaque map: it is split around it
        cur = a0
        for x, y in cuts + [(b0, b0)]:
            if x - cur >= 1.0:
                plan.layers.append(Layer("kit_badge", fr(cur), fr(x), {"kind": kind}, dim=False))
                counts["badges"] = counts.get("badges", 0) + 1
            cur = max(cur, y)

    # ---- 1 treatment ------------------------------------------------------------------------------------------------------------------
    hard = [x for x in ribbon_cuts]
    if cfg.get("split_shots", True):
        _split_long_shots(plan, meta_by_start, counts)
    _treat_shots(plan, meta_by_start, hard, full_spans, counts, film=bool(cfg.get("film_grade", True)))
    counts["empty_stretches"] = len(gap_notes)
    return {"counts": counts, "notes": gap_notes}
