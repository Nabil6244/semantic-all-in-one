"""Weather layer types beyond the phase-1 six, one module each in this package, found automatically.

A module registers its types with register(LayerType(...)) at import time. Everything that reads weather_layers.csv (sidecar),
fetches data (resolve.prepare), checks freshness (resolve.check_fresh) and builds what the engine draws (events.build) asks this
registry about any type it does not know itself, so a new layer type is ONE new file here (plus, for its graphics, one file in
weather-engine/lib/layers/). The contract is in docs/weather/integration_contract.md.

The hooks:
  check(row)                         -> raise ValueError for a row whose place/data_source/extra do not fit (named by the sidecar)
  fetch(row, ctx)                    -> put this row's data into ctx.snap.extra[<key>] (fetch each product once: look first)
  fresh(snap, now)                   -> problems (strings) that make the snapshot too old to render; [] when fine
  build(row, snap, window, out)      -> append to out (a weather.events.WeatherPayload): out.events (engine graphics), out.fills (pakMap
                                        fill events), out.rasters (timed tile layers: radar/satellite loops), out.credits, and
                                        out.report.add(...) for EVERY number shown"""

from __future__ import annotations

import importlib
import pkgutil
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple


@dataclass
class FetchContext:
    snap: Any  # weather.resolve.Snapshot
    now: datetime
    nws: Any = None  # weather.nws.NwsClient (or None when no NWS product is needed)
    get_text: Optional[Callable[[str], str]] = None  # cached GET for other public sources (weather.layers.http_text by default)
    get_bytes: Optional[Callable[[str], bytes]] = None


@dataclass
class LayerType:
    name: str
    products: Sequence[Tuple[str, str]]  # accepted (provider, product) of data_source; () = takes no data_source
    extra_keys: frozenset = frozenset()
    fetch: Optional[Callable[[Any, FetchContext], None]] = None
    build: Optional[Callable[[Any, Any, Any, Any], None]] = None
    check: Optional[Callable[[Any], None]] = None
    fresh: Optional[Callable[[Any, datetime], List[str]]] = None
    needs_place: bool = False
    about: str = ""


REGISTRY: Dict[str, LayerType] = {}
_FRESH: List[Callable[[Any, datetime], List[str]]] = []
_loaded = False


def register(lt: LayerType) -> LayerType:
    if lt.name in REGISTRY and REGISTRY[lt.name] is not lt:
        raise ValueError(f"weather layer type {lt.name!r} is registered twice")
    REGISTRY[lt.name] = lt
    return lt


def register_fresh(fn: Callable[[Any, datetime], List[str]]) -> None:
    """A freshness rule for a product that is not tied to one layer type."""
    if fn not in _FRESH:
        _FRESH.append(fn)


def discover() -> Dict[str, LayerType]:
    """Import every module of this package once (each registers its types)."""
    global _loaded
    if not _loaded:
        _loaded = True
        for m in sorted(pkgutil.iter_modules(__path__), key=lambda m: m.name):
            if not m.name.startswith("_"):
                importlib.import_module(f"{__name__}.{m.name}")
    return REGISTRY


def get(name: str) -> Optional[LayerType]:
    return discover().get(name)


def fresh_problems(snap, now: datetime) -> List[str]:
    out: List[str] = []
    for lt in discover().values():
        if lt.fresh is not None:
            out += lt.fresh(snap, now)
    for fn in _FRESH:
        out += fn(snap, now)
    return out


# ---- a cached GET for public sources other than the NWS API ---------------------------------------------------------------------

UA = "SemanticYTStudio-Weather/1.0"


def http_bytes(url: str, *, max_age_s: float = 6 * 3600.0, timeout: float = 60.0) -> bytes:
    """GET through Weather's own HTTP cache (a public archive answer rarely changes: 6 h by default). Raises on HTTP errors."""
    import urllib.error
    import urllib.request
    from datetime import timezone

    from ..cache import HttpCache, Response

    cache = HttpCache()
    hit = cache.get(url)
    if hit is not None:
        return hit.body
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    last = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = r.read()
                cache.put(url, Response(r.status, body, {}, datetime.now(timezone.utc)), max_age_s)
                return body
        except urllib.error.HTTPError as exc:
            if exc.code < 500 and exc.code != 429:
                raise
            last = exc
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            last = exc
        import time

        time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"{url} could not be fetched ({last})")


def http_text(url: str, **kw: Any) -> str:
    return http_bytes(url, **kw).decode("utf-8", "replace")


@dataclass
class Frame:
    """One picture of a timed tile layer (a radar or satellite loop): shown from `at` seconds into the layer."""
    at: float
    provider: Dict[str, Any]  # {id, title, urlTemplate, format, tileSize, maxNativeZoom}
    label: str = ""  # e.g. "4:35 PM CDT" (the clock the engine shows with the loop)


@dataclass
class Raster:
    """A timed tile layer for weather-engine (spec.weather.rasters): frames step (or cross-fade) through the layer's window."""
    id: str
    t_in: float
    t_out: float
    frames: List[Frame] = field(default_factory=list)
    opacity: float = 0.85
    crossfade_s: float = 0.0
    above_fills: bool = False  # radar sits above region fills; satellite pictures below them
    clock: bool = True  # show the frame's label (its time) in a corner chip

    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "t_in": self.t_in, "t_out": self.t_out, "opacity": self.opacity, "crossfade_s": self.crossfade_s,
                "above_fills": self.above_fills, "clock": self.clock,
                "frames": [{"at": f.at, "provider": f.provider, "label": f.label} for f in self.frames]}
