import json
import subprocess
from pathlib import Path

from cinematic_explainer.war import footage_discovery as FD
from cinematic_explainer.war import footage_match as FM
from cinematic_explainer.war import integration as I


def _scene(no, text, path=None, meta=None, **kw):
    d = {"scene_no": str(no), "text": text, "start": no * 5.0, "end": no * 5.0 + 5.0, "footage": path, "footage_meta": meta or {}}
    d.update(kw)
    return d


class _FakeResult:
    def __init__(self, path, meta):
        self.path, self.metadata, self.ok, self.error = path, meta, True, None

        class _S:
            value = "stock_video"
        self.source = _S()


class _FakeProvider:
    def __init__(self):
        self.calls = []

    def resolve(self, scene, images_dir, log=print):
        self.calls.append(scene.stock)
        p = Path(images_dir) / f"{int(scene.scene_number):03d}.mp4"
        p.write_bytes(b"x")
        return _FakeResult(p, {"provider": "pexels", "provider_asset_id": "42", "author": "A Person", "source_url": "https://www.pexels.com/video/42/",
                               "width": 1920, "height": 1080, "duration": 9.0})


def test_queries_are_offline_specific_and_never_name_people():
    q = FD.scene_queries("Drones hit the oil refinery near Moscow at night, Vladimir Putin said.")
    assert q and all("putin" not in x.lower() for x in q)
    assert any("refinery" in x.lower() for x in q) and any("night" in x.lower() for x in q)
    assert FD.scene_queries("") == []


def test_discovery_off_by_default_changes_nothing(tmp_path):
    scenes = [_scene(1, "Drones hit an oil refinery.")]
    out, rep = FD.discover(scenes, tmp_path, {})
    assert out[0].get("footage_candidates") is None
    assert "off" in rep["1"]["note"]


def test_discovery_with_provider_downloads_into_own_folder_and_records_provenance(tmp_path):
    (tmp_path / "Images").mkdir()
    (tmp_path / "Images" / "001.mp4").write_bytes(b"user file must stay")
    prov = _FakeProvider()
    scenes = [_scene(1, "Drones hit an oil refinery near Moscow."), _scene(2, "Hello.")]
    out, rep = FD.discover(scenes, tmp_path, {"discover_footage": True}, provider=prov)
    assert (tmp_path / "Images" / "001.mp4").read_bytes() == b"user file must stay"        # never over a project file
    c = out[0]["footage_candidates"][0]
    assert Path(c["path"]).parent.name == FD.DISCOVER_DIR and c["meta"]["provider"] == "pexels" and c["meta"]["author"] == "A Person"
    assert c["meta"]["license"] == "Pexels License" and rep["1"]["source"] == "provider" and prov.calls
    assert "2" not in rep                                                                   # no queries for a sentence with nothing to show


def test_second_run_reuses_the_cache_without_fetching(tmp_path):
    prov = _FakeProvider()
    FD.discover([_scene(1, "Drones hit an oil refinery near Moscow.")], tmp_path, {"discover_footage": True}, provider=prov)
    prov2 = _FakeProvider()
    out, rep = FD.discover([_scene(3, "Another oil refinery burns near Moscow.")], tmp_path, {"discover_footage": True}, provider=prov2)
    assert not prov2.calls and rep["3"]["source"] == "cache" and out[0]["footage_candidates"]


def test_budget_and_failures_never_break(tmp_path):
    class Boom:
        def resolve(self, *a, **k):
            raise RuntimeError("network down")
    out, rep = FD.discover([_scene(1, "Drones hit an oil refinery.")], tmp_path, {"discover_footage": True}, provider=Boom())
    assert not out[0].get("footage_candidates") and rep["1"]["source"] == "none"
    prov = _FakeProvider()
    sc = [_scene(i, "Drones hit an oil refinery near Moscow.") for i in range(1, 5)]
    out, rep = FD.discover(sc, tmp_path, {"discover_footage": True, "discover_max_clips": 1}, provider=prov)
    assert len(prov.calls) == 1


def test_no_key_means_no_provider(tmp_path, monkeypatch):
    monkeypatch.delenv("PEXELS_API_KEY", raising=False)
    monkeypatch.delenv("PIXABAY_API_KEY", raising=False)
    monkeypatch.setattr(FD, "_keys", lambda c: {"pexels": "", "pixabay": ""})
    p, why = FD.default_provider(tmp_path, {})
    assert p is None and "key" in why


def test_ai_generated_clip_is_an_illustration_never_an_event():
    s = _scene(1, "Ukrainian troops dug in near Kupiansk.", "ai.mp4", {"ai_generated": True, "user_supplied": True, "video_title": "soldiers in a trench near Kupiansk"})
    out = FM.match_scenes([s])[0]
    assert out["footage_match"]["class"] == "ai_generated"
    m = out["footage_meta"]
    assert m["ai_generated"] and m["generic"] and not m.get("stock_relevant")


def test_flow_record_is_ai_generated():
    m = I.footage_meta_for({"source": "flow_video", "provider": "flow", "status": "complete", "local_path": "x.mp4"}, None, scene_file="x.mp4")
    assert m["ai_generated"] and m["generic"]


def test_reuse_is_limited_and_never_adjacent_without_subject():
    stock = {"generic": True, "kind": "stock", "stock_query": "oil refinery"}
    t = "A refinery burned."
    sc = [_scene(i, t, "r.mp4", dict(stock)) for i in range(1, 5)]
    out = FM.match_scenes(sc, allow_reuse=False)
    chosen = [o.get("footage") for o in out]
    assert chosen.count("r.mp4") <= FM.MAX_USES
    assert not any(a == b == "r.mp4" for a, b in zip(chosen, chosen[1:]))
    assert all(o["footage_match"].get("uses", 0) <= FM.MAX_USES for o in out)


def test_same_subject_may_return_adjacent():
    st = {"generic": True, "kind": "stock", "stock_query": "Pantsir-S1 air defense"}
    out = FM.match_scenes([_scene(1, "The Pantsir-S1 system.", "p.mp4", dict(st)), _scene(2, "The Pantsir-S1 again.", "p.mp4", dict(st))], allow_reuse=False)
    assert out[0]["footage"] == out[1]["footage"] == "p.mp4"


def test_load_scenes_adds_discovery_report(tmp_path):
    out = I.load_scenes(tmp_path, [{"scene_no": 1, "text": "Drones hit an oil refinery near Moscow.", "start": 0, "end": 5}], discovery_provider=_FakeProvider(),
                        config={"discover_footage": True})
    assert out[0]["footage_discovery"]["queries"] and out[0].get("footage")


def _ffmpeg_clip(path, seconds=3):
    # top half green, a red band across the bottom 12% (a stand-in for a burned-in caption)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c=0x20a040:s=1280x720:r=25:d={seconds}", "-vf",
                    "drawbox=x=0:y=ih*0.88:w=iw:h=ih*0.12:color=red:t=fill", "-pix_fmt", "yuv420p", str(path)], check=True)


def test_prepare_clean_clip_removes_the_caption_band_and_is_cached(tmp_path):
    src = tmp_path / "src.mp4"
    _ffmpeg_clip(src)
    out = FD.prepare_clean_clip(src, tmp_path / "clips", 0.5, 1.5, crop_bottom=0.14)
    again = FD.prepare_clean_clip(src, tmp_path / "clips", 0.5, 1.5, crop_bottom=0.14)
    assert out == again and Path(out).stat().st_size > 0
    p = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=width,height:format=duration", "-of", "json", out], capture_output=True, text=True)
    j = json.loads(p.stdout)
    assert (j["streams"][0]["width"], j["streams"][0]["height"]) == (1280, 720) and abs(float(j["format"]["duration"]) - 1.5) < 0.2
    from PIL import Image
    png = tmp_path / "f.png"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", out, "-frames:v", "1", str(png)], check=True)
    im = Image.open(png).convert("RGB")
    reds = sum(1 for y in range(0, 720, 8) for x in range(0, 1280, 16) if im.getpixel((x, y))[0] > 150 and im.getpixel((x, y))[1] < 90)
    assert reds == 0


def test_prepare_clean_clip_rejects_bad_input(tmp_path):
    import pytest
    with pytest.raises(RuntimeError):
        FD.prepare_clean_clip(tmp_path / "missing.mp4", tmp_path, 0, 1)


def test_prepare_clean_clip_explicit_name_is_not_reused_for_a_different_request(tmp_path):
    src = tmp_path / "src.mp4"
    _ffmpeg_clip(src, 4)
    o = tmp_path / "named.mp4"
    FD.prepare_clean_clip(src, o, 0.0, 1.0)
    FD.prepare_clean_clip(src, o, 0.0, 2.0)
    d = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(o)], capture_output=True, text=True).stdout)
    assert abs(d - 2.0) < 0.2
