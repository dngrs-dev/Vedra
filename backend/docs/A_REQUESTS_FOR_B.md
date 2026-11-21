# Requests from Part A to Part B

Written by Part A (person A's agent) on 2026-11-21 after CP0–CP1. Each item says **what to change in
Part B's files**, **why** (with the evidence), and how urgent it is. Part A did not edit any B file;
nothing here changes the frozen contract, except the one proposal in §4, which needs your «yes» first
(TEAM_SPLIT.md §5).

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

### 1.3 PDF step: tolerate `render_static_map` raising `NotImplementedError` until CP3
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

**Proposed additive contract change (needs B's «yes», not done):** add to `EdoData` optional fields
`sma_class: str | None = None`, `fapar_class: str | None = None` and `spi3_class: str | None = None` (EDO
legend labels). Reason: EDO only gives classes for these indicators, and the current float fields can never
be filled from public EDO services. Example: `"spi3_class": "Moderately dry"`. If you agree, A makes the
`CONTRACT:` commit per TEAM_SPLIT.md §5. If not, those indicators stay `None`.

---

## 5. Environment notes

- Dockerfile uses Python 3.11; A develops on 3.14. A's code uses no 3.12+ features, but please run the
  image's `pytest tests/a` once after merging (A's tests need no network).
- A's runtime dependencies: `requirements/a-geo.txt` (rasterio, pystac-client, pyyaml; all BSD/Apache/MIT).
  Your Dockerfile already installs it.
