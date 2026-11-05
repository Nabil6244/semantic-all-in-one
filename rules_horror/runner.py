"""CSV + voice-over -> finished video, from the command line:
    python -m rules_horror --csv story.csv --voice voice.wav --out film.mp4 [--words words.json] [--seconds 60] [--width 1280 --height 720]
`--seconds` cuts the voice-over (and the story) to that many seconds for a quick test. A CSV run makes no Gemini call: the narrator's words come
from the local Whisper model (or from --words, a JSON list of [word, start, end]), the rows are placed on them by product_trailer.voiceover.align_lines."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


def _ffmpeg() -> str:
    from map_scene.render import _ffmpeg as f
    return f()


def get_words(voice: Path, words_json: Optional[Path], log: Callable[[str], None]) -> List[Any]:
    if words_json and Path(words_json).is_file():
        return [tuple(w) if not isinstance(w, dict) else w for w in json.loads(Path(words_json).read_text(encoding="utf-8"))]
    import video_generator as vg
    log("[Rules Horror] transcribing the voice-over (local Whisper, no network)")
    return list(vg.transcribe_audio(str(voice), "base"))


def build(csv_path, voice: Path, words: List[Any], duration: float, *, full_duration: Optional[float] = None, width: int = 1280, height: int = 720, fps: int = 24,
          pictures: Optional[Dict[str, str]] = None, media_dir: Optional[Path] = None, scheme: str = "mono") -> Dict[str, Any]:
    from product_trailer.voiceover import align_lines
    from .check import check_screen, check_story
    from .compile import compile_spec, stage_media
    from .csv_io import read_csv
    from .planner import plan
    data = read_csv(csv_path)
    lines = [r["line"] for r in data["rows"]]
    align = align_lines(lines, words, full_duration or duration)       # the whole story is aligned; a short test then cuts it at `duration`
    from . import profiles
    prof = profiles.get(profiles.pick(data, scheme)) if scheme in ("auto",) + tuple(profiles.PROFILES) else None    # auto: the reference look that fits this story
    pl = plan(data, align, words, duration, pictures=pictures, profile=prof)
    if prof:
        pl["stats"]["look"] = prof["name"]
    media = stage_media(pl, media_dir) if (media_dir and pictures) else {}
    spec = compile_spec(pl, width=width, height=height, fps=fps, media=media, media_dir=media_dir if media else None, scheme=prof["scheme"] if prof else scheme,
                        look=prof["look"] if prof else None, card_style=prof["card"] if prof else None)
    warnings = check_story(data, align, duration) + check_screen(pl)      # warnings only: they never stop a render
    return {"data": data, "align": align, "plan": pl, "spec": spec, "warnings": warnings}


def generate(csv_path, voice, out_dir, *, words: Optional[List[Any]] = None, words_json=None, seconds: Optional[float] = None, width: int = 1280,
             height: int = 720, fps: int = 24, pictures: Optional[Dict[str, str]] = None, log: Callable[[str], None] = print, scheme: str = "mono") -> Dict[str, Any]:
    """Plan the film: rows placed on the voice, spec written to out_dir/spec.json with its plan (beats, notes, warnings, Flow requests). No render, no Gemini."""
    from product_trailer.voiceover import audio_seconds
    from . import assets
    voice, out_dir = Path(voice), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    full = audio_seconds(voice)
    if full <= 0:
        raise RuntimeError(f"cannot read the voice-over: {voice}")
    duration = min(full, float(seconds)) if seconds else full
    if words is None:
        words = get_words(voice, words_json, log)
    built = build(csv_path, voice, words, duration, full_duration=full, width=width, height=height, fps=fps, pictures=pictures, media_dir=out_dir / "media", scheme=scheme)
    pl = built["plan"]
    reqs = assets.requests(built["data"])
    spec_path = out_dir / "spec.json"
    spec_path.write_text(json.dumps(built["spec"]), encoding="utf-8")
    (out_dir / "plan.json").write_text(json.dumps({"beats": pl["beats"], "notes": pl["notes"], "stats": pl["stats"], "warnings": built["warnings"],
                                                  "duration": duration, "voice": str(voice), "requests": reqs}, indent=1), encoding="utf-8")
    return {"spec_path": str(spec_path), "plan_path": str(out_dir / "plan.json"), "notes": pl["notes"], "warnings": built["warnings"], "stats": pl["stats"],
            "requests": reqs, "duration": duration}


def render_planned(spec_path, out_mp4, *, voice=None, log: Callable[[str], None] = print, progress=None, cancel=None) -> Dict[str, Any]:
    """Render a generated spec: picture (What If renderer), then the sound mix and the mux. `voice` defaults to the one recorded in plan.json."""
    from whatif.app_integration import mux_narration
    from whatif.engine_runner import render_spec
    from whatif.sound import normalize_loudness
    from .sound import mix, plan_cues
    spec_path, out_mp4 = Path(spec_path), Path(out_mp4)
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    info = json.loads((spec_path.parent / "plan.json").read_text(encoding="utf-8"))
    voice = Path(voice or info["voice"])
    duration = float(spec["duration"])
    ffmpeg = _ffmpeg()
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="rules_horror_") as tmp:
        silent = Path(tmp) / "picture.mp4"
        render_spec(spec, silent, progress=progress, cancel_check=cancel, log=log)
        if cancel is not None and cancel():
            raise RuntimeError("Rules Horror render cancelled.")
        cues = plan_cues(info["beats"])
        wav = mix(voice, cues, Path(tmp) / "mix.wav", duration, ffmpeg)
        try:
            wav = Path(normalize_loudness(wav, Path(tmp) / "norm.wav", ffmpeg))
        except Exception:  # noqa: BLE001 -- never stop a video for loudness
            pass
        mux_narration(silent, wav, out_mp4, duration, ffmpeg=ffmpeg)
    return {"output": str(out_mp4), "cues": len(cues), "duration": duration}


def render(csv_path, voice, out_mp4, *, words_json=None, seconds: Optional[float] = None, width: int = 1280, height: int = 720, fps: int = 24,
           log: Callable[[str], None] = print, progress=None, cancel=None, pictures: Optional[Dict[str, str]] = None, scheme: str = "mono") -> Dict[str, Any]:
    out_mp4 = Path(out_mp4)
    work = out_mp4.with_suffix("").parent / (out_mp4.stem + "_work")
    g = generate(csv_path, voice, work, words_json=words_json, seconds=seconds, width=width, height=height, fps=fps, pictures=pictures, log=log, scheme=scheme)
    for n in g["notes"] + g["warnings"]:
        log(f"[Rules Horror] note: {n}")
    log(f"[Rules Horror] {g['stats']}")
    r = render_planned(g["spec_path"], out_mp4, voice=voice, log=log, progress=progress, cancel=cancel)
    return {**r, "stats": g["stats"], "notes": g["notes"], "warnings": g["warnings"]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="rules_horror")
    ap.add_argument("--csv", required=True); ap.add_argument("--voice", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--words"); ap.add_argument("--seconds", type=float); ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720); ap.add_argument("--fps", type=int, default=24)
    from .profiles import PROFILES
    ap.add_argument("--scheme", default="auto", choices=["auto", *PROFILES, "story", "mono", "dark", "colour", "deep"])
    a = ap.parse_args(argv)
    res = render(a.csv, a.voice, a.out, words_json=a.words, seconds=a.seconds, width=a.width, height=a.height, fps=a.fps, scheme=a.scheme)
    print(json.dumps(res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
