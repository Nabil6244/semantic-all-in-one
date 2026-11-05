"""Photo cards for Voxel Map: which pictures a film asks for, how they are fetched, and the story CSV the renderer reads.

  requests(csv)                  every card the film wants: the CSV's own `card` rows, or (when it has none) cards planned from the narration
  table_rows(reqs)               the Visuals-tab rows (providers.base.SceneRow), one per card that needs a search
  fetch(reqs, manager, dir, ..)  fetches the pictures through the app's AssetManager (stock / Wikimedia via Openverse); no Gemini, ever
  write_story(csv, out, reqs, paths)   the story CSV the renderer reads: the original rows plus one `card` row per card that has a picture
  credits(reqs, records)         attribution lines for the pictures actually used

CSV wins: a story that carries any `card` row is used as written, nothing is added to it. Only a story with none gets planned cards.
A card whose picture cannot be fetched is dropped; nothing here ever stops a render. Pure Python (stdlib) apart from table_rows / fetch."""
from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path
from typing import Callable, Dict, List, Optional

IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp")
CARD_GAP_S = 12.0        # at most one planned card per this many seconds of film
LONG_BEAT_S = 15.0       # a scene longer than this always gets a card
MIN_BEAT_S = 6.0         # a shorter scene gets none
SECOND_CARD_S = 30.0     # a scene this long may carry two
DEFAULT_WPM = 140.0

_SKIP = set("""the a an and but or so then they their there this that these those he she it his her its we our you your i in on at by for of to from with
after before during while when as if because since until once soon later now today yesterday however meanwhile finally first second third next many most some
every each all both no not only also even still just one two three four five six seven eight nine ten monday tuesday wednesday thursday friday saturday sunday
january february march april may june july august september october november december what who why how where which bc ad bce ce above around across under over between beyond among against within without""".split())
_CAP = re.compile(r"[A-Z][\w'’.-]*(?:\s+(?:of|the|and|de|von|van|al|bin|ibn)\s+[A-Z][\w'’.-]*|\s+[A-Z][\w'’.-]*)*")


def _words(s: str) -> int:
    return len(re.findall(r"\w+", s or ""))


def _extra(row: dict) -> dict:
    try:
        return json.loads(row.get("extra") or "{}") or {}
    except ValueError:
        return {}


def read_rows(csv_path: str):
    text = Path(csv_path).read_text(encoding="utf-8-sig")
    rd = csv.DictReader(io.StringIO(text))
    return list(rd), list(rd.fieldnames or [])


def _num(v):
    try:
        return float(v) if str(v).strip() != "" else None
    except ValueError:
        return None


def beat_seconds(row: dict, wpm: float) -> float:
    return _words(row.get("text", "")) / max(60.0, wpm) * 60.0 + (_num(row.get("gap")) or 0.0)


def _subjects(sentence: str, known: Optional[set] = None) -> List[str]:
    """Named things in a sentence, best first: longer names before single words; sentence-opening function words and months are not names."""
    out: List[str] = []
    for m in _CAP.finditer(sentence):
        parts = re.sub(r"['’]s\b", "", m.group(0)).strip(" .,'’-").split()
        while parts and parts[0].lower() in _SKIP:
            parts.pop(0)
        while parts and parts[-1].lower() in _SKIP:
            parts.pop()
        name = " ".join(parts)
        if len(name) < 4 or name.lower() in _SKIP:
            continue
        if known is not None and " " not in name and m.start() == 0 and name.lower() not in known:
            continue        # a lone capital opening a sentence ("Archaeology shows", "Around 390") is a name only if it is capitalised mid-sentence somewhere too
        out.extend(n for n in re.split(r"\s+and\s+", name) if len(n) >= 4)      # "Crassus and Caesar" is two names
    return list(dict.fromkeys(out))      # the order of the sentence: its subject usually comes first


_TITLES = r"(?:general|emperor|king|queen|consul|dictator|senator|chieftain|sultan|pharaoh|prince|pope|admiral|commander|named|called|leader|tribune|saint|bishop|tsar|president|marshal|lord)"
_PLACE_WORDS = {"hill", "hills", "river", "sea", "ocean", "alps", "mountain", "mountains", "wall", "forum", "island", "islands", "gulf", "bay", "strait", "lake", "valley", "desert", "peninsula", "coast"}
_EVENT_WORDS = {"battle", "war", "wars", "siege", "sack", "treaty", "fire", "plague", "revolt", "rebellion", "conquest", "crossing", "fall", "revolution", "invasion", "massacre", "pax", "triumvirate"}
_CITY_CUE = r"\s*,?\s*(?:is\s+|was\s+)?(?:a|an)\s+(?:[a-z]+\s+){0,2}(?:city|port|town|province|capital|colony|stronghold|fortress)"


def classify(name: str, sentence: str) -> str:
    """person | place | event | thing, from the name's own words and the words around it in the sentence."""
    words = {w.lower() for w in name.split()}
    if words & _EVENT_WORDS:
        return "event"
    if words & _PLACE_WORDS:
        return "place"
    esc = re.escape(name)
    if re.search(rf"\b{_TITLES}\s+(?:[A-Z]\w+\s+)?{esc}", sentence, re.IGNORECASE) or re.search(rf"{esc}\s*(?:,\s*)?(?:the\s+)?(?:consul|general|emperor|king|sultan|dictator|chieftain)\b", sentence, re.IGNORECASE):
        return "person"
    if re.search(esc + _CITY_CUE, sentence):
        return "place"
    return "thing"


def query_for(name: str, kind: str, context: str = "") -> str:
    """The search that finds a good picture of it. Openverse is full of snapshots; a descriptor steers it to portraits, paintings and ruins.
    The stock search drops trailing words when a query finds nothing, so the descriptor is the first thing to go and the name always survives."""
    if kind == "person":
        return f"{name} portrait painting"
    if kind == "event":
        return f"{name} painting"
    if kind == "place":
        return f"{name} ruins" if not set(name.lower().split()) & _PLACE_WORDS else f"{name} landscape"
    ctx = f"{name} {context}" if context and " " not in name and context.lower() not in name.lower() else name
    return f"{ctx} painting"      # history on a free-image site: paintings and engravings beat modern snapshots (and board-game boxes)


def plan_auto(rows: List[dict]) -> List[dict]:
    """Cards planned from the narration (no AI): one named thing per card, no more than one per CARD_GAP_S of film, none on the globe opening or
    on very short scenes, and at least one in any long scene. Returns [{beat, label, query, words, kind, source}]."""
    plan = next((r for r in rows if r.get("row") == "plan"), {})
    wpm = float(_extra(plan).get("wpm") or DEFAULT_WPM)
    known = set()
    for r in rows:
        if r.get("row") == "beat":
            for sent in re.findall(r"[^.!?]+[.!?]*", r.get("text", "")):
                for m in _CAP.finditer(sent):
                    if m.start() > 0:
                        known.update(w.lower() for w in re.sub(r"['’]s\b", "", m.group(0)).split())
    context = (plan.get("id") or "").strip()
    clock, last, used, out, nth = 0.0, -1e9, set(), [], 0
    for r in rows:
        if r.get("row") != "beat":
            continue
        nth += 1
        bid = r.get("id") or f"b{nth}"      # the engine names an id-less beat b<its number>
        secs = beat_seconds(r, wpm)
        start, clock = clock, clock + secs
        if (r.get("rung") or "map") == "globe" or secs < MIN_BEAT_S:
            continue
        sentences = re.findall(r"[^.!?]+[.!?]*", r.get("text", ""))
        want = 2 if secs >= SECOND_CARD_S else 1
        made = 0
        for s in sentences:
            if made >= want or (made == 0 and start - last < CARD_GAP_S and secs < LONG_BEAT_S):
                break
            for name in _subjects(s, known):
                key = name.lower()
                if key in used or key == (r.get("place") or "").lower() or key == context.lower():
                    continue
                if re.search(re.escape(name) + r"\s+" + _TITLES + r"\b", s, re.IGNORECASE):
                    continue        # "Ottoman sultan", "Gallic chieftain": an adjective in front of the title; the person is named after it
                used.add(key)
                kind = classify(name, s)
                query = query_for(name, kind, context)
                out.append({"beat": bid, "label": name, "query": query, "words": s.strip(), "kind": {"person": "portrait", "event": "painting"}.get(kind, "photo"), "source": "auto"})
                made += 1
                last = start + secs * (made / (want + 1))
                break
    return out


def requests(csv_path: str) -> List[dict]:
    """Every card the film wants, numbered 1..n (the Visuals-tab scene numbers): [{n, beat, label, query, local, words, lon, lat, kind, hold, t, anchor, source}].
    `local` is a picture file named by the CSV (kept as is); `query` is a search to fetch."""
    rows, _ = read_rows(csv_path)
    base = Path(csv_path).resolve().parent
    cards = []
    for r in rows:
        if r.get("row") != "card":
            continue
        x = _extra(r)
        asset = str(x.get("asset") or "").strip()
        local = ""
        if asset.lower().endswith(IMAGE_EXT):
            for p in ([Path(asset)] if Path(asset).is_absolute() else [base / asset, base / "cards" / asset]):
                if p.is_file():
                    local = str(p)
                    break
        cards.append({"beat": r.get("id", ""), "label": r.get("text", ""), "query": "" if asset.lower().endswith(IMAGE_EXT) else asset, "local": local,
                      "asset": asset, "words": x.get("words", ""), "lon": _num(r.get("lon")), "lat": _num(r.get("lat")), "kind": x.get("kind", "photo"),
                      "hold": x.get("hold"), "t": x.get("t"), "anchor": x.get("anchor", ""), "source": "csv"})
    if not cards:
        cards = [dict(c, local="", asset=c["query"], lon=None, lat=None, hold=None, t=None, anchor="") for c in plan_auto(rows)]
    for i, c in enumerate(cards, 1):
        c["n"] = i
    return cards


def table_rows(reqs: List[dict]) -> list:
    """The Visuals-tab rows: one per card that has a search (a picture the CSV names as a file is not searched)."""
    from providers.base import SceneRow

    return [SceneRow.from_csv_row({"scene_number": str(c["n"]), "script_segment": c.get("words") or c.get("label") or "", "asset_type": "commons_image",
                                   "prompt": c["query"]}) for c in reqs if c.get("query") and not c.get("local")]


WIKI_API = "https://en.wikipedia.org/w"
UA = {"User-Agent": "VideoGenerator/1.0 (photo cards; local app)"}


def _tok(x: str) -> set:
    return {w for w in re.findall(r"[a-z0-9]+", (x or "").lower()) if len(w) > 2}


_NOT_THE_SUBJECT = re.compile(r"^(curia|baths?|war|battle|siege|sack|end|fall|assassination|death|temple|tomb|villa|palace|list|history|legacy|family|dynasty|reign|rise|cultural|depictions?|in popular)\b", re.IGNORECASE)


def _hit_rank(title: str, label: str, person: bool) -> int:
    """0 = the article about the name itself, 1 = fine, 2 = an article merely mentioning it (\"Curia of Pompey\", \"Baths of Diocletian\")."""
    t, l = title.lower(), label.lower()
    if person and (t == l or t.startswith(l + " ") or t.endswith(" " + l)):
        return 0
    if _NOT_THE_SUBJECT.match(title) and not _NOT_THE_SUBJECT.match(label):
        return 2
    return 1


def wiki_picture(label: str, query: str, get=None, cancel: Optional[Callable] = None) -> Optional[dict]:
    """The lead picture of the Wikipedia article that is about `label` (a free-licence Wikimedia Commons file only): {url, title, page}.
    A named person, place or event nearly always has one, and it is the right one; free-image sites return snapshots and doodles for the same
    name. Returns None when no article matches the name or its picture is not on Commons. `get(url, params)` -> parsed JSON (tests pass a fake)."""
    if get is None:
        import requests

        def get(url, params):
            import time

            for attempt in range(4):      # Wikipedia answers a burst of searches with 429; wait and ask again
                if cancel and cancel():
                    return {}
                r = requests.get(url, params=params, headers=UA, timeout=20)
                if r.status_code in (429, 500, 502, 503) and attempt < 3:
                    until = time.monotonic() + (float(r.headers.get("Retry-After") or 0) or 1.5 * (attempt + 1))
                    while time.monotonic() < until and not (cancel and cancel()):      # its wait can be a minute: Stop must not sit through it
                        time.sleep(min(0.3, max(0.0, until - time.monotonic())))
                    continue
                r.raise_for_status()
                return r.json()
    person = bool(re.search(r"\bportrait\b", query))
    base = re.sub(r"\s+(painting|portrait|ruins|landscape)$", "", query.strip())
    want = _tok(label)
    for q in dict.fromkeys([base, label]):
        try:
            hits = (get(f"{WIKI_API}/rest.php/v1/search/page", {"q": q, "limit": 4}) or {}).get("pages") or []
        except Exception:
            continue
        hits = sorted(hits, key=lambda h: _hit_rank(h.get("title") or "", label, person))      # stable: Wikipedia's own order within a rank
        for h in hits:
            title = h.get("title") or ""
            if not want & (_tok(title) | _tok(h.get("description") or "")) or _hit_rank(title, label, person) == 2:
                continue        # not about the name, or only an article that mentions it (a missing card beats a wrong one)
            if "disambiguation" in (h.get("description") or "").lower():
                continue
            try:
                d = get(f"{WIKI_API}/api.php", {"action": "query", "prop": "pageimages", "piprop": "thumbnail", "pithumbsize": 1280, "titles": title,
                                              "redirects": 1, "format": "json", "formatversion": 2})
            except Exception:
                continue
            for pg in (d.get("query") or {}).get("pages") or []:
                th = pg.get("thumbnail") or {}
                url = th.get("source") or ""
                if "/wikipedia/commons/" in url and not re.search(r"\.(svg|gif)(\.|$)", url, re.IGNORECASE):
                    return {"url": url, "title": pg.get("title") or title, "page": "https://en.wikipedia.org/wiki/" + (pg.get("title") or title).replace(" ", "_")}
    return None


def seed_from_wikipedia(reqs: List[dict], images_dir: Path, log: Callable = lambda m: None, get=None, download=None,
                        cancel: Optional[Callable] = None, progress: Optional[Callable] = None, on_picture: Optional[Callable] = None) -> int:
    """Files a Wikipedia lead picture as the finished asset of every search card the Visuals table does not hold a picture for yet. Returns how many.
    Reports each card it reaches and stops at Stop; pictures already filed are kept, so the next Generate carries on after them.
    on_picture() is called after each one is filed, so the Visuals tab can show it right away."""
    import visual_bridge
    from asset_manager import AssetManifest

    if download is None:
        import requests

        def download(url):
            r = requests.get(url, headers=UA, timeout=40)
            r.raise_for_status()
            return r.content
    images_dir = Path(images_dir)
    images_dir.mkdir(parents=True, exist_ok=True)
    man = AssetManifest(images_dir)
    got = 0
    searches = [c for c in reqs if c.get("query") and not c.get("local")]
    for i, c in enumerate(searches, start=1):
        if man.get(str(c["n"])):
            continue
        if cancel and cancel():
            break
        msg = f"Finding card pictures on Wikipedia {i}/{len(searches)}"
        log(msg)      # a line per card: Wikipedia can slow this to a few a minute, and the log must show it moving
        if progress:
            progress((i - 1) / len(searches), msg)
        hit = wiki_picture(c.get("label") or c["query"], c["query"], get, cancel)
        if not hit:
            continue
        try:
            data = download(hit["url"])
            ext = ".png" if hit["url"].lower().split("?")[0].endswith(".png") else ".jpg"
            f = images_dir / f"card_{c['n']:03d}_wikipedia{ext}"
            f.write_bytes(data)
        except Exception as exc:  # noqa: BLE001 - the stock search still gets its turn
            log(f"card {c['n']}: Wikipedia picture not downloaded ({type(exc).__name__})")
            continue
        man.set(str(c["n"]), {"scene_number": str(c["n"]), "status": "complete", "source": "stock_image", "type": "image", "local_path": str(f),
                              "stock_query": c["query"], "provider": "wikipedia", "author": "Wikimedia Commons", "source_url": hit["page"],
                              "provider_asset_id": hit["title"]})
        got += 1
        if on_picture:
            on_picture()
    if got:
        log(f"{got} card pictures from Wikipedia")
    return got


def fetch(reqs: List[dict], manager, images_dir: Path, log: Callable = lambda m: None, cancel: Optional[Callable] = None,
          progress: Optional[Callable] = None, on_picture: Optional[Callable] = None) -> list:
    """Fetches the pictures the Visuals table does not hold yet (a picture already there, or one the user picked, is kept). Returns the table's rows.
    A failed search leaves that card without a picture; the render drops it."""
    import threading

    import visual_bridge

    try:
        seed_from_wikipedia(reqs, images_dir, log, cancel=cancel, progress=progress, on_picture=on_picture)      # the article's own picture first: it is the right one
    except Exception as exc:  # noqa: BLE001
        log(f"Wikipedia pictures skipped: {type(exc).__name__}: {exc}")
    rows = table_rows(reqs)
    if cancel and cancel():
        return rows
    # A card planned from the narration that Wikipedia has no picture for is dropped: a stock search on a bare name returns snapshots and
    # doodles, and a missing card is better than a wrong one. A card the story's author wrote (CSV) still gets the stock search.
    auto = {str(c["n"]) for c in reqs if c.get("source") == "auto"}
    dropped = [r for r in rows if str(r.scene_number) in auto and not visual_bridge.records(images_dir, [r])]
    if dropped:
        log(f"{len(dropped)} planned cards have no Wikipedia picture and are left out: " + ", ".join(str(r.stock) for r in dropped[:6]))
    rows = [r for r in rows if r not in dropped]
    todo = [r for r in rows if not visual_bridge.records(images_dir, [r])]
    if not todo:
        return rows
    try:
        manager.settings["gemini_enabled"] = False        # the story directs: no AI calls
    except Exception:
        pass
    Path(images_dir).mkdir(parents=True, exist_ok=True)
    log(f"Fetching {len(todo)} card pictures…")
    stop = threading.Event()
    if cancel is not None:
        def watch() -> None:
            while not stop.wait(0.3):
                if cancel():
                    try:
                        manager.request_cancel()
                    except Exception:
                        pass
                    return

        threading.Thread(target=watch, daemon=True, name="vm-card-cancel").start()
    try:
        manager.resolve_all(todo)
    except Exception as exc:  # noqa: BLE001 - a failed fetch only costs those cards
        log(f"card fetch stopped early: {type(exc).__name__}: {exc}")
    finally:
        stop.set()
    return rows


def paths_from(reqs: List[dict], records: Dict[int, dict]) -> Dict[int, str]:
    """{card n: picture file}: the CSV's own file, else what the Visuals table holds now (so a picture the user swapped there is what is used)."""
    out: Dict[int, str] = {}
    for c in reqs:
        rec = records.get(c["n"]) or {}
        p = rec.get("path") or c.get("local") or ""
        if p and Path(p).is_file():
            out[c["n"]] = p
    return out


def credits(reqs: List[dict], records: Dict[int, dict]) -> List[str]:
    """One line per fetched picture that names its author or source (Wikimedia / Openverse pictures require it)."""
    lines = []
    for c in reqs:
        rec = records.get(c["n"]) or {}
        if rec.get("ok") and (rec.get("author") or rec.get("source_url")):
            lines.append(f"Picture: {c.get('label') or c.get('query')} - {rec.get('author') or 'unknown'} ({rec.get('provider') or rec.get('source') or 'web'})")
    return lines


def write_story(csv_path: str, out_path: str, reqs: List[dict], paths: Dict[int, str], credit_lines: Optional[List[str]] = None) -> str:
    """The story the renderer reads: the original rows (their own card rows replaced) + one card row per card that has a picture."""
    rows, head = read_rows(csv_path)
    for col in ("row", "id", "text", "lon", "lat", "extra"):
        if col not in head:
            head.append(col)
    out = []
    for r in rows:
        if r.get("row") == "card":
            continue
        if r.get("row") == "plan" and credit_lines:
            x = _extra(r)
            x["credits_lines"] = list(x.get("credits_lines") or []) + list(credit_lines)
            r = dict(r, extra=json.dumps(x, ensure_ascii=False))
        out.append(r)
    for c in reqs:
        p = paths.get(c["n"])
        if not p:
            continue
        x = {"asset": str(Path(p).resolve()), "kind": c.get("kind") or "photo"}
        for k in ("words", "hold", "t", "anchor"):
            if c.get(k) not in (None, ""):
                x[k] = c[k]
        out.append({"row": "card", "id": c["beat"], "text": c.get("label", ""), "lon": "" if c.get("lon") is None else c["lon"],
                    "lat": "" if c.get("lat") is None else c["lat"], "extra": json.dumps(x, ensure_ascii=False)})
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=head, extrasaction="ignore", lineterminator="\n")
    w.writeheader()
    for r in out:
        w.writerow({k: r.get(k, "") for k in head})
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(buf.getvalue(), encoding="utf-8")
    return str(out_path)
