"""Uploads page: the channels, their queues and the uploading computer (upload_videos.py), managed from this app.

The uploading itself runs on the other computer (upload_videos.py watch). This page only reads the shared folder and writes to it:
channel settings, sign-ins, videos to queue, and commands (pause, resume, check now, retry). Nothing starts until a button is pressed.
File reads and copies run in a background thread; results come back to the UI thread with after()."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Any, Dict, List, Optional

import customtkinter as ctk

from . import theme as T
from .widgets import Card, make_button

REFRESH_MS = 30_000
PRIVACY_CHOICES = ["private", "unlisted", "public", "schedule"]


def _U():
    import upload_videos as U
    return U


def _root() -> Optional[Path]:
    try:
        return _U().find_root()
    except Exception:
        return None


def _small(master, text: str = "", var=None, color=None, size: int = 12, **kw) -> ctk.CTkLabel:
    return ctk.CTkLabel(master, text=text, textvariable=var, text_color=color or T.MUTED, font=ctk.CTkFont(size=size),
                        anchor="w", justify="left", **kw)


def _open_path(path: Path) -> None:
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        elif os.name == "nt":
            os.startfile(str(path))  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception as exc:
        messagebox.showerror("Uploads", f"Could not open {path}:\n{exc}")


def _bg(view: Any, work, done) -> None:
    """work() in a thread, then done(result or exception) on the UI thread (the UI thread polls; Tk is never called from the thread)."""
    box: List[Any] = []

    def run():
        try:
            box.append(work())
        except Exception as exc:
            box.append(exc)

    def poll():
        if box:
            done(box[0])
            return
        try:
            view.after(100, poll)
        except Exception:
            pass

    threading.Thread(target=run, daemon=True).start()
    view.after(100, poll)


# ---------------------------------------------------------------- building the page

def build(view: Any, app: Any) -> None:
    view._up_status = ctk.StringVar(value="")
    view._up_root_var = ctk.StringVar(value="")
    view._up_msg = ctk.StringVar(value="")
    view._up_refreshing = False
    view._up_loop = None
    body = view._body

    top = Card(body, title="Uploading computer", subtitle="Videos upload from the computer running the uploader (for example the UAE "
                                                          "laptop). Commands reach it through the shared folder within about a minute.")
    top.grid(row=0, column=0, sticky="ew", pady=(0, 12))
    top.body.grid_columnconfigure(0, weight=1)
    view._up_state_lbl = ctk.CTkLabel(top.body, textvariable=view._up_status, font=ctk.CTkFont(size=14, weight="bold"),
                                      anchor="w", justify="left", text_color=T.TEXT)
    view._up_state_lbl.grid(row=0, column=0, sticky="ew")
    _small(top.body, var=view._up_root_var).grid(row=1, column=0, sticky="ew", pady=(2, 8))
    row = ctk.CTkFrame(top.body, fg_color="transparent")
    row.grid(row=2, column=0, sticky="w")
    view._up_pause_btn = make_button(row, "Pause", lambda: _command(view, "pause"), width=90)
    view._up_pause_btn.pack(side="left", padx=(0, 6))
    make_button(row, "Resume", lambda: _command(view, "resume"), width=90).pack(side="left", padx=(0, 6))
    make_button(row, "Check now", lambda: _command(view, "now"), width=100).pack(side="left", padx=(0, 6))
    make_button(row, "Retry failed", lambda: _command(view, "retry"), width=110).pack(side="left", padx=(0, 6))
    make_button(row, "Refresh", lambda: refresh(view), width=90, variant="ghost").pack(side="left", padx=(0, 6))
    make_button(row, "Open folder", lambda: _open_root(view), width=110, variant="ghost").pack(side="left", padx=(0, 6))
    make_button(row, "Choose folder...", lambda: _choose_root(view), width=130, variant="ghost").pack(side="left")
    _small(top.body, var=view._up_msg, color=T.ACCENT_TEXT).grid(row=3, column=0, sticky="ew", pady=(8, 0))

    view._up_channels = Card(body, title="Channels", subtitle="Sign each channel in once: copy its link into that channel's ixBrowser "
                                                             "profile and click Allow.")
    view._up_channels.grid(row=1, column=0, sticky="ew", pady=(0, 12))
    view._up_channels.body.grid_columnconfigure(0, weight=1)
    view._up_rows = ctk.CTkFrame(view._up_channels.body, fg_color="transparent")
    view._up_rows.grid(row=0, column=0, sticky="ew")
    view._up_rows.grid_columnconfigure(0, weight=1)
    add = ctk.CTkFrame(view._up_channels.body, fg_color="transparent")
    add.grid(row=1, column=0, sticky="w", pady=(10, 0))
    view._up_new_name = ctk.CTkEntry(add, placeholder_text="New channel name", width=220)
    view._up_new_name.pack(side="left", padx=(0, 6))
    view._up_new_kids = ctk.BooleanVar(value=False)
    ctk.CTkCheckBox(add, text="Made for kids", variable=view._up_new_kids).pack(side="left", padx=(0, 6))
    make_button(add, "Add channel", lambda: _add_channel(view), width=120, variant="primary").pack(side="left")

    q = Card(body, title="Queue a video", subtitle="Copies a finished video into the channel's queue. Batches made with make_video.py "
                                                   "do this by themselves for rows with a channel.")
    q.grid(row=2, column=0, sticky="ew", pady=(0, 12))
    q.body.grid_columnconfigure(1, weight=1)
    view._up_q_channel = ctk.StringVar(value="")
    view._up_q_video = ctk.StringVar(value="")
    view._up_q_thumb = ctk.StringVar(value="")
    _small(q.body, "Channel").grid(row=0, column=0, sticky="w", padx=(0, 10), pady=3)
    view._up_q_menu = ctk.CTkOptionMenu(q.body, values=["(no channels)"], variable=view._up_q_channel, width=240)
    view._up_q_menu.grid(row=0, column=1, sticky="w", pady=3)
    _small(q.body, "Video").grid(row=1, column=0, sticky="w", padx=(0, 10), pady=3)
    vrow = ctk.CTkFrame(q.body, fg_color="transparent")
    vrow.grid(row=1, column=1, sticky="ew", pady=3)
    vrow.grid_columnconfigure(0, weight=1)
    ctk.CTkEntry(vrow, textvariable=view._up_q_video).grid(row=0, column=0, sticky="ew", padx=(0, 6))
    make_button(vrow, "Choose...", lambda: _pick(view._up_q_video, "video"), width=90).grid(row=0, column=1)
    _small(q.body, "Title").grid(row=2, column=0, sticky="w", padx=(0, 10), pady=3)
    view._up_q_title = ctk.CTkEntry(q.body, placeholder_text="Empty: the file name")
    view._up_q_title.grid(row=2, column=1, sticky="ew", pady=3)
    _small(q.body, "Description").grid(row=3, column=0, sticky="nw", padx=(0, 10), pady=3)
    view._up_q_desc = ctk.CTkTextbox(q.body, height=80, wrap="word")
    view._up_q_desc.grid(row=3, column=1, sticky="ew", pady=3)
    _small(q.body, "Tags").grid(row=4, column=0, sticky="w", padx=(0, 10), pady=3)
    view._up_q_tags = ctk.CTkEntry(q.body, placeholder_text="comma separated (the channel's own tags are added)")
    view._up_q_tags.grid(row=4, column=1, sticky="ew", pady=3)
    _small(q.body, "Thumbnail").grid(row=5, column=0, sticky="w", padx=(0, 10), pady=3)
    trow = ctk.CTkFrame(q.body, fg_color="transparent")
    trow.grid(row=5, column=1, sticky="ew", pady=3)
    trow.grid_columnconfigure(0, weight=1)
    ctk.CTkEntry(trow, textvariable=view._up_q_thumb, placeholder_text="optional .jpg/.png (under 2 MB)").grid(row=0, column=0, sticky="ew", padx=(0, 6))
    make_button(trow, "Choose...", lambda: _pick(view._up_q_thumb, "image"), width=90).grid(row=0, column=1)
    _small(q.body, "Publish at").grid(row=6, column=0, sticky="w", padx=(0, 10), pady=3)
    view._up_q_when = ctk.CTkEntry(q.body, placeholder_text="optional, e.g. 2026-11-25 17:00 (channel's time zone); empty: channel setting", width=420)
    view._up_q_when.grid(row=6, column=1, sticky="w", pady=3)
    view._up_q_btn = make_button(q.body, "Queue video", lambda: _queue(view), width=130, variant="primary")
    view._up_q_btn.grid(row=7, column=1, sticky="w", pady=(8, 0))

    act = Card(body, title="Recent activity", subtitle="From the uploading computer's log (newest last).")
    act.grid(row=3, column=0, sticky="ew", pady=(0, 12))
    act.body.grid_columnconfigure(0, weight=1)
    view._up_log = ctk.CTkTextbox(act.body, height=220, wrap="none", font=ctk.CTkFont(family="Menlo" if sys.platform == "darwin" else "Consolas", size=11))
    view._up_log.grid(row=0, column=0, sticky="ew")
    view._up_log.configure(state="disabled")


def on_show(view: Any, app: Any) -> None:
    refresh(view)
    if view._up_loop is None:
        _tick(view)


def _tick(view: Any) -> None:
    """While the page is open it refreshes every 30 s (reads only)."""
    try:
        if view.winfo_ismapped():
            refresh(view)
        view._up_loop = view.after(REFRESH_MS, lambda: _tick(view))
    except Exception:
        view._up_loop = None


# ---------------------------------------------------------------- reading the folder

def _snapshot(root: Path) -> Dict[str, Any]:
    U = _U()
    st = U.read_json(root / "_status" / "status.json") or {}
    ctl = U.control(root)
    chans = []
    for ch in U.channels(root):
        cfg = U.channel_cfg(ch)
        tok = U.read_json(ch / ".token.json", {}) or {}
        failed = []
        for f in sorted((ch / "failed").glob("*.json"))[:5]:
            d = U.read_json(f, {}) or {}
            failed.append(f"{d.get('title')}: {d.get('error')}")
        recent = []
        for f in sorted((ch / "uploaded").glob("*.json"))[-3:]:
            d = U.read_json(f, {}) or {}
            recent.append({"title": d.get("title"), "url": d.get("url"), "privacy": d.get("privacy"), "notes": d.get("notes") or []})
        chans.append({"name": ch.name, "path": str(ch), "cfg": cfg, "signed_in_as": tok.get("channel_title", ""), "signed": bool(tok),
                      "ready": len(list((ch / "ready").glob("*.json"))), "today": U.uploads_today(ch), "failed": failed, "recent": recent})
    log = root / "_status" / "uploader.log"
    tail = ""
    if log.is_file():
        with open(log, "rb") as f:
            f.seek(max(0, log.stat().st_size - 12000))
            tail = "\n".join(f.read().decode("utf-8", "replace").splitlines()[-40:])
    return {"status": st, "control": ctl, "channels": chans, "log": tail, "root": str(root),
            "has_key": (root / "client_secret.json").is_file()}


def refresh(view: Any) -> None:
    if view._up_refreshing:
        return
    root = _root()
    if root is None:
        view._up_status.set("No channels folder chosen yet")
        view._up_root_var.set("Press 'Choose folder...' and pick the shared folder (for example My Drive/YouTube Channels).")
        _render_channels(view, [])
        return
    view._up_refreshing = True
    _bg(view, lambda: _snapshot(root), lambda res: _apply(view, res))


def _apply(view: Any, snap: Any) -> None:
    view._up_refreshing = False
    if isinstance(snap, Exception):
        view._up_status.set(f"Could not read the channels folder: {snap}")
        return
    st, ctl = snap["status"], snap["control"]
    U = _U()
    if not st:
        state, color = "The uploading computer has not reported yet (is the uploader running there, and is the folder syncing?)", T.WARNING
    else:
        age = time.time() - float(st.get("heartbeat_ts", 0))
        mins = age / 60
        seen = "just now" if mins < 2 else f"{mins:.0f} min ago" if mins < 120 else f"{mins / 60:.1f} h ago"
        if age > U.HEARTBEAT_STALE:
            state, color = f"{st.get('computer')}: NO NEWS since {seen} (off, asleep or not syncing?)", T.DANGER
        else:
            state, color = f"{st.get('computer')}: {st.get('state')} (last seen {seen})", T.SUCCESS
    if ctl.get("paused"):
        state, color = "PAUSED - " + state, T.WARNING
    view._up_status.set(state)
    view._up_state_lbl.configure(text_color=color)
    view._up_root_var.set(f"Folder: {snap['root']}" + ("" if snap["has_key"] else "   |   client_secret.json is missing (see docs/youtube_uploader/SETUP.md)"))
    _render_channels(view, snap["channels"])
    view._up_log.configure(state="normal")
    view._up_log.delete("1.0", "end")
    view._up_log.insert("end", snap["log"] or "No activity yet.")
    view._up_log.see("end")
    view._up_log.configure(state="disabled")


def _privacy_text(cfg: Dict[str, Any]) -> str:
    sch = cfg.get("schedule") or {}
    if sch.get("times"):
        days = ", ".join(sch.get("days") or []) or "every day"
        return f"scheduled {', '.join(sch['times'])} {sch.get('timezone') or sch.get('utc_offset') or 'UTC'} ({days})"
    return cfg.get("privacy", "private")


def _render_channels(view: Any, chans: List[Dict[str, Any]]) -> None:
    for w in view._up_rows.winfo_children():
        w.destroy()
    names = [c["name"] for c in chans]
    view._up_q_menu.configure(values=names or ["(no channels)"])
    if view._up_q_channel.get() not in names:
        view._up_q_channel.set(names[0] if names else "(no channels)")
    if not chans:
        _small(view._up_rows, "No channels yet: add one below.").grid(row=0, column=0, sticky="w")
        return
    for i, c in enumerate(chans):
        fr = ctk.CTkFrame(view._up_rows, fg_color=T.ROW_ALT if i % 2 else "transparent", corner_radius=T.RADIUS)
        fr.grid(row=i, column=0, sticky="ew", pady=2)
        fr.grid_columnconfigure(0, weight=1)
        head = f"{c['name']}" + (f"   → {c['signed_in_as']}" if c["signed_in_as"] else "   (not signed in)")
        ctk.CTkLabel(fr, text=head, font=ctk.CTkFont(size=13, weight="bold"), anchor="w",
                     text_color=T.TEXT if c["signed"] else T.WARNING).grid(row=0, column=0, sticky="ew", padx=8, pady=(6, 0))
        line = (f"{c['ready']} waiting  |  {c['today']} uploaded today  |  {len(c['failed'])} failed  |  {_privacy_text(c['cfg'])}"
                + ("  |  kids" if c["cfg"].get("made_for_kids") else "") + ("" if c["cfg"].get("enabled", True) else "  |  OFF"))
        _small(fr, line).grid(row=1, column=0, sticky="ew", padx=8)
        for f in c["failed"][:3]:
            _small(fr, "failed: " + f[:160], color=T.DANGER, size=11).grid(sticky="ew", padx=8, column=0)
        for r in reversed(c["recent"]):
            lbl = _small(fr, f"↗ {r['title']}  [{r['privacy']}]" + ("  - " + r["notes"][0][:90] if r["notes"] else ""),
                         color=T.ACCENT_TEXT, size=11, cursor="hand2")
            lbl.grid(sticky="ew", padx=8, column=0)
            if r.get("url"):
                lbl.bind("<Button-1>", lambda _e, u=r["url"]: webbrowser.open(u))
        btns = ctk.CTkFrame(fr, fg_color="transparent")
        btns.grid(row=0, column=1, rowspan=2, sticky="e", padx=8, pady=6)
        make_button(btns, "Sign in" if not c["signed"] else "Sign in again", lambda n=c["name"]: _sign_in(view, n),
                    width=110, variant="primary" if not c["signed"] else "secondary").pack(side="left", padx=(0, 6))
        make_button(btns, "Settings", lambda n=c["name"]: _settings(view, n), width=90).pack(side="left", padx=(0, 6))
        make_button(btns, "Folder", lambda p=c["path"]: _open_path(Path(p)), width=70, variant="ghost").pack(side="left")


# ---------------------------------------------------------------- actions

def _say(view: Any, msg: str) -> None:
    view._up_msg.set(msg)


def _need_root(view: Any) -> Optional[Path]:
    root = _root()
    if root is None:
        messagebox.showinfo("Uploads", "Choose the shared channels folder first (Choose folder...).")
    return root


def _choose_root(view: Any) -> None:
    folder = filedialog.askdirectory(title="The shared channels folder (for example My Drive/YouTube Channels)")
    if not folder:
        return
    try:
        root = _U().setup_root(Path(folder))
    except Exception as exc:
        messagebox.showerror("Uploads", str(exc))
        return
    _say(view, f"Channels folder set: {root}")
    refresh(view)


def _open_root(view: Any) -> None:
    root = _need_root(view)
    if root:
        _open_path(root)


def _command(view: Any, what: str) -> None:
    root = _need_root(view)
    if root is None:
        return
    U = _U()
    try:
        if what == "pause":
            U.send_control(root, paused=True)
            _say(view, "Paused: the uploader stops after the video it is on.")
        elif what == "resume":
            U.send_control(root, paused=False, now=U.now_iso())
            _say(view, "Resumed.")
        elif what == "now":
            U.send_control(root, now=U.now_iso())
            _say(view, "Asked the uploader to check for new videos now.")
        elif what == "retry":
            U.send_control(root, retry=U.now_iso(), now=U.now_iso())
            _say(view, "Asked the uploader to try the failed videos again.")
    except Exception as exc:
        messagebox.showerror("Uploads", str(exc))
        return
    refresh(view)


def _add_channel(view: Any) -> None:
    root = _need_root(view)
    if root is None:
        return
    name = view._up_new_name.get().strip()
    if not name:
        return
    try:
        _U().add_channel(root, name, bool(view._up_new_kids.get()))
    except Exception as exc:
        messagebox.showerror("Uploads", str(exc))
        return
    view._up_new_name.delete(0, "end")
    _say(view, f"Channel '{name}' added. Next: Sign in.")
    refresh(view)


def _pick(var, kind: str) -> None:
    types = [("Videos", "*.mp4 *.mov *.m4v *.mkv *.webm")] if kind == "video" else [("Images", "*.jpg *.jpeg *.png")]
    path = filedialog.askopenfilename(filetypes=types + [("All files", "*.*")])
    if path:
        var.set(path)


def _queue(view: Any) -> None:
    root = _need_root(view)
    if root is None:
        return
    name, video = view._up_q_channel.get(), view._up_q_video.get().strip()
    if name == "(no channels)" or not video:
        messagebox.showinfo("Uploads", "Pick the channel and the video first.")
        return
    title, tags, when = view._up_q_title.get().strip(), view._up_q_tags.get().strip(), view._up_q_when.get().strip()
    desc, thumb = view._up_q_desc.get("1.0", "end").strip(), view._up_q_thumb.get().strip()
    view._up_q_btn.configure(state="disabled", text="Copying...")
    _say(view, f"Copying {Path(video).name} into '{name}'...")

    def done(res):
        view._up_q_btn.configure(state="normal", text="Queue video")
        if isinstance(res, Exception):
            _say(view, "")
            messagebox.showerror("Uploads", str(res))
            return
        _say(view, f"Queued for '{name}': {res.stem}. The uploader takes it once the folder has synced.")
        for e in (view._up_q_title, view._up_q_tags, view._up_q_when):
            e.delete(0, "end")
        view._up_q_desc.delete("1.0", "end")
        view._up_q_video.set("")
        view._up_q_thumb.set("")
        refresh(view)

    _bg(view, lambda: _U().enqueue(root, name, video, title, desc, tags, thumb, publish_at=when), done)


# ---------------------------------------------------------------- sign-in

def _sign_in(view: Any, name: str) -> None:
    root = _need_root(view)
    if root is None:
        return
    win = ctk.CTkToplevel(view)
    win.title(f"Sign in: {name}")
    win.geometry("620x380")
    win.transient(view.winfo_toplevel())
    win.grid_columnconfigure(0, weight=1)
    ctk.CTkLabel(win, text=f"Sign in '{name}'", font=ctk.CTkFont(size=16, weight="bold"), anchor="w").grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 4))
    _small(win, "1. Copy the link and open it in the ixBrowser profile where this channel is signed in.\n"
                "2. Pick the CHANNEL (not just the account) and click Allow.\n"
                "3. If the tab then says it cannot connect, copy that tab's whole address and paste it below.",
           wraplength=580).grid(row=1, column=0, sticky="ew", padx=16)
    link = ctk.CTkTextbox(win, height=80, wrap="char")
    link.grid(row=2, column=0, sticky="ew", padx=16, pady=8)
    link.insert("end", "Making the link...")
    brow = ctk.CTkFrame(win, fg_color="transparent")
    brow.grid(row=3, column=0, sticky="w", padx=16)
    status = ctk.StringVar(value="Waiting for Allow (10 minutes)...")
    paste = ctk.CTkEntry(win, placeholder_text="Paste the address here (only if the tab could not connect)")
    paste.grid(row=4, column=0, sticky="ew", padx=16, pady=(8, 4))
    _small(win, var=status, wraplength=580).grid(row=5, column=0, sticky="ew", padx=16, pady=(4, 12))
    box: Dict[str, Any] = {"url": "", "pasted": threading.Event(), "text": "", "closed": False}

    def copy():
        win.clipboard_clear()
        win.clipboard_append(box["url"])
        status.set("Link copied. Paste it into the channel's ixBrowser profile.")

    make_button(brow, "Copy link", copy, width=110, variant="primary").pack(side="left", padx=(0, 6))

    def use_paste():
        box["text"] = paste.get().strip()
        if box["text"]:
            box["pasted"].set()

    make_button(brow, "Use pasted address", use_paste, width=160).pack(side="left")

    def on_close():
        box["closed"] = True
        box["pasted"].set()
        win.destroy()

    win.protocol("WM_DELETE_WINDOW", on_close)

    def say(msg: str):                       # called from the sign-in thread: only stores the link
        if msg.strip().startswith("https://accounts.google.com"):
            box["url"] = msg.strip()

    def show_link():
        if box["closed"]:
            return
        if box["url"]:
            link.delete("1.0", "end")
            link.insert("end", box["url"])
            return
        win.after(150, show_link)

    win.after(150, show_link)

    def work():
        # Two ways back: the local page (the normal case) or the pasted address. The local wait is cut short by a paste.
        import upload_videos as U
        result: Dict[str, Any] = {}

        def run_login(paste_mode: bool):
            return U.login(root, name, paste=paste_mode, say=say, ask=lambda _p: box["text"], wait_s=600)

        t = threading.Thread(target=lambda: result.update(info=_try(run_login, False)), daemon=True)
        t.start()
        while t.is_alive():
            if box["pasted"].wait(0.5):
                break
        if box["closed"]:
            raise RuntimeError("closed")
        if "info" in result and not isinstance(result["info"], Exception):
            return result["info"]
        if box["pasted"].is_set():
            return _finish_with_paste(U, root, name, box)
        return result.get("info")

    def done(res):
        if box["closed"]:
            return
        if isinstance(res, Exception) or res is None:
            status.set(f"Not signed in: {res}")
            return
        status.set(f"Signed in as '{res.get('title')}'. You can close this window.")
        refresh(view)

    _bg(view, work, done)


def _try(fn, *a):
    try:
        return fn(*a)
    except Exception as exc:
        return exc


def _finish_with_paste(U, root: Path, name: str, box: Dict[str, Any]) -> Dict[str, str]:
    """The pasted address holds the code for the link already shown; its redirect is the local page's own address."""
    from urllib.parse import parse_qs, urlparse
    q = parse_qs(urlparse(box["url"]).query)
    redirect = (q.get("redirect_uri") or [""])[0]
    state = (q.get("state") or [""])[0]
    verifier = getattr(U, "_LAST_VERIFIER", {}).get(state)
    if not redirect or not verifier:
        raise U.UploadError("this sign-in link has expired; close the window and press Sign in again")
    return U.finish_login(root, name, box["text"], redirect, state, verifier)


# ---------------------------------------------------------------- channel settings

def _settings(view: Any, name: str) -> None:
    root = _need_root(view)
    if root is None:
        return
    U = _U()
    ch = U.channel_dir(root, name)
    raw = U.read_json(ch / "channel.json", {}) or {}
    cfg = U.channel_cfg(ch)
    sch = cfg.get("schedule") or {}
    win = ctk.CTkToplevel(view)
    win.title(f"Settings: {name}")
    win.geometry("640x640")
    win.transient(view.winfo_toplevel())
    win.grid_columnconfigure(1, weight=1)
    r = 0

    def label(text: str):
        nonlocal r
        _small(win, text).grid(row=r, column=0, sticky="nw", padx=(16, 10), pady=4)

    def entry(text: str, value: Any, hint: str = "") -> ctk.CTkEntry:
        nonlocal r
        label(text)
        e = ctk.CTkEntry(win, placeholder_text=hint)
        if value not in (None, ""):
            e.insert(0, str(value))
        e.grid(row=r, column=1, sticky="ew", padx=(0, 16), pady=4)
        r += 1
        return e

    privacy = ctk.StringVar(value="schedule" if sch.get("times") else cfg.get("privacy", "private"))
    label("Publishing")
    ctk.CTkOptionMenu(win, values=PRIVACY_CHOICES, variable=privacy, width=200).grid(row=r, column=1, sticky="w", padx=(0, 16), pady=4)
    r += 1
    _small(win, "public and schedule need a Cloud project that passed YouTube's API audit; before that YouTube keeps uploads private.",
           size=11, wraplength=440).grid(row=r, column=1, sticky="ew", padx=(0, 16))
    r += 1
    times = entry("Schedule times", ", ".join(sch.get("times") or []), "e.g. 09:00, 17:00 (only for schedule)")
    tz = entry("Time zone", sch.get("timezone") or "", "e.g. Europe/London, Asia/Dubai (or use UTC offset)")
    off = entry("UTC offset", sch.get("utc_offset") or "", "e.g. +04:00 (instead of the time zone)")
    days = entry("Days", ", ".join(sch.get("days") or []), "empty = every day; e.g. mon, wed, fri")
    tags = entry("Tags", ", ".join(cfg.get("tags") or []), "added to every video, comma separated")
    cat = entry("Category id", cfg.get("category_id"), "22 People, 27 Education, 28 Science & Tech, 24 Entertainment")
    lang = entry("Language", cfg.get("language"), "en, ur, ar...")
    key = entry("Sign-in key file", cfg.get("client_secret"), "client_secret.json (another file spreads the daily limit)")
    cap = entry("Max uploads a day", cfg.get("max_uploads_per_day") or "", "empty = only YouTube's limit")
    label("Description footer")
    footer = ctk.CTkTextbox(win, height=90, wrap="word")
    footer.insert("end", cfg.get("description_footer") or "")
    footer.grid(row=r, column=1, sticky="ew", padx=(0, 16), pady=4)
    r += 1
    kids = ctk.BooleanVar(value=bool(cfg.get("made_for_kids")))
    on = ctk.BooleanVar(value=bool(cfg.get("enabled", True)))
    ctk.CTkCheckBox(win, text="Made for kids", variable=kids).grid(row=r, column=1, sticky="w", pady=4)
    r += 1
    ctk.CTkCheckBox(win, text="Uploading on for this channel", variable=on).grid(row=r, column=1, sticky="w", pady=4)
    r += 1
    msg = ctk.StringVar(value="")
    _small(win, var=msg, color=T.DANGER, wraplength=440).grid(row=r + 1, column=1, sticky="ew", padx=(0, 16))

    def save():
        split = lambda e: [x.strip() for x in e.get().split(",") if x.strip()]   # noqa: E731
        new = dict(raw)
        p = privacy.get()
        schedule = {}
        if p == "schedule":
            schedule = {"times": split(times)}
            if tz.get().strip():
                schedule["timezone"] = tz.get().strip()
            if off.get().strip():
                schedule["utc_offset"] = off.get().strip()
            if split(days):
                schedule["days"] = split(days)
            p = "private"
        new.update({"privacy": p, "schedule": schedule, "tags": U.clean_tags(split(tags)), "category_id": cat.get().strip() or "22",
                    "language": lang.get().strip() or "en", "client_secret": key.get().strip() or "client_secret.json",
                    "description_footer": footer.get("1.0", "end").strip(), "made_for_kids": bool(kids.get()), "enabled": bool(on.get())})
        try:
            new["max_uploads_per_day"] = int(cap.get().strip() or 0)
        except ValueError:
            msg.set("Max uploads a day must be a number.")
            return
        try:                                          # the same checks the uploader makes, before anything is saved
            if schedule:
                if not schedule["times"]:
                    raise U.UploadError("give at least one schedule time, like 17:00")
                U.next_slot({"schedule": schedule}, [])
        except Exception as exc:
            msg.set(str(exc))
            return
        U.write_json(ch / "channel.json", new)
        _say(view, f"Settings saved for '{name}'.")
        win.destroy()
        refresh(view)

    make_button(win, "Save", save, width=120, variant="primary").grid(row=r, column=1, sticky="w", pady=(10, 4))
