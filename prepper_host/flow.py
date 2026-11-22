"""Flow pictures and clips for Prepper Host, cached in out/prepper_host/library/<key>.png|.mp4 so nothing is made twice.

Pictures with the host attach his reference pictures (portrait + set): Flow keeps his face and clothes. Talking clips are
Flow "Ingredients" videos (reference pictures + a spoken line) and cost Flow video credits; pictures are free.
Uses the Flow engine that is already running (the app's), else starts one for the run and stops only that one.
Never raises for Flow trouble: what Flow could not make is listed and the renderer draws a stand-in.
"""
import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "out" / "prepper_host" / "library"
URL = "ws://127.0.0.1:8787/ws"
CLIP_LANES = 4   # Flow clips made at once, one per account (Flow profiles)
CLIP_AGENT = True   # clips through Flow's agent, several per message (FLOW_CLIP_AGENT=0 = the one-by-one path)


def lib_path(key, ext="png"):
    return LIB / f"{key}.{ext}"


def have(key, ext="png"):
    p = lib_path(key, ext)
    return str(p) if p.is_file() and p.stat().st_size > 0 else None


def _up(tries=3):
    """Is an engine listening? A busy engine can be slow to answer: a few patient tries before saying no, because 'no'
    starts a second engine that replaces the app's (and stops the app's Flow work)."""
    for i in range(tries):
        try:
            urllib.request.urlopen("http://127.0.0.1:8787/", timeout=6)
            return True
        except urllib.error.HTTPError:
            return True
        except Exception:  # noqa: BLE001
            if i + 1 < tries:
                time.sleep(2)
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
            if not self.client.is_alive():   # a dead engine is not busy: go on, the next send starts a fresh one
                return
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
        self._wait_idle()   # a new Generate stops the engine's running batch: never send on top of the app's work
        events = []
        unsub = self.client.subscribe(events.append)
        try:
            self.client.generate(prompts, settings, accounts, prompt_keys=keys)
            # Wait for the batch, but notice a dead engine (the app closed, it crashed) within seconds instead of
            # sitting out the whole timeout: the caller's next try starts a fresh engine.
            t_end = time.time() + timeout
            while time.time() < t_end:
                if any(m.get("type") == "GENERATE_DONE" or m.get("generateError") for m in events):
                    break
                if not self.client.is_alive():
                    self.log("prepper host: the Flow engine closed during the batch; what arrived is kept, the rest is retried")
                    break
                time.sleep(2.0)
            else:
                self.log("prepper host: Flow wait ended (timed out); what arrived is kept")
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

    def _agent_clips(self, todo, vid, accounts, refs, voice, timeout, attempt):
        """All clips through Flow's agent, up to 4 per message (live test 2026-11-23: 2 clips in ~50 s, faces and voice right).
        The agent's clips come back in any order, so each one is matched to its line by what he says in it."""
        pick = [x.strip() for x in os.environ.get("FLOW_CLIP_ACCOUNTS", "").split(",") if x.strip()]
        if pick and accounts:
            accounts = [a for a in accounts if any(a.startswith(x) for x in pick)] or accounts
        run = LIB / "runs" / time.strftime("vid_%Y%m%d_%H%M%S") / f"agent_{todo[0][0]}"
        run.mkdir(parents=True, exist_ok=True)
        st = {**vid, "mediaKind": "video", "imageCount": 1, "autoDownload": True, "outputDir": str(run),
              "folder": "prepper_host", "generationMode": "ui", "agentVideoBatch": True}
        if refs:
            st["referenceImages"] = list(refs)
        if voice and voice.get("name"):
            st["voice"] = {"name": voice["name"], "performance": voice.get("performance", "")}
        self.log(f"prepper host: Flow agent is making {len(todo)} clip(s), up to 4 per message (try {attempt + 1})")
        got, errs = self._run([p for _, p in todo], [f"ph_{k}" for k, _ in todo], st, accounts[:1] if accounts else None,
                              max(timeout, 900 * ((len(todo) + 3) // 4)))
        files = sorted({str(p) for p in got.values() if str(p).endswith(".mp4") and Path(p).is_file()})
        for k, path in match_clips(todo, files).items():
            shutil.copyfile(path, lib_path(k, "mp4"))
        if errs:
            self.log(f"prepper host: Flow said: {'; '.join(sorted(errs))[:300]}")

    def clips(self, jobs, refs=None, cancel=None, tries=2, timeout=1500, voice=None):
        """jobs: {key: prompt} -> {key: mp4 path}. One Flow video per job (uses credits); Ingredients mode with refs."""
        _img, vid, accounts, _mode = _settings()
        LIB.mkdir(parents=True, exist_ok=True)
        for attempt in range(tries):
            todo = [(k, p) for k, p in jobs.items() if not have(k, "mp4")]
            if not todo or (cancel and cancel()):
                break
            if CLIP_AGENT and os.environ.get("FLOW_CLIP_AGENT", "1") != "0":
                self._agent_clips(todo, vid, accounts, refs, voice, timeout, attempt)
                continue
            # One clip per Flow account at the same time: a batch of up to CLIP_LANES clips, one account each.
            pick = [x.strip() for x in os.environ.get("FLOW_CLIP_ACCOUNTS", "").split(",") if x.strip()]
            if pick and accounts:      # only these accounts (id or id prefix), e.g. the ones that still have credits
                accounts = [a for a in accounts if any(a.startswith(x) for x in pick)] or accounts
            lanes = max(1, min(CLIP_LANES, len(accounts) if accounts else CLIP_LANES))
            use = list(accounts)[:lanes] if accounts else None
            for i in range(0, len(todo), lanes):
                if cancel and cancel():
                    break
                part = todo[i:i + lanes]
                run = LIB / "runs" / time.strftime("vid_%Y%m%d_%H%M%S") / part[0][0]
                run.mkdir(parents=True, exist_ok=True)
                st = {**vid, "mediaKind": "video", "imageCount": 1, "autoDownload": True, "outputDir": str(run),
                      "folder": "prepper_host", "generationMode": "ui"}
                if refs:
                    st["referenceImages"] = list(refs)
                if voice and voice.get("name"):       # one of Flow's own voices, attached to every clip
                    st["voice"] = {"name": voice["name"], "performance": voice.get("performance", "")}
                names = ", ".join(k for k, _ in part)
                self.log(f"prepper host: Flow is making {len(part)} clip(s) on {len(use) if use else 'all'} account(s) "
                         f"({names}, try {attempt + 1})")
                got, errs = self._run([p for _, p in part], [f"ph_{k}" for k, _ in part], st,
                                      use[:len(part)] if use else None, timeout)
                for idx, path in got.items():
                    if idx < len(part) and Path(path).is_file() and str(path).endswith(".mp4"):
                        shutil.copyfile(path, lib_path(part[idx][0], "mp4"))
                if len(part) == 1 and not have(part[0][0], "mp4"):   # older engines: take the newest mp4 of the run
                    mp4s = sorted(run.rglob("*.mp4"), key=lambda q: q.stat().st_mtime)
                    if mp4s:
                        shutil.copyfile(mp4s[-1], lib_path(part[0][0], "mp4"))
                if errs:
                    self.log(f"prepper host: Flow said: {'; '.join(sorted(errs))[:300]}")
        return {k: have(k, "mp4") for k in jobs if have(k, "mp4")}


def _said(prompt):
    import re
    m = re.search(r'says[^"]*"([^"]+)"', prompt) or re.search(r'"([^"]+)"', prompt)
    return (m.group(1) if m else prompt).lower()


def _words(t):
    import re
    return re.findall(r"[a-z0-9']+", t.lower())


def match_clips(todo, files):
    """{key: file}: each clip goes to the line it actually says (Whisper), best match first; a clip that matches no line
    well (under half its words) is left out rather than put on the wrong line."""
    if not files:
        return {}
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel("base.en", device="cpu", compute_type="int8")
        heard = {f: " ".join(s.text for s in model.transcribe(f)[0]) for f in files}
    except Exception:  # noqa: BLE001 - no Whisper: keep the order Flow gave (one clip, or same order)
        return {k: f for (k, _), f in zip(todo, files)} if len(files) == 1 else {}
    pairs = []
    for k, p in todo:
        want = _words(_said(p))
        for f, txt in heard.items():
            got = set(_words(txt))
            score = sum(1 for w in want if w in got) / max(1, len(want))
            pairs.append((score, k, f))
    out, used = {}, set()
    for score, k, f in sorted(pairs, reverse=True):
        if score < 0.5 or k in out or f in used:
            continue
        out[k] = f
        used.add(f)
    return out
