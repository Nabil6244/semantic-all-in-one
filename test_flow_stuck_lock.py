"""Stop must end the wait for the Flow GENERATE lock (a stuck earlier job used to hold it for hours)."""
import threading
import time
import unittest

from providers.flow import provider as flow_provider


class AcquireGenerateLockTests(unittest.TestCase):
    def test_free_lock_is_taken(self):
        self.assertTrue(flow_provider._acquire_generate_lock(1.0, lambda: False))
        flow_provider._ENGINE_GENERATE_LOCK.release()

    def test_stop_ends_the_wait_behind_a_stuck_job(self):
        flow_provider._ENGINE_GENERATE_LOCK.acquire()   # the stuck earlier job
        try:
            stop = threading.Event()
            threading.Timer(0.2, stop.set).start()
            t0 = time.monotonic()
            got = flow_provider._acquire_generate_lock(3600.0, stop.is_set)
            self.assertIsNone(got)
            self.assertLess(time.monotonic() - t0, 3.0)
        finally:
            flow_provider._ENGINE_GENERATE_LOCK.release()

    def test_timeout_still_reported(self):
        flow_provider._ENGINE_GENERATE_LOCK.acquire()
        try:
            self.assertFalse(flow_provider._acquire_generate_lock(0.3, None))
        finally:
            flow_provider._ENGINE_GENERATE_LOCK.release()


if __name__ == "__main__":
    unittest.main()
