"""Visual mix: what kind of picture each scene is, how it relates to the narration's evidence, and whether the whole film
is balanced -- planned (from the refine pass) and actual (from the files that really exist), reported separately.

Primary visual type, by precedence (the first rule that applies wins, so percentages are reproducible):
  0 unresolved           nothing usable: a planned card that was not installed, or (actual) no file for the scene.
                         Never counted as a visual.
  1 ai_reconstruction    an AI asset type, or a file whose provenance is AI -- whatever its search words say
  2 text_card            a standalone text card (statement, section break)
  3 map_diagram          a map, or an explanatory graphic (comparison card, cited source card)
  4 historical_artwork   a painting, engraving, drawing, icon ...
  5 manuscript_document  a manuscript, scroll, fragment, printed edition (or a framed photo of one)
  6 real_world_location  every other real picture: places, objects, people, footage, the user's own files

Evidence relationship (what the picture does for the narration):
  direct_evidence   shows the very thing named (a document, the place, a verified quotation)
  illustration      depicts or explains it (historical art, a map, a comparison, a cited summary, a context picture)
  interpretation    a text card carrying an interpretive or disputed claim
  reconstruction    an AI image of what no camera or painter recorded
  narration_text    a text card restating the narration (not evidence of anything)

Targets are soft and configurable (reference profile "visual_mix"); they are reported, never enforced by inserting pictures.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

from .issues import Issue

CATEGORIES = ("ai_reconstruction", "text_card", "map_diagram", "historical_artwork", "manuscript_document",
              "real_world_location")
EVIDENCE = ("direct_evidence", "illustration", "interpretation", "reconstruction", "narration_text")
TEXT_KINDS = ("statement", "section_break")
GRAPHIC_KINDS = ("comparison", "source_excerpt")
SCENE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi")
AI_SOURCES = ("flow_image", "flow_video", "image", "video", "ai", "ai_generated")

DEFAULT_TARGETS = {
    "text_card": {"target": [0.15, 0.20], "warn": [0.25, 0.30]},
    "ai_reconstruction": {"max": 0.12},
    "consecutive_text_cards": {"warn_run": 2, "strong_run": 3},
}


def load_targets(profile: Optional[dict] = None) -> dict:
    t = dict(DEFAULT_TARGETS)
    if profile and isinstance(profile.get("visual_mix"), dict):
        t.update({k: v for k, v in profile["visual_mix"].items() if not k.startswith("_")})
    return t


def _get(m, key, default=None):
    return m.get(key, default) if isinstance(m, dict) else getattr(m, key, default)


def classify(meta, *, ai_provenance: bool = False, installed: bool = True) -> str:
    """The scene's primary visual type (see the module docstring for the precedence)."""
    card = _get(meta, "card") or None
    kind = _get(meta, "source_kind", "")
    if not installed or (card is None and _get(meta, "planned_card")):
        return "unresolved"
    if ai_provenance or kind == "ai":
        return "ai_reconstruction"
    if card:
        k = card.get("kind")
        if k in TEXT_KINDS:
            return "text_card"
        if k in GRAPHIC_KINDS:
            return "map_diagram"
        return card.get("fields", {}).get("evidence_kind") or "manuscript_document"   # framed_object
    if kind == "map":
        return "map_diagram"
    if kind == "artwork":
        return "historical_artwork"
    if kind == "document":
        return "manuscript_document"
    return "real_world_location"


def evidence_relation(meta, category: str, claim_status: Optional[Dict[str, str]] = None) -> str:
    claim_status = claim_status or {}
    if category == "ai_reconstruction":
        return "reconstruction"
    if category == "unresolved":
        return "none"
    if category == "text_card":
        statuses = {claim_status.get(c, "") for c in (_get(meta, "claim_ids") or [])}
        return "interpretation" if statuses & {"interpretation", "disputed"} else "narration_text"
    card = _get(meta, "card") or {}
    if category == "map_diagram":
        if card.get("kind") == "source_excerpt" and card.get("fields", {}).get("mode") == "quotation":
            return "direct_evidence"
        return "illustration"
    if category == "historical_artwork":
        return "illustration"
    if category == "manuscript_document":
        return "illustration" if _get(meta, "reason") == "context" else "direct_evidence"
    return "direct_evidence" if _get(meta, "reason") in ("names", "proves", "locates", "shows_person") else "illustration"


def _shares(cats: Sequence[str]) -> dict:
    n = len(cats)
    counts = {c: cats.count(c) for c in CATEGORIES + ("unresolved",)}
    return {"scenes": n, "counts": counts, "shares": {c: (round(counts[c] / n, 4) if n else 0.0) for c in counts}}


def _runs(cats: Sequence[str], target: str) -> List[List[int]]:
    out, cur = [], []
    for i, c in enumerate(cats):
        if c == target:
            cur.append(i)
        else:
            if cur:
                out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


def evaluate_mix(cats: Sequence[str], scene_ids: Sequence[int], targets: dict, *, label: str) -> List[Issue]:
    """Soft findings about balance. Never hard: balance is a style target, not a correctness rule."""
    issues: List[Issue] = []
    n = len(cats)
    if not n:
        return issues
    text = cats.count("text_card") / n
    t = targets.get("text_card", {})
    lo, hi = (t.get("target") or [0.15, 0.20])
    w1, w2 = (t.get("warn") or [0.25, 0.30])
    if text > w2:
        issues.append(Issue("text_cards_far_above_target", "soft", f"{label}: standalone text cards are {text:.0%} of scenes "
                            f"(target {lo:.0%}-{hi:.0%}, strong warning above {w2:.0%}); the script names little that can be shown",
                            label))
    elif text > w1:
        issues.append(Issue("text_cards_above_warning", "soft", f"{label}: standalone text cards are {text:.0%} of scenes "
                            f"(target {lo:.0%}-{hi:.0%}, warning above {w1:.0%})", label))
    elif text > hi:
        issues.append(Issue("text_cards_above_target", "soft", f"{label}: standalone text cards are {text:.0%} of scenes "
                            f"(target {lo:.0%}-{hi:.0%})", label))
    ai_max = (targets.get("ai_reconstruction") or {}).get("max")
    ai = cats.count("ai_reconstruction") / n
    if ai_max is not None and ai > ai_max:
        issues.append(Issue("ai_share_above_ceiling", "soft", f"{label}: AI reconstructions are {ai:.0%} of scenes (ceiling {ai_max:.0%})",
                            label))
    run_cfg = targets.get("consecutive_text_cards") or {}
    warn_run, strong = int(run_cfg.get("warn_run", 2)), int(run_cfg.get("strong_run", 3))
    for run in _runs(cats, "text_card"):
        if len(run) >= warn_run:
            ids = f"{scene_ids[run[0]]}-{scene_ids[run[-1]]}"
            issues.append(Issue("consecutive_text_cards", "soft",
                                f"{label}: {len(run)} text cards in a row (scenes {ids})"
                                + (" -- the picture stops changing in kind" if len(run) >= strong else ""), str(scene_ids[run[0]])))
    return issues


# ---------------------------------------------------------------- planned

def planned_mix(metas: Sequence, *, ledger=None, targets: Optional[dict] = None) -> dict:
    """The mix the plan intends (after the refine pass). A card planned but not installed is 'unresolved'."""
    targets = targets or DEFAULT_TARGETS
    statuses = {cid: c.status for cid, c in (ledger.claims.items() if ledger is not None else [])}
    cats = [classify(m) for m in metas]
    scenes = []
    for m, c in zip(metas, cats):
        scenes.append({"scene": int(_get(m, "scene")), "category": c, "evidence": evidence_relation(m, c, statuses)})
    ids = [int(_get(m, "scene")) for m in metas]
    issues = evaluate_mix(cats, ids, targets, label="planned")
    queries: Dict[str, List[int]] = {}
    for m, c in zip(metas, cats):
        q = (_get(m, "query") or "").strip().lower()
        if c in ("historical_artwork", "manuscript_document", "real_world_location") and q and not _get(m, "card"):
            queries.setdefault(q, []).append(int(_get(m, "scene")))
    for q, scs in queries.items():
        if len(scs) > 1 and not all(_get(metas[ids.index(s)], "motif") for s in scs):
            issues.append(Issue("repeated_imagery", "soft", f"planned: the search {q!r} is used by scenes {scs} (likely the same picture)",
                                str(scs[0])))
    return {**_shares(cats), "scenes_detail": scenes, "evidence_counts": _evidence_counts(scenes), "issues": [i.to_dict() for i in issues]}


def _evidence_counts(scenes: Iterable[dict]) -> dict:
    out = {e: 0 for e in EVIDENCE + ("none",)}
    for s in scenes:
        out[s["evidence"]] = out.get(s["evidence"], 0) + 1
    return out


# ---------------------------------------------------------------- actual

def scene_file(images_dir: Path, n: int) -> Optional[Path]:
    for stem in (f"{n}", f"{n:02d}", f"{n:03d}", f"{n:04d}"):
        for ext in SCENE_EXTS:
            for cand in (Path(images_dir) / f"{stem}{ext}", Path(images_dir) / f"{stem}{ext.upper()}"):
                if cand.is_file():
                    return cand
    return None


def load_provenance(images_dir: Path, state_dir: Optional[Path] = None) -> Dict[int, str]:
    """Where each scene's file came from: the app's download manifest (source per scene), overridden by the project's own
    declaration state/enoch_template/asset_provenance.json ({"14": "ai_generated", "3": "map_render", ...}) for files the
    user placed by hand. Unknown provenance is simply absent."""
    out: Dict[int, str] = {}
    mf = Path(images_dir) / ".asset_manifest.json"
    if mf.is_file():
        try:
            for k, r in json.loads(mf.read_text(encoding="utf-8")).items():
                if isinstance(r, dict) and r.get("status") == "complete" and r.get("source"):
                    out[int(k)] = str(r["source"])
        except (OSError, ValueError, json.JSONDecodeError):
            pass
    if state_dir is not None and (Path(state_dir) / "asset_provenance.json").is_file():
        try:
            for k, v in json.loads((Path(state_dir) / "asset_provenance.json").read_text(encoding="utf-8")).items():
                out[int(k)] = str(v)
        except (OSError, ValueError, json.JSONDecodeError):
            pass
    return out


def actual_mix(images_dir, metas: Sequence, *, provenance: Optional[Dict[int, str]] = None, ledger=None,
               targets: Optional[dict] = None) -> dict:
    """The mix of what is really there: one file per scene in the project's Images folder. A scene without a file is
    'unresolved' (and a hard 'missing_asset'); a file whose provenance is AI is an AI reconstruction whatever the plan
    said (a mislabel is reported); identical files across scenes are reported as repeated imagery."""
    targets = targets or DEFAULT_TARGETS
    provenance = provenance or {}
    statuses = {cid: c.status for cid, c in (ledger.claims.items() if ledger is not None else [])}
    issues: List[Issue] = []
    cats, scenes, hashes = [], [], {}
    for m in metas:
        n = int(_get(m, "scene"))
        f = scene_file(Path(images_dir), n)
        prov = provenance.get(n, "")
        planned = classify(m)
        if f is None:
            cat = "unresolved"
            issues.append(Issue("missing_asset", "hard", f"scene {n}: no file for the scene in the Images folder; nothing is "
                                "substituted", str(n)))
        else:
            ai = prov.lower() in AI_SOURCES
            cat = classify(m, ai_provenance=ai)
            card = _get(m, "card") or {}
            if card.get("installed") and card.get("sha256"):
                if hashlib.sha256(f.read_bytes()).hexdigest()[:16] != card["sha256"]:
                    issues.append(Issue("card_file_replaced", "review", f"scene {n}: the file is not the card the plan installed "
                                        "(replaced by hand?); check what it shows", str(n)))
            if ai and planned not in ("ai_reconstruction", "unresolved"):
                issues.append(Issue("ai_label_mismatch", "hard", f"scene {n}: the picture is AI-generated ({prov}) but the plan "
                                    f"labels it {planned}; it must be presented as a reconstruction", str(n)))
            if not ai and planned == "ai_reconstruction" and prov and prov.lower() not in ("local", "manual", ""):
                issues.append(Issue("source_label_mismatch", "review", f"scene {n}: planned as an AI reconstruction but the file "
                                    f"came from {prov}", str(n)))
            if not prov and not card.get("installed") and planned != "map_diagram":
                issues.append(Issue("provenance_unknown", "review", f"scene {n}: no record of where {f.name} came from", str(n)))
            hashes.setdefault(hashlib.sha256(f.read_bytes()).hexdigest(), []).append(n)
        cats.append(cat)
        scenes.append({"scene": n, "category": cat, "evidence": evidence_relation(m, cat, statuses),
                       "file": f.name if f is not None else None, "provenance": prov or None})
    for h, scs in hashes.items():
        if len(scs) > 1:
            issues.append(Issue("repeated_imagery", "soft", f"actual: scenes {scs} show the identical file", str(scs[0])))
    ids = [int(_get(m, "scene")) for m in metas]
    issues += evaluate_mix(cats, ids, targets, label="actual")
    return {**_shares(cats), "scenes_detail": scenes, "evidence_counts": _evidence_counts(scenes),
            "issues": [i.to_dict() for i in issues]}
