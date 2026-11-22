"""English on-screen text over a voice in another language (Urdu, Hindi, ...).

A scene CSV may carry an ``on_screen_en`` column: a short English line for each scene. Timing is always taken from the
real voice (the rows are aligned to Whisper first). After that, the planners that pick pop-up words, graphics, maps,
stat counters and sound cues read the narration TEXT and the spoken WORDS — both in the voice's language, which those
planners do not understand (and which Pillow cannot draw). So, after alignment, each scene's English line becomes its
script text, and its words are spread evenly across that scene's own time window as stand-in "spoken" words.
Scenes without an English line keep their own text and words.

Only the planning sees English: the voice, the cut points and the assets are unchanged.
"""
from __future__ import annotations

from typing import Callable, List, Optional, Sequence, Tuple

COLUMN = "on_screen_en"


def english_lines(rows: Sequence[dict]) -> dict:
    """scene_number -> English line, for rows that have one."""
    out = {}
    for r in rows or []:
        text = str((r or {}).get(COLUMN) or "").strip()
        if text:
            out[str(r.get("scene_number") or "").strip()] = text
    return out


def apply(rows: Sequence[dict], aligned: Sequence[dict], words: Sequence[tuple],
          split_words: Callable[[str], List[str]]) -> Optional[Tuple[list, list, list]]:
    """(rows, aligned, words) with English planning text, or None when no row has an English line."""
    en = english_lines(rows)
    gfx = {str(r.get("scene_number") or "").strip(): str(r.get("gfx") or "").strip() for r in rows or [] if str((r or {}).get("gfx") or "").strip()}
    if not en and not gfx:
        return None
    aligned = [dict(a, gfx=gfx[str(a.get("scene_number") or "").strip()]) if str(a.get("scene_number") or "").strip() in gfx else a
               for a in aligned]   # the scene CSV's own graphics (normal_gfx.planner.csv_events) reach the planner with the timing
    new_rows = [dict(r, script_segment=en.get(str(r.get("scene_number") or "").strip(), r.get("script_segment", ""))) for r in rows]
    new_aligned, new_words = [], []
    words = list(words or [])
    for a in aligned:
        scene = str(a.get("scene_number") or "").strip()
        t0, t1 = float(a.get("start_time", 0.0)), float(a.get("end_time", 0.0))
        line = en.get(scene)
        if line is None:
            new_aligned.append(dict(a))
            new_words.extend(w for w in words if t0 <= float(w[1]) < t1 or (t1 <= t0 and float(w[1]) == t0))
            continue
        new_aligned.append(dict(a, script_segment=line))
        toks = split_words(line)
        if not toks:
            continue
        span = max(t1 - t0, 0.05 * len(toks))
        step = span / len(toks)
        for k, tok in enumerate(toks):
            s = t0 + k * step
            new_words.append((tok, round(s, 3), round(s + step * 0.9, 3)))
    new_words.sort(key=lambda w: float(w[1]))
    return new_rows, new_aligned, new_words
