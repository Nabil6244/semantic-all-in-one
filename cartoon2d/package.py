"""Collect finished episodes into one folder: video, 3 thumbnails and UPLOAD.md (title, description, chapters, tags).

python3 cartoon2d/package.py ep02 [ep03 ...]      -> cartoon2d/episodes/<NN - Title>/
Thumbnail frames are picked from the timeline (the moments named in META[...]["thumbs"]), in episode time.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "cartoon2d" / "episodes"

COMMON_TAGS = ["ms molly", "bobo the bear", "toddler learning video", "preschool learning video", "learning videos for toddlers",
               "kids songs", "educational videos for kids", "cartoon for toddlers", "kids cartoon"]
META = {
    "ep02": {
        "folder": "02 - Counting with Ms Molly and Bobo",
        "title": "Learn to Count 1 to 10 with Ms Molly & Bobo the Bear 🎈 Counting Song & Games | Toddler Learning",
        "word": "1 2 3!",
        "thumbs": ["TEN! I did it", "Look at me!", "Pop, pop, pop!"],
        "intro": "Bobo the Bear wants to win the Big Bounce by bouncing ten times on his trampoline, but he can only count "
                 "\"one, two, seven, one hundred!\" 🐻 Help Ms Molly, Lily and Ollie teach Bobo to count from 1 to 10!",
        "learn": ["🔢 Count from 1 to 10", "🦘 Jump, bounce, hop and stomp while counting", "⚽ Count catches and ball bounces",
                  "🎈 Pop balloons and count them", "🍎 Easy adding and taking away with Bobo's snack",
                  "🙈 Count to 10 in hide and seek", "🚀 Count down from 10 to blast off", "🎵 Sing the counting song"],
        "tags": ["learn to count", "counting 1 to 10", "counting for toddlers", "numbers for kids", "counting song",
                 "1 to 10 song", "counting games for kids", "hide and seek for kids", "number freeze dance", "blast off countdown"],
        "next": "Next episode: Shapes with Bobo!",
    },
    "ep03": {
        "folder": "03 - Shapes with Ms Molly and Bobo",
        "title": "Learn Shapes with Ms Molly & Bobo the Bear 🔺 Circle, Square, Triangle | Shape Song for Toddlers",
        "word": "SHAPES!",
        "thumbs": ["Hooray! Hooray!", "Look at this house", "Party balloons"],
        "intro": "It's Bobo's birthday party! 🎂 He needs round cookies, square presents and triangle pizza, but Bobo keeps "
                 "mixing up his shapes. Help Ms Molly, Lily and Ollie teach Bobo the circle, the square and the triangle!",
        "learn": ["⚪ Learn the circle, square, triangle (and a star!)", "🔢 Count the sides of each shape",
                  "🏠 Find shapes in everyday things: cookies, clocks, windows, presents, pizza",
                  "✋ Draw shapes in the air and play Shape Simon Says", "🙈 Hide and seek behind the square box",
                  "🎵 Sing the shape song and dance the shape freeze dance"],
        "tags": ["learn shapes", "shapes for toddlers", "shapes for kids", "circle square triangle", "shape song",
                 "shapes song for kids", "simon says for kids", "freeze dance", "learning shapes preschool"],
        "next": "Next episode: Farm Animals with Bobo!",
    },
    "ep04": {
        "folder": "04 - Farm Animals with Ms Molly and Bobo",
        "title": "Farm Animals & Animal Sounds with Ms Molly & Bobo 🐮 Moo, Oink, Quack | Toddler Learning Video",
        "word": "MOO!",
        "thumbs": ["Woof, woof! I", "Here we are at the farm", "Freeze! Cow"],
        "intro": "Bobo wants to be a farmer for the day, but he thinks cows say \"woof\"! 🐮 Visit the farm with Ms Molly, "
                 "Lily and Ollie and help Bobo learn all the farm animals and their sounds.",
        "learn": ["🐄 Learn farm animals: cow, pig, sheep, duck, horse, chicken, dog", "🔊 Learn the animal sounds",
                  "🐸 Move like the animals: waddle, hop, stomp, flap", "🐣 Meet baby animals: chick, lamb, puppy",
                  "👂 Play the guess-the-sound game and Animal Simon Says", "🎵 Sing the farm song and dance the animal freeze dance"],
        "tags": ["farm animals", "animal sounds", "farm animals for toddlers", "animal sounds for kids", "farm song",
                 "learn animals", "baby animals", "animal moves for kids", "farm animals preschool"],
        "next": "Next episode: ABCs with Bobo!",
    },
}


def main():
    for ep in sys.argv[1:]:
        m = META[ep]
        st_path = ROOT / "cartoon2d" / "scenes" / f"{ep}_render.json"
        st = json.loads(st_path.read_text())
        build = ROOT / st["build"]
        video = build / f"{st['name']}.mp4"
        dest = OUT / m["folder"]
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copy(video, dest / f"{m['folder']}.mp4")
        tl = json.loads((ROOT / st["timeline"]).read_text())
        times = []
        for key in m["thumbs"]:
            ln = next(l for l in tl["lines"] if l["text"].startswith(key))
            times.append(str(round(ln["start"] + 1.2, 2)))
        subprocess.run([sys.executable, str(ROOT / "cartoon2d" / "thumbnail.py"), str(st_path), m["word"], *times], check=True)
        for i in range(1, len(times) + 1):
            shutil.copy(build / f"thumb_{i}.jpg", dest / f"thumbnail_{i}.jpg")
        chapters = (build / "chapters.txt").read_text().strip()
        dur = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video)]))
        tags = ", ".join(m["tags"] + COMMON_TAGS)
        desc = "\n".join([m["intro"], "", "In this video your little one will:", *m["learn"], "", "Chapters:", chapters, "",
                          "Made for toddlers and preschoolers (ages 1 to 5). Sing, clap, jump and dance along with Ms Molly and Bobo!",
                          m["next"] + " Subscribe so you don't miss it.", "", "#ToddlerLearning #KidsSongs #MsMolly"])
        (dest / "UPLOAD.md").write_text(
            f"# {m['folder']}\n\nLength: {int(dur // 60)}:{int(dur % 60):02d}\n\n## Title\n\n{m['title']}\n\n"
            f"## Description\n\n```\n{desc}\n```\n\n## Tags ({len(tags)} characters)\n\n```\n{tags}\n```\n\n"
            "## Settings\n\nMade for Kids = Yes · Category: Education · Language: English · Captions: auto (check them)\n\n"
            "## Thumbnails\n\nthumbnail_1.jpg, thumbnail_2.jpg, thumbnail_3.jpg - use YouTube Studio's Test & compare with all three.\n")
        print("PACKAGED", dest)


if __name__ == "__main__":
    main()
