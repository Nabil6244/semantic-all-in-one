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
