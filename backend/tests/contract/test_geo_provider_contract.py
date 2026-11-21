"""Contract test of the GeoProvider (CONTRACTS.md §3 and §4), owner A.

GEO_PROVIDER=real      RealGeoProvider.collect() live on 2 test parcels: the bundle validates, the deadline is respected,
                       no observation is dated after analysis_date, every result with data has provenance.
otherwise (default)    the same checks, without the network, on the recorded fixtures of the same 2 parcels
                       (tests/fixtures/geo/, written by scripts/a/record_geo_fixtures.py); the deadline is not
                       checked there.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.contracts.common import SourceStatus  # noqa: E402
from app.contracts.geo import GeoBundle, GeoRequest  # noqa: E402
from app.contracts.parcel import Parcel  # noqa: E402

MODE = os.environ.get("GEO_PROVIDER", "fixtures")
FIXTURES = BACKEND / "tests" / "fixtures"
# Inowrocław 1.5 ha (preprocessed NMT and Sentinel-2) and Kętrzyn 150 ha (Copernicus DEM path)
PARCEL_IDS = ["040704_2.0012.63/1", "280803_2.0028.78/40"]
DEADLINE_S = 22.0
DEADLINE_SLACK_S = 0.5   # CONTRACTS.md §3: collect() returns within deadline_s (+0.5 s)


def today_pl() -> date:
    return datetime.now(ZoneInfo("Europe/Warsaw")).date()


def check_bundle(parcel: Parcel, bundle: GeoBundle, day: date) -> None:
    Parcel.model_validate(parcel.model_dump(mode="json"))
    GeoBundle.model_validate(bundle.model_dump(mode="json"))

    # every result with data has provenance; missing results explain themselves
    for name, res in bundle:
        if res.data is not None:
            assert res.provenance, f"{name}: data without provenance"
            for p in res.provenance:
                assert p.url.startswith("https://") and p.licence and p.fetched_at.tzinfo is not None, name
        if res.status != SourceStatus.OK:
            assert res.notes_pl or res.error, f"{name}: {res.status.value} without notes_pl"

    # no observation dated after analysis_date
    veg = bundle.vegetation.data
    if veg is not None:
        scenes = list(veg.current) + [s for v in veg.same_window_by_year.values() for s in v] + \
            [s for s in veg.season_peaks.values() if s is not None]
        assert all(s.acquired <= day for s in scenes), "vegetation: scene after analysis_date"
        assert veg.current_window[1] <= day and all(y <= day.year for y in veg.season_peaks)
    if bundle.edo.data is not None:
        assert bundle.edo.data.date_used <= day, "edo: dekad after analysis_date"
    imgw = bundle.imgw.data
    if imgw is not None and (imgw.nearest_synop is not None or imgw.drought_warnings):
        # IMGW serves current data only: it may be used only when it was fetched on the analysis day
        assert all(p.fetched_at.astimezone(ZoneInfo("Europe/Warsaw")).date() == day
                   for p in bundle.imgw.provenance), "imgw: current data used for a historical date"
        if imgw.nearest_synop is not None:
            assert imgw.nearest_synop.observed_at.astimezone(ZoneInfo("Europe/Warsaw")).date() <= day
    for name in ("vegetation", "edo", "imgw"):
        for p in getattr(bundle, name).provenance:
            if p.data_period and ".." in p.data_period:
                assert date.fromisoformat(p.data_period.split("..")[1][:10]) <= day, f"{name}: {p.data_period}"


def _fixture_cases():
    out = []
    for pid in PARCEL_IDS:
        for path in sorted((FIXTURES / "geo").glob(pid.replace("/", "-") + "__*.json")):
            out.append(pytest.param(path, id=path.stem))
    return out


@pytest.mark.skipif(MODE == "real", reason="GEO_PROVIDER=real runs the live test instead")
@pytest.mark.parametrize("path", _fixture_cases())
def test_recorded_bundles_meet_the_contract(path):
    rec = json.loads(path.read_text(encoding="utf-8"))
    day = date.fromisoformat(path.stem.rsplit("__", 1)[1])
    check_bundle(Parcel.model_validate(rec["parcel"]), GeoBundle.model_validate(rec["bundle"]), day)


def test_fixtures_cover_both_contract_parcels():
    assert len(_fixture_cases()) >= 2 * len(PARCEL_IDS)


@pytest.mark.skipif(MODE != "real", reason="live network test: set GEO_PROVIDER=real")
@pytest.mark.asyncio
@pytest.mark.parametrize("parcel_id", PARCEL_IDS)
@pytest.mark.parametrize("day", [date(2023, 5, 31), today_pl()], ids=["2023-05-31", "today"])
async def test_real_provider_meets_the_contract(parcel_id, day):
    from app.core import http
    from app.geo import vegetation
    from app.geo.provider import RealGeoProvider

    geo = RealGeoProvider()
    try:
        parcels = await geo.find_parcels(parcel_id)
        assert [p.parcel_id for p in parcels] == [parcel_id]
        t = time.monotonic()
        bundle = await geo.collect(GeoRequest(parcel=parcels[0], analysis_date=day, deadline_s=DEADLINE_S))
        assert time.monotonic() - t <= DEADLINE_S + DEADLINE_SLACK_S
        check_bundle(parcels[0], bundle, day)
    finally:
        vegetation.shutdown_background()
        await http.close()
