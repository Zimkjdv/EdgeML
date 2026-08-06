from app.domain.errors import UnsupportedFrameworkError
from app.domain.schemas import ModelManifest
from app.predictors.base import BasePredictor
from app.predictors.sklearn_predictor import SklearnPredictor


class PredictorFactory:
    _registry: dict[str, type[BasePredictor]] = {"sklearn": SklearnPredictor}

    def create(self, manifest: ModelManifest) -> BasePredictor:
        predictor_type = self._registry.get(manifest.framework.lower())
        if predictor_type is None:
            raise UnsupportedFrameworkError(
                f"Framework '{manifest.framework}' is not supported by this deployment."
            )
        return predictor_type(manifest)

