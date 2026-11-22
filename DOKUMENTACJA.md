# Vedra – dokumentacja techniczna

**Zespół:** Ardev
**Tytuł rozwiązania:** Vedra – asystent rolnika do oceny niedoboru wody i planowania retencji na działce ewidencyjnej
**Zadanie:** KOWR „Zatrzymaj wodę, chroń plony – Inteligentne wsparcie gospodarowania wodą w rolnictwie”, HackNation 2026
**Repozytorium:** <https://github.com/dngrs-dev/Vedra> (gałąź `main`)

Struktura dokumentu odpowiada wymaganiom z opisu zadania. Rozdziały 1–9 to kolejne punkty
wymagań dokumentacji technicznej (pkt 4.2). Pozostałe rozdziały opisują dostępność i koszty
(pkt 5.4), skalowalność (pkt 5.5), bezpieczeństwo (pkt 5.6) i użycie AI (pkt 5.1).
Szczegóły techniczne znajdują się w dokumentach podlinkowanych w każdym rozdziale.

## Spis treści

- [Zwięzły opis rozwiązania](#zwięzły-opis-rozwiązania)
- [Zgodność z wymaganiami zadania](#zgodność-z-wymaganiami-zadania)
- [1. Instrukcja uruchomienia](#1-instrukcja-uruchomienia)
- [2. Podstawowe funkcjonalności](#2-podstawowe-funkcjonalności)
- [3. Architektura](#3-architektura)
- [4. Źródła i zakresy danych](#4-źródła-i-zakresy-danych)
- [5. Dane pobierane na bieżąco i przygotowane wcześniej](#5-dane-pobierane-na-bieżąco-i-przygotowane-wcześniej)
- [6. Biblioteki, komponenty, modele, usługi zewnętrzne i narzędzia AI](#6-biblioteki-komponenty-modele-usługi-zewnętrzne-i-narzędzia-ai)
- [7. Licencje i warunki korzystania](#7-licencje-i-warunki-korzystania)
- [8. Znane ograniczenia](#8-znane-ograniczenia)
- [9. Weryfikacja wyników i rekomendacji](#9-weryfikacja-wyników-i-rekomendacji)
- [10. Dostępność dla użytkownika i koszty](#10-dostępność-dla-użytkownika-i-koszty)
- [11. Skalowalność](#11-skalowalność)
- [12. Bezpieczeństwo i dane osobowe](#12-bezpieczeństwo-i-dane-osobowe)
- [13. Użycie sztucznej inteligencji](#13-użycie-sztucznej-inteligencji)
- [14. Wygenerowane raporty](#14-wygenerowane-raporty)

## Zwięzły opis rozwiązania

**Problem.** Dane satelitarne, meteorologiczne, glebowe i hydrologiczne są dostępne bezpłatnie,
ale rozproszone i trudne w użyciu. Rolnik nie dostaje z nich prostej odpowiedzi, czy jego działce
grozi niedobór wody, z jakiego powodu i co może zrobić.

**Główne funkcjonalności.**

- Wybór działki ewidencyjnej na mapie, po identyfikatorze, po nazwie obrębu i numerze lub ramką.
- Wybór uprawy z listy upraw rozporządzenia o suszy i dowolnej daty analizy z ostatnich 10 lat.
- Ocena bieżącej sytuacji wodnej na podstawie klimatycznego bilansu wodnego (KBW), z progami
  dla danej uprawy i kategorii gleby. Uzupełniają ją sygnały wilgotności gleby, SPI, kondycji
  roślin z Sentinel-2 (VCI) i regionalny wskaźnik EDO.
- Historyczna podatność działki na niedobór wody w ostatnich 10 latach.
- Wskazanie przyczyn niedoboru: opady, parowanie, gleba, odpływ, otoczenie i wymagania uprawy.
- Rekomendacje w kolejności z zadania: retencja krajobrazowa, retencja glebowa, agrotechnika
  i opcjonalnie nawadnianie. Każde zalecenie ma przesłankę z danych i źródło naukowe.
  Miejsca retencji, np. zagłębienia terenu i rowy, są pokazane na mapie.
- Symulacja „Co jeśli?”: wpływ retencji, próchnicy, międzyplonów lub mulczu i nawadniania
  na liczbę dni stresu wodnego.
- Raport z datą, źródłami danych, ograniczeniami i poziomem pewności. Raport można pobrać
  jako PDF i wydrukować. Jest też zapisany w systemie pod trwałym identyfikatorem.
- Analiza kilku działek naraz i porównanie wyników.

**Sposób wykorzystania danych.** Po wskazaniu działki backend pobiera jej granice z ewidencji
gruntów, a potem równolegle pogodę z 35 lat, glebę, obrazy Sentinel-2, model terenu, sieć wodną,
pokrycie terenu i tło suszowe. Wyniki i rekomendacje oblicza przy każdym żądaniu z tych danych.
Nie wyświetla gotowych tekstów. Brakujące dane są wskazane w raporcie wprost.

**Korzyści dla rolnika.** Rolnik dostaje odpowiedź w zwykłym języku, bez znajomości GIS.
Wie, czy ma niedobór wody i dlaczego. Wie też, które działania na jego działce zatrzymają
najwięcej wody i gdzie je wykonać. Nawadnianie rozważa dopiero po działaniach retencyjnych.
Raport w PDF może zabrać w pole albo pokazać doradcy.

## Zgodność z wymaganiami zadania

| Wymaganie | Realizacja |
| --- | --- |
| 3.2 Aplikacja webowa w przeglądarce, bez instalacji u rolnika | Aplikacja React korzysta tylko ze standardowych technologii przeglądarki, bez wtyczek. Sprawdzona w Google Chrome. Responsywny układ na telefon. |
| 3.3.2 Działka po identyfikatorze lub na mapie | Strona `/map`: kliknięcie, identyfikator, obręb i numer, ramka, **Wiele ID**. |
| 3.3.3 Wybór uprawy | 14 grup upraw z rozporządzenia o suszy ([`crops.yaml`](backend/config/crops.yaml)). |
| 3.3.4 Pobranie danych i ocena bieżąca oraz wieloletnia (10 lat) | [Potok analizy](backend/app/analytics/pipeline.py) przy każdym żądaniu, [rozdz. 2](#2-podstawowe-funkcjonalności). |
| 3.2.1a Interpretacja satelitarna zależna od uprawy | VCI ocenia się tylko w okresach wrażliwości danej uprawy ([metodyka](backend/docs/METHODOLOGY.md#sygnały-przyczyny-i-podatność-historyczna)). |
| 3.2.2 Rekomendacje z terenu, hydrologii i uprawy | Reguły w [`recommendations/rules`](backend/app/recommendations/rules), miejsca z NMT i BDOT10k. |
| 3.2.3 Nawadnianie (opcjonalnie) | Model FAO-56: zasadność, termin i dawka ([`irrigation.py`](backend/app/analytics/irrigation.py)). |
| Kolejność etapów | Ocena → przyczyny → retencja → agrotechnika → nawadnianie. Bez oceny brak rekomendacji. |
| 3.3.5 Raport z przyczynami, uzasadnieniem, datą, źródłami i ograniczeniami | Sekcje raportu: `assessment`, `causes`, `recommendations`, `data_sources`, `limitations_pl`. |
| Brak danych podany wprost | Status `missing` lub `partial` z polskim wyjaśnieniem przy każdym źródle. |
| 3.3.6 Zapis, PDF, wydruk | SQLite z trwałym `report_id`, **Pobierz PDF**, wydruk. |
| Pięć kategorii danych | [Rozdz. 4](#4-źródła-i-zakresy-danych). |
| 4.2 Dokumentacja techniczna, punkty 1–9 | Rozdziały 1–9 tego dokumentu. |
| 5.4 Dostępność i koszty | [Rozdz. 10](#10-dostępność-dla-użytkownika-i-koszty). |
| 5.5 Skalowalność | [Rozdz. 11](#11-skalowalność). |
| 5.6 Bezpieczeństwo | [Rozdz. 12](#12-bezpieczeństwo-i-dane-osobowe). |
| 5.1 Opis zastosowania AI | [Rozdz. 13](#13-użycie-sztucznej-inteligencji). |
| 4.1 Wygenerowane raporty | [Rozdz. 14](#14-wygenerowane-raporty). |
| 7.5 Analiza w czasie do 30 s | Budżet 30 s na analizę. Zmierzone czasy w [rozdz. 9](#9-weryfikacja-wyników-i-rekomendacji). |

## 1. Instrukcja uruchomienia

Prototyp uruchamia się lokalnie. Składa się z backendu (Python, FastAPI) i frontendu
(React, Vite). Rolnik używa tylko przeglądarki. Backend potrzebuje dostępu do Internetu,
bo pobiera dane źródłowe na bieżąco.

**Wymagania:** Docker **albo** Python 3.11, a do frontendu Node.js 18+ z npm.

### 1.1 Backend w Dockerze (zalecane)

Z katalogu głównego repozytorium:

```powershell
docker build -t vedra-backend backend
docker run --rm -e GEO_PROVIDER=real -e DB_PATH=/app/state/vedra.sqlite -v vedra-state:/app/state -p 127.0.0.1:8000:8000 vedra-backend
```

Obraz zawiera biblioteki do generowania PDF (WeasyPrint, Pango, czcionki z polskimi znakami).

### 1.2 Backend bez Dockera (Windows, PowerShell)

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements/base.txt -r requirements/a-geo.txt -r requirements/b-app.txt
$env:GEO_PROVIDER = 'real'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
```

Na Linuxie i macOS użyj `python3`, `. .venv/bin/activate` i `GEO_PROVIDER=real python -m uvicorn app.main:app`.
Bez bibliotek Pango PDF tworzy wbudowany renderer oparty na Matplotlib. Nie wymaga on
dodatkowej instalacji.

### 1.3 Frontend

W drugim terminalu:

```powershell
cd frontend
npm.cmd install
$env:VITE_API_URL = '/api'
$env:VITE_USE_MOCK = 'false'
npm.cmd run dev
```

Otwórz <http://localhost:5173>. Vite przekazuje `/api` do backendu na `127.0.0.1:8000`.
Na Linuxie i macOS użyj `npm` i `export`.

### 1.4 Pierwsza analiza

1. Na stronie głównej wybierz **Zobacz mapę** i zamknij okno z instrukcją (**OK, rozumiem**).
2. Wpisz identyfikator działki, np. `303005_5.0323.25/7`, albo kliknij działkę na mapie.
3. Wybierz uprawę i datę, np. `2018-07-10`, i potwierdź działkę.
4. Po zakończeniu analizy wybierz **Zobacz pełny raport**, a następnie **Pobierz PDF**.

### 1.5 Konfiguracja

| Zmienna | Domyślnie | Znaczenie |
| --- | --- | --- |
| `GEO_PROVIDER` | `real` | `real` – dane na żywo, `fixtures` – zapisane dane z 21.11.2026 dla działek testowych, `fake` – dane demonstracyjne. |
| `DB_PATH` | `data/vedra.sqlite` | Baza zapisanych raportów. |
| `CACHE_DIR` | `.cache` | Pamięć podręczna pobranych danych. |
| `ANALYSIS_CONCURRENCY` | `2` | Liczba analiz wykonywanych równolegle. |
| `CORS_ORIGINS` | `http://localhost:5173` | Adresy frontendu. |
| `EGIB_SNAPSHOT_PATH` | brak | Opcjonalna lokalna baza granic działek ([instrukcja](backend/README.md#lokalna-kopia-granic-działek-egib)). |
| `AI_ENABLED` | `true` | Włącza opcjonalny komentarz AI. |
| `AI_PROVIDER` | `gemini` | `gemini` albo `anthropic`. |
| `GEMINI_API_KEY` | brak | Klucz Google AI Studio. Bez klucza komentarz powstaje z reguł. |
| `ANTHROPIC_API_KEY` | brak | Klucz Anthropic dla `AI_PROVIDER=anthropic`. |

Szczegóły: [backend](backend/README.md#5-uruchomienie-lokalne), [frontend](frontend/README.md).

## 2. Podstawowe funkcjonalności

Przebieg odpowiada scenariuszowi z pkt 3.3 zadania.

1. **Wskazanie działki.** Rolnik klika działkę na mapie, wpisuje identyfikator lub obręb
   i numer. Może też zaznaczyć ramką kilka działek (`Ctrl` + przeciągnięcie) albo wkleić listę
   identyfikatorów (**Wiele ID**). Backend pobiera granicę działki z EGiB.
2. **Wybór uprawy i daty.** Lista zawiera 14 grup upraw z rozporządzenia o suszy rolniczej.
   Data może być dzisiejsza lub dowolna z ostatnich 10 lat. Obliczenia używają tylko danych
   do tej daty.
3. **Ocena stanu wilgotności.**
   - KBW za ostatni okres sześciu dekad, porównany z progiem dla uprawy i kategorii gleby
     (Dz.U. 2017 poz. 732, Dz.U. 2019 poz. 739). Równolegle wariant z ET0 FAO-56 pokazuje
     wrażliwość na metodę.
   - Sygnały uzupełniające: SPI-1 i SPI-3, percentyl wilgotności gleby ERA5-Land,
     VCI z Sentinel-2 w okresach wrażliwych dla uprawy, CDI z Copernicus EDO.
   - Pewność oceny zależy od zgodności sygnałów.
   - Podatność historyczna: udział okresów suszy w 10 latach, najbardziej narażone miesiące,
     porównanie szczytów NDVI w latach suchych i wilgotnych.
4. **Przyczyny.** Niedobór opadów, wysokie parowanie, mała pojemność wodna gleby (SoilGrids,
   Saxton–Rawls), spadki i odpływ (NMT), brak elementów retencji w otoczeniu (BDOT10k,
   WorldCover) i wymagania uprawy.
5. **Rekomendacje retencyjne i agrotechniczne.** Reguły zależą od przyczyn. Wskazują np.
   zagłębienia terenu i linie spływu do zatrzymania wody, rowy do spowolnienia odpływu,
   międzyplony, resztki pożniwne, uprawę bezorkową i zwiększanie próchnicy. Każde zalecenie
   ma przesłankę z danych działki i odsyłacz do literatury.
6. **Nawadnianie (opcjonalnie).** Dobowy bilans wody w strefie korzeniowej według FAO-56.
   Wskazuje zasadność, przewidywany termin osiągnięcia progu RAW i orientacyjną dawkę netto.
7. **Symulacja „Co jeśli?”.** Porównanie wariantu bez działań z retencją, próchnicą,
   międzyplonem lub mulczem, nawadnianiem i własną kombinacją działań. Opcjonalnie
   komentarz AI po zgodzie użytkownika ([rozdz. 13](#13-użycie-sztucznej-inteligencji)).
8. **Raport.** Widok webowy z mapą miejsc retencji i planem wizji w terenie. PDF dla jednej
   uprawy lub zbiorczy dla kilku upraw działki. Wydruk. Zapis w bazie pod `report_id`.
9. **Poza sezonem monitoringu** (sezon trwa od 21.03 do 30.09) raport pokazuje ostatni oceniony okres i historię
   zamiast bieżącego werdyktu.

Opis metod: [metodyka](backend/docs/METHODOLOGY.md).

## 3. Architektura

```text
Przeglądarka (React, Leaflet)
   │  REST /api
   ▼
FastAPI ──► kolejka zadań (asyncio, limit równoległości, budżet 30 s)
   │            │
   │            ├─► GeoProvider (część A): EGiB/ULDK, gleba, Sentinel-2, NMT,
   │            │      BDOT10k/OSM, WorldCover, EDO, IMGW ── równolegle, z pamięcią podręczną
   │            ├─► Pogoda (część B): Open-Meteo ERA5, zapas: archiwum IMGW-PIB (SQLite)
   │            ▼
   │        potok analizy: KBW, SPI, wilgotność, VCI, podatność → przyczyny → reguły rekomendacji
   │            ▼
   └──────► raport JSON → SQLite ──► PDF (WeasyPrint lub Matplotlib) / widok webowy
                                └──► symulacja „Co jeśli?” → opcjonalny komentarz AI
```

- **Frontend** ([`frontend/src`](frontend/src)): strony `/`, `/map`, `/report`. Stan w Zustand,
  zapytania w TanStack Query, walidacja odpowiedzi w Zod.
- **Backend** ([`backend/app`](backend/app)): `api` (endpointy), `geo` (dane przestrzenne),
  `analytics` (obliczenia), `recommendations` (reguły i teksty), `reports` (PDF),
  `ai` (komentarz AI), `storage` (SQLite), `core` (HTTP z listą dozwolonych hostów, cache).
- **Kontrakty** między częściami są typami Pydantic ([opis](backend/docs/CONTRACTS.md)).
  Każde źródło zwraca status `ok`, `partial` lub `missing`, notatkę po polsku i metadane
  pochodzenia.

Lista endpointów: [API](backend/README.md#4-api).

## 4. Źródła i zakresy danych

| Kategoria z pkt 3.3 | Źródło | Zakres i rozdzielczość | Do czego służy |
| --- | --- | --- | --- |
| Meteorologiczne | Open-Meteo (ERA5, ERA5-Land, model prognozy) | Dzienne dane od 1.01.1991 do daty analizy, siatka ok. 0,1° | Opady, ET0, temperatura, usłonecznienie, wilgotność gleby, prognoza |
| Meteorologiczne | IMGW-PIB, dobowe SYNOP | 63 stacje, 1.01.1991–31.10.2026 | Zapasowe źródło KBW |
| Meteorologiczne | IMGW-PIB, API danych publicznych | Bieżące, najbliższa stacja | Bieżąca pogoda i ostrzeżenia hydrologiczne |
| Satelitarne | Sentinel-2 L2A (Planetary Computer, Earth Search) | 10 m, sceny IV–VIII z 10 lat | NDVI, NDMI, VCI |
| Satelitarne / tło suszowe | Copernicus EDO, CDI | 0,04°, dekada | Regionalny wskaźnik suszy |
| Glebowe | Mapa glebowo-rolnicza GUGiK (WMS) | 1:5 000 | Kategoria gleby I–IV do progów KBW |
| Glebowe | ISRIC SoilGrids 2.0 | 250 m, profil 0–200 cm | Tekstura, węgiel organiczny, gęstość → pojemność wodna |
| Hydrologiczne | BDOT10k GUGiK (WMS), zapas: OpenStreetMap | 1:10 000, 500 m wokół działki | Rowy, cieki, kanały, zbiorniki |
| Przestrzenne: działki | EGiB WFS GUGiK, ULDK, eksport GeoParquet EGiB, PRG | Ewidencyjna | Granica, identyfikator, gmina, powiat, województwo |
| Przestrzenne: rzeźba terenu | NMT GRID1 GUGiK (WCS), zapas: Copernicus DEM GLO-30 | 1 m (przepróbkowane do 2–10 m), 30 m | Spadki, zagłębienia, linie spływu |
| Przestrzenne: użytkowanie | ESA WorldCover 2021 v200 | 10 m, działka i pas 500 m | Udział gruntów ornych, lasów, wód, zabudowy |
| Prawne i referencyjne | Dz.U. 2017 poz. 732, Dz.U. 2019 poz. 739 | Tabele progów KBW | Progi suszy dla upraw i gleb |
| Walidacja | Obwieszczenia MRiRW (10.07.2018, 31.05.2023) | Ok. 2 480 gmin | Tylko do sprawdzenia wyników, nie zasila obliczeń |

Opisy źródeł, parametry i fallbacki: [źródła przestrzenne](backend/docs/DATA_SOURCES.md),
[dane i pochodzenie](backend/README.md#6-dane-zakresy-i-pochodzenie),
[konfiguracja źródeł](backend/config/geo_sources.yaml).

## 5. Dane pobierane na bieżąco i przygotowane wcześniej

**Wynik i rekomendacje oblicza aplikacja przy każdym żądaniu** z danych wejściowych.
Pliki przygotowane wcześniej to dane wejściowe, indeksy lub zapas na wypadek awarii źródła.
Nie zawierają gotowych wyników ani rekomendacji.

### 5.1 Pobierane na bieżąco przy analizie

| Dane | Usługa | Pamięć podręczna |
| --- | --- | --- |
| Granica i atrybuty działki | EGiB WFS, ULDK, eksport GeoParquet EGiB | 1 doba dla wyszukiwania |
| Pogoda 1991 – data analizy, prognoza | Open-Meteo | Kompletne dni w komórce 0,1°, pobierane są tylko brakujące |
| Kategoria gleby | WMS mapy glebowo-rolniczej GUGiK | Dysk |
| Profil glebowy | SoilGrids (kafle COG, zapas REST) | Dysk |
| Sceny Sentinel-2 z 10 lat | Planetary Computer, Earth Search | Wyniki per scena na dysku |
| Model terenu | NMT GUGiK WCS, Copernicus DEM | Dysk |
| Sieć wodna | BDOT10k WMS, OSM Overpass | Dysk |
| Pokrycie terenu | ESA WorldCover | Dysk |
| Tło suszowe | Copernicus EDO WCS | Dysk, per dekada |
| Bieżąca pogoda, ostrzeżenia | IMGW-PIB API | 10 minut |
| Podkład mapy we frontendzie | Esri World Imagery, OpenTopoMap | Przeglądarka |
| Granice województw na mapie | jsDelivr, repozytorium `ppatrzyk/polska-geojson` | Przeglądarka |
| Zaznaczanie ramką we frontendzie | ULDK GUGiK | Sesja przeglądarki |

### 5.2 Pobrane lub przetworzone wcześniej

| Plik | Zawartość | Źródło | Data pobrania |
| --- | --- | --- | --- |
| [`backend/data/b/imgw_daily.sqlite`](backend/data/b/imgw_daily.sqlite) | Dobowe opady, temperatura, usłonecznienie, 63 stacje, 1991-01-01 – 2026-10-31 | IMGW-PIB, dane SYNOP | 21.11.2026 |
| [`backend/data/a/soilgrids_tiles.json`](backend/data/a/soilgrids_tiles.json) | Indeks kafli SoilGrids dla Polski | files.isric.org | 21.11.2026 |
| [`backend/data/a/teryt_names.json`](backend/data/a/teryt_names.json) | Nazwy 16 województw i 380 powiatów | PRG WFS | 21.11.2026 |
| [`backend/config/cadastral_teryt.json`](backend/config/cadastral_teryt.json) | Nazwy jednostek administracyjnych | PRG WFS | 21.11.2026 |
| [`backend/data/a/imgw_synop_stations.json`](backend/data/a/imgw_synop_stations.json) | 56 stacji synoptycznych ze współrzędnymi | IMGW-PIB API | 21.11.2026 |
| [`backend/data/a/soilgrids_points.json`](backend/data/a/soilgrids_points.json), [`s2_scene_stats.json`](backend/data/a/s2_scene_stats.json), [`nmt/`](backend/data/a/nmt) | Odpowiedzi SoilGrids, statystyki scen Sentinel-2 i NMT dla 8 działek testowych | SoilGrids, Planetary Computer, Earth Search, GUGiK | 21.11.2026 |
| [`backend/tests/fixtures/geo`](backend/tests/fixtures/geo) | Zapisane odpowiedzi geo dla trybu `fixtures` i testów | Usługi z rozdz. 4 | 21.11.2026 |
| [`backend/config/kbw_thresholds.csv`](backend/config/kbw_thresholds.csv), [`kbw_thresholds_2017.csv`](backend/config/kbw_thresholds_2017.csv) | Progi KBW dla upraw i kategorii gleby | Dz.U. 2019 poz. 739, Dz.U. 2017 poz. 732 | Przepisane z aktów prawnych |
| [`backend/config/crops.yaml`](backend/config/crops.yaml), [`references.yaml`](backend/config/references.yaml), [`thresholds.yaml`](backend/config/thresholds.yaml) | Parametry upraw FAO-56, bibliografia, progi sygnałów | Literatura podana w plikach | Wersjonowane w repozytorium |
| [`backend/data/b/kbw_official.parquet`](backend/data/b/kbw_official.parquet) | Urzędowe KBW gmin, tylko do walidacji | Obwieszczenia MRiRW | 21.11.2026 |

Sumy kontrolne i adresy: [manifest części A](backend/data/a/manifest.json),
[manifest części B](backend/data/b/manifest.json), tabela `input` w `imgw_daily.sqlite`.
Odtworzenie: skrypty w [`backend/scripts`](backend/scripts) (opis w [README backendu](backend/README.md#lokalna-kopia-granic-działek-egib)).

## 6. Biblioteki, komponenty, modele, usługi zewnętrzne i narzędzia AI

**Backend (Python 3.11)** – [base](backend/requirements/base.txt), [a-geo](backend/requirements/a-geo.txt), [b-app](backend/requirements/b-app.txt):
FastAPI, Uvicorn, Pydantic, pydantic-settings, HTTPX, DiskCache, Structlog, NumPy, SciPy,
pandas, Shapely, pyproj, Rasterio (GDAL), pystac-client, PyArrow, PyYAML, Jinja2, WeasyPrint,
Matplotlib, tzdata, google-genai, anthropic. Testy: pytest, pytest-asyncio, RESPX, pypdf.
Baza danych: SQLite.

**Frontend** – [package.json](frontend/package.json): React 18, React DOM, React Router,
TanStack Query, Zustand, Zod, Leaflet, React Leaflet, TypeScript, Vite, @vitejs/plugin-react.

**Modele obliczeniowe i naukowe:**

| Model | Zastosowanie |
| --- | --- |
| Klimatyczny bilans wodny, ETP Doroszewskiego–Górskiego | Ocena suszy zgodna z metodyką IUNG-PIB i rozporządzeniem |
| FAO-56 (Penman-Monteith ET0, Kc, TAW i RAW) | Wariant KBW, bilans strefy korzeniowej, nawadnianie, symulacje |
| SPI (McKee 1993, WMO 1090) | Niedobór opadów na tle 1991–2020 |
| VCI (FAO GIEWS, NOAA) | Kondycja roślin z NDVI Sentinel-2 |
| Saxton–Rawls (2006) | Pojemność wodna gleby z tekstury i materii organicznej |
| Minasny i McBratney (2018), Pribyl (2010) | Wpływ wzrostu próchnicy na retencję glebową |
| Analiza NMT (spadki, zagłębienia, akumulacja spływu) | Miejsca zatrzymania wody |

**Usługi zewnętrzne:** Open-Meteo, IMGW-PIB, GUGiK (EGiB WFS, ULDK, PRG WFS, WMS mapy
glebowo-rolniczej, NMT WCS, BDOT10k WMS), Geoportal Otwarte Dane (GeoParquet EGiB), ISRIC
SoilGrids, Microsoft Planetary Computer, Earth Search (Element 84), Copernicus EDO,
ESA WorldCover, OpenStreetMap Overpass, Esri World Imagery, OpenTopoMap, jsDelivr.

**Narzędzia AI:**

| Narzędzie | Rola |
| --- | --- |
| Google Gemini API (`gemini-3.5-flash`, zapas `gemini-3.5-flash-lite`) | Opcjonalny komentarz do symulacji w aplikacji (domyślny dostawca) |
| Anthropic Claude API (`claude-opus-5-5`) | Alternatywny dostawca tego samego komentarza |
| OpenAI Codex, Claude Code (Claude Opus 5.5), Google Gemini | Asystenci programistyczni zespołu |

Szczegóły w [rozdz. 13](#13-użycie-sztucznej-inteligencji).

## 7. Licencje i warunki korzystania

### 7.1 Dane

| Dane | Licencja lub warunki |
| --- | --- |
| Open-Meteo, ERA5 | Dane CC BY 4.0. Bezpłatne API do użytku niekomercyjnego, z limitami. [Warunki](https://open-meteo.com/en/terms) |
| IMGW-PIB | Dane publiczne, wymagana informacja o źródle i przetworzeniu. [Regulamin](https://danepubliczne.imgw.pl/pl/regulations) |
| GUGiK: EGiB, ULDK, PRG, NMT, BDOT10k, mapa glebowo-rolnicza | Dane PZGiK udostępniane bez opłat (ustawa Prawo geodezyjne i kartograficzne). [Geoportal](https://www.geoportal.gov.pl) |
| SoilGrids 2.0 | CC BY 4.0, ISRIC. [Warunki](https://isric.org/explore/soilgrids/) |
| Sentinel-2 | Copernicus: bezpłatny, pełny i otwarty dostęp. [Warunki](https://ewds.climate.copernicus.eu/licences/ec-sentinel) |
| Copernicus EDO | Polityka danych Copernicus, z przypisaniem źródła. [EDO](https://drought.emergency.copernicus.eu/) |
| Copernicus DEM GLO-30 | Licencja Copernicus DEM, bezpłatna z przypisaniem |
| ESA WorldCover 2021 | CC BY 4.0. [WorldCover](https://esa-worldcover.org/) |
| OpenStreetMap | ODbL 1.0. [Warunki](https://www.openstreetmap.org/copyright) |
| Esri World Imagery | Warunki Esri, wymagana atrybucja (wyświetlana na mapie) |
| OpenTopoMap | CC BY-SA 3.0, dane OSM |
| polska-geojson | MIT |
| Akty prawne i obwieszczenia MRiRW | Dokumenty urzędowe, nie są przedmiotem prawa autorskiego (art. 4 ustawy o prawie autorskim) |

Raport podaje przy każdym źródle licencję i wymaganą atrybucję w zakresie dostępnych metadanych.

### 7.2 Komponenty

| Komponenty | Licencja |
| --- | --- |
| FastAPI, Pydantic, pydantic-settings, Structlog, PyYAML, pyproj, pytest, anthropic (SDK) | MIT |
| Uvicorn, HTTPX, pandas, Shapely, Rasterio, RESPX, pypdf, Jinja2, WeasyPrint, NumPy, SciPy | BSD |
| DiskCache, pystac-client, PyArrow, pytest-asyncio, google-genai (SDK), tzdata | Apache-2.0 |
| Matplotlib | Licencja Matplotlib (oparta na PSF) |
| Python | PSF |
| GDAL (w kołach Rasterio) | MIT |
| Pango (LGPL), HarfBuzz (MIT), czcionki DejaVu | W obrazie Dockera |
| SQLite | Domena publiczna |
| React, React DOM, React Router, TanStack Query, Zustand, Zod, Vite, @vitejs/plugin-react | MIT |
| Leaflet | BSD-2-Clause |
| React Leaflet | Hippocratic License 2.1 (zakazuje użycia sprzecznego z prawami człowieka, nie ogranicza użycia przez KOWR) |
| TypeScript | Apache-2.0 |

Wszystkie licencje pozwalają na korzystanie z rozwiązania i jego modyfikację w zakresie
przeniesienia praw do KOWR (Regulamin § 2 ust. 10 i § 5). Usługi AI wymagają własnego klucza
API i akceptacji warunków dostawcy ([Gemini API](https://ai.google.dev/gemini-api/terms),
[Anthropic](https://www.anthropic.com/legal/commercial-terms)).

## 8. Znane ograniczenia

- **Skala oceny.** KBW działki pochodzi z siatki modelu pogodowego (0,1–0,25°) lub z najbliższej
  stacji IMGW-PIB. Urzędowe obwieszczenia podają wynik dla gminy na podstawie gęstszej sieci,
  opadu radarowego i innego wzoru ETP. Różnice w pojedynczych przypadkach są możliwe.
- **Gleba.** SoilGrids ma rozdzielczość 250 m. Kategoria gleby z mapy glebowo-rolniczej
  bywa niedostępna na terenach zabudowanych. Wtedy KBW nie ma progu, a raport to podaje.
- **Satelita.** Zachmurzenie, małe działki (< 20 pikseli wewnątrz) lub brak scen w oknie
  ograniczają VCI. Aplikacja nie zna dat siewu ani zbioru, więc okresy wrażliwości przybliża
  okresami KBW.
- **Teren i hydrologia.** Jakość miejsc retencji zależy od NMT. Przy zapasowym Copernicus DEM
  (30 m) wskazania są mniej szczegółowe. Rekomendacje przestrzenne wymagają wizji w terenie
  i mogą wymagać uzgodnień wodnoprawnych lub zgody właściciela gruntu.
- **Nawadnianie.** Dawka i termin są orientacyjne. Model nie zna rzeczywistych zabiegów,
  wcześniejszego nawadniania, podsiąku ani pomiarów wilgotności z pola.
- **Dostępność źródeł.** Usługi zewnętrzne mają limity (np. HTTP 429 Open-Meteo) i przerwy.
  Analiza ma budżet 30 s. Źródło, które nie zdąży, ma w raporcie status `partial` lub `missing`.
- **Poza sezonem monitoringu** (od 1.10 do 20.03) nie ma bieżącego werdyktu KBW ani dawki nawadniania.
- **Wdrożenie.** Prototyp działa lokalnie na jednej instancji. Brak HTTPS, kont użytkowników
  i limitów ruchu ([rozdz. 12](#12-bezpieczeństwo-i-dane-osobowe)).
- **Frontend.** Brak testów automatycznych frontendu. Gdy rejestr działek jest niedostępny
  albo w narysowanej ramce nie ma działek, mapa pokazuje zastępczy obrys lub sam obszar
  z wyraźnie oznaczonymi wynikami demonstracyjnymi.
- **Komentarz AI** interpretuje liczby z analizy i może zawierać nieścisłości. Nie zastępuje
  obliczeń ani rekomendacji z reguł.

Ograniczenia każdej analizy są też w raporcie, w sekcji ograniczeń.

## 9. Weryfikacja wyników i rekomendacji

### 9.1 Testy automatyczne

Z katalogu `backend`:

```powershell
python -m pytest tests/a tests/b tests/contract
```

Wynik z 22.11.2026: **355 testów zaliczonych, 5 pominiętych**. Pominięte testy wymagają
bibliotek Pango (PDF przez WeasyPrint) albo trybu `GEO_PROVIDER=real` z dostępem do sieci. Testy obejmują progi KBW, wzory ETP i SPI, model glebowy, brak i częściowe dane,
fallbacki źródeł, limit czasu, zapis raportu i odczyt po restarcie, PDF oraz kontrakt API.
CI na GitHub Actions uruchamia testy części B w Dockerze
([workflow](.github/workflows/part-b.yml)). Frontend: `npm run build` sprawdza typy TypeScript.

### 9.2 Porównanie z urzędowymi danymi o suszy

Wyniki porównano z obwieszczeniami MRiRW dla 8 działek w różnych województwach i dwóch
terminów (10.07.2018 i 31.05.2023).

- Zgodność werdyktu suszy Vedry z werdyktem MRiRW dla gminy: **14 z 16** przypadków.
- Średni błąd bezwzględny KBW: 19,1 mm (2018) i 24,9 mm (2023).
- Reguła progowa po podstawieniu urzędowego KBW odtwarza werdykt w **16 z 16** przypadków.

Tabele i polecenia do odtworzenia: [walidacja KBW](backend/docs/VALIDATION.md).

### 9.3 Test na żywo i czas odpowiedzi

22.11.2026 w trybie `real`, z pustą pamięcią podręczną:

| Działka | Uprawa, data | Czas analizy | Wynik |
| --- | --- | ---: | --- |
| 303005_5.0323.25/7 (Września) | zboża ozime, 2018-07-10 | 5,8 s | susza, KBW −254 mm, 24 zalecenia, PDF w 3,9 s |
| 141201_1.0001.6509 | zboża ozime, 2026-11-20 | 15,1 s | poza sezonem, ostatni oceniony okres, 15 zaleceń |
| 100206_2.0008.273/23 (Kutno) | rzepak, 2025-06-15 | 4,2 s | brak suszy, KBW −99 mm |
| 126105_9.0001.311 (Kraków, zabudowa) | ziemniaki, 2023-05-31 | 1,7 s | brak kategorii gleby, podane wprost, bez zaleceń |

Wszystkie analizy zmieściły się w limicie 30 s. Profil czasów źródeł:
[źródła przestrzenne](backend/docs/DATA_SOURCES.md#live-performance-check).

### 9.4 Jak sprawdzić pojedynczy raport

- Porównaj kategorię gleby, okres KBW, wartość bilansu i próg z tabelą rozporządzenia.
- Porównaj werdykt z mapą [Systemu Monitoringu Suszy Rolniczej IUNG-PIB](https://susza.iung.pulawy.pl/)
  dla gminy i tego samego okresu.
- Każde zalecenie ma przesłankę z danych i odsyłacz do źródła. Sekcja źródeł podaje
  adres usługi, datę pobrania i licencję.
- Widok webowy pozwala zapisać, czy miejsce retencji potwierdziło się w terenie.

## 10. Dostępność dla użytkownika i koszty

Podstawowe funkcje nie wymagają od rolnika licencji, konta, specjalnego sprzętu, znajomości
GIS, programowania ani instalacji. Wystarczy przeglądarka na komputerze lub telefonie.

| Element | Koszt w prototypie | Uwagi i alternatywy |
| --- | --- | --- |
| Dane GUGiK, IMGW-PIB, Copernicus, SoilGrids, WorldCover, OSM | Bezpłatne | Dane publiczne i otwarte. |
| Open-Meteo | Bezpłatne do użytku niekomercyjnego, z limitem zapytań | Przy wdrożeniu: plan płatny Open-Meteo, własna instancja (kod open source) albo archiwum IMGW-PIB, które już jest zapasem. |
| Microsoft Planetary Computer, Earth Search | Bezpłatne | Alternatywa: Copernicus Data Space Ecosystem. |
| Esri World Imagery | Bezpłatne do użytku niekomercyjnego, z atrybucją | Alternatywa: ortofotomapa Geoportalu (WMS/WMTS) lub OpenStreetMap. |
| Komentarz AI: Google Gemini | Bezpłatny plan z limitem zapytań | Funkcja opcjonalna. Bez klucza komentarz powstaje z reguł. Plan płatny rozlicza się za liczbę tokenów. |
| Komentarz AI: Anthropic Claude | Płatne za tokeny | Opcjonalne i domyślnie wyłączone (`AI_PROVIDER=gemini`). |
| Hosting | Brak (uruchomienie lokalne) | Patrz rozdz. 11. |

## 11. Skalowalność

Prototyp działa dla dowolnej działki w Polsce, bo wszystkie źródła mają zasięg krajowy.

- **Limity i dostępność źródeł.** Pamięć podręczna na dysku dla danych statycznych (gleba, NMT,
  sieć wodna, wyniki scen). Pogoda jest buforowana per komórka 0,1°, a później pobierane są
  tylko nowe dni. Każde źródło ma zapasowe źródło. Aplikacja respektuje nagłówek `Retry-After`
  przy HTTP 429. Liczba równoległych analiz jest ograniczona. Raporty i PDF są zapisywane,
  więc ponowne otwarcie nie wymaga obliczeń.
- **Aktualizacja danych.** Dane bieżące pobierane są przy analizie. Archiwum IMGW-PIB i lokalną
  kopię EGiB odświeża się skryptami z [`backend/scripts`](backend/scripts).
- **Większy ruch.** Wspólna kolejka zadań (np. Redis) i kilka procesów roboczych. Osobne procesy
  do rastrów i PDF. PostgreSQL/PostGIS zamiast SQLite i magazyn obiektów na PDF. Wstępne
  pobranie pogody i gleby dla siatki Polski. Lokalna kopia EGiB dla całego kraju.
- **Koszty.** Serwer obliczeniowy z kilkoma rdzeniami i dyskiem na cache rastrów, magazyn
  raportów, transfer danych, kopie zapasowe, płatny plan Open-Meteo lub własna instancja,
  opcjonalnie opłaty za tokeny AI.

Szczegóły: [skalowanie](backend/docs/SCALABILITY.md).

## 12. Bezpieczeństwo i dane osobowe

- Aplikacja nie wymaga konta i nie zbiera imion, nazwisk, adresów e-mail ani danych o
  właścicielach działek. Przyjmuje identyfikator działki lub współrzędne, uprawę i datę.
- Walidacja wejścia w Pydantic: zakres współrzędnych, zakres daty (ostatnie 10 lat),
  kod uprawy, liczba raportów w jednym PDF. Błędy są zwracane po polsku.
- Klient HTTP łączy się tylko z listą dozwolonych hostów. Adresy usług ustala kod, nie użytkownik.
- Zapytania SQL z parametrami. Szablony PDF z ucieczką znaków HTML. Nagłówek
  `X-Content-Type-Options: nosniff`, CORS tylko dla adresu frontendu.
- Kontener działa jako użytkownik `nobody`. Instrukcja uruchomienia udostępnia port tylko na `127.0.0.1`.
- Klucze API są przekazywane wyłącznie przez zmienne środowiskowe i nie trafiają do repozytorium.
- **Komentarz AI** wysyła dane analizy (identyfikator i lokalizację działki, uprawę, datę,
  wyniki) do zewnętrznej usługi tylko po wyraźnej zgodzie w oknie z informacją RODO.
  Bez zgody backend odrzuca żądanie (HTTP 403).
- Zalecenia dla wdrożenia publicznego: HTTPS, limity ruchu, czas przechowywania raportów,
  kopie zapasowe.

Szczegóły: [bezpieczeństwo](backend/docs/SECURITY.md).

## 13. Użycie sztucznej inteligencji

**W działającej aplikacji.** Wyniki, przyczyny i rekomendacje oblicza deterministyczny kod
według opisanych metod i reguł. AI ich nie tworzy ani nie zmienia. Jedyna funkcja AI to
opcjonalny komentarz do symulacji „Co jeśli?”. Model językowy (Google Gemini lub Anthropic
Claude) dostaje liczby z gotowej analizy i pisze krótkie podsumowanie, prognozę bez działań
i wskazanie najkorzystniejszego działania. Odpowiedź ma ustaloną strukturę JSON. Komentarz
jest oznaczony jako AI i wymaga zgody użytkownika. Bez klucza API ta sama sekcja powstaje
z reguł. Kod: [`backend/app/ai/insight.py`](backend/app/ai/insight.py).

**Przy tworzeniu kodu.** Zespół używał asystentów programistycznych: OpenAI Codex, Claude Code
(Claude Opus 5.5) i Google Gemini. Pomagały w czytaniu dokumentacji źródeł, pisaniu kodu,
testów i dokumentacji. Metody, progi i źródła sprawdzono z aktami prawnymi i literaturą,
a obliczenia testami i porównaniem z danymi MRiRW.

Szczegóły: [użycie AI](backend/docs/AI_USAGE.md).

## 14. Wygenerowane raporty

Przykładowe raporty PDF wygenerowane przez prototyp (renderer WeasyPrint, dane geo zapisane
21.11.2026, pogoda z archiwum IMGW-PIB):

- [Września, zboża jare, 10.07.2018 – susza](backend/data/b/samples/reports/wrzesnia-2018-07-10.pdf)
- [Inowrocław, zboża jare, 31.05.2023 – brak suszy](backend/data/b/samples/reports/inowroclaw-2023-05-31.pdf)
- [Kętrzyn, zboża jare, 21.11.2026 – poza sezonem](backend/data/b/samples/reports/ketrzyn-2026-11-21.pdf)

Odtworzenie: w katalogu `backend` uruchom `python -m scripts.b.generate_sample_reports --offline`.
Dowolny nowy raport można pobrać z aplikacji przyciskiem **Pobierz PDF**.
