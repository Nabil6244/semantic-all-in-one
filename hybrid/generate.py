"""Hybrid plan + voiceover -> final video, through the existing pakMap generator (same renderer, sound design, export).

H1 entry point: a hand-authored plan, no AI. The compiled pakMap script is written next to the render as hybrid_script.csv
(compiler output, for debugging); the plan JSON is the source of truth."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Sequence

from pakmap.app_integration import PakmapResult, generate_pakmap_video

from .compile import HybridCompileError, explain, longest_slot, plan_to_rows, rows_to_csv, spec_extra
from .plan import HybridPlan


def fit_to_audio(plan: HybridPlan, voiceover_path: "str | Path", *, log=print, tolerance: float = 1.5) -> HybridPlan:
    """The plan was made for the narration it was planned against. If the voiceover file's length differs by a little (a re-export, a trimmed
    tail), end the plan where the audio ends instead of letting layers run past it. A big difference is left alone: that is the wrong audio."""
    import copy

    from pakmap.app_integration import voiceover_duration

    actual = voiceover_duration(voiceover_path)
    if not actual or abs(actual - plan.duration) < 0.02 or abs(actual - plan.duration) > tolerance:
        return plan
    fitted = copy.deepcopy(plan)
    fitted.duration = round(float(actual), 3)
    if fitted.beats:
        last = fitted.beats[-1]
        last.end = fitted.duration
        if last.end <= last.start + 0.5:  # the tail was all there was to the last beat: fold it away rather than leave a sliver
            return plan
    log(f"[Hybrid] the voiceover is {actual:.2f}s but the plan was made for {plan.duration:.2f}s: the plan now ends with the audio")
    return fitted


def watermark_png(wm: dict, size: "tuple[int, int]", dest: Path) -> Path:
    """The channel name exactly as the page draws it (pakmap-engine/lib/draw.mjs drawWatermark): Montserrat ExtraBold 22 px on a
    1920-wide frame, caps, 1 px letter spacing, white, a yellow play triangle before it, 36 px from the corner, 60 % opacity."""
    from PIL import Image, ImageDraw, ImageFont

    W, H = size
    k = W / 1920.0
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    font_path = Path(__file__).resolve().parents[1] / "pakmap-engine" / "assets" / "fonts" / "Montserrat-VF.ttf"
    try:
        f = ImageFont.truetype(str(font_path), int(round(22 * k)))
        try:
            f.set_variation_by_axes([800])
        except Exception:
            pass
    except OSError:
        f = ImageFont.load_default()
    text = str(wm.get("text", "")).upper()
    tw = sum(d.textlength(ch, font=f) for ch in text) + len(text) * 1 * k
    left = wm.get("position") == "bl"
    tx = 36 * k + 30 * k if left else W - 36 * k - tw
    ix = tx - 30 * k
    base = H - 36 * k
    a = int(255 * float(wm.get("opacity", 0.6) if wm.get("opacity") is not None else 0.6))
    d.polygon([(ix + 6 * k, base - 17 * k), (ix + 6 * k, base + 1 * k), (ix + 21 * k, base - 8 * k)], fill=(0xFB, 0xE0, 0x40, a))
    x = tx
    for ch in text:
        d.text((x, base), ch, font=f, fill=(255, 255, 255, a), anchor="ls")
        x += d.textlength(ch, font=f) + 1 * k
    img.save(dest)
    return dest


def add_watermark(video: Path, wm: dict, work: Path) -> str:
    """Lay the channel name over a finished video (one ffmpeg pass, the sound copied). '' when done, else why not."""
    import subprocess

    try:
        from map_scene.render import _ffmpeg

        ffmpeg = _ffmpeg()
    except Exception:
        ffmpeg = "ffmpeg"
    try:
        probe = subprocess.run([str(Path(ffmpeg).with_name("ffprobe")) if Path(ffmpeg).is_file() else "ffprobe", "-v", "error",
                                "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0", str(video)],
                               capture_output=True, text=True, timeout=60)
        size = tuple(int(v) for v in probe.stdout.strip().split(",")[:2])
        png = watermark_png(wm, size, Path(work) / "channel_name.png")
        tmp = video.with_name(f".{video.stem}.wm{video.suffix}")
        r = subprocess.run([ffmpeg, "-y", "-v", "error", "-i", str(video), "-loop", "1", "-i", str(png), "-filter_complex",
                            "[0:v][1:v]overlay=0:0:shortest=1:format=auto[v]", "-map", "[v]", "-map", "0:a?", "-c:v", "libx264",
                            "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart", str(tmp)],
                           capture_output=True, text=True, timeout=6 * 3600)
        if r.returncode != 0 or not tmp.is_file():
            tmp.unlink(missing_ok=True)
            return (r.stderr or "ffmpeg failed").strip()[-200:]
        tmp.replace(video)
        return ""
    except Exception as exc:
        return str(exc)[:200]


def generate_hybrid_video(plan: HybridPlan, voiceover_path: "str | Path", output_path: "str | Path", *, work_dir: "str | Path",
                          whisper_words: Optional[Sequence] = None, **kw) -> PakmapResult:
    """`kw` goes to generate_pakmap_video (watermark, resolution, sound_design, progress_cb, cancel_check, the media providers...).
    Never raises: failures come back as ok=False with messages that name the beat and layer."""
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    plan = fit_to_audio(plan, voiceover_path, log=kw.get("log", print))
    try:
        rows, line_map, notes = plan_to_rows(plan)
    except HybridCompileError as exc:
        return PakmapResult(False, list(exc.problems))
    (work / "hybrid_plan.json").write_text(__import__("json").dumps(plan.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    csv_path = work / "hybrid_script.csv"
    csv_path.write_text(rows_to_csv(rows), encoding="utf-8")
    log = kw.get("log", print)
    for n in notes:
        log(f"[Hybrid] {n}")
    # times are explicit in the plan, so the narration words are only needed to satisfy the generator's checks
    words = list(whisper_words) if whisper_words else [("hybrid", 0.0, 0.1)]
    # YouTube gives short clips by default; ask for as much as the longest slot needs (the providers cap it themselves)
    options = {"youtube_clip_duration": float(min(8.0, max(4.0, longest_slot(plan)))), "dedupe": True}
    options.update(kw.pop("media_options", None) or {})
    # the channel name is laid over the finished video, not drawn by the page on every frame: with it in the spec the renderer cannot
    # copy footage-only frames straight from their clips (pakmap-engine/lib/footage_pass.mjs), so the whole video went through the page
    wm = kw.get("watermark")
    late_wm = isinstance(wm, dict) and str(wm.get("text") or "").strip() and wm.get("enabled", True) is not False
    if late_wm:
        kw["watermark"] = None
    result = generate_pakmap_video(csv_path, voiceover_path, output_path, work_dir=work, whisper_words=words, spec_extra=spec_extra(plan), media_options=options, **kw)
    if late_wm and result.ok and result.output_path:
        why = add_watermark(Path(result.output_path), wm, work)
        if why:
            log(f"[Hybrid] the channel name could not be added ({why}); the video is kept without it")
            result.warnings = list(result.warnings or []) + [f"channel name not added: {why}"]
    if not result.ok:
        result.errors = explain(line_map, result.errors)
    result.warnings = explain(line_map, result.warnings) + notes
    return result
