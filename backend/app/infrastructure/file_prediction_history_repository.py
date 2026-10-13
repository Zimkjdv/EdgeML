import heapq
import logging
import os
import shutil
import tempfile
from datetime import timezone
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError
from app.domain.schemas import PredictionHistoryRecord
from app.infrastructure.file_lock import FileLock


class FilePredictionHistoryRepository:
    def __init__(self, history_file: Path, max_records: int = 0) -> None:
        self._history_file = history_file
        self._lock = FileLock(history_file.with_suffix('.lock'))
        self._max_records = max_records
        self._logger = logging.getLogger('edgeml.history')

    def add(self, record: PredictionHistoryRecord) -> None:
        self._history_file.parent.mkdir(parents=True, exist_ok=True)
        payload = record.model_dump_json().encode('utf-8') + b'\n'
        with self._lock:
            self._repair_tail()
            with self._history_file.open('ab') as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            if self._max_records and len(self.list(self._max_records + 1)) > self._max_records:
                kept = self.list(self._max_records)
                archive = self._history_file.with_name(f'{self._history_file.name}.retention-{uuid4().hex}.jsonl')
                with self._history_file.open('rb') as source, archive.open('xb') as target:
                    shutil.copyfileobj(source, target)
                    target.flush(); os.fsync(target.fileno())
                self._replace([record.model_dump_json().encode() + b'\n' for record in reversed(kept)])

    @staticmethod
    def _key(record):
        date = record.created_at
        return (date.replace(tzinfo=timezone.utc) if date.tzinfo is None else date, record.id)

    def list(self, limit: int = 100, offset: int = 0) -> list[PredictionHistoryRecord]:
        if limit < 1 or offset < 0:
            raise ValueError('Invalid history pagination.')
        with self._lock:
            if not self._history_file.exists():
                return []
            try:
                records = heapq.nlargest(limit + offset, self._records(), key=self._key)
            except (ValidationError, ValueError, UnicodeError):
                self._repair()
                records = heapq.nlargest(limit + offset, self._records(), key=self._key)
            return records[offset:offset + limit]

    def _records(self):
        with self._history_file.open('rb') as stream:
            for line in stream:
                if line.strip():
                    yield PredictionHistoryRecord.model_validate_json(line)

    def _repair_tail(self):
        if not self._history_file.exists() or not self._history_file.stat().st_size:
            return
        with self._history_file.open('rb') as stream:
            stream.seek(-1, os.SEEK_END)
            if stream.read(1) == b'\n':
                return
            position = stream.tell()
            tail = b''
            while position:
                size = min(position, 8192); position -= size
                stream.seek(position)
                tail = stream.read(size) + tail
                if b'\n' in tail:
                    tail = tail.rsplit(b'\n', 1)[1]; break
        try:
            PredictionHistoryRecord.model_validate_json(tail)
        except (ValidationError, ValueError, UnicodeError):
            self._repair()
        else:
            with self._history_file.open('ab') as stream:
                stream.write(b'\n'); stream.flush(); os.fsync(stream.fileno())

    def _replace(self, lines):
        descriptor, temporary = tempfile.mkstemp(prefix='.history-', dir=self._history_file.parent)
        try:
            with os.fdopen(descriptor, 'wb') as stream:
                for line in lines: stream.write(line)
                stream.flush(); os.fsync(stream.fileno())
            os.replace(temporary, self._history_file)
        finally:
            Path(temporary).unlink(missing_ok=True)

    def _repair(self):
        # Archive original bytes before repair; errors never erase the evidence.
        archive = self._history_file.with_name(f'{self._history_file.name}.recovery-{uuid4().hex}.jsonl')
        with self._history_file.open('rb') as source, archive.open('xb') as target:
            shutil.copyfileobj(source, target)
            target.flush(); os.fsync(target.fileno())
        def valid_lines():
            with archive.open('rb') as stream:
                for line in stream:
                    try:
                        record = PredictionHistoryRecord.model_validate_json(line)
                    except (ValidationError, ValueError, UnicodeError):
                        continue
                    yield record.model_dump_json().encode('utf-8') + b'\n'
        self._replace(valid_lines())
        self._logger.warning('Repaired prediction history; original retained at %s', archive.name)
