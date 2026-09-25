"""Media/Assets browser — Semantic YT Studio 2.0 CapCut-style editor, left
panel.

Lists the REAL generated assets already on disk for this project (scene
images/videos from the workspace's assets_dir, the voiceover recording, an
optional music bed) with real thumbnails, a search/filter box, and both an
"Insert at playhead" button and genuine in-app drag-and-drop onto the
timeline (Tk mouse-motion tracking across widget boundaries — no OS-level
drag protocol needed since both widgets live in the same Tk root).
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Callable, List, Optional

import customtkinter as ctk
from PIL import Image, ImageTk

from . import theme as T
from providers import hidden_subprocess

try:
    import video_generator as vg
except Exception:  # pragma: no cover
    vg = None

THUMB_SIZE = (96, 54)
_VIDEO_EXTS = {".mp4", ".mov", ".webm", ".mkv", ".avi"}
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


class AssetItem:
    __slots__ = ("path", "kind", "scene_number", "label")

    def __init__(self, path: Path, kind: str, scene_number: str = "", label: str = ""):
        self.path = path
        self.kind = kind  # "visual" | "voiceover" | "music" | "ambience" | "sfx"
        self.scene_number = scene_number
        self.label = label or path.name


def _video_thumbnail(path: Path, cache_dir: Path) -> Optional[Path]:
    """Best-effort single-frame thumbnail for a video asset, cached next to
    the project's other preview artifacts. Returns None (never raises) if
    ffmpeg isn't available or the extraction fails — callers fall back to a
    generic icon."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    out = cache_dir / f"{path.stem}_{path.stat().st_mtime_ns if path.is_file() else 0}.jpg"
    if out.is_file() and out.stat().st_size > 0:
        return out
    try:
        result = hidden_subprocess.run(
            ["ffmpeg", "-y", "-i", str(path), "-frames:v", "1", "-vf", "scale=192:-1", str(out)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=8,
        )
        return out if result.returncode == 0 and out.is_file() else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def scan_visual_assets(images_dir: Path) -> List[AssetItem]:
    """Every scene image/video already generated for this project, sorted
    by scene number then filename — a real inventory of what render_video()
    will actually use, not a synthetic list."""
    if vg is None or not Path(images_dir).is_dir():
        return []
    out: List[AssetItem] = []
    try:
        for p in sorted(Path(images_dir).iterdir(), key=lambda x: vg._natural_key(x)):
            if not p.is_file() or p.name.startswith("."):
                continue
            ext = p.suffix.lower()
            if ext not in _IMAGE_EXTS and ext not in _VIDEO_EXTS:
                continue
            stem = p.stem
            scene_number = stem.split("_")[0] if "_" in stem else stem
            out.append(AssetItem(p, "visual", scene_number=scene_number, label=p.name))
    except OSError:
        pass
    return out


class MediaBrowser(ctk.CTkFrame):
    def __init__(
        self,
        master,
        *,
        on_insert: Optional[Callable[[AssetItem], None]] = None,
        on_drag_drop: Optional[Callable[[AssetItem, int, int], None]] = None,
        **kwargs,
    ):
        super().__init__(master, fg_color=T.PANEL, **kwargs)
        self._on_insert = on_insert
        self._on_drag_drop = on_drag_drop
        self._items: List[AssetItem] = []
        self._selected: Optional[AssetItem] = None
        self._thumb_cache: dict = {}
        self._drag_ghost = None
        self._project_sig: Optional[tuple] = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        ctk.CTkLabel(self, text="Media", font=ctk.CTkFont(size=13, weight="bold"), text_color=T.TEXT, anchor="w").grid(
            row=0, column=0, sticky="ew", padx=10, pady=(10, 2)
        )
        self._search_var = ctk.StringVar()
        self._search_var.trace_add("write", lambda *_a: self._refresh_list())
        ctk.CTkEntry(self, textvariable=self._search_var, placeholder_text="Search assets…", height=28).grid(
            row=1, column=0, sticky="ew", padx=10, pady=(0, 6)
        )

        # Where a VISUAL asset lands — VIDEO_1 (primary) or VIDEO_2
        # (B-roll). Audio/voiceover/music items ignore this and always go
        # to their own track (VOICEOVER/MUSIC) — see _on_insert_asset in
        # ui/editor_view.py.
        self._target_display_var = ctk.StringVar(value="VIDEO_1")
        target_row = ctk.CTkFrame(self, fg_color="transparent")
        target_row.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 4))
        ctk.CTkLabel(target_row, text="Insert visuals to:", font=ctk.CTkFont(size=10), text_color=T.MUTED).pack(side="left")
        ctk.CTkOptionMenu(
            target_row, values=["VIDEO_1", "VIDEO_2 (B-roll)"], width=130, height=22,
            variable=self._target_display_var,
        ).pack(side="left", padx=(6, 0))

        self._list = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self._list.grid(row=3, column=0, sticky="nsew", padx=6, pady=(0, 6))
        self._list.grid_columnconfigure(0, weight=1)

        self._insert_btn = ctk.CTkButton(
            self, text="Insert at playhead", height=30, state="disabled", command=self._insert_selected,
        )
        self._insert_btn.grid(row=4, column=0, sticky="ew", padx=10, pady=(0, 10))

    def target_track(self) -> str:
        return "VIDEO_2" if self._target_display_var.get().startswith("VIDEO_2") else "VIDEO_1"

    def set_project(self, images_dir: Optional[Path], voiceover_path: Optional[Path], music_path: Optional[Path]) -> None:
        # Editor tab calls this on every on_show() — with 100-300+ scene
        # assets, re-scanning images_dir every navigation (Path.iterdir() +
        # a natural-key sort per visit) was a measurable Windows stall, same
        # pattern as the Visual Plan tab's CSV/manifest re-read. Skip the
        # rescan when nothing on disk has changed since the last visit.
        try:
            images_mtime = Path(images_dir).stat().st_mtime if images_dir else None
        except OSError:
            images_mtime = None
        sig = (
            str(images_dir) if images_dir else None,
            images_mtime,
            str(voiceover_path) if voiceover_path else None,
            str(music_path) if music_path else None,
        )
        if sig == self._project_sig and self._items:
            self._refresh_list()
            return
        self._project_sig = sig

        items: List[AssetItem] = []
        if images_dir is not None:
            items += scan_visual_assets(Path(images_dir))
        if voiceover_path is not None and Path(voiceover_path).is_file():
            items.append(AssetItem(Path(voiceover_path), "voiceover", label="Voiceover"))
        if music_path is not None and Path(music_path).is_file():
            items.append(AssetItem(Path(music_path), "music", label="Music bed"))
        self._items = items
        self._selected = None
        self._insert_btn.configure(state="disabled")
        self._refresh_list()

    def _refresh_list(self) -> None:
        query = self._search_var.get().strip().lower()
        for w in self._list.winfo_children():
            w.destroy()
        shown = [
            it for it in self._items
            if not query or query in it.label.lower() or query in it.scene_number.lower()
        ]
        for i, item in enumerate(shown):
            self._row(item, i)

    def _row(self, item: AssetItem, row: int) -> None:
        frame = ctk.CTkFrame(self._list, fg_color=T.PANEL_ALT if hasattr(T, "PANEL_ALT") else T.PANEL, corner_radius=6)
        frame.grid(row=row, column=0, sticky="ew", pady=2, padx=2)
        frame.grid_columnconfigure(1, weight=1)

        thumb = self._thumbnail_photo(item)
        thumb_label = ctk.CTkLabel(frame, text="" if thumb else "🎬", image=thumb, width=THUMB_SIZE[0], height=THUMB_SIZE[1])
        thumb_label.grid(row=0, column=0, rowspan=2, padx=4, pady=4)

        ctk.CTkLabel(frame, text=item.label[:32], font=ctk.CTkFont(size=11), text_color=T.TEXT, anchor="w").grid(
            row=0, column=1, sticky="ew", padx=(0, 6), pady=(6, 0)
        )
        sub = f"Scene {item.scene_number}" if item.scene_number else item.kind.title()
        ctk.CTkLabel(frame, text=sub, font=ctk.CTkFont(size=10), text_color=T.MUTED, anchor="w").grid(
            row=1, column=1, sticky="ew", padx=(0, 6), pady=(0, 6)
        )

        for widget in (frame, thumb_label):
            widget.bind("<Button-1>", lambda _e, it=item: self._select(it))
            widget.bind("<ButtonPress-1>", lambda e, it=item: self._drag_start(e, it), add="+")
            widget.bind("<B1-Motion>", self._drag_motion, add="+")
            widget.bind("<ButtonRelease-1>", self._drag_release, add="+")

    def _thumbnail_photo(self, item: AssetItem):
        cache_key = str(item.path)
        if cache_key in self._thumb_cache:
            return self._thumb_cache[cache_key]
        photo = None
        try:
            ext = item.path.suffix.lower()
            if ext in _IMAGE_EXTS and item.path.is_file():
                img = Image.open(item.path).convert("RGB")
                img.thumbnail(THUMB_SIZE)
                photo = ImageTk.PhotoImage(img)
            elif ext in _VIDEO_EXTS and item.path.is_file():
                thumb_path = _video_thumbnail(item.path, Path(tempfile.gettempdir()) / "syt_media_thumbs")
                if thumb_path is not None:
                    img = Image.open(thumb_path).convert("RGB")
                    img.thumbnail(THUMB_SIZE)
                    photo = ImageTk.PhotoImage(img)
        except Exception:
            photo = None
        self._thumb_cache[cache_key] = photo
        return photo

    def _select(self, item: AssetItem) -> None:
        self._selected = item
        self._insert_btn.configure(state="normal")

    def _insert_selected(self) -> None:
        if self._selected is not None and self._on_insert is not None:
            self._on_insert(self._selected)

    # ---- drag & drop (in-app, Tk-native — see module docstring) ----

    def _drag_start(self, event, item: AssetItem) -> None:
        self._select(item)
        self._drag_item = item
        self._drag_ghost = ctk.CTkLabel(
            self.winfo_toplevel(), text=item.label[:24], fg_color=T.ACCENT, text_color="white",
            corner_radius=4, font=ctk.CTkFont(size=11),
        )

    def _drag_motion(self, event) -> None:
        if self._drag_ghost is None:
            return
        x = self.winfo_pointerx() - self.winfo_toplevel().winfo_rootx()
        y = self.winfo_pointery() - self.winfo_toplevel().winfo_rooty()
        self._drag_ghost.place(x=x + 12, y=y + 12)

    def _drag_release(self, event) -> None:
        if self._drag_ghost is None:
            return
        ghost = self._drag_ghost
        item = getattr(self, "_drag_item", None)
        self._drag_ghost = None
        ghost.destroy()
        if item is None or self._on_drag_drop is None:
            return
        root_x, root_y = self.winfo_pointerx(), self.winfo_pointery()
        target = self.winfo_containing(root_x, root_y)
        if target is None:
            return
        self._on_drag_drop(item, root_x, root_y)
