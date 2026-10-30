"""Checks for the puppet scene clips (run from the repo root):
    python3 -m health_cinema.puppet.linkcheck floors [assets_dir]      print the floor table (scene -> floor_conf, floor_ok, walk_y, horizon) and write a contact sheet
    python3 -m health_cinema.puppet.linkcheck link  A.png B.png [out_dir]   render two linked 6 s clips, concatenate (hard cut), save frames around the cut
"""
from __future__ import annotations
import glob, os, subprocess, sys, time
from pathlib import Path
from PIL import Image, ImageDraw

from . import render, scene

ASSETS = "/Users/muhammadnabil/Downloads/VideoGenerator/Video_2026-10-28_041_hrt/assets"

def floor_table(assets=ASSETS, sheet=None):
    rows = []; W, H = 320, 180; fs = sorted(glob.glob(os.path.join(assets, "0*.png"))); sh = Image.new("RGB", (W * 4, H * ((len(fs) + 3) // 4)))
    for i, f in enumerate(fs):
        s = scene.analyse(f); rows.append((Path(f).stem, s.floor_conf, s.floor_ok, s.walk_y, s.horizon))
        im = Image.open(f).convert("RGB").resize((W, H)); d = ImageDraw.Draw(im)
        d.line([0, s.horizon * H, W, s.horizon * H], fill=(0, 200, 255)); d.line([0, s.walk_y * H, W, s.walk_y * H], fill=(255, 0, 0))
        d.rectangle([0, 0, 150, 12], fill=(0, 0, 0)); d.text((3, 1), f"{Path(f).stem} c{s.floor_conf:.2f} {'OK' if s.floor_ok else '--'}", fill=(0, 255, 0) if s.floor_ok else (255, 120, 120))
        sh.paste(im, ((i % 4) * W, (i // 4) * H))
    print("scene  floor_conf  floor_ok  walk_y  horizon")
    for r in rows: print(f"{r[0]}    {r[1]:.2f}      {'yes' if r[2] else 'no ':3}      {r[3]:.2f}    {r[4]:.2f}")
    if sheet: sh.save(sheet)
    return rows

def _ff(): return render._ffmpeg()

def link_demo(a, b, out_dir, character="suit_man", dur=6.0, fps=30, size=(1920, 1080)):
    out_dir = Path(out_dir).resolve(); out_dir.mkdir(parents=True, exist_ok=True)
    pa, pb = render.link_params(a, b, "right", character=character, size=size, phase=.3)
    pa = dict(pa, beats=[{"t0": 2.0, "t1": 3.6, "action": "point", "x0": .55, "params": {"facing": "right"}}], x_in=.3)
    pb = dict(pb, beats=[{"t0": 2.4, "t1": 4.2, "action": "look_around", "x0": .6}], x_in=.35)
    t = time.time(); c1 = render.render_shot(a, character, None, out_dir / "clip1.mp4", duration=dur, fps=fps, size=size, params=pa); t1 = time.time() - t
    t = time.time(); c2 = render.render_shot(b, character, None, out_dir / "clip2.mp4", duration=dur, fps=fps, size=size, params=pb); t2 = time.time() - t
    lst = out_dir / "list.txt"; lst.write_text(f"file '{c1}'\nfile '{c2}'\n")
    subprocess.run([_ff(), "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(out_dir / "link_demo.mp4")], check=True, timeout=900)
    n = int(dur * fps)
    # frames: last frame of clip 1 (exit finishes 0.6 s before), 1st of clip 2, and a strip around the cut
    def grab(src, t, dst): subprocess.run([_ff(), "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", str(src), "-frames:v", "1", str(dst)], check=True, timeout=900)
    subprocess.run([_ff(), "-v", "error", "-y", "-sseof", "-0.05", "-i", str(c1), "-update", "1", "-frames:v", "1", str(out_dir / "a_last.png")], check=True, timeout=900); grab(c2, 0, out_dir / "b_first.png")
    for k, tt in enumerate((dur - 1.6, dur - 1.2, dur - .8)): grab(c1, tt, out_dir / f"a_{k}.png")
    for k, tt in enumerate((.2, .4, .8)): grab(c2, tt, out_dir / f"b_{k}.png")
    print(f"render times: clip1 {t1:.1f}s clip2 {t2:.1f}s ({dur * fps} frames each: {t1 / (dur * fps):.3f} / {t2 / (dur * fps):.3f} s/frame); params:", pa["link_out"], pb["link_in"])
    return out_dir / "link_demo.mp4"

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "floors"
    if cmd == "floors": floor_table(*(sys.argv[2:3] or [ASSETS]), sheet="out/motion_sample/floor_sheet.png")
    elif cmd == "link": link_demo(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else "out/motion_sample")
