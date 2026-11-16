"""Diorama layouts for Channel 3 (realistic cut-aways). Writes toontales/sets/worlds/<name>.json with
"engine": "diorama" (built by toontales/sets/diorama.py inside Blender).
    python3 -m toontales.diorama.layouts
"""
import json
from pathlib import Path

WORLDS = Path(__file__).resolve().parents[1] / "sets" / "worlds"
GROUND = [["grass", 0.12], ["soil", 1.5], ["gravel", 0.7], ["rock", 6.0]]  # top 0 down to -8.32
L = {}

L["dio_field_well"] = {
    "engine": "diorama", "hdri": "day", "sun": [40, 35],
    "about": "open field sliced side-on: grass, soil, gravel and rock bands; a stone well shaft (id well) cut in half "
             "at the face so you see down it to the water (id well_water, level 1.2) at z -7; a timber well frame "
             "with a little roof over it; pine trees and a car behind. Cast stands on the grass at y ~0.6..3.",
    "marks": {"A": [1.6, 0.9], "B": [-1.6, 0.9], "C": [2.8, 2.0], "D": [0.0, 2.6], "E": [-2.8, 2.0],
              "enter_l": [-5.0, 1.0], "enter_r": [5.0, 1.0], "deep": [0.0, 4.0], "well": [0.0, 0.0]},
    "pieces": [
        {"m": "@slice", "x": [-14, 14], "y": [0, 40], "layers": GROUND,
         "cuts": [{"shape": "cyl", "at": [0, 0], "r": 1.05, "z0": -7.2, "z1": 1.0}], "id": "ground"},
        {"m": "@shaft", "at": [0, 0], "r": 0.8, "wall": 0.25, "z0": -7.2, "z1": 0.7, "mat": "stone", "id": "well"},
        {"m": "@box", "at": [0, 0, -7.4], "size": [2.2, 2.2, 0.2], "mat": "rock"},
        {"m": "@water", "at": [0, 0, -7.2], "r": 0.8, "level": 1.2, "id": "well_water"},
        {"m": "@beam", "a": [-1.15, 0.5, 0.7], "b": [-1.15, 0.5, 2.9], "t": 0.16, "mat": "bark"},
        {"m": "@beam", "a": [1.15, 0.5, 0.7], "b": [1.15, 0.5, 2.9], "t": 0.16, "mat": "bark"},
        {"m": "@beam", "a": [-1.3, 0.5, 2.6], "b": [1.3, 0.5, 2.6], "t": 0.12, "mat": "bark"},
        {"m": "@box", "at": [0, 0.05, 2.95], "size": [3.0, 1.05, 0.07], "mat": "planks", "tilt": 28},
        {"m": "@box", "at": [0, 0.95, 2.95], "size": [3.0, 1.05, 0.07], "mat": "planks", "tilt": -28},
        {"m": "@beam", "a": [-1.15, 0.5, 2.9], "b": [-1.15, 0.5, 3.35], "t": 0.12, "mat": "bark"},
        {"m": "@beam", "a": [1.15, 0.5, 2.9], "b": [1.15, 0.5, 3.35], "t": 0.12, "mat": "bark"},
    ] + [{"m": "ph:fir_sapling", "at": a, "s": sc, "rot": r} for a, sc, r in (
        ([-6.5, 12, 0], 4.5, 10), ([-3.5, 20, 0], 5.5, 70), ([5.5, 15, 0], 5.0, 130), ([9.5, 24, 0], 6.0, 200),
        ([-10.5, 26, 0], 6.0, 300), ([2.0, 30, 0], 6.5, 20), ([13, 34, 0], 6.0, 90))]
      + [{"m": "ph:shrub_01", "at": a, "s": 1.3, "rot": r} for a, r in (([-4.2, 3.4, 0], 0), ([4.8, 5.0, 0], 120))]
      + [{"m": "ph:wooden_bucket_01", "at": [0, 0.35, 1.9], "s": 1.6, "id": "bucket"}]}

L["dio_riverside_house"] = {
    "engine": "diorama", "hdri": "day", "sun": [45, 30],
    "about": "a small house on a soil bank sliced side-on, front wall removed: white plaster room with a wood floor, "
             "sofa and bookshelf, pitched tile roof; a river (id river) beside it on the right whose level can rise "
             "(level_to) and flood the bank. Cast stands in the room (marks A-E) at floor z 0.6.",
    "marks": {"A": [-1.0, 1.4], "B": [0.6, 1.6], "C": [1.8, 2.2], "D": [-0.2, 2.6], "E": [-2.0, 2.4],
              "enter_l": [-3.4, 1.6], "enter_r": [3.4, 1.6], "deep": [0.0, 3.2]},
    "pieces": [
        {"m": "@slice", "x": [-14, 4.6], "y": [0, 40], "layers": GROUND, "id": "bank"},
        {"m": "@slice", "x": [4.6, 30], "y": [0, 40], "top": -1.4, "layers": [["wet_sand", 0.4], ["soil", 1.2],
                                                                            ["rock", 5.3]], "id": "riverbed"},
        {"m": "@water", "at": [17.3, 20, -1.4], "size": [25.4, 40], "level": 0.9, "id": "river"},
        {"m": "@box", "at": [0, 2.0, 0], "size": [6.4, 4.4, 0.6], "mat": "concrete"},
        {"m": "@house", "at": [0, 2.0, 0.6], "size": [6.0, 4.0, 2.7], "floor": "wood_floor", "walls": "plaster",
         "roof": "roof", "pitch": 28, "id": "house"},
        {"m": "ph:sofa_02", "at": [-0.6, 3.3, 0.6], "s": 1.0, "rot": 0},
        {"m": "ph:wooden_bookshelf_worn", "at": [2.3, 3.6, 0.6], "s": 1.0, "rot": 0},
        {"m": "ph:wooden_crate_01", "at": [-2.4, 3.2, 0.6], "s": 1.0, "rot": 15},
    ] + [{"m": "ph:fir_sapling", "at": a, "s": sc, "rot": r} for a, sc, r in (
        ([-8, 12, 0], 5.0, 10), ([-4, 18, 0], 6.0, 80), ([2, 22, 0], 5.5, 140), ([-11, 26, 0], 6.5, 200))]
      + [{"m": "ph:shrub_01", "at": [-4.6, 1.5, 0], "s": 1.4, "rot": 30}],
}

# Backyard with a pit cut into the slice next to the house. Every build stage is a named piece so a story place
# removes what is not built yet: turf + plug_soil + plug_gravel (ground before digging), tank_floor/back/l/r
# (concrete lining), lid + turf2 (closed), pipe_a/b/c (roof downpipe into the tank), pump + pump_pipe, water.
PIT = (1.2, 4.2, 2.6, 2.32)  # x0, x1, depth back (y), depth down: the pit bottom sits on the rock band
_px0, _px1, _py, _pz = PIT
_pcx, _pw = (_px0 + _px1) / 2, _px1 - _px0
L["dio_backyard_tank"] = {
    "engine": "diorama", "hdri": "day", "sun": [44, 25],
    "about": "backyard sliced side-on: a house (open front) on the left, lawn, a pit cut into the ground next to it "
             "(x 1.2..4.2, 2.32 m deep) shown in cut-away, garden shrubs on the right. Build-stage pieces by id: turf, "
             "plug_soil, plug_gravel (undug ground), tank_floor, tank_back, tank_l, tank_r (concrete lining), lid, turf2, "
             "pipe_a/pipe_b/pipe_c (roof downpipe into the tank, visible in the cut face), pump, pump_pipe, water "
             "(level 0..1.9). Marks: B pit's left edge, A right of the pit by the garden, C by the house.",
    "marks": {"A": [5.05, 1.3], "B": [0.55, 1.0], "C": [-0.9, 1.2], "D": [5.2, 2.6], "E": [0.2, 2.6],
              "enter_l": [-1.2, 0.8], "enter_r": [8.5, 1.0], "deep": [2.7, 4.2]},
    "pieces": [
        {"m": "@slice", "x": [-14, 14], "y": [0, 40], "layers": GROUND, "id": "ground",
         "cuts": [{"shape": "box", "at": [_pcx, _py / 2, -_pz], "size": [_pw, _py, _pz + 1]}]},
        # undug ground (soil over gravel, grass on top) filling the pit
        {"m": "@box", "at": [_pcx, _py / 2, -_pz], "size": [_pw, _py, 0.7], "mat": "gravel", "id": "plug_gravel"},
        {"m": "@box", "at": [_pcx, _py / 2, -1.62], "size": [_pw, _py, 1.5], "mat": "soil", "id": "plug_soil"},
        {"m": "@box", "at": [_pcx, _py / 2, -0.12], "size": [_pw, _py, 0.12], "mat": "grass", "id": "turf"},
        # concrete tank lining (front left open: it is the cut-away)
        {"m": "@box", "at": [_pcx, _py / 2, -_pz], "size": [_pw, _py, 0.15], "mat": "concrete", "id": "tank_floor"},
        {"m": "@box", "at": [_pcx, _py - 0.075, -_pz + 0.15], "size": [_pw, 0.15, _pz - 0.3], "mat": "concrete",
         "id": "tank_back"},
        {"m": "@box", "at": [_px0 + 0.075, _py / 2, -_pz + 0.15], "size": [0.15, _py, _pz - 0.3], "mat": "concrete",
         "id": "tank_l"},
        {"m": "@box", "at": [_px1 - 0.075, _py / 2, -_pz + 0.15], "size": [0.15, _py, _pz - 0.3], "mat": "concrete",
         "id": "tank_r"},
        {"m": "@box", "at": [_pcx, _py / 2, -0.15], "size": [_pw, _py, 0.15], "mat": "concrete", "id": "lid"},
        {"m": "@box", "at": [_pcx, _py / 2, 0.0], "size": [_pw, _py, 0.05], "mat": "grass", "id": "turf2"},
        {"m": "@water", "at": [_pcx, _py / 2, -_pz + 0.15], "size": [_pw - 0.3, _py - 0.3], "level": 0.001,
         "id": "water"},
        # roof downpipe: down the house corner, under the lawn (half showing in the cut face), into the tank
        {"m": "@beam", "a": [-1.3, 0.04, 3.05], "b": [-1.3, 0.04, -0.45], "t": 0.09, "color": [0.32, 0.33, 0.35],
         "rough": 0.4, "metal": 0.6, "id": "pipe_a"},
        {"m": "@beam", "a": [-1.3, 0.04, -0.45], "b": [_px0 + 0.3, 0.04, -0.45], "t": 0.09,
         "color": [0.32, 0.33, 0.35], "rough": 0.4, "metal": 0.6, "id": "pipe_b"},
        {"m": "@beam", "a": [_px0 + 0.3, 0.04, -0.45], "b": [_px0 + 0.3, 0.04, -0.75], "t": 0.09,
         "color": [0.32, 0.33, 0.35], "rough": 0.4, "metal": 0.6, "id": "pipe_c"},
        {"m": "@box", "at": [4.45, 0.6, 0.0], "size": [0.4, 0.34, 0.42], "color": [0.15, 0.45, 0.25], "rough": 0.35,
         "id": "pump"},
        {"m": "@beam", "a": [4.45, 0.04, 0.05], "b": [3.7, 0.04, -2.0], "t": 0.06, "color": [0.1, 0.1, 0.1],
         "rough": 0.6, "id": "pump_pipe"},
        # the house next door to the pit
        {"m": "@box", "at": [-4.3, 2.2, 0.0], "size": [6.0, 4.6, 0.35], "mat": "concrete"},
        {"m": "@house", "at": [-4.3, 2.2, 0.35], "size": [5.6, 4.2, 2.7], "floor": "wood_floor", "walls": "plaster",
         "roof": "roof", "pitch": 26, "id": "house"},
        {"m": "ph:sofa_02", "at": [-4.8, 3.6, 0.35], "s": 1.0},
        {"m": "ph:wooden_bookshelf_worn", "at": [-2.3, 3.9, 0.35], "s": 1.0},
    ] + [{"m": "ph:shrub_01", "at": a, "s": sc, "rot": r} for a, sc, r in (
        ([6.6, 1.2, 0], 1.5, 0), ([7.6, 2.4, 0], 1.7, 60), ([8.8, 1.1, 0], 1.4, 140), ([9.8, 2.6, 0], 1.8, 210),
        ([7.1, 3.8, 0], 1.6, 300))]
      + [{"m": "ph:fir_sapling", "at": a, "s": sc, "rot": r} for a, sc, r in (
        ([-9, 12, 0], 5.0, 10), ([-2, 16, 0], 6.0, 80), ([5, 14, 0], 5.5, 140), ([11, 20, 0], 6.5, 200),
        ([1, 26, 0], 6.0, 300))],
}

# ---- Channel 5 studio sets: objects ~0.25 m, so cameras sit 0.3-1.2 m away with depth of field.
COUNTER_Z = 0.9
L["dio_bar_counter"] = {
    "engine": "diorama", "hdri": "studio", "sky_strength": 0.12, "sun": None, "dof": {"fstop": 2.2},
    "about": "walnut bar counter (top at z 0.9) against a dark teal subway-tile wall (y 0.55) with a dark wooden "
             "shelf rail; warm key light from front-left, cool rim from back-right. Put close-up objects on the "
             "counter at z 0.9 between x -0.4..0.4, y -0.1..0.3; aim cameras at z ~1.0, dist 0.4-1.2.",
    "marks": {"A": [0.0, 0.1], "B": [-0.2, 0.1], "C": [0.2, 0.1], "D": [0.0, 0.3], "E": [-0.3, 0.3],
              "enter_l": [-0.6, 0.1], "enter_r": [0.6, 0.1], "deep": [0.0, 0.4]},
    "pieces": [
        {"m": "@wall", "at": [0, 0.55, 0.0], "size": [6.0, 3.0], "tiles": [0.03, 0.24, 0.25], "tile": 0.075},
        {"m": "@box", "at": [0, 0.15, 0.0], "size": [6.0, 1.0, COUNTER_Z], "mat": "walnut", "tint": [0.55, 0.38, 0.28]},
        {"m": "@box", "at": [0, 0.5, 1.32], "size": [6.0, 0.1, 0.05], "mat": "walnut"},
        {"m": "@box", "at": [0, 0.47, 1.37], "size": [6.0, 0.12, 0.02], "mat": "brass"},
    ],
    "lights": [{"at": [-0.9, -0.8, 1.7], "aim": [0, 0.1, 1.0], "size": 0.5, "w": 45, "color": [1.0, 0.82, 0.6]},
               {"at": [0.8, 0.45, 1.6], "aim": [0, 0.1, 1.0], "size": 0.3, "w": 30, "color": [0.7, 0.85, 1.0]},
               {"at": [0.0, -1.2, 0.95], "aim": [0, 0.1, 1.0], "size": 1.0, "w": 6, "color": [1.0, 0.95, 0.9]}],
}
L["dio_mint_studio"] = {
    "engine": "diorama", "hdri": "studio", "sky_strength": 0.15, "sun": None, "dof": {"fstop": 2.8},
    "about": "seamless mint studio: a mint wall (y 0.4) and floor; mechanism parts (coins, magnets, brass rails) "
             "are placed in front of the wall around z 0.8..1.4, x -0.4..0.4; aim cameras at z ~1.1, dist 0.5-1.5.",
    "marks": {"A": [0.0, 0.0], "B": [-0.3, 0.0], "C": [0.3, 0.0], "D": [0.0, 0.2], "E": [-0.2, 0.2],
              "enter_l": [-0.8, 0.0], "enter_r": [0.8, 0.0], "deep": [0.0, 0.3]},
    "pieces": [
        {"m": "@wall", "at": [0, 0.4, 0.0], "size": [8.0, 4.0], "color": [0.42, 0.78, 0.76]},
        {"m": "@box", "at": [0, -1.6, -0.02], "size": [8.0, 4.0, 0.02], "color": [0.42, 0.78, 0.76], "rough": 0.6},
    ],
    "lights": [{"at": [-1.0, -1.2, 2.0], "aim": [0, 0.2, 1.1], "size": 0.8, "w": 40, "color": [1.0, 0.97, 0.92]},
               {"at": [1.2, -0.6, 1.4], "aim": [0, 0.2, 1.1], "size": 0.4, "w": 14, "color": [1.0, 0.9, 0.8]}],
}


def write():
    WORLDS.mkdir(parents=True, exist_ok=True)
    for name, lay in L.items():
        (WORLDS / f"{name}.json").write_text(json.dumps(lay, indent=1))
    print("wrote", ", ".join(L))


if __name__ == "__main__":
    write()
