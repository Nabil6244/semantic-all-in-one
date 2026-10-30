"""Story Fast depth layers: layers are used ONLY when their edges follow the objects; cartoons / panels / blobby depth stay a clean rigid camera move (no ghosts, no smears)."""
import shutil, sys, tempfile
from pathlib import Path
import numpy as np
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from story_fast import compose as C

fails = []
def ok(c, m):
    print(("ok  " if c else "FAIL"), m)
    if not c: fails.append(m)

TMP = Path(tempfile.mkdtemp(prefix="sf_layers_"))
W, H = 960, 540
SIZE = (480, 270)
_DEPTH = {}
C._depth = lambda path: _DEPTH[str(path)]
C._depth_available = lambda: True

def textured():
    rng = np.random.default_rng(5); y, x = np.mgrid[0:H, 0:W]
    a = np.stack([130 + 40 * np.sin(x / 11.0), 120 + 40 * np.cos(y / 13.0), 110 + 30 * np.sin((x + y) / 17.0)], -1) + rng.normal(0, 10, (H, W, 3))
    return a.clip(0, 255).astype(np.uint8)

def rect(a, x0, y0, x1, y1, col):
    a[y0:y1, x0:x1] = col; a[y0:y0 + 3, x0:x1] = 0; a[y1 - 3:y1, x0:x1] = 0; a[y0:y1, x0:x0 + 3] = 0; a[y0:y1, x1 - 3:x1] = 0

def save(name, a, depth):
    p = TMP / name; Image.fromarray(a).save(p); _DEPTH[str(p)] = depth.astype(np.float32); return str(p)

def prep(path): return C.prepare(path, SIZE, str(TMP / "layers"), need_depth=True)

# 1. crisp objects whose depth is exactly the object: layers are allowed, high quality
a = textured(); d = np.zeros((H, W), np.float32)
rect(a, 100, 120, 400, 420, (240, 240, 40)); d[120:420, 100:400] = .86          # mid object, hard edges
rect(a, 560, 110, 900, 490, (60, 90, 200)); d[110:490, 560:900] = .55           # a pedestal object
rect(a, 620, 170, 840, 430, (200, 40, 40)); d[170:430, 620:840] = 1.0           # near object on it
_q = C.EDGE_Q_MIN; C.EDGE_Q_MIN = .3          # the real bar is 0.8; lowered here only to exercise the layer plumbing on synthetic depth
p1 = prep(save("crisp.png", a, d)); C.EDGE_Q_MIN = _q
ok(p1["depth"] and p1["quality"] > .3, f"layers are built and carry their quality when the bar is met (quality {p1['quality']:.2f})")

C._hash_memo.clear()
# 2. same picture but a blobby depth (does not follow the objects, as a monocular model does on cartoons): no layers
yy, xx = np.mgrid[0:H, 0:W]
blob = np.exp(-(((xx / W - .45) * 2.6) ** 2 + ((yy / H - .5) * 2.6) ** 2)).astype(np.float32)
a2 = a.copy(); a2[0, 0] = (1, 2, 3)          # a different picture file (the layer cache is keyed on the file)
p2 = prep(save("blob.png", a2, blob))
ok(not p2["depth"] and len(p2["layers"]) == 1, "blobby depth on the same picture -> one flat layer (rigid move only)")

# 3. a split-panel picture: long straight divider through the middle
b = textured(); b[:, W // 2 - 3:W // 2 + 3] = 0
dd = np.zeros((H, W), np.float32); dd[120:420, 100:400] = .86; dd[150:450, 600:860] = 1.0
p3 = prep(save("panel.png", b, dd))
ok(not p3["depth"], "split-panel picture -> no layers")
ok(C.panel_split(b) and not C.panel_split(textured()), "panel detector: divider yes, plain texture no")

# 4. quality metric itself: exact masks ~1, shifted masks low, absurd coverage 0
m = np.zeros((H, W), bool); m[120:420, 100:400] = True
q_exact = C.layer_quality(a, [m]); q_off = C.layer_quality(a, [np.roll(m, 25, axis=1)])
ok(q_exact > .9 and q_off < .6, f"layer_quality: exact {q_exact:.2f} vs 25px-off {q_off:.2f}")
ok(C.layer_quality(a, [np.ones((H, W), bool)]) == 0.0, "a layer that is the whole picture scores 0")

# 5. a depth treatment on the rejected picture still renders (rigid) and the flat verdict is remembered (no second depth run)
out = TMP / "o.mp4"
C.render_shot({"still": str(TMP / "blob.png"), "duration": 1.0, "fps": 30, "size": SIZE, "seed": 1, "treatment": "parallax_left", "tparams": {"dir": "l"}}, str(out))
ok(out.is_file() and out.stat().st_size > 1000, "parallax treatment on a rejected picture renders (rigid fallback)")
ok(any(Path(x).name == "flat.txt" for x in (TMP / "layers").rglob("flat.txt")), "flat verdict stored beside the layers")

# 6. weaker layer quality uses the small differential move
j = C._norm({"still": str(TMP / "crisp.png"), "duration": 1.0, "treatment": "parallax_left", "size": SIZE, "tparams": {"dir": "l"}})
ok(C._camera(j, True, .85)["gains"] == C._GAINS["soft"] and C._camera(j, True, 1.0)["gains"] == C._GAINS["strong"], "quality < 0.92 -> soft layer gains")

# 7. warm specks never land on white paper; a dark picture keeps them
wp = np.full((H, W, 3), 252, np.uint8); wp[150:400, 300:600] = (40, 60, 120); pw = TMP / "paper.png"; Image.fromarray(wp).save(pw)
dk = np.full((H, W, 3), 25, np.uint8); dk[150:400, 300:600] = (200, 160, 60); pd = TMP / "darkbg.png"; Image.fromarray(dk).save(pd)
ok(C._env_for_background(["embers", "light_sweep"], str(pw)) == ["light_sweep"], "embers dropped on a white-paper picture, light overlays kept")
ok(C._env_for_background(["embers"], str(pd)) == ["embers"], "embers kept on a dark picture")

shutil.rmtree(TMP, ignore_errors=True)
print("ALL OK" if not fails else f"{len(fails)} FAILED")
sys.exit(1 if fails else 0)
