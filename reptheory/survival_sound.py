"""Survival's scene sounds: a quiet bed that follows what the narration is about (fire, rain, water, cold, wind, woods), from the words themselves.
A topic must be the subject (named twice or more in a sentence and its two neighbours) and last AMB_MIN_S, else the sound stays where it was;
sentences about nothing in particular go back to silence (the music bed alone). pakMap ids in pakmap/sounds.py (sv_*)."""
from __future__ import annotations
import re
from typing import List

TOPICS = (
    ("sv_fire", r"\b(?:fires?|campfires?|flames?|coals?|embers?|stoves?|woodstoves?|chimneys?|firewood|kindling|smoke)\b"),
    ("sv_rain", r"\b(?:rain\w*|storms?|thunder\w*|downpours?|drizzle)\b"),
    ("sv_cold", r"\b(?:snow\w*|blizzards?|freez\w*|frozen|winter|ice|icy|frost\w*|cold)\b"),
    ("sv_water", r"\b(?:rivers?|creeks?|streams?|lakes?|ponds?|springs?|water|wells?)\b"),
    ("sv_wind", r"\b(?:wind\w*|plains|prairie|deserts?|dust|gusts?)\b"),
    ("sv_forest", r"\b(?:woods|forests?|trails?|trees?|pines?|oaks?|camps?|hunters?|wilderness)\b"),
)
AMB_MIN_S = 12.0

def _topic(text: str) -> tuple:
    best, hits = "", 0
    for bed, rx in TOPICS:
        n = len(re.findall(rx, text, re.I))
        if n > hits: best, hits = bed, n
    return best, hits

def beds(scenes: List[dict]) -> List[dict]:
    """[{"t", "ambience"}] for pakmap.audio_plan: one bed at a time, "none" for no topic."""
    sents = []
    for sc in scenes:
        for s in re.split(r"(?<=[.!?])\s+", sc.get("script_text") or sc.get("text", "")):
            if s.strip(): sents.append((float(sc["start"]), s))
    raw = []
    for k, (t, s) in enumerate(sents):      # each sentence with its neighbours: the subject is what this stretch keeps naming (two mentions or more)
        bed, hits = _topic(" ".join(x[1] for x in sents[max(0, k - 1):k + 2]))
        raw.append((t, bed if hits >= 2 else ""))
    out: List[dict] = []
    for t, bed in raw:
        cur = out[-1]["ambience"] if out else None
        if bed == (cur if cur not in (None, "none") else ""): continue
        if not out and not bed: continue      # silence at the start holds nothing back
        if out and t - out[-1]["t"] < AMB_MIN_S: continue      # a bed plays at least this long before another takes over
        out.append({"t": t, "ambience": bed or "none"})
    return [a for i, a in enumerate(out) if not (i == 0 and a["ambience"] == "none")]
