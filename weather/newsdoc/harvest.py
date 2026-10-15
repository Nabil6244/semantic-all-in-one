"""News footage of the event for News Doc: few searches, few downloads, many shots (docs/weather/news_footage_plan.md §2).

One search per part of the story (place + hazard + month), through the app's own YouTube code (providers.youtube); the results
are ranked by the place and the hazard named in the title, local news channels and report-length uploads first; livestreams,
compilations and very long uploads are skipped. From each chosen video ONE piece (~40 s, after the studio intro) is downloaded and
cut locally into continuous runs of 5-15 s (the reference plays a station's report as one run, its own cuts and lower third
included). Runs are muted and padded to 1920x1080, never cropped (the station's graphics stay).

Everything is cached in weather/_work/news_cache (index.json + the runs): a re-render or a Retry asks YouTube nothing. One request
at a time with a pause; any failure (no result, a block, a download that does not finish) is a note and that part falls back to
stock footage — the video never stops for it."""

from __future__ import annotations

import json
import re
import subprocess
import time
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

PIECE_S = 40.0
INTRO_S = 8.0           # a report usually opens on the studio anchor
RUN_MIN_S, RUN_MAX_S = 5.0, 12.0
MAX_DOWNLOADS = 48
PER_PART = 6            # videos per part (the reference cuts many uploads of each place)
PLACE_PER_PART = 2      # of them: drone / aerial footage of the town itself
NEWS_CHANNEL = re.compile(r"\b(K[A-Z]{2,3}|W[A-Z]{2,3}|NBC|CBS|ABC|FOX|CNN|AP|Reuters|News|Weather|WFAA|KFOR|KOCO|KWTV|KWES|KOSA|"
                          r"Channel\s?\d+|\d+\s?News|First Alert|Storm Team|Eyewitness)\b", re.I)
SKIP_TITLE = re.compile(r"\b(live|livestream|24/7|compilation|explained|reaction|shorts|#shorts|music|game|minecraft|asmr|lofi|"
                        r"full episode|podcast|documentary|top \d+|best|comparison|size|simulation|school|elementary|football|"
                        r"sports|recipe|tour|vlog|forecast update|outlook)\b", re.I)
CACHE_VERSION = "11"
MAX_VIDEO_S = 600      # longer uploads are shows and compilations, not a report of the event
SHORT_VIDEO_S = 240    # above this, only a news channel's upload is taken
# YouTube's own "upload date" filter (the results page's sp parameter): yesterday's local reports are buried under old, popular videos
# in a plain search (Fort Stockton, Oct 2026: 8 searches, only 2019-2025 storms), and this yt-dlp has no date-sorted search
UPLOAD_FILTER = ((7, "EgIIAw%253D%253D"), (31, "EgIIBA%253D%253D"), (366, "EgIIBQ%253D%253D"))   # this week / month / year
SHORT_PIECE_S = 20.0   # a download that comes back shorter than this gets a second piece from later in the same video
WINDOW_BEFORE, WINDOW_AFTER = 3, 60   # days around the event an upload may have
NOT_TOWN = {"The", "This", "That", "Texas", "Oklahoma", "Ohio", "National", "Weather", "Service", "Central", "Time", "County", "Counties",
            "River", "Warning", "Watch", "Statement", "Special", "Severe", "Thunderstorm", "Tornado", "Flood", "Flooding", "Major", "Minor",
            "Moderate", "Bottom", "Line", "Here", "Turning", "Finally", "Right", "Stay", "Turn"} | set(
    "January February March April May June July August September October November December Monday Tuesday Wednesday Thursday "
    "Friday Saturday Sunday".split())
HAZARD_WORDS = {"tornado": ["tornado", "twister", "funnel"], "severe": ["storm", "storms", "hail", "wind", "thunderstorm", "damage"],
                "flood": ["flood", "flooding", "floods", "river", "flooded", "rain"], "heavy_rain": ["rain", "flooding", "flood"],
                "hurricane": ["hurricane", "storm surge", "landfall"], "tropical_storm": ["tropical storm", "storm"],
                "winter": ["snow", "blizzard", "ice", "winter storm"], "heat": ["heat", "heat wave"], "forecast": ["weather", "forecast"]}
TOPIC = {"tornado": "tornado", "severe": "storm damage", "flood": "flooding", "heavy_rain": "flooding", "hurricane": "hurricane",
         "tropical_storm": "tropical storm", "winter": "winter storm", "heat": "heat wave", "forecast": "weather"}
MONTHS = "January February March April May June July August September October November December".split()


@dataclass
class Run:
    path: str           # relative to the Weather project folder
    video_id: str
    title: str
    channel: str
    url: str
    part: int
    place: str
    start: float        # where in the source video
    dur: float


@dataclass
class Harvest:
    runs: List[Run] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    searches: List[str] = field(default_factory=list)
    downloads: int = 0
    cached: bool = False

    def credits(self) -> List[str]:
        seen, out = set(), []
        for r in self.runs:
            if r.video_id not in seen:
                seen.add(r.video_id)
                out.append(f"News footage: {r.channel} — \"{r.title}\" ({r.url})")
        return out


def _part_hazard(story, part: int) -> str:
    from ..intel.understand import pick_category, score_categories

    text = " ".join(x.text for x in story.lines if x.part == part)
    cat, _h = pick_category(score_categories(text), [])
    return cat if cat in TOPIC else (story.category if story.category in TOPIC else "severe")


def towns(lines) -> List[str]:
    """Towns the lines name in passing ('8 miles northwest of Truscott', 'near Fort Stockton'), most named first."""
    found: Dict[str, int] = {}
    for x in lines:
        for m in re.finditer(r"\b(?:of|near|in|through|over|outside)\s+([A-Z][a-z]+(?:\s[A-Z][a-z]+)?)", x.text):
            name = m.group(1)
            if re.search(r"(Service|NWS|office|Office|Center|Centre)$", x.text[:m.start()].rstrip()):
                continue   # "the National Weather Service in Midland": the forecast office, not where the storm was
            if name.split()[0] in NOT_TOWN or name.split()[-1] in NOT_TOWN:
                continue
            found[name] = found.get(name, 0) + 1
    return sorted(found, key=lambda n: -found[n])


def queries(story, event: Dict, extra: Optional[Dict[int, List[str]]] = None) -> List[Dict]:
    """Searches per part: [{part, queries, place, words, state, hazard, month, year}] — a local search first (a town or county with
    the hazard), then the state with the month; `words` are the local names a title may share."""
    day = str((event or {}).get("main_day") or "")
    month, year = (MONTHS[int(day[5:7]) - 1], day[:4]) if len(day) >= 7 else ("", "")
    out, seen = [], set()
    for k, (first, title) in enumerate(story.parts):
        lines = [x for x in story.lines if x.part == k]
        county = next((p[0] for x in lines for p in x.places), "")
        town = next(iter(towns(lines)), "")
        state = next((s for x in lines for s in x.states), story.states[0] if story.states else "")
        hz = _part_hazard(story, k)
        topic = TOPIC.get(hz, "storm")
        local = town or county
        qs = [q for q in (f"{local} {state} {topic}".strip() if local else "", " ".join(x for x in (state, topic, month, year) if x)) if q]
        qs = [q for q in list((extra or {}).get(k, [])) + qs if q.lower() not in seen]   # the story CSV's own searches first
        if not qs:
            continue
        seen.update(q.lower() for q in qs)
        rivers = [m.group(0) for x in lines for m in re.finditer(r"\b[A-Z][a-z]+(?:\s[A-Z][a-z]+)?\s(?:River|Creek|Bayou|Lake)\b", x.text)]
        words = sorted({n.strip().lower() for n in [county.replace("County", ""), *towns(lines), *rivers] if len(n.strip()) > 3})
        place_q = f"{local} {state} drone".strip() if local else ""
        out.append({"part": k, "queries": qs, "query": qs[0], "place_query": place_q, "place": local or state, "words": words, "state": state.lower(),
                    "hazard": HAZARD_WORDS.get(hz, ["storm"]), "month": month.lower(), "year": year})
    return out


def _wrong_date(title: str, q: Dict) -> bool:
    """A title that names another year or another month is about another event."""
    years = set(re.findall(r"\b(19[5-9]\d|20\d\d)\b", title))
    if q.get("year") and years and q["year"] not in years:
        return True
    months = {m.lower() for m in MONTHS if re.search(r"\b" + m[:3] + r"[a-z]*\.?\b", title, re.I)}
    return bool(q.get("month") and months and q["month"] not in months)


def rank_place(cands, q: Dict) -> List:
    """Drone / aerial footage of the town itself (the reference's most used shot): the title names the place; no event date needed
    (it shows the place, not the storm); no compilations or long shows."""
    out = []
    for c in cands:
        title = f"{c.title}".lower()
        dur = c.duration or 0.0
        if SKIP_TITLE.search(c.title or "") or not dur or dur < 20 or dur > MAX_VIDEO_S:
            continue
        if not any(re.search(r"\b" + re.escape(w) + r"\b", title) for w in q.get("words", [])):
            continue
        out.append((2.0 if re.search(r"\b(drone|aerial|4k|flyover|from above)\b", title) else 0.0, c))
    return [c for _s, c in sorted(out, key=lambda p: -p[0])]


def rank(cands, q: Dict) -> List:
    """The search results worth a download, best first: the hazard AND a local name (or the state with the event's month) in the
    title; never another year or month, never a livestream, a compilation or something that is not a report."""
    scored = []
    for c in cands:
        title = f"{c.title}".lower()
        dur = c.duration or 0.0
        if SKIP_TITLE.search(c.title or "") or not dur or dur < 15 or dur > MAX_VIDEO_S or _wrong_date(c.title or "", q):
            continue
        if dur > SHORT_VIDEO_S and not NEWS_CHANNEL.search(c.channel or ""):
            continue   # a long upload from a channel that is not a station is usually a compilation of other footage
        local_hit = any(re.search(r"\b" + re.escape(w) + r"\b", title) for w in q.get("words", []))
        state_hit = bool(q.get("state")) and q["state"] in title
        month_hit = bool(q.get("month")) and q["month"] in title
        hazard_hit = any(w in title for w in q["hazard"])
        if not hazard_hit or not (local_hit or (state_hit and month_hit)):
            continue
        s = 3.0 * local_hit + 1.0 * state_hit + 1.0 * month_hit + (1.5 if NEWS_CHANNEL.search(c.channel or "") else 0.0) + \
            (1.0 if 30 <= dur <= 420 else 0.0)
        scored.append((s, c))
    return [c for _s, c in sorted(scored, key=lambda p: -p[0])]


def _ffmpeg() -> str:
    try:
        from map_scene.render import _ffmpeg as find

        return find()
    except Exception:
        return "ffmpeg"


def scene_cuts(path: Path) -> List[float]:
    """Cut times inside a downloaded piece (its own edits)."""
    try:
        p = subprocess.run([_ffmpeg(), "-hide_banner", "-nostats", "-i", str(path), "-vf", "scale=320:-2,select='gt(scene,0.3)',showinfo",
                            "-an", "-f", "null", "-"], capture_output=True, text=True, timeout=120)
        return [float(x) for x in re.findall(r"pts_time:([0-9.]+)", p.stderr)]
    except Exception:
        return []


def run_windows(length: float, cuts: Sequence[float]) -> List[tuple]:
    """Continuous runs of RUN_MIN_S..RUN_MAX_S covering a piece, starting on its own cuts where it has them."""
    marks = sorted({0.0} | {c for c in cuts if 0.5 < c < length - 1.0})
    out, a = [], 0.0
    while length - a >= RUN_MIN_S:
        nxt = [m for m in marks if a + RUN_MIN_S <= m <= a + RUN_MAX_S]
        z = nxt[-1] if nxt else min(a + 8.0, length)
        if length - z < RUN_MIN_S:   # the rest is too short for a run of its own: this run takes it
            z = min(length, a + RUN_MAX_S + 3.0)
        out.append((round(a, 2), round(z, 2)))
        a = z
    return out


def media_seconds(path: Path) -> float:
    """A file's real length (0 when it cannot be read: an empty or broken file)."""
    try:
        from map_scene.render import _ffmpeg as find

        probe = str(Path(find()).with_name("ffprobe"))
        if not Path(probe).is_file():
            probe = "ffprobe"
    except Exception:
        probe = "ffprobe"
    try:
        r = subprocess.run([probe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)], capture_output=True,
                           text=True, timeout=60)
        return float(r.stdout.strip() or 0.0)
    except Exception:
        return 0.0


def usable(path: Path, want: float = 1.0) -> bool:
    return path.is_file() and path.stat().st_size > 1000 and media_seconds(path) >= want


def _portrait(path: Path) -> bool:
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0",
                            str(path)], capture_output=True, text=True, timeout=30)
        w, h = (int(v) for v in r.stdout.strip().split(",")[:2])
        return h > w
    except Exception:
        return False


def _cut(src: Path, a: float, z: float, dest: Path) -> bool:
    vf = "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,fps=30"
    if _portrait(src):   # a phone video fills the frame (cropped), never pillarboxed between black bars
        vf = "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,setsar=1,fps=30"
    try:
        p = subprocess.run([_ffmpeg(), "-y", "-v", "error", "-ss", f"{a:.2f}", "-t", f"{z - a:.2f}", "-i", str(src), "-an", "-vf", vf,
                            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", str(dest)],
                           capture_output=True, text=True, timeout=300)
        ok = p.returncode == 0 and usable(dest, min(z - a, RUN_MIN_S) * 0.8)
        if not ok:
            dest.unlink(missing_ok=True)
        return ok
    except Exception:
        return False


def _search(backend, query: str, age_days: Optional[int] = None) -> List:
    """Search results; for a recent event, only videos uploaded since (YouTube's own upload-date filter), else a plain search."""
    sp = next((code for days, code in UPLOAD_FILTER if age_days is not None and 0 <= age_days <= days), None)
    if sp and hasattr(backend, "_ydl") and hasattr(backend, "_candidate_from_search_entry"):
        from urllib.parse import quote_plus

        try:
            url = f"https://www.youtube.com/results?search_query={quote_plus(query)}&sp={sp}"
            with backend._ydl({"extract_flat": "in_playlist", "playlistend": 12}) as ydl:
                info = ydl.extract_info(url, download=False)
            found = [c for c in (backend._candidate_from_search_entry(e) for e in (info or {}).get("entries") or [] if e) if c]
            if found:
                return found[:12]
        except Exception:
            pass
    return list(backend.search(query, 12))


def upload_date(backend, cand) -> Optional[date]:
    """The video's upload day (one page read; None when it cannot be read — e.g. a test backend)."""
    if not hasattr(backend, "_ydl"):
        return None
    try:
        with backend._ydl() as ydl:
            info = ydl.extract_info(cand.url or f"https://www.youtube.com/watch?v={cand.video_id}", download=False, process=False)
        d = str((info or {}).get("upload_date") or "")
        return date(int(d[:4]), int(d[4:6]), int(d[6:8])) if len(d) == 8 else None
    except Exception:
        return None


def in_window(day: Optional[date], event_day: str) -> bool:
    if day is None or len(event_day) < 10:
        return True
    ev = date.fromisoformat(event_day[:10])
    return -WINDOW_BEFORE <= (day - ev).days <= WINDOW_AFTER


PARALLEL = 3   # pieces downloaded at once (direct downloads; the browser capture, the fallback, runs one at a time by itself)


def _direct(cand, start: float, length: float, dest: Path) -> bool:
    """The app's own non-browser download (yt-dlp, a section of the video), safe to run several at once."""
    try:
        from providers.youtube.strategies import _legacy_yt_dlp_chain, run_strategy_chain

        out = run_strategy_chain(_legacy_yt_dlp_chain("bestvideo[height<=720]+bestaudio/best[height<=720]/best"), cand, start, length,
                                 dest, lambda m: None)
        return bool(out.ok) and dest.is_file()
    except Exception:
        return False


def _download_all(chosen, cache: Path, root: Path, backend, out: "Harvest", max_downloads: int, log) -> None:
    """Each chosen video's pieces, PARALLEL at a time: the first piece of every video, then later pieces of the videos whose first
    piece came back short. Each piece is cut into runs as soon as it arrives. Runs keep the order of the parts and the ranking."""
    import threading
    from concurrent.futures import ThreadPoolExecutor

    lock = threading.Lock()
    results: Dict[tuple, List[Run]] = {}
    direct_ok = hasattr(backend, "_ydl")   # a real YouTube backend (tests use a stand-in that has no direct path)

    def piece_job(order: int, c, q, start: float, n_piece: int) -> float:
        p_start = start + n_piece * (PIECE_S * 0.75)
        p_len = max(0.0, min(PIECE_S, (c.duration or 0) - p_start - 1.0))
        if p_len < RUN_MIN_S:
            return 0.0
        piece = cache / f"{c.video_id}_piece{n_piece or ''}.mp4"
        if not usable(piece, RUN_MIN_S):
            with lock:
                if out.downloads >= max_downloads:
                    return 0.0
                out.downloads += 1
            piece.unlink(missing_ok=True)
            log(f"[Weather] News Doc: downloading {p_len:.0f}s of \"{c.title}\" ({c.channel})")
            ok = direct_ok and _direct(c, p_start, p_len, piece)
            if not ok:
                try:
                    backend.download_segment(c, p_start, p_len, piece, log=log)
                except Exception as exc:
                    with lock:
                        out.notes.append(f"news footage: \"{c.title}\" could not be downloaded ({str(exc)[:120]})")
                    piece.unlink(missing_ok=True)
                    return 0.0
        real = media_seconds(piece) if piece.is_file() else 0.0
        if real < RUN_MIN_S:
            piece.unlink(missing_ok=True)
            return 0.0
        runs = []
        for k, (a, z) in enumerate(run_windows(real, scene_cuts(piece))):
            dest = cache / f"{c.video_id}_p{n_piece}r{k}.mp4"
            if usable(dest, (z - a) * 0.8) or _cut(piece, a, z, dest):
                runs.append(Run(str(dest.relative_to(root)), c.video_id, c.title, c.channel, c.url, q["part"], q["place"],
                                round(p_start + a, 2), round(min(z - a, media_seconds(dest) or (z - a)), 2)))
        with lock:
            results[(order, n_piece)] = runs
        return real

    with ThreadPoolExecutor(max_workers=PARALLEL) as pool:
        firsts = {k: pool.submit(piece_job, k, c, q, st, 0) for k, (c, q, st) in enumerate(chosen)}
        more = []
        for k, f in firsts.items():
            got = f.result()
            if 0 < got < SHORT_PIECE_S:   # a short piece: more of the same video, from later in it
                c, q, st = chosen[k]
                more += [pool.submit(piece_job, k, c, q, st, n) for n in (1, 2, 3)]
        for f in more:
            f.result()
    for key in sorted(results):
        out.runs += results[key]


def harvest(project_root: "str | Path", story, event: Dict, *, backend=None, pause: float = 3.0, max_downloads: int = MAX_DOWNLOADS,
            extra: Optional[Dict[int, List[str]]] = None,
            log: Callable[[str], None] = print, today: Optional[date] = None) -> Harvest:
    root = Path(project_root)
    cache = root / "_work" / "news_cache"
    cache.mkdir(parents=True, exist_ok=True)
    index_path = cache / "index.json"
    qs = queries(story, event, extra)
    key = CACHE_VERSION + "|" + "|".join(q["query"] for q in qs)
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        index = {}
    if index.get("key") == key and index.get("runs"):
        runs = [Run(**r) for r in index["runs"] if usable(root / r["path"], r.get("dur", 1.0) * 0.8)]
        if runs:
            return Harvest(runs=runs, searches=[q["query"] for q in qs], cached=True,
                           notes=[f"news footage: {len(runs)} run(s) from the cache (YouTube not asked again)"])
    out = Harvest(searches=[q["query"] for q in qs])
    if not qs:
        out.notes.append("news footage: the story names no place to search for; stock footage is used")
        return out
    if backend is None:
        try:
            from providers.youtube.ytdlp_backend import YtDlpBackend

            backend = YtDlpBackend()
        except Exception as exc:
            out.notes.append(f"news footage: YouTube is not available here ({exc}); stock footage is used")
            return out
    used_ids = set()
    chosen: List[tuple] = []
    day = str((event or {}).get("main_day") or "")
    age_days = ((today or date.today()) - date.fromisoformat(day[:10])).days if len(day) >= 10 else None
    for q in qs:
        if out.downloads >= max_downloads:
            break
        cands, failed = [], None

        def found(query, ranker, ages):
            nonlocal failed
            log(f"[Weather] News Doc: searching footage: {query}")
            for attempt in range(2):   # YouTube throttles quick requests ("Unable to download API page"): wait, try once more
                try:
                    got = [c for c in ranker(_search(backend, query, ages), q) if c.video_id not in used_ids]
                    time.sleep(pause)
                    return got
                except Exception as exc:
                    failed = exc
                    time.sleep(pause * 4)
            return []

        for query in q["queries"]:   # every news search of the part, not only the first that answers
            cands += [c for c in found(query, rank, age_days) if all(c.video_id != x.video_id for x in cands)]
        if q.get("place_query"):
            for c in found(q["place_query"], rank_place, None)[:PLACE_PER_PART]:
                if all(c.video_id != x.video_id for x in cands):
                    c.place_shot = True
                    cands.append(c)
        if not cands:
            out.notes.append(f"news footage: {'the search failed (' + str(failed)[:80] + ')' if failed else 'nothing relevant'} for "
                             f"{' / '.join(q['queries'])!r}; that part uses stock footage")
            continue
        taken = 0
        for c in cands:
            if taken >= PER_PART or out.downloads >= max_downloads:
                break
            if c.video_id in used_ids:
                continue
            up = None if getattr(c, "place_shot", False) else upload_date(backend, c)
            if up is None and hasattr(backend, "_ydl") and not getattr(c, "place_shot", False):   # throttled: one more try after a pause
                time.sleep(pause * 2)
                up = upload_date(backend, c)
            time.sleep(pause / 2)
            if not getattr(c, "place_shot", False) and not in_window(up, str((event or {}).get("main_day") or "")):
                out.notes.append(f"news footage: \"{c.title}\" is from {up}, not from this event; skipped")
                continue
            start = INTRO_S if (c.duration or 0) > 60 else 2.0
            length = max(0.0, min(PIECE_S, (c.duration or 0) - start - 1.0))
            if length < RUN_MIN_S:
                continue
            chosen.append((c, q, start))   # downloaded below, several at a time
            used_ids.add(c.video_id)
            taken += 1
    _download_all(chosen, cache, root, backend, out, max_downloads, log)
    try:
        index_path.write_text(json.dumps({"key": key, "runs": [asdict(r) for r in out.runs], "searches": out.searches}, indent=1),
                              encoding="utf-8")
    except OSError:
        pass
    out.notes.append(f"news footage: {len(out.runs)} run(s) from {len(used_ids)} video(s), {len(qs)} search(es), {out.downloads} download(s)")
    return out
