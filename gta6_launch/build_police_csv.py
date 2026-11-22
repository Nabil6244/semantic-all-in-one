"""Writes gta6_police_scenes.csv: 'Every GTA 6 Police Force' (Game Launch style, the user's own voiceover).

police_script.txt is the pasted script split into sentences. A chapter card opens each force (Vice Beach, the city, undercover
and body cams, the county, the sheriff, highway patrol, POACH, corrections), then the stars and the cheat sheet, so each
becomes a Short. Trailer seconds come from 1-per-second contact sheets of the three trailers (the shots the script names)."""
from pathlib import Path

from build_cartheft_csv import hud
from build_confirmed_csv import L, ST, T1, T2, chap, g, split, timeline, title
from build_map_csv import BK, CC, build, write

ROOT = Path(__file__).resolve().parent
S = "footage/stock/px_"
# where the script's shots are in the trailers (contact sheets, 1 frame a second)
NEWS_HELI = (T1, 67.4)       # Weazel News aerial, cars on a street
POOL_GATOR = (T1, 42.4)      # official poach post: gator out of a pool with a catchpole
NIGHT_HELI = (T1, 45.4)      # night aerial, lights below
RAID = (T1, 48.3)            # team smashes into an apartment
BODYCAM = (T1, 49.3)         # body cam frame
PICKUP = (T1, 60.3)          # Jason's pickup on the road (sheriff cars pass)
LUCIA_CASH = (T1, 63.2)      # Lucia, red bandana
WRECK = (T1, 64.4)           # live news: flipped car, two cruisers
BADGE = (T1, 65.3)           # corrections badge + neck-tattoo man
WALL = (T2, 47.4)            # Haitian-flag wall, pat-down, white car
PRISON = (T2, 50.3)          # prison tower
GUARD = (T2, 55.3)           # guard behind wire mesh
LUCIA_OUT = (T2, 63.4)       # Lucia walks out
VEST = (T2, 108.4)           # man pulls on a police vest
LDC = (T2, 134.6)            # orange LDC work vest
COUNTY_HELI = (T2, 138.4)    # helicopter over the water
ARMORED = (T2, 144.4)        # dark truck, red and blue lights
BOAT_RUN = (T2, 146.4)       # speedboat run
DIRT_BIKE = (T2, 148.3)      # dirt bike escape at night
CHASE = (L, 47.3)            # white police car in a street chase
SHOOTOUT = (L, 61.4)         # night shootout


def at(p):
    return g(*p)


def ttl(t, sub, p):
    return title(t, sub, *p)


def ch(t, sub, p):
    return chap(t, sub, *p)


RULES = [
    # ---- cold open
    (r"^Count the police cars", [at(NEWS_HELI)]),
    (r"^Three cars, three paint jobs", [hud("cards", "ONE NEWS SHOT::CAR 1=Paint job one|CAR 2=Paint job two|CAR 3=Paint job three")]),
    (r"eight different looks for the law", [hud("stats", "ROCKSTAR HAS SHOWN::8=looks for the law|59=years one real county had no sheriff")]),
    (r"lose a four star chase", [hud("stars", "upto=4")]),
    (r"^This is Six Vortex", [ttl("SIX VORTEX", "GUIDES THAT HELP YOU PLAY", CHASE)]),
    # ---- 1 Vice Beach
    (r"^One Rockstar screenshot explains Vice Beach", [ch("VICE BEACH POLICE", "Force 1  ·  black and white", CHASE)]),
    (r"one officer cuffs a woman in a bikini", [at((L, 54.6))]),
    (r"^The trunk reads Vice Beach Police", [hud("cards", "THE SCREENSHOT::TRUNK=Vice Beach Police|CAR=Black, white doors|"
                                                         "BEHIND=The Ocean View sign")]),
    (r"Tommy Vercetti's first safe house", [ttl("OCEAN VIEW", "TOMMY VERCETTI'S FIRST SAFE HOUSE  ·  2002", (T1, 33.3))]),
    (r"^In the extended look, these cars get real work", [at(SHOOTOUT)]),
    (r"sedans, pickups with push bars and a helicopter", [hud("checklist", "4 STARS ON VICE BEACH::SEDANS|PICKUPS WITH PUSH BARS|"
                                                                          "A HELICOPTER")]),
    (r"Miami Beach Police headquarters", [split(CHASE[0], CHASE[1], ST + "pexels_4135117.mp4", 2.0, "VICE BEACH POLICE",
                                                "MIAMI BEACH POLICE")]),
    (r"black and white Rolls Royce", [hud("cards", "MIAMI BEACH PD · 2024::ROLLS ROYCE=Black and white|WHY=A dealer loan for recruiting")]),
    # ---- 2 city police
    (r"^Cross the bay into the city", [ch("THE CITY POLICE", "Force 2  ·  white with a blue stripe", WALL)]),
    (r"pat down people lined up against a wall", [at((T2, 48.6))]),
    (r"white car with a blue stripe", [hud("cards", "THE CITY CAR::PAINT=White, blue stripe|SIDE=Police and a round seal")]),
    (r"^Fans call them the VCPD", [ttl("\"VCPD\"", "THE LETTERS AREN'T READABLE", (T2, 49.3))]),
    # ---- 3 undercover + body cams
    (r"^Not everyone who comes for you wears a uniform", [ch("UNDERCOVER", "Force 3  ·  no uniform", VEST)]),
    (r"pulls a police vest over his shirt", [at((T2, 109.2))]),
    (r"three stars brought the Vice Squad", [hud("cards", "VICE CITY · 2002 · 3 STARS::VICE SQUAD=Undercover detectives|"
                                                          "UZIS=In a fast police Cheetah")]),
    (r"^Then there's the shot almost nobody talks about", [at(RAID)]),
    (r"^Body cam footage", [at(BODYCAM)]),
    (r"^The frame reads body 3", [hud("checklist", "THE FRAME/BODY CAM::BODY 3|AUGUST 4|23:58")]),
    (r"could end up on somebody's screen", [at((T1, 48.8))]),
    # ---- 4 the county
    (r"^Why so many forces", [ttl("WHY SO MANY?", "THAT'S HOW FLORIDA WORKS", NIGHT_HELI)]),
    (r"^Cities, counties and the state", [hud("cards", "FLORIDA POLICING::CITIES=Their own police|COUNTIES=Police and sheriffs|"
                                                       "THE STATE=Troopers and prisons")]),
    (r"^Start with the helicopter at the end of trailer two", [ch("THE COUNTY POLICE", "Force 4  ·  white, green and gold",
                                                                  COUNTY_HELI)]),
    (r"letters D A L E on the tail", [hud("cards", "THE COUNTY HELICOPTER::PAINT=White, green and gold|TAIL=D A L E")]),
    (r"escape on a dirt bike", [at(DIRT_BIKE), at(BOAT_RUN)]),
    (r"^Now trailer one", [at(BADGE)]),
    (r"^A Spanish language news story", [hud("cards", "THE BADGE::CORRECTIONS=|SHERIFF'S OFFICE=|DEPUTY=|COUNTY=Starts with Vice")]),
    (r"^So this county has police and a sheriff", [ttl("POLICE + SHERIFF", "ONE COUNTY", BADGE)]),
    (r"abolished its sheriff in 1966", [timeline("MIAMI-DADE'S MISSING SHERIFF", ["1966=Sheriff abolished after a scandal",
                                                                                  "2018=Voters order a sheriff in every county",
                                                                                  "JAN 2025=Rosie Cordero-Stutz elected"])]),
    (r"^In 2018 Florida voters", [hud("stats", "MIAMI-DADE::~60=years without an elected sheriff|2025=the first one back")]),
    (r"^That badge trailer dropped in December 2023", [hud("cards", "THE TIMING::DEC 2023=Trailer shows police and sheriff|"
                                                                    "JAN 2025=Real county gets a sheriff")]),
    (r"the game brings one back", [at((T1, 65.8))]),
    # ---- 5 sheriff
    (r"^Now leave the city", [ch("THE SHERIFF", "Force 5  ·  forest green and white", PICKUP)]),
    (r"passed by two cars with lights flashing", [at((T1, 61.2))]),
    (r"red bandana and a stack of cash", [at(LUCIA_CASH)]),
    (r"where those deputies are headed", [at((T1, 62.3))]),
    (r"forest green and white for sheriff vehicles", [hud("cards", "FLORIDA LAW::SHERIFF CARS=Forest green and white|"
                                                                   "THE BADGE=5-point star, state seal")]),
    (r"^Which county are they from", [ttl("WHICH COUNTY?", "THE NAME IS A BLUR", PICKUP)]),
    # ---- 6 highway patrol
    (r"force that might be scariest", [ch("HIGHWAY PATROL", "Force 6  ·  black and tan", WRECK)]),
    (r"^Black and tan has been the Florida Highway Patrol", [hud("stats", "FLORIDA HIGHWAY PATROL::1939=black and tan since|"
                                                                           "4=Best Looking Cruiser wins in a row")]),
    (r"skipped out on his bill at Pee Wee's", [at((T1, 64.8))]),
    (r"^Fans call them Leonida Highway Patrol", [ttl("\"LEONIDA HIGHWAY PATROL\"", "BLACK CARS  ·  TAN ROOFS", WRECK)]),
    (r"can't turn and you can't hide", [at((BK, 6.0))]),
    # ---- 7 POACH
    (r"doesn't chase people at all", [ch("POACH", "Force 7  ·  the wildlife officers", POOL_GATOR)]),
    (r"drags an alligator out of a swimming pool", [at((T1, 42.9))]),
    (r"Protection of Animals and Controlled Hunting", [hud("cards", "P.O.A.C.H.::P=Protection|O=Of|A=Animals|C=Controlled|H=Hunting")]),
    (r"best joke yet", [split(T1, 41.35, ST + "pexels_11841042.mp4", 0.0, "POOL GATOR", "FLORIDA GATOR")]),
    (r"8,700 alligators", [hud("stats", "FLORIDA NUISANCE PROGRAM · 2024::8,700+=alligators captured")]),
    # ---- 8 corrections
    (r"^One agency Lucia knows from the inside", [ch("CORRECTIONS", "Force 8  ·  Leonida Penitentiary", PRISON)]),
    (r"orange work vest with L D C", [at(LDC)]),
    (r"Leonida Department of Corrections", [hud("cards", "L.D.C.::FANS READ=Leonida Department of Corrections|"
                                                         "ROCKSTAR CALLS IT=Leonida Penitentiary")]),
    (r"guard sits behind wire mesh", [at(GUARD), hud("checklist", "THE SIGNS · ENGLISH AND SPANISH::NO WEAPONS PAST THIS POINT|"
                                                                  "BOOK VISITS AHEAD")]),
    (r"state prisons and county jails are separate", [hud("cards", "FLORIDA::STATE PRISONS=One system|COUNTY JAILS=Another")]),
    (r"dark armored truck with red and blue lights", [at(ARMORED)]),
    (r"no readable lettering", [ttl("WHOSE TRUCK?", "NO READABLE LETTERING", (T2, 144.9))]),
    # ---- stars
    (r"^Now look at the top right of the extended look", [ch("THE STARS", "Four lit  ·  room for six", SHOOTOUT)]),
    (r"^Four stars lit, room for six", [hud("stars", "upto=4")]),
    (r"^Start with history", [timeline("THE WANTED LEVEL", ["GTA 1=Race and Chase · 4 cop heads", "GTA 2=Six · the army at 6",
                                                            "GTA 3=Stars · SWAT, FBI, tanks", "GTA 4=NOOSE, FIB, search area",
                                                            "GTA 5=Vision cones · five stars"])]),
    (r"^GTA 3 introduced stars", [hud("cards", "GTA III · 2001::4 STARS=SWAT|5 STARS=FBI|6 STARS=Tanks")]),
    (r"^GTA 5 added vision cones", [hud("minimap", "gta5")]),
    (r"hasn't said what six means", [ttl("6 STARS?", "ROCKSTAR HASN'T SAID", (L, 62.3))]),
    (r"search your whole map", [hud("cards", "ONE PREVIEW · UNCONFIRMED::BELOW 6=Police comb one area|AT 6=They search the whole map")]),
    # ---- cheat sheet
    (r"^So here's the cheat sheet", [ch("THE CHEAT SHEET", "Who comes for you, where", (T1, 36.8))]),
    (r"^Start trouble on Vice Beach", [hud("cards", "VICE BEACH::CARS=Black and white|ALSO=Pickups and a helicopter")]),
    (r"^Cross the bay and white cars", [hud("cards", "THE CITY::CARS=White, blue stripe|ALSO=Body cams, plainclothes")]),
    (r"a boat won't save you", [at(BOAT_RUN)]),
    (r"dark green sheriff country", [at(PICKUP)]),
    (r"black cars with tan roofs", [at(WRECK)]),
    (r"leave the wildlife alone", [at(POOL_GATOR)]),
    (r"no longer show on your radar", [hud("minimap", "gta6")]),
    (r"police set up a perimeter", [hud("checklist", "ANYWHERE::USE FOCUS, NOT THE RADAR|ROB A STORE = A PERIMETER|"
                                                     "RIFLE ON YOUR BACK")]),
    (r"done time in Leonida Penitentiary", [at(LUCIA_OUT)]),
    (r"^You don't want to be next", [at(PRISON)]),
    # ---- the question
    (r"^Here's the question nobody can answer", [ch("THE BORDER QUESTION", "One force's turf into the next", CHASE)]),
    (r"take the bridge into the city", [at((T1, 35.75))]),
    (r"^Do the city cops pick up the chase", [hud("cards", "WHEN A CHASE CROSSES::A=They back off|B=City cops take over|"
                                                           "C=It follows you across the state")]),
    (r"wanted level is tied to an area", [hud("heat", "icons=face,outfit,vehicle,partner lit=face,vehicle")]),
    (r"^Now it's your turn", [ttl("YOUR TURN", "SHERIFF OR BEACH COPS?", PICKUP)]),
    (r"See you in Leonida", [ttl("SIX VORTEX", "SEE YOU IN LEONIDA", (T1, 35.75))]),
]

POOLS = [
    [CHASE, SHOOTOUT, NEWS_HELI],                                     # intro
    [CHASE, SHOOTOUT, (L, 62.8), (L, 46.6)],                          # Vice Beach
    [WALL, (T2, 46.6), (T2, 49.6)],                                   # city
    [VEST, RAID, (T2, 106.4)],                                        # undercover
    [COUNTY_HELI, (T2, 139.4), BADGE, DIRT_BIKE],                     # county
    [PICKUP, (T1, 61.7), LUCIA_CASH],                                 # sheriff
    [WRECK, (BK, 4.0), (BK, 14.0)],                                   # highway
    [POOL_GATOR, (T1, 41.35), (T1, 20.3)],                            # POACH
    [PRISON, GUARD, (T2, 57.3), LDC, (T2, 136.4)],                    # corrections
    [SHOOTOUT, (L, 62.8), CHASE, (L, 72.3)],                          # stars
    [CHASE, WALL, PICKUP, WRECK],                                     # cheat sheet
    [CHASE, (T1, 35.75), (CC, 7.0)],                                  # border question
]

if __name__ == "__main__":
    write(ROOT / "gta6_police_scenes.csv", build("police_script.txt", RULES, POOLS), RULES)
