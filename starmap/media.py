"""StarMap's pictures and clips in the app's EXISTING Visual Plan table, and getting them.

Every card and clip that names a source (nasa_image:, stock_video:, flow_video: ...) is one Visual Plan row, numbered 1, 2, 3 ...
in CSV order; file:<name> assets are the author's own files and are not rows. The rows are resolved like every other style's,
into one folder with its .asset_manifest.json (so a replacement made in the table survives re-runs and nothing is fetched or
generated twice):
  * nasa_image  -> shown as a stock_image row; StarMap tries NASA's image library first (starmap/nasa_images.py)
  * nasa_video  -> the app's NASA video provider (providers/nasa)
  * stock_ / flow_ / youtube_ / archive_ / commons_  -> the shared resolver (video_generator.resolve_scene_assets)
AI material is always labelled on screen (AI ILLUSTRATION) and in the credits. When NASA has no picture of a mission scene, an AI
still (Google Flow) may stand in -- only for scenes no camera recorded: never a real person, never a photographed event, never
something passed off as a real photograph (ai_fallback_ok). If Flow is not there or fails, the scene is left out as before.
"""

from __future__ import annotations

import json

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from .beat_csv import Plan, asset_source

TABLE_TYPE = {"nasa_image": "stock_image"}        # how a StarMap source appears in the Visual Plan table
AI_LABEL = "AI ILLUSTRATION"                      # on screen on every AI-made picture or clip
_REAL_ONLY = re.compile(r"\b(photo|photograph|photographed|portrait|press conference|team|scientists?|engineers?|astronauts?|crew|"
                        r"people|person|man|woman|family|control room|mission control|launch of|lifting off|liftoff|selfie|"
                        r"signed|handwritten|newspaper|headline|"
                        # a craft's own picture (its real image exists, under another title): never faked
                        r"image|images|imaged|mosaic|close-up|closeup|view of|global view|captured|picture of|frame|"
                        # text-bearing graphics: AI pictures draw text badly
                        r"diagram|chart|graph|map|labell?ed|infographic)\b", re.I)
_NAME = re.compile(r"\b[A-Z][a-z]+ (?:[A-Z]\.? )?[A-Z][a-z]+\b")
_NOT_NAMES = re.compile(r"\b(Voyager|Jupiter|Saturn|Uranus|Neptune|Mars|Venus|Mercury|Earth|Moon|Sun|Pluto|Io|Europa|Titan|Ganymede|"
                        r"Callisto|Great|Red|Spot|Golden|Record|Milky|Way|Solar|System|Pale|Blue|Dot|Deep|Space|Network|Alpha|"
                        r"Centauri|Oort|Cloud|Kuiper|Belt|Pioneer|Cassini|Apollo|Artemis|Orion|Saturn V|Interstellar)\b")
_VIDEO_EXT = {".mp4", ".mov", ".m4v", ".webm", ".mkv"}


@dataclass
class MediaRow:
    scene_number: str
    row: int                                     # the CSV row
    kind: str                                    # card | clip
    source: str                                  # nasa_image, stock_video, ...
    prompt: str
    beat: str
    t: float
    label: str = ""

    def as_dict(self) -> Dict[str, str]:
        what = "photo card" if self.kind == "card" else "footage"
        when = f"{int(self.t // 60)}:{int(self.t % 60):02d}  " if self.t >= 0 else ""
        seg = f"{when}StarMap beat {self.beat} · {what}" + (f" — {self.label}" if self.label else "")
        if self.source == "nasa_image":
            seg += " (NASA image library first)"
        return {"scene_number": self.scene_number, "script_segment": seg, "asset_type": TABLE_TYPE.get(self.source, self.source), "prompt": self.prompt}


def media_rows(plan: Plan) -> List[MediaRow]:
    out: List[MediaRow] = []
    for b in plan.beats:
        items = [(c, "card") for c in b.cards] + [(c, "clip") for c in b.clips]
        for it, kind in sorted(items, key=lambda x: x[0].row):
            src = asset_source(it.asset)
            if src == "file":
                continue
            prompt = " ".join(it.asset.split(":", 1)[1].split())
            number = getattr(plan, "media_numbers", {}).get(it.row) or str(len(out) + 1)   # the author's CSV numbers them (see heal)
            out.append(MediaRow(number, it.row, kind, src, prompt, b.id, it.t if it.t is not None else b.start, it.label or it.why))
    return out


def media_rows_from_csv(text: str) -> List[MediaRow]:
    """The same rows, numbered the same way, straight from the CSV (no narration needed: no times). Rows with a bad asset are
    left out here; loading the plan reports them."""
    import csv
    import io

    out: List[MediaRow] = []
    for n, r in enumerate(csv.DictReader(io.StringIO(text.lstrip("\ufeff"))), start=2):
        kind = (r.get("row") or "").strip().lower()
        if kind not in ("card", "clip"):
            continue
        asset = (r.get("asset") or "").strip()
        try:
            src = asset_source(asset)
        except ValueError:
            continue
        if src == "file":
            continue
        label = (r.get("label") or "").strip() if kind == "card" else (r.get("why") or "").strip()
        out.append(MediaRow(str(len(out) + 1), n, kind, src, " ".join(asset.split(":", 1)[1].split()), (r.get("beat") or "").strip(), -1.0, label))
    return out


def visual_dicts(plan: Plan) -> List[Dict[str, str]]:
    """The rows for the Visual Plan table (SceneRow.from_csv_row shape)."""
    return [m.as_dict() for m in media_rows(plan)]


def _checked_nasa_video(provider_cls: Any) -> Any:
    """The shared NASA video provider, with StarMap's picture check on every candidate (nasa_images.contradicts: another
    mission, the asked-for subject not shown, decades from the asked-for year). Its search falls back to one word ("Titan",
    "NASA") and took whatever came first: a 2005 shuttle touchdown for "Titan IIIE-Centaur launch of Voyager 1 in September
    1977", an air-quality briefing for the 2013 interstellar announcement. A row with no candidate left is left out (its time
    goes to the rest of the beat), never replaced by an unrelated clip."""
    from .nasa_images import contradicts

    class Checked(provider_cls):
        def _search(self, scene, log, exclude_ids):
            want = scene.prompt or ""
            kept = []
            for c in super()._search(scene, log, exclude_ids):
                why = contradicts(want, c.title or "", c.description or "", getattr(c, "date", "") or "")
                if why:
                    log(f"[StarMap] NASA video {c.nasa_id} skipped for scene {scene.scene_number}: {why}")
                    continue
                kept.append(c)
            return kept

    return Checked


def make_resolver(nasa_clip_s: float = 6.0, base: Optional[Callable[..., Any]] = None) -> Callable[..., Any]:
    """A resolver for pakmap.sourcing.fetch_scenes that adds the NASA video provider to the shared one: nasa_video rows go to an
    AssetManager with that provider (same manifest, same reuse rule), the rest to video_generator.resolve_scene_assets."""

    def resolve(row_dicts: List[dict], images_dir: Path, log: Callable[[str], None] = print, on_scene_start=None, on_scene_complete=None,
                on_scene_generating=None, on_manager_ready=None, **kw: Any) -> None:
        nasa = [d for d in row_dicts if (d.get("asset_type") or "").lower() == "nasa_video"]
        rest = [d for d in row_dicts if d not in nasa]
        callbacks = dict(on_scene_start=on_scene_start, on_scene_complete=on_scene_complete, on_scene_generating=on_scene_generating)
        if nasa:
            from asset_manager import AssetManager
            from providers.base import SceneRow
            from providers.nasa.provider import NasaProvider

            mgr = AssetManager(Path(images_dir), nasa_provider=_checked_nasa_video(NasaProvider)(clip_duration=nasa_clip_s), log=log)
            if on_manager_ready is not None:
                try:
                    on_manager_ready(mgr)
                except Exception:
                    pass
            mgr.resolve_all([SceneRow.from_csv_row(d) for d in nasa], **{k: v for k, v in callbacks.items() if v is not None})
        if rest:
            fn = base
            if fn is None:
                import video_generator as vg

                fn = vg.resolve_scene_assets
            fn(rest, images_dir, log=log, on_manager_ready=on_manager_ready, **{k: v for k, v in callbacks.items() if v is not None}, **kw)

    return resolve


@dataclass
class Fetched:
    media: Dict[str, Dict[str, str]] = field(default_factory=dict)     # "row:<csv row>" -> {"file", "credit"}
    missing: List[str] = field(default_factory=list)                   # messages, one per scene still without a file
    unresolved: List[str] = field(default_factory=list)                # their scene numbers
    credits: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)                     # rows left out on purpose, and why


def still_of(video: Path, out: Path) -> Path:
    """A photo card needs a still: the clip's frame one second in (or its first)."""
    from map_scene.render import _ffmpeg

    out.parent.mkdir(parents=True, exist_ok=True)
    for ss in ("1", "0"):
        subprocess.run([_ffmpeg(), "-y", "-loglevel", "error", "-ss", ss, "-i", str(video), "-frames:v", "1", "-q:v", "2", str(out)],
                       check=False, capture_output=True)
        if out.is_file() and out.stat().st_size > 0:
            return out
    raise RuntimeError(f"could not take a still from {video.name}")


def _report_left_out(provider_kwargs: Dict[str, Any], table: Sequence[Any], n: str, why: str) -> None:
    """Tell the Visual Plan table a row was left out (it would otherwise stay QUEUED): the app's own scene callback, with a
    failed result carrying the reason, so the row shows NEEDS ACTION with Retry / Change source."""
    done = provider_kwargs.get("on_scene_complete")
    row = next((r for r in table if str(r.scene_number) == n), None)
    if done is None or row is None:
        return
    try:
        from providers.base import AssetResult, AssetSource, SceneStatus

        done(row, AssetResult(scene_number=n, path=None, media_type=None, source=AssetSource.STOCK_IMAGE, status=SceneStatus.FAILED, error=why))
    except Exception:
        pass


REJECTED_FILE = ".starmap_rejected.json"      # in the media folder: {scene number: [file ids never to use for it again]}
_OWN_SOURCES = ("manual", "local")              # the user's own file: never second-guessed
_NASA = ("nasa_image", "nasa_video")


def rejected_ids(images_dir: Path) -> Dict[str, List[str]]:
    try:
        return json.loads((Path(images_dir) / REJECTED_FILE).read_text(encoding="utf-8"))
    except Exception:
        return {}


def _reject(images_dir: Path, scene: str, asset_id: str) -> None:
    if not asset_id:
        return
    got = rejected_ids(images_dir)
    if asset_id not in got.setdefault(scene, []):
        got[scene].append(asset_id)
        (Path(images_dir) / REJECTED_FILE).write_text(json.dumps(got, indent=1), encoding="utf-8")


def _vqa_mismatch(images_dir: Path) -> Dict[tuple, str]:
    """The app's visual QA verdicts (media folder .visual_qa_cache.json) that say a file does not match its row:
    (scene number, file id) -> why."""
    try:
        cache = json.loads((Path(images_dir) / ".visual_qa_cache.json").read_text(encoding="utf-8"))
    except Exception:
        return {}
    out = {}
    for v in (cache.values() if isinstance(cache, dict) else []):
        if isinstance(v, dict) and "semantic mismatch" in (v.get("failure_reasons") or []) and v.get("asset_id"):
            out[(str(int(v["scene_number"])), str(v["asset_id"]))] = f"visual QA: semantic mismatch ({v.get('semantic_match')})"
    return out


def recheck_cached_media(rows_info: Sequence[Any], images_dir: Path, *, manifest_cls: Any = None, log: Callable[[str], None] = print,
                         get: Optional[Callable] = None) -> List[str]:
    """Files found by an earlier Generate are reused without a new search, so a check added since never saw them: the 011
    Voyager project kept a 2005 shuttle touchdown for its 1977 launch, an air-quality briefing for the 2013 interstellar
    announcement, a surveying instrument under a named JPL engineer and a woman at a fridge for a transmitter's power. Before
    reuse, each cached file is checked against its row:
      * a nasa_image / nasa_video row holds NASA material (a stock photo never stands in for the mission's own picture);
      * NASA material shows what the row asks for (NASA's own title and caption by id: metadata only, nothing downloaded);
      * the app's visual QA has not called it a semantic mismatch.
    A file that fails is marked failed (this Generate searches again under today's checks, and leaves the row out when nothing
    fits) and its id goes on the media folder's rejected list, so it can never return for that row. The user's own files
    (manual, local) and labelled AI stand-ins are left alone; NASA not answering changes nothing. Returns the scenes failed."""
    from . import nasa_images

    if manifest_cls is None:
        from asset_manager import AssetManifest as manifest_cls
    man = manifest_cls(images_dir)
    get = nasa_images._default_get(get)
    vqa = _vqa_mismatch(images_dir)
    failed: List[str] = []

    def fail(n: str, rec: Dict[str, Any], why: str) -> None:
        man.set(n, {**rec, "status": "failed", "error": f"not the asked-for picture: {why}", "relevance": why})
        _reject(images_dir, str(int(n)), str(rec.get("provider_asset_id") or ""))
        failed.append(n)
        log(f"[StarMap] scene {n}: the cached file {rec.get('provider_asset_id')} ({str(rec.get('title') or '')[:50]}) {why}; searching again")

    banned = rejected_ids(images_dir)
    for m in rows_info:
        n = m.scene_number
        rec = man.get(n) or {}
        nid = str(rec.get("provider_asset_id") or "")
        src = str(rec.get("source") or "")
        if rec.get("status") != "complete":
            continue
        if nid and nid in banned.get(str(int(n)), []):
            fail(n, rec, "is on this project's rejected list for this row")
            continue
        if rec.get("user_override") or src in _OWN_SOURCES or src.startswith("flow"):
            if rec.get("user_override") and m.source in _NASA and src not in _NASA:
                log(f"[StarMap] scene {n}: a {src} picture stands in for the NASA row {m.prompt!r} (your Visual Plan choice, kept): check it shows that")
            continue
        if m.source in _NASA and src not in _NASA:
            fail(n, rec, f"is a {src} file for a NASA row (no stock picture stands in for the mission's own)")
            continue
        if (str(int(n)), nid) in vqa:
            fail(n, rec, vqa[(str(int(n)), nid)])
            continue
        if m.source not in _NASA or not nid or rec.get("relevance"):
            continue
        try:
            r = get(nasa_images.SEARCH_URL, params={"nasa_id": nid}, headers={"User-Agent": nasa_images.USER_AGENT}, timeout=20)
            items = (r.json().get("collection") or {}).get("items", [])
        except Exception:
            continue
        if not items:
            continue
        d = (items[0].get("data") or [{}])[0]
        why = nasa_images.contradicts(m.prompt, d.get("title", ""), (d.get("description") or "")[:2000], (d.get("date_created") or "")[:10])
        if why:
            fail(n, rec, why)
        else:
            man.set(n, {**rec, "relevance": "ok"})
    return failed


def fetch_media(plan: Plan, images_dir: Path, *, scene_rows: Optional[Sequence[Any]] = None, log: Callable[[str], None] = print,
                cancel_check: Optional[Callable[[], bool]] = None, stills_dir: Optional[Path] = None, nasa_get=None,
                fetch_scenes: Optional[Callable[..., Any]] = None, manifest_cls: Any = None, mission: Any = "", ai_fallback: bool = True,
                ai_house: str = "", **provider_kwargs: Any) -> Fetched:
    """Every row's file (or why not). `scene_rows` is the Visual Plan table as the user left it; without it the rows come from the plan.
    `mission` steers NASA picture search towards the story's own mission: one name, or {scene number: name} when the video
    covers several missions (each row then prefers its own beat's mission)."""
    from providers.base import SceneRow

    from . import nasa_images

    rows_info = media_rows(plan)
    out = Fetched()
    if not rows_info:
        return out
    table = list(scene_rows) if scene_rows else [SceneRow.from_csv_row(m.as_dict()) for m in rows_info]
    wanted = {m.scene_number for m in rows_info}
    table = [r for r in table if str(r.scene_number) in wanted]
    all_rows = list(table)                                     # before NASA's misses are taken out (to report them)
    nasa_rows = {m.scene_number: m.prompt for m in rows_info if m.source == "nasa_image"}
    recheck_cached_media(rows_info, Path(images_dir), manifest_cls=manifest_cls, log=log, get=nasa_get)
    unanswered: Dict[str, str] = {}
    no_match: Dict[str, str] = {}
    if nasa_rows:
        nasa_images.prefetch(table, nasa_rows, images_dir, manifest_cls=manifest_cls, log=log, get=nasa_get, cancel_check=cancel_check,
                             context=mission, unanswered=unanswered, no_match=no_match)
        # A story about a mission keeps NASA's answer: no stock photo stands in for the mission's own picture. A story with no
        # mission (a moon, a planet, the scale of space) lets a NASA miss try the stock search, which also reaches Wikimedia.
        mission_story = (any(str(v).strip() for v in mission.values()) if isinstance(mission, dict) else bool(str(mission or "").strip())) \
            or any("." in (b.date or "") or b.extra.get("mission") or any(L.type in ("craft", "path", "orbit") for L in b.layers)
                   for b in plan.beats)
        if not mission_story:
            for n in list(no_match):
                log(f"[StarMap] No NASA image for scene {n}; this story names no mission, so it tries the stock search")
                del no_match[n]
        # not to the stock search: NASA was unreachable, or (for a mission) has no picture that is really this one
        table = [r for r in table if str(r.scene_number) not in unanswered and str(r.scene_number) not in no_match]
    if fetch_scenes is None:
        from pakmap.sourcing import fetch_scenes
    resolver = provider_kwargs.pop("resolver", None) or make_resolver()
    got = fetch_scenes(table, images_dir, resolver=resolver, manifest_cls=manifest_cls, log=log, dedupe=True, **provider_kwargs)
    # NASA has no real picture of a mission scene: an AI still may stand in, where that is honest (see ai_fallback_ok)
    ai_made: Dict[str, str] = {}
    standins = [m for m in rows_info if m.scene_number in no_match and ai_fallback and ai_fallback_ok(m.prompt)]
    if standins and not (cancel_check and cancel_check()):
        try:
            rows = [SceneRow.from_csv_row({**m.as_dict(), "asset_type": "flow_image", "prompt": ai_prompt(m.prompt, ai_house)}) for m in standins]
            got_ai = fetch_scenes(rows, images_dir, resolver=resolver, manifest_cls=manifest_cls, log=log, dedupe=True, **provider_kwargs)
            for m in standins:
                if got_ai.paths.get(m.scene_number):
                    ai_made[m.scene_number] = str(got_ai.paths[m.scene_number])
                    no_match.pop(m.scene_number, None)
                    log(f"[StarMap] scene {m.scene_number}: no NASA picture, an AI illustration stands in (labelled on screen)")
        except Exception as exc:                                # Flow not set up, a quota, a network error: left out as before
            log(f"[StarMap] AI stand-ins skipped ({exc}); those scenes are left out")
    if manifest_cls is None:
        from asset_manager import AssetManifest as manifest_cls
    for m in rows_info:
        n = m.scene_number
        if n in unanswered:                                     # never stops the video: left out, a clip's time goes to the rest
            why = f"NASA's image library did not answer ({unanswered[n]})"
            out.media[f"row:{m.row}"] = {"file": ""}
            _report_left_out(provider_kwargs, all_rows, n, f"Left out: {why}. Retry it, then Generate again.")
            out.notes.append(f"Visual Plan scene {n} ({m.kind} in beat {m.beat}, CSV row {m.row}: nasa_image:{m.prompt}): {why}, so it is left out. "
                             f"Retry it in the Visual Plan and Generate again to add it.")
            out.unresolved.append(n)
            continue
        if n in got.skipped:
            out.media[f"row:{m.row}"] = {"file": ""}
            continue
        if n in no_match:                                       # left out: a card goes, a clip leaves its time to the map
            out.media[f"row:{m.row}"] = {"file": ""}
            _report_left_out(provider_kwargs, all_rows, n, f"Left out: {no_match[n]} (nasa_image:{m.prompt}). Change source, "
                                                         f"use a local clip, or describe it the way NASA titles it.")
            out.notes.append(f"Visual Plan scene {n} ({m.kind} in beat {m.beat}, CSV row {m.row}: nasa_image:{m.prompt}): {no_match[n]}, "
                             f"so it is left out. Describe it the way NASA titles it, or give it another source in the Visual Plan.")
            continue
        if n in ai_made:
            out.media[f"row:{m.row}"] = {"file": ai_made[n], "credit": AI_LABEL}
            line = "AI-generated illustrations (Google Flow), labelled on screen"
            if line not in out.credits:
                out.credits.append(line)
            continue
        path = got.paths.get(n)
        if not path:                                            # never stops the video: left out, a clip's time goes to the rest
            why = got.missing.get(n, "no file")
            out.media[f"row:{m.row}"] = {"file": ""}
            out.notes.append(f"Visual Plan scene {n} ({m.kind} in beat {m.beat}, CSV row {m.row}: {m.source}:{m.prompt}): {why}, so it is left out. "
                             f"Retry, Change source or Use local clip in the Visual Plan and Generate again to add it.")
            out.unresolved.append(n)
            continue
        p = Path(path)                                          # a card's clip stays a clip: the card plays it
        rec = manifest_cls(images_dir).get(n) or {}
        if str(rec.get("provider_asset_id") or "") in rejected_ids(Path(images_dir)).get(str(int(n)), []):
            out.media[f"row:{m.row}"] = {"file": ""}             # rejected before for this row: left out, never back
            out.notes.append(f"Visual Plan scene {n} ({m.kind} in beat {m.beat}, CSV row {m.row}): the search found {rec.get('provider_asset_id')} "
                             f"again, which was rejected for this row before, so it is left out")
            continue
        credit = rec.get("credit") or _credit_from(rec)
        # only NASA material is credited on screen; stock (Pexels and the like) is credited in the credits file alone
        on_screen = credit and m.kind == "clip" and _is_nasa(rec)
        if m.source.startswith("flow_"):                        # AI material the CSV asked for: labelled like a stand-in
            out.media[f"row:{m.row}"] = {"file": str(p), "credit": AI_LABEL}
            line = "AI-generated illustrations (Google Flow), labelled on screen"
            if line not in out.credits:
                out.credits.append(line)
            continue
        out.media[f"row:{m.row}"] = {"file": str(p), **({"credit": credit} if on_screen else {})}
        if credit and credit not in out.credits:
            out.credits.append(credit)
    return out


def ai_fallback_ok(desc: str) -> bool:
    """May an AI still stand in for this NASA picture? Only for something no camera recorded: not a real person or group, not
    a photographed event, not a document -- those must be real or left out."""
    if _REAL_ONLY.search(desc or ""):
        return False
    return not any(not _NOT_NAMES.search(m.group(0)) for m in _NAME.finditer(desc or ""))


def ai_prompt(desc: str, house: str = "") -> str:
    """The Flow prompt for a stand-in: cinematic, faithful to the real thing, no text (in the Cinema option, What If's house look)."""
    if house:
        return f"{house}{desc}. No text, no logos, no labels."
    return (f"Photorealistic cinematic still for a space documentary: {desc}. Faithful to the real spacecraft, worlds and era; "
            "dramatic natural light from the Sun, deep black space, rich detail, 16:9, no text, no logos, no labels.")


def _is_nasa(rec: Dict[str, Any]) -> bool:
    """A manifest record for NASA material (the NASA image or video library), not a stock provider's."""
    return any("nasa" in str(rec.get(k) or "").lower() for k in ("source", "provider", "asset_type", "author"))


def _credit_from(rec: Dict[str, Any]) -> str:
    """A credit line from a provider's manifest record (author / provider / source page), when it has one."""
    who = rec.get("author") or rec.get("photographer") or rec.get("channel") or ""
    src = rec.get("source") or ""
    url = rec.get("source_url") or rec.get("url") or ""
    if not (who or url):
        return ""
    return " · ".join(x for x in (who, src.replace("_", " "), url) if x)
