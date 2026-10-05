import asyncio
from threading import Event

import httpx

from app.api.dependencies import get_prediction_service
from app.domain.schemas import PredictionOutput
from app.main import create_app


def test_health_and_models_respond_while_csv_inference_is_running():
    started, release = Event(), Event()

    class SlowPredictionService:
        def predict_csv(self, **kwargs):
            started.set()
            assert release.wait(5), 'inference was not released'
            return PredictionOutput(filename='result.csv', csv_content=b'x,prediction\n1,2\n')
        def list_models(self): return []

    async def exercise():
        app = create_app()
        app.dependency_overrides[get_prediction_service] = SlowPredictionService
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            prediction = asyncio.create_task(client.post('/api/predict', data={'model_id': 'test'},
                files={'file': ('data.csv', b'x\n1\n', 'text/csv')}))
            try:
                assert await asyncio.to_thread(started.wait, 2)
                assert not prediction.done()
                health = await asyncio.wait_for(client.get('/health/live'), timeout=1)
                models = await asyncio.wait_for(client.get('/api/models'), timeout=1)
                assert health.status_code == models.status_code == 200
                assert not prediction.done()
            finally:
                release.set()
                result = await prediction
            assert result.status_code == 200
            assert result.content == b'x,prediction\n1,2\n'
    asyncio.run(exercise())
