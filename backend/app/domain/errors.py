class ModelNotFoundError(Exception):
    pass


class PredictionValidationError(Exception):
    pass


class UnsupportedFrameworkError(Exception):
    pass


class PredictionHistoryError(Exception):
    """Prediction cannot be returned unless its audit metadata is durable."""


class WorkloadBusyError(Exception):
    """Bounded work admission was exhausted; callers may retry later."""

