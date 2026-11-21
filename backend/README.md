# Vedra — backend

Backend of **Vedra**, a HackNation 2026 prototype for the KOWR task *«Zatrzymaj wodę, chroń plony»*.
For a given cadastral parcel (działka ewidencyjna), a crop and an analysis date it computes the parcel's
water situation, the causes of water deficit and data-justified recommendations (landscape retention,
soil retention, agrotechnics, optional irrigation), and returns a report as JSON and PDF.

> Status: under construction during the hackathon (21–22.11.2026). Sections marked *planned* describe
> the agreed design; update them as the code lands.

- Code, identifiers and comments: **English**.
- Every text a farmer sees (report, API error messages, progress messages): **Polish**.
- No invented data: every number used by the analysis comes from a fetched source or from a config file
  entry that names its source (`source:` field).

---

## 1. What the backend does

1. **Resolves the parcel** — by full ULDK identifier (`141201_1.0001.6509`), by «obręb + number»
   (`Krzewina 134`) or by a point on the map (ULDK GUGiK).
2. **Fetches source data in parallel**, only for dates ≤ the analysis date («time machine»):
   - meteorology: Open-Meteo (ERA5 / ERA5-Land archive, forecast API for the last days and 7-day forecast), IMGW-PIB (current only);
   - satellite: Sentinel-2 L2A from Earth Search (NDVI, NDMI, cloud mask SCL), 10 years back;
   - soil: mapa glebowo-rolnicza (GUGiK WMS), SoilGrids 2.0 (texture, SOC, water retention with quantiles);
   - terrain: NMT 1 m GUGiK (fallback Copernicus DEM 30 m);
   - hydrology: MPHP Wody Polskie (fallback OSM); land cover: ESA WorldCover; drought background: EDO CDI.
3. **Runs 5 stages in a fixed order** (stage N reads only what stages < N produced):
   1. *Assessment* — climatic water balance KBW per the SMSR IUNG methodology and thresholds from
      Dz.U. 2019 poz. 739 (crop × soil category I–IV × six-decade period), SPI, ERA5-Land soil moisture,
      crop-aware Sentinel-2 anomalies, EDO CDI, 10-year vulnerability;
   2. *Causes* — precipitation deficit, evaporative demand, low soil retention, runoff, missing landscape elements, crop requirements;
   3. *Retention* — concrete places on/around the parcel from the 1 m terrain model (depressions with volume in m³, concentrated flow lines, ditch outlets);
   4. *Agrotechnics* — catch crops, residues, reduced tillage, organic matter (with a computed «what if» for TAW);
   5. *Irrigation (optional)* — FAO-56 daily soil water balance, date and net dose as a range.
4. **Builds the report** — summary, assessment, causes, recommendations with evidence and references,
   limitations and uncertainty, data sources with fetch times and attribution. Saved in SQLite under a
   permanent id; rendered to PDF.

Target: < 30 s per parcel on a cold cache, a few seconds on a warm one.

---

## 2. Architecture (short)

```text
HTTP (FastAPI) ──► jobs/runner ──► pipeline.run_analysis()
                                      │
          ┌───────────────────────────┼─────────────────────────────┐
          ▼ (Part A: app/geo)                                        ▼ (Part B: app/analytics)
   GeoProvider.find_parcels / parcel_at_point                 open_meteo.fetch_weather()
   GeoProvider.collect(GeoRequest) -> GeoBundle               (runs in parallel with collect)
          │                                                          │
          └──────────────────────────► stages 1..5 (Part B) ◄────────┘
                                             │
                                  reports/builder -> Report (JSON) -> pdf.py (PDF)
                                             │
                     GeoProvider.render_static_map() (Part A) -> PNG for the PDF
```

The backend is split into two independently developed parts with **one frozen interface** between them
(`app/contracts/`). Details: [`docs/TEAM_SPLIT.md`](docs/TEAM_SPLIT.md) and [`docs/CONTRACTS.md`](docs/CONTRACTS.md).

| Part | Owner | Package | Responsibility in one line |
| --- | --- | --- | --- |
| A — data & geo | person A | `app/geo/` | **Measures**: everything about the place (parcel, soil, satellite, terrain, water, land cover, EDO, IMGW) |
| B — analytics & product | person B | `app/analytics/`, `app/api/`, `app/reports/`, … | **Judges and serves**: weather, KBW, stages, recommendations, report, PDF, API, deployment |

Rule of thumb: *A measures, B judges.* A never decides whether there is a drought or what to recommend;
B never calls a geo service directly.

---

## 3. Folder structure (with owners)

```text
backend/
├─ README.md                       B   (A contributes via docs/DATA_SOURCES.md)
├─ Dockerfile                      B
├─ requirements/
│  ├─ base.txt                     T0  shared, frozen (fastapi, pydantic, httpx, numpy, shapely, ...)
│  ├─ a-geo.txt                    A   (rasterio, pystac-client, ...)
│  └─ b-app.txt                    B   (pandas, jinja2, weasyprint, slowapi, ...)
├─ app/
│  ├─ main.py, config.py           B
│  ├─ contracts/                   T0  frozen interface between A and B (see docs/CONTRACTS.md)
│  │  ├─ common.py  parcel.py  geo.py  errors.py   T0
│  │  └─ report.py                 B   (contract with the frontend)
│  ├─ core/
│  │  ├─ http.py  cache.py         T0  frozen shared utilities
│  ├─ geo/                         A   whole package
│  ├─ analytics/                   B   whole package
│  ├─ recommendations/             B
│  ├─ reports/                     B
│  ├─ api/                         B
│  ├─ jobs/  storage/              B
│  └─ fakes/                       B   FakeGeoProvider, FixtureGeoProvider (lets B work without A)
├─ config/
│  ├─ geo_sources.yaml  soil_categories.yaml                  A
│  └─ weather_sources.yaml  crops.yaml  kbw_thresholds.csv  thresholds.yaml  references.yaml   B
├─ data/                           preprocessed files + manifest.json (download dates); a/ = A, b/ = B
├─ scripts/a/                      A
├─ scripts/b/                      B
├─ tests/
│  ├─ a/                           A
│  ├─ b/                           B
│  ├─ contract/                    each file has one owner (named in the file header)
│  └─ fixtures/geo/                A writes, B only reads
└─ docs/                           see below
```

T0 = written once, before the split, by either person (≈ 20 min, code in `docs/CONTRACTS.md`), then frozen.

---

## 4. HTTP API

| Method and path | Purpose |
| --- | --- |
| `GET /api/health` | service and source status |
| `GET /api/crops` | the 14 crops of Dz.U. 2019 poz. 739 (`code`, `name_pl`) |
| `GET /api/parcels/search?q=` | parcel by full id or «obręb nr»; list of candidates with GeoJSON |
| `GET /api/parcels/by-point?lat=&lon=` | parcel under a map click |
| `POST /api/analyses` | start an analysis: `parcel_id`, `crop_code`, `analysis_date`, `include_irrigation` → `analysis_id` |
| `GET /api/analyses/{id}` | status, progress (Polish messages), `report` when done |
| `GET /api/analyses/{id}/report.pdf` (planned) | PDF |
| `GET /api/reports/{id}` (planned) | saved report (permanent link) |

Interactive docs: `/docs` (FastAPI OpenAPI). Report schema: `app/contracts/report.py`;
example for the frontend: `tests/fixtures/sample_report.json`.

The CP1 JSON API accepts a request with HTTP 202. Poll the analysis URL until its status is `done`
or `error`. Reports and progress are held in memory during CP1. Run one API process so every poll
reaches the same job registry. Use `GEO_PROVIDER=fake` to exercise the flow with synthetic geo data.

---

## 5. Running (planned)

Docker (recommended, also on Windows — WeasyPrint needs GTK/Pango which the image contains):

```bash
docker compose up --build          # from the repository root; API on http://localhost:8000
```

Local (Linux / WSL2):

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements/base.txt -r requirements/a-geo.txt -r requirements/b-app.txt
uvicorn app.main:app --reload
pytest
```

Environment variables:

| Variable | Default | Meaning |
| --- | --- | --- |
| `GEO_PROVIDER` | `real` | `real` (Part A), `fake` (synthetic), `fixtures` (recorded A outputs in `tests/fixtures/geo/`) |
| `CACHE_DIR` | `.cache` | disk cache for source responses |
| `DB_PATH` | `data/vedra.sqlite` | saved analyses and reports |
| `CORS_ORIGINS` | `http://localhost:5173` | allowed frontend origins |
| `LOG_LEVEL` | `INFO` | |

No API keys are needed: all sources are free and keyless.

---

## 6. Data and licences

Full list (source, scope, live vs preprocessed, download dates, licence, attribution text):
[`docs/DATA_SOURCES.md`](docs/DATA_SOURCES.md) (Part A) and the methodology in
[`docs/METHODOLOGY.md`](docs/METHODOLOGY.md) (Part B). Libraries: only MIT/BSD/Apache-compatible ones,
because rights to the winning solution pass to KOWR; flow-routing algorithms are implemented in-house
(pysheds and richdem are GPL-3.0).

---

## 7. Documentation index

| File | Owner | Content |
| --- | --- | --- |
| [`docs/TEAM_SPLIT.md`](docs/TEAM_SPLIT.md) | both (frozen) | how the work is split, ownership table, git workflow, agent prompts |
| [`docs/CONTRACTS.md`](docs/CONTRACTS.md) | both (frozen) | the A↔B interface: models, functions, guarantees, T0 code |
| [`docs/PART_A_DATA_GEO.md`](docs/PART_A_DATA_GEO.md) | A | Part A scope, files, functions, tasks, acceptance criteria |
| [`docs/PART_B_ANALYTICS_PRODUCT.md`](docs/PART_B_ANALYTICS_PRODUCT.md) | B | Part B scope, files, functions, tasks, acceptance criteria |
| `docs/DATA_SOURCES.md` | A | data sources and licences (created during the work) |
| `docs/METHODOLOGY.md`, `VALIDATION.md`, `SCALABILITY.md`, `SECURITY.md`, `AI_USAGE.md` | B | created during the work |
