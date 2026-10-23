"""Authoring of one board beat: key phrases, cards, arrows, chips, headers, captions, clears and the narrator, then the gate (dry build, drop what does not fit)
and the static-time repair. Every cue is anchored on a narration word of the beat (anchor {"index": k}); nothing is placed by a guessed time."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..board.cues import Cue
from ..board.dry import dry_build
from . import lexicon as LX
from .options import DirectorOptions
from .segment import Sent, norm

CARD_SLOTS = ("C3", "C4", "C1", "C2")
POSE_BY_LABEL = {"hook": "surprise", "question": "think", "twist": "surprise", "conclusion": "idle"}


@dataclass
class Phrase:
    text: str
    first: int                 # index (global word index) of its first word
    last: int
    tokens: List[str]


@dataclass
class BoardResult:
    cues: List[Cue]
    dropped: List[Dict[str, str]] = field(default_factory=list)
    phrases: List[Dict[str, Any]] = field(default_factory=list)
    metaphor_uses: List[Dict[str, str]] = field(default_factory=list)
    repairs: List[str] = field(default_factory=list)
    events: List[float] = field(default_factory=list)
    still_gap_s: float = 0.0
    still_gap_all_s: float = 0.0      # the same board measured with every change counted
    still_gap_strict_s: float = 0.0   # ... and with only meaningful changes counted
    last_pose: str = "idle"
    peak_occupancy: float = 0.0                       # the largest share of the content area covered by elements on screen together (report only)
    used_extra: set = field(default_factory=set)      # word indices shown by headers and captions (cards are in `phrases`)
    problems: List[str] = field(default_factory=list)
    subject: str = ""
    authored: List[Any] = field(default_factory=list)  # the cues as authored, before the layout gate dropped any (the rescue needs the text of what was lost)
    rescued: List[Dict[str, Any]] = field(default_factory=list)   # text the gate dropped (or a sentence that never got any) and what was done about it
    lost: List[Dict[str, Any]] = field(default_factory=list)      # text that could not be kept, with the reason: never silent


def _disp(tok: str, cased: Dict[str, str]) -> str:
    return cased.get(tok, "I" if tok == "i" else tok)


def _weight(tok: str, cased: Dict[str, str], table: Dict[str, str]) -> float:
    if tok in LX.LEADING_OK:
        return 1.0
    if tok in LX.STOP or tok in LX.WEAK:
        return 0.4
    w = 2.0 + min(len(tok), 10) / 5.0
    if any(c.isdigit() for c in tok):
        w += 3.0
    if tok in cased:
        w += 2.0
    if tok in table:
        w += 1.5
    return w


def _clauses(idxs: Sequence[int], words, breaks: set) -> List[List[int]]:
    """Split a sentence's word indices at clause ends (script punctuation or pauses) and before connector words (but, so, because, which, ...)."""
    out: List[List[int]] = []
    cur: List[int] = []
    for k, g in enumerate(idxs):
        if cur and (norm(words[g][0]) in LX.SOFT_BREAK or g != cur[-1] + 1):       # a gap in the indices (words already used elsewhere) also ends a clause: a phrase is always a contiguous quote
            out.append(cur)
            cur = []
        cur.append(g)
        if g in breaks:
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


def best_phrases(idxs: Sequence[int], words, cased: Dict[str, str], table: Dict[str, str], breaks: set, *, k: int = 2, max_words: int = 8, fit=None,
                 min_score: float = 5.0, min_words: int = 1, strict_edges: bool = False, require_clause_end: bool = False) -> List[Phrase]:
    """Up to k phrases, each the best contiguous quote of the narration inside one clause: 2 to max_words words, never starting or ending on a function or weak word, containing a
    content word, scored by content weight (+2 when it begins and +2 when it ends with its clause, a complete thought). `fit(text)` must accept the text (it has to fit its card).
    A single word is allowed only if it is a number, a name from the script or a metaphor keyword."""
    cands: List[Tuple[float, int, Phrase]] = []
    for ci, cl in enumerate(_clauses(idxs, words, breaks)):
        toks = [norm(words[g][0]) for g in cl]
        best = None
        for i in range(len(cl)):
            if (toks[i] in LX.STOP or toks[i] in LX.WEAK or not toks[i]) and not (not strict_edges and toks[i] in LX.LEADING_OK and i + 1 < len(cl)) and not (not strict_edges and toks[i] in LX.CLAUSE_START_OK and i == 0 and len(cl) >= 2):
                continue
            for j in range(i, min(len(cl), i + max_words)):
                if toks[j] in LX.STOP or toks[j] in LX.WEAK or not toks[j]:
                    continue
                n = j - i + 1
                run = toks[i:j + 1]
                if n < min_words or (toks[i] in LX.LEADING_OK and n < 2):
                    continue
                if require_clause_end and j != len(cl) - 1:
                    continue
                if j != len(cl) - 1 and (toks[j] in LX.DANGLING_END or (len(toks[j]) > 4 and toks[j].endswith("ly") and toks[j] not in cased and toks[j] not in table)):
                    continue            # it would stop in the middle of the clause on a word that needs what comes next ("... and officially", "right above")
                if j != len(cl) - 1 and toks[j + 1] not in LX.STOP:
                    continue            # a cut inside a clause falls before a function word ("founder died in 1994 | and ..."), never between two content words ("its eternal | leader")
                if n == 1 and not (any(c.isdigit() for c in run[0]) or run[0] in cased or run[0] in table):
                    continue
                sc = sum(_weight(t, cased, table) for t in run)
                sc += 2.0 * (i == 0) + 2.0 * (j == len(cl) - 1) - 0.2 * max(0, n - 5)
                text = " ".join(_disp(t, cased) for t in run)
                if fit is not None and not fit(text):
                    continue
                if best is None or sc > best[0] + 1e-9:
                    best = (sc, ci, Phrase(text, cl[i], cl[j], run))
        if best is not None and best[0] >= min_score:
            cands.append(best)
    cands.sort(key=lambda x: -x[0])
    chosen = sorted(cands[:k], key=lambda x: x[2].first)
    return [c[2] for c in chosen]


def key_phrase(idxs: Sequence[int], words, cased: Dict[str, str], table: Dict[str, str], breaks: Optional[set] = None, fit=None) -> Optional[Phrase]:
    got = best_phrases(idxs, words, cased, table, breaks or set(), k=1, fit=fit, min_score=3.0)
    return got[0] if got else None


def asset_for(tokens: Sequence[str], sent_tokens: Sequence[str], table: Dict[str, str]) -> Tuple[Optional[str], str]:
    for pool in (tokens, sent_tokens):
        for t in pool:
            if t in table:
                return table[t], t
    return None, ""


def role_for(tokens: Sequence[str], roles: Dict[str, str]) -> Tuple[str, str]:
    for t in tokens:
        if t in roles:
            return roles[t], t
    if any(t in LX.LOSS for t in tokens):
        return "red", next(t for t in tokens if t in LX.LOSS)
    if any(t in LX.GAIN for t in tokens):
        return "green", next(t for t in tokens if t in LX.GAIN)
    return "blue", ""


def _card_fit(has_icon: bool):
    from ..board import layout as LY

    def ok(text: str) -> bool:
        w = LY.DEFAULT_SIZE["card"][0] - 2 * LY.CARD_PAD - ((LY.CARD_ICON_PX + LY.CARD_ICON_GAP) if has_icon else 0)
        return LY.fit_text(text, w, LY.DEFAULT_SIZE["card"][1] - 24 - LY.CARD_PAD, "body") is not None
    return ok


def _header_fit(text: str) -> bool:
    from ..board import layout as LY
    return LY.fit_text(text, LY.DEFAULT_SIZE["header"][0], 70, "body", 60, 44, 1) is not None


def _caption_fit(text: str) -> bool:
    from ..board import layout as LY
    return LY.fit_text(text, 1184 - 16, 70, "body", 52, 44, 1) is not None          # the full band at 44 px or larger: a director caption must stay legible


def author(beat_id: str, start: float, end: float, sents: Sequence[Sent], words, cased: Dict[str, str], opt: DirectorOptions, table: Dict[str, str], roles: Dict[str, str],
           narrator: str, carry_pose: str) -> BoardResult:
    """narrator: 'none' | 'only' | 'start' | 'mid' | 'end' (position in a run of board beats); carry_pose: the pose the previous beat ended with."""
    bw = [i for i, w in enumerate(words) if start - 1e-6 <= w[1] < end - 1e-6]
    pos = {g: k for k, g in enumerate(bw)}                       # global word index -> index inside the beat
    res = BoardResult([])
    cues: List[Cue] = []
    n = {"card": 0, "chip": 0, "header": 0, "caption": 0, "arrow": 0, "clear": 0}

    def cid(kind: str) -> str:
        n[kind] += 1
        return f"{beat_id}_{kind}{n[kind]}"

    header_used = 0
    pose_seq: List[Tuple[int, str]] = []
    explain_flip = 0
    for si, s in enumerate(sents):
        sidx = [g for g in s.widx if g in pos]
        if not sidx:
            continue
        stoks = [norm(words[g][0]) for g in sidx]
        label = s.label
        nw = len(sidx)
        kmax = 1 if nw < 8 else 2 if nw < 18 else 3
        # one card per phrase; the icon decides how much room the text has, so fit is checked with the icon the phrase would get
        def fit_any(text: str) -> bool:
            toks_ = [norm(w_) for w_ in text.split()]
            has_icon = asset_for(toks_, stoks, table)[0] is not None
            return _card_fit(has_icon)(text)
        parts = best_phrases(sidx, words, cased, table, s.breaks, k=kmax, fit=fit_any)
        if not parts:
            fb = key_phrase(sidx, words, cased, table, s.breaks, fit=fit_any)
            parts = [fb] if fb else []
        if len(parts) == 1 and nw >= 9:
            # one long thought: show it as two shorter cards that appear as the two halves are spoken (more readable, and a change every few seconds)
            half = nw // 2
            lo = [g for g in sidx[:half] if g not in range(parts[0].first, parts[0].last + 1)] or sidx[:half]
            first_half = best_phrases(sidx[:half + 1], words, cased, table, s.breaks, k=1, fit=fit_any, min_score=3.0)
            second_half = best_phrases(sidx[half:], words, cased, table, s.breaks, k=1, fit=fit_any, min_score=3.0)
            if first_half and second_half and first_half[0].last < second_half[0].first:
                parts = [first_half[0], second_half[0]]
        if label in ("hook", "twist") and header_used < 2:
            covered = {g for ph in parts for g in range(ph.first, ph.last + 1)}          # a header never repeats words a card of this sentence already shows
            hp = best_phrases([g for g in sidx if g not in covered], words, cased, table, s.breaks, k=1, max_words=3, fit=_header_fit, min_score=3.0)
            if hp:
                cues.append(Cue(cid("header"), "header", {"index": pos[hp[0].first]}, text=hp[0].text))
                res.used_extra.update(range(hp[0].first, hp[0].last + 1))
                header_used += 1
        # a long phrase (6 or more words) is shown in the caption band, revealed word by word as it is spoken, instead of as one card (readable, and a change on every word)
        long_ph = next((ph for ph in reversed(parts) if len(ph.tokens) >= 6 and _caption_fit(ph.text)), None) if len(parts) >= 1 else None
        long_cap = None
        if long_ph is not None and len(parts) >= 2:           # only when another card remains: a board never ends up with text in the band alone
            parts = [ph for ph in parts if ph is not long_ph]
            long_cap = long_ph
        card_ids = []
        for ph in parts[:3]:
            asset, kw = asset_for(ph.tokens, stoks, table)
            role, rkw = role_for(ph.tokens + stoks, roles)
            # cards go to the lower row first (C3, C4, then C1, C2): that is the height of the narrator's figure, so the speaker and what is said sit together
            c = Cue(cid("card"), "card", {"index": pos[ph.first]}, text=ph.text, role=role, asset=asset or "", slot=CARD_SLOTS[min(len(card_ids), 3)])
            cues.append(c)
            card_ids.append(c.id)
            res.phrases.append({"sentence": s.index, "label": label, "phrase": ph.text, "asset": asset, "keyword": kw, "role": role, "role_keyword": rkw, "first": ph.first, "last": ph.last})
            if asset:
                res.metaphor_uses.append({"keyword": kw, "asset": asset, "role": role, "beat": beat_id})
        if len(card_ids) >= 2:
            between = [norm(words[g][0]) for g in sidx if parts[0].last < g < parts[1].first]
            link = next((t for t in between if t in LX.CAUSE or t in LX.TWIST), None)
            clause_end = any(g in s.breaks for g in range(parts[0].last, parts[1].first))
            if link or clause_end:
                contrast = bool(link and link in LX.TWIST)
                cues.append(Cue(cid("arrow"), "arrow", {"index": pos[parts[1].first]}, offset_s=0.4, role="red" if contrast else "ink", src=card_ids[0], dst=card_ids[1]))
        if long_cap is not None:
            cues.append(Cue(cid("caption"), "caption", {"index": pos[long_cap.first]}, text=long_cap.text, role="blue"))
            res.used_extra.update(range(long_cap.first, long_cap.last + 1))
            res.phrases.append({"sentence": s.index, "label": label, "phrase": long_cap.text, "asset": None, "keyword": "", "role": "blue", "role_keyword": "", "first": long_cap.first, "last": long_cap.last, "as": "caption"})
        elif label not in ("twist", "conclusion") and nw >= 10:
            # the best leftover thought of a long sentence goes to the caption band, revealed word by word as it is spoken (a change on every word, no extra card)
            covered_all = {g for ph in parts for g in range(ph.first, ph.last + 1)}
            lp = best_phrases([g for g in sidx if g not in covered_all], words, cased, table, s.breaks, k=1, max_words=6, fit=_caption_fit, min_score=6.0, min_words=3)
            if lp and not any(lp[0].text.lower() in c.text.lower() for c in cues if c.kind == "card"):
                cues.append(Cue(cid("caption"), "caption", {"index": pos[lp[0].first]}, text=lp[0].text, role="blue"))
                res.used_extra.update(range(lp[0].first, lp[0].last + 1))
        if label in ("twist", "conclusion") and len(sidx) >= 3 and long_cap is None:
            last_clause = _clauses(sidx, words, s.breaks)[-1]
            cp = best_phrases(last_clause, words, cased, table, set(), k=1, max_words=6, fit=_caption_fit, min_score=3.0, min_words=3)
            if cp and not any(cp[0].text.lower() in c.text.lower() or c.text.lower() in cp[0].text.lower() for c in cues if c.kind == "card"):
                cues.append(Cue(cid("caption"), "caption", {"index": pos[cp[0].first]}, text=cp[0].text, role="blue"))
                res.used_extra.update(range(cp[0].first, cp[0].last + 1))
        # the chip comes after the captions: the caption band keeps its legible size, and a number that finds no free chip slot is still in its card's text
        num = next((g for g in sidx if any(ch.isdigit() for ch in words[g][0])), None)
        if num is not None:
            ctext = re.sub(r"[^\w,.%$]", "", words[num][0])
            nxt_w = norm(words[num + 1][0]) if num + 1 < len(words) else ""
            if nxt_w in ("million", "billion", "thousand", "trillion", "percent", "hundred"):          # "2 billion", "40 percent": the chip shows the whole quantity
                ctext = f"{ctext} {nxt_w}"
            cues.append(Cue(cid("chip"), "chip", {"index": pos[num]}, text=ctext))
        if si + 1 < len(sents):
            nxt = [g for g in sents[si + 1].widx if g in pos]
            if nxt:
                cues.append(Cue(cid("clear"), "clear", {"index": pos[nxt[0]]}))
        if narrator != "none":
            if label in POSE_BY_LABEL:
                pose = POSE_BY_LABEL[label]
            else:
                explain_flip += 1
                pose = "explain" if explain_flip % 2 else "point"
            pose_seq.append((pos[sidx[0]], pose))
    if narrator != "none":
        first_pose = carry_pose if narrator in ("mid", "end") else (pose_seq[0][1] if pose_seq else "idle")
        enter = "slide" if narrator in ("only", "start") else "none"
        cues.insert(0, Cue(f"{beat_id}_n_show", "narrator", {"index": 0}, params={"action": "show", "pose": first_pose, "side": "left", "scale": 1.0, "enter": enter}))
        cur = first_pose
        for k, (wi, pose) in enumerate(pose_seq):
            if wi > 0 and pose != cur:
                cues.append(Cue(f"{beat_id}_n_pose{k}", "narrator", {"index": wi}, params={"action": "pose", "pose": pose}))
                cur = pose
        res.last_pose = cur
        if narrator in ("only", "end"):
            late = [k for k, g in enumerate(bw) if words[g][1] <= end - 0.45]
            cues.append(Cue(f"{beat_id}_n_hide", "narrator", {"index": late[-1] if late else len(bw) - 1}, params={"action": "hide", "exit": "slide"}))
    first = next((p for p in res.phrases), None)
    res.subject = first["phrase"] if first else " ".join(norm(words[g][0]) for g in bw[:2])
    res.cues = cues
    return res


def gate(res: BoardResult, beat_id: str, start: float, end: float, words, opt: DirectorOptions, rounds: int = 4) -> List[Any]:
    """Dry-build the beat; drop every cue named in a problem (and what depended on it) until it is clean. Returns the final resolved cues."""
    resolved = []
    for _ in range(rounds):
        probs, resolved, _items = dry_build(res.cues, words, start, end, dissolve_s=opt.dissolve_s, fps=opt.fps, beat_id=beat_id)
        if not probs:
            return resolved
        bad = set()
        for p in probs:
            m = re.match(r"cue (\S+?):", p)
            if m:
                bad.add(m.group(1))
                res.dropped.append({"cue": m.group(1), "reason": p})
        if not bad:
            res.problems += probs
            return resolved
        res.cues = [c for c in res.cues if c.id not in bad]
        if any(c.id.endswith("_n_show") for c in res.cues) is False:      # the narrator could not be shown: drop its other cues too
            res.cues = [c for c in res.cues if c.kind != "narrator"]
    probs, resolved, _items = dry_build(res.cues, words, start, end, dissolve_s=opt.dissolve_s, fps=opt.fps, beat_id=beat_id)
    res.problems += probs
    return resolved


def change_events(resolved, start: float, end: float, strict: bool = False) -> List[float]:
    """Times of visible changes. strict=True counts only what a viewer takes as new CONTENT: the start of every element, title, typed line, picture, box, tag, chip, arrow, caption and card, and the
    beat start and end (a cut). It leaves out narrator entrances and pose changes, board clears and the per-word growth of a line that has already started (cosmetic or gradual)."""
    ev = [start, end]
    for r in resolved:
        if strict and r.cue.kind in ("narrator", "clear"):
            continue
        if r.onset_abs is not None and not r.problems:
            ev.append(r.onset_abs)
            if strict:
                continue
            if r.cue.kind in ("caption", "visual") and r.caption and r.caption.get("rung") in (1, 2):          # a words-mode caption changes on every word it reveals
                ev += [t + float(r.caption.get("offset_s") or 0.0) for t in r.caption.get("reveal_times_abs", [])]
            if r.cue.kind == "narrator" and (r.cue.params or {}).get("action") == "show" and (r.cue.params or {}).get("enter", "slide") == "slide":
                ev.append(r.onset_abs + 0.4)
    return sorted(set(round(t, 4) for t in ev))


def repair_still(res: BoardResult, beat_id: str, start: float, end: float, words, cased: Dict[str, str], opt: DirectorOptions, resolved, table: Dict[str, str],
                 roles: Dict[str, str], breaks: Optional[set] = None) -> List[Any]:
    """Close the longest still gap (more than max_still_s without a change): first with a card holding the key phrase of the words inside the gap (the narration's own words,
    icon and role from the same tables), else with a caption of the words around its middle. At most 3 repairs; what remains is reported."""
    bw = [i for i, w in enumerate(words) if start - 1e-6 <= w[1] < end - 1e-6]
    for rnd in range(3):
        ev = change_events(resolved, start, end)
        gaps = sorted(((b - a, a, b) for a, b in zip(ev, ev[1:])), reverse=True)
        res.still_gap_s = gaps[0][0]
        if gaps[0][0] <= opt.max_still_s:
            return resolved
        g, a, b = gaps[0]
        used = set()
        for ph in res.phrases:
            used.update(range(ph["first"], ph["last"] + 1))
        used.update(res.used_extra)
        inside_g = [gi for gi in bw if a + 0.6 <= words[gi][1] <= b - 0.5 and gi not in used]       # never repeat words a card or caption already shows
        if len(inside_g) < 2:
            # nothing new is being said inside the gap (a pause, or words already shown): a narrator pose change in the middle of the gap is the change, if the narrator is there
            if any(c.kind == "narrator" for c in res.cues):
                mid = (a + b) / 2.0
                anchor_k = max([k for k, gi in enumerate(bw) if words[gi][1] <= mid] or [0])
                shown = [c.params.get("pose") for c in res.cues if c.kind == "narrator" and c.params.get("action") in ("show", "pose")]
                cur = shown[-1] if shown else "idle"
                nxt = {"idle": "explain", "explain": "point", "point": "think", "think": "explain", "surprise": "explain", "shrug": "explain"}.get(cur, "explain")
                cid_ = f"{beat_id}_n_pose_r{rnd + 1}"
                res.cues.append(Cue(cid_, "narrator", {"index": anchor_k}, offset_s=max(0.0, mid - words[bw[anchor_k]][1]), params={"action": "pose", "pose": nxt}))
                n_drop = len(res.dropped)
                resolved = gate(res, beat_id, start, end, words, opt)
                if any(d["cue"] == cid_ for d in res.dropped[n_drop:]):
                    res.cues = [c for c in res.cues if c.id != cid_]
                    res.repairs.append(f"{cid_}: the narrator pose change did not fit the state machine and was dropped")
                    break
                res.repairs.append(f"{cid_}: narrator pose {cur} -> {nxt} in the middle of a {g:.1f} s gap with nothing new being said ({a:.2f} to {b:.2f} s)")
                continue
            break
        done = False
        for kind in ("card", "caption"):
            cid_ = f"{beat_id}_{kind}_r{rnd + 1}"
            if kind == "card":
                kp = key_phrase(inside_g, words, cased, table, breaks or set(), fit=_card_fit(False))
                if kp is None:
                    continue
                stoks = [norm(words[gi][0]) for gi in inside_g]
                asset, kw = asset_for(kp.tokens, stoks, table)
                role, rkw = role_for(kp.tokens + stoks, roles)
                new = Cue(cid_, "card", {"index": bw.index(kp.first)}, text=kp.text, role=role, asset=asset or "")
                said = kp.text
            else:
                cp = best_phrases(inside_g, words, cased, table, breaks or set(), k=1, max_words=6, fit=_caption_fit, min_score=3.0, min_words=2)
                if not cp:
                    continue
                new = Cue(cid_, "caption", {"index": bw.index(cp[0].first)}, text=cp[0].text, role="blue")
                said = new.text
                asset, kw, role = None, "", "blue"
            res.cues.append(new)
            n_drop = len(res.dropped)
            resolved = gate(res, beat_id, start, end, words, opt)
            if any(d["cue"] == cid_ for d in res.dropped[n_drop:]):
                res.repairs.append(f"{cid_}: the repair {kind} {said!r} did not fit and was dropped")
                res.cues = [c for c in res.cues if c.id != cid_]
                continue
            if kind == "card" and asset:
                res.metaphor_uses.append({"keyword": kw, "asset": asset, "role": role, "beat": beat_id})
            res.repairs.append(f"{cid_}: added {kind} {said!r} inside a {g:.1f} s still gap ({a:.2f} to {b:.2f} s)")
            done = True
            break
        if not done:
            break
    ev = change_events(resolved, start, end)
    res.still_gap_s = max(b - a for a, b in zip(ev, ev[1:]))
    res.still_gap_all_s = res.still_gap_s
    evs = change_events(resolved, start, end, strict=True)
    res.still_gap_strict_s = max(b - a for a, b in zip(evs, evs[1:]))
    return resolved
