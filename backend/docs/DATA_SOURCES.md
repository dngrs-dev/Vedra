# Data sources (Part A: geo data)

What the backend fetches about a parcel, from where, what is read live and what was prepared in advance, under
which licence, and what each source cannot tell. The machine-readable twin of this page is
[`config/geo_sources.yaml`](../config/geo_sources.yaml): every URL, layer name, threshold and observation below is
recorded there with its `source:`. Prepared files are listed in [`data/a/manifest.json`](../data/a/manifest.json).
All observations quoted here were made on **2026-11-21** from the development machine (Poland).

Every populated `SourceResult` carries one or more `Provenance` records with the source, URL, fetch time,
live or cached status, resolution, licence and attribution where available. Data gaps have Polish
explanations. Cadastral boundaries and names come from ULDK or its EGiB fallback.

## 1. Summary

| Category (task §5.2) | Source | Used for | Live / prepared | Resolution |
| --- | --- | --- | --- | --- |
| Spatial: parcels | ULDK GUGiK; fallback: EGiB GeoParquet export (GUGiK) + PRG WFS | parcel geometry, id, names | live | cadastral |
| Soil | Mapa glebowo-rolnicza (GUGiK WMS) | soil texture code → KBW soil category I–IV | live | 1:5 000 |
| Soil | SoilGrids 2.0 (ISRIC) tiles; fallback: REST API | texture, organic carbon, bulk density per depth → water retention (Saxton & Rawls 2006) | live (test parcels: also prepared) | 250 m |
| Satellite | Sentinel-2 L2A on Microsoft Planetary Computer; fallback: Earth Search (Element 84) | NDVI / NDMI per scene, 10-year history | live (test parcels: also prepared) | 10 m |
| Spatial: terrain | NMT GRID1 GUGiK (WCS); fallback: Copernicus DEM GLO-30 | slope, depressions, flow lines, retention spots | live (test parcels: prepared NMT) | 1 m → 2–10 m; 30 m |
| Hydrological | BDOT10k water network (GUGiK WMS); fallback: OpenStreetMap (Overpass) | ditches, streams, canals, ponds around the parcel | live | 1:10 000 |
| Spatial: land use | ESA WorldCover 2021 v200 | land-cover shares in the parcel and in a 500 m ring | live | 10 m |
| Drought background | European Drought Observatory (Copernicus EMS), WCS | Combined Drought Indicator class for the dekad | live | 0.04° |
| Meteorological (current) | IMGW-PIB public data API | nearest synoptic station, hydrological drought warnings | live, today only | station |

Weather history (precipitation, evapotranspiration) is Part B's (Open-Meteo); see the methodology document.

## 2. Sources

### 2.1 ULDK GUGiK: parcel lookup
- **URL:** `https://uldk.gugik.gov.pl/`, requests `GetParcelById`, `GetParcelByIdOrNr`, `GetParcelByXY`, geometry in
  EPSG:2180.
- **Use:** turns a parcel id, «obręb + number» or a map click into the parcel geometry and its names.
- **Live**, cached without expiry (`geo.uldk`). Typical answer 0.3 s.
- **Licence:** PZGiK data, free of charge (GUGiK terms of service). No attribution text published.
- **Limits:** on 2026-11-21 around 19:00 ULDK started to answer *every* API call from the development machine with
  HTTP 302 to `integracja01.gugik.gov.pl/resp/uldk.php`, which returns `0` and a hex string instead of records (the
  documentation page still loaded). The fallback below is used automatically, for lookups by id and by point.
  «Obręb + number» queries fall back too, for obręb names that occur at most 5 times in Poland (PRG name
  lookup; «Nowa Wieś» occurs 108 times and then the user is asked for the id or a map click).

### 2.2 EGiB GeoParquet export + PRG: ULDK fallback
- **URLs:** `https://opendata.geoportal.gov.pl/InneDane/latest_exports/eziudp_wfs/PARQUET/0_dzialki.parquet`
  (named in the task, §5.2) and the PRG WFS `https://mapy.geoportal.gov.pl/wss/service/PZGIK/PRG/WFS/AdministrativeBoundaries`.
- **The file:** 4.6 GB, rebuilt daily, GeoParquet 1.1 with 38.9 million parcels in 594 spatially clustered row
  groups.
- **How it is read:** only the footer (about 1 MB, cached per file version) and the needed column chunks, through 16
  parallel HTTP range requests. One stream gives about 0.5 MB/s, 16 streams about 7 MB/s.
  - By point: row groups are chosen by their bounding-box statistics.
  - By id: the obręb envelope from PRG selects the row groups.
- **Speed:** the CP4 probe measured 4–7 s. A live fallback is bounded to 8 s, and successful responses
  are cached for 30 days. The primary ULDK HTTP attempt uses a 3 s timeout.
- **Names:** voivodeship and county names come from `data/a/teryt_names.json`, built from PRG (prepared
  2026-11-21). Commune and obręb names come from the export; some are upper case, as stored in EGiB.
- **Check:** the same parcels as ULDK, with the same areas (Września 9.08 ha, Kętrzyn 150.23 ha, Hrubieszów 1.02 ha).
- **Licence:** PZGiK data, free of charge. The attribution wording is ours, since none is published: «Dane EGiB:
  Główny Urząd Geodezji i Kartografii (geoportal.gov.pl)».
- **CRS:** the export is "ETRF2000-PL / CS92"; it is used as EPSG:2180 (same projection, frames differ by cm).

### 2.3 Mapa glebowo-rolnicza (GUGiK WMS): soil category
- **URL:** `https://mapy.geoportal.gov.pl/wss/service/pub/guest/MapaGlebowoRolnicza/MapServer/WMSServer`, layer
  `KONTURY_GLEBOWE`, `GetFeatureInfo` (text/xml).
- **Use:** the texture code of the top layer (`PODLOZE1`) at 9 points inside the parcel. The majority code decides.
  - The code is mapped to the KBW soil category I–IV with the table of **Dz.U. 2019 poz. 739**, copied verbatim
    into `config/soil_categories.yaml`.
  - When the map has no code, or the code is not in that table, the category comes from WOD (§2.4) and the
    report says so.
- **Live**, cached for 30 days. Currency date of the map contour reported («stan na rok …»).
- **Licence:** GetCapabilities declares «Fees: no conditions apply» and «AccessConstraints: otherRestrictions».
  The service declaration is recorded for attribution and does not specify a redistribution licence.
- **Limits:** forests and built-up land have no texture code (e.g. complex «Ls»).
- **Not used:** the IUNG «Podatność gleb na suszę» WMS is announced on geoportal, but its endpoint was not found
  during the spike.

### 2.4 SoilGrids 2.0 (ISRIC): soil profile and water retention
- **URLs:** tiles under `https://files.isric.org/soilgrids/latest/data/`; fallback REST
  `https://rest.isric.org/soilgrids/v2.0/properties/query`.
- **Use:** sand, silt, clay, organic carbon and bulk density for 6 depths (0–200 cm), each as Q0.05 / Q0.5 / Q0.95.
- **Why tiles, not REST:** the REST API needed 26–163 s per point, or answered HTTP 504. The 450 × 450 px tiles
  behind the VRTs are read pixel by pixel. A full profile (90 reads) takes about 2 s.
  - Check: identical values to REST at all 8 test points (every property, depth and quantile).
  - Tile index for Poland: `data/a/soilgrids_tiles.json`, prepared 2026-11-21. The tiling differs per property,
    so it is indexed per property.
- **Water retention:** field capacity (33 kPa) and wilting point (1500 kPa) are computed with the **Saxton &
  Rawls (2006)** pedotransfer functions (SSSAJ 70:1569–1578, Table 1), from sand, clay and organic matter
  (OM = 1.724 × SOC).
  - WOD = Σ(θFC − θWP) over 0–100 cm.
  - The band low–high is the range of the equations over the SoilGrids quantiles.
- **Why not SoilGrids' own `wv0033` / `wv1500`:** at the sandy test parcels they give a field capacity of
  0.38–0.43 m³/m³ at 71–78 % sand, and WOD 204–240 mm, which is category IV. The 1:5 000 map says I or II there.

  | Agreement with the map category (5 parcels with a map code) | exact | within one category |
  | --- | --- | --- |
  | SoilGrids wv0033/wv1500 | 1 | 1 |
  | Saxton & Rawls on SoilGrids texture | 2 | 4 |
- **Prepared:** REST answers for the 8 test parcels (`data/a/soilgrids_points.json`, 2026-11-21).
- **Licence:** CC BY 4.0. Cite Poggio et al. (2021), SOIL 7, 217–240.
  [ISRIC terms](https://isric.org/explore/soilgrids/), [SoilGrids paper](https://doi.org/10.5194/soil-7-217-2021).
- **Limits:** 250 m model cells. At one test point (Inowrocław) the model has no values; this is reported.

### 2.5 Sentinel-2 L2A: vegetation (NDVI, NDMI)
- **Primary:** Microsoft Planetary Computer, STAC `https://planetarycomputer.microsoft.com/api/stac/v1`,
  collection `sentinel-2-l2a`. Assets are signed with an anonymous SAS token.
- **Fallback:** Earth Search (Element 84) `https://earth-search.aws.element84.com/v1` (`sentinel-2-l2a`, then
  `sentinel-2-c1-l2a`).
- **Why this order:** reading one parcel window of one scene took 22.6 s from Earth Search's store (AWS us-west-2)
  and 1.3–1.9 s from Planetary Computer (West Europe). Only the latter fits a 10-year history into the time budget.
  Planetary Computer has full coverage from 2016 (125–470 scenes a year at the test point).
- **Per scene:** bands B04, B08, B8A, B11 and the SCL mask are read over the parcel interior (parcel buffered by
  −10 m, 10 m grid).
  - Only SCL classes 4 (vegetation) and 5 (bare soil) are kept.
  - A scene counts as clear when at least 30 % of the interior is valid.
  - NDVI = (B08 − B04)/(B08 + B04), NDMI = (B8A − B11)/(B8A + B11); medians are reported.
- **Reflectance offset:** read from each product's `MTD_MSIL2A.xml`.
  - Processing baselines 02.12 and 03.00 have no offset.
  - Baselines 04.00, 05.09, 05.10 and 05.11 have `BOA_ADD_OFFSET = -1000`.
  - Quantification is 10 000 throughout. The offset is applied per baseline.
  - On Earth Search `sentinel-2-l2a` the pixels are already harmonised: the same acquisition gives B04 284 there
    and 1284 in `sentinel-2-c1-l2a`.
- **Duplicates:** reprocessed products and overlapping MGRS tiles are reduced to one scene per datatake. The highest
  processing baseline is kept.
- **Windows:**
  - Current: 30 days, extended to 60 if there is no clear scene.
  - The same window in each of the previous 10 years: the 3 least cloudy scenes each.
  - Season peak (April–August): up to 6 least cloudy scenes a year.
  - Never a scene after the analysis date.
- **Live**, with per-scene results cached permanently. Scenes left unread at the deadline continue in the
  background. Prepared: per-scene results for the test parcels and fixture dates (`data/a/s2_scene_stats.json`).
- **Licence:** Copernicus Sentinel data, free, full and open. Attribution: «Contains modified Copernicus Sentinel
  data [year]». Reports fill in the observation years for each source used.
  [Copernicus Sentinel legal notice](https://ewds.climate.copernicus.eu/licences/ec-sentinel),
  [Planetary Computer terms](https://planetarycomputer.microsoft.com/terms).
- **Limits:**
  - Parcels narrower than about 20 m have no interior after the −10 m buffer: vegetation is `missing`.
  - Fewer than 20 interior pixels: `partial` with a note.
  - On a cold analysis of «today», some scenes may still be in progress at the deadline: the report says how many
    were processed.

### 2.6 Terrain: NMT GUGiK and Copernicus DEM
- **NMT GRID1:** `https://mapy.geoportal.gov.pl/wss/service/PZGIK/NMT/GRID1/WCS/DigitalTerrainModelFormatTIFF`,
  coverage `DTM_PL-KRON86-NH_TIFF`, 1 m, read at 2/5/10 m for the parcel + 200 m (at most 250 000 cells).
  - The service needed 52–164 s per request, so it can never answer within the analysis budget.
  - Test parcels use prepared NMT (`data/a/nmt/`, 7 of 8 parcels, 2026-11-21).
  - Other parcels get it in the background, for their next analysis.
  - Licence declared: «Fees: none; AccessConstraints: none».
- **Copernicus DEM GLO-30** (`copernicus-dem-30m.s3.amazonaws.com`, 30 m) is used when NMT is not available.
  - It is a **surface** model: trees and buildings are included. The report says so, and the terrain result is
    `partial`.
  - Attribution: «produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH
    2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved».
  - Organisations administering or operating the Copernicus programme incur no liability for use of the model.
    [WorldDEM-30 licence, Article 6](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Data/DEM/resources/license/License-COPDEM-30.pdf).
- **Analysis** (own numpy code, cited methods):
  - Depression filling: priority-flood (Barnes et al. 2014).
  - Flow directions: D8 (O'Callaghan & Mark 1984).
  - Wetness index: TWI (Beven & Kirkby 1979).
  - Retention spots: depressions ≥ 100 m² and ≥ 0.1 m deep (`Z`), flow concentration where a flow line leaves the
    parcel (`S`), ditch crossings of the boundary (`R`).
  - Test: a synthetic bowl's volume is within 3 % of the analytic value.
  - Volumes have no uncertainty band, because the DEM's vertical accuracy is not documented by the services.

### 2.7 Hydrology: BDOT10k water network
- **URL:** `https://mapy.geoportal.gov.pl/wss/service/pub/guest/kompozycja_BDOT10k_WMS/MapServer/WMSServer`.
  - Layers: `row` (ditches), `kan`/`kanOkr` (canals), `rz`/`rzOk` (streams), `WPow` (standing / flowing water).
- **Method:** each layer is drawn at 2 m over the parcel + 500 m, with a coarser grid for large areas.
  Connected drawn pixels become features, with
  distance to the parcel and ditch crossings. Names and kinds come from `GetFeatureInfo` for the 20 nearest.
- **Live**, cached for 30 days. Licence declared: «Fees: Brak opłat».
- **Why not the planned sources:** the planned MPHP (Wody Polskie) has no vector access (WMS only, without
  GetFeatureInfo), and BDOT10k's vector services refused access.
- **Fallback:** OpenStreetMap via Overpass, with the ODbL 1.0 attribution and licence link in reports.
  The development network could not reach the fallback during the original spike. Its processing was tested with payload fixtures.
  [OpenStreetMap copyright and licence](https://www.openstreetmap.org/copyright).
- **Limits:**
  - Distances can be short by half the symbol width.
  - A connected ditch network counts as one feature.
  - Drainage pipes (underground) are not in BDOT10k.

### 2.8 Land cover: ESA WorldCover 2021 v200
- **URL:** `https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/…`, 10 m. Class names come from the
  legend embedded in the files.
- **Use:** shares of each class in the parcel and in the 500 m ring around it.
- **Licence:** CC BY 4.0. Attribution: «© ESA WorldCover project 2021 / Contains modified Copernicus Sentinel data
  (2021) processed by ESA WorldCover consortium».
- **Limits:** the map uses observations through 31 December 2021. Earlier analysis dates receive a missing-data
  note, and later dates use 2021 as a dated reference.
  [ESA WorldCover product manual, §3.4.3](https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/docs/WorldCover_PUM_V2.0.pdf).

### 2.9 European Drought Observatory (Copernicus EMS)
- **URL:** WCS `https://drought.emergency.copernicus.eu/api/wcs`, layer `cdiad` (Combined Drought Indicator v4.1).
- **Use:** the CDI class at the parcel for the latest dekad that **ended** on or before the analysis date. Labels
  come from the CDI factsheet v4.1.1, Table 1: No drought, Watch, Warning, Alert, Recovery, Temporary soil-moisture
  recovery, Temporary vegetation recovery.
- **Terms:** public data under the CEMS EDO/GDO conditions. The derived-product attribution is
  «Contains modified Copernicus Emergency Management Service information [year]».
  [EDO/GDO terms](https://drought.emergency.copernicus.eu/terms%26conditions/).
- **Limits:**
  - The public services give classes, not indicator values, so `cdi_value`, `sma`, `fapar_anomaly` and `spi3` stay
    empty and the report says so.
  - Grid of 0.04° (about 4.4 km north–south, 2.7 km east–west in Poland).

### 2.10 IMGW-PIB public data
- **URLs:** `https://danepubliczne.imgw.pl/api/data/synop`, `…/warningshydro`; station coordinates from `…/meteo`.
  The station list is prepared in `data/a/imgw_synop_stations.json` (56 stations, 2026-11-21).
- **Use:** only when the analysis date is today.
  - The nearest synoptic station's latest observation: temperature, precipitation, humidity.
  - Hydrological drought warnings for the parcel's voivodeship.
- **Attribution (IMGW-PIB terms):** «Źródłem pochodzenia danych jest Instytut Meteorologii i Gospodarki Wodnej –
  Państwowy Instytut Badawczy. Dane Instytutu Meteorologii i Gospodarki Wodnej – Państwowego Instytutu Badawczego
  zostały przetworzone.»
  [Regulamin IMGW-PIB](https://danepubliczne.imgw.pl/regulations).
- **Limits:**
  - Current data only.
  - Warnings are matched by voivodeship: a warning may concern another catchment in that voivodeship (noted).

## 3. Prepared data (`data/a/`)

| File | Content | Source | Prepared | Script |
| --- | --- | --- | --- | --- |
| `soilgrids_tiles.json` | SoilGrids tile index for Poland, per property | files.isric.org VRTs | 2026-11-21 | `scripts/a/build_soilgrids_tiles.py` |
| `teryt_names.json` | 16 voivodeship and 380 county names by TERYT code | PRG WFS | 2026-11-21 | `scripts/a/build_teryt_names.py` |
| `imgw_synop_stations.json` | 56 synoptic stations with coordinates | IMGW API | 2026-11-21 | `scripts/a/build_imgw_stations.py` |
| `soilgrids_points.json` | SoilGrids REST answers for the 8 test parcels | rest.isric.org | 2026-11-21 | `scripts/a/prefetch_soilgrids.py` |
| `s2_scene_stats.json` | per-scene NDVI/NDMI for the test parcels × fixture dates | Planetary Computer / Earth Search | 2026-11-21 | `scripts/a/prefetch_s2.py` |
| `nmt/*.tif` | NMT for 7 test parcels + 200 m | GUGiK WCS | 2026-11-21 | `scripts/a/prefetch_nmt.py` |

The prepared files save time. Sentinel-2 scene stats apply to the exact recorded parcel interior.
When its boundary changes, the collector uses the current geometry to read the raster. Reports and
recommendations are computed at request time. The fixture recorder can reuse previously verified
parcel boundaries while it refreshes measurements from the same providers.

## 4. Our parameters and assumptions

Every threshold is listed in `config/geo_sources.yaml`, marked either with its source or as «OUR CHOICE».

| Parameter | Value | Basis |
| --- | --- | --- |
| Sentinel-2 interior buffer | −10 m | spec; keeps edge pixels out |
| Valid fraction for a clear scene | ≥ 30 % | our choice |
| Small-parcel warning | < 20 interior pixels | our choice |
| Same-window scenes per year | 3 least cloudy | our choice (time budget) |
| Sentinel-2 catalog search | Half of its source budget | our choice (reserve time to read available scenes) |
| Dated vegetation assessment cache | 10 minutes | our choice (allow refresh of incomplete data) |
| Season | April–August, ≤ 6 scenes | spec |
| Cloud filter in search | < 60 % scene cover | spec |
| DEM buffer / max grid | 200 m / 250 000 cells | spec / compute budget |
| Depression | ≥ 100 m², ≥ 0.1 m | our choice |
| Flow lines | ≥ 1 ha upslope | our choice |
| Water search radius | 500 m | `GeoRequest.hydro_buffer_m` |
| Soil sampling | 9 points, majority | our choice |
| OM / SOC factor | 1.724 | van Bemmelen factor (Pribyl 2010) |
| WOD category thresholds | 127.5 / 170 / 202.5 mm | Dz.U. 2019 poz. 739 |

## 5. Speed, caching and failures

- **Time budget:** `collect()` has 22 s. Independent sources run in parallel and return `partial` or
  `missing` when the deadline prevents a full result. DEM and scene reads can continue in the
  background. The vegetation search keeps results from catalog windows that finished before its deadline.
- **Caching:** everything static is cached on disk (parcels, soil, DEM, terrain analysis, water network, land cover,
  per-scene Sentinel-2 results, EDO dekads), so a repeated analysis needs a few seconds.
- **No silent failures:** each upstream failure is recorded in `error` and explained in `notes_pl`. A bundle is
  always returned, also with every source down (tested).
- **Fallbacks:**

  | Primary | Fallback |
  | --- | --- |
  | ULDK | EGiB GeoParquet |
  | Planetary Computer | Earth Search |
  | SoilGrids tiles | SoilGrids REST |
  | NMT | Copernicus DEM |
  | BDOT10k | OpenStreetMap |
- **Event loop:** GDAL work never runs on the event loop. A blocked loop once broke the deadline (142 s), and a
  regression test now guards this.

### Live performance check

The CP4 profile covered two parcels and the three checklist dates, with a fresh disk cache on the first pass.
The second pass repeated the same requests. The figures are seconds at the 95th percentile, rounded to
two places. A zero in the table is a rounded reading. Cold vegetation could return partial coverage.

| Stage | Cold p95 | Warm p95 |
| --- | ---: | ---: |
| Complete geo bundle | 21.05 | 0.06 |
| Soil | 2.09 | 0.03 |
| Sentinel-2 | 21.02 | 0.00 |
| Terrain | 4.09 | 0.03 |
| Hydrology | 3.23 | 0.03 |
| Land cover | 3.81 | 0.00 |
| EDO | 2.76 | 0.02 |
| IMGW | 1.96 | 0.01 |

Reproduce the profile from `backend` with `python -m scripts.a.profile_collect --parcels 2`.
The live edge run also covered a forest parcel, a lake above 7,000 ha, two built-up parcels and a
2016 analysis date. The lake lacked terrain and hydrology within the deadline. Other available
sources still returned valid data. [Recorded edge cases](../tests/a/data/edge_parcels.json).
