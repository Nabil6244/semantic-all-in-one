"""Writes gta6_savefile_scenes.csv: 'GTA 6's 99 and the Save-File Trap' (Game Launch style, six acts from the editing guide).

savefile_script.txt holds one voice line per line (lines are not re-split: 'A.M.' would break the sentence splitter).
Act openers get a chapter card; the rules give lines their graphics (first match wins, each rule used once); the rest take the
next trailer shot from the act's pool. New hud cards: saves, controller, archive (plus profile, download, stats, cards ...)."""
import csv
import re
from pathlib import Path

from build_cartheft_csv import hud
from build_confirmed_csv import L, ST, T1, T2, board, chap, g, mp, real, timeline, title
from build_launchnight_csv import COLS, END

ROOT = Path(__file__).resolve().parent
NZ = "Wellington=New Zealand@-41.29,174.78"
AKL = "Auckland=New Zealand@-36.85,174.76"
VICE = "Vice City=Miami@25.77,-80.19"
SAVES = "15 MANUAL SAVE SLOTS::1=PROLOGUE|2-13=EVERY 5-10%|14=PRE-FINALE|15=CHAOS"
PAD = "THE NEW CONTROLS::L3=SPRINT|X=HANDBRAKE|L1=AIM|R1=FIRE"

CHAPTERS = [  # line start -> chapter card (act 1 opens on the title)
    (r"^To understand why your save files", "THE DEATH OF MISSION REPLAY", "After 17 years", T1, 52.3),
    (r"^Back on June twenty-fifth", "THE $99.99 TRAP", "Three catches", T2, 46.3),
    (r"^Here is why the fifteen manual save slots", "THE 15-SAVE RULE", "Your only lifeline", L, 46.3),
    (r"^Even if you manage your fifteen save slots", "THE NEW CONTROLS", "Muscle memory betrays you", L, 70.3),
    (r"^When your countdown timer finally hits zero", "THE HOUR-ONE BLUEPRINT", "Before Chapter One", T2, 152.3),
]

RULES = [
    (r"^At exactly eleven", [title("NOV 18  ·  11:00 GMT", "HISTORY HAPPENED", T2, 154.3)]),
    (r"review embargo", [mp(NZ, L, 60.3)]),
    (r"one hundred and nine critic reviews", [hud("stats", "METACRITIC::99=Metascore|109=Critic reviews")]),
    (r"Ocarina of Time", [hud("stats", "THE HIGHEST EVER::99=Ocarina of Time|99=GTA VI")]),
    (r"Super Mario Odyssey", [hud("stats", "LEFT BEHIND AT 97::97=Red Dead Redemption 2|97=Breath of the Wild|97=Super Mario Odyssey")]),
    (r"nine million players", [hud("stats", "PRE-ORDERS::9M+=Players|$1.5B=Generated")]),
    (r"twenty-two percent", [title("+22%", "PS5 SALES IN ONE MONTH", T2, 20.3)]),
    (r"preloading two hundred and twelve", [hud("download", "212 GB  ·  PRELOAD WEEK::100 MBPS=4.7|50 MBPS=9.4|25 MBPS=18.8")]),
    (r"locations to Wellington", [hud("unlock", "15 HOURS EARLY::15|19|New Zealand|Mexico & Central America")]),
    (r"tourism board", [title("GLOBAL TIME TRAVELERS", "NEW ZEALAND CELEBRATES", T1, 2.3)]),
    (r"Twitch threatened bans", [board(["Xbox: no region switching=no", "Twitch: no fake NZ residency=no"], T2, 106.3,
                                       "THE WARNINGS")]),
    (r"fake secondary accounts in Auckland", [mp(AKL, T2, 108.3)]),
    (r"massive shock", [g(L, 68.6), g(T1, 64.3)]),
    (r"Simon Cardy", [title("LESS THAN AN HOUR IN", "AN URGENT WARNING", T1, 47.8)]),
    (r"something bizarre", [g(T2, 116.8)]),
    (r"seventeen straight years", [title("17 YEARS", "AND IT VANISHED", L, 38.3)]),
    (r"brutal catch", [title("$99.99", "THE BRUTAL CATCH", T2, 46.8)]),
    (r"permanently strip your paid bonus", [g(L, 64.3), g(T2, 120.3)]),
    (r"no undo button", [title("NO UNDO BUTTON", "ONE AUTOSAVE  ·  50 HOURS", T1, 70.3)]),
    (r"lock yourself out of entire chapters", [hud("cards", "WHAT YOU CAN LOSE::CHAPTERS=Locked out for good|SAFEHOUSES=Gone with the story"
                                                             "|ENDINGS=Before the credits roll")]),
    (r"Ballad of Gay Tony", [timeline("MISSION REPLAY", ["2009=Ballad of Gay Tony", "2010=Red Dead Redemption",
                                                         "2013=GTA V", "2018=RDR2", "NOV 19 2026=GTA VI  ·  gone"])]),
    (r"bronze, silver, and gold", [hud("cards", "THE MEDALS::BRONZE=Finish the job|SILVER=Do it well|GOLD=Do it perfectly")]),
    (r"it took two clicks", [hud("stats", "REPLAY A HEIST::2=Clicks in GTA V|0=Ways in GTA VI")]),
    (r"zero Gold Medal objectives", [title("ZERO GOLD MEDALS", "NO CHECKLISTS IN THE PROLOGUE", T2, 8.2)]),
    (r"wall of static thumbnail", [hud("archive", "COMPLETED MISSIONS::A WALL OF STILL PICTURES")]),
    (r"removed Mission Replay at launch", [hud("archive", "")]),
    (r"cannot select previous story chapters", [board(["Replay a mission=no", "Chapter select=no"], L, 34.3, "IN THE MENU")]),
    (r"baffling step backward", [hud("stats", "IGN::10/10=The review|BUT=A baffling step backward")]),
    (r"autosave icon spins", [title("AUTOSAVE", "THAT MOMENT IS GONE", T1, 66.8)]),
    (r"Why would Rockstar spend ten years", [g(T2, 152.8)]),
    (r"fugitive status", [hud("cards", "LEONIDA TRACKS::YOUR BANK=Every dollar|SAFEHOUSES=Where you sleep|FUGITIVE STATUS=Who hunts you")]),
    (r"Standard Edition launched at seventy-nine", [hud("stats", "THE EDITIONS::$79.99=Standard|$99.99=Ultimate  ·  digital only")]),
    (r"twenty-three thousand readers", [hud("stats", "IGN POLL  ·  23,000+ READERS::70%=Chose the $100 edition")]),
    (r"first true hundred-dollar", [title("THE FIRST $100 GAME", "FOR MILLIONS OF PLAYERS", L, 18.3)]),
    (r"Wyman’s Classic Car Collection\.", [hud("cards", "PRE-ORDER BONUS::VINTAGE VICE CITY PACK=Before November 20|"
                                                         "WYMAN'S CLASSIC CARS=A car collection")]),
    (r"Grotti Cheetah", [hud("cards", "THE BUNDLE::'95 GROTTI CHEETAH=Supercar|SAFEHOUSE VEHICLES=Jason's cars|"
                                      "MORGAN REVOLVERS=Custom guns|VICE CITY STYLE=Clothes and tattoos")]),
    (r"wardrobe and garage in Chapter One", [g(T2, 98.3)]),
    (r"three harsh realities", [hud("checklist", "THREE CATCHES/IGN::Cosmetics are not free|Items locked behind chapters|"
                                                 "Some items are taken away")]),
    (r"^Catch number one", [title("CATCH #1", "NOT FREE IN-GAME", T2, 42.3)]),
    (r"twenty extra real-world dollars", [hud("cards", "WHAT $20 BUYS::THE RIGHT TO BUY=Not the items|THE SHOPS=You still pay in game")]),
    (r"most expensive items in the state", [hud("cash")]),
    (r"^Catch number two", [title("CATCH #2", "LOCKED BEHIND CHAPTERS", L, 38.8)]),
    (r"equip every bonus weapon", [g(L, 46.8), g(T1, 30.3)]),
    (r"catch number three", [title("CATCH #3", "THE UPROAR", T2, 128.3)]),
    (r"permanently taken away", [board(["Some items taken away=no"], T2, 130.3, "IGN CONFIRMED")]),
    (r"confiscate items", [g(L, 52.8)]),
    (r"luxury mansions", [hud("cards", "GTA V vs GTA VI::GTA V=Buy any safehouse|GTA VI=Garages and storage only")]),
    (r"garages and vehicle storage", [title("GARAGES ONLY", "AND VEHICLE STORAGE BAYS", T2, 120.8)]),
    (r"go on the run", [g(T1, 56.3), g(L, 40.3)]),
    (r"burn a safehouse chapter down", [title("SAFEHOUSE BURNED", "ITS BONUSES VANISH", L, 52.3)]),
    (r"advancing past that point is permanent", [title("PERMANENT", "NO CHAPTER SELECT  ·  NO REPLAY", T1, 22.3)]),
    (r"disappear forever", [g(T2, 18.3)]),
    (r"exactly fifteen manual save slots", [hud("saves", "15 MANUAL SAVE SLOTS::1-15=EMPTY")]),
    (r"roughly fifty hours", [hud("stats", "HOW LONG::50H=Main story|200H=Platinum trophy")]),
    (r"only chapter select you get", [hud("saves", SAVES)]),
    (r"every five to ten percent\.", [hud("download", "STORY COMPLETION/A NEW SAVE EVERY 5-10%::SAVE=10%|SAVE AGAIN=20%|AND AGAIN=30%")]),
    (r"Slot One through Slot Fourteen", [hud("saves", "ROTATE::1-14=IN ORDER")]),
    (r"playable snapshot", [hud("cards", "EVERY SLOT KEEPS::A SAFEHOUSE=Before it burns|A MAP REGION=As it was|"
                                         "BONUS VEHICLES=Before they go")]),
    (r"money gates", [title("MONEY GATES", "CASH TOTALS TO ADVANCE", T2, 92.3)]),
    (r"never get trapped", [g(T2, 64.3)]),
    (r"instead of using all fifteen", [g(L, 60.8)]),
    (r"Chaos and Rampage save", [hud("saves", "SLOT 15::1-14=STORY|15=CHAOS")]),
    (r"hidden behavioral mechanic", [g(T2, 24.3)]),
    (r"independent Criminal Profiles", [hud("profile", "level=0")]),
    (r"zip-ties and intimidation", [hud("profile", "level=0")]),
    (r"slides toward Psychopath", [hud("profile", "level=3")]),
    (r"chilling detail", [g(T1, 66.3)]),
    (r"irreversible cracked icon state", [hud("profile", "level=4")]),
    (r"never restore your Professional", [title("CRACKED", "NO WAY BACK ON THAT SAVE", T2, 106.8)]),
    (r"player empathy", [title("BUILT FOR EMPATHY", "IGN'S LAUNCH REVIEW", L, 40.8)]),
    (r"multiple different story endings", [title("MULTIPLE ENDINGS", "CONFIRMED", T1, 72.3)]),
    (r"culminates in the finale", [g(L, 30.8), g(T2, 100.3)]),
    (r"separate save file before going on rampages", [hud("saves", "KEEP IT APART::1-14=STORY|15=RAMPAGE")]),
    (r"cheat codes", [title("BEAT THE STORY", "UNLOCK THE CHEAT CODES", T2, 154.8)]),
    (r"alter your ending forever", [g(L, 72.3)]),
    (r"shot town sheriffs", [g(T1, 24.3)]),
    (r"accidentally draw your revolver", [g(T1, 44.3)]),
    (r"would be catastrophic", [hud("profile", "level=4")]),
    (r"rebuilt their on-foot controller", [hud("controller", "ON FOOT::L3=SPRINT")]),
    (r"mash the X button", [hud("cards", "SPRINT::OLD WAY=Mash X or A|NEW WAY=Click L3")]),
    (r"Sprint to L3", [hud("controller", "SPRINT MOVED::L3=SPRINT")]),
    (r"deliberate command before aiming", [g(L, 48.3)]),
    (r"talk to NPCs", [g(T2, 90.3)]),
    (r"first police chase", [g(L, 48.8), g(T2, 34.3)]),
    (r"moved from R1 down to the X button", [hud("controller", "IN THE CAR::X=HANDBRAKE")]),
    (r"L1 and R1 are now dedicated", [hud("controller", "DRIVE-BY::L1=AIM|R1=FIRE|X=HANDBRAKE")]),
    (r"drift around a corner", [title("TAP R1 TO DRIFT?", "YOU FIRE YOUR WEAPON", L, 71.0)]),
    (r"much more physical", [g(T2, 138.6)]),
    (r"jumbo jet", [real(ST + "px_airport_runway_plane_landing.mp4", 2.0)]),
    (r"physical boarding path", [g(T1, 10.3)]),
    (r"three mandatory technical hurdles", [hud("checklist", "BEFORE THE TITLE SCREEN/THREE HURDLES::Firmware 14.22|"
                                                             "The day-one patch|Frame drops on base PS5")]),
    (r"firmware fourteen point two-two is required", [title("FIRMWARE 14.22", "REQUIRED ON PS5", T2, 6.6)]),
    (r"refuse to boot", [title("NO FIRMWARE", "NO BOOT AT MIDNIGHT", L, 60.0)]),
    (r"mandatory day-one patch awaits", [g(L, 26.3)]),
    (r"six hundred and two megabytes", [hud("download", "DAY-ONE PATCH 1.002/THE DOWNLOAD AFTER THE PRELOAD::PS5=0.602 GB|XBOX=1.59 GB")]),
    (r"one point five-nine gigabyte", [hud("stats", "PATCH 1.002::602 MB=PlayStation 5|1.59 GB=Xbox Series X|S")]),
    (r"heavy explosion sequences", [g(L, 52.0)]),
    (r"thirty frames per second", [hud("stats", "BASE PS5::30=FPS target|DROPS=In big explosions")]),
    (r"^Step one", [hud("checklist", "STEP 1/30 MINUTES BEFORE MIDNIGHT::Firmware 14.22|Patch 1.002")]),
    (r"^Step two", [hud("saves", "STEP 2::1=PROLOGUE")]),
    (r"Never overwrite that Prologue", [title("SLOT 1", "NEVER OVERWRITE IT", T2, 8.6)]),
    (r"^Step three", [hud("saves", "STEP 3::1=PROLOGUE|2-4=NEW SLOT")]),
    (r"Slots Two to Thirteen", [hud("saves", "ROTATE::1=PROLOGUE|2-13=EVERY 5-10%")]),
    (r"you still own a playable chapter", [g(T2, 126.3)]),
    (r"^Step four", [hud("saves", "STEP 4::1=PROLOGUE|2-13=EVERY 5-10%|14=PRE-FINALE")]),
    (r"^Step five", [hud("saves", SAVES)]),
    (r"L3 sprints and X pulls", [hud("controller", PAD)]),
    (r"which platform", [title("PS5  ·  OR XBOX?", "TELL US BELOW", T2, 154.3)]),
]


POOLS = [  # per act (0 = act 1)
    [(T1, 12.3), (L, 26.8), (T2, 28.3), (L, 46.0)],
    [(T1, 54.3), (T2, 30.3), (L, 64.8), (T1, 68.3)],
    [(T2, 42.8), (L, 34.8), (T2, 132.3), (T1, 76.3)],
    [(T2, 114.3), (L, 12.3), (T1, 20.8), (T2, 140.3)],
    [(L, 47.6), (T2, 107.6), (T1, 49.5), (L, 70.6)],
    [(T2, 86.3), (L, 4.3), (T1, 8.3), (T2, 84.3)],
]


def build():
    lines, used, act, pool_i, seen = [], set(), 0, [0] * len(POOLS), []
    for sent in [x.strip() for x in (ROOT / "savefile_script.txt").read_text(encoding="utf-8").splitlines() if x.strip()]:
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
        if not shots or (len(shots) == 1 and len(sent.split()) >= 22 and shots[0]["shot"] == "chapter"):
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
    out = ROOT / "gta6_savefile_scenes.csv"
    lines = build()
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        for t, shots in lines:
            for i, s in enumerate(shots):
                w.writerow({"narration": t if i == 0 else "", **{k: s.get(k, "") for k in COLS[1:]}})
    unused = [p for k, (p, _s) in enumerate(RULES) if not any(re.search(p, t) for t, _ in lines)]
    print(out, len(lines), "lines; rules never matched:", unused)
