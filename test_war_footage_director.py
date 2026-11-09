"""War Footage Director: offline tests for search, rules, frames, authenticity, capture and the end-to-end run (no network, no Gemini)."""

import datetime as dt
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import numpy as np

from cinematic_explainer.war import director_authenticity as A
from cinematic_explainer.war import director_capture as C
from cinematic_explainer.war import director_frames as F
from cinematic_explainer.war import director_rules as R
from cinematic_explainer.war import director_search as S
from cinematic_explainer.war import footage_director as FD
from cinematic_explainer.war import narration_read as N

FILM = dt.date(2025, 11, 10)


def cand(title, channel="Reuters", dur=60, up="", vid=None, desc=""):
    c = S.Candidate(video_id=vid or ("v" + str(abs(hash(title)) % 10 ** 8)), title=title, channel=channel, duration=dur, description=desc)
    if up:
        c.details = {"upload_date": up}
    return c


# ------------------------------------------------------------------------------------------------------------------ synthetic pictures
def _smooth(seed, h=180, w=320):
    rng = np.random.RandomState(seed)
    small = rng.randint(50, 200, (6, 8, 3)).astype(np.float32)
    small[..., 0] *= 0.7                                           # no skin tones
    big = np.kron(small, np.ones((h // 6 + 1, w // 8 + 1, 1), np.float32))[:h, :w]
    k = np.ones(15) / 15
    for ax in (0, 1):
        big = np.apply_along_axis(lambda m: np.convolve(m, k, "same"), ax, big)
    return big


def footage(base_seed=1, noise_seed=0, h=180, w=320):
    n = np.random.RandomState(noise_seed + 1000).randint(-18, 18, (h, w, 3))
    return np.clip(_smooth(base_seed, h, w) + n, 0, 255).astype(np.uint8)


def pillarbox():
    im = np.full((180, 320, 3), 40, np.uint8)
    im[:, 110:210] = footage(3)[:, 110:210]
    return im


def text_screen():
    im = np.full((180, 320, 3), 235, np.uint8)
    for y in range(12, 170, 10):
        im[y:y + 3, 20:300] = 25
    return im


def graphic():
    im = np.full((180, 320, 3), (30, 60, 110), np.uint8)
    im[:, 200:] = (200, 40, 40)
    return im


def dark():
    return np.random.RandomState(5).randint(0, 8, (180, 320, 3)).astype(np.uint8)


def tiles_of(imgs, step=2.0):
    return F.inspect([F.Tile(t=i * step, img=im) for i, im in enumerate(imgs)])


def one_shot(n, base=1):
    return [footage(base, i) for i in range(n)]


def jpeg(arr):
    from PIL import Image
    b = io.BytesIO()
    Image.fromarray(arr).save(b, "JPEG", quality=92)
    return b.getvalue()


def sheet(imgs):
    """3x3 storyboard sheet (960x540) from up to 9 tiles; empty cells black."""
    out = np.zeros((540, 960, 3), np.uint8)
    for k, im in enumerate(imgs[:9]):
        r, c = divmod(k, 3)
        out[r * 180:(r + 1) * 180, c * 320:(c + 1) * 320] = im
    return jpeg(out)


# ------------------------------------------------------------------------------------------------------------------ search
class SearchTest(unittest.TestCase):
    def test_entity_first_no_month_words_agency_variants(self):
        r = N.read("Overnight on November 5, drones set the Ryazan refinery on fire.")
        qs = S.build_queries(r)
        self.assertTrue(qs and "Ryazan refinery" in qs[0])
        self.assertFalse(any("november" in q.lower() or " 5" in q for q in qs))
        self.assertTrue(any(q.startswith("Reuters") for q in qs) and any(q.startswith("AP ") for q in qs))
        self.assertLessEqual(len(qs), 5)
        self.assertEqual(len({q.lower() for q in qs}), len(qs))

    def test_csv_prompt_parts_are_added(self):
        r = N.read("Overnight on November 5, drones set the Ryazan refinery on fire.")
        self.assertIn("night strike", [q.lower() for q in S.build_queries(r, "a || night strike video")])      # 'video' is a dropped word

    def test_pool_merges_by_id_and_caches(self):
        calls = []

        def hit(vid, title):
            return SimpleNamespace(video_id=vid, title=title, channel="Reuters", duration=30, description="", channel_is_verified=True,
                                   view_count=5, url="")

        class Backend:
            def search(self, q, max_results=10):
                calls.append(q)
                return [hit("aaa", "A"), hit("bbb", "B")] if q == "q1" else [hit("bbb", "B"), hit("ccc", "C")]

        with tempfile.TemporaryDirectory() as td:
            s = S.Searcher(Path(td), backend=Backend(), pause=0)
            pool = s.pool(["q1", "q2"])
            self.assertEqual(sorted(c.video_id for c in pool), ["aaa", "bbb", "ccc"])
            b = next(c for c in pool if c.video_id == "bbb")
            self.assertEqual(b.queries, ["q1", "q2"])
            self.assertEqual(b.rank, 1)
            n = len(calls)
            s.pool(["q1", "q2"])
            self.assertEqual(len(calls), n)                       # second call: cache only
            s2 = S.Searcher(Path(td), backend=Backend(), pause=0)  # a new Searcher reads the same disk cache
            s2.pool(["q1"])
            self.assertEqual(len(calls), n)

    def test_failed_search_gives_empty_pool_not_error(self):
        class Boom:
            def search(self, q, max_results=10):
                raise RuntimeError("rate limited")

        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(S.Searcher(Path(td), backend=Boom(), pause=0).pool(["x y"]), [])


# ------------------------------------------------------------------------------------------------------------------ rules
class RulesTest(unittest.TestCase):
    def why(self, sentence, c):
        return R.reject(c, N.read(sentence), FILM)

    def assertRule(self, reasons, prefix):
        self.assertTrue(any(x.startswith(prefix) for x in reasons), reasons)

    def test_commentary_channel(self):
        self.assertRule(self.why("Drones set the Ryazan refinery on fire.", cand("Ryazan refinery fire drone", "Perun")), "format: commentary")

    def test_other_country_in_title(self):
        self.assertRule(self.why("Russia is importing gasoline from Belarus by rail.", cand("Lithuania stops Belarus rail transit")), "country: about Lithuania")

    def test_side_reversed(self):
        self.assertRule(self.why("Third, Russia is hitting back from the air.", cand("Ukrainian drones hunt down Russian troops")), "side:")

    def test_repair_vs_explosion(self):
        self.assertRule(self.why("Workers are repairing the Moscow refinery after the strike.", cand("Moscow refinery explosion caught on camera")),
                        "subject: an attack")

    def test_long_aggregator_programme_for_event(self):
        self.assertRule(self.why("Drones set the Ryazan refinery on fire.", cand("Ryazan refinery fire", "Some Re-upload Channel", 900)), "format:")

    def test_entity_missing(self):
        self.assertRule(self.why("Drones set the Ryazan refinery on fire.", cand("Kirishi refinery fire drone")), "entity:")

    def test_uploaded_before_event(self):
        self.assertRule(self.why("Overnight on November 5, drones hit the Moscow refinery.", cand("Moscow refinery fire", up="20251101")), "time:")

    def test_accepts_reuters_moscow_refinery(self):
        c = cand("Moscow refinery on fire after Ukrainian drone attack", "Reuters", 31, "20251106")
        self.assertEqual(self.why("Overnight on November 5, drones hit the Moscow refinery.", c), [])
        ok, bad = R.rank([c, cand("Moscow refinery fire", "Perun")], N.read("Overnight on November 5, drones hit the Moscow refinery."), FILM)
        self.assertEqual([x.video_id for _, x in ok], [c.video_id])
        self.assertEqual(len(bad), 1)

    def test_channel_tiers(self):
        self.assertEqual(R.channel_tier("Reuters"), "agency")
        self.assertEqual(R.channel_tier("Perun"), "commentary")
        self.assertEqual(R.channel_tier("Frontline Mapper"), "commentary")      # name hint
        self.assertEqual(R.channel_tier("Zxq Local"), "unknown")


class UsedTest(unittest.TestCase):
    def test_same_video_overlap_and_third_moment(self):
        u = R.Used()
        u.add("003", "vid", 10, 18)
        self.assertIn("same seconds", u.conflict("vid", 12, 20))
        self.assertEqual(u.conflict("vid", 30, 38), "")
        u.add("004", "vid", 30, 38)
        self.assertIn("moments of this video", u.conflict("vid", 60, 68))
        self.assertEqual(u.conflict("other", 12, 20), "")

    def test_same_picture_under_another_id(self):
        tiles = tiles_of(one_shot(4, base=7))
        hs = [t.hash for t in tiles]
        u = R.Used()
        u.add("003", "orig", 4, 12, hs)
        self.assertIn("same picture", u.conflict("reupload", 40, 48, hs))
        other = [t.hash for t in tiles_of(one_shot(4, base=99))]
        self.assertEqual(u.conflict("reupload", 40, 48, other), "")


# ------------------------------------------------------------------------------------------------------------------ frames
class FramesTest(unittest.TestCase):
    def kind(self, img, prev=None):
        return F.classify(img, prev)[0]

    def test_tile_kinds(self):
        self.assertEqual(self.kind(footage(1, 0), footage(1, 1)), "footage")
        self.assertEqual(self.kind(pillarbox()), "pillarbox")
        self.assertEqual(self.kind(text_screen()), "text_screen")
        self.assertEqual(self.kind(graphic()), "graphic")
        self.assertEqual(self.kind(dark()), "dark")

    def test_choose_window_cut_free_3_to_8_s(self):
        tiles = tiles_of(one_shot(20))
        w = F.choose_window(tiles, 40)
        self.assertIsNotNone(w)
        self.assertGreaterEqual(w["end"] - w["start"], F.MIN_S)
        self.assertLessEqual(w["end"] - w["start"], F.CLIP_S)
        self.assertGreaterEqual(w["start"], 40 * F.EDGE_SKIP)
        self.assertLessEqual(w["end"], 40 * (1 - F.EDGE_SKIP))

    def test_window_never_spans_a_cut(self):
        imgs = one_shot(6, 1) + [255 - im for im in one_shot(2, 50)] + one_shot(6, 2)          # a 2-tile (4 s) shot between two long ones
        tiles = tiles_of(imgs)
        cuts = [t.t for t in tiles if t.cut_before]
        self.assertTrue(cuts)
        w = F.choose_window(tiles, 28)
        self.assertFalse(any(w["start"] < c < w["end"] - 1.9 for c in cuts), (w, cuts))

    def test_none_when_only_bad_tiles(self):
        bad = [pillarbox(), text_screen(), graphic(), dark()] * 4
        self.assertIsNone(F.choose_window(tiles_of(bad), 32))
        self.assertIsNone(F.choose_window([], 30))

    def test_usable_veto(self):
        tiles = tiles_of(one_shot(20))
        self.assertIsNone(F.choose_window(tiles, 40, usable=lambda a, b, h: False))
        w = F.choose_window(tiles, 40, usable=lambda a, b, h: a >= 20)
        self.assertGreaterEqual(w["start"], 20)

    def test_skips_edges(self):
        tiles = tiles_of(one_shot(2))                                     # tiles at 0 s and 2 s of a 40 s video: the first 5 % (2 s) is skipped
        self.assertIsNone(F.choose_window(tiles, 40))
        tiles = tiles_of([pillarbox()] * 2 + one_shot(8))
        w = F.choose_window(tiles, 20)
        self.assertGreaterEqual(w["start"], 4.0)


# ------------------------------------------------------------------------------------------------------------------ authenticity
class AuthenticityTest(unittest.TestCase):
    R_EVENT = N.read("Overnight on November 5, drones hit the Moscow refinery.")

    def test_verified_event(self):
        c = cand("Moscow refinery on fire after drone attack", "Reuters", 31, "20251107")
        cls, why = A.classify(c, self.R_EVENT, FILM)
        self.assertEqual(cls, "verified_event", why)
        self.assertTrue(A.allowed(cls, self.R_EVENT))

    def test_commentary_unverified(self):
        cls, why = A.classify(cand("Moscow refinery on fire drone attack", "Perun", 31, "20251107"), self.R_EVENT, FILM)
        self.assertEqual(cls, "unverified")
        self.assertFalse(A.allowed(cls, self.R_EVENT))

    def test_upload_before_event_unverified(self):
        cls, why = A.classify(cand("Moscow refinery on fire", "Reuters", 31, "20251101"), self.R_EVENT, FILM)
        self.assertEqual(cls, "unverified")
        self.assertTrue(any("before the event" in w for w in why))

    def test_red_flag_wording(self):
        cls, _ = A.classify(cand("Moscow refinery fire AI generated", "Reuters", 31, "20251107"), self.R_EVENT, FILM)
        self.assertEqual(cls, "unverified")

    def test_corroborated_by_another_channel(self):
        hs = [t.hash for t in tiles_of(one_shot(4, 9))]
        c = cand("Refinery burning at night", "Zxq Local", 40, "20251108", vid="mine")
        cls, why = A.classify(c, self.R_EVENT, FILM, hs, [("theirs", "Other Channel", hs)])
        self.assertEqual(cls, "corroborated", why)
        cls2, _ = A.classify(c, self.R_EVENT, FILM, hs, [("theirs", "Zxq Local", hs)])           # same channel is not independent
        self.assertEqual(cls2, "unverified")

    def test_allowed_strict_for_event_and_movement_only(self):
        ev, mv, subj = (SimpleNamespace(types=[t]) for t in ("EVENT", "MOVEMENT", "SUBJECT"))
        for r in (ev, mv):
            self.assertFalse(A.allowed("unverified", r))
            self.assertTrue(A.allowed("corroborated", r))
        self.assertTrue(A.allowed("unverified", subj))
        self.assertEqual(A.label("unverified"), "ILLUSTRATIVE FOOTAGE")
        self.assertEqual(A.label("verified_event"), "")


# ------------------------------------------------------------------------------------------------------------------ capture
class CaptureTest(unittest.TestCase):
    def test_verify_matching_and_not_matching(self):
        tiles = tiles_of(one_shot(20))
        good = [t.img for t in tiles if 10 <= t.t <= 18]
        v = C.verify(good, tiles, 10, 8)
        self.assertTrue(v["ok"], v)
        self.assertTrue(v["checked_against_storyboard"])
        other = [footage(77, i) for i in range(5)]
        v2 = C.verify(other, tiles, 10, 8)
        self.assertFalse(v2["ok"])
        self.assertTrue(any(r.startswith("moment:") for r in v2["reasons"]))
        self.assertFalse(C.verify([], tiles, 10, 8)["ok"])

    def test_verify_rejects_bad_pictures(self):
        tiles = tiles_of(one_shot(20))
        v = C.verify([text_screen()] * 5, tiles, 10, 8)
        self.assertFalse(v["ok"])
        self.assertTrue(any(r.startswith("picture:") for r in v["reasons"]))

    def _acquire_ok(self, video_id, start, seconds, dest):
        Path(dest).write_bytes(b"fake mp4")
        return {"ok": True, "width": 1920, "height": 1080}

    def test_capture_ok_writes_dest(self):
        tiles = tiles_of(one_shot(20))
        with tempfile.TemporaryDirectory() as td, mock.patch.object(C, "frames_of", return_value=[t.img for t in tiles if 10 <= t.t <= 18 for _ in (0, 1)]):   # 2 frames a second over 5 s
            dest = Path(td) / "sub" / "003.mp4"
            got = C.capture("vid", 10, 8, dest, tiles, acquire=self._acquire_ok, validate=lambda p, d: None)
            self.assertTrue(got["ok"], got)
            self.assertTrue(dest.is_file())
            self.assertFalse(list(Path(td).rglob("*.director.mp4")))

    def test_capture_failures_leave_no_file(self):
        tiles = tiles_of(one_shot(20))
        with tempfile.TemporaryDirectory() as td:
            d = Path(td) / "003.mp4"
            # acquire fails
            got = C.capture("vid", 10, 8, d, tiles, acquire=lambda *a: {"ok": False, "error": "blocked"}, validate=lambda p, dd: None)
            self.assertFalse(got["ok"])
            # acquire raises
            def boom(*a):
                raise RuntimeError("browser died")
            self.assertFalse(C.capture("vid", 10, 8, d, tiles, acquire=boom, validate=lambda p, dd: None)["ok"])
            # file validation fails
            got = C.capture("vid", 10, 8, d, tiles, acquire=self._acquire_ok, validate=lambda p, dd: "not a video")
            self.assertFalse(got["ok"])
            self.assertIn("file:", got["reasons"][0])
            # wrong moment
            with mock.patch.object(C, "frames_of", return_value=[footage(77, i) for i in range(5)]):
                got = C.capture("vid", 10, 8, d, tiles, acquire=self._acquire_ok, validate=lambda p, dd: None)
            self.assertFalse(got["ok"])
            self.assertEqual(list(Path(td).iterdir()), [])


# ------------------------------------------------------------------------------------------------------------------ end to end
class FakeBackend:
    def __init__(self, results):
        self.results = results
        self.calls = []

    def search(self, q, max_results=10):
        self.calls.append(q)
        return self.results


def make_info(n_tiles=20):
    sheets = [one_shot(n_tiles, base=4)[i:i + 9] for i in range(0, n_tiles, 9)]
    blobs = {f"https://sb/{i}.jpg": sheet(s) for i, s in enumerate(sheets)}

    def info(video_id):
        return {"upload_date": "20251106", "description": "Ryazan refinery burns", "tags": ["ryazan"], "duration": n_tiles * 2, "channel": "Reuters",
                "formats": [{"format_id": "sb0", "width": 320, "height": 180, "rows": 3, "columns": 3, "fps": 0.5,
                             "fragments": [{"url": u, "duration": 18} for u in blobs]}]}
    return info, (lambda url: blobs[url])


class DirectorRunTest(unittest.TestCase):
    SCENES = [
        {"scene_no": 1, "text": "Ukraine says its drones have disabled 51 percent of Russia's oil refining capacity.", "graphic": ""},
        {"scene_no": 2, "text": "Overnight on November 5, drones set the Ryazan refinery on fire.", "graphic": "date"},
        {"scene_no": 3, "text": "Overnight on November 5, drones set the Ryazan refinery on fire again.", "graphic": ""},
    ]

    def rows(self):
        return [SimpleNamespace(scene_number=str(s["scene_no"]), script_segment=s["text"], asset_type="youtube_video",
                                prompt="Ryazan refinery fire drone attack footage") for s in self.SCENES]

    def run_director(self, td, results, **kw):
        from asset_manager import AssetManifest
        images, state = Path(td) / "images", Path(td) / "state"
        images.mkdir()
        pre = kw.pop("pre", None)
        if pre:
            AssetManifest(images).set("3", pre(images))
        info, fetch = make_info()
        be = FakeBackend(results)
        s = S.Searcher(state / "director_cache", backend=be, info=info, pause=0)
        tiles = tiles_of(one_shot(20, base=4))
        frames = [t.img for t in tiles if 4 <= t.t <= 14]
        acquired = []

        def acquire(vid, start, secs, dest):
            acquired.append((vid, start, secs))
            Path(dest).write_bytes(b"x")
            return {"ok": True, "width": 1920, "height": 1080}

        with mock.patch.object(C, "frames_of", return_value=frames):
            rep = FD.run(self.SCENES, self.rows(), images, state, film_date=FILM, searcher=s, acquire=acquire, validate=lambda p, d: None,
                         fetch_sheet=fetch, render_id="t", **kw)
        return rep, images, state, be, acquired

    def good_results(self):
        return [SimpleNamespace(video_id="ryz00000001", title="Ryazan refinery on fire after Ukrainian drone attack", channel="Reuters",
                                duration=40, description="", channel_is_verified=True, view_count=9, url="")]

    def test_claim_to_graphics_event_to_footage(self):
        from asset_manager import AssetManifest
        with tempfile.TemporaryDirectory() as td:
            rep, images, state, be, acquired = self.run_director(td, self.good_results())
            by = {s["scene"]: s for s in rep["scenes"]}
            self.assertEqual(by["001"]["decision"], "graphics")
            self.assertTrue(by["001"]["graphic_intent"])
            self.assertEqual(by["002"]["decision"], "footage", by["002"])
            man = AssetManifest(images)
            rec = man.get("2")
            self.assertEqual(rec["selection_method"], "war_director")
            self.assertEqual(rec["channel"], "Reuters")
            self.assertEqual(rec["upload_date"], "20251106")
            self.assertEqual(rec["authenticity"], "verified_event")
            self.assertIn("clip_start", rec)
            self.assertIn("youtube.com/watch?v=ryz00000001", rec["source_url"])
            self.assertTrue(Path(rec["local_path"]).is_file())
            # the only other candidate is the same one-shot video: another moment of it shows the same picture (render 041, scenes 001/011),
            # so scene 003 goes to graphics instead of repeating the shot
            self.assertEqual(by["003"]["decision"], "graphics")
            self.assertEqual(len(acquired), 1)
            self.assertTrue((state / FD.REPORT).is_file() and (state / FD.DECISIONS).is_file())
            dec = FD.load_decisions(state)
            self.assertEqual(dec["1"]["decision"], "graphics")
            self.assertEqual(dec["2"]["decision"], "footage")

    def test_user_pick_untouched(self):
        from asset_manager import AssetManifest

        def pre(images):
            p = images / "003.mp4"
            p.write_bytes(b"user clip")
            return {"status": "complete", "type": "video", "local_path": str(p), "video_id": "usr", "user_override": True, "clip_start": 5,
                    "timestamp_end": 13, "source": "manual"}

        with tempfile.TemporaryDirectory() as td:
            rep, images, state, be, acquired = self.run_director(td, self.good_results(), pre=pre)
            by = {s["scene"]: s for s in rep["scenes"]}
            self.assertEqual(by["003"]["decision"], "footage")
            self.assertIn("user", by["003"]["note"])
            rec = AssetManifest(images).get("3")
            self.assertEqual(rec["video_id"], "usr")
            self.assertTrue(rec["user_override"])
            self.assertEqual((images / "003.mp4").read_bytes(), b"user clip")

    def test_nothing_found_means_graphics(self):
        with tempfile.TemporaryDirectory() as td:
            rep, images, state, be, acquired = self.run_director(td, [])
            self.assertEqual({s["decision"] for s in rep["scenes"]}, {"graphics"})
            self.assertEqual(acquired, [])
            self.assertEqual(FD.load_decisions(state)["2"]["decision"], "graphics")

    def test_unverified_footage_not_used_for_event(self):
        res = [SimpleNamespace(video_id="zzz00000002", title="Ryazan refinery on fire drone attack", channel="Zxq Local", duration=40,
                               description="", channel_is_verified=False, view_count=1, url="")]
        with tempfile.TemporaryDirectory() as td:
            rep, *_rest, acquired = self.run_director(td, res)
            self.assertEqual(acquired, [])
            s2 = next(s for s in rep["scenes"] if s["scene"] == "002")
            self.assertEqual(s2["decision"], "graphics")
            self.assertTrue(any("authenticity" in " ".join(c.get("why", [])) for c in s2["candidates"]))

    def test_apply_decisions(self):
        scenes = [{"scene_no": 1, "graphic": ""}, {"scene_no": 2, "graphic": "date"}, {"scene_no": 3, "graphic": "",
                  "footage_meta": {"user_supplied": True}, "footage": "u.mp4"}, {"scene_no": 4, "graphic": "", "footage": "a.mp4",
                  "footage_meta": {}}]
        dec = {"1": {"decision": "graphics", "graphic": "number"}, "2": {"decision": "graphics", "graphic": "map"},
               "3": {"decision": "graphics", "graphic": "map"}, "4": {"decision": "footage", "label": "ILLUSTRATIVE FOOTAGE"}}
        out = FD.apply_decisions(scenes, dec)
        self.assertTrue(out[0]["no_footage"])
        self.assertEqual(out[0]["graphic"], "number")
        self.assertTrue(out[1]["no_footage"])
        self.assertEqual(out[1]["graphic"], "date")                         # the CSV graphic wins
        self.assertNotIn("no_footage", out[2])                              # the user's own footage is never dropped
        self.assertEqual(out[3]["footage_meta"]["label"], "ILLUSTRATIVE FOOTAGE")
        self.assertNotIn("no_footage", scenes[0])                           # input not mutated

    def test_graphic_for(self):
        self.assertEqual(FD.graphic_for(N.read("So is Russia really running out of fuel?")), "kinetic")
        self.assertEqual(FD.graphic_for(N.read("Subscribe and tell me what you think in the comments.")), "title")


if __name__ == "__main__":
    unittest.main()


class HistoricalAndBlockedTest(unittest.TestCase):
    """Render 040 regressions: story-period dates, contextual footage, age-restricted candidates."""

    def _reading(self, scenes, no):
        from cinematic_explainer.war import narration_read as NR
        return NR.read_scenes(scenes)[no]

    def _cand(self, **kw):
        from cinematic_explainer.war.director_search import Candidate
        d = kw.pop("details", {})
        c = Candidate(**kw)
        c.details = d
        return c

    def test_earlier_footage_of_the_same_battle_is_contextual_not_rejected(self):
        import datetime as dt
        from cinematic_explainer.war import director_rules as R, narration_read as NR
        sc = [{"scene_no": 1, "text": "In August 2022, Russian forces began attacking Bakhmut."},
              {"scene_no": 2, "text": "On December 20, 2022, President Zelensky visited troops in Bakhmut."}]
        rs = NR.read_scenes(sc)
        story = R.story_period(list(rs.values()))
        c = self._cand(video_id="a", title="Ukrainian soldiers defend eastern city of Bakhmut", channel="AP Archive", duration=90,
                       details={"upload_date": "20221102", "ok": True})
        self.assertEqual(R.reject(c, rs["2"], dt.date(2026, 11, 9), story), [])
        self.assertEqual(R.match_level(c, rs["2"]), "contextual")
        old = self._cand(video_id="b", title="Bakhmut city 2019 tour", channel="AP Archive", duration=90,
                         details={"upload_date": "20190101", "ok": True})
        self.assertTrue(any(w.startswith("time:") for w in R.reject(old, rs["2"], dt.date(2026, 11, 9), story)))

    def test_relative_date_never_rejects(self):
        import datetime as dt
        from cinematic_explainer.war import director_rules as R, narration_read as NR
        rs = NR.read_scenes([{"scene_no": 1, "text": "In May 2023, Prigozhin said his fighters had taken Bakhmut."},
                             {"scene_no": 2, "text": "A month later, Wagner marched on Moscow."}])
        c = self._cand(video_id="m", title="Wagner mutiny: fighters march on Moscow", channel="Reuters", duration=60,
                       details={"upload_date": "20230624", "ok": True})
        self.assertFalse([w for w in R.reject(c, rs["2"], dt.date(2026, 11, 9), R.story_period(list(rs.values()))) if w.startswith("time:")])

    def test_news_brief_keeps_the_years_away_rule(self):
        import datetime as dt
        from cinematic_explainer.war import director_rules as R, narration_read as NR
        r = NR.read("Overnight, drones set the Ryazan refinery on fire.")
        c = self._cand(video_id="o", title="Ryazan refinery fire", channel="Reuters", duration=40, details={"upload_date": "20190101", "ok": True})
        self.assertTrue(any(w.startswith("time:") for w in R.reject(c, r, dt.date(2026, 11, 9), None)))

    def test_age_restricted_candidate_is_unverified_not_irrelevant(self):
        import datetime as dt
        from cinematic_explainer.war import director_authenticity as A, director_rules as R, narration_read as NR
        r = NR.read("In May 2023, Prigozhin said his fighters had taken Bakhmut.")
        c = self._cand(video_id="g", title="WARNING: GRAPHIC CONTENT - Wagner chief Prigozhin says Bakhmut taken", channel="Reuters", duration=70,
                       details={"ok": False, "sign_in": True, "error": "Sign in to confirm your age"})
        self.assertTrue(c.blocked)
        self.assertIn("graphic content", c.content_warning)
        self.assertEqual(R.reject(c, r, dt.date(2026, 11, 9)), [])
        cls, why = A.classify(c, r, dt.date(2026, 11, 9))
        self.assertEqual(cls, "unverified")
        self.assertIn("sign-in", why[0])
        self.assertTrue(A.allowed(cls, r, R.match_level(c, r), R.channel_tier(c.channel), c.blocked))
        self.assertFalse(A.allowed(cls, r, "exact", "aggregator", True))      # a re-upload channel is not enough

    def test_thumbnail_window_and_trim(self):
        import numpy as np
        from cinematic_explainer.war import director_capture as C, director_frames as F
        rng = np.random.default_rng(1)
        tex = lambda s: np.kron(np.random.default_rng(s).integers(0, 255, (9, 16, 3), dtype=np.uint8), np.ones((10, 10, 1), np.uint8))
        tiles = F.inspect([F.Tile(t=t, img=tex(i)) for i, t in enumerate((25.0, 50.0, 75.0))])
        w = F.window_from_thumbnails(tiles, 100.0)
        self.assertEqual((w["start"], w["end"], w["inspection"]), (21.0, 29.0, "thumbnails"))
        frames = [tex(1)] * 3 + [tex(2)] * 10 + [tex(3)] * 3        # a cut after 1.5 s and before the last 1.5 s
        self.assertEqual(C.longest_uncut(frames), (1.5, 6.5))


class HistoricalTimelinessTest(unittest.TestCase):
    def test_carried_date_in_a_historical_story_is_timely_by_the_story(self):
        import datetime as dt
        from cinematic_explainer.war import director_authenticity as A, director_rules as R, narration_read as NR
        from cinematic_explainer.war.director_search import Candidate
        rs = NR.read_scenes([{"scene_no": 1, "text": "In May 2023, Prigozhin said his fighters had taken Bakhmut."},
                             {"scene_no": 2, "text": "A month later, Wagner marched on Moscow."}])
        c = Candidate(video_id="w", title="Wagner fighters march on Moscow", channel="Reuters", duration=60)
        c.details = {"upload_date": "20230624", "ok": True}
        cls, why = A.classify(c, rs["2"], dt.date(2026, 11, 9), story=R.story_period(list(rs.values())), level=R.match_level(c, rs["2"]))
        self.assertEqual(cls, "verified_event", why)


class SplitScreenTest(unittest.TestCase):
    def test_still_presenter_box_beside_changing_pictures_is_studio(self):
        import numpy as np
        from cinematic_explainer.war import director_frames as F
        rng = np.random.default_rng(3)
        box = rng.integers(0, 255, (68, 40, 3), dtype=np.uint8)          # the presenter box: the same in both frames
        a = rng.integers(0, 255, (90, 160, 3), dtype=np.uint8)
        b = rng.integers(0, 255, (90, 160, 3), dtype=np.uint8)
        a[:68, 120:] = box
        b[:68, 120:] = box
        tiles = F.inspect([F.Tile(t=0.0, img=a), F.Tile(t=2.0, img=b)])
        self.assertEqual(tiles[1].kind, "studio")
        self.assertIn("inset_presenter", tiles[1].flags)
        c = rng.integers(0, 255, (90, 160, 3), dtype=np.uint8)
        self.assertEqual(F.inspect([F.Tile(t=0.0, img=a), F.Tile(t=2.0, img=c)])[1].kind, "footage")


class Render041RegressionTest(unittest.TestCase):
    """Bakhmut v2 (render 041): the CNN studio programme, the Moscow mall, hanging captures, quick cuts inside a capture."""

    def test_city_blamed_is_not_the_footage_location(self):
        import datetime as dt
        from cinematic_explainer.war import director_rules as R, narration_read as NR
        from cinematic_explainer.war.director_search import Candidate
        rs = NR.read_scenes([{"scene_no": 1, "text": "In May 2023, Prigozhin said his fighters had taken Bakhmut."},
                             {"scene_no": 2, "text": "Third, the cost. In May 2023, Prigozhin stood among the bodies of his men and blamed Moscow for a shortage of ammunition."}])
        r = rs["2"]
        self.assertNotIn("Moscow", [p.name for p in r.places])
        self.assertNotIn("Moscow", r.key_terms)
        mall = Candidate(video_id="9WUApAN6RDQ", title="New Moscow mall opens minus western brands", channel="Reuters", duration=60)
        mall.details = {"upload_date": "20230520", "ok": True}
        self.assertTrue(any(w.startswith("entity:") for w in R.reject(mall, r, dt.date(2026, 11, 9), R.story_period(list(rs.values())))))
        ok = Candidate(video_id="p", title="Prigozhin video: Wagner chief stands among bodies, demands ammunition", channel="Reuters", duration=60)
        ok.details = {"upload_date": "20230505", "ok": True}
        self.assertEqual(R.reject(ok, r, dt.date(2026, 11, 9), R.story_period(list(rs.values()))), [])

    def test_physical_city_stays_a_location(self):
        from cinematic_explainer.war import narration_read as NR
        self.assertIn("Moscow", [p.name for p in NR.read("Drones hit an oil depot in Moscow.").places])
        self.assertIn("Moscow", NR.read("A month later, Wagner marched on Moscow.").key_terms)
        self.assertEqual(NR.place_roles("Moscow said the strike was a provocation.", "Moscow"), ["actor"])

    def test_cnn_anchor_programme_is_rejected_and_blocklisted(self):
        import datetime as dt
        from cinematic_explainer.war import director_rules as R, footage_director as FD, narration_read as NR
        from cinematic_explainer.war.director_search import Candidate
        r = NR.read("First, Wagner recruited prisoners from Russian jails, promising them freedom after six months at the front.")
        c = Candidate(video_id="AdQ9vTiF3bA", title="See what Wagner Group's Prigozhin purportedly said days before his death", channel="CNN",
                      duration=310)
        self.assertTrue(any(w.startswith("format:") for w in R.reject(c, r, dt.date(2026, 11, 9))))
        self.assertTrue(FD.blocked_for(FD.load_blocklist(), "AdQ9vTiF3bA", r.text))
        self.assertTrue(FD.blocked_for(FD.load_blocklist(), "9WUApAN6RDQ", "Prigozhin ... blamed Moscow for a shortage"))
        self.assertFalse(FD.blocked_for(FD.load_blocklist(), "9WUApAN6RDQ", "Moscow malls reopened"))

    def test_lasting_capture_failure_is_remembered_for_that_window_only(self):
        import tempfile
        from pathlib import Path
        from cinematic_explainer.war import footage_director as FD
        with tempfile.TemporaryDirectory() as d:
            FD._remember_failure(Path(d), "v1", 30.0, ["picture: studio 7 of 13 frames"])
            FD._remember_failure(Path(d), "v2", 10.0, ["capture: timed out after 69 s (War limit)"])     # transient: not remembered
            bl = FD.load_blocklist(Path(d))
            win = [e for e in bl if e.get("scope") == "window"]
            self.assertEqual([e["video_id"] for e in win], ["v1"])
            self.assertTrue(FD.blocked_for(win, "v1", "x", 31.0))
            self.assertFalse(FD.blocked_for(win, "v1", "x", 60.0))

    def test_hanging_capture_is_given_up(self):
        import time
        from cinematic_explainer.war import footage_director as FD
        slow = FD.bounded(lambda *a: (time.sleep(2), {"ok": True})[1], lambda s: 0.3)
        t = time.time()
        res = slow("id", 0.0, 8.0, "x.mp4")
        self.assertLess(time.time() - t, 1.5)
        self.assertEqual(res["kind"], "timeout")

    def test_quick_cut_inside_a_storyboard_checked_capture_is_trimmed_or_dropped(self):
        import numpy as np
        from cinematic_explainer.war import director_capture as C
        tex = lambda s: np.kron(np.random.default_rng(s).integers(0, 255, (9, 16, 3), dtype=np.uint8), np.ones((10, 10, 1), np.uint8))
        self.assertEqual(C.longest_uncut([tex(1)] * 12 + [tex(2)] * 1 + [tex(3)] * 3), (0.0, 6.0))   # 0.5 s fragment cut away
        a, b = C.longest_uncut([tex(1)] * 4 + [tex(2)] * 4 + [tex(3)] * 4 + [tex(4)] * 4)
        self.assertLess(b - a, 3.0)                                                                  # no 3 s stretch: dropped


class SamePictureSameVideoTest(unittest.TestCase):
    def test_another_moment_with_the_same_picture_is_a_repeat(self):
        from cinematic_explainer.war.director_rules import Used
        u = Used()
        h = ["0f0f0f0f0f0f0f0f", "00ff00ff00ff00ff", "123456789abcdef0"]
        u.add("001", "Y5Vq0_8kjJA", 44.3, 52.3, h)
        self.assertIn("another moment", u.conflict("Y5Vq0_8kjJA", 35.4, 43.4, h))        # render 041: scenes 001 and 011
        self.assertEqual(u.conflict("Y5Vq0_8kjJA", 100.0, 108.0, ["aaaaaaaaaaaaaaaa", "5555555555555555"]), "")


class BlockedWithoutWarningTitleTest(unittest.TestCase):
    def test_age_restricted_without_warning_words_does_not_crash(self):
        from cinematic_explainer.war.director_search import Candidate
        c = Candidate(video_id="x", title="Prigozhin among the bodies of his fighters", channel="Reuters")
        c.details = {"ok": False, "sign_in": True}
        self.assertEqual(c.content_warning, "age-restricted on YouTube")
