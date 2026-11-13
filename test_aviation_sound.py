import re
import subprocess
import time
from pathlib import Path

import pytest

from aviation import sound as SO


def _shot(layer, a, b, **kw):
    d = {"layer": layer, "start": a, "end": b, "scene": 1}
    d.update(kw)
    return d


def _plan():
    shots = [
        _shot("stage.lay_stage", 0.0, 8.0, cues=[(0.5, "pop"), (0.6, "whoosh_soft"), (2.0, "typewriter_tick"), (3.0, "whoosh_soft"), (7.0, "thud_soft")]),
        {"kind": "footage", "start": 8.0, "end": 9.5, "scene": 2, "mode": "news"},
        _shot("cards.lay_article", 9.5, 14.0),
        _shot("retention.lay_rehook", 20.0, 22.0),
        _shot("flightmap.lay_flight_map", 24.0, 40.0, full_frame=True, mode="flight", cues=[(25.0, "whoosh_soft")]),
        _shot("cards.lay_article", 30.0, 34.0),
        _shot("stage.lay_stage", 40.0, 50.0, cues=[(41.0, "pop")]),
    ]
    scenes = [{"scene_no": 1, "text": "A story.", "start": 0.0, "end": 8.0},
              {"scene_no": 2, "text": "News now.", "start": 8.0, "end": 24.0},
              {"scene_no": 3, "text": "Flying on.", "start": 24.0, "end": 40.0},
              {"scene_no": 4, "text": "But then it turned.", "start": 40.0, "end": 50.0}]
    return {"shots": shots, "modes": ["story", "news", "flight", "story"]}, scenes


def test_sfx_map_files_exist():
    from aviation import style as S
    for name in set(v for v in S.SOUNDS.values() if v):
        assert name in SO.SFX_MAP, name
        assert Path(SO.SFX_MAP[name]).is_file(), name
    for b in sum(SO.BEDS.values(), []):
        assert (SO.MUSIC_DIR / f"{b}.opus").is_file(), b


def test_events_rules():
    plan, scenes = _plan()
    ev = SO.events(plan, scenes)
    ts = [e["t"] for e in ev]
    assert ts == sorted(ts)
    assert all(b - a >= 0.25 - 1e-9 for a, b in zip(ts, ts[1:]))
    assert not [e for e in ev if 24 <= e["t"] < 40 and e["kind"] == "whoosh"]      # map stretch is calm
    assert not [e for e in ev if e["t"] == 30.0]                                    # a card inside the map stretch gets nothing
    assert not [e for e in ev if 8.0 <= e["t"] < 9.5]                               # footage slot: nothing
    assert any(e["t"] == 9.5 and e["kind"] == "whoosh" for e in ev)                 # card: soft whoosh
    assert any(e["kind"] == "tick" for e in ev) and any(e["kind"] == "thud" for e in ev)
    # 0.5 pop vs 0.6 whoosh: closer than 0.25 s -> only the stronger (pop) stays
    assert any(e["t"] == 0.5 for e in ev) and not any(e["t"] == 0.6 for e in ev)
    hit = [e for e in ev if e["kind"] == "hit"]
    assert len(hit) == 1 and hit[0]["t"] == 20.0 and abs(hit[0]["duck_from"] - 19.6) < 1e-6
    assert all(Path(e["file"]).is_file() and e["gain_db"] < 0 for e in ev)


def test_music_plan_covers_film():
    plan, scenes = _plan()
    mp = SO.music_plan(plan, scenes, 50.0)
    assert mp[0]["start"] == 0.0 and mp[-1]["end"] == 50.0
    assert [m["mood"] for m in mp] == ["story", "news", "flight", "story"]
    for a, b in zip(mp, mp[1:]):
        assert a["end"] > b["start"]                                                # crossfade overlap
        assert abs((a["end"] - b["start"]) - SO.XFADE_S) < 1e-6
        assert a["bed"] != b["bed"]
    flat = [d for m in mp for d in m["dips"]]
    assert any(abs(d[1] - 40.0) < 1e-6 and abs((d[1] - d[0]) - 0.8) < 1e-6 for d in flat)     # silence before the turn line
    assert any(abs(d[0] - 19.6) < 1e-6 for d in flat)                                          # rehook duck


def _lufs(p):
    r = subprocess.run(["ffmpeg", "-nostats", "-i", str(p), "-af", "ebur128", "-f", "null", "-"], capture_output=True, text=True)
    return float(re.findall(r"I:\s+(-?[\d.]+) LUFS", r.stderr)[-1])


def _dur(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)], capture_output=True, text=True)
    return float(r.stdout.strip())


def test_mix_length_and_loudness(tmp_path):
    voice = tmp_path / "v.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=f=220:d=6,tremolo=f=3:d=0.7", "-ar", "48000", str(voice)], check=True)
    ev = [SO._ev(1.0, "pop"), SO._ev(2.0, "whoosh_soft"), SO._ev(4.0, "low_hit", duck_from=3.6)]
    music = [{"start": 0.0, "end": 3.5, "bed": str(SO.MUSIC_DIR / "lost_frontier.opus"), "gain_db": -32.0, "mood": "story", "xfade": 3.0, "dips": [(3.2, 4.0, -30.0)]},
             {"start": 2.0, "end": 6.0, "bed": str(SO.MUSIC_DIR / "long_note_four.opus"), "gain_db": -35.0, "mood": "flight", "xfade": 3.0, "dips": []}]
    out = tmp_path / "mix.wav"
    t0 = time.time()
    SO.mix(str(voice), ev, music, str(out), 6.0)
    assert out.is_file()
    assert abs(_dur(out) - 6.0) < 0.15
    assert abs(_lufs(out) - (-14.0)) < 2.0
    assert time.time() - t0 < 60
