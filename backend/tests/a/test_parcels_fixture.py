"""tests/fixtures/parcels.json: shape B relies on (CONTRACTS.md section 4) and the CP0 mix (PART_A_DATA_GEO.md)."""
from __future__ import annotations

import json
import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
PARCELS = json.loads((BACKEND / "tests" / "fixtures" / "parcels.json").read_text(encoding="utf-8"))
# Full ULDK id, regex from PART_A_DATA_GEO.md (uldk.parse_query spec)
ULDK_ID = re.compile(r"^\d{6}_\d\.\d{4}\.(?:AR_\d+\.)?[0-9A-Za-z/]+$")


def test_required_fields() -> None:
    for p in PARCELS:
        assert ULDK_ID.match(p["parcel_id"]), p["parcel_id"]
        assert isinstance(p["note"], str) and p["note"]
        assert isinstance(p["lat"], float) and isinstance(p["lon"], float)


def test_ids_unique() -> None:
    ids = [p["parcel_id"] for p in PARCELS]
    assert len(ids) == len(set(ids))


def test_cp0_mix() -> None:
    assert 6 <= len(PARCELS) <= 8
    facts = [p["facts"] for p in PARCELS]
    assert len({f["voivodeship"] for f in facts}) >= 3
    assert any(f["area_ha"] < 1 for f in facts)
    assert any(f["area_ha"] > 20 for f in facts)
    assert any(".AR_" in p["parcel_id"] for p in PARCELS)
