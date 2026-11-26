"""Senior Trivia: CSV checks, timeline rhythm, every layout draws, the mix writes. No Flow, no Edge, no network."""
import wave
from pathlib import Path

import numpy as np
from PIL import Image

from senior_trivia import csvplan, pictures, render, timeline

SAMPLE = Path(__file__).parent / "senior_trivia" / "samples" / "test_8.csv"


def _wav(path, secs):
    pcm = (np.sin(np.arange(int(secs * 48000)) * 0.05) * 8000).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(48000)
        w.writeframes(pcm.tobytes())
    return str(path)


def _spec(tmp_path, with_pics=True):
    rows, problems = csvplan.read(SAMPLE)
    rows = [r for r in rows if r["type"] != "thumbnail"]
    sc = timeline.scripts(rows)
    sents = {s for parts in sc.values() for k in parts for s in parts[k]}
    voiced = {}
    for k, s in enumerate(sorted(sents)):
        voiced[s] = _wav(tmp_path / f"v{k}.wav", 0.6 + 0.02 * len(s.split()))
    pics = {i: pictures.picture_keys(r) for i, r in enumerate(rows)}
    spec = timeline.build(rows, voiced, sc, pics=pics, size=(640, 360), title="Test Quiz")
    pic = tmp_path / "p.png"
    Image.new("RGB", (800, 450), (180, 140, 90)).save(pic)
    keys = {k for v in pics.values() for k in v if k}
    spec["assets"] = {"pictures": {k: str(pic) for k in keys} if with_pics else {}}
    spec["host"] = {"name": "Hal", "tagline": "your quiz host"}
    return rows, spec


def test_sample_csv_is_clean():
    rows, problems = csvplan.read(SAMPLE)
    assert problems == []
    assert csvplan.mode_of(rows) == "rounds"
    q = next(r for r in rows if r["type"] == "question")
    assert csvplan.answer_index(q) == 0 and csvplan.answer_text(q) == "A line shared by several homes"


def test_checker_catches_bad_rows():
    text = ("type,round,question,options,answer\nround,R | easy,,,\n"
            "question,,Q one?,A | B | C,E\nquestion,,Q one?,A | A,A\nquestion,,,X | Y,X\nhost,,,,\n")
    _rows, problems = csvplan.read(text)
    joined = " ".join(problems)
    assert "not one of the options" in joined
    assert "same question" in joined
    assert "two options are the same" in joined
    assert "no question text" in joined
    assert "needs its `line`" in joined


def test_answer_forms():
    r = {"options": "Ford | Chevy | Dodge", "answer": "b"}
    assert csvplan.answer_index(r) == 1
    assert csvplan.answer_index(dict(r, answer="3")) == 2
    assert csvplan.answer_index(dict(r, answer="Dodge")) == 2
    assert csvplan.answer_index(dict(r, answer="C) Dodge")) == 2


def test_timeline_rhythm(tmp_path):
    rows, spec = _spec(tmp_path)
    qs = [s for s in spec["segs"] if s["kind"] == "question"]
    assert len(qs) == 8 and qs[-1]["n"] == 8
    for s in qs:
        assert len(s["opt_at"]) == 4 and s["opt_at"] == sorted(s["opt_at"])
        assert s["count_at"] > s["opt_at"][-1]
        assert abs(s["reveal_at"] - s["count_at"] - 6) < 1e-6
        assert s["t1"] > s["reveal_at"] + 1
    ticks = [e for e in spec["sfx"] if e["name"] == "tick"]
    assert len(ticks) == 9 * 6   # 8 questions + bonus, 6 ticks each
    t = [s["t0"] for s in spec["segs"]]
    assert t == sorted(t) and all(s["t1"] > s["t0"] for s in spec["segs"])


def test_every_layout_draws(tmp_path):
    for with_pics in (True, False):
        rows, spec = _spec(tmp_path, with_pics)
        dr = render.Drawer(spec, spec["assets"])
        for seg in spec["segs"]:
            for t in (seg["t0"], (seg["t0"] + seg["t1"]) / 2, seg.get("reveal_at", seg["t1"]) + 0.5, seg["t1"] - 0.01):
                im = dr.frame(seg, t)
                assert im.size == (640, 360)
        dr.close()


def test_item_mode(tmp_path):
    text = "type,answer,picture,seconds\n" + "".join(f"item,Thing {k},an old thing {k},7\n" for k in range(5))
    rows, problems = csvplan.read(text)
    assert problems == [] and csvplan.mode_of(rows) == "items"
    spec = timeline.build(rows, {}, timeline.scripts(rows), pics={i: pictures.picture_keys(r) for i, r in enumerate(rows)},
                          size=(640, 360))
    assert spec["voice"] == [] and len(spec["segs"]) == 5
    dr = render.Drawer(dict(spec, host={}), {"pictures": {}})
    seg = spec["segs"][0]
    dr.frame(seg, seg["reveal_at"] + 0.5)


def test_mix_writes(tmp_path):
    _rows, spec = _spec(tmp_path)
    spec["duration"] = min(spec["duration"], 20)
    spec["voice"] = [v for v in spec["voice"] if v["t"] < 18]
    spec["sfx"] = [e for e in spec["sfx"] if e["t"] < 18]
    out = render.mix(spec, tmp_path / "m.wav")
    with wave.open(str(out)) as w:
        assert w.getnframes() > 48000 * 19


def test_app_page_is_wired():
    root = Path(__file__).parent
    app = (root / "app.py").read_text(encoding="utf-8")
    for hook in ("from ui import senior_trivia_section as _st_section", "_st_section.activate(self)", "_st_section.cta(self, action)",
                 "_st_section.sync_cta(self)", "_st_section.resume_on_open(self)", "_st_section.deactivate(self, remember=False)",
                 'return "Senior Trivia"'):
        assert hook in app, hook
    from ui import style_registry as R
    assert "Senior Trivia" in R.STANDALONE and "Senior Trivia" in R.EXTRA_CARDS
    assert any("Senior Trivia" in names for _t, names in R.GROUPS)
    import visual_bridge
    assert "senior_trivia" in visual_bridge.OWNERS
    from autorun import job
    import make_video
    assert job.STYLES["senior-trivia"]["pick"] == "Senior Trivia" and make_video.STYLES["senior-trivia"][3] == "Senior Trivia"
    from ui import senior_trivia_section as S
    assert S.STYLE == "Senior Trivia" and callable(S.on_generate) and callable(S.on_render)


def test_plan_pictures_fit_the_visuals_tab(tmp_path):
    _rows, spec = _spec(tmp_path)
    from senior_trivia import pictures as P
    spec["pictures"] = {k: {"prompt": p} for k, p in P.jobs(_rows).items()}
    import visual_bridge
    rows = visual_bridge.spec_rows(tmp_path / "assets", spec)
    assert len(rows) == len(spec["pictures"]) > 0
