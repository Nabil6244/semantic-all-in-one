"""Optional Smart Text Effects + SFX layer. Fast, cached, skipped when disabled."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import wave
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

# Reuse alignment tokenization from the existing renderer pipeline.
from video_generator import is_distinctive, split_words, words_match

TEXT_EFFECT_PRESETS = (
    "fade",
    "highlight",
    "rise",
    "pop",
    "punch",
    "scale",
    "word_reveal",
    "impact",
)

INTENSITY_LEVELS = ("low", "medium", "high")
MODES = ("smart", "automatic")
SMART_EDITING_VERSION = 3

SFX_CATEGORIES = (
    "whoosh",
    "impact",
    "ui",
    "text",
    "transition",
    "riser",
    "cinematic",
    "technology",
    "ambience",
)

DEFAULT_SETTINGS: Dict[str, Any] = {
    "text_effects": True,
    "sound_effects": True,
    "intensity": "medium",
    "mode": "smart",
}


@dataclass
class SmartEditingSettings:
    text_effects: bool = True
    sound_effects: bool = True
    intensity: str = "medium"
    mode: str = "smart"

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "SmartEditingSettings":
        raw = data or {}
        intensity = str(raw.get("intensity") or "medium").lower()
        mode = str(raw.get("mode") or "smart").lower()
        if intensity not in INTENSITY_LEVELS:
            intensity = "medium"
        if mode not in MODES:
            mode = "smart"
        return cls(
            text_effects=bool(raw.get("text_effects", True)),
            sound_effects=bool(raw.get("sound_effects", True)),
            intensity=intensity,
            mode=mode,
        )

    def enabled(self) -> bool:
        return self.text_effects or self.sound_effects

    def fingerprint(self) -> str:
        payload = json.dumps(asdict(self), sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


@dataclass
class SmartEditingPlan:
    text_effects: List[dict] = field(default_factory=list)
    sfx_events: List[dict] = field(default_factory=list)
    whisper_words: List[list] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "text_effects": self.text_effects,
            "sfx_events": self.sfx_events,
            "whisper_words": self.whisper_words,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SmartEditingPlan":
        return cls(
            text_effects=list(data.get("text_effects") or []),
            sfx_events=list(data.get("sfx_events") or []),
            whisper_words=list(data.get("whisper_words") or []),
        )


def _repo_root() -> Path:
    return Path(__file__).resolve().parent


def sfx_library_root() -> Path:
    return Path.home() / ".videogen" / "sfx"


def sfx_catalog_path(root: Optional[Path] = None) -> Path:
    return Path(root or sfx_library_root()) / "catalog.json"


def catalog_template_path() -> Path:
    return _repo_root() / "sfx" / "catalog.template.json"


def cache_settings_key(settings: SmartEditingSettings) -> str:
    payload = {"smart_editing_version": SMART_EDITING_VERSION, **asdict(settings)}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:16]


def _audio_fingerprint(audio_path: Path | str) -> str:
    p = Path(audio_path)
    try:
        stat = p.stat()
    except OSError:
        return hashlib.sha256(str(p).encode()).hexdigest()[:16]
    raw = f"{p.resolve()}:{stat.st_mtime_ns}:{stat.st_size}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def cache_file(state_dir: Path) -> Path:
    return Path(state_dir) / "smart_editing.json"


def load_cache(state_dir: Path) -> dict:
    path = cache_file(state_dir)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def save_cache(state_dir: Path, payload: dict) -> None:
    state_dir = Path(state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    payload = dict(payload)
    payload["smart_editing_version"] = SMART_EDITING_VERSION
    cache_file(state_dir).write_text(json.dumps(payload, indent=2), encoding="utf-8")


@dataclass(frozen=True)
class SfxEntry:
    id: str
    file: str
    category: str
    tags: Tuple[str, ...]
    intensity: str
    duration: float
    source: str = ""
    license: str = ""
    commercial_use: bool = True
    attribution_required: bool = False

    @classmethod
    def from_dict(cls, data: dict) -> Optional["SfxEntry"]:
        if not isinstance(data, dict):
            return None
        file_path = str(data.get("file") or "").strip()
        category = str(data.get("category") or "").strip().lower()
        entry_id = str(data.get("id") or "").strip() or file_path
        if not file_path or not category:
            return None
        raw_tags = data.get("tags") or []
        tags = tuple(str(t).lower() for t in raw_tags if str(t).strip())
        try:
            duration = float(data.get("duration") or 0.4)
        except (TypeError, ValueError):
            duration = 0.4
        return cls(
            id=entry_id,
            file=file_path,
            category=category,
            tags=tags,
            intensity=str(data.get("intensity") or "medium").lower(),
            duration=max(0.05, duration),
            source=str(data.get("source") or ""),
            license=str(data.get("license") or ""),
            commercial_use=bool(data.get("commercial_use", True)),
            attribution_required=bool(data.get("attribution_required", False)),
        )

    def resolved_path(self, root: Path) -> Path:
        return (Path(root) / self.file).resolve()


@dataclass(frozen=True)
class SfxRequest:
    event_type: str
    category: str
    tags: Tuple[str, ...] = ()
    intensity: str = "medium"
    max_duration: Optional[float] = None


class SfxCatalog:
    def __init__(self, root: Path, entries: Sequence[SfxEntry]):
        self.root = Path(root)
        self.entries = list(entries)
        self._by_category: Dict[str, List[SfxEntry]] = {}
        for entry in self.entries:
            self._by_category.setdefault(entry.category, []).append(entry)

    @classmethod
    def load(cls, root: Optional[Path] = None, catalog_path: Optional[Path] = None) -> "SfxCatalog":
        lib_root = Path(root or sfx_library_root())
        path = Path(catalog_path) if catalog_path else sfx_catalog_path(lib_root)
        if not path.is_file():
            return cls(lib_root, [])
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return cls(lib_root, [])
        items = data.get("sfx") if isinstance(data, dict) else data
        if not isinstance(items, list):
            return cls(lib_root, [])
        entries: List[SfxEntry] = []
        for raw in items:
            entry = SfxEntry.from_dict(raw)
            if entry is not None:
                entries.append(entry)
        return cls(lib_root, entries)

    def match(self, request: SfxRequest) -> Optional[SfxEntry]:
        pool = list(self._by_category.get(request.category.lower(), []))
        if not pool:
            return None
        req_tags = {t.lower() for t in request.tags if t}
        req_intensity = (request.intensity or "medium").lower()
        max_duration = request.max_duration

        def score(entry: SfxEntry) -> Tuple[int, int, int, float]:
            if max_duration is not None and entry.duration > max_duration + 0.05:
                return (-999, 0, 0, entry.duration)
            if not entry.resolved_path(self.root).is_file():
                return (-998, 0, 0, entry.duration)
            tag_hits = len(req_tags.intersection(set(entry.tags))) if req_tags else 0
            intensity_delta = abs(_intensity_rank(entry.intensity) - _intensity_rank(req_intensity))
            duration_penalty = abs(entry.duration - (max_duration or entry.duration))
            return (tag_hits, -intensity_delta, -duration_penalty, entry.duration)

        ranked = sorted(pool, key=score, reverse=True)
        best = ranked[0]
        if score(best)[0] <= -998:
            return None
        return best

    def __len__(self) -> int:
        return len(self.entries)


_catalog_cache: Optional[SfxCatalog] = None
_catalog_cache_key: Tuple[str, float] = ("", 0.0)


def _intensity_rank(value: str) -> int:
    return {"low": 0, "medium": 1, "high": 2}.get(str(value or "").lower(), 1)


def get_sfx_catalog(*, root: Optional[Path] = None, force_reload: bool = False) -> SfxCatalog:
    global _catalog_cache, _catalog_cache_key
    lib_root = Path(root or sfx_library_root())
    catalog = sfx_catalog_path(lib_root)
    try:
        mtime = catalog.stat().st_mtime if catalog.is_file() else 0.0
    except OSError:
        mtime = 0.0
    key = (str(lib_root.resolve()), mtime)
    if not force_reload and _catalog_cache is not None and _catalog_cache_key == key:
        return _catalog_cache
    _catalog_cache = SfxCatalog.load(lib_root, catalog)
    _catalog_cache_key = key
    return _catalog_cache


def reset_sfx_catalog_cache() -> None:
    global _catalog_cache, _catalog_cache_key
    _catalog_cache = None
    _catalog_cache_key = ("", 0.0)


def load_sfx_catalog(path: Optional[Path] = None) -> List[dict]:
    """Backward-compatible raw catalog loader (tests / legacy callers)."""
    if path is not None:
        catalog = SfxCatalog.load(root=Path(path).parent, catalog_path=Path(path))
    else:
        catalog = get_sfx_catalog()
    return [
        {
            "id": e.id,
            "file": e.file,
            "category": e.category,
            "tags": list(e.tags),
            "intensity": e.intensity,
            "duration": e.duration,
            "source": e.source,
            "license": e.license,
            "commercial_use": e.commercial_use,
            "attribution_required": e.attribution_required,
        }
        for e in catalog.entries
    ]


def _intensity_scale(intensity: str) -> float:
    return {"low": 0.35, "medium": 0.65, "high": 0.85}.get(intensity, 0.65)


def _max_text_effects(duration: float, intensity: str) -> int:
    if duration < 2.0:
        return 0
    rules = {"low": (4.0, 1), "medium": (3.0, 2), "high": (2.0, 3)}
    min_dur, cap = rules.get(intensity, (3.0, 2))
    if duration < min_dur:
        return 0
    return cap


def _find_emphasis_phrases(text: str) -> List[str]:
    text = (text or "").strip()
    if not text:
        return []
    phrases: List[str] = []
    phrases.extend(re.findall(r'"([^"]{2,})"', text))
    phrases.extend(re.findall(r"'([^']{2,})'", text))
    for match in re.finditer(r"\b[A-Z]{2,}[A-Z0-9'\-]*\b", text):
        phrases.append(match.group())
    for match in re.finditer(r"[\$€£]?\d[\d,\.]*%?", text):
        token = match.group().strip()
        if len(token) >= 2:
            phrases.append(token)
    # Distinctive single words from the narration (semantic emphasis, no extra LLM call).
    for word in split_words(text):
        if is_distinctive(word):
            phrases.append(word)
    deduped: List[str] = []
    seen = set()
    for p in phrases:
        key = p.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(p)
    return deduped


def _assign_effect(phrase: str, index: int, mode: str) -> str:
    if mode == "automatic":
        return TEXT_EFFECT_PRESETS[index % len(TEXT_EFFECT_PRESETS)]
    upper = phrase.upper()
    if phrase.isupper() and len(phrase) >= 3:
        return "punch"
    if any(ch in phrase for ch in "$€£%"):
        return "impact"
    if len(phrase.split()) >= 3:
        return "word_reveal"
    if len(phrase) >= 10:
        return "highlight"
    return TEXT_EFFECT_PRESETS[index % len(TEXT_EFFECT_PRESETS)]


def _align_phrase_in_window(
    phrase: str,
    whisper_words: Sequence[Tuple[str, float, float]],
    window_start: float,
    window_end: float,
) -> Optional[Tuple[float, float]]:
    tokens = split_words(phrase)
    if not tokens:
        return None
    in_window = [
        (w, s, e)
        for w, s, e in whisper_words
        if s >= window_start - 0.05 and e <= window_end + 0.25
    ]
    if not in_window:
        return None
    local_cursor = 0
    hits: List[int] = []
    for target in tokens:
        idx = None
        for j in range(local_cursor, len(in_window)):
            if words_match(in_window[j][0], target):
                idx = j
                break
        if idx is None:
            return None
        hits.append(idx)
        local_cursor = idx + 1
    start = in_window[hits[0]][1]
    end = in_window[hits[-1]][2]
    return start, max(end, start + 0.12)


def plan_text_effects(
    rows: Sequence[dict],
    aligned_rows: Sequence[dict],
    whisper_words: Sequence[Tuple[str, float, float]],
    settings: SmartEditingSettings,
) -> List[dict]:
    if not settings.text_effects:
        return []
    effects: List[dict] = []
    aligned_by_scene = {str(r["scene_number"]): r for r in aligned_rows}
    scale = _intensity_scale(settings.intensity)
    auto_idx = 0
    for row in rows:
        scene = str(row.get("scene_number", ""))
        aligned = aligned_by_scene.get(scene)
        if aligned is None:
            continue
        scene_start = float(aligned["start_time"])
        scene_end = float(aligned["end_time"])
        duration = max(0.0, scene_end - scene_start)
        budget = _max_text_effects(duration, settings.intensity)
        if budget <= 0:
            continue
        phrases = _find_emphasis_phrases(str(row.get("script_segment") or ""))
        added = 0
        for phrase in phrases:
            if added >= budget:
                break
            timing = _align_phrase_in_window(phrase, whisper_words, scene_start, scene_end)
            if timing is None:
                continue
            start, end = timing
            effect = _assign_effect(phrase, auto_idx, settings.mode)
            auto_idx += 1
            effects.append(
                {
                    "scene_number": scene,
                    "text": phrase,
                    "start": round(start, 3),
                    "end": round(end, 3),
                    "effect": effect,
                    "intensity": round(scale, 2),
                }
            )
            added += 1
    return effects


def _sfx_request_for_text_effect(effect: str, settings: SmartEditingSettings) -> SfxRequest:
    effect = str(effect or "").lower()
    intensity = settings.intensity
    mapping = {
        "punch": SfxRequest("text_emphasis", "impact", ("punch", "emphasis"), intensity, 0.55),
        "impact": SfxRequest("text_emphasis", "cinematic", ("hit", "emphasis"), intensity, 0.65),
        "pop": SfxRequest("text_pop", "text", ("text_pop", "pop"), intensity, 0.35),
        "rise": SfxRequest("text_rise", "riser", ("rising", "tension"), intensity, 0.9),
        "fade": SfxRequest("text_fade", "whoosh", ("soft", "movement"), intensity, 0.55),
        "highlight": SfxRequest("text_highlight", "ui", ("click", "select", "emphasis"), intensity, 0.3),
        "scale": SfxRequest("text_scale", "whoosh", ("sweep", "movement"), intensity, 0.5),
        "word_reveal": SfxRequest("text_reveal", "text", ("text_reveal", "reveal", "appear"), intensity, 0.75),
    }
    return mapping.get(
        effect,
        SfxRequest("text_emphasis", "ui", ("pop", "emphasis"), intensity, 0.35),
    )


def _sfx_request_for_transition(settings: SmartEditingSettings) -> SfxRequest:
    tag = {"low": "soft", "medium": "fast", "high": "cinematic"}.get(settings.intensity, "fast")
    return SfxRequest(
        "scene_transition",
        "transition",
        (tag, "movement", "sweep"),
        settings.intensity,
        0.75,
    )


def _pick_sfx_entry(catalog: SfxCatalog, request: SfxRequest) -> Optional[SfxEntry]:
    try:
        return catalog.match(request)
    except Exception:
        return None


def _entry_to_event(
    entry: SfxEntry,
    request: SfxRequest,
    *,
    start: float,
    volume: float,
    scene_number: Optional[str] = None,
) -> dict:
    return {
        "type": request.event_type,
        "category": entry.category,
        "sfx_id": entry.id,
        "start": round(start, 3),
        "duration": round(entry.duration, 3),
        "volume": round(volume, 3),
        "file": entry.file,
        "source": entry.source,
        "license": entry.license,
        "commercial_use": entry.commercial_use,
        "attribution_required": entry.attribution_required,
        "scene_number": scene_number,
    }


def plan_sfx_events(
    aligned_rows: Sequence[dict],
    text_effects: Sequence[dict],
    settings: SmartEditingSettings,
    catalog: Optional[SfxCatalog] = None,
) -> List[dict]:
    if not settings.sound_effects:
        return []
    cat = catalog if catalog is not None else get_sfx_catalog()
    if not cat.entries:
        return []
    events: List[dict] = []
    # Keep narration dominant, but previous medium≈0.14 was inaudible in real mixes.
    base_vol = {"low": 0.28, "medium": 0.40, "high": 0.52}.get(settings.intensity, 0.40)

    for fx in text_effects:
        request = _sfx_request_for_text_effect(str(fx.get("effect") or ""), settings)
        entry = _pick_sfx_entry(cat, request)
        if entry is None:
            continue
        # Visual intensity is already baked into which effects fire; use a mild weight only.
        fx_w = float(fx.get("intensity") or 0.65)
        vol = min(0.55, base_vol * (0.9 + 0.25 * fx_w))
        events.append(
            _entry_to_event(
                entry,
                request,
                start=float(fx["start"]),
                volume=round(vol, 3),
                scene_number=str(fx.get("scene_number") or ""),
            )
        )

    transition_request = _sfx_request_for_transition(settings)
    for i, row in enumerate(aligned_rows):
        if i == 0:
            continue
        start = float(row["start_time"])
        prev_end = float(aligned_rows[i - 1]["end_time"])
        gap = start - prev_end
        duration = float(row["end_time"]) - start
        if duration < 2.5 or gap < 0.05:
            continue
        entry = _pick_sfx_entry(cat, transition_request)
        if entry is None:
            continue
        events.append(
            _entry_to_event(
                entry,
                transition_request,
                start=max(0.0, start - 0.05),
                volume=round(min(0.55, base_vol * 0.9), 3),
                scene_number=str(row.get("scene_number") or ""),
            )
        )
    return events


def build_plan(
    rows: Sequence[dict],
    aligned_rows: Sequence[dict],
    whisper_words: Sequence[Tuple[str, float, float]],
    settings: SmartEditingSettings,
    *,
    state_dir: Optional[Path] = None,
    audio_path: Optional[Path | str] = None,
) -> SmartEditingPlan:
    if not settings.enabled():
        return SmartEditingPlan()

    audio_key = _audio_fingerprint(audio_path) if audio_path else ""
    settings_key = cache_settings_key(settings)
    cached: dict = {}
    if state_dir is not None:
        cached = load_cache(state_dir)
        if cached.get("smart_editing_version") not in (None, SMART_EDITING_VERSION):
            cached = {}
        if (
            cached.get("audio_key") == audio_key
            and cached.get("settings_key") == settings_key
            and cached.get("plan")
        ):
            plan = SmartEditingPlan.from_dict(cached["plan"])
            if plan.whisper_words or not settings.text_effects:
                return plan

    whisper_list = [[w, s, e] for w, s, e in whisper_words]
    text_effects = plan_text_effects(rows, aligned_rows, whisper_words, settings)
    sfx_events = plan_sfx_events(aligned_rows, text_effects, settings) if settings.sound_effects else []
    plan = SmartEditingPlan(
        text_effects=text_effects,
        sfx_events=sfx_events,
        whisper_words=whisper_list,
    )

    if state_dir is not None and audio_key:
        save_cache(
            state_dir,
            {
                "audio_key": audio_key,
                "settings_key": settings_key,
                "plan": plan.to_dict(),
            },
        )
    return plan


def get_cached_whisper_words(state_dir: Path, audio_path: Path | str) -> Optional[List[list]]:
    cached = load_cache(state_dir)
    if cached.get("audio_key") != _audio_fingerprint(audio_path):
        return None
    plan = cached.get("plan") or {}
    words = plan.get("whisper_words")
    if not words:
        return None
    return list(words)


def scene_text_effects(
    plan: SmartEditingPlan,
    scene_number: str,
    scene_display_start: float,
) -> List[dict]:
    out: List[dict] = []
    for fx in plan.text_effects:
        if str(fx.get("scene_number")) != str(scene_number):
            continue
        local = dict(fx)
        local["local_start"] = max(0.0, float(fx["start"]) - scene_display_start)
        local["local_end"] = max(local["local_start"] + 0.08, float(fx["end"]) - scene_display_start)
        out.append(local)
    return out


def _escape_drawtext(text: str) -> str:
    escaped = (text or "").replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    return escaped.replace("%", "\\%")


def _escape_filter_expr(expr: str) -> str:
    """Escape commas/semicolons so ffmpeg does not treat them as filter separators."""
    return (expr or "").replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;")


_DRAWTEXT_AVAILABLE: Optional[bool] = None


def ffmpeg_supports_drawtext() -> bool:
    """Homebrew ffmpeg is often built without libfreetype — drawtext is then missing."""
    global _DRAWTEXT_AVAILABLE
    if _DRAWTEXT_AVAILABLE is not None:
        return _DRAWTEXT_AVAILABLE
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        _DRAWTEXT_AVAILABLE = False
        return False
    try:
        proc = subprocess.run(
            [ffmpeg, "-hide_banner", "-filters"],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
        blob = (proc.stdout or "") + (proc.stderr or "")
        _DRAWTEXT_AVAILABLE = "drawtext" in blob
    except (OSError, subprocess.TimeoutExpired):
        _DRAWTEXT_AVAILABLE = False
    return _DRAWTEXT_AVAILABLE


def drawtext_filters(effects: Sequence[dict], width: int, height: int) -> str:
    """Render Smart Text via the typography theme layer (drawtext backend)."""
    if not effects:
        return ""
    if not ffmpeg_supports_drawtext():
        return ""
    from typography import build_drawtext_filters

    return build_drawtext_filters(effects, width, height)


def _resolve_sfx_file(entry: dict, root: Optional[Path] = None) -> Optional[Path]:
    raw = str(entry.get("file") or "").strip()
    if not raw:
        return None
    base = Path(root or sfx_library_root())
    path = (base / raw).resolve()
    if path.is_file():
        return path
    return None


def mix_sfx_with_narration(
    narration_path: Path | str,
    sfx_events: Sequence[dict],
    output_path: Path | str,
    *,
    sfx_root: Optional[Path] = None,
) -> Path:
    narration_path = Path(narration_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    usable: List[tuple[Path, dict]] = []
    root = Path(sfx_root or sfx_library_root())
    for ev in sfx_events:
        path = _resolve_sfx_file(ev, root)
        if path is not None:
            usable.append((path, ev))
    if not usable:
        shutil.copy2(narration_path, output_path)
        return output_path

    cmd = ["ffmpeg", "-y", "-i", str(narration_path)]
    filter_parts: List[str] = []
    mix_inputs = ["[0:a]"]
    for i, (path, ev) in enumerate(usable, start=1):
        cmd.extend(["-i", str(path)])
        delay_ms = max(0, int(float(ev.get("start") or 0.0) * 1000))
        vol = min(0.55, float(ev.get("volume") or 0.32))
        dur = float(ev.get("duration") or 0.4)
        label = f"s{i}"
        filter_parts.append(
            f"[{i}:a]atrim=0:{dur:.3f},asetpts=PTS-STARTPTS,"
            f"volume={vol:.4f},adelay={delay_ms}|{delay_ms}[{label}]"
        )
        mix_inputs.append(f"[{label}]")

    n = len(mix_inputs)
    filter_parts.append(
        f"{''.join(mix_inputs)}amix=inputs={n}:duration=first:dropout_transition=0:normalize=0,"
        f"volume=0.92[aout]"
    )
    cmd.extend(["-filter_complex", ";".join(filter_parts), "-map", "[aout]", str(output_path)])
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not output_path.is_file():
        shutil.copy2(narration_path, output_path)
    return output_path


def write_test_sfx_library(root: Path, entries: Optional[Sequence[dict]] = None) -> Path:
    """Create a tiny offline SFX library for tests only — never called during generation."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    if entries is None:
        entries = [
            {
                "id": "whoosh_test",
                "file": "whoosh/whoosh_test.wav",
                "category": "whoosh",
                "tags": ["soft", "movement", "sweep"],
                "intensity": "medium",
                "duration": 0.4,
                "source": "test",
                "license": "test",
                "commercial_use": True,
                "attribution_required": False,
            },
            {
                "id": "impact_test",
                "file": "impact/impact_test.wav",
                "category": "impact",
                "tags": ["punch", "emphasis"],
                "intensity": "high",
                "duration": 0.3,
                "source": "test",
                "license": "test",
                "commercial_use": True,
                "attribution_required": False,
            },
            {
                "id": "text_reveal_test",
                "file": "text/text_reveal_test.wav",
                "category": "text",
                "tags": ["text_reveal", "reveal"],
                "intensity": "medium",
                "duration": 0.5,
                "source": "test",
                "license": "test",
                "commercial_use": True,
                "attribution_required": False,
            },
            {
                "id": "transition_test",
                "file": "transition/transition_test.wav",
                "category": "transition",
                "tags": ["soft", "fast", "movement"],
                "intensity": "medium",
                "duration": 0.35,
                "source": "test",
                "license": "test",
                "commercial_use": True,
                "attribution_required": False,
            },
            {
                "id": "ui_pop_test",
                "file": "ui/ui_pop_test.wav",
                "category": "ui",
                "tags": ["pop", "click"],
                "intensity": "low",
                "duration": 0.2,
                "source": "test",
                "license": "test",
                "commercial_use": True,
                "attribution_required": False,
            },
        ]
    for raw in entries:
        rel = str(raw.get("file") or "")
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.is_file():
            sr = 24000
            dur = float(raw.get("duration") or 0.2)
            frames = max(1, int(dur * sr))
            with wave.open(str(path), "w") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sr)
                wf.writeframes(b"\x00\x00" * frames)
    catalog_path = root / "catalog.json"
    catalog_path.write_text(json.dumps({"version": 1, "sfx": list(entries)}, indent=2), encoding="utf-8")
    reset_sfx_catalog_cache()
    return catalog_path
