"""ResearchAssetProvider: bridges the research/ package's ResearchResult
(already-downloaded, property-scoped media) into the existing AssetProvider
contract, so AssetManager can treat research media exactly like Archive/NASA
output — this file, not research/, is where the CSV/scene pipeline
boundary lives.

Ranking stays owned by the existing Smart Visual Selection machinery
(smart_selection_score / SelectionHistory / scene_has_manual_authority) —
this provider only pre-filters to unused, on-disk candidates and adds a
small boost from property_match_score/script_relevance on top of the
existing score, never a second ranking system.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import List, Optional

from providers.base import AssetProvider, AssetResult, AssetSource, LogFn, MediaType, SceneRow, SceneStatus
from research.models import MediaCandidate


class ResearchAssetProvider(AssetProvider):
    name = "research"
    source = AssetSource.RESEARCH

    def __init__(self, candidates: List[MediaCandidate], property_scope_by_scene: Optional[dict] = None):
        self.candidates = list(candidates)
        self.should_stop_scene = None
        self.resolved_style = None
        self.selection_history = None
        # scene_number -> property_id, produced by the Property Script
        # Analyzer and carried alongside the plan (never through the CSV —
        # the CSV schema is unchanged). Same sidecar pattern AssetManager
        # already uses for coverage_by_scene.
        self.property_scope_by_scene = dict(property_scope_by_scene or {})

    def property_id_for_scene(self, scene_number) -> str:
        key = str(scene_number).strip()
        scope = self.property_scope_by_scene
        return str(scope.get(key) or scope.get(key.lstrip("0") or key) or "")

    def _candidates_in_scope(self, scene_number) -> List[MediaCandidate]:
        """HARD property filter, applied BEFORE any ranking/scoring.

        A scene scoped to listing X may only ever see listing X's media.
        This is deliberately not a ranking penalty: no amount of quality or
        relevance may promote another listing's photo into this scene."""
        property_id = self.property_id_for_scene(scene_number)
        if not property_id:
            return list(self.candidates)
        return [c for c in self.candidates if (c.property_id or "") == property_id]

    def has_unused_candidates(self, scene_number=None) -> bool:
        pool = self.candidates if scene_number is None else self._candidates_in_scope(scene_number)
        return any(self._is_available(c) for c in pool)

    @staticmethod
    def _ensure_dimensions(candidate: MediaCandidate) -> None:
        """Smart Visual Selection's technical-quality gate rejects any
        candidate with no known width/height ("missing dimensions") unless
        the provider is on its hardcoded archival allowlist — which we
        deliberately don't touch (see module docstring: ranking stays
        owned by the existing scorer). The research engine normally already
        captures image dimensions at download time, but probe the file
        locally as a defensive fallback so a manifest gap never silently
        drops an otherwise-good photo."""
        if candidate.width and candidate.height:
            return
        if candidate.media_type != "image" or not candidate.local_path:
            return
        try:
            from PIL import Image

            with Image.open(candidate.local_path) as img:
                candidate.width, candidate.height = img.size
        except Exception:  # noqa: BLE001 - Pillow not installed, or not a real image
            pass

    @staticmethod
    def _is_available(candidate: MediaCandidate) -> bool:
        return bool(not candidate.used and candidate.local_path and Path(candidate.local_path).is_file())

    # ---- research-only validity + ranking -------------------------------
    # Authentic property media is judged on whether it is USABLE, not on
    # whether it clears a threshold designed for stock footage. A 316x234
    # photo of *this* property is the real thing; a pristine 4K photo of a
    # different property is worthless here. The existing scorer is still
    # called (unmodified) — but only to ORDER candidates, never to veto one.

    _SUPPORTED_MEDIA_TYPES = ("image", "video")
    _FATAL_DOWNLOAD_NOTES = ("download_failed", "perceptual_duplicate_of", "unexpected_mime_type")

    def _hard_validity_failure(self, candidate: MediaCandidate) -> Optional[str]:
        """The ONLY reasons a research candidate may be rejected.

        Deliberately excluded as rejection reasons: small dimensions,
        unknown dimensions, low quality tier (T3/T4), missing role_detail,
        a coarse role of "gallery", and a low semantic score. Those describe
        media that is merely modest or under-described — not media that is
        unusable."""
        if candidate.used:
            return "already used for another scene"
        if not candidate.local_path:
            return "no local file"
        path = Path(candidate.local_path)
        if not path.is_file():
            return "file missing or unreadable"
        try:
            if path.stat().st_size <= 0:
                return "zero-byte file"
        except OSError:
            return "file missing or unreadable"
        if (candidate.media_type or "").lower() not in self._SUPPORTED_MEDIA_TYPES:
            return f"unsupported media type ({candidate.media_type!r})"
        note = (candidate.download_note or "").lower()
        for fatal in self._FATAL_DOWNLOAD_NOTES:
            if note.startswith(fatal):
                return f"failed download/probe ({candidate.download_note})"
        return None

    @staticmethod
    def _tier_rank(candidate: MediaCandidate) -> int:
        """Lower is better. T1..T4 in order; unknown sorts with the weakest
        but is NEVER a rejection — "we could not measure it" is not "it is
        bad"."""
        tier = candidate.quality_tier
        if tier in (1, 2, 3, 4):
            return tier
        return 5

    @staticmethod
    def _role_rank(candidate: MediaCandidate, scene: SceneRow) -> int:
        """0 = role_detail directly matches what the scene asks for,
        1 = related/compatible, 2 = unknown, 3 = unrelated. Unknown ranks
        mid — never excluded."""
        detail = (candidate.role_detail or "").strip().lower()
        if not detail:
            return 2
        wanted = " ".join(filter(None, [
            scene.prompt or "", scene.stock or "",
            getattr(scene, "visual_description", "") or "",
            scene.script_segment or "",
        ])).lower()
        if not wanted:
            return 2
        if detail in wanted:
            return 0
        related = {
            "water": ("waterfront", "creek", "river", "pond", "lake", "dock"),
            "waterfront": ("water", "creek", "river", "pond", "lake", "dock"),
            # "structure" covers barn/shed/garage/silo/stable per the research
            # engine's _ROLE_PATTERNS — the related terms must too, or a
            # garage beat ties with every other outbuilding photo at rank 1.
            "structure": ("exterior", "cabin", "house", "home", "barn", "garage",
                          "shed", "outbuilding", "workshop", "carport", "stable"),
            "exterior": ("structure", "facade", "porch", "front"),
            "interior": ("kitchen", "bedroom", "bathroom", "room", "inside", "basement", "fireplace"),
            "land": ("acre", "pasture", "field", "meadow", "clearing"),
            "approach": ("driveway", "drive", "gate", "entrance", "lane"),
            "construction_detail": ("log", "beam", "chinking", "detail", "close"),
            "boundary_map": ("boundary", "parcel", "acre", "survey", "map"),
            "aerial": ("aerial", "drone", "overhead", "above"),
            # "recreation" also covers pool/hot tub/golf per _ROLE_PATTERNS.
            "recreation": ("fishing", "trail", "kayak", "hunting", "pool",
                          "golf", "hot tub"),
        }
        for token in related.get(detail, ()):
            if token in wanted:
                return 1
        return 3

    def _research_rank_key(self, candidate: MediaCandidate, breakdown, scene: SceneRow) -> tuple:
        """Ordering only — every candidate reaching here is already valid and
        already property-isolated. Property identity is enforced *before*
        this by _candidates_in_scope(), so a wrong-property asset can never
        appear regardless of how well it would rank."""
        return (
            -float(candidate.property_match_score or 0.0),  # strongest property evidence first
            self._tier_rank(candidate),                      # then measured quality tier
            self._role_rank(candidate, scene),               # then role relevance to this scene
            -float(getattr(breakdown, "total", 0.0) or 0.0), # existing scorer as final tiebreak
        )

    def resolve(self, scene: SceneRow, images_dir: Path, log: LogFn = print) -> AssetResult:
        # Property scope first — before availability, before scoring.
        in_scope = self._candidates_in_scope(scene.scene_number)
        available = [c for c in in_scope if self._is_available(c)]
        if not available:
            property_id = self.property_id_for_scene(scene.scene_number)
            detail = f" for property '{property_id}'" if property_id else " for this property"
            return AssetResult(
                scene_number=scene.scene_number, path=None, media_type=None,
                source=self.source, status=SceneStatus.FAILED,
                error=f"No unused research media remaining{detail}.",
            )

        from style_engine.visual_selection import (
            build_selection_context,
            scene_has_manual_authority,
            smart_selection_score,
        )

        manual = scene_has_manual_authority(scene)
        ctx = None if manual else build_selection_context(scene, self.resolved_style, self.selection_history)
        query = (scene.prompt or scene.stock or getattr(scene, "visual_description", "") or scene.script_segment or "").strip()
        used_ids = set(getattr(self.selection_history, "used_asset_ids", None) or set())
        provider_counts = getattr(self.selection_history, "provider_counts", None)

        scored = []
        hard_invalid: list = []
        for candidate in available:
            failure = self._hard_validity_failure(candidate)
            if failure is not None:
                hard_invalid.append((candidate, failure))
                continue
            self._ensure_dimensions(candidate)
            asset_id = f"research:{candidate.source_id or ''}:{Path(candidate.local_path).name}"
            breakdown = smart_selection_score(
                query=query,
                script_segment=scene.script_segment or "",
                visual_description=getattr(scene, "visual_description", "") or "",
                title=candidate.title or "",
                # role_detail is the scraper's granular classification
                # (interior/water/approach/construction_detail/...). Feeding
                # it to the EXISTING scorer is what lets a scene asking for
                # "creek" match the authentic creek photo instead of any
                # arbitrary property photo — no second ranking system, and
                # no extra planner heuristics.
                description=" ".join(filter(None, [candidate.role_detail, candidate.role])),
                extra_text=" ".join(filter(None, [candidate.role_detail, candidate.role])),
                width=candidate.width or 0,
                height=candidate.height or 0,
                download_url=candidate.source_url,
                provider="research",
                media_type=candidate.media_type,
                used_asset_ids=used_ids,
                asset_id=asset_id,
                provider_use_counts=provider_counts,
                context=ctx,
            )
            # NOTE: breakdown.reject_reason is deliberately NOT a veto here.
            # It carries the stock quality floor (1000x600), which throws away
            # authentic property photos — a real 316x234 listing photo is the
            # genuine article, not a defect. The scorer's output is used for
            # ordering only; validity was decided by _hard_validity_failure().
            scored.append((candidate, breakdown, asset_id))

        if not scored:
            if hard_invalid:
                reasons = "; ".join(sorted({why for _, why in hard_invalid}))
                return AssetResult(
                    scene_number=scene.scene_number, path=None, media_type=None,
                    source=self.source, status=SceneStatus.FAILED,
                    error=f"All research media candidates were hard-invalid ({reasons}).",
                )
            return AssetResult(
                scene_number=scene.scene_number, path=None, media_type=None,
                source=self.source, status=SceneStatus.FAILED,
                error="No research media candidates available for this property.",
            )

        scored.sort(key=lambda row: self._research_rank_key(row[0], row[1], scene))
        chosen, _breakdown, asset_id = scored[0]

        n = int(str(scene.scene_number).strip())
        ext = Path(chosen.local_path).suffix or (".jpg" if chosen.media_type == "image" else ".mp4")
        target_path = Path(images_dir) / f"{n:03d}{ext}"
        shutil.copy2(chosen.local_path, target_path)
        chosen.used = True

        if self.selection_history is not None:
            self.selection_history.record(
                provider="research", asset_id=asset_id,
                title=chosen.title or "", description=chosen.role or "",
            )

        log(f"[ASSET] Scene {scene.scene_number} -> RESEARCH ({Path(chosen.local_path).name}, role={chosen.role})")
        media_type = MediaType.VIDEO if chosen.media_type == "video" else MediaType.IMAGE
        return AssetResult(
            scene_number=scene.scene_number, path=target_path, media_type=media_type,
            source=self.source, status=SceneStatus.READY,
            metadata={
                "provider": "research",
                "source_url": chosen.source_url,
                "role": chosen.role,
                # The resolved listing is retained on the scene's result so
                # downstream QA/regeneration can never silently re-resolve it
                # against a different property.
                "property_id": chosen.property_id,
                "property_match_score": chosen.property_match_score,
                "script_relevance": chosen.script_relevance,
                "license_status": chosen.license_status,
                "license_evidence": chosen.license_evidence,
            },
        )
