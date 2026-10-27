"""Numbers pass (opt-in, DirectorOptions.numbers; phase C of the upgrade plan): two small moves on a board beat that is already authored.

COUNT-UP: a bare spoken quantity that the board already shows as a tag or chip ("1,200", "45%", "$2.5 million") rolls up from zero to that exact text in 0.8 to 1.2 s (integer ease-out, nothing random),
ending on its final text. The cue keeps its place, its text and its timing; only `params.count` is added, so the layout is unchanged. Years are never rolled (they are plates), and a text the roll could not
reproduce character for character is left alone.
CROSS-OUT: a spoken negation (no, not, never, without, ...) within three words before the word a picture (tile or circle) is anchored on draws two red strokes over that picture, after it has landed.
Both are rate-limited (12 s and 20 s between two of them) and every candidate is tested with dry_build, so nothing can take another element's place."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence

from ..board import styles as ST
from ..board.cues import Cue
from ..board.dry import dry_build
from ..motion import presets as P
from .segment import norm

MIN_COUNT_GAP_S = 12.0
MIN_CROSS_GAP_S = 20.0
CROSS_AFTER_S = 0.4              # the picture pops in over 0.25 s; the first stroke starts once it has landed
HOLD_AFTER_S = 1.0
NEG_WINDOW = 3
NEG = frozenset("""no not never none nobody nothing nowhere without neither nor cannot cant dont didnt doesnt wasnt werent isnt arent wont wouldnt couldnt shouldnt hasnt havent hadnt""".split())


def _key(w: str) -> str:
    return re.sub(r"[^a-z]", "", w.lower())


def _is_year(spec) -> bool:
    return not spec["pre"] and not spec["unit"] and not spec["dec"] and not spec["commas"] and 1000 <= spec["to"] <= 2099      # "1944" and "1944 army" are dates; "1,200 percent" is not


def _worth_rolling(spec) -> bool:
    return spec["unit"] or spec["to"] / 10 ** spec["dec"] >= 20


def numbers_pass(br, beat_id: str, start: float, end: float, sents: Sequence[Any], words, opt, state: Dict[str, List[float]]) -> Dict[str, Any]:
    rec: Dict[str, Any] = {"counts": [], "crosses": [], "skipped": []}
    counts, crosses = state.setdefault("counts", []), state.setdefault("crosses", [])
    bw = [i for i, w in enumerate(words) if start - 1e-6 <= w[1] < end - 1e-6]
    # ---- one count-up ----
    for c in br.cues:
        is_tag = c.kind == "visual" and (c.params or {}).get("style") == "tag"
        if not (c.kind == "chip" or is_tag) or not c.text or (c.params or {}).get("count"):
            continue
        spec = P.count_spec(c.text)
        if spec is None:
            continue
        if _is_year(spec) or not _worth_rolling(spec):
            rec["skipped"].append(f"count {c.text!r}: a year or too small a number to roll")
            continue
        if P._fmt(spec["to"], spec) != " ".join(c.text.split()):
            rec["skipped"].append(f"count {c.text!r}: the roll would not end on exactly this text")
            continue
        a = (c.anchor or {}).get("index")
        if a is None or a >= len(bw):
            continue
        g = bw[a]
        t = float(words[g][1])
        if counts and t - counts[-1] < MIN_COUNT_GAP_S:
            rec["skipped"].append(f"count {c.text!r}: {t - counts[-1]:.1f} s after the previous count (minimum {MIN_COUNT_GAP_S:.0f} s)")
            continue
        frames = int(round((float(words[g][2]) - t + 0.6) * P.GRID_FPS))
        spec["frames"] = max(P.COUNT_MIN_FRAMES, min(P.COUNT_MAX_FRAMES, frames))
        bd = state.get("budget")
        if bd is not None:
            if not bd.allow("count", t)[0]:
                rec["skipped"].append(f"count {c.text!r}: {bd.refused[-1]['why']}")
                continue
            bd.commit("count", t)
        c.params = {**(c.params or {}), "count": spec, "cv": P.VERSION}
        counts.append(t)
        rec["counts"].append({"cue": c.id, "text": " ".join(c.text.split()), "t": round(t, 3), "frames": spec["frames"]})
        break
    # ---- one cross-out ----
    for c in list(br.cues):
        st = (c.params or {}).get("style")
        if c.kind != "visual" or st not in ("tile", "circle"):
            continue
        a = (c.anchor or {}).get("index")
        if a is None or a >= len(bw) or a < 1:
            continue
        g = bw[a]
        s_ = next((s for s in sents if g in s.widx), None)
        if s_ is None:
            continue
        near = [h for h in bw[max(0, a - NEG_WINDOW):a] if h in s_.widx]
        neg = next((h for h in reversed(near) if _key(words[h][0]) in NEG), None)
        if neg is None:
            continue
        t = float(words[g][1])
        off = float(c.offset_s if c.offset_s is not None else 0.1) + CROSS_AFTER_S
        if t + off > end - HOLD_AFTER_S:
            rec["skipped"].append(f"cross {c.id}: only {end - t:.1f} s left in the beat")
            continue
        if crosses and t - crosses[-1] < MIN_CROSS_GAP_S:
            rec["skipped"].append(f"cross {c.id}: {t - crosses[-1]:.1f} s after the previous cross-out (minimum {MIN_CROSS_GAP_S:.0f} s)")
            continue
        bd = state.get("budget")
        if bd is not None and not bd.allow("cross", t)[0]:
            rec["skipped"].append(f"cross {c.id}: {bd.refused[-1]['why']}")
            continue
        m = ST.measure(st, c.text or "", c.params or {}, c.asset)
        if m is None or c.pos is None:
            continue
        size = ST.TILE if st == "tile" else ST.RINGD
        cue = Cue(id=f"{beat_id}_cross1", kind="visual", anchor=dict(c.anchor), text="", role="red", offset_s=round(off, 3), pos=(int(c.pos[0]) + (m["w"] - size) // 2, int(c.pos[1]) + 4),
                  params={"style": "cross", "mv": P.VERSION, "over": [c.id], "size": size})
        probs, _r, _i = dry_build(list(br.cues) + [cue], words, start, end, dissolve_s=opt.dissolve_s, fps=opt.fps, beat_id=beat_id)
        if probs:
            rec["skipped"].append(f"cross {c.id}: does not fit the board ({probs[0][:80]})")
            continue
        br.cues.append(cue)
        crosses.append(t)
        if bd is not None:
            bd.commit("cross", t)
        rec["crosses"].append({"cue": cue.id, "over": c.id, "negation": norm(words[neg][0]), "t": round(t, 3)})
        break
    return rec
