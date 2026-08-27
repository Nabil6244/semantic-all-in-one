"""Build a StockProvider from configured API keys (Pexels, Pixabay, …)."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from .base import StockBackend, StockProvider
from .cache import StockCache
from .openverse import OpenverseBackend
from .pexels import PexelsBackend
from .pixabay import PixabayBackend


def build_stock_provider(
    images_dir: Path,
    *,
    pexels_api_key: str = "",
    pixabay_api_key: str = "",
    include_openverse: bool = True,
) -> Optional[StockProvider]:
    backends: List[StockBackend] = []
    if pexels_api_key.strip():
        backends.append(PexelsBackend(pexels_api_key.strip()))
    if pixabay_api_key.strip():
        backends.append(PixabayBackend(pixabay_api_key.strip()))
    if include_openverse:
        backends.append(OpenverseBackend())
    if not backends:
        return None
    cache = StockCache(used_ids_file=Path(images_dir) / ".stock_used_assets.json")
    return StockProvider(backends=backends, cache=cache)
