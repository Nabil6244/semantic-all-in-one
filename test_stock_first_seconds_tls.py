"""Real-log bug (#021-#023): "keep only the first 30 s" of a big stock clip failed with "certificate verify failed", because
the bundled ffmpeg has no certificate store and this command did not pass the trusted certificates (other ffmpeg paths did)."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from providers.stock import downloader


class _Proc:
    stderr = None

    def __init__(self, cmd):
        self.cmd = cmd
        Path(cmd[-1]).write_bytes(b"\0" * 2048)   # the "-y <tmp>" output

    def poll(self):
        return 0

    @property
    def returncode(self):
        return 0

    def wait(self, timeout=None):
        return 0


class FirstSecondsTls(unittest.TestCase):
    def _run(self, url):
        seen = {}

        def popen(cmd, **kw):
            seen["cmd"] = cmd
            return _Proc(cmd)

        with tempfile.TemporaryDirectory() as d, mock.patch("providers.hidden_subprocess.popen", side_effect=popen):
            try:
                downloader.download_first_seconds(SimpleNamespace(url=url), Path(d), "7", 3.0)
            except Exception:
                pass   # only the command matters here
        return seen["cmd"]

    def test_https_passes_the_trusted_certificates_before_the_input(self):
        cmd = self._run("https://videos.pexels.com/video-files/1/1_1920_1080_24fps.mp4")
        self.assertIn("-ca_file", cmd)
        self.assertLess(cmd.index("-ca_file"), cmd.index("-i"))
        self.assertTrue(Path(cmd[cmd.index("-ca_file") + 1]).is_file())

    def test_local_file_gets_no_tls_option(self):
        cmd = self._run("/tmp/clip.mp4")
        self.assertNotIn("-ca_file", cmd)

    def test_plain_http_gets_no_tls_option(self):
        # ffmpeg answers "Option ca_file not found" for a plain http server (test_uhd_footage's local server caught this)
        cmd = self._run("http://127.0.0.1:8000/long.mp4")
        self.assertNotIn("-ca_file", cmd)


if __name__ == "__main__":
    unittest.main()
