#!/usr/bin/env python3
"""
align_and_render.py

Reusable tool: given a CSV (scene_number, script_segment, prompt),
a single voiceover audio file, and a folder of numbered images,
this will:
  1. Transcribe the audio with word-level timestamps (faster-whisper)
  2. Align each script_segment to the audio timeline
  3. Render a final MP4: each image Ken-Burns zoomed for its aligned
     duration, synced under the original audio (optional background bed)

Usage:
    python video_generator.py \
        --csv script.csv \
        --audio voiceover.mp3 \
        --images-dir ./Images \
        --output final.mp4

Optional:
    --model small              # whisper model size: tiny/base/small/medium/large-v3
    --resolution 1920x1080     # output resolution
    --debug-csv timings.csv    # dump per-scene start/end/confidence for QC
    --zoom-amount 0.10         # Ken Burns zoom range (1.0 → 1+amount)
    --no-zoom                  # disable zoom (static images)
    --bg-audio path.mp3        # optional background bed under voiceover
    --bg-volume 0.15           # background volume (0–1)
    --captions                 # burn in scene script text as subtitles
"""

import argparse
import csv
import os
import re
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

from providers import hidden_subprocess

hidden_subprocess.install()


# ---------- text normalization ----------

# English number words → values (used to collapse phrases Whisper often emits as digits)
_ONES = {
    "zero": 0, "oh": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19,
}
_TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}
_SCALES = {
    "hundred": 100, "thousand": 1_000, "million": 1_000_000, "billion": 1_000_000_000,
}


def normalize_word(w: str) -> str:
    """Lowercase, strip punctuation/possessives. Keeps letters+digits only."""
    w = w.lower().strip()
    w = re.sub(r"[^a-z0-9']", "", w)
    if w.endswith("'s"):
        w = w[:-2]
    elif w.endswith("s'") and len(w) > 2:
        w = w[:-2]
    return w.replace("'", "")


def _raw_tokens(text: str):
    """Split on whitespace and hyphens/dashes so compounds match Whisper's pieces."""
    text = re.sub(r"[–—/]", "-", text)
    parts = re.split(r"[\s\-]+", text.strip())
    return [normalize_word(p) for p in parts if normalize_word(p)]


def _is_number_atom(tok: str) -> bool:
    if tok.isdigit():
        return True
    return tok in _ONES or tok in _TENS or tok in _SCALES or tok == "point"


def _consume_number_phrase(tokens, start):
    """
    Parse a run of English number words / digits into the digit token(s) Whisper
    tends to emit. Examples:
      twenty five          → ["25"]
      one point eight      → ["1", "8"]
      a hundred thirty     → ["130"]
      twenty five million  → ["25", "million"]  (scale kept as word; often spoken)

    Lone ones/teens ("one", "three") are left alone — Whisper usually keeps those
    as words, and collapsing them would break matching.

    Returns (replacement_tokens, next_index). If nothing parsed, replacement is [].
    """
    i = start
    n = len(tokens)

    # Optional leading "a" / "an" before hundred/thousand/...
    if i < n and tokens[i] in ("a", "an") and i + 1 < n and tokens[i + 1] in _SCALES:
        i += 1

    if i >= n or not _is_number_atom(tokens[i]):
        return [], start

    started_with_article = i > start

    # Decimal: "one point eight" → ["1", "8"] (Whisper often drops "point")
    if (
        i + 2 < n
        and tokens[i] in _ONES
        and tokens[i + 1] == "point"
        and (tokens[i + 2] in _ONES or tokens[i + 2].isdigit())
    ):
        left = str(_ONES[tokens[i]])
        right = tokens[i + 2] if tokens[i + 2].isdigit() else str(_ONES[tokens[i + 2]])
        return [left, right], i + 3

    # Only collapse when this looks like a real numeric quantity, not prose "one"
    # or a lone scale word like "million" left after "twenty-five million".
    look = tokens[i]
    next_tok = tokens[i + 1] if i + 1 < n else None
    next_is_num = bool(
        next_tok
        and (
            next_tok.isdigit()
            or next_tok in _ONES
            or next_tok in _TENS
            or next_tok in _SCALES
        )
    )
    looks_numeric = (
        look.isdigit()
        or look in _TENS
        or (look in _SCALES and (started_with_article or next_is_num))
        or (look in _ONES and next_is_num)
    )
    if not looks_numeric:
        return [], start

    total = 0
    current = 0
    saw_value = False
    j = i

    while j < n:
        tok = tokens[j]
        if tok.isdigit():
            current += int(tok)
            saw_value = True
            j += 1
            continue
        if tok in _ONES:
            current += _ONES[tok]
            saw_value = True
            j += 1
            continue
        if tok in _TENS:
            current += _TENS[tok]
            saw_value = True
            j += 1
            continue
        if tok in _SCALES:
            scale = _SCALES[tok]
            # twenty-five million → emit "25", leave "million" for next token
            if saw_value and scale >= 1000 and current > 0 and current < scale:
                total += current
                current = 0
                break
            if current == 0:
                current = 1
            current *= scale
            if scale >= 1000:
                total += current
                current = 0
            saw_value = True
            j += 1
            continue
        break

    total += current
    if not saw_value or j == i:
        return [], start
    return [str(total)], j


def collapse_number_words(tokens):
    """Rewrite English number phrases into digit tokens Whisper usually produces."""
    out = []
    i = 0
    while i < len(tokens):
        replaced, nxt = _consume_number_phrase(tokens, i)
        if replaced and nxt > i:
            out.extend(replaced)
            i = nxt
        else:
            out.append(tokens[i])
            i += 1
    return out


def split_words(text: str):
    """Tokenize script/transcript text for alignment (hyphen-split + number collapse)."""
    return collapse_number_words(_raw_tokens(text))


def words_match(a: str, b: str) -> bool:
    """Exact match, or number-word ↔ digit equivalence for single atoms."""
    if a == b:
        return True
    if a.isdigit() and b.isdigit():
        return int(a) == int(b)
    # single number-word ↔ digit (e.g. "twenty" vs "20")
    av = _ONES.get(a, _TENS.get(a))
    bv = _ONES.get(b, _TENS.get(b))
    if a.isdigit() and bv is not None:
        return int(a) == bv
    if b.isdigit() and av is not None:
        return int(b) == av
    return False


# ---------- step 1: transcribe ----------

def transcribe_audio(audio_path: str, model_size: str):
    from faster_whisper import WhisperModel

    print(f"[1/4] Loading whisper model '{model_size}' (first run downloads it)...")
    # num_workers=1 avoids ProcessPool children that re-launch the packaged GUI.
    model = WhisperModel(
        model_size,
        device="cpu",
        compute_type="int8",
        cpu_threads=max(1, min(4, (os.cpu_count() or 4))),
        num_workers=1,
    )

    print(f"[1/4] Transcribing {audio_path} (this can take a while for long audio)...")
    segments, _ = model.transcribe(audio_path, word_timestamps=True, vad_filter=True)

    words = []  # list of (normalized_word, start, end)
    for seg in segments:
        if not seg.words:
            continue
        for w in seg.words:
            # Apply same tokenize path as script so digits/hyphens align
            toks = split_words(w.word)
            if not toks:
                continue
            # Whisper rarely emits multi-token words; if it does, keep timing on each
            for tok in toks:
                words.append((tok, w.start, w.end))

    if not words:
        sys.exit("ERROR: whisper returned no words — check the audio file.")

    print(f"[1/4] Got {len(words)} words from transcription.")
    return words


# ---------- step 2: align script rows to whisper words ----------

STOPWORDS = {
    "a", "an", "the", "and", "to", "of", "in", "on", "is", "it", "its", "that",
    "this", "for", "with", "as", "at", "by", "be", "are", "was", "were", "you",
    "your", "so", "but", "or", "not", "we", "they", "he", "she", "i", "im",
    "my", "our", "us", "them", "his", "her", "if", "than", "then", "when",
    "what", "who", "how", "just", "up", "out", "all", "can", "will", "do",
    "does", "did", "get", "got", "like", "one", "into", "about", "youre",
}

# Magnitude/currency words that recur constantly in numbers-heavy scripts
# (e.g. finance/business explainers). They're long enough to pass a naive
# length check, but Whisper frequently drops or reformats them next to a
# digit (e.g. "$400,000" transcribed as bare digit tokens with no literal
# "thousand"), so a literal-text match on one of these can latch onto an
# unrelated occurrence dozens of words away. Never treat them as distinctive
# on their own.
WEAK_MAGNITUDE_WORDS = {
    "hundred", "thousand", "million", "billion", "dollars", "dollar",
    "percent", "percentage",
}


def is_distinctive(word: str) -> bool:
    # Digits count as distinctive at any length (e.g. "25", "130") — Whisper loves them
    if word.isdigit():
        return len(word) >= 2
    if word in WEAK_MAGNITUDE_WORDS:
        return False
    return len(word) >= 4 and word not in STOPWORDS


def align_rows(rows, whisper_words):
    """
    rows: list of dicts with 'scene_number' and 'script_segment'
    whisper_words: list of (word, start, end)

    Forward-only anchor matching: walk the whisper transcript with a
    monotonic cursor, anchoring each row to the position of its
    distinctive (non-stopword) words. Rows with no distinctive match get
    their timing interpolated proportionally (by word count) between the
    nearest anchored neighbors. This guarantees a strictly increasing
    timeline — it cannot collapse or go out of order like a global diff can.
    """
    print("[2/4] Aligning script segments to audio timeline...")

    n_whisper = len(whisper_words)
    audio_end = whisper_words[-1][2]

    row_words = [split_words(row["script_segment"]) for row in rows]
    row_word_counts = [len(w) for w in row_words]

    # anchors[i] = (whisper_start_idx, whisper_end_idx) for row i, or None
    anchors = [None] * len(rows)
    cursor = 0                 # never search before this (keeps order monotonic)
    # Horizon: how far ahead of the cursor we are allowed to look. Cap prevents
    # matching a repeated word much later in the transcript.
    base_horizon = 120

    words_consumed_script = 0   # running count of script words processed
    words_consumed_whisper = 0  # running count of whisper words at last anchor
    pace_ratio = 1.0             # whisper_words_per_script_word, updated as we go

    for i, words in enumerate(row_words):
        distinctive = [w for w in words if is_distinctive(w)]
        expected_span = max(1, round(len(words) * pace_ratio))

        if distinctive:
            # Always search FROM the cursor forward. Never jump window_start past
            # unread transcript (that caused end-of-video interpolation cascades
            # when a few scenes missed and pace estimate ran ahead).
            horizon = max(base_horizon, expected_span + base_horizon)
            window_start = cursor
            window_end = min(n_whisper, cursor + horizon)

            found_indices = []
            local_cursor = window_start
            for target in distinctive:
                idx = None
                for j in range(local_cursor, window_end):
                    if words_match(whisper_words[j][0], target):
                        idx = j
                        break
                if idx is not None:
                    found_indices.append(idx)
                    local_cursor = idx + 1

            # Quality gates — reject weak/spurious anchors that would advance the
            # cursor past later scenes (the other cascade mode).
            min_hits = 1 if len(distinctive) == 1 else min(2, len(distinctive))
            max_lead = max(55, expected_span * 3)
            max_span = max(25, round(expected_span * 2.5 + 15))
            hit_rate = len(found_indices) / len(distinctive)

            ok = (
                len(found_indices) >= min_hits
                and hit_rate >= 0.25
                and (found_indices[0] - cursor) <= max_lead
                and (found_indices[-1] - found_indices[0]) <= max_span
            )
            if ok:
                start_idx = found_indices[0]
                end_idx = found_indices[-1]
                anchors[i] = (start_idx, end_idx)
                cursor = end_idx + 1

        words_consumed_script += len(words)
        if anchors[i] is not None:
            words_consumed_whisper = anchors[i][1] + 1
            if words_consumed_script > 0:
                pace_ratio = words_consumed_whisper / words_consumed_script
        else:
            # Soft nudge only — enough to recover past a bad scene, nowhere near
            # the old full-pace advance that skipped the rest of the transcript.
            cursor = min(n_whisper, cursor + max(1, expected_span // 2))

    n_anchored = sum(1 for a in anchors if a is not None)
    print(f"[2/4] Anchored {n_anchored}/{len(rows)} rows directly; "
          f"interpolating the rest proportionally by word count.")

    # Convert anchors to (start_time, end_time); interpolate un-anchored rows
    # proportionally (by word count) between the surrounding anchors.
    results = [None] * len(rows)

    def anchor_time(idx_pair):
        s, e = idx_pair
        return whisper_words[s][1], whisper_words[e][2]

    i = 0
    prev_end_time = 0.0
    while i < len(rows):
        if anchors[i] is not None:
            st, en = anchor_time(anchors[i])
            st = max(st, prev_end_time)
            en = max(en, st)
            results[i] = {"start_time": st, "end_time": en, "confidence": 1.0}
            prev_end_time = en
            i += 1
            continue

        # gather the run of consecutive un-anchored rows
        run_start = i
        while i < len(rows) and anchors[i] is None:
            i += 1
        run_end = i  # exclusive

        next_start_time = anchor_time(anchors[i])[0] if i < len(rows) else audio_end
        next_start_time = max(next_start_time, prev_end_time)

        run_word_counts = row_word_counts[run_start:run_end]
        total_words = sum(run_word_counts) or 1
        span = max(next_start_time - prev_end_time, 0.01)

        t = prev_end_time
        for k, wc in enumerate(run_word_counts):
            share = span * (wc / total_words)
            st = t
            en = t + share
            results[run_start + k] = {"start_time": st, "end_time": en, "confidence": 0.0}
            t = en
        prev_end_time = next_start_time

    results[-1]["end_time"] = max(results[-1]["end_time"], audio_end)

    # Guard against zero/negative durations from rounding
    min_dur = 0.15
    for r in results:
        if r["end_time"] - r["start_time"] < min_dur:
            r["end_time"] = r["start_time"] + min_dur

    for i, row in enumerate(rows):
        results[i]["scene_number"] = row["scene_number"]
        results[i]["script_segment"] = row["script_segment"]

    low_conf = [r["scene_number"] for r in results if r["confidence"] < 1.0]
    if low_conf:
        print(f"[2/4] Interpolated (no distinctive word match) on scenes: {low_conf}")
        print("       (still monotonic/proportional, but spot-check these if timing looks off)")

    return results, audio_end


# ---------- step 0: flatten Images/ subfolders ----------

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"}
MEDIA_EXTS = IMAGE_EXTS | VIDEO_EXTS

# Search order for find_image_for_scene: images first, then video clips, so a
# scene with both an image and a clip on disk deterministically prefers the image.
_SCENE_SEARCH_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi")


def is_video_file(path) -> bool:
    return Path(path).suffix.lower() in VIDEO_EXTS


def _natural_key(path: Path):
    """Sort key: folder '2' before '10', image '002.png' before '010.png'."""
    name = path.stem if path.suffix else path.name
    parts = re.split(r"(\d+)", name)
    return [int(p) if p.isdigit() else p.lower() for p in parts]


def arrange_images(images_dir: Path):
    """
    Move images out of subfolders into images_dir and rename them
    sequentially as 001, 002, 003, ... continuing the count across folders.

    Example: folder 1 has 50 images → 001–050;
             folder 2's images start at 051, and so on.
    Empty subfolders are deleted afterward.
    """
    images_dir = Path(images_dir)
    if not images_dir.is_dir():
        sys.exit(f"ERROR: images dir not found: {images_dir}")

    subfolders = sorted(
        [p for p in images_dir.iterdir() if p.is_dir() and not p.name.startswith(".")],
        key=_natural_key,
    )
    if not subfolders:
        print("[0/4] No subfolders in images dir — skipping arrange.")
        return

    # Collect (src, ext) in folder order, then file order within each folder
    to_move = []
    for folder in subfolders:
        files = sorted(
            [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in MEDIA_EXTS],
            key=_natural_key,
        )
        for f in files:
            to_move.append(f)

    if not to_move:
        print("[0/4] Subfolders found but no images inside — nothing to arrange.")
        return

    print(f"[0/4] Arranging {len(to_move)} images from {len(subfolders)} subfolders "
          f"into {images_dir} as 001, 002, ...")

    # Stage into a temp dir first so we never overwrite mid-move
    staging = images_dir / "_arrange_staging"
    staging.mkdir(exist_ok=True)

    staged = []
    for i, src in enumerate(to_move, start=1):
        dest_name = f"{i:03d}{src.suffix.lower()}"
        staged_path = staging / dest_name
        src.rename(staged_path)
        staged.append(staged_path)

    # Remove emptied subfolders (and any leftover junk like .DS_Store)
    for folder in subfolders:
        for leftover in folder.iterdir():
            if leftover.is_file():
                leftover.unlink()
        folder.rmdir()

    # Move staged files into images_dir root
    for staged_path in staged:
        final = images_dir / staged_path.name
        if final.exists():
            final.unlink()
        staged_path.rename(final)

    staging.rmdir()
    print(f"[0/4] Done. Images are now {staged[0].name} … {staged[-1].name} in {images_dir}")


# ---------- step 3: locate image files ----------

def build_scene_media_index(images_dir: Path) -> dict:
    """One directory scan → stem → preferred media path (image before video)."""
    images_dir = Path(images_dir)
    by_stem: dict[str, dict[str, Path]] = {}
    try:
        for p in images_dir.iterdir():
            if not p.is_file() or p.name.startswith("."):
                continue
            ext = p.suffix.lower()
            if ext not in MEDIA_EXTS:
                continue
            by_stem.setdefault(p.stem, {})[ext] = p
    except OSError:
        return {}
    out: dict[str, Path] = {}
    for stem, by_ext in by_stem.items():
        for ext in _SCENE_SEARCH_EXTS:
            if ext in by_ext:
                out[stem] = by_ext[ext]
                break
    return out


def find_image_for_scene(images_dir: Path, scene_number: str, ext_cache: dict = None):
    """Handles zero-padded (001) or plain (1) numbering; matches an image or a video clip.

    Pass ``ext_cache`` from :func:`build_scene_media_index` to avoid repeated
    ``Path.exists`` probes when resolving many scenes.
    """
    n = int(str(scene_number).strip())
    candidates = [
        f"{n}", f"{n:02d}", f"{n:03d}", f"{n:04d}",
    ]
    if ext_cache is not None:
        for c in candidates:
            hit = ext_cache.get(c)
            if hit is not None:
                return hit
        return None

    for c in candidates:
        for e in _SCENE_SEARCH_EXTS:
            p = images_dir / f"{c}{e}"
            if p.exists():
                return p
    return None


def missing_images_for_scenes(rows, images_dir: Path):
    """Return scene_number strings that have no matching image file."""
    index = build_scene_media_index(images_dir)
    missing = []
    for row in rows:
        scene = str(row["scene_number"]).strip()
        if find_image_for_scene(images_dir, scene, ext_cache=index) is None:
            missing.append(scene)
    return missing


def count_image_files(images_dir: Path) -> int:
    """Count image files in images_dir including one level of subfolders."""
    images_dir = Path(images_dir)
    n = 0
    for p in images_dir.rglob("*"):
        if p.is_file() and p.suffix.lower() in MEDIA_EXTS and not p.name.startswith("."):
            # Ignore staging leftovers if any
            if "_arrange_staging" in p.parts:
                continue
            n += 1
    return n


def validate_prerequisites(
    rows,
    images_dir: Path,
    audio_path: str,
    bg_audio: str | None = None,
):
    """
    Fail fast BEFORE Whisper transcription.

    Call after arrange_images() so subfolder layouts are already flattened.
    Raises SystemExit with a clear message on failure.
    """
    print("[0/4] Checking prerequisites...")

    images_dir = Path(images_dir)
    if not images_dir.is_dir():
        sys.exit(f"ERROR: images dir not found: {images_dir}")

    if not Path(audio_path).is_file():
        sys.exit(f"ERROR: voiceover audio not found: {audio_path}")

    if bg_audio is not None and not Path(bg_audio).is_file():
        sys.exit(f"ERROR: background audio not found: {bg_audio}")

    if not rows:
        sys.exit("ERROR: CSV has no rows.")

    missing = missing_images_for_scenes(rows, images_dir)
    if missing:
        preview = missing[:20]
        more = f" (and {len(missing) - 20} more)" if len(missing) > 20 else ""
        sys.exit(
            f"ERROR: missing image/video files for {len(missing)} scene(s): "
            f"{preview}{more}\n"
            f"       Need one image or video clip per CSV row "
            f"(e.g. 001.png or 001.mp4 … {len(rows):03d}) in {images_dir}"
        )

    print(f"[0/4] Prerequisites OK — {len(rows)} scenes, "
          f"{len(rows)} images, audio present.")



# ---------- step 4: render ----------

def _scene_display_timeline(aligned_rows, audio_end):
    """
    Display windows matching rendered clips: scene 0 starts at 0,
    later scenes start at their aligned start_time; last ends at audio_end.
    Returns list of (start, end) in seconds.
    """
    n = len(aligned_rows)
    display_start = [0.0] + [aligned_rows[i]["start_time"] for i in range(1, n)]
    windows = []
    for i in range(n - 1):
        start = display_start[i]
        end = max(display_start[i + 1], start + 0.05)
        windows.append((start, end))
    last_start = display_start[-1]
    windows.append((last_start, max(audio_end, last_start + 0.05)))
    return windows


def _scene_durations(aligned_rows, audio_end):
    """Duration per scene = gap until next scene start (absorbs pauses)."""
    return [end - start for start, end in _scene_display_timeline(aligned_rows, audio_end)]


def _load_caption_font(size: int):
    """Prefer a bold system sans; fall back to Pillow default."""
    from PIL import ImageFont

    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial Bold.ttf",
        "/Library/Fonts/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "C:\\Windows\\Fonts\\arialbd.ttf",
        "C:\\Windows\\Fonts\\arial.ttf",
    ]
    for path in candidates:
        if Path(path).is_file():
            try:
                return ImageFont.truetype(path, size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def _wrap_caption_lines(text: str, font, max_width: int, draw) -> list[str]:
    """Greedy word-wrap so each line fits within max_width pixels."""
    words = (text or "").strip().split()
    if not words:
        return []
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        trial = f"{current} {word}"
        if draw.textlength(trial, font=font) <= max_width:
            current = trial
        else:
            lines.append(current)
            current = word
    lines.append(current)
    # Soft-cap very long single words
    wrapped: list[str] = []
    for line in lines:
        if draw.textlength(line, font=font) <= max_width:
            wrapped.append(line)
        else:
            wrapped.extend(textwrap.wrap(line, width=max(8, len(line) // 2)) or [line])
    return wrapped


def render_caption_overlay(
    text: str,
    out_path: Path,
    width: int,
    height: int,
) -> Path | None:
    """
    Transparent PNG with white outlined text near the bottom.
    Returns None if text is empty.
    """
    from PIL import Image, ImageDraw

    text = (text or "").strip()
    if not text:
        return None

    font_size = 42 if height >= width else 52
    font = _load_caption_font(font_size)
    margin_x = int(width * 0.08)
    max_text_w = width - 2 * margin_x
    bottom_margin = int(height * 0.08)

    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    lines = _wrap_caption_lines(text, font, max_text_w, draw)
    if not lines:
        return None

    line_gap = int(font_size * 0.25)
    heights = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font, stroke_width=3)
        heights.append(bbox[3] - bbox[1])
    block_h = sum(heights) + line_gap * (len(lines) - 1)
    y = height - bottom_margin - block_h

    for line, lh in zip(lines, heights):
        bbox = draw.textbbox((0, 0), line, font=font, stroke_width=3)
        lw = bbox[2] - bbox[0]
        x = (width - lw) // 2
        draw.text(
            (x, y),
            line,
            font=font,
            fill=(255, 255, 255, 255),
            stroke_width=3,
            stroke_fill=(0, 0, 0, 220),
        )
        y += lh + line_gap

    out_path = Path(out_path)
    img.save(out_path, format="PNG")
    return out_path


def render_smart_text_overlay(
    text: str,
    out_path: Path,
    width: int,
    height: int,
    *,
    intensity: float = 0.65,
    effect: str = "highlight",
    local_start: float = 0.0,
    local_end: float | None = None,
    fx: dict | None = None,
) -> Path | None:
    """Transparent full-frame PNG via typography theme (Pillow — no drawtext needed).

    Never falls back to the old Arial caption renderer — that produced the
    "subtitle" look users report as broken typography.
    """
    from typography import render_style_overlay

    t1 = float(local_end) if local_end is not None else float(local_start) + 0.35
    payload = {
        "text": text,
        "effect": effect,
        "intensity": intensity,
        "local_start": float(local_start),
        "local_end": t1,
    }
    if isinstance(fx, dict):
        # Preserve scene metadata (composition hints, etc.) from Smart Editing.
        payload = {**fx, **payload}
    return render_style_overlay(payload, out_path, width, height)


def _zoompan_filter(width: int, height: int, fps: int, frames: int,
                    zoom_in: bool, zoom_amount: float) -> str:
    """Ken Burns zoompan. Upscale first so zoom stays sharp."""
    max_z = 1.0 + max(zoom_amount, 0.0)
    # Spread zoom across frames; clamp so we never exceed max_z / go below 1.0
    step = (max_z - 1.0) / max(frames - 1, 1)
    if zoom_in:
        z_expr = f"min(1.0+on*{step:.8f},{max_z:.6f})"
    else:
        z_expr = f"max({max_z:.6f}-on*{step:.8f},1.0)"

    # Cover-crop to 4x output, then zoompan down to final size
    sw, sh = width * 4, height * 4
    return (
        f"scale={sw}:{sh}:force_original_aspect_ratio=increase,"
        f"crop={sw}:{sh},"
        f"zoompan=z='{z_expr}':"
        f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        f"d={frames}:s={width}x{height}:fps={fps},"
        f"setsar=1,format=yuv420p"
    )


def _static_filter(width: int, height: int) -> str:
    return (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,"
        f"setsar=1,format=yuv420p"
    )


def _video_fit_filter(width: int, height: int, fps: int) -> str:
    """Cover-crop to fill the frame and conform to the target fps (no Ken Burns — the clip already has motion)."""
    return (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},"
        f"fps={fps},setsar=1,format=yuv420p"
    )


def _escape_overlay_enable(t0: float, t1: float) -> str:
    """enable='between(t,t0,t1)' with commas escaped for filter graphs."""
    return f"between(t\\,{t0:.3f}\\,{t1:.3f})"


def _overlay_xy(t0: float | None, animation: str | None) -> str:
    """Static or subtle slide-in overlay position (no bounce)."""
    if t0 is None:
        return "0:0"
    anim = str(animation or "")
    if anim in ("slide_fade", "reveal"):
        # 14px settle upward over ~120ms
        y = (
            f"if(lt(t\\,{t0:.3f}+0.120)\\,"
            f"14*(1-(t-{t0:.3f})/0.120)\\,"
            f"0)"
        )
        return f"0:{y}"
    if anim == "slide_in":
        # 18px settle from the left over ~120ms
        x = (
            f"if(lt(t\\,{t0:.3f}+0.120)\\,"
            f"-18*(1-(t-{t0:.3f})/0.120)\\,"
            f"0)"
        )
        return f"{x}:0"
    return "0:0"


def _render_scene_clip(
    img_path: Path,
    out_path: Path,
    duration: float,
    width: int,
    height: int,
    fps: int,
    zoom: bool,
    zoom_in: bool,
    zoom_amount: float,
    caption_overlay: Path | None = None,
    text_effect_filters: str = "",
    timed_overlays: list | None = None,
):
    """
    timed_overlays: list of (png_path, local_start, local_end[, animation])
    for Pillow text when ffmpeg has no drawtext filter.
    """
    frames = max(int(round(duration * fps)), 1)
    # Use exact frame count so concat length matches audio timeline
    clip_dur = frames / fps
    timed_overlays = list(timed_overlays or [])

    if is_video_file(img_path):
        # -stream_loop -1 loops the clip if it's shorter than the scene, and is a
        # no-op (truncated by -t below) if it's longer — one code path for both.
        base_vf = _video_fit_filter(width, height, fps)
        input_args = ["-stream_loop", "-1", "-i", str(img_path)]
    elif zoom:
        base_vf = _zoompan_filter(width, height, fps, frames, zoom_in, zoom_amount)
        input_args = ["-loop", "1", "-i", str(img_path)]
    else:
        base_vf = _static_filter(width, height)
        input_args = ["-loop", "1", "-i", str(img_path)]

    # Collect extra image inputs: static caption first, then timed smart-text PNGs
    extra_inputs: list[str] = []
    # (input_idx, t0, t1, animation)
    layers: list[tuple[int, float | None, float | None, str | None]] = []
    next_idx = 1
    if caption_overlay is not None:
        extra_inputs += ["-loop", "1", "-i", str(caption_overlay)]
        layers.append((next_idx, None, None, None))
        next_idx += 1
    for item in timed_overlays:
        png, t0, t1 = item[0], item[1], item[2]
        anim = item[3] if len(item) > 3 else None
        extra_inputs += ["-loop", "1", "-i", str(png)]
        layers.append((next_idx, float(t0), float(t1), anim))
        next_idx += 1

    if layers or text_effect_filters:
        parts = [f"[0:v]{base_vf}[v0]"]
        cur = "v0"
        for layer_i, (in_idx, t0, t1, anim) in enumerate(layers):
            lab_in = f"ov{layer_i}"
            lab_out = f"v{layer_i + 1}"
            parts.append(f"[{in_idx}:v]format=rgba,scale={width}:{height}[{lab_in}]")
            if t0 is None:
                enable = ""
            else:
                enable = f":enable='{_escape_overlay_enable(t0, t1)}'"
            xy = _overlay_xy(t0, anim)
            parts.append(
                f"[{cur}][{lab_in}]overlay={xy}:format=auto{enable}[{lab_out}]"
            )
            cur = lab_out
        if text_effect_filters:
            parts.append(f"[{cur}]{text_effect_filters},format=yuv420p[vout]")
        else:
            parts.append(f"[{cur}]format=yuv420p[vout]")
        filter_complex = ";".join(parts)
        try:
            from typography.debug import log_ffmpeg_filter

            log_ffmpeg_filter(filter_complex)
        except Exception:
            pass
        cmd = [
            "ffmpeg", "-y",
            *input_args,
            *extra_inputs,
            "-filter_complex", filter_complex,
            "-map", "[vout]",
            "-t", f"{clip_dur:.6f}",
            "-r", str(fps),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-pix_fmt", "yuv420p",
            "-an",
            str(out_path),
        ]
    else:
        cmd = [
            "ffmpeg", "-y",
            *input_args,
            "-vf", base_vf,
            "-t", f"{clip_dur:.6f}",
            "-r", str(fps),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-pix_fmt", "yuv420p",
            "-an",
            str(out_path),
        ]

    result = hidden_subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()
        print(err[-3000:])
        hint = ""
        if "drawtext" in err.lower() and "no such filter" in err.lower():
            hint = (
                "\nHint: this ffmpeg build has no drawtext filter "
                "(needs libfreetype). Smart Text should use Pillow overlays; "
                "if you still see this, turn off Smart Text Effects or install "
                "ffmpeg with --enable-libfreetype."
            )
        sys.exit(f"ERROR: ffmpeg failed rendering clip for {img_path.name}{hint}")


def render_video(
    aligned_rows,
    audio_end,
    images_dir: Path,
    audio_path: str,
    output_path: str,
    resolution: str,
    fps: int,
    zoom: bool = True,
    zoom_amount: float = 0.10,
    bg_audio: str | None = None,
    bg_volume: float = 0.15,
    captions: bool = False,
    scene_text_effects: list | None = None,
):
    print("[3/4] Locating image files...")
    missing = missing_images_for_scenes(aligned_rows, images_dir)
    if missing:
        # Should have been caught in validate_prerequisites; keep as safety net.
        sys.exit(f"ERROR: missing image files for scenes: {missing}")

    image_paths = [
        find_image_for_scene(images_dir, row["scene_number"]).resolve()
        for row in aligned_rows
    ]

    durations = _scene_durations(aligned_rows, audio_end)
    width, height = (int(x) for x in resolution.split("x"))
    per_scene_fx = scene_text_effects or [[] for _ in aligned_rows]

    if bg_audio is not None and not Path(bg_audio).is_file():
        sys.exit(f"ERROR: background audio not found: {bg_audio}")

    clips_dir = Path("._render_clips")
    if clips_dir.exists():
        shutil.rmtree(clips_dir)
    clips_dir.mkdir()

    captions_dir = None
    if captions:
        try:
            from PIL import Image  # noqa: F401
        except ImportError:
            sys.exit(
                "ERROR: captions require Pillow. Install with:\n"
                "       pip install 'Pillow>=10.0.0'"
            )
        captions_dir = clips_dir / "_captions"
        captions_dir.mkdir()
        print("[3/4] Captions ON — rendering text overlays per scene...")

    n = len(image_paths)
    smart_fx = any(per_scene_fx)
    print(f"[3/4] Rendering {n} scene clips"
          f"{' with Ken Burns zoom' if zoom else ''}"
          f"{' + captions' if captions else ''}"
          f"{' + smart text' if smart_fx else ''}...")

    # GUI runs pipeline in-process — reload typography once per render so edits apply.
    if smart_fx:
        try:
            import importlib

            import typography
            import typography.debug as typography_debug
            import typography.placement as typography_placement
            import typography.render as typography_render
            import typography.styles as typography_styles
            import typography.theme as typography_theme
            import typography.variation as typography_variation

            importlib.reload(typography_theme)
            importlib.reload(typography_styles)
            importlib.reload(typography_placement)
            importlib.reload(typography_variation)
            importlib.reload(typography_debug)
            importlib.reload(typography_render)
            importlib.reload(typography)
            typography_variation.reset_variation_history()
            print(
                "[3/4] Smart text via Pillow typography overlays "
                f"(module={typography_render.__file__})."
            )
        except Exception as exc:
            print(f"[3/4] Typography reload warning: {exc}")

    clip_files = []
    for i, (img, dur, row) in enumerate(zip(image_paths, durations, aligned_rows)):
        out_clip = clips_dir / f"scene_{i:04d}.mp4"
        zoom_in = (i % 2 == 0)
        if (i + 1) % 25 == 0 or i == 0 or i == n - 1:
            print(f"       clip {i + 1}/{n} ({dur:.2f}s)")

        overlay = None
        if captions_dir is not None:
            overlay = render_caption_overlay(
                row.get("script_segment", ""),
                captions_dir / f"cap_{i:04d}.png",
                width,
                height,
            )

        fx_filters = ""
        timed_overlays: list = []
        if per_scene_fx[i]:
            # Always burn modern typography via Pillow full-frame overlays.
            # System ffmpeg often lacks drawtext; even when present, drawtext
            # cannot reproduce theme fonts / plates / placement. Never fall
            # back to the old Arial caption renderer.
            try:
                from typography import render_style_overlay, typography_params_for_effect
                from typography.debug import log_typography_event, typography_debug_enabled

                smart_dir = Path("smart_text_overlays")
                smart_dir.mkdir(exist_ok=True)
                for j, fx in enumerate(per_scene_fx[i]):
                    raw = str(fx.get("text") or "").strip()
                    if not raw:
                        continue
                    fx_payload = dict(fx)
                    fx_payload["scene_duration"] = float(dur)
                    params = typography_params_for_effect(fx_payload, width, height)
                    display = str(params.get("text") or "")
                    if not display:
                        if typography_debug_enabled():
                            log_typography_event(
                                raw_text=raw,
                                display_text="",
                                style_id=str(params.get("style_id") or ""),
                                font=params.get("font_path"),
                                fontsize=int(params.get("fontsize") or 0),
                                position=str(params.get("placement") or ""),
                                effect=str(fx.get("effect") or ""),
                                filter_or_overlay="SKIPPED (empty display / weak filler)",
                            )
                        continue
                    png_path = smart_dir / f"scene_{i:04d}_{j:02d}.png"
                    png = render_style_overlay(
                        fx_payload,
                        png_path,
                        width,
                        height,
                        params=params,
                        record_history=False,
                    )
                    if png is None:
                        continue
                    t0 = float(fx.get("local_start") or 0.0)
                    t1 = float(fx.get("local_end") or t0 + 0.3)
                    if t1 <= t0:
                        t1 = t0 + 0.12
                    anim = str(params.get("animation") or "")
                    overlay_desc = (
                        f"pillow_overlay file={png.name} "
                        f"enable=between(t\\,{t0:.3f}\\,{t1:.3f}) "
                        f"xy=0:0 (full-frame baked placement={params.get('placement')})"
                    )
                    log_typography_event(
                        raw_text=raw,
                        display_text=display,
                        style_id=str(params.get("style_id") or ""),
                        font=params.get("font_path"),
                        fontsize=int(params.get("fontsize") or 0),
                        position=str(params.get("placement") or ""),
                        effect=str(fx.get("effect") or ""),
                        filter_or_overlay=overlay_desc,
                    )
                    timed_overlays.append((png, t0, t1, anim))
            except Exception as exc:
                # Do not silently substitute old Arial text — surface the failure.
                print(f"[3/4] Smart typography failed for scene clip {i + 1}: {exc}")
                fx_filters = ""
                timed_overlays = []

        _render_scene_clip(
            img_path=img,
            out_path=out_clip,
            duration=dur,
            width=width,
            height=height,
            fps=fps,
            zoom=zoom,
            zoom_in=zoom_in,
            zoom_amount=zoom_amount,
            caption_overlay=overlay,
            text_effect_filters=fx_filters,
            timed_overlays=timed_overlays,
        )
        clip_files.append(out_clip)

    concat_list_path = Path("concat_list.txt")
    concat_lines = [f"file '{p.resolve()}'" for p in clip_files]
    concat_list_path.write_text("\n".join(concat_lines), encoding="utf-8")

    print("[4/4] Muxing clips + audio...")
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", str(concat_list_path),
        "-i", audio_path,
    ]

    if bg_audio:
        # Loop bed under voiceover; keep VO dominant
        cmd += ["-stream_loop", "-1", "-i", bg_audio]
        filter_complex = (
            f"[2:a]volume={bg_volume:.4f}[bg];"
            f"[1:a][bg]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[a]"
        )
        cmd += [
            "-filter_complex", filter_complex,
            "-map", "0:v", "-map", "[a]",
        ]
    else:
        cmd += ["-map", "0:v", "-map", "1:a"]

    cmd += [
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        output_path,
    ]

    result = hidden_subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stderr[-3000:])
        sys.exit("ERROR: ffmpeg final mux failed — see log above.")

    shutil.rmtree(clips_dir, ignore_errors=True)
    print(f"[4/4] Done. Output: {output_path}")


# ---------- scene asset resolution (AI / stock / local) ----------

def resolve_scene_assets(
    rows,
    images_dir: Path,
    *,
    pexels_api_key: str | None = None,
    flow_engine_manager=None,
    flow_settings: dict | None = None,
    youtube_max_results: int = 5,
    youtube_clip_duration: float = 3.5,
    youtube_transcript_matching: bool = True,
    log=print,
) -> None:
    """
    Routes each CSV row to LocalProvider / StockProvider / FlowProvider(image or
    video) and writes the resulting file into images_dir *before*
    arrange_images() / validate_prerequisites() / transcribe_audio() /
    render_video() run — those functions are completely unmodified and only
    ever see ordinary files at images_dir/00N.<ext>, exactly like a
    hand-populated Images/ folder.

    A no-op (besides a fast local-file check) for old-style 2-column CSVs,
    since every row with no asset_type/prompt/stock value routes to
    LocalProvider, which just looks for the file the way
    find_image_for_scene() always has.

    Deferred (function-local) imports of asset_manager/providers are
    deliberate: video_generator.py must stay importable on its own (e.g. from
    app.py) without pulling in the provider stack unless this function is
    actually called.
    """
    from asset_manager import AssetManager
    from providers.base import AssetError, SceneRow

    scene_rows = [SceneRow.from_csv_row(r) for r in rows]
    needs_flow_image = any(s.wants_flow_image for s in scene_rows)
    needs_flow_video = any(s.wants_flow_video for s in scene_rows)
    needs_stock = any(s.wants_stock for s in scene_rows)
    needs_youtube = any(s.wants_youtube for s in scene_rows)

    stock_provider = None
    if needs_stock:
        if not pexels_api_key:
            sys.exit(
                "ERROR: this CSV has scene(s) with a 'stock' keyword but no Pexels "
                "API key was provided. Set --pexels-api-key or the PEXELS_API_KEY "
                "environment variable."
            )
        from providers.stock.pexels import build_pexels_provider

        stock_provider = build_pexels_provider(images_dir, pexels_api_key)

    flow_image_provider = None
    flow_video_provider = None
    if needs_flow_image or needs_flow_video:
        if flow_engine_manager is None:
            sys.exit(
                "ERROR: this CSV has AI image/video scene(s) but no Flow engine is "
                "configured. See flow-engine/README.md for setup."
            )
        from providers.flow.provider import FlowProvider

        if needs_flow_image:
            flow_image_provider = FlowProvider(
                flow_engine_manager, media_kind="image", flow_settings=flow_settings
            )
        if needs_flow_video:
            flow_video_provider = FlowProvider(
                flow_engine_manager, media_kind="video", flow_settings=flow_settings
            )

    youtube_provider = None
    if needs_youtube:
        try:
            from providers.youtube.base import YouTubeProvider
            from providers.youtube.ytdlp_backend import YtDlpBackend

            youtube_provider = YouTubeProvider(
                YtDlpBackend(),
                max_results=youtube_max_results,
                clip_duration=youtube_clip_duration,
                transcript_matching=youtube_transcript_matching,
            )
        except RuntimeError as exc:
            sys.exit(f"ERROR: this CSV has youtube_video scene(s): {exc}")

    manager = AssetManager(
        images_dir,
        stock_provider=stock_provider,
        flow_image_provider=flow_image_provider,
        flow_video_provider=flow_video_provider,
        youtube_provider=youtube_provider,
        log=log,
    )
    try:
        summary = manager.resolve_all(scene_rows)
    except AssetError as exc:
        sys.exit(f"ERROR: {exc.reason}")

    if not summary.ok:
        lines = [f"  Scene {r.scene_number}: {r.error}" for r in summary.failed]
        sys.exit("ERROR: could not resolve assets for these scene(s):\n" + "\n".join(lines))


# ---------- main ----------

def main():
    parser = argparse.ArgumentParser(description="Auto-sync numbered images to a voiceover using CSV script segments.")
    parser.add_argument("--csv", required=True, help="Path to CSV (scene_number, script_segment, asset_type, prompt — or legacy scene_number, script_segment, prompt, stock)")
    parser.add_argument("--audio", required=True, help="Path to voiceover audio file (any ffmpeg-readable format)")
    parser.add_argument("--images-dir", required=True, help="Folder containing numbered images (also used as the AI/stock download target)")
    parser.add_argument("--output", default="final.mp4", help="Output MP4 path")
    parser.add_argument("--model", default="small", help="Whisper model size: tiny/base/small/medium/large-v3")
    parser.add_argument("--resolution", default="1920x1080", help="Output resolution WxH (default landscape 1920x1080; use 1080x1920 for vertical/shorts)")
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--debug-csv", default=None, help="Optional path to dump per-scene alignment timings for QC")
    parser.add_argument("--zoom-amount", type=float, default=0.10,
                        help="Ken Burns zoom range: 1.0 → 1+amount (default 0.10 = 10%%)")
    parser.add_argument("--no-zoom", action="store_true", help="Disable Ken Burns zoom (static stills)")
    parser.add_argument("--bg-audio", default=None,
                        help="Optional background bed/SFX loop mixed under the voiceover")
    parser.add_argument("--bg-volume", type=float, default=0.15,
                        help="Background bed volume 0–1 (default 0.15)")
    parser.add_argument("--captions", action="store_true",
                        help="Burn in scene script_segment text as subtitles")
    parser.add_argument("--pexels-api-key", default=None,
                        help="Pexels API key for 'stock' scenes (falls back to PEXELS_API_KEY env var)")
    parser.add_argument("--flow-engine-port", type=int, default=8787,
                        help="Port for the flow-engine sidecar, used only if the CSV has 'prompt' scenes")
    parser.add_argument("--youtube-max-results", type=int, default=5,
                        help="Search results to consider per youtube_video scene (default 5)")
    parser.add_argument("--youtube-clip-duration", type=float, default=3.5,
                        help="Target clip length in seconds for youtube_video scenes (default 3.5)")
    parser.add_argument("--youtube-no-transcript-matching", action="store_true",
                        help="Disable transcript matching for youtube_video scenes (uses the fallback timestamp strategy)")
    args = parser.parse_args()

    with open(args.csv, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if not rows:
        sys.exit("ERROR: CSV has no rows.")
    for col in ("scene_number", "script_segment"):
        if col not in rows[0]:
            sys.exit(f"ERROR: CSV missing required column '{col}'")

    arrange_images(Path(args.images_dir))

    from providers.base import SceneRow as _SceneRow

    _scene_rows_preview = [_SceneRow.from_csv_row(r) for r in rows]
    flow_engine_manager = None
    if any(s.wants_flow for s in _scene_rows_preview):
        from providers.flow.engine_manager import FlowEngineManager

        flow_engine_manager = FlowEngineManager(port=args.flow_engine_port)

    resolve_scene_assets(
        rows,
        Path(args.images_dir),
        pexels_api_key=args.pexels_api_key or os.environ.get("PEXELS_API_KEY"),
        flow_engine_manager=flow_engine_manager,
        youtube_max_results=args.youtube_max_results,
        youtube_clip_duration=args.youtube_clip_duration,
        youtube_transcript_matching=not args.youtube_no_transcript_matching,
    )

    validate_prerequisites(
        rows,
        Path(args.images_dir),
        args.audio,
        bg_audio=args.bg_audio,
    )

    whisper_words = transcribe_audio(args.audio, args.model)
    aligned, audio_end = align_rows(rows, whisper_words)

    if args.debug_csv:
        with open(args.debug_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["scene_number", "start_time", "end_time", "confidence", "script_segment"])
            writer.writeheader()
            for r in aligned:
                writer.writerow({
                    "scene_number": r["scene_number"],
                    "start_time": round(r["start_time"], 3),
                    "end_time": round(r["end_time"], 3),
                    "confidence": r["confidence"],
                    "script_segment": r["script_segment"],
                })
        print(f"[debug] Wrote alignment timings to {args.debug_csv}")

    render_video(
        aligned,
        audio_end,
        Path(args.images_dir),
        args.audio,
        args.output,
        args.resolution,
        args.fps,
        zoom=not args.no_zoom,
        zoom_amount=args.zoom_amount,
        bg_audio=args.bg_audio,
        bg_volume=args.bg_volume,
        captions=args.captions,
    )

    if flow_engine_manager is not None:
        flow_engine_manager.stop()


if __name__ == "__main__":
    main()