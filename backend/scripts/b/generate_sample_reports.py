"""Generate the CP5 sample PDFs from recorded Part A geo results."""
from __future__ import annotations

import argparse
import asyncio
from contextlib import nullcontext
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.analytics import open_meteo
from app.analytics.models import AnalysisRequest, WeatherData
from app.analytics.pipeline import run_analysis
from app.config import CONFIG_DIR
from app.contracts.common import SourceResult, SourceStatus
from app.contracts.geo import GeoBundle
from app.core import http
from app.fakes.fixture_geo import FIXTURES_DIR, FixtureGeoProvider
from app.recommendations import texts_pl as text
from app.reports import pdf

OUTPUT = CONFIG_DIR.parent / "data" / "b" / "samples" / "reports"
# The three dates are from TEAM_SPLIT.md §7. Parcel IDs and names come from
# Part A's tests/fixtures/parcels.json and its recorded geo snapshots (2538d48).
SCENARIOS = (
    ("wrzesnia", "303005_5.0323.25/7", date(2018, 7, 10)),
    ("inowroclaw", "040704_2.0012.63/1", date(2023, 5, 31)),
    ("ketrzyn", "280803_2.0028.78/40", date(2026, 11, 21)),
)


async def _generate(fixtures: Path, output: Path) -> None:
    provider = FixtureGeoProvider(fixtures)
    documents = []
    for name, parcel_id, day in SCENARIOS:
        bundles: list[GeoBundle] = []
        report = await run_analysis(
            # The validation crop is published in both MRiRW annexes used in CP4.
            AnalysisRequest(parcel_id=parcel_id, crop_code="spring_cereals", analysis_date=day, include_irrigation=True),
            provider,
            lambda _: None,
            on_geo=bundles.append,
        )
        if text.GEO_FIXTURE_UNAVAILABLE in report.limitations_pl:
            raise ValueError(f"Brak zapisu danych przestrzennych dla działki {parcel_id} z dnia {day}.")
        map_png = await provider.render_static_map(report.parcel, bundles[0])
        document = await asyncio.to_thread(pdf.render, report, map_png)
        documents.append((output / f"{name}-{day}.pdf", document))

    output.mkdir(parents=True, exist_ok=True)
    for path, document in documents:
        path.write_bytes(document)
        print(f"Zapisano raport {path}.")


async def _run(args: argparse.Namespace) -> None:
    missing_weather = SourceResult[WeatherData](
        status=SourceStatus.MISSING, notes_pl=[text.WEATHER_ARCHIVE_UNAVAILABLE],
    )
    weather_source = (
        patch.object(open_meteo, "fetch_weather", AsyncMock(return_value=missing_weather))
        if args.offline else nullcontext()
    )
    try:
        with weather_source:
            await _generate(args.fixtures, args.output)
    finally:
        await http.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Wygeneruj przykładowe raporty Vedry na podstawie zapisanych danych geo.")
    parser.add_argument("--fixtures", type=Path, default=FIXTURES_DIR, help="Katalog zapisanych danych przestrzennych.")
    parser.add_argument("--output", type=Path, default=OUTPUT, help="Katalog raportów PDF.")
    parser.add_argument("--offline", action="store_true", help="Korzystaj z zapisanych pomiarów IMGW-PIB i danych geo.")
    asyncio.run(_run(parser.parse_args()))


if __name__ == "__main__":
    main()
