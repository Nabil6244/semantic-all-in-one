"""Writes gta6_launchnight_scenes.csv: '10 Things That Will Happen on GTA 6 Launch Night' (Game Launch style, countdown).

launchnight_script.txt is split into sentences, one voice line each. Each 'Number N.' sentence gets a rank card (#10 .. #1);
the rules below give the other sentences their graphics (first match wins, each rule used once); a sentence no rule claims
gets the next trailer shot from its entry's pool. New hud cards used here: nodisc, download, scam, unlock."""
import csv
import re
from pathlib import Path

from build_cartheft_csv import hud
from build_confirmed_csv import L, ST, T1, T2, board, g, mp, split, timeline, title
from build_mistakes_csv import sentences

ROOT = Path(__file__).resolve().parent
VICE = "Vice City=Miami@25.77,-80.19"


def rank(name, line, clip, at):
    return {"shot": "rank", "title": name, "subtitle": line, "game_clip": clip, "game_at": at}


def card(t, params):
    return hud(t, params)


RANKS = [  # sentence start -> rank entry
    (r"^Number ten", "THE BOX HAS NO DISC", "A case with a download code", L, 38.3),
    (r"^Number nine", "THE PRICE ARGUMENT", "$79.99 and $99.99", T2, 46.3),
    (r"^Number eight", "NO PC VERSION", "PS5 and Xbox Series X|S only", T1, 66.3),
    (r"^Number seven", "SCAMMERS", "Fake early access, fake betas", T2, 106.3),
    (r"^Number six", "REVIEWS THE DAY BEFORE", "Leaked embargo: Nov 18", L, 60.3),
    (r"^Number five", "SPOILERS AND STREAMS", "The story leaks in hours", T1, 52.3),
    (r"^Number four", "THE CLOCK TRICK FAILS", "Region decides, not the clock", L, 70.3),
    (r"^Number three", "LAUNCH NIGHT ON WEDNESDAY", "Some US stores: 11 p.m. Central", T2, 152.3),
    (r"^Number two", "NO SINGLE MIDNIGHT", "15 windows, nearly 19 hours", T1, 20.3),
    (r"^And number one", "212 GIGABYTES", "The download decides your night", L, 0.6),
]

RULES = [  # (pattern, shots) - first match wins, each used once
    (r"^By the time GTA 6 unlocks", [title("GTA 6 LAUNCH NIGHT", "10 THINGS THAT WILL HAPPEN", T2, 154.3),
                                     mp("Auckland=New Zealand@-36.85,174.76", T1, 2.3)]),
    (r"one number that decides", [title("ONE NUMBER", "DECIDES YOUR MIDNIGHT", L, 46.3), g(L, 26.3)]),
    (r"buried in the store listings", [g(T2, 28.3), g(T1, 54.3)]),
    (r"counting down ten things", [card("cards", "THE COUNTDOWN::SMALL STUFF=Numbers ten to six|YOUR NIGHT=Numbers five to two"
                                                 "|THE BIG ONE=Number one can wreck it all")]),
    (r"^The box has no disc", [card("nodisc", "WHAT IS IN THE BOX::STANDARD EDITION  ·  $79.99")]),
    (r"physical edition of GTA 6 is a case", [card("cards", "TWO EDITIONS::STANDARD=$79.99  ·  boxed case with a code inside"
                                                            "|ULTIMATE=$99.99  ·  digital only")]),
    (r"Thirteen years ago, GTA 5", [title("2013", "GTA V  ·  THE GAME WAS ON THE DISC", real=ST + "pexels_3770584.mp4", real_at=2.0),
                                    g(T1, 32.3)]),
    (r"very expensive receipt", [g(L, 40.3), title("A VERY EXPENSIVE RECEIPT", "THE BOX JUST STARTS A DOWNLOAD", T2, 30.3)]),
    (r"^Remember that", [g(L, 18.8)]),
    (r"price argument comes back", [g(T2, 42.3)]),
    (r"\$79\.99 for Standard", [card("stats", "THE PRICE::$79.99=Standard Edition|$99.99=Ultimate Edition")]),
    (r"fair for thirteen years", [card("cards", "THE COMMENT SECTION::FAIR=Thirteen years of waiting|TOO MUCH=$100 for a game")]),
    (r"mostly noise", [g(T2, 18.3), g(L, 64.3)]),
    (r"nothing says you have to buy", [g(T1, 68.3)]),
    (r"Friday morning", [title("IT WILL STILL BE THERE", "FRIDAY MORNING", T2, 132.3)]),
    (r"^There is no PC version", [title("NO PC VERSION", "NOT ANNOUNCED", T1, 49.5)]),
    (r"PlayStation 5 and Xbox Series", [board(["PlayStation 5=yes", "Xbox Series X and S=yes", "PC=no"], T2, 20.3, "WHERE YOU CAN PLAY")]),
    (r"early 2027", [timeline("PC  ·  ONLY RUMORS", ["NOV 19 2026=Consoles", "EARLY 2027=PC rumor"])]),
    (r"huge part of the audience", [g(T2, 24.3), g(T2, 64.3)]),
    (r"desperation", [g(L, 68.6)]),
    (r"Malwarebytes", [title("SECURITY WARNING", "FAKE VIP EARLY ACCESS  ·  PAID IN CRYPTO", T1, 47.8), g(T1, 64.3)]),
    (r"GTA Mobile 6", [card("cards", "THE FAKES::VIP EARLY ACCESS=A few hundred dollars in crypto|BETA KEYS=There is no beta"
                                     "|GTA MOBILE 6=A fake download")]),
    (r"tells are always the same", [card("scam", "")]),
    (r"^Here is the simple version", [g(T2, 116.8)]),
    (r"announced no beta", [board(["Beta=no", "Early access=no", "Mobile version=no"], T1, 66.8, "WHAT ROCKSTAR ANNOUNCED")]),
    (r"it is a trap", [title("IT IS A TRAP", "CRYPTO PAYMENTS DON'T COME BACK", L, 52.8)]),
    (r"only places to buy", [card("checklist", "PlayStation Store|Xbox Store|A real retailer")]),
    (r"embargo lifts", [timeline("REVIEW WEEK  ·  REPORTED", ["END OF OCT=Review codes", "NOV 18=Reviews", "NOV 19 2026=Launch"])]),
    (r"treat it as a leak", [title("NOT CONFIRMED", "TREAT IT AS A LEAK", T2, 108.3)]),
    (r"one evening to read the verdicts", [g(L, 34.3)]),
    (r"97 on Metacritic", [card("stats", "THE BAR TO BEAT::97=GTA V Metacritic|98=GTA IV Metacritic|?=GTA VI")]),
    (r"disappointment by somebody", [g(T2, 92.3), g(T1, 72.3)]),
    (r"first half of the list", [title("HALFWAY", "NONE OF IT IS DANGEROUS  ·  YET", T2, 154.8)]),
    (r"stop being trivia", [g(L, 72.3)]),
    (r"unlocks in waves", [mp("all", T1, 10.3)]),
    (r"my prediction, not a fact", [title("PREDICTION", "NOT A FACT", T1, 22.3)]),
    (r"first mission will be clipped", [timeline("HOW FAST IT LEAKS", ["HOUR 1=First mission clips", "DAY 1-2=The ending"])]),
    (r"mute the character names", [card("checklist", "Mute the character names|Mute the game's title|"
                                                    "Stay off social media until you get there")]),
    (r"changing the time or the region", [g(T2, 66.3)]),
    (r"country or region controls", [card("cards", "WHAT DECIDES UNLOCK::ACCOUNT REGION=Picks your store listing"
                                                    "|CONSOLE CLOCK=Does not move the unlock")]),
    (r"^So skip the tricks", [g(L, 48.3)]),
    (r"Risking your account", [title("A BAD TRADE", "YOUR ACCOUNT FOR A FEW HOURS", T2, 108.8)]),
    (r"11 PM Central", [timeline("SOME US LISTINGS  ·  REPORTED", ["NOV 18=11 p.m. Central", "NOV 19 2026=Midnight local"])]),
    (r"boring one", [g(T2, 100.3)]),
    (r"read the countdown for your own region", [card("checklist", "Open your store page in launch week|"
                                                                   "Read the countdown for your region|Ignore screenshots in your feed")]),
    (r"63 countries", [card("unlock", "THERE IS NO SINGLE MIDNIGHT::15|19|New Zealand|Mexico & Central America")]),
    (r"built from the store data", [title("FROM THE STORE DATA", "NOT ANNOUNCED BY ROCKSTAR", L, 30.8)]),
    (r"every time zone gets its own launch", [mp("Auckland=New Zealand@-36.85,174.76", L, 54.3)]),
    (r"player in Auckland", [split(T1, 3.4, ST + "pexels_3770584.mp4", 0.0, "AUCKLAND · PLAYING", "YOU · EATING DINNER")]),
    (r"piling up for most of a day", [g(T2, 126.3), g(L, 71.0)]),
    (r"decides your night\. 212", [title("212 GB", "THE MOST THE PRELOAD NEEDS", L, 0.6)]),
    (r"most space Rockstar says", [g(T2, 46.8)]),
    (r"Preload opened on November 10th", [timeline("PRELOAD", ["NOV 10=Preload opens", "NOV 19 2026=Unlock"])]),
    (r"do the math", [g(L, 62.3)]),
    (r"On a 100 megabit", [card("download", "212 GB  ·  HOW LONG IT TAKES::100 MBPS=4.7|50 MBPS=9.4|25 MBPS=18.8")]),
    (r"servers keep up", [g(T1, 56.3), g(L, 40.8)]),
    (r"would not be shocked", [title("DAY ONE PATCH?", "NOT ANNOUNCED", T2, 128.3)]),
    (r"leave yourself a margin", [card("checklist", "Leave a margin on space|Use a wired connection|"
                                                   "Check your free space tonight|Start early: deleting takes time")]),
    (r"rest mode", [title("START IT NOW", "LEAVE THE CONSOLE IN REST MODE", T1, 70.3)]),
    (r"own it at midnight", [g(T2, 152.8)]),
    (r"comes down to a progress bar", [title("IT COMES DOWN TO", "A PROGRESS BAR", L, 46.8)]),
    (r"That is launch night", [card("cards", "LAUNCH NIGHT::NO DISC=Just a code|NO SINGLE MIDNIGHT=15 windows"
                                             "|THE DOWNLOAD=Decides everything")]),
    (r"Thursday, November 19th", [title("GTA VI", "THURSDAY  ·  NOVEMBER 19", T2, 154.3)]),
    (r"Tell me in the comments", [title("WHERE WILL YOU BE?", "PRELOADED  ·  OR CUTTING IT CLOSE", L, 18.3)]),
    (r"^Subscribe", [title("SUBSCRIBE", "LAUNCH WEEK  ·  EVERY DAY", T2, 6.6)]),
]

POOLS = [  # fallback trailer shots per entry (0 = intro, 1 = #10 ... 10 = #1)
    [(T1, 2.3), (T1, 12.3), (L, 26.3), (T2, 152.3)],
    [(L, 38.8), (T2, 28.3), (L, 46.3)],
    [(T2, 42.8), (T2, 18.3), (L, 64.8)],
    [(T1, 66.8), (T2, 24.3), (L, 68.0)],
    [(T2, 106.8), (L, 52.3), (T1, 64.3)],
    [(L, 60.8), (T2, 90.3), (T1, 76.3)],
    [(T1, 52.8), (T2, 98.3), (L, 8.3), (T2, 114.3)],
    [(L, 73.0), (T2, 34.3), (T1, 44.3)],
    [(T2, 138.6), (L, 12.3), (T1, 30.3)],
    [(T1, 20.8), (T2, 86.3), (L, 4.8)],
    [(L, 34.8), (T2, 120.3), (T1, 68.8), (T2, 130.3), (L, 66.3)],
]


END = {L: 74.0, T1: 75.0, T2: 154.0}   # last usable second before each trailer's end cards


def build(script="launchnight_script.txt"):
    lines, used, entry, pool_i, seen = [], set(), 0, [0] * len(POOLS), []
    for sent in sentences((ROOT / script).read_text(encoding="utf-8")):
        shots = []
        for k, (pat, name, sub, clip, at) in enumerate(RANKS):
            if re.search(pat, sent):
                entry = k + 1
                shots.append(rank(name, sub, clip, at))
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
            pool = POOLS[entry]
            clip, at = pool[pool_i[entry] % len(pool)]
            pool_i[entry] += 1
            shots.append(g(clip, at + 0.4 * (pool_i[entry] // len(pool))))
        for sh in shots:                       # a plain trailer shot never lands on a moment already used: step past it
            if sh.get("shot") == "game":
                while any(c == sh["game_clip"] and abs(a - float(sh["game_at"])) < 1.6 for c, a in seen):
                    nxt = round(float(sh["game_at"]) + 1.7, 1)
                    sh["game_at"] = nxt if nxt < END.get(sh["game_clip"], 1e9) else round(6.3 + nxt % 7, 1)
            if sh.get("game_clip") and sh.get("game_at") not in ("", None):
                seen.append((sh["game_clip"], float(sh["game_at"])))
        lines.append((sent, shots))
    return lines


COLS = ["narration", "shot", "game_clip", "game_at", "real", "real_at", "left", "right", "title", "subtitle", "place"]

if __name__ == "__main__":
    out = ROOT / "gta6_launchnight_scenes.csv"
    lines = build()
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        for text, shots in lines:
            for i, s in enumerate(shots):
                w.writerow({"narration": text if i == 0 else "", **{k: s.get(k, "") for k in COLS[1:]}})
    unused = [p for k, (p, _s) in enumerate(RULES) if not any(re.search(p, t) for t, _ in lines)]
    print(out, len(lines), "lines; rules never matched:", unused)
