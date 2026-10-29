"""Animation pass (opt-in, DirectorOptions.animate): after a beat is authored, cues get `params["motion"]` (board/anim.py) so elements ENTER instead of popping.

  * cartoon beat: each figure slides in from its nearer screen edge (ease and length vary with the beat's index), a crowd arrives as a left-to-right wave, a prop drops in; a figure that
    continues from the previous beat (scene_registry) does not enter again; the figure that is speaking (a speech verb) pulses once. The set is never moved.
  * recipe beat (cause / before-after / columns / pyramid / pictogram / timeline): the elements enter in the order they are spoken, from a direction that suits the recipe; the key number
    gets one pulse.

Rules kept for every beat: resting positions are the authored ones (only the draw offset is animated), an entrance ends within 0.6 s, nothing moves in the last 0.35 s before the board is
cleared (or the beat ends), a moving element is at rest for at least half of its time on the board, at most 3 elements move at once. Pure and deterministic; the cue params carry
everything, so the clip hash changes with the motion."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence

from ..board.dry import dry_build
from .segment import norm

MAX_ENTER_S = 0.6
QUIET_END_S = 0.35               # no motion in the last 0.35 s before the board is cleared
MAX_MOVING = 3
CAP_DIST = 520
SPEECH = frozenset("""said says say told tells asked asks shouted shouts declared declares announced announces warned warns cried claimed claims replied whispered explained explains demanded
demands ordered orders argued argues insisted proclaimed promised answered called yelled swore admitted""".split())
EASES = ("out", "back", "inout")
PULSE = {"kind": "pulse", "dur": 0.4, "amp": 0.07}
RECIPE_STYLES = ("node", "tag", "tile", "box", "bars", "photo", "crowd", "circle", "lite")


def _enter(frm: str, dist: float, dur: float, ease: str, fade: float = 0.25, **extra: Any) -> Dict[str, Any]:
    return {"enter": {"from": frm, "dist": int(dist), "dur": round(dur, 3), "ease": ease}, "fade": fade, "nopop": True, **extra}


def _items(br, beat_id, start, end, words, opt):
    probs, _r, items = dry_build(br.cues, words, start, end, dissolve_s=opt.dissolve_s, fps=opt.fps, beat_id=beat_id)
    return {it.cue_id: it for it in items}, end - start


def _num(text: str) -> float:
    m = re.findall(r"\d[\d,.]*", text or "")
    try:
        return max(float(x.replace(",", "")) for x in m) if m else -1.0
    except ValueError:
        return -1.0


def _speech_time(words, bw: Sequence[int]) -> Optional[float]:
    for g in bw:
        if norm(words[g][0]) in SPEECH:
            return float(words[g][1])
    return None


class _Budget:
    """At most MAX_MOVING windows overlap in time; a window may not cover more than half of the element's time on the board."""

    def __init__(self, clip_end: float):
        self.win: List[List[float]] = []
        self.clip_end = clip_end

    def fits(self, onset: float, dur: float, hide: Optional[float]) -> float:
        """The usable duration (<= dur), or 0 when the element cannot move."""
        stop = (hide if hide is not None else self.clip_end) - QUIET_END_S
        avail = stop - onset
        d = min(dur, avail, 0.5 * ((hide if hide is not None else self.clip_end) - onset))
        if d < 0.2:
            return 0.0
        if sum(1 for a, b in self.win if a < onset + d and onset < b) >= MAX_MOVING:
            return 0.0
        return d

    def add(self, onset: float, dur: float) -> None:
        self.win.append([onset, onset + dur])


def _cartoon(br, items, words, bw, seed: int, clip_end: float, continuity, prev_cast, rec, alive: bool = False) -> None:
    bud = _Budget(clip_end)
    ease = EASES[seed % 3]
    dur0 = 0.45 + 0.05 * (seed % 3)
    cast = (continuity or {}).get("cast") or []
    on_stage = bool(continuity and continuity.get("continued") and prev_cast)
    figs = []
    for c in br.cues:
        st = (c.params or {}).get("style")
        it = items.get(c.id)
        if c.kind != "visual" or it is None or st == "set":
            continue
        if st == "figure":
            k = int(re.search(r"fig(\d+)$", c.id).group(1)) - 1 if re.search(r"fig(\d+)$", c.id) else -1
            if on_stage and 0 <= k < len(cast) and [cast[k][0], cast[k][1]] in [list(p) for p in prev_cast]:
                rec["stayed"].append(c.id)
                figs.append((c, it, True))
                continue
            x0, _y0, x1, _y1 = it.rect
            left = (x0 + x1) / 2 < 960 if k != 1 else (seed % 2 == 0 and (x0 + x1) / 2 < 1100)
            d = bud.fits(it.onset, dur0, it.hide_at)
            if d <= 0:
                figs.append((c, it, False))
                continue
            dist = min(CAP_DIST, x1 if left else 1920 - x0)
            c.params["motion"] = _enter("left" if left else "right", dist, d, ease, 0.25)
            bud.add(it.onset, d)
            rec["entered"].append({"cue": c.id, "from": "left" if left else "right", "dur": round(d, 3), "ease": ease})
            figs.append((c, it, False))
        elif st == "crowd":
            n = int((c.params or {}).get("n", 6))
            member = 0.3
            step = min(0.1, 0.3 / max(1, n - 1))
            span = round(step * max(0, n - 1), 3)
            d = bud.fits(it.onset, span + member, it.hide_at)
            if d <= 0:
                continue
            span = round(max(0.0, d - member), 3)
            c.params["motion"] = {"wave": {"span": span, "dur": member, "dist": 50}, "nopop": True}
            bud.add(it.onset, d)
            rec["entered"].append({"cue": c.id, "from": "wave", "dur": round(d, 3), "step": round(step, 3)})
        elif st == "prop":
            d = bud.fits(it.onset, 0.5, it.hide_at)
            if d <= 0:
                continue
            c.params["motion"] = _enter("top", 150, d, "out", 0.2, scale=[0.7, 1.0, round(d, 3)])
            bud.add(it.onset, d)
            rec["entered"].append({"cue": c.id, "from": "top", "dur": round(d, 3)})
    for j, (c, it, _stayed) in enumerate(figs if alive else []):         # opt-in `alive`: every figure is alive: it bobs and sways on its own phase (the motion has no keyframes, so it never competes with the entrance budget)
        c.params.setdefault("motion", {})["idle"] = {"period": round(2.0 + 0.35 * ((seed + j) % 4), 2), "phase": round(1.7 * j + 0.6 * (seed % 5), 2), "bob": 5.0, "sway": 3.0}
    tv = _speech_time(words, bw)
    if tv is not None and figs:
        cand = [(c, it, st_) for c, it, st_ in figs if it.onset <= tv - 0.0]
        if cand:
            c, it, stayed = max(cand, key=lambda x: x[1].onset)
            enter_end = 0.0 if stayed or "motion" not in c.params else float(c.params["motion"]["enter"]["dur"])
            at = max(tv - it.onset, enter_end + 0.05)
            stop = (it.hide_at if it.hide_at is not None else clip_end) - QUIET_END_S
            if it.onset + at + PULSE["dur"] <= stop and sum(1 for a, b in bud.win if a < it.onset + at + PULSE["dur"] and it.onset + at < b) < MAX_MOVING:
                m = c.params.setdefault("motion", {})
                m["emphasis"] = {"at": round(at, 3), **PULSE}
                if alive:
                    m["talk"] = {"at": round(at + PULSE["dur"], 3), "dur": round(min(2.4, max(0.0, stop - it.onset - at - PULSE["dur"])), 3), "amp": 7.0}
                bud.add(it.onset + at, PULSE["dur"])
                rec["pulses"].append({"cue": c.id, "at": round(it.onset + at, 3)})


def _board(br, items, words, bw, seed: int, clip_end: float, recipe: str, rec) -> None:
    bud = _Budget(clip_end)
    els = sorted([(items[c.id].onset, i, c) for i, c in enumerate(br.cues) if c.kind == "visual" and c.id in items and (c.params or {}).get("style") in RECIPE_STYLES], key=lambda x: (x[0], x[1]))
    if not els:
        return
    ease = EASES[seed % 3] if recipe != "pyramid" else ("out", "back")[seed % 2]
    dur0 = 0.4 + 0.05 * (seed % 4)
    n = len(els)
    for k, (_t, _i, c) in enumerate(els):
        it, st = items[c.id], c.params["style"]
        if st == "bars":
            continue
        if st == "crowd":                                              # pictogram rows pop in: scale 0.6 -> 1 with a fade and a small stagger across the row
            d = bud.fits(it.onset, 0.35, it.hide_at)
            if d <= 0:
                continue
            c.params["motion"] = {"scale": [0.6, 1.0, round(d, 3)], "wave": {"span": round(max(0.0, d - 0.2), 3), "dur": 0.2, "dist": 0}, "nopop": True}
            bud.add(it.onset, d)
            rec["entered"].append({"cue": c.id, "from": "pop", "dur": round(d, 3)})
            continue
        frm, dist = "left", 220
        if recipe == "before_after":
            frm = "left" if k < (n + 1) // 2 else "right"
        elif recipe == "two_column":
            frm, dist = "bottom", 110
        elif recipe == "pyramid":
            frm, dist = "top", 130
        elif recipe == "timeline":
            frm, dist = "left", 160
        elif recipe == "cause_effect":
            frm = "left" if seed % 4 != 3 else "bottom"
            dist = 220 if frm == "left" else 120
        d = bud.fits(it.onset, dur0, it.hide_at)
        if d <= 0:
            continue
        c.params["motion"] = _enter(frm, dist, d, ease, 0.3)
        bud.add(it.onset, d)
        rec["entered"].append({"cue": c.id, "from": frm, "dur": round(d, 3), "ease": ease})
    # the key number: one pulse right after it arrives
    nums = [(_num(c.text), -k, c) for k, (_t, _i, c) in enumerate(els) if _num(c.text) >= 0 and (c.params or {}).get("style") != "crowd"]
    if nums:
        _v, _k, c = max(nums, key=lambda x: (x[0], x[1]))
        it = items[c.id]
        enter_end = float(c.params["motion"]["enter"]["dur"]) if "motion" in c.params and "enter" in c.params["motion"] else 0.0
        at = round(enter_end + 0.1, 3)
        stop = (it.hide_at if it.hide_at is not None else clip_end) - QUIET_END_S
        if it.onset + at + PULSE["dur"] <= stop and sum(1 for a, b in bud.win if a < it.onset + at + PULSE["dur"] and it.onset + at < b) < MAX_MOVING:
            c.params.setdefault("motion", {})["emphasis"] = {"at": at, **PULSE}
            bud.add(it.onset + at, PULSE["dur"])
            rec["pulses"].append({"cue": c.id, "at": round(it.onset + at, 3)})


def animate_pass(br, beat_id: str, start: float, end: float, sents: Sequence[Any], words, opt, variant: int = 0, kind: str = "board", continuity: Optional[Dict] = None,
                 prev_cast: Optional[Sequence[Any]] = None) -> Dict[str, Any]:
    """Adds `params["motion"]` to some of `br.cues` (positions and timing untouched) and returns a record for the plan report. Never raises: a beat that cannot be animated keeps its cues."""
    rec: Dict[str, Any] = {"entered": [], "stayed": [], "pulses": [], "skipped": []}
    bw = [i for i, w in enumerate(words) if start - 1e-6 <= w[1] < end - 1e-6]
    try:
        items, clip_end = _items(br, beat_id, start, end, words, opt)
        if kind == "cartoon":
            _cartoon(br, items, words, bw, variant, clip_end, continuity, prev_cast, rec, bool(getattr(opt, "alive", False)))
        else:
            recipe = getattr(br, "recipe", "") or ""
            if recipe:
                _board(br, items, words, bw, variant, clip_end, recipe, rec)
            else:
                rec["skipped"].append("not a recipe beat")
    except Exception as exc:                       # never stop: the beat keeps its cues
        rec["skipped"].append(f"animate pass failed: {type(exc).__name__}: {str(exc)[:80]}")
    return rec
