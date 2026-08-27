"""Per-video project workspace: one video = one isolated folder.

Does not acquire assets, render, or change provider logic. It only owns where
generated files for the *current* project live, and a stable project_id that is
independent of the folder name.
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

UNSAFE_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
TITLE_MAX_LEN = 60
META_NAME = "project.json"
CSV_NAME = "visual_plan.csv"
NARRATION_WAV = "narration.wav"
NARRATION_MP3 = "narration.mp3"
PLAN_JSON_NAME = "ai_visual_plan.json"
SCRIPT_TXT = "narration.txt"
VOICEOVER_SUFFIXES = (".wav", ".mp3", ".m4a", ".aac", ".flac", ".webm", ".ogg")


def default_projects_root() -> Path:
    """Reuse the user's Downloads tree when it exists; never a second unrelated disk root."""
    downloads = Path.home() / "Downloads"
    if downloads.is_dir():
        return downloads / "Semantic YT Studio"
    return Path.home() / "Semantic YT Studio"


def sanitize_title(title: Optional[str], max_len: int = TITLE_MAX_LEN) -> str:
    raw = (title or "").strip()
    raw = UNSAFE_CHARS.sub("", raw)
    raw = raw.replace("—", " ").replace("–", " ").replace("−", " ")
    raw = re.sub(r"[\s\-]+", "_", raw)
    raw = re.sub(r"_+", "_", raw).strip("._")
    if not raw:
        return "Untitled"
    return raw[:max_len].rstrip("._") or "Untitled"


def path_is_inside(path: Path, root: Path) -> bool:
    try:
        Path(path).resolve().relative_to(Path(root).resolve())
        return True
    except (ValueError, OSError):
        return False


@dataclass
class ProjectWorkspace:
    project_id: str
    title: str
    seq: int
    root: Path
    created_at: str = ""
    folder_name: str = ""

    script_dir: Path = field(init=False)
    csv_dir: Path = field(init=False)
    audio_dir: Path = field(init=False)
    assets_dir: Path = field(init=False)
    flow_dir: Path = field(init=False)
    youtube_dir: Path = field(init=False)
    stock_dir: Path = field(init=False)
    logs_dir: Path = field(init=False)
    state_dir: Path = field(init=False)
    final_dir: Path = field(init=False)
    tmp_dir: Path = field(init=False)

    def __post_init__(self) -> None:
        self.root = Path(self.root)
        self.folder_name = self.folder_name or self.root.name
        self.created_at = self.created_at or datetime.now().isoformat(timespec="seconds")
        self.script_dir = self.root / "script"
        self.csv_dir = self.root / "csv"
        self.audio_dir = self.root / "audio"
        self.assets_dir = self.root / "assets"
        self.flow_dir = self.root / "flow"
        self.youtube_dir = self.root / "youtube"
        self.stock_dir = self.root / "stock"
        self.logs_dir = self.root / "logs"
        self.state_dir = self.root / "state"
        self.final_dir = self.root / "final"
        self.tmp_dir = self.root / "tmp"

    @property
    def csv_path(self) -> Path:
        return self.csv_dir / CSV_NAME

    @property
    def audio_path(self) -> Path:
        return self.audio_dir / NARRATION_WAV

    @property
    def audio_mp3_path(self) -> Path:
        return self.audio_dir / NARRATION_MP3

    def find_voiceover_audio(self) -> Optional[Path]:
        """Return the project's active voiceover file.

        Priority:
        1. Explicit active_voiceover from project.json (what the UI last selected)
        2. Most recently modified audio in audio/ (includes legacy narration.wav /
           voiceover_qwen* files discovered as normal audio)
        """
        active = self.get_active_voiceover()
        if active is not None:
            return active
        if not self.audio_dir.is_dir():
            return None
        candidates: List[Path] = []
        for path in self.audio_dir.iterdir():
            if not path.is_file():
                continue
            if path.name.startswith("."):
                continue
            if path.suffix.lower() in VOICEOVER_SUFFIXES:
                candidates.append(path)
        if not candidates:
            return None
        candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return candidates[0]

    def get_active_voiceover(self) -> Optional[Path]:
        raw = str(self.read_meta().get("active_voiceover") or "").strip()
        if not raw:
            return None
        path = Path(raw)
        if not path.is_absolute():
            path = self.root / path
        try:
            path = path.resolve()
        except OSError:
            return None
        if path.is_file() and path.suffix.lower() in VOICEOVER_SUFFIXES:
            return path
        return None

    def set_active_voiceover(self, path: Path | str | None, *, source: str = "") -> None:
        """Persist which audio file the video pipeline should use.

        Obsolete source values such as ``tts`` / ``cloned`` are not written;
        they are normalized to ``imported`` so new projects never persist TTS tags.
        Existing project.json fields are left alone until the next write.
        """
        self.ensure_dirs()
        data = self.read_meta()
        data.update(self.to_dict())
        if path is None:
            data.pop("active_voiceover", None)
            data.pop("active_voiceover_source", None)
        else:
            p = Path(path)
            try:
                rel = p.resolve().relative_to(self.root.resolve())
                stored = str(rel).replace("\\", "/")
            except (ValueError, OSError):
                stored = str(p)
            data["active_voiceover"] = stored
            src = (source or "").strip().lower()
            # Never persist obsolete TTS source tags on new writes.
            if src in ("tts", "cloned"):
                src = "imported"
            if src:
                data["active_voiceover_source"] = src
            else:
                data.pop("active_voiceover_source", None)
        # Leave obsolete voice_id untouched if present (ignore, don't migrate).
        self._write_meta(data)

    def active_voiceover_source(self) -> str:
        return str(self.read_meta().get("active_voiceover_source") or "").strip().lower()

    @property
    def script_path(self) -> Path:
        return self.script_dir / SCRIPT_TXT

    @property
    def visual_plan_json_path(self) -> Path:
        return self.script_dir / PLAN_JSON_NAME

    @property
    def editorial_plan_json_path(self) -> Path:
        return self.state_dir / "editorial_plan.json"

    @property
    def meta_path(self) -> Path:
        return self.root / META_NAME

    @property
    def manifest_path(self) -> Path:
        return self.state_dir / "manifest.json"

    @property
    def scene_state_path(self) -> Path:
        return self.state_dir / "scene_state.json"

    @property
    def log_path(self) -> Path:
        return self.logs_dir / "generation.log"

    def display_seq(self) -> str:
        return f"{int(self.seq):03d}"

    def ensure_dirs(self) -> None:
        for d in (
            self.script_dir,
            self.csv_dir,
            self.audio_dir,
            self.assets_dir,
            self.flow_dir,
            self.youtube_dir,
            self.stock_dir,
            self.logs_dir,
            self.state_dir,
            self.final_dir,
            self.tmp_dir,
        ):
            d.mkdir(parents=True, exist_ok=True)

    def to_dict(self) -> dict:
        return {
            "project_id": self.project_id,
            "title": self.title,
            "seq": int(self.seq),
            "folder_name": self.root.name,
            "created_at": self.created_at,
            "root": str(self.root),
        }

    def save_meta(self) -> None:
        self._write_meta(self.to_dict())

    def read_meta(self) -> Dict[str, Any]:
        path = self.meta_path
        if not path.is_file():
            _META_CACHE.pop(str(path), None)
            return {}
        try:
            mtime = path.stat().st_mtime
        except OSError:
            return {}
        key = str(path)
        cached = _META_CACHE.get(key)
        if cached is not None and cached[0] == mtime:
            return dict(cached[1])
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
        if not isinstance(data, dict):
            return {}
        _META_CACHE[key] = (mtime, dict(data))
        return data

    def _write_meta(self, data: Dict[str, Any]) -> None:
        self.ensure_dirs()
        self.meta_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        try:
            mtime = self.meta_path.stat().st_mtime
        except OSError:
            _META_CACHE.pop(str(self.meta_path), None)
        else:
            _META_CACHE[str(self.meta_path)] = (mtime, dict(data))
        # Folder listing cache may include this project's mtime.
        try:
            _LIST_PROJECTS_CACHE.pop(str(self.root.parent.resolve()), None)
        except OSError:
            pass

    def voice_id(self) -> str:
        """Obsolete TTS field. Readable for old projects; always ignored by the app."""
        return str(self.read_meta().get("voice_id") or "").strip()

    def set_voice_id(self, voice_id: str) -> None:
        """No-op: new projects never write voice_id. Leaves existing values untouched."""
        return

    def smart_editing_settings(self) -> dict:
        from smart_editing import DEFAULT_SETTINGS

        data = self.read_meta().get("smart_editing")
        if not isinstance(data, dict):
            return dict(DEFAULT_SETTINGS)
        merged = dict(DEFAULT_SETTINGS)
        merged.update(data)
        return merged

    def set_smart_editing_settings(self, settings: dict) -> None:
        data = self.read_meta()
        data.update(self.to_dict())
        data["smart_editing"] = {
            k: settings.get(k)
            for k in (
                "text_effects",
                "sound_effects",
                "visual_transitions",
                "scene_ambience",
                "intensity",
                "text_effects_intensity",
                "sound_effects_intensity",
                "visual_transitions_intensity",
                "scene_ambience_intensity",
                "mode",
            )
            if k in settings
        }
        self._write_meta(data)

    def video_style_settings(self) -> dict:
        """Return {mode, style_id, brand_kit_id}. Empty mode = legacy (no style)."""
        data = self.read_meta().get("video_style")
        if not isinstance(data, dict):
            return {"mode": "", "style_id": None, "brand_kit_id": None}
        return {
            "mode": str(data.get("mode") or "").strip().lower(),
            "style_id": data.get("style_id") or None,
            "brand_kit_id": data.get("brand_kit_id") or None,
        }

    def set_video_style_settings(
        self,
        *,
        mode: str = "",
        style_id: str | None = None,
        brand_kit_id: str | None = None,
    ) -> None:
        data = self.read_meta()
        data.update(self.to_dict())
        data["video_style"] = {
            "mode": str(mode or "").strip().lower(),
            "style_id": style_id or None,
            "brand_kit_id": brand_kit_id or None,
        }
        self._write_meta(data)

    def style_resolution(self) -> dict:
        data = self.read_meta().get("style_resolution")
        return dict(data) if isinstance(data, dict) else {}

    def set_style_resolution(self, resolution: dict | None) -> None:
        data = self.read_meta()
        data.update(self.to_dict())
        if resolution:
            data["style_resolution"] = dict(resolution)
        else:
            data.pop("style_resolution", None)
        self._write_meta(data)

    def save_script(self, text: str) -> Path:
        self.ensure_dirs()
        self.script_path.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")
        return self.script_path

    def save_visual_plan_json(self, payload: Any) -> Path:
        self.ensure_dirs()
        self.visual_plan_json_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return self.visual_plan_json_path

    def copy_csv_in(self, src: Path) -> Path:
        """Manual CSV stays inside this workspace; schema is unchanged."""
        self.ensure_dirs()
        src = Path(src)
        if src.resolve() != self.csv_path.resolve():
            shutil.copy2(src, self.csv_path)
        return self.csv_path

    def next_final_path(self) -> Path:
        """First export uses the title (or final_video). Re-exports become final 1, final 2, …"""
        self.ensure_dirs()
        stem = sanitize_title(self.title)
        primary = self.final_dir / ("final_video.mp4" if stem == "Untitled" else f"{stem}.mp4")
        existing = list(self.final_dir.glob("*.mp4"))
        if not existing:
            return primary
        n = 1
        while True:
            candidate = self.final_dir / f"final {n}.mp4"
            if not candidate.exists():
                return candidate
            n += 1

    def append_log(self, text: str) -> None:
        self.ensure_dirs()
        try:
            with self.log_path.open("a", encoding="utf-8") as fh:
                fh.write(text)
        except OSError:
            pass

    def sync_state_copies(self) -> None:
        """Keep spec state/ copies of the AssetManager / QA files that still live in assets/."""
        self.ensure_dirs()
        src_manifest = self.assets_dir / ".asset_manifest.json"
        if src_manifest.is_file():
            try:
                shutil.copy2(src_manifest, self.manifest_path)
            except OSError:
                pass
        src_qa = self.assets_dir / ".scene_qa.json"
        if src_qa.is_file():
            try:
                shutil.copy2(src_qa, self.scene_state_path)
            except OSError:
                pass

    def mirror_provider_asset(self, source_name: str, scene_number: str, src: Path) -> Optional[Path]:
        """Copy a finished asset into flow/ youtube/ stock/ without changing acquisition."""
        src = Path(src)
        if not src.is_file():
            return None
        try:
            n = int(str(scene_number).strip())
            name = f"scene_{n:03d}{src.suffix.lower()}"
        except ValueError:
            name = f"scene_{scene_number}{src.suffix.lower()}"
        key = (source_name or "").lower()
        if "youtube" in key:
            dest_dir = self.youtube_dir
        elif "flow" in key:
            dest_dir = self.flow_dir
        elif "stock" in key or "pexels" in key:
            dest_dir = self.stock_dir
        else:
            dest_dir = self.assets_dir
            dest = dest_dir / src.name
            if dest.resolve() == src.resolve():
                return dest
            dest_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            return dest
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / name
        if dest.resolve() != src.resolve():
            shutil.copy2(src, dest)
        return dest


def _next_seq(projects: Iterable[ProjectWorkspace]) -> int:
    seqs = [int(p.seq) for p in projects]
    return (max(seqs) + 1) if seqs else 1


def _unique_folder(root: Path, name: str) -> Path:
    candidate = root / name
    if not candidate.exists():
        return candidate
    n = 2
    while True:
        alt = root / f"{name}_{n}"
        if not alt.exists():
            return alt
        n += 1


def create_project(
    title: str = "",
    *,
    projects_root: Optional[Path] = None,
    when: Optional[date] = None,
) -> ProjectWorkspace:
    root = Path(projects_root) if projects_root is not None else default_projects_root()
    root.mkdir(parents=True, exist_ok=True)
    existing = list_projects(root)
    seq = _next_seq(existing)
    day = when or date.today()
    project_id = f"project_{day.strftime('%Y%m%d')}_{seq:03d}"
    # Collision on same-day recreate after deleted folders: bump until unique.
    used_ids = {p.project_id for p in existing}
    extra = seq
    while project_id in used_ids:
        extra += 1
        project_id = f"project_{day.strftime('%Y%m%d')}_{extra:03d}"
        seq = extra
    safe = sanitize_title(title)
    folder = f"Video_{day.isoformat()}_{seq:03d}_{safe}"
    workspace_root = _unique_folder(root, folder)
    ws = ProjectWorkspace(
        project_id=project_id,
        title=(title or "").strip() or "Untitled",
        seq=seq,
        root=workspace_root,
    )
    ws.ensure_dirs()
    ws.save_meta()
    return ws


def load_project(root: Path) -> Optional[ProjectWorkspace]:
    meta = Path(root) / META_NAME
    if not meta.is_file():
        return None
    try:
        data = json.loads(meta.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict) or not data.get("project_id"):
        return None
    try:
        seq = int(data.get("seq") or 0)
    except (TypeError, ValueError):
        seq = 0
    return ProjectWorkspace(
        project_id=str(data["project_id"]),
        title=str(data.get("title") or "Untitled"),
        seq=seq,
        root=Path(root),
        created_at=str(data.get("created_at") or ""),
        folder_name=str(data.get("folder_name") or Path(root).name),
    )


def find_project(projects_root: Path, project_id: str) -> Optional[ProjectWorkspace]:
    for ws in list_projects(projects_root):
        if ws.project_id == project_id:
            return ws
    return None


def list_projects(projects_root: Path) -> List[ProjectWorkspace]:
    root = Path(projects_root)
    if not root.is_dir():
        return []
    fingerprint = _list_projects_fingerprint(root)
    cached = _LIST_PROJECTS_CACHE.get(str(root.resolve()) if root.exists() else str(root))
    if cached is not None and cached[0] == fingerprint:
        return list(cached[1])

    found: List[ProjectWorkspace] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        ws = load_project(child)
        if ws is not None:
            found.append(ws)
    found.sort(key=lambda w: (w.seq, w.project_id))
    try:
        cache_key = str(root.resolve())
    except OSError:
        cache_key = str(root)
    _LIST_PROJECTS_CACHE[cache_key] = (fingerprint, list(found))
    return found


def _list_projects_fingerprint(root: Path) -> tuple:
    """Invalidate when project folders or their project.json mtimes change."""
    entries: list[tuple[str, float]] = []
    try:
        for child in root.iterdir():
            if not child.is_dir():
                continue
            meta = child / META_NAME
            if not meta.is_file():
                continue
            try:
                entries.append((child.name, meta.stat().st_mtime))
            except OSError:
                entries.append((child.name, 0.0))
    except OSError:
        return ()
    return tuple(sorted(entries))


_LIST_PROJECTS_CACHE: Dict[str, tuple] = {}
_META_CACHE: Dict[str, tuple] = {}


def asset_belongs_to_project(path: Optional[Path], workspace: ProjectWorkspace) -> bool:
    if path is None:
        return False
    return path_is_inside(path, workspace.root)
