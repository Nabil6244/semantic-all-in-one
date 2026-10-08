"""pakMap Phase 7: the sound design.

Vocabulary, event->sound mapping, restraint (anti-stacking), explicit overrides, ambience, missing assets, the
narration-ducking mixer, the audio policy and mode isolation, and a full generate run with a fake renderer.
Uses a throw-away sound library of generated tones (never the user's library) and never touches the network."""

from __future__ import annotations

import json
import re
import tempfile
import unittest
import wave
from pathlib import Path

import numpy as np

from pakmap import audio_mix as am
from pakmap import audio_plan as ap
from pakmap import sounds as sd
from pakmap.audio_policy import PAKMAP_POLICY, generic_flags_for, policy_for
from pakmap.schema import CsvError, parse_csv

ROOT = Path(__file__).resolve().parent
SR = am.SR


# ---- helpers ---------------------------------------------------------------------------------------------

def _write_wav(path: Path, samples: np.ndarray, sr: int = SR) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes())


def _tone(freq: float, dur: float, amp: float = 0.8) -> np.ndarray:
    t = np.arange(int(dur * SR)) / SR
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def make_catalog(root: Path, skip=()):
    """A catalog with a tone for every candidate id in the vocabulary (ambience ids get 3 s of noise)."""
    import smart_editing as se

    rng = np.random.default_rng(0)
    entries, seen = [], set()
    amb_ids = {c for s in sd.SOUNDS.values() if s.kind == "ambience" for c, _ in s.candidates}
    for s in sd.SOUNDS.values():
        for n, (cid, _f) in enumerate(s.candidates):
            if cid in seen or cid in skip:
                continue
            seen.add(cid)
            rel = f"{cid}.wav"
            if cid in amb_ids:
                _write_wav(root / rel, (0.8 * rng.uniform(-1, 1, 3 * SR)).astype(np.float32)); dur, cat = 3.0, "ambience"
            else:
                _write_wav(root / rel, _tone(300 + 37 * len(seen), 1.0)); dur, cat = 1.0, "ui"
            entries.append(se.SfxEntry(id=cid, file=rel, category=cat, tags=(), intensity="low", duration=dur))
    return se.SfxCatalog(root, entries)


def spec(events=(), moves=(), duration=40.0, start=None):
    return {"duration": duration, "events": [dict(e) for e in events],
            "camera": {"start": start or {"lon": 37.0, "lat": 0.0, "zoom": 6.0}, "moves": [dict(m) for m in moves]}}


def ev(i, typ, t, **kw):
    return {"id": i, "type": typ, "t_in": t, "t_out": t + 3.0, **kw}


def cue_names(plan):
    return [(round(c.t, 2), c.sound) for c in plan.cues]


# ---- 1. vocabulary ---------------------------------------------------------------------------------------

class TestVocabulary(unittest.TestCase):
    NEEDED_SFX = ("map_slide_whoosh", "ui_click", "data_tick", "marker_pop", "directional_whoosh", "earth_spin", "equator_ding",
                  "record_scratch", "paper_slide", "marker_clack", "shimmer_riser", "bone_tap", "steam_chug", "construction_impact",
                  "camera_shutter", "fast_whoosh", "final_chime", "soft_transition")
    NEEDED_AMBIENCE = ("geographic_atmosphere", "desert_wind", "rushing_wind", "water_ambience", "historical_texture", "railway_texture", "electrical_hum")

    def test_every_listed_sound_is_in_the_vocabulary(self):
        for i in self.NEEDED_SFX:
            self.assertIn(i, sd.SFX_IDS)
        for i in self.NEEDED_AMBIENCE:
            self.assertIn(i, sd.AMBIENCE_IDS)

    def test_levels_stay_well_below_speech_and_no_music(self):
        for s in sd.SOUNDS.values():
            self.assertLessEqual(s.volume, 0.18, s.id)
            if s.kind == "ambience":
                self.assertLessEqual(s.volume, 0.09, s.id)
            self.assertNotIn("music", s.id)
            if s.kind == "sfx":
                self.assertIsNotNone(s.max_s, f"{s.id}: a one-shot must have a length cap")

    def test_every_event_mapping_names_a_real_sound_and_composites_have_real_parts(self):
        for sound in sd.EVENT_SOUND.values():
            self.assertIn(sound, sd.SOUNDS)
        for s in sd.SOUNDS.values():
            for part in s.parts:
                self.assertIn(part, sd.SOUNDS)

    def test_a_sound_without_a_library_candidate_is_declared_not_faked(self):
        self.assertEqual(sd.SOUNDS["record_scratch"].candidates, ())


# ---- 2. event -> sound -----------------------------------------------------------------------------------

class TestEventMapping(unittest.TestCase):
    def one(self, e, **kw):
        return ap.plan_audio(spec([e], **kw))

    def test_each_visual_event_gets_its_mapped_sound_at_its_time(self):
        cases = [(ev("h", "hud_title", 4.0), "deep_thud", 4.0), (ev("m", "marker", 5.0, dot=True), "marker_pop", 5.0), (ev("s", "stat", 6.0), "counter_ticks", 6.0),
                 (ev("l", "line", 7.0, kind="flow"), "draw_zap", 7.0), (ev("b", "line", 7.5, kind="border_trace"), "draw_zap", 7.5),
                 (ev("p", "pip", 8.0), "ui_click", 8.0), (ev("f", "filmstrip", 9.0), "ui_click", 9.0),
                 (ev("k", "sticker", 10.0), "subtle_pop", 10.0), (ev("v", "media_full", 11.0), "soft_transition", 11.0),
                 (ev("r", "fill", 12.0), "bubble_pluck", 12.0), (ev("d", "dots", 13.0), "bubble_pluck", 13.0), (ev("g", "ghost_shape", 14.0), "paper_slide", 14.0)]
        for e, sound, t in cases:
            self.assertEqual(cue_names(self.one(e)), [(t, sound)], e["type"])

    def test_the_reference_line_zaps_then_dings_when_it_finishes_drawing(self):
        self.assertEqual(cue_names(self.one(ev("r", "line", 4.0, kind="reference"))), [(4.0, "draw_zap"), (round(4.0 + ap.LINE_DRAW_S, 2), "equator_ding")])

    def test_text_only_layers_and_value_overlays_are_silent(self):
        for e in (ev("c", "caption", 3.0), ev("z", "marker", 3.0, dot=False), ev("o", "value_overlay", 3.0)):
            plan = self.one(e)
            self.assertEqual(plan.cues, [], e["type"])
            self.assertTrue(plan.silent)

    def test_a_counter_is_a_rapid_run_of_ticks(self):
        hits = ap.expand(self.one(ev("s", "stat", 6.0)).cues[0])
        self.assertEqual(len(hits), 10)
        self.assertAlmostEqual(hits[-1].t - hits[0].t, 0.495, places=3)

    def test_a_pan_across_the_map_gets_the_soft_whoosh_but_a_nudge_does_not(self):
        pan = {"type": "fly_to", "t": 5.0, "dur": 2.0, "to": {"lon": 38.5, "lat": 0.0, "zoom": 6.0}}  # about 170 km
        p = ap.plan_audio(spec(moves=[pan]))
        self.assertEqual(cue_names(p), [(5.0, "map_slide_whoosh")])
        self.assertEqual(p.cues[0].priority, sd.PRIORITY_NORMAL)
        self.assertEqual(ap.plan_audio(spec(moves=[dict(pan, to={"lon": 37.1, "lat": 0.1, "zoom": 6.0})])).cues, [])

    def test_major_camera_moves_sound_but_slow_motion_never_does(self):
        far = {"type": "fly_to", "t": 5.0, "dur": 2.0, "to": {"lon": 100.0, "lat": 20.0, "zoom": 6.0}}
        self.assertEqual(cue_names(ap.plan_audio(spec(moves=[far]))), [(5.0, "map_slide_whoosh")])
        self.assertEqual(ap.plan_audio(spec(moves=[far])).cues[0].priority, sd.PRIORITY_MAJOR)
        globe = {"type": "pull_back", "t": 5.0, "dur": 2.0, "to": {"zoom": 1.8}}
        self.assertEqual(cue_names(ap.plan_audio(spec(moves=[globe]))), [(5.0, "earth_spin")])
        for quiet in ({"type": "push_in", "t": 5.0, "dur": 8.0, "to": {"zoom": 6.4}},
                      {"type": "fly_to", "t": 5.0, "dur": 2.0, "to": {"lon": 37.1, "lat": 0.1, "zoom": 6.2}}):
            p = ap.plan_audio(spec(moves=[quiet]))
            self.assertEqual(p.cues, [])
            self.assertTrue(p.silent)

    def test_zoom_in_and_zoom_out_make_a_soft_whoosh_but_small_zooms_do_not(self):
        push = {"type": "push_in", "t": 5.0, "dur": 8.0, "to": {"zoom": 7.0}}
        pull = {"type": "pull_back", "t": 5.0, "dur": 2.0, "to": {"zoom": 5.0}}
        for m, what in ((push, "in"), (pull, "out")):
            p = ap.plan_audio(spec(moves=[m]))
            self.assertEqual(cue_names(p), [(5.0, "map_slide_whoosh")], m["type"])
            self.assertEqual(p.cues[0].priority, sd.PRIORITY_NORMAL)
            self.assertIn(f"zoom {what}", p.cues[0].reason)
        for tiny in (dict(push, to={"zoom": 6.4}), dict(pull, to={"zoom": 5.5})):
            self.assertEqual(ap.plan_audio(spec(moves=[tiny])).cues, [], tiny["type"])

    def test_the_desert_wind_bed_is_a_low_rumble_not_a_hiss(self):
        self.assertEqual([c for c, _ in sd.SOUNDS["desert_wind"].candidates], ["amb_atmospheric_05"])

    def test_camera_drift_alone_is_never_a_sound(self):
        self.assertEqual(ap.plan_audio(spec(duration=60)).cues, [])


# ---- 3. determinism -------------------------------------------------------------------------------------

class TestDeterminism(unittest.TestCase):
    def test_same_spec_same_plan_and_same_mixed_bytes(self):
        events = [ev("a", "marker", 2.0, dot=True), ev("b", "pip", 6.0), ev("c", "stat", 9.0), ev("d", "line", 12.0, kind="flow")]
        moves = [{"type": "fly_to", "t": 4.0, "dur": 2.0, "to": {"lon": 80.0, "lat": 10.0, "zoom": 5.0}}]
        hints = {"ambience": [{"t": 1.0, "ambience": "desert_wind"}]}
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            cat = make_catalog(d / "lib")
            _write_wav(d / "vo.wav", _tone(180, 20.0, 0.2))
            outs = []
            for n in range(2):
                plan = am.resolve_assets(ap.plan_audio(spec(events, moves, duration=20), hints), cat)
                outs.append(((cue_names(plan), [b.to_dict() for b in plan.beds]), am.mix_pakmap_audio(plan, d / "vo.wav", d / f"out{n}.wav", duration=20).path.read_bytes()))
            self.assertEqual(outs[0][0], outs[1][0])
            self.assertEqual(outs[0][1], outs[1][1])


# ---- 4. restraint / anti-stacking -----------------------------------------------------------------------

class TestRestraint(unittest.TestCase):
    def test_a_burst_of_markers_is_thinned(self):
        evs = [ev(f"m{i}", "marker", 5.0 + 0.1 * i, dot=True) for i in range(5)]
        plan = ap.plan_audio(spec(evs))
        self.assertEqual(len(plan.cues), 1)
        self.assertEqual(len(plan.dropped), 4)

    def test_the_same_sound_is_not_repeated_inside_its_cooldown(self):
        plan = ap.plan_audio(spec([ev("a", "marker", 5.0, dot=True), ev("b", "marker", 5.5, dot=True), ev("c", "marker", 6.2, dot=True)]))
        self.assertEqual([c.t for c in plan.cues], [5.0, 6.2])

    def test_a_normal_effect_under_a_major_one_is_dropped_and_the_major_wins(self):
        move = {"type": "fly_to", "t": 5.0, "dur": 2.0, "to": {"lon": 100.0, "lat": 20.0, "zoom": 6.0}}
        plan = ap.plan_audio(spec([ev("m", "marker", 5.2, dot=True)], [move]))
        self.assertEqual(cue_names(plan), [(5.0, "map_slide_whoosh")])
        late = ap.plan_audio(spec([ev("m", "marker", 5.2, dot=True)], [dict(move, t=5.25)]))  # major arrives after the normal one
        self.assertEqual([c.sound for c in late.cues], ["map_slide_whoosh"])
        after = ap.plan_audio(spec([ev("m", "marker", 6.2, dot=True)], [move]))  # well after the whoosh: both play
        self.assertEqual(len(after.cues), 2)

    def test_no_more_than_the_density_cap_in_any_window(self):
        evs = [ev(f"p{i}", "pip", 1.0 + i * 1.0) for i in range(10)]
        plan = ap.plan_audio(spec(evs, duration=60))
        for c in plan.cues:
            self.assertLessEqual(len([k for k in plan.cues if c.t <= k.t < c.t + ap.WINDOW_S]), ap.MAX_PER_WINDOW)

    def test_a_cue_at_the_very_end_is_dropped(self):
        plan = ap.plan_audio(spec([ev("m", "marker", 39.95, dot=True)], duration=40))
        self.assertEqual(plan.cues, [])

    def test_explicit_sounds_are_never_thinned(self):
        evs = [ev(f"m{i}", "marker", 5.0 + 0.1 * i, dot=True) for i in range(3)]
        plan = ap.plan_audio(spec(evs), {"events": {f"m{i}": "marker_clack" for i in range(3)}})
        self.assertEqual(len(plan.cues), 3)


# ---- 5. overrides + CSV ---------------------------------------------------------------------------------

HEAD = "item_no,vo_anchor,layer_type,layer_id,label_text,geo_ref,camera_action,sfx,ambience\n"


class TestOverrides(unittest.TestCase):
    def test_sfx_none_silences_an_event_and_a_named_sound_replaces_it(self):
        plan = ap.plan_audio(spec([ev("m", "marker", 5.0, dot=True), ev("p", "pip", 9.0)]), {"events": {"m": "none", "p": "marker_clack"}})
        self.assertEqual(cue_names(plan), [(9.0, "marker_clack")])
        self.assertIn(("m", "sfx=none"), plan.silent)

    def test_sfx_none_on_a_camera_row_silences_a_major_move(self):
        move = {"type": "fly_to", "t": 5.0, "dur": 2.0, "to": {"lon": 100.0, "lat": 20.0, "zoom": 6.0}}
        plan = ap.plan_audio(spec(moves=[move]), {"camera": [{"t": 5.0, "sfx": "none"}]})
        self.assertEqual(plan.cues, [])
        forced = ap.plan_audio(spec(moves=[dict(move, to={"lon": 37.1, "lat": 0.1, "zoom": 6.2})]), {"camera": [{"t": 5.0, "sfx": "fast_whoosh"}]})
        self.assertEqual(cue_names(forced), [(5.0, "fast_whoosh")])

    def test_a_sound_row_places_a_sound_at_its_time_and_none_places_nothing(self):
        plan = ap.plan_audio(spec(), {"cues": [{"t": 12.0, "sfx": "bone_tap"}, {"t": 14.0, "sfx": "none"}]})
        self.assertEqual(cue_names(plan), [(12.0, "bone_tap")])

    def test_catalog_prefix_names_a_library_entry_directly(self):
        plan = ap.plan_audio(spec(), {"cues": [{"t": 3.0, "sfx": "catalog:whoosh_02"}]})
        self.assertEqual(cue_names(plan), [(3.0, "catalog:whoosh_02")])
        with tempfile.TemporaryDirectory() as d:
            cat = make_catalog(Path(d))
            am.resolve_assets(plan, cat)
            self.assertEqual(plan.cues[0].asset, "whoosh_02")
            gone = am.resolve_assets(ap.plan_audio(spec(), {"cues": [{"t": 3.0, "sfx": "catalog:nope_99"}]}), cat)
            self.assertIn("catalog:nope_99", gone.missing)

    def test_csv_columns_reach_the_compiler_hints(self):
        from pakmap.compile import compile_rows

        text = (HEAD + "1,Kenya,hud_title,t,PART 1,,,none,\n1,,marker,m1,NAIROBI,Nairobi,,marker_clack,desert_wind\n"
                "1,,sound,,,,,bone_tap,\n2,w3,camera,,,Kenya,fly_to,none,none\n")
        rows, _ = parse_csv("x.csv", text=text)
        res = compile_rows(rows, [("Kenya", 0.5, 0.9)] + [("w%d" % i, 1.0 + i * 0.5, 1.3 + i * 0.5) for i in range(20)], duration=20.0, validate=False)
        h = res.audio_hints
        self.assertEqual(h["events"], {"t": "none", "m1": "marker_clack"})
        self.assertEqual([c["sfx"] for c in h["cues"]], ["bone_tap"])
        self.assertEqual([a["ambience"] for a in h["ambience"]], ["desert_wind", "none"])
        self.assertEqual([c["sfx"] for c in h["camera"]], ["none"])
        self.assertFalse(any(e["type"] == "sound" for e in res.spec["events"]))

    def test_bad_values_are_row_numbered_with_a_hint(self):
        for cell, col, expect in (("marker_pap", "sfx", "marker_pop"), ("desert_wind", "sfx", "ambience column"), ("marker_pop", "ambience", "sfx column"), ("zzz", "ambience", "unknown ambience")):
            text = "item_no,layer_type,label_text,geo_ref," + col + "\n1,marker,N,Nairobi," + cell + "\n"
            with self.assertRaises(CsvError) as cm:
                parse_csv("x.csv", text=text)
            self.assertIn("row 2", cm.exception.problems[0])
            self.assertIn(expect, cm.exception.problems[0])
        with self.assertRaises(CsvError) as cm:
            parse_csv("x.csv", text="item_no,layer_type,sfx\n1,sound,\n")
        self.assertIn("needs an sfx or an ambience", cm.exception.problems[0])


# ---- 6. ambience ------------------------------------------------------------------------------------------

class TestAmbience(unittest.TestCase):
    def test_no_ambience_unless_the_script_asks(self):
        self.assertEqual(ap.plan_audio(spec([ev("a", "marker", 3.0, dot=True)], duration=60)).beds, [])

    def test_a_bed_runs_until_the_next_ambience_row_or_none(self):
        plan = ap.plan_audio(spec(duration=60), {"ambience": [{"t": 2.0, "ambience": "desert_wind"}, {"t": 20.0, "ambience": "water_ambience"}, {"t": 40.0, "ambience": "none"}]})
        self.assertEqual([(b.start, b.end, b.sound) for b in plan.beds], [(2.0, 20.0, "desert_wind"), (20.0, 40.0, "water_ambience")])

    def test_the_last_bed_ends_with_the_video(self):
        plan = ap.plan_audio(spec(duration=30), {"ambience": [{"t": 5.0, "ambience": "geographic_atmosphere"}]})
        self.assertEqual(plan.beds[0].end, 30.0)

    def test_a_wind_layer_brings_its_own_wind_unless_a_bed_is_playing(self):
        streak = ev("w", "streak", 8.0, t_out=14.0)
        alone = ap.plan_audio(spec([streak]))
        self.assertEqual([(b.sound, b.start, b.end) for b in alone.beds], [("rushing_wind", 8.0, 14.0)])
        busy = ap.plan_audio(spec([streak]), {"ambience": [{"t": 1.0, "ambience": "desert_wind"}]})
        self.assertEqual([b.sound for b in busy.beds], ["desert_wind"])

    def test_explicit_ambience_catalog_entry(self):
        plan = ap.plan_audio(spec(), {"ambience": [{"t": 1.0, "ambience": "catalog:amb_atmospheric_01"}]})
        with tempfile.TemporaryDirectory() as d:
            am.resolve_assets(plan, make_catalog(Path(d)))
        self.assertEqual(plan.beds[0].asset, "amb_atmospheric_01")


# ---- 7. missing / approximate assets -------------------------------------------------------------------

class TestMissingAssets(unittest.TestCase):
    def test_a_sound_with_no_file_is_reported_and_everything_else_still_plays(self):
        plan = ap.plan_audio(spec([ev("m", "marker", 5.0, dot=True)]), {"cues": [{"t": 9.0, "sfx": "record_scratch"}]})
        with tempfile.TemporaryDirectory() as d:
            am.resolve_assets(plan, make_catalog(Path(d)))
        self.assertIn("record_scratch", plan.missing)
        self.assertEqual([c.sound for c in plan.cues], ["marker_pop"])
        self.assertIn("no matching file", plan.missing["record_scratch"])
        self.assertIn("MISSING record_scratch", plan.to_text())

    def test_a_composite_plays_the_parts_it_has_and_reports_the_rest(self):
        plan = ap.plan_audio(spec(), {"cues": [{"t": 9.0, "sfx": "archival_texture"}]})
        with tempfile.TemporaryDirectory() as d:
            am.resolve_assets(plan, make_catalog(Path(d)))
        self.assertEqual(len(plan.cues), 1)
        self.assertEqual([c.sound for c in ap.expand(plan.cues[0])], ["paper_slide", "record_scratch"])
        self.assertIn("record_scratch", plan.missing)
        self.assertNotIn("paper_slide", plan.missing)

    def test_a_missing_ambience_is_skipped_with_a_warning(self):
        plan = ap.plan_audio(spec(), {"ambience": [{"t": 1.0, "ambience": "desert_wind"}]})
        with tempfile.TemporaryDirectory() as d:
            am.resolve_assets(plan, make_catalog(Path(d), skip={"amb_atmospheric_05"}))
        self.assertEqual(plan.beds, [])
        self.assertIn("desert_wind", plan.missing)
        self.assertTrue(plan.warnings)

    def test_an_empty_library_loses_every_sound_without_failing(self):
        import smart_editing as se

        with tempfile.TemporaryDirectory() as d:
            plan = ap.plan_audio(spec([ev("m", "marker", 5.0, dot=True)]), {"ambience": [{"t": 1.0, "ambience": "desert_wind"}]})
            am.resolve_assets(plan, se.SfxCatalog(Path(d), []))
            self.assertEqual((plan.cues, plan.beds), ([], []))
            self.assertEqual(set(plan.missing), {"marker_pop", "desert_wind"})
            res = am.mix_pakmap_audio(plan, Path(d) / "vo.wav", Path(d) / "o.wav")
            self.assertFalse(res.changed)

    def test_approximations_are_labelled_close_ones_are_not(self):
        plan = ap.plan_audio(spec([ev("m", "marker", 5.0, dot=True), ev("k", "sticker", 9.0)]), {"cues": [{"t": 20.0, "sfx": "earth_spin"}, {"t": 25.0, "sfx": "bone_tap"}]})
        with tempfile.TemporaryDirectory() as d:
            am.resolve_assets(plan, make_catalog(Path(d)))
        self.assertIn("earth_spin", plan.approximate)
        self.assertIn("processed", plan.approximate["earth_spin"])
        self.assertIn("bone_tap", plan.approximate)
        self.assertNotIn("marker_pop", plan.approximate)

    def test_the_real_vocabulary_resolves_against_a_library_that_has_the_candidates(self):
        plan = ap.plan_audio(spec(duration=200), {"cues": [{"t": 2.0 + 2 * i, "sfx": s} for i, s in enumerate(sd.SFX_IDS)]})
        with tempfile.TemporaryDirectory() as d:
            am.resolve_assets(plan, make_catalog(Path(d)))
        self.assertEqual(set(plan.missing), {"record_scratch", "mammoth_trumpet", "polar_bear_growl"})


# ---- 8. the mixer: ducking, priority, narration untouched ----------------------------------------------

def _mix_fixture(d: Path, narr: np.ndarray, plan_hints, events=(), moves=(), duration=10.0):
    cat = make_catalog(d / "lib")
    _write_wav(d / "vo.wav", narr)
    plan = am.resolve_assets(ap.plan_audio(spec(events, moves, duration=duration), plan_hints), cat)
    narr_dec = am.decode(d / "vo.wav")
    return plan, narr_dec


class TestMixer(unittest.TestCase):
    def test_nothing_to_add_returns_the_narration_file_itself(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d); _write_wav(d / "vo.wav", _tone(200, 3, 0.2))
            for plan in (ap.plan_audio(spec(), enabled=False), ap.plan_audio(spec())):
                res = am.mix_pakmap_audio(plan, d / "vo.wav", d / "o.wav")
                self.assertFalse(res.changed)
                self.assertEqual(res.path, d / "vo.wav")
            self.assertFalse((d / "o.wav").exists())

    def test_effects_dip_under_speech_and_ambience_dips_more(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            narr = np.concatenate([_tone(200, 5.0, 0.2), np.zeros(5 * SR, np.float32)])  # speech 0-5 s, silence 5-10 s
            hints = {"cues": [{"t": 3.0, "sfx": "marker_pop"}, {"t": 7.0, "sfx": "marker_pop"}], "ambience": [{"t": 0.0, "ambience": "desert_wind"}]}
            plan, nd = _mix_fixture(d, narr, hints)
            sfx, amb, _ = am.build_bus(plan, nd, 10.0)
            pk = lambda x, a, b: float(np.abs(x[int(a * SR):int(b * SR)]).max())  # noqa: E731
            speech, quiet = pk(sfx, 3.0, 3.4), pk(sfx, 7.0, 7.4)
            self.assertLess(speech, quiet)
            self.assertAlmostEqual(speech / quiet, 1 - am.DUCK_SFX, delta=0.06)
            a_speech, a_quiet = np.sqrt((amb[int(2 * SR):int(4 * SR)] ** 2).mean()), np.sqrt((amb[int(7 * SR):int(9 * SR)] ** 2).mean())
            self.assertAlmostEqual(a_speech / a_quiet, 1 - am.DUCK_AMBIENCE, delta=0.08)
            self.assertLess(1 - am.DUCK_AMBIENCE, 1 - am.DUCK_SFX)

    def test_a_major_effect_pushes_the_ambience_down_while_it_sounds(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            move = {"type": "fly_to", "t": 5.0, "dur": 2.0, "to": {"lon": 100.0, "lat": 20.0, "zoom": 6.0}}
            hints = {"ambience": [{"t": 0.0, "ambience": "desert_wind"}]}
            plan, nd = _mix_fixture(d, np.zeros(10 * SR, np.float32), hints, moves=[move])
            calm, _ = _mix_fixture(d, np.zeros(10 * SR, np.float32), hints)
            _, amb, _ = am.build_bus(plan, nd, 10.0)
            _, amb0, _ = am.build_bus(calm, nd, 10.0)  # the same bed with no major effect
            rms = lambda x, a, b: float(np.sqrt((x[int(a * SR):int(b * SR)] ** 2).mean()))  # noqa: E731
            ratio = rms(amb, 5.3, 5.9) / rms(amb0, 5.3, 5.9)
            self.assertTrue(0.4 < ratio < 0.6, ratio)  # about -6 dB under the whoosh
            self.assertAlmostEqual(rms(amb, 8.0, 9.0) / rms(amb0, 8.0, 9.0), 1.0, delta=0.01)

    def test_the_narration_is_never_changed_even_when_the_sum_would_clip(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            narr = _tone(200, 6.0, 0.96)
            hints = {"cues": [{"t": 1.0 + i * 0.7, "sfx": "marker_clack"} for i in range(6)], "ambience": [{"t": 0.0, "ambience": "desert_wind"}]}
            plan, nd = _mix_fixture(d, narr, hints, duration=6.0)
            res = am.mix_pakmap_audio(plan, d / "vo.wav", d / "o.wav", duration=6.0)
            self.assertTrue(res.changed)
            self.assertLessEqual(res.peak, am.PEAK_LIMIT + 1e-4 if res.bus_scale < 1 else 1.0)
            out = am.decode(res.path)
            sfx, amb, _ = am.build_bus(plan, nd, 6.0)
            base = np.zeros_like(out); base[:len(nd)] = nd[:len(out)]
            np.testing.assert_allclose(out - (sfx + amb)[:len(out)] * res.bus_scale, base, atol=2e-4)

    def test_a_quiet_narration_is_bit_identical_in_the_mix_where_nothing_plays(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            narr = _tone(200, 8.0, 0.2)
            plan, nd = _mix_fixture(d, narr, {"cues": [{"t": 6.0, "sfx": "marker_pop"}]}, duration=8.0)
            res = am.mix_pakmap_audio(plan, d / "vo.wav", d / "o.wav", duration=8.0)
            out = am.decode(res.path)
            np.testing.assert_allclose(out[:5 * SR], nd[:5 * SR], atol=1e-6)

    def test_library_files_recorded_at_different_levels_come_out_at_the_vocabulary_level(self):
        import smart_editing as se

        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            lib = d / "lib"
            ents = []
            for cid, amp in (("ui_pop_01", 0.02), ("amb_atmospheric_05", 0.01)):
                _write_wav(lib / f"{cid}.wav", _tone(400, 3.0, amp) if cid.startswith("ui") else (amp * np.random.default_rng(1).uniform(-1, 1, 3 * SR)).astype(np.float32))
                ents.append(se.SfxEntry(id=cid, file=f"{cid}.wav", category="ui", tags=(), intensity="low", duration=3.0))
            plan = am.resolve_assets(ap.plan_audio(spec(), {"cues": [{"t": 1.0, "sfx": "marker_pop"}], "ambience": [{"t": 4.0, "ambience": "desert_wind"}]}), se.SfxCatalog(lib, ents))
            sfx, amb, _ = am.build_bus(plan, np.zeros((8 * SR, 2), np.float32), 8.0)
            self.assertAlmostEqual(float(np.abs(sfx).max()), sd.SOUNDS["marker_pop"].volume, delta=0.01)
            mid = amb[int(5.3 * SR):int(6.1 * SR)]  # past the fade-in, before the loop join
            self.assertAlmostEqual(float(np.sqrt((mid ** 2).mean())) / sd.SOUNDS["desert_wind"].volume, am.AMBIENCE_REF_RMS, delta=0.08)

    def test_the_mix_is_as_long_as_the_video(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            plan, nd = _mix_fixture(d, _tone(200, 4.0, 0.2), {"cues": [{"t": 1.0, "sfx": "marker_pop"}]}, duration=9.0)
            res = am.mix_pakmap_audio(plan, d / "vo.wav", d / "o.wav", duration=9.0)
            self.assertAlmostEqual(len(am.decode(res.path)) / SR, 9.0, delta=0.01)

    def test_beds_loop_to_fill_their_window(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            plan, nd = _mix_fixture(d, np.zeros(12 * SR, np.float32), {"ambience": [{"t": 1.0, "ambience": "desert_wind"}]}, duration=12.0)  # the noise asset is 3 s
            _, amb, _ = am.build_bus(plan, nd, 12.0)
            self.assertGreater(float(np.abs(amb[int(10 * SR):int(11 * SR)]).max()), 0.0)
            self.assertEqual(float(np.abs(amb[:int(0.9 * SR)]).max()), 0.0)

    def test_priority_order_is_narration_then_major_then_normal_then_ambience(self):
        from pakmap.sounds import PRIORITY_RANK
        self.assertLess(PRIORITY_RANK["major"], PRIORITY_RANK["normal"])
        self.assertLess(PRIORITY_RANK["normal"], PRIORITY_RANK["ambience"])
        self.assertLess(am.DUCK_AMBIENCE, 1.0)
        self.assertLess(am.DUCK_SFX, am.DUCK_AMBIENCE)  # ambience yields more than effects do


# ---- 9. audio policy and mode isolation -----------------------------------------------------------------

class TestPolicyAndIsolation(unittest.TestCase):
    def test_the_pakmap_policy(self):
        p = PAKMAP_POLICY
        self.assertEqual((p.narration, p.pakmap_sfx, p.pakmap_ambience, p.generic_sfx, p.generic_ambience, p.zoom_blur_sound), (True, True, True, False, False, False))

    def test_sound_design_off_keeps_narration_and_the_generic_systems_off(self):
        p = policy_for("pakmap", sound_design=False)
        self.assertEqual((p.narration, p.pakmap_sfx, p.pakmap_ambience, p.generic_sfx, p.generic_ambience, p.zoom_blur_sound), (True, False, False, False, False, False))

    def test_generic_flags_are_forced_off_for_pakmap_only_and_the_input_is_untouched(self):
        user = {"sound_effects": True, "scene_ambience": True, "zoom_blur_sound": True}
        before = dict(user)
        self.assertEqual(generic_flags_for("pakmap", user), {"sound_effects": False, "scene_ambience": False, "zoom_blur_sound": False})
        self.assertEqual(user, before)
        for mode in ("overscaled", "exp_solar", "map_facts", "other"):
            self.assertEqual(generic_flags_for(mode, user), before, mode)
            p = policy_for(mode)
            self.assertFalse(p.pakmap_sfx or p.pakmap_ambience, mode)

    def test_no_other_style_imports_pakmap(self):
        offenders = []
        for rel in ("smart_editing.py", "video_generator.py", "scene_graph", "editorial", "sfx", "map_scene"):
            path = ROOT / rel
            files = [path] if path.is_file() else (list(path.rglob("*.py")) if path.is_dir() else [])
            for f in files:
                text = f.read_text(encoding="utf-8", errors="ignore")
                if re.search(r"^\s*(from|import)\s+pakmap\b", text, re.M):
                    offenders.append(str(f.relative_to(ROOT)))
        self.assertEqual(offenders, [])

    def test_pakmap_never_calls_the_generic_mixers_or_planners(self):
        banned = ("mix_sfx_with_narration", "plan_exp_solar", "SmartEditingSettings", "mark_zoom_blur_transitions", "plan_smart_editing", "exp_solar_audio")
        for f in (ROOT / "pakmap").glob("*.py"):
            text = f.read_text(encoding="utf-8")
            for name in banned:
                self.assertNotIn(name, text, f"{f.name} uses {name}")

    def test_pakmap_sounds_do_not_enter_the_shared_catalog(self):
        import smart_editing as se

        with tempfile.TemporaryDirectory() as d:
            cat = make_catalog(Path(d))
            before = [e.id for e in cat.entries]
            am.resolve_assets(ap.plan_audio(spec([ev("m", "marker", 5.0, dot=True)])), cat)
            self.assertEqual([e.id for e in cat.entries], before)


# ---- 10. a whole generate run ---------------------------------------------------------------------------

CSV = ("item_no,vo_anchor,layer_type,layer_id,label_text,sub_text,geo_ref,camera_action,sfx,ambience\n"
       "1,Kenya has,camera,,,,Kenya,start,,\n"
       "1,Kenya has,hud_title,t1,PART 1,THE EMPTY HALF,,,,desert_wind\n"
       "1,Nairobi,marker,m1,NAIROBI,,Nairobi,,,\n"
       "2,rain,marker,m2,MOMBASA,,Mombasa,,none,\n")


class TestGenerateRun(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        (self.d / "s.csv").write_text(CSV, encoding="utf-8")
        _write_wav(self.d / "vo.wav", _tone(200, 12.0, 0.2))
        self.words = [("Kenya", 0.5, 0.9), ("has", 0.9, 1.1), ("Nairobi", 3.0, 3.5), ("rain", 7.0, 7.4)]
        self.cat = make_catalog(self.d / "lib")
        self.exported = []

    def tearDown(self):
        self.tmp.cleanup()

    def run_gen(self, **kw):
        from unittest import mock
        from pakmap import app_integration as ai

        def fake_render(spec_, out, progress=None, cancel_check=None, log=print):
            Path(out).write_bytes(b"x")
            return type("O", (), {"sidecar": {}})()

        def fake_export(graph, silent, *, voiceover_path, output_path, **k):
            self.exported.append(voiceover_path)
            Path(output_path).write_bytes(b"x")

        with mock.patch("scene_graph.app_integration._export_via_existing_renderer", fake_export), \
             mock.patch("scene_graph.app_integration.validate_rendered_output", lambda *a, **k: None), \
             mock.patch.object(ai, "voiceover_duration", lambda p: 12.0), \
             mock.patch("pakmap.compile.check_with_engine", lambda s: ([], [], True)):
            return ai.generate_pakmap_video(self.d / "s.csv", self.d / "vo.wav", self.d / "out.mp4", work_dir=self.d / "w", whisper_words=self.words,
                                            render=fake_render, sound_catalog=self.cat, **kw)

    def test_sound_design_on_exports_the_mixed_audio_and_reports_the_plan(self):
        r = self.run_gen()
        self.assertTrue(r.ok, r.errors)
        self.assertEqual(Path(self.exported[0]), self.d / "w" / "pakmap_audio.wav")
        self.assertTrue(r.audio_mix.changed)
        sounds = [c.sound for c in r.audio.cues]
        self.assertIn("marker_pop", sounds)
        self.assertEqual([b.sound for b in r.audio.beds], ["desert_wind"])
        self.assertTrue((self.d / "w" / "pakmap_sound_plan.txt").is_file())
        self.assertEqual(sounds.count("marker_pop"), 1)  # m2 says sfx=none

    def test_sound_design_off_exports_the_narration_untouched(self):
        r = self.run_gen(sound_design=False)
        self.assertTrue(r.ok, r.errors)
        self.assertEqual(Path(self.exported[0]), self.d / "vo.wav")
        self.assertFalse(r.audio.cues or r.audio.beds)
        self.assertFalse((self.d / "w" / "pakmap_audio.wav").exists())

    def test_a_mixer_failure_still_makes_the_video_and_says_so(self):
        from unittest import mock
        with mock.patch("pakmap.audio_mix.mix_pakmap_audio", side_effect=am.AudioMixError("disk full")):
            r = self.run_gen()
        self.assertTrue(r.ok)
        self.assertEqual(Path(self.exported[0]), self.d / "vo.wav")
        self.assertTrue(any("sound design failed" in w and "disk full" in w for w in r.warnings))
        self.assertEqual(r.sound_failed, "disk full")  # the app shows this: never a plain success

    def test_running_out_of_memory_while_mixing_is_reported_as_a_sound_failure(self):
        from unittest import mock
        with mock.patch("pakmap.audio_mix.mix_pakmap_audio", side_effect=MemoryError()):
            r = self.run_gen()
        self.assertTrue(r.ok)
        self.assertEqual(Path(self.exported[0]), self.d / "vo.wav")
        self.assertIn("not enough memory", r.sound_failed)
        self.assertTrue(any("not enough memory" in w for w in r.warnings))

    def test_a_working_mix_or_sound_design_off_is_no_sound_failure(self):
        self.assertIsNone(self.run_gen().sound_failed)
        self.assertIsNone(self.run_gen(sound_design=False).sound_failed)

    def test_a_narration_peaking_above_full_scale_keeps_its_sound_design(self):
        narr = _tone(200, 12.0, 0.2)
        narr[int(5.0 * SR):int(5.2 * SR)] = _tone(200, 0.2, 1.0)  # one word louder than full scale (the reported 1.010 peak)
        with wave.open(str(self.d / "vo.wav"), "wb") as w:  # stereo, so the level is not lowered by an upmix
            w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
            w.writeframes((np.stack([narr, narr], axis=1) * 32767).astype("<i2").tobytes())
        r = self.run_gen()
        self.assertTrue(r.ok)
        self.assertIsNone(r.sound_failed)
        self.assertGreater(r.audio_mix.clip_dip_s, 0.0)
        self.assertLess(r.audio_mix.clip_dip_s, 1.0)  # the bed dips only around the loud word
        mixed, vo = am.decode(r.audio_mix.path), am.decode(self.d / "vo.wav")
        self.assertGreater(float(np.abs(mixed[: 4 * SR] - vo[: 4 * SR]).max()), 1e-3)  # effects and ambience are in the video

    def test_missing_sounds_are_in_the_warnings(self):
        import smart_editing as se
        self.cat = se.SfxCatalog(self.d / "lib", [e for e in self.cat.entries if e.id not in ("ui_pop_01", "text_pop_01", "ui_08")])
        r = self.run_gen()
        self.assertTrue(r.ok)
        self.assertTrue(any("missing sound marker_pop" in w for w in r.warnings))

    def test_the_generic_audio_systems_are_not_called_during_a_pakmap_run(self):
        import smart_editing as se
        from unittest import mock
        with mock.patch.object(se, "mix_sfx_with_narration", side_effect=AssertionError("generic mixer used")), \
             mock.patch.object(se, "_ffmpeg_mix_layers", side_effect=AssertionError("generic mixer used")):
            r = self.run_gen()
        self.assertTrue(r.ok, r.errors)


# ---- Phase 8: reference-video sound design (synthesized sounds, richer mapping) ----------------------------------

class TestSynthesizedSounds(unittest.TestCase):
    def test_every_generator_is_deterministic_finite_and_below_clipping(self):
        from pakmap import synth

        for name, gen in synth.GENERATORS.items():
            a, b = gen(), gen()
            self.assertTrue(np.array_equal(a, b), name)
            self.assertEqual(a.ndim, 2)
            self.assertTrue(np.isfinite(a).all(), name)
            self.assertLess(float(np.abs(a).max()), 1.0, name)
            self.assertGreater(float(np.abs(a).max()), 0.3, name)

    def test_the_sounds_have_the_character_they_claim(self):
        from pakmap import synth

        def centroid(name):
            x = synth.render(name)[:, 0]
            sp = np.abs(np.fft.rfft(x)) ** 2
            return float((np.fft.rfftfreq(len(x), 1 / synth.SR) * sp).sum() / sp.sum())

        for low in ("deep_thud", "muffled_explosion", "industrial_hum", "airplane_hum"):
            self.assertLess(centroid(low), 200, low)
        for high in ("draw_zap", "paper_slide", "boil_sizzle", "birds_chirping"):
            self.assertGreater(centroid(high), 2500, high)
        self.assertTrue(500 < centroid("clock_chime") < 2500)

    def test_every_vocabulary_sound_finds_a_source_except_the_declared_gaps(self):
        gaps = {"record_scratch", "mammoth_trumpet", "polar_bear_growl"}
        plan = ap.plan_audio(spec(duration=200), {"cues": [{"t": 2.0 + 2 * i, "sfx": i_} for i, i_ in enumerate(sd.SFX_IDS)],
                                      "ambience": [{"t": 1.0, "ambience": "cold_wind"}]})
        with tempfile.TemporaryDirectory() as d:
            am.resolve_assets(plan, make_catalog(Path(d)))
        self.assertEqual(set(plan.missing), gaps)
        for sid in ("deep_thud", "draw_zap", "cash_register", "steam_chug", "paper_slide"):
            self.assertIn(sid, plan.approximate)
            self.assertIn("synthesized", plan.approximate[sid])
        self.assertNotIn("counter_ticks", plan.approximate)

    def test_ambience_ids_resolve_too(self):
        for amb in ("cold_wind", "industrial_hum", "airplane_hum", "space_drone", "water_lapping"):
            plan = ap.plan_audio(spec(), {"ambience": [{"t": 1.0, "ambience": amb}]})
            with tempfile.TemporaryDirectory() as d:
                am.resolve_assets(plan, make_catalog(Path(d)))
            self.assertEqual(len(plan.beds), 1, amb)
            self.assertNotIn(amb, plan.missing)

    def test_a_synthesized_effect_and_bed_are_audible_in_the_mix(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            plan = am.resolve_assets(ap.plan_audio(spec(duration=10), {"cues": [{"t": 2.0, "sfx": "deep_thud"}], "ambience": [{"t": 5.0, "ambience": "industrial_hum"}]}), make_catalog(d / "lib"))
            sfx, amb, used = am.build_bus(plan, np.zeros((10 * SR, 2), np.float32), 10.0)
            self.assertAlmostEqual(float(np.abs(sfx).max()), sd.SOUNDS["deep_thud"].volume, delta=0.01)
            self.assertGreater(float(np.abs(amb[int(7 * SR):int(9 * SR)]).max()), 0.005)
            self.assertEqual([u["asset"] for u in used], ["synth:deep_thud", "synth:industrial_hum"])

    def test_animal_calls_are_reported_missing_not_faked(self):
        plan = ap.plan_audio(spec(), {"cues": [{"t": 3.0, "sfx": "mammoth_trumpet"}]})
        with tempfile.TemporaryDirectory() as d:
            am.resolve_assets(plan, make_catalog(Path(d)))
        self.assertEqual(plan.cues, [])
        self.assertIn("needs a real recording", plan.missing["mammoth_trumpet"])


if __name__ == "__main__":
    unittest.main()
