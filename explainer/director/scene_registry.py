"""Scene, cast and environment continuity for cartoon beats (opt-in: DirectorOptions.continuity).

Without it every cartoon beat is drawn from scratch: its own set, its own cast, its own prop. With it a `SceneRegistry` walks the cartoon beats in order and decides, for each one,
CONTINUE (the same set, the same people standing in the same places, the props already on the stage) or NEW (a genuinely different place, time or subject). It never forces continuity:

  * a beat continues only when the previous cartoon beat ended a few seconds before it starts, no word of the beat changes the place or the time ("meanwhile", "years later", "back in",
    "the next day"), and no word names a different set than the one on stage;
  * a continued beat keeps the set and the cast; the light may change (day -> dusk on "evening", "hours later"; dusk -> day on "morning"), a new person named by the words may join, a
    prop named by the words is added, and a prop stays until the narration removes it ("burned", "destroyed"...);
  * the registry counts every composition (scene, light, cast, prop). A composition used in the last few cartoon beats, or the same scene too many beats in a row, is replaced by the
    next-best deterministic alternative: another cast arrangement, another valid set from the scores, the other light.

`plan_cartoon(...)` returns the decision as a plain dict; `compose_cartoon.author_cartoon(..., plan=that dict)` draws it. Pure and deterministic; nothing is random and nothing is read from disk."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import lexicon as LX

CONT_GAP_S = 3.0                 # the previous cartoon beat must end at most this long before the new one starts
RECENT_N = 3                     # a composition used in the last N cartoon beats is a repeat
MAX_SCENE_RUN = 4                # the same scene this many cartoon beats in a row is replaced when another set is valid
XS = (560, 1060, 1560)           # the places a figure can stand

HARD_PHRASES = ("years later", "decades later", "centuries later", "months later", "weeks later", "a year later", "years earlier", "years before", "years after", "decades after", "years ago",
                "the next day", "next day", "the next morning", "next morning", "the next year", "back in", "back at", "back to", "in the meantime")
HARD_WORDS = frozenset("meanwhile elsewhere".split())
DUSK = LX.DUSK_WORDS | frozenset("nightfall sundown midnight".split())
TIME_PASS = frozenset("later afterwards afterward eventually nightfall hours".split())      # soft: the same place, later in the day
DAWN = frozenset("morning dawn sunrise daybreak noon".split())
REMOVE_WORDS = frozenset("removed burned burnt destroyed vanished gone stolen seized sold abandoned lost".split())


@dataclass
class SceneRegistry:
    history: List[Dict[str, Any]] = field(default_factory=list)          # one record per cartoon beat, in order
    usage: Dict[str, int] = field(default_factory=dict)                  # "scene|light|cast|prop" -> times used
    boards: List[Dict[str, Any]] = field(default_factory=list)           # board beats noted (signature only)

    def last(self) -> Optional[Dict[str, Any]]:
        return self.history[-1] if self.history else None

    def note_board(self, beat_id: str, start: float, end: float, sig: Sequence[str] = ()) -> None:
        """A board beat's picture-layout signature; it counts for the report and ends a continuation only through the time gap it creates."""
        self.boards.append({"id": beat_id, "start": round(start, 3), "end": round(end, 3), "sig": list(sig)})

    def to_dict(self) -> Dict[str, Any]:
        return {"cartoon_beats": len(self.history), "continued": sum(1 for h in self.history if h["continued"]), "usage": dict(sorted(self.usage.items())),
                "boards": len(self.boards), "order": [h["id"] for h in self.history]}


# ---- word tables ----
def _tables(scenes2: bool):
    if scenes2:
        from . import lexicon_v2 as LV
        return LV.SET_WORDS_V2, LV.SCENE_WEAK_V2, LV.choose_scene_v2
    from .compose_cartoon import scene_for
    return LX.SET_WORDS, LX.SCENE_WEAK, scene_for


def ranked_scenes(tokens: Sequence[str], scenes2: bool = False) -> List[Tuple[str, int]]:
    """[(set, scene words said)] for the sets with at least one hit, best first (ties: said first, then table order)."""
    sets, weak, _c = _tables(scenes2)
    out = []
    for k, (name, ws) in enumerate(sets.items()):
        h = [i for i, t in enumerate(tokens) if t in ws and t not in weak]
        if scenes2:                                      # a word a contrast marker rejects ("instead of relying on agriculture") names no scene
            from . import lexicon_v2 as LV
            rej = LV.rejected_indices(tokens)
            h = [i for i in h if i not in rej]
        if h:
            if scenes2:                                  # the same weighting as choose_scene_v2: a people word counts half
                from . import lexicon_v2 as LV
                out.append((-LV.scene_score_v2(name, tokens)[0], h[0], k, name))
            else:
                out.append((-len(h), h[0], k, name))
    out.sort()
    return [(n, -c) for c, _f, _k, n in out]


def _fresh_cast(toks: Sequence[str], n_words: int, scenes2: bool, second: str) -> Tuple[List[List[Any]], Optional[List[Any]]]:
    """The cast the words call for when nothing is carried over (mirrors compose_cartoon.author_cartoon): ([[x, type]], crowd [kind, word] or None)."""
    if scenes2:
        from . import lexicon_v2 as LV
        chars = LV.characters_for(toks)
        crowd = LV.crowd_for(toks)
        if crowd is not None:
            lead = LV.lead_for_crowd(chars, crowd)
            return [[420, lead]], [crowd[0], crowd[1]]
        if chars:
            cast = [[XS[k], t] for k, (t, _i) in enumerate(chars[:3])]
            if len(cast) == 1 and n_words >= 10:
                cast.append([1060, second])
            return cast, None
    crowd_word = next((i for i, t in enumerate(toks) if t in LX.PEOPLE_WORDS), None)
    if crowd_word is not None and n_words >= 10:
        return [[430, "blue"], [900, second]], ["", crowd_word]
    cast = [[560, "blue"], [1060, second]]
    if n_words >= 14:
        cast.append([1560, "green" if second != "green" else "gold"])
    return cast, None


def _prop(toks: Sequence[str], scenes2: bool) -> Optional[Tuple[str, int]]:
    if scenes2:
        from . import lexicon_v2 as LV
        return LV.prop_for_v2(toks)
    return next(((p, i) for i, t in enumerate(toks) for p, ws in LX.PROP_WORDS.items() if t in ws), None)


def _prop_words(name: str, scenes2: bool):
    if scenes2:
        from . import lexicon_v2 as LV
        return LV.PROP_WORDS_V2.get(name, [])
    return LX.PROP_WORDS.get(name, [])


def _ident(scene, light, cast, crowd, prop) -> str:
    return f"{scene}|{light}|{','.join(f'{x}:{t}' for x, t in cast)}|{crowd[0] if crowd else '-'}|{prop or '-'}"


def _variants(st: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Other ways to stand the same people: the types reversed over the same places, rotated, a lone figure on the other side. Crowd layouts have one arrangement."""
    cast = st["cast"]
    if st["crowd"] is not None or not cast:
        return []
    out = []
    if len(cast) == 1:
        out.append([[1060 if cast[0][0] < 1000 else 560, cast[0][1]]])
    else:
        xs, ts = [c[0] for c in cast], [c[1] for c in cast]
        out.append([[x, t] for x, t in zip(xs, ts[::-1])])
        out.append([[x, t] for x, t in zip(xs, ts[1:] + ts[:1])])
    seen, res = {tuple(map(tuple, cast))}, []
    for c in out:
        k = tuple(map(tuple, c))
        if k not in seen:
            seen.add(k)
            res.append(dict(st, cast=c))
    return res


def plan_cartoon(reg: SceneRegistry, beat, tokens: Sequence[str], *, scenes2: bool = False, second: str = "gold", n_words: Optional[int] = None, variant: int = 0, hint: Optional[str] = None) -> Dict[str, Any]:
    """Decide the set, light, cast and prop of one cartoon beat and remember it. `beat` needs .id, .start, .end."""
    toks = list(tokens)
    n = n_words if n_words is not None else len(toks)
    text = " " + " ".join(toks) + " "
    reasons: List[str] = []
    _sets, _weak, chooser = _tables(scenes2)
    ranked = ranked_scenes(toks, scenes2)
    hits = dict(ranked)
    base = chooser(toks)
    want = base or hint
    prev = reg.last()
    hard = [p for p in HARD_PHRASES if f" {p} " in text] + sorted(w for w in HARD_WORDS if w in toks)
    dusk_w = any(t in DUSK for t in toks)
    pass_w = any(t in TIME_PASS for t in toks)
    dawn_w = any(t in DAWN for t in toks)

    cont = False
    if prev is None:
        reasons.append("first cartoon beat")
    elif beat.start - prev["end"] > CONT_GAP_S:
        reasons.append(f"new: {beat.start - prev['end']:.1f}s since the previous cartoon beat")
    elif hard:
        reasons.append("new: time or place change (" + ", ".join(hard) + ")")
    elif base and base != prev["scene"] and (base == "snowy_village" or hits.get(prev["scene"], 0) == 0 or hits.get(base, 0) - hits.get(prev["scene"], 0) >= 2):
        reasons.append(f"new: the words name {base}, not {prev['scene']}")
    else:
        cont = True
        reasons.append("continue: same place, people and time frame")

    fresh_cast, fresh_crowd = _fresh_cast(toks, n, scenes2, second)
    new_prop = _prop(toks, scenes2)
    if cont:
        scene = prev["scene"]
        light = prev["light"]
        if dusk_w or pass_w:
            light = "dusk"
        elif dawn_w:
            light = "day"
        if light != prev["light"]:
            reasons.append(f"light {prev['light']} -> {light} without rebuilding the set")
        cast, crowd = [list(c) for c in prev["cast"]], (list(prev["crowd"]) if prev["crowd"] else None)
        if fresh_crowd is not None and (crowd is None or crowd[0] != fresh_crowd[0]):
            cast, crowd = fresh_cast, fresh_crowd                                    # a new crowd arrives: the stage is rearranged around it, the set stays
            reasons.append("cast: a new crowd arrives")
        elif crowd is None and fresh_cast and scenes2:
            have = {t for _x, t in cast}
            free = [x for x in XS if x not in {c[0] for c in cast}]
            for _x0, t in fresh_cast:
                if t not in have and free and len(cast) < 3 and t not in ("blue", "gold", "green", "red"):
                    cast.append([free.pop(0), t])
                    have.add(t)
                    reasons.append(f"cast: {t} joins")
        prop_name = prev["prop"]
        if prop_name and any(t in REMOVE_WORDS for t in toks) and any(t in _prop_words(prop_name, scenes2) for t in toks):
            if new_prop is not None and new_prop[0] == prop_name:
                new_prop = None                                                      # the word that names the prop is the one that removes it
            prop_name = None
            reasons.append("prop removed by the narration")
        prop = (prop_name, 0) if prop_name else None
        if new_prop is not None and new_prop[0] != prop_name:
            prop = new_prop
            reasons.append(f"prop {new_prop[0]} added")
        elif prop is not None:
            reasons.append(f"prop {prop[0]} stays")
    else:
        scene = want
        light = "dusk" if dusk_w else "day"
        cast, crowd, prop = fresh_cast, fresh_crowd, new_prop

    # ---- repetition: the same composition in the last few cartoon beats, or the same scene too many times in a row ----
    st = {"scene": scene, "light": light, "cast": cast, "crowd": crowd, "prop": prop[0] if prop else None}
    recent = [h["ident"] for h in reg.history[-RECENT_N:]]
    run = 0
    for h in reversed(reg.history):
        if h["scene"] == scene:
            run += 1
        else:
            break

    def bad(c):
        return _ident(c["scene"], c["light"], c["cast"], c["crowd"], c["prop"]) in recent or (run >= MAX_SCENE_RUN and c["scene"] == (prev or {}).get("scene"))

    if scene is not None and bad(st):
        arr = _variants(st)
        alts = [dict(st, scene=a) for a, _h in ranked if a != scene]
        flips = [dict(st, light="day" if light == "dusk" else "dusk")]
        order = (alts + arr + flips) if not cont else (arr + flips + alts)
        pick = next((c for c in order if not bad(c)), None)
        if pick is None and arr:
            pick = next((dict(c, light=f["light"]) for c in arr for f in flips if not bad(dict(c, light=f["light"]))), None)
        if pick is not None:
            what = "scene" if pick["scene"] != scene else ("light" if pick["light"] != light else "cast arrangement")
            reasons.append(f"repeat avoided: another {what}")
            if pick["scene"] != scene:
                cont = False
            st = pick
            scene, light, cast, crowd = st["scene"], st["light"], st["cast"], st["crowd"]
            if st["prop"] != (prop[0] if prop else None):
                prop = (st["prop"], 0) if st["prop"] else None
        else:
            reasons.append("repeat kept: no other valid composition")

    ident = _ident(scene, light, cast, crowd, prop[0] if prop else None)
    reg.history.append({"id": beat.id, "start": beat.start, "end": beat.end, "scene": scene, "light": light, "cast": [list(c) for c in cast], "crowd": list(crowd) if crowd else None,
                        "prop": prop[0] if prop else None, "ident": ident, "continued": cont})
    key = f"{scene}|{light}|{','.join(t for _x, t in cast)}|{prop[0] if prop else '-'}"
    reg.usage[key] = reg.usage.get(key, 0) + 1
    return {"scene": scene, "light": light, "cast": [list(c) for c in cast], "crowd": list(crowd) if crowd else None, "prop": list(prop) if prop else None,
            "props": [prop[0]] if prop else [], "continued": cont, "reasons": reasons, "ident": ident}
