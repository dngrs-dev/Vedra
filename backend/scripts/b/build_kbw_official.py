"""Extract commune KBW and crop/soil verdicts from the CP4 MRiRW annexes."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date
from hashlib import sha256
import json
from pathlib import Path
import re

import pandas as pd
from pypdf import PdfReader

from app.config import CONFIG_DIR

DATA_DIR = CONFIG_DIR.parent / "data" / "b"

# Crop order and category order are from the header of each linked PDF annex.
CROPS_2018 = (
    "winter_cereals", "spring_cereals", "grain_maize", "silage_maize",
    "rapeseed", "potatoes", "sugar_beet", "hops", "tobacco",
    "field_vegetables", "fruit_bushes", "fruit_trees", "strawberries", "legumes",
)
CROPS_2023 = (
    "winter_cereals", "spring_cereals", "rapeseed", "sugar_beet",
    "fruit_bushes", "fruit_trees", "strawberries",
)
CATEGORIES = ("I", "II", "III", "IV")
# The legend at the end of each official annex supplies the Polish labels.
LEGEND = {
    "+": ("susza", "drought"),
    "-": ("brak suszy", "no_drought"),
    "*": ("kategoria gleby nie występuje", "soil_absent"),
    "#": ("na oznaczonej kategorii gleby uprawa nie jest wskazana", "not_recommended"),
}


@dataclass(frozen=True)
class Notice:
    source: str
    start: date
    end: date
    period_title: str
    crop_codes: tuple[str, ...]
    has_teryt: bool
    communes: int


# Period bounds and publication details are on the cover of each PDF.
# Commune counts are the number of rows published in the respective annexes.
NOTICES = (
    Notice(
        "https://edziennik.minrol.gov.pl/DUM_MRIRW/2018/13/akt.pdf",
        date(2018, 5, 11), date(2018, 7, 10), "11 maja do dnia 10 lipca 2018",
        CROPS_2018, False, 2478,
    ),
    Notice(
        "https://edziennik.minrol.gov.pl/DUM_MRIRW/2023/25/oryginal/akt.pdf",
        date(2023, 4, 1), date(2023, 5, 31), "1 kwietnia do 31 maja 2023",
        CROPS_2023, True, 2477,
    ),
)


def extract(path: Path, notice: Notice) -> pd.DataFrame:
    reader = PdfReader(path)
    cover = " ".join(reader.pages[0].extract_text().split())
    if notice.period_title not in cover:
        raise ValueError(f"Okres obwieszczenia nie zgadza się z oczekiwanym: {notice.end}.")
    rows = []
    labels = {}
    identities = set()
    for page_number, page in enumerate(reader.pages[1:], start=2):
        layout = page.extract_text(extraction_mode="layout")
        legend = re.findall(r"(?m)^\s*([+*#-])\s+([^\r\n]+)", layout)
        labels.update((symbol, " ".join(label.casefold().split())) for symbol, label in legend)
        for line in layout.splitlines():
            parts = re.split(r" {2,}", line.strip())
            if not parts or parts[-1] not in LEGEND or len(parts) < len(CATEGORIES):
                continue
            prefix_count = 4 if notice.has_teryt else 3
            expected = prefix_count + len(notice.crop_codes) * len(CATEGORIES)
            if len(parts) != expected or any(mark not in LEGEND for mark in parts[prefix_count:]):
                raise ValueError(f"Nieoczekiwany układ wiersza w obwieszczeniu {notice.end}, strona {page_number}.")
            county, commune, *fields = parts[:prefix_count]
            teryt, value = fields if notice.has_teryt else (None, fields[0])
            if teryt is not None and not re.fullmatch(r"[0-9]{7}", teryt):
                raise ValueError(f"Niepoprawny kod TERYT w obwieszczeniu {notice.end}, strona {page_number}.")
            identity = teryt if teryt is not None else (county, commune)
            identities.add(identity)
            pairs = ((crop, category) for crop in notice.crop_codes for category in CATEGORIES)
            rows.extend({
                "period_start": notice.start,
                "period_end": notice.end,
                "county": county,
                "commune": commune,
                "teryt": teryt,
                "kbw_mm": int(value),
                "crop_code": crop,
                "soil_category": category,
                "symbol": symbol,
                "verdict": LEGEND[symbol][1],
                "source": notice.source,
                "pdf_page": page_number,
            } for (crop, category), symbol in zip(pairs, parts[prefix_count:], strict=True))
    expected_rows = notice.communes * len(notice.crop_codes) * len(CATEGORIES)
    expected_labels = {symbol: label for symbol, (label, _) in LEGEND.items()}
    if labels != expected_labels or len(rows) != expected_rows or len(identities) != notice.communes:
        raise ValueError(f"Niepełna legenda lub nieoczekiwana liczba gmin w obwieszczeniu {notice.end}.")
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Zapisz dane KBW z dwóch obwieszczeń MRiRW.")
    parser.add_argument("--pdf-2018", type=Path, required=True, help="Plik PDF z 18 lipca 2018 r., poz. 13.")
    parser.add_argument("--pdf-2023", type=Path, required=True, help="Plik PDF z 7 czerwca 2023 r., poz. 25.")
    parser.add_argument("--output", type=Path, default=DATA_DIR / "kbw_official.parquet")
    args = parser.parse_args()

    frames = []
    sources = []
    for notice, path in zip(NOTICES, (args.pdf_2018, args.pdf_2023), strict=True):
        frames.append(extract(path, notice))
        sources.append({
            "source": notice.source,
            "period_start": notice.start.isoformat(),
            "period_end": notice.end.isoformat(),
            "source_sha256": sha256(path.read_bytes()).hexdigest(),
            "communes": notice.communes,
        })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result = pd.concat(frames, ignore_index=True)
    result.to_parquet(args.output, index=False)
    manifest = {
        "kbw_official": {
            "file": args.output.name,
            "rows": len(result),
            "sources": sources,
            "licence_pl": "Obwieszczenia urzędowe MRiRW (art. 4 pkt 2 ustawy o prawie autorskim).",
        },
    }
    args.output.with_name("manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    print(f"Zapisano {len(result)} wierszy: {args.output}")


if __name__ == "__main__":
    main()
