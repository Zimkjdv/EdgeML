from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="EDGEML_", case_sensitive=False)

    models_root: Path = Path(__file__).resolve().parents[2] / "ml_models"
    datasets_root: Path = Path(__file__).resolve().parents[2] / "data" / "datasets"
    trained_models_root: Path = Path(__file__).resolve().parents[2] / "trained_models"
    training_jobs_root: Path = Path(__file__).resolve().parents[2] / "training_jobs"
    prediction_history_file: Path = Path(__file__).resolve().parents[2] / "data" / "prediction_history.jsonl"
    model_registry_file: Path = Path(__file__).resolve().parents[2] / "data" / "model_registry.json"
    queue_backend: str = "redis"
    redis_url: str = "redis://localhost:6379/0"
    training_queue_name: str = "edgeml:training"
    max_upload_bytes: int = 5 * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
