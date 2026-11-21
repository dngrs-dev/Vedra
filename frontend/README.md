# KOWR HackNation 2026 — Cyfrowy Asystent Gospodarowania Wodą (frontend)

Aplikacja webowa dla rolników: wskaż działkę (ID lub klik na mapie), wybierz uprawę i datę → ocena wilgotności i ryzyka suszy (10 lat), rekomendacje retencyjne / agrotechniczne / nawodnieniowe, raport PDF.

**Stack:** Vite · React 18 · TypeScript (strict) · react-leaflet · TanStack Query · Zustand · Zod · React Router (BrowserRouter).

## Uruchomienie

```bash
npm install
cp .env.example .env     # domyślnie VITE_USE_MOCK=true (dane demonstracyjne)
npm run dev              # http://localhost:5173
npm run build            # typecheck + produkcyjny build do dist/
```

Build to zwykłe pliki statyczne (`dist/`). Adresy: `/` (strona główna), `/map` (mapa), `/report` (raport). Hosting musi zwracać `index.html` dla każdej ścieżki — w projekcie są `vercel.json` (Vercel) i `public/_redirects` (Netlify).

## Przepływ użytkownika

1. `/` — krótka strona główna (przycisk **Zobacz mapę**).
2. `/map` — mapa Polski z liniami województw. Klik w województwo → mapa przybliża się, jego etykieta znika (przycisk „← Cała Polska” cofa widok).
3. Wybór działki: klik w działkę (GUGiK ULDK) **lub** `Ctrl` (⌘ na Macu) + LPM + przeciągnięcie ramki. Tryb ramki przełącza się na górnym pasku:
   - **Zwykły wybór** — ramka = dokładnie zaznaczony prostokąt (własny obszar, max 5000 ha).
   - **Inteligentny wybór** (domyślny) — zaznaczane są wszystkie działki z ramki (`findParcelsInArea`: siatka punktów co ≥12 m, limit 150 działek / 300 zapytań). Działka trafia do wyboru tylko, gdy **co najmniej 50% jej powierzchni** leży w ramce (`MIN_INSIDE_SHARE` w `services/parcelApi.ts`) — pola tylko zahaczone krawędzią są pomijane. Gdy w ramce nie ma działki albo ULDK nie odpowiada — używany jest sam prostokąt.
   - Znalezione działki są **łączone w jeden kontur** (`utils/union.ts`: usuwanie wspólnych krawędzi, sklejanie wierzchołków z tolerancją ~0,2 m, obsługa styków typu „T”, dziury). Działki rozdzielone drogą/rowem dają kilka części — luki nie są zamalowywane, bo to nie jest ziemia użytkownika.
4. **Potwierdź działkę** → dopiero teraz startuje obliczenie (backend). Zmiana uprawy/daty po potwierdzeniu przelicza wynik.
5. **Generuj Raport PDF** → `/report`.

Granice województw: `public/data/wojewodztwa.geojson` (jeśli plik istnieje), w przeciwnym razie CDN jsDelivr z repozytorium `ppatrzyk/polska-geojson` (MIT). Nazwy pól w GeoJSON są wykrywane automatycznie (`nazwa`, `name`, `JPT_NAZWA_`…). Chcesz pracować offline — wrzuć plik do `public/data/`.

## Architektura

```
src/
  app/                 App.tsx (routing), providers.tsx (React Query + Router)
  pages/               LandingPage (/), MapPage (/map: mapa + panel), ReportPage (/report)
  features/analysis/   cała logika „analizy działki”
    store.ts             Zustand: działka + uprawy + data
    hooks/               useAnalysis (React Query), useParcelSelect (ULDK)
    components/          CropSelect, DateField, MoistureCard, RecommendationsCard,
                         BasisCard (źródła/ograniczenia), AnalysisProgress, ParcelMap, AnalysisPanel
  components/          współdzielone, bez logiki biznesowej
    layout/ map/ charts/ ui/
  services/            warstwa danych (jedyne miejsce rozmów z siecią)
    analysisApi.ts       analyze() — mock lub POST /analyze + walidacja zod
    mockAnalysis.ts      deterministyczne dane demo
    parcelApi.ts         GUGiK ULDK (kontur działki po ID / po kliknięciu)
  types/               analysis.ts (KONTRAKT z backendem, zod), parcel.ts
  constants/           pl.ts (wszystkie teksty), crops.ts, poland.ts
  utils/               geo, format, rng, validation
```

Zasady: komponenty nie wywołują `fetch` — tylko przez `services/` i hooki; teksty UI tylko w `constants/pl.ts`; kształt odpowiedzi backendu zdefiniowany raz (`types/analysis.ts`).

## Podłączenie backendu

1. W `.env`: `VITE_USE_MOCK=false`, `VITE_API_URL=https://twoj-backend/api`.
2. Backend implementuje `POST /analyze`:
   - **Request:** `{ parcelId, lat, lng, areaHa, geometry: [[lat,lng],…], isCustomArea, parcels: [{ id, geometry }], cropIds[], date: "YYYY-MM-DD" }` (`AnalysisRequest`). Przy wyborze grupowym `parcels` zawiera wszystkie działki z ramki, `outline` — ich połączony kontur (multipolygon `[[zewnętrzny, ...dziury], ...]`), `geometry` to sama ramka, `areaHa` to suma powierzchni. Dla `isCustomArea=true` backend używa wyłącznie `geometry` (id typu `OBSZAR_lat_lng` nie istnieje w ewidencji).
   - **Response:** JSON zgodny z `AnalysisSchema` w `src/types/analysis.ts` — odpowiedź jest walidowana, niezgodność = czytelny błąd w UI.
3. Nic więcej we froncie nie trzeba zmieniać.

## Co jest wymagane przez ZT, a gdzie to jest w UI

| Wymaganie | Gdzie |
|---|---|
| ID działki lub punkt na mapie | `ParcelMap` + `useParcelSelect` (ULDK), `AreaSelect` (Ctrl + przeciągnięcie) |
| Potwierdzenie przed obliczeniem | `AnalysisPanel` (`store.confirmed`) |
| Wybór uprawy | `CropSelect` |
| Dowolna data z ostatnich 10 lat | `DateField` |
| Ocena bieżąca + 10 lat | `MoistureCard` |
| Rekomendacje z uzasadnieniem | `RecommendationsCard` („Dlaczego?”) |
| Źródła, daty, ograniczenia, niepewność | `BasisCard`, `ConfidenceBadge`, raport |
| Brak danych komunikowany wprost | `Gauge` („Brak danych”), `limitations` |
| Raport do zapisu / wydruku | `ReportPage` → druk → PDF |
| Działa na telefonie | responsywny CSS |

## Znane ograniczenia (TODO)

- Granice województw ładowane z CDN w przeglądarce — nie mogłem ich zweryfikować w środowisku budowy (brak sieci). Jeśli nazwy się nie wyświetlą poprawnie, sprawdź pola w GeoJSON (`services/regionsApi.ts → NAME_KEYS`). Uproszczony kontur Polski w `constants/poland.ts` to tylko zapas na czas ładowania.
- Tryb demo: wartości są losowe (deterministyczne), widoczny baner „dane demonstracyjne”.
- Pasek postępu analizy działa na timerze — gdy backend zacznie raportować etapy, przekazać `step` do `AnalysisProgress`.
- ULDK bywa blokowany przez CORS — wtedy przy kliknięciu pokazywany jest kontur demo (z komunikatem); docelowo proxy przez backend.
- Brak testów automatycznych (do dodania: Vitest dla `utils/` i `services/mockAnalysis`).

## Licencje danych / komponentów

Leaflet (BSD-2), react-leaflet (Hippocratic-2.1), kafelki Esri World Imagery i OpenTopoMap — zgodnie z ich warunkami (atrybucja wyświetlana na mapie). Dane analityczne — patrz `sources` w odpowiedzi API.
