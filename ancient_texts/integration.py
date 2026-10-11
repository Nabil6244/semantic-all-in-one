"""The functions app.py calls. Every one is a no-op unless the project's style is `enoch_template`.

"On" has one source of truth: the project's `video_style.style_id` (project_workspace.video_style_settings), the same
setting project creation writes and that the figure, AI-limit and graphics rules already read. The picker card sets it and,
when the user leaves the card, puts back the style the project had before (kept in the project's state folder).

Project files (all optional, all in <project>/state/enoch_template/):
  claims.json       the claim ledger (sources + claims) returned by the research prompt and reviewed by a person
  script_map.json   the script map (sentence roles, claim links) returned by the script prompt
  cards.json        card requests: {"<scene number>": {"kind": ..., "fields": {...}, "claim_ids": [...]}}
written by the app:
  plan_report.json  the refine pass: reasons, AI share and denominator, what changed and why, issues
  sources.md        the verification sheet (what each claim rests on; "unreviewed" where nobody checked)
  qc_report.json    after a render: hard failures / soft deviations / review items, loudness before and after
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Callable, List, Optional

from . import STYLE_ID
from .issues import Issue, ValidationError, summary

STATE_SUBDIR = "enoch_template"
REFERENCE_PROFILE = "enoch_ref_01"


def is_active(ws) -> bool:
    try:
        return ws is not None and (ws.video_style_settings() or {}).get("style_id") == STYLE_ID
    except Exception:
        return False


def state_dir(ws) -> Path:
    return Path(ws.state_dir) / STATE_SUBDIR


# ---------------------------------------------------------------- selection (picker card)

def select(ws) -> None:
    """Make Enoch Template the project's style, remembering the style it had so leaving the card restores it."""
    current = ws.video_style_settings()
    if current.get("style_id") == STYLE_ID:
        return
    d = state_dir(ws)
    d.mkdir(parents=True, exist_ok=True)
    (d / "previous_style.json").write_text(json.dumps(current, indent=1), encoding="utf-8")
    ws.set_video_style_settings(mode="manual", style_id=STYLE_ID, brand_kit_id=current.get("brand_kit_id"))


def deselect(ws) -> None:
    """Leave Enoch Template: restore the project's previous style (or none, if it had none)."""
    current = ws.video_style_settings()
    if current.get("style_id") != STYLE_ID:
        return
    prev = {"mode": "", "style_id": None, "brand_kit_id": current.get("brand_kit_id")}
    p = state_dir(ws) / "previous_style.json"
    if p.is_file():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("style_id") != STYLE_ID:
                prev = {"mode": data.get("mode") or "", "style_id": data.get("style_id"), "brand_kit_id": data.get("brand_kit_id")}
        except (OSError, json.JSONDecodeError):
            pass
    ws.set_video_style_settings(mode=prev["mode"], style_id=prev["style_id"], brand_kit_id=prev["brand_kit_id"])


# ---------------------------------------------------------------- planning

def guidance(script: str = "") -> str:
    """Extra guidance for the VisualDirector (plan path), next to the style's own adornment."""
    del script
    return ("ENOCH TEMPLATE: evidence first. Each shot must show what its narration names: a real manuscript, fragment, "
            "printed edition, place or work of art when the narration names one; a map for a place; a reconstruction ONLY "
            "for what no camera or painter recorded, and never more than two in a row. No generic stock to fill time. "
            "Prefer still documents and art (they will move gently); hard cuts.")


def _inputs(ws, script: str, log: Callable[[str], None]):
    from .claims import load_ledger
    from .framework import build_script_map, load_annotations

    d = state_dir(ws)
    ledger = smap = None
    issues: List[Issue] = []
    requests = {}
    if (d / "claims.json").is_file():
        try:
            ledger = load_ledger(d / "claims.json")
        except ValidationError as exc:
            issues.append(Issue("ledger_invalid", "hard", str(exc), "claims.json"))
    if (d / "script_map.json").is_file() and script.strip():
        try:
            ann = load_annotations(d / "script_map.json")
            smap, more = build_script_map(script, ann, preset=str(ann.get("preset") or "adaptive"))
            issues.extend(more)
        except ValidationError as exc:
            issues.append(Issue("script_map_invalid", "hard", str(exc), "script_map.json"))
    if (d / "cards.json").is_file():
        try:
            raw = json.loads((d / "cards.json").read_text(encoding="utf-8"))
            requests = {int(k): v for k, v in raw.items()} if isinstance(raw, dict) else {}
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            issues.append(Issue("cards_invalid", "hard", f"cards.json: {exc}", "cards.json"))
    return ledger, smap, requests, issues


def refine(plan, ws, *, script: str = "", images_dir: Optional[Path] = None, csv_rows=None,
           log: Callable[[str], None] = lambda s: None) -> Optional[dict]:
    """Run the style's checks and refine pass on `plan` (in place). Returns the plan report, or None when not active."""
    if not is_active(ws) or plan is None:
        return None
    from style_engine.loader import load_style

    from .claims import check_ledger, sources_markdown, watch_list_as_claims
    from .framework import check_structure
    from .plan import refine_plan
    from .subjects import pack_for_style

    style = load_style(STYLE_ID)
    pack = pack_for_style(STYLE_ID)
    ledger, smap, requests, issues = _inputs(ws, script, log)
    if ledger is not None:
        issues.extend(check_ledger(ledger))
    if smap is not None:
        issues.extend(check_structure(smap, ledger))
    if pack is not None and ledger is None:
        issues.extend(watch_list_as_claims(pack.research_watch_list))
    import copy

    from .qc import load_profile
    from .visual_mix import load_targets

    snapshot = copy.deepcopy(plan.scenes)
    try:
        result = refine_plan(plan, style=style, pack=pack, ledger=ledger, script_map=smap, card_requests=requests,
                             images_dir=images_dir, csv_rows=csv_rows, mix_targets=load_targets(load_profile(REFERENCE_PROFILE)))
    except Exception:
        plan.scenes = snapshot             # a failed pass leaves the plan exactly as it was
        raise
    issues.extend(result.issues)
    d = state_dir(ws)
    d.mkdir(parents=True, exist_ok=True)
    payload = result.to_dict()
    payload["issues"] = [i.to_dict() for i in issues]
    payload["summary"] = summary(issues)
    (d / "plan_report.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")
    if ledger is not None:
        (d / "sources.md").write_text(sources_markdown(ledger), encoding="utf-8")
    r = result.report
    log(f"[ENOCH TEMPLATE] {r['eligible_visual_scenes']} scene(s): AI {r['ai_scenes']} ({r['ai_share']:.0%}, ceiling "
        f"{r['ai_ceiling']:.0%} = {r['ai_allowed']} allowed, {'met' if r['ai_ceiling_met'] else 'NOT met'}), documents "
        f"{r['documentary_source_imagery']}, art {r['historical_art']}, cards {r['designed_cards']}, real-world "
        f"{r['real_world_footage']}, maps {r['maps']}.")
    for m in result.scenes:
        if m.change:
            log(f"[ENOCH TEMPLATE] scene {m.scene}: {m.change}")
    mix = r.get("planned_mix") or {}
    if mix:
        log("[ENOCH TEMPLATE] Planned mix: " + ", ".join(f"{k} {v:.0%}" for k, v in mix["shares"].items() if v))
    log(f"[ENOCH TEMPLATE] Checks: {summary(issues)} — details in state/{STATE_SUBDIR}/plan_report.json")
    return payload


def csv_local_rows_win(scene_rows: list, csv_rows: list) -> list:
    """The pipeline builds its asset rows from the in-memory plan, whose conversion has no `local` branch (a `local` scene
    would become a stock search for its description). For this style, a scene the CSV marks local/local_image/local_video
    (a card, or a file the user placed) keeps its CSV row, so it resolves to its numbered file and nothing is searched."""
    from providers.base import SceneRow

    local = {}
    for r in csv_rows or []:
        at = str(r.get("asset_type") or "").strip().lower()
        if at in ("local", "local_image", "local_video"):
            try:
                local[int(str(r.get("scene_number") or "").strip())] = r
            except ValueError:
                continue
    out = []
    for row in scene_rows:
        try:
            n = int(str(row.scene_number).strip())
        except ValueError:
            out.append(row)
            continue
        out.append(SceneRow.from_csv_row(local[n]) if n in local else row)
    return out


def actual_visual_mix(ws, ledger=None) -> Optional[dict]:
    """The mix of the files really in the project's Images folder, against the last plan report (None without one)."""
    from .qc import load_profile
    from .visual_mix import actual_mix, load_provenance, load_targets

    p = state_dir(ws) / "plan_report.json"
    if not p.is_file():
        return None
    scenes = json.loads(p.read_text(encoding="utf-8")).get("scenes") or []
    if ledger is None and (state_dir(ws) / "claims.json").is_file():
        from .claims import load_ledger

        try:
            ledger = load_ledger(state_dir(ws) / "claims.json")
        except ValidationError:
            ledger = None
    return actual_mix(ws.assets_dir, scenes, provenance=load_provenance(ws.assets_dir, state_dir(ws)), ledger=ledger,
                      targets=load_targets(load_profile(REFERENCE_PROFILE)))


def card_scenes(ws) -> set:
    """Scene numbers whose picture is an installed card (from the last plan report)."""
    p = state_dir(ws) / "plan_report.json" if ws is not None else None
    if p is None or not p.is_file():
        return set()
    try:
        scenes = json.loads(p.read_text(encoding="utf-8")).get("scenes") or []
    except (OSError, json.JSONDecodeError):
        return set()
    return {str(s.get("scene")) for s in scenes if (s.get("card") or {}).get("installed")}


def drop_graphics_on_cards(timeline: dict, ws) -> dict:
    """Remove graphic overlays (lower thirds, callouts, number cards) whose scene is a card; every other event is kept."""
    cards = card_scenes(ws)
    if not cards or not isinstance(timeline, dict):
        return timeline
    events = []
    for e in timeline.get("events") or []:
        meta = (e or {}).get("metadata") or {} if isinstance(e, dict) else {}
        if isinstance(e, dict) and meta.get("graphic") and str(e.get("scene_number") or "").lstrip("0") in {c.lstrip("0") for c in cards}:
            continue
        events.append(e)
    return dict(timeline, events=events)


def named_terms(style=None, pack=None) -> list:
    """Words that name a subject for the post-download check: the pack's subject/document/place words and scholars, the
    style's figures and real subjects, and the artists its artwork searches name."""
    from style_engine.loader import load_style

    from .subjects import pack_for_style

    style = style or load_style(STYLE_ID)
    pack = pack or pack_for_style(STYLE_ID)
    out = []
    if pack is not None:
        out += list(pack.subject_terms + pack.place_terms) + [n for s in pack.scholars for n in s.names]
    if style is not None:
        out += list(style.selection_rules.real_subjects)
        out += [str(e.get("name") or "") for e in style.entities or []] + [a for e in style.entities or [] for a in e.get("aliases") or []]
        out += ["blake", "doré", "dore", "martin", "reni", "michelangelo", "rembrandt", "qumran", "hermon"]
    return sorted({t.lower() for t in out if t})


# ---------------------------------------------------------------- editing / render

def smart_editing_settings(base):
    """Conservative editing until the reference's music/SFX are confirmed by listening: hard cuts dominate, low SFX,
    no ambience bed. Text effects and graphics keep the user's settings."""
    return dataclasses.replace(base, intensity="low", sound_effects_intensity="low", visual_transitions_intensity="low",
                               scene_ambience=False)


def finish_render(output_path, ws, *, log: Callable[[str], None] = lambda s: None) -> Optional[dict]:
    """After a successful render: finish the audio (opt-in, this style only), measure the result, write the QC report."""
    if not is_active(ws):
        return None
    from . import audio as A
    from .qc import evaluate, measure_render

    path = Path(output_path)
    fin = A.finish(path)
    if fin.status == "finished" and fin.after is not None:
        log(f"[ENOCH TEMPLATE] Audio: {fin.before.integrated_lufs:.1f} LUFS / {fin.before.true_peak_dbtp:.1f} dBTP -> "
            f"{fin.after.integrated_lufs:.1f} LUFS / {fin.after.true_peak_dbtp:.1f} dBTP (measured); video stream "
            f"{'unchanged' if fin.video_stream_identical else 'n/a'}. {fin.message}")
    else:
        log(f"[ENOCH TEMPLATE] Audio finishing: {fin.status} — {fin.message}")
    plan_report = None
    p = state_dir(ws) / "plan_report.json"
    if p.is_file():
        try:
            plan_report = json.loads(p.read_text(encoding="utf-8")).get("report")
        except (OSError, json.JSONDecodeError):
            plan_report = None
    try:
        render = measure_render(path)
    except Exception as exc:  # QC never blocks the finished file
        render = {"error": str(exc)}
    render["audio_status"] = fin.status
    render["audio_message"] = fin.message
    asset_issues = []
    try:
        from .plan import SceneMeta
        from .qc import check_acquired_assets
        from style_engine.loader import load_style

        scenes = json.loads(p.read_text(encoding="utf-8")).get("scenes") if p.is_file() else []
        metas = [SceneMeta(scene=int(x["scene"]), reason=x.get("reason", ""), source_kind=x.get("source_kind", ""),
                           anchors=list(x.get("anchors") or []), query=x.get("query", "")) for x in scenes or []]
        asset_issues = check_acquired_assets(ws.assets_dir, metas, load_style(STYLE_ID).search_guidance.avoid_terms, named_terms())
    except Exception as exc:  # the check is an extra; it never blocks the finished file
        log(f"[ENOCH TEMPLATE] Download check skipped ({exc})")
    actual = None
    try:
        actual = actual_visual_mix(ws)
        if actual is not None:
            asset_issues = list(asset_issues) + [Issue(**i) for i in actual["issues"]]
            log("[ENOCH TEMPLATE] Actual mix: " + ", ".join(f"{k} {v:.0%}" for k, v in actual["shares"].items() if v))
    except Exception as exc:
        log(f"[ENOCH TEMPLATE] Actual mix skipped ({exc})")
    report = evaluate(plan_report=plan_report, render=render, profile_id=REFERENCE_PROFILE, issues=asset_issues)
    report["audio_finishing"] = fin.to_dict()
    report["planned_mix"] = (plan_report or {}).get("planned_mix")
    report["actual_mix"] = {k: actual[k] for k in ("counts", "shares", "evidence_counts", "scenes_detail")} if actual else None
    state_dir(ws).mkdir(parents=True, exist_ok=True)
    (state_dir(ws) / "qc_report.json").write_text(json.dumps(report, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    log(f"[ENOCH TEMPLATE] QC: {report['verdict']}")
    return report
