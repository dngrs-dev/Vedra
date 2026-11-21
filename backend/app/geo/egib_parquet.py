"""Parcel lookup in the national EGiB GeoParquet export (config/geo_sources.yaml `egib_parquet`): ULDK fallback.

The file is 4.6 GB, so nothing is downloaded in full. Per lookup:
  1. the Parquet footer (~1 MB; disk-cached per file version, the file is rebuilt daily),
  2. candidate row groups from the footer's geometry_bbox statistics (row groups are spatially clustered),
  3. only the needed column chunks of those row groups, as parallel HTTP range requests (16 x 0.5 MB; one stream
     gives ~0.5 MB/s, 16 give ~7 MB/s - probe in the config),
  4. decoding with pyarrow in a worker thread from the fetched byte ranges (no network inside the decoder).
By point: geometry_bbox columns of the candidates -> rows whose bbox holds the point -> geometry of those row groups
-> exact point-in-polygon. By id: the obręb bbox from the PRG WFS (id prefix "040704_2.0012") selects the candidates,
then id_dzialki is searched and the geometry of the matching row group is read.
"""
from __future__ import annotations

import asyncio
import io
import json
import re
import struct
from functools import lru_cache
from urllib.parse import urlparse

from app.contracts.errors import UpstreamUnavailable
from app.core import cache, http
from app.geo.hosts import GEO_HOSTS
from app.geo.sources import BACKEND, source

ATTR_COLUMNS = ["id_dzialki", "numer_dzialki", "nazwa_obrebu", "nazwa_gminy"]
BBOX = "geometry_bbox"


def _cfg() -> dict:
    return source("egib_parquet")


def _url() -> str:
    url = _cfg()["url"]
    if urlparse(url).hostname not in GEO_HOSTS:      # requests below bypass app.core.http.get (Range header)
        raise UpstreamUnavailable(f"egib_parquet: host not allowed: {url}")
    return url


async def _range(start: int, end: int) -> bytes:
    """Bytes [start, end] (inclusive) of the file."""
    try:
        resp = await http.get_client().get(_url(), headers={"Range": f"bytes={start}-{end}"}, timeout=60.0)
    except Exception as exc:  # noqa: BLE001 - network errors -> contract error type
        raise UpstreamUnavailable(f"egib_parquet: {exc!r}") from exc
    if resp.status_code != 206 or len(resp.content) != end - start + 1:
        raise UpstreamUnavailable(f"egib_parquet: range {start}-{end} -> HTTP {resp.status_code}, "
                                  f"{len(resp.content)} bytes")
    return resp.content


async def fetch_ranges(ranges: list[tuple[int, int]]) -> dict[int, bytes]:
    """{start: bytes} for (start, length) ranges, split into chunk_bytes pieces fetched parallel_requests at a time."""
    cfg = _cfg()
    chunk, sem = int(cfg["chunk_bytes"]), asyncio.Semaphore(int(cfg["parallel_requests"]))
    pieces = [(s, min(s + chunk, start + length) - 1) for start, length in ranges
              for s in range(start, start + length, chunk)]

    async def one(a: int, b: int) -> tuple[int, bytes]:
        async with sem:
            return a, await _range(a, b)

    got = dict(await asyncio.gather(*(one(a, b) for a, b in pieces)))
    return {start: b"".join(got[s] for s in range(start, start + length, chunk)) for start, length in ranges}


class SparseFile(io.RawIOBase):
    """Read-only file of `size` bytes of which only `segments` ({offset: bytes}) are known; for pyarrow."""

    def __init__(self, size: int, segments: dict[int, bytes]):
        self.size, self.pos = size, 0
        self.segments = sorted(segments.items())

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self.pos

    def seek(self, offset: int, whence: int = 0) -> int:
        self.pos = offset if whence == 0 else self.pos + offset if whence == 1 else self.size + offset
        return self.pos

    def read(self, n: int = -1) -> bytes:
        if n is None or n < 0:
            n = self.size - self.pos
        for start, data in self.segments:
            if start <= self.pos and self.pos + n <= start + len(data):
                out = data[self.pos - start:self.pos - start + n]
                self.pos += n
                return out
        raise OSError(f"egib_parquet: bytes {self.pos}..{self.pos + n} were not fetched")

    def readinto(self, b) -> int:
        data = self.read(len(b))
        b[:len(data)] = data
        return len(data)


# ---------------------------------------------------------------- footer / metadata
async def _file_version() -> tuple[int, str]:
    try:
        resp = await http.get_client().get(_url(), headers={"Range": "bytes=0-0"}, timeout=15.0)
    except Exception as exc:  # noqa: BLE001
        raise UpstreamUnavailable(f"egib_parquet: {exc!r}") from exc
    m = re.search(r"/(\d+)$", resp.headers.get("content-range", ""))
    if resp.status_code != 206 or not m:
        raise UpstreamUnavailable(f"egib_parquet: no size (HTTP {resp.status_code})")
    return int(m.group(1)), resp.headers.get("last-modified", "")


async def footer() -> tuple[int, bytes]:
    """(file size, footer bytes incl. the 8-byte tail)."""
    size, modified = await _file_version()
    key = cache.make_key("geo.egib.footer", size=size, modified=modified)
    hit = cache.get(key)
    if hit is not None:
        return size, hit
    tail = await _range(size - 8, size - 1)
    if tail[4:] != b"PAR1":
        raise UpstreamUnavailable("egib_parquet: not a Parquet file")
    flen = struct.unpack("<I", tail[:4])[0]
    data = await _range(size - 8 - flen, size - 1)
    cache.set(key, data, expire_s=float(_cfg()["footer_cache_s"]))
    return size, data


def metadata(footer_bytes: bytes):
    import pyarrow.parquet as pq

    return pq.ParquetFile(io.BytesIO(b"PAR1" + footer_bytes)).metadata


def _columns(md) -> dict[str, int]:
    rg = md.row_group(0)
    return {rg.column(j).path_in_schema: j for j in range(rg.num_columns)}


def row_groups_for(md, xmin: float, ymin: float, xmax: float, ymax: float) -> list[int]:
    """Row groups whose geometry_bbox statistics intersect the box (EPSG:2180, x = easting)."""
    ix = _columns(md)
    out = []
    for i in range(md.num_row_groups):
        rg = md.row_group(i)
        st = {k: rg.column(ix[f"{BBOX}.{k}"]).statistics for k in ("xmin", "ymin", "xmax", "ymax")}
        if any(s is None or not s.has_min_max for s in st.values()):
            out.append(i)
            continue
        if st["xmin"].min <= xmax and st["xmax"].max >= xmin and st["ymin"].min <= ymax and st["ymax"].max >= ymin:
            out.append(i)
    return out


def chunk_ranges(md, groups: list[int], columns: list[str]) -> list[tuple[int, int]]:
    """(start, length) of the column chunks (all leaves of the named columns) of the row groups."""
    out = []
    for i in groups:
        rg = md.row_group(i)
        for j in range(rg.num_columns):
            col = rg.column(j)
            if col.path_in_schema.split(".")[0] not in columns:
                continue
            start = col.dictionary_page_offset if col.has_dictionary_page and col.dictionary_page_offset else \
                col.data_page_offset
            out.append((start, col.total_compressed_size))
    return out


def _read(size: int, md, segments: dict[int, bytes], group: int, columns: list[str]):
    import pyarrow.parquet as pq

    pf = pq.ParquetFile(SparseFile(size, segments), metadata=md, pre_buffer=False)
    return pf.read_row_group(group, columns=columns)


async def _read_groups(size: int, md, groups: list[int], columns: list[str]) -> dict[int, object]:
    segments = await fetch_ranges(chunk_ranges(md, groups, columns))
    tables = await asyncio.gather(*(asyncio.to_thread(_read, size, md, segments, g, columns) for g in groups))
    return dict(zip(groups, tables))


# ---------------------------------------------------------------- lookups
@lru_cache(maxsize=1)
def _names() -> dict:
    return json.loads((BACKEND / source("prg_wfs")["names_file"]).read_text(encoding="utf-8"))


def record(row: dict, wkb_geom: bytes) -> list[str]:
    """ULDK-shaped record (config uldk.result_fields order) for app.geo.uldk.to_parcel."""
    from shapely import wkb

    pid = row["id_dzialki"]
    names = _names()
    g = wkb.loads(wkb_geom)
    return [pid, f"SRID=2180;{g.wkt}", pid.split(".")[0], names["voivodeships"].get(pid[:2], ""),
            names["counties"].get(pid[:4], ""), row.get("nazwa_gminy") or "", row.get("nazwa_obrebu") or "",
            row.get("numer_dzialki") or pid.rsplit(".", 1)[-1]]


async def by_point(x: float, y: float) -> list[str] | None:
    """Record of the parcel containing the EPSG:2180 point, or None."""
    from shapely import wkb
    from shapely.geometry import Point

    size, foot = await footer()
    md = await asyncio.to_thread(metadata, foot)
    groups = row_groups_for(md, x, y, x, y)
    boxes = await _read_groups(size, md, groups, [BBOX])
    hits = {g: [k for k, b in enumerate(t.column(BBOX).to_pylist())
                if b["xmin"] <= x <= b["xmax"] and b["ymin"] <= y <= b["ymax"]] for g, t in boxes.items()}
    hits = {g: rows for g, rows in hits.items() if rows}
    if not hits:
        return None
    full = await _read_groups(size, md, list(hits), ATTR_COLUMNS + ["geometry"])
    p = Point(x, y)
    for g, rows in hits.items():
        t = full[g]
        for k in rows:
            geom = t.column("geometry")[k].as_py()
            if geom and wkb.loads(geom).covers(p):
                return record({c: t.column(c)[k].as_py() for c in ATTR_COLUMNS}, geom)
    return None


async def obreb_bbox(obreb_code: str) -> tuple[float, float, float, float]:
    """(xmin, ymin, xmax, ymax) EPSG:2180 (x = easting) of an obręb from the PRG WFS."""
    cfg = source("prg_wfs")
    flt = ('<fes:Filter xmlns:fes="http://www.opengis.net/fes/2.0"><fes:PropertyIsEqualTo>'
           f'<fes:ValueReference>JPT_KOD_JE</fes:ValueReference><fes:Literal>{obreb_code}</fes:Literal>'
           '</fes:PropertyIsEqualTo></fes:Filter>')
    resp = await http.get(cfg["url"], params={"SERVICE": "WFS", "REQUEST": "GetFeature", "VERSION": "2.0.0",
                                              "TYPENAMES": cfg["layers"]["obreby"], "FILTER": flt}, timeout=20.0)
    lo = re.search(r"<gml:lowerCorner>([\d.]+) ([\d.]+)</gml:lowerCorner>", resp.text)
    hi = re.search(r"<gml:upperCorner>([\d.]+) ([\d.]+)</gml:upperCorner>", resp.text)
    if not lo or not hi:
        raise UpstreamUnavailable(f"prg_wfs: no obręb {obreb_code}")
    # envelope axis order northing easting (config prg_wfs.envelope_axis_order)
    return float(lo.group(2)), float(lo.group(1)), float(hi.group(2)), float(hi.group(1))


async def by_id(parcel_id: str) -> list[str] | None:
    """Record of the parcel with this id, or None if the obręb exists but the parcel does not."""
    obreb = ".".join(parcel_id.split(".")[:2])
    xmin, ymin, xmax, ymax = await obreb_bbox(obreb)
    size, foot = await footer()
    md = await asyncio.to_thread(metadata, foot)
    groups = row_groups_for(md, xmin, ymin, xmax, ymax)
    ids = await _read_groups(size, md, groups, ["id_dzialki"])
    found = [(g, t.column("id_dzialki").to_pylist().index(parcel_id)) for g, t in ids.items()
             if parcel_id in t.column("id_dzialki").to_pylist()]
    if not found:
        return None
    g, k = found[0]
    t = (await _read_groups(size, md, [g], ATTR_COLUMNS + ["geometry"]))[g]
    return record({c: t.column(c)[k].as_py() for c in ATTR_COLUMNS}, t.column("geometry")[k].as_py())
