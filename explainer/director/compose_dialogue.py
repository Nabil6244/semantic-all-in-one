"""Dialogue pass (opt-in, DirectorOptions.dialogue): the in-story speaker. When a cartoon (or board) beat's narration contains quoted speech, or a short cry such as "furious", the speaker's figure
gets a speech BUBBLE (visual style `bubble`) that pops in on the first spoken word of the quote and carries that quote, word for word, as it stands in the script. On cartoon beats there is no
narrator, so the speaker is one of the cast figures (turned to the 'point' pose for speech, 'surprise' for a cry); on a board beat the bubble points at the narrator. On a dark (dusk) cartoon
set a soft SPOT (stage light) is added over the speaker. Every added cue is accepted only when the whole beat still builds without a problem (same gate as compose_motion).

Quote detection reads the script text (the sentences' own text, quotation marks kept) and aligns it to the spoken words, which carry no punctuation or capitals. Without a script there are no
quotation marks to read: only the cry words are used. Nothing is reworded: the bubble text is a contiguous run of the script's own words (a prefix when the quote is long)."""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..board import styles as ST
from ..board.cues import Cue
from ..board.dry import dry_build
from ..motion import bubbles as BU
from .segment import norm

SPEECH_VERBS = frozenset("said says asked asks replied replies shouted shouts whispered whispers cried yelled declared answered exclaimed told warned insisted muttered screamed".split())
CRY = frozenset("furious angry outraged shocked terrified horrified stunned panicked desperate unbelievable nonsense enough".split())
OPEN_Q, CLOSE_Q, STRAIGHT_Q = "“«", "”»", '"'
MAX_QUOTE_WORDS, MIN_TRIM_WORDS = 9, 3
MIN_GAP_S = 5.0                 # between two bubbles of the video
HOLD_AFTER_S = 1.2              # a bubble needs this long in its beat to be read
MAX_PER_BEAT = 2
MAX_ONSET_DELAY_S = 0.25        # a bubble waits at most this long for its speaker to be on screen
MAX_LEAN = 70
POSE_SPEECH, POSE_CRY = "point", "surprise"
EDGE = 96                       # the layout margin


def new_state() -> Dict[str, List[float]]:
    return {"bubbles": []}


# ---------------------------------------------------------------- finding the speech
def _strip_marks(tok: str) -> str:
    return tok.translate({ord(c): None for c in OPEN_Q + CLOSE_Q + STRAIGHT_Q})


def _quoted_runs(text: str, widx: Sequence[int], words, inq: bool):
    """Runs of quoted script tokens in one sentence, aligned to the spoken words. Returns (runs, inq_after); a run is [(clean_token, global word index or None)]."""
    toks = text.split()
    flags: List[bool] = []
    closes: List[bool] = []
    for tok in toks:
        inside, any_in, closed = inq, False, False
        for ch in tok:
            if ch in OPEN_Q or (ch == STRAIGHT_Q and not inq):
                inq, any_in = True, True
            elif ch in CLOSE_Q or (ch == STRAIGHT_Q and inq):
                inq, any_in, closed = False, True, True
            elif inq:
                any_in = True
        flags.append(inside or any_in)
        closes.append(closed)
    s_norm = [norm(_strip_marks(t)) for t in toks]
    w_norm = [norm(words[g][0]) for g in widx]
    link: Dict[int, int] = {}
    for blk in SequenceMatcher(None, s_norm, w_norm, autojunk=False).get_matching_blocks():
        for k in range(blk.size):
            if s_norm[blk.a + k]:
                link[blk.a + k] = widx[blk.b + k]
    runs, cur = [], []
    for i, tok in enumerate(toks):
        clean = _strip_marks(tok)
        if flags[i] and clean:
            cur.append((clean, link.get(i)))
        if cur and (not flags[i] or closes[i]):
            runs.append(cur)
            cur = []
    if cur:
        runs.append(cur)
    return runs, inq


def _clean_end(text: str) -> str:
    return text.rstrip(" ,;:—-").rstrip(".") if not text.endswith(("?", "!")) else text


def _trim(run: List[Tuple[str, Optional[int]]], n: int) -> List[Tuple[str, Optional[int]]]:
    """The first n words of the run, cut back to the last clause end (comma, full stop, ? or !) when there is one after the third word."""
    part = run[:n]
    if len(run) > n:
        for k in range(len(part) - 1, MIN_TRIM_WORDS - 2, -1):
            if part[k][0][-1:] in ",;:.!?":
                return part[:k + 1]
    return part


ECHO_MIN_BEAT_S = 4.0
ECHO_WORDS = (2, 5)             # an in-world line is a short phrase


def _echo(sents: Sequence[Any], words, pos: Dict[int, int]) -> List[Dict[str, Any]]:
    """An in-world line for the cast when the script quotes nobody (the references act the narration out: the villagers say the key phrase themselves): the most telling run of 2 to 4 content
    words of the beat, taken word for word from the narration (nothing is invented), starting after the first third of the beat so the figures are on stage. Shown as speech with an exclamation mark."""
    from ..director import lexicon as LX
    gs = [g for s in sents for g in s.widx if g in pos]
    if len(gs) < 8:
        return []
    best, best_score = None, 0
    for a in range(len(gs) // 3, len(gs) - ECHO_WORDS[0] + 1):
        for n in range(ECHO_WORDS[1], ECHO_WORDS[0] - 1, -1):
            run = gs[a:a + n]
            if len(run) < n or any(run[k + 1] != run[k] + 1 for k in range(n - 1)):
                continue
            toks = [norm(words[g][0]) for g in run]
            if toks[0] in LX.STOP or toks[-1] in LX.STOP or any(not t for t in toks):
                continue
            content = sum(1 for t in toks if t not in LX.STOP)
            ends = any(run[-1] == s.widx[-1] for s in sents if s.widx)
            score = content * 10 + sum(len(t) for t in toks) - (3 if toks[0] in LX.WEAK else 0) + (8 if ends else 0) - (9 if toks[-1].endswith("ed") or toks[0].endswith("ed") else 0)
            if content >= 2 and score > best_score:
                best, best_score = run, score
    if best is None:
        return []
    cas = {norm(t): re.sub(r"[^\w'-]", "", t) for sn in sents for t in (getattr(sn, "text", "") or "").split() if t[:1].isupper() and norm(t)}      # the script's own capitals (Napoleon, Venice)
    ws = [cas.get(norm(words[g][0]), re.sub(r"[^\w'-]", "", words[g][0])) for g in best]
    text = " ".join(ws)
    return [{"kind": "echo", "g": best[0], "run": [(w, g) for w, g in zip(ws, best)], "text": text[:1].upper() + text[1:] + "!", "shout": False}]


def candidates(sents: Sequence[Any], words, pos: Dict[int, int]) -> List[Dict[str, Any]]:
    """Every speech or cry in the beat, in spoken order: {kind, g (first word), words [(text, g)], text, shout}."""
    out: List[Dict[str, Any]] = []
    inq = False
    for s in sents:
        text = getattr(s, "text", "") or ""
        runs, inq = _quoted_runs(text, s.widx, words, inq)
        verb = any(norm(w) in SPEECH_VERBS for w in text.split())
        bang = text.rstrip().endswith("!")
        for run in runs:
            matched = [g for _t, g in run if g is not None]
            if not matched or matched[0] not in pos:
                continue
            if len(run) < 2 and not (verb or bang):            # a single quoted word is a scare-quote, not speech
                continue
            out.append({"kind": "quote", "g": matched[0], "run": run, "text": " ".join(t for t, _g in run), "shout": False})
        toks = text.split()
        if 1 <= len(toks) <= 3 and bang and not runs:           # a short exclamation sentence ("Run!")
            matched = [g for g in s.widx if g in pos]
            if matched:
                out.append({"kind": "cry", "g": matched[0], "run": [(t, None) for t in toks], "text": " ".join(toks), "shout": True})
        for g in s.widx:
            if g in pos and norm(words[g][0]) in CRY and not any(c["g"] == g for c in out):
                inside = any(c["kind"] == "quote" and g in {x for _t, x in c["run"] if x is not None} for c in out)
                if not inside and not (out and out[-1]["kind"] == "cry" and out[-1]["g"] == s.widx[0] and len(toks) <= 3):
                    out.append({"kind": "cry", "g": g, "run": [(re.sub(r"[^\w'-]", "", words[g][0]), g)], "text": re.sub(r"[^\w'-]", "", words[g][0]), "shout": True})
    return sorted(out, key=lambda c: c["g"])


# ---------------------------------------------------------------- placing
def _ok(cues: Sequence[Cue], words, start: float, end: float, opt, beat_id: str) -> bool:
    probs, _r, _i = dry_build(cues, words, start, end, dissolve_s=opt.dissolve_s, fps=opt.fps, beat_id=beat_id)
    return not probs


def _bubble_spots(tr, w: int, h: int, hx: int):
    """Candidate (x, y, tx, lean) for a bubble of w x h whose tail points down at x = hx just above the speaker's box `tr`: tail positions 30%, 70%, 50% along the bubble, two gaps."""
    for gap in (10, 36):
        y = tr[1] - gap - h
        if y < EDGE:
            continue
        for frac in (0.3, 0.7, 0.5):
            tx = int(w * frac)
            x = min(max(hx - tx, EDGE), 1920 - EDGE - w)
            lean = hx - (x + tx)
            if abs(lean) > MAX_LEAN:
                continue
            yield x, y, tx, lean


def _proto(cid: str, g_pos: int, text: str, role: str, offset: float, params: Dict[str, Any]) -> Dict[str, Any]:
    return dict(id=cid, kind="visual", anchor={"index": g_pos}, text=text, role=role, offset_s=round(offset, 3), params=params)


def _set_pose(fig: Cue, pose: str) -> Optional[Tuple[Dict[str, Any], Tuple[int, int]]]:
    """Turn a figure cue to `pose` keeping its feet where they were; returns the old (params, pos) for undo, or None when it is already in that pose or the pose does not exist."""
    p = dict(fig.params or {})
    if p.get("pose", "idle") == pose or fig.pos is None:
        return None
    q = {**p, "pose": pose}
    old, new = ST.measure_cartoon("figure", p), ST.measure_cartoon("figure", q)
    if old is None or new is None:
        return None
    undo = (p, tuple(fig.pos))
    fig.params = q
    fig.pos = (fig.pos[0], fig.pos[1] + old["h"] - new["h"])
    return undo


def dialogue_pass(br, beat_id: str, start: float, end: float, sents: Sequence[Any], words, opt, state: Dict[str, List[float]]) -> Dict[str, Any]:
    """Adds at most MAX_PER_BEAT bubbles (and, on a dusk set, one spot) to `br.cues`; returns a record for the plan report. Never raises for a candidate that does not fit: it is skipped with a reason."""
    rec: Dict[str, Any] = {"bubbles": [], "spots": [], "poses": [], "skipped": []}
    bw = [i for i, w in enumerate(words) if start - 1e-6 <= w[1] < end - 1e-6]
    pos = {g: k for k, g in enumerate(bw)}
    done = state.setdefault("bubbles", [])
    cands = candidates(sents, words, pos)
    echo = False
    if not cands and end - start >= ECHO_MIN_BEAT_S and any((c.params or {}).get("style") == "figure" for c in br.cues if c.kind == "visual"):
        cands, echo = _echo(sents, words, pos), True          # no quoted speech: the cast says the key phrase of its own narration
    if not cands:
        return rec
    probs, resolved, items = dry_build(br.cues, words, start, end, dissolve_s=opt.dissolve_s, fps=opt.fps, beat_id=beat_id)
    if probs:
        rec["skipped"].append(f"the beat already has a problem ({probs[0][:80]}): no bubble added")
        return rec
    origin = next((r.onset_abs - r.onset_clip for r in resolved if r.onset_abs is not None and r.onset_clip is not None), start)
    dusk = any(c.kind == "visual" and (c.params or {}).get("style") == "set" and (c.params or {}).get("tod") == "dusk" for c in br.cues)
    taken: List[float] = []
    for cand in cands:
        if len(rec["bubbles"]) >= MAX_PER_BEAT:
            break
        g = cand["g"]
        t = float(words[g][1])
        label = cand["text"][:40]
        if (done and t - done[-1] < MIN_GAP_S) or (taken and t - taken[-1] < MIN_GAP_S):
            rec["skipped"].append(f"bubble {label!r}: too soon after the previous bubble (minimum {MIN_GAP_S:.0f} s)")
            continue
        if t > end - HOLD_AFTER_S:
            rec["skipped"].append(f"bubble {label!r}: only {end - t:.1f} s left in the beat")
            continue
        tc = t - origin
        figs = sorted([it for it in items if it.kind == "visual" and it.style == "figure" and it.onset <= tc + MAX_ONSET_DELAY_S and (it.hide_at is None or it.hide_at > tc)], key=lambda it: it.rect[0])
        if not figs:
            figs = [it for it in items if it.kind == "narrator" and it.onset <= tc + MAX_ONSET_DELAY_S and (it.hide_at is None or it.hide_at > tc)]
        if not figs:
            rec["skipped"].append(f"bubble {label!r}: no speaker on screen")
            continue
        k0 = len(rec["bubbles"]) % len(figs)
        order = figs[k0:] + figs[:k0]
        role = "red" if cand["shout"] else "ink"
        run = cand["run"]
        sizes = list(range(min(len(run), MAX_QUOTE_WORDS), MIN_TRIM_WORDS - 1, -1)) if len(run) > MIN_TRIM_WORDS else [len(run)]
        texts, seen = [], set()
        for n in sizes:
            tx_ = _clean_end(" ".join(x for x, _g in _trim(run, n)))
            if tx_ and tx_ not in seen:
                seen.add(tx_)
                texts.append(tx_)
        if cand["kind"] == "echo":
            texts = [cand["text"]]
        placed = None
        for sp in order:
            fig_cue = next((c for c in br.cues if c.id == sp.cue_id), None)
            delay = max(0.0, min(MAX_ONSET_DELAY_S, sp.onset - tc))
            hx = (sp.rect[0] + sp.rect[2]) // 2
            for text in texts:
                prm = {"style": "bubble", "bv": BU.VERSION, "pv": len(done) % BU.VARIANTS, "px": 52, "shout": bool(cand["shout"])}
                m = ST.measure("bubble", text, prm)
                if m is None:
                    continue
                for x, y, tx, lean in _bubble_spots(sp.rect, m["w"], m["h"], hx):
                    cue = Cue(pos=(x, y), **_proto(f"{beat_id}_bubble{len(rec['bubbles']) + 1}", pos[g], text, role, delay, {**prm, "tx": tx, "lean": lean}))
                    undo = None
                    if fig_cue is not None and fig_cue.params.get("style") == "figure":
                        undo = _set_pose(fig_cue, POSE_CRY if cand["shout"] else POSE_SPEECH)
                        if undo is not None and not ST.measure("figure", "", fig_cue.params):
                            undo = None
                    if _ok(list(br.cues) + [cue], words, start, end, opt, beat_id):
                        placed = (cue, sp, fig_cue, undo)
                        break
                    if undo is not None:                                # the pose change broke something: try the bubble alone
                        fig_cue.params, fig_cue.pos = undo[0], undo[1]
                        undo = None
                        if _ok(list(br.cues) + [cue], words, start, end, opt, beat_id):
                            placed = (cue, sp, fig_cue, None)
                            break
                if placed:
                    break
            if placed:
                break
        if not placed:
            rec["skipped"].append(f"bubble {label!r}: no free place above a speaker")
            continue
        cue, sp, fig_cue, undo = placed
        br.cues.append(cue)
        taken.append(t)
        done.append(t)
        rec["bubbles"].append({"cue": cue.id, "text": cue.text, "t": round(t, 3), "kind": cand["kind"], "speaker": sp.cue_id, "pos": list(cue.pos), "offset_s": cue.offset_s})
        if undo is not None:
            rec["poses"].append({"cue": fig_cue.id, "pose": fig_cue.params["pose"]})
        if dusk and not rec["spots"]:
            spot = _try_spot(br, beat_id, cue, sp, pos[g], words, start, end, opt)
            if spot is not None:
                br.cues.append(spot)
                rec["spots"].append({"cue": spot.id, "pos": list(spot.pos), "params": {k: spot.params[k] for k in ("w", "h", "power")}})
        items = _items(br, words, start, end, opt, beat_id)
    return rec


def _items(br, words, start, end, opt, beat_id):
    return dry_build(br.cues, words, start, end, dissolve_s=opt.dissolve_s, fps=opt.fps, beat_id=beat_id)[2]


def _try_spot(br, beat_id: str, bubble: Cue, speaker, g_pos: int, words, start: float, end: float, opt) -> Optional[Cue]:
    """A cone of stage light from the top of the frame down onto the speaker, lying over the figure and the bubble (it declares them in `over`, as a cross-out does)."""
    over = [c.id for c in br.cues if c.kind == "visual" and (c.params or {}).get("style") not in ("set",)]
    cx = (speaker.rect[0] + speaker.rect[2]) // 2
    floor = min(1080 - EDGE, speaker.rect[3] + 24)
    for w in (SPOT_W_PREF, 440):
        x = min(max(cx - w // 2, EDGE), 1920 - EDGE - w)
        prm = {"style": "spot", "bv": BU.VERSION, "w": w, "h": floor - EDGE, "power": 0.4, "over": over}
        cue = Cue(pos=(x, EDGE), **_proto(f"{beat_id}_spot1", g_pos, bubble.text, "ink", bubble.offset_s or 0.0, prm))
        if ST.measure("spot", cue.text, prm) and _ok(list(br.cues) + [cue], words, start, end, opt, beat_id):
            return cue
    return None


SPOT_W_PREF = 560
