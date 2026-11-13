"""War Documentary in the app's style picker: the card, its controls and the render worker. Imported only when the style is picked.

The picker hooks in app.py are small and additive (see the `_war_*` methods there); everything the style does lives here.
Opt-in per session: nothing is saved by this module except what the render itself writes (the video and its .plan.json next to it) and,
for a scenes CSV, the footage its searches fetch (state/war/assets, listed in the Visuals tab; the next Render uses what the tab holds).

Scenes come from (1) a scenes CSV or JSON you choose (JSON: list of {text, start, end, words, footage, footage_meta}; footage paths may be
relative to the project; CSV: what "Copy the CSV prompt" asks for, untimed rows aligned to the voiceover, scene numbers kept), else (2) the voiceover's own transcript, cut into sentences, with the footage the project's scene manifest holds for the same
scene number when there is one. Without footage a scene gets a truthful map/card or no visual, never an unrelated clip.
A CSV run makes no Gemini call: the CSV's prompt column is the search.
"""

from __future__ import annotations

import json
import re
import sys
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

STYLE_NAME = "War Documentary"
TAG = "[WAR DOCUMENTARY]"


def _m(app):
    return sys.modules[type(app).__module__]


# ---- scenes ---------------------------------------------------------------------------------------------------------------
def _breath_after(words: List[Any], i: int) -> bool:
    """A pause of at least 0.25 s after word i (the narrator took a breath)."""
    try:
        return float(words[i + 1][1]) - float(words[i][2]) >= 0.25
    except (ValueError, IndexError, TypeError):
        return False


def sentences_from_words(words: List[Any], total_s: float = 0.0) -> List[Dict[str, Any]]:
    """Scene dicts from word times [(word, start, end), ...]: a scene per sentence (a pause over 1.2 s also ends one); contiguous in time."""
    out: List[Dict[str, Any]] = []
    cur: List[dict] = []

    def flush() -> None:
        if cur:
            out.append({"scene_no": len(out) + 1, "text": " ".join(w["w"] for w in cur), "start": cur[0]["t0"], "end": cur[-1]["t1"],
                        "words": list(cur)})
            cur.clear()

    prev_end = None
    words = list(words or [])
    for idx, item in enumerate(words):
        try:
            w, t0, t1 = str(item[0]), float(item[1]), float(item[2])
        except (TypeError, ValueError, IndexError):
            continue
        if cur and prev_end is not None and t0 - prev_end > 1.2:
            flush()
        cur.append({"w": w, "t0": t0, "t1": t1})
        prev_end = t1
        if re.search(r"[.!?]['\")\]]*$", w) and len(cur) >= 4:
            flush()
        elif len(cur) >= 28 or (len(cur) >= 12 and t1 - cur[0]["t0"] >= 4.0 and _breath_after(words, idx)):
            flush()          # Whisper words carry no punctuation: a whole voiceover was one scene; cut at a breath after ~4 s, at most 28 words
    flush()
    for i, sc in enumerate(out):                    # contiguous: each scene runs to the next one's start; the last to the narration's end
        sc["end"] = out[i + 1]["start"] if i + 1 < len(out) else max(sc["end"], float(total_s or 0.0))
    if out:
        out[0]["start"] = 0.0
    return out


_CSV_TEXT = ("script_segment", "text", "narration", "script", "sentence", "vo_text")
_CSV_NO = ("scene_number", "scene_no", "scene", "no", "#")


def read_scenes_csv(path: str) -> List[dict]:
    """The CSV "Copy the CSV prompt" asks for (scene_number, script_segment, asset_type, prompt) -> scene dicts. Header names are case-insensitive;
    `,` `;` or tab separated; a ```csv fence pasted along with the AI's reply is ignored. start/end (seconds) are optional: all rows or none;
    untimed rows are aligned to the voiceover at Render. The scene number is kept, so footage the Visuals tab fetched for that scene is used."""
    import csv
    import io

    p = Path(path)
    raw = p.read_bytes()
    try:
        content = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        content = raw.decode("cp1252")      # older Excel exports
    lines = [ln for ln in content.splitlines() if ln.strip() and not ln.strip().startswith("```")]
    if not lines:
        raise ValueError(f"{p.name} is empty")
    try:
        delim = csv.Sniffer().sniff(lines[0], delimiters=",;\t").delimiter
    except csv.Error:
        delim = ","
    # only the separator is guessed: a header has no quotes, and the sniffed dialect then read '"He said, ""no."""' as three cells
    reader = csv.DictReader(io.StringIO("\n".join(lines)), delimiter=delim, quotechar='"', doublequote=True, skipinitialspace=False)
    cols = {(k or "").strip().lower(): k for k in (reader.fieldnames or [])}
    text_col = next((cols[a] for a in _CSV_TEXT if a in cols), None)
    if text_col is None:
        raise ValueError(f"{p.name} needs a script_segment (or text) column; its header is: {', '.join(reader.fieldnames or [])}")
    no_col = next((cols[a] for a in _CSV_NO if a in cols), None)
    start_col, end_col = cols.get("start"), cols.get("end")
    out: List[dict] = []
    names = list(reader.fieldnames or [])
    for r in reader:
        extra = r.pop(None, None) or []
        if extra and text_col in names:
            # more cells than the header: an unquoted comma in the narration (render 038, scene 13: "Second, Russians are feeling it. ...")
            # split it, and every later column moved one cell right. The extra cells go back into the narration.
            cells = [r.get(n) or "" for n in names] + [str(x) for x in extra]
            i = names.index(text_col)
            k = len(cells) - len(names)
            cells = cells[:i] + [",".join(cells[i:i + k + 1])] + cells[i + k + 1:]
            r = dict(zip(names, cells))
        text = (r.get(text_col) or "").strip()
        if not text:
            continue
        sc: Dict[str, Any] = {"text": text}
        no = (r.get(no_col) or "").strip() if no_col else ""
        sc["scene_no"] = int(no) if no.isdigit() else len(out) + 1
        for key in ("asset_type", "prompt", "footage", "graphic", "images", "stock", "subject"):
            if key in cols and (r.get(cols[key]) or "").strip():
                sc[key] = r[cols[key]].strip()
        if start_col and end_col and (r.get(start_col) or "").strip() and (r.get(end_col) or "").strip():
            try:
                sc["start"], sc["end"] = float(r[start_col]), float(r[end_col])
            except ValueError:
                raise ValueError(f"{p.name} scene {sc['scene_no']}: start/end must be seconds, got {r[start_col]!r} / {r[end_col]!r}") from None
        out.append(sc)
    if not out:
        raise ValueError(f"{p.name} has no scenes with narration text")
    if any("start" in x for x in out) and not all("start" in x for x in out):
        raise ValueError("start/end are filled on some rows but not all: fill them on every row, or clear them on all rows to align to the voiceover")
    return out


def read_scenes_file(path: str, project_dir: Path) -> List[dict]:
    import json

    p = Path(path)
    if p.suffix.lower() in (".csv", ".tsv", ".txt"):
        return read_scenes_csv(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{p.name} must hold a JSON list of scenes")
    return data


def needs_alignment(scenes: List[dict]) -> bool:
    return bool(scenes) and any("start" not in sc or "end" not in sc for sc in scenes)


# ---- CSV footage (fetched through the app's AssetManager, listed in the Visuals tab) ------------------------------------------
OWNER = "war"      # its CSV footage rows in the Visuals tab (visual_bridge)
FETCH_TYPES = ("stock_video", "youtube_video", "archive_video", "nasa_video", "commons_video", "flow_video")
AI_TYPES = ("flow_video",)
AI_CREDITS_PER_CLIP = 10          # Flow's price for one video clip
DEFAULT_AI_CAP = 15               # AI clips made per video at most, unless the user sets another number on the War page
AI_LOOK = ("cinematic documentary shot, desaturated muted colours, overcast moody light, shallow depth of field, slow camera move, "
           "35mm film grain, no text, no logos, no faces in close-up")
LOCAL_TYPES = ("local", "local_video")
WAR_YT_CLIP_S = 8.0               # War scenes run 5-10 s and are cut into 3-6 s shots: the app-wide 3.5 s YouTube cut ran out mid-scene


def war_manager(manager: Any) -> Any:
    """The app's AssetManager set up for War Documentary: no Gemini (the CSV directs), YouTube cuts long enough for a scene."""
    manager.settings["gemini_enabled"] = False
    try:                                   # archive_video rows: the CSV's own searches, relevant clips only, in parallel (war/archive_fast.py)
        from . import archive_fast

        archive_fast.install(manager)
    except Exception:  # noqa: BLE001 - the shared archive search still works
        pass
    yp = getattr(manager, "youtube_provider", None)
    if yp is not None and float(getattr(yp, "clip_duration", 0.0) or 0.0) < WAR_YT_CLIP_S:
        yp.clip_duration = WAR_YT_CLIP_S
    return manager


def csv_rows(scenes: List[dict]) -> List[Any]:
    """Visuals-tab rows (the app's SceneRow) for the CSV scenes that ask for footage. `none` rows get a map or card from the narration and
    are left out; `local` rows are listed so the user can attach the clip there."""
    from providers.base import SceneRow

    rows = []
    for sc in scenes:
        at = str(sc.get("asset_type") or "").strip().lower()
        if at in FETCH_TYPES or at in LOCAL_TYPES:
            prompt = str(sc.get("prompt") or "").strip()
            if at == "nasa_video" and not prompt:
                prompt = str(sc.get("text") or "")[:80]
            if at == "youtube_video" and prompt and not re.search(r"\b(footage|video|clip|b-?roll)\b", prompt, re.IGNORECASE):
                prompt = " || ".join(q.strip() + " footage" for q in prompt.split("||") if q.strip())   # news footage, not a studio interview
            if at in AI_TYPES and prompt and AI_LOOK not in prompt:
                prompt = f"{prompt.rstrip('. ')}. {AI_LOOK}"         # every AI clip in the same documentary look
            row = SceneRow.from_csv_row({"scene_number": str(sc.get("scene_no")), "script_segment": str(sc.get("text") or ""),
                                         "asset_type": at, "prompt": prompt})
            if at in STOCK_FALLBACK_TYPES:              # nothing real found: archive -> YouTube (HD re-uploads of the same newsreels) -> stock
                fb = list(getattr(row, "fallbacks", None) or [])
                if at == "archive_video":
                    fb.append("youtube_video")
                sq = str(sc.get("stock") or "").strip() or stock_query_for(prompt, str(sc.get("text") or ""))
                if sq:
                    row.stock = sq
                    fb.append("stock_video")
                row.fallbacks = fb
            rows.append(row)
    return rows


STOCK_FALLBACK_TYPES = ("youtube_video", "archive_video", "nasa_video")
_STOCK_STOP = {"the", "a", "an", "of", "in", "on", "at", "and", "or", "to", "for", "by", "with", "from", "into", "as", "is", "was", "that",
               "this", "then", "footage", "archive", "archival", "video", "film", "clip", "newsreel", "historical", "history", "documentary",
               "real", "rare", "original", "hd", "4k", "battle", "war", "operation", "offensive", "counteroffensive", "advance", "invasion",
               "army", "sixth", "front", "eastern", "western", "soviet", "german", "russian", "ukrainian", "american", "british", "red"}
_STOCK_GOOD = re.compile(r"\b(ruins?|smoke|fire|snow|winter|soldiers?|troops|tanks?|aircraft|planes?|river|bridge|factory|city|street|"
                         r"ships?|boats?|explosions?|artillery|trenches?|prisoners?|crowd|refugees?|sniper|rifle|map|missiles?|drones?|"
                         r"railway|train|convoy|trucks?|night|sky|clouds?|fields?|forest|steppe|rubble|buildings?|flag|helmet)\b", re.IGNORECASE)


def stock_query_for(prompt: str, text: str = "") -> str:
    """A plain stock search (2-3 words, no names, no dates) for the subject the CSV searched for: 'Stalingrad 1942 city ruins Volga' ->
    'city ruins'; 'German soldiers Stalingrad winter starvation' -> 'soldiers winter'. Stock sites have no Stalingrad: they have the shot."""
    words: List[str] = []
    for q in [x for x in re.split(r"\|\|", prompt or "") if x.strip()] + [text]:
        for w in re.findall(r"[A-Za-z][A-Za-z'-]+", q):
            lw = w.lower()
            if w[0].isupper() and lw not in ("soldiers", "snow", "winter"):
                continue                                         # a name (Stalingrad, Volga, Luftwaffe): no stock site has it
            if lw in _STOCK_STOP or len(lw) < 4 or lw in words:
                continue
            if _STOCK_GOOD.search(lw):
                words.append(lw)
        if len(words) >= 2:
            break
    return " ".join(words[:3])


def audit_held(images_dir: Path, rows: List[Any], log=lambda m: None) -> List[str]:
    """Clips the Visuals table holds for archive / YouTube rows that cannot be footage of their scene: an empty file, an archive item that
    fails War's relevance or period check (fetched by the old search), or a credit roll / black cut. Their records are marked failed, so
    this Generate fetches them again. A clip the user picked (Change source, local file) is never touched."""
    from asset_manager import AssetManifest
    from . import archive_fast as AF
    from .segments import is_empty_container

    if not Path(images_dir).is_dir():
        return []
    man = AssetManifest(Path(images_dir))
    redo: List[str] = []
    for r in rows:
        if r.asset_type not in ("archive_video", "youtube_video", "video") or r.asset_type == "video":
            continue
        no = str(r.scene_number)
        rec = man.get(no) or {}
        if str(rec.get("status") or "").lower() not in ("complete", "ready", "done") or rec.get("user_override") or rec.get("source") == "manual":
            continue
        path = str(rec.get("local_path") or "")
        why = ""
        if path and Path(path).is_file() and is_empty_container(path):
            why = "empty file"
        elif str(rec.get("provider") or rec.get("source") or "").startswith("archive"):
            queries = AF.csv_queries(r)
            names, plain = AF.key_terms(queries)
            cand = AF.ArchiveCandidate(identifier=str(rec.get("provider_asset_id") or ""), title=str(rec.get("title") or rec.get("video_title") or ""),
                                       description="")
            if rec.get("selection_method") != "war_relevance" and AF.relevance(cand, names, plain, AF.query_years(queries)) <= 0:
                why = f"off-topic archive item ({cand.title[:60]})"
            elif path and Path(path).is_file():
                why = AF.frame_problem(path)
        if why:
            rec = dict(rec, status="failed", error=f"War clip check: {why}")
            man.set(no, rec)
            log(f"scene {no}: {why}: fetching again")
            redo.append(no)
    return redo


def repeated_clips(images_dir: Path, rows: List[Any]) -> List[str]:
    """Scenes whose clip is the same moment of the same video as an earlier scene's (Black Sea film, 2026-11-09: one sea-drone shot cut
    four times from the same seconds, so four scenes showed one picture). A different moment of the same video is fine; the user's own
    picks are never counted."""
    from asset_manager import AssetManifest

    if not Path(images_dir).is_dir():
        return []
    man = AssetManifest(Path(images_dir))
    seen: List[Tuple[str, float, float]] = []
    out: List[str] = []
    for r in sorted(rows, key=lambda x: int(x.scene_number) if str(x.scene_number).isdigit() else 0):
        rec = man.get(str(r.scene_number)) or {}
        vid = str(rec.get("video_id") or rec.get("provider_asset_id") or "")
        if str(rec.get("status") or "").lower() != "complete" or not vid:
            continue
        try:
            a = float(rec.get("clip_start") if rec.get("clip_start") is not None else rec.get("timestamp_start"))
            b = float(rec.get("timestamp_end") if rec.get("timestamp_end") is not None else a + float(rec.get("clip_duration") or 8.0))
        except (TypeError, ValueError):
            continue
        if any(v == vid and a < b0 - 1.0 and b > a0 + 1.0 for v, a0, b0 in seen) and not (rec.get("user_override") or rec.get("source") == "manual"):
            out.append(str(r.scene_number))
        else:
            seen.append((vid, a, b))
    return out


def fix_repeats(images_dir: Path, rows: List[Any], manager: Any, log=lambda m: None, cancel=None) -> List[str]:
    """Each repeated clip gets the asset manager's Alternative (a different video or query, as the Visuals tab's button does), up to two
    rounds. The new clip is still the CSV's own search, so it is not marked as the user's pick."""
    from asset_manager import AssetManifest

    done: List[str] = []
    by_no = {str(r.scene_number): r for r in rows}
    for _round in range(2):
        rep = repeated_clips(images_dir, rows)
        if not rep:
            break
        log(f"Same clip in several scenes: finding another clip for scenes {', '.join(rep)}")
        for no in rep:
            if cancel is not None and cancel():
                return done
            try:
                manager.alternative_scene(by_no[no])
            except Exception as exc:  # noqa: BLE001 - a scene that cannot be replaced keeps its clip
                log(f"scene {no}: no other clip ({exc})")
                continue
            man = AssetManifest(Path(images_dir))
            rec = man.get(no) or {}
            if rec.get("user_override"):
                man.set(no, {**rec, "user_override": False})
            done.append(no)
    return done


def ai_plan(scenes: List[dict], images_dir: Optional[Path], cap: int = DEFAULT_AI_CAP) -> Dict[str, Any]:
    """{make: [scene nos to generate], over: [scene nos past the cap], have: n already made}. Clips already in the Visuals table cost nothing."""
    import visual_bridge

    make: List[str] = []
    over: List[str] = []
    have = 0
    for r in csv_rows(scenes):
        if r.asset_type != "video" or not str(r.scene_number):
            continue
        if images_dir is not None and visual_bridge.records(images_dir, [r]):
            have += 1
        elif len(make) < max(0, int(cap)):
            make.append(str(r.scene_number))
        else:
            over.append(str(r.scene_number))
    return {"make": make, "over": over, "have": have, "credits": len(make) * AI_CREDITS_PER_CLIP}


def _library_dir(library: Any, manager: Any) -> Optional[Path]:
    """The War library folder this fetch asks first, or None (off)."""
    from . import library as LIB

    if library is False:
        return None
    if library not in (None, True):
        return Path(library)
    settings = getattr(manager, "settings", None) if manager is not None else None
    return LIB.root(settings) if LIB.enabled(settings) else None


def _library_report(state_dir: Path) -> Dict[str, Dict[str, Any]]:
    """{scene: {source}} from the last Generate's war_library_report.json ({} when there is none)."""
    from . import library as LIB

    try:
        data = json.loads((Path(state_dir) / LIB.REPORT).read_text(encoding="utf-8"))
        return {str(r["scene"]): {"source": r.get("source")} for r in data.get("rows") or [] if r.get("scene")}
    except (OSError, ValueError, TypeError, AttributeError):
        return {}


def fetch_csv_footage(scenes: List[dict], manager: Any, images_dir: Path, log=lambda m: None, cancel=None,
                      ai_cap: int = DEFAULT_AI_CAP, fetch: bool = True, listed=None, on_start=None, on_done=None,
                      director: Optional[bool] = None, library: Any = None) -> "tuple[List[dict], List[Any]]":
    """(scenes with `footage` set from the Visuals table, the table's rows). The CSV's own searches are fetched for the rows the table does not
    hold yet (a clip already there, or one the user picked, is kept); `none` rows are marked no_footage so no clip is put under their graphic.
    fetch=False (Render after Generate scenes) fetches nothing: the video uses exactly what the Visuals tab holds.

    director (default: the War setting `war_footage_director`, on): YouTube rows go to the War Footage Director (footage_director.py), which
    reads the sentence, searches specifically, rejects off-topic / commentary / repeated / unverifiable clips, checks the frames and captures
    a verified moment; a scene it cannot fill is handed to the War graphics (no_footage + a fitting graphic). Other rows are unchanged.

    library (default: the War setting `war_footage_library`, on, folder from WAR_LIBRARY_DIR / `war_library_dir`; False = off, a path = that
    folder): every footage row asks the reviewed War library first (library.py). Its clips are filed as the rows' finished assets; a row whose
    library subject is used up goes to the War graphics with no search; only rows the library has nothing for are searched live."""
    import visual_bridge
    from asset_manager import AssetManifest
    from . import footage_director as FD
    from . import integration
    from . import library as LIB
    from . import narration_read as N

    if director is None:
        director = FD.enabled(getattr(manager, "settings", None) if manager is not None else None)
    state_dir = Path(images_dir).parent
    rows = csv_rows(scenes)
    lib_plan: Dict[str, Dict[str, Any]] = {}
    lib_dir = _library_dir(library, manager) if fetch else None
    if fetch and lib_dir is not None:
        try:
            lib_plan = LIB.apply(scenes, [r for r in rows if r.asset_type in FETCH_TYPES], Path(images_dir), state_dir, lib=lib_dir, log=log,
                                 settings=getattr(manager, "settings", None))
        except Exception as exc:  # noqa: BLE001 - a library problem leaves every row to the live search
            log(f"War library skipped: {type(exc).__name__}: {exc}")
            lib_plan = {}
    elif not fetch:
        lib_plan = _library_report(state_dir)       # Render after Generate scenes: the rows the library handed to the graphics stay there
    lib_nos = {no for no, d in lib_plan.items() if d.get("source") == "library"}
    gfx_nos = {no for no, d in lib_plan.items() if d.get("source") == "graphics"}
    if fetch:
        try:                    # clips already in the table that are not footage of the scene are fetched again (the user's own picks stay)
            redo = audit_held(images_dir, rows, log)
            if redo:
                log(f"Re-fetching {len(redo)} clip(s) that do not show their scene: scenes {', '.join(redo)}")
        except Exception as exc:  # noqa: BLE001 - an audit never stops Generate scenes
            log(f"clip check skipped: {exc}")
    over = set(ai_plan(scenes, images_dir, ai_cap)["over"])
    if over and fetch:                   # a listing pass (fetch=False) makes nothing: no cap message (Aviation makes its Flow rows itself)
        log(f"AI clip limit {ai_cap} reached: scenes {', '.join(sorted(over, key=lambda x: int(x) if x.isdigit() else 0))} use the map or cards instead")
    todo = []
    directed = [r for r in rows if director and fetch and r.asset_type == "youtube_video" and str(r.scene_number) not in over
                and str(r.scene_number) not in lib_nos | gfx_nos]
    for r in (rows if fetch else []):
        if r in directed or str(r.scene_number) in lib_nos | gfx_nos:
            continue
        if r.asset_type in LOCAL_TYPES or str(r.scene_number) in over or visual_bridge.records(images_dir, [r]):
            continue
        errs = manager.validate_rows([r])
        if errs:
            log(f"scene {r.scene_number}: not searched ({'; '.join(errs)})")
            continue
        todo.append(r)
    if fetch and rows and listed is not None:
        listed(rows)           # every scene is in the Visuals tab before the first download (the fetch takes minutes), then fills in live
    if todo:
        log(f"Fetching footage for {len(todo)} scenes with the CSV's searches…")
        Path(images_dir).mkdir(parents=True, exist_ok=True)
        stop = threading.Event()
        if cancel is not None:
            def watch() -> None:
                while not stop.wait(0.3):
                    if cancel():
                        try:
                            manager.request_cancel()
                            for r_ in todo:               # a run-level stop leaves a download in flight; a scene stop aborts it
                                manager.request_cancel_scene(r_.scene_number)
                        except Exception:
                            pass
                        return

            threading.Thread(target=watch, daemon=True, name="war-asset-cancel").start()
        try:
            manager.resolve_all(todo, on_scene_start=on_start, on_scene_complete=on_done)
            fix_repeats(images_dir, [r for r in rows if r not in directed and str(r.scene_number) not in lib_nos], manager, log, cancel=cancel)
        except Exception as exc:  # noqa: BLE001 - a failed fetch leaves those scenes on maps/cards; the render still runs
            log(f"footage fetch stopped early: {type(exc).__name__}: {exc}")
        finally:
            stop.set()
    if directed:
        log(f"Footage Director: {len(directed)} YouTube scenes (reading the narration, searching, checking frames)…")
        for r in directed:
            if on_start is not None:
                try:
                    on_start(r, "youtube_video")
                except Exception:  # noqa: BLE001 - a Visuals-tab callback never stops the fetch
                    pass
        try:
            FD.run(scenes, directed, Path(images_dir), state_dir, log=log, cancel=cancel or (lambda: False),
                   render_id=Path(images_dir).parent.parent.parent.name)
        except Exception as exc:  # noqa: BLE001 - a director failure leaves those scenes to the War graphics, never stops the render
            log(f"Footage Director stopped early: {type(exc).__name__}: {exc}")
        if listed is not None:
            try:
                listed(rows)           # the Visuals tab re-reads every row: director clips, and the scenes handed to graphics with their reason
            except Exception:  # noqa: BLE001
                pass
    if fetch and lib_dir is not None:
        try:                    # 2026-11-12: a row the live search left empty takes a library clip of its kind before it becomes graphics
            LIB.fallback(scenes, [r for r in rows if r.asset_type in FETCH_TYPES and str(r.scene_number) not in over], Path(images_dir),
                         lib_dir, log=log, settings=getattr(manager, "settings", None))
        except Exception as exc:  # noqa: BLE001 - a fallback problem leaves those rows to the War graphics
            log(f"War library fallback skipped: {type(exc).__name__}: {exc}")
    try:
        lib_nos = set(lib_nos) | LIB.library_nos(Path(images_dir), rows)      # library clips (incl. fallbacks) are never overruled by a graphics decision
    except Exception:  # noqa: BLE001
        pass
    man = AssetManifest(Path(images_dir)) if Path(images_dir).is_dir() else None
    out: List[dict] = []
    got = 0
    for sc in scenes:
        sc = dict(sc)
        at = str(sc.get("asset_type") or "").strip().lower()
        if at == "none":
            sc["no_footage"] = True
        rec = (man.get(str(sc.get("scene_no"))) or {}) if man is not None and (at in FETCH_TYPES or at in LOCAL_TYPES) else {}
        foot, _why = integration.footage_from_record(rec, Path(images_dir)) if rec else (None, "")
        if foot:
            sc["footage"] = foot
            meta = integration.footage_meta_for(rec, sc.get("footage_meta"), scene_file=Path(foot).name)
            if rec.get("user_override") or rec.get("source") == "manual":
                meta["user_supplied"] = True       # picked in the Visuals tab: never swapped for another clip
            elif at in AI_TYPES or rec.get("ai_generated") is True or str(rec.get("ai_generated")).lower() == "true":     # incl. War Flow pictures
                meta["ai_generated"] = True        # labelled "AI-generated illustration", never presented as footage of the event
            meta["csv_pick"] = True                # the CSV's own search, shown in the Visuals tab before Render: only a clear contradiction drops it
            sc["footage_meta"] = meta
            got += 1
        elif str(sc.get("scene_no")) in gfx_nos:
            sc["no_footage"] = True                # the library knows this subject but every clip of it is used: War graphics, no search
            sc.pop("footage", None)
            if not str(sc.get("graphic") or "").strip():
                try:
                    sc["graphic"] = FD.graphic_for(N.read(str(sc.get("text") or "")))
                    sc["graphic_by"] = "war_library"
                except Exception:  # noqa: BLE001 - the War graphics pick their own default
                    pass
        out.append(sc)
    if director:
        decisions = {k: v for k, v in FD.load_decisions(state_dir).items() if str(k).lstrip("0") not in {n.lstrip("0") for n in lib_nos}}
        if decisions:
            out = FD.apply_decisions(out, decisions)
            got = sum(1 for sc in out if sc.get("footage"))
    want = sum(1 for r in rows if r.asset_type not in LOCAL_TYPES)
    if rows:
        log(f"Footage from the CSV: {got} of {len(rows)} scenes have a clip" + (f" ({want} searched)" if want != len(rows) else ""))
    return out, rows


# ---- build / show / hide ---------------------------------------------------------------------------------------------------
def build(app, parent, *, row: int) -> None:
    M = _m(app)
    ctk = M.ctk
    app._war_scenes_var = ctk.StringVar(value="")
    app._war_scenes_var.trace_add("write", lambda *_: getattr(app, "_war_running", False) or app._sync_primary_cta())   # a new CSV: Generate scenes again
    app._war_ai_cap_var = ctk.StringVar(value=str((getattr(app, "_settings", None) or {}).get("war_ai_cap", DEFAULT_AI_CAP)))
    app._war_status_var = ctk.StringVar(value="")
    app._war_cancel = threading.Event()
    app._war_running = getattr(app, "_war_running", False)
    block = ctk.CTkFrame(parent, fg_color=M._CARD, corner_radius=10, border_width=1, border_color=M._BORDER)
    block.grid(row=row, column=0, sticky="ew", pady=(0, 12))
    block.grid_columnconfigure(0, weight=1)
    app._war_block = block
    app._style_card_header(block, "War Documentary",
                           "Narration-driven war and geopolitics documentaries: maps, equipment cards, attributed statements and statistics, each "
                           "labelled confirmed, attributed, disputed, unverified or illustrative. Planned from your voiceover; nothing starts until you press Render.")
    controls = ctk.CTkFrame(block, fg_color="transparent")
    controls.grid(row=1, column=0, sticky="ew", padx=16, pady=(10, 12))
    controls.grid_columnconfigure(0, weight=1)
    app._path_row(0, "Voiceover", app.audio_var, lambda: app._browse_audio(stay=True), parent=controls,
                  placeholder_text="None yet: use Import Voiceover")
    app._path_row(1, "Scenes file", app._war_scenes_var, lambda: browse_scenes(app), parent=controls,
                  placeholder_text="Optional: the scenes CSV (from Copy the CSV prompt) or JSON; otherwise planned from the narration")
    go = ctk.CTkFrame(controls, fg_color="transparent")
    go.grid(row=2, column=0, sticky="ew", pady=(12, 0))
    app._war_render_btn = ctk.CTkButton(go, text="Render War Documentary", width=230, height=40, corner_radius=6, fg_color=M._ACCENT,
                                        hover_color=M._ACCENT_HOV, font=ctk.CTkFont(size=13, weight="bold"), command=lambda: on_render_click(app))
    app._war_render_btn.grid(row=0, column=0, padx=(0, 12))
    cap = ctk.CTkFrame(go, fg_color="transparent")
    cap.grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))
    ctk.CTkLabel(cap, text="Max AI clips per video", font=ctk.CTkFont(size=11)).grid(row=0, column=0, sticky="w")
    ctk.CTkEntry(cap, textvariable=app._war_ai_cap_var, width=52, height=26).grid(row=0, column=1, padx=(8, 8))
    ctk.CTkLabel(cap, text=f"{AI_CREDITS_PER_CLIP} Flow credits each; only for CSV rows marked flow_video. You are asked before any are made.",
                 font=ctk.CTkFont(size=11), text_color=M._MUTED).grid(row=0, column=2, sticky="w")
    ctk.CTkLabel(go, text="Without footage in the scenes, a scene gets a map or card, or no visual.", font=ctk.CTkFont(size=11),
                 text_color=M._MUTED).grid(row=0, column=1, sticky="w")
    ctk.CTkLabel(controls, textvariable=app._war_status_var, font=ctk.CTkFont(size=11), text_color=M._MUTED, anchor="w", wraplength=560,
                 justify="left").grid(row=3, column=0, sticky="ew", pady=(8, 0))
    bar = ctk.CTkFrame(controls, fg_color="transparent")
    bar.grid(row=4, column=0, sticky="ew", pady=(10, 0))
    bar.grid_columnconfigure(1, weight=1)
    M._make_button(bar, "Copy the CSV prompt", lambda: copy_csv_prompt(app), size="lg", width=150).grid(row=0, column=0, sticky="w")
    ctk.CTkLabel(bar, text="Paste it into any AI, then choose the CSV it writes as the Scenes file.", font=ctk.CTkFont(size=11), text_color=M._MUTED,
                 anchor="w").grid(row=0, column=1, sticky="w", padx=(10, 0))
    app._build_csv_prompt_script_box(bar, row=1, columnspan=2)
    fl = ctk.CTkFrame(controls, fg_color="transparent")             # front-line data: optional, dated, sourced control areas for the maps
    fl.grid(row=5, column=0, sticky="ew", pady=(10, 0))
    fl.grid_columnconfigure(1, weight=1)
    app._war_frontline_var = ctk.StringVar(value=frontline_summary())
    M._make_button(fl, "Add front-line data", lambda: add_frontline(app), size="lg", width=150).grid(row=0, column=0, sticky="w")
    ctk.CTkLabel(fl, textvariable=app._war_frontline_var, font=ctk.CTkFont(size=11), text_color=M._MUTED, anchor="w", wraplength=520,
                 justify="left").grid(row=0, column=1, sticky="w", padx=(10, 0))
    block.grid_remove()


def frontline_summary() -> str:
    """One line on the front-line data the maps can use (the per-user folder plus the app's own, which ships empty)."""
    try:
        from . import frontline as FL

        good, bad = FL.load_library()
    except Exception as exc:  # noqa: BLE001 - a summary line never stops the panel
        return f"Front-line data could not be read: {exc}"
    if not good:
        txt = ("No front-line data yet: maps show what the narration says changed hands (illustrative areas). "
               "Add a dated, sourced GeoJSON to also draw assessed control areas and front-line history.")
    else:
        txt = (f"Front-line data: {len(good)} snapshot(s), {good[0]['as_of']} to {good[-1]['as_of']} "
               f"({', '.join(sorted({g['source'][:30] for g in good}))}). Maps use it when the narration gives a date.")
    if bad:
        txt += f" {len(bad)} file(s) skipped ({bad[0][1]})."
    return txt


def frontline_dir() -> Path:
    from . import frontline as FL

    return FL.default_dirs()[-1]


def import_frontline_file(path: str, *, as_of: str = "", source: str = "", licence: str = "", status: str = "assessed", side: str = "russia") -> Path:
    """A snapshot file (war.frontline/1 JSON) is copied as it is; a GeoJSON is converted with the date, source and licence given here.
    Raises ValueError with the reason when something required is missing."""
    import json as _json
    import shutil

    from . import frontline as FL

    src = Path(path)
    dest_dir = frontline_dir()
    dest_dir.mkdir(parents=True, exist_ok=True)
    try:
        raw = _json.loads(src.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"{src.name} is not readable JSON: {exc}") from None
    if isinstance(raw, dict) and raw.get("areas") is not None:
        ok, why = FL.validate(raw)
        if not ok:
            raise ValueError(f"{src.name}: {why}")
        dest = dest_dir / src.name
        shutil.copyfile(src, dest)
        return dest
    return FL.import_geojson(src, dest_dir, as_of=as_of.strip(), source=source.strip(), licence=licence.strip(), status=status, side=side)


def add_frontline(app) -> None:
    """Choose a GeoJSON (or a snapshot file), say its date, source and licence, and it joins the maps' front-line data (per user)."""
    M = _m(app)
    path = M.filedialog.askopenfilename(title="Choose front-line data (GeoJSON or snapshot JSON)",
                                        filetypes=[("GeoJSON or JSON", "*.geojson *.json"), ("All files", "*.*")])
    if not path:
        return
    ask = lambda title, text: (M.ctk.CTkInputDialog(title=title, text=text).get_input() or "").strip()   # noqa: E731
    meta = {}
    try:
        import json as _json

        is_snapshot = isinstance(_json.loads(Path(path).read_text(encoding="utf-8")), dict) and "areas" in _json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        is_snapshot = False
    if not is_snapshot:
        meta["as_of"] = ask("Front-line data", "Date this map shows (YYYY-MM-DD):")
        if not meta["as_of"]:
            return
        meta["source"] = ask("Front-line data", "Who made it (source shown on screen and in the credits):")
        if not meta["source"]:
            return
        meta["licence"] = ask("Front-line data", "Licence or permission (e.g. CC BY-SA 4.0, OGL v3.0, permission email):")
        if not meta["licence"]:
            return
    try:
        dest = import_frontline_file(path, **meta)
        msg = f"Added {dest.name}. " + frontline_summary()
    except Exception as exc:  # noqa: BLE001 - shown to the user
        msg = f"Front-line data not added: {exc}"
    var = getattr(app, "_war_frontline_var", None)
    if var is not None:
        var.set(msg)


def csv_prompt_text(script: str = "") -> str:
    """The War Documentary CSV prompt (cinematic_explainer/war/data/war_csv_prompt.txt) with the script in place of its placeholder."""
    text = (Path(__file__).resolve().parent / "data" / "war_csv_prompt.txt").read_text(encoding="utf-8")
    script = (script or "").strip()
    return text.replace("<<<PASTE THE SCRIPT HERE>>>", script) if script else text


def copy_csv_prompt(app) -> None:
    M = _m(app)
    for box in getattr(app, "_csv_prompt_script_boxes", []):
        try:
            if box.get("1.0", "end").strip() != getattr(box, "_csv_synced", None):
                app._on_csv_prompt_script_edited(box)   # typed in but not yet left: the click must not lose it
                break
        except Exception:
            pass
    script = app._main_script_text()
    try:
        text = csv_prompt_text(script)
    except OSError as exc:
        M.messagebox.showerror("Copy the CSV prompt", f"The prompt file could not be read: {exc}")
        return
    app.clipboard_clear()
    app.clipboard_append(text)
    app._war_status_var.set("War Documentary prompt copied with your script. Paste it into any AI to get the footage CSV." if script else
                            "War Documentary prompt copied. Paste it into any AI and replace its last line with your script.")


def _pick_file(app) -> Optional[Path]:
    ws = getattr(app, "_workspace", None)
    return Path(ws.root) / "state" / "war" / "scenes_file.txt" if ws is not None and getattr(ws, "root", None) else None


def remember_scenes(app, path: str) -> None:
    """The project remembers its scenes file (only the choice: nothing is planned or fetched until Generate)."""
    f = _pick_file(app)
    if f is None:
        return
    try:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(path, encoding="utf-8")
    except OSError:
        pass


def recall_scenes(app) -> str:
    """The scenes file this project used last, when it still exists (the app reopened: the field was empty and Render ran without the CSV)."""
    f = _pick_file(app)
    try:
        path = f.read_text(encoding="utf-8").strip() if f is not None and f.is_file() else ""
    except OSError:
        return ""
    return path if path and Path(path).is_file() else ""


def browse_scenes(app) -> None:
    M = _m(app)
    path = M.filedialog.askopenfilename(title="Choose the scenes file", filetypes=[("Scenes CSV or JSON", "*.csv *.json"), ("All files", "*.*")])
    if path:
        app._war_scenes_var.set(path)
        remember_scenes(app, path)


def activate(app) -> None:
    if getattr(app, "_war_running", False):
        return
    app._war_block.grid()
    app._war_status_var.set("")
    if not app._war_scenes_var.get().strip():
        last = recall_scenes(app)
        if last:
            app._war_scenes_var.set(last)
    import visual_bridge

    visual_bridge.restore(app, OWNER)      # the CSV footage of the last Generate scenes, back in the Visuals tab


def _is_csv(path: str) -> bool:
    return path.lower().endswith((".csv", ".tsv", ".txt"))


def _inputs_key(app) -> tuple:
    """What Generate scenes fetched for: a different scenes file or voiceover needs Generate scenes again before Render."""
    return (app._war_scenes_var.get().strip(), str(app._current_voiceover_path() or ""))


def needs_scenes(app) -> bool:
    """A scenes CSV asks for footage: Generate scenes puts it in the Visuals tab first, then Render uses what the tab holds."""
    return _is_csv(app._war_scenes_var.get().strip()) and getattr(app, "_war_ready_key", None) != _inputs_key(app)


def deactivate(app) -> None:
    block = getattr(app, "_war_block", None)
    if block is not None:
        block.grid_remove()
    try:
        import visual_bridge

        visual_bridge.clear(app, OWNER)
    except Exception:
        pass


# ---- primary button ---------------------------------------------------------------------------------------------------------
def sync_cta(app) -> None:
    if getattr(app, "_war_running", False):
        app._cta_action = "war_cancel"
        app.stage_var.set("GENERATING")
        if app._war_cancel.is_set():
            app.hint_var.set("Stopping…")
            app._set_generate_btn(state="disabled", text="Stopping…")
        else:
            app.hint_var.set("Rendering — click Stop to cancel.")
            app._set_generate_btn(state="normal", text="Stop")
        return
    if app._workspace is None:
        app._cta_action = "picker"
        app.stage_var.set("SETUP")
        app.hint_var.set("Choose a project to get started.")
        app._set_generate_btn(state="normal", text="Choose project")
        return
    if app._current_voiceover_path() is None:
        app._cta_action = "import_audio"
        app.stage_var.set("PLAN")
        app.hint_var.set("Select or import a voiceover to continue.")
        app._set_generate_btn(state="normal", text="Import Voiceover")
        return
    app._cta_action = "war_render"
    if needs_scenes(app):
        app.stage_var.set("PLAN")
        app.hint_var.set("Click Generate scenes: the CSV's footage is fetched into the Visuals tab for you to check before rendering.")
        _set_page_btn(app, "Generate scenes")
        app._set_generate_btn(state="normal", text="Generate scenes")
        return
    app.stage_var.set("RENDER")
    if _is_csv(app._war_scenes_var.get().strip()):
        app.hint_var.set("The clips are in the Visuals tab: change any there (Retry, Change source, Local clip), then click Render War Documentary.")
    else:
        app.hint_var.set("Click Render War Documentary: the visuals are planned from the narration, then rendered.")
    _set_page_btn(app, "Render War Documentary")
    app._set_generate_btn(state="normal", text="Render War Documentary")


def _set_page_btn(app, text: str) -> None:
    try:
        app._war_render_btn.configure(text=text)
    except Exception:
        pass


def cta(app, action: str) -> None:
    if action == "war_cancel":
        cancel(app)
    else:
        on_render_click(app)


def cancel(app) -> None:
    if not getattr(app, "_war_running", False) or app._war_cancel.is_set():
        return
    app._war_cancel.set()
    app._append_log(f"{TAG} Stop requested: finishing the current piece, then stopping.\n")
    app._sync_primary_cta()


# ---- render ---------------------------------------------------------------------------------------------------------------
def on_render_click(app) -> None:
    M = _m(app)
    if getattr(app, "_war_running", False):
        return
    ws = app._workspace
    if ws is None:
        M.messagebox.showerror("Cannot start", "Create or choose a project first.")
        return
    voiceover = app._current_voiceover_path()
    if voiceover is None:
        M.messagebox.showerror("Cannot start", "Select or import a voiceover first.")
        return
    scenes_path = app._war_scenes_var.get().strip()
    if scenes_path and not Path(scenes_path).is_file():
        M.messagebox.showerror("Cannot start", f"The scenes file was not found:\n{scenes_path}")
        return
    out_path = ws.next_final_path()
    app.output_var.set(str(out_path))
    project_dir = Path(ws.root)
    model = app.model_var.get().strip() or "base"
    state_dir = getattr(ws, "state_dir", None)
    manager = None
    images_dir = None
    ai_cap = DEFAULT_AI_CAP
    media_only = needs_scenes(app)       # first Generate scenes (the CSV's footage into the Visuals tab), then Render from what the tab holds
    inputs = _inputs_key(app)
    if _is_csv(scenes_path):
        import visual_bridge

        images_dir = visual_bridge.folder(OWNER, ws)
    if media_only:                       # the CSV's searches are fetched through the app's own providers
        try:
            ai_cap = max(0, int(str(app._war_ai_cap_var.get()).strip() or DEFAULT_AI_CAP))
        except ValueError:
            M.messagebox.showerror("Cannot start", "Max AI clips must be a whole number (0 for none).")
            return
        try:
            app._settings["war_ai_cap"] = ai_cap
            M.save_settings(app._settings)
        except Exception:
            pass
        try:
            plan_ai = ai_plan(read_scenes_file(scenes_path, project_dir), images_dir, ai_cap)
        except Exception as exc:  # noqa: BLE001
            M.messagebox.showerror("Cannot start", f"The scenes file could not be read:\n{exc}")
            return
        if plan_ai["make"]:                # Flow credits are spent only after the user says yes, with the count and cost in front of them
            msg = (f"This CSV asks for {len(plan_ai['make']) + len(plan_ai['over'])} AI clips"
                   + (f" ({plan_ai['have']} already made, free)" if plan_ai["have"] else "") + ".\n\n"
                   f"Make {len(plan_ai['make'])} now = {plan_ai['credits']} Flow credits."
                   + (f"\n{len(plan_ai['over'])} more are over your limit of {ai_cap} and will use the map or cards." if plan_ai["over"] else "")
                   + "\n\nYes: make them.  No: continue without new AI clips.")
            if not M.messagebox.askyesno("AI footage", msg):
                ai_cap = 0
        try:
            manager = war_manager(app._build_asset_manager(images_dir, []))      # built here: it reads Tk variables
        except Exception as exc:  # noqa: BLE001
            M.messagebox.showerror("Cannot start", f"The app's asset sources could not be set up:\n{exc}")
            return
    app._war_cancel.clear()
    app._war_running = True
    app._war_status_var.set("Fetching the footage for the Visuals tab…" if media_only else "Starting…")
    run = None if media_only else app._track_generation_start("war")      # the Export page follows the render (not Generate scenes)
    app._sync_primary_cta()

    def log(msg: str) -> None:
        app.after(0, lambda: app._append_log(f"{TAG} {msg}\n"))

    def progress(k: float, msg: str) -> None:
        app.after(0, lambda: (app._war_status_var.set(f"{int(k * 100)}%  {msg}"), run is not None and app._export_progress(k, msg)))

    def return_rows(rows: List[Any]) -> None:
        def done() -> None:      # Generate scenes ends in the Visuals tab; nothing is rendered and the Export page is not touched
            import visual_bridge

            app._war_running = False
            visual_bridge.fill(app, OWNER, rows)
            app._war_ready_key = inputs
            ok = len(visual_bridge.records(images_dir, rows))
            msg = (f"Scenes ready: {ok} of {len(rows)} clips found. Check them in the Visuals tab, then click Render War Documentary."
                   if rows else "Scenes ready (no footage scenes to check). Click Render War Documentary.")
            app._war_status_var.set(msg)
            app._append_log(f"{TAG} {msg}\n")
            if rows:
                try:
                    app._goto_workflow_view("visual_plan")
                except Exception:
                    pass
            app._sync_primary_cta()

        app.after(0, done)

    def worker() -> None:
        from . import integration, segments

        result: Optional[dict] = None
        error = ""
        rows: List[Any] = []
        try:
            scenes = read_scenes_file(scenes_path, project_dir) if scenes_path else None
            if scenes is None or needs_alignment(scenes):
                log("Reading the narration's word times…")
                words = app._pakmap_get_words(voiceover, model, state_dir, log)
                try:
                    from pakmap.app_integration import voiceover_duration

                    total = float(voiceover_duration(voiceover) or 0.0)
                except Exception:
                    total = 0.0
            if scenes is not None and needs_alignment(scenes):     # untimed CSV rows (what "Copy the CSV prompt" asks for): the voiceover's real times
                from health_cinema import scenes_csv

                scenes, frac = scenes_csv.align_to_words(scenes, words, total)
                log(f"{len(scenes)} scenes from the CSV, aligned to the voiceover: {scenes_csv.match_note(frac)}")
            if scenes is not None and images_dir is not None:
                if media_only:
                    progress(0.0, "fetching the CSV's footage")
                def listed(rows_: List[Any]) -> None:
                    import visual_bridge

                    app.after(0, lambda: visual_bridge.fill(app, OWNER, rows_))

                def on_start(scene: Any, source: Any) -> None:
                    app._ui_queue.put(("scene_busy", (scene.scene_number, M._scene_busy_kind(source))))

                def on_done(scene: Any, result: Any) -> None:
                    app._ui_queue.put(("scene_asset", (scene.scene_number, result)))

                live = media_only and hasattr(app, "_ui_queue")
                app._style_fetch_manager = manager       # Change source / Stop on a Visuals row reaches the scene this fetch is downloading
                try:
                    scenes, rows = fetch_csv_footage(scenes, manager, images_dir, log, cancel=app._war_cancel.is_set, ai_cap=ai_cap, fetch=media_only,
                                                     listed=listed if live else None, on_start=on_start if live else None, on_done=on_done if live else None)
                finally:
                    app._style_fetch_manager = None
                if app._war_cancel.is_set():
                    raise segments.RenderCancelled()
                if media_only:
                    try:            # where the video might sag, before anything is rendered (war/engagement.py)
                        rep = integration.preview_engagement(str(project_dir), scenes)
                        if rep:
                            (Path(project_dir) / "state").mkdir(parents=True, exist_ok=True)
                            (Path(project_dir) / "state" / "war_engagement.txt").write_text(rep, encoding="utf-8")
                            for ln in rep.splitlines()[:12]:
                                log(ln)
                    except Exception as exc:  # noqa: BLE001 - a report never stops Generate scenes
                        log(f"engagement check skipped: {exc}")
                    return_rows(rows)
                    return
            elif scenes is None:
                scenes = sentences_from_words(words, total)
                if not scenes:
                    raise RuntimeError("the narration has no words to plan from")
                log(f"{len(scenes)} scenes planned from the narration")
            result = integration.run_war_documentary(str(project_dir), scenes, str(voiceover), str(out_path), cancel_check=app._war_cancel.is_set,
                                                     progress_cb=progress)
        except segments.RenderCancelled:
            error = "Stopped."
        except segments.MissingInput as exc:
            error = f"A footage file is missing: {exc}"
        except Exception as exc:  # noqa: BLE001 - shown to the user, never a silent failure
            error = f"{type(exc).__name__}: {exc}"

        def finish() -> None:
            app._war_running = False
            if rows:
                import visual_bridge

                visual_bridge.fill(app, OWNER, rows)      # check or change the clips there; the next Render uses what the tab holds
            if run is not None:
                from export_state import run_outcome

                done = run_outcome(error, out_path if result else None)
                app._track_generation_end(run, done, output_path=out_path if done == "completed" else None, validated=done == "completed", message=error)
            if error:
                app._war_status_var.set(error)
                app._append_log(f"{TAG} {error}\n")
            elif result:
                n = len(result.get("plan_log") or [])
                msg = f"Done: {out_path.name} ({n} scenes planned"
                rr = result.get("render", {}) or {}
                if rr.get("fallback"):
                    msg += "; used the fallback renderer"
                if rr.get("retried_pieces"):
                    msg += f"; {len(rr['retried_pieces'])} piece(s) re-rendered plainly"
                msg += ")"
                if rr.get("fallback_reason"):           # why the main renderer stopped, so it can be fixed (it is also in the plan report)
                    app._append_log(f"{TAG} fallback reason: {str(rr['fallback_reason'])[-300:]}\n")
                app._war_status_var.set(msg)
                app._append_log(f"{TAG} {msg}; plan report: {result.get('report_path')}\n")
                gfx = result.get("graphics") or {}
                app._append_log(f"{TAG} Graphics in the video: {sum(gfx.values())}"
                                + (f" ({', '.join(f'{k} x{v}' for k, v in list(gfx.items())[:12])})" if gfx else " (none: send this log and the plan report)") + "\n")
                for line in (result.get("credits") or [])[:20]:
                    app._append_log(f"{TAG} credit: {line}\n")
            app._sync_primary_cta()

        app.after(0, finish)

    threading.Thread(target=worker, name="war-documentary-render", daemon=True).start()
