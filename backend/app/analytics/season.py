"""The statutory agricultural drought monitoring season."""
from __future__ import annotations

from datetime import date
from typing import Literal

from app.analytics.periods import PERIODS


def mode(analysis_date: date) -> Literal["in_season", "off_season"]:
    # The first and last days come from the annex to Dz.U. 2019 poz. 739 (periods.py).
    day = (analysis_date.month, analysis_date.day)
    return "in_season" if PERIODS[0][0] <= day <= PERIODS[-1][1] else "off_season"
