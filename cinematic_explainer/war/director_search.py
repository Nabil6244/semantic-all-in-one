"""War Footage Director, Stage 2: specific queries from what the narration names, and a pooled candidate set.

docs/war/FOOTAGE_DIRECTOR_PLAN.md. The shared YouTube backend (providers/youtube/ytdlp_backend.YtDlpBackend) is IMPORTED, never changed: its flat
search (title, channel, duration, description snippet, verified flag) and yt-dlp's metadata call (upload date, full description, tags,
storyboards). Everything is cached per project (state/war/director_cache) so Retry and Render never search again. No Gemini, no API keys.

    build_queries(reading, csv_prompt="") -> [str]           3-5 short entity-first queries, no month words
    Searcher(cache_dir, backend=None, pause=1.2)
        .pool(queries, per_query=10)  -> [Candidate]       every result of every query, merged by video id (hits = queries that found it)
        .details(candidate)           -> dict              upload_date, description, tags, duration, storyboard, captions, chapters (cached)
        .transcript(video_id)         -> [segment] | None  timed English captions; 429 retried with backoff, never cached as a failure
        .transcript_info(video_id)    -> (segments, status, chapters)   status in ok / none / rate_limited / error
"""

from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from .narration_read import Reading, fold

AGENCY_PREFIXES = ("Reuters", "AP")
_MONTHS = r"(January|February|March|April|May|June|July|August|September|October|November|December)"
RATE_LIMIT_COOLDOWN_S = 60.0   # a video YouTube rate-limited is not asked again for this long (live run: 7 x 429 for 3 videos in seconds)
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
        self.calls = {"search": 0, "details": 0, "transcript": 0, "transcript_rate_limited": 0}
        self.backoff: Sequence[float] = (4.0, 12.0)       # waits before the 2nd and 3rd try after HTTP 429; tests set (0, 0)
        self.transcript_status: Dict[str, str] = {}       # video id -> ok / none / rate_limited / error (in memory only)
        self._rate_limited_at: Dict[str, float] = {}
        self._details_mem: Dict[str, Dict[str, Any]] = {}

    # ---- transcripts (moment relevance: the cut must sit where the video talks about the line's subject) ----
    def _caption_text(self, url: str, ext: str) -> str:
        if self._captions is not None:
            return self._captions(url, ext)
        import requests

        r = requests.get(url, timeout=20)
        r.raise_for_status()
        return r.text

    @staticmethod
    def caption_track(info: Dict[str, Any]) -> Optional[Dict[str, str]]:
        """The English caption file to read: {ext, url} (uploaded subtitles before automatic captions; en, en-US, en-GB, en-orig; json3
        before vtt), None when the video has none."""
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
        return {"ext": str(entry["ext"]), "url": str(entry["url"])}

    def _segments_from_track(self, track: Optional[Dict[str, str]]) -> Optional[List[Dict[str, Any]]]:
        if not track:
            return None
        from providers.youtube.ytdlp_backend import parse_json3, parse_vtt

        text = self._caption_text(track["url"], track["ext"])
        segs = parse_json3(json.loads(text)) if track["ext"] == "json3" else parse_vtt(text)
        return [{"start": float(s.start), "duration": float(s.duration), "text": s.text} for s in segs]

    def _segments_from_info(self, info: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
        """[{start, duration, text}] from the English captions (uploaded, else automatic) of a yt-dlp info dict; None = the video has none."""
        return self._segments_from_track(self.caption_track(info))

    @staticmethod
    def _http_status(exc: BaseException) -> Optional[int]:
        """429 / 403 / 404 from a requests HTTPError or a yt-dlp message; None for anything else."""
        code = getattr(getattr(exc, "response", None), "status_code", None)
        if code in (429, 403, 404):
            return int(code)
        msg = str(exc)
        if re.search(r"\b429\b|too many requests", msg, re.I):
            return 429
        m = re.search(r"\b(403|404)\b", msg)
        return int(m.group(1)) if m else None

    def _cached_details(self, video_id: str) -> Optional[Dict[str, Any]]:
        d = self._details_mem.get(video_id)
        if d is None:
            d = self._read(self._cache("v", video_id))
        return d if isinstance(d, dict) else None

    def transcript(self, video_id: str) -> Optional[List[Dict[str, Any]]]:
        """The video's timed English transcript, cached per video ([] / null cached = the video has none). Uses the caption track details()
        already found (no second metadata call). HTTP 429 is retried after self.backoff, then remembered for RATE_LIMIT_COOLDOWN_S;
        a failure is never written to the disk cache, so a later run asks again."""
        p = self._cache("t", video_id)
        hit = self._read(p)
        if hit is not None:
            segs = hit.get("segments")
            self.transcript_status[video_id] = "ok" if segs else "none"
            return segs
        if self.transcript_status.get(video_id) == "rate_limited" and \
                time.time() - self._rate_limited_at.get(video_id, 0.0) < RATE_LIMIT_COOLDOWN_S:
            return None
        self.calls["transcript"] += 1
        d = self._cached_details(video_id)
        from_details = bool(d and d.get("ok") and "captions" in d)
        track: Optional[Dict[str, str]] = d.get("captions") if from_details else None
        have_track = from_details
        refetched = False
        delays = list(self.backoff or ())
        segs: Optional[List[Dict[str, Any]]] = None
        while True:
            self._wait()
            try:
                if not have_track:
                    track = self.caption_track(self._fetch_info(video_id) or {})
                    have_track = True
                segs = self._segments_from_track(track)
                break
            except Exception as exc:  # noqa: BLE001 - no transcript: the moment cannot be checked, the caller decides
                code = self._http_status(exc)
                if code == 429 and delays:
                    wait = delays.pop(0)
                    self.log(f"transcript for {video_id}: YouTube said 429 Too Many Requests, trying again in {wait:.0f} s")
                    if wait > 0:
                        time.sleep(wait)
                    continue
                if code == 429:
                    self.calls["transcript_rate_limited"] += 1
                    self.transcript_status[video_id] = "rate_limited"
                    self._rate_limited_at[video_id] = time.time()
                    self.log(f"transcript rate-limited for {video_id}: not checked, asked again after {RATE_LIMIT_COOLDOWN_S:.0f} s")
                    return None
                if code in (403, 404) and from_details and not refetched:
                    refetched, have_track = True, False   # the cached caption URL expired: ask for fresh metadata once
                    continue
                self.transcript_status[video_id] = "error"
                self.log(f"transcript failed for {video_id}: {str(exc)[:160]}")
                return None
        self.transcript_status[video_id] = "ok" if segs else "none"
        self._rate_limited_at.pop(video_id, None)
        try:
            p.write_text(json.dumps({"segments": segs}), encoding="utf-8")
        except OSError:
            pass
        return segs

    def transcript_info(self, video_id: str) -> Tuple[Optional[List[Dict[str, Any]]], str, List[Dict[str, Any]]]:
        """(segments, status, chapters) for director_moment.check(..., status=, chapters=) in one call."""
        segs = self.transcript(video_id)
        status = self.transcript_status.get(video_id) or ("ok" if segs else "none")
        d = self._cached_details(video_id) or {}
        return segs, status, list(d.get("chapters") or [])

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
                 "error": err[:300], "sign_in": bool(re.search(r"sign in|age|inappropriate|confirm your age|login", err, re.I)) if err else False,
                 "captions": self.caption_track(info), "chapters": chapters_of(info)}
            try:
                p.write_text(json.dumps(d), encoding="utf-8")
            except OSError:
                pass
        c.details = d
        self._details_mem[c.video_id] = d
        if d.get("description") and len(d["description"]) > len(c.description or ""):
            c.description = d["description"]
        if d.get("duration") and not c.duration:
            c.duration = float(d["duration"])
        return d


def chapters_of(info: Dict[str, Any]) -> List[Dict[str, Any]]:
    """[{start, title}] from yt-dlp's chapter list ([] when the uploader set none)."""
    out: List[Dict[str, Any]] = []
    for ch in info.get("chapters") or []:
        try:
            out.append({"start": float(ch.get("start_time") or 0.0), "title": str(ch.get("title") or "")})
        except (TypeError, ValueError, AttributeError):
            continue
    return out


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
