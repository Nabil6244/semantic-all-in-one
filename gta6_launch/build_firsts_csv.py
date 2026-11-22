"""Writes gta6_firsts_scenes.csv: 'GTA 6's First Glitch and First Tiger Death' (Game Launch style).

Footage: two streamer clips cleaned into the trailers folder (facecam / QR cropped off, Portuguese subtitles blurred, reaction
cuts listed in their .avoid.json): gta6_first_glitch.mp4 (night truck stuck in a hedge) and gta6_tiger_death.mp4 (van in the
mud, tiger, death screen, Key Lento respawn). The trailers fill the context act.
firsts_script.txt holds one voice line per line. New hud cards: firsts, wasted, stuck."""
import csv
import re
from pathlib import Path

from build_cartheft_csv import hud
from build_confirmed_csv import GRASS, KEYS, L, T1, T2, board, chap, g, mp, timeline, title
from build_launchnight_csv import COLS, END

ROOT = Path(__file__).resolve().parent
GL, TG = "gta6_first_glitch.mp4", "gta6_tiger_death.mp4"
NZ = "Wellington=New Zealand@-41.29,174.78"
BR = "Sao Paulo=Brazil@-23.55,-46.63"
END = {**END, GL: 117.0, TG: 85.0}


def spot(clip, at, xy, tag, hint=""):
    return {"shot": "spot", "game_clip": clip, "game_at": at, "place": xy, "title": tag, "subtitle": hint}


FIRSTS_EARLY = "GTA VI WORLD FIRSTS/LAUNCH NIGHT LOG::FIRST GLITCH=?|FIRST TIGER DEATH=?|FIRST 100%=?"

CHAPTERS = [
    (r"^Let us start with the one", "THE FIRST GLITCH", "A truck vs a garden", GL, 8.0),
    (r"^But the second clip", "THE FIRST TIGER DEATH", "Never push a stranger's van", TG, 2.0),
    (r"^So why is there a tiger", "WHY A TIGER?", "Welcome to Leonida", T2, 30.3),
    (r"^So the board is filling", "THE WORLD FIRSTS", "Claimed and unclaimed", L, 46.3),
]

RULES = [
    (r"less than a day", [title("LESS THAN 24 HOURS", "AND TWO LEGENDS ALREADY", TG, 44.0)]),
    (r"game simply gave up", [g(GL, 50.0)]),
    (r"eaten by a tiger", [g(TG, 13.0), g(TG, 40.5)]),
    (r"first glitch and the first tiger death", [hud("firsts", FIRSTS_EARLY)]),
    (r"how this new world actually works", [g(TG, 33.5)]),
    (r"what launch night looked like", [g(T2, 116.8)]),
    (r"New Zealand at midnight", [mp(NZ, L, 60.3)]),
    (r"Brazil, Europe, and America", [hud("unlock", "LAUNCH NIGHT::0|19|New Zealand|The Americas")]),
    (r"watching live", [title("MILLIONS WATCHING", "WAITING FOR ANYTHING STRANGE", T1, 47.8)]),
    (r"two Brazilian stream clips", [mp(BR, TG, 14.0)]),
    (r"quiet Leonida neighborhood", [g(GL, 14.0)]),
    (r"pink route", [spot(GL, 2.0, "0.12,0.85", "THE ROUTE", "Following the pink line")]),
    (r"too real", [g(GL, 22.0)]),
    (r"front yard", [g(GL, 30.0)]),
    (r"into a thick hedge", [g(GL, 35.0)]),
    (r"drive was over", [title("DRIVE OVER", "THE HEDGE WINS", GL, 44.0)]),
    (r"decorative rocks", [hud("stuck", "WHY THE TRUCK WON'T MOVE::ROCKS LIFT THE FRAME|WHEELS SPIN IN THE AIR|CAMERA CLIPS INTO THE HEDGE",
                               GL, 50.0)]),
    (r"lose their grip", [g(GL, 52.0)]),
    (r"not move a single inch", [g(GL, 55.0)]),
    (r"reverse, then forward", [g(GL, 64.0)]),
    (r"fighting the leaves", [g(GL, 67.0)]),
    (r"clipping into the hedge", [g(GL, 74.0), g(GL, 80.0)]),
    (r"turntable", [g(GL, 85.0)]),
    (r"palm plant", [g(GL, 98.0)]),
    (r"feel human", [g(GL, 92.0)]),
    (r"heavier driving model", [hud("cards", "THE NEW DRIVING::WEIGHT=Cars feel heavy|SUSPENSION=Every bump counts"
                                              "|CONTACT=Rocks can beat a truck")]),
    (r"rock can beat a truck", [g(GL, 102.0)]),
    (r"bounced free", [g(L, 26.8)]),
    (r"physics are honest", [title("HONEST PHYSICS", "TRAPPED IN A GARDEN", GL, 104.0)]),
    (r"finally slides off", [g(GL, 107.5)]),
    (r"drive just continues", [g(GL, 112.0)]),
    (r"ruined front yard", [g(GL, 115.0)]),
    (r"bug, or is it", [board(["Bug?=yes", "Realistic physics?=yes"], GL, 76.0, "BUG OR REALISM?")]),
    (r"patch one point zero zero two", [hud("download", "DAY-ONE PATCH/1.002::PS5=602 MB|XBOX=1.59 GB")]),
    (r"first big update", [g(GL, 88.0)]),
    (r"broad daylight", [mp(KEYS, TG, 3.0)]),
    (r"stuck deep in a flooded", [g(TG, 1.0)]),
    (r"asks for help", [g(TG, 6.0)]),
    (r"open the doors or push", [spot(TG, 9.5, "0.55,0.45", "TWO CHOICES", "Open or push")]),
    (r"starts pushing", [g(TG, 14.5)]),
    (r"shouting directions", [g(TG, 17.5)]),
    (r"opens the back doors", [g(TG, 20.0)]),
    (r"bright blue collar", [spot(TG, 21.0, "0.47,0.28", "LOOK INSIDE", "A tiger in the back")]),
    (r"leaps out of the van", [g(TG, 22.0)]),
    (r"naughty house cat", [title("\"BAD KITTY!\"", "THE OWNER'S ONLY PLAN", TG, 23.0)]),
    (r"Jason runs", [g(TG, 24.0)]),
    (r"get away", [g(TG, 26.5)]),
    (r"bravest and worst", [title("THE WORST DECISION", "OF LAUNCH DAY", TG, 28.5)]),
    (r"walked back toward", [g(TG, 30.0)]),
    (r"raises his fists", [g(TG, 34.0)]),
    (r"turning red at the edges", [g(TG, 37.0)]),
    (r"pins Jason down", [g(TG, 40.0)]),
    (r"death screen fades in", [g(TG, 44.5)]),
    (r"does not say wasted", [hud("wasted", "HOW YOU DIE NOW::WASTED|se fodeu|SAME DEATH  ·  LOCAL LANGUAGE")]),
    (r"completely done for", [title("\"YOU'RE DONE FOR\"", "ROUGH TRANSLATION", TG, 46.0)]),
    (r"Key Lento welcome sign", [spot(TG, 59.5, "0.45,0.45", "KEY LENTO", "The respawn point")]),
    (r"wooden dock", [g(TG, 68.0)]),
    (r"right reaction", [g(TG, 76.0)]),
    (r"Rockstar's version of Florida", [mp(KEYS, T2, 130.3)]),
    (r"exotic animals", [hud("cards", "FLORIDA, FOR REAL::BIG CATS=Kept as pets|ALLIGATORS=In swimming pools"
                                      "|SNAKES=Inside apartment walls")]),
    (r"random encounters", [g(TG, 11.0)]),
    (r"alligators in the swamps", [mp(GRASS, T1, 12.3)]),
    (r"Florida Man", [title("FLORIDA MAN", "LEVEL: TIGER IN A VAN", TG, 21.5)]),
    (r"did not feel scripted", [g(TG, 36.0)]),
    (r"one player's choice", [g(TG, 31.5)]),
    (r"background decoration", [hud("stats", "ANIMAL ATTACKS::GTA V=Rare, quick, easy to escape|GTA VI=Chase, fight, slow-motion finish")]),
    (r"mountain lion", [g(T2, 42.8)]),
    (r"slow-motion finish", [g(TG, 42.0)]),
    (r"side by side", [{"shot": "split", "game_clip": GL, "game_at": 58.0, "real": "", "left": "THE GLITCH", "right": "THE TIGER"}]),
    (r"reacts to the player", [g(TG, 38.5)]),
    (r"neither does the tiger", [g(GL, 60.0)]),
    (r"under twenty-four hours", [timeline("LAUNCH NIGHT", ["MIDNIGHT NZ=Leonida opens", "NIGHT ONE=Truck vs hedge",
                                                            "DAY ONE=Tiger in a van", "NEXT=Your clip?"])]),
    (r"claimed on launch night", [hud("firsts", "GTA VI WORLD FIRSTS/LAUNCH NIGHT LOG::FIRST GLITCH=NIGHT ONE|FIRST TIGER DEATH=?|FIRST 100%=?")]),
    (r"claimed on day one", [hud("firsts", "GTA VI WORLD FIRSTS/LAUNCH NIGHT LOG::FIRST GLITCH=NIGHT ONE|FIRST TIGER DEATH=DAY ONE|FIRST 100%=?")]),
    (r"still unclaimed\.$", [g(L, 70.6)]),
    (r"probably impossible", [hud("firsts", "GTA VI WORLD FIRSTS/STILL OPEN::FIRST GLITCH=NIGHT ONE|FIRST TIGER DEATH=DAY ONE"
                                            "|FIRST 100%=?|BEAT A TIGER BAREHANDED=?")]),
    (r"someone will be watching", [g(TG, 70.0)]),
    (r"Drop a comment", [title("YOUR WORLD FIRST?", "TELL US IN THE COMMENTS", TG, 80.0)]),
]

# a split needs a second clip: give it the tiger fight on the right
for _p, _sh in RULES:
    for _s in _sh:
        if _s.get("shot") == "split":
            _s.update({"real": f"footage/trailer/{TG}", "real_at": 33.0})

POOLS = [
    [(T1, 12.3), (L, 26.8), (T2, 28.3), (L, 46.0)],
    [(GL, 40.0), (GL, 57.0), (GL, 83.0), (GL, 95.0)],
    [(TG, 4.0), (TG, 15.5), (TG, 27.5), (TG, 39.0)],
    [(T2, 86.3), (L, 4.3), (T1, 8.3), (T2, 140.3)],
    [(L, 47.6), (T2, 107.6), (T1, 49.5), (L, 70.6)],
]


def build():
    lines, used, act, pool_i, seen = [], set(), 0, [0] * len(POOLS), []
    for sent in [x.strip() for x in (ROOT / "firsts_script.txt").read_text(encoding="utf-8").splitlines() if x.strip()]:
        shots = []
        for k, (pat, head, sub, clip, at) in enumerate(CHAPTERS):
            if re.search(pat, sent):
                act = k + 1
                shots.append(chap(head, sub, clip, at))
        for k, (pat, sh) in enumerate(RULES):
            if k not in used and re.search(pat, sent):
                used.add(k)
                shots += [dict(x) for x in sh]
                break
        if not shots:
            pool = POOLS[act]
            clip, at = pool[pool_i[act] % len(pool)]
            pool_i[act] += 1
            shots.append(g(clip, at + 0.4 * (pool_i[act] // len(pool))))
        for sh in shots:
            if sh.get("shot") == "game":
                while any(c == sh["game_clip"] and abs(a - float(sh["game_at"])) < 1.6 for c, a in seen):
                    nxt = round(float(sh["game_at"]) + 1.7, 1)
                    sh["game_at"] = nxt if nxt < END.get(sh["game_clip"], 1e9) else round(6.3 + nxt % 7, 1)
            if sh.get("game_clip") and sh.get("game_at") not in ("", None):
                seen.append((sh["game_clip"], float(sh["game_at"])))
        lines.append((sent, shots))
    return lines


if __name__ == "__main__":
    out = ROOT / "gta6_firsts_scenes.csv"
    lines = build()
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        for t, shots in lines:
            for i, s in enumerate(shots):
                w.writerow({"narration": t if i == 0 else "", **{k: s.get(k, "") for k in COLS[1:]}})
    unused = [p for k, (p, _s) in enumerate(RULES) if not any(re.search(p, t) for t, _ in lines)]
    print(out, len(lines), "lines; rules never matched:", unused)
