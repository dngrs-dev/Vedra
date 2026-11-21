# Walidacja KBW

Uprawa porównawcza to **zboża jare**. Klasa gleby pochodzi z zapisu części A dla danej działki i daty.
Porównanie korzysta z dobowych pomiarów stacji IMGW-PIB oraz tych samych obliczeń KBW co aplikacja.
Podana różnica to KBW Vedry minus KBW MRiRW. Wynik z obwieszczenia dotyczy gminy. Vedra wykorzystuje komórkę modelu lub pomiary stacji przypisanej do działki.
Ocena Vedry używa progów z 2019 r. Dla 2018 r. zgodność werdyktów ma charakter orientacyjny ze względu na wcześniejsze przepisy.
[Progi dla 2018 r.](https://eli.gov.pl/eli/DU/2017/732/ogl), [progi od 2019 r.](https://eli.gov.pl/eli/DU/2019/739/ogl)

## Odtworzenie lokalne

Uruchom polecenia w katalogu `backend` po zainstalowaniu zależności aplikacji i pobraniu obu PDF-ów z odsyłaczy poniżej.
Skrypt porównawczy korzysta domyślnie z zapisów części A w `tests/fixtures/geo`.

```sh
python -m pip install pypdf pyarrow
python -m scripts.b.build_kbw_official --pdf-2018 2018-13.pdf --pdf-2023 2023-25.pdf
python -m scripts.b.backtest --imgw-only
```

## 2018-07-10

[Obwieszczenie MRiRW](https://edziennik.minrol.gov.pl/DUM_MRIRW/2018/13/akt.pdf)

| Działka | Gmina | Gleba | KBW MRiRW, mm | Werdykt MRiRW | KBW Vedry, mm | KBW FAO-56, mm | Werdykt Vedry |
| --- | --- | --- | ---: | --- | ---: | ---: | --- |
| 040704_2.0012.63/1 | Inowrocław | III | -212,0 | brak suszy | -216,4 | — | susza |
| 060406_2.0136.AR_5.1077/6 | Trzeszczany | III | -140,0 | brak suszy | -188,4 | — | brak suszy |
| 100206_2.0008.273/23 | Kutno | II | -170,0 | brak suszy | -182,9 | — | susza |
| 121405_5.0016.480/3 | Proszowice | III | -111,0 | brak suszy | -101,5 | — | brak suszy |
| 142513_2.0039.102 | Zakrzew | II | -159,0 | brak suszy | -149,6 | — | brak suszy |
| 200605_5.0002.143 | Stawiski | I | -184,0 | susza | -204,5 | — | susza |
| 280803_2.0028.78/40 | Kętrzyn | IV | -192,0 | brak suszy | -174,1 | — | brak suszy |
| 303005_5.0323.25/7 | Września | I | -224,0 | susza | -254,1 | — | susza |

- Doroszewski–Górski, n = 8, średni błąd bezwzględny 19,1 mm, średnia różnica -10,0 mm.
- FAO-56, n = 0. Brak podstaw do obliczenia błędu.
- Zgodne werdykty, 6 z 8 porównywalnych przypadków.

## 2023-05-31

[Obwieszczenie MRiRW](https://edziennik.minrol.gov.pl/DUM_MRIRW/2023/25/oryginal/akt.pdf)

| Działka | Gmina | Gleba | KBW MRiRW, mm | Werdykt MRiRW | KBW Vedry, mm | KBW FAO-56, mm | Werdykt Vedry |
| --- | --- | --- | ---: | --- | ---: | ---: | --- |
| 040704_2.0012.63/1 | Inowrocław | III | -140,0 | brak suszy | -128,2 | — | brak suszy |
| 060406_2.0136.AR_5.1077/6 | Trzeszczany | III | -119,0 | brak suszy | -58,4 | — | brak suszy |
| 100206_2.0008.273/23 | Kutno | II | -114,0 | brak suszy | -135,8 | — | brak suszy |
| 121405_5.0016.480/3 | Proszowice | III | -20,0 | brak suszy | -29,7 | — | brak suszy |
| 142513_2.0039.102 | Zakrzew | II | -71,0 | brak suszy | -96,0 | — | brak suszy |
| 200605_5.0002.143 | Stawiski | I | -119,0 | brak suszy | -146,6 | — | susza |
| 280803_2.0028.78/40 | Kętrzyn | IV | -152,0 | brak suszy | -166,8 | — | brak suszy |
| 303005_5.0323.25/7 | Września | I | -143,0 | susza | -114,9 | — | brak suszy |

- Doroszewski–Górski, n = 8, średni błąd bezwzględny 24,9 mm, średnia różnica 0,2 mm.
- FAO-56, n = 0. Brak podstaw do obliczenia błędu.
- Zgodne werdykty, 6 z 8 porównywalnych przypadków.
