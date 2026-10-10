from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BALLSPEED_", env_file=".env", extra="ignore")

    data_dir: Path | None = None
    max_upload_mb: int = 500
    ttl_minutes: int = 60
    min_fps_auto: float = 100.0
    min_fps_manual: float = 24.0
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    detector: Literal["classical", "yolo"] = "classical"
    yolo_weights: Path | None = None
    static_dir: Path | None = None


settings = Settings()
