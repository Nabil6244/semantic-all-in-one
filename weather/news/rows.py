"""Small helpers shared by the Weather News layer types: naming the row in a message, fetching the first URL that answers,
and the provenance record of a product."""

from __future__ import annotations

import urllib.error
from typing import Callable, List, Tuple, TypeVar

T = TypeVar("T")


def at(row) -> str:
    return f"weather_layers.csv row {row.line} ({row.id})"


def first_answer(urls: List[str], get: Callable[[str], T], what: str) -> Tuple[str, T]:
    """(url, body) of the first URL that answers; ValueError naming every URL tried when none does (a 404 = not archived)."""
    tried = []
    for u in urls:
        try:
            return u, get(u)
        except urllib.error.HTTPError as exc:
            tried.append(f"{u} (HTTP {exc.code})")
        except (RuntimeError, OSError) as exc:
            tried.append(f"{u} ({exc})")
    raise ValueError(f"{what} could not be fetched: {'; '.join(tried)}")
