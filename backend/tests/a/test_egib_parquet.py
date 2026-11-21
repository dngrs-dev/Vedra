"""egib_parquet.py (ULDK fallback): range reads, row-group selection, lookups by point and id, wiring in uldk.py.

A small GeoParquet with the column layout of the real export (probe 2026-11-21, config `egib_parquet.probe`) is
built in memory and served through respx with real HTTP Range semantics.
"""
from __future__ import annotations

import io
import re

import httpx
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
import respx
from shapely.geometry import box

from app.geo import egib_parquet, uldk
from app.geo.sources import source

URL = source("egib_parquet")["url"]
PRG = source("prg_wfs")["url"]


def _parcel(pid: str, x0: float, y0: float, size: float = 100.0) -> dict:
    g = box(x0, y0, x0 + size, y0 + size)
    return {"id_dzialki": pid, "numer_dzialki": pid.rsplit(".", 1)[-1], "nazwa_obrebu": "Jacewo",
            "nazwa_gminy": "Inowrocław", "geometry": g.wkb,
            "geometry_bbox": {"xmin": x0, "ymin": y0, "xmax": x0 + size, "ymax": y0 + size}}


def _file() -> bytes:
    # two spatially separate row groups, as in the real export
    near = [_parcel(f"040704_2.0012.{i}/1", 452800 + 100 * i, 548400) for i in range(5)]
    far = [_parcel(f"303005_5.0323.{i}/7", 300000 + 100 * i, 480000) for i in range(5)]
    schema = pa.schema([("id_dzialki", pa.string()), ("numer_dzialki", pa.string()), ("nazwa_obrebu", pa.string()),
                        ("nazwa_gminy", pa.string()), ("geometry", pa.binary()),
                        ("geometry_bbox", pa.struct([("xmin", pa.float32()), ("ymin", pa.float32()),
                                                     ("xmax", pa.float32()), ("ymax", pa.float32())]))])
    buf = io.BytesIO()
    with pq.ParquetWriter(buf, schema) as w:
        for rows in (near, far):
            w.write_table(pa.Table.from_pylist(rows, schema=schema))
    return buf.getvalue()


DATA = _file()


def _serve(request: httpx.Request) -> httpx.Response:
    m = re.fullmatch(r"bytes=(\d+)-(\d+)", request.headers.get("range", ""))
    a, b = int(m.group(1)), int(m.group(2))
    return httpx.Response(206, content=DATA[a:b + 1], headers={"content-range": f"bytes {a}-{b}/{len(DATA)}",
                                                                 "last-modified": "Sat, 21 Nov 2026 03:03:07 GMT"})


PRG_JACEWO = ('<wfs:FeatureCollection><gml:Envelope srsName="urn:ogc:def:crs:EPSG::2180">'
              '<gml:lowerCorner>548300.0 452700.0</gml:lowerCorner><gml:upperCorner>548600.0 453400.0'
              '</gml:upperCorner></gml:Envelope></wfs:FeatureCollection>')


@pytest.fixture
def served():
    with respx.mock(assert_all_called=False) as mock:
        route = mock.get(URL).mock(side_effect=_serve)
        mock.get(PRG).mock(return_value=httpx.Response(200, text=PRG_JACEWO))
        yield route


def test_sparse_file_refuses_bytes_it_does_not_have():
    f = egib_parquet.SparseFile(100, {10: b"abcdef"})
    f.seek(12)
    assert f.read(3) == b"cde"
    f.seek(50)
    with pytest.raises(OSError):
        f.read(2)


@pytest.mark.asyncio
async def test_row_group_selection_and_point_lookup(served):
    size, foot = await egib_parquet.footer()
    md = egib_parquet.metadata(foot)
    assert size == len(DATA) and md.num_row_groups == 2
    assert egib_parquet.row_groups_for(md, 452950, 548450, 452950, 548450) == [0]     # far group skipped
    rec = await egib_parquet.by_point(452950.0, 548450.0)
    assert rec[0] == "040704_2.0012.1/1"
    p = uldk.to_parcel(rec)
    assert (p.voivodeship, p.county, p.commune, p.region, p.parcel_number) == (
        "kujawsko-pomorskie", "powiat inowrocławski", "Inowrocław", "Jacewo", "1/1")
    assert abs(p.area_ha - 1.0) < 1e-6
    assert await egib_parquet.by_point(10.0, 10.0) is None
    # only ranges were requested, never the whole file
    assert all(c.request.headers["range"] for c in served.calls)


@pytest.mark.asyncio
async def test_id_lookup_uses_the_obreb_bbox(served):
    rec = await egib_parquet.by_id("040704_2.0012.3/1")
    assert rec[0] == "040704_2.0012.3/1" and rec[1].startswith("SRID=2180;POLYGON")
    assert await egib_parquet.by_id("040704_2.0012.99/1") is None


BLOCKED = "0\n0101000020E6100000000000000080564000000000008056400101"   # ULDK answer seen 2026-11-21


@pytest.mark.asyncio
async def test_uldk_blocked_falls_back_to_the_export():
    """2026-11-21: ULDK answered every request with a redirect to a page returning '0' + a hex string."""
    from shapely.geometry import Point

    from app.geo import geometry

    with respx.mock(assert_all_called=False) as mock:
        mock.get(URL).mock(side_effect=_serve)
        mock.get(PRG).mock(return_value=httpx.Response(200, text=PRG_JACEWO))
        mock.get(source("uldk")["url"]).mock(return_value=httpx.Response(200, text=BLOCKED))
        p = await uldk.get_by_id("040704_2.0012.2/1")
        assert p.parcel_id == "040704_2.0012.2/1" and p.county == "powiat inowrocławski"
        pt = geometry.to_4326(Point(453050.0, 548450.0))
        q = await uldk.get_by_xy(pt.y, pt.x)
        assert q.parcel_id == "040704_2.0012.2/1"
        with pytest.raises(uldk.ParcelNotFound):
            await uldk.get_by_id("040704_2.0012.99/1")


@pytest.mark.asyncio
async def test_both_down_is_upstream_unavailable(monkeypatch):
    async def _no_sleep(_s):
        return None

    monkeypatch.setattr("asyncio.sleep", _no_sleep)
    with respx.mock(assert_all_called=False) as mock:
        mock.get(URL).mock(return_value=httpx.Response(503))
        mock.get(PRG).mock(return_value=httpx.Response(503))
        mock.get(source("uldk")["url"]).mock(return_value=httpx.Response(200, text=BLOCKED))
        with pytest.raises(uldk.UpstreamUnavailable):
            await uldk.get_by_id("040704_2.0012.2/1")
