"""War Footage Director, Stage 2: specific queries from what the narration names, and a pooled candidate set.

docs/war/FOOTAGE_DIRECTOR_PLAN.md. The shared YouTube backend (providers/youtube/ytdlp_backend.YtDlpBackend) is IMPORTED, never changed: its flat
search (title, channel, duration, description snippet, verified flag) and yt-dlp's metadata call (upload date, full description, tags,
storyboards). Everything is cached per project (state/war/director_cache) so Retry and Render never search again. No Gemini, no API keys.

    build_queries(reading, csv_prompt="") -> [str]           3-5 short entity-first queries, no month words
    Searcher(cache_dir, backend=None, pause=1.2)
        .pool(queries, per_query=10)  -> [Candidate]       every result of every query, merged by video id (hits = queries that found it)
        .details(candidate)           -> dict              upload_date, description, tags, duration, storyboard (cached)
"""

from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from .narration_read import Reading, fold

AGENCY_PREFIXES = ("Reuters", "AP")
_MONTHS = r"(January|February|March|April|May|June|July|August|September|October|November|December)"
_DROP = re.compile(r"\b(" + _MONTHS + r"|\d{1,2}(st|nd|rd|th)?|(19|20)\d\d|footage|video|clip|b-?roll|archival|cinematic|real|authentic)\b", re.I)


@dataclass
class Candidate:
    video_id: str
    title: str = ""
    channel: str = ""
    duration: Optional[float] = None
    description: str = ""
    verified: bool = False
    views: Optional[int] = None
    url: str = ""
    queries: List[str] = field(default_factory=list)       # which queries found it (more = more central)
    rank: int = 99                                         # best position in any result list (1 = top)
    details: Dict[str, Any] = field(default_factory=dict)
    level_hint: str = ""                                   # set by the rules: 'contextual' for earlier footage of the same story

    @property
    def blocked(self) -> bool:
        """YouTube would not give this video's metadata or previews without signing in (age-restricted / 'graphic content')."""
        return bool(self.details) and not self.details.get("ok") and bool(self.details.get("sign_in"))

    @property
    def content_warning(self) -> str:
        m = re.search(r"\b(warning:?\s*graphic content|graphic content|graphic footage|viewer discretion|disturbing)\b", self.title or "", re.I)
        if m:
            return m.group(0).lower()
        return "age-restricted on YouTube" if self.blocked else ""   # render 042 crashed here: blocked, no warning words in the title

    def as_dict(self) -> Dict[str, Any]:
        d = dict(self.__dict__)
        d.pop("details", None)
        return d


def _clean(q: str) -> str:
    q = _DROP.sub(" ", q or "")
    q = re.sub(r"[^\w\s\-']", " ", q)
    return re.sub(r"\s+", " ", q).strip()


def _event_phrase(r: Reading) -> str:
    """What the camera would have filmed, in search words."""
    low = r.text.lower()
    rules = (
        (r"queue|wait|lines? at|gas(oline)? station|petrol station|shortage", "gas station queues"),
        (r"changed course|reroute|tankers?\b", "tankers"),
        (r"by rail|rail tank|\btrains?\b", "rail tank cars"),
        (r"repair", "repairs"),
        (r"power plant|power station|power line|\bgrid\b|energy|blackout", "strike power plant"),
        (r"\b(advanc|push|attacking|assault|offensive|cleared|captured|seized|freed|liberat)", "assault" if r.actor == "Russia" else "advance"),
        (r"from the air|missiles?", "missile drone attack"),
        (r"set .{0,30}on fire|ablaze|\bfire\b|burn", "fire"),
        (r"\bdrones?\b", "drone strike"),
        (r"strike|struck|\bhit\b|attack|bomb|shell|damag|shut down|halted|offline", "drone attack"),
    )
    for pat, phrase in rules:
        if re.search(pat, low):
            return phrase
    return ""


def topic_of(readings: Sequence[Reading]) -> Dict[str, str]:
    """The film's main facility class and target country (038: 'refinery' in Russia), so a scene that names neither still searches on topic."""
    from collections import Counter
    fac = Counter()
    for r in readings:
        for p in r.places:
            if p.site_type:
                fac[p.site_type] += 2
        for f in r.facilities:
            f = re.sub(r"(ies)$", "y", f)
            f = re.sub(r"s$", "", f)
            if f not in ("unit", "equipment", "position", "drone", "missile"):
                fac[f] += 1
    target = Counter(c for r in readings for c in r.countries if c != r.actor and c in ("Russia", "Ukraine"))
    return {"facility": fac.most_common(1)[0][0] if fac else "", "country": target.most_common(1)[0][0] if target else ""}


_ADJ = {"Ukraine": "Ukrainian", "Russia": "Russian"}


def _anchor(r: Reading, topic: Optional[Dict[str, str]] = None) -> str:
    """The most specific thing the scene names: a site ('Kirishi refinery'), a place (+ the film's facility when the place is a city that
    hosts it: 'Ryazan refinery'), countries moved between, else the facility class with its country."""
    topic = topic or {}
    for p in r.places:
        if p.site_type:
            base = re.sub(r"\s*\(.*\)$", "", p.name)
            short = re.sub(r"\s+(Refinery|Air Base|Naval Base|Oil Port|Oil Terminal|Port)$", "", base)
            return f"{short} refinery" if p.site_type == "refinery" else base
    for p in r.places:
        tf = topic.get("facility", "")
        if tf and tf in ("refinery",) and re.search(r"\b(unit|refin|plant|distillation)", r.text, re.I):
            return f"{p.name} {tf}"
        return p.name
    moving = next((f for f in r.facilities if re.match(r"(tankers?|ships?|vessels?)$", f)), "")
    if moving:
        cargo = re.search(r"\b(diesel|gasoline|oil|grain|crude|LNG)\b", r.text, re.I)
        side = _ADJ.get(r.actor, "") or _ADJ.get(topic.get("country", ""), "")
        return _join(side, cargo.group(1).lower() if cargo else "", moving if moving.endswith("s") else moving + "s")
    others = [c for c in r.countries if c not in (r.actor, "Russia", "Ukraine")]
    if others and "MOVEMENT" in r.types:
        return " ".join(others[:2])
    fac = next((f for f in r.facilities if f not in ("units", "unit", "equipment", "positions", "position", "rail", "drones", "drone",
                                                       "missiles", "missile")), "")
    target = next((c for c in r.countries if c in _ADJ and c != r.actor), "") or topic.get("country", "")
    if fac:
        return f"{_ADJ.get(target, '')} {fac}".strip()
    if topic.get("facility") and re.search(r"\b(equipment|units?|repair)", r.text, re.I):
        return f"{_ADJ.get(topic.get('country', ''), '')} {topic['facility']}".strip()
    return ""


def _join(*parts: str) -> str:
    """Words in order, each once ('Russian tankers' + 'tankers' -> 'Russian tankers')."""
    seen, out = set(), []
    for part in parts:
        for w in (part or "").split():
            k = re.sub(r"s$", "", w.lower())
            if k not in seen:
                seen.add(k)
                out.append(w)
    return " ".join(out)


def build_queries(r: Reading, csv_prompt: str = "", max_queries: int = 5, topic: Optional[Dict[str, str]] = None) -> List[str]:
    anchor = _anchor(r, topic)
    ev = _event_phrase(r)
    actor = _ADJ.get(r.actor, "")
    out: List[str] = []

    def add(q: str) -> None:
        q = _clean(q)
        if q and len(q.split()) >= 2 and q.lower() not in [x.lower() for x in out]:
            out.append(q)

    # the CSV prompt is the writer's own search for this line: it goes first (Moskva 2026-11-09: 'Moskva cruiser sinking' ran 4th, after
    # 'Black Sea' / 'Reuters Black Sea' / 'AP Black Sea', and the slots filled with grain-crisis and Odesa clips)
    for part in [x for x in re.split(r"\|\|", csv_prompt or "") if x.strip()][:2]:
        add(part)
    if anchor:
        add(_join(anchor, ev))
        for ag in AGENCY_PREFIXES:
            add(_join(ag, anchor, ev if not any(p.kind != "region" for p in r.places) else ""))
        add(_join(anchor, actor, ev) if actor and ev else _join(anchor, "attack" if ev in ("fire", "drone attack", "drone strike") else ev))
    elif ev:
        target = next((c for c in r.countries if c != r.actor), "")
        add(_join(actor, ev, target))
        add(_join("Reuters", actor, ev, target))
        add(_join("AP", actor, ev, target))
    return out[:max_queries]


class Searcher:
    """Pooled YouTube search + metadata with a per-project JSON cache. `backend` needs .search(q, max_results) -> objects with video_id,
    title, channel, duration (and optionally description / channel_is_verified / view_count); `info` fetches full metadata for an id."""

    def __init__(self, cache_dir: Path, backend: Any = None, info: Optional[Callable[[str], Dict[str, Any]]] = None,
                 pause: float = 1.2, log: Callable[[str], None] = lambda m: None,
                 captions: Optional[Callable[[str, str], str]] = None):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._backend = backend
        self._info = info
        self._captions = captions          # (url, ext) -> caption file text; tests pass a fake, the app fetches it
        self.pause = pause
        self.log = log
        self._lock = threading.Lock()
        self._last = 0.0
        self.calls = {"search": 0, "details": 0, "transcript": 0}

    # ---- transcripts (moment relevance: the cut must sit where the video talks about the line's subject) ----
    def _caption_text(self, url: str, ext: str) -> str:
        if self._captions is not None:
            return self._captions(url, ext)
        import requests

        r = requests.get(url, timeout=20)
        r.raise_for_status()
        return r.text

    def _segments_from_info(self, info: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
        """[{start, duration, text}] from the English captions (uploaded, else automatic) of a yt-dlp info dict; None = the video has none."""
        track = None
        for key in ("subtitles", "automatic_captions"):
            tracks = info.get(key) or {}
            for lang in ("en", "en-US", "en-GB", "en-orig"):
                if tracks.get(lang):
                    track = tracks[lang]
                    break
            if track:
                break
        if not track:
            return None
        entry = next((e for e in track if e.get("ext") == "json3"), None) or next((e for e in track if e.get("ext") == "vtt"), None)
        if not entry or not entry.get("url"):
            return None
        from providers.youtube.ytdlp_backend import parse_json3, parse_vtt

        text = self._caption_text(entry["url"], entry["ext"])
        segs = parse_json3(json.loads(text)) if entry["ext"] == "json3" else parse_vtt(text)
        return [{"start": float(s.start), "duration": float(s.duration), "text": s.text} for s in segs]

    def transcript(self, video_id: str) -> Optional[List[Dict[str, Any]]]:
        """The video's timed English transcript, cached per video ([] cached = the video has none). One metadata call + one caption file."""
        p = self._cache("t", video_id)
        hit = self._read(p)
        if hit is not None:
            return hit.get("segments")
        self._wait()
        self.calls["transcript"] += 1
        segs: Optional[List[Dict[str, Any]]] = None
        try:
            segs = self._segments_from_info(self._fetch_info(video_id) or {})
        except Exception as exc:  # noqa: BLE001 - no transcript: the moment cannot be checked, the caller decides
            self.log(f"transcript failed for {video_id}: {str(exc)[:160]}")
            return None
        try:
            p.write_text(json.dumps({"segments": segs}), encoding="utf-8")
        except OSError:
            pass
        return segs

    # ---- backends (lazy: importing yt-dlp only when a real search runs) ----
    def backend(self) -> Any:
        if self._backend is None:
            from providers.youtube.ytdlp_backend import YtDlpBackend
            self._backend = YtDlpBackend()
        return self._backend

    def _fetch_info(self, video_id: str) -> Dict[str, Any]:
        if self._info is not None:
            return self._info(video_id)
        import yt_dlp
        with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "skip_download": True, "socket_timeout": 20}) as y:
            return y.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False) or {}

    def _wait(self) -> None:
        with self._lock:
            gap = self.pause - (time.time() - self._last)
            if gap > 0:
                time.sleep(gap)
            self._last = time.time()

    def _cache(self, kind: str, key: str) -> Path:
        safe = re.sub(r"[^A-Za-z0-9_\-]+", "_", key)[:120]
        return self.cache_dir / f"{kind}_{safe}.json"

    def _read(self, p: Path) -> Optional[Any]:
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def search(self, query: str, n: int = 10) -> List[Dict[str, Any]]:
        p = self._cache("q", f"{n}_{fold(query).lower()}")
        hit = self._read(p)
        if hit is not None:
            return hit
        self._wait()
        self.calls["search"] += 1
        try:
            res = self.backend().search(query, max_results=n) or []
        except Exception as exc:  # noqa: BLE001 - one failed search leaves the pool smaller, never stops the scene
            self.log(f"search failed for '{query}': {exc}")
            return []
        rows = [{"video_id": getattr(c, "video_id", ""), "title": getattr(c, "title", "") or "", "channel": getattr(c, "channel", "") or "",
                 "duration": getattr(c, "duration", None), "description": getattr(c, "description", "") or "",
                 "verified": bool(getattr(c, "channel_is_verified", False)), "views": getattr(c, "view_count", None),
                 "url": getattr(c, "url", "") or ""} for c in res if getattr(c, "video_id", "")]
        try:
            p.write_text(json.dumps(rows), encoding="utf-8")
        except OSError:
            pass
        return rows

    def pool(self, queries: Sequence[str], per_query: int = 10, cancel: Callable[[], bool] = lambda: False) -> List[Candidate]:
        out: Dict[str, Candidate] = {}
        for q in queries:
            if cancel():
                break
            for i, row in enumerate(self.search(q, per_query), start=1):
                c = out.get(row["video_id"])
                if c is None:
                    c = out[row["video_id"]] = Candidate(**{k: row.get(k) for k in ("video_id", "title", "channel", "duration", "description",
                                                                                      "verified", "views", "url")})
                c.queries.append(q)
                c.rank = min(c.rank, i)
        return list(out.values())

    def details(self, c: Candidate) -> Dict[str, Any]:
        """upload_date (YYYYMMDD), description, tags, duration, channel, verified and the storyboard (finest level) of one video."""
        if c.details:
            return c.details
        p = self._cache("v", c.video_id)
        d = self._read(p)
        if d is None:
            self._wait()
            self.calls["details"] += 1
            err = ""
            try:
                info = self._fetch_info(c.video_id) or {}
            except Exception as exc:  # noqa: BLE001 - no details: inspected another way (thumbnails), never called irrelevant
                err = str(exc)
                self.log(f"details failed for {c.video_id}: {err[:160]}")
                info = {}
            d = {"upload_date": info.get("upload_date") or "", "description": info.get("description") or "", "tags": info.get("tags") or [],
                 "duration": info.get("duration"), "channel": info.get("channel") or c.channel, "verified": bool(info.get("channel_is_verified")),
                 "is_live": bool(info.get("is_live") or info.get("was_live")), "storyboard": storyboard_of(info), "ok": bool(info),
                 "error": err[:300], "sign_in": bool(re.search(r"sign in|age|inappropriate|confirm your age|login", err, re.I)) if err else False}
            try:
                p.write_text(json.dumps(d), encoding="utf-8")
            except OSError:
                pass
        c.details = d
        if d.get("description") and len(d["description"]) > len(c.description or ""):
            c.description = d["description"]
        if d.get("duration") and not c.duration:
            c.duration = float(d["duration"])
        return d


def storyboard_of(info: Dict[str, Any]) -> Dict[str, Any]:
    """The finest storyboard yt-dlp lists (sb0: 320x180 tiles, about one every 2 s) as {width, height, rows, columns, interval, fragments:
    [{url, duration}]}; {} when the video has none."""
    sbs = [f for f in (info.get("formats") or []) if str(f.get("format_id", "")).startswith("sb") and f.get("fragments")]
    if not sbs:
        return {}
    sb = max(sbs, key=lambda f: (f.get("width") or 0) * (f.get("height") or 0))
    fps = float(sb.get("fps") or 0) or 0.5
    return {"width": sb.get("width"), "height": sb.get("height"), "rows": sb.get("rows") or 1, "columns": sb.get("columns") or 1,
            "interval": round(1.0 / fps, 4), "fragments": [{"url": fr.get("url"), "duration": fr.get("duration")} for fr in sb["fragments"]]}
