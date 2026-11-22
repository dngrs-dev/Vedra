"""Display formatting shared by the PDF renderers."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from app.config import ANALYSIS_TIMEZONE
from app.contracts.common import Range
from app.recommendations import texts_pl as text


def display_value(value) -> str:
    if value is None:
        return text.PDF_MISSING
    if isinstance(value, Range):
        estimate = display_value(value.mid)
        if value.low is not None and value.high is not None:
            return f"{estimate} ({display_value(value.low)}–{display_value(value.high)})"
        return estimate
    if isinstance(value, float):
        # Report formatting precision only. JSON retains the underlying values.
        return f"{value:.2f}".rstrip("0").rstrip(".").replace(".", ",")
    return str(value)


def source_time(value: datetime) -> str:
    return value.astimezone(ZoneInfo(ANALYSIS_TIMEZONE)).strftime("%Y-%m-%d %H:%M %Z")
