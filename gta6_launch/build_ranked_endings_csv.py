"""Writes gta6_ranked_endings_scenes.csv: 'Every GTA 6 Ending Ranked, Worst to Best' (Vice Ranked, the user's own voiceover).

ranked_endings_script.txt is the pasted script split into sentences. A chapter card opens the count, each ranked ending (#6 to #1),
the rumors and the replay, so each becomes a Short. Cards say only what the script says and name the outlet (sources:
~/Downloads/Vice_Ranked_GTA6_Endings_Source_Links.csv). Every card plays over trailer footage (no bare navy) and no two cards run
back to back. Trailer seconds are the known shots from build_police_csv.py."""
from pathlib import Path

from build_cartheft_csv import hud
from build_confirmed_csv import L, T1, T2, board, chap, g, timeline, title
from build_map_csv import BK, CC, build, write

ROOT = Path(__file__).resolve().parent
NEWS_HELI, POOL_GATOR, NIGHT_HELI, RAID, PICKUP = (T1, 67.4), (T1, 42.4), (T1, 45.4), (T1, 48.3), (T1, 60.3)
LUCIA_CASH, WRECK, BRIDGE, GATOR2 = (T1, 63.2), (T1, 64.4), (T1, 35.75), (T1, 41.35)
WALL, PRISON, GUARD, LUCIA_OUT, VEST = (T2, 47.4), (T2, 50.3), (T2, 55.3), (T2, 63.4), (T2, 108.4)
COUNTY_HELI, ARMORED, BOAT_RUN, DIRT_BIKE = (T2, 138.4), (T2, 144.4), (T2, 146.4), (T2, 148.3)
CHASE, SHOOTOUT = (L, 47.3), (L, 61.4)
# source-link clips (make_endings_sources.py): ending footage starts at 2:04 of 19HTPoQVd2w; 60-80 s are X-post frames, skip them
END = "gta6_src_ending_footage.mp4"
X_FANS, X_FIVE, X_TWO = "gta6_src_x_moviefans_endings.mp4", "gta6_src_x_kruqia_five_endings.mp4", "gta6_src_x_siddhiman_more_than_two.mp4"
X_2M, X_CL, X_IGN, X_PLUS = ("gta6_src_x_sultan_2m_savings.mp4", "gta6_src_x_cyberleek_has_ending.mp4", "gta6_src_x_ign_cyberleek.mp4",
                             "gta6_src_x_omxr_story_plus.mp4")
SH_ALL, SH_BRIDGE = "gta6_src_short_all_endings.mp4", "gta6_src_short_bridge.mp4"


def C(card, params, p):
    """A card over a trailer shot (blurred behind it)."""
    return hud(card, params, *p)


def ch(t, sub, p):
    return chap(t, sub, *p)


RULES = [
    # ---- cold open
    (r"^One ending in GTA 6 finishes", [g(*POOL_GATOR)]),
    (r"cannot agree whether this game has four", [C("stats", "HOW MANY ENDINGS?::4=The Big Lead|5=GamerBlurb, Detonated|6=ComicBook", CHASE)]),
    (r"^Spoilers ahead", [title("SPOILER WARNING", "FINISH THE STORY FIRST", *BRIDGE)]),
    # ---- the count
    (r"^First, the count", [ch("THE COUNT", "Four, five or six?", NEWS_HELI)]),
    (r"^GamerBlurb and Detonated both list five", [C("cards", "WHO COUNTS WHAT::THE BIG LEAD=4 endings|GAMERBLURB=5 endings|"
                                                               "DETONATED=5 endings|COMICBOOK=6 endings", (L, 62.8))]),
    (r"^Reports published between November 20", [g(X_FANS, 0.0), g(X_FIVE, 0.0)]),
    (r"^Rockstar has not published a number", [g(SH_ALL, 4.0)]),
    (r"^Beebom reports that Rockstar said", [g(X_TWO, 0.0), C("cards", "REPORTED  ·  BEEBOM::ROCKSTAR SAID=A lot more than two conclusions|"
                                                        "FIRST-PARTY SOURCE=Not found", NIGHT_HELI)]),
    (r"called The End of the Road", [title("THE END OF THE ROAD", "THE FINAL MISSION", *CHASE)]),
    (r"police roadblock on a bridge", [g(SH_BRIDGE, 8.0)]),
    (r"^Everything else depends on your criminal", [C("checklist", "WHAT DECIDES YOUR ENDING::YOUR CRIMINAL PROFILE|HOW CLOSE THEY ARE|"
                                                                   "BUCKME FAMILY SAVINGS|A COUPLE OF EARLIER CHOICES", WRECK)]),
    (r"^Careful, low casualty play", [C("cards", "CRIMINAL PROFILE  ·  THE BIG LEAD::CAREFUL=Professional|GUNS BLAZING=Psycho|"
                                                 "EVEN WORSE=Irredeemable", SHOOTOUT)]),
    (r"six ending layout that three outlets", [C("stats", "THE LAYOUT IN THIS VIDEO::6=endings|3=outlets share it", ARMORED)]),
    # ---- #6
    (r"^Number six, the worst", [ch("#6  THE SWAMP", "Secret ending  ·  the worst", POOL_GATOR)]),
    (r"call it Alligator Lunch", [g(*GATOR2)]),
    (r"^If you hold off, wait for the second prompt", [C("checklist", "THE SWAMP PATH::CONFRONT MENDEZ|DON'T TAKE THE SHOOT OPTION|"
                                                                      "WAIT FOR THE SECOND PROMPT|TAKE HIS DEAL", RAID)]),
    (r"only see their skulls", [C("cards", "REPORTED  ·  ONE OUTLET::AFTER THE CREDITS=Only their skulls|THE WINNER=Mendez", GATOR2)]),
    # ---- #5
    (r"^Number five is No Surrender", [ch("#5  NO SURRENDER", "Bonnie and Clyde", SHOOTOUT)]),
    (r"^At the bridge you pick No Surrender", [g(END, 30.0)]),
    (r"^Both of them die in the police ambush", [g(END, 54.0)]),
    (r"^ComicBook says that saving around", [C("stats", "REPORTED  ·  COMICBOOK::$2.5M=saved helps their son", LUCIA_CASH)]),
    # ---- #4
    (r"^Number four is where the sources", [ch("#4  BOTCHED SURRENDER", "The sources disagree", WRECK)]),
    (r"^It is called the Botched Surrender", [g(END, 90.0)]),
    (r"^You pick Swim for It, but a Psycho", [C("cards", "THE CAUSE::YOU PICK=Swim for It|YOUR PROFILE=Psycho or Irredeemable|"
                                                         "THE POLICE=Open fire anyway", CHASE)]),
    (r"^ComicBook says both are shot", [g(END, 138.0)]),
    (r"^The Big Lead says Lucia trades the hard drive", [g(END, 126.0), g(END, 132.0)]),
    (r"^So treat the exact outcome with caution", [g(END, 102.0)]),
    (r"^Of Zen and Computing says one or both", [C("cards", "THREE REPORTED OUTCOMES::COMICBOOK=Both are shot|"
                                                            "THE BIG LEAD=Lucia pardoned, Jason killed|"
                                                            "OF ZEN AND COMPUTING=One or both die", (T2, 139.4))]),
    # ---- #3
    (r"^Number three is Staying Down", [ch("#3  STAYING DOWN", "Bittersweet", PICKUP)]),
    (r"splits off earlier, at a tower standoff", [C("checklist", "THE STAYING DOWN PATH::TAKE MENDEZ'S DEAL|FIGHT OUT OF THE AMBUSH|"
                                                                 "THE TOWER STANDOFF", COUNTY_HELI)]),
    (r"^Lucia takes the government deal", [C("cards", "LUCIA AFTERWARDS::SAVINGS THERE=Back with her son|SAVINGS LOW=Robbing a store",
                                             LUCIA_CASH)]),
    # ---- #2
    (r"^Number two is Prison Sacrifice", [ch("#2  PRISON SACRIFICE", "Years apart", PRISON)]),
    (r"profile below Psycho", [C("cards", "HOW YOU GET IT::AT THE BRIDGE=Swim for It|YOUR PROFILE=Below Psycho", BRIDGE)]),
    (r"^Lucia gets back to Tomas", [g(*GUARD)]),
    # ---- #1
    (r"^Number one is the ending that asks", [ch("#1  LUCIA PAYS JASON'S BAIL", "The best ending", LUCIA_OUT)]),
    (r"^You need the top relationship tier", [C("checklist", "THE BEST ENDING NEEDS::TOP RELATIONSHIP TIER|"
                                                             "PROFESSIONAL OR HARDENED PROFILE|A LARGE BUCKME BALANCE|"
                                                             "SWIM FOR IT AT THE BRIDGE", (T2, 57.3))]),
    (r"^The savings number is where", [g(X_2M, 0.0), C("stats", "THE MONEY  ·  REPORTED::$2M-$3M=savings targets|$2.5M=the bail",
                                                         VEST)]),
    (r"Liberty City reported", [g(*LUCIA_OUT)]),
    (r"^Detonated, which says its own list", [C("cards", "REPORTED  ·  DETONATED::EVERY ENDING=Same post-credit scenes|"
                                                         "ITS OWN LIST=Incomplete", NIGHT_HELI)]),
    (r"^Mattia and Kat have a son", [g(X_FIVE, 2.0)]),
    # ---- rumors
    (r"separate the rumors from the facts", [ch("RUMORS VS FACTS", "A leak target for months", NIGHT_HELI)]),
    (r"^On October 14, Dexerto", [timeline("THE ENDING RUMORS", ["JUN 2025=Rewrite rumor, via Tez2", "OCT 14 2026=Cyberleek's claim",
                                                                  "NOV 19 2026=The game is out"]), g(X_IGN, 0.0)]),
    (r"^That is his claim", [g(X_CL, 0.0)]),
    (r"^Nobody has confirmed the clips", [board(["Clips from the final missions=no", "He holds the ending=no", "Rockstar comment=no"],
                                                *BOAT_RUN, head="CYBERLEEK'S CLAIM")]),
    (r"filing that one under unconfirmed", [C("cards", "THE REWRITE RUMOR::SOURCE=Anonymous, via Tez2|STATUS=Unconfirmed", DIRT_BIKE)]),
    # ---- replay
    (r"^Kotaku reported on November 18", [ch("REPLAY THE FINALE", "Kotaku  ·  Nov 18", CHASE)]),
    (r"returned to that choice", [g(X_PLUS, 0.0)]),
    (r"finale marker stays on the map", [C("minimap", "gta6", BRIDGE)]),
    (r"fifteen manual save slots", [C("stats", "REPORTED  ·  GAMERBLURB::15=manual save slots", (L, 72.3))]),
    (r"^The swamp at six", [C("checklist", "THE FULL RANKING::#6 THE SWAMP|#5 NO SURRENDER|#4 BOTCHED SURRENDER|#3 STAYING DOWN|"
                                           "#2 PRISON SACRIFICE|#1 LUCIA PAYS JASON'S BAIL", LUCIA_OUT)]),
    (r"^Tell me in the comments", [title("VICE RANKED", "WHICH ENDING DID YOU GET?", *BRIDGE)]),
]

POOLS = [
    [CHASE, SHOOTOUT, NEWS_HELI, (L, 62.8)],                     # intro
    [NEWS_HELI, (L, 46.6), BRIDGE, WRECK, SHOOTOUT, (CC, 7.0)],  # the count, the finale, profiles
    [POOL_GATOR, GATOR2, (T1, 20.3), RAID],                      # #6 swamp
    [SHOOTOUT, (L, 62.8), CHASE, (L, 72.3)],                     # #5 no surrender
    [WRECK, (BK, 4.0), (BK, 14.0), CHASE],                       # #4 botched surrender
    [PICKUP, (T1, 61.7), COUNTY_HELI, LUCIA_CASH],               # #3 staying down
    [PRISON, GUARD, (T2, 136.4), WALL],                          # #2 prison
    [LUCIA_OUT, (T2, 57.3), LUCIA_CASH, (T2, 106.4)],            # #1 bail
    [NIGHT_HELI, VEST, BOAT_RUN, DIRT_BIKE],                     # rumors
    [CHASE, BRIDGE, PICKUP, (L, 62.8)],                          # replay
]

if __name__ == "__main__":
    write(ROOT / "gta6_ranked_endings_scenes.csv", build("ranked_endings_script.txt", RULES, POOLS), RULES)
