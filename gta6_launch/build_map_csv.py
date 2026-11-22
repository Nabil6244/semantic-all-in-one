"""Writes gta6_map_scenes.csv: 'What's Hiding Under the GTA 6 Map' (Game Launch style, the user's own voiceover).

map_script.txt is the pasted script split into sentences. A chapter card opens each region (Keys, Grassrivers, Port Gellhorn
and Ambrosia, Kalaga, Vice City) so each one becomes a Short. The fog-of-war route map opens and closes the video.
Every number on screen comes from the script; guesses are labelled MY GUESS, preview reports PREVIEWS."""
import csv
import re
from pathlib import Path

from build_cartheft_csv import hud
from build_confirmed_csv import (AMBR, GRASS, KALAGA, KEYS, L, PORT, ST, T1, T2, VICE, chap, dossier, g, mp, split, storms,
                                 timeline, title)
from build_launchnight_csv import COLS

ROOT = Path(__file__).resolve().parent
PL, BK, SH, CC, DJ, PC = ("gta6_plane_steal.mp4", "gta6_bike_night_crash.mp4", "gta6_shark_attack.mp4", "gta6_car_cat_attack.mp4",
                          "gta6_dog_jetski.mp4", "gta6_pet_cat.mp4")
BASE = "Military Base=far end of the Keys@24.56,-81.78"
SILVER = "Silver Springs=real monkey home@29.21,-82.05"
STOP = {"keys": "Leonida Keys@24.72,-81.1", "grass": "Grassrivers@25.55,-80.95", "vice": "Vice City@25.77,-80.19",
        "ambr": "Ambrosia@26.75,-80.93", "kal": "Mount Kalaga@29.9,-82.2", "port": "Port Gellhorn@30.16,-85.66"}


def route(head, *keys):
    return {"shot": "route", "title": head, "place": " > ".join(STOP[k] for k in keys)}


def steps(head, items, clip=T2, at=144.3):
    return {"shot": "steps", "title": head, "subtitle": items, "game_clip": clip, "game_at": at}


RULES = [  # (pattern, shots): first unused match wins
    # ---- cold open
    (r"^Tonight you open the GTA 6 map", [route("UNDER THE BLACK", "keys", "grass", "vice")]),
    (r"^That is not a glitch", [title("NOT A GLITCH", "FOG OF WAR  ·  UNEXPLORED = HIDDEN", L, 46.4)]),
    (r"twice the size of the GTA 5 map", [hud("stats", "UNDER THE DARKNESS::~2x=the GTA V map")]),
    (r"military base Rockstar has never shown", [title("1 SECRET BASE", "NEVER SHOWN IN A TRAILER", T2, 82.3)]),
    (r"one cheap shirt", [hud("stars", "upto=4")]),
    (r"Six regions, one secret base", [hud("checklist", "TONIGHT/UNDER THE BLACK::6 REGIONS|1 SECRET BASE|REAL MONKEYS|"
                                                        "THE NEW POLICE SYSTEM|MY NIGHT-ONE ROUTE")]),
    (r"^One quick rule before we start", [hud("cards", "THREE LABELS::CONFIRMED=Rockstar said it|PREVIEWS=People who played "
                                                        "preview builds|MY GUESS=I say so out loud")]),
    (r"one pattern jumped out", [g(T1, 36.8)]),
    # ---- size
    (r"^First, the size", [chap("THE SIZE", "Bigger than anything Rockstar has built", T1, 10.3)]),
    (r"Aaron Garbut told Game Informer", [hud("quote", "ROCKSTAR NORTH::The biggest map the studio has ever built|"
                                                       "Aaron Garbut|Game Informer")]),
    (r"Rockstar gave Edge a different comparison", [hud("cards", "TWO COMPARISONS::GAME INFORMER=About double GTA V|"
                                                                 "EDGE=GTA IV + GTA V + RDR2 combined")]),
    (r"never published a number in kilometers", [title("NO OFFICIAL KM", "ANY EXACT NUMBER = FAN ESTIMATE", T1, 20.3)]),
    (r"full in-game day lasts much longer", [hud("checklist", "EDGE/WHY IT FEELS PACKED::A LONGER IN-GAME DAY THAN GTA V|"
                                                             "NARROWER ROADS")]),
    (r"not enough time to walk you through", [g(T1, 18.8)]),
    (r"parts of that map will stay black", [route("STORY ONLY = STILL BLACK", "keys", "vice")]),
    (r"^So let us light it up", [mp("all")]),
    # ---- Keys
    (r"^The Leonida Keys, Rockstar's version", [chap("LEONIDA KEYS", "Region 1  ·  the rule: money", T2, 6.1),
                                                 split(T1, 35.75, ST + "pexels_33959669.mp4", 3.0, "LEONIDA KEYS", "FLORIDA KEYS")]),
    (r"where Jason's story begins", [mp(KEYS, T2, 6.6)]),
    (r"^It belongs to Brian Heder", [dossier("Brian Heder", "Old-school smuggler", "Runs a boat yard with his third wife, Lori. "
                                                                                  "Jason stays free for local work.", T2, 8.2)]),
    (r"most Florida rental deal", [g(T2, 90.3)]),
    (r"^Now the part the trailers skipped", [title("THE SECRET BASE", "PREVIEWS  ·  NOT SHOWN YET", T2, 82.3)]),
    (r"military base at the far end of the Keys", [mp(BASE)]),
    (r"Remember Fort Zancudo", [title("FORT ZANCUDO", "GTA V  ·  EVERYONE TRIED TO BREAK IN", T1, 60.3)]),
    (r"steering my first car", [g(BK, 4.0)]),
    (r"more than 170 animal species", [hud("stats", "GAME INFORMER::170+=animal species|3=land, sea and sky")]),
    (r"^Flamingos, manatees", [hud("cards", "LEONIDA WILDLIFE::NATIVE=Flamingos · manatees · pelicans · alligators|"
                                            "INVASIVE=Green iguanas · cane toads · rhesus monkeys")]),
    (r"^Hold on to those monkeys", [title("THE MONKEYS", "WE'RE COMING BACK TO THEM", DJ, 2.0)]),
    (r"^The rule of the Keys is money", [title("RULE 1: MONEY", "LEONIDA KEYS", T2, 46.8)]),
    (r"cash you carry disappears", [hud("checklist", "PREVIEWS/YOUR POCKET CASH::LOST IF YOU DIE|LOST IF YOU GET ARRESTED|"
                                                     "DEPOSIT AT AN ATM|NOT THROUGH YOUR PHONE")]),
    (r"^Lesson one, find an ATM", [g(T2, 46.8)]),
    # ---- Grassrivers
    (r"^Now head northwest", [route("HEAD NORTHWEST", "keys", "grass")]),
    (r"^This is Grassrivers", [chap("GRASSRIVERS", "Region 2  ·  the rule: movement", T1, 19.25),
                               split(T1, 20.0, ST + "pexels_34338326.mp4", 10.0, "GRASSRIVERS", "EVERGLADES")]),
    (r"deadlier predators and stranger discoveries", [hud("quote", "ROCKSTAR::Deadlier predators and stranger discoveries "
                                                                   "wait deep in the mangroves|Official region description|rockstargames.com")]),
    (r"^Which predators", [split(T1, 41.35, ST + "pexels_11841042.mp4", 0.0, "LEONIDA GATOR", "EVERGLADES GATOR")]),
    (r"^My guess is Burmese pythons", [title("MY GUESS", "BURMESE PYTHONS", T1, 20.3)]),
    (r"invasive species that eats birds", [hud("cards", "REAL EVERGLADES::BURMESE PYTHON=Invasive|EATS=Birds, mammals, "
                                                         "even alligators")]),
    (r"nothing confirms it", [g(T1, 20.8)]),
    (r"^The rule here is how you move", [title("RULE 2: MOVEMENT", "GRASSRIVERS", T1, 41.0)]),
    (r"airboat glides over grass", [hud("cards", "AIRBOAT vs BOAT::AIRBOAT=Glides over the grass|BOAT=Gets stuck")]),
    (r"if you cannot see the bottom", [hud("checklist", "ON FOOT::CAN'T SEE THE BOTTOM? DON'T STEP IN")]),
    (r"boats react to the waves", [g(SH, 4.0), g(DJ, 6.0)]),
    # ---- crime money
    (r"^Quick step back", [route("2 DOWN · 4 TO GO", "keys", "grass", "port")]),
    (r"The next two run on crime money", [title("CRIME MONEY", "THE NEXT TWO REGIONS", T2, 84.3)]),
    (r"^Follow the Gulf coast north", [chap("PORT GELLHORN + AMBROSIA", "Regions 3 and 4  ·  the rule: crime pay", T2, 125.8),
                                        mp(PORT, T1, 72.85)]),
    (r"forgotten coast of Leonida", [hud("quote", "ROCKSTAR::The forgotten coast of Leonida|Port Gellhorn|rockstargames.com"),
                                      split(T2, 126.8, ST + "pexels_31040643.mp4", 5.0, "PORT GELLHORN", "PANHANDLE BEACH TOWN")]),
    (r"^Inland sits Ambrosia", [mp(AMBR, T1, 70.3)]),
    (r"Allied Crystal Sugar refinery", [split(T1, 59.55, ST + "px_sugar_factory_smokestacks.mp4", 2.0, "AMBROSIA", "SUGAR COUNTRY"),
                                        title("THE BIKERS", "PROVIDE ALMOST EVERYTHING ELSE", L, 18.0)]),
    (r"^The rule here is how you get paid", [title("RULE 3: CRIME PAY", "PORT GELLHORN + AMBROSIA", T2, 106.3)]),
    (r"gang stashes you can rob", [steps("PREVIEWS · HOW THE LOOT BECOMES MONEY", "Rob a marked gang stash; Sell stolen goods "
                                         "to a fence; Pawn shops buy too; Marked bank cash needs a special buyer", T2, 106.3)]),
    (r"an app called WAINK", [hud("checklist", "WAINK/BEFORE YOU STEAL A CAR::WHAT THE FENCES WANT|HOW WELL IT'S PROTECTED|"
                                                "WHETHER IT HAS A TRACKER")]),
    (r"wrecked and you get paid less", [g(CC, 29.0)]),
    # ---- Kalaga
    (r"hiding at the top of the map", [route("THE TOP OF THE MAP", "vice", "ambr", "kal")]),
    (r"^Mount Kalaga National Park", [chap("MOUNT KALAGA", "Region 5  ·  the rule: hunting", T1, 55.05),
                                      split(T1, 52.25, ST + "pexels_31149971.mp4", 3.0, "MOUNT KALAGA", "NORTH FLORIDA WILDS")]),
    (r"ranked common, discoverable or legendary", [hud("cards", "GAME INFORMER · TRACKED ANIMALS::COMMON=Everywhere|"
                                                                "DISCOVERABLE=Go looking|LEGENDARY=Unnamed so far")]),
    (r"^Panthers\?", [title("PANTHERS?", "MY GUESS  ·  UNCONFIRMED", T1, 54.3)]),
    (r"state animal since 1982", [hud("stats", "THE FLORIDA PANTHER::1982=made the state animal|1=vote by school students")]),
    (r"^And now the monkeys", [title("THE MONKEYS", "WHERE THEY REALLY LIVE", T1, 52.25)]),
    (r"rhesus macaques live around Silver Springs", [mp(SILVER)]),
    (r"^In 1938 a tour boat operator", [timeline("HOW FLORIDA GOT MONKEYS", ["1938=Colonel Tooey releases a few on an island",
                                                                             "SAME YEAR=His jungle cruise gets wilder",
                                                                             "ALMOST AT ONCE=They swim away"])]),
    (r"^So here is my theory", [title("MY THEORY", "NOT IN THE KEYS", T1, 70.3)]),
    (r"somewhere between Ambrosia and Kalaga", [route("WHERE I'LL LOOK FIRST", "ambr", "kal")]),
    # ---- Vice City
    (r"the part everyone came for, Vice City", [chap("VICE CITY", "Region 6  ·  the rule: the police", T1, 23.35),
                                                 mp(VICE, T1, 32.3)]),
    (r"everything to excess", [hud("quote", "ROCKSTAR::Everything to excess|Vice City|rockstargames.com")]),
    (r"^Ocean Beach has pastel", [split(L, 54.6, ST + "pexels_4135117.mp4", 2.0, "OCEAN BEACH", "MIAMI BEACH")]),
    (r"Little Cuba bakeries", [hud("cards", "IT'S MIAMI::LITTLE CUBA=Panaderias keep their Spanish name|"
                                            "THE PORT=Cruise ship capital of the world")]),
    (r"^Turn on the radio", [hud("cards", "LATIN RADIO::BACHATA=|MERENGUE=|DEMBOW=|REGGAETON=")]),
    (r"twice the size of Los Santos", [hud("stats", "PREVIEWS · VICE CITY::2x=Los Santos|ALMOST=anything can be robbed")]),
    (r"it was a headphone store", [g(PC, 2.0)]),
    (r"the big rule of Vice City, the police", [title("RULE 4: THE POLICE", "VICE CITY", T1, 44.3)]),
    (r"only know about a crime if someone sees it", [hud("cards", "HOW COPS FIND OUT::A WITNESS=Someone sees it|"
                                                                  "AN ALARM=Something goes off")]),
    (r"someone always sees", [g(T1, 18.8)]),
    (r"build a description of you", [hud("heat", "icons=face,outfit,weapon,vehicle,partner,camera off=")]),
    (r"^Your face, your clothes", [hud("heat", "icons=face,outfit,weapon,vehicle,partner,camera lit=face,outfit,weapon,vehicle,"
                                               "partner,camera")]),
    (r"^Change clothes, drop the gun", [hud("heat", "icons=face,outfit,weapon,vehicle,partner,camera lit=face,camera "
                                                    "off=outfit,weapon,vehicle,partner")]),
    (r"wearing a mask before a job", [hud("heat", "icons=face,outfit,weapon,vehicle,partner,camera lit=outfit off=face")]),
    (r"carry trackers that tell the police", [hud("checklist", "EDGE/EXPENSIVE CARS::SOME NEWER MODELS CARRY TRACKERS|"
                                                              "THE POLICE KNOW WHERE YOU ARE")]),
    (r"^Getting around, you will not need the map", [g(BK, 14.0)]),
    (r"a ride app called Ride Me", [hud("cards", "GETTING AROUND::NO MENU=Set a destination on the go|RIDE ME=Fast travel app")]),
    (r"^Buses and trains actually run", [g(L, 24.3)]),
    (r"buses really reach their stops", [hud("quote", "ROCKSTAR DEVELOPER::He checked that buses really reach their stops on time|"
                                                      "Rockstar developer|Edge")]),
    (r"Scooter Bros will deliver", [hud("cards", "SCOOTER BROS::DELIVERS YOUR CAR=For a fee|THE DRIVER=Leaves on a scooter")]),
    (r"room for only three cars", [hud("garage", "PREVIEWS · YOUR START::3|Your first car|Your second car|Your third car|"
                                                 "One more")]),
    # ---- sky + interiors
    (r"^One last thing to watch is the sky", [g(T2, 40.3)]),
    (r"tropical storms and hurricanes", [storms("REAL FLORIDA HURRICANES", ["AL041992", "AL142018", "AL092022"])]),
    (r"order of magnitude more interiors", [hud("stats", "AARON GARBUT · EDGE::10x=more interiors|MORE=doors you can open")]),
    (r"wind, humidity, fog", [hud("checklist", "EDGE/WHAT SHAPES THE WEATHER::WIND|HUMIDITY|FOG|TIME OF DAY|THE SEASON")]),
    (r"^After rain, the roads", [g(BK, 24.0)]),
    (r"small planes get tossed", [g(PL, 280.0)]),
    (r"flying straight into a hurricane", [title("ON MY LIST", "FLY INTO A HURRICANE", PL, 300.0)]),
    # ---- night one + outro
    (r"^Here is my route for night one", [chap("MY NIGHT-ONE ROUTE", "Based on everything above", T2, 154.3),
                                          route("NIGHT ONE", "keys", "vice", "ambr", "kal")]),
    (r"^Start in the Keys", [steps("MY NIGHT-ONE ROUTE", "Finish the first missions in the Keys; Deposit your cash at a bank; "
                                   "Buy a mask and a spare outfit; Bus or train into Vice City; Head north while the map is black",
                                   T2, 6.6)]),
    (r"keep the clothes in your trunk", [g(L, 46.8)]),
    (r"save your three garage slots", [hud("garage", "SAVE THE SLOTS::3|Worth keeping|Worth keeping|Worth keeping|Junk")]),
    (r"away from the mission path", [route("OFF THE MISSION PATH", "vice", "ambr", "kal", "port")]),
    (r"^That is Leonida", [mp("all")]),
    (r"Every region changes one rule", [hud("cards", "ONE RULE PER REGION::KEYS=Money|GRASSRIVERS=Movement|"
                                                     "PORT GELLHORN + AMBROSIA=Crime pay|KALAGA=Hunting|VICE CITY=The police")]),
    (r"GTA 6 is out today", [title("OUT TODAY", "GTA VI  ·  NOV 19", T2, 154.3)]),
    (r"see you behind the bridges", [g(T1, 35.75)]),
]

POOLS = [  # fallback trailer shots per chapter (0 = intro)
    [(L, 6.3), (T1, 36.3), (T2, 114.3), (L, 26.3)],
    [(T1, 10.3), (T1, 22.3), (L, 60.3)],                     # size
    [(T2, 8.2), (T2, 6.6), (L, 4.3), (T2, 90.3)],             # Keys
    [(T1, 20.3), (T1, 41.35), (SH, 38.0)],                    # Grassrivers
    [(T2, 126.8), (T1, 72.85), (T1, 59.55), (L, 18.0)],       # Port + Ambrosia
    [(T1, 52.25), (T1, 54.3), (T1, 55.05)],                   # Kalaga
    [(T1, 27.45), (T2, 35.5), (T1, 24.3), (L, 54.6), (T1, 30.05)],   # Vice
    [(T2, 154.3), (L, 66.3), (T1, 12.8)],                     # night one
]


def sentences(script="map_script.txt"):
    text = re.sub(r"\s+", " ", (ROOT / script).read_text(encoding="utf-8")).strip()
    return [s for s in re.split(r"(?<=[.!?])\s+(?=[A-Z\"$])", text) if s.strip()]


def build(script="map_script.txt", rules=None, pools=None):
    RULES, POOLS = rules or globals()["RULES"], pools or globals()["POOLS"]
    lines, used, act, pool_i, seen = [], set(), 0, [0] * len(POOLS), []
    for sent in sentences(script):
        shots = []
        for k, (pat, sh) in enumerate(RULES):
            if k not in used and re.search(pat, sent):
                used.add(k)
                shots = [dict(x) for x in sh]
                break
        if any(s.get("shot") == "chapter" for s in shots):
            act = min(act + 1, len(POOLS) - 1)
        if not shots:
            pool = POOLS[act]
            clip, at = pool[pool_i[act] % len(pool)]
            pool_i[act] += 1
            shots.append(g(clip, round(at + 0.4 * (pool_i[act] // len(pool)), 1)))
        for sh in shots:
            if sh.get("shot") == "game":
                tries = 0
                while tries < 14 and any(c == sh["game_clip"] and abs(a - float(sh["game_at"])) < 1.6 for c, a in seen):
                    tries += 1
                    sh["game_at"] = round(float(sh["game_at"]) + 1.7, 1)
                seen.append((sh["game_clip"], float(sh["game_at"])))
        lines.append((sent, shots))
    return lines


def write(out, lines, rules):
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        for t, shots in lines:
            for i, s in enumerate(shots):
                w.writerow({"narration": t if i == 0 else "", **{k: s.get(k, "") for k in COLS[1:]}})
    unused = [p for k, (p, _s) in enumerate(rules) if not any(re.search(p, t) for t, _ in lines)]
    print(out, len(lines), "lines; rules never matched:", unused)


if __name__ == "__main__":
    out = ROOT / "gta6_map_scenes.csv"
    lines = build()
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        for t, shots in lines:
            for i, s in enumerate(shots):
                w.writerow({"narration": t if i == 0 else "", **{k: s.get(k, "") for k in COLS[1:]}})
    unused = [p for k, (p, _s) in enumerate(RULES) if not any(re.search(p, t) for t, _ in lines)]
    print(out, len(lines), "lines; rules never matched:", unused)
