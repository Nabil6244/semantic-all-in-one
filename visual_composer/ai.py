"""The AI author for scenes: off unless settings.json has "scene_ai_author": true and a provider key is configured. One short call per picture shot the
rules cannot read (answers are cached by the router), at most MAX_CALLS per video."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Callable, Optional

MAX_CALLS = 14
_SETTINGS = Path(__file__).resolve().parent.parent / "settings.json"


@lru_cache(maxsize=1)
def author_from_settings() -> Optional[Callable[[str, str], str]]:
    try:
        s = json.loads(_SETTINGS.read_text(encoding="utf-8")) if _SETTINGS.is_file() else {}
        if not s.get("scene_ai_author"):
            return None
        from ai_router import providers_configured, router_from_settings

        if not any(providers_configured(s).values()):
            return None
        router = router_from_settings(s)
    except Exception:
        return None

    def run(system: str, user: str) -> str:
        return router.run_task("utility", system, user, label="scene")

    return run
