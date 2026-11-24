"""Podcast Cut phase 1: thoughts, junk, picking to a target length, hook, clip CSV, checker, captions parsing."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from podcast_cut import check, clipcsv, director, fetch, picker, runner

GOOD = ("You need to understand that discipline is the key to everything you want in your life. "
        "Most people never start because they wait for motivation. Stop waiting and start doing the work today.")
STORY = ("I remember when I was nineteen and I decided I was done being a loser. "
         "I learned that fear can drive real change if you let it.")
MEH = ("Um so yeah it was kind of like a thing you know sort of what we were um doing back then I mean. "
       "And uh the weather was okay I guess and we had some lunch.")
AD = "This episode is brought to you by Athletic Greens, use the code SHOW for a free trial at the link in the description."
QUESTION = "What do you think makes people change their life?"


def make_words(paragraphs, pause=1.0, wps=2.6):
    """[(word, start, end)] at wps words per second, a pause between paragraphs, 0.25 s between sentences."""
    words, t = [], 0.0
    for p in paragraphs:
        for w in p.split():
            words.append((w, round(t, 3), round(t + 1 / wps - 0.05, 3)))
            t += 1 / wps
            if w.endswith((".", "?", "!")):
                t += 0.25
        t += pause
    return words


class Thoughts(unittest.TestCase):
    def test_question_is_its_own_thought(self):
        ts = picker.thoughts(make_words([QUESTION, GOOD]))
        self.assertTrue(ts[0].question)
        self.assertTrue(ts[0].text.endswith("?"))
        self.assertFalse(ts[1].question)

    def test_hard_pause_splits_and_short_pause_does_not(self):
        ts = picker.thoughts(make_words([GOOD, STORY], pause=2.0))
        self.assertEqual(len(ts), 2)
        ts = picker.thoughts(make_words([GOOD + " " + STORY], pause=2.0))
        self.assertEqual(len(ts), 1)

    def test_no_punctuation_splits_on_pauses(self):
        raw = make_words([GOOD.replace(".", ""), STORY.replace(".", "")], pause=0.9)
        self.assertFalse(picker.has_punctuation(raw))
        self.assertEqual(len(picker.thoughts(raw)), 2)


class Junk(unittest.TestCase):
    def test_ad_and_plug_marked(self):
        ts = picker.thoughts(make_words([GOOD, AD, STORY], pause=2.0))
        picker.mark_junk(ts)
        self.assertEqual([bool(t.junk) for t in ts], [False, True, False])

    def test_sponsorblock_range_marked(self):
        ts = picker.thoughts(make_words([GOOD, STORY], pause=2.0))
        picker.mark_junk(ts, [{"start": ts[1].start - 1, "end": ts[1].end + 1, "category": "sponsor"}])
        self.assertIn("SponsorBlock", ts[1].junk)
        self.assertFalse(ts[0].junk)


class Picking(unittest.TestCase):
    def episode(self, n=40):
        paras = []
        for k in range(n):
            paras += [QUESTION, GOOD, MEH, STORY] if k % 3 == 0 else [GOOD, MEH, STORY]
            if k % 10 == 5:
                paras.append(AD)
        return make_words(paras, pause=1.8)

    def test_hits_target_in_order_without_junk(self):
        words = self.episode()
        res = picker.pick(words, target_min=5)
        clips = res["clips"]
        self.assertEqual(clips[0].role, "hook")
        tot = check.total_length(clips)
        self.assertLess(abs(tot - 300), 60, tot)
        body = clips[1:]
        self.assertEqual([c.start for c in body], sorted(c.start for c in body))
        self.assertFalse(any("Athletic" in c.text for c in clips))
        self.assertFalse(any(c.text.startswith("Um so yeah") for c in body))   # filler loses to the good lines
        errors, warns = check.check(clips, duration=words[-1][2], target_min=5, words=words)
        self.assertEqual(errors, [])
        self.assertFalse([w for w in warns if "inside the word" in w])

    def test_question_kept_only_with_answer(self):
        words = self.episode(12)
        res = picker.pick(words, target_min=2)
        ts = res["thoughts"]
        kept = {i for c in res["clips"] for i in c.thoughts}
        for i in kept:
            if ts[i].question:
                self.assertIn(i + 1, kept)

    def test_hook_length_and_clean_start(self):
        res = picker.pick(self.episode(), target_min=5)
        h = res["clips"][0]
        self.assertTrue(8 <= h.length <= 30, h.length)
        self.assertNotIn(h.text.split()[0].lower().strip(",."), picker.DANGLING)

    def test_short_episode_notes_it(self):
        res = picker.pick(make_words([GOOD, STORY], pause=2.0), target_min=30)
        self.assertTrue(any("only has" in n for n in res["notes"]))


class PickingRealFaults(unittest.TestCase):
    """Faults from a real 146-min episode (9VlvbpXwLJs): Whisper punctuation gone after minute 33, the hook heard again
    inside a body clip, the talk's own 'next 45 minutes' intro, a 6 s scrap, one hour skipped."""

    def episode(self, n=60, punct_until=30):
        paras = []
        for k in range(n):
            ps = [GOOD, MEH, STORY]
            if k >= punct_until:     # Whisper stopped punctuating: lower case, no full stops
                ps = [p.replace(".", "").replace("?", "").lower() for p in ps]
            paras += ps
        return make_words(paras, pause=1.8)

    def test_local_punctuation_fallback(self):
        words = self.episode()
        lp = picker.local_punct(words)
        self.assertTrue(lp[0])
        self.assertFalse(lp[-1])
        late = [t for t in picker.thoughts(words) if t.start > words[-1][2] * 0.75]
        self.assertTrue(late and max(t.dur for t in late) < 30, [round(t.dur) for t in late])

    def test_clips_whole_spread_no_scraps_no_hook_repeat(self):
        words = self.episode()
        clips = picker.pick(words, target_min=5)["clips"]
        hook, body = clips[0], clips[1:]
        self.assertEqual(hook.role, "hook")
        for c in body:
            self.assertGreaterEqual(c.length, picker.MIN_CLIP)
            self.assertFalse(c.start < hook.end and c.end > hook.start, "hook heard twice")
            self.assertNotIn(c.text.split()[-1].lower().strip(",."), picker.END_BAD, c.text[-60:])
        span = words[-1][2]
        self.assertTrue(any(c.start < span / 3 for c in body) and any(c.start > span * 2 / 3 for c in body))

    def test_whisper_pieces_cut_in_quiet(self):
        import numpy as np
        sr = fetch.SR
        audio = np.full(int(2000 * sr), 0.5, dtype=np.float32)
        quiet = int(603 * sr)
        audio[quiet:quiet + int(0.2 * sr)] = 0.0
        bounds = fetch.chunk_bounds(audio)
        self.assertEqual(bounds[0][0], 0)
        self.assertEqual(bounds[-1][1], len(audio))
        self.assertTrue(all(b1 == a2 for (_a1, b1), (a2, _b2) in zip(bounds, bounds[1:])))
        self.assertTrue(quiet <= bounds[0][1] <= quiet + int(0.2 * sr), bounds[0][1] / sr)
        self.assertEqual(fetch.chunk_bounds(np.zeros(int(700 * sr), dtype=np.float32)), [(0, int(700 * sr))])

    def test_trim_lower_start_and_lead_in_end(self):
        words = make_words(["Discipline wins. why you should do that is simple. You keep going every single day of your "
                            "life. Next up, how to sell."])
        lp = picker.local_punct(words)
        ok = lambda k: picker.clean_end(words, k, True, False, lp)   # noqa: E731
        a, b = picker._trim(words, 2, len(words) - 1, ok, lp)
        self.assertEqual(words[a][0], "You")
        self.assertEqual(words[b][0], "life.")
        self.assertEqual(picker.junk_reason("How to sell. How to hire. How to grow your business."), "topic list")

    def test_source_framing_and_outro_are_junk(self):
        self.assertEqual(picker.junk_reason("If you can't stay on this video for five minutes without clicking off"),
                         "source framing")
        self.assertEqual(picker.junk_reason("I'm going to go through it all in the next 45 minutes"), "source framing")
        self.assertTrue(picker.junk_reason("so that's it I'm going to eat chicken now see you"))
        self.assertEqual(picker.junk_reason(GOOD), "")


class ClipCsv(unittest.TestCase):
    def test_times_roundtrip(self):
        for t in (0, 5.25, 75.5, 3725.04):
            self.assertAlmostEqual(clipcsv.parse_time(clipcsv.fmt_time(t)), t, places=2)
        self.assertEqual(clipcsv.parse_time("1:05"), 65)
        self.assertEqual(clipcsv.parse_time("90.5"), 90.5)
        with self.assertRaises(ValueError):
            clipcsv.parse_time("1:xx")

    def test_write_read(self):
        clips = [picker.Clip("hook", 100, 118.5, "A line, with a comma.", 2.5), picker.Clip("body", 10, 70, "Body", 1.0)]
        with tempfile.TemporaryDirectory() as d:
            p = clipcsv.write(clips, Path(d) / "c.csv")
            back = clipcsv.read(p)
        self.assertEqual([(c.role, c.start, c.end, c.text) for c in back], [(c.role, c.start, c.end, c.text) for c in clips])

    def test_bad_role_names_line(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "c.csv"
            p.write_text("role,start,end,text\nintro,0,5,x\n")
            with self.assertRaisesRegex(ValueError, "line 2"):
                clipcsv.read(p)


class Checker(unittest.TestCase):
    def test_errors(self):
        C = picker.Clip
        e, _ = check.check([C("body", 50, 60, ""), C("body", 10, 20, "")])
        self.assertTrue(any("order" in x for x in e))
        e, _ = check.check([C("body", 10, 30, ""), C("body", 25, 40, "")])
        self.assertTrue(any("overlap" in x for x in e))
        e, _ = check.check([C("body", 10, 30, ""), C("hook", 100, 115, "")])
        self.assertTrue(any("first row" in x for x in e))
        e, _ = check.check([C("body", 10, 9, "")])
        self.assertTrue(any("not after" in x for x in e))
        e, _ = check.check([C("body", 10, 200, "")], duration=100)
        self.assertTrue(any("episode is" in x for x in e))

    def test_warns_inside_word_and_ad(self):
        words = [("hello", 1.0, 1.6), ("there", 1.7, 2.2)]
        _, w = check.check([picker.Clip("body", 1.3, 2.25, "use the code SAVE")], words=words)
        self.assertTrue(any("inside the word \"hello\"" in x for x in w))
        self.assertTrue(any("ad read" in x for x in w))


class Captions(unittest.TestCase):
    def test_json3_words(self):
        data = {"events": [{"tStartMs": 1000, "dDurationMs": 2000, "segs": [{"utf8": "hello"}, {"utf8": " big", "tOffsetMs": 400},
                                                                          {"utf8": " world", "tOffsetMs": 900}]},
                           {"tStartMs": 3000, "dDurationMs": 500, "segs": [{"utf8": "[Music]"}]}]}
        w = fetch.caption_words(data)
        self.assertEqual([x[0] for x in w], ["hello", "big", "world"])
        self.assertEqual(w[0][1], 1.0)
        self.assertEqual(w[1][1], 1.4)
        self.assertAlmostEqual(w[0][2], 1.39, places=2)    # 0.12 + 5 letters x 0.065 = 1.445, capped before "big" at 1.4
        self.assertAlmostEqual(w[2][2], 2.345, places=2)   # a pause before the caption event ends at 3.0

    def test_source_id(self):
        self.assertEqual(fetch.source_id("https://www.youtube.com/watch?v=AIBfnG1it0s&t=60s"), "AIBfnG1it0s")
        self.assertEqual(fetch.source_id("https://youtu.be/AIBfnG1it0s"), "AIBfnG1it0s")
        self.assertTrue(fetch.is_url("https://youtu.be/x"))
        self.assertFalse(fetch.is_url("/Users/me/pod.mp3"))


class RunnerPlan(unittest.TestCase):
    def test_plan_from_cached_words_and_users_csv(self):
        words = Picking().episode()
        with tempfile.TemporaryDirectory() as d:
            wd = Path(d)
            media = wd / "pod.mp3"
            media.write_bytes(b"x" * 2000)
            (wd / "words.json").write_text(json.dumps(words))
            with mock.patch.object(fetch, "media_duration", return_value=words[-1][2]):
                res = runner.plan(str(media), target_min=4, workdir=wd, log=lambda m: None)
                self.assertTrue(res["ok"], res["errors"])
                self.assertTrue((wd / "clips.csv").is_file() and (wd / "plan_report.txt").is_file())
                mine = wd / "mine.csv"
                mine.write_text("role,start,end,text\nbody,0:00:01,0:00:30,first\nbody,0:01:00,0:01:40,second\n")
                res2 = runner.plan(str(media), target_min=4, clip_csv=str(mine), workdir=wd, log=lambda m: None)
            self.assertEqual([c.text for c in res2["clips"]], ["first", "second"])
            self.assertTrue(any("target" in w for w in res2["warnings"]))


class Director(unittest.TestCase):
    def film(self, has_video=True, index=None):
        words = Picking().episode()
        res = picker.pick(words, target_min=5)
        idx = index if index is not None else [{"file": f"{t}/{t}_{k}.mp4", "tag": t} for t in director.LIB.MOODS for k in range(3)]
        return res["clips"], words, director.build(res["clips"], words, has_video=has_video, index=idx, channel="Chan")

    def test_timeline_is_contiguous_and_rules_hold(self):
        clips, words, f = self.film()
        shots = f["shots"]
        for a, b in zip(shots, shots[1:]):
            self.assertAlmostEqual(a["out_start"] + a["dur"], b["out_start"], places=2)
        self.assertAlmostEqual(shots[-1]["out_start"] + shots[-1]["dur"], f["length"], places=2)
        self.assertEqual(f["card"]["out_start"], round(clips[0].length, 3))
        self.assertTrue(any(s["kind"] == "card" for s in shots))
        self.assertTrue(0.25 <= f["camera_share"] <= 0.7, f["camera_share"])
        run, kind = 0.0, None
        for s in shots:
            run = run + s["dur"] if s["kind"] == kind else s["dur"]
            kind = s["kind"]
            if kind == "camera":
                self.assertLessEqual(run, director.CAM_MAX + director.WIN_MAX)
            if kind == "broll":
                self.assertLessEqual(run, director.BROLL_MAX + director.WIN_MAX)
        for s in shots:
            self.assertLessEqual(s["dur"], director.WIN_MAX * 2 + 0.01)
        self.assertTrue(f["captions"] and all(c["out_end"] > c["out_start"] for c in f["captions"]))

    def test_no_library_repeat_within_gap(self):
        _, _, f = self.film()
        last = {}
        for s in f["shots"]:
            if s.get("file") and s["kind"] == "broll" and not s.get("row"):
                if s["file"] in last:
                    self.assertGreaterEqual(s["out_start"] - last[s["file"]], director.LIBRARY_GAP / 4 - 0.01)
                last[s["file"]] = s["out_start"]

    def test_audio_only_and_empty_library(self):
        _, _, f = self.film(has_video=False, index=[])
        self.assertFalse(any(s["kind"] == "camera" for s in f["shots"]))
        self.assertTrue(f["rows"])          # an empty library becomes mood searches in the Visuals tab
        self.assertTrue(all(r["asset_type"] == "stock_video" and r["stock"] for r in f["rows"]))

    def test_literal_subject(self):
        self.assertEqual(director.literal_for("we went diving with great white sharks"), "sharks")
        self.assertEqual(director.literal_for("an ice bath every morning"), "ice bath")
        self.assertIsNone(director.literal_for("think about it"))


class Packaging(unittest.TestCase):
    def test_titles_and_speaker(self):
        from podcast_cut import titles
        meta = {"title": "Breakups, Sadness, Focus & Rebuilding Yourself - Dr Andrew Huberman (4K)", "uploader": "Chris"}
        self.assertEqual(titles.speaker_from(meta), "Andrew Huberman")
        clips = [picker.Clip("body", 0, 10, "fear fear fear afraid scared courage mind")]
        t = titles.titles(meta, clips, 35.4 * 60)
        self.assertEqual(t[0], "The Only 35 Minutes You Need To Conquer Your Fear | Andrew Huberman Motivation")

    def test_chapters_start_at_zero_and_are_long(self):
        from podcast_cut import titles
        clips, _, f = Director().film()
        chs = titles.chapters(f, clips)
        self.assertEqual(chs[0]["t"], 0.0)
        for a, b in zip(chs, chs[1:]):
            self.assertGreaterEqual(b["t"] - a["t"], 10)
        self.assertIn("0:00", titles.chapters_text(chs))

    def test_shorts_windows(self):
        sc = picker.shorts(make_words([GOOD, STORY, GOOD, MEH, STORY, GOOD, STORY] * 3, pause=0.5), n=2)
        self.assertTrue(1 <= len(sc) <= 2)
        for c in sc:
            self.assertTrue(20 <= c.length <= 60, c.length)


class Grades(unittest.TestCase):
    def test_grades_are_valid_ffmpeg_filters(self):
        """A wrong option name in the grade made every library grab and every render fail (2026-11-23)."""
        import subprocess
        from podcast_cut import look
        from providers.media_clip.ffmpeg_clip import _ffmpeg
        for g in (look.GRADE, look.GRADE_LIGHT):
            r = subprocess.run([_ffmpeg(), "-v", "error", "-f", "lavfi", "-i", "testsrc=s=320x180:d=0.2", "-vf",
                                look.fit_filter(640, 360) + "," + g, "-f", "null", "-"], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr[-300:])


class TinyRender(unittest.TestCase):
    def test_render_joins_pieces_with_sound(self):
        import subprocess
        from podcast_cut import render as R
        from providers.media_clip.ffmpeg_clip import _ffmpeg, _ffprobe
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            vid, aud = d / "cam.mp4", d / "pod.m4a"
            subprocess.run([_ffmpeg(), "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=s=640x360:r=25:d=20", "-pix_fmt", "yuv420p",
                            str(vid)], check=True)
            subprocess.run([_ffmpeg(), "-v", "error", "-y", "-f", "lavfi", "-i", "sine=f=220:d=20", "-c:a", "aac", str(aud)], check=True)
            words = make_words([GOOD, STORY], pause=1.0)
            clips = [picker.Clip("hook", 2.0, 8.0, "hook"), picker.Clip("body", 1.0, 12.0, "body")]
            f = director.build(clips, words, has_video=True, index=[], channel="Test")
            f["rows"] = []
            for s in f["shots"]:
                s.pop("row", None)
            sections = {(c.start, c.end): (vid, 0.0) for c in clips}
            old = R.PIECE
            R.PIECE = 6.0
            try:
                out = R.render(f, aud, sections, d / "out.mp4", channel="Test", size=(640, 360), preview=True, music=False,
                               lib_dir=d, log=lambda m: None)
            finally:
                R.PIECE = old
            self.assertGreater(out["pieces"], 1)
            dur = float(subprocess.run([_ffprobe(), "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                        str(d / "out.mp4")], capture_output=True, text=True).stdout)
            self.assertAlmostEqual(dur, f["length"], delta=0.3)
            streams = subprocess.run([_ffprobe(), "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0",
                                      str(d / "out.mp4")], capture_output=True, text=True).stdout.split()
            self.assertEqual(sorted(streams), ["audio", "video"])


if __name__ == "__main__":
    unittest.main()
