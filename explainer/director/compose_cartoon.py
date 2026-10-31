"""Cartoon beat authoring (Phase 7, opt-in). A cartoon beat is a board clip drawn from the prebuilt cartoon kit: a scene set (chosen from the words the beat says), one to three cast
figures in colour roles, at most one prop, a row of small figures when the beat is about many people, and one word-by-word caption of the beat's best phrase. No narrator (the
reference shows none in cartoon shots). Every element appears on a word of the narration, spread over the beat so that something new arrives every couple of seconds; nothing is
drawn from words that are not spoken."""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence

from ..board import styles as ST
from ..board.cues import Cue
from . import lexicon as LX
from .compose import BoardResult, Phrase, _caption_fit, best_phrases, role_for
from .options import DirectorOptions
from .segment import Sent, norm

STAGE_Y = 880
FIG_H = 420
POSE_BY_LABEL = {"hook": "surprise", "question": "think", "twist": "surprise", "conclusion": "idle"}


def _cartoon_caption_fit(text: str) -> bool:
    """A cartoon caption is read over a busy picture: it must fit one line at 48 px (the largest the caption slot draws: 52 never fits its 70 px box), not just 44."""
    from ..board import layout as LY
    return LY.fit_text(text, 1184 - 16, 70, "body", 52, 48, 1) is not None


def _caption_pos(text: str):
    """The caption sits centred in the sky of the set (a flat light colour behind dark lettering: high contrast, clear of the figures and the wooden floor), not on the ground band
    where the dark ink sat on brown planks. None (the usual caption slot) if the text cannot be measured."""
    try:
        from ..board import layout as LY
        from ..board import theme as T
        fit = LY.fit_text(text, 1184 - 16, 70, "body", 52, 44, 1)
        if fit is None:
            return None
        px, ln = fit
        w = int(T.tracked_width(T.font("body", px), ln[0], px * T.THEME.tracking_em)) + 17
        return ((1920 - w) // 2, 110)
    except Exception:
        return None


def scene_for(tokens: Sequence[str]) -> Optional[str]:
    """The set whose words are said most in the beat (ties: the one said first, then the table order), or None when the beat names no scene: there is no default set, because a wrong
    scene (a desert town for a story about a country) is worse than a board."""
    best, key = None, (0, 0)
    for k, (name, words) in enumerate(LX.SET_WORDS.items()):
        hits = [i for i, t in enumerate(tokens) if t in words and t not in LX.SCENE_WEAK]
        cand = (len(hits), -(hits[0] if hits else 10 ** 6))
        if hits and cand > key:
            best, key = name, cand
    return best


def _v2_ready() -> bool:
    """scenes2 needs the v2 pack: when it is missing or damaged the beat is authored exactly as with the flag off (never-stop)."""
    try:
        from ..cartoon import kit_v2
        return bool(kit_v2.install())
    except Exception:
        return False


def scene_score(tokens: Sequence[str], scenes2: bool = False) -> int:
    """How well a beat suits a cartoon: 0 when it names no scene; otherwise scene words plus people words. `scenes2` (default off) uses the v2 tables (more scenes, no default)."""
    if scenes2 and _v2_ready():
        from . import lexicon_v2 as LV
        if LV.choose_scene_v2(tokens) is None:
            return 0
        strong = LV.scene_strength_v2(tokens)
        people = sum(1 for t in tokens if t in LV.PEOPLE_V2)
        groups = LV.group_subjects(tokens) if people == 0 else 0     # a demonym or a collective is the cast of a beat that goes somewhere (see lexicon_v2.GROUP_NOUNS)
        return 0 if people == 0 and groups == 0 and strong < 2 else strong + 2 * people + groups
    if scene_for(tokens) is None:
        return 0
    strong = sum(1 for t in tokens if any(t in w for w in LX.SET_WORDS.values()) and t not in LX.SCENE_WEAK)
    people = sum(1 for t in tokens if t in LX.PEOPLE_WORDS)
    if people == 0 and strong < 2:          # figures need someone to be: a place word alone ("light cities glowing") stays a board
        return 0
    return strong + 2 * people


def _dangles(ph: Phrase, last_idx: int, ends: set, words) -> bool:
    """True when a caption would stop on a word that needs what follows: it ends the beat but not its sentence, and that last word is a function word, a preposition, or a verb in -ed
    that wants an object ("... safety among the", "Venetians turned"). A phrase that stops inside the beat is cut by best_phrases before a function word already."""
    if ph.last != last_idx or ph.last in ends:
        return False
    t = norm(words[ph.last][0])
    return t in LX.STOP or t in LX.WEAK or t in LX.DANGLING_END or (len(t) > 4 and (t.endswith("ed") or t.endswith("ly")))


def _complete_caption(allidx, words, cased, table, brk, ends, fit) -> Optional[Phrase]:
    """The best caption that is a finished thought: of the best phrase of each clause (up to four), the highest scoring one that does not end on a dangling word; when the only candidates
    dangle, the same text is re-chosen with the clause end of the beat treated as unfinished (the phrase stops before its trailing verb)."""
    if not allidx:
        return None
    last = allidx[-1]
    top = best_phrases(allidx, words, cased, table, brk, k=1, max_words=8, fit=fit, min_score=3.0, min_words=2)
    if top and not _dangles(top[0], last, ends, words):
        return top[0]                   # the usual choice, unchanged
    cands = best_phrases(allidx, words, cased, table, brk, k=4, max_words=8, fit=fit, min_score=3.0, min_words=2)
    ok = [p for p in cands if not _dangles(p, last, ends, words)]
    if ok:
        return max(ok, key=lambda p: len(p.tokens))
    if cands:                           # try the beat without its unfinished tail: the phrase that stops earlier in the same clause
        trimmed = [g for g in allidx if g < min(p.last for p in cands if _dangles(p, last, ends, words))]
        again = best_phrases(trimmed, words, cased, table, brk | {trimmed[-1]} if trimmed else brk, k=1, max_words=8, fit=fit, min_score=3.0, min_words=2) if trimmed else []
        return again[0] if again else None
    return None


def author_cartoon(beat_id: str, start: float, end: float, sents: Sequence[Sent], words, cased: Dict[str, str], opt: DirectorOptions, table, roles, variant: int = 0, scene: Optional[str] = None, plan: Optional[Dict] = None,
                   on_plate: bool = False) -> BoardResult:
    """`plan` (opt-in continuity, scene_registry.plan_cartoon): the set, light, cast, crowd and prop decided across beats; None = authored exactly as always.
    `on_plate`: the cast stands on a Flow picture of the place, so no library set is drawn and no stand-in figure is added beside the people the words name."""
    bw = [i for i, w in enumerate(words) if start - 1e-6 <= w[1] < end - 1e-6]
    pos = {g: k for k, g in enumerate(bw)}
    toks = [norm(words[g][0]) for g in bw]
    res = BoardResult([])
    cues: List[Cue] = []
    v2 = (bool(getattr(opt, "scenes2", False)) or on_plate) and _v2_ready()      # a cast on a picture is always the named characters (the kit's soldiers, merchants...), never the stand-in pair
    if v2:
        from . import lexicon_v2 as LV
        name = LV.choose_scene_v2(toks) or scene     # None when no word names a scene: then there is no set at all (no default)
    else:
        name = scene_for(toks) or "town"      # only reached for a beat the selection already judged to have a scene
    tod = "dusk" if any(t in LX.DUSK_WORDS for t in toks) else "day"
    if plan:
        name = plan.get("scene") or name
        tod = plan.get("light") or tod
    if v2 and name == "harbour" and LV.obstruction_for(toks) is not None:       # something made it hard for people to reach the place: the shallows (a ship aground on a sandbar, troops halted on the beach)
        from ..cartoon import kit_v2
        if kit_v2.has_set("shallows", tod):
            name = "shallows"
    if name is not None and not on_plate:
        cues.append(Cue(f"{beat_id}_set1", "visual", {"index": 0}, pos=(0, 0), offset_s=0.0, params={"style": "set", "set": name, "tod": tod}))

    def at_fraction(f: float) -> int:
        return min(len(bw) - 1, int(f * len(bw)))

    # the words the cast reacts to: polarity of the beat (loss red, gain green) and the first sentence's label
    role_s, _kw = role_for(toks, roles)
    label = sents[0].label if sents else "explain"
    pose1 = POSE_BY_LABEL.get(label, "idle" if variant % 2 else "point")
    second = {"red": "red", "green": "green"}.get(role_s, "gold")
    # at most one prop, on the first word that suggests it
    prop = LV.prop_for_v2(toks) if v2 else next(((p, i) for i, t in enumerate(toks) for p, ws in LX.PROP_WORDS.items() if t in ws), None)
    n_people = sum(1 for t in toks if t in LX.PEOPLE_WORDS)
    crowd_word = next((i for i, t in enumerate(toks) if t in LX.PEOPLE_WORDS), None)
    if crowd_word is not None and len(bw) >= 10:           # a beat about many people: two figures on the left, a row of small ones on the right
        layout = [(430, "blue", pose1, 0.0), (900, second, "idle" if pose1 != "idle" else "point", 0.25)]
    else:
        crowd_word = None
        layout = [(560, "blue", pose1, 0.0), (1060, second, "idle" if pose1 != "idle" else "point", 0.28)]
        if len(bw) >= 14:
            layout.append((1560, "green" if second != "green" else "gold", "idle", 0.5))
    chars = LV.characters_for(toks) if v2 else []
    crowd_kind = LV.crowd_for(toks) if v2 else None
    if v2 and crowd_kind is not None:                    # an army, a line of police, rebels: a leader on the left and a row of that character beside him
        lead_t = LV.lead_for_crowd(chars, crowd_kind)
        crowd_word = crowd_kind[1]
        layout = [] if on_plate and lead_t == "blue" else [(420, lead_t, pose1, 0.0)]      # on a picture the row stands alone unless the words name its leader
    elif v2 and chars:                                   # the people the words name stand on the stage: up to three, each when its word is spoken
        crowd_word = None
        xs = (560, 1060, 1560)
        layout = [(xs[k], t_, pose1 if k == 0 else ("idle" if pose1 != "idle" else "point"), 0.0 if k == 0 else 0.3 * k) for k, (t_, _i) in enumerate(chars[:3])]
        if len(layout) == 1 and len(bw) >= 10 and not on_plate:
            layout.append((1060, second, "idle" if pose1 != "idle" else "point", 0.28))
        if on_plate and len(layout) == 1 and variant % 2:          # one figure on a picture: not always at the same spot
            layout = [(1060, layout[0][1], layout[0][2], 0.0)]
    if plan:
        if plan.get("cast"):
            layout = [(x, t_, pose1 if k == 0 else ("idle" if pose1 != "idle" else "point"), layout[k][3] if k < len(layout) else 0.3 * k) for k, (x, t_) in enumerate(plan["cast"])]
        if "crowd" in plan:
            pc = plan["crowd"]
            crowd_kind = (pc[0], pc[1]) if pc and pc[0] and v2 else None
            crowd_word = pc[1] if pc else None
        if "prop" in plan:
            prop = tuple(plan["prop"]) if plan["prop"] else None
    if prop and v2:
        pp = {"style": "prop", "prop": prop[0], "height": LV.PROP_HEIGHT.get(prop[0], 260)}
        m = ST.measure_cartoon("prop", pp)
        if m:                                   # a wide picture goes where no figure stands; if neither side is free it is left out
            busy = [(x - 20, x + 230) for x, _r, _p, _f in layout]
            if crowd_word is not None:
                busy.append((780 if crowd_kind is not None else 1240, 1920))
            sides = [100, 1820 - m["w"]] if variant % 2 == 0 else [1820 - m["w"], 100]
            side = next((x for x in sides if all(x + m["w"] + 30 <= lo or x >= hi + 30 for lo, hi in busy)), None)
            if side is not None:
                cues.append(Cue(f"{beat_id}_prop1", "visual", {"index": prop[1]}, pos=(side, STAGE_Y - m["h"]), params=pp))
    elif prop:
        side = 150 if variant % 2 == 0 else 1500
        pp = {"style": "prop", "prop": prop[0], "height": 300}
        cues.append(Cue(f"{beat_id}_prop1", "visual", {"index": prop[1]}, pos=(side, STAGE_Y - ST.measure_cartoon("prop", pp)["h"]), params=pp))
    for k, (x, role, pose, frac) in enumerate(layout):
        fp = {"style": "figure", "cast": role, "pose": pose, "kit": "a", "height": FIG_H, "flip": k == 1}
        m_fig = ST.measure_cartoon("figure", fp)
        if plan and pose != "idle":                      # continuity: the body stays where the slot puts it; only the arms change (a sprite is placed by its opaque box, so correct for the pose's box)
            m_idle = ST.measure_cartoon("figure", {**fp, "pose": "idle"})
            x = x + (m_fig["ox"] - m_idle["ox"]) if m_idle else x
        cues.append(Cue(f"{beat_id}_fig{k + 1}", "visual", {"index": at_fraction(frac)}, role=role if role in ("blue", "green", "red", "gold") else "gold", pos=(x, STAGE_Y - m_fig["h"]), params=fp))
    if crowd_word is not None and v2 and crowd_kind is not None:
        shore = name in ("harbour", "shallows")                        # a row of troops on the shore, short enough to leave the ship in the water beside it in view
        cp = {"style": "crowd", "n": 5 if shore else 7, "height": 250, "seed": variant + (1000 if plan else 0), "kind": crowd_kind[0]}
        cues.append(Cue(f"{beat_id}_crowd1", "visual", {"index": max(crowd_word, at_fraction(0.2 if shore else 0.3))}, pos=(700 if shore else 820, STAGE_Y - ST.measure_cartoon("crowd", cp)["h"]), params=cp))
    elif crowd_word is not None:
        cp = {"style": "crowd", "n": 7, "height": 170, "seed": variant}
        cues.append(Cue(f"{beat_id}_crowd1", "visual", {"index": max(crowd_word, at_fraction(0.62))}, pos=(700 if name == "harbour" else 1260, STAGE_Y - ST.measure_cartoon("crowd", cp)["h"]), params=cp))      # the harbour set has its ship on the right: the crowd stands on the shore beside it, not under the hull
    # one caption: the best contiguous quote of the beat (word by word, as the narration is spoken)
    allidx = [g for s in sents for g in s.widx if g in pos]
    ends = {s.widx[-1] for s in sents if s.widx}
    brk = set().union(*[s.breaks for s in sents]) | ends if sents else ends
    one = _complete_caption(allidx, words, cased, table, brk, ends, _cartoon_caption_fit) or _complete_caption(allidx, words, cased, table, brk, ends, _caption_fit)
    got = [one] if one else []
    if got:
        ph = got[0]
        cues.append(Cue(f"{beat_id}_caption1", "caption", {"index": pos[ph.first]}, text=ph.text, pos=_caption_pos(ph.text), params={"mode": "words"}))
        res.phrases.append({"sentence": sents[0].index if sents else -1, "label": label, "phrase": ph.text, "asset": None, "keyword": "", "role": "ink", "role_keyword": "", "first": ph.first, "last": ph.last, "as": "caption"})
        res.used_extra.update(range(ph.first, ph.last + 1))
    res.subject = got[0].text if got else " ".join(toks[:2])
    res.cues = cues
    res.authored = list(cues)
    return res


def continuity_plan(registry, b, words, opt: DirectorOptions, roles, variant: int = 0) -> Dict:
    """The continuity decision for one cartoon beat (see scene_registry): the beat's tokens and cast colour are read exactly as author_cartoon reads them."""
    from .scene_registry import plan_cartoon
    bw = [i for i, w in enumerate(words) if b.start - 1e-6 <= w[1] < b.end - 1e-6]
    toks = [norm(words[g][0]) for g in bw]
    role_s, _kw = role_for(toks, roles)
    second = {"red": "red", "green": "green"}.get(role_s, "gold")
    return plan_cartoon(registry, b, toks, scenes2=bool(getattr(opt, "scenes2", False)) and _v2_ready(), second=second, n_words=len(bw), variant=variant, hint=b.scene_hint)
