"""edo.py: dekad selection (no future data), class sampling, service handling (network mocked)."""
from __future__ import annotations

from datetime import date, timedelta

import httpx
import numpy as np
import pytest
import respx

from app.contracts.common import SourceStatus
from app.geo import edo
from app.geo.sources import source

FIRST, LAST = date(2012, 1, 1), date(2026, 11, 1)


@pytest.mark.parametrize("analysis,expected", [
    (date(2023, 5, 31), date(2023, 5, 21)),   # third dekad of May ends 31 May
    (date(2023, 5, 30), date(2023, 5, 11)),   # 21-31 May not ended yet
    (date(2023, 5, 15), date(2023, 5, 1)),
    (date(2023, 5, 10), date(2023, 5, 1)),
    (date(2023, 5, 9), date(2023, 4, 21)),
    (date(2024, 3, 1), date(2024, 2, 21)),    # leap February: 21-29 Feb ended
    (date(2026, 11, 21), date(2026, 11, 1)),  # newest published dekad (extent end)
    (date(2012, 1, 5), None),                 # before the first complete dekad
])
def test_dekad_for(analysis, expected):
    t = edo.dekad_for(analysis, FIRST, LAST)
    assert t == expected
    if t is not None:   # the chosen dekad has ended on or before the analysis date (no future data)
        assert edo.next_dekad(t) - timedelta(days=1) <= analysis


def _tiff(codes: np.ndarray, left=18.5, top=72.0, xres=0.04, yres=0.0416667) -> bytes:
    import rasterio
    from rasterio.io import MemoryFile
    from rasterio.transform import from_origin

    with MemoryFile() as mf:
        with mf.open(driver="GTiff", width=codes.shape[1], height=codes.shape[0], count=1, dtype="uint8",
                     crs="EPSG:4326", transform=from_origin(left, top, xres, yres)) as ds:
            ds.write(codes, 1)
        return mf.read()


def test_sample_code_at_point():
    codes = np.zeros((1200, 5), "uint8")
    row = int((72.0 - 52.8) / 0.0416667)
    codes[row, 2] = 3
    assert edo.sample_code(_tiff(codes), 52.8, 18.6) == 3
    assert edo.sample_code(_tiff(codes), 52.8, 25.0) is None   # outside the strip


CAPS = ('<WMT_MS_Capabilities><Capability><Layer><Layer><Name>cdiad</Name>'
        '<Extent name="time" default="2026-11-01">2012-01-01/2026-11-01/P10D</Extent></Layer></Layer>'
        '</Capability></WMT_MS_Capabilities>')


@pytest.mark.asyncio
@respx.mock
async def test_edo_signal_label_and_no_values():
    codes = np.full((1200, 5), 3, "uint8")
    respx.get(source("edo")["wms_url"]).mock(return_value=httpx.Response(200, text=CAPS))
    wcs = respx.get(source("edo")["wcs_url"]).mock(return_value=httpx.Response(200, content=_tiff(codes)))
    res = await edo.edo_signal(52.8, 18.6, date(2018, 7, 10))
    assert res.status == SourceStatus.OK
    assert res.data.date_used == date(2018, 7, 1) and res.data.cdi_class == "Alert"
    assert res.data.cdi_value is None and res.data.sma is None and res.data.spi3 is None
    assert res.provenance and edo.NO_VALUES_NOTE_PL in res.notes_pl
    assert wcs.calls.last.request.url.params["TIME"] == "2018-07-01"


@pytest.mark.asyncio
@respx.mock
async def test_edo_signal_no_class_is_partial():
    codes = np.full((1200, 5), 200, "uint8")   # value not in the CDI level table
    respx.get(source("edo")["wms_url"]).mock(return_value=httpx.Response(200, text=CAPS))
    respx.get(source("edo")["wcs_url"]).mock(return_value=httpx.Response(200, content=_tiff(codes)))
    res = await edo.edo_signal(52.8, 18.6, date(2023, 5, 31))
    assert res.status == SourceStatus.PARTIAL and res.data.cdi_class is None
