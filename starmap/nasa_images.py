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


_MISSION = re.compile(r"\b([A-Z][A-Za-z]+)[ -]?(\d{1,2}|I{1,3}|IV|V|VI{0,3})\b")


def contradicts(query: str, title: str, description: str, date: str = "") -> Optional[str]:
    """Why an item is NOT the picture asked for (None when it may be): it names another mission of the same name (Voyager 2's
    photo for "Voyager 1 ..."), or it lacks most of the named things the description asks for ("Great Red Spot", "Titan").
    The search ranks by shared words, so a caption about Io scored well for "the storms of Jupiter"; this check rejects it."""
    text = f"{title} {description}"
    low = text.lower()
    for name, num in _MISSION.findall(query):
        if name.lower() in STOP or name == "NASA":
            continue
        said = {n.upper() for n in re.findall(rf"\b{re.escape(name)}[ -]?(\d{{1,2}}|[IVX]{{1,4}})\b", text, flags=re.I)}
        if said and num.upper() not in said:
            return f"it is about {name} {'/'.join(sorted(said))}, not {name} {num}"
    # a mission the query names must be named by the item: an Apollo 11 "B roll" with a launch in it stood in for "Voyager 1 launch 1977"
    first = next(((n, num) for n, num in _MISSION.findall(query) if n.lower() not in STOP and n != "NASA"), None)
    if first and not re.search(rf"\b{re.escape(first[0])}", text, flags=re.I):
        return f"it never mentions {first[0]}"
    words = re.findall(r"[A-Za-z][A-Za-z0-9'-]*", query)
    named = [w for i, w in enumerate(words) if i > 0 and w[0].isupper() and w.lower() not in STOP and w != "NASA"]
    have = {_stem(w) for w in _words(low)}
    found = [w for w in named if _stem(w.lower()) in have or w.lower() in low]
    if named and len(found) * 3 < len(named) * 2:
        return f"it does not show {', '.join(w for w in named if w not in found)}"
    # the mission's name is not evidence of what the picture shows: a caption about the Madrid antennas receiving "data from
    # the agency's Voyager 1 spacecraft" won the card for "Voyager 1 spacecraft being prepared before launch in 1977". With the
    # mission's name (and a "spacecraft" / "probe" right after it) taken out, what the description asks to SEE must be in
    # what the item says it shows: its title, or its first sentence when the title is only the mission or a catalogue number
    # a photo of people at an event, unless people are what is asked for: "Suzanne Dodd ... holds a replica of the golden record ... at a
    # news conference" stood in for "Voyager 1 interstellar space 2013"
    opening = _first_sentence(description)
    if _EVENT.search(opening) and not _PEOPLE_ASKED.search(query):
        return "it is a photo of people at an event (a news conference or briefing), not of what is asked for"
    want = _subject(query, query)
    if want:
        shows = _subject(title, query) | _subject(opening, query)
        # a generic word is no evidence: "European Space Agency" in a Huygens touchdown clip matched "Deep Space Network antenna"
        if want - _GENERIC_SUBJECT:
            want, shows = want - _GENERIC_SUBJECT, shows - _GENERIC_SUBJECT
        if not any(_same(w, s) for w in want for s in shows):
            return f"it mentions the mission but does not show {' / '.join(sorted(want))}"
    # an asked-for year (a 1977 launch) and a picture made decades away from it that never mentions that year
    years = {int(y) for y in re.findall(r"\b(19[5-9]\d|20[0-4]\d)\b", query)}
    made = int(date[:4]) if re.match(r"(19|20)\d\d", date or "") else None
    if years and made and all(abs(made - y) > 2 for y in years) and not any(str(y) in text for y in years):
        return f"it was made in {made}, not {'/'.join(map(str, sorted(years)))}"
    return None


# words that name the kind of picture, not its subject
_NOT_SUBJECT = {"image", "photo", "photograph", "picture", "view", "nasa", "being", "before", "after", "during", "while", "shows",
                "showing", "seen", "taken", "by", "as", "it", "this", "that", "his", "her", "their", "one", "two", "first"}
_CRAFT_NOUN = r"(?:\s+(?:spacecraft|space\s+probe|probe|mission|team|project|program))?"


_EVENT = re.compile(r"\b(news conference|press conference|briefing|press event|media day|town hall|speaks|speaking|answers questions|"
                    r"is interviewed|ceremony|award|honou?red|poses|posing|panel discussion)\b", re.I)
_PEOPLE_ASKED = re.compile(r"\b(team|engineers?|scientists?|people|person|crew|astronauts?|press|conference|briefing|portrait|manager|staff|"
                           r"control room|mission control|ceremony|celebrat\w*|react\w*)\b", re.I)

_GENERIC_SUBJECT = {"space", "deep", "outer", "view", "image", "imag", "picture", "photo", "photograph", "shot", "footage", "video", "agency",
                    "mission", "program", "scene", "nasa", "spacecraft", "probe", "craft", "close", "far", "new", "first", "last"}


def _subject(text: str, query: str) -> set:
    """The content words of `text` once the query's missions ("Voyager 1", "Voyager", "Voyager 1 spacecraft"), years and
    catalogue numbers are taken out: what it is a picture OF."""
    t = text or ""
    t = re.sub(r"[\w-]*\d[\w-]*", " ", t)           # catalogue numbers (ARC-1979-A79-7086, PIA00010) are not words
    for name, num in _MISSION.findall(query):
        if name.lower() in STOP or name == "NASA":
            continue
        t = re.sub(rf"\b{re.escape(name)}(?:[ -]?(?:\d{{1,2}}|[IVX]{{1,4}}))?(?:'s)?{_CRAFT_NOUN}\b", " ", t, flags=re.I)
    return {_stem(w) for w in _words(t) if w not in _NOT_SUBJECT and not w.isdigit() and not re.search(r"\d", w) and len(w) >= 2}


def _same(a: str, b: str) -> bool:
    """One word, give or take its ending (prepar / preparation, launch / launched)."""
    return a == b or (min(len(a), len(b)) >= 5 and (a.startswith(b) or b.startswith(a)))


def _first_sentence(description: str) -> str:
    """The opening sentence, past a dateline (as `score` reads it)."""
    parts, first = re.split(r"(?<=\.)\s+", (description or "").strip()), ""
    while parts and len(first) < 60:
        first += " " + parts.pop(0)
    return first


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
        why = contradicts(query, img.title, img.description, img.date)
        if why:
            log(f"[StarMap] NASA image {img.nasa_id} skipped: {why}")
            continue
        url = file_url(img.nasa_id, get=get)
        if not url:
            continue
        r = get(url, headers={"User-Agent": USER_AGENT}, timeout=60)
        r.raise_for_status()
        out = target.with_suffix(".png" if url.lower().endswith(".png") else ".jpg")
        for old in target.parent.glob(f"{target.stem}.*"):     # an earlier run's file for this scene must not be picked up instead
            if old != out and old.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp", ".mp4", ".mov", ".webm"):
                old.unlink(missing_ok=True)
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


def _still_matches(rec: Dict[str, Any], row: Any) -> bool:
    """The shared reuse rule: the stored file was found for this row's description (an edited CSV renumbers its scenes, and
    scene 4's old picture is not the new scene 4's)."""
    from asset_manager import asset_record_matches
    from providers.base import AssetSource

    return asset_record_matches(rec, row, AssetSource.STOCK_IMAGE)


def prefetch(rows: Sequence, nasa_rows: Dict[str, str], images_dir: Path, *, manifest_cls=None, log: Callable[[str], None] = print,
             get: Optional[Callable] = None, cancel_check: Optional[Callable[[], bool]] = None, context: "str | Dict[str, str]" = "",
             unanswered: Optional[Dict[str, str]] = None, no_match: Optional[Dict[str, str]] = None) -> Dict[str, str]:
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
        if rec.get("status") == "complete" and _still_matches(rec, row):
            continue                                            # found before for this same row (a renumbered row's old file is not)
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
            if no_match is not None:                            # a modern stock photo would pass for the mission's own picture
                no_match[n] = "no NASA picture matches it"
                log(f"[StarMap] No NASA image for scene {n} ({want!r}); left out, not replaced by a stock picture")
            else:
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
