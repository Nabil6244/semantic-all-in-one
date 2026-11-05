"""Rules Horror sound: the voice-over first; under it a low continuous bed (synthesised by ffmpeg -- no download, no file); short hits on
rule cards, glitches and sight lines from the bundled impact / riser / whoosh folders; the voice ducks the bed; loudness -14 LUFS."""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

SFX_ROOT = Path(__file__).resolve().parent.parent / "assets" / "bundled-sfx"
BED_GAIN, CUE_GAIN = 0.55, 0.45


def _pick(kind: str, key: str, root: Path = SFX_ROOT) -> Optional[Path]:
    files = sorted((root / kind).glob("*.opus")) + sorted((root / kind).glob("*.wav")) + sorted((root / kind).glob("*.mp3"))
    if not files:
        return None
    return files[int(hashlib.sha1(key.encode()).hexdigest(), 16) % len(files)]


def plan_cues(beats: List[Dict[str, Any]], root: Path = SFX_ROOT) -> List[Dict[str, Any]]:
    """[{t, kind, file, gain}] -- a rule card lands with an impact, a glitch is a riser into an impact, a sight line is a quiet whoosh.
    No two cues closer than 0.5 s, none at a negative time."""
    raw = []
    for i, b in enumerate(beats):
        if b.get("card"):
            raw.append((b["start"], "impact", 1.0))
        if b.get("glitch"):
            raw.append((b["start"] - 1.1, "riser", 0.7))
            raw.append((b["start"], "impact", 1.0))
        if any(m["kind"] == "sight" for m in b.get("marks", [])) and (i == 0 or not any(m["kind"] == "sight" for m in beats[i - 1].get("marks", []))):
            raw.append((b["start"], "whoosh", 0.6))
    cues, last = [], -9.0
    for t, kind, gain in sorted(raw):
        t = max(0.0, t)
        if t - last < 0.5:
            continue
        f = _pick(kind, f"{kind}{t:.2f}", root)
        if f:
            cues.append({"t": round(t, 3), "kind": kind, "file": str(f), "gain": gain})
            last = t
    return cues


def mix(voice: Path, cues: List[Dict[str, Any]], out_wav: Path, duration: float, ffmpeg: str) -> Path:
    """voice + synthesised low bed (ducked under the voice) + cues -> one wav of `duration` seconds."""
    cmd = [ffmpeg, "-y", "-v", "error", "-nostdin", "-i", str(voice),
           "-f", "lavfi", "-t", f"{duration:.3f}", "-i", "anoisesrc=color=brown:amplitude=0.5:sample_rate=48000",
           "-f", "lavfi", "-t", f"{duration:.3f}", "-i", "sine=frequency=48:sample_rate=48000"]
    for c in cues:
        cmd += ["-i", c["file"]]
    fl = ["[0:a]aresample=48000,aformat=channel_layouts=stereo,asplit=2[v][vs]",
          f"[1:a]lowpass=f=140,volume={0.9 * BED_GAIN},tremolo=f=0.15:d=0.4[n]",
          f"[2:a]volume={0.35 * BED_GAIN}[s]",
          "[n][s]amix=inputs=2:normalize=0,aformat=channel_layouts=stereo[bed0]",
          "[bed0][vs]sidechaincompress=threshold=0.02:ratio=6:attack=40:release=500[bed]"]
    labels = ["[v]", "[bed]"]
    for k, c in enumerate(cues):
        ms = int(c["t"] * 1000)
        fl.append(f"[{3 + k}:a]aresample=48000,aformat=channel_layouts=stereo,volume={CUE_GAIN * c['gain']},adelay={ms}|{ms}[c{k}]")
        labels.append(f"[c{k}]")
    fl.append("".join(labels) + f"amix=inputs={len(labels)}:duration=first:normalize=0,atrim=0:{duration:.3f}[o]")
    cmd += ["-filter_complex", ";".join(fl), "-map", "[o]", "-ac", "2", "-ar", "48000", str(out_wav)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    if r.returncode != 0 or not Path(out_wav).is_file():
        raise RuntimeError(f"could not mix the sound: {r.stderr[-400:]}")
    return Path(out_wav)
