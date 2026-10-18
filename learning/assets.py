"""Conservative asset-type vocabulary mapping between the three places the words appear.

* a rule's ``asset_type``  = a provider source key (``providers.base.AssetSource`` value, e.g. ``flow_image``), because that is what
  scene-failure events carry (production ``asset`` events: ``source=result.source.value``);
* a CSV's ``asset_type`` column. Only the *normal* and *overscaled* (incl. Exp Solar) CSVs use the ``SceneRow`` vocabulary, where
  ``video``/``flow_video`` -> flow_video and ``image``/``flow_image`` -> flow_image (providers/base.py ``SceneRow.from_csv_row``);
* every other style (pakMap, Hybrid, StarMap, What If, Weather) has no ``asset_type`` column in its CSV, so a CSV from those styles
  never matches an asset-type rule.

Unknown words map to None and can never trigger a rule. Legacy ``stock`` means "any stock media" and is NOT equal to
``stock_video``/``stock_image``; ``local_*`` is not a provider failure source and maps to ``local``.
"""

from __future__ import annotations

from typing import Iterable, Optional, Set

KNOWN_SOURCES = frozenset({"local", "stock", "stock_image", "stock_video", "flow_image", "flow_video", "youtube_video", "archive_video",
                           "nasa_video", "commons_video", "commons_image", "manual", "research", "map"})
_CSV_ALIASES = {"video": "flow_video", "flow_video": "flow_video", "image": "flow_image", "flow_image": "flow_image",
                "local_video": "local", "local_image": "local"}
_SCENEROW_MODES = ("normal", "overscaled")


def canonical_source(token: object) -> Optional[str]:
    t = str(token or "").strip().lower()
    return t if t in KNOWN_SOURCES else None


def csv_sources(scope: str, asset_types: Iterable[object]) -> Set[str]:
    """Provider source keys an imported CSV's asset_type values stand for, in the style named by ``scope`` (mode/style)."""
    if str(scope).split("/", 1)[0] not in _SCENEROW_MODES:
        return set()
    out: Set[str] = set()
    for a in asset_types:
        t = str(a or "").strip().lower()
        c = _CSV_ALIASES.get(t) or canonical_source(t)
        if c:
            out.add(c)
    return out
