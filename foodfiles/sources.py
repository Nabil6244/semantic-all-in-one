"""Real imagery for Food Files (docs/food_files/IMPROVEMENT_PLAN.md, Phase 1): photos, page screenshots, news / TV clips.

Order for every picture slot: a real photo from Wikimedia Commons (only public domain / CC0 / CC BY / CC BY-SA, the credit
line filled in from what Commons reports) -> Flow (only for things fine to illustrate). Page cards screenshot the real page
(a recall notice, a headline) with the app's Aviation web capture. Clip shots cut a few seconds from a news / TV video on
YouTube where its transcript says the row's words.

Everything is fetched once and kept in the shared library (prepper_host/flow.LIB) under the shot's key, with a .json beside
it holding the credit, so a later Generate, another video or the renderer finds it without the network. Nothing here
raises for network trouble: a miss returns None and the caller keeps its fallback.
"""
import json
import math
import re
import time
from pathlib import Path

from prepper_host import flow

STOP = {"the", "a", "an", "of", "in", "on", "and", "or", "with", "for", "to", "at", "by", "from", "its", "it", "photo",
        "picture", "image", "real", "old", "new", "close", "up", "closeup", "view"}
BAD_TITLE = re.compile(r"\b(logo|icon|map|flag|coat of arms|diagram|chart|signature|svg|seal)\b", re.I)
MIN_W = 640
WIDTH = 1280   # a standard Wikimedia thumbnail width: odd sizes get "429 Too many requests"


# ------------------------------------------------------------------ library sidecars
def meta_path(key, ext="png"):
    return flow.lib_path(key, ext).with_suffix(f".{ext}.json")


def meta(key, ext="png"):
    p = meta_path(key, ext)
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None
    except ValueError:
        return None


def _store(key, data, ext, info):
    flow.LIB.mkdir(parents=True, exist_ok=True)
    dst = flow.lib_path(key, ext)
    dst.write_bytes(data)
    meta_path(key, ext).write_text(json.dumps(info, indent=1), encoding="utf-8")
    return str(dst)


def words_of(text):
    return [w for w in re.findall(r"[a-z0-9]+", str(text or "").lower()) if w not in STOP and len(w) > 1]


def matches(query, text, need=0.6):
    """Enough of the query's meaningful words appear in the candidate's title / description / categories."""
    q = words_of(query)
    if not q:
        return False
    t = set(words_of(text))
    hit = sum(1 for w in q if w in t or (w.endswith("s") and w[:-1] in t) or f"{w}s" in t)
    return hit >= max(1, math.ceil(len(q) * need - 1e-9))


# ------------------------------------------------------------------ Wikimedia Commons
def _war():
    from cinematic_explainer.war import equipment_images as E
    return E


# No contact in the client name (owner, 2026-11-22: no repo link): spacing, one call per photo and the breaker keep us polite
UA = "SemanticYTStudio-FoodFiles/1.0 (food history videos; each file fetched once and cached)"
MISS_DAYS = 7
_last_get = [0.0]
_last_api = [0.0]
BREAKER = {"refused": 0, "open_until": 0.0}   # after 2 refusals in a row, stop asking Commons for 10 minutes


class CommonsBusy(Exception):
    pass


def breaker_open():
    return time.time() < BREAKER["open_until"]


def _refused(exc):
    if "429" in str(exc):
        BREAKER["refused"] += 1
        if BREAKER["refused"] >= 2:
            BREAKER["open_until"] = time.time() + 600
    return exc


def _get_json(params):
    """Commons API calls at least 1 s apart; a refusal (429) counts toward the breaker instead of being hammered."""
    import requests
    if breaker_open():
        raise CommonsBusy("Wikimedia asked us to slow down; Flow stands in for the next few minutes")
    wait = 1.0 - (time.time() - _last_api[0])
    if wait > 0:
        time.sleep(wait)
    _last_api[0] = time.time()
    last = None
    for host in ("https://commons.wikimedia.org/w/api.php", "https://en.wikipedia.org/w/api.php"):
        try:
            r = requests.get(host, params={**params, "format": "json"}, headers={"User-Agent": UA}, timeout=30)
            r.raise_for_status()
            BREAKER["refused"] = 0
            return r.json()
        except Exception as exc:  # noqa: BLE001 - next host
            last = _refused(exc)
            if breaker_open():
                break
    raise last


def _get_bytes(url, tries=2):
    """Polite downloads: at least 1.5 s apart, and a 429 (too many requests) waits and tries again."""
    import requests
    for i in range(tries):
        wait = 1.5 - (time.time() - _last_get[0])
        if wait > 0:
            time.sleep(wait)
        _last_get[0] = time.time()
        r = requests.get(url, headers={"User-Agent": UA}, timeout=90)
        if r.status_code == 429 and i + 1 < tries:
            ra = float(r.headers.get("Retry-After") or 0) or 5 * (i + 1)
            if ra > 15:            # a long ban: move on (the next candidate or Flow) instead of stalling Generate
                break
            time.sleep(ra)
            continue
        r.raise_for_status()
        return r.content


def _short_name(creator):
    """'Donald Trung Quoc Don (Chữ Hán: ...) - Wikimedia Commons.(Wa...' -> 'Donald Trung Quoc Don'."""
    c = re.sub(r"\s+", " ", str(creator or "")).strip()
    c = re.split(r"\s[-–—|]\s|\(|,|;|\bfrom\b|https?://", c)[0].strip(" .")
    return c[:40].strip()


def credit_of(info):
    who = _short_name(info.get("creator"))
    lic = str(info.get("licence") or "").strip()
    return "Photo: " + " / ".join(x for x in (who, "Wikimedia Commons", lic) if x)


def commons_candidates(query, get_json=None, n=12):
    """Commons file pages for the words, best first, with licence + size + description - in ONE request (a search
    generator with the file details attached), so each photo costs Wikimedia one call plus the download."""
    E = _war()
    get = get_json or _get_json
    r = get({"action": "query", "generator": "search", "gsrnamespace": "6", "gsrlimit": str(n),
             "gsrsearch": f"{query} filetype:bitmap", "prop": "imageinfo", "iiprop": "url|size|extmetadata|mime",
             "iiurlwidth": str(WIDTH)})
    pages = list((r.get("query", {}).get("pages") or {}).values())
    titles = [p.get("title", "") for p in sorted(pages, key=lambda p: p.get("index", 99))]
    out = []
    for page in pages:
        ii = (page.get("imageinfo") or [None])[0]
        if not ii:
            continue
        m = ii.get("extmetadata") or {}
        v = lambda k: E._strip(str((m.get(k) or {}).get("value") or ""))
        info = {"title": page.get("title", ""), "thumb": ii.get("thumburl") or ii.get("url", ""), "width": ii.get("width") or 0,
                "height": ii.get("height") or 0, "mime": ii.get("mime", ""), "creator": v("Artist"),
                "licence": v("LicenseShortName"), "description": v("ImageDescription"), "categories": v("Categories"),
                "page_url": ii.get("descriptionurl", "")}
        info["rank"] = titles.index(info["title"]) if info["title"] in titles else 99
        out.append(info)
    return sorted(out, key=lambda i: i["rank"])


def pick_commons(query, cands):
    E = _war()
    for c in cands:
        if not E.acceptable_licence(c["licence"]):
            continue
        if not str(c["mime"]).startswith("image/") or c["mime"] in ("image/svg+xml", "image/gif"):
            continue
        if c["width"] < MIN_W or c["height"] < MIN_W * 0.5:
            continue
        name = re.sub(r"^File:", "", c["title"])
        if BAD_TITLE.search(name) and not BAD_TITLE.search(query):
            continue
        if not matches(query, f"{name} {c['description']} {c['categories']}"):
            continue
        if not matches(query, name, need=0.5):   # half the words in the file's own title: descriptions are long and loose
            continue
        return c
    return None


def commons(key, query, *, get_json=None, get_bytes=None, log=print):
    """A real photo for `query` stored under `key` -> {"path", "credit", ...} or None (nothing acceptable found)."""
    have = flow.have(key)
    m = meta(key)
    if have and m:
        return dict(m, path=have)
    if breaker_open() and get_json is None:
        return None                       # Commons is refusing right now: Flow stands in, no more requests
    if get_json is None and missed_lately(query):
        return None                       # Commons had nothing for these words a few days ago: don't ask again yet
    try:
        c = None
        for q in _variants(query):          # "peppermint humbugs" -> also "peppermint humbug"
            c = pick_commons(query, commons_candidates(q, get_json=get_json))
            if c:
                break
        if not c:
            remember_miss(query)
            return None
        url = c["thumb"]
        if c["width"] <= WIDTH and get_json is None:   # a small original: ask for a ready-made standard thumbnail instead
            url = _standard_thumb(c["title"], c["width"]) or url
        data = (get_bytes or _get_bytes)(url)
        info = {"source": "commons", "query": query, "title": c["title"], "page_url": c["page_url"], "creator": c["creator"],
                "licence": c["licence"], "credit": credit_of(c),
                "note": "licence and creator as reported by Wikimedia Commons; not independently verified"}
        path = _store(key, data, "png", info)
        _to_png(path)
        return dict(info, path=path)
    except Exception as e:  # noqa: BLE001 - a miss falls back to Flow
        log(f"food files: Commons search for '{query}' did not work ({type(e).__name__}: {e})")
        return None


STANDARD = (960, 800, 640, 500, 400)


def _standard_thumb(title, width):
    step = next((w for w in STANDARD if w < width), None)
    if not step:
        return None
    try:
        r = _get_json({"action": "query", "titles": title, "prop": "imageinfo", "iiprop": "url", "iiurlwidth": str(step)})
        page = next(iter((r.get("query", {}).get("pages") or {}).values()))
        return (page.get("imageinfo") or [{}])[0].get("thumburl")
    except Exception:  # noqa: BLE001
        return None


def _miss_file():
    return flow.LIB / "commons_misses.json"


def _misses():
    try:
        return json.loads(_miss_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def missed_lately(query, days=MISS_DAYS):
    t = _misses().get(re.sub(r"\s+", " ", str(query).strip().lower()))
    return bool(t) and time.time() - float(t) < days * 86400


def remember_miss(query):
    """A search that found nothing acceptable (not a refusal or a network error) is not asked again for a week."""
    m = _misses()
    m[re.sub(r"\s+", " ", str(query).strip().lower())] = time.time()
    try:
        flow.LIB.mkdir(parents=True, exist_ok=True)
        _miss_file().write_text(json.dumps(m, indent=1), encoding="utf-8")
    except OSError:
        pass


def _variants(query):
    q = re.sub(r"\s+", " ", str(query or "")).strip()
    out = [q]
    sing = " ".join(w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w for w in q.split())
    if sing != q:
        out.append(sing)
    return out


def _to_png(path):
    """Commons thumbs are often JPEG: keep the library file a real PNG (the renderer opens it either way)."""
    try:
        from PIL import Image
        im = Image.open(path)
        if im.format != "PNG":
            im.convert("RGB").save(path, "PNG")
    except Exception:  # noqa: BLE001
        pass


# ------------------------------------------------------------------ page screenshots
def page(key, url, *, log=print):
    """A screenshot of the real page (recall notice, headline...) -> {"path", "site", "title", "date", "headline_box"} or None."""
    have = flow.have(key)
    m = meta(key)
    if have and m:
        return dict(m, path=have)
    try:
        from aviation import webshot
        cache = flow.LIB / "pages"
        r = webshot.shot(url, cache)
        if not r.get("ok"):
            log(f"food files: no screenshot of {url} ({r.get('reason')})")
            return None
        info = {"source": "page", "url": url, "site": r.get("site", ""), "title": r.get("title", ""), "date": r.get("date", ""),
                "headline_box": r.get("headline_box"), "credit": f"Source: {r.get('site') or url}"}
        return dict(info, path=_store(key, Path(r["path"]).read_bytes(), "png", info))
    except Exception as e:  # noqa: BLE001
        log(f"food files: page screenshot failed ({type(e).__name__}: {e})")
        return None


# ------------------------------------------------------------------ news / TV clips
def best_window(segments, words, length):
    """Start time of the `length`-second window of the transcript that says most of `words` (None if it says none)."""
    want = set(words_of(words))
    if not want or not segments:
        return None
    best, best_t = 0, None
    for i, s in enumerate(segments):
        t0 = float(s.start)
        said = set()
        for s2 in segments[i:]:
            if float(s2.start) > t0 + length:
                break
            said |= set(words_of(s2.text))
        score = len(want & said)
        if score > best:
            best, best_t = score, t0
    return best_t if best >= max(1, round(len(want) * 0.4)) else None


def clip(key, query, words, *, seconds=7.0, backend=None, log=print):
    """A few seconds of a news / TV video where it says `words` -> {"path", "title", "channel", "credit"} or None."""
    have = flow.have(key, "mp4")
    m = meta(key, "mp4")
    if have and m:
        return dict(m, path=have)
    try:
        if backend is None:
            from providers.youtube.ytdlp_backend import YtDlpBackend
            backend = YtDlpBackend()
        for cand in backend.search(query, max_results=6):
            if cand.duration and cand.duration > 3600:
                continue
            if not matches(query, f"{cand.title} {cand.description}", need=0.4):
                continue
            segs = backend.get_transcript(cand)
            at = best_window(segs, words or query, seconds) if segs else None
            if at is None:
                continue
            tmp = flow.LIB / f"{key}.part.mp4"
            flow.LIB.mkdir(parents=True, exist_ok=True)
            backend.download_segment(cand, max(0.0, at - 0.5), seconds, tmp, log=lambda m: None)
            info = {"source": "clip", "query": query, "video_id": cand.video_id, "url": cand.url, "title": cand.title,
                    "channel": cand.channel, "start": round(at, 2), "credit": f"Video: {cand.channel} via YouTube"}
            if not tmp.is_file():
                continue
            data = tmp.read_bytes()
            tmp.unlink(missing_ok=True)
            return dict(info, path=_store(key, data, "mp4", info))
    except Exception as e:  # noqa: BLE001
        log(f"food files: no clip for '{query}' ({type(e).__name__}: {e})")
    return None
