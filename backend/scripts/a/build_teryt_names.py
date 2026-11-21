"""Build data/a/teryt_names.json: voivodeship and county names by TERYT code, from the PRG WFS (+ manifest).

Usage (from backend/): python -m scripts.a.build_teryt_names

The national parcel GeoParquet (config `egib_parquet`, the ULDK fallback) has the commune and obręb names but not the
voivodeship / county names that Parcel needs; PRG (państwowy rejestr granic, GUGiK) has both by TERYT code.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone

import httpx

from app.geo.sources import DATA_DIR, source

OUT = DATA_DIR / "teryt_names.json"
MANIFEST = DATA_DIR / "manifest.json"
_MEMBER_RE = re.compile(r"<ms:JPT_KOD_JE>([^<]+)</ms:JPT_KOD_JE>\s*<ms:JPT_NAZWA_>([^<]+)</ms:JPT_NAZWA_>")


def names(c: httpx.Client, layer: str) -> dict[str, str]:
    cfg = source("prg_wfs")
    r = c.get(cfg["url"], params={"SERVICE": "WFS", "REQUEST": "GetFeature", "VERSION": "2.0.0",
                                  "TYPENAMES": cfg["layers"][layer], "PROPERTYNAME": "JPT_KOD_JE,JPT_NAZWA_"})
    r.raise_for_status()
    return dict(_MEMBER_RE.findall(r.text))


def main() -> int:
    with httpx.Client(timeout=120, follow_redirects=True) as c:
        out = {"voivodeships": names(c, "voivodeships"), "counties": names(c, "counties")}
    if len(out["voivodeships"]) != 16:
        print("unexpected voivodeship count", len(out["voivodeships"]))
        return 1
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=0, sort_keys=True) + "\n", encoding="utf-8")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {}
    manifest["teryt_names.json"] = {
        "url": source("prg_wfs")["url"] + " (GetFeature " + ", ".join(source("prg_wfs")["layers"][k]
                                                                  for k in ("voivodeships", "counties")) + ")",
        "downloaded": datetime.now(timezone.utc).date().isoformat(),
        "licence": source("prg_wfs")["licence"],
        "content": f"{len(out['voivodeships'])} voivodeship and {len(out['counties'])} county names by TERYT code "
                   "(JPT_KOD_JE -> JPT_NAZWA_)",
        "script": "scripts/a/build_teryt_names.py",
    }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{len(out['voivodeships'])} voivodeships, {len(out['counties'])} counties -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
