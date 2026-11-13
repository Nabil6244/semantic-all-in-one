"""Story director: story stretches become one evolving sticker stage (aviation/story.py + planner hookup)."""

from aviation import planner as P
from aviation import router as R
from aviation import stage as G
from aviation import story as ST

LINES = [
    "In 1947 Malayan Airways was founded in Singapore.",
    "In 1963 it was renamed Malaysian Airways when Malaysia was formed.",
    "In 1966 the two governments formed Malaysia-Singapore Airlines together.",
    "Malaysia wanted a domestic network, while Singapore wanted international routes.",
    "By 1972 the joint airline split into Singapore Airlines and Malaysia Airlines.",
]


def _scenes(lines, step=6.0):
    return [{"scene_no": i + 1, "text": t, "start": i * step, "end": (i + 1) * step} for i, t in enumerate(lines)]


def test_countries_in_skips_airline_names():
    assert ST.countries_in("Malaysia wanted routes, while Singapore wanted jets") == ["MY", "SG"]
    assert ST.countries_in("Singapore Airlines flew to London") == []
    assert ST.countries_in("Britain and the Malaysian government") == ["GB", "MY"]


def test_era_type():
    assert ST.era_type(1950) == "dc3" and ST.era_type(1966) == "b707" and ST.era_type(2020) == "a350"


def test_story_lines_make_one_stage_shot():
    sc = _scenes(LINES)
    pl = P.plan(sc)
    assert all(m == "story" for m in pl.modes), pl.modes
    stages = [s for s in pl.shots if s.get("layer") == "stage.lay_stage"]
    assert len(stages) == 1
    st = stages[0]
    assert st["start"] == 0.0 and st["end"] == 30.0 and st["full_frame"]
    assert not [s for s in pl.shots if s.get("kind") == "footage"]          # no news clips on story lines
    years = [y for _, y in st["params"]["years"]]
    assert years[:3] == ["1947", "1963", "1966"] and "1972" in years
    kinds = {e["kind"] for e in st["params"]["elements"]}
    assert "logo_card" in kinds or "aircraft" in kinds
    assert all(L.get("stage") for L in pl.log)                             # every line says what it did on the stage
    assert st["cues"] and all(st["start"] <= t <= st["end"] + 1 for t, _ in st["cues"])


def test_stage_renders_through_whole_stretch():
    pl = P.plan(_scenes(LINES))
    st = next(s for s in pl.shots if s.get("layer") == "stage.lay_stage")
    dur = st["end"] - st["start"]
    for t in (0.5, 7.0, 13.0, 19.0, 25.0, 29.5):
        im = G.lay_stage(t, dur, st["params"])
        assert im is not None and im.size == (G.W, G.H)


def test_row_never_holds_more_than_max():
    lines = ["In 1970 Air France flew the Boeing 707.", "KLM flew the Boeing 747 in 1971.",
             "Lufthansa flew the Airbus A300 in 1974.", "British Airways was formed in 1974 from BOAC.",
             "Qantas flew the Boeing 747 in 1975."]
    sc = _scenes(lines)
    cls = R.route_script(lines)
    shot, log = ST.build(sc, cls, None, 0, len(lines) - 1)
    stg = G.Stage()
    els = shot["params"]["elements"]
    for t in (5.0, 11.0, 17.0, 23.0, 29.0):
        live = [e for e in els if G.transform(e, t) is not None and e["kind"] == "aircraft"]
        assert len(live) <= ST.MAX_STICKERS + 1                              # +1: one may still be sliding out


def test_stretch_naming_nothing_never_blank():
    sc = _scenes(["It was a strange time for everyone involved in the founding."])
    cls = R.route_script([sc[0]["text"]])
    shot, _ = ST.build(sc, cls, None, 0, 0)
    assert shot["params"]["elements"]


def test_numbers_on_a_story_line_use_the_sticker_skin():
    lines = ["In 1966 Malaysia-Singapore Airlines was formed by the two governments.",
             "By 1971 the joint airline owned 12 aircraft and its profit rose from $4 million to $9 million."]
    pl = P.plan(_scenes(lines))
    st = next(s for s in pl.shots if s.get("layer") == "stage.lay_stage")
    kinds = [e["kind"] for e in st["params"]["elements"]]
    assert any(k in ("sticker_change", "sticker_fleet", "cash_pile", "sticker_big_number") for k in kinds), kinds
    assert not any(s.get("layer", "").startswith("gfx_air.") for s in pl.shots)       # no blue news card inside a story


def test_split_line_naming_a_child_draws_the_whole_split():
    pl = P.plan(_scenes(LINES))
    st = next(s for s in pl.shots if s.get("layer") == "stage.lay_stage")
    tree = next(e for e in st["params"]["elements"] if e["kind"] == "split_tree")
    kids = [c["airline"] for c in tree["args"]["children"]]
    assert tree["args"]["parent"]["airline"] == "msa" and set(kids) == {"singapore_airlines", "malaysia_airlines"}


def test_independence_and_kept_routes_stay_story():
    from aviation import router as R
    assert R.classify("In 1965 Singapore became independent from Malaysia.").mode == "story"


def test_sticker_type_comes_from_the_script_before_the_era_guess():
    lines = ["In 2015 Vistara began flying Airbus A320s from Delhi.",
             "Vistara grew fast in 2019 and won awards for its service.",
             "In 2019 Vistara was praised by passengers again."]
    sc = _scenes(lines)
    cls = R.route_script(lines)
    from aviation import bible as BB
    shot, log = ST.build(sc, cls, None, 0, 2, bible=BB.read(lines))
    types = {e["args"]["type"] for e in shot["params"]["elements"] if e["kind"] == "aircraft"}
    assert types == {"a320"}                                 # never the A350 era guess for an airline the script says flies A320s
    shot2, _ = ST.build(sc[1:], cls[1:], None, 0, 1, bible=BB.read(lines[1:]))
    t2 = {e["args"]["type"] for e in shot2["params"]["elements"] if e["kind"] == "aircraft"}
    assert t2 <= {"a350"}                                    # nothing named anywhere: the era guess is the last fallback


def test_planner_passes_the_bible():
    lines = ["In 1966 the two governments formed Malaysia-Singapore Airlines, flying Boeing 707s.",
             "Malaysia-Singapore Airlines was owned by both governments in 1968."]
    pl = P.plan(_scenes(lines))
    st = next(s for s in pl.shots if s.get("layer") == "stage.lay_stage")
    assert {e["args"]["type"] for e in st["params"]["elements"] if e["kind"] == "aircraft"} == {"b707"}


def test_csv_story_columns_are_read(tmp_path):
    from aviation import csv_rows as V
    p = tmp_path / "s.csv"
    p.write_text("scene_number,script_segment,asset_type,prompt,graphic,mode,airline,search,owners,split,person,role,quote\n"
                 '1,"In 1966 the two governments formed Malaysia-Singapore Airlines.",none,,ownership,story,MSA,'
                 '"Malaysia-Singapore Airlines Boeing 707 1960s || Paya Lebar Airport 1960s","Malaysia 42.79% / Singapore 42.79%",'
                 '"Singapore: international routes | Malaysia: domestic network",,,\n', encoding="utf-8")
    r = V.read_rows(p)[0]
    assert r["mode"] == "story" and r["web_queries"] == ["Malaysia-Singapore Airlines Boeing 707 1960s", "Paya Lebar Airport 1960s"]
    assert r["owners"].startswith("Malaysia 42.79%") and r["split"].startswith("Singapore:")
    assert ST._web_q(r) == r["web_queries"]
    assert ST._web_q({"asset_type": "flow_video", "queries": ["a Flow prompt"]}) == []        # a Flow prompt is never a web search
    assert "story" in V.prompt_text() and "search," in V.prompt_text()


def test_story_line_with_its_own_clip_plays_it_full_screen():
    sc = _scenes(LINES)
    sc[2]["has_clip"] = True
    sc[2]["footage"] = "/x/archive.mp4"
    sc[2]["asset_type"] = "youtube_video"
    pl = P.plan(sc)
    foot = [s for s in pl.shots if s.get("kind") == "footage"]
    assert foot and all(f["scene"] == 3 for f in foot)                       # the opening may cut it into faster pieces
    assert 4.0 <= max(f["end"] for f in foot) - min(f["start"] for f in foot) <= 6.0 + 1e-6
    stages = [s for s in pl.shots if s.get("layer") == "stage.lay_stage"]
    assert len(stages) == 2 and stages[1]["params"]["t_offset"] == stages[1]["start"] - stages[0]["start"]
    assert stages[0]["cues"] and stages[1]["cues"] == []
