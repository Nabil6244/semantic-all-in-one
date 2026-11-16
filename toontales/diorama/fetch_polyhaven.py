"""Fetch the CC0 Poly Haven textures and sky HDRI the realistic diorama engine uses (once; shared by Channels 3 and 5).

Each material key maps to a Poly Haven asset; files land in assets/diorama/textures/<key>/{diff,nor,rough}.jpg and
assets/diorama/hdri/<key>.hdr. Re-running skips what is already there.
    python3 -m toontales.diorama.fetch_polyhaven
"""
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEX = ROOT / "assets" / "diorama" / "textures"
HDRI = ROOT / "assets" / "diorama" / "hdri"
UA = {"User-Agent": "toontales-asset-fetch"}

MATERIALS = {  # key used in layouts -> (Poly Haven id, resolution)
    "grass": ("leafy_grass", "1k"), "soil": ("excavated_soil_wall", "2k"), "gravel": ("gravel", "1k"),
    "rock": ("rock_boulder_cracked", "2k"), "stone": ("castle_wall_slates", "2k"), "brick": ("red_brick", "1k"),
    "planks": ("brown_planks_05", "1k"), "wood_floor": ("wood_floor", "1k"), "plaster": ("white_plaster_02", "1k"),
    "tile": ("brown_floor_tiles", "1k"), "sand": ("coast_sand_01", "1k"), "wet_sand": ("damp_beach_sand", "1k"),
    "concrete": ("concrete", "1k"), "roof": ("clay_roof_tiles_02", "1k"), "metal": ("metal_plate", "1k"),
    "bark": ("bark_brown_01", "1k"), "cobble": ("cobblestone_01", "1k"),
    "walnut": ("walnut_veneer", "1k"), "oak": ("oak_veneer_01", "1k"),  # Channel 5 counters and tables
}
SKIES = {"day": "kloofendal_38d_partly_cloudy_puresky", "evening": "evening_road_01_puresky",
         "studio": "brown_photostudio_02"}
MAPS = {"diff": "Diffuse", "nor": "nor_gl", "rough": "Rough"}
MODELS = ["fir_sapling", "shrub_01", "wooden_bucket_01", "wooden_ladder", "sofa_02", "wooden_bookshelf_worn",
          "wooden_crate_01", "dead_tree_trunk"]  # used in layouts as "ph:<id>"; full trees are 0.5-1 GB: not used
MOD = ROOT / "assets" / "diorama" / "models"


def _get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        return r.read()


def fetch(keys=None):
    for key, (pid, res) in MATERIALS.items():
        if keys and key not in keys:
            continue
        d = TEX / key
        if all((d / f"{m}.jpg").exists() for m in MAPS):
            continue
        d.mkdir(parents=True, exist_ok=True)
        files = json.loads(_get(f"https://api.polyhaven.com/files/{pid}"))
        for m, name in MAPS.items():
            url = files[name][res]["jpg"]["url"]
            (d / f"{m}.jpg").write_bytes(_get(url))
        (d / "SOURCE.txt").write_text(f"Poly Haven {pid} ({res}), CC0: https://polyhaven.com/a/{pid}\n")
        print("TEX", key, pid, flush=True)
    HDRI.mkdir(parents=True, exist_ok=True)
    for key, pid in SKIES.items():
        p = HDRI / f"{key}.hdr"
        if not p.exists():
            files = json.loads(_get(f"https://api.polyhaven.com/files/{pid}"))
            p.write_bytes(_get(files["hdri"]["2k"]["hdr"]["url"]))
            (HDRI / f"{key}.txt").write_text(f"Poly Haven {pid} (2k), CC0\n")
            print("HDRI", key, pid, flush=True)


def fetch_models(ids=None):
    for pid in ids or MODELS:
        d = MOD / pid
        main = d / f"{pid}_1k.gltf"
        if main.exists():
            continue
        g = json.loads(_get(f"https://api.polyhaven.com/files/{pid}"))["gltf"]["1k"]["gltf"]
        d.mkdir(parents=True, exist_ok=True)
        for rel, f in g.get("include", {}).items():
            out = d / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(_get(f["url"]))
        main.write_bytes(_get(g["url"]))
        (d / "SOURCE.txt").write_text(f"Poly Haven {pid} (1k gltf), CC0: https://polyhaven.com/a/{pid}\n")
        print("MODEL", pid, flush=True)


if __name__ == "__main__":
    fetch(set(sys.argv[1:]) or None)
    fetch_models()
