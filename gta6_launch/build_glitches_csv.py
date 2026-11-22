"""Writes gta6_glitches_scenes.csv: 'Every Wild GTA 6 Day-One Glitch' (Game Launch style, six acts from the assembly guide).

Footage: the clip library (footage/library, hard-linked into footage/trailer) plus the three trailers. A line that names a
streamer's clip we do not have gets a card over trailer footage, never somebody else's clip passed off as theirs; the library's
own glitch clips play where they match (Lucia's scooter fall = gta6_glitch_fall_through_map). New hud cards: quote, void, launch."""
import csv
import re
from pathlib import Path

from build_cartheft_csv import hud
from build_confirmed_csv import L, T1, T2, board, chap, g, timeline, title
from build_launchnight_csv import COLS, END

ROOT = Path(__file__).resolve().parent
FM, CG, TR = "gta6_glitch_fall_through_map.mp4", "gta6_glitch_cage.mp4", "gta6_glitch_tattoo_ragdoll.mp4"
GL, BK, SH, PL = "gta6_first_glitch.mp4", "gta6_bike_night_crash.mp4", "gta6_shark_attack.mp4", "gta6_plane_steal.mp4"
END = {**END, FM: 20.5, CG: 28.0, TR: 7.5, GL: 117.0, BK: 37.0, SH: 104.0, PL: 340.0}
VIEW = "6.38M LIVE/STREAMS CHARTS::YOUTUBE=2.66 M|TWITCH=2.50 M|KICK=1.31 M"
RULES3 = "3 SURVIVAL RULES/TONIGHT::NO PHONE IN TIGHT GAPS|MANUAL SAVE BEFORE STUNTS|PUNCH OUT OF WALL GRABS"

CHAPTERS = [
    (r"^Imagine booting up", "FLOOR DROPS & WALL COPS", "Act 2", FM, 2.0),
    (r"^Wait until you see what happens", "GHOST PLANES & BRIDGE SHIPS", "Act 3", PL, 237.0),
    (r"^Okay, floating coffee cups", "SWINGSET & SHADOW REALM", "Act 4", GL, 50.0),
    (r"^Now let’s drop the clickbait", "THE 1% REALITY CHECK", "Act 5", T2, 116.8),
    (r"^So before you jump into Vice City", "3 SURVIVAL RULES TONIGHT", "Act 6", BK, 10.0),
]

RULES = [
    (r"a boat climbs a bridge", [title("13 YEARS LATER", "A BOAT CLIMBS A BRIDGE", SH, 14.0)]),
    (r"six million live viewers", [hud("download", VIEW)]),
    (r"ninety-nine on Metacritic", [hud("stats", "METACRITIC::99=GTA VI|99=Ocarina of Time")]),
    (r"lost its mind", [g(TR, 2.5), g(CG, 15.0)]),
    (r"mortar shells", [g(BK, 26.5)]),
    (r"solid concrete walls", [title("COPS IN THE WALLS", "INSIDE A PRECINCT", L, 70.8)]),
    (r"black void", [g(FM, 16.5)]),
    (r"every studio dreads", [hud("quote", "ON X TONIGHT::It's Cyberpunk 2077 all over again|MichaelDoesLife on X|via PlayStation LifeStyle")]),
    (r"cancel your download", [title("DON'T CANCEL YET", "HALF THE STORY", T2, 154.3)]),
    (r"full console restart", [g(CG, 20.0)]),
    (r"Shadow Realm\.$", [g(FM, 19.0)]),
    (r"from two thousand eight", [title("2008 IS BACK", "THE PHYSICS MEME RETURNS", GL, 52.0)]),
    (r"caught on camera tonight", [hud("cards", "TONIGHT'S GLITCHES::FLOOR DROPS=Falling under the map|WALL COPS=Fused into drywall"
                                                 "|GHOST PLANES=Phasing through towers|BRIDGE SHIPS=Climbing the road"
                                                 "|FLYING CARS=The swingset returns|SHADOW REALM=The one that traps you")]),
    (r"ruins your save", [board(["Harmless comedy=yes", "Ruins your save=no"], CG, 6.0, "COMEDY OR SAVE-KILLER?")]),
    (r"hundreds of thousands watching", [g(T2, 108.3)]),
    (r"Kai Cenat", [title("KAI CENAT  ·  LIVE", "COPS CLOSE IN", L, 48.8)]),
    (r"busted screen", [hud("wasted", "THE SCREEN CHAT EXPECTED::BUSTED|busted|A TRIP TO COUNTY JAIL")]),
    (r"stopped existing", [title("THE FLOOR STOPPED EXISTING", "MID-ARREST", T2, 144.3)]),
    (r"sheer collision failure", [hud("void", "UNDER THE MAP::ESCAPED THE COPS|THROUGH COLLISION FAILURE")]),
    (r"exact same problem in the Prologue", [g(FM, 0.5)]),
    (r"flee on a scooter", [g(FM, 2.0)]),
    (r"tase her", [g(FM, 5.0)]),
    (r"BaylenLatona", [g(FM, 9.0), g(FM, 15.5)]),
    (r"plummeted endlessly", [g(FM, 17.5), g(FM, 19.5)]),
    (r"strange launch day", [g(T1, 24.3)]),
    (r"MichaelDoesLife walked into", [title("MICHAELDOESLIFE", "PICKS A FIGHT IN THE PRECINCT", T2, 108.3)]),
    (r"wet clay", [g(TR, 3.0)]),
    (r"solid precinct wall", [hud("cards", "THE WALL GRAB::1=Cop tackles Jason|2=Both bodies fuse|3=Pulled into the wall")]),
    (r"knocked the officer out", [g(L, 70.8)]),
    (r"spit Jason back", [title("SPAT BACK OUT", "ONCE THE COP WAS DOWN", L, 48.3)]),
    (r"into the sky", [g(PL, 237.0)]),
    (r"hits a skyscraper", [g(T2, 34.7)]),
    (r"Michael Bay fireball", [title("WINDPRESS", "EXPECTING A FIREBALL", PL, 280.0)]),
    (r"popped his parachute", [g(PL, 290.0)]),
    (r"like a ghost", [title("NO EXPLOSION", "THROUGH THE TOWER LIKE A GHOST", T1, 18.8)]),
    (r"Criminal Profile", [hud("stats", "THE DAMAGE::0=Smoke|0=Debris|0=Casualties")]),
    (r"Kick streamer Neon", [title("NEON  ·  KICK", "MID-AIR POLICE CHASE", PL, 300.0)]),
    (r"zero parachute", [g(PL, 310.0)]),
    (r"massive explosion", [g(L, 52.0)]),
    (r"single sliver of health", [hud("stats", "THE LANDING::5,000 FT=No parachute|100%=Health left")]),
    (r"JasonTheWeen", [title("JASONTHEWEEN", "MID-DRIVE ON A BRIDGE", T1, 35.75)]),
    (r"the ocean glitched", [g(SH, 12.0)]),
    (r"wedged sideways", [g(T2, 90.3)]),
    (r"climbing onto the asphalt", [title("THE SHIP CLIMBS THE ROAD", "BRIDGE SUPPORTS  ·  ASPHALT", SH, 16.0)]),
    (r"Gone Fishing", [g(SH, 0.5), g(SH, 5.0)]),
    (r"didn’t even blink", [g(T2, 8.2)]),
    (r"genuinely dangerous", [board(["Swingset launch=yes", "Shadow Realm=no"], GL, 95.0, "NOSTALGIC VS DANGEROUS")]),
    (r"remember the swingset", [title("GTA IV  ·  2008", "THE SWINGSET", T1, 70.8)]),
    (r"launched into orbit", [hud("launch", "LAUNCHED INTO ORBIT::2008=SWINGSET")]),
    (r"spiritual successor", [hud("launch", "THE SPIRITUAL SUCCESSOR::2008=SWINGSET|2026=TREE")]),
    (r"TheCanadianGTR", [title("THECANADIANGTR", "VS AN ORDINARY TREE", L, 46.3)]),
    (r"catapulted their entire car", [g(BK, 27.0)]),
    (r"heavy truck rocketing", [g(L, 48.3)]),
    (r"brutal catch", [title("THE BRUTAL CATCH", "", GL, 104.0)]),
    (r"completely wrecked", [g(BK, 29.0)]),
    (r"repair money", [hud("cash", "")]),
    (r"yelling Cyberpunk", [hud("quote", "THE COMPARISON::Cyberpunk 2077 all over again|Posts on X tonight|")]),
    (r"out of twenty-twenty", [timeline("THE FEAR", ["DEC 2020=Cyberpunk 2077 launch", "NOV 2026=GTA VI launch"])]),
    (r"Raeed", [title("RAEED ON X", "THE OPENING SEQUENCE", T2, 6.3)]),
    (r"PlayStation One nightmare", [title("PS1 MODE", "TEXTURES FAILED TO LOAD", T1, 12.3)]),
    (r"worse than San Andreas", [hud("cards", "THE TEXTURE BUG::WORLD=Whole stretches vanished|FACES=Worse than San Andreas"
                                               "|WHEN=Opening sequence")]),
    (r"FACELESS", [title("FACELESS ON X", "THE SAVE-TRAP GLITCH", L, 12.3)]),
    (r"parked car and a fence", [g(CG, 12.0)]),
    (r"reality breaks", [g(T1, 46.8)]),
    (r"pitch-black void", [hud("void", "THE SHADOW REALM::NO TELEPORT BACK|JASON STARING AT HIS PHONE")]),
    (r"never teleports you back", [board(["Lucia's scooter fall: teleported back=yes", "Phone void: teleported back=no"], FM, 18.0,
                                         "WHICH ONE LETS YOU OUT?")]),
    (r"praying your last manual save", [title("CLOSE THE GAME", "PRAY YOUR SAVE IS RECENT", FM, 19.8)]),
    (r"PlayStation pulled it off the store", [hud("stats", "2020 VS 2026::PULLED=Cyberpunk from the PS Store|99=GTA VI Metascore")]),
    (r"same broken category", [g(T2, 140.3)]),
    (r"remarkably polished", [title("REMARKABLY POLISHED", "50-150 HOURS PER CRITIC", T2, 86.3)]),
    (r"Shacknews", [hud("cards", "WHAT CRITICS FOUND::SHACKNEWS=One floating coffee cup|GOSUGAMERS=Brief clothing pop-ins"
                                 "|SYDNEY MORNING HERALD=Pedestrians walking into walls")]),
    (r"GosuGamers", [g(L, 4.3)]),
    (r"brick walls", [g(T1, 8.3)]),
    (r"flooding your feed", [g(FM, 16.0)]),
    (r"simple math", [hud("download", VIEW.replace("6.38M LIVE/STREAMS CHARTS", "THE STRESS TEST/6.38M WATCHING LIVE"))]),
    (r"two-hundred-twelve-gigabyte", [hud("stats", "MIDNIGHT STRESS TEST::10M=Players|212 GB=Simulation")]),
    (r"edge cases slip through", [hud("cards", "WHAT THE ENGINE TRACKS::WATER=Dynamic waves and wakes|SAFEHOUSES=Shifting with the story"
                                                "|INTERIORS=Hundreds you can enter")]),
    (r"divide velocity by zero", [hud("launch", "ONE TREE, ONE ORBIT::2026=TREE")]),
    (r"rite of passage", [g(GL, 107.5)]),
    (r"Rule number one", [hud("checklist", "RULE 1::NEVER PULL OUT THE PHONE IN A TIGHT GAP")]),
    (r"hard restart gets Jason back", [hud("void", "SHADOW REALM::HARD RESTART ONLY|")]),
    (r"Rule number two", [hud("checklist", "RULE 2::MANUAL SAVE BEFORE ANY STUNT")]),
    (r"removed Mission Replay", [hud("archive", "NO MISSION REPLAY::YOUR MANUAL SAVE IS THE BACKUP")]),
    (r"Rule number three", [hud("checklist", "RULE 3::KEEP SWINGING IF A COP PULLS YOU INTO A WALL")]),
    (r"spit you right back out", [hud("checklist", RULES3)]),
    (r"accidentally triggered", [g(CG, 24.0)]),
    (r"Drop it in the comments", [title("WHICH BUG GOT YOU?", "TELL US IN THE COMMENTS", BK, 33.0)]),
]

POOLS = [
    [(T2, 28.3), (L, 26.8), (T1, 12.3), (BK, 4.0)],
    [(FM, 3.5), (T2, 106.3), (L, 70.8), (TR, 1.0)],
    [(PL, 250.0), (PL, 320.0), (SH, 8.0), (T2, 36.3)],
    [(GL, 60.0), (BK, 18.0), (CG, 8.0), (FM, 18.5)],
    [(T2, 86.3), (L, 4.3), (T1, 8.3), (T2, 140.3)],
    [(BK, 14.0), (L, 47.6), (T2, 107.6), (L, 70.6)],
]


def build():
    lines, used, act, pool_i, seen = [], set(), 0, [0] * len(POOLS), []
    for sent in [x.strip() for x in (ROOT / "glitches_script.txt").read_text(encoding="utf-8").splitlines() if x.strip()]:
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
                tries = 0
                while tries < 14 and any(c == sh["game_clip"] and abs(a - float(sh["game_at"])) < 1.6 for c, a in seen):
                    tries += 1
                    nxt = round(float(sh["game_at"]) + 1.7, 1)
                    sh["game_at"] = nxt if nxt < END.get(sh["game_clip"], 1e9) else round(0.5 + nxt % 7, 1)
            if sh.get("game_clip") and sh.get("game_at") not in ("", None):
                seen.append((sh["game_clip"], float(sh["game_at"])))
        lines.append((sent, shots))
    return lines


if __name__ == "__main__":
    out = ROOT / "gta6_glitches_scenes.csv"
    lines = build()
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        for t, shots in lines:
            for i, s in enumerate(shots):
                w.writerow({"narration": t if i == 0 else "", **{k: s.get(k, "") for k in COLS[1:]}})
    unused = [p for k, (p, _s) in enumerate(RULES) if not any(re.search(p, t) for t, _ in lines)]
    print(out, len(lines), "lines; rules never matched:", unused)
