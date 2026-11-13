"""Friend batch CSVs for the War footage library: real-footage batches (YouTube) and a Flow batch (AI) for subjects the library lacks.

    python -m cinematic_explainer.war.friend_batches <out dir>

Writes friend_batch_H/, friend_batch_I/ and friend_flow6/, each with the War page CSV (timed, library_name column), the same list as a
normal-style Visual plan CSV and a silent voice-over. Zip the folders (with a HOW_TO_RUN.txt) and send them; when the friend sends the
assets back, run library.py import + approve. Real subjects get 4 rows with different searches: about 1 in 4 YouTube clips passes review.
Edit H / I / FLOW for the next batch (subjects the library report or the last import found missing)."""
import csv
import subprocess
import sys
from pathlib import Path

SEG = 8.0
TAIL = "one continuous shot, no text, no flags, no insignia, no logos"

# subject: (sentence with a named place, [search alternatives]) -> 4 rows each, the alternatives rotate
H = {
    "himars_launch": ("HIMARS launchers fired rockets in Ukraine.", ["M142 HIMARS rocket launch", "HIMARS firing 4K", "HIMARS launch slow motion", "M142 HIMARS live fire exercise"]),
    "iskander_launch": ("A Russian Iskander missile was launched from Russia.", ["Russian Iskander-M missile launch", "Iskander launcher exercise", "Iskander missile launch close up", "Iskander-M launcher vehicle"]),
    "s400_launcher": ("Russian S-400 launchers stood guard in Crimea.", ["Russian S-400 Triumf launcher", "S-400 missile launch exercise", "S-400 launcher raising missiles", "S-400 air defence system deployment"]),
    "bayraktar_tb2": ("Ukrainian Bayraktar TB2 drones flew over Ukraine.", ["Ukrainian Bayraktar TB2 drone flight", "Bayraktar TB2 takeoff", "Bayraktar TB2 landing runway", "Bayraktar TB2 flying 4K"]),
    "ka52_helicopter": ("Russian Ka-52 helicopters flew low over Zaporizhzhia.", ["Russian Ka-52 Alligator helicopter flying", "Ka-52 helicopter rockets launch", "Ka-52 low flight", "Ka-52 Alligator takeoff"]),
    "tu95_bomber": ("Russian Tu-95 bombers took off from Engels air base.", ["Russian Tu-95 bomber takeoff", "Tu-95MS bomber flight", "Tu-22M3 bomber takeoff", "Tu-160 bomber flight"]),
    "su34_jet": ("A Russian Su-34 took off from an airfield in Russia.", ["Russian Su-34 takeoff", "Su-34 fighter bomber flight", "Su-34 afterburner takeoff", "Su-34 flying low"]),
    "leopard_tank": ("Leopard 2 tanks drove to the front in Ukraine.", ["Leopard 2 tank driving", "Leopard 2A6 tank Ukraine", "Leopard 2 tank firing", "Leopard 2A4 tank column"]),
    "bradley_ifv": ("Bradley fighting vehicles moved through Ukraine.", ["M2 Bradley fighting vehicle driving", "Bradley IFV Ukraine", "Bradley fighting vehicle firing", "Bradley IFV convoy"]),
    "f16_jet": ("F-16 jets took off from an air base in Ukraine.", ["F-16 takeoff afterburner", "F-16 fighter jet Ukraine", "F-16 landing runway", "F-16 flying 4K"]),
    "howitzer_firing": ("Ukrainian artillery fired near Bakhmut.", ["M777 howitzer firing", "2S19 Msta howitzer firing", "howitzer firing slow motion", "self propelled howitzer firing"]),
    "storm_shadow_missile": ("Storm Shadow missiles were fired at Crimea.", ["Storm Shadow missile test launch", "Storm Shadow missile flight", "SCALP missile test", "Storm Shadow Su-24 Ukraine"]),
    "neptune_missile": ("A Ukrainian Neptune missile was launched near Odesa.", ["Ukrainian Neptune missile launch", "R-360 Neptune test launch", "Neptune missile launcher truck", "Long Neptune missile launch"]),
    "shahed_drone": ("Shahed drones flew towards Kyiv.", ["Shahed 136 drone flying", "Geran-2 drone launch", "Shahed drone launch rack", "Shahed drone in flight"]),
    "magura_sea_drone": ("Ukrainian sea drones sped across the Black Sea near Crimea.", ["Ukrainian Magura V5 sea drone", "Ukrainian naval drone speeding", "Ukrainian sea drone camera approach ship", "Sea Baby naval drone"]),
    "mig31_kinzhal": ("A Russian MiG-31 carried a Kinzhal missile over Russia.", ["Russian MiG-31 Kinzhal", "MiG-31K Kinzhal flight", "MiG-31 takeoff afterburner", "Kinzhal missile launch"]),
}
I = {
    "sevastopol_bay": ("Warships lay at anchor in Sevastopol bay.", ["Sevastopol bay warships", "Sevastopol harbour drone 4K", "Sevastopol embankment warships", "Sevastopol naval base aerial"]),
    "odesa_port": ("Ships waited in the port of Odesa.", ["Odesa port aerial", "Odesa seaport drone 4K", "Odesa grain ship port", "Odesa harbour cranes"]),
    "novorossiysk_port": ("Warships sailed out of Novorossiysk.", ["Novorossiysk naval base warships", "Novorossiysk port aerial", "Novorossiysk bay drone 4K", "Novorossiysk harbour ships"]),
    "kharkiv_city": ("Smoke rose over Kharkiv.", ["Kharkiv city drone 4K", "Kharkiv city aerial", "Kharkiv Freedom Square aerial", "Kharkiv streets"]),
    "bakhmut_ruins": ("Bakhmut lay in ruins.", ["Bakhmut ruins drone footage", "Bakhmut destroyed city aerial", "Bakhmut streets destroyed", "Avdiivka ruins drone"]),
    "zaporizhzhia_npp": ("The Zaporizhzhia nuclear plant stood by the Dnipro in Enerhodar.", ["Zaporizhzhia nuclear power plant aerial", "Zaporizhzhia nuclear plant drone", "Enerhodar nuclear plant cooling", "Zaporizhzhia NPP reactors"]),
    "kherson_dnipro": ("The Dnipro river divided Kherson.", ["Kherson Dnipro river aerial", "Antonivskyi bridge Kherson", "Kherson city drone 4K", "Dnipro river Kherson bank"]),
    "ammo_depot_explosion": ("An ammunition depot exploded in Crimea.", ["ammunition depot explosion", "arsenal explosion fireball", "ammo depot explosions night", "ammunition warehouse blast"]),
    "ship_hit_fire": ("A warship burned off Crimea.", ["warship on fire smoke at sea", "ship burning at sea", "navy ship fire smoke", "ship explosion at sea"]),
    "landing_ship": ("A Russian landing ship sailed off Crimea.", ["Russian Ropucha landing ship", "Russian landing ship at sea", "Russian amphibious landing exercise", "Russian landing ship beach"]),
    "radar": ("A radar station watched the sky over Crimea.", ["military radar rotating", "air defence radar antenna", "radar station rotating dish", "military radar truck"]),
    "tank_column": ("A tank column moved through Donetsk.", ["tank column on the road", "armored column convoy driving", "tanks driving in column", "military convoy armoured vehicles"]),
    "fpv_drone_flight": ("FPV drones flew over the front near Bakhmut.", ["FPV drone flight frontline", "FPV drone flying low field", "FPV drone launch soldiers", "FPV drone flight forest"]),
    "kalibr_launch": ("Kalibr missiles were launched from the Black Sea.", ["Russian Kalibr missile launch ship", "Kalibr launch submarine", "Kalibr cruise missile launch", "Russian frigate missile launch"]),
    "warship_deck_sailors": ("Russian sailors worked on the deck of a warship in Sevastopol.", ["Russian navy sailors on deck", "Russian warship crew drill deck", "Russian sailors parade ship", "Russian navy crew on frigate"]),
    "ukraine_air_defence_night": ("Air defence fired over Kyiv at night.", ["air defence interception night sky", "Kyiv air defence night", "anti aircraft fire night tracer", "air defence missile night launch"]),
}
FLOW = {
    "ai_ammo_depot_explosion": ["a huge ammunition depot explosion at night, fireball and secondary blasts, seen from far away across a field",
                                "rows of burning ammunition crates in a forest depot at dusk, small explosions, thick smoke",
                                "a mushroom of smoke rising over a military warehouse at dawn, aerial wide shot"],
    "ai_ship_hit_fire": ["a grey warship burning at sea, black smoke pouring from the hull, overcast, aerial wide",
                         "a damaged warship listing in a harbour at night, fire on deck, sirens lights on the pier",
                         "close view of smoke and flames on a warship superstructure, waves, cold grey light"],
    "ai_submarine_interior": ["inside a submarine control room, red light, sailors at periscope and panels, faces in shadow",
                              "a narrow submarine corridor with pipes and hatches, dim light, slow push",
                              "a submarine hatch opening upward to a grey sky, water dripping"],
    "ai_landing_ship": ["a large grey landing ship sailing in a calm sea, bow doors closed, overcast, aerial",
                        "a landing ship at a pier loading armoured vehicles, dusk, floodlights",
                        "a landing ship opening bow ramp on a rocky beach, waves, morning mist"],
    "ai_coastal_missile_launcher": ["a coastal missile launcher truck raising two launch tubes on a cliff above the sea, dusk",
                                    "a column of missile launcher trucks driving along a coast road, overcast",
                                    "a missile launching from a truck on a coastal cliff, smoke cloud, sea behind"],
    "ai_substation_fire": ["an electrical substation burning at night, transformers on fire, sparks, smoke",
                           "firefighters spraying water on a burning power substation at dawn, winter",
                           "a dark city at night after a power station strike, one fire glowing on the horizon"],
    "ai_naval_drone_pov": ["point of view from a small sea drone racing over waves toward a grey warship at dusk",
                           "low camera skimming over dark water at night, a ship silhouette growing on the horizon",
                           "a small black unmanned boat speeding across choppy sea, spray, overcast, tracking shot"],
    "ai_interception_night": ["an air defence missile rising into a dark night sky and a bright interception flash high above, city lights below",
                              "tracer fire and a single interception explosion high over a dark city, no fireworks colours",
                              "two missile trails crossing in a night sky, a white flash, smoke drifting"],
    "ai_officers_map_table": ["military officers leaning over a large paper map on a table in a dim command post, faces in shadow, hands moving markers",
                              "close view of hands placing markers on a war map under a desk lamp",
                              "a dim underground command room with screens and a map table, figures from behind"],
    "ai_shells_production": ["an old factory line of artillery shells moving on a conveyor, sparks, workers from behind",
                             "rows of fresh artillery shells stacked in a warehouse, slow dolly",
                             "a worker painting artillery shells on a production line, harsh factory light"],
    "ai_airfield_bombers": ["large swept-wing bombers parked on a snowy military airfield, ground crew, dawn, aerial",
                            "a heavy bomber taking off from a long runway at dusk, heat haze",
                            "aircraft shelters on a military airfield at night, one bomber lit by floodlights"],
    "ai_tanker_at_sea": ["an old oil tanker sailing in a grey sea, rust on the hull, overcast, aerial wide",
                         "an oil tanker at anchor at night with deck lights, calm water",
                         "two tankers transferring oil side by side at sea, hoses between them, aerial"],
    "ai_bridge_crossing": ["a long road and rail bridge across a strait at dawn, trucks crossing, aerial",
                           "a damaged span of a long sea bridge with smoke rising, overcast, aerial wide",
                           "a military pontoon bridge across a wide river, trucks driving over, morning fog"],
    "ai_evacuation_train": ["people boarding an old train at a station platform at night, bags, faces turned away",
                            "a train leaving a snowy station at dawn, steam, empty platform"],
}


def silent(path: Path, seconds: float) -> None:
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", f"{seconds:.0f}", "-q:a", "9", str(path)], check=True)


def real(name: str, letter: str, subjects: dict) -> list:
    d = OUT / name
    d.mkdir(parents=True, exist_ok=True)
    rows, n = [], 0
    for subj, (sentence, alts) in subjects.items():
        for k in range(4):
            n += 1
            first = alts[k]
            rest = [a for a in alts if a != first][:1]
            rows.append({"scene_number": n, "start": f"{(n - 1) * SEG:.1f}", "end": f"{n * SEG:.1f}", "script_segment": sentence,
                         "asset_type": "youtube_video", "prompt": " || ".join([first] + rest), "graphic": "", "library_name": f"{subj}_{k + 1:02d}"})
    write(d, f"library_batch_{letter}", f"normal_batch_{letter}", rows)
    silent(d / f"silent_voiceover_{letter}.mp3", len(rows) * SEG + 20)
    return rows


def flow(name: str) -> list:
    d = OUT / name
    d.mkdir(parents=True, exist_ok=True)
    rows, n = [], 0
    for subj, prompts in FLOW.items():
        for k, p in enumerate(prompts):
            n += 1
            rows.append({"scene_number": n, "start": f"{(n - 1) * SEG:.1f}", "end": f"{n * SEG:.1f}", "script_segment": f"Illustration: {p.split(',')[0]}.",
                         "asset_type": "flow_video", "prompt": f"{p}, {TAIL}", "graphic": "", "library_name": f"{subj}_{k + 1:02d}"})
    write(d, "flow_batch_10_missing", "flow_batch_10_missing_normal", rows)
    silent(d / "silent_voiceover_flow10.mp3", len(rows) * SEG + 20)
    return rows


def write(d: Path, war_name: str, normal_name: str, rows: list) -> None:
    keys = ["scene_number", "start", "end", "script_segment", "asset_type", "prompt", "graphic", "library_name"]
    with open(d / f"{war_name}.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, keys)
        w.writeheader()
        w.writerows(rows)
    with open(d / f"{normal_name}.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, ["scene_number", "script_segment", "asset_type", "prompt"])
        w.writeheader()
        for r in rows:
            w.writerow({"scene_number": r["scene_number"], "script_segment": r["script_segment"], "asset_type": r["asset_type"],
                        "prompt": r["prompt"].split(" || ")[0]})


OUT = Path(".")


def main(argv: list) -> int:
    global OUT
    if not argv:
        print(__doc__)
        return 2
    OUT = Path(argv[0])
    h = real("friend_batch_H", "H", H)
    i = real("friend_batch_I", "I", I)
    f = flow("friend_flow6")
    print(f"rows: H {len(h)}, I {len(i)}, Flow {len(f)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
