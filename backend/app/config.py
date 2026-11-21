"""Runtime configuration for the backend."""
from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings

CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"


class Settings(BaseSettings):
    """Read settings from the environment, with defaults from README.md §5."""

    geo_provider: Literal["real", "fake", "fixtures"] = "real"
    cache_dir: Path = Path(".cache")
    db_path: Path = Path("data/vedra.sqlite")
    cors_origins: str = "http://localhost:5173"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
