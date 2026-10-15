import asyncio
from threading import Event
import httpx
import pytest

from app.api.dependencies import get_dataset_service
from app.domain.errors import WorkloadBusyError
from app.services.dataset_ingestion import DatasetIngestion
from app.main import create_app


def test_cancelled_upload_keeps_capacity_until_worker_finishes():
    async def scenario():
        ingestion = DatasetIngestion(1); entered, release, finished = Event(), Event(), Event()
        class Datasets:
            def upload(self, *_):
                entered.set()
                try:
                    assert release.wait(5)
                    return 'saved'
                finally: finished.set()
        try:
            task = asyncio.create_task(ingestion.upload(Datasets(),'a.csv',b'x\n1'))
            assert await asyncio.to_thread(entered.wait, 5)
            task.cancel()
            with pytest.raises(asyncio.CancelledError): await task
            with pytest.raises(WorkloadBusyError): await ingestion.upload(Datasets(),'b.csv',b'x\n1')
            release.set(); assert await asyncio.to_thread(finished.wait, 5)
            # Future callbacks may run immediately after the worker's finally.
            await asyncio.sleep(0)
        finally: release.set(); ingestion.close()
    asyncio.run(scenario())


def test_profile_upload_does_not_block_health_and_overload_returns_503():
    async def scenario():
        app = create_app(); app.state.dataset_ingestion.close(); app.state.dataset_ingestion = DatasetIngestion(1)
        entered, release = Event(), Event()
        class Datasets:
            def upload(self,*_):
                entered.set(); assert release.wait(5)
                raise ValueError('synthetic profile failure')
        app.dependency_overrides[get_dataset_service] = lambda: Datasets()
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app,raise_app_exceptions=False), base_url='http://test') as client:
                first = asyncio.create_task(client.post('/api/datasets',files={'file':('a.csv',b'x\n1','text/csv')}))
                assert await asyncio.to_thread(entered.wait, 5)
                health = await asyncio.wait_for(client.get('/health/live'), 1)
                assert health.status_code == 200
                busy = await asyncio.wait_for(client.post('/api/datasets',files={'file':('b.csv',b'x\n1','text/csv')}),1)
                assert busy.status_code == 503 and busy.headers['retry-after'] == '1'
                release.set(); assert (await first).status_code == 500
                health = await client.get('/health/live'); assert health.status_code == 200
        finally: release.set(); app.state.dataset_ingestion.close()
    asyncio.run(scenario())
