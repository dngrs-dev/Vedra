# Part B — analytics & product («B judges and serves»)

Owner: **person B** (and their coding agent). Read first: `README.md`, `TEAM_SPLIT.md`, `CONTRACTS.md`.

**Mission.** Turn a request (parcel, crop, date) into a report: fetch weather, compute the KBW verdict
and the other signals, interpret A's facts, identify causes, generate data-justified recommendations,
build the report (JSON + PDF), save it, and serve everything through the HTTP API. Own the app skeleton,
Docker and deployment.

**You do not:** call ULDK, WMS/WCS/WFS, STAC/COG, Overpass, EDO or IMGW yourself — those are A's. You get
them only through `GeoProvider`. You never edit `app/geo/**` or other A files. Until A is ready, use
`GEO_PROVIDER=fake` (synthetic) or `fixtures` (A's recordings).

---

## 1. Files you own

```text
app/main.py                    FastAPI app: routers, CORS, rate limit, security headers, startup/shutdown (core.http.close)
app/config.py                  Settings (pydantic-settings): GEO_PROVIDER, CACHE_DIR, DB_PATH, CORS_ORIGINS, LOG_LEVEL
app/contracts/report.py        Report models (contract with the frontend)
app/api/
├─ deps.py                     get_geo_provider() (real | fake | fixtures), get_db()
├─ routes_meta.py              /api/health, /api/crops
├─ routes_parcels.py           /api/parcels/search, /api/parcels/by-point
├─ routes_analyses.py          POST/GET /api/analyses, /report.pdf
└─ routes_reports.py           /api/reports/{id}
app/analytics/
├─ __init__.py, hosts.py       ANALYTICS_HOSTS
├─ models.py                   private models: WeatherData, KbwResult, Signal, Cause, ...
├─ open_meteo.py               weather fetch (archive + forecast)
├─ crops.py                    loads config/crops.yaml + kbw_thresholds.csv
├─ periods.py                  14 six-decade periods
├─ evapotranspiration.py       Doroszewski-Gorski ETP
├─ kbw.py                      KBW value + threshold + verdict, 10-year history
├─ spi.py                      SPI-1 / SPI-3
├─ soil_moisture.py            ERA5-Land anomaly
├─ vegetation_signal.py        crop-aware interpretation of A's VegetationData
├─ soil_water.py               TAW for crop root depth from A's SoilInfo.layers; SOM "what if" (Saxton-Rawls)
├─ water_balance.py            FAO-56 daily bucket
├─ vulnerability.py            10-year vulnerability, risk calendar, parcel sensitivity
├─ season.py                   in-season / off-season mode
├─ causes.py                   cause ranking with evidence
├─ uncertainty.py              confidence level, limitations list
├─ irrigation.py               irrigation verdict, date, dose
└─ pipeline.py                 run_analysis(): stage order, progress callbacks
app/recommendations/
├─ engine.py                   evaluates rules in stage order
├─ rules/landscape.py  soil.py  agrotech.py  irrigation.py  off_season.py
└─ texts_pl.py                 ALL Polish user-facing strings
app/reports/
├─ builder.py                  Report from pipeline outputs (collects A's provenance)
├─ charts.py                   matplotlib -> SVG
├─ pdf.py                      WeasyPrint
└─ templates/report.html.j2, report.css
app/jobs/runner.py             asyncio background jobs, progress, timeouts
app/storage/db.py              SQLite: analyses, reports
app/fakes/fake_geo.py          FakeGeoProvider (synthetic, contract-valid)
app/fakes/fixture_geo.py       FixtureGeoProvider (reads tests/fixtures/geo/*.json)
config/weather_sources.yaml  crops.yaml  kbw_thresholds.csv  thresholds.yaml  references.yaml
requirements/b-app.txt          pandas, jinja2, weasyprint, slowapi, python-multipart if needed, pdfplumber (scripts)
Dockerfile
scripts/b/build_kbw_official.py  backtest.py  generate_sample_reports.py
tests/b/**, tests/contract/test_pipeline_on_fixtures.py, tests/fixtures/sample_report.json
data/b/** (+ data/b/manifest.json)
README.md, docs/METHODOLOGY.md, VALIDATION.md, SCALABILITY.md, SECURITY.md, AI_USAGE.md, this file
```

---

## 2. How you use Part A

```python
# app/api/deps.py  (the only place that imports app.geo)
from app.config import settings
from app.contracts.geo import GeoProvider

def get_geo_provider() -> GeoProvider:
    if settings.geo_provider == "real":
        from app.geo.provider import RealGeoProvider
        return RealGeoProvider()
    if settings.geo_provider == "fixtures":
        from app.fakes.fixture_geo import FixtureGeoProvider
        return FixtureGeoProvider()
    from app.fakes.fake_geo import FakeGeoProvider
    return FakeGeoProvider()
```

- `/api/parcels/*` → `geo.find_parcels()` / `geo.parcel_at_point()`; map `InvalidParcelQuery` → 422,
  `ParcelNotFound` → 404, `UpstreamUnavailable` → 503, each with a Polish `detail`.
- Pipeline → `geo.collect(GeoRequest(...))` in parallel with your weather fetch.
- PDF → `geo.render_static_map(parcel, bundle)`; if it fails, PDF without the map + note.
- `FakeGeoProvider` must return **every** `SourceStatus` across calls (e.g. seeded by parcel id) so the
  report handles `partial`/`missing` from day one.

---

## 3. Functions, file by file

### `open_meteo.py`
| Function | Spec |
| --- | --- |
| `async fetch_weather(lat, lon, analysis_date) -> SourceResult[WeatherData]` | Keep a complete daily ERA5-Seamless archive from `1991-01-01` in `an.openmeteo` per 0.1° cell. Request only missing dates and use Open-Meteo's daily soil-moisture means. If `analysis_date` > today − 5 days, fill the gap from the forecast API with `past_days`. Truncate to ≤ `analysis_date` and keep cached days if a refresh is limited. [Methodology](METHODOLOGY.md#dane-pogodowe). |
| `async fetch_forecast(lat, lon) -> SourceResult[Forecast]` | 7 days; only called when `analysis_date == today`. |

### `crops.py`, `periods.py`, `evapotranspiration.py`, `kbw.py`
| Function | Spec |
| --- | --- |
| `crops.load() -> dict[str, Crop]` | 14 crops of Dz.U. 2019 poz. 739 with `name_pl`, FAO-56 Kc/Zr/p (each with `source`). |
| `crops.threshold(crop, category, period_idx) -> float \| Literal["x", "-"]` | From `kbw_thresholds.csv` (14 × 4 × 14). |
| `periods.PERIODS` / `periods.latest_completed(d) -> Period \| None` / `periods.for_year(y)` | 21 III–20 V … 1 VIII–30 IX. |
| `evapotranspiration.etp_monthly(t, h, f) -> float` | ETP = −89.6 + 0.0621·t² + 0.00448·h^1.66 + 9.1·f (IUNG, verify exponents against the PDF). |
| `evapotranspiration.etp_period(weather, start, end) -> float` | monthly ETP pro-rated by days (our assumption, documented). |
| `kbw.assess(weather, soil_category, crop, analysis_date) -> KbwResult` | KBW (Doroszewski-Górski and FAO-56 ET0 variants), threshold, verdict (`drought` / `no_drought` / `not_applicable` («x»), `not_recommended` («–»), `off_season`), distance to threshold, «na granicy progu» band. |
| `kbw.history(weather, soil_category, crop, analysis_date, years=10) -> KbwHistory` | per year × period: KBW and exceeded flag; years with drought; risk by month. |

### Signals
| Function | Spec |
| --- | --- |
| `spi.spi(monthly_precip, scale, baseline=(1991, 2020)) -> pd.Series` | gamma fit with zero-precip handling; McKee 1993 classes. |
| `soil_moisture.anomaly(weather, analysis_date) -> Signal` | per layer: percentile vs same day-of-year over 10 years. |
| `vegetation_signal.interpret(veg: VegetationData, crop, analysis_date) -> Signal` | percentile/VCI of current vs `same_window_by_year`; uses crop sensitivity (periods with «x» = outside critical period) and known bare-soil phases → «niska wartość NDVI wynika prawdopodobnie ze zbioru / braku wschodów, nie z suszy»; thresholds from PolSA 2024 §6.3.4 in `thresholds.yaml`. |
| EDO | read `bundle.edo` directly; compare with own verdict. |

### Stages and recommendations
| Function | Spec |
| --- | --- |
| `season.mode(analysis_date) -> Literal["in_season", "off_season"]` | in season = 21 III – 30 IX. |
| `soil_water.taw_mm(layers, zr_cm) -> Range`, `soil_water.what_if_som(layers, delta_som_pct) -> Range` | Saxton & Rawls 2006 PTF (coefficients transcribed with citation). |
| `water_balance.run(weather, crop, soil, start, end) -> DailyBalance` | FAO-56 Dr, Ks, stress days. |
| `vulnerability.assess(kbw_history, balance_10y, veg) -> Vulnerability` | years with drought, months of risk, parcel sensitivity (season NDVI peak in KBW-drought years vs other years). |
| `causes.rank(ctx) -> list[Cause]` | precipitation deficit, evaporative demand, low soil retention, runoff (from `bundle.terrain`), missing landscape elements (`bundle.landcover`), crop requirements; each with `evidence: list[Metric]`. |
| `uncertainty.assess(ctx) -> (confidence, limitations_pl)` | agreement of KBW with ≥ 2 independent signals; resolutions; clear scenes; missing sources (from every `SourceResult.notes_pl`). |
| `irrigation.advise(balance, forecast, soil, crop) -> IrrigationAdvice` | justified?, date when Dr reaches RAW, net dose range; no forecast for historical dates. |
| `recommendations.engine.run(ctx) -> list[Recommendation]` | rules ordered: landscape retention → soil retention → agrotech → irrigation; every rule needs an assessment input, else does not fire; texts only from `texts_pl.py`; each recommendation carries `why_pl`, `evidence`, `reference_ids`, optional `geometry` (from A's retention spots). |
| `pipeline.async run_analysis(req, geo, progress) -> Report` | 1) parcel; 2) gather(`fetch_weather`, `geo.collect`); 3) stages in order on an `AnalysisContext` dataclass (private to B); 4) `builder.build`; emits Polish progress messages per stage. |

### Report, API, jobs, storage
| Function | Spec |
| --- | --- |
| `reports.builder.build(ctx) -> Report` | schema as in the plan (summary, assessment, causes, recommendations, map_layers from A's GeoJSON, irrigation, limitations, data_sources = all `Provenance` from weather + bundle, references). |
| `reports.pdf.render(report, map_png) -> bytes` | Jinja2 HTML → WeasyPrint; charts SVG. Without Pango, `reports.pdf_basic` renders the same sections with Matplotlib. |
| `jobs.runner.submit(req) -> analysis_id`, `status(id)` | asyncio task, overall timeout, progress list. |
| `storage.db.save_report / get_report` | SQLite, report JSON + PDF path; permanent id. |

---

## 4. Tasks by checkpoint (tick as you go)

### T0 (with A, ≈ 20 min)
- [x] One of you commits the T0 files from `CONTRACTS.md` §5; both pull.

### CP0 — skeleton (→ 15:30)
- [x] `main.py`, `config.py`, `api/deps.py`, `routes_meta.py`, `Dockerfile`, `requirements/b-app.txt`, CI (pytest).
- [x] `fakes/fake_geo.py` (all statuses), `fakes/fixture_geo.py`.
- [x] `contracts/report.py` + `tests/fixtures/sample_report.json` → hand to the frontend.
- [x] `config/kbw_thresholds.csv` from Dz.U. 2019 poz. 739 + test: 14 crops × 4 categories × 14 periods present; `config/crops.yaml`.
- [x] Fill `app/analytics/hosts.py`.

### CP1 — vertical slice (→ 19:00)
- [x] `open_meteo.py` (+ verify variable names), `periods.py`, `evapotranspiration.py`, `kbw.py` (+ unit tests).
- [x] `pipeline.py` with stages 1–2 minimal, `builder.py` minimal, `jobs/runner.py`, `routes_parcels.py`, `routes_analyses.py`.
- [x] Local HTTP smoke test with `GEO_PROVIDER=fake`. Public deployment is scheduled for the final CP5 task.

### CP2 — full assessment (→ 23:00)
- [x] `spi.py`, `soil_moisture.py`, `vegetation_signal.py`, `vulnerability.py`, `causes.py`, `uncertainty.py`.
- [x] `season.py` + off-season behaviour of every stage (jury may enter today's date — November).

### CP3 — recommendations and report (→ 03:00)
- [x] `recommendations/engine.py` + rules (landscape uses A's `retention_spots`, ditches; soil; agrotech; off-season); `texts_pl.py`.
- [x] `soil_water.py`, `water_balance.py`, `irrigation.py`.
- [x] `reports/charts.py`, `pdf.py`, templates; `storage/db.py`; `routes_reports.py`; PDF endpoint.

### CP4 — validation and robustness (→ 07:00)
- [x] `scripts/b/build_kbw_official.py` (MRiRW obwieszczenia → `data/b/kbw_official.parquet`, legend read from the PDFs) and `scripts/b/backtest.py` → `docs/VALIDATION.md`.
  The official annexes and historical matches were verified. The comparison with local IMGW-PIB observations, including discrepancies, is in [VALIDATION.md](VALIDATION.md).
- [x] `tests/contract/test_pipeline_on_fixtures.py` green for every fixture; end-to-end with `real` on all parcels × 3 dates; timings.
  Local integration of Part A `8a4099b` finished all 24 API scenarios on both passes.
  The eight first-lookups took 0.453–2.110 s; the 24 repeated analyses took 0.062–0.079 s.
  Timings include live geo access or its cache and the missing-weather path after the verified archive quota error.
- [x] Error paths: 422/404/503 with Polish messages; job timeout; every source `missing` → still a report.

### CP5 — docs and release (→ 10:00)
- [x] `README.md` (9 mandatory points of the task §4.2), `METHODOLOGY.md`, `SCALABILITY.md`, `SECURITY.md`, `AI_USAGE.md`.
- [x] `scripts/b/generate_sample_reports.py` → `data/b/samples/reports/*.pdf`.
  The sample PDFs use recorded Part A spatial inputs and bundled IMGW-PIB observations. Repeated retention actions have numbered maps and separate evidence for each location.
- [ ] Deploy the validated backend with `GEO_PROVIDER=real` over HTTPS and smoke-test it from a clean browser.
  This is the final task. Earlier checkpoints run locally with `fake`, `fixtures`, or `real` as available.

---

## 5. Acceptance criteria (Part B done)

- `pytest tests/b tests/contract` green with `GEO_PROVIDER=fixtures`.
- Every report: KBW verdict or explicit off-season / «x» / «–» explanation; ≥ 3 signals; ranked causes
  with evidence; recommendations only after assessment, each with `why_pl` + reference; limitations;
  all provenance from weather and A's bundle listed with attribution.
- All user-facing text comes from `texts_pl.py` / templates (grep for Polish letters elsewhere = bug).
- No threshold or coefficient without `source` in config.
