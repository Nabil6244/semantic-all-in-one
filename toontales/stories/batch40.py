"""Batch 40 (2026-11-20): new Walt & Pip Flow-painted Toon Tales stories (engaging_v2 shape: ~24 shots, ~45 s).
Stories live in batch40_a.py / _b / _c (STORIES dicts with title, topic, places + shots).
    python3 toontales/stories/batch40.py [story_id ...]   -> stories/<id>/plan.json
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from batch40_a import STORIES as A  # noqa: E402
try:
    from batch40_b import STORIES as B  # noqa: E402
except ImportError:
    B = {}
try:
    from batch40_c import STORIES as C  # noqa: E402
except ImportError:
    C = {}

STORIES = {**A, **B, **C}


def build(sid):
    st = STORIES[sid]
    shots = st["shots"]
    for i, s in enumerate(shots):
        s["id"] = f"s{i + 1:02d}"
    plan = {"id": sid, "title": st["title"], "topic": st["topic"], "cast": ["walt", "pip"], "places": st["places"],
            "hook_title": st["hook_title"], "keywords": st["keywords"], "sources": st["sources"], "shots": shots,
            "version": "batch40"}
    d = HERE / sid
    d.mkdir(exist_ok=True)
    (d / "plan.json").write_text(json.dumps(plan, indent=1, ensure_ascii=False))
    words = sum(len(s["text"].split()) for s in shots)
    print(f"{sid}: {len(shots)} shots, {words} words")


if __name__ == "__main__":
    for sid in sys.argv[1:] or STORIES:
        build(sid)
