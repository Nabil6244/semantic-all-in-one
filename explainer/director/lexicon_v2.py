"""Keyword tables for the "scenes v2" pack (opt-in: DirectorOptions.scenes2). Plain data plus three small functions. The rules:

  1. Near-synonyms are NOT merged: village, town, border, station, bank, mountains, barn, winter each choose their own picture.
  2. No default: a beat whose words name no scene gets no scene (choose_scene_v2 returns None), and no prop or tile picture unless a word names one. Words that are generic or only
     suggest a mood ("people", "family", "country", "king", "plan" as a verb, "light") never choose anything on their own.
  3. Names from the v1 kit (field, city, harbour, room, and the desert town) are still answered for the topics v2 does not cover.

    choose_scene_v2(tokens) -> scene name or None        prop_for_v2(tokens) -> (prop, token index) or None       tile_for_v2(tokens) -> (asset, token index) or None
    scenes2_tables() -> every table in one dict (for the director)"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from . import lexicon as LX

# ---- scenes: name -> words; v2 names first, then the v1 sets for what v2 does not cover ----
SET_WORDS_V2: Dict[str, List[str]] = {
    "border_wall": "border borders frontier frontiers checkpoint checkpoints wall walls barrier barriers customs smuggler smugglers smuggled smuggling refugees crossing guards guard".split(),
    "mountain_pass": "mountain mountains alps alpine pass peak peaks summit summits cliff cliffs valley valleys highlands highland switzerland swiss himalayas andes pyrenees glacier glaciers tunnel".split(),
    "vault": "vault vaults bank banks banker bankers treasury bullion reserves deposits deposit ledger".split(),
    "station": "station stations railway railways railroad railroads train trains locomotive locomotives platform passengers".split(),
    "barn": "barn barns stable stables hayloft hay livestock cattle cows cow pigs sheep poultry dairy farmyard".split(),
    "snowy_village": "snow snowy snowfall blizzard blizzards frozen frost icy sleigh winter".split(),
    "village": "village villages villager villagers hamlet hamlets cottage cottages countryside rural peasants parish church".split(),
    "old_town": "town towns townsfolk townspeople square marketplace street streets cobbled shop shops market markets merchants".split(),
    # the v1 kit
    "field": "farm farms farmer farmers farming field fields crop crops harvest wheat grain plantation soil".split(),
    "city": "city cities capital skyline factory factories office offices".split(),
    "harbour": "harbour harbor port ports ship ships sea boat boats sail sailors sailing dock docks voyage".split(),
    "room": "room rooms school classroom parliament court palace throne meeting council ministry students teacher king queen".split(),
    "town": "desert".split(),
}
# words that never choose a scene alone (the v1 list plus words that mean "a place of some kind" without saying which)
SCENE_WEAK_V2 = LX.SCENE_WEAK | frozenset("country countries land lands nation nations world area region home homes house houses guard guards crossing deposit deposits pass".split())
SNOW_WORDS = frozenset(SET_WORDS_V2["snowy_village"])
HOMES = ("village", "old_town")                     # a snow word beside a village or a town makes it the snowy one
SCENE_ORDER = tuple(SET_WORDS_V2)

# ---- props (small pictures standing on the stage beside the figures): name -> words; a prop is shown only when a word names it ----
PROP_WORDS_V2: Dict[str, List[str]] = {
    "coin_stack": "coin coins cash savings fortune wealth riches payment payments".split(),
    "gold_bars": "gold bullion ingots ingot".split(),
    "vault_door": "vault vaults safe strongroom".split(),
    "folder": "dossier dossiers folder folders file files secret secrets classified plan plans".split(),
    "letter": "letter letters mail envelope telegram message messages post".split(),
    "train": "train trains locomotive railway railways railroad railroads".split(),
    "truck": "truck trucks lorry lorries convoy convoys".split(),
    "tank": "tank tanks armour armor panzer panzers".split(),
    "plane": "plane planes aircraft airplane airplanes bomber bombers fighter fighters aeroplane luftwaffe".split(),
    "ship": "ship ships navy fleet steamer steamers liner cargo".split(),
    "barbed_wire": "wire barbed fence fences".split(),
    "border_post": "border borders frontier checkpoint checkpoints".split(),
    "radio": "radio radios broadcast broadcasts broadcasting propaganda".split(),
    "lantern": "lantern lanterns lamp lamps candle candles".split(),
    "map_table": "strategy headquarters generals commanders command".split(),
    # the v1 props, with the generic words taken out (no "country -> flag", no "village -> house")
    "house": "house cottage cottages".split(),
    "tree": "tree trees forest woods timber orchard".split(),
    "cactus": "cactus cacti".split(),
    "flag": "flag flags".split(),
    "sign": "sign signs notice tax taxes".split(),
    "crate": "crate crates goods barrels".split(),
}
PROP_ORDER = tuple(PROP_WORDS_V2)
# the height a prop is drawn at (px on the 1920 x 1080 stage): the wide ones are kept to about 450 px
PROP_HEIGHT: Dict[str, int] = {"coin_stack": 230, "gold_bars": 220, "vault_door": 300, "folder": 220, "letter": 170, "train": 170, "truck": 230, "tank": 200, "plane": 200, "ship": 230,
                               "barbed_wire": 160, "border_post": 330, "radio": 210, "lantern": 270, "map_table": 280, "house": 300, "tree": 300, "cactus": 300, "flag": 300, "sign": 300, "crate": 200}

# ---- tile pictures (icon ids for cards, tiles and rings; consulted before the v1 ICONS table): word -> asset ----
TILE_WORDS_V2: Dict[str, List[str]] = {
    "pic:coin_stack": "coin coins cash savings fortune wealth riches payment payments".split(),
    "pic:gold_bars": "gold bullion ingots".split(),
    "pic:vault_door": "vault vaults reserves strongroom".split(),
    "pic:folder": "dossier dossiers folder file files classified secret secrets plan plans".split(),
    "pic:letter": "letter letters mail envelope telegram message messages".split(),
    "pic:train": "train trains locomotive railway railways railroad railroads".split(),
    "pic:truck": "truck trucks lorry lorries convoy convoys".split(),
    "pic:tank": "tank tanks armour armor panzer panzers".split(),
    "pic:plane": "plane planes aircraft airplane airplanes bomber bombers fighter fighters aeroplane luftwaffe".split(),
    "pic:ship": "ship ships navy fleet steamer liner cargo".split(),
    "pic:barbed_wire": "wire barbed fence fences".split(),
    "pic:border_post": "border borders frontier checkpoint checkpoints".split(),
    "pic:radio": "radio radios broadcast broadcasts propaganda".split(),
    "pic:lantern": "lantern lanterns lamp lamps candle candles".split(),
    "pic:map_table": "strategy headquarters generals commanders".split(),
}


def _flat(table: Dict[str, List[str]]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for name, words in table.items():
        for w in words:
            out.setdefault(w, name)             # the first table entry that lists a word owns it
    return out


TILE_ICONS_V2: Dict[str, str] = _flat(TILE_WORDS_V2)


def _hits(tokens: Sequence[str], words) -> List[int]:
    return [i for i, t in enumerate(tokens) if t in words and t not in SCENE_WEAK_V2]


def choose_scene_v2(tokens: Sequence[str]) -> Optional[str]:
    """The set whose words are said most in the beat (ties: said first, then table order); None when no word names a scene. A snow word beside a village or a town picks the snowy village."""
    best, key = None, (0, 0)
    for name in SCENE_ORDER:
        h = _hits(tokens, SET_WORDS_V2[name])
        cand = (len(h), -(h[0] if h else 10 ** 6))
        if h and cand > key:
            best, key = name, cand
    if best in HOMES and any(t in SNOW_WORDS for t in tokens):
        return "snowy_village"
    return best


def scene_strength_v2(tokens: Sequence[str]) -> int:
    """How many scene words (not weak, not people words alone) the beat says: the number the cartoon scorer needs."""
    allw = set().union(*[set(w) for w in SET_WORDS_V2.values()])
    return sum(1 for t in tokens if t in allw and t not in SCENE_WEAK_V2)


def prop_for_v2(tokens: Sequence[str]) -> Optional[Tuple[str, int]]:
    """(prop, index of the word) for the first word that names a prop, or None. No default prop."""
    for i, t in enumerate(tokens):
        for p in PROP_ORDER:
            if t in PROP_WORDS_V2[p]:
                return p, i
    return None


def tile_for_v2(tokens: Sequence[str]) -> Optional[Tuple[str, int]]:
    for i, t in enumerate(tokens):
        if t in TILE_ICONS_V2:
            return TILE_ICONS_V2[t], i
    return None


def scenes2_tables() -> Dict[str, object]:
    """Everything the director or the cartoon composer reads. `icons` is meant to be merged IN FRONT of lexicon.ICONS when scenes2 is on ({**LX.ICONS, **icons} keeps v1 words that v2
    does not name; for 'v2 wins' use the dict as the caller's table)."""
    return {"sets": SET_WORDS_V2, "set_weak": SCENE_WEAK_V2, "props": PROP_WORDS_V2, "prop_height": PROP_HEIGHT, "icons": dict(TILE_ICONS_V2), "choose_scene": choose_scene_v2,
            "prop_for": prop_for_v2, "tile_for": tile_for_v2}
