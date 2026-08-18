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
import traceback
from io import StringIO
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

import video_generator as vg
from asset_manager import AssetManager
from providers.base import AssetSource, SceneRow
from providers.router import SceneAssetRouter


def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


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


SOURCE_BADGE = {
    AssetSource.FLOW_IMAGE: ("AI IMAGE", "#2563EB", "#EFF6FF"),
    AssetSource.FLOW_VIDEO: ("AI VIDEO", "#7C3AED", "#EEF2FF"),
    AssetSource.STOCK: ("STOCK", "#B45309", "#FEF3C7"),
    AssetSource.STOCK_IMAGE: ("STOCK IMAGE", "#B45309", "#FEF3C7"),
    AssetSource.STOCK_VIDEO: ("STOCK VIDEO", "#B45309", "#FEF3C7"),
    AssetSource.LOCAL: ("LOCAL", "#64748B", "#F1F5F9"),
}

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

STATUS_COLOR = {
    "waiting": "#64748B",
    "queued": "#64748B",
    "searching": "#D97706",
    "generating": "#D97706",
    "downloading": "#D97706",
    "ready": "#16A34A",
    "failed": "#DC2626",
    "cancelled": "#64748B",
    "rendering": "#2563EB",
}

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
    if t.startswith("failed") or "failed:" in t:
        return "failed"
    if "(cached" in t or "downloaded" in t or "saved " in t or t.startswith("local ("):
        return "ready"
    if "searching" in t:
        return "searching"
    if "selected" in t:
        return "downloading"
    if t.startswith("generated") or "generating" in t:
        return "generating"
    if t.startswith(("stock", "flow", "local", "image", "video")):
        return "queued"
    return None


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

# ── White + blue professional palette ──────────────────────────────────────
_BG          = "#FFFFFF"   # window canvas
_PANEL       = "#FFFFFF"   # left sidebar panel
_PANEL_ALT   = "#F8FAFC"   # right activity panel (subtle off-white)
_CARD        = "#FFFFFF"   # input card / entry well
_BORDER      = "#E2E8F0"   # subtle light-gray borders
_TEXT        = "#0F172A"   # primary text (near-black slate)
_MUTED       = "#64748B"   # secondary / label text (slate gray)
_ACCENT      = "#2563EB"   # primary blue — CTA / progress / switch
_ACCENT_DARK = "#FFFFFF"   # text on accent (blue) button
_ACCENT_HOV  = "#1D4ED8"   # hover state (darker blue)
_COPPER      = "#2563EB"   # secondary highlight (status text / switches) — same blue family
_SUCCESS     = "#16A34A"   # ready / done states
_DANGER      = "#DC2626"   # failed states
_DANGER_BG   = "#FEE2E2"   # light red hover background
_WARNING     = "#D97706"   # generating / in-progress states
# ───────────────────────────────────────────────────────────────────────────

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
        self.title("Semantic All-In-One")
        self.geometry("1180x760")
        self.minsize(1000, 620)

        # Force light + blue palette — professional, not a dark developer theme
        ctk.set_appearance_mode("Light")
        ctk.set_default_color_theme("blue")
        self.configure(fg_color=_BG)

        self._ui_queue: queue.Queue = queue.Queue()
        self._worker: threading.Thread | None = None
        self._running = False
        self._last_output: str | None = None
        self._settings = load_settings()

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

        # Root: 2 columns — left inputs (~380px), right activity (expands)
        self.grid_columnconfigure(0, minsize=380, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # ── Left panel ───────────────────────────────────────────────────
        left = ctk.CTkFrame(self, fg_color=_PANEL, corner_radius=0)
        left.grid(row=0, column=0, sticky="nsew")
        left.grid_columnconfigure(0, weight=1)
        left.grid_rowconfigure(2, weight=1)   # inputs section expands
        self._left_panel = left

        # Brand header
        brand = ctk.CTkFrame(left, fg_color="transparent")
        brand.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 10))
        brand.grid_columnconfigure(1, weight=1)

        logo_path = _logo_path()
        self._logo_ctk = None
        if logo_path is not None:
            try:
                from PIL import Image, ImageDraw

                SIZE = 56
                BORDER = 3
                TOTAL = SIZE + BORDER * 2

                base = Image.open(logo_path).convert("RGBA").resize(
                    (SIZE, SIZE), Image.Resampling.LANCZOS
                )

                # Circular mask
                mask = Image.new("L", (SIZE, SIZE), 0)
                ImageDraw.Draw(mask).ellipse((0, 0, SIZE - 1, SIZE - 1), fill=255)

                # Compose on transparent canvas (same size for clip)
                circle = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
                circle.paste(base, mask=mask)

                # Add teal border ring on a slightly larger canvas
                out = Image.new("RGBA", (TOTAL, TOTAL), (0, 0, 0, 0))
                # border ring
                ring_draw = ImageDraw.Draw(out)
                ring_draw.ellipse(
                    (0, 0, TOTAL - 1, TOTAL - 1),
                    fill=None,
                    outline=_ACCENT,
                    width=BORDER,
                )
                out.paste(circle, (BORDER, BORDER), mask=circle)

                self._logo_ctk = ctk.CTkImage(
                    light_image=out,
                    dark_image=out,
                    size=(TOTAL, TOTAL),
                )
                ctk.CTkLabel(
                    brand, image=self._logo_ctk, text="",
                    fg_color="transparent",
                ).grid(row=0, column=0, rowspan=2, sticky="w", padx=(0, 14))
            except Exception:
                self._logo_ctk = None

        ctk.CTkLabel(
            brand,
            text="Semantic All-In-One",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color=_TEXT,
            fg_color="transparent",
        ).grid(row=0, column=1, sticky="sw")
        ctk.CTkLabel(
            brand,
            text="AI · Stock · Manual — script + voiceover → synced MP4",
            font=ctk.CTkFont(size=12),
            text_color=_MUTED,
            fg_color="transparent",
        ).grid(row=1, column=1, sticky="nw")

        ctk.CTkButton(
            brand,
            text="⚙ Settings",
            width=90,
            height=30,
            fg_color="transparent",
            border_width=1,
            border_color=_BORDER,
            text_color=_TEXT,
            hover_color="#F1F5F9",
            corner_radius=6,
            font=ctk.CTkFont(size=12),
            command=self._open_settings,
        ).grid(row=0, column=2, rowspan=2, sticky="e", padx=(8, 0))

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
        scroll.grid(row=2, column=0, sticky="nsew", padx=0, pady=0)
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
        self.pexels_key_var = ctk.StringVar(value=self._settings.get("pexels_api_key", ""))

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

        # Input rows inside scroll. Images/ is an internal working directory the
        # app manages itself (see _sync_images_dir) — no user-facing folder picker;
        # the user only ever provides a script and a voiceover.
        self._path_row(0, "Script CSV",                self.csv_var,    self._browse_csv)
        self._path_row(1, "Voiceover Audio",           self.audio_var,  self._browse_audio)
        self._path_row(2, "Background Music (optional)",self.bg_var,    self._browse_bg,  clearable=True)
        self._path_row(3, "Save Video As",             self.output_var, self._browse_output)

        # Options row
        opts = ctk.CTkFrame(scroll, fg_color="transparent")
        opts.grid(row=4, column=0, sticky="ew", padx=16, pady=(12, 4))
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

        # Bottom bar: Generate CTA
        bottom = ctk.CTkFrame(left, fg_color=_PANEL, corner_radius=0)
        bottom.grid(row=3, column=0, sticky="ew")
        bottom.grid_columnconfigure(0, weight=1)

        ctk.CTkFrame(bottom, fg_color=_BORDER, height=1, corner_radius=0).grid(
            row=0, column=0, sticky="ew"
        )

        cta_row = ctk.CTkFrame(bottom, fg_color="transparent")
        cta_row.grid(row=1, column=0, sticky="ew", padx=16, pady=14)
        cta_row.grid_columnconfigure(0, weight=1)

        self.generate_btn = ctk.CTkButton(
            cta_row,
            text="Generate Video",
            height=44,
            fg_color=_ACCENT,
            hover_color=_ACCENT_HOV,
            text_color=_ACCENT_DARK,
            font=ctk.CTkFont(size=15, weight="bold"),
            corner_radius=6,
            command=self._on_generate,
        )
        self.generate_btn.grid(row=0, column=0, sticky="ew")

        self.cancel_btn = ctk.CTkButton(
            cta_row,
            text="Cancel",
            width=90,
            height=44,
            fg_color="transparent",
            border_width=1,
            border_color=_DANGER,
            text_color=_DANGER,
            hover_color=_DANGER_BG,
            font=ctk.CTkFont(size=13, weight="bold"),
            corner_radius=6,
            command=self._on_cancel,
        )
        # Not gridded yet — shown only while a run is in progress (see _on_generate).

        # ── Right panel (Activity) ────────────────────────────────────────
        right = ctk.CTkFrame(self, fg_color=_PANEL_ALT, corner_radius=0)
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(3, weight=1)   # log expands
        right.grid_rowconfigure(4, weight=1)   # preview (hidden until done)
        self._right_panel = right

        # Activity header
        act_header = ctk.CTkFrame(right, fg_color="transparent")
        act_header.grid(row=0, column=0, sticky="ew", padx=20, pady=(18, 0))
        act_header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            act_header,
            text="Activity",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=_TEXT,
        ).grid(row=0, column=0, sticky="w")

        self.status_var = ctk.StringVar(value="Ready")
        ctk.CTkLabel(
            act_header,
            textvariable=self.status_var,
            font=ctk.CTkFont(size=11),
            text_color=_COPPER,
            anchor="e",
        ).grid(row=0, column=1, sticky="e")

        # Progress bar
        self.progress = ctk.CTkProgressBar(
            right,
            height=6,
            progress_color=_ACCENT,
            fg_color=_BORDER,
            corner_radius=3,
        )
        self.progress.grid(row=1, column=0, sticky="ew", padx=20, pady=(10, 0))
        self.progress.set(0)

        # ── Scenes table ────────────────────────────────────────────────────
        scenes_wrap = ctk.CTkFrame(right, fg_color=_CARD, corner_radius=6, border_width=1, border_color=_BORDER)
        scenes_wrap.grid(row=2, column=0, sticky="ew", padx=16, pady=(12, 0))
        scenes_wrap.grid_columnconfigure(0, weight=1)

        scenes_header = ctk.CTkFrame(scenes_wrap, fg_color="transparent")
        scenes_header.pack(fill="x", padx=12, pady=(10, 4))
        ctk.CTkLabel(
            scenes_header, text="SCENES", font=ctk.CTkFont(size=11, weight="bold"), text_color=_MUTED,
        ).pack(side="left")
        self.scenes_summary_var = ctk.StringVar(value="Choose a script CSV to preview scenes")
        ctk.CTkLabel(
            scenes_header, textvariable=self.scenes_summary_var, font=ctk.CTkFont(size=11), text_color=_MUTED,
        ).pack(side="right")

        self._scenes_list = ctk.CTkScrollableFrame(
            scenes_wrap, fg_color="transparent", height=220,
            scrollbar_button_color=_BORDER, scrollbar_button_hover_color=_ACCENT,
        )
        self._scenes_list.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self._scenes_list.grid_columnconfigure(0, weight=1)
        self._scene_row_widgets: dict[str, dict] = {}
        self._scene_rows: list[SceneRow] = []

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
        self.log_box.grid(row=3, column=0, sticky="nsew", padx=16, pady=(12, 0))
        self.log_box.configure(state="disabled")

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

        # Thumbnail label — filled by _show_preview()
        self._thumb_label = ctk.CTkLabel(
            self._preview_panel,
            text="",
            fg_color="transparent",
        )
        self._thumb_label.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        self._last_output: str | None = None  # track for "Open" button

    def _set_window_icon(self) -> None:
        """Taskbar / dock / window icon from assets (best-effort)."""
        logo = _logo_path()
        if logo is None:
            return
        try:
            from PIL import Image, ImageTk
            img = Image.open(logo)
            self._icon_photo = ImageTk.PhotoImage(img.resize((64, 64), Image.Resampling.LANCZOS))
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
    ) -> None:
        """Styled input card inside the scrollable left panel."""
        card = ctk.CTkFrame(self._scroll, fg_color=_CARD, corner_radius=6)
        card.grid(row=row, column=0, sticky="ew", padx=16, pady=(10, 0))
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

    def _apply_defaults(self) -> None:
        if DEFAULTS["csv"].is_file():
            self.csv_var.set(str(DEFAULTS["csv"]))
        if DEFAULTS["audio"].is_file():
            self.audio_var.set(str(DEFAULTS["audio"]))
        self.output_var.set(str(DEFAULTS["output"]))
        if DEFAULTS["bg_audio"].is_file():
            self.bg_var.set(str(DEFAULTS["bg_audio"]))
        self._sync_images_dir()
        self._refresh_scene_preview()

    def _sync_images_dir(self) -> None:
        """Images/ is an internal working directory, never chosen by the user —
        it lives next to the script CSV (the "project folder"), created
        automatically. Falls back to a folder next to the output path, then the
        app's own data dir, if no CSV is chosen yet."""
        csv_path = self.csv_var.get().strip()
        if csv_path:
            base = Path(csv_path).resolve().parent
        else:
            out = self.output_var.get().strip()
            base = Path(out).resolve().parent if out else (Path.home() / ".videogen")
        images_dir = base / "Images"
        images_dir.mkdir(parents=True, exist_ok=True)
        self.images_var.set(str(images_dir))

    # ---------- browse helpers ----------

    def _browse_csv(self) -> None:
        path = filedialog.askopenfilename(
            title="Select script CSV",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialdir=str(_browse_start_dir()),
        )
        if path:
            self.csv_var.set(path)
            self._sync_images_dir()
            self._refresh_scene_preview()

    def _browse_audio(self) -> None:
        path = filedialog.askopenfilename(
            title="Select voiceover audio",
            filetypes=[
                ("Audio", "*.mp3 *.wav *.m4a *.webm *.aac *.flac"),
                ("All files", "*.*"),
            ],
            initialdir=str(_browse_start_dir()),
        )
        if path:
            self.audio_var.set(path)

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
        self._render_scene_rows()

    def _render_scene_rows(self) -> None:
        for child in self._scenes_list.winfo_children():
            child.destroy()
        self._scene_row_widgets = {}

        if not self._scene_rows:
            ctk.CTkLabel(
                self._scenes_list, text="Choose a script CSV to preview scenes.",
                text_color=_MUTED, font=ctk.CTkFont(size=12),
            ).grid(row=0, column=0, sticky="w", padx=8, pady=8)
            self.scenes_summary_var.set("")
            return

        # defaultdict, not a fixed dict of known sources — a hardcoded key set
        # here has already broken once (KeyError) when a new AssetSource was
        # added; this can never miss a key again.
        from collections import defaultdict

        counts: dict[str, int] = defaultdict(int)
        for i, scene in enumerate(self._scene_rows):
            source = SceneAssetRouter.classify(scene) or AssetSource.LOCAL
            counts[source.value] += 1
            badge_text, badge_fg, badge_bg = SOURCE_BADGE[source]

            row = ctk.CTkFrame(
                self._scenes_list, fg_color="#F8FAFC" if i % 2 else "transparent", corner_radius=4,
            )
            row.grid(row=i, column=0, sticky="ew", pady=1)
            row.grid_columnconfigure(1, weight=1)

            ctk.CTkLabel(
                row, text=f"#{scene.scene_number}", width=36,
                font=ctk.CTkFont(size=12, weight="bold"), text_color=_TEXT, anchor="w",
            ).grid(row=0, column=0, sticky="w", padx=(8, 4), pady=6)

            preview = scene.script_segment[:52] + ("…" if len(scene.script_segment) > 52 else "")
            ctk.CTkLabel(
                row, text=preview, font=ctk.CTkFont(size=12), text_color=_TEXT, anchor="w",
            ).grid(row=0, column=1, sticky="w", padx=4)

            ctk.CTkLabel(
                row, text=badge_text, font=ctk.CTkFont(size=10, weight="bold"),
                text_color=badge_fg, fg_color=badge_bg, corner_radius=4, width=104, height=20,
            ).grid(row=0, column=2, sticky="e", padx=4)

            status_label = ctk.CTkLabel(
                row, text="Waiting", font=ctk.CTkFont(size=11), text_color=_MUTED, width=76, anchor="e",
            )
            status_label.grid(row=0, column=3, sticky="e", padx=4)

            if source != AssetSource.LOCAL:
                ctk.CTkButton(
                    row, text="Regenerate", width=84, height=24,
                    fg_color="transparent", border_width=1, border_color=_BORDER,
                    text_color=_ACCENT, hover_color="#EFF6FF", font=ctk.CTkFont(size=11),
                    corner_radius=4, command=lambda s=scene: self._regenerate_scene(s),
                ).grid(row=0, column=4, sticky="e", padx=(4, 8))
            else:
                ctk.CTkFrame(row, fg_color="transparent", width=84, height=24).grid(
                    row=0, column=4, sticky="e", padx=(4, 8)
                )

            self._scene_row_widgets[_scene_key(scene.scene_number)] = {"status_label": status_label}

        stock_total = counts["stock"] + counts["stock_image"] + counts["stock_video"]
        self.scenes_summary_var.set(
            f"{len(self._scene_rows)} scenes — {counts['flow_image']} AI Image · "
            f"{counts['flow_video']} AI Video · {stock_total} Stock · {counts['local']} Local"
        )

    def _set_scene_status(self, scene_number, status: str) -> None:
        widgets = self._scene_row_widgets.get(_scene_key(scene_number))
        if not widgets:
            return
        widgets["status_label"].configure(
            text=status.capitalize(), text_color=STATUS_COLOR.get(status, _MUTED)
        )

    def _maybe_update_scene_status(self, line: str) -> None:
        m = _SCENE_LOG_RE.search(line)
        if not m:
            return
        status = _classify_scene_status(m.group(2).strip())
        if status:
            self._set_scene_status(m.group(1), status)

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
        """Shared by the main pipeline and Regenerate — builds only the providers
        this project actually needs, based on the CSV's asset_type/prompt/stock
        columns. Image and video AI scenes get separate FlowProvider instances
        (media_kind="image"/"video") since they're separate Flow API workflows."""
        needs_stock = any(s.wants_stock for s in scene_rows)
        needs_flow_image = any(s.wants_flow_image for s in scene_rows)
        needs_flow_video = any(s.wants_flow_video for s in scene_rows)

        stock_provider = None
        if needs_stock:
            key = self.pexels_key_var.get().strip() or os.environ.get("PEXELS_API_KEY", "")
            if not key:
                raise RuntimeError(
                    "This project has Stock scenes but no Pexels API key is set. "
                    "Add one in Settings."
                )
            from providers.stock.pexels import build_pexels_provider

            stock_provider = build_pexels_provider(images_dir, key)

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

        return AssetManager(
            images_dir,
            stock_provider=stock_provider,
            flow_image_provider=flow_image_provider,
            flow_video_provider=flow_video_provider,
            log=print,
        )

    def _regenerate_scene(self, scene_row: SceneRow) -> None:
        if self._running:
            messagebox.showinfo("Busy", "Wait for the current run to finish before regenerating a scene.")
            return
        if not self.images_var.get().strip():
            self._sync_images_dir()
        images_dir = Path(self.images_var.get().strip())
        images_dir.mkdir(parents=True, exist_ok=True)
        self._set_scene_status(scene_row.scene_number, "queued")
        threading.Thread(
            target=self._regenerate_scene_worker, args=(scene_row, images_dir), daemon=True
        ).start()

    def _regenerate_scene_worker(self, scene_row: SceneRow, images_dir: Path) -> None:
        old_out, old_err = sys.stdout, sys.stderr
        writer = _QueueWriter(self._ui_queue)
        sys.stdout = writer
        sys.stderr = writer
        try:
            if self._asset_manager is None or Path(self._asset_manager.images_dir) != images_dir:
                self._asset_manager = self._build_asset_manager(images_dir, self._scene_rows)
            result = self._asset_manager.regenerate_scene(scene_row)
            if result.ok:
                self._ui_queue.put(("scene_done", scene_row.scene_number))
            else:
                self._ui_queue.put(("scene_failed", (scene_row.scene_number, result.error)))
        except Exception as exc:
            self._ui_queue.put(("scene_failed", (scene_row.scene_number, str(exc))))
        finally:
            writer.flush()
            sys.stdout = old_out
            sys.stderr = old_err

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
        ).pack(anchor="w", padx=20, pady=(0, 16))

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

        def connect_and(fn):
            def worker():
                try:
                    client = self._get_flow_engine_manager().ensure_running()
                    fn(client)

                    def on_state(msg, _client=client):
                        if msg.get("type") == "STATE":
                            accounts = msg.get("accounts", [])
                            self.after(0, lambda: (status_var.set("Connected"), render_accounts(accounts)))

                    client.subscribe(on_state)
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
                        hover_color="#EFF6FF", command=lambda pid=profile["id"]: set_default_profile(pid),
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

    def _validate(self) -> tuple[dict | None, str | None]:
        if ensure_ffmpeg_on_path() is None:
            return None, (
                "ffmpeg was not found.\n\n"
                "For development: put a binary at bin/ffmpeg (Mac) or "
                "bin/ffmpeg.exe (Windows), or install ffmpeg on your PATH.\n"
                "Packaged builds should already include ffmpeg — if you see "
                "this message, the install is incomplete."
            )

        csv_path = Path(self.csv_var.get().strip())
        audio_path = Path(self.audio_var.get().strip())
        images_dir = Path(self.images_var.get().strip())
        output_path = Path(self.output_var.get().strip())
        bg_raw = self.bg_var.get().strip()
        bg_path = Path(bg_raw) if bg_raw else None

        if not self.csv_var.get().strip():
            return None, "Please choose a script CSV file."
        if not csv_path.is_file():
            return None, f"Script CSV not found:\n{csv_path}"

        if not self.audio_var.get().strip():
            return None, "Please choose a voiceover audio file."
        if not audio_path.is_file():
            return None, f"Voiceover audio not found:\n{audio_path}"

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
        }, None

    # ---------- generate ----------

    def _on_generate(self) -> None:
        if self._running:
            return

        config, err = self._validate()
        if err:
            messagebox.showerror("Cannot start", err)
            return

        self._running = True
        self.generate_btn.configure(
            state="disabled",
            text="Generating…",
            fg_color=_BORDER,
            text_color=_MUTED,
        )
        self.cancel_btn.grid(row=0, column=1, sticky="e", padx=(8, 0))
        self.cancel_btn.configure(state="normal", text="Cancel")
        self.progress.set(0)
        self.status_var.set("Running…")
        self._clear_log()
        self._append_log("Starting pipeline…\n")
        # Hide stale preview from a previous run
        self._preview_panel.grid_forget()
        self._right_panel.grid_rowconfigure(4, weight=0)

        self._worker = threading.Thread(
            target=self._run_pipeline,
            args=(config,),
            daemon=True,
        )
        self._worker.start()

    def _on_cancel(self) -> None:
        """Cancels the asset-resolution phase (AI/stock scenes not yet started, plus
        signals the in-flight Flow batch to stop). Whisper transcription and FFmpeg
        rendering are not interruptible — see the pre-existing pipeline, unchanged."""
        if not self._running:
            return
        self.cancel_btn.configure(state="disabled", text="Cancelling…")
        if self._asset_manager is not None:
            self._asset_manager.request_cancel()
            self._append_log("\n[ASSET] Cancel requested — finishing in-flight work, skipping the rest…\n")
        else:
            self._append_log(
                "\n[ASSET] Cancel requested, but nothing cancellable is running yet "
                "(Whisper/render can't be interrupted).\n"
            )

    def _run_pipeline(self, config: dict) -> None:
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

        work_dir = Path(tempfile.mkdtemp(prefix="videogen_"))
        old_cwd = os.getcwd()

        try:
            os.chdir(work_dir)
            print(f"CSV:    {config['csv_path']}")
            print(f"Audio:  {config['audio_path']}")
            print(f"Images: {config['images_dir']}")
            print(f"Output: {config['output_path']}")
            if config["bg_path"]:
                print(f"BG:     {config['bg_path']}")
            print(f"Model:  {config['model']}")
            print(f"Zoom:     {'ON' if config['zoom'] else 'OFF'}")
            print(f"Captions: {'ON' if config['captions'] else 'OFF'}")
            print(f"Work:   {work_dir}")
            print("")

            scene_rows = [SceneRow.from_csv_row(r) for r in config["rows"]]
            if any(s.wants_flow or s.wants_stock for s in scene_rows):
                print("[ASSET] Resolving scene assets (AI / stock / manual)...")
                self._asset_manager = self._build_asset_manager(config["images_dir"], scene_rows)
                from providers.base import AssetError

                try:
                    summary = self._asset_manager.resolve_all(scene_rows)
                except AssetError as exc:
                    raise RuntimeError(exc.reason) from exc
                if summary.cancelled:
                    raise _PipelineCancelled(
                        f"Cancelled — {len(summary.cancelled)} scene(s) skipped, "
                        f"{sum(1 for r in summary.results.values() if r.ok)} already completed."
                    )
                if not summary.ok:
                    lines = "\n".join(f"  Scene {r.scene_number}: {r.error}" for r in summary.failed)
                    raise RuntimeError(f"Could not resolve assets for these scene(s):\n{lines}")
                print("")

            vg.arrange_images(config["images_dir"])
            vg.validate_prerequisites(
                config["rows"],
                config["images_dir"],
                str(config["audio_path"]),
                bg_audio=str(config["bg_path"]) if config["bg_path"] else None,
            )
            whisper_words = vg.transcribe_audio(str(config["audio_path"]), config["model"])
            aligned, audio_end = vg.align_rows(config["rows"], whisper_words)
            vg.render_video(
                aligned,
                audio_end,
                config["images_dir"],
                str(config["audio_path"]),
                str(config["output_path"]),
                resolution="1920x1080",
                fps=30,
                zoom=config["zoom"],
                zoom_amount=0.10,
                bg_audio=str(config["bg_path"]) if config["bg_path"] else None,
                bg_volume=0.15,
                captions=config["captions"],
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
        try:
            while True:
                kind, payload = self._ui_queue.get_nowait()
                if kind == "log":
                    self._append_log(payload)
                    self._maybe_update_progress(payload)
                    self._maybe_update_scene_status(payload)
                elif kind == "done":
                    self._on_finished(success=True, message=payload)
                elif kind == "error":
                    self._on_finished(success=False, message=payload)
                elif kind == "cancelled":
                    self._on_finished(success=False, message=payload, cancelled=True)
                elif kind == "scene_done":
                    self._set_scene_status(payload, "ready")
                elif kind == "scene_failed":
                    scene_number, error = payload
                    self._set_scene_status(scene_number, "failed")
                    self._append_log(f"[ASSET] Scene {scene_number} regenerate failed: {error}\n")
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)

    def _maybe_update_progress(self, line: str) -> None:
        for marker, value in STAGE_PROGRESS.items():
            if marker in line:
                self.progress.set(value / 100.0)
                self.status_var.set(line.strip())
                break
        if "Done. Output:" in line:
            self.progress.set(1.0)

    def _on_finished(self, success: bool, message: str, cancelled: bool = False) -> None:
        self._running = False
        self.generate_btn.configure(
            state="normal",
            text="Generate Video",
            fg_color=_ACCENT,
            hover_color=_ACCENT_HOV,
            text_color=_ACCENT_DARK,
        )
        self.cancel_btn.grid_forget()
        if success:
            self.progress.set(1.0)
            self.status_var.set(f"Done — {message}")
            self._append_log(f"\n✓ Finished: {message}\n")
            self._last_output = message
            self._show_preview(message)
            messagebox.showinfo("Done", f"Video saved to:\n{message}")
        elif cancelled:
            self.status_var.set("Cancelled")
            self._append_log(f"\n○ Cancelled: {message}\n")
            messagebox.showinfo("Cancelled", message)
        else:
            self.status_var.set("Failed")
            self._append_log(f"\n✗ Error: {message}\n")
            messagebox.showerror("Generation failed", message)

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

    def _clear_log(self) -> None:
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")

    def _append_log(self, text: str) -> None:
        self.log_box.configure(state="normal")
        self.log_box.insert("end", text)
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _on_close(self) -> None:
        if self._running:
            if not messagebox.askyesno(
                "Quit?",
                "A video is still generating. Quit anyway?\n\n"
                "(The background job will be interrupted.)",
            ):
                return
        self.destroy()


def main() -> None:
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
