"""Machine paths for Toy Vehicles, so the same code runs on the Mac and on a Windows PC (RTX render box).

TOY_BLENDER overrides the Blender executable; TOY_FONT overrides the rounded title font.
"""
import glob
import os
import shutil
import sys


def blender():
    if os.environ.get("TOY_BLENDER"):
        return os.environ["TOY_BLENDER"]
    if sys.platform == "darwin":
        return "/Applications/Blender.app/Contents/MacOS/Blender"
    if sys.platform.startswith("win"):
        found = sorted(glob.glob(r"C:\Program Files\Blender Foundation\Blender*\blender.exe"))
        if found:
            return found[-1]                       # the newest installed version
    return shutil.which("blender") or "blender"


_FONTS = ["/System/Library/Fonts/Supplemental/Arial Rounded Bold.ttf",      # Mac
          r"C:\Windows\Fonts\ARLRDBD.TTF",                                    # Windows (Arial Rounded MT Bold)
          r"C:\Windows\Fonts\seguibl.ttf",                                    # Windows fallback (Segoe UI Black)
          r"C:\Windows\Fonts\arialbd.ttf",
          "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]


def font():
    if os.environ.get("TOY_FONT"):
        return os.environ["TOY_FONT"]
    for f in _FONTS:
        if os.path.exists(f):
            return f
    return _FONTS[0]
