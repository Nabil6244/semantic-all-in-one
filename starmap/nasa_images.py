"""NASA photographs for StarMap's `nasa_image:` assets, from the NASA Image and Video Library (images.nasa.gov, public API,
no key). NASA material is not copyrighted; NASA asks for credit and that its insignia not imply endorsement.

A `nasa_image:` row is shown in the app's Visual Plan as a stock_image row (so Retry / Change source / Skip / Local clip work
unchanged). Before the shared resolver runs, StarMap looks the description up here and, when NASA has a good match, saves it as
that scene's file with a complete manifest record (source "nasa_image"); the shared reuse rule then keeps it. If NASA has
nothing, the row goes on to the stock search like any other. A row the user changed or replaced in the table is left alone.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

SEARCH_URL = "https://images-api.nasa.gov/search"
ASSET_URL = "https://images-api.nasa.gov/asset/{nasa_id}"
DETAILS_URL = "https://images.nasa.gov/details/{nasa_id}"
USER_AGENT = "SemanticYTStudio-StarMap/1.0"
PREFERRED = ("~large.jpg", "~orig.jpg", "~medium.jpg", "~large.png", "~orig.png")
STOP = {"the", "a", "an", "of", "on", "in", "at", "to", "with", "and", "from", "its", "is", "over", "above", "for"}


@dataclass
class NasaImage:
    nasa_id: str
    title: str
    description: str = ""
    center: str = ""
    date: str = ""
    score: float = 0.0

    @property
    def credit(self) -> str:
        return f"NASA{'/' + self.center if self.center else ''} ({self.nasa_id})"

    @property
    def url(self) -> str:
        return DETAILS_URL.format(nasa_id=self.nasa_id)


def _stem(w: str) -> str:
    for suffix in ("ing", "ed", "es", "s"):
        if len(w) > len(suffix) + 3 and w.endswith(suffix):
            return w[: -len(suffix)]
    return w


def _words(text: str) -> List[str]:
    return [w for w in re.findall(r"[a-z0-9]+", (text or "").lower()) if w not in STOP]


def score(query: str, title: str, description: str) -> float:
    """How well an item covers the description: its title and FIRST sentence (what the picture shows) count most; the rest of
    NASA's caption (often background: who was where, what happened next) counts little."""
    q = {_stem(w) for w in _words(query)}
    if not q:
        return 0.0
    # the opening sentence, past a dateline ("KENNEDY SPACE CENTER, FLA. -- The Saturn V lifts off ...")
    parts, first = re.split(r"(?<=\.)\s+", (description or "").strip()), ""
    while parts and len(first) < 60:
        first += " " + parts.pop(0)
    shows = {_stem(w) for w in _words(title + " " + first)}
    rest = {_stem(w) for w in _words(" ".join(parts))}
    return (2 * len(q & shows) + 0.5 * len((q & rest) - shows)) / (2 * len(q))


def queries(description: str) -> List[str]:
    """NASA's search wants every word to match, so a long description finds nothing: try it whole, then its key words, then fewer."""
    keys = _words(description)
    out = [description.strip()]
    for n in (len(keys), 4, 3, 2):
        q = " ".join(keys[:n])
        if q and q not in out:
            out.append(q)
    return out


RETRY_WAITS = (2.0, 5.0, 10.0)      # seconds before the 2nd, 3rd and 4th try
_BUSY = (429, 500, 502, 503, 504)


def patient(get: Callable) -> Callable:
    """`get` that tries again when NASA's server drops the connection, times out or says it is busy (it resets connections
    under load): without this, one dropped request sent the row to the stock search and a modern stock photo stood in for
    a historical NASA picture. Other errors (a fake `get` in a test, a 404) come back at once."""
    if getattr(get, "_patient", False):
        return get

    def call(*args, **kwargs):
        import requests

        for i in range(len(RETRY_WAITS) + 1):
            last = i == len(RETRY_WAITS)
            try:
                r = get(*args, **kwargs)
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
                if last:
                    raise
            else:
                if last or getattr(r, "status_code", 200) not in _BUSY:
                    return r
            time.sleep(RETRY_WAITS[i])

    call._patient = True
    return call


def _default_get(get: Optional[Callable]) -> Callable:
    if get is None:
        import requests

        get = requests.get
    return patient(get)


def search(query: str, *, limit: int = 20, get: Optional[Callable] = None, context: str = "") -> List[NasaImage]:
    """Best matches first (scored against the full description; an item naming the story's mission, `context` such as
    "Apollo 11", ranks above one from another mission). `get` is requests.get (injectable for tests)."""
    get = _default_get(get)
    items: list = []
    for q in queries(query):
        r = get(SEARCH_URL, params={"q": q, "media_type": "image", "page_size": limit}, headers={"User-Agent": USER_AGENT}, timeout=20)
        r.raise_for_status()
        items = (r.json().get("collection") or {}).get("items", [])
        if items:
            break
    out = []
    for item in items[:limit]:
        data = (item.get("data") or [{}])[0]
        if not data.get("nasa_id"):
            continue
        img = NasaImage(data["nasa_id"], data.get("title", ""), data.get("description", "")[:2000], data.get("center", ""),
                        (data.get("date_created") or "")[:10])
        img.score = score(query, img.title, img.description)
        if context and context.lower() in f"{img.title} {img.description}".lower():
            img.score += 0.16                     # the story's own mission wins a close call, never a clearly better match
        out.append(img)
    return sorted(out, key=lambda i: -i.score)


def file_url(nasa_id: str, *, get: Optional[Callable] = None) -> Optional[str]:
    """The best-sized JPEG/PNG of an item (large, else original, else medium)."""
    get = _default_get(get)
    r = get(ASSET_URL.format(nasa_id=nasa_id), headers={"User-Agent": USER_AGENT}, timeout=20)
    r.raise_for_status()
    hrefs = [i.get("href", "") for i in (r.json().get("collection") or {}).get("items", [])]
    for suffix in PREFERRED:
        hit = next((h for h in hrefs if h.lower().endswith(suffix)), None)
        if hit:
            return hit.replace("http://", "https://", 1)
    return None


def fetch(query: str, target: Path, *, min_score: float = 0.4, min_width: int = 800, get: Optional[Callable] = None,
          log: Callable[[str], None] = print, context: str = "") -> Optional[NasaImage]:
    """Find and download the best NASA image for `query` to `target` (its suffix is set from the file). None if nothing fits."""
    get = _default_get(get)
    for img in search(query, get=get, context=context)[:5]:
        if img.score < min_score:
            break
        url = file_url(img.nasa_id, get=get)
        if not url:
            continue
        r = get(url, headers={"User-Agent": USER_AGENT}, timeout=60)
        r.raise_for_status()
        out = target.with_suffix(".png" if url.lower().endswith(".png") else ".jpg")
        out.write_bytes(r.content)
        try:
            from PIL import Image

            with Image.open(out) as im:
                if im.width < min_width:
                    log(f"[StarMap] NASA image {img.nasa_id} is only {im.width}px wide; trying the next match")
                    out.unlink(missing_ok=True)
                    continue
        except Exception:
            out.unlink(missing_ok=True)
            continue
        return img
    return None


def prefetch(rows: Sequence, nasa_rows: Dict[str, str], images_dir: Path, *, manifest_cls=None, log: Callable[[str], None] = print,
             get: Optional[Callable] = None, cancel_check: Optional[Callable[[], bool]] = None, context: "str | Dict[str, str]" = "",
             unanswered: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """For each Visual Plan row that is still StarMap's own nasa_image row (scene number -> its description, unchanged by the
    user) and has no finished file yet, try NASA first. Returns {scene number: credit} for the ones found. A row NASA's
    server never answered for (after `patient`'s retries) goes into `unanswered` (scene number -> why): the caller must not
    send it to the stock search, where a modern stock photo would stand in for a historical NASA picture."""
    if manifest_cls is None:
        from asset_manager import AssetManifest as manifest_cls
    images_dir = Path(images_dir)
    images_dir.mkdir(parents=True, exist_ok=True)
    found: Dict[str, str] = {}
    for row in rows:
        n = str(row.scene_number)
        want = nasa_rows.get(n)
        if want is None or (getattr(row, "asset_type", "") or "").lower() != "stock_image" or " ".join((row.prompt or row.stock or "").split()) != " ".join(want.split()):
            continue                                            # not ours any more: the user changed its source or text
        if cancel_check is not None and cancel_check():
            break
        rec = manifest_cls(images_dir).get(n) or {}
        if rec.get("status") == "complete":
            continue
        try:
            img = fetch(want, images_dir / f"{int(n):03d}", get=get, log=log, context=context.get(n, "") if isinstance(context, dict) else context)
        except Exception as exc:
            if unanswered is not None:
                unanswered[n] = str(exc)
                log(f"[StarMap] NASA's image library did not answer for scene {n} ({exc}); not replaced by a stock picture")
            else:
                log(f"[StarMap] NASA image search failed for scene {n} ({exc}); it goes to the stock search")
            continue
        if img is None:
            log(f"[StarMap] No NASA image for scene {n} ({want!r}); it goes to the stock search")
            continue
        path = next(images_dir.glob(f"{int(n):03d}.*"))
        manifest_cls(images_dir).set(n, {
            "source": "nasa_image", "asset_type": "stock_image", "type": "image", "prompt": row.prompt, "stock_query": row.stock,
            "script_segment": getattr(row, "script_segment", ""), "local_path": str(path), "status": "complete", "resolved_at": time.time(),
            "error": None, "provider_asset_id": img.nasa_id, "author": "NASA", "source_url": img.url, "credit": img.credit, "title": img.title})
        found[n] = img.credit
        log(f"[StarMap] Scene {n}: NASA image {img.nasa_id} ({img.title[:60]})")
    return found
