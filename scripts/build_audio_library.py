#!/usr/bin/env python3
r"""Build the bundled Audio Director library from a source sound library.

BUILD TIME ONLY. Never runs in the shipped application, and never copies the
source library wholesale — only the selected, transcoded assets are emitted.

    DISCOVER -> MEASURE -> CLASSIFY -> QUALITY GATE -> REDUNDANCY
    -> COVERAGE -> VARIETY -> CONVERT -> CATALOG -> VALIDATE

Asset count and distribution format are BUILD PARAMETERS, deliberately not
constants: the winner is decided by validation, not by this file.

    python scripts/build_audio_library.py \
        --source ~/Downloads/videogen-sfx-source \
        --out assets/bundled-sfx \
        --format opus128 --target 110
"""
from __future__ import annotations

import argparse
import json
import math
import re
import statistics as st
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

REPO = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------- formats
# Every profile must decode/seek/mix through the SAME bundled ffmpeg the app
# uses. WAV stays first-class so the existing pipeline keeps working while the
# format decision is still open.
FORMATS: Dict[str, dict] = {
    "wav48":   {"ext": "wav",  "codec": "pcm_s16le", "args": ["-ar", "48000", "-c:a", "pcm_s16le"]},
    "flac48":  {"ext": "flac", "codec": "flac",      "args": ["-ar", "48000", "-c:a", "flac", "-compression_level", "8"]},
    "opus96":  {"ext": "opus", "codec": "opus",      "args": ["-ar", "48000", "-c:a", "libopus", "-b:a", "96k"]},
    "opus128": {"ext": "opus", "codec": "opus",      "args": ["-ar", "48000", "-c:a", "libopus", "-b:a", "128k"]},
}

AUDIO_EXTS = {".wav", ".flac", ".aif", ".aiff", ".mp3", ".ogg", ".m4a", ".opus"}

# Filename evidence only. Never the sole basis for SFX/ambience — the SIGNAL
# decides that (see classify()). Absence of a match is not disqualifying.
CATEGORY_PATTERNS: Dict[str, str] = {
    "whoosh": r"whoosh|swoosh|swish", "impact": r"impact|hit|slam|crash|smash|thud|bang",
    "transition": r"transition|stinger|sweep", "riser": r"riser|rise|build|uplift",
    "ui": r"\bui\b|button|click|menu|beep|notif|interface",
    "technology": r"tech|digital|glitch|computer|robot|electric|sci-?fi|cyber|data",
    "mechanical": r"mechan|gear|lever|lock|machine|motor|servo",
    "vehicle": r"car|truck|train|vehicle|engine|drive",
    "object": r"book|clock|door|glass|metal|wood|paper|coin|key",
    "movement": r"foot|step|cloth|fabric|walk|run",
    "nature": r"nature|forest|jungle|bird|wildlife", "rain": r"rain|storm|thunder",
    "wind": r"wind|breeze|gale", "water": r"water|stream|creek|river",
    "ocean": r"ocean|sea|wave|surf", "city": r"city|urban|street",
    "traffic": r"traffic|road|highway", "room": r"room|interior|indoor|house|office",
    "crowd": r"crowd|people|chatter|cafe", "industrial": r"industr|factory|plant",
    "machinery": r"machin|generator|turbine", "space": r"space|cosmic|alien",
    "cinematic": r"cinematic|atmos|ambience|ambient|drone|tension",
}
_CAT_RE = {k: re.compile(v, re.I) for k, v in CATEGORY_PATTERNS.items()}

# ---------------------------------------------------------------- taxonomy
# The RUNTIME enumerates a fixed set of category folders (smart_editing.
# SFX_CATEGORIES) and seeds ~/.videogen/sfx by walking them, so the generated
# library must lay its files out in exactly those folders. Emitting the finer
# semantic taxonomy as folders instead left 73 of 110 catalog entries
# unreachable after seeding.
#
# The fine category is NOT lost: it is preserved per entry as
# `semantic_category`, and every matched keyword stays in `tags`, so a future
# ranking pass keeps full granularity while today's runtime keeps working.
RUNTIME_CATEGORIES = (
    "whoosh", "impact", "ui", "text", "transition",
    "riser", "cinematic", "technology", "ambience",
)

_SEMANTIC_TO_RUNTIME = {
    # identity
    "whoosh": "whoosh", "impact": "impact", "ui": "ui", "transition": "transition",
    "riser": "riser", "cinematic": "cinematic", "technology": "technology",
    # physical events read as impacts
    "mechanical": "impact", "object": "impact", "vehicle": "impact",
    # motion reads as whoosh
    "movement": "whoosh",
    # everything environmental is ambience when the signal says so (handled by
    # audio_type below); anything left over is neutral cinematic texture
    "nature": "cinematic", "rain": "cinematic", "wind": "cinematic",
    "water": "cinematic", "ocean": "cinematic", "city": "cinematic",
    "traffic": "cinematic", "room": "cinematic", "crowd": "cinematic",
    "industrial": "technology", "machinery": "technology", "space": "cinematic",
    "uncategorized": "cinematic",
}

# `text` has no source keyword, so it is defined by measurable shape: a short,
# bright, percussive interface sound is what a text-reveal cue is.
def _is_text_cue(a: "Asset") -> bool:
    return (
        a.duration < 1.5
        and a.transient_character == "percussive"
        and a.spectral_character.startswith("bright")
    )


# Quality gate. Tuned to exclude the measurably unusable WITHOUT discarding
# merely-unusual material (a rare sound at healthy level survives).
MIN_PEAK_DB = -40.0
MAX_SILENCE_RATIO = 0.6
MIN_QUALITY = 45.0


def ffbin(name: str) -> str:
    local = REPO / "bin" / name
    return str(local) if local.is_file() else name


@dataclass
class Asset:
    path: Path
    rel: str
    size: int = 0
    duration: float = 0.0
    sample_rate: int = 0
    channels: int = 0
    mean_db: Optional[float] = None
    peak_db: Optional[float] = None
    silence_ratio: float = 0.0
    centroid_hz: Optional[float] = None
    flatness: Optional[float] = None
    transient_density: float = 0.0
    crest: Optional[float] = None
    ok: bool = False
    error: str = ""
    cats: List[str] = field(default_factory=list)
    quality: float = 0.0
    reason: str = ""
    similarity_group: int = -1

    # ---- derived, deterministic ----
    @property
    def dur_band(self) -> str:
        v = self.duration
        return "stab" if v < 1 else "short" if v < 5 else "medium" if v < 30 else "long" if v < 120 else "verylong"

    @property
    def transient_character(self) -> str:
        if self.transient_density >= 0.08 or (self.crest or 0) >= 20:
            return "percussive"
        return "articulated" if self.transient_density >= 0.03 else "sustained"

    @property
    def spectral_character(self) -> str:
        c, f = self.centroid_hz or 0, self.flatness or 0
        if c < 800:
            return "low/rumble"
        if c < 2500:
            return "warm/body"
        if c < 5000:
            return "mid/present"
        return "bright/noisy" if f > 0.35 else "bright/tonal"

    @property
    def intensity(self) -> str:
        m = self.mean_db if self.mean_db is not None else -99
        return "high" if m > -18 else "medium" if m > -28 else "low"

    @property
    def energy(self) -> str:
        return {"high": "strong", "medium": "moderate", "low": "subtle"}[self.intensity]

    @property
    def audio_type(self) -> str:
        """Signal-derived, NOT filename-derived: long + sustained == ambience."""
        if self.duration >= 60:
            return "ambience"
        if self.duration >= 25 and self.transient_character == "sustained":
            return "ambience"
        return "sfx"

    @property
    def semantic_category(self) -> str:
        """Fine-grained category from filename evidence — kept in the catalog."""
        return self.cats[0] if self.cats else ("cinematic" if self.audio_type == "ambience" else "uncategorized")

    @property
    def category(self) -> str:
        """Folder the runtime will look in — one of RUNTIME_CATEGORIES."""
        if self.audio_type == "ambience":
            return "ambience"
        if _is_text_cue(self):
            return "text"
        return _SEMANTIC_TO_RUNTIME.get(self.semantic_category, "cinematic")

    @property
    def subcategory(self) -> str:
        return f"{self.transient_character}/{self.spectral_character}"


# ------------------------------------------------------------- 1. DISCOVER
def discover(source: Path) -> List[Asset]:
    out: List[Asset] = []
    for p in sorted(source.rglob("*")):
        if p.is_file() and p.suffix.lower() in AUDIO_EXTS and not p.name.startswith("._"):
            out.append(Asset(path=p, rel=str(p.relative_to(source))))
    return out


# -------------------------------------------------------------- 2. MEASURE
def measure(a: Asset, ffmpeg: str, ffprobe: str) -> Asset:
    try:
        a.size = a.path.stat().st_size
        r = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries",
             "format=duration:stream=sample_rate,channels", "-of", "json", str(a.path)],
            capture_output=True, text=True, timeout=120)
        d = json.loads(r.stdout or "{}")
        stream = (d.get("streams") or [{}])[0]
        a.duration = float((d.get("format") or {}).get("duration") or 0)
        a.sample_rate = int(stream.get("sample_rate") or 0)
        a.channels = int(stream.get("channels") or 0)

        # ONE decode for loudness, silence and spectral shape.
        r = subprocess.run(
            [ffmpeg, "-hide_banner", "-nostats", "-i", str(a.path), "-af",
             "aformat=channel_layouts=mono,aresample=48000,"
             "aspectralstats=measure=centroid+flatness,"
             "ametadata=mode=print:file=-,"
             "volumedetect,silencedetect=n=-50dB:d=0.5,astats=metadata=1:reset=0",
             "-f", "null", "-"], capture_output=True, text=True, timeout=600)
        txt = r.stdout + r.stderr
        m = re.search(r"mean_volume:\s*(-?[\d.]+) dB", txt); a.mean_db = float(m.group(1)) if m else None
        m = re.search(r"max_volume:\s*(-?[\d.]+) dB", txt);  a.peak_db = float(m.group(1)) if m else None
        m = re.search(r"Crest factor:\s*([\d.]+)", txt);     a.crest = float(m.group(1)) if m else None
        sil = sum(float(x) for x in re.findall(r"silence_duration:\s*([\d.]+)", txt))
        a.silence_ratio = round(sil / a.duration, 4) if a.duration else 0.0
        cen = [float(x) for x in re.findall(r"aspectralstats\.1\.centroid=([\d.eE+-]+)", txt)]
        fla = [float(x) for x in re.findall(r"aspectralstats\.1\.flatness=([\d.eE+-]+)", txt)]
        if cen:
            a.centroid_hz = round(st.median(cen), 1)
            jumps = sum(1 for p, q in zip(cen, cen[1:]) if abs(q - p) > max(200, 0.5 * max(p, 1)))
            a.transient_density = round(jumps / max(len(cen) - 1, 1), 4)
        if fla:
            a.flatness = round(st.median(fla), 4)
        a.ok = a.duration > 0
    except Exception as exc:                        # a bad file must not kill the build
        a.ok = False
        a.error = f"{type(exc).__name__}: {exc}"[:120]
    return a


# ------------------------------------------------------- 3. CLASSIFY + GATE
def classify(a: Asset) -> Asset:
    hay = f"{a.rel} {a.path.name}"
    a.cats = [k for k, rx in _CAT_RE.items() if rx.search(hay)]
    peak = a.peak_db if a.peak_db is not None else -99
    mean = a.mean_db if a.mean_db is not None else -99
    q = 0.0
    q += 25 if -24 <= peak <= -0.5 else (10 if peak > -40 else 0)
    q += 25 if -30 <= mean <= -12 else (10 if mean > -45 else 0)
    q += 20 * (1 - min(a.silence_ratio, 1))
    q += 15 if a.channels <= 2 else 5
    q += 15 if a.cats else 8            # unmatched is penalised, NOT excluded
    if peak >= -0.1:
        q -= 10                          # clipping risk
    a.quality = round(max(0.0, min(100.0, q)), 1)
    return a


def passes_quality(a: Asset) -> bool:
    return (a.ok and (a.peak_db or -99) > MIN_PEAK_DB
            and a.silence_ratio <= MAX_SILENCE_RATIO and a.quality >= MIN_QUALITY)


# ------------------------------------------------- 4. REDUNDANCY / DISTANCE
_W = (1.0, 1.2, 2.0, 0.8, 1.0)


def _vec(a: Asset) -> Tuple[float, ...]:
    return (math.log10(max(a.centroid_hz or 1, 1)), a.flatness or 0.0, a.transient_density,
            math.log10(max(a.duration, 0.05)), ((a.mean_db or -60) + 60) / 60.0)


def distance(a: Asset, b: Asset) -> float:
    return math.sqrt(sum(w * (p - q) ** 2 for w, p, q in zip(_W, _vec(a), _vec(b))))


def group_similar(assets: Sequence[Asset], threshold: float) -> int:
    """Single-link grouping in FEATURE space (not vendor pack): two files from
    different packs can be interchangeable, two from one pack may not be."""
    gid = 0
    for i, a in enumerate(assets):
        if a.similarity_group >= 0:
            continue
        a.similarity_group = gid
        for b in assets[i + 1:]:
            if b.similarity_group < 0 and distance(a, b) < threshold:
                b.similarity_group = gid
        gid += 1
    return gid


# ---------------------------------------------------------- 5. COVERAGE
def cells(a: Asset) -> Set[tuple]:
    out: Set[tuple] = set()
    # Coverage is measured on the SEMANTIC category, not the runtime folder:
    # mapping several semantic categories onto one folder must not collapse
    # selection diversity (e.g. mechanical/object/vehicle all land in impact/).
    for c in (a.cats or [a.semantic_category]):
        out |= {("cat", c), ("cat_dur", c, a.dur_band), ("cat_int", c, a.intensity)}
    out.add(("type_trans_spec", a.audio_type, a.transient_character, a.spectral_character))
    out.add(("type_dur_int", a.audio_type, a.dur_band, a.intensity))
    return out


def select(pool: List[Asset], target: int, sep_cov: float, sep_var: float,
           uncategorized_weight: float = 0.45, log=print) -> Tuple[List[Asset], Set[tuple], Set[tuple], int]:
    universe: Set[tuple] = set().union(*[cells(a) for a in pool]) if pool else set()
    chosen: List[Asset] = []
    covered: Set[tuple] = set()

    # Stage A — coverage. Runs to saturation; the count is an OUTPUT.
    while True:
        best, best_score = None, -1.0
        for a in pool:
            if a in chosen:
                continue
            gain = len(cells(a) - covered)
            if gain == 0:
                continue
            uniq = min((distance(a, c) for c in chosen), default=9.0)
            if uniq < sep_cov:
                continue
            score = (gain ** 1.6) * (a.quality / 100) * min(uniq, 3.0) / (1 + (a.size / 1e6) / 400)
            if score > best_score:
                best, best_score = a, score
        if best is None:
            break
        new = cells(best) - covered
        best.reason = (f"coverage: {best.category}/{best.audio_type}/{best.dur_band}/"
                       f"{best.intensity}/{best.transient_character} (+{len(new)} cells)")
        chosen.append(best); covered |= cells(best)
    saturated = len(chosen)
    log(f"  stage A (coverage): {saturated} assets, {len(covered)}/{len(universe)} cells")

    # Stage B — variety. Only after coverage saturates; prevents 4 near-identical whooshes.
    while len(chosen) < target:
        best, best_score = None, -1.0
        for a in pool:
            if a in chosen:
                continue
            uniq = min((distance(a, c) for c in chosen), default=9.0)
            if uniq < sep_var:
                continue
            # Load must be counted against a SHARED bucket for unlabelled files.
            # Treating "uncategorized" as its own category made every unlabelled
            # file look under-represented, and stage B filled 45% of the bundle
            # with acoustically-diverse but semantically-unusable material.
            if a.cats:
                load = min(sum(1 for c in chosen if set(c.cats) & set(a.cats)), 12)
                label_bonus = 1.0
            else:
                load = min(sum(1 for c in chosen if not c.cats), 12)
                label_bonus = uncategorized_weight
            score = (uniq * (a.quality / 100) * label_bonus
                     / (1 + load * 0.35) / (1 + (a.size / 1e6) / 500))
            if score > best_score:
                best, best_score = a, score
        if best is None:
            break
        best.reason = (f"variety: {best.category}/{best.transient_character}/"
                       f"{best.spectral_character}/{best.intensity}")
        chosen.append(best)
    log(f"  stage B (variety) : +{len(chosen)-saturated} assets -> {len(chosen)} total")
    return chosen, covered, universe, saturated


# ------------------------------------------------------------- 6. CONVERT
def convert(a: Asset, dest_dir: Path, fmt: str, ffmpeg: str, index: int) -> Optional[dict]:
    spec = FORMATS[fmt]
    cat = a.category
    (dest_dir / cat).mkdir(parents=True, exist_ok=True)
    aid = f"{cat}_{index:03d}"
    rel = f"{cat}/{aid}.{spec['ext']}"
    out = dest_dir / rel
    downmix = ["-ac", "2"] if a.channels > 2 else []
    r = subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(a.path)]
                       + downmix + spec["args"] + [str(out)], capture_output=True, text=True, timeout=900)
    if r.returncode != 0 or not out.is_file():
        return None
    return {
        "id": aid, "file": rel, "format": spec["ext"], "codec": spec["codec"],
        "category": cat, "semantic_category": a.semantic_category,
        "subcategory": a.subcategory,
        "tags": sorted(set(a.cats)) or [a.audio_type],
        "audio_type": a.audio_type,
        "duration": round(a.duration, 3), "duration_band": a.dur_band,
        "sample_rate": 48000, "channels": min(a.channels, 2) or 2,
        "loudness_db": a.mean_db, "peak_db": a.peak_db,
        "silence_ratio": a.silence_ratio, "quality_score": a.quality,
        "intensity": a.intensity, "energy": a.energy,
        "transient_character": a.transient_character,
        "spectral_character": a.spectral_character,
        "centroid_hz": a.centroid_hz, "flatness": a.flatness,
        "similarity_group": a.similarity_group,
        "selection_reason": a.reason,
        "source": "Sonniss GDC", "license": "Sonniss #GameAudioGDC Bundle License",
        "commercial_use": True, "attribution": "",
    }


# ------------------------------------------------------------- 7. VALIDATE
def validate_bundled_audio_library(root: Path, ffprobe: Optional[str] = None,
                                   deep: bool = True) -> List[str]:
    """Hard gate. Returns a list of problems; empty means the library is sound.

    Reused verbatim by the build, the tests and the post-build packaged check,
    so all three enforce exactly the same contract."""
    problems: List[str] = []
    cat_path = root / "catalog.json"
    if not cat_path.is_file():
        return [f"catalog missing: {cat_path}"]
    try:
        data = json.loads(cat_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"catalog does not parse: {exc}"]
    entries = data.get("sfx") or []
    if not entries:
        problems.append("catalog has no entries")

    seen: Set[str] = set()
    for e in entries:
        rel = e.get("file") or ""
        if not rel:
            problems.append(f"{e.get('id')}: empty file field"); continue
        if Path(rel).is_absolute() or ".." in Path(rel).parts:
            problems.append(f"{e.get('id')}: non-relative or escaping path {rel!r}")
            continue
        p = root / rel
        if not p.is_file():
            problems.append(f"{e.get('id')}: missing file {rel}")
            continue
        if rel in seen:
            problems.append(f"duplicate catalog file reference {rel}")
        seen.add(rel)
        for src_key in ("source_path", "abs_path", "original_path"):
            if e.get(src_key):
                problems.append(f"{e.get('id')}: leaks source path via {src_key}")
        if deep and ffprobe:
            try:
                r = subprocess.run([ffprobe, "-v", "error", "-show_entries",
                                    "stream=codec_name,sample_rate,channels", "-of", "json", str(p)],
                                   capture_output=True, text=True, timeout=60)
                s = (json.loads(r.stdout or "{}").get("streams") or [{}])[0]
                if e.get("codec") and s.get("codec_name") != e["codec"]:
                    problems.append(f"{e['id']}: codec {s.get('codec_name')} != {e['codec']}")
                if int(s.get("sample_rate") or 0) != int(e.get("sample_rate") or 0):
                    problems.append(f"{e['id']}: sample_rate {s.get('sample_rate')} != {e.get('sample_rate')}")
                if int(s.get("channels") or 0) != int(e.get("channels") or 0):
                    problems.append(f"{e['id']}: channels {s.get('channels')} != {e.get('channels')}")
            except Exception as exc:
                problems.append(f"{e.get('id')}: does not decode ({exc})")

    exts = {f"*.{v['ext']}" for v in FORMATS.values()}
    on_disk = {str(p.relative_to(root)) for pat in exts for p in root.rglob(pat)}
    for orphan in sorted(on_disk - seen):
        problems.append(f"orphan audio file with no catalog entry: {orphan}")
    return problems


# ----------------------------------------------------------------- driver
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True, type=Path)
    ap.add_argument("--out", default=REPO / "assets" / "bundled-sfx", type=Path)
    ap.add_argument("--format", default="opus128", choices=sorted(FORMATS))
    ap.add_argument("--target", type=int, default=110, help="upper bound; coverage decides the floor")
    ap.add_argument("--sep-coverage", type=float, default=0.25)
    ap.add_argument("--sep-variety", type=float, default=0.20)
    ap.add_argument("--similarity", type=float, default=0.22)
    ap.add_argument("--uncategorized-weight", type=float, default=0.45,
                    help="stage-B preference for files with no category keyword (1.0 = neutral)")
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--dry-run", action="store_true", help="analyse + select, write nothing")
    ap.add_argument("--report", type=Path, default=None)
    a = ap.parse_args()

    ffmpeg, ffprobe = ffbin("ffmpeg"), ffbin("ffprobe")
    t0 = time.time()
    found = discover(a.source)
    print(f"[1/7] discovered {len(found)} audio files under {a.source}")
    if not found:
        print("ERROR: no audio found"); return 2

    with ThreadPoolExecutor(max_workers=a.jobs) as ex:
        assets = list(ex.map(lambda x: measure(x, ffmpeg, ffprobe), found))
    bad = [x for x in assets if not x.ok]
    print(f"[2/7] measured {len(assets)-len(bad)} ok, {len(bad)} undecodable ({time.time()-t0:.1f}s)")

    assets = [classify(x) for x in assets if x.ok]
    pool = [x for x in assets if passes_quality(x)]
    print(f"[3/7] quality gate: {len(pool)} pass, {len(assets)-len(pool)} rejected")

    groups = group_similar(pool, a.similarity)
    print(f"[4/7] redundancy: {groups} similarity groups over {len(pool)} assets")

    chosen, covered, universe, saturated = select(
        pool, a.target, a.sep_coverage, a.sep_variety,
        uncategorized_weight=a.uncategorized_weight)
    pct = 100 * len(covered) / len(universe) if universe else 0
    print(f"[5/7] selected {len(chosen)}  coverage {len(covered)}/{len(universe)} ({pct:.0f}%)")

    if a.dry_run:
        print("[dry-run] nothing written")
        return 0

    out = a.out
    if out.exists():
        for pat in {f"*.{v['ext']}" for v in FORMATS.values()}:
            for p in out.rglob(pat):
                p.unlink()
    out.mkdir(parents=True, exist_ok=True)
    # The packaging gate requires every runtime category folder to exist.
    for _c in RUNTIME_CATEGORIES:
        (out / _c).mkdir(parents=True, exist_ok=True)

    entries, failed = [], []
    per_cat: Dict[str, int] = {}
    for asset in chosen:
        c = asset.category
        per_cat[c] = per_cat.get(c, 0) + 1
        e = convert(asset, out, a.format, ffmpeg, per_cat[c])
        (entries if e else failed).append(e or asset.rel)
    print(f"[6/7] converted {len(entries)} to {a.format}, {len(failed)} failed")
    if failed:
        print("ERROR: conversion failures:", failed[:5]); return 3

    catalog = {
        "version": 2, "library_root": "${USER_SFX_ROOT}",
        "generated_by": "scripts/build_audio_library.py",
        "format": a.format,
        "preferred_sources": ["sonniss_gdc"],
        "sfx": entries,
    }
    (out / "catalog.json").write_text(json.dumps(catalog, indent=2), encoding="utf-8")

    problems = validate_bundled_audio_library(out, ffprobe=ffprobe, deep=True)
    print(f"[7/7] validation: {'OK' if not problems else str(len(problems)) + ' PROBLEMS'}")
    for p in problems[:10]:
        print("   -", p)
    if problems:
        return 4

    total = sum((out / e["file"]).stat().st_size for e in entries)
    sfx_n = sum(1 for e in entries if e["audio_type"] == "sfx")
    print(f"\n  assets {len(entries)}  sfx {sfx_n}  ambience {len(entries)-sfx_n}")
    print(f"  bundled size {total/1e6:.1f} MB   format {a.format}   elapsed {time.time()-t0:.0f}s")
    if a.report:
        a.report.write_text(json.dumps({
            "source_files": len(found), "undecodable": len(bad), "pool": len(pool),
            "similarity_groups": groups, "selected": len(entries),
            "coverage_saturated_at": saturated,
            "coverage": {"covered": len(covered), "universe": len(universe), "pct": round(pct, 1)},
            "sfx": sfx_n, "ambience": len(entries) - sfx_n,
            "format": a.format, "bytes": total,
        }, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
