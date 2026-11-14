"""Sea-animal catalogue for Ocean Predators: every animal a script may name, so any topic works, not just sharks and orcas.

    SPECIES                 {key: Species}   pattern (what the narrator says), desc (Flow prompt words), base (the code
                                             drawing used only until its painted picture exists), family (for "sharks" /
                                             "whales" meaning the story's own species), jaw (gets a mouth-open picture)
    get(key) -> Species | None
    family(key) -> str      "shark" / "whale" / "squid" / ... or ""
    patterns() -> [(regex, key, args)]   for ocean/reader.py, longest first, generic words last

The painted pictures live in assets/ocean/art/<key>_<pose>.png (ocean/art_flow.py); a script naming an animal that has no
picture yet gets it made on Generate. An animal not in this list is not drawn (never the wrong animal).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class Species:
    key: str
    pattern: str
    desc: str
    base: str = "shark"          # code drawing until the painted picture exists (ocean/animals.py SPECS)
    family: str = ""
    jaw: bool = False


def _s(key, pattern, desc, base="shark", family="", jaw=False):
    return Species(key, pattern, desc, base, family, jaw)


_LIST: List[Species] = [
    # sharks
    _s("great_white", r"great white sharks?|great whites?|white sharks?", "great white shark (Carcharodon carcharias): grey back, sharp white belly "
       "with a torn uneven edge, black eye, a few pale scars", "shark", "shark", True),
    _s("megalodon", r"megalodons?|megatooth sharks?|otodus(?: \w+)?", "megalodon, a gigantic prehistoric shark: massive dark "
       "grey body, broad head, many old scars", "megalodon", "shark", True),
    _s("tiger_shark", r"tiger sharks?", "tiger shark: blunt square snout, grey-brown body with dark vertical stripes", "shark", "shark", True),
    _s("bull_shark", r"bull sharks?", "bull shark: stocky heavy grey body, short blunt snout, small eyes", "shark", "shark", True),
    _s("hammerhead", r"(?:great |scalloped )?hammerheads?(?: sharks?)?", "great hammerhead shark: wide flat hammer-shaped head "
       "with eyes at the ends, tall curved dorsal fin", "shark", "shark", True),
    _s("mako_shark", r"(?:shortfin |longfin )?makos?(?: sharks?)?", "shortfin mako shark: sleek metallic blue back, white belly, "
       "pointed snout, big black eye", "shark", "shark", True),
    _s("whale_shark", r"whale sharks?", "whale shark: huge broad flat head, dark grey-blue skin covered in white spots and "
       "pale stripes", "shark", "shark"),
    _s("basking_shark", r"basking sharks?", "basking shark: huge grey body, enormous gaping mouth, long gill slits", "shark", "shark"),
    _s("greenland_shark", r"greenland sharks?", "Greenland shark: slow heavy dark grey-brown body, small fins, tiny pale eye, "
       "very old scarred skin", "shark", "shark"),
    _s("goblin_shark", r"goblin sharks?", "goblin shark: pink-grey body, long flat blade-like snout, protruding jaw with needle "
       "teeth", "shark", "shark", True),
    _s("thresher_shark", r"thresher sharks?", "thresher shark: very long whip-like upper tail lobe, big eyes, grey-purple back",
       "shark", "shark"),
    _s("blue_shark", r"blue sharks?", "blue shark: slender bright indigo-blue body, long pointed snout, long pectoral fins",
       "shark", "shark"),
    _s("oceanic_whitetip", r"oceanic whitetips?|whitetip sharks?", "oceanic whitetip shark: bronze-grey body, very long rounded "
       "white-tipped fins", "shark", "shark", True),
    _s("lemon_shark", r"lemon sharks?", "lemon shark: yellow-brown body, two dorsal fins of similar size, blunt snout", "shark", "shark"),
    _s("nurse_shark", r"nurse sharks?", "nurse shark: brown flattened body, small barbels by the mouth, resting look", "shark", "shark"),
    _s("sand_tiger", r"sand tiger sharks?|ragged-tooth sharks?", "sand tiger shark: bulky light brown body with dark spots, "
       "crooked protruding teeth", "shark", "shark", True),
    _s("cookiecutter_shark", r"cookiecutter sharks?|cookie-cutter sharks?", "cookiecutter shark: small cigar-shaped brown "
       "shark with a dark collar and big round lips", "shark", "shark"),
    _s("shark", r"reef sharks?|grey reef sharks?|blacktip sharks?", "grey reef shark: slim grey body, pale belly, dark fin tips",
       "shark", "shark", True),
    # whales and dolphins
    _s("orca", r"killer whales?|orcas?", "orca (killer whale): glossy black body, white eye patch, white belly, grey saddle "
       "patch, tall dorsal fin", "orca", "whale", True),
    _s("humpback", r"humpbacks?(?: whales?)?", "humpback whale: dark grey body with knobbly head, very long white pectoral "
       "fins, throat grooves, barnacles", "humpback", "whale"),
    _s("sperm_whale", r"sperm whales?|cachalots?", "sperm whale: huge square head, wrinkled dark grey-brown skin, small lower "
       "jaw, scars from squid suckers", "sperm_whale", "whale"),
    _s("blue_whale", r"blue whales?", "blue whale: enormously long slender blue-grey mottled body, tiny dorsal fin, flat "
       "U-shaped head", "humpback", "whale"),
    _s("fin_whale", r"fin whales?", "fin whale: long sleek dark grey body, pale right jaw, small hooked dorsal fin", "humpback", "whale"),
    _s("minke_whale", r"minke whales?", "minke whale: small sleek dark grey baleen whale, white band on the flippers", "humpback", "whale"),
    _s("grey_whale", r"gr[ae]y whales?", "grey whale: mottled grey body covered with white barnacle patches, no dorsal fin",
       "humpback", "whale"),
    _s("right_whale", r"right whales?", "right whale: stocky black body, no dorsal fin, arched mouth, white callosities on the "
       "head", "humpback", "whale"),
    _s("bowhead", r"bowheads?(?: whales?)?", "bowhead whale: huge dark body, giant bow-shaped white-chinned head", "humpback", "whale"),
    _s("beluga", r"belugas?(?: whales?)?", "beluga whale: pure white body, rounded bulging forehead (melon), no dorsal fin",
       "dolphin", "whale"),
    _s("narwhal", r"narwhals?", "narwhal: mottled grey-white whale with a long spiral tusk from the upper lip", "dolphin", "whale"),
    _s("pilot_whale", r"pilot whales?", "long-finned pilot whale: black body, round bulbous head, long sickle flippers",
       "dolphin", "whale"),
    _s("false_killer_whale", r"false killer whales?", "false killer whale: slender all-black body, rounded head, S-shaped "
       "flippers", "dolphin", "whale", True),
    _s("beaked_whale", r"(?:cuvier'?s )?beaked whales?", "Cuvier's beaked whale: brown-grey body covered in pale scratches, "
       "short beak, small dorsal fin", "dolphin", "whale"),
    _s("dolphin", r"bottlenose dolphins?|dolphins?", "bottlenose dolphin: smooth grey body, lighter belly, curved dorsal fin",
       "dolphin", "dolphin"),
    _s("porpoise", r"porpoises?|vaquitas?", "harbour porpoise: small stocky grey porpoise, small triangular dorsal fin", "dolphin", "dolphin"),
    # seals and other marine mammals
    _s("seal", r"harbou?r seals?|seals?", "harbour seal: spotted grey-brown fur, round head, whiskers, flippers", "seal", "seal"),
    _s("sea_lion", r"sea lions?", "California sea lion: sleek dark brown body, small ear flaps, long front flippers", "seal", "seal"),
    _s("elephant_seal", r"elephant seals?", "male elephant seal: huge grey-brown body, big inflatable trunk-like nose", "seal", "seal"),
    _s("leopard_seal", r"leopard seals?", "leopard seal: long spotted grey body, huge reptile-like head, wide jaws", "seal", "seal", True),
    _s("fur_seal", r"fur seals?", "fur seal: thick dark brown fur, pointed snout, small ears", "seal", "seal"),
    _s("walrus", r"walrus(?:es)?", "walrus: huge wrinkled pinkish-brown body, two long ivory tusks, bristly whiskers", "seal", "seal"),
    _s("sea_otter", r"sea otters?|otters?", "sea otter: thick brown fur, pale whiskered face, floating on its back", "seal", "seal"),
    _s("manatee", r"manatees?|sea cows?|dugongs?", "West Indian manatee: grey wrinkled bulky body, paddle tail, whiskered snout",
       "seal", "seal"),
    _s("polar_bear", r"polar bears?", "polar bear swimming: thick white-cream fur, long neck, black nose", "seal", "bear"),
    # rays and fish
    _s("manta_ray", r"(?:giant )?manta(?: rays?)?|mantas", "giant oceanic manta ray seen from above: wide black diamond wings, "
       "white markings, head fins", "shark", "ray"),
    _s("stingray", r"sting ?rays?|eagle rays?|rays?", "southern stingray seen from above: flat grey-brown diamond body, long thin "
       "whip tail with a barb", "shark", "ray"),
    _s("sawfish", r"sawfish(?:es)?", "sawfish: shark-like grey body with a long flat saw-blade snout lined with teeth", "shark", "ray"),
    _s("tuna", r"(?:bluefin )?tunas?", "Atlantic bluefin tuna: torpedo-shaped metallic dark blue back, silver sides, yellow "
       "finlets", "dolphin", "fish"),
    _s("swordfish", r"swordfish(?:es)?", "swordfish: sleek bronze-grey body, long flat sword bill, tall sickle dorsal fin", "dolphin", "fish"),
    _s("marlin", r"(?:blue |black )?marlins?|sailfish(?:es)?", "blue marlin: cobalt-blue back, silver belly, long spear bill, tall "
       "dorsal fin", "dolphin", "fish"),
    _s("barracuda", r"barracudas?", "great barracuda: long silver body with dark bars, jutting lower jaw full of fangs",
       "dolphin", "fish", True),
    _s("grouper", r"(?:goliath )?groupers?", "goliath grouper: huge heavy olive-brown fish with dark mottling, wide mouth",
       "dolphin", "fish"),
    _s("moray_eel", r"moray(?: eels?)?s?|eels?", "green moray eel: long snake-like green body, open mouth with sharp teeth",
       "dolphin", "fish", True),
    _s("anglerfish", r"angler ?fish(?:es)?|monkfish", "deep-sea anglerfish: dark round body, huge mouth with needle teeth, "
       "glowing lure on a stalk above the head", "dolphin", "fish", True),
    _s("viperfish", r"viper ?fish(?:es)?", "viperfish: slim black deep-sea fish with huge fang teeth that do not fit in its mouth",
       "dolphin", "fish", True),
    _s("gulper_eel", r"gulper eels?|pelican eels?", "gulper eel: black whip-like body with an enormous balloon-like mouth",
       "dolphin", "fish"),
    _s("oarfish", r"oar ?fish(?:es)?", "giant oarfish: very long silver ribbon body with a red crest and red dorsal fin",
       "dolphin", "fish"),
    _s("sunfish", r"(?:ocean )?sunfish(?:es)?|mola(?: mola)?s?", "ocean sunfish (mola): huge flat round grey body, tall top "
       "and bottom fins, no tail", "dolphin", "fish"),
    _s("pufferfish", r"puffer ?fish(?:es)?|blowfish(?:es)?", "pufferfish inflated into a spiky ball, big eyes", "dolphin", "fish"),
    _s("lionfish", r"lion ?fish(?:es)?", "red lionfish: striped red-white body with long venomous feathery spines", "dolphin", "fish"),
    _s("stonefish", r"stone ?fish(?:es)?", "reef stonefish: lumpy mottled brown rock-like fish with venomous spines", "dolphin", "fish"),
    _s("piranha", r"piranhas?", "red-bellied piranha: silver body, red belly, jutting jaw with sharp triangular teeth",
       "dolphin", "fish", True),
    _s("coelacanth", r"coelacanths?", "coelacanth: big dark blue fish with white speckles and fleshy lobed fins", "dolphin", "fish"),
    _s("salmon", r"salmons?", "Atlantic salmon: silver body with small dark spots", "dolphin", "fish"),
    _s("sardine", r"sardines?|herrings?|anchov(?:y|ies)", "sardine: small slim silver fish with a blue-green back", "dolphin", "fish"),
    _s("clownfish", r"clown ?fish(?:es)?", "clownfish: orange with three white bands edged in black", "dolphin", "fish"),
    _s("seahorse", r"sea ?horses?", "seahorse: upright yellow-brown curled body, horse-like head, curled tail", "dolphin", "fish"),
    # cephalopods, jellies, invertebrates
    _s("colossal_squid", r"colossal squids?", "colossal squid: huge deep-red body, enormous eye, thick arms with hooks, trailing "
       "tentacles", "colossal_squid", "squid"),
    _s("giant_squid", r"giant squids?", "giant squid: long red-brown mantle, huge eye, eight arms and two very long tentacles",
       "colossal_squid", "squid"),
    _s("humboldt_squid", r"humboldt squids?|jumbo squids?", "Humboldt squid: red-purple muscular squid, big eyes, arms spread",
       "squid", "squid"),
    _s("vampire_squid", r"vampire squids?", "vampire squid: dark red-black body, webbed cloak between the arms, big blue eyes",
       "squid", "squid"),
    _s("squid", r"squids?", "large red-brown squid: long mantle, big eye, eight arms and two long tentacles trailing behind",
       "squid", "squid"),
    _s("octopus", r"(?:giant pacific )?octop(?:us(?:es)?|i)", "giant Pacific octopus: red-orange wrinkled body, eight long arms "
       "with suckers spread out", "squid", "squid"),
    _s("blue_ringed_octopus", r"blue[- ]ringed octop(?:us(?:es)?|i)", "blue-ringed octopus: small yellow octopus covered with "
       "bright blue rings", "squid", "squid"),
    _s("cuttlefish", r"cuttlefish(?:es)?", "common cuttlefish: oval body with a wavy fin skirt, zebra stripes, W-shaped pupil",
       "squid", "squid"),
    _s("nautilus", r"nautilus(?:es)?", "chambered nautilus: striped cream and brown spiral shell, many small tentacles", "squid", "squid"),
    _s("jellyfish", r"jelly ?fish(?:es)?|jellies", "lion's mane jellyfish: big orange-red bell with very long trailing tentacles",
       "squid", "jelly"),
    _s("box_jellyfish", r"box jelly ?fish(?:es)?|sea wasps?", "box jellyfish: transparent pale-blue cube-shaped bell, long thin "
       "tentacles", "squid", "jelly"),
    _s("man_o_war", r"(?:portuguese )?man[- ]o[f']?[- ]war", "Portuguese man o' war: blue-purple gas float with long blue tentacles",
       "squid", "jelly"),
    _s("crab", r"crabs?", "king crab: spiny red-orange shell, long thick legs, big claws", "squid", "crab"),
    _s("lobster", r"lobsters?", "American lobster: dark blue-green shell, two big claws, long antennae", "squid", "crab"),
    _s("mantis_shrimp", r"mantis shrimps?", "peacock mantis shrimp: rainbow green-red-blue body, club arms folded in front",
       "squid", "crab"),
    _s("isopod", r"giant isopods?|isopods?", "giant deep-sea isopod: pale lilac armoured segmented body like a huge woodlouse",
       "squid", "crab"),
    _s("sea_urchin", r"sea urchins?|urchins?", "purple sea urchin: round body covered with long spines", "squid", "crab"),
    _s("starfish", r"star ?fish(?:es)?|sea stars?", "crown-of-thorns starfish: many-armed spiny purple-red starfish", "squid", "crab"),
    # reptiles, birds, prehistoric
    _s("sea_turtle", r"(?:green |leatherback |loggerhead |hawksbill )?(?:sea )?turtles?", "green sea turtle swimming: olive "
       "brown patterned shell, long front flippers", "seal", "turtle"),
    _s("saltwater_crocodile", r"(?:saltwater |salt-water )?crocodiles?|crocs?|salties", "saltwater crocodile swimming: long "
       "armoured dark olive body, long powerful tail, toothy snout", "seal", "reptile", True),
    _s("sea_snake", r"sea snakes?", "banded sea krait: blue-grey body with black rings, paddle-shaped tail", "dolphin", "reptile"),
    _s("marine_iguana", r"marine iguanas?", "marine iguana: black spiky lizard with a blunt face swimming", "seal", "reptile"),
    _s("penguin", r"(?:emperor |king |gentoo )?penguins?", "emperor penguin swimming underwater: black back, white belly, "
       "yellow-orange neck patch", "seal", "bird"),
    _s("albatross", r"albatross(?:es)?|seagulls?|gulls?|pelicans?", "wandering albatross flying: huge long narrow white wings with "
       "black tips", "dolphin", "bird"),
    _s("mosasaur", r"mosasaurs?(?:us)?", "mosasaur: huge prehistoric marine reptile, long crocodile-like jaws full of teeth, "
       "flippers, shark-like tail", "megalodon", "reptile", True),
    _s("plesiosaur", r"plesiosaurs?|elasmosaurs?(?:us)?", "plesiosaur: prehistoric marine reptile with a very long neck, small "
       "head, four large flippers", "humpback", "reptile"),
    _s("liopleurodon", r"liopleurodons?|pliosaurs?", "Liopleurodon pliosaur: huge prehistoric marine reptile, big crocodile-"
       "like head, four flippers", "megalodon", "reptile", True),
    _s("ichthyosaur", r"ichthyosaurs?", "ichthyosaur: dolphin-shaped prehistoric marine reptile with huge eyes and a long "
       "toothy snout", "dolphin", "reptile"),
    _s("dunkleosteus", r"dunkleosteus", "Dunkleosteus: prehistoric armoured fish with a bony plated head and blade-like jaws",
       "megalodon", "fish", True),
    _s("livyatan", r"livyatans?", "Livyatan melvillei: prehistoric sperm whale with huge teeth in both jaws", "sperm_whale", "whale", True),
]

SPECIES: Dict[str, Species] = {s.key: s for s in _LIST}

# what "sharks", "whales", "squid" alone mean: the story's own species of that family (ocean/planner.py), else this drawing
GENERIC: List[Tuple[str, str, Dict[str, Any]]] = [
    (r"sharks?", "shark", {"generic": "shark"}),
    (r"whales?", "humpback", {"generic": "whale"}),
    (r"fish(?:es)?", "tuna", {"generic": "fish"}),
]
PROPS: List[Tuple[str, str, Dict[str, Any]]] = [
    (r"scuba divers?|divers?|snorkell?ers?|swimmers?|surfers?", "diver", {}),
    (r"boats?|ships?|vessels?|tour operators?|fishing boats?|trawlers?", "boat", {}),
    (r"cages?", "cage", {}),
    (r"fossil(?:ised|ized)? teeth|fossil tooth|tooth", "tooth", {}),
]
PROP_DESC = {
    "diver": "scuba diver in a black wetsuit with tank, mask and fins, swimming horizontally",
    "boat": "small white motor fishing boat with a cabin (a man-made boat, not an animal, no fish, no whale), the full hull "
            "seen side-on",
    "tooth": "single fossil shark tooth, triangular, serrated edges, brown-grey enamel",
    "car": "ordinary silver four-door family sedan car (a man-made car, no animal), the whole car side-on",
    "bus": "ordinary yellow single-deck city bus (a man-made bus, no animal), the whole bus side-on",
}


def get(key: str) -> Optional[Species]:
    return SPECIES.get(key)


def family(key: str) -> str:
    s = SPECIES.get(key)
    return s.family if s else ""


def patterns() -> List[Tuple[str, str, Dict[str, Any]]]:
    """For ocean/reader.py: specific species (longest pattern first, so 'blue-ringed octopus' beats 'octopus'), then the
    generic family words, then props."""
    spec = sorted(((s.pattern, s.key, {}) for s in _LIST), key=lambda p: -len(p[0]))
    return spec + GENERIC + PROPS
