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


def asset_shots(shots: Sequence[Any]) -> List[Any]:
    """The shots that name a source (file: ones are the author's own and need no fetching)."""
    return [s for s in shots if s.asset and not s.asset.lower().startswith("file:")]


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


def _illustration_for(s: Any) -> Optional[str]:
    """What an AI picture of this shot would be, when NASA has no picture of it: the shot's own description, in the house look.
    Never for people (a face must be real or absent)."""
    from .planner import brief, house

    what = (s.extra.get("alt") or "").strip() or " ".join(filter(None, [s.name.title() if s.name else "", s.text])).strip()
    if not what or PEOPLE.search(what):
        return None
    return f"flow_image:{house(what)}{brief(what)}"


def _merge(got: Any, more: Any) -> None:
    got.media.update(more.media)
    got.unresolved = list(getattr(got, "unresolved", []) or []) + list(getattr(more, "unresolved", []) or [])
    got.notes = list(getattr(got, "notes", []) or []) + list(getattr(more, "notes", []) or [])
    have = list(getattr(got, "credits", []) or [])
    got.credits = have + [c for c in (getattr(more, "credits", []) or []) if c not in have]


def fetch(shots: Sequence[Any], images_dir: Path, *, log: Callable[[str], None] = print, fetcher: Optional[Callable[..., Any]] = None,
          **kw: Any) -> Any:
    """Fetch every asset shot's file; sets shot.file / shot.credit. A real-picture request (nasa_image) that NASA cannot answer
    is NEVER filled by a stock photo (a Moon photo once stood in for "the first colour photos of Venus"): it gets an AI
    illustration of the same thing, labelled AI ILLUSTRATION on screen, or -- for people -- nothing, and the compiler's fallback
    (a globe or a typographic shot) takes over."""
    from starmap.media import fetch_media

    as_plan(shots)                       # numbers the shots' rows as the Visual Plan does
    _take_visual_plan_sources(shots, kw.get("scene_rows"), log)
    if kw.get("scene_rows"):
        realign_saved(Path(images_dir), [r for r in kw["scene_rows"] if hasattr(r, "scene_number")], log)
    plan = as_plan(shots)
    # naming a mission keeps NASA's answer: no stock search stands in for it
    mission = {str(s.row): (s.name or s.place or "mission") for s in shots if s.row and s.asset.lower().startswith("nasa_")}
    got = (fetcher or fetch_media)(plan, Path(images_dir), log=log, ai_fallback=False, mission=mission or "", **kw)
    _apply(shots, got)
    kw.pop("scene_rows", None)         # the Visual Plan table holds the first pass's rows only; the extra passes use their own
    # a second real source for what NASA does not hold: Wikimedia Commons (only for a named craft or place, so a search cannot drift to
    # a lookalike), then -- only if that is empty too -- an AI illustration of the same thing
    missed = [s for s in shots if s.row and not s.file and s.asset.lower().startswith("nasa_")]
    first_rows = {s.id: str(s.row) for s in missed}           # their Visual Plan numbers (the later passes number them anew)
    first = max([x.row for x in shots if x.row] or [0]) + 1
    named = [s for s in missed if s.name and not PEOPLE.search(s.name + " " + s.text)]
    if named:
        for s in named:
            s.extra["_nasa_asset"] = s.asset
            s.asset = "commons_image:" + s.asset.split(":", 1)[1].strip()[:90]
            s.cite = ("REAL IMAGE", "")
        log(f"[What If] NASA has no picture of {', '.join(s.name for s in named)}; trying Wikimedia Commons")
        got2 = (fetcher or fetch_media)(as_plan(named, start_row=first), Path(images_dir), log=log, ai_fallback=False, mission=mission or "", **kw)
        _apply(named, got2)
        _merge(got, got2)
        first = max(x.row for x in named) + 1
    redo = []
    for s in [s for s in missed if not s.file]:
        alt = _illustration_for(s)
        if alt:
            log(f"[What If] shot {s.id}: no real picture of {s.name or s.place or 'this'} was found; an AI illustration stands in (labelled on screen)")
            s.asset, s.cite = alt, ("AI ILLUSTRATION", "")
            redo.append(s)
    if redo:
        got3 = (fetcher or fetch_media)(as_plan(redo, start_row=first), Path(images_dir), log=log, ai_fallback=False, **kw)
        _apply(redo, got3)
        _merge(got, got3)
    # a NASA miss that a later pass filled (Commons, or an AI illustration) is not left out: only shots still without a file are
    # reported, under the number the Visual Plan shows (4 rows were flagged "needs action" although the video had their stand-ins)
    filled = {first_rows[s.id] for s in missed if s.file}
    if filled:
        log(f"[What If] Visual Plan scene(s) {', '.join(sorted(filled, key=int))}: no NASA picture, a stand-in from a later search is used")
    stand_in_rows = {str(s.row) for s in shots if s.id in first_rows}
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
        if not kinds or not text_of(r) or (done(own) and _same_text(rec_text(own), text_of(r))):
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
                shutil.move(str(old), str(aside / f"{old.name}.realigned"))
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
