"""Pick real agricultural test parcels via ULDK GetParcelByXY -> tests/fixtures/parcels.json.

Usage (from backend/):
    python -m scripts.a.pick_test_parcels            # query candidates, write parcels.json
    python -m scripts.a.pick_test_parcels --dry-run  # print only

Parcel ids are never typed by hand: each comes from ULDK for a candidate point. The candidate points are
our choice (farmland regions in different voivodeships, aimed at the mix asked for in
PART_A_DATA_GEO.md CP0: light/heavy soils, flat/sloped, < 1 ha and > 20 ha, an id with AR_).
A parcel is kept only if ESA WorldCover 2021 says "Cropland" (class 40, WorldCover legend) at its
centroid. All facts written to the file are measured from the sources named next to them.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from pathlib import Path

for _var in ("PROJ_LIB", "GDAL_DATA"):  # see scripts/a/spike_sources.py
    os.environ.pop(_var, None)

import httpx  # noqa: E402
import yaml  # noqa: E402
from pyproj import Transformer  # noqa: E402
from shapely import wkt  # noqa: E402
from shapely.geometry import mapping  # noqa: E402

BACKEND = Path(__file__).resolve().parents[2]
CFG = yaml.safe_load((BACKEND / "config" / "geo_sources.yaml").read_text(encoding="utf-8"))
OUT = BACKEND / "tests" / "fixtures" / "parcels.json"

# (lon, lat, region label) - our choice of farmland areas; the parcel itself comes from ULDK.
# Dry run 2026-11-21 also tried, and dropped: 14.90,53.15 (Pyrzyce: WorldCover 10 Tree cover),
# 17.05,50.78 (Strzelin: ULDK no parcel), 21.90,49.95 (Rzeszów: WorldCover 30 Grassland),
# 17.85,50.35 (Głogówek: cropland, but heavy-soil case already covered; keeps the set at 8).
CANDIDATES: list[tuple[float, float, str]] = [
    (18.30, 52.80, "Kujawy, okolice Inowrocławia"),
    (17.62, 52.30, "Wielkopolska, okolice Wrześni"),
    (23.80, 50.82, "Lubelszczyzna, okolice Hrubieszowa"),
    (21.05, 51.45, "Mazowsze, okolice Radomia"),
    (20.30, 50.20, "Małopolska, okolice Proszowic"),
    (21.35, 54.05, "Warmia i Mazury, okolice Kętrzyna"),
    (22.10, 53.40, "Podlasie, okolice Grajewa"),
    (19.35, 52.25, "Ziemia łódzka, okolice Kutna"),
]

WORLDCOVER_CROPLAND = 40  # ESA WorldCover v200 legend: 40 = Cropland
TO_2180 = Transformer.from_crs(4326, 2180, always_xy=True)
client = httpx.Client(timeout=float(CFG["spike"]["timeout_s"]), follow_redirects=True,
                      headers={"User-Agent": "Vedra/0.1 (HackNation 2026 prototype)"})


def uldk_by_xy(lon: float, lat: float, srid: int) -> list[str] | None:
    c = CFG["uldk"]
    r = client.get(c["url"], params={"request": "GetParcelByXY", "xy": c["xy_format"].format(lon=lon, lat=lat),
                                     "result": c["result_fields"], "srid": srid})
    r.raise_for_status()
    lines = r.text.strip().splitlines()
    if not lines or lines[0].strip() != "0" or len(lines) < 2:
        return None
    return lines[1].split("|")


def _sample(href: str, lon: float, lat: float):
    import rasterio
    from rasterio.warp import transform

    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif"), \
            rasterio.open("/vsicurl/" + href) as ds:
        xs, ys = transform("EPSG:4326", ds.crs, [lon], [lat])
        return next(ds.sample([(xs[0], ys[0])]))[0]


def worldcover_class(lon: float, lat: float) -> int:
    lat0, lon0 = 3 * math.floor(lat / 3), 3 * math.floor(lon / 3)
    tile = f"N{lat0:02d}E{lon0:03d}"  # Poland: northern and eastern hemisphere only
    return int(_sample(CFG["worldcover"]["url_template"].format(tile=tile), lon, lat))


def dem_range(geom_wgs84) -> tuple[float, float] | None:
    """Min/max elevation (m) of Copernicus DEM GLO-30 cells touching the parcel."""
    import numpy as np
    import rasterio
    from rasterio.mask import mask

    lon, lat = geom_wgs84.centroid.x, geom_wgs84.centroid.y
    href = CFG["copernicus_dem"]["url_template"].format(lat=math.floor(lat), lon=math.floor(lon))
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif"), \
            rasterio.open("/vsicurl/" + href) as ds:
        arr, _ = mask(ds, [mapping(geom_wgs84)], crop=True, all_touched=True, filled=False)
    vals = arr.compressed()
    if vals.size == 0:
        return None
    return float(np.min(vals)), float(np.max(vals))


def soil_at(lon: float, lat: float) -> dict[str, object]:
    c = CFG["soil_map"]
    x, y = TO_2180.transform(lon, lat)
    r = client.get(c["url"], params=dict(
        SERVICE="WMS", VERSION=c["wms_version"], REQUEST="GetFeatureInfo", LAYERS=c["query_layer"],
        QUERY_LAYERS=c["query_layer"], CRS=c["crs"], BBOX=f"{y - 50},{x - 50},{y + 50},{x + 50}",
        WIDTH=101, HEIGHT=101, I=50, J=50, INFO_FORMAT=c["info_format"], STYLES=""))
    if "<FIELDS" not in r.text:
        return {}
    attrs = dict(re.findall(r'(\w+)="([^"]*)"', r.text.split("<FIELDS", 1)[1]))
    a, nulls = c["attributes"], set(c["null_values"])

    def vals(keys):
        return [attrs[k] for k in keys if attrs.get(k) not in (None, *nulls)]

    return {"complex": attrs.get(a["complex"]), "texture_layers": vals(a["texture_layers"]),
            "alluvial_texture": vals(a["alluvial_texture"])}


def describe(lon: float, lat: float, region: str) -> dict | None:
    rec4326, rec2180 = uldk_by_xy(lon, lat, 4326), uldk_by_xy(lon, lat, 2180)
    if not rec4326 or not rec2180:
        print(f"  - {region}: ULDK returned no parcel")
        return None
    parcel_id = rec4326[0]
    g4326 = wkt.loads(rec4326[1].split(";", 1)[1])
    g2180 = wkt.loads(rec2180[1].split(";", 1)[1])
    teryt, voiv, county, commune, obreb, nr = rec4326[2:8]
    area_ha = g2180.area / 10_000
    # representative_point() is guaranteed inside the polygon (centroid may not be)
    pt = g4326.representative_point()
    wc = worldcover_class(pt.x, pt.y)
    soil = soil_at(pt.x, pt.y)
    rng = dem_range(g4326)
    facts = {
        "voivodeship": voiv, "county": county, "commune": commune, "region": obreb, "parcel_number": nr,
        "area_ha": round(area_ha, 3),
        "worldcover_class_at_point": wc,
        "soil_map_complex": soil.get("complex"),
        "soil_map_texture_layers": soil.get("texture_layers"),
        "soil_map_alluvial_texture": soil.get("alluvial_texture"),
        "copernicus_dem_min_max_m": [round(v, 1) for v in rng] if rng else None,
        "has_ar_sheet": ".AR_" in parcel_id,
    }
    tex = soil.get("texture_layers") or soil.get("alluvial_texture") or []
    relief = f"deniwelacja {rng[1] - rng[0]:.0f} m (Copernicus DEM 30 m)" if rng else "brak danych NMT"
    note = (f"{region}; {area_ha:.2f} ha; gleba: {', '.join(tex) or 'brak gatunku'} "
            f"(kompleks {soil.get('complex')}, mapa glebowo-rolnicza); {relief}")
    status = "OK " if wc == WORLDCOVER_CROPLAND else "SKIP"
    print(f"  {status} {parcel_id:28} {area_ha:8.2f} ha  WC={wc}  soil={tex} kompleks={soil.get('complex')}  {relief}")
    if wc != WORLDCOVER_CROPLAND:
        return None
    return {"parcel_id": parcel_id, "note": note, "lat": round(pt.y, 6), "lon": round(pt.x, 6),
            "source": "ULDK GetParcelByXY (2026-11-21)", "facts": facts}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    picked: list[dict] = []
    for lon, lat, region in CANDIDATES:
        try:
            p = describe(lon, lat, region)
        except Exception as exc:  # noqa: BLE001 - one bad candidate must not stop the run
            print(f"  ERR {region}: {type(exc).__name__}: {exc}")
            continue
        if p and p["parcel_id"] not in {q["parcel_id"] for q in picked}:
            picked.append(p)
    areas = [p["facts"]["area_ha"] for p in picked]
    print(f"\n{len(picked)} parcels; voivodeships={len({p['facts']['voivodeship'] for p in picked})}; "
          f"<1 ha: {sum(a < 1 for a in areas)}; >20 ha: {sum(a > 20 for a in areas)}; "
          f"AR_: {sum(p['facts']['has_ar_sheet'] for p in picked)}")
    if not args.dry_run:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(picked, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"written {OUT.relative_to(BACKEND)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
