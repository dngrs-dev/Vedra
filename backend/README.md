# Vedra — backend

Vedra to prototyp przygotowany na HackNation 2026 dla zadania KOWR „Zatrzymaj wodę, chroń plony”.
Pomaga ocenić sytuację wodną działki, zrozumieć możliwe przyczyny niedoboru i wybrać działania
retencyjne lub agrotechniczne. Raport obejmuje pochodzenie danych, ograniczenia i opcjonalną
ocenę zasadności nawadniania.

## 1. Funkcje

1. Wyszukanie działki po pełnym identyfikatorze ULDK, nazwie obrębu i numerze lub współrzędnych.
2. Wybór uprawy i daty analizy z ostatnich dziesięciu lat. Obliczenia historyczne kończą się na wybranej dacie.
3. Ocena klimatycznego bilansu wodnego (KBW), sygnałów uzupełniających i historycznej podatności.
4. Wskazanie możliwych przyczyn oraz zaleceń opartych na dostępnych danych. Kolejność działań to
   retencja krajobrazowa, retencja glebowa, agrotechnika i opcjonalne nawadnianie.
5. Zapis raportu pod trwałym identyfikatorem oraz pobranie JSON lub PDF do wydruku.

Cel wydajności to 30 s dla pojedynczej analizy z pustą pamięcią podręczną. Wyniki pomiarów i ich
zakres opisuje [lista kontrolna części B](docs/PART_B_ANALYTICS_PRODUCT.md#cp4--validation-and-robustness--0700).

## 2. Architektura

```text
HTTP (FastAPI) → zadanie analizy → potok obliczeń → raport JSON → SQLite
                                       ↓                               ↓
                GeoProvider (działka i dane przestrzenne)    WeasyPrint / Matplotlib → PDF
                Open-Meteo (pogoda, pobierana równolegle)
```

Część A dostarcza fakty i dane przestrzenne przez `GeoProvider`. Część B pobiera pogodę,
oblicza wskaźniki, ocenia ich zgodność i uzasadnia zalecenia. Umowa między częściami opisuje typy,
sposób zgłaszania braków i maksymalny czas pobierania.
[Kontrakty](docs/CONTRACTS.md), [podział odpowiedzialności](docs/TEAM_SPLIT.md).

Frontend i backend działają z jednego drzewa repozytorium. Podział na części dotyczy
odpowiedzialności za kod. Zrzuty danych, pomiary oraz decyzje projektowe dokumentują
[część A](docs/PART_A_DATA_GEO.md) i [część B](docs/PART_B_ANALYTICS_PRODUCT.md).
W części B pozostało uruchomienie przez HTTPS jako ostatni krok. Obie części można sprawdzić lokalnie.

## 3. Stan integracji

Tryb `real` wyszukuje kontur przez lokalną kopię EGiB, jeśli ją skonfigurowano, a następnie
przez EGiB WFS i źródła zapasowe. Pobiera dane przestrzenne
przez dostawcę części A. Tryb `fixtures` korzysta z zapisanych przypadków, a `fake` służy do
demonstracji. Raport pokazuje dostępne wyniki oraz powody braków.
[Źródła danych przestrzennych](docs/DATA_SOURCES.md).

Frontend uruchamia `POST /api/analyses` dla każdej pary działka–uprawa i odczytuje postęp zadania.
Działki z listy identyfikatorów lub inteligentnego zaznaczenia można analizować w jednej serii.
Porównanie pokazuje różniące się wyniki KBW dla tej samej uprawy i okresu.
Dla każdej działki można pobrać PDF ze wszystkimi gotowymi uprawami albo raport dla jednej uprawy.
Własne obszary i zastępcze obrysy korzystają z wyników demonstracyjnych.
[Uruchomienie frontendu](../frontend/README.md).

## 4. API

| Metoda i ścieżka | Działanie |
| --- | --- |
| `GET /api/health` | Sprawdzenie usługi i wybranego trybu. |
| `GET /api/crops` | Lista upraw z rozporządzenia, pola `code` i `name_pl`. |
| `GET /api/parcels/search?q=` | Wyszukanie działek po identyfikatorze lub obrębie i numerze. |
| `GET /api/parcels/by-point?lat=&lon=` | Działka pod wskazanym punktem. |
| `POST /api/analyses` | Uruchomienie zadania i zwrot `analysis_id` z kodem 202. |
| `GET /api/analyses/{id}` | Stan, postęp i raport po zakończeniu. |
| `GET /api/analyses/{id}/report.pdf` | Pobranie raportu w formacie PDF. |
| `GET /api/analyses/report.pdf?analysis_id=&analysis_id=` | Jeden PDF dla kilku upraw działki: część ogólna, część dla każdej uprawy i wspólne źródła danych, bez powtórzeń. |
| `GET /api/reports/{id}` | Odczyt zapisanego raportu po `report_id`. |
| `POST /api/analyses/{id}/scenarios` | Symulacja „co jeśli”: retencja, próchnica, międzyplony/mulcz, nawadnianie wobec wariantu bez działań. |
| `POST /api/analyses/{id}/ai-insight` | Prognoza i porada AI: Gemini (`GEMINI_API_KEY`, darmowy limit) lub Claude (`AI_PROVIDER=anthropic`, `ANTHROPIC_API_KEY`); bez klucza podsumowanie z reguł. |

Docelowa forma odpowiedzi to [model raportu](app/contracts/report.py).
[Przykład JSON](tests/fixtures/sample_report.json).

## 5. Uruchomienie lokalne

**Docker** z katalogu głównego repozytorium.

```sh
docker build -t vedra-backend backend
docker run --rm -e GEO_PROVIDER=fake -p 127.0.0.1:8000:8000 vedra-backend
```

**Python 3.11, PowerShell** z katalogu głównego repozytorium.

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements/base.txt -r requirements/a-geo.txt -r requirements/b-app.txt
$env:GEO_PROVIDER = 'fake'
.\.venv\Scripts\python.exe -m uvicorn app.main:app
```

**Python 3.11, Linux lub WSL** z katalogu głównego repozytorium.

```sh
cd backend
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements/base.txt -r requirements/a-geo.txt -r requirements/b-app.txt
GEO_PROVIDER=fake python -m uvicorn app.main:app
```

PDF powstaje przez WeasyPrint, gdy dostępne są biblioteki Pango i czcionki z polskimi znakami.
Obraz Dockera zawiera te zależności.
[Instalacja WeasyPrint](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html).
Bez Pango, np. w zwykłej instalacji Pythona w Windows, ten sam raport tworzy wbudowany moduł
oparty na Matplotlib (`app/reports/pdf_basic.py`). Nie wymaga on dodatkowej instalacji.

### Próba w przeglądarce

Otwórz [dokumentację lokalnego API](http://localhost:8000/docs). Sprawdź `/api/health`, a następnie
użyj `POST /api/analyses` z poniższą demonstracyjną działką i jedną z dat kontrolnych zespołu.

```json
{
  "parcel_id": "141201_1.0001.6509",
  "crop_code": "winter_cereals",
  "analysis_date": "2023-05-31",
  "include_irrigation": false
}
```

Skopiuj zwrócony `analysis_id`, sprawdź `GET /api/analyses/{id}` do stanu `done`, a potem
otwórz `/api/analyses/{id}/report.pdf`. Tryb `fake` dostarcza syntetyczne dane przestrzenne,
a backend nadal próbuje pobrać pogodę. Gdy model nie dostarcza danych potrzebnych do KBW,
backend korzysta z dołączonego archiwum dobowego IMGW-PIB i wskazuje stację w raporcie.

| Zmienna | Wartość domyślna | Znaczenie |
| --- | --- | --- |
| `GEO_PROVIDER` | `real` | `real` pobiera dane części A, `fixtures` czyta zapisy części A, `fake` zwraca dane demonstracyjne. |
| `EGIB_SNAPSHOT_PATH` | brak | Ścieżka do opcjonalnej lokalnej bazy granic działek dla trybu `real`. |
| `ANALYSIS_CONCURRENCY` | `2` | Maksymalna liczba analiz wykonywanych równolegle przez proces API. |
| `CACHE_DIR` | `.cache` | Pamięć podręczna źródeł. |
| `DB_PATH` | `data/vedra.sqlite` | Baza raportów. |
| `CORS_ORIGINS` | `http://localhost:5173` | Dozwolone adresy frontendu, rozdzielone przecinkami. |
| `LOG_LEVEL` | `INFO` | Poziom logowania. |
| `AI_ENABLED` | `true` | Włącza opcjonalny komentarz AI do symulacji „Co jeśli?”. |
| `AI_PROVIDER` | `gemini` | `gemini` (Google AI Studio) albo `anthropic` (Claude). |
| `GEMINI_API_KEY` | brak | Klucz Gemini. Bez klucza komentarz powstaje z reguł. |
| `GEMINI_MODEL`, `GEMINI_FALLBACK_MODEL` | `gemini-3.5-flash`, `gemini-3.5-flash-lite` | Model główny i zapasowy przy przeciążeniu. |
| `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL` | brak, `claude-opus-5-5` | Klucz i model dla `AI_PROVIDER=anthropic`. |

Jeden proces API obsługuje kolejkę i odpytywanie w toku zadania. Limit czasu analizy zaczyna się
po zwolnieniu miejsca w kolejce. Zapisane raporty przeżywają restart.
W Dockerze można oddzielić dane raportów od dołączonych danych źródłowych przez
`-e DB_PATH=/app/state/vedra.sqlite -v vedra-state:/app/state`.

## 6. Dane, zakresy i pochodzenie

| Źródło | Zakres i sposób pozyskania | Warunki |
| --- | --- | --- |
| Open-Meteo, ERA5 / ERA5-Land | Pobieranie na żądanie od 1 stycznia 1991 r. do daty analizy. Dzienne opady, ET0, temperatura, usłonecznienie i długość dnia oraz średnie dobowe wilgotności gleby. Prognoza uzupełnia końcową lukę archiwum i może posłużyć jako dane do planowania nawadniania dla bieżącej daty. | Dane CC BY 4.0 z przypisaniem autorstwa. Bezpłatna usługa ma limity i warunki użycia niekomercyjnego. [Warunki Open-Meteo](https://open-meteo.com/en/terms). |
| IMGW-PIB, dobowe SYNOP | Dołączona baza SQLite obejmuje opad, temperaturę i usłonecznienie z 63 stacji. Zakres dostępnych plików to 1991-01-01 – 2026-10-31. Dane pobrano 21.11.2026. Daty pobrań i sumy kontrolne plików są w tabeli `input`. | Źródłem pochodzenia danych jest Instytut Meteorologii i Gospodarki Wodnej – Państwowy Instytut Badawczy. Dane Instytutu Meteorologii i Gospodarki Wodnej – Państwowego Instytutu Badawczego zostały przetworzone. [Regulamin](https://danepubliczne.imgw.pl/pl/regulations). |
| EGiB, PRG i mapa glebowo-rolnicza | Tryb `real` pobiera granice działki po identyfikatorze lub punkcie z krajowego EGiB WFS. Nazwy województw i powiatów pochodzą z dołączonego zestawienia PRG. Przy braku wyniku backend próbuje ULDK i krajowego eksportu GeoParquet. Kategoria gleby pochodzi z odrębnych źródeł glebowych. | [EGiB WFS](https://mapy.geoportal.gov.pl/wss/service/PZGIK/EGIB/WFS/UslugaZbiorcza), [PRG](https://www.geoportal.gov.pl/pl/dane/panstwowy-rejestr-granic-prg/), [ULDK GUGiK](https://uldk.gugik.gov.pl/), [informacja o usłudze WMS](https://www.geoportal.gov.pl/aktualnosci/usluga-wms-prezentujaca-mape-glebowo-rolnicza-dostepna-w-serwisie-www-geoportal-gov-pl/). |
| SoilGrids 2.0 | Profil glebowy o rozdzielczości 250 m. Dla działek kontrolnych część A korzysta także z odpowiedzi pobranych 21.11.2026. | CC BY 4.0, ISRIC. [Warunki SoilGrids](https://isric.org/explore/soilgrids/). |
| Sentinel-2, NMT, hydrografia, pokrycie terenu, EDO i IMGW | Część A pobiera obserwacje Sentinel-2 przez Planetary Computer lub Earth Search, model terenu GUGiK lub Copernicus DEM, dane hydrograficzne BDOT10k lub OSM, ESA WorldCover, Copernicus EDO oraz bieżące dane IMGW. Raport wskazuje, które źródła zwróciły dane dla danej działki i daty. | [Źródła przestrzenne, zakresy i warunki](docs/DATA_SOURCES.md), [konfiguracja źródeł](config/geo_sources.yaml). |
| MRiRW, obwieszczenia KBW | Załączniki dla okresów kończących się 10.07.2018 i 31.05.2023 pobrano 21.11.2026. Parquet i sumy kontrolne dokumentują walidację. Progi z Dz.U. 2017 poz. 732 i Dz.U. 2019 poz. 739 oraz współczynniki literaturowe są w wersjonowanej konfiguracji. | Dokumenty urzędowe. [Manifest](data/b/manifest.json), [porównanie z obwieszczeniami](docs/VALIDATION.md), [progi 2017](https://eli.gov.pl/eli/DU/2017/732/ogl), [progi 2019](https://eli.gov.pl/eli/DU/2019/739/ogl). |

Zapisane odpowiedzi geo z 21.11.2026 służą lokalnym testom oraz demonstracji powtarzalnych przypadków.
Potok za każdym uruchomieniem oblicza wynik i zalecenia na podstawie wejściowych danych.
Raport wskazuje źródło, datę pobrania, warunki i przypisanie autorstwa w zakresie dostępnych metadanych.
[Metodyka](docs/METHODOLOGY.md).

Wyniki wyszukiwania przez krajowe EGiB WFS są buforowane przez dobę. Potwierdzenie działki po kliknięciu
może użyć już zapisanego konturu zamiast ponownie pobierać go po identyfikatorze. Nazwy administracyjne
zapisano 21.11.2026 w `config/cadastral_teryt.json` z warstw województw i powiatów usługi PRG WFS.

### Lokalna kopia granic działek EGiB

Katalog Otwarte Dane odsyła do usług GUGiK, między innymi KIEG (WMS) i ULDK. Do lokalnej kopii
granic używamy eksportu GeoParquet z Geoportalu. Zawiera geometrię i identyfikatory oraz podstawowe
atrybuty działek. [Katalog Otwarte Dane](https://dane.gov.pl/pl/dataset/925),
[Eksporty Geoportalu](https://www.geoportal.gov.pl/aktualnosci/nowa-usluga-dane-powiatowe-dostepna-w-serwisie-www-geoportal-gov-pl/),
[Warunki danych EGiB](docs/DATA_SOURCES.md#22-egib-geoparquet-export--prg-uldk-fallback).

Poniższy przykład dla województwa warmińsko-mazurskiego uruchom w katalogu `backend`, w środowisku
Pythona z zależnościami Vedry. Polecenie zapisuje pliki poza repozytorium.

```powershell
$vedraEgib = Join-Path $env:TEMP 'vedra-egib-snapshot'
New-Item -ItemType Directory -Force $vedraEgib | Out-Null
$export = Join-Path $vedraEgib '28_dzialki.parquet'
$env:EGIB_SNAPSHOT_PATH = Join-Path $vedraEgib 'egib-28.sqlite'
curl.exe --fail --remote-time --output $export https://opendata.geoportal.gov.pl/InneDane/latest_exports/eziudp_wfs/PARQUET/28_dzialki.parquet
python -m scripts.b.build_egib_snapshot --output $env:EGIB_SNAPSHOT_PATH $export
$env:GEO_PROVIDER = 'real'
python -m uvicorn app.main:app
```

W Dockerze zamontuj gotową bazę tylko do odczytu, np. przez `--mount type=bind,source=$env:EGIB_SNAPSHOT_PATH,target=/app/egib.sqlite,readonly`,
i ustaw `-e EGIB_SNAPSHOT_PATH=/app/egib.sqlite` oraz `-e GEO_PROVIDER=real`.

Podaj jeden [eksport krajowy](https://opendata.geoportal.gov.pl/InneDane/latest_exports/eziudp_wfs/PARQUET/0_dzialki.parquet)
lub zestaw plików z różnych województw. Baza obejmuje tylko zaimportowane dane. Czytanie po
identyfikatorze i kliknięcie na mapie najpierw sprawdzają bazę lokalną. Po braku jednoznacznego
wyniku aplikacja przechodzi do zwykłego wyszukiwania online. Pozostałe dane analizy korzystają
z dotychczasowych źródeł. Wyszukiwanie nazwą obrębu oraz zaznaczanie ramką korzystają z usług online.

Do aktualizacji pobierz nowszy eksport i ponownie uruchom skrypt. Skrypt podmienia bazę po udanej
budowie. Dla pliku krajowego zapewnij miejsce na eksport, gotowy indeks oraz budowaną kopię.

Aby odtworzyć bazę IMGW-PIB, uruchom w katalogu `backend` polecenie
`python -m scripts.b.build_imgw_weather --cache-dir <katalog-roboczy>`. Budowa pobiera
publiczne pliki SYNOP i zapisuje `data/b/imgw_daily.sqlite`. Do aktualizacji użyj nowego
katalogu roboczego, aby odczytać nowsze wersje opublikowanych plików.

## 7. Komponenty i licencje

Wykaz bezpośrednich zależności obejmuje również narzędzia testowe.
[Zależności wspólne](requirements/base.txt), [geoprzestrzenne](requirements/a-geo.txt),
[analityczne](requirements/b-app.txt).

| Zastosowanie | Komponenty i licencje |
| --- | --- |
| API, zapisy, konfiguracja | Python (PSF), FastAPI i Pydantic (MIT), Uvicorn i HTTPX (BSD-3-Clause), SQLite (domena publiczna), DiskCache (Apache-2.0), Structlog (MIT lub Apache-2.0), PyYAML (MIT), tzdata (Apache-2.0 z danymi IANA). |
| Obliczenia i GIS | NumPy i SciPy (licencje BSD wraz z warunkami dołączonych składników), pandas, Shapely i Rasterio (BSD-3-Clause), pyproj (MIT), pystac-client (Apache-2.0). |
| PDF i wykresy | Jinja2 i WeasyPrint (BSD), Matplotlib (licencja Matplotlib oparta na PSF), Pango (LGPL), HarfBuzz (MIT) i DejaVu (warunki Bitstream Vera i dodatków DejaVu). [Licencja Pango](https://github.com/GNOME/pango/blob/main/COPYING), [licencja DejaVu](https://github.com/dejavu-fonts/dejavu-fonts/blob/master/LICENSE). |
| Komentarz AI | google-genai (Apache-2.0), anthropic (MIT). Usługi wymagają klucza i akceptacji warunków dostawcy. [Użycie AI](docs/AI_USAGE.md). |
| Testy i porównanie urzędowe | pytest (MIT), pytest-asyncio (Apache-2.0), RESPX (BSD-3-Clause), pypdf (BSD-3-Clause) i PyArrow (Apache-2.0). |

Modele obliczeniowe obejmują Doroszewskiego–Górskiego, FAO-56, SPI i Saxtona–Rawlsa.
Użycie AI w aplikacji i przy tworzeniu kodu opisuje [wykaz użycia AI](docs/AI_USAGE.md).

## 8. Ograniczenia

- Werdykt działki jest oszacowaniem z siatki meteorologicznej lub ze stacji IMGW-PIB. Urzędowe obwieszczenia podają wynik dla gminy.
- Geometria i kategoria gleby mogą pochodzić ze źródeł o różnej rozdzielczości. Zalecenia przestrzenne
  zależą od pokrycia danymi i od szczegółowości modelu terenu.
- Brak pełnych danych pogodowych może uniemożliwić obliczenie KBW, historii lub dawki. Ograniczenia
  i tryb poza sezonem są widoczne w raporcie.
- Dawka i termin nawadniania są orientacyjne. W obliczeniach nie ma rzeczywistych terminów zabiegów,
  wcześniejszego nawadniania ani pomiarów wilgotności wykonanych na działce.
- Tryb uruchomienia oraz dostępność poszczególnych źródeł opisuje [stan integracji](#3-stan-integracji).
  Limity i utrzymanie opisują [skalowalność](docs/SCALABILITY.md) i [bezpieczeństwo](docs/SECURITY.md).

## 9. Weryfikacja

W katalogu `backend` uruchom `python -m pytest tests/b`. W zintegrowanym drzewie uruchom dodatkowo
`python -m pytest tests/b tests/contract` z zapisami geo części A. W Dockerze można użyć
`docker build --target test backend` z katalogu głównego repozytorium.

- W raporcie porównaj datę i kategorię gleby, okres KBW, wartość i próg. Sprawdź wskazaną przesłankę,
  źródło i odsyłacz przy każdym zaleceniu.
- Dla dat historycznych przejrzyj urzędowe wartości odpowiednich gmin. Tabela podaje przypadki
  ocenione, rozbieżności metod oraz brakujące porównania. Skrypt obsługuje porównanie z lokalnymi
  pomiarami IMGW-PIB. [Walidacja KBW](docs/VALIDATION.md).
- Testy sprawdzają między innymi progi, brak danych, zapis raportu, odczyt po restarcie i PDF.
  Scenariusze porównawcze oraz kolejne kroki dokumentuje [lista kontrolna części B](docs/PART_B_ANALYTICS_PRODUCT.md).

### Przykładowe raporty PDF

Przykłady wykorzystują zapisane dane przestrzenne części A i dołączone pomiary IMGW-PIB.
Raporty z Wrześni i Inowrocławia pokazują KBW dla wskazanych dat. Raport z Kętrzyna
pokazuje przypadek poza sezonem oceny oraz ostatni dostępny okres historyczny.
Powtarzające się zalecenia dla miejsc retencji mają wspólne uzasadnienie. W raporcie webowym
można wybierać miejsca na mapie. W PDF numery na mapach prowadzą do tabel z pomiarami i uwagami
dla poszczególnych miejsc.

Plan wizji w terenie wskazuje pierwsze miejsce zgodnie z kolejnością zaleceń. Preferuje miejsca
bez uwagi o konieczności uzgodnienia wizji z właścicielem terenu. W widoku webowym można zapisać,
czy obliczone warunki potwierdziły się na miejscu. Obserwacje są przechowywane w bieżącej
przeglądarce dla danej działki, uprawy, daty analizy i geometrii miejsca. Wydruk zawiera pola
do odznaczania sprawdzonych miejsc.

- [Września, 10.07.2018](data/b/samples/reports/wrzesnia-2018-07-10.pdf)
- [Inowrocław, 31.05.2023](data/b/samples/reports/inowroclaw-2023-05-31.pdf)
- [Kętrzyn, 21.11.2026](data/b/samples/reports/ketrzyn-2026-11-21.pdf)

W zintegrowanym drzewie i w katalogu `backend` wygeneruj raporty z zapisanymi danymi geo
i archiwum IMGW-PIB poleceniem `python -m scripts.b.generate_sample_reports --offline`.
Bez tej opcji aplikacja sprawdza dostępność Open-Meteo przed użyciem danych stacyjnych.
