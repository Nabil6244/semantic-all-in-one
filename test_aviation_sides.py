"""Colour = side (aviation/sides.py): a film's two sides keep one colour in every graphic."""

from aviation import dossier as D
from aviation import planner as P
from aviation import router as R
from aviation import sides as SD

LINES = ["In 1966 Malaysia and Singapore formed one airline together.",
         "Malaysia wanted a domestic network, while Singapore wanted international routes.",
         "In 1965 Singapore became independent from Malaysia."]


def test_two_most_named_countries_are_the_sides():
    s = SD.film_sides(LINES)
    assert s["a"]["id"] == "MY" and s["b"]["id"] == "SG"


def test_falls_back_to_airlines():
    s = SD.film_sides(["Air France grew.", "KLM grew.", "Air France and KLM merged.", "KLM kept its name."])
    assert {s["a"]["id"], s["b"]["id"]} == {"air_france", "klm"}


def test_side_of_and_colours():
    SD.set_film(LINES)
    assert SD.side_of("MY") == "a" and SD.side_of("Singapore") == "b" and SD.side_of("France") == ""
    assert SD.hex_of("a") and SD.hex_of("") == ""


def test_political_map_and_share_bar_use_the_film_colours():
    pl = P.plan([{"scene_no": i + 1, "text": t, "start": i * 6.0, "end": (i + 1) * 6.0} for i, t in enumerate(LINES)],
                [{"mode": "story"}] * 3)
    st = next(s for s in pl.shots if s.get("layer") == "stage.lay_stage")
    pm = next((e for e in st["params"]["elements"] if e["kind"] == "political_map"), None)
    assert pm is not None
    cols = {c["code"]: c.get("color") for c in pm["args"]["countries"]}
    assert cols.get("SG") == SD.HEX["b"] and cols.get("MY") == SD.HEX["a"]
    SD.set_film(LINES)
    _, p = D.pick(R.classify("About 72 percent of the jets were built in Singapore."))
    assert p["parts"][0]["side"] == "b"                                     # Singapore is side b in this film
