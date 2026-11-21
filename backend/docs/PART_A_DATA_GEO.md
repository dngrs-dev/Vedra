# Part A — data & geo («A measures»)

Owner: **person A** (and their coding agent). Read first: `README.md`, `TEAM_SPLIT.md`, `CONTRACTS.md`.

**Mission.** Implement `RealGeoProvider` (`app/geo/provider.py`): given a parcel query, return a
`Parcel`; given a `GeoRequest`, return a `GeoBundle` with soil, vegetation, terrain, hydrology, land
cover, EDO and IMGW facts — within the deadline, never raising, with provenance, with no data after the
analysis date. Plus a static map PNG for the PDF.

**You do not:** decide drought, compute KBW/SPI/weather, write recommendations, touch the API, reports,
Docker, or any file owned by B. You need nothing from B.

---

## 1. Files you own

```text
app/geo/
├─ __init__.py          exports RealGeoProvider
├─ hosts.py             GEO_HOSTS allowlist
├─ provider.py          RealGeoProvider (bodies; signatures frozen)
├─ uldk.py              parcel lookup
├─ soil_map.py          mapa glebowo-rolnicza WMS GetFeatureInfo (+ IUNG WMS fallback)
├─ soilgrids.py         SoilGrids layers with quantiles
├─ soil.py              SoilInfo assembly + KBW soil category
├─ raster_io.py         GDAL env, COG window reads, host check for /vsicurl/
├─ sentinel2.py         STAC search + per-scene statistics
├─ vegetation.py        VegetationData assembly
├─ dem.py               NMT GUGiK WCS / Copernicus DEM
├─ terrain.py           pure numpy terrain analysis
├─ hydro.py             MPHP WFS / OSM Overpass
├─ landcover.py         ESA WorldCover shares
├─ edo.py               EDO WMS GetFeatureInfo
├─ imgw.py              IMGW synop + hydro warnings (current only)
├─ static_map.py        PNG for the PDF
└─ geometry.py          CRS transforms, buffers, sampling points (private helpers)
config/geo_sources.yaml           endpoints, layer names, licences, attribution texts (with `source:` urls)
config/soil_categories.yaml       soil type code -> KBW category I-IV, WOD thresholds (Dz.U. 2019 poz. 739)
requirements/a-geo.txt            rasterio, pystac-client (+ anything else you add)
scripts/a/spike_sources.py        one request per source, prints what came back
scripts/a/pick_test_parcels.py    real parcel ids via ULDK GetParcelByXY -> tests/fixtures/parcels.json
scripts/a/record_geo_fixtures.py  RealGeoProvider -> tests/fixtures/geo/*.json
scripts/a/run_geo.py              CLI: python -m scripts.a.run_geo <parcel_id> <date> -> pretty JSON + timings
tests/a/**                        unit + integration tests (respx for HTTP)
tests/contract/test_geo_provider_contract.py
tests/fixtures/parcels.json, tests/fixtures/geo/*.json
data/a/**                         anything preprocessed (with entry in data/a/manifest.json: url, date, licence)
docs/PART_A_DATA_GEO.md (this file), docs/DATA_SOURCES.md
```

---

## 2. Functions, file by file

Signatures are a guide; private helpers are free. Everything public returns contract models from
`app/contracts/geo.py` / `parcel.py`.

### `uldk.py`
| Function | Spec |
| --- | --- |
| `parse_query(q: str) -> ParsedQuery` | Classifies the input: full id (`WWPPGG_R.OOOO.[AR_NR.]NR_DZ`, regex `^\d{6}_\d\.\d{4}\.(?:AR_\d+\.)?[0-9A-Za-z/]+$`), «obręb + number» (`Krzewina 134`), or `lat,lon`. Raises `InvalidParcelQuery` with a Polish message. |
| `async get_by_id(parcel_id) -> Parcel` | `request=GetParcelById&id=…&result=geom_wkt,teryt,voivodeship,county,commune,region,parcel` twice (`srid=4326` and `srid=2180`) or once + pyproj transform. ULDK answers text: first line status, then `|`-separated fields — parse defensively. |
| `async get_by_id_or_nr(text) -> list[Parcel]` | `GetParcelByIdOrNr`; may return several parcels (same obręb name in different gminas). |
| `async get_by_xy(lat, lon) -> Parcel \| None` | `GetParcelByXY` with `xy=lon,lat,4326` (check axis order in the spike!). |
| `to_parcel(raw) -> Parcel` | area from EPSG:2180 geometry (m² → ha), centroid in 4326. |
Cache: `geo.uldk`, no expiry.

### `soil_map.py`
| Function | Spec |
| --- | --- |
| `async soil_type_at(lat, lon) -> SoilMapHit \| None` | WMS 1.3.0 GetFeatureInfo on `MapaGlebowoRolnicza/MapServer/WMSServer` (layer names from GetCapabilities, recorded in `geo_sources.yaml`). Returns soil type code (gatunek, e.g. `pgl`) and complex if present. |
| `async dominant_soil_type(parcel) -> SoilMapHit \| None` | 5–9 sample points inside the parcel (`geometry.sample_points`), majority vote; record the share of the majority. |
| `async iung_category_at(lat, lon) -> str \| None` | Fallback: IUNG «Podatność gleb na susze» WMS (find URL in the geoportal «Rolnictwo» module). |

### `soilgrids.py`
| Function | Spec |
| --- | --- |
| `async soil_layers(lat, lon) -> list[SoilLayer]` | sand, silt, clay, soc, bdod, wv0033, wv1500 for depths 0-5…100-200 cm, Q0.05/Q0.5/Q0.95. Primary: REST `rest.isric.org/soilgrids/v2.0/properties/query` (beta, 5 calls/min → one call, cache forever). Fallback: read VRT/COG from `files.isric.org/soilgrids/latest/data/` (Homolosine projection) via `raster_io`. Convert units per SoilGrids docs (integers scaled). |
| `wod_mm(layers, depth_cm=100) -> Range` | Σ (θFC − θWP) × thickness (mm) up to depth; low/mid/high from quantiles. |

### `soil.py`
| Function | Spec |
| --- | --- |
| `category_from_soil_type(code) -> str \| None` | From `config/soil_categories.yaml` (table of Dz.U. 2019 poz. 739: pl/plp/ps/psp → I, pgl/pglp/pgm/pgmp → II, gl/glp/płg/płz/płp → III, gs/gsp/gc/gcp/płi/i/ip → IV). |
| `category_from_wod(mm) -> str` | I < 127.5; II 127.5–169.9; III 170–202.5; IV > 202.5 mm (same regulation). |
| `async soil_info(parcel) -> SourceResult[SoilInfo]` | Order: soil map → IUNG WMS → SoilGrids WOD. Always include SoilGrids `layers` (B needs them for TAW). Set `category_source`. Polish note when falling back. |

### `raster_io.py`
| Function | Spec |
| --- | --- |
| `gdal_env()` | context manager: `GDAL_DISABLE_READDIR_ON_OPEN=EMPTY_DIR`, `CPL_VSIL_CURL_ALLOWED_EXTENSIONS=.tif,.vrt`, `GDAL_HTTP_MULTIRANGE=YES`, `AWS_NO_SIGN_REQUEST=YES`, VSI cache. |
| `read_window(href, geom_crs_wkt, out_res=None) -> (array, transform, nodata)` | checks host ∈ `GEO_HOSTS` before opening; windowed read of the geometry bbox only. |

### `sentinel2.py`
| Function | Spec |
| --- | --- |
| `async search_scenes(bbox_wgs84, start, end, max_cloud=60) -> list[SceneRef]` | pystac-client on `https://earth-search.aws.element84.com/v1`, collection `sentinel-2-c1-l2a` (fallback `sentinel-2-l2a`); filter `datetime <= analysis_date`. |
| `scene_stats(scene, interior_2180) -> SceneStat \| None` (sync, run in thread pool) | Read B04, B08, B8A, B11, SCL for the interior polygon (parcel buffered −10 m); apply scale/offset from item `raster:bands` (handles the PB 04.00 BOA offset); keep SCL 4/5 only; NDVI = (B08−B04)/(B08+B04), NDMI = (B8A−B11)/(B8A+B11); return medians, valid pixels, valid fraction; `None` if valid fraction < 0.3 (record the threshold as our assumption in DATA_SOURCES.md). |

### `vegetation.py`
| Function | Spec |
| --- | --- |
| `async vegetation_data(parcel, req, deadline) -> SourceResult[VegetationData]` | Priority queue of work: (1) current window `[date − current_window_days, date]`, extend to 60 days if no clear scene; (2) same ±`same_window_half_days` window in each of `history_years` previous years; (3) Apr–Aug of each year ≤ date for `season_peaks` (sample ≤ 6 least-cloudy scenes per season). ThreadPool 16–32. Stop at `deadline`; status `partial` + «Przeanalizowano N z M scen Sentinel-2». Interior < 20 pixels → `partial` + note about a small parcel. **No interpretation** (that is B). |

### `dem.py` and `terrain.py`
| Function | Spec |
| --- | --- |
| `dem.async fetch_dem(parcel, buffer_m=200) -> Dem` | GUGiK NMT GRID1 WCS GetCoverage (GeoTIFF, EPSG:2180) for bbox+buffer; resample to 2–5 m by area (time budget). Fallback: Copernicus DEM GLO-30 COG (`cop-dem-glo-30` on Earth Search). |
| `terrain.slope_pct(z, res) -> ndarray` | numpy gradient. |
| `terrain.priority_flood(z) -> ndarray` | own implementation (heapq), **no GPL libraries**. |
| `terrain.depressions(z, filled, res, parcel_mask, min_area_m2) -> list[Depression]` | connected regions of `filled − z > 0`; volume = Σ depth × cell area; ranges from DEM vertical accuracy if documented, else `low=high=None`. `min_area_m2` in config with a note that it is our choice. |
| `terrain.d8(filled) -> ndarray`, `flow_accumulation(dirs) -> ndarray` | standard D8. |
| `terrain.flow_lines(acc, dirs, res, min_upstream_ha) -> list[FlowLine]` | vectorise cells above the threshold. |
| `terrain.twi(acc, slope, res) -> ndarray` | ln(a / tan β). |
| `terrain.async terrain_data(parcel, hydro: HydroData \| None, deadline) -> SourceResult[TerrainData]` | stats inside the parcel; `retention_spots` = depressions + `ditch_outlet` (ditch crossing the boundary near the lowest point, uses `hydro`) + `flow_concentration` (flow line exits the parcel). Geometries back to EPSG:4326. |

### `hydro.py`, `landcover.py`, `edo.py`, `imgw.py`
| Function | Spec |
| --- | --- |
| `hydro.async water_features(parcel, buffer_m) -> SourceResult[HydroData]` | MPHP10k WFS from Wody Polskie (`wody.isok.gov.pl/wss/INSPIRE/…`, find the watercourse layer in GetCapabilities). Fallback: Overpass (`waterway=ditch,drain,stream,river,canal`, `natural=water,wetland`), licence ODbL. Distances in EPSG:2180. |
| `landcover.async landcover(parcel, buffer_m) -> SourceResult[LandCoverData]` | ESA WorldCover 2021 v200 COG tile(s) on AWS; class names exactly as in the WorldCover legend. |
| `edo.async edo_signal(lat, lon, analysis_date) -> SourceResult[EdoData]` | EDO WMS GetCapabilities → layer names and TIME values; GetFeatureInfo on the latest TIME ≤ analysis date for CDI v4.0, SMA, fAPAR anomaly, SPI. Class labels from the EDO legend. |
| `imgw.async imgw_context(lat, lon, analysis_date) -> SourceResult[ImgwData]` | Only if `analysis_date == today` (Europe/Warsaw): `/api/data/synop` (nearest station — station coordinates are not in that endpoint; keep a small station-coordinate table in `data/a/` with source and date) and `/api/data/warningshydro` filtered to drought. Else `missing` + «Dane bieżące IMGW niedostępne dla daty historycznej». Provenance attribution: «Źródłem pochodzenia danych jest Instytut Meteorologii i Gospodarki Wodnej – Państwowy Instytut Badawczy» + «Dane … zostały przetworzone». |

### `provider.py`
| Method | Spec |
| --- | --- |
| `find_parcels(query)` | `uldk.parse_query` → `get_by_id` / `get_by_id_or_nr` / `get_by_xy`. |
| `parcel_at_point(lat, lon)` | `uldk.get_by_xy`. |
| `collect(req)` | `asyncio.gather` of soil, vegetation, hydro, landcover, edo, imgw; terrain after hydro (needs it) but started as soon as the DEM is fetched; global deadline via `asyncio.wait_for` per task with remaining budget; wrap every task so exceptions become `SourceResult(status=MISSING, error=..., notes_pl=[...])`; set `elapsed_s`. |
| `render_static_map(parcel, bundle, width_px)` | `static_map.render` — hillshade from the DEM (or GUGiK orthophoto WMS GetMap as background), parcel outline, retention spots numbered as in the report, flow lines, water features, scale bar, north arrow, attribution line. matplotlib → PNG bytes. |

---

## 3. Tasks by checkpoint (tick as you go)

### T0 (with B, ≈ 20 min)
- [x] One of you commits the T0 files from `CONTRACTS.md` §5; both pull.

### CP0 — spikes (→ 15:30)
- [x] `scripts/a/spike_sources.py`: one call to ULDK, soil map WMS (GetCapabilities + GetFeatureInfo), SoilGrids REST, Earth Search STAC, one COG window read, NMT WCS GetCapabilities + small GetCoverage, MPHP WFS GetCapabilities, Overpass, WorldCover, EDO GetCapabilities, IMGW synop + warningshydro. Write exact URLs, layer names, attribute names into `config/geo_sources.yaml`.
- [x] `scripts/a/pick_test_parcels.py` → `tests/fixtures/parcels.json`: 6–8 real agricultural parcels via `GetParcelByXY` (different voivodeships; light and heavy soils; flat and sloped; < 1 ha and > 20 ha; at least one id with `AR_`). Push immediately — B and the frontend use it.
- [ ] Fill `app/geo/hosts.py`.

### CP1 — parcel + soil (→ 19:00)
- [ ] `uldk.py` + tests (all three query types, ambiguous «obręb nr», invalid input, not found).
- [ ] `soil_map.py`, `soilgrids.py`, `soil.py`, `config/soil_categories.yaml` + tests.
- [ ] `provider.find_parcels`, `parcel_at_point`; `collect` returning real `soil` and `MISSING` placeholders for the rest.
- [ ] `scripts/a/run_geo.py`, `scripts/a/record_geo_fixtures.py`; record fixtures for 3 parcels × 3 dates (today, 2018-07-10, 2023-05-31); push.

### CP2 — satellite, EDO, IMGW (→ 23:00)
- [ ] `raster_io.py`, `sentinel2.py`, `vegetation.py` (+ test that no scene is after `analysis_date`; test of the offset handling on one pre-2022 and one post-2022 scene).
- [ ] `edo.py`, `imgw.py`.
- [ ] Re-record fixtures; push.

### CP3 — terrain, hydrology, land cover, static map (→ 03:00)
- [ ] `hydro.py` (MPHP + OSM fallback), `landcover.py`.
- [ ] `dem.py`, `terrain.py` (+ unit test: artificial bowl with known volume; flat plane → no depressions).
- [ ] `static_map.py` + `render_static_map`.
- [ ] Re-record fixtures for all test parcels; push.

### CP4 — performance and robustness (→ 07:00)
- [ ] Profile `collect` per source; p95 ≤ 22 s cold, ≤ 3 s warm (cache).
- [ ] Edge cases: multipolygon, parcel < 0.2 ha, forest/water/built-up parcel, date in 2016 (fewer S2 years), zero clear scenes, every source down (mock) → still a valid bundle.
- [ ] `tests/contract/test_geo_provider_contract.py` green on 2 parcels.

### CP5 — docs (→ 10:00)
- [ ] `docs/DATA_SOURCES.md`: per source — what, URL, scope, live vs preprocessed + download date, resolution, licence, exact attribution text, known limits.
- [ ] Final fixtures for all parcels; push.

---

## 4. Acceptance criteria (Part A done)

- `python -m scripts.a.run_geo <id> <date>` works for every parcel in `parcels.json` and prints a bundle
  where `soil`, `vegetation`, `terrain`, `hydro`, `landcover` are `ok` or explained `partial`.
- `collect()` never raises, respects `deadline_s`, uses no data after `analysis_date`.
- Every number traceable to a source in `geo_sources.yaml` / `DATA_SOURCES.md`; every threshold either
  from a cited document or explicitly labelled «our choice» there.
- No GPL/AGPL dependency in `requirements/a-geo.txt`.
