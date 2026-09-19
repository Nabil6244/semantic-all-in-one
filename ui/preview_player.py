"""Real (not static) proxy video preview player — Semantic YT Studio 2.0
CapCut-style editor, center panel.

Plays the actual proxy files preview_engine.py builds from the current
(possibly operator-edited) timeline: genuinely decoded video frames via
ffmpeg (not a JPEG placeholder), with real synced audio via sounddevice
when available. Rebuilds are debounced and run on a background thread —
the Tk mainloop is never blocked.
"""

from __future__ import annotations

import queue
import subprocess
import threading
import time
import wave
from pathlib import Path
from typing import Callable, Optional

import customtkinter as ctk
from PIL import Image, ImageTk

from . import theme as T

try:
    import sounddevice as _sd
except Exception:  # pragma: no cover - optional dependency
    _sd = None

PROXY_FPS = 15


class _FrameDecoder(threading.Thread):
    """Streams rawvideo frames from a proxy MP4 starting at ``seek``,
    pushing (presentation_time, PIL.Image) into ``out_queue``. One instance
    per playback position — a new seek/stop replaces it rather than
    reusing it, keeping the state machine simple and hard to get wrong."""

    def __init__(self, video_path: Path, *, seek: float, width: int, height: int, fps: int, out_queue: "queue.Queue"):
        super().__init__(daemon=True)
        self.video_path = video_path
        self.seek = max(0.0, seek)
        self.width = width
        self.height = height
        self.fps = fps
        self.out_queue = out_queue
        self._stop = threading.Event()
        self._proc: Optional[subprocess.Popen] = None

    def stop(self) -> None:
        self._stop.set()
        if self._proc is not None:
            try:
                self._proc.kill()
            except Exception:
                pass

    def run(self) -> None:
        frame_size = self.width * self.height * 3
        args = [
            "ffmpeg", "-ss", f"{self.seek:.3f}", "-i", str(self.video_path),
            "-f", "rawvideo", "-pix_fmt", "rgb24",
            "-vf", f"fps={self.fps}", "-",
        ]
        try:
            self._proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        except OSError:
            return
        idx = 0
        t = self.seek
        try:
            while not self._stop.is_set():
                buf = self._proc.stdout.read(frame_size)
                if not buf or len(buf) < frame_size:
                    break
                img = Image.frombytes("RGB", (self.width, self.height), buf)
                try:
                    self.out_queue.put((t, img), timeout=0.5)
                except queue.Full:
                    pass
                idx += 1
                t = self.seek + idx / float(self.fps)
        finally:
            try:
                if self._proc.stdout:
                    self._proc.stdout.close()
                self._proc.kill()
            except Exception:
                pass


class _AudioPlayer:
    """Plays a mixed-down proxy WAV from an arbitrary start offset via
    sounddevice. No-op (silent) if sounddevice isn't available — the video
    preview still works, just without sound (a stated limitation)."""

    def __init__(self) -> None:
        self._stream = None
        self._wf: Optional[wave.Wave_read] = None
        self.available = _sd is not None

    def play(self, path: Path, *, start_s: float) -> bool:
        self.stop()
        if _sd is None or not path.is_file():
            return False
        try:
            wf = wave.open(str(path), "rb")
            sr = wf.getframerate()
            wf.setpos(min(int(start_s * sr), wf.getnframes()))
            channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()

            def callback(outdata, frames, time_info, status):
                data = wf.readframes(frames)
                if not data:
                    raise _sd.CallbackStop()
                if len(data) < frames * channels * sampwidth:
                    outdata[: len(data)] = data
                    outdata[len(data):] = b"\x00" * (len(outdata) - len(data))
                else:
                    outdata[:] = data

            stream = _sd.RawOutputStream(
                samplerate=sr, channels=channels,
                dtype="int16" if sampwidth == 2 else "int8",
                callback=callback,
            )
            stream.start()
            self._wf, self._stream = wf, stream
            return True
        except Exception:
            self.stop()
            return False

    def stop(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        if self._wf is not None:
            try:
                self._wf.close()
            except Exception:
                pass
            self._wf = None


class PreviewPlayer(ctk.CTkFrame):
    def __init__(
        self,
        master,
        *,
        on_time_change: Optional[Callable[[float], None]] = None,
        canvas_width: int = 480,
        canvas_height: int = 270,
        **kwargs,
    ):
        super().__init__(master, fg_color=T.PANEL, **kwargs)
        self._on_time_change = on_time_change
        # NOTE: intentionally NOT self._w/_h — Tk uses self._w internally
        # for the widget's own Tcl path name; clobbering it corrupts every
        # subsequent Tk call on this widget.
        self._proxy_w, self._proxy_h = canvas_width, canvas_height
        self._video_path: Optional[Path] = None
        self._audio_path: Optional[Path] = None
        self._duration = 0.0
        self._position = 0.0
        self._playing = False
        self._play_started_at = 0.0
        self._play_started_pos = 0.0
        self._decoder: Optional[_FrameDecoder] = None
        self._frame_queue: "queue.Queue" = queue.Queue(maxsize=6)
        self._last_frame_photo = None
        self._audio = _AudioPlayer()
        self._building = False

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._canvas = ctk.CTkCanvas(self, bg="black", highlightthickness=0, width=canvas_width, height=canvas_height)
        self._canvas.grid(row=0, column=0, sticky="nsew", padx=6, pady=(6, 2))
        self._empty_text = self._canvas.create_text(
            canvas_width // 2, canvas_height // 2, fill="#888888",
            text="No preview yet — build the first cut to see real playback.",
            font=("", 11), width=canvas_width - 40,
        )
        # One persistent image item, reused every frame via itemconfigure
        # instead of delete()+create_image() (was recreating a canvas item
        # up to 15x/second — real, measurable per-frame Tk overhead, and a
        # contributor to uneven playback pacing alongside the drift fix in
        # _tick() below). Starts hidden; the first real frame reveals it.
        self._frame_item = self._canvas.create_image(0, 0, anchor="nw", state="hidden")
        self._next_tick_at = 0.0

        controls = ctk.CTkFrame(self, fg_color="transparent")
        controls.grid(row=1, column=0, sticky="ew", padx=6, pady=(0, 6))
        controls.grid_columnconfigure(2, weight=1)

        self._play_btn = ctk.CTkButton(controls, text="▶", width=36, height=28, command=self.toggle_play)
        self._play_btn.grid(row=0, column=0, padx=(0, 4))
        self._stop_btn = ctk.CTkButton(
            controls, text="■", width=36, height=28, command=self.stop,
            fg_color="transparent", border_width=1, border_color=T.BORDER, text_color=T.TEXT,
        )
        self._stop_btn.grid(row=0, column=1, padx=(0, 8))

        self._scrub = ctk.CTkSlider(controls, from_=0, to=1, number_of_steps=1000, command=self._on_scrub)
        self._scrub.set(0)
        self._scrub.grid(row=0, column=2, sticky="ew", padx=4)

        self._time_label = ctk.CTkLabel(controls, text="00:00 / 00:00", width=100, font=ctk.CTkFont(size=11), text_color=T.MUTED)
        self._time_label.grid(row=0, column=3, padx=(8, 0))

        # Honest audio-availability indicator (never silent/fake playback):
        # sounddevice missing or PortAudio unable to open an output device
        # means the video preview plays but with NO sound — that must be
        # visible in the UI, not just an unexplained silent player (this
        # exact gap was reported live: a real environment missing the
        # sounddevice dependency showed a normally-working video preview
        # with no indication audio was never actually playing).
        self._audio_status_label = ctk.CTkLabel(
            controls, text="", font=ctk.CTkFont(size=10), text_color=T.DANGER,
        )
        self._audio_status_label.grid(row=0, column=4, padx=(8, 0))
        if not self._audio.available:
            self._audio_status_label.configure(text="🔇 no audio device")

        self.bind_all_spacebar()
        self.after(1000 // PROXY_FPS, self._tick)

    # ---- public API ----

    def bind_all_spacebar(self) -> None:
        try:
            self._canvas.bind("<space>", lambda _e: self.toggle_play())
        except Exception:
            pass

    def set_proxies(self, video_path: Optional[Path], audio_path: Optional[Path], duration: float, *, failed: bool = False) -> None:
        """Point the player at freshly (re)built proxy files. Resets
        playback to the start; call is cheap and idempotent.

        ``failed=True`` (task: "PREVIEW ERROR HANDLING") means proxy
        generation was actually ATTEMPTED and failed — as opposed to
        "there's simply no visual content yet" — so a distinct message is
        shown. Either way the timeline itself is untouched and remains
        fully editable; the next edit automatically retries (EditorView's
        normal debounced rebuild), so no separate "retry" plumbing is
        needed — the editor never gets stuck."""
        self.stop()
        self._video_path = video_path
        self._audio_path = audio_path
        self._duration = max(0.0, float(duration))
        self._position = 0.0
        self._scrub.configure(to=max(self._duration, 0.001))
        self._scrub.set(0)
        self._update_time_label()
        if video_path is not None:
            self._canvas.itemconfigure(self._empty_text, state="hidden")
            self._seek_decoder(0.0)
        elif failed:
            self._canvas.itemconfigure(self._frame_item, state="hidden")
            self._canvas.itemconfigure(
                self._empty_text, state="normal",
                text="Preview couldn't be built for this edit — your changes are safe and still exported "
                     "correctly. Make another edit to retry.",
            )
        else:
            self._canvas.itemconfigure(self._frame_item, state="hidden")
            self._canvas.itemconfigure(
                self._empty_text, state="normal",
                text="No preview yet — build the first cut to see real playback.",
            )

    def set_building(self, building: bool) -> None:
        self._building = building
        if building:
            self._canvas.itemconfigure(
                self._empty_text, state="normal", text="Building proxy preview…",
            )
        elif self._video_path is not None:
            self._canvas.itemconfigure(self._empty_text, state="hidden")

    def toggle_play(self) -> None:
        self.pause() if self._playing else self.play()

    def play(self) -> None:
        if self._video_path is None or self._playing:
            return
        self._playing = True
        self._play_btn.configure(text="⏸")
        self._play_started_at = time.monotonic()
        self._play_started_pos = self._position
        if self._audio_path is not None:
            ok = self._audio.play(self._audio_path, start_s=self._position)
            if not ok and self._audio.available:
                # sounddevice IS importable but the actual output stream
                # failed to open (device busy, permission denied, etc.) —
                # a runtime failure distinct from "never available", and
                # just as silent to the user without this.
                self._audio_status_label.configure(text="🔇 audio device error")
            elif ok:
                self._audio_status_label.configure(text="")
        self._seek_decoder(self._position)

    def pause(self) -> None:
        if not self._playing:
            return
        self._playing = False
        self._play_btn.configure(text="▶")
        self._position = self._current_time()
        self._audio.stop()

    def stop(self) -> None:
        self._playing = False
        self._play_btn.configure(text="▶")
        self._position = 0.0
        self._audio.stop()
        if self._decoder is not None:
            self._decoder.stop()
            self._decoder = None
        self._scrub.set(0)
        self._update_time_label()

    def seek(self, seconds: float) -> None:
        was_playing = self._playing
        if was_playing:
            self.pause()
        self._position = max(0.0, min(self._duration, float(seconds)))
        self._scrub.set(self._position)
        self._update_time_label()
        self._seek_decoder(self._position)
        if was_playing:
            self.play()

    # ---- internals ----

    def _on_scrub(self, value: float) -> None:
        self.seek(float(value))

    def _current_time(self) -> float:
        if not self._playing:
            return self._position
        return min(self._duration, self._play_started_pos + (time.monotonic() - self._play_started_at))

    def _seek_decoder(self, at: float) -> None:
        if self._decoder is not None:
            self._decoder.stop()
        self._frame_queue = queue.Queue(maxsize=6)
        if self._video_path is None:
            return
        self._decoder = _FrameDecoder(
            self._video_path, seek=at, width=self._proxy_w, height=self._proxy_h, fps=PROXY_FPS,
            out_queue=self._frame_queue,
        )
        self._decoder.start()

    def _update_time_label(self) -> None:
        def fmt(s: float) -> str:
            s = max(0.0, s)
            return f"{int(s // 60):02d}:{int(s % 60):02d}"

        self._time_label.configure(text=f"{fmt(self._current_time())} / {fmt(self._duration)}")

    def _tick(self) -> None:
        if self._playing:
            t = self._current_time()
            self._scrub.set(t)
            self._update_time_label()
            if self._on_time_change is not None:
                try:
                    self._on_time_change(t)
                except Exception:
                    pass
            if t >= self._duration:
                self.stop()
        # Drain the frame queue for the most recent frame at/near current time.
        latest = None
        try:
            while True:
                latest = self._frame_queue.get_nowait()
        except queue.Empty:
            pass
        if latest is not None:
            _pts, img = latest
            photo = ImageTk.PhotoImage(img)
            self._last_frame_photo = photo  # keep a reference (Tk needs it alive)
            # Reuse the one persistent image item (see __init__) instead of
            # delete()+create_image() every frame — real per-frame Tk
            # overhead avoided, not just a micro-optimization.
            self._canvas.itemconfigure(self._frame_item, image=photo, state="normal")
        # Drift-compensated scheduling: anchor the next fire time to a
        # fixed cadence from a monotonic clock rather than "N ms from
        # whenever this call happens to finish" (the previous pattern) —
        # if THIS tick's own work (queue drain, PhotoImage conversion,
        # canvas update, or unrelated UI activity sharing the same Tk
        # event loop, e.g. a timeline redraw) takes non-trivial time, the
        # old pattern let every tick's real-world interval grow past the
        # nominal 1000/PROXY_FPS ms, compounding into visibly uneven/
        # slowing playback over time. If we've fallen behind by more than
        # one full interval (a genuine stall, not just normal jitter),
        # resync to "now" instead of firing a burst of catch-up ticks.
        interval = 1000.0 / PROXY_FPS
        now = time.monotonic() * 1000.0
        if self._next_tick_at <= 0.0 or now - self._next_tick_at > interval:
            self._next_tick_at = now + interval
        else:
            self._next_tick_at += interval
        delay = max(1, round(self._next_tick_at - now))
        self.after(delay, self._tick)

    def destroy(self) -> None:
        self.stop()
        super().destroy()
