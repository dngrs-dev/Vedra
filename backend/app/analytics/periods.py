"""The six-decade periods in the KBW regulation."""
from __future__ import annotations

from datetime import date

from app.analytics.models import Period

# Annex to Dz.U. 2019 poz. 739, table header, in chronological order.
# https://eli.gov.pl/api/acts/DU/2019/739/text.pdf#page=2
PERIODS = (
    ((3, 21), (5, 20)),
    ((4, 1), (5, 31)),
    ((4, 11), (6, 10)),
    ((4, 21), (6, 20)),
    ((5, 1), (6, 30)),
    ((5, 11), (7, 10)),
    ((5, 21), (7, 20)),
    ((6, 1), (7, 31)),
    ((6, 11), (8, 10)),
    ((6, 21), (8, 20)),
    ((7, 1), (8, 31)),
    ((7, 11), (9, 10)),
    ((7, 21), (9, 20)),
    ((8, 1), (9, 30)),
)


def for_year(year: int) -> tuple[Period, ...]:
    return tuple(
        Period(idx, date(year, *start), date(year, *end))
        for idx, (start, end) in enumerate(PERIODS, start=1)
    )


def latest_completed(day: date) -> Period | None:
    return next((period for period in reversed(for_year(day.year)) if period.end <= day), None)
