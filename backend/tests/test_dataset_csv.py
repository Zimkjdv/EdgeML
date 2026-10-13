import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_dataset_service
from app.domain.errors import PredictionValidationError
from app.main import create_app
from app.services.dataset_service import DatasetService


@pytest.fixture
def dataset_client(tmp_path):
    service = DatasetService(tmp_path / 'datasets')
    app = create_app()
    app.dependency_overrides[get_dataset_service] = lambda: service
    with TestClient(app) as client:
        yield service, client


@pytest.mark.parametrize('content', [
    b'', b'\xef\xbb\xbf', b' \r\n', b'x,y\n', b'x,x\n1,2\n',
    b',y\n1,2\n', b'x, \n1,2\n', b'x,y\n1,2,3\n', b'x,y\n1\n',
    b'x,y\n"open,2\n', b'x,y\nwrong"quote,2\n', b'x\n\xff\n',
    b'x\n1\ninf\n', b'x\n-Infinity\n', b'x\x00,y\n1,2\n',
])
def test_invalid_upload_is_422_and_preserves_existing_files(dataset_client, content):
    service, client = dataset_client
    existing = service.upload('existing.csv', b'x,y\n1,2\n')
    before = {p.name: p.read_bytes() for p in service._root.iterdir()}
    response = client.post('/api/datasets', files={'file': ('invalid.csv', content, 'text/csv')})
    assert response.status_code == 422, response.text
    assert isinstance(response.json()['detail'], str)
    assert {p.name: p.read_bytes() for p in service._root.iterdir()} == before
    assert service.get(existing.id).row_count == 1


@pytest.mark.parametrize('encoding', ['utf-8-sig', 'utf-8', 'cp950', 'big5'])
def test_chinese_encodings_quoted_multiline_and_missing_values(dataset_client, encoding):
    service, client = dataset_client
    content = '數值,紙種\n1,"中文\n多行"\n,乙\n3,\n'.encode(encoding)
    response = client.post('/api/datasets', files={'file': ('中文.csv', content, 'text/csv')})
    assert response.status_code == 201, response.text
    result = response.json()
    assert result['column_count'] == 2 and result['row_count'] == 3
    profiles = {p['name']: p for p in result['columns']}
    assert profiles['數值']['missing_count'] == profiles['紙種']['missing_count'] == 1
    assert profiles['數值']['mean'] == pytest.approx(2)
    assert profiles['數值']['std'] == pytest.approx(np.sqrt(2))
    assert service.frame(result['id']).iloc[0]['紙種'] == '中文\n多行'
    # Strict JSON must work both for the HTTP response and persisted metadata.
    json.dumps(result, allow_nan=False)
    json.loads((service._root / f"{result['id']}.json").read_text(encoding='utf-8'),
               parse_constant=lambda value: pytest.fail(f'Invalid JSON number: {value}'))


def test_zero_iqr_counts_values_outside_the_equal_quartile():
    profiles = DatasetService._profile(pd.DataFrame({'constant': [1] * 10, 'spike': [1] * 9 + [100]}))
    assert profiles[0].outlier_count == 0
    assert profiles[1].outlier_count == 1


def test_finite_extreme_statistics_and_all_missing_are_json_safe():
    profiles = DatasetService._profile(pd.DataFrame({
        'large': [1e308, 1e308], 'opposite': [-1.79e308, 1.79e308], 'missing': [np.nan, np.nan],
    }))
    assert profiles[0].mean == pytest.approx(1e308)
    assert profiles[0].median == pytest.approx(1e308)
    assert profiles[0].std == 0
    assert profiles[1].mean == 0 and profiles[1].std is None
    assert profiles[2].minimum is None and profiles[2].std is None
    json.dumps([p.model_dump() for p in profiles], allow_nan=False)


def test_metadata_write_failure_removes_only_the_new_csv(tmp_path, monkeypatch):
    service = DatasetService(tmp_path)
    existing = service.upload('existing.csv', b'x\n1\n')
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    def fail(*args): raise OSError('simulated storage failure')
    monkeypatch.setattr('app.services.dataset_service.write_json_atomic', fail)
    with pytest.raises(OSError):
        service.upload('new.csv', b'x\n2\n')
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before
    assert service.get(existing.id).row_count == 1


def test_partial_csv_write_failure_is_cleaned(tmp_path, monkeypatch):
    service = DatasetService(tmp_path)
    original = Path.open
    class BrokenStream:
        def __init__(self, stream): self.stream = stream
        def __enter__(self): return self
        def __exit__(self, *args): self.stream.close()
        def write(self, content):
            self.stream.write(content[:2])
            raise OSError('simulated partial write')
    def open_file(path, mode='r', *args, **kwargs):
        stream = original(path, mode, *args, **kwargs)
        return BrokenStream(stream) if mode == 'xb' else stream
    monkeypatch.setattr(Path, 'open', open_file)
    with pytest.raises(OSError):
        service.upload('new.csv', b'x\n2\n')
    assert list(tmp_path.iterdir()) == []
