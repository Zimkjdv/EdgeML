"""Per-process LRU of trusted runtimes; catalogs remain the access authority."""
from collections import OrderedDict
from concurrent.futures import Future
from dataclasses import dataclass
import json
from threading import BoundedSemaphore, RLock

from app.domain.errors import ModelNotFoundError, PredictionValidationError, WorkloadBusyError
from app.domain.optimization import PredictorProvider
from app.domain.schemas import ModelManifest
from app.infrastructure.file_lock import child_path
from app.predictors.base import BasePredictor


class SynchronizedPredictor(BasePredictor):
    """Plugins need not promise thread-safe predict/transform implementations."""
    def __init__(self, delegate: BasePredictor):
        self.delegate, self._lock, self._loaded = delegate, RLock(), False

    def load(self):
        with self._lock:
            if not self._loaded:
                self.delegate.load()
                self._loaded = True

    def predict(self, df):
        with self._lock:
            self.load()
            return self.delegate.predict(df)

    def predict_proba(self, df):
        with self._lock:
            self.load()
            return self.delegate.predict_proba(df)

    def explain(self, df):
        with self._lock:
            self.load()
            return self.delegate.explain(df)

    def metadata(self):
        return self.delegate.metadata()


@dataclass
class PendingLoad:
    model_id: str
    future: Future
    retain: bool = True


class CachedPredictorProvider:
    def __init__(self, factory: PredictorProvider, max_entries=4, max_artifact_bytes=256 * 1024 * 1024, max_loads=2):
        self.factory, self.max_entries, self.max_artifact_bytes = factory, max_entries, max_artifact_bytes
        self._entries = OrderedDict()
        self._loading = {}
        self._guard = RLock()
        self._load_slots = BoundedSemaphore(max_loads)
        self._bytes = 0

    @staticmethod
    def fingerprint(manifest: ModelManifest):
        stamps, size = [], 0
        for artifact in filter(None, (manifest.artifact, manifest.preprocess_artifact)):
            path = child_path(manifest.model_path, artifact)
            try:
                stat = path.stat()
                if not path.is_file(): raise FileNotFoundError(path)
            except FileNotFoundError as exc:
                raise ModelNotFoundError('Model artifact is missing; cached results cannot be used.') from exc
            stamps.append((str(path), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_ino))
            size += stat.st_size
        metadata = json.dumps(manifest.model_dump(mode='json'), sort_keys=True, ensure_ascii=False)
        return (manifest.id, metadata, tuple(stamps)), size

    def invalidate(self, model_id: str):
        with self._guard:
            for key in list(self._entries):
                if key[0] == model_id:
                    _, size = self._entries.pop(key)
                    self._bytes -= size
            for pending in self._loading.values():
                if pending.model_id == model_id: pending.retain = False

    def info(self):
        with self._guard:
            return {'entries': len(self._entries), 'artifact_bytes': self._bytes, 'loading': len(self._loading)}

    def create(self, manifest: ModelManifest) -> BasePredictor:
        if self.max_entries == 0:
            return self.factory.create(manifest)
        try:
            key, size = self.fingerprint(manifest)
        except Exception:
            self.invalidate(manifest.id)
            raise
        with self._guard:
            # Only one retained identity per model, including metadata renames.
            for old_key, old_pending in self._loading.items():
                if old_key[0] == manifest.id and old_key != key: old_pending.retain = False
            for old in list(self._entries):
                if old[0] == manifest.id and old != key:
                    _, old_size = self._entries.pop(old)
                    self._bytes -= old_size
            if key in self._entries:
                self._entries.move_to_end(key)
                return self._entries[key][0]
            pending = self._loading.get(key)
            owner = pending is None or not pending.retain
            if owner:
                if not self._load_slots.acquire(blocking=False):
                    raise WorkloadBusyError('Model loading capacity is busy. Retry this request shortly.')
                pending = PendingLoad(manifest.id, Future())
                self._loading[key] = pending
        if not owner:
            result = pending.future.result()
            if self.fingerprint(manifest)[0] != key:
                raise PredictionValidationError('Model artifacts changed while loading; retry the request.')
            return result
        try:
            runtime = SynchronizedPredictor(self.factory.create(manifest))
            runtime.load()
            if self.fingerprint(manifest)[0] != key:
                raise PredictionValidationError('Model artifacts changed while loading; retry the request.')
            with self._guard:
                if pending.retain and size <= self.max_artifact_bytes:
                    self._entries[key] = (runtime, size)
                    self._bytes += size
                    while len(self._entries) > self.max_entries or self._bytes > self.max_artifact_bytes:
                        _, (_, removed_size) = self._entries.popitem(last=False)
                        self._bytes -= removed_size
                pending.future.set_result(runtime)
            return runtime
        except BaseException as exc:
            pending.future.set_exception(exc)
            raise
        finally:
            with self._guard:
                if self._loading.get(key) is pending: self._loading.pop(key)
                self._load_slots.release()
