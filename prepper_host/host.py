"""The host: one AI character kept the same in every picture by Flow reference images.

A host pack lives in out/prepper_host/hosts/<name>/:
  portrait.png   waist-up reference (face + clothes anchor)       -> attached to every picture/video with the host
  set.png        the host seated in his talking set               -> host / split / pip shots (still mode) + 2nd reference
  talk_*.mp4     optional Flow clips of the host talking (muted)  -> host / split / pip shots (talking mode)
  host.json      name, look sentence, tagline
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOSTS = ROOT / "out" / "prepper_host" / "hosts"

DALE = {
    "name": "Dale",
    "tagline": "30 years on a working ranch",
    "look": ("Dale, a weathered American man in his late fifties, short grey hair, short salt-and-pepper beard, deep smile lines, "
             "kind pale-blue eyes, broad shoulders, wearing a dark olive-green canvas work jacket open over a red-and-black buffalo "
             "check flannel shirt, worn dark jeans, brown leather work boots, no hat"),
    "set": ("seated on a wooden stool in a cosy home workshop: weathered barn-wood wall behind him, wooden shelves of mason jars, "
            "canned food, stacked water jugs and a hanging oil lantern, warm tungsten light"),
}
# words that mean the host is in the picture
HOST_WORDS = ("{host}", "dale", " he ", " him ", " his ", "host", "man ")


SHIPPED = Path(__file__).resolve().parent / "hosts"   # the packs that ship with the app (Dale)


def names():
    found = set()
    for root in (HOSTS, SHIPPED):
        if root.is_dir():
            found |= {p.name for p in root.glob("*") if (p / "portrait.png").is_file()}
    return sorted(found)


def _seed(name):
    """A shipped pack is copied once into the writable host folder (talking clips and new pictures are added there)."""
    src, dst = SHIPPED / name, HOSTS / name
    if (dst / "portrait.png").is_file() or not (src / "portrait.png").is_file():
        return
    try:
        dst.mkdir(parents=True, exist_ok=True)
        for f in src.iterdir():
            if f.is_file() and not (dst / f.name).exists():
                (dst / f.name).write_bytes(f.read_bytes())
    except OSError:
        pass


def load(name="dale"):
    _seed(name)
    d = HOSTS / name if (HOSTS / name / "portrait.png").is_file() else SHIPPED / name
    meta = dict(DALE)
    jf = d / "host.json"
    if jf.is_file():
        meta.update(json.loads(jf.read_text(encoding="utf-8")))
    elif name == "dale":
        try:
            d.mkdir(parents=True, exist_ok=True)
            jf.write_text(json.dumps(DALE, indent=1), encoding="utf-8")
        except OSError:
            pass
    meta["dir"] = str(d)
    meta["portrait"] = str(d / "portrait.png") if (d / "portrait.png").is_file() else None
    meta["set_image"] = str(d / "set.png") if (d / "set.png").is_file() else None
    meta["talk_clips"] = [str(p) for p in sorted(d.glob("talk_*.mp4"))]
    return meta


def refs(meta):
    """Reference pictures for a picture/video that shows the host (unique file names: Flow's picker finds them by name)."""
    out = []
    for key, fname in (("portrait", "portrait.png"), ("set_image", "set.png")):
        if meta.get(key):
            src = Path(meta[key])
            home = HOSTS / meta["name"].lower()
            try:
                home.mkdir(parents=True, exist_ok=True)
            except OSError:
                import tempfile
                home = Path(tempfile.gettempdir())
            uniq = home / f"{meta['name'].lower()}_{fname}"
            if not uniq.is_file() or uniq.stat().st_mtime < src.stat().st_mtime:
                uniq.write_bytes(src.read_bytes())
            out.append(str(uniq))
    return out


def shows_host(prompt):
    p = f" {str(prompt).lower()} "
    return any(w in p for w in HOST_WORDS)


def expand(prompt, meta):
    """'{host} carries water' -> the fixed look sentence in place, so every picture describes him the same way."""
    p = str(prompt or "").strip()
    if "{host}" in p:
        return p.replace("{host}", meta["look"])
    if shows_host(p):
        return f"{meta['look']}. {p}"
    return p
