"""Writes gta6_cartheft_scenes.csv: 'Stealing a Car in GTA 6 Is Now a Death Sentence. Here's Why' (Game Launch style).
One voice line per script sentence. Trailer times come from 2-second contact sheets of the three trailers.
GTA V comparisons use footage/gta5/*.mp4 when you record them; until then the GTA VI shot plays full screen."""
import csv
from pathlib import Path

from build_confirmed_csv import (AMBR, GRASS, KALAGA, KEYS, L, PORT, ST, T1, T2, VICE, chap, g, mp, split, timeline, title)

G5 = "footage/gta5/"


def hud(card, params="", clip="", at=""):
    return {"shot": "hud", "title": card, "subtitle": params, "game_clip": clip, "game_at": at}


def tracker(head):
    return {"shot": "tracker", "title": head}


def vs(clip, at, gta5_file, gta5_at=0.0):
    """GTA VI trailer | your GTA V recording, side by side."""
    return {"shot": "versus", "game_clip": clip, "game_at": at, "real": G5 + gta5_file, "real_at": gta5_at}


LINES = [
    # ------------------------------------------------------------------ cold open: the GTA V muscle memory
    ("For thirteen years, every Grand Theft Auto Five player has shared the exact same muscle memory.",
     [title("STEALING A CAR IN GTA 6", "IS NOW A DEATH SENTENCE", T1, 24.3)]),
    ("You walk out onto a sunny sidewalk, spot a parked supercar, and press a single button.",
     [vs(L, 46.3, "gta5_carjack.mp4", 0.0)]),
    ("Your character smashes the window, connects two wires in three seconds, and speeds off into traffic.",
     [vs(L, 47.0, "gta5_carjack.mp4", 4.0)]),
    ("If the cops spot you, you just watch their little cones of vision on your minimap.", [hud("minimap", "gta5")]),
    ("You duck into a dark alley for forty seconds, the stars vanish, and the car is yours.",
     [vs(T1, 32.3, "gta5_alley.mp4", 0.0)]),
    ("Try that exact same move on Thursday night in Grand Theft Auto Six, and you're dead.",
     [title("THURSDAY NIGHT", "GTA VI  ·  NOV 19", L, 70.3)]),
    ("According to three-hour developer showcases inside Rockstar North, Rockstar completely rebuilt how crime works in Leonida.",
     [g(T1, 66.3), g(L, 68.0)]),
    ("Stealing the wrong car in Vice City now triggers a six-layer trap designed to hunt you down.",
     [title("THE SIX-LAYER TRAP", "", T2, 152.3)]),
    ("Even if you lose the cruisers, ditch the car, and run home, the cops still remember you.", [g(T2, 106.3), g(T1, 49.5)]),
    ("And the deadliest part of this new system isn't even the police helicopters overhead.", [g(L, 68.6)]),
    ("It's a silent digital bomb ticking inside your stolen dashboard that only triggers when you hit the brakes.",
     [g(L, 38.3), g(T2, 46.3)]),

    # ------------------------------------------------------------------ 1 the steal
    ("Before we look at how that hidden tracker works, look at what happens before you even sit down.",
     [chap("THE STEAL", "Chapter 1", T1, 52.3)]),
    ("In old GTA games, pulling a driver out of their seat was a guaranteed, automatic animation.",
     [vs(T1, 70.3, "gta5_carjack.mp4", 10.0)]),
    ("In GTA 6, yanking open an occupied car door starts an unpredictable physical brawl on the street.",
     [g(T1, 30.3), g(T2, 114.3)]),
    ("Drivers actively resist, and passengers can grab Jason or Lucia and throw them straight back onto the pavement.",
     [g(T1, 56.3), g(L, 40.3)]),
    ("While you're wrestling in the middle of an intersection, civilians on the sidewalk aren't just screaming anymore.",
     [g(T1, 22.3), g(T2, 32.3)]),
    ("Witnesses pull out their smartphones, record your face and clothing, and send a live description to dispatch.",
     [g(T1, 44.3), hud("heat", "lit=face,outfit")]),
    ("So you might think it's safer to steal an empty car parked down a quiet side street.", [g(T2, 20.3), g(T2, 8.8)]),
    ("Except Rockstar divided every vehicle in Leonida into strict security tiers.", [hud("tiers", "focus=both")]),
    ("If you smash the window of a parked car, the alarm blares across the entire block immediately.",
     [g(T2, 152.8), g(T1, 32.8)]),
    ("To get inside quietly, you have to use physical burglary tools and beat an analog-stick lockpicking minigame.",
     [g(L, 6.3), g(L, 42.3)]),
    ("An old rusty sedan outside the Starlet Motel in Port Gellhorn opens easily with a simple slim jim.",
     [mp(PORT, T1, 72.85), g(T1, 74.3)]),
    ("Once you're inside an older model like that, you can hotwire the ignition column by hand.", [hud("tiers", "focus=1")]),
    ("But try taking a slim jim to a high-end sports car in downtown Vice City, and nothing happens.",
     [mp(VICE, L, 46.3), g(L, 40.8)]),
    ("Luxury cars are protected by digital immobilizers that completely block manual hotwiring.", [hud("tiers", "focus=3")]),
    ("You can't even start the engine unless you've unlocked a high-tech electronic key cloner from an underground fence.",
     [g(T2, 130.3), g(L, 34.3)]),

    # ------------------------------------------------------------------ 2 the arsenal
    ("And even if you have that key cloner, hopping into a random street car creates an immediate combat problem.",
     [chap("THE ARSENAL", "Chapter 2", L, 64.3)]),
    ("In GTA 5, your character was a walking military warehouse carrying nine rifles and an RPG in their pants.",
     [vs(L, 72.3, "gta5_weapon_wheel.mp4", 0.0)]),
    ("Rockstar killed the magic pocket inventory in GTA 6 and brought over the realism of Red Dead Redemption 2.",
     [title("NO MORE MAGIC POCKETS", "", T2, 132.3)]),
    ("On foot, Jason and Lucia can only conceal two handguns underneath their jackets.", [hud("carry")]),
    ("You can carry long guns, like an assault rifle or a shotgun, but they stay strapped visibly to your body.",
     [g(L, 72.8), g(L, 64.8)]),
    ("Walk down a crowded Vice Beach sidewalk holding a rifle, and terrified NPCs will scatter and call the police.",
     [split(L, 54.6, ST + "pexels_4135117.mp4", 2.0, "VICE BEACH", "MIAMI BEACH"), g(T1, 22.8)]),
    ("Your real arsenal lives inside the trunk compartment of your registered Personal Vehicle.", [g(T2, 86.3), g(T2, 10.8)]),
    ("And that vehicle size determines how much stolen loot you can actually haul away from a robbery.",
     [g(L, 34.8), g(T1, 76.3)]),
    ("A motorcycle holds almost zero duffel bags, a coupe holds a little, and a heavy van holds a fortune.", [hud("capacity")]),
    ("Think about what that means the second you abandon your personal ride to carjack a flashy convertible.", [g(L, 26.3)]),
    ("You just left all your heavy body armor, customized rifles, and duffel bag capacity sitting six blocks away.",
     [g(T2, 120.3), g(T2, 144.3)]),
    ("If you get cornered by SWAT teams and die with only a pistol, the punishment hits your wallet hard.",
     [g(L, 30.3), g(T2, 108.3)]),
    ("GTA 6 separates your money into protected bank funds on the BuckMe app and physical cash in your pocket.", [hud("cash")]),
    ("Until you physically visit an ATM to deposit your dirty bills, dying on the street wipes out your pocket cash.",
     [g(T1, 68.3), g(T2, 92.3)]),

    # ------------------------------------------------------------------ 3 the radar
    ("Yet losing your guns and cash is nothing compared to what happens when the new police radar locks onto you.",
     [chap("THE RADAR", "Chapter 3", L, 70.3)]),
    ("When sirens start wailing in GTA 6, your eyes will automatically dart to the bottom-left minimap.",
     [g(L, 70.8), g(T1, 66.8)]),
    ("And for the first five seconds, you're going to panic because the minimap is completely empty.", [hud("minimap", "gta6")]),
    ("Rockstar removed individual police blips and vision cones from the radar.",
     [title("NO BLIPS. NO CONES.", "THE RADAR IS EMPTY", T1, 24.8)]),
    ("You can't stare at a tiny corner map to cheese your way around patrol cars anymore.",
     [vs(T1, 66.3, "gta5_minimap.mp4", 0.0)]),
    ("Instead, the outer edge of your screen flashes red and blue from the direction cruisers are approaching.",
     [hud("minimap", "gta6", L, 70.3)]),
    ("You have to actually look down alleyways, check mirrors, and watch crossroads in real time.",
     [g(T2, 28.3), g(T2, 34.3)]),
    ("Even the classic wanted stars at the top of the screen now speak a completely new tactical language.",
     [title("THE WANTED STARS", "A NEW LANGUAGE", T2, 148.3)]),
    ("Hollow stars mean you tripped a silent alarm, so police are rushing in without knowing what you look like.",
     [hud("stars", "upto=1")]),
    ("Solid white stars mean officers have direct visual contact on you right now.", [hud("stars", "upto=2")]),
    ("Flashing white stars mean you broke line of sight, while red stars lock down a dual-ring search perimeter.",
     [hud("stars", "upto=3"), hud("stars", "upto=4")]),
    ("But look directly underneath those stars, and you'll spot Rockstar's smartest new mechanic: the Heat bar.",
     [hud("heat", "lit=none")]),
    ("The Heat bar displays five distinct icons showing every piece of evidence the police currently have on you.",
     [hud("heat", "lit=face,outfit,weapon,vehicle,partner")]),
    ("It tracks whether witnesses saw your face, your outfit, your weapon, your getaway car, and your partner.",
     [g(T1, 47.8), g(T1, 64.3)]),
    ("Even after you escape a chase and the wanted stars disappear, those Heat icons stay active in that neighborhood.",
     [g(T1, 33.0), g(T2, 152.3)]),
    ("Walk past a beat cop twenty minutes later wearing the same bloody shirt, and the chase restarts instantly.",
     [g(T2, 106.8), g(T2, 116.3)]),

    # ------------------------------------------------------------------ 4 the tracker
    ("And if you stole a luxury car without scanning it first, you won't even make it out of the district.",
     [chap("THE TRACKER", "Chapter 4", L, 46.8)]),
    ("Here is the secret mechanic that turns a routine supercar theft into a total death trap.",
     [title("THE DEATH TRAP", "", L, 40.3)]),
    ("On Jason and Lucia's in-game smartphone sits a black-market scanning tool called the Waink app.", [g(L, 12.3)]),
    ("Before you ever touch a parked vehicle, pointing the Waink app at it reveals its entire security profile.",
     [hud("waink", "", L, 46.3)]),
    ("It shows the lock tier, the resale value at a chop shop, the registration fee, and the GPS tracker class.",
     [hud("waink", "", T2, 152.3)]),
    ("Most players on launch night are going to ignore that app, hijack the fastest car in Vice City, and floor it.",
     [g(L, 46.8), g(L, 48.3)]),
    ("At first, as you're tearing down the highway at a hundred and forty miles an hour, everything feels fine.",
     [split(T1, 23.35, ST + "pexels_37694375.mp4", 3.0, "VICE CITY", "MIAMI"), g(T1, 2.3)]),
    ("There are no sirens behind you, no flashing stars, and no warnings on the dashboard.", [g(T2, 30.3), g(T1, 54.3)]),
    ("That's because high-tier vehicle trackers in GTA 6 are engineered to stay completely silent at high speeds.",
     [g(L, 38.8), g(T2, 34.8)]),
    ("The system waits until you think you're safe.", [g(T2, 84.3)]),
    ("The moment you slow down for dense city traffic, a red light, or a toll booth on the Leonida Keys bridges, the trap springs.",
     [tracker("THE SILENT TRACKER")]),
    ("A rapid electronic beep starts echoing inside the cabin.", [g(T2, 46.8)]),
    ("If you don't immediately accelerate back to high speed, that tracker broadcasts your exact GPS coordinates to every squad car in the county.",
     [mp(KEYS, T1, 35.75), split(L, 70.0, ST + "pexels_32538553.mp4", 3.0, "LEONIDA POLICE", "FLORIDA POLICE")]),
    ("Unless you've built enough reputation with a high-level vehicle fence who can strip advanced trackers, you can't turn it off.",
     [g(T2, 130.8), g(T2, 150.3)]),
    ("Even worse, if you try carjacking a police cruiser to escape, every single cop car has a permanent hardware tracker wired in.",
     [g(T2, 108.8), g(L, 70.6)]),
    ("Within seconds, you're staring at a full six-star manhunt that covers the entire state of Leonida.",
     [title("SIX STARS", "STATEWIDE MANHUNT", T1, 66.3), mp("all")]),

    # ------------------------------------------------------------------ 5 the getaway
    ("Surviving a high-heat pursuit in GTA 6 takes way more than just holding down the gas pedal.",
     [chap("THE GETAWAY", "Chapter 5", T2, 152.3)]),
    ("Rockstar rebuilt driving physics from scratch, blending the heavy suspension weight of GTA 4 with high-speed control.",
     [g(T1, 70.3), g(L, 18.3)]),
    ("Roads outside Vice City are narrower, traffic is packed tighter, and supercars spin out helplessly if you take them off-road into the Grassrivers mud.",
     [g(T1, 60.3), split(T1, 20.0, ST + "pexels_34338326.mp4", 10.0, "GRASSRIVERS", "EVERGLADES")]),
    ("During a chase, Leonida officers don't just pit-maneuver your bumper, they aim directly for your tires.",
     [g(T1, 66.8), g(L, 71.0)]),
    ("Losing a single tire at high speed violently pulls your steering and can flip your vehicle across the highway.",
     [g(T1, 70.8), g(L, 52.3)]),
    ("And if you get ejected in a high-speed wreck, your character stays dazed and stumbling for several seconds.",
     [g(L, 48.8), g(T2, 148.3)]),
    ("To fight back without triggering the Psychopath rating on your Criminal Profile, you have to use Focus Mode.",
     [title("CRIMINAL PROFILE", "PSYCHOPATH  ·  PROFESSIONAL", L, 64.3)]),
    ("Activating Focus slows down time, highlights hidden officers through walls, and marks vehicle weak points like tires, engine blocks, and fuel tanks.",
     [hud("focus", "", L, 70.3)]),
    ("Shooting out a cruiser's tires instead of killing the officers keeps your profile at the clean Professional tier.",
     [g(L, 72.3), g(T2, 108.3)]),
    ("Then, to wipe the Heat bar clean, you have to execute a multi-step getaway protocol.",
     [timeline("THE GETAWAY PROTOCOL", ["STEP 1=Torch the getaway car", "STEP 2=Swap outfits from the trunk",
                                        "STEP 3=Split up, minus one star"])]),
    ("In Rockstar's official showcase, Lucia drives the crew's getaway car into an alley, pours gasoline, and torches it.",
     [g(L, 52.8), g(L, 72.0)]),
    ("The moment they pile into a clean van, the vehicle icon vanishes from the police Heat display.",
     [hud("heat", "off=vehicle")]),
    ("Next, you grab the spare outfit stashed in your trunk to erase the clothing description.", [hud("heat", "off=vehicle,outfit")]),
    ("Finally, if dispatch reported a man and a woman robbing the target together, Jason and Lucia have to physically split up.",
     [g(L, 40.3), g(T2, 98.3)]),
    ("Going separate ways invalidates the police description of a criminal couple and drops a wanted star immediately.",
     [hud("heat", "off=vehicle,outfit,partner")]),
    ("In GTA 5, stealing a car was a mindless button press you forgot about five seconds later.",
     [vs(L, 46.3, "gta5_carjack.mp4", 12.0)]),
    ("In GTA 6, every stolen car is a high-stakes heist of its own, and only smart criminals will survive Leonida.",
     [g(T2, 154.3), title("SURVIVE LEONIDA", "GTA VI  ·  NOV 19", L, 60.3)]),
]

COLS = ["narration", "shot", "game_clip", "game_at", "real", "real_at", "left", "right", "title", "subtitle", "place"]

if __name__ == "__main__":
    out = Path(__file__).with_name("gta6_cartheft_scenes.csv")
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        for text, shots in LINES:
            for i, s in enumerate(shots):
                w.writerow({"narration": text if i == 0 else "", **s})
    print(out)
