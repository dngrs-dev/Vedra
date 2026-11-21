"""Record RealGeoProvider outputs -> tests/fixtures/geo/<parcel_id_sanitized>__<YYYY-MM-DD>.json

Usage (from backend/):
    python -m scripts.a.record_geo_fixtures                 # first 3 parcels x default dates
    python -m scripts.a.record_geo_fixtures --all           # every parcel in tests/fixtures/parcels.json
    python -m scripts.a.record_geo_fixtures --dates 2023-05-31

File name and content follow docs/CONTRACTS.md section 4: {"parcel": Parcel, "bundle": GeoBundle} dumped with
model_dump(mode="json"); parcel_id_sanitized = parcel id with "/" replaced by "-".
Default dates: today (Europe/Warsaw), 2018-07-10, 2023-05-31 (TEAM_SPLIT.md section 7).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

for _var in ("PROJ_LIB", "GDAL_DATA"):  # see scripts/a/spike_sources.py
    os.environ.pop(_var, None)

from app.contracts.geo import GeoRequest  # noqa: E402
from app.core import http  # noqa: E402
from app.geo import uldk  # noqa: E402
from app.geo.provider import RealGeoProvider  # noqa: E402
from app.geo.vegetation import shutdown_background  # noqa: E402
from app.geo.sources import BACKEND  # noqa: E402

OUT_DIR = BACKEND / "tests" / "fixtures" / "geo"


def fixture_path(parcel_id: str, day: date, output_dir: Path = OUT_DIR) -> Path:
    return output_dir / f"{parcel_id.replace('/', '-')}__{day.isoformat()}.json"


async def main(n_parcels: int | None, dates: list[date], deadline: float, output_dir: Path = OUT_DIR) -> int:
    parcels = json.loads((BACKEND / "tests" / "fixtures" / "parcels.json").read_text(encoding="utf-8"))
    if n_parcels is not None:
        parcels = parcels[:n_parcels]
    output_dir.mkdir(parents=True, exist_ok=True)
    geo = RealGeoProvider()
    for p in parcels:
        parcel = await uldk.get_by_id(p["parcel_id"])
        for day in dates:
            bundle = await geo.collect(GeoRequest(parcel=parcel, analysis_date=day, deadline_s=deadline))
            path = fixture_path(parcel.parcel_id, day, output_dir)
            path.write_text(json.dumps({"parcel": parcel.model_dump(mode="json"),
                                        "bundle": bundle.model_dump(mode="json")},
                                       ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
            status = " ".join(f"{k}={v.status.value}" for k, v in bundle)
            print(f"  {path.name}: {status}")
    await http.close()
    shutdown_background()
    return 0


if __name__ == "__main__":
    today = datetime.now(ZoneInfo("Europe/Warsaw")).date()
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--parcels", type=int, default=3)
    ap.add_argument("--dates", nargs="*", type=date.fromisoformat,
                    default=[today, date(2018, 7, 10), date(2023, 5, 31)])
    ap.add_argument("--deadline", type=float, default=22.0)
    ap.add_argument("--output-dir", type=Path, default=OUT_DIR, help="Katalog zapisu zestawów danych geo.")
    a = ap.parse_args()
    sys.exit(asyncio.run(main(None if a.all else a.parcels, a.dates, a.deadline, a.output_dir)))
