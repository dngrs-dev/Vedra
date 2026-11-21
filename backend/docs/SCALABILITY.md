# Skalowanie Vedry

## Praca prototypu

API uruchamia zadanie na pojedynczej instancji i od razu zwraca identyfikator. Żądanie
odczytu postępu korzysta z pamięci procesu. Po ukończeniu raport trafia do SQLite i można
go odczytać po restarcie. Renderowanie PDF następuje przy pierwszym pobraniu, a późniejsze
pobrania korzystają z zapisanego pliku.

Pogoda i źródła geo są pobierane równolegle po ustaleniu działki. Kompletne archiwum pogody
jest buforowane dla komórki 0,1°. Okres opóźnienia publikacji uzupełnia bieżący model
pogodowy. Lokalne archiwum IMGW-PIB może dostarczyć dane potrzebne do KBW przy niedostępności
modelu. Część A używa oddzielnych kluczy pamięci podręcznej i odczytuje przygotowane profile
SoilGrids, gdy są dostępne. Każde zadanie ma limit 30 s zgodny z celem prototypu. Po
wyszukaniu działki aplikacja dopasowuje czas zbierania danych geo do pozostałego budżetu
zadania i rezerwuje czas na obliczenia. Częściowe źródła opisuje się w raporcie.
[Metodyka](METHODOLOGY.md), [kontrakty](CONTRACTS.md).

W pomiarze lokalnym zadania korzystały z rzeczywistego źródła działek i gleb oraz ścieżki
braku pogody po wyczerpaniu limitu Open-Meteo. Wyniki dotyczą tego wariantu i pojedynczych
wywołań. Test nie obejmował obciążenia równoległego, pełnych danych meteorologicznych ani
czasu pierwszego pobrania PDF.
[Wyniki pomiarów](PART_B_ANALYTICS_PRODUCT.md#cp4--validation-and-robustness--0700).

## Obsługa większego ruchu

1. Wspólna kolejka i trwały rejestr zadań umożliwią uruchamianie kilku procesów. Kolejka
   powinna ograniczać liczbę analiz w toku i deduplikować jednoczesne pobrania tej samej komórki.
   Operacje na źródłach powinny uwzględniać limity dostawców oraz czas ponowienia z odpowiedzi.
2. Oddzielne procesy mogą pobierać i przetwarzać rastry, a oddzielne renderować PDF. Wspólna
   baza raportów i magazyn plików umożliwią odczyt niezależnie od instancji API.
3. Dane historyczne można współdzielić, przechowując odczyt według wersji źródła i zakresu.
   Dołączanie kolejnych dni może postępować zgodnie z publikacją dostawcy, z ponowną próbą
   po awarii. Aktualizacja warstw terenu i gleby zależy od wersji zbioru i licencji.
4. Pomiar dla działek o różnej powierzchni powinien raportować medianę i 95. percentyl czasu,
   udział brakujących źródeł, odsetek trafień w pamięci podręcznej oraz liczbę odpowiedzi
   429. Szybkość pod obciążeniem zależy od rozkładu danych, limitów zewnętrznych i kolejki.

Koszty utrzymania będą wynikały z obliczeń, transferu rastrów, przechowywania źródeł, kopii
zapasowych oraz limitów API. Bezpłatny wariant Open-Meteo jest przeznaczony do zastosowań
niekomercyjnych. Dla większego ruchu można porównać płatną usługę z samodzielnym
utrzymaniem infrastruktury i archiwum według warunków dostawcy danych.
[Warunki Open-Meteo](https://open-meteo.com/en/terms).
