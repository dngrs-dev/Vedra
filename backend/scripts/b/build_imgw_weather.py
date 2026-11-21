"""Prepare a reproducible SQLite archive from public IMGW-PIB daily SYNOP files."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import csv
from datetime import date, datetime, timezone
from hashlib import sha256
from html.parser import HTMLParser
from io import BytesIO, TextIOWrapper
import json
from math import isfinite
from pathlib import Path
import re
import sqlite3
from tempfile import TemporaryDirectory
from zipfile import ZipFile

import httpx

from app.analytics.imgw_weather import ARCHIVE_URL, DEFAULT_ARCHIVE, STATIONS_URL
from app.analytics.open_meteo import ARCHIVE_START
from app.config import analysis_today

# Official archive format: s_d_format.txt in ARCHIVE_URL. Flag 8 means no measurement,
# flag 9 means the phenomenon did not occur (valid zero for precipitation and sunshine).
DAILY_PRECIPITATION = 13  # SMDB
DAILY_SUNSHINE = 20  # USL
COLUMNS = (DAILY_PRECIPITATION, 9, DAILY_SUNSHINE)  # The middle field is STD (daily mean temperature).
NO_MEASUREMENT = "8"
NO_PHENOMENON = "9"
ZERO_IF_ABSENT = {DAILY_PRECIPITATION, DAILY_SUNSHINE}
PRE_2001 = ("1991_1995", "1996_2000")  # Grouped directories in the official archive listing.
# Use a small maintenance-only worker pool and the shared HTTP client's nominal timeout.
DOWNLOAD_WORKERS = 6
REQUEST_TIMEOUT_S = 10

SCHEMA = """
CREATE TABLE station (code INTEGER PRIMARY KEY, name TEXT NOT NULL, lat REAL NOT NULL, lon REAL NOT NULL)
    WITHOUT ROWID;
CREATE TABLE observation (
    station INTEGER NOT NULL REFERENCES station(code), day INTEGER NOT NULL,
    precipitation_mm REAL, temperature_mean_c REAL, sunshine_h REAL, PRIMARY KEY (station, day)
) WITHOUT ROWID;
CREATE TABLE input (url TEXT PRIMARY KEY, fetched_at TEXT NOT NULL, sha256 TEXT NOT NULL) WITHOUT ROWID;
"""


class ArchiveListing(HTMLParser):
    def __init__(self, folder: str) -> None:
        super().__init__()
        self.pattern = re.compile(rf"{folder}_(\d{{2,3}})_s\.zip")
        self.entries: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        href = dict(attrs).get("href")
        if tag == "a" and href and (match := self.pattern.fullmatch(href)):
            self.entries.append((href, match[1]))


def measurement(row: list[str], index: int) -> float | None:
    status = row[index + 1].strip()
    if status == NO_PHENOMENON and index in ZERO_IF_ABSENT:
        return 0.0
    if status == NO_MEASUREMENT or status or not row[index].strip():
        return None
    value = float(row[index])
    return value if isfinite(value) else None


def observations(payload: bytes, stations: dict[str, tuple], start: date, end: date):
    with ZipFile(BytesIO(payload)) as archive:
        for member in archive.namelist():
            name = Path(member).name
            if not name.startswith("s_d_") or name.startswith("s_d_t_") or not name.endswith(".csv"):
                continue
            with archive.open(member) as raw, TextIOWrapper(raw, encoding="cp1250", newline="") as stream:
                for row in csv.reader(stream):
                    if not row or row[0] not in stations:
                        continue
                    day = date(*map(int, row[2:5]))
                    if start <= day <= end:
                        values = tuple(measurement(row, index) for index in COLUMNS)
                        if any(value is not None for value in values):
                            yield int(row[0]), day.toordinal(), *values


def download(client: httpx.Client, url: str) -> bytes:
    response = client.get(url)
    response.raise_for_status()
    return response.content


def saved_download(client: httpx.Client, url: str, path: Path) -> tuple[str, str, bytes]:
    if path.is_file():
        payload = path.read_bytes()
    else:
        payload = download(client, url)
        partial = path.with_suffix(".part")
        partial.write_bytes(payload)
        partial.replace(path)
    fetched_at = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
    return url, fetched_at, payload


def build(destination: Path, cache_dir: Path, start: date, end: date) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=REQUEST_TIMEOUT_S, follow_redirects=True, headers={"User-Agent": "Vedra"}) as client:
        url, fetched_at, raw = saved_download(client, STATIONS_URL, cache_dir / "stations.json")
        stations = {
            row["kod_stacji"]: (row["nazwa_stacji"], float(row["lat"]), float(row["lon"]))
            for row in json.loads(raw)
            if row.get("kod_stacji") and row.get("lat") and row.get("lon")
        }
        station_suffixes = {code[-3:] for code in stations}
        folders = [folder for folder in PRE_2001 if int(folder[-4:]) >= start.year and int(folder[:4]) <= end.year]
        folders.extend(str(year) for year in range(max(start.year, 2001), end.year + 1))
        entries = []
        for folder in folders:
            listing = ArchiveListing(folder)
            listing.feed(download(client, f"{ARCHIVE_URL}{folder}/").decode("utf-8"))
            # Published files for the open year contain all stations for each month.
            for filename, suffix in listing.entries:
                if len(suffix) == 2 or suffix in station_suffixes:
                    entries.append((f"{ARCHIVE_URL}{folder}/{filename}", cache_dir / filename))
        if not entries:
            raise ValueError("Archiwum IMGW-PIB nie zawiera plików dla podanego zakresu.")
        print(f"Pobieranie zestawu IMGW-PIB ({len(entries)} archiwów).", flush=True)

        with TemporaryDirectory(dir=destination.parent) as temp:
            pending = Path(temp) / destination.name
            with closing(sqlite3.connect(pending)) as db, db, ThreadPoolExecutor(max_workers=DOWNLOAD_WORKERS) as pool:
                db.executescript(SCHEMA)
                db.execute("INSERT INTO input VALUES (?, ?, ?)", (url, fetched_at, sha256(raw).hexdigest()))
                db.executemany("INSERT INTO station VALUES (?, ?, ?, ?)", ((int(k), *v) for k, v in sorted(stations.items())))
                for source_url, stamp, payload in pool.map(lambda pair: saved_download(client, *pair), entries):
                    db.execute("INSERT INTO input VALUES (?, ?, ?)", (source_url, stamp, sha256(payload).hexdigest()))
                    db.executemany("INSERT INTO observation VALUES (?, ?, ?, ?, ?)",
                                   observations(payload, stations, start, end))
                db.execute("DELETE FROM station WHERE code NOT IN (SELECT DISTINCT station FROM observation)")
                span = db.execute("SELECT count(*), min(day), max(day) FROM observation").fetchone()
                count = db.execute("SELECT count(*) FROM station").fetchone()[0]
                if not span[0] or not count:
                    raise ValueError("Nie udało się powiązać pomiarów z metadanymi stacji.")
            pending.replace(destination)
        print(f"Zapisano {span[0]} dni stacyjnych dla {count} stacji "
              f"({date.fromordinal(span[1])} – {date.fromordinal(span[2])}).", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Przygotuj lokalne archiwum pomiarów dobowych IMGW-PIB.")
    parser.add_argument("--cache-dir", type=Path, required=True, help="Katalog roboczy na źródłowe pliki ZIP.")
    parser.add_argument("--output", type=Path, default=DEFAULT_ARCHIVE, help="Plik SQLite do zapisania.")
    parser.add_argument("--start", type=date.fromisoformat, default=ARCHIVE_START)
    parser.add_argument("--end", type=date.fromisoformat, default=analysis_today())
    args = parser.parse_args()
    build(args.output, args.cache_dir, args.start, args.end)


if __name__ == "__main__":
    main()
