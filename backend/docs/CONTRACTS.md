# Contracts — the only interface between Part A and Part B

This file defines **everything** that crosses the A↔B boundary: data models, the `GeoProvider`
protocol, behavioural guarantees, timing, errors and test fixtures. It also contains the full code of
the **T0 commit** — the files written once, before the split.

If something is not in this file, it is private to one part and the other part must not depend on it.

---

## 1. Data flow

```text
                 Part B                                   Part A
  POST /api/analyses ─► jobs.runner ─► pipeline.run_analysis(req, geo)
                                         │
     1. parcel  ◄────────────────────────┼──── geo.find_parcels(parcel_id)          (≤ 6 s)¹
                                         │
     2. in parallel (asyncio.gather):    │
          weather = open_meteo.fetch_weather(parcel centroid, dates)   [B]
          bundle  = geo.collect(GeoRequest(parcel, analysis_date, ...)) ──► [A] (≤ deadline_s, default 22 s)
                                         │
     3. stages 1..5 on (parcel, weather, bundle, crop)                   [B]   (≤ 3 s)
     4. report = builder.build(...)                                      [B]
     5. png = geo.render_static_map(parcel, bundle) ◄────────────────── [A]   (≤ 3 s, only for the PDF)
     6. pdf = pdf.render(report, png)                                    [B]
```

¹ Was 3 s. Measured 2026-11-22: one EGiB WFS point query takes ~3.4 s, so the 3 s budget sent most
lookups into the slow fallbacks (`LOOKUP_TIMEOUT_S` in `app/api/cadastral.py`).

Direction of calls: **B calls A, never the other way round.** A does not import anything from
`app/analytics`, `app/api`, `app/reports`, `app/recommendations`, `app/jobs`, `app/storage`, `app/fakes`.
B does not import anything from `app/geo` except `app.geo.provider.RealGeoProvider` (in one place:
`app/api/deps.py`).

---

## 2. Division of meaning («A measures, B judges»)

| Topic | A returns (facts) | B decides (meaning) |
| --- | --- | --- |
| Parcel | geometry, TERYT, names, area | — |
| Soil | soil type code from the map, KBW soil category I–IV and its source, WOD range, per-layer FC/WP/texture/SOC with quantiles | TAW for the crop's root depth, «low retention» cause, «what if» SOM scenario |
| Vegetation | NDVI/NDMI per clear scene: current window, same window in previous years, seasonal peaks per year | crop-aware interpretation (harvest vs drought), percentile/VCI, parcel sensitivity vs KBW years |
| Terrain | DEM source/resolution, slope stats, depressions with volume, flow lines, ditch outlets | which retention measures to recommend, priority, wording |
| Hydrology | water features within 500 m with distances, ditches crossing the boundary | «landscape retention possible», water source for irrigation |
| Land cover | class shares in the parcel and in a 500 m buffer | «missing landscape elements» cause; warning if the parcel is not farmland |
| EDO | CDI class/value, SMA, fAPAR anomaly, SPI-3 on the nearest available date ≤ analysis date | agreement with our verdict |
| IMGW | nearest synop observation and active hydrological drought warnings (only when analysis date = today) | how to show them |
| Weather, KBW, SPI, ERA5-Land soil moisture | — (B fetches Open-Meteo itself) | everything |

---

## 3. Behavioural guarantees

**A guarantees:**

1. `collect()` **never raises**. Every field of `GeoBundle` is a `SourceResult` with `status` `ok`,
   `partial` or `missing`; failures go to `error` (English, technical) and `notes_pl` (Polish, for the report).
2. **No future data:** nothing observed after `GeoRequest.analysis_date` is used (scenes, EDO dates,
   IMGW). For a historical date, `imgw` is `missing` with a Polish note.
3. **Deadline:** `collect()` returns within `GeoRequest.deadline_s` (+0.5 s). Work not finished in time
   is returned as `partial` with a note (e.g. «Przeanalizowano 14 z 30 scen Sentinel-2»).
4. **Provenance:** every `SourceResult` with data has ≥ 1 `Provenance` (source, URL, fetch time,
   live/preprocessed, resolution, licence, attribution text).
5. **Geometries** crossing the boundary are GeoJSON in EPSG:4326; numeric areas in m² or ha as named.
6. `find_parcels()` raises only `InvalidParcelQuery` (syntax) or `ParcelNotFound`; network problems
   raise `UpstreamUnavailable`.

**B guarantees:**

1. B passes a `GeoRequest` with `analysis_date` ≤ today and ≥ today − 10 years (validated in the API).
2. B treats `partial`/`missing` as normal and shows `notes_pl` in the report.
3. B never re-fetches A's sources and never post-edits A's numbers (only interprets them).

---

## 4. Test fixtures

- `tests/fixtures/parcels.json` (A): real test parcels, e.g.
  `[{"parcel_id": "...", "note": "light soil, Kujawy", "lat": 0, "lon": 0}]` — ids obtained from ULDK,
  never typed by hand.
- `tests/fixtures/geo/<parcel_id_sanitized>__<YYYY-MM-DD>.json` (A): `{"parcel": Parcel, "bundle": GeoBundle}`
  serialised with `model_dump(mode="json")`, recorded by `scripts/a/record_geo_fixtures.py`.
  `parcel_id_sanitized` = parcel id with `/` replaced by `-`.
- `FixtureGeoProvider` (B, `app/fakes/fixture_geo.py`) loads these files; `FakeGeoProvider`
  (B, `app/fakes/fake_geo.py`) generates synthetic but contract-valid data for any input.
- Contract tests:
  - `tests/contract/test_geo_provider_contract.py` (A) — `RealGeoProvider` on 2 parcels: types validate,
    deadline respected, no observation dated after `analysis_date`, provenance present.
  - `tests/contract/test_pipeline_on_fixtures.py` (B) — full pipeline with `FixtureGeoProvider` for
    every fixture file produces a valid `Report`.

---

## 5. T0 commit — exact code

Create these files exactly as below in one commit (`T0: contracts and shared core`). After that they are
frozen (changes per `TEAM_SPLIT.md` §5), except files explicitly marked «owner A/B fills in».

### 5.1 `requirements/base.txt` (frozen)

```text
fastapi>=0.115
uvicorn[standard]>=0.30
pydantic>=2.8
pydantic-settings>=2.4
httpx>=0.27
diskcache>=5.6
numpy>=1.26
scipy>=1.13
shapely>=2.0
pyproj>=3.6
matplotlib>=3.9
structlog>=24.1
pytest>=8.2
pytest-asyncio>=0.23
respx>=0.21
```

`requirements/a-geo.txt` (owner A) and `requirements/b-app.txt` (owner B) start as empty files.

### 5.2 Empty package markers (frozen, never edited)

`app/__init__.py`, `app/contracts/__init__.py`, `app/core/__init__.py` — empty files.
`app/geo/__init__.py` (owner A) and `app/analytics/__init__.py` (owner B) — empty files at T0.

### 5.3 `app/contracts/common.py`

```python
"""Shared building blocks of the A<->B contract. Frozen after T0."""
from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class SourceStatus(str, Enum):
    OK = "ok"
    PARTIAL = "partial"
    MISSING = "missing"


class Provenance(BaseModel):
    source_id: str  # stable id, e.g. "uldk", "sentinel2_earth_search"
    name: str  # display name, e.g. "ULDK GUGiK"
    url: str  # endpoint or dataset URL actually used
    fetched_at: datetime  # UTC
    live: bool  # True = fetched during this analysis; False = preprocessed file
    data_period: str | None = None  # e.g. "2016-05-01..2026-05-31" or "2021"
    resolution: str | None = None  # e.g. "10 m", "0.1 deg", "1:5000"
    licence: str  # e.g. "CC BY 4.0"
    attribution_pl: str | None = None  # exact attribution text required by the provider


class SourceResult(BaseModel, Generic[T]):
    status: SourceStatus
    data: T | None = None
    provenance: list[Provenance] = Field(default_factory=list)
    notes_pl: list[str] = Field(default_factory=list)  # user-facing limitations (Polish)
    error: str | None = None  # technical detail for logs (English)
    elapsed_s: float | None = None


class Range(BaseModel):
    """A value with optional uncertainty bounds (e.g. SoilGrids Q0.05 / Q0.5 / Q0.95)."""

    low: float | None = None
    mid: float
    high: float | None = None


class DateWindow(BaseModel):
    start: date
    end: date
```

### 5.4 `app/contracts/errors.py`

```python
"""Exceptions that may cross the A<->B boundary. Frozen after T0."""


class InvalidParcelQuery(ValueError):
    """The query is not a valid parcel id / 'obreb + number' / coordinates."""


class ParcelNotFound(LookupError):
    """ULDK returned no parcel for a syntactically valid query."""


class UpstreamUnavailable(RuntimeError):
    """A required upstream service did not answer (after retries)."""
```

### 5.5 `app/contracts/parcel.py`

```python
"""Parcel model. Frozen after T0."""
from __future__ import annotations

from pydantic import BaseModel


class Parcel(BaseModel):
    parcel_id: str  # full ULDK id, e.g. "141201_1.0001.6509"
    teryt: str
    voivodeship: str
    county: str
    commune: str
    region: str  # obreb (name or number)
    parcel_number: str
    area_ha: float
    geometry_wgs84: dict  # GeoJSON Polygon or MultiPolygon, EPSG:4326
    geometry_2180_wkt: str  # same geometry, EPSG:2180 (PUWG 1992)
    centroid_lat: float
    centroid_lon: float
```

### 5.6 `app/contracts/geo.py`

```python
"""Everything Part A returns to Part B. Frozen after T0."""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Protocol

from pydantic import BaseModel, Field

from app.contracts.common import Range, SourceResult
from app.contracts.parcel import Parcel

KbwSoilCategory = Literal["I", "II", "III", "IV"]


# ---------- soil ----------
class SoilLayer(BaseModel):
    top_cm: int
    bottom_cm: int
    sand_pct: Range | None = None
    silt_pct: Range | None = None
    clay_pct: Range | None = None
    soc_g_kg: Range | None = None
    bulk_density_g_cm3: Range | None = None
    theta_fc: Range | None = None  # volumetric water content at 33 kPa, m3/m3
    theta_wp: Range | None = None  # volumetric water content at 1500 kPa, m3/m3


class SoilInfo(BaseModel):
    kbw_category: KbwSoilCategory | None = None
    category_source: Literal["soil_map", "iung_wms", "soilgrids_wod"] | None = None
    soil_type_code: str | None = None  # e.g. "pgl" (mapa glebowo-rolnicza)
    soil_type_name_pl: str | None = None
    wod_mm: Range | None = None  # (FC - WP) summed over wod_depth_cm
    wod_depth_cm: int = 100
    layers: list[SoilLayer] = Field(default_factory=list)  # top to bottom


# ---------- vegetation (Sentinel-2) ----------
class SceneStat(BaseModel):
    scene_id: str
    acquired: date
    ndvi_median: float
    ndmi_median: float
    valid_pixels: int
    valid_fraction: float  # clear pixels / parcel interior pixels


class VegetationData(BaseModel):
    interior_pixels: int  # 10 m pixels inside the parcel after a -10 m buffer
    current: list[SceneStat]  # clear scenes in the current window, newest first
    current_window: tuple[date, date]
    same_window_by_year: dict[int, list[SceneStat]]  # previous years, same day-of-year window
    season_peaks: dict[int, SceneStat | None]  # max-NDVI clear scene Apr-Aug per year (<= analysis date)
    scenes_considered: int
    scenes_processed: int


# ---------- terrain (NMT) ----------
class RetentionSpot(BaseModel):
    id: str
    kind: Literal["depression", "ditch_outlet", "flow_concentration"]
    geometry: dict  # GeoJSON Point or Polygon, EPSG:4326
    inside_parcel: bool
    volume_m3: Range | None = None
    area_m2: float | None = None
    max_depth_m: float | None = None
    upstream_area_ha: float | None = None


class FlowLine(BaseModel):
    geometry: dict  # GeoJSON LineString, EPSG:4326
    upstream_area_ha: float
    length_m: float
    crosses_parcel: bool


class TerrainData(BaseModel):
    dem_source: Literal["gugik_nmt_1m", "copernicus_dem_30m"]
    resolution_m: float
    elevation_min_m: float
    elevation_max_m: float
    slope_mean_pct: float
    slope_p90_pct: float
    twi_p90: float | None = None
    lowest_point: dict | None = None  # GeoJSON Point of the parcel's lowest cell
    retention_spots: list[RetentionSpot] = Field(default_factory=list)
    flow_lines: list[FlowLine] = Field(default_factory=list)


# ---------- hydrology ----------
class WaterFeature(BaseModel):
    kind: Literal["ditch", "stream", "river", "canal", "lake", "pond", "wetland", "other"]
    name: str | None = None
    geometry: dict  # GeoJSON, EPSG:4326
    distance_m: float  # 0 if touching/inside the parcel
    touches_parcel: bool
    source_id: str  # "mphp" | "osm"


class HydroData(BaseModel):
    buffer_m: int
    features: list[WaterFeature] = Field(default_factory=list)
    nearest_water_m: float | None = None
    ditches_crossing_boundary: int = 0


# ---------- land cover ----------
class LandCoverData(BaseModel):
    dataset: str  # e.g. "ESA WorldCover 2021 v200"
    buffer_m: int
    shares_parcel: dict[str, float]  # class name -> share 0..1
    shares_buffer: dict[str, float]


# ---------- EDO ----------
class EdoData(BaseModel):
    date_used: date  # nearest available EDO date <= analysis date
    cdi_class: str | None = None  # label as in the EDO legend
    cdi_value: float | None = None
    sma: float | None = None
    fapar_anomaly: float | None = None
    spi3: float | None = None


# ---------- IMGW (current only) ----------
class ImgwObservation(BaseModel):
    station_id: str
    station_name: str
    distance_km: float
    observed_at: datetime
    temperature_c: float | None = None
    precipitation_mm: float | None = None
    relative_humidity_pct: float | None = None


class HydroWarning(BaseModel):
    number: str | None = None
    phenomenon: str  # e.g. "susza hydrologiczna"
    area_pl: str
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    level: str | None = None


class ImgwData(BaseModel):
    nearest_synop: ImgwObservation | None = None
    drought_warnings: list[HydroWarning] = Field(default_factory=list)


# ---------- request / bundle / provider ----------
class GeoRequest(BaseModel):
    parcel: Parcel
    analysis_date: date
    current_window_days: int = 30  # extended by A up to 60 if no clear scene
    same_window_half_days: int = 15
    history_years: int = 10
    hydro_buffer_m: int = 500
    deadline_s: float = 22.0


class GeoBundle(BaseModel):
    soil: SourceResult[SoilInfo]
    vegetation: SourceResult[VegetationData]
    terrain: SourceResult[TerrainData]
    hydro: SourceResult[HydroData]
    landcover: SourceResult[LandCoverData]
    edo: SourceResult[EdoData]
    imgw: SourceResult[ImgwData]


class GeoProvider(Protocol):
    async def find_parcels(self, query: str) -> list[Parcel]:
        """Full ULDK id, 'obreb number' or 'lat,lon'. Raises InvalidParcelQuery / ParcelNotFound / UpstreamUnavailable."""

    async def parcel_at_point(self, lat: float, lon: float) -> Parcel | None:
        """Parcel containing the WGS84 point, or None."""

    async def collect(self, req: GeoRequest) -> GeoBundle:
        """All geo facts for the parcel and date. Never raises; respects req.deadline_s."""

    async def render_static_map(self, parcel: Parcel, bundle: GeoBundle, width_px: int = 1200) -> bytes:
        """PNG: parcel outline + retention spots + flow lines + water features on a hillshade/orthophoto."""
```

### 5.7 `app/core/http.py` (frozen)

```python
"""Shared async HTTP client with host allowlist and retries. Frozen after T0."""
from __future__ import annotations

import asyncio
from urllib.parse import urlparse

import httpx

from app.analytics.hosts import ANALYTICS_HOSTS  # owner B
from app.contracts.errors import UpstreamUnavailable
from app.geo.hosts import GEO_HOSTS  # owner A

_client: httpx.AsyncClient | None = None


class HostNotAllowed(Exception):
    pass


def allowed_hosts() -> set[str]:
    return set(GEO_HOSTS) | set(ANALYTICS_HOSTS)


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(10.0, connect=5.0),
            follow_redirects=True,
            headers={"User-Agent": "Vedra/0.1 (HackNation 2026 prototype)"},
            limits=httpx.Limits(max_connections=64),
        )
    return _client


async def get(url: str, *, params: dict | None = None, timeout: float | None = None, retries: int = 2) -> httpx.Response:
    host = urlparse(url).hostname or ""
    if host not in allowed_hosts():
        raise HostNotAllowed(host)
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            resp = await get_client().get(url, params=params, timeout=timeout)
            if resp.status_code >= 500 and attempt < retries:
                await asyncio.sleep(0.5 * 2**attempt)
                continue
            resp.raise_for_status()
            return resp
        except (httpx.TransportError, httpx.HTTPStatusError) as exc:
            last_exc = exc
            if attempt < retries:
                await asyncio.sleep(0.5 * 2**attempt)
    raise UpstreamUnavailable(f"{host}: {last_exc}")


async def close() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
```

GDAL `/vsicurl/` reads (rasterio) do not go through this client; Part A enforces `GEO_HOSTS` for them in
`app/geo/raster_io.py`.

### 5.8 Host lists (created at T0, then owned)

`app/geo/hosts.py` (owner A fills in):

```python
GEO_HOSTS: set[str] = {"uldk.gugik.gov.pl"}
```

`app/analytics/hosts.py` (owner B fills in):

```python
ANALYTICS_HOSTS: set[str] = {"archive-api.open-meteo.com", "api.open-meteo.com"}
```

### 5.9 `app/core/cache.py` (frozen)

```python
"""Disk cache shared by both parts. Keys are namespaced; each part uses its own namespaces. Frozen after T0."""
from __future__ import annotations

import hashlib
import json
import os
from typing import Any

from diskcache import Cache

_cache = Cache(os.environ.get("CACHE_DIR", ".cache"), size_limit=2 * 1024**3)


def make_key(namespace: str, **parts: Any) -> str:
    payload = json.dumps(parts, sort_keys=True, default=str)
    return f"{namespace}:{hashlib.sha256(payload.encode()).hexdigest()}"


def get(key: str) -> Any | None:
    return _cache.get(key)


def set(key: str, value: Any, expire_s: float | None = None) -> None:  # noqa: A001
    _cache.set(key, value, expire=expire_s)
```

Namespaces: Part A uses `geo.*` (e.g. `geo.uldk`, `geo.s2.scene`), Part B uses `an.*`
(e.g. `an.openmeteo`). Never read the other part's namespace.

### 5.10 `app/geo/provider.py` (signatures frozen, bodies owner A)

```python
"""Real GeoProvider. Signatures frozen at T0; Part A implements the bodies."""
from __future__ import annotations

from app.contracts.geo import GeoBundle, GeoRequest
from app.contracts.parcel import Parcel


class RealGeoProvider:
    async def find_parcels(self, query: str) -> list[Parcel]:
        raise NotImplementedError

    async def parcel_at_point(self, lat: float, lon: float) -> Parcel | None:
        raise NotImplementedError

    async def collect(self, req: GeoRequest) -> GeoBundle:
        raise NotImplementedError

    async def render_static_map(self, parcel: Parcel, bundle: GeoBundle, width_px: int = 1200) -> bytes:
        raise NotImplementedError
```

### 5.11 Optional: `scripts/check_ownership.py` (frozen)

```python
"""Usage: git diff --cached --name-only | python scripts/check_ownership.py A|B"""
import fnmatch
import sys

OWN = {
    "A": ["backend/app/geo/*", "backend/config/geo_sources.yaml", "backend/config/soil_categories.yaml",
          "backend/requirements/a-geo.txt", "backend/scripts/a/*", "backend/tests/a/*",
          "backend/tests/fixtures/geo/*", "backend/tests/fixtures/parcels.json",
          "backend/tests/contract/test_geo_provider_contract.py", "backend/data/a/*",
          "backend/docs/PART_A_DATA_GEO.md", "backend/docs/DATA_SOURCES.md"],
    "B": ["backend/app/main.py", "backend/app/config.py", "backend/app/api/*", "backend/app/analytics/*",
          "backend/app/recommendations/*", "backend/app/reports/*", "backend/app/jobs/*",
          "backend/app/storage/*", "backend/app/fakes/*", "backend/app/contracts/report.py",
          "backend/config/*", "backend/requirements/b-app.txt", "backend/Dockerfile", "backend/scripts/b/*",
          "backend/tests/b/*", "backend/tests/contract/test_pipeline_on_fixtures.py",
          "backend/tests/fixtures/sample_report.json", "backend/data/b/*", "backend/README.md",
          "backend/docs/*"],
}
EXCLUDE_FROM_B = OWN["A"]  # A's files under config/ and docs/ stay A's

who = sys.argv[1]
bad = []
for path in (line.strip() for line in sys.stdin if line.strip()):
    if not path.startswith("backend/"):
        continue  # frontend / repo root are outside this check
    mine = any(fnmatch.fnmatch(path, p) for p in OWN[who])
    if who == "B" and any(fnmatch.fnmatch(path, p) for p in EXCLUDE_FROM_B):
        mine = False
    if not mine:
        bad.append(path)
if bad:
    print("Not your files:\n  " + "\n  ".join(bad))
    sys.exit(1)
```

Note: `fnmatch` `*` matches across `/`, so `backend/app/geo/*` covers sub-folders.
