"""The persistent art library: every Flow-generated (or supplied) picture is stored once with what it shows and reused by later videos.

Folder: ~/RepTheoryAssets/ (REP_THEORY_ASSET_DIR overrides) holding index.json and the picture files. Entry: id, kind (character|prop|anatomy|comparison), subject, prompt,
style, source (flow|supplied), file, sha256, created. `cutout()` makes (and caches) a transparent copy by removing the near-black background connected to the picture's edge,
so art sits on the canvas without a visible box. Nothing here generates anything: reptheory/art.py fills the library through the app's existing Flow image workflow."""
from __future__ import annotations
import hashlib, json, os, re, shutil, time
from pathlib import Path
from typing import Dict, List, Optional

STYLE_ID = "rep-manga-v1"
SOURCES = ("flow", "supplied")

def root() -> Path:
    """The user's writable library: REP_THEORY_ASSET_DIR when set (development / advanced users), else ~/RepTheoryAssets. New pictures and cut-out caches are written here."""
    env = os.environ.get("REP_THEORY_ASSET_DIR")
    return Path(env).expanduser() if env else Path.home() / "RepTheoryAssets"

def bundled_root() -> Path:
    """The pictures that ship with the app (assets/reptheory, next to assets/fonts; added to the build by reptheory/packaging.py). Read-only: never written to."""
    return Path(__file__).resolve().parent.parent / "assets" / "reptheory"

def roots() -> List[Path]:
    """Where a picture is looked for, in order: the user's library first (so a development copy overrides), then the bundled set."""
    out: List[Path] = []
    for r in (root(), bundled_root()):
        if r not in out: out.append(r)
    return out

def _slug(t: str) -> str: return re.sub(r"[^a-z0-9]+", "_", (t or "").lower()).strip("_")
def _index_path() -> Path: return root() / "index.json"

def _load_one(r: Path) -> List[dict]:
    try: return json.loads((r / "index.json").read_text(encoding="utf-8"))
    except (OSError, ValueError): return []

def load() -> List[dict]:
    """Every entry whose picture file exists, user library first; an id in both places is the user's. Each entry carries `dir` (where its file is)."""
    out, seen = [], set()
    for r in roots():
        for e in _load_one(r):
            if e.get("id") in seen or not (r / e.get("file", "")).is_file(): continue
            seen.add(e["id"]); out.append(dict(e, dir=str(r)))
    return out

def _save(entries: List[dict]) -> None:
    entries = [{k: v for k, v in e.items() if k != "dir"} for e in entries]
    root().mkdir(parents=True, exist_ok=True); tmp = _index_path().with_suffix(".tmp"); tmp.write_text(json.dumps(entries, indent=1, ensure_ascii=False), encoding="utf-8"); tmp.replace(_index_path())

def sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""): h.update(chunk)
    return h.hexdigest()

def find(ref: str) -> Optional[dict]:
    for e in load():
        if e["id"] == ref: return dict(e, path=str(Path(e["dir"]) / e["file"]))
    return None

def where() -> str:
    """For error messages: every place a picture is looked for."""
    return ", ".join(str(r) for r in roots())

def register(src_path, *, id: str, kind: str, subject: str, prompt: str, source: str, style: str = STYLE_ID, notes: str = "") -> dict:
    if source not in SOURCES: raise ValueError(f"source must be one of {SOURCES}")
    root().mkdir(parents=True, exist_ok=True); fn = f"{_slug(id)}{Path(src_path).suffix.lower() or '.png'}"
    if Path(src_path).resolve() != (root() / fn).resolve(): shutil.copyfile(src_path, root() / fn)
    e = {"id": id, "kind": kind, "subject": subject, "prompt": prompt, "style": style, "source": source, "file": fn, "sha256": sha256(root() / fn), "created": time.strftime("%Y-%m-%dT%H:%M:%S"), "notes": notes}
    _save([x for x in _load_one(root()) if x["id"] != id] + [e]); return dict(e, path=str(root() / fn))

def missing(ids: List[str]) -> List[str]: return [i for i in ids if not find(i)]

def cutout(ref: str, low: int = 5, high: int = 30):
    """RGBA PIL image for a stored picture: black becomes transparent by brightness (fully clear at or below `low`, fully opaque at `high`), so the art sits on the near-black canvas with
    no box and no black holes between arms or under a bar; dark ink and hair simply show the canvas, which is almost the same colour. Cropped to its content, cached as <file>.cut2.png."""
    import numpy as np
    from PIL import Image
    e = find(ref)
    if e is None: raise FileNotFoundError(f"art '{ref}' was not found in the bundled pictures or the user library (looked in: {where()}). Add it with reptheory.library.register, or restore assets/reptheory")
    src = Path(e["path"]); cache = src.with_name(src.stem + ".cut2.png") if Path(e["dir"]) == root() else root() / "_cache" / (src.stem + ".cut2.png")      # the bundled folder is read-only: its cut-outs are cached in the user folder
    if cache.is_file() and cache.stat().st_mtime >= src.stat().st_mtime: return Image.open(cache).convert("RGBA")
    im = Image.open(src).convert("RGB"); a = np.asarray(im).max(axis=2).astype(np.float32); alpha = np.clip((a - low) / float(high - low), 0, 1)
    out = im.convert("RGBA"); out.putalpha(Image.fromarray((alpha * 255).astype("uint8"))); bbox = out.getchannel("A").point(lambda v: 255 if v > 24 else 0).getbbox()
    if bbox: out = out.crop(bbox)
    try: cache.parent.mkdir(parents=True, exist_ok=True); out.save(cache)
    except OSError: pass      # a read-only install still renders: the cut-out is just made again next time
    return out
