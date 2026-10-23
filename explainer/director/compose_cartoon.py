"""Cartoon beat authoring (Phase 7, opt-in). A cartoon beat is a board clip drawn from the prebuilt cartoon kit: a scene set (chosen from the words the beat says), one to three cast
figures in colour roles, at most one prop, a row of small figures when the beat is about many people, and one word-by-word caption of the beat's best phrase. No narrator (the
reference shows none in cartoon shots). Every element appears on a word of the narration, spread over the beat so that something new arrives every couple of seconds; nothing is
drawn from words that are not spoken."""

from __future__ import annotations

from typing import Dict, List, Sequence

from ..board import styles as ST
from ..board.cues import Cue
from . import lexicon as LX
from .compose import BoardResult, Phrase, _caption_fit, best_phrases, role_for
from .options import DirectorOptions
from .segment import Sent, norm

STAGE_Y = 880
FIG_H = 420
POSE_BY_LABEL = {"hook": "surprise", "question": "think", "twist": "surprise", "conclusion": "idle"}


def scene_for(tokens: Sequence[str]) -> str:
    """The set whose words are said most in the beat (ties: the one said first, then the table order)."""
    best, key = "town", (0, 0)
    for k, (name, words) in enumerate(LX.SET_WORDS.items()):
        hits = [i for i, t in enumerate(tokens) if t in words]
        cand = (len(hits), -(hits[0] if hits else 10 ** 6))
        if hits and cand > key:
            best, key = name, cand
    return best


def scene_score(tokens: Sequence[str]) -> int:
    """How well a beat suits a cartoon: scene words plus people words."""
    return sum(1 for t in tokens if any(t in w for w in LX.SET_WORDS.values())) + 2 * sum(1 for t in tokens if t in LX.PEOPLE_WORDS)


def author_cartoon(beat_id: str, start: float, end: float, sents: Sequence[Sent], words, cased: Dict[str, str], opt: DirectorOptions, table, roles, variant: int = 0) -> BoardResult:
    bw = [i for i, w in enumerate(words) if start - 1e-6 <= w[1] < end - 1e-6]
    pos = {g: k for k, g in enumerate(bw)}
    toks = [norm(words[g][0]) for g in bw]
    res = BoardResult([])
    cues: List[Cue] = []
    name = scene_for(toks)
    tod = "dusk" if any(t in LX.DUSK_WORDS for t in toks) else "day"
    cues.append(Cue(f"{beat_id}_set1", "visual", {"index": 0}, pos=(0, 0), offset_s=0.0, params={"style": "set", "set": name, "tod": tod}))

    def at_fraction(f: float) -> int:
        return min(len(bw) - 1, int(f * len(bw)))

    # the words the cast reacts to: polarity of the beat (loss red, gain green) and the first sentence's label
    role_s, _kw = role_for(toks, roles)
    label = sents[0].label if sents else "explain"
    pose1 = POSE_BY_LABEL.get(label, "idle" if variant % 2 else "point")
    second = {"red": "red", "green": "green"}.get(role_s, "gold")
    # at most one prop, on the first word that suggests it
    prop = next(((p, i) for i, t in enumerate(toks) for p, ws in LX.PROP_WORDS.items() if t in ws), None)
    n_people = sum(1 for t in toks if t in LX.PEOPLE_WORDS)
    crowd_word = next((i for i, t in enumerate(toks) if t in LX.PEOPLE_WORDS), None)
    if crowd_word is not None and len(bw) >= 10:           # a beat about many people: two figures on the left, a row of small ones on the right
        layout = [(430, "blue", pose1, 0.0), (900, second, "idle" if pose1 != "idle" else "point", 0.25)]
    else:
        crowd_word = None
        layout = [(560, "blue", pose1, 0.0), (1060, second, "idle" if pose1 != "idle" else "point", 0.28)]
        if len(bw) >= 14:
            layout.append((1560, "green" if second != "green" else "gold", "idle", 0.5))
    if prop:
        side = 150 if variant % 2 == 0 else 1500
        pp = {"style": "prop", "prop": prop[0], "height": 300}
        cues.append(Cue(f"{beat_id}_prop1", "visual", {"index": prop[1]}, pos=(side, STAGE_Y - ST.measure_cartoon("prop", pp)["h"]), params=pp))
    for k, (x, role, pose, frac) in enumerate(layout):
        fp = {"style": "figure", "cast": role, "pose": pose, "kit": "a", "height": FIG_H, "flip": k == 1}
        cues.append(Cue(f"{beat_id}_fig{k + 1}", "visual", {"index": at_fraction(frac)}, role=role, pos=(x, STAGE_Y - ST.measure_cartoon("figure", fp)["h"]), params=fp))
    if crowd_word is not None:
        cp = {"style": "crowd", "n": 7, "height": 170, "seed": variant}
        cues.append(Cue(f"{beat_id}_crowd1", "visual", {"index": max(crowd_word, at_fraction(0.62))}, pos=(1260, STAGE_Y - ST.measure_cartoon("crowd", cp)["h"]), params=cp))
    # one caption: the best contiguous quote of the beat (word by word, as the narration is spoken)
    allidx = [g for s in sents for g in s.widx if g in pos]
    ends = {s.widx[-1] for s in sents if s.widx}
    brk = set().union(*[s.breaks for s in sents]) | ends if sents else ends
    got = best_phrases(allidx, words, cased, table, brk, k=1, max_words=8, fit=_caption_fit, min_score=3.0, min_words=2)
    if got:
        ph = got[0]
        cues.append(Cue(f"{beat_id}_caption1", "caption", {"index": pos[ph.first]}, text=ph.text, params={"mode": "words"}))
        res.phrases.append({"sentence": sents[0].index if sents else -1, "label": label, "phrase": ph.text, "asset": None, "keyword": "", "role": "ink", "role_keyword": "", "first": ph.first, "last": ph.last, "as": "caption"})
        res.used_extra.update(range(ph.first, ph.last + 1))
    res.subject = got[0].text if got else " ".join(toks[:2])
    res.cues = cues
    res.authored = list(cues)
    return res
