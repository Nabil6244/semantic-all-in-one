"""Rules fixed after the first 3-minute Aviation film (2026-11-13): each failure seen in the render, as a general rule."""

from aviation import director as D
from aviation import planner as P
from aviation import router as R
from aviation import story as ST
from aviation import transitions as TR

NEWS = "In October 2018, Singapore Airlines brought back the longest passenger flight in the world, from Singapore to New York."


def _scenes(lines, step=6.0):
    return [{"scene_no": i + 1, "text": t, "start": i * step, "end": (i + 1) * step} for i, t in enumerate(lines)]


def test_passenger_trip_video_is_not_news_footage():
    c = R.classify(NEWS)
    c.mode = "news"
    bad = "(4K) SQ 22 | FLYING NONSTOP | THE WORLD'S SECOND LONGEST FLIGHT | SIN - EWR | AIRBUS A350-900ULR"
    assert "passenger" in D.title_reject(bad, c, airlines=["singapore_airlines"])
    assert D.title_reject("Singapore Airlines relaunches world longest flight to Newark", c, airlines=["singapore_airlines"]) == ""


def test_saved_burst_clips_are_rechecked_at_render():
    scenes = [{"scene_no": 1, "text": NEWS, "mode": "news", "airline": "singapore_airlines"}]
    ex = {"1": [{"title": "(4K) SQ 22 | FLYING NONSTOP | SIN - EWR | A350-900ULR", "channel": "M Paul"},
                {"title": "Singapore Airlines A350-900ULR Newark takeoff", "channel": "spotter"}]}
    kept = D.recheck_extras(ex, scenes)
    assert [x["title"] for x in kept["1"]] == ["Singapore Airlines A350-900ULR Newark takeoff"]


def test_transition_takes_the_card_before_it_fades():
    lines = [NEWS, "In 1966 the two governments formed Malaysia-Singapore Airlines together."]
    pl = P.plan(_scenes(lines))
    for s in pl.shots:
        if s.get("layer") == "transitions.lay_out":
            p = s["params"]
            assert p["from_t"] <= p["from_dur"] - TR.EXIT_GUARD_S + 1e-6


def test_became_is_not_a_rename():
    lines = ["In 1972 Singapore Airlines was formed after the split.",
             "That is why its home airport, Changi, became one of the busiest hubs in Asia."]
    shot, log = ST.build(_scenes(lines), R.route_script(lines), [{}, {"airline": "singapore_airlines"}], 0, 1)
    assert log[1]["stage"] != "timeline"


def test_received_a_stake_in_makes_an_ownership_card():
    lines = ["Singapore Airlines received a 25.1 percent stake in the merged Air India."]
    shot, log = ST.build(_scenes(lines), R.route_script(lines), [{"airline": "air_india"}], 0, 0)
    own = next(e for e in shot["params"]["elements"] if e["kind"] == "ownership")
    assert own["args"]["airline"] == "air_india"
    assert own["args"]["owners"] == [{"name": "Singapore Airlines", "airline": "singapore_airlines", "pct": 25.1}]


def test_business_class_trip_and_explainer_videos_rejected():
    c = R.classify(NEWS)
    c.mode = "news"
    for t in ("Ultra Long Haul with Singapore Airlines | Singapore to Newark in Business Class | Airbus A350-900ULR",
              "Air India- Vistara Merger Explained | Merger by 2024 | What is a Merger? | Kinds of Merger"):
        assert D.title_reject(t, c) != "", t
    assert D.title_reject("Air India-Vistara To Merge On 12th November: No Vistara Bookings From 3rd September", R.classify(
        "In 2024 Vistara merged into Air India.")) == ""


def test_main_clip_rechecked_at_render(tmp_path):
    import json
    clip = tmp_path / "028.mp4"
    clip.write_bytes(b"x")
    (tmp_path / D.REPORT).write_text(json.dumps({"scenes": {
        "28": {"decision": "footage", "title": "Air India- Vistara Merger Explained | What is a Merger? | Kinds of Merger"},
        "29": {"decision": "footage", "title": "Air India-Vistara To Merge On 12th November: No Vistara Bookings"}}}))
    sc = [{"scene_no": 28, "text": "In 2024 Vistara merged into Air India.", "asset_type": "youtube_video", "footage": str(clip),
           "mode": "news"},
          {"scene_no": 29, "text": "Vistara flew its last flights in November 2024.", "asset_type": "youtube_video",
           "footage": str(clip), "mode": "news"}]
    assert D.recheck_main(sc, tmp_path) == 1
    assert sc[0]["footage"] is None and sc[1]["footage"] == str(clip)


def test_captions_never_cut_mid_phrase():
    assert ST.caption_of("So the airline had to fly further than almost anyone else.") == \
        "So the airline had to fly further than almost anyone else"
    long = "That is why its home airport, Changi, became one of the busiest hubs in Asia and the world by far."
    assert ST.caption_of(long) == ""                                  # first clause too short: no caption rather than a cut


def test_no_text_only_fact_card_survives_the_bridge(tmp_path):
    from aviation import bridge as BR
    lines = ["The airline ordered special long-range Airbus A350s just for this route.",
             "The new version could stay in the air for around twenty hours without stopping."]
    sc = [dict(s, mode="news") for s in _scenes(lines)]
    pl = P.plan(sc)
    shots, layers, rep = BR.build_timeline(pl, sc, lambda slot: None, black=str(tmp_path / "black.mp4"))
    assert not [ly for ly in layers if ly.kind == "cards.lay_article" and ly.params.get("fact")
                and not any(ly.params.get(k) for k in ("page", "image", "video"))]


def test_long_opening_question_still_gets_big_type():
    lines = ["In October 2018, Singapore Airlines brought back the longest passenger flight in the world.",
             "So how did an airline from a small island end up flying the longest routes on Earth?",
             "In 1947 Malayan Airways was founded in Singapore, flying small propeller airliners."]
    pl = P.plan([dict(s, mode="story") for s in _scenes(lines)], [{"mode": "story"}] * 3)
    st = next(s for s in pl.shots if s.get("layer") == "stage.lay_stage")
    assert any(e["kind"] == "big_type" and e["args"]["text"].endswith("?") for e in st["params"]["elements"])


def test_question_big_type_holds_to_the_end_of_its_line():
    lines = ["In October 2018, Singapore Airlines brought back the longest passenger flight in the world.",
             "So how did an airline from a small island end up flying the longest routes on Earth?",
             "In 1947 Malayan Airways was founded in Singapore, flying small propeller airliners."]
    sc = [dict(s, mode="story") for s in _scenes(lines, step=6.0)]
    pl = P.plan(sc, [{"mode": "story"}] * 3)
    st = next(s for s in pl.shots if s.get("layer") == "stage.lay_stage")
    big = next(e for e in st["params"]["elements"] if e["kind"] == "big_type" and e["args"]["text"].endswith("?"))
    assert big["t1"] + st["start"] >= 12.0 - 0.05                           # until the question line ends at 12 s


def test_fallback_beat_uses_the_scenes_airline():
    st = ST.fallback_stage("The airline ordered special long-range Airbus A350s just for this route.", 5.0,
                           scene={"airline": "singapore_airlines", "aircraft": "a350"})
    ac = next(e for e in st["elements"] if e["kind"] == "aircraft")
    assert ac["args"]["airline"] == "singapore_airlines" and ac["args"]["type"] == "a350"


def test_article_card_holds_to_the_cut():
    from aviation import cards as K
    p = {"fact": "Singapore Airlines brought back the longest flight.", "headline": "x"}
    end = K.lay_article(4.95, 5.0, p)
    mid = K.lay_article(3.0, 5.0, p)
    assert abs(sum(end.convert("L").resize((32, 18)).getdata()) - sum(mid.convert("L").resize((32, 18)).getdata())) < 3000
