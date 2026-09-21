"""Reentrant thread/process lock for local shared volumes (Windows and Linux)."""
import os
import time
from pathlib import Path
from threading import RLock


class FileLock:
    def __init__(self, path: Path, timeout: float = 30):
        self.path, self.timeout = path, timeout
        self._thread_lock = RLock()
        self._depth = 0
        self._stream = None

    def __enter__(self):
        if not self._thread_lock.acquire(timeout=self.timeout):
            raise TimeoutError(f'File lock is busy: {self.path.name}')
        try:
            if self._depth == 0:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                stream = self.path.open('a+b')
                try:
                    if os.name == 'nt' and self.path.stat().st_size == 0:
                        stream.write(b'0'); stream.flush()
                    deadline = time.monotonic() + self.timeout
                    while True:
                        try:
                            if os.name == 'nt':
                                import msvcrt
                                stream.seek(0)
                                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                            else:
                                import fcntl
                                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                            break
                        except OSError as exc:
                            if time.monotonic() >= deadline:
                                raise TimeoutError(f'File lock is busy: {self.path.name}') from exc
                            time.sleep(0.02)
                    self._stream = stream
                except BaseException:
                    stream.close()
                    raise
            self._depth += 1
            return self
        except BaseException:
            self._thread_lock.release()
            raise

    def __exit__(self, *_):
        try:
            self._depth -= 1
            if self._depth == 0:
                try:
                    if os.name == 'nt':
                        import msvcrt
                        self._stream.seek(0)
                        msvcrt.locking(self._stream.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(self._stream.fileno(), fcntl.LOCK_UN)
                finally:
                    self._stream.close()
                    self._stream = None
        finally:
            self._thread_lock.release()


def child_path(root: Path, identifier: str) -> Path:
    """Identifiers are path components, never user-controlled paths."""
    from app.domain.errors import ModelNotFoundError
    if not identifier or identifier in {'.', '..'} or any(c in identifier for c in '/\\:'):
        raise ModelNotFoundError('Invalid model identifier or package name.')
    root = root.resolve()
    child = root / identifier
    if child.is_symlink() or child.resolve().parent != root:
        raise ModelNotFoundError('Model path is outside the configured root.')
    return child
