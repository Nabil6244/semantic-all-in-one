"""Real footage for the sentences the scene-writer marked as footage: a stock search (Pexels, then Pixabay) per query, the best landscape clip of a usable
length is downloaded into the film's folder and set as `path` on its item. A sentence whose search finds nothing keeps no path, and the planner draws a
3D shot there instead, so the film never stops on a missing clip.

    resolve_footage(parsed, out_dir, settings, log, backends=None) -> {"found": n, "missing": n}
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

MIN_S, MAX_S = 4.0, 40.0


def _backends(settings: Dict[str, Any]) -> List[Any]:
    out: List[Any] = []
    try:
        from providers.stock.pexels import PexelsBackend
        from providers.stock.pixabay import PixabayBackend

        if str(settings.get("pexels_api_key") or "").strip():
            out.append(PexelsBackend(str(settings["pexels_api_key"]).strip()))
        if str(settings.get("pixabay_api_key") or "").strip():
            out.append(PixabayBackend(str(settings["pixabay_api_key"]).strip()))
    except Exception:  # noqa: BLE001
        pass
    return out


def _usable(c: Any, used: set) -> bool:
    d = getattr(c, "duration", None)
    return getattr(c, "asset_id", None) not in used and getattr(c, "width", 0) >= getattr(c, "height", 0) and (d is None or MIN_S <= float(d) <= MAX_S)


def resolve_footage(parsed: Dict[str, Any], out_dir: Any, settings: Dict[str, Any], log: Callable[[str], None] = print, backends: Optional[List[Any]] = None,
                    download: Optional[Callable[..., Path]] = None) -> Dict[str, int]:
    from providers.stock.downloader import download_candidate

    dl = download or download_candidate
    bks = backends if backends is not None else _backends(settings)
    d = Path(out_dir) / "footage"
    d.mkdir(parents=True, exist_ok=True)
    used: set = set()
    found = missing = 0
    n = 0
    for ch in parsed["chapters"]:
        for it in ch["items"]:
            if it.get("kind") != "footage" or it.get("path"):
                continue
            n += 1
            cand = None
            for b in bks:
                try:
                    hits = [c for c in b.search(it["query"], "video", 15) if _usable(c, used)]
                except Exception as exc:  # noqa: BLE001
                    log(f"footage search '{it['query']}' failed on {type(b).__name__}: {type(exc).__name__}")
                    continue
                if hits:
                    cand = hits[0]
                    break
            if cand is None:
                missing += 1
                log(f"no footage found for '{it['query']}'")
                continue
            try:
                it["path"] = str(dl(cand, d, str(n), log=log))
                used.add(cand.asset_id)
                found += 1
                log(f"footage {n}: '{it['query']}' -> {cand.provider} {cand.asset_id}")
            except Exception as exc:  # noqa: BLE001
                missing += 1
                log(f"footage '{it['query']}' could not be downloaded ({type(exc).__name__})")
    return {"found": found, "missing": missing}
