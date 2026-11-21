"""Build data/a/imgw_synop_stations.json: coordinates for the IMGW synop stations (+ data/a/manifest.json).

Usage (from backend/): python -m scripts.a.build_imgw_stations

/api/data/synop has no coordinates (spike 2026-11-21). /api/data/meteo lists IMGW stations with lat/lon.
Join by station name (the IMGW code and WMO id do not follow one rule - checked 2026-11-21: the last three
digits differ for 8 of 46 name-matched stations, e.g. Wrocław 12424 vs 351160425):
  1. exact name (case-insensitive),
  2. otherwise a unique meteo station named "<synop name>-..." or "<synop name> ..." (e.g. Kraków ->
     KRAKÓW-BALICE), with '-' and ' ' treated alike,
  3. otherwise unmatched (recorded, not used).
"""
from __future__ import annotations

import json
import sys
import unicodedata
from datetime import datetime, timezone

import httpx

from app.geo.sources import DATA_DIR, source

OUT = DATA_DIR / "imgw_synop_stations.json"
MANIFEST = DATA_DIR / "manifest.json"


def norm(text: str) -> str:
    return unicodedata.normalize("NFC", text).strip().casefold().replace("-", " ")


def main() -> int:
    cfg = source("imgw")
    with httpx.Client(timeout=30, headers={"User-Agent": "Vedra/0.1 (HackNation 2026 prototype)"}) as c:
        synop = c.get(cfg["synop_url"]).json()
        meteo = c.get(cfg["meteo_url"]).json()
    by_name: dict[str, list[dict]] = {}
    for m in meteo:
        by_name.setdefault(norm(m["nazwa_stacji"]), []).append(m)
    stations, unmatched = [], []
    for s in synop:
        name = norm(s["stacja"])
        cands, method = by_name.get(name, []), "name_exact"
        if len(cands) != 1:
            cands = [m for k, ms in by_name.items() if k.startswith(name + " ") for m in ms]
            method = "name_prefix"
        if len(cands) != 1:
            unmatched.append({"id_stacji": s["id_stacji"], "stacja": s["stacja"], "candidates": len(cands)})
            continue
        m = cands[0]
        stations.append({"id_stacji": s["id_stacji"], "stacja": s["stacja"], "lat": float(m["lat"]),
                         "lon": float(m["lon"]), "meteo_kod_stacji": m["kod_stacji"],
                         "meteo_nazwa_stacji": m["nazwa_stacji"], "method": method})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"stations": stations, "unmatched": unmatched}, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {}
    manifest["imgw_synop_stations.json"] = {
        "url": f"{cfg['synop_url']} + {cfg['meteo_url']}",
        "downloaded": datetime.now(timezone.utc).date().isoformat(),
        "licence": "IMGW-PIB dane publiczne (attribution required, see config/geo_sources.yaml imgw)",
        "content": "synop station id/name joined by name to meteo station coordinates",
        "script": "scripts/a/build_imgw_stations.py",
    }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{len(stations)} stations with coordinates, {len(unmatched)} unmatched: "
          f"{[u['stacja'] for u in unmatched]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
