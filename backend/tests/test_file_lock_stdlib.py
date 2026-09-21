"""Portable lock checks; also runnable without the project's ML dependencies."""
import multiprocessing
import tempfile
import unittest
from pathlib import Path
from app.infrastructure.file_lock import FileLock


def _hold(path, ready):
    with FileLock(Path(path)):
        ready.send('locked')
        ready.recv()


class FileLockTests(unittest.TestCase):
    def test_nested_lock_and_distinct_instance_exclusion(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'lock'
            lock = FileLock(path)
            with lock:
                with lock:
                    with self.assertRaises(TimeoutError):
                        with FileLock(path, timeout=0):
                            pass
            with FileLock(path, timeout=0):
                pass

    def test_process_crash_releases_lock(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'lock'
            context = multiprocessing.get_context('spawn')
            parent, child = context.Pipe()
            process = context.Process(target=_hold, args=(str(path), child))
            process.start()
            try:
                self.assertTrue(parent.poll(15))
                self.assertEqual(parent.recv(), 'locked')
                with self.assertRaises(TimeoutError):
                    with FileLock(path, timeout=0):
                        pass
                process.terminate(); process.join(10)
                self.assertFalse(process.is_alive())
                with FileLock(path, timeout=0):
                    pass
            finally:
                if process.is_alive():
                    process.terminate(); process.join(10)
                parent.close(); child.close()
