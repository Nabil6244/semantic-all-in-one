"""War footage library: the one-time, reviewed b-roll folder is asked first for every footage row; YouTube / Flow / stock are searched live
only for what it does not hold.

    <library>/index.json            {version, clips: [{file, subject, words, usable_s, url, title, channel, upload_date, ai_generated, ...}]}
    <library>/<subject>/<name>.mp4  reviewed by eye before it goes in (no watermark, no subtitles, no studio)

plan(scenes, rows, clips) is a pure function of the CSV and the index: the same CSV and library give the same clips on every run.

 match    each '||' alternative of the row's prompt is compared with a clip's subject + words.
            - a prompt that names something ('Moskva cruiser', 'Storm Shadow missile') takes only a clip that carries that name: a named
              thing the library does not hold goes to the live search
            - a plain prompt ('refinery fire night') needs two shared words, or one that is in the clip's subject name
            - a prompt that is a subject name ('russian_warships_sea', 'steel mill') takes that subject
            - a clip of the other side (Russian / Ukrainian) is never taken
 reuse    a clip comes back at most MAX_USES times in a video and never within REUSE_GAP_S: a row whose subject is used up gets the
          War graphics (no search: the library knows the subject, it only needs more clips of it)
 report   <state>/war_library_report.json lists every row's source and the subjects that need more clips.

Friends' batches:   python -m cinematic_explainer.war.library import <zip or folder> [batch.csv]      checks + contact sheet, nothing added
                    python -m cinematic_explainer.war.library approve <batch> [--reject name,name]    reviewed clips go into the library
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

SETTING = "war_footage_library"
DIR_SETTING = "war_library_dir"
ENV_DIR = "WAR_LIBRARY_DIR"
LIVE_SETTING = "war_live_searches"   # rows per video that may still go to YouTube / Flow / stock; -1 = every row the library lacks
LIVE_DEFAULT = 10
REPORT = "war_library_report.json"
METHOD = "war_library"
MAX_USES = 2              # one source video in one film (render 050: one road clip on 3 unrelated lines, one Kremlin clip on 5)
REUSE_GAP_S = 60.0        # seconds before the same clip may come back
REUSE_GAP_SCENES = 10     # the same, for scenes that carry no times yet
MIN_CLIP_S = 3.0          # direction.MIN_SHOT_S: a shorter cut-free stretch is never shown
MIN_HEIGHT = 720

_STOP = {"the", "a", "an", "of", "in", "on", "at", "to", "for", "and", "or", "with", "from", "by", "after", "before", "during", "over", "near",
         "into", "footage", "video", "clip", "news", "report", "live", "official", "photo", "photos", "images", "b-roll", "broll"}
_DOMAINS = {"underwater": "sea", "naval": "sea", "maritime": "sea", "sea": "sea", "seaborne": "sea", "aerial": "air", "airborne": "air",
            "flying": "air", "sky": "air"}   # where a thing is: an underwater drone is never an aerial drone clip
_SEA_NAMES = {"black", "azov", "red", "north", "baltic", "caspian", "south"}   # 'Black Sea' names a place, not a sea shot
_CONTEXT = re.compile(r"\b(?:black|azov|baltic|caspian)\s+sea(?:\s+fleet)?\b|\bsea\s+of\s+azov\b|\bfleet\b", re.I)  # where, not what
_SIDES = {"russian": "ru", "russia": "ru", "russias": "ru", "ukrainian": "ua", "ukraine": "ua", "ukraines": "ua"}


# ---- the library ------------------------------------------------------------------------------------------------------------------
def root(settings: Optional[Dict[str, Any]] = None) -> Path:
    p = os.environ.get(ENV_DIR) or (settings or {}).get(DIR_SETTING) or ""
    return Path(p).expanduser() if p else Path.home() / "Downloads" / "VideoGenerator" / "war_library"


def enabled(settings: Optional[Dict[str, Any]]) -> bool:
    return bool((settings or {}).get(SETTING, True))


def live_cap(settings: Optional[Dict[str, Any]]) -> Optional[int]:
    """How many rows may be searched live (None: no limit)."""
    try:
        n = int((settings or {}).get(LIVE_SETTING, LIVE_DEFAULT))
    except (TypeError, ValueError):
        n = LIVE_DEFAULT
    return None if n < 0 else n


def load(lib: Path) -> List[Dict[str, Any]]:
    """The index's clips whose file is on disk, in a fixed order (file name)."""
    try:
        data = json.loads((Path(lib) / "index.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    clips = data.get("clips") if isinstance(data, dict) else data
    out = [dict(c) for c in (clips or []) if isinstance(c, dict) and c.get("file") and (Path(lib) / str(c["file"])).is_file()]
    return sorted(out, key=lambda c: str(c["file"]))


_ACTIONS = {"military", "war", "launch", "strike", "attack", "firing", "view", "combat", "sinking", "aftermath", "production", "repair"}   # what happens,
#   not what is shown, and words every war clip carries: one of these in a clip's subject name is never enough alone (a drone
#   launch is no rocket salvo, army vehicles are no military factory)
_SAME = {"army": "military", "truck": "vehicle", "troop": "soldier", "rouble": "ruble", "cash": "money"}   # one word each


def _stem(w: str) -> str:
    w = w.lower().strip("'-")
    w = w[:-2] if w.endswith("'s") else w
    w = w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w
    return _SAME.get(w, w)


def _tokens(text: str) -> List[str]:
    return [_stem(w) for w in re.findall(r"[A-Za-z0-9][\w'-]*", str(text or "").replace("_", " "))]


def _side(tokens: Sequence[str]) -> set:
    return {_SIDES[t] for t in tokens if t in _SIDES}


def _domain(tokens: Sequence[str]) -> set:
    return {_DOMAINS[t] for k, t in enumerate(tokens) if t in _DOMAINS and not (t == "sea" and k and tokens[k - 1] in _SEA_NAMES)}


def _clip_view(c: Dict[str, Any]) -> Dict[str, Any]:
    subj = [t for t in _tokens(c.get("subject", "")) if t not in _STOP]
    words = set(_tokens(c.get("words", ""))) | set(subj)
    order = _tokens(c.get("subject", "")) + _tokens(c.get("words", ""))
    return {"subject": subj, "words": words, "side": _side(list(words)), "domain": _domain(order), "text": f" {' '.join(order)} ",
            "ai": bool(c.get("ai_generated"))}


def _alternatives(prompt: str) -> List[Dict[str, Any]]:
    """Each '||' search of the prompt as {tokens (content words in order), names (what it names), side, subject (as one subject key)}. The War
    look sentence added to AI prompts is not a search."""
    out = []
    for part in str(prompt or "").split("||"):
        part = part.split(". cinematic documentary shot")[0].strip()
        if not part:
            continue
        toks = [t for t in _tokens(part) if t not in _STOP]
        names = _joined([n for n in _names(part) if not all(w in _SIDES for w in n.split())], part)
        context = {t for m in _CONTEXT.finditer(part) for t in _tokens(m.group(0))}
        out.append({"text": part, "tokens": [t for t in toks if t not in _SIDES], "names": names, "side": _side(_tokens(part)),
                    "domain": _domain(_tokens(part)), "context": context, "subject": "_".join(toks)})
    return out


def _joined(names: List[str], part: str) -> List[str]:
    """Names that stand next to each other in the search are one name ('Storm' + 'Shadow' -> 'storm shadow')."""
    text = f" {' '.join(_tokens(part))} "
    out: List[str] = []
    for n in names:
        if out and f" {out[-1]} {n} " in text:
            out[-1] = f"{out[-1]} {n}"
        else:
            out.append(n)
    return out


def _names(part: str) -> List[str]:
    """What a search names (the Footage Director's own reading: 'Snake Island' is one name, 'Black Sea' / 'Fleet' / a country are none)."""
    from . import footage_director as FD
    from . import narration_read as N

    skip = {c.lower() for c in getattr(N, "COUNTRIES", ())} | {m.lower() for m in N.MONTHS} | FD._PROMPT_NOT_SUBJECT
    return [" ".join(_stem(w) for w in n.split()) for n in FD._prompt_part(part, skip)["names"]]


def score(alt: Dict[str, Any], view: Dict[str, Any], subject_key: str = "", relax: bool = False) -> Tuple[int, int]:
    """(score, position of the first shared word in the search); score 0 = this clip does not show what the search asks for. relax: the
    search's names are read as plain words (a row past the live-search limit takes a clip of the same kind of thing: a warship for
    'warships Novorossiysk', an air-defence launcher for 'Pantsir'); side, sea/air and every plain-word rule still hold."""
    if alt["side"] and view["side"] and not (alt["side"] & view["side"]):
        return 0, 99
    if subject_key and alt["subject"] == subject_key:
        return 10, 0
    if alt.get("domain") and view.get("domain") is not None and not (alt["domain"] & view["domain"]):
        return 0, 99                        # an underwater / sea search never takes an aerial clip, nor the other way round
    shared = [t for t in alt["tokens"] if t in view["words"] or (t in _DOMAINS and _DOMAINS[t] in alt.get("domain", ()) and
                                                                    _DOMAINS[t] in view.get("domain", ()))]
    if alt["names"] and not relax:
        if f" {alt['names'][0]} " not in view.get("text", f" {' '.join(sorted(view['words']))} "):
            return 0, 99                    # it names a ship, a person, a weapon, a place: only a clip that carries the name
        return 4 + len(set(shared)), 0
    ctx = alt.get("context") or set()
    core = [t for t in shared if t not in ctx]   # 'Black Sea Fleet' says where: a submarine search never takes a coast clip for it
    pts = sum(2 if t in view["subject"] and t not in _ACTIONS else 1 for t in set(core))
    placed = set(alt.get("domain") or ()) | ({"sea"} if ctx else set())   # a Black Sea Fleet search welcomes a ship at sea
    pts -= sum(1 for t in view["subject"] if t in _DOMAINS and _DOMAINS[t] not in placed)   # a sea / aerial version of a thing the search
    if pts < 2:                                                                          # did not place there (a drone launch: no sea drone)
        return 0, 99
    pts += 1 if set(shared) & ctx else 0
    return pts, alt["tokens"].index(core[0])


_PLAIN = {"one", "two", "three", "side", "sides", "way", "time", "thing", "getting", "still", "very", "much", "more", "most", "every", "each",
          "this", "that", "these", "those", "their", "there", "where", "what", "which", "while", "will", "would", "could", "have", "has", "been",
          "also", "only", "even", "just", "first", "last", "next", "new", "now", "again", "into", "than", "then", "when", "about", "against", "ai"}


def line_terms(text: str, section_terms: Sequence[str] = ()) -> set:
    """The words a clip must share with what is said: the line's content words (stemmed, 'front line' also as 'frontline') and its
    section's subject (narration_read section_terms)."""
    toks = [t for t in _tokens(text) if t not in _STOP and t not in _PLAIN and len(t) >= 3]
    out = set(toks) | {a + b for a, b in zip(toks, toks[1:])}
    for s in section_terms:
        out |= {t for t in _tokens(s) if t not in _STOP and len(t) >= 3}
        out.add("".join(_tokens(s)))
    return out


def line_fits(view: Dict[str, Any], terms: set) -> bool:
    """Does the clip show what the LINE is about (not only what its CSV prompt says)? Its subject (minus side / action / 'ai' words) shares a
    word with the line or its section, or - for a clip whose subject is only an action ('strike_aftermath') - two of its words do."""
    core = [t for t in view["subject"] if t not in _ACTIONS and t not in _SIDES and t not in _PLAIN]
    if core and any(t in terms for t in core):
        return True
    shared = {w for w in view["words"] if w in terms and w not in _SIDES and w not in _PLAIN}
    return len(shared - _ACTIONS) >= 1 and len(shared) >= 2


def source_key(clip: Dict[str, Any]) -> str:
    """The video a library clip was cut from (several clips of one upload are one source)."""
    return _video_id(clip.get("url", "")) or str(clip.get("url") or clip.get("file") or "")


def candidates(prompt: str, clips: Sequence[Dict[str, Any]], views: Optional[Sequence[Dict[str, Any]]] = None,
               relax: bool = False) -> List[Tuple[int, int, int]]:
    """[(score, position, clip index)] of the clips that fit the prompt, best first; ties in file order."""
    views = views or [_clip_view(c) for c in clips]
    alts = _alternatives(prompt)
    out = []
    for i, (c, v) in enumerate(zip(clips, views)):
        best = (0, 99, 0)
        for k, a in enumerate(alts):
            s, pos = score(a, v, "_".join(_tokens(c.get("subject", ""))), relax=relax)
            if s and (s, -k, -pos) > (best[0], -best[2], -best[1]):
                best = (s, pos, k)
        if best[0]:
            out.append((best[0], best[1] + 10 * best[2], i))
    return sorted(out, key=lambda x: (-x[0], x[1], x[2]))


def _fitting(r: Any, clips: Sequence[Dict[str, Any]], views: Sequence[Dict[str, Any]], terms: Optional[set], relax: bool = False) -> List[Tuple[int, int, int]]:
    """candidates() of the row's prompt that also show what the row's LINE is about (terms None: prompt only, the old behaviour for callers
    without the narration)."""
    got = candidates(_query(r), clips, views, relax=relax)
    return got if terms is None else [x for x in got if line_fits(views[x[2]], terms)]


def live_rows(rows: Sequence[Any], clips: Sequence[Dict[str, Any]], views: Sequence[Dict[str, Any]], cap: Optional[int],
              held: Dict[str, str], terms_of: Optional[Dict[str, set]] = None, priority: Optional[Dict[str, int]] = None) -> set:
    """The rows the library has nothing for that may be searched live: every different search once, then second rows of the same searches,
    ... until `cap` rows (None: all of them). Most specific lines first (priority: a line that names its own event before one that borrows
    its section's subject), then scene order: render 050 spent its slots in script order on lines the director then turned into cards."""
    groups: Dict[str, List[str]] = {}
    order = sorted(range(len(rows)), key=lambda i: ((priority or {}).get(str(rows[i].scene_number), 0), i))
    for i in order:
        r = rows[i]
        no = str(r.scene_number)
        if no not in held and not _fitting(r, clips, views, (terms_of or {}).get(no) if terms_of is not None else None):
            groups.setdefault(_query(r).split("||")[0].strip().lower(), []).append(no)
    if cap is None:
        return {no for g in groups.values() for no in g}
    out: List[str] = []
    k = 0
    while len(out) < cap and any(len(g) > k for g in groups.values()):
        out += [g[k] for g in groups.values() if len(g) > k][:cap - len(out)]
        k += 1
    return set(out)


def plan(scenes: Sequence[Dict[str, Any]], rows: Sequence[Any], clips: Sequence[Dict[str, Any]],
         held: Optional[Dict[str, str]] = None, cap: Optional[int] = None) -> Dict[str, Dict[str, Any]]:
    """{scene no: {source: 'library', clip, score} | {source: 'graphics', subject, why} | {source: 'live'}} for the footage rows, in scene
    order. held: {scene no: library file} rows that keep a clip the user picked or an earlier live fetch (never changed here). cap: at most
    this many rows go live (live_rows); the others take a clip of the same kind of thing (relaxed match) or the War graphics."""
    held = held or {}
    views = [_clip_view(c) for c in clips]
    terms_of, priority = narration_terms(scenes, rows)
    live = live_rows(rows, clips, views, cap, held, terms_of, priority)
    by_no = {str(sc.get("scene_no")): (i, sc) for i, sc in enumerate(scenes)}
    uses: Dict[str, List[Tuple[float, int]]] = {}       # per SOURCE video: two clips cut from one upload are one source
    out: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        no = str(r.scene_number)
        if no in held:
            continue
        idx, sc = by_no.get(no) or (by_no.get(str(int(no))) if no.isdigit() else None) or (len(out), {})
        try:
            t = float(sc.get("start"))
        except (TypeError, ValueError):
            t = None
        terms = terms_of.get(no)
        cands = _fitting(r, clips, views, terms)
        relaxed = False
        if not cands and no in live:
            out[no] = {"source": "live"}
            continue
        if not cands:
            cands, relaxed = _fitting(r, clips, views, terms, relax=True), True
        if not cands:
            out[no] = {"source": "graphics", "subject": "", "why": "nothing in the library shows what this line is about, and it is over the "
                                                                  "live-search limit: War graphics"}
            continue
        said = set(_tokens(f"{getattr(r, 'script_segment', '')} {_query(r)}")) - _STOP

        def free_of(pool: Sequence[Tuple[int, int, int]], window: bool) -> List[Tuple[Any, ...]]:
            top = pool[0][0] if pool else 0
            got = []
            for s, pos, i in pool:
                if window and s < top - 1:
                    break                       # only clips about as fitting as the best one take turns
                u = uses.get(source_key(clips[i])) or []
                if len(u) >= MAX_USES:
                    continue
                if u and ((t is not None and u[-1][0] is not None and t - u[-1][0] < REUSE_GAP_S) or
                          ((t is None or u[-1][0] is None) and idx - u[-1][1] < REUSE_GAP_SCENES)):
                    continue
                # Novorossiysk render (2026-11-10): 107 of 191 shots were AI clips and 'gold bars' played over 'a constant flow of money'.
                # Among clips that fit about as well: real footage before an AI clip, then the clip whose own description shares the most
                # words with what is said, then the least used.
                fit = len(views[i]["words"] & said)
                got.append((views[i].get("ai", False), len(u), -s, -fit, pos, i))
            return got

        free = free_of(cands, True)
        if not free:          # the best clips are used up: another clip that still fits, before the row loses its footage (render 048's last 3 min)
            free = free_of(cands, False)
        if not free and not relaxed:
            more = _fitting(r, clips, views, terms, relax=True)
            free = free_of(more, False)
            if free:
                cands, relaxed = more, True
        if not free:
            subj = str(clips[cands[0][2]].get("subject") or "")
            out[no] = {"source": "graphics", "subject": subj, "why": f"library subject '{subj}' has no unused clip left for this scene"}
            continue
        i = sorted(free)[0][-1]
        uses.setdefault(source_key(clips[i]), []).append((t, idx))
        out[no] = {"source": "library", "clip": clips[i], "score": next(s for s, _p, j in cands if j == i), "relaxed": relaxed}
    return out


def narration_terms(scenes: Sequence[Dict[str, Any]], rows: Sequence[Any]) -> Tuple[Dict[str, set], Dict[str, int]]:
    """({scene no: line_terms}, {scene no: priority}) from the narration (narration_read.read_scenes). Priority 0: the line shows its own
    event / place / subject; 1: it names a subject but is not an event; 2: it borrows its section's subject; 3: nothing to show."""
    from . import narration_read as N

    by_no = {str(sc.get("scene_no")): sc for sc in scenes}
    try:
        readings = N.read_scenes(scenes)
    except Exception:  # noqa: BLE001 - without a reading the row text alone decides
        readings = {}
    terms: Dict[str, set] = {}
    prio: Dict[str, int] = {}
    for r in rows:
        no = str(r.scene_number)
        sc = by_no.get(no) or (by_no.get(str(int(no))) if no.isdigit() else None) or {}
        rd = readings.get(str(sc.get("scene_no", no)))
        text = str(getattr(r, "script_segment", "") or sc.get("text") or "")
        sec = list(getattr(rd, "section_terms", None) or [])
        terms[no] = line_terms(text, sec)
        frm = getattr(rd, "subject_from", "") if rd is not None else ""
        prio[no] = 0 if (frm == "line" and rd.footage_wanted) else 1 if frm == "line" else 2 if frm == "section" else 3
    return terms, prio


def _query(r: Any) -> str:
    """The row's search: its prompt, or a stock row's stock query."""
    return str(getattr(r, "prompt", "") or getattr(r, "stock", "") or "")


# ---- into the project's Visuals table ---------------------------------------------------------------------------------------------
def _video_id(url: str) -> str:
    m = re.search(r"(?:v=|youtu\.be/|/shorts/)([\w-]{6,})", str(url or ""))
    return m.group(1) if m else ""


def record_for(clip: Dict[str, Any], row: Any, dest: Path) -> Dict[str, Any]:
    ai = bool(clip.get("ai_generated"))
    n = float(clip.get("usable_s") or clip.get("seconds") or 0.0)
    return {
        "status": "complete", "type": "video", "source": "flow_video" if ai else "youtube_video", "asset_type": getattr(row, "asset_type", ""),
        "local_path": str(dest), "video_id": _video_id(clip.get("url", "")), "provider_asset_id": _video_id(clip.get("url", "")),
        "source_url": clip.get("url") or "", "video_title": clip.get("title") or "", "channel": clip.get("channel") or "",
        "author": clip.get("channel") or "", "license": None, "upload_date": clip.get("upload_date") or "",
        "clip_start": 0.0, "clip_duration": round(n, 2), "timestamp_end": round(n, 2), "duration": round(n, 2),
        "selection_method": METHOD, "library_file": str(clip["file"]), "library_subject": clip.get("subject") or "",
        "script_segment": getattr(row, "script_segment", ""), "prompt": getattr(row, "prompt", ""), "ai_generated": ai,
        "authenticity": "library", "resolved_at": time.time(), "error": None,
    }


def _same_file(a: Path, b: Path) -> bool:
    try:
        return a.is_file() and b.is_file() and a.stat().st_size == b.stat().st_size
    except OSError:
        return False


USABILITY = ".usability.json"     # per-clip result of the visual check, keyed by file size + mtime (re-checked when a file changes)


def picture_problem(path: Path) -> str:
    """Why a library clip's own frames are unusable ('' = clean): text over the picture (subtitles, a lower third, a ticker, an infographic)
    or mostly graphics / studio / dark frames. The same checks the Footage Director gives a captured clip (director_capture / frames)."""
    from . import director_capture as C
    from . import director_frames as F

    frames = C.frames_of(str(path), w=C.TEXT_W, h=C.TEXT_H)
    if not frames:
        return "no frames"
    why = C.text_on_frames(frames)
    if why:
        return why
    bad = 0
    prev = None
    for f in frames:
        k, _d, _fl = F.classify(f, prev)
        bad += k in LIBRARY_BAD
        prev = f
    return f"picture: {bad} of {len(frames)} frames are a presenter or a text screen" if bad > 0.3 * len(frames) else ""


# what disqualifies a REVIEWED library clip: a presenter or a text screen. Night, fog and furnace glow read as 'dark' / 'graphic' to the
# tile classifier and are legitimate footage (2026-11-11: counting them refused 33 good clips); the old pale-area 'text_screen' rule reads a
# bright sky or a white background as a text card (5 good clips), so text is judged by the line-shape check (text_on_frames) alone
LIBRARY_BAD = ("studio",)


def usable_clips(clips: Sequence[Dict[str, Any]], lib: Path, check: Callable[[Path], str] = picture_problem,
                 log: Callable[[str], None] = lambda m: None) -> List[Dict[str, Any]]:
    """The clips whose frames pass the visual check (render 050 review: the reviewed library still held the Moskva infographic, subtitled
    interviews and watermarked clips). Results are cached in <library>/.usability.json; a changed file is checked again."""
    p = Path(lib) / USABILITY
    try:
        cache = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cache = {}
    out: List[Dict[str, Any]] = []
    changed = False
    dropped = []
    for c in clips:
        f = Path(lib) / str(c["file"])
        try:
            st = f.stat()
            sig = f"{st.st_size}:{int(st.st_mtime)}"
        except OSError:
            continue
        hit = cache.get(str(c["file"]))
        if not hit or hit.get("sig") != sig:
            try:
                why = check(f)
            except Exception as exc:  # noqa: BLE001 - an unreadable clip is not used
                why = f"check failed: {exc}"
            cache[str(c["file"])] = hit = {"sig": sig, "why": why}
            changed = True
        if hit.get("why"):
            dropped.append(f"{c['file']} ({hit['why'][:60]})")
        else:
            out.append(c)
    if changed:
        try:
            p.write_text(json.dumps(cache, indent=1), encoding="utf-8")
        except OSError:
            pass
    if dropped:
        log(f"War library: {len(dropped)} clips not used (their frames fail the visual check): {'; '.join(dropped[:6])}")
    return out


def apply(scenes: Sequence[Dict[str, Any]], rows: Sequence[Any], images_dir: Path, state_dir: Path, lib: Optional[Path] = None,
          log: Callable[[str], None] = lambda m: None, settings: Optional[Dict[str, Any]] = None) -> Dict[str, Dict[str, Any]]:
    """Library clips are filed as the scenes' finished assets (the Visuals tab shows them like any fetched clip). Returns plan(): the caller
    sends only its 'live' rows to YouTube / Flow / stock. A clip the user picked, or one an earlier live fetch found, stays."""
    from asset_manager import AssetManifest

    lib = Path(lib) if lib else root(settings)
    clips = load(lib)
    if not clips:
        return {}
    clips = usable_clips(clips, lib, log=log)
    images_dir = Path(images_dir)
    images_dir.mkdir(parents=True, exist_ok=True)
    man = AssetManifest(images_dir)
    held: Dict[str, str] = {}
    for r in rows:
        rec = man.get(str(r.scene_number)) or {}
        mine = rec.get("selection_method") == METHOD
        if rec.get("user_override") or rec.get("source") == "manual" or getattr(r, "asset_type", "") in ("local", "local_video") or (
                not mine and str(rec.get("status") or "").lower() == "complete" and Path(str(rec.get("local_path") or "")).is_file()):
            held[str(r.scene_number)] = ""
    got = plan(scenes, rows, clips, held, cap=live_cap(settings))
    by_no = {str(r.scene_number): r for r in rows}
    for no, d in got.items():
        rec = man.get(no) or {}
        if d["source"] == "library":
            src = lib / str(d["clip"]["file"])
            dest = images_dir / (f"{int(no):03d}.mp4" if no.isdigit() else f"{no}.mp4")
            if not (rec.get("selection_method") == METHOD and rec.get("library_file") == d["clip"]["file"] and _same_file(src, dest)):
                tmp = dest.with_suffix(".lib.tmp")
                shutil.copyfile(src, tmp)
                tmp.replace(dest)
                man.set(no, record_for(d["clip"], by_no[no], dest))
        elif rec.get("selection_method") == METHOD:      # the library changed: an older library clip is not left behind
            man.set(no, dict(rec, status="failed", error="War library: " + d.get("why", "no clip of this subject any more")))
    report = summary(got, by_no)
    try:
        Path(state_dir).mkdir(parents=True, exist_ok=True)
        (Path(state_dir) / REPORT).write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
    n = report["counts"]
    log(f"War library: {n['library']} scenes from the library ({n['clips']} different clips, {n['relaxed']} of them over the live-search "
        f"limit), {n['graphics']} to War graphics, {n['live']} to the live search")
    for s in report["need_more"][:8]:
        log(f"  library needs more '{s['subject']}': {s['rows']} rows wanted it, {s['short']} got graphics")
    return got


# ------------------------------------------------------------------------------------------------ fallback before graphics -----------
# 2026-11-12 owner: "for the final videos we need videos and images too" (the render 050 slice was ~90 % graphics). After the live search, a
# footage row that still has no clip takes a library clip of the KIND of thing its line talks about (a refinery fire for a refinery strike,
# a missile factory for 'the factories that build the weapons'), shown as illustrative footage, never as footage of that event. Only these
# subject families, only when the line names that kind of thing; a source video at most MAX_USES times; real clips before AI ones.
FALLBACK = [
    (r"\b(refiner\w*|oil|fuel|petrol|diesel|depots?|pumping station|terminals?|port zone|exports?)\b",
     ["refinery_fire", "oil_pipeline", "ai_refinery_night", "ai_strike_industry"]),
    (r"\b(explosives?|rocket fuel|propellant|workshops?|factor(?:y|ies)|plants?\b.*\b(?:defen[cs]e|weapons?|military)|build the weapons|production)\b",
     ["factory_workers", "chemical_plant", "ai_strike_industry"]),
    (r"\bmissiles?\b.*\b(fires?|fired|launch\w*)\b|\b(launch\w*|fires?)\b.*\bmissiles?\b", ["missile_launch"]),
    (r"\b(air defen[cs]es?|shot down|intercept\w*|pantsir|s-400)\b", ["air_defence"]),
]
FALLBACK_SETTING = "war_library_fallback"


STEADY_RUN_S = 3.0
CHOPPY_RUN_S = 3.0          # the War shot minimum (direction.MIN_SHOT_S): a fallback clip never needs covering for its own edits


def steady(path: Path) -> bool:
    """Every uncut stretch of the clip is at least CHOPPY_RUN_S (direction.source_cuts): its own edits never make a short shot."""
    try:
        from .direction import _clip_seconds, source_cuts

        n = float(_clip_seconds(str(path)) or 0.0)
        cs = sorted(c for c in (source_cuts(str(path)) or []) if 0.0 < c < n)
    except Exception:  # noqa: BLE001 - unmeasurable: allowed (the render-time checks still apply)
        return True
    if n <= 0:
        return True                             # unmeasurable here: the render-time checks still judge it
    runs = [b - a for a, b in zip([0.0] + cs, cs + [n])]
    return max(runs) >= STEADY_RUN_S and min(runs) >= CHOPPY_RUN_S


def fallback_subjects(text: str) -> List[str]:
    """Library subjects whose kind of picture the line talks about, most specific first."""
    low = (text or "").lower()
    out: List[str] = []
    for rx, subs in FALLBACK:
        if re.search(rx, low):
            out += [x for x in subs if x not in out]
    return out


def fallback(scenes: Sequence[Dict[str, Any]], rows: Sequence[Any], images_dir: Path, lib: Optional[Path] = None,
             log: Callable[[str], None] = lambda m: None, settings: Optional[Dict[str, Any]] = None) -> List[str]:
    """Rows still without a clip get a library clip of their line's kind (illustrative). Returns the scene numbers filled."""
    from asset_manager import AssetManifest

    if not (settings or {}).get(FALLBACK_SETTING, True):
        return []
    lib = Path(lib) if lib else root(settings)
    clips = usable_clips(load(lib), lib, log=log)
    if not clips:
        return []
    images_dir = Path(images_dir)
    man = AssetManifest(images_dir)
    by_no = {str(sc.get("scene_no")): sc for sc in scenes}
    uses: Dict[str, int] = {}
    last_at: Dict[str, float] = {}
    for no, rec in (man.all() or {}).items():
        if not (by_no.get(no) or by_no.get(no.lstrip("0"))):
            continue                            # a record of a scene this script no longer has is not a use in this film
        if rec.get("selection_method") == METHOD and str(rec.get("status")).lower() == "complete":
            key = _video_id(str(rec.get("source_url") or "")) or str(rec.get("library_file") or "")
            uses[key] = uses.get(key, 0) + 1
            last_at[str(rec.get("library_file"))] = float((by_no.get(no) or by_no.get(no.lstrip("0")) or {}).get("start") or 0.0)
    filled: List[str] = []
    for r in rows:
        no = str(r.scene_number)
        rec = man.get(no) or {}
        if str(rec.get("status") or "").lower() == "complete" and Path(str(rec.get("local_path") or "")).is_file():
            continue
        if rec.get("user_override") or rec.get("source") == "manual":
            continue
        sc = by_no.get(no) or {}
        subs = fallback_subjects(str(sc.get("text") or getattr(r, "script_segment", "")))
        if not subs:
            continue
        t = float(sc.get("start") or 0.0)
        pick = None
        for sub in subs:
            for c in sorted((c for c in clips if c.get("subject") == sub), key=lambda c: (bool(c.get("ai_generated")), str(c["file"]))):
                key = source_key(c)
                if uses.get(key, 0) >= MAX_USES or str(c["file"]) in last_at:
                    continue                    # a fallback clip is shown once per film (a repeated filler reads as a loop)
                if not steady(lib / str(c["file"])):
                    continue                    # a choppy montage (cuts under 1 s, no 3 s stretch) would be covered by cards anyway: flashes
                pick = c
                break
            if pick:
                break
        if pick is None:
            continue
        dest = images_dir / (f"{int(no):03d}.mp4" if no.isdigit() else f"{no}.mp4")
        tmp = dest.with_suffix(".lib.tmp")
        shutil.copyfile(lib / str(pick["file"]), tmp)
        tmp.replace(dest)
        man.set(no, dict(record_for(pick, r, dest), match_level="illustrative", library_fallback=True,
                                                               fallback_note=f"the line's kind of picture ({pick.get('subject')}), not footage of the event"))
        uses[source_key(pick)] = uses.get(source_key(pick), 0) + 1
        last_at[str(pick["file"])] = t
        filled.append(no)
    if filled:
        log(f"War library fallback: {len(filled)} scene(s) without a clip get an illustrative library clip of their kind: {', '.join(filled)}")
    return filled


def summary(got: Dict[str, Dict[str, Any]], by_no: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    by_no = by_no or {}
    need: Dict[str, List[int]] = {}
    rows = []
    for no, d in got.items():
        subj = (d.get("clip") or {}).get("subject") or d.get("subject") or ""
        if subj:
            a = need.setdefault(subj, [0, 0])
            a[0] += 1
            a[1] += d["source"] == "graphics"
        rows.append({"scene": no, "source": d["source"], "file": (d.get("clip") or {}).get("file", ""), "subject": subj,
                     "prompt": _query(by_no.get(no))})
    live = sorted({_query(by_no.get(no)).split("||")[0].strip() for no, d in got.items() if d["source"] == "live"} - {""})
    return {"version": 1,
            "counts": {"library": sum(1 for d in got.values() if d["source"] == "library"),
                       "clips": len({d["clip"]["file"] for d in got.values() if d["source"] == "library"}),
                       "relaxed": sum(1 for d in got.values() if d["source"] == "library" and d.get("relaxed")),
                       "graphics": sum(1 for d in got.values() if d["source"] == "graphics"),
                       "live": sum(1 for d in got.values() if d["source"] == "live")},
            "need_more": sorted(({"subject": k, "rows": v[0], "short": v[1]} for k, v in need.items() if v[1]), key=lambda x: (-x["short"], x["subject"])),
            "live_searches": live, "rows": rows}


def library_nos(images_dir: Path, rows: Sequence[Any]) -> set:
    """Scene numbers whose finished asset is a library clip."""
    from asset_manager import AssetManifest

    if not Path(images_dir).is_dir():
        return set()
    man = AssetManifest(Path(images_dir))
    return {str(r.scene_number) for r in rows if (man.get(str(r.scene_number)) or {}).get("selection_method") == METHOD
            and str((man.get(str(r.scene_number)) or {}).get("status") or "").lower() == "complete"}


# ---- friends' batches -------------------------------------------------------------------------------------------------------------
def _probe(path: Path) -> Dict[str, Any]:
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height:format=duration", "-of", "json",
                            str(path)], capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:      # an unreadable file: no size, no length
        return {"w": 0, "h": 0, "seconds": 0.0}
    try:
        d = json.loads(r.stdout or "{}")
        st = (d.get("streams") or [{}])[0]
        return {"w": int(st.get("width") or 0), "h": int(st.get("height") or 0), "seconds": float((d.get("format") or {}).get("duration") or 0)}
    except (ValueError, TypeError):
        return {"w": 0, "h": 0, "seconds": 0.0}


def check_clip(path: Path) -> Dict[str, Any]:
    """{ok, why, seconds, usable_s, size}: the picture checks every incoming clip passes before a person looks at it."""
    p = _probe(path)
    out = {"ok": False, "why": "", "seconds": round(p["seconds"], 2), "usable_s": 0.0, "size": f"{p['w']},{p['h']}"}
    if not p["w"] or p["seconds"] <= 0:
        out["why"] = "not a video"
    elif p["h"] > p["w"]:
        out["why"] = "vertical phone video"
    elif p["h"] < MIN_HEIGHT:
        out["why"] = f"only {p['h']}p (720p is the least)"
    else:
        from . import archive_fast as AF
        from . import direction as D

        cuts = sorted(c for c in (D.source_cuts(str(path)) or []) if 0.15 < c < p["seconds"] - 0.15)
        edges = [0.0] + cuts + [p["seconds"]]
        out["usable_s"] = round(max(b - a for a, b in zip(edges, edges[1:])), 2)
        bad = AF.frame_problem(str(path))
        if out["usable_s"] < MIN_CLIP_S:
            out["why"] = f"longest stretch without a cut is {out['usable_s']:.1f} s (3 s is the least)"
        elif bad:
            out["why"] = bad
        else:
            out["ok"] = True
    return out


def _sheet(files: Sequence[Tuple[str, Path]], out: Path) -> Optional[Path]:
    """One contact sheet: a row per clip (its name, then frames from the start, middle and end)."""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return None
    tw, th, pad = 320, 180, 22
    sheet = Image.new("RGB", (tw * 3, (th + pad) * max(1, len(files))), (18, 18, 18))
    draw = ImageDraw.Draw(sheet)
    for row, (name, path) in enumerate(files):
        n = _probe(path)["seconds"]
        draw.text((6, row * (th + pad) + 4), f"{row + 1}. {name}  ({n:.1f} s)", fill=(235, 235, 235))
        for k, frac in enumerate((0.1, 0.5, 0.9)):
            try:
                r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{n * frac:.2f}", "-i", str(path), "-frames:v", "1", "-vf", f"scale={tw}:{th}",
                                    "-f", "image2pipe", "-vcodec", "png", "-"], capture_output=True, timeout=60)
            except subprocess.TimeoutExpired:      # a frame that never comes leaves a dark tile
                continue
            if r.stdout:
                try:
                    import io

                    sheet.paste(Image.open(io.BytesIO(r.stdout)).convert("RGB"), (k * tw, row * (th + pad) + pad))
                except Exception:  # noqa: BLE001 - one unreadable frame leaves a dark tile
                    pass
    sheet.save(out, quality=88)
    return out


def _batch_names(csv_path: Optional[Path]) -> Dict[str, Dict[str, str]]:
    """{scene number: {name, prompt, asset_type}} from a friend batch CSV (its library_name column)."""
    import csv

    if not csv_path or not Path(csv_path).is_file():
        return {}
    with open(csv_path, encoding="utf-8-sig", newline="") as fh:
        return {str(r.get("scene_number") or "").strip().lstrip("0") or "0": {"name": str(r.get("library_name") or "").strip(),
                                                                               "prompt": str(r.get("prompt") or "").strip(),
                                                                               "asset_type": str(r.get("asset_type") or "").strip().lower()}
                for r in csv.DictReader(fh) if str(r.get("library_name") or "").strip()}


def _subject_of(name: str) -> str:
    """'ai_dry_dock_2_01' -> 'ai_dry_dock': the clip number goes, then a one-digit batch marker ('_2'); 'su_34_01' stays 'su_34'."""
    s = re.sub(r"[_-]?\d+$", "", Path(name).stem).strip("_-")
    return re.sub(r"[_-][2-9]$", "", s).strip("_-").lower()


def _clip_key(stem: str) -> str:
    """'scene_007' / '007' -> '7': the scene number a War page or a hand-cut batch gave the file."""
    return re.sub(r"^scene[_-]?", "", stem, flags=re.I).lstrip("0") or "0"


def _words_of(prompt: str, subject: str) -> str:
    """What a clip shows, for the matcher: the search's first clause (an AI prompt's camera and light notes are left out)."""
    first = re.split(r"[,;]|\|\|", str(prompt or ""))[0]
    first = re.sub(r"\b(footage|illustration)\b:?", "", first, flags=re.I)
    return " ".join(dict.fromkeys(first.split())) or subject.replace("_", " ")


def import_batch(src: Path, batch_csv: Optional[Path] = None, lib: Optional[Path] = None, log: Callable[[str], None] = print) -> Path:
    """A friend's zip or folder -> <library>/_inbox/<name>/ with the checked clips, pending.json and contact sheets. Nothing enters the
    library here: approve() does that after the sheets were looked at. Clips are named by the batch CSV's library_name (the friend ran the
    War page, files are 001.mp4 ...), or keep their own name (the friend cut them by hand)."""
    lib = Path(lib) if lib else root()
    src = Path(src)
    box = lib / "_inbox" / re.sub(r"[^\w-]+", "_", src.stem)
    raw = box / "raw"
    if box.exists():
        shutil.rmtree(box)
    raw.mkdir(parents=True)
    if src.is_file():
        import zipfile

        with zipfile.ZipFile(src) as z:
            for m in z.infolist():                      # only plain media, records and CSVs leave the zip, under their own base names
                name = Path(m.filename).name
                if m.is_dir() or name.startswith(".") or Path(name).suffix.lower() not in (".mp4", ".mov", ".mkv", ".webm", ".json", ".csv"):
                    continue
                with z.open(m) as fin, open(raw / name, "wb") as fout:
                    shutil.copyfileobj(fin, fout)
    else:
        for p in sorted(src.rglob("*")):
            if p.is_file() and p.suffix.lower() in (".mp4", ".mov", ".mkv", ".webm", ".json", ".csv") and not p.name.startswith("."):
                shutil.copyfile(p, raw / p.name)
    csvs = [batch_csv] if batch_csv else sorted(raw.glob("*.csv"))
    names: Dict[str, Dict[str, str]] = {}
    for c in csvs:
        names.update(_batch_names(c))
    records: Dict[str, Dict[str, Any]] = {}
    for j in sorted(raw.glob("*.json")):                # the friend's Visuals table: where each clip came from
        try:
            data = json.loads(j.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        items = data.get("scenes") if isinstance(data, dict) and isinstance(data.get("scenes"), dict) else data
        if isinstance(items, dict):
            for k, v in items.items():
                if isinstance(v, dict) and v.get("local_path"):
                    records[_clip_key(Path(str(v["local_path"])).stem)] = v
    pending, ok_files = [], []
    seen: Dict[str, int] = {}
    for p in sorted(list(raw.glob("*.mp4")) + list(raw.glob("*.mov")) + list(raw.glob("*.mkv")) + list(raw.glob("*.webm"))):
        key = _clip_key(p.stem)
        row = names.get(key) or {}
        name = row.get("name") or p.stem
        subject = _subject_of(name)
        chk = check_clip(p)
        rec = records.get(key) or {}
        seen[subject] = seen.get(subject, 0) + 1
        item = {"raw": p.name, "name": name, "subject": subject, **chk, "url": rec.get("source_url") or "", "title": rec.get("video_title") or "",
                "channel": rec.get("channel") or "", "upload_date": rec.get("upload_date") or "",
                "words": _words_of(rec.get("prompt") or row.get("prompt") or "", subject),
                "ai_generated": "flow" in str(rec.get("source") or rec.get("asset_type") or row.get("asset_type") or "").lower()}
        pending.append(item)
        if chk["ok"]:
            ok_files.append((name, p))
        else:
            log(f"dropped {name}: {chk['why']}")
    sheets = []
    for k in range(0, len(ok_files), 12):
        s = _sheet(ok_files[k:k + 12], box / f"sheet_{k // 12 + 1:02d}.jpg")
        if s:
            sheets.append(s.name)
    (box / "pending.json").write_text(json.dumps({"source": str(src), "clips": pending, "sheets": sheets}, indent=1, ensure_ascii=False), encoding="utf-8")
    log(f"{len(ok_files)} of {len(pending)} clips passed the picture checks. Look at {box}/sheet_*.jpg, then: "
        f"python -m cinematic_explainer.war.library approve {box.name} --reject name,name")
    return box


def approve(batch: str, reject: Sequence[str] = (), lib: Optional[Path] = None, log: Callable[[str], None] = print) -> int:
    """The batch's checked clips, minus the rejected names, are copied into <library>/<subject>/ and listed in index.json."""
    lib = Path(lib) if lib else root()
    box = lib / "_inbox" / batch
    data = json.loads((box / "pending.json").read_text(encoding="utf-8"))
    idx_path = lib / "index.json"
    try:
        index = json.loads(idx_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        index = {"version": 1, "clips": []}
    have_urls = {(c.get("url"), c.get("subject")) for c in index["clips"] if c.get("url")}
    drop = {x.strip().lower() for x in reject if x.strip()}
    added = 0
    for it in data["clips"]:
        if not it.get("ok") or it["name"].lower() in drop or Path(it["raw"]).stem.lower() in drop:
            continue
        sub = lib / it["subject"]
        sub.mkdir(parents=True, exist_ok=True)
        n = 1
        while (sub / f"{it['subject']}_{n:03d}.mp4").exists():
            n += 1
        dest = sub / f"{it['subject']}_{n:03d}{Path(it['raw']).suffix.lower()}"
        shutil.copyfile(box / "raw" / it["raw"], dest)
        index["clips"].append({"file": f"{it['subject']}/{dest.name}", "subject": it["subject"], "words": it["words"], "seconds": it["seconds"],
                               "usable_s": it["usable_s"], "size": it["size"], "title": it["title"], "channel": it["channel"], "url": it["url"],
                               "upload_date": it["upload_date"], "ai_generated": bool(it["ai_generated"]), "added": time.strftime("%Y-%m-%d"),
                               "source": f"friend batch {batch}", "uses": 0,
                               "note": "same source video as another clip of this subject" if (it["url"], it["subject"]) in have_urls else ""})
        added += 1
    tmp = idx_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(index, indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(idx_path)
    log(f"{added} clips added to the library ({len(index['clips'])} in all)")
    return added


def main(argv: List[str]) -> int:
    if len(argv) >= 2 and argv[0] == "import":
        import_batch(Path(argv[1]), Path(argv[2]) if len(argv) > 2 else None)
        return 0
    if len(argv) >= 2 and argv[0] == "approve":
        rej = argv[argv.index("--reject") + 1].split(",") if "--reject" in argv and len(argv) > argv.index("--reject") + 1 else []
        approve(argv[1], rej)
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
