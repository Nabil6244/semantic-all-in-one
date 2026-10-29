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
    "snowy_village": "snow snowy snowfall blizzard blizzards frozen frost icy sleigh winter freezing frostbite".split(),
    "village": "village villages villager villagers hamlet hamlets cottage cottages countryside rural peasants parish church".split(),
    "old_town": "town towns townsfolk townspeople square marketplace street streets cobbled shop shops market markets merchants".split(),
    # the v1 kit
    "field": "farm farms farmer farmers farming field fields crop crops harvest wheat grain plantation soil food farmland agriculture agricultural battle battles battlefield army armies troops infantry cavalry regiment regiments cannon cannons musket muskets campaign campaigns invasion invaded marched soldiers soldier".split(),
    "city": "city cities capital skyline factory factories office offices paris vienna berlin london moscow rome revolution revolutions revolutionary uprising barricades".split(),
    "harbour": "harbour harbor port ports ship ships sea boat boats sail sailors sailing dock docks voyage fleet navy naval exiled exile island expedition mediterranean trafalgar water waters shallow lagoon lagoons marsh marshes islands shore shoreline canal canals".split(),
    "room": "room rooms school classroom parliament court palace throne meeting council ministry students teacher king queen emperor empress crowned coronation crown treaty treaties congress cabinet senate assembly consul decree decrees dictator".split(),
    "town": "desert".split(),
}
# words that never choose a scene alone (the v1 list plus words that mean "a place of some kind" without saying which)
SCENE_WEAK_V2 = LX.SCENE_WEAK | frozenset("country countries land lands nation nations world area region home homes house houses guard guards crossing deposit deposits pass".split())
PEOPLE_V2 = LX.PEOPLE_WORDS | frozenset("soldiers soldier army armies troops generals officers emperor empress king queen revolutionaries napoleon leaders".split())      # who the cast stands for in a history beat (v2 only)
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

# history words -> the code-drawn props of explainer/board/props.py (consulted with the tile pictures, v2 only)
HISTORY_ICONS_V2: Dict[str, str] = {w: a for a, ws in (("prop:crown", "emperor empress crowned coronation throne monarchy queen crown dynasty"), ("prop:swords", "battle battles army armies soldiers troops campaign conflicts fighters invaded defeated revolution"), ("prop:cannon", "cannon cannons artillery siege military"), ("prop:castle", "castle palace fortress capital paris moscow"), ("prop:sailship", "fleet navy ship ships expedition voyage exiled island")) for w in ws.split()}

# the abstract words of a history script (power, collapse, victory, retreat...) -> an existing icon, so a sentence with no concrete noun still gets a picture
_MORE_HISTORY = {
    "prop:crown": "power powerful rule ruled ruler rulers rulers' control controlled seized supreme authority influence dynasty reign reigned sovereign royal noble nobles aristocracy",
    "prop:swords": "victories victory won win wins conquered conquest conquer crushed fought fight fighting fighters resistance resist attacked attack war wars warfare clash clashes captured defeat defeating destroyed",
    "prop:cannon": "weapons weapon bombardment fire fired artillery guns gun forces force military",
    "prop:castle": "government governments monarchy capital kingdom kingdoms empire empires territories territory fortress regime state states republic",
    "prop:sailship": "crossed crossing sailed trade routes route expedition navy fleet british ocean overseas colonies colony",
    "icon:warning": "collapsed collapse crisis catastrophe disaster instability devastated devastation famine hunger disease freezing losses loss feared fear danger threat revolt rebellion uprising chaos",
    "icon:person": "man men leader leaders general generals identity people population citizens citizen emperor soldier soldiers born",
    "icon:document": "treaty treaties reforms reform legal code codes laws law constitution agreement agreements decree",
    "icon:clock": "years year century decades later eventually brief briefly",
    "prop:flag": "continent countries country nation nations borders alliance alliances allies coalition powers european french austrian russian prussian",
    "prop:bulb": "ideas ideas' ambition ambitions plan plans decision strategy",
    "prop:key": "escaped escape returned regained seized opportunity",
    "prop:scale": "political politics balance justice courts congress",
    "prop:book": "history story legacy influence survived shaping",
}
for _a, _ws in _MORE_HISTORY.items():
    for _w in _ws.split():
        HISTORY_ICONS_V2.setdefault(_w, _a)


def _hits(tokens: Sequence[str], words) -> List[int]:
    return [i for i, t in enumerate(tokens) if t in words and t not in SCENE_WEAK_V2]


# words of the "field" set that name PEOPLE or a military unit, not a place: beside a real setting word (water, lagoon, island, market...) they count half, so one "armies" never outvotes "shallow water"
PEOPLE_IN_SET = frozenset("army armies troops infantry cavalry regiment regiments soldiers soldier cannon cannons musket muskets campaign campaigns invasion invaded marched food".split())         # "food" is a half-word: it points to the fields, but a real setting word (market, harbour) beats it


# a contrast marker rejects what follows it: "instead of relying on agriculture, the Venetians turned toward the sea" is about the sea. The rejected stretch runs from the marker to the end
# of its phrase (a determiner or pronoun that starts the next clause, a clause word, or four words); a scene word inside it names a place the beat turns AWAY from and counts for nothing.
CONTRAST_MARKERS = (("instead", "of"), ("rather", "than"), ("not",), ("no", "longer"), ("never",), ("abandoned",), ("gave", "up"), ("giving", "up"), ("moving", "away", "from"), ("away", "from"))
CLAUSE_OPENERS = frozenset("the a an we they he she it this these those their his her its our".split())


def rejected_indices(tokens: Sequence[str]) -> set:
    """Indices of the words a contrast marker rejects (see CONTRAST_MARKERS)."""
    out: set = set()
    n = len(tokens)
    for i in range(n):
        for m in CONTRAST_MARKERS:
            if tuple(tokens[i:i + len(m)]) != m:
                continue
            j, taken = i + len(m), 0
            while j < n and taken < 4:
                if taken >= 1 and (tokens[j] in CLAUSE_OPENERS or tokens[j] in LX.SOFT_BREAK):
                    break
                out.add(j)
                j += 1
                taken += 1
    return out


def scene_score_v2(name: str, tokens: Sequence[str]) -> Tuple[float, int]:
    """(weighted number of scene words said, index of the first one): a people or military word counts half, a setting word counts one; a word a contrast marker rejects counts nothing."""
    rej = rejected_indices(tokens)
    h = [i for i in _hits(tokens, SET_WORDS_V2[name]) if i not in rej]
    return sum(0.5 if tokens[i] in PEOPLE_IN_SET else 1.0 for i in h), (h[0] if h else 10 ** 6)


# ---- an obstruction: something made it hard (or impossible) for people who would move to get somewhere ----
OBSTRUCT_WORDS = frozenset("difficult difficulty hard impossible prevented prevent preventing blocked blocking block stopped stopping hindered hampered barred deterred unable thwarted".split())
MOVE_VERBS = frozenset("reach reaching enter entering land landing cross crossing attack attacking approach approaching invade invading invaded sail sailing advance advancing pass".split())
MOVER_WORDS = frozenset("invaders invader invading attackers raiders enemies enemy intruders armies army troops soldiers fleets fleet ships".split())


def obstruction_for(tokens: Sequence[str]) -> Optional[int]:
    """Index of the obstruction word when the beat says that something made it hard or impossible for people who would move (an army, invaders, ships, a verb of reaching or crossing) to get
    somewhere, AND the place is water ("harbour" set: a lagoon, the sea, shallows). The relationship, not a word: the same sentence about a mountain or a wall is not answered here."""
    if choose_scene_v2(tokens) != "harbour":
        return None
    obs = next((i for i, t in enumerate(tokens) if t in OBSTRUCT_WORDS), None)
    if obs is None:
        return None
    if crowd_for(tokens) is None and not any(t in MOVER_WORDS or t in MOVE_VERBS for t in tokens):
        return None
    return obs


def choose_scene_v2(tokens: Sequence[str]) -> Optional[str]:
    """The set whose words are said most in the beat (ties: said first, then table order); None when no word names a scene. A snow word beside a village or a town picks the snowy village.
    A people or military word ("armies") weighs half a setting word, so "shallow water ... invading armies" is a harbour, not a battlefield."""
    best, key = None, (0.0, 0)
    for name in SCENE_ORDER:
        n, first = scene_score_v2(name, tokens)
        cand = (n, -first)
        if n > 0 and cand > key:
            best, key = name, cand
    if best in HOMES and any(t in SNOW_WORDS for t in tokens):
        return "snowy_village"
    return best


def scene_strength_v2(tokens: Sequence[str]) -> int:
    """How many scene words (not weak, not people words alone) the beat says: the number the cartoon scorer needs."""
    allw = set().union(*[set(w) for w in SET_WORDS_V2.values()])
    rej = rejected_indices(tokens)
    return sum(1 for i, t in enumerate(tokens) if t in allw and t not in SCENE_WEAK_V2 and i not in rej)


# a group of people that is the subject of a beat (a demonym such as "the Venetians", a collective such as settlers or villagers): with ONE setting word it is enough for a scene
# ("the Venetians turned toward the sea"): the people are the cast, the setting word is where they go. A word counts only when it is not inside a rejected (contrast) stretch.
GROUP_NOUNS = frozenset("settlers settler communities community villagers villagers townspeople citizens citizen merchants traders sailors fishermen fishers farmers peasants refugees inhabitants residents natives colonists pioneers families tribes nomads islanders locals people population crews".split())
_DEMONYM_ENDS = ("ians", "eans", "ites", "ese", "ards", "ers", "ans")


def group_subjects(tokens: Sequence[str]) -> int:
    """How many group-of-people words (demonyms, collectives) the beat says outside a contrast-rejected stretch."""
    rej = rejected_indices(tokens)
    n = 0
    for i, t in enumerate(tokens):
        if i in rej:
            continue
        if t in GROUP_NOUNS or (len(t) >= 8 and t.endswith(("ians", "eans", "ites", "ese"))):
            n += 1
    return n


# ---- the people of a story (the characters pack, explainer/assets/characters): type -> the words that call for one ----
CHARACTER_WORDS: Dict[str, List[str]] = {
    "soldier": "soldier soldiers army armies troops infantry regiment regiments infantrymen musketeers militia forces garrison conscripts crusaders crusading knights invaders invading".split(),
    "officer": "general generals officer officers marshal marshals commander commanders napoleon bonaparte captain admiral wellington colonel".split(),
    "king": "king emperor monarch monarchs ruler rulers sovereign kaiser tsar czar pharaoh sultan prince crown doge doges duke nobles noble aristocrats aristocracy".split(),
    "police": "police policeman policemen cop cops constable detective detectives inspector patrol gendarmes".split(),
    "worker": "worker workers factory miners miner labourers laborers builders engineers workforce union strike strikers".split(),
    "farmer": "farmer farmers peasant peasants harvest villagers villager farming serfs".split(),
    "merchant": "merchant merchants trader traders banker bankers shopkeeper shopkeepers businessman businessmen tycoon traders' vendors".split(),
    "sailor": "sailor sailors navy fleet crew crews captain's seamen mariners pirates explorer explorers navigator navigators voyagers voyage voyages shipbuilders shipwrights".split(),
    "doctor": "doctor doctors scientist scientists physician surgeon nurse nurses researcher researchers professor professors inventor".split(),
    "revolutionary": "revolutionary revolutionaries rebels rebel mob protesters protest crowd uprising insurgents republicans".split(),
    "guard": "guard guards guardsmen sentry sentries bodyguard bodyguards".split(),
    "judge": "judge judges court trial lawyer lawyers tribunal jury magistrate".split(),
    "woman": "woman women queen mother wife lady ladies daughter girl widow princess".split(),
    "priest": "priest priests bishop bishops monk monks pope church clergy cardinal".split(),
}
CHARACTER_OF: Dict[str, str] = {w: t for t, ws in CHARACTER_WORDS.items() for w in ws}
CROWD_TYPES = ("soldier", "police", "worker", "revolutionary", "sailor", "farmer", "guard")
PLURAL_HINT = frozenset("army armies troops soldiers infantry regiment regiments forces militia police workers miners farmers peasants villagers sailors crew crews fleet navy rebels mob protesters revolutionaries guards insurgents strikers".split())

PEOPLE_V2 = PEOPLE_V2 | (frozenset(CHARACTER_OF) - frozenset("crown church court trial fleet navy forces protest strike union factory harvest farming patrol uprising jury".split()))      # whoever the characters pack can draw is a person


def characters_for(tokens: Sequence[str]) -> List[Tuple[str, int]]:
    """[(character type, index of the word)] in spoken order, each type once: who stands on the stage."""
    out: List[Tuple[str, int]] = []
    for i, t in enumerate(tokens):
        k = CHARACTER_OF.get(t)
        if k and all(k != x for x, _ in out) and t not in SCENE_WEAK_V2:
            out.append((k, i))
    return out


def crowd_for(tokens: Sequence[str]) -> Optional[Tuple[str, int]]:
    """(character type, index) when a many-people word (army, workers, rebels) is spoken: the stage gets a row of that character."""
    for i, t in enumerate(tokens):
        k = CHARACTER_OF.get(t)
        if k in CROWD_TYPES and t in PLURAL_HINT:
            return k, i
    return None


def lead_for_crowd(chars: Sequence[Tuple[str, int]], crowd_kind: Tuple[str, int]) -> str:
    """Who stands beside a row of soldiers (or police...): a leader only when the words name one (an officer word -> the officer; another character the beat names -> that one). With none
    named the lead is the plain blue figure: the pack's officer wears a Napoleonic uniform, which is wrong for a story that never says so."""
    if crowd_kind[0] == "soldier":
        if any(k == "officer" for k, _i in chars):
            return "officer"
        return next((k for k, _i in chars if k != "soldier"), "blue")
    return next((k for k, _i in chars if k != crowd_kind[0]), crowd_kind[0])


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
    return {"sets": SET_WORDS_V2, "set_weak": SCENE_WEAK_V2, "props": PROP_WORDS_V2, "prop_height": PROP_HEIGHT, "icons": {**TILE_ICONS_V2, **HISTORY_ICONS_V2}, "choose_scene": choose_scene_v2,
            "prop_for": prop_for_v2, "tile_for": tile_for_v2}
