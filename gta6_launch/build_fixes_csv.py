"""Writes gta6_fixes_scenes.csv: '10 Fixes Before Your First Night in GTA 6' (Game Launch style, the user's own voiceover).

fixes_script.txt is the pasted script split into sentences. Chapter cards open the three problems plus the cloud, the clock
and the preload files, so each becomes a Short. Every number on screen comes from the script."""
from pathlib import Path

from build_cartheft_csv import hud
from build_confirmed_csv import L, ST, T1, T2, chap, g, split, title
from build_map_csv import BK, CC, PC, PL, build, steps, write

ROOT = Path(__file__).resolve().parent
KEYS = "Leonida Keys=Florida Keys@24.72,-81.1"
VICE = "Vice City=Miami@25.77,-80.19"


def fix(n, name, clip, at):
    return title(f"FIX {n}", name, clip, at)


RULES = [
    # ---- cold open
    (r"^Three things are about to ruin", [title("3 PROBLEMS", "YOUR FIRST NIGHT IN LEONIDA", T2, 154.3)]),
    (r"one of them is a cop", [hud("heat", "icons=face,outfit,vehicle,partner lit=outfit")]),
    (r"^Another is a TV setting", [title("INPUT LAG", "A TV SETTING THAT DELAYS EVERY PRESS", BK, 4.0)]),
    (r"^The third is a download bar", [hud("download", "STILL CRAWLING::YOU=4.7|EVERYONE ELSE=0.1")]),
    (r"^All three have fixes, ten in total", [hud("checklist", "TONIGHT/10 FIXES IN THE ORDER YOU NEED THEM::1-3  THE DOWNLOAD|"
                                                                "4-7  THE SCREEN AND SOUND|8-10  THE COPS AND YOUR MONEY")]),
    (r"^Stay to the end", [title("THE PRELOAD FILES", "ONE CLUE  ·  ONE SETTING TO LEAVE ALONE", L, 46.4)]),
    # ---- problem 1: the download
    (r"^Start with the download bar", [chap("THE DOWNLOAD", "Problem 1  ·  fixes 1 to 3", T1, 36.8)]),
    (r"^Back in 2013", [hud("cards", "GTA V · XBOX 360 · 2013::DISC 1=Install from it|DISC 2=Play from it")]),
    (r"^GTA 6 has no disc at all", [hud("nodisc", "NO DISC AT ALL")]),
    (r"up to 212 gigabytes", [hud("stats", "ROCKSTAR::212 GB=up to, depending on console|0=discs, even boxed")]),
    (r"^Early unboxings show", [hud("checklist", "EARLY UNBOXINGS/WHAT'S IN THE BOX::A DOWNLOAD CODE|A DOUBLE-SIDED POSTER|"
                                                  "NO PAPER MAP")]),
    (r"how long will 212 gigabytes", [hud("download", "212 GB  ·  HOW LONG IT TAKES::100 MBPS=4.7|600 MBPS=0.75")]),
    (r"perfect-world numbers", [g(T1, 22.3)]),
    (r"start preloading on November 10th", [hud("checklist", "FIX 1/THE PRELOAD::STARTED NOVEMBER 10|OPEN GTA 6 IN YOUR LIBRARY|"
                                                             "IS THE BAR MOVING?|NOT MOVING? START IT YOURSELF")]),
    (r"run a cable to the console", [hud("cards", "CABLE vs WI-FI::ETHERNET=Steady|WI-FI=Don't trust it")]),
    (r"^That is fix one", [fix(1, "PRELOAD + CABLE", T2, 114.3)]),
    (r"^Fix two is space", [fix(2, "SPACE", T2, 34.0)]),
    (r"about 223 gigabytes", [hud("stats", "THE GAP::212 GB=Rockstar|223 GB=data miners  ·  +11")]),
    (r"I would want 230 gigabytes free", [hud("stats", "LEAVE ROOM::230 GB=free before launch|+=a likely day-one patch")]),
    (r"do not delete a single game yet", [title("DON'T DELETE GAMES", "CHECK THE CAPTURE GALLERY FIRST", L, 6.3)]),
    (r"^Sort by size", [steps("FIX 2 · FREE THE SPACE", "Sort the gallery by size; Clear the big clips; Or move them to a USB "
                              "stick; Turn trophy videos off", T2, 34.0)]),
    (r"buy an internal SSD", [hud("cards", "PS5 STORAGE::INTERNAL SSD=Stores and plays|USB DRIVE=Stores, can't play")]),
    (r"^Fix three is to let the console work", [fix(3, "WORK WHILE YOU SLEEP", T1, 10.3)]),
    (r"^In the power saving settings", [hud("checklist", "POWER SAVING/REST MODE::STAY CONNECTED TO THE INTERNET|"
                                                         "AUTOMATIC DOWNLOADS ON")]),
    (r"console and controller updates today", [hud("checklist", "TODAY::CONSOLE UPDATE|CONTROLLER UPDATE")]),
    (r"^So the download is handled", [g(T1, 18.8)]),
    # ---- problem 2: the screen
    (r"^That is problem two, the screen", [chap("THE SCREEN", "Problem 2  ·  fixes 4 to 7", L, 54.6)]),
    (r"targets 30 frames per second", [hud("stats", "ROCKSTAR · NOV 10::30 FPS=every console|PS5 PRO=included")]),
    (r"^The Pro gets a sharper image", [hud("cards", "PS5 PRO ONLY::PSSR=Sony's AI upscaler|RAY TRACED SHADOWS=Nowhere else")]),
    (r"^Every PS5 gets haptic", [hud("checklist", "EVERY PS5::HAPTIC FEEDBACK|TEMPEST 3D AUDIO|FASTER LOADING")]),
    (r"brings us to fix four", [fix(4, "GAME MODE", BK, 14.0)]),
    (r"^Turn on game mode", [hud("cards", "YOUR TV::GAME MODE=On|MOTION SMOOTHING=Off")]),
    (r"invents extra frames", [g(BK, 20.0)]),
    (r"^Fix five is checking", [fix(5, "REAL 4K", T1, 24.3)]),
    (r"^On PS5, open screen and video", [hud("cards", "SCREEN AND VIDEO::VIDEO OUTPUT INFO=What the console sends|"
                                                      "TV CAPABILITIES=What the TV accepts")]),
    (r"never offers 2160p", [hud("checklist", "NO 2160P? THE USUAL CULPRITS::AN OLD HDMI CABLE|A SOUNDBAR PASSING IT THROUGH")]),
    (r"^Fix six is the HDR calibration", [fix(6, "HDR", T1, 27.45)]),
    (r"raise each pattern", [g(T1, 30.05)]),
    (r"leave VRR and 120 hertz on automatic", [hud("cards", "LEAVE ON AUTOMATIC::VRR=Automatic|120 HZ=Automatic")]),
    (r"^Why would I tell you", [title("120 HZ?", "FOR A 30 FPS GAME", L, 24.3)]),
    (r"^Fix seven is sound", [fix(7, "SOUND", "gta6_shark_attack.mp4", 4.0)]),
    (r"^Turn on 3D audio", [hud("checklist", "SOUND SETTINGS::3D AUDIO ON|ANY WIRED HEADPHONES IN THE CONTROLLER")]),
    (r"not set to stereo", [hud("cards", "SOUNDBAR OR SURROUND::OUTPUT=Not stereo")]),
    (r"^Keep haptics and adaptive triggers", [hud("controller", "KEEP THEM ON::R2=ADAPTIVE TRIGGERS|L2=ADAPTIVE TRIGGERS")]),
    (r"charge the controller and clear the dust", [hud("checklist", "BEFORE THE FIRST LONG SESSION::CHARGE THE CONTROLLER|"
                                                                    "CLEAR THE DUST FROM THE VENTS")]),
    # ---- cloud
    (r"still on an Xbox One", [chap("XBOX ONE + THE CLOUD", "You're not locked out", T2, 84.3)]),
    (r"streams through Xbox Cloud Gaming", [hud("cards", "XBOX CLOUD GAMING::REPORTEDLY=Series S settings|YOU NEED=To own the game")]),
    (r"capping cloud play at 15 hours", [hud("stats", "GAME PASS ULTIMATE::15 H=cloud play a month|?=how GTA 6 counts")]),
    (r"^VGC reported that existing members", [hud("cards", "VGC · NO CAP FOR EXISTING MEMBERS::AUSTRALIA=|GERMANY=|BRAZIL=|"
                                                            "KEEP=The subscription running")]),
    (r"^The US, the UK and Canada", [hud("cards", "NOT ON THE LIST::THE US=|THE UK=|CANADA=")]),
    (r"fifteen hours is a single weekend", [title("BACKUP PLAN", "NOT THE PLAN", T2, 140.3)]),
    # ---- the clock
    (r"^Now the clock", [chap("THE CLOCK", "Who sees what first", T1, 12.8)]),
    (r"midnight local time on November 19th", [hud("unlock", "MIDNIGHT LOCAL TIME::13|19|New Zealand|The UK")]),
    (r"^Forbes found", [hud("cards", "FORBES · US STOREFRONTS::EASTERN TIME=Midnight|WEST COAST=9 PM on the 18th")]),
    (r"dodging spoilers", [g(T2, 64.3)]),
    (r"mute GTA 6, Jason and Lucia", [hud("checklist", "MUTE FOR A COUPLE OF DAYS::GTA 6|JASON|LUCIA")]),
    (r"skip the so-called leaked build", [title("THE \"LEAKED BUILD\"", "SKIP IT", L, 12.3)]),
    (r"113 gigabyte GTA 6 file", [hud("stats", "SECURITY TESTERS::113 GB=almost all empty padding|1=small piece of malware")]),
    (r"cheap accounts are the same kind of trap", [hud("scam", "")]),
    # ---- problem 3: the cop
    (r"^Which brings us to the problem that can cost", [chap("THE COP", "Problem 3  ·  fixes 8 to 10", T1, 44.3)]),
    (r"you do not start rich", [split(T2, 6.6, ST + "pexels_33959669.mp4", 3.0, "LEONIDA KEYS", "FLORIDA KEYS")]),
    (r"^You start in the Leonida Keys", [hud("garage", "PREVIEWS · YOUR START::3|Car one|Car two|Car three|One more")]),
    (r"^They track your clothes", [hud("heat", "icons=outfit,face,vehicle,partner lit=outfit,face,vehicle,partner")]),
    (r"^A hat or sunglasses is not enough", [hud("heat", "icons=outfit,face,vehicle,partner lit=face,vehicle,partner off=outfit")]),
    (r"^So fix eight is a spare outfit", [fix(8, "A SPARE OUTFIT", L, 46.8)]),
    (r"^Haircuts are less clear", [hud("cards", "THE HAIRCUT::SOME REVIEWERS=Clears your face|OTHERS=It doesn't")]),
    (r"lose the cops first", [g(BK, 28.0)]),
    (r"^Fix nine is where you sell", [fix(9, "WHERE YOU SELL", CC, 2.0)]),
    (r"scans a car and tells you", [hud("checklist", "PREVIEWS/THE PHONE SCAN::AN ALARM?|A TRACKER?|WHAT IT'S WORTH")]),
    (r"open with a slim jim", [hud("tiers", "")]),
    (r"^Paint spray is back", [hud("cards", "WHERE TO SELL::PAINT SPRAY=Back|SPECIALTY FENCES=Pay for the good stuff")]),
    (r"lose it before you drive", [g(CC, 29.0)]),
    (r"^Fix ten is the money", [fix(10, "THE MONEY", T2, 46.8)]),
    (r"cash you are carrying is gone", [hud("cards", "PREVIEWS::POCKET CASH=Gone if you die or get arrested|THE BANK=Safe")]),
    (r"^So deposit early", [g(T2, 46.8)]),
    (r"never register eventually vanish", [title("UNREGISTERED CARS", "EVENTUALLY VANISH", PL, 280.0)]),
    (r"best early purchase is somewhere to keep", [title("BUY STORAGE", "THE BEST EARLY PURCHASE", T2, 152.3)]),
    (r"pre-order pack before November 20th", [hud("cards", "PRE-ORDER PACK · BEFORE NOV 20::'55 VAPID STANIER=Car|"
                                                             "OUTFITS=Clothes|WEAPON PATTERN=Cosmetic|SHORE COURT GARAGE=By Ocean Beach")]),
    # ---- preload files
    (r"^Finally, the preload files", [chap("THE PRELOAD FILES", "The clue", L, 46.4)]),
    (r"^They are encrypted", [hud("checklist", "DATA MINERS · NOT CONFIRMED/WHAT THEY CAN SEE::FILE NAMES|FILE SIZES|"
                                                "NOT THE CONTENTS")]),
    (r"^Tez2 found the story", [hud("stats", "TEZ2 · STORY ZERO::18 GB=the story's own chunk|+=online hangs off it")]),
    (r"story and online could install separately", [hud("cards", "THE THEORY::STORY=Install on its own|ONLINE=Install on its own")]),
    (r"^Audio alone is over 22 gigabytes", [hud("stats", "AUDIO ALONE::22 GB+=in the preload")]),
    (r"mention 120 hertz output", [title("120 HZ", "IN THE FILES", L, 54.6)]),
    (r"a 40 frames per second mode", [hud("stats", "THE USUAL REASON::40 FPS=a mode that needs|120 HZ=a TV that can show it")]),
    (r"Rob Nelson has only promised 30", [hud("cards", "SO FAR::PROMISED=30 FPS at launch|MAYBE=40 FPS on 120 Hz")]),
    (r"^That is every fix I have got", [hud("checklist", "10 FIXES::1 PRELOAD + CABLE|2 SPACE|3 REST MODE|4 GAME MODE|5 REAL 4K|"
                                                         "6 HDR|7 SOUND|8 SPARE OUTFIT|9 WHERE YOU SELL|10 BANK YOUR CASH")]),
    (r"Which time zone did you unlock in", [title("YOUR TURN", "WHICH TIME ZONE?  ·  WHICH PROBLEM?", T2, 154.3)]),
]

POOLS = [
    [(L, 6.3), (T1, 36.3), (T2, 114.3), (L, 26.3)],        # intro
    [(T1, 10.3), (T1, 22.3), (L, 60.3), (T2, 20.3)],       # download
    [(T1, 24.3), (L, 54.6), (T2, 35.5), (BK, 4.0)],        # screen
    [(T2, 84.3), (T2, 140.3), (L, 40.3)],                  # cloud
    [(T1, 12.8), (T2, 64.3), (L, 66.3)],                   # clock
    [(T1, 44.3), (T2, 144.3), (CC, 7.0), (L, 46.8)],       # cop
    [(L, 46.4), (T2, 154.3), (T1, 36.8), (PC, 2.0)],       # preload
]

if __name__ == "__main__":
    write(ROOT / "gta6_fixes_scenes.csv", build("fixes_script.txt", RULES, POOLS), RULES)
