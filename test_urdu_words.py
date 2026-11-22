"""Urdu (Arabic-script) narration must align: the words survive tokenizing, Arabic/Urdu letter forms agree, and
Whisper's own spellings of the same word still match the script."""
import video_generator as v


def test_urdu_words_survive_tokenizing():
    assert v.split_words("سوچیے ایک ایسا ملک، جس کے پاس!") == ["سوچیے", "ایک", "ایسا", "ملک", "جس", "کے", "پاس"]


def test_urdu_digits_and_mixed_tokens():
    assert v.split_words("سال ۱۹۸۶ میں WTO اور 16%") == ["سال", "1986", "میں", "wto", "اور", "16"]


def test_arabic_letter_forms_become_urdu():
    assert v.normalize_word("كيا") == v.normalize_word("کیا")      # Arabic kaf/yeh vs Urdu
    assert v.normalize_word("مُلک") == v.normalize_word("ملک")     # diacritic dropped


def test_whisper_spellings_match_script():
    for heard, script in [("اندسٹریل", "انڈسٹریل"), ("دیکھئے", "دیکھیے"), ("ٹیکنوالجی", "ٹیکنالوجی"), ("کپڑے", "کپڑی")]:
        assert v._align_words_match(v.normalize_word(heard), v.normalize_word(script)), (heard, script)
    assert not v._align_words_match(v.normalize_word("پاکستان"), v.normalize_word("ویتنام"))


def test_urdu_function_words_are_not_anchors():
    assert not v.is_distinctive(v.normalize_word("لیکن"))
    assert not v.is_distinctive(v.normalize_word("نہیں"))
    assert v.is_distinctive(v.normalize_word("پاکستان"))


def test_urdu_rows_anchor_to_urdu_transcript():
    rows = [{"scene_number": "1", "script_segment": "اس ملک کا نام ہے ویتنام۔"},
            {"scene_number": "2", "script_segment": "اب ذرا پاکستان کو دیکھیے۔ پاکستان کے پاس کاٹن ہے"},
            {"scene_number": "3", "script_segment": "ٹیکسٹائل انڈسٹری ہے، ایک بڑی ڈومیسٹک مارکیٹ ہے"}]
    heard = "اس ملکا نام ہے ویتنام اب زرا پاکستان کو دیکھئے پاکستان کے پاس کاٹن ہے ٹیکسٹائل اندسٹری ہے ایک بڑی دمیسٹک مارکٹ ہے"
    words = [(w, i * 0.5, i * 0.5 + 0.4) for i, w in enumerate(t for p in heard.split() for t in v.split_words(p))]
    out = v.align_rows(rows, words)
    timed = out[0] if isinstance(out, tuple) else out
    assert all(r["confidence"] > 0 for r in timed), [(r["scene_number"], r["confidence"]) for r in timed]
    starts = [r["start_time"] for r in timed]
    assert starts == sorted(starts) and starts[1] >= 2.0 and starts[2] >= 5.0


def test_urdu_text_is_found_inside_overlay_specs():
    from dataclasses import dataclass, field

    @dataclass
    class Spec:
        text: object = None
        payload: dict = field(default_factory=dict)

    assert v._has_arabic_text({"text": "ویتنام", "style": "pop"})
    assert v._has_arabic_text(Spec(payload={"lines": ["16%", "پاکستان"]}))
    assert not v._has_arabic_text(Spec(text="Vietnam", payload={"value": 87}))
    assert not v._has_arabic_text(None)
