"""The style's refine pass on a VisualPlan (the same object both planning paths produce): one pass, run last.

For every scene it records WHY the picture is there (a reason tied to words in that scene's narration) and fixes what the
style's rules require, using only relevant material:

  * AI ceiling and run limit, as a configurable style setting (selection_rules.max_ai_share / max_ai_run). The denominator
    is every visual scene of the plan. An AI scene over the limit is replaced, in this order, by: a real artwork known to
    show the narrated subject -> a real document/place search named by the narration -> a verified-quotation card ->
    a card the user asked for -> a statement card of the narration's own words. When none fits, the scene stays AI and is
    reported (never replaced by unrelated stock to meet the number). The resulting share is reported, met or not.
  * Relevance: a search whose query shares nothing with its narration is re-aimed at what the narration names (a motif or
    a style search term); with nothing to aim at, it is flagged, not filled.
  * Motifs: a recurring document or object may reuse its anchor search deliberately; other repeats are reported.

Cost: it can only REMOVE Flow work (assertion at the end); it adds no provider call, no network, no generation.
"""

from __future__ import annotations

import dataclasses
import hashlib
import re
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from . import language as L
from .cards import CardError, CardSpec, render as render_card, validate as validate_card
from .claims import Ledger, quote_for_card
from .framework import ScriptMap
from .issues import Issue
from .subjects import SubjectPack, has_term

AI_TYPES = frozenset({"image", "video", "flow_image", "flow_video"})
SEARCH_TYPES = frozenset({"stock_video", "stock_image", "stock", "archive_video", "youtube_video", "nasa_video",
                          "commons_image", "commons_video"})
FOOTAGE_TYPES = frozenset({"stock_video", "stock", "archive_video", "youtube_video", "nasa_video", "commons_video"})
ART_WORDS = ("engraving", "painting", "drawing", "icon", "mosaic", "fresco", "illumination", "woodcut", "etching", "plate")
REASONS = ("names", "proves", "locates", "shows_person", "compares", "illustrates", "quotes", "reconstructs", "emphasizes",
           "sections", "user_file", "context")
GENERATION_PROMPT_WORDS = 14       # a "search" longer than this is a generation prompt, not something an archive can answer
SCENE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi")
_PROPER = re.compile(r"(?<![.!?¿¡]\s)(?<!^)\b([A-ZÁÉÍÓÚÑÄÖÜ][\w'’-]{3,})")


@dataclasses.dataclass
class SceneMeta:
    scene: int
    reason: str
    source_kind: str            # ai | document | artwork | real_world | card | map | local | context
    anchors: List[str]
    query: str = ""
    motif: str = ""
    claim_ids: List[str] = dataclasses.field(default_factory=list)
    card: Optional[dict] = None            # an INSTALLED card (the scene's picture)
    planned_card: Optional[dict] = None    # a card that could not be installed (no Images folder): the scene kept its source
    ai_justification: str = ""
    change: str = ""
    category: str = ""          # primary visual type (visual_mix.classify)
    evidence: str = ""          # direct_evidence | illustration | interpretation | reconstruction | narration_text            # what the refine pass did to this scene, if anything

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclasses.dataclass
class RefineResult:
    scenes: List[SceneMeta]
    issues: List[Issue]
    report: dict

    def to_dict(self) -> dict:
        return {"scenes": [s.to_dict() for s in self.scenes], "issues": [i.to_dict() for i in self.issues], "report": self.report}


# ---------------------------------------------------------------- helpers

def flow_counts(plan) -> Dict[str, int]:
    return {"ai_scenes": sum(1 for s in plan.scenes if (s.asset_type or "") in AI_TYPES),
            "flow_fallbacks": sum(1 for s in plan.scenes if (s.asset_type or "") not in AI_TYPES
                                  and any(str(f) in ("flow_video", "flow_image", "video", "image") for f in (s.fallbacks or [])))}


def _query(scene) -> str:
    if scene.search_queries:
        return str(scene.search_queries[0])
    return str(scene.visual_description or "")


def anchors_for(text: str, pack: Optional[SubjectPack], style) -> List[str]:
    """What the narration names: the pack's subject/document/place words, the style's real subjects, figures and their
    aliases, scholars, and proper names. Order kept, duplicates removed."""
    out: List[str] = []

    def add(t: str) -> None:
        if t and t.lower() not in (x.lower() for x in out):
            out.append(t)

    if pack is not None:
        for t in pack.subject_terms + pack.document_terms + pack.place_terms:
            if has_term(text, t):
                add(t)
        for s in pack.scholars:
            for n in s.names:
                if has_term(text, n):
                    add(s.name)
    if style is not None:
        for t in style.selection_rules.real_subjects:
            if has_term(text, t):
                add(t)
        for e in style.entities or []:
            for n in [e.get("name", "")] + list(e.get("aliases") or []):
                if n and has_term(text, n) and not any(has_term(text, x) for x in (e.get("not_when") or [])):
                    add(str(e.get("name")))
    for m in _PROPER.finditer(text or ""):
        add(m.group(1))
    return out


def _relevant(query: str, narration: str, anchors: Sequence[str], artwork_queries: Sequence[str]) -> bool:
    q = (query or "").lower()
    if not q:
        return False
    if q in (a.lower() for a in artwork_queries):
        return True
    if any(a.lower() in q for a in anchors):
        return True
    nw = {w for w in L.words(narration) if len(w) > 3}
    qw = {w for w in L.words(query) if len(w) > 3}
    return len(nw & qw) >= 2


def _artwork_for(narration: str, style) -> Optional[str]:
    low = (narration or "").lower()
    for a in (style.selection_rules.artworks if style is not None else []):
        if any(str(m).lower() in low for m in (a.get("match") or [])):
            return str(a["query"])
    return None


def _real_query(narration: str, anchors: Sequence[str], pack: Optional[SubjectPack], style) -> Tuple[str, str]:
    """(query, motif id) for a real document/place/object the narration names, or ("", "")."""
    if pack is not None:
        for m in pack.anchor_motifs:
            if m.kind in ("document", "place") and any(has_term(narration, t) for t in m.concept_terms):
                return m.query, m.id
    if style is not None:
        for t in style.search_guidance.prefer_terms:
            if has_term(narration, t):
                return t, ""
    if pack is not None:
        for t in pack.place_terms + pack.document_terms:
            if has_term(narration, t) and t in (a.lower() for a in anchors):
                subj = next((s for s in anchors if s.lower() in pack.subject_terms), "")
                return (f"{t} {subj}".strip(), "")
    return "", ""


def _statement_phrase(narration: str) -> str:
    """The narration's own words, short enough for a statement card: its shortest sentence or clause of 3-14 words."""
    parts = [p.strip(" ,;:") for p in re.split(r"(?<=[.!?…;:])\s+|,\s+", narration or "") if p.strip(" ,;:")]
    fits = [p for p in parts if 3 <= len(p.split()) <= 14]
    if not fits:
        return ""
    phrase = min(fits, key=lambda p: (abs(len(p.split()) - 7), parts.index(p)))
    return phrase.replace('"', "").replace("«", "").replace("»", "").replace("“", "").replace("”", "")


def _scene_stems(n: int) -> List[str]:
    return [f"{n}", f"{n:02d}", f"{n:03d}", f"{n:04d}"]


def card_conflict(images_dir: Path, scene_number: int, new_bytes: Optional[bytes] = None) -> Optional[Path]:
    """Another file the renderer could take as this scene's source (any numbering, any media extension) -- installing a
    card next to it would leave the renderer picking one of them by extension order, so it is a conflict to report."""
    for stem in _scene_stems(scene_number):
        for ext in SCENE_EXTS:
            for cand in (Path(images_dir) / f"{stem}{ext}", Path(images_dir) / f"{stem}{ext.upper()}"):
                if cand.is_file():
                    if new_bytes is not None and cand.name == f"{scene_number:03d}.png" and cand.read_bytes() == new_bytes:
                        continue
                    return cand
    return None


def _claims_for_scene(narration: str, smap: Optional[ScriptMap]) -> List[str]:
    if smap is None:
        return []
    n = L.normalize_text(narration).lower()
    out: List[str] = []
    for s in smap.sentences:
        t = L.normalize_text(s.text).lower()
        if n and t and (n in t or t in n):
            for c in s.claim_ids:
                if c not in out:
                    out.append(c)
    return out


def _source_kind(scene, query: str, pack: Optional[SubjectPack], style, art_queries: Sequence[str]) -> str:
    at = (scene.asset_type or "").lower()
    if at in AI_TYPES:
        return "ai"
    if at == "map":
        return "map"
    if at in ("local", "local_video", "local_image"):
        return "local"
    q = (query or "").lower()
    if q in (a.lower() for a in art_queries) or any(w in q for w in ART_WORDS):
        return "artwork"
    doc_terms = (pack.document_terms if pack else ()) + tuple(t.lower() for t in (style.selection_rules.real_subjects if style else ()))
    if any(has_term(q, t) for t in doc_terms) or (pack is not None and any(
            has_term(q, t) for m in pack.anchor_motifs if m.kind == "document" for t in m.concept_terms)):
        return "document"
    return "real_world"


def _reason(kind: str, narration: str, query: str, anchors: Sequence[str], pack: Optional[SubjectPack], claim_ids) -> str:
    if kind == "ai":
        return "reconstructs"
    if kind == "map":
        return "locates"
    if kind == "artwork":
        return "illustrates"
    if kind == "local":
        return "user_file"
    if pack is not None:
        sch = pack.scholar_for(narration)
        if sch is not None and any(has_term(query, n) for n in sch.names):
            return "shows_person"
        if any(has_term(narration, t) and has_term(query, t) for t in pack.place_terms):
            return "locates"
    if kind == "document":                    # direct evidence only when the picture is of something the narration names
        if any(a.lower() in (query or "").lower() for a in anchors) or \
                (pack is not None and any(has_term(narration, t) and has_term(query, t) for t in pack.document_terms)):
            return "proves" if claim_ids else "names"
        return "context"
    if anchors and any(a.lower() in (query or "").lower() for a in anchors):
        return "names"
    return "context"


# ---------------------------------------------------------------- the pass

def refine_plan(plan, *, style, pack: Optional[SubjectPack] = None, ledger: Optional[Ledger] = None, mix_targets: Optional[dict] = None,
                script_map: Optional[ScriptMap] = None, card_requests: Optional[Dict[int, dict]] = None,
                images_dir: Optional[Path] = None, card_size: Tuple[int, int] = (1920, 1080),
                ai_ceiling: Optional[float] = None, max_ai_run: Optional[int] = None,
                csv_rows: Optional[Sequence[dict]] = None) -> RefineResult:
    """Refine `plan` in place (asset types, search queries) and return what was decided and why.

    images_dir: where card PNGs are installed as the scene's numbered file (the project's Images folder). Without it,
    cards are planned (spec recorded) but not installed, and the scene keeps its previous source.
    csv_rows: the imported CSV as written (CSV path only). Where the CSV chose a real (non-AI) source and an earlier step
    replaced it (the asset mix's provider quotas, or the CSV-to-plan conversion that turns map/archive/commons rows into
    stock video), the CSV's own choice is restored: in this style the plan's evidence choice wins. Only non-AI sources are
    restored, so this can never add Flow work.
    """
    before = flow_counts(plan)
    restored = _restore_csv_sources(plan, csv_rows) if csv_rows else {}
    issues: List[Issue] = []
    rules = style.selection_rules if style is not None else None
    ceiling = ai_ceiling if ai_ceiling is not None else (rules.max_ai_share if rules and rules.max_ai_share is not None else 1.0)
    run_limit = max_ai_run if max_ai_run is not None else (rules.max_ai_run if rules and rules.max_ai_run is not None else None)
    art_queries = [str(a["query"]) for a in (rules.artworks if rules else [])]
    requests = {int(k): v for k, v in (card_requests or {}).items()}
    metas: List[SceneMeta] = []

    # 1. reasons, relevance, motifs, requested cards
    prev_query = ""
    for sc in plan.scenes:
        nar = sc.narration or ""
        anchors = anchors_for(nar, pack, style)
        claim_ids = _claims_for_scene(nar, script_map)
        q = _query(sc)
        meta = SceneMeta(scene=int(sc.scene_id), reason="", source_kind="", anchors=anchors, query=q, claim_ids=claim_ids,
                         change=restored.get(int(sc.scene_id), ""))
        at = (sc.asset_type or "").lower()
        if at in SEARCH_TYPES:
            avoid = [t for t in (style.search_guidance.avoid_terms if style else []) if has_term(q, t)]
            generation_prompt = len(q.split()) > GENERATION_PROMPT_WORDS   # an AI prompt being used as a search
            if avoid or generation_prompt or not _relevant(q, nar, anchors, art_queries):
                new_q, motif = _real_query(nar, anchors, pack, style)       # existing evidence first: the document or place
                art = None
                if not new_q or new_q == prev_query:                        # then a historical depiction of the subject
                    art = _artwork_for(nar, style)
                    if art and art != prev_query:
                        new_q, motif = art, ""
                    else:
                        art = None
                if new_q and new_q == prev_query:
                    new_q = ""
                if new_q and new_q != q:
                    sc.search_queries = [new_q]
                    if (art or motif) and at in FOOTAGE_TYPES:         # a painting, engraving or document is a still
                        sc.asset_type, sc.provider_preference = "stock_image", "stock_image"
                    meta.change = f"search re-aimed at what the narration names: {q[:60]!r} -> {new_q!r}" + \
                                  (f" (dropped avoided term {avoid})" if avoid else "")
                    meta.query, meta.motif = new_q, motif
                elif generation_prompt and not avoid:
                    phrase = _statement_phrase(nar)
                    explanatory = _explanatory_card(meta, ledger, str(sc.scene_id))
                    spec = CardSpec("statement", {"phrase": phrase}, scene=str(sc.scene_id)) if phrase else None
                    done = explanatory is not None and _apply_card(sc, meta, explanatory, ledger, images_dir, card_size, issues,
                                                                   why="a generation prompt was being used as a search; cited card")
                    if not done and (spec is None or not _apply_card(sc, meta, spec, ledger, images_dir, card_size, issues,
                                                                     why="a generation prompt was being used as a search")):
                        short = " ".join(q.split()[:8])
                        sc.search_queries = [short]
                        meta.query = short
                        meta.change = f"generation prompt shortened to a search: {short!r}"
                        issues.append(Issue("generation_prompt_as_search", "review",
                                            f"scene {sc.scene_id}: a {len(q.split())}-word generation prompt was set as a "
                                            f"search; shortened to {short!r} -- check the picture", str(sc.scene_id)))
                elif avoid:
                    issues.append(Issue("avoided_term_in_query", "hard",
                                        f"scene {sc.scene_id}: query uses an avoided term {avoid} and the narration names "
                                        "nothing to search instead", str(sc.scene_id)))
                else:
                    issues.append(Issue("query_not_tied_to_narration", "review",
                                        f"scene {sc.scene_id}: the search {q!r} shares nothing with its narration and the "
                                        "narration names nothing searchable; check the picture fits", str(sc.scene_id)))
            if not meta.motif and pack is not None:
                for m in pack.anchor_motifs:
                    if meta.query == m.query:
                        meta.motif = m.id
        prev_query = (sc.search_queries or [""])[0] if (sc.asset_type or "").lower() in SEARCH_TYPES else ""
        if sc.scene_id in requests:
            spec = CardSpec(kind=str(requests[sc.scene_id].get("kind") or ""),
                            fields={k: str(v) for k, v in (requests[sc.scene_id].get("fields") or {}).items()},
                            claim_ids=tuple(requests[sc.scene_id].get("claim_ids") or ()), scene=str(sc.scene_id))
            _apply_card(sc, meta, spec, ledger, images_dir, card_size, issues, why="requested card")
        metas.append(meta)

    # 2. AI ceiling (denominator: every visual scene in the plan)
    def is_ai(i: int) -> bool:
        return (plan.scenes[i].asset_type or "").lower() in AI_TYPES

    eligible = len(plan.scenes)
    allowed = int(eligible * float(ceiling) + 1e-9)
    ai_idx = [i for i in range(eligible) if is_ai(i)]
    no_alternative: List[int] = []

    def needs_reconstruction(i: int) -> int:
        sc, meta = plan.scenes[i], metas[i]
        named_figure = any(a in [str(e.get("name")) for e in (style.entities if style else [])] for a in meta.anchors)
        real = bool(_real_query(sc.narration or "", meta.anchors, pack, style)[0]) or bool(_artwork_for(sc.narration or "", style))
        return (2 if named_figure else 0) + (0 if real else 1)

    if len(ai_idx) > allowed:
        keep = set(sorted(ai_idx, key=lambda i: (-needs_reconstruction(i), i))[:allowed])
        for i in ai_idx:
            if i in keep:
                continue
            if not _replace_ai(plan.scenes[i], metas[i], pack, style, ledger, requests, images_dir, card_size, issues,
                               neighbour_queries=_neighbour_queries(plan, i)):
                no_alternative.append(i)

    # 3. run limit
    if run_limit is not None:
        i = 0
        while i < eligible:
            if not is_ai(i):
                i += 1
                continue
            j = i
            while j < eligible and is_ai(j):
                j += 1
            run = list(range(i, j))
            while len(run) > run_limit:
                order = sorted(run, key=lambda k: (abs(k - (run[0] + run[-1]) / 2), k))
                fixed = None
                for k in order:
                    if k in no_alternative:
                        continue
                    if _replace_ai(plan.scenes[k], metas[k], pack, style, ledger, requests, images_dir, card_size, issues,
                                   neighbour_queries=_neighbour_queries(plan, k)):
                        fixed = k
                        break
                    no_alternative.append(k)
                if fixed is None:
                    issues.append(Issue("ai_run_exceeded", "hard", f"scenes {plan.scenes[run[0]].scene_id}-{plan.scenes[run[-1]].scene_id}: "
                                        f"{len(run)} AI shots in a row (limit {run_limit}) and no relevant non-AI picture for any",
                                        str(plan.scenes[run[0]].scene_id)))
                    break
                left, right = [k for k in run if k < fixed], [k for k in run if k > fixed]
                run = max(left, right, key=len)
            i = j

    # 4. final reasons and kinds
    for sc, meta in zip(plan.scenes, metas):
        q = _query(sc)
        if meta.card is None:
            meta.query = q
            meta.source_kind = _source_kind(sc, q, pack, style, art_queries)
            meta.reason = _reason(meta.source_kind, sc.narration or "", q, meta.anchors, pack, meta.claim_ids)
        if meta.source_kind == "ai":
            meta.ai_justification = meta.ai_justification or (
                "reconstruction of what no camera or painter recorded" if needs_reconstruction(plan.scenes.index(sc)) >= 1
                else "kept as AI within the ceiling")
            issues.append(Issue("reconstruction", "review", f"scene {sc.scene_id}: AI reconstruction -- check it does not read "
                                "as documentary evidence", str(sc.scene_id)))
        if meta.reason == "context":
            issues.append(Issue("context_shot", "review", f"scene {sc.scene_id}: atmosphere/context picture, not tied to a "
                                "named subject", str(sc.scene_id)))

    # 5. repeats
    times, t = [], 0.0
    for sc in plan.scenes:
        times.append(t)
        t += float(sc.duration or 3.0)
    by_query: Dict[str, List[int]] = {}
    for i, meta in enumerate(metas):
        if meta.source_kind in ("document", "artwork", "real_world") and meta.query:
            by_query.setdefault(meta.query.lower(), []).append(i)
    for q, idxs in by_query.items():
        motif = metas[idxs[0]].motif
        for a, b in zip(idxs, idxs[1:]):
            gap = times[b] - times[a]
            if motif:
                if gap < 45.0:
                    issues.append(Issue("motif_too_close", "soft", f"motif {motif} returns after {gap:.0f}s (scenes "
                                        f"{plan.scenes[a].scene_id}->{plan.scenes[b].scene_id}); spacing target ≥45 s",
                                        str(plan.scenes[b].scene_id)))
            elif gap < 180.0:
                issues.append(Issue("repeated_search", "soft", f"the search {q!r} repeats after {gap:.0f}s (scenes "
                                    f"{plan.scenes[a].scene_id}->{plan.scenes[b].scene_id}) without being a motif",
                                    str(plan.scenes[b].scene_id)))
        if motif and len(idxs) > 4:
            issues.append(Issue("motif_overused", "soft", f"motif {motif} used {len(idxs)} times (target ≤4)", motif))

    after = flow_counts(plan)
    if after["ai_scenes"] > before["ai_scenes"] or after["flow_fallbacks"] > before["flow_fallbacks"]:
        raise AssertionError(f"refine_plan added Flow work: {before} -> {after}")

    kinds = [m.source_kind for m in metas]
    ai_n = kinds.count("ai")
    statement_n = sum(1 for m in metas if m.card and m.card.get("kind") == "statement")
    report = {
        "eligible_visual_scenes": eligible,
        "ai_scenes": ai_n,
        "documentary_source_imagery": kinds.count("document"),
        "designed_cards": kinds.count("card"),
        "historical_art": kinds.count("artwork"),
        "real_world_footage": kinds.count("real_world"),
        "maps": kinds.count("map"),
        "local_files": kinds.count("local"),
        "context_shots": sum(1 for m in metas if m.reason == "context"),
        "scenes_with_no_non_ai_alternative": [int(plan.scenes[i].scene_id) for i in sorted(set(no_alternative)) if is_ai(i)],
        "ai_share": round(ai_n / eligible, 4) if eligible else 0.0,
        "ai_ceiling": float(ceiling),
        "ai_allowed": allowed,
        "ai_ceiling_met": ai_n <= allowed,
        "max_ai_run_limit": run_limit,
        "max_ai_run_observed": _max_run([k == "ai" for k in kinds]),
        "flow_before": before,
        "flow_after": after,
        "statement_cards": statement_n,
    }
    if not report["ai_ceiling_met"]:
        issues.append(Issue("ai_ceiling_not_met", "hard",
                            f"{ai_n} AI scene(s) of {eligible} ({report['ai_share']:.0%}); ceiling {ceiling:.0%} allows {allowed}. "
                            f"No relevant non-AI picture for scenes {report['scenes_with_no_non_ai_alternative']}",
                            "plan"))
    from .visual_mix import planned_mix

    mix = planned_mix(metas, ledger=ledger, targets=mix_targets)
    for detail, meta in zip(mix["scenes_detail"], metas):
        meta.category, meta.evidence = detail["category"], detail["evidence"]
    report["planned_mix"] = {k: mix[k] for k in ("counts", "shares", "evidence_counts")}
    issues.extend(Issue(**i) for i in mix["issues"])
    return RefineResult(scenes=metas, issues=issues, report=report)


def _restore_csv_sources(plan, rows: Sequence[dict]) -> Dict[int, str]:
    from visual_director.schema import ASSET_TYPE_TO_PROVIDER

    by_num: Dict[int, dict] = {}
    for r in rows:
        try:
            by_num[int(str(r.get("scene_number") or "").strip())] = r
        except ValueError:
            continue
    out: Dict[int, str] = {}
    for sc in plan.scenes:
        r = by_num.get(int(sc.scene_id))
        if r is None:
            continue
        at = str(r.get("asset_type") or "").strip().lower()
        prompt = str(r.get("prompt") or "").strip()
        if not at or not prompt or at in AI_TYPES or at.startswith("flow") or at.startswith("local"):
            continue
        queries = [] if at == "map" else [q.strip() for q in prompt.split("||") if q.strip()]
        if (sc.asset_type or "").lower() == at and (at == "map" or list(sc.search_queries or [])[:1] == queries[:1]):
            continue
        prev = sc.asset_type
        sc.asset_type = at
        sc.provider_preference = ASSET_TYPE_TO_PROVIDER.get(at, at)
        sc.visual_description = prompt
        sc.search_queries = queries
        sc.fallbacks = [f for f in (sc.fallbacks or []) if f not in ("flow_video", "flow_image", "video", "image")]
        out[int(sc.scene_id)] = f"kept the CSV's own source ({at}: {prompt[:50]!r}); an earlier step had changed it to {prev}"
    return out


def _explanatory_card(meta: SceneMeta, ledger, scene: str) -> Optional[CardSpec]:
    """A card that explains with a source: a verified quotation, else a summary of a DOCUMENTED claim linked to this
    scene, shown with its citation and locator and marked 'Summary'. Never a credential, never unsourced text."""
    if ledger is None:
        return None
    from .claims import _supporting

    for cid in meta.claim_ids:
        q = quote_for_card(ledger, cid)
        if q:
            return CardSpec("source_excerpt", {"text": q[0], "citation": q[2], "locator": q[3], "mode": "quotation"},
                            claim_ids=(cid,), scene=scene)
    for cid in meta.claim_ids:
        c = ledger.claims.get(cid)
        if c is None or c.status != "documented" or len(c.text) > 300:
            continue
        sup = _supporting(ledger, c)
        if sup:
            src = ledger.sources[sup[0].source_id]
            return CardSpec("source_excerpt", {"text": c.text.replace('"', "").replace("“", "").replace("”", ""),
                                               "citation": src.citation[:140], "locator": sup[0].locator[:60], "mode": "summary"},
                            claim_ids=(cid,), scene=scene)
    return None


def _neighbour_queries(plan, i: int) -> List[str]:
    out = []
    for j in (i - 1, i + 1):
        if 0 <= j < len(plan.scenes) and (plan.scenes[j].asset_type or "").lower() in SEARCH_TYPES and plan.scenes[j].search_queries:
            out.append(plan.scenes[j].search_queries[0])
    return out


def _max_run(flags: Sequence[bool]) -> int:
    best = cur = 0
    for f in flags:
        cur = cur + 1 if f else 0
        best = max(best, cur)
    return best


def _apply_card(sc, meta: SceneMeta, spec: CardSpec, ledger, images_dir, size, issues: List[Issue], *, why: str) -> bool:
    vq = None
    if spec.kind == "source_excerpt" and spec.fields.get("mode") == "quotation":
        vq = next((quote_for_card(ledger, c) for c in spec.claim_ids if ledger is not None and quote_for_card(ledger, c)), None)
    problems = [i for i in validate_card(spec, verified_quote=vq) if i.severity == "hard"]
    if problems:
        issues.extend(problems)
        return False
    if images_dir is None:
        meta.planned_card = {"kind": spec.kind, "fields": dict(spec.fields)}
        issues.append(Issue("card_not_installed", "review", f"scene {sc.scene_id}: {spec.kind} card planned but no Images "
                            "folder was given, so the scene keeps its previous source", str(sc.scene_id)))
        return False
    n = int(sc.scene_id)
    target = Path(images_dir) / f"{n:03d}.png"
    try:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            probe = render_card(spec, Path(tmp) / "card.png", size, verified_quote=vq)
            data = probe.read_bytes()
    except CardError as exc:
        issues.append(Issue("card_render_failed", "hard" if why == "requested card" else "review",
                            f"scene {sc.scene_id}: {spec.kind} card: {exc}", str(sc.scene_id)))
        return False
    conflict = card_conflict(Path(images_dir), n, data)
    if conflict is not None:
        issues.append(Issue("card_conflicts_with_existing_file", "review",
                            f"scene {sc.scene_id}: {conflict.name} already exists; the card was not installed so the renderer "
                            "cannot pick a stale file. Remove it (or re-import) to use the card.", str(sc.scene_id)))
        return False
    Path(images_dir).mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    prev = sc.asset_type
    sc.asset_type = "local"            # the scene's numbered file in the project's Images folder (no Local Assets mode needed)
    sc.provider_preference = "local"
    sc.fallbacks = []
    sc.search_queries = []
    sc.visual_description = f"{spec.kind} card"
    meta.card = {"kind": spec.kind, "fields": dict(spec.fields), "installed": True, "path": target.name,
                 "sha256": hashlib.sha256(data).hexdigest()[:16]}
    meta.source_kind = "card"
    meta.reason = {"source_excerpt": "quotes", "framed_object": "names", "comparison": "compares",
                   "section_break": "sections", "statement": "emphasizes"}[spec.kind]
    meta.change = f"{why}: {prev} -> {spec.kind} card ({target.name})"
    return True


def _replace_ai(sc, meta: SceneMeta, pack, style, ledger, requests, images_dir, size, issues: List[Issue],
                neighbour_queries: Sequence[str] = ()) -> bool:
    """Swap one AI scene for the most relevant non-AI picture. False when nothing relevant exists."""
    nar = sc.narration or ""
    # 1. relevant existing evidence: the document or place the narration names, then a historical depiction of it
    query, motif = _real_query(nar, meta.anchors, pack, style)
    art = None
    if not query or query in neighbour_queries:
        art = _artwork_for(nar, style)
        query, motif = (art, "") if art else ("", "")
    if query and query in neighbour_queries:                       # never the same search as the scene next to it
        query, motif, art = "", "", None
    if query:
        prev = sc.asset_type
        sc.asset_type = "stock_image"
        sc.provider_preference = "stock_image"
        sc.search_queries = [query]
        sc.fallbacks = [f for f in (sc.fallbacks or []) if f not in ("flow_video", "flow_image", "video", "image")]
        meta.query, meta.motif = query, motif
        meta.change = f"AI over the style's limit -> real {'artwork' if art else 'source'} search {query!r} (was {prev})"
        return True
    # 2. a relevant explanatory graphic: a verified quotation, else a cited summary of a documented claim
    spec = _explanatory_card(meta, ledger, str(sc.scene_id))
    if spec is not None and _apply_card(sc, meta, spec, ledger, images_dir, size, issues,
                                        why="AI over the limit, " + ("verified quotation" if spec.fields.get("mode") == "quotation"
                                                                     else "cited summary card")):
        return True
    # 3. a labelled reconstruction is what is being replaced here (over the ceiling), so it is not available
    # 4. the narration's own words as a designed text card
    phrase = _statement_phrase(nar)
    if phrase:
        spec = CardSpec("statement", {"phrase": phrase}, scene=str(sc.scene_id))
        if _apply_card(sc, meta, spec, ledger, images_dir, size, issues, why="AI over the limit, the narration's own words"):
            return True
    return False
