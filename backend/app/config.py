"""Runtime configuration for the backend."""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic_settings import BaseSettings

CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"
# Analysis dates use the task's Polish civil time zone.
ANALYSIS_TIMEZONE = "Europe/Warsaw"


def analysis_today() -> date:
    return datetime.now(ZoneInfo(ANALYSIS_TIMEZONE)).date()


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
