# Bezpieczeństwo Vedry

## Dane i dostęp

Prototyp przyjmuje identyfikator działki lub współrzędne, wybraną uprawę i datę. Działanie
nie wymaga konta, nazwiska, adresu e-mail ani informacji o właścicielu. Zapisy obejmują
geometrię działki, raport, postęp oraz dane potrzebne do odtworzenia PDF. Identyfikator
raportu pozwala go odczytać. Osoba mająca taki odsyłacz może pobrać dane raportu.

Do uruchomienia lokalnego wystarczy adres pętli zwrotnej. W wersji dostępnej przez sieć
warstwa wdrożeniowa powinna zapewnić HTTPS, ograniczenia ruchu oraz dostępu do plików
raportów zgodne z zamierzonym sposobem ich udostępniania. Przed udostępnieniem testowych
raportów należy sprawdzić ich zakres danych i odsyłacze do źródeł.

## Zabezpieczenia w kodzie

- FastAPI i Pydantic kontrolują format żądań. Backend sprawdza granice współrzędnych,
  uprawę oraz zakres daty, a błędy zwraca po polsku.
- Wspólny klient sieciowy sprawdza dozwolone hosty. Adresy usług ustala kod i konfiguracja.
  Szablon PDF używa osadzonych obrazów i lokalnego arkusza stylów. Jinja2 stosuje
  ucieczkę znaków HTML w danych przekazywanych do szablonu.
- Aplikacja ustawia `X-Content-Type-Options: nosniff` i zezwala na CORS z podanych adresów
  frontendu. CORS określa politykę przeglądarki. Dostęp do raportów zależy od znajomości identyfikatora.
- Operacje bazodanowe przekazują wartości przez parametry SQL. Nazwa pliku PDF używa skrótu
  identyfikatora, a zapis pliku następuje przez atomową zamianę pliku tymczasowego.
- Obraz kontenera uruchamia aplikację jako `nobody`. Stan raportów i pamięć podręczna
  mogą mieć oddzielne wolumeny i kontrolę dostępu systemu plików.

## Konfiguracja publicznego uruchomienia

Ostatni etap wdrożenia powinien ograniczyć rozmiar żądania i liczbę kosztownych wywołań,
włączyć rotację logów oraz utworzyć kopie SQLite i plików PDF. Publiczny adres frontendu
powinien znaleźć się w `CORS_ORIGINS`. Dla dłuższego użytkowania należy ustalić czas
przechowywania raportów i możliwość odwołania udostępnionego odsyłacza.
