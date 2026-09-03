"""Optional Smart Text Effects + SFX layer. Fast, cached, skipped when disabled."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import wave
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

# Reuse alignment tokenization from the existing renderer pipeline.
from video_generator import _scene_display_timeline, is_distinctive, split_words, words_match
from providers import hidden_subprocess
from sfx.ambience_profiles import smart_editing_profile_tags
from sfx.audio_probe import probe_audio

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
SMART_EDITING_VERSION = 13

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
    "visual_transitions": True,
    "scene_ambience": True,
    "intensity": "medium",
    "text_effects_intensity": "medium",
    "sound_effects_intensity": "medium",
    "visual_transitions_intensity": "medium",
    "scene_ambience_intensity": "medium",
    # None = follow scene_ambience_intensity. A float is an explicit operator
    # override of the ambience bed level (absolute, not a multiplier).
    "scene_ambience_volume": None,
    "mode": "smart",
}

# Ambience bed level per intensity step, and the reference the runtime clamps
# are calibrated against. An explicit operator volume rescales those clamps by
# `volume / _AMBIENCE_REFERENCE_VOL`, so the level the operator picks is the
# level that survives the per-scene envelope instead of being capped at 0.42.
_AMBIENCE_INTENSITY_VOLUME: Dict[str, float] = {"low": 0.22, "medium": 0.30, "high": 0.38}
_AMBIENCE_REFERENCE_VOL = 0.30
AMBIENCE_VOLUME_MIN = 0.0
AMBIENCE_VOLUME_MAX = 1.0


def normalize_ambience_volume(value: Any) -> Optional[float]:
    """Coerce an operator ambience volume to [0.0, 1.0]; None means 'auto'."""
    if value is None or value == "":
        return None
    try:
        vol = float(value)
    except (TypeError, ValueError):
        return None
    if vol != vol:  # NaN
        return None
    return round(max(AMBIENCE_VOLUME_MIN, min(AMBIENCE_VOLUME_MAX, vol)), 3)

# Ambience profiles → catalog tag hints (SfxRequest category is always "ambience").
_AMBIENCE_PROFILES: Dict[str, Tuple[str, ...]] = {
    **smart_editing_profile_tags(),
    "none": (),
}

# Rotate transition SFX so scene changes do not all share one mode/preset.
_TRANSITION_SFX_VARIANTS: Tuple[Tuple[str, Tuple[str, ...], float], ...] = (
    ("transition", ("soft", "transition", "movement"), 0.85),
    ("whoosh", ("sweep", "movement", "fast"), 0.70),
    ("transition", ("fast", "sweep", "transition"), 0.75),
    ("whoosh", ("soft", "movement"), 0.65),
    ("riser", ("rising", "tension"), 0.90),
    ("cinematic", ("sweep", "transition"), 0.80),
    ("whoosh", ("whoosh", "short", "fast"), 0.55),
    ("impact", ("soft", "hit"), 0.35),
)

# Mid-scene accents when Text Effects are off (still under narration).
_BEAT_SFX_VARIANTS: Tuple[Tuple[str, Tuple[str, ...], float], ...] = (
    ("whoosh", ("soft", "movement"), 0.55),
    ("ui", ("click", "select"), 0.30),
    ("impact", ("soft", "emphasis"), 0.35),
    ("whoosh", ("sweep", "movement"), 0.60),
    ("cinematic", ("hit", "emphasis"), 0.45),
)


def _normalize_intensity(value: Any, fallback: str = "medium") -> str:
    level = str(value or "").strip().lower()
    if level in INTENSITY_LEVELS:
        return level
    fb = str(fallback or "medium").strip().lower()
    return fb if fb in INTENSITY_LEVELS else "medium"


@dataclass
class SmartEditingSettings:
    text_effects: bool = True
    sound_effects: bool = True
    visual_transitions: bool = True
    scene_ambience: bool = True
    # Legacy global intensity — used when a per-feature value is unset.
    intensity: str = "medium"
    text_effects_intensity: Optional[str] = None
    sound_effects_intensity: Optional[str] = None
    visual_transitions_intensity: Optional[str] = None
    scene_ambience_intensity: Optional[str] = None
    # Explicit ambience level override; None follows scene_ambience_intensity.
    scene_ambience_volume: Optional[float] = None
    mode: str = "smart"

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "SmartEditingSettings":
        raw = data or {}
        intensity = _normalize_intensity(raw.get("intensity"), "medium")
        mode = str(raw.get("mode") or "smart").lower()
        if mode not in MODES:
            mode = "smart"
        return cls(
            text_effects=bool(raw.get("text_effects", True)),
            sound_effects=bool(raw.get("sound_effects", True)),
            visual_transitions=bool(raw.get("visual_transitions", True)),
            scene_ambience=bool(raw.get("scene_ambience", True)),
            intensity=intensity,
            text_effects_intensity=_normalize_intensity(
                raw.get("text_effects_intensity"), intensity,
            ),
            sound_effects_intensity=_normalize_intensity(
                raw.get("sound_effects_intensity"), intensity,
            ),
            visual_transitions_intensity=_normalize_intensity(
                raw.get("visual_transitions_intensity"), intensity,
            ),
            scene_ambience_intensity=_normalize_intensity(
                raw.get("scene_ambience_intensity"), intensity,
            ),
            scene_ambience_volume=normalize_ambience_volume(
                raw.get("scene_ambience_volume"),
            ),
            mode=mode,
        )

    def enabled(self) -> bool:
        return (
            self.text_effects
            or self.sound_effects
            or self.visual_transitions
            or self.scene_ambience
        )

    def text_intensity(self) -> str:
        return _normalize_intensity(self.text_effects_intensity, self.intensity)

    def sfx_intensity(self) -> str:
        return _normalize_intensity(self.sound_effects_intensity, self.intensity)

    def transitions_intensity(self) -> str:
        return _normalize_intensity(self.visual_transitions_intensity, self.intensity)

    def ambience_intensity(self) -> str:
        return _normalize_intensity(self.scene_ambience_intensity, self.intensity)

    def ambience_volume(self) -> float:
        """Ambience bed level: the operator override, else the intensity step."""
        override = normalize_ambience_volume(self.scene_ambience_volume)
        if override is not None:
            return override
        return _AMBIENCE_INTENSITY_VOLUME.get(
            self.ambience_intensity(), _AMBIENCE_REFERENCE_VOL,
        )

    def ambience_volume_is_auto(self) -> bool:
        return normalize_ambience_volume(self.scene_ambience_volume) is None

    def to_settings_dict(self) -> Dict[str, Any]:
        return {
            "text_effects": self.text_effects,
            "sound_effects": self.sound_effects,
            "visual_transitions": self.visual_transitions,
            "scene_ambience": self.scene_ambience,
            "intensity": _normalize_intensity(self.intensity),
            "text_effects_intensity": self.text_intensity(),
            "sound_effects_intensity": self.sfx_intensity(),
            "visual_transitions_intensity": self.transitions_intensity(),
            "scene_ambience_intensity": self.ambience_intensity(),
            "scene_ambience_volume": normalize_ambience_volume(self.scene_ambience_volume),
            "mode": self.mode if self.mode in MODES else "smart",
        }

    def fingerprint(self) -> str:
        payload = json.dumps(self.to_settings_dict(), sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


@dataclass
class SmartEditingPlan:
    text_effects: List[dict] = field(default_factory=list)
    sfx_events: List[dict] = field(default_factory=list)
    whisper_words: List[list] = field(default_factory=list)
    # Boundaries INTO these scenes get a visual/SFX transition (AI or heuristic).
    scene_transitions: List[dict] = field(default_factory=list)
    # Continuous low beds under each scene (AI/heuristic profile → ambience catalog).
    scene_ambience: List[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "text_effects": self.text_effects,
            "sfx_events": self.sfx_events,
            "whisper_words": self.whisper_words,
            "scene_transitions": self.scene_transitions,
            "scene_ambience": self.scene_ambience,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SmartEditingPlan":
        return cls(
            text_effects=list(data.get("text_effects") or []),
            sfx_events=list(data.get("sfx_events") or []),
            whisper_words=list(data.get("whisper_words") or []),
            scene_transitions=list(data.get("scene_transitions") or []),
            scene_ambience=list(data.get("scene_ambience") or []),
        )

    def transition_style_map(self) -> Dict[str, str]:
        out: Dict[str, str] = {}
        for item in self.scene_transitions:
            key = str(item.get("scene_number") or "").strip()
            style = str(item.get("style") or "fade").strip().lower()
            if key:
                out[key] = style
        return out

    def transition_sfx_scenes(self) -> set:
        out = set()
        for item in self.scene_transitions:
            if item.get("sfx", True) is False:
                continue
            key = str(item.get("scene_number") or "").strip()
            if key:
                out.add(key)
        return out


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

    def match(
        self,
        request: SfxRequest,
        *,
        avoid_ids: Optional[Sequence[str]] = None,
    ) -> Optional[SfxEntry]:
        pool = list(self._by_category.get(request.category.lower(), []))
        if not pool:
            return None
        req_tags = {t.lower() for t in request.tags if t}
        req_intensity = (request.intensity or "medium").lower()
        max_duration = request.max_duration
        avoided = {str(x) for x in (avoid_ids or []) if x}

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
        fallback: Optional[SfxEntry] = None
        for entry in ranked:
            if score(entry)[0] <= -998:
                continue
            if fallback is None:
                fallback = entry
            if entry.id in avoided:
                continue
            return entry
        return fallback

    def match_any(
        self,
        requests: Sequence[SfxRequest],
        *,
        avoid_ids: Optional[Sequence[str]] = None,
    ) -> Optional[Tuple[SfxEntry, SfxRequest]]:
        """Try each request in order until a catalog hit is found."""
        for request in requests:
            entry = self.match(request, avoid_ids=avoid_ids)
            if entry is not None:
                return entry, request
        return None

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
    scale = _intensity_scale(settings.text_intensity())
    auto_idx = 0
    for row in rows:
        scene = str(row.get("scene_number", ""))
        aligned = aligned_by_scene.get(scene)
        if aligned is None:
            continue
        scene_start = float(aligned["start_time"])
        scene_end = float(aligned["end_time"])
        duration = max(0.0, scene_end - scene_start)
        budget = _max_text_effects(duration, settings.text_intensity())
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
    intensity = settings.sfx_intensity()
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


def _sfx_request_for_transition(settings: SmartEditingSettings, index: int = 0) -> SfxRequest:
    category, tags, max_dur = _TRANSITION_SFX_VARIANTS[index % len(_TRANSITION_SFX_VARIANTS)]
    return SfxRequest(
        "scene_transition",
        category,
        tags,
        settings.sfx_intensity(),
        max_dur,
    )


def _transition_sfx_fallback_chain(settings: SmartEditingSettings, index: int) -> List[SfxRequest]:
    """Primary variant plus a couple of fallbacks so sparse catalogs still hit."""
    primary = _sfx_request_for_transition(settings, index)
    intensity = settings.sfx_intensity()
    fallbacks = [
        SfxRequest("scene_transition", "transition", ("soft", "movement"), intensity, 0.9),
        SfxRequest("scene_transition", "whoosh", ("sweep", "movement"), intensity, 0.75),
        SfxRequest("scene_transition", "whoosh", (), intensity, 0.8),
    ]
    out = [primary]
    for req in fallbacks:
        if (req.category, req.tags) != (primary.category, primary.tags):
            out.append(req)
    return out


def _beat_sfx_request(settings: SmartEditingSettings, index: int) -> SfxRequest:
    category, tags, max_dur = _BEAT_SFX_VARIANTS[index % len(_BEAT_SFX_VARIANTS)]
    return SfxRequest("scene_beat", category, tags, settings.sfx_intensity(), max_dur)


def _pick_sfx_entry(
    catalog: SfxCatalog,
    request: SfxRequest,
    *,
    avoid_ids: Optional[Sequence[str]] = None,
) -> Optional[SfxEntry]:
    try:
        return catalog.match(request, avoid_ids=avoid_ids)
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


_TRANSITION_STYLES = ("fade", "dissolve", "flash", "soft", "cut")
_TRANSITION_CUE_RE = re.compile(
    r"\b(meanwhile|however|but then|suddenly|instead|later|next|"
    r"far beyond|on the other hand|section|chapter|years later|"
    r"back (?:in|to)|now\b|then\b)\b",
    re.I,
)


def _transition_budget(n_boundaries: int, intensity: str) -> int:
    if n_boundaries <= 0:
        return 0
    frac = {"low": 0.18, "medium": 0.32, "high": 0.48}.get(intensity, 0.32)
    return max(1, min(n_boundaries, int(round(n_boundaries * frac))))


def _beat_budget(n_scenes: int, intensity: str, *, text_effects_on: bool) -> int:
    if n_scenes <= 0:
        return 0
    frac = {"low": 0.10, "medium": 0.18, "high": 0.28}.get(intensity, 0.18)
    if text_effects_on:
        frac *= 0.45
    return max(0, min(n_scenes, int(round(n_scenes * frac))))


def _token_set(text: str) -> set:
    return {t for t in split_words(text or "") if is_distinctive(t)}


def _jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def _heuristic_scene_transitions(
    rows: Sequence[dict],
    aligned_rows: Sequence[dict],
    settings: SmartEditingSettings,
) -> List[dict]:
    """Editorial fallback when Gemini is unavailable — sparse, not every scene."""
    if len(aligned_rows) < 2:
        return []
    by_num = {str(r.get("scene_number")): r for r in rows}
    scored: List[Tuple[float, int, str]] = []
    for i in range(1, len(aligned_rows)):
        cur = aligned_rows[i]
        prev = aligned_rows[i - 1]
        sn = str(cur.get("scene_number") or "")
        cur_row = by_num.get(sn) or {}
        prev_sn = str(prev.get("scene_number") or "")
        prev_row = by_num.get(prev_sn) or {}
        cur_text = str(cur_row.get("script_segment") or cur.get("script_segment") or "")
        prev_text = str(prev_row.get("script_segment") or prev.get("script_segment") or "")
        overlap = _jaccard(_token_set(prev_text), _token_set(cur_text))
        score = (1.0 - overlap) * 3.0
        if _TRANSITION_CUE_RE.search(cur_text):
            score += 2.0
        cur_dur = max(0.1, float(cur["end_time"]) - float(cur["start_time"]))
        prev_dur = max(0.1, float(prev["end_time"]) - float(prev["start_time"]))
        if abs(cur_dur - prev_dur) / max(cur_dur, prev_dur) > 0.55:
            score += 0.6
        # Prefer not clustering at the very start
        if i == 1:
            score *= 0.75
        scored.append((score, i, sn))

    scored.sort(key=lambda t: (-t[0], t[1]))
    budget = _transition_budget(len(aligned_rows) - 1, settings.transitions_intensity())
    picked_idx: List[int] = []
    picked: List[dict] = []
    styles = ("dissolve", "fade", "soft", "flash", "fade")
    for score, i, sn in scored:
        if len(picked) >= budget:
            break
        if score < 0.85 and len(picked) >= max(1, budget // 2):
            continue
        if any(abs(i - j) == 1 for j in picked_idx):
            continue
        style = styles[len(picked) % len(styles)]
        picked_idx.append(i)
        picked.append({"scene_number": sn, "style": style, "sfx": True, "source": "heuristic"})
    return picked


def _extract_json_object(text: str) -> dict:
    raw = (text or "").strip()
    if not raw:
        return {}
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{[\s\S]*\}", raw)
    if not match:
        return {}
    try:
        data = json.loads(match.group(0))
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _parse_ai_transitions(
    payload: dict,
    aligned_rows: Sequence[dict],
    settings: SmartEditingSettings,
) -> List[dict]:
    items = payload.get("transitions")
    if not isinstance(items, list):
        return []
    valid_scenes = {str(r.get("scene_number")) for r in aligned_rows}
    # First scene usually shouldn't open with a "scene change" transition.
    if aligned_rows:
        valid_scenes.discard(str(aligned_rows[0].get("scene_number")))
    budget = _transition_budget(max(0, len(aligned_rows) - 1), settings.transitions_intensity())
    out: List[dict] = []
    seen = set()
    for raw in items:
        if not isinstance(raw, dict):
            continue
        sn = str(raw.get("into_scene") or raw.get("scene_number") or "").strip()
        if not sn or sn not in valid_scenes or sn in seen:
            continue
        style = str(raw.get("style") or "fade").strip().lower().replace(" ", "_")
        if style not in _TRANSITION_STYLES:
            style = "fade"
        if style == "cut" and raw.get("sfx", True):
            # Hard cut with optional soft whoosh still allowed via sfx flag.
            pass
        out.append(
            {
                "scene_number": sn,
                "style": style,
                "sfx": bool(raw.get("sfx", True)),
                "source": "ai",
            }
        )
        seen.add(sn)
        if len(out) >= budget + 2:  # slight slack; trim below
            break
    # Prefer spaced selections if AI packed adjacent scenes.
    spaced: List[dict] = []
    idx_by_sn = {str(r.get("scene_number")): i for i, r in enumerate(aligned_rows)}
    used_i: List[int] = []
    for item in out:
        i = idx_by_sn.get(item["scene_number"], -1)
        if i < 0:
            continue
        if any(abs(i - j) == 1 for j in used_i) and len(spaced) >= max(1, budget // 2):
            continue
        spaced.append(item)
        used_i.append(i)
        if len(spaced) >= budget:
            break
    return spaced


_TRANSITION_SYSTEM = """You are an editor choosing where a narrated documentary needs a
scene transition (visual fade/dissolve/flash + optional whoosh SFX).

Rules:
- Most scene changes should be HARD CUTS with NO transition sound.
- Only mark a transition when the story clearly shifts: new location, new idea,
  section break, time jump, contrast, or emotional beat.
- Target about 15–30% of scene boundaries (fewer for calm narration).
- Never mark every scene. Prefer spaced-out moments, not adjacent scenes.
- Styles: fade, dissolve, soft, flash, cut (cut = visual hard cut; sfx may still be true for a soft whoosh).

Return ONLY JSON:
{"transitions":[{"into_scene":"<scene_number>","style":"dissolve","sfx":true}]}
into_scene = the scene being entered (not the previous one).
"""


def _ai_scene_transitions(
    rows: Sequence[dict],
    aligned_rows: Sequence[dict],
    settings: SmartEditingSettings,
    gemini_settings: Optional[Mapping[str, Any]] = None,
) -> Optional[List[dict]]:
    try:
        from visual_director.llm import GeminiLLM, LLMError, gemini_configured
    except Exception:
        return None
    if not gemini_configured(gemini_settings):
        return None
    lines = []
    by_num = {str(r.get("scene_number")): r for r in rows}
    for i, aligned in enumerate(aligned_rows):
        sn = str(aligned.get("scene_number") or "")
        row = by_num.get(sn) or {}
        text = str(row.get("script_segment") or aligned.get("script_segment") or "").strip()
        if len(text) > 160:
            text = text[:157] + "…"
        dur = max(0.0, float(aligned["end_time"]) - float(aligned["start_time"]))
        lines.append(f"{i + 1}. scene {sn} ({dur:.1f}s): {text}")
    budget = _transition_budget(max(0, len(aligned_rows) - 1), settings.transitions_intensity())
    user = (
        f"Intensity={settings.transitions_intensity()}. Pick up to {budget} transitions.\n"
        f"Scenes:\n" + "\n".join(lines)
    )
    try:
        llm = GeminiLLM(settings=gemini_settings, timeout=90.0)
        # Lighter thinking for a small editorial JSON pick.
        raw = llm.complete(_TRANSITION_SYSTEM, user)
        parsed = _parse_ai_transitions(_extract_json_object(raw), aligned_rows, settings)
        if not parsed and budget > 0:
            print("[SMART] Transition AI returned no usable picks; using heuristic.")
            return None
        return parsed
    except Exception as exc:
        print(f"[SMART] Transition AI unavailable ({exc}); using heuristic picks.")
        return None


def _editorial_transition_hints(editorial_plan: Any) -> List[dict]:
    """Pull explicit transition_in choices from the Editorial Plan."""
    scenes = getattr(editorial_plan, "scenes", None) or []
    out: List[dict] = []
    for scene in scenes:
        sn = str(getattr(scene, "scene_number", "") or "")
        style = getattr(scene, "transition_in", None)
        if not sn or not style or str(style).lower() == "cut":
            continue
        out.append(
            {
                "scene_number": sn,
                "style": str(style).lower(),
                "sfx": True,
                "source": "editorial",
            }
        )
    return out


def _merge_transition_picks(
    editorial: Sequence[dict],
    generated: Sequence[dict],
    *,
    budget: int,
) -> List[dict]:
    """Editorial hints win; fill remaining budget from AI/heuristic picks."""
    out: List[dict] = []
    seen: set[str] = set()
    for item in editorial:
        sn = str(item.get("scene_number") or "")
        if sn and sn not in seen:
            out.append(dict(item))
            seen.add(sn)
    for item in generated:
        if len(out) >= budget + len(editorial):
            break
        sn = str(item.get("scene_number") or "")
        if not sn or sn in seen:
            continue
        out.append(dict(item))
        seen.add(sn)
    return out


def plan_scene_transitions(
    rows: Sequence[dict],
    aligned_rows: Sequence[dict],
    settings: SmartEditingSettings,
    *,
    gemini_settings: Optional[Mapping[str, Any]] = None,
    editorial_plan: Any = None,
) -> List[dict]:
    """Choose sparse scene boundaries for visual + SFX transitions (AI preferred)."""
    if not (settings.sound_effects or settings.visual_transitions):
        return []
    if len(aligned_rows) < 2:
        return []
    editorial = _editorial_transition_hints(editorial_plan) if editorial_plan else []
    budget = _transition_budget(max(0, len(aligned_rows) - 1), settings.transitions_intensity())
    # When EditorialPlan already finalized transitions, those are authoritative —
    # do not independently inflate the set (Smart Editing becomes an adapter).
    if editorial and getattr(editorial_plan, "scenes", None):
        with_style = sum(
            1
            for s in editorial_plan.scenes
            if getattr(s, "transition_in", None) and str(s.transition_in) != "cut"
        )
        if with_style >= max(1, budget // 2):
            print(f"[SMART] Using {len(editorial)} authoritative editorial transition(s) for SFX.")
            return editorial
    ai = _ai_scene_transitions(rows, aligned_rows, settings, gemini_settings)
    if ai is not None:
        picks = _merge_transition_picks(editorial, ai, budget=budget)
        print(
            f"[SMART] AI selected {len(ai)} scene transition(s)"
            + (f"; {len(editorial)} editorial hint(s) merged." if editorial else ".")
        )
        return picks
    heuristic = _heuristic_scene_transitions(rows, aligned_rows, settings)
    picks = _merge_transition_picks(editorial, heuristic, budget=budget)
    print(
        f"[SMART] Heuristic selected {len(heuristic)} scene transition(s)"
        + (f"; {len(editorial)} editorial hint(s) merged." if editorial else ".")
    )
    return picks


_AMBIENCE_SYSTEM = """You pick a subtle background ambience profile for EACH scene in a narrated documentary.

Profiles (pick exactly one per scene):
- room: indoor, quiet room tone, hallway, library, house
- city: urban streets, downtown, distant city life
- crowd: people, public spaces, busy markets (not music)
- nature: forest, wind, meadow, wildlife, outdoor wilderness
- rain: gentle/heavy rain, storm, thunder, rain on window
- traffic: highway, distant road traffic, intersections
- water: ocean, shoreline, river, calm water environments
- fire: fireplace, campfire, subtle crackle
- transport: train station, subway, airport, public transit
- technology: office, lab, server room, subtle electronic hum
- atmospheric: dark, tense, mysterious environmental beds (no melody)
- none: only for very abstract or silent beats — use sparingly

Beds stay quiet under narration. Return ONLY JSON:
{"scenes":[{"scene_number":"1","profile":"city"},{"scene_number":"2","profile":"technology"}]}
"""


def _normalize_ambience_profile(raw: str) -> str:
    key = str(raw or "room").strip().lower().replace(" ", "_")
    if key in _AMBIENCE_PROFILES:
        return key
    aliases = {
        "urban": "city",
        "office": "room",
        "indoor": "room",
        "outdoor": "nature",
        "wind": "nature",
        "forest": "nature",
        "space": "nature",
        "tech": "technology",
        "sci": "technology",
        "silent": "none",
        "storm": "rain",
        "weather": "rain",
        "thunder": "rain",
        "ocean": "water",
        "beach": "water",
        "river": "water",
        "shore": "water",
        "highway": "traffic",
        "road": "traffic",
        "freeway": "traffic",
        "train": "transport",
        "subway": "transport",
        "metro": "transport",
        "airport": "transport",
        "station": "transport",
        "fireplace": "fire",
        "campfire": "fire",
        "dark": "atmospheric",
        "tension": "atmospheric",
        "mysterious": "atmospheric",
        "drone": "atmospheric",
    }
    return aliases.get(key, "room")


def _heuristic_ambience_profile(text: str, prompt: str = "") -> str:
    blob = f"{text} {prompt}".lower()
    if re.search(r"\b(rain|storm|thunder|drizzle|downpour|lightning)\b", blob):
        return "rain"
    if re.search(r"\b(fireplace|campfire|fire crackl|embers|bonfire)\b", blob):
        return "fire"
    if re.search(r"\b(ocean|shoreline|shore|waves|river|underwater|stream|beach)\b", blob):
        return "water"
    if re.search(r"\b(train|subway|metro|airport|platform|departure|transit)\b", blob):
        return "transport"
    if re.search(r"\b(highway|freeway|intersection|motorway|road traffic)\b", blob):
        return "traffic"
    if re.search(r"\b(dark|myster|tension|ominous|haunting|sinister|eerie)\b", blob):
        return "atmospheric"
    if re.search(r"\b(rocket|space|launch|engine|machine|digital|computer|lab|satellite|orbit|server|data center)\b", blob):
        return "technology"
    if re.search(r"\b(city|street|urban|skyline|downtown|commut)\b", blob) and not re.search(r"\btraffic\b", blob):
        return "city"
    if re.search(r"\b(traffic|cars rush|vehicles|highway)\b", blob):
        return "traffic"
    # "people" was dropped as an independent trigger — it appears in almost
    # any narration ("many people believe...", "people were shocked...") and
    # turned ordinary scenes into crowd/stadium ambience. The remaining words
    # only fire when the sentence is actually about a crowd/audience, not
    # merely mentioning humans. `protest` is widened to also catch
    # protesters/protesting/protests — the exact-noun-only version missed
    # plainly crowd-shaped phrasing like "protesters filled the streets".
    if re.search(r"\b(crowd|audience|stadium|protest(?:s|ers?|ing)?|market|busy)\b", blob):
        return "crowd"
    if re.search(r"\b(wind|forest|mountain|nature|outdoor|wild|meadow|wildlife|bird)\b", blob):
        return "nature"
    if re.search(r"\b(bedroom|office|room|indoor|home|quiet|hallway|library)\b", blob):
        return "room"
    return "room"


def _scene_context(row: dict, aligned: dict) -> Tuple[str, str]:
    text = str(row.get("script_segment") or aligned.get("script_segment") or "")
    prompt = str(row.get("prompt") or row.get("stock") or "")
    return text, prompt


def _parse_ai_ambience(payload: dict, aligned_rows: Sequence[dict]) -> List[dict]:
    items = payload.get("scenes")
    if not isinstance(items, list):
        return []
    valid = {str(r.get("scene_number")) for r in aligned_rows}
    out: List[dict] = []
    seen = set()
    for raw in items:
        if not isinstance(raw, dict):
            continue
        sn = str(raw.get("scene_number") or "").strip()
        if not sn or sn not in valid or sn in seen:
            continue
        profile = _normalize_ambience_profile(str(raw.get("profile") or "room"))
        out.append({"scene_number": sn, "profile": profile, "source": "ai"})
        seen.add(sn)
    return out


def _ai_scene_ambience(
    rows: Sequence[dict],
    aligned_rows: Sequence[dict],
    gemini_settings: Optional[Mapping[str, Any]] = None,
) -> Optional[List[dict]]:
    try:
        from visual_director.llm import GeminiLLM, gemini_configured
    except Exception:
        return None
    if not gemini_configured(gemini_settings):
        return None
    by_num = {str(r.get("scene_number")): r for r in rows}
    lines = []
    for aligned in aligned_rows:
        sn = str(aligned.get("scene_number") or "")
        row = by_num.get(sn) or {}
        text, prompt = _scene_context(row, aligned)
        if len(text) > 120:
            text = text[:117] + "…"
        hint = f" | visual: {prompt[:80]}" if prompt else ""
        lines.append(f"scene {sn}: {text}{hint}")
    user = "Pick one ambience profile per scene.\n" + "\n".join(lines)
    try:
        llm = GeminiLLM(settings=gemini_settings, timeout=90.0)
        raw = llm.complete(_AMBIENCE_SYSTEM, user)
        parsed = _parse_ai_ambience(_extract_json_object(raw), aligned_rows)
        if len(parsed) < max(1, len(aligned_rows) // 2):
            print("[SMART] Ambience AI returned too few scenes; using heuristic.")
            return None
        return parsed
    except Exception as exc:
        print(f"[SMART] Ambience AI unavailable ({exc}); using heuristic profiles.")
        return None


def _heuristic_scene_ambience(
    rows: Sequence[dict],
    aligned_rows: Sequence[dict],
) -> List[dict]:
    by_num = {str(r.get("scene_number")): r for r in rows}
    out: List[dict] = []
    for aligned in aligned_rows:
        sn = str(aligned.get("scene_number") or "")
        row = by_num.get(sn) or {}
        text, prompt = _scene_context(row, aligned)
        profile = _heuristic_ambience_profile(text, prompt)
        out.append({"scene_number": sn, "profile": profile, "source": "heuristic"})
    return out


# Mix level per SFX intensity step. Named so the curve can be asserted
# without a bundled catalog (CI has none) and stays a single source of truth.
_SFX_INTENSITY_VOLUME: Dict[str, float] = {"low": 0.28, "medium": 0.40, "high": 0.52}


def _sfx_base_volume(settings: SmartEditingSettings) -> float:
    return _SFX_INTENSITY_VOLUME.get(settings.sfx_intensity(), 0.40)


def _ambience_volume(settings: SmartEditingSettings) -> float:
    return settings.ambience_volume()


def ambience_volume_bounds(base_volume: float) -> Tuple[float, float]:
    """Per-bed clamp window for a given operator base level.

    The historical window was a fixed [0.05, 0.42], calibrated for the default
    0.30 bed. Scaling it by the operator's chosen base keeps that behaviour
    identical at 0.30 while letting a deliberately louder or quieter setting
    actually reach the mix rather than being clipped back to the old ceiling.
    """
    base = max(0.0, float(base_volume or 0.0))
    if base <= 0.0:
        return (0.0, 0.0)
    scale = base / _AMBIENCE_REFERENCE_VOL
    return (round(0.05 * scale, 4), round(0.42 * scale, 4))


def _display_window_by_scene(
    aligned_rows: Sequence[dict],
    audio_end: float,
) -> Dict[str, Tuple[float, float]]:
    """Map scene_number → (start, end) using the same windows as rendered clips."""
    windows = _scene_display_timeline(list(aligned_rows), float(audio_end))
    out: Dict[str, Tuple[float, float]] = {}
    for i, row in enumerate(aligned_rows):
        sn = str(row.get("scene_number") or "")
        if sn and i < len(windows):
            out[sn] = windows[i]
    return out


def _smooth_ambience_profiles(profiles: Sequence[dict], *, min_run: int = 3) -> List[dict]:
    """Absorb very short profile runs so beds can merge into continuous segments."""
    if len(profiles) < min_run:
        return [dict(p) for p in profiles]
    raw = [dict(p) for p in profiles]
    n = len(raw)
    i = 0
    while i < n:
        prof = str(raw[i].get("profile") or "room")
        j = i + 1
        while j < n and str(raw[j].get("profile") or "room") == prof:
            j += 1
        run_len = j - i
        if run_len < min_run and i > 0:
            prev = str(raw[i - 1].get("profile") or "room")
            nxt = str(raw[j].get("profile") or "room") if j < n else prev
            if prev == nxt:
                for k in range(i, j):
                    raw[k]["profile"] = prev
        i = j
    return raw


def _merge_ambience_beds(beds: Sequence[dict]) -> List[dict]:
    """Return one bed per visual scene — never span multiple scene boundaries.

    Same profile/file may still be selected for adjacent scenes, but each bed
    keeps its own start/end so ambience ends/starts with the visual cut.
    """
    return [dict(b) for b in beds]


_PROFILE_BOUNDARY_GAP_S = 0.05
_PROFILE_BOUNDARY_FADE_OUT_S = 0.10


def _annotate_ambience_boundary_fades(beds: List[dict]) -> None:
    """Set abutting-bed fades so scene cuts stay tight without silence gaps.

    - Different profile: short fade-out on outgoing, hard fade-in on incoming.
    - Same profile: hard abut (no fade-out/fade-in pair) so the bed sounds continuous
      while remaining logically one segment per visual scene.
    """
    if len(beds) < 2:
        return
    ordered = sorted(beds, key=lambda b: float(b.get("start") or 0.0))
    for i in range(len(ordered) - 1):
        cur = ordered[i]
        nxt = ordered[i + 1]
        gap = float(nxt["start"]) - float(cur["end"])
        if abs(gap) > _PROFILE_BOUNDARY_GAP_S:
            continue
        if cur.get("profile") == nxt.get("profile"):
            cur["fade_out"] = 0.0
            nxt["fade_in"] = 0.0
            continue
        dur = float(cur.get("duration") or 0.5)
        cur["fade_out"] = min(_PROFILE_BOUNDARY_FADE_OUT_S, max(0.04, dur / 12.0))
        nxt["fade_in"] = 0.0


def _pick_ambience_entry(
    catalog: SfxCatalog,
    profile: str,
    settings: SmartEditingSettings,
    *,
    scene_number: str,
    avoid_ids: Sequence[str],
) -> Optional[SfxEntry]:
    tags = _AMBIENCE_PROFILES.get(profile, ("room",))
    request = SfxRequest("scene_ambience", "ambience", tags, settings.ambience_intensity(), 30.0)
    pool = list(catalog._by_category.get("ambience", []))
    if not pool:
        return None
    req_tags = {t.lower() for t in tags if t}
    req_intensity = (settings.ambience_intensity() or "medium").lower()
    avoided = {str(x) for x in avoid_ids if x}

    def score(entry: SfxEntry) -> Tuple[int, int, float]:
        if not entry.resolved_path(catalog.root).is_file():
            return (-998, 0, entry.duration)
        tag_hits = len(req_tags.intersection(set(entry.tags))) if req_tags else 0
        intensity_delta = abs(_intensity_rank(entry.intensity) - _intensity_rank(req_intensity))
        return (tag_hits, -intensity_delta, entry.duration)

    ranked = sorted(pool, key=score, reverse=True)
    top_score = score(ranked[0])[0] if ranked else -999
    candidates = [e for e in ranked if score(e)[0] == top_score and score(e)[0] > -998]
    if not candidates:
        return catalog.match(request, avoid_ids=avoid_ids)
    try:
        sn_num = int(re.sub(r"\D", "", scene_number) or "0")
    except ValueError:
        sn_num = hash(scene_number) % 997
    start = (sn_num + len(avoid_ids)) % len(candidates)
    for offset in range(len(candidates)):
        entry = candidates[(start + offset) % len(candidates)]
        if entry.id not in avoided:
            return entry
    return candidates[0]


def _resolve_ambience_beds(
    profiles: Sequence[dict],
    aligned_rows: Sequence[dict],
    settings: SmartEditingSettings,
    catalog: SfxCatalog,
    *,
    display_windows: Optional[Mapping[str, Tuple[float, float]]] = None,
    editorial_plan: Any = None,
) -> List[dict]:
    aligned_by_sn = {str(r.get("scene_number")): r for r in aligned_rows}
    windows = display_windows or {}
    beds: List[dict] = []
    recent_ids: List[str] = []
    base_vol = _ambience_volume(settings)
    if base_vol <= 0.0:
        # Operator muted ambience with the volume control. Emitting silent beds
        # would still cost an ffmpeg input per scene, so plan none at all.
        return []
    vol_lo, vol_hi = ambience_volume_bounds(base_vol)
    intensity_map: Dict[str, float] = {}
    if editorial_plan is not None and hasattr(editorial_plan, "ambience_intensity_map"):
        try:
            intensity_map = dict(editorial_plan.ambience_intensity_map())
        except Exception:
            intensity_map = {}
    for pick in profiles:
        sn = str(pick.get("scene_number") or "")
        aligned = aligned_by_sn.get(sn)
        if aligned is None:
            continue
        profile = _normalize_ambience_profile(str(pick.get("profile") or "room"))
        if profile == "none":
            continue
        if sn in windows:
            start, end = windows[sn]
        else:
            start = float(aligned["start_time"])
            end = float(aligned["end_time"])
        duration = max(0.5, end - start)
        tags = _AMBIENCE_PROFILES.get(profile, ("room",))
        request = SfxRequest("scene_ambience", "ambience", tags, settings.ambience_intensity(), 30.0)
        entry = _pick_ambience_entry(
            catalog,
            profile,
            settings,
            scene_number=sn,
            avoid_ids=recent_ids,
        )
        if entry is None:
            entry = _pick_sfx_entry(catalog, request, avoid_ids=recent_ids)
        if entry is None:
            entry = _pick_sfx_entry(
                catalog,
                SfxRequest("scene_ambience", "ambience", (), settings.ambience_intensity(), 30.0),
                avoid_ids=recent_ids,
            )
        if entry is None:
            continue
        recent_ids.append(entry.id)
        if len(recent_ids) > 12:
            del recent_ids[0]
        vol = base_vol
        if sn in intensity_map:
            vol = min(vol_hi, max(vol_lo, base_vol * float(intensity_map[sn])))
        beds.append(
            {
                "type": "scene_ambience",
                "scene_number": sn,
                "profile": profile,
                "start": round(start, 3),
                "end": round(end, 3),
                "duration": round(duration, 3),
                "volume": round(vol, 3),
                # Operator base level, so downstream stages clamp against what
                # was actually asked for rather than a hardcoded default.
                "base_volume": round(base_vol, 3),
                "file": entry.file,
                "sfx_id": entry.id,
                "source": pick.get("source") or "heuristic",
            }
        )
    return beds


def _apply_editorial_ambience_hints(
    profiles: List[dict],
    editorial_plan: Any,
) -> List[dict]:
    profile_map = getattr(editorial_plan, "ambience_profile_map", None)
    if not callable(profile_map):
        return profiles
    hints = profile_map()
    if not hints:
        return profiles
    out = [dict(p) for p in profiles]
    by_sn = {str(p.get("scene_number")): i for i, p in enumerate(out)}
    for sn, profile in hints.items():
        if not sn or not profile:
            continue
        normalized = _normalize_ambience_profile(str(profile))
        if sn in by_sn:
            out[by_sn[sn]]["profile"] = normalized
            out[by_sn[sn]]["source"] = "editorial"
        else:
            out.append({"scene_number": sn, "profile": normalized, "source": "editorial"})
    return out


def plan_scene_ambience(
    rows: Sequence[dict],
    aligned_rows: Sequence[dict],
    settings: SmartEditingSettings,
    catalog: Optional[SfxCatalog] = None,
    *,
    audio_end: Optional[float] = None,
    gemini_settings: Optional[Mapping[str, Any]] = None,
    editorial_plan: Any = None,
) -> List[dict]:
    if not settings.scene_ambience or not aligned_rows:
        return []
    cat = catalog if catalog is not None else get_sfx_catalog()
    if not cat.entries:
        return []
    end_time = float(audio_end if audio_end is not None else aligned_rows[-1].get("end_time") or 0.0)
    display_windows = _display_window_by_scene(aligned_rows, end_time)
    ai = _ai_scene_ambience(rows, aligned_rows, gemini_settings)
    if ai is not None:
        profiles = _smooth_ambience_profiles(ai)
        print(f"[SMART] AI picked ambience for {len(profiles)} scene(s).")
    else:
        profiles = _smooth_ambience_profiles(_heuristic_scene_ambience(rows, aligned_rows))
        print(f"[SMART] Heuristic ambience for {len(profiles)} scene(s).")
    if editorial_plan is not None:
        profiles = _apply_editorial_ambience_hints(profiles, editorial_plan)
    beds = _resolve_ambience_beds(
        profiles,
        aligned_rows,
        settings,
        cat,
        display_windows=display_windows,
        editorial_plan=editorial_plan,
    )
    if len(beds) > 1:
        merged = _merge_ambience_beds(beds)
        if len(merged) < len(beds):
            print(
                f"[SMART] Merged {len(beds)} scene beds into {len(merged)} "
                f"continuous ambience segment(s)."
            )
        beds = merged
    beds = list(beds)
    _annotate_ambience_boundary_fades(beds)
    if beds:
        mix = ", ".join(f"{b['scene_number']}={b['profile']}" for b in beds[:8])
        if len(beds) > 8:
            mix += f", +{len(beds) - 8} more"
        print(f"[SMART] Scene ambience beds: {mix}")
    return beds


def plan_sfx_events(
    aligned_rows: Sequence[dict],
    text_effects: Sequence[dict],
    settings: SmartEditingSettings,
    catalog: Optional[SfxCatalog] = None,
    *,
    scene_transitions: Optional[Sequence[dict]] = None,
    editorial_plan: Any = None,
) -> List[dict]:
    if not settings.sound_effects:
        return []
    cat = catalog if catalog is not None else get_sfx_catalog()
    if not cat.entries:
        return []
    events: List[dict] = []
    recent_ids: List[str] = []
    # Keep narration dominant, but previous medium≈0.14 was inaudible in real mixes.
    base_vol = _sfx_base_volume(settings)

    def _remember(entry: SfxEntry) -> None:
        recent_ids.append(entry.id)
        if len(recent_ids) > 4:
            del recent_ids[0]

    for fx in text_effects:
        request = _sfx_request_for_text_effect(str(fx.get("effect") or ""), settings)
        entry = _pick_sfx_entry(cat, request, avoid_ids=recent_ids)
        if entry is None:
            continue
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
        _remember(entry)

    # Transition SFX only on AI/heuristic-selected scene boundaries.
    sfx_scenes = {
        str(item.get("scene_number") or "")
        for item in (scene_transitions or [])
        if item.get("sfx", True) is not False and item.get("scene_number")
    }
    for i, row in enumerate(aligned_rows):
        if i == 0:
            continue
        sn = str(row.get("scene_number") or "")
        if sn not in sfx_scenes:
            continue
        start = float(row["start_time"])
        duration = float(row["end_time"]) - start
        if duration < 0.8:
            continue
        hit = cat.match_any(
            _transition_sfx_fallback_chain(settings, i - 1),
            avoid_ids=recent_ids,
        )
        if hit is None:
            continue
        entry, request = hit
        events.append(
            _entry_to_event(
                entry,
                request,
                start=max(0.0, start - 0.08),
                volume=round(min(0.58, base_vol * 1.05), 3),
                scene_number=sn,
            )
        )
        _remember(entry)

    # Mid-scene accents — especially when Text Effects are off (still sparse).
    beat_budget = _beat_budget(
        len(aligned_rows), settings.sfx_intensity(), text_effects_on=bool(text_effects),
    )
    if beat_budget > 0:
        fx_times: Dict[str, List[float]] = {}
        for fx in text_effects:
            sn = str(fx.get("scene_number") or "")
            fx_times.setdefault(sn, []).append(float(fx["start"]))
        scored_beats: List[Tuple[float, int, str, float, float]] = []
        for i, row in enumerate(aligned_rows):
            sn = str(row.get("scene_number") or "")
            start = float(row["start_time"])
            end = float(row["end_time"])
            dur = end - start
            if dur < 2.0:
                continue
            text = str(row.get("script_segment") or "")
            score = len(_token_set(text)) * 0.5
            if _TRANSITION_CUE_RE.search(text):
                score += 1.0
            # Editorial purpose boost/penalty
            if editorial_plan is not None:
                escene = editorial_plan.scene_by_number().get(sn)
                if escene is not None:
                    if escene.purpose == "hook":
                        score += 1.2
                    elif escene.purpose in ("evidence", "explanation"):
                        score *= 0.45
                    elif escene.allow_silence:
                        score *= 0.15
                    score += float(escene.attention_score or 0.5)
            scored_beats.append((score, i, sn, start, dur))
        scored_beats.sort(key=lambda t: (-t[0], t[1]))
        picked_beat_idx: List[int] = []
        for score, i, sn, start, dur in scored_beats:
            if len(picked_beat_idx) >= beat_budget:
                break
            if score < 0.4 and len(picked_beat_idx) >= max(1, beat_budget // 3):
                continue
            if any(abs(i - j) <= 1 for j in picked_beat_idx):
                continue
            mid = start + dur * 0.48
            if sn in sfx_scenes and mid - start < 0.45:
                continue
            if any(abs(mid - t) < 0.35 for t in fx_times.get(sn, [])):
                continue
            request = _beat_sfx_request(settings, len(picked_beat_idx))
            entry = _pick_sfx_entry(cat, request, avoid_ids=recent_ids)
            if entry is None:
                continue
            vol = min(0.42, base_vol * 0.72)
            events.append(
                _entry_to_event(
                    entry,
                    request,
                    start=mid,
                    volume=round(vol, 3),
                    scene_number=sn,
                )
            )
            _remember(entry)
            picked_beat_idx.append(i)

    events.sort(key=lambda e: float(e.get("start") or 0.0))
    if editorial_plan is not None:
        try:
            from editorial.audio_director import filter_sfx_events

            events = filter_sfx_events(events, editorial_plan, aligned_rows=aligned_rows)
        except Exception as exc:
            print(f"[SMART] Editorial SFX filter skipped ({exc})")
    return events


def build_plan(
    rows: Sequence[dict],
    aligned_rows: Sequence[dict],
    whisper_words: Sequence[Tuple[str, float, float]],
    settings: SmartEditingSettings,
    *,
    state_dir: Optional[Path] = None,
    audio_path: Optional[Path | str] = None,
    gemini_settings: Optional[Mapping[str, Any]] = None,
    editorial_plan: Any = None,
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
    scene_transitions = plan_scene_transitions(
        rows,
        aligned_rows,
        settings,
        gemini_settings=gemini_settings,
        editorial_plan=editorial_plan,
    )
    audio_end = float(aligned_rows[-1].get("end_time") or 0.0) if aligned_rows else 0.0
    scene_ambience = (
        plan_scene_ambience(
            rows,
            aligned_rows,
            settings,
            audio_end=audio_end,
            gemini_settings=gemini_settings,
            editorial_plan=editorial_plan,
        )
        if settings.scene_ambience
        else []
    )
    sfx_events = (
        plan_sfx_events(
            aligned_rows,
            text_effects,
            settings,
            scene_transitions=scene_transitions,
            editorial_plan=editorial_plan,
        )
        if settings.sound_effects
        else []
    )
    plan = SmartEditingPlan(
        text_effects=text_effects,
        sfx_events=sfx_events,
        whisper_words=whisper_list,
        scene_transitions=scene_transitions,
        scene_ambience=scene_ambience,
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
        proc = hidden_subprocess.run(
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


_MIX_CHUNK_SIZE = 24
_MIX_CHUNK_SIZE_WIN = 8
# Windows CreateProcess cmdline limit is ~32k; stay well under with filter script.
_WIN_CMDLINE_SOFT_LIMIT = 7000


def _mix_chunk_size() -> int:
    if sys.platform == "win32":
        return int(os.environ.get("SMART_MIX_CHUNK_SIZE", _MIX_CHUNK_SIZE_WIN))
    return int(os.environ.get("SMART_MIX_CHUNK_SIZE", _MIX_CHUNK_SIZE))


def _is_win_cmdline_error(exc: BaseException) -> bool:
    if sys.platform != "win32":
        return False
    if isinstance(exc, OSError):
        winerr = getattr(exc, "winerror", None)
        if winerr in (206, 87):  # filename too long / parameter incorrect
            return True
        if "too long" in str(exc).lower():
            return True
    return False


def _estimate_cmd_chars(cmd: Sequence[str]) -> int:
    # Rough Windows CreateProcess length (argv joined with spaces + quotes)
    total = 0
    for part in cmd:
        s = str(part)
        total += len(s) + 3  # space + optional quotes
    return total


def _ffmpeg_path_arg(path: Path | str) -> str:
    """Windows ffmpeg is more reliable with forward-slash paths."""
    p = Path(path)
    try:
        p = p.resolve()
    except OSError:
        pass
    if sys.platform == "win32":
        return p.as_posix()
    return str(p)


def _normalize_ffmpeg_cmd(cmd: List[str]) -> List[str]:
    if sys.platform != "win32":
        return list(cmd)
    out: List[str] = []
    i = 0
    while i < len(cmd):
        token = cmd[i]
        if token in ("-i", "-filter_complex_script") and i + 1 < len(cmd):
            out.extend([token, _ffmpeg_path_arg(cmd[i + 1])])
            i += 2
            continue
        if i == len(cmd) - 1 and not token.startswith("-"):
            out.append(_ffmpeg_path_arg(token))
        else:
            out.append(token)
        i += 1
    return out


def _run_ffmpeg_cmd(cmd: List[str], *, work_dir: Optional[Path] = None) -> bool:
    """Run ffmpeg; on Windows prefer filter_complex_script to avoid WinError 206."""
    cmd = _normalize_ffmpeg_cmd(cmd)
    cwd = str(work_dir) if work_dir else None
    script_path: Optional[Path] = None

    def _with_filter_script(raw: List[str]) -> List[str]:
        nonlocal script_path
        if "-filter_complex" not in raw:
            return raw
        idx = raw.index("-filter_complex")
        if idx + 1 >= len(raw):
            return raw
        graph = raw[idx + 1]
        base = Path(work_dir) if work_dir else Path(raw[-1]).resolve().parent
        base.mkdir(parents=True, exist_ok=True)
        script_path = base / f"_fc_{os.getpid()}_{abs(hash(graph)) % 10_000_000}.txt"
        script_path.write_text(graph, encoding="utf-8")
        out = raw[:idx] + ["-filter_complex_script", _ffmpeg_path_arg(script_path)] + raw[idx + 2 :]
        return out

    use_script = sys.platform == "win32" or _estimate_cmd_chars(cmd) > _WIN_CMDLINE_SOFT_LIMIT
    attempt = _with_filter_script(cmd) if use_script else cmd
    try:
        proc = hidden_subprocess.run(attempt, capture_output=True, text=True, cwd=cwd)
        ok = proc.returncode == 0
        if not ok and use_script and attempt is not cmd:
            # Some Windows ffmpeg builds reject filter_complex_script paths — retry inline.
            proc = hidden_subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
            ok = proc.returncode == 0
        if not ok and _mix_debug_enabled():
            _mix_debug(f"ffmpeg rc={proc.returncode} stderr={(proc.stderr or '')[-400:]}")
        return ok
    except OSError as exc:
        if _is_win_cmdline_error(exc) and attempt is cmd and "-filter_complex" in cmd:
            # Retry once with filter script
            try:
                attempt2 = _with_filter_script(cmd)
                proc = hidden_subprocess.run(attempt2, capture_output=True, text=True, cwd=cwd)
                return proc.returncode == 0
            except OSError as exc2:
                _mix_debug(f"ffmpeg OSError after script retry: {exc2}")
                return False
        _mix_debug(f"ffmpeg OSError: {exc}")
        return False
    finally:
        if script_path is not None and not _mix_keep_temp():
            try:
                script_path.unlink(missing_ok=True)
            except OSError:
                pass


def _mix_debug_enabled() -> bool:
    return os.environ.get("SMART_MIX_DEBUG", "").strip().lower() in ("1", "true", "yes")


def _mix_keep_temp() -> bool:
    return os.environ.get("SMART_MIX_KEEP_TEMP", "").strip().lower() in ("1", "true", "yes")


def _boundary_debug_enabled() -> bool:
    return os.environ.get("SMART_MIX_BOUNDARY_DEBUG", "").strip().lower() in ("1", "true", "yes")


def _mix_debug(msg: str) -> None:
    if _mix_debug_enabled():
        print(f"[SMART][MIX-DEBUG] {msg}")


def _probe_duration(path: Path) -> Optional[float]:
    try:
        return float(probe_audio(path).duration_seconds)
    except (ValueError, RuntimeError, OSError):
        return None


def _dump_ambience_boundary_forensics(
    beds_usable: Sequence[tuple[Path, dict, str]],
    stem_path: Path,
    out_dir: Path,
    *,
    max_boundaries: int = 3,
) -> None:
    """Write previous/next solo stems for the first profile-change + mid-merge boundaries."""
    beds = [(p, ev) for p, ev, kind in beds_usable if kind == "ambience"]
    if len(beds) < 2:
        return
    out_dir.mkdir(parents=True, exist_ok=True)
    ordered = sorted(beds, key=lambda x: float(x[1].get("start") or 0.0))
    targets: List[tuple[str, float, tuple[Path, dict], tuple[Path, dict]]] = []
    for i in range(len(ordered) - 1):
        p_path, prev = ordered[i]
        n_path, nxt = ordered[i + 1]
        T = float(prev.get("end") or 0.0)
        if abs(float(nxt.get("start") or 0.0) - T) > 0.05:
            continue
        if prev.get("profile") != nxt.get("profile"):
            targets.append(("profile_change", T, (p_path, prev), (n_path, nxt)))
        if len(targets) >= max_boundaries:
            break
    # Also dump the first long merged bed endpoint as a visual-cut forensic if present.
    for path, bed in ordered:
        sn = str(bed.get("scene_number") or "")
        if "-" in sn and float(bed.get("duration") or 0.0) >= 20.0:
            T = float(bed.get("end") or 0.0)
            # Find next bed after this merged segment for contrast.
            nxt = next((x for x in ordered if float(x[1].get("start") or 0.0) >= T - 0.01), None)
            if nxt is not None and nxt[1] is not bed:
                targets.append(("merged_end", T, (path, bed), nxt))
            break
    for idx, (kind, T, (p_path, prev), (n_path, nxt)) in enumerate(targets[:max_boundaries]):
        sub = out_dir / f"boundary_{idx}_{kind}_T{T:.2f}"
        sub.mkdir(parents=True, exist_ok=True)
        local_prev = dict(prev)
        local_prev["start"] = 0.0
        local_next = dict(nxt)
        local_next["start"] = 0.0
        prev_local = sub / "previous_bed.wav"
        next_local = sub / "next_bed.wav"
        prev_delayed = sub / "previous_bed_delayed.wav"
        next_delayed = sub / "next_bed_delayed.wav"
        boundary_mix = sub / "boundary_mix.wav"
        trim = T + float(nxt.get("duration") or 1.0) + 0.5
        _ffmpeg_mix_ambience_chunk([(p_path, local_prev)], prev_local, trim_duration=float(prev.get("duration") or 1.0) + 0.5)
        _ffmpeg_mix_ambience_chunk([(n_path, local_next)], next_local, trim_duration=float(nxt.get("duration") or 1.0) + 0.5)
        _ffmpeg_mix_ambience_chunk([(p_path, prev)], prev_delayed, trim_duration=trim)
        _ffmpeg_mix_ambience_chunk([(n_path, nxt)], next_delayed, trim_duration=trim)
        _ffmpeg_mix_ambience_chunk([(p_path, prev), (n_path, nxt)], boundary_mix, trim_duration=trim)
        meta = {
            "kind": kind,
            "T": T,
            "previous": {k: prev.get(k) for k in ("scene_number", "profile", "start", "end", "duration", "volume", "file", "fade_in", "fade_out")},
            "next": {k: nxt.get(k) for k in ("scene_number", "profile", "start", "end", "duration", "volume", "file", "fade_in", "fade_out")},
            "durations_sec": {
                "previous_bed": _probe_duration(prev_local),
                "next_bed": _probe_duration(next_local),
                "previous_bed_delayed": _probe_duration(prev_delayed),
                "next_bed_delayed": _probe_duration(next_delayed),
                "boundary_mix": _probe_duration(boundary_mix),
                "ambience_stem": _probe_duration(stem_path) if stem_path.is_file() else None,
            },
        }
        (sub / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        print(
            f"[SMART][BOUNDARY-DEBUG] {kind} T={T:.3f}s "
            f"{prev.get('scene_number')}={prev.get('profile')} → "
            f"{nxt.get('scene_number')}={nxt.get('profile')} → {sub}"
        )


def _ffmpeg_mix_ambience_chunk(
    layers: Sequence[tuple[Path, dict]],
    output_path: Path,
    *,
    base_path: Optional[Path] = None,
    trim_duration: Optional[float] = None,
) -> bool:
    """Build an ambience stem from delayed bed layers (optionally extending an existing stem)."""
    if not layers:
        if base_path is not None and base_path.is_file():
            if trim_duration is not None:
                cmd = [
                    "ffmpeg", "-y", "-i", str(base_path),
                    "-af", f"atrim=0:{trim_duration:.3f}",
                    str(output_path),
                ]
                proc = hidden_subprocess.run(cmd, capture_output=True, text=True)
                return proc.returncode == 0 and output_path.is_file()
            shutil.copy2(base_path, output_path)
            return True
        return False
    cmd = ["ffmpeg", "-y"]
    filter_parts: List[str] = []
    mix_labels: List[str] = []
    input_idx = 0
    if base_path is not None:
        cmd.extend(["-i", str(base_path)])
        mix_labels.append("[0:a]")
        input_idx = 1
    for path, ev in layers:
        cmd.extend(["-stream_loop", "-1", "-i", str(path)])
        delay_ms = max(0, int(float(ev.get("start") or 0.0) * 1000))
        dur = float(ev.get("duration") or 0.0)
        if dur <= 0.0:
            end = float(ev.get("end") or ev.get("start") or 0.0)
            start = float(ev.get("start") or 0.0)
            dur = max(0.5, end - start)
        vol = min(0.42, float(ev.get("volume") or 0.30))
        default_fade = min(0.35, max(0.08, dur / 5.0))
        fade_in = float(ev["fade_in"]) if ev.get("fade_in") is not None else default_fade
        fade_out = float(ev["fade_out"]) if ev.get("fade_out") is not None else default_fade
        fade_parts: List[str] = []
        if fade_in > 0.001:
            fade_parts.append(f"afade=t=in:st=0:d={fade_in:.3f}")
        if fade_out > 0.001:
            fade_out_st = max(0.0, dur - fade_out)
            fade_parts.append(f"afade=t=out:st={fade_out_st:.3f}:d={fade_out:.3f}")
        fade_chain = (",".join(fade_parts) + ",") if fade_parts else ""
        label = f"amb{input_idx}"
        # Fade on the trimmed clip (local t=0..dur), then adelay to global start.
        filter_parts.append(
            f"[{input_idx}:a]atrim=0:{dur:.3f},asetpts=PTS-STARTPTS,"
            f"volume={vol:.4f},"
            f"{fade_chain}"
            f"adelay={delay_ms}|{delay_ms}[{label}]"
        )
        mix_labels.append(f"[{label}]")
        input_idx += 1
    n = len(mix_labels)
    out_label = "aout"
    if trim_duration is not None:
        filter_parts.append(
            f"{''.join(mix_labels)}amix=inputs={n}:duration=longest:dropout_transition=0:normalize=0[amixed];"
            f"[amixed]atrim=0:{trim_duration:.3f}[{out_label}]"
        )
    else:
        filter_parts.append(
            f"{''.join(mix_labels)}amix=inputs={n}:duration=longest:dropout_transition=0:normalize=0[{out_label}]"
        )
    cmd.extend(["-filter_complex", ";".join(filter_parts), "-map", f"[{out_label}]", str(output_path)])
    work = Path(output_path).resolve().parent
    ok = _run_ffmpeg_cmd(cmd, work_dir=work) and output_path.is_file()
    if _mix_debug_enabled():
        beds = [float(ev.get("start") or 0.0) for _, ev in layers]
        _mix_debug(
            f"ambience chunk → {output_path.name}: ok={ok} layers={len(layers)} "
            f"base={'yes' if base_path else 'no'} trim={trim_duration} "
            f"start_range={min(beds, default=0):.1f}-{max(beds, default=0):.1f}s "
            f"out_dur={_probe_duration(output_path)}"
        )
    return ok


def _mix_ambience_stem_chunked(
    layers: Sequence[tuple[Path, dict, str]],
    output_path: Path,
    *,
    temp_dir: Path,
    total_duration: float,
) -> tuple[int, bool]:
    """Mix all ambience beds onto a dedicated stem (never re-processes narration)."""
    amb_layers = [(p, ev) for p, ev, kind in layers if kind == "ambience"]
    if not amb_layers:
        return 0, False
    current: Optional[Path] = None
    mixed = 0
    temps: List[Path] = []
    chunk_size = _mix_chunk_size()
    for offset in range(0, len(amb_layers), chunk_size):
        chunk = amb_layers[offset : offset + chunk_size]
        is_last = offset + chunk_size >= len(amb_layers)
        dest = output_path if is_last else temp_dir / f"amb_stem_{offset // chunk_size + 1}.wav"
        if not is_last:
            temps.append(dest)
        trim = total_duration if is_last else None
        if not _ffmpeg_mix_ambience_chunk(chunk, dest, base_path=current, trim_duration=trim):
            for t in temps:
                t.unlink(missing_ok=True)
            return mixed, False
        mixed += len(chunk)
        if not is_last:
            current = dest
    for t in temps:
        t.unlink(missing_ok=True)
    return mixed, True


def _ffmpeg_mix_narration_with_stem(
    narration_path: Path,
    stem_path: Path,
    output_path: Path,
) -> bool:
    """Combine narration with a pre-built ambience stem (2-input mix, narration stays dominant)."""
    cmd = [
        "ffmpeg", "-y",
        "-i", str(narration_path),
        "-i", str(stem_path),
        "-filter_complex",
        "[0:a][1:a]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,volume=0.98[aout]",
        "-map", "[aout]",
        str(output_path),
    ]
    return _run_ffmpeg_cmd(cmd, work_dir=Path(output_path).resolve().parent) and output_path.is_file()


def _ffmpeg_mix_layers(
    base_path: Path,
    layers: Sequence[tuple[Path, dict, str]],
    output_path: Path,
) -> bool:
    """Mix one narration/base track with a chunk of SFX or ambience layers."""
    if not layers:
        shutil.copy2(base_path, output_path)
        return True
    cmd = ["ffmpeg", "-y", "-i", str(base_path)]
    filter_parts: List[str] = []
    mix_inputs = ["[0:a]"]
    input_idx = 1
    for path, ev, kind in layers:
        if kind == "ambience":
            cmd.extend(["-stream_loop", "-1", "-i", str(path)])
        else:
            cmd.extend(["-i", str(path)])
        delay_ms = max(0, int(float(ev.get("start") or 0.0) * 1000))
        if kind == "ambience":
            dur = float(ev.get("duration") or 0.0)
            if dur <= 0.0:
                end = float(ev.get("end") or ev.get("start") or 0.0)
                start = float(ev.get("start") or 0.0)
                dur = max(0.5, end - start)
            vol = min(0.42, float(ev.get("volume") or 0.30))
            fade = min(0.25, dur / 4.0)
            fade_out_st = max(0.0, dur - fade)
            label = f"x{input_idx}"
            filter_parts.append(
                f"[{input_idx}:a]atrim=0:{dur:.3f},asetpts=PTS-STARTPTS,"
                f"volume={vol:.4f},adelay={delay_ms}|{delay_ms},"
                f"afade=t=in:st=0:d={fade:.3f},afade=t=out:st={fade_out_st:.3f}:d={fade:.3f}[{label}]"
            )
        else:
            vol = min(0.55, float(ev.get("volume") or 0.32))
            dur = float(ev.get("duration") or 0.4)
            label = f"x{input_idx}"
            filter_parts.append(
                f"[{input_idx}:a]atrim=0:{dur:.3f},asetpts=PTS-STARTPTS,"
                f"volume={vol:.4f},adelay={delay_ms}|{delay_ms}[{label}]"
            )
        mix_inputs.append(f"[{label}]")
        input_idx += 1
    n = len(mix_inputs)
    filter_parts.append(
        f"{''.join(mix_inputs)}amix=inputs={n}:duration=first:dropout_transition=0:normalize=0,"
        f"volume=0.95[aout]"
    )
    cmd.extend(["-filter_complex", ";".join(filter_parts), "-map", "[aout]", str(output_path)])
    return _run_ffmpeg_cmd(cmd, work_dir=Path(output_path).resolve().parent) and output_path.is_file()


def _mix_layers_chunked(
    base_path: Path,
    layers: Sequence[tuple[Path, dict, str]],
    output_path: Path,
    *,
    temp_dir: Path,
    prefix: str,
) -> tuple[int, bool]:
    if not layers:
        shutil.copy2(base_path, output_path)
        return 0, True
    current = base_path
    mixed = 0
    chunk_count = 0
    temps: List[Path] = []
    chunk_size = _mix_chunk_size()
    for offset in range(0, len(layers), chunk_size):
        chunk = layers[offset : offset + chunk_size]
        chunk_count += 1
        is_last = offset + chunk_size >= len(layers)
        if is_last:
            dest = output_path
        else:
            dest = temp_dir / f"{prefix}_{chunk_count}.wav"
            temps.append(dest)
        if not _ffmpeg_mix_layers(current, chunk, dest):
            for t in temps:
                t.unlink(missing_ok=True)
            return mixed, False
        mixed += len(chunk)
        if not is_last:
            current = dest
    for t in temps:
        t.unlink(missing_ok=True)
    return mixed, True


def mix_sfx_with_narration(
    narration_path: Path | str,
    sfx_events: Sequence[dict],
    output_path: Path | str,
    *,
    sfx_root: Optional[Path] = None,
    ambience_beds: Optional[Sequence[dict]] = None,
    stats: Optional[Dict[str, Any]] = None,
) -> Path:
    narration_path = Path(narration_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    root = Path(sfx_root or sfx_library_root())

    usable: List[tuple[Path, dict, str]] = []
    sfx_skipped = 0
    for ev in sfx_events:
        path = _resolve_sfx_file(ev, root)
        if path is not None:
            usable.append((path, ev, "sfx"))
        else:
            sfx_skipped += 1

    beds_usable: List[tuple[Path, dict, str]] = []
    amb_skipped = 0
    for bed in ambience_beds or ():
        path = _resolve_sfx_file(bed, root)
        if path is not None:
            beds_usable.append((path, bed, "ambience"))
        else:
            amb_skipped += 1

    report: Dict[str, Any] = {
        "sfx_planned": len(sfx_events),
        "sfx_mixed": 0,
        "sfx_skipped": sfx_skipped,
        "ambience_planned": len(ambience_beds or ()),
        "ambience_mixed": 0,
        "ambience_skipped": amb_skipped,
        "mix_chunks": 0,
        "used_fallback": False,
    }

    if not usable and not beds_usable:
        shutil.copy2(narration_path, output_path)
        if stats is not None:
            stats.update(report)
        return output_path

    temp_dir = output_path.parent / ".smart_mix_tmp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    current = narration_path
    ok = True

    if beds_usable:
        if _mix_debug_enabled() and beds_usable:
            starts = [float(b[1].get("start") or 0.0) for b in beds_usable]
            _mix_debug(
                f"ambience plan: {len(beds_usable)} beds, "
                f"timeline {min(starts):.1f}s–{max(float(b[1].get('end') or 0.0) for b in beds_usable):.1f}s"
            )
        try:
            narr_info = probe_audio(narration_path)
            total_duration = float(narr_info.duration_seconds) + 0.25
        except (ValueError, RuntimeError, OSError):
            total_duration = max(
                (float(b[1].get("end") or 0.0) for b in beds_usable),
                default=60.0,
            )
        amb_stem = temp_dir / "ambience_stem.wav"
        amb_out = temp_dir / "with_ambience.wav" if usable else output_path
        mixed, ok = _mix_ambience_stem_chunked(
            beds_usable, amb_stem, temp_dir=temp_dir, total_duration=total_duration,
        )
        report["ambience_mixed"] = mixed
        report["mix_chunks"] += (len(beds_usable) + _mix_chunk_size() - 1) // _mix_chunk_size()
        if ok and amb_stem.is_file() and _boundary_debug_enabled():
            dbg = output_path.parent / "smart_mix_boundary_debug"
            _dump_ambience_boundary_forensics(beds_usable, amb_stem, dbg)
            if amb_stem.is_file():
                shutil.copy2(amb_stem, dbg / "ambience_stem.wav")
        if ok and amb_stem.is_file():
            ok = _ffmpeg_mix_narration_with_stem(narration_path, amb_stem, amb_out)
            _mix_debug(
                f"narration+stem → {amb_out.name}: ok={ok} "
                f"narr_dur={_probe_duration(narration_path)} stem_dur={_probe_duration(amb_stem)}"
            )
        if ok:
            current = amb_out

    if ok and usable:
        mixed, sfx_ok = _mix_layers_chunked(
            current, usable, output_path, temp_dir=temp_dir, prefix="sfx",
        )
        report["sfx_mixed"] = mixed
        report["mix_chunks"] += (len(usable) + _mix_chunk_size() - 1) // _mix_chunk_size()
        ok = sfx_ok
    elif ok and not usable:
        if current != output_path:
            shutil.copy2(current, output_path)

    if not ok or not output_path.is_file():
        report["used_fallback"] = True
        shutil.copy2(narration_path, output_path)

    if _mix_keep_temp():
        keep_root = output_path.parent / "smart_mix_debug"
        keep_root.mkdir(parents=True, exist_ok=True)
        for name in ("ambience_stem.wav", "with_ambience.wav"):
            src = temp_dir / name
            if src.is_file():
                shutil.copy2(src, keep_root / name)
        shutil.copy2(output_path, keep_root / output_path.name)
        print(f"[SMART][MIX-DEBUG] Kept mix artifacts under {keep_root}")
    else:
        shutil.rmtree(temp_dir, ignore_errors=True)
    if stats is not None:
        stats.update(report)
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
            {
                "id": "ambience_room_test",
                "file": "ambience/ambience_room_test.wav",
                "category": "ambience",
                "tags": ["room", "office"],
                "intensity": "medium",
                "duration": 3.0,
                "source": "test",
                "license": "test",
                "commercial_use": True,
                "attribution_required": False,
            },
            {
                "id": "ambience_city_test",
                "file": "ambience/ambience_city_test.wav",
                "category": "ambience",
                "tags": ["city", "traffic"],
                "intensity": "medium",
                "duration": 3.0,
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
