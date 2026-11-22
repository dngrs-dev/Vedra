"""Runtime configuration for the backend."""
from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import PositiveInt
from pydantic_settings import BaseSettings

CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"
# Analysis dates use the task's Polish civil time zone.
ANALYSIS_TIMEZONE = "Europe/Warsaw"
# The integrated live smoke test ran two independent analyses concurrently within the 30 s budget.
DEFAULT_ANALYSIS_CONCURRENCY = 2


def analysis_today() -> date:
    return datetime.now(ZoneInfo(ANALYSIS_TIMEZONE)).date()


def years_before(day: date, years: int) -> date:
    """Return the calendar anniversary, using the last day of a shorter month."""
    target_year = day.year - years
    return day.replace(year=target_year, day=min(day.day, monthrange(target_year, day.month)[1]))


class Settings(BaseSettings):
    """Read settings from the environment, with defaults from README.md §5."""

    geo_provider: Literal["real", "fake", "fixtures"] = "real"
    egib_snapshot_path: Path | None = None
    analysis_concurrency: PositiveInt = DEFAULT_ANALYSIS_CONCURRENCY
    cache_dir: Path = Path(".cache")
    db_path: Path = Path("data/vedra.sqlite")
    cors_origins: str = "http://localhost:5173"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    # Optional AI commentary on the "what if" scenarios; without a key it falls back to rules.
    ai_enabled: bool = True
    ai_provider: Literal["gemini", "anthropic"] = "gemini"
    gemini_api_key: str | None = None  # GEMINI_API_KEY (Google AI Studio, free tier available)
    gemini_model: str = "gemini-3.5-flash"  # stable, free tier, ~5 s per answer (checked 2026-11-22)
    gemini_fallback_model: str = "gemini-3.5-flash-lite"  # used when the main model is overloaded
    anthropic_model: str = "claude-opus-5-5"  # used with AI_PROVIDER=anthropic and ANTHROPIC_API_KEY

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
