import video_generator as v


def test_devanagari_words_survive():
    assert v.split_words("आज रात Amazon के किसी ऑर्डर का पेज १२") == ["आज", "रात", "amazon", "के", "किसी", "ऑर्डर", "का", "पेज", "12"]


def test_nukta_and_chandrabindu_fold():
    assert v.normalize_word("फ़ुटबॉल") == v.normalize_word("फुटबॉल")
    assert v.normalize_word("हाँ") == v.normalize_word("हां")


def test_latin_unchanged():
    assert v.normalize_word("caminó") == "camino"
    assert v.normalize_word("don't") == "dont"


def test_hindi_close_spelling_aligns():
    assert v._align_words_match("मैदानो", "मैदानों")
    assert not v._align_words_match("गोदाम", "विमान")


from unittest_adopt import adopt
adopt(globals())
