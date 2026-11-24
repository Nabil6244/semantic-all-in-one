"""Writes gta6_leak_scenes.csv: 'GTA 6 on PC in a Week? 5 Reasons to Doubt It' (Vice Ranked, the user's own voiceover).

leak_script.txt is the pasted script split into sentences. A chapter card opens each ranked reason (#5 to #1), the best case and
what to watch on Monday, so each becomes a Short. Every card says only what the script says and who said it (REPORTED / CLAIMS).
No leaked file, link or screen is ever shown. Trailer seconds are the known shots from build_police_csv.py."""
from pathlib import Path

from build_cartheft_csv import hud
from build_confirmed_csv import L, T1, T2, board, chap, g, real, split, timeline, title
from build_map_csv import BK, CC, build, write

ROOT = Path(__file__).resolve().parent
S = "footage/stock/px_"
NEWS_HELI, NIGHT_HELI, RAID, PICKUP = (T1, 67.4), (T1, 45.4), (T1, 48.3), (T1, 60.3)
LUCIA_CASH, WRECK, BRIDGE = (T1, 63.2), (T1, 64.4), (T1, 35.75)
WALL, PRISON, LUCIA_OUT, VEST = (T2, 47.4), (T2, 50.3), (T2, 63.4), (T2, 108.4)
COUNTY_HELI, ARMORED, BOAT_RUN, DIRT_BIKE = (T2, 138.4), (T2, 144.4), (T2, 146.4), (T2, 148.3)
CHASE, SHOOTOUT = (L, 47.3), (L, 61.4)


def ttl(t, sub, p):
    return title(t, sub, *p)


def ch(t, sub, p):
    return chap(t, sub, *p)


RULES = [
    # ---- cold open
    (r"^Somebody says GTA 6 could be playable", [g(*CHASE), hud("stats", "THE CLAIM::1 WEEK=to play it on PC|NOV 23=the countdown ends")]),
    (r"one file that would decide everything", [hud("cards", "WHAT'S STILL MISSING::THE FILE=The executable|THE TOOL=A working emulator")]),
    (r"rank the five biggest reasons", [hud("checklist", "5 REASONS/TO DOUBT THE ONE-WEEK PROMISE::#5 THE COUNTDOWN|#4 THE MISSING FILE|"
                                                         "#3 REAL OR NOT?|#2 THE FAKES|#1 THE WALL")]),
    (r"reported or claimed, not confirmed", [hud("cards", "HOW TO READ THIS VIDEO::REPORTED=An outlet says it|CLAIMED=The group says it|"
                                                          "CONFIRMED=Nothing here yet")]),
    (r"^This is Vice Ranked, and I will not", [ttl("VICE RANKED", "NO LINKS  ·  NO LEAKED FILES", CHASE)]),
    # ---- what happened
    (r"^Let's start with what actually happened", [ch("WHAT HAPPENED", "Nov 19  ·  launch day", NEWS_HELI)]),
    (r"group called Cyberleek posted", [g(*NIGHT_HELI), hud("cards", "THE CLAIM  ·  NOV 19::WHO=Cyberleek|WHAT=A full Nov 2026 Xbox build|"
                                                                     "HOW=By torrent")]),
    (r"209 gigabytes", [hud("stats", "REPORTED  ·  XDA::209 GB=reported size|NO .EXE=the file that launches it")]),
    (r"vx-underground reportedly inspected", [hud("cards", "WHO SAYS WHAT::VX-UNDERGROUND=Found real GTA 6 assets|OTHER OUTLETS=Not confirmed|"
                                                           "KOTAKU=Could not verify")]),
    (r"have not commented on this leak", [hud("cards", "OFFICIAL WORD::ROCKSTAR=No comment|TAKE-TWO=No comment")]),
    (r"^So the setup is files", [hud("checklist", "THE SETUP::FILES THAT LOOK REAL TO SOME|NO LAUNCHER|A PROMISE")]),
    (r"emulated inside a week", [hud("stats", "CYBERLEEK CLAIMS::7 DAYS=until PC players emulate it")]),
    # ---- #5
    (r"^Number five", [ch("#5  THE COUNTDOWN", "It has a history", BRIDGE)]),
    (r"executable drops on Monday", [timeline("THE COUNTDOWN", ["NOV 19=The leak claim", "NOV 23=Executable promised"])]),
    (r"fifteen million dollar market cap", [hud("cards", "TWO VERSIONS OF THE TERMS::VERSION 1=Sooner at a $15M coin cap|"
                                                         "VERSION 2=Nov 23 regardless|GAMEREACTOR=They don't line up")]),
    (r"October 10 the group threatened", [timeline("THE DEADLINES", ["OCT 10=$30M coin or discs", "NOV 23=Executable promised"])]),
    (r"coin missed the target", [hud("cards", "OCT 10  ·  WHAT HAPPENED::THE COIN=Missed the target|THE ACCOUNT=Went quiet")]),
    (r"two hundred fifty thousand dollar", [hud("stats", "REPORTED  ·  GAMEREACTOR::$250K=earlier crypto scheme")]),
    (r"a date from this group is a claim", [hud("cards", "THE NOV 23 DATE::STATUS=A claim|CHECKED BY=Nobody yet")]),
    # ---- #4
    (r"^Number four", [ch("#4  THE MISSING FILE", "No key, no game", PICKUP)]),
    (r"^Picture a car with everything", [g(*CHASE)]),
    (r"researchers can look around", [hud("cards", "209 GB, NO EXECUTABLE::CAN=Look around the data|CAN'T=Run it as released")]),
    (r"no independent proof", [hud("checklist", "REPORTED  ·  MIXED/NOT SHOWN YET::PROOF IT RUNS AS A FULL GAME|A WORKING PC VERSION")]),
    (r"^It starts if the key shows up", [hud("cards", "THE ONE-WEEK CLOCK::STARTS=If the key shows up|NOT=Today")]),
    (r"^Booting to a logo", [hud("cards", "WHAT COUNTS AS RUNNING?::BOOTS=A logo|PLAYS=A steady frame rate|THE GAP=Months")]),
    # ---- #3
    (r"^Number three: the sources", [ch("#3  REAL OR NOT?", "The sources disagree", NIGHT_HELI)]),
    (r"^TalkEsport reported", [hud("cards", "WHO CHECKED?::VX-UNDERGROUND=Real assets|TALKESPORT=Nobody confirmed a build|"
                                            "SHATTERED=Nobody checked it's whole")]),
    (r"August 26 statement", [hud("cards", "ROCKSTAR  ·  AUG 26::AUGUST LEAKS=Acknowledged as real|THIS BUILD=No comment")]),
    (r"real gameplay clips from August", [hud("cards", "DOESN'T FOLLOW::AUGUST=Real gameplay clips|NOVEMBER=A complete, bootable build?")]),
    # ---- #2
    (r"^Number two", [ch("#2  THE FAKES", "Already out there", (BK, 4.0))]),
    (r"viral video claimed to show GTA 6 booting", [g(*SHOOTOUT)]),
    (r"^XDA reports it was a hoax", [hud("cards", "THE VIRAL 'PC' CLIP  ·  NOV 17-18::CLAIM=GTA 6 booting on PC|REALITY=GTA 5 on PS5|"
                                                  "TRICK=An overlay on the title screen")]),
    (r"Xmarc posted a clip", [hud("cards", "THE XMARC CLIP  ·  NOV 19::CLAIM=PS5 recompilation|NO=Public jailbreak|"
                                           "NEEDS=Decrypted files")]),
    (r"113 gigabyte torrent", [hud("cards", "REPORTED  ·  TWEAKTOWN::LABEL=GTA 6 PC build, 113 GB|INSIDE=Mostly empty data|"
                                             "ALSO=Malware")]),
    (r"NordVPN", [hud("scam", "")]),
    (r"carries legal risk", [hud("cards", "THE OTHER RISK::LEGAL=Downloading or sharing it|TAKE-TWO=Reportedly pursuing leaks")]),
    (r"empties your accounts", [real(S + "atm_machine.mp4", 1.0)]),
    # ---- #1
    (r"^And number one", [ch("#1  THE WALL", "What most headlines skip", SHOOTOUT)]),
    (r"x86-64 chips", [split(*ARMORED, S + "video_game_controller_dark_room.mp4", 1.0, "XBOX SERIES X|S", "GAMING PC")]),
    (r"breaking the console's encryption", [hud("checklist", "REPORTED  ·  XDA/WHAT IT WOULD TAKE::BREAK THE ENCRYPTION|"
                                                              "REPLACE XBOX SYSTEM FUNCTIONS|REPLACE XBOX GRAPHICS")]),
    (r"no working Xbox Series X and S emulator", [hud("stats", "REPORTED  ·  GAMEREACTOR::0=working Xbox Series emulators")]),
    (r"live translator", [hud("cards", "ROUTE 1  ·  EMULATOR::LIKE=A live translator|WHEN=While you play")]),
    (r"other route is recompilation", [hud("cards", "ROUTE 2  ·  RECOMPILE::LIKE=Translating the whole book once|"
                                                     "GAMEREACTOR=Slower, less certain than a week")]),
    (r"PS5 build is the fallback", [hud("cards", "THE PS5 FALLBACK::CLAIM=A PS5 build instead|PS5 EMULATORS=Logos, early frames|"
                                                 "FULL GAMES=Not yet")]),
    (r"^That is the wall", [hud("checklist", "THE WALL/ONE WEEK = THE LEAKER'S NUMBER::THE TOOL IT NEEDS|NOBODY HAS BUILT IT")]),
    # ---- best case
    (r"best case for the optimists", [ch("THE BEST CASE", "Fair is fair", LUCIA_OUT)]),
    (r"Game Development Kit", [hud("cards", "THE OPTIMISTS' POINT::GDK=Shares architecture with Windows|BUT=No guarantee it runs")]),
    (r"suggested PC play could follow", [hud("cards", "IF THE FILE APPEARS::VX-UNDERGROUND=PC play within days|ONLY IF=The executable shows up")]),
    (r"Obbe Vermeij", [hud("cards", "AN OFFICIAL PC VERSION?::VERMEIJ=An early port helps Rockstar|RUMOR=Early 2027|"
                                    "ROCKSTAR=Nothing announced")]),
    (r"honest picture", [board(["Official PC date=no", "Leak verified=no", "Emulator built=no"], T2, 140.4, head="THE HONEST PICTURE")]),
    # ---- what to watch
    (r"what should you actually watch on Monday", [ch("WATCH ON MONDAY", "Three things", CHASE)]),
    (r"^First, whether the executable", [hud("checklist", "MONDAY  ·  NOV 23::THE EXECUTABLE APPEARS|INDEPENDENT PROOF IT RUNS|"
                                                          "ROCKSTAR OR TAKE-TWO SPEAKS")]),
    (r"was never a measurement", [hud("cards", "ONE WEEK WAS::A MEASUREMENT=No|THE LEAKER'S NUMBER=Yes")]),
    (r"countdown is the only part", [timeline("THE ONLY DATE", ["NOV 19=The claim", "NOV 23=The countdown"])]),
    (r"spoil the story", [real(S + "playing_video_games_night.mp4", 1.0)]),
    (r"thanks for watching", [ttl("VICE RANKED", "THE UPDATE AFTER MONDAY", BRIDGE)]),
]

POOLS = [
    [CHASE, SHOOTOUT, NEWS_HELI, (L, 62.8)],                     # intro
    [NIGHT_HELI, NEWS_HELI, (L, 46.6), WALL],                    # what happened
    [BRIDGE, LUCIA_CASH, (T1, 61.7), (CC, 7.0)],                 # #5 countdown
    [PICKUP, CHASE, (T1, 20.3), DIRT_BIKE],                      # #4 missing file
    [NIGHT_HELI, VEST, RAID, (T2, 106.4)],                       # #3 real or not
    [(BK, 4.0), (BK, 14.0), WRECK, BOAT_RUN],                    # #2 fakes
    [SHOOTOUT, (T2, 139.4), COUNTY_HELI, (L, 72.3)],                 # #1 wall
    [LUCIA_OUT, (T2, 57.3), (T2, 136.4), (T1, 41.35)],           # best case
    [CHASE, BRIDGE, PICKUP, (L, 62.8)],                          # watch on Monday
]

if __name__ == "__main__":
    write(ROOT / "gta6_leak_scenes.csv", build("leak_script.txt", RULES, POOLS), RULES)
