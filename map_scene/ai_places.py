"""AI fallback for places with no official border (e.g. "Eglin Air Force Base").

Gemini (the app's existing client) is asked what the place is made of — a
group of US counties / provinces / countries — or, for a small site, where it
is. Answers are cached on disk so each place is asked once, ever.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Callable, Optional

_SYSTEM = (
    "You locate places for a map. Reply with JSON only. If the place is a region made of whole "
    "US counties, reply {\"type\":\"us_counties\",\"items\":[\"State|County\",...]}. If it is made of "
    "whole states/provinces of a country, reply {\"type\":\"admin1\",\"items\":[\"Country|Province\",...]}. "
    "If it is made of whole countries, reply {\"type\":\"countries\",\"items\":[\"Country\",...]}. "
    "Otherwise (a city, base, park, island, landmark) reply {\"type\":\"point\",\"lat\":..,\"lon\":..,"
    "\"radius_km\":..} with radius_km roughly the size of the place. If you don't know it, reply "
    "{\"type\":\"unknown\"}. Never guess."
)
_LOCK = threading.Lock()


def _cache_path() -> Path:
    from .render import cache_dir

    return cache_dir() / "ai_places.json"


def cached_resolver(ask: Callable[[str, Optional[str]], Optional[dict]], path: Optional[Path] = None):
    """Wrap ``ask`` so every answer (including "unknown") is stored and reused."""

    def resolve(name: str, parent: Optional[str]) -> Optional[dict]:
        store = path or _cache_path()
        key = f"{(parent or '').strip().lower()}>{name.strip().lower()}"
        with _LOCK:
            try:
                cache = json.loads(store.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                cache = {}
        if key in cache:
            return cache[key]
        answer = ask(name, parent)
        if answer is None:  # transient failure: don't cache, ask again next time
            return None
        with _LOCK:
            try:
                cache = json.loads(store.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                cache = {}
            cache[key] = answer
            store.parent.mkdir(parents=True, exist_ok=True)
            tmp = store.with_suffix(".tmp")
            tmp.write_text(json.dumps(cache, indent=1), encoding="utf-8")
            tmp.replace(store)
        return answer

    return resolve


def gemini_place_resolver(settings=None):
    from visual_director.llm import GeminiLLM, LLMError

    llm = GeminiLLM(settings=settings, timeout=60.0)

    def ask(name: str, parent: Optional[str]) -> Optional[dict]:
        where = f" (inside {parent})" if parent else ""
        try:
            text = llm.complete(_SYSTEM, f"Place: {name}{where}", thinking_level="low", max_output_tokens=2048)
            data = json.loads(text)
        except (LLMError, ValueError):
            return None
        return data if isinstance(data, dict) else None

    return cached_resolver(ask)
