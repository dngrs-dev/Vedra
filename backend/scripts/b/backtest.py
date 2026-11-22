"""Compare parcel KBW with the MRiRW annexes for the Part A scenarios."""
from __future__ import annotations

import argparse
import asyncio
from datetime import date
from pathlib import Path
from statistics import mean

import pandas as pd

from app.analytics import crops, imgw_weather, kbw, periods, weather as weather_provider
from app.analytics.models import KbwResult
from app.config import CONFIG_DIR
from app.contracts.geo import GeoRequest, KbwSoilCategory
from app.contracts.parcel import Parcel
from app.core import http
from app.fakes.fixture_geo import FIXTURES_DIR, FixtureGeoProvider

BACKEND = CONFIG_DIR.parent
PARQUET = BACKEND / "data" / "b" / "kbw_official.parquet"
VALIDATION = BACKEND / "docs" / "VALIDATION.md"
# Spring cereals are the chosen validation crop and appear in both notice annexes.
DEFAULT_CROP = "spring_cereals"
LABELS = {
    "drought": "susza",
    "no_drought": "brak suszy",
    "soil_absent": "brak kategorii gleby",
    "not_recommended": "uprawa niewskazana",
    "not_applicable": "okres poza zakresem progu",
    "unavailable": "brak oceny",
}


def official_rows(table: pd.DataFrame, parcel: Parcel, day: date, crop: str) -> pd.DataFrame:
    options = table.loc[(table.period_end == day) & (table.crop_code == crop)]
    teryt = parcel.teryt.replace("_", "")
    # GUS TERYT: 4 and 5 are parts of the same urban-rural commune (3).
    # https://bdl.stat.gov.pl/bdl/metadane/teryt/rodzaj
    if teryt[-1:] in {"4", "5"}:
        teryt = f"{teryt[:-1]}3"
    if options.teryt.notna().any():
        matches = options.loc[options.teryt == teryt]
    else:
        # The 2018 table adds "(gm. miejska)" to distinguish urban municipalities.
        commune = parcel.commune.casefold()
        if teryt.endswith("1"):
            commune += " (gm. miejska)"
        county = parcel.county.casefold().removeprefix("powiat ")
        matches = options.loc[(options.commune.str.casefold() == commune) & (options.county.str.casefold() == county)]
    return matches if len(matches) == len(set(matches.soil_category)) else matches.iloc[:0]


def _number(value: float | None) -> str:
    return "—" if value is None else f"{value:.1f}".replace(".", ",")


def _matches(cases: list[tuple[KbwResult, int | None, str | None]]) -> list[bool]:
    return [
        result.verdict == official
        for result, _, official in cases
        if result.verdict in {"drought", "no_drought"} and official in {"drought", "no_drought"}
    ]


def _metrics(cases: list[tuple[KbwResult, int | None, str | None]]) -> list[str]:
    lines = []
    for label, field in (("Doroszewski–Górski", "kbw_mm"), ("FAO-56", "kbw_et0_mm")):
        errors = [
            getattr(result, field) - official
            for result, official, _ in cases if official is not None and getattr(result, field) is not None
        ]
        if errors:
            lines.append(f"- {label}, n = {len(errors)}, średni błąd bezwzględny {_number(mean(map(abs, errors)))} mm, średnia różnica {_number(mean(errors))} mm.")
        else:
            lines.append(f"- {label}, n = 0. Brak podstaw do obliczenia błędu.")
    decisions = _matches(cases)
    lines.append(
        f"- Zgodne werdykty, {sum(decisions)} z {len(decisions)} porównywalnych przypadków."
        if decisions else "- Brak porównywalnych rozstrzygnięć susza / brak suszy."
    )
    return lines


async def build(table: pd.DataFrame, fixtures: Path, crop: str, offline_reason: str | None, imgw_only: bool) -> str:
    provider = FixtureGeoProvider(fixtures)
    parcels = sorted(await asyncio.to_thread(provider.recorded_parcels), key=lambda parcel: parcel.parcel_id)
    if not parcels:
        raise ValueError(f"Brak zapisów części A w katalogu {fixtures}.")

    lines = [
        "# Walidacja KBW",
        "",
        f"Uprawa porównawcza to **{crops.load()[crop].name_pl.lower()}**. Klasa gleby pochodzi z zapisu części A dla danej działki i daty.",
        (
            "Porównanie korzysta z dobowych pomiarów stacji IMGW-PIB oraz tych samych obliczeń KBW co aplikacja."
            if imgw_only else "Porównanie korzysta z doboru pogody i obliczeń KBW stosowanych przez aplikację."
        ),
        "Podana różnica to KBW Vedry minus KBW MRiRW. Wynik z obwieszczenia dotyczy gminy. Vedra wykorzystuje komórkę modelu lub pomiary stacji przypisanej do działki.",
        "Dla 2018 r. stosujemy progi obowiązujące od 22.04.2017, a dla 2023 r. progi obowiązujące od 01.05.2019.",
        "Osobno sprawdzamy, czy urzędowa wartość KBW po porównaniu z progiem odtwarza opublikowany werdykt. Dane urzędowe służą tutaj do weryfikacji i nie zasilają obliczeń działki.",
        "[Progi dla 2018 r.](https://eli.gov.pl/eli/DU/2017/732/ogl), [progi od 2019 r.](https://eli.gov.pl/eli/DU/2019/739/ogl)",
        "",
        "## Odtworzenie lokalne",
        "",
        "Uruchom polecenia w katalogu `backend` po zainstalowaniu zależności aplikacji i pobraniu obu PDF-ów z odsyłaczy poniżej.",
        "Skrypt porównawczy korzysta domyślnie z zapisów części A w `tests/fixtures/geo`.",
        "",
        "```sh",
        "python -m pip install pypdf pyarrow",
        "python -m scripts.b.build_kbw_official --pdf-2018 2018-13.pdf --pdf-2023 2023-25.pdf",
        "python -m scripts.b.backtest --imgw-only" if imgw_only else "python -m scripts.b.backtest",
        "```",
        "",
    ]
    if offline_reason:
        lines.extend((f"**Wynik niepełny.** {offline_reason} Tabele pokazują odczytane wartości urzędowe i dostępność porównania.", ""))
    all_cases = []
    all_threshold_checks = []
    for day in sorted(set(table.period_end)):
        source = table.loc[table.period_end == day, "source"].iloc[0]
        lines.extend((
            f"## {day}", "",
            f"[Obwieszczenie MRiRW]({source})", "",
            "| Działka | Gmina | Gleba | Próg KBW, mm | KBW MRiRW, mm | Werdykt MRiRW | KBW Vedry, mm | KBW FAO-56, mm | Werdykt Vedry |",
            "| --- | --- | --- | ---: | ---: | --- | ---: | ---: | --- |",
        ))
        cases = []
        threshold_checks = []
        for parcel in parcels:
            bundle = await provider.collect(GeoRequest(parcel=parcel, analysis_date=day))
            category: KbwSoilCategory | None = bundle.soil.data.kbw_category if bundle.soil.data else None
            published = official_rows(table, parcel, day, crop)
            official = int(published.kbw_mm.iloc[0]) if not published.empty else None
            verdicts = published.loc[published.soil_category == category, "verdict"]
            official_verdict = verdicts.iloc[0] if not verdicts.empty else None
            if offline_reason:
                fetched = None
            elif imgw_only:
                period = periods.latest_completed(day)
                fetched = await asyncio.to_thread(
                    imgw_weather.read_weather, parcel.centroid_lat, parcel.centroid_lon, day, period,
                ) if period is not None else None
            else:
                fetched = await weather_provider.fetch_weather(parcel.centroid_lat, parcel.centroid_lon, day)
            result = kbw.assess(fetched.data if fetched is not None else None, category, crop, day)
            cases.append((result, official, official_verdict))
            threshold = result.threshold_mm
            if official is not None and isinstance(threshold, float) and official_verdict in {"drought", "no_drought"}:
                threshold_checks.append(kbw.numeric_verdict(official, threshold) == official_verdict)
            fields = (
                parcel.parcel_id, parcel.commune, category or "—",
                _number(threshold) if isinstance(threshold, float) else threshold or "—", _number(official),
                LABELS.get(official_verdict, "—"), _number(result.kbw_mm), _number(result.kbw_et0_mm),
                LABELS[result.verdict],
            )
            lines.append("| " + " | ".join(fields) + " |")
        lines.extend(("", *_metrics(cases), ""))
        if threshold_checks:
            lines.extend((f"- Odtworzenie werdyktu po podstawieniu urzędowego KBW: {sum(threshold_checks)} z {len(threshold_checks)}.", ""))
        all_cases.extend(cases)
        all_threshold_checks.extend(threshold_checks)

    weather_checks = _matches(all_cases)
    lines.extend(("## Podsumowanie", ""))
    if weather_checks:
        lines.append(f"- Zgodność niezależnych szacunków KBW Vedry z werdyktami MRiRW: **{sum(weather_checks)} z {len(weather_checks)}**.")
    if all_threshold_checks:
        lines.append(f"- Zgodność reguły progowej przy urzędowym KBW gminy: **{sum(all_threshold_checks)} z {len(all_threshold_checks)}**.")
    lines.append("")
    return "\n".join(lines)


async def _run(args: argparse.Namespace) -> None:
    try:
        document = await build(pd.read_parquet(args.official), args.fixtures, args.crop, args.offline_reason, args.imgw_only)
        args.output.write_text(document, encoding="utf-8")
        print(f"Zapisano wyniki walidacji w pliku {args.output}.")
    finally:
        await http.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Porównaj KBW Vedry z obwieszczeniami MRiRW.")
    parser.add_argument("--official", type=Path, default=PARQUET)
    parser.add_argument("--fixtures", type=Path, default=FIXTURES_DIR)
    parser.add_argument("--crop", choices=tuple(crops.load()), default=DEFAULT_CROP, help="Kod uprawy.")
    parser.add_argument("--output", type=Path, default=VALIDATION)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--offline-reason", help="Pomiń pobieranie pogody i wpisz przyczynę w dokumencie.")
    mode.add_argument("--imgw-only", action="store_true", help="Użyj tylko lokalnego archiwum pomiarów IMGW-PIB.")
    asyncio.run(_run(parser.parse_args()))


if __name__ == "__main__":
    main()
