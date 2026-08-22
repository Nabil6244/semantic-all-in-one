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

import customtkinter as ctk

import video_generator as vg
from asset_manager import AssetManager
from providers.base import AssetResult, AssetSource, MediaType, SceneRow, SceneStatus
from providers.router import SceneAssetRouter
from scene_recovery import SceneRecoveryTracker, summarize_assets
from scene_qa import SceneQAState, preview_alternatives, save_qa_file, load_qa_file, summarize_alternative_preview, short_error
from manual_clip import FILE_DIALOG_TYPES, ManualClipError, validate_local_media
from visual_director.llm import MISSING_GEMINI_KEY, gemini_configured
from tts.base import CLONE_MODEL_ID, PREVIEW_TEXT, VOICE_MODE_LABEL_CLONE
from tts.client import get_shared_client, qwen_runtime_status, shutdown_shared_client
from tts.errors import TTSError
from tts.model_cache import MODEL_DIR_NAME, candidate_model_dirs, model_is_installed
from tts.narration import VOICE_NARRATION_PLACEHOLDER, collect_narration
from tts.qwen_provision import friendly_provision_error, provision_qwen, qwen_install_status_message
from tts.voice_library import (
    VoiceProfile,
    create_voice_profile,
    delete_voice,
    get_default_voice,
    get_voice,
    list_voices,
    mark_voice_needs_rebuild,
    mark_voice_ready,
    migrate_legacy_reference,
    refresh_profile_status,
    replace_voice_reference,
    set_default_voice,
)
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
    build_plan,
    get_cached_whisper_words,
    mix_sfx_with_narration,
    scene_text_effects,
)


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
    if path.is_file():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_settings(data: dict) -> None:
    import json

    try:
        _settings_path().write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        pass


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
    if "selected" in t:
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


def _logo_path() -> Path | None:
    """Return path to assets/logo.png if present (dev or bundled)."""
    candidates = [
        _bundle_root() / "assets" / "logo.png",
        SOURCE_DIR / "assets" / "logo.png",
    ]
    for p in candidates:
        if p.is_file():
            return p
    return None


def _logo_ctk_image(diameter: int, *, circular: bool = True):
    """Load branding asset; UI uses a centered circular crop (no stretch)."""
    logo_path = _logo_path()
    if logo_path is None:
        return None, None
    try:
        from PIL import Image, ImageDraw

        img = Image.open(logo_path).convert("RGBA")
        w, h = img.size
        if h <= 0 or w <= 0:
            return None, None
        size = max(1, int(diameter))
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
        return ctk_img, img
    except Exception:
        return None, None


def _logo_icon_photo(size: int = 64):
    """Window/dock icon — same centered circular crop as the header."""
    logo_path = _logo_path()
    if logo_path is None:
        return None
    try:
        from PIL import Image, ImageDraw, ImageTk

        img = Image.open(logo_path).convert("RGBA")
        w, h = img.size
        if h <= 0 or w <= 0:
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
        return ImageTk.PhotoImage(out)
    except Exception:
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

# ── Dark cinematic palette ─────────────────────────────────────────────────
_BG          = "#0B0D10"   # near-black canvas
_PANEL       = "#12151A"   # sidebar
_PANEL_ALT   = "#0F1218"   # main workspace
_CARD        = "#181C24"   # elevated panels
_CARD_HOVER  = "#1E2430"   # hover / secondary buttons
_ROW_ALT     = "#141820"   # alternating scene row
_BORDER      = "#2A3140"   # low-contrast borders
_TEXT        = "#E8EAED"   # primary text
_MUTED       = "#8B95A8"   # secondary text
_ACCENT      = "#4F6BF6"   # electric blue / indigo
_ACCENT_HOV  = "#3D56E8"
_ACCENT_DARK = "#FFFFFF"   # text on primary buttons
_ACCENT_SEL  = "#1A2240"   # selected scene background
_ACCENT_BORDER = "#3D5080" # selected scene border
_SUCCESS     = "#34D399"   # ready
_PROCESSING  = "#60A5FA"   # in progress
_QUEUED      = "#64748B"   # queued / waiting
_WARNING     = "#FBBF24"   # needs action
_DANGER      = "#F87171"   # failed
_DANGER_BG   = "#2A1A1A"   # failed row tint
_SKIPPED     = "#6B7280"
_COPPER      = _ACCENT
# ───────────────────────────────────────────────────────────────────────────

SOURCE_BADGE = {
    AssetSource.FLOW_IMAGE: ("AI Image", _MUTED, "transparent"),
    AssetSource.FLOW_VIDEO: ("AI Video", _MUTED, "transparent"),
    AssetSource.STOCK: ("Stock", _MUTED, "transparent"),
    AssetSource.STOCK_IMAGE: ("Stock", _MUTED, "transparent"),
    AssetSource.STOCK_VIDEO: ("Stock", _MUTED, "transparent"),
    AssetSource.YOUTUBE_VIDEO: ("YouTube", _MUTED, "transparent"),
    AssetSource.MANUAL: ("Manual", _MUTED, "transparent"),
    AssetSource.LOCAL: ("Local", _MUTED, "transparent"),
}

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
        "cancelled": ("— SKIPPED", _SKIPPED),
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


class VideoGeneratorApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Semantic YT Studio")
        self.geometry("1240x780")
        self.minsize(960, 620)
        self._qa_ui_dirty = False
        self._qa_ui_scheduled = False
        self._qa_persist_at = 0.0
        self._log_visible = False
        self._issues_visible = False
        self._log_backlog: list[str] = []
        self._scene_row_signature: tuple = ()
        self._selected_scene_key: str | None = None

        # Dark cinematic theme — premium production workspace
        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")
        self.configure(fg_color=_BG)

        self._ui_queue: queue.Queue = queue.Queue()
        self._worker: threading.Thread | None = None
        self._running = False
        self._last_output: str | None = None
        self._settings = load_settings()
        self._workspace = None
        self._project_menu_lock = False
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

        # Parent containers reused by helpers
        self._left_panel: ctk.CTkFrame | None = None
        self._right_panel: ctk.CTkFrame | None = None

        self._build_ui()
        self._apply_defaults()
        self._poll_queue()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------- UI ----------

    def _build_ui(self) -> None:
        self._set_window_icon()

        # Top bar + 2 columns (script | production)
        self.grid_columnconfigure(0, minsize=360, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=1)

        # ── Left panel ───────────────────────────────────────────────────
        left = ctk.CTkFrame(self, fg_color=_PANEL, corner_radius=0)
        left.grid(row=1, column=0, sticky="nsew")
        left.grid_columnconfigure(0, weight=1)
        left.grid_rowconfigure(1, weight=1)
        self._left_panel = left

        # Brand header
        brand = ctk.CTkFrame(left, fg_color="transparent")
        brand.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 6))
        brand.grid_columnconfigure(1, weight=1)

        logo_path = _logo_path()
        self._logo_ctk = None
        if logo_path is not None:
            self._logo_ctk, _ = _logo_ctk_image(48)
            if self._logo_ctk is not None:
                ctk.CTkLabel(
                    brand, image=self._logo_ctk, text="",
                    fg_color="transparent",
                ).grid(row=0, column=0, rowspan=2, sticky="w", padx=(0, 12))

        ctk.CTkLabel(
            brand,
            text="Semantic YT Studio",
            font=ctk.CTkFont(size=17, weight="bold"),
            text_color=_TEXT,
            fg_color="transparent",
        ).grid(row=0, column=1, sticky="w")
        ctk.CTkLabel(
            brand,
            text="AI Video Production",
            font=ctk.CTkFont(size=11),
            text_color=_MUTED,
            fg_color="transparent",
        ).grid(row=1, column=1, sticky="w")

        # Thin divider
        ctk.CTkFrame(left, fg_color=_BORDER, height=1, corner_radius=0).grid(
            row=1, column=0, sticky="ew", padx=0, pady=0
        )

        # Scrollable inputs area
        scroll = ctk.CTkScrollableFrame(
            left,
            fg_color="transparent",
            scrollbar_button_color=_BORDER,
            scrollbar_button_hover_color=_ACCENT,
        )
        scroll.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)
        scroll.grid_columnconfigure(0, weight=1)
        self._scroll = scroll

        # ── Variables ────────────────────────────────────────────────────
        self.csv_var     = ctk.StringVar()
        self.audio_var   = ctk.StringVar()
        self.images_var  = ctk.StringVar()
        self.bg_var      = ctk.StringVar()
        self.output_var  = ctk.StringVar()
        self.model_var   = ctk.StringVar(value="small")
        self.captions_var = ctk.BooleanVar(value=False)
        self.zoom_var    = ctk.BooleanVar(value=True)
        self.smart_text_effects_var = ctk.BooleanVar(
            value=bool(self._settings.get("smart_text_effects", DEFAULT_SETTINGS["text_effects"]))
        )
        self.smart_sfx_var = ctk.BooleanVar(
            value=bool(self._settings.get("smart_sound_effects", DEFAULT_SETTINGS["sound_effects"]))
        )
        self.smart_intensity_var = ctk.StringVar(
            value=str(self._settings.get("smart_intensity", DEFAULT_SETTINGS["intensity"]))
        )
        self.smart_mode_var = ctk.StringVar(
            value=str(self._settings.get("smart_mode", DEFAULT_SETTINGS["mode"]))
        )
        self.pexels_key_var = ctk.StringVar(value=self._settings.get("pexels_api_key", ""))
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
        self.current_project_meta_var = ctk.StringVar(value="Click New Project to start a video")
        self.project_menu_var = ctk.StringVar(value="(none)")
        self._project_labels: dict[str, str] = {}
        self.stage_var = ctk.StringVar(value="SCRIPT")
        self.prod_ready_var = ctk.StringVar(value="")
        self.prod_processing_var = ctk.StringVar(value="")
        self.prod_queued_var = ctk.StringVar(value="")
        self.prod_needs_var = ctk.StringVar(value="")
        self.prod_mix_var = ctk.StringVar(value="")
        self.hint_var = ctk.StringVar(value="Create a project, then paste a script or import a CSV.")

        topbar = ctk.CTkFrame(self, fg_color=_PANEL, corner_radius=0)
        topbar.grid(row=0, column=0, columnspan=2, sticky="ew")
        topbar.grid_columnconfigure(3, weight=1)
        ctk.CTkFrame(topbar, fg_color=_BORDER, height=1, corner_radius=0).grid(
            row=2, column=0, columnspan=8, sticky="ew"
        )
        ctk.CTkLabel(
            topbar, text="PROJECT", font=ctk.CTkFont(size=9, weight="bold"),
            text_color=_MUTED,
        ).grid(row=0, column=0, sticky="w", padx=(16, 6), pady=(8, 0))
        self._project_menu = ctk.CTkOptionMenu(
            topbar,
            variable=self.project_menu_var,
            values=["＋ New Project", "Open Project…", "(none)"],
            command=self._on_project_menu,
            width=240,
            height=28,
            fg_color=_CARD,
            button_color=_BORDER,
            button_hover_color=_ACCENT,
            text_color=_TEXT,
            dropdown_fg_color=_CARD,
            dropdown_text_color=_TEXT,
            dropdown_hover_color=_BORDER,
        )
        self._project_menu.grid(row=1, column=0, sticky="w", padx=(16, 8), pady=(0, 8))
        ctk.CTkLabel(
            topbar, textvariable=self.current_project_title_var,
            font=ctk.CTkFont(size=13, weight="bold"), text_color=_TEXT,
        ).grid(row=0, column=1, sticky="w", padx=(8, 16), pady=(8, 0))
        ctk.CTkLabel(
            topbar, textvariable=self.current_project_meta_var,
            font=ctk.CTkFont(size=11), text_color=_MUTED,
        ).grid(row=1, column=1, sticky="w", padx=(8, 16), pady=(0, 8))
        ctk.CTkLabel(
            topbar, textvariable=self.stage_var,
            font=ctk.CTkFont(size=11, weight="bold"), text_color=_ACCENT,
        ).grid(row=0, column=2, sticky="w", padx=8, pady=(8, 0))
        self.status_var = ctk.StringVar(value="Ready")
        ctk.CTkLabel(
            topbar, textvariable=self.status_var, font=ctk.CTkFont(size=11), text_color=_MUTED,
        ).grid(row=1, column=2, sticky="w", padx=8, pady=(0, 8))
        ctk.CTkLabel(
            topbar, textvariable=self.prod_ready_var,
            font=ctk.CTkFont(size=12, weight="bold"), text_color=_TEXT,
        ).grid(row=0, column=3, sticky="w", padx=8, pady=(8, 0))
        self.qa_counter_var = ctk.StringVar(value="")
        self.issues_toggle_btn = ctk.CTkButton(
            topbar, textvariable=self.qa_counter_var, width=150, height=28,
            fg_color="transparent", border_width=1, border_color=_BORDER,
            text_color=_DANGER, hover_color=_DANGER_BG, font=ctk.CTkFont(size=11, weight="bold"),
            command=self._toggle_issues,
        )
        self.issues_toggle_btn.grid(row=0, column=4, rowspan=2, padx=6, pady=8)
        self.top_analyze_btn = ctk.CTkButton(
            topbar, text="Analyze", width=88, height=28,
            fg_color="transparent", border_width=1, border_color=_BORDER,
            text_color=_TEXT, hover_color=_CARD_HOVER, font=ctk.CTkFont(size=12),
            command=self._on_analyze_script,
        )
        self.top_analyze_btn.grid(row=0, column=5, rowspan=2, padx=4, pady=8)
        self.top_voice_btn = ctk.CTkButton(
            topbar, text="Voice", width=72, height=28,
            fg_color="transparent", border_width=1, border_color=_BORDER,
            text_color=_TEXT, hover_color=_CARD_HOVER, font=ctk.CTkFont(size=12),
            command=self._on_generate_narration,
        )
        self.top_voice_btn.grid(row=0, column=6, rowspan=2, padx=4, pady=8)
        ctk.CTkButton(
            topbar, text="Settings", width=80, height=28,
            fg_color="transparent", border_width=1, border_color=_BORDER,
            text_color=_TEXT, hover_color=_CARD_HOVER, font=ctk.CTkFont(size=12),
            command=self._open_settings,
        ).grid(row=0, column=7, rowspan=2, padx=(4, 16), pady=8)
        self.progress = ctk.CTkProgressBar(
            topbar, height=5, progress_color=_ACCENT, fg_color=_BORDER, corner_radius=3,
        )
        self.progress.grid(row=3, column=0, columnspan=8, sticky="ew", padx=16, pady=(0, 4))
        self.progress.set(0)
        self.prod_error_var = ctk.StringVar(value="")
        ctk.CTkLabel(
            topbar, textvariable=self.prod_error_var,
            font=ctk.CTkFont(size=10), text_color=_WARNING, anchor="w",
        ).grid(row=4, column=0, columnspan=8, sticky="w", padx=16, pady=(0, 6))

        # Flow Image Settings — exactly the options flow-engine/config.js supports
        # (see FLOW_IMAGE_MODELS etc. above). Video settings live per-Video-Profile
        # instead (see _get_video_profiles) since video needs its own account pool.
        flow_saved = self._settings.get("flow_settings", {})
        self.flow_image_model_var = ctk.StringVar(value=flow_saved.get("model", FLOW_IMAGE_MODELS[1][0]))
        self.flow_image_aspect_var = ctk.StringVar(
            value=flow_saved.get("aspectRatio", FLOW_IMAGE_ASPECT_RATIOS[0][0])
        )
        # Live-updated whenever the Flow engine reports its account list, so the
        # Video Profile editor can show real account names to assign, not just IDs.
        self._known_flow_accounts: list[dict] = []

        mode_wrap = ctk.CTkFrame(scroll, fg_color="transparent")
        mode_wrap.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 0))
        ctk.CTkLabel(
            mode_wrap, text="SCRIPT", font=ctk.CTkFont(size=9, weight="bold"),
            text_color=_MUTED, anchor="w",
        ).pack(anchor="w")
        self._mode_seg = ctk.CTkSegmentedButton(
            mode_wrap,
            values=["Manual CSV", "AI Script"],
            command=self._on_script_mode,
            fg_color=_BORDER,
            selected_color=_ACCENT,
            selected_hover_color=_ACCENT_HOV,
            unselected_color=_CARD,
            unselected_hover_color=_CARD_HOVER,
            text_color=_TEXT,
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        self._mode_seg.pack(fill="x", pady=(6, 0))
        self._mode_seg.set("Manual CSV")

        self._csv_block = ctk.CTkFrame(scroll, fg_color="transparent")
        self._csv_block.grid(row=1, column=0, sticky="ew", padx=16)
        self._csv_block.grid_columnconfigure(0, weight=1)
        self._path_row(0, "Script CSV", self.csv_var, self._browse_csv, parent=self._csv_block)

        self._ai_block = ctk.CTkFrame(
            scroll, fg_color=_CARD, corner_radius=6, border_width=1, border_color=_BORDER,
        )
        self._ai_block.grid(row=1, column=0, sticky="ew", padx=16, pady=(10, 0))
        self._ai_block.grid_columnconfigure(0, weight=1)
        ai_head = ctk.CTkFrame(self._ai_block, fg_color="transparent")
        ai_head.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 4))
        ai_head.grid_columnconfigure(1, weight=1)
        if getattr(self, "_logo_ctk", None) is not None:
            ctk.CTkLabel(ai_head, image=self._logo_ctk, text="").grid(row=0, column=0, rowspan=2, padx=(0, 10))
        ctk.CTkLabel(
            ai_head, text="AI Script", font=ctk.CTkFont(size=14, weight="bold"), text_color=_TEXT,
        ).grid(row=0, column=1, sticky="w")
        ctk.CTkLabel(
            ai_head, text="Gemini 3.6 Flash visual director", font=ctk.CTkFont(size=11), text_color=_MUTED,
        ).grid(row=1, column=1, sticky="w")
        self._gemini_status_var = ctk.StringVar(value="")
        self._gemini_status_label = ctk.CTkLabel(
            self._ai_block, textvariable=self._gemini_status_var, font=ctk.CTkFont(size=11),
            text_color=_MUTED, wraplength=280, justify="left",
        )
        self._gemini_status_label.grid(row=1, column=0, sticky="ew", padx=12)
        self.script_box = ctk.CTkTextbox(
            self._ai_block, height=150, fg_color=_BG, border_color=_BORDER, border_width=1,
            text_color=_TEXT, font=ctk.CTkFont(size=12), wrap="word",
        )
        self.script_box.grid(row=2, column=0, sticky="ew", padx=12, pady=(4, 8))
        self.script_box.insert("1.0", "Paste your narration script here...")
        ai_btns = ctk.CTkFrame(self._ai_block, fg_color="transparent")
        ai_btns.grid(row=3, column=0, sticky="ew", padx=12, pady=(0, 12))
        ai_btns.grid_columnconfigure(0, weight=1)
        self.analyze_btn = ctk.CTkButton(
            ai_btns, text="Analyze Script", height=34, fg_color=_ACCENT, hover_color=_ACCENT_HOV,
            text_color=_ACCENT_DARK, font=ctk.CTkFont(size=13, weight="bold"),
            command=self._on_analyze_script,
        )
        self.analyze_btn.grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(
            ai_btns, text="Export CSV", width=100, height=34, fg_color="transparent",
            border_width=1, border_color=_BORDER, text_color=_TEXT, hover_color=_CARD_HOVER,
            command=self._export_ai_csv,
        ).grid(row=0, column=1, padx=(8, 0))
        self._ai_block.grid_remove()
        self._refresh_gemini_status()

        self.tts_status_var = ctk.StringVar(value="")
        self.tts_selected_voice_var = ctk.StringVar(value="(none)")
        self.tts_voice_detail_var = ctk.StringVar(value="Create or select a saved voice.")
        self.tts_create_name_var = ctk.StringVar(value="")
        self.tts_create_ref_var = ctk.StringVar(value="")
        self._tts_voice_profiles: dict[str, VoiceProfile] = {}
        self._tts_create_ref_path: Path | None = None
        self._settings.setdefault(
            "qwen_selected_voice_id",
            self._settings.get("qwen_selected_voice_id") or "",
        )

        tts = ctk.CTkFrame(
            scroll, fg_color=_CARD, corner_radius=6, border_width=1, border_color=_BORDER,
        )
        tts.grid(row=2, column=0, sticky="ew", padx=16, pady=(10, 0))
        tts.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            tts, text="VOICE",
            font=ctk.CTkFont(size=9, weight="bold"), text_color=_MUTED, anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(10, 0))
        ctk.CTkLabel(
            tts, text=VOICE_MODE_LABEL_CLONE,
            font=ctk.CTkFont(size=11, weight="bold"), text_color=_TEXT, anchor="w",
        ).grid(row=1, column=0, sticky="w", padx=12, pady=(2, 0))

        # Status text — wraplength tracks panel width (avoids cut-off in the left column).
        self._tts_status_label = ctk.CTkLabel(
            tts,
            textvariable=self.tts_status_var,
            font=ctk.CTkFont(size=11),
            text_color=_MUTED,
            wraplength=280,
            justify="left",
            anchor="w",
        )
        self._tts_status_label.grid(row=2, column=0, sticky="ew", padx=12, pady=(4, 0))
        # Idle: Download button. Active: progress bar + ✕ (no Open Folder here).
        tts_status_actions = ctk.CTkFrame(tts, fg_color="transparent")
        tts_status_actions.grid(row=3, column=0, sticky="ew", padx=12, pady=(6, 0))
        tts_status_actions.grid_columnconfigure(0, weight=1)
        self._tts_download_btn = ctk.CTkButton(
            tts_status_actions,
            text="Download",
            width=88,
            height=28,
            fg_color=_ACCENT,
            hover_color=_ACCENT_HOV,
            text_color=_ACCENT_DARK,
            font=ctk.CTkFont(size=11, weight="bold"),
            corner_radius=4,
            command=self._on_download_qwen,
        )
        self._tts_download_btn.grid(row=0, column=0, sticky="w")

        self._tts_dl_row = ctk.CTkFrame(tts_status_actions, fg_color="transparent")
        self._tts_dl_row.grid(row=1, column=0, sticky="ew")
        self._tts_dl_row.grid_columnconfigure(0, weight=1)
        self._tts_dl_progress = ctk.CTkProgressBar(
            self._tts_dl_row,
            height=10,
            progress_color=_ACCENT,
            fg_color=_BORDER,
            corner_radius=4,
        )
        self._tts_dl_progress.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self._tts_dl_progress.set(0)
        self._tts_download_cancel_btn = ctk.CTkButton(
            self._tts_dl_row,
            text="✕",
            width=32,
            height=28,
            fg_color="transparent",
            border_width=1,
            border_color=_BORDER,
            text_color=_MUTED,
            hover_color=_BORDER,
            font=ctk.CTkFont(size=14, weight="bold"),
            corner_radius=4,
            command=self._on_cancel_qwen_download,
        )
        self._tts_download_cancel_btn.grid(row=0, column=1, sticky="e")
        self._tts_dl_row.grid_remove()
        self._qwen_download_active = False
        self._qwen_download_cancel = False

        lib_head = ctk.CTkFrame(tts, fg_color="transparent")
        lib_head.grid(row=4, column=0, sticky="ew", padx=12, pady=(10, 0))
        lib_head.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            lib_head, text="Voice Library", font=ctk.CTkFont(size=11, weight="bold"), text_color=_MUTED,
        ).grid(row=0, column=0, sticky="w")
        self._tts_voice_menu = ctk.CTkOptionMenu(
            lib_head,
            variable=self.tts_selected_voice_var,
            values=["(none)"],
            width=180,
            height=28,
            fg_color=_BG,
            button_color=_BORDER,
            button_hover_color=_ACCENT,
            text_color=_TEXT,
            dropdown_fg_color=_CARD,
            dropdown_text_color=_TEXT,
            command=self._on_voice_selected,
        )
        self._tts_voice_menu.grid(row=0, column=1, sticky="e")
        self._tts_voice_detail_label = ctk.CTkLabel(
            tts, textvariable=self.tts_voice_detail_var, font=ctk.CTkFont(size=11),
            text_color=_MUTED, wraplength=280, justify="left", anchor="w",
        )
        self._tts_voice_detail_label.grid(row=5, column=0, sticky="ew", padx=12, pady=(4, 0))

        voice_actions = ctk.CTkFrame(tts, fg_color="transparent")
        voice_actions.grid(row=6, column=0, sticky="ew", padx=12, pady=(6, 0))
        voice_actions.grid_columnconfigure(1, weight=1)
        ctk.CTkButton(
            voice_actions,
            text="Test Voice",
            width=100,
            height=28,
            fg_color="transparent",
            border_width=1,
            border_color=_BORDER,
            text_color=_TEXT,
            hover_color=_CARD_HOVER,
            command=self._on_preview_voice,
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(
            voice_actions,
            text="Delete",
            width=78,
            height=28,
            fg_color="transparent",
            border_width=1,
            border_color=_DANGER,
            text_color=_DANGER,
            hover_color=_DANGER_BG,
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._delete_selected_voice,
        ).grid(row=0, column=2, sticky="e")
        self._tts_test_hint = ctk.CTkLabel(
            tts,
            text="Test Voice plays a short sample with the selected voice.",
            font=ctk.CTkFont(size=10),
            text_color=_MUTED,
            wraplength=280,
            justify="left",
            anchor="w",
        )
        self._tts_test_hint.grid(row=7, column=0, sticky="ew", padx=12, pady=(4, 0))

        ctk.CTkLabel(
            tts, text="Create New Voice", font=ctk.CTkFont(size=11, weight="bold"),
            text_color=_MUTED, anchor="w",
        ).grid(row=8, column=0, sticky="w", padx=12, pady=(10, 0))
        ctk.CTkEntry(
            tts, textvariable=self.tts_create_name_var, placeholder_text="Voice name (e.g. Nabil)",
            height=28, border_color=_BORDER, fg_color=_BG,
        ).grid(row=9, column=0, sticky="ew", padx=12, pady=(4, 0))
        create_ref_row = ctk.CTkFrame(tts, fg_color="transparent")
        create_ref_row.grid(row=10, column=0, sticky="ew", padx=12, pady=(4, 0))
        create_ref_row.grid_columnconfigure(0, weight=1)
        ctk.CTkEntry(
            create_ref_row, textvariable=self.tts_create_ref_var, placeholder_text="Reference audio path",
            height=28, border_color=_BORDER, fg_color=_BG,
        ).grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(
            create_ref_row, text="Browse", width=72, height=28, fg_color="transparent",
            border_width=1, border_color=_BORDER, text_color=_TEXT, hover_color=_CARD_HOVER,
            command=self._browse_create_reference_audio,
        ).grid(row=0, column=1, padx=(8, 0))
        ctk.CTkLabel(
            tts, text="Reference Transcript", font=ctk.CTkFont(size=11), text_color=_MUTED, anchor="w",
        ).grid(row=11, column=0, sticky="w", padx=12, pady=(6, 0))
        self.tts_create_transcript_box = ctk.CTkTextbox(
            tts, height=72, fg_color=_BG, border_color=_BORDER, border_width=1,
            text_color=_TEXT, font=ctk.CTkFont(size=11), wrap="word",
        )
        self.tts_create_transcript_box.grid(row=12, column=0, sticky="ew", padx=12, pady=(4, 0))
        self.tts_create_transcript_box.insert(
            "1.0",
            "Enter the exact words spoken in the reference recording.",
        )
        self.tts_create_btn = ctk.CTkButton(
            tts, text="+ Create Voice", height=32, fg_color=_ACCENT, hover_color=_ACCENT_HOV,
            text_color=_ACCENT_DARK, font=ctk.CTkFont(size=12, weight="bold"),
            command=self._create_voice_profile,
        )
        self.tts_create_btn.grid(row=13, column=0, sticky="ew", padx=12, pady=(8, 0))

        ctk.CTkLabel(
            tts, text="Narration Script", font=ctk.CTkFont(size=11, weight="bold"),
            text_color=_MUTED, anchor="w",
        ).grid(row=14, column=0, sticky="w", padx=12, pady=(12, 0))
        self.tts_narration_box = ctk.CTkTextbox(
            tts, height=110, fg_color=_BG, border_color=_BORDER, border_width=1,
            text_color=_TEXT, font=ctk.CTkFont(size=12), wrap="word",
        )
        self.tts_narration_box.grid(row=15, column=0, sticky="ew", padx=12, pady=(4, 0))
        self.tts_narration_box.insert("1.0", VOICE_NARRATION_PLACEHOLDER)
        # Large pastes into CTk/Tk text with undo enabled can freeze the UI.
        try:
            self.tts_narration_box._textbox.configure(undo=False)  # type: ignore[attr-defined]
        except Exception:
            pass
        self.tts_narration_box.bind("<FocusIn>", self._tts_narration_focus_in)
        self.tts_narration_box.bind("<<Paste>>", self._tts_narration_paste)

        self.tts_btn = ctk.CTkButton(
            tts, text="Generate Narration", height=34, fg_color=_ACCENT,
            hover_color=_ACCENT_HOV, text_color=_ACCENT_DARK,
            font=ctk.CTkFont(size=13, weight="bold"), command=self._on_tts_primary_click,
        )
        self.tts_btn.grid(row=16, column=0, sticky="ew", padx=12, pady=(10, 4))

        self.tts_progress = ctk.CTkProgressBar(
            tts,
            height=8,
            progress_color=_ACCENT,
            fg_color=_BORDER,
            corner_radius=4,
        )
        self.tts_progress.grid(row=17, column=0, sticky="ew", padx=12, pady=(0, 2))
        self.tts_progress.set(0)
        self.tts_progress_var = ctk.StringVar(value="")
        self.tts_progress_label = ctk.CTkLabel(
            tts,
            textvariable=self.tts_progress_var,
            font=ctk.CTkFont(size=11),
            text_color=_MUTED,
            anchor="w",
        )
        self.tts_progress_label.grid(row=18, column=0, sticky="ew", padx=12, pady=(0, 4))
        self._tts_progress_t0: float | None = None
        self._tts_progress_done = 0
        self._tts_progress_total = 0
        self._tts_progress_phase = ""

        voice_play_row = ctk.CTkFrame(tts, fg_color="transparent")
        voice_play_row.grid(row=19, column=0, sticky="ew", padx=12, pady=(0, 4))
        voice_play_row.grid_columnconfigure((0, 1), weight=1)
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
        self._play_voice_btn.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self._stop_voice_btn = ctk.CTkButton(
            voice_play_row,
            text="■  Stop",
            height=30,
            fg_color="transparent",
            border_width=1,
            border_color=_BORDER,
            text_color=_TEXT,
            hover_color=_CARD_HOVER,
            font=ctk.CTkFont(size=12),
            command=self._stop_voice_playback,
            state="disabled",
        )
        self._stop_voice_btn.grid(row=0, column=1, sticky="ew", padx=(4, 0))
        self._voice_play_proc: subprocess.Popen | None = None
        self._voice_play_t0: float | None = None
        self._voice_play_duration = 0.0
        self._voice_play_paused = False
        self._voice_play_paused_at = 0.0
        self._voice_play_path: Path | None = None
        self._tts_job_active = False
        self._tts_cancel_requested = False

        self.voice_play_progress = ctk.CTkProgressBar(
            tts,
            height=8,
            progress_color=_ACCENT,
            fg_color=_BORDER,
            corner_radius=4,
        )
        self.voice_play_progress.grid(row=20, column=0, sticky="ew", padx=12, pady=(0, 2))
        self.voice_play_progress.set(0)
        self.voice_play_progress_var = ctk.StringVar(value="")
        self.voice_play_progress_label = ctk.CTkLabel(
            tts,
            textvariable=self.voice_play_progress_var,
            font=ctk.CTkFont(size=11),
            text_color=_MUTED,
            anchor="w",
        )
        self.voice_play_progress_label.grid(row=21, column=0, sticky="ew", padx=12, pady=(0, 4))

        self._tts_privacy_label = ctk.CTkLabel(
            tts, text="Local voice cloning — audio stays on this computer.",
            font=ctk.CTkFont(size=11), text_color=_MUTED, justify="left", anchor="w",
            wraplength=280,
        )
        self._tts_privacy_label.grid(row=22, column=0, sticky="ew", padx=12, pady=(0, 10))
        self._init_voice_library()
        self._refresh_tts_status()
        self._refresh_voice_playback_buttons()
        # Re-validate Qwen completeness after the window is up (partial downloads, etc.).
        self.after(250, self._refresh_tts_status)

        self._path_row(3, "Voiceover Audio (USED FOR VIDEO)", self.audio_var, self._browse_audio)
        self.voiceover_active_var = ctk.StringVar(value="Video has no voiceover yet.")
        self._voiceover_active_label = ctk.CTkLabel(
            scroll,
            textvariable=self.voiceover_active_var,
            font=ctk.CTkFont(size=11),
            text_color=_ACCENT,
            wraplength=280,
            justify="left",
            anchor="w",
        )
        self._voiceover_active_label.grid(row=4, column=0, sticky="ew", padx=28, pady=(2, 0))
        self._path_row(5, "Background Music (optional)", self.bg_var, self._browse_bg, clearable=True)
        self._path_row(6, "Final video (this project)", self.output_var, self._browse_output)
        # Output path is project-managed — keep the widget for binding, hide it.
        try:
            self._scroll.grid_slaves(row=6, column=0)[0].grid_remove()
        except (IndexError, Exception):
            pass

        # Options row (Whisper / captions live in Settings — hidden on the main screen)
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

        # Bottom bar: one primary action
        bottom = ctk.CTkFrame(left, fg_color=_PANEL, corner_radius=0)
        bottom.grid(row=2, column=0, sticky="ew")
        bottom.grid_columnconfigure(0, weight=1)

        ctk.CTkFrame(bottom, fg_color=_BORDER, height=1, corner_radius=0).grid(
            row=0, column=0, sticky="ew"
        )
        ctk.CTkLabel(
            bottom, textvariable=self.hint_var, font=ctk.CTkFont(size=11),
            text_color=_MUTED, wraplength=280, justify="left",
        ).grid(row=1, column=0, sticky="w", padx=16, pady=(8, 0))

        cta_row = ctk.CTkFrame(bottom, fg_color="transparent")
        cta_row.grid(row=2, column=0, sticky="ew", padx=16, pady=(6, 12))
        cta_row.grid_columnconfigure(0, weight=1)

        self.generate_btn = ctk.CTkButton(
            cta_row,
            text="Generate Assets",
            height=40,
            fg_color=_ACCENT,
            hover_color=_ACCENT_HOV,
            text_color=_ACCENT_DARK,
            font=ctk.CTkFont(size=14, weight="bold"),
            corner_radius=6,
            command=self._on_generate,
        )
        self.generate_btn.grid(row=0, column=0, sticky="ew")

        self.cancel_btn = ctk.CTkButton(
            cta_row,
            text="Cancel",
            width=90,
            height=40,
            fg_color="transparent",
            border_width=1,
            border_color=_DANGER,
            text_color=_DANGER,
            hover_color=_DANGER_BG,
            font=ctk.CTkFont(size=13, weight="bold"),
            corner_radius=6,
            command=self._on_cancel,
        )

        # ── Right panel (scenes) ────────────────────────────────────────
        right = ctk.CTkFrame(self, fg_color=_PANEL_ALT, corner_radius=0)
        right.grid(row=1, column=1, sticky="nsew")
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(1, weight=1)
        self._right_panel = right

        act_header = ctk.CTkFrame(right, fg_color="transparent")
        act_header.grid(row=0, column=0, sticky="ew", padx=16, pady=(10, 0))
        act_header.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            act_header, text="ASSETS  ·  REVIEW",
            font=ctk.CTkFont(size=11, weight="bold"), text_color=_MUTED,
        ).grid(row=0, column=0, sticky="w")
        self.scenes_summary_var = ctk.StringVar(value="No visual plan yet")
        ctk.CTkLabel(
            act_header, textvariable=self.scenes_summary_var,
            font=ctk.CTkFont(size=12, weight="bold"), text_color=_TEXT,
        ).grid(row=0, column=1, sticky="w", padx=10)
        self.goto_error_btn = ctk.CTkButton(
            act_header, text="Go to Error", width=100, height=26,
            fg_color=_WARNING, hover_color="#D97706", text_color="#0B0D10",
            font=ctk.CTkFont(size=11, weight="bold"), corner_radius=4,
            command=self._go_to_error,
        )
        self.goto_error_btn.grid(row=0, column=2, sticky="e", padx=(0, 6))
        self.cleanup_assets_btn = ctk.CTkButton(
            act_header, text="Cleanup", width=150, height=26,
            fg_color="transparent", border_width=1, border_color=_BORDER,
            text_color=_MUTED, hover_color=_CARD_HOVER, font=ctk.CTkFont(size=11),
            command=self._on_cleanup_downloaded_assets,
            state="disabled",
        )
        self.cleanup_assets_btn.grid(row=0, column=3, sticky="e", padx=(0, 6))
        self.log_toggle_btn = ctk.CTkButton(
            act_header, text="Activity ▸", width=90, height=26,
            fg_color="transparent", border_width=1, border_color=_BORDER,
            text_color=_MUTED, hover_color=_CARD_HOVER, font=ctk.CTkFont(size=11),
            command=self._toggle_activity_log,
        )
        self.log_toggle_btn.grid(row=0, column=4, sticky="e")

        # ── Scenes ────────────────────────────────────────────────────────
        scenes_wrap = ctk.CTkFrame(right, fg_color=_CARD, corner_radius=6, border_width=1, border_color=_BORDER)
        scenes_wrap.grid(row=1, column=0, sticky="nsew", padx=16, pady=(8, 0))
        scenes_wrap.grid_columnconfigure(0, weight=1)
        scenes_wrap.grid_rowconfigure(4, weight=1)

        prod_panel = ctk.CTkFrame(scenes_wrap, fg_color=_PANEL, corner_radius=6, border_width=1, border_color=_BORDER)
        prod_panel.pack(fill="x", padx=12, pady=(10, 6))
        ctk.CTkLabel(
            prod_panel, text="VIDEO GENERATION", font=ctk.CTkFont(size=10, weight="bold"),
            text_color=_MUTED, anchor="w",
        ).pack(fill="x", padx=10, pady=(8, 2))
        stats_row = ctk.CTkFrame(prod_panel, fg_color="transparent")
        stats_row.pack(fill="x", padx=10, pady=(0, 8))
        ctk.CTkLabel(
            stats_row, textvariable=self.prod_ready_var,
            font=ctk.CTkFont(size=14, weight="bold"), text_color=_TEXT, anchor="w",
        ).pack(side="left", padx=(0, 12))
        ctk.CTkLabel(
            stats_row, textvariable=self.prod_processing_var,
            font=ctk.CTkFont(size=11, weight="bold"), text_color=_PROCESSING, anchor="w",
        ).pack(side="left", padx=(0, 10))
        ctk.CTkLabel(
            stats_row, textvariable=self.prod_queued_var,
            font=ctk.CTkFont(size=11), text_color=_QUEUED, anchor="w",
        ).pack(side="left", padx=(0, 10))
        ctk.CTkLabel(
            stats_row, textvariable=self.prod_needs_var,
            font=ctk.CTkFont(size=11, weight="bold"), text_color=_WARNING, anchor="w",
        ).pack(side="left")
        ctk.CTkLabel(
            prod_panel, textvariable=self.prod_mix_var,
            font=ctk.CTkFont(size=11), text_color=_MUTED, anchor="w",
            wraplength=720, justify="left",
        ).pack(fill="x", padx=10, pady=(0, 8))

        qa_health_row = ctk.CTkFrame(scenes_wrap, fg_color="transparent")
        qa_health_row.pack(fill="x", padx=12, pady=(0, 0))
        self.qa_health_var = ctk.StringVar(value="")
        ctk.CTkLabel(
            qa_health_row, textvariable=self.qa_health_var,
            font=ctk.CTkFont(size=12), text_color=_MUTED, anchor="w",
        ).pack(side="left")
        self.prev_error_btn = ctk.CTkButton(
            qa_health_row, text="←", width=32, height=24,
            fg_color="transparent", border_width=1, border_color=_BORDER,
            text_color=_ACCENT, hover_color=_ACCENT_SEL, font=ctk.CTkFont(size=12),
            corner_radius=4, command=self._prev_error,
        )
        self.prev_error_btn.pack(side="right")
        self.error_pos_var = ctk.StringVar(value="0 / 0")
        ctk.CTkLabel(
            qa_health_row, textvariable=self.error_pos_var, font=ctk.CTkFont(size=11), text_color=_MUTED, width=48,
        ).pack(side="right", padx=4)
        self.next_error_btn = ctk.CTkButton(
            qa_health_row, text="→", width=32, height=24,
            fg_color="transparent", border_width=1, border_color=_BORDER,
            text_color=_ACCENT, hover_color=_ACCENT_SEL, font=ctk.CTkFont(size=10),
            corner_radius=4, command=self._next_error,
        )
        self.next_error_btn.pack(side="right")

        qa_filter = ctk.CTkFrame(scenes_wrap, fg_color="transparent")
        qa_filter.pack(fill="x", padx=12, pady=(4, 4))
        self.scene_search_var = ctk.StringVar(value="")
        self.scene_search_entry = ctk.CTkEntry(
            qa_filter, textvariable=self.scene_search_var, placeholder_text="Search # / narration / status",
            height=26, border_color=_BORDER, fg_color=_BG,
        )
        self.scene_search_entry.pack(side="left", fill="x", expand=True)
        self.scene_search_var.trace_add("write", lambda *_: self._apply_scene_filter())

        self.qa_bulk_progress_var = ctk.StringVar(value="")
        ctk.CTkLabel(
            scenes_wrap, textvariable=self.qa_bulk_progress_var,
            font=ctk.CTkFont(size=11), text_color=_COPPER, anchor="w",
        ).pack(fill="x", padx=12)

        self._scenes_list = ctk.CTkScrollableFrame(
            scenes_wrap, fg_color="transparent", height=280,
            scrollbar_button_color=_BORDER, scrollbar_button_hover_color=_ACCENT,
        )
        self._scenes_list.pack(fill="both", expand=True, padx=8, pady=(0, 4))
        self._scenes_list.grid_columnconfigure(0, weight=1)

        details_col = ctk.CTkFrame(scenes_wrap, fg_color=_BG, corner_radius=4, border_width=1, border_color=_BORDER)
        details_col.pack(fill="x", padx=8, pady=(0, 8))
        ctk.CTkLabel(
            details_col, text="SELECTED SCENE", font=ctk.CTkFont(size=11, weight="bold"), text_color=_MUTED, anchor="w",
        ).pack(fill="x", padx=8, pady=(6, 0))
        self.details_text_var = ctk.StringVar(value="Select a scene to inspect status and recover.")
        ctk.CTkLabel(
            details_col, textvariable=self.details_text_var, font=ctk.CTkFont(size=11),
            text_color=_TEXT, anchor="nw", justify="left", wraplength=520,
        ).pack(fill="both", expand=True, padx=8, pady=(2, 4))
        details_actions = ctk.CTkFrame(details_col, fg_color="transparent")
        details_actions.pack(fill="x", padx=8, pady=(0, 6))
        self.details_retry_btn = ctk.CTkButton(
            details_actions, text="Retry", width=70, height=24,
            font=ctk.CTkFont(size=11, weight="bold"), command=lambda: self._details_action("retry"),
        )
        self.details_retry_btn.pack(side="left", padx=(0, 4))
        self.details_alt_btn = ctk.CTkButton(
            details_actions, text="Alternative", width=96, height=24,
            font=ctk.CTkFont(size=11, weight="bold"), command=lambda: self._details_action("alternative"),
        )
        self.details_alt_btn.pack(side="left", padx=(0, 4))
        self.details_local_btn = ctk.CTkButton(
            details_actions, text="Add local clip", width=110, height=24,
            font=ctk.CTkFont(size=11, weight="bold"), command=lambda: self._details_action("local_clip"),
        )
        self.details_local_btn.pack(side="left", padx=(0, 4))
        self.details_skip_btn = ctk.CTkButton(
            details_actions, text="Skip", width=64, height=24,
            fg_color="transparent", border_width=1, border_color=_BORDER,
            text_color=_DANGER, font=ctk.CTkFont(size=11, weight="bold"),
            command=lambda: self._details_action("skip"),
        )
        self.details_skip_btn.pack(side="left")
        self.details_source_btn = ctk.CTkButton(
            details_actions, text="Change Source", width=110, height=24,
            fg_color="transparent", border_width=1, border_color=_BORDER,
            text_color=_ACCENT, font=ctk.CTkFont(size=11),
            command=lambda: self._change_source_for_focused(),
        )
        self.details_source_btn.pack(side="left", padx=(8, 0))
        self.details_stop_btn = ctk.CTkButton(
            details_actions, text="Stop", width=64, height=24,
            fg_color="transparent", border_width=1, border_color=_DANGER,
            text_color=_DANGER, font=ctk.CTkFont(size=11, weight="bold"),
            command=lambda: self._details_action("cancel"),
        )
        self.details_stop_btn.pack(side="left", padx=(8, 0))
        self.details_stop_btn.configure(state="disabled")
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
        self.issues_header_var = ctk.StringVar(value="No issues")
        ctk.CTkLabel(
            self._issues_drawer, textvariable=self.issues_header_var,
            font=ctk.CTkFont(size=11), text_color=_DANGER, anchor="w",
        ).pack(fill="x", padx=12)
        self._issues_list = ctk.CTkScrollableFrame(
            self._issues_drawer, fg_color="transparent", height=120,
            scrollbar_button_color=_BORDER, scrollbar_button_hover_color=_ACCENT,
        )
        self._issues_list.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        # Hidden until the user opens Issues from the status bar.

        self._scene_row_widgets: dict[str, dict] = {}
        self._scene_rows: list[SceneRow] = []
        self._asset_results: dict[str, object] = {}
        self._busy_scenes: set[str] = set()
        self._pending_source_after_cancel: dict[str, str] = {}
        self._scene_started: dict[str, float] = {}
        self._retry_queue: list[SceneRow] = []
        self._retry_pumping = False
        self._qa = SceneQAState()
        self._hydrated_skipped: set[str] = set()
        self._recovery_queue: list[tuple[str, SceneRow]] = []
        self._recovery_total = 0
        self._recovery_done = 0
        self.retry_all_btn = self.retry_failed_btn

        # Log textbox — takes remaining height until preview appears
        self.log_box = ctk.CTkTextbox(
            right,
            wrap="word",
            font=ctk.CTkFont(family="Menlo", size=12),
            fg_color=_CARD,
            text_color="#334155",
            border_width=1,
            border_color=_BORDER,
            corner_radius=6,
            scrollbar_button_color=_BORDER,
            scrollbar_button_hover_color=_ACCENT,
        )
        self.log_box.configure(state="disabled")
        # Collapsed by default — Activity toggle reveals it.

        # ── Preview panel (hidden until generation succeeds) ──────────────
        self._preview_panel = ctk.CTkFrame(right, fg_color=_CARD, corner_radius=6)
        # Not gridded yet — revealed by _show_preview()

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

        # Thumbnail label — filled by _show_preview()
        self._thumb_label = ctk.CTkLabel(
            self._preview_panel,
            text="",
            fg_color="transparent",
        )
        self._thumb_label.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        self._last_output: str | None = None  # track for "Open" / "Open Folder"

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
    ) -> None:
        """Styled input card inside the scrollable left panel."""
        host = parent if parent is not None else self._scroll
        pad_x = 0 if parent is not None else 16
        card = ctk.CTkFrame(host, fg_color=_CARD, corner_radius=6)
        card.grid(row=row, column=0, sticky="ew", padx=pad_x, pady=(10, 0))
        card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            card,
            text=label.upper(),
            font=ctk.CTkFont(size=9, weight="bold"),
            text_color=_MUTED,
            anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(8, 2), columnspan=3)

        entry = ctk.CTkEntry(
            card,
            textvariable=var,
            height=34,
            fg_color=_BG,
            border_color=_BORDER,
            border_width=1,
            text_color=_TEXT,
            placeholder_text_color=_MUTED,
            corner_radius=4,
        )
        entry.grid(row=1, column=0, sticky="ew", padx=(10, 6), pady=(0, 10))

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
        ).grid(row=1, column=1, sticky="e", padx=(0, 4 if clearable else 10), pady=(0, 10))

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
            ).grid(row=1, column=2, sticky="e", padx=(0, 10), pady=(0, 10))

    def _toggle_tts_advanced(self) -> None:
        return

    def _init_voice_library(self) -> None:
        legacy = self._settings.get("qwen_ref_audio") or ""
        if legacy and not list_voices():
            migrate_legacy_reference(legacy)
        self._refresh_voice_library_ui()
        preferred = (self._settings.get("qwen_selected_voice_id") or "").strip()
        if not preferred and self._workspace is not None:
            preferred = self._workspace.voice_id()
        if not preferred:
            default = get_default_voice()
            preferred = default.id if default else ""
        if preferred:
            self._select_voice_by_id(preferred, persist=False)

    def _voice_menu_label(self, profile: VoiceProfile) -> str:
        parts = [profile.name]
        if profile.is_default:
            parts.append("DEFAULT")
        if profile.status == "ready":
            parts.append("READY")
        elif profile.status == "building":
            parts.append("BUILDING")
        else:
            parts.append("NEEDS REBUILD")
        return " · ".join(parts)

    def _refresh_voice_library_ui(self) -> None:
        profiles = list_voices()
        self._tts_voice_profiles = {self._voice_menu_label(p): p for p in profiles}
        labels = list(self._tts_voice_profiles.keys()) or ["(none)"]
        current = self.tts_selected_voice_var.get()
        self._tts_voice_menu.configure(values=labels)
        if current in labels:
            self.tts_selected_voice_var.set(current)
        elif profiles:
            default = next((p for p in profiles if p.is_default), profiles[0])
            self._select_voice_by_id(default.id, persist=False)
        else:
            self.tts_selected_voice_var.set("(none)")
            self.tts_voice_detail_var.set("Create or select a saved voice.")
        profile = self._selected_voice_profile()
        if profile is not None:
            self.tts_voice_detail_var.set(self._format_voice_detail(profile))

    def _selected_voice_profile(self) -> VoiceProfile | None:
        label = (self.tts_selected_voice_var.get() or "").strip()
        if label == "(none)":
            return None
        return self._tts_voice_profiles.get(label)

    def _select_voice_by_id(self, voice_id: str, *, persist: bool = True) -> None:
        profile = get_voice(voice_id)
        if profile is None:
            return
        label = self._voice_menu_label(profile)
        self._tts_voice_profiles[label] = profile
        self.tts_selected_voice_var.set(label)
        self.tts_voice_detail_var.set(self._format_voice_detail(profile))
        if persist:
            self._settings["qwen_selected_voice_id"] = profile.id
            save_settings(self._settings)
            if self._workspace is not None:
                self._workspace.set_voice_id(profile.id)

    def _format_voice_detail(self, profile: VoiceProfile) -> str:
        model_label = "Qwen 1.7B"
        if profile.status == "ready":
            status = "✓ VOICE READY"
        elif profile.status == "building":
            status = "Building voice profile…"
        else:
            status = "⚠ VOICE PROFILE NEEDS REBUILD"
        default = " · DEFAULT" if profile.is_default else ""
        return f"{profile.name}{default}\n{status} · {model_label}"

    def _on_voice_selected(self, _label: str) -> None:
        profile = self._selected_voice_profile()
        if profile is None:
            self.tts_voice_detail_var.set("Create or select a saved voice.")
            return
        self.tts_voice_detail_var.set(self._format_voice_detail(profile))
        self._settings["qwen_selected_voice_id"] = profile.id
        save_settings(self._settings)
        if self._workspace is not None:
            self._workspace.set_voice_id(profile.id)

    def _refresh_tts_status(self) -> None:
        if getattr(self, "_qwen_download_active", False):
            return
        # Always re-check files on launch / focus — ready only at 100% model+runtime.
        ok, message = qwen_install_status_message()
        self.tts_status_var.set(message)
        self._apply_qwen_ready_ui(ok)

    def _apply_qwen_ready_ui(self, ready: bool) -> None:
        downloading = getattr(self, "_qwen_download_active", False)
        dl = getattr(self, "_tts_download_btn", None)
        dl_row = getattr(self, "_tts_dl_row", None)
        cancel_btn = getattr(self, "_tts_download_cancel_btn", None)
        if downloading:
            if dl is not None:
                dl.grid_remove()
            if dl_row is not None:
                dl_row.grid()
            if cancel_btn is not None:
                cancel_btn.configure(state="normal", text="✕")
        else:
            if dl_row is not None:
                dl_row.grid_remove()
            if dl is not None:
                if ready:
                    dl.grid_remove()
                else:
                    dl.grid()
                    dl.configure(state="normal", text="Download")
        voice_state = "disabled" if (downloading or not ready) else "normal"
        if getattr(self, "tts_create_btn", None) is not None:
            self.tts_create_btn.configure(state=voice_state)
        if getattr(self, "tts_btn", None) is not None and not getattr(self, "_tts_job_active", False):
            self.tts_btn.configure(state=voice_state)
        if getattr(self, "top_voice_btn", None) is not None and not getattr(self, "_tts_job_active", False):
            self.top_voice_btn.configure(state=voice_state)

    def _set_qwen_dl_progress(self, fraction: float) -> None:
        bar = getattr(self, "_tts_dl_progress", None)
        if bar is None:
            return
        try:
            bar.set(max(0.0, min(1.0, float(fraction))))
        except Exception:
            pass

    def _on_cancel_qwen_download(self) -> None:
        if not getattr(self, "_qwen_download_active", False):
            return
        self._qwen_download_cancel = True
        cancel_btn = getattr(self, "_tts_download_cancel_btn", None)
        if cancel_btn is not None:
            cancel_btn.configure(state="disabled", text="…")
        self.tts_status_var.set("Cancelling Qwen download…")
        self.status_var.set("Cancelling Qwen download…")
        self._append_log("[TTS] Cancel requested for Qwen download\n")

    def _on_download_qwen(self) -> None:
        if getattr(self, "_qwen_download_active", False):
            return
        if getattr(self, "_tts_job_active", False):
            messagebox.showinfo(
                "Voice busy",
                "Finish the current voice job before downloading Qwen.",
            )
            return
        self._qwen_download_active = True
        self._qwen_download_cancel = False
        self._set_qwen_dl_progress(0.02)
        self._apply_qwen_ready_ui(ready=False)
        self.tts_status_var.set("Downloading Qwen…")
        self.status_var.set("Downloading Qwen voice engine…")
        self._append_log("\n[TTS] Starting Qwen download (runtime + model)…\n")

        def work() -> None:
            try:
                def on_status(msg: str) -> None:
                    self._ui_queue.put(("qwen_dl_status", msg))

                def on_progress(frac: float) -> None:
                    self._ui_queue.put(("qwen_dl_progress", float(frac)))

                provision_qwen(
                    status=on_status,
                    progress=on_progress,
                    should_stop=lambda: bool(getattr(self, "_qwen_download_cancel", False)),
                )
                self._ui_queue.put(("qwen_dl_done", None))
            except Exception as exc:
                self._ui_queue.put(("qwen_dl_error", friendly_provision_error(exc)))

        threading.Thread(target=work, daemon=True).start()

    def _on_qwen_download_status(self, message: str) -> None:
        short = (message or "").split("\n", 1)[0]
        self.tts_status_var.set(short)
        self.status_var.set(short)
        self._append_log(f"[TTS] {short}\n")

    def _on_qwen_download_progress(self, frac: float) -> None:
        pct = max(0, min(100, int(round(float(frac) * 100))))
        self._set_qwen_dl_progress(float(frac))
        self.tts_status_var.set(f"Downloading Qwen… {pct}%")

    def _on_qwen_download_done(self) -> None:
        self._qwen_download_active = False
        self._qwen_download_cancel = False
        self._set_qwen_dl_progress(1.0)
        self._append_log("[TTS] ✓ Qwen download complete\n")
        self.status_var.set("Qwen voice engine ready")
        self._refresh_tts_status()
        messagebox.showinfo(
            "Qwen ready",
            "Voice cloning is ready.\n\nYou can Create Voice and Generate Narration.",
        )

    def _on_qwen_download_error(self, message: str) -> None:
        self._qwen_download_active = False
        self._qwen_download_cancel = False
        self._set_qwen_dl_progress(0.0)
        cancelled = "cancel" in (message or "").lower()
        if cancelled:
            self._append_log(f"[TTS] {message}\n")
            self.status_var.set("Qwen download cancelled")
        else:
            self._append_log(f"[TTS] Qwen download failed: {message}\n")
            self.status_var.set("Qwen download failed")
        self._refresh_tts_status()
        if cancelled:
            messagebox.showinfo("Qwen download", message or "Qwen download cancelled.")
        else:
            messagebox.showerror("Qwen download", message)

    def _qwen_model_folder(self) -> Path:
        """Preferred local install folder for the 1.7B Base clone model."""
        preferred = Path.home() / ".videogen" / "qwen3-tts" / MODEL_DIR_NAME
        for path in candidate_model_dirs(CLONE_MODEL_ID):
            if path.is_dir():
                return path
        return preferred

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

    def _open_qwen_model_folder(self) -> None:
        """Reveal the Qwen voice-clone model directory in the system file browser."""
        self._open_folder_path(self._qwen_model_folder())

    def _browse_create_reference_audio(self) -> None:
        path = filedialog.askopenfilename(
            title="Select reference voice recording",
            filetypes=[
                ("Audio", "*.wav *.mp3 *.m4a *.flac"),
                ("WAV", "*.wav"),
                ("MP3", "*.mp3"),
                ("M4A", "*.m4a"),
                ("FLAC", "*.flac"),
                ("All files", "*.*"),
            ],
            initialdir=str(_browse_start_dir()),
        )
        if path:
            self._tts_create_ref_path = Path(path)
            self.tts_create_ref_var.set(path)

    def _create_transcript_text(self) -> str:
        raw = self.tts_create_transcript_box.get("1.0", "end").strip()
        placeholder = "Enter the exact words spoken in the reference recording."
        if raw == placeholder:
            return ""
        return raw

    def _tts_narration_text(self) -> str:
        box = getattr(self, "tts_narration_box", None)
        if box is None:
            return ""
        raw = box.get("1.0", "end").strip()
        if not raw or raw == VOICE_NARRATION_PLACEHOLDER:
            return ""
        return raw

    def _set_tts_narration_text(self, text: str) -> None:
        box = getattr(self, "tts_narration_box", None)
        if box is None:
            return
        box.delete("1.0", "end")
        box.insert("1.0", (text or "").strip() or VOICE_NARRATION_PLACEHOLDER)

    def _tts_narration_focus_in(self, _event=None) -> None:
        box = getattr(self, "tts_narration_box", None)
        if box is None:
            return
        if box.get("1.0", "end").strip() == VOICE_NARRATION_PLACEHOLDER:
            box.delete("1.0", "end")

    def _tts_narration_paste(self, _event=None):
        """Paste via clipboard on idle so large scripts don't freeze the UI thread."""
        box = getattr(self, "tts_narration_box", None)
        if box is None:
            return "break"
        try:
            clip = self.clipboard_get()
        except Exception:
            return "break"
        if not clip:
            return "break"

        def _apply():
            try:
                current = box.get("1.0", "end").strip()
                if current == VOICE_NARRATION_PLACEHOLDER:
                    box.delete("1.0", "end")
                box.insert("insert", clip)
            except Exception:
                pass

        self.after(0, _apply)
        return "break"

    def _begin_tts_job(self, label: str = "Generate Narration") -> bool:
        if getattr(self, "_tts_job_active", False):
            messagebox.showinfo(
                "Voice busy",
                "A voice job is already running.\n\n"
                "Click Stop to cancel it, then try again.",
            )
            return False
        self._tts_job_active = True
        self._tts_cancel_requested = False
        self._set_tts_busy(True, label=label)
        return True

    def _end_tts_job(self, label: str = "Generate Narration") -> None:
        self._tts_job_active = False
        self._tts_cancel_requested = False
        self._set_tts_busy(False, label=label)

    def _force_tts_idle(self, status_label: str = "") -> None:
        """Idempotent UI reset — safe to call from log completion or done handlers."""
        self._tts_job_active = False
        self._tts_cancel_requested = False
        self._restore_tts_generate_btn()
        if getattr(self, "top_voice_btn", None) is not None:
            self.top_voice_btn.configure(state="normal", text="Voice", command=self._on_tts_primary_click)
        self._tts_progress_t0 = None
        self._tts_progress_phase = status_label or ""
        if status_label:
            self._set_tts_progress(1.0, status_label)
        else:
            self._tts_progress_done = 0
            self._tts_progress_total = 0
            self._set_tts_progress(0.0, "")
        self._refresh_voice_playback_buttons()
        # Re-apply Download gating (Create / Generate disabled until Qwen is ready).
        if not getattr(self, "_qwen_download_active", False):
            self._refresh_tts_status()

    def _restore_tts_generate_btn(self) -> None:
        btn = getattr(self, "tts_btn", None)
        if btn is None:
            return
        btn.configure(
            state="normal",
            text="Generate Narration",
            fg_color=_ACCENT,
            hover_color=_ACCENT_HOV,
            text_color=_ACCENT_DARK,
            border_width=0,
            command=self._on_tts_primary_click,
        )

    def _on_tts_primary_click(self) -> None:
        if getattr(self, "_tts_job_active", False):
            self._on_stop_tts_job()
            return
        self._on_generate_narration()

    def _on_stop_tts_job(self) -> None:
        if not getattr(self, "_tts_job_active", False):
            return
        if getattr(self, "_tts_cancel_requested", False):
            return
        self._tts_cancel_requested = True
        btn = getattr(self, "tts_btn", None)
        if btn is not None:
            btn.configure(state="disabled", text="Stopping…")
        top = getattr(self, "top_voice_btn", None)
        if top is not None:
            top.configure(state="disabled", text="…")
        self.status_var.set("Stopping voice job…")
        self._append_log("[TTS] Stop requested — shutting down worker\n")

        def kill() -> None:
            try:
                shutdown_shared_client()
            except Exception:
                pass
            self.after(0, self._tts_stop_finished)

        threading.Thread(target=kill, daemon=True).start()

    def _tts_stop_finished(self) -> None:
        # Failure handler may have already cleared the job after the worker died.
        if getattr(self, "_tts_job_active", False):
            self._force_tts_idle("")
            self.status_var.set("Voice job stopped")
            self._append_log("[TTS] Stopped\n")
            messagebox.showinfo("Voice", "Voice generation was stopped.")

    def _create_voice_profile(self) -> None:
        name = self.tts_create_name_var.get().strip()
        ref_raw = (self.tts_create_ref_var.get() or "").strip()
        ref_path = self._tts_create_ref_path or (Path(ref_raw) if ref_raw else None)
        transcript = self._create_transcript_text()
        if ref_path is None or not ref_path.is_file():
            messagebox.showerror("Create Voice", "Select a reference audio recording first.")
            return
        if not transcript:
            messagebox.showerror(
                "Create Voice",
                "Reference transcript is required.\n\n"
                "Enter only the exact words spoken in the short reference recording "
                "(not the full narration script).",
            )
            return
        if len(transcript) > 600:
            if not messagebox.askyesno(
                "Long reference transcript",
                "The reference transcript looks like a full script.\n\n"
                "For Create Voice, paste only the words spoken in the reference audio.\n"
                "Paste the full narration under Narration Script, then Generate Narration.\n\n"
                "Continue anyway?",
            ):
                return
        if not self._begin_tts_job("+ Create Voice"):
            return
        self.status_var.set(f"Creating voice profile for {name}…")
        self._append_log(f"\n[TTS] Creating voice profile: {name}\n")

        def work():
            profile = None
            try:
                profile = create_voice_profile(name, ref_path, transcript)
                client = get_shared_client(log=lambda line: self._ui_queue.put(("log", line + "\n")))
                client.build_voice_prompt(
                    profile.reference_path,
                    profile.reference_text,
                    profile.prompt_path,
                )
                mark_voice_ready(profile.id)
                self._tts_ui("tts_voice_created", profile.id)
            except TTSError as exc:
                if profile is not None:
                    try:
                        mark_voice_needs_rebuild(profile.id)
                    except Exception:
                        pass
                self._tts_ui("tts_voice_failed", exc.message)
            except Exception as exc:
                if profile is not None:
                    try:
                        mark_voice_needs_rebuild(profile.id)
                    except Exception:
                        pass
                self._tts_ui("tts_voice_failed", str(exc))
            finally:
                self._tts_ui("tts_job_end", None)

        threading.Thread(target=work, daemon=True).start()

    def _voice_created(self, voice_id: str) -> None:
        # Clear busy/Stop state before the dialog so the CTA never looks stuck.
        self._end_tts_job()
        self.status_var.set("Voice saved")
        self._refresh_voice_library_ui()
        self._select_voice_by_id(voice_id)
        self.tts_create_name_var.set("")
        self.tts_create_ref_var.set("")
        self._tts_create_ref_path = None
        messagebox.showinfo("Create Voice", "✓ Voice saved and ready to use.")

    def _voice_create_failed(self, message: str) -> None:
        cancelled = bool(getattr(self, "_tts_cancel_requested", False))
        self._end_tts_job()
        self.status_var.set("Voice job stopped" if cancelled else "Ready")
        self._refresh_voice_library_ui()
        self._append_log(f"[TTS] {message}\n")
        if cancelled:
            return
        messagebox.showerror("Create Voice", message)

    def _require_ready_voice(self, action: str) -> VoiceProfile | None:
        profile = self._selected_voice_profile()
        if profile is None:
            messagebox.showerror("Voice", f"Select a saved voice before you {action}.")
            return None
        profile = refresh_profile_status(profile)
        if profile.status == "needs_rebuild":
            messagebox.showerror(
                "Voice",
                "This voice profile needs to be rebuilt.\n\n"
                "Use Replace to provide reference audio and transcript again.",
            )
            return None
        if profile.status == "building":
            messagebox.showinfo("Voice", "This voice profile is still being created.")
            return None
        if not profile.prompt_path.is_file():
            messagebox.showerror(
                "Voice",
                "Saved voice profile could not be loaded.\n\n"
                "Rebuild the voice or choose another saved voice.",
            )
            return None
        return profile

    def _set_default_voice(self) -> None:
        profile = self._selected_voice_profile()
        if profile is None:
            messagebox.showinfo("Default Voice", "Select a voice from your library first.")
            return
        try:
            set_default_voice(profile.id)
        except TTSError as exc:
            messagebox.showerror("Default Voice", exc.message)
            return
        self._refresh_voice_library_ui()
        self._select_voice_by_id(profile.id, persist=True)

    def _replace_selected_voice(self) -> None:
        profile = self._selected_voice_profile()
        if profile is None:
            messagebox.showinfo("Replace Voice", "Select a voice to replace first.")
            return
        path = filedialog.askopenfilename(
            title=f"Replace reference for {profile.name}",
            filetypes=[
                ("Audio", "*.wav *.mp3 *.m4a *.flac"),
                ("All files", "*.*"),
            ],
            initialdir=str(_browse_start_dir()),
        )
        if not path:
            return
        dialog = ctk.CTkInputDialog(
            text="Enter the exact words spoken in the new reference recording:",
            title=f"Replace {profile.name}",
        )
        transcript = (dialog.get_input() or "").strip()
        if not transcript:
            messagebox.showerror("Replace Voice", "Reference transcript is required.")
            return
        try:
            updated = replace_voice_reference(profile.id, path, transcript)
        except TTSError as exc:
            messagebox.showerror("Replace Voice", exc.message)
            return
        if not self._begin_tts_job("Replace"):
            return
        self.status_var.set(f"Rebuilding voice profile for {updated.name}…")

        def work():
            try:
                client = get_shared_client(log=lambda line: self._ui_queue.put(("log", line + "\n")))
                client.build_voice_prompt(
                    updated.reference_path,
                    updated.reference_text,
                    updated.prompt_path,
                )
                mark_voice_ready(updated.id)
                self._tts_ui("tts_voice_replaced", updated.id)
            except TTSError as exc:
                mark_voice_needs_rebuild(updated.id)
                self._tts_ui("tts_voice_failed", exc.message)
            except Exception as exc:
                mark_voice_needs_rebuild(updated.id)
                self._tts_ui("tts_voice_failed", str(exc))
            finally:
                self._tts_ui("tts_job_end", None)

        threading.Thread(target=work, daemon=True).start()

    def _voice_replaced(self, voice_id: str) -> None:
        self._end_tts_job()
        self.status_var.set("Voice updated")
        self._refresh_voice_library_ui()
        self._select_voice_by_id(voice_id)
        messagebox.showinfo("Replace Voice", "✓ Voice profile updated.")

    def _delete_selected_voice(self) -> None:
        profile = self._selected_voice_profile()
        if profile is None:
            messagebox.showinfo("Delete Voice", "Select a voice to delete first.")
            return
        if not messagebox.askyesno(
            "Delete Voice",
            f"Delete saved voice '{profile.name}'?\n\n"
            "This removes the profile and reference audio. The Qwen model is not deleted.",
        ):
            return
        try:
            delete_voice(profile.id)
        except TTSError as exc:
            messagebox.showerror("Delete Voice", exc.message)
            return
        if self._settings.get("qwen_selected_voice_id") == profile.id:
            self._settings["qwen_selected_voice_id"] = ""
            save_settings(self._settings)
        self._refresh_voice_library_ui()

    def _toggle_issues(self) -> None:
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

    def _change_source_for_focused(self) -> None:
        key = self._qa.focused_key
        if not key:
            return
        scene = next((s for s in self._scene_rows if _scene_key(s.scene_number) == key), None)
        if scene is not None:
            self._change_source_dialog(scene)

    def _sync_primary_cta(self, snap=None) -> None:
        snap = snap or (self._qa_snapshot() if self._scene_rows else None)
        audio_ok = bool(self.audio_var.get().strip()) and Path(self.audio_var.get().strip()).is_file()
        has_csv = bool(self.csv_var.get().strip()) and Path(self.csv_var.get().strip()).is_file()
        if self._running:
            self.stage_var.set("GENERATING")
            self.hint_var.set("Work is in progress. You can cancel asset generation.")
            return
        if self._workspace is None:
            self.stage_var.set("SCRIPT")
            self.hint_var.set("Create a project, then paste a script or import a CSV.")
            self._set_generate_btn(state="disabled", text="New Project first")
            return
        if not has_csv:
            self.stage_var.set("PLAN")
            self.hint_var.set("Paste your script and click Analyze, or import a CSV.")
            self._set_generate_btn(state="disabled", text="Analyze or import CSV")
            return
        if snap is None or snap.total == 0:
            self.stage_var.set("PLAN")
            self.hint_var.set("No visual plan yet. Paste your script and click Analyze Script.")
            self._set_generate_btn(state="disabled", text="Analyze Script")
            return
        if snap.needs_action:
            self.stage_var.set("REVIEW")
            self.hint_var.set("Fix scenes that need attention, then generate remaining assets.")
            self._set_generate_btn(state="normal", text="Generate Assets")
            return
        if not snap.allow_render:
            self.stage_var.set("GENERATE")
            self.hint_var.set("Generate visuals for every scene.")
            self._set_generate_btn(state="normal", text="Generate Assets")
            return
        if not audio_ok:
            self.stage_var.set("VOICE")
            self.hint_var.set("Scenes are ready. Generate narration next.")
            self._set_generate_btn(state="disabled", text="Generate Narration first")
            return
        self.stage_var.set("EXPORT")
        self.hint_var.set("Everything is ready. Render the final video.")
        self._set_generate_btn(state="normal", text="Render Video")

    def _set_generate_btn(self, *, state: str, text: str) -> None:
        """Restore accent styling whenever the primary CTA leaves Stop / busy."""
        if state == "normal":
            self.generate_btn.configure(
                state=state,
                text=text,
                fg_color=_ACCENT,
                hover_color=_ACCENT_HOV,
                text_color=_ACCENT_DARK,
                border_width=0,
            )
        else:
            self.generate_btn.configure(
                state=state,
                text=text,
                fg_color=_BORDER,
                text_color=_MUTED,
                border_width=0,
            )

    def _apply_defaults(self) -> None:
        if DEFAULTS["bg_audio"].is_file():
            self.bg_var.set(str(DEFAULTS["bg_audio"]))
        last_id = (self._settings.get("active_project_id") or "").strip()
        ws = find_project(self._projects_root, last_id) if last_id else None
        if ws is not None:
            self._activate_workspace(ws, persist=False, refresh_menu=True)
        else:
            self._refresh_project_menu()
            self._update_project_indicator()
            self._sync_images_dir()
            self._refresh_scene_preview()

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
        messagebox.showinfo(
            "No project",
            f"Create a New Project before you {action}.\n\n"
            "Each video gets its own folder; retries stay in that folder.",
        )
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
        if persist:
            self._settings["active_project_id"] = ws.project_id
            self._settings["projects_root"] = str(self._projects_root_path())
            save_settings(self._settings)
        self._bind_workspace_paths()
        if refresh_menu:
            self._refresh_project_menu()
        self._update_project_indicator()
        self._refresh_scene_preview()
        self._refresh_cleanup_button()
        vid = ws.voice_id()
        if vid and get_voice(vid) is not None:
            self._select_voice_by_id(vid, persist=False)
        self._load_smart_editing_settings_from_project(ws)

    def _refresh_cleanup_button(self) -> None:
        btn = getattr(self, "cleanup_assets_btn", None)
        if btn is None:
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
        if self._running or getattr(self, "_tts_job_active", False):
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

    def _smart_editing_settings(self) -> SmartEditingSettings:
        intensity = (self.smart_intensity_var.get() or "Medium").strip().lower()
        mode_raw = (self.smart_mode_var.get() or "Smart").strip().lower()
        return SmartEditingSettings(
            text_effects=bool(self.smart_text_effects_var.get()),
            sound_effects=bool(self.smart_sfx_var.get()),
            intensity=intensity,
            mode="automatic" if mode_raw.startswith("auto") else "smart",
        )

    def _smart_editing_settings_dict(self) -> dict:
        s = self._smart_editing_settings()
        return {
            "text_effects": s.text_effects,
            "sound_effects": s.sound_effects,
            "intensity": s.intensity,
            "mode": s.mode,
        }

    def _persist_smart_editing_settings(self) -> None:
        payload = self._smart_editing_settings_dict()
        self._settings["smart_text_effects"] = payload["text_effects"]
        self._settings["smart_sound_effects"] = payload["sound_effects"]
        self._settings["smart_intensity"] = payload["intensity"]
        self._settings["smart_mode"] = payload["mode"]
        save_settings(self._settings)
        if self._workspace is not None:
            self._workspace.set_smart_editing_settings(payload)

    def _load_smart_editing_settings_from_project(self, ws) -> None:
        data = ws.smart_editing_settings()
        self.smart_text_effects_var.set(bool(data.get("text_effects", True)))
        self.smart_sfx_var.set(bool(data.get("sound_effects", True)))
        intensity = str(data.get("intensity") or "medium").title()
        self.smart_intensity_var.set(intensity if intensity in {"Low", "Medium", "High"} else "Medium")
        mode = str(data.get("mode") or "smart").title()
        self.smart_mode_var.set("Automatic" if mode.lower().startswith("auto") else "Smart")

    def _bind_workspace_paths(self) -> None:
        ws = self._workspace
        if ws is None:
            return
        ws.ensure_dirs()
        self.images_var.set(str(ws.assets_dir))
        if ws.csv_path.is_file():
            self.csv_var.set(str(ws.csv_path))
        elif not self.csv_var.get().strip() or not path_is_inside(Path(self.csv_var.get()), ws.root):
            self.csv_var.set(str(ws.csv_path))
        found = ws.find_voiceover_audio()
        if found is not None:
            src = ws.active_voiceover_source() or (
                "tts"
                if found.name.lower() in ("narration.wav", "narration.mp3")
                or found.name.lower().startswith("voiceover_qwen")
                else "imported"
            )
            self._set_active_voiceover(found, source=src)
        else:
            # Keep a project-owned destination even before TTS / manual upload.
            current = self.audio_var.get().strip()
            if not current or not path_is_inside(Path(current), ws.root) or not Path(current).is_file():
                self.audio_var.set(str(ws.audio_path))
            self._refresh_voiceover_active_label()
            self._bind_voice_player_to(None)
        self.output_var.set(str(ws.next_final_path()))
        if ws.script_path.is_file() and self._script_mode_is_ai():
            text = ws.script_path.read_text(encoding="utf-8")
            self.script_box.delete("1.0", "end")
            self.script_box.insert("1.0", text)
            if not self._tts_narration_text():
                self._set_tts_narration_text(text)
        elif ws.script_path.is_file() and not self._tts_narration_text():
            try:
                self._set_tts_narration_text(ws.script_path.read_text(encoding="utf-8"))
            except OSError:
                pass
        self._sync_primary_cta()
        self._refresh_voice_playback_buttons()

    def _refresh_project_menu(self) -> None:
        projects = list_projects(self._projects_root_path())
        self._project_labels = {}
        labels = []
        for p in projects:
            label = f"#{p.display_seq()}  {p.title}"
            self._project_labels[label] = p.project_id
            labels.append(label)
        special = ["＋ New Project", "Open Project…"]
        self._project_menu_lock = True
        try:
            values = special + (labels or ["(none)"])
            self._project_menu.configure(values=values)
            if self._workspace is not None:
                current = None
                for lab, pid in self._project_labels.items():
                    if pid == self._workspace.project_id:
                        current = lab
                        break
                self.project_menu_var.set(current or values[0])
            else:
                self.project_menu_var.set("(none)" if not labels else labels[-1])
        finally:
            self._project_menu_lock = False

    def _update_project_indicator(self) -> None:
        ws = self._workspace
        if ws is None:
            self.current_project_title_var.set("No project")
            self.current_project_meta_var.set("Click New Project to start a video")
            return
        extra = ""
        snap = getattr(self, "_qa", None)
        if snap is not None and self._scene_rows:
            try:
                q = self._qa_snapshot()
                extra = f"  ·  {q.header}"
            except Exception:
                extra = ""
        self.current_project_title_var.set(ws.title)
        self.current_project_meta_var.set(f"#{ws.display_seq()}  ·  {ws.project_id}")

    def _mirror_result_into_workspace(self, result) -> None:
        ws = self._workspace
        if ws is None or result is None or not getattr(result, "ok", False):
            return
        path = getattr(result, "path", None)
        if path is None:
            return
        source = getattr(result, "source", None)
        name = getattr(source, "value", None) or str(source or "")
        ws.mirror_provider_asset(name, getattr(result, "scene_number", ""), Path(path))
        ws.sync_state_copies()

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

    def _script_mode_is_ai(self) -> bool:
        return getattr(self, "_mode_seg", None) is not None and self._mode_seg.get() == "AI Script"

    def _refresh_gemini_status(self) -> None:
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
        if value == "AI Script":
            if not self._manual_csv_backup:
                self._manual_csv_backup = self.csv_var.get()
            self._csv_block.grid_remove()
            self._ai_block.grid(row=1, column=0, sticky="ew", padx=16, pady=(10, 0))
            self._refresh_gemini_status()
            if self._visual_plan is not None:
                self._render_scene_rows()
        else:
            self._ai_block.grid_remove()
            self._csv_block.grid(row=1, column=0, sticky="ew", padx=16)
            if self._manual_csv_backup:
                self.csv_var.set(self._manual_csv_backup)
            self._visual_plan = None
            self._refresh_scene_preview()

    def _on_analyze_script(self) -> None:
        if not self._require_workspace("analyze a script"):
            return
        script = self.script_box.get("1.0", "end").strip()
        if not script or script == "Paste your narration script here...":
            messagebox.showerror("AI Script", "Paste your complete narration script first.")
            return
        settings = {"gemini_api_key": self.gemini_key_var.get().strip()}
        if not gemini_configured(settings):
            messagebox.showerror("AI Script", MISSING_GEMINI_KEY)
            return
        self.analyze_btn.configure(state="disabled", text="Analyzing…")
        if getattr(self, "top_analyze_btn", None) is not None:
            self.top_analyze_btn.configure(state="disabled")
        self.status_var.set("Analyzing script…")

        def work():
            try:
                from visual_director import VisualDirector

                plan = VisualDirector(settings=settings).plan(script)
                self.after(0, lambda: self._apply_ai_plan(plan))
            except Exception as exc:
                msg = str(exc)
                self.after(0, lambda m=msg: self._analyze_failed(m))

        threading.Thread(target=work, daemon=True).start()

    def _analyze_failed(self, message: str) -> None:
        self.analyze_btn.configure(state="normal", text="Analyze Script")
        if getattr(self, "top_analyze_btn", None) is not None:
            self.top_analyze_btn.configure(state="normal")
        self.status_var.set("Ready")
        self._refresh_gemini_status()
        messagebox.showerror("AI Script", message)

    def _apply_ai_plan(self, plan) -> None:
        self._visual_plan = plan
        if self._workspace is None:
            self._sync_images_dir()
            csv_path = Path(self.images_var.get()).resolve().parent / "ai_visual_plan.csv"
        else:
            script = self.script_box.get("1.0", "end").strip()
            if script and script != "Paste your narration script here...":
                self._workspace.save_script(script)
            self._workspace.save_visual_plan_json(plan.to_dict())
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
        self._append_log("\n[AI] Visual plan ready — review scenes, then Generate Video.\n")
        self._append_log(plan.format_preview() + "\n")

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
        name = p.name.lower()
        meta_src = ""
        if self._workspace is not None:
            meta_src = self._workspace.active_voiceover_source()
        if meta_src in ("tts", "cloned"):
            return "cloned TTS"
        if meta_src in ("imported", "file", "manual"):
            return "imported file"
        if name in ("narration.wav", "narration.mp3") or name.startswith("voiceover_qwen"):
            return "cloned TTS"
        return "imported file"

    def _refresh_voiceover_active_label(self) -> None:
        var = getattr(self, "voiceover_active_var", None)
        if var is None:
            return
        raw = self.audio_var.get().strip()
        path = Path(raw) if raw else None
        if path is None or not path.is_file():
            var.set("Video has no voiceover yet.")
            return
        src = self._voiceover_source_label(path)
        var.set(f"Video will use: {path.name}  ·  {src}")

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
        new_src = "cloned TTS" if source in ("tts", "cloned") else "imported file"
        return bool(
            messagebox.askyesno(
                "Switch voiceover?",
                "Only ONE voiceover is used for the video.\n\n"
                f"Currently active:\n  {cur.name}  ({old_src})\n\n"
                f"Replace with:\n  {new_path.name}  ({new_src})?\n\n"
                "The cloned Voice Library profile is only used to generate audio — "
                "the file shown in Voiceover Audio is what gets rendered.",
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

    def _narration_source_text(self) -> str:
        # Prefer the Voice-section narration box so users can paste there directly.
        voice_script = self._tts_narration_text()
        if voice_script:
            return collect_narration(script_text=voice_script)

        script = ""
        if self._script_mode_is_ai():
            script = self.script_box.get("1.0", "end").strip()
        csv_raw = self.csv_var.get().strip()
        csv_path = Path(csv_raw) if csv_raw else None
        return collect_narration(
            script_text=script,
            csv_path=csv_path if csv_path and csv_path.is_file() else None,
            visual_plan=self._visual_plan,
        )

    def _narration_output_path(self) -> Path:
        if self._workspace is not None:
            self._workspace.ensure_dirs()
            return self._workspace.audio_path
        csv_raw = self.csv_var.get().strip()
        if csv_raw:
            return Path(csv_raw).resolve().parent / "voiceover_qwen.wav"
        out = self.output_var.get().strip()
        if out:
            return Path(out).resolve().parent / "voiceover_qwen.wav"
        return SOURCE_DIR / "voiceover_qwen.wav"

    def _set_tts_busy(self, busy: bool, label: str = "Generate Narration") -> None:
        # While busy the narration CTA becomes Stop (not a disabled "Generating…").
        if getattr(self, "tts_btn", None) is not None:
            if busy:
                self.tts_btn.configure(
                    state="normal",
                    text="Stop",
                    fg_color="transparent",
                    hover_color=_DANGER_BG,
                    text_color=_DANGER,
                    border_width=1,
                    border_color=_DANGER,
                    command=self._on_stop_tts_job,
                )
            else:
                self._restore_tts_generate_btn()
        if getattr(self, "top_voice_btn", None) is not None:
            if busy:
                self.top_voice_btn.configure(
                    state="normal",
                    text="Stop",
                    text_color=_DANGER,
                    border_color=_DANGER,
                    hover_color=_DANGER_BG,
                    command=self._on_stop_tts_job,
                )
            else:
                self.top_voice_btn.configure(
                    state="normal",
                    text="Voice",
                    text_color=_TEXT,
                    border_color=_BORDER,
                    hover_color=_CARD_HOVER,
                    command=self._on_tts_primary_click,
                )
        if getattr(self, "tts_create_btn", None) is not None and busy:
            self.tts_create_btn.configure(state="disabled")
        if busy:
            self._tts_progress_t0 = time.monotonic()
            self._tts_progress_done = 0
            self._tts_progress_total = 0
            self._tts_progress_phase = "Starting…"
            self._set_tts_progress(0.02, "Starting…")
            self.after(400, self._tick_tts_progress)
        else:
            self._tts_progress_t0 = None
            self._tts_progress_done = 0
            self._tts_progress_total = 0
            # Keep a brief "Done" if we just finished; otherwise clear.
            done_label = ""
            if getattr(self, "tts_progress_var", None) is not None:
                done_label = self.tts_progress_var.get() or ""
            if done_label.startswith("Done"):
                self.after(1200, lambda: self._set_tts_progress(0.0, ""))
            else:
                self._tts_progress_phase = ""
                self._set_tts_progress(0.0, "")
        if not busy:
            self._refresh_voice_playback_buttons()
            if not getattr(self, "_qwen_download_active", False):
                self._refresh_tts_status()

    def _set_tts_progress(self, fraction: float, label: str = "") -> None:
        bar = getattr(self, "tts_progress", None)
        var = getattr(self, "tts_progress_var", None)
        if bar is not None:
            bar.set(max(0.0, min(1.0, float(fraction))))
        if var is not None:
            var.set(label or "")

    @staticmethod
    def _format_eta_seconds(seconds: float) -> str:
        seconds = max(0, int(round(seconds)))
        if seconds < 60:
            return f"~{seconds}s left"
        mins, secs = divmod(seconds, 60)
        if mins < 60:
            return f"~{mins}m {secs:02d}s left"
        hours, mins = divmod(mins, 60)
        return f"~{hours}h {mins:02d}m left"

    def _tts_progress_label_text(self) -> str:
        phase = self._tts_progress_phase or "Working…"
        done = int(self._tts_progress_done or 0)
        total = int(self._tts_progress_total or 0)
        parts = phase
        if total > 0:
            parts = f"{phase}  ·  {done}/{total}"
        t0 = self._tts_progress_t0
        if t0 is None:
            return parts
        elapsed = max(0.0, time.monotonic() - t0)
        frac = 0.0
        if total > 0:
            # Mid-chunk estimate: count in-progress chunk as half done.
            frac = min(0.99, (done + (0.35 if done < total else 0.0)) / float(total))
        elif "load" in phase.lower():
            frac = 0.08
        if frac >= 0.08 and elapsed >= 2.0:
            remaining = elapsed * (1.0 - frac) / frac
            parts = f"{parts}  ·  {self._format_eta_seconds(remaining)}"
        elif elapsed >= 1.0:
            parts = f"{parts}  ·  {int(elapsed)}s elapsed"
        return parts

    def _tick_tts_progress(self) -> None:
        if not getattr(self, "_tts_job_active", False):
            return
        total = int(self._tts_progress_total or 0)
        done = int(self._tts_progress_done or 0)
        if total > 0:
            frac = min(0.97, (done + 0.35) / float(total)) if done < total else 1.0
        elif "load" in (self._tts_progress_phase or "").lower():
            # Soft indeterminate while the model loads.
            t0 = self._tts_progress_t0 or time.monotonic()
            pulse = 0.05 + 0.12 * (0.5 + 0.5 * ((time.monotonic() - t0) % 2.4) / 2.4)
            frac = pulse
        else:
            t0 = self._tts_progress_t0 or time.monotonic()
            frac = min(0.2, 0.03 + (time.monotonic() - t0) * 0.01)
        self._set_tts_progress(frac, self._tts_progress_label_text())
        self.after(400, self._tick_tts_progress)

    def _apply_tts_log_progress(self, line: str) -> None:
        """Update the Voice panel progress bar from TTS worker log lines."""
        stripped = (line or "").strip()
        if not stripped.startswith("[TTS]"):
            return
        if "Generated audio" in stripped or stripped.startswith("[TTS] Saved:"):
            self._tts_progress_done = self._tts_progress_total or 1
            self._tts_progress_total = self._tts_progress_total or 1
            self._tts_progress_phase = "Done"
            self._set_tts_progress(1.0, "Done")
            # Don't leave the CTA stuck on Generating if the done event is delayed.
            if getattr(self, "_tts_job_active", False):
                self._force_tts_idle("Done")
            return
        m_prog = re.search(r"\[TTS\]\s*Progress\s+(\d+)%\s*\((\d+)/(\d+)\)", stripped)
        if m_prog:
            pct = int(m_prog.group(1))
            done = int(m_prog.group(2))
            total = int(m_prog.group(3))
            self._tts_progress_done = done
            self._tts_progress_total = total
            self._tts_progress_phase = "Generating"
            self._set_tts_progress(pct / 100.0, self._tts_progress_label_text())
            if pct >= 100 and getattr(self, "_tts_job_active", False):
                self._force_tts_idle("Done")
            return
        m_part = re.search(r"\[TTS\]\s*Generating part\s+(\d+)\s*/\s*(\d+)", stripped)
        if m_part:
            idx = int(m_part.group(1))
            total = int(m_part.group(2))
            self._tts_progress_done = max(0, idx - 1)
            self._tts_progress_total = total
            self._tts_progress_phase = f"Part {idx}/{total}"
            frac = min(0.97, max(0.05, (idx - 0.65) / float(total)))
            self._set_tts_progress(frac, self._tts_progress_label_text())
            return
        if "Generating narration" in stripped:
            self._tts_progress_phase = "Generating"
            if self._tts_progress_total <= 0:
                self._set_tts_progress(0.08, self._tts_progress_label_text())
            return
        if "Loading" in stripped:
            self._tts_progress_phase = "Loading model"
            self._set_tts_progress(0.06, self._tts_progress_label_text())
            return
        if "Model ready" in stripped:
            self._tts_progress_phase = "Model ready"
            self._set_tts_progress(
                max(0.1, self.tts_progress.get() if self.tts_progress else 0.1),
                self._tts_progress_label_text(),
            )
            return
        if "Creating reusable voice" in stripped or "Creating voice" in stripped:
            self._tts_progress_phase = "Creating voice"
            self._set_tts_progress(0.25, self._tts_progress_label_text())
            return
        if "Voice profile saved" in stripped:
            self._tts_progress_phase = "Saving voice"
            self._set_tts_progress(0.9, self._tts_progress_label_text())
            return

    def _tts_ui(self, kind: str, payload=None) -> None:
        """Marshal TTS lifecycle events onto the main UI queue (thread-safe)."""
        self._ui_queue.put((kind, payload))

    def _current_voiceover_path(self) -> Path | None:
        """Prefer the bound voiceover path, then the project narration output."""
        for raw in (self.audio_var.get().strip(), str(self._narration_output_path())):
            if not raw:
                continue
            path = Path(raw)
            if path.is_file():
                return path
        return None

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
            out = subprocess.check_output(
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
        stop_btn = getattr(self, "_stop_voice_btn", None)
        if play_btn is None or stop_btn is None:
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
        stop_btn.configure(state="normal" if (playing or paused or has_audio) else "disabled")

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
                is_preview = play_path.name.lower() == "voiceover_qwen_preview.wav"
                if not same and not is_preview:
                    play_path = active
                    self._voice_play_paused_at = 0.0

        path = play_path or active
        if path is None:
            messagebox.showinfo(
                "Play Voice",
                "Generate narration first, then you can play it here.",
            )
            self._refresh_voice_playback_buttons()
            return
        start_at = float(getattr(self, "_voice_play_paused_at", 0.0) or 0.0)
        if self._start_voice_playback(Path(path), start_at=start_at):
            self.status_var.set(f"Playing {Path(path).name}…")
            self._append_log(f"[TTS] Playing narration: {Path(path).name}\n")

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
            self._voice_play_proc = subprocess.Popen(
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

    def _play_generated_voice(self) -> None:
        self._toggle_voice_playback()

    def _on_preview_voice(self) -> None:
        if not self._require_workspace("preview a voice"):
            return
        profile = self._require_ready_voice("preview")
        if profile is None:
            return
        if not self._begin_tts_job("Generate Narration"):
            return
        dest = self._narration_output_path().parent / "voiceover_qwen_preview.wav"
        self.status_var.set(f"Previewing {profile.name}…")
        self._append_log(f"\n[TTS] Previewing saved voice: {profile.name}\n")

        def work():
            try:
                client = get_shared_client(log=lambda line: self._ui_queue.put(("log", line + "\n")))
                result = client.generate_clone(
                    text=PREVIEW_TEXT,
                    output_path=dest,
                    voice_prompt_path=profile.prompt_path,
                )
                self._tts_ui("tts_preview_done", result)
            except TTSError as exc:
                self._tts_ui("tts_failed", exc.message)
            except Exception as exc:
                self._tts_ui("tts_failed", str(exc))
            finally:
                self._tts_ui("tts_job_end", None)

        threading.Thread(target=work, daemon=True).start()

    def _preview_done(self, result) -> None:
        self._end_tts_job()
        self.status_var.set("Voice preview ready")
        self._append_log(f"[TTS] Preview saved: {result.path}\n")
        self._refresh_tts_status()
        if self._start_voice_playback(Path(result.path)):
            self.status_var.set("Playing voice preview…")

    def _on_generate_narration(self) -> None:
        if not self._require_workspace("generate narration"):
            return
        profile = self._require_ready_voice("generate narration")
        if profile is None:
            return
        ok, status_msg = qwen_runtime_status()
        if not ok or not model_is_installed(CLONE_MODEL_ID):
            messagebox.showerror("Qwen3-TTS", status_msg)
            return
        try:
            spoken = self._narration_source_text()
        except TTSError as exc:
            messagebox.showerror("Narration", exc.message)
            return
        if self._workspace is not None and spoken:
            try:
                self._workspace.save_script(spoken)
            except OSError:
                pass
        dest = self._narration_output_path()
        if dest.is_file() or (
            self.audio_var.get().strip()
            and Path(self.audio_var.get().strip()).is_file()
        ):
            if not self._confirm_voiceover_switch(dest, source="tts"):
                return
        self._settings["qwen_selected_voice_id"] = profile.id
        save_settings(self._settings)
        if self._workspace is not None:
            self._workspace.set_voice_id(profile.id)

        if not self._begin_tts_job("Generate Narration"):
            return
        self.status_var.set(f"Generating narration with {profile.name}…")
        self._append_log(
            f"\n[TTS] Starting narration with saved voice: {profile.name}\n"
            f"[TTS] Script length: {len(spoken)} chars\n"
        )

        def work():
            try:
                client = get_shared_client(log=lambda line: self._ui_queue.put(("log", line + "\n")))
                result = client.generate_clone(
                    text=spoken,
                    output_path=dest,
                    voice_prompt_path=profile.prompt_path,
                )
                self._tts_ui("tts_narration_done", result)
            except TTSError as exc:
                self._tts_ui("tts_failed", exc.message)
            except Exception as exc:
                self._tts_ui("tts_failed", str(exc))
            finally:
                self._tts_ui("tts_job_end", None)

        threading.Thread(target=work, daemon=True).start()

    def _narration_done(self, result) -> None:
        self._end_tts_job()
        self._set_active_voiceover(result.path, source="tts")
        # Prefer the measured duration from generation when ffprobe/wave disagree.
        secs = max(0.0, float(getattr(result, "duration_seconds", 0) or 0))
        if secs <= 0:
            secs = self._audio_duration_seconds(Path(result.path))
        self._voice_play_duration = secs
        clock = self._format_play_clock(secs)
        self._set_voice_play_progress(0.0, f"0:00 / {clock}")
        mm, ss = divmod(int(round(secs)), 60)
        hh, mm = divmod(mm, 60)
        self.status_var.set(f"Narration ready — {hh:02d}:{mm:02d}:{ss:02d}")
        self._append_log(
            f"[TTS] ✓ Narration generated\n"
            f"[TTS] Duration: {hh:02d}:{mm:02d}:{ss:02d}\n"
            f"[TTS] File: {Path(result.path).name}\n"
            f"[AUDIO] Video will use cloned TTS voiceover: {Path(result.path).name}\n"
            f"[TTS] Local generation complete ({result.device}, {result.model})\n"
        )
        self._refresh_tts_status()

    def _narration_failed(self, message: str) -> None:
        cancelled = bool(getattr(self, "_tts_cancel_requested", False))
        self._end_tts_job()
        self.status_var.set("Voice job stopped" if cancelled else "Ready")
        self._refresh_tts_status()
        self._append_log(f"[TTS] {message}\n")
        if cancelled:
            return
        messagebox.showerror("Qwen3-TTS", message)

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
                existing = vg.find_image_for_scene(images_dir, scene.scene_number)
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
        max_inflight = 4
        while self._recovery_queue and len(self._busy_scenes) < max_inflight:
            action, scene = self._recovery_queue.pop(0)
            key = _scene_key(scene.scene_number)
            if key in self._busy_scenes:
                continue
            result = self._asset_results.get(key)
            if result is not None and getattr(result, "ok", False) and action != "skip":
                self._recovery_done += 1
                continue
            self._scene_action(action, scene)
        snap = self._qa_snapshot()
        if self._recovery_total:
            in_flight = len(self._busy_scenes)
            done = max(0, self._recovery_total - len(self._recovery_queue) - in_flight)
            if self._recovery_queue or in_flight:
                self.qa_bulk_progress_var.set(
                    f"RECOVERING FAILED SCENES  {done} / {self._recovery_total}"
                )
        if self._recovery_queue or (self._retry_pumping and self._busy_scenes and self._recovery_total):
            self.after(400, self._pump_retry_queue)
            return
        if self._recovery_total:
            snap = self._qa_snapshot()
            recovered = self._recovery_total - snap.needs_action
            if snap.needs_action:
                self.qa_bulk_progress_var.set(
                    f"{max(0, recovered)} / {self._recovery_total} recovered · "
                    f"{snap.needs_action} scene(s) still need attention"
                )
            else:
                self.qa_bulk_progress_var.set(f"{self._recovery_total} / {self._recovery_total} recovered")
            self._recovery_total = 0
        self._retry_pumping = False
        self._refresh_qa_ui()

    def _render_scene_rows(self) -> None:
        signature = tuple(_scene_key(s.scene_number) for s in self._scene_rows)
        if signature and signature == self._scene_row_signature and self._scene_row_widgets:
            self._refresh_qa_ui(immediate=True)
            return

        for child in self._scenes_list.winfo_children():
            child.destroy()
        self._scene_row_widgets = {}
        self._scene_row_signature = signature

        if not self._scene_rows:
            ctk.CTkLabel(
                self._scenes_list,
                text="No visual plan yet\nPaste your script and click Analyze Script, or import a CSV.",
                text_color=_MUTED, font=ctk.CTkFont(size=13), justify="left",
            ).grid(row=0, column=0, sticky="w", padx=12, pady=16)
            self.scenes_summary_var.set("No visual plan yet")
            self._refresh_qa_ui(immediate=True)
            return

        header = ctk.CTkFrame(self._scenes_list, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=4, pady=(0, 4))
        header.grid_columnconfigure(2, weight=1)
        for col, text, width in (
            (0, "", 22), (1, "#", 32), (2, "Status", 118), (3, "Source", 72), (4, "Dur", 36), (5, "Actions", 170),
        ):
            ctk.CTkLabel(
                header, text=text, width=width or 1, anchor="w",
                font=ctk.CTkFont(size=10, weight="bold"), text_color=_MUTED,
            ).grid(row=0, column=col, sticky="w", padx=4)

        from collections import defaultdict
        counts: dict[str, int] = defaultdict(int)
        for i, scene in enumerate(self._scene_rows):
            source = SceneAssetRouter.classify(scene) or AssetSource.LOCAL
            counts[source.value] += 1
            badge_text, badge_fg, badge_bg = SOURCE_BADGE[source]
            default_fg = _ROW_ALT if i % 2 else "transparent"
            row = ctk.CTkFrame(
                self._scenes_list, fg_color=default_fg, corner_radius=4, height=32,
            )
            row.grid(row=i + 1, column=0, sticky="ew", pady=0)
            row.grid_columnconfigure(5, weight=1)

            key = _scene_key(scene.scene_number)
            check_var = ctk.BooleanVar(value=key in self._qa.selected_failed)
            check = ctk.CTkCheckBox(
                row, text="", width=18, checkbox_width=14, checkbox_height=14,
                variable=check_var,
                command=lambda k=key, v=check_var: self._on_scene_check(k, v),
            )
            check.grid(row=0, column=0, sticky="w", padx=(6, 0), pady=2)

            ctk.CTkLabel(
                row, text=f"{scene.scene_number}", width=32,
                font=ctk.CTkFont(size=12, weight="bold"), text_color=_TEXT, anchor="w",
            ).grid(row=0, column=1, sticky="w", padx=(2, 4))

            status_label = ctk.CTkLabel(
                row, text="◌ QUEUED", font=ctk.CTkFont(size=11, weight="bold"),
                text_color=_QUEUED, width=118, anchor="w",
            )
            status_label.grid(row=0, column=2, sticky="w", padx=2)

            badge = ctk.CTkLabel(
                row, text=badge_text, font=ctk.CTkFont(size=10),
                text_color=badge_fg, fg_color=badge_bg, corner_radius=4, width=72, anchor="w",
            )
            badge.grid(row=0, column=3, sticky="w", padx=2)
            dur = ""
            if self._visual_plan is not None:
                planned = next(
                    (s for s in self._visual_plan.scenes if str(s.scene_id) == str(scene.scene_number)),
                    None,
                )
                if planned:
                    dur = f"{planned.duration:.1f}s"
            dur_label = ctk.CTkLabel(
                row, text=dur or "—", font=ctk.CTkFont(size=11), text_color=_MUTED, width=36, anchor="e",
            )
            dur_label.grid(row=0, column=4, sticky="e", padx=(0, 4))

            actions = ctk.CTkFrame(row, fg_color="transparent")
            actions.grid(row=0, column=5, sticky="e", padx=(4, 6), pady=2)
            retry_btn = ctk.CTkButton(
                actions, text="Retry", width=48, height=22,
                font=ctk.CTkFont(size=10, weight="bold"),
                command=lambda s=scene: self._scene_action("retry", s),
            )
            retry_btn.pack(side="left", padx=(0, 3))
            source_btn = ctk.CTkButton(
                actions, text="Source", width=54, height=22,
                fg_color="transparent", border_width=1, border_color=_BORDER,
                text_color=_ACCENT, font=ctk.CTkFont(size=10),
                command=lambda s=scene: self._change_source_dialog(s),
            )
            source_btn.pack(side="left", padx=(0, 3))
            stop_btn = ctk.CTkButton(
                actions, text="Stop", width=44, height=22,
                fg_color="transparent", border_width=1, border_color=_DANGER,
                text_color=_DANGER, font=ctk.CTkFont(size=10, weight="bold"),
                command=lambda s=scene: self._cancel_one_scene(s),
            )
            stop_btn.pack(side="left")
            stop_btn.configure(state="disabled")

            preview_label = ctk.CTkLabel(row, text="", font=ctk.CTkFont(size=1))
            elapsed_label = ctk.CTkLabel(row, text="", font=ctk.CTkFont(size=10), text_color=_MUTED, width=1)
            error_label = ctk.CTkLabel(row, text="", font=ctk.CTkFont(size=1), text_color=_WARNING)
            self._scene_row_widgets[key] = {
                "status_label": status_label,
                "elapsed_label": elapsed_label,
                "error_label": error_label,
                "badge": badge,
                "buttons": {"retry": retry_btn, "source": source_btn, "cancel": stop_btn},
                "scene": scene,
                "row": row,
                "default_fg": default_fg,
                "check_var": check_var,
                "check": check,
            }
            row.bind("<Button-1>", lambda _e, k=key: self._focus_scene(k, scroll=False))
            preview_label.bind("<Button-1>", lambda _e, k=key: self._focus_scene(k, scroll=False))
            for widget in (status_label, badge, dur_label):
                widget.bind("<Button-1>", lambda _e, k=key: self._focus_scene(k, scroll=False))

        self._refresh_qa_ui(immediate=True)

    def _sync_row_action_buttons(self, key: str) -> None:
        widgets = self._scene_row_widgets.get(key)
        if not widgets:
            return
        busy = key in self._busy_scenes or key in self._qa.busy
        buttons = widgets.get("buttons") or {}
        cancel = buttons.get("cancel")
        if cancel is not None:
            cancel.configure(state="normal" if busy else "disabled")
        for name, btn in buttons.items():
            if name == "cancel":
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

    def _maybe_update_scene_status(self, line: str) -> None:
        """Activity Log is history only — never update current QA/scene state from it."""
        return

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
            key = self.pexels_key_var.get().strip() or os.environ.get("PEXELS_API_KEY", "")
            if key:
                from providers.stock.pexels import build_pexels_provider

                stock_provider = build_pexels_provider(images_dir, key)
            elif any(s.wants_stock for s in scene_rows):
                raise RuntimeError(
                    "This project has Stock scenes but no Pexels API key is set. "
                    "Add one in Settings."
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

        return AssetManager(
            images_dir,
            stock_provider=stock_provider,
            flow_image_provider=flow_image_provider,
            flow_video_provider=flow_video_provider,
            youtube_provider=youtube_provider,
            log=print,
        )

    def _regenerate_scene(self, scene_row: SceneRow) -> None:
        self._scene_action("retry", scene_row)

    def _ensure_asset_manager(self, images_dir: Path) -> AssetManager:
        images_dir.mkdir(parents=True, exist_ok=True)
        mgr = self._asset_manager
        need_rebuild = mgr is None or Path(mgr.images_dir) != images_dir
        if not need_rebuild and mgr is not None:
            # Rebuild once if Change Source targets were missing from an older run.
            if mgr.youtube_provider is None or mgr.flow_video_provider is None:
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
                source = SceneAssetRouter.classify(updated) or AssetSource.LOCAL
                text, fg, bg = SOURCE_BADGE.get(source, ("Local", _MUTED, "transparent"))
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
        options = ["stock_video", "youtube", "flow_video", "flow_image", "stock_image"]
        if self._asset_manager is not None:
            options = self._asset_manager.recovery.change_source_options(scene_row) or options
        busy = _scene_key(scene_row.scene_number) in self._busy_scenes
        win = ctk.CTkToplevel(self)
        win.title(f"Change source — Scene {scene_row.scene_number}")
        win.geometry("280x280")
        win.transient(self)
        title = "Choose a source for this scene only"
        if busy:
            title = "Scene is busy — it will Stop, then switch source"
        ctk.CTkLabel(win, text=title).pack(pady=(12, 8))
        for name in options:
            ctk.CTkButton(
                win, text=name.replace("_", " ").title(), height=28,
                command=lambda n=name: (win.destroy(), self._scene_action_with_source(scene_row, n)),
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
        self.after(50, self._flush_qa_ui)

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
        if self._issues_visible:
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
                self.scenes_summary_var.set(snap.header)

    def _scene_source_mix_label(self) -> str:
        """Plan mix under VIDEO GENERATION — AI Image/Video, Stock, YouTube, Local."""
        from collections import Counter

        from providers.router import SceneAssetRouter

        counts: Counter[str] = Counter()
        for scene in self._scene_rows:
            key = _scene_key(scene.scene_number)
            result = self._asset_results.get(key)
            source = getattr(result, "source", None) if result is not None else None
            if source is None:
                source = SceneAssetRouter.classify(scene)
            if source == AssetSource.FLOW_IMAGE:
                counts["AI Image"] += 1
            elif source == AssetSource.FLOW_VIDEO:
                counts["AI Video"] += 1
            elif source == AssetSource.STOCK_VIDEO:
                counts["Stock Video"] += 1
            elif source == AssetSource.STOCK_IMAGE:
                counts["Stock Image"] += 1
            elif source == AssetSource.STOCK:
                counts["Stock"] += 1
            elif source == AssetSource.YOUTUBE_VIDEO:
                counts["YouTube"] += 1
            elif source in (AssetSource.MANUAL, AssetSource.LOCAL) or source is None:
                counts["Local"] += 1
            else:
                counts["Other"] += 1
        order = (
            "AI Image",
            "AI Video",
            "Stock Video",
            "Stock Image",
            "Stock",
            "YouTube",
            "Local",
            "Other",
        )
        parts = [f"{name} {counts[name]}" for name in order if counts.get(name)]
        return " · ".join(parts)

    def _paint_qa_chrome(self, snap=None) -> None:
        snap = snap or self._qa_snapshot()
        self.scenes_summary_var.set(snap.header)
        self.qa_health_var.set(snap.health_label)
        self.qa_counter_var.set(
            f"⚠ {snap.needs_action} NEED ATTENTION" if snap.needs_action else "Issues"
        )
        self.issues_toggle_btn.configure(
            text_color=_DANGER if snap.needs_action else _MUTED,
            border_color=_DANGER if snap.needs_action else _BORDER,
        )
        color = _DANGER if snap.needs_action else (_COPPER if snap.processing else "#16A34A")
        # counter label color isn't a StringVar — update via children is brittle; text is enough
        self.goto_error_btn.configure(
            text=snap.go_to_error_label,
            state="normal" if snap.needs_action else "disabled",
        )
        nav_state = "normal" if snap.needs_action else "disabled"
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

    def _update_details_panel(self, snap=None) -> None:
        snap = snap or self._qa_snapshot()
        key = self._qa.focused_key
        scene = next((s for s in self._scene_rows if _scene_key(s.scene_number) == key), None) if key else None
        detail_btns = (
            self.details_retry_btn,
            self.details_alt_btn,
            self.details_local_btn,
            self.details_skip_btn,
            self.details_source_btn,
            self.details_stop_btn,
        )
        if scene is None:
            self.details_text_var.set("Select a scene, or press GO TO ERROR.")
            for btn in detail_btns:
                btn.configure(state="disabled")
            return
        status = snap.statuses.get(key, self._row_status_from_result(scene))
        tracker = self._asset_manager.recovery if self._asset_manager is not None else None
        info = self._qa.details(scene, self._asset_results.get(key), status, tracker)
        lines = [
            info["title"],
            f"Status    {info['status']}",
            f"Provider  {info['provider']}",
        ]
        if info["search"]:
            lines.append(f"Search    {info['search']}")
        if info["error"]:
            lines.append(f"Error     {info['error']}")
        lines.append(f"Attempt   {info['attempt']}")
        if info["duration"]:
            lines.append(f"Duration  {info['duration']}")
        if info["fallback"]:
            lines.append(f"Fallback  {info['fallback']}")
        self.details_text_var.set("\n".join(lines))
        actions = set(info["actions"])
        busy = key in self._busy_scenes or key in self._qa.busy
        self.details_retry_btn.configure(state="normal" if "retry" in actions and not busy else "disabled")
        self.details_alt_btn.configure(state="normal" if "alternative" in actions and not busy else "disabled")
        self.details_local_btn.configure(state="normal" if "local_clip" in actions and not busy else "disabled")
        self.details_skip_btn.configure(state="normal" if "skip" in actions and not busy else "disabled")
        self.details_source_btn.configure(state="normal")
        self.details_stop_btn.configure(state="normal" if busy or "cancel" in actions else "disabled")

    def _focus_scene(self, key: str, scroll: bool = True) -> None:
        self._qa.focused_key = key
        if scroll:
            self._scroll_scene_into_view(key)
        self._paint_qa_chrome()
        self._update_details_panel()

    def _scroll_scene_into_view(self, key: str) -> None:
        widgets = self._scene_row_widgets.get(key)
        if not widgets or widgets.get("row") is None:
            return
        row = widgets["row"]
        self._scenes_list.update_idletasks()
        canvas = getattr(self._scenes_list, "_parent_canvas", None)
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
        key = self._qa.focused_key
        if not key:
            return
        scene = next((s for s in self._scene_rows if _scene_key(s.scene_number) == key), None)
        if scene is None:
            return
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

    def _on_scene_check(self, key: str, var) -> None:
        if var.get():
            self._qa.selected_failed.add(key)
        else:
            self._qa.selected_failed.discard(key)
        self._focus_scene(key, scroll=False)
        self._paint_qa_chrome()

    def _on_failed_check(self, key: str, var) -> None:
        self._on_scene_check(key, var)
    def _select_all_failed(self) -> None:
        self._qa.select_all_failed(self._qa_snapshot().unresolved_keys)
        for key, widgets in self._scene_row_widgets.items():
            if widgets.get("check_var") is not None:
                widgets["check_var"].set(key in self._qa.selected_failed)
        self._paint_qa_chrome()

    def _clear_failed_selection(self) -> None:
        self._qa.clear_selection()
        for widgets in self._scene_row_widgets.values():
            if widgets.get("check_var") is not None:
                widgets["check_var"].set(False)
        self._paint_qa_chrome()

    def _apply_scene_filter(self) -> None:
        self._qa.filter_query = self.scene_search_var.get()
        snap = self._qa_snapshot()
        for scene in self._scene_rows:
            key = _scene_key(scene.scene_number)
            widgets = self._scene_row_widgets.get(key)
            if not widgets or widgets.get("row") is None:
                continue
            show = self._qa.scene_matches(scene, snap.statuses.get(key, ""), self._asset_results.get(key))
            if show:
                widgets["row"].grid()
            else:
                widgets["row"].grid_remove()

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
        self.qa_bulk_progress_var.set(f"RECOVERING FAILED SCENES  0 / {self._recovery_total}")
        if not self._retry_pumping:
            self._retry_pumping = True
            self._pump_retry_queue()

    def _confirm_alternatives(self, scenes: list[SceneRow]) -> bool:
        tracker = SceneRecoveryTracker()
        if self._asset_manager is not None:
            tracker = self._asset_manager.recovery
        previews = preview_alternatives(scenes, tracker)
        counts = summarize_alternative_preview(previews)
        lines = [f"{n} scenes selected"] + [f"{v} → {k}" for k, v in counts.items()]
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

        ctk.CTkLabel(
            body, text="STOCK PROVIDERS", font=ctk.CTkFont(size=11, weight="bold"), text_color=_MUTED,
        ).pack(anchor="w", padx=20, pady=(20, 4))
        ctk.CTkLabel(
            body, text="Pexels — used for scenes with a 'stock' keyword and no prompt.",
            font=ctk.CTkFont(size=12), text_color=_TEXT,
        ).pack(anchor="w", padx=20)
        ctk.CTkEntry(
            body, textvariable=self.pexels_key_var, show="•", height=34,
            placeholder_text="Pexels API key", fg_color=_BG, border_color=_BORDER, text_color=_TEXT,
        ).pack(fill="x", padx=20, pady=(8, 4))

        pexels_status_var = ctk.StringVar(
            value="Configured" if self.pexels_key_var.get().strip() else "Not configured"
        )
        ctk.CTkLabel(body, textvariable=pexels_status_var, font=ctk.CTkFont(size=11), text_color=_MUTED).pack(
            anchor="w", padx=20
        )

        def save_key():
            self._settings["pexels_api_key"] = self.pexels_key_var.get().strip()
            save_settings(self._settings)
            pexels_status_var.set("Configured" if self.pexels_key_var.get().strip() else "Not configured")
            messagebox.showinfo("Saved", "Pexels API key saved.")

        ctk.CTkButton(
            body, text="Save Key", height=32, fg_color=_ACCENT, hover_color=_ACCENT_HOV,
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
            body, text="SMART EDITING", font=ctk.CTkFont(size=11, weight="bold"), text_color=_MUTED,
        ).pack(anchor="w", padx=20, pady=(4, 4))
        ctk.CTkSwitch(
            body, text="Text Effects", variable=self.smart_text_effects_var,
            onvalue=True, offvalue=False, progress_color=_ACCENT, button_color=_TEXT,
            text_color=_TEXT, font=ctk.CTkFont(size=12), command=self._persist_smart_editing_settings,
        ).pack(anchor="w", padx=20, pady=2)
        ctk.CTkSwitch(
            body, text="Sound Effects", variable=self.smart_sfx_var,
            onvalue=True, offvalue=False, progress_color=_ACCENT, button_color=_TEXT,
            text_color=_TEXT, font=ctk.CTkFont(size=12), command=self._persist_smart_editing_settings,
        ).pack(anchor="w", padx=20, pady=2)
        smart_row = ctk.CTkFrame(body, fg_color="transparent")
        smart_row.pack(fill="x", padx=20, pady=(4, 12))
        ctk.CTkLabel(smart_row, text="Intensity", font=ctk.CTkFont(size=12), text_color=_TEXT).pack(side="left")
        ctk.CTkOptionMenu(
            smart_row, variable=self.smart_intensity_var, values=["Low", "Medium", "High"],
            width=110, fg_color=_BG, button_color=_BORDER, button_hover_color=_ACCENT,
            text_color=_TEXT, dropdown_fg_color=_CARD, dropdown_text_color=_TEXT,
            command=lambda _v: self._persist_smart_editing_settings(),
        ).pack(side="left", padx=(8, 16))
        ctk.CTkLabel(smart_row, text="Mode", font=ctk.CTkFont(size=12), text_color=_TEXT).pack(side="left")
        ctk.CTkOptionMenu(
            smart_row, variable=self.smart_mode_var, values=["Smart", "Automatic"],
            width=110, fg_color=_BG, button_color=_BORDER, button_hover_color=_ACCENT,
            text_color=_TEXT, dropdown_fg_color=_CARD, dropdown_text_color=_TEXT,
            command=lambda _v: self._persist_smart_editing_settings(),
        ).pack(side="left", padx=(8, 0))

        ctk.CTkLabel(
            body, text="TTS style, speed, and clone options are also on the Voice card (Voice options).",
            font=ctk.CTkFont(size=11), text_color=_MUTED, wraplength=410, justify="left",
        ).pack(anchor="w", padx=20, pady=(0, 12))

        ctk.CTkFrame(body, fg_color=_BORDER, height=1).pack(fill="x", padx=20)

        # ── Flow Settings — Image + Video (exact options flow-engine supports) ──
        ctk.CTkLabel(
            body, text="FLOW SETTINGS", font=ctk.CTkFont(size=11, weight="bold"), text_color=_MUTED,
        ).pack(anchor="w", padx=20, pady=(16, 8))

        def _option_row(parent, label_text, var, options):
            """options: list[(value, label)]. The OptionMenu shows/edits labels;
            `var` (the real backing StringVar, e.g. holding "NARWHAL") is updated
            via `command` whenever the user picks a different label."""
            row = ctk.CTkFrame(parent, fg_color="transparent")
            row.pack(fill="x", pady=3)
            ctk.CTkLabel(
                row, text=label_text, font=ctk.CTkFont(size=12), text_color=_TEXT, width=110, anchor="w",
            ).pack(side="left")
            labels = [label for _, label in options]
            current_label = next((lbl for val, lbl in options if val == var.get()), labels[0])
            display = ctk.StringVar(value=current_label)

            def on_choice(chosen, o=options, v=var):
                v.set(next((val for val, lbl in o if lbl == chosen), o[0][0]))

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
        _option_row(image_card, "Model", self.flow_image_model_var, FLOW_IMAGE_MODELS)
        _option_row(image_card, "Dimension", self.flow_image_aspect_var, FLOW_IMAGE_ASPECT_RATIOS)
        ctk.CTkFrame(image_card, fg_color="transparent", height=6).pack()

        def save_flow_settings():
            self._settings["flow_settings"] = self._current_image_flow_settings()
            save_settings(self._settings)
            messagebox.showinfo("Saved", "Flow image settings saved. They apply to newly generated scenes.")

        ctk.CTkButton(
            body, text="Save Image Settings", height=32, fg_color=_ACCENT, hover_color=_ACCENT_HOV,
            text_color=_ACCENT_DARK, command=save_flow_settings,
        ).pack(anchor="w", padx=20, pady=(0, 16))

        ctk.CTkFrame(body, fg_color=_BORDER, height=1).pack(fill="x", padx=20)

        ctk.CTkLabel(
            body, text="AI / FLOW ACCOUNTS", font=ctk.CTkFont(size=11, weight="bold"), text_color=_MUTED,
        ).pack(anchor="w", padx=20, pady=(16, 4))
        ctk.CTkLabel(
            body,
            text="Used for scenes with an AI prompt. Each account gets its own browser "
                 "profile and works independently — sign in opens a real Chrome window "
                 "once; no passwords or session data are seen or stored by this app.",
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

        def render_accounts(accounts):
            # The FlowClient STATE subscription below outlives this window (it's
            # only torn down on <Destroy>, and a message can already be in
            # flight via self.after() when the user closes Settings) — without
            # this guard, redrawing into a destroyed CTkToplevel's widgets
            # raises "bad window path name".
            if not win.winfo_exists():
                return
            self._known_flow_accounts = accounts
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

        def _on_settings_closed(event):
            if event.widget is not win:
                return  # <Destroy> also fires for every child widget; only act once
            for unsub in _state_unsubscribers:
                try:
                    unsub()
                except Exception:
                    pass
            _state_unsubscribers.clear()

        win.bind("<Destroy>", _on_settings_closed)

        def connect_and(fn):
            def worker():
                try:
                    client = self._get_flow_engine_manager().ensure_running()
                    fn(client)

                    def on_state(msg, _client=client):
                        if msg.get("type") == "STATE":
                            accounts = msg.get("accounts", [])
                            self.after(0, lambda: (status_var.set("Connected"), render_accounts(accounts)))

                    _state_unsubscribers.append(client.subscribe(on_state))
                    state = client.get_state()
                    self.after(0, lambda: (status_var.set("Connected"), render_accounts(state.get("accounts", []))))
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

        def save_profile(pid, name_var, model_var, aspect_var, duration_var):
            for p in self._get_video_profiles():
                if p["id"] == pid:
                    p["name"] = name_var.get().strip() or p["name"]
                    p["model"] = model_var.get()
                    p["aspectRatio"] = aspect_var.get()
                    p["duration"] = int(duration_var.get())
            self._save_video_profiles(self._get_video_profiles())
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
                _option_row(card, "Model", model_var, FLOW_VIDEO_MODELS)
                _option_row(card, "Dimension", aspect_var, FLOW_IMAGE_ASPECT_RATIOS)
                _option_row(card, "Duration", duration_var, [(str(v), lbl) for v, lbl in FLOW_VIDEO_DURATIONS])

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
                    "Generate Narration (or import a voiceover) before Render Video.\n\n"
                    "You can Generate Assets while narration is still running."
                )
            if not audio_path.is_file():
                return None, (
                    f"Voiceover audio not found:\n{audio_path}\n\n"
                    "Wait for Generate Narration to finish, or import an audio file.\n"
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
                src = self._workspace.active_voiceover_source() or self._voiceover_source_label(audio_path)
                src_key = "tts" if src == "cloned TTS" else "imported"
                try:
                    self._workspace.set_active_voiceover(audio_path, source=src_key)
                except OSError:
                    pass
                self._refresh_voiceover_active_label()
        else:
            # Assets-only: keep a project-owned destination path even if TTS is
            # still writing narration.wav — Whisper is not used in this mode.
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

        snap = self._qa_snapshot() if self._scene_rows else None
        audio_ok = bool(self.audio_var.get().strip()) and Path(self.audio_var.get().strip()).is_file()
        # Match the CTA: Generate Assets stops after visuals; Render Video continues.
        mode = "render" if (snap is not None and snap.allow_render and audio_ok) else "assets"

        if mode == "render" and getattr(self, "_tts_job_active", False):
            messagebox.showinfo(
                "Narration still running",
                "Wait for Generate Narration to finish (or Stop it) before Render Video.\n\n"
                "You can Generate Assets while narration is running.",
            )
            return

        config, err = self._validate(require_audio=(mode == "render"))
        if err:
            messagebox.showerror("Cannot start", err)
            return

        tts_parallel = bool(getattr(self, "_tts_job_active", False)) and mode == "assets"
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
            self.status_var.set(
                "Generating assets… (narration still running)"
                if tts_parallel
                else "Generating assets…"
            )
        else:
            self.status_var.set("Rendering…")
        self.stage_var.set("GENERATING")
        # Keep Activity history if TTS is mid-flight so progress lines stay visible.
        if not tts_parallel:
            self._clear_log()
        self._append_log(
            (
                "Starting asset generation while narration continues…\n"
                if tts_parallel
                else "Starting asset generation…\n"
            )
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
                f"({smart_cfg.intensity}/{smart_cfg.mode})"
            )
            print(f"Work:   {work_dir}")
            print("")

            scene_rows = [SceneRow.from_csv_row(r) for r in config["rows"]]
            if getattr(self, "_visual_plan", None) is not None:
                scene_rows = self._visual_plan.to_scene_rows()
            if any(s.wants_flow or s.wants_stock or s.wants_youtube for s in scene_rows):
                print("[ASSET] Resolving scene assets (AI / stock / manual)...")
                self._asset_manager = self._build_asset_manager(config["images_dir"], scene_rows)
                from providers.base import AssetError
                from providers.router import SceneAssetRouter

                for scene in scene_rows:
                    key = _scene_key(scene.scene_number)
                    existing = self._asset_results.get(key)
                    if existing is not None and getattr(existing, "ok", False):
                        continue
                    source = SceneAssetRouter.classify(scene)
                    if source is None:
                        continue
                    self._ui_queue.put(("scene_busy", (scene.scene_number, "queued")))

                def _on_scene_start(scene: SceneRow, source: AssetSource) -> None:
                    self._ui_queue.put(
                        ("scene_busy", (scene.scene_number, _scene_busy_kind(source)))
                    )

                def _on_scene_complete(scene: SceneRow, result: AssetResult) -> None:
                    self._ui_queue.put(("scene_asset", (scene.scene_number, result)))

                try:
                    summary = self._asset_manager.resolve_all(
                        scene_rows,
                        on_scene_start=_on_scene_start,
                        on_scene_complete=_on_scene_complete,
                    )
                except AssetError as exc:
                    raise RuntimeError(exc.reason) from exc
                for number, result in summary.results.items():
                    key = _scene_key(number)
                    self._asset_results[key] = result
                    self._mirror_result_into_workspace(result)
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
                whisper_words = vg.transcribe_audio(str(config["audio_path"]), config["model"])
            aligned, audio_end = vg.align_rows(config["rows"], whisper_words)

            scene_text_fx = None
            render_audio = str(config["audio_path"])
            if smart_cfg.enabled():
                plan = build_plan(
                    config["rows"],
                    aligned,
                    whisper_words,
                    smart_cfg,
                    state_dir=state_dir,
                    audio_path=config["audio_path"],
                )
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
                    mixed = work_dir / "narration_with_sfx.wav"
                    from smart_editing import sfx_library_root

                    mix_sfx_with_narration(
                        config["audio_path"],
                        plan.sfx_events,
                        mixed,
                        sfx_root=sfx_library_root(),
                    )
                    render_audio = str(mixed)
                    print(f"[SMART] Mixed {len(plan.sfx_events)} SFX event(s) under narration.")

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
                bg_audio=str(config["bg_path"]) if config["bg_path"] else None,
                bg_volume=0.15,
                captions=config["captions"],
                scene_text_effects=scene_text_fx,
            )
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
                os.chdir(old_cwd)
            except OSError:
                pass
            shutil.rmtree(work_dir, ignore_errors=True)
            writer.flush()
            sys.stdout = old_out
            sys.stderr = old_err

    # ---------- UI queue / log ----------

    def _poll_queue(self) -> None:
        logs: list[str] = []
        try:
            try:
                while True:
                    kind, payload = self._ui_queue.get_nowait()
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
                        elif kind == "qwen_dl_status":
                            self._on_qwen_download_status(payload)
                        elif kind == "qwen_dl_progress":
                            self._on_qwen_download_progress(payload)
                        elif kind == "qwen_dl_done":
                            self._on_qwen_download_done()
                        elif kind == "qwen_dl_error":
                            self._on_qwen_download_error(payload)
                        elif kind == "assets_partial":
                            self._on_assets_partial(payload)
                        elif kind == "assets_complete":
                            self._on_assets_complete(payload)
                        elif kind == "assets_status":
                            self._refresh_qa_ui(immediate=True)
                        elif kind == "scene_busy":
                            scene_number, status = payload
                            key = _scene_key(scene_number)
                            self._busy_scenes.add(key)
                            self._qa.busy[key] = status
                            self._set_scene_status(scene_number, status)
                            self._refresh_qa_ui(immediate=True)
                        elif kind == "scene_asset":
                            scene_number, result = payload
                            key = _scene_key(scene_number)
                            self._busy_scenes.discard(key)
                            self._qa.busy.pop(key, None)
                            if result is not None:
                                self._asset_results[key] = result
                                self._mirror_result_into_workspace(result)
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
                            self._refresh_qa_ui(immediate=True)
                            self._maybe_resume_pending_source_change(key)
                        elif kind == "scene_result":
                            scene_number, token, result = payload
                            key = _scene_key(scene_number)
                            if not self._qa.apply_result(scene_number, token):
                                continue
                            self._busy_scenes.discard(key)
                            if result is not None:
                                self._asset_results[key] = result
                                self._mirror_result_into_workspace(result)
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
                        elif kind == "tts_narration_done":
                            self._narration_done(payload)
                        elif kind == "tts_preview_done":
                            self._preview_done(payload)
                        elif kind == "tts_failed":
                            self._narration_failed(str(payload or "Voice generation failed."))
                        elif kind == "tts_voice_created":
                            self._voice_created(str(payload))
                        elif kind == "tts_voice_replaced":
                            self._voice_replaced(str(payload))
                        elif kind == "tts_voice_failed":
                            self._voice_create_failed(str(payload or "Voice profile failed."))
                        elif kind == "tts_job_end":
                            # Safety net if a done/fail handler never ran or threw earlier.
                            if getattr(self, "_tts_job_active", False):
                                self._end_tts_job()
            except queue.Empty:
                pass
            if logs:
                self._append_log("".join(logs))
        except Exception:
            # Never let a handler crash stop the poll loop — TTS done events would stall.
            try:
                self._append_log(f"[UI] Queue handler error:\n{traceback.format_exc()}\n")
            except Exception:
                pass
            if getattr(self, "_tts_job_active", False):
                try:
                    self._end_tts_job()
                except Exception:
                    pass
        finally:
            self.after(80, self._poll_queue)

    def _end_generate_run(self) -> None:
        self._running = False
        self.cancel_btn.grid_forget()
        self._refresh_qa_ui(immediate=True)
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
        self._refresh_cleanup_button()
        messagebox.showinfo(
            "Scenes need attention",
            f"{snap.header}\n{snap.health_label}\n\n"
            "Successful assets were kept. GO TO ERROR jumps to the first unresolved scene.",
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
            "Generate narration if needed, then click Render Video.\n"
        )
        self._refresh_cleanup_button()

    def _maybe_update_progress(self, line: str) -> None:
        for marker, value in STAGE_PROGRESS.items():
            if marker in line:
                self.progress.set(value / 100.0)
                self.status_var.set(line.strip())
                break
        if "Done. Output:" in line:
            self.progress.set(1.0)
        # Keep the Voice CTA status + local progress bar in sync while TTS streams logs.
        stripped = (line or "").strip()
        if stripped.startswith("[TTS]"):
            self._apply_tts_log_progress(stripped)
            if (
                stripped.startswith("[TTS] Generating part")
                or stripped.startswith("[TTS] Generating narration")
                or stripped.startswith("[TTS] Progress")
                or stripped.startswith("[TTS] Generated audio")
                or stripped.startswith("[TTS] Duration:")
                or stripped.startswith("[TTS] Model ready")
                or stripped.startswith("[TTS] Loading")
                or "Creating reusable voice" in stripped
            ):
                self.status_var.set(stripped)

    def _on_finished(self, success: bool, message: str, cancelled: bool = False) -> None:
        self._end_generate_run()
        if success:
            self.progress.set(1.0)
            self.status_var.set(f"Done — {message}")
            self._append_log(f"\n✓ Finished: {message}\n")
            self._last_output = message
            self._show_preview(message)
            messagebox.showinfo("Done", f"Video saved to:\n{message}")
            self._offer_cleanup_after_render()
        elif cancelled:
            self.status_var.set("Cancelled")
            self._append_log(f"\n○ Cancelled: {message}\n")
            messagebox.showinfo("Cancelled", message)
            self._refresh_cleanup_button()
        else:
            self.status_var.set("Failed")
            self._append_log(f"\n✗ Error: {message}\n")
            messagebox.showerror("Generation failed", message)
            self._refresh_cleanup_button()
        self._refresh_qa_ui(immediate=True)

    def _show_preview(self, video_path: str) -> None:
        """Extract a thumbnail frame via ffmpeg and reveal the preview panel."""
        import tempfile as _tmp

        thumb = Path(_tmp.mktemp(suffix=".jpg"))
        ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
        try:
            result = subprocess.run(
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
                    subprocess.Popen(["explorer", f"/select,{p}"])
                else:
                    os.startfile(str(folder))  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", str(folder)])
        except Exception as exc:
            messagebox.showerror("Cannot open folder", str(exc))

    def _clear_log(self) -> None:
        self._log_backlog.clear()
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")

    def _append_log(self, text: str) -> None:
        if self._workspace is not None:
            self._workspace.append_log(text)
        if not self._log_visible:
            self._log_backlog.append(text)
            if len(self._log_backlog) > 400:
                self._log_backlog = self._log_backlog[-300:]
            return
        self.log_box.configure(state="normal")
        self.log_box.insert("end", text)
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _on_close(self) -> None:
        busy_bits = []
        if self._running:
            busy_bits.append("asset generation / render")
        if getattr(self, "_tts_job_active", False):
            busy_bits.append("voice narration")
        if busy_bits:
            if not messagebox.askyesno(
                "Quit?",
                "Still running: " + ", ".join(busy_bits) + ".\n\n"
                "Quit anyway? In-flight work will be interrupted.",
            ):
                return
        try:
            if self._running and self._asset_manager is not None:
                self._asset_manager.request_cancel()
        except Exception:
            pass
        try:
            self._stop_voice_playback()
        except Exception:
            pass
        try:
            shutdown_shared_client()
        except Exception:
            pass
        self.destroy()


def main() -> None:
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
