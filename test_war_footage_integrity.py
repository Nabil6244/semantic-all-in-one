"""Stage B of the render-050 repair: footage integrity as three separate checks (visual usability, video relevance, moment relevance), earlier
picks re-validated, no arbitrary fill, footage for lines without a place name.

Real frames: test_fixtures/war_render050/frames (labels.json from Stage A, labels_corrections.json from Stage B).
"""

import json
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from cinematic_explainer.war import director_capture as C
from cinematic_explainer.war import director_frames as F

FR = Path(__file__).resolve().parent / "test_fixtures" / "war_render050" / "frames"


def _frame(key, t, size=(320, 180)):
    return np.asarray(Image.open(FR / f"{key}_{t}.jpg").convert("RGB").resize(size, Image.BOX))


def _window_usable(key, size=(320, 180)):
    """A clip window is usable only when every frame in it is footage (the way choose_window / capture judge it)."""
    a, b = _frame(key, "t1", size), _frame(key, "t3", size)
    k1, _d, _f = F.classify(a, None)
    k3, _d, _f = F.classify(b, a)
    return k1 == F.FOOTAGE and k3 == F.FOOTAGE, (k1, k3)


def _expected():
    labels = json.loads((FR / "labels.json").read_text())
    fixes = json.loads((FR / "labels_corrections.json").read_text())
    out = {}
    for k, v in labels.items():
        if k.startswith("_"):
            continue
        out[k] = fixes[k]["window_usable"] if k in fixes else v["usable"]
    return out


class VisualUsability(unittest.TestCase):
    def test_render050_frames_judged_per_window(self):
        for key, usable in _expected().items():
            got, kinds = _window_usable(key)
            self.assertEqual(got, usable, f"{key}: kinds {kinds}")

    def test_the_old_check_accepted_the_bad_frames(self):
        """The original failure: at the size the old check worked with, text cannot be seen and every bad clip passed as footage."""
        for key in ("a001", "a084", "a098", "a120", "a156", "a168", "a176"):
            a, b = _frame(key, "t1", (160, 90)), _frame(key, "t3", (160, 90))
            self.assertEqual(F.text_kind(a), "", key)
            self.assertEqual(F.text_kind(b), "", key)

    def test_text_lines_are_found_by_shape(self):
        img = np.full((180, 320, 3), 90, np.uint8)
        rng = np.random.default_rng(1)
        img[:100] = rng.integers(40, 160, (100, 320, 3))          # a textured picture above
        img[150:162, 30:290] = 20                                   # a dark subtitle bar
        for x in range(36, 284, 6):                                 # white character strokes on it
            img[152:160, x:x + 2] = 240
        lines = F.text_lines(img)
        self.assertTrue(any(ln["y"] > 0.8 and ln["w"] > 0.6 for ln in lines), lines)
        self.assertEqual(F.text_kind(img), "overlay_text")

    def test_texture_is_not_text(self):
        rng = np.random.default_rng(2)
        img = rng.integers(0, 255, (180, 320, 3)).astype(np.uint8)  # rubble / foliage: strokes everywhere, no isolated line
        self.assertEqual(F.text_kind(img), "")

    def test_small_pictures_are_not_read(self):
        img = np.zeros((90, 160, 3), np.uint8)
        self.assertEqual(F.text_kind(img), "")

    def test_capture_refuses_a_clip_with_text_on_its_frames(self):
        clean = [_frame("a011", "t1"), _frame("a011", "t3")] * 4
        self.assertEqual(C.text_on_frames(clean), "")
        subtitled = clean[:5] + [_frame("a120", "t1"), _frame("a120", "t3"), _frame("a156", "t3")]
        self.assertIn("text over the footage", C.text_on_frames(subtitled))

    def test_one_stray_frame_does_not_refuse_a_clip(self):
        frames = [_frame("a011", "t1")] * 9 + [_frame("a168", "t1")]
        self.assertEqual(C.text_on_frames(frames), "")



# ---- subject discovery: a line without a place still gets footage of its section's subject ------------------------------------------
from cinematic_explainer.war import footage_director as FD  # noqa: E402
from cinematic_explainer.war import narration_read as N  # noqa: E402

FX = FR.parent


def _readings():
    return N.read_scenes(json.loads((FX / "scenes.json").read_text()))


class SubjectDiscovery(unittest.TestCase):
    def test_lines_without_a_place_take_their_sections_subject(self):
        rd = _readings()
        by_text = {r.text: r for r in rd.values()}
        core = by_text["The core issue is security guarantees."]
        self.assertEqual(core.subject_from, "section")
        self.assertTrue(core.section_terms)
        grid = by_text["It has not broken Ukraine yet."]
        self.assertIn("substation", grid.section_terms)

    def test_part_headings_open_a_new_subject(self):
        rd = _readings()
        heading = next(r for r in rd.values() if r.text.startswith("Part two."))
        self.assertTrue(N.section_break(heading.text))
        self.assertEqual(heading.section_terms, [])

    def test_countries_nationalities_and_broken_tokens_are_not_a_subject(self):
        rd = _readings()
        state = next(r for r in rd.values() if r.text.startswith("This is the state of the Russia-Ukraine war"))
        self.assertEqual(N.own_subject(state), [])
        officials = next(r for r in rd.values() if r.text.startswith("On this point, American, Ukrainian and European officials"))
        self.assertEqual(N.own_subject(officials), [])

    def test_the_original_failure_and_the_fix(self):
        """Render 050: the director sent these lines to graphics as ANALYSIS / STATISTIC sentences, without searching."""
        dec = json.loads((FX / "director_decisions.json").read_text())
        before = [no for no in ("2", "3", "5", "10", "14", "49", "53") if dec.get(no, {}).get("decision") == "graphics"]
        self.assertEqual(len(before), 7)
        rd = _readings()
        FD.widen_to_section(rd)
        self.assertTrue(all(rd[no].footage_wanted for no in before), [(no, rd[no].text[:40]) for no in before if not rd[no].footage_wanted])

    def test_headings_and_outros_stay_graphics(self):
        rd = _readings()
        FD.widen_to_section(rd)
        for r in rd.values():
            if N.section_break(r.text) or "subscribe" in r.text.lower():
                self.assertFalse(getattr(r, "widened", False), r.text)


# ---- moment relevance ------------------------------------------------------------------------------------------------------------
from types import SimpleNamespace  # noqa: E402

from cinematic_explainer.war import director_moment as M  # noqa: E402


def _reading(terms):
    return SimpleNamespace(section_terms=list(terms), key_terms=list(terms))


class MomentRelevance(unittest.TestCase):
    UATV = [{"start": 600.0, "duration": 4, "text": "drones hit an oil refinery near St Petersburg overnight"},
            {"start": 845.0, "duration": 4, "text": "Russia's Rassvet satellite system is used for military purposes"}]

    def test_a_short_upload_needs_no_transcript(self):
        self.assertEqual(M.check(90.0, None, _reading(["St Petersburg"])), (True, None, ""))

    def test_a_long_programme_without_a_transcript_is_refused(self):
        ok, _h, why = M.check(900.0, None, _reading(["St Petersburg"]))
        self.assertFalse(ok)
        self.assertIn("without a transcript", why)

    def test_the_cut_must_sit_where_the_programme_talks_about_the_line(self):
        ok, hint, _w = M.check(900.0, self.UATV, _reading(["St Petersburg", "drones"]))
        self.assertTrue(ok)
        self.assertEqual(hint, 600.0)
        self.assertTrue(M.near(hint)(610.0, 618.0))
        self.assertFalse(M.near(hint)(845.0, 853.0))      # render 050's cut: the satellite segment

    def test_a_programme_that_never_names_the_subject_is_refused(self):
        ok, _h, why = M.check(900.0, self.UATV, _reading(["Kostiantynivka"]))
        self.assertFalse(ok)
        self.assertIn("never talks about", why)


# ---- re-validation of earlier picks -----------------------------------------------------------------------------------------------
import tempfile  # noqa: E402


class _Searcher:
    def __init__(self, duration=None, segs=None):
        self.duration, self.segs = duration, segs

    def details(self, c):
        c.duration = self.duration
        return {}

    def transcript(self, vid):
        return self.segs


class Revalidation(unittest.TestCase):
    def _rec(self, td, title="St. Petersburg under attack: drones hit an oil refinery", start=845.0):
        p = Path(td) / "001.mp4"
        p.write_bytes(b"x")
        return {"local_path": str(p), "video_id": "KXV0DBHR3sk", "video_title": title, "channel": "UATV English", "clip_start": start}

    def _reading(self):
        return N.read("On the night of the ninth of November, more than a hundred drones crossed into Russia and flew toward the outskirts "
                      "of Saint Petersburg.")

    def test_render050_first_clip_fails_today(self):
        """The studio panel kept by 'chosen by an earlier run: kept' is refused on its own frames and on its moment."""
        with tempfile.TemporaryDirectory() as td:
            frames = [_frame("a001", "t1"), _frame("a001", "t3")] * 4
            why = FD.revalidate(self._rec(td), self._reading(), _Searcher(900.0, MomentRelevance.UATV), frames_of=lambda *a, **k: frames)
            self.assertTrue(any("text over the footage" in w for w in why), why)
            self.assertTrue(any(w.startswith("moment:") for w in why), why)

    def test_a_clean_relevant_pick_is_kept(self):
        with tempfile.TemporaryDirectory() as td:
            frames = [_frame("a011", "t1"), _frame("a011", "t3")] * 4
            why = FD.revalidate(self._rec(td, start=60.0), self._reading(), _Searcher(90.0), frames_of=lambda *a, **k: frames)
            self.assertEqual(why, [])

    def test_a_missing_file_fails(self):
        why = FD.revalidate({"local_path": "/nope/001.mp4"}, self._reading(), None)
        self.assertEqual(why, ["file: the kept clip is missing"])


# ---- the War library: a clip must fit the line, not only the CSV prompt; reuse per source video; frames checked --------------------
from cinematic_explainer.war import library as L  # noqa: E402


def _view(subject, words):
    return L._clip_view({"subject": subject, "words": words})


class LibraryRelevance(unittest.TestCase):
    def test_render050_generic_prompt_no_longer_puts_one_road_clip_on_unrelated_lines(self):
        road = _view("frontline_road", "frontline road smoke burning vehicle soldier")
        for line in ("On one side of the war, the strikes are getting heavier.", "They produced a swap of 314 prisoners, but no ceasefire."):
            self.assertFalse(L.line_fits(road, L.line_terms(line, ["Abu Dhabi"])), line)
        self.assertTrue(L.line_fits(road, L.line_terms("And on the front line, hundreds of battles are being fought every single day.")))

    def test_a_putin_clip_needs_a_line_about_putin(self):
        putin = _view("putin", "Putin meeting Kremlin officials")
        self.assertFalse(L.line_fits(putin, L.line_terms("Russia wants far more.", ["Moscow", "Donetsk"])))
        self.assertTrue(L.line_fits(putin, L.line_terms("And on the sixth of November, Vladimir Putin changed a decree.")))

    def test_an_action_only_subject_needs_two_shared_words(self):
        aftermath = _view("strike_aftermath", "strike aftermath damaged building rubble")
        self.assertFalse(L.line_fits(aftermath, L.line_terms("The strikes are getting heavier.")))
        self.assertTrue(L.line_fits(aftermath, L.line_terms("The strike left the building in rubble.")))

    def test_two_clips_of_one_upload_count_as_one_source(self):
        a = {"file": "a.mp4", "url": "https://www.youtube.com/watch?v=EgtVGTb38fk"}
        b = {"file": "b.mp4", "url": "https://youtu.be/EgtVGTb38fk"}
        self.assertEqual(L.source_key(a), L.source_key(b))

    def test_library_clips_are_checked_once_and_again_when_changed(self):
        with tempfile.TemporaryDirectory() as td:
            lib = Path(td)
            (lib / "s").mkdir()
            for n in ("clean", "subtitled"):
                (lib / "s" / f"{n}.mp4").write_bytes(n.encode())
            clips = [{"file": "s/clean.mp4"}, {"file": "s/subtitled.mp4"}]
            calls = []

            def check(p):
                calls.append(p.name)
                return "picture: text over the footage" if "subtitled" in p.name else ""
            self.assertEqual([c["file"] for c in L.usable_clips(clips, lib, check)], ["s/clean.mp4"])
            self.assertEqual([c["file"] for c in L.usable_clips(clips, lib, check)], ["s/clean.mp4"])
            self.assertEqual(len(calls), 2)                                   # cached
            (lib / "s" / "clean.mp4").write_bytes(b"changed file")
            L.usable_clips(clips, lib, check)
            self.assertEqual(calls[-1], "clean.mp4")                          # re-checked after a change


if __name__ == "__main__":
    unittest.main()
