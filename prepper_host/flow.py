"""Flow pictures and clips for Prepper Host, cached in out/prepper_host/library/<key>.png|.mp4 so nothing is made twice.

Pictures with the host attach his reference pictures (portrait + set): Flow keeps his face and clothes. Talking clips are
Flow "Ingredients" videos (reference pictures + a spoken line) and cost Flow video credits; pictures are free.
Uses the Flow engine that is already running (the app's), else starts one for the run and stops only that one.
Never raises for Flow trouble: what Flow could not make is listed and the renderer draws a stand-in.
"""
import json
import shutil
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "out" / "prepper_host" / "library"
URL = "ws://127.0.0.1:8787/ws"


def lib_path(key, ext="png"):
    return LIB / f"{key}.{ext}"


def have(key, ext="png"):
    p = lib_path(key, ext)
    return str(p) if p.is_file() and p.stat().st_size > 0 else None


def _up():
    try:
        urllib.request.urlopen("http://127.0.0.1:8787/", timeout=2)
        return True
    except urllib.error.HTTPError:
        return True
    except Exception:  # noqa: BLE001
        return False


def _settings():
    s = json.loads((ROOT / "settings.json").read_text(encoding="utf-8"))
    mode = "agent" if s.get("flow_agent_images") else ("ui" if s.get("flow_ui_mode", True) else "rpc")
    fs = s.get("flow_settings", {})
    img = {"model": fs.get("model"), "aspectRatio": fs.get("aspectRatio", "IMAGE_ASPECT_RATIO_LANDSCAPE"), "generationMode": mode}
    prof = next((p for p in s.get("video_profiles", []) if p["id"] == s.get("default_video_profile_id", "default")),
                (s.get("video_profiles") or [{}])[0])
    vid = {"videoModel": prof.get("model"), "aspectRatio": prof.get("aspectRatio", "IMAGE_ASPECT_RATIO_LANDSCAPE"),
           "videoDuration": int(prof.get("duration") or 8), "videoResolution": prof.get("resolution", "720p")}
    return img, vid, prof.get("account_ids"), mode


class Session:
    """One connection to the Flow engine for a Generate run."""

    def __init__(self, log=print):
        self.log, self.mgr, self.client = log, None, None

    def __enter__(self):
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        from providers.flow.client import FlowClient
        if _up():
            self.client = FlowClient(URL, log=lambda m: None)
            self.client.connect()
        else:
            from providers.flow.engine_manager import FlowEngineManager
            self.log("prepper host: starting the Flow engine for this run")
            self.mgr = FlowEngineManager(log=lambda m: None)
            self.client = self.mgr.ensure_running()
        time.sleep(1.0)
        self._wait_idle()
        return self

    def _wait_idle(self, limit=1800):
        """Another run (the app's) is using Flow: wait for it instead of sending on top of it."""
        t_end = time.time() + limit
        said = False
        while time.time() < t_end:
            try:
                st = self.client.get_state() or {}
            except Exception:  # noqa: BLE001
                return
            if not any(st.get(k) for k in ("isRunning", "running", "generating", "isGenerating")):
                return
            if not said:
                self.log("prepper host: Flow is busy with another run; waiting for it to finish")
                said = True
            time.sleep(10)

    def __exit__(self, *exc):
        try:
            self.client.close()
        except Exception:  # noqa: BLE001
            pass
        if self.mgr is not None:
            try:
                self.mgr.stop()
            except Exception:  # noqa: BLE001
                pass

    def _ensure(self):
        """The engine can go away mid-run (another run that started it ended): reconnect, or start one for this run."""
        try:
            if self.client is not None and self.client.is_alive():
                return
        except Exception:  # noqa: BLE001
            pass
        from providers.flow.client import FlowClient
        try:
            self.client.close()
        except Exception:  # noqa: BLE001
            pass
        if _up():
            self.client = FlowClient(URL, log=lambda m: None)
            self.client.connect()
        else:
            from providers.flow.engine_manager import FlowEngineManager
            self.log("prepper host: the Flow engine went away; starting it again")
            self.mgr = self.mgr or FlowEngineManager(log=lambda m: None)
            self.client = self.mgr.ensure_running()
        time.sleep(1.0)

    def _run(self, prompts, keys, settings, accounts, timeout):
        self._ensure()
        events = []
        unsub = self.client.subscribe(events.append)
        try:
            self.client.generate(prompts, settings, accounts, prompt_keys=keys)
            self.client.wait_for(lambda m: m.get("type") == "GENERATE_DONE" or bool(m.get("generateError")), timeout=timeout)
        except Exception as e:  # noqa: BLE001 - a timeout keeps whatever arrived
            self.log(f"prepper host: Flow wait ended ({type(e).__name__}: {e})")
        finally:
            unsub()
        got = {}
        for e in events:
            if e.get("type") == "PROMPT_RESULT" and e.get("status") == "done" and e.get("path") and isinstance(e.get("index"), int):
                got[e["index"]] = e["path"]
        errs = {str(e.get("generateError") or e.get("error"))[:160] for e in events if e.get("generateError") or e.get("error")}
        return got, errs

    def pictures(self, jobs, refs=None, cancel=None, tries=3, timeout=2400):
        """jobs: {key: prompt}. -> {key: path} for everything now in the library."""
        img, _vid, accounts, mode = _settings()
        LIB.mkdir(parents=True, exist_ok=True)
        for attempt in range(tries):
            todo = [(k, p) for k, p in jobs.items() if not have(k)]
            if not todo or (cancel and cancel()):
                break
            for i in range(0, len(todo), 24):
                part = todo[i:i + 24]
                run = LIB / "runs" / time.strftime("img_%Y%m%d_%H%M%S") / f"{attempt}_{i}"
                run.mkdir(parents=True, exist_ok=True)
                st = {**img, "mediaKind": "image", "imageCount": 1, "autoDownload": True, "outputDir": str(run)}
                if refs:
                    st["referenceImages"] = list(refs)
                self.log(f"prepper host: Flow is making {len(part)} picture(s){' with the host' if refs else ''} (try {attempt + 1})")
                got, errs = self._run([p for _, p in part], [f"ph_{k}" for k, _ in part], st,
                                      accounts if mode == "agent" else None, timeout)
                for idx, path in got.items():
                    if idx < len(part) and Path(path).is_file():
                        shutil.copyfile(path, lib_path(part[idx][0]))
                if errs:
                    self.log(f"prepper host: Flow said: {'; '.join(sorted(errs))[:300]}")
                if cancel and cancel():
                    break
        return {k: have(k) for k in jobs if have(k)}

    def clips(self, jobs, refs=None, cancel=None, tries=2, timeout=1500):
        """jobs: {key: prompt} -> {key: mp4 path}. One Flow video per job (uses credits); Ingredients mode with refs."""
        _img, vid, accounts, _mode = _settings()
        LIB.mkdir(parents=True, exist_ok=True)
        for attempt in range(tries):
            todo = [(k, p) for k, p in jobs.items() if not have(k, "mp4")]
            if not todo or (cancel and cancel()):
                break
            for k, p in todo:
                if cancel and cancel():
                    break
                run = LIB / "runs" / time.strftime("vid_%Y%m%d_%H%M%S") / k
                run.mkdir(parents=True, exist_ok=True)
                st = {**vid, "mediaKind": "video", "imageCount": 1, "autoDownload": True, "outputDir": str(run),
                      "folder": "prepper_host", "generationMode": "ui"}
                if refs:
                    st["referenceImages"] = list(refs)
                self.log(f"prepper host: Flow is making a clip ({k}, try {attempt + 1})")
                self._run([p], [f"ph_{k}"], st, accounts, timeout)
                mp4s = sorted(run.rglob("*.mp4"), key=lambda q: q.stat().st_mtime)
                if mp4s:
                    shutil.copyfile(mp4s[-1], lib_path(k, "mp4"))
        return {k: have(k, "mp4") for k in jobs if have(k, "mp4")}
