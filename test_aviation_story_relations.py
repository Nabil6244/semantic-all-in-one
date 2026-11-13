"""Split tree, ownership, flag argument and who-got-what board (aviation/story_relations.py)."""

from aviation import stage as G
from aviation import story_relations as R

TREE = {"parent": {"airline": "msa", "name": "Malaysia-Singapore Airlines", "years": "1966–1972"},
        "children": [{"airline": "singapore_airlines", "name": "Singapore Airlines", "years": "since 1972"},
                     {"airline": "malaysia_airlines", "name": "Malaysia Airlines", "years": "since 1972"}], "merge": False}
OWN = {"airline": "singapore_airlines", "owners": [{"name": "Malaysia", "code": "MY", "pct": 42.79},
                                                   {"name": "Singapore", "code": "SG", "pct": 42.79},
                                                   {"name": "BOAC", "airline": "boac", "pct": 14.42}]}
BOARD = {"sides": R.split_from("Singapore: international routes, 707s, HQ | Malaysia: domestic network, Fokker 27s")}


def _differs(a, b):
    return a.tobytes() != b.tobytes()


def test_kinds_return_rgba_and_animate():
    for kind, args in (("split_tree", TREE), ("ownership", OWN), ("split_board", BOARD),
                       ("split_tree", dict(TREE, merge=True))):
        a, b = R.G._FACTORIES[kind](dict(args, _k=0.2)), R.G._FACTORIES[kind](dict(args, _k=1.0))
        assert a.mode == "RGBA" and b.mode == "RGBA" and a.size == b.size
        assert _differs(a, b), kind


def test_tree_from_catalog_msa():
    t = R.tree_from_catalog("msa")
    assert t["parent"]["airline"] == "msa" and not t["merge"]
    assert [c["airline"] for c in t["children"]] == ["singapore_airlines", "malaysia_airlines"]
    assert R.tree_from_catalog("nope") is None
    assert R.tree_from_catalog("singapore_airlines")["parent"]["airline"] == "msa"
    assert R.tree_from_catalog("msa", 1970)["parent"]["name"] == "Malaysia-Singapore Airlines"


def test_country_code():
    assert R.country_code("Malaysia") == "MY" and R.country_code("Britain") == "GB" and R.country_code("United Kingdom") == "GB"
    assert R.country_code("sg") == "SG" and R.country_code("Atlantis") == ""
    from aviation import stickers
    assert all(c in stickers.FLAGS for c in R._COUNTRIES) and set(R._COUNTRIES) == set(stickers.FLAGS)


def test_owners_from_list_and_sentence():
    o = R.owners_from("Malaysia 42.79% / Singapore 42.79% / BOAC / Qantas")
    assert [x["name"] for x in o] == ["Malaysia", "Singapore", "BOAC", "Qantas"]
    assert o[0]["code"] == "MY" and o[0]["pct"] == 42.79 and o[2]["airline"] == "boac" and "pct" not in o[3]
    s = R.owners_from("It was a 49% stake held by Singapore Airlines, and the rest stayed local.")
    assert s and s[0]["pct"] == 49.0 and s[0]["airline"] == "singapore_airlines"
    s2 = R.owners_from("Qantas owned 20 percent of the carrier.")
    assert s2[0]["name"] == "Qantas" and s2[0]["pct"] == 20.0
    assert R.owners_from("The airline flew to Tokyo every day.") == [] and R.owners_from("") == []


def test_ownership_counts_up():
    a, b = R.ownership(dict(OWN, _k=0.6)), R.ownership(dict(OWN, _k=1.0))
    assert _differs(a, b)


def test_sides_from_line():
    r = R.sides_from_line("Malaysia wanted a domestic network, while Singapore wanted international routes", ["Malaysia", "Singapore"])
    assert r and r[0]["code"] == "MY" and r[1]["code"] == "SG"
    assert r[0]["text"] == "Malaysia wanted a domestic network" and r[1]["text"].startswith("Singapore wanted")
    r2 = R.sides_from_line("Singapore wanted 4 jets for the hub, but the Malaysian side insisted on a regional network", ["MY", "SG"])
    assert r2 and r2[0]["code"] == "SG" and r2[0]["bold"] == ["4"] and r2[1]["code"] == "MY"
    r3 = R.sides_from_line("Malaysia wanted a domestic network; Singapore wanted international routes", ["Malaysia", "Singapore"])
    assert r3 and r3[1]["code"] == "SG"
    assert R.sides_from_line("Malaysia and Singapore shared the airline for six years", ["Malaysia", "Singapore"]) is None
    assert R.sides_from_line("Malaysia wanted a domestic network", ["Malaysia", "Singapore"]) is None


def test_split_from_guesses_icons():
    s = BOARD["sides"]
    assert [x["code"] for x in s] == ["SG", "MY"]
    assert [i["icon"] for i in s[0]["items"]] == ["route_icon", "aircraft:b707", "building"]
    assert s[1]["items"][0]["icon"] == "route_icon" and s[1]["items"][1]["caption"] == "Fokker 27s"
    assert R._guess_icon("a payment of $2 million") == "cash" and R._guess_icon("cargo") == "cargo"
    assert R.split_from("no colon here") == []
    assert R.split_from("Qantas: shares")[0]["airline"] == "qantas"


def test_add_argument_builds_elements():
    st = G.Stage()
    l = {"code": "MY", "text": "Malaysia wanted a domestic network", "bold": ["domestic"]}
    r = {"code": "SG", "text": "Singapore wanted international routes", "bold": []}
    ids = R.add_argument(st, 1.0, l, r, aircraft={"type": "b707", "airline": "msa"}, step=1.2)
    kinds = [e["kind"] for e in st.params()["elements"]]
    assert kinds.count("hand_flag") == 2 and kinds.count("bubble") == 2 and kinds.count("aircraft") == 1 and len(ids) == 5
    plane = [e for e in st.params()["elements"] if e["kind"] == "aircraft"][0]
    xs = [k[1] for k in plane["keys"]]
    assert min(xs) < 640 < max(xs)                       # tugged both ways
    assert len(R.add_argument(G.Stage(), 0, l, r)) == 4


def test_lay_stage_frames():
    st = G.Stage()
    t = st.add("split_tree", 0.0, TREE, pos=(640, 380), scale=0.9, anim=2.5, edge=False)
    st.year(0.0, 1966)
    p = st.params()
    for tt in (0.5, 1.5, 3.5):
        im = G.lay_stage(tt, 5.0, p)
        assert im is not None and im.size == (G.W, G.H)
    assert _differs(G.lay_stage(0.9, 5.0, p), G.lay_stage(3.5, 5.0, p)) and t
