#!/usr/bin/env python3
"""
Desktop GUI for video_generator.py (CustomTkinter).

Runs the existing pipeline functions in-process — no subprocess —
and streams their print() output into a log panel.
"""

from __future__ import annotations

import os
import platform
import sys

# Quiet Hugging Face / tokenizers; avoid worker processes re-launching the GUI.
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")

# darkdetect crashes on some macOS builds when mac_ver() returns "".
_original_mac_ver = platform.mac_ver


def _safe_mac_ver():
    result = _original_mac_ver()
    if not result[0]:
        return ("10.16", result[1], result[2])
    return result


platform.mac_ver = _safe_mac_ver

import csv
import multiprocessing
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import time
import traceback
from io import StringIO
from pathlib import Path
from tkinter import filedialog, messagebox

# Windows: hide black CMD flashes from ffmpeg / node / yt-dlp (must run before
# those libraries spawn children). No-op on macOS/Linux.
from providers import hidden_subprocess as _hidden_subprocess

_hidden_subprocess.install()

import customtkinter as ctk

import video_generator as vg
from asset_manager import AssetManager
from providers.base import AssetResult, AssetSource, MediaType, SceneRow, SceneStatus
from providers.router import SceneAssetRouter
from scene_recovery import SceneRecoveryTracker, summarize_assets
from scene_qa import SceneQAState, preview_alternatives, save_qa_file, load_qa_file, summarize_alternative_preview, short_error
from manual_clip import FILE_DIALOG_TYPES, ManualClipError, validate_local_media
from project_picker import ProjectPickerDialog, project_dicts_from_workspaces
from project_workspace import (
    asset_belongs_to_project,
    create_project,
    default_projects_root,
    find_project,
    list_projects,
    load_project,
    path_is_inside,
)
from smart_editing import (
    DEFAULT_SETTINGS,
    SmartEditingSettings,
    _audio_fingerprint,
    build_plan,
    get_cached_whisper_words,
    mix_sfx_with_narration,
    normalize_ambience_volume,
    scene_text_effects,
)
from editorial import (
    authoritative_transition_map,
    build_editorial_plan,
    build_music_plan,
    cache_settings_key as editorial_cache_settings_key,
    render_ducked_music,
    run_editorial_qa,
    save_editorial_plan,
    save_editorial_qa,
)
from editorial.persistence import load_cached_plan
from visual_director import parse_visual_plan
from ui.shell import AppShell
from ui import views as ui_views
from ui import theme as _ui_theme
from ui import scene_list as _scene_list


def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


APP_DISPLAY_NAME = "Semantic YT Studio"


def _configure_macos_dock_name(name: str = APP_DISPLAY_NAME) -> None:
    """Dock hover name when running `python app.py` (not a .app bundle).

    Packaged builds already set CFBundleName in Info.plist via VideoGenerator.spec.
    Requires pyobjc-framework-Cocoa in the env (see requirements-build.txt).
    """
    if sys.platform != "darwin" or _is_frozen():
        return
    try:
        from Foundation import NSBundle  # type: ignore
    except ImportError:
        return
    try:
        info = NSBundle.mainBundle().infoDictionary()
        if info is not None:
            info["CFBundleName"] = name
            info["CFBundleDisplayName"] = name
    except Exception:
        pass


# Dev: project folder. Packaged: PyInstaller extract dir (read-only — don't save here).
SOURCE_DIR = Path(__file__).resolve().parent
APP_DIR = SOURCE_DIR


def _default_output_path() -> Path:
    """Writable default — Desktop when packaged, project folder when developing."""
    if _is_frozen():
        return Path.home() / "Desktop" / "final.mp4"
    return SOURCE_DIR / "final.mp4"


def _browse_start_dir() -> Path:
    if _is_frozen():
        desktop = Path.home() / "Desktop"
        return desktop if desktop.is_dir() else Path.home()
    return SOURCE_DIR


DEFAULTS = {
    "csv": SOURCE_DIR / "script.csv",
    "audio": SOURCE_DIR / "voiceover.mp3",
    "output": _default_output_path(),
    "bg_audio": SOURCE_DIR / "assets" / "bg_audio.mp3",
}


def _settings_path() -> Path:
    """Local, gitignored settings file (Pexels key, etc.) — never committed,
    never hardcoded. Lives next to Desktop when packaged, project folder in dev."""
    base = Path.home() / ".videogen" if _is_frozen() else SOURCE_DIR
    base.mkdir(parents=True, exist_ok=True)
    return base / "settings.json"


def load_settings() -> dict:
    import json

    path = _settings_path()
    if not path.is_file():
        _SETTINGS_CACHE.clear()
        return {}
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return {}
    cached = _SETTINGS_CACHE.get("data")
    if cached is not None and _SETTINGS_CACHE.get("mtime") == mtime:
        return dict(cached)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(data, dict):
        return {}
    _SETTINGS_CACHE["mtime"] = mtime
    _SETTINGS_CACHE["data"] = dict(data)
    return data


def save_settings(data: dict) -> None:
    import json

    try:
        path = _settings_path()
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        try:
            _SETTINGS_CACHE["mtime"] = path.stat().st_mtime
            _SETTINGS_CACHE["data"] = dict(data)
        except OSError:
            _SETTINGS_CACHE.clear()
    except OSError:
        pass


_SETTINGS_CACHE: dict = {}


# Mirrors flow-engine/config.js exactly (models/aspectRatios/videoModels/
# videoDurations) — the ONLY Flow options this GUI offers, per the original
# Semantic Automator implementation. Do not add options that aren't actually
# supported there.
FLOW_IMAGE_MODELS = [("HARBOR_SEAL", "NB Lite"), ("NARWHAL", "NB 2"), ("GEM_PIX_2", "NB Pro")]
FLOW_IMAGE_ASPECT_RATIOS = [
    ("IMAGE_ASPECT_RATIO_LANDSCAPE", "16:9"),
    ("IMAGE_ASPECT_RATIO_SQUARE", "1:1"),
    ("IMAGE_ASPECT_RATIO_PORTRAIT", "9:16"),
]
FLOW_VIDEO_MODELS = [
    ("veo_3_1_t2v_lite", "Veo 3.1 – Lite"),
    ("veo_3_1_t2v_fast", "Veo 3.1 – Fast"),
    ("veo_3_1_t2v_quality", "Veo 3.1 – Quality"),
]
FLOW_VIDEO_DURATIONS = [(4, "4s"), (6, "6s"), (8, "8s"), (10, "10s")]

_SCENE_LOG_RE = re.compile(r"Scene\s+(\d+)\b\s*(?:->)?\s*(.+)$")


def _scene_key(scene_number) -> str:
    try:
        return f"{int(str(scene_number).strip()):03d}"
    except ValueError:
        return str(scene_number).strip()


def _classify_scene_status(tail: str) -> str | None:
    """Map an `[ASSET]`/`[STOCK]`/`[FLOW]` log line's tail text (after 'Scene N -> ')
    to a scene-table status word. Best-effort text matching against the exact
    strings those modules log — see asset_manager.py / providers/*."""
    t = tail.lower()
    if "(cached" in t or t.startswith("success"):
        return "ready"
    if "searching" in t:
        return "searching"
    if "selected" in t or "downloading" in t:
        return "downloading"
    if t.startswith("generated") or "generating" in t:
        return "generating"
    if "retry" in t:
        return "retrying"
    # Routing logs like "STOCK_VIDEO" / "FLOW_VIDEO" are not a status — they used
    # to paint every ready scene as Queued when Generate Final Video ran.
    return None


def _scene_busy_kind(source: AssetSource | None) -> str:
    if source in (AssetSource.STOCK, AssetSource.STOCK_IMAGE, AssetSource.STOCK_VIDEO):
        return "searching"
    if source == AssetSource.YOUTUBE_VIDEO:
        return "searching"
    if source in (AssetSource.FLOW_IMAGE, AssetSource.FLOW_VIDEO):
        return "generating"
    return "generating"


def _bundle_root() -> Path:
    """PyInstaller extract dir when frozen; otherwise the project folder."""
    if _is_frozen() and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return SOURCE_DIR


_LOGO_PATH_CACHE: Path | None | bool = False  # False = unset; None = missing
_LOGO_CTK_CACHE: dict[tuple[int, bool], tuple] = {}
_LOGO_ICON_CACHE: dict[int, object] = {}


def _logo_path() -> Path | None:
    """Return path to assets/logo.png if present (dev or bundled)."""
    global _LOGO_PATH_CACHE
    if _LOGO_PATH_CACHE is not False:
        return _LOGO_PATH_CACHE  # type: ignore[return-value]
    candidates = [
        _bundle_root() / "assets" / "logo.png",
        SOURCE_DIR / "assets" / "logo.png",
    ]
    for p in candidates:
        if p.is_file():
            _LOGO_PATH_CACHE = p
            return p
    _LOGO_PATH_CACHE = None
    return None


def _logo_ctk_image(diameter: int, *, circular: bool = True):
    """Load branding asset; UI uses a centered circular crop (no stretch)."""
    size = max(1, int(diameter))
    cache_key = (size, bool(circular))
    hit = _LOGO_CTK_CACHE.get(cache_key)
    if hit is not None:
        return hit
    logo_path = _logo_path()
    if logo_path is None:
        _LOGO_CTK_CACHE[cache_key] = (None, None)
        return None, None
    try:
        from PIL import Image, ImageDraw

        img = Image.open(logo_path).convert("RGBA")
        w, h = img.size
        if h <= 0 or w <= 0:
            _LOGO_CTK_CACHE[cache_key] = (None, None)
            return None, None
        if circular:
            side = min(w, h)
            left = (w - side) // 2
            top = (h - side) // 2
            img = img.crop((left, top, left + side, top + side))
            img = img.resize((size, size), Image.Resampling.LANCZOS)
            mask = Image.new("L", (size, size), 0)
            ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
            out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            out.paste(img, mask=mask)
            img = out
        else:
            scale = size / h
            disp_w = max(1, int(w * scale))
            img = img.resize((disp_w, size), Image.Resampling.LANCZOS)
        ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(size, size if circular else img.size[1]))
        result = (ctk_img, img)
        _LOGO_CTK_CACHE[cache_key] = result
        return result
    except Exception:
        _LOGO_CTK_CACHE[cache_key] = (None, None)
        return None, None


def _logo_icon_photo(size: int = 64):
    """Window/dock icon — same centered circular crop as the header."""
    size = max(1, int(size))
    if size in _LOGO_ICON_CACHE:
        return _LOGO_ICON_CACHE[size]
    logo_path = _logo_path()
    if logo_path is None:
        _LOGO_ICON_CACHE[size] = None
        return None
    try:
        from PIL import Image, ImageDraw, ImageTk

        img = Image.open(logo_path).convert("RGBA")
        w, h = img.size
        if h <= 0 or w <= 0:
            _LOGO_ICON_CACHE[size] = None
            return None
        side = min(w, h)
        left = (w - side) // 2
        top = (h - side) // 2
        img = img.crop((left, top, left + side, top + side))
        img = img.resize((size, size), Image.Resampling.LANCZOS)
        mask = Image.new("L", (size, size), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
        out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        out.paste(img, mask=mask)
        photo = ImageTk.PhotoImage(out)
        _LOGO_ICON_CACHE[size] = photo
        return photo
    except Exception:
        _LOGO_ICON_CACHE[size] = None
        return None


def ensure_ffmpeg_on_path() -> Path | None:
    """
    Prefer a bundled ffmpeg (bin/ffmpeg or bin/ffmpeg.exe), then system PATH.
    Prepends the chosen binary's directory to PATH so video_generator's
    subprocess calls to bare "ffmpeg" resolve correctly.
    """
    name = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
    candidates: list[Path] = [
        _bundle_root() / "bin" / name,
        SOURCE_DIR / "bin" / name,
    ]
    if _is_frozen():
        exe_dir = Path(sys.executable).resolve().parent
        candidates = [
            exe_dir / "bin" / name,
            exe_dir / name,
            *candidates,
        ]

    found: Path | None = None
    for path in candidates:
        if path.is_file():
            found = path.resolve()
            break

    if found is None:
        which = shutil.which("ffmpeg")
        return Path(which).resolve() if which else None

    if sys.platform != "win32":
        mode = found.stat().st_mode
        if not (mode & 0o111):
            found.chmod(mode | 0o111)
        # Sibling ffprobe from the same bundle (packaged mac/Linux).
        probe = found.parent / ("ffprobe.exe" if sys.platform == "win32" else "ffprobe")
        if probe.is_file():
            pmode = probe.stat().st_mode
            if not (pmode & 0o111):
                probe.chmod(pmode | 0o111)

    bin_dir = str(found.parent)
    path_env = os.environ.get("PATH", "")
    parts = path_env.split(os.pathsep) if path_env else []
    if bin_dir not in parts:
        os.environ["PATH"] = bin_dir + (os.pathsep + path_env if path_env else "")
    return found


def _output_not_writable_reason(output_path: Path) -> str | None:
    """Return an error message if we shouldn't write here, else None."""
    resolved = output_path.resolve()
    for part in resolved.parts:
        if part.endswith(".app"):
            return (
                "Save location is inside the app (read-only).\n\n"
                "Choose your Desktop or Documents folder instead."
            )
    parent = resolved.parent
    if not parent.is_dir():
        return f"Output folder does not exist:\n{parent}"
    probe = parent / ".videogen_write_test"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
    except OSError:
        return (
            f"Cannot write to:\n{parent}\n\n"
            "That folder is read-only (for example a DMG). "
            "Save to Desktop or Documents instead."
        )
    return None

# ── Dark cinematic palette (ui.theme) ──────────────────────────────────────
_BG = _ui_theme.BG
_PANEL = _ui_theme.PANEL
_PANEL_ALT = _ui_theme.PANEL_ALT
_CARD = _ui_theme.CARD
_CARD_HOVER = _ui_theme.CARD_HOVER
_ROW_ALT = _ui_theme.ROW_ALT
_BORDER = _ui_theme.BORDER
_TEXT = _ui_theme.TEXT
_MUTED = _ui_theme.MUTED
_ACCENT = _ui_theme.ACCENT
_ACCENT_HOV = _ui_theme.ACCENT_HOV
_ACCENT_DARK = _ui_theme.ACCENT_DARK
_ACCENT_SEL = _ui_theme.ACCENT_SEL
_ACCENT_BORDER = _ui_theme.ACCENT_BORDER
_SUCCESS = _ui_theme.SUCCESS
_PROCESSING = _ui_theme.PROCESSING
_QUEUED = _ui_theme.QUEUED
_WARNING = _ui_theme.WARNING
_DANGER = _ui_theme.DANGER
_DANGER_BG = _ui_theme.DANGER_BG
_SKIPPED = _ui_theme.SKIPPED
_COPPER = _ACCENT
# ───────────────────────────────────────────────────────────────────────────

SOURCE_BADGE = {
    AssetSource.FLOW_IMAGE: ("AI Image", _MUTED, "transparent"),
    AssetSource.FLOW_VIDEO: ("AI Video", _MUTED, "transparent"),
    AssetSource.STOCK: ("Stock", _MUTED, "transparent"),
    AssetSource.STOCK_IMAGE: ("Stock", _MUTED, "transparent"),
    AssetSource.STOCK_VIDEO: ("Stock", _MUTED, "transparent"),
    AssetSource.YOUTUBE_VIDEO: ("YouTube", _MUTED, "transparent"),
    AssetSource.ARCHIVE_VIDEO: ("Archive", _MUTED, "transparent"),
    AssetSource.NASA_VIDEO: ("NASA", _MUTED, "transparent"),
    AssetSource.COMMONS_VIDEO: ("Stock", _MUTED, "transparent"),
    AssetSource.COMMONS_IMAGE: ("Stock", _MUTED, "transparent"),
    AssetSource.MANUAL: ("Manual", _MUTED, "transparent"),
    AssetSource.LOCAL: ("Manual", _MUTED, "transparent"),
}

_UNASSIGNED_BADGE = ("Unassigned", _WARNING, "transparent")


def scene_source_badge(scene) -> tuple[str, str, str]:
    """Badge label for a scene row; unroutable AI rows are Unassigned, not Manual."""
    from providers.router import SceneAssetRouter

    source = SceneAssetRouter.classify(scene)
    if source is not None:
        return SOURCE_BADGE.get(
            source,
            (
                str(getattr(source, "value", source)).replace("_", " ").title(),
                _MUTED,
                "transparent",
            ),
        )
    if (getattr(scene, "asset_type", None) or "").strip().lower() == "local":
        return SOURCE_BADGE[AssetSource.LOCAL]
    return _UNASSIGNED_BADGE

STATUS_COLOR = {
    "waiting": _QUEUED,
    "queued": _QUEUED,
    "searching": _PROCESSING,
    "matching": _PROCESSING,
    "extracting": _PROCESSING,
    "generating": _PROCESSING,
    "downloading": _PROCESSING,
    "cancelling": _PROCESSING,
    "ready": _SUCCESS,
    "success": _SUCCESS,
    "failed": _DANGER,
    "needs_action": _WARNING,
    "timeout": _WARNING,
    "cancelled": _SKIPPED,
    "skipped": _SKIPPED,
    "rendering": _PROCESSING,
    "retrying": _PROCESSING,
    "using_alternative": _PROCESSING,
    "adding_local": _PROCESSING,
}


def _status_display(status: str) -> tuple[str, str]:
    """Return (label with icon, color) for scene status."""
    mapping = {
        "ready": ("✓ READY", _SUCCESS),
        "success": ("✓ READY", _SUCCESS),
        "generating": ("⟳ PROCESSING", _PROCESSING),
        "searching": ("⟳ PROCESSING", _PROCESSING),
        "downloading": ("⟳ PROCESSING", _PROCESSING),
        "extracting": ("⟳ PROCESSING", _PROCESSING),
        "matching": ("⟳ PROCESSING", _PROCESSING),
        "retrying": ("⟳ PROCESSING", _PROCESSING),
        "using_alternative": ("⟳ PROCESSING", _PROCESSING),
        "adding_local": ("⟳ PROCESSING", _PROCESSING),
        "rendering": ("⟳ PROCESSING", _PROCESSING),
        "cancelling": ("⟳ PROCESSING", _PROCESSING),
        "waiting": ("◌ QUEUED", _QUEUED),
        "queued": ("◌ QUEUED", _QUEUED),
        "needs_action": ("⚠ NEEDS ACTION", _WARNING),
        "failed": ("⚠ NEEDS ACTION", _WARNING),
        "timeout": ("⚠ NEEDS ACTION", _WARNING),
        "skipped": ("— SKIPPED", _SKIPPED),
        "cancelled": ("⊘ CANCELLED", _SKIPPED),
    }
    if status in mapping:
        return mapping[status]
    label = status.replace("_", " ").upper()
    return (label, _MUTED)

STAGE_PROGRESS = {
    "[0/4]": 5,
    "[1/4]": 25,
    "[2/4]": 50,
    "[3/4]": 70,
    "[4/4]": 95,
}


class _PipelineCancelled(Exception):
    """Raised inside _run_pipeline when asset resolution was cancelled by the user,
    so it can be routed to a distinct 'cancelled' outcome instead of 'error'."""


class _QueueWriter:
    """Redirect stdout/stderr into a thread-safe queue for the GUI log."""

    def __init__(self, q: queue.Queue, also: StringIO | None = None):
        self.q = q
        self.also = also
        self._buf = ""

    def write(self, text: str) -> int:
        if not text:
            return 0
        if self.also is not None:
            self.also.write(text)
        self._buf += text
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            self.q.put(("log", line + "\n"))
        return len(text)

    def flush(self) -> None:
        if self._buf:
            self.q.put(("log", self._buf))
            self._buf = ""


_STEPPER_STEPS = ("Script", "Scenes", "Assets", "Voice", "Render")
_STEPPER_DONE = _ui_theme.STEPPER_DONE
_PASTE_SCRIPT_MODES = frozenset({"Paste script", "Paste script", "AI Script"})


class VideoGeneratorApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Semantic YT Studio")
        self.geometry("1280x820")
        self.minsize(900, 600)
        self._qa_ui_dirty = False
        self._qa_ui_scheduled = False
        self._qa_persist_at = 0.0
        self._log_visible = False
        self._issues_visible = False
        self._log_backlog: list[str] = []
        self._scene_row_signature: tuple = ()
        self._selected_scene_key: str | None = None
        self._cta_action = "picker"
        self._stepper_index = 0
        self._stepper_compact = False
        self._chip_ellipsis = False
        self._project_chip_full = "No project"
        self._project_picker = None
        self._optional_open = False

        # Dark cinematic theme — premium production workspace
        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")
        self.configure(fg_color=_BG)

        self._ui_queue: queue.Queue = queue.Queue()
        self._worker: threading.Thread | None = None
        self._running = False
        self._last_output: str | None = None
        self._prev_image = None
        self._settings = load_settings()
        self._workspace = None
        self._project_menu_lock = False
        self._log_disk_buf: list[str] = []
        self._log_disk_scheduled = False
        # Windows CustomTkinter freezes if we process hundreds of scene events
        # (each forcing a full QA rebuild) in one poll tick.
        self._UI_QUEUE_BATCH = 48
        self._QA_UI_IDLE_MS = 50
        self._QA_UI_RUNNING_MS = 200
        raw_root = (self._settings.get("projects_root") or "").strip()
        self._projects_root = Path(raw_root) if raw_root else default_projects_root()

        # Asset pipeline state — built lazily on first use (main run or Regenerate)
        self._asset_manager: AssetManager | None = None
        self._flow_engine_manager = None
        # Guards the lazy-create-on-first-use below: Settings' auto-connect and a
        # user clicking Add Account can both race to create the FlowEngineManager
        # at nearly the same time. An unprotected "if None: create" here can create
        # TWO separate instances (each with its own internal lock, so neither one's
        # locking helps) — confirmed via a real concurrent-thread reproduction that
        # crashed the Flow engine with EADDRINUSE. See report.
        self._flow_engine_manager_lock = threading.Lock()
        self._auth_session = None  # licensing.AuthSession when signed in

        # Parent containers reused by helpers
        self._left_panel: ctk.CTkFrame | None = None
        self._right_panel: ctk.CTkFrame | None = None

        self._scene_render_gen = 0
        self._sfx_ready = False

        self._build_ui()
        self._apply_defaults()
        self._poll_queue()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        # Seed bundled SFX after first paint so startup isn't blocked on copy I/O.
        # ensure_sfx_library is idempotent; also re-checked before smart-editing mix.
        self.after_idle(self._ensure_sfx_ready)
        self.after_idle(self._ensure_licensed_then_picker)
    # ---------- UI ----------

    def _build_ui(self) -> None:
        self._set_window_icon()
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._init_ui_vars()

        self._shell = AppShell(
            self,
            on_nav=self._on_shell_nav,
            on_switch_project=self._open_project_picker,
            on_settings=self._open_settings,
            on_close_instances=self._close_flow_instances,
            on_primary_cta=self._on_primary_cta,
            on_toggle_issues=self._toggle_issues,
            project_chip_var=self._project_chip_var,
            stage_var=self.stage_var,
            hint_var=self.hint_var,
            qa_counter_var=self.qa_counter_var,
            status_line_var=self.status_line_var,
            cache_var=self.cache_status_var,
            logo_image=self._logo_ctk,
        )
        self._shell.grid(row=0, column=0, sticky="nsew")
        self._topbar = self._shell.topbar
        self.progress = self._shell.progress
        self.generate_btn = self._shell.generate_btn
        self.issues_toggle_btn = self._shell.issues_toggle_btn
        self._settings_btn = self._shell.settings_btn
        self._close_instances_btn = self._shell.close_instances_btn
        self._project_chip_label = self._shell.project_chip_label
        self._project_menu = None
        self.top_analyze_btn = None
        self._stepper_labels = []
        self._stepper_full = ctk.CTkFrame(self, fg_color="transparent")
        self._stepper_compact_label = ctk.CTkLabel(self, text="")
        self._stepper_compact_label.grid_remove()

        self._view_project = ui_views.ProjectView(self._shell.center, self)
        self._view_script = ui_views.ScriptView(self._shell.center, self)
        self._view_brand_style = ui_views.BrandStyleView(self._shell.center, self)
        self._view_research = ui_views.ResearchView(self._shell.center, self)
        self._view_visual = ui_views.VisualPlanView(self._shell.center, self)
        self._view_assets = ui_views.AssetsView(self._shell.center, self)
        self._view_audio = ui_views.AudioView(self._shell.center, self)
        self._view_music = ui_views.MusicView(self._shell.center, self)
        self._view_editorial = ui_views.EditorialView(self._shell.center, self)
        self._view_render = ui_views.RenderView(self._shell.center, self)
        self._view_qa = ui_views.QAView(self._shell.center, self)
        self._view_about = ui_views.AboutOwnershipView(self._shell.center, self)
        self._shell.center.grid_columnconfigure(0, weight=1)
        self._shell.center.grid_rowconfigure(0, weight=1)
        for key, view in (
            ("project", self._view_project),
            ("brand_style", self._view_brand_style),
            ("script", self._view_script),
            ("research", self._view_research),
            ("visual_plan", self._view_visual),
            ("assets", self._view_assets),
            ("audio", self._view_audio),
            ("music", self._view_music),
            ("editorial", self._view_editorial),
            ("render", self._view_render),
            ("qa", self._view_qa),
            ("about", self._view_about),
        ):
            self._shell.register_view(key, view)

        self._build_left_sections(parent=self._view_script.content)
        self._build_scenes_workspace(parent=self._view_visual.content)
        # Details panel is created inside inspector_body by _build_scenes_workspace.
        self._shell.navigate("script")
        self._refresh_cache_status()
        self._topbar.bind("<Configure>", self._on_topbar_configure, add="+")
        self._scene_window_first = 0
        self._scene_window_last = 0
        self._scene_window_bound = False
        self._scene_scroll_frac = 0.0
        self._editorial_plan_cache: dict | None = None
        self._editorial_plan_mtime = 0.0

    def _on_shell_nav(self, key: str) -> None:
        # Preserve Visual Plan scroll index across navigations.
        prev = getattr(self, "_shell_prev_view", None)
        if prev == "visual_plan" and key != "visual_plan":
            self._remember_scene_scroll()
        view = self._shell.views.get(key)
        if view is not None and hasattr(view, "on_show"):
            try:
                view.on_show()
            except Exception as exc:
                self._append_log(f"[UI] View refresh skipped ({exc})\n")
        if key == "visual_plan" and prev != "visual_plan":
            self.after_idle(self._restore_scene_scroll)
        self._shell_prev_view = key
        self._refresh_cache_status()

    def _goto_workflow_view(self, key: str) -> None:
        """Move the shell sidebar to the next workflow stage after a task completes."""
        shell = getattr(self, "_shell", None)
        if shell is None:
            return
        try:
            shell.navigate(key)
        except Exception:
            return

    def _open_issues_drawer(self) -> None:
        """Show Issues drawer when unresolved scenes exist (Need Attention / bulk retry)."""
        snap = self._qa_snapshot() if self._scene_rows else None
        if snap is None or not snap.needs_action:
            return
        drawer = getattr(self, "_issues_drawer", None)
        if drawer is None:
            return
        self._issues_visible = True
        try:
            drawer.grid(row=2, column=0, sticky="ew", padx=16, pady=(8, 0))
        except Exception:
            return
        self._rebuild_issues(snap)

    def _refresh_cache_status(self) -> None:
        ws = self._workspace
        if ws is None:
            self.cache_status_var.set("No project")
            return
        bits = []
        if (ws.state_dir / "editorial_plan.json").is_file():
            bits.append("Editorial")
        if (ws.state_dir / "smart_editing.json").is_file():
            bits.append("Smart")
        if (ws.state_dir / "editorial_qa.json").is_file():
            bits.append("QA")
        self.cache_status_var.set("Cached: " + ", ".join(bits) if bits else "Cache empty")

    def _mount_inspector_into_shell(self) -> None:
        """No-op: details are parented to inspector_body at build time."""
        return

    def _ensure_details_in_inspector(self) -> None:
        panel = getattr(self, "_details_panel", None)
        if panel is None:
            return
        try:
            panel.grid()
        except Exception:
            pass

    def _load_editorial_plan_cached(self) -> dict:
        """Read editorial_plan.json only when mtime changes (no rebuild)."""
        ws = self._workspace
        if ws is None:
            self._editorial_plan_cache = None
            return {}
        path = ws.state_dir / "editorial_plan.json"
        try:
            mtime = path.stat().st_mtime if path.is_file() else 0.0
        except OSError:
            return self._editorial_plan_cache or {}
        if self._editorial_plan_cache is not None and mtime == self._editorial_plan_mtime:
            return self._editorial_plan_cache
        data = {}
        if mtime:
            try:
                import json
                raw = json.loads(path.read_text(encoding="utf-8"))
                data = raw if isinstance(raw, dict) else {}
            except (OSError, ValueError):
                data = {}
        self._editorial_plan_cache = data
        self._editorial_plan_mtime = mtime
        return data

    def _editorial_scene_lookup(self, scene_number) -> dict:
        plan = self._load_editorial_plan_cached()
        key = str(scene_number)
        for s in plan.get("scenes") or []:
            if str(s.get("scene_number")) == key:
                return s
            try:
                if int(str(s.get("scene_number"))) == int(str(scene_number)):
                    return s
            except (TypeError, ValueError):
                continue
        return {}

    @staticmethod
    def _format_scene_timecode(seconds: float) -> str:
        s = max(0.0, float(seconds or 0.0))
        m = int(s // 60)
        rem = s - m * 60
        return f"{m}:{rem:04.1f}"

    def _scene_time_label(self, scene_number) -> str:
        """Timeline window for this scene (from editorial plan after align/render)."""
        ed = self._editorial_scene_lookup(scene_number)
        try:
            start = float(ed.get("start"))
            end = float(ed.get("end"))
        except (TypeError, ValueError):
            return "—"
        if end <= 0 and start <= 0:
            return "—"
        if end < start:
            end = start
        return f"{self._format_scene_timecode(start)}–{self._format_scene_timecode(end)}"

    def _scene_asset_path(self, scene_number) -> Path | None:
        key = _scene_key(scene_number)
        result = self._asset_results.get(key)
        path = getattr(result, "path", None) if result is not None else None
        if path is not None and Path(path).is_file():
            return Path(path)
        images = self.images_var.get().strip()
        if not images:
            return None
        found = vg.find_image_for_scene(Path(images), scene_number)
        return found if found is not None and found.is_file() else None

    def _open_scene_asset(self, scene_number) -> None:
        path = self._scene_asset_path(scene_number)
        if path is None:
            messagebox.showinfo(
                "Open clip",
                f"No media file found for scene {scene_number} yet.",
            )
            return
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            elif sys.platform == "win32":
                os.startfile(str(path))  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", str(path)])
            self.status_var.set(f"Opened scene {scene_number}: {path.name}")
        except Exception as exc:
            messagebox.showerror("Open clip", str(exc))

    def _init_ui_vars(self) -> None:
        self.csv_var = ctk.StringVar()
        self.audio_var = ctk.StringVar()
        self.images_var = ctk.StringVar()
        self.bg_var = ctk.StringVar()
        self.output_var = ctk.StringVar()
        self.model_var = ctk.StringVar(value="small")
        self.captions_var = ctk.BooleanVar(value=False)
        self.zoom_var = ctk.BooleanVar(value=True)
        self.smart_text_effects_var = ctk.BooleanVar(
            value=bool(self._settings.get("smart_text_effects", DEFAULT_SETTINGS["text_effects"]))
        )
        self.smart_sfx_var = ctk.BooleanVar(
            value=bool(self._settings.get("smart_sound_effects", DEFAULT_SETTINGS["sound_effects"]))
        )
        self.smart_visual_transitions_var = ctk.BooleanVar(
            value=bool(
                self._settings.get(
                    "smart_visual_transitions",
                    DEFAULT_SETTINGS.get("visual_transitions", True),
                )
            )
        )
        self.smart_scene_ambience_var = ctk.BooleanVar(
            value=bool(
                self._settings.get(
                    "smart_scene_ambience",
                    DEFAULT_SETTINGS.get("scene_ambience", True),
                )
            )
        )
        def _smart_intensity_label(key: str, fallback_key: str = "intensity") -> str:
            raw = str(
                self._settings.get(key)
                or self._settings.get(f"smart_{fallback_key}", DEFAULT_SETTINGS.get(fallback_key, "medium"))
                or "medium"
            ).strip().title()
            return raw if raw in {"Low", "Medium", "High"} else "Medium"

        legacy = _smart_intensity_label("smart_intensity", "intensity")
        self.smart_text_intensity_var = ctk.StringVar(
            value=_smart_intensity_label("smart_text_effects_intensity") if self._settings.get("smart_text_effects_intensity") else legacy
        )
        self.smart_sfx_intensity_var = ctk.StringVar(
            value=_smart_intensity_label("smart_sound_effects_intensity") if self._settings.get("smart_sound_effects_intensity") else legacy
        )
        self.smart_transitions_intensity_var = ctk.StringVar(
            value=_smart_intensity_label("smart_visual_transitions_intensity") if self._settings.get("smart_visual_transitions_intensity") else legacy
        )
        self.smart_ambience_intensity_var = ctk.StringVar(
            value=_smart_intensity_label("smart_scene_ambience_intensity") if self._settings.get("smart_scene_ambience_intensity") else legacy
        )
        # Ambience bed level. -1.0 is the sentinel for "auto" (follow the
        # intensity step) because a Tk DoubleVar cannot hold None.
        _amb_vol = normalize_ambience_volume(
            self._settings.get("smart_scene_ambience_volume")
        )
        self.smart_ambience_volume_var = ctk.DoubleVar(
            value=-1.0 if _amb_vol is None else _amb_vol
        )
        # Keep legacy var in sync for any leftover reads.
        self.smart_intensity_var = self.smart_sfx_intensity_var
        self.smart_mode_var = ctk.StringVar(
            value=str(self._settings.get("smart_mode", DEFAULT_SETTINGS["mode"]))
        )
        self.pexels_key_var = ctk.StringVar(value=self._settings.get("pexels_api_key", ""))
        self.pixabay_key_var = ctk.StringVar(value=self._settings.get("pixabay_api_key", ""))
        self.gemini_key_var = ctk.StringVar(value=self._settings.get("gemini_api_key", ""))
        self._visual_plan = None
        self._manual_csv_backup = ""
        self.youtube_clip_duration_var = ctk.StringVar(
            value=str(self._settings.get("youtube_clip_duration", 3.5))
        )
        self.youtube_search_results_var = ctk.StringVar(
            value=str(self._settings.get("youtube_search_results", 5))
        )
        self.youtube_transcript_matching_var = ctk.BooleanVar(
            value=self._settings.get("youtube_transcript_matching", True)
        )
        self.current_project_title_var = ctk.StringVar(value="No project")
        self.current_project_meta_var = ctk.StringVar(value="Choose a project to start")
        self.project_menu_var = ctk.StringVar(value="(none)")
        self._project_chip_var = ctk.StringVar(value="No project")
        self._project_labels: dict[str, str] = {}
        self.stage_var = ctk.StringVar(value="SCRIPT")
        self.prod_ready_var = ctk.StringVar(value="")
        self.prod_processing_var = ctk.StringVar(value="")
        self.prod_queued_var = ctk.StringVar(value="")
        self.prod_needs_var = ctk.StringVar(value="")
        self.prod_mix_var = ctk.StringVar(value="")
        self.hint_var = ctk.StringVar(value="Choose a project to get started.")
        self.status_var = ctk.StringVar(value="Ready")
        self.status_line_var = ctk.StringVar(value="")
        self.cache_status_var = ctk.StringVar(value="Cache idle")
        self.qa_counter_var = ctk.StringVar(value="")
        self.prod_error_var = ctk.StringVar(value="")
        self.scenes_summary_var = ctk.StringVar(value="")
        self.qa_health_var = ctk.StringVar(value="")
        self.error_pos_var = ctk.StringVar(value="0 / 0")
        self.scene_search_var = ctk.StringVar(value="")
        self.qa_bulk_progress_var = ctk.StringVar(value="")
        self.issues_header_var = ctk.StringVar(value="No issues")
        self.details_text_var = ctk.StringVar(value="")
        self.voiceover_active_var = ctk.StringVar(value="No voiceover yet — needed to render")
        self.voice_play_progress_var = ctk.StringVar(value="")
        flow_saved = self._settings.get("flow_settings", {})
        self.flow_image_model_var = ctk.StringVar(value=flow_saved.get("model", FLOW_IMAGE_MODELS[1][0]))
        self.flow_image_aspect_var = ctk.StringVar(
            value=flow_saved.get("aspectRatio", FLOW_IMAGE_ASPECT_RATIOS[0][0])
        )
        self._known_flow_accounts: list[dict] = []
        self._logo_ctk = None
        logo_path = _logo_path()
        if logo_path is not None:
            self._logo_ctk, _ = _logo_ctk_image(32)

    def _build_topbar(self) -> None:
        topbar = ctk.CTkFrame(self, fg_color=_PANEL, corner_radius=0)
        topbar.grid(row=0, column=0, columnspan=2, sticky="ew")
        topbar.grid_columnconfigure(1, weight=1)
        self._topbar = topbar

        left_zone = ctk.CTkFrame(topbar, fg_color="transparent")
        left_zone.grid(row=0, column=0, sticky="w", padx=(12, 8), pady=8)
        if self._logo_ctk is not None:
            ctk.CTkLabel(
                left_zone, image=self._logo_ctk, text="", fg_color="transparent",
            ).pack(side="left", padx=(0, 8))
        chip = ctk.CTkFrame(
            left_zone, fg_color=_CARD, corner_radius=8, border_width=1, border_color=_BORDER,
        )
        chip.pack(side="left", padx=(0, 6))
        self._project_chip_label = ctk.CTkLabel(
            chip, textvariable=self._project_chip_var,
            font=ctk.CTkFont(size=13, weight="bold"), text_color=_TEXT,
        )
        self._project_chip_label.pack(side="left", padx=10, pady=6)
        self._switch_btn = ctk.CTkButton(
            left_zone, text="Switch", width=72, height=30,
            fg_color="transparent", border_width=1, border_color=_BORDER,
            text_color=_TEXT, hover_color=_CARD_HOVER, font=ctk.CTkFont(size=12),
            command=self._open_project_picker,
        )
        self._switch_btn.pack(side="left")

        mid = ctk.CTkFrame(topbar, fg_color="transparent")
        mid.grid(row=0, column=1, sticky="ew", padx=8)
        mid.grid_columnconfigure(0, weight=1)
        self._stepper_full = ctk.CTkFrame(mid, fg_color="transparent")
        self._stepper_full.grid(row=0, column=0)
        self._stepper_labels: list[ctk.CTkLabel] = []
        for i, name in enumerate(_STEPPER_STEPS):
            if i:
                ctk.CTkLabel(
                    self._stepper_full, text="→", font=ctk.CTkFont(size=11),
                    text_color=_BORDER,
                ).pack(side="left", padx=4)
            lbl = ctk.CTkLabel(
                self._stepper_full, text=name,
                font=ctk.CTkFont(size=12, weight="bold"), text_color=_MUTED,
            )
            lbl.pack(side="left")
            self._stepper_labels.append(lbl)
        self._stepper_compact_label = ctk.CTkLabel(
            mid, text="Step 1 of 5 · Script",
            font=ctk.CTkFont(size=12, weight="bold"), text_color=_ACCENT,
        )
        self._stepper_compact_label.grid(row=0, column=0)
        self._stepper_compact_label.grid_remove()

        right_zone = ctk.CTkFrame(topbar, fg_color="transparent")
        right_zone.grid(row=0, column=2, sticky="e", padx=(8, 12), pady=8)
        self.issues_toggle_btn = ctk.CTkButton(
            right_zone, textvariable=self.qa_counter_var, width=88, height=30,
            fg_color="transparent", border_width=1, border_color=_DANGER,
            text_color=_DANGER, hover_color=_DANGER_BG, font=ctk.CTkFont(size=11, weight="bold"),
            command=self._toggle_issues,
        )
        self.issues_toggle_btn.pack(side="left", padx=(0, 6))
        self.issues_toggle_btn.pack_forget()
        self._close_instances_btn = ctk.CTkButton(
            right_zone, text="Close instances", width=118, height=30,
            fg_color="transparent", border_width=1, border_color=_BORDER,
            text_color=_TEXT, hover_color=_CARD_HOVER, font=ctk.CTkFont(size=11),
            command=self._close_flow_instances,
        )
        self._close_instances_btn.pack(side="left", padx=(0, 6))
        self._settings_btn = ctk.CTkButton(
            right_zone, text="⚙", width=36, height=30,
            fg_color="transparent", border_width=1, border_color=_BORDER,
            text_color=_TEXT, hover_color=_CARD_HOVER, font=ctk.CTkFont(size=16),
            command=self._open_settings,
        )
        self._settings_btn.pack(side="left")

        # Compatibility no-ops: option menu and top Analyze were removed.
        self._project_menu = None
        self.top_analyze_btn = None

        self.progress = ctk.CTkProgressBar(
            topbar, height=4, progress_color=_ACCENT, fg_color=_BORDER, corner_radius=2,
        )
        self.progress.grid(row=1, column=0, columnspan=3, sticky="ew")
        self.progress.set(0)

        topbar.bind("<Configure>", self._on_topbar_configure, add="+")
        self._refresh_stepper()

    def _build_left_sections(self, parent=None) -> None:
        left = parent if parent is not None else ctk.CTkFrame(self, fg_color=_PANEL, corner_radius=0)
        if parent is None:
            left.grid(row=1, column=0, sticky="nsew")
        left.grid_columnconfigure(0, weight=1)
        left.grid_rowconfigure(0, weight=1)
        self._left_panel = left

        scroll = ctk.CTkScrollableFrame(
            left,
            fg_color="transparent",
            scrollbar_button_color=_BORDER,
            scrollbar_button_hover_color=_ACCENT,
        )
        scroll.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)
        scroll.grid_columnconfigure(0, weight=1)
        self._scroll = scroll

        mode_wrap = ctk.CTkFrame(scroll, fg_color="transparent")
        mode_wrap.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 0))
        mode_wrap.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            mode_wrap, text="Script", font=ctk.CTkFont(size=12, weight="bold"),
            text_color=_TEXT, anchor="w",
        ).grid(row=0, column=0, sticky="w")
        self._mode_seg = ctk.CTkSegmentedButton(
            mode_wrap,
            values=["Paste script", "Import CSV"],
            fg_color=_BORDER,
            selected_color=_ACCENT,
            selected_hover_color=_ACCENT_HOV,
            unselected_color=_CARD,
            unselected_hover_color=_CARD_HOVER,
            text_color=_TEXT,
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        self._mode_seg.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        self._mode_seg.set("Paste script")

        self._csv_block = ctk.CTkFrame(scroll, fg_color="transparent")
        self._csv_block.grid(row=1, column=0, sticky="ew", padx=16, pady=(8, 0))
        self._csv_block.grid_columnconfigure(0, weight=1)
        self._path_row(
            0, "", self.csv_var, self._browse_csv, parent=self._csv_block,
            placeholder_text="Choose a visual-plan CSV…",
        )
        self._csv_block.grid_remove()

        self._ai_block = ctk.CTkFrame(
            scroll, fg_color=_CARD, corner_radius=6, border_width=1, border_color=_BORDER,
        )
        self._ai_block.grid(row=1, column=0, sticky="ew", padx=16, pady=(10, 0))
        self._ai_block.grid_columnconfigure(0, weight=1)
        self._gemini_status_var = ctk.StringVar(value="")
        self._gemini_status_label = ctk.CTkLabel(
            self._ai_block, textvariable=self._gemini_status_var, font=ctk.CTkFont(size=11),
            text_color=_MUTED, wraplength=200, justify="left", anchor="w",
        )
        self._gemini_status_label.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 0))
        self._bind_responsive_wrap(self._gemini_status_label, pad=24)

        script_host = ctk.CTkFrame(self._ai_block, fg_color="transparent")
        script_host.grid(row=1, column=0, sticky="ew", padx=12, pady=(6, 8))
        script_host.grid_columnconfigure(0, weight=1)
        self.script_box = ctk.CTkTextbox(
            script_host, height=150, fg_color=_BG, border_color=_BORDER, border_width=1,
            text_color=_TEXT, font=ctk.CTkFont(size=12), wrap="word",
        )
        self.script_box.grid(row=0, column=0, sticky="ew")
        self._script_watermark = ctk.CTkLabel(
            script_host,
            text="Paste your narration script here…",
            font=ctk.CTkFont(size=12),
            text_color=_MUTED,
            anchor="nw",
            justify="left",
        )
        self._script_watermark.place(in_=self.script_box, x=10, y=8)
        self.script_box.bind("<KeyRelease>", lambda _e: self._sync_script_watermark())
        self.script_box.bind("<ButtonRelease-1>", lambda _e: self._sync_script_watermark())
        self.script_box.bind("<FocusIn>", lambda _e: self._sync_script_watermark())
        self.script_box.bind("<FocusOut>", lambda _e: self._sync_script_watermark())

        ai_btns = ctk.CTkFrame(self._ai_block, fg_color="transparent")
        ai_btns.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 12))
        ai_btns.grid_columnconfigure(0, weight=1)
        self.analyze_btn = ctk.CTkButton(
            ai_btns, text="Analyze Script", height=34, fg_color=_ACCENT, hover_color=_ACCENT_HOV,
            text_color=_ACCENT_DARK, font=ctk.CTkFont(size=13, weight="bold"),
            command=self._on_analyze_script,
        )
        self.analyze_btn.grid(row=0, column=0, sticky="ew")
        self._export_csv_btn = ctk.CTkButton(
            ai_btns, text="Export CSV", width=88, height=28, fg_color="transparent",
            border_width=0, text_color=_ACCENT, hover_color=_CARD_HOVER,
            font=ctk.CTkFont(size=12, underline=True),
            command=self._export_ai_csv,
        )
        self._export_csv_btn.grid(row=1, column=0, sticky="w", pady=(6, 0))
        self._export_csv_btn.grid_remove()
        self._refresh_gemini_status()

        voice_panel = ctk.CTkFrame(
            scroll, fg_color=_CARD, corner_radius=6, border_width=1, border_color=_BORDER,
        )
        voice_panel.grid(row=2, column=0, sticky="ew", padx=16, pady=(10, 0))
        voice_panel.grid_columnconfigure(0, weight=1)
        self._voice_panel = voice_panel
        ctk.CTkLabel(
            voice_panel, text="Voiceover",
            font=ctk.CTkFont(size=12, weight="bold"), text_color=_TEXT, anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(10, 0))
        self._path_row(
            1, "", self.audio_var, self._browse_audio, parent=voice_panel,
            placeholder_text="Choose narration audio (MP3, WAV, M4A)…",
        )

        voice_play_row = ctk.CTkFrame(voice_panel, fg_color="transparent")
        voice_play_row.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 4))
        voice_play_row.grid_columnconfigure(0, weight=1)
        self._play_voice_btn = ctk.CTkButton(
            voice_play_row,
            text="▶  Play",
            height=30,
            fg_color="transparent",
            border_width=1,
            border_color=_BORDER,
            text_color=_ACCENT,
            hover_color=_BORDER,
            font=ctk.CTkFont(size=12),
            command=self._toggle_voice_playback,
            state="disabled",
        )
        self._play_voice_btn.grid(row=0, column=0, sticky="w")
        self._stop_voice_btn = None
        self._voice_play_proc: subprocess.Popen | None = None
        self._voice_play_t0: float | None = None
        self._voice_play_duration = 0.0
        self._voice_play_paused = False
        self._voice_play_paused_at = 0.0
        self._voice_play_path: Path | None = None

        self.voice_play_progress = ctk.CTkProgressBar(
            voice_panel,
            height=8,
            progress_color=_ACCENT,
            fg_color=_BORDER,
            corner_radius=4,
        )
        self.voice_play_progress.grid(row=3, column=0, sticky="ew", padx=12, pady=(0, 2))
        self.voice_play_progress.set(0)
        self.voice_play_progress.grid_remove()
        self.voice_play_progress_label = ctk.CTkLabel(
            voice_panel,
            textvariable=self.voice_play_progress_var,
            font=ctk.CTkFont(size=11),
            text_color=_MUTED,
            anchor="w",
        )
        self.voice_play_progress_label.grid(row=4, column=0, sticky="ew", padx=12, pady=(0, 4))
        self.voice_play_progress_label.grid_remove()
        self._voiceover_active_label = ctk.CTkLabel(
            voice_panel,
            textvariable=self.voiceover_active_var,
            font=ctk.CTkFont(size=11),
            text_color=_MUTED,
            wraplength=200,
            justify="left",
            anchor="w",
        )
        self._voiceover_active_label.grid(row=5, column=0, sticky="ew", padx=12, pady=(0, 10))
        self._bind_responsive_wrap(self._voiceover_active_label, pad=24)
        self._refresh_voice_playback_buttons()

        self._optional_toggle = ctk.CTkButton(
            scroll, text="Optional +", height=28, width=100, anchor="w",
            fg_color="transparent", hover_color=_CARD_HOVER,
            text_color=_MUTED, font=ctk.CTkFont(size=12),
            command=self._toggle_optional_section,
        )
        self._optional_toggle.grid(row=3, column=0, sticky="w", padx=16, pady=(8, 0))
        self._optional_block = ctk.CTkFrame(scroll, fg_color="transparent")
        self._optional_block.grid(row=4, column=0, sticky="ew", padx=16)
        self._optional_block.grid_columnconfigure(0, weight=1)
        self._path_row(
            0, "Background music", self.bg_var, self._browse_bg,
            clearable=True, parent=self._optional_block,
            placeholder_text="Optional background track…",
        )
        self._optional_block.grid_remove()

        opts = ctk.CTkFrame(scroll, fg_color="transparent")
        opts.grid(row=7, column=0, sticky="ew", padx=16, pady=(12, 4))
        opts.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            opts, text="Whisper Model",
            font=ctk.CTkFont(size=11),
            text_color=_MUTED,
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkOptionMenu(
            opts,
            variable=self.model_var,
            values=["tiny", "base", "small", "medium", "large-v3"],
            width=130,
            fg_color=_CARD,
            button_color=_BORDER,
            button_hover_color=_ACCENT,
            text_color=_TEXT,
            dropdown_fg_color=_CARD,
            dropdown_text_color=_TEXT,
            dropdown_hover_color=_BORDER,
        ).grid(row=0, column=1, sticky="w", padx=(10, 0))
        ctk.CTkSwitch(
            opts,
            text="Ken Burns Zoom",
            variable=self.zoom_var,
            onvalue=True,
            offvalue=False,
            progress_color=_ACCENT,
            button_color=_TEXT,
            button_hover_color=_ACCENT,
            text_color=_COPPER,
            font=ctk.CTkFont(size=12),
        ).grid(row=0, column=2, sticky="e", padx=(14, 0))
        ctk.CTkSwitch(
            opts,
            text="Captions",
            variable=self.captions_var,
            onvalue=True,
            offvalue=False,
            progress_color=_ACCENT,
            button_color=_TEXT,
            button_hover_color=_ACCENT,
            text_color=_COPPER,
            font=ctk.CTkFont(size=12),
        ).grid(row=0, column=3, sticky="e", padx=(14, 0))
        opts.grid_remove()

        bottom = ctk.CTkFrame(left, fg_color=_PANEL, corner_radius=0)
        bottom.grid(row=1, column=0, sticky="ew")
        bottom.grid_columnconfigure(0, weight=1)
        # Primary CTA lives in the shell topbar; keep cancel + hint locally for Script view.
        ctk.CTkFrame(bottom, fg_color=_BORDER, height=1, corner_radius=0).grid(
            row=0, column=0, sticky="ew"
        )
        self._hint_label = ctk.CTkLabel(
            bottom, textvariable=self.hint_var, font=ctk.CTkFont(size=11),
            text_color=_MUTED, wraplength=200, justify="left", anchor="w",
        )
        self._hint_label.grid(row=1, column=0, sticky="ew", padx=16, pady=(8, 0))
        self._bind_responsive_wrap(self._hint_label, pad=32)

        cta_row = ctk.CTkFrame(bottom, fg_color="transparent")
        cta_row.grid(row=2, column=0, sticky="ew", padx=16, pady=(6, 12))
        cta_row.grid_columnconfigure(0, weight=1)
        self._cta_row = cta_row
        # Reuse shell CTA if already created; otherwise create legacy button.
        if getattr(self, "generate_btn", None) is None:
            self.generate_btn = ctk.CTkButton(
                cta_row,
                text="Choose project",
                height=40,
                fg_color=_ACCENT,
                hover_color=_ACCENT_HOV,
                text_color=_ACCENT_DARK,
                font=ctk.CTkFont(size=14, weight="bold"),
                corner_radius=6,
                command=self._on_primary_cta,
            )
            self.generate_btn.grid(row=0, column=0, sticky="ew")
        self._mode_seg.configure(command=self._on_script_mode)

        self.cancel_btn = ctk.CTkButton(
            cta_row,
            text="Cancel",
            width=90,
            height=32,
            fg_color="transparent",
            border_width=1,
            border_color=_DANGER,
            text_color=_DANGER,
            hover_color=_DANGER_BG,
            font=ctk.CTkFont(size=12, weight="bold"),
            corner_radius=6,
            command=self._on_cancel,
        )
        # Cancel shown only while running via existing helpers; keep packed off by default.

    def _build_scenes_workspace(self, parent=None) -> None:
        right = parent if parent is not None else ctk.CTkFrame(self, fg_color=_PANEL_ALT, corner_radius=0)
        if parent is None:
            right.grid(row=1, column=1, sticky="nsew")
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(0, weight=0)
        right.grid_rowconfigure(1, weight=1)
        self._right_panel = right

        # Compact production toolbar — one line, no duplicate titles.
        act_header = ctk.CTkFrame(right, fg_color="transparent", height=36)
        act_header.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 2))
        act_header.grid_propagate(False)
        act_header.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            act_header, text="Visual Plan",
            font=ctk.CTkFont(size=14, weight="bold"), text_color=_TEXT,
        ).grid(row=0, column=0, sticky="w")
        self._scenes_counts_label = ctk.CTkLabel(
            act_header, textvariable=self.scenes_summary_var,
            font=ctk.CTkFont(size=11), text_color=_MUTED,
            wraplength=520, justify="left", anchor="w",
        )
        self._scenes_counts_label.grid(row=0, column=1, sticky="ew", padx=(10, 6))
        self._bind_responsive_wrap(self._scenes_counts_label, pad=16)
        self._error_nav = ctk.CTkFrame(act_header, fg_color="transparent")
        self._error_nav.grid(row=0, column=2, sticky="e", padx=(0, 4))
        self.goto_error_btn = ctk.CTkButton(
            self._error_nav, text="Go to Error", width=96, height=24,
            fg_color=_WARNING, hover_color="#D97706", text_color="#0B0D10",
            font=ctk.CTkFont(size=11, weight="bold"), corner_radius=4,
            command=self._go_to_error,
        )
        self.goto_error_btn.pack(side="left", padx=(0, 4))
        self.prev_error_btn = ctk.CTkButton(
            self._error_nav, text="←", width=28, height=22,
            fg_color="transparent", border_width=1, border_color=_BORDER,
            text_color=_ACCENT, hover_color=_ACCENT_SEL, font=ctk.CTkFont(size=11),
            corner_radius=4, command=self._prev_error,
        )
        self.prev_error_btn.pack(side="left")
        ctk.CTkLabel(
            self._error_nav, textvariable=self.error_pos_var, font=ctk.CTkFont(size=11),
            text_color=_MUTED, width=44,
        ).pack(side="left", padx=2)
        self.next_error_btn = ctk.CTkButton(
            self._error_nav, text="→", width=28, height=22,
            fg_color="transparent", border_width=1, border_color=_BORDER,
            text_color=_ACCENT, hover_color=_ACCENT_SEL, font=ctk.CTkFont(size=10),
            corner_radius=4, command=self._next_error,
        )
        self.next_error_btn.pack(side="left")
        self._error_nav.grid_remove()

        self._overflow_btn = ctk.CTkButton(
            act_header, text="⋯", width=30, height=24,
            fg_color="transparent", border_width=1, border_color=_BORDER,
            text_color=_MUTED, hover_color=_CARD_HOVER, font=ctk.CTkFont(size=14),
            command=self._open_workspace_overflow,
        )
        self._overflow_btn.grid(row=0, column=3, sticky="e")

        # Hidden compatibility widgets (state still updated by existing helpers).
        self.cleanup_assets_btn = ctk.CTkButton(
            right, text="Cleanup", width=1, height=1,
            command=self._on_cleanup_downloaded_assets, state="disabled",
        )
        self.log_toggle_btn = ctk.CTkButton(
            right, text="Activity ▸", width=1, height=1,
            command=self._toggle_activity_log,
        )

        scenes_wrap = ctk.CTkFrame(right, fg_color=_CARD, corner_radius=4, border_width=1, border_color=_BORDER)
        scenes_wrap.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 8))
        scenes_wrap.grid_columnconfigure(0, weight=1)
        scenes_wrap.grid_rowconfigure(2, weight=1)
        self._scenes_wrap = scenes_wrap

        # Compatibility: filter API still exists but search UI was removed.
        self.scene_search_entry = None
        self.scene_search_var.set("")

        self._qa_bulk_progress_label = ctk.CTkLabel(
            scenes_wrap, textvariable=self.qa_bulk_progress_var,
            font=ctk.CTkFont(size=11), text_color=_COPPER, anchor="w",
        )
        self._qa_bulk_progress_label.grid(row=0, column=0, sticky="ew", padx=8, pady=0)
        self._qa_bulk_progress_label.grid_remove()

        self._scenes_empty_label = ctk.CTkLabel(
            scenes_wrap,
            text="Paste a script and analyze it, or import a visual-plan CSV, to see scenes here.",
            text_color=_MUTED, font=ctk.CTkFont(size=12), justify="left", anchor="w",
            wraplength=200,
        )
        self._scenes_empty_label.grid(row=1, column=0, sticky="ew", padx=12, pady=(6, 2))
        self._bind_responsive_wrap(self._scenes_empty_label, pad=24)

        self._scenes_list = ctk.CTkScrollableFrame(
            scenes_wrap, fg_color="transparent",
            scrollbar_button_color=_BORDER, scrollbar_button_hover_color=_ACCENT,
        )
        self._scenes_list.grid(row=2, column=0, sticky="nsew", padx=4, pady=(0, 4))
        self._scenes_list.grid_columnconfigure(0, weight=1)

        # Details live in the shell inspector (cannot reparent into CTkScrollableFrame).
        insp_parent = getattr(getattr(self, "_shell", None), "inspector_body", None)
        details_col = ctk.CTkFrame(
            insp_parent if insp_parent is not None else scenes_wrap,
            fg_color="transparent", corner_radius=4, border_width=0,
        )
        self._details_panel = details_col
        if insp_parent is not None:
            details_col.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
            insp_parent.grid_rowconfigure(0, weight=1)
        self.details_title_var = ctk.StringVar(value="Selected scene")
        ctk.CTkLabel(
            details_col, textvariable=self.details_title_var, font=ctk.CTkFont(size=11, weight="bold"),
            text_color=_MUTED, anchor="w",
        ).pack(fill="x", padx=8, pady=(6, 0))
        self._details_text_label = ctk.CTkLabel(
            details_col, textvariable=self.details_text_var, font=ctk.CTkFont(size=11),
            text_color=_TEXT, anchor="nw", justify="left", wraplength=200,
        )
        self._details_text_label.pack(fill="both", expand=True, padx=8, pady=(2, 4))
        self._bind_responsive_wrap(self._details_text_label, pad=24)
        details_actions = ctk.CTkFrame(details_col, fg_color="transparent")
        details_actions.pack(fill="x", padx=8, pady=(0, 6))
        self._details_actions = details_actions
        self.details_source_btn = ctk.CTkButton(
            details_actions, text="Source", width=90, height=28,
            fg_color="transparent", border_width=1, border_color=_BORDER,
            text_color=_ACCENT, font=ctk.CTkFont(size=11),
            command=lambda: self._details_action("change_source"),
        )
        self.details_local_btn = ctk.CTkButton(
            details_actions, text="Local clip", width=90, height=28,
            font=ctk.CTkFont(size=11, weight="bold"), command=lambda: self._details_action("local_clip"),
        )
        self.details_open_btn = ctk.CTkButton(
            details_actions, text="Open", width=70, height=28,
            fg_color="transparent", border_width=1, border_color=_BORDER,
            text_color=_SUCCESS, font=ctk.CTkFont(size=11, weight="bold"),
            command=lambda: self._details_action("open"),
        )
        self.details_open_btn._inspector_show = False
        self.details_retry_btn = ctk.CTkButton(
            details_actions, text="Retry", width=70, height=28,
            font=ctk.CTkFont(size=11, weight="bold"), command=lambda: self._details_action("retry"),
        )
        self.details_alt_btn = ctk.CTkButton(
            details_actions, text="Alt", width=70, height=28,
            font=ctk.CTkFont(size=11, weight="bold"), command=lambda: self._details_action("alternative"),
        )
        self.details_skip_btn = ctk.CTkButton(
            details_actions, text="Skip", width=70, height=28,
            fg_color="transparent", border_width=1, border_color=_BORDER,
            text_color=_DANGER, font=ctk.CTkFont(size=11, weight="bold"),
            command=lambda: self._details_action("skip"),
        )
        self.details_stop_btn = ctk.CTkButton(
            details_actions, text="Stop", width=70, height=28,
            fg_color="transparent", border_width=1, border_color=_DANGER,
            text_color=_DANGER, font=ctk.CTkFont(size=11, weight="bold"),
            command=lambda: self._details_action("cancel"),
        )
        self.details_stop_btn.configure(state="disabled")
        details_actions.bind("<Configure>", self._on_inspector_configure, add="+")
        self._layout_inspector_actions()

        self._issues_drawer = ctk.CTkFrame(right, fg_color=_CARD, corner_radius=6, border_width=1, border_color=_BORDER)
        qa_bulk = ctk.CTkFrame(self._issues_drawer, fg_color="transparent")
        qa_bulk.pack(fill="x", padx=10, pady=(8, 4))
        self.retry_failed_btn = ctk.CTkButton(
            qa_bulk, text="Retry failed", width=110, height=24,
            fg_color="transparent", border_width=1, border_color=_BORDER,
            text_color=_ACCENT, hover_color=_ACCENT_SEL, font=ctk.CTkFont(size=11),
            corner_radius=4, command=lambda: self._bulk_recovery("retry", selected_only=False),
        )
        self.retry_failed_btn.pack(side="left", padx=(0, 4))
        self.alt_failed_btn = ctk.CTkButton(
            qa_bulk, text="Alternatives", width=110, height=24,
            fg_color="transparent", border_width=1, border_color=_BORDER,
            text_color=_ACCENT, hover_color=_ACCENT_SEL, font=ctk.CTkFont(size=11),
            corner_radius=4, command=lambda: self._bulk_recovery("alternative", selected_only=False),
        )
        self.alt_failed_btn.pack(side="left", padx=(0, 4))
        self.skip_failed_btn = ctk.CTkButton(
            qa_bulk, text="Skip failed", width=100, height=24,
            fg_color="transparent", border_width=1, border_color=_BORDER,
            text_color=_DANGER, hover_color=_DANGER_BG, font=ctk.CTkFont(size=11),
            corner_radius=4, command=lambda: self._bulk_recovery("skip", selected_only=False),
        )
        self.skip_failed_btn.pack(side="left", padx=(0, 4))
        self.retry_selected_btn = ctk.CTkButton(
            qa_bulk, text="Retry selected", width=110, height=24,
            fg_color="transparent", border_width=1, border_color=_BORDER,
            text_color=_ACCENT, font=ctk.CTkFont(size=11),
            corner_radius=4, command=lambda: self._bulk_recovery("retry", selected_only=True),
        )
        self.retry_selected_btn.pack(side="left", padx=(8, 4))
        self.alt_selected_btn = ctk.CTkButton(
            qa_bulk, text="Alt selected", width=100, height=24,
            fg_color="transparent", border_width=1, border_color=_BORDER,
            text_color=_ACCENT, font=ctk.CTkFont(size=11),
            corner_radius=4, command=lambda: self._bulk_recovery("alternative", selected_only=True),
        )
        self.alt_selected_btn.pack(side="left", padx=(0, 4))
        self.skip_selected_btn = ctk.CTkButton(
            qa_bulk, text="Skip selected", width=100, height=24,
            fg_color="transparent", border_width=1, border_color=_BORDER,
            text_color=_DANGER, font=ctk.CTkFont(size=11),
            corner_radius=4, command=lambda: self._bulk_recovery("skip", selected_only=True),
        )
        self.skip_selected_btn.pack(side="left")
        self.fix_all_vqa_btn = ctk.CTkButton(
            qa_bulk, text="Fix All Issues", width=110, height=24,
            fg_color=_ACCENT, hover_color=_ACCENT_HOV, text_color=_ACCENT_DARK,
            font=ctk.CTkFont(size=11, weight="bold"),
            corner_radius=4, command=self._on_fix_all_visual_issues,
        )
        self.fix_all_vqa_btn.pack(side="left", padx=(8, 4))
        ctk.CTkButton(
            qa_bulk, text="Select failed", width=100, height=24,
            fg_color="transparent", border_width=1, border_color=_BORDER,
            text_color=_ACCENT, font=ctk.CTkFont(size=11),
            command=self._select_all_failed,
        ).pack(side="left", padx=(8, 4))
        ctk.CTkButton(
            qa_bulk, text="Clear", width=60, height=24,
            fg_color="transparent", border_width=1, border_color=_BORDER,
            text_color=_MUTED, font=ctk.CTkFont(size=11),
            command=self._clear_failed_selection,
        ).pack(side="left")
        ctk.CTkLabel(
            self._issues_drawer, textvariable=self.issues_header_var,
            font=ctk.CTkFont(size=11), text_color=_DANGER, anchor="w",
        ).pack(fill="x", padx=12)
        self._issues_list = ctk.CTkScrollableFrame(
            self._issues_drawer, fg_color="transparent", height=120,
            scrollbar_button_color=_BORDER, scrollbar_button_hover_color=_ACCENT,
        )
        self._issues_list.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self._scene_row_widgets: dict[str, dict] = {}
        self._scene_rows: list[SceneRow] = []
        self._asset_results: dict[str, object] = {}
        self._busy_scenes: set[str] = set()
        self._pending_source_after_cancel: dict[str, str] = {}
        self._scene_started: dict[str, float] = {}
        self._retry_queue: list[SceneRow] = []
        self._retry_pumping = False
        self._flow_retry_batch_busy = False
        self._qa = SceneQAState()
        self._hydrated_skipped: set[str] = set()
        self._recovery_queue: list[tuple[str, SceneRow]] = []
        self._recovery_total = 0
        self._recovery_done = 0
        self.retry_all_btn = self.retry_failed_btn

        self.log_box = ctk.CTkTextbox(
            right,
            wrap="word",
            font=ctk.CTkFont(family="Menlo", size=12),
            fg_color=_CARD,
            text_color=_TEXT,
            border_width=1,
            border_color=_BORDER,
            corner_radius=6,
            scrollbar_button_color=_BORDER,
            scrollbar_button_hover_color=_ACCENT,
        )
        self.log_box.configure(state="disabled")

        self._preview_panel = ctk.CTkFrame(right, fg_color=_CARD, corner_radius=6)

        prev_header = ctk.CTkFrame(self._preview_panel, fg_color="transparent")
        prev_header.pack(fill="x", padx=12, pady=(10, 4))

        ctk.CTkLabel(
            prev_header,
            text="Preview",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=_TEXT,
        ).pack(side="left")

        self._open_btn = ctk.CTkButton(
            prev_header,
            text="▶  Open",
            width=80,
            height=26,
            fg_color="transparent",
            border_width=1,
            border_color=_BORDER,
            text_color=_ACCENT,
            hover_color=_BORDER,
            font=ctk.CTkFont(size=11),
            corner_radius=4,
            command=self._open_in_player,
        )
        self._open_btn.pack(side="right")

        self._open_folder_btn = ctk.CTkButton(
            prev_header,
            text="Open Folder",
            width=100,
            height=26,
            fg_color="transparent",
            border_width=1,
            border_color=_BORDER,
            text_color=_ACCENT,
            hover_color=_BORDER,
            font=ctk.CTkFont(size=11),
            corner_radius=4,
            command=self._open_output_folder,
        )
        self._open_folder_btn.pack(side="right", padx=(0, 6))

        self._thumb_label = ctk.CTkLabel(
            self._preview_panel,
            text="",
            fg_color="transparent",
        )
        self._thumb_label.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        self._last_output: str | None = None

    def _bind_responsive_wrap(self, widget, pad: int = 24) -> None:
        def _on_configure(event, w=widget, p=pad):
            if event.widget is not w:
                return
            wrap = max(80, int(event.width) - int(p))
            try:
                current = int(w.cget("wraplength") or 0)
            except Exception:
                current = 0
            if current != wrap:
                try:
                    w.configure(wraplength=wrap)
                except Exception:
                    pass

        widget.bind("<Configure>", _on_configure, add="+")

    def _set_stepper_compact(self, compact: bool) -> None:
        compact = bool(compact)
        if compact == self._stepper_compact:
            return
        self._stepper_compact = compact
        self._refresh_stepper()

    def _refresh_stepper(self) -> None:
        # Shell uses ScriptView workflow strip; keep stubs out of the layout.
        view = getattr(self, "_view_script", None)
        if view is not None and hasattr(view, "on_show"):
            try:
                view.on_show()
            except Exception:
                pass
        idx = max(0, min(len(_STEPPER_STEPS) - 1, int(self._stepper_index)))
        name = _STEPPER_STEPS[idx]
        compact_lbl = getattr(self, "_stepper_compact_label", None)
        full = getattr(self, "_stepper_full", None)
        labels = getattr(self, "_stepper_labels", None) or []
        if not labels:
            # Shell mode — stage label already shows phase; optional compact hint
            return
        if self._stepper_compact:
            if full is not None:
                full.grid_remove()
            if compact_lbl is not None:
                compact_lbl.configure(text=f"Step {idx + 1} of 5 · {name}")
                compact_lbl.grid()
            return
        if compact_lbl is not None:
            compact_lbl.grid_remove()
        if full is not None:
            full.grid()
        for i, lbl in enumerate(labels):
            if i < idx:
                color = _STEPPER_DONE
                weight = "normal"
            elif i == idx:
                color = _ACCENT
                weight = "bold"
            else:
                color = _MUTED
                weight = "normal"
            lbl.configure(text_color=color, font=ctk.CTkFont(size=12, weight=weight))

    def _on_topbar_configure(self, event) -> None:
        if event.widget is not getattr(self, "_topbar", None):
            return
        width = int(event.width)
        self._set_stepper_compact(width < 1080)
        ellipsis = width < 900
        if ellipsis != self._chip_ellipsis:
            self._chip_ellipsis = ellipsis
            self._apply_chip_text()

    def _apply_chip_text(self) -> None:
        text = self._project_chip_full or "No project"
        if self._chip_ellipsis and len(text) > 22:
            text = text[:20].rstrip() + "…"
        self._project_chip_var.set(text)

    def _sync_script_watermark(self) -> None:
        mark = getattr(self, "_script_watermark", None)
        box = getattr(self, "script_box", None)
        if mark is None or box is None:
            return
        text = box.get("1.0", "end").strip()
        if text:
            mark.place_forget()
        else:
            mark.place(in_=box, x=10, y=8)
        if not self._running:
            self._sync_primary_cta()

    def _sync_export_csv_link(self) -> None:
        btn = getattr(self, "_export_csv_btn", None)
        if btn is None:
            return
        if self._visual_plan is not None:
            btn.grid()
        else:
            btn.grid_remove()

    def _toggle_optional_section(self) -> None:
        self._optional_open = not self._optional_open
        if self._optional_open:
            self._optional_block.grid()
            self._optional_toggle.configure(text="Optional −")
        else:
            self._optional_block.grid_remove()
            self._optional_toggle.configure(text="Optional +")

    def _open_workspace_overflow(self) -> None:
        import tkinter as tk

        menu = tk.Menu(
            self, tearoff=0, bg=_CARD, fg=_TEXT, activebackground=_CARD_HOVER,
            activeforeground=_TEXT, bd=0,
        )
        cleanup = getattr(self, "cleanup_assets_btn", None)
        cleanup_label = "Cleanup"
        cleanup_state = "disabled"
        if cleanup is not None:
            try:
                cleanup_label = str(cleanup.cget("text") or "Cleanup")
                cleanup_state = str(cleanup.cget("state") or "disabled")
            except Exception:
                pass
        has_plan = bool(self._scene_rows) or bool(self.csv_var.get().strip())
        menu.add_command(
            label="Clear plan…",
            command=self._clear_visual_plan,
            state=tk.NORMAL if has_plan and not self._running else tk.DISABLED,
        )
        menu.add_separator()
        menu.add_command(
            label=cleanup_label,
            command=self._on_cleanup_downloaded_assets,
            state=tk.NORMAL if cleanup_state == "normal" else tk.DISABLED,
        )
        activity = "Hide activity" if self._log_visible else "Activity"
        menu.add_command(label=activity, command=self._toggle_activity_log)
        try:
            menu.tk_popup(self._overflow_btn.winfo_rootx(), self._overflow_btn.winfo_rooty() + 28)
        finally:
            menu.grab_release()

    def _on_inspector_configure(self, event) -> None:
        if event.widget is not getattr(self, "_details_actions", None):
            return
        self._layout_inspector_actions(int(event.width))

    def _layout_inspector_actions(self, width: int | None = None) -> None:
        frame = getattr(self, "_details_actions", None)
        if frame is None:
            return
        buttons = [
            self.details_source_btn,
            self.details_local_btn,
            self.details_open_btn,
            self.details_retry_btn,
            self.details_alt_btn,
            self.details_skip_btn,
            self.details_stop_btn,
        ]
        use = [b for b in buttons if getattr(b, "_inspector_show", True)]
        if not use:
            use = buttons[:2]
        if width is None:
            try:
                width = int(frame.winfo_width())
            except Exception:
                width = 240
        # Narrow inspector (~260px): always 2 columns so labels stay readable.
        cols = 2 if width < 420 else 3
        for b in buttons:
            b.grid_forget()
        for i in range(cols):
            frame.grid_columnconfigure(i, weight=1, uniform="insp")
        col = 0
        row = 0
        for b in use:
            b.grid(row=row, column=col, sticky="ew", padx=(0, 4), pady=3)
            col += 1
            if col >= cols:
                col = 0
                row += 1

    def _set_inspector_button(self, btn, *, show: bool, state: str = "normal") -> None:
        btn._inspector_show = show
        if show:
            btn.configure(state=state)
        else:
            btn.configure(state="disabled")
        self._layout_inspector_actions()

    def _script_has_text(self) -> bool:
        box = getattr(self, "script_box", None)
        if box is None:
            return False
        return bool(box.get("1.0", "end").strip())

    def _on_primary_cta(self) -> None:
        action = getattr(self, "_cta_action", "generate")
        if action == "picker":
            self._open_project_picker()
        elif action == "analyze":
            self._on_analyze_script()
        elif action == "import_csv":
            self._browse_csv()
        elif action == "import_audio":
            self._browse_audio()
        elif action == "cancel":
            self._on_cancel()
        else:
            self._on_generate()

    # ---------- friend login gate ----------

    def _auth_required(self) -> bool:
        """Enforce login when Supabase is configured, or always in packaged builds."""
        from licensing.config import is_configured

        if is_configured():
            return True
        # Packaged builds without embedded secrets still show a login wall
        # (misconfigured) rather than silently opening the app.
        return _is_frozen()

    def _ensure_licensed_then_picker(self) -> None:
        if not self._auth_required():
            self._open_project_picker()
            return

        def open_picker():
            self._open_project_picker()

        def show_login(message: str = ""):
            self._show_login_dialog(message=message, then=open_picker)

        # Try restore session off the UI thread (network).
        def work():
            from licensing.auth_client import AuthError, get_auth_client
            from licensing.config import is_configured

            if not is_configured():
                self.after(0, lambda: show_login("App is not configured for login."))
                return
            try:
                session = get_auth_client().verify_stored_session()
                self.after(0, lambda: self._on_auth_ok(session, then=open_picker))
            except AuthError as exc:
                if exc.code == "unsigned":
                    self.after(0, lambda: show_login(""))
                elif exc.code in ("revoked", "disabled"):
                    # Definitive server-side deny — always show the login wall.
                    msg = exc.message
                    self.after(0, lambda m=msg: show_login(m))
                else:
                    # "network" (timeout/offline/etc.) is not a deny — we simply
                    # couldn't confirm anything against the server. Trust the
                    # last stored session rather than forcing offline
                    # Stock/Manual use behind a login wall.
                    self._continue_offline_or_login(open_picker, show_login, exc.message)
            except Exception as exc:
                self._continue_offline_or_login(open_picker, show_login, str(exc) or "Sign in required")

        threading.Thread(target=work, daemon=True).start()

    def _continue_offline_or_login(self, open_picker, show_login, message: str) -> None:
        """Called when session verification couldn't be confirmed against the
        server (network failure, timeout, or another non-deny error) — NOT a
        definitive revoke/disable. A transient network failure must not
        destroy a valid local session or force offline Stock/Manual use
        behind a login wall, so fall back to the last stored session when one
        exists; only show the login dialog when there is truly nothing to
        trust."""
        from licensing import session_store
        from licensing.auth_client import AuthSession

        stored = session_store.load_session()
        if stored:
            session = AuthSession.from_store(stored)
            self.after(0, lambda: self._on_auth_ok(session, then=open_picker))
        else:
            self.after(0, lambda m=message: show_login(m))

    def _on_auth_ok(self, session, *, then=None) -> None:
        self._auth_session = session
        self._require_terms_ack(session, then=then)

    def _require_terms_ack(self, session, *, then=None) -> None:
        """Onboarding gate layered ON TOP of licensing — never a replacement.

        Every successful auth path (fresh login, restored session, offline
        fallback) converges on _on_auth_ok, so this is the single enforcement
        point. A lookup that cannot be completed is NOT treated as
        acknowledged: the screen is shown, and the Supabase write must succeed
        before the workflow opens.
        """
        def proceed():
            if then:
                then()

        if not getattr(session, "user_id", ""):
            proceed()
            return

        def work():
            from licensing import terms as _terms

            try:
                done = bool(_terms.has_acknowledged(session))
            except Exception:
                done = False  # could not confirm -> ask, never assume yes
            self.after(
                0,
                lambda d=done: proceed() if d else self._show_terms_dialog(session, then=proceed),
            )

        threading.Thread(target=work, daemon=True).start()

    def _show_terms_dialog(self, session, *, then=None) -> None:
        from licensing.terms_dialog import TermsDialog

        existing = self.__dict__.get("_terms_dialog")
        if existing is not None and existing.winfo_exists():
            return

        def accepted():
            self._terms_dialog = None
            if then:
                then()

        def cancelled():
            # Declining is not acceptance — close instead of opening the app.
            self._terms_dialog = None
            self.destroy()

        self._terms_dialog = TermsDialog(
            self, session=session, on_accept=accepted, on_cancel=cancelled,
        )

    def _show_login_dialog(self, *, message: str = "", then=None) -> None:
        from licensing.login_dialog import LoginDialog
        from licensing.auth_client import get_auth_client

        existing = getattr(self, "_login_dialog", None)
        if existing is not None:
            try:
                if existing.winfo_exists():
                    existing.lift()
                    existing.focus_force()
                    return
            except Exception:
                pass

        def on_success(session):
            self._login_dialog = None
            self._on_auth_ok(session, then=then)

        def on_cancel():
            self._login_dialog = None
            self.destroy()

        self._login_dialog = LoginDialog(
            self,
            auth_client=get_auth_client(),
            on_success=on_success,
            on_cancel=on_cancel,
            message=message,
        )

    def _revalidate_license(self) -> tuple[bool, str]:
        """Refresh + active check. Returns (ok, error_message).

        Only a definitive server-side deny (revoked refresh token, disabled
        account) counts as "not ok" here. A network failure or any other
        error that isn't a positive deny means the server couldn't be
        reached to confirm anything either way — it must not be treated as a
        revoke, or a transient wifi blip while clicking Generate would
        force-logout an already-signed-in user and cancel in-flight work for
        no real security reason.
        """
        if not self._auth_required():
            return True, ""
        from licensing.auth_client import AuthError, get_auth_client
        from licensing.config import is_configured

        if not is_configured():
            return False, "App is not configured for login."
        try:
            session = get_auth_client().verify_stored_session()
            self._auth_session = session
            return True, ""
        except AuthError as exc:
            if exc.code in ("revoked", "disabled"):
                return False, exc.message
            # Not a deny (network/unsigned/misconfigured/etc.) — keep trusting
            # the session already held this run, if any.
            return (True, "") if self._auth_session is not None else (False, exc.message)
        except Exception:
            return (True, "") if self._auth_session is not None else (False, "Access check failed")

    def _force_logout(self, reason: str = "") -> None:
        from licensing import session_store

        session_store.clear_session()
        self._auth_session = None
        if self._running and self._asset_manager is not None:
            try:
                self._asset_manager.request_cancel()
            except Exception:
                pass
        self._running = False
        try:
            self._set_generate_btn(state="disabled", text="Generate Assets")
        except Exception:
            pass
        msg = (
            reason
            if reason in (
                "Account disabled",
                "Access revoked — contact the owner.",
                "Access revoked or password changed",
            )
            else "Your access was removed or your password changed. Sign in again."
        )
        messagebox.showwarning("Access revoked", msg)

        def after_login():
            if self._workspace is None:
                self._open_project_picker()

        self._show_login_dialog(message="", then=after_login)

    def _sign_out(self) -> None:
        from licensing import session_store

        session_store.clear_session()
        self._auth_session = None
        messagebox.showinfo("Signed out", "You have been signed out.")
        self._show_login_dialog(message="", then=lambda: self._open_project_picker())

    def _auth_identity_label(self) -> str:
        session = self._auth_session
        if session is None:
            from licensing import session_store

            stored = session_store.load_session()
            if not stored:
                return "Not signed in"
            name = (stored.get("display_name") or "").strip()
            email = (stored.get("email") or "").strip()
            return name or email or "Signed in"
        name = (session.display_name or "").strip()
        email = (session.email or "").strip()
        return name or email or "Signed in"

    def _open_project_picker(self) -> None:
        existing = getattr(self, "_project_picker", None)
        if existing is not None:
            try:
                if existing.winfo_exists():
                    existing.lift()
                    existing.focus_force()
                    return
            except Exception:
                pass

        last_id = (self._settings.get("active_project_id") or "").strip()
        workspaces = list_projects(self._projects_root_path())
        projects = project_dicts_from_workspaces(workspaces, last_id=last_id)
        self._project_picker = ProjectPickerDialog(
            self,
            projects=projects,
            on_create=self._picker_on_create,
            on_select=self._picker_on_select,
            on_open_folder=self._picker_on_open_folder,
            on_settings=self._open_settings,
            on_dismiss=self._picker_on_dismiss,
        )

    def _picker_on_create(
        self,
        title: str,
        *,
        brand_kit_id: str | None = None,
        style_mode: str = "",
        style_id: str | None = None,
    ) -> None:
        ws = create_project(title or "", projects_root=self._projects_root_path())
        # Optional brand/style — empty mode keeps legacy behavior.
        try:
            ws.set_video_style_settings(
                mode=str(style_mode or "").strip().lower(),
                style_id=style_id,
                brand_kit_id=brand_kit_id if brand_kit_id and brand_kit_id != "none" else None,
            )
        except Exception:
            pass
        self._activate_workspace(ws, persist=True, clear_session=True)

    def _resolve_project_style(
        self,
        *,
        script: str = "",
        visual_plan=None,
        rows=None,
        persist: bool = False,
    ):
        """Resolve Brand/Style for this project. None = legacy (unchanged heuristics)."""
        ws = self._workspace
        if ws is None:
            return None
        try:
            from style_engine import resolve_style, style_prompt_adornment

            resolved = resolve_style(
                script=script or (
                    self.script_box.get("1.0", "end").strip() if hasattr(self, "script_box") else ""
                ),
                visual_plan=visual_plan if visual_plan is not None else self._visual_plan,
                rows=rows if rows is not None else [
                    {
                        "scene_number": s.scene_number,
                        "script_segment": s.script_segment,
                        "asset_type": s.asset_type,
                        "prompt": s.prompt or s.stock,
                    }
                    for s in (getattr(self, "_scene_rows", None) or [])
                ],
                project_meta=ws.read_meta(),
                title=str((ws.read_meta() or {}).get("name") or ""),
                state_dir=getattr(ws, "state_dir", None) or (ws.path / "state" if hasattr(ws, "path") else None),
                gemini_settings=dict(getattr(self, "settings", None) or {}),
            )
            if persist and resolved is not None:
                ws.set_style_resolution(resolved.to_resolution_meta())
                # Keep AUTO detected id visible without forcing mode change
                vs = ws.video_style_settings()
                if vs.get("mode") == "auto" and not vs.get("style_id"):
                    ws.set_video_style_settings(
                        mode="auto",
                        style_id=resolved.detected_style_id or resolved.style_id,
                        brand_kit_id=vs.get("brand_kit_id"),
                    )
            # Stash for typography / prompt adornment in this session
            self._resolved_style = resolved
            self._style_prompt_adornment = style_prompt_adornment(resolved) if resolved else ""
            return resolved
        except Exception as exc:
            self._append_log(f"[STYLE] Resolve skipped ({exc})\n")
            return None

    def _picker_on_select(self, project_id: str) -> None:
        ws = find_project(self._projects_root_path(), project_id)
        if ws is None:
            messagebox.showerror("Open Project", "That project could not be found.")
            self.after_idle(self._open_project_picker)
            return
        self._activate_workspace(ws, persist=True, clear_session=True)

    def _picker_on_open_folder(self) -> None:
        self._on_open_project()
        if self._workspace is None:
            return
        win = getattr(self, "_project_picker", None)
        if win is not None:
            try:
                if win.winfo_exists():
                    win.destroy()
            except Exception:
                pass
            self._project_picker = None

    def _picker_on_dismiss(self) -> None:
        self._project_picker = None
        if self._workspace is None:
            self._sync_primary_cta()

    def _set_window_icon(self) -> None:
        """Taskbar / dock / window icon from assets (best-effort)."""
        try:
            self._icon_photo = _logo_icon_photo(64)
            if self._icon_photo is not None:
                self.iconphoto(True, self._icon_photo)
        except Exception:
            pass
        if sys.platform == "win32":
            ico = SOURCE_DIR / "assets" / "AppIcon.ico"
            if ico.is_file():
                try:
                    self.iconbitmap(str(ico))
                except Exception:
                    pass

    def _path_row(
        self,
        row: int,
        label: str,
        var: ctk.StringVar,
        browse_cmd,
        clearable: bool = False,
        parent=None,
        placeholder_text: str = "",
    ) -> None:
        """Styled input card inside the scrollable left panel."""
        host = parent if parent is not None else self._scroll
        pad_x = 0 if parent is not None else 16
        card = ctk.CTkFrame(host, fg_color=_CARD if parent is None or label else "transparent", corner_radius=6)
        card.grid(row=row, column=0, sticky="ew", padx=pad_x, pady=(8 if label else 4, 0))
        card.grid_columnconfigure(0, weight=1)

        if label:
            ctk.CTkLabel(
                card,
                text=label,
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=_MUTED,
                anchor="w",
            ).grid(row=0, column=0, sticky="w", padx=12, pady=(8, 2), columnspan=3)

        display = ctk.StringVar()

        def _sync_display(*_):
            raw = var.get().strip()
            name = Path(raw).name if raw else ""
            if display.get() != name:
                display.set(name)

        var.trace_add("write", lambda *_: _sync_display())
        _sync_display()

        entry = ctk.CTkEntry(
            card,
            textvariable=display,
            height=34,
            fg_color=_BG,
            border_color=_BORDER,
            border_width=1,
            text_color=_TEXT,
            placeholder_text=placeholder_text,
            placeholder_text_color=_MUTED,
            corner_radius=4,
        )
        entry_row = 1 if label else 0
        entry.grid(row=entry_row, column=0, sticky="ew", padx=(10, 6), pady=(0, 10))

        ctk.CTkButton(
            card,
            text="Browse",
            width=74,
            height=34,
            fg_color="transparent",
            border_width=1,
            border_color=_BORDER,
            text_color=_TEXT,
            hover_color=_ACCENT,
            corner_radius=4,
            font=ctk.CTkFont(size=12),
            command=browse_cmd,
        ).grid(row=entry_row, column=1, sticky="e", padx=(0, 4 if clearable else 10), pady=(0, 10))

        if clearable:
            ctk.CTkButton(
                card,
                text="✕",
                width=34,
                height=34,
                fg_color="transparent",
                border_width=1,
                border_color=_BORDER,
                text_color=_MUTED,
                hover_color=_DANGER_BG,
                corner_radius=4,
                font=ctk.CTkFont(size=13),
                command=lambda: var.set(""),
            ).grid(row=entry_row, column=2, sticky="e", padx=(0, 10), pady=(0, 10))

    def _open_folder_path(self, folder: Path) -> None:
        folder = Path(folder)
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        if not folder.is_dir():
            messagebox.showwarning("Not found", f"Folder not found:\n{folder}")
            return
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", str(folder)])
            elif sys.platform == "win32":
                os.startfile(str(folder))  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", str(folder)])
        except Exception as exc:
            messagebox.showerror("Cannot open folder", str(exc))

    def _toggle_issues(self) -> None:
        snap = self._qa_snapshot() if self._scene_rows else None
        if snap is None or not snap.needs_action:
            self._issues_visible = False
            self._issues_drawer.grid_remove()
            return
        self._issues_visible = not self._issues_visible
        if self._issues_visible:
            self._issues_drawer.grid(row=2, column=0, sticky="ew", padx=16, pady=(8, 0))
            self._rebuild_issues()
        else:
            self._issues_drawer.grid_remove()

    def _toggle_activity_log(self) -> None:
        self._log_visible = not self._log_visible
        if self._log_visible:
            self.log_box.grid(row=3, column=0, sticky="nsew", padx=16, pady=(8, 0))
            self.log_toggle_btn.configure(text="Activity ▾")
            if self._log_backlog:
                chunk = "".join(self._log_backlog)
                self._log_backlog.clear()
                self.log_box.configure(state="normal")
                self.log_box.insert("end", chunk)
                self.log_box.see("end")
                self.log_box.configure(state="disabled")
        else:
            self.log_box.grid_remove()
            self.log_toggle_btn.configure(text="Activity ▸")

    def _selected_scenes(self) -> list:
        """Scenes checked in the list; falls back to the focused scene."""
        keys = list(self._qa.selected_failed)
        by_key = {_scene_key(s.scene_number): s for s in self._scene_rows}
        scenes = [by_key[k] for k in keys if k in by_key]
        if scenes:
            return scenes
        key = self._qa.focused_key
        if key and key in by_key:
            return [by_key[key]]
        return []

    def _change_source_for_focused(self) -> None:
        scenes = self._selected_scenes()
        if not scenes:
            return
        if len(scenes) == 1:
            self._change_source_dialog(scenes[0])
            return
        self._change_source_dialog_bulk(scenes)

    def _close_flow_instances(self) -> None:
        """Close all Flow Chrome windows (leftover from generate / sign-in)."""
        self.status_var.set("Closing Flow browsers…")
        self._append_log("[FLOW] Close instances requested…\n")

        def worker():
            parts: list[str] = []
            try:
                mgr = self._get_flow_engine_manager()
                closed_via_engine = False
                has_client = getattr(mgr, "_client", None) is not None
                proc_alive = (
                    getattr(mgr, "_proc", None) is not None
                    and mgr._proc.poll() is None  # type: ignore[union-attr]
                )
                if has_client or proc_alive:
                    client = mgr.ensure_running()
                    client.close_browsers()
                    time.sleep(0.35)
                    closed_n = None
                    try:
                        st = client.get_state() or {}
                        if "browsersClosed" in st:
                            closed_n = int(st.get("browsersClosed") or 0)
                    except Exception:
                        closed_n = None
                    if closed_n is not None:
                        parts.append(f"engine closed {closed_n} browser(s)")
                    else:
                        parts.append("engine browsers closed")
                    closed_via_engine = True
                else:
                    # Engine may still be running from a prior session — probe briefly.
                    try:
                        from providers.flow.client import FlowClient, FlowClientError

                        probe = FlowClient(mgr.url, log=lambda *_: None)
                        probe.connect(timeout=1.2)
                        probe.close_browsers()
                        time.sleep(0.3)
                        probe.close()
                        parts.append("engine browsers closed")
                        closed_via_engine = True
                    except Exception:
                        parts.append("Flow engine was not running")
                killed = self._kill_orphan_flow_browsers()
                if killed:
                    parts.append(f"stopped {killed} leftover Chrome/Chromium process(es)")
                elif closed_via_engine:
                    parts.append("no leftover profile processes")
                summary = "; ".join(parts) if parts else "done"
                self.after(
                    0,
                    lambda s=summary: (
                        self.status_var.set("Flow browsers closed"),
                        self._append_log(f"[FLOW] Close instances: {s}\n"),
                    ),
                )
            except Exception as exc:
                msg = str(exc)
                # Still try orphans if engine path failed.
                try:
                    killed = self._kill_orphan_flow_browsers()
                    if killed:
                        msg = f"{msg} (also stopped {killed} leftover process(es))"
                except Exception:
                    pass
                self.after(
                    0,
                    lambda m=msg: (
                        self.status_var.set("Close instances failed"),
                        messagebox.showerror("Close instances", m),
                    ),
                )

        threading.Thread(target=worker, daemon=True).start()

    @staticmethod
    def _kill_orphan_flow_browsers() -> int:
        """SIGTERM Chrome/Chromium processes using Flow profile user-data-dirs.

        Only targets processes whose command line references
        ~/.semantic-automator-desktop/profiles — never the user's normal Chrome.
        """
        marker = "semantic-automator-desktop"
        killed = 0
        try:
            if sys.platform == "win32":
                ps = (
                    "Get-CimInstance Win32_Process -Filter \"name='chrome.exe' OR name='chromium.exe'\" "
                    f"| Where-Object {{ $_.CommandLine -and ($_.CommandLine -like '*{marker}*profiles*') }} "
                    "| ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; 1 }"
                )
                out = subprocess.run(
                    ["powershell", "-NoProfile", "-Command", ps],
                    capture_output=True, text=True, timeout=15,
                )
                return sum(1 for line in (out.stdout or "").splitlines() if line.strip() == "1")
            out = subprocess.check_output(["ps", "-ax", "-o", "pid=,command="], text=True, timeout=10)
        except Exception:
            return 0
        for line in out.splitlines():
            low = line.lower()
            if marker not in low or "profiles" not in low:
                continue
            if not any(x in low for x in ("chrome", "chromium", "google chrome")):
                continue
            try:
                pid = int(line.strip().split(None, 1)[0])
            except (ValueError, IndexError):
                continue
            try:
                os.kill(pid, 15)  # SIGTERM
                killed += 1
            except OSError:
                continue
        return killed

    def _sync_primary_cta(self, snap=None) -> None:
        snap = snap or (self._qa_snapshot() if self._scene_rows else None)
        audio_ok = bool(self.audio_var.get().strip()) and Path(self.audio_var.get().strip()).is_file()
        has_plan = bool(self.csv_var.get().strip()) and Path(self.csv_var.get().strip()).is_file()
        paste_mode = self._script_mode_is_ai()
        if self._running:
            self._cta_action = "cancel"
            self.stage_var.set("GENERATING")
            self.hint_var.set("Work is in progress. You can stop asset generation.")
            self._stepper_index = 4 if (snap is not None and snap.allow_render and audio_ok) else 2
            self._refresh_stepper()
            self.generate_btn.configure(
                state="normal",
                text="Stop",
                fg_color="transparent",
                hover_color=_DANGER_BG,
                text_color=_DANGER,
                border_width=1,
                border_color=_DANGER,
            )
            return
        if self._workspace is None:
            self._cta_action = "picker"
            self.stage_var.set("SCRIPT")
            self.hint_var.set("Choose a project to get started.")
            self._stepper_index = 0
            self._refresh_stepper()
            self._set_generate_btn(state="normal", text="Choose project")
            return
        if not has_plan or snap is None or snap.total == 0:
            self.stage_var.set("PLAN")
            self._stepper_index = 0
            if paste_mode:
                self._cta_action = "analyze"
                self.hint_var.set("Paste your script, then analyze it into scenes.")
                self._set_generate_btn(state="normal", text="Analyze Script")
            else:
                self._cta_action = "import_csv"
                self.hint_var.set("Import a visual-plan CSV to load scenes.")
                self._set_generate_btn(state="normal", text="Import CSV")
            self._refresh_stepper()
            return
        if snap.needs_action or not snap.allow_render:
            self._cta_action = "generate"
            self.stage_var.set("REVIEW" if snap.needs_action else "GENERATE")
            self.hint_var.set(
                "Fix scenes that need attention, then generate remaining assets."
                if snap.needs_action
                else "Generate visuals for every scene."
            )
            untouched = snap.ready == 0 and not snap.processing and not snap.needs_action
            self._stepper_index = 1 if untouched else 2
            self._refresh_stepper()
            self._set_generate_btn(state="normal", text="Generate Assets")
            return
        if not audio_ok:
            self._cta_action = "import_audio"
            self.stage_var.set("VOICE")
            self.hint_var.set("Scenes are ready. Import a voiceover audio file next.")
            self._stepper_index = 3
            self._refresh_stepper()
            self._set_generate_btn(state="normal", text="Import Voiceover")
            return
        self._cta_action = "generate"
        self.stage_var.set("EXPORT")
        self.hint_var.set("Everything is ready. Render the final video.")
        self._stepper_index = 4
        self._refresh_stepper()
        self._set_generate_btn(state="normal", text="Render Video")

    def _set_generate_btn(self, *, state: str, text: str) -> None:
        """Restore accent styling whenever the primary CTA leaves Stop / busy."""
        self.generate_btn.configure(
            state=state,
            text=text,
            fg_color=_ACCENT,
            hover_color=_ACCENT_HOV,
            text_color=_ACCENT_DARK,
            border_width=0,
        )

    def _apply_defaults(self) -> None:
        # Fresh session: never auto-activate the last project or prefill bg music.
        self._refresh_project_menu()
        self._update_project_indicator()
        self._sync_images_dir()
        self._refresh_scene_preview()
        self._sync_primary_cta()

    def _sync_images_dir(self) -> None:
        """Assets live in the active project workspace. Legacy CSVs (no project)
        still use Images/ next to the CSV — existing files are never moved."""
        if self._workspace is not None:
            self._workspace.ensure_dirs()
            self.images_var.set(str(self._workspace.assets_dir))
            return
        csv_path = self.csv_var.get().strip()
        if csv_path:
            base = Path(csv_path).resolve().parent
            if base.name == "csv":
                base = base.parent
        else:
            out = self.output_var.get().strip()
            base = Path(out).resolve().parent if out else (Path.home() / ".videogen")
        images_dir = base / "Images"
        images_dir.mkdir(parents=True, exist_ok=True)
        self.images_var.set(str(images_dir))

    def _projects_root_path(self) -> Path:
        return Path(self._projects_root)

    def _require_workspace(self, action: str = "continue") -> bool:
        if self._workspace is not None:
            self._workspace.ensure_dirs()
            return True
        self._open_project_picker()
        return False

    def _on_new_project(self) -> None:
        dialog = ctk.CTkInputDialog(
            text="Video title (optional — used in the folder name):",
            title="New Project",
        )
        title = dialog.get_input()
        if title is None:
            return
        ws = create_project(title or "", projects_root=self._projects_root_path())
        self._activate_workspace(ws, persist=True, clear_session=True)

    def _on_project_menu(self, label: str) -> None:
        if self._project_menu_lock:
            return
        if label in ("＋ New Project", "+ New Project"):
            self._on_new_project()
            self._refresh_project_menu()
            return
        if label.startswith("Open Project"):
            self._on_open_project()
            self._refresh_project_menu()
            return
        pid = self._project_labels.get(label)
        if not pid:
            return
        if self._workspace is not None and self._workspace.project_id == pid:
            return
        ws = find_project(self._projects_root_path(), pid)
        if ws is None:
            return
        self._activate_workspace(ws, persist=True, clear_session=True)

    def _on_open_project(self) -> None:
        path = filedialog.askdirectory(title="Open project folder")
        if not path:
            return
        ws = load_project(Path(path))
        if ws is None:
            messagebox.showerror("Open Project", "That folder is not a video project (missing project.json).")
            return
        self._activate_workspace(ws, persist=True, clear_session=True)

    def _activate_workspace(self, ws, persist: bool = True, clear_session: bool = False, refresh_menu: bool = True) -> None:
        self._workspace = ws
        self._editorial_plan_cache = None
        self._editorial_plan_mtime = 0.0
        ws.ensure_dirs()
        if clear_session:
            self._asset_manager = None
            self._asset_results.clear()
            self._busy_scenes.clear()
            self._pending_source_after_cancel.clear()
            self._hydrated_skipped.clear()
            self._qa = SceneQAState()
            self._visual_plan = None
            self._manual_csv_backup = ""
            self._reset_project_session_ui()
            self.csv_var.set("")
            self.audio_var.set("")
            self.bg_var.set("")
            try:
                self.script_box.delete("1.0", "end")
                self._sync_script_watermark()
            except Exception:
                pass
            self._sync_export_csv_link()
        if persist:
            self._settings["active_project_id"] = ws.project_id
            self._settings["projects_root"] = str(self._projects_root_path())
            save_settings(self._settings)
        self._bind_workspace_paths()
        self._resolve_project_style(persist=False)
        if refresh_menu:
            self._refresh_project_menu()
        self._update_project_indicator()
        self._refresh_scene_preview()
        # Non-critical FS scan — don't block project switch / first paint.
        self._refresh_cleanup_button(defer=True)
        self._load_smart_editing_settings_from_project(ws)
        try:
            self._refresh_cache_status()
        except Exception:
            pass

    def _refresh_cleanup_button(self, *, defer: bool = False) -> None:
        """Update Cleanup button label from a downloaded-assets scan.

        ``defer=True`` schedules the scan after idle (safe for project switch /
        post-run housekeeping). Explicit user actions keep the default sync path.
        """
        btn = getattr(self, "cleanup_assets_btn", None)
        if btn is None:
            return
        if defer:
            self.after_idle(lambda: self._refresh_cleanup_button(defer=False))
            return
        if self._workspace is None:
            btn.configure(text="Cleanup", state="disabled")
            return
        try:
            from downloaded_assets import scan_downloaded_assets

            report = scan_downloaded_assets(self._workspace)
        except Exception:
            btn.configure(text="Cleanup", state="disabled")
            return
        if report.is_empty:
            btn.configure(text="Cleanup", state="disabled", text_color=_MUTED)
        else:
            btn.configure(
                text=report.button_label(),
                state="normal",
                text_color=_ACCENT,
            )

    def _on_cleanup_downloaded_assets(self) -> None:
        if not self._require_workspace("delete downloaded assets"):
            return
        if self._running:
            messagebox.showinfo(
                "Cleanup",
                "Wait for generation to finish before deleting downloaded assets.",
            )
            return
        from downloaded_assets import delete_downloaded_assets, scan_downloaded_assets

        report = scan_downloaded_assets(self._workspace)
        if report.is_empty:
            messagebox.showinfo("Cleanup", "No downloaded pipeline assets to delete.")
            self._refresh_cleanup_button()
            return
        if not messagebox.askyesno("Delete downloaded assets", report.confirmation_message()):
            return
        self._apply_downloaded_assets_cleanup(report)

    def _offer_cleanup_after_render(self) -> None:
        """Optional post-render cleanup — never auto-deletes."""
        if self._workspace is None:
            return
        try:
            from downloaded_assets import scan_downloaded_assets

            report = scan_downloaded_assets(self._workspace)
        except Exception:
            return
        if report.is_empty:
            self._refresh_cleanup_button()
            return
        if not messagebox.askyesno(
            "Delete downloaded assets?",
            "Video is ready.\n\n" + report.confirmation_message(),
        ):
            self._refresh_cleanup_button()
            return
        self._apply_downloaded_assets_cleanup(report)

    def _apply_downloaded_assets_cleanup(self, report) -> None:
        from downloaded_assets import delete_downloaded_assets

        result = delete_downloaded_assets(
            self._workspace, confirm=True, report=report,
        )
        # Drop in-memory results for files that no longer exist.
        for key, res in list(self._asset_results.items()):
            path = getattr(res, "path", None)
            if path is None:
                continue
            try:
                if not Path(path).is_file():
                    self._asset_results.pop(key, None)
            except OSError:
                self._asset_results.pop(key, None)
        if self._asset_manager is not None:
            try:
                self._asset_manager.manifest.load()
            except Exception:
                pass
        self._refresh_qa_ui(immediate=True)
        self._refresh_cleanup_button()
        self._sync_primary_cta()
        freed = ""
        try:
            from downloaded_assets import format_bytes

            freed = format_bytes(result.bytes_freed)
        except Exception:
            freed = f"{result.bytes_freed} B"
        if result.failed:
            lines = "\n".join(f"  • {p.name}: {err}" for p, err in result.failed[:12])
            more = "" if len(result.failed) <= 12 else f"\n  …and {len(result.failed) - 12} more"
            self._append_log(
                f"[CLEANUP] Deleted {len(result.deleted)} file(s) ({freed}); "
                f"{len(result.failed)} could not be removed.\n"
            )
            messagebox.showwarning(
                "Cleanup partially finished",
                f"Removed {len(result.deleted)} file(s) ({freed}).\n\n"
                f"Could not remove {len(result.failed)} file(s):\n{lines}{more}",
            )
        else:
            self._append_log(f"[CLEANUP] Deleted {len(result.deleted)} file(s) ({freed}).\n")
            messagebox.showinfo(
                "Cleanup complete",
                f"Removed {len(result.deleted)} downloaded asset file(s) ({freed}).",
            )

    def ambience_volume_override(self) -> Optional[float]:
        """Explicit ambience level, or None when the control is on Auto."""
        try:
            raw = float(self.smart_ambience_volume_var.get())
        except Exception:
            return None
        if raw < 0:
            return None
        return normalize_ambience_volume(raw)

    def effective_ambience_volume(self) -> float:
        """The level ambience beds will actually be planned at."""
        return self._smart_editing_settings().ambience_volume()

    def reset_ambience_volume_to_auto(self) -> None:
        self.smart_ambience_volume_var.set(-1.0)
        self._persist_smart_editing_settings()

    def _smart_editing_settings(self) -> SmartEditingSettings:
        def _lvl(var) -> str:
            return (var.get() or "Medium").strip().lower()

        mode_raw = (self.smart_mode_var.get() or "Smart").strip().lower()
        return SmartEditingSettings(
            text_effects=bool(self.smart_text_effects_var.get()),
            sound_effects=bool(self.smart_sfx_var.get()),
            visual_transitions=bool(self.smart_visual_transitions_var.get()),
            scene_ambience=bool(self.smart_scene_ambience_var.get()),
            intensity=_lvl(self.smart_sfx_intensity_var),
            text_effects_intensity=_lvl(self.smart_text_intensity_var),
            sound_effects_intensity=_lvl(self.smart_sfx_intensity_var),
            visual_transitions_intensity=_lvl(self.smart_transitions_intensity_var),
            scene_ambience_intensity=_lvl(self.smart_ambience_intensity_var),
            scene_ambience_volume=self.ambience_volume_override(),
            mode="automatic" if mode_raw.startswith("auto") else "smart",
        )

    def _smart_editing_settings_dict(self) -> dict:
        return self._smart_editing_settings().to_settings_dict()

    def _persist_smart_editing_settings(self) -> None:
        payload = self._smart_editing_settings_dict()
        self._settings["smart_text_effects"] = payload["text_effects"]
        self._settings["smart_sound_effects"] = payload["sound_effects"]
        self._settings["smart_visual_transitions"] = payload["visual_transitions"]
        self._settings["smart_scene_ambience"] = payload["scene_ambience"]
        self._settings["smart_intensity"] = payload["intensity"]
        self._settings["smart_text_effects_intensity"] = payload["text_effects_intensity"]
        self._settings["smart_sound_effects_intensity"] = payload["sound_effects_intensity"]
        self._settings["smart_visual_transitions_intensity"] = payload["visual_transitions_intensity"]
        self._settings["smart_scene_ambience_intensity"] = payload["scene_ambience_intensity"]
        self._settings["smart_scene_ambience_volume"] = payload["scene_ambience_volume"]
        self._settings["smart_mode"] = payload["mode"]
        save_settings(self._settings)
        if self._workspace is not None:
            self._workspace.set_smart_editing_settings(payload)

    def _load_smart_editing_settings_from_project(self, ws) -> None:
        data = ws.smart_editing_settings()
        self.smart_text_effects_var.set(bool(data.get("text_effects", True)))
        self.smart_sfx_var.set(bool(data.get("sound_effects", True)))
        self.smart_visual_transitions_var.set(bool(data.get("visual_transitions", True)))
        self.smart_scene_ambience_var.set(bool(data.get("scene_ambience", True)))
        legacy = str(data.get("intensity") or "medium").title()
        if legacy not in {"Low", "Medium", "High"}:
            legacy = "Medium"

        def _set_intensity(var, key: str) -> None:
            val = str(data.get(key) or legacy).title()
            var.set(val if val in {"Low", "Medium", "High"} else legacy)

        _set_intensity(self.smart_text_intensity_var, "text_effects_intensity")
        _set_intensity(self.smart_sfx_intensity_var, "sound_effects_intensity")
        _set_intensity(self.smart_transitions_intensity_var, "visual_transitions_intensity")
        _set_intensity(self.smart_ambience_intensity_var, "scene_ambience_intensity")
        amb_vol = normalize_ambience_volume(data.get("scene_ambience_volume"))
        self.smart_ambience_volume_var.set(-1.0 if amb_vol is None else amb_vol)
        mode = str(data.get("mode") or "smart").title()
        self.smart_mode_var.set("Automatic" if mode.lower().startswith("auto") else "Smart")

    def _clear_render_preview(self) -> None:
        """Drop final-render thumbnail/path so project switches don't show stale media."""
        self._last_output = None
        self._prev_image = None
        panel = getattr(self, "_preview_panel", None)
        thumb = getattr(self, "_thumb_label", None)
        if thumb is not None:
            try:
                thumb.configure(image=None, text="")
            except Exception:
                pass
        if panel is not None:
            try:
                panel.grid_forget()
            except Exception:
                pass

    def _reset_project_session_ui(self) -> None:
        """Clear in-memory UI tied to the previous project (preview, log, scene chrome)."""
        self._clear_render_preview()
        self._clear_log()
        self._resolved_style = None
        self._style_prompt_adornment = ""
        self._scene_rows = []
        self._scene_row_signature = ()
        self._scene_row_widgets = {}
        self._editorial_plan_cache = None
        self._editorial_plan_mtime = 0.0
        if hasattr(self, "details_title_var"):
            self.details_title_var.set("Selected scene")
        if hasattr(self, "details_text_var"):
            self.details_text_var.set(
                "Select a scene in Visual Plan to inspect assets and editorial cues."
            )
        self.scenes_summary_var.set("")

    def _bind_workspace_paths(self) -> None:
        ws = self._workspace
        if ws is None:
            return
        ws.ensure_dirs()
        self.images_var.set(str(ws.assets_dir))
        if ws.csv_path.is_file():
            self.csv_var.set(str(ws.csv_path))
        elif not self.csv_var.get().strip() or not path_is_inside(Path(self.csv_var.get()), ws.root):
            self.csv_var.set("")
        found = ws.find_voiceover_audio()
        if found is not None:
            # Old projects may have active_voiceover_source "tts" — treat as imported.
            self._set_active_voiceover(found, source="imported")
        else:
            current = self.audio_var.get().strip()
            if current and (not path_is_inside(Path(current), ws.root) or not Path(current).is_file()):
                self.audio_var.set("")
            elif not current:
                self.audio_var.set("")
            self._refresh_voiceover_active_label()
            self._bind_voice_player_to(None)
        self.output_var.set(str(ws.next_final_path()))
        if ws.script_path.is_file() and self._script_mode_is_ai():
            text = ws.script_path.read_text(encoding="utf-8")
            self.script_box.delete("1.0", "end")
            self.script_box.insert("1.0", text)
            self._sync_script_watermark()
        self._sync_export_csv_link()
        self._sync_primary_cta()
        self._refresh_voice_playback_buttons()
        self._rehydrate_visual_plan_from_workspace()

    def _rehydrate_visual_plan_from_workspace(self) -> None:
        """Restore rich VisualDirector fields from ai_visual_plan.json on project open."""
        ws = self._workspace
        if ws is None:
            return
        path = ws.visual_plan_json_path
        if not path.is_file():
            return
        try:
            import json

            payload = json.loads(path.read_text(encoding="utf-8"))
            self._visual_plan = parse_visual_plan(payload)
            print(f"[VISUAL] Rehydrated AI visual plan ({len(self._visual_plan.scenes)} scenes).")
        except Exception as exc:
            print(f"[VISUAL] Could not rehydrate ai_visual_plan.json ({exc}).")

    def _refresh_project_menu(self) -> None:
        """Keep label map in sync. Never show a project name with no workspace."""
        projects = list_projects(self._projects_root_path())
        self._project_labels = {}
        for p in projects:
            label = f"#{p.display_seq()}  {p.title}"
            self._project_labels[label] = p.project_id
        self._project_menu_lock = True
        try:
            if self._workspace is None:
                self.project_menu_var.set("(none)")
            else:
                current = next(
                    (lab for lab, pid in self._project_labels.items()
                     if pid == self._workspace.project_id),
                    "(none)",
                )
                self.project_menu_var.set(current)
            menu = getattr(self, "_project_menu", None)
            if menu is not None:
                values = ["(none)"] if self._workspace is None else (
                    [self.project_menu_var.get()] if self.project_menu_var.get() != "(none)" else ["(none)"]
                )
                menu.configure(values=values)
        finally:
            self._project_menu_lock = False

    def _update_project_indicator(self) -> None:
        ws = self._workspace
        if ws is None:
            self.current_project_title_var.set("No project")
            self.current_project_meta_var.set("Choose a project to start")
            self._project_chip_full = "No project"
            self._apply_chip_text()
            return
        chip = f"#{ws.display_seq()}  {ws.title}"
        self.current_project_title_var.set(ws.title)
        self.current_project_meta_var.set(f"#{ws.display_seq()}  ·  {ws.project_id}")
        self._project_chip_full = chip
        self._apply_chip_text()

    def _mirror_result_into_workspace(self, result, *, sync_state: bool = True) -> None:
        ws = self._workspace
        if ws is None or result is None or not getattr(result, "ok", False):
            return
        path = getattr(result, "path", None)
        if path is None:
            return
        source = getattr(result, "source", None)
        name = getattr(source, "value", None) or str(source or "")
        ws.mirror_provider_asset(name, getattr(result, "scene_number", ""), Path(path))
        if sync_state:
            ws.sync_state_copies()

    def _flush_log_disk(self) -> None:
        self._log_disk_scheduled = False
        if not self._log_disk_buf or self._workspace is None:
            self._log_disk_buf.clear()
            return
        chunk = "".join(self._log_disk_buf)
        self._log_disk_buf.clear()
        try:
            self._workspace.append_log(chunk)
        except Exception:
            pass

    def _schedule_log_disk_flush(self) -> None:
        if self._log_disk_scheduled:
            return
        self._log_disk_scheduled = True
        # Batch disk writes — open/append/close per line freezes Windows during Generate.
        self.after(400, self._flush_log_disk)

    # ---------- browse helpers ----------

    def _browse_csv(self) -> None:
        if not self._require_workspace("import a CSV"):
            return
        path = filedialog.askopenfilename(
            title="Select script CSV",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialdir=str(_browse_start_dir()),
        )
        if path:
            dest = self._workspace.copy_csv_in(Path(path))
            self.csv_var.set(str(dest))
            self._sync_images_dir()
            self._refresh_scene_preview()
            self._goto_workflow_view("visual_plan")
            self._sync_primary_cta()

    def _script_mode_is_ai(self) -> bool:
        mode = getattr(self, "_mode_seg", None)
        if mode is None:
            return True
        return mode.get() in _PASTE_SCRIPT_MODES

    def _refresh_gemini_status(self) -> None:
        from visual_director.llm import gemini_configured

        settings = {"gemini_api_key": self.gemini_key_var.get().strip()}
        if gemini_configured(settings):
            self._gemini_status_var.set("Gemini 3.6 Flash is configured.")
            self.analyze_btn.configure(state="normal")
        else:
            self._gemini_status_var.set(
                "Gemini API key required. Add GEMINI_API_KEY in Settings (⚙) "
                "or as an environment variable to enable AI Script mode."
            )
            self.analyze_btn.configure(state="disabled")

    def _on_script_mode(self, value: str) -> None:
        if getattr(self, "_csv_block", None) is None or getattr(self, "_ai_block", None) is None:
            return
        paste = value in _PASTE_SCRIPT_MODES
        if paste:
            if not self._manual_csv_backup:
                self._manual_csv_backup = self.csv_var.get()
            self._csv_block.grid_remove()
            self._ai_block.grid(row=1, column=0, sticky="ew", padx=16, pady=(10, 0))
            self._refresh_gemini_status()
            if self._visual_plan is not None:
                self._render_scene_rows()
        else:
            self._ai_block.grid_remove()
            self._csv_block.grid(row=1, column=0, sticky="ew", padx=16, pady=(8, 0))
            if self._manual_csv_backup:
                self.csv_var.set(self._manual_csv_backup)
            self._visual_plan = None
            self._sync_export_csv_link()
            self._refresh_scene_preview()
        self._sync_primary_cta()

    def _on_analyze_script(self) -> None:
        if not self._require_workspace("analyze a script"):
            return
        script = self.script_box.get("1.0", "end").strip()
        if not script:
            messagebox.showerror("AI Script", "Paste your complete narration script first.")
            return
        from visual_director.llm import MISSING_GEMINI_KEY, gemini_configured

        settings = {"gemini_api_key": self.gemini_key_var.get().strip()}
        if not gemini_configured(settings):
            messagebox.showerror("AI Script", MISSING_GEMINI_KEY)
            return
        self.analyze_btn.configure(state="disabled", text="Analyzing…")
        if getattr(self, "top_analyze_btn", None) is not None:
            self.top_analyze_btn.configure(state="disabled")
        self.status_var.set("Analyzing script…")
        self._append_log("\n[AI] Analyzing script with Gemini…\n")
        self.progress.set(0.02)

        def on_progress(message: str, fraction: float | None = None) -> None:
            def ui_update() -> None:
                self._append_log(f"[AI] {message}\n")
                self.status_var.set(message[:80])
                if fraction is not None:
                    self.progress.set(max(0.02, min(0.92, float(fraction))))

            self.after(0, ui_update)

        def work():
            try:
                from visual_director import VisualDirector
                from visual_director.director import gemini_plan_settings, script_word_count
                from style_engine import style_prompt_adornment
                from visual_allocation import (
                    apply_allocation_to_plan,
                    build_plan_validation_report,
                    load_allocation_settings,
                )

                words = script_word_count(script)
                opts = gemini_plan_settings(words)
                self.after(
                    0,
                    lambda: self._append_log(
                        f"[AI] Script ~{words} words — Gemini thinking={opts['thinking_level']}, "
                        f"timeout={int(opts['timeout'])}s\n"
                    ),
                )

                resolved = self._resolve_project_style(script=script, persist=True)
                guidance = style_prompt_adornment(resolved)
                plan = VisualDirector(settings=settings).plan(
                    script, style_guidance=guidance, on_progress=on_progress
                )
                self.after(
                    0,
                    lambda: self._append_log("[ALLOC] Running visual allocation…\n"),
                )
                alloc_settings = load_allocation_settings(self._workspace)
                bundle = apply_allocation_to_plan(plan, alloc_settings, resolved)
                plan.set_allocation(bundle.to_dict())
                report = build_plan_validation_report(plan, bundle)
                self.after(0, lambda r=report: self._append_log(f"\n{r}\n"))
                self.after(
                    0,
                    lambda: self._append_log(
                        f"[ALLOC] Visual allocation — {bundle.ai_assigned}/{bundle.ai_budget_limit} "
                        f"Flow video (credits), {bundle.flow_image_assigned} Flow image (free) "
                        f"({bundle.ai_opportunities} opportunities)\n"
                    ),
                )
                self.after(
                    0,
                    lambda: self._append_log(
                        f"[AI] Plan ready — {len(plan.scenes)} scene(s).\n"
                    ),
                )
                self.after(0, lambda p=plan: self._apply_ai_plan(p))
            except Exception as exc:
                msg = str(exc)
                self.after(0, lambda m=msg: self._analyze_failed(m))

        threading.Thread(target=work, daemon=True).start()

    def _analyze_failed(self, message: str) -> None:
        self.analyze_btn.configure(state="normal", text="Analyze Script")
        if getattr(self, "top_analyze_btn", None) is not None:
            self.top_analyze_btn.configure(state="normal")
        self.status_var.set("Ready")
        self.progress.set(0)
        self._refresh_gemini_status()
        messagebox.showerror("AI Script", message)

    def _apply_ai_plan(self, plan) -> None:
        self._visual_plan = plan
        if self._workspace is None:
            self._sync_images_dir()
            csv_path = Path(self.images_var.get()).resolve().parent / "ai_visual_plan.csv"
        else:
            script = self.script_box.get("1.0", "end").strip()
            if script:
                self._workspace.save_script(script)
            plan_payload = plan.to_dict()
            # Property Video only: scene_number -> property_id, stored beside
            # the plan so research candidates stay scoped to their own
            # listing. Absent (and inert) for the normal YouTube workflow.
            pending_scope = getattr(self, "_pending_property_scope", None)
            if pending_scope:
                plan_payload["property_scope"] = dict(pending_scope)
                self._pending_property_scope = None
            self._workspace.save_visual_plan_json(plan_payload)
            csv_path = self._workspace.csv_path
            csv_path.parent.mkdir(parents=True, exist_ok=True)
        plan.write_csv(csv_path)
        self.csv_var.set(str(csv_path))
        self._sync_images_dir()
        self._refresh_scene_preview()
        self._visual_plan = plan
        self._render_scene_rows()
        self.analyze_btn.configure(state="normal", text="Analyze Script")
        if getattr(self, "top_analyze_btn", None) is not None:
            self.top_analyze_btn.configure(state="normal")
        self.status_var.set("Review scenes, then generate assets")
        self.progress.set(1.0)
        self._sync_export_csv_link()
        self._sync_primary_cta()
        self._append_log("\n[AI] Visual plan ready — review scenes, then Generate Video.\n")
        self._append_log(plan.format_preview() + "\n")
        self._goto_workflow_view("visual_plan")

    def _export_ai_csv(self) -> None:
        if self._visual_plan is None:
            messagebox.showinfo("Export CSV", "Analyze a script first.")
            return
        path = filedialog.asksaveasfilename(
            title="Export visual plan CSV",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile="ai_visual_plan.csv",
        )
        if path:
            self._visual_plan.write_csv(Path(path))
            messagebox.showinfo("Export CSV", f"Saved:\n{path}")

    def _voiceover_source_label(self, path: Path | None = None) -> str:
        p = Path(path) if path is not None else None
        if p is None:
            raw = self.audio_var.get().strip()
            p = Path(raw) if raw else None
        if p is None or not p.is_file():
            return "none"
        # Legacy active_voiceover_source "tts" / narration.wav / voiceover_qwen* are
        # treated as normal imported audio (no special Qwen handling).
        return "imported file"

    def _refresh_voiceover_active_label(self) -> None:
        var = getattr(self, "voiceover_active_var", None)
        if var is None:
            return
        raw = self.audio_var.get().strip()
        path = Path(raw) if raw else None
        if path is None or not str(path):
            var.set("No voiceover yet — needed to render")
            return
        if not path.is_file():
            var.set(f"Missing file: {path.name} — re-import voiceover")
            return
        var.set(f"Using {path.name}")

    def _set_active_voiceover(self, path: Path | str, *, source: str) -> None:
        """Bind the single audio file the video pipeline will use."""
        p = Path(path)
        self.audio_var.set(str(p))
        if self._workspace is not None:
            try:
                self._workspace.set_active_voiceover(p, source=source)
            except OSError:
                pass
        self._refresh_voiceover_active_label()
        # Always re-point the Voice panel player — otherwise Play keeps a stale
        # path/duration from a previous longer voiceover.
        self._bind_voice_player_to(p)
        self._sync_primary_cta()

    def _bind_voice_player_to(self, path: Path | str | None) -> None:
        """Stop playback and lock the panel player to this file (or clear it)."""
        # Tear down any in-flight afplay/ffplay without wiping the path we set next.
        proc = self._voice_play_proc
        self._voice_play_proc = None
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=1.5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

        self._voice_play_t0 = None
        self._voice_play_paused = False
        self._voice_play_paused_at = 0.0

        if path is None:
            self._voice_play_path = None
            self._voice_play_duration = 0.0
            self._set_voice_play_progress(0.0, "0:00 / 0:00")
            self._refresh_voice_playback_buttons()
            return

        p = Path(path)
        if not p.is_file():
            self._voice_play_path = None
            self._voice_play_duration = 0.0
            self._set_voice_play_progress(0.0, "0:00 / 0:00")
            self._refresh_voice_playback_buttons()
            return

        duration = self._audio_duration_seconds(p)
        self._voice_play_path = p
        self._voice_play_duration = duration
        clock = self._format_play_clock(duration) if duration > 0 else "0:00"
        self._set_voice_play_progress(0.0, f"0:00 / {clock}")
        self._refresh_voice_playback_buttons()

    def _confirm_voiceover_switch(self, new_path: Path, *, source: str) -> bool:
        current = self.audio_var.get().strip()
        if not current:
            return True
        cur = Path(current)
        try:
            if cur.resolve() == new_path.resolve():
                return True
        except OSError:
            pass
        if not cur.is_file():
            return True
        old_src = self._voiceover_source_label(cur)
        return bool(
            messagebox.askyesno(
                "Switch voiceover?",
                "Only ONE voiceover is used for the video.\n\n"
                f"Currently active:\n  {cur.name}  ({old_src})\n\n"
                f"Replace with:\n  {new_path.name}  (imported file)?\n\n"
                "The file shown in Voiceover Audio is what gets rendered.",
            )
        )

    def _browse_audio(self) -> None:
        path = filedialog.askopenfilename(
            title="Select voiceover audio (this file is used for the video)",
            filetypes=[
                ("Audio", "*.mp3 *.wav *.m4a *.webm *.aac *.flac"),
                ("All files", "*.*"),
            ],
            initialdir=str(_browse_start_dir()),
        )
        if not path:
            return
        src = Path(path)
        dest = src
        if self._workspace is not None:
            self._workspace.ensure_dirs()
            dest = self._workspace.audio_dir / src.name
            try:
                if dest.resolve() != src.resolve():
                    shutil.copy2(src, dest)
            except OSError:
                dest = src
        if not self._confirm_voiceover_switch(dest, source="imported"):
            return
        self._set_active_voiceover(dest, source="imported")
        self.status_var.set(f"Voiceover set: {dest.name} (imported file)")
        self._append_log(f"[AUDIO] Video will use imported voiceover: {dest.name}\n")
        self._sync_primary_cta()
        self._goto_workflow_view("music")

    def _current_voiceover_path(self) -> Path | None:
        """Return the bound voiceover path if the file exists."""
        raw = self.audio_var.get().strip()
        if not raw:
            return None
        path = Path(raw)
        return path if path.is_file() else None

    def _audio_duration_seconds(self, path: Path) -> float:
        path = Path(path)
        try:
            import wave

            if path.suffix.lower() == ".wav":
                with wave.open(str(path), "rb") as wf:
                    rate = float(wf.getframerate() or 0)
                    if rate > 0:
                        return wf.getnframes() / rate
        except Exception:
            pass
        ffprobe = shutil.which("ffprobe")
        if not ffprobe:
            return 0.0
        try:
            from providers import hidden_subprocess

            out = hidden_subprocess.check_output(
                [
                    ffprobe,
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    str(path),
                ],
                text=True,
                timeout=8,
            )
            return max(0.0, float((out or "").strip()))
        except Exception:
            return 0.0

    @staticmethod
    def _format_play_clock(seconds: float) -> str:
        seconds = max(0, int(seconds))
        mm, ss = divmod(seconds, 60)
        hh, mm = divmod(mm, 60)
        if hh:
            return f"{hh:d}:{mm:02d}:{ss:02d}"
        return f"{mm:d}:{ss:02d}"

    def _set_voice_play_progress(self, fraction: float, label: str = "") -> None:
        bar = getattr(self, "voice_play_progress", None)
        var = getattr(self, "voice_play_progress_var", None)
        if bar is not None:
            bar.set(max(0.0, min(1.0, float(fraction))))
        if var is not None:
            var.set(label or "")

    def _reset_voice_play_progress(self) -> None:
        self._voice_play_t0 = None
        self._voice_play_duration = 0.0
        self._voice_play_paused = False
        self._voice_play_paused_at = 0.0
        self._set_voice_play_progress(0.0, "0:00 / 0:00")

    def _refresh_voice_playback_buttons(self) -> None:
        play_btn = getattr(self, "_play_voice_btn", None)
        if play_btn is None:
            return
        has_audio = self._current_voiceover_path() is not None or self._voice_play_path is not None
        playing = (
            self._voice_play_proc is not None
            and self._voice_play_proc.poll() is None
        )
        paused = bool(getattr(self, "_voice_play_paused", False))
        play_btn.configure(
            state="normal" if has_audio else "disabled",
            text="⏸  Pause" if playing else "▶  Play",
        )
        stop_btn = getattr(self, "_stop_voice_btn", None)
        if stop_btn is not None:
            stop_btn.configure(state="normal" if (playing or paused or has_audio) else "disabled")
        self._sync_voice_progress_visibility(playing or paused)

    def _sync_voice_progress_visibility(self, visible: bool) -> None:
        bar = getattr(self, "voice_play_progress", None)
        label = getattr(self, "voice_play_progress_label", None)
        if bar is None:
            return
        if visible:
            bar.grid()
            if label is not None:
                label.grid()
        else:
            bar.grid_remove()
            if label is not None:
                label.grid_remove()

    def _stop_voice_playback(self) -> None:
        """Stop playback and reset the timestamp to 0:00."""
        proc = self._voice_play_proc
        self._voice_play_proc = None
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=1.5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        self._reset_voice_play_progress()
        self._refresh_voice_playback_buttons()

    def _pause_voice_playback(self) -> None:
        proc = self._voice_play_proc
        elapsed = 0.0
        t0 = self._voice_play_t0
        if t0 is not None:
            elapsed = max(0.0, time.monotonic() - t0)
        self._voice_play_proc = None
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=1.5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        self._voice_play_paused = True
        self._voice_play_paused_at = elapsed
        self._voice_play_t0 = None
        total = float(self._voice_play_duration or 0.0)
        if total > 0:
            frac = min(0.999, elapsed / total)
            self._set_voice_play_progress(
                frac,
                f"{self._format_play_clock(min(elapsed, total))} / {self._format_play_clock(total)}",
            )
        self._refresh_voice_playback_buttons()

    def _toggle_voice_playback(self) -> None:
        playing = (
            self._voice_play_proc is not None
            and self._voice_play_proc.poll() is None
        )
        if playing:
            self._pause_voice_playback()
            return

        active = self._current_voiceover_path()
        play_path = self._voice_play_path
        # Prefer the active video voiceover over a stale Play path (e.g. an older
        # 27‑minute import). Preview clips keep their own path until overwritten.
        if active is not None:
            if play_path is None or not play_path.is_file():
                play_path = active
                self._voice_play_paused_at = 0.0
            else:
                try:
                    same = play_path.resolve() == active.resolve()
                except OSError:
                    same = False
                if not same:
                    play_path = active
                    self._voice_play_paused_at = 0.0

        path = play_path or active
        if path is None:
            messagebox.showinfo(
                "Play Voice",
                "Import a voiceover audio file first, then you can play it here.",
            )
            self._refresh_voice_playback_buttons()
            return
        start_at = float(getattr(self, "_voice_play_paused_at", 0.0) or 0.0)
        if self._start_voice_playback(Path(path), start_at=start_at):
            self.status_var.set(f"Playing {Path(path).name}…")
            self._append_log(f"[AUDIO] Playing voiceover: {Path(path).name}\n")

    def _start_voice_playback(self, path: Path, *, start_at: float = 0.0) -> bool:
        path = Path(path)
        if not path.is_file():
            messagebox.showwarning("Play Voice", f"Audio not found:\n{path}")
            return False
        player = shutil.which("ffplay") or shutil.which("afplay")
        if not player:
            messagebox.showerror(
                "Play Voice",
                "No audio player found (afplay / ffplay).",
            )
            return False
        # Stop any active process without wiping the pause/seek state we want.
        proc = self._voice_play_proc
        self._voice_play_proc = None
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=1.0)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

        start_at = max(0.0, float(start_at or 0.0))
        player_name = Path(player).name
        if player_name.startswith("ffplay"):
            cmd = [
                player,
                "-nodisp",
                "-autoexit",
                "-loglevel",
                "quiet",
                "-ss",
                f"{start_at:.3f}",
                str(path),
            ]
        else:
            # afplay cannot seek; resume from pause restarts from the beginning.
            cmd = [player, str(path)]
            start_at = 0.0

        try:
            from providers import hidden_subprocess

            self._voice_play_proc = hidden_subprocess.popen(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except OSError as exc:
            messagebox.showerror("Play Voice", str(exc))
            self._voice_play_proc = None
            self._refresh_voice_playback_buttons()
            return False

        self._voice_play_path = path
        self._voice_play_paused = False
        self._voice_play_paused_at = 0.0
        self._voice_play_duration = self._audio_duration_seconds(path)
        self._voice_play_t0 = time.monotonic() - start_at
        total = self._voice_play_duration
        if total > 0:
            self._set_voice_play_progress(
                min(0.999, start_at / total) if total else 0.0,
                f"{self._format_play_clock(start_at)} / {self._format_play_clock(total)}",
            )
        else:
            self._set_voice_play_progress(0.02, "Playing…")
        self._refresh_voice_playback_buttons()
        self._watch_voice_playback()
        return True

    def _watch_voice_playback(self) -> None:
        proc = self._voice_play_proc
        if proc is None:
            return
        if proc.poll() is None:
            t0 = self._voice_play_t0
            total = float(self._voice_play_duration or 0.0)
            if t0 is not None:
                elapsed = max(0.0, time.monotonic() - t0)
                if total > 0:
                    frac = min(0.999, elapsed / total)
                    self._set_voice_play_progress(
                        frac,
                        f"{self._format_play_clock(min(elapsed, total))} / {self._format_play_clock(total)}",
                    )
                else:
                    cycle = elapsed % 1.8
                    pulse = 0.12 + (cycle / 1.8) * 0.5
                    self._set_voice_play_progress(pulse, f"Playing…  {self._format_play_clock(elapsed)}")
            self.after(250, self._watch_voice_playback)
            return
        self._voice_play_proc = None
        total = float(self._voice_play_duration or 0.0)
        if total > 0:
            self._set_voice_play_progress(1.0, f"{self._format_play_clock(total)} / {self._format_play_clock(total)}")
            self.after(800, self._reset_voice_play_progress)
        else:
            self._reset_voice_play_progress()
        self._refresh_voice_playback_buttons()

    def _browse_bg(self) -> None:
        path = filedialog.askopenfilename(
            title="Select background music (optional)",
            filetypes=[
                ("Audio", "*.mp3 *.wav *.m4a *.webm *.aac *.flac"),
                ("All files", "*.*"),
            ],
            initialdir=str(_browse_start_dir()),
        )
        if path:
            self.bg_var.set(path)

    def _browse_output(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Save video as",
            defaultextension=".mp4",
            filetypes=[("MP4 video", "*.mp4"), ("All files", "*.*")],
            initialdir=str(_browse_start_dir()),
            initialfile="final.mp4",
        )
        if path:
            self.output_var.set(path)

    # ---------- scenes preview / asset pipeline ----------

    def _refresh_scene_preview(self) -> None:
        """Parse the chosen CSV (if any) and repaint the Scenes table with each
        row's routed source. Cheap — no network, no provider calls — just
        SceneAssetRouter.classify() against the CSV columns."""
        csv_path = self.csv_var.get().strip()
        rows: list[dict] = []
        if csv_path and Path(csv_path).is_file():
            try:
                with open(csv_path, newline="", encoding="utf-8-sig") as f:
                    reader = csv.DictReader(f)
                    rows = list(reader)
                if not rows or "scene_number" not in reader.fieldnames:
                    rows = []
            except (OSError, csv.Error):
                rows = []
        self._scene_rows = [SceneRow.from_csv_row(r) for r in rows]
        self._hydrated_skipped.clear()
        self._qa.selected_failed.clear()
        self._render_scene_rows()
        self._hydrate_assets_from_manifest()
        self._refresh_assets_cta()

    def _hydrate_assets_from_manifest(self) -> None:
        """Restore Success/Needs-action from Images/.asset_manifest.json after a CSV load."""
        csv_path = self.csv_var.get().strip()
        images_raw = self.images_var.get().strip()
        if csv_path:
            self._sync_images_dir()
            images_raw = self.images_var.get().strip()
        if not images_raw:
            return
        images_dir = Path(images_raw)
        manifest_path = images_dir / ".asset_manifest.json"
        if not manifest_path.is_file():
            return
        from asset_manager import AssetManifest

        manifest = AssetManifest(images_dir)
        qa_data = load_qa_file(images_dir)
        for key, count in (qa_data.get("attempts") or {}).items():
            try:
                self._qa.attempts[_scene_key(key)] = int(count)
            except (TypeError, ValueError):
                pass
        for key in qa_data.get("skipped") or []:
            self._hydrated_skipped.add(_scene_key(key))
        restored: dict[str, AssetResult] = {}
        media_index = vg.build_scene_media_index(images_dir) if images_dir.is_dir() else {}
        for scene in self._scene_rows:
            key = _scene_key(scene.scene_number)
            rec = manifest.get(scene.scene_number) or {}
            path = Path(rec["local_path"]) if rec.get("local_path") else None
            if path is not None and self._workspace is not None:
                if not asset_belongs_to_project(path, self._workspace):
                    continue
            if rec.get("status") == "complete" and path is not None and path.is_file():
                media = MediaType.VIDEO if vg.is_video_file(path) else MediaType.IMAGE
                try:
                    source = AssetSource(str(rec.get("source") or "local"))
                except ValueError:
                    source = SceneAssetRouter.classify(scene) or AssetSource.LOCAL
                restored[key] = AssetResult(
                    scene_number=scene.scene_number,
                    path=path,
                    media_type=media,
                    source=source,
                    status=SceneStatus.READY,
                    metadata=rec,
                )
            elif rec.get("status") == "failed":
                err = str(rec.get("error") or "Previous attempt failed")
                if "placeholder only" in err.lower() or err.lower().startswith("skipped"):
                    restored[key] = AssetResult(
                        scene_number=scene.scene_number,
                        path=path if path is not None and path.is_file() else None,
                        media_type=MediaType.IMAGE,
                        source=SceneAssetRouter.classify(scene) or AssetSource.LOCAL,
                        status=SceneStatus.SKIPPED,
                        error=err,
                    )
                    self._hydrated_skipped.add(key)
                else:
                    restored[key] = AssetResult(
                        scene_number=scene.scene_number,
                        path=None,
                        media_type=None,
                        source=SceneAssetRouter.classify(scene) or AssetSource.LOCAL,
                        status=SceneStatus.NEEDS_ACTION,
                        error=err,
                    )
            elif SceneAssetRouter.classify(scene) is None:
                existing = vg.find_image_for_scene(
                    images_dir, scene.scene_number, ext_cache=media_index
                )
                if existing is not None:
                    media = MediaType.VIDEO if vg.is_video_file(existing) else MediaType.IMAGE
                    restored[key] = AssetResult(
                        scene_number=scene.scene_number,
                        path=existing,
                        media_type=media,
                        source=AssetSource.LOCAL,
                        status=SceneStatus.READY,
                    )
        for scene in self._scene_rows:
            key = _scene_key(scene.scene_number)
            if key in restored:
                self._asset_results[key] = restored[key]
            elif key not in self._busy_scenes:
                self._asset_results.pop(key, None)
        self._sync_scene_statuses_from_results()
        self._refresh_qa_ui()

    def _skipped_set(self) -> set[str]:
        skipped = set(self._hydrated_skipped)
        if self._asset_manager is not None:
            skipped |= set(self._asset_manager.recovery.skipped)
        for key, result in self._asset_results.items():
            if getattr(result, "status", None) == SceneStatus.SKIPPED:
                skipped.add(key)
        return skipped

    def _qa_snapshot(self):
        return self._qa.snapshot(self._scene_rows, self._asset_results, self._skipped_set())

    def _row_status_from_result(self, scene: SceneRow) -> str:
        return self._qa.row_status(scene, self._asset_results, self._skipped_set())

    def _sync_scene_statuses_from_results(self) -> None:
        for scene in self._scene_rows:
            key = _scene_key(scene.scene_number)
            if key in self._busy_scenes:
                continue
            self._set_scene_status(scene.scene_number, self._row_status_from_result(scene))

    def _scenes_needing_retry(self) -> list[SceneRow]:
        snap = self._qa_snapshot()
        by_key = {_scene_key(s.scene_number): s for s in self._scene_rows}
        return [by_key[k] for k in snap.unresolved_keys if k in by_key]

    def _retry_all_attention_scenes(self) -> None:
        self._bulk_recovery("retry", selected_only=False)

    def _pump_retry_queue(self) -> None:
        # Prefer one batched Flow GENERATE for pending Flow retries (avoids N
        # parallel jobs all hitting a busy engine).
        self._try_start_flow_retry_batch()
        max_inflight = 4
        while self._recovery_queue and len(self._busy_scenes) < max_inflight:
            action, scene = self._recovery_queue[0]
            key = _scene_key(scene.scene_number)
            if key in self._busy_scenes:
                self._recovery_queue.pop(0)
                continue
            result = self._asset_results.get(key)
            if result is not None and getattr(result, "ok", False) and action != "skip":
                self._recovery_queue.pop(0)
                self._recovery_done += 1
                continue
            # Flow retries belong in the batch starter — wait if a batch is active.
            if action == "retry" and self._scene_is_flow(scene):
                if getattr(self, "_flow_retry_batch_busy", False):
                    break
                if self._try_start_flow_retry_batch():
                    continue
                # Fallback: single-scene Flow retry if batching could not start.
            self._recovery_queue.pop(0)
            self._scene_action(action, scene)
        if self._recovery_total:
            in_flight = len(self._busy_scenes)
            done = max(0, self._recovery_total - len(self._recovery_queue) - in_flight)
            if self._recovery_queue or in_flight:
                self._set_qa_bulk_progress(
                    f"RECOVERING FAILED SCENES  {done} / {self._recovery_total}"
                )
        if self._recovery_queue or (self._retry_pumping and self._busy_scenes and self._recovery_total):
            self.after(400, self._pump_retry_queue)
            return
        if self._recovery_total:
            snap = self._qa_snapshot()
            recovered = self._recovery_total - snap.needs_action
            if snap.needs_action:
                self._set_qa_bulk_progress(
                    f"{max(0, recovered)} / {self._recovery_total} recovered · "
                    f"{snap.needs_action} scene(s) still need attention"
                )
            else:
                self._set_qa_bulk_progress(f"{self._recovery_total} / {self._recovery_total} recovered")
            self._recovery_total = 0
        self._retry_pumping = False
        self._refresh_qa_ui()

    def _set_qa_bulk_progress(self, text: str = "") -> None:
        self.qa_bulk_progress_var.set(text or "")
        lbl = getattr(self, "_qa_bulk_progress_label", None)
        if lbl is None:
            return
        if text:
            lbl.grid()
        else:
            lbl.grid_remove()

    def _scene_is_flow(self, scene: SceneRow) -> bool:
        from providers.router import SceneAssetRouter

        source = SceneAssetRouter.classify(scene)
        return source in (AssetSource.FLOW_IMAGE, AssetSource.FLOW_VIDEO)

    def _start_flow_batch(
        self,
        scenes: list,
        *,
        provider_name: str | None = None,
    ) -> bool:
        """Run one Flow GENERATE for many scenes (retry or bulk change source)."""
        if getattr(self, "_flow_retry_batch_busy", False):
            return False
        if not self._require_workspace("retry or change a scene"):
            return False
        ready: list = []
        for scene in scenes:
            key = _scene_key(scene.scene_number)
            if key in self._busy_scenes:
                continue
            ready.append(scene)
        if not ready:
            return False

        if provider_name:
            updated = [self._apply_scene_source_choice(s, provider_name) for s in ready]
            log_line = (
                f"[QA] Flow batch change source -> {provider_name} — "
                f"{len(updated)} scene(s) in one GENERATE\n"
            )
            job_kind = "generating"
        else:
            updated = ready
            log_line = f"[QA] Flow batch retry — {len(updated)} scene(s) in one GENERATE\n"
            job_kind = "retrying"

        if not self.images_var.get().strip():
            self._sync_images_dir()
        images_dir = self._workspace.assets_dir
        tokens: dict[str, int] = {}
        for scene in updated:
            key = _scene_key(scene.scene_number)
            tokens[key] = self._qa.begin_job(key, job_kind)
            self._busy_scenes.add(key)
            # QUEUED, not job_kind — this scene hasn't necessarily gotten a
            # Flow worker yet (see _on_scene_generating below). Arming the
            # 12-minute watchdog here, before the scene is actually in
            # flight, is what let a big batch time out scenes that were
            # simply still waiting their turn.
            self._set_scene_status(scene.scene_number, "waiting")
        self._flow_retry_batch_busy = True
        self._paint_qa_chrome()
        self._append_log(log_line)

        def _on_scene_generating(scene: SceneRow) -> None:
            self._ui_queue.put(("scene_busy", (scene.scene_number, job_kind)))

        def worker() -> None:
            old_out, old_err = sys.stdout, sys.stderr
            writer = _QueueWriter(self._ui_queue)
            sys.stdout = writer
            sys.stderr = writer
            results: dict = {}
            try:
                mgr = self._ensure_asset_manager(images_dir)
                if provider_name:
                    results = mgr.change_source_flow_batch(
                        updated, provider_name, on_scene_generating=_on_scene_generating,
                    )
                else:
                    results = mgr.retry_flow_batch(updated, on_scene_generating=_on_scene_generating)
            except Exception as exc:
                for scene in updated:
                    results[_scene_key(scene.scene_number)] = AssetResult(
                        scene.scene_number, None, None,
                        AssetSource.FLOW_IMAGE, SceneStatus.NEEDS_ACTION, error=str(exc),
                    )
            finally:
                writer.flush()
                sys.stdout = old_out
                sys.stderr = old_err
                self._ui_queue.put(("flow_retry_batch_done", None))
                for scene in updated:
                    key = _scene_key(scene.scene_number)
                    result = results.get(scene.scene_number) or results.get(key)
                    if result is None:
                        result = AssetResult(
                            scene.scene_number, None, None,
                            AssetSource.FLOW_IMAGE, SceneStatus.NEEDS_ACTION,
                            error="Flow batch returned no result for this scene.",
                        )
                    try:
                        self._mirror_result_into_workspace(result, sync_state=False)
                    except Exception:
                        pass
                    self._ui_queue.put(("scene_result", (scene.scene_number, tokens.get(key, 0), result)))
                try:
                    if self._workspace is not None:
                        self._workspace.sync_state_copies()
                except Exception:
                    pass

        threading.Thread(target=worker, daemon=True).start()
        return True

    def _try_start_flow_retry_batch(self) -> bool:
        """Drain queued Flow retries into one engine GENERATE. Returns True if started."""
        if getattr(self, "_flow_retry_batch_busy", False):
            return False
        if not self._require_workspace("retry or change a scene"):
            return False
        flow_items: list[tuple[str, SceneRow]] = []
        rest: list[tuple[str, SceneRow]] = []
        for action, scene in self._recovery_queue:
            if action == "retry" and self._scene_is_flow(scene):
                key = _scene_key(scene.scene_number)
                if key in self._busy_scenes:
                    continue
                result = self._asset_results.get(key)
                if result is not None and getattr(result, "ok", False):
                    continue
                flow_items.append((action, scene))
            else:
                rest.append((action, scene))
        if len(flow_items) < 1:
            return False
        self._recovery_queue = rest
        scenes = [s for _, s in flow_items]
        return self._start_flow_batch(scenes, provider_name=None)

    # Batches keep the event loop responsive for large visual plans without
    # changing row widgets / QA behavior once construction finishes.
    _SCENE_ROW_SYNC_LIMIT = _scene_list.SCENE_ROW_SYNC_LIMIT
    _SCENE_ROW_BATCH = _scene_list.SCENE_ROW_BATCH

    def _remember_scene_scroll(self) -> None:
        canvas = getattr(getattr(self, "_scenes_list", None), "_parent_canvas", None)
        if canvas is None:
            return
        try:
            self._scene_scroll_frac = float(canvas.yview()[0])
        except Exception:
            pass

    def _restore_scene_scroll(self) -> None:
        canvas = getattr(getattr(self, "_scenes_list", None), "_parent_canvas", None)
        if canvas is None:
            return
        try:
            canvas.yview_moveto(float(getattr(self, "_scene_scroll_frac", 0.0) or 0.0))
        except Exception:
            pass
        self._schedule_scene_window_refresh()

    def _bind_scene_list_scroll(self) -> None:
        if getattr(self, "_scene_window_bound", False):
            return
        canvas = getattr(getattr(self, "_scenes_list", None), "_parent_canvas", None)
        if canvas is None:
            return
        self._scene_window_bound = True

        def _on_scroll(*_args):
            self._schedule_scene_window_refresh()

        try:
            canvas.bind("<Configure>", lambda _e: self._schedule_scene_window_refresh(), add="+")
            # Mousewheel / trackpad often route through the canvas yview command.
            prev = canvas.cget("yscrollcommand")
            def _yscroll(*args):
                if callable(prev):
                    prev(*args)
                elif prev:
                    try:
                        self.tk.call(prev, *args)
                    except Exception:
                        pass
                self._schedule_scene_window_refresh()
            canvas.configure(yscrollcommand=_yscroll)
        except Exception:
            pass

    def _schedule_scene_window_refresh(self) -> None:
        if getattr(self, "_scene_window_pending", False):
            return
        if not _scene_list.should_window(len(getattr(self, "_scene_rows", None) or [])):
            return
        self._scene_window_pending = True

        def _run():
            self._scene_window_pending = False
            try:
                self._refresh_scene_window()
            except Exception:
                pass

        self.after(40, _run)

    def _scene_viewport_metrics(self) -> tuple[float, float]:
        canvas = getattr(getattr(self, "_scenes_list", None), "_parent_canvas", None)
        if canvas is None:
            return 0.0, 400.0
        try:
            top = float(canvas.canvasy(0))
            h = float(max(canvas.winfo_height(), 1))
            return top, h
        except Exception:
            return 0.0, 400.0

    def _render_scene_rows(self) -> None:
        signature = tuple(_scene_key(s.scene_number) for s in self._scene_rows)
        total = len(self._scene_rows)
        use_window = _scene_list.should_window(total)
        if (
            signature
            and signature == self._scene_row_signature
            and self._scene_row_widgets
            and (use_window or len(self._scene_row_widgets) == total)
        ):
            if use_window:
                self._schedule_scene_window_refresh()
            self._refresh_qa_ui(immediate=True)
            return

        self._scene_render_gen += 1
        gen = self._scene_render_gen

        for child in self._scenes_list.winfo_children():
            child.destroy()
        self._scene_row_widgets = {}
        self._scene_row_signature = ()
        self._scene_window_first = 0
        self._scene_window_last = 0
        self._scene_spacer_top = None
        self._scene_spacer_bottom = None
        self._scene_header = None

        empty = getattr(self, "_scenes_empty_label", None)
        if empty is not None:
            if not self._scene_rows:
                empty.grid()
            else:
                empty.grid_remove()

        if not self._scene_rows:
            self.scenes_summary_var.set("")
            self._refresh_qa_ui(immediate=True)
            return

        self._build_scene_list_header()
        self._bind_scene_list_scroll()

        if not use_window:
            if total <= self._SCENE_ROW_SYNC_LIMIT:
                for i, scene in enumerate(self._scene_rows):
                    self._decorate_scene_row(i, scene)
                self._scene_row_signature = signature
                self._refresh_qa_ui(immediate=True)
                return

            def _batch(start: int) -> None:
                if gen != self._scene_render_gen:
                    return
                end = min(start + self._SCENE_ROW_BATCH, total)
                for i in range(start, end):
                    self._decorate_scene_row(i, self._scene_rows[i])
                if end < total:
                    self.after(1, lambda: _batch(end))
                else:
                    self._scene_row_signature = signature
                    self._refresh_qa_ui(immediate=True)

            self.after_idle(lambda: _batch(0))
            return

        # Windowed path: spacers + visible slice only (no per-scroll disk I/O).
        self._scene_spacer_top = ctk.CTkFrame(self._scenes_list, fg_color="transparent", height=1)
        self._scene_spacer_top.grid(row=1, column=0, sticky="ew")
        self._scene_spacer_bottom = ctk.CTkFrame(self._scenes_list, fg_color="transparent", height=1)
        self._scene_spacer_bottom.grid(row=2, column=0, sticky="ew")
        self._scene_row_signature = signature
        self._refresh_scene_window(force=True)
        self._refresh_qa_ui(immediate=True)

    def _build_scene_list_header(self) -> None:
        header = ctk.CTkFrame(self._scenes_list, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=0, pady=(0, 4))
        header.grid_columnconfigure(3, weight=1)
        self._scene_header = header
        self._scene_header_check_var = ctk.BooleanVar(value=False)
        self._scene_header_check = ctk.CTkCheckBox(
            header, text="", width=18, checkbox_width=14, checkbox_height=14,
            variable=self._scene_header_check_var,
            command=self._on_header_select_all,
        )
        self._scene_header_check.grid(row=0, column=0, sticky="w", padx=(6, 0), pady=2)
        cols = (
            ("#", 28),
            ("Time", 72),
            ("Narration", 110),
            ("Visual", 100),
            ("Src", 56),
            ("Cam", 52),
            ("Tr", 40),
            ("Amb", 48),
            ("Status", 90),
            ("", 44),
        )
        for i, (title, width) in enumerate(cols):
            ctk.CTkLabel(
                header, text=title, width=width, anchor="w",
                font=ctk.CTkFont(size=10, weight="bold"), text_color=_MUTED,
            ).grid(row=0, column=i + 1, sticky="w", padx=2)

    def _refresh_scene_window(self, force: bool = False) -> None:
        total = len(self._scene_rows)
        if not _scene_list.should_window(total):
            return
        top, vh = self._scene_viewport_metrics()
        first, last = _scene_list.window_bounds(
            total=total, scroll_top_px=top, viewport_h=vh,
        )
        if (
            not force
            and first == getattr(self, "_scene_window_first", -1)
            and last == getattr(self, "_scene_window_last", -1)
            and self._scene_row_widgets
        ):
            return
        # Destroy rows outside the new window
        keep = {_scene_key(self._scene_rows[i].scene_number) for i in range(first, last)}
        for key, widgets in list(self._scene_row_widgets.items()):
            if key not in keep:
                row = widgets.get("row")
                if row is not None:
                    try:
                        row.destroy()
                    except Exception:
                        pass
                self._scene_row_widgets.pop(key, None)
        rh = _scene_list.SCENE_ROW_HEIGHT
        top_sp = getattr(self, "_scene_spacer_top", None)
        bot_sp = getattr(self, "_scene_spacer_bottom", None)
        if top_sp is not None:
            top_sp.configure(height=max(1, first * rh))
            top_sp.grid(row=1, column=0, sticky="ew")
        # Materialize missing rows in window (grid after spacer)
        for i in range(first, last):
            scene = self._scene_rows[i]
            key = _scene_key(scene.scene_number)
            if key in self._scene_row_widgets:
                widgets = self._scene_row_widgets[key]
                row = widgets.get("row")
                if row is not None:
                    row.grid(row=i - first + 2, column=0, sticky="ew", pady=0)
                continue
            self._decorate_scene_row(i, scene, grid_row=i - first + 2)
        if bot_sp is not None:
            bot_sp.configure(height=max(1, (total - last) * rh))
            bot_sp.grid(row=last - first + 2, column=0, sticky="ew")
        self._scene_window_first = first
        self._scene_window_last = last

    def _decorate_scene_row(self, i: int, scene: SceneRow, grid_row: int | None = None) -> None:
        """Build one denser scene-table row (shared by sync / batch / window paths)."""
        from ui.scene_list import truncate as _trunc

        badge_text, badge_fg, badge_bg = scene_source_badge(scene)
        default_fg = _ROW_ALT if i % 2 else "transparent"
        row = ctk.CTkFrame(
            self._scenes_list, fg_color=default_fg, corner_radius=4, height=28,
        )
        row.grid(row=(grid_row if grid_row is not None else i + 1), column=0, sticky="ew", pady=0)
        row.grid_columnconfigure(3, weight=1)

        key = _scene_key(scene.scene_number)
        check_var = ctk.BooleanVar(value=key in self._qa.selected_failed)
        check = ctk.CTkCheckBox(
            row, text="", width=18, checkbox_width=14, checkbox_height=14,
            variable=check_var,
            command=lambda k=key, v=check_var: self._on_scene_check(k, v),
        )
        check.grid(row=0, column=0, sticky="w", padx=(6, 0), pady=1)

        ctk.CTkLabel(
            row, text=f"{scene.scene_number}", width=28,
            font=ctk.CTkFont(size=11, weight="bold"), text_color=_TEXT, anchor="w",
        ).grid(row=0, column=1, sticky="w", padx=2)

        time_label = ctk.CTkLabel(
            row, text=self._scene_time_label(scene.scene_number), width=72, anchor="w",
            font=ctk.CTkFont(size=9), text_color=_MUTED,
        )
        time_label.grid(row=0, column=2, sticky="w", padx=2)

        narr_label = ctk.CTkLabel(
            row, text=_trunc(scene.script_segment, 36), width=110, anchor="w",
            font=ctk.CTkFont(size=10), text_color=_TEXT,
        )
        narr_label.grid(row=0, column=3, sticky="ew", padx=2)

        visual = scene.prompt or scene.stock or scene.visual_description or ""
        vis_label = ctk.CTkLabel(
            row, text=_trunc(visual, 32), width=100, anchor="w",
            font=ctk.CTkFont(size=10), text_color=_MUTED,
        )
        vis_label.grid(row=0, column=4, sticky="w", padx=2)

        badge = ctk.CTkLabel(
            row, text=badge_text, font=ctk.CTkFont(size=9),
            text_color=badge_fg, fg_color=badge_bg, corner_radius=4, width=56, anchor="w",
        )
        badge.grid(row=0, column=5, sticky="w", padx=2)

        ed = self._editorial_scene_lookup(scene.scene_number)
        cam = (ed.get("camera_style") or "—")[:10]
        tr = (ed.get("transition_in") or "cut")[:6]
        amb = (ed.get("ambience_profile") or "—")[:8]
        sfx_mark = "·" if (ed.get("sfx_events") or ed.get("sfx")) else ""
        cam_label = ctk.CTkLabel(
            row, text=cam, width=52, anchor="w", font=ctk.CTkFont(size=9), text_color=_MUTED,
        )
        cam_label.grid(row=0, column=6, sticky="w", padx=2)
        tr_label = ctk.CTkLabel(
            row, text=tr, width=40, anchor="w", font=ctk.CTkFont(size=9), text_color=_MUTED,
        )
        tr_label.grid(row=0, column=7, sticky="w", padx=2)
        amb_label = ctk.CTkLabel(
            row, text=f"{amb}{sfx_mark}", width=48, anchor="w",
            font=ctk.CTkFont(size=9), text_color=_MUTED,
        )
        amb_label.grid(row=0, column=8, sticky="w", padx=2)

        status_label = ctk.CTkLabel(
            row, text="◌ QUEUED", font=ctk.CTkFont(size=10, weight="bold"),
            text_color=_QUEUED, width=90, anchor="w",
        )
        status_label.grid(row=0, column=9, sticky="w", padx=2)

        open_btn = ctk.CTkButton(
            row, text="Open", width=44, height=20,
            fg_color="transparent", border_width=1, border_color=_BORDER,
            text_color=_SUCCESS, font=ctk.CTkFont(size=9),
            command=lambda n=scene.scene_number: self._open_scene_asset(n),
        )
        open_btn.grid(row=0, column=10, sticky="e", padx=(0, 2))
        open_btn.grid_remove()

        source_btn = ctk.CTkButton(
            row, text="Src", width=40, height=20,
            fg_color="transparent", border_width=1, border_color=_BORDER,
            text_color=_ACCENT, font=ctk.CTkFont(size=9),
            command=lambda s=scene: self._change_source_dialog(s),
        )
        source_btn.grid(row=0, column=11, sticky="e", padx=(0, 4))

        preview_label = ctk.CTkLabel(row, text="", font=ctk.CTkFont(size=1))
        elapsed_label = ctk.CTkLabel(row, text="", font=ctk.CTkFont(size=10), text_color=_MUTED, width=1)
        error_label = ctk.CTkLabel(row, text="", font=ctk.CTkFont(size=1), text_color=_WARNING)
        self._scene_row_widgets[key] = {
            "status_label": status_label,
            "time_label": time_label,
            "elapsed_label": elapsed_label,
            "error_label": error_label,
            "badge": badge,
            "buttons": {"source": source_btn, "open": open_btn},
            "scene": scene,
            "row": row,
            "default_fg": default_fg,
            "check_var": check_var,
            "check": check,
            "index": i,
        }
        row.bind("<Button-1>", lambda _e, k=key: self._focus_scene(k, scroll=False))
        preview_label.bind("<Button-1>", lambda _e, k=key: self._focus_scene(k, scroll=False))
        for widget in (status_label, time_label, badge, narr_label, vis_label, cam_label, tr_label, amb_label):
            widget.bind("<Button-1>", lambda _e, k=key: self._focus_scene(k, scroll=False))

        if key in self._busy_scenes:
            busy = self._qa.busy.get(key) or "generating"
            self._set_scene_status(scene.scene_number, busy)
        elif key in self._asset_results or key in self._hydrated_skipped:
            self._set_scene_status(scene.scene_number, self._row_status_from_result(scene))
        else:
            self._sync_row_action_buttons(key)

    def _sync_row_action_buttons(self, key: str) -> None:
        widgets = self._scene_row_widgets.get(key)
        if not widgets:
            return
        busy = key in self._busy_scenes or key in self._qa.busy
        buttons = widgets.get("buttons") or {}
        cancel = buttons.get("cancel")
        if cancel is not None:
            cancel.configure(state="normal" if busy else "disabled")
        open_btn = buttons.get("open")
        if open_btn is not None:
            scene = widgets.get("scene")
            path_ok = False
            if scene is not None and not busy:
                status = self._row_status_from_result(scene)
                path_ok = status in ("ready", "success") and self._scene_asset_path(scene.scene_number) is not None
            if path_ok:
                open_btn.grid()
                open_btn.configure(state="normal")
            else:
                open_btn.grid_remove()
        for name, btn in buttons.items():
            if name in ("cancel", "open"):
                continue
            # Source stays available anytime — busy scenes cancel-then-switch.
            if name == "source":
                btn.configure(state="normal")
                continue
            btn.configure(state="disabled" if busy else "normal")

    def _set_scene_status(self, scene_number, status: str) -> None:
        widgets = self._scene_row_widgets.get(_scene_key(scene_number))
        if not widgets:
            return
        label, color = _status_display(status)
        widgets["status_label"].configure(text=label, text_color=color)
        time_lbl = widgets.get("time_label")
        if time_lbl is not None:
            time_lbl.configure(text=self._scene_time_label(scene_number))
        key = _scene_key(scene_number)
        self._sync_row_action_buttons(key)
        if status in ("generating", "searching", "retrying", "extracting", "using_alternative", "adding_local"):
            self._scene_started.setdefault(key, time.time())
            self._tick_scene_elapsed(scene_number)
        elif status in ("ready", "needs_action", "failed", "cancelled", "skipped", "timeout"):
            self._scene_started.pop(key, None)
            if widgets.get("elapsed_label") is not None:
                widgets["elapsed_label"].configure(text="")
            err = ""
            result = self._asset_results.get(key)
            if status in ("needs_action", "failed", "timeout") and result is not None:
                msg = short_error(getattr(result, "error", None), 80)
                if msg:
                    err = f"⚠ {msg}"
            if widgets.get("error_label") is not None:
                widgets["error_label"].configure(text=err)
        self._paint_row_highlight(key)

    def _paint_row_highlight(self, key: str) -> None:
        widgets = self._scene_row_widgets.get(key)
        if not widgets or widgets.get("row") is None:
            return
        status = self._qa.busy.get(key) or (
            self._row_status_from_result(widgets["scene"]) if widgets.get("scene") else ""
        )
        if key == self._qa.focused_key:
            widgets["row"].configure(fg_color=_ACCENT_SEL, border_width=1, border_color=_ACCENT_BORDER)
        elif status in ("needs_action", "failed", "timeout"):
            widgets["row"].configure(fg_color=_DANGER_BG, border_width=0)
        else:
            widgets["row"].configure(fg_color=widgets.get("default_fg") or "transparent", border_width=0)

    def _tick_scene_elapsed(self, scene_number) -> None:
        key = _scene_key(scene_number)
        widgets = self._scene_row_widgets.get(key)
        started = self._scene_started.get(key)
        if not widgets or started is None:
            return
        elapsed = int(time.time() - started)
        widgets["elapsed_label"].configure(text=f"{elapsed}s")
        if elapsed >= 720:
            self._timeout_scene(scene_number)
            return
        self.after(1000, lambda n=scene_number: self._tick_scene_elapsed(n))

    def _timeout_scene(self, scene_number) -> None:
        key = _scene_key(scene_number)
        if key not in self._scene_started:
            return
        if self._asset_manager is not None:
            self._asset_manager.request_cancel_scene(str(scene_number))
        self._set_scene_status(scene_number, "timeout")
        self._append_log(
            f"[SCENE {scene_number}] TIMEOUT — waiting for the in-flight job to stop, "
            "then Retry will work again\n"
        )

    def _get_flow_engine_manager(self):
        """Thread-safe lazy singleton — see _flow_engine_manager_lock's comment."""
        if self._flow_engine_manager is not None:
            return self._flow_engine_manager
        with self._flow_engine_manager_lock:
            if self._flow_engine_manager is None:
                from providers.flow.engine_manager import FlowEngineManager

                self._flow_engine_manager = FlowEngineManager(log=print)
            return self._flow_engine_manager

    def _current_image_flow_settings(self) -> dict:
        return {
            "model": self.flow_image_model_var.get(),
            "aspectRatio": self.flow_image_aspect_var.get(),
        }

    # ---------- video profiles ----------
    # A Video Profile bundles the account/browser pool + model/dimension/duration
    # that AI VIDEO scenes use — kept separate from image settings since video is
    # a distinct Flow workflow with its own accounts and options (see
    # providers/flow/provider.py media_kind="video").

    def _get_video_profiles(self) -> list[dict]:
        profiles = self._settings.get("video_profiles")
        if not profiles:
            profiles = [{
                "id": "default",
                "name": "Default",
                "account_ids": [],
                "model": FLOW_VIDEO_MODELS[1][0],
                "aspectRatio": FLOW_IMAGE_ASPECT_RATIOS[0][0],
                "duration": 8,
            }]
            self._settings["video_profiles"] = profiles
        return profiles

    def _default_video_profile(self) -> dict:
        profiles = self._get_video_profiles()
        default_id = self._settings.get("default_video_profile_id")
        for p in profiles:
            if p["id"] == default_id:
                return p
        return profiles[0]

    def _save_video_profiles(self, profiles: list[dict], default_id: str | None = None) -> None:
        self._settings["video_profiles"] = profiles
        if default_id:
            self._settings["default_video_profile_id"] = default_id
        elif "default_video_profile_id" not in self._settings and profiles:
            self._settings["default_video_profile_id"] = profiles[0]["id"]
        save_settings(self._settings)

    def _video_flow_settings(self) -> dict:
        """The default Video Profile's model/dimension/duration, for the GENERATE
        call's `settings` payload."""
        p = self._default_video_profile()
        return {
            "videoModel": p.get("model", FLOW_VIDEO_MODELS[1][0]),
            "aspectRatio": p.get("aspectRatio", FLOW_IMAGE_ASPECT_RATIOS[0][0]),
            "videoDuration": int(p.get("duration", 8)),
        }

    def _video_account_ids(self) -> list[str] | None:
        """The default Video Profile's assigned accounts, or None (= all
        signed-in accounts) if the profile has none assigned yet."""
        ids = self._default_video_profile().get("account_ids") or []
        return ids or None

    def _coverage_map_from_workspace(self) -> dict:
        ws = self._workspace
        if ws is None:
            return {}
        try:
            import json

            raw = json.loads(ws.visual_plan_json_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        alloc = raw.get("allocation") if isinstance(raw, dict) else None
        if not isinstance(alloc, dict):
            return {}
        out = {}
        for p in alloc.get("coverage_plans") or []:
            if not isinstance(p, dict):
                continue
            sid = str(p.get("scene_id", ""))
            key = _scene_key(sid)
            out[key] = p
        return out

    def _persist_global_settings(self) -> None:
        """Machine-level settings.json — same store as Pexels/Gemini keys.
        Used by ResearchView to save the (optional) research engine path."""
        save_settings(self._settings)

    def _build_research_provider(self, ws) -> Optional["ResearchAssetProvider"]:
        """Loads whatever research package already exists for this project
        (written by a prior Manual Research run) as candidate media for the
        asset pipeline. Never raises — a missing/unreadable/stale package
        just means no research candidates this run, exactly as if the
        feature were never used.

        Staleness: a research run performed WITH a script is bound to that
        exact script text (research_media.script_fingerprint) — if the
        current narration no longer matches, the package is treated as
        unavailable rather than silently offering media for a script it was
        never run against. A run performed URL/topic-only (no script at the
        time) has no fingerprint and is property-bound, not script-bound —
        it stays valid even after a script is written later."""
        if ws is None:
            return None
        try:
            from providers.research_asset_provider import ResearchAssetProvider
            from research.package_importer import load_research_result
            from research.settings import is_research_stale, load_project_research_settings

            research_json = ws.research_dir / "research.json"
            if not research_json.is_file():
                return None

            settings = load_project_research_settings(ws)
            if settings.script_fingerprint:
                current_script = ""
                if ws.script_path.is_file():
                    current_script = ws.script_path.read_text(encoding="utf-8")
                if is_research_stale(settings.script_fingerprint, current_script):
                    print("[ASSET] Research package predates the current script — "
                          "run Manual Research again to refresh it.")
                    return None

            # Multi-listing: every researched property is loaded, each
            # candidate still tagged with its own property_id, and the
            # scene->property_id map decides which listing a given scene may
            # draw from (hard filter inside the provider, before ranking).
            from research.library import load_research_library

            library = load_research_library(ws.research_dir)
            if library.has_media():
                return ResearchAssetProvider(
                    library.all_media(),
                    property_scope_by_scene=self._property_scope_from_workspace(),
                )

            result = load_research_result(ws.research_dir)
            if not result.ok or not result.media:
                return None
            return ResearchAssetProvider(
                result.media,
                property_scope_by_scene=self._property_scope_from_workspace(),
            )
        except Exception as exc:  # noqa: BLE001 - research must never block asset generation
            print(f"[ASSET] Research provider unavailable: {exc}")
            return None

    def _property_scope_from_workspace(self) -> dict:
        """scene_number -> property_id, stored beside the plan in
        ai_visual_plan.json (never in the CSV — that schema is unchanged).
        Same sidecar pattern as _coverage_map_from_workspace()."""
        # __dict__ (not getattr): this can run on an app instance built via
        # __new__ in tests, where a missing attribute on a Tk widget recurses
        # through Tk's own __getattr__ and raises RecursionError — which
        # getattr's default does NOT swallow.
        ws = self.__dict__.get("_workspace")
        if ws is None:
            return {}
        try:
            import json

            if not getattr(ws, "visual_plan_json_path", None) or not ws.visual_plan_json_path.is_file():
                return {}
            raw = json.loads(ws.visual_plan_json_path.read_text(encoding="utf-8"))
            scope = raw.get("property_scope") if isinstance(raw, dict) else None
            return {str(k): str(v) for k, v in (scope or {}).items()}
        except Exception:  # noqa: BLE001 - scope is an optimization, never fatal
            return {}

    def _build_asset_manager(self, images_dir: Path, scene_rows: list[SceneRow]) -> AssetManager:
        """Shared by the main pipeline and Regenerate — builds providers needed for
        planned scenes plus Change Source targets (YouTube/Stock/Flow video)."""
        needs_stock = True  # Change Source can pick Stock even when the plan didn't
        # Always available: Skip-replace and Change Source can pick Flow image
        # even when the CSV row is still youtube_video / stock_video.
        needs_flow_image = True
        needs_flow_video = True  # Change Source can switch any scene to AI Video
        needs_youtube = True  # Change Source can switch any scene to YouTube

        stock_provider = None
        if needs_stock:
            pexels_key = self.pexels_key_var.get().strip() or os.environ.get("PEXELS_API_KEY", "")
            pixabay_key = self.pixabay_key_var.get().strip() or os.environ.get("PIXABAY_API_KEY", "")
            from providers.stock.factory import build_stock_provider

            stock_provider = build_stock_provider(
                images_dir,
                pexels_api_key=pexels_key,
                pixabay_api_key=pixabay_key,
                include_openverse=True,
            )
            if stock_provider is None and any(s.wants_stock for s in scene_rows):
                raise RuntimeError(
                    "This project has Stock scenes but no stock API key is set "
                    "(Pexels and/or Pixabay). Add one in Settings."
                )

        flow_image_provider = None
        flow_video_provider = None
        if needs_flow_image or needs_flow_video:
            self._get_flow_engine_manager()
            from providers.flow.provider import FlowProvider

            if needs_flow_image:
                flow_image_provider = FlowProvider(
                    self._flow_engine_manager, media_kind="image",
                    flow_settings=self._current_image_flow_settings(),
                )
            if needs_flow_video:
                # Video scenes always use the default Video Profile's account
                # pool + model/dimension/duration (see §7/§9 — no per-scene
                # profile column, one profile drives every video scene in a run).
                flow_video_provider = FlowProvider(
                    self._flow_engine_manager, media_kind="video",
                    account_ids=self._video_account_ids(),
                    flow_settings=self._video_flow_settings(),
                )

        youtube_provider = None
        try:
            clip_duration = float(self.youtube_clip_duration_var.get().strip() or 3.5)
        except ValueError:
            clip_duration = 3.5
        try:
            search_results = int(self.youtube_search_results_var.get().strip() or 5)
        except ValueError:
            search_results = 5
        try:
            from providers.youtube.base import YouTubeProvider
            from providers.youtube.ytdlp_backend import YtDlpBackend

            youtube_provider = YouTubeProvider(
                YtDlpBackend(),
                max_results=max(1, search_results),
                clip_duration=max(1.0, min(10.0, clip_duration)),
                transcript_matching=self.youtube_transcript_matching_var.get(),
            )
        except RuntimeError as exc:
            if any(s.wants_youtube for s in scene_rows):
                raise RuntimeError(f"This project has youtube_video scenes: {exc}") from exc
            print(f"[ASSET] YouTube provider unavailable for Change Source: {exc}")

        clip_duration = max(1.0, min(10.0, clip_duration))
        archive_provider = None
        nasa_provider = None
        try:
            from providers.archive.provider import ArchiveProvider
            from providers.nasa.provider import NasaProvider

            archive_provider = ArchiveProvider(clip_duration=clip_duration)
            nasa_provider = NasaProvider(clip_duration=clip_duration)
        except Exception as exc:
            needs_doc = any(s.wants_archive or s.wants_nasa for s in scene_rows)
            if needs_doc:
                raise RuntimeError(f"Documentary media providers failed to load: {exc}") from exc
            print(f"[ASSET] Archive/NASA providers unavailable: {exc}")

        return AssetManager(
            images_dir,
            stock_provider=stock_provider,
            flow_image_provider=flow_image_provider,
            flow_video_provider=flow_video_provider,
            youtube_provider=youtube_provider,
            archive_provider=archive_provider,
            nasa_provider=nasa_provider,
            research_provider=self._build_research_provider(self._workspace),
            log=print,
            resolved_style=getattr(self, "_resolved_style", None),
            coverage_by_scene=self._coverage_map_from_workspace(),
            settings=self._settings,
        )

    def _regenerate_scene(self, scene_row: SceneRow) -> None:
        self._scene_action("retry", scene_row)

    def _ensure_asset_manager(self, images_dir: Path) -> AssetManager:
        images_dir.mkdir(parents=True, exist_ok=True)
        mgr = self._asset_manager
        need_rebuild = mgr is None or Path(mgr.images_dir) != images_dir
        if not need_rebuild and mgr is not None:
            # Rebuild once if Change Source targets were missing from an older run.
            if (
                mgr.youtube_provider is None
                or mgr.flow_video_provider is None
                or mgr.archive_provider is None
                or mgr.nasa_provider is None
            ):
                need_rebuild = True
        if need_rebuild:
            self._asset_manager = self._build_asset_manager(images_dir, self._scene_rows)
        self._asset_manager.recovery.skipped |= set(self._hydrated_skipped)
        return self._asset_manager

    def _scene_by_number(self, scene_row: SceneRow) -> SceneRow:
        for row in self._scene_rows:
            if _scene_key(row.scene_number) == _scene_key(scene_row.scene_number):
                return row
        return scene_row

    def _add_local_clip(self, scene_row: SceneRow) -> None:
        scene_row = self._scene_by_number(scene_row)
        key = _scene_key(scene_row.scene_number)
        if key in self._busy_scenes:
            return
        previous = self.status_var.get()
        self.status_var.set("Selecting local media…")
        try:
            picked = filedialog.askopenfilename(
                title=f"Add local clip — Scene {scene_row.scene_number}",
                filetypes=FILE_DIALOG_TYPES,
            )
        except Exception as exc:
            self.status_var.set("Ready")
            messagebox.showerror("Could not add local clip", str(exc))
            return
        if not picked:
            self.status_var.set(previous or "Ready")
            return
        self.status_var.set("Validating…")
        try:
            validate_local_media(picked)
        except ManualClipError as exc:
            self.status_var.set("Ready")
            messagebox.showerror("Could not use this file.", str(exc))
            self._append_log(f"[QA] Could not add local clip for scene {scene_row.scene_number}: {exc}\n")
            return
        if not self._require_workspace("add a local clip"):
            return
        if not self.images_var.get().strip():
            self._sync_images_dir()
        images_dir = self._workspace.assets_dir
        token = self._qa.begin_job(key, "adding_local")
        self._busy_scenes.add(key)
        self._set_scene_status(scene_row.scene_number, "adding_local")
        self._paint_qa_chrome()
        self.status_var.set("Copying asset…")
        threading.Thread(
            target=self._scene_action_worker,
            args=("local_clip", scene_row, images_dir, picked, token),
            daemon=True,
        ).start()

    def _scene_action(self, action: str, scene_row: SceneRow) -> None:
        if not self._require_workspace("retry or change a scene"):
            return
        scene_row = self._scene_by_number(scene_row)
        key = _scene_key(scene_row.scene_number)
        if key in self._busy_scenes:
            return
        if not self.images_var.get().strip():
            self._sync_images_dir()
        images_dir = self._workspace.assets_dir
        kind = {"retry": "retrying", "alternative": "using_alternative", "skip": "generating"}.get(action, "generating")
        token = self._qa.begin_job(key, kind)
        self._busy_scenes.add(key)
        self._set_scene_status(scene_row.scene_number, kind)
        self._paint_qa_chrome()
        threading.Thread(
            target=self._scene_action_worker, args=(action, scene_row, images_dir, None, token), daemon=True
        ).start()

    def _cancel_one_scene(self, scene_row: SceneRow) -> None:
        if self._asset_manager is None:
            return
        key = _scene_key(scene_row.scene_number)
        self._asset_manager.request_cancel_scene(scene_row.scene_number)
        self._qa.begin_job(key, "cancelling")
        self._set_scene_status(scene_row.scene_number, "cancelling")
        self._append_log(f"[SCENE {scene_row.scene_number}] Cancel requested for this scene only\n")
        self._update_details_panel()
        self._paint_qa_chrome()

    def _skip_scene_dialog(self, scene_row: SceneRow) -> None:
        win = ctk.CTkToplevel(self)
        win.title(f"Scene {scene_row.scene_number}")
        win.geometry("360x200")
        win.transient(self)
        ctk.CTkLabel(
            win,
            text=(
                f"Scene {scene_row.scene_number} has no usable clip.\n"
                "Generate a Flow image instead of skipping."
            ),
            justify="left",
        ).pack(padx=16, pady=(16, 12))
        ctk.CTkButton(
            win, text="Generate Flow image", height=32,
            command=lambda: (win.destroy(), self._scene_action_with_source(scene_row, "flow_image")),
        ).pack(fill="x", padx=16, pady=3)
        ctk.CTkButton(
            win, text="Skip (black frame)", height=28,
            fg_color="transparent", border_width=1, border_color=_BORDER,
            command=lambda: (win.destroy(), self._scene_action("skip", scene_row)),
        ).pack(fill="x", padx=16, pady=3)
        ctk.CTkButton(win, text="Cancel", fg_color="transparent", command=win.destroy).pack(pady=8)

    def _apply_scene_source_choice(self, scene_row: SceneRow, provider_name: str) -> SceneRow:
        """Update in-memory scene + Source badge when the user picks a new provider."""
        from providers.router import SceneAssetRouter

        updated = scene_row.as_fallback(provider_name)
        key = _scene_key(updated.scene_number)
        for i, row in enumerate(self._scene_rows):
            if _scene_key(row.scene_number) == key:
                self._scene_rows[i] = updated
                break
        widgets = self._scene_row_widgets.get(key)
        if widgets is not None:
            widgets["scene"] = updated
            badge = widgets.get("badge")
            if badge is not None:
                text, fg, bg = scene_source_badge(updated)
                badge.configure(text=text, text_color=fg, fg_color=bg)
        return updated

    def _maybe_resume_pending_source_change(self, key: str) -> None:
        provider = self._pending_source_after_cancel.pop(key, None)
        if not provider:
            return
        scene = next((s for s in self._scene_rows if _scene_key(s.scene_number) == key), None)
        if scene is None:
            return
        self.after(40, lambda s=scene, p=provider: self._scene_action_with_source(s, p))

    def _change_source_dialog(self, scene_row: SceneRow) -> None:
        scene_row = self._scene_by_number(scene_row)
        options = ["stock_video", "youtube", "flow_video", "flow_image", "stock_image", "local"]
        if self._asset_manager is not None:
            options = self._asset_manager.recovery.change_source_options(scene_row) or options
        if "local" not in options:
            options = list(options) + ["local"]
        busy = _scene_key(scene_row.scene_number) in self._busy_scenes
        win = ctk.CTkToplevel(self)
        win.title(f"Change source — Scene {scene_row.scene_number}")
        win.geometry("300x340")
        win.transient(self)
        title = "Choose a source for this scene only"
        if busy:
            title = "Scene is busy — it will Stop, then switch source"
        ctk.CTkLabel(win, text=title).pack(pady=(12, 8))

        def pick(name: str) -> None:
            win.destroy()
            if name == "local":
                self._add_local_clip(scene_row)
            else:
                self._scene_action_with_source(scene_row, name)

        for name in options:
            label = "Local file…" if name == "local" else name.replace("_", " ").title()
            ctk.CTkButton(
                win, text=label, height=28,
                command=lambda n=name: pick(n),
            ).pack(fill="x", padx=16, pady=3)
        ctk.CTkButton(win, text="Cancel", fg_color="transparent", command=win.destroy).pack(pady=8)

    def _change_source_dialog_bulk(self, scenes: list) -> None:
        if not scenes:
            return
        options = ["stock_video", "youtube", "flow_video", "flow_image", "stock_image", "local"]
        if self._asset_manager is not None:
            opts = self._asset_manager.recovery.change_source_options(scenes[0])
            if opts:
                options = list(opts)
        if "local" not in options:
            options = list(options) + ["local"]
        win = ctk.CTkToplevel(self)
        win.title(f"Change source — {len(scenes)} scenes")
        win.geometry("320x360")
        win.transient(self)
        ctk.CTkLabel(
            win, text=f"Apply one source to {len(scenes)} selected scenes",
        ).pack(pady=(12, 8))

        def apply(name: str) -> None:
            win.destroy()
            if name == "local":
                self._add_local_clip_bulk(scenes)
                return
            if name in ("flow_image", "flow_video") and len(scenes) >= 2:
                self._start_flow_batch(scenes, provider_name=name)
            else:
                for scene in scenes:
                    self._scene_action_with_source(scene, name)

        for name in options:
            label = "Local file…" if name == "local" else name.replace("_", " ").title()
            ctk.CTkButton(
                win, text=label, height=28,
                command=lambda n=name: apply(n),
            ).pack(fill="x", padx=16, pady=3)
        ctk.CTkButton(win, text="Cancel", fg_color="transparent", command=win.destroy).pack(pady=8)

    def _scene_action_with_source(self, scene_row: SceneRow, provider_name: str) -> None:
        if not self._require_workspace("change a scene source"):
            return
        scene_row = self._scene_by_number(scene_row)
        key = _scene_key(scene_row.scene_number)
        if key in self._busy_scenes:
            self._pending_source_after_cancel[key] = provider_name
            self._apply_scene_source_choice(scene_row, provider_name)
            if self._asset_manager is not None:
                self._asset_manager.request_cancel_scene(scene_row.scene_number)
            # Don't bump the job token — wait for the in-flight job to finish,
            # then resume Change Source with the original completion event.
            self._qa.busy[key] = "cancelling"
            self._set_scene_status(scene_row.scene_number, "cancelling")
            self._append_log(
                f"[SCENE {scene_row.scene_number}] Stop then Change source -> {provider_name}\n"
            )
            self._update_details_panel()
            self._paint_qa_chrome()
            return
        scene_row = self._apply_scene_source_choice(scene_row, provider_name)
        if not self.images_var.get().strip():
            self._sync_images_dir()
        images_dir = self._workspace.assets_dir if self._workspace is not None else Path(self.images_var.get().strip())
        self._busy_scenes.add(key)
        token = self._qa.begin_job(key, "generating")
        self._set_scene_status(scene_row.scene_number, "generating")
        self._paint_qa_chrome()
        threading.Thread(
            target=self._scene_action_worker,
            args=("change_source", scene_row, images_dir, provider_name, token),
            daemon=True,
        ).start()

    def _scene_action_worker(self, action: str, scene_row: SceneRow, images_dir: Path, extra, token: int = 0) -> None:
        old_out, old_err = sys.stdout, sys.stderr
        writer = _QueueWriter(self._ui_queue)
        sys.stdout = writer
        sys.stderr = writer
        key = _scene_key(scene_row.scene_number)
        result = None
        try:
            mgr = self._ensure_asset_manager(images_dir)
            if action == "retry":
                result = mgr.retry_scene(scene_row)
            elif action == "alternative":
                result = mgr.alternative_scene(scene_row)
            elif action == "skip":
                result = mgr.skip_scene(scene_row)
            elif action == "change_source":
                result = mgr.change_source(scene_row, str(extra))
            elif action == "local_clip":
                result = mgr.attach_manual_clip(scene_row, Path(str(extra)))
            else:
                result = mgr.regenerate_scene(scene_row)
        except Exception as exc:
            result = AssetResult(
                scene_row.scene_number, None, None,
                SceneAssetRouter.classify(scene_row) or AssetSource.LOCAL,
                SceneStatus.NEEDS_ACTION, error=str(exc),
            )
        finally:
            writer.flush()
            sys.stdout = old_out
            sys.stderr = old_err
            try:
                self._mirror_result_into_workspace(result)
            except Exception:
                pass
            self._ui_queue.put(("scene_result", (scene_row.scene_number, token, result)))

    def _refresh_assets_cta(self) -> None:
        self._refresh_qa_ui(immediate=True)

    def _persist_qa(self, force: bool = False) -> None:
        raw = self.images_var.get().strip()
        if not raw:
            return
        now = time.time()
        if not force and now - self._qa_persist_at < 1.0:
            return
        self._qa_persist_at = now
        save_qa_file(Path(raw), self._qa.attempts, self._skipped_set())
        if self._workspace is not None:
            self._workspace.sync_state_copies()

    def _refresh_qa_ui(self, immediate: bool = False) -> None:
        self._qa_ui_dirty = True
        if immediate:
            self._flush_qa_ui()
            return
        if self._qa_ui_scheduled:
            return
        self._qa_ui_scheduled = True
        delay = self._QA_UI_RUNNING_MS if self._running else self._QA_UI_IDLE_MS
        self.after(delay, self._flush_qa_ui)

    def _flush_qa_ui(self) -> None:
        self._qa_ui_scheduled = False
        if not self._qa_ui_dirty:
            return
        self._qa_ui_dirty = False
        snap = self._qa_snapshot()
        self._qa.prune_selection([_scene_key(s.scene_number) for s in self._scene_rows])
        self._qa.clear_focus_if_resolved(snap.unresolved_keys)
        self._sync_scene_statuses_from_results()
        self._paint_qa_chrome(snap)
        # Rebuilding hundreds of issue cards mid-run freezes Windows — defer until idle.
        if self._issues_visible and not self._running:
            self._rebuild_issues(snap)
        self._update_details_panel(snap)
        self._persist_qa()
        self._update_project_indicator()
        self._sync_primary_cta(snap)
        if snap.total == 0:
            self.prod_ready_var.set("")
            self.prod_processing_var.set("")
            self.prod_queued_var.set("")
            self.prod_needs_var.set("")
            self.prod_mix_var.set("")
            self.prod_error_var.set("")
            return
        self.prod_ready_var.set(f"{snap.ready} / {snap.total} READY")
        self.prod_processing_var.set(f"{snap.processing} PROCESSING" if snap.processing else "")
        self.prod_queued_var.set(f"{snap.waiting} QUEUED" if snap.waiting else "")
        self.prod_needs_var.set(f"{snap.needs_action} NEEDS ACTION" if snap.needs_action else "")
        self.prod_mix_var.set(self._scene_source_mix_label())
        self.prod_error_var.set(
            f"⚠ {snap.needs_action} scene(s) need attention" if snap.needs_action else ""
        )
        if snap.total:
            self.progress.set(snap.progress)
            if self._running:
                self.status_var.set(snap.header)

    def _scene_source_mix_label(self) -> str:
        """Counts by resolved source (post-generate when available), one label per provider."""
        from collections import Counter

        from providers.router import SceneAssetRouter

        counts: Counter[str] = Counter()
        for scene in self._scene_rows:
            key = _scene_key(scene.scene_number)
            result = self._asset_results.get(key)
            source = getattr(result, "source", None) if result is not None else None
            if source is None:
                source = SceneAssetRouter.classify(scene)
            label = self._source_mix_bucket(source)
            counts[label] += 1
        order = (
            "AI Image",
            "AI Video",
            "Stock",
            "YouTube",
            "Archive",
            "NASA",
            "Commons",
            "Manual",
            "Unassigned",
        )
        extras = [name for name in counts if name not in order]
        return " · ".join(
            f"{name} {counts[name]}"
            for name in (*order, *sorted(extras))
            if counts.get(name)
        )

    @staticmethod
    def _source_mix_bucket(source: AssetSource | None) -> str:
        if source is None:
            return "Unassigned"
        if source == AssetSource.FLOW_IMAGE:
            return "AI Image"
        if source == AssetSource.FLOW_VIDEO:
            return "AI Video"
        if source in (AssetSource.STOCK, AssetSource.STOCK_IMAGE, AssetSource.STOCK_VIDEO):
            return "Stock"
        if source == AssetSource.YOUTUBE_VIDEO:
            return "YouTube"
        if source == AssetSource.ARCHIVE_VIDEO:
            return "Archive"
        if source == AssetSource.NASA_VIDEO:
            return "NASA"
        if source in (AssetSource.COMMONS_VIDEO, AssetSource.COMMONS_IMAGE):
            return "Commons"
        if source in (AssetSource.MANUAL, AssetSource.LOCAL):
            return "Manual"
        badge = SOURCE_BADGE.get(source)
        if badge:
            return badge[0]
        return str(getattr(source, "value", source)).replace("_", " ").title()

    def _paint_qa_chrome(self, snap=None) -> None:
        snap = snap or self._qa_snapshot()
        if snap.total:
            parts = [f"{snap.total} scene{'s' if snap.total != 1 else ''}", f"{snap.ready} ready"]
            if snap.needs_action:
                parts.append(f"{snap.needs_action} need attention")
            elif snap.processing:
                parts.append(f"{snap.processing} processing")
            mix = self._scene_source_mix_label()
            if mix:
                parts.append(mix)
            if getattr(snap, "visual_summary", ""):
                parts.append(snap.visual_summary)
            self.scenes_summary_var.set(" · ".join(parts))
        else:
            self.scenes_summary_var.set("")
        self.qa_health_var.set(snap.health_label)
        n = snap.needs_action
        if n:
            self.qa_counter_var.set(f"Issues {n}")
            self.issues_toggle_btn.configure(text_color=_DANGER, border_color=_DANGER)
            # Pack Issues before Close instances (or settings) when shell topbar is active.
            anchor = (
                getattr(self, "_close_instances_btn", None)
                or getattr(self, "_settings_btn", None)
            )
            pack_kw = {"side": "left", "padx": (0, 6)}
            if anchor is not None:
                pack_kw["before"] = anchor
            self.issues_toggle_btn.pack(**pack_kw)
            nav = getattr(self, "_error_nav", None)
            if nav is not None:
                nav.grid()
        else:
            self.qa_counter_var.set("")
            self.issues_toggle_btn.pack_forget()
            self._issues_visible = False
            self._issues_drawer.grid_remove()
            nav = getattr(self, "_error_nav", None)
            if nav is not None:
                nav.grid_remove()
        self.goto_error_btn.configure(
            text="Go to Error" if n else snap.go_to_error_label,
            state="normal" if n else "disabled",
        )
        nav_state = "normal" if n else "disabled"
        self.prev_error_btn.configure(state=nav_state)
        self.next_error_btn.configure(state=nav_state)
        self.error_pos_var.set(self._qa.error_position(snap.unresolved_keys))
        n = snap.needs_action
        bulk = "normal" if n else "disabled"
        self.retry_failed_btn.configure(text=f"RETRY {n}" if n else "RETRY", state=bulk)
        self.alt_failed_btn.configure(text=f"ALTERNATIVES {n}" if n else "ALTERNATIVES", state=bulk)
        self.skip_failed_btn.configure(text=f"SKIP {n}" if n else "SKIP", state=bulk)
        sel = len(self._qa.selected_failed)
        sel_state = "normal" if sel else "disabled"
        self.retry_selected_btn.configure(state=sel_state)
        self.alt_selected_btn.configure(state=sel_state)
        self.skip_selected_btn.configure(state=sel_state)
        self.issues_header_var.set(f"NEEDS ATTENTION — {n}")
        for key, widgets in self._scene_row_widgets.items():
            self._paint_row_highlight(key)
            check = widgets.get("check")
            if check is not None:
                check.configure(state="normal")
                if widgets.get("check_var") is not None:
                    widgets["check_var"].set(key in self._qa.selected_failed)
            self._sync_row_action_buttons(key)
        self._sync_header_select_all(snap)

    def _rebuild_issues(self, snap=None) -> None:
        snap = snap or self._qa_snapshot()
        for child in self._issues_list.winfo_children():
            child.destroy()
        if not snap.issues:
            ctk.CTkLabel(
                self._issues_list, text="No unresolved scenes.", text_color=_MUTED, font=ctk.CTkFont(size=11),
            ).pack(anchor="w", padx=4, pady=4)
            return
        for issue in snap.issues:
            card = ctk.CTkFrame(self._issues_list, fg_color="transparent")
            card.pack(fill="x", pady=2)
            btn = ctk.CTkButton(
                card,
                text=f"Scene {issue.scene_number}\n{issue.provider} — {issue.error}",
                anchor="w", height=40, fg_color="transparent", border_width=0,
                text_color=_TEXT, hover_color=_DANGER_BG, font=ctk.CTkFont(size=11),
                command=lambda k=issue.key: self._focus_scene(k, scroll=True),
            )
            btn.pack(fill="x")

            # A low QA score on a generated still is a judgement call, not a
            # defect: regenerating uses the same prompt, so it may well come
            # back scored the same. Offer the choice instead of acting.
            if getattr(issue, "needs_decision", False):
                row = ctk.CTkFrame(card, fg_color="transparent")
                row.pack(fill="x", padx=(8, 0))
                score = getattr(issue, "score", 0.0)
                ctk.CTkLabel(
                    row, text=f"Low score {score:.2f} — keep this asset or regenerate?",
                    text_color=_MUTED, font=ctk.CTkFont(size=10), anchor="w",
                ).pack(side="left")
                ctk.CTkButton(
                    row, text="Retry", width=58, height=22,
                    fg_color=_BORDER, hover_color=_ACCENT, text_color=_TEXT,
                    font=ctk.CTkFont(size=10),
                    command=lambda k=issue.key: self._on_qa_decision(k, "retry"),
                ).pack(side="right", padx=(6, 0))
                ctk.CTkButton(
                    row, text="Keep", width=58, height=22,
                    fg_color=_BORDER, hover_color=_ACCENT, text_color=_TEXT,
                    font=ctk.CTkFont(size=10),
                    command=lambda k=issue.key: self._on_qa_decision(k, "keep"),
                ).pack(side="right")

    def _on_qa_decision(self, scene_key: str, decision: str) -> None:
        """Operator's answer to a low QA score on a generated still.

        Keep  -> accept the asset as-is and stop listing it as an issue.
        Retry -> the existing per-scene retry path, unchanged.
        """
        row = next(
            (r for r in (self._scene_rows or []) if _scene_key(r.scene_number) == scene_key),
            None,
        )
        if row is None:
            return
        if decision == "retry":
            self._scene_action("retry", row)
            return
        # Keep: mark the QA verdict as accepted by the operator so the scene
        # stops appearing in Issues. The asset and its score are untouched.
        result = (self._asset_results or {}).get(scene_key)
        meta = getattr(result, "metadata", None)
        if isinstance(meta, dict) and isinstance(meta.get("visual_qa"), dict):
            meta["visual_qa"]["operator_accepted"] = True
            meta["visual_qa"]["status"] = "PASS"
        self._refresh_qa_ui()

    def _update_details_panel(self, snap=None) -> None:
        snap = snap or self._qa_snapshot()
        selected = self._selected_scenes()
        panel = getattr(self, "_details_panel", None)
        self._ensure_details_in_inspector()
        if not selected:
            self.details_title_var.set("Selected scene")
            self.details_text_var.set("Select a scene in Visual Plan to inspect assets and editorial cues.")
            if getattr(self, "details_open_btn", None) is not None:
                self._set_inspector_button(self.details_open_btn, show=False)
            return

        if len(selected) > 1:
            self.details_title_var.set(f"{len(selected)} scenes selected")
            by_source: dict[str, int] = {}
            failed_n = 0
            busy_n = 0
            for scene in selected:
                key = _scene_key(scene.scene_number)
                status = snap.statuses.get(key, self._row_status_from_result(scene))
                if status in ("needs_action", "failed", "timeout"):
                    failed_n += 1
                if key in self._busy_scenes or key in self._qa.busy:
                    busy_n += 1
                src = SceneAssetRouter.classify(scene) or AssetSource.LOCAL
                label = SOURCE_BADGE.get(src, ("Local", _MUTED, "transparent"))[0]
                by_source[label] = by_source.get(label, 0) + 1
            lines = [
                f"Scenes    {', '.join(str(s.scene_number) for s in selected)}",
                f"Sources   " + ", ".join(f"{k} {v}" for k, v in by_source.items()),
            ]
            if failed_n:
                lines.append(f"Need help {failed_n}")
            if busy_n:
                lines.append(f"Busy      {busy_n}")
            lines.append("Actions apply to every checked scene.")
            self.details_text_var.set("\n".join(lines))
            any_failed = failed_n > 0
            any_busy = busy_n > 0
            self._set_inspector_button(self.details_source_btn, show=True, state="normal")
            self._set_inspector_button(self.details_local_btn, show=True, state="normal")
            self._set_inspector_button(self.details_open_btn, show=False)
            self._set_inspector_button(
                self.details_retry_btn, show=True,
                state="normal" if any_failed and not any_busy else "disabled",
            )
            self._set_inspector_button(
                self.details_alt_btn, show=True,
                state="normal" if any_failed and not any_busy else "disabled",
            )
            self._set_inspector_button(
                self.details_skip_btn, show=True,
                state="normal" if any_failed and not any_busy else "disabled",
            )
            self._set_inspector_button(
                self.details_stop_btn, show=any_busy,
                state="normal" if any_busy else "disabled",
            )
            return

        scene = selected[0]
        key = _scene_key(scene.scene_number)
        self.details_title_var.set(f"Selected scene · #{scene.scene_number}")
        status = snap.statuses.get(key, self._row_status_from_result(scene))
        tracker = self._asset_manager.recovery if self._asset_manager is not None else None
        info = self._qa.details(scene, self._asset_results.get(key), status, tracker)
        lines = [
            info["title"],
            f"Status    {info['status']}",
            f"Provider  {info['provider']}",
        ]
        time_txt = self._scene_time_label(scene.scene_number)
        if time_txt and time_txt != "—":
            lines.append(f"Time      {time_txt}")
        if info["search"]:
            lines.append(f"Search    {info['search']}")
        if info["error"]:
            lines.append(f"Error     {info['error']}")
        lines.append(f"Attempt   {info['attempt']}")
        if info["duration"]:
            lines.append(f"Duration  {info['duration']}")
        if info["fallback"]:
            lines.append(f"Fallback  {info['fallback']}")
        narr = (scene.script_segment or "").strip()
        if narr:
            lines.append(f"Narration {narr[:160]}{'…' if len(narr) > 160 else ''}")
        prompt = (scene.prompt or scene.stock or scene.visual_description or "").strip()
        if prompt:
            lines.append(f"Visual    {prompt[:160]}{'…' if len(prompt) > 160 else ''}")
        ed = self._editorial_scene_lookup(scene.scene_number)
        if ed:
            lines.append("— Editorial —")
            lines.append(f"Camera    {ed.get('camera_style') or '—'}")
            lines.append(f"Transition {ed.get('transition_in') or 'cut'}")
            lines.append(f"Ambience  {ed.get('ambience_profile') or '—'}")
            if ed.get("sfx_events"):
                lines.append(f"SFX       {len(ed.get('sfx_events') or [])} events")
            elif ed.get("allow_silence"):
                lines.append("SFX       (allow silence)")
            att = ed.get("attention_score")
            if att is not None:
                lines.append(f"Attention {float(att):.2f}")
            purpose = ed.get("purpose")
            if purpose:
                lines.append(f"Purpose   {purpose}")
        self.details_text_var.set("\n".join(lines))
        actions = set(info["actions"])
        busy = key in self._busy_scenes or key in self._qa.busy
        failed = status in ("needs_action", "failed", "timeout")
        can_open = status in ("ready", "success") and self._scene_asset_path(scene.scene_number) is not None
        self._set_inspector_button(self.details_source_btn, show=True, state="normal")
        self._set_inspector_button(
            self.details_local_btn, show=True,
            state="normal" if not busy else "disabled",
        )
        self._set_inspector_button(
            self.details_open_btn, show=can_open,
            state="normal" if can_open and not busy else "disabled",
        )
        self._set_inspector_button(
            self.details_retry_btn, show=failed,
            state="normal" if "retry" in actions and not busy else "disabled",
        )
        self._set_inspector_button(
            self.details_alt_btn, show=failed,
            state="normal" if "alternative" in actions and not busy else "disabled",
        )
        self._set_inspector_button(
            self.details_skip_btn, show=failed,
            state="normal" if "skip" in actions and not busy else "disabled",
        )
        self._set_inspector_button(
            self.details_stop_btn, show=busy,
            state="normal" if busy or "cancel" in actions else "disabled",
        )

    def _focus_scene(self, key: str, scroll: bool = True) -> None:
        self._qa.focused_key = key
        if scroll:
            self._scroll_scene_into_view(key)
        self._paint_qa_chrome()
        self._update_details_panel()

    def _scroll_scene_into_view(self, key: str) -> None:
        canvas = getattr(self._scenes_list, "_parent_canvas", None)
        total = len(self._scene_rows)
        idx = next(
            (i for i, s in enumerate(self._scene_rows) if _scene_key(s.scene_number) == key),
            None,
        )
        if idx is not None and _scene_list.should_window(total) and canvas is not None:
            # Jump by index so off-window rows get materialized first.
            frac = min(1.0, max(0.0, idx / max(total, 1)))
            try:
                canvas.yview_moveto(frac)
            except Exception:
                pass
            self._refresh_scene_window(force=True)
        widgets = self._scene_row_widgets.get(key)
        if not widgets or widgets.get("row") is None:
            return
        row = widgets["row"]
        self._scenes_list.update_idletasks()
        if canvas is None:
            return
        inner_h = max(int(self._scenes_list.winfo_reqheight()), 1)
        canvas_h = max(int(canvas.winfo_height()), 1)
        y = int(row.winfo_y())
        frac = min(1.0, max(0.0, y / max(inner_h - canvas_h, 1)))
        canvas.yview_moveto(frac)

    def _go_to_error(self) -> None:
        snap = self._qa_snapshot()
        key = self._qa.go_to_error(snap.unresolved_keys)
        if key:
            self._focus_scene(key, scroll=True)

    def _next_error(self) -> None:
        snap = self._qa_snapshot()
        key = self._qa.next_error(snap.unresolved_keys)
        if key:
            self._focus_scene(key, scroll=True)

    def _prev_error(self) -> None:
        snap = self._qa_snapshot()
        key = self._qa.prev_error(snap.unresolved_keys)
        if key:
            self._focus_scene(key, scroll=True)

    def _details_action(self, action: str) -> None:
        scenes = self._selected_scenes()
        if not scenes:
            return
        if action == "change_source":
            self._change_source_for_focused()
            return
        if action == "open":
            self._open_scene_asset(scenes[0].scene_number)
            return
        if len(scenes) > 1:
            if action in ("retry", "alternative", "skip"):
                self._bulk_recovery(action, selected_only=True)
                return
            if action == "cancel":
                for scene in scenes:
                    key = _scene_key(scene.scene_number)
                    if key in self._busy_scenes or key in self._qa.busy:
                        self._cancel_one_scene(scene)
                return
            if action == "local_clip":
                self._add_local_clip_bulk(scenes)
                return
        scene = scenes[0]
        if action == "cancel":
            self._cancel_one_scene(scene)
            return
        if action == "skip":
            self._skip_scene_dialog(scene)
            return
        if action == "local_clip":
            self._add_local_clip(scene)
            return
        self._scene_action(action, scene)

    def _add_local_clip_bulk(self, scenes: list) -> None:
        if not scenes:
            return
        previous = self.status_var.get()
        self.status_var.set("Selecting local media…")
        try:
            picked = filedialog.askopenfilename(
                title=f"Add local clip — {len(scenes)} scenes",
                filetypes=FILE_DIALOG_TYPES,
            )
        except Exception as exc:
            self.status_var.set("Ready")
            messagebox.showerror("Could not add local clip", str(exc))
            return
        if not picked:
            self.status_var.set(previous or "Ready")
            return
        try:
            validate_local_media(picked)
        except ManualClipError as exc:
            self.status_var.set("Ready")
            messagebox.showerror("Could not use this file.", str(exc))
            return
        if not self._require_workspace("add a local clip"):
            return
        if not self.images_var.get().strip():
            self._sync_images_dir()
        images_dir = self._workspace.assets_dir
        self.status_var.set("Copying asset…")
        for scene_row in scenes:
            scene_row = self._scene_by_number(scene_row)
            key = _scene_key(scene_row.scene_number)
            if key in self._busy_scenes:
                continue
            token = self._qa.begin_job(key, "adding_local")
            self._busy_scenes.add(key)
            self._set_scene_status(scene_row.scene_number, "adding_local")
            threading.Thread(
                target=self._scene_action_worker,
                args=("local_clip", scene_row, images_dir, picked, token),
                daemon=True,
            ).start()
        self._paint_qa_chrome()
        self._update_details_panel()

    def _on_scene_check(self, key: str, var) -> None:
        if var.get():
            self._qa.selected_failed.add(key)
        else:
            self._qa.selected_failed.discard(key)
        self._focus_scene(key, scroll=False)
        self._paint_qa_chrome()

    def _on_failed_check(self, key: str, var) -> None:
        self._on_scene_check(key, var)

    def _visible_scene_keys(self, snap=None) -> list:
        """Keys for scene rows currently shown after the search filter."""
        snap = snap or self._qa_snapshot()
        keys = []
        for scene in self._scene_rows:
            key = _scene_key(scene.scene_number)
            if key not in self._scene_row_widgets:
                continue
            if self._qa.scene_matches(
                scene, snap.statuses.get(key, ""), self._asset_results.get(key),
            ):
                keys.append(key)
        return keys

    def _sync_header_select_all(self, snap=None) -> None:
        var = getattr(self, "_scene_header_check_var", None)
        if var is None:
            return
        visible = self._visible_scene_keys(snap)
        if not visible:
            var.set(False)
            return
        var.set(all(k in self._qa.selected_failed for k in visible))

    def _on_header_select_all(self) -> None:
        visible = self._visible_scene_keys()
        if getattr(self, "_scene_header_check_var", None) is not None and self._scene_header_check_var.get():
            self._qa.selected_failed.update(visible)
        else:
            for key in visible:
                self._qa.selected_failed.discard(key)
        for key, widgets in self._scene_row_widgets.items():
            if widgets.get("check_var") is not None:
                widgets["check_var"].set(key in self._qa.selected_failed)
        self._paint_qa_chrome()
        self._update_details_panel()

    def _select_all_failed(self) -> None:
        self._qa.select_all_failed(self._qa_snapshot().unresolved_keys)
        for key, widgets in self._scene_row_widgets.items():
            if widgets.get("check_var") is not None:
                widgets["check_var"].set(key in self._qa.selected_failed)
        self._paint_qa_chrome()
        self._update_details_panel()

    def _clear_failed_selection(self) -> None:
        self._qa.clear_selection()
        for widgets in self._scene_row_widgets.values():
            if widgets.get("check_var") is not None:
                widgets["check_var"].set(False)
        self._paint_qa_chrome()
        self._update_details_panel()

    def _apply_scene_filter(self) -> None:
        """Search UI removed — keep all rows visible and sync select-all."""
        self._qa.filter_query = ""
        for widgets in self._scene_row_widgets.values():
            row = widgets.get("row")
            if row is not None:
                row.grid()
        self._sync_header_select_all()

    def _clear_visual_plan(self) -> None:
        """Undo an import/analyze: clear the scene queue so the user can start over."""
        if self._running:
            messagebox.showinfo(
                "Clear plan",
                "Wait for generation to finish before clearing the plan.",
            )
            return
        if not self._scene_rows and not self.csv_var.get().strip() and self._visual_plan is None:
            messagebox.showinfo("Clear plan", "There is no scene plan to clear.")
            return
        if not messagebox.askyesno(
            "Clear plan",
            "Remove the current scene list so you can paste or import again?\n\n"
            "Your project folder and any downloaded assets are kept. "
            "Past narration text (if any) stays in the script box.",
        ):
            return
        self._visual_plan = None
        self._manual_csv_backup = ""
        self.csv_var.set("")
        self._scene_rows = []
        self._asset_results.clear()
        self._busy_scenes.clear()
        self._pending_source_after_cancel.clear()
        self._hydrated_skipped.clear()
        self._qa = SceneQAState()
        self._qa.filter_query = ""
        self._selected_scene_key = None
        ws = self._workspace
        if ws is not None:
            for path in (ws.csv_path, ws.visual_plan_json_path):
                try:
                    if path.is_file():
                        path.unlink()
                except OSError:
                    pass
        self._sync_export_csv_link()
        self._render_scene_rows()
        self._refresh_assets_cta()
        self._sync_primary_cta()
        self._append_log("Cleared visual plan — paste a script or import a CSV to continue.\n")

    def _bulk_recovery(self, action: str, selected_only: bool) -> None:
        snap = self._qa_snapshot()
        keys = self._qa.targets(snap.unresolved_keys, selected_only=selected_only)
        if not keys:
            messagebox.showinfo("Recovery", "No unresolved scenes in this selection.")
            return
        by_key = {_scene_key(s.scene_number): s for s in self._scene_rows}
        scenes = [by_key[k] for k in keys if k in by_key]
        if action == "skip":
            ok = messagebox.askokcancel(
                "Skip failed scenes",
                f"Skip {len(scenes)} unresolved scene(s)?\n\n"
                "Skipped scenes may result in missing visuals in the final video.\n"
                "Ready scenes are not touched.",
            )
            if not ok:
                return
        if action == "alternative":
            if not self._confirm_alternatives(scenes):
                return
        self._recovery_queue = []
        seen = set()
        for scene in scenes:
            key = _scene_key(scene.scene_number)
            result = self._asset_results.get(key)
            if result is not None and getattr(result, "ok", False):
                continue
            if key in seen:
                continue
            seen.add(key)
            self._recovery_queue.append((action, scene))
        self._recovery_total = len(self._recovery_queue)
        self._recovery_done = 0
        self._append_log(f"\n[QA] {action} {self._recovery_total} unresolved scene(s) — ready scenes untouched\n")
        self._set_qa_bulk_progress(f"RECOVERING FAILED SCENES  0 / {self._recovery_total}")
        if not self._retry_pumping:
            self._retry_pumping = True
            self._pump_retry_queue()

    def _confirm_alternatives(self, scenes: list[SceneRow]) -> bool:
        tracker = SceneRecoveryTracker()
        if self._asset_manager is not None:
            tracker = self._asset_manager.recovery
        previews = preview_alternatives(scenes, tracker)
        counts = summarize_alternative_preview(previews)
        lines = [f"{len(scenes)} scenes selected"] + [f"{v} → {k}" for k, v in counts.items()]
        return bool(messagebox.askokcancel(
            "Alternative Recovery",
            "\n".join(lines) + "\n\nAPPLY ALTERNATIVES uses each scene's existing fallback path.\nReady scenes are not touched.",
        ))

    # ---------- settings ----------

    def _open_settings(self) -> None:
        win = ctk.CTkToplevel(self)
        win.title("Settings")
        win.geometry("480x600")
        win.minsize(420, 320)
        win.configure(fg_color=_BG)
        win.grab_set()

        # Everything lives inside one scrollable body so content can never get
        # squeezed invisible by a fixed window height (confirmed bug: with a plain
        # pack() directly on `win`, the last widget — Add Account — was silently
        # compressed to ~1px when content exceeded the window's fixed size). A
        # scrollable outer frame makes this correct regardless of content length,
        # font size, or OS display scaling.
        body = ctk.CTkScrollableFrame(
            win, fg_color=_BG, scrollbar_button_color=_BORDER, scrollbar_button_hover_color=_ACCENT,
        )
        body.pack(fill="both", expand=True)

        if self._auth_required():
            ctk.CTkLabel(
                body, text="ACCOUNT", font=ctk.CTkFont(size=11, weight="bold"), text_color=_MUTED,
            ).pack(anchor="w", padx=20, pady=(20, 4))
            ctk.CTkLabel(
                body,
                text=self._auth_identity_label(),
                font=ctk.CTkFont(size=13),
                text_color=_TEXT,
            ).pack(anchor="w", padx=20, pady=(0, 8))

            def do_sign_out():
                try:
                    win.destroy()
                except Exception:
                    pass
                self._sign_out()

            ctk.CTkButton(
                body, text="Sign out", height=32, fg_color="transparent",
                hover_color=_DANGER_BG, text_color=_DANGER, border_width=1, border_color=_DANGER,
                command=do_sign_out,
            ).pack(anchor="w", padx=20, pady=(0, 16))

        ctk.CTkLabel(
            body, text="STOCK PROVIDERS", font=ctk.CTkFont(size=11, weight="bold"), text_color=_MUTED,
        ).pack(anchor="w", padx=20, pady=(20, 4))
        ctk.CTkLabel(
            body, text="Pexels — primary stock source for stock_image / stock_video scenes.",
            font=ctk.CTkFont(size=12), text_color=_TEXT,
        ).pack(anchor="w", padx=20)
        ctk.CTkEntry(
            body, textvariable=self.pexels_key_var, show="•", height=34,
            placeholder_text="Pexels API key", fg_color=_BG, border_color=_BORDER, text_color=_TEXT,
        ).pack(fill="x", padx=20, pady=(8, 4))

        pexels_status_var = ctk.StringVar(
            value="Configured" if self.pexels_key_var.get().strip() else "Not configured"
        )
        ctk.CTkLabel(body, textvariable=pexels_status_var, font=ctk.CTkFont(size=12), text_color=_MUTED).pack(
            anchor="w", padx=20
        )

        ctk.CTkLabel(
            body, text="Pixabay — secondary stock source (used when Pexels misses).",
            font=ctk.CTkFont(size=12), text_color=_TEXT,
        ).pack(anchor="w", padx=20, pady=(12, 0))
        ctk.CTkEntry(
            body, textvariable=self.pixabay_key_var, show="•", height=34,
            placeholder_text="Pixabay API key", fg_color=_BG, border_color=_BORDER, text_color=_TEXT,
        ).pack(fill="x", padx=20, pady=(8, 4))

        pixabay_status_var = ctk.StringVar(
            value="Configured" if self.pixabay_key_var.get().strip() else "Not configured"
        )
        ctk.CTkLabel(body, textvariable=pixabay_status_var, font=ctk.CTkFont(size=12), text_color=_MUTED).pack(
            anchor="w", padx=20
        )
        ctk.CTkLabel(
            body,
            text="Openverse (no key) is also searched for stock images when stock providers run.",
            font=ctk.CTkFont(size=11), text_color=_MUTED, wraplength=410, justify="left",
        ).pack(anchor="w", padx=20, pady=(4, 0))

        def save_key():
            self._settings["pexels_api_key"] = self.pexels_key_var.get().strip()
            self._settings["pixabay_api_key"] = self.pixabay_key_var.get().strip()
            save_settings(self._settings)
            pexels_status_var.set("Configured" if self.pexels_key_var.get().strip() else "Not configured")
            pixabay_status_var.set("Configured" if self.pixabay_key_var.get().strip() else "Not configured")
            messagebox.showinfo("Saved", "Stock API keys saved.")

        ctk.CTkButton(
            body, text="Save Stock Keys", height=32, fg_color=_ACCENT, hover_color=_ACCENT_HOV,
            text_color=_ACCENT_DARK, command=save_key,
        ).pack(anchor="w", padx=20, pady=(0, 12))

        ctk.CTkLabel(
            body, text="AI SCRIPT (GEMINI)", font=ctk.CTkFont(size=11, weight="bold"), text_color=_MUTED,
        ).pack(anchor="w", padx=20, pady=(8, 4))
        ctk.CTkLabel(
            body,
            text="Gemini 3.6 Flash plans visuals from a pasted narration. "
                 "You can also set GEMINI_API_KEY.",
            font=ctk.CTkFont(size=12), text_color=_TEXT, wraplength=410, justify="left",
        ).pack(anchor="w", padx=20)
        ctk.CTkEntry(
            body, textvariable=self.gemini_key_var, show="•", height=34,
            placeholder_text="Gemini API key", fg_color=_BG, border_color=_BORDER, text_color=_TEXT,
        ).pack(fill="x", padx=20, pady=(8, 4))

        def save_gemini():
            self._settings["gemini_api_key"] = self.gemini_key_var.get().strip()
            save_settings(self._settings)
            self._refresh_gemini_status()
            messagebox.showinfo("Saved", "Gemini API key saved.")

        ctk.CTkButton(
            body, text="Save Gemini Key", height=32, fg_color=_ACCENT, hover_color=_ACCENT_HOV,
            text_color=_ACCENT_DARK, command=save_gemini,
        ).pack(anchor="w", padx=20, pady=(0, 16))

        ctk.CTkLabel(
            body, text="OUTPUT", font=ctk.CTkFont(size=11, weight="bold"), text_color=_MUTED,
        ).pack(anchor="w", padx=20, pady=(8, 4))
        out_row = ctk.CTkFrame(body, fg_color="transparent")
        out_row.pack(fill="x", padx=20, pady=(0, 8))
        ctk.CTkLabel(out_row, text="Whisper", font=ctk.CTkFont(size=12), text_color=_TEXT).pack(side="left")
        ctk.CTkOptionMenu(
            out_row, variable=self.model_var,
            values=["tiny", "base", "small", "medium", "large-v3"],
            width=130, fg_color=_BG, button_color=_BORDER, button_hover_color=_ACCENT,
            text_color=_TEXT, dropdown_fg_color=_CARD, dropdown_text_color=_TEXT,
        ).pack(side="left", padx=10)

        ctk.CTkSwitch(
            body, text="Ken Burns zoom", variable=self.zoom_var,
            onvalue=True, offvalue=False, progress_color=_ACCENT, button_color=_TEXT,
            text_color=_TEXT, font=ctk.CTkFont(size=12),
        ).pack(anchor="w", padx=20, pady=2)
        ctk.CTkSwitch(
            body, text="Captions", variable=self.captions_var,
            onvalue=True, offvalue=False, progress_color=_ACCENT, button_color=_TEXT,
            text_color=_TEXT, font=ctk.CTkFont(size=12),
        ).pack(anchor="w", padx=20, pady=(2, 8))
        ctk.CTkLabel(
            body,
            text="Smart Editing controls (Text / SFX / Transitions / Ambience) live on the Audio dashboard.",
            font=ctk.CTkFont(size=11), text_color=_MUTED, wraplength=410, justify="left",
        ).pack(anchor="w", padx=20, pady=(0, 12))

        ctk.CTkFrame(body, fg_color=_BORDER, height=1).pack(fill="x", padx=20)

        # ── Flow Settings — Image + Video (exact options flow-engine supports) ──
        ctk.CTkLabel(
            body, text="FLOW SETTINGS", font=ctk.CTkFont(size=11, weight="bold"), text_color=_MUTED,
        ).pack(anchor="w", padx=20, pady=(16, 8))

        def _option_row(parent, label_text, var, options, on_change=None):
            """options: list[(value, label)]. The OptionMenu shows/edits labels;
            `var` (the real backing StringVar, e.g. holding "NARWHAL") is updated
            via `command` whenever the user picks a different label. Optional
            `on_change` runs after the value is set (used to auto-persist)."""
            row = ctk.CTkFrame(parent, fg_color="transparent")
            row.pack(fill="x", pady=3)
            ctk.CTkLabel(
                row, text=label_text, font=ctk.CTkFont(size=12), text_color=_TEXT, width=110, anchor="w",
            ).pack(side="left")
            labels = [label for _, label in options]
            current_label = next((lbl for val, lbl in options if val == var.get()), labels[0])
            display = ctk.StringVar(value=current_label)

            def on_choice(chosen, o=options, v=var, cb=on_change):
                v.set(next((val for val, lbl in o if lbl == chosen), o[0][0]))
                if cb is not None:
                    cb()

            ctk.CTkOptionMenu(
                row, variable=display, values=labels, command=on_choice,
                width=200, fg_color=_BG, button_color=_BORDER, button_hover_color=_ACCENT,
                text_color=_TEXT, dropdown_fg_color=_CARD, dropdown_text_color=_TEXT,
            ).pack(side="left")

        image_card = ctk.CTkFrame(body, fg_color=_CARD, corner_radius=6, border_width=1, border_color=_BORDER)
        image_card.pack(fill="x", padx=20, pady=(0, 8))
        ctk.CTkLabel(
            image_card, text="Image", font=ctk.CTkFont(size=11, weight="bold"), text_color=_TEXT,
        ).pack(anchor="w", padx=12, pady=(10, 2))

        def persist_image_flow_settings(silent=True):
            self._settings["flow_settings"] = self._current_image_flow_settings()
            save_settings(self._settings)
            if not silent:
                messagebox.showinfo(
                    "Saved",
                    "Flow image settings saved. They apply to newly generated scenes.",
                )

        _option_row(
            image_card, "Model", self.flow_image_model_var, FLOW_IMAGE_MODELS,
            on_change=persist_image_flow_settings,
        )
        _option_row(
            image_card, "Dimension", self.flow_image_aspect_var, FLOW_IMAGE_ASPECT_RATIOS,
            on_change=persist_image_flow_settings,
        )
        ctk.CTkFrame(image_card, fg_color="transparent", height=6).pack()
        ctk.CTkLabel(
            body,
            text="Image model & dimension save automatically when you change them.",
            font=ctk.CTkFont(size=11), text_color=_MUTED,
        ).pack(anchor="w", padx=20, pady=(0, 16))

        ctk.CTkFrame(body, fg_color=_BORDER, height=1).pack(fill="x", padx=20)

        ctk.CTkLabel(
            body, text="AI / FLOW ACCOUNTS", font=ctk.CTkFont(size=11, weight="bold"), text_color=_MUTED,
        ).pack(anchor="w", padx=20, pady=(16, 4))
        ctk.CTkLabel(
            body,
            text="Used for scenes with an AI prompt. Each account gets its own browser "
                 "profile. Chrome count matches prompts (1 for a single scene); batches "
                 "of 15+ prompts split across all signed-in accounts.",
            font=ctk.CTkFont(size=11), text_color=_MUTED, wraplength=410, justify="left",
        ).pack(anchor="w", padx=20)

        # Plain (non-scrolling) frame — it sits inside `body`, which already scrolls;
        # nesting a second CTkScrollableFrame here causes unreliable mouse-wheel/
        # sizing behavior in CustomTkinter, so account rows just stack naturally.
        accounts_list = ctk.CTkFrame(body, fg_color=_CARD)
        accounts_list.pack(fill="x", padx=20, pady=(8, 8))
        status_var = ctk.StringVar(value="Not connected")
        ctk.CTkLabel(body, textvariable=status_var, font=ctk.CTkFont(size=11), text_color=_MUTED).pack(
            anchor="w", padx=20
        )

        WORKER_DOT = {
            "idle": "#64748B", "ready": "#16A34A", "preparing": "#D97706",
            "running": "#2563EB", "waiting": "#2563EB", "done": "#16A34A",
            "login": "#D97706", "checking": "#D97706", "error": "#DC2626",
        }

        # Rebuild video-profile cards only when the set of account IDs changes —
        # every Flow STATE ping used to destroy Model/Duration dropdowns and
        # snap Fast↔Lite back to the last saved value mid-edit.
        _profiles_account_ids: list | None = [None]

        def render_accounts(accounts):
            # The FlowClient STATE subscription below outlives this window (it's
            # only torn down on <Destroy>, and a message can already be in
            # flight via self.after() when the user closes Settings) — without
            # this guard, redrawing into a destroyed CTkToplevel's widgets
            # raises "bad window path name".
            if not win.winfo_exists():
                return
            self._known_flow_accounts = accounts
            account_ids = tuple(a.get("id") for a in accounts)
            if account_ids != _profiles_account_ids[0]:
                _profiles_account_ids[0] = account_ids
                render_profiles()
            for c in accounts_list.winfo_children():
                c.destroy()
            if not accounts:
                ctk.CTkLabel(
                    accounts_list, text="No accounts yet — click \"+ Add Google Account\" below.",
                    text_color=_MUTED, font=ctk.CTkFont(size=11),
                ).pack(anchor="w", padx=8, pady=8)
                return
            for a in accounts:
                row = ctk.CTkFrame(accounts_list, fg_color="transparent")
                row.pack(fill="x", pady=3, padx=4)

                signed_in = bool(a.get("authenticated"))
                progress = a.get("progress") or {}
                worker_status = str(progress.get("status") or ("idle" if signed_in else "login")).lower()
                dot_color = WORKER_DOT.get(worker_status, _MUTED)
                scene_hint = ""
                idx = progress.get("index")
                if idx is not None and worker_status in ("running", "waiting"):
                    scene_hint = f"  ·  scene {int(idx) + 1:03d}"

                ctk.CTkLabel(row, text="●", text_color=dot_color, font=ctk.CTkFont(size=13)).pack(
                    side="left", padx=(4, 4)
                )
                label = a.get("label", "?")
                detail = progress.get("message") or ("Signed in" if signed_in else "Not signed in")
                ctk.CTkLabel(
                    row, text=f"{label}", font=ctk.CTkFont(size=12, weight="bold"), text_color=_TEXT, anchor="w",
                ).pack(side="left")
                ctk.CTkLabel(
                    row, text=f"  {detail}{scene_hint}", font=ctk.CTkFont(size=11), text_color=_MUTED, anchor="w",
                ).pack(side="left", fill="x", expand=True)

                ctk.CTkButton(
                    row, text="Remove", width=64, height=22, font=ctk.CTkFont(size=10),
                    fg_color="transparent", border_width=1, border_color=_BORDER,
                    text_color=_DANGER, hover_color=_DANGER_BG,
                    command=lambda aid=a["id"]: connect_and(lambda c: c.delete_account(aid)),
                ).pack(side="right", padx=(4, 4))
                if not signed_in:
                    ctk.CTkButton(
                        row, text="Sign in", width=70, height=22, font=ctk.CTkFont(size=10),
                        fg_color=_ACCENT, hover_color=_ACCENT_HOV, text_color=_ACCENT_DARK,
                        command=lambda aid=a["id"]: connect_and(lambda c: c.login(aid)),
                    ).pack(side="right", padx=4)

        _state_unsubscribers: list = []
        _state_subscribed = [False]

        def _on_settings_closed(event):
            if event.widget is not win:
                return  # <Destroy> also fires for every child widget; only act once
            for unsub in _state_unsubscribers:
                try:
                    unsub()
                except Exception:
                    pass
            _state_unsubscribers.clear()
            _state_subscribed[0] = False

        win.bind("<Destroy>", _on_settings_closed)

        def connect_and(fn):
            def worker():
                try:
                    client = self._get_flow_engine_manager().ensure_running()
                    fn(client)

                    # One STATE subscription per Settings window. Adding another on
                    # every Sign in / Add Account used to redraw the panel N times
                    # per engine ping (and wipe unsaved model picks).
                    if not _state_subscribed[0]:
                        def on_state(msg):
                            if msg.get("type") == "STATE":
                                accounts = msg.get("accounts", [])
                                self.after(
                                    0,
                                    lambda a=accounts: (
                                        status_var.set("Connected"),
                                        render_accounts(a),
                                    ),
                                )

                        _state_unsubscribers.append(client.subscribe(on_state))
                        _state_subscribed[0] = True

                    state = client.get_state()
                    self.after(
                        0,
                        lambda: (
                            status_var.set("Connected"),
                            render_accounts(state.get("accounts", [])),
                        ),
                    )
                except Exception as exc:
                    # Capture the message as a plain string now — `exc` itself is
                    # auto-deleted by Python when this except block exits, so the
                    # lambda below (which runs later, via self.after) would otherwise
                    # raise NameError instead of showing the real error.
                    error_msg = str(exc)
                    self.after(0, lambda m=error_msg: status_var.set(f"Error: {m}"))

            threading.Thread(target=worker, daemon=True).start()

        btn_row = ctk.CTkFrame(body, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=(0, 20))
        ctk.CTkButton(
            btn_row, text="+ Add Google Account", height=32, fg_color=_ACCENT, hover_color=_ACCENT_HOV,
            text_color=_ACCENT_DARK,
            command=lambda: connect_and(
                lambda c: c.add_account(f"Account {len(c.get_state().get('accounts', [])) + 1}")
            ),
        ).pack(side="left")
        ctk.CTkButton(
            btn_row, text="Close instances", height=32, width=130,
            fg_color="transparent", border_width=1, border_color=_BORDER,
            text_color=_TEXT, hover_color=_CARD_HOVER,
            command=self._close_flow_instances,
        ).pack(side="left", padx=(8, 0))

        ctk.CTkFrame(body, fg_color=_BORDER, height=1).pack(fill="x", padx=20)

        # ── Flow Video Profiles — each bundles its own account pool + model/
        # dimension/duration, since video is a separate Flow workflow from image
        # (see providers/flow/provider.py, media_kind="video") and every video
        # scene in a run uses the one selected/default profile (§7/§9). ──────────
        ctk.CTkLabel(
            body, text="FLOW VIDEO PROFILES", font=ctk.CTkFont(size=11, weight="bold"), text_color=_MUTED,
        ).pack(anchor="w", padx=20, pady=(16, 4))
        ctk.CTkLabel(
            body,
            text="Used for scenes with a video prompt. Each profile has its own "
                 "accounts, model, dimension, and duration — the default profile "
                 "drives every AI VIDEO scene in a run.",
            font=ctk.CTkFont(size=11), text_color=_MUTED, wraplength=410, justify="left",
        ).pack(anchor="w", padx=20)

        profiles_list = ctk.CTkFrame(body, fg_color="transparent")
        profiles_list.pack(fill="x", padx=20, pady=(8, 4))

        def set_default_profile(pid):
            self._settings["default_video_profile_id"] = pid
            save_settings(self._settings)
            render_profiles()

        def delete_profile(pid):
            profs = [p for p in self._get_video_profiles() if p["id"] != pid]
            if not profs:
                return
            if self._settings.get("default_video_profile_id") == pid:
                self._settings["default_video_profile_id"] = profs[0]["id"]
            self._save_video_profiles(profs)
            render_profiles()

        def save_profile(pid, name_var, model_var, aspect_var, duration_var, *, silent=False):
            for p in self._get_video_profiles():
                if p["id"] == pid:
                    p["name"] = name_var.get().strip() or p["name"]
                    p["model"] = model_var.get()
                    p["aspectRatio"] = aspect_var.get()
                    try:
                        p["duration"] = int(duration_var.get())
                    except (TypeError, ValueError):
                        p["duration"] = int(p.get("duration", 8))
            self._save_video_profiles(self._get_video_profiles())
            if not silent:
                messagebox.showinfo("Saved", "Video profile saved.")

        def toggle_account(pid, aid, var):
            for p in self._get_video_profiles():
                if p["id"] == pid:
                    ids = set(p.get("account_ids") or [])
                    ids.add(aid) if var.get() else ids.discard(aid)
                    p["account_ids"] = sorted(ids)
            self._save_video_profiles(self._get_video_profiles())

        def render_profiles():
            if not win.winfo_exists():
                return
            for c in profiles_list.winfo_children():
                c.destroy()
            profiles = self._get_video_profiles()
            default_id = self._settings.get("default_video_profile_id") or profiles[0]["id"]

            for profile in profiles:
                card = ctk.CTkFrame(profiles_list, fg_color=_CARD, corner_radius=6, border_width=1, border_color=_BORDER)
                card.pack(fill="x", pady=(0, 8))

                header = ctk.CTkFrame(card, fg_color="transparent")
                header.pack(fill="x", padx=12, pady=(10, 2))
                name_var = ctk.StringVar(value=profile.get("name", "Profile"))
                ctk.CTkEntry(
                    header, textvariable=name_var, height=26, width=140,
                    fg_color=_BG, border_color=_BORDER, text_color=_TEXT,
                ).pack(side="left")
                is_default = profile["id"] == default_id
                if is_default:
                    ctk.CTkLabel(
                        header, text="Default", font=ctk.CTkFont(size=10, weight="bold"), text_color=_ACCENT,
                    ).pack(side="left", padx=8)
                else:
                    ctk.CTkButton(
                        header, text="Set Default", width=90, height=24, font=ctk.CTkFont(size=10),
                        fg_color="transparent", border_width=1, border_color=_BORDER, text_color=_TEXT,
                        hover_color=_ACCENT_SEL, command=lambda pid=profile["id"]: set_default_profile(pid),
                    ).pack(side="left", padx=8)
                if len(profiles) > 1:
                    ctk.CTkButton(
                        header, text="Delete", width=64, height=24, font=ctk.CTkFont(size=10),
                        fg_color="transparent", border_width=1, border_color=_BORDER,
                        text_color=_DANGER, hover_color=_DANGER_BG,
                        command=lambda pid=profile["id"]: delete_profile(pid),
                    ).pack(side="right")

                model_var = ctk.StringVar(value=profile.get("model", FLOW_VIDEO_MODELS[1][0]))
                aspect_var = ctk.StringVar(value=profile.get("aspectRatio", FLOW_IMAGE_ASPECT_RATIOS[0][0]))
                duration_var = ctk.StringVar(value=str(profile.get("duration", 8)))

                def _autosave_profile(
                    pid=profile["id"], nv=name_var, mv=model_var, av=aspect_var, dv=duration_var,
                ):
                    save_profile(pid, nv, mv, av, dv, silent=True)

                _option_row(card, "Model", model_var, FLOW_VIDEO_MODELS, on_change=_autosave_profile)
                _option_row(card, "Dimension", aspect_var, FLOW_IMAGE_ASPECT_RATIOS, on_change=_autosave_profile)
                _option_row(
                    card, "Duration", duration_var,
                    [(str(v), lbl) for v, lbl in FLOW_VIDEO_DURATIONS],
                    on_change=_autosave_profile,
                )

                ctk.CTkLabel(
                    card, text="Accounts", font=ctk.CTkFont(size=11, weight="bold"), text_color=_TEXT,
                ).pack(anchor="w", padx=12, pady=(8, 2))
                assigned = set(profile.get("account_ids") or [])
                if not self._known_flow_accounts:
                    ctk.CTkLabel(
                        card, text="No accounts yet — add one above.",
                        font=ctk.CTkFont(size=11), text_color=_MUTED,
                    ).pack(anchor="w", padx=12, pady=(0, 8))
                else:
                    for acc in self._known_flow_accounts:
                        cb_var = ctk.BooleanVar(value=acc["id"] in assigned)
                        ctk.CTkCheckBox(
                            card, text=acc.get("label", "?"), variable=cb_var,
                            command=lambda pid=profile["id"], aid=acc["id"], v=cb_var: toggle_account(pid, aid, v),
                            font=ctk.CTkFont(size=11), text_color=_TEXT,
                            fg_color=_ACCENT, hover_color=_ACCENT_HOV, border_color=_BORDER,
                        ).pack(anchor="w", padx=12, pady=1)

                ctk.CTkLabel(
                    card,
                    text="Model / dimension / duration save when changed. Use Save Profile for the name.",
                    font=ctk.CTkFont(size=10), text_color=_MUTED,
                ).pack(anchor="w", padx=12, pady=(6, 0))
                ctk.CTkButton(
                    card, text="Save Profile", height=28, font=ctk.CTkFont(size=11),
                    fg_color=_ACCENT, hover_color=_ACCENT_HOV, text_color=_ACCENT_DARK,
                    command=lambda pid=profile["id"], nv=name_var, mv=model_var, av=aspect_var, dv=duration_var: (
                        save_profile(pid, nv, mv, av, dv)
                    ),
                ).pack(anchor="w", padx=12, pady=(8, 10))

        def add_profile():
            import uuid as _uuid

            profs = self._get_video_profiles()
            profs.append({
                "id": _uuid.uuid4().hex[:8],
                "name": f"Profile {len(profs) + 1}",
                "account_ids": [],
                "model": FLOW_VIDEO_MODELS[1][0],
                "aspectRatio": FLOW_IMAGE_ASPECT_RATIOS[0][0],
                "duration": 8,
            })
            self._save_video_profiles(profs)
            render_profiles()

        ctk.CTkButton(
            body, text="+ Add Video Profile", height=32, fg_color=_ACCENT, hover_color=_ACCENT_HOV,
            text_color=_ACCENT_DARK, command=add_profile,
        ).pack(anchor="w", padx=20, pady=(0, 20))

        render_profiles()

        # Auto-connect on open (best-effort — a missing Node/engine just shows the
        # status line below rather than an alarming popup, since most users opening
        # Settings just want to check/add a Pexels key and haven't touched Flow yet).
        connect_and(lambda c: None)

    # ---------- validation ----------

    def _validate(self, *, require_audio: bool = True) -> tuple[dict | None, str | None]:
        if self._workspace is None:
            return None, (
                "Create a New Project first.\n\n"
                "Each video is stored in its own folder under Downloads/Semantic YT Studio."
            )
        if ensure_ffmpeg_on_path() is None:
            return None, (
                "ffmpeg was not found.\n\n"
                "For development: put a binary at bin/ffmpeg (Mac) or "
                "bin/ffmpeg.exe (Windows), or install ffmpeg on your PATH.\n"
                "Packaged builds should already include ffmpeg — if you see "
                "this message, the install is incomplete."
            )

        csv_path = Path(self.csv_var.get().strip())
        audio_raw = self.audio_var.get().strip()
        audio_path = Path(audio_raw) if audio_raw else self._workspace.audio_path
        images_dir = Path(self.images_var.get().strip())
        self._workspace.ensure_dirs()
        self.images_var.set(str(self._workspace.assets_dir))
        images_dir = self._workspace.assets_dir
        output_path = self._workspace.next_final_path()
        self.output_var.set(str(output_path))
        bg_raw = self.bg_var.get().strip()
        bg_path = Path(bg_raw) if bg_raw else None

        if not self.csv_var.get().strip():
            if self._script_mode_is_ai():
                return None, (
                    "Analyze Script first so Gemini can create a visual plan.\n\n"
                    "Then review the scene table and click Generate Assets."
                )
            return None, "Please choose a script CSV file."
        if not csv_path.is_file():
            return None, f"Script CSV not found:\n{csv_path}"
        if not path_is_inside(csv_path, self._workspace.root):
            csv_path = self._workspace.copy_csv_in(csv_path)
            self.csv_var.set(str(csv_path))

        if require_audio:
            if not audio_raw:
                return None, (
                    "Import a voiceover audio file before Render Video.\n\n"
                    "You can Generate Assets before adding voiceover."
                )
            if not audio_path.is_file():
                return None, (
                    f"Voiceover audio not found:\n{audio_path}\n\n"
                    "Choose an audio file under Voiceover Audio.\n"
                    "Generate Assets does not need voiceover yet."
                )
            if not path_is_inside(audio_path, self._workspace.root):
                dest = self._workspace.audio_dir / audio_path.name
                self._workspace.ensure_dirs()
                if dest.resolve() != audio_path.resolve():
                    shutil.copy2(audio_path, dest)
                audio_path = dest
                self._set_active_voiceover(audio_path, source="imported")
            else:
                # Keep the locked active voiceover in sync with what we render.
                try:
                    self._workspace.set_active_voiceover(audio_path, source="imported")
                except OSError:
                    pass
                self._refresh_voiceover_active_label()
        else:
            # Assets-only: keep a project-owned destination path.
            # Whisper is not used in this mode.
            if not audio_raw:
                audio_path = self._workspace.audio_path
                self.audio_var.set(str(audio_path))
            elif audio_path.is_file() and not path_is_inside(audio_path, self._workspace.root):
                dest = self._workspace.audio_dir / audio_path.name
                self._workspace.ensure_dirs()
                if dest.resolve() != audio_path.resolve():
                    shutil.copy2(audio_path, dest)
                audio_path = dest
                self._set_active_voiceover(audio_path, source="imported")

        # Images/ is internal/automatic (see _sync_images_dir) — just make sure it
        # exists rather than asking the user to pick it.
        if not self.images_var.get().strip():
            self._sync_images_dir()
            images_dir = Path(self.images_var.get().strip())
        images_dir.mkdir(parents=True, exist_ok=True)

        if not self.output_var.get().strip():
            return None, "Please choose where to save the output MP4."
        if output_path.suffix.lower() != ".mp4":
            output_path = output_path.with_suffix(".mp4")
        writable_err = _output_not_writable_reason(output_path)
        if writable_err:
            return None, writable_err

        if bg_path is not None and not bg_path.is_file():
            return None, f"Background music not found:\n{bg_path}"

        try:
            with open(csv_path, newline="", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                if not reader.fieldnames:
                    return None, "CSV has no header row."
                missing_cols = [c for c in ("scene_number", "script_segment") if c not in reader.fieldnames]
                if missing_cols:
                    return None, (
                        "CSV is missing required column(s):\n"
                        + ", ".join(missing_cols)
                        + "\n\nExpected: scene_number, script_segment"
                    )
                rows = list(reader)
        except Exception as exc:
            return None, f"Could not read CSV:\n{exc}"

        if not rows:
            return None, "CSV has no data rows."

        empty_scenes = [
            i + 2 for i, r in enumerate(rows)
            if not str(r.get("scene_number", "")).strip()
            or not str(r.get("script_segment", "")).strip()
        ]
        if empty_scenes:
            preview = ", ".join(str(n) for n in empty_scenes[:8])
            more = "…" if len(empty_scenes) > 8 else ""
            return None, (
                "CSV has empty scene_number or script_segment on row(s): "
                f"{preview}{more}"
            )

        # Fail before transcription: route every scene (AI / stock / manual) and make
        # sure it's actually resolvable — either it has a prompt/stock query (resolved
        # during the run, before rendering) or an existing local file.
        n_scenes = len(rows)
        scene_rows = [SceneRow.from_csv_row(r) for r in rows]

        has_subfolders = any(
            p.is_dir() and not p.name.startswith(".")
            for p in images_dir.iterdir()
        )
        if not has_subfolders:
            routing_errors = SceneAssetRouter.validate(scene_rows, images_dir)
            if routing_errors:
                preview = "\n".join(f"  {e}" for e in routing_errors[:10])
                more = f"\n  …and {len(routing_errors) - 10} more" if len(routing_errors) > 10 else ""
                return None, "Some scene(s) can't be resolved:\n\n" + preview + more

        if any(s.wants_stock for s in scene_rows):
            key = self.pexels_key_var.get().strip() or os.environ.get("PEXELS_API_KEY", "")
            if not key:
                return None, (
                    "This CSV has scene(s) using 'stock' keywords, but no Pexels API "
                    "key is set.\n\nAdd one in Settings (⚙) before generating."
                )

        return {
            "csv_path": csv_path,
            "audio_path": audio_path,
            "images_dir": images_dir,
            "output_path": output_path,
            "bg_path": bg_path,
            "rows": rows,
            "model": self.model_var.get().strip() or "small",
            "captions": bool(self.captions_var.get()),
            "zoom": bool(self.zoom_var.get()),
            "smart_editing": self._smart_editing_settings(),
        }, None

    # ---------- generate ----------

    def _on_generate(self) -> None:
        if self._running:
            self._on_cancel()
            return

        # Revoke / password-change must bite before Generate Assets or Render,
        # even if the app has been open since before access was removed.
        ok, err = self._revalidate_license()
        if not ok:
            self._force_logout(err or "Access revoked or password changed")
            return

        snap = self._qa_snapshot() if self._scene_rows else None
        audio_ok = bool(self.audio_var.get().strip()) and Path(self.audio_var.get().strip()).is_file()
        # Match the CTA: Generate Assets stops after visuals; Render Video continues.
        mode = "render" if (snap is not None and snap.allow_render and audio_ok) else "assets"

        config, err = self._validate(require_audio=(mode == "render"))
        if err:
            messagebox.showerror("Cannot start", err)
            return

        # Only NON-Flow-image QA failures can stop a render. Flow stills are
        # regenerated assets: their QA is advisory and still fully reported
        # (visual_fail / visual_issues / the VQA summary all still count them),
        # but they must never halt production behind a modal prompt.
        if mode == "render" and snap is not None and getattr(snap, "visual_fail_blocking", 0) > 0:
            if not messagebox.askyesno(
                "Visual QA",
                f"{snap.visual_fail} scene(s) failed visual QA.\n"
                f"{snap.visual_weak} weak.\n\nRender anyway?",
            ):
                return

        self._running = True
        self.generate_btn.configure(
            state="normal",
            text="Stop",
            fg_color="transparent",
            hover_color=_DANGER_BG,
            text_color=_DANGER,
            border_width=1,
            border_color=_DANGER,
        )
        self.cancel_btn.grid_forget()
        self.progress.set(0)
        if mode == "assets":
            self.status_var.set("Generating assets…")
        else:
            self.status_var.set("Rendering…")
        self.stage_var.set("GENERATING")
        self._clear_log()
        self._append_log(
            "Starting asset generation…\n"
            if mode == "assets"
            else "Starting render pipeline…\n"
        )
        # Hide stale preview from a previous run
        self._preview_panel.grid_forget()
        self._right_panel.grid_rowconfigure(4, weight=0)

        self._worker = threading.Thread(
            target=self._run_pipeline,
            args=(config, mode),
            daemon=True,
        )
        self._worker.start()

    def _on_cancel(self) -> None:
        """Cancels the asset-resolution phase (AI/stock scenes not yet started, plus
        signals the in-flight Flow batch to stop). Whisper transcription and FFmpeg
        rendering are not interruptible — see the pre-existing pipeline, unchanged."""
        if not self._running:
            return
        self.generate_btn.configure(state="disabled", text="Stopping…")
        if self._asset_manager is not None:
            self._asset_manager.request_cancel()
            self._append_log("\n[ASSET] Stop requested — finishing in-flight work, skipping the rest…\n")
        else:
            self._append_log(
                "\n[ASSET] Stop requested, but nothing cancellable is running yet "
                "(Whisper/render can't be interrupted).\n"
            )

    def _run_pipeline(self, config: dict, mode: str = "render") -> None:
        old_out, old_err = sys.stdout, sys.stderr
        writer = _QueueWriter(self._ui_queue)
        sys.stdout = writer  # type: ignore[assignment]
        sys.stderr = writer  # type: ignore[assignment]

        # video_generator writes ._render_clips / concat_list.txt relative to cwd.
        # Packaged .app bundles are read-only — use a temp work dir instead.
        for key in ("csv_path", "audio_path", "images_dir", "output_path"):
            config[key] = Path(config[key]).resolve()
        if config["bg_path"] is not None:
            config["bg_path"] = Path(config["bg_path"]).resolve()

        work_dir = Path(
            tempfile.mkdtemp(
                prefix=f"videogen_{self._workspace.project_id}_" if self._workspace else "videogen_",
                dir=str(self._workspace.tmp_dir) if self._workspace is not None else None,
            )
        )
        old_cwd = os.getcwd()

        try:
            os.chdir(work_dir)
            print(f"CSV:    {config['csv_path']}")
            print(f"Audio:  {config['audio_path']}")
            print(
                f"[AUDIO] Video pipeline locked to voiceover: "
                f"{Path(config['audio_path']).name}"
            )
            print(f"Images: {config['images_dir']}")
            print(f"Output: {config['output_path']}")
            if config["bg_path"]:
                print(f"BG:     {config['bg_path']}")
            print(f"Model:  {config['model']}")
            print(f"Zoom:     {'ON' if config['zoom'] else 'OFF'}")
            print(f"Captions: {'ON' if config['captions'] else 'OFF'}")
            smart_cfg: SmartEditingSettings = config.get("smart_editing") or SmartEditingSettings()
            print(
                f"Smart Editing: text={'ON' if smart_cfg.text_effects else 'OFF'} "
                f"sfx={'ON' if smart_cfg.sound_effects else 'OFF'} "
                f"transitions={'ON' if smart_cfg.visual_transitions else 'OFF'} "
                f"ambience={'ON' if smart_cfg.scene_ambience else 'OFF'} "
                f"(text={smart_cfg.text_intensity()}/sfx={smart_cfg.sfx_intensity()}/"
                f"transitions={smart_cfg.transitions_intensity()}/"
                f"ambience={smart_cfg.ambience_intensity()}, {smart_cfg.mode})"
            )
            print(f"Work:   {work_dir}")
            print("")

            scene_rows = [SceneRow.from_csv_row(r) for r in config["rows"]]
            if getattr(self, "_visual_plan", None) is not None:
                scene_rows = self._visual_plan.to_scene_rows()
            if any(s.wants_flow or s.wants_stock or s.wants_youtube for s in scene_rows):
                print("[ASSET] Resolving scene assets (AI / stock / manual)...")
                self._asset_manager = self._build_asset_manager(config["images_dir"], scene_rows)
                from asset_manager import ResolveSummary
                from providers.base import AssetError
                from providers.router import SceneAssetRouter

                # Do NOT enqueue scene_busy for every row up front — that floods the
                # UI thread (especially Windows) and looks like a system hang. Rows
                # flip to busy only when work actually starts via on_scene_start.
                # Restart Generate: keep READY scenes with files on disk; only resolve
                # missing / failed / cancelled scenes.
                pre_resolved: dict = {}
                rows_to_resolve: list[SceneRow] = []
                for scene in scene_rows:
                    key = _scene_key(scene.scene_number)
                    existing = self._asset_results.get(key)
                    path = getattr(existing, "path", None) if existing is not None else None
                    if (
                        existing is not None
                        and getattr(existing, "ok", False)
                        and path is not None
                        and Path(path).is_file()
                    ):
                        pre_resolved[str(scene.scene_number)] = existing
                        print(
                            f"[ASSET] Scene {scene.scene_number} -> already ready "
                            f"(reusing {Path(path).name})"
                        )
                        continue
                    # Manifest/disk cache (covers app restart with empty in-memory results).
                    source = SceneAssetRouter.classify(scene) or AssetSource.LOCAL
                    cached = self._asset_manager._cache_hit(scene, source)
                    if cached is not None:
                        pre_resolved[str(scene.scene_number)] = cached
                        self._asset_results[key] = cached
                        print(
                            f"[ASSET] Scene {scene.scene_number} -> {source.value.upper()} "
                            f"(cached, reusing {cached.path.name})"
                        )
                        continue
                    rows_to_resolve.append(scene)

                pending_count = len(rows_to_resolve)
                if pending_count:
                    print(
                        f"[ASSET] {pending_count} scene(s) to resolve "
                        f"({len(pre_resolved)} already ready, skipped)…"
                    )
                    self._ui_queue.put(("assets_status", None))
                elif pre_resolved:
                    print(f"[ASSET] All {len(pre_resolved)} scene(s) already ready — nothing to resolve.")

                def _on_scene_start(scene: SceneRow, source: AssetSource) -> None:
                    # Flow batches report "start" the moment the WHOLE batch is
                    # queued, not when this specific scene gets a worker — with
                    # a handful of accounts and hundreds of scenes, a scene near
                    # the back of the queue can wait well past the 12-minute
                    # watchdog before it ever runs. Mark it QUEUED (no timer)
                    # here; _on_scene_generating flips it to the real busy state
                    # (and starts the watchdog) only once Flow confirms this
                    # scene actually began generating.
                    if source in (AssetSource.FLOW_IMAGE, AssetSource.FLOW_VIDEO):
                        self._ui_queue.put(("scene_busy", (scene.scene_number, "waiting")))
                    else:
                        self._ui_queue.put(
                            ("scene_busy", (scene.scene_number, _scene_busy_kind(source)))
                        )

                def _on_scene_generating(scene: SceneRow) -> None:
                    self._ui_queue.put(("scene_busy", (scene.scene_number, "generating")))

                def _on_scene_complete(scene: SceneRow, result: AssetResult) -> None:
                    # File copies on the worker — never on the Tk UI thread.
                    try:
                        self._mirror_result_into_workspace(result, sync_state=False)
                    except Exception:
                        pass
                    self._ui_queue.put(("scene_asset", (scene.scene_number, result)))

                try:
                    if rows_to_resolve:
                        summary = self._asset_manager.resolve_all(
                            rows_to_resolve,
                            on_scene_start=_on_scene_start,
                            on_scene_complete=_on_scene_complete,
                            on_scene_generating=_on_scene_generating,
                        )
                    else:
                        summary = ResolveSummary(results={}, warnings=[])
                    summary.results.update(pre_resolved)
                except AssetError as exc:
                    raise RuntimeError(exc.reason) from exc
                try:
                    if self._workspace is not None:
                        self._workspace.sync_state_copies()
                except Exception:
                    pass
                for number, result in summary.results.items():
                    key = _scene_key(number)
                    self._asset_results[key] = result
                    if result.ok:
                        print(f"[ASSET] Scene {number} SUCCESS")
                    elif getattr(result.status, "value", "") == "skipped":
                        print(f"[ASSET] Scene {number} SKIPPED")
                    else:
                        print(f"[SCENE {number}] Needs action: {result.error}")
                skipped = set(self._asset_manager.recovery.skipped)
                stats = summarize_assets(
                    [s.scene_number for s in scene_rows], self._asset_results, skipped
                )
                print(f"[ASSET] {stats['ready']}/{stats['total']} scenes ready.")
                if not stats["allow_render"]:
                    self._ui_queue.put(("assets_partial", stats))
                    return
                if mode == "assets":
                    self._ui_queue.put(("assets_complete", stats))
                    return
                print("")
            elif mode == "assets":
                # No remote providers — local/manual assets already on disk.
                self._ui_queue.put(("assets_complete", {"ready": len(scene_rows), "total": len(scene_rows)}))
                return

            vg.arrange_images(config["images_dir"])
            vg.validate_prerequisites(
                config["rows"],
                config["images_dir"],
                str(config["audio_path"]),
                bg_audio=str(config["bg_path"]) if config["bg_path"] else None,
            )
            whisper_words = None
            state_dir = self._workspace.state_dir if self._workspace is not None else None
            if smart_cfg.enabled() and state_dir is not None:
                cached = get_cached_whisper_words(state_dir, config["audio_path"])
                if cached:
                    whisper_words = [(w, float(s), float(e)) for w, s, e in cached]
                    print("[SMART] Reusing cached word alignment.")
            if whisper_words is None:
                whisper_words = vg.transcribe_audio(
                    str(config["audio_path"]),
                    config["model"],
                )
            aligned, audio_end = vg.align_rows(config["rows"], whisper_words)

            visual_plan = getattr(self, "_visual_plan", None)
            resolved_style = self._resolve_project_style(
                script=self.script_box.get("1.0", "end").strip() if hasattr(self, "script_box") else "",
                visual_plan=visual_plan,
                rows=config["rows"],
                persist=True,
            )
            style_fp = resolved_style.fingerprint() if resolved_style is not None else None
            editorial_settings_key = editorial_cache_settings_key(
                config["rows"],
                visual_plan_dict=visual_plan.to_dict() if visual_plan is not None else None,
                style_fingerprint=style_fp,
            )
            audio_key = _audio_fingerprint(config["audio_path"])
            editorial_plan = None
            if state_dir is not None:
                editorial_plan = load_cached_plan(
                    state_dir,
                    audio_key=audio_key,
                    settings_key=editorial_settings_key,
                )
            if editorial_plan is None:
                editorial_plan = build_editorial_plan(
                    config["rows"],
                    aligned,
                    audio_end,
                    visual_plan=visual_plan,
                    settings_key=editorial_settings_key,
                    audio_key=audio_key,
                    resolved_style=resolved_style,
                    # Resolved assets carry the measured length of the delivered
                    # file, so the editor plans from the real source rather than
                    # assuming the configured duration was honoured.
                    asset_results=self._asset_results,
                )
                if state_dir is not None:
                    save_editorial_plan(state_dir, editorial_plan)
                    print(f"[EDITORIAL] Saved plan for {len(editorial_plan.scenes)} scene(s).")
            else:
                print(f"[EDITORIAL] Reusing cached plan ({len(editorial_plan.scenes)} scenes).")

            # Brand accent → typography theme for this render only.
            try:
                from typography.theme import get_theme, set_theme
                from style_engine import typography_theme_for_resolved

                self._pipeline_prev_theme = get_theme()
                set_theme(typography_theme_for_resolved(resolved_style, base=self._pipeline_prev_theme))
            except Exception:
                self._pipeline_prev_theme = None

            # Pacing Director: single authoritative transition + camera energy map
            transition_map = authoritative_transition_map(editorial_plan)
            camera_map = editorial_plan.camera_style_map()
            if transition_map:
                print(
                    f"[EDITORIAL] Pacing transitions: "
                    + ", ".join(f"{k}={v}" for k, v in list(transition_map.items())[:12])
                    + (f" (+{len(transition_map) - 12} more)" if len(transition_map) > 12 else "")
                )

            # Music Director on manual track (optional)
            bg_path = config.get("bg_path")
            bg_volume = 0.15
            music_cues_for_qa: list = []
            if bg_path:
                music_plan = build_music_plan(
                    editorial_plan,
                    music_path=bg_path,
                    narration_path=config["audio_path"],
                )
                editorial_plan.music = music_plan.to_dict()
                editorial_plan.film_sections = [s.to_dict() for s in music_plan.sections]
                if state_dir is not None:
                    save_editorial_plan(state_dir, editorial_plan)
                if music_plan.enabled and music_plan.cues:
                    ducked = work_dir / "music_ducked.wav"
                    ok = render_ducked_music(
                        bg_path,
                        music_plan.cues,
                        ducked,
                        duration=float(audio_end),
                    )
                    if ok and ducked.is_file():
                        bg_path = ducked
                        bg_volume = 1.0  # envelope already applied
                        music_cues_for_qa = [c.to_dict() for c in music_plan.cues]
                        print(
                            f"[EDITORIAL] Music ducked stem ({len(music_plan.cues)} cues, "
                            f"{len(music_plan.sections)} sections)."
                        )
                    else:
                        print("[EDITORIAL] Music ducking failed — using flat bed volume.")
                        bg_volume = 0.15

            scene_text_fx = None
            render_audio = str(config["audio_path"])
            smart_plan = None
            if smart_cfg.enabled():
                smart_plan = build_plan(
                    config["rows"],
                    aligned,
                    whisper_words,
                    smart_cfg,
                    state_dir=state_dir,
                    audio_path=config["audio_path"],
                    gemini_settings={"gemini_api_key": self.gemini_key_var.get().strip()},
                    editorial_plan=editorial_plan,
                )
                plan = smart_plan
                if smart_cfg.text_effects and plan.text_effects:
                    display_timeline = vg._scene_display_timeline(aligned, audio_end)
                    scene_text_fx = []
                    for i, row in enumerate(aligned):
                        scene_text_fx.append(
                            scene_text_effects(
                                plan,
                                row["scene_number"],
                                display_timeline[i][0],
                            )
                        )
                    print(f"[SMART] {len(plan.text_effects)} text effect(s) planned.")
                if smart_cfg.sound_effects and plan.sfx_events:
                    print(f"[SMART] {len(plan.sfx_events)} SFX event(s) planned.")
                if smart_cfg.scene_ambience and plan.scene_ambience:
                    mix = ", ".join(
                        f"{b['scene_number']}={b.get('profile', '?')}" for b in plan.scene_ambience[:8]
                    )
                    if len(plan.scene_ambience) > 8:
                        mix += f", +{len(plan.scene_ambience) - 8} more"
                    print(f"[SMART] {len(plan.scene_ambience)} scene ambience bed(s): {mix}")
                needs_audio_mix = (
                    (smart_cfg.sound_effects and plan.sfx_events)
                    or (smart_cfg.scene_ambience and plan.scene_ambience)
                )
                if needs_audio_mix:
                    mixed = work_dir / "narration_with_sfx.wav"
                    from sfx.seed import ensure_sfx_library
                    from smart_editing import sfx_library_root

                    ensure_sfx_library()
                    mix_stats: dict = {}
                    mix_sfx_with_narration(
                        config["audio_path"],
                        plan.sfx_events if smart_cfg.sound_effects else [],
                        mixed,
                        sfx_root=sfx_library_root(),
                        ambience_beds=plan.scene_ambience if smart_cfg.scene_ambience else [],
                        stats=mix_stats,
                    )
                    render_audio = str(mixed)
                    if mix_stats.get("used_fallback"):
                        print("[SMART] WARNING: audio mix failed — using plain narration.")
                    sfx_m = mix_stats.get("sfx_mixed", 0)
                    sfx_p = mix_stats.get("sfx_planned", 0)
                    amb_m = mix_stats.get("ambience_mixed", 0)
                    amb_p = mix_stats.get("ambience_planned", 0)
                    chunks = mix_stats.get("mix_chunks", 0)
                    print(
                        f"[SMART] Mixed audio: {sfx_m}/{sfx_p} SFX, "
                        f"{amb_m}/{amb_p} ambience beds"
                        + (f" ({chunks} ffmpeg pass(es))" if chunks else "")
                        + " under narration."
                    )
                # SFX may still use smart transition picks; visual map stays pacing-authoritative.
                if plan.scene_transitions:
                    print(
                        f"[SMART] Transition SFX cues: {len(plan.scene_transitions)} "
                        "(visual map owned by Editorial Pacing)."
                    )

            vg.render_video(
                aligned,
                audio_end,
                config["images_dir"],
                render_audio,
                str(config["output_path"]),
                resolution="1920x1080",
                fps=30,
                zoom=config["zoom"],
                zoom_amount=0.10,
                bg_audio=str(bg_path) if bg_path else None,
                bg_volume=bg_volume,
                captions=config["captions"],
                scene_text_effects=scene_text_fx,
                visual_transitions=bool(transition_map),
                transition_by_scene=transition_map if transition_map else None,
                camera_by_scene=camera_map if camera_map else None,
            )

            # Editorial QA (never blocks render)
            if state_dir is not None:
                try:
                    ambience_beds = (
                        smart_plan.scene_ambience
                        if smart_plan is not None
                        else []
                    )
                    qa = run_editorial_qa(
                        editorial_plan,
                        output_video=Path(config["output_path"]),
                        narration_path=Path(config["audio_path"]),
                        ambience_beds=ambience_beds,
                        music_cues=music_cues_for_qa,
                        images_dir=Path(config["images_dir"]),
                        transition_map=transition_map,
                    )
                    save_editorial_qa(state_dir, qa)
                    print(f"[EDITORIAL QA] {qa.verdict} — score {qa.score:.0f}/100")
                    for issue in qa.issues[:6]:
                        print(f"  [{issue.severity}] Scene {issue.scene_number} @ {issue.timestamp:.1f}s — {issue.message}")
                except Exception as exc:
                    print(f"[EDITORIAL QA] Skipped ({exc})")

            self._ui_queue.put(("done", str(config["output_path"])))
        except SystemExit as exc:
            # video_generator uses sys.exit("ERROR: ...") on failures
            msg = str(exc) if exc.code not in (0, None) else "Pipeline aborted."
            if isinstance(exc.code, str):
                msg = exc.code
            self._ui_queue.put(("error", msg))
        except _PipelineCancelled as exc:
            self._ui_queue.put(("cancelled", str(exc)))
        except RuntimeError as exc:
            # Asset-resolution failures (Pexels/Flow) — a clean message, not a traceback.
            self._ui_queue.put(("error", str(exc)))
        except Exception:
            self._ui_queue.put(("error", traceback.format_exc()))
        finally:
            try:
                prev = getattr(self, "_pipeline_prev_theme", None)
                if prev is not None:
                    from typography.theme import set_theme

                    set_theme(prev)
                    self._pipeline_prev_theme = None
            except Exception:
                pass
            try:
                os.chdir(old_cwd)
            except OSError:
                pass
            keep_work = os.environ.get("VIDEOGEN_KEEP_WORK", "").strip().lower() in ("1", "true", "yes")
            if keep_work:
                print(f"[DEBUG] Keeping render work dir: {work_dir}")
            else:
                shutil.rmtree(work_dir, ignore_errors=True)
            writer.flush()
            sys.stdout = old_out
            sys.stderr = old_err

    # ---------- UI queue / log ----------

    def _poll_queue(self) -> None:
        logs: list[str] = []
        processed = 0
        batch_limit = self._UI_QUEUE_BATCH
        try:
            try:
                while processed < batch_limit:
                    kind, payload = self._ui_queue.get_nowait()
                    processed += 1
                    if kind == "log":
                        logs.append(payload)
                        self._maybe_update_progress(payload)
                    else:
                        if logs:
                            self._append_log("".join(logs))
                            logs.clear()
                        if kind == "done":
                            self._on_finished(success=True, message=payload)
                        elif kind == "error":
                            self._on_finished(success=False, message=payload)
                        elif kind == "cancelled":
                            self._on_finished(success=False, message=payload, cancelled=True)
                        elif kind == "assets_partial":
                            self._on_assets_partial(payload)
                        elif kind == "assets_complete":
                            self._on_assets_complete(payload)
                        elif kind == "assets_status":
                            self._refresh_qa_ui()
                        elif kind == "scene_busy":
                            scene_number, status = payload
                            key = _scene_key(scene_number)
                            self._busy_scenes.add(key)
                            self._qa.busy[key] = status
                            self._set_scene_status(scene_number, status)
                            # Deferred — immediate flush per scene freezes Windows on large projects.
                            self._refresh_qa_ui()
                        elif kind == "scene_asset":
                            scene_number, result = payload
                            key = _scene_key(scene_number)
                            self._busy_scenes.discard(key)
                            self._qa.busy.pop(key, None)
                            if result is not None:
                                self._asset_results[key] = result
                                # Mirror already done on the worker thread when possible.
                                if getattr(result, "status", None) == SceneStatus.SKIPPED:
                                    self._hydrated_skipped.add(key)
                                elif getattr(result, "ok", False):
                                    self._hydrated_skipped.discard(key)
                                    self._qa.selected_failed.discard(key)
                            scene = next(
                                (s for s in self._scene_rows if _scene_key(s.scene_number) == key),
                                None,
                            )
                            if scene is not None:
                                self._set_scene_status(scene.scene_number, self._row_status_from_result(scene))
                            self._refresh_qa_ui()
                            self._maybe_resume_pending_source_change(key)
                        elif kind == "scene_result":
                            scene_number, token, result = payload
                            key = _scene_key(scene_number)
                            if not self._qa.apply_result(scene_number, token):
                                continue
                            self._busy_scenes.discard(key)
                            if result is not None:
                                self._asset_results[key] = result
                                if getattr(result, "status", None) == SceneStatus.SKIPPED:
                                    self._hydrated_skipped.add(key)
                                elif getattr(result, "ok", False):
                                    self._hydrated_skipped.discard(key)
                                    self._qa.selected_failed.discard(key)
                                    if getattr(result, "source", None) == AssetSource.MANUAL:
                                        self.status_var.set(f"✓ Scene {scene_number} ready")
                                        self._append_log(f"[ASSET] Scene {scene_number} → MANUAL ({Path(result.path).name})\n")
                            if self._recovery_total:
                                self._recovery_done += 1
                            if result is not None and not getattr(result, "ok", False):
                                err = getattr(result, "error", None) or "Needs action"
                                self._append_log(f"[SCENE {scene_number}] {err}\n")
                                if getattr(result, "source", None) == AssetSource.MANUAL:
                                    self.status_var.set("⚠ Could not add local clip")
                                    messagebox.showerror("Could not add local clip", err)
                            self._refresh_qa_ui()
                            self._maybe_resume_pending_source_change(key)
                        elif kind == "flow_retry_batch_done":
                            self._flow_retry_batch_busy = False
                            if self._retry_pumping:
                                self.after(50, self._pump_retry_queue)
                        elif kind == "scene_done":
                            key = _scene_key(payload)
                            self._busy_scenes.discard(key)
                            self._refresh_qa_ui()
                            self._maybe_resume_pending_source_change(key)
                        elif kind == "scene_skipped":
                            key = _scene_key(payload)
                            self._busy_scenes.discard(key)
                            self._hydrated_skipped.add(key)
                            self._refresh_qa_ui()
                        elif kind == "scene_cancelled":
                            key = _scene_key(payload)
                            self._busy_scenes.discard(key)
                            self._refresh_qa_ui()
                            self._maybe_resume_pending_source_change(key)
                        elif kind == "scene_failed":
                            scene_number, error = payload
                            self._busy_scenes.discard(_scene_key(scene_number))
                            self._append_log(f"[SCENE {scene_number}] {error}\n")
                            self._refresh_qa_ui()
            except queue.Empty:
                pass
            if logs:
                self._append_log("".join(logs))
        except Exception:
            # Never let a handler crash stop the poll loop.
            try:
                self._append_log(f"[UI] Queue handler error:\n{traceback.format_exc()}\n")
            except Exception:
                pass
        finally:
            # Drain faster while the worker is flooding the queue (generation start).
            delay = 40 if processed >= batch_limit else 80
            self.after(delay, self._poll_queue)

    def _end_generate_run(self) -> None:
        self._running = False
        self.cancel_btn.grid_forget()
        self._flush_log_disk()
        # Force issues drawer rebuild now that the run is idle.
        self._qa_ui_dirty = True
        self._flush_qa_ui()
        if self._issues_visible:
            self._rebuild_issues()
        self._sync_primary_cta()

    def _on_assets_partial(self, payload: dict) -> None:
        self._end_generate_run()
        snap = self._qa_snapshot()
        self.progress.set(snap.progress)
        self.status_var.set(snap.header)
        self._append_log(
            f"\n⚠ {snap.header}. Use GO TO ERROR, RETRY FAILED, or USE ALTERNATIVES. "
            "Successful assets were kept. History log is not current status.\n"
        )
        self._refresh_cleanup_button(defer=True)
        self._goto_workflow_view("visual_plan")
        self._open_issues_drawer()
        messagebox.showinfo(
            "Scenes need attention",
            f"{snap.header}\n{snap.health_label}\n\n"
            "Successful assets were kept. Open Issues for Retry failed / Retry selected.",
        )

    def _on_assets_complete(self, payload: dict) -> None:
        self._end_generate_run()
        snap = self._qa_snapshot()
        ready = int((payload or {}).get("ready") or (snap.ready if snap else 0))
        total = int((payload or {}).get("total") or (snap.total if snap else 0))
        self.progress.set(1.0 if total and ready >= total else (snap.progress if snap else 1.0))
        self.status_var.set(f"Assets ready — {ready}/{total}")
        self._append_log(
            f"\n✓ Assets ready ({ready}/{total}). "
            "Import a voiceover if needed, then click Render Video.\n"
        )
        self._refresh_cleanup_button(defer=True)
        self._log_visual_qa_report()
        self._goto_workflow_view("audio")

    def _log_visual_qa_report(self) -> None:
        try:
            from visual_qa import build_project_report

            mgr = getattr(self, "_asset_manager", None)
            report = build_project_report(
                self._scene_rows,
                self._asset_results,
                images_dir=mgr.images_dir if mgr else None,
                coverage_by_scene=getattr(mgr, "coverage_by_scene", None) if mgr else None,
                selection_history=getattr(mgr, "selection_history", None) if mgr else None,
                resolved=getattr(self, "_resolved_style", None),
                settings={"gemini_api_key": self.gemini_key_var.get().strip()},
            )
            self._append_log("\n" + "\n".join(report.summary_lines()) + "\n")
            from scene_recovery import scene_key as _sk

            self._visual_qa_results = {
                _sk(str(qa.scene_number)): qa
                for qa in report.results
            }
        except Exception as exc:
            self._append_log(f"\n[VQA] Report skipped: {exc}\n")

    def _on_fix_all_visual_issues(self) -> None:
        if not self._scene_rows:
            return
        mgr = self._ensure_asset_manager(Path(self.images_var.get()))

        self.status_var.set("Fixing visual QA issues…")
        self.fix_all_vqa_btn.configure(state="disabled")

        def work():
            try:
                from scene_recovery import scene_key as _sk
                from visual_qa import build_project_report, fix_all_issues

                report = build_project_report(
                    self._scene_rows,
                    self._asset_results,
                    images_dir=mgr.images_dir,
                    coverage_by_scene=mgr.coverage_by_scene,
                    selection_history=mgr.selection_history,
                    resolved=getattr(self, "_resolved_style", None),
                )
                qa_map = {_sk(str(qa.scene_number)): qa for qa in report.results}
                allocation = None
                if self._visual_plan and getattr(self._visual_plan, "allocation", None):
                    allocation = self._visual_plan.allocation
                elif self._workspace is not None:
                    plan = self._workspace.read_visual_plan_json()
                    if isinstance(plan, dict):
                        allocation = plan.get("allocation")

                fix_report = fix_all_issues(
                    mgr,
                    self._scene_rows,
                    qa_map,
                    self._asset_results,
                    allocation=allocation,
                    max_attempts=2,
                    log=lambda m: self._ui_queue.put(("log", m + "\n")),
                )
                self.after(0, lambda a=allocation: self._persist_qa_flow_spend(a))
                self.after(0, lambda: self._on_fix_all_visual_issues_done(fix_report))
            except Exception as exc:
                msg = str(exc)
                self.after(0, lambda m=msg: self._on_fix_all_visual_issues_failed(m))

        threading.Thread(target=work, daemon=True).start()

    def _persist_qa_flow_spend(self, allocation) -> None:
        """Write the cumulative QA Flow-video spend back to the saved plan.

        Without this the paid ceiling would reset on the next app launch and
        a stubborn project could keep buying fresh credits, one session at a
        time. Best-effort: never let bookkeeping break the fix itself.
        """
        if not isinstance(allocation, dict) or self._workspace is None:
            return
        try:
            plan = self._workspace.read_visual_plan_json()
            if not isinstance(plan, dict):
                return
            stored = plan.get("allocation")
            if not isinstance(stored, dict):
                return
            from visual_qa.fix_engine import QA_FLOW_SPEND_KEY

            spend = allocation.get(QA_FLOW_SPEND_KEY)
            if spend is None or stored.get(QA_FLOW_SPEND_KEY) == spend:
                return
            stored[QA_FLOW_SPEND_KEY] = spend
            self._workspace.save_visual_plan_json(plan)
        except Exception as exc:
            self._append_log(f"[VQA] Could not record Flow credit spend: {exc}\n")

    def _on_fix_all_visual_issues_done(self, fix_report) -> None:
        self._sync_scene_statuses_from_results()
        self._refresh_qa_ui()
        self._log_visual_qa_report()
        self.status_var.set(
            f"VQA fix — {fix_report.fixed} fixed, "
            f"{fix_report.still_weak} weak, {fix_report.still_fail} fail"
        )
        if getattr(self, "fix_all_vqa_btn", None) is not None:
            self.fix_all_vqa_btn.configure(state="normal")
        messagebox.showinfo(
            "Fix All Issues",
            f"Targeted {fix_report.targeted} scene(s).\n"
            f"Fixed: {fix_report.fixed}\n"
            f"Still weak: {fix_report.still_weak}\n"
            f"Still fail: {fix_report.still_fail}\n"
            f"Flow regenerations: {fix_report.flow_regenerations}\n"
            f"Paid Flow video credits used: {getattr(fix_report, 'flow_credits_spent', 0)}",
        )

    def _on_fix_all_visual_issues_failed(self, message: str) -> None:
        self.status_var.set("Ready")
        if getattr(self, "fix_all_vqa_btn", None) is not None:
            self.fix_all_vqa_btn.configure(state="normal")
        messagebox.showerror("Fix All Issues", message)

    def _maybe_update_progress(self, line: str) -> None:
        for marker, value in STAGE_PROGRESS.items():
            if marker in line:
                self.progress.set(value / 100.0)
                self.status_var.set(line.strip())
                break
        if "Done. Output:" in line:
            self.progress.set(1.0)

    def _on_finished(self, success: bool, message: str, cancelled: bool = False) -> None:
        self._end_generate_run()
        if success:
            self.progress.set(1.0)
            self.status_var.set(f"Done — {message}")
            self._append_log(f"\n✓ Finished: {message}\n")
            self._last_output = message
            self._show_preview(message)
            self._goto_workflow_view("render")
            messagebox.showinfo("Done", f"Video saved to:\n{message}")
            self._offer_cleanup_after_render()
        elif cancelled:
            self.status_var.set("Cancelled")
            self._append_log(f"\n○ Cancelled: {message}\n")
            messagebox.showinfo("Cancelled", message)
            self._refresh_cleanup_button(defer=True)
        else:
            self.status_var.set("Failed")
            self._append_log(f"\n✗ Error: {message}\n")
            messagebox.showerror("Generation failed", message)
            self._refresh_cleanup_button(defer=True)
        self._refresh_qa_ui(immediate=True)

    def _show_preview(self, video_path: str) -> None:
        """Extract a thumbnail frame via ffmpeg and reveal the preview panel."""
        import tempfile as _tmp

        thumb = Path(_tmp.mktemp(suffix=".jpg"))
        ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
        try:
            from providers import hidden_subprocess

            result = hidden_subprocess.run(
                [
                    ffmpeg, "-y",
                    "-ss", "1",           # seek to 1 s for a more interesting frame
                    "-i", video_path,
                    "-vframes", "1",
                    "-q:v", "3",
                    str(thumb),
                ],
                capture_output=True, timeout=15,
            )
        except Exception:
            return

        if not thumb.is_file():
            return

        try:
            from PIL import Image

            img = Image.open(thumb).convert("RGB")
            thumb.unlink(missing_ok=True)

            # Determine display size: fill available width keeping 16:9 ratio
            panel_w = self._right_panel.winfo_width() - 40
            if panel_w < 100:
                panel_w = 520   # fallback before widget is measured
            vid_w, vid_h = img.size
            ratio = vid_h / max(vid_w, 1)
            disp_w = min(panel_w, 600)
            disp_h = int(disp_w * ratio)

            self._prev_image = ctk.CTkImage(
                light_image=img,
                dark_image=img,
                size=(disp_w, disp_h),
            )
            self._thumb_label.configure(image=self._prev_image)

            # Grid the preview panel (row=4) so the log (row=3) shrinks to ~50%
            self._preview_panel.grid(
                row=4, column=0, sticky="nsew", padx=16, pady=(8, 12)
            )
            # Ensure equal row weights so log and preview each get ~half
            self._right_panel.grid_rowconfigure(3, weight=1)
            self._right_panel.grid_rowconfigure(4, weight=1)

        except Exception:
            thumb.unlink(missing_ok=True)

    def _open_in_player(self) -> None:
        """Open the generated video in the system default player."""
        if not self._last_output:
            return
        p = Path(self._last_output)
        if not p.is_file():
            messagebox.showwarning("Not found", f"File not found:\n{self._last_output}")
            return
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", str(p)])
            elif sys.platform == "win32":
                os.startfile(str(p))   # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", str(p)])
        except Exception as exc:
            messagebox.showerror("Cannot open", str(exc))

    def _open_output_folder(self) -> None:
        """Open the folder that contains the generated video (selects the file when possible)."""
        if not self._last_output:
            return
        p = Path(self._last_output)
        folder = p.parent if p.exists() else Path(self._last_output).parent
        if not folder.is_dir():
            messagebox.showwarning("Not found", f"Folder not found:\n{folder}")
            return
        try:
            if sys.platform == "darwin":
                if p.is_file():
                    subprocess.Popen(["open", "-R", str(p)])
                else:
                    subprocess.Popen(["open", str(folder)])
            elif sys.platform == "win32":
                if p.is_file():
                    # Two-arg form: "/select," + path — survives spaces in the path.
                    subprocess.Popen(["explorer", "/select,", str(p)])
                else:
                    os.startfile(str(folder))  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", str(folder)])
        except Exception as exc:
            messagebox.showerror("Cannot open folder", str(exc))

    def _clear_log(self) -> None:
        self._log_backlog.clear()
        self._log_disk_buf.clear()
        self._log_disk_scheduled = False
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")

    def _append_log(self, text: str) -> None:
        line = (text or "").strip().split("\n")[-1].strip()
        if line:
            try:
                self.status_line_var.set(line[:140])
            except Exception:
                pass
        if self._workspace is not None:
            self._log_disk_buf.append(text)
            if len(self._log_disk_buf) >= 40:
                self._flush_log_disk()
            else:
                self._schedule_log_disk_flush()
        if not self._log_visible:
            self._log_backlog.append(text)
            if len(self._log_backlog) > 400:
                self._log_backlog = self._log_backlog[-300:]
            return
        self.log_box.configure(state="normal")
        self.log_box.insert("end", text)
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _ensure_sfx_ready(self) -> None:
        """Copy bundled SFX + ambience into ~/.videogen/sfx when empty/incomplete."""
        if self._sfx_ready:
            return
        try:
            from sfx.seed import bundled_sfx_inventory, count_resolvable_sfx, ensure_sfx_library

            inv = bundled_sfx_inventory()
            ensure_sfx_library()
            n = count_resolvable_sfx()
            self._sfx_ready = True
            if inv.get("ok"):
                self._append_log(
                    f"[SFX] Library ready: {n} sounds "
                    f"(bundled {inv.get('wav_count')} wavs incl. ambience)\n"
                )
            elif n == 0:
                self._append_log(
                    "[SFX] Warning: no bundled SFX/ambience found — "
                    "Smart Editing sounds will be silent.\n"
                )
            else:
                self._append_log(f"[SFX] Library ready: {n} sounds\n")
        except Exception as exc:
            self._append_log(f"[SFX] Seed skipped ({exc})\n")
            # Allow retry next time
            self._sfx_ready = False

    def _on_close(self) -> None:
        busy_bits = []
        if self._running:
            busy_bits.append("asset generation / render")
        if busy_bits:
            if not messagebox.askyesno(
                "Quit?",
                "Still running: " + ", ".join(busy_bits) + ".\n\n"
                "Quit anyway? In-flight work will be interrupted.",
            ):
                return
        try:
            self._flush_log_disk()
        except Exception:
            pass
        try:
            if self._running and self._asset_manager is not None:
                self._asset_manager.request_cancel()
        except Exception:
            pass
        try:
            self._stop_voice_playback()
        except Exception:
            pass
        # Lifecycle only — do not change Flow API / concurrency / GENERATE lock.
        try:
            mgr = self._flow_engine_manager
            if mgr is not None:
                mgr.stop()
        except Exception:
            pass
        try:
            from providers.youtube.acquisition import shutdown_client

            shutdown_client()
        except Exception:
            pass
        self.destroy()


def main() -> None:
    # Re-assert Windows console hiding (frozen builds / late imports of yt-dlp).
    _hidden_subprocess.install()
    _configure_macos_dock_name()
    ensure_ffmpeg_on_path()
    app = VideoGeneratorApp()
    app.mainloop()


if __name__ == "__main__":
    # Frozen .app: Whisper/ctranslate2 may spawn workers. Without freeze_support,
    # those children re-run this file and open a second GUI window.
    multiprocessing.freeze_support()
    if multiprocessing.current_process().name != "MainProcess":
        raise SystemExit(0)
    main()
