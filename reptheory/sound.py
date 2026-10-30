"""Rep Theory sound (docs/rep_theory/UPGRADE_LIST.md section 7, Step 1): every change on screen gets the sound of what it does, a music bed runs
under the whole narration, and the result is mastered to -14 LUFS. The events are the plan's own (cadence.events), so a new script gets new
sounds where its own pictures change; nothing is tuned to one video. The sounds, the spacing rule, the mixer (narration first, everything ducked
under the voice), the music beds and the loudness pass are the app's own (pakMap / StarMap / What If), used as they are: no per-video assets.

    path, notes = mix(scenes, voiceover, work_dir, duration, title)      # never raises: on any failure the narration alone is returned"""
from __future__ import annotations
from pathlib import Path
from typing import Callable, Dict, List, Tuple

from . import cadence as C

KIND_SFX = {      # what each development sounds like (cadence.events "what")
    "headline": "subtle_pop", "callout page": "subtle_pop", "chip": "bubble_pluck", "value": "counter_ticks", "stat number": "counter_ticks",
    "ring": "marker_pop", "grip ring": "marker_pop", "glow": "marker_pop", "equation term": "marker_clack", "tier mark": "marker_clack",
    "tier placement": "deep_thud", "steps item": "ui_click", "versus item": "bubble_pluck", "hand switch": "ui_click", "tint": "deep_thud", "time mark": "clock_ticking", "mistake panel": "marker_clack",
    "slider panel": "ui_click", "dial value": "counter_ticks", "study value": "paper_slide",
    "graph bend": "marker_pop", "bar": "counter_ticks", "calendar day": "ui_click", "result band": "marker_clack", "warning card": "deep_thud", "comment typed": "bubble_pluck", "like press": "marker_pop", "subscribe press": "marker_pop", "stamp": "deep_thud", "next teaser": "fast_whoosh", "test lock": "marker_clack", "myth panel": "marker_clack", "question asked": "bubble_pluck", "number lands": "marker_pop", "signal beam": "fast_whoosh", "body change": "deep_thud"}
MAJOR = ("deep_thud", "fast_whoosh")
SAME_SOUND_GAP_S, MIN_GAP_S, MAX_PER_WINDOW, WINDOW_S = 0.6, 0.4, 8, 10.0      # What If's restraint: up to ~48 a minute, never stacked
MUSIC_GAIN = 0.36

def cues(scenes: List[dict]) -> List[dict]:
    """[{t, sfx, source}] for the plan's meaningful changes: a new composition gets a soft transition (a new part of the video a whoosh), every development
    the sound of what it does; then the spacing rule (same sound >= 0.6 s apart, any two >= 0.4 s, at most 8 in 10 s, a major sound wins)."""
    out: List[dict] = []; chapter_at = {float(sc["start"]) for sc in scenes if sc.get("chapter_card")}
    for e in C.events(scenes):
        if e["type"] == "primary": out.append({"t": e["t"], "sfx": "fast_whoosh" if e["t"] in chapter_at else "soft_transition", "source": e["what"]})
        elif e["meaningful"] and e["what"] in KIND_SFX: out.append({"t": e["t"], "sfx": KIND_SFX[e["what"]], "source": e["what"]})
    kept: List[dict] = []
    for c in sorted(out, key=lambda c: (c["t"], 0 if c["sfx"] in MAJOR else 1)):
        if any(k["sfx"] == c["sfx"] and c["t"] - k["t"] < SAME_SOUND_GAP_S for k in kept[-6:]): continue
        if kept and c["t"] - kept[-1]["t"] < MIN_GAP_S:
            if c["sfx"] in MAJOR and kept[-1]["sfx"] not in MAJOR: kept.pop()      # a major sound replaces a small one just before it
            else: continue
        if c["sfx"] not in MAJOR and sum(1 for k in kept if c["t"] - k["t"] < WINDOW_S) >= MAX_PER_WINDOW: continue
        kept.append(c)
    return kept

def mix(scenes: List[dict], voiceover: str, work: Path, duration: float, title: str = "", ffmpeg: str = "ffmpeg", log: Callable[[str], None] = lambda m: None) -> Tuple[str, List[str]]:
    """The final audio: narration + event sounds (ducked under the voice) + music bed, at -14 LUFS. Returns (path, notes); every step that fails is skipped and said."""
    work = Path(work); work.mkdir(parents=True, exist_ok=True); path, notes = str(voiceover), []
    try:
        from pakmap.audio_mix import mix_pakmap_audio, resolve_assets
        from pakmap.audio_plan import plan_audio
        cs = cues(scenes); plan = resolve_assets(plan_audio({"duration": duration}, {"cues": cs, "ambience": []}, duration=duration))
        notes += [f"missing sound {sid}: {what}" for sid, what in sorted(plan.missing.items())]
        path = str(mix_pakmap_audio(plan, voiceover, work / "rt_audio_sfx.wav", duration=duration).path); notes.append(f"{len(cs)} sounds on screen events ({60 * len(cs) / max(duration, 1):.0f} a minute)")
    except Exception as ex: notes.append(f"event sounds skipped ({type(ex).__name__}: {ex})")
    try:
        from starmap.music import add_music
        text = " ".join(sc.get("text", "") for sc in scenes)
        with_music, credits = add_music(Path(path), work / "rt_audio_music.wav", duration, text, seed=title or text[:60], ffmpeg=ffmpeg, log=log, gain=MUSIC_GAIN)
        if with_music: path = str(with_music); notes += [f"music: {c}" for c in credits]
    except Exception as ex: notes.append(f"music skipped ({type(ex).__name__}: {ex})")
    try:
        from whatif.sound import measure_loudness, normalize_loudness
        before = measure_loudness(path, ffmpeg)["lufs"]; out = normalize_loudness(path, work / "rt_audio_final.wav", ffmpeg)
        if str(out) != path: path = str(out); notes.append(f"loudness {before:.1f} -> {measure_loudness(path, ffmpeg)['lufs']:.1f} LUFS")
    except Exception as ex: notes.append(f"loudness pass skipped ({type(ex).__name__}: {ex})")
    return path, notes
