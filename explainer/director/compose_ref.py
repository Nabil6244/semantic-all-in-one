"""Reference-style board authoring (schema v1.3). Same inputs and outputs as compose.author; the composition follows the reference frames: large picture tiles or rings with a one-word
label, labelled diagram boxes joined by a big arrow, a display title with a typed subtitle, a scroll for a question, and typed lines in a role colour, spread over the whole content
area and varied by what the sentence says. Every text is a contiguous quote of the narration (the words are the speaker's, never reworded)."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..board import styles as ST
from ..board.cues import Cue
from . import lexicon as LX
from .compose import (BoardResult, POSE_BY_LABEL, Phrase, _clauses, _disp, asset_for, best_phrases, key_phrase, role_for)
from .options import DirectorOptions
from .segment import Sent, norm

ICON_ROLE = {"icon:drop": "blue", "icon:coin": "gold", "icon:house": "gold", "icon:person": "blue", "icon:gear": "blue", "icon:document": "gold", "icon:clock": "blue",
             "icon:warning": "red", "prop:note": "gold", "prop:scale": "gold", "prop:magnifier": "blue", "prop:book": "blue", "prop:key": "gold", "prop:flag": "red",
             "prop:chest": "gold", "prop:bulb": "gold"}
RING_ROLE = {"red": "red", "green": "green"}        # tile ring: orange (gold) unless the sentence is about loss or gain
X0, X1 = 720, 1810
GENERIC = frozenset("year years time day days age century decade way thing things".split())      # real words, but a picture of a clock says nothing about the point


def _line_fit(width: int, px: int = 56, lines: int = 1):
    def ok(text: str) -> bool:
        return ST.measure("line", text, {"width": width, "px": px, "lines": lines}) is not None
    return ok


def author_ref(beat_id: str, start: float, end: float, sents: Sequence[Sent], words, cased: Dict[str, str], opt: DirectorOptions, table: Dict[str, str], roles: Dict[str, str],
               narrator: str, carry_pose: str, variant: int = 0) -> BoardResult:
    bw = [i for i, w in enumerate(words) if start - 1e-6 <= w[1] < end - 1e-6]
    pos = {g: k for k, g in enumerate(bw)}
    res = BoardResult([])
    cues: List[Cue] = []
    n: Dict[str, int] = {}

    def cid(kind: str) -> str:
        n[kind] = n.get(kind, 0) + 1
        return f"{beat_id}_{kind}{n[kind]}"

    def at(g: int) -> Dict[str, int]:
        return {"index": pos[g]}

    pose_seq: List[Tuple[int, str]] = []
    last_asset = [""]
    flip = variant
    explain_flip = 0
    for si, s in enumerate(sents):
        sidx = [g for g in s.widx if g in pos]
        if not sidx:
            continue
        stoks = [norm(words[g][0]) for g in sidx]
        label = s.label
        nw = len(sidx)
        role_s, role_kw = role_for(stoks, roles)
        ring = RING_ROLE.get(role_s, "gold")
        tint_role = role_s if role_s in ("red", "green") else None
        # concept tiles: the distinct picture keywords of the sentence, in the order they are spoken (the label is the spoken word itself)
        concepts: List[Tuple[int, str, str]] = []
        seen_assets = set()
        for g, t in zip(sidx, stoks):
            if t in table and table[t] not in seen_assets and t not in LX.STOP and t not in LX.WEAK and t not in GENERIC:
                seen_assets.add(table[t])
                concepts.append((g, t, table[t]))
        first_new = len(cues)
        concepts = concepts[:3]
        if len(concepts) > 1 or (concepts and concepts[0][2] != last_asset[0]):
            concepts = [c for c in concepts if c[2] != last_asset[0]] or concepts           # vary the picture from one sentence to the next when the sentence offers another
        last_asset[0] = concepts[0][2] if concepts else ""
        covered = set()
        used_text = set()

        def lines_for(width: int, k: int, px: int = 56, exclude=(), nlines: int = 1) -> List[Phrase]:
            pool = [g for g in sidx if g not in exclude]
            got = best_phrases(pool, words, cased, table, s.breaks, k=k, max_words=7, fit=_line_fit(width, px, nlines), min_score=5.0, min_words=2)
            if not got:
                fb = key_phrase(pool, words, cased, table, s.breaks, fit=_line_fit(width, px, nlines))
                got = [fb] if fb else []
            return got

        def add_line(ph: Phrase, x: int, y: int, width: int, last_red: bool = False, px: int = 56, center: bool = False, nlines: int = 1) -> int:
            tint = bool(last_red or tint_role)
            prm = {"style": "line", "width": width, "px": px, "tint": tint, "align": "center" if center else "", "lines": nlines, "sync": True}
            cues.append(Cue(cid("line"), "visual", at(ph.first), text=ph.text, role="red" if last_red else (tint_role or "ink"), pos=(x, y), cps=34.0, offset_s=0.0, params=prm))
            res.phrases.append({"sentence": s.index, "label": label, "phrase": ph.text, "asset": None, "keyword": "", "role": "red" if last_red else (tint_role or "ink"), "role_keyword": role_kw,
                                "first": ph.first, "last": ph.last, "as": "line"})
            covered.update(range(ph.first, ph.last + 1))
            m_ = ST.measure("line", ph.text, prm)
            return m_["h"] if m_ else 100

        def add_tile(c: Tuple[int, str, str], x: int, y: int, style: str = "tile", role: Optional[str] = None) -> None:
            g, t, asset = c
            lab = _disp(t, cased)
            prm = {"style": style}
            cues.append(Cue(cid("tile"), "visual", at(g), text=lab, role=role or (ring if style == "tile" else ICON_ROLE.get(asset, "blue")), asset=asset, pos=(x, y), params=prm))
            res.metaphor_uses.append({"keyword": t, "asset": asset, "role": ICON_ROLE.get(asset, "blue"), "beat": beat_id})
            res.phrases.append({"sentence": s.index, "label": label, "phrase": lab, "asset": asset, "keyword": t, "role": ring, "role_keyword": role_kw, "first": g, "last": g, "as": style})
            covered.add(g)

        two = best_phrases(sidx, words, cased, table, s.breaks, k=2, max_words=5, fit=_line_fit(560, 52), min_score=5.0, min_words=2)
        link = None
        if len(two) == 2:
            between = [norm(words[g][0]) for g in sidx if two[0].last < g < two[1].first]
            link = next((t for t in between if t in LX.CAUSE or t in LX.TWIST), None)
        layout = "split"
        tt_probe = best_phrases(sidx, words, cased, table, s.breaks, k=1, max_words=3, fit=lambda t: len(t) <= 22, min_score=5.0, min_words=2, strict_edges=True, require_clause_end=True) if label in ("hook", "twist") else []
        if label == "question":
            layout = "scroll"
        elif label in ("hook", "twist") and nw >= 6 and tt_probe and norm(tt_probe[0].text.split()[-1]) not in {"apart", "away", "up", "down", "out", "off", "back", "over", "again", "together"}:
            layout = "title"
        elif link is not None and len(two) == 2:
            layout = "flow"
        elif len(concepts) >= 2:
            layout = "tiles"
        # ---------------------------------------------------------------- layouts
        if layout == "scroll":
            q = best_phrases(sidx, words, cased, table, s.breaks, k=1, max_words=8, fit=lambda t: ST.measure("scroll", t, {}) is not None, min_score=4.0, min_words=2)
            if q:
                cues.append(Cue(cid("scroll"), "visual", at(q[0].first), text=q[0].text, role="gold", pos=(760, 210), params={"style": "scroll"}))
                res.phrases.append({"sentence": s.index, "label": label, "phrase": q[0].text, "asset": None, "keyword": "", "role": "ink", "role_keyword": "", "first": q[0].first, "last": q[0].last, "as": "scroll"})
                covered.update(range(q[0].first, q[0].last + 1))
                cues.append(Cue(cid("title"), "title", at(q[0].last), text="?", pos=(1700, 330)))
            if concepts:
                add_tile(concepts[0], 1180, 560, "circle")
            rest = lines_for(900, 1, 56, exclude=covered)
            if rest and not concepts:
                add_line(rest[0], 760, 600, 900)
        elif layout == "title":
            particles = {"apart", "away", "up", "down", "out", "off", "back", "over", "again", "together"}
            tt = best_phrases(sidx, words, cased, table, s.breaks, k=1, max_words=3, fit=lambda t: len(t) <= 22 and norm(t.split()[-1]) not in particles, min_score=5.0, min_words=2, strict_edges=True,
                              require_clause_end=True)
            if tt:
                cues.append(Cue(cid("title"), "title", at(tt[0].first), text=tt[0].text.upper(), pos=(1270, 250)))
                covered.update(range(tt[0].first, tt[0].last + 1))
                res.phrases.append({"sentence": s.index, "label": label, "phrase": tt[0].text, "asset": None, "keyword": "", "role": "yellow", "role_keyword": "", "first": tt[0].first, "last": tt[0].last, "as": "title"})
            sub = [p_ for p_ in lines_for(1000, 2, 64, nlines=2) if p_.text.lower() not in tt[0].text.lower() and tt[0].text.lower() not in p_.text.lower() or len(p_.text) > len(tt[0].text) + 6]
            yy = 390
            for j, ph in enumerate(sub[:2]):
                yy += add_line(ph, 770, yy, 1000, last_red=(j == len(sub[:2]) - 1 and label in ("twist", "conclusion")), center=True, px=64, nlines=2) + 40
            if concepts and yy + 10 + 350 <= 880:                  # a ring with its label needs about 350 px under the lines; without room the board stays title and lines
                add_tile(concepts[0], 1115, yy + 10, "circle")
        elif layout == "flow":
            a, b = two
            ra = "blue"
            idc = ra if not (label == "twist") else "gold"
            boxes_fit = lambda t: ST.measure("lite", t, {}) is not None
            cues.append(Cue(cid("box"), "visual", at(a.first), text=a.text, role="blue", pos=(740, 520), params={"style": "lite"}))
            mb = ST.measure("box", b.text, {})
            cues.append(Cue(cid("box"), "visual", at(b.first), text=b.text, role=("red" if link in LX.TWIST or tint_role == "red" else "blue"), pos=(min(1250, 1790 - mb["w"]), 190), params={"style": "box"}))
            ids = [c.id for c in cues[-2:]]
            cues.append(Cue(cid("arrow"), "arrow", at(b.first), offset_s=0.5, role="blue" if tint_role is None else tint_role, src=ids[0], dst=ids[1], params={"width": 16}))
            covered.update(range(a.first, a.last + 1))
            covered.update(range(b.first, b.last + 1))
            res.phrases.append({"sentence": s.index, "label": label, "phrase": a.text, "asset": None, "keyword": "", "role": "blue", "role_keyword": "", "first": a.first, "last": a.last, "as": "box"})
            res.phrases.append({"sentence": s.index, "label": label, "phrase": b.text, "asset": None, "keyword": "", "role": "blue", "role_keyword": "", "first": b.first, "last": b.last, "as": "box"})
            if concepts:
                add_tile(concepts[0], 1480, 560, "circle")
        elif layout == "tiles":
            m = len(concepts)
            x0 = X0 + (3 - m) * 195
            for j, c in enumerate(concepts):
                add_tile(c, x0 + j * 390, 120, "tile")
            yy = 580
            lf = lines_for(1100, 2, 64, exclude=covered)[:2]
            for j, ph in enumerate(lf):
                yy += add_line(ph, X0, yy, 1100, last_red=(label in ("twist", "conclusion") and j == len(lf) - 1), center=True, px=64) + 30
        elif not concepts and (flip + si) % 2 == 0 and nw >= 6:       # no picture to show: a cream scroll carries the main thought, a typed line adds the rest
            flip += 1
            q = best_phrases(sidx, words, cased, table, s.breaks, k=1, max_words=7, fit=lambda t: ST.measure("scroll", t, {}) is not None, min_score=5.0, min_words=2)
            if q:
                cues.append(Cue(cid("scroll"), "visual", at(q[0].first), text=q[0].text, role="gold", pos=(900, 230), params={"style": "scroll"}))
                res.phrases.append({"sentence": s.index, "label": label, "phrase": q[0].text, "asset": None, "keyword": "", "role": "ink", "role_keyword": "", "first": q[0].first, "last": q[0].last, "as": "scroll"})
                covered.update(range(q[0].first, q[0].last + 1))
                rest = lines_for(1000, 1, 68, exclude=covered, nlines=2)
                if rest:
                    add_line(rest[0], 800, 600, 1000, last_red=(label in ("twist", "conclusion")), px=68, center=True, nlines=2)
        else:   # split: one picture and typed lines, mirrored from one sentence to the next
            flip += 1
            vis_left = flip % 2 == 0
            lw = 660 if concepts else 1080
            px_ = 64 if concepts else 76
            nl = 2
            ph_list = lines_for(lw, 3 if nw >= 14 else 2 if nw >= 8 else 1, px_, nlines=nl)
            if concepts:
                add_tile(concepts[0], X0 + 20 if vis_left else 1430, 170, "circle" if flip % 3 == 0 else "tile")
            lx = 1090 if (concepts and vis_left) else 720
            yy = 190 if concepts else 230
            for j, ph in enumerate(ph_list):
                yy += add_line(ph, lx, yy, lw, last_red=(label in ("twist", "conclusion") and j == len(ph_list) - 1), px=px_, nlines=nl) + 40
        # centre the sentence's group of elements vertically on the board (the reference puts its content around mid-height, not at the top)
        grp = [c for c in cues[first_new:] if c.kind in ("visual", "title") and c.pos is not None]
        rects = []
        for c in grp:
            if c.kind == "title":
                rects.append((c.pos[0] - 380, c.pos[1] - 90, c.pos[0] + 380, c.pos[1] + 90))
            else:
                prm = c.params or {}
                m_ = ST.measure(prm.get("style", ""), c.text, prm, c.asset)
                if m_:
                    rects.append((c.pos[0], c.pos[1], c.pos[0] + m_["w"], c.pos[1] + m_["h"]))
        if rects:
            top, bot = min(r_[1] for r_ in rects), max(r_[3] for r_ in rects)
            dy = int(500 - (top + bot) / 2)
            dy = max(110 - top, min(dy, 880 - bot))
            if abs(dy) > 8:
                for c in grp:
                    c.pos = (c.pos[0], c.pos[1] + dy)
        # a quantity: a navy tag with the number and its noun (as "x3 income" in the reference) when there is room beside the lines, else the bottom chip below
        num_g = next((g for g in sidx if any(ch.isdigit() for ch in words[g][0])), None)
        if num_g is not None and layout in ("split", "title", "scroll") and not any(c.kind == "visual" and (c.params or {}).get("style") == "tag" for c in cues[first_new:]):
            nx = [norm(words[g][0]) for g in sidx if g > num_g][:2]
            take = [num_g] + [g for g in sidx if g > num_g][:1 if nx and nx[0] in ("million", "billion", "thousand", "percent", "hundred", "trillion") else 0]
            nxt2 = [g for g in sidx if g > take[-1]][:1]
            if nxt2 and norm(words[nxt2[0]][0]) not in LX.STOP and norm(words[nxt2[0]][0]) not in LX.WEAK:
                take.append(nxt2[0])
            ttext = " ".join(re.sub(r"[^\w,.%$]", "", words[g][0]) for g in take)
            cues.append(Cue(cid("tag"), "visual", at(num_g), text=ttext, role="blue", pos=(1380, 130), params={"style": "tag"}))
            covered.update(take)
            num_g = None
        # number: a big dark chip (year or quantity), after the picture elements, in the bottom strip
        num = num_g
        if num is not None:
            ctext = re.sub(r"[^\w,.%$]", "", words[num][0])
            nxt_w = norm(words[num + 1][0]) if num + 1 < len(words) else ""
            if nxt_w in ("million", "billion", "thousand", "trillion", "percent", "hundred"):
                ctext = f"{ctext} {nxt_w}"
            cues.append(Cue(cid("chip"), "chip", at(num), text=ctext, params={"px": 72}))
        if si + 1 < len(sents):
            nxt = [g for g in sents[si + 1].widx if g in pos]
            if nxt:
                cues.append(Cue(cid("clear"), "clear", at(nxt[0])))
        if narrator != "none":
            pose = POSE_BY_LABEL.get(label)
            if pose is None:
                explain_flip += 1
                pose = "explain" if explain_flip % 2 else "point"
            pose_seq.append((pos[sidx[0]], pose))
        res.used_extra.update(covered)
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
    res.authored = list(cues)
    return res


TEXT_KINDS = ("visual", "title", "caption", "card", "header")


def _shows_text(c: Cue) -> bool:
    return c.kind in TEXT_KINDS and bool((c.text or "").strip()) and (c.text or "").strip() != "?"


def _content(tok: str) -> bool:
    return bool(tok) and (any(ch.isdigit() for ch in tok) or (tok not in LX.STOP and tok not in LX.WEAK))


def rescue_text_ref(res: BoardResult, beat_id: str, start: float, end: float, sents: Sequence[Sent], words, cased: Dict[str, str], opt: DirectorOptions, table, resolved):
    """After the layout gate: every sentence of the board that says something (a content word and at least two words) must still show some of it. A sentence whose text cues were all
    dropped, or that never got a phrase, gets its best contiguous quote (relaxed thresholds, edges still on content words) as a typed line in a free place, else as a band caption. Every
    attempt goes through the same dry-build gate: a collision drops the attempt, never the gate. A dropped authored text cue of a sentence that kept other text is retried the same
    way (at most 2 per beat). Whatever cannot be kept is listed in `res.lost` with the reason."""
    from .compose import gate

    bw = [i for i, w in enumerate(words) if start - 1e-6 <= w[1] < end - 1e-6]
    pos = {g: k for k, g in enumerate(bw)}
    dropped_ids = {d["cue"] for d in res.dropped}
    lost_authored = [c for c in res.authored if c.id in dropped_ids and _shows_text(c) and c.kind in ("visual", "title") and len((c.text or "").split()) >= 2
                     and (c.params or {}).get("style") in ("line", "scroll", "box", "lite", None)]
    def spots(w: int, h: int) -> List[Tuple[int, int]]:
        out = []
        for y in range(860 - h, 110, -70):
            for x in range(X0, X1 - w + 1, 70):
                out.append((x, y))
        return out[:70] + [(x, y) for y in range(110, 860 - h, 70) for x in range(X0, X1 - w + 1, 70)][:70]
    def shown_words() -> set:
        got = set()
        for c in res.cues:
            if _shows_text(c) and "index" in (c.anchor or {}) and c.anchor["index"] < len(bw):
                a = bw[c.anchor["index"]]
                got.update(range(a, a + max(1, len((c.text or "").split()))))
        return got
    def try_place(ph: Phrase, why: str, sid: int) -> Optional[str]:
        k = len(res.rescued) + 1
        for (lw_, ln_, px_) in ((900, 1, 56), (560, 2, 56), (1080, 1, 48), (720, 3, 48)):
            if ST.measure("line", ph.text, {"width": lw_, "px": px_, "lines": ln_}) is None:
                continue
            mm = ST.measure("line", ph.text, {"width": lw_, "px": px_, "lines": ln_}) or {"h": 150}
            for (x, y) in spots(lw_, mm["h"]):
                cid_ = f"{beat_id}_rescue{k}_{x}_{y}"
                res.cues.append(Cue(cid_, "visual", {"index": pos[ph.first]}, text=ph.text, role="ink", pos=(x, y), cps=34.0, offset_s=0.0,
                                    params={"style": "line", "width": lw_, "px": px_, "lines": ln_, "tint": False, "sync": True}))
                n0 = len(res.dropped)
                gate(res, beat_id, start, end, words, opt)
                if any(d["cue"] == cid_ for d in res.dropped[n0:]):
                    res.cues = [c for c in res.cues if c.id != cid_]
                    continue
                res.used_extra.update(range(ph.first, ph.last + 1))
                res.phrases.append({"sentence": sid, "label": "rescue", "phrase": ph.text, "asset": None, "keyword": "", "role": "ink", "role_keyword": "", "first": ph.first, "last": ph.last, "as": "line"})
                return f"typed line at ({x}, {y}), width {lw_}"
        from .compose import _caption_fit
        if _caption_fit(ph.text):
            cid_ = f"{beat_id}_rescue{k}_cap"
            res.cues.append(Cue(cid_, "caption", {"index": pos[ph.first]}, text=ph.text, params={"mode": "words"}))
            n0 = len(res.dropped)
            gate(res, beat_id, start, end, words, opt)
            if any(d["cue"] == cid_ for d in res.dropped[n0:]):
                res.cues = [c for c in res.cues if c.id != cid_]
                return None
            res.used_extra.update(range(ph.first, ph.last + 1))
            res.phrases.append({"sentence": sid, "label": "rescue", "phrase": ph.text, "asset": None, "keyword": "", "role": "ink", "role_keyword": "", "first": ph.first, "last": ph.last, "as": "caption"})
            return "word-by-word caption in the band"
        return None
    def best_for(idxs, breaks) -> Optional[Phrase]:
        for (ms, mw, fit_w) in ((5.0, 2, 1080), (3.0, 2, 1080), (0.0, 1, 1080)):
            got = best_phrases(idxs, words, cased, table, breaks, k=1, max_words=7, fit=_line_fit(fit_w, 48, 2), min_score=ms, min_words=mw)
            if got:
                return got[0]
        return None
    n_resc = 0
    for s in sents:
        sidx = [g for g in s.widx if g in pos]
        toks = [norm(words[g][0]) for g in sidx]
        if len(sidx) < 2 or not any(_content(t) for t in toks):
            continue
        have = shown_words()
        if have & set(sidx):
            continue
        why = "every text cue of this sentence was dropped by the layout gate" if any(c.id in dropped_ids and c.anchor.get("index", -1) in [pos[g] for g in sidx] for c in res.authored) else "no phrase of this sentence qualified"
        ph = best_for(sidx, s.breaks | {sidx[-1]})
        if ph is None:
            res.lost.append({"sentence": s.index, "text": " ".join(toks), "reason": why + "; no contiguous quote with content words fits"})
            continue
        how = try_place(ph, why, s.index)
        if how:
            res.rescued.append({"sentence": s.index, "text": ph.text, "how": how, "why": why})
            res.repairs.append(f"{beat_id}: rescued {ph.text!r} ({how}): {why}")
            n_resc += 1
        else:
            res.lost.append({"sentence": s.index, "text": ph.text, "reason": why + "; no free place on the board for it (collision gate kept on)"})
    for c in lost_authored[:2]:
        if n_resc >= 4:
            break
        a = bw[c.anchor["index"]] if "index" in (c.anchor or {}) and c.anchor["index"] < len(bw) else None
        if a is None:
            continue
        sid = next((s.index for s in sents if a in s.widx), -1)
        ntok = len((c.text or "").split())
        last = min(a + ntok - 1, bw[-1])
        ph = Phrase(c.text, a, last, [norm(t) for t in c.text.split()])
        if any(r_["text"] == c.text for r_ in res.rescued) or (set(range(a, last + 1)) <= shown_words()):
            continue
        how = try_place(ph, "authored cue dropped", sid)
        if how:
            res.rescued.append({"sentence": sid, "text": c.text, "how": how, "why": f"the authored cue {c.id} collided and was dropped"})
            res.repairs.append(f"{beat_id}: rescued {c.text!r} ({how}): the authored cue {c.id} collided")
            n_resc += 1
        else:
            res.lost.append({"sentence": sid, "text": c.text, "reason": f"the authored cue {c.id} collided and nothing else fit (collision gate kept on)"})
    return resolved


def repair_still_ref(res: BoardResult, beat_id: str, start: float, end: float, words, cased, opt: DirectorOptions, resolved, table, roles, breaks: Optional[set] = None):
    """Close the longest still gap (more than max_still_s with no change) with something the narration says that no element shows yet: a picture tile for an unused keyword, else a typed
    line in a free place, else a band caption, else (when the narrator is on screen and nothing new is being said) a pose change. Candidate places are tried in order; the dry-build gate
    drops a cue that collides. At most 3 repairs; what remains is reported."""
    from .compose import change_events, gate

    bw = [i for i, w in enumerate(words) if start - 1e-6 <= w[1] < end - 1e-6]
    used_assets = {c.asset for c in res.cues if c.kind == "visual" and c.asset}
    def spots(w: int, h: int) -> List[Tuple[int, int]]:
        """Candidate top-left corners for an element of w x h in the content area, lower rows first (the upper rows are usually the busy ones); the layout gate rejects collisions."""
        out = []
        for y in range(860 - h, 110, -70):
            for x in range(X0, X1 - w + 1, 70):
                out.append((x, y))
        return out[:70]
    for rnd in range(3):
        ev = change_events(resolved, start, end, strict=True)
        gaps = sorted(((b - a, a, b) for a, b in zip(ev, ev[1:])), reverse=True)
        res.still_gap_s = gaps[0][0]
        if gaps[0][0] <= opt.max_still_s - 0.1:          # a gap of exactly the limit can still leave a 2 s window empty: stay clearly under it
            return resolved
        g, a, b = gaps[0]
        used = set()
        for ph in res.phrases:
            used.update(range(ph["first"], ph["last"] + 1))
        used.update(res.used_extra)
        inside = [gi for gi in bw if a + 0.5 <= words[gi][1] <= b - 0.4 and gi not in used]
        done = False
        # 1. a picture tile for a keyword spoken inside the gap
        for gi in inside:
            t = norm(words[gi][0])
            if t in table and table[t] not in used_assets and t not in LX.STOP and t not in LX.WEAK:
                for (x, y) in spots(330, 420):
                    cid_ = f"{beat_id}_tile_r{rnd + 1}_{x}_{y}"
                    res.cues.append(Cue(cid_, "visual", {"index": bw.index(gi)}, text=_disp(t, cased), role="gold", asset=table[t], pos=(x, y), params={"style": "tile"}))
                    n0 = len(res.dropped)
                    resolved = gate(res, beat_id, start, end, words, opt)
                    if any(d["cue"] == cid_ for d in res.dropped[n0:]):
                        res.cues = [c for c in res.cues if c.id != cid_]
                        continue
                    used_assets.add(table[t])
                    res.repairs.append(f"{cid_}: added picture tile {t!r} inside a {g:.1f} s still gap ({a:.2f} to {b:.2f} s)")
                    res.phrases.append({"sentence": -1, "label": "repair", "phrase": t, "asset": table[t], "keyword": t, "role": "gold", "role_keyword": "", "first": gi, "last": gi, "as": "tile"})
                    res.metaphor_uses.append({"keyword": t, "asset": table[t], "role": ICON_ROLE.get(table[t], "blue"), "beat": beat_id})
                    done = True
                    break
            if done:
                break
        if done:
            continue
        # 2. a typed line with the best leftover phrase: a narrow two-line block first, then wider one-line strips (the busy area decides what fits)
        for (lw_, ln_, px_) in ((560, 2, 64), (900, 1, 56), (1080, 1, 48)):
            got = best_phrases(inside, words, cased, table, breaks or set(), k=1, max_words=6, fit=_line_fit(lw_, px_, ln_), min_score=4.0, min_words=2)
            if not got:
                continue
            mm = ST.measure("line", got[0].text, {"width": lw_, "px": px_, "lines": ln_}) or {"h": 150}
            for (x, y) in spots(lw_, mm["h"]):
                cid_ = f"{beat_id}_line_r{rnd + 1}_{x}_{y}"
                res.cues.append(Cue(cid_, "visual", {"index": bw.index(got[0].first)}, text=got[0].text, role="ink", pos=(x, y), cps=34.0, offset_s=0.0,
                                    params={"style": "line", "width": lw_, "px": px_, "lines": ln_, "tint": False, "sync": True}))
                n0 = len(res.dropped)
                resolved = gate(res, beat_id, start, end, words, opt)
                if any(d["cue"] == cid_ for d in res.dropped[n0:]):
                    res.cues = [c for c in res.cues if c.id != cid_]
                    continue
                res.repairs.append(f"{cid_}: added typed line {got[0].text!r} inside a {g:.1f} s still gap ({a:.2f} to {b:.2f} s)")
                res.used_extra.update(range(got[0].first, got[0].last + 1))
                res.phrases.append({"sentence": -1, "label": "repair", "phrase": got[0].text, "asset": None, "keyword": "", "role": "ink", "role_keyword": "", "first": got[0].first, "last": got[0].last, "as": "line"})
                done = True
                break
            if done:
                break
        if done:
            continue
        break
    ev = change_events(resolved, start, end, strict=True)
    res.still_gap_s = max(b - a for a, b in zip(ev, ev[1:]))
    res.still_gap_strict_s = res.still_gap_s
    eva = change_events(resolved, start, end)
    res.still_gap_all_s = max(b - a for a, b in zip(eva, eva[1:]))
    return resolved
