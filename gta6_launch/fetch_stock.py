"""Fetch free Pexels clips by search words with the app's own Pexels key (the same source as the Visuals tab).
Each query is saved once as footage/stock/px_<slug>.mp4; sources.json keeps the Pexels page of every clip."""
import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
from providers.stock.pexels import PexelsBackend  # noqa: E402

STOCK = ROOT / "footage/stock"
SRC = STOCK / "sources.json"


def _slug(q: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", q.lower()).strip("_")[:40]


def fetch(query: str) -> str:
    """Path (relative to gta6_launch/) of a 1080p Pexels clip for the words, downloading it the first time; '' if none."""
    f = STOCK / f"px_{_slug(query)}.mp4"
    if f.is_file() and f.stat().st_size > 100_000:
        return f"footage/stock/{f.name}"
    key = json.loads((ROOT.parent / "settings.json").read_text()).get("pexels_api_key", "")
    cands = PexelsBackend(key).search(query, "video", 8)
    good = [c for c in cands if int(getattr(c, "width", 0) or 0) >= 1920 and float(getattr(c, "duration", 0) or 0) >= 8]
    if not good:
        good = [c for c in cands if int(getattr(c, "width", 0) or 0) >= 1280]
    if not good:
        print("no clip for", query)
        return ""
    c = good[0]
    req = urllib.request.Request(c.url, headers={"User-Agent": "video-generator/1.0"})
    with urllib.request.urlopen(req, timeout=120) as r, open(f, "wb") as out:
        out.write(r.read())
    src = json.loads(SRC.read_text()) if SRC.is_file() else {}
    src[f.name] = {"query": query, "page": getattr(c, "source_url", ""), "file": c.url}
    SRC.write_text(json.dumps(src, indent=1))
    print("fetched", f.name, getattr(c, "source_url", ""))
    return f"footage/stock/{f.name}"


if __name__ == "__main__":
    for q in sys.argv[1:]:
        print(fetch(q))
