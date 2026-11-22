"""Build a queryable local index from official GUGiK parcel GeoParquet files."""
from __future__ import annotations

import argparse
import json
import sqlite3
from contextlib import closing
from math import isfinite
from pathlib import Path
from tempfile import NamedTemporaryFile

import pyarrow.parquet as pq
from pyproj import CRS

from app.api.egib_snapshot import SCHEMA

# Official Geoportal exports use these columns (see docs/DATA_SOURCES.md §2.2).
COLUMNS = ["id_dzialki", "nazwa_gminy", "nazwa_obrebu", "numer_dzialki", "geometry", "geometry_bbox"]


def _append_file(db: sqlite3.Connection, path: Path, offset: int) -> int:
    with pq.ParquetFile(path) as source:
        metadata = source.schema_arrow.metadata or {}
        geo = json.loads(metadata.get(b"geo", b"{}"))
        description = geo.get("columns", {}).get("geometry", {})
        crs = CRS.from_user_input(description["crs"]) if description.get("crs") else None
        # GUGiK publishes ETRF2000-PL / CS92 in the same projection as EPSG:2180.
        if crs is None or (crs.to_epsg() != 2180 and crs.name != "ETRF2000-PL / CS92"):
            raise ValueError(f"Nieobsługiwany układ współrzędnych w pliku {path.name}.")
        if description.get("encoding") != "WKB" or not set(COLUMNS) <= set(source.schema_arrow.names):
            raise ValueError(f"Plik {path.name} nie ma struktury eksportu działek EGiB.")

        count = offset
        for batch in source.iter_batches(columns=COLUMNS):
            parcels = []
            bounds = []
            for row in batch.to_pylist():
                bbox = row["geometry_bbox"]
                if not (row["id_dzialki"] and row["geometry"] and bbox):
                    continue
                xmin, xmax, ymin, ymax = (bbox[key] for key in ("xmin", "xmax", "ymin", "ymax"))
                if not all(value is not None and isfinite(value) for value in (xmin, xmax, ymin, ymax)):
                    continue
                if xmin > xmax or ymin > ymax:
                    continue
                count += 1
                parcels.append((count, row["id_dzialki"], row["nazwa_gminy"], row["nazwa_obrebu"],
                                row["numer_dzialki"], row["geometry"]))
                bounds.append((count, xmin, xmax, ymin, ymax))
            db.executemany("INSERT INTO parcels VALUES (?, ?, ?, ?, ?, ?)", parcels)
            db.executemany("INSERT INTO parcel_bounds VALUES (?, ?, ?, ?, ?)", bounds)
        if count == offset:
            raise ValueError(f"Nie znaleziono działek w pliku {path.name}.")
        db.execute("INSERT INTO sources VALUES (?, ?)", (path.name, count - offset))
        print(f"{path.name}: wczytano {count - offset} z {source.metadata.num_rows} rekordów.", flush=True)
        return count


def build(inputs: list[Path], output: Path) -> int:
    if output.resolve() in {path.resolve() for path in inputs}:
        raise ValueError("Baza wynikowa musi mieć inną ścieżkę niż pliki wejściowe.")
    output.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=output.parent, suffix=".sqlite.tmp", delete=False) as stream:
        temporary = Path(stream.name)
    try:
        with closing(sqlite3.connect(temporary)) as db, db:
            db.executescript(SCHEMA)
            count = 0
            for path in inputs:
                count = _append_file(db, path, count)
            db.execute("CREATE INDEX parcel_id_idx ON parcels(parcel_id)")
        temporary.replace(output)
        return count
    finally:
        temporary.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Zbuduj lokalną bazę działek z eksportu GeoParquet GUGiK.")
    parser.add_argument("inputs", type=Path, nargs="+", help="Krajowy lub wojewódzkie pliki działek EGiB.")
    parser.add_argument("--output", type=Path, required=True, help="Ścieżka do lokalnej bazy SQLite.")
    args = parser.parse_args()
    try:
        count = build(args.inputs, args.output)
    except (OSError, ValueError, KeyError, sqlite3.Error) as exc:
        parser.exit(1, f"Nie udało się zbudować bazy EGiB. {exc}\n")
    print(f"Zapisano {count} rekordów w {args.output}.")


if __name__ == "__main__":
    main()
