"""Writes gta6_day1_scenes.csv: '12 Mistakes You'll Make in Your First 24 Hours of GTA 6' (Game Launch style, countdown).

Same builder as build_launchnight_csv.py: day1_script.txt -> one voice line per sentence, a rank card (#12 .. #1) on each
'Number N.' sentence, rule graphics on the rest, trailer pools for whatever no rule claims. New hud cards: garage, loop."""
import csv
import re
from pathlib import Path

import build_launchnight_csv as B
from build_cartheft_csv import hud, tracker, vs
from build_confirmed_csv import L, ST, T1, T2, board, g, mp, split, timeline, title

ROOT = Path(__file__).resolve().parent
VICE = "Vice City=Miami@25.77,-80.19"
HEAT4 = "icons=face,outfit,weapon,vehicle"
rank, card = B.rank, hud

RANKS = [
    (r"^Number twelve", "LEAVING THE DOWNLOAD LATE", "Preload is not the end of it", L, 0.6),
    (r"^Number eleven", "STEALING THE FIRST NICE CAR", "Scan first, steal second", L, 46.3),
    (r"^Number ten", "A CAR YOU CAN'T KEEP", "Unregistered cars disappear", T2, 28.3),
    (r"^Number nine", "THE WRONG WITNESS", "No witness, no stars", T2, 106.3),
    (r"^Number eight", "SUNGLASSES WON'T SAVE YOU", "Take the description apart", T1, 49.5),
    (r"^Number seven", "FLEEING THREE STARS BY CAR", "Ditch it, vanish on foot", L, 70.3),
    (r"^Number six", "BLOWING THE SAFE", "Fast, but the loot burns", L, 52.3),
    (r"^Number five", "PLAYING IT SOLO", "Jason and Lucia work as a pair", L, 40.3),
    (r"^Number four", "SEEING IT ALL IN ONE DAY", "One playthrough: about 80 hours", T1, 20.3),
    (r"^Number three", "THINKING LOOT IS MONEY", "Nothing pays until a fence does", T2, 130.3),
    (r"^Number two", "RACING THROUGH THE STORY", "Some jobs wait for your cash", T2, 92.3),
    (r"^And number one", "CARRYING YOUR CASH", "Bank it before you lose it", T2, 46.3),
]

RULES = [
    (r"^Sometime during your first night", [title("YOUR FIRST 24 HOURS", "IN GTA 6", T2, 154.3), g(L, 52.8)]),
    (r"take back the car", [g(L, 38.3), g(T1, 66.3)]),
    (r"waiting at number one", [title("THE COSTLIEST MISTAKE", "IS WAITING AT NUMBER ONE", T2, 46.8)]),
    (r"out on November 19", [title("NOVEMBER 19", "BUILT TO PUNISH GTA 5 HABITS", L, 60.3)]),
    (r"twelve mistakes", [card("cards", "12 MISTAKES::CARS=Stealing, keeping, tracking|COPS=Witnesses and descriptions"
                                       "|MONEY=Safes, fences and cash|TIME=Story and play hours")]),
    (r"single report or still unconfirmed", [board(["Rockstar's official material=yes", "Preview coverage=yes",
                                                    "Single reports=no"], T1, 66.8, "WHERE IT COMES FROM")]),
    (r"^Let's get into it", [g(T1, 2.3)]),
    (r"^Leaving the download", [g(L, 26.3)]),
    (r"opened preloading a week", [timeline("PRELOAD WEEK", ["NOV 10=Preload opens", "NOV 19 2026=Unlock"])]),
    (r"one gigabyte", [title("~1 GB UPDATE", "ALREADY OUT ON PS5  ·  NO NOTES", L, 46.8)]),
    (r"automatic updates", [card("checklist", "Check your console before the unlock|Switch on automatic updates|"
                                              "Leave free space on the drive")]),
    (r"cruelest first mission", [title("THE CRUELEST FIRST MISSION", "A PROGRESS BAR", T2, 132.3)]),
    (r"New Zealand going first", [card("unlock", "REGION BY REGION::15|19|New Zealand|Mexico & Central America")]),
    (r"^Mute the words", [g(T2, 18.3)]),
    (r"^Stealing the first beautiful car", [g(L, 64.3)]),
    (r"yours with one button", [vs(L, 47.0, "gta5_carjack.mp4", 0.0)]),
    (r"told IGN", [title("ROB NELSON  ·  ROCKSTAR NORTH", "LAYERS ADDED TO VEHICLES", T1, 52.3), g(L, 46.8)]),
    (r"phone scanner", [hud("waink", "", L, 46.3)]),
    (r"slim jim", [hud("tiers", "focus=1")]),
    (r"key cloner", [hud("tiers", "focus=3")]),
    (r"tracker can send police", [tracker("THE TRACKER")]),
    (r"care which car you take", [g(L, 30.3), g(T2, 24.3)]),
    (r"scan first and steal second", [title("SCAN FIRST", "STEAL SECOND", L, 64.8)]),
    (r"disappears when you reload", [title("NOT REGISTERED?", "GONE WHEN YOU RELOAD", T2, 30.3)]),
    (r"^Registering costs money", [g(T2, 42.3)]),
    (r"hadn't done enough fence work", [g(L, 38.8), g(T1, 64.3)]),
    (r"trackers come in levels", [card("cards", "TRACKERS::LEVELS=Trackers come in levels|REMOVAL=Black market dealers"
                                                "|UNLOCK IT=Work your way up the fences")]),
    (r"keep your speed up", [card("stats", "ONE REPORT::FAST=Tracker stays quiet|SLOW=Warning sounds")]),
    (r"room for just three cars", [card("garage", "YOUR FIRST GARAGE::3|Coupe|Pickup|Muscle car|Supercar")]),
    (r"^Three\.", [title("THREE", "PARKING SPACES", L, 18.8)]),
    (r"push out of your garage", [g(T2, 120.3), g(T2, 130.8)]),
    (r"rebuilt around information", [title("THE WANTED SYSTEM", "REBUILT AROUND INFORMATION", T2, 108.3)]),
    (r"witness sees it", [card("cards", "HOW POLICE FIND OUT::WITNESS=Someone sees it|VICTIM=Someone reports it"
                                        "|ALARM OR CAMERA=A system catches it")]),
    (r"^No witness, no stars", [title("NO WITNESS", "NO STARS", T1, 47.8)]),
    (r"six star scale", [card("stats", "THE WANTED SCALE::6=Stars are back|+=What sits under them")]),
    (r"Red Dead Redemption 2", [g(T2, 116.8), g(T1, 44.3)]),
    (r"small icon below the wanted level", [card("heat", HEAT4)]),
    (r"camera in the corner", [g(T2, 152.8), g(L, 34.3)]),
    (r"^Believing a pair of sunglasses", [g(T2, 98.3)]),
    (r"piece by piece", [card("heat", HEAT4 + " off=face")]),
    (r"outfit stays on file", [card("heat", HEAT4 + " off=face,outfit")]),
    (r"seen entering", [card("heat", HEAT4 + " off=face,outfit,vehicle")]),
    (r"A mask can keep your face", [g(L, 68.0)]),
    (r"splitting up with your partner during a chase", [g(L, 40.8), g(T2, 106.8)]),
    (r"hid in a bush", [vs(T1, 32.3, "gta5_alley.mp4", 0.0)]),
    (r"plan before the crime starts", [title("HAVE A PLAN", "BEFORE THE CRIME STARTS", T1, 22.3)]),
    (r"once you hit three stars", [g(L, 48.3), g(T1, 24.3)]),
    (r"narrower, the traffic is denser", [card("cards", "WHY CARS FAIL::NARROW STREETS=Less room to weave|DENSE TRAFFIC=More to hit"
                                                        "|ON FOOT=Vanish through the alleys")]),
    (r"first big chase", [g(L, 71.0)]),
    (r"floor it and weave", [title("FLOOR IT AND WEAVE", "MAY KEEP THE STARS ON", L, 72.3)]),
    (r"That's the first half", [title("HALFWAY", "CARS AND COPS DONE", T2, 154.8)]),
    (r"where the game gets mean", [title("NOW THE MONEY", "WHERE THE GAME GETS MEAN", T2, 128.3)]),
    (r"jewelry stores and smaller banks", [g(T1, 68.3), g(T2, 90.3)]),
    (r"^Blow the safe", [card("cards", "THE SAFE::BLOW IT=Fast  ·  part of the loot destroyed|CRACK IT=Slower  ·  pays far more")]),
    (r"fence even texted", [g(T2, 86.3)]),
    (r"potential take", [title("THE POTENTIAL TAKE", "ON THE MAP BEFORE YOU COMMIT", L, 54.3)]),
    (r"trade between speed and profit", [card("stats", "EVERY JOB::SPEED=or|PROFIT=pick one")]),
    (r"^Playing it like a solo game", [g(T2, 100.3)]),
    (r"You control Jason and Lucia", [g(L, 40.3), g(T2, 98.8)]),
    (r"brings the two of them closer", [title("ROB TOGETHER", "GROW CLOSER", T1, 8.3)]),
    (r"mid chase can drop a star", [g(L, 41.6)]),
    (r"escape route, a second pair", [card("cards", "YOUR PARTNER IS::AN ESCAPE ROUTE=Split up, drop a star"
                                                    "|SECOND HANDS=Jobs as a pair|THE STORY=The game keeps track")]),
    (r"sidekick who follows", [g(T2, 114.3)]),
    (r"New York Times", [card("stats", "HOW LONG::80=Hours  ·  one GTA VI run|30=Hours  ·  GTA V story|50-60=Hours  ·  RDR2")]),
    (r"twice the size of GTA 5", [mp(VICE, T1, 10.3)]),
    (r"ten hours straight", [card("download", "ONE DAY  ·  ONE EIGHTH::THURSDAY=10|THE FULL RUN=80")]),
    (r"designed to be wandered", [g(T2, 138.6), g(T1, 20.8)]),
    (r"opening act", [title("DAY ONE", "IS THE OPENING ACT", T2, 8.2)]),
    (r"you don't get cash", [title("LOOT IS NOT MONEY", "", T2, 128.8)]),
    (r"duffel bag", [hud("economy", "focus=bag")]),
    (r"Different fences take different goods", [card("cards", "THE FENCES::CAR FENCE=Takes cars|JEWELRY FENCE=Takes jewelry"
                                                              "|WRONG FENCE=A wasted trip")]),
    (r"damaged car sells for less", [g(L, 52.3)]),
    (r"the loop is steal, escape, fence", [card("loop", "THE LOOP::STEAL|ESCAPE|FENCE|MONEY")]),
    (r"unlocks new abilities", [g(T2, 130.3)]),
    (r"stranger pays you", [title("NOT A SCORE", "UNTIL A STRANGER PAYS YOU", L, 34.8)]),
    (r"missions paid you", [g(T2, 64.3)]),
    (r"Edge magazine reports", [title("EDGE MAGAZINE", "PAUSES BETWEEN STORY MISSIONS", T2, 66.3)]),
    (r"hush money", [card("cards", "CASH PAYS FOR::EQUIPMENT=Gear for the job|HUSH MONEY=Keeping people quiet"
                                   "|BAIL MONEY=Hopefully not")]),
    (r"hasn't published the amounts", [title("THE AMOUNTS", "NOT PUBLISHED", T2, 120.8)]),
    (r"hit a wall", [g(T1, 70.3)]),
    (r"explore, rob and steal", [g(L, 4.3), g(T1, 76.3)]),
    (r"Money in your bank is safe", [hud("cash")]),
    (r"wasted or busted", [card("cards", "LOSE YOUR POCKET CASH::WASTED=You die|BUSTED=You're arrested")]),
    (r"phone app", [title("AN ATM RUN", "A REAL STOP ON EVERY BIG NIGHT", T2, 42.8)]),
    (r"picture your first night", [g(T1, 56.3)]),
    (r"three stars on you", [g(L, 48.8), g(T2, 34.3)]),
    (r"run to the ATM", [title("THE ATM", "OR RUN FOR YOUR LIFE?", L, 68.6)]),
    (r"rob, fence, bank, repeat", [card("loop", "THE RULE FOR NIGHT ONE::ROB|FENCE|BANK")]),
    (r"that's your first day", [card("checklist", "An update|A scanner|Three parking spaces|A face the police remember|"
                                                  "A story that waits for your money")]),
    (r"Tell me in the comments", [title("YOUR FIRST MOVE?", "DEPOSIT  ·  OR LIVE DANGEROUSLY", L, 18.3)]),
    (r"^Subscribe", [title("SUBSCRIBE", "GTA 6 THROUGH LAUNCH WEEK", T2, 6.6)]),
]

POOLS = [
    [(T1, 12.3), (L, 26.8), (T2, 152.3)],
    [(L, 62.3), (T2, 20.8), (L, 8.3)],
    [(L, 47.6), (T2, 28.8), (T1, 54.3)],
    [(T2, 24.8), (L, 46.0), (T1, 66.0)],
    [(T2, 107.6), (T1, 30.3), (L, 69.0)],
    [(T1, 49.0), (T2, 114.8), (L, 64.0)],
    [(L, 70.6), (T1, 24.8), (T2, 34.8)],
    [(L, 52.0), (T2, 92.8), (T1, 68.0)],
    [(L, 40.0), (T2, 98.0), (T1, 8.8)],
    [(T1, 20.0), (T2, 138.2), (L, 12.3), (T2, 140.3)],
    [(T2, 130.0), (L, 34.0), (T1, 76.8)],
    [(T2, 92.0), (T1, 72.3), (L, 30.0)],
    [(T2, 46.0), (L, 60.0), (T1, 68.8)],
]


if __name__ == "__main__":
    B.RANKS, B.RULES, B.POOLS = RANKS, RULES, POOLS
    lines = B.build("day1_script.txt")
    out = ROOT / "gta6_day1_scenes.csv"
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=B.COLS)
        w.writeheader()
        for t, shots in lines:
            for i, s in enumerate(shots):
                w.writerow({"narration": t if i == 0 else "", **{k: s.get(k, "") for k in B.COLS[1:]}})
    unused = [p for k, (p, _s) in enumerate(RULES) if not any(re.search(p, t) for t, _ in lines)]
    print(out, len(lines), "lines; rules never matched:", unused)
