"""Offline, testable evidence analysis: ledger events of ONE style scope -> candidate rules (never active rules).

Safeguards: one vote per project (a project re-rendered ten times counts once), minimum projects / observations / share before a
candidate exists, correlation is stated as correlation, and nothing here edits CSVs, prompts, settings or code. A human must
approve a candidate before ``approved_rules`` turns it into package material; publishing is a separate trusted step.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional

from . import events as ev
from . import packages
from .assets import canonical_source

MIN_PROJECTS = 3
MIN_FAILURES = 8
MIN_FAILING_RENDER_SHARE = 0.2
MIN_RATED_PROJECTS = 5
MIN_TAG_SHARE = 0.3
MIN_RATING_GAP = 1.0
LOW_CATEGORY_MEAN = 2.5

_TAG_TEXT = {
    "wrong_visuals": "Reviewers often report visuals that do not match the narration in this style: describe each scene's subject concretely.",
    "repetitive_scenes": "Reviewers often report repetitive scenes in this style: vary the subject and framing between neighbouring scenes.",
    "bad_transitions": "Reviewers often report poor transitions in this style: avoid abrupt changes of visual type between adjacent scenes.",
    "weak_graphics": "Reviewers often report weak graphics in this style: use graphic rows only where a number, name or place needs them.",
    "poor_pacing": "Reviewers often report poor pacing in this style: keep scenes short and avoid long static stretches.",
}
_CAT_TEXT = {
    "visual_relevance": "Visual relevance to the narration is rated low in this style: make each scene's prompt specific to its sentence.",
    "footage_selection": "Footage selection is rated low in this style: prefer specific footage queries over generic ones.",
    "animations_graphics": "Animations and graphics are rated low in this style: simplify graphic rows and check their timing.",
    "typography_transitions": "Typography and transitions are rated low in this style: keep on-screen text short and transitions consistent.",
    "pacing": "Pacing is rated low in this style: shorten long scenes and keep something moving every few seconds.",
}


def _cand(scope, cid, kind, text, evidence, confidence, pattern, benefit, **extra):
    return {"id": cid, "kind": kind, "status": "candidate", "style_scope": scope, "text": text, "evidence_count": int(evidence),
            "confidence": round(float(confidence), 2), "pattern": pattern, "expected_benefit": benefit,
            "side_effects": "May over-correct scenes that were fine; advisory only, never applied automatically.",
            "suggested_action": "Add as an advisory line to the copied CSV prompt for this style after review.",
            "evaluation_criteria": "Compare ratings and scene-failure rate of renders made before and after adoption (association, not proof).",
            **extra}


def build_candidates(events: Iterable[Dict[str, Any]], scope: str, *, min_projects: int = MIN_PROJECTS, min_failures: int = MIN_FAILURES,
                     min_rated: int = MIN_RATED_PROJECTS) -> List[Dict[str, Any]]:
    evs = [e for e in events if e.get("style_scope") == scope]          # strict scope isolation
    renders = {e.get("generation_id") or (e.get("payload") or {}).get("operation_id") or e["event_id"]
               for e in evs if e["event_type"] == "render_outcome"}
    out: List[Dict[str, Any]] = []

    # scene failures by provider key: distinct projects and renders, not raw counts from one project
    by_src: Dict[str, Dict[str, set]] = defaultdict(lambda: {"projects": set(), "renders": set(), "n": [0]})
    for e in evs:
        if e["event_type"] != "scene_failure":
            continue
        p = e.get("payload") or {}
        d = by_src[p.get("source") or "unknown"]
        d["projects"].add(e.get("project_id"))
        d["renders"].add(e.get("generation_id") or e["event_id"].split(":")[1])
        d["n"][0] += 1
    for src, d in sorted(by_src.items()):
        share = len(d["renders"]) / max(1, len(renders))
        if canonical_source(src) and len(d["projects"]) >= min_projects and d["n"][0] >= min_failures and share >= MIN_FAILING_RENDER_SHARE:
            out.append(_cand(scope, f"fail-{src}", "asset_type_failure",
                             f"Scenes using the {src} asset type often fail to resolve in this style; prefer another type where the scene allows.",
                             d["n"][0], min(0.95, 0.4 + share / 2 + min(len(d["projects"]), 10) / 40),
                             f"{len(d['renders'])} of {len(renders)} renders in {len(d['projects'])} projects had {src} scene failures.",
                             "Fewer failed scenes and retries.", asset_type=src))

    # ratings: one vote per project = its newest rating event
    latest: Dict[str, Dict[str, Any]] = {}
    for e in evs:
        if e["event_type"] == "video_rating" and e.get("project_id"):
            latest[e["project_id"]] = e
    rated = list(latest.values())
    if len(rated) >= min_rated:
        for tag, text in _TAG_TEXT.items():
            n = sum(1 for e in rated if tag in (e["payload"].get("tags") or []))
            if n >= min_projects and n / len(rated) >= MIN_TAG_SHARE:
                out.append(_cand(scope, f"tag-{tag}", "tag_pattern", text, n, min(0.9, 0.4 + n / len(rated) / 2),
                                 f"{n} of {len(rated)} rated projects carry the '{tag}' tag.", "Fewer repeat complaints."))
        for cat, text in _CAT_TEXT.items():
            vals = [e["payload"]["categories"][cat] for e in rated if cat in (e["payload"].get("categories") or {})]
            if len(vals) >= min_rated and sum(vals) / len(vals) <= LOW_CATEGORY_MEAN:
                out.append(_cand(scope, f"cat-{cat}", "note", text, len(vals), 0.5,
                                 f"Mean {cat} score {sum(vals) / len(vals):.1f} over {len(vals)} rated projects.", "Higher category scores."))
    out += _feature_candidates(evs, scope, min_projects=min_projects, min_rated=min_rated)
    return out


def _mean(v):
    return sum(v) / len(v)


def _feature_candidates(evs, scope, *, min_projects, min_rated) -> List[Dict[str, Any]]:
    """CSV structure vs ratings, one vote per project (its newest analysis and newest rating). Unrated projects are simply absent
    (missing is never negative). Results are ASSOCIATIONS between a structural feature and ratings, not proof of cause."""
    analysis: Dict[str, Dict[str, Any]] = {}
    rating: Dict[str, int] = {}
    ok_r: set = set()
    bad_r: set = set()
    for e in evs:
        pid = e.get("project_id")
        if not pid:
            continue
        t, pl = e["event_type"], e.get("payload") or {}
        if t == "csv_analysis":
            analysis[pid] = pl
        elif t == "video_rating":
            rating[pid] = pl.get("rating")
        elif t == "render_outcome":
            (ok_r if pl.get("outcome") == "success" else bad_r).add(pid)
    pairs = [(analysis[p], rating[p], p) for p in analysis if isinstance(rating.get(p), int)]
    if len(pairs) < min_rated:
        return []
    out: List[Dict[str, Any]] = []
    basis = f"{len(pairs)} rated projects with an analysed CSV; renders: {len(ok_r)} projects succeeded, {len(bad_r)} had a failed render (not counted as ratings)."

    wm = [(a["words_mean"], r) for a, r, _ in pairs if isinstance(a.get("words_mean"), (int, float))]
    if len(wm) >= min_rated:
        med = sorted(w for w, _ in wm)[len(wm) // 2]
        short = [(w, r) for w, r in wm if w < med]
        long_ = [(w, r) for w, r in wm if w >= med]
        if len(short) >= min_projects and len(long_) >= min_projects:
            diff = _mean([r for _, r in short]) - _mean([r for _, r in long_])
            gap = _mean([w for w, _ in long_]) - _mean([w for w, _ in short])
            if diff >= MIN_RATING_GAP and gap >= 10:
                param = max(12, min(120, int(round(_mean([w for w, _ in short])))))
                out.append(_cand(scope, "pace-shorter", "pacing_target",
                                 f"Projects with shorter scenes (about {param} words) were rated higher in this style; keep scenes near {param} words.",
                                 len(wm), min(0.9, 0.35 + diff / 5 + len(wm) / 40),
                                 f"Association only: shorter-scene projects averaged {_mean([r for _, r in short]):.1f} stars vs "
                                 f"{_mean([r for _, r in long_]):.1f} for longer ones ({len(short)} vs {len(long_)} projects). {basis}",
                                 "Possibly better-rated pacing.", param=param))
    runs = [(a["max_same_type_run"], r) for a, r, _ in pairs if isinstance(a.get("max_same_type_run"), int)]
    rep, varied = [(x, r) for x, r in runs if x >= 4], [(x, r) for x, r in runs if x <= 2]
    if len(rep) >= min_projects and len(varied) >= min_projects:
        diff = _mean([r for _, r in varied]) - _mean([r for _, r in rep])
        if diff >= MIN_RATING_GAP:
            out.append(_cand(scope, "variety-run2", "variety_run",
                             "Projects that never repeated an asset type more than twice in a row were rated higher in this style; limit repeats to 2.",
                             len(rep) + len(varied), min(0.9, 0.35 + diff / 5 + len(runs) / 40),
                             f"Association only: varied projects averaged {_mean([r for _, r in varied]):.1f} stars vs {_mean([r for _, r in rep]):.1f} "
                             f"for projects with runs of 4+ ({len(varied)} vs {len(rep)} projects). {basis}",
                             "Possibly fewer 'repetitive scenes' complaints.", param=2))
    mode = scope.split("/", 1)[0]
    if mode in ("hybrid", "starmap", "whatif"):
        out += _beat_candidates(pairs, scope, mode, basis, min_projects=min_projects, min_rated=min_rated)
    return out


def _beat_candidates(pairs, scope, mode, basis, *, min_projects, min_rated) -> List[Dict[str, Any]]:
    """Hybrid / StarMap / What If: beat-or-shot structure vs ratings. The generator has no planner for these styles, so the rules
    are plain-text ``note`` guidance (shown in the copied prompt for that exact style), never an automatic change."""
    unit = "shots" if mode == "whatif" else "beats"
    kind = "visual types" if mode == "whatif" else "modes"
    out: List[Dict[str, Any]] = []
    runs = [(a["max_same_mode_run"], r) for a, r, _ in pairs if isinstance(a.get("max_same_mode_run"), int)]
    rep, varied = [(x, r) for x, r in runs if x >= 4], [(x, r) for x, r in runs if x <= 2]
    if len(rep) >= min_projects and len(varied) >= min_projects:
        diff = _mean([r for _, r in varied]) - _mean([r for _, r in rep])
        if diff >= MIN_RATING_GAP:
            out.append(_cand(scope, "mode-run2", "note",
                             f"Projects that never used the same {kind[:-1]} for more than 2 {unit} in a row were rated higher in this style; alternate the {kind}.",
                             len(rep) + len(varied), min(0.9, 0.35 + diff / 5 + len(runs) / 40),
                             f"Association only: varied projects averaged {_mean([r for _, r in varied]):.1f} stars vs {_mean([r for _, r in rep]):.1f} "
                             f"for projects with runs of 4+ ({len(varied)} vs {len(rep)} projects). {basis}", "Possibly less repetitive pacing."))
    bs = [(a["beat_s_mean"], r) for a, r, _ in pairs if isinstance(a.get("beat_s_mean"), (int, float))]
    if len(bs) >= min_rated:
        med = sorted(w for w, _ in bs)[len(bs) // 2]
        short, long_ = [(w, r) for w, r in bs if w < med], [(w, r) for w, r in bs if w >= med]
        if len(short) >= min_projects and len(long_) >= min_projects:
            diff = _mean([r for _, r in short]) - _mean([r for _, r in long_])
            gap = _mean([w for w, _ in long_]) - _mean([w for w, _ in short])
            if diff >= MIN_RATING_GAP and gap >= 1.0:
                target = round(_mean([w for w, _ in short]), 1)
                out.append(_cand(scope, "beat-shorter", "note",
                                 f"Projects with shorter {unit} (about {target:g} seconds each) were rated higher in this style; keep {unit} near {target:g} seconds.",
                                 len(bs), min(0.9, 0.35 + diff / 5 + len(bs) / 40),
                                 f"Association only: shorter-{unit[:-1]} projects averaged {_mean([r for _, r in short]):.1f} stars vs {_mean([r for _, r in long_]):.1f} "
                                 f"({len(short)} vs {len(long_)} projects; only {unit} with timings in the file are measured). {basis}", "Possibly better-rated pacing."))
    return out


def discover(events: Iterable[Dict[str, Any]], **kw) -> Dict[str, List[Dict[str, Any]]]:
    """Candidates per style scope, from ledger events (each scope analysed strictly on its own events)."""
    evs = list(events)
    out = {}
    for scope in sorted({e["style_scope"] for e in evs}):
        c = build_candidates(evs, scope, **kw)
        if c:
            out[scope] = c
    return out


def approved_rules(candidates: List[Dict[str, Any]], approved_ids: Iterable[str]) -> List[Dict[str, Any]]:
    """Human approval step: only explicitly approved candidate ids become package rules."""
    want = set(approved_ids)
    rules = []
    for c in candidates:
        if c["id"] in want:
            r = {"id": c["id"], "kind": c["kind"], "text": c["text"], "confidence": c["confidence"],
                 "evidence_count": c["evidence_count"], "status": "approved"}
            if c.get("asset_type"):
                r["asset_type"] = c["asset_type"]
            if c.get("param") is not None:
                r["param"] = int(c["param"])
            rules.append(r)
    return rules


def compare_packages(old: Optional[Dict[str, Any]], new: Dict[str, Any]) -> Dict[str, Any]:
    """What a candidate package changes relative to the one in force. Says nothing about whether quality improves."""
    o = {r["id"]: r for r in (old or {}).get("rules", [])}
    n = {r["id"]: r for r in new.get("rules", [])}
    return {"added": sorted(set(n) - set(o)), "removed": sorted(set(o) - set(n)),
            "changed": sorted(i for i in set(o) & set(n) if o[i] != n[i]),
            "same_scope": (old is None) or old.get("style_scope") == new.get("style_scope"),
            "valid": packages.validate(new).ok}
