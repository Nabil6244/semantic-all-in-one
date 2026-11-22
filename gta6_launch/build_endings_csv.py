"""Writes gta6_endings_scenes.csv: 'GTA 6 All Endings Explained' (Game Launch style, free Edge voice, no Shorts).

Footage is post-launch gameplay only (no trailers): the real bridge aftermath and Cal's credits scene cut from two YouTube
uploads, plus free-roam, chase, boat and save-menu clips (footage/trailer/gta6_end_*.mp4, sources in library/raw/yt_endings).
The endings themselves are told with cards, since no real footage of the prompts or the prison scene was found."""
from pathlib import Path

from build_cartheft_csv import hud
from build_confirmed_csv import g, timeline, title
from build_map_csv import build, write

ROOT = Path(__file__).resolve().parent
BR, CAL, CH, KEYS, CITY, FP, GC, NT, BOAT, SAVE = (f"gta6_end_{n}.mp4" for n in (
    "bridge", "cal", "chase", "drive_keys", "drive_city", "first_person", "green_car", "night_drive", "boat", "save_menu"))


def t(a, b, clip, at):
    return title(a, b, clip, at)


def chap(a, b, clip, at):
    return {"shot": "chapter", "title": a, "subtitle": b, "game_clip": clip, "game_at": at}


RULES = [
    # ---- open
    (r"^Quick spoiler warning", [t("SPOILER WARNING", "ALL GTA 6 ENDINGS", NT, 2.0)]),
    (r"click away now", [g(NT, 12.0)]),
    (r"^Still here\?", [g(CH, 60.0)]),
    (r"twenty-five-minute finale", [t("MISSION 91", "THE END OF THE ROAD", CH, 120.0)]),
    (r"^Sheriff cars block the bridge", [g(BR, 2.0)]),
    (r"two button prompts appear", [hud("cards", "THE BRIDGE::TRIANGLE=Swim for It|R2=No Surrender")]),
    (r"^Wrong, and that is the exact brutal trap", [t("THE TRAP", "SWIM FOR IT ≠ SURVIVAL", BR, 8.0)]),
    (r"two of the three confirmed endings", [hud("stats", "3 CONFIRMED ENDINGS::2=both die on the bridge|1=both survive")]),
    (r"one four-word line", [hud("checklist", "TODAY/WATCH FOR::JASON'S 4-WORD LINE|THE HIDDEN CAL SCENE|THE MANUAL SAVE TRICK")]),
    # ---- setup
    (r"^Before we compare all three endings", [chap("THE SETUP", "How Rockstar traps you", KEYS, 20.0)]),
    (r"kicks off at Cal's place in the Keys", [g(KEYS, 40.0)]),
    (r"plug a hard drive", [hud("checklist", "MISSION 91/OBJECTIVE::PLUG THE HARD DRIVE IN|LET CAL'S SOFTWARE DECRYPT IT")]),
    (r"body armor and frag grenades", [hud("cards", "LOADOUT::BODY ARMOR=On|FRAG GRENADES=Ready")]),
    (r"construction elevator", [g(BOAT, 10.0)]),
    (r"somebody tipped off the cops", [t("TIPPED OFF", "THE DOCKS ARE BURNED", CH, 150.0)]),
    (r"South Point airfield", [timeline("THE ESCAPE ROUTE", ["PLAN A=Cal's boat offshore", "DOCKS=Cops waiting",
                                                            "PLAN B=South Point airfield", "THE BRIDGE=Sealed by sheriffs"])]),
    (r"nothing else in this entire twenty-five-minute mission", [hud("stats", "MISSION 91::25 MIN=no other decision|1=the freeze-frame")]),
    # ---- ending 1
    (r"^Let's start with what happens when you pick \"No Surrender\"", [chap("ENDING 1", "No Surrender  ·  R2", CH, 90.0)]),
    (r"slams the accelerator", [g(CH, 95.0)]),
    (r"smash straight through the barricade", [g(CH, 170.0)]),
    (r"both Jason and Lucia are shot dead", [g(BR, 10.0), hud("cards", "ENDING 1 · NO SURRENDER::JASON=Killed|LUCIA=Killed")]),
    (r"classic, heartbreaking Bonnie and Clyde", [t("BONNIE & CLYDE", "THE ENDING FANS PREDICTED", BR, 16.0)]),
    # ---- ending 2
    (r"reload your save and hit Triangle", [chap("ENDING 2", "Swim for It  ·  version A", BOAT, 30.0)]),
    (r"two completely different versions", [hud("cards", "SWIM FOR IT · TWO VERSIONS::VERSION A=Doomed|VERSION B=Survivor")]),
    (r"\"Don't do anything stupid,\" you are already doomed", [hud("quote", "THE DOOMED LINE::Don't do anything stupid.|Jason|"
                                                                            "Swim for It · version A")]),
    (r"sandbar, steal a boat, and head for Cuba", [g(BOAT, 50.0)]),
    (r"still gripping his pistol", [hud("checklist", "THE FATAL MISTAKE::ONE HAND UP|PISTOL STILL IN THE OTHER")]),
    (r"Jason drops dead on the asphalt", [g(BR, 20.0), hud("cards", "ENDING 2 · SWIM FOR IT (A)::JASON=Killed|LUCIA=Killed")]),
    # ---- ending 3
    (r"^In the third confirmed ending", [chap("ENDING 3", "Swim for It  ·  version B", BOAT, 70.0)]),
    (r"says four words", [hud("quote", "THE SURVIVOR LINE::Don't draw your weapon.|Jason|Swim for It · version B")]),
    (r"single Triangle prompt reading", [hud("cards", "THE SECOND PROMPT::TRIANGLE=Exit")]),
    (r"Lucia leaps off the concrete barrier", [g(BOAT, 85.0)]),
    (r"Lucia is completely gone", [hud("cards", "ENDING 3 · THE SURVIVOR ENDING::LUCIA=Escaped into the water|JASON=Arrested")]),
    (r"Jason's mugshot", [t("VICE-DALE PD", "THE MUGSHOT", NT, 30.0)]),
    (r"Hey, Duval", [hud("quote", "THE TIME JUMP::Hey, Duval. Got a visitor.|A guard|The credits")]),
    (r"saying one single word", [hud("quote", "THE VISIT::Surprise.|Lucia, holding a toddler|The credits")]),
    (r"took the fall in prison", [g(GC, 40.0)]),
    # ---- fact check
    (r"what actually locks this ending", [chap("THE FACT-CHECK", "What unlocks the survivor ending?", CITY, 30.0)]),
    (r"They claim you need two million", [hud("checklist", "THE VIRAL LIST/TIKTOK + REDDIT::$2M IN BUCKME SAVINGS|"
                                                           "MAX ROMANCE WITH LUCIA|PROFESSIONAL CRIMINAL PROFILE|SPARE A COP")]),
    (r"no \"spare the cop\" prompt", [hud("lockout", "UNVERIFIED::NO SPARE-THE-COP PROMPT|NO SAVINGS CHECK|"
                                                     "NO PROFILE POPUP|the list is a guess")]),
    (r"a lot more than two", [hud("quote", "ROCKSTAR::A lot more than two ending variants|Shaped by earlier choices|"
                                           "All five chapters")]),
    # ---- Cal
    (r"do not skip the credits", [chap("DON'T SKIP THE CREDITS", "Cal's scene  ·  all 3 endings", CAL, 1.0)]),
    (r"cuts back to Cal sitting alone", [g(CAL, 3.0)]),
    (r"waiting all day for that stolen hard drive", [g(CAL, 10.0)]),
    (r"the files finally unlock", [g(CAL, 20.0)]),
    (r"You Gotta Know When to Get Off", [hud("cards", "SECRET GOLD TROPHY::YOU GOTTA KNOW WHEN TO GET OFF=50 Gamerscore")]),
    (r"rewinds you back before the finale", [t("STORY COMPLETE", "REWINDS TO BEFORE THE FINALE", GC, 80.0)]),
    (r"head back out into Vice City", [g(CITY, 120.0)]),
    # ---- save
    (r"do not rely on the single autosave", [chap("THE SAVE TRICK", "Before Mission 91", SAVE, 1.0)]),
    (r"manual save in a fresh slot", [g(SAVE, 4.0)]),
    (r"removed Mission Replay", [hud("lockout", "NO MISSION REPLAY::REPLAY THE FINALE|PICK THE OTHER PROMPT|"
                                                "your manual save does it")]),
    (r"^Play through once", [hud("checklist", "THE PLAN::1  PLAY ONCE + WATCH CAL|2  UNLOCK YOUR 61 CHEATS|"
                                              "3  RELOAD, TRY THE OTHER PROMPT")]),
    (r"Which ending did you get", [t("WHICH ENDING?", "DROP IT IN THE COMMENTS", NT, 40.0)]),
]

POOLS = [
    [(NT, 20.0), (CH, 30.0), (FP, 20.0), (KEYS, 60.0)],
    [(KEYS, 80.0), (CITY, 10.0), (FP, 50.0), (BOAT, 5.0)],
    [(CH, 100.0), (CH, 130.0), (BR, 12.0), (FP, 80.0)],
    [(BOAT, 40.0), (BR, 22.0), (NT, 40.0)],
    [(BOAT, 60.0), (GC, 10.0), (NT, 25.0), (KEYS, 120.0)],
    [(CITY, 60.0), (FP, 110.0), (GC, 60.0), (KEYS, 140.0)],
    [(CAL, 14.0), (CAL, 25.0), (GC, 100.0), (CITY, 150.0)],
    [(SAVE, 10.0), (CITY, 90.0), (GC, 110.0), (FP, 130.0)],
]

if __name__ == "__main__":
    write(ROOT / "gta6_endings_scenes.csv", build("endings_script.txt", RULES, POOLS), RULES)
