"""Writes gta6_mistakes_scenes.csv: '5 Biggest Mistakes in Your First Hour of GTA 6' (Game Launch style).

The script (mistakes_script.txt) is split into sentences, one voice line each. Each sentence is matched to its picture by the
rules below (first matching rule wins, each rule used once); a sentence no rule claims gets the next trailer shot from its
chapter's pool, so shots stay on topic and rarely repeat. Long sentences get a second shot. Nothing from the visual guide's
sources is written on screen."""
import csv
import re
from pathlib import Path

from build_cartheft_csv import hud, tracker, vs
from build_confirmed_csv import L, ST, T1, T2, chap, dossier, g, mp, split, title

ROOT = Path(__file__).resolve().parent
KEYLANTO = "Key Lanto@24.70,-81.09"
OCEAN = "Ocean Beach=Miami Beach@25.79,-80.13"
VICE = "Vice City=Miami@25.77,-80.19"
GRASS = "Grassrivers=Everglades@25.55,-80.95"
WATSON = "Watson Bay@25.86,-81.38"
PORT = "Port Gellhorn=Panhandle@30.16,-85.66"
AMBR = "Ambrosia=Lake Okeechobee Area@26.75,-80.93"
HEAT5 = "icons=camera,build,weapon,vehicle,outfit"


def route(head, *stops):
    return {"shot": "route", "title": head, "place": " > ".join(stops)}


def real(f, at=0.0):
    return {"shot": "real", "real": f, "real_at": at}


CHAPTERS = [  # sentence start -> chapter card
    (r"^Let's start with the very first thing", "STEALING THE WRONG CAR", "Mistake 1"),
    (r"^Which brings us to Mistake Number Two", "LOSING THE COPS THE OLD WAY", "Mistake 2"),
    (r"^Mistake Number Three is", "THE FIRST-HOUR RAMPAGE", "Mistake 3"),
    (r"^Mistake Number Four is", "GTA 5 MONEY HABITS", "Mistake 4"),
    (r"^So if rushing into Downtown Vice City", "THE SMART FIRST-HOUR ROUTE", "Where to go instead"),
]
CHAP_CLIPS = [(T1, 52.3), (L, 70.3), (T2, 8.2), (T2, 92.3), (T1, 20.3)]

RULES = [  # (pattern, shots) - first match wins, each used once
    (r"It is almost here", [title("GTA VI", "IT IS ALMOST HERE", T2, 154.3)]),
    (r"unlocks at midnight", [title("MIDNIGHT", "NOVEMBER 19", L, 60.3)]),
    (r"two hundred and twelve gigabytes", [title("212 GB", "PRELOAD  ·  KEEP 250 GB FREE", L, 0.6)]),
    (r"neon strip of Ocean Beach", [split(L, 54.6, ST + "pexels_4135117.mp4", 2.0, "OCEAN BEACH", "MIAMI BEACH"),
                                    vs(L, 46.3, "gta5_carjack.mp4", 0.0)]),
    (r"within four minutes", [g(T1, 66.3), g(L, 68.0)]),
    (r"Rob Nelson", [title("THE WORLD NO LONGER FORGETS", "WHAT YOU DID", T2, 106.3)]),
    (r"From high-end supercars that secretly ping", [g(L, 46.8), hud("heat", HEAT5), mp(KEYLANTO, T1, 8.3)]),
    (r"one-button hotwire is officially dead", [title("THE ONE-BUTTON HOTWIRE", "IS DEAD", L, 38.3)]),
    (r"million-dollar hypercar took one button", [vs(L, 47.0, "gta5_carjack.mp4", 4.0)]),
    (r"tiered security puzzle", [hud("tiers", "focus=both")]),
    (r"trip the vehicle alarm", [g(T2, 152.8)]),
    (r"key cloner", [hud("tiers", "focus=3")]),
    (r"actually fight back", [g(T1, 30.3), g(T2, 114.3)]),
    (r"passenger literally threw", [g(T1, 56.3), g(L, 40.3), g(T1, 44.3)]),
    (r"slowing down can get you arrested", [g(L, 48.3), g(T2, 34.3)]),
    (r"built-in GPS trackers", [g(L, 38.3), g(L, 70.6)]),
    (r"start beeping the moment your speed drops", [tracker("THE SILENT TRACKER")]),
    (r"open the WAINK scanning app", [g(L, 12.3), hud("waink", "", L, 46.3)]),
    (r"four critical stats", [hud("waink", "", T2, 152.3)]),
    (r"slim jim", [hud("tiers", "focus=1")]),
    (r"feather the throttle", [g(T1, 70.3), g(T1, 2.3)]),
    (r"walking straight into an ambush", [g(T2, 106.8), g(L, 70.3)]),
    (r"cones or dots on your minimap", [hud("minimap", "gta5")]),
    (r"red-and-blue directional flash", [hud("minimap", "gta6", L, 70.3), hud("focus", "", L, 70.3)]),
    (r"Heat memory layer directly underneath", [hud("heat", HEAT5 + " lit=none")]),
    (r"four distinct color states", [title("THE WANTED STARS", "FOUR STATES", T2, 148.3)]),
    (r"^Hollow stars", [hud("stars", "upto=1")]),
    (r"^Solid white stars", [hud("stars", "upto=2")]),
    (r"^Flashing white stars", [hud("stars", "upto=3")]),
    (r"^And red stars", [hud("stars", "upto=4")]),
    (r"individual evidence icons", [hud("heat", HEAT5)]),
    (r"torch your getaway car", [g(L, 52.8), hud("heat", HEAT5 + " off=vehicle")]),
    (r"clothing icon is still active", [g(T2, 116.3), g(T1, 33.0)]),
    (r"spare outfit inside the trunk", [hud("heat", HEAT5 + " off=vehicle,outfit"), g(T2, 86.3)]),
    (r"split Jason and Lucia up", [g(L, 40.8), g(T2, 98.3), hud("heat", HEAT5 + " off=vehicle,outfit,weapon")]),
    (r"police roadblock", [g(T1, 24.3), g(L, 70.8)]),
    (r"impound lot", [g(T2, 108.8), g(T2, 120.3)]),
    (r"unrestricted rampage", [g(L, 72.3), g(L, 52.3)]),
    (r"not living in a penthouse", [g(T1, 18.3), g(L, 66.3)]),
    (r"stilt house on the water in Key Lanto", [mp(KEYLANTO, T2, 8.2),
                                               dossier("Brian Heder", "Keys drug runner", "Jason does his jobs to pay the rent.", T2, 14.3)]),
    (r"ankle monitor", [title("ANKLE MONITOR", "LUCIA'S EARLY LIMITS", T1, 8.3), mp(VICE, L, 60.3)]),
    (r"aren't just dealing with beat cops", [g(T2, 108.3)]),
    (r"seven distinct law enforcement", [hud("agencies"), split(L, 70.0, ST + "pexels_32538553.mp4", 3.0,
                                                                "LEONIDA POLICE", "FLORIDA POLICE")]),
    (r"separate Criminal Profile", [hud("profile", "level=0")]),
    (r"Honor bar", [title("NOT AN HONOR BAR", "THE WORLD REACTS TO YOU", T1, 22.3)]),
    (r"permanent Shattered state", [hud("profile", "level=4")]),
    (r"keep long guns stored", [hud("carry"), g(L, 64.8)]),
    (r"crime-free hubs", [g(T2, 126.3), g(T2, 100.3), hud("focus", "", L, 72.3)]),
    (r"go broke in their first two hours", [g(T2, 92.3)]),
    (r"fifty million dollars in your pocket", [title("GTA V", "$50,000,000 IN YOUR POCKET", T2, 46.3)]),
    (r"Wi-Fi cash deposits", [title("PHONE DEPOSITS", "REMOVED", T2, 46.8)]),
    (r"three strict buckets", [hud("economy")]),
    (r"Bank Money in purple", [hud("economy", "focus=bank"), g(T2, 42.3)]),
    (r"Physical Cash on Hand", [hud("economy", "focus=cash"), g(T1, 68.3)]),
    (r"Third is Duffel Bag Value", [hud("economy", "focus=bag")]),
    (r"black-market fence", [g(T2, 130.3), g(L, 34.3)]),
    (r"do not blow the safe", [hud("safe", "focus=loud")]),
    (r"physically damages the loot", [g(L, 52.3), g(L, 34.8)]),
    (r"directly to the cloud", [title("CLOUD CCTV", "SHOOTING THE MONITOR WON'T SAVE YOU", T1, 47.8), g(T1, 49.5)]),
    (r"use a snap gun to pick", [hud("safe", "focus=quiet"), g(L, 6.3)]),
    (r"motorcycles hold zero duffel bags", [hud("capacity", "rows=motorcycle:0:zero-bags,car:2:in-the-trunk,van-or-pickup:4:three-to-five")]),
    (r"story progression in GTA Six is cash-gated", [title("STORY IS CASH-GATED", "BANK EVERY SCORE", T2, 130.8)]),
    (r"where should you actually go first", [mp("all")]),
    (r"Fog-of-War map system", [route("FOG OF WAR", KEYLANTO, GRASS, PORT)]),
    (r"Garate ES-Nine", [g(L, 64.3), g(L, 30.3), mp("all")]),
    (r"^Step one", [route("STEP 1  ·  INTO THE GRASSRIVERS", KEYLANTO, GRASS)]),
    (r"Brian's boatyard", [g(L, 4.3), g(T2, 6.3)]),
    (r"Atlantic side is deep water", [g(T1, 10.3), split(T1, 20.0, ST + "pexels_34338326.mp4", 10.0, "GRASSRIVERS", "EVERGLADES")]),
    (r"lawless Everglades wetland", [mp(GRASS, T1, 20.3)]),
    (r"grab an airboat", [split(T2, 138.2, ST + "pexels_11840880.mp4", 0.0, "AIRBOAT", "REAL AIRBOAT")]),
    (r"Watson Bay", [mp(WATSON, T2, 138.6), title("ULTIMATE EDITION", "PARADISE GARAGE  ·  1967 VAPID DOMINATOR", L, 18.3)]),
    (r"zero cloud-synced city cameras", [g(T1, 20.8), g(T2, 140.3), split(T1, 41.35, ST + "pexels_11841042.mp4", 0.0, "GRASSRIVERS", "EVERGLADES")]),
    (r"^Step two", [route("STEP 2  ·  WEST TO PORT GELLHORN", GRASS, PORT)]),
    (r"decaying resort town", [split(T2, 126.8, ST + "pexels_31040643.mp4", 5.0, "PORT GELLHORN", "PANAMA CITY BEACH"), g(T1, 72.85)]),
    (r"ultimate Hour One goldmine", [title("PORT GELLHORN", "THE FIRST-HOUR GOLDMINE", T1, 74.3)]),
    (r"Gellhorn International Raceway", [g(L, 48.8), g(T1, 70.8)]),
    (r"pool and darts", [g(T2, 90.3), g(T2, 92.8)]),
    (r"packed with gang strongholds", [mp(AMBR, T1, 70.3)]),
    (r"four-thousand-five-hundred-dollar", [title("$4,500", "DRUG FENCE PAYOUT IN THE PREVIEW", T2, 128.3)]),
    (r"Uncle Jack's Liquor", [g(T1, 76.3), g(T1, 68.8)]),
    (r"^Step three", [title("STEP 3", "BUY A STORAGE GARAGE", T2, 120.3)]),
    (r"Shorecourt Garage", [mp(OCEAN, L, 54.3)]),
    (r"cannot buy safe houses", [title("NO SAFE HOUSES FOR SALE", "ONLY GARAGES", T2, 88.3)]),
    (r"three personal vehicle slots", [title("3 VEHICLE SLOTS", "STOLEN CARS DESPAWN UNLESS PARKED", L, 46.3)]),
    (r"weapon locker and contraband", [title("YOUR GARAGE", "WEAPON LOCKER  ·  CONTRABAND STORAGE", L, 38.8)]),
    (r"before the clock strikes midnight", [hud("checklist", "Scan every car with WAINK|Keep a clean outfit in your trunk|"
                                                          "Bank your cash at an ATM after every job|"
                                                          "Start in the Grassrivers and Port Gellhorn")]),
    (r"Drop a comment", [title("WHERE ARE YOU GOING FIRST?", "OCEAN BEACH  ·  OR PORT GELLHORN", T2, 154.8)]),
    (r"Hit subscribe", [title("SUBSCRIBE", "DAY ONE FENCES + SAFE CODES NEXT", real=ST + "pexels_3770584.mp4", real_at=6.0)]),
]

POOLS = [  # fallback trailer shots per chapter (0 = intro)
    [(T1, 2.3), (T1, 12.3), (L, 26.3), (T1, 32.3), (T2, 152.3), (L, 60.8)],
    [(L, 46.3), (L, 40.3), (T2, 28.3), (T2, 30.3), (T1, 54.3), (L, 18.8), (T2, 46.3)],
    [(T1, 66.8), (L, 68.6), (T2, 106.3), (T1, 49.5), (T2, 116.8), (L, 71.0), (T1, 64.3)],
    [(T2, 18.3), (T2, 20.3), (T2, 24.3), (T2, 64.3), (T2, 66.3), (L, 64.3), (T2, 108.3)],
    [(T1, 68.3), (T2, 92.3), (T2, 132.3), (L, 34.3), (T2, 42.8), (L, 30.8)],
    [(T2, 6.6), (T2, 84.3), (T1, 20.3), (T2, 154.3), (T1, 72.3), (L, 4.8)],
]


def sentences(text: str):
    out = []
    for para in text.split("\n"):
        para = para.strip()
        if para:
            out += [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z])", para) if s.strip()]
    return out


def build():
    lines, used, chapter, pool_i = [], set(), 0, [0] * len(POOLS)
    for sent in sentences((ROOT / "mistakes_script.txt").read_text(encoding="utf-8")):
        shots = []
        for k, (pat, head, sub) in enumerate(CHAPTERS):
            if re.search(pat, sent):
                chapter = k + 1
                shots.append(chap(head, sub, *CHAP_CLIPS[k]))
        for k, (pat, sh) in enumerate(RULES):
            if k not in used and re.search(pat, sent):
                used.add(k)
                shots += [dict(x) for x in sh]
                break
        words = len(sent.split())
        need = 0 if shots and (words < 26 or len(shots) > 1) else (1 if (shots or words < 26) else 2)
        if not shots:
            need = max(need, 1)
        for _ in range(need):
            pool = POOLS[chapter]
            clip, at = pool[pool_i[chapter] % len(pool)]
            pool_i[chapter] += 1
            shots.append(g(clip, at + 0.4 * (pool_i[chapter] // len(pool))))
        lines.append((sent, shots))
    return lines


COLS = ["narration", "shot", "game_clip", "game_at", "real", "real_at", "left", "right", "title", "subtitle", "place"]

if __name__ == "__main__":
    out = ROOT / "gta6_mistakes_scenes.csv"
    lines = build()
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        for text, shots in lines:
            for i, s in enumerate(shots):
                w.writerow({"narration": text if i == 0 else "", **s})
    unused = [p for k, (p, _s) in enumerate(RULES) if not any(re.search(p, t) for t, _ in lines)]
    print(out, len(lines), "lines; rules never matched:", unused)
