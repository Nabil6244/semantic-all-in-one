"""pakMap's mixer streams the mix in windows: the result must be the mix the old whole-file mixer made.

A frozen copy of the old whole-file mixer is kept below as the reference. The streaming mixer is run with tiny windows
(so effects, ambience loops, loop joins, fades, ducking and the major-effect dip all cross window edges) and compared
sample by sample. Only the major-effect dip is computed differently (a running sum instead of a direct convolution), so
it may differ in the last float digit (~1e-7); everything else is bit-identical. Memory: a 2-minute and a 12-minute mix
need the same memory (run in a child process). Uses generated tones, never the user's sound library."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import textwrap
import unittest
import wave
from pathlib import Path
from unittest import mock

import numpy as np

from pakmap import audio_mix as am
from pakmap import audio_plan as ap

ROOT = Path(__file__).resolve().parent
SR = am.SR


# ---- the old whole-file mixer (reference; do not "fix" it) ----------------------------------------------------------

def _ref_narration_envelope(narr):
    mono = narr.mean(axis=1) if narr.ndim == 2 else narr
    n = len(mono)
    hops = max(1, -(-n // am.HOP))
    pad = np.zeros(hops * am.HOP, dtype=np.float32)
    pad[:n] = mono
    rms = np.sqrt((pad.reshape(hops, am.HOP) ** 2).mean(axis=1))
    target = np.clip(rms / am.SPEECH_RMS, 0.0, 1.0)
    a_att = 1.0 - np.exp(-am.HOP / SR / am.ATTACK_S)
    a_rel = 1.0 - np.exp(-am.HOP / SR / am.RELEASE_S)
    env = np.zeros(hops, dtype=np.float32)
    y = 0.0
    for i, x in enumerate(target):
        y += (a_att if x > y else a_rel) * (x - y)
        env[i] = y
    xs = (np.arange(n) / am.HOP) - 0.5
    return np.interp(xs, np.arange(hops), env).astype(np.float32)


def _ref_major_envelope(majors, n):
    env = np.zeros(n, dtype=np.float32)
    for a, b in majors:
        env[int(max(0, a) * SR):int(min(n / SR, b) * SR)] = 1.0
    if not majors:
        return env
    k = int(0.15 * SR)
    kernel = np.hanning(2 * k + 1).astype(np.float32)
    return np.clip(np.convolve(env, kernel / kernel.sum(), mode="same"), 0.0, 1.0)


def _ref_loop(clip, length):
    if len(clip) == 0:
        return np.zeros((length, 2), dtype=np.float32)
    if len(clip) >= length:
        return clip[:length].copy()
    x = int(min(am.LOOP_FADE_S, len(clip) / 4) * SR)
    up = np.linspace(0.0, 1.0, x, dtype=np.float32)[:, None]
    out = np.zeros((length, 2), dtype=np.float32)
    pos, first = 0, True
    while pos < length:
        seg = clip.copy()
        if not first and x:
            seg[:x] *= up
        more = pos + len(seg) < length
        if more and x:
            seg[-x:] *= up[::-1]
        end = min(length, pos + len(seg))
        out[pos:end] += seg[:end - pos]
        pos = pos + len(seg) - x if more else length
        first = False
    return out


def _ref_build_bus(plan, narr, total_s):
    n = int(round(total_s * SR))
    env = _ref_narration_envelope(narr)
    env = np.pad(env, (0, max(0, n - len(env))))[:n]
    sfx = np.zeros((n, 2), dtype=np.float32)
    amb = np.zeros((n, 2), dtype=np.float32)
    used = []
    cache = {}

    def clip_for(sound, asset):
        key = (str(asset.path or asset.catalog_id), sound.filters)
        if key not in cache:
            raw = am._synth.render(sound.synth) if asset.path is None else am.decode(asset.path, sound.filters)
            cache[key] = am.normalise(raw, sound.kind)
        return cache[key]

    for cue in plan.cues:
        for hit in ap.expand(cue):
            asset = plan.assets.get(hit.sound)
            sound = ap.sound_for(hit.sound)
            if asset is None or sound is None:
                continue
            clip = clip_for(sound, asset).copy()
            if sound.max_s:
                clip = clip[:int(sound.max_s * SR)]
            clip = am._fade(clip, sound.fade_in, sound.fade_out) * sound.volume
            i = int(round(hit.t * SR))
            if i >= n:
                continue
            j = min(n, i + len(clip))
            sfx[i:j] += clip[:j - i]
            used.append({"t": round(hit.t, 3), "sound": hit.sound, "asset": asset.catalog_id, "fidelity": asset.fidelity, "priority": hit.priority})
    for bed in plan.beds:
        asset = plan.assets.get(bed.sound)
        sound = ap.sound_for(bed.sound, "ambience")
        if asset is None or sound is None:
            continue
        i, j = int(bed.start * SR), min(n, int(bed.end * SR))
        if j - i < SR // 4:
            continue
        seg = am._fade(_ref_loop(clip_for(sound, asset), j - i), sound.fade_in, sound.fade_out) * sound.volume
        amb[i:j] += seg
        used.append({"t": round(bed.start, 3), "end": round(bed.end, 3), "sound": bed.sound, "asset": asset.catalog_id, "fidelity": asset.fidelity, "priority": "ambience"})
    major_env = _ref_major_envelope(plan.majors(), n)
    sfx *= (1.0 - am.DUCK_SFX * env)[:, None]
    amb *= ((1.0 - am.DUCK_AMBIENCE * env) * (1.0 - am.DUCK_AMBIENCE_BY_MAJOR * major_env))[:, None]
    return sfx, amb, used


def _ref_mix(plan, voiceover, duration=None):
    """(mixed samples, bed scale, used) exactly as the old mix_pakmap_audio computed them (before writing the WAV)."""
    narr = am.decode(voiceover)
    total = max(len(narr) / SR, duration or 0.0)
    n = int(round(total * SR))
    sfx, amb, used = _ref_build_bus(plan, narr, total)
    bus = sfx + amb
    base = np.zeros((n, 2), dtype=np.float32)
    base[:len(narr)] = narr[:n]
    scale = 1.0
    if float(np.abs(base + bus).max()) > am.PEAK_LIMIT:
        lo, hi = 0.0, 1.0
        for _ in range(14):
            mid = (lo + hi) / 2
            if float(np.abs(base + bus * mid).max()) <= am.PEAK_LIMIT:
                lo = mid
            else:
                hi = mid
        scale = lo
    return base + bus * scale, scale, used


# ---- fixtures ------------------------------------------------------------------------------------------------------

def _write_wav(path: Path, samples: np.ndarray, sr: int = SR) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = (np.clip(samples, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1 if pcm.ndim == 1 else pcm.shape[1])
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


def _speech(seconds: float, amp: float, seed: int = 3) -> np.ndarray:
    """A tone that speaks and pauses (the envelope rises and falls), so ducking is exercised."""
    t = np.arange(int(seconds * SR)) / SR
    gate = (np.sin(2 * np.pi * 0.37 * t) > -0.2).astype(np.float32)
    noise = np.random.default_rng(seed).uniform(-0.05, 0.05, len(t))
    return (amp * gate * (np.sin(2 * np.pi * 190 * t) + noise)).astype(np.float32)


def _catalog(root: Path):
    """Effects and ambience of awkward lengths: a 1.5 s bed (loop fades overlap), a 3 s bed and a 40 s bed."""
    import smart_editing as se

    rng = np.random.default_rng(7)
    files = {
        "ui_pop_01": (0.4, lambda n: np.sin(2 * np.pi * 900 * np.arange(n) / SR) * np.exp(-np.arange(n) / (0.08 * SR))),
        "whoosh_01": (1.3, lambda n: rng.uniform(-0.6, 0.6, n) * np.hanning(n)),
        "amb_atmospheric_05": (3.0, lambda n: rng.uniform(-0.3, 0.3, n)),
        "amb_wind_02": (1.5, lambda n: rng.uniform(-0.2, 0.2, n)),
        "amb_city_01": (40.0, lambda n: rng.uniform(-0.25, 0.25, n) * (1 + 0.5 * np.sin(np.arange(n) / SR))),
    }
    ents = []
    for cid, (dur, make) in files.items():
        n = int(dur * SR)
        _write_wav(root / f"{cid}.wav", make(n).astype(np.float32))
        ents.append(se.SfxEntry(id=cid, file=f"{cid}.wav", category="ambience" if cid.startswith("amb") else "ui", tags=(), intensity="low", duration=dur))
    return se.SfxCatalog(root, ents)


def _plan(cat, duration: float, *, cues_every: float = 2.3, majors_every: float = 9.0, beds=None) -> ap.AudioPlan:
    plan = ap.AudioPlan(enabled=True)
    t = 0.7
    while t < duration - 1:
        plan.cues.append(ap.Cue(round(t, 3), "catalog:ui_pop_01", "test", "test", explicit=True))
        t += cues_every
    t = 3.1
    while majors_every and t < duration - 2:
        plan.cues.append(ap.Cue(round(t, 3), "catalog:whoosh_01", "test", "test", explicit=True, priority="major"))
        t += majors_every
    for start, end, cid in beds or [(0.0, duration * 0.4, "amb_atmospheric_05"), (duration * 0.4, duration * 0.55, "amb_wind_02"), (duration * 0.55, duration, "amb_city_01")]:
        plan.beds.append(ap.Bed(start, end, "catalog:" + cid, "test"))
    plan.cues.sort(key=lambda c: c.t)
    return am.resolve_assets(plan, cat)


class StreamingTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        self.cat = _catalog(self.d / "lib")

    def tearDown(self):
        self.tmp.cleanup()

    def mix_both(self, plan, narr, duration=None, chunk_s=0.73):
        _write_wav(self.d / "vo.wav", np.stack([narr, narr], axis=1) if narr.ndim == 1 else narr)  # stereo: no 3 dB upmix
        ref, ref_scale, ref_used = _ref_mix(plan, self.d / "vo.wav", duration)
        with mock.patch.object(am, "CHUNK", int(chunk_s * SR) // am.HOP * am.HOP):
            res = am.mix_pakmap_audio(plan, self.d / "vo.wav", self.d / "o.wav", duration=duration)
        return ref, ref_scale, ref_used, res, am.decode(res.path)


class TestTheSameMix(StreamingTestCase):
    def test_the_streamed_mix_is_the_old_mix(self):
        plan = _plan(self.cat, 25.0)
        self.assertTrue(plan.majors())
        ref, ref_scale, ref_used, res, out = self.mix_both(plan, _speech(22.0, 0.25), duration=25.0)  # music runs past the voice
        self.assertEqual(out.shape, ref.shape)
        self.assertEqual((res.bus_scale, ref_scale), (1.0, 1.0))
        self.assertEqual(res.used, ref_used)
        self.assertLess(float(np.abs(out - ref).max()), 1e-6)  # only the major-effect dip can differ, in the last digit
        self.assertAlmostEqual(res.peak, float(np.abs(ref).max()), places=6)

    def test_without_major_effects_it_is_bit_identical(self):
        plan = _plan(self.cat, 20.0, majors_every=0)
        self.assertFalse(plan.majors())
        ref, _, _, _, out = self.mix_both(plan, _speech(20.0, 0.25))
        np.testing.assert_array_equal(out, ref)

    def test_window_size_does_not_matter(self):
        plan = _plan(self.cat, 18.0)
        _write_wav(self.d / "vo.wav", _speech(18.0, 0.3))
        outs = []
        for chunk_s in (0.01, 0.37, 5.0, 60.0):
            with mock.patch.object(am, "CHUNK", max(am.HOP, int(chunk_s * SR) // am.HOP * am.HOP)):
                outs.append(am.decode(am.mix_pakmap_audio(plan, self.d / "vo.wav", self.d / f"o{chunk_s}.wav").path))
        for o in outs[1:]:
            np.testing.assert_array_equal(o, outs[0])

    def test_a_mix_that_would_clip_turns_the_bed_down_by_the_same_amount(self):
        plan = _plan(self.cat, 12.0, cues_every=0.9)
        ref, ref_scale, _, res, out = self.mix_both(plan, _speech(12.0, 0.9), duration=12.0)
        self.assertLess(ref_scale, 1.0)
        self.assertGreater(ref_scale, 0.0)
        self.assertEqual(res.bus_scale, ref_scale)
        self.assertLess(float(np.abs(out - ref).max()), 1e-6)
        self.assertLessEqual(res.peak, am.PEAK_LIMIT)

    def test_a_narration_louder_than_the_limit_mutes_the_bed_as_before(self):
        plan = _plan(self.cat, 6.0)
        narr = np.full(6 * SR, 0.985, np.float32)
        ref, ref_scale, _, res, out = self.mix_both(plan, narr)
        self.assertEqual((res.bus_scale, ref_scale), (0.0, 0.0))
        np.testing.assert_array_equal(out, ref)


class TestErrors(StreamingTestCase):
    def test_an_unreadable_voiceover_is_a_mixer_error(self):
        (self.d / "vo.wav").write_bytes(b"RIFF not really audio")
        with self.assertRaises(am.AudioMixError):
            am.mix_pakmap_audio(_plan(self.cat, 5.0), self.d / "vo.wav", self.d / "o.wav")


class TestPieces(StreamingTestCase):
    def test_loop_windows_match_the_old_loop(self):
        rng = np.random.default_rng(5)
        for clip_s, length_s in ((3.0, 11.3), (1.5, 9.1), (1.02, 4.0), (5.0, 5.0), (7.0, 3.0), (2.0, 2.0001)):
            clip = rng.uniform(-1, 1, (int(clip_s * SR), 2)).astype(np.float32)
            length = int(length_s * SR)
            ref = _ref_loop(clip, length)
            np.testing.assert_array_equal(am._loop(clip, length), ref)
            for w0, w1 in ((0, 1), (SR - 7, 2 * SR + 11), (length - 1000, length), (int(1.4 * SR), int(1.6 * SR))):
                w0, w1 = max(0, min(w0, length)), max(0, min(w1, length))
                np.testing.assert_array_equal(am._loop_window(clip, length, w0, w1), ref[w0:w1])

    def test_an_ambience_file_too_short_to_loop_is_an_error_not_a_hang(self):
        clip = np.zeros((int(0.8 * SR), 2), np.float32) + 0.1
        with self.assertRaises(am.AudioMixError):
            am._loop(clip, 5 * SR)

    def test_the_major_dip_matches_the_old_convolution(self):
        n = 40 * SR
        majors = [(0.0, 0.5), (3.0, 4.1), (3.9, 6.0), (20.0, 20.05), (39.8, 45.0), (-1.0, 0.2)]
        ref = _ref_major_envelope(majors, n)
        got = am._MajorEnvelope(majors, n)
        self.assertLess(float(np.abs(got.samples(0, n) - ref).max()), 1e-6)
        np.testing.assert_array_equal(got.samples(SR, 2 * SR), got.samples(0, n)[SR:2 * SR])

    def test_the_narration_envelope_is_bit_identical_however_it_is_fed(self):
        narr = np.stack([_speech(13.3, 0.3), _speech(13.3, 0.2, seed=9)], axis=1)
        ref = _ref_narration_envelope(narr)
        env = am._NarrationEnvelope()
        for a in range(0, len(narr), 12345):
            env.feed(narr[a:a + 12345])
        env.finish()
        np.testing.assert_array_equal(env.samples(0, len(narr)), ref)
        np.testing.assert_array_equal(env.samples(len(narr) - 10, len(narr) + 50)[10:], np.zeros(50, np.float32))


_MEMORY_PROBE = textwrap.dedent("""
    import json, resource, sys, time
    from pathlib import Path
    sys.path.insert(0, sys.argv[1])
    import numpy as np
    from pakmap import audio_mix as am
    from pakmap import audio_plan as ap
    import test_pakmap_audio_stream as t
    d, minutes = Path(sys.argv[2]), float(sys.argv[3])
    cat = t._catalog(d / "lib")
    plan = t._plan(cat, minutes * 60, cues_every=7.0, majors_every=40.0)
    before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    t0 = time.time()
    res = am.mix_pakmap_audio(plan, d / "vo.wav", d / "out.wav", duration=minutes * 60)
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    scale = 1 if sys.platform == "darwin" else 1024  # ru_maxrss: bytes on macOS, KiB on Linux
    print(json.dumps({"rss_mb": peak * scale / 1e6, "before_mb": before * scale / 1e6, "seconds": time.time() - t0, "cues": len(plan.cues)}))
""")


def measure_mix(minutes: float, workdir: Path) -> dict:
    """Mix `minutes` of narration in a fresh process; peak RSS, time, and what the output file holds."""
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"sine=f=190:d={minutes * 60}", "-af", "volume=0.25",
                    "-ar", "44100", "-ac", "1", str(workdir / "vo.wav")], check=True)
    probe = workdir / "probe.py"
    probe.write_text(_MEMORY_PROBE, encoding="utf-8")
    run = subprocess.run([sys.executable, str(probe), str(ROOT), str(workdir), str(minutes)], capture_output=True, text=True, check=True)
    stats = json.loads(run.stdout.strip().splitlines()[-1])
    info = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=sample_rate,channels,codec_name:format=duration",
                                      "-of", "json", str(workdir / "out.wav")], capture_output=True, text=True, check=True).stdout)
    stream = info["streams"][0]
    stats.update(duration=float(info["format"]["duration"]), sample_rate=int(stream["sample_rate"]), channels=int(stream["channels"]),
                 codec=stream["codec_name"])
    # effects and ambience are really in the file: compare a window with a cue against the narration alone
    a = am.decode(workdir / "out.wav")[int(60.7 * SR):int(61.2 * SR)]
    v = am.decode(workdir / "vo.wav")[int(60.7 * SR):int(61.2 * SR)]
    stats["bed_present"] = bool(float(np.abs(a - v).max()) > 1e-3)
    return stats


class TestMemoryStaysFlat(unittest.TestCase):
    def test_a_long_mix_needs_no_more_memory_than_a_short_one(self):
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            short, long_ = measure_mix(2.0, Path(d1)), measure_mix(12.0, Path(d2))
        for s in (short, long_):
            self.assertEqual((s["sample_rate"], s["channels"], s["codec"]), (SR, 2, "pcm_f32le"))
            self.assertTrue(s["bed_present"])
        self.assertAlmostEqual(long_["duration"], 720.0, delta=0.05)
        # the old mixer grew by ~0.22 GB per minute: 10 more minutes would be ~2.2 GB more
        self.assertLess(long_["rss_mb"] - short["rss_mb"], 150, (short, long_))


if __name__ == "__main__":
    unittest.main()


class TestSoundFailureIsShown(unittest.TestCase):
    """pakMap and Hybrid share _sound_failed_notice: a narration-only video is never announced as a plain success."""

    def _notice(self, result):
        import app as app_mod
        logs, shown = [], []
        fake = type("A", (), {"_append_log": lambda self, m: logs.append(m)})()
        with mock.patch.object(app_mod.messagebox, "showwarning", lambda title, msg: shown.append((title, msg))):
            said = app_mod.VideoGeneratorApp._sound_failed_notice(fake, "HYBRID", "Hybrid Map", result)
        return said, logs, shown

    def test_a_failed_sound_design_is_a_warning_with_the_reason(self):
        from pakmap.app_integration import PakmapResult
        said, logs, shown = self._notice(PakmapResult(True, [], Path("/x/final.mp4"), sound_failed="not enough memory to mix the sound (MemoryError)"))
        self.assertTrue(said)
        self.assertIn("sound design failed. The video contains narration only", shown[0][1])
        self.assertIn("MemoryError", shown[0][1])
        self.assertIn("without sound design", shown[0][0])
        self.assertTrue(any("WARNING" in m and "MemoryError" in m for m in logs))

    def test_a_good_run_shows_nothing_extra(self):
        from pakmap.app_integration import PakmapResult
        self.assertEqual(self._notice(PakmapResult(True, [], Path("/x/final.mp4"))), (False, [], []))
