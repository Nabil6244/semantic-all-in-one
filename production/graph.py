"""The production dependency graph — a thin layer over the state that already exists.

It does not store the project a second time. Every node is a FINGERPRINT of something an existing system owns:

  narration:N   the row's script_segment                     (CSV, the production contract)
  visual:N      the row's visual instruction                 (CSV: asset_type, prompt/stock, queries, fallbacks)
  text:N        the row's on-screen words                    (CSV: caption, highlight, edge_label, chapter_title)
  structure:N   the row's composition links                  (CSV: node_id, node_type, role, edge_from, edge_to)
  asset:N       the media file the scene uses                (asset manifest record + the file's size/mtime)
  timing:N      the scene's start/end on the narration       (editorial plan, after alignment)
  graphics:N    the scene's overlays                         (derived: text + narration + timing)
  clip:N        the scene's rendered clip                    (render cache: asset + timing + graphics + settings)
  audio         the narration recording                      (the same audio fingerprint the existing caches use)
  alignment     word timings                                 (depends on audio and every narration row)
  settings      render settings (resolution, captions, styles, smart editing)
  final         the finished video                           (every clip + audio)

Edges say what is built from what. ``impact`` answers "what becomes invalid if X changes"; ``diff`` compares the
graph now with the snapshot saved after the last successful render and returns exactly what changed and everything
downstream of it — and, by elimination, everything that can be reused.

The asset rule is the canonical one: ``asset_manager.asset_record_matches`` (the same function AssetManager's cache
uses), so the graph can never disagree with Generate about which media is reused.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set

GRAPH_NAME = "production_graph.json"
SCHEMA_VERSION = 1

VISUAL_FIELDS = ("asset_type", "prompt", "stock", "search_queries", "fallbacks", "visual_description")
TEXT_FIELDS = ("caption", "highlight", "edge_label", "chapter_title", "label", "on_screen_text")
STRUCTURE_FIELDS = ("node_id", "node_type", "role", "edge_from", "edge_to")
NARRATION_FIELDS = ("script_segment",)
_KNOWN = set(VISUAL_FIELDS) | set(TEXT_FIELDS) | set(STRUCTURE_FIELDS) | set(NARRATION_FIELDS) | {"scene_number"}

# What each scene node is built from (inputs that live outside the scene are wired in build()).
SCENE_EDGES = {
    "asset": ("visual",),
    "timing": ("narration",),
    "graphics": ("text", "narration", "timing", "structure"),
    "clip": ("asset", "timing", "graphics", "structure"),
}
ASPECT_LABELS = {
    "narration": "narration",
    "visual": "visual instruction",
    "text": "on-screen text",
    "structure": "composition links",
    "asset": "media file",
    "timing": "timing",
    "graphics": "graphics",
    "clip": "rendered clip",
}


def _fp(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def scene_key(n: Any) -> str:
    try:
        return f"{int(str(n).strip()):03d}"
    except ValueError:
        return str(n).strip()


def _row_get(row: Any, name: str) -> Any:
    if isinstance(row, Mapping):
        return row.get(name)
    return getattr(row, name, None)


def _norm(value: Any) -> Any:
    if isinstance(value, str):
        return " ".join(value.split())
    if isinstance(value, (list, tuple)):
        return [_norm(v) for v in value]
    return value if value is not None else ""


def _row_fields(row: Any, names: Sequence[str]) -> dict:
    return {n: _norm(_row_get(row, n)) for n in names if _row_get(row, n) not in (None, "", [], ())}


def _other_fields(row: Any) -> dict:
    if not isinstance(row, Mapping):
        return {}
    return {k: _norm(v) for k, v in row.items() if k not in _KNOWN and v not in (None, "")}


@dataclass
class Node:
    id: str
    kind: str
    scene: str = ""
    fp: str = ""
    deps: List[str] = field(default_factory=list)
    label: str = ""
    reusable: Optional[bool] = None  # asset nodes: does the canonical reuse rule keep the saved media?


@dataclass
class ChangeSet:
    """The difference between two graph states, and its consequences."""

    changed: Dict[str, List[str]] = field(default_factory=dict)  # scene -> aspects whose INPUT changed
    global_changes: List[str] = field(default_factory=list)  # "audio", "settings", "scenes_added", ...
    invalidated: Set[str] = field(default_factory=set)  # every node id that must be rebuilt
    added_scenes: List[str] = field(default_factory=list)
    removed_scenes: List[str] = field(default_factory=list)
    first_run: bool = False

    def scenes(self, kind: str) -> List[str]:
        return sorted(n.split(":", 1)[1] for n in self.invalidated if n.startswith(kind + ":"))

    @property
    def assets_to_regenerate(self) -> List[str]:
        return self.scenes("asset")

    @property
    def clips_to_render(self) -> List[str]:
        return self.scenes("clip")

    @property
    def needs_realign(self) -> bool:
        return "alignment" in self.invalidated

    def to_dict(self) -> dict:
        return {
            "changed": self.changed,
            "global_changes": self.global_changes,
            "assets_to_regenerate": self.assets_to_regenerate,
            "clips_to_render": self.clips_to_render,
            "needs_realign": self.needs_realign,
            "added_scenes": self.added_scenes,
            "removed_scenes": self.removed_scenes,
            "first_run": self.first_run,
        }


class ProductionGraph:
    def __init__(self) -> None:
        self.nodes: Dict[str, Node] = {}
        self.scenes: List[str] = []
        self._dependents: Dict[str, Set[str]] = {}

    # ------------------------------------------------------------------ construction
    def _add(self, node: Node) -> Node:
        self.nodes[node.id] = node
        return node

    def _wire(self) -> None:
        self._dependents = {nid: set() for nid in self.nodes}
        for node in self.nodes.values():
            for dep in node.deps:
                self._dependents.setdefault(dep, set()).add(node.id)

    @classmethod
    def build(
        cls,
        rows: Iterable[Any],
        *,
        manifest: Optional[Mapping[str, dict]] = None,
        images_dir: Optional[Path] = None,
        audio_key: str = "",
        timings: Optional[Mapping[str, Sequence[float]]] = None,
        settings: Optional[Mapping[str, Any]] = None,
    ) -> "ProductionGraph":
        """``rows``: CSV dicts or SceneRow objects. ``manifest``: the asset manifest (scene -> record).
        ``timings``: scene -> (start, end) once alignment is known. ``settings``: anything that changes every clip."""
        g = cls()
        rows_list = list(rows)
        manifest = {scene_key(k): v for k, v in (manifest or {}).items()}
        timings = {scene_key(k): v for k, v in (timings or {}).items()}
        g._add(Node("audio", "audio", fp=str(audio_key or ""), label="narration recording"))
        g._add(Node("settings", "settings", fp=_fp(dict(settings or {})), label="render settings"))
        narration_ids = []
        for row in rows_list:
            n = scene_key(_row_get(row, "scene_number"))
            if not n or n in g.scenes:
                continue
            g.scenes.append(n)
            g._add(Node(f"narration:{n}", "narration", n, _fp(_row_fields(row, NARRATION_FIELDS))))
            g._add(Node(f"visual:{n}", "visual", n, _fp(_row_fields(row, VISUAL_FIELDS))))
            g._add(Node(f"text:{n}", "text", n, _fp({**_row_fields(row, TEXT_FIELDS), **_other_fields(row)})))
            g._add(Node(f"structure:{n}", "structure", n, _fp(_row_fields(row, STRUCTURE_FIELDS))))
            narration_ids.append(f"narration:{n}")
            rec = manifest.get(n) or {}
            afp = _asset_fp(rec, images_dir, n)
            g._add(Node(f"asset:{n}", "asset", n, afp, deps=[f"visual:{n}"],
                        reusable=bool(afp) and _asset_reusable(row, rec)))
            t = timings.get(n)
            # A clip is built from its scene's LENGTH (the render cache keys on duration; overlays are timed within the
            # scene), so a scene that only moved later on the timeline keeps its clip.
            g._add(Node(f"timing:{n}", "timing", n, _fp(round(float(t[1]) - float(t[0]), 3)) if t else "",
                        deps=[f"narration:{n}", "alignment"]))
            g._add(Node(f"graphics:{n}", "graphics", n, "", deps=[f"text:{n}", f"narration:{n}", f"timing:{n}", f"structure:{n}"]))
            g._add(Node(f"clip:{n}", "clip", n, "", deps=[f"asset:{n}", f"timing:{n}", f"graphics:{n}", f"structure:{n}", "settings"]))
        g._add(Node("alignment", "alignment", fp="", deps=["audio"] + narration_ids, label="word timings"))
        g._add(Node("final", "final", deps=[f"clip:{n}" for n in g.scenes] + ["audio", "settings"], label="final video"))
        # Overscaled / Exp Solar arrows connect scenes: an arrow is drawn between two nodes, so a scene's graphics depend on
        # the composition of the scenes its arrow comes from or goes to.
        by_node_id = {}
        rows_by_scene = {}
        for row in rows_list:
            n = scene_key(_row_get(row, "scene_number"))
            rows_by_scene.setdefault(n, row)
            nid = str(_row_get(row, "node_id") or "").strip()
            if nid:
                by_node_id.setdefault(nid, n)
        for n, row in rows_by_scene.items():
            for col in ("edge_from", "edge_to"):
                other = by_node_id.get(str(_row_get(row, col) or "").strip())
                if other and other != n and f"graphics:{n}" in g.nodes:
                    g.nodes[f"graphics:{n}"].deps.append(f"structure:{other}")
        g._wire()
        return g

    # ------------------------------------------------------------------ queries
    def dependents(self, node_id: str, *, through: Optional[Set[str]] = None, avoid: Iterable[str] = ()) -> Set[str]:
        """Every node built (directly or not) from ``node_id`` (``avoid``: nodes not to propagate through)."""
        out: Set[str] = set()
        blocked = set(avoid)
        stack = [node_id]
        while stack:
            cur = stack.pop()
            for d in self._dependents.get(cur, ()):
                if d in blocked:
                    continue
                if d not in out:
                    out.add(d)
                    stack.append(d)
        return out

    def dependencies(self, node_id: str) -> Set[str]:
        out: Set[str] = set()
        stack = [node_id]
        while stack:
            cur = stack.pop()
            node = self.nodes.get(cur)
            for d in (node.deps if node else ()):
                if d not in out:
                    out.add(d)
                    stack.append(d)
        return out

    def impact(self, scene: Any, aspect: str) -> Dict[str, Any]:
        """What becomes invalid if ``aspect`` ("visual", "text", "narration", "structure", "asset") of ``scene`` changes —
        and what stays untouched."""
        n = scene_key(scene)
        if aspect == "audio":
            hit = self.dependents("audio")
        else:
            hit = self.dependents(f"{aspect}:{n}")
            if aspect == "narration":
                # New narration means a new recording: alignment (and so every scene's timing) can move.
                hit |= {"alignment"} | self.dependents("alignment")
        by_kind: Dict[str, List[str]] = {}
        for nid in hit:
            kind, _, sc = nid.partition(":")
            by_kind.setdefault(kind, []).append(sc or kind)
        untouched_assets = [s for s in self.scenes if f"asset:{s}" not in hit]
        return {
            "scene": n,
            "aspect": aspect,
            "regenerate_assets": sorted(by_kind.get("asset", [])),
            "rebuild_graphics": sorted(by_kind.get("graphics", [])),
            "rerender_clips": sorted(by_kind.get("clip", [])),
            "realign": "alignment" in hit,
            "final": "final" in hit,
            "reuse_assets": untouched_assets,
        }

    def explain_scene(self, scene: Any) -> Dict[str, List[str]]:
        """For the scene details panel: what this scene's clip is built from, and what is built from its inputs."""
        n = scene_key(scene)
        return {
            "built_from": sorted(self.dependencies(f"clip:{n}")),
            "visual_change_rebuilds": sorted(self.dependents(f"visual:{n}")),
            "text_change_rebuilds": sorted(self.dependents(f"text:{n}")),
        }

    # ------------------------------------------------------------------ snapshots & diff
    def snapshot(self) -> dict:
        return {
            "schema_version": SCHEMA_VERSION,
            "scenes": list(self.scenes),
            "fingerprints": {nid: node.fp for nid, node in self.nodes.items() if node.fp},
        }

    def diff(self, previous: Optional[Mapping[str, Any]]) -> ChangeSet:
        """Compare with a snapshot. Missing/old snapshot -> everything is new (first_run)."""
        cs = ChangeSet()
        if not previous or int(previous.get("schema_version") or 0) != SCHEMA_VERSION:
            cs.first_run = True
            cs.invalidated = {nid for nid, node in self.nodes.items() if not (node.kind == "asset" and node.reusable)}
            cs.added_scenes = list(self.scenes)
            return cs
        old_fp: Mapping[str, str] = previous.get("fingerprints") or {}
        old_scenes = [str(s) for s in previous.get("scenes") or []]
        cs.added_scenes = [s for s in self.scenes if s not in old_scenes]
        cs.removed_scenes = [s for s in old_scenes if s not in self.scenes]
        roots: Set[str] = set()
        for gid in ("audio", "settings"):
            if self.nodes[gid].fp != old_fp.get(gid, ""):
                cs.global_changes.append(gid)
                roots.add(gid)
        for n in self.scenes:
            if n in cs.added_scenes:
                roots |= {f"{k}:{n}" for k in ("narration", "visual", "text", "structure", "asset")}
                cs.changed[n] = ["new scene"]
                continue
            aspects = []
            for kind in ("narration", "visual", "text", "structure", "asset", "timing"):
                nid = f"{kind}:{n}"
                now = self.nodes[nid].fp
                if kind == "timing" and not now:
                    continue  # not aligned yet: alignment decides later
                if now != old_fp.get(nid, ""):
                    aspects.append(kind)
                    roots.add(nid)
            if aspects:
                cs.changed[n] = aspects
        if cs.removed_scenes or cs.added_scenes:
            cs.global_changes.append("scene list")
        realign = "audio" in cs.global_changes or any("narration" in a for a in cs.changed.values())
        # Once the new alignment is known (every scene has a timing), each scene's timing was compared on its own
        # above, so only the scenes that really moved are invalidated. Before that, a new recording may move any scene.
        timings_known = bool(self.scenes) and all(self.nodes[f"timing:{n}"].fp for n in self.scenes)
        extra: Set[str] = set()
        if realign:
            if timings_known:
                roots.discard("audio")
                extra |= {"alignment", "audio", "final"}
            else:
                roots.add("alignment")
        invalid: Set[str] = set(roots) | extra
        avoid = {"alignment"} if (realign and timings_known) else set()
        for r in roots:
            invalid |= self.dependents(r, avoid=avoid)
        # Removing a scene changes the final cut even when no remaining scene changed.
        if cs.removed_scenes:
            invalid.add("final")
        # Which media Generate fetches again is decided by the canonical reuse rule (asset_record_matches), not by the
        # diff: a file Change Source already replaced only needs its clip re-rendered; a file that is gone, or was made
        # for an instruction the row no longer asks for, is regenerated.
        for n in self.scenes:
            aid = f"asset:{n}"
            if self.nodes[aid].reusable:
                invalid.discard(aid)
            else:
                invalid.add(aid)
                invalid |= self.dependents(aid)
        cs.invalidated = invalid
        return cs


def _asset_reusable(row: Any, record: Mapping[str, Any]) -> bool:
    """The canonical rule (asset_manager.asset_record_matches). A local/numbered scene has no generated media to lose."""
    try:
        from asset_manager import asset_record_matches
        from providers.base import AssetSource, SceneRow
        from providers.router import SceneAssetRouter

        scene = row if isinstance(row, SceneRow) else SceneRow.from_csv_row(dict(row))
        source = SceneAssetRouter.classify(scene) or AssetSource.LOCAL
        if source == AssetSource.LOCAL:
            return True
        return asset_record_matches(dict(record or {}), scene, source)
    except Exception:
        return False


def _asset_fp(record: Mapping[str, Any], images_dir: Optional[Path], scene: str) -> str:
    """The media actually in use: its manifest identity plus the file's size and mtime (a replaced file differs)."""
    if not record and images_dir is None:
        return ""
    path = None
    local = (record or {}).get("local_path")
    if local and Path(local).is_file():
        path = Path(local)
    elif images_dir is not None:
        try:
            import video_generator as vg

            path = vg.find_image_for_scene(Path(images_dir), scene)
        except Exception:
            path = None
    if path is None:
        return ""
    try:
        st = path.stat()
        ident = [path.name, st.st_size, st.st_mtime_ns]
    except OSError:
        return ""
    return _fp({"src": (record or {}).get("source"), "file": ident})


# ---------------------------------------------------------------------- persistence
def graph_path(state_dir: Path) -> Path:
    return Path(state_dir) / GRAPH_NAME


def load_snapshot(state_dir: Optional[Path]) -> Optional[dict]:
    if state_dir is None:
        return None
    try:
        data = json.loads(graph_path(state_dir).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def save_snapshot(state_dir: Optional[Path], graph: ProductionGraph) -> None:
    if state_dir is None:
        return
    try:
        p = graph_path(state_dir)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(graph.snapshot(), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        tmp.replace(p)
    except OSError:
        pass


def timings_from_editorial_plan(plan: Any) -> Dict[str, tuple]:
    """scene -> (start, end) from an EditorialPlan object or its saved dict."""
    out: Dict[str, tuple] = {}
    scenes = getattr(plan, "scenes", None)
    if scenes is None and isinstance(plan, Mapping):
        scenes = plan.get("scenes")
    for sc in scenes or []:
        num = _row_get(sc, "scene_number")
        start, end = _row_get(sc, "start"), _row_get(sc, "end")
        if num is not None and start is not None and end is not None:
            try:
                out[scene_key(num)] = (float(start), float(end))
            except (TypeError, ValueError):
                continue
    return out


def settings_fingerprint(config: Mapping[str, Any]) -> Dict[str, Any]:
    """The render settings that change every clip (one place, so the graph and the UI agree)."""
    smart = config.get("smart_editing")
    smart_d = smart.to_dict() if hasattr(smart, "to_dict") else (dict(smart) if isinstance(smart, Mapping) else str(smart or ""))
    return {
        "resolution": config.get("resolution") or "1920x1080",
        "zoom": bool(config.get("zoom")),
        "zoom_amount": config.get("zoom_amount"),
        "captions": bool(config.get("captions")),
        "caption_style": config.get("caption_style") or "classic",
        "smart": smart_d,
        "style": config.get("style_fingerprint") or "",
    }
