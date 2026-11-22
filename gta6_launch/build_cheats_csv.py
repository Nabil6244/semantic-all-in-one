"""Writes gta6_cheats_scenes.csv: 'All 61 GTA 6 Cheats and Why They Are Locked' (Game Launch style).

No cheat gameplay exists in the library, so the codes live on hud cards (dpad, grind, grid, prefix, pyramid, lockout, filter)
over trailer footage; vehicle / stunt / boat lines use the library clips (plane, bike, speedboat, jet ski, car).
Dexerto's X post (no video, two key-art pictures) appears as a quote card. cheats_script.txt = one voice line per line."""
import csv
import itertools
import re
from pathlib import Path

from build_cartheft_csv import hud
from build_confirmed_csv import L, T1, T2, chap, g, title
from build_launchnight_csv import COLS, END

ROOT = Path(__file__).resolve().parent
PL, BK, SH, CC, DJ, TG = ("gta6_plane_steal.mp4", "gta6_bike_night_crash.mp4", "gta6_shark_attack.mp4", "gta6_car_cat_attack.mp4",
                          "gta6_dog_jetski.mp4", "gta6_tiger_death.mp4")
END = {**END, PL: 340.0, BK: 37.0, SH: 104.0, CC: 36.0, DJ: 11.0, TG: 47.0}

BG = itertools.cycle([(T2, 28.3), (L, 26.8), (T1, 12.8), (T2, 106.3), (L, 60.8), (T2, 74.3), (L, 46.8), (T1, 39.85),
                      (T2, 140.3), (L, 12.3), (T2, 8.2), (L, 66.3), (T1, 60.3), (T2, 152.3), (L, 40.3), (T2, 114.3)])


def card(name, params):
    clip, at = next(BG)
    return hud(name, params, clip, at)


def code(name, seq, rule, status="", pre=""):
    return card("dpad", f"{name}::{seq}|{rule}|{status}|{pre}")


def grind(name, goal, what, prize=""):
    return card("grind", f"{name}::{goal}|{what}|{prize or name}")


def filt(name, kind, rule):
    return card("filter", f"{name}::{kind}|{rule}")


AMMO = "THE AMMO FAMILY::MAX AMMO=DURDLLUUDL|INFINITE AMMO=DURDLLUDDD|NO RELOAD=DURDLLUDDU"
PHYS = "THE PHYSICS FAMILY::ATTACK FORCE=DULLRDDUD|EXPLODING BALLS=DULLRDDUR|VEHICLE FORCE=DULLRDLUD"
VEHS = "THE VEHICLE FAMILY::BOOMAZOOM=LURDLLUL|MTL PUMPER=LURDLRRU|BULLDOZER=LURDLRRD"
FILT = "THE FILTER FAMILY::CATACLYSM=DDURRULLRR|DOLLHOUSE=DDURRULLDR|FADED GLORY=DDURRULLLR"
LADDER = ("21 VEHICLE SPAWNS::P-996 LAZER=Every challenge in the game|RHINO TANK=Every survival challenge|"
          "ONE FULL CATEGORY=Banshee · Emerus · Dominator|50 COCAINE FLAMINGOS=Inflatable Flamingo|"
          "5 CHALLENGES=Starter spawns|DISCOVER IT=Bulldozer · Ambulance")

CHAPTERS = [
    (r"^Hold on, before we get into the wild codes", "WHY ROCKSTAR LOCKED THEM", "The story comes first", L, 12.3),
    (r"^Now let.s crack open the vault", "THE 10 PLAYER CHEATS", "Money, armor and a hundred gym sessions", T2, 114.3),
    (r"^If you love pure cartoon physics", "THE 11 COMBAT CHEATS", "Exploding balls and the ammo ladder", T2, 84.3),
    (r"^Vehicle spawns make up", "THE 21 VEHICLE SPAWNS", "From a bulldozer to a fighter jet", T2, 152.3),
    (r"^Before we hit those sixteen", "ENVIRONMENT + 16 FILTERS", "Weather, time and a world flipped upside down", L, 60.8),
    (r"^Stop everything and look closely", "THE SECRET PREFIX PATTERN", "The codes are a language", T1, 39.85),
    (r"^So if you are starting Grand Theft Auto Six tonight", "THE FAST-TRACK PLAN", "Bank progress during the story", L, 40.3),
]

RULES = [
    # ---- act 1: the brick wall
    (r"very first thing you do", [g(L, 24.3)]),
    (r"look up the cheat codes", [g(T2, 152.3)]),
    (r"twenty-five years", [title("25 YEARS OF CHEATS", "THE RITUAL OF EVERY GTA LAUNCH", T1, 60.3)]),
    (r"spawn a tank on the sidewalk", [g(T2, 144.3)]),
    (r"millions of players tried", [g(L, 60.8)]),
    (r"exact directional sequence", [code("$250,000", "URDLULDR", "ENTERED ON DAY ONE", "NOTHING HAPPENS")]),
    (r"Absolutely nothing", [title("NOTHING", "NO CHIME · NO CASH · NO TANK", T2, 38.3)]),
    (r"No chime", [g(T1, 12.8)]),
    (r"sixty-one official cheat codes", [card("quote", "THE ANNOUNCEMENT::Cheat codes have officially returned in GTA 6. "
                                                  "There are 61 cheats to unlock after completing the main story.|Dexerto|X · Nov 18")]),
    (r"double-lock security wall", [card("stats", "THE DOUBLE LOCK::LOCK 1=Beat the story|LOCK 2=Beat the challenge")]),
    (r"ninety-one story missions", [card("grid", "LOCK 1 · THE STORY::91|91|STORY MISSIONS|")]),
    (r"forty-five to ninety hours", [card("stats", "BEFORE THE MENU EXISTS::45-90 H=to finish the story|91=missions")]),
    (r"hands you the keys", [g(T2, 64.3)]),
    (r"only unlocks four", [card("grid", "WHAT THE CREDITS GIVE YOU::61|4|UNLOCKED BY THE STORY|LOCKED BEHIND CHALLENGES")]),
    (r"fifty-seven cheats are locked", [g(T2, 86.3)]),
    (r"hold hands with your partner", [grind("GOLDEN HOUR", "4 H", "HOLDING HANDS WITH YOUR PARTNER")]),
    (r"fifty cocaine flamingos just", [grind("INFLATABLE FLAMINGO", "50", "COCAINE FLAMINGOS DESTROYED")]),
    (r"six-star wanted level\.$", [grind("MIGRAINE", "6:00", "MINUTES AT SIX STARS")]),
    (r"happens to your save file", [g(T2, 46.8)]),
    (r"every single category", [card("cards", "ALL 61 CHEATS::PLAYER=10 cheats|COMBAT=11 cheats|VEHICLES=21 spawns|"
                                              "ENVIRONMENT=3 cheats|SCREEN FILTERS=16 filters")]),
    (r"real reason Rockstar locked", [g(L, 66.3)]),
    # ---- act 2: why
    (r"hate fun", [g(T2, 20.3)]),
    (r"Stephen Donkin", [title("STEPHEN DONKIN", "VICE PRESIDENT OF DESIGN · ROCKSTAR GAMES", L, 40.3)]),
    (r"completely raw first", [g(T2, 74.3)]),
    (r"cash economy", [card("cash", "")]),
    (r"being broke", [g(T2, 114.3)]),
    (r"decent rifle", [g(T2, 84.3)]),
    (r"fighter jet or drop", [g(PL, 280.0)]),
    (r"post-game progression tree", [card("checklist", "THE NEW RULE/CHEATS = A POST-GAME REWARD::BEAT ALL 91 MISSIONS|"
                                                       "OPEN PROGRESS · CHEATS LIST|FINISH CHALLENGES TO UNLOCK MORE")]),
    (r"credits roll", [title("CHEATS LIST", "NEW TAB IN THE PROGRESS MENU", T2, 140.3)]),
    (r"completely overhauled", [g(L, 46.8)]),
    (r"ten-digit phone numbers", [title("NO MORE PHONE NUMBERS", "THE GTA IV AND GTA V WAY IS GONE", T1, 26.3)]),
    (r"triangle, circle, square", [g(T2, 10.8)]),
    (r"strictly the directional D-pad", [code("D-PAD ONLY", "URDL", "ARROWS ONLY", "EVERY CHEAT")]),
    (r"identical on PlayStation", [card("stats", "ONE CODE · BOTH CONSOLES::PS5=same arrows|XBOX SERIES X|S=same arrows")]),
    (r"three-step ritual", [card("controller", "THE CHEAT RITUAL::DPAD=1 · UP = PHONE|L1=2 · HOLD L1|R1=2 · TAP R1|L3=3 · NO STICK")]),
    (r"^Step one", [card("dpad", "STEP 1 · PULL OUT THE PHONE::U|STAND IN FREE ROAM|TAP UP")]),
    (r"^Step two", [card("stats", "STEP 2 · OPEN CHEAT ENTRY::PLAYSTATION=Hold L1 + tap R1|XBOX=Hold LB + tap RB")]),
    (r"^Step three", [code("STEP 3 · ENTER THE CODE", "??????????", "RAPID D-PAD TAPS · NEVER THE STICK", "ANY CODE")]),
    (r"PC keyboard cheats", [card("scam", "")]),
    (r"no PC version announced", [title("NO PC VERSION", "EVERY PC CHEAT LIST IS FAKE", T1, 44.3)]),
    (r"one huge catch", [g(T2, 46.8)]),
    (r"disables trophies", [card("lockout", "CHEAT ACTIVE::TROPHIES|ACHIEVEMENTS|MANUAL SAVING|for that entire session")]),
    (r"pad your story bank", [g(L, 6.3)]),
    (r"reload a clean save", [title("RELOAD A CLEAN SAVE", "TO EARN PROGRESS AGAIN", T2, 90.3)]),
    # ---- act 3: player cheats
    (r"five distinct categories", [card("cards", "FIVE CATEGORIES::PLAYER=10|COMBAT=11|VEHICLES=21|ENVIRONMENT=3|SCREEN FILTERS=16")]),
    (r"ten Player cheats, eleven", [card("stats", "61 CHEATS::10=player|11=combat|21=vehicles|19=environment + filters")]),
    (r"cracked the exact D-pad", [card("grid", "CRACKED ON LAUNCH DAY::61|17|CODES CONFIRMED|STILL TBC")]),
    (r"other forty-four", [g(T2, 36.3)]),
    (r"instant post-story rewards", [g(L, 12.3)]),
    (r"only money cheat", [title("$250,000", "THE ONLY MONEY CHEAT IN THE GAME", L, 6.3)]),
    (r"unlocks automatically", [code("$250,000", "URDLULDR", "UNLOCKS WHEN YOU BEAT MISSION 91")]),
    (r"Unlimited Focus, which", [g(T2, 84.3)]),
    (r"tongue-twister", [code("UNLIMITED FOCUS", "DUUDUDUDUR", "UNLOCKS WHEN YOU BEAT MISSION 91")]),
    (r"turns up the grind", [g(T2, 114.3)]),
    (r"full Body Armor", [g(T2, 64.3)]),
    (r"one hundred full workouts", [grind("BODY ARMOR", "100", "GYM WORKOUTS")]),
    (r"basically a bodybuilder", [code("BODY ARMOR", "DULUUUUUDD", "100 GYM WORKOUTS")]),
    (r"Drunk Mode", [g(L, 60.8)]),
    (r"buying alcohol", [grind("DRUNK MODE", "$2,500", "SPENT ON ALCOHOL AT BARS")]),
    (r"Raise Heat Level cheat", [g(T2, 144.3)]),
    (r"three-star wanted level twenty-five", [code("RAISE HEAT LEVEL", "LDRDUDU", "ESCAPE 3 STARS 25 TIMES")]),
    (r"Raise Wanted Level cheat", [grind("RAISE WANTED LEVEL", "50", "THREE-STAR ESCAPES")]),
    (r"stunt-based Player Cheats", [g(BK, 20.0)]),
    (r"No Fall Damage", [grind("NO FALL DAMAGE", "20", "FORTY-FOOT FALLS SURVIVED")]),
    (r"Parachute on command", [g(PL, 300.0)]),
    (r"Unlimited Nitrous", [grind("UNLIMITED NITROUS", "50", "STUNT JUMPS CLEARED")]),
    (r"Repair Vehicle", [g(BK, 29.0)]),
    (r"grind sounds intense", [g(T2, 38.3)]),
    # ---- act 4: combat
    (r"Attack Force\.$", [title("ATTACK FORCE", "UNLOCKS WHEN YOU BEAT THE STORY", T2, 84.3)]),
    (r"^Enter Down, Up, Left, Left", [code("ATTACK FORCE", "DULLRDDUD", "BEAT THE STORY")]),
    (r"Kill twenty-five enemies with vehicles", [code("VEHICLE FORCE", "DULLRDLUD", "25 VEHICLE KILLS")]),
    (r"into the stratosphere", [g(CC, 7.0)]),
    (r"spit out their drink", [g(L, 66.3)]),
    (r"literally called Exploding Balls", [grind("EXPLODING BALLS", "20", "ENEMIES HIT WITH EXPLOSIVES")]),
    (r"every sports ball explodes", [code("EXPLODING BALLS", "DULLRDDUR", "20 EXPLOSIVE HITS")]),
    (r"beach volleyball", [g(T1, 12.8)]),
    (r"true sharpshooters", [g(T2, 106.3)]),
    (r"shooting ranges\.$", [card("pyramid", "THE SHOOTING-RANGE LADDER::NO RELOAD=25 gold medals|INFINITE AMMO=25 silver medals|"
                                                 "MAX AMMO=20-25 bronze medals")]),
    (r"PC Gamer", [card("stats", "BRONZE MEDALS NEEDED::20=per PC Gamer|25=per PowerPyx")]),
    (r"^Its confirmed sequence is Down, Up, Right", [code("MAX AMMO", "DURDLLUUDL", "BRONZE MEDALS")]),
    (r"twenty-five silver", [code("INFINITE AMMO", "DURDLLUDDD", "25 SILVER MEDALS")]),
    (r"twenty-five gold", [code("NO RELOAD", "DURDLLUDDU", "25 GOLD MEDALS", "LISTED · FROM THE AMMO PATTERN")]),
    (r"mirror each other", [card("prefix", AMMO)]),
    (r"demolition marathons", [g(T2, 144.3)]),
    (r"one hundred grenades", [card("cards", "100-COUNT GRINDS::ALL EXPLOSIVE WEAPONS=100 grenades|EXPLODING BOTTLES=100 Molotovs")]),
    (r"Incendiary Ammo", [card("cards", "100-COUNT GRINDS::INCENDIARY AMMO=Burn 100 enemies|EXPLOSIVE SHOTGUN=100 explosive kills")]),
    (r"anti-tank launcher", [grind("HAUNERS H-AT", "100", "VEHICLES DESTROYED")]),
    (r"hardest cheat to unlock", [g(PL, 237.0)]),
    # ---- act 5: vehicles
    (r"twenty-one different rides", [card("pyramid", LADDER)]),
    (r"massive ladder", [g(T2, 34.0)]),
    (r"bottom rung", [g(T2, 152.3)]),
    (r"HVY Bulldozer", [code("HVY BULLDOZER", "LURDLRRD", "DISCOVER IT")]),
    (r"Interstate Ambulance", [title("INTERSTATE AMBULANCE", "DISCOVER IT · CODE TBC", L, 48.8)]),
    (r"MTL Pumper", [code("MTL PUMPER", "LURDLRRU", "UNLOCK STILL DEBATED", "CODE CONFIRMED")]),
    (r"five-challenge tier", [g(T2, 10.8)]),
    (r"Maibatsu Boomazoom", [code("MAIBATSU BOOMAZOOM", "LURDLLUL", "5 SHOPPING CHALLENGES")]),
    (r"Airboat Zero-Nine", [g(T2, 140.3)]),
    (r"Tuff BMX", [card("cards", "5 CHALLENGES EACH::TUFF BMX=Fitness|STANIER G2 TAXI=Sports")]),
    (r"Lapwing Mallard", [g(PL, 250.0), card("cards", "5 CHALLENGES EACH::LAPWING MALLARD=Vehicle|MAIBATSU SANCHEZ=Criminal")]),
    (r"Sea Sparrow", [g(L, 68.0), card("cards", "5 CHALLENGES EACH::SEA SPARROW=Exploration|SPEEDER 700 GT=Combat")]),
    (r"funniest collectible unlock", [g(DJ, 0.5)]),
    (r"cocaine-stuffed lawn flamingos", [title("50 COCAINE FLAMINGOS", "HIDDEN ACROSS LEONIDA", T2, 8.2)]),
    (r"destroy all fifty cocaine", [grind("INFLATABLE FLAMINGO", "50", "FLAMINGOS DESTROYED")]),
    (r"climb to the top rung", [g(T2, 34.0)]),
    (r"Bravado Banshee", [card("cards", "ONE FULL CATEGORY::BRAVADO BANSHEE=All combat|VAPID DOMINATOR '65=All fitness")]),
    (r"Progen Emerus", [card("cards", "ONE FULL CATEGORY::PROGEN EMERUS=All vehicle|TRUFFADE THRAX=All shopping")]),
    (r"Nagasaki Carbon RS", [card("cards", "ONE FULL CATEGORY::NAGASAKI CARBON RS=All exploration|BRIMSTONE GOLFER=All sports|"
                                           "ZOMBIE BOBBER=All criminal")]),
    (r"Rhino Tank\? You must", [title("HAUNERS RHINO TANK", "EVERY SURVIVAL CHALLENGE", T2, 144.3)]),
    (r"P-996 Lazer fighter jet", [g(PL, 280.0)]),
    (r"spawn that jet on command", [card("grid", "P-996 LAZER::61|0||EVERY CHALLENGE IN THE GAME")]),
    (r"Not just one category", [title("ALL OF THEM", "EVERY CHALLENGE · EVERY CATEGORY", PL, 300.0)]),
    (r"sixteen bizarre screen filters", [filt("DARK MIRROR", "dark", "coming up")]),
    # ---- act 6: environment + filters
    (r"Cycle Weather", [code("CYCLE WEATHER", "DRUDRUR", "ENVIRONMENT CHEAT")]),
    (r"Move Time Forward", [grind("MOVE TIME FORWARD", "10", "HIDDEN WATCHES FOUND")]),
    (r"Pause Time of Day", [grind("PAUSE TIME OF DAY", "20", "HIDDEN WATCHES FOUND")]),
    (r"most unexpected addition", [card("grid", "SCREEN FILTERS::16|3|CODES CONFIRMED|STILL TBC")]),
    (r"Instagram tints", [filt("BUBBLEGUM", "bubblegum", "a taste of what is coming")]),
    (r"unlock Dark Mirror", [grind("DARK MIRROR", "$500,000", "EARNED SELLING VEHICLES")]),
    (r"flips completely upside down", [filt("DARK MIRROR", "dark", "$500,000 selling vehicles")]),
    (r"Ocean Beach", [g(L, 46.8)]),
    (r"look at Migraine", [filt("MIGRAINE", "migraine", "six minutes at six stars")]),
    (r"How do you unlock Migraine", [grind("MIGRAINE", "6:00", "MINUTES AT SIX STARS")]),
    (r"officially back in GTA Six", [card("stars", "upto=6")]),
    (r"Golden Hour widescreen", [filt("GOLDEN HOUR", "golden", "4 hours holding hands")]),
    (r"Dollhouse filter", [filt("DOLLHOUSE", "dollhouse", "8 hours with your partner")]),
    (r"Dollhouse already", [code("DOLLHOUSE", "DDURRULLDR", "8 HOURS WITH YOUR PARTNER")]),
    (r"Faded Glory", [code("FADED GLORY", "DDURRULLLR", "ROB 50 STORES WITH YOUR PARTNER")]),
    (r"Cataclysm", [code("CATACLYSM", "DDURRULLRR", "DISCOVER MARTHA'S VAMOS")]),
    (r"other ten filters", [g(L, 60.8)]),
    (r"Powdered Sugar", [filt("POWDERED SUGAR", "powdered", "scan all space debris with WAiNK")]),
    (r"Bubblegum, bathing", [filt("BUBBLEGUM", "bubblegum", "all 24 Vice City Flamingos cards")]),
    (r"Hellscape", [filt("HELLSCAPE", "hellscape", "steal 100 police cars"), filt("FISHEYE", "fisheye", "catch 100 fish")]),
    (r"Pixel Art", [filt("PIXEL ART", "pixel", "$250,000 selling collectibles")]),
    (r"Videotape", [filt("VIDEOTAPE", "videotape", "50 partner activities"), filt("PINHOLE", "pinhole", "25 gang ops"),
                    filt("NEON JUNGLE", "neon", "all 16 Girlypop vehicles"), filt("YESTERYEAR", "yesteryear", "discover the Ridgway")]),
    (r"marked .TBC", [card("grid", "LAUNCH DAY::61|17|CONFIRMED|MARKED TBC")]),
    # ---- act 7: the prefix pattern
    (r"something weird", [g(T2, 38.3)]),
    (r"prefix-based family tree", [title("NOT RANDOM", "A PREFIX FAMILY TREE", T1, 39.85)]),
    (r"three shooting-range cheats", [card("prefix", AMMO)]),
    (r"exact same seven arrows", [code("THE AMMO PREFIX", "DURDLLU???", "SHARED BY ALL THREE", "7 SHARED ARROWS", "7")]),
    (r"final three arrows", [g(T2, 106.3)]),
    (r"physics combat cheats", [card("prefix", PHYS)]),
    (r"exact same six arrows", [code("THE PHYSICS PREFIX", "DULLRD???", "SHARED BY ALL THREE", "6 SHARED ARROWS", "6")]),
    (r"three confirmed vehicle spawns", [card("prefix", VEHS)]),
    (r"opens with Left, Up", [code("THE VEHICLE PREFIX", "LURDL???", "SHARED BY ALL THREE", "5 SHARED ARROWS", "5")]),
    (r"three confirmed Screen Filters", [card("prefix", FILT)]),
    (r"exact same eight arrows", [code("THE FILTER PREFIX", "DDURRULL??", "SHARED BY ALL THREE", "8 SHARED ARROWS", "8")]),
    (r"last two arrows tell", [g(L, 60.8)]),
    (r"logical command language", [card("stats", "A CODE LANGUAGE::PREFIX=picks the category|SUFFIX=picks the cheat")]),
    (r"brute-forced", [code("DARK MIRROR", "DDURRULL??", "GUESSING THE LAST TWO", "STILL LOCKED", "8")]),
    (r"checks your Progress file", [card("checklist", "THE ENGINE CHECKS FIRST/IS THE CHALLENGE DONE?::CODE ENTERED|"
                                                     "PROGRESS FILE CHECKED|CHALLENGE NOT DONE = CODE DEAD")]),
    (r"only seventeen codes are verified", [card("grid", "WHY ONLY 17::61|17|VERIFIED|WAITING ON THE GRIND")]),
    (r"seventy-two hours", [title("NEXT 72 HOURS", "44 CODES STILL TO DROP", L, 66.3)]),
    # ---- act 8: the plan
    (r"challenge progress counts", [card("checklist", "RULE 1/PROGRESS COUNTS DURING THE STORY::GYM WORKOUTS|"
                                                     "STORE ROBBERIES WITH YOUR PARTNER|SHOOTING-RANGE MEDALS")]),
    (r"banks progress", [g(T2, 114.3)]),
    (r"glowing pink cocaine flamingo", [title("RULE 2 · GRAB COLLECTIBLES", "FLAMINGOS AND WATCHES · ON SIGHT", T2, 8.2)]),
    (r"fifteen manual save slots", [title("RULE 3 · 15 SAVE SLOTS", "SAVE BEFORE EVERY CHEAT", T2, 46.8)]),
    (r"fresh manual save", [card("controller", "SAVE, THEN CHEAT::DPAD=SAVE FIRST|L1=HOLD L1|R1=TAP R1")]),
    (r"saving locks out", [card("lockout", "SAVING LOCKS OUT::RHINO TANK|DARK MIRROR|ANY CHEAT|reload the clean save afterwards")]),
    (r"Port Gellhorn", [card("cards", "PORT GELLHORN SAFES · CHAPTER 2::BROOKS BOATWORKS=6823|LA CASCARA MOTEL=6969|"
                                      "KINGPIN BOWLING=0300")]),
    (r"honest take", [g(L, 24.3)]),
    (r"genius move", [card("stats", "YOUR VERDICT::GENIUS=cheats as endgame rewards|RUINED=classic sandbox chaos")]),
    (r"grinding for first", [g(L, 66.3)]),
]

POOLS = [
    [(L, 26.8), (T2, 28.3), (T1, 12.8), (L, 46.8)],
    [(T2, 74.3), (L, 12.3), (T2, 20.3), (L, 40.3)],
    [(T2, 114.3), (BK, 4.0), (T2, 64.3), (L, 60.8)],
    [(T2, 84.3), (T2, 144.3), (CC, 0.5), (T2, 106.3)],
    [(T2, 152.3), (PL, 194.0), (SH, 2.0), (T2, 148.3), (L, 48.3)],
    [(L, 60.8), (T1, 12.8), (T2, 90.3), (L, 26.3)],
    [(T1, 39.85), (T2, 38.3), (L, 66.3)],
    [(L, 40.3), (T2, 8.2), (L, 4.3), (T2, 74.3)],
]


def build():
    lines, used, act, pool_i, seen = [], set(), 0, [0] * len(POOLS), []
    for sent in [x.strip() for x in (ROOT / "cheats_script.txt").read_text(encoding="utf-8").splitlines() if x.strip()]:
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
            if sh.get("game_clip") and sh.get("game_at") not in ("", None) and sh.get("shot") == "game":
                seen.append((sh["game_clip"], float(sh["game_at"])))
        lines.append((sent, shots))
    return lines


if __name__ == "__main__":
    out = ROOT / "gta6_cheats_scenes.csv"
    lines = build()
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        for t, shots in lines:
            for i, s in enumerate(shots):
                w.writerow({"narration": t if i == 0 else "", **{k: s.get(k, "") for k in COLS[1:]}})
    unused = [p for k, (p, _s) in enumerate(RULES) if not any(re.search(p, t) for t, _ in lines)]
    print(out, len(lines), "lines; rules never matched:", unused)
