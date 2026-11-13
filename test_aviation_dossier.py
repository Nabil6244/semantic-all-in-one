"""Dossier cards (aviation/dossier.py): the analysis skin from the J-11 reference."""

from aviation import bridge as BR
from aviation import dossier as D

SAMPLES = {
    "dossier.lay_share": {"title": "Share", "parts": [{"label": "Local", "pct": 72, "side": "a"}, {"label": "Imported", "pct": 28, "side": "b"}]},
    "dossier.lay_range": {"title": "Price", "lo": 1.2, "hi": 2.7, "unit": "$", "suffix": " BN", "note": "No official figure"},
    "dossier.lay_icons": {"title": "Batch", "count": 26, "label": "aircraft"},
    "dossier.lay_markers": {"title": "Dates", "start": 1994, "end": 2004, "markers": [{"year": 1995, "label": "1995"}],
                            "stops": [{"from": 1996, "to": 2003, "label": "Kits", "stopped": True}]},
    "dossier.lay_options": {"title": "Two ways", "options": [{"title": "Buy", "sub": "x"}, {"title": "Licence", "sub": "y"}]},
    "dossier.lay_quotes": {"title": "Claims", "quotes": [{"text": "Close to the original", "who": "a"}, {"text": "Not reliable", "who": "b"}]},
    "dossier.lay_flow": {"title": "Flow", "left": "A", "right": "B", "items": ["Parts", "Engines"]},
    "dossier.lay_family": {"title": "Family", "members": [{"name": "A320", "sub": "base", "type": "a320"}]},
}


def test_every_card_draws_animates_and_is_registered():
    table = BR.card_table()
    for name, p in SAMPLES.items():
        fn = D.CARDS[name]
        assert table[name] is fn
        a, b = fn(0.3, 5.0, p), fn(4.0, 5.0, p)
        assert a is not None and a.size == (D.W, D.H) and a.mode == "RGBA"
        assert a.tobytes() != b.tobytes(), name                          # it moves: never a still screen


def test_empty_params_draw_nothing():
    for name, fn in D.CARDS.items():
        assert fn(1.0, 5.0, {"title": "x"}) is None, name


def test_side_colours_are_fixed():
    assert D.side("a") == D.ORANGE and D.side("b") == D.BLUE and D.side("warn") == D.RED and D.side("x") == D.GREY


def test_icons_fill_to_the_count():
    assert D.icons_shown(26, 1, 1.0) == 26 and D.icons_shown(26, 1, 0.5) == 13 and D.icons_shown(600, 5, 1.0) == 40


def test_grid_is_faint():
    bg = D._backdrop(D.W, D.H).convert("RGB")
    assert max(max(px) for px in bg.resize((64, 36)).getdata()) < 80          # no bright grid lines


def _scenes(lines, step=7.0, **kw):
    return [dict({"scene_no": i + 1, "text": t, "start": i * step, "end": (i + 1) * step}, **kw) for i, t in enumerate(lines)]


def test_pick_follows_the_lines_own_numbers():
    from aviation import router as R
    assert D.pick(R.classify("Estimates of the deal range between $1.2 billion and $2.7 billion."))[0] == "dossier.lay_range"
    assert D.pick(R.classify("About 72 percent of the aircraft was made in China."))[0] == "dossier.lay_share"
    assert D.pick(R.classify("China ordered 26 aircraft in the first batch."))[1]["count"] == 26
    assert D.pick(R.classify("Singapore Airlines flew to London.")) is None


def test_news_number_cards_rotate_skins():
    from aviation import planner as P
    lines = ["Air France reported a profit of $4 million, up from $2 million, in 2015.",
             "Estimates of the Air France deal range between $1.2 billion and $2.7 billion.",
             "Air France ordered 26 aircraft in the first batch in 2016.",
             "Air France said profit rose from $5 million to $9 million in 2017."]
    pl = P.plan(_scenes(lines, has_clip=False, mode="news"), [{"mode": "news"}] * 4)
    layers = [s["layer"] for s in pl.shots if s.get("layer", "").startswith(("dossier.", "gfx_air."))]
    assert any(x.startswith("dossier.") for x in layers) and any(x.startswith("gfx_air.") for x in layers)


def test_story_line_with_a_figure_gets_a_dossier_cut():
    from aviation import planner as P
    lines = ["In 1966 the two governments formed Malaysia-Singapore Airlines together.",
             "Estimates of the cost of the joint airline range between $1.2 million and $2.7 million.",
             "By 1972 the joint airline split into Singapore Airlines and Malaysia Airlines."]
    pl = P.plan(_scenes(lines), [{"mode": "story"}] * 3)
    cards = [s for s in pl.shots if str(s.get("layer", "")).startswith("dossier.")]
    stages = [s for s in pl.shots if s.get("layer") == "stage.lay_stage"]
    assert cards and cards[0]["scene"] == 2 and len(stages) == 2


def test_newspaper_and_reveal_cards():
    from aviation import router as R
    p = {"title": "The press", "outlet": "The Straits Times", "date": "1972", "headline": "One airline becomes two", "split": "becomes"}
    a, b = D.lay_newspaper(0.2, 5.0, p), D.lay_newspaper(3.0, 5.0, p)
    assert a.tobytes() != b.tobytes() and D.lay_newspaper(1.0, 5.0, {"title": "x"}) is None
    name, rp = D.pick(R.classify("Air France turned its Airbus A340 fleet into an Airbus A350 fleet."))
    assert name == "dossier.lay_reveal" and rp["from"]["type"] == "a340" and rp["to"]["type"] == "a350"
    assert D.lay_reveal(0.5, 4.0, rp).tobytes() != D.lay_reveal(3.5, 4.0, rp).tobytes()


def test_article_without_a_page_rotates_to_the_newspaper_card():
    from aviation import planner as P
    lines = ["Air France confirmed plans to cut 2,900 jobs in 2015.", "Air France launched Joon in 2017."]
    rows = [{"mode": "news", "article": {"outlet": "The Guardian", "headline": "Air France to cut 2,900 jobs", "date": "2015"}},
            {"mode": "news", "article": {"outlet": "Reuters", "headline": "Air France launches Joon", "date": "2017"}}]
    pl = P.plan(_scenes(lines, step=10.0), rows)
    layers = [s["layer"] for s in pl.shots if s.get("layer") in ("dossier.lay_newspaper", "cards.lay_article")]
    assert "dossier.lay_newspaper" in layers and "cards.lay_article" in layers


def test_framed_photo_for_a_non_wide_picture(tmp_path):
    from PIL import Image
    from aviation import storycards as K
    p = tmp_path / "old.png"
    Image.new("RGB", (600, 600), (200, 60, 40)).save(p)
    im = K.photo_full({"image": str(p), "_k": 0.5})
    assert im.getpixel((640, 360))[:3] == (200, 60, 40)                       # the whole photo is in the middle
    assert im.getpixel((20, 360))[0] < 120                                   # its blurred, darkened copy fills the sides


def test_part_callouts_from_the_lines_words():
    from aviation import router as R
    name, p = D.pick(R.classify("The Boeing 747 is about 70 m long, with its cockpit up front and four engines under the wings."))
    assert name == "dossier.lay_callouts" and p["type"] == "b747" and p["length_m"] == 70.0
    assert set(p["parts"]) == {"cockpit", "engines", "wings"}
    assert D.parts_in("Singapore Airlines flew to London.") == []
    a, b = D.lay_callouts(0.5, 5.0, p), D.lay_callouts(4.5, 5.0, p)
    assert a.tobytes() != b.tobytes() and D.lay_callouts(1.0, 5.0, {"parts": ["wings"]}) is None   # needs an aircraft


def test_csv_asks_for_dossier_cards():
    from aviation import planner as P, router as R
    c = R.classify("That is why three airline groups raised their hands.")
    m = D.from_csv("markers", c, {"split": "Nov 2025: three bidders | Apr 2026: IAG out | Oct 2026: Lufthansa chosen"})
    assert m[0] == "dossier.lay_markers" and [x["year"] for x in m[1]["markers"]] == [2025, 2026, 2026]
    f = D.from_csv("family", c, {"split": "Lufthansa | Swiss | Austrian | TAP Air Portugal"})
    assert [x["airline"] for x in f[1]["members"]] == ["lufthansa", "swiss", "austrian", "tap"]
    o = D.from_csv("options", c, {"split": "Air France-KLM: its only hub in southern Europe | Lufthansa: South Atlantic routes"})
    assert [x["title"] for x in o[1]["options"]] == ["Air France-KLM", "Lufthansa"]
    pl = P.plan(_scenes(["That is why three airline groups raised their hands.", "Lufthansa won."]),
                [{"mode": "news", "graphic": "markers", "split": "Nov 2025: three bidders | Oct 2026: Lufthansa chosen"}, {"mode": "news"}])
    assert any(s.get("layer") == "dossier.lay_markers" for s in pl.shots)
