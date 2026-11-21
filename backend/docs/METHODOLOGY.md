# Metodyka analizy

## Dane pogodowe

Seria Open-Meteo ERA5-Seamless w aplikacji zaczyna się 1 stycznia 1991 r. Backend zachowuje
kompletne dane w komórce 0,1° i przy późniejszej analizie pobiera tylko brakujące dni.
Wilgotność gleby pochodzi z gotowych średnich dobowych Open-Meteo dla polskiej strefy
czasowej. Przy ograniczeniu HTTP 429 backend respektuje wskazany czas ponowienia
i nadal wykorzystuje dostępne dni z pamięci podręcznej. Długość dnia i usłonecznienie są przeliczane
z sekund na godziny. Bieżący model pogodowy uzupełnia dni oczekujące na publikację
archiwum, z wyjątkiem wilgotności gleby. Obliczenia używają wyłącznie danych do daty
analizy. Prognoza na kolejne dni jest osobnym wejściem dla bieżącej oceny nawadniania.
[Archiwum Open-Meteo](https://open-meteo.com/en/docs/historical-weather-api),
[API prognoz](https://open-meteo.com/en/docs).

Gdy dane modelu nie wystarczają do obliczenia KBW, aplikacja może użyć dobowych pomiarów
opadu, średniej temperatury i usłonecznienia IMGW-PIB. Wybiera najbliższą stację z kompletem
pomiarów dla najnowszego zakończonego okresu. Gdy w lokalnym archiwum brakuje tego okresu,
aplikacja korzysta z najbliższej stacji z najnowszymi dostępnymi pomiarami do daty analizy
i nadal sprawdza, które okresy historyczne da się ocenić. Wybór lokalizacji opiera się na
kodzie stacji i aktualnej metryce IMGW-PIB. Raport pokazuje nazwę stacji i jej przybliżoną
odległość od działki. Różnice lokalne, zmiany położenia stacji i luki w obserwacjach wpływają
na wynik. Jedna stacja dostarcza całą zastępczą serię dla KBW i historii. Archiwum nie zawiera
wilgotności gleby ani ET₀. Braki pomiaru pozostają puste, a oficjalny status braku zjawiska
oznacza zerowy opad lub zerowe usłonecznienie.
[Dane dobowe IMGW-PIB](https://danepubliczne.imgw.pl/data/dane_pomiarowo_obserwacyjne/dane_meteorologiczne/dobowe/synop/),
[metadane stacji](https://danepubliczne.imgw.pl/api/data/meteo),
[warunki wykorzystania](https://danepubliczne.imgw.pl/pl/regulations).

## Klimatyczny bilans wodny

Vedra odejmuje szacowaną ewapotranspirację potencjalną od sumy opadów. Wynik dla ostatniego
zakończonego okresu sześciodekadowego porównuje z progiem dla uprawy i kategorii gleby.
Susza w tym okresie wymaga wartości niższej od progu. Znaki `x` i `-` oznaczają odpowiednio
brak progu dla uprawy w danym okresie i niewskazaną uprawę na danej kategorii gleby.
[Dz.U. 2019 poz. 739](https://eli.gov.pl/api/acts/DU/2019/739/text.pdf),
[art. 3 ust. 2 pkt 10 ustawy, Dz.U. 2019 poz. 477](https://eli.gov.pl/api/acts/DU/2019/477/text/I/D20190477.pdf).

Miesięczne ETP Doroszewskiego–Górskiego w mm wynosi

```text
ETP = -89,6 + 0,0621 · t² + 0,00448 · h^(1,66) + 9,1 · f
```

W równaniu `t` to średnia temperatura w °C, `h` to suma godzin usłonecznienia,
a `f` to reprezentatywna długość dnia w godzinach. Vedra przyjmuje 15. dzień miesiąca zgodnie
z tabelą FAO-56 i oblicza długość dnia astronomicznie, jeśli brakuje tej wartości lub
dzień wypada po końcu zakresu. Dla niepełnego miesiąca średnia temperatura i dzienne
usłonecznienie dotyczą dotychczasowych dni, a całkowite usłonecznienie to oszacowanie
z tej średniej i liczby dni miesiąca. Miesięczne ETP rozkłada się proporcjonalnie do liczby
dni przypadających na okres sześciodekadowy. Założenie wprowadza niepewność przy zmianach
pogody w trakcie miesiąca. Brak wymaganych wartości w serii uniemożliwia oszacowanie ETP.
[IUNG, wzory 1 i 2](https://iung.pl/images/wyd/Susza%20rolnicza%20w%20Polsce.pdf),
[FAO-56, rozdział 3](https://www.fao.org/4/x0490e/x0490e07.htm).

Równoległy wariant korzysta z sumy dziennego ET0 FAO-56. Wynik graniczny oznacza, że próg
mieści się między obydwoma wariantami lub jest równy głównemu oszacowaniu. Rozpiętość
pokazuje wrażliwość na metodę. SMSR IUNG stosuje własne dane i metody estymacji,
a obwieszczenie podaje wartość dla gminy.
[Opis SMSR](https://susza.iung.pulawy.pl/system/), [walidacja KBW](VALIDATION.md).

## Sygnały, przyczyny i podatność historyczna

- **SPI-1 i SPI-3** używają pełnych miesięcy. Dla miesiąca kończącego okno dopasowywany jest
  odrębny rozkład gamma z bazy 1991–2020, z uwzględnieniem częstości miesięcy bez opadów.
  Krótsza baza daje wynik orientacyjny z podaną liczebnością.
  [McKee i in. (1993)](https://www.droughtmanagement.info/literature/AMS_Relationship_Drought_Frequency_Duration_Time_Scales_1993.pdf),
  [podręcznik WMO 1090](https://www.droughtmanagement.info/literature/WMO_standardized_precipitation_index_user_guide_en_2012.pdf).
- **Wilgotność gleby** wykorzystuje ostatnią dostępną wartość przed lub w dniu analizy.
  Percentyl każdej warstwy wynika z porównania z tym samym dniem kalendarzowym w poprzednich
  dziesięciu latach. Jako orientacyjną granicę niskiej wilgotności przyjęto 20. percentyl
  z produktu referencyjnego, stosując go tutaj dla dobowych wartości warstwy.
  [European Climate Data Explorer](https://confluence.ecmwf.int/spaces/CKB/pages/453680707).
- **VCI** odnosi bieżącą medianę NDVI działki do minimum i maksimum median w porównywalnych
  oknach wcześniejszych lat. Terminy wrażliwości na niedobór zależą od uprawy. Aplikacja
  przyjmuje okresy KBW jako przybliżenie, gdy brakuje dat siewu, wschodów i zbioru.
  PolSA opisuje wpływ fenologii jakościowo. Zakresy poniżej 40 i powyżej 60 pochodzą
  z eksperymentalnej interpretacji NOAA i pełnią rolę orientacyjnych wartości.
  [FAO VCI](https://www.fao.org/giews/earthobservation/asis/index_2.jsp?lang=en),
  [PolSA §6.3.4](https://polsa.gov.pl/wp-content/themes/polsa/files/Podrecznik.pdf#page=293),
  [NOAA STAR](https://www.star.nesdis.noaa.gov/smcd/emb/vci/VH/vh_browseByCountry_province.php).
- **CDI** opisuje sytuację regionalną. Jest wskaźnikiem złożonym i zawiera m.in. informacje
  o opadach, wilgotności gleby i roślinności.
  [Copernicus EDO](https://drought.emergency.copernicus.eu/data/factsheets/factsheet_combinedDroughtIndicator_v4.pdf).

Pewność ma charakter jakościowy. Aplikacja sprawdza, czy KBW wspierają sygnały wilgotności
głębszej warstwy i satelitarnej kondycji upraw. ERA5 i ERA5-Land korzystają ze wspólnych
danych wymuszających, a SPI wykorzystuje te same opady co KBW. Niedobór opadów i
podwyższony popyt atmosferyczny wyprzedzają w rankingu wpływ gleby, odpływu, otoczenia
i wymagań uprawy. Wnioski przestrzenne zależą od rozdzielczości i pokrycia danych.
[Konfiguracja progów](../config/thresholds.yaml), [opis reguł części B](PART_B_ANALYTICS_PRODUCT.md).

Historia przypisuje okres KBW do jego miesiąca końcowego. Udział okresów suszy jest liczony
wśród okresów z werdyktem liczbowym. Porównanie szczytów NDVI w latach z suszą i bez
suszy wykorzystuje zakończone sezony kwiecień–sierpień, z podaniem liczebności obu grup.
Poza okresem od 21 marca do 30 września raport pokazuje osobny wynik poza sezonem,
obserwacje opisowe i dostępną historię. Aktualne przyczyny suszy i dawka nawadniania
w tym trybie nie są wyznaczane.
[Okresy z załącznika do rozporządzenia](https://eli.gov.pl/api/acts/DU/2019/739/text.pdf).

## Zalecenia i nawadnianie

Reguły przechodzą od retencji krajobrazowej przez glebową i agrotechnikę do nawadniania.
Zalecenia wynikają z przesłanek, takich jak oszacowany niedobór, okresy suszy w historii,
podatność gleby albo cechy przestrzenne działki. Lokalizacje i objętości pochodzą z danych
części A. Porównanie zmiany materii organicznej oblicza różnicę dwóch estymacji Saxtona–Rawlsa
dla tej samej tekstury. Przyrost węgla przyjęto z pracy Minasny'ego i McBratneya,
a konwersję z węgla do materii organicznej opisuje Pribyl. Brak pełnego profilu lub zmiennych
wejściowych pozostawia scenariusz bez wartości liczbowej.
[Saxton i Rawls](https://doi.org/10.2136/sssaj2005.0117),
[Minasny i McBratney](https://doi.org/10.1111/ejss.12475),
[Pribyl](https://doi.org/10.1016/j.geoderma.2010.02.003).

Dobowy model nawadniania integruje właściwości gleby do głębokości korzeni. Rozpoczyna
od wilgotności ERA5-Land dla tego profilu i uwzględnia dzienne opady i ET0. Korzysta
z parametrów uprawy w pełnym rozwoju, ponieważ rzeczywiste terminy poszczególnych faz
najczęściej są nieznane. Krańce zakresu parametrów uprawy dają alternatywne dawki netto.
Model pomija wcześniejsze nawadnianie, podsiąk i odpływ. W sezonie dla bieżącej daty
prognoza może wskazać dzień osiągnięcia RAW. Dawka netto uzupełnia oszacowany ubytek
wody w strefie korzeniowej.
[FAO-56, rozdział 8](https://www.fao.org/4/x0490e/x0490e0e.htm),
[parametry upraw](../config/crops.yaml).
