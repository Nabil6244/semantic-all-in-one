"""War Documentary: narration-matched footage (metadata estimate, never proof). Offline, synthetic metadata."""
import json

from cinematic_explainer.war import footage_match as FM
from cinematic_explainer.war import integration as I
from cinematic_explainer.war import planner as P


def _stock(query, **kw):
    m = {"source": "stock", "provider": "pexels", "kind": "stock", "generic": True, "stock_query": query, "rights_known": False}
    m.update(kw)
    return m


def _scene(no, text, path, meta, **kw):
    d = {"scene_no": str(no), "text": text, "start": no * 5.0, "end": no * 5.0 + 5.0, "footage": path, "footage_meta": meta}
    d.update(kw)
    return d


def test_same_system_scores_and_is_relevant_stock():
    r = FM.match_scenes([_scene(1, "A Pantsir air defence system guards the refinery.", "a.mp4", _stock("pantsir air defense truck"))])[0]
    assert r["footage_match"]["class"] == "relevant_stock"
    assert r["footage_match"]["score"] >= 0.45
    assert r["footage_meta"]["stock_relevant"] is True
    assert not r["footage_meta"].get("mismatch")


def test_different_named_system_is_a_contradiction_even_with_shared_words():
    r = FM.match_scenes([_scene(1, "A Pantsir air defence system guards the refinery.", "a.mp4", _stock("patriot air defense battery truck"))])[0]
    m = r["footage_match"]
    assert m["class"] == "illustrative" and m["contradictions"]
    assert r["footage_meta"]["mismatch"] is True
    assert P.footage_info(r["footage_meta"])["chip"] == "ILLUSTRATIVE FOOTAGE"


def test_different_person_and_country_and_year_contradict():
    s = FM.score_clip(FM.narration_profile("Putin said in 2022 that Russia would respond."), _stock("zelensky speech ukraine 2019"))
    assert len(s["contradictions"]) >= 2 and s["score"] < FM.RELEVANT_MIN


def test_generic_words_alone_are_weak_and_stay_illustrative():
    r = FM.match_scenes([_scene(1, "Drones struck a fuel depot at night.", "a.mp4", _stock("city street traffic"))])[0]
    assert r["footage_match"]["class"] == "illustrative"
    assert P.footage_info(r["footage_meta"])["chip"] == "ILLUSTRATIVE FOOTAGE"


def test_missing_or_odd_metadata_never_raises_and_is_illustrative():
    for meta in ({}, None, {"tags": 5}, {"stock_query": None, "description": {"a": [1, 2]}}):
        r = FM.match_scenes([_scene(1, "Putin spoke in Moscow.", "a.mp4", meta)])[0]
        assert r["footage"] == "a.mp4"
        assert r["footage_match"]["class"] in FM.CLASSES


def test_no_clip_gives_no_choice_not_an_error():
    r = FM.match_scenes([{"scene_no": "1", "text": "Kyiv at dawn.", "start": 0, "end": 4, "footage": None, "footage_meta": {}}])[0]
    assert r["footage_match"]["chosen"] is None and not r.get("footage")


def test_candidate_beats_weak_own_clip():
    own = _stock("city street traffic")
    good = {"path": "good.mp4", "meta": _stock("pantsir missile system russia")}
    r = FM.match_scenes([_scene(1, "The Pantsir missile system in Russia.", "own.mp4", own, footage_candidates=[good])])[0]
    assert r["footage"] == "good.mp4" and r["footage_match"]["source"] == "candidate"


def test_user_file_is_pinned_flagged_but_never_swapped():
    own = {"kind": "user", "user_supplied": True, "generic": False, "stock_query": "patriot battery"}
    good = {"path": "good.mp4", "meta": _stock("pantsir missile system")}
    r = FM.match_scenes([_scene(1, "The Pantsir missile system.", "mine.mp4", own, footage_candidates=[good])])[0]
    assert r["footage"] == "mine.mp4"
    assert r["footage_match"]["class"] == "user_supplied" and r["footage_meta"]["mismatch"] is True


def test_verified_event_needs_confirmation_and_agreement():
    meta = {"kind": "youtube", "generic": False, "verification": "confirmed", "video_title": "Pantsir strike on refinery Moscow 2024", "provider": "youtube"}
    r = FM.match_scenes([_scene(1, "A Pantsir covers the Moscow refinery in 2024.", "a.mp4", meta)])[0]
    assert r["footage_match"]["class"] == "verified_event"
    assert not r["footage_meta"].get("mismatch")


def test_reuse_pulls_same_subject_clip_from_pool_and_is_marked_reused_not_recycled():
    pool = [{"path": "pantsir.mp4", "meta": _stock("pantsir air defense russia")}]
    sc = [_scene(1, "A Pantsir air defence system in Russia.", "pantsir.mp4", _stock("pantsir air defense russia")),
          _scene(2, "Kyiv woke to alarms.", "kyiv.mp4", _stock("kyiv skyline ukraine")),
          _scene(3, "Again the Pantsir was on the roof.", "city.mp4", _stock("city street traffic"))]
    r = FM.match_scenes(sc, pool)
    assert r[2]["footage"] == "pantsir.mp4"
    m = r[2]["footage_meta"]
    assert m["reused"] is True and not m.get("recycled") and r[2]["footage_match"]["reused_from_scene"] == "1"
    assert "reused" in P.footage_info(m) and P.footage_info(m)["reused"]


def test_reuse_is_not_forced_when_narration_needs_something_else():
    pool = [{"path": "pantsir.mp4", "meta": _stock("pantsir air defense russia")}]
    sc = [_scene(1, "Kharkiv was shelled overnight.", "kh.mp4", _stock("kharkiv ukraine shelling"))]
    assert FM.match_scenes(sc, pool)[0]["footage"] == "kh.mp4"


def test_generic_words_never_pull_a_pool_clip():
    pool = [{"path": "x.mp4", "meta": _stock("drone night city")}]
    r = FM.match_scenes([_scene(1, "A drone flew over the city at night.", "own.mp4", _stock("harbour boats"))], pool)[0]
    assert r["footage"] == "own.mp4"      # no named subject, so no reuse


def test_relevant_stock_chip_is_stock_not_illustrative_and_has_no_mismatch():
    r = FM.match_scenes([_scene(1, "A Pantsir air defence system.", "a.mp4", _stock("pantsir air defense"))])[0]
    fi = P.footage_info(r["footage_meta"])
    assert fi["chip"] == "STOCK FOOTAGE" and not fi["mismatch"] and fi["generic"]


def test_load_scenes_uses_manifest_pool_and_report_carries_relevance(tmp_path):
    (tmp_path / "Images").mkdir()
    for n in ("one.mp4", "two.mp4"):
        (tmp_path / "Images" / n).write_bytes(b"x")
    man = {"001": {"status": "complete", "local_path": "one.mp4", "provider": "pexels", "type": "video", "stock_query": "pantsir air defense russia"},
           "002": {"status": "complete", "local_path": "two.mp4", "provider": "pexels", "type": "video", "stock_query": "city street traffic"}}
    (tmp_path / "Images" / ".asset_manifest.json").write_text(json.dumps(man))
    scenes = [{"scene_no": 1, "text": "A Pantsir air defence system in Russia.", "start": 0, "end": 5},
              {"scene_no": 2, "text": "Traffic jammed the streets.", "start": 5, "end": 10},
              {"scene_no": 3, "text": "Again the Pantsir was on the roof.", "start": 10, "end": 15}]
    out = I.load_scenes(tmp_path, scenes)
    assert out[0]["footage_match"]["class"] == "relevant_stock"
    assert out[2]["footage"].endswith("one.mp4") and out[2]["footage_meta"]["reused"]


def test_load_scenes_without_matching_is_unchanged(tmp_path):
    (tmp_path / "v.mp4").write_bytes(b"x")
    out = I.load_scenes(tmp_path, [{"scene_no": 1, "text": "Hello.", "start": 0, "end": 3, "footage": "v.mp4"}], match=False)
    assert "footage_match" not in out[0]


def test_build_report_has_relevance_and_class():
    sc = FM.match_scenes([_scene(1, "A Pantsir air defence system.", "a.mp4", _stock("pantsir"))])
    class _Plan:
        shots, layers, log = [], [], []
    rep = I.build_report(sc, _Plan())
    fr = rep["scenes"][0]["footage_relevance"]
    assert fr["class"] == "relevant_stock" and "estimated" in fr["note"]


def test_candidate_with_nothing_in_common_is_not_adopted():
    s = _scene(1, "Strikes hit refineries near Moscow and in Ryazan.", None, None)
    s["footage_candidates"] = [{"footage": "pluto.mp4", "footage_meta": {"video_title": "Pluto New Horizons flyby", "generic": True}}]
    out = FM.match_scenes([s])[0]
    assert not out.get("footage") and out["footage_match"]["class"] == "illustrative"


def test_pinned_clip_unrelated_to_named_subjects_is_flagged_not_swapped():
    s = _scene(1, "Russia protects key sites with the Pantsir-S1 air defense system.", "moon.mp4", {"user_supplied": True, "video_title": "the moon at night"})
    out = FM.match_scenes([s])[0]
    assert out["footage"] == "moon.mp4" and out["footage_meta"]["weak_match"] and out["footage_meta"]["mismatch"]

