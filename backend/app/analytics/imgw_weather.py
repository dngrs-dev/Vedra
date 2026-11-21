"""Use preprocessed, source-attributed IMGW-PIB daily station observations."""
from __future__ import annotations

from contextlib import closing
from datetime import date, datetime
from pathlib import Path
import sqlite3

from pyproj import Geod

from app.analytics.models import Period, WeatherData, WeatherDay
from app.config import CONFIG_DIR
from app.contracts.common import Provenance, SourceResult, SourceStatus
from app.recommendations import texts_pl as text

ARCHIVE_URL = (
    "https://danepubliczne.imgw.pl/data/dane_pomiarowo_obserwacyjne/"
    "dane_meteorologiczne/dobowe/synop/"
)
STATIONS_URL = "https://danepubliczne.imgw.pl/api/data/meteo"
DEFAULT_ARCHIVE = CONFIG_DIR.parent / "data" / "b" / "imgw_daily.sqlite"
SOURCE_ID = "imgw_daily_synop"
_GEOD = Geod(ellps="WGS84")  # Standard EPSG:4326 ellipsoid, as used for parcel coordinates.


def _eligible_stations(db: sqlite3.Connection, period: Period, end: date) -> set[int]:
    month_start = period.start.replace(day=1)
    expected = (period.end - month_start).days + 1
    complete = {row[0] for row in db.execute(
        """SELECT station FROM observation
           WHERE day BETWEEN ? AND ? AND temperature_mean_c IS NOT NULL AND sunshine_h IS NOT NULL
             AND (day < ? OR precipitation_mm IS NOT NULL)
           GROUP BY station HAVING count(*) = ?""",
        (month_start.toordinal(), period.end.toordinal(), period.start.toordinal(), expected),
    )}
    if complete:
        return complete

    # A recently unpublished month should leave the current KBW unavailable while retaining history.
    return {row[0] for row in db.execute(
        """WITH available AS (
               SELECT station, max(day) AS latest FROM observation
               WHERE day <= ? AND precipitation_mm IS NOT NULL AND temperature_mean_c IS NOT NULL
                 AND sunshine_h IS NOT NULL
               GROUP BY station
           ) SELECT station FROM available WHERE latest = (SELECT max(latest) FROM available)""",
        (end.toordinal(),),
    )}


def read_weather(
    lat: float, lon: float, end: date, period: Period, path: Path = DEFAULT_ARCHIVE
) -> SourceResult[WeatherData]:
    if not path.is_file():
        return SourceResult[WeatherData](status=SourceStatus.MISSING)
    try:
        with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
            eligible = _eligible_stations(db, period, end)
            if not eligible:
                return SourceResult[WeatherData](status=SourceStatus.MISSING)
            stations = [
                (_GEOD.inv(lon, lat, station_lon, station_lat)[2], code, name, station_lat, station_lon)
                for code, name, station_lat, station_lon in db.execute("SELECT code, name, lat, lon FROM station")
                if code in eligible
            ]
            distance_m, code, name, station_lat, station_lon = min(stations)
            entries = db.execute(
                """SELECT day, precipitation_mm, temperature_mean_c, sunshine_h
                   FROM observation WHERE station = ? AND day <= ? ORDER BY day""",
                (code, end.toordinal()),
            )
            days = {
                date.fromordinal(day): WeatherDay(precipitation_mm=rain, temperature_mean_c=mean, sunshine_h=sun)
                for day, rain, mean, sun in entries
            }
            fetched_at = datetime.fromisoformat(db.execute("SELECT max(fetched_at) FROM input").fetchone()[0])
    except (sqlite3.Error, TypeError, ValueError) as exc:
        return SourceResult[WeatherData](status=SourceStatus.MISSING, error=f"IMGW archive: {exc}")

    # This source provides station observations without the ERA5-Land soil profile or reference ET0.
    source = Provenance(
        source_id=SOURCE_ID,
        name=text.IMGW_DAILY_NAME.format(station=name),
        url=ARCHIVE_URL,
        fetched_at=fetched_at,
        live=False,
        data_period=f"{min(days).isoformat()}..{max(days).isoformat()}",
        resolution=text.IMGW_DAILY_RESOLUTION,
        licence=text.IMGW_DAILY_LICENCE,
        attribution_pl=text.IMGW_DAILY_ATTRIBUTION,
    )
    # SI unit conversion; the report shows the approximate station distance to one decimal place.
    distance = f"{distance_m / 1000:.1f}".replace(".", ",")
    return SourceResult[WeatherData](
        status=SourceStatus.PARTIAL,
        data=WeatherData(station_lat, station_lon, days),
        provenance=[source],
        notes_pl=[text.IMGW_DAILY_LIMITATION.format(station=name, distance=distance), text.IMGW_DAILY_VARIABLES_MISSING],
    )
