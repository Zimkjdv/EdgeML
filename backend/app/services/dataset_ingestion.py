"""Per-application bounded profiling; cancellation does not free a running slot."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from threading import BoundedSemaphore, Lock

from app.domain.errors import WorkloadBusyError
from app.services.dataset_service import DatasetService


class DatasetIngestion:
    def __init__(self, concurrency: int = 2):
        self._slots = BoundedSemaphore(concurrency)
        self._pool = ThreadPoolExecutor(max_workers=concurrency, thread_name_prefix='edgeml-profile')
        self._guard, self._closed = Lock(), False

    async def upload(self, datasets: DatasetService, filename: str, content: bytes):
        with self._guard:
            if self._closed or not self._slots.acquire(blocking=False):
                raise WorkloadBusyError('Dataset profiling capacity is busy. Retry the upload shortly.')
            try:
                future = self._pool.submit(partial(datasets.upload, filename, content))
            except BaseException:
                self._slots.release()
                raise
            future.add_done_callback(lambda _: self._slots.release())
        wrapped = asyncio.wrap_future(future)
        # A disconnected request may leave work running. Drain its eventual
        # exception, and keep admission until the underlying worker terminates.
        wrapped.add_done_callback(lambda done: None if done.cancelled() else done.exception())
        return await asyncio.shield(wrapped)

    def close(self):
        with self._guard:
            if not self._closed:
                self._closed = True
                self._pool.shutdown(wait=False, cancel_futures=True)
