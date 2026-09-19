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
import contextlib
import csv
import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

from providers import hidden_subprocess

hidden_subprocess.install()

# Real, previously-latent Windows crash: this module's own print()/logging
# calls contain non-ASCII characters (→, ✓, ⚠, …) throughout, and Windows'
# default console codepage (cp1252 or similar, NOT UTF-8) raises
# UnicodeEncodeError on ANY of them — confirmed for real via CI (Windows
# runner, plain `python -m unittest`, e.g. "[3/4] Scene clips → {dir}").
# This is not merely a test artifact: the packaged .exe's stdout is subject
# to the exact same default codepage whenever it isn't already UTF-8
# (console redirection, certain Windows locales). errors="replace" makes
# this fail-safe even if reconfigure itself is unavailable for some reason.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


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

    model = WhisperModel(
        model_size,
        device="cpu",
        compute_type="int8",
        cpu_threads=max(1, min(4, (os.cpu_count() or 4))),
        num_workers=1,
    )

    print(f"[1/4] Transcribing {audio_path} (this can take a while for long audio)...")
    segments, _ = model.transcribe(audio_path, word_timestamps=True, vad_filter=True)
    seg_list = list(segments)

    words = []  # list of (normalized_word, start, end)
    for seg in seg_list:
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

    Does **not** match complement stems (``001_b``) — those are returned by
    :func:`find_complement_assets_for_scene`.
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


def find_complement_assets_for_scene(images_dir: Path, scene_number: str) -> list[Path]:
    """Return on-disk complementary assets for a scene (``001_b``, ``001_c``, …).

    Ordered by suffix letter. Primary ``001.ext`` is never included.
    """
    images_dir = Path(images_dir)
    try:
        n = int(str(scene_number).strip())
    except ValueError:
        return []
    stems = [f"{n:03d}", f"{n}", f"{n:02d}", f"{n:04d}"]
    found: list[Path] = []
    seen: set[str] = set()
    for letter in ("b", "c", "d", "e"):
        for stem in stems:
            for ext in _SCENE_SEARCH_EXTS:
                p = images_dir / f"{stem}_{letter}{ext}"
                if p.is_file():
                    key = str(p.resolve())
                    if key not in seen:
                        seen.add(key)
                        found.append(p)
                    break
            else:
                continue
            break
    return found


def complement_asset_id(scene_number: str, path: Path) -> str:
    """Stable id like ``001_b`` from a complement filename."""
    try:
        n = int(str(scene_number).strip())
        prefix = f"{n:03d}"
    except ValueError:
        prefix = str(scene_number).strip()
    stem = Path(path).stem  # e.g. 001_b
    if "_" in stem:
        return stem
    return f"{prefix}_b"


def manifest_scene_record(images_dir: Path, scene_number: str) -> dict:
    """Return one scene's asset-manifest record (or {})."""
    path = Path(images_dir) / ".asset_manifest.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    try:
        n = int(str(scene_number).strip())
        keys = [f"{n:03d}", str(n), f"{n:02d}", str(scene_number)]
    except ValueError:
        keys = [str(scene_number)]
    for key in keys:
        rec = data.get(key)
        if isinstance(rec, dict):
            return rec
    return {}


def manifest_coverage_flags(images_dir: Path) -> dict[str, dict]:
    """Per-scene coverage metadata from asset manifest (avoid_blind_loop, strategy)."""
    path = Path(images_dir) / ".asset_manifest.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    out: dict[str, dict] = {}
    for key, rec in data.items():
        if not isinstance(rec, dict):
            continue
        cov = rec.get("coverage_plan")
        if isinstance(cov, dict):
            out[str(key).lstrip("0") or key] = cov
            out[str(key)] = cov
    return out


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


def _zoompan_filter(
    width: int,
    height: int,
    fps: int,
    frames: int,
    zoom_in: bool,
    zoom_amount: float,
    *,
    camera_style: str | None = None,
) -> str:
    """Ken Burns zoompan. Upscale first so zoom stays sharp."""
    style = (camera_style or "").strip().lower().replace(" ", "_")
    if style == "subtle_drift":
        return _subtle_drift_filter(width, height, fps, frames, zoom_amount=max(zoom_amount * 0.45, 0.03))

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


def _subtle_drift_filter(
    width: int,
    height: int,
    fps: int,
    frames: int,
    zoom_amount: float = 0.04,
) -> str:
    """Gentle push with slow horizontal drift — distinct from full Ken Burns."""
    max_z = 1.0 + max(zoom_amount, 0.02)
    step = (max_z - 1.0) / max(frames - 1, 1)
    z_expr = f"min(1.0+on*{step:.8f},{max_z:.6f})"
    drift = max(1, width // 180)
    x_expr = f"iw/2-(iw/zoom/2)+on*{drift}"
    sw, sh = width * 4, height * 4
    return (
        f"scale={sw}:{sh}:force_original_aspect_ratio=increase,"
        f"crop={sw}:{sh},"
        f"zoompan=z='{z_expr}':"
        f"x='{x_expr}':y='ih/2-(ih/zoom/2)':"
        f"d={frames}:s={width}x{height}:fps={fps},"
        f"setsar=1,format=yuv420p"
    )


def _camera_motion(
    camera_style: str | None,
    *,
    index: int,
    zoom: bool,
) -> tuple[bool, bool, str | None]:
    """Return (use_zoom, zoom_in, style_token) for a scene clip."""
    style = (camera_style or "").strip().lower().replace(" ", "_")
    if not style:
        if not zoom:
            return False, False, None
        return True, (index % 2 == 0), None
    if style in ("static", "hold"):
        return False, False, style
    if style == "push_in":
        return True, True, style
    if style == "pull_out":
        return True, False, style
    if style == "subtle_drift":
        return True, True, style
    if not zoom:
        return False, False, style
    return True, (index % 2 == 0), style


def _static_filter(width: int, height: int) -> str:
    return (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,"
        f"setsar=1,format=yuv420p"
    )


# ---- real B-roll (VIDEO_2) picture-in-picture overlay --------------------
#
# VIDEO_2 previously had no real "simultaneous overlay" semantics anywhere:
# build_timeline_from_decisions labels the SECOND shot of a multi-shot scene
# "VIDEO_2" purely for timeline-row display, but the renderer plays every
# shot in a scene sequentially — there was never any actual compositing.
# This is a genuine picture-in-picture compositor using ffmpeg's overlay
# filter: two real decoded video streams, one drawn on top of the other for
# the requested time window.

_BROLL_POSITIONS = {
    "bottom_right": "main_w-overlay_w-{margin}:main_h-overlay_h-{margin}",
    "bottom_left": "{margin}:main_h-overlay_h-{margin}",
    "top_right": "main_w-overlay_w-{margin}:{margin}",
    "top_left": "{margin}:{margin}",
    "center": "(main_w-overlay_w)/2:(main_h-overlay_h)/2",
}


def composite_broll_overlay(
    base_clip: Path,
    broll_source: Path,
    out_path: Path,
    *,
    overlay_start: float,
    overlay_duration: float,
    width: int,
    height: int,
    fps: int,
    broll_source_start: float = 0.0,
    broll_speed: float = 1.0,
    scale: float = 0.4,
    position: str = "bottom_right",
) -> bool:
    """Composite ``broll_source`` as a real picture-in-picture overlay onto
    ``base_clip`` for [overlay_start, overlay_start+overlay_duration).
    ``scale`` is the B-roll's width as a fraction of the full frame (aspect
    preserved). Returns False (never raises) on any ffmpeg failure — the
    caller keeps the un-composited base_clip in that case, never a corrupt
    or half-written output."""
    if overlay_duration <= 0:
        return False
    margin = max(8, int(round(min(width, height) * 0.03)))
    pos_expr = _BROLL_POSITIONS.get(position, _BROLL_POSITIONS["bottom_right"]).format(margin=margin)
    pip_w = max(2, int(round(width * max(0.1, min(0.9, scale)))))

    speed = 1.0
    try:
        from editorial_timeline_edit import clamp_speed

        speed = clamp_speed(broll_speed)
    except Exception:
        speed = max(0.25, min(2.0, broll_speed))

    src_start = max(0.0, float(broll_source_start))
    read_dur = overlay_duration * speed
    pts_chain = f"setpts={1.0 / speed:.6f}*PTS," if abs(speed - 1.0) > 1e-3 else ""

    filter_complex = (
        f"[1:v]{pts_chain}scale={pip_w}:-2,format=yuva420p[pip];"
        f"[0:v][pip]overlay={pos_expr}:"
        f"enable='between(t\\,{overlay_start:.3f}\\,{overlay_start + overlay_duration:.3f})'[vout]"
    )
    cmd = [
        "ffmpeg", "-y",
        "-i", str(base_clip),
        "-ss", f"{src_start:.3f}", "-t", f"{read_dur:.3f}", "-i", str(broll_source),
        "-filter_complex", filter_complex,
        "-map", "[vout]",
        *_cpu_encode_argv(),
        "-an",
        "-r", str(fps),
        str(out_path),
    ]
    result = hidden_subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0 and Path(out_path).is_file() and Path(out_path).stat().st_size > 0


def _video_fit_filter(width: int, height: int, fps: int) -> str:
    """Cover-crop to fill the frame and conform to the target fps (no Ken Burns — the clip already has motion)."""
    return (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},"
        f"fps={fps},setsar=1,format=yuv420p"
    )


def _escape_overlay_enable(t0: float, t1: float) -> str:
    """enable='between(t,t0,t1)' with commas escaped for filter graphs.

    A hair of slack on each side so the alpha fades are not clipped by the
    on/off window that used to be the only thing shaping the overlay.
    """
    return f"between(t\\,{max(0.0, t0 - 0.02):.3f}\\,{t1 + 0.02:.3f})"


# Rotate visual scene joins so edits are not all hard cuts or the same fade.
_VISUAL_TRANSITION_CYCLE = ("fade", "dissolve", "cut", "flash", "soft", "fade")


def scene_visual_transition_style(index: int, total: int) -> str:
    """Pick a transition style for the boundary *into* this scene clip."""
    if total <= 1:
        return "fade"
    if index == 0:
        return "fade"
    return _VISUAL_TRANSITION_CYCLE[index % len(_VISUAL_TRANSITION_CYCLE)]


def transition_fade_params(style: str, duration: float) -> tuple[float, float, str]:
    """Return (fade_in_sec, fade_out_sec, color) for a clip. Duration-preserving (no overlap)."""
    d = max(float(duration), 0.4)
    max_fade = min(0.42, d * 0.20)
    style = (style or "fade").lower()
    if style == "cut":
        return 0.0, 0.0, "black"
    if style == "dissolve":
        return min(0.38, max_fade), min(0.38, max_fade), "black"
    if style == "flash":
        return min(0.10, max_fade), min(0.18, max_fade), "white"
    if style == "soft":
        return min(0.32, max_fade), min(0.22, max_fade), "black"
    # fade (default)
    return min(0.26, max_fade), min(0.26, max_fade), "black"


def _fade_vf_suffix(clip_dur: float, fade_in: float, fade_out: float, color: str = "black") -> str:
    """ffmpeg fade filters; empty string when both fades are zero."""
    parts: list[str] = []
    fi = max(0.0, float(fade_in))
    fo = max(0.0, float(fade_out))
    color = (color or "black").lower()
    if fi > 0.01:
        parts.append(f"fade=t=in:st=0:d={fi:.3f}:color={color}")
    if fo > 0.01 and clip_dur > fo + 0.05:
        st = max(0.0, clip_dur - fo)
        # Outgoing fades always go to black so the next clip can open cleanly.
        parts.append(f"fade=t=out:st={st:.3f}:d={fo:.3f}:color=black")
    return ",".join(parts)


# ---- real cross-clip transitions (ffmpeg xfade) ---------------------------
#
# The fade-in/fade-out machinery above (transition_fade_params/_fade_vf_suffix)
# is each clip independently fading to/from a solid color at its own edges —
# "duration-preserving (no overlap)" per its own docstring. That is NOT a
# crossfade: clip A's tail and clip B's head never actually blend. Real
# crossfade/dip/wipe/slide need ffmpeg's xfade filter, which requires both
# clips as decoded inputs to one filter graph — it cannot work with the fast
# "-c copy" concat-demuxer mux. This is used ONLY when the operator actually
# requests a real transition (TimelineEvent.metadata["transition_duration"]
# set to something > 0 with a transition_in in TRANSITION_TYPES) — a project
# that never asks for one renders through the exact same fast path as before
# this existed (see run_final_mux's `transitions is None` fast path).

TRANSITION_TYPES = ("cut", "crossfade", "dip_black", "dip_white", "wipe", "slide")

_XFADE_NAME_FOR_TYPE = {
    "cut": "fade",  # only reached with a near-zero duration (see build_xfade_filter_complex)
    "crossfade": "fade",
    "dip_black": "fadeblack",
    "dip_white": "fadewhite",
    "wipe": "wipeleft",
    "slide": "slideleft",
}

# Directional xfade variants for "wipe"/"slide" — all 8 are real ffmpeg
# xfade transition names (verified against `ffmpeg -h filter=xfade`), not
# an invented vocabulary. Only these two base types expose a direction;
# every other TRANSITION_TYPES entry ignores transition_direction.
TRANSITION_DIRECTIONS = ("left", "right", "up", "down")
_DIRECTIONAL_XFADE_NAME = {
    "wipe": {"left": "wipeleft", "right": "wiperight", "up": "wipeup", "down": "wipedown"},
    "slide": {"left": "slideleft", "right": "slideright", "up": "slideup", "down": "slidedown"},
}

MIN_XFADE_DURATION = 0.05  # short enough to read as a cut, long enough for xfade to accept


def xfade_name_for_transition(transition_type: str, direction: str = "") -> str:
    ttype = (transition_type or "cut").lower()
    by_dir = _DIRECTIONAL_XFADE_NAME.get(ttype)
    if by_dir:
        return by_dir.get((direction or "left").lower(), by_dir["left"])
    return _XFADE_NAME_FOR_TYPE.get(ttype, "fade")


def build_xfade_filter_complex(
    durations: list[float],
    transitions: list[tuple[str, float] | None] | list[tuple[str, float, str] | None],
) -> tuple[str, str]:
    """Build the ffmpeg filter_complex chaining xfade across every clip
    boundary. ``durations[i]`` is clip i's own length in seconds;
    ``transitions[i]`` is the (type, duration) or (type, duration,
    direction) to use at the boundary BETWEEN clip i and clip i+1, or None
    for an (effectively-instant, see MIN_XFADE_DURATION) cut there.
    ``direction`` (only meaningful for "wipe"/"slide" — see
    TRANSITION_DIRECTIONS) defaults to "left" when omitted. len(transitions)
    must be len(durations)-1.

    Returns (filter_complex_string, final_video_stream_label). Each xfade's
    ``offset`` is measured from the start of the FIRST original input
    (ffmpeg xfade semantics) — computed here by tracking the cumulative
    duration of the merged stream so far, which shrinks by each
    transition's own duration as clips start overlapping.
    """
    n = len(durations)
    if n < 2:
        raise ValueError("build_xfade_filter_complex needs at least 2 clips")
    if len(transitions) != n - 1:
        raise ValueError(f"expected {n - 1} boundary transition(s), got {len(transitions)}")

    parts: list[str] = []
    running = float(durations[0])
    prev_label = "0:v"
    for i in range(1, n):
        spec = transitions[i - 1]
        if spec is None:
            ttype, tdur, tdir = "cut", 0.0, ""
        elif len(spec) >= 3:
            ttype, tdur, tdir = spec[0], spec[1], spec[2]
        else:
            ttype, tdur, tdir = spec[0], spec[1], ""
        # Never exceed either neighboring clip's own length — xfade can't
        # borrow frames that don't exist.
        tdur = max(MIN_XFADE_DURATION, min(float(tdur) or MIN_XFADE_DURATION, durations[i - 1] - 0.02, durations[i] - 0.02))
        tdur = max(MIN_XFADE_DURATION, tdur)
        xf_name = xfade_name_for_transition(ttype, tdir)
        offset = max(0.0, running - tdur)
        out_label = f"vx{i}"
        parts.append(
            f"[{prev_label}][{i}:v]xfade=transition={xf_name}:duration={tdur:.3f}:offset={offset:.3f}[{out_label}]"
        )
        running = running + float(durations[i]) - tdur
        prev_label = out_label
    return ";".join(parts), prev_label


def _overlay_xy(
    t0: float | None,
    animation: str | None,
    center: tuple[int, int] | None = None,
) -> str:
    """Static or subtle slide-in overlay position (no bounce).

    For `scale_fade` the whole full-frame overlay is scaled, which would grow
    it from the frame's top-left corner; the offset here pulls it back so the
    type scales about its own centre instead.
    """
    if t0 is None:
        return "0:0"
    anim = str(animation or "")
    if anim == "scale_fade" and center is not None:
        cx, cy = center
        expr = _overlay_scale_expr(float(t0))
        return f"{int(cx)}*(1-({expr})):{int(cy)}*(1-({expr}))"
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


# Overlay motion. Keep these short and controlled — documentary typography
# settles, it does not bounce.
_OV_FADE_IN = 0.16
_OV_FADE_OUT = 0.12
_OV_SCALE_FROM = 0.98
_OV_SCALE_DUR = 0.22


def _overlay_scale_expr(t0: float) -> str:
    """s(t): ease from _OV_SCALE_FROM up to 1.0, then hold."""
    grow = 1.0 - _OV_SCALE_FROM
    return (
        f"if(lt(t\\,{t0:.3f}+{_OV_SCALE_DUR})\\,"
        f"{_OV_SCALE_FROM}+{grow:.4f}*(t-{t0:.3f})/{_OV_SCALE_DUR}\\,1)"
    )


def _overlay_motion_chain(
    t0: float | None,
    t1: float | None,
    anim: str | None,
    width: int,
    height: int,
) -> str:
    """Filters applied to one overlay stream before it is composited.

    Previously overlays were switched on and off with `enable=` alone, which
    is a hard cut: text popped on and popped off, and the `scale_fade` /
    `kinetic_punch` animations the style layer asked for never happened at
    all (the alpha/scale machinery only ever fed the unused drawtext path).
    """
    chain = [f"format=rgba,scale={width}:{height}"]
    if t0 is None or t1 is None:
        return ",".join(chain)

    # Scale punch is per-frame work at full resolution, so it is reserved for
    # the hero animation rather than applied to every overlay in the scene.
    if str(anim or "") == "scale_fade":
        expr = _overlay_scale_expr(float(t0))
        chain.append(
            f"scale=w='{width}*({expr})':h='{height}*({expr})':eval=frame"
        )

    span = float(t1) - float(t0)
    fi = min(_OV_FADE_IN, max(0.04, span * 0.35))
    fo = min(_OV_FADE_OUT, max(0.04, span * 0.30))
    fade_out_st = max(float(t0) + fi, float(t1) - fo)
    chain.append(f"fade=t=in:st={float(t0):.3f}:d={fi:.3f}:alpha=1")
    chain.append(f"fade=t=out:st={fade_out_st:.3f}:d={fo:.3f}:alpha=1")
    return ",".join(chain)


def _cpu_encode_argv() -> list[str]:
    try:
        from providers.ffmpeg_runner import encode_argv

        return encode_argv(quality="documentary")
    except Exception:
        return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20"]


def _run_ffmpeg_encode(cmd: list[str], img_name: str) -> None:
    """Encode one clip via the central runner (timeout + stall detection).

    Raises ``RuntimeError`` on failure (never ``sys.exit``) so unit tests and
    the GUI host are not killed by a single clip encode error.
    """
    try:
        from providers.ffmpeg_runner import FFmpegError, run_ffmpeg
    except Exception:
        FFmpegError = None  # type: ignore
        run_ffmpeg = None  # type: ignore

    def _fail(message: str) -> None:
        raise RuntimeError(message)

    if run_ffmpeg is not None:
        try:
            # Infer a soft duration hint from -t in the command when present.
            media_dur = 0.0
            for i, tok in enumerate(cmd):
                if tok == "-t" and i + 1 < len(cmd):
                    try:
                        media_dur = float(cmd[i + 1])
                    except ValueError:
                        pass
                    break
            result = run_ffmpeg(
                cmd,
                owner="render",
                label=str(img_name),
                media_duration_s=media_dur,
                stall_s=float(os.environ.get("VIDEOGEN_FFMPEG_STALL_S", "120") or 120),
            )
            if result.returncode == 0 and not result.timed_out and not result.stalled:
                return
            err = (result.stderr or result.stdout or "").strip()
            print(err[-3000:])
            why = "timed out" if result.timed_out else ("stalled" if result.stalled else "failed")
            hint = ""
            if "drawtext" in err.lower() and "no such filter" in err.lower():
                hint = (
                    "\nHint: this ffmpeg build has no drawtext filter "
                    "(needs libfreetype). Smart Text should use Pillow overlays; "
                    "if you still see this, turn off Smart Text Effects or install "
                    "ffmpeg with --enable-libfreetype."
                )
            _fail(f"ERROR: ffmpeg {why} rendering clip for {img_name}{hint}")
        except RuntimeError:
            raise
        except Exception as exc:
            if FFmpegError is not None and isinstance(exc, FFmpegError):
                res = exc.result
                err = ((res.stderr if res else "") or "").strip()
                if err:
                    print(err[-3000:])
                _fail(f"ERROR: ffmpeg failed rendering clip for {img_name}: {exc}")
            # Fall through to legacy path on unexpected runner failures.

    result = hidden_subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        return
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
    _fail(f"ERROR: ffmpeg failed rendering clip for {img_name}{hint}")


def _video_punch_filter(
    width: int,
    height: int,
    fps: int,
    *,
    scale: float = 1.0,
    crop_x: float = 0.5,
    crop_y: float = 0.5,
) -> str:
    """Cover-crop with optional punch-in (scale>1) around a normalized focal point."""
    s = max(1.0, float(scale) or 1.0)
    cx = min(1.0, max(0.0, float(crop_x)))
    cy = min(1.0, max(0.0, float(crop_y)))
    # Scale up first, then crop a window centered near (cx, cy).
    # Using expressions keeps this resolution-agnostic.
    if s <= 1.001:
        return _video_fit_filter(width, height, fps)
    # iw/ih after scale-to-cover at punch scale
    return (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop=iw/{s:.4f}:ih/{s:.4f}:"
        f"(iw-ow)*{cx:.4f}:(ih-oh)*{cy:.4f},"
        f"scale={width}:{height},"
        f"fps={fps},setsar=1,format=yuv420p"
    )


def _render_editorial_shot(
    img_path: Path,
    out_path: Path,
    shot: dict,
    width: int,
    height: int,
    fps: int,
    zoom_amount: float = 0.10,
) -> None:
    """Render one ShotSpec dict from an EditDecision into a temp clip."""
    duration = max(0.05, float(shot.get("output_duration") or 0.05))
    frames = max(int(round(duration * fps)), 1)
    clip_dur = frames / fps
    scale = float(shot.get("scale") or 1.0)
    crop_x = float(shot.get("crop_x") if shot.get("crop_x") is not None else 0.5)
    crop_y = float(shot.get("crop_y") if shot.get("crop_y") is not None else 0.5)
    speed = float(shot.get("speed") or 1.0)
    try:
        from editorial_timeline_edit import clamp_speed

        speed = clamp_speed(speed)
    except Exception:
        speed = min(2.0, max(0.25, speed))
    camera_style = str(shot.get("camera_style") or "static")
    hold_tail = bool(shot.get("hold_tail"))
    src_start = float(shot.get("source_start") or 0.0)
    src_end = shot.get("source_end")
    encode_args = _cpu_encode_argv()

    if is_video_file(img_path):
        base_vf = _video_punch_filter(
            width, height, fps, scale=scale, crop_x=crop_x, crop_y=crop_y
        )
        base_vf = f"{base_vf},setpts=PTS-STARTPTS"
        if abs(speed - 1.0) > 0.02:
            base_vf = f"{base_vf},setpts=PTS/{speed:.4f},fps={fps}"
        try:
            from providers.media_clip.ffmpeg_clip import probe_duration

            file_dur = probe_duration(img_path) or 0.0
        except Exception:
            file_dur = 0.0
        src_span = None
        if src_end is not None:
            try:
                src_span = max(0.05, float(src_end) - src_start)
            except (TypeError, ValueError):
                src_span = None
        window = src_span
        if window is None and file_dur > 0:
            window = max(0.05, file_dur - max(0.0, src_start))
        window = float(window or 0.0)

        # Delivered file is authoritative. If it can cover this shot's output
        # duration, ignore a stale short source_end from an old edit plan and
        # play one continuous segment (no 2s×3 loop of an 8s Flow clip).
        file_remaining = max(0.0, file_dur - max(0.0, src_start)) if file_dur > 0 else 0.0
        if file_remaining + 0.05 >= clip_dur:
            window = max(window, clip_dur * max(speed, 0.01))

        playable = window / max(speed, 0.01) if window > 0 else 0.0

        input_args: list[str] = []
        if src_start > 0.02:
            input_args += ["-ss", f"{src_start:.3f}"]

        if hold_tail and file_remaining + 0.05 < clip_dur:
            # Intentional editorial hold only when the real file is short.
            read_dur = playable if playable > 0 else clip_dur
            input_args += ["-t", f"{read_dur:.3f}", "-i", str(img_path)]
            pad = max(0.0, clip_dur - read_dur)
            if pad > 0.08:
                base_vf = f"{base_vf},tpad=stop_mode=clone:stop_duration={pad:.3f}"
        elif (
            playable > 0.08
            and playable + 0.05 < clip_dur
            and (file_remaining <= 0 or file_remaining + 0.05 < clip_dur)
        ):
            # Loop only when the REAL file cannot cover the shot duration.
            nframes = max(2, int(round(playable * fps)))
            base_vf = f"{base_vf},loop=-1:size={nframes}:start=0,setpts=N/{fps}/TB"
            input_args += ["-t", f"{playable:.3f}", "-i", str(img_path)]
        else:
            read_dur = clip_dur / max(speed, 0.01)
            # Prefer reading from the real file continuously.
            if file_remaining > 0:
                read_dur = min(read_dur, file_remaining + 0.05)
            input_args += ["-t", f"{read_dur:.3f}", "-i", str(img_path)]
        cmd = [
            "ffmpeg", "-y",
            *input_args,
            "-vf", base_vf,
            "-t", f"{clip_dur:.6f}",
            "-r", str(fps),
            *encode_args,
            "-pix_fmt", "yuv420p",
            "-an",
            str(out_path),
        ]
        _run_ffmpeg_encode(cmd, img_path.name)
        return

    # Still image — Ken Burns / drift using camera_style; punch via zoom_amount
    use_zoom, zoom_in, style = _camera_motion(camera_style, index=0, zoom=True)
    punch_boost = max(0.0, scale - 1.0) * 0.35
    amount = max(zoom_amount, 0.04) + punch_boost
    if use_zoom:
        base_vf = _zoompan_filter(
            width, height, fps, frames, zoom_in, amount, camera_style=style
        )
    else:
        # Static still with optional punch crop
        if scale > 1.05:
            base_vf = (
                f"scale={width}:{height}:force_original_aspect_ratio=increase,"
                f"crop=iw/{scale:.4f}:ih/{scale:.4f}:"
                f"(iw-ow)*{crop_x:.4f}:(ih-oh)*{crop_y:.4f},"
                f"scale={width}:{height},setsar=1,format=yuv420p"
            )
        else:
            base_vf = _static_filter(width, height)
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", str(img_path),
        "-vf", base_vf,
        "-t", f"{clip_dur:.6f}",
        "-r", str(fps),
        *encode_args,
        "-pix_fmt", "yuv420p",
        "-an",
        str(out_path),
    ]
    _run_ffmpeg_encode(cmd, img_path.name)


# ---------- FFmpeg concat demuxer paths (Windows-safe) ----------

# Temp scene clips live here during mux. Do NOT use an AppleDouble-style
# ``._…`` name — macOS cleanup/sync tools treat ``._*`` as metadata and may
# delete the folder mid-render, leaving concat entries missing at mux time.
# Windows ``\s`` escape issues are already avoided by forward-slash concat paths.
RENDER_CLIPS_DIRNAME = "_vg_render_clips"
CONCAT_LIST_FILENAME = "concat_list.txt"


class ConcatMuxError(Exception):
    """concat_list.txt is missing or a listed clip does not exist."""

    def __init__(self, message: str, *, missing_path=None, scene_number=None):
        super().__init__(message)
        self.missing_path = missing_path
        self.scene_number = scene_number


def scene_clip_filename(index: int) -> str:
    return f"scene_{int(index):04d}.mp4"


def scene_clip_path(render_dir, scene_filename: str, *, path_cls=None):
    """Join render-clips dir and scene filename with a real path separator.

    ``Path(render_dir) / scene_filename`` — never ``render_dir + scene_filename``,
    which on Windows glues ``...\\render_clips`` + ``scene_0000.mp4`` into
    ``...\\render_clipsscene_0000.mp4``.
    """
    cls = path_cls if path_cls is not None else Path
    return cls(render_dir) / scene_filename


def render_clips_dir(work_dir, *, path_cls=None):
    cls = path_cls if path_cls is not None else Path
    return cls(work_dir) / RENDER_CLIPS_DIRNAME


def concat_list_path_for(work_dir, *, path_cls=None):
    cls = path_cls if path_cls is not None else Path
    return cls(work_dir) / CONCAT_LIST_FILENAME


def ffmpeg_concat_path_text(clip_path: Path, concat_list_path: Path) -> str:
    """Path text for one concat demuxer entry.

    Always absolute + forward slashes. Relative entries break when FFmpeg's
    working directory drifts; Windows backslashes are escapes in the concat
    demuxer (``\\s`` → eaten), so ``as_posix()`` is mandatory on every OS.
    """
    del concat_list_path  # kept in signature for call-site compatibility
    return Path(clip_path).resolve().as_posix()


def _escape_ffmpeg_concat_filename(path_text: str) -> str:
    # Backslash is the concat-demuxer escape; single quote ends the quoted path.
    return path_text.replace("\\", "\\\\").replace("'", r"'\''")


def _unescape_ffmpeg_concat_filename(inner: str) -> str:
    return inner.replace(r"'\''", "'").replace("\\\\", "\\")


def ffmpeg_concat_file_line(clip_path: Path, concat_list_path: Path) -> str:
    inner = ffmpeg_concat_path_text(clip_path, concat_list_path)
    return f"file '{_escape_ffmpeg_concat_filename(inner)}'"


def write_ffmpeg_concat_list(clip_paths, concat_list_path: Path) -> Path:
    """Write concat_list.txt with demuxer-safe absolute forward-slash paths."""
    concat_list_path = Path(concat_list_path)
    concat_list_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [ffmpeg_concat_file_line(Path(p), concat_list_path) for p in clip_paths]
    concat_list_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return concat_list_path.resolve()


def parse_concat_list_clip_paths(concat_list_path: Path) -> list[Path]:
    """Resolve each ``file '...'`` entry (absolute or relative to the list file)."""
    concat_list_path = Path(concat_list_path)
    base = concat_list_path.resolve().parent
    paths: list[Path] = []
    for line in concat_list_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not stripped.lower().startswith("file "):
            continue
        rest = stripped[5:].strip()
        if len(rest) >= 2 and rest.startswith("'") and rest.endswith("'"):
            inner = _unescape_ffmpeg_concat_filename(rest[1:-1])
        else:
            inner = _unescape_ffmpeg_concat_filename(rest)
        p = Path(inner)
        if not p.is_absolute():
            p = (base / inner).resolve()
        else:
            p = p.resolve()
        paths.append(p)
    return paths


def _mux_missing_hint(missing_path: Path) -> str:
    text = str(missing_path)
    if "._render_clips" in text.replace("\\", "/"):
        return (
            " Hint: path still uses legacy '._render_clips' — install a build "
            "from 2026-09-14 or later (uses _vg_render_clips)."
        )
    return ""


def run_final_mux(
    *,
    concat_list_path: Path,
    audio_path,
    output_path,
    bg_audio=None,
    bg_volume: float = 0.25,
    clip_files=None,
    scene_numbers=None,
    transitions=None,
    clip_durations=None,
) -> None:
    """Mux scene clips + audio with cwd pinned and a last-chance input check.

    ``transitions``/``clip_durations``: when transitions is None (the
    default) or every entry is None, this is byte-for-byte the same fast
    stream-copy concat-demuxer mux as before real transitions existed — a
    project that never requests one pays zero cost for this feature. When
    at least one boundary requests a real transition, every clip becomes a
    separate ffmpeg input and the video is built via an xfade filter chain
    (build_xfade_filter_complex) instead — this DOES require a full video
    re-encode (xfade can't work with "-c copy"), which only projects that
    actually use the feature pay for.
    """
    concat_list_path = Path(concat_list_path).resolve()
    work = concat_list_path.parent
    try:
        listed = validate_mux_inputs(
            concat_list_path, clip_files, scene_numbers=scene_numbers
        )
    except ConcatMuxError as exc:
        hint = _mux_missing_hint(Path(exc.missing_path or concat_list_path))
        sys.exit(f"ERROR: {exc}{hint}")

    has_transitions = bool(transitions) and any(t is not None for t in transitions)

    print(f"[4/4] Muxing {len(listed)} clip(s) + audio…")
    print(f"[4/4] concat={concat_list_path}")
    print(f"[4/4] clips_dir={render_clips_dir(work)}")
    if has_transitions:
        print(f"[4/4] {sum(1 for t in transitions if t is not None)} real transition(s) requested — re-encoding via xfade.")

    if has_transitions:
        _run_final_mux_with_transitions(
            listed, audio_path=audio_path, output_path=output_path,
            bg_audio=bg_audio, bg_volume=bg_volume,
            transitions=transitions, clip_durations=clip_durations, work=work,
        )
        return

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", str(concat_list_path),
        "-i", str(audio_path),
    ]

    if bg_audio:
        cmd += ["-stream_loop", "-1", "-i", str(bg_audio)]
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
        str(output_path),
    ]

    result = hidden_subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(work),
    )
    if result.returncode != 0:
        # Re-check: FFmpeg's message is often "concat_list.txt" even when the
        # real problem is a vanished scene clip under a cloud-synced folder.
        vanished = [p for p in listed if not p.is_file()]
        print(result.stderr[-3000:] if result.stderr else "")
        if vanished:
            sample = vanished[0]
            hint = _mux_missing_hint(sample)
            sys.exit(
                f"ERROR: ffmpeg final mux failed — {len(vanished)} clip(s) missing "
                f"(e.g. {sample}).{hint}"
            )
        sys.exit("ERROR: ffmpeg final mux failed — see log above.")


def _run_final_mux_with_transitions(
    clip_paths: list[Path],
    *,
    audio_path,
    output_path,
    bg_audio,
    bg_volume: float,
    transitions,
    clip_durations,
    work: Path,
) -> None:
    if clip_durations is None:
        from providers.media_clip.ffmpeg_clip import probe_duration

        clip_durations = [probe_duration(p) or 0.05 for p in clip_paths]
    if len(clip_durations) != len(clip_paths):
        sys.exit("ERROR: xfade mux — clip_durations length mismatch.")
    if len(transitions) != len(clip_paths) - 1:
        sys.exit("ERROR: xfade mux — transitions length mismatch.")

    if len(clip_paths) == 1:
        # Nothing to cross-fade between — fall back to a plain re-encode.
        video_filter_complex, video_label = "", "0:v"
    else:
        video_filter_complex, video_label = build_xfade_filter_complex(clip_durations, transitions)

    cmd = ["ffmpeg", "-y"]
    for p in clip_paths:
        cmd += ["-i", str(p)]
    audio_input_index = len(clip_paths)
    cmd += ["-i", str(audio_path)]

    filter_parts = [video_filter_complex] if video_filter_complex else []
    if bg_audio:
        bg_input_index = audio_input_index + 1
        cmd += ["-stream_loop", "-1", "-i", str(bg_audio)]
        filter_parts.append(
            f"[{bg_input_index}:a]volume={bg_volume:.4f}[bg];"
            f"[{audio_input_index}:a][bg]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[a]"
        )
        audio_label = "[a]"
    else:
        audio_label = f"{audio_input_index}:a"

    cmd += ["-filter_complex", ";".join(p for p in filter_parts if p)]
    cmd += ["-map", f"[{video_label}]" if video_filter_complex else f"{video_label}", "-map", audio_label]
    cmd += [*_cpu_encode_argv(), "-c:a", "aac", "-b:a", "192k", "-shortest", str(output_path)]

    result = hidden_subprocess.run(cmd, capture_output=True, text=True, cwd=str(work))
    if result.returncode != 0:
        print(result.stderr[-3000:] if result.stderr else "")
        sys.exit("ERROR: ffmpeg transition mux failed — see log above.")


def validate_mux_inputs(
    concat_list_path: Path,
    clip_files=None,
    scene_numbers=None,
) -> list[Path]:
    """Fail before FFmpeg if concat_list.txt or any listed clip is missing."""
    concat_list_path = Path(concat_list_path)
    if not concat_list_path.is_file():
        raise ConcatMuxError(
            f"concat list missing: {concat_list_path.resolve()}",
            missing_path=concat_list_path,
        )
    listed = parse_concat_list_clip_paths(concat_list_path)
    if not listed:
        raise ConcatMuxError(
            f"concat list is empty: {concat_list_path.resolve()}",
            missing_path=concat_list_path,
        )
    expected = [Path(p) for p in clip_files] if clip_files is not None else None
    if expected is not None and len(listed) != len(expected):
        raise ConcatMuxError(
            f"concat list has {len(listed)} clip(s) but {len(expected)} were rendered: "
            f"{concat_list_path.resolve()}",
            missing_path=concat_list_path,
        )
    for i, listed_path in enumerate(listed):
        scene = None
        if scene_numbers is not None and i < len(scene_numbers):
            scene = scene_numbers[i]
        else:
            scene = i
        if not listed_path.is_file():
            raise ConcatMuxError(
                f"mux input missing for scene {scene}: {listed_path}",
                missing_path=listed_path,
                scene_number=scene,
            )
        if expected is not None and not expected[i].is_file():
            raise ConcatMuxError(
                f"mux input missing for scene {scene}: {expected[i].resolve()}",
                missing_path=expected[i],
                scene_number=scene,
            )
    return listed


def _concat_shot_clips(shot_paths: list[Path], out_path: Path) -> None:
    """Lossless-ish concat of same-codec shot clips into one scene clip."""
    if len(shot_paths) == 1:
        shutil.copy2(shot_paths[0], out_path)
        return
    list_path = out_path.with_suffix(".concat.txt")
    write_ffmpeg_concat_list(shot_paths, list_path)
    try:
        validate_mux_inputs(list_path, shot_paths)
    except ConcatMuxError as exc:
        sys.exit(f"ERROR: {exc}")
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-fflags", "+genpts",
        "-i", str(list_path.resolve()),
        "-c", "copy",
        str(out_path),
    ]
    result = hidden_subprocess.run(
        cmd, capture_output=True, text=True, cwd=str(list_path.resolve().parent)
    )
    if result.returncode != 0:
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-fflags", "+genpts",
            "-i", str(list_path.resolve()),
            *_cpu_encode_argv(),
            "-pix_fmt", "yuv420p",
            "-an",
            str(out_path),
        ]
        _run_ffmpeg_encode(cmd, "shot_concat")
    list_path.unlink(missing_ok=True)


def _apply_overlays_to_clip(
    base_clip: Path,
    out_path: Path,
    duration: float,
    width: int,
    height: int,
    fps: int,
    caption_overlay: Path | None = None,
    text_effect_filters: str = "",
    timed_overlays: list | None = None,
    fade_in: float = 0.0,
    fade_out: float = 0.0,
    fade_color: str = "black",
) -> None:
    """Burn captions/smart-text/fades onto an already-assembled scene clip."""
    frames = max(int(round(duration * fps)), 1)
    clip_dur = frames / fps
    timed_overlays = list(timed_overlays or [])
    encode_args = _cpu_encode_argv()
    fade_suffix = _fade_vf_suffix(clip_dur, fade_in, fade_out, fade_color)
    input_args = ["-i", str(base_clip)]
    base_vf = f"fps={fps},setpts=PTS-STARTPTS,setsar=1,format=yuv420p"

    extra_inputs: list[str] = []
    layers: list[tuple[int, float | None, float | None, str | None, tuple[int, int] | None]] = []
    next_idx = 1
    if caption_overlay is not None:
        extra_inputs += ["-loop", "1", "-i", str(caption_overlay)]
        layers.append((next_idx, None, None, None, None))
        next_idx += 1
    for item in timed_overlays:
        png, t0, t1 = item[0], item[1], item[2]
        anim = item[3] if len(item) > 3 else None
        center = item[4] if len(item) > 4 else None
        extra_inputs += ["-loop", "1", "-i", str(png)]
        layers.append((next_idx, float(t0), float(t1), anim, center))
        next_idx += 1

    if layers or text_effect_filters or fade_suffix:
        parts = [f"[0:v]{base_vf}[v0]"]
        cur = "v0"
        for layer_i, (in_idx, t0, t1, anim, center) in enumerate(layers):
            lab_in = f"ov{layer_i}"
            lab_out = f"v{layer_i + 1}"
            motion = _overlay_motion_chain(t0, t1, anim, width, height)
            parts.append(f"[{in_idx}:v]{motion}[{lab_in}]")
            if t0 is None:
                enable = ""
            else:
                enable = f":enable='{_escape_overlay_enable(t0, t1)}'"
            xy = _overlay_xy(t0, anim, center)
            parts.append(
                f"[{cur}][{lab_in}]overlay={xy}:format=auto{enable}[{lab_out}]"
            )
            cur = lab_out
        tail_bits = []
        if text_effect_filters:
            tail_bits.append(text_effect_filters)
        if fade_suffix:
            tail_bits.append(fade_suffix)
        tail_bits.append("format=yuv420p")
        parts.append(f"[{cur}]{','.join(tail_bits)}[vout]")
        filter_complex = ";".join(parts)
        cmd = [
            "ffmpeg", "-y",
            *input_args,
            *extra_inputs,
            "-filter_complex", filter_complex,
            "-map", "[vout]",
            "-t", f"{clip_dur:.6f}",
            "-r", str(fps),
            *encode_args,
            "-pix_fmt", "yuv420p",
            "-an",
            str(out_path),
        ]
    else:
        if fade_suffix:
            cmd = [
                "ffmpeg", "-y",
                *input_args,
                "-vf", f"{base_vf},{fade_suffix}",
                "-t", f"{clip_dur:.6f}",
                "-r", str(fps),
                *encode_args,
                "-pix_fmt", "yuv420p",
                "-an",
                str(out_path),
            ]
        else:
            shutil.copy2(base_clip, out_path)
            return
    _run_ffmpeg_encode(cmd, base_clip.name)


def _render_scene_from_edit_decision(
    img_path: Path,
    out_path: Path,
    duration: float,
    edit_decision: dict,
    width: int,
    height: int,
    fps: int,
    zoom_amount: float = 0.10,
    caption_overlay: Path | None = None,
    text_effect_filters: str = "",
    timed_overlays: list | None = None,
    fade_in: float = 0.0,
    fade_out: float = 0.0,
    fade_color: str = "black",
) -> bool:
    """Execute a multi-shot EditDecision. Returns False to fall back to legacy path."""
    shots = edit_decision.get("shots") if isinstance(edit_decision, dict) else None
    if not isinstance(shots, list) or not shots:
        return False
    # Normalize durations to exact scene length
    raw_total = sum(max(0.05, float(s.get("output_duration") or 0.05)) for s in shots)
    if raw_total <= 0:
        return False
    scale = float(duration) / raw_total
    norm_shots = []
    for s in shots:
        sc = dict(s)
        sc["output_duration"] = round(max(0.05, float(s.get("output_duration") or 0.05) * scale), 4)
        norm_shots.append(sc)
    # Fix residual frames on last shot
    used = sum(s["output_duration"] for s in norm_shots[:-1])
    norm_shots[-1]["output_duration"] = round(max(0.05, float(duration) - used), 4)

    scratch = out_path.parent / f"_shots_{out_path.stem}"
    scratch.mkdir(parents=True, exist_ok=True)
    shot_paths: list[Path] = []
    try:
        for i, shot in enumerate(norm_shots):
            sp = scratch / f"shot_{i:02d}.mp4"
            shot_src = img_path
            raw_src = shot.get("source_path") or ""
            if raw_src:
                cand = Path(raw_src)
                if cand.is_file():
                    shot_src = cand
            _render_editorial_shot(
                shot_src, sp, shot, width, height, fps, zoom_amount=zoom_amount
            )
            shot_paths.append(sp)
        assembled = scratch / "assembled.mp4"
        _concat_shot_clips(shot_paths, assembled)
        needs_post = bool(
            caption_overlay
            or text_effect_filters
            or timed_overlays
            or fade_in > 0
            or fade_out > 0
        )
        if needs_post:
            _apply_overlays_to_clip(
                assembled,
                out_path,
                duration,
                width,
                height,
                fps,
                caption_overlay=caption_overlay,
                text_effect_filters=text_effect_filters,
                timed_overlays=timed_overlays,
                fade_in=fade_in,
                fade_out=fade_out,
                fade_color=fade_color,
            )
        else:
            shutil.copy2(assembled, out_path)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    return out_path.is_file()


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
    fade_in: float = 0.0,
    fade_out: float = 0.0,
    fade_color: str = "black",
    camera_style: str | None = None,
    avoid_blind_loop: bool = False,
    edit_decision: dict | None = None,
):
    """
    timed_overlays: list of (png_path, local_start, local_end[, animation])
    for Pillow text when ffmpeg has no drawtext filter.

    When edit_decision contains multiple shots (or punch-in/reframe), the
    EditorialEngine path assembles coverage before overlays/fades.
    """
    if isinstance(edit_decision, dict) and edit_decision.get("shots"):
        shots = edit_decision.get("shots") or []
        # Use editorial path for multi-shot or punch/reframe/image-motion strategies
        strategy = str(edit_decision.get("strategy") or "")
        use_editorial = (
            len(shots) > 1
            or strategy in (
                "DUAL_ASSET",
                "MULTI_SHOT",
                "PUNCH_IN",
                "REFRAME",
                "IMAGE_MOTION",
                "MONTAGE",
                "RETIME",
                "HOLD_TAIL",
            )
            or any(float(s.get("scale") or 1.0) > 1.08 for s in shots if isinstance(s, dict))
            or any(
                str(s.get("source_path") or "") and Path(str(s.get("source_path"))).is_file()
                for s in shots
                if isinstance(s, dict)
            )
        )
        if use_editorial:
            ok = _render_scene_from_edit_decision(
                img_path=img_path,
                out_path=out_path,
                duration=duration,
                edit_decision=edit_decision,
                width=width,
                height=height,
                fps=fps,
                zoom_amount=zoom_amount,
                caption_overlay=caption_overlay,
                text_effect_filters=text_effect_filters,
                timed_overlays=timed_overlays,
                fade_in=fade_in,
                fade_out=fade_out,
                fade_color=fade_color,
            )
            if ok:
                return

    frames = max(int(round(duration * fps)), 1)
    # Use exact frame count so concat length matches audio timeline
    clip_dur = frames / fps
    timed_overlays = list(timed_overlays or [])
    encode_args = _cpu_encode_argv()
    fade_suffix = _fade_vf_suffix(clip_dur, fade_in, fade_out, fade_color)

    # Single-shot edit decision may still carry hold_tail / avoid loop
    hold_tail = False
    if isinstance(edit_decision, dict):
        avoid_blind_loop = avoid_blind_loop or bool(edit_decision.get("avoid_blind_loop"))
        shots = edit_decision.get("shots") or []
        strategy = str(edit_decision.get("strategy") or "")
        if strategy == "HOLD_TAIL":
            hold_tail = True
        if len(shots) == 1 and isinstance(shots[0], dict):
            if shots[0].get("hold_tail"):
                hold_tail = True
            cam = shots[0].get("camera_style")
            if cam and not camera_style:
                camera_style = str(cam)

    if is_video_file(img_path):
        base_vf = f"{_video_fit_filter(width, height, fps)},setpts=PTS-STARTPTS"
        if hold_tail:
            try:
                from providers.media_clip.ffmpeg_clip import probe_duration

                src_dur = probe_duration(img_path) or 0.0
            except Exception:
                src_dur = 0.0
            pad = max(0.0, clip_dur - src_dur) if src_dur > 0 else 0.0
            if pad > 0.08:
                base_vf = f"{base_vf},tpad=stop_mode=clone:stop_duration={pad:.3f}"
            input_args = ["-i", str(img_path)]
        else:
            # Continuous playback: loop the source when it is shorter than the
            # scene. Freeze (tpad clone) is reserved for explicit HOLD_TAIL.
            input_args = ["-stream_loop", "-1", "-i", str(img_path)]
    elif zoom:
        base_vf = _zoompan_filter(
            width,
            height,
            fps,
            frames,
            zoom_in,
            zoom_amount,
            camera_style=camera_style,
        )
        input_args = ["-loop", "1", "-i", str(img_path)]
    else:
        base_vf = _static_filter(width, height)
        input_args = ["-loop", "1", "-i", str(img_path)]

    # Collect extra image inputs: static caption first, then timed smart-text PNGs
    extra_inputs: list[str] = []
    # (input_idx, t0, t1, animation, text_center)
    layers: list[tuple[int, float | None, float | None, str | None, tuple[int, int] | None]] = []
    next_idx = 1
    if caption_overlay is not None:
        extra_inputs += ["-loop", "1", "-i", str(caption_overlay)]
        layers.append((next_idx, None, None, None, None))
        next_idx += 1
    for item in timed_overlays:
        png, t0, t1 = item[0], item[1], item[2]
        anim = item[3] if len(item) > 3 else None
        center = item[4] if len(item) > 4 else None
        extra_inputs += ["-loop", "1", "-i", str(png)]
        layers.append((next_idx, float(t0), float(t1), anim, center))
        next_idx += 1

    if layers or text_effect_filters or fade_suffix:
        parts = [f"[0:v]{base_vf}[v0]"]
        cur = "v0"
        for layer_i, (in_idx, t0, t1, anim, center) in enumerate(layers):
            lab_in = f"ov{layer_i}"
            lab_out = f"v{layer_i + 1}"
            motion = _overlay_motion_chain(t0, t1, anim, width, height)
            parts.append(f"[{in_idx}:v]{motion}[{lab_in}]")
            if t0 is None:
                enable = ""
            else:
                # Keep the window: the fades shape the edges, `enable` still
                # keeps the overlay out of the graph the rest of the time.
                enable = f":enable='{_escape_overlay_enable(t0, t1)}'"
            xy = _overlay_xy(t0, anim, center)
            parts.append(
                f"[{cur}][{lab_in}]overlay={xy}:format=auto{enable}[{lab_out}]"
            )
            cur = lab_out
        tail_bits = []
        if text_effect_filters:
            tail_bits.append(text_effect_filters)
        if fade_suffix:
            tail_bits.append(fade_suffix)
        tail_bits.append("format=yuv420p")
        parts.append(f"[{cur}]{','.join(tail_bits)}[vout]")
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
            *encode_args,
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
            *encode_args,
            "-pix_fmt", "yuv420p",
            "-an",
            str(out_path),
        ]

    _run_ffmpeg_encode(cmd, img_path.name)


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
    visual_transitions: bool = True,
    transition_by_scene: dict | None = None,
    camera_by_scene: dict | None = None,
    edit_decisions_by_scene: dict | None = None,
    editorial_timeline: dict | None = None,
    render_cache_state_dir: Path | None = None,
    perf=None,
    progress_cb=None,
):
    """
    render_cache_state_dir, perf, progress_cb: all optional, all default to
    None/no-op (Semantic YT Studio 2.0 — Batch 1). Every existing caller and
    test that does not pass them gets byte-for-byte the same behavior as
    before this batch — caching, instrumentation, and progress reporting are
    strictly additive.

      render_cache_state_dir: a project's state/ directory. When given, a
        RenderCache is opened there and unchanged scene clips are reused
        instead of re-encoded (PHASE 4/5). When None, no cache is used at
        all — every scene renders exactly as it always has.
      perf: an optional perf_instrumentation.PerfRecorder to record
        scene_render/mux timings and cache hit/miss counts into.
      progress_cb: an optional callable(ProgressEvent) invoked once per
        scene and once for mux — the caller (app.py) is responsible for how
        that turns into UI updates (PHASE 9); render_video() never touches
        the UI queue directly.
    """
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
    display_timeline = _scene_display_timeline(aligned_rows, audio_end)
    width, height = (int(x) for x in resolution.split("x"))
    per_scene_fx = scene_text_effects or [[] for _ in aligned_rows]

    if bg_audio is not None and not Path(bg_audio).is_file():
        sys.exit(f"ERROR: background audio not found: {bg_audio}")

    work_dir = Path.cwd().resolve()
    if RENDER_CLIPS_DIRNAME.startswith("._"):
        sys.exit(
            "ERROR: internal render clips dirname must not use an AppleDouble "
            f"'._' prefix (got {RENDER_CLIPS_DIRNAME!r})."
        )
    clips_dir = render_clips_dir(work_dir)
    if clips_dir.exists():
        shutil.rmtree(clips_dir)
    clips_dir.mkdir()
    print(f"[3/4] Scene clips → {clips_dir}")

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
          f"{' + smart text' if smart_fx else ''}"
          f"{' + visual transitions' if visual_transitions else ''}...")

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

    # PHASE 3: hoisted out of the per-scene loop below. editorial_timeline
    # never changes across scenes, so rebuilding the full graphics-spec list
    # from every timeline event on every single scene iteration (previously:
    # inside the loop, O(n_scenes * n_timeline_events)) was pure repeated
    # work — compute it once here instead. Each scene still filters this
    # same list down to only the specs overlapping its own window, exactly
    # as before; only the (expensive) rebuild itself moved outside the loop.
    gfx_specs_all_once: list = []
    if editorial_timeline:
        try:
            from graphics import graphics_from_timeline

            gfx_specs_all_once = graphics_from_timeline(editorial_timeline)
        except Exception as exc:
            print(f"[3/4] Graphics timeline load skipped: {exc}")
            gfx_specs_all_once = []

    # PHASE 4/5: project-scoped render cache — off entirely (pure render,
    # identical to pre-Batch-1 behavior) unless a caller opts in by passing
    # render_cache_state_dir. See render_cache.py for the invalidation rules.
    render_cache = None
    if render_cache_state_dir is not None:
        try:
            from render_cache import RenderCache

            render_cache = RenderCache(render_cache_state_dir)
        except Exception as exc:
            print(f"[3/4] Render cache unavailable, rendering without it: {exc}")
            render_cache = None

    scene_eta = None
    if progress_cb is not None:
        try:
            from progress_events import EtaEstimator

            scene_eta = EtaEstimator()
        except Exception:
            scene_eta = None

    clip_files = []
    # Real (xfade) transition requested at the boundary INTO scene i, or
    # None for a hard cut — filled in below from each scene's first shot's
    # transition_in/transition_duration (see build_xfade_filter_complex).
    real_transition_into_scene: list[tuple[str, float] | None] = [None] * n
    coverage_flags = manifest_coverage_flags(images_dir)
    for i, (img, dur, row) in enumerate(zip(image_paths, durations, aligned_rows)):
        out_clip = scene_clip_path(clips_dir, scene_clip_filename(i))
        sn = str(row.get("scene_number") or "")
        style_key = (camera_by_scene or {}).get(sn)
        use_zoom, zoom_in, camera_style = _camera_motion(
            style_key,
            index=i,
            zoom=zoom,
        )
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
        scene_start = float(display_timeline[i][0])
        scene_end = float(display_timeline[i][1])

        # Prefer timeline graphics (lower-third panel) over floating Smart Text.
        # gfx_specs_all_once was built once, before this loop (PHASE 3) —
        # reused here instead of rebuilding the full spec list every scene.
        scene_gfx_specs = []
        if editorial_timeline:
            try:
                from graphics import render_graphics_for_scene
                from typography.composition import analyze_media as analyze_gfx_frame

                gfx_specs_all = gfx_specs_all_once
                # Any graphic overlapping this scene window (time-native, not scene-bound).
                scene_gfx_specs = [
                    s for s in gfx_specs_all
                    if float(s.start) < scene_end and float(s.end) > scene_start
                ]
                if scene_gfx_specs:
                    gfx_dir = Path("graphics_overlays")
                    gfx_dir.mkdir(exist_ok=True)
                    gfx_comp = analyze_gfx_frame(
                        img,
                        at_time=min(float(dur) * 0.5, 2.0),
                        ffmpeg="ffmpeg",
                        is_video=is_video_file(img),
                        scratch_dir=gfx_dir,
                    )
                    gfx_timed = render_graphics_for_scene(
                        scene_gfx_specs,
                        scene_number=str(row.get("scene_number") or ""),
                        scene_start=scene_start,
                        scene_end=scene_end,
                        width=width,
                        height=height,
                        out_dir=gfx_dir,
                        composition=gfx_comp or None,
                    )
                    timed_overlays.extend(gfx_timed)
            except Exception as exc:
                print(f"[3/4] Graphics overlays skipped for scene clip {i + 1}: {exc}")
                scene_gfx_specs = []

        smart_fx_list = list(per_scene_fx[i] or [])
        if smart_fx_list and scene_gfx_specs:
            try:
                from graphics.conflicts import filter_smart_text_for_graphics

                before = len(smart_fx_list)
                smart_fx_list = filter_smart_text_for_graphics(
                    smart_fx_list,
                    scene_gfx_specs,
                    scene_start=scene_start,
                    scene_end=scene_end,
                )
                skipped = before - len(smart_fx_list)
                if skipped:
                    print(
                        f"[3/4] Skipped {skipped} Smart Text overlay(s) on scene "
                        f"{row.get('scene_number')} — graphics lower-third preferred."
                    )
            except Exception:
                pass

        if smart_fx_list:
            # Always burn modern typography via Pillow full-frame overlays.
            # System ffmpeg often lacks drawtext; even when present, drawtext
            # cannot reproduce theme fonts / plates / placement. Never fall
            # back to the old Arial caption renderer.
            try:
                from typography import render_style_overlay, typography_params_for_effect
                from typography.debug import log_typography_event, typography_debug_enabled

                from typography.composition import analyze_media, merge_composition

                smart_dir = Path("smart_text_overlays")
                smart_dir.mkdir(exist_ok=True)

                # Look at the actual picture once per scene, so placement can
                # keep type off the subject, off blown-out areas, and off any
                # captions already burned into the source clip. Analysis is
                # advisory: on any failure this is {} and placement behaves
                # exactly as it did before.
                scene_composition = analyze_media(
                    img,
                    at_time=min(float(dur) * 0.5, 2.0),
                    ffmpeg="ffmpeg",
                    is_video=is_video_file(img),
                    scratch_dir=smart_dir,
                )

                for j, fx in enumerate(smart_fx_list):
                    raw = str(fx.get("text") or "").strip()
                    if not raw:
                        continue
                    fx_payload = dict(fx)
                    fx_payload["scene_duration"] = float(dur)
                    fx_payload["composition"] = merge_composition(
                        fx.get("composition"), scene_composition,
                    )
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
                    ov_metrics: dict = {}
                    png = render_style_overlay(
                        fx_payload,
                        png_path,
                        width,
                        height,
                        params=params,
                        record_history=False,
                        metrics=ov_metrics,
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
                    center = None
                    if ov_metrics:
                        center = (
                            int(ov_metrics.get("center_x") or 0),
                            int(ov_metrics.get("center_y") or 0),
                        )
                    timed_overlays.append((png, t0, t1, anim, center))
            except Exception as exc:
                # Do not silently substitute old Arial text — surface the failure.
                print(f"[3/4] Smart typography failed for scene clip {i + 1}: {exc}")
                fx_filters = ""

        fade_in = fade_out = 0.0
        fade_color = "black"
        if visual_transitions:
            style_map = transition_by_scene or {}
            # Only AI/heuristic-selected scenes get a visual transition; others hard-cut.
            sn = str(row.get("scene_number") or "")
            style_in = style_map.get(sn) if style_map else None
            next_sn = (
                str(aligned_rows[i + 1].get("scene_number") or "")
                if i + 1 < n
                else ""
            )
            style_out = style_map.get(next_sn) if style_map and next_sn else None
            if style_in:
                fade_in, _, fade_color = transition_fade_params(style_in, dur)
            if style_out:
                _, fade_out, _ = transition_fade_params(style_out, dur)

        sn_key = str(row.get("scene_number") or "")
        cov = coverage_flags.get(sn_key) or coverage_flags.get(str(int(sn_key)) if sn_key.isdigit() else sn_key)
        avoid_loop = bool(cov and cov.get("avoid_blind_loop"))
        edit_dec = None
        if edit_decisions_by_scene:
            edit_dec = (
                edit_decisions_by_scene.get(sn_key)
                or edit_decisions_by_scene.get(sn_key.zfill(3))
                or edit_decisions_by_scene.get(sn_key.lstrip("0") or sn_key)
            )
        if isinstance(edit_dec, dict) and edit_dec.get("avoid_blind_loop"):
            avoid_loop = True

        if isinstance(edit_dec, dict) and edit_dec.get("shots"):
            first_shot = edit_dec["shots"][0]
            if isinstance(first_shot, dict):
                t_type = str(first_shot.get("transition_in") or "cut").lower()
                t_dur = float(first_shot.get("transition_duration") or 0.0)
                t_dir = str(first_shot.get("transition_direction") or "")
                if t_type in TRANSITION_TYPES and t_type != "cut" and t_dur > 0.0:
                    real_transition_into_scene[i] = (t_type, t_dur, t_dir)

        _scene_clip_kwargs = dict(
            img_path=img,
            out_path=out_clip,
            duration=dur,
            width=width,
            height=height,
            fps=fps,
            zoom=use_zoom,
            zoom_in=zoom_in,
            zoom_amount=zoom_amount,
            caption_overlay=overlay,
            text_effect_filters=fx_filters,
            timed_overlays=timed_overlays,
            camera_style=camera_style,
            fade_in=fade_in,
            fade_out=fade_out,
            fade_color=fade_color,
            avoid_blind_loop=avoid_loop,
            edit_decision=edit_dec if isinstance(edit_dec, dict) else None,
        )

        cache_hit = False
        _perf_ctx = perf.timer("scene_render", scene_id=sn_key) if perf is not None else contextlib.nullcontext()
        with _perf_ctx:
            if render_cache is not None:
                try:
                    from render_cache import build_scene_cache_key

                    cache_key = build_scene_cache_key(
                        scene_number=sn_key,
                        encode_args=_cpu_encode_argv(),
                        **_scene_clip_kwargs,
                    )
                    cached_clip = render_cache.get(sn_key, cache_key)
                except Exception as exc:
                    # Any failure building/looking up the key is a miss —
                    # never let cache-layer trouble block a render.
                    print(f"[3/4] Render cache lookup skipped for scene {sn_key}: {exc}")
                    cache_key = None
                    cached_clip = None
                if cached_clip is not None and render_cache.reuse(cached_clip, out_clip):
                    cache_hit = True

            if not cache_hit:
                _render_scene_clip(**_scene_clip_kwargs)
                if render_cache is not None and cache_key is not None:
                    try:
                        render_cache.put(sn_key, cache_key, out_clip)
                    except Exception as exc:
                        print(f"[3/4] Render cache store skipped for scene {sn_key}: {exc}")

        # Real B-roll overlay: composite any genuinely-overlapping VIDEO_2
        # clip(s) (see reconcile_timeline_into_decisions) onto the just-
        # rendered scene clip. Applied AFTER cache lookup/render (a cache
        # hit's stored clip never has broll baked in — the cache key
        # doesn't cover it) so it always reflects the current broll state;
        # cheap in practice since most scenes have no broll entries at all.
        broll_entries = edit_dec.get("broll") if isinstance(edit_dec, dict) else None
        if broll_entries:
            for b_i, broll in enumerate(broll_entries):
                broll_src = broll.get("source_path")
                if not broll_src or not Path(broll_src).is_file():
                    continue
                composited = out_clip.parent / f"{out_clip.stem}_broll{b_i}{out_clip.suffix}"
                ok = composite_broll_overlay(
                    out_clip, Path(broll_src), composited,
                    overlay_start=float(broll.get("overlay_start") or 0.0),
                    overlay_duration=float(broll.get("overlay_duration") or 0.0),
                    width=width, height=height, fps=fps,
                    broll_source_start=float(broll.get("source_start") or 0.0),
                    broll_speed=float(broll.get("speed") or 1.0),
                    scale=float(broll.get("scale") or 0.4),
                    position=str(broll.get("position") or "bottom_right"),
                )
                if ok:
                    try:
                        composited.replace(out_clip)
                    except OSError:
                        pass
                else:
                    print(f"[3/4] B-roll overlay failed for scene {sn_key} — kept base clip without it.")
                    try:
                        composited.unlink(missing_ok=True)
                    except OSError:
                        pass

        if perf is not None:
            perf.note_cache(cache_hit)
        if progress_cb is not None:
            try:
                from progress_events import make_event

                progress_cb(
                    make_event(
                        "rendering",
                        i + 1,
                        n,
                        scene_id=sn_key,
                        message=f"Scene {sn_key}" + (" (cached)" if cache_hit else ""),
                        eta=scene_eta,
                    )
                )
            except Exception:
                pass

        clip_files.append(out_clip)

    missing_after_render = [p for p in clip_files if not Path(p).is_file()]
    if missing_after_render:
        sample = missing_after_render[0]
        sys.exit(
            f"ERROR: {len(missing_after_render)} scene clip(s) missing after render "
            f"(e.g. {sample}). Cannot mux."
        )

    concat_list_path = concat_list_path_for(work_dir)
    write_ffmpeg_concat_list(clip_files, concat_list_path)
    scene_numbers = [
        str(row.get("scene_number") or (i + 1))
        for i, row in enumerate(aligned_rows)
    ]
    if progress_cb is not None:
        try:
            from progress_events import make_event

            progress_cb(make_event("mux", 0, 1, message="Finalizing video"))
        except Exception:
            pass
    with (perf.timer("mux") if perf is not None else contextlib.nullcontext()):
        run_final_mux(
            concat_list_path=concat_list_path,
            audio_path=audio_path,
            output_path=output_path,
            bg_audio=bg_audio,
            bg_volume=bg_volume,
            clip_files=clip_files,
            scene_numbers=scene_numbers,
            transitions=real_transition_into_scene[1:] if len(clip_files) > 1 else None,
            clip_durations=list(durations) if len(clip_files) > 1 else None,
        )
    if progress_cb is not None:
        try:
            from progress_events import make_event

            progress_cb(make_event("mux", 1, 1, status="done", message="Mux complete"))
        except Exception:
            pass

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