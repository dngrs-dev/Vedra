"""Preprocess GUGiK NMT for the test parcels -> data/a/nmt/<parcel_id_sanitized>.tif (+ data/a/manifest.json).

Usage (from backend/): python -m scripts.a.prefetch_nmt [--parcels N]

The NMT WCS needs 52-99 s per GetCoverage (config/geo_sources.yaml gugik_nmt_wcs), beyond the 22 s budget,
so the test parcels get their DEM ahead of time. Grid and resolution are exactly what app.geo.dem.grid_for
chooses at runtime (parcel + 200 m, 2-10 m, <= max_cells), stored as deflate-compressed float32 GeoTIFF.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime, timezone

from app.core import http
from app.geo import dem, uldk
from app.geo.sources import BACKEND, DATA_DIR, source

MANIFEST = DATA_DIR / "manifest.json"


def write_manifest(done: list[str]) -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {}
    manifest["nmt/"] = {
        "url": source("gugik_nmt_wcs")["url"] + f" (coverage {source('gugik_nmt_wcs')['coverage_id']})",
        "downloaded": datetime.now(timezone.utc).date().isoformat(),
        "licence": source("gugik_nmt_wcs")["licence_declared"],
        "content": "NMT (EPSG:2180, PL-KRON86-NH) for each test parcel + 200 m, resampled by the WCS "
                   "(SCALEFACTOR) to the grid chosen by app.geo.dem.grid_for; files: " + ", ".join(done),
        "script": "scripts/a/prefetch_nmt.py",
    }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


async def main(n: int | None, parallel: int) -> int:
    parcels = json.loads((BACKEND / "tests" / "fixtures" / "parcels.json").read_text(encoding="utf-8"))[:n]
    dem.NMT_DIR.mkdir(parents=True, exist_ok=True)
    done = set(p.name for p in dem.NMT_DIR.glob("*.tif"))
    sem = asyncio.Semaphore(parallel)   # the WCS latency is per request, so a few requests can overlap
    failed = 0

    async def one(pid: str) -> None:
        nonlocal failed
        parcel = await uldk.get_by_id(pid)
        path = dem.preprocessed_path(parcel)
        if path.exists():
            print(f"  have  {path.name}")
            return
        async with sem:
            t = time.monotonic()
            try:
                blob = await dem.prefetch_nmt(parcel)
            except Exception as exc:  # noqa: BLE001 - report and continue
                failed += 1
                print(f"  fail  {parcel.parcel_id} after {time.monotonic() - t:.0f} s: {type(exc).__name__}: "
                      f"{str(exc)[:150]}")
                return
        path.write_bytes(blob)
        done.add(path.name)
        write_manifest(sorted(done))
        _, res = dem.grid_for(parcel)
        print(f"  ok    {path.name} ({res:g} m, {len(blob) // 1024} KB) in {time.monotonic() - t:.0f} s")

    await asyncio.gather(*(one(p["parcel_id"]) for p in parcels))
    await http.close()
    return 1 if failed else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--parcels", type=int, default=None)
    ap.add_argument("--parallel", type=int, default=4)   # our choice: polite to the GUGiK service
    a = ap.parse_args()
    sys.exit(asyncio.run(main(a.parcels, a.parallel)))
