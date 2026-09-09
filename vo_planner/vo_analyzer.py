"""VO Analyzer — exact timing from Whisper (no LLM, no duration-from-text)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable, List, Optional, Sequence, Tuple

from smart_editing import get_cached_whisper_words

from .cache import (
    load_cached_vo_analysis,
    save_cached_vo_analysis,
    store_whisper_words_in_smart_cache,
)
from .schema import VOAnalysis, VOSentence, VOWord

ProgressCallback = Callable[[str, Optional[float]], None]

# Pause longer than this (seconds) starts a new sentence boundary candidate.
_PAUSE_SPLIT = 0.55
# Hard sentence-ending punctuation.
_SENTENCE_END = frozenset(".?!")


def _emit(cb: Optional[ProgressCallback], message: str, fraction: Optional[float] = None) -> None:
    if cb:
        cb(message, fraction)


def _load_whisper_words(
    audio_path: Path,
    *,
    state_dir: Optional[Path],
    whisper_model: str,
    on_progress: Optional[ProgressCallback],
) -> List[Tuple[str, float, float]]:
    if state_dir is not None:
        cached = get_cached_whisper_words(state_dir, audio_path)
        if cached:
            _emit(on_progress, "Reusing cached Whisper alignment…", 0.15)
            return [(str(w), float(s), float(e)) for w, s, e in cached]

    _emit(on_progress, f"Transcribing voiceover ({whisper_model})…", 0.08)
    from video_generator import transcribe_audio

    words = transcribe_audio(str(audio_path), whisper_model)
    tuples = [(str(w), float(s), float(e)) for w, s, e in words]
    if state_dir is not None:
        store_whisper_words_in_smart_cache(state_dir, audio_path, tuples)
    return tuples


def _split_sentences(words: Sequence[Tuple[str, float, float]]) -> List[VOSentence]:
    if not words:
        return []

    sentences: List[VOSentence] = []
    buf: List[Tuple[str, float, float]] = []
    prev_end = float(words[0][1])

    def flush(pause_before: float, pause_after: float = 0.0) -> None:
        nonlocal buf
        if not buf:
            return
        text = " ".join(w for w, _, _ in buf).strip()
        start = float(buf[0][1])
        end = float(buf[-1][2])
        dur = max(0.05, end - start)
        wc = len(buf)
        density = wc / dur
        sentences.append(
            VOSentence(
                text=text,
                start=start,
                end=end,
                word_count=wc,
                pause_before=round(pause_before, 3),
                pause_after=round(pause_after, 3),
                speech_density=round(density, 3),
            )
        )
        buf = []

    pause_before = 0.0
    for i, (word, start, end) in enumerate(words):
        gap = max(0.0, float(start) - prev_end) if i > 0 else 0.0
        if buf and gap >= _PAUSE_SPLIT:
            flush(pause_before, pause_after=gap)
            pause_before = gap
        buf.append((word, float(start), float(end)))
        # Also split on sentence-ending punctuation attached to the token.
        token = word.rstrip()
        if token and token[-1] in _SENTENCE_END and len(buf) >= 3:
            next_gap = 0.0
            if i + 1 < len(words):
                next_gap = max(0.0, float(words[i + 1][1]) - float(end))
            flush(pause_before, pause_after=next_gap)
            pause_before = next_gap
        prev_end = float(end)

    flush(pause_before, pause_after=0.0)

    # Annotate pause_after from following sentence gaps when missing.
    for i in range(len(sentences) - 1):
        gap = max(0.0, sentences[i + 1].start - sentences[i].end)
        if sentences[i].pause_after <= 0:
            sentences[i].pause_after = round(gap, 3)
        if sentences[i + 1].pause_before <= 0:
            sentences[i + 1].pause_before = round(gap, 3)
    return sentences


def _detect_pauses(
    words: Sequence[Tuple[str, float, float]],
    audio_end: float,
    *,
    min_pause: float = 0.35,
) -> List[dict]:
    pauses: List[dict] = []
    if not words:
        return pauses
    # Leading silence
    if float(words[0][1]) >= min_pause:
        s, e = 0.0, float(words[0][1])
        pauses.append({"start": s, "end": e, "duration": e - s})
    for i in range(len(words) - 1):
        gap_start = float(words[i][2])
        gap_end = float(words[i + 1][1])
        dur = gap_end - gap_start
        if dur >= min_pause:
            pauses.append({"start": gap_start, "end": gap_end, "duration": dur})
    # Trailing silence
    tail = audio_end - float(words[-1][2])
    if tail >= min_pause:
        pauses.append(
            {"start": float(words[-1][2]), "end": audio_end, "duration": tail}
        )
    return pauses


def analyze_voiceover(
    audio_path: Path | str,
    *,
    state_dir: Optional[Path] = None,
    whisper_model: str = "base",
    on_progress: Optional[ProgressCallback] = None,
    force: bool = False,
) -> VOAnalysis:
    """Build VOAnalysis from actual audio. Never estimates duration from text alone."""
    path = Path(audio_path)
    if not path.is_file():
        raise FileNotFoundError(f"voiceover not found: {path}")

    if state_dir is not None and not force:
        cached = load_cached_vo_analysis(state_dir, path, whisper_model)
        if cached and cached.get("words"):
            _emit(on_progress, "Reusing cached VO analysis…", 0.2)
            return _analysis_from_cache_dict(cached)

    words = _load_whisper_words(
        path,
        state_dir=state_dir,
        whisper_model=whisper_model,
        on_progress=on_progress,
    )
    if not words:
        raise RuntimeError("Whisper returned no words for voiceover")

    _emit(on_progress, "Detecting sentence boundaries and pauses…", 0.35)
    audio_duration = max(float(words[-1][2]), float(words[0][1]))
    # Prefer container duration when available
    try:
        proc = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            audio_duration = max(audio_duration, float(proc.stdout.strip()))
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass

    sentences = _split_sentences(words)
    pauses = _detect_pauses(words, audio_duration)
    densities = [s.speech_density for s in sentences if s.speech_density > 0]
    mean_density = sum(densities) / len(densities) if densities else 0.0

    analysis = VOAnalysis(
        audio_path=str(path.resolve()),
        audio_duration=round(audio_duration, 3),
        words=[VOWord(w, s, e) for w, s, e in words],
        sentences=sentences,
        pauses=pauses,
        mean_speech_density=round(mean_density, 3),
        whisper_model=whisper_model,
    )

    if state_dir is not None:
        # Persist analysis without full word list in a parallel cache key;
        # words live in smart_editing cache for reuse.
        payload = analysis.to_dict()
        payload["words"] = [[w.word, w.start, w.end] for w in analysis.words]
        save_cached_vo_analysis(state_dir, path, whisper_model, payload)

    _emit(on_progress, f"VO analyzed — {len(sentences)} sentences, {audio_duration:.1f}s", 0.45)
    return analysis


def _analysis_from_cache_dict(data: dict) -> VOAnalysis:
    words_raw = data.get("words") or []
    words = [VOWord(str(w), float(s), float(e)) for w, s, e in words_raw]
    sentences = [
        VOSentence(
            text=str(s.get("text") or ""),
            start=float(s.get("start") or 0),
            end=float(s.get("end") or 0),
            word_count=int(s.get("word_count") or 0),
            pause_before=float(s.get("pause_before") or 0),
            pause_after=float(s.get("pause_after") or 0),
            speech_density=float(s.get("speech_density") or 0),
        )
        for s in (data.get("sentences") or [])
        if isinstance(s, dict)
    ]
    if not sentences and words:
        sentences = _split_sentences([(w.word, w.start, w.end) for w in words])
    pauses = [p for p in (data.get("pauses") or []) if isinstance(p, dict)]
    return VOAnalysis(
        audio_path=str(data.get("audio_path") or ""),
        audio_duration=float(data.get("audio_duration") or (words[-1].end if words else 0)),
        words=words,
        sentences=sentences,
        pauses=pauses,
        mean_speech_density=float(data.get("mean_speech_density") or 0),
        whisper_model=str(data.get("whisper_model") or ""),
    )
