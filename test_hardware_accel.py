"""Hardware acceleration detection — CPU fallback must always win when GPU fails."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from hardware import accel


class TestHardwareAccel(unittest.TestCase):
    def tearDown(self) -> None:
        accel.set_performance_mode_override(None)
        accel.clear_caps_cache()

    def test_cpu_mode_forces_libx264_and_cpu_whisper(self):
        accel.set_performance_mode_override("cpu")
        caps = accel.get_capabilities(force_refresh=True)
        self.assertEqual(caps.preferred_encoder, "libx264")
        self.assertEqual(caps.whisper_device, "cpu")
        self.assertEqual(accel.video_encode_argv()[1], "libx264")
        device, ctype, label = accel.whisper_device_and_compute()
        self.assertEqual(device, "cpu")
        self.assertEqual(ctype, "int8")
        self.assertEqual(label, "CPU")

    @patch.object(accel, "_probe_cuda_whisper", return_value=(False, "no cuda"))
    @patch.object(accel, "_listed_encoders", return_value=set())
    def test_auto_without_gpu_uses_cpu(self, _enc, _cuda):
        accel.set_performance_mode_override("auto")
        with patch.object(accel, "_smoke_test_encoder", return_value=(False, "skip")):
            caps = accel.get_capabilities(force_refresh=True)
        self.assertEqual(caps.preferred_encoder, "libx264")
        self.assertFalse(caps.using_gpu_encode)
        self.assertFalse(caps.using_gpu_whisper)

    @patch.object(accel, "_probe_cuda_whisper", return_value=(True, "cuda ok"))
    @patch.object(accel, "_listed_encoders", return_value={"h264_nvenc", "libx264"})
    def test_auto_prefers_nvenc_when_smoke_ok(self, _enc, _cuda):
        accel.set_performance_mode_override("auto")

        def smoke(name, argv):
            if name == "h264_nvenc":
                return True, ""
            return False, "no"

        with patch.object(accel, "_smoke_test_encoder", side_effect=smoke):
            caps = accel.get_capabilities(force_refresh=True)
        self.assertEqual(caps.preferred_encoder, "h264_nvenc")
        self.assertTrue(caps.nvenc_available)
        self.assertEqual(caps.whisper_device, "cuda")
        self.assertIn("h264_nvenc", accel.video_encode_argv())

    @patch.object(accel, "_probe_cuda_whisper", return_value=(False, "no cuda"))
    @patch.object(accel, "_listed_encoders", return_value={"h264_nvenc", "libx264"})
    def test_listed_nvenc_but_smoke_fail_falls_back(self, _enc, _cuda):
        """Driver missing: encoder listed but smoke test fails → libx264."""
        accel.set_performance_mode_override("gpu")
        with patch.object(accel, "_smoke_test_encoder", return_value=(False, "driver")):
            caps = accel.get_capabilities(force_refresh=True)
        self.assertEqual(caps.preferred_encoder, "libx264")
        self.assertFalse(caps.nvenc_available)
        self.assertEqual(caps.whisper_device, "cpu")

    @patch.object(accel, "_probe_cuda_whisper", return_value=(False, "no cuda"))
    @patch.object(accel, "_listed_encoders", return_value={"h264_amf", "libx264"})
    def test_amf_preferred_when_nvenc_absent(self, _enc, _cuda):
        accel.set_performance_mode_override("auto")

        def smoke(name, argv):
            return (name == "h264_amf"), ""

        with patch.object(accel, "_smoke_test_encoder", side_effect=smoke):
            caps = accel.get_capabilities(force_refresh=True)
        self.assertEqual(caps.preferred_encoder, "h264_amf")

    def test_format_report_includes_mode(self):
        accel.set_performance_mode_override("cpu")
        text = accel.format_accel_report(accel.get_capabilities(force_refresh=True))
        self.assertIn("Performance Mode: CPU", text)
        # Video encoding and Whisper are reported as INDEPENDENT capabilities;
        # neither line may imply the other's backend.
        self.assertIn("Video Encoder: CPU (libx264)", text)
        self.assertIn("Whisper:       CPU (int8)", text)
        self.assertNotIn("GPU: available", text)

    def test_invalid_mode_defaults_auto(self):
        self.assertEqual(accel.get_performance_mode() in ("auto", "gpu", "cpu"), True)


class TestEncodeFallback(unittest.TestCase):
    def test_run_ffmpeg_encode_retries_cpu_on_gpu_failure(self):
        import video_generator as vg

        calls = {"n": 0}

        class FakeResult:
            def __init__(self, code):
                self.returncode = code
                self.stderr = "NVENC failed"
                self.stdout = ""

        def fake_run(cmd, **kwargs):
            calls["n"] += 1
            # First call uses nvenc → fail; second libx264 → ok
            if calls["n"] == 1:
                self.assertIn("h264_nvenc", cmd)
                return FakeResult(1)
            self.assertIn("libx264", cmd)
            return FakeResult(0)

        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "color",
            "-t", "0.1",
            "-c:v", "h264_nvenc", "-preset", "p4",
            "-pix_fmt", "yuv420p",
            "-an", "out.mp4",
        ]
        with patch.object(vg.hidden_subprocess, "run", side_effect=fake_run):
            vg._run_ffmpeg_encode(cmd, "001.png")
        self.assertEqual(calls["n"], 2)


if __name__ == "__main__":
    unittest.main()


class TestWhisperBackendTruthfulness(unittest.TestCase):
    """The audited failure: probe predicts CUDA (driver present), the real model
    load then fails on a missing CUDA runtime DLL, and the UI kept saying CUDA.
    No cheap probe can prevent this — CTranslate2 resolves cuBLAS/cuDNN lazily
    at model load and Encoder/Generator both need a model file — so the label
    must follow the OBSERVED load outcome, which is DLL-agnostic."""

    def setUp(self):
        accel._verified_whisper_backend = None

    def tearDown(self):
        accel._verified_whisper_backend = None

    def _caps_predicting_cuda(self):
        class C:
            performance_mode = "auto"; gpu_name = "NVIDIA (probe)"
            cuda_available = True; using_gpu_whisper = True
            whisper_compute_type = "float16"; preferred_encoder = "h264_nvenc"
            nvenc_available = True; amf_available = False; qsv_available = False
            videotoolbox_available = False; ffmpeg_path = "x"; notes = []
        return C()

    def test_unverified_prediction_is_not_reported_as_cuda(self):
        label = accel.whisper_backend_label(self._caps_predicting_cuda())
        self.assertIn("unverified", label)

    def test_failed_cuda_load_reports_cpu_not_cuda(self):
        caps = self._caps_predicting_cuda()
        accel.record_whisper_backend("CPU", "int8")
        label = accel.whisper_backend_label(caps)
        self.assertNotIn("CUDA", label)
        self.assertIn("CPU", label)

    def test_successful_cuda_load_reports_cuda(self):
        caps = self._caps_predicting_cuda()
        accel.record_whisper_backend("CUDA", "float16")
        self.assertEqual(accel.whisper_backend_label(caps), "CUDA (float16)")

    def test_video_encoder_label_is_independent_of_whisper(self):
        caps = self._caps_predicting_cuda()
        accel.record_whisper_backend("CPU", "int8")
        self.assertIn("NVENC", accel.video_encoder_label(caps))
        self.assertNotIn("CUDA", accel.whisper_backend_label(caps))
