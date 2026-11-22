"""Host Explainer: your own picture as a presenter in the corner, talking while the stickmen act.

Uses the puppet folders made for Kids Learn (cartoon3d-engine/assets/puppets/<name>/spec.json + cutout.png):
the head is cut along spec["head"]["cut"] and turns a little about its pivot; the mouth opens with every spoken
word (word times from the voice), the eyes blink. Plain PIL, made once per worker at the output size.

16:9: waist-up, bottom-right on the frame edge; the stage slides left (spec["host_shift"]).
9:16: smaller, bottom-left under the stage, fading out at its waist, clear of the Shorts buttons on the right.
"""
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
PUPPETS = ROOT / "cartoon3d-engine" / "assets" / "puppets"
LEVELS = 4                   # mouth shapes besides closed
_CACHE = {}

# where the host sits and what the rest of the frame does to make room
LAYOUT_16x9 = {"height": 0.50, "x": 0.995, "bottom": 1.0, "anchor": "right", "fade": 0.0,
               "host_shift": 0.10, "caption_x": 0.42, "caption_w": 0.74}
LAYOUT_9x16 = {"height": 0.17, "x": 0.03, "bottom": 0.895, "anchor": "left", "fade": 0.16,
               "host_shift": 0.0, "caption_x": 0.62, "caption_w": 0.64}


def hosts():
    """{folder name: shown name} for every puppet folder with a spec."""
    out = {}
    for sp in sorted(PUPPETS.glob("*/spec.json")):
        try:
            out[sp.parent.name] = json.loads(sp.read_text()).get("name") or sp.parent.name
        except Exception:  # noqa: BLE001
            continue
    return out


def layout(shorts):
    return dict(LAYOUT_9x16 if shorts else LAYOUT_16x9)


def setup(spec, name, words=None):
    """Turn the host on in a plan. words: the voice's word times [{start, end}] (better mouth timing than beat words)."""
    if name not in hosts():
        raise ValueError(f"no host picture '{name}' (have: {', '.join(hosts()) or 'none'})")
    lay = layout(spec.get("shorts"))
    spec["host"] = {"name": name, "layout": lay}
    spec["host_shift"] = lay["host_shift"]
    spec["layout"] = dict(spec.get("layout") or {}, caption_x=lay["caption_x"], caption_w=lay["caption_w"])
    if words:
        spec["speech"] = [[round(w["start"], 3), round(max(w["end"], w["start"] + 0.08), 3), _syll(w.get("word", ""))]
                          for w in words]
    return spec


def _syll(word):
    w = "".join(c for c in word.lower() if c.isalpha())
    n, prev = 0, False
    for c in w:
        v = c in "aeiouy"
        n += v and not prev
        prev = v
    if w.endswith("e") and n > 1:
        n -= 1
    return max(1, n)


def _speech(spec):
    if spec.get("speech"):
        return spec["speech"]
    out, flat = [], [w for b in spec["beats"] for w in b.get("words") or []]
    for k, w in enumerate(flat):
        nxt = flat[k + 1]["t"] if k + 1 < len(flat) else w["t"] + 0.4
        out.append([w["t"], w["t"] + min(0.5, max(0.1, nxt - w["t"] - 0.03)), _syll(w["w"])])
    return out


def mouth_open(speech, t):
    """0..1: how open the mouth is at t (one open-close per syllable while a word is said)."""
    lo, hi = 0, len(speech)
    while lo < hi:                               # last word starting at or before t
        mid = (lo + hi) // 2
        if speech[mid][0] <= t:
            lo = mid + 1
        else:
            hi = mid
    k = lo - 1
    if k < 0:
        return 0.0
    s, e, n = speech[k]
    if t > e:
        return 0.0
    u = (t - s) / max(0.05, e - s)
    return abs(math.sin(math.pi * n * u)) ** 0.8


def _in_word(speech, t):
    return any(s <= t <= e for s, e, _ in speech if s <= t + 0.01 and e >= t - 0.01)


def talking(speech, t, win=0.6):
    """0..1 smoothed: is the host in the middle of speaking (drives the head moves)."""
    hit = 0.0
    for s, e, _ in speech:
        if s > t + win:
            break
        if e >= t - win:
            hit = max(hit, 1 - max(0.0, max(s - t, t - e)) / win)
    return hit


# ------------------------------------------------------------------ building the pictures (once per worker)
def _sample(src, pts):
    a = np.asarray(src.convert("RGB"), np.float32)
    c = np.mean([a[int(y), int(x)] for x, y in pts], axis=0)
    return tuple(int(v) for v in c)


def _cut_mask(size, cut, below):
    """Mask of the part above (head) or below (body) the cut line."""
    W, H = size
    pts = [(x, y) for x, y in cut]
    poly = [(0, 0), (W, 0)] + [(W, pts[-1][1])] + pts[::-1] + [(0, pts[0][1])] if not below else \
        [(0, H), (W, H), (W, pts[-1][1])] + pts[::-1] + [(0, pts[0][1])]
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).polygon(poly, fill=255)
    return m


def _mouth(head, sp, o, col):
    """Draw an open mouth (o 0..1) over the picture's mouth, at the picture's own size."""
    d = ImageDraw.Draw(head)
    plate = Image.new("L", head.size, 0)
    ImageDraw.Draw(plate).polygon([tuple(p) for p in sp["mouth"]["mask"]], fill=255)
    plate = plate.filter(ImageFilter.GaussianBlur(3))
    head.paste(Image.new("RGBA", head.size, (*col["skin"], 255)), (0, 0), plate)
    cx, cy = sp["mouth"]["center"]
    hw = sp["mouth"]["halfWidth"] * (0.78 + 0.12 * o)
    depth = 14 + 56 * o
    top, bot = [], []
    for i in range(25):
        u = i / 24
        x = cx - hw + 2 * hw * u
        top.append((x, cy + 5 * math.sin(math.pi * u)))
        bot.append((x, cy + 5 * math.sin(math.pi * u) + depth * math.sin(math.pi * u) ** 0.75))
    shape = top + bot[::-1]
    d.polygon(shape, fill=(*col["inside"], 255))
    if o > 0.3:                                   # top teeth
        th = min(16.0, depth * 0.28)
        teeth = top + [(x, y + th * math.sin(math.pi * i / 24) ** 0.4) for i, (x, y) in enumerate(top)][::-1]
        d.polygon(teeth, fill=(*col["teeth"], 255))
    d.line(shape + [shape[0]], fill=(*col["line"], 255), width=7, joint="curve")


def _blink(head, sp, col):
    d = ImageDraw.Draw(head)
    for eye in sp["eyes"]:
        m = Image.new("L", head.size, 0)
        ImageDraw.Draw(m).polygon([tuple(p) for p in eye["contour"]], fill=255)
        m = m.filter(ImageFilter.GaussianBlur(2)).point(lambda v: min(255, v * 2))
        head.paste(Image.new("RGBA", head.size, (*col["lid"], 255)), (0, 0), m)
        (x0, y0), (x1, y1) = eye["corners"]
        pts = [(x0 + (x1 - x0) * u, y0 + (y1 - y0) * u + 16 * math.sin(math.pi * u)) for u in [i / 12 for i in range(13)]]
        d.line(pts, fill=(*col["lash"], 255), width=10, joint="curve")


def _build(name, H, lay):
    folder = PUPPETS / name
    sp = json.loads((folder / "spec.json").read_text())
    src = Image.open(folder / sp.get("image", "cutout.png")).convert("RGBA")
    col = {"skin": _sample(src, sp["samples"]["lid"][:2]), "lid": _sample(src, sp["samples"]["lid"][:2]),
           "inside": _sample(src, sp["samples"]["inside"]), "teeth": _sample(src, sp["samples"]["teeth"]),
           "line": _sample(src, sp["samples"]["line"]), "lash": _sample(src, sp["samples"]["lash"])}
    cut = sp["head"]["cut"]
    head_m = _cut_mask(src.size, cut, below=False)
    # the body keeps a stub of neck/hair just above the cut, so nothing opens up when the head turns
    stub = _cut_mask(src.size, [(x, y - 34) for x, y in cut], below=True)
    body = src.copy()
    body.putalpha(Image.fromarray(np.minimum(np.asarray(src.getchannel("A")), np.asarray(stub))))
    head0 = src.copy()
    head0.putalpha(Image.fromarray(np.minimum(np.asarray(src.getchannel("A")), np.asarray(head_m))))

    scale = lay["height"] * H / src.height
    size = (max(1, int(src.width * scale)), max(1, int(src.height * scale)))

    def small(im):
        return im.resize(size, Image.LANCZOS)

    heads = {}
    for blink in (False, True):
        for lv in range(LEVELS + 1):
            h = head0.copy()
            if lv:
                _mouth(h, sp, lv / LEVELS, col)
            if blink:
                _blink(h, sp, col)
            heads[(lv, blink)] = small(h)
    body = small(body)
    if lay["fade"] > 0:                            # Shorts: the waist fades out instead of ending on a hard line
        a = np.asarray(body.getchannel("A"), np.float32)
        rows = np.linspace(0, 1, a.shape[0], dtype=np.float32)
        a *= np.clip((1 - rows) / lay["fade"], 0, 1)[:, None]
        body.putalpha(Image.fromarray(a.astype(np.uint8)))
    shadow = Image.new("RGBA", (size[0] + 40, size[1] + 40), (0, 0, 0, 0))
    sil = Image.alpha_composite(body, heads[(0, False)]).getchannel("A").point(lambda v: int(v * 0.42))
    shadow.paste(Image.new("RGBA", size, (0, 0, 0, 255)), (20, 20), sil)
    shadow = shadow.filter(ImageFilter.GaussianBlur(max(2, H * 0.008)))
    pivot = (sp["head"]["pivot"][0] * scale, sp["head"]["pivot"][1] * scale)
    return {"body": body, "heads": heads, "shadow": shadow, "pivot": pivot, "size": size}


def _get(spec):
    W, H = spec["size"]
    h = spec["host"]
    key = (h["name"], W, H, json.dumps(h["layout"], sort_keys=True))
    if key not in _CACHE:
        _CACHE[key] = _build(h["name"], H, h["layout"])
    sk = ("speech", h["name"], spec["duration"], len(spec["beats"]))
    if sk not in _CACHE:
        _CACHE[sk] = _speech(spec)
    return _CACHE[key], _CACHE[sk]


def paste(out, fr, spec):
    """Draw the host into the frame (an RGBA PIL image)."""
    W, H = out.size
    pp, speech = _get(spec)
    lay = spec["host"]["layout"]
    t = fr["t"]
    o = mouth_open(speech, t)
    lv = min(LEVELS, int(round(o * LEVELS)))
    if lv == 0 and _in_word(speech, t):           # inside a word: a drawn closed mouth, not the picture's wide smile
        lv = 1
    blink = ((t + 0.7) % 3.7) < 0.13
    tk = talking(speech, t)
    # head: a slow sway, livelier while talking, and a small nod with the words
    ang = 1.1 * math.sin(t * 2 * math.pi / 5.3) + tk * 1.6 * math.sin(t * 2 * math.pi * 0.85 + 0.6)
    dy = -tk * 2.5 * abs(math.sin(t * 2 * math.pi * 1.3)) * pp["size"][1] / 760
    breath = 1.2 * math.sin(t * 2 * math.pi / 3.9) * pp["size"][1] / 760
    w, h = pp["size"]
    x0 = int(lay["x"] * W - w) if lay["anchor"] == "right" else int(lay["x"] * W)
    y0 = int(lay["bottom"] * H - h + breath)
    out.alpha_composite(pp["shadow"], (x0 - 20 + int(H * 0.006), y0 - 20 + int(H * 0.006)))
    out.alpha_composite(pp["body"], (x0, y0))
    head = pp["heads"][(lv, blink)].rotate(ang, resample=Image.BICUBIC, center=pp["pivot"], translate=(0, dy))
    out.alpha_composite(head, (x0, y0))
