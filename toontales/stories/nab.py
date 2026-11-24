"""Nabilllll night batch (2026-11-23): Walt & Pip Flow stories from nab_a/_b/_c.
    python3 toontales/stories/nab.py [story_id ...]   -> stories/<id>/plan.json"""
import json, sys
from pathlib import Path
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
STORIES = {}
for m in ("nab_a", "nab_b", "nab_c"):
    try:
        STORIES.update(__import__(m).STORIES)
    except ImportError:
        pass


def build(sid):
    st = STORIES[sid]
    shots = [dict(x) for x in st["shots"]]
    try:
        from nab_extra import EXTRA
    except ImportError:
        EXTRA = {}
    ins = EXTRA.get(sid, [])
    for k in range(len(ins) - 1, -1, -1):
        after, extra = ins[k]
        shots.insert(after, dict(extra))
    for i, s in enumerate(shots):
        s["id"] = f"s{i + 1:02d}"
    plan = {"id": sid, "title": st["title"], "topic": st["topic"], "cast": ["walt", "pip"], "places": st["places"],
            "hook_title": st["hook_title"], "keywords": st["keywords"], "sources": st["sources"], "shots": shots,
            "version": "nabilllll"}
    d = HERE / sid
    d.mkdir(exist_ok=True)
    (d / "plan.json").write_text(json.dumps(plan, indent=1, ensure_ascii=False))
    print(f"{sid}: {len(shots)} shots, {sum(len(s['text'].split()) for s in shots)} words")


if __name__ == "__main__":
    for sid in sys.argv[1:] or STORIES:
        build(sid)
