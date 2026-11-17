"""Writes gta6_confirmed_scenes.csv: 'Everything Confirmed About GTA 6' (Game Launch style).
Narration = gta6_confirmed_voiceover.txt, split into voice lines. Trailer times were picked from 2-second contact sheets."""
import csv
from pathlib import Path

T1, T2, L = "gta6_trailer1.mp4", "gta6_trailer2.mp4", "gta6_launch_trailer.mp4"
ST = "footage/stock/"


def g(clip, at):
    return {"shot": "game", "game_clip": clip, "game_at": at}


def title(t, sub, clip=None, at=None, real=None, real_at=None):
    return {"shot": "title", "title": t, "subtitle": sub, "game_clip": clip or "", "game_at": at if at is not None else "",
            "real": real or "", "real_at": real_at if real_at is not None else ""}


def chap(t, sub, clip, at):
    return {"shot": "chapter", "title": t, "subtitle": sub, "game_clip": clip, "game_at": at}


def split(clip, at, real, real_at, left, right):
    return {"shot": "split", "game_clip": clip, "game_at": at, "real": real, "real_at": real_at, "left": left, "right": right}


def real(r, at=""):
    return {"shot": "real", "real": r, "real_at": at}


def mp(place, clip="", at=""):
    return {"shot": "map", "place": place, "game_clip": clip, "game_at": at}


def board(items, clip="", at="", head="CONFIRMED OR NOT?"):
    return {"shot": "board", "title": head, "subtitle": "; ".join(items), "game_clip": clip, "game_at": at}


def dossier(name, role, line, clip, at):
    return {"shot": "dossier", "title": name, "subtitle": f"{role} | {line}", "game_clip": clip, "game_at": at}


def timeline(head, items):
    return {"shot": "timeline", "title": head, "subtitle": "; ".join(items)}


def storms(head, ids):
    return {"shot": "storms", "title": head, "place": "; ".join(ids)}


# scoreboard items, chapter by chapter (each chapter's board adds its own with +)
B_MAP = ["Leonida = Florida=yes", "Six regions named=yes", "Vice City returns=yes", "Map size=no"]
B_CHAR = ["Lucia and Jason=yes", "Six supporting characters=yes", "Story roles=no", "Character switching=no"]
B_CARS = ["Cars, bikes and boats=yes", "Full car list=no"]
B_COPS = ["Chases and arrests shown=yes", "Wanted system=no"]
B_WX = ["Weather system=no", "Hurricanes=no"]


def plus(items):
    return ["+" + x for x in items]


VICE = "Vice City=Miami@25.77,-80.19"
KEYS = "Leonida Keys=Florida Keys@24.72,-81.1"
GRASS = "Grassrivers=Everglades@25.55,-80.95"
PORT = "Port Gellhorn=Panhandle@30.16,-85.66"
AMBR = "Ambrosia=Lake Okeechobee Area@26.75,-80.93"
KALAGA = "Mount Kalaga=North Florida Wilds@29.9,-82.2"

LINES = [
    # ------------------------------------------------------------------ cold open
    ("Grand Theft Auto Six is almost here.", [title("NOV 19", "GTA VI  ·  BEFORE YOU PLAY", T2, 154.3)]),
    ("After more than ten years of waiting, two delays, and more rumors than anyone can count, the date is finally locked in.",
     [timeline("THE ROAD TO LAUNCH", ["DEC 2023=Trailer 1, coming 2025", "MAY 2025=Delayed to May 26, 2026",
                                       "NOV 2025=Delayed again to Nov 19, 2026", "NOV 19 2026=Launch day"])]),
    ("November nineteenth. On PlayStation Five, and Xbox Series X and S.",
     [title("NOV 19", "PS5  ·  XBOX SERIES X|S", L, 60.3)]),
    ("But before you play, there's a problem. The internet is full of noise.", [g(T1, 26.3), g(T1, 44.3)]),
    ("Fake maps. Fake leaks. So-called insiders who are wrong more often than they're right.",
     [title("RUMORS EVERYWHERE", "FAKE MAPS  ·  FAKE LEAKS", T1, 58.3)]),
    ("So in this video, we're doing something simple. We're only covering what Rockstar has actually confirmed, or actually shown in the trailers.",
     [title("ONLY WHAT'S CONFIRMED", "ROCKSTAR TRAILERS  ·  OFFICIAL INFO", T2, 34.3)]),
    ("Five chapters. The map. The characters. The cars. The police. And the weather.",
     [g(T1, 36.3), g(L, 26.3), g(L, 46.3), g(L, 70.3), g(T2, 84.3)]),
    ("If something is just a rumor, I'll tell you it's a rumor. By the end, you'll know exactly what's real, and exactly what's still a mystery.",
     [g(T2, 6.8), g(L, 10.3)]),
    ("Let's get you ready for Leonida.", [title("EVERYTHING CONFIRMED", "5 CHAPTERS", T1, 14.3)]),

    # ------------------------------------------------------------------ 1 the map
    ("Chapter one. The map.", [chap("THE MAP", "Chapter 1", T1, 36.8)]),
    ("GTA Six takes place in the State of Leonida. It's Rockstar's version of Florida.",
     [split(T1, 21.75, ST + "pexels_11243172.mp4", 6.0, "LEONIDA", "FLORIDA")]),
    ("And that alone is a big deal. The last time a GTA gave us a whole state, instead of one city and its outskirts, was San Andreas, back in two thousand four.",
     [mp("all"), g(T1, 10.3)]),
    ("At the heart of Leonida is Vice City.", [g(T1, 39.85)]),
    ("If you're old enough, you remember it from two thousand two. Pastel suits, neon lights, and an eighties soundtrack.",
     [g(T1, 30.05), g(T1, 32.3)]),
    ("But this Vice City is not a remake. It's set in the present day, and it's rebuilt from the ground up.", [g(T2, 34.7)]),
    ("Glass towers. Packed highways. Crowded beaches. And a nightlife that never seems to stop.",
     [g(T1, 18.8), g(T1, 24.3), g(T1, 22.3), g(T1, 28.3)]),
    ("Rockstar has officially named six regions of Leonida. Let's go through them, one by one.", [mp("all")]),
    ("First, Vice City itself. Rockstar's take on Miami.", [title("VICE CITY", "REGION 1", T1, 23.35), mp(VICE, T1, 32.3)]),
    ("The beach strip, the downtown skyline, the clubs, and all the money moving through them.",
     [split(L, 54.6, ST + "pexels_4135117.mp4", 2.0, "VICE BEACH", "MIAMI BEACH"),
      split(T2, 35.5, ST + "pexels_31004828.mp4", 2.0, "DOWNTOWN VICE", "DOWNTOWN MIAMI"),
      split(T1, 27.45, ST + "pexels_34059053.mp4", 0.0, "VICE NIGHTS", "MIAMI NIGHTS")]),
    ("Second, the Leonida Keys.", [title("LEONIDA KEYS", "REGION 2", T2, 6.1)]),
    ("A long chain of islands, linked by bridges that stretch out over bright blue water, just like the Florida Keys.",
     [mp(KEYS, T2, 6.6), split(T1, 35.75, ST + "pexels_33959669.mp4", 3.0, "LEONIDA KEYS", "SEVEN MILE BRIDGE")]),
    ("Boats, fishing docks, beach bars, and a lot of shady business.", [g(T2, 8.2), g(L, 4.3), g(T2, 90.3)]),
    ("Third, Grassrivers.", [title("GRASSRIVERS", "REGION 3", T1, 19.25)]),
    ("Rockstar's version of the Everglades. Wide open wetlands, tall grass, slow brown water, and alligators. Lots of alligators.",
     [mp(GRASS, T1, 20.3), split(T1, 20.0, ST + "pexels_34338326.mp4", 10.0, "GRASSRIVERS", "EVERGLADES"),
      split(T1, 41.35, ST + "pexels_11841042.mp4", 0.0, "POOL GATOR", "EVERGLADES GATOR")]),
    ("Fourth, Port Gellhorn.", [title("PORT GELLHORN", "REGION 4", T2, 125.8)]),
    ("A beach town that has seen better days. Cheap motels, empty lots, and people just trying to get by.",
     [mp(PORT, T1, 72.85), split(T2, 126.8, ST + "pexels_31040643.mp4", 5.0, "PORT GELLHORN", "PANAMA CITY BEACH"), g(T1, 72.85)]),
    ("Fifth, Ambrosia.", [title("AMBROSIA", "REGION 5", T1, 70.3)]),
    ("A small industrial town built around a giant sugar refinery. It's working class, it's rough, and it's a long way from the glamour of Vice City.",
     [mp(AMBR, T1, 70.3), split(T1, 59.55, ST + "pexels_40799964.mp4", 5.0, "AMBROSIA", "SUGAR COUNTRY"), g(L, 18.0)]),
    ("And sixth, Mount Kalaga National Park.", [title("MOUNT KALAGA", "REGION 6", T1, 55.05)]),
    ("Up in the north of the state. Forests, rivers, trails, and the wild side of Leonida.",
     [mp(KALAGA, T1, 54.3), split(T1, 52.25, ST + "pexels_31149971.mp4", 3.0, "MOUNT KALAGA", "REAL WILDS")]),
    ("But this map isn't just about places. It's about people.", [g(T2, 40.3)]),
    ("The first trailer is packed with clips that look like real social media posts.", [g(T1, 46.3), g(T1, 43.95)]),
    ("People partying on the roof of a moving car. Fights in the street. An alligator wandering into a convenience store.",
     [g(T1, 26.8), g(T1, 30.3), g(T1, 42.0)]),
    ("If you've ever seen a Florida Man headline, you'll get the joke right away.", [g(T1, 63.65), g(T1, 66.3)]),
    ("Rockstar is clearly having fun with it, and it shows how busy and alive this world is going to feel.",
     [g(L, 18.8), g(L, 20.3)]),
    ("Now, what is not confirmed? The exact size of the map.", [title("NOT CONFIRMED", "MAP SIZE", L, 46.4)]),
    ("You'll see videos claiming it's twice as big as GTA Five, or three times bigger than Red Dead Redemption Two.",
     [mp("all")]),
    ("Rockstar has not said any of that. Until we play it, map size is a guess.", [board(plus(B_MAP), T2, 82.3)]),

    # ------------------------------------------------------------------ 2 the characters
    ("Chapter two. The characters.", [chap("THE CHARACTERS", "Chapter 2", T2, 88.3)]),
    ("For the first time in a modern GTA, one of the main characters is a woman.", [g(L, 62.3)]),
    ("And this time, there are two leads, telling one story together.", [g(L, 40.3)]),
    ("Let's start with Lucia Caminos.", [dossier("Lucia Caminos", "Protagonist", "Locked up protecting her family. Learned to fight from her father.", T1, 6.3)]),
    ("She's the very first thing you see in the very first trailer. A prison jumpsuit, inside the Leonida Department of Corrections.",
     [g(T1, 8.3)]),
    ("Rockstar says Lucia ended up behind bars trying to protect her family.", [g(T2, 64.3)]),
    ("Her father taught her to fight when she was just a kid.", [g(T2, 114.3)]),
    ("She's tough, she's smart, and after her time inside, she's done playing it safe.", [g(T1, 62.3), g(L, 72.3)]),
    ("Then there's Jason Duval.", [dossier("Jason Duval", "Protagonist", "Grew up around grifters. Ex-army. Runs jobs in the Keys.", T2, 18.3)]),
    ("Jason grew up around grifters and crooks. He tried to leave that life behind by joining the army, but it didn't stick.",
     [g(T2, 24.3), g(T2, 28.3)]),
    ("Now he lives in the Keys, doing jobs for local drug runners.", [g(T2, 20.3), g(L, 6.3)]),
    ("He isn't chasing power. He wants something simple. An easy life.", [g(L, 12.3)]),
    ("And then he meets Lucia. Maybe she's the best thing that ever happened to him. Maybe she's the worst.",
     [g(T2, 66.3), g(T2, 68.3)]),
    ("Together, they are the heart of the game.", [g(L, 66.3)]),
    ("The trailers show them robbing stores side by side, cruising with the top down, and sinking deeper into trouble.",
     [g(T1, 76.3), g(L, 26.8), g(T1, 74.3)]),
    ("Rockstar says that when an easy score goes wrong, the two of them end up in the middle of a criminal conspiracy that stretches across the whole state.",
     [g(L, 32.3), g(L, 52.3)]),
    ("Think Bonnie and Clyde, in modern day Florida.", [g(T2, 74.3)]),
    ("Rockstar has also introduced the people around them.", [title("THE SUPPORTING CAST", "", T2, 90.8)]),
    # CHECK: supporting-cast shots are best guesses from the trailers; swap a time if the face is wrong.
    ("Cal Hampton. Jason's friend and partner.", [dossier("Cal Hampton", "Jason's partner", "Beer, Coast Guard radio, and trusts no one.", T2, 150.3)]),
    ("He'd rather stay home with a beer, listening in on Coast Guard radio, and he's convinced that somebody, somewhere, is always watching.",
     [g(L, 58.3)]),
    ("Brian Heder. An old school drug runner who has worked the Keys for decades.",
     [dossier("Brian Heder", "Keys drug runner", "Old school. Jason lives on one of his properties.", T2, 14.3)]),
    ("Jason lives on one of his properties, and pays his way by doing jobs for him.", [g(T2, 10.3), g(T2, 22.3)]),
    ("Boobie Ike. A Vice City legend.", [dossier("Boobie Ike", "Vice City legend", "Real estate, a strip club and Only Raw Records.", T2, 118.3)]),
    ("He took money from the streets and turned it into real estate, a strip club, and a record label called Only Raw Records.",
     [g(T2, 128.3), g(T2, 102.3)]),
    ("Dre'Quan Priest. He dreams of managing the next big rap act, and he's signed to Boobie's label.",
     [dossier("Dre'Quan Priest", "Only Raw Records", "Wants to manage the next big rap act.", T2, 100.3)]),
    ("Real Dimez. A rap duo, Bae-Luxe and Roxy.", [dossier("Real Dimez", "Rap duo", "Bae-Luxe and Roxy. Went viral, now want real money.", T2, 124.3)]),
    ("Old friends who went viral, and now want to turn that fame into real money.", [g(L, 44.3)]),
    ("And Raul Bautista.", [dossier("Raul Bautista", "Bank robber", "Seasoned, takes big risks, always hunting new talent.", L, 30.3)]),
    ("A confident, experienced bank robber who is always looking for fresh talent, and doesn't mind big risks if it means a big score.",
     [g(L, 34.3), g(L, 64.3)]),
    ("What's not confirmed? How these characters fit into the story. Who betrays who.",
     [title("NOT CONFIRMED", "STORY ROLES", T2, 76.3)]),
    ("And whether you can switch between Jason and Lucia at any time, the way you could in GTA Five. Rockstar is keeping all of that quiet.",
     [g(T2, 132.3), board(B_MAP + plus(B_CHAR), T2, 146.3)]),

    # ------------------------------------------------------------------ 3 the cars
    ("Chapter three. The cars.", [chap("THE CARS", "Chapter 3", T1, 24.8)]),
    ("Leonida is built for driving, and the trailers prove it.", [g(T2, 34.0), g(T1, 60.3)]),
    ("We see muscle cars roaring down the highway.", [g(T2, 152.3)]),
    ("Exotic sports cars parked outside the clubs of Vice City.", [g(L, 46.8)]),
    ("Convertibles cruising the beach at sunset.", [g(L, 26.3)]),
    ("Lifted pickup trucks kicking up dust on back country roads.", [g(T1, 70.8), g(T2, 10.8)]),
    ("Motorbikes weaving through traffic.", [g(T2, 148.3), g(L, 48.3)]),
    ("Even ordinary, everyday cars stuck in traffic jams, which makes the whole world feel real.", [g(T1, 32.8)]),
    ("And the detail is on another level. Paint that reflects the neon lights.", [g(L, 19.0)]),
    ("Mud on the tires. Cars that lean and bounce on the road, the way real ones do.", [g(L, 38.3), g(T2, 30.3)]),
    ("But in Florida, the road is only half the story. Water is everywhere.", [g(T1, 10.8)]),
    ("The trailers show speedboats racing through the Keys, jet skis skipping over the waves, and airboats flying across the swamps of Grassrivers.",
     [split(T2, 140.05, ST + "pexels_35077123.mp4", 5.0, "LEONIDA WATERS", "FLORIDA WATERS"),
      split(T2, 138.2, ST + "pexels_11840880.mp4", 0.0, "AIRBOAT CHASE", "REAL AIRBOAT")]),
    ("As always in GTA, the brands are parodies. The cars look like the real thing, but the names are Rockstar's own jokes.",
     [g(L, 47.3), g(T2, 120.3)]),
    ("And if you've played GTA before, you'll recognize a few familiar shapes.", [g(T2, 16.3)]),
    ("What's not confirmed? The full list of vehicles. How many cars are in the game.",
     [title("NOT CONFIRMED", "CAR LIST  ·  CUSTOMIZATION", T2, 130.3)]),
    ("How deep customization goes. And whether you can buy, store and upgrade everything you drive.", [g(T1, 52.3)]),
    ("You'll see full car lists online. None of them come from Rockstar.", [board(B_MAP + B_CHAR + plus(B_CARS), T1, 24.3)]),

    # ------------------------------------------------------------------ 4 the police
    ("Chapter four. The police.", [chap("THE POLICE", "Chapter 4", T2, 108.3)]),
    ("Crime is the whole point of GTA. So what do we actually know about the law in Leonida?", [g(T1, 76.8)]),
    ("First, the story starts with the justice system. Lucia's first scene is inside a prison.", [g(T2, 50.3)]),
    ("So from minute one, the police are not just the people chasing you. They're part of the story.",
     [g(T2, 52.3), g(T2, 60.3)]),
    ("The trailers show Lucia and Jason holding up a convenience store, masks on, guns out.", [g(T1, 68.3)]),
    ("They show high speed chases on the highway, with police cruisers right on their bumper.",
     [split(L, 70.0, ST + "pexels_32538553.mp4", 3.0, "LEONIDA POLICE", "FLORIDA POLICE")]),
    ("Helicopters circling over the city.", [g(L, 68.0)]),
    ("And arrests shown like real news clips, and even bodycam style footage, just like what you'd see on the evening news.",
     [g(T1, 48.3), g(T1, 64.3)]),
    ("The police themselves look more realistic than in any GTA before. The cruisers, the uniforms, the way officers move and react. It's a big step up from the cartoon cops of the older games.",
     [g(T2, 106.3), g(L, 71.0), real(ST + "pexels_7714378.mp4", 2.0)]),
    ("And there's something else. In these trailers, it's not only the police who are watching. It's everyone.",
     [g(T1, 56.3)]),
    ("People film crimes on their phones. Clips go viral. The news picks them up.", [g(T1, 46.8), g(T1, 66.8)]),
    ("In a world like that, getting away with anything might be harder than ever.", [g(T2, 116.3)]),
    ("What's not confirmed? How the wanted system works. Whether it's still stars.",
     [title("NOT CONFIRMED", "WANTED SYSTEM", L, 32.8)]),
    ("How the police search for you, and how long they remember you.", [g(T2, 144.3)]),
    ("Rockstar hasn't shown real gameplay of this yet. So anything you've heard is still a guess.",
     [board(B_MAP + B_CHAR + B_CARS + plus(B_COPS), L, 74.3)]),

    # ------------------------------------------------------------------ 5 the weather
    ("Chapter five. The weather.", [chap("THE WEATHER", "Chapter 5", T1, 2.3)]),
    ("This chapter is short, and here's why. Rockstar has not explained a weather system for GTA Six yet.",
     [title("NO WEATHER SYSTEM REVEALED", "YET", T1, 4.3)]),
    ("So we're going to stick to what the trailers actually show.", [g(T2, 38.3)]),
    ("And what they show is beautiful. Golden sunsets over the Keys.",
     [split(T2, 84.8, ST + "pexels_17362433.mp4", 3.0, "LEONIDA SUNSET", "KEYS SUNSET")]),
    ("A thick, hot haze hanging over the swamps of Grassrivers.",
     [split(T1, 20.5, ST + "pexels_6156482.mp4", 4.0, "GRASSRIVERS HAZE", "EVERGLADES HAZE")]),
    ("Clear blue beach days in Vice City.", [g(T1, 12.8)]),
    ("And at night, the whole city glowing in neon.", [g(L, 60.8)]),
    ("The real star here is the lighting. Light bounces off water, off car paint, off skin.", [g(L, 62.8), g(L, 10.8)]),
    ("Shadows stretch out as the sun goes down. It's the most realistic lighting Rockstar has ever shown, and it changes the mood of every single scene.",
     [g(T2, 66.8), g(L, 36.3)]),
    ("Now, the rumor you've probably heard. Hurricanes.", [title("RUMOR", "HURRICANES", T1, 50.3)]),
    ("A huge storm that sweeps across Leonida and changes the world around you.",
     [real(ST + "pexels_7318020.mp4", 2.0)]),
    ("It's a great idea, and Florida would be the perfect place for it.", [storms("REAL FLORIDA HURRICANES", ["AL041992", "AL142018", "AL092022"])]),
    ("But it is not confirmed. If it's in the game, we'll all find out together.",
     [board(B_MAP + B_CHAR + B_CARS + B_COPS + plus(B_WX), T2, 154.8)]),

    # ------------------------------------------------------------------ outro
    ("So let's put it all together.", [title("RECAP", "EVERYTHING CONFIRMED", T1, 36.0)]),
    ("GTA Six takes you to the State of Leonida, with six named regions, from the neon of Vice City to the swamps of Grassrivers.",
     [board(B_MAP + B_CHAR + B_CARS + B_COPS + B_WX, T1, 36.3, head="EVERYTHING CONFIRMED")]),
    ("You'll play as Lucia Caminos and Jason Duval, with a wild cast of characters around them.", [g(L, 27.0)]),
    ("You'll drive cars, bikes, boats and airboats.", [g(L, 48.8), g(T2, 140.3)]),
    ("You'll face police that look more real than ever, in a world where everyone is filming.", [g(L, 70.8), g(T1, 27.0)]),
    ("And you'll see all of it under the best lighting Rockstar has ever made.", [g(T2, 155.3)]),
    ("Release date. November nineteenth.", [title("NOV 19", "GTA VI", L, 60.3)]),
    ("On PlayStation Five, and Xbox Series X and S. No PC version has been announced yet.",
     [title("PS5  ·  XBOX SERIES X|S", "NO PC VERSION ANNOUNCED", T2, 152.95)]),
    ("If this helped you get ready, hit subscribe. Because once the game is out, we're going to test every single one of these things, for real.",
     [title("SUBSCRIBE", "WE'LL TEST IT ALL AFTER LAUNCH", real=ST + "pexels_3770584.mp4", real_at=6.0)]),
    ("See you in Leonida.", [g(L, 24.3)]),
]

COLS = ["narration", "shot", "game_clip", "game_at", "real", "real_at", "left", "right", "title", "subtitle", "place"]

if __name__ == "__main__":
    out = Path(__file__).with_name("gta6_confirmed_scenes.csv")
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        for text, shots in LINES:
            for i, s in enumerate(shots):
                w.writerow({"narration": text if i == 0 else "", **s})
    print(out)
