"""Loudness levelling before the mix: the narration and the background music are brought to a standard loudness first, so the
effects, ambience and Music Director levels (tuned for an ordinary narration) sit where they were meant to.

Why: a phone recording came in at -7.8 LUFS with peaks above 0 dBFS. Mixed as it was, the whole film came out near -9.6 LUFS (YouTube
plays at -14) and the opening, before the voice starts, blasted music and effects at the level of speech.

Only the gain changes (one static gain plus a peak limiter): the length and timing of the audio stay exactly the same, so alignment,
captions and cuts are untouched. Each levelled copy is cached in the render's work folder by the source file's size and time."""

from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path
from typing import Optional, Union

NARRATION_LUFS = -16.0   # spoken word for YouTube: the mix (voice + bed + effects) lands near -14
MUSIC_LUFS = -16.0       # every music track at one level, so the Music Director's volumes mean the same for any track
CLOSE_DB = 1.0           # already within this of the target: used as it is
LIMIT = 0.84             # about -1.5 dBFS peak ceiling after the gain
MAX_GAIN_DB = 18.0       # a nearly silent file is not pushed up into noise

_I_RE = re.compile(r"I:\s*(-?[\d.]+|-inf)\s*LUFS")


def integrated_lufs(path: Union[str, Path]) -> Optional[float]:
    """The file's integrated loudness (EBU R128), or None when it cannot be measured."""
    try:
        r = subprocess.run(["ffmpeg", "-nostats", "-hide_banner", "-i", str(path), "-vn", "-af", "ebur128", "-f", "null", "-"],
                           capture_output=True, text=True, timeout=900)
    except Exception:
        return None
    found = _I_RE.findall(r.stderr or "")
    if not found or found[-1] == "-inf":
        return None
    try:
        return float(found[-1])
    except ValueError:
        return None


def gain_for(measured: Optional[float], target: float) -> float:
    """dB to add (0 when unknown or already close)."""
    if measured is None or abs(measured - target) <= CLOSE_DB:
        return 0.0
    return max(-40.0, min(MAX_GAIN_DB, target - measured))


def level(path: Union[str, Path], out_dir: Union[str, Path], *, target: float, kind: str = "audio") -> str:
    """A copy of `path` at `target` LUFS (wav, same length), or `path` itself when it is already close or anything fails."""
    src = Path(path)
    try:
        st = src.stat()
    except OSError:
        return str(path)
    key = hashlib.sha1(f"{src.resolve()}|{st.st_size}|{int(st.st_mtime)}|{target}".encode()).hexdigest()[:12]
    out = Path(out_dir) / f"{kind}_level_{key}.wav"
    if out.is_file() and out.stat().st_size > 0:
        return str(out)
    measured = integrated_lufs(src)
    g = gain_for(measured, target)
    if not g:
        if measured is not None:
            print(f"[LEVEL] {kind}: {measured:.1f} LUFS, already at the standard level")
        return str(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(src), "-vn", "-af", f"volume={g:.2f}dB,alimiter=limit={LIMIT}:level=false",
           "-ar", "48000", "-c:a", "pcm_s16le", str(out)]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=900)
    except Exception as exc:
        print(f"[LEVEL] {kind}: levelling skipped ({exc})")
        return str(path)
    print(f"[LEVEL] {kind}: {measured:.1f} LUFS -> {target:.0f} LUFS ({g:+.1f} dB, peaks limited)")
    return str(out)


def level_narration(path: Union[str, Path], out_dir: Union[str, Path]) -> str:
    return level(path, out_dir, target=NARRATION_LUFS, kind="narration")


def level_music(path: Union[str, Path], out_dir: Union[str, Path]) -> str:
    return level(path, out_dir, target=MUSIC_LUFS, kind="music")
