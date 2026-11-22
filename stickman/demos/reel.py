"""Looks reel: five 5-second clips, one per look, each in a different place with new poses and props.

python3 -m stickman.demos.reel out/stickman/phase3_looks_reel.mp4 [--preview]
"""
import subprocess
import sys
import tempfile
from pathlib import Path

from stickman import render

CLIPS = [
    ("ink_paper", "bedroom", "Ink *Paper*", [
        ("Tired *again*?", {"a": {"do": "yawn"}, "b": {"do": "wave"}}, []),
        ("Check your *phone*", {"a": {"do": "phone"}, "b": {"do": "arms_crossed"}}, []),
        ("Then *sleep*.", {"a": {"do": "sleep"}, "b": {"do": "present"}}, [])]),
    ("chalk_dark", "classroom", "Chalk *Dark*", [
        ("Here's the *idea*", {"a": {"do": "idea"}, "b": {"do": "look"}}, []),
        ("It takes *time*", {"a": {"do": "present"}, "b": {"do": "think"}}, [{"name": "hourglass", "fig": "a", "at": "side"}]),
        ("Write it *down*", {"a": {"do": "type"}, "b": {"do": "clap"}}, [])]),
    ("colour_pop", "park", "Colour *Pop*", [
        ("Get *outside*", {"a": {"do": "dance"}, "b": {"do": "laugh"}}, []),
        ("Lift *something*", {"a": {"do": "lift"}, "b": {"do": "hands_hips"}}, []),
        ("You *win*!", {"a": {"do": "fist_up"}, "b": {"do": "clap"}}, [{"name": "trophy", "fig": "a", "at": "side"}])]),
    ("retro_tv", "street", "Retro *TV*", [
        ("Channel *three*", {"a": {"do": "sneak", "to": 0.46}, "b": {"do": "stop"}}, []),
        ("Too *heavy*", {"a": {"do": "carry"}, "b": {"do": "push"}}, []),
        ("Down he *goes*", {"a": {"do": "fall"}, "b": {"do": "laugh"}}, [])]),
    ("night_thriller", "city_night", "Night *Thriller*", [
        ("Something is *out there*", {"a": {"do": "crouch"}, "b": {"do": "shiver"}}, []),
        ("Don't *move*", {"a": {"do": "scared"}, "b": {"do": "angry"}}, [{"name": "exclaim", "fig": "b", "at": "above", "size": 0.3}]),
        ("*Run*.", {"a": {"do": "run", "to": 1.3}, "b": {"do": "run", "to": 1.3}}, [])]),
]


def clip_spec(look, place, title, beats, size):
    out = {"look": look, "fps": 30, "size": size, "duration": 5.0, "place": place,
           "title": {"text": title, "t1": 1.6},
           "figures": {"a": {"x": 0.36, "facing": 1, "height": 0.4}, "b": {"x": 0.66, "facing": -1, "height": 0.4}},
           "beats": []}
    t = 0.0
    durs = (1.7, 1.6, 1.7)
    cams = ({"zoom": 1.0, "x": 0.5}, {"zoom": 1.14, "x": 0.42}, {"zoom": 1.06, "x": 0.55})
    for (cap, acts, props), d, cam in zip(beats, durs, cams):
        words = [{"w": w, "t": round(t + 0.1 + 0.22 * k, 3)} for k, w in enumerate(cap.split())]
        out["beats"].append({"t": round(t, 3), "dur": d, "caption": cap, "words": words,
                             "acts": acts, "props": props, "camera": cam})
        t += d
    return out


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    dest = Path(argv[0] if argv else "out/stickman/phase3_looks_reel.mp4")
    size = [1280, 720] if "--preview" in argv else [1920, 1080]
    with tempfile.TemporaryDirectory() as wd:
        parts = []
        for k, (look, place, title, beats) in enumerate(CLIPS):
            p = Path(wd) / f"clip{k}.mp4"
            render.render(clip_spec(look, place, title, beats, size), p, log=None)
            parts.append(p)
        lst = Path(wd) / "list.txt"
        lst.write_text("".join(f"file '{p}'\n" for p in parts))
        dest.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                        "-c", "copy", "-movflags", "+faststart", str(dest)], check=True)
    print(f"reel -> {dest}")


if __name__ == "__main__":
    main()
