"""AI pictures that came back as two or three panels side by side (a hard straight seam from top to bottom): cut to their widest panel before the render.
Flow drew them for repeated plate requests ("variation 4"); the prompt no longer asks that, and this catches any that still come back. Never raises."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List


def panel_seams(path: "str | Path") -> List[int]:
    """x of each full-height straight vertical edge in a picture: an AI picture that came back as two or three panels side by side. [] for a normal picture (or one that cannot be read)."""
    try:
        import numpy as np
        from PIL import Image

        with Image.open(path) as im:                 # closed at once: Windows cannot overwrite or delete a file that is still open
            g = np.asarray(im.convert("L"), dtype=np.int16)
    except Exception:
        return []
    if g.ndim != 2 or g.shape[1] < 64:
        return []
    frac = (np.abs(np.diff(g, axis=1)) > 18).mean(axis=0)          # share of rows where the column changes sharply: about 1.0 on a panel border, under 0.5 on real edges
    margin = int(g.shape[1] * 0.04)
    frac[:margin] = 0
    frac[-margin:] = 0
    seams: List[int] = []
    for x in np.nonzero(frac > 0.9)[0]:
        if not seams or x - seams[-1] > 8:
            seams.append(int(x))
    return seams


def unpanel(path: "str | Path") -> bool:
    """A panelled picture is cut to its widest panel, cropped to the picture's own shape and saved over itself. -> True when it was changed."""
    seams = panel_seams(path)
    if not seams:
        return False
    from PIL import Image

    with Image.open(path) as im:
        img = im.convert("RGB")
    w, h = img.size
    edges = [0] + seams + [w]
    a, b = max(zip(edges, edges[1:]), key=lambda e: e[1] - e[0])
    a, b = a + 4, b - 4                             # the border line itself stays out
    ch = min(h, int((b - a) * h / w))
    top = (h - ch) // 2
    img.crop((a, top, b, top + ch)).resize((w, h), Image.LANCZOS).save(path)
    return True


IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp")


def unpanel_spec_pictures(spec: Dict[str, Any], log: Callable[[str], None] = lambda m: None) -> int:
    """Every full-screen picture of the render spec, cut to one panel when it came back panelled. -> how many were changed."""
    n = 0
    seen: set = set()
    for e in spec.get("events") or []:
        p = str(e.get("media") or "")
        if e.get("type") != "media_full" or not p.lower().endswith(IMAGE_EXT) or p in seen or not Path(p).is_file():
            continue
        seen.add(p)
        try:
            if unpanel(p):
                n += 1
                log(f"[Explainer] {Path(p).name} came back as side-by-side panels: cut to its widest panel")
        except Exception:
            continue
    return n
