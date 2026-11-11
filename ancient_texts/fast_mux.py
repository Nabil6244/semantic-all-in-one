"""Fast final join for Enoch Template renders.

The shared final mux (video_generator.run_final_mux, a protected file) re-encodes the WHOLE film in one ffmpeg pass,
with every scene clip open as its own input and a chained xfade, as soon as a single soft transition is asked for
(this style asks for a few). Measured 2026-11-12: 40 five-second clips with 2 transitions took 91 s to join instead of
13 s, and the cost grows with every scene. That pass also shaved 0.05 s off every hard cut, so a long film ended shorter
than its voice-over and `-shortest` cut the voice's last seconds.

Here only the clips joined by a transition are re-encoded together (a few seconds each, several at once); every other
clip is stream-copied, exactly like a film without transitions. Hard cuts keep each clip's full length. Any failure
falls back to the original mux, so the render never stops because of this.
"""

from __future__ import annotations

import contextlib
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable, List, Optional, Sequence


def transition_groups(transitions: Sequence) -> List[List[int]]:
    """Clip indexes joined by real transitions, in order. ``transitions[i]`` is the boundary between clip i and i+1
    (None = hard cut). A clip on its own is a group of one."""
    groups: List[List[int]] = [[0]]
    for i, t in enumerate(transitions, start=1):
        if t is None:
            groups.append([i])
        else:
            groups[-1].append(i)
    return groups


def _probe_video(path: Path) -> tuple:
    """(frame rate text, timescale) of the clip's video stream; (None, None) when it cannot be read."""
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                            "stream=r_frame_rate,time_base", "-of", "json", str(path)],
                           capture_output=True, text=True, timeout=60)
        s = (json.loads(r.stdout or "{}").get("streams") or [{}])[0]
        tb = str(s.get("time_base") or "")
        ts = int(tb.split("/")[1]) if tb.startswith("1/") else None
        return s.get("r_frame_rate") or None, ts
    except Exception:
        return None, None


def _encode_group(vg, clips: List[Path], durations: List[float], transitions: list, out: Path, rate, timescale) -> Path:
    graph, label = vg.build_xfade_filter_complex(durations, transitions)
    cmd = ["ffmpeg", "-y", "-v", "error"]
    for p in clips:
        cmd += ["-i", str(p)]
    cmd += ["-filter_complex", graph, "-map", f"[{label}]", "-an", *vg._cpu_encode_argv(), "-pix_fmt", "yuv420p"]
    if rate:
        cmd += ["-r", str(rate)]
    if timescale:
        cmd += ["-video_track_timescale", str(timescale)]
    cmd.append(str(out))
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=max(300.0, 60.0 * sum(durations)))
    if r.returncode != 0 or not out.is_file():
        raise RuntimeError(f"transition segment failed: {(r.stderr or '').strip()[-400:]}")
    return out


def fast_final_mux(vg, original: Callable, *, concat_list_path, audio_path, output_path, bg_audio=None, bg_volume=0.25,
                   clip_files=None, scene_numbers=None, transitions=None, clip_durations=None,
                   log: Callable[[str], None] = print) -> None:
    has = bool(transitions) and any(t is not None for t in transitions)
    if not has or not clip_files or clip_durations is None or len(clip_files) < 2:
        return original(concat_list_path=concat_list_path, audio_path=audio_path, output_path=output_path,
                        bg_audio=bg_audio, bg_volume=bg_volume, clip_files=clip_files, scene_numbers=scene_numbers,
                        transitions=transitions, clip_durations=clip_durations)
    try:
        clips = [Path(p).resolve() for p in clip_files]
        durs = [float(d) for d in clip_durations]
        if len(durs) != len(clips) or len(transitions) != len(clips) - 1 or not all(p.is_file() for p in clips):
            raise RuntimeError("clip list does not match the plan")
        work = Path(concat_list_path).resolve().parent
        seg_dir = vg.render_clips_dir(work) / "_fast_mux"
        seg_dir.mkdir(parents=True, exist_ok=True)
        rate, timescale = _probe_video(clips[0])
        groups = transition_groups(transitions)
        segments: List[Optional[Path]] = [clips[g[0]] if len(g) == 1 else None for g in groups]
        jobs = [(k, g) for k, g in enumerate(groups) if len(g) > 1]
        log(f"[ENOCH TEMPLATE] Fast join: {len(jobs)} transition segment(s) re-encoded, "
            f"{sum(1 for g in groups if len(g) == 1)} clip(s) copied as they are.")
        with ThreadPoolExecutor(max_workers=max(1, min(4, len(jobs)))) as pool:
            futs = {k: pool.submit(_encode_group, vg, [clips[i] for i in g], [durs[i] for i in g],
                                   [transitions[i - 1] for i in g[1:]], seg_dir / f"seg_{k:05d}.mp4", rate, timescale)
                    for k, g in jobs}
            for k, f in futs.items():
                segments[k] = f.result()
        seg_list = work / "concat_fast.txt"
        vg.write_ffmpeg_concat_list(segments, seg_list)
    except Exception as exc:
        log(f"[ENOCH TEMPLATE] Fast join unavailable ({exc}); using the full re-encode.")
        return original(concat_list_path=concat_list_path, audio_path=audio_path, output_path=output_path,
                        bg_audio=bg_audio, bg_volume=bg_volume, clip_files=clip_files, scene_numbers=scene_numbers,
                        transitions=transitions, clip_durations=clip_durations)
    return original(concat_list_path=seg_list, audio_path=audio_path, output_path=output_path, bg_audio=bg_audio,
                    bg_volume=bg_volume, clip_files=segments, scene_numbers=None, transitions=None, clip_durations=None)


@contextlib.contextmanager
def applied(vg, log: Callable[[str], None] = print):
    """For one render: the renderer's final mux becomes the fast join; restored afterwards."""
    original = vg.run_final_mux

    def _mux(**kw):
        return fast_final_mux(vg, original, log=log, **kw)

    vg.run_final_mux = _mux
    try:
        yield
    finally:
        vg.run_final_mux = original
