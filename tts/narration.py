"""Collect spoken narration only — never visual prompts or search queries."""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Iterable, Optional

from tts.errors import TTSError

SCRIPT_PLACEHOLDER = "Paste your narration script here..."
VOICE_NARRATION_PLACEHOLDER = (
    "Paste the full narration script here to generate with your cloned voice…"
)
# Soft cap per Qwen generate call — long single prompts often stall on MPS.
NARRATION_CHUNK_CHARS = 320
_VISUAL_COLUMNS = frozenset(
    {
        "prompt",
        "stock",
        "visual_description",
        "visual_goal",
        "search_queries",
        "asset_type",
    }
)


def validate_text(text: str) -> str:
    cleaned = (text or "").strip()
    if not cleaned or cleaned in (SCRIPT_PLACEHOLDER, VOICE_NARRATION_PLACEHOLDER):
        raise TTSError(
            "No narration text to speak. Paste the full script, or load a CSV "
            "whose script_segment column contains the spoken words.",
            "invalid_text",
        )
    letters = sum(ch.isalnum() for ch in cleaned)
    if letters < 3:
        raise TTSError(
            "Narration text is too short or is not speakable English.",
            "invalid_text",
        )
    return cleaned


def narration_from_csv(path: Path) -> str:
    """Join script_segment values in scene_number order. Ignores prompt/stock."""
    path = Path(path)
    if not path.is_file():
        raise TTSError(f"Script CSV not found: {path}", "invalid_text")
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or "script_segment" not in reader.fieldnames:
            raise TTSError(
                f"{path} must include a script_segment column "
                f"(found: {reader.fieldnames}).",
                "invalid_text",
            )
        rows = list(reader)

    if "scene_number" in (reader.fieldnames or []):
        def sort_key(row: dict) -> tuple:
            raw = str(row.get("scene_number", "")).strip()
            try:
                return (0, int(raw))
            except ValueError:
                return (1, raw)

        rows.sort(key=sort_key)

    segments = [
        (row.get("script_segment") or "").strip()
        for row in rows
        if (row.get("script_segment") or "").strip()
    ]
    if not segments:
        raise TTSError(
            "CSV has no script_segment narration to send to TTS.",
            "invalid_text",
        )
    return " ".join(segments)


def narration_from_visual_plan(plan) -> str:
    scenes = getattr(plan, "scenes", None) or []
    parts = []
    for scene in scenes:
        text = str(getattr(scene, "narration", "") or "").strip()
        if text:
            parts.append(text)
    if not parts:
        raise TTSError("Visual plan has no narration text.", "invalid_text")
    return " ".join(parts)


def collect_narration(
    *,
    script_text: str = "",
    csv_path: Optional[Path] = None,
    visual_plan=None,
) -> str:
    """Prefer the pasted full script, then plan.narration, then CSV script_segment."""
    pasted = (script_text or "").strip()
    if pasted and pasted not in (SCRIPT_PLACEHOLDER, VOICE_NARRATION_PLACEHOLDER):
        return validate_text(pasted)
    if visual_plan is not None:
        return validate_text(narration_from_visual_plan(visual_plan))
    if csv_path:
        return validate_text(narration_from_csv(Path(csv_path)))
    raise TTSError(
        "No narration text found. Paste a script in the Voice section "
        "(or AI Script / CSV), then generate narration.",
        "invalid_text",
    )


def split_narration_chunks(
    text: str,
    *,
    max_chars: int = NARRATION_CHUNK_CHARS,
) -> list[str]:
    """Split spoken text into stable sentence-ish chunks for safer TTS generation."""
    cleaned = validate_text(text)
    max_chars = max(120, int(max_chars))
    if len(cleaned) <= max_chars:
        return [cleaned]

    # Prefer sentence boundaries, then commas, then hard wrap.
    parts = re.split(r"(?<=[.!?])\s+", cleaned)
    chunks: list[str] = []
    buf = ""
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if not buf:
            buf = part
            continue
        if len(buf) + 1 + len(part) <= max_chars:
            buf = f"{buf} {part}"
            continue
        chunks.extend(_hard_wrap_chunk(buf, max_chars))
        buf = part
    if buf:
        chunks.extend(_hard_wrap_chunk(buf, max_chars))
    return [c for c in chunks if c.strip()]


def _hard_wrap_chunk(text: str, max_chars: int) -> list[str]:
    text = (text or "").strip()
    if len(text) <= max_chars:
        return [text] if text else []
    out: list[str] = []
    words = text.split()
    buf: list[str] = []
    size = 0
    for word in words:
        add = len(word) + (1 if buf else 0)
        if buf and size + add > max_chars:
            out.append(" ".join(buf))
            buf = [word]
            size = len(word)
        else:
            buf.append(word)
            size += add
    if buf:
        out.append(" ".join(buf))
    return out


def assert_not_visual_prompt(text: str, forbidden: Iterable[str] = ()) -> None:
    """Test helper: spoken text must not equal visual search/prompt strings."""
    lowered = text.strip().lower()
    for item in forbidden:
        blob = (item or "").strip().lower()
        if blob and lowered == blob:
            raise TTSError(
                "TTS received a visual prompt instead of spoken narration.",
                "invalid_text",
            )
