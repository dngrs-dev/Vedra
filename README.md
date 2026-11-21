# Vedra

Vedra pomaga rolnikowi ocenić niedobór wody na działce i zdecydować, jak zwiększyć retencję
oraz ograniczyć straty wilgoci. Prototyp powstał na HackNation 2026 dla zadania KOWR
„Zatrzymaj wodę, chroń plony”.

Wybierz jedną działkę ewidencyjną na mapie lub wpisz jej identyfikator. Po potwierdzeniu możesz
zmienić uprawę i wybrać datę z ostatnich 10 lat. Raport zawiera ocenę warunków wodnych,
historyczną podatność na niedobór oraz zalecenia uzasadnione dostępnymi danymi. Źródła, daty
i ograniczenia znajdziesz w raporcie, który możesz pobrać jako PDF i wydrukować.

## Uruchomienie lokalne

Polecenia wykonaj z katalogu głównego repozytorium na gałęzi `main`. Potrzebujesz Dockera
oraz Node.js z npm. Obraz backendu zawiera biblioteki potrzebne do generowania PDF.

W pierwszym terminalu uruchom backend z dostępem do rzeczywistych źródeł danych.

```powershell
docker build -t vedra-backend backend
docker run --rm -e GEO_PROVIDER=real -e DB_PATH=/app/state/vedra.sqlite -v vedra-state:/app/state -p 127.0.0.1:8000:8000 vedra-backend
```

Bez Dockera skorzystaj z instrukcji [uruchomienia w Pythonie](backend/README.md#5-uruchomienie-lokalne)
i ustaw `GEO_PROVIDER` na `real`.

W drugim terminalu uruchom frontend.

```powershell
cd frontend
npm.cmd install
$env:VITE_API_URL = '/api'
$env:VITE_USE_MOCK = 'false'
npm.cmd run dev
```

Otwórz [Vedrę](http://localhost:5173) w przeglądarce. Na Linuxie i macOS użyj `npm` zamiast
`npm.cmd` i ustaw zmienne z powyższymi wartościami przez `export`.

### Powtarzalny przykład

Aby sprawdzić przepływ z zapisanymi danymi przestrzennymi, uruchom backend z `GEO_PROVIDER=fixtures`.
Wpisz `040704_2.0012.63/1`, potwierdź działkę i wybierz jęczmień jary oraz `2023-05-31`.
Po zakończeniu analizy wybierz **Generuj Raport PDF**, a następnie **Pobierz PDF**.
[Przykładowe raporty](backend/README.md#przykładowe-raporty-pdf).

Tryb `real` wyszukuje działki w krajowej ewidencji. Dostępność poszczególnych wskaźników zależy
od daty, pokrycia danymi oraz dostępności usług źródłowych. KBW ma sezonowy okres oceny.
Wybór grup działek i obszarów rysowanych na mapie pokazuje oznaczone wyniki demonstracyjne.

## Dokumentacja techniczna

Frontend React prezentuje mapę i wyniki. Backend FastAPI pobiera dane, wykonuje analizę
na żądanie, zapisuje wyniki w SQLite i generuje PDF. Archiwum pomiarów IMGW-PIB jest dołączone
jako zapasowe źródło pogody. Podkład mapy korzysta z usług dostępnych przez Internet.

- [Backend: uruchomienie, źródła i zakresy danych, licencje, ograniczenia](backend/README.md)
- [Frontend: obsługa, konfiguracja i komponenty](frontend/README.md)
- [Metodyka obliczeń i rekomendacji](backend/docs/METHODOLOGY.md)
- [Walidacja na danych referencyjnych MRiRW](backend/docs/VALIDATION.md)
- [Użycie narzędzi AI](backend/docs/AI_USAGE.md)
