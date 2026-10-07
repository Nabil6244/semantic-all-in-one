"""StarMap phase 5, the Python side of the app integration: NASA's image library as a source (search, ranking, the manifest
record the shared reuse rule keeps), the Visual Plan rows, stills for photo cards from clips, the sound cues, and a whole
generate_starmap_video run with a fake renderer (real sound mix and export). No network."""

import json
import shutil
import subprocess
import tempfile
import unittest
import wave
import struct
from pathlib import Path

from pakmap.words import estimate_words
from starmap import nasa_images
from starmap.app_integration import generate_starmap_video, load_plan, visual_dicts, visual_dicts_from_csv
from starmap.media import Fetched, fetch_media, media_rows
from starmap.sound import sound_hints

HERE = Path(__file__).resolve().parent
S = HERE / "starmap" / "samples"
SAMPLE = (S / "apollo11_beats.csv").read_text(encoding="utf-8")
SCRIPT = (S / "apollo11_script.txt").read_text(encoding="utf-8")
WORDS = estimate_words(SCRIPT, words_per_second=2.5)
HAS_FFMPEG = shutil.which("ffmpeg") is not None


class FakeResponse:
    def __init__(self, data=None, content=b"", status=200):
        self._data, self.content, self.status_code = data, content, status

    def json(self):
        return self._data

    def raise_for_status(self):
        pass


def fake_nasa(items, files):
    """A requests.get stand-in for the NASA API: `items` per query (title, nasa_id), `files` per nasa_id (bytes)."""
    calls = []

    def get(url, params=None, **_kw):
        calls.append((url, dict(params or {})))
        if url == nasa_images.SEARCH_URL:
            hits = items.get(params["q"], [])
            return FakeResponse({"collection": {"items": [{"data": [{"nasa_id": i, "title": t, "description": "", "center": "JSC"}]} for t, i in hits]}})
        if "/asset/" in url:
            nid = url.rsplit("/", 1)[1]
            return FakeResponse({"collection": {"items": [{"href": f"http://images-assets.nasa.gov/image/{nid}/{nid}~large.jpg"}]}})
        nid = url.split("/image/")[1].split("/")[0]
        return FakeResponse(content=files[nid])

    get.calls = calls
    return get


def jpeg(width=1200, height=800) -> bytes:
    from io import BytesIO

    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", (width, height), (40, 40, 60)).save(buf, "JPEG")
    return buf.getvalue()


class Nasa(unittest.TestCase):
    def test_long_descriptions_fall_back_to_key_words(self):
        q = nasa_images.queries("the lunar module above the Moon with the Earth on the horizon")
        self.assertEqual(q[0], "the lunar module above the Moon with the Earth on the horizon")
        self.assertEqual(q[1:3], ["lunar module moon earth horizon", "lunar module moon earth"])

    def test_ranking_prefers_the_words_and_the_storys_mission(self):
        get = fake_nasa({"astronaut flag moon": [("Apollo 12 astronaut beside the flag on the moon", "as12"), ("Apollo 11 astronaut beside the flag on the moon", "as11"),
                                                 ("A rocket", "r1")]}, {})
        got = nasa_images.search("astronaut flag moon", get=get, context="Apollo 11")
        self.assertEqual([g.nasa_id for g in got], ["as11", "as12", "r1"])
        self.assertEqual(got[0].credit, "NASA/JSC (as11)")

    def test_prefetch_saves_a_record_the_shared_reuse_rule_keeps(self):
        from asset_manager import AssetManifest, asset_record_matches
        from providers.base import AssetSource, SceneRow

        d = Path(tempfile.mkdtemp())
        rows = [SceneRow.from_csv_row(r) for r in visual_dicts_from_csv(SAMPLE)]
        get = fake_nasa({"Apollo 11 Saturn V lifting off from Launch Complex 39A": [("Apollo 11 Saturn V lifting off from Launch Complex 39A", "kscid")]}, {"kscid": jpeg()})
        nasa_rows = {m.scene_number: m.prompt for m in media_rows(load_plan(SAMPLE, WORDS)) if m.source == "nasa_image"}
        rows[1].stock = "a moon base"                          # the user changed scene 2's text in the table: not ours any more
        found = nasa_images.prefetch(rows, nasa_rows, d, get=get, log=lambda m: None)
        self.assertEqual(list(found), ["1"], "scene 3's search finds nothing and goes to stock; scene 2 is the user's now")
        rec = AssetManifest(d).get("1")
        self.assertEqual((rec["status"], rec["source"], rec["provider_asset_id"]), ("complete", "nasa_image", "kscid"))
        self.assertTrue(Path(rec["local_path"]).is_file())
        self.assertTrue(asset_record_matches(rec, rows[0], AssetSource.STOCK_IMAGE), "the shared resolver reuses it (no stock search)")
        # a second run does not search again
        get.calls.clear()
        nasa_images.prefetch(rows, nasa_rows, d, get=get, log=lambda m: None)
        self.assertFalse(any(c[1].get("q", "").startswith("Saturn") for c in get.calls))

    def test_a_dropped_connection_is_tried_again_not_sent_to_stock(self):
        """NASA's server resets connections under load; one reset used to send the row to the stock search."""
        import requests

        from starmap import nasa_images

        calls = []

        def flaky(url, **kw):
            calls.append(url)
            if len(calls) == 1:
                raise requests.exceptions.ConnectionError("Connection reset by peer")
            if len(calls) == 2:
                return FakeResponse(status=503)
            return FakeResponse(status=200)

        old = nasa_images.RETRY_WAITS
        nasa_images.RETRY_WAITS = (0, 0, 0)
        try:
            self.assertEqual(nasa_images.patient(flaky)("u").status_code, 200)
            self.assertEqual(len(calls), 3)
            calls.clear()

            def always_reset(url, **kw):
                calls.append(url)
                raise requests.exceptions.ConnectionError("Connection reset by peer")

            with self.assertRaises(requests.exceptions.ConnectionError):
                nasa_images.patient(always_reset)("u")
            self.assertEqual(len(calls), 4, "three retries, then the error is reported")
            calls.clear()

            def missing(url, **kw):
                calls.append(url)
                return FakeResponse(status=404)

            self.assertEqual(nasa_images.patient(missing)("u").status_code, 404)
            self.assertEqual(len(calls), 1, "a real answer (404) is not retried")
        finally:
            nasa_images.RETRY_WAITS = old

    def test_a_small_image_is_passed_over(self):
        d = Path(tempfile.mkdtemp())
        get = fake_nasa({"comet": [("comet", "tiny"), ("comet tail", "big")]}, {"tiny": jpeg(300, 200), "big": jpeg()})
        img = nasa_images.fetch("comet", d / "001", get=get, log=lambda m: None)
        self.assertEqual(img.nasa_id, "big")


class Rows(unittest.TestCase):
    def test_rows_from_the_csv_match_the_timed_plan(self):
        a, b = visual_dicts_from_csv(SAMPLE), visual_dicts(load_plan(SAMPLE, WORDS))
        self.assertEqual([(x["scene_number"], x["asset_type"], x["prompt"]) for x in a], [(x["scene_number"], x["asset_type"], x["prompt"]) for x in b])
        self.assertEqual([x["asset_type"] for x in a], ["stock_image"] * 3, "nasa_image rows show as stock_image rows (every table action works)")

    @unittest.skipUnless(HAS_FFMPEG, "ffmpeg")
    def test_a_card_whose_file_is_a_clip_gets_a_still(self):
        d = Path(tempfile.mkdtemp())
        clip = d / "002.mp4"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=320x180:rate=10:duration=2", "-pix_fmt", "yuv420p", str(clip)], check=True)
        from starmap.media import still_of

        out = still_of(clip, d / "stills" / "002.jpg")
        self.assertTrue(out.is_file() and out.stat().st_size > 0)

    def test_fetch_media_reports_missing_rows_by_scene_and_csv_row(self):
        from pakmap.sourcing import FetchResult

        plan = load_plan(SAMPLE, WORDS)
        res = fetch_media(plan, Path(tempfile.mkdtemp()), log=lambda m: None, nasa_get=fake_nasa({}, {}),
                          fetch_scenes=lambda rows, d, **kw: FetchResult(paths={}, missing={"1": "no result", "2": "no result"}, skipped=["3"]))
        self.assertEqual(res.unresolved, ["1", "2"])
        self.assertIn("Visual Plan scene 1 (clip in beat b2, CSV row 7", res.missing[0])
        self.assertEqual(res.media["row:30"], {"file": ""}, "a skipped row is left out, not an error")

    def test_rows_nasa_never_answered_are_reported_not_given_to_stock(self):
        """A NASA outage must not put a modern stock photo where a historical NASA picture belongs: the row is reported
        missing (Generate again retries it) and never reaches the stock search."""
        import requests

        from pakmap.sourcing import FetchResult

        def down(url, **kw):
            raise requests.exceptions.ConnectionError("Connection reset by peer")

        seen = []

        def stock(rows, d, **kw):
            seen.extend(str(r.scene_number) for r in rows)
            return FetchResult(paths={n: str(Path(d) / f"{n}.jpg") for n in ()}, missing={}, skipped=[])

        old = nasa_images.RETRY_WAITS
        nasa_images.RETRY_WAITS = (0, 0, 0)
        try:
            plan = load_plan(SAMPLE, WORDS)
            res = fetch_media(plan, Path(tempfile.mkdtemp()), log=lambda m: None, nasa_get=down, fetch_scenes=stock)
        finally:
            nasa_images.RETRY_WAITS = old
        nasa_scenes = [m.scene_number for m in media_rows(plan) if m.source == "nasa_image"]
        self.assertTrue(nasa_scenes)
        self.assertFalse(set(seen) & set(nasa_scenes), "no NASA row went to the stock search")
        self.assertEqual(sorted(res.unresolved), sorted(nasa_scenes))
        self.assertTrue(all("did not answer" in m and "Generate again" in m for m in res.missing))


class Sound(unittest.TestCase):
    def test_cues_one_at_a_time_and_the_drone_stops_under_footage(self):
        spec = {"duration": 30, "camera": {"start": {"target": "earth", "fill": 0.5}, "moves": [{"t": 5, "dur": 3, "to": {"target": "earth+moon", "fit": 1.5}},
                                                                                            {"t": 15, "dur": 3, "to": {"target": "milkyway", "distance": {"ly": 160000}}}]},
                "layers": [{"type": "title", "start": 0.2}, {"type": "trajectory", "start": 5.1}, {"type": "orbit", "start": 5.2},
                           {"type": "trajectory", "draw": False}, {"type": "stat_chip", "start": 9, "count_up": {"t0": 9, "t1": 10.6}}],
                "footage": [{"start": 20, "end": 24}, {"start": 24, "end": 28}]}
        h = sound_hints(spec)
        self.assertEqual([(c["t"], c["sfx"]) for c in h["cues"]],
                         [(0.2, "deep_thud"), (5, "map_slide_whoosh"), (9.0, "counter_ticks"), (15, "earth_spin"), (19.75, "soft_transition"), (23.75, "soft_transition")])
        self.assertEqual(h["ambience"], [{"t": 0.0, "ambience": "space_drone"}, {"t": 20.0, "ambience": "none"}, {"t": 28.0, "ambience": "space_drone"}])


@unittest.skipUnless(HAS_FFMPEG, "ffmpeg")
class Generate(unittest.TestCase):
    def test_a_whole_run_with_a_fake_renderer(self):
        tmp = Path(tempfile.mkdtemp())
        vo = tmp / "vo.wav"
        with wave.open(str(vo), "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000); w.writeframes(struct.pack("<h", 0) * 16000 * 55)
        media = json.loads((S / "apollo11_media.json").read_text(encoding="utf-8"))

        def fetch(plan, images_dir, **kw):
            out = Fetched()
            for m in media_rows(plan):
                hit = media[f"{m.source}:{m.prompt}"]
                out.media[f"row:{m.row}"] = {"file": str(HERE / "starmap-engine" / "samples" / "media" / hit["file"]), "credit": hit["credit"]}
                out.credits.append(hit["credit"])
            return out

        seen = {}

        def render(spec, out, progress=None, **kw):
            seen["spec"] = spec
            progress(1, 2)
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"color=c=black:s=320x180:r=30:d={spec['duration']}", "-pix_fmt", "yuv420p", str(out)], check=True)
            from starmap.engine_runner import RenderOutcome

            return RenderOutcome(Path(out), 10)

        res = generate_starmap_video(S / "apollo11_beats.csv", vo, tmp / "final.mp4", work_dir=tmp / "work", whisper_words=WORDS, images_dir=tmp / "media",
                                     watermark={"text": "My Channel"}, fetch=fetch, render=render, log=lambda m: None)
        self.assertTrue(res.ok, res.errors)
        self.assertTrue((tmp / "final.mp4").is_file() and (tmp / "final - credits.txt").is_file())
        spec = seen["spec"]
        self.assertEqual(spec["watermark"], {"text": "My Channel"})
        self.assertAlmostEqual(spec["duration"], 55.0, places=1)
        media_dir = Path(spec["media_dir"])
        names = [L["image"] for L in spec["layers"] if L["type"] == "photo_card"] + [f.get("image") or f.get("file") for f in spec["footage"]]
        self.assertTrue(names and all((media_dir / n).is_file() for n in names), "every picture is in the one folder the renderer serves")
        credits = (tmp / "final - credits.txt").read_text(encoding="utf-8")
        self.assertIn("NASA AS11-40-5875", credits)
        self.assertIn("illustrated", credits)
        self.assertTrue(res.audio is not None and res.audio.cues, "sound design ran")

    def test_file_pictures_next_to_the_csv_are_found_wherever_the_app_runs(self):
        """A file:<name> picture sits next to the CSV (in its own folder, not the app's): Generate must use that file."""
        tmp = Path(tempfile.mkdtemp())
        (tmp / "pictures").mkdir()
        src = HERE / "starmap-engine" / "samples" / "media"
        shutil.copy(src / "as11-44-6642.jpg", tmp / "pictures" / "card.jpg")
        shutil.copy(src / "as11-40-5875.jpg", tmp / "pictures" / "clip.jpg")
        text = (S / "apollo11_beats.csv").read_text(encoding="utf-8")
        for asset, name in json.loads((S / "apollo11_media.json").read_text(encoding="utf-8")).items():
            if not asset.startswith("_"):
                text = text.replace(asset, "file:pictures/" + ("card.jpg" if "horizon" in asset else "clip.jpg"))
        (tmp / "plan.csv").write_text(text, encoding="utf-8")
        vo = tmp / "vo.wav"
        with wave.open(str(vo), "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000); w.writeframes(struct.pack("<h", 0) * 16000 * 55)
        seen = {}

        def render(spec, out, progress=None, **kw):
            seen["spec"] = spec
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"color=c=black:s=320x180:r=30:d={spec['duration']}", "-pix_fmt", "yuv420p", str(out)], check=True)
            from starmap.engine_runner import RenderOutcome

            return RenderOutcome(Path(out), 10)

        res = generate_starmap_video(tmp / "plan.csv", vo, tmp / "final.mp4", work_dir=tmp / "work", whisper_words=WORDS, images_dir=tmp / "media",
                                     fetch=lambda plan, d, **kw: Fetched(), render=render, log=lambda m: None, sound_design=False)
        self.assertTrue(res.ok, res.errors)
        spec, media_dir = seen["spec"], Path(seen["spec"]["media_dir"])
        names = [L["image"] for L in spec["layers"] if L["type"] == "photo_card"] + [f.get("image") or f.get("file") for f in spec["footage"]]
        self.assertTrue(names and all((media_dir / n).is_file() for n in names))
        self.assertTrue(any(n.endswith("card.jpg") for n in names) and any(n.endswith("clip.jpg") for n in names))
        self.assertEqual(Path(spec["segment_cache"]), tmp / "work" / "render_chunks", "a re-render reuses the unchanged parts")

    def test_a_card_given_a_clip_plays_the_clip(self):
        """A card's file:<name>.mp4 stays a clip: the spec card carries "video" (not "image") and Generate keeps it."""
        tmp = Path(tempfile.mkdtemp())
        (tmp / "pictures").mkdir()
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=320x180:rate=30:duration=2",
                        "-pix_fmt", "yuv420p", str(tmp / "pictures" / "card.mp4")], check=True)
        shutil.copy(HERE / "starmap-engine" / "samples" / "media" / "as11-40-5875.jpg", tmp / "pictures" / "clip.jpg")
        text = (S / "apollo11_beats.csv").read_text(encoding="utf-8")
        for asset in json.loads((S / "apollo11_media.json").read_text(encoding="utf-8")):
            if not asset.startswith("_"):
                text = text.replace(asset, "file:pictures/" + ("card.mp4" if "horizon" in asset else "clip.jpg"))
        (tmp / "plan.csv").write_text(text, encoding="utf-8")
        vo = tmp / "vo.wav"
        with wave.open(str(vo), "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000); w.writeframes(struct.pack("<h", 0) * 16000 * 55)
        seen = {}

        def render(spec, out, progress=None, **kw):
            seen["spec"] = spec
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"color=c=black:s=320x180:r=30:d={spec['duration']}", "-pix_fmt", "yuv420p", str(out)], check=True)
            from starmap.engine_runner import RenderOutcome

            return RenderOutcome(Path(out), 10)

        res = generate_starmap_video(tmp / "plan.csv", vo, tmp / "final.mp4", work_dir=tmp / "work", whisper_words=WORDS, images_dir=tmp / "media",
                                     fetch=lambda plan, d, **kw: Fetched(), render=render, log=lambda m: None, sound_design=False)
        self.assertTrue(res.ok, res.errors)
        spec = seen["spec"]
        videos = [L for L in spec["layers"] if L["type"] == "photo_card" and L.get("video")]
        self.assertTrue(videos, "the clip card survived Generate")
        self.assertTrue(all(L["video"].endswith("card.mp4") and not L.get("image") for L in videos))
        self.assertTrue(all((Path(spec["media_dir"]) / L["video"]).is_file() for L in videos))

    def test_only_nasa_material_is_credited_on_screen(self):
        from starmap.media import _is_nasa

        self.assertTrue(_is_nasa({"source": "nasa_image", "author": "NASA"}))
        self.assertTrue(_is_nasa({"asset_type": "nasa_video"}))
        self.assertFalse(_is_nasa({"source": "pexels", "author": "Luz Calor Som", "asset_type": "stock_video"}))

    def test_problems_come_back_as_messages(self):
        tmp = Path(tempfile.mkdtemp())
        res = generate_starmap_video(tmp / "nope.csv", tmp / "vo.wav", tmp / "out.mp4", work_dir=tmp, whisper_words=WORDS, images_dir=tmp)
        self.assertFalse(res.ok)
        self.assertIn("not found", res.errors[0])


if __name__ == "__main__":
    unittest.main()
