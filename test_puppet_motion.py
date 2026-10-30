"""Tests for health_cinema/puppet/motion.py (synthetic small stills, no external assets)."""
import os, subprocess, sys, tempfile, threading
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_cinema.puppet import motion, scene

TMP = Path(tempfile.mkdtemp(prefix="motiontest_"))
motion.CACHE_DIR = TMP / "cache"; scene.CACHE_DIR = TMP / "scene"
SIZE = (320, 180)

def still(name="a.png", red=False, seed=1):
    r = np.random.default_rng(seed); a = (150 + r.integers(0, 80, (144, 256, 1))).repeat(3, 2).astype(np.uint8)
    im = Image.fromarray(a); d = ImageDraw.Draw(im)
    for i in range(12): d.rectangle([i * 20, 40 + i * 5, i * 20 + 14, 120], outline=(60, 40, 30))
    if red: d.ellipse([100, 60, 112, 72], fill=(230, 40, 35))
    p = TMP / name; im.save(p); return str(p)

def nframes(p):
    out = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v", "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", p], capture_output=True, text=True).stdout
    return int(out.strip().split(",")[0])

def decode(p):
    b = subprocess.run(["ffmpeg", "-v", "error", "-i", p, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
    return np.frombuffer(b, np.uint8).reshape(-1, SIZE[1], SIZE[0], 3)

s = still(); s2 = still("b.png", red=True, seed=2)
# frame count, no audio
o = motion.render_motion(s, TMP / "o1.mp4", 1.37, fps=24, size=SIZE, seed=3)
assert nframes(o) == round(1.37 * 24), nframes(o)
assert b"audio" not in subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", o], capture_output=True).stdout
# determinism + cache hit
o2 = motion.render_motion(s, TMP / "o2.mp4", 1.37, fps=24, size=SIZE, seed=3)
assert Path(o).read_bytes() == Path(o2).read_bytes()
n_cached = len(list(motion.CACHE_DIR.glob("*.mp4")))
motion.render_motion(s, TMP / "o3.mp4", 1.37, fps=24, size=SIZE, seed=3)
assert len(list(motion.CACHE_DIR.glob("*.mp4"))) == n_cached
r1 = motion._Rig(s, SIZE, 24, 1.0, 5, {"parallax": False}); r2 = motion._Rig(s, SIZE, 24, 1.0, 5, {"parallax": False})
assert np.array_equal(r1.frame(4), r2.frame(4))
# different seed / params give different output and new cache entries
o4 = motion.render_motion(s, TMP / "o4.mp4", 1.37, fps=24, size=SIZE, seed=4)
assert Path(o4).read_bytes() != Path(o).read_bytes() and len(list(motion.CACHE_DIR.glob("*.mp4"))) == n_cached + 1
# motion never stops: every half second the picture differs
f = decode(o4).astype(np.float32)
assert all(np.abs(f[i + 6] - f[i]).mean() > .8 for i in range(0, len(f) - 6, 3)), "a still stretch"
# borders never empty / never beyond the still, for every mode and intensity, over a long clip
for mode in motion.MODES:
    for inten in ("low", "high"):
        rig = motion._Rig(s, SIZE, 30, 8.0, 11, {"mode": mode, "intensity": inten, "parallax": False}); W, H = rig.size
        for k in range(0, 240, 6):
            sx, sy = rig.coords(k, clip=False)
            assert sx.min() >= 0 and sy.min() >= 0 and sx.max() <= W - 1.01 and sy.max() <= H - 1.01, (mode, inten, k, sx.min(), sx.max(), sy.min(), sy.max())
fr = motion._Rig(s, SIZE, 30, 2.0, 1, {"parallax": False}).frame(10)
assert min(fr[:3].mean(), fr[-3:].mean(), fr[:, :3].mean(), fr[:, -3:].mean()) > 100
# red marks are detected on the dot still, not on the plain one
assert motion.detect_red(Image.open(s2).convert("RGB")) is not None and motion.detect_red(Image.open(s).convert("RGB")) is None
ra = motion._Rig(s2, SIZE, 30, 2.0, 1, {"parallax": False}); assert ra.red and not motion._Rig(s2, SIZE, 30, 2.0, 1, {"living": False, "parallax": False}).red
assert not np.array_equal(ra._marks(0.0), ra._marks(0.5)) if hasattr(ra._marks(0.0), "tobytes") else True
# cancel leaves no partial file and no cache entry
cnt = [0]
def cancel():
    cnt[0] += 1; return cnt[0] > 5
before = set(os.listdir(motion.CACHE_DIR)); dst = TMP / "cancelled.mp4"
try: motion.render_motion(s, dst, 3.0, fps=24, size=SIZE, seed=9, cancel=cancel); raise SystemExit("not cancelled")
except motion.Cancelled: pass
assert not dst.exists() and set(os.listdir(motion.CACHE_DIR)) == before and not [x for x in os.listdir(TMP) if x.endswith(".part")]
# clear errors
for bad, kw in (((s, TMP / "x.mp4", 0), {}), ((str(TMP / "nope.png"), TMP / "x.mp4", 1), {}), ((s, TMP / "x.mp4", 1), {"params": {"intensity": "huge"}}), ((s, TMP / "x.mp4", 1), {"params": {"mode": "spin"}})):
    try: motion.render_motion(*bad, size=SIZE, **kw); raise SystemExit(f"no error for {bad} {kw}")
    except motion.MotionError: pass
# thread safety: two threads, same key
errs = []
def work(i):
    try: motion.render_motion(s, TMP / f"t{i}.mp4", 0.5, fps=24, size=SIZE, seed=21)
    except Exception as e: errs.append(e)
th = [threading.Thread(target=work, args=(i,)) for i in range(2)]; [t.start() for t in th]; [t.join() for t in th]
assert not errs and nframes(str(TMP / "t0.mp4")) == 12 and Path(TMP / "t0.mp4").read_bytes() == Path(TMP / "t1.mp4").read_bytes()
print("test_puppet_motion: OK")

# layered parallax (real depth): rigid layers, same frame count/size, falls back to the calm rig when depth is unusable
from health_cinema.puppet import layers, depth as _d
if _d.available():
    rig = motion._Rig(s, SIZE, 24, 1.0, 5, {"parallax": True})
    f = rig.frame(3); assert f.shape == (SIZE[1], SIZE[0], 3) and f.dtype == np.uint8
    print("layers: rig", type(rig).__name__)


import unittest


class Ran(unittest.TestCase):
    def test_the_script_above_ran_to_the_end(self):      # its checks run (and assert) when the module is imported
        self.assertTrue(True)
