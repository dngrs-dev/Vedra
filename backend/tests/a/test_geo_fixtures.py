"""tests/fixtures/geo/*.json load as {parcel: Parcel, bundle: GeoBundle} under the name rule of CONTRACTS.md section 4."""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app.contracts.common import SourceStatus
from app.contracts.geo import GeoBundle
from app.contracts.parcel import Parcel
from app.geo import edo
from app.geo.sources import source

ROOT = Path(__file__).resolve().parents[1] / "fixtures"
FIXTURES = sorted((ROOT / "geo").glob("*.json"))
# TEAM_SPLIT.md §7 and the registered CP5 recording date.
RELEASE_DATES = {"2018-07-10", "2023-05-31", "2026-11-21"}


def test_fixtures_cover_every_release_parcel_and_date():
    parcels = json.loads((ROOT / "parcels.json").read_text(encoding="utf-8"))
    expected = {
        f"{entry['parcel_id'].replace('/', '-')}__{day}.json" for entry in parcels for day in RELEASE_DATES
    }
    assert expected <= {path.name for path in FIXTURES}


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.name)
def test_fixture_matches_contract(path: Path):
    raw = json.loads(path.read_text(encoding="utf-8"))
    parcel = Parcel.model_validate(raw["parcel"])
    bundle = GeoBundle.model_validate(raw["bundle"])
    stem_id, day = path.stem.split("__")
    assert stem_id == parcel.parcel_id.replace("/", "-")
    analysis_date = date.fromisoformat(day)
    for name, res in bundle:
        if res.data is not None:
            assert res.provenance, f"{name}: data without provenance"
        if res.status != SourceStatus.OK:
            assert res.notes_pl, f"{name}: not ok but no Polish note"
    if bundle.vegetation.data is not None:
        veg = bundle.vegetation.data
        scenes = [*veg.current, *(s for window in veg.same_window_by_year.values() for s in window),
                  *(peak for peak in veg.season_peaks.values() if peak is not None)]
        assert all(scene.acquired <= analysis_date for scene in scenes)
        assert veg.current_window[1] <= analysis_date
    if bundle.edo.data is not None:
        assert edo.next_dekad(bundle.edo.data.date_used) - timedelta(days=1) <= analysis_date
    if bundle.landcover.data is not None:
        assert date.fromisoformat(source("worldcover")["observed_through"]) <= analysis_date
    if bundle.imgw.data is not None:
        assert all(record.fetched_at.astimezone(ZoneInfo("Europe/Warsaw")).date() == analysis_date
                   for record in bundle.imgw.provenance)
