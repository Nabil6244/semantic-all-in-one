"""The Weather password (weather/lock.py): only a hash is kept, the switch alone (or a hand-edited settings.json) does not unlock
Weather, and a new password locks it again."""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from weather import app_section, lock


class Lock(unittest.TestCase):
    def setUp(self):
        p = mock.patch.object(lock, "UNLOCK_HASH", lock.hash_password("open sesame"))
        p.start()
        self.addCleanup(p.stop)

    def test_the_right_password_and_only_it(self):
        self.assertTrue(lock.check("open sesame"))
        for bad in ("Open sesame", "", None, "open sesame "):
            self.assertFalse(lock.check(bad))

    def test_weather_is_on_only_with_the_switch_and_the_token(self):
        self.assertFalse(app_section.enabled({"weather_enabled": True}))                       # edited by hand
        self.assertFalse(app_section.enabled({"weather_enabled": True, "weather_unlock": "x" * 32}))
        self.assertFalse(app_section.enabled({"weather_unlock": lock.token()}))               # switch off
        self.assertTrue(app_section.enabled({"weather_enabled": True, "weather_unlock": lock.token()}))

    def test_a_new_password_locks_it_again(self):
        settings = {"weather_enabled": True, "weather_unlock": lock.token()}
        with mock.patch.object(lock, "UNLOCK_HASH", lock.hash_password("another one")):
            self.assertFalse(app_section.enabled(settings))

    def test_no_password_set_means_locked(self):
        with mock.patch.object(lock, "UNLOCK_HASH", ""):
            self.assertFalse(lock.check(""))
            self.assertFalse(app_section.enabled({"weather_enabled": True, "weather_unlock": ""}))

    def test_set_password_writes_only_the_hash(self):
        f = Path(tempfile.mkdtemp()) / "lock.py"
        f.write_text(Path(lock.__file__).read_text(encoding="utf-8"), encoding="utf-8")
        lock.set_password("hunter2!", f)
        text = f.read_text(encoding="utf-8")
        self.assertIn(f'UNLOCK_HASH = "{lock.hash_password("hunter2!")}"', text)
        self.assertNotIn("hunter2!", text)


if __name__ == "__main__":
    unittest.main()
