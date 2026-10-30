"""Benchmark timer for the story_fast pipeline. Stages run in a fixed order; Flow waiting is reported apart from local work."""
from __future__ import annotations
import json, os, threading, time
from contextlib import contextmanager

STAGES = ("csv", "flow_wait", "image_prep", "animation", "scene_render", "assemble")
LABELS = {"csv": "CSV / script", "flow_wait": "Flow waiting time (not local work)", "image_prep": "Image preparation",
          "animation": "Animation", "scene_render": "Scene render", "assemble": "Assemble"}


class StageTimer:
    def __init__(self):
        self.seconds = {s: 0.0 for s in STAGES}; self.counts = {s: 0 for s in STAGES}; self._lock = threading.Lock(); self.meta = {}

    def add(self, name, seconds, n=1):
        if name not in self.seconds: raise KeyError(f"unknown stage {name!r}; stages are {STAGES}")
        with self._lock: self.seconds[name] += float(seconds); self.counts[name] += n

    @contextmanager
    def stage(self, name):
        t = time.time()
        try: yield
        finally: self.add(name, time.time() - t)

    def local_seconds(self): return sum(v for k, v in self.seconds.items() if k != "flow_wait")

    def to_dict(self):
        return {"stages": {s: round(self.seconds[s], 3) for s in STAGES}, "counts": dict(self.counts),
                "local_seconds": round(self.local_seconds(), 3), "flow_wait_seconds": round(self.seconds["flow_wait"], 3), "meta": dict(self.meta)}

    def save(self, path):
        """Write atomically (default location state/story/bench.json is chosen by the caller)."""
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True); tmp = str(path) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f: json.dump(self.to_dict(), f, indent=1)
        os.replace(tmp, path); return str(path)

    def report(self):
        lines = ["Local processing time", "---------------------"]
        for s in STAGES:
            if s != "flow_wait": lines.append(f"  {LABELS[s]:<38}{self.seconds[s]:>10.1f} s   ({self.counts[s]})")
        lines.append(f"  {'Local total':<38}{self.local_seconds():>10.1f} s")
        lines += ["", "Waiting on Google Flow", "----------------------",
                  f"  {LABELS['flow_wait']:<38}{self.seconds['flow_wait']:>10.1f} s"]
        return "\n".join(lines)
