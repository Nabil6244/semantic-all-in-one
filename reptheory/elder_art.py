"""Elder Health Theory's Flow pictures, directed by rules (no Gemini call, ever):

    1. one main person    built from random parts per install (cast(): four, kept for every video) or per video (the Elder page switch); every picture of them carries the same verbatim description and is sent with
                          the host's reference picture (made once through Flow, saved in the Rep Theory library, reused by every later video). A picture the
                          user uploads on the Elder page is used instead, for every video: optional, never required.
    2. scene director     the sentence -> a place, an action, the objects it names and a mood (RULES + the card library's 190 topics), not the raw sentence alone
    3. organ / disease    an exact leaflet description per organ (ORGANS) and, for a named disease, its healthy-versus-affected comparison (DISEASES)
    4. shot rotation      wide / medium / hands close-up / still life / with someone / organ, never the same shot twice in a row
    5. quality check      check(): plain white background and one side left empty for the words, from the pixels; a picture that fails is redrawn once with
                          stronger wording (beat_art.prepare, app_section.fetch_pictures) and the first one is kept if the retry is no better.

plan(scenes) sets each scene's host and shot before the prompts are made; prompt(sc) builds the prompt."""
from __future__ import annotations
import hashlib, re, zlib
from pathlib import Path
from typing import Dict, List, Optional

from . import art as A

STYLE = A.ELDER_STYLE
ORGAN_STYLE = A.ELDER_ORGAN_STYLE
REF_STYLE = ("Soft-colour illustration with gentle watercolour shading and clean soft outlines, calm pastel palette of teal, sage, warm peach and navy, plain solid pure white "
             "background (#FFFFFF), warm and respectful, no text, no letters, no numbers, no logos, no watermark, no border")

# ---------------------------------------------------------------- 1. the cast: one of them is the main person of a video

# Every install builds its own people from random parts (no two app users share a face; 2026-11-10): a seed made once per install, saved with the
# per-video switch in <Rep Theory library>/elder_cast.json. Per channel (default): four people from that seed, kept for every video. Per video:
# a new person from the seed and the script (the same script makes the same person, so Generate scenes and Render agree).
import json, random, secrets

NAMES = {"f": "Rose Margaret Helen Amara Grace Linda Carmen Mei Priya Ruth Joan Fatima Elena Sofia Nora Ingrid Beatrice Hana Lucia Doris".split(),
         "m": "Walter Raj George Frank Samuel Harold Carlos Kenji Ahmed Arthur Leon Victor Henry Omar Felix Bernard Tomas Desmond Hiro Malcolm".split()}
AGES = ["early sixties", "mid sixties", "late sixties", "early seventies", "mid seventies", "late seventies", "early eighties"]
ORIGINS = ["white", "Black", "South Asian", "East Asian", "Hispanic", "Middle Eastern", "Mediterranean", "Southeast Asian"]
BUILDS = {"f": ["slim", "petite", "average-build", "sturdy", "tall"], "m": ["slim", "tall", "average-build", "sturdy", "broad-shouldered"]}
HAIR = {"f": ["a short soft white bob", "silver hair in a low bun", "short curly grey hair", "shoulder-length silver hair", "a cropped white pixie cut", "grey hair in a neat braid",
              "wavy salt-and-pepper hair", "short natural grey hair", "a silver chin-length cut with a side parting"],
        "m": ["neat silver hair", "a bald head with a white fringe at the sides", "short grey curls", "thinning white hair combed back", "a salt-and-pepper crew cut", "wavy grey hair",
              "short natural grey hair", "a shaved head"]}
FACE_M = ["clean-shaven", "a short trimmed grey beard", "a neat white moustache", "a grey goatee", "light grey stubble", "a full white beard"]
GLASSES = ["round tortoiseshell glasses", "thin wire glasses", "rectangular black glasses", "no glasses", "rimless glasses", "red-framed glasses", "no glasses"]
COLOURS = ["teal", "coral", "sage-green", "navy", "mustard", "lilac", "burgundy", "sky-blue", "cream", "olive", "rust", "dusty-pink", "forest-green", "charcoal"]
TOPS = {"f": ["cardigan", "knitted sweater", "quilted vest", "linen jacket", "soft fleece"], "m": ["sweater", "quilted vest", "cardigan", "zip-up fleece", "linen jacket"]}
SHIRTS = {"f": ["blouse", "collared shirt", "plain top", "striped top", "polo shirt", "checked shirt"], "m": ["collared shirt", "plain T-shirt", "striped shirt", "polo shirt", "checked shirt"]}
BOTTOMS = ["navy trousers", "khaki trousers", "dark grey trousers", "beige chinos", "dark jeans", "brown corduroy trousers"]
EXTRAS = {"f": ["small pearl earrings", "gold stud earrings", "a silver wristwatch", "a patterned scarf", "a beaded necklace", "a simple pendant"],
          "m": ["a silver wristwatch", "a flat cap", "a leather-strap watch", "a patterned scarf", "a wedding ring", "a fabric bracelet"]}

def _state_path() -> Path:
    from . import library as L
    return L.root() / "elder_cast.json"

def _state() -> dict:
    """This install's seed and the per-video switch, made on first use."""
    try: st = json.loads(_state_path().read_text(encoding="utf-8"))
    except Exception: st = {}
    if not st.get("seed"):
        st = {"seed": secrets.token_hex(8), "per_video": bool(st.get("per_video", False))}
        try: _state_path().parent.mkdir(parents=True, exist_ok=True); _state_path().write_text(json.dumps(st, indent=1), encoding="utf-8")
        except OSError: pass
    return st

def per_video() -> bool: return bool(_state().get("per_video"))

def set_per_video(on: bool) -> None:
    """The Elder page's switch: a new main person for every video (True) or this channel's own cast (False). Only remembered; nothing runs."""
    st = _state(); st["per_video"] = bool(on)
    try: _state_path().write_text(json.dumps(st, indent=1), encoding="utf-8")
    except OSError: pass

# ---- the user's own main person: a picture uploaded on the Elder page (optional), used for every video while it is set

OWN_EXT = (".png", ".jpg", ".jpeg", ".webp"); OWN_MIN_SIDE = 256; OWN_MAX_BYTES = 10 * 1024 * 1024      # Flow's reference limits (story_character.py)
OWN_SHEET = "the main older person exactly as in the reference picture: the same face, hair, skin tone, build and clothes"

def own_picture() -> Optional[str]:
    from . import library as L
    for ext in OWN_EXT:
        p = L.root() / f"elder_main_person{ext}"
        if p.is_file(): return str(p)
    return None

def own_sex() -> str: return "m" if _state().get("own_sex") == "m" else "f"

def set_own_sex(sex: str) -> None:
    st = _state(); st["own_sex"] = "m" if sex == "m" else "f"
    try: _state_path().write_text(json.dumps(st, indent=1), encoding="utf-8")
    except OSError: pass

def set_own_picture(src: str) -> str:
    """Copies the chosen picture in as the main person (any earlier one replaced). Returns "" when done, else what is wrong with it."""
    from PIL import Image
    from . import library as L
    p = Path(src); ext = p.suffix.lower()
    if ext not in OWN_EXT: return "Choose a PNG, JPG or WEBP picture."
    if not p.is_file(): return "That file could not be found."
    if p.stat().st_size > OWN_MAX_BYTES: return "That picture is over 10 MB: choose a smaller one."
    try:
        with Image.open(p) as im: im.verify()
        with Image.open(p) as im: w, h = im.size
    except Exception: return "That file is not a picture the app can read."
    if min(w, h) < OWN_MIN_SIDE: return f"That picture is too small ({w}x{h}): at least {OWN_MIN_SIDE} pixels on each side."
    clear_own_picture(); L.root().mkdir(parents=True, exist_ok=True)
    import shutil; shutil.copyfile(p, L.root() / f"elder_main_person{ext}"); return ""

def clear_own_picture() -> None:
    from . import library as L
    for ext in OWN_EXT:
        try: (L.root() / f"elder_main_person{ext}").unlink()
        except OSError: pass

def _own_person() -> Optional[dict]:
    pic = own_picture()
    if not pic: return None
    sex = own_sex(); hid = "own_" + hashlib.sha1(Path(pic).read_bytes()).hexdigest()[:8]
    p = {"id": hid, "sex": sex, "name": "Your main person", "sheet": OWN_SHEET + f" (an older {'woman' if sex == 'f' else 'man'})"}; _EXTRA[hid] = p; return p

def make_person(seed: str, sex: str) -> dict:
    """One older person from random parts: a name and the verbatim description put in every prompt that shows them."""
    r = random.Random(seed); c1, c2 = r.sample(COLOURS, 2); an = lambda w: ("an " if w[0].lower() in "aeiou" else "a ") + w
    noun = "woman" if sex == "f" else "man"; face = "" if sex == "f" else f", {r.choice(FACE_M)}"; gl = r.choice(GLASSES); gl = "" if gl == "no glasses" else f", {gl}"
    name = r.choice(NAMES[sex])
    sheet = (f"{name}, {an(r.choice(BUILDS[sex]))} {r.choice(ORIGINS)} {noun} in {'her' if sex == 'f' else 'his'} {r.choice(AGES)} with {r.choice(HAIR[sex])}{face}{gl}, "
             f"{an(c1)} {r.choice(TOPS[sex])} over {an(c2)} {r.choice(SHIRTS[sex])} and {r.choice(BOTTOMS)}, {r.choice(EXTRAS[sex])}")
    return {"id": "h_" + hashlib.sha1(sheet.encode()).hexdigest()[:8], "sex": sex, "name": name, "sheet": sheet}

COMPANION = {"f": "her husband, a friendly older man with grey hair in a beige sweater", "m": "his wife, a friendly older woman with grey hair in a lilac cardigan"}
_EXTRA: Dict[str, dict] = {}      # per-video people made in this run

def cast() -> Dict[str, dict]:
    """This channel's four people (two women, two men), the same for every video of this install."""
    seed = _state()["seed"]; out = {}
    for k, sex in enumerate("fmfm"):
        p = make_person(f"{seed}:{k}", sex); out[p["id"]] = p
    return out

def person(host: str) -> dict:
    if host.startswith("own_") and host not in _EXTRA: _own_person()
    return _EXTRA.get(host) or cast()[host]

def _people() -> Dict[str, dict]:
    _own_person(); return {**cast(), **_EXTRA}

WOMAN_RX = re.compile(r"\b(she|her|women|woman|ladies|menopaus\w*|grandmother|grandma|wife's)\b", re.I)
MAN_RX = re.compile(r"\b(he|him|his|men|man|prostate|grandfather|grandpa|husband's)\b", re.I)

def pick_host(texts: List[str], prompts: List[str] = ()) -> str:
    """The video's main person: a CSV picture description that says woman / man decides the sex, then the script's own words; per channel one of this install's cast
    (same script, same person), per video a new person from the install's seed and the script."""
    sex = ""
    for src in (" ".join(prompts), " ".join(texts)):
        w, m = len(WOMAN_RX.findall(src)), len(MAN_RX.findall(src))
        if w != m and (w or m): sex = "f" if w > m else "m"; break
    own = _own_person()
    if own: return own["id"]      # the picture the user uploaded: their person in every video
    h = zlib.crc32(" ".join(texts).encode())
    if per_video():
        p = make_person(f"{_state()['seed']}:video:{h}", sex or "fm"[h % 2]); _EXTRA[p["id"]] = p; return p["id"]
    pool = [k for k, v in cast().items() if not sex or v["sex"] == sex]
    return pool[h % len(pool)]

def ref_prompt(host: str) -> str:
    return (f"A character reference picture of {person(host)['sheet']}: the same person shown twice side by side, on the left a full-body front view standing relaxed, "
            f"on the right a head-and-shoulders portrait with a gentle smile. {REF_STYLE}.")

def ref_id(host: str) -> str: return "elderhost_" + host + "_" + hashlib.sha1(ref_prompt(host).encode()).hexdigest()[:8]

def user_ref(host: str) -> Optional[str]:
    """The picture the user uploaded on the Elder page, for their own main person (host id own_...)."""
    return own_picture() if host.startswith("own_") else None

def host_refs(host: str) -> List[str]:
    """The reference picture(s) for this host that exist now: the user's own, else the one the app made. [] until it is made."""
    u = user_ref(host)
    if u: return [u]
    from . import library as L
    got = L.find(ref_id(host)); return [got["path"]] if got and Path(got["path"]).is_file() else []

def ref_key(host: str) -> str:
    """What a host picture's library id depends on besides its prompt: the user's reference file, else the app's reference prompt (known before the picture exists)."""
    u = user_ref(host)
    return "user:" + hashlib.sha1(Path(u).read_bytes()).hexdigest()[:8] if u else "app:" + ref_id(host)

def ensure_refs(host: str, make_one, log=print) -> List[str]:
    """The host's reference, made once through Flow when there is none (make_one(prompt) -> a file path or None), saved in the Rep Theory library."""
    got = host_refs(host)
    if got: return got
    log(f"[ELDER ART] making the reference picture of {person(host)['name']} once" + ("" if host in _EXTRA else " (reused by every later video)"))
    path = make_one(ref_prompt(host))
    if path and Path(path).is_file():
        from . import library as L
        L.register(path, id=ref_id(host), kind="reference", subject=f"Elder Health host {person(host)['name']}", prompt=ref_prompt(host), source="flow", notes="elder host reference")
    else: log(f"[ELDER ART] the reference picture of {person(host)['name']} could not be made: their pictures use the description alone")
    return host_refs(host)

def wants_refs(prompt: str) -> Optional[str]:
    """The host whose description is in this prompt (sent with their reference picture), or None."""
    for k, v in _people().items():
        if v["sheet"] in prompt: return k
    return None

# ---------------------------------------------------------------- 2. the scene director: place, action, objects, shots

# (words, place, action, shots it suits)
RULES = [
    (r"\b(doctor|check-?ups?|blood test|test results?|screening|appointment|clinic|nurse)\b", "a bright, friendly doctor's office", "talking with a kind doctor who is explaining a result", ("together", "medium")),
    (r"\b(blood pressure|cuff)\b", "a calm kitchen table", "checking their own blood pressure with a home cuff on the upper arm", ("close", "medium")),
    (r"\b(blood sugar|glucose|finger prick|meter)\b", "a calm kitchen table", "checking blood sugar with a small glucose meter", ("close", "medium")),
    (r"\b(pills?|medicines?|medications?|tablets?|supplements?|vitamins?|doses?|prescriptions?|statins?|aspirin)\b", "a sunny kitchen table", "sorting pills into a weekly pill organiser beside a glass of water", ("close", "still", "medium")),
    (r"\b(walk\w*|stroll\w*|steps?)\b", "a leafy park path in soft morning light", "walking briskly with good posture and comfortable shoes", ("wide", "medium")),
    (r"\b(stairs|staircase)\b", "a home staircase with a sturdy handrail", "climbing the stairs one step at a time, one hand on the rail", ("wide", "medium")),
    (r"\b(swim\w*|pool|water aerobics)\b", "an indoor swimming pool", "swimming calmly in a lane", ("wide",)),
    (r"\b(danc\w*)\b", "a bright living room", "dancing happily to music", ("wide", "together")),
    (r"\b(cycl\w*|bike|biking)\b", "a quiet countryside cycle path", "riding a bicycle with a helmet", ("wide",)),
    (r"\b(yoga|tai chi|stretch\w*|pilates)\b", "a sunny park lawn in the morning", "doing a slow, gentle stretch", ("wide", "medium")),
    (r"\b(weights?|dumbbells?|resistance bands?|strength|squats?|push-?ups?|lift\w*)\b", "a tidy living room", "doing a gentle strength exercise with light dumbbells", ("medium", "wide")),
    (r"\b(balance|one leg|one foot|steady|wobbl\w*)\b", "a kitchen, beside the counter", "standing on one leg while lightly holding the counter for safety", ("medium", "wide")),
    (r"\b(falls?|falling|trip\w*|slip\w*|grab bars?|rugs?)\b", "a safe, well-lit hallway with a grab bar and no loose rugs", "walking steadily, one hand near the grab bar", ("wide", "medium")),
    (r"\b(sleep\w*|bed(?:time)?|nap\w*|insomnia|night)\b", "a calm bedroom with soft lamp light", "settling into bed with a relaxed face", ("medium", "wide")),
    (r"\b(water|hydrat\w*|thirst\w*|drink (?:a|more) glass)\b", "a bright kitchen", "drinking a tall glass of water", ("medium", "close")),
    (r"\b(cook\w*|recipe|meals?|salt|season\w*)\b", "a warm home kitchen", "cooking a colourful, healthy meal and seasoning it with herbs", ("medium", "close", "still")),
    (r"\b(breakfast)\b", "a sunny breakfast table", "eating a healthy breakfast", ("medium", "still")),
    (r"\b(groceries|grocery|supermarket|shopping|labels?)\b", "a bright grocery store aisle", "reading a food label carefully", ("medium", "close")),
    (r"\b(eat\w*|food|diet|plate|snack\w*)\b", "a dining table by a window", "enjoying a healthy plate of food", ("medium", "still", "close")),
    (r"\b(friends?|family|grandchild\w*|grandkids?|lonel\w*|social\w*|visit\w*)\b", "a cosy living room", "laughing with family and friends", ("together", "wide")),
    (r"\b(read\w*|puzzles?|crosswords?|learn\w*|memory|brain|sharp)\b", "an armchair by a sunny window", "doing a crossword puzzle with a pencil", ("medium", "close")),
    (r"\b(sun(?:light|shine)?|outdoors|outside|daylight|garden\w*)\b", "a flower garden in morning sunlight", "tending the garden in the sunshine", ("wide", "medium")),
    (r"\b(stress\w*|anxi\w*|worr\w*|breath\w*|calm|relax\w*|meditat\w*)\b", "a quiet room by a window", "sitting upright with eyes closed, breathing slowly", ("medium", "close")),
    (r"\b(teeth|tooth|gums?|floss\w*|brush\w*)\b", "a clean bathroom", "brushing teeth at the mirror", ("medium", "close")),
    (r"\b(eyes?|vision|eyesight|glasses|cataracts?)\b", "an optician's room", "having a gentle eye check", ("medium", "together")),
    (r"\b(hearing|ears?)\b", "a quiet clinic room", "having a hearing check with headphones", ("medium",)),
    (r"\b(phone|call)\b", "a cosy armchair at home", "calling the doctor on the phone", ("medium", "close")),
    (r"\b(pain|aches?|stiff\w*|sore\w*|joints?|knees?|back|hips?)\b", "a bright living room", "gently rubbing a stiff knee while sitting on the sofa", ("medium", "close")),
]
RULES = [(re.compile(rx, re.I), place, action, shots) for rx, place, action, shots in RULES]
WORRY_RX = re.compile(r"\b(worr\w*|danger\w*|risk\w*|warning|harm\w*|damag\w*|silent\w*|problem|mistake|never|don'?t|stop|avoid|pain|hurts?|sick|ill)\b", re.I)
SHOT_TEXT = {
    "wide": "Wide shot: the whole setting visible, the person shown full length",
    "medium": "Medium shot from the waist up",
    "close": "Close-up on the hands and the objects they hold, the face out of frame or soft at the edge",
    "still": "A still life of the objects only, neatly arranged, no person",
    "together": "Medium shot of the person together with {companion}",
}

def _objects(text: str) -> List[str]:
    """The concrete things the sentence names, read through the card library's topics (foods, pills, ...), as picture nouns."""
    from . import health_lib as HL
    out = []
    for sp in HL.TOPICS.values():
        if sp["engine"] in ("foods", "pills") and sp["rx"].search(text):
            noun = (f"a bowl or plate of {sp['label'].lower()}" if sp["engine"] == "foods" else f"a bottle of {sp['label'].lower()} {'softgels' if sp.get('shape') == 'softgel' else 'pills'}")
            if noun not in out: out.append(noun)
    return out[:4]

def scene_of(text: str) -> dict:
    """place, action, objects, the shots that suit it, mood."""
    rule = next((r for r in RULES if r[0].search(text)), None)
    place, action, shots = (rule[1], rule[2], rule[3]) if rule else ("a bright, tidy living room", "going about the day, calm and well", ("medium", "wide"))
    objs = _objects(text)
    if objs and not rule: place, action, shots = "a dining table by a window", "about to enjoy " + objs[0], ("still", "medium", "close")
    mood = "with a thoughtful, slightly concerned expression" if WORRY_RX.search(text) else "looking content and relaxed"
    return {"place": place, "action": action, "objects": objs, "shots": shots, "mood": mood}

# ---------------------------------------------------------------- 3. organs and diseases

ORGANS = {
    "heart": "a healthy human heart with its coronary arteries running over the surface, the arteries highlighted in teal",
    "arteries": "a cut-away of an artery showing its smooth inner wall and red blood cells flowing freely, the wall highlighted in teal",
    "veins": "a cut-away of a leg vein with its small one-way valves, blood flowing upward, the valves highlighted in teal",
    "lungs": "a pair of healthy lungs with the airway branching into them like a tree, the small air sacs shown in a magnified circle",
    "liver": "a healthy liver beside the gallbladder, smooth and reddish-brown, its lobes clearly shaped",
    "kidneys": "a pair of kidneys with a cross-section of one showing the filtering layers inside, the filters highlighted in teal",
    "bladder": "the bladder and the kidneys connected by thin tubes, seen from the front",
    "prostate": "a simple side view of the male bladder and the small prostate gland beneath it, the prostate highlighted in teal",
    "brain": "a healthy human brain seen from the side, with a magnified circle of brain cells linked by glowing connections",
    "stomach": "the stomach and the start of the intestines, seen from the front",
    "gut": "the large and small intestines, with a magnified circle of friendly gut bacteria on the gut lining",
    "pancreas": "the pancreas lying behind the stomach, with a magnified circle of cells releasing insulin",
    "thyroid": "the butterfly-shaped thyroid gland at the front of the neck, highlighted in teal",
    "bones": "a cross-section of a healthy bone showing its dense honeycomb inside, the honeycomb highlighted in teal",
    "joints": "a cross-section of a healthy knee joint showing the thigh bone, the shin bone and the smooth cartilage cushion between them, the cartilage highlighted in teal",
    "spine": "the spine seen from the side with its discs between the vertebrae, the discs highlighted in teal",
    "eyes": "a cross-section of the human eye showing the clear lens and the retina at the back, the lens highlighted in teal",
    "ears": "a cut-away of the ear showing the ear canal, the eardrum and the snail-shaped inner ear, the inner ear highlighted in teal",
    "skin": "a cut-away of skin in layers with the springy collagen fibres in the middle layer, the collagen highlighted in teal",
    "muscles": "a cut-away of the thigh muscle showing its bundles of fibres, the fibres highlighted in teal",
    "teeth": "a cut-away of a tooth in the gum showing the root and the healthy pink gum line",
}
ORGAN_WORDS = {"heart": "heart", "arter": "arteries", "blood vessel": "arteries", "vein": "veins", "lung": "lungs", "liver": "liver", "kidney": "kidneys", "bladder": "bladder",
               "prostate": "prostate", "brain": "brain", "stomach": "stomach", "gut": "gut", "intestin": "gut", "colon": "gut", "pancreas": "pancreas", "thyroid": "thyroid",
               "bone": "bones", "joint": "joints", "knee": "joints", "hip": "joints", "cartilage": "joints", "spine": "spine", "eye": "eyes", "retina": "eyes", "ear": "ears",
               "skin": "skin", "muscle": "muscles", "teeth": "teeth", "tooth": "teeth", "gum": "teeth"}
ORGAN_RX = re.compile(r"\b(" + "|".join(sorted(ORGAN_WORDS, key=len, reverse=True)) + r")\w*", re.I)
DAILY_RX = re.compile(r"\b(walk\w*|eat\w*|drink\w*|sleep\w*|sit\w*|stand\w*|cook\w*|stretch\w*|garden\w*|doctor|take|taking|try|you can|start)\b", re.I)

# disease topic id -> (organ, what the affected side shows)
DISEASES = {
    "dz_osteoarthritis": ("joints", "the cartilage worn thin and rough, the bone ends closer together"), "dz_rheumatoid": ("joints", "a swollen, inflamed joint lining"),
    "dz_osteoporosis": ("bones", "the honeycomb thin and full of large holes"), "dz_gout": ("joints", "small needle-shaped crystals in the joint of the big toe"),
    "dz_sarcopenia": ("muscles", "thinner, smaller muscle fibre bundles"), "dz_diabetes": ("pancreas", "cells that ignore the insulin, sugar left outside them in the blood"),
    "dz_hypertension": ("arteries", "a stiff, thickened artery wall under strain"), "dz_heart_failure": ("heart", "an enlarged heart with a thin, weakened wall"),
    "dz_afib": ("heart", "the upper chambers quivering with uneven signals"), "dz_heart_disease": ("arteries", "yellow plaque narrowing the artery"),
    "dz_pad": ("arteries", "a narrowed leg artery with plaque"), "dz_dvt": ("veins", "a dark red clot blocking a deep leg vein"),
    "dz_varicose": ("veins", "a swollen, twisting vein with leaking valves"), "dz_anemia": ("arteries", "far fewer, paler red blood cells"),
    "dz_stroke": ("brain", "a blocked vessel and a darker area of the brain without blood"), "dz_alzheimers": ("brain", "fewer brain cell connections and small patches of plaque"),
    "dz_dementia": ("brain", "fewer brain cell connections"), "dz_parkinsons": ("brain", "the small movement centre deep in the brain fading"),
    "dz_depression": ("brain", "dimmer, quieter brain cell signals"), "dz_copd": ("lungs", "narrowed airways and enlarged, damaged air sacs"),
    "dz_asthma": ("lungs", "a swollen, tightened airway"), "dz_pneumonia": ("lungs", "air sacs filled with fluid"), "dz_sleep_apnea": ("lungs", "the airway at the back of the throat closing in sleep"),
    "dz_kidney": ("kidneys", "smaller, scarred kidneys with fewer working filters"), "dz_fatty_liver": ("liver", "a pale, swollen liver with fat droplets"),
    "dz_reflux": ("stomach", "stomach acid rising back up into the food pipe"), "dz_diverticulitis": ("gut", "small inflamed pouches on the colon wall"),
    "dz_constipation": ("gut", "a slow, crowded bowel"), "dz_cataracts": ("eyes", "a cloudy, milky lens"), "dz_glaucoma": ("eyes", "pressure pressing on the optic nerve at the back"),
    "dz_macular": ("eyes", "a damaged spot in the centre of the retina"), "dz_hearing": ("ears", "worn, flattened hair cells in the inner ear"),
    "dz_gum": ("teeth", "red, swollen gums pulling back from the tooth"), "dz_shingles": ("skin", "a band of small blisters along one nerve"),
    "dz_skin_cancer": ("skin", "an uneven, dark spot with irregular edges"),
}

PROBLEM_WORDS = {      # the problem said without the disease's name -> the disease picture that shows it
    "dz_heart_disease": r"plaque|clog\w*|narrow(?:ed|ing|s)? arter\w*|harden\w* arter\w*", "dz_osteoporosis": r"brittle|thin(?:ning|ner)? bones?|bones? (?:get|grow|become) (?:thin|weak)\w*",
    "dz_osteoarthritis": r"cartilage (?:wears|thins|breaks)\w*|worn(?:-| )out (?:knee|joint)s?", "dz_fatty_liver": r"fat (?:in|builds up in|around) (?:your|the) liver",
    "dz_cataracts": r"cloudy lens|lens (?:clouds|gets cloudy)", "dz_sarcopenia": r"(?:lose|losing|lost) muscle|muscles? (?:shrink|weaken)\w*",
    "dz_gum": r"bleeding gums|gums? (?:bleed|recede|swell)\w*", "dz_dvt": r"clots? in (?:your|the) legs?"}
PROBLEM_WORDS = {k: re.compile(r"\b(?:" + v + r")\b", re.I) for k, v in PROBLEM_WORDS.items()}

def organ_prompt(text: str) -> Optional[str]:
    """A leaflet picture for a sentence about the inside of the body: the named disease as healthy-versus-affected, else the named organ, exactly. None for daily life."""
    from . import health_lib as HL
    if DAILY_RX.search(text): return None
    for tid, (organ, affected) in DISEASES.items():
        if HL.TOPICS[tid]["rx"].search(text) or (tid in PROBLEM_WORDS and PROBLEM_WORDS[tid].search(text)):
            return (f"A side-by-side medical comparison for an elder health explainer: on the left {ORGANS[organ]}, and on the right the same view "
                    f"with {HL.TOPICS[tid]['label'].lower()}: {affected}. Clean, friendly, accurate, the difference obvious at a glance. {ORGAN_STYLE}.")
    m = ORGAN_RX.search(text)
    if not m: return None
    organ = ORGAN_WORDS[m.group(1).lower()]
    return f"A clear medical illustration for an elder health explainer: {ORGANS[organ]}. Clean, friendly and accurate, like a patient leaflet. {ORGAN_STYLE}."

# ---------------------------------------------------------------- 4. the plan: one host, shots that never repeat back to back

def plan(scenes: List[dict]) -> str:
    """Sets sc["elder_host"] and sc["elder_shot"] on every scene, in order. Returns the host id."""
    texts = [sc.get("text", "") for sc in scenes]; host = pick_host(texts, [sc.get("flow_prompt") or "" for sc in scenes]); prev = prev2 = ""
    for sc in scenes:
        txt = sc.get("text", ""); sc["elder_host"] = host
        if organ_prompt(txt) and not sc.get("hook"): shot = "organ"
        else:
            want = list(scene_of(txt)["shots"]) + ["medium", "wide", "close"]
            if sc.get("hook"): want = ["medium", "wide"]
            shot = next((s for s in want if s != prev and s != prev2), next((s for s in want if s != prev), want[0]))
        sc["elder_shot"] = shot; prev2, prev = prev, shot
    return host

def prompt(sc: dict) -> str:
    """The Flow prompt for one scene from its sentence: an organ / disease leaflet, or the host in a directed scene."""
    text = re.sub(r"\s+", " ", sc.get("text", "")).strip().rstrip("."); host = sc.get("elder_host") or pick_host([text]); shot = sc.get("elder_shot") or "medium"
    if shot == "organ":
        op = organ_prompt(text)
        if op: return op
        shot = "medium"
    s = scene_of(text); who = person(host)["sheet"]; comp = COMPANION[person(host)["sex"]]
    objs = (" Clearly drawn: " + ", ".join(s["objects"]) + ".") if s["objects"] else ""
    lead = "The opening image of an elder health explainer, one warm, inviting picture" if sc.get("hook") else "A single scene from an elder health explainer"
    if shot == "still":
        things = ", ".join(s["objects"]) or "the objects of this moment"
        return f"{lead}: {SHOT_TEXT['still']}: {things}, on a small patch of clean table drawn as a soft vignette on the white. The moment: \"{text}\". {STYLE}."
    framing = SHOT_TEXT[shot].format(companion=comp)
    return (f"{lead}. {framing}. The person is {who}, {s['action']}, {s['mood']}. Setting: {s['place']}, drawn as a soft vignette that fades into the plain white background.{objs} The moment it shows: \"{text}\". "
            f"Healthy, dignified and active, never frail. {STYLE}.")

def own_prompt(text: str, host: Optional[str]) -> str:
    """A CSV picture description: an organ request gets the leaflet style; a person in it is the video's host when it names an older woman / man / person."""
    from .beat_art import _elder_style_for
    style = _elder_style_for(text)
    if host and style == STYLE and re.search(r"\b(older|elderly|senior|woman|man|person|grandmother|grandfather|lady|gentleman|she|he)\b", text, re.I):
        return f"{text}. The main older person is {person(host)['sheet']}. {style}."
    return f"{text}. {style}."

# ---------------------------------------------------------------- 5. the quality check (pixels only: no call, no render time worth noting)

def check(path) -> List[str]:
    """Problems a finished picture has: [] when its background is plain white and one side is left mostly empty for the words."""
    from PIL import Image
    try: im = Image.open(path).convert("RGB")
    except Exception: return ["unreadable"]
    im.thumbnail((240, 240)); w, h = im.size; px = im.load(); out = []
    white = lambda p: min(p) >= 226 and max(p) - min(p) <= 22
    border = [px[x, y] for x in range(w) for y in (0, 1, h - 2, h - 1)] + [px[x, y] for y in range(h) for x in (0, 1, w - 2, w - 1)]
    if sum(map(white, border)) / len(border) < 0.7: out.append("background not plain white")
    side = lambda xs: sum(white(px[x, y]) for x in xs for y in range(0, h, 2)) / (len(xs) * len(range(0, h, 2)))
    third = max(1, w // 3)
    if max(side(range(0, third)), side(range(w - third, w))) < 0.82: out.append("no empty side for the words")
    return out

def stronger(prompt_: str, problems: List[str]) -> str:
    """The redraw wording for a picture that failed check(): the white background and the empty side said again, first."""
    add = []
    if "background not plain white" in problems: add.append("The background must be plain solid pure white (#FFFFFF) from edge to edge: no room, no wall, no floor, no shadow, no scenery behind")
    if "no empty side for the words" in problems: add.append("Keep the left third of the frame completely empty white: everything drawn sits in the right two thirds")
    return (". ".join(add) + ". " + prompt_) if add else prompt_
