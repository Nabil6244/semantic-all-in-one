"""Where event footage comes from, each answer turned into the same clip record (weather.news.footage_pool.Clip).

    NASA Image and Video Library   https://images-api.nasa.gov/search?q=...&media_type=video
                                   NASA's own media is generally not copyrighted (public domain); a description that credits
                                   someone else ("Credit: ...", "courtesy of", "©") marks the clip for a check.
    Wikimedia Commons              https://commons.wikimedia.org/w/api.php (generator=search, filetype:video, imageinfo with
                                   extmetadata): the licence and author come from the file page's own metadata.
    YouTube, by video ID only      a video the user names (never a search): channel, title, publish date and licence from the
                                   app's own YouTube code (providers.youtube, imported unchanged; nothing is downloaded here).

Every function takes the fetch function (or the parsed answer), so the tests run on recorded answers with no network."""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import quote, urlencode

from .timeline import UTC

NASA_SEARCH = "https://images-api.nasa.gov/search"
NASA_ASSETS = "https://images-assets.nasa.gov/video/{id}/collection.json"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
NASA_THIRD_PARTY = re.compile(r"(credit:\s*(?!nasa)|courtesy of|©|copyright|all rights reserved)", re.I)


def _strip_html(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text or "")).strip()


# ---- NASA ------------------------------------------------------------------------------------------------------------

def nasa_search_url(query: str, year_start: Optional[int] = None, year_end: Optional[int] = None) -> str:
    q = {"q": query, "media_type": "video"}
    if year_start:
        q["year_start"] = str(year_start)
    if year_end:
        q["year_end"] = str(year_end)
    return f"{NASA_SEARCH}?{urlencode(q)}"


def nasa_clips(text: str) -> List[Dict[str, Any]]:
    """NASA search answer -> clip dicts (footage_pool.Clip fields)."""
    out = []
    for it in (json.loads(text).get("collection") or {}).get("items") or []:
        d = (it.get("data") or [{}])[0]
        nid = d.get("nasa_id")
        if not nid or d.get("media_type") != "video":
            continue
        desc = d.get("description") or ""
        notes = []
        if NASA_THIRD_PARTY.search(desc) or d.get("secondary_creator"):
            notes.append("the description credits someone other than NASA: check the rights of this clip")
        center = d.get("center") or ""
        out.append({"id": f"nasa:{nid}", "source": "nasa", "source_id": nid, "title": d.get("title") or nid, "description": desc[:600],
                    "date": (d.get("date_created") or "")[:10], "place": d.get("location") or "", "author": f"NASA{('/' + center) if center else ''}",
                    "licence": "public domain (NASA)", "licence_url": "https://www.nasa.gov/nasa-brand-center/images-and-media/",
                    "page_url": f"https://images.nasa.gov/details/{quote(nid)}", "media_url": "", "assets_url": it.get("href") or NASA_ASSETS.format(id=quote(nid)),
                    "notes": notes})
    return out


def nasa_pick_rendition(assets: List[str], prefer=("~medium.mp4", "~large.mp4", "~orig.mp4", "~small.mp4", "~mobile.mp4")) -> str:
    """The video file to use from a NASA collection.json list (720p medium first)."""
    for suffix in prefer:
        for a in assets:
            if a.endswith(suffix):
                return a.replace("http://", "https://", 1)
    return ""


# ---- Wikimedia Commons -----------------------------------------------------------------------------------------------

def commons_search_url(query: str, limit: int = 20) -> str:
    q = {"action": "query", "format": "json", "generator": "search", "gsrsearch": f"{query} filetype:video", "gsrnamespace": "6",
         "gsrlimit": str(limit), "prop": "imageinfo", "iiprop": "url|extmetadata|size|mime",
         "iiextmetadatafilter": "LicenseShortName|LicenseUrl|Artist|DateTimeOriginal|ImageDescription|Credit|UsageTerms|AttributionRequired"}
    return f"{COMMONS_API}?{urlencode(q)}"


def commons_clips(text: str) -> List[Dict[str, Any]]:
    out = []
    for p in ((json.loads(text).get("query") or {}).get("pages") or {}).values():
        ii = (p.get("imageinfo") or [{}])[0]
        em = ii.get("extmetadata") or {}
        val = lambda k: _strip_html(str((em.get(k) or {}).get("value", "")))  # noqa: E731
        title = p.get("title", "")
        date = val("DateTimeOriginal")
        m = re.search(r"\d{4}-\d\d-\d\d", date)
        out.append({"id": f"commons:{title}", "source": "commons", "source_id": title, "title": title.removeprefix("File:"),
                    "description": val("ImageDescription")[:600], "date": m.group(0) if m else "", "place": "", "author": val("Artist"),
                    "licence": val("LicenseShortName"), "licence_url": val("LicenseUrl"), "page_url": ii.get("descriptionurl", ""),
                    "media_url": ii.get("url", ""), "assets_url": "", "notes": []})
    return out


# ---- YouTube by video ID ---------------------------------------------------------------------------------------------

YT_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")


def youtube_info(video_id: str, extract: Optional[Callable[[str], Dict[str, Any]]] = None) -> Dict[str, Any]:
    """yt-dlp's info for one video, through the app's YouTube backend (providers.youtube.ytdlp_backend, imported unchanged).
    Metadata only: skip_download is set by the backend. Tests pass `extract` with a recorded dict."""
    if not YT_ID.match(video_id or ""):
        raise ValueError(f"{video_id!r} is not a YouTube video id (11 letters, digits, - or _)")
    if extract is None:
        from providers.youtube.ytdlp_backend import YtDlpBackend

        backend = YtDlpBackend()

        def extract(vid: str) -> Dict[str, Any]:
            with backend._ydl() as ydl:   # the backend's own options (IPv4, timeouts, no download)
                return ydl.extract_info(f"https://www.youtube.com/watch?v={vid}", download=False) or {}
    return extract(video_id)


def youtube_clip(video_id: str, info: Dict[str, Any]) -> Dict[str, Any]:
    up = str(info.get("upload_date") or "")
    date = f"{up[:4]}-{up[4:6]}-{up[6:8]}" if len(up) == 8 else ""
    lic = info.get("license") or ""
    return {"id": f"youtube:{video_id}", "source": "youtube", "source_id": video_id, "title": info.get("title") or video_id,
            "description": (info.get("description") or "")[:600], "date": date, "place": info.get("location") or "",
            "author": info.get("channel") or info.get("uploader") or "", "channel_id": info.get("channel_id") or "",
            "licence": lic, "licence_url": "", "page_url": f"https://www.youtube.com/watch?v={video_id}", "media_url": "", "assets_url": "",
            "duration": info.get("duration"), "notes": []}


def parse_date(text: str) -> Optional[datetime]:
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").replace(tzinfo=UTC)
    except (TypeError, ValueError):
        return None
