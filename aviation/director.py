"""Aviation footage director (docs/aviation/PLAN.md section 7, step 1): YouTube footage that shows the sentence, or no clip at all.

    run(scenes, images_dir, state_dir, search=None, tiles=None, capture=None, log, cancel) -> report

For every scene whose asset_type is youtube_video:
  1 queries      the CSV's own searches (|| separated) + the sentence's names (footage.queries_for); pooled, cached (War's Searcher)
  2 title rules  title_reject: promos / trailers / safety videos / cartoons / reactions / podcasts / shorts / live streams, and a named
                 aircraft type, or a news event of a named airline, that the title does not name (footage.clip_ok); title_score
                 ranks the rest (names matched, English first, how many searches found it)
  3 frames       the storyboard BEFORE any download (War's director_frames: studio, text screens, subtitles / tickers, title cards,
                 flat graphics, still, dark are not footage); the best clean, uncut 3-8 s window away from the first / last 5 %
  4 capture      that window only (War's director_capture), checked against the storyboard
  5 no repeats   at most 2 moments per video, never the same seconds or the same picture twice in a film
News and number lines get EXTRA_PER_NEWS more clips from other videos (state/<EXTRAS>), so a burst cuts between real shots.
A scene where nothing passes gets no clip: the planner shows a Flow shot or a card there, never a wrong clip. No Gemini, no API keys.
search / tiles / capture are injectable (tests use fakes; the app uses the shared YouTube search, storyboards and capture browser).
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from . import footage as FT
from . import router as R

EXTRAS = "aviation_extra_clips.json"
REPORT = "aviation_director_report.json"
SHORTLIST = 5
CAPTURE_TRIES = 2               # a failed capture costs about a minute: two tries, then the scene goes to Flow or a card
CAPTURE_LIMIT_S = 30.0          # aviation's own limit per capture (+2 s per clip second: 46 s for an 8 s clip; War waits 69 s)
SCENE_WORKERS = 3               # scenes captured at the same time (the shared browser pool records several clips at once)
EXTRA_PER_NEWS = 2
MAX_PER_VIDEO = 2
CLIP_S = 8.0

_JUNK = re.compile(r"\b(official\s+trailer|trailer|teaser|promo|safety\s+(?:video|demonstration|instructions?)|cartoon|animated|animation|"
                   r"reaction|reacts?|podcast|#shorts|shorts|live\s*stream|livestream|music\s+video|lyrics?|unboxing|asmr|"
                   r"free\s+documentary|full\s+documentary|full\s+movie|gameplay|let'?s\s+play|tier\s+list|ranking\s+every)\b", re.I)
_EN = set("the a an of and to in on for with at from new is are its how why what when after first flight airline airlines plane".split())
_OTHER = set("le la les des du de et une un sur pour avec est der die das und mit von ein eine el los las del con por para una il della "
             "per com uma dos não sa ses fait".split())


def classify_line(text: str) -> Any:
    return R.classify(text)


_AVIATION = re.compile(r"\b(airlines?|airways|air\s*lines?|airport|aircraft|airplane|aeroplane|planes?|jets?|jetliner|airliner|flights?|"
                       r"flying|takeoff|take\s*off|landing|cockpit|cabin|pilots?|crew|runway|terminal|airbus|boeing|embraer|aviation|hangar|"
                       r"spotting|tarmac|gate|departures?|arrivals?|livery|storm|thunderstorm|clouds?|rain|monsoon)\b", re.I)
_TRIP = re.compile(r"\b(trip\s*report|flight\s*report|flight\s*experience|review|vlog|cabin\s*tour|seat\s*review|unboxing|"
                   r"flying\s+(?:nonstop|non-stop|business|economy|first|premium)|my\s+(?:flight|trip|journey)|"
                   r"(?:economy|business|first|premium\s+economy)\s+class\s+(?:on|in|flight)|"
                   r"[A-Z]{3}\s*[-–→>]\s*[A-Z]{3}\s*(?:\||$)|"
                   r"\bin\s+(?:business|economy|first|premium\s+economy)(?:\s+class)?\b|\bultra\s+long\s+haul\s+with\b)", re.I)
# an explainer / education video: its pictures are stock offices, handshakes and slides, never the event itself
_EXPLAINER = re.compile(r"\bexplained\b|\bwhat\s+is\s+(?:a|an)\b|\bkinds\s+of\b|\btypes\s+of\b|\bupsc\b|\bcurrent\s+affairs\b|"
                        r"\bfor\s+beginners\b|\bclass\s+\d+\b|\blecture\b", re.I)
# the last ones: a passenger's own trip video ('FLYING NONSTOP', 'SIN - EWR |'); its captured moments are hotels, zoos and meals
# a sub-brand's own name may be missing from a title about it: the parent's name is accepted (Joon -> Air France)
PARENTS = {"joon": "air_france", "transavia": "air_france", "scoot": "singapore_airlines", "vistara": "air_india"}


def _airline_named(title: str, ids: Sequence[str]) -> bool:
    from . import catalog as C

    found = {m.entry["id"] for m in C.find_airlines(title) if m.entry}
    for a in ids:
        if a in found or PARENTS.get(a) in found or any(PARENTS.get(f) == a for f in found):
            return True
    return False


_FREIGHT = re.compile(r"\b(freighters?|cargo|skycargo|777f|747f|767f|\d{3}-?f\b|\bf\b)", re.I)


def min_stretch(mode: str) -> float:
    """The shortest clean, uncut stretch a clip must have: news bursts cut every 1-2 s, so 2 s will do; beauty shots need 3."""
    return 2.0 if mode in ("news", "numbers") else 3.0


def cache_dir(state_dir: Path) -> Path:
    """Searches and storyboards are kept per user, not per project: a second film (or a re-render) never searches the same thing twice."""
    try:
        from map_scene.render import cache_dir as _c
        return _c().parent / "aviation_director"
    except Exception:  # noqa: BLE001
        return Path.home() / ".cache" / "video-generator" / "aviation_director"


def title_reject(title: str, c: Any, people_line: bool = False, airlines: Sequence[str] = (), aircraft: Sequence[str] = (),
                 channel: str = "") -> str:
    """Why this video cannot show the line ('' = it may). The channel's name is checked for junk too (a podcast channel's video
    with a plain title is still a podcast)."""
    t = str(title or "")
    ch = _JUNK.search(str(channel or ""))
    if ch:
        return f"channel: {ch.group(0).lower()}"
    letters = [ch for ch in t if ch.isalpha()]
    if letters and sum(1 for ch in letters if ord(ch) > 0x24F) / len(letters) > 0.25:
        return "title: not in a Latin script (foreign subtitles / channel)"
    m = _JUNK.search(t)
    if m:
        return f"title: {m.group(0).lower()}"
    if re.search(r"\binterview\b", t, re.I) and not people_line:
        return "title: interview (a talking head)"
    mode = getattr(c, "mode", "")
    if mode in ("news", "numbers", "people", "evidence") and _TRIP.search(t):
        return f"title: {_TRIP.search(t).group(0).lower()} (a passenger's video, not the story)"
    if _EXPLAINER.search(t):
        return f"title: {_EXPLAINER.search(t).group(0).lower()} (an explainer video: stock pictures, not the event)"
    ok, _s, why = FT.clip_ok(t, c)
    if not ok:
        return f"title: {why}"
    if re.search(r"\bfreighters?\b|\bcargo\b", getattr(c, "text", ""), re.I) and getattr(c, "aircraft", None) and not _FREIGHT.search(t):
        return "title: a freighter / cargo line needs a freighter or cargo video"
    want_types = {a for a in aircraft if a} - {a["id"] for a in getattr(c, "aircraft", [])}
    if want_types:
        from . import catalog as C
        got = {m.entry["id"] for m in C.find_aircraft(t) if m.entry}
        if not want_types & got:
            return f"title: does not show {', '.join(sorted(want_types))}"
    named = [a["id"] for a in getattr(c, "airlines", [])] + [a for a in airlines if a]
    if named and not _airline_named(t, named):
        return f"title: does not name {', '.join(sorted(set(named)))}"
    subs = [a["id"] for a in getattr(c, "airlines", []) if a["id"] in PARENTS]
    if subs and mode in ("news", "numbers"):
        from . import catalog as C
        found = {m.entry["id"] for m in C.find_airlines(t) if m.entry}
        if not set(subs) & found:
            return f"title: a news line about {', '.join(subs)} needs a video about {', '.join(subs)} itself"
    if not named and not getattr(c, "aircraft", None) and not _AVIATION.search(t):
        return "title: nothing about aviation"
    return ""


def title_score(cand: Any, c: Any, airlines: Sequence[str] = ()) -> float:
    from . import catalog as C

    t = f"{cand.title} {cand.channel}"
    _ok, s, _why = FT.clip_ok(t, c)
    exact = {a["id"] for a in getattr(c, "airlines", [])} | {a for a in airlines if a}
    found = {m.entry["id"] for m in C.find_airlines(cand.title or "") if m.entry}
    if exact & found:
        s += 3.0                                    # the line's own airline by name, not only its parent
    words = re.findall(r"[a-zà-ÿ']+", (cand.title or "").lower())
    en = sum(w in _EN for w in words)
    other = sum(w in _OTHER for w in words)
    s += 1.5 if en > other else (-2.0 if other > en else 0.0)          # an English title first: no foreign subtitles to fight
    s += 0.5 * min(3, len(getattr(cand, "queries", []) or []))          # found by several searches: central to the subject
    s -= 0.05 * min(20, max(0, int(getattr(cand, "rank", 99) or 99) - 1))
    d = float(getattr(cand, "duration", 0) or 0)
    if d and (d < 20 or d > 3 * 3600):
        s -= 5.0
    return round(s, 2)


class Used:
    """Moments already in the film: same seconds never twice, at most MAX_PER_VIDEO moments of one video, the same picture never twice."""

    def __init__(self) -> None:
        self.moments: List[Dict[str, Any]] = []

    def conflict(self, vid: str, a: float, b: float, hashes: Sequence[str] = ()) -> bool:
        from cinematic_explainer.war.director_rules import hamming

        same = [m for m in self.moments if m["vid"] == vid]
        if len(same) >= MAX_PER_VIDEO or any(a < m["b"] + 2.0 and m["a"] < b + 2.0 for m in same):
            return True
        for m in self.moments:
            near = sum(1 for h in hashes if any(hamming(h, x) <= 10 for x in m["hashes"]))
            if near >= 2:
                return True
        return False

    def add(self, vid: str, a: float, b: float, hashes: Sequence[str]) -> Dict[str, Any]:
        m = {"vid": vid, "a": a, "b": b, "hashes": list(hashes)}
        self.moments.append(m)
        return m

    def drop(self, m: Dict[str, Any]) -> None:
        """A reserved moment whose capture failed is free again."""
        if m in self.moments:
            self.moments.remove(m)


# ---------------------------------------------------------------------------------------------------------------- the app's tools

def _default_tools(state_dir: Path, log):
    from cinematic_explainer.war import director_capture as C
    from cinematic_explainer.war import director_frames as F
    from cinematic_explainer.war import director_search as S

    searcher = S.Searcher(cache_dir(state_dir), log=log)

    def search(queries: Sequence[str]) -> List[Any]:
        return searcher.pool(list(queries), per_query=8)

    def tiles(c: Any) -> List[Any]:
        d = searcher.details(c)
        sb = d.get("storyboard") or {}
        return F.inspect(F.tiles_from_storyboard(sb) if sb else F.tiles_from_thumbnails(c.video_id, c.duration))

    from providers.youtube.acquisition.browser_client import get_client
    from cinematic_explainer.war.footage_director import bounded
    acquire = bounded(get_client().acquire, lambda sec: CAPTURE_LIMIT_S + 2.0 * float(sec))

    def capture(video_id: str, start: float, seconds: float, dest: Path, tl: Sequence[Any]) -> Dict[str, Any]:
        return C.capture(video_id, start, seconds, dest, tl, acquire=acquire, log=log)

    return search, tiles, capture


# ---------------------------------------------------------------------------------------------------------------- run

def _queries(sc: Dict[str, Any], c: Any) -> List[str]:
    own = [q.strip() for q in str(sc.get("prompt") or "").split("||") if q.strip()]
    out: List[str] = []
    for q in own + FT.queries_for(c):
        q = re.sub(r"\s+\bfootage\b", "", q).strip()
        if q and q.lower() not in [x.lower() for x in out]:
            out.append(q)
    return out[:4]


def _record(man: Any, no: str, sc: Dict[str, Any], cand: Any, win: Dict[str, Any], path: str) -> Dict[str, Any]:
    rec = {"status": "complete", "type": "video", "source": "youtube_video", "asset_type": "youtube_video", "local_path": path,
           "video_id": cand.video_id, "provider_asset_id": cand.video_id, "source_url": f"https://www.youtube.com/watch?v={cand.video_id}",
           "video_title": cand.title, "channel": cand.channel, "author": cand.channel, "clip_start": round(float(win["start"]), 2),
           "timestamp_end": round(float(win["end"]), 2), "duration": round(float(win["end"]) - float(win["start"]), 2),
           "selection_method": "aviation_director", "script_segment": sc.get("text", ""), "prompt": sc.get("prompt", ""),
           "tile_hashes": list(win.get("hashes") or []), "resolved_at": time.time(), "error": None}
    man.set(no, rec)
    return rec


def run(scenes: Sequence[Dict[str, Any]], images_dir: Any, state_dir: Any, *, search: Optional[Callable] = None,
        tiles: Optional[Callable] = None, capture: Optional[Callable] = None, log: Callable[[str], None] = lambda m: None,
        cancel: Callable[[], bool] = lambda: False) -> Dict[str, Any]:
    from asset_manager import AssetManifest
    from cinematic_explainer.war import director_frames as F

    images_dir, state_dir = Path(images_dir), Path(state_dir)
    images_dir.mkdir(parents=True, exist_ok=True)
    state_dir.mkdir(parents=True, exist_ok=True)
    if search is None or tiles is None or capture is None:
        s_, t_, c_ = _default_tools(state_dir, log)
        search, tiles, capture = search or s_, tiles or t_, capture or c_
    man = AssetManifest(images_dir)
    used = Used()
    report: Dict[str, Any] = {"scenes": {}, "unfilled": []}
    extras: Dict[str, List[Dict[str, Any]]] = {}
    rows = [sc for sc in scenes if str(sc.get("asset_type") or "").lower() == "youtube_video"]
    # a clip the user picked in the Visuals tab (or an earlier run's director clip that is still there) keeps its place
    for sc in rows:
        rec = man.get(str(sc["scene_no"])) or {}
        if rec.get("video_id") and str(rec.get("status")).lower() == "complete" and Path(str(rec.get("local_path") or "")).is_file():
            used.add(rec["video_id"], float(rec.get("clip_start") or 0), float(rec.get("timestamp_end") or 0), rec.get("tile_hashes") or [])
    tiles_cache: Dict[str, List[Any]] = {}
    import threading
    lock = threading.RLock()            # scenes run side by side: the used moments, the manifest and the report are shared

    def frames_of(c: Any) -> List[Any]:
        if c.video_id not in tiles_cache:
            try:
                tiles_cache[c.video_id] = list(tiles(c) or [])
            except Exception as exc:  # noqa: BLE001 - a video whose previews cannot be read is skipped, never captured blind
                log(f"frames of {c.video_id} not read: {type(exc).__name__}")
                tiles_cache[c.video_id] = []
        return tiles_cache[c.video_id]

    def pick(no: str, sc: Dict[str, Any], c: Any, pool: List[Any], dest: Path, skip: set, floor: float = -1e9) -> Optional[Dict[str, Any]]:
        people = c.mode == "people"
        ok = []
        for cand in pool:
            if cand.video_id in skip:
                continue
            why = title_reject(cand.title, c, people_line=people, airlines=[sc.get("airline") or ""], aircraft=[sc.get("aircraft") or ""],
                               channel=getattr(cand, "channel", ""))
            if why:
                continue
            sc_ = title_score(cand, c, airlines=[sc.get("airline") or ""])
            if sc_ >= floor:
                ok.append((sc_, cand))
        ok.sort(key=lambda x: -x[0])
        tries = 0
        for _score, cand in ok[:SHORTLIST]:
            if cancel() or tries >= CAPTURE_TRIES:
                break
            tl = frames_of(cand)
            if not tl:
                continue
            with lock:                  # the window is reserved before the capture, so two scenes never take the same seconds
                win = F.choose_window(tl, cand.duration, clip_s=CLIP_S, min_s=min_stretch(c.mode),
                                      usable=lambda a, b, h, v=cand.video_id: not used.conflict(v, a, b, h))
                held = used.add(cand.video_id, float(win["start"]), float(win["end"]), win.get("hashes") or []) if win else None
            if not win:
                log(f"scene {no}: '{cand.title[:50]}' has no clean filmed stretch (studio, text, graphics or stills)")
                continue
            tries += 1
            got = capture(cand.video_id, float(win["start"]), float(win["end"]) - float(win["start"]), dest, tl)
            if not got.get("ok"):
                with lock:
                    used.drop(held)
                log(f"scene {no}: '{cand.title[:50]}' capture failed: {'; '.join(got.get('reasons') or [])}")
                continue
            return {"cand": cand, "win": win, "path": got["path"], "score": _score}
        return None

    pools: Dict[str, List[Any]] = {}

    def discover(sc: Dict[str, Any]) -> None:
        if cancel():
            return
        c_ = classify_line(sc.get("text", ""))
        if sc.get("mode") in R.MODES:
            c_.mode = sc["mode"]
        pl = list(search(_queries(sc, c_)) or [])
        pools[str(sc["scene_no"])] = pl
        ranked = sorted((cand for cand in pl if not title_reject(cand.title, c_, airlines=[sc.get("airline") or ""],
                                                                 aircraft=[sc.get("aircraft") or ""], channel=getattr(cand, "channel", ""))),
                        key=lambda cand: -title_score(cand, c_, airlines=[sc.get("airline") or ""]))
        for cand in ranked[:SHORTLIST]:
            frames_of(cand)

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=4) as ex:
        list(ex.map(discover, rows))

    def one(sc: Dict[str, Any]) -> None:
        if cancel():
            return
        no = str(sc["scene_no"])
        with lock:
            rec = man.get(no) or {}
        if rec.get("user_override") or rec.get("source") == "manual" or \
                (rec.get("selection_method") == "aviation_director" and Path(str(rec.get("local_path") or "")).is_file()):
            with lock:
                report["scenes"][no] = {"decision": "kept", "video_id": rec.get("video_id", "")}
            return
        c = classify_line(sc.get("text", ""))
        if sc.get("mode") in R.MODES:
            c.mode = sc["mode"]
        qs = _queries(sc, c)
        pool = pools.get(no) if no in pools else list(search(qs) or [])
        main = pick(no, sc, c, pool, images_dir / f"{int(no):03d}.mp4" if no.isdigit() else images_dir / f"{no}.mp4", set())
        if not main:
            with lock:
                report["scenes"][no] = {"decision": "none", "queries": qs, "found": len(pool)}
                report["unfilled"].append(no)
            log(f"scene {no}: no YouTube clip passed the checks ({len(pool)} found): a Flow shot or a card goes here")
            return
        with lock:
            _record(man, no, sc, main["cand"], main["win"], main["path"])
            report["scenes"][no] = {"decision": "footage", "video_id": main["cand"].video_id, "title": main["cand"].title,
                                "window": [main["win"]["start"], main["win"]["end"]], "queries": qs}
        log(f"scene {no}: {main['cand'].channel} '{main['cand'].title[:60]}' {float(main['win']['start']):.1f}-{float(main['win']['end']):.1f}s")
        if c.mode in ("news", "numbers"):
            got_vids = {main["cand"].video_id}
            for k in range(EXTRA_PER_NEWS):
                ex = pick(no, sc, c, pool, images_dir / "extra" / f"{int(no) if no.isdigit() else no:03}_{k + 1}.mp4", got_vids,
                          floor=main["score"] - 2.0)      # an extra must be nearly as relevant as the main clip
                if not ex:
                    break
                got_vids.add(ex["cand"].video_id)
                with lock:
                    extras.setdefault(no, []).append({"path": ex["path"], "video_id": ex["cand"].video_id, "title": ex["cand"].title,
                                                  "channel": ex["cand"].channel,
                                                  "duration": float(ex["win"]["end"]) - float(ex["win"]["start"])})
    with ThreadPoolExecutor(max_workers=max(1, SCENE_WORKERS)) as ex:
        list(ex.map(one, rows))
    report["unfilled"].sort(key=lambda x: int(x) if str(x).isdigit() else 0)
    (state_dir / EXTRAS).write_text(json.dumps(extras, indent=1), encoding="utf-8")
    (state_dir / REPORT).write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    n = sum(1 for v in report["scenes"].values() if v["decision"] in ("footage", "kept"))
    log(f"Aviation footage: {n} of {len(rows)} YouTube scenes have checked footage, {sum(len(v) for v in extras.values())} extra burst clips")
    return report


def recheck_extras(extras: Dict[str, List[Dict[str, Any]]], scenes: Sequence[Dict[str, Any]],
                   log: Callable[[str], None] = lambda m: None) -> Dict[str, List[Dict[str, Any]]]:
    """Burst clips saved by an earlier Generate, checked again against today's title rules at Render (a rule fixed later -
    e.g. a passenger trip video - also cleans projects made before the fix). Clips that fail are left out, never replaced."""
    from . import router as R
    by_no = {str(s.get("scene_no")): s for s in scenes}
    out: Dict[str, List[Dict[str, Any]]] = {}
    for no, clips in (extras or {}).items():
        sc = by_no.get(str(no))
        if sc is None:
            continue
        c = R.classify(str(sc.get("text") or ""))
        c.mode = sc.get("mode") or c.mode
        keep = []
        for x in clips or []:
            why = title_reject(x.get("title", ""), c, airlines=[sc["airline"]] if sc.get("airline") else (),
                               channel=x.get("channel", ""))
            if why:
                log(f"scene {no}: burst clip left out ({why}): {str(x.get('title', ''))[:60]}")
            else:
                keep.append(x)
        if keep:
            out[str(no)] = keep
    return out


REPORT = "aviation_director_report.json"


def recheck_main(scenes: List[Dict[str, Any]], state_dir: Any, log: Callable[[str], None] = lambda m: None) -> int:
    """The main YouTube clip each scene got at Generate, checked again against today's title rules at Render (the report keeps
    each clip's title). A clip that fails is taken off the scene (the line plays on the stage instead), never swapped for another
    scene's clip. Flow / local / user-picked clips are not touched. Returns how many were taken off."""
    from . import router as R
    try:
        rep = json.loads((Path(state_dir) / REPORT).read_text(encoding="utf-8")).get("scenes") or {}
    except Exception:
        return 0
    n = 0
    for sc in scenes:
        r = rep.get(str(sc.get("scene_no"))) or {}
        if r.get("decision") != "footage" or str(sc.get("asset_type") or "") != "youtube_video" or not sc.get("footage"):
            continue
        c = R.classify(str(sc.get("text") or ""))
        c.mode = sc.get("mode") or c.mode
        why = title_reject(r.get("title", ""), c, airlines=[sc["airline"]] if sc.get("airline") else (), channel=r.get("channel", ""))
        if why:
            log(f"scene {sc.get('scene_no')}: clip left out at Render ({why}): {str(r.get('title', ''))[:60]}")
            sc["footage"] = None
            sc["has_clip"] = False
            n += 1
    return n
