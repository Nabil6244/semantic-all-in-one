"""Motion pass (opt-in, DirectorOptions.motion): after a board beat is authored, add at most one verdict STAMP (a spoken verdict word such as "caught" or "worthless", slammed on that word) and
at most one date PLATE (a spoken four-digit year in a corner plate). Both are `visual` cues (styles stamp and plate) timed on the word itself, so they follow the same narration timing as every
other cue. The word is the speaker's own (a contiguous quote of the narration, shown in capitals); nothing is reworded. A candidate place is accepted only when the whole beat still builds
without a problem, so a stamp can never take another element's place or be dropped by the layout gate afterwards."""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..board import layout as LY
from ..board import styles as ST
from ..board.cues import Cue
from ..board.dry import dry_build
from ..motion import presets as P
from ..motion import sprites as MS
from . import lexicon as LX
from .segment import norm

VERDICT = frozenset("""caught surrounded worthless banned forbidden failed failure collapsed destroyed doomed trapped defeated impossible cancelled canceled stopped abandoned betrayed
bankrupt guilty fake lies lie rejected refused ruined useless illegal secret planned classified wrong""".split())
VERDICT_GREEN = frozenset("saved won victory succeeded survived freed approved".split())
MIN_STAMP_GAP_S = 15.0          # never two stamps within 15 s (at most 2 in any 30 s)
MIN_PLATE_GAP_S = 15.0
HOLD_AFTER_S = 0.8              # a stamp needs this much time left in its beat to land and be read
STAMP_AT = (0.0, 0.0)           # offsets: the slam's first frame is the word's own frame; the impact is 4 frames (0.13 s) later
YEAR = re.compile(r"^(1[0-9]{3}|20[0-9]{2})$")


MAX_TILT = math.radians(7.0)
SHAKE = 3
SETTLE_SCALE = max(f[0] for f in P.SLAM[P.IMPACT_FRAME:])      # the largest the stamp is after the impact (frames before it are a short approach, partly transparent)
STAMP_PX = (120, 96, 72)
PLATE_PX = (40, 34, 28)


def _grid(w: int, h: int, order, rotated: bool) -> List[Tuple[int, int]]:
    """Candidate top-left corners, in preference order, whose whole drawn extent (for a stamp: its rect rotated by the largest tilt, plus the slam shake) stays inside the content area."""
    sw, sh = w * SETTLE_SCALE, h * SETTLE_SCALE
    px = int(math.ceil((sw * math.cos(MAX_TILT) + sh * math.sin(MAX_TILT) - w) / 2)) + SHAKE + 2 if rotated else 0
    py = int(math.ceil((sw * math.sin(MAX_TILT) + sh * math.cos(MAX_TILT) - h) / 2)) + SHAKE + 2 if rotated else 0
    left, right, top, bottom = 720 + px, 1824 - px, LY.MARGIN + py, 1080 - LY.MARGIN - py            # right of the narrator zone, inside the margins
    xs = {"r": right - w, "m": (left + right - w) // 2, "l": left}
    ys = {"t": top, "m": (top + bottom - h) // 2, "b": bottom - h}
    out: List[Tuple[int, int]] = []
    for o in order:
        x, y = xs[o[0]], ys[o[1]]
        if left <= x and x + w <= right and top <= y and y + h <= bottom and (x, y) not in out:
            out.append((x, y))
    return out


def _stamp_spots(w: int, h: int) -> List[Tuple[int, int]]:
    return _grid(w, h, ("rb", "rt", "mb", "mt", "lb", "lt", "rm", "mm", "lm"), True)


def _plate_spots(w: int, h: int) -> List[Tuple[int, int]]:
    return _grid(w, h, ("rt", "mt", "lt"), False)


EVENT = frozenset("""began begin begins started ended end ends fell fall falls founded signed born died dies invaded invasion declared launched built collapsed won lost surrendered war wars treaty revolution
attacked captured liberated freed crowned elected discovered invented opened destroyed independence assassinated erupted exploded sank landed arrived conquered banned abolished""".split())
DATE_MIN_SCORE = 2              # event word within 6 words +2; the opening, a twist or a conclusion sentence +1; the narration's first year +1: a year with none of these is ordinary
EVENT_WINDOW = 6


def _year_of(tok: str) -> str:
    """The four-digit year a word is, or '' (a bare token such as 1944 or 1944, only)."""
    t = tok.strip(".,;:!?\"'")
    return t if YEAR.match(t) else ""


def _bare_year(text: Optional[str]) -> str:
    return " ".join((text or "").split()) if YEAR.match(" ".join((text or "").split())) else ""


def year_in(c: Cue, year: str) -> bool:
    return year in re.findall(r"\d+", c.text or "")


def _redundant_year(c: Cue, year: str) -> bool:
    """With a tag or chip being replaced: a second separate year element left on the board (another plate, tag, chip, title or header with the number in it). The board's running phrases that contain the
    year (typed line, scroll, caption) were already shown beside the old tag, so replacing the tag does not add a repeat. Without a tag to replace, any cue showing the year blocks the plate."""
    return year_in(c, year) and (c.kind in ("chip", "title", "header") or (c.kind == "visual" and (c.params or {}).get("style") in ("tag", "plate")))


def date_score(sent, g: int, words, first_year: Optional[int]) -> Tuple[int, str]:
    """Deterministic importance of the year at word g: its sentence names an event within EVENT_WINDOW words (+2), the sentence is the opening / a twist / a conclusion (+1), it is the first year of the narration (+1)."""
    sc, why = 0, []
    k = sent.widx.index(g)
    near = sent.widx[max(0, k - EVENT_WINDOW): k + EVENT_WINDOW + 1]
    ev = [norm(words[i][0]) for i in near if norm(words[i][0]) in EVENT]
    if ev:
        sc += 2
        why.append(f"event word {ev[0]!r}")
    if sent.label in ("hook", "twist", "conclusion"):
        sc += 1
        why.append(f"{sent.label} sentence")
    if first_year == g:
        sc += 1
        why.append("first year of the narration")
    return sc, ", ".join(why)


def new_state() -> Dict[str, List[float]]:
    return {"stamps": [], "plates": []}


def _ok(cues: Sequence[Cue], new_id: str, words, start: float, end: float, opt) -> bool:
    probs, _r, _i = dry_build(cues, words, start, end, dissolve_s=opt.dissolve_s, fps=opt.fps, beat_id=new_id.rsplit("_", 1)[0])
    return not probs


def _place(base, style: str, text: str, sizes, cue_proto: Dict[str, Any], spots, words, start: float, end: float, opt) -> Optional[Cue]:
    """Largest size first; for each size every candidate place in preference order. The first combination where the whole beat still builds cleanly wins."""
    for px in sizes:
        m = ST.measure(style, text, {"px": px})
        if m is None:
            continue
        for x, y in spots(m["w"], m["h"]):
            cue = Cue(pos=(x, y), **{**cue_proto, "params": {**cue_proto["params"], "px": px}})
            if _ok(list(base) + [cue], cue.id, words, start, end, opt):
                return cue
    return None


def motion_pass(br, beat_id: str, start: float, end: float, sents: Sequence[Any], words, opt, state: Dict[str, List[float]]) -> Dict[str, Any]:
    """Adds cues to `br.cues` (appended last, so they draw on top) and returns a small record for the plan report."""
    rec: Dict[str, Any] = {"stamps": [], "plates": [], "skipped": []}
    bw = [i for i, w in enumerate(words) if start - 1e-6 <= w[1] < end - 1e-6]
    pos = {g: k for k, g in enumerate(bw)}
    textured = MS.available()
    if not textured:
        br.repairs.append("stamp texture assets missing or damaged: stamps are drawn plain (rebuild with: python3 -B explainer/motion/build_assets.py)")
    # ---- one verdict stamp ----
    done = False
    for s in sents:
        if done:
            break
        for g in s.widx:
            if g not in pos:
                continue
            tok = norm(words[g][0])
            if tok not in VERDICT and tok not in VERDICT_GREEN:
                continue
            t = float(words[g][1])
            if state["stamps"] and t - state["stamps"][-1] < MIN_STAMP_GAP_S:
                rec["skipped"].append(f"stamp {tok!r}: {t - state['stamps'][-1]:.1f} s after the previous stamp (minimum {MIN_STAMP_GAP_S:.0f} s)")
                continue
            if t > end - HOLD_AFTER_S:
                rec["skipped"].append(f"stamp {tok!r}: only {end - t:.1f} s left in the beat")
                continue
            bd = state.get("budget")
            if bd is not None:
                ok_b, why_b = bd.allow("stamp", t)
                if not ok_b:
                    rec["skipped"].append(f"stamp {tok!r}: {why_b}")
                    continue
            text = re.sub(r"[^\w'-]", "", words[g][0]).upper()
            role = "green" if tok in VERDICT_GREEN else "red"
            proto = dict(id=f"{beat_id}_stamp1", kind="visual", anchor={"index": pos[g]}, text=text, role=role, offset_s=STAMP_AT[0], params={"style": "stamp", "mv": P.VERSION, "texture": textured, **({"sv": bd.variant("stamp")} if bd is not None else {})})
            cue = _place(br.cues, "stamp", text, STAMP_PX, proto, _stamp_spots, words, start, end, opt)
            if cue is None:
                rec["skipped"].append(f"stamp {tok!r}: no free place on the board")
                continue
            br.cues.append(cue)
            state["stamps"].append(t)
            if bd is not None:
                bd.commit("stamp", t)
            rec["stamps"].append({"cue": cue.id, "text": text, "t": round(t, 3), "pos": list(cue.pos)})
            done = True
            break
    # ---- one date plate for an important date; it replaces the board's own bare-year tag or chip ----
    first_year = next((g for g, w in enumerate(words) if _year_of(w[0])), None)
    for s_ in sents:
        for hit in s_.widx:
            if hit not in pos or not _year_of(words[hit][0]):
                continue
            text = _year_of(words[hit][0])
            t = float(words[hit][1])
            score, why = date_score(s_, hit, words, first_year)
            if score < DATE_MIN_SCORE:
                rec["skipped"].append(f"plate {text}: an ordinary year (importance {score}, needs {DATE_MIN_SCORE})")
                continue
            if state["plates"] and t - state["plates"][-1] < MIN_PLATE_GAP_S:
                rec["skipped"].append(f"plate {text}: {t - state['plates'][-1]:.1f} s after the previous plate (minimum {MIN_PLATE_GAP_S:.0f} s)")
                continue
            bd = state.get("budget")
            if bd is not None and not bd.allow("plate", t)[0]:
                rec["skipped"].append(f"plate {text}: {bd.refused[-1]['why']}")
                continue
            refs = {c.src for c in br.cues if c.src} | {c.dst for c in br.cues if c.dst}
            own = [c for c in br.cues if c.kind in ("chip", "visual") and (c.kind == "chip" or (c.params or {}).get("style") == "tag") and _bare_year(c.text) == text and c.id not in refs]
            rest = [c for c in br.cues if c not in own]
            clash = [c for c in rest if (_redundant_year(c, text) if own else year_in(c, text))]       # replacing the board's own tag adds no repeat; adding a plate beside any cue that shows the year does
            if clash:
                rec["skipped"].append(f"plate {text}: would repeat the year beside {clash[0].id} ({clash[0].text!r})")
                continue
            anchor = dict(own[0].anchor) if own else {"index": pos[hit]}
            proto = dict(id=f"{beat_id}_plate1", kind="visual", anchor=anchor, text=text, role="blue", offset_s=0.0, params={"style": "plate", "mv": P.VERSION, **({"pv": bd.variant("plate")} if bd is not None else {})})
            cue = _place(rest, "plate", text, PLATE_PX, proto, _plate_spots, words, start, end, opt)
            if cue is None:
                rec["skipped"].append(f"plate {text}: no free place on the board (the board's own year is kept)")
                continue
            br.cues[:] = rest + [cue]
            state["plates"].append(t)
            if bd is not None:
                bd.commit("plate", t)
            rec["plates"].append({"cue": cue.id, "text": text, "t": round(t, 3), "pos": list(cue.pos), "why": why, "replaced": [c.id for c in own]})
            return rec
    return rec
