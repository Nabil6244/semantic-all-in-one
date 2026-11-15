"""Step 2 test shot: Walt points at a gold vein in the mine and talks, Pip reacts; push-in. Voice + Blender + mux.

Run: python3 toontales/shots/test_shot.py [--frames 0,40,80]   (frames = quick still check only)
Out: out/toontales_step2_shot.mp4
"""
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TT = HERE.parent
ROOT = TT.parent
sys.path.insert(0, str(TT / "audio"))
import voice  # noqa: E402

BUILD = TT / "build" / "shot01"
LEAD = 0.2


def plan():
    ln = voice.speak("walt", "Pip, look at this wall. It's full of gold!", BUILD / "audio")
    end = LEAD + ln["dur"]
    return ln, {
        "set": "mine", "fps": 30, "size": [1080, 1920], "dur": round(end + 0.45, 2),
        "cast": [{"id": "walt", "mark": "A"}, {"id": "pip", "mark": "B"}],
        "lines": [{"who": "walt", "start": LEAD, "dur": ln["dur"], "cues": ln["cues"]}],
        "actions": [
            {"who": "walt", "pose": "point", "t0": LEAD + 0.45, "t1": LEAD + 0.8},
            {"who": "pip", "pose": "shock", "t0": end - 0.55, "t1": end - 0.3, "eyes": "shock", "mouth": "o_shock"},
        ],
        "faces": [{"who": "walt", "eyes": "wide", "t0": end - 0.75, "t1": 99},
                  {"who": "pip", "eyes": "open", "mouth": "X", "t0": 0, "t1": end - 0.55}],
        "camera": {"from": {"target": [0.55, 0.0, 1.15], "dist": 4.6, "yaw": -12, "pitch": 3, "lens": 22},
                   "to": {"target": [0.78, 0.1, 1.3], "dist": 3.3, "yaw": -19, "pitch": 2, "lens": 22},
                   "drift": 0.012},
    }


def main():
    ln, shot = plan()
    frames = None
    if "--frames" in sys.argv:
        frames = [int(x) for x in sys.argv[sys.argv.index("--frames") + 1].split(",")]
        shot["frames"] = frames
    sj = BUILD / "shot.json"
    sj.write_text(json.dumps(shot, indent=1))
    fd = BUILD / ("check" if frames else "frames")
    subprocess.run(["blender", "-b", "--factory-startup", "--python", str(HERE / "shot.py"), "--", str(sj), str(fd)],
                   check=True)
    if frames:
        print("check frames ->", fd)
        return
    out = ROOT / "out" / "toontales_step2_shot.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", str(shot["fps"]), "-i", str(fd / "f%04d.png"),
                    "-i", ln["wav"], "-filter_complex",
                    f"[1]adelay={int(LEAD * 1000)}:all=1,apad[a]", "-map", "0:v", "-map", "[a]", "-shortest",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "17", "-preset", "medium",
                    "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
                    "-c:a", "aac", "-b:a", "192k", str(out)], check=True)
    print("SHOT ->", out)


if __name__ == "__main__":
    main()
