"""Writes gta6_endings_scenes.csv per the user's Visual Assembly Guide: every beat's footage is that beat's own Clip 1 and
Clip 2 (the YouTube links in the guide), alternating sentence by sentence and moving forward through each clip.

The cards from build_endings_csv (prompts, results, quotes, chapters) stay; every plain footage shot is replaced by the beat's
clips. Vertical uploads sit centred over a blurred copy (gta6_src_*), the clip with only a black screen (A1dy357XeUI) is skipped,
and the 12-hour walkthrough (jPxtUQEj8L0) was not downloaded, so those beats use their other clip."""
import re
from pathlib import Path

import build_endings_csv as E
from build_map_csv import build, write

ROOT = Path(__file__).resolve().parent
SRC = {  # guide link id -> (file in footage/trailer, first useful second, last usable second)
    "r7EfeLD-Xq0": ("gta6_src_r7ef.mp4", 0.5, 55.0), "8-DRGbQ1IXc": ("gta6_end_chase.mp4", 40.0, 205.0),
    "Xq0hKr8gPA0": ("gta6_src_xq0h.mp4", 9.0, 50.0), "TtFrLZsxOOA": ("gta6_src_ttfr.mp4", 28.0, 89.0),
    "BWq8b7nriyE": ("gta6_src_bwq8.mp4", 3.0, 34.0), "yS7BO8yO-bo": ("gta6_src_ys7b.mp4", 20.0, 78.0),
    "NuuGDSumo8Y": ("gta6_end_drive_keys.mp4", 5.0, 160.0), "K-uFahxraLM": ("gta6_end_drive_city.mp4", 5.0, 175.0),
    "o46Cdr9Vnq0": ("gta6_src_o46c.mp4", 5.0, 270.0), "bSZ-L-N-W2U": ("gta6_src_bsz.mp4", 1.0, 52.0),
    "bYmqFCMNflw": ("gta6_src_bymq.mp4", 2.0, 175.0), "zKgWV5JoeW4": ("gta6_end_first_person.mp4", 5.0, 145.0),
    "vCywV51m1Lc": ("gta6_end_green_car.mp4", 5.0, 125.0), "PmTd6p2tKiA": ("gta6_src_pmtd.mp4", 10.0, 48.0),
}
# (start phrase of the beat in the guide, Clip 1, Clip 2, where in each clip the beat starts)
BEATS = [
    (r"Quick spoiler warning", "r7EfeLD-Xq0", "8-DRGbQ1IXc", 0.5, 40.0),
    (r"Picture this", "Xq0hKr8gPA0", None, 9.0, 0),
    (r"Seems like a simple choice", "TtFrLZsxOOA", None, 28.0, 0),
    (r"And there is one four-word line", "BWq8b7nriyE", "yS7BO8yO-bo", 3.0, 28.0),
    (r"Before we compare all three endings", "NuuGDSumo8Y", None, 5.0, 0),
    (r"You gear up with body armor", "8-DRGbQ1IXc", None, 60.0, 0),
    (r"Then the nightmare twist hits", "K-uFahxraLM", "Xq0hKr8gPA0", 5.0, 9.0),
    (r"Remember, nothing else", "Xq0hKr8gPA0", None, 18.0, 0),
    (r"Let's start with what happens", "r7EfeLD-Xq0", None, 29.0, 0),
    (r"They smash straight through", "8-DRGbQ1IXc", "Xq0hKr8gPA0", 160.0, 12.0),
    (r"Okay, so you reload", "r7EfeLD-Xq0", "Xq0hKr8gPA0", 38.0, 20.0),
    (r"If Jason opens with the words", "TtFrLZsxOOA", "o46Cdr9Vnq0", 61.0, 5.0),
    (r"Jason steps out with one hand", "8-DRGbQ1IXc", None, 120.0, 0),
    (r"In the third confirmed ending", "TtFrLZsxOOA", "r7EfeLD-Xq0", 30.0, 47.0),
    (r"This time, both Jason and Lucia", "Xq0hKr8gPA0", "o46Cdr9Vnq0", 26.0, 60.0),
    (r"Now watch what happens during the", "TtFrLZsxOOA", "bSZ-L-N-W2U", 51.0, 1.0),
    (r"Jason walks into the visiting room", "TtFrLZsxOOA", "bYmqFCMNflw", 55.0, 2.0),
    (r"Right now, lists all over TikTok", "bYmqFCMNflw", "vCywV51m1Lc", 30.0, 5.0),
    (r"Guides that checked complete", "NuuGDSumo8Y", "bYmqFCMNflw", 60.0, 60.0),
    (r"Now whatever ending you get", "BWq8b7nriyE", None, 3.0, 0),
    (r"Right after that, the secret Gold", "zKgWV5JoeW4", "vCywV51m1Lc", 5.0, 40.0),
    (r"So if you are about to", "yS7BO8yO-bo", "PmTd6p2tKiA", 20.0, 10.0),
    (r"Play through once", "K-uFahxraLM", "zKgWV5JoeW4", 80.0, 60.0),
]
STEP = 4.5          # seconds the place in a clip moves on each time it is used


def per_beat(lines):
    beat, pos, turn = -1, {}, 0
    for sent, shots in lines:
        for k, (pat, *_r) in enumerate(BEATS):
            if re.search(pat, sent):
                beat, turn = k, 0
                _p, c1, c2, a1, a2 = BEATS[k]
                pos = {c1: a1, **({c2: a2} if c2 else {})}
        if beat < 0:
            continue
        clips = [c for c in BEATS[beat][1:3] if c]
        for s in shots:
            if s.get("shot") in ("game", "title", "chapter") or (s.get("shot") == "hud" and s.get("game_clip")):
                cid = clips[turn % len(clips)]
                turn += 1
                f, lo, hi = SRC[cid]
                at = pos[cid]
                if at > hi:
                    at = lo
                pos[cid] = at + STEP
                s["game_clip"], s["game_at"] = f, round(at, 1)
    return lines


if __name__ == "__main__":
    lines = per_beat(build("endings_script.txt", E.RULES, E.POOLS))
    missing = [p for p, *_r in BEATS if not any(re.search(p, t) for t, _s in lines)]
    write(ROOT / "gta6_endings_scenes.csv", lines, E.RULES)
    print("beats never found:", missing)
