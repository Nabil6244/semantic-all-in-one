"""Writes gta6_capri_scenes.csv: 'The Secret City Rockstar Hid in GTA 6' (Game Launch style).
One voice line per script line (capri_script.txt). Rules pick each line's picture (first match wins, each rule once); other
lines take the next shot of their chapter's pool. Map pins put Leonida's places on the real Florida map they copy (shown as
illustration). Real-life splits are labelled honestly when a stock clip is not the named place."""
import csv
import re
from pathlib import Path

from build_cartheft_csv import hud
from build_confirmed_csv import L, ST, T1, T2, chap, g, mp, split, title

ROOT = Path(__file__).resolve().parent
PX = "footage/stock/px_"

VICE = "Vice City=Miami@25.77,-80.19"
OCEAN = "Ocean Beach=Miami Beach@25.79,-80.13"
VCI = "VCI Airport=Miami International@25.80,-80.29"
CAPRI = "Capri=Naples@26.14,-81.79"
PORT = "Port Gellhorn=Panama City@30.16,-85.66"
AMBR = "Ambrosia=Clewiston@26.75,-80.93"
LAKE = "Lake Leonida=Lake Okeechobee@26.95,-80.83"
LUMMOX = "Lummox County=North Florida@30.30,-82.60"
SERA = "SERA=Cape Canaveral@28.39,-80.60"
KEYS = "Key Lento=Florida Keys@24.70,-81.09"
GRASS = "Grassrivers=Everglades@25.55,-80.95"
MARIANA = "Mariana County@25.98,-81.55"
SEBRING = "Circle Park=Sebring@27.50,-81.44"
LAKELAND = "Lake Mirror=Lakeland@28.04,-81.95"
STPETE = "Towers=St. Petersburg@27.77,-82.64"
AIRSTRIP = "Coastal airstrip@25.86,-81.45"


def route(head, *stops):
    return {"shot": "route", "title": head, "place": " > ".join(stops)}


def real(f, at=0.0):
    return {"shot": "real", "real": f, "real_at": at}


def rtitle(head, sub, f, at=2.0):
    return title(head, sub, real=f, real_at=at)


CHAPTERS = [
    (r"^Before we zoom in on that exact frame", "THE HIDDEN MAP", "Chapter 1", (T1, 36.3)),
    (r"^To understand how Rockstar hid an entire city", "SIX COUNTIES", "Chapter 2", (T2, 154.3)),
    (r"^But here is the critical question", "THE SECOND SKYLINE", "Chapter 3", (T2, 34.3)),
    (r"^Rockstar didn’t just build a carbon copy", "INSIDE CAPRI", "Chapter 4", (L, 54.3)),
    (r"^So why did Rockstar build an entire wealthy", "PROJECT AMERICAS", "Chapter 5", (T1, 2.3)),
]

RULES = [
    (r"^In every Grand Theft Auto game ever released", [title("THE SECRET CITY", "ROCKSTAR HID IN GTA 6", T1, 18.3)]),
    (r"desert town, and mountain pass", [rtitle("EVERY GTA BEFORE", "THE STORY SHOWED YOU EVERYTHING", PX + "desert_highway_aerial.mp4")]),
    (r"Grand Theft Auto V worked back in 2013", [rtitle("GTA V", "2013", PX + "mountain_road_aerial_california.mp4", 3.0)]),
    (r"Blaine County", [real(PX + "desert_highway_aerial.mp4", 8.0)]),
    (r"Mount Chiliad", [real(PX + "mountain_road_aerial_california.mp4", 9.0)]),
    (r"Sandy Shores", [real(PX + "trailer_park_desert.mp4", 2.0), real(PX + "small_town_main_street.mp4", 2.0)]),
    (r"biggest complaint", [rtitle("AN EMPTY NORTH", "GTA V'S BIGGEST COMPLAINT", PX + "small_town_main_street.mp4", 9.0)]),
    (r"Rockstar changed the rules", [title("48 HOURS TO GO", "NOVEMBER 19  ·  MIDNIGHT", L, 60.3)]),
    (r"dropped a bombshell", [g(T2, 152.3)]),
    (r"won’t even take you across the entire map", [title("THE STORY", "WON'T SHOW YOU THE WHOLE MAP", T1, 36.3)]),
    (r"never visited during a standard story", [mp("all")]),
    (r"turn off the GPS route", [g(T2, 34.3), g(L, 46.3)]),
    (r"saw this firsthand", [g(T2, 28.3)]),
    (r"fog of war", [route("FOG OF WAR", VICE, GRASS, CAPRI)]),
    (r"gator shacks", [g(T1, 20.3), g(T1, 42.0)]),
    (r"fourth major urban center", [hud("stats", "A FOURTH CITY::20=storey towers|1=beachfront pier|1=stadium")]),
    (r"hiding in plain sight", [g(T1, 60.3)]),
    (r"official website promoted", [g(T1, 12.3)]),
    (r"exactly six regions", [hud("cards", "THE OFFICIAL SIX::VICE CITY=East coast art deco and neon|LEONIDA KEYS=Island chain to the south|"
                                           "GRASSRIVERS=The Everglades swamp|MOUNT KALAGA=Northern forest park|"
                                           "PORT GELLHORN=Gulf coast town|AMBROSIA=Inland refinery town")]),
    (r"^First was Vice City", [mp(VICE, T1, 39.85)]),
    (r"^Second was the Leonida Keys", [split(T1, 35.75, ST + "pexels_33959669.mp4", 3.0, "LEONIDA KEYS", "FLORIDA KEYS")]),
    (r"^Third was the Grassrivers", [split(T1, 20.0, ST + "pexels_34338326.mp4", 10.0, "GRASSRIVERS", "EVERGLADES")]),
    (r"^Fourth was Mount Kalaga", [split(T1, 52.25, ST + "pexels_31149971.mp4", 3.0, "MOUNT KALAGA", "REAL WILDS")]),
    (r"only named two other urban", [g(T1, 72.85)]),
    (r"Port Gellhorn on the western Gulf coast and Ambrosia", [mp(PORT, T1, 74.3), mp(AMBR, T1, 70.3)]),
    (r"second-biggest city", [split(T2, 126.8, ST + "pexels_31040643.mp4", 5.0, "PORT GELLHORN", "PANAMA CITY BEACH")]),
    (r"twenty-five-year tradition", [title("A 25-YEAR TRADITION", "BROKEN", T2, 120.3)]),
    (r"folded paper map", [rtitle("A PAPER MAP", "IN EVERY GAME CASE SINCE GTA 3", PX + "map_unfolding.mp4")]),
    (r"there’s no map inside", [title("NO MAP INSIDE", "STANDARD PS5 + XBOX COPY", L, 0.6)]),
    (r"Lucia Bikini Girl", [g(T1, 38.3)]),
    (r"printable map", [title("PRINTABLE MAP", "HELD BACK UNTIL LAUNCH DAY", T1, 14.3)]),
    (r"four-hundred-dollar Goodtime State", [title("$400", "THE COLLECTOR'S BOX MAP", L, 40.3)]),
    (r"stop early leaks cold", [g(L, 34.3)]),
    (r"blew the lid off", [title("TWO LEAKS", "", T1, 66.3)]),
    (r"Version 16", [g(T2, 148.3), mp("all")]),
    (r"3,400 verified markers", [hud("stats", "COMMUNITY MAP V16::3,400+=verified markers")]),
    (r"Selfridges", [g(L, 44.3)]),
    (r"Instagram unboxing", [real(PX + "map_unfolding.mp4", 8.0)]),
    (r"six massive counties", [hud("cards", "SIX COUNTIES::VICE-DALE=Vice City and its islands|LUMMOX=Forest and Mount Kalaga|"
                                            "LEONARD=Around Lake Leonida|AMBROSIA=The refinery town|"
                                            "KELLY=Port Gellhorn|MARIANA=The secret one")]),
    (r"Aaron Garbut", [hud("stats", "HOW BIG::2×=Leonida vs GTA V's map|2×=Vice City vs Los Santos")]),
    (r"Vice City by itself", [mp(VICE, T2, 34.7)]),
    (r"walk up to a building door", [g(T2, 42.3)]),
    (r"hollow cardboard prop", [rtitle("GTA V", "MOSTLY HOLLOW BUILDINGS", PX + "small_town_main_street.mp4", 14.0)]),
    (r"700, enterable interiors", [hud("stats", "INSIDE LEONIDA::700+=enterable interiors|4×=random encounters vs RDR2")]),
    (r"four times the number of random", [g(T1, 26.3), g(T1, 44.3)]),
    (r"six distinct counties", [mp("all")]),
    (r"Vice-Dale County, the urban heart", [mp(VICE, T1, 18.3)]),
    (r"barrier islands across the bay", [mp(OCEAN, L, 54.6), split(L, 54.6, ST + "pexels_4135117.mp4", 2.0, "OCEAN BEACH", "MIAMI BEACH")]),
    (r"Sahara Arena", [g(T1, 28.3), g(T2, 126.3)]),
    (r"two-runway Vice City International", [mp(VCI, T2, 36.3), split(T2, 36.3, PX + "airport_runway_plane_landing.mp4", 2.0,
                                                                      "VICE CITY AIRPORT", "REAL AIRPORT")]),
    (r"Lummox County", [mp(LUMMOX, T1, 54.3)]),
    (r"rocket icon", [mp(SERA), rtitle("SPACE COAST", "A ROCKET ON THE MAP", PX + "rocket_launch.mp4", 3.0)]),
    (r"Leonard County and Ambrosia County", [mp(LAKE, T1, 70.3)]),
    (r"Emerald Springs", [g(T2, 82.3), g(T1, 32.3)]),
    (r"company town of Ambrosia", [split(T1, 59.55, ST + "pexels_40799964.mp4", 5.0, "AMBROSIA", "SUGAR COUNTRY")]),
    (r"Allied Crystal Sugar Refinery", [real(PX + "sugar_factory_smokestacks.mp4", 2.0), g(L, 18.0)]),
    (r"Pelican Valley", [mp(GRASS, T1, 20.3), mp(KEYS, T2, 6.3)]),
    (r"in Kelly County sits Port Gellhorn", [mp(PORT, T2, 125.8)]),
    (r"Panama City and Florida’s Forgotten Coast", [split(T2, 126.8, ST + "pexels_31040643.mp4", 12.0, "PORT GELLHORN", "PANAMA CITY BEACH")]),
    (r"Starlet Motel", [g(T1, 72.3), g(T1, 74.3)]),
    (r"second skyline of skyscrapers", [title("A SECOND SKYLINE?", "", T2, 34.3)]),
    (r"Take-Two’s lawyers", [g(T1, 66.3)]),
    (r"sixth and most secretive county", [mp(MARIANA, T2, 138.3)]),
    (r"empty bayou", [real(PX + "swamp_road_aerial.mp4", 3.0)]),
    (r"Saukko505", [g(T2, 34.8), g(T1, 24.3)]),
    (r"Capri City Centre\.", [rtitle("CAPRI  ·  CITY CENTRE", "THE ROAD SIGN", PX + "highway_overpass_sign.mp4", 2.0)]),
    (r"small neighborhood inside Port Gellhorn", [mp(PORT, T1, 72.85)]),
    (r"triangulated the camera angles", [mp(CAPRI, T2, 34.3)]),
    (r"hypercar slams into a truck", [g(L, 46.3), g(L, 48.3)]),
    (r"fifty-to-seventy-story skyscrapers", [g(T2, 34.7), g(T1, 18.8)]),
    (r"pans southwest behind the player", [g(T2, 154.3)]),
    (r"completely separate skyline", [title("15 – 20 STOREYS", "A SEPARATE SKYLINE ON THE GULF", T2, 154.8)]),
    (r"green pickup truck", [g(T1, 60.3), g(T1, 60.9)]),
    (r"Nowhere else in Leonida", [mp(CAPRI)]),
    (r"is the City of Capri", [title("CAPRI", "THE SECRET CITY", T2, 154.3)]),
    (r"real-world geography joke", [g(L, 62.3)]),
    (r"Bay of Naples", [rtitle("CAPRI, ITALY", "OFF THE COAST OF NAPLES", PX + "capri_italy_coast.mp4", 3.0)]),
    (r"wealthiest Gulf Coast city", [mp(CAPRI)]),
    (r"^Naples, Florida", [title("NAPLES, FLORIDA", "CAPRI = A PLAY ON NAPLES", real=PX + "naples_florida_pier.mp4", real_at=2.0)]),
    (r"direct geographical play", [split(T2, 154.3, PX + "capri_italy_coast.mp4", 8.0, "CAPRI", "CAPRI, ITALY")]),
    (r"larger than Port Gellhorn", [hud("stats", "CAPRI VS PORT GELLHORN::BIGGER=street grid than Port Gellhorn")]),
    (r"four different west and central Florida", [hud("cards", "CAPRI = 4 CITIES::NAPLES=Beach and pier|SEBRING=Circle Park roundabout|"
                                                                "LAKELAND=Lake Mirror promenade|ST. PETERSBURG=The high-rise towers")]),
    (r"real Naples Pier", [split(L, 54.3, PX + "naples_florida_pier.mp4", 6.0, "CAPRI BEACH", "A REAL GULF PIER")]),
    (r"private boat docks", [split(L, 10.3, PX + "mansion_boat_dock_florida.mp4", 2.0, "CAPRI DOCKS", "REAL DOCKS")]),
    (r"rob the safe inside", [g(T2, 140.3), g(L, 34.3)]),
    (r"circular park roundabout", [real(PX + "roundabout_aerial_park.mp4", 2.0)]),
    (r"Sebring Circle Park", [mp(SEBRING)]),
    (r"skyline shoots upward", [g(T2, 34.3)]),
    (r"Lake Mirror Park", [mp(LAKELAND), split(T1, 18.3, PX + "st_petersburg_florida_skyline.mp4", 3.0, "CAPRI TOWERS",
                                                  "ST. PETE AREA")]),
    (r"3.3 kilometers", [hud("stats", "CAPRI CITY::3.3 KM=one loop around the city")]),
    (r"Firemen’s Field", [g(T2, 38.3), g(T2, 40.3)]),
    (r"Capri City Jackals Stadium", [rtitle("CAPRI CITY JACKALS", "STADIUM", PX + "football_stadium_aerial.mp4", 2.0)]),
    (r"just south of Capri in Mariana County", [mp(MARIANA)]),
    (r"secret coastal airstrip", [route("ONE ROAD IN  ·  ONE ROAD OUT", CAPRI, AIRSTRIP)]),
    (r"one road in and one road out", [real(PX + "small_airstrip_aerial.mp4", 2.0)]),
    (r"six-star police perimeter", [hud("stars", "upto=4")]),
    (r"trapped between the swamp and the sea", [g(L, 70.3), g(T2, 138.3)]),
    (r"original blueprint", [g(T1, 36.3)]),
    (r"Project Americas\.", [title("PROJECT AMERICAS", "THE ORIGINAL CODENAME", T1, 14.3)]),
    (r"expand with new cities", [mp("all")]),
    (r"DNA of Project Americas", [g(T2, 154.3)]),
    (r"license plates from Gloriana", [hud("cards", "OUT-OF-STATE PLATES::GLORIANA=Rockstar's Georgia|LIBERTY STATE=Home of Liberty City")]),
    (r"landlocked northern border", [mp(LUMMOX, T1, 54.8)]),
    (r"burn through the map in a single weekend", [g(T1, 2.3)]),
    (r"stumble into whole cities", [route("FOG OF WAR", VICE, LAKE, CAPRI)]),
    (r"two-hundred-and-twelve-gigabyte", [title("MIDNIGHT", "NOVEMBER 19", L, 60.3)]),
    (r"^Don’t make that mistake", [g(L, 54.6)]),
    (r"west-bound toll highway", [route("YOUR MIDNIGHT ROUTE", OCEAN, LAKE, CAPRI)]),
    (r"standing in the secret city", [title("CAPRI", "THE CITY ROCKSTAR HID", T2, 154.3)]),
]

POOLS = [
    [(T1, 2.3), (T1, 12.3), (T2, 152.3), (L, 60.8)],
    [(T1, 36.3), (L, 40.3), (T2, 120.8), (L, 44.8)],
    [(T1, 18.8), (T2, 34.3), (T1, 28.8), (L, 54.8), (T2, 36.8)],
    [(T2, 154.3), (T2, 34.3), (T1, 60.3), (L, 62.3)],
    [(L, 54.3), (T2, 38.3), (L, 10.3), (T2, 140.3)],
    [(T1, 2.3), (T1, 36.3), (L, 60.3), (T2, 154.3)],
]


def build():
    text = (ROOT / "capri_script.txt").read_text(encoding="utf-8")
    lines, used, chapter, pool_i = [], set(), 0, [0] * len(POOLS)
    for sent in [x.strip() for x in text.split("\n") if x.strip()]:
        shots = []
        for k, (pat, head, sub, clip) in enumerate(CHAPTERS):
            if re.search(pat, sent):
                chapter = k + 1
                shots.append(chap(head, sub, *clip))
        for k, (pat, sh) in enumerate(RULES):
            if k not in used and re.search(pat, sent):
                used.add(k)
                shots += [dict(x) for x in sh]
                break
        words = len(sent.split())
        need = 0 if shots and (words < 24 or len(shots) > 1) else 1
        for _ in range(need):
            pool = POOLS[chapter]
            clip, at = pool[pool_i[chapter] % len(pool)]
            pool_i[chapter] += 1
            shots.append(g(clip, at + 0.5 * (pool_i[chapter] // len(pool))))
        lines.append((sent, shots))
    return lines


COLS = ["narration", "shot", "game_clip", "game_at", "real", "real_at", "left", "right", "title", "subtitle", "place"]

if __name__ == "__main__":
    out = ROOT / "gta6_capri_scenes.csv"
    lines = build()
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        for text, shots in lines:
            for i, s in enumerate(shots):
                w.writerow({"narration": text if i == 0 else "", **s})
    unused = [p for p, _s in RULES if not any(re.search(p, t) for t, _ in lines)]
    print(out, len(lines), "lines; rules never matched:", unused)
