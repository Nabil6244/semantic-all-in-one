"""Scene choice for cartoon beats: a setting word beats a lone people word, the lead beside a row of soldiers is not a Napoleonic officer unless the words say so, and the cartoon
caption is large and sits on the sky."""
from explainer.director import lexicon_v2 as LV
from explainer.director import scene_registry as SR
from explainer.director import compose_cartoon as CC


def toks(s):
    return s.lower().split()


def test_water_beats_armies():
    assert LV.choose_scene_v2(toks("shallow water made it difficult for invading armies")) == "harbour"
    assert SR.ranked_scenes(toks("shallow water made it difficult for invading armies"), True)[0][0] == "harbour"


def test_armies_alone_still_a_field():
    assert LV.choose_scene_v2(toks("the armies marched across the plain")) == "field"


def test_food_points_to_field_but_market_wins():
    assert LV.choose_scene_v2(toks("and no easy way to produce enough food for a growing population")) == "field"
    assert LV.choose_scene_v2(toks("food in the market for merchants")) == "old_town"


def test_lead_beside_soldiers_is_neutral():
    crowd = ("soldier", 3)
    assert LV.lead_for_crowd([("soldier", 3)], crowd) == "blue"
    assert LV.lead_for_crowd([("officer", 0), ("soldier", 3)], crowd) == "officer"
    cast, cr = SR._fresh_cast(toks("shallow water made it difficult for invading armies"), 8, True, "gold")
    assert cast[0][1] == "blue" and cr[0] == "soldier"


def test_caption_on_sky():
    pos = CC._caption_pos("shallow water made it difficult for invading armies")
    assert pos is not None and pos[1] < 300 and 0 < pos[0] < 960
    assert CC._cartoon_caption_fit("shallow water made it difficult")


def test_contrast_clause_outranks_rejected_word():
    s = "so instead of relying on agriculture the venetians turned toward the sea"
    assert LV.choose_scene_v2(toks(s)) == "harbour"
    assert SR.ranked_scenes(toks(s), True)[0][0] == "harbour"
    assert LV.choose_scene_v2(toks("rather than growing grain they sailed to the harbour")) == "harbour"
    assert LV.choose_scene_v2(toks("instead of relying on agriculture the venetians turned")) is None      # a rejected word alone names no place


def test_adjacent_beats_keep_their_scene():
    assert LV.choose_scene_v2(toks("and no easy way to produce enough food for a growing population")) == "field"
    assert LV.choose_scene_v2(toks("venice had very little farmland limited natural resources")) == "field"
    assert LV.choose_scene_v2(toks("mainland settlements sought safety among the islands and marshes of the venetian lagoon")) == "harbour"


def test_obstruction_is_a_relation_not_a_word():
    s = toks("the shallow water made it difficult for invading armies to reach them")
    assert LV.obstruction_for(s) is not None
    assert LV.obstruction_for(toks("the walls made it difficult for invading armies to reach them")) is None        # not water
    assert LV.obstruction_for(toks("the shallow water was warm and clear")) is None                                  # no obstruction, no movers
    assert LV.obstruction_for(toks("it was difficult to learn the lagoon dialect")) is None                           # no one who would move


def test_obstruction_beat_gets_the_shallows_set():
    from explainer.cartoon import kit_v2
    assert kit_v2.has_set("shallows", "day") and kit_v2.has_set("shallows", "dusk")
    text = "the shallow water made it difficult for invading armies to reach them".split()
    words = [(w, i * 0.4, i * 0.4 + 0.35) for i, w in enumerate(text)]
    from explainer.director.segment import sentences, compute_breaks, label_sentences
    from explainer.director.options import DirectorOptions
    sents = sentences(words, " ".join(text), 4.0, 12.0)
    compute_breaks(sents, words)
    label_sentences(sents, words, " ".join(text))
    opt = DirectorOptions(scenes2=True)
    res = CC.author_cartoon("e2", 0.0, 4.0, sents, words, {}, opt, {}, {})
    sets = [c.params.get("set") for c in res.cues if c.params.get("style") == "set"]
    crowd = [c for c in res.cues if c.params.get("style") == "crowd"]
    assert sets == ["shallows"] and crowd and crowd[0].params["kind"] == "soldier"
    cap = [c for c in res.cues if c.kind == "caption"][0].text
    assert cap in " ".join(text)                                    # still a contiguous quote of the narration


def test_caption_never_ends_on_a_dangling_word():
    from explainer.director.compose import Phrase
    words = [(w, i * 0.3, i * 0.3 + 0.25) for i, w in enumerate("mainland settlements sought safety among the".split())]
    n = len(words) - 1
    assert CC._dangles(Phrase("settlements sought safety among the", 1, n, []), n, set(), words)
    assert CC._dangles(Phrase("venetians turned", 4, n, []), n, set(), [(w, 0, 0) for w in "a b c d venetians turned".split()])
    assert not CC._dangles(Phrase("mainland settlements sought safety", 0, 3, []), n, set(), words)
    assert not CC._dangles(Phrase("venetians turned", 4, n, []), n, {n}, [(w, 0, 0) for w in "a b c d venetians turned".split()])        # a sentence end completes it


def test_group_subject_with_one_setting_word_is_scene_worthy():
    sc = lambda s: CC.scene_score(toks(s), scenes2=True)
    assert sc("so instead of relying on agriculture the venetians turned toward the sea") > 0
    assert sc("the villagers walked toward the harbour") > 0
    assert sc("light glowing by the sea") == 0                       # no group of people: still a board
    assert LV.group_subjects(toks("instead of the venetians the sea")) == 0     # a rejected group does not count


def test_fallback_opening_map_is_decided_before_cartoon_budget():
    import inspect
    from explainer.director import select
    src = inspect.getsource(select.choose_kinds)
    assert src.index("fallback_place") < src.index("_assign_cartoons(")
