"""Writes the toon world layouts (toontales/sets/worlds/*.json) from code, so every place is laid out the same way:
puppets stand on the stage marks (x -1.6..1.6, y -0.2..1.8), the camera looks down +y, the world is built behind and
around that strip. Run: python3 -m toontales.sets.make_worlds
Pieces with an "id" can be moved per shot (plan shot "moves"); a plan place can "add" pieces or "remove" ids."""
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent / "worlds"
T = 2.4  # furniture-kit tile (floor/wall) in metres after pack scale


def road_x(y, x0=-42, x1=42, m="road-straight"):
    return [{"m": m, "at": [x, y, 0], "rot": 90} for x in range(x0, x1 + 1, 7)]


def row(m, a, b, n, jitter=0.5, s=1.0, rot=None):
    r = {"m": m, "from": a, "to": b, "n": n, "jitter": jitter, "s": s}
    if rot is not None:
        r["rot"] = rot
    return r


def shell(depth=6.0, half=7.2, floors=2):
    """Interior (furniture-kit pieces by pack name: fantasy-town-kit also has a "wall"): floor tiles, a back wall at y=depth (with windows), side walls, two storeys high (no ceiling)."""
    p = []
    xs = [round(-half + i * T, 2) for i in range(int(2 * half / T) + 1)]
    for x in xs[:-1]:
        for y in [round(-9.6 + j * T, 2) for j in range(int((depth + 9.6) / T) + 1)]:
            p.append({"m": "floorFull", "at": [x, y, 0]})
    for k, x in enumerate(xs[:-1]):
        for z in range(floors):
            p.append({"m": "furniture-kit/wallWindow" if (z == 0 and k % 3 == 1) else "furniture-kit/wall",
                      "at": [x, depth, z * 3.1]})
    for y in [round(-2.4 + j * T, 2) for j in range(int((depth + 2.4) / T))]:
        for z in range(floors):
            p.append({"m": "furniture-kit/wall", "at": [-half, y + T, z * 3.1], "rot": -90})
            p.append({"m": "furniture-kit/wall", "at": [half, y, z * 3.1], "rot": 90})
    return p


FRONT = [row(["grass_large", "grass_leafs", "flower_yellowA", "flower_redB", "rock_smallA"], [-9, -2.5], [-3.5, -1.5], 6, 1.0, 0.35),
         row(["grass_large", "grass_leafs", "flower_purpleA", "plant_bushSmall"], [3.5, -1.5], [9, -2.5], 6, 1.0, 0.35)]
WALLS = {"wall": [0.95, 0.80, 0.62], "floorFull": [0.85, 0.62, 0.42]}
SKY = {"top": [0.26, 0.58, 0.97], "low": [0.80, 0.91, 1.0]}
houses = ["building-type-a", "building-type-c", "building-type-f", "building-type-k", "building-type-m", "building-type-q"]
shops = ["building-a", "building-c", "building-e", "building-g", "building-h", "building-k"]
pines = ["tree_pineRoundA", "tree_pineTallA", "tree_pineDefaultA", "tree_pineRoundC"]
leafy = ["tree_default", "tree_oak", "tree_detailed", "tree_fat"]

W = {}
W["highway"] = {"about": "open country road crossing the frame behind the cast, fields, houses and trees behind; "
                         "movers: rig (delivery truck), car (sedan)",
                "ground": [0.42, 0.66, 0.25], "sky": SKY,
                "pieces": road_x(7) + [{"m": "delivery", "at": [-4, 5.6, 0], "rot": 90, "id": "rig"},
                                       {"m": "sedan", "at": [10, 8.6, 0], "rot": -90, "id": "car"},
                                       {"m": "road-sign-warning", "at": [5.5, 3.6, 0], "rot": 180, "s": 0.5}]
                + [{"m": houses[i % 6], "at": [-26 + i * 11, 20 + (i % 2) * 3, 0], "rot": 180} for i in range(6)],
                "rows": [row(leafy, [-40, 13], [40, 13], 12, 1.5), row(pines, [-60, 40], [60, 40], 22, 3, 1.6)]}
W["town"] = {"about": "town main street: road behind the cast, a row of shops, tall buildings behind, traffic light; "
                      "movers: taxi, car, van",
             "ground": [0.55, 0.57, 0.6], "sky": SKY,
             "pieces": road_x(6) + [{"m": "taxi", "at": [-7, 4.6, 0], "rot": 90, "id": "taxi"},
                                    {"m": "sedan-sports", "at": [12, 7.5, 0], "rot": -90, "id": "car"},
                                    {"m": "van", "at": [4, 7.5, 0], "rot": -90, "id": "van"},
                                    {"m": "traffic-light", "at": [3.2, 3.0, 0], "rot": 180, "s": 0.55}]
             + [{"m": shops[i % 6], "at": [-30 + i * 6.2, 13.5, 0], "rot": 180} for i in range(11)]
             + [{"m": f"building-skyscraper-{'abcde'[i % 5]}", "at": [-36 + i * 12, 32, 0], "rot": 180} for i in range(7)],
             "rows": [row("tree-small", [-30, 10.4], [30, 10.4], 8, 0.2, 1.0)]}
W["suburb"] = {"about": "quiet suburb: houses with fences and driveways behind the cast, a parked car; movers: car",
               "ground": [0.45, 0.70, 0.30], "sky": SKY,
               "pieces": road_x(5) + [{"m": "suv", "at": [6, 9.5, 0], "rot": 180, "id": "car"}]
               + [{"m": houses[i % 6], "at": [-24 + i * 9.5, 13, 0], "rot": 180} for i in range(6)]
               + [{"m": "fence-1x4", "at": [-24 + i * 9.5, 9.0, 0], "rot": 0} for i in range(6)],
               "rows": [row(leafy, [-40, 22], [40, 22], 14, 2), row(["plant_bush", "plant_bushLarge"], [-20, 9.6], [20, 9.6], 8, 1)]}
W["room"] = {"paint": {"wall": [0.95, 0.80, 0.62], "floorFull": [0.85, 0.62, 0.42]}, "about": "living room inside a house: sofa, TV, lamp, rug, plant, windows; movers: none",
             "clouds": False, "sky": SKY, "ground": [0.6, 0.5, 0.4],
             "pieces": shell() + [{"m": "loungeSofa", "at": [-3.6, 3.6, 0]}, {"m": "cabinetTelevision", "at": [2.0, 4.6, 0]},
                                  {"m": "televisionModern", "at": [2.3, 4.7, 1.2]}, {"m": "lampRoundFloor", "at": [-5.6, 4.2, 0]},
                                  {"m": "rugRectangle", "at": [-1.8, -0.6, 0.02]}, {"m": "pottedPlant", "at": [5.6, 4.6, 0]},
                                  {"m": "tableCoffee", "at": [-2.6, 1.9, 0]}, {"m": "bookcaseOpen", "at": [-6.9, 0.4, 0], "rot": -90}]}
W["office"] = {"paint": {"wall": [0.70, 0.82, 0.92], "floorFull": [0.85, 0.62, 0.42]}, "about": "office: desks with computers, desk chairs, bookcases, windows; movers: none",
               "clouds": False, "sky": SKY, "ground": [0.6, 0.5, 0.4],
               "pieces": shell() + [{"m": "desk", "at": [x, 3.4, 0]} for x in (-5.4, -1.2, 3.0)]
               + [{"m": "computerScreen", "at": [x + 0.6, 3.6, 0.92]} for x in (-5.4, -1.2, 3.0)]
               + [{"m": "chairDesk", "at": [x + 0.6, 2.6, 0]} for x in (-5.4, -1.2, 3.0)]
               + [{"m": "bookcaseClosedWide", "at": [6.9, 0.2, 0], "rot": 90}, {"m": "pottedPlant", "at": [-6.4, 4.8, 0]}]}
W["kitchen"] = {"paint": {"wall": [0.98, 0.90, 0.62], "floorFull": [0.85, 0.62, 0.42]}, "about": "kitchen or diner: counters, fridge, stove, table and chairs, coffee machine; movers: none",
                "clouds": False, "sky": SKY, "ground": [0.6, 0.5, 0.4],
                "pieces": shell() + [{"m": "kitchenCabinet", "at": [x, 4.9, 0]} for x in (-4.8, -3.6, -2.4, 0.0, 1.2)]
                + [{"m": "kitchenStove", "at": [-1.2, 4.9, 0]}, {"m": "kitchenFridgeLarge", "at": [2.6, 4.7, 0]},
                   {"m": "kitchenCoffeeMachine", "at": [-4.4, 5.0, 0.95]}, {"m": "kitchenSink", "at": [0.0, 4.9, 0]},
                   {"m": "tableRound", "at": [4.6, 2.2, 0]}, {"m": "chair", "at": [4.0, 1.4, 0]}, {"m": "chair", "at": [5.6, 2.6, 0], "rot": 90}]}
W["mountain_road"] = {"about": "mountain road: road behind the cast along a cliff, big rock walls and pines behind, "
                               "snow optional (place ground override); movers: rig (garbage-truck as heavy truck), car",
                      "ground": [0.48, 0.62, 0.35], "sky": SKY,
                      "pieces": road_x(6) + [{"m": "garbage-truck", "at": [-6, 4.6, 0], "rot": 90, "id": "rig"},
                                             {"m": "suv", "at": [9, 7.5, 0], "rot": -90, "id": "car"},
                                             {"m": "road-sign-warning", "at": [4.6, 3.4, 0], "rot": 180, "s": 0.5}]
                      + [{"m": "cliff_large_rock", "at": [-48 + i * 8, 22 + (i % 3) * 2, 0], "rot": 180 + (i % 4) * 12, "s": 2.6} for i in range(13)]
                      + [{"m": "cliff_large_stone", "at": [-50 + i * 12, 40, 0], "rot": 170 + (i % 3) * 15, "s": 5} for i in range(9)],
                      "rows": [row(pines, [-40, 10.5], [40, 10.5], 10, 1.2), row(pines, [-50, 30], [50, 30], 16, 3, 1.8),
                               row(["rock_largeA", "rock_largeB"], [-14, 3.4], [14, 3.4], 5, 1.5, 0.7)]}
W["desert_road"] = {"about": "desert highway: road behind the cast, sand, cactus, red rock cliffs far away; movers: rig, car",
                    "ground": [0.86, 0.70, 0.45], "sky": {"top": [0.30, 0.60, 0.95], "low": [0.95, 0.88, 0.75]},
                    "pieces": road_x(6) + [{"m": "delivery", "at": [-5, 4.6, 0], "rot": 90, "id": "rig"},
                                           {"m": "sedan", "at": [10, 7.5, 0], "rot": -90, "id": "car"}]
                    + [{"m": "cliff_large_rock", "at": [-60 + i * 12, 48 + (i % 2) * 6, 0], "rot": 160 + (i % 4) * 14, "s": 4.5} for i in range(11)],
                    "rows": [row(["cactus_tall", "cactus_short"], [-30, 10], [30, 10], 9, 2.5),
                             row(["rock_largeA", "rock_largeC", "rock_smallA"], [-30, 16], [30, 16], 10, 3)]}
W["forest"] = {"about": "forest clearing: pines, a river behind, logs, rocks, campfire; movers: none",
               "ground": [0.36, 0.58, 0.24], "sky": SKY,
               "pieces": [{"m": "ground_riverStraight", "at": [x, 8, 0.01], "rot": 90, "s": 2.3} for x in range(-42, 43, 7)]
               + [{"m": "log_large", "at": [-3.4, 3.2, 0], "rot": 20}, {"m": "campfire_stones", "at": [3.0, 2.6, 0]},
                  {"m": "rock_largeB", "at": [5.6, 4.4, 0]}],
               "rows": [row(pines, [-40, 4.4], [-6, 4.4], 6, 1.2), row(pines, [6, 4.4], [40, 4.4], 6, 1.2),
                        row(pines, [-50, 14], [50, 14], 20, 3, 1.4), row(pines, [-70, 30], [70, 30], 26, 4, 2.0)]}
W["farm"] = {"about": "farm: crop rows, wooden fence, a farmhouse, a tractor; movers: tractor",
             "ground": [0.50, 0.70, 0.30], "sky": SKY,
             "pieces": [{"m": "fence_simple", "at": [x, 3.4, 0], "s": 1.0} for x in range(-15, 16, 3)]
             + [{"m": "tractor", "at": [-6, 6.5, 0], "rot": 90, "id": "tractor"},
                {"m": "building-type-n", "at": [10, 16, 0], "rot": 200}]
             + [{"m": "crops_cornStageD", "at": [x, y, 0]} for x in range(-18, 4, 3) for y in (10, 12.5, 15)],
             "rows": [row(leafy, [-40, 24], [40, 24], 12, 2.5, 1.2)]}

FT = 3.5  # fantasy-town-kit wall tile after pack scale
DUSK = {"sky": {"top": [0.30, 0.16, 0.52], "low": [1.0, 0.52, 0.22]},
        "light": {"lit": [1.0, 0.82, 0.60], "shade": [0.66, 0.46, 0.74]}, "sun": [16, 145]}


def storefront(x, y0, n, side, floors=2, seed=0, stone=False):
    """A row of wooden false-front shops along the street (y), facing the street. side -1: left of the street.
    stone=True: Victorian stone fronts (same pieces without "wood")."""
    p = []
    kinds = ["wall-wood-window-glass", "wall-wood-window-shutters", "wall-wood-window-small", "wall-wood-detail-cross"]
    if stone:
        kinds = ["wall-window-glass", "wall-window-shutters", "wall-window-stone", "wall-window-glass"]
    rot = 0 if side < 0 else 180
    off = -1.575 if side < 0 else 1.575  # the wall panel sits 0.45 tile off the piece origin
    for i in range(n):
        yy = y0 + i * FT
        for f in range(floors + 1):  # top row: the tall false front above the roof line
            if f == 0:
                m = ("wall-door" if stone else "wall-wood-door") if (i + seed) % 3 == 1 else kinds[(i + seed) % 4]
            elif f == floors:
                m = ("wall-block" if stone else "wall-wood-block") if (i + seed) % 2 else \
                    ("wall-detail-horizontal" if stone else "wall-wood-detail-horizontal")
            else:
                m = kinds[(i + f + seed) % 4]
            p.append({"m": f"fantasy-town-kit/{m}", "at": [x + off, yy, f * FT], "rot": rot})
    return p


def water_tower(x, y):
    p = [{"m": "pillar-wood", "at": [x + dx, y + dy, 0], "s": 1.6} for dx in (-1.6, 1.6) for dy in (-1.6, 1.6)]
    p += [{"m": "survival-kit/barrel", "at": [x, y, 5.4], "s": 3.4}]
    return p


street = (storefront(-5.2, 2.5, 10, -1, seed=0) + storefront(5.2, 2.5, 10, 1, seed=2)
          + water_tower(1.5, 40) + water_tower(-12, 48)
          + [{"m": "survival-kit/barrel", "at": [-3.6, 5.0, 0], "s": 1.2}, {"m": "survival-kit/barrel", "at": [-3.2, 6.2, 0], "s": 1.2},
             {"m": "cart", "at": [3.0, 10.0, 0], "rot": 10, "s": 1.0, "id": "wagon"},
             {"m": "coffin", "at": [-3.4, 13.0, 0], "rot": 90, "id": "coffin"},
             {"m": "fantasy-town-kit/lantern", "at": [-4.0, 3.4, 0], "s": 0.9}, {"m": "fantasy-town-kit/lantern", "at": [4.0, 7.6, 0], "s": 0.9},
             {"m": "survival-kit/box-large", "at": [3.6, 15.5, 0], "rot": 20, "s": 1.0}])
W["frontier_town"] = dict(DUSK, about="Wild West street at dusk: two rows of wooden false-front shops, water towers at the end, "
                                       "barrels, a wagon (mover: wagon), a coffin (mover: coffin), lanterns; purple-orange sky",
                          ground=[0.80, 0.42, 0.22], pieces=street,
                          rows=[row(["cactus_tall", "cactus_short", "rock_largeA"], [-30, 60], [30, 60], 12, 3, 1.2),
                                row(["rock_smallA", "rock_smallC"], [-4, -2.5], [4, -2.5], 4, 1.5, 0.4)])
W["frontier_desert"] = dict(DUSK, about="open desert outside town at dusk: cactus, rocks, far mesas, a lone wagon (mover: wagon)",
                            ground=[0.82, 0.46, 0.24],
                            pieces=[{"m": "cart", "at": [-4.5, 7, 0], "rot": 70, "id": "wagon"}]
                            + [{"m": "cliff_large_rock", "at": [-60 + i * 12, 50 + (i % 2) * 6, 0], "rot": 160 + (i % 4) * 14, "s": 4.5} for i in range(11)],
                            rows=[row(["cactus_tall", "cactus_short"], [-30, 10], [30, 10], 9, 2.5),
                                  row(["rock_largeA", "rock_largeC", "rock_smallA"], [-30, 18], [30, 18], 10, 3)])

WOOD = {"wall": [0.78, 0.50, 0.30], "floorFull": [0.62, 0.40, 0.24]}
LAMP = {"sky": {"top": [0.30, 0.16, 0.52], "low": [1.0, 0.52, 0.22]}, "clouds": False,
        "light": {"lit": [1.0, 0.84, 0.62], "shade": [0.62, 0.44, 0.40]}, "sun": [40, 160]}
W["frontier_office"] = dict(LAMP, about="1880s Wells Fargo office: wood walls, a desk with papers, a safe, bench, lanterns, bookcase",
                            paint=WOOD, ground=[0.6, 0.4, 0.25],
                            pieces=shell() + [{"m": "desk", "at": [-1.6, 3.4, 0], "s": 1.2}, {"m": "chairDesk", "at": [-0.9, 4.6, 0]},
                                              {"m": "survival-kit/box-large", "at": [3.6, 4.4, 0], "s": 2.2, "tint": [0.35, 0.35, 0.38], "id": "safe"},
                                              {"m": "fantasy-town-kit/lantern", "at": [-5.8, 4.8, 0], "s": 0.8},
                                              {"m": "bookcaseClosedWide", "at": [6.9, 0.2, 0], "rot": 90}, {"m": "bench", "at": [-6.4, 0.6, 0], "rot": -90}])
W["frontier_laundry"] = dict(LAMP, about="1880s San Francisco laundry: steaming tubs (barrels), baskets, folded linen on tables, buckets",
                             paint={"wall": [0.80, 0.86, 0.90], "floorFull": [0.62, 0.48, 0.34]}, ground=[0.6, 0.4, 0.25],
                             pieces=shell() + [{"m": "survival-kit/barrel-open", "at": [x, 4.4, 0], "s": 1.6} for x in (-5.0, -3.2, 3.6, 5.4)]
                             + [{"m": "tableCloth", "at": [-0.8, 4.2, 0], "s": 1.3}, {"m": "survival-kit/bucket", "at": [2.2, 3.2, 0], "s": 1.4},
                                {"m": "survival-kit/box-open", "at": [-2.4, 2.6, 0], "s": 1.6}, {"m": "cardboardBoxClosed", "at": [4.8, 1.4, 0], "s": 1.4}])
W["frontier_jail"] = dict(LAMP, about="1880s prison: brick walls, iron bars, a bench, a lantern; cold and grim",
                          paint={"wall": [0.70, 0.62, 0.58], "floorFull": [0.50, 0.48, 0.46]}, ground=[0.5, 0.48, 0.46],
                          light={"lit": [0.92, 0.86, 0.80], "shade": [0.48, 0.46, 0.60]},
                          pieces=shell() + [{"m": "iron-fence-bar", "at": [x, 4.6, 0], "s": 1.6} for x in (-4.8, -3.2, -1.6, 1.6, 3.2, 4.8)]
                          + [{"m": "bench", "at": [0.0, 5.2, 0]}, {"m": "fantasy-town-kit/lantern", "at": [5.8, 4.8, 0], "s": 0.8}])

for k in ("highway", "suburb", "mountain_road", "forest", "farm"):
    W[k]["rows"] = W[k].get("rows", []) + FRONT
W["desert_road"]["rows"] += [row(["rock_smallA", "rock_smallC", "cactus_short"], [-9, -2.5], [-3.5, -1.5], 4, 1.0, 0.6),
                             row(["rock_smallB", "cactus_short"], [3.5, -1.5], [9, -2.5], 4, 1.0, 0.6)]

# ---- Channel 1 (Wobbly-style Victorian tales): warm sunset light over stone towns and steam railways.
SUNSET = {"sky": {"top": [0.36, 0.42, 0.78], "low": [1.0, 0.70, 0.42]},
          "light": {"lit": [1.0, 0.88, 0.72], "shade": [0.60, 0.52, 0.72]}, "sun": [22, 140]}
STONE = [0.90, 0.80, 0.64]


def exchange(y, clock):
    """A grand stone hall across the end of the street, facing the camera, columns, a clock over the door."""
    return [{"m": "@box", "at": [0, y + 2, 0], "size": [16, 4, 10], "color": STONE},
            {"m": "@box", "at": [0, y + 2, 10], "size": [17, 4.6, 0.8], "color": [0.80, 0.70, 0.56]},
            {"m": "@box", "at": [0, y - 0.4, 0], "size": [5, 0.6, 3.4], "color": [0.30, 0.22, 0.18]}] \
        + [{"m": "pillar-stone", "at": [x, y - 0.9, 0], "s": 1.4} for x in (-6.5, -4, 4, 6.5)] \
        + [dict(clock, m="@clock", at=[0, y - 0.15, 6.4])]


def track_x(y, x0=-60, x1=60, step=4):
    return [{"m": "railroad-straight", "at": [x, y, 0], "rot": 90} for x in range(x0, x1 + 1, step)]


def train(x, y, loco="train-locomotive-a", cars=2, rot=90, idn="loco"):
    p = [{"m": loco, "at": [x, y, 0], "rot": rot, "id": idn}]
    for k in range(cars):
        p.append({"m": "train-locomotive-passenger-a", "at": [x - (k + 1) * 6.4, y, 0], "rot": rot, "ride": idn})
    return p


W["victorian_square"] = dict(SUNSET, about="Victorian stone town street at sunset: stone shop fronts both sides, a grand "
                                           "stone hall with a big clock at the end (id clock: hands hour/min, red min2), lanterns, "
                                           "a cart (mover: cart)",
                             ground=[0.58, 0.52, 0.46],
                             pieces=storefront(-5.2, 2.5, 9, -1, floors=2, seed=1, stone=True)
                             + storefront(5.2, 2.5, 9, 1, floors=2, seed=3, stone=True)
                             + exchange(36, {"id": "clock", "r": 1.6, "hour": 9, "min": 50})
                             + [{"m": "fantasy-town-kit/lantern", "at": [x, y, 0], "s": 0.9} for x, y in ((-3.9, 4), (3.9, 9), (-3.9, 16))]
                             + [{"m": "cart", "at": [3.0, 12.0, 0], "rot": 10, "id": "cart"},
                                {"m": "stall-red", "at": [-3.0, 22, 0], "rot": 90}],
                             rows=[row(leafy, [-30, 52], [30, 52], 10, 3, 1.3)])
W["station"] = dict(SUNSET, about="Victorian railway station platform at sunset: the track right behind the cast, a steam "
                                  "train (mover: loco, carriages ride with it), lanterns, benches, a station clock "
                                  "(id station_clock), brick buildings and trees behind",
                    ground=[0.60, 0.56, 0.50],
                    pieces=track_x(6.0) + train(-4, 6.0)
                    + [{"m": "@box", "at": [0, 3.6, 0], "size": [60, 0.25, 0.08], "color": [0.95, 0.92, 0.80]},
                       {"m": "bench", "at": [-5.5, 2.4, 0], "rot": 180}, {"m": "bench", "at": [5.5, 2.4, 0], "rot": 180},
                       {"m": "fantasy-town-kit/lantern", "at": [-3.6, 3.0, 0], "s": 0.9},
                       {"m": "fantasy-town-kit/lantern", "at": [3.6, 3.0, 0], "s": 0.9},
                       {"m": "@clock", "at": [6.8, 3.2, 3.2], "r": 0.55, "hour": 9, "min": 50, "id": "station_clock"},
                       {"m": "@box", "at": [6.8, 3.4, 0], "size": [0.2, 0.2, 2.7], "color": [0.25, 0.25, 0.28]}]
                    + [{"m": "@box", "at": [-24 + i * 9.5, 16, 0], "size": [8, 5, 6 + (i % 3) * 2],
                        "color": [0.72, 0.36, 0.26] if i % 2 else [0.78, 0.44, 0.30]} for i in range(6)],
                    rows=[row(leafy, [-40, 26], [40, 26], 12, 2.5, 1.3)])
W["railway_line"] = dict(SUNSET, about="open country at sunset: a railway line crossing behind the cast, telegraph poles, "
                                       "fields and trees, a steam train (mover: loco, carriages ride with it)",
                         ground=[0.56, 0.66, 0.30],
                         pieces=track_x(7.0) + train(-30, 7.0, loco="train-locomotive-b", cars=3)
                         + [{"m": "@box", "at": [x, 10.5, 0], "size": [0.22, 0.22, 6.0], "color": [0.42, 0.30, 0.20]} for x in range(-40, 41, 12)]
                         + [{"m": "@box", "at": [x, 10.5, 5.6], "size": [1.4, 0.16, 0.16], "color": [0.42, 0.30, 0.20]} for x in range(-40, 41, 12)],
                         rows=[row(leafy, [-50, 22], [50, 22], 14, 3, 1.4), row(pines, [-70, 40], [70, 40], 20, 4, 1.8)]
                         + FRONT)
W["clock_shop"] = dict(SUNSET, clouds=False, about="Victorian clockmaker's shop: wood walls, a big wall clock (id shop_clock), "
                                                   "a work desk, shelves, a lantern, warm lamp light",
                       paint=WOOD, ground=[0.6, 0.4, 0.25],
                       light={"lit": [1.0, 0.86, 0.66], "shade": [0.62, 0.46, 0.44]},
                       pieces=shell() + [{"m": "@clock", "at": [0, 5.8, 2.6], "r": 0.9, "hour": 9, "min": 50, "id": "shop_clock"},
                                         {"m": "desk", "at": [-3.2, 3.6, 0], "s": 1.2}, {"m": "chairDesk", "at": [-2.6, 2.8, 0]},
                                         {"m": "bookcaseOpen", "at": [4.6, 5.2, 0]}, {"m": "bookcaseOpen", "at": [6.0, 5.2, 0]},
                                         {"m": "fantasy-town-kit/lantern", "at": [-5.8, 4.8, 0], "s": 0.8}])

# Wobbly-style density: Victorian places are full of street life and clutter (lamps, barrels, crates, fences,
# clocks). Everything stays clear of the cast marks (x within +-1.6, y -0.2..1.8) so it frames, never blocks.
LAMP_POST = "graveyard-kit/lightpost-single"
W["victorian_square"]["pieces"] += (
    [{"m": LAMP_POST, "at": [x, y, 0], "s": 1.5} for y in (6.5, 14.5, 22.5, 30) for x in (-3.9, 3.9)]
    + [{"m": "survival-kit/barrel", "at": a, "s": 1.5} for a in ([-4.2, 7.4, 0], [-4.4, 8.4, 0], [4.3, 19.2, 0])]
    + [{"m": "survival-kit/box-large", "at": [4.2, 5.2, 0], "s": 1.4, "rot": 12},
       {"m": "survival-kit/box", "at": [4.4, 6.1, 0], "s": 1.4, "rot": -8},
       {"m": "stall-green", "at": [3.3, 27, 0], "rot": -90}, {"m": "stall-bench", "at": [-3.4, 12, 0], "rot": 90},
       {"m": "fountain-round", "at": [0, 28.5, 0], "s": 1.1},
       {"m": "cart-high", "at": [-3.2, 31, 0], "rot": 30},
       {"m": "tree-high-round", "at": [-9.0, 33, 0], "s": 1.6}, {"m": "tree-high-round", "at": [9.0, 33, 0], "s": 1.6}]
    + [{"m": "graveyard-kit/iron-fence", "at": [x, 33.4, 0], "s": 1.4} for x in (-7.5, -5.2, 5.2, 7.5)])
W["station"]["pieces"] += (
    [{"m": "@box", "at": [0, 1.6, 4.4], "size": [30, 5.4, 0.22], "color": [0.46, 0.20, 0.16]},          # platform canopy
     {"m": "@box", "at": [0, -1.05, 4.15], "size": [30, 0.12, 0.5], "color": [0.95, 0.90, 0.78]}]       # canopy valance
    + [{"m": "@box", "at": [x, 3.3, 0], "size": [0.24, 0.24, 4.4], "color": [0.18, 0.30, 0.24]} for x in (-12, -6.5, 6.5, 12)]
    + [{"m": LAMP_POST, "at": [x, 3.1, 0], "s": 1.4} for x in (-9.2, 9.2)]
    + [{"m": "survival-kit/chest", "at": [-7.4, 2.4, 0], "s": 1.5, "rot": 10},
       {"m": "survival-kit/box-large", "at": [-8.4, 2.9, 0], "s": 1.3},
       {"m": "survival-kit/box", "at": [-8.3, 2.9, 0.9], "s": 1.2, "rot": 20},
       {"m": "survival-kit/barrel", "at": [7.6, 2.6, 0], "s": 1.4}, {"m": "survival-kit/barrel", "at": [8.3, 3.1, 0], "s": 1.4},
       {"m": "survival-kit/signpost-single", "at": [3.4, 3.2, 0], "s": 1.4, "rot": 180}]
    + [{"m": "@box", "at": [-24 + i * 9.5, 16, 6 + (i % 3) * 2], "size": [8.4, 5.4, 0.5], "color": [0.30, 0.24, 0.24]} for i in range(6)]
    + [{"m": "@box", "at": [-25.5 + i * 9.5, 16, 6.4 + (i % 3) * 2], "size": [0.9, 0.9, 1.6], "color": [0.55, 0.28, 0.22]} for i in range(6)]
    + [{"m": "@box", "at": [-24 + i * 9.5 + dx, 13.45, 2.4 + (i % 3)], "size": [1.1, 0.1, 1.4], "color": [1.0, 0.82, 0.48]}
       for i in range(6) for dx in (-2, 0, 2)])                                                          # lit windows
W["railway_line"]["pieces"] += (
    [{"m": "fantasy-town-kit/fence", "at": [x, 4.2, 0], "s": 1.3} for x in range(-30, 31, 2) if abs(x) > 2]
    + [{"m": "graveyard-kit/hay-bale", "at": a, "s": 1.6} for a in ([-9, 14, 0], [-7.6, 14.8, 0], [11, 16, 0])]
    + [{"m": "@box", "at": [6.5, 9.3, 0], "size": [0.18, 0.18, 4.5], "color": [0.25, 0.25, 0.28]},          # signal post
       {"m": "@box", "at": [6.5, 9.2, 4.2], "size": [0.9, 0.12, 0.22], "color": [0.85, 0.14, 0.1]},
       {"m": "survival-kit/rock-a", "at": [-4.5, 2.8, 0], "s": 1.4}, {"m": "survival-kit/rock-b", "at": [5.0, 3.0, 0], "s": 1.2},
       {"m": "survival-kit/signpost", "at": [-3.6, 3.3, 0], "s": 1.4, "rot": 160}])
W["clock_shop"]["pieces"] = [q for q in W["clock_shop"]["pieces"] if q["m"] != "fantasy-town-kit/lantern"] + (
    [{"m": "@clock", "at": [x, 5.8, z], "r": r, "hour": h, "min": mn}                                     # a wall of clocks
     for x, z, r, h, mn in ((-2.3, 3.0, 0.42, 3, 15), (2.3, 3.0, 0.42, 7, 40), (-3.5, 2.0, 0.32, 11, 5),
                            (3.5, 2.0, 0.32, 1, 30), (-2.0, 1.4, 0.26, 6, 0), (2.0, 1.4, 0.26, 4, 45), (0, 4.2, 0.3, 12, 0))]
    + [item for x in (-4.9, -6.0) for item in (
        {"m": "@box", "at": [x, 5.4, 0], "size": [0.75, 0.5, 2.3], "color": [0.45, 0.24, 0.14]},          # grandfather clocks
        {"m": "@clock", "at": [x, 5.14, 1.75], "r": 0.27, "hour": 9, "min": 50},
        {"m": "@box", "at": [x, 5.14, 0.85], "size": [0.3, 0.04, 0.7], "color": [0.95, 0.78, 0.3]})]
    + [{"m": "survival-kit/workbench", "at": [4.0, 3.4, 0], "s": 1.4, "rot": 180},
       {"m": "graveyard-kit/lantern-glass", "at": [3.6, 3.3, 0.95], "s": 1.6},
       {"m": "graveyard-kit/candle-multiple", "at": [-3.6, 3.6, 0.95], "s": 1.5},
       {"m": "survival-kit/box", "at": [-5.6, 2.4, 0], "s": 1.3, "rot": 15}])

# ---- Channel 4 (car builds): a bright tiled garage with engine stands, and a drag strip. Engines, turbos and
# superchargers are "@" parts (sets/parts.py) that a plan place adds onto the stands.
STAND_H = 1.0
garage_shell = [q for q in shell(depth=6.0, half=9.6) if q["m"] != "floorFull"]
W["garage"] = {"about": "bright home garage: white tiled floor, tan walls, a tool pegboard, two orange engine stands "
                        "(engines go on top at z 1.0: stand_a x -0.75, stand_b x 0.75: close enough to share a 9:16 frame), a red sports car parked at the side; "
                        "movers: stand_a, stand_b, car",
               "clouds": False, "sky": SKY, "ground": [0.6, 0.6, 0.6], "paint": {"wall": [0.93, 0.80, 0.62]},
               "light": {"lit": [1.0, 0.98, 0.95], "shade": [0.72, 0.70, 0.80]},
               "pieces": garage_shell + [{"m": "@tiles", "at": [0, 0, 0], "w": 19, "d": 16},
                                         {"m": "@pegboard", "at": [0, 5.85, 1.0], "w": 3.0},
                                         {"m": "@stand", "at": [-0.75, 2.2, 0], "h": STAND_H, "id": "stand_a"},
                                         {"m": "@stand", "at": [0.75, 2.2, 0], "h": STAND_H, "id": "stand_b"},
                                         {"m": "sedan-sports", "at": [-6.2, 2.5, 0], "rot": 160, "tint": [1.0, 0.12, 0.1], "tint_mode": "color", "id": "car"},
                                         {"m": "@box", "at": [6.4, 4.8, 0], "size": [0.9, 0.9, 1.1], "color": [0.95, 0.42, 0.14]}]}
W["drag_strip"] = {"about": "quarter-mile drag strip: straight road running away from the camera, grass and trees both "
                            "sides, start lights at the line, a red FINISH gantry far down; movers: car_a (left lane, "
                            "red), car_b (right lane, blue) both at the start line y 0 facing down the strip",
                   "ground": [0.42, 0.70, 0.28], "sky": SKY,
                   "pieces": [{"m": "@strip", "at": [0, 0, 0], "w": 8.0, "finish_y": 150}]
                   + [{"m": "@start_tree", "at": [-4.6, 3.0, 0], "rot": 20},
                      {"m": "@finish", "at": [0, 150, 0], "w": 12},
                      {"m": "sedan-sports", "at": [-1.7, 0, 0], "rot": 180, "s": 0.8, "tint": [1.0, 0.12, 0.1], "tint_mode": "color", "id": "car_a"},
                      {"m": "sedan-sports", "at": [1.7, 0, 0], "rot": 180, "s": 0.8, "tint": [0.15, 0.35, 1.0], "tint_mode": "color", "id": "car_b"}],
                   "rows": [row(leafy + pines, [-9, -10], [-9, 170], 40, 2.0), row(leafy + pines, [9, -10], [9, 170], 40, 2.0),
                            row(pines, [-24, 0], [-24, 200], 30, 4, 1.5), row(pines, [24, 0], [24, 200], 30, 4, 1.5)]}

if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    for k, v in W.items():
        (OUT / f"{k}.json").write_text(json.dumps(v, indent=1))
    print("wrote", ", ".join(W))
