"""Python entry for the City Timelapse engine (the app's City Timelapse page calls this; nothing else knows the engine's insides).
    check(csv)            story CSV -> errors, warnings, length; a story whose world is not built yet gets `world_build`
    build_world(wb)       builds that world once (elevation tiles + OpenStreetMap water and streets: the caller asks first)
    plan(csv, work)       -> work/timeline.json, no rendering
    render(csv, work, …)  -> silent video on the GPU -> music bed (+ optional voice-over) at -14 LUFS -> final mp4 + credits
Every call takes progress(fraction, message) and cancel() callables. No Gemini, no paid API."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Optional

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
TAG = "[City Timelapse]"


class Cancelled(Exception):
    pass


def _binaries():
    try:
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        from map_scene.render import _ffmpeg, _node
        return _node(), _ffmpeg()
    except Exception:  # noqa: BLE001 - running outside the app
        return shutil.which("node") or "node", shutil.which("ffmpeg") or "ffmpeg"


def _popen(cmd, **kw):
    try:
        from providers import hidden_subprocess as hs
        return hs.popen(cmd, **kw)
    except Exception:  # noqa: BLE001
        return subprocess.Popen(cmd, **kw)


def _env():
    _, ffmpeg = _binaries()
    env = dict(os.environ)
    if ffmpeg and str(ffmpeg) not in ("ffmpeg", ""):
        env["PATH"] = str(Path(str(ffmpeg)).resolve().parent) + os.pathsep + env.get("PATH", "")
    return env


def _stream(cmd: list, *, progress=None, cancel=None, log=print, on_event=None, timeout_s: float = 6 * 3600.0) -> dict:
    """Run a command that prints one JSON object per line; collect them. Stop kills it at once."""
    proc = _popen(cmd, cwd=str(HERE), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", env=_env())
    err: list = []
    threading.Thread(target=lambda: err.extend(proc.stderr), daemon=True).start()
    timer = threading.Timer(timeout_s, proc.kill)
    timer.start()
    out: dict = {"warnings": [], "error": None, "events": []}

    def watch() -> None:
        while proc.poll() is None:
            if cancel and cancel():
                proc.kill()
                return
            time.sleep(0.3)

    threading.Thread(target=watch, daemon=True).start()
    try:
        for raw in proc.stdout:
            try:
                ev = json.loads(raw)
            except ValueError:
                continue
            k = ev.get("event")
            out["events"].append(ev)
            if k == "warning":
                out["warnings"].append(ev.get("message"))
                log(f"{TAG} {ev.get('message')}")
            elif k == "error":
                out["error"] = ev
            elif k:
                out[k] = ev
            if on_event:
                on_event(ev)
        proc.wait(timeout=60)
    finally:
        timer.cancel()
        if proc.poll() is None:
            proc.kill()
    if cancel and cancel():
        raise Cancelled("City Timelapse cancelled.")
    if proc.returncode and not out["error"]:
        out["error"] = {"message": "".join(err)[-600:] or f"exited {proc.returncode}"}
    return out


def _node_cmd(*args) -> list:
    node, _ = _binaries()
    return [node, str(HERE / "render.mjs"), *[str(a) for a in args]]


def check(csv: str, *, cancel=None, log=print) -> dict:
    """Plan without rendering: errors, warnings, duration; world_build when the story's world is missing."""
    r = _stream(_node_cmd(str(Path(csv).resolve()), "--plan", "--outdir", str(HERE / "out" / "_check")), cancel=cancel, log=log)
    res = {"errors": [], "warnings": r["warnings"], "duration": (r.get("plan") or {}).get("duration"), "eras": (r.get("plan") or {}).get("eras")}
    e = r["error"]
    if e:
        if e.get("code") == "NO_WORLD":
            res["world_build"] = _world_request(csv, e.get("world"))
            if not res["world_build"]:
                res["errors"].append(e.get("message"))
        else:
            res["errors"].append(e.get("message"))
    p = r.get("plan") or {}
    if not e and p.get("world") and p.get("landuse") is False and not (HERE / "worlds" / str(p["world"]) / "landuse_skipped").exists():
        res["landuse_build"] = _landuse_request(str(p["world"]))
    return res


def _landuse_request(world_id: str) -> Optional[dict]:
    """A world built before land use existed: its centre and size, to add land use (parks, fields, sand, built-up: one small OpenStreetMap download)."""
    try:
        meta = json.loads((HERE / "worlds" / world_id / "meta.json").read_text(encoding="utf-8"))
        return {"id": world_id, "center": meta["center"], "size_m": meta["size_m"]}
    except Exception:  # noqa: BLE001
        return None


def skip_landuse(world_id: str) -> None:
    """The user said no: do not ask again for this world."""
    (HERE / "worlds" / world_id / "landuse_skipped").write_text("skipped", encoding="utf-8")


def add_landuse(lb: dict, *, log=print) -> bool:
    """Adds land use to an existing world (DOWNLOADS from OpenStreetMap: call only after the user agreed). True when it worked."""
    from importlib import util
    spec = util.spec_from_file_location("ctl_build_real", HERE / "tools" / "build_real.py")
    real = util.module_from_spec(spec)
    spec.loader.exec_module(real)
    wid = str(lb["id"])
    log(f"{TAG} adding land use to world '{wid}'")
    w = real.World(wid)
    res = real.build_landuse(w)
    ok = "landuse_areas" in res
    if ok:
        meta = dict(w.meta, landuse=True)
        (w.dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    else:
        log(f"{TAG} land use could not be downloaded now; the ground follows the climate rule")
    return ok


def _world_request(csv: str, world_id: str) -> Optional[dict]:
    """The plan row's centre and size (km) for a world that is not built yet."""
    sys.path.insert(0, str(HERE))
    text = Path(csv).read_text(encoding="utf-8-sig")
    import csv as _csv
    import io
    for row in _csv.DictReader(io.StringIO(text)):
        if (row.get("row") or "").strip().lower() != "plan":
            continue
        focus = (row.get("focus") or "").replace(";", ",").split(",")
        try:
            lon, lat = float(focus[0]), float(focus[1])
        except (ValueError, IndexError):
            return None
        try:
            extra = json.loads(row.get("extra") or "{}")
        except ValueError:
            extra = {}
        size = float(extra.get("size") or 8)
        tiles = int((size * 1000 / (2446 * max(0.2, abs(__import__("math").cos(lat * 3.14159 / 180)))) + 2) ** 2)
        return {"id": world_id, "center": [lon, lat], "size": size, "download_mb_est": round(tiles * 0.09 + 6, 1)}
    return None


def build_world(wb: dict, *, progress=None, cancel=None, log=print) -> str:
    """Builds the story's missing world (check()'s `world_build`: id, center, size) in-process with tools/build_city.py.
    This DOWNLOADS elevation tiles and OpenStreetMap data: call it only after the user agreed. meta.json is written last, so a
    stopped or failed build still counts as not built and the next Generate asks again."""
    from importlib import util
    spec = util.spec_from_file_location("ctl_build_city", HERE / "tools" / "build_city.py")
    mod = util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    wid = str(wb["id"])

    def on_tile(done, total):
        if cancel and cancel():
            raise Cancelled("City Timelapse cancelled.")
        if progress:
            progress(0.85 * done / max(1, total), f"Building world '{wid}': elevation {done}/{total}")

    log(f"{TAG} building world '{wid}' around {wb['center']} ({wb.get('size', 8)} km)")
    mod.build(wid, (float(wb["center"][0]), float(wb["center"][1])), float(wb.get("size", 8)), on_tile=on_tile)
    if progress:
        progress(1.0, f"World '{wid}' built")
    return wid


def plan(csv: str, work: str, *, progress: Optional[Callable] = None, cancel: Optional[Callable] = None, log=print) -> dict:
    w = Path(work)
    w.mkdir(parents=True, exist_ok=True)
    r = _stream(_node_cmd(str(Path(csv).resolve()), "--plan", "--outdir", str(w)), cancel=cancel, log=log)
    if r["error"]:
        raise RuntimeError(r["error"].get("message"))
    p = r.get("plan") or {}
    if progress:
        progress(1.0, "Planned")
    return {"duration": p.get("duration", 0), "eras": p.get("eras", 0), "lots": p.get("lots", 0), "landmarks": p.get("landmarks", 0),
            "warnings": r["warnings"], "timeline": str(w / "timeline.json")}


def render(csv: str, work: str, *, output: str, resolution: int = 1080, voiceover: Optional[str] = None, music: Optional[str] = None,
           progress: Optional[Callable] = None, cancel: Optional[Callable] = None, log=print) -> dict:
    w = Path(work)
    w.mkdir(parents=True, exist_ok=True)
    H = 1080 if resolution >= 1080 else 720
    W = H * 16 // 9
    video = w / "video_silent.mp4"

    def on(ev):
        if ev.get("event") == "progress" and progress:
            progress(0.92 * ev["frame"] / max(1, ev["frames"]), f"frame {ev['frame']}/{ev['frames']}")
    r = _stream(_node_cmd(str(Path(csv).resolve()), "--out", str(video), "--w", W, "--h", H, "--outdir", str(w)), progress=progress, cancel=cancel, log=log, on_event=on)
    if r["error"]:
        raise RuntimeError(r["error"].get("message"))
    seconds = float((r.get("done") or {}).get("seconds") or 0)
    if progress:
        progress(0.94, "Music")
    track = music or _plan_music(csv) or "ascending_the_vale"
    sys.path.insert(0, str(HERE / "tools"))
    import music_bed
    bed = music_bed.make(seconds, w / "mix.wav", track, voiceover)
    _, ffmpeg = _binaries()
    subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", str(video), "-i", bed["file"], "-map", "0:v", "-map", "1:a", "-c:v", "copy",
                    "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", output], check=True, timeout=1800)
    tl = json.loads((w / "timeline.json").read_text(encoding="utf-8")) if (w / "timeline.json").is_file() else {}
    credits = [bed["credit"], *tl.get("credits", [])]
    Path(output).with_suffix(".credits.txt").write_text("\n".join(credits) + "\n", encoding="utf-8")
    for c in credits:
        log(f"{TAG} credit: {c}")
    if progress:
        progress(1.0, "Done")
    return {"output": output, "seconds": seconds, "credits": credits, "frame_ms": (r.get("done") or {}).get("frame_ms")}


def _plan_music(csv: str) -> Optional[str]:
    import csv as _csv
    import io
    for row in _csv.DictReader(io.StringIO(Path(csv).read_text(encoding="utf-8-sig"))):
        if (row.get("row") or "").strip().lower() == "plan":
            try:
                return json.loads(row.get("extra") or "{}").get("music")
            except ValueError:
                return None
    return None
