"""English on-screen text over an Urdu voice: planning reads the English line, timing stays on the voice."""
import english_overlay as eo
import video_generator as v


ROWS = [{"scene_number": "1", "script_segment": "اس ملک کا نام ہے ویتنام۔", "on_screen_en": "That country is Vietnam."},
        {"scene_number": "2", "script_segment": "سال 1986۔", "on_screen_en": ""},
        {"scene_number": "3", "script_segment": "تقریباً 87% ہو گیا۔", "on_screen_en": "By 2023 it rose to 87% of GDP."}]
ALIGNED = [{"scene_number": "1", "script_segment": ROWS[0]["script_segment"], "start_time": 0.0, "end_time": 2.0, "confidence": 1.0},
           {"scene_number": "2", "script_segment": ROWS[1]["script_segment"], "start_time": 2.0, "end_time": 3.0, "confidence": 1.0},
           {"scene_number": "3", "script_segment": ROWS[2]["script_segment"], "start_time": 3.0, "end_time": 6.0, "confidence": 1.0}]
WORDS = [("اس", 0.0, 0.2), ("ویتنام", 1.0, 1.5), ("سال", 2.0, 2.3), ("1986", 2.4, 2.9), ("87", 4.0, 4.5)]


def test_no_english_column_changes_nothing():
    rows = [{k: v_ for k, v_ in r.items() if k != "on_screen_en"} for r in ROWS]
    assert eo.apply(rows, ALIGNED, WORDS, v.split_words) is None


def test_english_lines_drive_text_and_words_but_not_timing():
    rows, aligned, words = eo.apply(ROWS, ALIGNED, WORDS, v.split_words)
    assert rows[0]["script_segment"] == "That country is Vietnam." and rows[1]["script_segment"] == "سال 1986۔"
    assert [(a["start_time"], a["end_time"]) for a in aligned] == [(a["start_time"], a["end_time"]) for a in ALIGNED]
    assert [a["script_segment"] for a in aligned][2] == "By 2023 it rose to 87% of GDP."
    scene1 = [w for w in words if 0.0 <= w[1] < 2.0]
    assert [w[0] for w in scene1] == v.split_words("That country is Vietnam.")
    assert ("1986", 2.4, 2.9) in words                      # a scene without English keeps its own words
    assert all(3.0 <= w[1] < 6.0 for w in words if w[0] in ("2023", "gdp"))
    assert [w[1] for w in words] == sorted(w[1] for w in words)


def test_smart_plan_cache_is_not_reused_for_other_text():
    import tempfile
    from pathlib import Path
    import smart_editing as se

    with tempfile.TemporaryDirectory() as d:
        audio = Path(d) / "voice.wav"
        audio.write_bytes(b"RIFF0000WAVE")
        cfg = se.SmartEditingSettings() if hasattr(se, "SmartEditingSettings") else None
        if cfg is None:
            return
        rows_ur = [{"scene_number": "1", "script_segment": "ویتنام"}]
        rows_en = [{"scene_number": "1", "script_segment": "VIETNAM EXPORTS"}]
        al = [{"scene_number": "1", "script_segment": "x", "start_time": 0.0, "end_time": 3.0}]
        se.build_plan(rows_ur, al, [("ویتنام", 0.5, 1.0)], cfg, state_dir=Path(d), audio_path=audio)
        key_ur = se.load_cache(Path(d)).get("settings_key")
        se.build_plan(rows_en, al, [("vietnam", 0.5, 1.0), ("exports", 1.0, 1.5)], cfg, state_dir=Path(d), audio_path=audio)
        assert se.load_cache(Path(d)).get("settings_key") != key_ur


def test_csv_graphics_land_on_their_own_scene():
    from normal_gfx import planner
    rows = [{"scene_number": "1", "gfx": '{"t": "text_slam", "text": "VIETNAM"}'}, {"scene_number": "2", "gfx": ""},
            {"scene_number": "3", "gfx": '{"t": "not_a_template", "text": "X"}'}]
    notes = []
    evs = planner.csv_events(rows, [(0.0, 4.0), (4.0, 8.0), (8.0, 12.0)], [], notes=notes)
    assert len(evs) == 1 and evs[0]["template"]["id"] == "text_slam" and 0.0 < evs[0]["t_in"] < 4.0
    assert any("scene 3" in n for n in notes)
