"""When each weather layer is on screen, in narration seconds, from the Hybrid plan's beats and the narrator's words.

A layer belongs to a beat (its id in beats.csv). It appears at `t`, or where its vo_anchor words are spoken inside that beat
(pakMap's matcher, searched from the beat's start, the same way Hybrid places a layer), and stays for `hold` seconds, else
until the beat ends (`until` = beat_end, the default), the video ends (end) or a given second."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Sequence

from .sidecar import SidecarError, WxRow


@dataclass(frozen=True)
class Window:
    t_in: float
    t_out: float


def layer_windows(rows: Sequence[WxRow], plan, words: Sequence = ()) -> Dict[str, Window]:
    """id -> Window for every row. `plan` is a hybrid.plan.HybridPlan (beats with id, start, end). Problems name the row."""
    from pakmap.anchor import Transcript

    beats = {b.id: b for b in plan.beats}
    tr = Transcript(list(words)) if words else None
    out: Dict[str, Window] = {}
    problems: List[str] = []
    for r in rows:
        at = f"weather_layers.csv row {r.line} ({r.id})"
        b = beats.get(r.beat)
        if b is None:
            problems.append(f"{at}: beat {r.beat!r} is not in beats.csv (beats: {', '.join(beats)})")
            continue
        if r.t is not None:
            t = float(r.t)
        else:
            if tr is None or not len(tr):
                problems.append(f"{at}: vo_anchor needs the narration's words (choose the voiceover first)")
                continue
            words_, _, mod = r.vo_anchor.partition("|")
            start_token = next((i for i, (f, _l) in enumerate(tr._spans) if tr.words[f][1] >= b.start - 0.05), len(tr._spans))
            hit = tr.find(words_.strip(), start_token)
            if hit is None:
                hit = _shorter_phrase_hit(tr, words_.strip(), start_token, b.start, b.end)
            if hit is None or hit[0].out_of_order:
                near = tr.nearest(words_.strip())
                problems.append(f"{at}: vo_anchor {words_.strip()!r} is not spoken in beat {r.beat}"
                                + (f" (closest: {near[0]!r} at {near[1]:.1f}s)" if near else ""))
                continue
            m = hit[0]
            t = round(m.t_end if mod.strip().lower() == "end" else m.t_start, 3)
        if not (b.start - 0.05 <= t < b.end):
            problems.append(f"{at}: it starts at {t:.2f}s, outside its beat {r.beat} ({b.start:.2f}-{b.end:.2f}s)")
            continue
        if r.hold is not None:
            end = t + r.hold
        elif r.until == "end":
            end = plan.duration
        elif r.until == "beat_end":
            end = b.end
        else:
            end = float(r.until)
        end = min(end, plan.duration)
        if end <= t + 0.2:
            problems.append(f"{at}: it would be on screen for {max(0.0, end - t):.2f}s (from {t:.2f}s); give it a longer hold or a later until")
            continue
        out[r.id] = Window(round(max(0.0, t), 3), round(end, 3))
    if problems:
        raise SidecarError(problems)
    return out


def _shorter_phrase_hit(tr, phrase: str, start_token: int, b_start: float, b_end: float):
    """The phrase with one word left out (then two ...), for a word the transcriber did not hear ("A tornado carrying" heard as
    "tornado carrying"). At least two words are kept; one word only as a last resort, and only a word of 4 letters or more.
    Only a match inside the beat counts."""
    from itertools import combinations

    words = phrase.split()
    n = len(words)
    tries = [" ".join(w for i, w in enumerate(words) if i not in drop)
             for k in range(1, max(1, n - 1)) for drop in combinations(range(n), k)]
    if n == 2:
        tries += [w for w in words if len(w.strip(".,;:!?\"'")) >= 4]
    for sub in tries:
        hit = tr.find(sub, start_token)
        if hit is not None and not hit[0].out_of_order and b_start - 0.05 <= hit[0].t_start < b_end:
            return hit
    return None
