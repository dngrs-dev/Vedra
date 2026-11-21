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
