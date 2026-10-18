"""What If: getting the pictures and clips for the shots that need them. The shots become rows for the SAME resolver StarMap and
the other styles use (starmap.media.fetch_media -> NASA image library first, then the app's providers: stock, Flow images, Flow
video, YouTube, archive...), so the Visual Plan table, the asset manifest, retries and billing-safety behave exactly as they do
everywhere else: nothing is fetched or generated twice, nothing is retried in a loop. AI material is labelled."""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Dict, List, Optional, Sequence

from starmap.beat_csv import Item

VIDEO_EXT = {".mp4", ".mov", ".m4v", ".webm", ".mkv"}


def is_asset(a: str) -> bool:
    """'<source>:<what to find>' with a source the resolver knows (shot_csv.ASSET_SOURCES)."""
    from .shot_csv import ASSET_SOURCES

    src, sep, what = str(a or "").partition(":")
    return bool(sep) and src.strip().lower() in ASSET_SOURCES and bool(what.strip())


def asset_shots(shots: Sequence[Any]) -> List[Any]:
    """The shots that name a source (file: ones are the author's own and need no fetching). A shot whose asset is not a
    '<source>:<what>' request is left to its fallback: one bad request stopped the listing and the fetch of EVERY picture
    (project #016: a disc map's text "Every person|Every city|..." taken as its photo)."""
    return [s for s in shots if s.asset and not s.asset.lower().startswith("file:") and is_asset(s.asset)]


PEOPLE = re.compile(r"\b(astronauts?|cosmonauts?|engineers?|scientists?|team|crew|people|person|man|woman|portrait|selfie|control room|press)\b", re.I)


def as_plan(shots: Sequence[Any], start_row: int = 1) -> Any:
    """A minimal object shaped like a StarMap Plan for starmap.media: one 'beat' per shot, its asset a clip row."""
    beats = []
    for n, s in enumerate(asset_shots(shots), start_row):
        s.row = n
        it = Item(row=n, kind="clip", asset=s.asset, t=s.start, why=(s.name or s.place or s.text[:60]))
        beats.append(SimpleNamespace(id=s.id, start=s.start, end=s.end, cards=[], clips=[it], layers=[], extra={}, date=""))
    # numbered by row, so the extra passes (Commons, AI) never reuse an earlier pass's scene numbers -- and so its file names:
    # a Flow 001.png replacing the NASA 001.jpg deleted that photo out from under the shot that had it
    numbers = {b.clips[0].row: str(b.clips[0].row) for b in beats}
    plan = SimpleNamespace(beats=beats, media_numbers=numbers, duration=shots[-1].end if shots else 0.0)
    return plan


def visual_dicts(shots: Sequence[Any]) -> List[Dict[str, str]]:
    """The Visual Plan rows: one per picture or clip, with the shot's length, so a row can be switched between Flow Image and Flow Video
    knowing whether it fits a clip (a Flow video shot stays under 6 s; see planner.FLOW_VIDEO_MAX_S)."""
    from starmap.media import media_rows

    plan = as_plan(shots)
    length = {b.clips[0].row: b.end - b.start for b in plan.beats}
    out = []
    for m in media_rows(plan):
        d = m.as_dict()
        d["script_segment"] = d["script_segment"].replace("StarMap beat", "What If shot").replace(" · footage", f" · {length.get(m.row, 0):.1f} s", 1)
        out.append(d)
    return out


def _apply(shots: Sequence[Any], got: Any) -> None:
    for s in shots:
        rec = got.media.get(f"row:{s.row}") if s.row else None
        if rec and rec.get("file"):
            s.file, s.credit = str(rec["file"]), str(rec.get("credit") or "")
            if Path(s.file).suffix.lower() in VIDEO_EXT:
                s.kind = "video"
            elif s.kind == "video":
                s.kind = "image"              # a still came back where a clip was asked for


_FROM_TABLE = {"image": "flow_image", "video": "flow_video", "stock_image": "nasa_image", "stock_video": "stock_video"}


def _take_visual_plan_sources(shots: Sequence[Any], scene_rows: Optional[Sequence[Any]], log: Callable[[str], None]) -> int:
    """A source changed in the Visual Plan (Change source, Use alternatives) is the shot's source from now on. The NASA search is
    planned from the shots, so a NASA row turned into a Flow image was still asked of NASA, found nothing and was dropped before
    its (already made) Flow image was looked at. Returns how many shots took their row's source."""
    by_number = {str(r.scene_number): r for r in scene_rows or [] if hasattr(r, "scene_number")}
    changed = 0
    for s in shots:
        r = by_number.get(str(s.row)) if s.row else None
        src = _FROM_TABLE.get(getattr(r, "asset_type", "") or "")
        what = " ".join(((r.prompt or r.stock) if r is not None else "").split())
        if not src or not what:
            continue
        cur_src, _, cur_what = s.asset.partition(":")
        if src == cur_src.lower() and " ".join(cur_what.split()).startswith(what[:60]):
            continue
        if src == "nasa_image" and cur_src.lower() != "nasa_image":
            continue                     # a NASA row shows as stock_image in the table: only a real change counts
        s.asset = f"{src}:{what}"
        if src in ("flow_image", "flow_video"):
            s.cite = ("AI ILLUSTRATION", "")
            s.kind = "video" if src == "flow_video" else "image"
        changed += 1
        log(f"[What If] Visual Plan scene {s.row}: using its source as set there ({src})")
    return changed


def _save_on_table_rows(shots: Sequence[Any], numbers: Dict[str, str], images_dir: Path) -> None:
    """An AI stand-in made under its own number (84, 85 ...) is also recorded under the Visual Plan row it fills (28, 29 ...): the row
    shows it after a restart, and Render finds it there. A row that already has its own finished file is left as it is."""
    from asset_manager import AssetManifest

    man = AssetManifest(Path(images_dir))
    for s in shots:
        row = numbers.get(str(s.row))
        if not row or not s.file or not Path(s.file).is_file():
            continue
        own = man.get(row) or {}
        if own.get("status") == "complete" and Path(str(own.get("local_path") or "/-")).is_file():
            continue
        rec = man.get(str(s.row)) or {}
        man.set(row, {**rec, "status": "complete", "local_path": str(s.file), "stand_in_for": row, "error": None})


def _stand_in_for(man: Any, shot: Any) -> Optional[dict]:
    """A finished file of another manifest entry that was made for this shot's own request (same words): a Commons or AI
    stand-in saved under a later pass's number. None when there is none."""
    want = " ".join(shot.asset.partition(":")[2].lower().split())[:60]
    if not want:
        return None
    for key, rec in sorted((getattr(man, "_data", None) or {}).items(), reverse=True):
        if str(key).lstrip("0") == str(shot.row) or rec.get("status") != "complete":
            continue
        f = Path(str(rec.get("local_path") or "/-"))
        said = " ".join(str(rec.get("prompt") or rec.get("stock_query") or "").lower().split())[:60]
        if f.is_file() and said and said == want:
            return rec
    return None


def _from_saved(shots: Sequence[Any], images_dir: Path, log: Callable[[str], None]) -> Any:
    """Render: every asset as it is saved for its Visual Plan row -- nothing searched, generated or downloaded. A row with no saved
    file is reported (unresolved), never fetched."""
    from asset_manager import AssetManifest

    as_plan(shots)
    man = AssetManifest(Path(images_dir))
    got = SimpleNamespace(media={}, unresolved=[], notes=[], credits=[])
    for s in asset_shots(shots):
        rec = man.get(str(s.row)) or {}
        f = Path(str(rec.get("local_path") or "/-"))
        if not (rec.get("status") == "complete" and f.is_file()):
            alt = _stand_in_for(man, s)       # a stand-in saved under another number is the row's picture: never stop Render for it
            if alt:
                rec, f = alt, Path(str(alt["local_path"]))
                man.set(str(s.row), {**alt, "stand_in_for": str(s.row), "error": None})
                log(f"[What If] scene {s.row}: its stand-in picture ({f.name}) was recorded under another number; now saved on the row")
        if rec.get("status") == "complete" and f.is_file():
            s.file, s.credit = str(f), str(rec.get("credit") or "")
            if f.suffix.lower() in VIDEO_EXT:
                s.kind = "video"
            elif s.kind == "video":
                s.kind = "image"
            got.media[f"row:{s.row}"] = {"file": str(f), "credit": s.credit}
            if s.credit and s.credit not in got.credits:
                got.credits.append(s.credit)
            if str(rec.get("source") or "").startswith("flow") and "AI-generated illustrations (Google Flow), labelled on screen" not in got.credits:
                got.credits.append("AI-generated illustrations (Google Flow), labelled on screen")
        else:
            got.unresolved.append(str(s.row))
    log(f"[What If] Render: {len(got.media)} saved picture(s)/clip(s) used as they are; nothing searched or generated"
        + (f"; {len(got.unresolved)} row(s) have no saved file" if got.unresolved else ""))
    return got


_STOCK_SITES = re.compile(r"pexels\.com|pixabay\.com|^pixabay:|^pexels:", re.I)


def _set_aside_stock_for_nasa(shots: Sequence[Any], images_dir: Path, log: Callable[[str], None]) -> int:
    """A real-subject row (nasa_image / nasa_video) holding a stock site's photo: the Visual Plan lists a NASA picture as Stock Image, so
    its Retry and Use alternatives searched Pexels/Pixabay -- "Voyager 1 launch Titan IIIE" got a fantasy Titan statue (project #016).
    That photo is moved to _set_aside (never deleted) and the row is asked of NASA again; if NASA has nothing, it gets its labelled AI
    stand-in, as every NASA miss does. Returns how many were set aside."""
    import json
    import shutil

    man_path = Path(images_dir) / ".asset_manifest.json"
    try:
        man = json.loads(man_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0
    moved = []
    for s in shots:
        if not (s.row and s.asset.lower().startswith("nasa_")):
            continue
        k = f"{int(s.row):03d}"
        rec = man.get(k)
        if not isinstance(rec, dict) or not str(rec.get("source", "")).startswith("stock_"):
            continue
        if not (_STOCK_SITES.search(str(rec.get("source_url") or "")) or _STOCK_SITES.search(str(rec.get("provider_asset_id") or ""))):
            continue
        f = Path(str(rec.get("local_path") or ""))
        if f.is_file():
            aside = Path(images_dir) / "_set_aside"
            aside.mkdir(exist_ok=True)
            shutil.move(str(f), str(aside / f"{f.name}.stock_for_nasa"))
        man[k] = {**rec, "status": "failed", "local_path": "", "user_override": None,
                  "error": "a stock photo is not a picture of this real subject; asked of NASA again"}
        moved.append(k)
    if moved:
        man_path.write_text(json.dumps(man, indent=1, ensure_ascii=False), encoding="utf-8")
        log(f"[What If] Visual Plan scene(s) {', '.join(str(int(k)) for k in moved)}: a stock site's photo stood in for a real NASA subject; "
            f"set aside (in _set_aside) and asked of NASA again")
    return len(moved)


def _illustration_for(s: Any) -> Optional[str]:
    """What an AI picture of this shot would be, when NASA has no picture of it: the shot's own description, in the house look.
    Never for people (a face must be real or absent)."""
    from .planner import brief, house

    what = (s.extra.get("alt") or "").strip() or " ".join(filter(None, [s.name.title() if s.name else "", s.text])).strip()
    # people are judged on what the picture shows (its alt, else its name), not on the narration around it: "the team chose
    # Titan" kept Titan's haze from its stand-in; Voyager's "Family Portrait" is a mosaic of planets, not a portrait
    subject = (s.extra.get("alt") or "").strip() or (s.name or "").strip() or s.text
    if not what or PEOPLE.search(re.sub(r"\bfamily portrait\b", "", subject, flags=re.I)):
        return None
    return f"flow_image:{house(what)}{brief(what)}"


def _merge(got: Any, more: Any) -> None:
    got.media.update(more.media)
    got.unresolved = list(getattr(got, "unresolved", []) or []) + list(getattr(more, "unresolved", []) or [])
    got.notes = list(getattr(got, "notes", []) or []) + list(getattr(more, "notes", []) or [])
    have = list(getattr(got, "credits", []) or [])
    got.credits = have + [c for c in (getattr(more, "credits", []) or []) if c not in have]


def _numbering_kept() -> bool:
    """Does starmap.media number rows by plan.media_numbers? (Older StarMap numbered every pass 1, 2, 3 ...)"""
    from starmap.media import media_rows

    probe = SimpleNamespace(beats=[SimpleNamespace(id="b", start=0.0, cards=[], clips=[Item(row=7, kind="clip", asset="nasa_image:x", t=0.0)])],
                            media_numbers={7: "7"})
    try:
        return media_rows(probe)[0].scene_number == "7"
    except Exception:
        return False


def _caller(fn: Callable[..., Any]) -> Callable[..., Any]:
    """fn with ai_fallback passed only when fn names it (an older fetch_media would hand it on to the providers)."""
    import inspect

    try:
        named = "ai_fallback" in inspect.signature(fn).parameters
    except (TypeError, ValueError):
        named = False
    return lambda *a, **k: fn(*a, **({**k} if named else {x: v for x, v in k.items() if x != "ai_fallback"}))


_CALLBACKS = ("on_scene_start", "on_scene_generating", "on_scene_complete")


def _renumbered(kw: Dict[str, Any], numbers: Dict[str, str]) -> Dict[str, Any]:
    """kw with the Visual Plan callbacks reporting a later pass's scene (numbered 45, 53 ...) under the number its row has in the
    table (21, 23 ...): those rows stayed QUEUED for the whole run, as nothing ever reported on their numbers."""
    import copy
    import dataclasses

    def back(obj: Any) -> Any:
        n = numbers.get(str(getattr(obj, "scene_number", "")))
        if n is None:
            return obj
        if dataclasses.is_dataclass(obj):
            return dataclasses.replace(obj, scene_number=n)
        obj = copy.copy(obj)
        obj.scene_number = n
        return obj

    def wrap(cb: Callable[..., Any]) -> Callable[..., Any]:
        return lambda *a, **k: cb(*[back(x) for x in a], **k)

    return {**kw, **{c: wrap(kw[c]) for c in _CALLBACKS if callable(kw.get(c))}}


def fetch(shots: Sequence[Any], images_dir: Path, *, log: Callable[[str], None] = print, fetcher: Optional[Callable[..., Any]] = None,
          **kw: Any) -> Any:
    """Fetch every asset shot's file; sets shot.file / shot.credit. A real-picture request (nasa_image) that NASA cannot answer
    is NEVER filled by a stock photo (a Moon photo once stood in for "the first colour photos of Venus"): it gets an AI
    illustration of the same thing, labelled AI ILLUSTRATION on screen, or -- for people -- nothing, and the compiler's fallback
    (a globe or a typographic shot) takes over."""
    from starmap.media import fetch_media

    if kw.pop("render_only", False):
        return _from_saved(shots, Path(images_dir), log)
    as_plan(shots)                       # numbers the shots' rows as the Visual Plan does
    _take_visual_plan_sources(shots, kw.get("scene_rows"), log)
    # a ready row is the author's choice: never set aside or searched again at Generate (see starmap.media.recheck_cached_media)
    if kw.get("scene_rows"):
        realign_saved(Path(images_dir), [r for r in kw["scene_rows"] if hasattr(r, "scene_number")], log)
    plan = as_plan(shots)
    call = _caller(fetcher or fetch_media)
    # the extra passes number their rows after the first pass's; where StarMap cannot keep those numbers, each pass gets its own
    # folder instead, so a later pass's 001.png can never replace the first pass's 001.jpg
    kept = _numbering_kept()
    pass_dir = lambda k: Path(images_dir) if kept else Path(images_dir) / f"whatif_pass{k}"  # noqa: E731
    # naming a mission keeps NASA's answer: no stock search stands in for it
    mission = {str(s.row): (s.name or s.place or "mission") for s in shots if s.row and s.asset.lower().startswith("nasa_")}
    got = call(plan, Path(images_dir), log=log, ai_fallback=False, mission=mission or "", recheck_warn_only=True, **kw)
    _apply(shots, got)
    kw.pop("scene_rows", None)         # the Visual Plan table holds the first pass's rows only; the extra passes use their own
    # a second real source for what NASA does not hold: Wikimedia Commons (only for a named craft or place, so a search cannot drift to
    # a lookalike), then -- only if that is empty too -- an AI illustration of the same thing
    missed = [s for s in shots if s.row and not s.file and s.asset.lower().startswith("nasa_")]
    first_rows = {s.id: str(s.row) for s in missed}           # their Visual Plan numbers (the later passes number them anew)
    first = max([x.row for x in shots if x.row] or [0]) + 1
    later_rows: set = set()                                     # the numbers the later passes gave them (never shown in the table)
    named = [s for s in missed if s.name and not PEOPLE.search(s.name + " " + s.text)]
    if named:
        for s in named:
            s.extra["_nasa_asset"] = s.asset
            s.asset = "commons_image:" + s.asset.split(":", 1)[1].strip()[:90]
            s.cite = ("REAL IMAGE", "")
        log(f"[What If] NASA has no picture of {', '.join(s.name for s in named)}; trying Wikimedia Commons")
        plan2 = as_plan(named, start_row=first)
        later_rows.update(str(s.row) for s in named)
        got2 = call(plan2, pass_dir(2), log=log, ai_fallback=False, mission=mission or "",
                    **_renumbered(kw, {str(s.row): first_rows[s.id] for s in named}))
        _apply(named, got2)
        _merge(got, got2)
        # a Commons picture is also recorded under the Visual Plan row it fills: Render reads only that row (project #023: rows
        # 10, 13 and 44 showed READY from the Commons stand-ins 095/096/101 but had no saved file, so Render stopped)
        _save_on_table_rows(named, {str(s.row): first_rows[s.id] for s in named}, Path(images_dir))
        first = max(x.row for x in named) + 1
    redo = []
    # every miss gets its AI picture, not only those in the opening (FLOW_OPEN_S): a later miss used to be left out, and the video
    # was rendered with a title card where its picture should be (project #016: 9 of 11 misses). One still per miss, never a clip.
    for s in [s for s in missed if not s.file]:
        alt = _illustration_for(s)
        if alt:
            log(f"[What If] shot {s.id}: no real picture of {s.name or s.place or 'this'} was found; an AI illustration stands in (labelled on screen)")
            s.asset, s.cite = alt, ("AI ILLUSTRATION", "")
            redo.append(s)
    if redo:
        plan3 = as_plan(redo, start_row=first)
        stand_in_rows = {str(s.row): first_rows[s.id] for s in redo if s.id in first_rows}
        later_rows.update(str(s.row) for s in redo)
        got3 = call(plan3, pass_dir(3), log=log, ai_fallback=False, **_renumbered(kw, {str(s.row): first_rows[s.id] for s in redo if s.id in first_rows}))
        _apply(redo, got3)
        _merge(got, got3)
        _save_on_table_rows(redo, stand_in_rows, Path(images_dir))
    # a NASA miss that a later pass filled (Commons, or an AI illustration) is not left out: only shots still without a file are
    # reported, under the number the Visual Plan shows (4 rows were flagged "needs action" although the video had their stand-ins)
    filled = {first_rows[s.id] for s in missed if s.file}
    if filled:
        log(f"[What If] Visual Plan scene(s) {', '.join(sorted(filled, key=int))}: no NASA picture, a stand-in from a later search is used")
    stand_in_rows = {str(s.row) for s in shots if s.id in first_rows} | later_rows
    got.unresolved = [n for n in (getattr(got, "unresolved", []) or []) if str(n) not in filled and str(n) not in stand_in_rows] + \
                     [first_rows[s.id] for s in missed if not s.file]
    got.unresolved = list(dict.fromkeys(got.unresolved))
    return got


_SAME_KIND = {"image": {"flow_image"}, "video": {"flow_video"}, "stock_image": {"nasa_image", "stock_image", "commons_image"},
              "stock_video": {"stock_video"}, "commons_image": {"commons_image", "stock_image"}}


def _same_text(a: str, b: str) -> bool:
    n = lambda s: " ".join(re.sub(r"[^\w\s]", " ", (s or "").lower()).split())   # noqa: E731
    return bool(n(a)) and n(a) == n(b)


def _subject(text: str) -> str:
    """A picture brief without its framing words or camera move: what it shows."""
    t = re.split(r"\s+--\s+", text or "")[0]
    t = re.sub(r"\.?\s*slow, smooth camera push-in; gentle drift\.?\s*$", "", t, flags=re.I)
    return " ".join(re.sub(r"[^\w\s]", " ", t.lower()).split())


def realign_saved(images_dir: Path, rows: Sequence[Any], log: Callable[[str], None] = print) -> int:
    """Every Visual Plan row whose own saved record is for something else, while a finished file made for exactly this row's text is
    saved under another number, gets that file at its own number (a copy: the other number keeps its own). Shot lists renumber when a
    source changes (a row added or split), and the files stay under the old numbers: 14 made assets showed as missing in project #013.
    Matches only the exact same text and the same kind of source (a NASA row shows as stock_image). Returns how many rows it filled."""
    import json
    import shutil
    import tempfile

    images_dir = Path(images_dir)
    man_path = images_dir / ".asset_manifest.json"
    try:
        man = json.loads(man_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0
    key = lambda n: f"{int(str(n).strip()):03d}"   # noqa: E731
    done = lambda rec: isinstance(rec, dict) and rec.get("status") == "complete" and Path(str(rec.get("local_path") or "/-")).is_file()  # noqa: E731
    text_of = lambda r: (getattr(r, "prompt", "") or getattr(r, "stock", "") or "")   # noqa: E731
    rec_text = lambda rec: rec.get("prompt") or rec.get("stock_query") or ""   # noqa: E731
    plan = []
    for r in rows:
        try:
            k = key(r.scene_number)
        except (TypeError, ValueError):
            continue
        kinds = _SAME_KIND.get((getattr(r, "asset_type", "") or "").lower())
        own = man.get(k)
        # a row's own finished file stays when it was made for this row (the same text) or the user chose it; a file made for another
        # row's text (the numbers shifted, #013) gives way to the finished file made for exactly this text -- the old one goes to
        # _set_aside, never deleted (asked for by the owner, 2026-10-18)
        if not kinds or not text_of(r):
            continue
        if done(own) and (own.get("user_override") or _same_text(rec_text(own), text_of(r))):
            continue
        donor = next((d for d, rec in man.items() if d != k and done(rec) and rec.get("source") in kinds and _same_text(rec_text(rec), text_of(r))), None)
        if donor is None and kinds & {"flow_image", "flow_video"}:
            # a split shot's other half (vary() added "-- medium view"; a clip says how it moves): the same subject's picture, the
            # nearest number first, so a half whose own picture was never made still shows its twin's instead of nothing
            subj = _subject(text_of(r))
            twins = sorted((abs(int(d) - int(k)), d) for d, rec in man.items() if d != k and done(rec) and str(d).isdigit()
                           and rec.get("source") in ("flow_image", "flow_video") and subj and _subject(rec_text(rec)) == subj)
            donor = twins[0][1] if twins and twins[0][0] <= 3 else None
        if donor:
            plan.append((r, k, donor))
    if not plan:
        return 0
    snap = Path(tempfile.mkdtemp(prefix="whatif_realign_", dir=str(images_dir)))
    try:
        copies = {}
        for _r, _k, d in plan:                              # every donor copied first: a chain of shifted rows never overwrites itself
            if d not in copies:
                src = Path(man[d]["local_path"])
                copies[d] = (snap / f"{d}{src.suffix.lower()}", dict(man[d]))
                shutil.copy2(src, copies[d][0])
        aside = images_dir / "_set_aside"
        for r, k, d in plan:
            src, rec = copies[d]
            for old in images_dir.glob(f"{k}.*"):
                aside.mkdir(exist_ok=True)
                tgt, n = aside / f"{old.name}.realigned", 1
                while tgt.exists():                  # an earlier set-aside copy is kept too, never overwritten
                    tgt, n = aside / f"{old.name}.realigned{n}", n + 1
                shutil.move(str(old), str(tgt))
            dst = images_dir / f"{k}{src.suffix}"
            shutil.copy2(src, dst)
            man[k] = {**rec, "local_path": str(dst), "script_segment": getattr(r, "script_segment", rec.get("script_segment", ""))}
            if rec.get("prompt"):                # the file is this row's now: recorded under its text (a twin's had other framing words)
                man[k]["prompt"] = getattr(r, "prompt", "") or rec["prompt"]
            elif rec.get("stock_query"):
                man[k]["stock_query"] = getattr(r, "stock", "") or rec["stock_query"]
        man_path.write_text(json.dumps(man, indent=1, ensure_ascii=False), encoding="utf-8")
    finally:
        shutil.rmtree(snap, ignore_errors=True)
    log(f"[What If] {len(plan)} saved picture(s)/clip(s) were filed under other scene numbers; put back on their rows: "
        + ", ".join(r.scene_number for r, _k, _d in plan))
    return len(plan)
