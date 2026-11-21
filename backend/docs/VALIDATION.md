# Walidacja KBW

Uprawa porównawcza to **zboża jare**. Klasa gleby pochodzi z zapisu części A dla danej działki i daty.
Meteorologiczna część porównania korzysta z tego samego archiwum Open-Meteo i obliczeń KBW co aplikacja.
Podana różnica to KBW Vedry minus KBW MRiRW. Wynik z obwieszczenia dotyczy gminy, a wynik Vedry punktu w siatce meteorologicznej przypisanego do działki.
Ocena Vedry używa progów z 2019 r. Dla 2018 r. zgodność werdyktów ma charakter orientacyjny ze względu na wcześniejsze przepisy.
[Progi dla 2018 r.](https://eli.gov.pl/eli/DU/2017/732/ogl), [progi od 2019 r.](https://eli.gov.pl/eli/DU/2019/739/ogl)

## Odtworzenie lokalne

Uruchom polecenia w katalogu `backend` po zainstalowaniu zależności aplikacji i pobraniu obu PDF-ów z odsyłaczy poniżej.
Skrypt porównawczy korzysta domyślnie z zapisów części A w `tests/fixtures/geo`.

```sh
python -m pip install pypdf pyarrow
python -m scripts.b.build_kbw_official --pdf-2018 2018-13.pdf --pdf-2023 2023-25.pdf
python -m scripts.b.backtest
```

**Wynik niepełny.** Archiwum Open-Meteo zwróciło HTTP 429 z powodu dziennego limitu zapytań. Tabele pokazują odczytane wartości urzędowe i dostępność porównania.

## 2018-07-10

[Obwieszczenie MRiRW](https://edziennik.minrol.gov.pl/DUM_MRIRW/2018/13/akt.pdf)

| Działka | Gmina | Gleba | KBW MRiRW, mm | Werdykt MRiRW | KBW Vedry, mm | KBW FAO-56, mm | Werdykt Vedry |
| --- | --- | --- | ---: | --- | ---: | ---: | --- |
| 040704_2.0012.63/1 | Inowrocław | III | -212,0 | brak suszy | — | — | brak oceny |
| 060406_2.0136.AR_5.1077/6 | Trzeszczany | III | -140,0 | brak suszy | — | — | brak oceny |
| 100206_2.0008.273/23 | Kutno | II | -170,0 | brak suszy | — | — | brak oceny |
| 121405_5.0016.480/3 | Proszowice | II | -111,0 | brak suszy | — | — | brak oceny |
| 142513_2.0039.102 | Zakrzew | II | -159,0 | brak suszy | — | — | brak oceny |
| 200605_5.0002.143 | Stawiski | I | -184,0 | susza | — | — | brak oceny |
| 280803_2.0028.78/40 | Kętrzyn | IV | -192,0 | brak suszy | — | — | brak oceny |
| 303005_5.0323.25/7 | Września | I | -224,0 | susza | — | — | brak oceny |

- Doroszewski–Górski, n = 0. Brak podstaw do obliczenia błędu.
- FAO-56, n = 0. Brak podstaw do obliczenia błędu.
- Brak porównywalnych rozstrzygnięć susza / brak suszy.

## 2023-05-31

[Obwieszczenie MRiRW](https://edziennik.minrol.gov.pl/DUM_MRIRW/2023/25/oryginal/akt.pdf)

| Działka | Gmina | Gleba | KBW MRiRW, mm | Werdykt MRiRW | KBW Vedry, mm | KBW FAO-56, mm | Werdykt Vedry |
| --- | --- | --- | ---: | --- | ---: | ---: | --- |
| 040704_2.0012.63/1 | Inowrocław | III | -140,0 | brak suszy | — | — | brak oceny |
| 060406_2.0136.AR_5.1077/6 | Trzeszczany | III | -119,0 | brak suszy | — | — | brak oceny |
| 100206_2.0008.273/23 | Kutno | II | -114,0 | brak suszy | — | — | brak oceny |
| 121405_5.0016.480/3 | Proszowice | II | -20,0 | brak suszy | — | — | brak oceny |
| 142513_2.0039.102 | Zakrzew | II | -71,0 | brak suszy | — | — | brak oceny |
| 200605_5.0002.143 | Stawiski | I | -119,0 | brak suszy | — | — | brak oceny |
| 280803_2.0028.78/40 | Kętrzyn | IV | -152,0 | brak suszy | — | — | brak oceny |
| 303005_5.0323.25/7 | Września | I | -143,0 | susza | — | — | brak oceny |

- Doroszewski–Górski, n = 0. Brak podstaw do obliczenia błędu.
- FAO-56, n = 0. Brak podstaw do obliczenia błędu.
- Brak porównywalnych rozstrzygnięć susza / brak suszy.
