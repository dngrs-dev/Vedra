"""tests/fixtures/geo/*.json load as {parcel: Parcel, bundle: GeoBundle} under the name rule of CONTRACTS.md section 4."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from app.contracts.common import SourceStatus
from app.contracts.geo import GeoBundle
from app.contracts.parcel import Parcel

FIXTURES = sorted((Path(__file__).resolve().parents[1] / "fixtures" / "geo").glob("*.json"))


def test_fixtures_exist():
    assert len(FIXTURES) >= 9  # CP1: 3 parcels x 3 dates


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.name)
def test_fixture_matches_contract(path: Path):
    raw = json.loads(path.read_text(encoding="utf-8"))
    parcel = Parcel.model_validate(raw["parcel"])
    bundle = GeoBundle.model_validate(raw["bundle"])
    stem_id, day = path.stem.split("__")
    assert stem_id == parcel.parcel_id.replace("/", "-")
    date.fromisoformat(day)
    for name, res in bundle:
        if res.status != SourceStatus.MISSING:
            assert res.provenance, f"{name}: data without provenance"
        if res.status != SourceStatus.OK:
            assert res.notes_pl, f"{name}: not ok but no Polish note"
