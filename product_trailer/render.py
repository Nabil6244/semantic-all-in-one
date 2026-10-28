"""Render a Product Trailer spec with the What If renderer (whatif.engine_runner.render_spec: same Node engine, parallel parts, Stop),
then lay the music under it: cut to the trailer length, faded out over the last seconds, loudness-normalised (whatif.sound) and muxed
with whatif.app_integration.mux_narration (video stream copied, no second encode)."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, Optional

FADE_OUT_S = 2.5


def _ffmpeg() -> str:
    from map_scene.render import _ffmpeg as f

    return f()


def prepare_music(music: Path, out_wav: Path, duration: float, ffmpeg: str, fade_s: float = FADE_OUT_S) -> Path:
    fade = max(0.1, min(fade_s, duration * 0.2))
    af = f"afade=t=in:st=0:d=0.05,afade=t=out:st={max(0.0, duration - fade):.3f}:d={fade:.3f}"
    cmd = [ffmpeg, "-y", "-v", "error", "-nostdin", "-i", str(music), "-t", f"{duration:.3f}", "-af", af, "-ac", "2", "-ar", "48000", str(out_wav)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("preparing the music took too long") from exc
    if r.returncode != 0 or not out_wav.is_file():
        raise RuntimeError(f"could not prepare the music: {r.stderr[-300:]}")
    return out_wav


def render(spec_path, out_mp4, progress: Optional[Callable[[int, int], None]] = None, cancel: Optional[Callable[[], bool]] = None,
           log: Callable[[str], None] = print) -> str:
    from whatif.app_integration import mux_narration
    from whatif.engine_runner import render_spec

    spec_path, out_mp4 = Path(spec_path), Path(out_mp4)
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    music = (spec.get("product_trailer") or {}).get("music")
    voice = (spec.get("product_trailer") or {}).get("voiceover")
    engine_spec = {k: v for k, v in spec.items() if k != "product_trailer"}
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    have_music, have_voice = bool(music) and Path(music).is_file(), bool(voice) and Path(voice).is_file()
    if not have_music and not have_voice:
        render_spec(engine_spec, out_mp4, progress=progress, cancel_check=cancel, log=log)
        return str(out_mp4)
    ffmpeg = _ffmpeg()
    with tempfile.TemporaryDirectory(prefix="product_trailer_") as tmp:
        silent = Path(tmp) / "picture.mp4"
        render_spec(engine_spec, silent, progress=progress, cancel_check=cancel, log=log)
        if cancel is not None and cancel():
            raise RuntimeError("Product Trailer render cancelled.")
        if have_voice:   # the voice-over carries the film; any music sits far below it
            from .voiceover import mix_voiceover

            wav = mix_voiceover(Path(voice), Path(music) if have_music else None, Path(tmp) / "voice_mix.wav", float(spec["duration"]), ffmpeg)
            mux_narration(silent, wav, out_mp4, float(spec["duration"]), ffmpeg=ffmpeg)
            return str(out_mp4)
        wav = prepare_music(Path(music), Path(tmp) / "music.wav", float(spec["duration"]), ffmpeg)
        try:
            from whatif.sound import normalize_loudness

            wav = Path(normalize_loudness(wav, Path(tmp) / "music_norm.wav", ffmpeg))
        except Exception:  # noqa: BLE001 -- never stop a video for loudness
            pass
        mux_narration(silent, wav, out_mp4, float(spec["duration"]), ffmpeg=ffmpeg)
    return str(out_mp4)
