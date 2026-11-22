"""Places: simple sets built from props, drawn faintly behind the figures.

Each item is (prop, x, base, size): x in screen widths, base = height of the prop's
bottom above the ground line and size = prop box, both in screen heights.
Items sit at the edges and back so the acting space in the middle stays clear.
'sky' is the Colour Pop backdrop colour for the place.
"""
PLACES = {
    "void": {"sky": (236, 241, 248), "items": []},
    "bedroom": {"sky": (247, 228, 208), "items": [
        ("window", 0.16, 0.20, 0.22), ("bed", 0.86, 0.0, 0.26), ("lamp", 0.07, 0.0, 0.2), ("frame", 0.5, 0.42, 0.1)]},
    "kitchen": {"sky": (214, 236, 226), "items": [
        ("fridge", 0.08, 0.0, 0.34), ("counter", 0.86, 0.0, 0.2), ("cup", 0.82, 0.21, 0.06),
        ("window", 0.5, 0.26, 0.16), ("plant", 0.94, 0.21, 0.08)]},
    "office": {"sky": (222, 230, 245), "items": [
        ("desk", 0.86, 0.0, 0.24), ("laptop", 0.84, 0.205, 0.08), ("plant", 0.08, 0.0, 0.16),
        ("board", 0.5, 0.26, 0.2), ("lamp", 0.96, 0.21, 0.08)]},
    "street": {"sky": (205, 226, 245), "items": [
        ("building", 0.08, 0.0, 0.5), ("building", 0.92, 0.0, 0.42), ("streetlamp", 0.2, 0.0, 0.34),
        ("cloud", 0.55, 0.42, 0.12), ("car", 0.8, 0.0, 0.12)]},
    "park": {"sky": (200, 235, 250), "items": [
        ("tree", 0.08, 0.0, 0.42), ("tree", 0.93, 0.0, 0.34), ("bench", 0.8, 0.0, 0.12), ("sun", 0.86, 0.46, 0.12),
        ("cloud", 0.3, 0.44, 0.12)]},
    "city_night": {"sky": (40, 48, 84), "items": [
        ("building", 0.06, 0.0, 0.46), ("building", 0.2, 0.0, 0.3), ("building", 0.82, 0.0, 0.36),
        ("building", 0.95, 0.0, 0.5), ("moon", 0.6, 0.46, 0.1), ("star", 0.4, 0.5, 0.04), ("star", 0.72, 0.4, 0.03)]},
    "classroom": {"sky": (240, 232, 205), "items": [
        ("board", 0.5, 0.22, 0.24), ("desk", 0.1, 0.0, 0.18), ("book", 0.1, 0.17, 0.06), ("clock", 0.9, 0.36, 0.08)]},
}

# words in a sentence that suggest a place
WORDS = {
    "bedroom": "sleep sleeps slept bed wake woke night tired dream pillow bedtime alarm",
    "kitchen": "coffee cup lunch breakfast dinner eat eating food cook kitchen drink sugar",
    "office": "work job boss office laptop email meeting desk money salary computer",
    "street": "city street walk car traffic country travel flying trip outside road",
    "park": "park outside sun weekend weekends tree run exercise fresh walk saturday sunday",
    "city_night": "midnight late dark night lights",
    "classroom": "learn school class study lesson test teacher habit habits",
}
_W = {}
for _p, _ws in WORDS.items():
    for _w in _ws.split():
        _W.setdefault(_w, []).append(_p)


def score(words):
    s = {}
    for w in words:
        for p in _W.get(w, []):
            s[p] = s.get(p, 0) + 1
    return s
