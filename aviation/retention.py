"""Aviation retention pass (docs/aviation/MASTER_PLAN.md section 6, video side): the visual retention check and the deterministic
fixes that run on a Plan before render.

    turn_lines(scenes) -> [scene idx]          the narration's own turning lines (+ the opening question and its answer line)
    opening_question(scenes) -> (q_idx, a_idx, question) the first question in the first ~60 s and the later line that answers it (-1 if none)
    check(plan, scenes) -> [issue]             issue = {kind, start, end, scene, detail}
    apply(plan, scenes) -> report              fixes what it can IN the plan; report = {fixed, left, turn_lines}
    lay_rehook(t, dur, params) -> RGBA 1280x720 or None     the 0.6 s wipe flash (shared card contract; registered by the lead)

Issue kinds
    same_kind          one kind of picture (footage / map / card / graphic) on screen for more than MAX_SAME_S
    stage_idle         a stage shot where nothing new appears (no element in/out/move, no year) for more than MAX_SAME_S
    text_cards_in_row  two text-only cards (article, document, fact sheet, title) back to back
    slow_opening       the first OPEN_WINDOW_S change picture slower than every OPEN_AVG_S on average
    card_long          a card held longer than CARD_MAX
    no_rehook          no re-hook (rehook marker) for REHOOK_MAX_S
    no_callback        the answer line does not bring the opening's visual back

Fixes (all deterministic, never inventing words - every inserted text is a substring of the scene's own text)
    re-hook        each turn line gets a short marker shot {"layer": "retention.lay_rehook", end = start + 0.6}, a cue (t, "rehook") on
                   the shots it touches, and on a stage a 'big_type' element with the turn line's first words (<= 6)
    forced re-hook a wipe-only marker at a scene start when 90 s pass without a turn line
    stage idle     a gentle glide/scale on the oldest live element (or a 'text' element with the line's key noun phrase)
    slow opening   footage slots of the first 30 s are cut into 1.5-2 s slots with the same queries
    long footage   a footage slot longer than 8 s is cut into <= 4 s slots (same queries)
    callback       the opening's first stage element (same kind + args) or the opening's first footage queries come back on the answer line
    long card      shortened to CARD_MAX; the rest returns to the underlying shot (or to a footage slot with the nearest queries)
Cue format: a stage shot keeps the cue format it already has ((t, name) tuples from story.build; dicts if it already holds dicts).
"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFilter

from cinematic_explainer.war import tokens as T

W, H = T.W, T.H

MAX_SAME_S = 8.0
CARD_MAX = 6.0
OPEN_WINDOW_S = 30.0
CALM_MODES = ("flight", "weather", "fleet")
OPEN_AVG_S = 2.0
REHOOK_MAX_S = 90.0
MIN_REHOOK_GAP_S = 15.0
REHOOK_S = 0.6
BIG_TYPE_S = 2.2
BIG_TYPE_WORDS = 6
QUESTION_WINDOW_S = 60.0

TEXT_CARDS = {"cards.lay_article", "war.lay_document", "gfx.lay_sheet", "gfx_air.lay_title", "gfx.lay_end_card"}
OVERLAYS = {"hud.lay_hud", "hud.lay_radio", "gfx.lay_counters", "gfx.lay_altitude", "gfx.lay_weather", "gfx.lay_place_title",
            "gfx_air.lay_crew", "retention.lay_rehook"}
MAPS = {"flightmap.lay_flight_map"}
GATHER_GAP = 0.5            # shots closer than this belong to one continuous run

_STOP = set("the a an and or of to in on at for with by from is are was were be been it its this that these those as but not "
            "so do did does has have had will would could can who what why how when where which than then there their they he she "
            "his her we you i us our your into about over after before just also very more most".split())

# ------------------------------------------------------------------------------------------------------------ turn lines
_TURN = re.compile(
    r"^(?:"
    r"but\s+(?:then|now|here|there|what|nobody|no\s+one|in\s+fact|the|this|that|it|as|by|when|just)\b"
    r"|however\b|until\b|then\s+the\s+story\b|then\s+everything\b|then\s+something\b"
    r"|what\s+nobody\b|what\s+no\s+one\b|what\s+(?:they|he|she|we)\s+(?:didn't|did\s+not|never)\b"
    r"|that\s+changed\b|that\s+all\s+changed\b|everything\s+changed\b|all\s+of\s+that\s+changed\b"
    r"|here(?:'s|\s+is)\s+the\s+(?:problem|catch|thing|twist)\b|the\s+(?:twist|catch|problem)\b"
    r"|there\s+(?:is|was)\s+(?:a|one)\s+(?:catch|problem|twist)\b"
    r"|except\b|yet\b|instead\b|and\s+then\b|suddenly\b|little\s+did\b|nobody\s+(?:knew|expected|saw)\b"
    r")", re.I)
_QSTART = re.compile(r"^(?:so\s+|and\s+|but\s+)?(?:why|how|what|who|where|when|which|did|does|do|was|were|is|are|could|can|would|"
                     r"should|will|has|have)\b", re.I)
_ANSWER = re.compile(r"\b(?:because|the\s+answer|that(?:'s|\s+is)\s+why|the\s+reason|this\s+is\s+why)\b", re.I)
_SENT = re.compile(r"[^.!?]+[.!?]+[\"')\]]*|[^.!?]+$")
_WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9'\-]*")


def _sentences(text: str) -> List[Tuple[int, str]]:
    """(char position, sentence text) with the sentence a verbatim substring of text."""
    out = []
    for m in _SENT.finditer(text):
        s = m.group(0)
        lead = len(s) - len(s.lstrip())
        s = s.strip()
        if s:
            out.append((m.start() + lead, s))
    return out


def _scene_turns(text: str) -> List[Tuple[int, str, str]]:
    """(char pos, sentence, why) for the turning sentences of a scene."""
    hits = []
    for pos, s in _sentences(text):
        body = s.lstrip("\"'([ ")
        if s.rstrip().endswith("?") and len(_WORD.findall(s)) >= 3 and _QSTART.match(body):
            hits.append((pos, s, "question"))
        elif _TURN.match(body):
            hits.append((pos, s, "turn"))
    return hits


def _keys(sentence: str) -> List[str]:
    return [w.lower() for w in _WORD.findall(sentence) if len(w) >= 3 and w.lower() not in _STOP]


def opening_question(scenes: Sequence[Dict[str, Any]]) -> Tuple[int, int, str]:
    """(question scene idx, answer scene idx, question sentence); -1 where not found."""
    if not scenes:
        return -1, -1, ""
    t_first = float(scenes[0].get("start", 0) or 0)
    q_idx, q_sent = -1, ""
    for i, sc in enumerate(scenes):
        if float(sc.get("start", 0) or 0) - t_first > QUESTION_WINDOW_S:
            break
        for _, s in _sentences(str(sc.get("text") or "")):
            if s.rstrip().endswith("?") and len(_WORD.findall(s)) >= 3:
                q_idx, q_sent = i, s
                break
        if q_idx >= 0:
            break
    if q_idx < 0:
        return -1, -1, ""
    keys = set(_keys(q_sent))
    need = min(2, len(keys))
    for j in range(q_idx + 1, len(scenes)):
        text = str(scenes[j].get("text") or "")
        if _ANSWER.search(text) and len(keys & set(_keys(text))) >= max(1, need):
            return q_idx, j, q_sent
    return q_idx, -1, q_sent


def turn_lines(scenes: Sequence[Dict[str, Any]]) -> List[int]:
    """Indices of the scenes that turn the story: rule-based turn phrases, questions, the opening question and its answer line."""
    out = set()
    for i, sc in enumerate(scenes):
        if _scene_turns(str(sc.get("text") or "")):
            out.add(i)
    q, a, _ = opening_question(scenes)
    if q >= 0:
        out.add(q)
    if a >= 0:
        out.add(a)
    return sorted(out)


# ------------------------------------------------------------------------------------------------------------ plan helpers
def _kind(shot: Dict[str, Any]) -> str:
    lay = shot.get("layer")
    if not lay:
        return "footage"
    if lay == "retention.lay_rehook":
        return "rehook"
    if lay in OVERLAYS:
        return "overlay"
    if lay in MAPS:
        return "map"
    if lay.startswith("stage."):
        return "stage"
    if lay in TEXT_CARDS:
        return "card"
    return "graphic"


def _is_text_card(shot: Dict[str, Any]) -> bool:
    return shot.get("layer") in TEXT_CARDS and shot.get("layer") != "gfx.lay_end_card"


def _base(plan) -> List[Dict[str, Any]]:
    return sorted((s for s in plan.shots if _kind(s) not in ("overlay", "rehook")), key=lambda s: (float(s["start"]), float(s["end"])))


def _plan_span(plan) -> Tuple[float, float]:
    if not plan.shots:
        return 0.0, 0.0
    return min(float(s["start"]) for s in plan.shots), max(float(s["end"]) for s in plan.shots)


def _stage_events(shot: Dict[str, Any]) -> List[float]:
    """Absolute times at which something new happens on a stage shot (always includes the shot's start)."""
    t0 = float(shot["start"])
    p = shot.get("params") or {}
    ev = [t0]
    for e in p.get("elements") or []:
        ev.append(t0 + float(e.get("t0", 0)))
        for k in (e.get("keys") or [])[1:]:
            ev.append(t0 + float(k[0]))
        if e.get("t1") is not None:
            ev.append(t0 + float(e["t1"]))
    for y in p.get("years") or []:
        ev.append(t0 + float(y[0]))
    return sorted(t for t in ev if t0 - 1e-6 <= t <= float(shot["end"]) + 1e-6)


def _scene_no(shot: Dict[str, Any]) -> Any:
    return shot.get("scene")


def _scene_index_at(scenes: Sequence[Dict[str, Any]], t: float) -> int:
    for i, sc in enumerate(scenes):
        if float(sc.get("start", 0) or 0) - 1e-6 <= t < float(sc.get("end", 0) or 0):
            return i
    return max(0, len(scenes) - 1) if scenes else -1


def _issue(kind: str, start: float, end: float, scene: Any, detail: str) -> Dict[str, Any]:
    return {"kind": kind, "start": round(float(start), 3), "end": round(float(end), 3), "scene": scene, "detail": detail}


def _rehook_times(plan) -> List[float]:
    return sorted(float(s["start"]) for s in plan.shots if s.get("layer") == "retention.lay_rehook")


# ------------------------------------------------------------------------------------------------------------ check
def _opening_changes(plan, lo: float, hi: float) -> List[float]:
    ev: List[float] = []
    for s in _base(plan):
        if s["start"] >= hi:
            continue
        ev.append(float(s["start"]))
        if _kind(s) == "stage":
            ev.extend(_stage_events(s))
    ev = sorted(t for t in ev if lo - 1e-6 <= t < hi)
    out: List[float] = []
    for t in ev:
        if not out or t - out[-1] > 0.15:
            out.append(t)
    return out


def _callback_target(plan) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """(first stage element of the opening, the stage shot holding it) or (None, None); footage is read by _first_footage."""
    for s in _base(plan):
        if _kind(s) != "stage":
            continue
        els = [e for e in (s.get("params") or {}).get("elements") or [] if not str(e.get("id", "")).startswith("rh_")
               and e.get("kind") not in ("caption", "backdrop", "text", "big_type", "timeline_bar", "timeline_dot")]
        if els:
            return min(els, key=lambda e: float(e.get("t0", 0))), s
    return None, None


def _first_footage(plan) -> Optional[Dict[str, Any]]:
    for s in _base(plan):
        if _kind(s) == "footage" and s.get("queries"):
            return s
    return None


def _has_callback(plan, a_start: float, a_end: float) -> Optional[bool]:
    """True/False, or None when the opening has no visual to call back."""
    el, st = _callback_target(plan)
    fo = _first_footage(plan)
    if el is None and fo is None:
        return None
    for s in plan.shots:
        if s.get("callback") and a_start - 1e-6 <= float(s["start"]) < a_end:
            return True
    for s in _base(plan):
        if not (a_start - 1e-6 <= float(s["end"]) and float(s["start"]) < a_end):
            continue
        if el is not None and _kind(s) == "stage" and s is not st:
            for e in (s.get("params") or {}).get("elements") or []:
                if e.get("kind") == el.get("kind") and e.get("args") == el.get("args"):
                    return True
        if el is None and fo is not None and _kind(s) == "footage" and s is not fo and s.get("queries") == fo.get("queries"):
            return True
    return False


def check(plan, scenes: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    base = _base(plan)
    lo, hi = _plan_span(plan)

    # same kind of picture too long ----------------------------------------------------------------------------------
    i = 0
    while i < len(base):
        s = base[i]
        k = _kind(s)
        if k == "map":                                           # a map is one continuous run; overlays are its changes
            j, end = i, float(s["end"])
            while j + 1 < len(base) and _kind(base[j + 1]) == "map" and float(base[j + 1]["start"]) - end < GATHER_GAP:
                j += 1
                end = float(base[j]["end"])
            run0 = float(s["start"])
            ev = [run0, end] + [float(o["start"]) for o in plan.shots if _kind(o) == "overlay" and run0 <= float(o["start"]) <= end
                                and o.get("layer") != "hud.lay_hud"]
            ev = sorted(ev)
            for a, b in zip(ev, ev[1:]):
                if b - a > MAX_SAME_S:
                    out.append(_issue("same_kind", a, b, _scene_no(s), f"map for {b - a:.1f}s with nothing new"))
            i = j + 1
            continue
        if k == "stage":
            ev = _stage_events(s)
            ev = sorted(set(ev + [float(s["end"])]))
            for a, b in zip(ev, ev[1:]):
                if b - a > MAX_SAME_S:
                    out.append(_issue("stage_idle", a, b, _scene_no(s), f"nothing new on stage for {b - a:.1f}s"))
        elif float(s["end"]) - float(s["start"]) > MAX_SAME_S:
            out.append(_issue("same_kind", s["start"], s["end"], _scene_no(s),
                              f"{k} for {float(s['end']) - float(s['start']):.1f}s"))
        i += 1

    # text-only cards in a row ---------------------------------------------------------------------------------------
    for a, b in zip(base, base[1:]):
        if _is_text_card(a) and _is_text_card(b) and float(b["start"]) - float(a["end"]) < GATHER_GAP:
            out.append(_issue("text_cards_in_row", a["start"], b["end"], _scene_no(b), f"{a['layer']} then {b['layer']}"))

    # cards held too long ----------------------------------------------------------------------------------------------
    for s in base:
        if _kind(s) == "card" and s.get("layer") != "gfx.lay_end_card" and float(s["end"]) - float(s["start"]) > CARD_MAX + 1e-6:
            out.append(_issue("card_long", s["start"], s["end"], _scene_no(s),
                              f"{s['layer']} held {float(s['end']) - float(s['start']):.1f}s"))

    # opening ----------------------------------------------------------------------------------------------------------
    if base:
        win_hi = min(hi, lo + OPEN_WINDOW_S)
        ch = _opening_changes(plan, lo, win_hi)
        span = win_hi - lo
        if span >= 6.0 and ch and span / len(ch) > OPEN_AVG_S + 1e-6:
            out.append(_issue("slow_opening", lo, win_hi, _scene_no(base[0]),
                              f"{len(ch)} picture changes in {span:.0f}s (every {span / len(ch):.1f}s)"))

    # re-hook ----------------------------------------------------------------------------------------------------------
    marks = [lo] + _rehook_times(plan) + [hi]
    for a, b in zip(marks, marks[1:]):
        if b - a > REHOOK_MAX_S:
            out.append(_issue("no_rehook", a, b, None, f"{b - a:.0f}s without a re-hook"))

    # callback ---------------------------------------------------------------------------------------------------------
    q, a_idx, _ = opening_question(scenes)
    if q >= 0 and a_idx >= 0:
        a0, a1 = float(scenes[a_idx]["start"]), float(scenes[a_idx]["end"])
        if a0 - lo > OPEN_WINDOW_S and _has_callback(plan, a0, a1) is False:
            out.append(_issue("no_callback", a0, a1, scenes[a_idx].get("scene_no", a_idx + 1),
                              "the answer line does not bring the opening's visual back"))
    return sorted(out, key=lambda x: (x["start"], x["kind"]))


# ------------------------------------------------------------------------------------------------------------ fixes
def _fx(fixed: List[Dict[str, Any]], kind: str, start: float, scene: Any, reason: str) -> None:
    fixed.append({"fix": kind, "start": round(float(start), 3), "scene": scene, "reason": reason})


def _split_footage(plan, shot: Dict[str, Any], pieces: int) -> List[Dict[str, Any]]:
    a, b = float(shot["start"]), float(shot["end"])
    step = (b - a) / pieces
    new = []
    for k in range(pieces):
        c = dict(shot)
        c["start"], c["end"] = a + k * step, a + (k + 1) * step if k < pieces - 1 else b
        if "queries" in shot:
            c["queries"] = list(shot["queries"])
        new.append(c)
    idx = plan.shots.index(shot)
    plan.shots[idx:idx + 1] = new
    return new


def _fix_long_cards(plan, fixed, left) -> None:
    for s in list(_base(plan)):
        if _kind(s) != "card" or s.get("layer") == "gfx.lay_end_card":
            continue
        a, b = float(s["start"]), float(s["end"])
        if b - a <= CARD_MAX + 1e-6:
            continue
        cut = a + CARD_MAX
        covered = any(o is not s and _kind(o) in ("footage", "map", "stage") and float(o["start"]) <= cut + 1e-6 and float(o["end"]) >= b - 1e-6
                      for o in plan.shots)
        s["end"] = cut
        if not covered:
            ref = next((o for o in sorted(plan.shots, key=lambda o: abs(float(o["start"]) - cut))
                        if _kind(o) == "footage" and o.get("queries")), None)
            if ref is None:
                s["end"] = b
                left.append({"kind": "card_long", "start": a, "scene": s.get("scene"), "why": "no footage queries to fall back on"})
                continue
            back = {"kind": "footage", "start": cut, "end": b, "scene": s.get("scene"), "mode": ref.get("mode", "news"),
                    "queries": list(ref["queries"]), "cut": ref.get("cut", "cut")}
            plan.shots.append(back)
        _fx(fixed, "card_shortened", a, s.get("scene"), f"card held {b - a:.1f}s > {CARD_MAX:.0f}s; the rest returns to the picture beneath")


def _fix_footage_pace(plan, fixed) -> None:
    lo, hi = _plan_span(plan)
    win_hi = min(hi, lo + OPEN_WINDOW_S)
    ch = _opening_changes(plan, lo, win_hi)
    slow = win_hi - lo >= 6.0 and ch and (win_hi - lo) / len(ch) > OPEN_AVG_S + 1e-6
    for s in list(_base(plan)):
        if _kind(s) != "footage" or s.get("mode") in CALM_MODES:
            continue                       # flight / weather / fleet shots hold on purpose (Vistara: calm, 5-15 s on a moving map)
        a, b = float(s["start"]), float(s["end"])
        if slow and a < win_hi and b - a > 2.0 + 1e-6:
            n = math.ceil((b - a) / 2.0)
            if (b - a) / n < 1.5 and n > 1:
                n -= 1
            if n > 1:
                _split_footage(plan, s, n)
                _fx(fixed, "opening_split", a, s.get("scene"), f"opening picture changed every {(win_hi - lo) / len(ch):.1f}s; footage cut into {n} slots")
                continue
        if b - a > MAX_SAME_S:
            n = math.ceil((b - a) / 4.0)
            _split_footage(plan, s, n)
            _fx(fixed, "footage_split", a, s.get("scene"), f"same footage slot {b - a:.1f}s > {MAX_SAME_S:.0f}s; cut into {n}")


def _question_words(sentence: str) -> str:
    """The opening question as big type: the whole question when it fits (<= 20 words, wrapped), its question mark kept."""
    ms = _WORD.findall(sentence)
    return sentence.strip().strip(" \"'([") if 3 <= len(ms) <= 20 else ""


def _first_words(sentence: str, n: int = BIG_TYPE_WORDS) -> str:
    """The turn line's own words for big type: the whole line when it is short (<= WHOLE_WORDS, a question keeps its '?'),
    else its first clause, else its first n words. Always a verbatim piece of the narration."""
    ms = list(_WORD.finditer(sentence))
    if not ms:
        return ""
    if len(ms) <= WHOLE_WORDS:
        return sentence.strip().rstrip(".!,;:").strip(" \"'([")
    m = re.match(r"\s*([^,;:—–]+)[,;:—–]", sentence)
    if m and 3 <= len(_WORD.findall(m.group(1))) <= WHOLE_WORDS:
        return m.group(1).strip(" \"'([")
    return ""                         # a long line with no short clause: the wipe alone, never a half sentence on screen
    end = ms[min(n, len(ms)) - 1].end()
    return sentence[:end].strip(" \"'([")


WHOLE_WORDS = 9


def _a_of(scenes) -> int:
    try:
        return opening_question(scenes)[1]
    except Exception:
        return -1


def _wipe(els: List[Dict[str, Any]], rel: float, length: float) -> None:
    """The stage wipe of a re-hook / callback: everything on stage slides out for the beat (so the big type or the callback
    stands alone) and pops back after it - the stage never goes empty."""
    for e in els:
        if e.get("kind") == "backdrop":
            continue                                   # the photo behind the stage stays behind the big words
        t0 = float(e.get("t0", 0))
        if t0 < rel + length - 1e-6 and (e.get("t1") is None or float(e["t1"]) > rel):
            e.setdefault("hide", []).append([max(float(rel), t0 - 0.01), float(rel + length)])   # incl. what arrives mid-beat


def _make_element(kind: str, args: Dict[str, Any], t0: float, t1: Optional[float], z: int, ident: str,
                  pos: Tuple[float, float] = (640.0, 360.0), scale: float = 1.0, anim: float = 0.0,
                  edge: bool = False, float_: bool = False) -> Dict[str, Any]:
    """Built the way stage.Stage.add builds it (same keys), so lay_stage draws it like any other element."""
    from . import stage as G
    st = G.Stage()
    st.add(kind, t0, args, id=ident, pos=pos, scale=scale, edge=edge, float_=float_, anim=anim, enter="pop", z=z)
    e = st.params()["elements"][0]
    if t1 is not None:
        e["t1"] = float(t1)
        e["exit"] = "fade"
    return e


def _add_cue(shot: Dict[str, Any], t: float, name: str) -> None:
    cues = shot.setdefault("cues", [])
    if cues and isinstance(cues[0], dict):
        cues.append({"t": float(t), "name": name})
    else:
        cues.append((float(t), name))


def _stage_at(plan, t: float) -> Optional[Dict[str, Any]]:
    for s in plan.shots:
        if _kind(s) == "stage" and float(s["start"]) - 1e-6 <= t < float(s["end"]):
            return s
    return None


def _add_marker(plan, t: float, scene: Any) -> Dict[str, Any]:
    _, hi = _plan_span(plan)
    m = {"layer": "retention.lay_rehook", "start": float(t), "end": min(float(t) + REHOOK_S, hi) if hi > t else float(t) + REHOOK_S,
         "scene": scene, "params": {"style": "wipe"}, "full_frame": False, "cues": [(float(t), "rehook")]}
    plan.shots.append(m)
    return m


def _fix_rehooks(plan, scenes, fixed, left) -> List[int]:
    lo, hi = _plan_span(plan)
    q_idx, _, _ = opening_question(scenes)
    done: List[float] = [lo]
    done.extend(_rehook_times(plan))
    used: List[int] = []
    for i, sc in enumerate(scenes):
        text = str(sc.get("text") or "")
        turns = _scene_turns(text)
        a, b = float(sc.get("start", 0) or 0), float(sc.get("end", 0) or 0)
        _, a_idx, _ = opening_question(scenes)
        if not turns and i != q_idx and i != a_idx:
            continue
        pos, sent, why = turns[0] if turns else (text.find(next((s for _, s in _sentences(text) if s.endswith("?")), "")), "", "question")
        if not sent:
            sent = next((s for _, s in _sentences(text) if s.endswith("?")), "") or (_sentences(text)[0][1] if _sentences(text) else "")
            if not sent:
                continue
        t = a + (max(0, pos) / max(1, len(text))) * (b - a)
        if i == q_idx:
            why = "opening question"
        elif i == a_idx and not turns:
            why = "answer line"
        near = min((abs(t - d) for d in done), default=1e9)
        stage = _stage_at(plan, t)
        words = _question_words(sent) if i == q_idx else _first_words(sent)
        already = any(str(e.get("id", "")) == f"rh_big{i}" for s in plan.shots if _kind(s) == "stage"
                      for e in (s.get("params") or {}).get("elements") or [])
        if t - lo >= 1.0 and near >= MIN_REHOOK_GAP_S and not any(abs(float(s["start"]) - t) < 0.7 for s in plan.shots
                                                                     if s.get("layer") == "retention.lay_rehook"):
            _add_marker(plan, t, sc.get("scene_no", i + 1))
            done.append(t)
            _fx(fixed, "rehook", t, sc.get("scene_no", i + 1), f"{why}: {sent[:60]}")
            used.append(i)
            marked = True
        else:
            marked = False
            if t - lo >= 1.0 and i != q_idx:
                continue                     # too close to the last re-hook: no second flash, no second big type
        if stage is not None and words and not already and (marked or i == q_idx) and i != _a_of(scenes):
            rel = t - float(stage["start"])
            dur = float(stage["end"]) - float(stage["start"])
            if rel < dur - 0.5:
                els = stage.setdefault("params", {}).setdefault("elements", [])
                z = max([int(e.get("z", 0)) for e in els] or [0]) + 1
                # the opening question stays up until its own line ends (no empty stage before the next line's picture)
                hold = max(BIG_TYPE_S, b - t) if i == q_idx else BIG_TYPE_S
                _wipe(els, rel, min(dur, rel + hold) - rel)
                els.append(_make_element("big_type", {"text": words}, rel, min(dur, rel + hold), z, f"rh_big{i}", anim=1.0))
                _add_cue(stage, t, "rehook")
                _fx(fixed, "rehook_big_type", t, sc.get("scene_no", i + 1), f"big type '{words}' on the turn line")
    # forced re-hooks: 90 s without any
    for _ in range(40):
        marks = sorted([lo] + _rehook_times(plan) + [hi])
        gap = next(((x, y) for x, y in zip(marks, marks[1:]) if y - x > REHOOK_MAX_S), None)
        if gap is None:
            break
        x, y = gap
        cand = [float(sc["start"]) for sc in scenes if x + 30.0 <= float(sc.get("start", 0) or 0) <= min(y - 5.0, x + REHOOK_MAX_S - 2.0)]
        if not cand:
            left.append({"kind": "no_rehook", "start": x, "scene": None, "why": "no scene start in range for a wipe"})
            break
        t = min(cand, key=lambda c: abs(c - (x + 75.0)))
        i = _scene_index_at(scenes, t)
        _add_marker(plan, t, scenes[i].get("scene_no", i + 1))
        _fx(fixed, "rehook_forced", t, scenes[i].get("scene_no", i + 1), f"{y - x:.0f}s without a turn line: wipe, no words")
    plan.shots.sort(key=lambda s: float(s["start"]))
    return used


def _key_noun_phrase(text: str) -> str:
    caps = re.findall(r"(?:[A-Z][\w\-']*)(?:\s+(?:[A-Z][\w\-']*|\d+))*", text)
    caps = [c for c in caps if c.split()[0].lower() not in _STOP or len(c.split()) > 1]
    if caps:
        return max(caps, key=lambda c: (len(c.split()), len(c)))
    ws = list(_WORD.finditer(text))
    best, run = (None, None), None
    for m in ws:
        if m.group(0).lower() in _STOP:
            run = None
            continue
        run = (run[0], m.end()) if run else (m.start(), m.end())
        if best[0] is None or (run[1] - run[0]) > (best[1] - best[0]):
            best = run
    if best[0] is None:
        return ""
    chunk = text[best[0]:best[1]]
    return " ".join(chunk.split()[:3]) if len(chunk.split()) > 3 else chunk


def _fix_stage_idle(plan, scenes, fixed, left) -> None:
    from . import stage as G
    for s in [x for x in plan.shots if _kind(x) == "stage"]:
        for _ in range(12):
            t0 = float(s["start"])
            ev = sorted(set(_stage_events(s) + [float(s["end"])]))
            gap = next(((a, b) for a, b in zip(ev, ev[1:]) if b - a > MAX_SAME_S + 1e-6), None)
            if gap is None:
                break
            a, b = gap
            t = a + 6.0                                       # absolute
            rel = t - t0
            els = [e for e in (s.get("params") or {}).get("elements") or []
                   if e.get("keys") and float(e["t0"]) <= rel and (e.get("t1") is None or float(e["t1"]) > rel)]
            sc_i = _scene_index_at(scenes, t)
            scn = scenes[sc_i].get("scene_no", sc_i + 1) if sc_i >= 0 else s.get("scene")
            if els:
                e = min(els, key=lambda x: float(x["t0"]))
                x, y, sc = G._key_at(e["keys"], rel)
                first = float(e["keys"][0][3])
                ns = sc * 1.08 if sc <= first * 1.04 else sc / 1.08
                e["keys"].append([float(rel), float(x), float(y), float(ns), 1.4])
                _fx(fixed, "stage_move", t, scn, f"nothing new on stage for {b - a:.1f}s: {e.get('kind')} glides")
            else:
                text = str(scenes[sc_i].get("text") or "") if sc_i >= 0 else ""
                phrase = _key_noun_phrase(text)
                if not phrase:
                    left.append({"kind": "stage_idle", "start": a, "scene": scn, "why": "empty stage and no key phrase"})
                    break
                els_all = s.setdefault("params", {}).setdefault("elements", [])
                z = max([int(e.get("z", 0)) for e in els_all] or [0]) + 1
                els_all.append(_make_element("text", {"text": phrase, "size": 64}, rel, min(float(s["end"]) - t0, rel + 3.0), z,
                                             f"rh_text{len(els_all)}"))
                _fx(fixed, "stage_text", t, scn, f"empty stage for {b - a:.1f}s: key phrase '{phrase}'")


def _fix_callback(plan, scenes, fixed, left) -> None:
    q, a_idx, _ = opening_question(scenes)
    if q < 0 or a_idx < 0:
        return
    a0, a1 = float(scenes[a_idx]["start"]), float(scenes[a_idx]["end"])
    lo, _ = _plan_span(plan)
    if a0 - lo <= OPEN_WINDOW_S or _has_callback(plan, a0, a1) is not False:
        return
    scn = scenes[a_idx].get("scene_no", a_idx + 1)
    el, _st = _callback_target(plan)
    if el is not None:
        stage = _stage_at(plan, a0 + 0.2)
        if stage is not None:
            rel = max(0.0, a0 - float(stage["start"])) + 0.2
            dur = float(stage["end"]) - float(stage["start"])
            els = stage.setdefault("params", {}).setdefault("elements", [])
            z = max([int(e.get("z", 0)) for e in els] or [0]) + 1
            _wipe(els, rel, min(dur, rel + 3.5) - rel)
            ne = _make_element(el["kind"], dict(el.get("args") or {}), rel, min(dur, rel + 3.5), z, f"rh_cb{a_idx}",
                               pos=(640.0, 380.0), scale=0.85, edge=bool(el.get("edge")), float_=True, anim=float(el.get("anim", 0.0)))
            els.append(ne)
            stage["callback"] = True
            _add_cue(stage, a0 + 0.2, "callback")
            _fx(fixed, "callback", a0, scn, f"answer line: the opening's {el['kind']} comes back")
            return
    fo = _first_footage(plan)
    if fo is not None:
        tgt = next((s for s in _base(plan) if _kind(s) == "footage" and float(s["start"]) - 1e-6 <= a0 < float(s["end"]) - 2.5), None)
        if tgt is not None:
            a, b = float(tgt["start"]), float(tgt["end"])
            cut = max(a, a0) + 2.0
            head = dict(tgt, queries=list(tgt.get("queries") or []), end=max(a0, a))
            call = dict(tgt, queries=list(fo["queries"]), start=max(a0, a), end=cut, callback=True)
            tail = dict(tgt, queries=list(tgt.get("queries") or []), start=cut)
            parts = [p for p in (head, call, tail) if float(p["end"]) - float(p["start"]) > 0.05]
            idx = plan.shots.index(tgt)
            plan.shots[idx:idx + 1] = parts
            _fx(fixed, "callback", a0, scn, "answer line: the opening's footage comes back")
            return
    left.append({"kind": "no_callback", "start": a0, "scene": scn, "why": "no stage or footage slot at the answer line to host it"})


def _use_tuned_limits() -> None:
    """This channel's limits, tuned from its own retention data (aviation/retention_import.py); the defaults without any."""
    try:
        from . import retention_import as RI
        lim = RI.limits()
    except Exception:
        return
    g = globals()
    for k, v in lim.items():
        if k in g:
            g[k] = float(v)


def apply(plan, scenes: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    _use_tuned_limits()
    fixed: List[Dict[str, Any]] = []
    left: List[Dict[str, Any]] = []
    _fix_long_cards(plan, fixed, left)
    _fix_footage_pace(plan, fixed)
    _fix_rehooks(plan, scenes, fixed, left)
    _fix_callback(plan, scenes, fixed, left)
    _fix_stage_idle(plan, scenes, fixed, left)
    plan.shots.sort(key=lambda s: float(s["start"]))
    for it in check(plan, scenes):
        left.append({"kind": it["kind"], "start": it["start"], "scene": it["scene"], "why": it["detail"]})
    return {"fixed": fixed, "left": left, "turn_lines": turn_lines(scenes)}


# ------------------------------------------------------------------------------------------------------------ the wipe
def lay_rehook(t: float, dur: float, params: Optional[Dict[str, Any]] = None) -> Optional[Image.Image]:
    """A quick diagonal wipe band (white core, yellow edges) sweeping left to right; style 'flash' is a soft full-frame pulse.
    Shared card contract: (t, dur, params) -> RGBA W x H, None once it is over."""
    p = params or {}
    d = max(float(dur or REHOOK_S), 1e-3)
    if t < 0 or t >= d:
        return None
    k = t / d
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    if str(p.get("style", "wipe")) == "flash":
        a = int(150 * math.sin(math.pi * k) ** 2)
        im.paste((255, 244, 200, a), (0, 0, W, H))
        return im
    ease = k * k * (3 - 2 * k)
    width = 300.0
    lean = 0.35 * H                                      # how far the band leans over the frame height
    x = -width - lean + ease * (W + 2 * width + 2 * lean)
    fade = min(1.0, k * 6.0, (1 - k) * 4.0)
    d_ = ImageDraw.Draw(im)
    bands = ((1.0, (250, 190, 40)), (0.72, (255, 226, 110)), (0.40, (255, 255, 255)))
    for frac, col in bands:
        w = width * frac
        cx = x + width / 2
        poly = [(cx - w / 2 + lean, 0), (cx + w / 2 + lean, 0), (cx + w / 2 - lean, H), (cx - w / 2 - lean, H)]
        d_.polygon(poly, fill=col + (int(230 * fade),))
    return im.filter(ImageFilter.GaussianBlur(2))
