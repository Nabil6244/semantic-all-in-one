"""Equipment photographs for the War Documentary equipment card: exact-model Wikimedia Commons images, cached once, with their credits.

    lookup(equip_id)            -> record dict (with 'path') or None; reads the shipped index (data/equipment_images.json + data/equipment_images/)
                                   and then the per-user cache (<app cache>/war_equipment/), never the network
    credit_line(rec)            -> the short line drawn on the card ("Photo: creator · CC BY-SA 4.0 · Wikimedia Commons")
    provenance_for(rec)         -> a provenance.Provenance for the credits / report output
    fetch_and_store(...)        -> the only function that touches the network (planning-time tooling, never the renderer); injectable HTTP

Rules: only public-domain, CC0, CC BY and CC BY-SA files are accepted; the file title or description must name the exact designation of the
system (a category-mate is rejected, see identity_ok); the licence string is what Commons reports and is stored as "reported by Commons, not
independently verified". A missing record, file or licence gives None and the card keeps its labelled illustrative silhouette.

Build / extend (network): python3 -m cinematic_explainer.war.equipment_images --id t-72 --title "File:T-72B in Chebarkul training ground.jpg" [--shipped]
"""

from __future__ import annotations

import io
import json
import logging
import os
import re
import time
from datetime import date
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

log = logging.getLogger("cinematic_explainer.war.equipment_images")

HERE = Path(__file__).resolve().parent
SHIPPED_INDEX = HERE / "data" / "equipment_images.json"
SHIPPED_DIR = HERE / "data" / "equipment_images"
MAX_W = 800
VERIFICATION_NOTE = "licence and creator as reported by Wikimedia Commons; not independently verified"

# (regex on the Commons LicenseShortName, normalised name, licence url)
_ALLOWED = (
    (r"^(public domain|pd\b|pdm|cc0|cc-0)", None),
    (r"^cc[ -]by[ -]sa\b", None),
    (r"^cc[ -]by\b", None),
)
_BLOCKED = re.compile(r"\b(nc|nd|gfdl only|fair use|all rights|non-?commercial|no derivatives|unknown|copyright)\b", re.IGNORECASE)


def acceptable_licence(short: str) -> bool:
    s = (short or "").strip().lower()
    if not s or _BLOCKED.search(s):
        return False
    return any(re.search(p, s) for p, _ in _ALLOWED)


def default_cache_dir() -> Path:
    """Sibling of the other per-user caches (boundaries): <app cache>/war_equipment."""
    try:
        from map_scene.render import cache_dir

        return Path(cache_dir()) / "war_equipment"
    except Exception:
        return Path.home() / ".semantic_yt_studio" / "war_equipment"


# ---- reading (offline) -------------------------------------------------------------------------------------------------------------------
def _read(path: Path) -> Dict[str, dict]:
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        imgs = d.get("images") if isinstance(d, dict) else None
        return imgs if isinstance(imgs, dict) else {}
    except (OSError, ValueError):
        return {}


def lookup(equip_id: str, *, cache_dir: Optional[Path] = None, shipped_index: Optional[Path] = None, shipped_dir: Optional[Path] = None) -> Optional[dict]:
    """The stored photograph for a catalogue id, or None. The record's 'path' is absolute. Records whose licence is not acceptable or whose
    file is missing are ignored (never an error)."""
    if not equip_id:
        return None
    sources = [(Path(shipped_index) if shipped_index else SHIPPED_INDEX, Path(shipped_dir) if shipped_dir else SHIPPED_DIR)]
    cd = Path(cache_dir) if cache_dir else default_cache_dir()
    sources.append((cd / "index.json", cd))
    for idx, base in sources:
        rec = _read(idx).get(equip_id)
        if not isinstance(rec, dict) or not rec.get("file") or not acceptable_licence(str(rec.get("licence") or "")):
            continue
        p = base / str(rec["file"])
        if p.is_file():
            out = dict(rec)
            out["path"] = str(p)
            return out
    return None


def credit_line(rec: Optional[dict]) -> str:
    if not rec:
        return ""
    who = str(rec.get("creator") or "").strip() or "unknown author"
    lic = str(rec.get("licence") or "").strip()
    return f"Photo: {who} · {lic} · Wikimedia Commons" if lic else f"Photo: {who} · Wikimedia Commons"


def provenance_for(rec: dict, equip_name: str = ""):
    """A provenance.Provenance for the credits output. Status stays 'unverified' (the identification is the catalogue's, the licence Commons')."""
    from . import provenance as P

    p = P.Provenance(asset_id=f"equipment:{rec.get('id', '')}", category="equipment",
                     description=(equip_name or str(rec.get("name") or "")) + " photograph", source_url=str(rec.get("source_url") or ""),
                     provider="Wikimedia Commons", provider_asset_id=str(rec.get("commons_title") or ""), licence=str(rec.get("licence") or P.UNKNOWN),
                     attribution=str(rec.get("creator") or ""), status="unverified")
    p.caveats.append(VERIFICATION_NOTE)
    return p


# ---- identity ----------------------------------------------------------------------------------------------------------------------------
def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def identity_ok(entry: dict, title: str, description: str = "", extra_terms: Optional[List[str]] = None) -> bool:
    """True when the Commons file title or description contains one of the entry's own names/aliases (or an explicit designation term).
    A different member of the same class (another tank, another SAM) fails because its designation is not in the text."""
    hay = _norm(title) + "|" + _norm(description)
    raw = (title + " | " + description).lower()
    terms = [entry.get("name", "")] + list(entry.get("aliases") or []) + list(extra_terms or [])
    for t in terms:
        n = _norm(str(t))
        if len(n) >= 4 and n in hay:
            return True
        if 2 <= len(n) < 4 and re.search(r"[a-z]", n) and re.search(r"\d", n):
            # a short designation (T-72, F-16): match as a whole token, allowing one variant letter (T-72B, F-16C), never a longer number
            pat = r"(?<![a-z0-9])" + r"[\s\-]?".join(re.escape(c) for c in n) + r"[a-z]?(?![a-z0-9])"
            if re.search(pat, raw):
                return True
    return False


# ---- fetching (planning-time tooling) ----------------------------------------------------------------------------------------------------
_HOSTS = ("https://commons.wikimedia.org/w/api.php", "https://en.wikipedia.org/w/api.php")   # both serve Commons file metadata


def _user_agent() -> str:
    try:
        from app_version import APP_VERSION  # type: ignore

        v = str(APP_VERSION)
    except Exception:
        v = "dev"
    return f"SemanticYTStudio/{v} (war-documentary equipment images; cached once)"


def _http_json(params: Dict[str, str]) -> dict:
    import requests

    last: Exception = RuntimeError("no host")
    for host in _HOSTS:
        try:
            r = requests.get(host, params={**params, "format": "json"}, headers={"User-Agent": _user_agent()}, timeout=30)
            r.raise_for_status()
            return r.json()
        except Exception as exc:     # a host that does not resolve falls through to the next
            last = exc
    raise last


def _http_bytes(url: str) -> bytes:
    import requests

    r = requests.get(url, headers={"User-Agent": _user_agent()}, timeout=90)
    r.raise_for_status()
    return r.content


def _strip(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html or "")).strip()


def commons_info(title: str, *, get_json: Optional[Callable[[Dict[str, str]], dict]] = None) -> dict:
    """Metadata of one Commons file: {title, url, thumb (800 px), creator, licence, licence_url, description, categories, page_url}."""
    get = get_json or _http_json
    t = title if title.lower().startswith("file:") else "File:" + title
    r = get({"action": "query", "titles": t, "prop": "imageinfo", "iiprop": "url|size|extmetadata", "iiurlwidth": str(MAX_W)})
    page = list((r.get("query", {}).get("pages") or {}).values())[0]
    ii = (page.get("imageinfo") or [None])[0]
    if not ii:
        raise LookupError(f"{t}: no image info")
    m = ii.get("extmetadata") or {}
    v = lambda k: _strip(str((m.get(k) or {}).get("value") or ""))
    return {"title": page.get("title", t), "url": ii.get("url", ""), "thumb": ii.get("thumburl") or ii.get("url", ""), "creator": v("Artist"),
            "licence": v("LicenseShortName"), "licence_url": v("LicenseUrl"), "description": v("ImageDescription"), "categories": v("Categories"),
            "page_url": ii.get("descriptionurl") or "https://commons.wikimedia.org/wiki/" + t.replace(" ", "_"), "width": ii.get("width"), "height": ii.get("height")}


def fetch_and_store(equip_id: str, title: str, entry: dict, *, dest: str = "cache", extra_terms: Optional[List[str]] = None,
                    cache_dir: Optional[Path] = None, get_json: Optional[Callable[[Dict[str, str]], dict]] = None,
                    get_bytes: Optional[Callable[[str], bytes]] = None, shipped_dir: Optional[Path] = None, shipped_index: Optional[Path] = None) -> dict:
    """Fetch one named Commons file for a catalogue entry, check licence and identity, resize to <=800 px, store it once and record the credit.
    dest 'cache' = the per-user cache, 'shipped' = data/equipment_images (repository assets). Raises ValueError with the reason when rejected."""
    from PIL import Image

    info = commons_info(title, get_json=get_json)
    if not acceptable_licence(info["licence"]):
        raise ValueError(f"{info['title']}: licence '{info['licence'] or 'not reported'}' is not one of public domain / CC0 / CC BY / CC BY-SA")
    if not identity_ok(entry, info["title"], info["description"], extra_terms):
        raise ValueError(f"{info['title']}: file title and description do not name {entry.get('name')}; not used")
    raw = (get_bytes or _http_bytes)(info["thumb"])
    im = Image.open(io.BytesIO(raw)).convert("RGB")
    im.thumbnail((MAX_W, MAX_W))
    if dest == "shipped":
        base, idx = Path(shipped_dir) if shipped_dir else SHIPPED_DIR, Path(shipped_index) if shipped_index else SHIPPED_INDEX
    else:
        base = Path(cache_dir) if cache_dir else default_cache_dir()
        idx = base / "index.json"
    base.mkdir(parents=True, exist_ok=True)
    fname = f"{equip_id}.jpg"
    im.save(base / fname, "JPEG", quality=88)
    rec = {"id": equip_id, "name": entry.get("name", ""), "file": fname, "commons_title": info["title"], "source_url": info["page_url"],
           "original_url": info["url"], "creator": info["creator"], "licence": info["licence"], "licence_url": info["licence_url"],
           "attribution": credit_line({"creator": info["creator"], "licence": info["licence"]}), "retrieved": date.today().isoformat(),
           "size": [im.width, im.height], "identity_basis": "exact designation in the Commons file title or description",
           "description": info["description"][:200], "verification": VERIFICATION_NOTE}
    data = {"version": 1, "images": _read(idx)}
    data["images"][equip_id] = rec
    tmp = idx.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    os.replace(tmp, idx)
    return rec


def main(argv: Optional[List[str]] = None) -> int:
    import argparse
    from . import catalog

    ap = argparse.ArgumentParser(description="Fetch one equipment photograph from Wikimedia Commons into the cache (or the shipped assets).")
    ap.add_argument("--id", required=True, help="catalogue id, e.g. t-72")
    ap.add_argument("--title", required=True, help="Commons file title")
    ap.add_argument("--term", action="append", default=[], help="extra designation accepted in the title/description (e.g. 'Iskander')")
    ap.add_argument("--shipped", action="store_true")
    a = ap.parse_args(argv)
    entry = catalog.get_equipment(a.id)
    if not entry:
        print("unknown catalogue id")
        return 2
    try:
        rec = fetch_and_store(a.id, a.title, entry, dest="shipped" if a.shipped else "cache", extra_terms=a.term)
    except Exception as exc:
        print("rejected:", exc)
        return 1
    print(json.dumps(rec, indent=1, ensure_ascii=False))
    time.sleep(1.0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
