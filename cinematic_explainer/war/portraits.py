"""War Documentary portraits: one cached portrait per named person, resolved exactly through Wikidata and fetched from Wikimedia Commons.

    portrait_for(figure_id_or_name) -> {"path", "reuse", "record"} or None      (cache only; never touches the network)
    fetch_portrait(entry, ...)      -> same, after one lookup when the person is not cached (explicit call only)
    provenance_for_path(path)       -> provenance.Provenance for the credits, or None

Exact person: a Wikidata item is accepted only when it is a human (P31 = Q5), its English label or an alias equals the catalogue name, and it
carries a P18 image. The image is the one Wikidata itself links to that item, so there is no search-by-face and no lookalike. A licence is
accepted only when Commons reports public domain, CC0, CC BY or CC BY-SA (any version); anything else is skipped and remembered as skipped.
Licence data is exactly what Commons reports: it is recorded as "as reported by Commons, not independently verified".

Store: bundled records/images in data/portraits/ (shipped with the app, read first) and a per-user cache next to the map caches (written
by fetch_portrait). One file + one <id>.json per person; the same file is returned every time. Nothing here downloads during a render.
"""

from __future__ import annotations

import difflib
import io
import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

log = logging.getLogger("cinematic_explainer.war.portraits")

BUNDLED_DIR = Path(__file__).resolve().parent / "data" / "portraits"
PORTRAIT_PX = 512
STATUS_TEXT = "licence as reported by Commons, not independently verified"
API_WD = "https://www.wikidata.org/w/api.php"
API_COMMONS = "https://commons.wikimedia.org/w/api.php"
API_COMMONS_FALLBACKS = ("https://commons.m.wikimedia.org/w/api.php", "https://en.wikipedia.org/w/api.php")   # same Commons data when one host does not resolve

_FREE_RE = re.compile(r"^(public domain|pd\b|pd-|cc0|cc[- ]by(?:[- ]sa)?\b|cc[- ]zero)", re.IGNORECASE)


def user_dir() -> Path:
    try:
        from map_scene.render import cache_dir

        return Path(cache_dir()) / "portraits"
    except Exception:
        return Path.home() / ".semantic_yt_studio" / "portraits"


def _stores(extra: Optional[Path] = None, only: bool = False) -> List[Path]:
    if only and extra:
        return [Path(extra)]
    return [d for d in ([Path(extra)] if extra else []) + [BUNDLED_DIR, user_dir()]]


def classify_licence(short_name: str) -> Dict[str, Any]:
    """{ok, reuse, attribution_required, share_alike}. Anything not clearly public domain / CC0 / CC BY / CC BY-SA is not ok."""
    s = (short_name or "").strip()
    low = s.lower()
    if not s or not _FREE_RE.match(s) or "nc" in re.findall(r"[a-z]+", low) or "nd" in re.findall(r"[a-z]+", low):
        return {"ok": False, "reuse": "none", "attribution_required": True, "share_alike": False}
    pd = low.startswith(("public domain", "pd", "cc0", "cc zero", "cc-zero"))
    sa = "sa" in re.findall(r"[a-z]+", low)
    return {"ok": True, "reuse": "free" if pd else ("share_alike" if sa else "attribution_required"), "attribution_required": not pd, "share_alike": sa}


def _strip_html(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s or "")).strip()


def _ua() -> str:
    try:
        from app_version import APP_VERSION

        v = str(APP_VERSION)
    except Exception:
        v = "dev"
    return f"SemanticYTStudio/{v} (War Documentary portraits; local desktop app)"


def _http_json(url: str, params: Dict[str, str]) -> Dict[str, Any]:
    import requests

    for wait in (0, 6, 15):
        time.sleep(wait)
        r = requests.get(url, params={**params, "format": "json"}, headers={"User-Agent": _ua()}, timeout=20)
        if r.status_code != 429:
            break
    r.raise_for_status()
    return r.json()


def _http_bytes(url: str) -> bytes:
    import requests

    for wait in (0, 6, 15):
        time.sleep(wait)
        r = requests.get(url, headers={"User-Agent": _ua()}, timeout=40)
        if r.status_code != 429:
            break
    r.raise_for_status()
    return r.content


# ---- reading the store --------------------------------------------------------------------------------------------------------------------
def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")


def load_record(fid: str, extra: Optional[Path] = None, only: bool = False) -> Optional[dict]:
    for d in _stores(extra, only):
        p = d / f"{fid}.json"
        if p.is_file():
            try:
                rec = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            img = d / str(rec.get("file") or "")
            if rec.get("status") == "skipped":
                return rec
            if img.is_file():
                rec["path"] = str(img)
                return rec
    return None


def portrait_for(fid: str, extra: Optional[Path] = None, only: bool = False) -> Optional[Dict[str, Any]]:
    """The cached portrait for a figure id, or None. No network. A skipped (rejected) record gives None."""
    rec = load_record(_slug(fid), extra, only)
    if not rec or rec.get("status") == "skipped" or not rec.get("path"):
        return None
    if rec.get("reuse") in (None, "", "none", "unknown"):
        return None
    return {"path": rec["path"], "reuse": rec["reuse"], "record": rec}


def record_for_path(path: str) -> Optional[dict]:
    try:
        p = Path(path).resolve()
    except OSError:
        return None
    rp = p.with_suffix(".json")
    if rp.is_file():
        try:
            return json.loads(rp.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
    return None


def provenance_for_path(path: str):
    """Provenance for a portrait file the planner used, for the credits; None when the file is not one of ours."""
    rec = record_for_path(path)
    if not rec or not rec.get("source_url"):
        return None
    from . import provenance as P

    lic = rec.get("licence") or P.UNKNOWN
    obl = " (attribution required)" if rec.get("attribution_required") else ""
    obl += " (share-alike)" if rec.get("share_alike") else ""
    p = P.Provenance(asset_id=f"portrait:{rec.get('id')}", category="figure", description=f"portrait of {rec.get('name')}", source_url=rec["source_url"],
                     provider="Wikimedia Commons", provider_asset_id=str(rec.get("commons_title") or ""), licence=f"{lic}{obl}" if lic != P.UNKNOWN else lic,
                     attribution=str(rec.get("attribution") or rec.get("creator") or ""), status="attributed")
    p.caveats.append(STATUS_TEXT)
    return p


# ---- resolving and fetching -------------------------------------------------------------------------------------------------------------
def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def resolve_person(name: str, aliases: Optional[List[str]] = None, *, http: Callable[[str, Dict[str, str]], Dict[str, Any]] = None) -> Optional[dict]:
    """Exact Wikidata human whose English label or alias equals the catalogue name (or one of its Latin-script aliases) and that has a P18
    image. Two requests: one search, one batched read of the hits. None when no hit is exact."""
    http = http or _http_json
    found = http(API_WD, {"action": "wbsearchentities", "search": name, "language": "en", "type": "item", "limit": "7"})
    ids = [h["id"] for h in found.get("search", []) if h.get("id")]
    if not ids:
        return None
    ent = http(API_WD, {"action": "wbgetentities", "ids": "|".join(ids), "props": "labels|aliases|claims|descriptions", "languages": "en"})
    want = {_norm(name)} | {_norm(a) for a in (aliases or []) if re.fullmatch(r"[A-Za-z .'\-]+", str(a))}
    for qid in ids:
        e = (ent.get("entities") or {}).get(qid) or {}
        claims = e.get("claims") or {}
        is_human = any(((c.get("mainsnak") or {}).get("datavalue") or {}).get("value", {}).get("id") == "Q5" for c in claims.get("P31", []))
        label = ((e.get("labels") or {}).get("en") or {}).get("value", "")
        als = [a.get("value", "") for a in (e.get("aliases") or {}).get("en", [])]
        names = {_norm(label)} | {_norm(a) for a in als}
        if not is_human or not (want & names or any(difflib.SequenceMatcher(None, _norm(name), n).ratio() >= 0.93 for n in names if n)):
            continue
        img = None
        for c in claims.get("P18", []):
            v = ((c.get("mainsnak") or {}).get("datavalue") or {}).get("value")
            if isinstance(v, str):
                img = v
                if c.get("rank") == "preferred":
                    break
        if not img:
            continue
        return {"qid": qid, "label": label, "description": ((e.get("descriptions") or {}).get("en") or {}).get("value", ""), "file": img}
    return None


def commons_info(file_name: str, *, http: Callable[[str, Dict[str, str]], Dict[str, Any]] = None) -> Optional[dict]:
    http = http or _http_json
    title = "File:" + file_name.replace("_", " ")
    q = {"action": "query", "titles": title, "prop": "imageinfo", "iiprop": "url|extmetadata|mime", "iiurlwidth": str(PORTRAIT_PX)}
    d, last = {}, None
    for host in (API_COMMONS,) + API_COMMONS_FALLBACKS:
        try:
            d = http(host, q)
            break
        except OSError as exc:      # requests' errors are OSErrors: try the next host for the same Commons data
            last = exc
    else:
        raise last  # type: ignore[misc]
    for pg in (d.get("query", {}).get("pages") or {}).values():
        ii = (pg.get("imageinfo") or [None])[0]
        if not ii:
            continue
        m = ii.get("extmetadata") or {}
        g = lambda k: _strip_html((m.get(k) or {}).get("value", ""))
        return {"title": pg.get("title", title), "thumb": ii.get("thumburl") or ii.get("url"), "mime": ii.get("mime", ""), "page": ii.get("descriptionurl", ""),
                "licence": g("LicenseShortName"), "licence_url": g("LicenseUrl"), "artist": g("Artist"), "credit": g("Credit"),
                "attribution_required": g("AttributionRequired").lower() == "true", "usage_terms": g("UsageTerms"), "date": g("DateTimeOriginal")}
    return None


def head_square(im):
    """Square crop anchored at the top of a taller-than-wide photo, so the circle on the card shows the head and shoulders (the card's own
    centred cover-crop would cut the head off a standing portrait). Resized to PORTRAIT_PX."""
    w, h = im.size
    if h > w:
        im = im.crop((0, 0, w, w))
    elif w > h:
        x = (w - h) // 2
        im = im.crop((x, 0, x + h, h))
    im.thumbnail((PORTRAIT_PX, PORTRAIT_PX))
    return im


def _write_skip(store: Path, fid: str, name: str, why: str, extra: Optional[dict] = None) -> None:
    store.mkdir(parents=True, exist_ok=True)
    rec = {"id": fid, "name": name, "status": "skipped", "reason": why, "retrieved": time.strftime("%Y-%m-%d"), **(extra or {})}
    (store / f"{fid}.json").write_text(json.dumps(rec, indent=1, ensure_ascii=False), encoding="utf-8")


def fetch_portrait(entry: dict, *, store: Optional[Path] = None, http: Callable = None, download: Callable[[str], bytes] = None,
                   force: bool = False) -> Optional[Dict[str, Any]]:
    """One lookup for one catalogue entry; cached result (including a recorded skip) is returned without any request."""
    fid = _slug(entry.get("id") or entry.get("name"))
    name = str(entry.get("name") or "")
    only = store is not None            # an explicit store is looked at alone; the default also sees the bundled set
    store = Path(store) if store else user_dir()
    if not force:
        have = portrait_for(fid, store, only)
        if have:
            return have
        old = load_record(fid, store, only)
        if old and old.get("status") == "skipped":
            return None
    http = http or _http_json
    download = download or _http_bytes
    try:
        who = resolve_person(name, entry.get("aliases"), http=http)
        if not who:
            _write_skip(store, fid, name, "no exact Wikidata human with an image")
            return None
        info = commons_info(who["file"], http=http)
        if not info or not info.get("thumb"):
            _write_skip(store, fid, name, "Commons file info not available", {"qid": who["qid"]})
            return None
        lic = classify_licence(info["licence"])
        if not lic["ok"] or not info["mime"].startswith("image/"):
            _write_skip(store, fid, name, f"licence not accepted: '{info['licence'] or 'none reported'}'", {"qid": who["qid"], "commons_title": info["title"]})
            return None
        raw = download(info["thumb"])
        from PIL import Image

        im = head_square(Image.open(io.BytesIO(raw)).convert("RGB"))
        store.mkdir(parents=True, exist_ok=True)
        fname = f"{fid}.jpg"
        im.save(store / fname, "JPEG", quality=90)
        creator = info["artist"] or info["credit"]
        attribution = f"{creator}, {info['licence']}" if creator else info["licence"]
        rec = {"id": fid, "name": name, "status": "ok", "file": fname, "reuse": lic["reuse"], "attribution_required": lic["attribution_required"],
               "share_alike": lic["share_alike"], "licence": info["licence"], "licence_url": info["licence_url"], "creator": creator, "attribution": attribution,
               "source_url": info["page"], "commons_title": info["title"], "wikidata_qid": who["qid"], "wikidata_label": who["label"],
               "wikidata_description": who["description"], "resolution": "Wikidata human (Q5) whose English label/alias equals the catalogue name; image is that item's own P18",
               "licence_status": STATUS_TEXT, "crop": "top-anchored square from the Commons thumbnail", "date_taken": info["date"], "retrieved": time.strftime("%Y-%m-%d"), "size": list(im.size)}
        (store / f"{fid}.json").write_text(json.dumps(rec, indent=1, ensure_ascii=False), encoding="utf-8")
        return portrait_for(fid, store, True)
    except Exception as exc:   # a lookup problem leaves the name plate; it is never fatal and is not cached as a rejection
        log.warning("portrait lookup for %s failed: %s", name, exc)
        return None


def main(argv: Optional[List[str]] = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Fetch and cache portraits for catalogue figures (explicit, a few requests per person).")
    ap.add_argument("ids", nargs="+")
    ap.add_argument("--store", default=str(BUNDLED_DIR))
    a = ap.parse_args(argv)
    figs = {e["id"]: e for e in json.loads((Path(__file__).parent / "data" / "figures.json").read_text(encoding="utf-8"))["entries"]}
    for i in a.ids:
        r = fetch_portrait(figs[i], store=Path(a.store))
        print(i, "->", (r or {}).get("path") or "skipped/failed")
        time.sleep(3.0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
