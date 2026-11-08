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
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..render import Layer, Shot
from . import semantics as S

FPS = 25
SOFT = {"kicker", "status_chip", "kit_badge", "kit_grain", "bc_source"}          # never block a decoration
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
    for piece in re.split(r"(?<!\d),|,(?!\d{3}\b)|;|:| because | while | and | but | which | that | so ", sentence.strip()):   # '2,000' is one word
        w = piece.strip(" .\"'").split()
        if 3 <= len(w) <= 6 and w[-1].lower() not in _STOP_END:
            return " ".join(w)
    return ""


_STOP_END = {"of", "the", "a", "an", "to", "in", "on", "at", "with", "for", "by", "as", "from", "and", "or", "but", "that", "which", "is", "are", "was",
             "were", "its", "their", "his", "her", "this", "these", "those", "toward", "towards", "into", "onto", "over", "near", "after",
             "before", "against", "across", "through", "along", "behind", "under", "between", "around", "than", "more", "most", "very"}


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


def _fit_short_clips(plan: Any, counts: Dict[str, int], probe=_clip_seconds) -> None:
    """A clip shorter than its scene ends when the clip ends (YouTube cuts are 3.5 s by default): the rest of the scene is left for
    _broll_returns instead of a held or looped last frame."""
    lengths: Dict[str, Optional[float]] = {}
    for sh in plan.shots:
        if sh.path not in lengths:
            lengths[sh.path] = probe(sh.path)
        n = lengths[sh.path]
        if n is None:
            continue
        have = n - sh.seek - 0.05
        if have < (sh.end - sh.start) - 0.25:
            sh.end = fr(sh.start + max(min(1.0, sh.end - sh.start), have))
            counts["short_clips"] = counts.get("short_clips", 0) + 1


BROLL_MIN_S, BROLL_MAX_S, BROLL_USES = 1.2, 5.0, 2
CONTEXT_REPEAT_S = 90.0     # the wide 'Russia and Ukraine' context map at most once in this many seconds (render 033 showed it four times)
MAX_MAP_HOLD = 12.0 + 0.5     # map_build.MAX_MAP_S and a little: a sliver is never closed by holding a map past its limit


def _broll_returns(plan: Any, rows: Sequence[Dict[str, Any]], log_by_no: Dict[str, Any], meta_by_start: Dict[float, Dict[str, Any]],
                   counts: Dict[str, int], probe=_clip_seconds) -> None:
    """Where nothing is on screen (no footage, no full-frame card or map), cut back to the video's own footage: the clip of the nearest scene
    that is not the one just shown, at a moment of it not used yet, at most BROLL_USES returns per clip. Documentaries return to their own
    b-roll; an empty backdrop with a tag is what render 047 showed instead."""
    total = max((r["_end"] for r in rows), default=0.0)
    shots = sorted(plan.shots, key=lambda x: x.start)
    if not shots:
        return
    def open_gaps() -> List[Tuple[float, float]]:
        covered = sorted([(x.start, x.end) for x in plan.shots] + [(ly.start, ly.end) for ly in plan.layers if ly.kind in FULL_KINDS])
        out_: List[Tuple[float, float]] = []
        cur = 0.0
        for a, b in covered:
            if a - cur >= BROLL_MIN_S:
                out_.append((cur, a))
            cur = max(cur, b)
        if total - cur >= BROLL_MIN_S:
            out_.append((cur, total))
        return out_

    lengths: Dict[str, Optional[float]] = {}
    used: Dict[str, List[Tuple[float, float]]] = {}
    for x in shots:
        used.setdefault(x.path, []).append((x.seek, x.seek + (x.end - x.start)))
    returns: Dict[str, int] = {}
    owners = {x.path: x for x in shots}

    def seek_for(path: str, need: float) -> Optional[Tuple[float, float]]:
        if path not in lengths:
            lengths[path] = probe(path)
        n = lengths[path] or 0.0
        if n < BROLL_MIN_S:
            return None
        spans = sorted(used.get(path, []))
        cur_ = 0.0
        best = (0.0, min(need, n))                       # nothing unused left: the clip's start again (a return, not a new moment)
        for a, b in spans + [(n, n)]:
            if a - cur_ >= min(need, BROLL_MIN_S + 0.3):
                return cur_, min(need, a - cur_)
            cur_ = max(cur_, b)
        return best

    # first every clip at most BROLL_USES times; when the video has too few clips for that, a clip may return more often (a repeat beats
    # an empty backdrop), still never the one just shown
    for limit in (BROLL_USES, BROLL_USES * 4):
        for g0, g1 in open_gaps():
            t = g0
            while g1 - t >= BROLL_MIN_S - 1e-6:
                before = max((x for x in plan.shots if x.end <= t + 0.05), key=lambda x: x.end, default=None)
                after = min((x for x in plan.shots if x.start >= t), key=lambda x: x.start, default=None)
                avoid = {getattr(before, "path", None), getattr(after, "path", None)} if len(owners) > 2 else set()
                cands = sorted((x for x in owners.values() if x.path not in avoid and returns.get(x.path, 0) < limit),
                               key=lambda x: (min(abs(x.start - t), abs(x.end - t)), x.start))
                pick = None
                for c in cands:
                    sk = seek_for(c.path, min(BROLL_MAX_S, g1 - t))
                    if sk is not None and sk[1] >= BROLL_MIN_S - 1e-6:
                        pick = (c, sk)
                        break
                if pick is None:
                    break
                c, (seek, dur) = pick
                left = g1 - (t + dur)
                if 0 < left < BROLL_MIN_S and (lengths.get(c.path) or 0.0) - seek >= g1 - t:
                    dur = g1 - t                              # no sliver too short for another cut is left at the end of the gap
                a, b = fr(t), fr(min(g1, t + dur))
                plan.shots.append(Shot(c.path, a, b, round(seek, 3)))
                if b - a >= 2.0:                              # the clip belongs to another sentence: shown as illustration, never as this one's event
                    plan.layers.append(Layer("kit_badge", fr(a + 0.2), fr(b - 0.1), {"kind": "illustrative"}, dim=False))
                used.setdefault(c.path, []).append((seek, seek + (b - a)))
                returns[c.path] = returns.get(c.path, 0) + 1
                src = meta_by_start.get(fr(c.start)) or {}
                meta_by_start[a] = dict(src, reused=True)
                row = next((r for r in rows if r["_start"] - 0.01 <= a < r["_end"]), None)
                dec = log_by_no.get(str(row["_no"])) if row else None
                if dec is not None:
                    dec.flags.append("dir:broll_return")
                counts["broll_returns"] = counts.get("broll_returns", 0) + 1
                counts["broll_s"] = round(counts.get("broll_s", 0) + (b - a), 2)
                t = b
    plan.shots.sort(key=lambda x: x.start)
    _close_slivers(plan, total, lengths, probe)


def _close_slivers(plan: Any, total: float, lengths: Dict[str, Optional[float]], probe=_clip_seconds) -> None:
    """A gap too short for a cut of its own (under BROLL_MIN_S) is closed by holding what came before it a moment longer: the clip when it
    has the frames, else the full-frame card or map. A second of empty backdrop between two pieces reads as a glitch."""
    full = [ly for ly in plan.layers if ly.kind in FULL_KINDS]
    things = sorted([("shot", x.start, x.end, x) for x in plan.shots] + [("layer", ly.start, ly.end, ly) for ly in full], key=lambda z: z[1])
    cur, last = 0.0, None
    for kind, a, b, obj in things + [("end", total, total, None)]:
        gap = a - cur
        if last is not None and 0.04 < gap < BROLL_MIN_S:
            lk, lo = last
            if lk == "shot":
                if lo.path not in lengths:
                    lengths[lo.path] = probe(lo.path)
                if (lengths[lo.path] or 0.0) - lo.seek >= (a - lo.start):
                    lo.end = fr(a)
            elif lo.kind not in ("tac_map", "tac_route", "map_card") or a - lo.start <= MAX_MAP_HOLD:
                lo.end = fr(a)
            elif kind == "shot" and obj.seek >= gap:          # a map at its limit: the next clip starts a moment earlier instead
                obj.seek, obj.start = round(obj.seek - gap, 3), fr(cur)
        if b > cur:
            cur, last = b, (kind, obj)


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
        # 'Oleksandr Syrskyi, Ukraine's top commander, ordered a withdrawal' is a name, a role and a verb, not a list
        name_first = all(w[:1].isupper() for w in parts[0].split())
        if name_first and re.match(r"(?:[a-z]+ed|is|was|were|are|said|says|has|had|will|would|can|could)\b", parts[-1].split()[0], re.IGNORECASE):
            return []
        return parts
    return []


_ADVANCE_V = re.compile(r"\b(advanc\w*|push\w*|attack\w*|assault\w*|moved|marched|drove|rolled|crossed|stormed|captured|encircl\w*|broke through|poured)\b", re.IGNORECASE)
_STRIKE_V = re.compile(r"\b(struck|strikes?|hit|hits|launched|fired|shelled|bombed|targeted|missiles?|drones?|rockets?)\b", re.IGNORECASE)
_RETREAT_V = re.compile(r"\b(withdr\w*|retreat\w*|pulled back|fell back|evacuat\w*|abandon\w*)\b", re.IGNORECASE)
_REGION_WORD = re.compile(r"\s+(region|oblast|province)\b", re.IGNORECASE)


def _named_regions(text: str) -> List[Tuple[str, str]]:
    """Oblasts / regions the sentence names: 'Donetsk region', 'Kharkiv oblast', or an admin-1 area that is not also a town ('Crimea')."""
    try:
        from .maps_tactical import G, resolve_place
    except Exception:
        return []
    out: List[str] = []
    low = text.lower()
    for a in G.theatre_admin1():
        for nm in [a.name] + list(a.alts or []):
            nm = str(nm)
            if len(nm) < 4:
                continue
            m = re.search(r"\b" + re.escape(nm.lower()) + r"\b", low)
            if not m:
                continue
            city, _w = resolve_place(nm)
            if _REGION_WORD.match(text[m.end():]) or city is None:
                if a.name not in [x[0] for x in out]:
                    out.append((a.name, text[m.start():m.end()]))
            break
    return out[:3]


def _countries_in(A: Any) -> List[str]:
    out: List[str] = []
    for s_ in getattr(A, "sentences", []) or []:
        for c in _countries(s_):
            if c.name not in out:
                out.append(c.name)
    return out


def _narrate_map(p: Dict[str, Any], text: str, A: Any, t0: float, countries: Sequence[str] = ()) -> Dict[str, Any]:
    """The owner (2026-11-07): maps should follow the narration. Every element appears when its words are spoken (times are seconds from the
    card's start t0): each pin lands as its place is named, a country colours in and a region is outlined as it is named, the movement or
    strike draws on its verb, and the camera opens wide then pushes in on each place as it is named (close-up on one town, or the route
    when something moves). Never adds a place, side or event the sentence does not name."""
    if not p:
        return p
    p = dict(p)
    low = text.lower()

    def when(name: str) -> Optional[float]:
        i = low.find(str(name).lower())
        return round(max(0.3, A.time_at(i) - t0), 2) if i >= 0 else None

    named: List[Tuple[float, str]] = []
    places = []
    for pl in p.get("places") or []:
        spec = dict(pl) if isinstance(pl, dict) else {"name": str(pl)}
        w = when(spec.get("name") or "")
        if w is not None:
            spec["start"] = w
            named.append((w, spec["name"]))
        places.append(spec)
    p["places"] = places
    if countries and p.get("theme") == "political" and not places:
        # a sentence about countries only: frame the countries named and colour each in, with its flag, as it is spoken
        from .maps_tactical import G, country_roles

        roles = country_roles(list(countries))
        fills, steps, times = [], [], []
        for c in countries:
            w, f = when(c), G.find_country(c)
            if w is None or f is None:
                continue
            fills.append({"iso3": f.iso, "role": roles.get(f.iso, "neutral"), "start": max(0.4, w)})
            steps.append({"country": c})
            times.append(w)
        if fills:
            p["fills"] = fills
            p.pop("frame", None)
            p["focus"] = [steps]                                       # one frame that takes in every country named
            return p
    if countries and p.get("theme") != "political":
        from .maps_tactical import G, country_roles

        roles = country_roles(list(countries))           # {ISO3: role}: Russia red, Ukraine blue, Belarus brown, the rest in order
        fills = []
        for c in countries:
            w = when(c)
            f = G.find_country(c)
            if w is not None and f is not None:
                fills.append({"iso3": f.iso, "role": roles.get(f.iso, "neutral"), "start": max(0.4, w)})
        if fills:
            p["fills"] = fills
    regs = []
    for rn, said in _named_regions(text):
        w = when(said)                                        # 'Donetsk' as spoken, though the data spells it Donets'k
        regs.append({"name": rn, "label": said, "colour": "amber", "start": w if w is not None else 0.6})
    if regs:
        p["regions"] = regs
    verb = _STRIKE_V.search(text) or _ADVANCE_V.search(text) or _RETREAT_V.search(text)
    if not p.get("routes") and _STRIKE_V.search(text) and len(places) >= 2:
        m = re.search(r"\bfrom\s+(?:the\s+)?([A-Z][\w'-]+(?:\s[A-Z][\w'-]+)?)", text)
        if m:
            src = next((x["name"] for x in places if str(x.get("name", "")).lower() == m.group(1).lower()), None)
            dst = next((x["name"] for x in places if x.get("name") != src), None)
            if src and dst:
                p["routes"] = [{"from": src, "to": dst}]
    for r in p.get("routes") or []:
        if verb is not None:
            r["start"] = round(max(0.4, A.time_at(verb.start()) - t0), 2)
            r["length"] = 1.4
        r["style"] = "strike" if _STRIKE_V.search(text) and not _ADVANCE_V.search(text) else "retreat" if _RETREAT_V.search(text) else "advance"
        side = "red" if re.search(r"\bruss\w*|\bmoscow\b|\bkremlin\b", low) else "blue" if re.search(r"\bukrain\w*|\bkyiv\b", low) else ""
        r["colour"] = {"strike": "amber"}.get(r["style"], side or "white")
        if r["style"] == "strike":
            p.setdefault("glyphs", [])
            p["glyphs"] = [g for g in p["glyphs"] if not (g.get("kind") == "ring" and g.get("place") == r.get("to"))]
    named.sort()
    if p.get("routes"):
        r0 = p["routes"][0]
        p["focus"] = [[r0["from"]], [r0["from"], r0["to"]]]          # start on the origin, widen to take in the movement as it is spoken
        p["focus_times"] = [0.0, max(0.5, float(r0.get("start", 1.0)) - 0.4)]
    elif len(named) == 1:
        nm = named[0][1]
        p["focus"] = [[nm], [nm]]                                     # wide regional view first, then push in on the town as it is named
        p["focus_times"] = [0.0, max(0.6, named[0][0] - 0.2)]
        p["close_steps"] = [False, True]
    elif 2 <= len(named) <= 4:
        p["focus"] = [[n for _w, n in named]] + [[n] for _w, n in named[1:]]
        p["focus_times"] = [0.0] + [max(0.6, w - 0.2) for w, _n in named[1:]]
        p["close_steps"] = [False] + [True] * (len(named) - 1)      # each further place named: the camera moves in on it
    return p


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


_AIR = re.compile(r"\b(drones?|missiles?|rockets?|air|airspace|radar|jets?|aircraft|sky|skies|detect\w*|intercept\w*|air defen[cs]e|warplanes?|bombers?|satellites?)\b", re.IGNORECASE)
_DOC = re.compile(r"\b(report\w*|document\w*|said|says|announced|according|officials?|claimed|intelligence|secret\w*|plan|plans|order\w*|decision|"
                  r"decided|agreement|treaty|deal|memo|letter|statement|ministry|government)\b", re.IGNORECASE)
_STOP = {"the", "a", "an", "of", "to", "in", "on", "at", "and", "or", "but", "with", "for", "by", "as", "from", "that", "which", "was", "were",
         "is", "are", "be", "been", "had", "has", "have", "it", "its", "their", "his", "her", "this", "these", "those", "they", "there", "then",
         "would", "could", "will", "into", "after", "before", "about", "every", "many", "some", "what", "who", "when", "where", "more", "most"}
MOTION_MAX_S = 6.5
_MONTHS = r"(January|February|March|April|May|June|July|August|September|October|November|December)"
_DATE = re.compile(r"\b(?:(?:early|mid|late)[- ])?" + _MONTHS + r"(?:\s+\d{1,2})?(?:,)?\s+(?:19|20)\d{2}\b|\b(?:in|by|since|until)\s+((?:19|20)\d{2})\b", re.IGNORECASE)


def _date_of(text: str) -> str:
    """'February 2022', 'late March 2023', or a year after in/by/since ('2014'), exactly as the narration says it; else ''."""
    m = _DATE.search(text or "")
    if not m:
        return ""
    return m.group(2) if m.group(2) else m.group(0).strip(" ,")


def _after_date(text: str, date: str) -> str:
    """The narration's words after the date ('In February 2022, Russian columns advanced ...' -> 'Russian columns advanced ...'), 3-6 words;
    the words before it when the date ends the sentence; never the date again."""
    i = text.lower().find(date.lower())
    rest = text[i + len(date):] if i >= 0 else text
    h = _phrase_or_lead(rest.strip(" ,;:.-"))
    if not h and i > 0:
        h = _phrase_or_lead(re.sub(r"\b(in|by|since|until|on)\s*$", "", text[:i].strip(" ,"), flags=re.IGNORECASE))
    return "" if date.lower() in h.lower() else h


def _quote_of(sent: Any) -> Optional[Dict[str, Any]]:
    """The quoted words and their speaker when the sentence quotes someone (never a paraphrase shown as a quote)."""
    q = getattr(sent, "quote", None)
    if q is not None and getattr(q, "text", "").strip():
        return {"quote": q.text.strip(), "speaker": getattr(q, "speaker", "") or ""}
    m = re.search(r"[\"\u201c]([^\"\u201d]{6,220})[\"\u201d]", sent.text or "")
    return {"quote": m.group(1).strip(), "speaker": ""} if m else None          # one motion graphic holds at most this long; a longer empty stretch gets the next one


def _key_words(text: str, n: int = 2) -> List[str]:
    ws = [w.strip(".,;:!?'\"()") for w in text.split()]
    ws = [w for w in ws if len(w) >= 5 and w.lower() not in _STOP]
    return sorted(ws, key=len, reverse=True)[:n]


def _motion_options(sent: Any, h: str) -> List[Tuple[str, Dict[str, Any]]]:
    """Full-frame motion graphics (cards_motion) the sentence supports; the words are always the narration's own."""
    text = sent.text.strip()
    out: List[Tuple[str, Dict[str, Any]]] = []
    if _AIR.search(text):
        out.append(("kit_radar", {"label": h}))
    if len(text) <= 220:      # any sentence can be a page in the file; one that names a report, plan or decision most of all
        out.append(("kit_dossier", {"title": h, "body": text if text.upper() != h.upper() else "", "mark": _key_words(text, 1)}))
    items = _items(text)
    if not items:
        names = []
        for e in sent.entities:
            if e.name.lower() not in [x.lower() for x in names]:
                names.append(e.name)
        items = names if 2 <= len(names) <= 4 else []
    if items:
        out.append(("kit_keywords", {"items": [i[:1].upper() + i[1:] for i in items], "title": h if len(h.split()) <= 6 else ""}))
    q = _quote_of(sent)
    if q:
        out.insert(0, ("kit_quote", q))
    dt = _date_of(text)
    if dt:
        out.insert(0, ("kit_datecard", {"date": dt, "sub": _after_date(text, dt)}))
    out.append(("kit_kinetic", {"text": h, "key": _key_words(h, 2)}))
    if not _DOC.search(text):                       # ties go to the first: the file page leads only for a report, plan or decision
        out.sort(key=lambda o: o[0] == "kit_dossier")
    return out


def _no_empty_stretch(plan: Any, rows: Sequence[Dict[str, Any]], cat: Any, log_by_no: Dict[str, Any], counts: Dict[str, int], notes: List[str],
                      motion: bool = True) -> None:
    """Rule 11: wherever no footage is on screen, the plain backdrop is never what the viewer sees. Since 2026-11-07 (the owner: "we can use
    graphics instead of that") every free stretch of the plate is covered by full-frame motion graphics (kinetic type, dossier, radar,
    numbered keywords: cards_motion) made from the sentence spoken there, the least used kind first. motion=False keeps the old small tag.
    Where nothing truthful exists the stretch is logged, never filled with invention."""
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
    used: Dict[str, int] = {}
    last = ""
    flip = 0
    need = 2.0 if motion else 3.6
    for g0, g1 in plate:
        t = g0
        while g1 - t >= need:
            slot = busy.free(t, g1, need, margin=0.0, ignore=("shot_headline",))
            if slot is None:
                break
            w0 = slot[0]
            row = next((r for r in rows if r["_start"] - 0.01 <= w0 < r["_end"]), None)
            if row is None:                       # the plate after the last scene: the scene before it speaks there
                row = next((r for r in reversed(rows) if r["_start"] <= w0 + 0.01), None)
            h, sent = "", None
            if row:
                A2 = S.analyze_scene(str(row.get("text") or ""), cat, row.get("words"), row["_start"], row["_end"])
                sent = next((x for x in A2.sentences if A2.time_at(x.span[0]) - 0.2 <= w0 + 0.6 <= A2.end_time_of(x.span) + 0.6), A2.sentences[-1] if A2.sentences else None)
                h = _phrase_or_lead(sent.text) if sent is not None else ""
            dec = log_by_no.get(str(row["_no"])) if row else None
            if not h or dec is None:
                notes.append(f"nothing truthful to show at {w0:.1f}s")
                if dec is not None:
                    dec.flags.append("dir:empty_stretch")
                t = w0 + need
                continue
            if motion:
                room = slot[1] - w0
                span = room if room <= MOTION_MAX_S + 2.5 else MOTION_MAX_S      # never leave a sliver too short for the next graphic
                opts = _motion_options(sent, h)
                opts.sort(key=lambda o: (o[0] == last, used.get(o[0], 0)))
                kind, params = opts[0]
                params = dict(params, seed=int(row["_no"]) if str(row["_no"]).isdigit() else 0)
                ly = Layer(kind, fr(w0), fr(w0 + span), params, dim=False)
                used[kind] = used.get(kind, 0) + 1
                last = kind
                why, rule = f"no footage here: {kind} from the narration", "motion_fill"
            else:
                a = fr(w0 + 0.6)
                ly = Layer("kit_tag", a, fr(a + 3.2), {"text": h, "pos": "top-left" if flip % 2 == 0 else "lower-left", "style": "hook"}, dim=False)
                flip += 1
                why, rule = "no footage here, the narration's own words as a tag", "fallback_tags"
            plan.layers.append(ly)
            busy.add(ly.start, ly.end, ly.kind)
            dec.flags.append("dir:" + ("motion_fill" if motion else "fallback_tag"))
            dec.candidates.append({"kind": ly.kind, "score": 0.0, "reason": "direction: " + why, "accepted": True, "start": ly.start, "end": ly.end})
            counts[rule] = counts.get(rule, 0) + 1
            t = ly.end



# ------------------------------------------------------------------------------------------------ CSV graphic column ------------------
# The owner (2026-11-07): "we can add graphics through csv too". A scenes CSV may name the graphic for a scene in its `graphic` column.
# The graphic is built from that scene's own narration (never from words the CSV adds), placed first, and wins over what the planner
# put in the same seconds. When the sentence cannot support it (no number for `number`, no place for `map`), the scene keeps the
# automatic choice and the plan log says why.
CSV_GRAPHIC = {"map": "map", "number": "number", "stat": "number", "figure": "number", "compare": "compare", "versus": "compare",
               "equipment": "equipment", "weapon": "equipment", "speaker": "speaker", "person": "speaker", "quote": "quote",
               "timeline": "timeline", "dates": "timeline", "date": "date", "list": "list", "icons": "icons", "kinetic": "kinetic",
               "text": "kinetic", "dossier": "dossier", "document": "dossier", "radar": "radar", "keywords": "keywords", "title": "title",
               "chapter": "chapter", "bignum": "number", "big number": "number", "institution": "institution", "organisation": "institution",
               "organization": "institution", "supply": "supply", "supply chain": "supply", "logistics": "supply", "sticker": "sticker",
               "steps": "steps", "chips": "steps", "route": "route", "situation map": "route", "claim": "claim", "source": "source",
               "evidence": "source", "ratio": "ratio", "scale": "scale", "flag": "flag", "stamp": "stamp", "speaker card": "speaker_card",
               "name": "speaker_card", "lower third": "speaker_card", "auto": "", "none": "", "": "",
               "chart": "chart", "bar chart": "chart", "bars": "chart", "percent": "chart", "percentage": "chart", "line chart": "chart",
               "graph": "chart", "donut": "chart", "article": "article", "news": "article", "news article": "article", "screenshot": "article",
               "report page": "article", "flyover": "flyover", "fly-over": "flyover", "drone": "flyover", "missile": "flyover", "aircraft": "flyover",
               "satellite": "satellite", "before after": "satellite", "before/after": "satellite", "satellite image": "satellite",
               "front line": "map", "frontline": "map", "capture": "map", "advance": "map", "retreat": "map", "territory": "map",
               "locator": "locator", "inset map": "locator", "minimap": "locator", "mini map": "locator",
               "document page": "article", "strategic": "map", "strategic site": "map",
               "label": "bc_label", "keyword": "bc_label", "keyword label": "bc_label", "caption": "bc_caption", "quote box": "bc_caption",
               "caption box": "bc_caption", "big word": "bc_bigword", "bigword": "bc_bigword", "big figure": "bc_bigword"}
_PLANNER_KINDS = {"number": ("number", "compare"), "compare": ("compare", "split"), "equipment": ("equipment", "split"), "speaker": ("figure",),
                  "timeline": ("timeline",), "institution": ("institution",), "source": ("evidence",),
                  "claim": ("evidence", "figure")}   # a leader's claim with no outlet line: the claimant's portrait card carries it
CSV_MAX_S, CSV_MIN_S = 8.0, 3.0
TEXT_CARD_KINDS = {"kit_title", "kit_datecard", "kit_kinetic", "kit_keywords"}
TEXT_CARD_MAX_S = 4.5


def _planner_layer(r: Dict[str, Any], cfg: Dict[str, Any], cat: Any, want: Sequence[str]) -> Optional[Layer]:
    """The planner's own card for this scene, of the wanted kind, regardless of spacing (the CSV asked for it)."""
    from . import planner as P

    A = S.analyze_scene(str(r.get("text") or ""), cat, r.get("words"), r["_start"], r["_end"])
    ctx = P._Ctx(scene=r, A=A, cfg=cfg, catalog=cat, assets={}, start=r["_start"], end=r["_end"], has_words=bool(r.get("words")),
                 seen_equipment={}, footage_verified=False)
    cands = [c for c in P.build_candidates(ctx) if c.code == "" and c.kind in want]
    if not cands:
        return None
    c = sorted(cands, key=lambda c: (want.index(c.kind), -c.score))[0]
    params = dict(c.params)
    params.pop("image_record", None)
    return Layer(P.LAYER_KIND[c.kind], c.start, c.end, params, dim=c.kind not in P.NO_DIM)


_STILL_EXT = (".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff")


def _still_of(r: Dict[str, Any]) -> str:
    """The row's own picture: a still attached as footage (the renderer turns it into '<image>.war.mp4'; the card wants the image)."""
    f = str(r.get("footage") or "")
    if f.lower().endswith(".war.mp4"):                       # still_to_clip names it <stem>.war.mp4
        base = f[:-len(".war.mp4")]
        for ext in _STILL_EXT + tuple(e.upper() for e in _STILL_EXT):
            if Path(base + ext).is_file():
                return base + ext
    if f.lower().endswith(_STILL_EXT):
        return f
    lp = str((r.get("footage_meta") or {}).get("local_path") or "")
    return lp if lp.lower().endswith(_STILL_EXT) else ""


def _csv_layer(kind: str, r: Dict[str, Any], cfg: Dict[str, Any], cat: Any) -> Tuple[Optional[Layer], str]:
    text = str(r.get("text") or "")
    A = S.analyze_scene(text, cat, r.get("words"), r["_start"], r["_end"])
    sents = A.sentences or []
    seed = int(r["_no"]) if str(r["_no"]).isdigit() else 0
    h = _phrase_or_lead(sents[0].text) if sents else ""
    full = lambda k, p: Layer(k, r["_start"], r["_end"], dict(p, seed=seed), dim=(k in DIM))   # noqa: E731
    if kind in _PLANNER_KINDS:
        ly = _planner_layer(r, cfg, cat, _PLANNER_KINDS[kind])
        if ly is None and kind == "number":       # a figure the parser could not pair with its referent: labelled with the narration's next words
            from . import planner as P

            for sent in sents:
                ctx = P._Ctx(scene=r, A=A, cfg=cfg, catalog=cat, assets={}, start=r["_start"], end=r["_end"], has_words=bool(r.get("words")),
                             seen_equipment={}, footage_verified=False)
                c = P._loose_number(ctx, sent, sent.numbers)
                if c is not None:
                    ly = Layer("stat_number", c.start, c.end, dict(c.params), dim=True)
                    break
        if ly is not None:
            return ly, ""
        fallback = {"compare": "compare_kit", "claim": "stamp", "route": "map", "number": "number_raw", "source": "source_doc"}.get(kind)
        if fallback is None:
            return None, f"the narration has nothing for a {kind} card"
        kind = fallback          # versus/ratio card, CLAIMED stamp, or the places on the tactical map
    if kind == "route":
        kind = "map"                              # the tactical map draws the movement the sentence states (from a country too)
    if kind == "number_raw":                      # the script states a figure: it is shown as the script says it, labelled with its own words
        for sent in sents:
            nums = [n for n in sent.numbers if not n.is_year]
            if len(nums) >= 2 and re.search(r"\bfrom\b.*\bto\b", sent.text[nums[0].span[0] - 12:nums[1].span[1]], re.IGNORECASE):
                def lab_(n):
                    w = re.findall(r"[\w'’-]+", sent.text[n.span[1]:n.span[1] + 40])[:2]
                    return " ".join(w) if w and w[0].lower() in ("in", "by", "on", "at", "during", "per", "a") else (n.unit or " ".join(w))
                return full("kit_versus", {"a": nums[0].raw, "a_label": lab_(nums[0]), "b": nums[1].raw, "b_label": lab_(nums[1]), "title": ""}), ""
            for n in sent.numbers:
                if n.is_year:
                    continue
                after = re.findall(r"[\w'’-]+", sent.text[n.span[1]:n.span[1] + 60])[:4]
                lab = (n.unit if n.unit and n.unit != "%" else " ".join(after)).strip()
                return full("kit_bignum", {"value": n.raw, "label": lab.upper(), "sub": n.period or "", "colour": "yellow", "count": False}), ""
        return None, "no figure in the narration"
    if kind == "source_doc":                      # a named report / study / outlet: its document page with what it found highlighted
        m = re.search(r"\b(?:report|study|assessment|analysis|investigation|survey)\s+(?:by|from|of)\s+(?:the\s+)?([A-Z][\w'’&.-]*(?:\s+(?:for|of|the|and|on|[A-Z][\w'’&.-]*))*?)"
                      r"(?=\s+(?:found|said|says|showed|shows|concluded|estimated|reported|warned)\b|[,.])", text) or \
            re.search(r"\baccording to\s+(?:the\s+)?([A-Z][\w'’&.-]*(?:\s+[A-Z][\w'’&.-]*){0,5})", text)
        if m:
            hl = re.split(r"\b(?:found|said|says|showed|shows|concluded|estimated|reported|warned)\b\s*(?:that\s+)?", text, maxsplit=1)
            hl_ = (hl[1] if len(hl) > 1 else text).strip().rstrip(".")
            return full("lay_document", {"outlet": m.group(1).strip(), "text": text, "highlight": hl_, "quote": " ".join(hl_.split()[:12])}), ""
        return None, "no named report or outlet"
    if kind in ("bc_label", "bc_caption", "bc_bigword"):     # broadcast overlays the CSV asks for, from the sentence's own words
        from . import broadcast as _bc

        for sent in sents:
            if kind == "bc_label":
                lab = _bc._label_of(sent, text)
                if lab:
                    a = max(r["_start"], A.time_at(lab[1]) - 0.1)
                    return Layer("bc_label", a, min(r["_end"] + 0.4, a + 2.8), {"text": lab[0], "sub": lab[2]}, dim=False), ""
            elif kind == "bc_caption":
                cap = _bc._caption_of(sent, text) or (" ".join(sent.text.split()[:14]) if sent.text else None)
                if cap:
                    a = A.time_at(sent.span[0]) + 0.2
                    return Layer("bc_caption", a, min(r["_end"] + 0.3, a + min(5.0, max(2.6, len(cap.split()) * 0.36))),
                                 {"text": cap.rstrip("."), "quote": sent.quote is not None}, dim=False), ""
            else:
                bw = _bc._bigword_of(sent)
                if bw:
                    a = max(r["_start"], A.time_at(bw[2]) - 0.15)
                    return Layer("bc_bigword", a, min(r["_end"] + 0.3, a + 2.6), {"text": bw[0], "sub": bw[1], "accent": "yellow"}, dim=False), ""
        if kind == "bc_bigword":
            h2 = _phrase_or_lead(sents[0].text) if sents else ""
            if h2:
                return Layer("bc_bigword", r["_start"] + 0.2, min(r["_end"], r["_start"] + 2.8), {"text": " ".join(h2.split()[:3]), "accent": "yellow"}, dim=False), ""
        return None, f"the narration has nothing for a {kind[3:]}"
    if kind == "locator":
        for sent in sents:
            from . import maps_tactical as _mt

            pts = [p_ for p_ in (_mt.resolve_place(e.name)[0] for e in _places(sent)) if p_][:2]
            if pts:
                lat0, lon0 = sum(p_["lat"] for p_ in pts) / len(pts), sum(p_["lon"] for p_ in pts) / len(pts)
                return Layer("map_inset", r["_start"], min(r["_end"], r["_start"] + 5.0),
                             {"pins": [{"lat": p_["lat"], "lon": p_["lon"], "label": p_["name"], "start": 0.4 + 0.3 * i} for i, p_ in enumerate(pts)],
                              "pos": "tr", "width": 320, "frame": [lon0 - 5.5, lat0 - 3.0, lon0 + 5.5, lat0 + 3.0]}, dim=False), ""
        return None, "no place named"
    if kind == "map":
        for sent in sents:
            pl, co = _places(sent), _countries(sent)
            p = _tac_params(sent, pl, co, False) if pl else (_tac_params(sent, [], co, True) if co else {})
            if p:
                return Layer("tac_map", r["_start"], r["_end"], _narrate_map(p, text, A, r["_start"], _countries_in(A)), dim=False), ""
        return None, "no place or country named"
    if kind in ("chart", "article", "flyover", "satellite"):
        from . import graphics_lib as GL

        if kind == "chart":
            for sent in sents:
                c = GL.chart_of(sent.text, sent.numbers)
                if c:
                    return full("kit_chart", c), ""
            return None, "fewer than three labelled figures (or two dated percentages) in the narration"
        if kind == "article":
            for sent in sents:
                a = GL.article_of(sent)
                if a:
                    return full("lay_document", dict(a, image=_still_of(r) or None)), ""
            return full("lay_document", {"text": text, "highlight": h, "quote": h, "image": _still_of(r) or None}), ""
        if kind == "flyover":
            f = GL.flyover_of(text) or next(({"name": n, "label": m.group(0).upper(), "count": 1} for rx, n in GL._FLY_NAMES
                                             for m in [re.search(rx, text, re.IGNORECASE)] if m), None)
            if f:
                return Layer("kit_flyover", r["_start"], min(r["_end"], r["_start"] + 4.0), f, dim=False), ""
            return None, "no drone, missile or aircraft named"
        imgs = [x.strip() for x in str(r.get("images") or "").split("|") if x.strip()]
        if not imgs and _still_of(r):
            imgs = [_still_of(r)]
        d0 = _date_of(text)
        place = next((e.name for sent in sents for e in _places(sent)), "")
        if len(imgs) >= 2:
            return full("lay_satellite", {"before": imgs[0], "after": imgs[1], "caption": h, "after_date": d0 or "AFTER", "place": place}), ""
        if len(imgs) == 1:
            return full("lay_satellite", {"before": imgs[0], "after": imgs[0], "single": True, "caption": h, "after_date": d0 or "", "place": place}), ""
        return None, "a satellite card needs an image: the row's images column (before|after, or one file) or a local still"
    if kind == "quote":
        for sent in sents:
            q = _quote_of(sent)
            if q:
                return full("kit_quote", q), ""
        return None, "no quoted words in the narration"
    if kind == "date":
        d = _date_of(text)
        return (full("kit_datecard", {"date": d, "sub": _after_date(text, d)}), "") if d else (None, "no date in the narration")
    if kind in ("compare_kit", "ratio"):
        from .map_build import ratio_of, versus_of

        for sent in sents:
            vs = versus_of(sent.text) if kind == "compare_kit" else None
            if vs:
                return full("kit_versus", dict(vs, title="")), ""
            rt = ratio_of(sent.text)
            if rt:
                return full("kit_bignum", {"value": rt["value"], "label": rt["label"].upper(), "sub": rt["sub"], "colour": "yellow", "count": False}), ""
        if kind == "compare_kit":
            for sent in sents:
                nums = [n for n in sent.numbers if not n.is_year]
                if len(nums) >= 2:
                    def lab(n):
                        w = re.findall(r"[\w'’-]+", sent.text[n.span[1]:n.span[1] + 50])[:3]
                        return n.unit if n.unit and n.unit != "%" else " ".join(w)
                    return full("kit_versus", {"a": nums[0].raw, "a_label": lab(nums[0]), "b": nums[1].raw, "b_label": lab(nums[1]), "title": ""}), ""
        return None, "no comparison or 'N in M' ratio stated"
    if kind == "scale":
        ms = _SCALE.search(text)
        if ms:
            nraw = ms.group(1).lower()
            n_ = int(nraw) if nraw.isdigit() else _NUMWORD.get(nraw, 0)
            if 2 <= n_ <= 20:
                return full("kit_scale", {"n": n_, "label": f"{n_} {ms.group(2).upper()} · SINGLE FILE", "bar": "pipe"}), ""
        return None, "no 'N soldiers in single file' count"
    if kind == "flag":
        from .cards_kit import FLAGS
        from .maps_tactical import G

        for sent in sents:
            for c in _countries(sent):
                f = G.find_country(c.name)
                if f is not None and f.iso in FLAGS:
                    return Layer("kit_flag", r["_start"], r["_start"] + 3.0, {"iso3": f.iso}, dim=False), ""
        return None, "no country with a flag in the set"
    if kind == "stamp":
        m = _CLAIM.search(text)
        if m:
            status = "unverified" if _UNVERIFIED.search(text) else "disputed" if _DISPUTED.search(text) else "claimed"
            return Layer("kit_stamp", r["_start"], min(r["_end"], r["_start"] + 4.5), {"status": status, "pos": "upper-right"}, dim=False), ""
        return None, "no claimed / unverified / denied wording"
    if kind == "speaker_card":
        from .map_build import speaker_of

        for sent in sents:
            spk = speaker_of(sent.text)
            if not spk:
                m = re.match(r"\W*([A-Z][\w'’-]+(?:\s+[A-Z][\w'’-]+){1,3}),\s+([^,.;]{3,60}),", sent.text)
                fig = getattr(sent, "intro_figure", None)
                if m:
                    spk = (m.group(1), m.group(2).strip())
                elif fig:
                    spk = (fig[0].name, str(fig[1]))
            if spk:
                return Layer("kit_speaker", r["_start"], min(r["_end"], r["_start"] + 4.0), {"name": spk[0], "role": spk[1]}, dim=False), ""
        return None, "no named person with a role"
    if kind == "chapter":
        from .map_build import chapter_of

        ch = chapter_of(sents[0].text) if sents else None
        if ch:
            return Layer("kit_chapter", r["_start"], r["_start"] + 3.6, {"label": ch[0], "sub": ch[1]}, dim=False), ""
        kind = "title"                            # not written as 'Chapter N': the cinematic title card instead
    if kind == "supply":
        nodes = _logistics_nodes(text)
        return (full("lay_logistics", {"title": "Supply chain", "nodes": nodes, "links": []}), "") if len(nodes) >= 2 else \
            (None, "fewer than two supply links named (fuel, rail, trucks, depots, ammunition ...)")
    if kind == "sticker":
        for rx, name, lab in _STICKERS:
            mm = re.search(rx, text, re.IGNORECASE)
            if mm:
                return Layer("kit_sticker", r["_start"], min(r["_end"], r["_start"] + 4.0),
                             {"name": name, "x": 0.68, "y": 0.46, "size": 260, "label": lab, "label_style": "tape"}, dim=True), ""
        return None, "nothing the sticker set can draw"
    if kind == "steps":
        for sent in sents:
            if len(_ORDINAL.findall(sent.text)) >= 2:
                segs = [s_.strip(" ,;") for s_ in re.split(r"\b(?:first|second|third|fourth)\b", sent.text, flags=re.IGNORECASE)[1:] if s_.strip(" ,;")]
                if 2 <= len(segs) <= 4:
                    chips = [{"title": f"{i + 1} · " + " ".join(sg.split()[:6]).rstrip(",."), "sub": "", "variant": ("red" if i == 0 else "dark")}
                             for i, sg in enumerate(segs)]
                    return Layer("kit_chips", r["_start"], r["_end"], {"chips": chips, "side": "right"}, dim=False), ""
        its = _items(text)
        if its:
            chips = [{"title": f"{i + 1} · {it}", "sub": "", "variant": ("red" if i == 0 else "dark")} for i, it in enumerate(its[:4])]
            return Layer("kit_chips", r["_start"], r["_end"], {"chips": chips, "side": "right"}, dim=False), ""
        return None, "no first/second/third steps or listed items"
    if kind == "title":
        from .map_build import chapter_of

        ch = chapter_of(sents[0].text) if sents else None
        return (full("kit_title", {"text": ch[1] or ch[0], "sub": ch[0] if ch[1] else ""} if ch else {"text": h}), "") if (ch or h) else (None, "no words")
    if kind == "list":
        its = _items(text)
        if its:
            return full("kit_recap", {"items": [i[:1].upper() + i[1:] for i in its]}), ""
        kind = "keywords"
    if kind == "icons":
        found: List[Tuple[int, str, str]] = []
        for rx, name, _lab in _STICKERS:
            mm = re.search(rx, text, re.IGNORECASE)
            if mm and name not in [f[1] for f in found]:
                found.append((mm.start(), name, mm.group(0)))
        found.sort()
        if len(found) >= 2:
            return full("kit_icons", {"icons": [{"name": n, "label": w, "start": 0.3 + 0.5 * i} for i, (_p, n, w) in enumerate(found[:4])],
                                      "link": "", "title": _phrase(text)}), ""
        if found:
            return Layer("kit_sticker", r["_start"], min(r["_end"], r["_start"] + 4.0),
                         {"name": found[0][1], "x": 0.68, "y": 0.46, "size": 260, "label": found[0][2].upper(), "label_style": "tape"}, dim=True), ""
        return None, "nothing the icon set can draw"
    if kind in ("kinetic", "dossier", "radar", "keywords"):
        if not sents or not h:
            return None, "no words"
        k = "kit_" + kind
        if k == "kit_radar":
            return full(k, {"label": h}), ""
        opts = dict(_motion_options(sents[0], h))
        if k in opts:
            return full(k, opts[k]), ""
        if k == "kit_keywords":
            kw = _key_words(text, 3)
            return (full(k, {"items": [w[:1].upper() + w[1:] for w in kw], "title": h if len(h.split()) <= 6 else ""}), "") if len(kw) >= 2 else (None, "no key words")
        return None, "no words"
    return None, f"unknown graphic '{kind}'"


def _csv_wins(plan: Any, counts: Dict[str, int]) -> None:
    """After every other rule: a graphic the CSV asked for keeps its seconds. Another card that overlaps it (an icon explainer, a map piece,
    a layout stretched into the gap) is trimmed to end before it, or dropped when too little of it is left."""
    csv = [(ly.start, ly.end) for ly in plan.layers if (ly.params or {}).get("csv_graphic")]
    if not csv:
        return
    csv_full = [(ly.start, ly.end) for ly in plan.layers if (ly.params or {}).get("csv_graphic") and ly.kind in FULL_KINDS
                and not (ly.params or {}).get("over")]
    keep = []
    for ly in plan.layers:
        if (ly.params or {}).get("csv_graphic") or ly.kind in SOFT or ly.kind in ("shot_headline", "kit_badge", "kit_grain"):
            keep.append(ly)
            continue
        # a small card (name, stamp, tag, sticker, fly-over ...) lies beside an overlay the CSV asked for; only a full-frame CSV card hides it
        span = csv_full if ly.kind in CORNER_KINDS else csv
        hit = [(a, b) for a, b in span if ly.start < b - 0.01 and ly.end > a + 0.01]
        if not hit:
            keep.append(ly)
            continue
        first = min(a for a, _b in hit)
        if first - ly.start >= 1.5:
            ly.end = fr(first - 0.1)
            keep.append(ly)
        counts["csv_trimmed"] = counts.get("csv_trimmed", 0) + 1
    plan.layers[:] = keep


def _csv_graphics(plan: Any, rows: Sequence[Dict[str, Any]], cfg: Dict[str, Any], cat: Any, log_by_no: Dict[str, Any], counts: Dict[str, int]) -> None:
    for r in rows:
        raw = str(r.get("graphic") or "").strip().lower()
        if not raw:
            continue
        dec = log_by_no.get(str(r["_no"]))
        kind = CSV_GRAPHIC.get(raw)
        if kind is None:
            kind = next((v for k, v in CSV_GRAPHIC.items() if k and k in raw), None)
        if not kind:
            if dec is not None and raw not in ("auto", "none"):
                dec.flags.append(f"csv_graphic_unknown:{raw}")
            continue
        try:
            ly, why = _csv_layer(kind, r, cfg, cat)
        except Exception as exc:            # one odd row never stops the plan
            ly, why = None, f"{type(exc).__name__}: {exc}"
        if ly is None:
            if dec is not None:
                dec.flags.append(f"csv_graphic_fallback:{kind}")
                dec.candidates.append({"kind": kind, "score": 0.0, "reason": f"CSV asked for {kind}: {why}; the automatic choice is kept", "accepted": False})
            counts["csv_graphic_fallback"] = counts.get("csv_graphic_fallback", 0) + 1
            continue
        st, en = r["_start"], r["_end"]
        a = fr(max(st, min(ly.start, en - CSV_MIN_S)))
        b = fr(min(max(ly.end, a + CSV_MIN_S), max(en, a + CSV_MIN_S), a + CSV_MAX_S))     # never into the next scene (its own graphic)
        if ly.kind in TEXT_CARD_KINDS:            # a title / date / kinetic line lands and goes: the reference never holds type 6-8 s
            b = fr(min(b, a + TEXT_CARD_MAX_S))
        ly.start, ly.end = a, b
        ly.params = dict(ly.params or {}, csv_graphic=True)
        if ly.kind in MOTION_KINDS and dec is not None and "no_footage" not in dec.flags:
            ly.params["over"] = True             # a YouTube / stock row: the graphic lies over the playing clip instead of hiding it
            ly.dim = False
        plan.layers[:] = [x for x in plan.layers if not (x.kind not in SOFT and x.kind not in ("shot_headline", "kit_badge")
                                                           and x.start < b and x.end > a and not (x.params or {}).get("csv_graphic"))]
        if ly.kind in FULL_KINDS or ly.kind in ("lay_inset",):
            _yield_headline(plan, a, b)
        plan.layers.append(ly)
        if dec is not None:
            dec.flags.append("dir:csv_graphic")
            dec.candidates.append({"kind": ly.kind, "score": 0.0, "reason": f"CSV graphic column: {raw}", "accepted": True, "start": a, "end": b})
        counts["csv_graphic"] = counts.get("csv_graphic", 0) + 1


# ------------------------------------------------------------------------------------------------ graphic floor -----------------------
# Rule 17 (the owner, 2026-11-07: "graphics we already have should be added in the video"; a footage-heavy render showed almost none):
# the triggers above only fire on places, numbers, quotes and named weapons, so plain narration over footage got nothing but headlines.
# Now no stretch of more than GRAPHIC_GAP s goes without one of the graphics the style already has, made from the narration's own words
# (a map for a place or country, icons or a sticker for the things named, a list recap, an inset caption or a hook tag). The least used
# kind so far goes first, so one video shows the whole kit instead of the same card again and again.
GRAPHIC_GAP = 10.0
_NOT_A_GRAPHIC = SOFT | {"shot_headline", "kit_ribbon", "kit_stamp", "kit_flag"}     # small marks; a gap with only these is still empty


def _floor_options(sent: Any, has_footage: bool, layouts: bool) -> List[Tuple[str, Dict[str, Any], float]]:
    """(kind, params, seconds) the sentence truthfully supports, most specific first. The hook tag is always possible."""
    out: List[Tuple[str, Dict[str, Any], float]] = []
    from . import graphics_lib as GL

    ch = GL.chart_of(sent.text, sent.numbers)               # the script's own figures, three or more, each with its label: a chart
    if ch:
        out.append(("kit_chart", ch, 5.0))
    art = GL.article_of(sent)                                # a cited report: the document page with the reported words highlighted
    if art:
        out.append(("lay_document", art, 5.0))
    pl, co = _places(sent), _countries(sent)
    if pl:
        p = _tac_params(sent, pl, co, False)
        if p:
            out.append(("tac_map", p, 4.5))
    elif co:
        p = _tac_params(sent, [], co, True)
        if p:
            out.append(("tac_map", p, 4.5))
    found: List[Tuple[int, str, str, str]] = []
    if not pl and not co:
        for rx, name, lab in _STICKERS:
            mm = re.search(rx, sent.text, re.IGNORECASE)
            if mm and name not in [f[1] for f in found] and not any(f[0] <= mm.start() < f[0] + 12 for f in found):
                found.append((mm.start(), name, mm.group(0), lab))
        found.sort()
    if 2 <= len(found) <= 4:
        out.append(("kit_icons", {"icons": [{"name": nm, "label": word, "start": 0.3 + 0.5 * i} for i, (_p, nm, word, _l) in enumerate(found)],
                                  "link": "vs" if _ICON_LINK_VS.search(sent.text) else "arrow" if _ICON_LINK_ARROW.search(sent.text) else "",
                                  "title": _phrase(sent.text)}, 5.0))
    if found:
        out.append(("kit_sticker", {"name": found[0][1], "x": 0.68, "y": 0.46, "size": 260, "label": found[0][3], "label_style": "tape"}, 3.2))
    its = _items(sent.text)
    if its:
        out.append(("kit_recap", {"items": [i[:1].upper() + i[1:] for i in its]}, 4.0))
    h = _phrase_or_lead(sent.text)
    if h:
        out.append(("kit_kinetic", {"text": h, "key": _key_words(h, 2)}, 3.6))     # a short full-frame type break, then back to the clip
        if has_footage and layouts:
            out.append(("lay_inset", {"caption": h, "caption_sub": "", "notes": []}, 4.0))
        out.append(("kit_tag", {"text": h, "pos": "top-left", "style": "hook"}, 3.2))
    return out


def _graphic_floor(plan: Any, rows: Sequence[Dict[str, Any]], cat: Any, log_by_no: Dict[str, Any], counts: Dict[str, int], gap: float,
                   first_at: float, layouts: bool = True) -> None:
    total = max((r["_end"] for r in rows), default=0.0)
    if gap <= 0 or total <= first_at + gap:
        return
    sents: List[Tuple[float, float, Any, Dict[str, Any]]] = []      # (start, end, sentence, row) of every spoken sentence, in order
    for r in rows:
        if not str(r.get("text") or "").strip() or log_by_no.get(str(r["_no"])) is None:
            continue
        A = S.analyze_scene(str(r.get("text") or ""), cat, r.get("words"), r["_start"], r["_end"])
        for sent in A.sentences:
            a, b = _sent_window(A, sent, r["_start"], r["_end"])
            sents.append((a, b, sent, r))
    sents.sort(key=lambda x: x[0])
    used: Dict[str, int] = {}
    for ly in plan.layers:
        if ly.kind not in _NOT_A_GRAPHIC:
            used[ly.kind] = used.get(ly.kind, 0) + 1
    busy = _Busy(plan.layers)
    last_kind = ""
    cursor = first_at
    while cursor < total - 3.0:
        spans = sorted((ly.start, ly.end) for ly in plan.layers if ly.kind not in _NOT_A_GRAPHIC and ly.end > cursor + 0.01)
        nxt = spans[0][0] if spans else total
        if nxt <= cursor + 0.01:                       # a graphic is on screen now: carry on after it
            cursor = max(cursor + 0.5, spans[0][1])
            continue
        if nxt - cursor < gap:
            if not spans:
                break                                  # the video ends before the gap would
            cursor = spans[0][1]
            continue
        # an empty stretch [cursor, nxt): the sentence that starts nearest a few seconds in gets a graphic
        aim = cursor + min(gap * 0.5, (nxt - cursor) * 0.5)
        pool = sorted((x for x in sents if cursor - 0.01 <= x[0] < nxt - 2.5), key=lambda x: abs(x[0] - aim))
        placed = False
        for a, b, sent, r in pool:
            dec = log_by_no.get(str(r["_no"]))
            has_footage = "no_footage" not in dec.flags
            opts = _floor_options(sent, has_footage, layouts)
            opts.sort(key=lambda o: (o[0] == last_kind, used.get(o[0], 0)))     # least used first, never the same kind twice in a row
            full = [(ly.start, ly.end) for ly in plan.layers if ly.kind in FULL_KINDS]
            for kind, params, secs in opts:
                ign = ("shot_headline",)
                slot = busy.free(max(a, cursor), min(nxt, r["_end"] + 1.5), min(secs, 3.0), ignore=ign)
                if slot is None:
                    continue
                s0, s1 = slot[0], fr(min(slot[1], slot[0] + secs))
                if kind in FULL_KINDS | {"lay_inset"} and _near_full(full, s0, s1):
                    continue
                if kind == "kit_icons":
                    params = dict(params, seed=int(r["_no"]) if str(r["_no"]).isdigit() else 0)
                if kind in MOTION_KINDS and has_footage:
                    params = dict(params, over=True)     # over the clip, not instead of it
                if kind == "tac_map":
                    A_ = S.analyze_scene(str(r.get("text") or ""), cat, r.get("words"), r["_start"], r["_end"])
                    params = _narrate_map(params, str(r.get("text") or ""), A_, s0, _countries_in(A_))
                ly = Layer(kind, s0, s1, params, dim=(kind in DIM))
                if kind in ("tac_map", "lay_inset", "kit_icons"):
                    _yield_headline(plan, s0, s1)
                plan.layers.append(ly)
                busy.add(s0, s1, kind)
                used[kind] = used.get(kind, 0) + 1
                last_kind = kind
                dec.flags.append("dir:floor")
                dec.candidates.append({"kind": kind, "score": 0.0, "reason": f"direction: no graphic for {nxt - cursor:.0f} s, one from the kit",
                                       "accepted": True, "start": s0, "end": s1})
                counts["floor"] = counts.get("floor", 0) + 1
                cursor = s1
                placed = True
                break
            if placed:
                break
        if not placed:
            cursor += gap                              # nothing fits here (no free slot): move on, never invent


# ------------------------------------------------------------------------------------------------ layout choice -----------------------
# What the narration means picks the composition. Existing planner layers are upgraded in place (params only restated, nothing invented):
# quotation -> figure hero, named system -> equipment hero, number -> stat split, dated events -> timeline, claim -> claim layout.
# Supply language that names two or more chain links -> logistics diagram. Two full-frame compositions never meet within FULL_GAP s.
LAYOUT_KINDS = {"lay_figure_hero", "lay_figure_pair", "lay_equipment_hero", "lay_equipment_compare", "lay_stat_split", "lay_timeline", "lay_claim",
                "lay_logistics"}
MOTION_KINDS = {"kit_kinetic", "kit_dossier", "kit_radar", "kit_keywords", "kit_title", "kit_datecard", "kit_quote"}
FULL_KINDS = {"map_card", "timeline", "split_compare", "tac_map", "tac_route", "stat_compare", "kit_icons", "kit_flag", "lay_satellite", "lay_document",
              "kit_chart", "lay_speaker_quote"} | LAYOUT_KINDS | MOTION_KINDS
FULL_GAP = 1.2
CORNER_KINDS = {"kit_speaker", "kit_stamp", "kit_tag", "kit_ribbon", "kit_sticker", "kit_flyover", "kit_chips", "map_inset", "kit_flag",
                "bc_source", "bc_label", "bc_caption", "bc_bigword",
                "status_chip", "evidence_card", "source_label"}     # cards that sit in a corner or cross the frame: they coexist with a clip
ICON_GAP = 15.0            # one icon explainer per this many seconds
COUNTRY_MAP_GAP = 30.0     # a country on its own gets a map again only after this long (Ukraine and Russia are named in every other sentence)
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


def _yield_headline(plan: Any, a: float, b: float) -> None:
    """A full-frame map placed over a footage headline: the headline ends where the map begins, or goes when too little of it is left."""
    keep = []
    for ly in plan.layers:
        if ly.kind == "shot_headline" and ly.start < b and ly.end > a:
            if a - ly.start >= 1.5:
                ly.end = fr(a)
            else:
                continue
        keep.append(ly)
    plan.layers[:] = keep


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
        if _near_full(others, ly.start, ly.end) and not (ly.params or {}).get("csv_graphic"):     # the CSV asked for this one
            counts["layout_skipped_adjacent"] = counts.get("layout_skipped_adjacent", 0) + 1
            return False
        if (ly.params or {}).get("csv_graphic"):
            params = dict(params, csv_graphic=True)    # still the CSV's choice after the layout upgrade
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
        elif ly.kind == "equipment_card" and p.get("name"):     # a type card too ('Tanks'): labelled silhouette, class row, unverified chip
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
            prev = [ly for ly in plan.layers if ly.kind in cover and abs(ly.end - g0) < 0.05 and not (ly.params or {}).get("csv_graphic")]
            if prev and prev[0].kind in cover:
                nxt_starts = [ly.start for ly in plan.layers if ly is not prev[0] and ly.start >= g0 - 0.01
                              and ly.kind not in ("kit_badge", "kicker", "shot_headline", "status_chip")]
                limit = min([g1, g0 + max_extra] + [x - 0.35 for x in nxt_starts])   # never into the next card
                if prev[0].kind in ("tac_map", "tac_route", "map_card"):
                    from .map_build import MAX_MAP_S
                    limit = min(limit, prev[0].start + MAX_MAP_S)          # a map's footage break stays a break
                if limit - g0 < 0.4:
                    continue
                prev[0].end = fr(limit)
                moved = True
                continue
            nxt = [ly for ly in plan.layers if ly.kind in LAYOUT_KINDS and abs(ly.start - g1) < 0.05 and not (ly.params or {}).get("csv_graphic")]
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
    (one leads to the next) or VS. At most one per ICON_GAP s; never over another full-frame card. Over footage too: the things named
    explained as icons say more than a clip of something near them."""
    last = -999.0
    block = FULL_KINDS - ({"tac_map", "tac_route", "map_card"} if maps_rebuilt else set())     # short maps give way: map_build redraws them
    for r in rows:
        dec = log_by_no.get(str(r["_no"]))
        if dec is None or not str(r.get("text") or "").strip():
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
            if a - last < ICON_GAP or any(ly.kind in block and ly.start < b and ly.end > a for ly in plan.layers) or _near_full(
                    [(ly.start, ly.end) for ly in plan.layers if ly.kind in block], a, b):
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
    carded: set = set()
    for r in rows:
        dec = log_by_no.get(str(r["_no"]))
        if dec is None or "no_footage" in dec.flags or not str(r.get("text") or "").strip():
            continue
        A = S.analyze_scene(str(r.get("text") or ""), cat, r.get("words"), r["_start"], r["_end"])
        for sent in A.sentences:
            spk = speaker_of(sent.text)
            at_char = sent.span[0]
            if not spk:                  # a known person named over footage, first time in the video: the catalogue's name and role (a lower third)
                fig = next((e for e in sent.entities if e.kind == "figure" and e.specific and not e.ambiguous and e.entry
                            and (e.id or e.name) not in carded and e.entry.get("role")), None)
                if fig is None:
                    continue
                role = re.split(r"\s+(?:since|from|until)\s+|\s*\(", str(fig.entry["role"]))[0].strip()
                spk = (str(fig.entry.get("name") or fig.name), role[:48])
                at_char = fig.span[0]
            carded.add(spk[0])
            a = fr(max(r["_start"], A.time_at(at_char) + 0.2))
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
            if any((ly.params or {}).get("csv_graphic") and ly.start < b and ly.end > a for ly in plan.layers):
                continue                          # the CSV chose this scene's graphic
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
    _csv_graphics(plan, rows, cfg, cat, log_by_no, counts)     # what the CSV's graphic column asks for goes in first; the rules fill around it
    if cfg.get("layouts", True):
        layout_spans = _choose_layouts(plan, rows, cat, log_by_no, counts)
    busy = _Busy(plan.layers)
    new_layers: List[Layer] = []

    def add(kind: str, a: float, b: float, params: Dict[str, Any], dec: Any, rule: str, why: str, scene_end: float, dim: Optional[bool] = None) -> bool:
        a, b = fr(a), fr(min(b, scene_end + 0.5))
        if b - a < 0.8:
            return False
        if kind == "tac_map":                     # the map follows the narration: pins, colours, movement and camera on the words
            params = _narrate_map(params, text, A, a, _countries_in(A))
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
                                                                and ly.start < a0 + 3.6 and ly.end > a0 and st - 0.01 <= ly.start < en
                                                                and not (ly.params or {}).get("csv_graphic"))]  # not a statistic
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

        # ---- 5a chart: three or more labelled figures in one sentence are a chart, not one big number -----------------------------------
        if cfg.get("charts", True) and last_kind != "kit_chart":
            from . import graphics_lib as _gl

            for sent in A.sentences:
                ch = _gl.chart_of(sent.text, sent.numbers)
                if not ch:
                    continue
                old = next((ly for ly in plan.layers if ly.kind in ("stat_number", "kit_bignum", "stat_compare") and st - 0.01 <= ly.start < en
                            and not (ly.params or {}).get("csv_graphic")), None)
                if old is None:
                    break
                a0, b0 = old.start, min(en + 0.5, max(old.end, old.start + 5.0))
                plan.layers[:] = [x for x in plan.layers if not (x.kind == "kicker" and abs(x.start - old.start) < 0.01)]
                old_span = (old.start, old.end, old.kind)
                old.kind, old.params, old.dim, old.end = "kit_chart", ch, False, fr(b0)
                busy.items = [x for x in busy.items if x != old_span] + [(old.start, old.end, "kit_chart")]   # the next scene sees the real span
                dec.flags.append("dir:chart")
                dec.candidates.append({"kind": "kit_chart", "score": 0.0, "reason": f"direction: {len(ch['items'])} labelled figures in one sentence",
                                       "accepted": True, "start": a0, "end": old.end})
                counts["chart"] = counts.get("chart", 0) + 1
                last_at["kit_chart"] = st
                picked = picked or "kit_chart"
                break

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
                ctx_key = "ctx:" + "|".join(sorted(c.name for c in co))   # the same wide view of the same countries says nothing new a minute later
                if st - last_at.get(ctx_key, -1e9) >= CONTEXT_REPEAT_S:
                    last_at[ctx_key] = st
                    proposals.append((4, "tac_map", a, max(b, a + 4.0), _tac_params(sent, [], co, True), "tacmap", "country-to-country context", False))
            elif pl and has_footage:      # one named place over footage: a short map shows where it is, then back to the clip
                p1 = _tac_params(sent, pl, co, False)
                if p1:
                    proposals.append((4, "tac_map", a, max(b, a + 4.0), p1, "tacmap", "a named place over footage: where it is", False))
            elif co and not pl and st - max((last_at.get("country:" + c.name, -999.0) for c in co), default=-999.0) >= COUNTRY_MAP_GAP:
                pc = _tac_params(sent, [], co, True)
                if pc:
                    proposals.append((5, "tac_map", a, max(b, a + 4.0), pc, "tacmap", f"{co[0].name} named: where it sits", False))
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
            # 4b cited report -> the document page with the reported words highlighted (full frame, the clip returns after it)
            if cfg.get("articles", True) and sent.citation is not None and st - last_at.get("lay_document", -999) >= 30.0:
                from . import graphics_lib as _gl

                art = _gl.article_of(sent)
                if art:
                    ka = max(a, st + 0.2)
                    if r.get("footage"):
                        art = dict(art, plate=str(r["footage"]), plate_t=1.0)       # the reference's blurred plate: the scene's own clip
                    proposals.append((3, "lay_document", ka, min(b + 1.0, ka + 5.0), art, "article", f"a report cited ({art['outlet']})", False))
            # 4c drones / missiles / aircraft launched or flying: the named system crosses the frame as the words are spoken
            if cfg.get("flyovers", True) and st - last_at.get("kit_flyover", -999) >= 25.0:
                from . import graphics_lib as _gl

                fo = _gl.flyover_of(sent.text)
                if fo:
                    mm = re.search(r"\b" + re.escape(fo["label"].split()[0].lower()), sent.text.lower())
                    ka = max(a, A.time_at(sent.span[0] + mm.start()) - 0.3) if mm else max(a, st + 0.3)
                    proposals.append((4, "kit_flyover", max(st + 0.2, ka - 1.5), en + 0.5, fo, "flyover", f"'{fo['label'].lower()}' in flight", False))
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
                was_csv = bool((old.params or {}).get("csv_graphic"))
                old.kind, old.params, old.dim = "tac_map", _narrate_map(tac[4], text, A, old.start, _countries_in(A)), False
                if was_csv:
                    old.params["csv_graphic"] = True
                dec.flags.append("dir:tacmap")
                dec.candidates.append({"kind": "tac_map", "score": 0.0, "reason": "direction: " + tac[6] + " (replaces the plain map card)", "accepted": True,
                                       "start": old.start, "end": old.end})
                counts["tacmap"] = counts.get("tacmap", 0) + 1
                last_at["tac_map"] = st
                picked = "tac_map"
        proposals = [x for x in proposals if not (picked == "tac_map" and x[1] == "tac_map")]
        for pri, kind, a, b, params, rule, why, dim in proposals:
            if picked is not None and kind not in ("kit_stamp", "kit_flyover"):
                continue                                  # an overlay (stamp, fly-over) may still join the scene's one graphic
            if kind == last_kind and not (kind == "tac_map" and a - last_at.get("tac_map_end", -999.0) >= 4.0):
                continue                                  # two maps in a row only with time between them
            if kind == "kit_tag" and st - last_at.get("kit_tag", -999) < 25.0:
                continue
            ign = ("shot_headline",) if kind in ("kit_stamp", "kit_sticker", "kit_scale", "kit_recap", "kit_chips", "kit_tag", "tac_map", "lay_document",
                                                 "kit_flyover") else ()
            need = {"tac_map": 3.6, "kit_stamp": 1.4, "kit_flyover": 2.2, "lay_document": 3.4, "kit_tag": 2.0, "kit_recap": 3.0, "kit_chips": 3.0, "kit_sticker": 2.2, "kit_scale": 3.0}.get(kind, 2.0)
            slot = busy.free(a, min(b + (1.0 if kind in ("tac_map", "kit_recap", "kit_chips") else 0.0), en + 0.5), need, ignore=ign)
            if not slot:
                continue
            end = slot[1] if kind not in ("kit_stamp", "kit_flyover") else min(slot[1], slot[0] + (2.6 if kind == "kit_stamp" else 3.6))
            if kind == "tac_map" and _near_full([sp for sp in full_spans], slot[0], end):
                after = max((y for x, y in full_spans if x < end and y + FULL_GAP > slot[0]), default=slot[0])
                if end - (after + FULL_GAP) < need:
                    continue                              # no two full-frame compositions back to back
                slot = (fr(after + FULL_GAP), end)        # the map waits for the card before it to clear
            if kind == "kit_tag" and has_footage and cfg.get("layouts", True):
                kind, params, rule = "lay_inset", {"caption": params["text"], "caption_sub": "", "notes": []}, "inset"
            if add(kind, slot[0], end, params, dec, rule, why, en, dim=dim):
                last_at[kind] = st
                if kind == "lay_document":
                    full_spans.append((slot[0], end))
                    _yield_headline(plan, slot[0], end)
                if kind == "tac_map":
                    full_spans.append((slot[0], end))
                    last_at["tac_map_end"] = end
                    _yield_headline(plan, slot[0], end)
                    for sent_ in A.sentences:
                        for c in _countries(sent_):
                            last_at["country:" + c.name] = st
                if kind not in ("kit_stamp", "kit_flyover"):     # overlays join the scene's one graphic; they do not take its place
                    picked = picked or kind
                elif kind == "kit_stamp":
                    picked = picked or kind

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

        _mb.build(plan, rows, cat, log_by_no, counts, gap_notes, tuple(FULL_KINDS - {"tac_map", "tac_route", "map_card"}),
                  broll=bool(cfg.get("broll", True) and plan.shots))
    _speakers(plan, rows, cat, log_by_no, counts)
    _ratios_and_versus(plan, rows, cat, log_by_no, counts)
    if cfg.get("layouts", True):
        _extend_into_plate(plan, rows)
    for ov in [x for x in plan.layers if x.kind in ("kit_stamp",)]:       # a stamp lands on the footage or plate, never on top of a layout panel
        for lay in plan.layers:
            if lay.kind in LAYOUT_KINDS and lay.start < ov.start < lay.end and ov.start - lay.start >= 3.0:
                lay.end = fr(ov.start - 0.15)
    if cfg.get("broll", True):            # short clips end with their clip; the gaps they and the map breaks leave go back to the video's own footage
        _fit_short_clips(plan, counts)
        _broll_returns(plan, rows, log_by_no, meta_by_start, counts)
    _no_empty_stretch(plan, rows, cat, log_by_no, counts, gap_notes, motion=bool(cfg.get("motion_fill", True)))
    _csv_wins(plan, counts)
    if cfg.get("graphic_floor", True):
        _graphic_floor(plan, rows, cat, log_by_no, counts, float(cfg.get("graphic_gap", GRAPHIC_GAP)), float(cfg.get("first_at", 4.0)),
                       layouts=bool(cfg.get("layouts", True)))

    ev_stats: Dict[str, Any] = {}
    if cfg.get("map_events", True):               # what the script says changed hands, and strategic sites it names, on the tactical maps
        from . import map_events as _me

        ev_stats = _me.attach(plan, rows, cfg, cat)
        ev_stats["linked_maps"] = _me.continuity(plan) if cfg.get("map_continuity", True) else 0
        for k_, v_ in ev_stats.items():
            if v_:
                counts["map_" + k_] = v_
    fl_stats: Dict[str, Any] = {}
    if cfg.get("frontline", True):                # sourced front lines on the territorial maps (frontline.py); no library -> nothing happens
        from . import frontline as _fl

        fl_stats = _fl.attach(plan, rows, cfg)
        if fl_stats.get("attached"):
            counts["frontline"] = fl_stats["attached"]
    st_stats: Dict[str, Any] = {}
    if cfg.get("story", True):                    # long map runs get cards on the narration's beats; the opening becomes a montage hook
        from . import story as _story

        st_stats["rhythm"] = _story.map_rhythm(plan, rows, cat, cfg)
        for ly in plan.layers:                    # a map that now starts after a card travels on from the map before it again
            if ly.kind == "tac_map" and isinstance(ly.params, dict):
                ly.params.pop("enter_from", None)
        if cfg.get("map_events", True) and cfg.get("map_continuity", True):
            from . import map_events as _me2

            st_stats["linked_maps"] = _me2.continuity(plan)
        st_stats["hook"] = _story.hook(plan, rows, cfg)
        if cfg.get("storyline", True):
            from . import storyline as _sl

            st_stats["roadmap"] = _sl.roadmap(plan, rows, cat)
            st_stats.update(_sl.callbacks_and_recap(plan, rows, cat))
            st_stats["flashes"] = _sl.flashes(plan, rows, cat)
        for k_, v_ in list(st_stats["rhythm"].items()) + list(st_stats["hook"].items()) + [(k, v) for k, v in st_stats.items() if isinstance(v, int)]:
            if v_:
                counts["story_" + k_] = v_
    if cfg.get("broadcast", True):                # news-documentary marks on the footage: source tag, keyword label, caption box, big figure
        from . import broadcast as _bc

        bc = _bc.apply(plan, rows, cfg, cat)
        for k_, v_ in bc.items():
            if v_:
                counts["bc_" + k_] = v_
    full_spans = [(ly.start, ly.end) for ly in plan.layers if ly.kind in FULL_KINDS]

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
    if cfg.get("story", True) and cfg.get("storyline", True):     # strike lines over fitting footage cut faster (rhythm by meaning)
        from . import storyline as _sl2

        counts["story_paced"] = _sl2.pace(plan, rows, cat)
    eng: Dict[str, Any] = {}
    if cfg.get("engagement", True):               # where would it sag? measured on the plan; slow stretches of fitting footage re-cut
        from . import engagement as _eng

        eng = _eng.check(plan, rows)
        if cfg.get("engagement_fix", True):
            n_fix = _eng.fix(plan, rows, eng)
            if n_fix:
                eng = _eng.check(plan, rows)
                eng["fixed"] = n_fix
                counts["engagement_fixed"] = n_fix
    _treat_shots(plan, meta_by_start, hard, full_spans, counts, film=bool(cfg.get("film_grade", True)))
    _final_coverage(plan, max((r["_end"] for r in rows), default=0.0), counts)
    counts["empty_stretches"] = len(gap_notes)
    return {"counts": counts, "notes": gap_notes, "frontline": fl_stats, "map_events": ev_stats, "story": st_stats, "engagement": eng}


# ------------------------------------------------------------------------------------------------ final coverage --------------------
# Ahmed test render (2026-11-08): seconds of bare backdrop (gaps under the 2 s motion-card minimum, or opened by trims that run after the
# empty-stretch rule), a source chip left on the plate after its clip ended, and a 0.8 s clip flash between two cards. This runs last, on the
# finished timeline: every second shows footage or a full-frame graphic, footage marks only sit on footage, and a clip seen for less than
# FLASH_S between two graphics is covered by the graphic before it.
FLASH_S = 1.5
HOLE_HOLD_S = 2.0          # a bare gap up to this long is closed by its neighbours (longer ones are filled with motion graphics earlier)


def _opaque(ly: Layer) -> bool:
    return ly.kind in FULL_KINDS and not (ly.params or {}).get("over")


def _spans_union(spans: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    out: List[List[float]] = []
    for a, b in sorted(spans):
        if b - a <= 1e-6:
            continue
        if out and a <= out[-1][1] + 1e-6:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return [(a, b) for a, b in out]


def _final_coverage(plan: Any, total: float, counts: Dict[str, int]) -> None:
    if total <= 0:
        return
    full = sorted((ly for ly in plan.layers if _opaque(ly)), key=lambda x: x.start)
    # 1 a clip glimpsed between two graphics: the graphic before it holds instead of a flash
    for i, a in enumerate(full[:-1]):
        b = min(full[i + 1:], key=lambda x: x.start)
        gap = b.start - a.end
        if 0.04 < gap < FLASH_S and any(sh.start < b.start and sh.end > a.end for sh in plan.shots):
            mid = fr((a.end + b.start) / 2.0)                         # both graphics share the glimpse: neither runs long or into another scene
            a.end, b.start = mid, mid
            counts["flashes_covered"] = counts.get("flashes_covered", 0) + 1
    # 2 any bare second: hold the piece before it (a card, or the clip when it still has frames), else start the next one earlier
    shots = sorted(plan.shots, key=lambda x: x.start)
    covered = _spans_union([(x.start, x.end) for x in shots] + [(ly.start, ly.end) for ly in full])
    holes, cur = [], 0.0
    for a, b in covered + [(total, total)]:
        if a - cur > 0.04:
            holes.append((cur, min(a, total)))
        cur = max(cur, b)
    for h0, h1 in holes:
        if h1 - h0 > HOLE_HOLD_S:                    # a long stretch is the empty-stretch rule's (motion graphics from the narration), not a hold
            continue
        prev_l = max((ly for ly in full if abs(ly.end - h0) < 0.05), key=lambda x: x.end, default=None)
        prev_s = max((sh for sh in shots if abs(sh.end - h0) < 0.05), key=lambda x: x.end, default=None)
        next_l = min((ly for ly in full if abs(ly.start - h1) < 0.05), key=lambda x: x.start, default=None)
        next_s = min((sh for sh in shots if abs(sh.start - h1) < 0.05), key=lambda x: x.start, default=None)
        if prev_s is not None and (_clip_seconds(prev_s.path) or 0.0) - prev_s.seek >= (h1 - prev_s.start):
            prev_s.end = fr(h1)
        elif prev_l is not None and next_l is not None:
            mid = fr((h0 + h1) / 2.0)
            prev_l.end, next_l.start = mid, mid
        elif prev_l is not None:
            prev_l.end = fr(h1)
        elif next_l is not None:
            next_l.start = fr(h0)
        elif next_s is not None and next_s.seek >= h1 - h0:          # the next clip starts a moment earlier in its own source
            next_s.seek, next_s.start = round(next_s.seek - (h1 - h0), 3), fr(h0)
        elif prev_s is not None:                                     # the clip's last frame holds (the renderer clones it) instead of bare plate
            prev_s.end = fr(h1)
        elif next_s is not None:
            next_s.start = fr(h0)
        else:
            continue
        counts["holes_closed"] = counts.get("holes_closed", 0) + 1
    # 3 footage marks (source chip, badge) only where footage is actually seen
    seen = [(sh.start, sh.end) for sh in plan.shots]
    blocked = _spans_union([(ly.start, ly.end) for ly in plan.layers if _opaque(ly)])
    keep: List[Layer] = []
    for ly in plan.layers:
        if ly.kind not in ("status_chip", "kit_badge"):
            keep.append(ly)
            continue
        vis = []
        for a, b in seen:
            a, b = max(a, ly.start), min(b, ly.end)
            for x, y in blocked:                       # minus the graphics drawn over the footage
                if y <= a or x >= b:
                    continue
                if x - a >= 1.0:
                    vis.append((a, x))
                a = max(a, y)
            if b - a >= 1.0:
                vis.append((a, b))
        if not vis:
            counts["orphan_marks"] = counts.get("orphan_marks", 0) + 1
            continue
        for a, b in vis:
            keep.append(Layer(ly.kind, fr(a), fr(b), dict(ly.params or {}), dim=ly.dim))
    plan.layers[:] = keep
