"""StarMap's music bed: cinematic tracks under the whole video, chosen by the story's mood, chained with crossfades to its
length, and ducked under the narrator (it rises in the gaps, dips while the voice speaks). Added after the sound design's
mix (narration + effects + ambience), so the shared pakMap mixer is untouched.

The tracks ship in assets/music (Kevin MacLeod, incompetech.com, Creative Commons Attribution 4.0): every video that uses
one lists its credit line, exactly as the licence asks."""

from __future__ import annotations

import hashlib
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable, List, Optional, Tuple

TRACKS = {   # file stem -> (title, moods)
    "lost_frontier": ("Lost Frontier", ("wonder", "epic")),
    "interloper": ("Interloper", ("mystery",)),
    "echoes_of_time_v2": ("Echoes of Time v2", ("wonder",)),
    "ascending_the_vale": ("Ascending the Vale", ("epic", "wonder")),
    "long_note_four": ("Long Note Four", ("mystery", "wonder")),
    "despair_and_triumph": ("Despair and Triumph", ("epic",)),
    "stormfront": ("Stormfront", ("epic", "mystery")),
    "dark_fog": ("Dark Fog", ("mystery",)),
}
MOOD_WORDS = {
    "epic": r"\b(first|record|farthest|fastest|historic|triumph|launch\w*|journey|greatest|never before|survive\w*|race\w*)\b",
    "mystery": r"\b(unknown|strange|mystery|mysterious|dark|silence|silent|alone|lost|edge|nobody knows|secret\w*|unexplained)\b",
}
MUSIC_GAIN = 0.2            # about -14 dB under full scale before ducking: a bed, never a song over the narrator
CROSSFADE_S, FADE_IN_S, FADE_OUT_S = 5.0, 3.0, 5.0
# ducking under the narrator: down in 40 ms when the voice starts; back up in 300 ms, so the music swells in the
# short breaths between sentences (900 ms only came halfway back in a narrator's usual 0.5-1 s pauses)
DUCK_ATTACK_MS, DUCK_RELEASE_MS = 40, 300


def music_dir() -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / "assets" / "music"


def credit(stem: str) -> str:
    title = TRACKS[stem][0]
    return (f'Music: "{title}" by Kevin MacLeod (incompetech.com), licensed under Creative Commons: By Attribution 4.0 '
            f"(http://creativecommons.org/licenses/by/4.0/)")


def mood_of(text: str) -> str:
    scores = {m: len(re.findall(rx, text or "", re.I)) for m, rx in MOOD_WORDS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] >= 2 else "wonder"


# What If's bed: sparse, slow, drone-led (documentary minimalism), never a theme
AMBIENT = ("long_note_four", "echoes_of_time_v2", "dark_fog", "lost_frontier")


def choose(text: str, duration: float, seed: str = "", mood: Optional[str] = None) -> List[str]:
    """Tracks of the story's mood (or the given one: "ambient" = AMBIENT), in an order fixed by the title (the same video always
    gets the same music), until they cover the duration."""
    mood = mood or mood_of(text)
    folder = music_dir()
    pool = [s for s, (_, moods) in TRACKS.items() if (s in AMBIENT if mood == "ambient" else mood in moods) and (folder / f"{s}.opus").is_file()]
    if not pool:
        return []
    k = int(hashlib.sha1(seed.encode("utf-8")).hexdigest(), 16) % len(pool)
    pool = pool[k:] + pool[:k]
    out, total = [], 0.0
    while total < duration + CROSSFADE_S and len(out) < 24:
        s = pool[len(out) % len(pool)]
        out.append(s)
        total += _length(folder / f"{s}.opus") - CROSSFADE_S
    return out


def _length(path: Path) -> float:
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                           capture_output=True, text=True, timeout=30)
        return float(r.stdout.strip())
    except Exception:
        return 240.0


def add_music(mix: Path, out: Path, duration: float, text: str, seed: str = "", ffmpeg: str = "ffmpeg",
              log: Callable[[str], None] = lambda s: None, mood: Optional[str] = None, gain: Optional[float] = None) -> Tuple[Optional[Path], List[str]]:
    """The mix with the music bed under it -> (the new file, the credit lines); (None, []) when there is no music to add."""
    stems = choose(text, duration, seed, mood)
    if not stems:
        return None, []
    folder = music_dir()
    args = [ffmpeg, "-v", "error", "-y", "-i", str(mix)]
    for s in stems:
        args += ["-i", str(folder / f"{s}.opus")]
    chain, last = [], "1:a"
    for i in range(2, len(stems) + 1):
        chain.append(f"[{last}][{i}:a]acrossfade=d={CROSSFADE_S}:c1=tri:c2=tri[m{i}]")
        last = f"m{i}"
    fade_out_at = max(0.0, duration - FADE_OUT_S)
    chain.append(f"[{last}]atrim=0:{duration:.3f},asetpts=PTS-STARTPTS,volume={MUSIC_GAIN if gain is None else gain},"
                 f"afade=t=in:d={FADE_IN_S},afade=t=out:st={fade_out_at:.3f}:d={FADE_OUT_S}[bed]")
    chain.append("[0:a]asplit=2[main][key]")
    # ducked by the mix itself (the narrator above all): down quickly when the voice starts, back up in the gaps
    chain.append(f"[bed][key]sidechaincompress=threshold=0.025:ratio=8:attack={DUCK_ATTACK_MS}:release={DUCK_RELEASE_MS}:makeup=1[duck]")
    chain.append("[main][duck]amix=inputs=2:normalize=0:duration=first,alimiter=limit=0.95[out]")
    args += ["-filter_complex", ";".join(chain), "-map", "[out]", "-c:a", "pcm_s16le", str(out)]
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0 or not out.is_file():
        log(f"[StarMap] music skipped: {(r.stderr or '').strip()[-300:]}")
        return None, []
    log(f"[StarMap] music: {', '.join(TRACKS[s][0] for s in stems)} ({mood_of(text)})")
    return out, [credit(s) for s in dict.fromkeys(stems)]
