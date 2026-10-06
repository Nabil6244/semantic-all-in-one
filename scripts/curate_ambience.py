#!/usr/bin/env python3
"""Rebuild the bundled AMBIENCE beds from a hand-curated list (2026-10-06).

The earlier ambience set was labelled from pack/folder names, so sports matches, a paintball firefight, metal drags and
toy drones ended up as "room" or "water" beds. This list was chosen from the original Sonniss file names (UCS category
codes: AMBUrbn, RAINInt, WATRWave, CRWDWalla, ...): only steady background recordings, one profile each.

Each bed: 60 s from 1 s in (beds loop under longer scenes), levelled to a low TARGET_LUFS, Opus 128k, written to
assets/bundled-sfx/ambience/amb_<profile>_NN.opus; the catalog's ambience entries are replaced and its version bumped.
Two room tones are generated (the source has no plain office room tone).

    python scripts/curate_ambience.py --source ~/Downloads/videogen-sfx-source
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from sfx.ambience_profiles import PROFILE_SECONDARY_TAGS  # noqa: E402

BED_SECONDS = 60
# Beds sit well under narration: about 4 dB quieter than the old library's typical bed (~-30 LUFS), and the generated
# room tones quieter still. The app's ambience volume control applies on top.
TARGET_LUFS = -34.0
ROOM_TONE_LUFS = -42.0

# profile -> [(file name fragment, extra descriptive tags, intensity)]
# Removed by the user after listening (2026-10-06): "Loop Ambience Jungle Night Humid Birds Bug Chirps" (irritating).
CURATED = {
    "city": [
        ("AMBUrbn_Ambience, City, Madrid", ("day", "birds"), "medium"),
        ("AMBUrbn_City Nightlife Ext Street", ("night", "walla"), "medium"),
        ("AMBTown_City Courtyard Calm Street", ("calm", "distant"), "low"),
        ("AMBTown_Ambience, Big Town, Streets", ("day", "people"), "medium"),
    ],
    "traffic": [
        ("AMBTraf_Downtown Construction Traffic Light", ("downtown",), "medium"),
        ("VEHCar_TownDrivingAmbience06", ("car", "interior", "driving"), "medium"),
        ("VEHCar_TownDrivingAmbience13", ("car", "interior", "driving"), "medium"),
    ],
    "rain": [
        ("RAINConc_Rain Medium Exterior Splatter City", ("exterior",), "medium"),
        ("RAINInt_Heavy Rain on Window", ("window", "interior"), "medium"),
        ("RAINInt_Rain Light Interior Hail Storm", ("light", "interior"), "low"),
        ("STORM_StormAmbience11", ("thunder",), "high"),
        ("STORM_StormAmbience13", ("thunder",), "high"),
        ("SBsna_City Block Square Storm", ("city",), "high"),
    ],
    "nature": [
        ("AMBSubn_Ambience, Forest Crickets, Birds", ("birds", "crickets"), "low"),
        ("AMBSwmp_Meadow Pipits", ("meadow", "insects"), "low"),
    ],
    "water": [
        ("WATRWave_Soft Waves Cliffs", ("waves", "soft"), "low"),
        ("WATRWave_Medium Waves at Pebble Beach", ("waves", "beach"), "medium"),
        ("WATRLap_Small Waves sloshing onto Rock Slabs", ("lake",), "low"),
        ("WATRLap_Summer Tennessee Lake Dock", ("lake", "gentle"), "low"),
    ],
    "fire": [
        ("24 Campfire, Dropping Fresh Pine Branches", ("campfire",), "medium"),
        ("FIRECrkl_Fire Crackling, Popping", ("hearth",), "medium"),
        ("FIREBurn_Loop Elements Fire Crackling Crunchy", ("flame",), "medium"),
    ],
    "transport": [
        ("AMBTran_MainHallAmbience03B", ("station", "hall"), "medium"),
        ("AMBTran_TrainInterior09", ("train", "interior"), "medium"),
        ("AMBTran_TrainInterior12", ("train", "interior"), "medium"),
        ("AMBPubl_Metro Station Entrance Hall", ("metro", "hall"), "medium"),
        ("AEROInt_Airplane Interior Small Plane Cruise", ("airplane", "cabin", "flight", "aircraft"), "medium"),
    ],
    "crowd": [
        ("CRWDWalla_Pub Walla Atmos, Restaurant", ("pub", "restaurant"), "medium"),
        ("CRWDWalla_Pub Walla, Crowd, Bar", ("pub", "bar"), "medium"),
        ("CRWDWalla_Dinner Party Crowd in Terrace", ("party",), "medium"),
        ("CRWDWalla_Crowd, Walla, Dense Immersive Group", ("audience", "exterior"), "high"),
        ("CRWDWalla_Crowd, Walla, Movement, 30 People Working", ("workplace", "indoor"), "medium"),
    ],
    "technology": [
        ("Roomtone Space Ship Interior Muted", ("hum", "interior"), "low"),
        ("AMBSubn_Electricity Hum, Lightbulb", ("hum", "electric"), "low"),
        ("MACHAppl_Rhythmic Electric Fridge Hum", ("hum", "electric"), "low"),
        ("DSGNSynth_Scifi Loop Ship Reactor", ("reactor", "scifi"), "medium"),
        ("AMBRoom_Factory Loop Heavy Machinery Tonal Roomtone", ("factory", "industrial"), "medium"),
    ],
    "atmospheric": [
        ("DSGNSynth_Dark Loop Mystic Forest Tonal Steady", ("drone",), "low"),
        ("Dark Industrial Ambience", ("industrial",), "medium"),
        ("magic, drone, tension, spellbound", ("drone",), "low"),
        ("AMBDsgn_Evil Spell Ambience", ("ghostly",), "medium"),
        ("WINDInt_ChimneyWind05", ("wind",), "low"),
    ],
    "room": [
        ("MACHAppl_Deep Fridge Hum", ("hum",), "low"),
        ("CLOCKTick_Crooked Antique Clock", ("clock", "ticking"), "low"),
    ],
}
# Generated room tones: (id suffix, ffmpeg source filter, extra tags)
GENERATED_ROOM = [
    ("air", "anoisesrc=color=brown:sample_rate=48000:amplitude=0.5,lowpass=f=320,highpass=f=35", ("air", "roomtone")),
    ("hvac", "anoisesrc=color=pink:sample_rate=48000:amplitude=0.5,lowpass=f=1400,highpass=f=90", ("hvac", "roomtone")),
]


def find(source: Path, fragment: str) -> Path:
    hits = [p for p in source.rglob("*.wav") if fragment.lower() in p.name.lower() and not p.name.startswith("._")]
    if len(hits) != 1:
        raise SystemExit(f"'{fragment}': expected one source file, found {len(hits)}: {[h.name for h in hits][:4]}")
    return hits[0]


def duration(path: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
                       capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


def encode(inputs: list, out: Path, length: float, lufs: float) -> None:
    fade = 0.03
    af = f"loudnorm=I={lufs}:TP=-2:LRA=11,afade=t=in:d={fade},afade=t=out:st={length - fade:.3f}:d={fade},aresample=48000"
    cmd = ["ffmpeg", "-v", "error", "-y", *inputs, "-t", f"{length:.3f}", "-af", af, "-ac", "2",
           "-c:a", "libopus", "-b:a", "128k", str(out)]
    subprocess.run(cmd, check=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=REPO / "assets" / "bundled-sfx")
    args = ap.parse_args()
    amb_dir = args.out / "ambience"
    catalog_path = args.out / "catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))

    for old in amb_dir.glob("*"):
        old.unlink()
    entries = []
    for profile, beds in CURATED.items():
        base_tags = (profile, *PROFILE_SECONDARY_TAGS.get(profile, ()))
        for n, (fragment, extra, intensity) in enumerate(beds, 1):
            src = find(args.source, fragment)
            length = min(BED_SECONDS, duration(src) - 1.0)
            start = 1.0 if duration(src) > BED_SECONDS + 2 else 0.0
            aid = f"amb_{profile}_{n:02d}"
            out = amb_dir / f"{aid}.opus"
            encode(["-ss", f"{start}", "-i", str(src)], out, length, TARGET_LUFS)
            entries.append({"id": aid, "file": f"ambience/{aid}.opus", "category": "ambience",
                            "tags": [*base_tags, *[t for t in extra if t not in base_tags]], "intensity": intensity,
                            "duration": round(duration(out), 3), "source": "Sonniss GDC", "source_file": src.name,
                            "license": "Sonniss #GameAudioGDC Bundle License", "commercial_use": True,
                            "attribution_required": False, "format": "opus", "curated": True, "loudness_lufs": TARGET_LUFS})
    base_tags = ("room", *PROFILE_SECONDARY_TAGS["room"])
    for n, (suffix, flt, extra) in enumerate(GENERATED_ROOM, len(CURATED["room"]) + 1):
        aid = f"amb_room_{n:02d}"
        out = amb_dir / f"{aid}.opus"
        encode(["-f", "lavfi", "-i", flt], out, BED_SECONDS, ROOM_TONE_LUFS)
        entries.append({"id": aid, "file": f"ambience/{aid}.opus", "category": "ambience",
                        "tags": [*base_tags, *extra], "intensity": "low", "duration": round(duration(out), 3),
                        "source": "Generated", "source_file": f"generated {suffix} room tone", "license": "Original",
                        "commercial_use": True, "attribution_required": False, "format": "opus", "curated": True,
                        "loudness_lufs": ROOM_TONE_LUFS})
    catalog["sfx"] = [e for e in catalog["sfx"] if e.get("category") != "ambience"] + entries
    catalog["version"] = max(3, int(catalog.get("version") or 0) + 1)
    catalog["ambience_curated"] = "2026-10-06"
    catalog_path.write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")
    print(f"{len(entries)} ambience beds; catalog version {catalog['version']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
