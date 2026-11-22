"""Writes gta6_blackout_scenes.csv: 'What If GTA 6 Launch Night Blacked Out Your City' (Game Launch style, the user's voiceover).

blackout_script.txt is the pasted script split into sentences. Each hour of the night opens with a chapter card (so each becomes
a Short); the real blackouts (Chile, Spain, Pakistan, India, Texas, 2003) play over real Pexels footage with their numbers."""
from pathlib import Path

from build_cartheft_csv import hud
from build_confirmed_csv import L, T1, T2, chap, g, real, timeline, title
from build_map_csv import BK, PL, build, write

ROOT = Path(__file__).resolve().parent
S = "footage/stock/px_"
DARK, LINES, SUB, TORCH, CROWD, HELI = (S + "city_blackout_night.mp4", S + "power_lines_high_voltage.mp4", S + "electrical_substation.mp4",
                                        S + "dark_apartment_hallway_flashlight.mp4", S + "crowd_street_night_phones.mp4",
                                        S + "helicopter_night_city.mp4")
TOWER, TAP, LIGHTS, METRO, ATM, DC = (S + "cell_tower.mp4", S + "kitchen_faucet_water.mp4", S + "traffic_light_night.mp4",
                                      S + "metro_train_tunnel.mp4", S + "atm_machine.mp4", S + "data_center_servers.mp4")
SNOW, ICE, FRIDGE, CTRL, ON, PAD = (S + "snow_storm_texas.mp4", S + "frozen_power_lines_ice.mp4", S + "fridge_open_kitchen.mp4",
                                    S + "power_control_room.mp4", S + "city_lights_turning_on.mp4", S + "loading_screen_gaming.mp4")
FAM, BANK, NZ, CANDLE, PLAY = (S + "video_game_controller_dark_room.mp4", S + "power_bank_phone_charging.mp4",
                               S + "new_zealand_city_night.mp4", S + "candles_dark_room.mp4", S + "playing_video_games_night.mp4")


def hour(clock, name, clip, at=2.0):
    return {"shot": "chapter", "title": clock, "subtitle": name, "real": clip, "real_at": at}


def over(t, sub, clip, at=2.0):
    return title(t, sub, real=clip, real_at=at)


RULES = [
    # ---- cold open
    (r"^Midnight, November nineteenth", [over("12:00 AM", "NOVEMBER 19  ·  GTA 6 UNLOCKS", PLAY, 1.0)]),
    (r"seven minutes later every light", [real(DARK, 1.0), hud("download", "12:07 AM  ·  FROZEN::YOUR PS5=0.8")]),
    (r"whispers one number", [real(TORCH, 1.0), hud("stats", "THE HALLWAY::80%=your PS5|82%=your neighbor's")]),
    (r"could take down a power grid", [hud("checklist", "BY THE END/YOU'LL KNOW::COULD GTA 6 TAKE DOWN A GRID?|"
                                                        "3 CHEAP FIXES FOR LAUNCH NIGHT")]),
    (r"^Picture it", [title("THE MOVIE VERSION", "PICTURE IT", T1, 26.8)]),
    (r"^You grab your phone, flashlight on", [real(TORCH, 4.0)]),
    (r"^Downstairs, the street is packed", [real(CROWD, 1.0)]),
    (r"climbs a bus shelter", [g(T1, 26.8)]),
    (r"toy lightsaber", [real(LIGHTS, 1.0)]),
    (r"marches on the power company", [g(T1, 30.3)]),
    (r"news helicopter circles", [real(HELI, 1.0)]),
    (r"a kid yells a sentence", [g(L, 62.3)]),
    (r"We waited thirteen years", [hud("quote", "ON EVERY NEWS CHANNEL::We waited thirteen years. We can wait for the electricity.|"
                                                "A kid in the crowd|The movie version")]),
    (r"^Okay, that's the movie version", [over("THE REAL ONE", "NIGHTS LIKE THIS ALREADY HAPPENED", DARK, 3.0)]),
    (r"from Delhi to Santiago to New York", [hud("cards", "ONE NIGHT, HOUR BY HOUR::DELHI=2012|SANTIAGO=2025|NEW YORK=2003")]),
    # ---- 12:07 the click
    (r"^Twelve oh seven", [hour("12:07 AM", "The click", LINES, 2.0)]),
    (r"power grid is a balancing act", [real(SUB, 2.0)]),
    (r"electricity going in has to match", [hud("cards", "EVERY SECOND::IN=Power made|OUT=Power used|MUST MATCH=Or it trips")]),
    (r"one shutdown can trigger the next", [hud("loop", "THE CHAIN REACTION::ONE LINE FAILS|THE BALANCE BREAKS|"
                                                         "PARTS SHUT DOWN|THE NEXT ONE TRIPS")]),
    (r"^In February 2025, a single high-voltage line", [hud("stats", "CHILE · FEBRUARY 2025::1=high-voltage line failed|"
                                                                     "~90%=of the country in the dark")]),
    (r"Spain lost fifteen gigawatts", [hud("stats", "SPAIN · APRIL 2025::15 GW=lost in five seconds|60%=of what it was using")]),
    (r"your entire city just went dark", [real(DARK, 6.0)]),
    # ---- 12:08 console
    (r"^Twelve oh eight", [hour("12:08 AM", "Your console", FAM, 1.0)]),
    (r"^The screen doesn't fade", [real(PAD, 1.0)]),
    (r"loses power mid-download", [hud("checklist", "PS5 · POWER CUT MID-DOWNLOAD::DOESN'T SAVE ITS PLACE|"
                                                     "\"NOT SHUT DOWN PROPERLY\" WARNING")]),
    (r"Safe Mode option called Rebuild Database", [{"shot": "steps", "title": "SONY'S FIX · STUCK INSTALL",
                                                    "subtitle": "Start in Safe Mode; Pick Rebuild Database; It re-scans the drive; "
                                                                "Your games stay", "game_clip": T2, "game_at": 34.0}]),
    (r"^And your actual GTA 6 progress", [title("YOUR PROGRESS?", "NONE YET", T2, 6.8)]),
    (r"seven minutes in, buddy", [g(T2, 8.2)]),
    # ---- 12:15 phones
    (r"^Twelve fifteen", [hour("12:15 AM", "The phones", TORCH, 6.0)]),
    (r"cell tower at the end of the street", [real(TOWER, 2.0)]),
    (r"backup batteries that last a few hours", [hud("cards", "THE CELL TOWER::BACKUP BATTERY=A few hours|SOMETIMES=Less")]),
    (r"more than half of mobile users", [hud("stats", "SPAIN · THE WORST MOMENT::50%+=of mobile users, no signal|HOURS=to reach family")]),
    (r"group chat goes silent", [g(L, 40.3)]),
    # ---- 12:40 the tap
    (r"^Twelve forty", [hour("12:40 AM", "The tap", TAP, 1.0)]),
    (r"Pakistan in January 2023", [hud("stats", "PAKISTAN · JANUARY 2023::220 M=people hit|~1 DAY=to bring the grid back")]),
    (r"pumps that push it through the pipes", [hud("cards", "WHY THE TAP STOPS::THE PUMPS=Run on electricity|NO POWER=No water")]),
    (r"quietly plugged into that wall", [real(FRIDGE, 2.0)]),
    # ---- 1 am streets
    (r"^One a\.m\.", [hour("1:00 AM", "The streets", LIGHTS, 3.0)]),
    (r"^Traffic lights are dead", [real(LIGHTS, 6.0)]),
    (r"^The metro has stopped", [real(METRO, 2.0)]),
    (r"India suffered the biggest blackout", [hud("stats", "INDIA · JULY 2012::620 M=people lost power|BIGGEST=blackout in history")]),
    (r"Delhi's metro had to walk passengers", [real(METRO, 6.0)]),
    (r"state of emergency and a nighttime curfew", [hud("checklist", "CHILE · 2025::STATE OF EMERGENCY|NIGHTTIME CURFEW|"
                                                                     "SOLDIERS IN THE STREETS")]),
    (r"^ATMs went dark there too", [real(ATM, 1.0)]),
    (r"goes completely still", [real(DARK, 10.0)]),
    # ---- 3 am rest of world
    (r"^Three a\.m\.", [hour("3:00 AM", "The rest of the world keeps playing", NZ, 2.0)]),
    (r"^A blackout is local", [title("A BLACKOUT IS LOCAL", "THE SERVERS AREN'T", T1, 36.3)]),
    (r"live in data centers", [real(DC, 1.0)]),
    (r"^It's just not online for you", [g(T2, 114.3)]),
    (r"midnight local time", [hud("unlock", "MIDNIGHT LOCAL TIME::13|19|New Zealand|The UK")]),
    (r"posting the first mission", [hud("checklist", "WHILE YOU SIT IN THE DARK::THE FIRST MISSION|THE FIRST CAR|THE FIRST ENDING")]),
    (r"spoilers will be waiting", [real(NZ, 6.0)]),
    (r"stops being an inconvenience", [over("THE NEXT HOUR", "WHERE IT STOPS BEING FUNNY", DARK, 14.0)]),
    # ---- 4 am cold
    (r"^Four a\.m\.", [hour("4:00 AM", "The cold", SNOW, 2.0)]),
    (r"winter storm hit Texas", [real(ICE, 2.0), hud("stats", "TEXAS · FEBRUARY 2021::4 M+=customers lost power|DAYS=in freezing cold")]),
    (r"two hundred forty-six deaths", [hud("stats", "TEXAS HEALTH OFFICIALS::246=deaths linked to the storm")]),
    (r"nothing to do with video games", [real(SNOW, 8.0)]),
    (r"finding every blanket", [real(CANDLE, 2.0)]),
    # ---- 6 am fridge
    (r"^Six a\.m\.", [hour("6:00 AM", "The fridge", FRIDGE, 1.0)]),
    (r"power bank is the most valuable", [real(BANK, 1.0)]),
    (r"^History gives us a range", [timeline("HOW LONG IT LASTS", ["2003=Northeast US + Canada · about a day",
                                                                   "2025 SPAIN=99% back by 7 the next morning",
                                                                   "2025 CHILE=90% of homes back overnight"])]),
    (r"^In August 2003", [hud("stats", "NORTHEAST US + CANADA · AUGUST 2003::55 M=people hit|1=software bug in an alarm")]),
    (r"software bug in a control-room alarm", [real(CTRL, 2.0)]),
    (r"restart a collapsed system piece by piece", [hud("loop", "THE RESTART::ONE PLANT|ONE LINE|ONE CITY|THE NEXT PIECE")]),
    (r"ninety-nine percent of Spain's demand", [hud("cards", "THE COMEBACK::SPAIN=99% by 7 the next morning|CHILE=90% of homes overnight")]),
    (r"^It's what happens the moment the lights", [real(ON, 1.0)]),
    # ---- 7 am second wave
    (r"^Seven a\.m\.", [hour("7:00 AM", "The second wave", ON, 4.0)]),
    (r"millions of devices wake up", [hud("checklist", "EVERY DEVICE, THE SAME SECOND::LOG IN|FINISH THE DOWNLOAD|"
                                                        "GRAB THE DAY-ONE UPDATE")]),
    (r"GTA Online launched in October 2013", [timeline("WHEN SERVERS SWEAT", ["OCT 2013=GTA Online · days of failed logins",
                                                                              "AFTER=Rockstar pays players in-game cash",
                                                                              "DEC 25 2014=PSN and Xbox Live knocked offline"])]),
    (r"^On Christmas Day 2014", [real(DC, 5.0)]),
    (r"stuck in a queue anyway", [g(L, 6.3)]),
    # ---- the big question
    (r"^Now, the big question", [chap("THE BIG QUESTION", "Could GTA 6 cause a blackout?", T1, 36.8)]),
    (r"extremely unlikely", [title("EXTREMELY UNLIKELY", "HERE'S WHY", T2, 40.3)]),
    (r"few old light bulbs", [hud("cards", "ONE PS5 IN A BIG GAME::POWER DRAW=About a few old light bulbs")]),
    (r"one time zone at a time", [hud("unlock", "ONE ZONE AT A TIME::13|19|New Zealand|The UK")]),
    (r"^Offices are closed", [real(DARK, 18.0)]),
    (r"what actually caused those blackouts", [hud("cards", "THE REAL CAUSES::CHILE=A failed line|TEXAS=Frozen plants|"
                                                            "OHIO=A software bug|INDIA=A grid past its limits")]),
    (r"^None of them was caused by people", [real(PLAY, 4.0)]),
    (r"quietly protecting the grid", [real(NZ, 10.0)]),
    (r"the ordinary kind", [real(LINES, 6.0)]),
    # ---- three fixes
    (r"^Three things\.", [chap("3 CHEAP FIXES", "Protect your launch night", T2, 154.3)]),
    (r"download is completely finished", [hud("download", "FIX 1 · FINISH IT FIRST::212 GB=1.0")]),
    (r"surge protector", [hud("checklist", "FIX 2/THE SURGE::A SURGE PROTECTOR|STORM? UNPLUG IT")]),
    (r"surge is the part that can actually hurt", [real(LINES, 10.0)]),
    (r"charged power bank next to the couch", [real(BANK, 4.0), hud("checklist", "FIX 3/NEXT TO THE COUCH::A CHARGED POWER BANK")]),
    (r"only thing that should go dark is your room", [real(PLAY, 8.0)]),
    (r"what's your plan if the power cuts out", [title("YOUR PLAN?", "WAIT IT OUT  ·  OR GO TO SLEEP", T2, 154.3)]),
    (r"I'm Six Vortex", [title("SIX VORTEX", "SEE YOU IN LEONIDA", T1, 35.75)]),
]

POOLS = [
    [(T1, 26.3), (L, 18.8), (T1, 46.3)],          # intro
    [(T1, 18.8), (L, 26.3)], [(T2, 6.8), (L, 60.3)], [(L, 40.3), (T1, 43.95)], [(T2, 90.3), (L, 4.3)],
    [(BK, 4.0), (BK, 14.0), (T1, 28.3)], [(T1, 36.3), (T2, 114.3)], [(T2, 82.3), (T1, 63.65)], [(T2, 20.3), (L, 10.3)],
    [(L, 66.3), (T2, 64.3)], [(T1, 10.3), (T2, 35.5), (PL, 194.0)], [(T2, 154.3), (L, 24.3)],
]

if __name__ == "__main__":
    write(ROOT / "gta6_blackout_scenes.csv", build("blackout_script.txt", RULES, POOLS), RULES)
