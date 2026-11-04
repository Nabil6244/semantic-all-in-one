"""Real footage for a news-style Review (the leak channels' look: hands on the phone, dummies, renders, the screen in use): one YouTube search per
subject the script talks about (the phone + design / cameras / battery / ...), one piece of each of a few videos (after their intro), cut on the
video's own edits into short runs, cached in the film's folder. Every footage beat of the film then takes the next unused run of its subject.

Built on the News Doc harvester's YouTube code (weather.newsdoc.harvest: search, section download, scene cuts, cut + pad to 1920x1080). Nothing
here stops the film: a search with no result, a block or a failed download is a note, and those beats fall back to stock (footage.resolve_footage)
or to a 3D shot.

    queries(parsed, phone)                                  -> {topic: query}
    resolve(parsed, out_dir, phone, backend=None, log=print) -> {"found", "missing", "runs", "notes"}
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

PIECE_S = 30.0          # seconds taken from each video
RUN_S = (2.0, 4.0)      # a news cut: 2-4 s (the reference channels' median shot is 2.0-2.4 s)
PER_TOPIC = 3           # videos per subject
MAX_VIDEOS = 18
CACHE_VERSION = "pt-news-1"
TOPIC_QUERY = {"design": "{p} dummy unit hands on", "camera": "{p} camera leak", "battery": "{p} battery charging", "display": "{p} display",
               "chip": "{p} snapdragon performance", "price": "{old} hands on", None: "{p} leak"}


def _family(phone: str) -> str:
    """The model token a title must name ("S27" for Galaxy S27 Ultra, "iPhone 18" for iPhone 18 Pro)."""
    m = re.search(r"\b(S\d{2}|iPhone \d+|Pixel \d+)\b", phone or "", re.I)
    return m.group(1) if m else (phone or "").split(" ")[0]


def queries(parsed: Dict[str, Any], phone: str, older: str = "") -> Dict[Optional[str], str]:
    """One search per subject that has footage beats: "Galaxy S27 Ultra dummy unit hands on", "Galaxy S27 Ultra battery charging", ..."""
    topics = {it.get("topic") for ch in parsed["chapters"] for it in ch["items"] if it.get("kind") == "footage" and not it.get("path")}
    old = older or re.sub(r"(\d+)", lambda m: str(int(m.group(1)) - 1), phone or "", count=1)   # Galaxy S27 Ultra -> Galaxy S26 Ultra (the phone you can buy)
    return {t: TOPIC_QUERY.get(t, TOPIC_QUERY[None]).format(p=phone, old=old) for t in topics}


def _pick(cands: List[Any], token: str, used: set) -> List[Any]:
    """Videos about this phone (its model named in the title), report length, not live, not already used."""
    out = []
    for c in cands:
        title, dur = str(getattr(c, "title", "")), getattr(c, "duration", None) or 0
        if c.video_id in used or not re.search(re.escape(token), title, re.I) or re.search(r"\blive\b|stream|#shorts", title, re.I):
            continue
        if dur and not 90 <= dur <= 2400:
            continue
        out.append(c)
    return out


def _runs(piece: Path, dest_dir: Path, stem: str, H) -> List[str]:
    """The piece cut into 2-4 s runs that start on its own edits."""
    length = H.media_seconds(piece)
    cuts = sorted({0.0} | {c for c in H.scene_cuts(piece) if 0.3 < c < length - 1.0})
    out, a, n = [], 0.0, 0
    while length - a >= RUN_S[0]:
        nxt = [c for c in cuts if a + RUN_S[0] <= c <= a + RUN_S[1]]
        z = nxt[0] if nxt else min(a + 3.0, length)
        dest = dest_dir / f"{stem}_{n:02d}.mp4"
        if H._cut(piece, a, z, dest):
            out.append(dest.name)
            n += 1
        a = z
    return out


def resolve(parsed: Dict[str, Any], out_dir: Any, phone: str, *, backend=None, log: Callable[[str], None] = print, pause: float = 2.0,
            max_videos: int = MAX_VIDEOS) -> Dict[str, Any]:
    """Set `path` on the footage beats from YouTube runs of their subject. Returns {"found", "missing", "runs", "notes"}."""
    from weather.newsdoc import harvest as H

    cache = Path(out_dir) / "news_cache"
    cache.mkdir(parents=True, exist_ok=True)
    qs = queries(parsed, phone)
    notes: List[str] = []
    key = CACHE_VERSION + "|" + "|".join(f"{t}={q}" for t, q in sorted(qs.items(), key=lambda kv: str(kv[0])))
    index_path = cache / "index.json"
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        index = {}
    pools: Dict[str, List[str]] = {}
    if index.get("key") == key:
        pools = {t: [r for r in rs if H.usable(cache / r, 1.0)] for t, rs in index.get("pools", {}).items()}
        notes.append("news footage: runs from the cache (YouTube not asked again)")
    else:
        if backend is None:
            try:
                from providers.youtube.ytdlp_backend import YtDlpBackend

                backend = YtDlpBackend()
            except Exception as exc:  # noqa: BLE001 -- no YouTube here: the beats use stock
                notes.append(f"news footage: YouTube is not available ({exc}); stock footage is used")
                backend = None
        used: set = set()
        videos = 0
        token = _family(phone)
        for topic, q in qs.items():
            if backend is None or videos >= max_videos:
                break
            try:
                cands = _pick(H._search(backend, q), token, used)[:PER_TOPIC]
            except Exception as exc:  # noqa: BLE001
                notes.append(f"news footage: search '{q}' failed ({type(exc).__name__})")
                continue
            if not cands:
                notes.append(f"news footage: nothing found for '{q}'")
            for c in cands:
                if videos >= max_videos:
                    break
                used.add(c.video_id)
                dur = getattr(c, "duration", None) or 300.0
                start = min(max(20.0, dur * 0.2), max(0.0, dur - PIECE_S - 5))       # past the intro, never past the end
                piece = cache / f"piece_{c.video_id}.mp4"
                ok = piece.is_file() or H._direct(c, start, PIECE_S, piece)
                videos += 1
                if not ok:
                    notes.append(f"news footage: '{c.title[:50]}' did not download")
                    continue
                pools.setdefault(str(topic), []).extend(_runs(piece, cache, f"run_{c.video_id}", H))
                time.sleep(pause)
        index_path.write_text(json.dumps({"key": key, "pools": pools}, indent=1), encoding="utf-8")
    found = missing = 0
    taken: Dict[str, int] = {}
    every = [r for rs in pools.values() for r in rs]
    for ch in parsed["chapters"]:
        for it in ch["items"]:
            if it.get("kind") != "footage" or it.get("path"):
                continue
            pool = pools.get(str(it.get("topic"))) or every                    # its own subject first, else any run of this phone
            i = taken.get(id(pool), 0)
            if pool and i < len(pool) * 2:
                it["path"] = str(cache / pool[i % len(pool)])                   # a run is reused only once the whole pool has been seen
                taken[id(pool)] = i + 1
                found += 1
            else:
                missing += 1
    log(f"News footage: {found} beats from {len(every)} runs, {missing} without footage")
    return {"found": found, "missing": missing, "runs": len(every), "notes": notes}
