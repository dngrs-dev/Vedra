# Team split — two people, zero shared files

Goal: person A and person B (each with their own coding agent) build the backend **in parallel and
independently**, with no merge conflicts at any point — whether they push to `main` continuously or
merge two branches once at the end.

How this is achieved:

1. **One frozen interface.** Everything A and B exchange is defined in `app/contracts/` (Python models +
   one `Protocol`). It is written once at T0 and then changed only by mutual agreement (see §5).
2. **Every file has exactly one owner.** There is no file that both people edit. Where both need
   something (dependencies, config, allow-listed hosts, tests, docs), it is split into two files.
3. **B never waits for A.** B develops against `FakeGeoProvider` (synthetic data shaped by the contract)
   and later `FixtureGeoProvider` (real outputs recorded by A). Switching to A's real code is one
   environment variable: `GEO_PROVIDER=real`.
4. **A never waits for B.** A's code is driven and tested by its own scripts and tests; it needs nothing
   from B.

> Principle: **A measures, B judges.** A returns facts about the place (geometry, soil, NDVI series,
> depressions with volumes, ditches…). B turns facts into verdicts, causes, recommendations and the report.

---

## 1. Who does what (summary)

| | Part A — data & geo | Part B — analytics & product |
| --- | --- | --- |
| Mission | Everything about *the place*: find the parcel and measure it | Everything about *the meaning*: weather, drought verdict, causes, recommendations, report, API |
| Owns | `app/geo/**`, `config/geo_sources.yaml`, `config/soil_categories.yaml`, `requirements/a-geo.txt`, `scripts/a/**`, `tests/a/**`, `tests/fixtures/geo/**`, `tests/fixtures/parcels.json`, `tests/contract/test_geo_provider_contract.py`, `data/a/**`, `docs/PART_A_DATA_GEO.md`, `docs/DATA_SOURCES.md` | `app/main.py`, `app/config.py`, `app/api/**`, `app/analytics/**`, `app/recommendations/**`, `app/reports/**`, `app/jobs/**`, `app/storage/**`, `app/fakes/**`, `app/contracts/report.py`, `config/` (all other files), `requirements/b-app.txt`, `Dockerfile`, `scripts/b/**`, `tests/b/**`, `tests/contract/test_pipeline_on_fixtures.py`, `tests/fixtures/sample_report.json`, `data/b/**`, `README.md`, all other `docs/*.md` |
| Sources | ULDK, mapa glebowo-rolnicza WMS, IUNG WMS, SoilGrids, Sentinel-2 (Earth Search), NMT GUGiK / Copernicus DEM, MPHP / OSM, ESA WorldCover, EDO, IMGW | Open-Meteo (archive + forecast), MRiRW obwieszczenia (offline validation) |
| Produces for the other part | `GeoProvider` implementation (`RealGeoProvider`), recorded fixtures, `render_static_map()` PNG | nothing that A consumes |
| Rough effort (estimate) | ≈ 23–25 h of work | ≈ 23–25 h of work |

Frozen at T0 (nobody edits afterwards without §5): `app/contracts/common.py`, `parcel.py`, `geo.py`,
`errors.py`, `app/contracts/__init__.py`, `app/core/http.py`, `app/core/cache.py`, `app/geo/provider.py`
*signatures* (bodies are A's), `requirements/base.txt`, this file and `CONTRACTS.md`.

Full per-file and per-function lists: [`PART_A_DATA_GEO.md`](PART_A_DATA_GEO.md),
[`PART_B_ANALYTICS_PRODUCT.md`](PART_B_ANALYTICS_PRODUCT.md).

---

## 2. Places where the two parts touch — and how the overlap is removed

| Touch point | Naive (conflicts) | Our split |
| --- | --- | --- |
| Python dependencies | both edit one `pyproject.toml` | `requirements/base.txt` (T0) + `a-geo.txt` (A) + `b-app.txt` (B); Dockerfile installs all three |
| Allowed outbound hosts (SSRF allowlist) | one list in `core/http.py` | `app/geo/hosts.py` → `GEO_HOSTS` (A), `app/analytics/hosts.py` → `ANALYTICS_HOSTS` (B); `core/http.py` (T0) imports both |
| Source configuration | one `sources.yaml` | `config/geo_sources.yaml` (A), `config/weather_sources.yaml` (B) |
| Data provenance in the report | shared registry | each `SourceResult` carries its own `Provenance`; B's report builder only collects them |
| Wiring A into the app | B imports half-finished A code | `app/geo/provider.py` exists from T0 with stub methods; B selects provider by `GEO_PROVIDER` |
| Test data for B | B waits for A | B: `app/fakes/fake_geo.py` (synthetic); A: records `tests/fixtures/geo/*.json`; B's `FixtureGeoProvider` reads them |
| Test parcels | each invents own | A owns `tests/fixtures/parcels.json` (real ids via ULDK); B reads it |
| Contract tests | one file, two authors | `test_geo_provider_contract.py` (A), `test_pipeline_on_fixtures.py` (B) |
| README / docs | both edit README | B owns README; A writes `docs/DATA_SOURCES.md`, README links to it |
| Package `__init__.py` files | both add imports | `app/__init__.py`, `app/contracts/__init__.py`, `app/core/__init__.py` created empty at T0 and never edited; each part owns its own package `__init__.py` |
| Docker / compose | both tweak | B owns; A tells B if a system package is needed (rasterio wheels already bundle GDAL, so normally nothing) |

---

## 3. Timeline (both people, in parallel)

| Checkpoint (assumed times, Sat → Sun) | Person A | Person B |
| --- | --- | --- |
| **T0** 14:30–15:00 | One of you commits T0 (code from `CONTRACTS.md`); the other reviews it. Both pull. | ← same |
| **CP0** → 15:30 | Source spikes, `parcels.json` with real ids | App skeleton, fakes, `kbw_thresholds.csv`, sample report fixture for the frontend |
| **CP1** → 19:00 | ULDK + soil (category, WOD, layers) working in `RealGeoProvider` | Open-Meteo, periods, ETP, KBW, pipeline + jobs + API, first deploy (with `GEO_PROVIDER=fake`) |
| **19:00 integration check** | Push; record fixtures for 3 parcels | Run with `GEO_PROVIDER=fixtures`, then `real`; deploy with `real` |
| **CP2** → 23:00 | Sentinel-2 + vegetation series, EDO, IMGW | SPI, soil-moisture anomaly, crop-aware vegetation interpretation, vulnerability, causes, uncertainty, off-season mode |
| **CP3** → 03:00 | NMT + terrain (depressions, flow, TWI), hydro, land cover, static map | Recommendation engine + rules, FAO-56 + irrigation, report builder, PDF, storage |
| **CP4** → 07:00 | Performance (< 22 s geo budget), edge cases, fixtures for all test parcels | Backtest vs official KBW, edge cases, end-to-end on all parcels |
| **CP5** → 10:00 | `DATA_SOURCES.md`, sample reports script | README, methodology/validation/scalability/security/AI docs, final deploy |

Integration moments are optional sanity checks, not merges: with disjoint files the code is always
mergeable.

---

## 4. Git workflow — choose one

**Option 1 (recommended): both on `main`, no merges at all.**

```bash
git pull --rebase         # before starting a task
# ... work only in your own files ...
pytest tests/a  (or tests/b)
git add <your files>      # never `git add -A` blindly; check `git status` for foreign files
git commit -m "A: soil category from mapa glebowo-rolnicza"
git pull --rebase && git push
```

Because no file has two owners, `pull --rebase` never conflicts. B gets A's fixtures and real provider
as soon as they are pushed.

**Option 2: two long-lived branches, one merge at the end.**

`part-a` and `part-b`, each branched from the T0 commit. At the end: `git checkout main && git merge
part-a && git merge part-b` — no conflicts, because the file sets are disjoint. Downside: B can only use
`fake` data until the end, and integration bugs surface late. If you choose this, still do a throw-away
local merge at 19:00 and at 03:00 to run the pipeline with `GEO_PROVIDER=real`.

Guard rail (both options): before every commit run

```bash
git diff --cached --name-only | python scripts/check_ownership.py A   # or B
```

`scripts/check_ownership.py` (T0, optional) fails if a staged file is outside your ownership list. If
you skip the script, at least read `git status` before committing.

---

## 5. Changing the contract

The contract will need small changes. Protocol:

1. The person who needs the change writes it in the team chat: which model/field/function, why, and an
   example value.
2. Only **additive** changes are allowed without discussion (a new optional field with a default).
   Renames, removals or type changes need a «yes» from the other person.
3. The change is made by **the person who asked**, in a commit that touches only `app/contracts/` and
   `docs/CONTRACTS.md`, prefixed `CONTRACT:`; pushed immediately; the other person pulls before
   continuing.
4. Never change the contract inside a feature commit.

---

## 6. Instructions for the coding agents

Each person starts their agent with the same short prompt, changing only the part file:

```text
Read backend/README.md, backend/docs/TEAM_SPLIT.md, backend/docs/CONTRACTS.md and
backend/docs/PART_A_DATA_GEO.md. You are the agent of person A.
Rules: edit only files owned by Part A (ownership table in TEAM_SPLIT.md §1). Never edit app/contracts/,
app/core/, requirements/base.txt or files owned by Part B; if you need a contract change, stop and tell
me exactly what and why. Code and comments in English; every user-facing string in Polish. Never invent
data, thresholds or coefficients: every constant must cite its source in a comment or config `source:`.
Work through the unchecked tasks of the current checkpoint in PART_A_DATA_GEO.md, in order.
After each task: run `pytest tests/a`, tick the task's checkbox in the part file, commit only your files
with a message starting with "A:", then `git pull --rebase && git push`.
```

For person B: replace `PART_A_DATA_GEO.md` → `PART_B_ANALYTICS_PRODUCT.md`, «person A» → «person B»,
`tests/a` → `tests/b`, `"A:"` → `"B:"`.

Re-run the same prompt after each checkpoint; the checklists in the part files carry the state.

---

## 7. Definition of done for the whole backend

- `GEO_PROVIDER=real`: `POST /api/analyses` for every parcel in `tests/fixtures/parcels.json` × dates
  {today, 2018-07-10, 2023-05-31} finishes with status `done` in < 30 s cold, < 5 s warm.
- Every report has: summary, KBW verdict (or off-season explanation), ≥ 3 signals, causes,
  recommendations with evidence + references, limitations, data sources with fetch time and attribution.
- `pytest` is green; `tests/contract/*` passes with both `fixtures` and `real`.
- PDF opens and prints; saved report reachable under `/api/reports/{id}`.
