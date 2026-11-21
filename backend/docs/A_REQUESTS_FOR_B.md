# Requests from Part A to Part B

Written by Part A (person A's agent) on 2026-11-21 after CP0–CP1. Each item says **what to change in
Part B's files**, **why** (with the evidence), and how urgent it is. Part A did not edit any B file, and
nothing here changes the frozen contract. The EDO contract proposal made after CP1 is **withdrawn** (§4).

State of Part A on branch `part_A` (commit `2538d48`): ULDK lookup, soil (soil map + SoilGrids + KBW
category) and `collect()` are real. Vegetation, terrain, hydro, land cover, EDO and IMGW return `missing`
with a Polish note until CP2/CP3. 24 recorded fixtures exist: 8 parcels × {2026-11-21, 2018-07-10, 2023-05-31}.

---

## 1. Do now

### 1.1 Get Part A's files onto `backend` (git, no code)
- **What:** merge `origin/part_A` into `backend`, e.g. `git checkout backend && git merge origin/part_A`.
- **Why:** `tests/fixtures/parcels.json`, `tests/fixtures/geo/*.json` (read by `app/fakes/fixture_geo.py`),
  `app/geo/**` (used when `GEO_PROVIDER=real`), `config/geo_sources.yaml`, `config/soil_categories.yaml` and
  `data/a/**` exist only on `part_A`. With the current `backend` branch, `GEO_PROVIDER=fixtures` finds no
  files and `GEO_PROVIDER=real` hits the T0 stubs (`NotImplementedError`).
- **Conflicts:** none expected. The file sets are disjoint. The only shared change is the T0 checkbox in
  `docs/PART_A_DATA_GEO.md`, which both branches ticked identically. Please leave A's files (including
  `PART_A_DATA_GEO.md`) to A from now on.

### 1.2 Dockerfile: copy `data/`, and the geo fixtures if fixture mode is used in Docker
- **What:** in `backend/Dockerfile`, stage `base`, add `COPY data/ ./data/`. If you deploy with
  `GEO_PROVIDER=fixtures`, also copy `tests/fixtures/geo/` and `tests/fixtures/parcels.json` into the image.
- **Why:** `app/geo/soilgrids.py` reads preprocessed SoilGrids answers from `data/a/soilgrids_points.json`.
  The live SoilGrids API takes 26–163 s per point, or returns HTTP 504 (spike and prefetch 2026-11-21).
  Without the file, the 8 test parcels lose their soil profiles in the deployed image. `FixtureGeoProvider`
  reads `tests/fixtures/geo/`, which the runtime stage does not contain today.

### 1.3 PDF step: tolerate `render_static_map` failures (implemented since CP3)
- **What:** wherever `pdf.py` / the job calls `geo.render_static_map(...)`, catch `NotImplementedError`
  (and, defensively, any exception) and render the PDF without the map. Your parcel routes already do this
  for lookups.
- **Why:** `RealGeoProvider.render_static_map` is implemented in CP3 (`static_map.py`).

---

## 2. Soil: how to read what A returns (B judges; A only measures)

### 2.1 `soil.data.category_source` matters for confidence
- `"soil_map"`: the category comes from the soil-map texture code (1:5000), via the table in Dz.U. 2019
  poz. 739 (copied verbatim into `config/soil_categories.yaml`).
- `"soilgrids_wod"`: the soil map gave a code the regulation does not list (seen: `li`, `l`, alluvial `c`, `bc`)
  or no code at all. The category then comes from SoilGrids WOD (250 m model, 0–100 cm). In the test set
  this applies to `060406_2.0136.AR_5.1077/6` (`li` → III) and `121405_5.0016.480/3` (`l` → II).
- **Suggested:** show `soil_type_name_pl` / `soil_type_code` and the category source in the report. When the
  source is `soilgrids_wod`, state lower confidence in the KBW verdict's uncertainty section.

### 2.2 `soil.data.layers` can be empty, so TAW / FAO-56 must not assume it
- **Cases:** (a) first analysis of a parcel not in `data/a/`: SoilGrids does not answer within the 22 s budget;
  (b) SoilGrids has only nulls at the point. This happens for test parcel `040704_2.0012.63/1`, so its soil is
  `partial`, with category III from the map and no layers.
- **What to change (your CP3: `analytics` TAW / irrigation):** when `layers == []` or `wod_mm is None`, do not
  compute TAW. Mark the «what if» SOM scenario and the irrigation dose as unavailable, with a Polish reason.
  Do not invent texture-based defaults unless you cite a source for them.
- **Good to know:** the SoilGrids request keeps running in the background after the deadline and fills the
  disk cache, so the same parcel analysed again a few minutes later has layers. The Polish note says so.
  This works because your runner uses the server's main event loop (`jobs/runner.py`). Keep it that way. If
  you run several uvicorn workers, keep the default shared `CACHE_DIR` so they share the result.

### 2.3 `wod_mm` semantics
- Summed over **0–100 cm** (`wod_depth_cm`), not over the crop's root zone. If you need WOD for a root depth,
  compute it from `layers` (θFC − θWP per layer, thickness in mm).
- `wod_mm.low` / `.high` are an **indicative band**: θFC and θWP quantiles are paired as Q0.05 with Q0.05 and
  Q0.95 with Q0.95 (our choice, explained in `soilgrids.wod_mm`). They are not a 90 % confidence interval.
- When the map category and the SoilGrids WOD category disagree, `notes_pl` carries an explicit
  «Niepewność: …» line. Example: `303005_5.0323.25/7`, where the map says `ps` → I but WOD ≈ 230 mm → IV. Your
  builder already copies `notes_pl` into limitations, so no change is needed unless you want it in the
  verdict text instead.

### 2.4 `kbw_category` can still be `None`
- When the map has no regulation code **and** SoilGrids is missing or null. Your `kbw.assess` already handles
  `None`; just keep that path tested with real fixtures once merged.

---

## 3. Parcel lookup

- `Parcel.teryt` = `WWPPGG_R` (commune TERYT + commune-type digit), taken from the parcel id. ULDK's own
  `teryt` result field returns the full parcel id, so it is not used.
- `find_parcels("<obręb> <nr>")` can return many parcels. «Nowa Wieś 1» returned 59 parcels across Poland
  (live, 2026-11-21, 4 s), each with full geometry. **Suggested** for `/api/parcels/search` and the frontend:
  show `commune`, `county` and `voivodeship` in the candidate list. Consider capping or paginating the
  response, which is B's call.
- Errors: `InvalidParcelQuery` (Polish message, but your handler uses its own text, which is fine),
  `ParcelNotFound`, `UpstreamUnavailable`, all as in CONTRACTS.md.

---

## 4. Coming in CP2/CP3: what the data will look like (plan from the CP0 spike)

| Source | What B will get | Why (spike 2026-11-21, details in `config/geo_sources.yaml`) | What B should do |
| --- | --- | --- | --- |
| EDO | `cdi_class` (legend label, e.g. «Watch» / «Warning» / «Alert»), `date_used`. **`cdi_value`, `sma`, `fapar_anomaly`, `spi3` stay `None`.** | EDO's public WMS has no GetFeatureInfo; the WCS returns only uint8 **class codes**, not values. | Use EDO as a categorical cross-check only. |
| Terrain | `dem_source="copernicus_dem_30m"`, `resolution_m≈30` for most parcels; `gugik_nmt_1m` only where A has preprocessed NMT (test parcels). | GUGiK NMT WCS needs about 52 s per request regardless of area. | Word retention-spot findings by `dem_source` / `resolution_m`: a 30 m DEM cannot resolve small depressions or furrows. |
| Hydro | Often `partial` or `missing`. | MPHP is exposed only as an image WMS (vector endpoints answer 401). OSM Overpass was unreachable from all 4 endpoints on 2026-11-21. | Treat «no water feature found» (`ok`, empty list) differently from «hydro unavailable» (`missing`). Never conclude «no ditches» from `missing`. |
| IMGW | `missing` for any historical date (contract). | — | Already planned. |

**EDO contract proposal: withdrawn (decided by person A, 2026-11-21). No contract change.** The CP1
proposal to add `sma_class` / `fapar_class` / `spi3_class` to `EdoData` is dropped:
- `cdi_class` already carries that information. By the CDI definition (factsheet v4.1.1, Table 1), *Watch*
  is triggered by SPI, *Warning* by soil moisture (SMA ≤ −1) and *Alert* by fAPAR (anomaly ≤ −1).
- B already has the underlying signals from better-resolved sources: SPI and the soil-moisture anomaly from
  Open-Meteo (B's own pipeline), vegetation anomalies from Sentinel-2 (`bundle.vegetation`).
- The extra class labels could only be mapped from legend images, with the same partial verification as CDI.
So `cdi_value`, `sma`, `fapar_anomaly` and `spi3` stay `None` permanently. **B should treat EDO as a
categorical cross-check (`cdi_class`, `date_used`) and never wait for those numeric fields.**

---

## 4a. Added after CP2 (Sentinel-2, EDO, IMGW are now real)

### Vegetation (`bundle.vegetation`)
- **Cold analyses are usually `partial`.** Each clear Sentinel-2 scene costs about 4 MB of COG tiles (10 m
  bands are stored as 1024×1024 deflate tiles of about 1.4 MB). On the dev link (about 140 KB/s per stream to
  us-west-2) only about 3–10 of the 40–70 scenes fit into 22 s. The current window is processed first, so `current` is
  the most likely field to be filled. History (`same_window_by_year`, `season_peaks`) fills up on later runs:
  unfinished scenes keep being read in the background into a permanent cache. The test parcels get
  preprocessed scene statistics in `data/a/s2_scene_stats.json`, so they are complete in any deployment once
  `data/` is copied (§1.2).
- **Read the keys, not only the values.** A year **missing** from `same_window_by_year` / `season_peaks` means
  «not processed in time» or «no Sentinel-2 L2A archive that year» (before 2016; a Polish note lists those
  years). A year **present with `[]` / `None`** means scenes were checked and none was clear. Compute
  percentiles / VCI only over present years, and state the number of years used.
- `same_window_by_year` holds at most the **3 least-cloudy** scenes per previous year (our choice, for the time
  budget; `config/geo_sources.yaml` `sentinel2_processing.same_window_max_scenes`).
- `scenes_considered` vs `scenes_processed` tells you how complete the history is. `notes_pl` says it in Polish
  («Przeanalizowano N z M scen…»).
- NDVI/NDMI are medians over clear interior pixels (SCL 4/5, parcel buffered −10 m). Earth Search's
  `sentinel-2-l2a` metadata declares a −0.1 BOA offset, but its pixels are harmonized. A verified this against
  `sentinel-2-c1-l2a` on the same acquisitions (`config/geo_sources.yaml` `earth_search.offset_note`), so values
  are consistent across 2017–2026. Nothing for B to change; mention it in METHODOLOGY.md if you describe NDVI.

### EDO (`bundle.edo`)
- `cdi_class` uses the CDI factsheet v4.1.1 Table 1 labels (English): `No drought`, `Watch`, `Warning`,
  `Alert`, `Recovery`, `Temporary Soil Moisture recovery`, `Temporary vegetation recovery`. **B should
  translate them for the report** (Part A returns the provider's labels). Note that `No drought` and the three
  recovery classes are also possible, not only Watch/Warning/Alert.
- `date_used` is the latest dekad that has **ended** on or before the analysis date (the CDI may therefore be up
  to about 20 days older than the analysis date, and the newest published dekad lags real time).
- The numeric fields stay `None` permanently (the proposal in §4 is withdrawn).

### IMGW (`bundle.imgw`, only when analysis date = today)
- `nearest_synop` comes from the nearest of 56 synop stations with known coordinates. Six stations
  (Gdańsk, Katowice, Kraków, Tarnów, Warszawa, Platforma) are excluded because their coordinates could not be
  matched unambiguously; distances can be 40–60 km. `observed_at` is UTC.
- `drought_warnings` are filtered by the parcel's **voivodeship** (IMGW gives catchment codes but no catchment
  geometry). A Polish note says that a warning may concern another catchment in the same voivodeship.
  `valid_to = None` means «until further notice». Warning times are given exactly as IMGW publishes them
  (naive, no time zone stated by the API).

---

## 4b. Added after CP3 (hydro, land cover, terrain, static map are now real)

### Hydro (`bundle.hydro`), changed source
- Primary source is **BDOT10k** (GUGiK topographic database, 1:10 000), not MPHP. BDOT10k includes drainage
  ditches; MPHP has no vector access. `WaterFeature.source_id` is therefore **`"bdot10k"`** (or `"osm"` for the
  fallback), not `"mphp"`. The contract comment lists `"mphp" | "osm"`, but the field is a plain `str`, so no
  contract change is needed; please do not match on `"mphp"`.
- BDOT10k has no open vector API, so features are outlines of the drawn map symbols on a 2 m grid. Distances can
  be short by up to half a symbol width (a Polish note says so). One connected ditch network = one feature.
- `kind` mapping (our choice, documented in `config/geo_sources.yaml`): ditch, canal, `stream` (BDOT10k has one
  class for «rzeka lub strumień»), standing water → `pond`, flowing-water areas → `river`. `name` is filled
  only for named features.
- `status`: `ok` with an empty `features` list means **nothing within 500 m**; `missing` means sources were down
  (the Polish note says «nie oznacza to braku wód»). `partial` = OSM fallback was used.

### Land cover (`bundle.landcover`)
- `shares_buffer` is the **ring** around the parcel (500 m buffer minus the parcel), not buffer + parcel.
- Class names are WorldCover's own English legend labels (e.g. `Cropland`, `Tree cover`, `Built-up`,
  `Bare/sparse vegetation`); **B should translate them** for the report.

### Terrain (`bundle.terrain`)
- `dem_source="gugik_nmt_1m"`: test parcels (preprocessed NMT in `data/a/nmt/`) and parcels analysed before
  (cache), at 2–10 m (`resolution_m`, at most 250k cells). `status=ok`.
- `dem_source="copernicus_dem_30m"`: first analysis of a new parcel, because NMT needs 50–100 s per request.
  `status=partial`, with a Polish note. **Copernicus DEM is a surface model (DSM): tree lines and buildings can
  look like terrain**, and depressions found on it are coarse (30 m). B should word recommendations based on
  them cautiously. NMT keeps downloading in the background, so a re-analysis later uses it.
- `missing` with the note «…pobieranie trwa w tle…» means that no DEM arrived in time.
- Fixtures (CP3): 7 of 8 test parcels have preprocessed NMT (`terrain=ok`). Kętrzyn `280803_2.0028.78/40` (150 ha) is recorded on Copernicus (`terrain=partial`), so the fixtures cover both paths.
- Retention spot ids: `Z<n>` = depression (with `volume_m3.mid`, `area_m2`, `max_depth_m`), `S<n>` = flow
  concentration where a flow line leaves the parcel, `R<n>` = ditch crossing the parcel boundary, lowest first.
  **The static map labels spots with these ids**, so use the same ids in the report text.
  `volume_m3.low/high` are `None` (DEM vertical accuracy not yet sourced).
- Thresholds (min depression 100 m² / 0.1 m deep, flow lines from 1 ha upslope) are our choices, listed in
  `config/geo_sources.yaml` `terrain_processing`. Mention them in METHODOLOGY.md if you describe retention spots.

### Static map
- `render_static_map` is implemented (PNG, Polish legend, caption with parcel id and sources). Typical time is
  1–1.5 s. The §1.3 try/except is still worth keeping for robustness.

---

## 4c. Added in CP4 (robustness and the cold path)

Every source now has a fallback, and a parcel nobody has analysed before (the jury's case) gets almost
complete data within the 22 s. Full details: [`DATA_SOURCES.md`](DATA_SOURCES.md).

### Soil: WOD and `theta_fc` / `theta_wp` changed method (please read before using them)
- Field capacity and wilting point are now computed with the **Saxton & Rawls (2006)** pedotransfer functions
  from SoilGrids texture and organic matter. They are no longer SoilGrids' own `wv0033` / `wv1500`.
- **Why:** SoilGrids' values made sandy parcels look like heavy soils. At the 5 test parcels with a soil-map code,
  SoilGrids wv gave WOD 204–240 mm (category IV) where the 1:5000 map says I or II. Saxton & Rawls matches the
  map exactly at 2 of 5 parcels and within one category at 4 of 5; SoilGrids wv at 1 of 5.
- **Effect for B:**
  - `wod_mm` is much lower on sands (75–100 mm instead of 200–240 mm). Any TAW / FAO-56 numbers you computed
    from earlier fixtures will change.
  - `category_source == "soilgrids_wod"` now means «Saxton & Rawls on SoilGrids texture»; a Polish note in
    `soil.notes_pl` says so.
  - Provenance `source_id` is `"soilgrids_files"` (tiles, the live path) or `"soilgrids_rest"`.
- **§2.2 update:** `layers` is now normally filled on the first analysis too. The tiles answer in about 2 s;
  REST took 26–163 s. Keep the empty-layers guard anyway: some points have no SoilGrids values.

### Vegetation: Sentinel-2 now comes from Microsoft Planetary Computer
- Provenance `source_id` is `"planetary_computer"`, or `"earth_search"` when Planetary Computer is down. Use the
  attribution in the provenance as before.
- A cold analysis now usually has the whole 10-year history (`status == "ok"`). It was `partial` before.

### Parcel lookup: ULDK fallback
- ULDK blocked the dev machine on 2026-11-21 (every API call redirected to a page returning garbage). Lookups by
  id and by point now fall back to the national EGiB GeoParquet export (4–7 s instead of 0.3 s).
- **For B:** `find_parcels` / `parcel_at_point` can take up to ~7 s when ULDK is down; keep the frontend spinner.
  «Obręb + number» queries fall back too, when the obręb name occurs at most 5 times in Poland (6–8 s). For
  more frequent names (e.g. «Nowa Wieś», 108 obręby) they raise `UpstreamUnavailable`. Suggested Polish
  message: «Wyszukiwarka działek po nazwie obrębu jest chwilowo niedostępna – podaj pełny identyfikator działki
  albo wskaż ją na mapie.»
- Commune and obręb names from the export may be in upper case (as stored in EGiB, e.g. «NADARZYCE»).

### Smaller changes
- `landcover.notes_pl` says when the analysis date is before 2021, the year of the WorldCover map.
- Vegetation note «Brak bezchmurnych zdjęć …» now also names water, snow and shadows as reasons.
- Every source result can come from the disk cache. Warm analyses take a few seconds; provenance keeps the original
  fetch time.

---

## 5. Environment notes

- Dockerfile uses Python 3.11; A develops on 3.14. A's code uses no 3.12+ features, but please run the
  image's `pytest tests/a` once after merging (A's tests need no network).
- A's runtime dependencies: `requirements/a-geo.txt` (rasterio, pystac-client, pyyaml, **pyarrow** added in CP4
  for the ULDK fallback; all BSD/Apache/MIT). Your Dockerfile already installs the file.
- README (B): please link [`DATA_SOURCES.md`](DATA_SOURCES.md) in the data-sources / licences / limitations
  sections. It lists live versus prepared data with download dates, as task §4.2 points 4, 5, 7 and 8 require.
