"""War Documentary sound (reference study: -14.4 LUFS, LRA ~4 LU, a music bed under the whole film, sound on the graphics).

    build_mix(voice, total_s, layers, out_path, state_dir, cfg) -> path or None

  music   one of the app's own bundled beds (assets/music), looped, ducked under the voice (sidechain), never louder than the narration
  sfx     the app's bundled library (assets/bundled-sfx): a whoosh where a full-frame graphic or a light flash comes in, an impact under a
          big figure, a soft text tick when a keyword label types on; spaced so they never pile up
  master  loudnorm to -14 LUFS integrated, true peak -1.5 dBTP, a narrow loudness range like the reference

Config: "music" (True), "music_track" (a file stem in assets/music), "music_db" (-17: bed level before ducking), "sfx" (True).
Nothing is downloaded; with ffmpeg missing or any input unreadable the voice alone is returned (the render never fails over sound).
"""

from __future__ import annotations

import hashlib
import logging
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

log = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[2]
MUSIC_DIR = ROOT / "assets" / "music"
SFX_DIR = ROOT / "assets" / "bundled-sfx"
SR = 44100
WAR_BEDS = ("stormfront", "dark_fog", "interloper", "despair_and_triumph", "lost_frontier")
FULL = {"tac_map", "tac_route", "map_card", "lay_document", "lay_satellite", "kit_chart", "lay_timeline", "lay_figure_hero", "lay_equipment_hero",
        "lay_stat_split", "kit_datecard", "kit_title", "kit_quote", "kit_kinetic", "lay_speaker_quote", "kit_icons"}


def _decode(path: Path, seconds: Optional[float] = None) -> Optional[np.ndarray]:
    cmd = ["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"]
    if seconds:
        cmd[3:3] = ["-t", f"{seconds:.3f}"]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=120)
        a = np.frombuffer(r.stdout, dtype=np.float32)
        return a if a.size else None
    except Exception:
        return None


def pick_track(seed: str, cfg: Dict[str, Any]) -> Optional[Path]:
    want = str(cfg.get("music_track") or "")
    if want and (MUSIC_DIR / f"{want}.opus").is_file():
        return MUSIC_DIR / f"{want}.opus"
    beds = [MUSIC_DIR / f"{b}.opus" for b in WAR_BEDS if (MUSIC_DIR / f"{b}.opus").is_file()]
    if not beds:
        return None
    h = int(hashlib.sha1(seed.encode()).hexdigest(), 16)
    return beds[h % len(beds)]


def _sfx_files(kind: str) -> List[Path]:
    d = SFX_DIR / kind
    return sorted(p for p in d.glob("*.opus")) if d.is_dir() else []


def sfx_events(layers: Sequence[Any]) -> List[Tuple[float, str, float]]:
    """(time, sfx folder, gain) for the graphics that land: spaced at least 1.2 s apart, at most one per graphic."""
    ev: List[Tuple[float, str, float]] = []
    for ly in sorted(layers, key=lambda l: l.start):
        k = ly.kind
        if k in FULL or k == "fx_flash":
            ev.append((max(0.0, ly.start - 0.15), "whoosh", 0.32))
        elif k == "bc_bigword":
            ev.append((ly.start, "impact", 0.30))
        elif k in ("bc_label", "fx_roadmap"):
            ev.append((ly.start, "text", 0.18))
    out: List[Tuple[float, str, float]] = []
    for t, kind, g in ev:
        if not out or t - out[-1][0] >= 1.2:
            out.append((t, kind, g))
    return out


def _sfx_track(total: float, events: List[Tuple[float, str, float]]) -> np.ndarray:
    track = np.zeros(int(total * SR) + SR, dtype=np.float32)
    cache: Dict[Path, Optional[np.ndarray]] = {}
    for i, (t, kind, g) in enumerate(events):
        files = _sfx_files(kind)
        if not files:
            continue
        f = files[i % len(files)]
        if f not in cache:
            cache[f] = _decode(f, 2.5)
        a = cache[f]
        if a is None:
            continue
        s = int(t * SR)
        e = min(len(track), s + len(a))
        track[s:e] += a[: e - s] * g
    return track


def build_mix(voice: Optional[str], total_s: float, layers: Sequence[Any], out_path: str, cfg: Optional[Dict[str, Any]] = None) -> Optional[str]:
    cfg = cfg or {}
    if not voice or not Path(voice).is_file() or total_s <= 0:
        return voice
    if cfg.get("music") is False and cfg.get("sfx") is False:
        return voice
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    sfx_wav = out.with_suffix(".sfx.wav")
    inputs = ["-i", str(voice)]
    parts = []
    music = pick_track(Path(voice).name, cfg) if cfg.get("music", True) is not False else None
    if music is not None:
        inputs += ["-stream_loop", "-1", "-i", str(music)]
    if cfg.get("sfx", True) is not False:
        tr = _sfx_track(total_s, sfx_events(layers))
        if np.abs(tr).max() > 0:
            pcm = (np.clip(tr, -1, 1) * 32767).astype(np.int16)
            import wave

            with wave.open(str(sfx_wav), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(SR)
                w.writeframes(pcm.tobytes())
            inputs += ["-i", str(sfx_wav)]
            parts.append("sfx")
    db = float(cfg.get("music_db", -17.0))
    T = f"{total_s:.3f}"
    fg = [f"[0:a]aresample={SR},aformat=channel_layouts=stereo,apad,atrim=0:{T},asplit=2[v][sc]"]
    mix_in = ["[v]"]
    idx = 1
    if music is not None:
        fg.append(f"[{idx}:a]aresample={SR},aformat=channel_layouts=stereo,atrim=0:{T},volume={db}dB,afade=t=in:d=1.5,"
                  f"afade=t=out:st={max(0.0, total_s - 3):.3f}:d=3[m]")
        fg.append("[m][sc]sidechaincompress=threshold=0.02:ratio=6:attack=15:release=450:makeup=1[md]")
        mix_in.append("[md]")
        idx += 1
    else:
        fg[0] = fg[0].replace(",asplit=2[v][sc]", "[v]")
    if "sfx" in parts:
        fg.append(f"[{idx}:a]aresample={SR},aformat=channel_layouts=stereo,apad,atrim=0:{T}[fx]")
        mix_in.append("[fx]")
    fg.append("".join(mix_in) + f"amix=inputs={len(mix_in)}:normalize=0:duration=first,loudnorm=I=-14:TP=-1.5:LRA=7,aresample={SR}[out]")
    cmd = ["ffmpeg", "-y", "-v", "error"] + inputs + ["-filter_complex", ";".join(fg), "-map", "[out]", "-c:a", "aac", "-b:a", "192k", str(out)]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=1800)
        return str(out)
    except Exception as exc:  # noqa: BLE001 - sound is an addition: the voice alone still makes the film
        log.warning("War sound mix failed, using the voice alone: %s", getattr(exc, "stderr", b"")[-400:] if hasattr(exc, "stderr") else exc)
        return voice
    finally:
        try:
            sfx_wav.unlink()
        except OSError:
            pass
