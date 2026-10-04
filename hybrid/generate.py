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
    result = generate_pakmap_video(csv_path, voiceover_path, output_path, work_dir=work, whisper_words=words, spec_extra=spec_extra(plan), media_options=options, **kw)
    if not result.ok:
        result.errors = explain(line_map, result.errors)
    result.warnings = explain(line_map, result.warnings) + notes
    return result
