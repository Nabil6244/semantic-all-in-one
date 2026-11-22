"""Writes gta6_money_scenes.csv: '15 Ways to Get Rich in GTA 6, Ranked' (Game Launch style, the user's own voiceover).

money_script.txt is the pasted script split into sentences. A rank shot opens each entry (#15 fishing ... #1 banks).
Every number on screen comes from the script; cards with made-up example amounts (cash, waink, capacity) are not used."""
import csv
import re
from pathlib import Path

from build_cartheft_csv import hud
from build_confirmed_csv import KALAGA, L, PORT, T1, T2, g, mp, title
from build_launchnight_csv import COLS, END, rank

ROOT = Path(__file__).resolve().parent
PL, BK, SH, CC, DJ, TG, PC = ("gta6_plane_steal.mp4", "gta6_bike_night_crash.mp4", "gta6_shark_attack.mp4", "gta6_car_cat_attack.mp4",
                              "gta6_dog_jetski.mp4", "gta6_tiger_death.mp4", "gta6_pet_cat.mp4")
END = {**END, PL: 340.0, BK: 37.0, SH: 104.0, CC: 36.0, DJ: 11.0, TG: 47.0, PC: 19.5}


def card(name, params, clip=T2, at=28.3):
    return hud(name, params, clip, at)


def payout(head, items, clip=T2, at=46.8):
    return {"shot": "payout", "title": head, "subtitle": items, "game_clip": clip, "game_at": at}


def steps(head, items, clip=T2, at=144.3):
    return {"shot": "steps", "title": head, "subtitle": items, "game_clip": clip, "game_at": at}


RANKS = [  # (pattern, name, line, clip, at)
    (r"^Number fifteen,", "FISHING", "You can't sell what you catch", DJ, 0.5),
    (r"^Number fourteen,", "HONEST WORK", "Odd jobs for next to no pay", T2, 20.3),
    (r"^Number thirteen,", "OTHER PEOPLE'S WALLETS", "$70 after a shootout", T2, 84.3),
    (r"^Number twelve,", "OTHER PEOPLE'S TRUNKS", "Loot, not money", L, 46.8),
    (r"^Number eleven,", "SUNKEN TREASURE", "No published price yet", SH, 49.0),
    (r"^Number ten,", "HUNTING", "Confirmed to pay", T2, 10.8),
    (r"^Number nine,", "ROB THE ROBBERS", "Armored-car crews", T2, 144.3),
    (r"^Number eight,", "TAKE THE WHOLE ATM", "168 machines can be towed", T2, 46.8),
    (r"^Number seven,", "THE CORNER STORE", "91 variety stores", PC, 2.0),
    (r"^Number six,", "PAY AND SPRAY", "Sell almost any car", L, 46.8),
    (r"^Number five,", "STEALING TO ORDER", "Moses and Randy", T2, 152.3),
    (r"^Number four,", "THE STORY ITSELF", "Heists and savings targets", PL, 237.0),
    (r"^Number three,", "JEWELRY STORES", "Bags, trunks and fences", T2, 86.3),
    (r"^Number two,", "GANG HIDEOUTS", "Illegal operations", T2, 106.3),
    (r"^Number one,", "BANKS", "$140,000 in ten minutes", T2, 46.8),
]

RULES = [
    # ---- intro
    (r"^One bank\.", [title("$140,000", "ONE BANK  ·  TEN MINUTES", T2, 46.8)]),
    (r"isn't even a story mission", [g(BK, 4.0)]),
    (r"twenty thousand, and one bust", [card("grind", "POCKET CASH CAP::$20,000|THE MOST YOU CAN CARRY|")]),
    (r"built to keep you broke", [g(T2, 114.3)]),
    (r"seventy bucks", [title("$70", "TWO WALLETS AFTER A SHOOTOUT", T2, 84.3)]),
    (r"two thousand times", [card("stats", "THE GAP::$70=two wallets|$140,000=one bank job")]),
    (r"feel poor", [g(L, 6.3)]),
    (r"tens of millions and nothing", [title("GTA V", "TENS OF MILLIONS  ·  NOTHING TO BUY", T1, 60.3)]),
    (r"pocket stops at twenty", [card("checklist", "WHY YOU FEEL POOR/GTA VI AT LAUNCH::POCKET CAPPED AT $20,000|WASTED OR BUSTED WIPES IT|"
                                                   "SKIP A CAB RIDE: +$100|ONE QUESTLINE: SAVE $2,000,000")]),
    (r"where does the money come from", [g(L, 46.8)]),
    (r"fifteen ways to earn", [title("15 WAYS TO EARN", "RANKED  ·  WORTHLESS TO RICH", L, 60.8)]),
    (r"none invented", [title("REAL NUMBERS ONLY", "SINGLE-SOURCE FIGURES FLAGGED", T2, 38.3)]),
    (r"top three", [g(T2, 152.3)]),
    # ---- 15 fishing
    (r"more than a hundred animals", [card("stats", "LEONIDA WILDLIFE::100+=animals and fish|0=you can sell (fishing)")]),
    (r"can't sell what you catch", [title("YOU CAN'T SELL IT", "FISHING SLOWS YOU DOWN", DJ, 4.0)]),
    (r"life on a boat", [g(SH, 2.0)]),
    (r"Dead last", [title("#15  ·  DEAD LAST", "A HOBBY, NOT AN INCOME", T1, 10.8)]),
    # ---- 14 honest work
    (r"Brian Hader", [title("BRIAN HADER", "BOATYARD  ·  SMUGGLING FRONT", T2, 20.3)]),
    (r"cash tips", [g(L, 6.3)]),
    (r"two hundred fifty dollars", [title("$250", "ONE CAR REPAIR CAN WIPE YOUR SAVINGS", T2, 152.3)]),
    (r"rags to riches", [g(T2, 64.3)]),
    (r"buy a cinema", [card("cards", "GTA V LET YOU BUY::CINEMA=Property|CAB COMPANY=Business|GOLF CLUB=Property|STOCK MARKET=Investing")]),
    (r"None of the reviews", [title("NO STOCK MARKET", "NO BUSINESSES TO BUY  ·  PER THE REVIEWS", T2, 90.3)]),
    (r"garages are the only property", [title("GARAGES ONLY", "THE ONLY PROPERTY YOU CAN OWN  ·  THE SIXTH AXIS", T2, 34.0)]),
    # ---- 13 wallets
    (r"glowed on the pavement", [g(T2, 144.3)]),
    (r"two wallets, and walked away", [title("+$70", "GIANT BOMB  ·  TWO WALLETS", T2, 84.3)]),
    (r"^Seventy\.", [title("SEVENTY.", "", L, 12.3)]),
    (r"hold someone up at gunpoint", [g(T2, 106.3)]),
    (r"call it in", [card("heat", "")]),
    (r"lunch money", [card("checklist", "THE GAMBLE/FOR LUNCH MONEY::A WANTED LEVEL|A DESCRIPTION OF YOUR FACE|EVERY DOLLAR IN YOUR POCKET")]),
    # ---- 12 trunks
    (r"break into parked cars", [g(CC, 0.5)]),
    (r"half an hour", [card("checklist", "ONE PARKING LOT/30 MINUTES  ·  SHACKNEWS::WEAPONS + AMMUNITION|CIGARETTES|HATS + SUNGLASSES|"
                                         "A LITTLE CASH|DRUGS")]),
    (r"lucky dip", [g(L, 46.8)]),
    (r"stuff only turns into money", [card("economy", "focus=bag")]),
    # ---- 11 sunken treasure
    (r"teaches you to dive", [g(SH, 35.0)]),
    (r"Nobody has published a number", [title("PRICE: UNKNOWN", "NO OUTLET HAS PUBLISHED ONE", SH, 49.0)]),
    (r"shark attack", [g(SH, 84.0)]),
    (r"water does pay", [g(SH, 60.0)]),
    # ---- 10 hunting
    (r"confirmed to pay", [title("HUNTING PAYS", "CONFIRMED BY PREVIEWS AND REVIEWS", T2, 10.8)]),
    (r"Mount Kalaga", [mp(KALAGA, T1, 70.8)]),
    (r"ride in your trunk", [card("carry", "")]),
    (r"ComicBook", [title("RARE WILDLIFE", "\"BIG BUCKS\"  ·  COMICBOOK", T2, 36.3)]),
    # ---- 9 rob the robbers
    (r"Forbes describes", [g(T2, 144.3)]),
    (r"armored car", [title("ARMORED-CAR CREW", "TAKE THEM OUT  ·  TAKE THE CASH", T2, 84.3)]),
    (r"side with the victims", [card("stats", "TWO WAYS TO PLAY IT::ROB=take the crew's haul|HELP=collect a reward")]),
    (r"police are coming", [card("stars", "")]),
    (r"game decides when", [g(L, 68.0)]),
    # ---- 8 ATM
    (r"four hundred fifty-four", [card("stats", "LEONIDA'S ATMS  ·  SHACKNEWS::454=cash machines|168=can be towed")]),
    (r"free money with one catch", [title("FREE MONEY", "ONE CATCH: THE WANTED SYSTEM", T2, 46.8)]),
    (r"keep your own cash safe", [card("economy", "focus=bank")]),
    (r"halfway", [title("HALFWAY", "FROM HERE IT PAYS IN THOUSANDS", L, 60.8)]),
    # ---- 7 corner store
    (r"emptied the register", [g(PC, 6.0)]),
    (r"ninety-one variety stores", [card("stats", "ROBBABLE STORES  ·  SHACKNEWS::91=variety stores|+=pawn, liquor and gas")]),
    (r"couple thousand dollars a store", [payout("ONE STORE  ·  PREVIEW ESTIMATE", "Variety store, at most=$2,000", PC, 10.0)]),
    (r"changes the take", [g(PC, 13.0)]),
    (r"safe code and you keep everything", [card("safe", "")]),
    (r"wipe the tapes", [card("checklist", "THE CLEAN ROBBERY::KILL THE ALARM|KILL THE CAMERAS|WIPE THE TAPES IN THE SECURITY ROOM")]),
    (r"marked bills, and one review", [title("MARKED BILLS", "DYE PACKS  ·  UNTIL THE STORY GIVES YOU A JAMMER", T2, 106.3)]),
    (r"clothing store", [g(L, 26.3)]),
    # ---- 6 pay and spray
    (r"Los Santos Customs", [g(T2, 152.3)]),
    (r"registers a stolen one", [card("checklist", "PAY AND SPRAY/IN GTA VI::REPAIRS YOUR CAR|REGISTERS A STOLEN ONE|BUYS THE ONES YOU DON'T WANT")]),
    (r"pocket a couple thousand", [payout("SELLING A CAR  ·  SHACKNEWS", "Almost any car, any shop=$2,000", L, 46.8)]),
    (r"daily cap", [card("checklist", "WHY NOT HIGHER/THE CATCHES::OPENS LATER IN THE STORY|DAILY SALES CAP|"
                                      "GAME8: PAYOUT CONSIDERABLY LOWER")]),
    (r"carry trackers", [card("tiers", "")]),
    (r"better the tracker", [g(T2, 34.0)]),
    # ---- 5 stealing to order
    (r"two men to meet", [card("cards", "TWO CONTACTS  ·  GAMESPOT::MOSES=Port Gellhorn · mid-range cars|"
                                         "RANDY=Western Vice City · high-end · key cloning")]),
    (r"Moses in Port Gellhorn", [mp(PORT, T2, 20.3)]),
    (r"list of wanted cars", [g(L, 26.3)]),
    (r"mint shape", [title("MINT CONDITION", "= BONUS", T2, 152.3)]),
    (r"scanning app", [card("checklist", "SCAN FIRST/THE PHONE APP SHOWS::WHAT IT SELLS FOR|WHAT IT COSTS TO REGISTER|"
                                         "WHETHER IT HAS A TRACKER")]),
    (r"grandmother", [g(CC, 29.0)]),
    # ---- 4 the story
    (r"final heist alone", [title("GTA V", "THE FINAL HEIST: TENS OF MILLIONS EACH", T1, 26.3)]),
    (r"biggest paydays are still tied", [g(T2, 74.3)]),
    (r"Donnie", [g(PL, 280.0)]),
    (r"smaller share", [g(PL, 300.0)]),
    (r"Buckme app", [title("BUCKME", "A SAVINGS TARGET EVERY CHAPTER", L, 40.3)]),
    (r"start at a hundred thousand", [card("stats", "FAMILY SAVINGS TARGETS::$100,000=first|$500,000=next|NO=withdrawals")]),
    (r"can't be replayed", [card("archive", "")]),
    (r"windfall", [title("A WINDFALL", "NOT AN INCOME", T2, 64.3)]),
    # ---- 3 jewelry
    (r"top three", [g(T2, 152.3)]),
    (r"estimated take on your map", [title("ESTIMATED TAKE", "SHOWN ON THE MAP BEFORE YOU GO IN", T2, 86.3)]),
    (r"without tripping a single alarm", [g(L, 60.8)]),
    (r"trunk holds six", [card("grind", "A BIG TRUNK::6|DUFFEL BAGS|")]),
    (r"three of them", [card("checklist", "THE FENCES/THREE OF THEM::EACH HAS A SPECIALTY|PRICES MOVE WITH DEMAND|"
                                          "COMPARE BEFORE YOU SELL")]),
    (r"partner can make the sale", [g(L, 40.3)]),
    (r"haven't registered", [title("REGISTER THE CAR", "OR RISK LOSING THE LOOT", T2, 38.3)]),
    # ---- 2 hideouts
    (r"money printer", [title("ILLEGAL OPERATIONS", "THE CLOSEST THING TO A MONEY PRINTER", T2, 106.3)]),
    (r"aren't marked on your map", [card("minimap", "")]),
    (r"Inside there's cash", [card("checklist", "INSIDE A HIDEOUT::CASH + MARKED BILLS|DRUGS + JEWELRY|A RARE GUN|A ONE-OF-A-KIND CAR")]),
    (r"one or two dozen", [card("stats", "HOW HARD?::12-24=enemies (GameSpot)|95%=harder than the campaign (Forbes)")]),
    (r"bring armor", [g(T2, 84.3)]),
    (r"sticky note", [card("checklist", "THE SAFE CODE IS ON::A STICKY NOTE|A COMPUTER SCREEN|ANOTHER HIDEOUT OF THE SAME GANG")]),
    (r"paid almost instantly", [g(T2, 140.3)]),
    (r"PlayStation Universe", [card("quote", "THE VERDICT::Stores and hideouts are the only really good ways to earn.|PlayStation Universe|review")]),
    (r"never worry about money", [g(L, 66.3)]),
    # ---- 1 banks
    (r"best documented payday", [title("THE BANK JOB", "SHACKNEWS  ·  BEST DOCUMENTED PAYDAY", T2, 46.8)]),
    (r"hundred thirty-five thousand", [payout("ESTIMATED TAKE", "Bank in the heart of the city=$135,000", T2, 46.8)]),
    (r"body armor and ammunition", [steps("THE SHACKNEWS BANK JOB", "Body armor and ammo; Second car at a gas station; "
                                          "Follow a guard into the vault; Three bags of marked bills; Out the front on a sport bike; "
                                          "Change clothes and vehicles; Sell the bills", T2, 144.3)]),
    (r"followed a guard", [g(T2, 38.3)]),
    (r"sport bike", [g(BK, 10.0)]),
    (r"change of clothes", [g(BK, 20.0)]),
    (r"hundred forty thousand dollars", [payout("THE PAYOUT", "Marked bills, sold to an associate=$140,000", T2, 46.8)]),
    (r"Ten minutes of work", [title("TEN MINUTES", "$140,000", L, 6.3)]),
    (r"planning board", [g(T1, 26.3)]),
    (r"jammer for dye packs", [card("checklist", "BEFORE YOUR FIRST BANK/YOU NEED::THE STORY'S TOOLS|A JAMMER FOR DYE PACKS|"
                                                 "THE BIG BANKS OPEN LATER")]),
    (r"Treat it like a job", [g(T2, 46.8)]),
    # ---- outro
    (r"that's the ranking", [card("checklist", "THE RANKING::FISHING PAYS NOTHING|STORES PAY THE BILLS|HIDEOUTS KEEP YOU COMFORTABLE|"
                                               "BANKS MAKE YOU RICH")]),
    (r"find an ATM", [card("economy", "focus=bank")]),
    (r"how the story ends", [g(L, 66.3)]),
    (r"Six Vortex", [title("SIX VORTEX", "SUBSCRIBE FOR LAUNCH WEEK", L, 24.3)]),
]

POOLS = [
    [(L, 6.3), (T2, 114.3), (L, 46.8), (T1, 60.3)],            # intro
    [(DJ, 2.0), (SH, 4.0), (T2, 8.2), (T1, 10.8)],             # 15 fishing
    [(T2, 20.3), (L, 6.3), (T2, 90.3), (T2, 64.3)],            # 14
    [(T2, 84.3), (T2, 144.3), (L, 12.3)],                      # 13
    [(L, 46.8), (T2, 152.3), (CC, 2.0), (T1, 70.8)],           # 12
    [(SH, 38.0), (SH, 52.0), (SH, 64.0), (SH, 91.0)],          # 11
    [(T2, 10.8), (T1, 70.8), (T2, 36.3), (TG, 1.0)],           # 10
    [(T2, 144.3), (T2, 84.3), (L, 68.0)],                      # 9
    [(T2, 46.8), (L, 60.8), (T2, 140.3)],                      # 8
    [(PC, 2.0), (PC, 15.0), (T2, 106.3)],                      # 7
    [(L, 46.8), (T2, 34.0), (CC, 29.0), (T2, 152.3)],          # 6
    [(T2, 152.3), (L, 26.3), (CC, 7.0), (BK, 0.5)],            # 5
    [(PL, 194.0), (PL, 280.0), (T2, 74.3), (L, 40.3)],         # 4
    [(T2, 86.3), (L, 60.8), (T2, 38.3)],                       # 3
    [(T2, 84.3), (T2, 106.3), (L, 66.3), (T2, 140.3)],         # 2
    [(T2, 46.8), (BK, 4.0), (BK, 14.0), (T2, 144.3)],          # 1
    [(L, 24.3), (L, 66.3), (T1, 12.8)],                        # outro
]


def sentences():
    text = re.sub(r"\s+", " ", (ROOT / "money_script.txt").read_text(encoding="utf-8")).strip()
    return [s for s in re.split(r"(?<=[.!?])\s+(?=[A-Z\"$])", text) if s.strip()]


def build():
    lines, used, act, pool_i, seen = [], set(), 0, [0] * len(POOLS), []
    for sent in sentences():
        shots = []
        for k, (pat, name, line, clip, at) in enumerate(RANKS):
            if re.search(pat, sent):
                act = k + 1
                shots.append(rank(name, line, clip, at))
        if re.search(r"that's the ranking", sent):
            act = len(POOLS) - 1
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
                seen.append((sh["game_clip"], float(sh["game_at"])))
        lines.append((sent, shots))
    return lines


if __name__ == "__main__":
    out = ROOT / "gta6_money_scenes.csv"
    lines = build()
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        for t, shots in lines:
            for i, s in enumerate(shots):
                w.writerow({"narration": t if i == 0 else "", **{k: s.get(k, "") for k in COLS[1:]}})
    unused = [p for k, (p, _s) in enumerate(RULES) if not any(re.search(p, t) for t, _ in lines)]
    print(out, len(lines), "lines; rules never matched:", unused)
