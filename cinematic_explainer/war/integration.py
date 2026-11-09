"""War Documentary: the entry point the app (or a script) calls. Complete and callable without any change to existing code.

    run_war_documentary(project_dir, scenes, voiceover_path, out_path, cancel_check, progress_cb) -> result dict

scenes: a list of scene dicts {text, start, end, words (optional), footage (path or None), footage_meta (optional), scene_no}; or None, in which
case <project_dir>/war_scenes.json is read (a JSON list of the same dicts; footage may be relative to the project) and, for any scene without
footage, the project's own scene manifest (Images/.asset_manifest.json, written by the app's providers) supplies local_path and the
provider's metadata by scene number.

Optional metadata is never required: a missing field is "unknown", never an error.

HOW THE APP OFFERS IT (not done here: needs a user-interface section, more than one additive line)
------------------------------------------------------------------------------------------------
app.py is NOT in test_fixtures/weather_protected.json or enoch_template_protected.json (checked), so it may be edited, but a new style is not a
one-line hook: the picker needs, in the same pattern as "What If" (whatif/app_section.py), (1) a name in STYLE_CHOICES / STYLE_BLURBS /
STYLE_CARDS (see style_entry() below for the exact strings), (2) an `_active_style()` mapping, (3) a branch in `_on_style_pick` that activates a
section with a "Render War Documentary" button, (4) a running flag in the "Generation running" guard, and (5) a button handler that calls
run_war_documentary in a worker thread with cancel_check and progress_cb. Until then the style is usable from this module, from
`python -m cinematic_explainer.war.integration --scenes scenes.json --voiceover vo.wav --out out.mp4`, and from the Python console.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

log = logging.getLogger("cinematic_explainer.war.integration")

STYLE_NAME = "War Documentary"


def style_entry() -> Dict[str, Any]:
    """The strings the style picker needs, so the eventual app hook is a copy-paste (nothing here touches the picker)."""
    return {
        "name": STYLE_NAME,
        "blurb": "Narration-driven war and geopolitics documentaries: maps, equipment cards, attributed statements, statistics, sources.",
        "card": ("◈", "Maps, equipment, statements, statistics and sources", "Script + voiceover with timings", "Conflict and geopolitics analysis"),
        "settings_key": "war_documentary",          # off by default; the style is opt-in per project
    }


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _manifest_for(project_dir: Path) -> Dict[str, dict]:
    """The project's own asset manifest (Images/.asset_manifest.json), read with the app's AssetManifest when it can be imported (read only:
    nothing is written), else as plain JSON. Keys are normalised like the app does ('1' and '001' are one scene)."""
    images = project_dir / "Images"
    try:
        from asset_manager import AssetManifest   # the app's reader; importing it must never stop a render

        m = AssetManifest(images)
        return {k: dict(v) for k, v in m.all().items() if isinstance(v, dict)}
    except Exception:
        pass
    try:
        data = _read_json(images / ".asset_manifest.json")
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _record_for(manifest: Dict[str, dict], no: str) -> dict:
    keys = [str(no)]
    try:
        keys.append(f"{int(str(no).strip()):03d}")
    except ValueError:
        pass
    for k in keys:
        if isinstance(manifest.get(k), dict):
            return manifest[k]
    return {}


_USABLE_STATUS = ("", "complete", "completed", "ok", "done")
_VIDEO_SUFFIX = (".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi")


def footage_from_record(rec: dict, project_dir: Path) -> "tuple[Optional[str], str]":
    """(absolute path or None, reason). A failed/skipped/pending record or a missing file gives no footage: the planner then uses a labelled
    illustrative graphic, never a placeholder clip. A still image is played as a slow push-in clip made from it."""
    if not rec:
        return None, "no asset record"
    st = str(rec.get("status") or "").strip().lower()
    if st not in _USABLE_STATUS:
        return None, f"asset record status is '{st}'"
    lp = rec.get("local_path")
    if not lp:
        return None, "record has no local file"
    p = Path(lp)
    if not p.is_absolute():
        p = project_dir / "Images" / p if (project_dir / "Images" / p).is_file() else project_dir / p
    if not p.is_file():
        return None, "file is missing"
    if p.suffix.lower() in _STILL_SUFFIX:
        clip = still_to_clip(p)      # a picture picked in the Visuals tab (Change source -> stock image) plays as a slow push-in, never dropped
        return (clip, "") if clip else (None, "still image could not be turned into a clip")
    if p.suffix.lower() not in _VIDEO_SUFFIX:
        return None, f"unsupported file type {p.suffix}"
    from .segments import is_empty_container

    if is_empty_container(str(p)):   # an empty MP4 shell (a cut asked past the source's end): no picture, so no footage
        return None, "downloaded file has no picture"
    return str(p), ""


_STILL_SUFFIX = (".jpg", ".jpeg", ".png", ".webp", ".bmp")
STILL_CLIP_S = 12.0


def still_to_clip(path: Path, seconds: float = STILL_CLIP_S) -> Optional[str]:
    """`<image>.war.mp4` beside the image: a 1080p slow push-in (no still screens), made once and reused while the image is unchanged."""
    import subprocess

    path = Path(path)
    out = path.with_name(path.stem + ".war.mp4")
    try:
        if out.is_file() and out.stat().st_size > 0 and out.stat().st_mtime >= path.stat().st_mtime:
            return str(out)
        frames = int(round(seconds * 25))
        vf = ("scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,"
              f"zoompan=z='1+0.08*on/{frames}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s=1920x1080:fps=25,format=yuv420p")
        tmp = out.with_name(out.stem + ".part.mp4")
        r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(path), "-vf", vf, "-frames:v", str(frames), "-c:v", "libx264",
                            "-preset", "veryfast", "-crf", "18", "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
                            "-an", str(tmp)], capture_output=True, text=True, timeout=180)
        if r.returncode != 0 or not tmp.is_file() or tmp.stat().st_size == 0:
            log.warning("still %s -> clip failed: %s", path.name, (r.stderr or "")[-300:])
            tmp.unlink(missing_ok=True)
            return None
        tmp.replace(out)
        return str(out)
    except Exception as exc:  # noqa: BLE001 - a bad picture leaves that scene on a graphic, never stops the render
        log.warning("still %s -> clip failed: %s", path.name, exc)
        return None


def footage_meta_for(rec: dict, explicit: Optional[dict] = None, *, scene_file: str = "") -> dict:
    """Provenance-honest footage_meta for the planner: the record's own fields (provider, provider_asset_id, author, source_url, license,
    video_title, channel, width, height, duration), classification flags, and never a verification claim (always 'unverified')."""
    from . import provenance as P

    meta: Dict[str, Any] = {}
    keep = ("source", "provider", "provider_asset_id", "author", "source_url", "license", "video_title", "channel", "width", "height", "duration",
            "type", "local_path", "stock_query", "query", "title", "description", "tags", "keywords", "location", "country", "event")
    for k in keep:
        if rec.get(k) not in (None, ""):
            meta[k] = rec[k]
    if rec:
        c = P.classify_record(rec)
    else:   # a file named by the scene itself, with no asset record
        c = {"kind": "user", "generic": False, "user_supplied": True, "rights": "user-supplied file; rights not recorded", "rights_known": False,
             "licence": P.UNKNOWN, "source_chip": False}
    if c["kind"] == "generated":
        meta["ai_generated"] = True                     # a generated clip is an illustration: footage_match classes it ai_generated
    meta.update({"kind": c["kind"], "generic": c["generic"], "user_supplied": c["user_supplied"], "rights": c["rights"],
                 "rights_known": c["rights_known"], "source_chip": c["source_chip"], "verification": "unverified"})
    if scene_file:
        meta["file"] = scene_file
    meta.update(explicit or {})                       # what the caller states explicitly wins (e.g. a verification the user has done)
    return meta


def _clip_pool(manifest: Dict[str, dict], project_dir: Path) -> List[dict]:
    """Every usable video record of the project's manifest as a {path, meta} candidate (same records the app's providers wrote; nothing new)."""
    pool: List[dict] = []
    for _k, rec in manifest.items():
        if not isinstance(rec, dict):
            continue
        p, _why = footage_from_record(rec, project_dir)
        if p:
            pool.append({"path": p, "meta": footage_meta_for(rec, None, scene_file=Path(p).name)})
    return pool


_SMALL_MARKS = ("kicker", "status_chip", "shot_headline", "kit_badge", "kit_grain", "kit_ribbon", "kit_stamp")


def graphics_count(layers: Any) -> Dict[str, int]:
    """{graphic kind: how many} for the render log, small marks (chips, headlines, grain) left out, most used first."""
    c: Dict[str, int] = {}
    for ly in layers or []:
        k = str(getattr(ly, "kind", "") or "")
        if k and k not in _SMALL_MARKS:
            c[k] = c.get(k, 0) + 1
    return dict(sorted(c.items(), key=lambda kv: (-kv[1], kv[0])))


GRAPHIC_NAMES = {"tac_map": "Tactical / political map", "tac_route": "Route map", "map_card": "Situation map", "map_inset": "Corner locator map",
                 "kit_field": "Background field", "kit_title": "Title card", "kit_datecard": "Date card", "kit_quote": "Quote card", "kit_kinetic": "Kinetic words",
                 "kit_keywords": "Keywords", "kit_dossier": "Dossier file", "kit_radar": "Radar sweep", "kit_chapter": "Chapter label",
                 "kit_bignum": "Big number", "kit_versus": "Versus comparison", "kit_chart": "Animated chart", "kit_icons": "Icon explainer",
                 "kit_sticker": "Pictogram sticker", "kit_recap": "Numbered recap", "kit_chips": "Note chips", "kit_scale": "Scale row",
                 "kit_speaker": "Name / role card", "kit_stamp": "CLAIMED / UNVERIFIED stamp", "kit_tag": "Hook tag", "kit_ribbon": "Section ribbon",
                 "kit_flag": "Waving flag", "kit_flyover": "Drone / missile fly-over", "lay_document": "Document highlight",
                 "lay_satellite": "Satellite before/after", "lay_figure_hero": "Person hero", "lay_figure_pair": "Two people", "lay_equipment_hero": "Equipment hero",
                 "lay_equipment_compare": "Equipment compare", "lay_stat_split": "Stat split", "lay_timeline": "Timeline", "lay_claim": "Claim panel",
                 "lay_inset": "Inset caption", "lay_logistics": "Supply chain", "figure_card": "Portrait card", "equipment_card": "Equipment card",
                 "institution_card": "Institution card", "evidence_card": "Source card", "stat_number": "Number card", "stat_compare": "Compare bars",
                 "timeline": "Timeline (classic)", "split_compare": "Split compare", "bc_source": "Source tag", "bc_label": "Keyword label",
                 "bc_caption": "Caption box", "bc_bigword": "Big word over footage", "lay_speaker_quote": "Speaker quote card",
                 "fx_flash": "Light flash", "fx_roadmap": "Roadmap words"}
_INDEX_SKIP = {"kit_grain", "kit_badge", "status_chip", "kicker", "source_label", "shot_headline"}


def graphics_index(layers: List[Any]) -> str:
    """'0:12  Date card (kit_datecard)  3.6 s' per graphic in time order, then the totals: where to find each graphic in the video."""
    lines, used = [], {}
    for ly in sorted(layers, key=lambda l: l.start):
        if ly.kind in _INDEX_SKIP:
            continue
        m, s_ = divmod(int(ly.start), 60)
        extra = ""
        p = ly.params or {}
        if ly.kind == "tac_map":
            bits = [x for x, on in (("capture", p.get("control")), ("front line", p.get("frontline")), ("route", p.get("routes"))) if on]
            extra = f"  [{', '.join(bits)}]" if bits else ""
        lines.append(f"{m}:{s_:02d}  {GRAPHIC_NAMES.get(ly.kind, ly.kind)} ({ly.kind})  {ly.end - ly.start:.1f} s{extra}")
        used[ly.kind] = used.get(ly.kind, 0) + 1
    tot = [f"{GRAPHIC_NAMES.get(k, k)}: {n}" for k, n in sorted(used.items(), key=lambda kv: -kv[1])]
    return "GRAPHICS IN THIS VIDEO (time, graphic, seconds)\n" + "\n".join(lines) + f"\n\n{len(used)} kinds used\n" + "\n".join(tot) + "\n"


def preview_engagement(project_dir: str, scenes: List[dict], config: Optional[dict] = None) -> str:
    """The engagement check for scenes that are ready (after Generate scenes), without rendering: the readable report."""
    from . import engagement as _eng, planner

    plan = planner.plan(load_scenes(Path(project_dir), scenes, config=config), config=config)
    rep_e = ((plan.stats or {}).get("direction") or {}).get("engagement")
    return _eng.text(rep_e) if rep_e else ""


def load_scenes(project_dir: Path, scenes: Optional[List[dict]] = None, *, match: bool = True, config: Optional[dict] = None,
                discovery_provider: Any = None) -> List[dict]:
    """Scene dicts with footage resolved from the explicit list, war_scenes.json and the project's asset manifest (same scene numbering as the
    app). Footage paths are made absolute; a missing, failed or still-image asset gives footage None (a labelled graphic is used instead)."""
    project_dir = Path(project_dir)
    if scenes is None:
        src = project_dir / "war_scenes.json"
        if not src.is_file():
            raise FileNotFoundError(f"no scenes given and {src} does not exist")
        scenes = _read_json(src)
    manifest = _manifest_for(project_dir)
    out: List[dict] = []
    for i, sc in enumerate(scenes):
        sc = dict(sc)
        no = str(sc.get("scene_no") or sc.get("scene_number") or i + 1)
        rec = _record_for(manifest, no)
        explicit = sc.get("footage")
        why = ""
        if sc.get("no_footage"):            # the scenes CSV asks for no footage here (asset_type none): its map or card is not hidden under a clip
            foot, why, use_rec = None, "the scenes CSV asks for no footage here", {}
            sc["footage_candidates"] = []
        elif explicit:
            p = Path(explicit)
            if not p.is_absolute():
                p = project_dir / p
            foot = str(p) if p.is_file() else None
            if foot is None:
                why = "file is missing"
                log.warning("scene %s: footage %s not found; the planner will use a truthful fallback", no, explicit)
            same = bool(rec.get("local_path")) and foot and Path(str(rec["local_path"])).name == Path(foot).name
            use_rec = rec if same else {}
        else:
            foot, why = footage_from_record(rec, project_dir)
            use_rec = rec if foot else {}
            if foot is None and rec and why:
                log.info("scene %s: no footage from the asset record (%s)", no, why)
        sc["footage"] = foot
        sc["footage_meta"] = footage_meta_for(use_rec, sc.get("footage_meta"), scene_file=Path(foot).name if foot else "") if foot else dict(sc.get("footage_meta") or {})
        if not foot and why:
            sc["footage_meta"].setdefault("no_footage_reason", why)
        sc.setdefault("scene_no", no)
        if sc.get("images"):                  # the CSV's images column (before|after for a satellite comparison): project-relative paths made absolute
            sc["images"] = "|".join(str(Path(x.strip()) if Path(x.strip()).is_absolute() else project_dir / x.strip())
                                    for x in str(sc["images"]).split("|") if x.strip())
        out.append(sc)
    if match:
        try:       # estimate which clip fits each narration (metadata only); a failure leaves every scene exactly as resolved above
            from . import footage_match as FM

            for sc in out:       # explicit candidate files get the same honest metadata as manifest clips
                cands = []
                for c in sc.get("footage_candidates") or []:
                    c = {"path": c} if isinstance(c, str) else dict(c or {})
                    p = c.get("path") or c.get("footage")
                    if p:
                        q = Path(p) if Path(p).is_absolute() else project_dir / p
                        if q.is_file():
                            c["path"] = str(q)
                            c["meta"] = footage_meta_for(c.get("meta") if isinstance(c.get("meta"), dict) else {}, None, scene_file=q.name)
                            cands.append(c)
                sc["footage_candidates"] = cands
            disc: Dict[str, dict] = {}
            if (config or {}).get("discover_footage") or discovery_provider is not None:
                try:       # opt-in: narration-derived searches through the app's own stock provider; never needed for a render
                    from . import footage_discovery as FD

                    out, disc = FD.discover(out, project_dir, config, provider=discovery_provider)
                except Exception as exc:
                    log.warning("footage discovery skipped: %s", exc)
            matched = FM.match_scenes(out, _clip_pool(manifest, project_dir))
            for sc in matched:
                if str(sc.get("scene_no")) in disc:
                    sc["footage_discovery"] = disc[str(sc.get("scene_no"))]
            out = matched
        except Exception as exc:
            log.warning("footage relevance estimate skipped: %s", exc)
    return out


def _decision_dict(d: Any) -> dict:
    return d if isinstance(d, dict) else dict(getattr(d, "__dict__", {}) or {"text": str(d)})


def build_report(scenes: List[dict], plan: Any) -> Dict[str, Any]:
    """Per scene: the visual chosen, the asset behind it, its status, flags and reasons (all taken from the plan log and the asset records)."""
    from . import provenance as P

    used = {str(sh.path) for sh in getattr(plan, "shots", [])}
    log_by_no = {str(_decision_dict(d).get("scene_no")): _decision_dict(d) for d in (getattr(plan, "log", []) or [])}
    rows, entries = [], []
    for sc in scenes:
        no = str(sc.get("scene_no"))
        d = log_by_no.get(no, {})
        meta = sc.get("footage_meta") or {}
        foot = sc.get("footage")
        asset = None
        if foot:
            prov = P.from_manifest_record(meta) if (meta.get("provider") or meta.get("source")) else P.Provenance(provider="", description=Path(foot).name, category="footage")
            counted = str(foot) in used
            asset = {"file": Path(foot).name, "kind": meta.get("kind"), "provider": meta.get("provider") or meta.get("source"),
                     "provider_asset_id": meta.get("provider_asset_id"), "author": meta.get("author") or meta.get("channel"),
                     "source_url": meta.get("source_url"), "licence": prov.licence, "rights": meta.get("rights"), "generic": bool(meta.get("generic")),
                     "status": "illustrative" if meta.get("generic") else str(meta.get("verification") or "unverified"),
                     "footage_class": meta.get("footage_class"), "ai_generated": bool(meta.get("ai_generated"))}
            if counted:
                entries.append({"scene_no": no, "prov": prov, "kind": meta.get("kind"), "rights": meta.get("rights"),
                                "rights_known": bool(meta.get("rights_known")), "file": Path(foot).name})
        s0, s1 = float(sc.get("start", 0) or 0), float(sc.get("end", 0) or 0)
        layer_kinds = [ly.kind for ly in getattr(plan, "layers", []) if ly.start < s1 and ly.end > s0 and ly.kind not in ("kicker", "status_chip")]
        fm = sc.get("footage_match") or {}
        rows.append({"scene_no": no, "visual": d.get("chosen"), "layers": layer_kinds, "asset": asset, "flags": d.get("flags", []),
                     "footage_relevance": {k: fm.get(k) for k in ("class", "score", "reasons", "contradictions", "reused_from_scene", "uses", "note")} if fm else None,
                     "footage_discovery": sc.get("footage_discovery"),
                     "reason": d.get("fallback_reason") or "", "no_footage_reason": meta.get("no_footage_reason", "")})
    return {"scenes": rows, "entries": entries}


def run_war_documentary(project_dir: str, scenes: Optional[List[dict]] = None, voiceover_path: Optional[str] = None,
                        out_path: Optional[str] = None, cancel_check: Optional[Callable[[], bool]] = None,
                        progress_cb: Optional[Callable[[float, str], None]] = None, *, assets: Optional[dict] = None,
                        config: Optional[dict] = None, plan_fn: Optional[Callable[..., Any]] = None, workers: Optional[int] = None,
                        write_report: bool = True) -> Dict[str, Any]:
    """Plan from the narration, then render with the bounded-memory segmented renderer. Returns a result dict; raises RenderCancelled on cancel.

    result: {ok, out, plan_log (list), credits (list), stats, render (the renderer's dict), report_path, credits_path, seconds}
    Writes next to the output: <out>.report.json (per scene: visual, asset, status, flags, reasons) and <out>.credits.txt.
    """
    from . import segments, provenance as P
    t0 = time.time()
    pd = Path(project_dir)
    if plan_fn is None:
        from . import planner

        plan_fn = planner.plan
    sc = load_scenes(pd, scenes, config=config)
    if not sc:
        raise ValueError("no scenes to render")
    if progress_cb:
        progress_cb(0.0, "planning visuals from the narration")
    plan = plan_fn(sc, assets=assets, config=config)
    out = Path(out_path) if out_path else pd / "War_Documentary.mp4"
    state = pd / "state"             # the project's own state folder: the same RenderCache location the other styles use, so a re-run reuses unchanged segments
    state.mkdir(parents=True, exist_ok=True)
    try:        # measured cover (direction.harden_measured): a map or card that draws thin on the plate is repaired in the plan, before anything is rendered
        from . import backdrop as _bd0, direction as _dir

        hook0 = float((((getattr(plan, "stats", {}) or {}).get("direction") or {}).get("story") or {}).get("hook", {}).get("window") or 0.0)
        hc = _dir.harden_measured(plan, sc, _bd0.ensure_backdrop(state), hook0)
        if hc and isinstance(getattr(plan, "stats", None), dict):
            plan.stats.setdefault("direction", {}).setdefault("counts", {}).update({k: v for k, v in hc.items() if v})
    except Exception as exc:  # noqa: BLE001 - the plan stays as planned
        log.warning("measured cover pass skipped: %s", exc)
    shots, layers = list(plan.shots), list(plan.layers)
    # a scene with no footage must not leave a hole (or an empty timeline): its maps and cards sit on a plain labelled-neutral backdrop, never on an unrelated clip
    from . import backdrop as _bd

    total_end = max([float(x.get("end") or 0.0) for x in sc] + [0.0])
    plate_path = _bd.ensure_backdrop(state)
    shots = _bd.fill_gaps(shots, total_end, plate_path)

    def prog(k: float, msg: str) -> None:
        if progress_cb:
            progress_cb(0.05 + 0.95 * k, msg)

    audio_path = voiceover_path
    try:                                  # music bed ducked under the voice, sound on the graphics, -14 LUFS master (war/audio.py)
        from . import audio as _audio

        prog(0.0, "mixing the sound")
        audio_path = _audio.build_mix(voiceover_path, total_end, layers, str(state / "war_mix.m4a"), config or {})
    except Exception as exc:  # noqa: BLE001 - the voice alone still makes the film
        log.warning("sound mix skipped: %s", exc)
    res = segments.render_with_fallback(shots, layers, str(out), audio_path=audio_path, audio_fallback=voiceover_path,
                                        backdrop_path=str(plate_path) if plate_path else None, state_dir=str(state), cancel_check=cancel_check,
                                        progress_cb=prog, workers=workers)
    rep = build_report(sc, plan)
    credit_lines = list(getattr(plan, "credits", []) or [])
    fl_credits = list(((getattr(plan, "stats", {}) or {}).get("direction") or {}).get("frontline", {}).get("credits") or [])
    credit_lines += [c for c in fl_credits if c not in credit_lines]      # front-line sources are credited with their dates and licences
    unresolved = [f"scene {e['scene_no']}: {e.get('rights') or 'rights not established'}" for e in rep["entries"]
                  if e.get("kind") != "user" and (not e.get("rights_known") or e["prov"].licence == P.UNKNOWN)]
    result: Dict[str, Any] = {"ok": bool(res.get("ok")), "out": str(out), "render": res, "credits": credit_lines, "rights_not_established": unresolved,
                              "plan_log": [_decision_dict(d) for d in (getattr(plan, "log", []) or [])],
                              "stats": getattr(plan, "stats", {}), "seconds": time.time() - t0, "report_path": None, "credits_path": None,
                              "graphics": graphics_count(layers)}
    if write_report:
        try:
            cp = out.with_suffix(".credits.txt")
            cp.write_text(P.credits_text(rep["entries"]) + ("\n\nFRONT-LINE DATA\n" + "\n".join(fl_credits) + "\n" if fl_credits else ""),
                          encoding="utf-8")
            result["credits_path"] = str(cp)
        except OSError as exc:
            log.warning("credits file not written: %s", exc)
        try:                                  # where the video might sag (war/engagement.py), measured on the plan
            from . import engagement as _eng

            rep_e = ((getattr(plan, "stats", {}) or {}).get("direction") or {}).get("engagement")
            if rep_e:
                ep = out.with_suffix(".engagement.txt")
                ep.write_text(_eng.text(rep_e), encoding="utf-8")
                result["engagement_path"] = str(ep)
                result["engagement"] = rep_e.get("summary")
        except OSError as exc:
            log.warning("engagement report not written: %s", exc)
        try:                                  # where every graphic is in the video, so each one in the graphics sheets can be found
            gp = out.with_suffix(".graphics.txt")
            gp.write_text(graphics_index(layers), encoding="utf-8")
            result["graphics_path"] = str(gp)
        except OSError as exc:
            log.warning("graphics index not written: %s", exc)
        try:                                  # visual QA of the finished mp4 (render_qa.py): bare grid, blank frames, short footage shots; never fails the render
            from . import render_qa as _qa

            if result["ok"] and out.is_file():
                hook_w = float((((getattr(plan, "stats", {}) or {}).get("direction") or {}).get("story") or {}).get("hook", {}).get("window") or 0.0)
                qa = _qa.check(str(out), str(plate_path) if plate_path else None, montage=[(0.0, hook_w)] if hook_w > 0 else ())
                out.with_suffix(".qa.json").write_text(json.dumps(qa, indent=1, default=str), encoding="utf-8")
                out.with_suffix(".qa.txt").write_text(_qa.text(qa), encoding="utf-8")
                result["qa"] = {k: qa.get(k) for k in ("bare_plate_s", "sparse_plate_s", "blank_s")}
                result["qa"]["short_shots"] = len(qa.get("short_shots") or [])
                log.warning("render QA: bare grid %.1f s, sparse grid %.1f s, blank %.1f s, short footage shots %d (see %s)", qa["bare_plate_s"],
                            qa["sparse_plate_s"], qa["blank_s"], len(qa.get("short_shots") or []), out.with_suffix(".qa.txt").name)
        except Exception as exc:  # noqa: BLE001 - the QA never fails a render
            log.warning("render QA skipped: %s", exc)
        try:
            rp = out.with_suffix(".report.json")
            rp.write_text(json.dumps({"credits": credit_lines, "rights_not_established": unresolved, "scenes": rep["scenes"], "log": result["plan_log"],
                                      "stats": result["stats"], "render": res}, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
            result["report_path"] = str(rp)
        except OSError as exc:
            log.warning("plan report not written: %s", exc)
    return result


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Render a War Documentary from a scenes.json (no app needed).")
    ap.add_argument("--project", default=".", help="project folder (footage paths and Images/.asset_manifest.json are read from it)")
    ap.add_argument("--scenes", help="scenes JSON (default <project>/war_scenes.json)")
    ap.add_argument("--voiceover")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    scenes = _read_json(Path(a.scenes)) if a.scenes else None
    r = run_war_documentary(a.project, scenes, a.voiceover, a.out, progress_cb=lambda k, m: print(f"{k:5.1%} {m}", file=sys.stderr))
    print(json.dumps({k: r[k] for k in ("ok", "out", "report_path", "seconds")}, indent=1))
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
