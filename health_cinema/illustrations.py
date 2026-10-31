"""The persistent illustration library for body-map scenes: every generated (or supplied) medical illustration is stored once with what it shows, so a later video reuses it
instead of paying for it again.

Folder: ~/HealthCinemaTools/illustrations/ (HEALTH_CINEMA_ILLUSTRATION_DIR overrides) holding index.json and the picture files.
Entry: id, topic (the condition or mechanism), view (what the picture shows: lesion, microscopic, mechanism ...), kind (card type), prompt, style (STYLE_ID), source (flow | supplied |
placeholder), file, sha256, created, notes. Lookup is by exact id first, then by topic + view + style. A placeholder is only ever used to check layout; it is never chosen for a final render.
Nothing here generates anything: `missing()` says what is absent and the app's existing Flow image workflow fills it (see bodymap_flow.py)."""
from __future__ import annotations
import hashlib, json, os, re, shutil, time
from pathlib import Path
from typing import Dict, List, Optional

STYLE_ID = "holo-medical-v1"
STYLE_PROMPT = ("Clean medical illustration for a premium health documentary, soft cinematic lighting on a deep navy background, restrained cyan accents, realistic proportions, "
                "no text, no labels, no logos, no watermark, not graphic or gory")
SOURCES = ("flow", "supplied", "placeholder")

def root() -> Path:
    env = os.environ.get("HEALTH_CINEMA_ILLUSTRATION_DIR")
    return Path(env).expanduser() if env else Path.home() / "HealthCinemaTools" / "illustrations"

def _slug(t: str) -> str: return re.sub(r"[^a-z0-9]+", "_", (t or "").lower()).strip("_")

def _index_path() -> Path: return root() / "index.json"

def load() -> List[dict]:
    from . import asset_index
    try: return list(asset_index.load_json(_index_path()))      # read once while the library index is unchanged
    except (OSError, ValueError): return []

def _save(entries: List[dict]) -> None:
    root().mkdir(parents=True, exist_ok=True); tmp = _index_path().with_suffix(".tmp"); tmp.write_text(json.dumps(entries, indent=1, ensure_ascii=False), encoding="utf-8"); tmp.replace(_index_path())

def sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""): h.update(chunk)
    return h.hexdigest()

def find(ref: str = "", topic: str = "", view: str = "", style: str = STYLE_ID, allow_placeholder: bool = False) -> Optional[dict]:
    """The stored illustration for an id, or for topic + view in this style (the newest one). None when there is none or its file is gone."""
    entries = [e for e in load() if (allow_placeholder or e.get("source") != "placeholder") and (root() / e.get("file", "")).is_file()]
    if ref:
        for e in entries:
            if e["id"] == ref: return dict(e, path=str(root() / e["file"]))
    if topic:
        t, v = _slug(topic), _slug(view)
        hit = [e for e in entries if _slug(e.get("topic")) == t and (not v or _slug(e.get("view")) == v) and e.get("style", STYLE_ID) == style]
        if hit: e = max(hit, key=lambda x: x.get("created", "")); return dict(e, path=str(root() / e["file"]))
    return None

def register(src_path, *, id: str, topic: str, view: str, kind: str, prompt: str, source: str, style: str = STYLE_ID, notes: str = "") -> dict:
    """Copy a picture into the library and record it (replacing an entry with the same id). Returns the entry."""
    if source not in SOURCES: raise ValueError(f"source must be one of {SOURCES}")
    root().mkdir(parents=True, exist_ok=True); ext = Path(src_path).suffix.lower() or ".png"; fn = f"{_slug(id)}{ext}"
    if Path(src_path).resolve() != (root() / fn).resolve(): shutil.copyfile(src_path, root() / fn)
    e = {"id": id, "topic": topic, "view": view, "kind": kind, "prompt": prompt, "style": style, "source": source, "file": fn, "sha256": sha256(root() / fn),
         "created": time.strftime("%Y-%m-%dT%H:%M:%S"), "notes": notes}
    entries = [x for x in load() if x["id"] != id] + [e]; _save(entries); return dict(e, path=str(root() / fn))

def missing(refs: List[dict]) -> List[dict]:
    """refs: [{ref, topic, view, kind, prompt}] -> the ones with no real (non-placeholder) picture in the library."""
    return [r for r in refs if not find(r.get("ref", ""), r.get("topic", ""), r.get("view", ""), r.get("style", STYLE_ID))]

def full_prompt(subject: str) -> str:
    """The generation prompt: the subject sentence + the shared style, so every illustration of the film looks like one set."""
    return f"{subject.strip().rstrip('.')}. {STYLE_PROMPT}."
