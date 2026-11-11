"""War Footage Director: footage that shows what the narrator says, or War graphics when no such footage can be verified.

docs/war/FOOTAGE_DIRECTOR_PLAN.md (Stages 1-9). For each YouTube row of a War scenes CSV:

  1 read the sentence (narration_read)            -> types, places, actor, date; claims / figures / questions / transitions want no footage
  2 search (director_search)                      -> 3-5 entity-first queries, results pooled
  3 rules (director_rules)                        -> hard rejections with reasons, then rank
  4 frames (director_frames)                      -> storyboard check of the shortlist, best cut-free 3-8 s window
  5 authenticity (director_authenticity)          -> verified_event / corroborated / unverified; events take only the first two
  6 no repeats (director_rules.Used)              -> same seconds, same picture under another URL, max 2 moments per video
  7 capture + verify (director_capture)           -> the shared capture pool records it; the file is matched against the storyboard
  9 report                                        -> state/war/discovery_report.json + director_decisions.json

A scene left without verified footage is handed to the graphics: no_footage, and (when its CSV row names no graphic) the existing War
graphic that fits the sentence (graphic_for). A clip the user picked in the Visuals tab is never touched. No Gemini, no API keys.
"""

from __future__ import annotations

import re

import datetime as _dt
import json
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from . import director_authenticity as A
from . import director_capture as C
from . import director_frames as F
from . import director_moment as M
from . import director_rules as R
from . import director_search as S
from . import narration_read as N

SHORTLIST = 4
CAPTURE_TRIES = 3
PREFETCH_THREADS = 4
CAPTURE_LIMIT_S = 45.0          # War's own limit per capture (+3 s per clip second); the shared browser's own limit is 180 s


def bounded(acquire: Callable[..., Dict[str, Any]], seconds_fn: Callable[[float], float]) -> Callable[..., Dict[str, Any]]:
    """acquire() with a War-side time limit: a capture that hangs is given up (its browser finishes on its own), the next candidate goes on."""
    import threading

    def run(video_id, start, seconds, dest):
        box: Dict[str, Any] = {}
        th = threading.Thread(target=lambda: box.update(res=acquire(video_id, start, seconds, dest)), daemon=True, name="war-capture")
        th.start()
        limit = seconds_fn(seconds)
        th.join(limit)
        if th.is_alive():
            return {"ok": False, "kind": "timeout", "error": f"timed out after {limit:.0f} s (War limit)"}
        return box.get("res") or {"ok": False, "error": "no result"}
    return run
REPORT = "discovery_report.json"
DECISIONS = "director_decisions.json"
SETTING = "war_footage_director"


BLOCKLIST = Path(__file__).resolve().parent / "data" / "footage_blocklist.json"
PROJECT_BLOCKLIST = "director_blocklist.json"
# capture failures that will fail again for the same video and window: never retried; a timeout or a browser hiccup may be retried once
LASTING = ("picture:", "moment:", "file:", "capture: no video tracks", "capture: age restricted", "capture: age_restricted")


def load_blocklist(state_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for p in [BLOCKLIST] + ([Path(state_dir) / PROJECT_BLOCKLIST] if state_dir else []):
        try:
            out += list(json.loads(Path(p).read_text(encoding="utf-8")).get("entries") or [])
        except (OSError, ValueError):
            continue
    return out


def blocked_for(entries: Sequence[Dict[str, Any]], video_id: str, text: str, start: Optional[float] = None) -> str:
    """The reason this video may not be used for this narration ('' = allowed). A lasting capture failure blocks only its own window."""
    for e in entries:
        if e.get("video_id") != video_id:
            continue
        if e.get("scope") == "text" and str(e.get("text") or "").lower() not in (text or "").lower():
            continue
        if e.get("scope") == "window" and start is not None and abs(float(e.get("start") or -99) - float(start)) > 4.0:
            continue
        return str(e.get("reason") or "blocklisted")
    return ""


def _remember_failure(state_dir: Path, video_id: str, start: float, reasons: Sequence[str]) -> None:
    """A capture that failed for a lasting reason is written to the project's blocklist (that window only), so no later run retries it."""
    why = "; ".join(reasons)
    if not any(why.startswith(x) or x in why for x in LASTING):
        return
    p = Path(state_dir) / PROJECT_BLOCKLIST
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {"note": "this project's War Footage Director failures and rejections (merged with data/footage_blocklist.json)", "entries": []}
    data["entries"].append({"video_id": video_id, "scope": "window", "start": round(float(start), 2), "reason": f"capture failed: {why[:160]}"})
    _write(p, data)


def enabled(settings: Optional[Dict[str, Any]]) -> bool:
    return bool((settings or {}).get(SETTING, True))


def graphic_for(r: N.Reading) -> str:
    """The existing War graphic (a CSV `graphic` value, direction.CSV_GRAPHIC) for a sentence shown without footage."""
    t = set(r.types)
    low = r.text.lower()
    if "TRANSITION" in t and not ({"EVENT", "MOVEMENT", "STATISTIC"} & t):
        return "title" if any(w in low for w in ("subscribe", "comments", "tell me")) else "chapter"
    if "QUESTION" in t:
        return "kinetic"
    if "STATISTIC" in t:
        return "number"
    if "CLAIM" in t and r.speaker:
        return "speaker"
    if "MOVEMENT" in t and r.places:
        return "route"
    if ("LOCATION" in t or "EVENT" in t) and r.places:
        return "map"
    if "EVENT" in t and any(w in low for w in ("drone", "missile", "from the air", "air strike")):
        return "flyover"
    if "CLAIM" in t:
        return "source" if r.outlet else "claim"
    if "SUBJECT" in t and r.equipment:
        return "equipment"
    if re.search(r",.+,.+\band\b", r.text):
        return "list"                   # a real list ('refineries, depots and factories'): its items, never loose words
    return ""                           # nothing specific: the War graphics choose from the sentence (no keyword card of loose words)


def widen_to_section(readings: Dict[str, Any]) -> int:
    """A line that names nothing filmable of its own still gets footage of its section's subject (narration_read.read_scenes section_terms):
    'The core issue is security guarantees' inside the Abu Dhabi part searches for the Abu Dhabi talks. Render 050: such lines were read as
    ANALYSIS / STATISTIC and never searched, so whole minutes (the talks, the grid) had no footage. Part headings and outro lines stay
    graphics. Returns how many lines were widened."""
    n = 0
    for rd in readings.values():
        if rd.footage_wanted or not getattr(rd, "section_terms", None):
            continue
        if N.section_break(rd.text) or N._OUTRO.search(rd.text or ""):
            continue
        rd.footage_wanted = True
        rd.widened = True                  # picks after the lines that show their own event (run(): most specific first)
        rd.key_terms = list(rd.section_terms) + [k for k in rd.key_terms if k not in rd.section_terms]
        rd.reasons = list(rd.reasons) + ["FOOTAGE: the section's subject (" + ", ".join(rd.section_terms[:3]) + ")"]
        n += 1
    return n


LABEL_FRAMES = 2          # Stage B.3: text lines on at least this many frames ...
LABEL_SHARE = 0.2         # ... and this share of them: the clip carries an on-screen caption (a place label, a source credit) we cannot read


def burnt_label(frames: Sequence[Any]) -> bool:
    """The clip shows short lines of text on several frames (a place caption like 'DONETSK REGION, UKRAINE', a source credit). Without OCR
    the place it names cannot be read, so where the picture was filmed is not established (render 050 scene 89)."""
    if not frames:
        return False
    n = sum(1 for f in frames if F.text_lines(f))
    return n >= LABEL_FRAMES and n >= LABEL_SHARE * len(frames)


def _location_verdict(label: bool, c: Any, reading: Any) -> Dict[str, Any]:
    """{'unverified': bool, 'refuse': reason}. A label we cannot read on footage uploaded before the line's event, for a line about an event
    at a named place, is refused: it may show another place (a compilation of an earlier strike). Otherwise the clip is only unverified."""
    if not label:
        return {}
    place_bound = bool(R.line_places(reading)) and bool({"EVENT", "MOVEMENT"} & set(getattr(reading, "types", []) or []))
    if place_bound and R.stale(c, reading):
        return {"unverified": True, "refuse": "location: an on-screen label the engine cannot read, on footage uploaded before this event: "
                                              "it may show another place"}
    return {"unverified": True}


def location_check(path: str, c: Any, reading: Any) -> Dict[str, Any]:
    try:
        frames = C.frames_of(str(path), w=C.TEXT_W, h=C.TEXT_H)
    except Exception:  # noqa: BLE001 - unreadable here: the capture's own checks already passed
        return {}
    return _location_verdict(burnt_label(frames), c, reading)


def moment_check(searcher: Any, c: Any, reading: Any) -> Any:
    """director_moment.check with the transcript's status and the video's chapters (a rate-limited transcript is 'not checked', never
    'irrelevant'; chapters can place the moment without it)."""
    if not (c.duration and c.duration > M.LONG_S) or searcher is None:
        return M.check(c.duration, None, reading)
    info = getattr(searcher, "transcript_info", None)
    if info is None:
        return M.check(c.duration, searcher.transcript(c.video_id), reading)
    segs, status, chapters = info(c.video_id)
    return M.check(c.duration, segs, reading, status=status, chapters=chapters)


def revalidate(rec: Dict[str, Any], reading: Any, searcher: Any, film_date: Optional[_dt.date] = None, story: Any = None,
               frames_of: Callable[..., Any] = C.frames_of) -> List[str]:
    """Why a clip an earlier run chose may no longer be used ([] = it passes today's checks). The same three checks a new pick gets:
    visual usability (its own frames: text over the picture, graphics, studio), video relevance (director_rules.reject on its title and
    description) and moment relevance (a long programme's cut must sit where its transcript names the line's subject)."""
    why: List[str] = []
    path = str(rec.get("local_path") or "")
    if not path or not Path(path).is_file():
        return ["file: the kept clip is missing"]
    frames = frames_of(path, w=C.TEXT_W, h=C.TEXT_H)
    if not frames:
        return ["file: the kept clip has no frames"]
    txt = C.text_on_frames(frames)
    if txt:
        why.append(txt)
    label = burnt_label(frames)
    kinds: Dict[str, int] = {}
    prev = None
    for f in frames:
        k, _d, _fl = F.classify(f, prev)
        if k in F.BAD and k not in ("overlay_text", "text_graphic"):
            kinds[k] = kinds.get(k, 0) + 1
        prev = f
    if sum(kinds.values()) > 0.3 * len(frames):
        why.append("picture: " + ", ".join(f"{k} {v}" for k, v in kinds.items()) + f" of {len(frames)} frames")
    c = S.Candidate(video_id=str(rec.get("video_id") or ""), title=str(rec.get("video_title") or rec.get("title") or ""),
                    channel=str(rec.get("channel") or rec.get("author") or ""), description=str(rec.get("description") or ""))
    if searcher is not None and c.video_id:
        try:
            searcher.details(c)
        except Exception:  # noqa: BLE001 - judged on what the record holds
            pass
    why += [f"relevance: {x}" for x in R.reject(c, reading, film_date, story)]
    if rec.get("upload_date") and not (getattr(c, "details", None) or {}).get("upload_date"):
        c.details = dict(getattr(c, "details", None) or {}, upload_date=str(rec.get("upload_date")))
    loc = _location_verdict(label, c, reading)
    if loc.get("refuse"):
        why.append(loc["refuse"])
    if c.duration and c.duration > M.LONG_S:
        ok, hint, w = moment_check(searcher, c, reading)
        if not ok:
            why.append(w)
        elif not M.inside(float(rec.get("clip_start") or 0.0), hint):
            why.append(f"moment: the kept cut at {float(rec.get('clip_start') or 0):.0f} s is not where the programme talks about "
                       f"{', '.join(M.terms_of(reading)[:2])} ({hint:.0f} s)")
    return why


def _clip_dict(rec: Dict[str, Any]) -> Dict[str, Any]:
    keys = ("video_id", "source", "source_url", "clip_start", "title", "channel", "description", "upload_date", "authenticity",
            "moment_verified", "frame_flags", "tile_hashes")
    d = {k: rec.get(k) for k in keys}
    d["title"] = rec.get("video_title") or rec.get("title") or ""
    d["clip_end"] = rec.get("timestamp_end")
    d["reused"] = bool(rec.get("reused"))
    return d


_PROMPT_NOT_SUBJECT = {"reuters", "ap", "afp", "bbc", "cnn", "footage", "video", "news", "official", "officials"}
_AREA_TAILS = {"sea", "ocean", "river", "gulf", "strait", "fleet", "region", "coast"}
_GENERIC_NAME_WORDS = {"island", "sea", "fleet", "river", "city", "port", "navy", "army", "black", "pentagon", "us", "uk", "eu", "nato"}


_PROMPT_STOP = {"the", "a", "an", "of", "in", "on", "at", "to", "for", "and", "or", "with", "from", "by", "after", "before", "during", "over",
                "near", "into", "footage", "video", "clip", "news", "report", "live", "official", "officials", "photo", "photos", "images"}


def _prompt_part(part: str, skip: set) -> Dict[str, List[str]]:
    """One '||' alternative of a CSV prompt: its names (capitalised runs, 'Snake Island' as one; not countries / months / outlets) and its
    other content words ('sinking', 'stamp', 'queue')."""
    import re as _re

    names, words = [], []
    for tok in _re.findall(r"[A-Z][\w'-]*(?:\s+[A-Z][\w'-]*)*|[a-z][\w'-]+", part):
        if tok[:1].isupper():
            kept = [w.lower() for w in tok.split() if w.lower() not in skip and w.lower() not in _PROMPT_STOP
                    and not _re.match(r"(?:russian|ukrainian)s?$", w.lower())]
            i = 0
            while i < len(kept):                      # 'Snake Island' is one name, 'Snake Island Moskva' two; a whole sea is none
                if i + 1 < len(kept) and kept[i + 1] in _GENERIC_NAME_WORDS:
                    nm, i = f"{kept[i]} {kept[i + 1]}", i + 2
                else:
                    nm, i = kept[i], i + 1
                if nm.split()[-1] in _AREA_TAILS or nm in _GENERIC_NAME_WORDS or len(nm) < 3:
                    continue
                if nm not in names:
                    names.append(nm)
        elif tok not in _PROMPT_STOP and len(tok) >= 3:
            words.append(tok)
    return {"names": names, "words": words}


def prompt_conflict(rd: Any, prompt: str) -> str:
    """Why the CSV prompt is about something other than the line ('' = it agrees). The line names its own place / site (not only as a
    reference point) and the prompt names none of them, or the prompt's events and the line's belong to different families (frontline
    soldiers for 'Diplomacy is back on the table'). A line that names no subject of its own ('the flagship ... sank') takes the prompt's."""
    from . import director_rules as R

    hay = N.fold(prompt or "").lower()
    le, pe = R.events_in(rd.text), R.events_in(prompt)
    if le and pe and not (R._families(le) & R._families(pe)):
        return f"the prompt is about {'/'.join(sorted(pe))}, the line about {'/'.join(sorted(le))}"
    if le and pe:
        return ""                                  # same kind of event ('talks' for talks between Washington, Moscow and Kyiv): it agrees
    own = [p_ for p_ in R.line_places(rd) if p_.split()[-1].lower() not in _AREA_TAILS]   # a sea or region is no subject of its own
    if own and not any(R._has(hay, p_) for p_ in own) and not any(R._has(hay, k) for k in (rd.equipment or []) + (rd.facilities or [])
                                                                    if k[:1].isupper()):
        return f"the prompt names none of {', '.join(own[:3])}"
    return ""


def queries_for(rd: Any, prompt: str, topic: Any = None) -> List[str]:
    """Search queries: the narration's own first when the prompt conflicts with it, the prompt then only as the last hint."""
    if getattr(rd, "prompt_conflict", ""):
        qs = S.build_queries(rd, "", topic=topic)[:4]
        hint = next((x.strip() for x in str(prompt or "").split("||") if x.strip()), "")
        return qs + ([hint] if hint and hint.lower() not in [q.lower() for q in qs] else [])
    return S.build_queries(rd, prompt, topic=topic)


def _prompt_subjects(readings: Dict[str, Any], scenes: Sequence[Dict[str, Any]], rows: Sequence[Any]) -> None:
    """The names in a row's CSV prompt (its first search) are what the writer wants shown: they lead the reading's key terms. Moskva
    2026-11-09: 'On April 14, 2022, the flagship of Russia's Black Sea Fleet sank' named no ship, so Al Jazeera's 'sinking of Russia's
    flagship Moskva' was rejected as 'none of Black Sea, Fleet named' while grain-crisis clips passed. Countries and months are not
    subjects (every Ukraine clip names Ukraine)."""
    import re as _re

    skip = {c.lower() for c in getattr(N, "COUNTRIES", ())} | {m.lower() for m in N.MONTHS} | _PROMPT_NOT_SUBJECT
    by_no = {str(sc.get("scene_no")): sc for sc in scenes}
    for r in rows:
        full = str(getattr(r, "prompt", "") or "")
        prompt = full.split("||")[0]
        no_ = str(getattr(r, "scene_number", ""))
        sc_ = by_no.get(no_) or (by_no.get(str(int(no_))) if no_.isdigit() else None) or {}
        rd = readings.get(str(sc_.get("scene_no", no_)))
        if rd is None or not prompt.strip():
            continue
        rd.prompt_parts = [_prompt_part(x, skip) for x in full.split("||") if x.strip()]
        why_c = prompt_conflict(rd, full)
        if why_c:
            # Stage B.3: the narration decides the subject. A prompt about something else (render 050 'Putin meeting Kremlin' on 'the Ryazan
            # refinery') is only a late search hint: it neither leads the key terms nor gates the clips.
            rd.prompt_conflict = why_c
            rd.prompt_parts = []
            continue
        names: List[str] = []
        for run_ in _re.findall(r"\b[A-Z][\w-]+(?:\s+[A-Z][\w-]+)*", prompt):     # 'Snake Island' stays one name; a lone 'Island' is no subject
            words = [w for w in run_.split() if w.lower() not in skip and not _re.match(r"(?:Russian|Ukrainian)s?$", w)]
            if not words:
                continue
            parts = []
            i = 0
            while i < len(words):                     # 'Snake Island', 'Black Sea' are one name; 'Pentagon Moskva Neptune' is three
                if i + 1 < len(words) and words[i + 1].lower() in _GENERIC_NAME_WORDS:
                    parts.append(f"{words[i]} {words[i + 1]}")
                    i += 2
                    continue
                parts.append(words[i])
                i += 1
            for p_ in parts:
                if p_.split()[-1].lower() in _AREA_TAILS:
                    continue      # 'Black Sea' names a whole region: Odesa news mentions it too (Moskva 044: a 2024 Odesa strike clip passed)
                if p_.lower() not in _GENERIC_NAME_WORDS and len(p_) >= 3 and p_ not in names:
                    names.append(p_)
        if names:
            rd.key_terms = names + [k for k in rd.key_terms if k not in names]


def run(scenes: Sequence[Dict[str, Any]], rows: Sequence[Any], images_dir: Path, state_dir: Path, log: Callable[[str], None] = lambda m: None,
        cancel: Callable[[], bool] = lambda: False, film_date: Optional[_dt.date] = None, searcher: Optional[S.Searcher] = None,
        acquire: Optional[Callable[..., Dict[str, Any]]] = None, validate: Optional[Callable[..., Optional[str]]] = None,
        fetch_sheet: Optional[Callable[[str], bytes]] = None, render_id: str = "") -> Dict[str, Any]:
    """Decide footage or graphics for every YouTube row; capture what is chosen. Returns the report (also written to state_dir)."""
    from asset_manager import AssetManifest

    images_dir, state_dir = Path(images_dir), Path(state_dir)
    images_dir.mkdir(parents=True, exist_ok=True)
    state_dir.mkdir(parents=True, exist_ok=True)
    film_date = film_date or _dt.date.today()
    searcher = searcher or S.Searcher(state_dir / "director_cache", log=log)
    fetch_sheet = fetch_sheet or F._fetch
    readings = N.read_scenes(scenes)
    _prompt_subjects(readings, scenes, rows)
    widened = widen_to_section(readings)
    if widened:
        log(f"Footage Director: {widened} lines without a subject of their own search for their section's subject")
    topic = S.topic_of(list(readings.values()))
    story = R.story_period(list(readings.values()))
    man = AssetManifest(images_dir)
    used = R.Used()
    blocklist = load_blocklist(state_dir)
    by_no = {str(sc.get("scene_no")): sc for sc in scenes}
    yt_rows = [r for r in rows if getattr(r, "asset_type", "") == "youtube_video"]
    report_scenes: List[Dict[str, Any]] = []
    decisions: Dict[str, Dict[str, Any]] = {}

    # clips already decided: the user's own picks keep their place; an earlier director run's pick is kept only when it passes today's checks
    # (render 050: a studio panel picked by the first run was 'kept' by the second without any check). Both block repeats.
    stale: Dict[str, List[str]] = {}
    for r in yt_rows:
        no_ = str(r.scene_number)
        rec = man.get(no_) or {}
        if str(rec.get("status") or "").lower() != "complete" or not rec.get("video_id") or not Path(str(rec.get("local_path") or "")).is_file():
            continue
        mine = rec.get("selection_method") == "war_director" and not (rec.get("user_override") or rec.get("source") == "manual")
        if mine:
            sc_ = by_no.get(no_) or (by_no.get(str(int(no_))) if no_.isdigit() else None) or {}
            rd_ = readings.get(str(sc_.get("scene_no", no_))) or N.read(r.script_segment)
            bad_ = revalidate(rec, rd_, searcher, film_date, story)
            if bad_:
                stale[no_] = bad_
                continue
        if mine or rec.get("user_override") or rec.get("source") == "manual":
            used.add(no_, rec["video_id"], float(rec.get("clip_start") or 0), float(rec.get("timestamp_end") or 0), rec.get("tile_hashes") or [])

    t_start = time.time()
    timing = {"prefetch_s": 0.0, "capture_ok_s": 0.0, "capture_fail_s": 0.0, "captures_ok": 0, "captures_failed": 0}
    if acquire is None:
        from providers.youtube.acquisition.browser_client import get_client
        acquire = get_client().acquire
    acquire = bounded(acquire, lambda sec: CAPTURE_LIMIT_S + 3.0 * float(sec))

    # 1 discovery for every footage scene at once (search, rules, metadata, storyboards): network waits overlap; picking stays in order
    pre_scene: Dict[str, Any] = {}
    tiles_of: Dict[str, Any] = {}

    def discover(r: Any) -> None:
        no_ = str(r.scene_number)
        sc_ = by_no.get(no_) or (by_no.get(str(int(no_))) if no_.isdigit() else None) or {}
        rd = readings.get(str(sc_.get("scene_no", no_))) or N.read(r.script_segment)
        rec_ = man.get(no_) or {}
        if not rd.footage_wanted or rec_.get("user_override") or rec_.get("source") == "manual":
            return
        qs = queries_for(rd, getattr(r, "prompt", "") or "", topic=topic)
        pl = searcher.pool(qs, cancel=cancel)
        ok_, _bad = R.rank([c for c in pl if not blocked_for(blocklist, c.video_id, rd.text)], rd, film_date, story)
        for _s, c in ok_[:SHORTLIST + 2]:
            d_ = searcher.details(c)
            if c.video_id in tiles_of:
                continue
            sb_ = d_.get("storyboard") or {}
            try:
                tiles_of[c.video_id] = (F.inspect(F.tiles_from_storyboard(sb_, fetch=fetch_sheet)) if sb_ else
                                        F.inspect(F.tiles_from_thumbnails(c.video_id, c.duration, fetch=fetch_sheet)), bool(sb_))
            except Exception:  # noqa: BLE001 - frames are fetched again in the pick loop
                pass
        pre_scene[no_] = (qs, pl)

    t0 = time.time()
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=PREFETCH_THREADS) as ex:
        list(ex.map(lambda r: (None if cancel() else discover(r)), yt_rows))
    timing["prefetch_s"] = round(time.time() - t0, 1)

    def _widened(r: Any) -> bool:
        no_ = str(r.scene_number)
        sc_ = by_no.get(no_) or (by_no.get(str(int(no_))) if no_.isdigit() else None) or {}
        return bool(getattr(readings.get(str(sc_.get("scene_no", no_))), "widened", False))

    # most specific first: a line that shows its own event picks before a line that only borrows its section's subject (a claim about
    # refineries must not take the one clip of the strike the next line narrates)
    for r in sorted(yt_rows, key=lambda r_: (_widened(r_), yt_rows.index(r_))):
        if cancel():
            log("Footage Director stopped")
            break
        no = str(r.scene_number)
        sc = by_no.get(no) or by_no.get(str(int(no))) if no.isdigit() else by_no.get(no)
        sc = sc or {}
        reading = readings.get(str(sc.get("scene_no", no))) or N.read(r.script_segment)
        entry: Dict[str, Any] = {"scene": f"{int(no):03d}" if no.isdigit() else no, "types": reading.types, "actor": reading.actor,
                                 "key_terms": reading.key_terms, "graphic_intent": graphic_for(reading), "reasons": reading.reasons,
                                 "queries": [], "candidates": [], "rejected": [], "decision": "graphics", "clip": {}}
        rec = man.get(no) or {}
        if rec.get("user_override") or rec.get("source") == "manual":
            entry.update(decision="footage", clip=_clip_dict(rec), note="the user's own pick: kept")
            report_scenes.append(entry)
            decisions[no] = {"decision": "footage", "graphic": ""}
            continue
        if no in stale:
            entry["revalidation"] = stale[no]
            log(f"scene {no}: the clip an earlier run chose fails today's checks ({'; '.join(stale[no])[:160]}): searching again")
            _mark_graphics(man, no, rec, "failed re-validation: " + "; ".join(stale[no])[:200])
            rec = {}
        elif rec.get("selection_method") == "war_director" and str(rec.get("status")).lower() == "complete" and \
                Path(str(rec.get("local_path") or "")).is_file():
            entry.update(decision="footage", clip=_clip_dict(rec), note="chosen by an earlier run: re-validated and kept")
            report_scenes.append(entry)
            decisions[no] = {"decision": "footage", "graphic": ""}
            continue
        if not reading.footage_wanted:
            why = f"{'/'.join(reading.types)} sentence: shown with War graphics, not footage"
            entry["note"] = why
            log(f"scene {no}: {why}")
            _mark_graphics(man, no, rec, why)
            decisions[no] = {"decision": "graphics", "graphic": entry["graphic_intent"], "why": why}
            report_scenes.append(entry)
            continue
        queries, pool = pre_scene.get(no) or (queries_for(reading, getattr(r, "prompt", "") or "", topic=topic), None)
        entry["queries"] = queries
        if pool is None:
            pool = searcher.pool(queries, cancel=cancel)
        pre = [c for c in pool if blocked_for(blocklist, c.video_id, reading.text) and
               not any(e.get("scope") == "window" for e in blocklist if e.get("video_id") == c.video_id)]
        if pre:
            pool = [c for c in pool if c not in pre]
        ok, bad = R.rank(pool, reading, film_date, story)
        bad += [(c, [f"blocklist: {blocked_for(blocklist, c.video_id, reading.text)}"]) for c in pre]
        entry["rejected"] = [{"video_id": c.video_id, "title": c.title, "channel": c.channel, "why": w} for c, w in bad]
        picked = None
        tries = 0
        shortlist = ok[:SHORTLIST + 2]
        for _sc, c in shortlist:
            searcher.details(c)
        # an age-restricted upload cannot be recorded by the capture browser (no sign-in): it stays a candidate, tried last
        shortlist = sorted(shortlist, key=lambda x: (x[1].blocked, -x[0]))[:SHORTLIST + 1]
        others: List[Any] = []
        for score, c in shortlist:
            if cancel() or tries >= CAPTURE_TRIES:
                break
            d = searcher.details(c)
            cand = {"video_id": c.video_id, "title": c.title, "channel": c.channel, "tier": R.channel_tier(c.channel), "score": score,
                    "duration": c.duration, "upload_date": d.get("upload_date", ""), "queries": c.queries}
            late = R.reject(c, reading, film_date, story)          # the upload date is known now
            if late:
                cand["why"] = late
                entry["candidates"].append(cand)
                continue
            level = R.match_level(c, reading)
            cand["level"] = level
            # moment relevance: a long programme is cut only near the passage that talks about the line's subject (director_moment)
            ok_m, hint, why_m = moment_check(searcher, c, reading)
            if not ok_m:
                cand["why"] = [why_m]
                entry["candidates"].append(cand)
                continue
            if hint is not None:
                cand["moment"] = round(hint, 1)
            fits = M.near(hint)
            sb = d.get("storyboard") or {}
            ok_win = lambda a, b, h, vid=c.video_id: not used.conflict(vid, a, b, h) and fits(a, b)  # noqa: E731
            if c.video_id in tiles_of:
                tiles, _has_sb = tiles_of[c.video_id]
                win = (F.choose_window(tiles, c.duration, usable=ok_win, hint=hint) if sb else
                       F.window_from_thumbnails(tiles, c.duration, usable=ok_win))
                if not sb:
                    cand["inspection"] = "thumbnails" + (" (metadata needs sign-in)" if c.blocked else "")
            elif sb:
                tiles = F.inspect(F.tiles_from_storyboard(sb, fetch=fetch_sheet))
                win = F.choose_window(tiles, c.duration, usable=ok_win, hint=hint)
            else:
                # no storyboard (age-restricted / sign-in): preview from YouTube's thumbnails, capture is then judged on its own frames
                tiles = F.inspect(F.tiles_from_thumbnails(c.video_id, c.duration, fetch=fetch_sheet))
                win = F.window_from_thumbnails(tiles, c.duration, usable=ok_win)
                cand["inspection"] = "thumbnails" + (" (metadata needs sign-in)" if c.blocked else "")
                if c.content_warning:
                    cand["content_warning"] = c.content_warning
            cand["frames"] = F.summary(tiles)
            if not win:
                cand["why"] = ["frames: no cut-free stretch of filmed footage (talking heads, graphics, phone video in bars, or repeats)"]
                entry["candidates"].append(cand)
                continue
            stop = blocked_for([e for e in blocklist if e.get("scope") == "window"], c.video_id, reading.text, win["start"])
            if stop:
                cand["why"] = [f"blocklist: {stop} (not retried)"]
                entry["candidates"].append(cand)
                continue
            others.append((c.video_id, c.channel, win["hashes"]))
            cls, why_cls = A.classify(c, reading, film_date, win["hashes"], others, story=story, level=level)
            cand.update(window=win, authenticity=cls, authenticity_reasons=why_cls)
            if not A.allowed(cls, reading, level, cand["tier"], c.blocked, why_cls):
                cand["why"] = [f"authenticity: {cls} ({'; '.join(why_cls)}): this scene takes only verified or corroborated footage"]
                entry["candidates"].append(cand)
                continue
            tries += 1
            dest = images_dir / (f"{int(no):03d}.mp4" if no.isdigit() else f"{no}.mp4")
            got = C.capture(c.video_id, win["start"], win["end"] - win["start"], dest, tiles, acquire=acquire, validate=validate, log=log,
                            storyboard=bool(sb))
            timing["capture_ok_s" if got["ok"] else "capture_fail_s"] += float(got.get("seconds") or 0)
            timing["captures_ok" if got["ok"] else "captures_failed"] += 1
            cand["capture"] = {k: got.get(k) for k in ("ok", "reasons", "seconds")}
            entry["candidates"].append(cand)
            if not got["ok"]:
                log(f"scene {no}: {c.title[:50]} not used: {'; '.join(got['reasons'])}")
                _remember_failure(state_dir, c.video_id, win["start"], got["reasons"])
                blocklist = load_blocklist(state_dir)
                continue
            loc = location_check(got["path"], c, reading)
            if loc.get("refuse"):
                cand["why"] = [loc["refuse"]]
                log(f"scene {no}: {c.title[:50]} not used: {loc['refuse']}")
                continue
            if loc.get("unverified") and level == "exact":
                level = "contextual"           # a location label the engine cannot read: never claimed as exact footage of the event
                cand["level"] = level
            cand["location"] = "unverified: on-screen label not read" if loc.get("unverified") else "from title"
            picked = {"candidate": c, "window": win, "path": got["path"], "verify": got.get("verify"), "authenticity": cls,
                      "authenticity_reasons": why_cls, "score": score, "tier": cand["tier"], "queries": queries, "level": level,
                      "frame_flags": sorted({fl for t in tiles if win["start"] <= t.t < win["end"] for fl in t.flags}
                                            | ({"location_label_unread"} if loc.get("unverified") else set()))}
            break
        if picked:
            rec = C.write_record(man, no, getattr(r, "script_segment", ""), getattr(r, "prompt", ""), picked)
            used.add(no, picked["candidate"].video_id, picked["window"]["start"], picked["window"]["end"], picked["window"]["hashes"])
            entry.update(decision="footage", clip=_clip_dict(rec), match_level=level)
            decisions[no] = {"decision": "footage", "graphic": "", "label": A.label(picked["authenticity"])}
            log(f"scene {no}: {picked['candidate'].channel} '{picked['candidate'].title[:60]}' {picked['window']['start']:.1f}-"
                f"{picked['window']['end']:.1f}s ({picked['authenticity']})")
        else:
            why = "no candidate passed the checks: shown with War graphics"
            entry["note"] = why
            _mark_graphics(man, no, rec, why)
            decisions[no] = {"decision": "graphics", "graphic": entry["graphic_intent"], "why": why}
            log(f"scene {no}: {why} ({len(pool)} found, {len(bad)} rejected by the rules)")
        report_scenes.append(entry)

    order = {str(getattr(r, "scene_number", "")): i for i, r in enumerate(yt_rows)}
    report_scenes.sort(key=lambda x: order.get(str(int(x["scene"])) if str(x.get("scene", "")).isdigit() else str(x.get("scene")), 0))
    levels = {k: sum(1 for x in report_scenes if x.get("decision") == "footage" and x.get("match_level") == k)
              for k in ("exact", "contextual", "atmospheric")}
    report = {"version": 1, "render": render_id, "film_date": str(film_date), "topic": topic, "seconds": round(time.time() - t_start, 1),
              "story_period": [str(story[0]), str(story[1])] if story else None, "levels": levels,
              "graphics": sum(1 for x in report_scenes if x.get("decision") == "graphics"),
              "calls": dict(searcher.calls), "timing": {**{k: round(v, 1) if isinstance(v, float) else v for k, v in timing.items()},
                                                         "other_s": round(time.time() - t_start - timing["prefetch_s"] - timing["capture_ok_s"]
                                                                          - timing["capture_fail_s"], 1)},
              "scenes": report_scenes}
    _write(state_dir / REPORT, report)
    _write(state_dir / DECISIONS, decisions)
    placed = sum(1 for s in report_scenes if s["decision"] == "footage")
    log(f"Footage Director: {placed} of {len(report_scenes)} YouTube scenes have verified footage, the rest use War graphics "
        f"({report['seconds']:.0f} s; report in {state_dir / REPORT})")
    return report


def _mark_graphics(man: Any, no: str, rec: Dict[str, Any], why: str) -> None:
    """A clip an older run left for this scene is not used: the record says why (the Visuals tab shows it)."""
    if rec and str(rec.get("status") or "").lower() == "complete" and not (rec.get("user_override") or rec.get("source") == "manual"):
        man.set(no, dict(rec, status="failed", error=f"War Footage Director: {why}"))


def _write(p: Path, data: Any) -> None:
    try:
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
        tmp.replace(p)
    except OSError:
        pass


def load_decisions(state_dir: Path) -> Dict[str, Dict[str, Any]]:
    try:
        return json.loads((Path(state_dir) / DECISIONS).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def apply_decisions(scenes: List[Dict[str, Any]], decisions: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Scenes handed to the graphics get no_footage and, when their CSV row names no graphic, the War graphic that fits the sentence."""
    out = []
    for sc in scenes:
        sc = dict(sc)
        d = decisions.get(str(sc.get("scene_no"))) or decisions.get(f"{sc.get('scene_no')}".zfill(3)) or {}
        if d.get("decision") == "graphics" and not (sc.get("footage_meta") or {}).get("user_supplied"):
            sc["no_footage"] = True
            sc.pop("footage", None)
            sc.pop("footage_meta", None)
            if not str(sc.get("graphic") or "").strip() and d.get("graphic"):
                sc["graphic"] = d["graphic"]
                sc["graphic_by"] = "footage_director"
        elif d.get("label") and sc.get("footage_meta") is not None:
            sc["footage_meta"] = dict(sc["footage_meta"], label=d["label"])
        out.append(sc)
    return out
