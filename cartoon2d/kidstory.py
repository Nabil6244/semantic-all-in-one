"""Kids story files (.kidstory): one file that carries a whole 2D cartoon episode to the app.

Claude writes the episode (scenes/<name>.py with ch3.Episode, or any script + render json), runs it, then packs it:
    python3 cartoon2d/kidstory.py pack cartoon2d/scenes/ch3_ep01_playground_render.json  [out.kidstory]
The owner imports that file on the app's Kids Stories page; Generate voices and checks it, Render makes the video.

A .kidstory is a zip:
    story.json   {"format": "kidstory", "version": 1, "name", "title", "script": {...}, "render": {...}}
    bg/<file>    every background the episode uses (+ <file>.depth.npy: its depth map, so every computer gets the
                 same parallax even without the depth model)
The cast (cartoon2d/cast/<name>), props, hands and sounds ship with the app; check() says if a story needs one
that this app does not have.
"""
import io
import json
import re
import sys
import zipfile
from pathlib import Path

C2D = Path(__file__).resolve().parent
ROOT = C2D.parent
FORMAT, VERSION = "kidstory", 1


def _rel(p):
    p = Path(p)
    return p if p.is_absolute() else ROOT / p


def _title(render, script):
    for ln in script.get("lines", []):
        if ln.get("title"):
            return ln["title"].replace("\n", " ")
    return render.get("name", "story")


def pack(render_json, out=None):
    """Bundle a written episode (its render json + the script json it names + its backgrounds) into one file."""
    render_json = Path(render_json)
    render = json.loads(render_json.read_text())
    script = json.loads(_rel(render["script"]).read_text())
    name = render.get("name") or render_json.stem.replace("_render", "")
    out = Path(out) if out else C2D / "stories" / f"{name}.kidstory"
    out.parent.mkdir(parents=True, exist_ok=True)
    r = json.loads(json.dumps(render))
    files = {}
    for pname, pl in r.get("places", {}).items():
        src = _rel(pl["background"])
        if not src.is_file():
            raise SystemExit(f"place '{pname}': background missing: {src}")
        files.setdefault(src.name, src)
        pl["background"] = f"bg/{src.name}"
    if r.get("background"):
        src = _rel(r["background"])
        files.setdefault(src.name, src)
        r["background"] = f"bg/{src.name}"
    for k in ("timeline", "build", "script"):       # set again on the computer that renders it
        r.pop(k, None)
    doc = {"format": FORMAT, "version": VERSION, "name": name, "title": _title(render, script), "script": script, "render": r}
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("story.json", json.dumps(doc, indent=1))
        for fname, src in files.items():
            z.write(src, f"bg/{fname}")
            d = _depth(src)
            if d is not None:
                b = io.BytesIO()
                import numpy as np
                np.save(b, d.astype(np.float16))
                z.writestr(f"bg/{fname}.depth.npy", b.getvalue())
    print("PACKED", out, f"({len(files)} backgrounds, {len(script.get('lines', []))} lines)")
    return out


def _depth(src):
    try:
        from PIL import Image
        sys.path.insert(0, str(C2D))
        import scenery
        return scenery._depth(Image.open(src).convert("RGB"))
    except Exception as e:   # noqa: BLE001 - the renderer falls back to its own guess
        print("no depth map for", src.name, e)
        return None


def read(path):
    with zipfile.ZipFile(path) as z:
        doc = json.loads(z.read("story.json"))
        names = set(z.namelist())
    if doc.get("format") != FORMAT:
        raise ValueError("not a kids story file (story.json has no \"format\": \"kidstory\")")
    return doc, names


def check(path):
    """What the app shows after Generate's first step: errors (cannot render) or the story's title, length, cast."""
    errors = []
    try:
        doc, names = read(path)
    except Exception as e:   # noqa: BLE001
        return {"errors": [f"cannot read the story file: {e}"], "title": "", "lines": 0, "cast": []}
    if int(doc.get("version", 0)) > VERSION:
        errors.append(f"made for a newer app (story version {doc['version']}); update the app")
    r, s = doc.get("render", {}), doc.get("script", {})
    if not s.get("lines"):
        errors.append("the story has no lines")
    for pname, pl in r.get("places", {}).items():
        if pl.get("background") not in names:
            errors.append(f"place '{pname}': background {pl.get('background')} is not in the file")
    used = set()
    for ln in s.get("lines", []):
        w = ln.get("who")
        used |= set(w if isinstance(w, list) else [w])
    for w in sorted(used):
        c = r.get("cast", {}).get(w)
        if not c:
            errors.append(f"'{w}' speaks but is not in the cast")
        elif not (ROOT / c["dir"]).is_dir():
            errors.append(f"character '{w}' is not in this app ({c['dir']})")
        if w not in s.get("voices", {}):
            errors.append(f"'{w}' has no voice")
    words = sum(len(re.findall(r"\w+", ln.get("text", ""))) for ln in s.get("lines", []))
    return {"errors": errors, "title": doc.get("title", ""), "name": doc.get("name", "story"), "lines": len(s.get("lines", [])),
            "minutes": round(words / 125.0, 1), "cast": sorted(used)}


def unpack(path, work):
    """Write the episode into work/: script.json, render.json (paths made absolute), bg/*. Returns render.json."""
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    doc, names = read(path)
    with zipfile.ZipFile(path) as z:
        for n in names:
            if n.startswith("bg/") and not n.endswith("/") and ".." not in n:
                (work / n).parent.mkdir(parents=True, exist_ok=True)
                (work / n).write_bytes(z.read(n))
    (work / "script.json").write_text(json.dumps(doc["script"], indent=1))
    r = doc["render"]
    for pl in r.get("places", {}).values():
        pl["background"] = str((work / pl["background"]).resolve())
    if r.get("background"):
        r["background"] = str((work / r["background"]).resolve())
    build = (work / "build").resolve()
    r.update(script=str((work / "script.json").resolve()), build=str(build), timeline=str(build / "audio" / "timeline.json"),
             register=False)
    rp = work / "render.json"
    rp.write_text(json.dumps(r, indent=1))
    return rp


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "pack":
        pack(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
    elif len(sys.argv) >= 3 and sys.argv[1] == "check":
        print(json.dumps(check(sys.argv[2]), indent=1))
    else:
        sys.exit(__doc__)
