"""Named seas and regions are map places; geography beats win the map budget; a direction in the narration becomes a flow line across the named area."""
import pytest

from explainer.beats import geography as GEO
from explainer.beats.mapbeat import make_map_beat
from explainer.beats.relevance import beat_tokens, find_phrase
from hybrid import geo
from pakmap import geo as pgeo, waters

TEXT = "Look east across the Adriatic and you will find the Balkan coastline".split()
WORDS = [(w, 1.0 + 0.4 * i, 1.35 + 0.4 * i) for i, w in enumerate(TEXT)]


class Hit:
    def __init__(self, name, kind, match):
        self.name, self.kind, self.match = name, kind, match


def test_named_waters_resolve():
    for name, kind in (("Adriatic", "sea"), ("Adriatic Sea", "sea"), ("Mediterranean", "sea"), ("Venetian Lagoon", "sea"), ("Black Sea", "sea")):
        r = geo.resolve(name)
        assert r.kind == kind and r.bbox[0] < r.lon < r.bbox[2] and r.bbox[1] < r.lat < r.bbox[3]


def test_unlisted_water_words_are_not_guessed():
    for name in ("Lagoon", "Sea", "Atlantis Sea"):
        with pytest.raises(geo.GeoError):
            geo.resolve(name)


def test_balkan_is_the_balkans_not_a_turkmen_province():
    r = geo.resolve("Balkan")
    assert r.name == "Balkans" and r.bbox[2] < 35


def test_atlas_places_still_win_over_waters():
    assert geo.resolve("Italy").kind == "country"
    assert waters.find("Italy") is None


def test_sea_view_holds_the_whole_box():
    from explainer.beats import framing as FR
    for name in ("Adriatic", "Mediterranean", "Venetian Lagoon"):
        v = pgeo.view_for(geo.resolve(name), "region")
        assert FR.inside(FR.view_box(*v), FR.place_bbox(name), margin=0.0), name


def _hits():
    tk = beat_tokens(WORDS, 0, 100)
    return tk, [Hit("Adriatic", "sea", find_phrase(tk, "Adriatic")), Hit("Balkan", "region", find_phrase(tk, "Balkan"))]


def test_direction_and_sea_beat_outscores_a_passing_mention():
    tk, hits = _hits()
    s, why = GEO.map_priority(tk, hits)
    plain = beat_tokens([(w, 1.0 + 0.4 * i, 1.3 + 0.4 * i) for i, w in enumerate("We visited Venice last year and liked it".split())], 0, 100)
    s0, _ = GEO.map_priority(plain, [Hit("Venice", "admin1", find_phrase(plain, "Venice"))])
    assert s >= 6 and s0 == 0 and any("direction" in w for w in why)


def test_budget_goes_to_highest_score_and_equal_scores_keep_story_order():
    c = [{"idx": i, "id": f"e{i}", "dur": 6.0, "score": 0} for i in range(5)]
    assert GEO.pick_map_beats(c, 5, 12.0) == ["e0", "e1"]                    # the old first-come rule
    c[4]["score"] = 6
    assert GEO.pick_map_beats(c, 5, 12.0) == ["e0", "e4"]                    # the opening beat is kept, the geography beat takes the rest
    c[0]["idx"], c[0]["id"] = 1, "e1"
    assert GEO.pick_map_beats(c[:1] + c[2:], 5, 12.0)[-1] == "e4"
    assert GEO.pick_map_beats([{"idx": i, "id": f"e{i}", "dur": 1.0, "score": 0} for i in range(5)], 5, 99.0) == ["e0", "e1", "e3", "e4"]   # never three in a row


def test_direction_cue_is_a_flow_line_east_across_the_sea():
    tk, hits = _hits()
    cue = GEO.direction_cue(tk, "Adriatic", hits[0].match, geo.resolve)
    (la, lo), (lb, lob) = [tuple(map(float, p.split(","))) for p in cue["places"]]
    assert lob > lo and abs(lb - la) < 1e-6 and cue["direction"] == "east"
    assert cue["t"] == pytest.approx(1.4, abs=0.01)                          # when "east" is spoken
    assert GEO.direction_cue(tk, "Balkan", hits[1].match, geo.resolve) is None   # no direction word right before it


def test_map_beat_carries_the_cue_and_labels_the_sea():
    beat, ev, problems = make_map_beat("e1", 0.0, 12.0, WORDS, zone_labels=[{"place": "Adriatic"}], markers=[], strict=False)
    kinds = {l["id"]: l for l in beat["layers"]}
    assert "e1_dir1" in kinds and kinds["e1_dir1"]["kind"] == "flow" and kinds["e1_dir1"]["type"] == "line"
    assert kinds["e1_zone1"]["label"] == "ADRIATIC"
    assert not problems


def test_cue_passes_the_relevance_check():
    from explainer.beats.relevance import check_plan
    from explainer.beats.mapbeat import make_map_beat as mk
    beat, _ev, _p = mk("e1", 0.0, 12.0, WORDS, camera_start={"place": "Adriatic", "frame": "region"}, zone_labels=[{"place": "Adriatic"}], strict=False)
    rep = check_plan({"version": 1, "duration": 12.0, "beats": [beat]}, WORDS, resolve_offline=True)
    assert not [p for p in rep.problems if "e1_dir1" in p], rep.problems
