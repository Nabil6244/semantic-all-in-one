"""The bundled static ffmpeg has no certificate store: https sources get certifi's bundle, local files get nothing."""
import unittest
from pathlib import Path

from providers.media_clip import ffmpeg_clip as fc


class TlsOptions(unittest.TestCase):
    def test_web_sources_are_checked_against_certifi(self):
        import certifi

        for url in ("https://images-assets.nasa.gov/video/x/x~small.mp4", "http://images-assets.nasa.gov/video/x/x~orig.mp4"):
            self.assertEqual(fc._tls_opts(url), ["-ca_file", certifi.where()])

    def test_local_files_get_no_tls_options(self):
        self.assertEqual(fc._tls_opts(Path("/tmp/clip.mp4")), [])
        self.assertEqual(fc._tls_opts("C:\\clips\\a.mp4"), [])


if __name__ == "__main__":
    unittest.main()
