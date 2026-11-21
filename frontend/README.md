# Vendra (frontend)

Aplikacja webowa dla rolników: wskaż działkę (ID lub klik na mapie), wybierz uprawę i datę → ocena wilgotności i ryzyka suszy (10 lat), rekomendacje retencyjne / agrotechniczne / nawodnieniowe, raport PDF.

**Stack:** Vite · React 18 · TypeScript (strict) · react-leaflet · TanStack Query · Zustand · Zod · React Router (BrowserRouter).

## Uruchomienie

```bash
npm install
cp .env.example .env     # domyślnie backend dla jednej działki ewidencyjnej
npm run dev              # http://localhost:5173
npm run build            # typecheck + produkcyjny build do dist/
```

Build to zwykłe pliki statyczne (`dist/`). Adresy: `/` (strona główna), `/map` (mapa), `/report` (raport). Hosting musi zwracać `index.html` dla każdej ścieżki — w projekcie są `vercel.json` (Vercel) i `public/_redirects` (Netlify).

## Przepływ użytkownika

1. `/` — krótka strona główna (przycisk **Zobacz mapę**).
2. `/map` — mapa Polski z liniami województw. Klik w województwo → mapa przybliża się, jego etykieta znika (przycisk „← Cała Polska” cofa widok).
3. Wybór działki: klik na mapie, wpisanie identyfikatora lub `Ctrl` (⌘ na Macu) + LPM i przeciągnięcie ramki. Klik i wyszukiwanie po identyfikatorze korzystają z API Vedry i zapamiętują kontury już znalezionych działek w obrębie bieżącej sesji. Tryb ramki przełącza się na górnym pasku:
   - **Zwykły wybór** — ramka = dokładnie zaznaczony prostokąt (własny obszar, max 5000 ha).
   - **Inteligentny wybór** (domyślny) — zaznaczane są wszystkie działki z ramki (`findParcelsInArea`: siatka punktów co ≥12 m, limit 150 działek / 300 zapytań). Działka trafia do wyboru tylko, gdy **co najmniej 50% jej powierzchni** leży w ramce (`MIN_INSIDE_SHARE` w `services/parcelApi.ts`) — pola tylko zahaczone krawędzią są pomijane. Gdy w ramce nie ma działki albo ULDK nie odpowiada — używany jest sam prostokąt.
   - Znalezione działki są **łączone w jeden kontur** (`utils/union.ts`: usuwanie wspólnych krawędzi, sklejanie wierzchołków z tolerancją ~0,2 m, obsługa styków typu „T”, dziury). Działki rozdzielone drogą/rowem dają kilka części — luki nie są zamalowywane, bo to nie jest ziemia użytkownika.
4. **Potwierdź działkę** → uruchamia analizę. Zmiana uprawy lub daty wykorzystuje wynik z pamięci aplikacji lub uruchamia nowe zadanie.
5. **Generuj Raport PDF** otwiera `/report`. Analiza backendowa udostępnia plik przez **Pobierz PDF**, a raport demonstracyjny korzysta z dialogu drukowania przeglądarki.

Granice województw: `public/data/wojewodztwa.geojson` (jeśli plik istnieje), w przeciwnym razie CDN jsDelivr z repozytorium `ppatrzyk/polska-geojson` (MIT). Nazwy pól w GeoJSON są wykrywane automatycznie (`nazwa`, `name`, `JPT_NAZWA_`…). Chcesz pracować offline — wrzuć plik do `public/data/`.

## Architektura

```
src/
  app/                 App.tsx (routing), providers.tsx (React Query + Router)
  pages/               LandingPage (/), MapPage (/map: mapa + panel), ReportPage (/report)
  features/analysis/   cała logika „analizy działki”
    store.ts             Zustand: działka + uprawy + data
    hooks/               useAnalysis (React Query), useParcelSelect (klik, identyfikator, ramka)
    components/          CropSelect, DateField, MoistureCard, RecommendationsCard,
                         BasisCard (źródła/ograniczenia), AnalysisProgress, ParcelMap, AnalysisPanel
  components/          współdzielone, bez logiki biznesowej
    layout/ map/ charts/ ui/
  services/            warstwa danych (jedyne miejsce rozmów z siecią)
    analysisApi.ts       uruchamianie zadania, odczyt postępu i adres PDF
    mockAnalysis.ts      deterministyczne dane demo
    parcelApi.ts         kontury i pamięć sesji, API Vedry dla pojedynczej działki
  types/               backendReport.ts (walidacja Zod), analysis.ts (model demo), parcel.ts
  constants/           pl.ts (wszystkie teksty), crops.ts, poland.ts
  utils/               geo, format, rng, validation
```

Komponenty korzystają z API przez `services/` i hooki. `types/backendReport.ts` waliduje pola raportu wykorzystywane przez interfejs.

## Podłączenie backendu

Uruchom backend z tego samego drzewa repozytorium na `127.0.0.1:8000` zgodnie z [instrukcją uruchomienia](../README.md#uruchomienie-lokalne). Vite domyślnie przekazuje żądania `/api` na ten adres. Do lokalnej próby z `GEO_PROVIDER=fixtures` wybierz zapisaną działkę, np. `040704_2.0012.63/1` z datą `2023-05-31`. Do hostingu ustaw `VITE_API_URL` na publiczny adres zakończony `/api` lub skonfiguruj reverse proxy.

Dla jednej potwierdzonej działki ewidencyjnej frontend przesyła `parcel_id`, `crop_code` i `analysis_date` do `POST /api/analyses`. Po przyjęciu zadania odczytuje jego stan przez `GET /api/analyses/{analysis_id}` co dwie sekundy. Po zakończeniu używa odebranego raportu i udostępnia plik z `GET /api/analyses/{analysis_id}/report.pdf`. Każda wybrana kategoria uprawy otrzymuje osobny raport. Przypisanie opcji formularza do kategorii backendu znajduje się w `src/constants/crops.ts`.

Grupy działek, własne obszary i zastępcze obrysy demo korzystają z jawnie oznaczonych danych demonstracyjnych. `VITE_USE_MOCK=true` uruchamia tryb demo dla każdego wyboru. Błąd analizy działki ewidencyjnej jest widoczny w panelu i można ponowić próbę.

## Co jest wymagane przez ZT, a gdzie to jest w UI

| Wymaganie | Gdzie |
|---|---|
| ID działki lub punkt na mapie | `ParcelMap` + `useParcelSelect` (API Vedry), `AreaSelect` (Ctrl + przeciągnięcie) |
| Potwierdzenie przed obliczeniem | `AnalysisPanel` (`store.confirmed`) |
| Wybór uprawy | `CropSelect` |
| Dowolna data z ostatnich 10 lat | `DateField` |
| Ocena bieżąca i historia | `BackendReportCards`; w demo `MoistureCard` |
| Rekomendacje, źródła i ograniczenia | `BackendReportCards`; w demo `RecommendationsCard` i `BasisCard` |
| Raport do zapisu / wydruku | `ReportPage` udostępnia PDF z backendu lub wydruk demo |
| Działa na telefonie | responsywny CSS |

## Znane ograniczenia (TODO)

- Granice województw ładowane z CDN w przeglądarce — nie mogłem ich zweryfikować w środowisku budowy (brak sieci). Jeśli nazwy się nie wyświetlą poprawnie, sprawdź pola w GeoJSON (`services/regionsApi.ts → NAME_KEYS`). Uproszczony kontur Polski w `constants/poland.ts` to tylko zapas na czas ładowania.
- Tryb demo: wartości są losowe (deterministyczne), widoczny baner „dane demonstracyjne”.
- Inteligentne zaznaczenie ramką używa bezpośrednich zapytań do ULDK, aby korzystać z dotychczasowej siatki punktów. W razie niedostępności rejestru obowiązują komunikaty i tryb demonstracyjny.
- Brak testów automatycznych (do dodania: Vitest dla `utils/` i `services/mockAnalysis`).

## Licencje danych / komponentów

- React, React DOM, React Router DOM, TanStack Query, Zustand i Zod (MIT).
- Leaflet (BSD-2-Clause) i React Leaflet (Hippocratic-2.1).
- TypeScript (Apache-2.0), Vite, wtyczka React i deklaracje typów (MIT).
- Kafelki Esri World Imagery i OpenTopoMap są pobierane na bieżąco. Mapa wyświetla atrybucję wybranego podkładu.
- Źródła danych analitycznych i ich warunki widnieją w `data_sources` w raporcie API oraz w [dokumentacji backendu](../backend/README.md#6-dane-zakresy-i-pochodzenie).
