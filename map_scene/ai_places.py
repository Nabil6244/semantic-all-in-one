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
        resolve.last_error = None
        store = path or _cache_path()
        key = f"{(parent or '').strip().lower()}>{name.strip().lower()}"
        with _LOCK:
            try:
                cache = json.loads(store.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                cache = {}
        try:
            from production import events as _pevents

            _pevents.emit("cache", cache="map_place", hit=key in cache)
        except Exception:
            pass
        if key in cache:
            return cache[key]
        answer = ask(name, parent)
        if answer is None:  # transient failure: don't cache, ask again next time
            resolve.last_error = getattr(ask, "last_error", None) or "no answer"
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

    resolve.last_error = None
    return resolve


def gemini_place_resolver(settings=None):
    from visual_director.llm import GeminiLLM, LLMError

    llm = GeminiLLM(settings=settings, timeout=60.0)

    def ask(name: str, parent: Optional[str]) -> Optional[dict]:
        where = f" (inside {parent})" if parent else ""
        ask.last_error = None
        try:
            text = llm.complete(_SYSTEM, f"Place: {name}{where}", thinking_level="low", max_output_tokens=2048)
        except LLMError as exc:
            msg = str(exc)
            ask.last_error = ("Gemini quota exceeded" if "quota" in msg.lower() or "429" in msg
                              else f"Gemini error: {msg[:120]}")
            return None
        text = text.strip()
        if text.startswith("```"):  # tolerate a fenced JSON reply
            text = text.strip("`")
            text = text[4:] if text.lower().startswith("json") else text
        try:
            data = json.loads(text)
        except ValueError:
            ask.last_error = "Gemini gave an unreadable answer"
            return None
        return data if isinstance(data, dict) else None

    ask.last_error = None

    return cached_resolver(ask)


# ---- free fallback: OpenStreetMap (no key, no quota) -------------------------------------------------------------
# The built-in data has only countries, states/provinces and US counties; a mountain, base, town or a country
# named in another language ("Líbano") used to need Gemini, so a spent Gemini quota failed the scene. OpenStreetMap's
# Nominatim answers the same question for free. Its policy is respected: one request per second at most (shared with
# boundary_source), an identifying User-Agent, and every answer cached on disk so each place is asked once.

def _osm_cache_path() -> Path:
    from .render import cache_dir

    return cache_dir() / "osm_places.json"


def _osm_answer(item: dict) -> Optional[dict]:
    """One Nominatim result as the resolver's answer: a country or province by its English name (with its point as a
    fallback when the bundled data doesn't know that name either), anything else as a point sized from its box."""
    import math

    try:
        lat, lon = float(item["lat"]), float(item["lon"])
    except (KeyError, TypeError, ValueError):
        return None
    radius = 8.0
    try:
        s, n, w, e = (float(v) for v in item.get("boundingbox") or ())
        half = max((n - s) * 111.0, (e - w) * 111.0 * max(0.2, math.cos(math.radians(lat)))) / 2.0
        radius = min(150.0, max(1.0, half))
    except (TypeError, ValueError):
        pass
    point = {"type": "point", "lat": lat, "lon": lon, "radius_km": round(radius, 1)}
    kind = str(item.get("addresstype") or item.get("type") or "").lower()
    name = str(item.get("name") or "").strip()
    country = str((item.get("address") or {}).get("country") or "").strip()
    if name and kind == "country":
        return dict(point, type="countries", items=[name])
    if name and country and kind in ("state", "province", "region") and name != country:
        return dict(point, type="admin1", items=[f"{country}|{name}"])
    return point


def _osm_pick(items: list, parent: Optional[str]) -> dict:
    """The best of several matches: one inside the wider area when that is known, then the most important
    ("Líbano" alone is Lebanon, not a town of that name in Colombia)."""
    from boundary_source import fold

    if parent:
        inside = [it for it in items if fold(str((it.get("address") or {}).get("country") or "")) == fold(parent)]
        items = inside or items

    def importance(it: dict) -> float:
        try:
            return float(it.get("importance") or 0.0)
        except (TypeError, ValueError):
            return 0.0

    return max(items, key=importance)


def osm_place_resolver(fetch: Optional[Callable[[dict], list]] = None, path: Optional[Path] = None,
                       sleep: Callable[[float], None] = None):
    """Free place lookup through OpenStreetMap (Nominatim), cached like the Gemini one."""
    import time

    sleep = sleep or time.sleep

    def ask(name: str, parent: Optional[str]) -> Optional[dict]:
        ask.last_error = None
        try:
            import boundary_source as bs
        except Exception as exc:  # pragma: no cover - the module ships with the app
            ask.last_error = f"OpenStreetMap lookup unavailable ({type(exc).__name__})"
            return None
        get = fetch or bs._http_fetch
        # With the wider area first ("Monte Hermón, Lebanon"); OpenStreetMap often has no match for that pair
        # (the peak sits on a border, or its name there is another language), so then the name alone.
        queries = [", ".join((name, parent)), name] if parent else [name]
        items = []
        for q in queries:
            with bs._lock:
                wait = 1.1 - (time.time() - bs._last_request[0])
                if wait > 0:
                    sleep(wait)
                bs._last_request[0] = time.time()
            try:
                items = get({"q": q, "format": "jsonv2", "limit": "5", "addressdetails": "1", "accept-language": "en"}) or []
            except Exception as exc:  # offline or blocked: not cached, asked again next time
                ask.last_error = f"OpenStreetMap could not be reached ({type(exc).__name__})"
                return None
            if items:
                break
        answer = _osm_answer(_osm_pick(items, parent)) if items else None
        return answer or {"type": "unknown"}

    ask.last_error = None
    return cached_resolver(ask, path or _osm_cache_path())


def place_resolver(settings=None, *, osm=None, gemini="auto"):
    """The map's place lookup: OpenStreetMap first (free), then Gemini only when a key is set. ``last_error``
    names what went wrong when neither found the place."""
    if osm is None:
        osm = osm_place_resolver()
    if gemini == "auto":
        gemini = None
        try:
            from visual_director.llm import gemini_configured

            if gemini_configured(settings):
                gemini = gemini_place_resolver(settings)
        except Exception:
            gemini = None

    def resolve(name: str, parent: Optional[str]) -> Optional[dict]:
        errors = []
        for source in (osm, gemini):
            if source is None:
                continue
            try:
                answer = source(name, parent)
            except Exception as exc:
                answer = None
                source.last_error = f"{type(exc).__name__}"
            if isinstance(answer, dict) and answer.get("type") not in (None, "unknown"):
                resolve.last_error = None
                return answer
            if getattr(source, "last_error", None):
                errors.append(source.last_error)
        resolve.last_error = "; ".join(errors) or None
        return None

    resolve.last_error = None
    return resolve
