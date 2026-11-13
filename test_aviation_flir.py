"""Infrared look (aviation/flir.py): only for clips that are infrared footage by their own title."""

import subprocess

from aviation import bridge as BR
from aviation import flir as F


def test_is_flir_only_by_title():
    assert F.is_flir("A PLA J-11 seen through a FLIR targeting pod, 2023")
    assert F.is_flir("Infrared footage of a Su-35 intercept")
    assert not F.is_flir("Singapore Airlines A350 takeoff at Changi")


def test_graded_copy_is_grey_and_cached(tmp_path):
    src = tmp_path / "c.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=red:s=320x180:d=1", "-c:v", "libx264", "-pix_fmt",
                    "yuv420p", str(src)], check=True)
    out = F.graded(src)
    assert out.endswith(".flir.mp4")
    png = tmp_path / "f.png"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", out, "-frames:v", "1", str(png)], check=True)
    from PIL import Image
    r, g, b = Image.open(png).convert("RGB").getpixel((160, 90))
    assert abs(r - g) < 12 and abs(g - b) < 12                               # no colour left
    assert F.graded(src) == out                                              # made once


def test_hud_draws_and_is_registered():
    a, b = F.lay_hud(0.1, 4.0, {}), F.lay_hud(2.0, 4.0, {})
    assert a.size == (F.W, F.H) and a.tobytes() != b.tobytes()
    assert BR.card_table()["flir.lay_hud"] is F.lay_hud
