from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="EDGEML_", case_sensitive=False)

    models_root: Path = Path(__file__).resolve().parents[2] / "ml_models"
    datasets_root: Path = Path(__file__).resolve().parents[2] / "data" / "datasets"
    trained_models_root: Path = Path(__file__).resolve().parents[2] / "trained_models"
    training_jobs_root: Path = Path(__file__).resolve().parents[2] / "training_jobs"
    prediction_history_file: Path = Path(__file__).resolve().parents[2] / "data" / "prediction_history.jsonl"
    api_tokens_database: Path = Path(__file__).resolve().parents[2] / "data" / "api_tokens.sqlite3"
    model_registry_file: Path = Path(__file__).resolve().parents[2] / "data" / "model_registry.json"
    queue_backend: str = "redis"
    redis_url: str = "redis://localhost:6379/0"
    training_queue_name: str = "edgeml:training"
    training_max_attempts: int = Field(default=3, ge=1, le=10)
    training_retry_backoff_seconds: float = Field(default=2.0, ge=0, le=300)
    training_retry_backoff_max_seconds: float = Field(default=60.0, ge=0, le=3600)
    max_upload_bytes: int = 5 * 1024 * 1024
    max_json_records: int = Field(default=10_000, ge=1, le=100_000)
    max_json_columns: int = Field(default=256, ge=1, le=10_000)
    max_json_value_chars: int = Field(default=10_000, ge=1, le=1_000_000)
    max_json_body_bytes: int = Field(default=10 * 1024 * 1024, ge=1, le=100 * 1024 * 1024)
    api_token: str | None = None
    web_username: str = "admin"
    web_password: str | None = Field(default=None, repr=False)
    web_session_seconds: int = Field(default=28800, ge=300, le=86400)
    web_cookie_secure: bool = False
    web_allowed_origins: list[str] = ["http://localhost:5173", "http://localhost:5180"]
    optimization_population: int = Field(default=256, ge=16, le=512)
    optimization_iterations: int = Field(default=12, ge=1, le=20)
    importance_max_samples: int = Field(default=500, ge=2, le=2000)
    importance_repeats: int = Field(default=3, ge=1, le=10)


@lru_cache
def get_settings() -> Settings:
    return Settings()
