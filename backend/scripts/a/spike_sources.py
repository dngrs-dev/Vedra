"""One request per Part A source; prints what came back.

Usage (from backend/):
    python -m scripts.a.spike_sources                 # all sources
    python -m scripts.a.spike_sources uldk soil_map   # selected probes

Every URL, layer and attribute name comes from config/geo_sources.yaml; this script only checks that
they still answer as recorded there. It is a developer tool, not used by the provider.
"""
from __future__ import annotations

import os
import re
import sys
import time
import traceback
from pathlib import Path
from typing import Callable

# A system-wide PostGIS/GDAL install can export PROJ_LIB / GDAL_DATA pointing at an older proj.db
# (seen on the dev machine on 2026-11-21); rasterio/pyproj wheels ship their own data, so drop them.
for _var in ("PROJ_LIB", "GDAL_DATA"):
    os.environ.pop(_var, None)

import httpx  # noqa: E402
import yaml  # noqa: E402
from pyproj import Transformer  # noqa: E402

BACKEND = Path(__file__).resolve().parents[2]
CFG = yaml.safe_load((BACKEND / "config" / "geo_sources.yaml").read_text(encoding="utf-8"))
POINTS: dict[str, list[float]] = CFG["spike"]["points"]
TIMEOUT = float(CFG["spike"]["timeout_s"])
LON, LAT = next(iter(POINTS.values()))
TO_2180 = Transformer.from_crs(4326, 2180, always_xy=True)

client = httpx.Client(timeout=TIMEOUT, follow_redirects=True,
                      headers={"User-Agent": "Vedra/0.1 (HackNation 2026 prototype)"})


def _gdal_env():
    import rasterio

    return rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
                        CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif,.vrt", GDAL_HTTP_MULTIRANGE="YES")


def _sample_cog(href: str, lon: float, lat: float):
    import rasterio
    from rasterio.warp import transform

    with _gdal_env(), rasterio.open("/vsicurl/" + href) as ds:
        xs, ys = transform("EPSG:4326", ds.crs, [lon], [lat])
        value = next(ds.sample([(xs[0], ys[0])]))[0]
        return f"crs={ds.crs} res={tuple(round(r, 6) for r in ds.res)} dtype={ds.dtypes[0]} value={value}"


# ---------------------------------------------------------------- probes (each returns a one-line summary)
def probe_uldk() -> str:
    c = CFG["uldk"]
    xy = c["xy_format"].format(lon=LON, lat=LAT)
    r = client.get(c["url"], params={"request": "GetParcelByXY", "xy": xy, "result": c["result_fields"], "srid": 4326})
    lines = r.text.strip().splitlines()
    rec = lines[1].split("|") if len(lines) > 1 else []
    return f"status_line={lines[0]!r} id={rec[0] if rec else None} fields={len(rec)}"


def probe_soil_map() -> str:
    c = CFG["soil_map"]
    out = []
    for name, (lon, lat) in POINTS.items():
        x, y = TO_2180.transform(lon, lat)
        r = client.get(c["url"], params=dict(
            SERVICE="WMS", VERSION=c["wms_version"], REQUEST="GetFeatureInfo", LAYERS=c["query_layer"],
            QUERY_LAYERS=c["query_layer"], CRS=c["crs"], BBOX=f"{y - 50},{x - 50},{y + 50},{x + 50}",
            WIDTH=101, HEIGHT=101, I=50, J=50, INFO_FORMAT=c["info_format"], STYLES=""))
        attrs = dict(re.findall(r'(\w+)="([^"]*)"', r.text.split("<FIELDS", 1)[1])) if "<FIELDS" in r.text else {}
        a = c["attributes"]
        tex = [attrs.get(k) for k in a["texture_layers"] if attrs.get(k) not in (None, *c["null_values"])]
        out.append(f"{name}: {a['complex']}={attrs.get(a['complex'])} {a['type_subtype']}={attrs.get(a['type_subtype'])} texture={tex}")
    return " | ".join(out)


def probe_soilgrids_rest() -> str:
    c = CFG["soilgrids_rest"]
    params = [("lon", LON), ("lat", LAT)] + [("property", p) for p in c["properties"]] \
        + [("depth", d) for d in c["depths"]] + [("value", v) for v in c["values"]]
    r = client.get(c["url"], params=params)
    r.raise_for_status()
    layers = r.json()["properties"]["layers"]
    d = {L["name"]: (L["unit_measure"]["d_factor"], L["depths"][0]["values"]["Q0.5"]) for L in layers}
    return f"{len(layers)} properties; (d_factor, Q0.5 @0-5cm) = {d}"


def probe_soilgrids_files() -> str:
    c = CFG["soilgrids_files"]
    href = c["url"] + c["path_template"].format(prop="sand", depth="0-5cm", value="Q0.5")
    return _sample_cog(href, LON, LAT)


def probe_earth_search() -> str:
    c = CFG["earth_search"]
    out = []
    for coll in (c["collections"]["primary"], c["collections"]["fallback"]):
        body = {"collections": [coll], "intersects": {"type": "Point", "coordinates": [LON, LAT]},
                "datetime": "2023-05-01T00:00:00Z/2023-05-31T23:59:59Z", "limit": 1}
        r = client.post(c["url"] + "/search", json=body)
        r.raise_for_status()
        j = r.json()
        f = j["features"][0] if j["features"] else None
        bands = f["assets"][c["assets"]["B04"]].get("raster:bands") if f else None
        out.append(f"{coll}: matched={j.get('numberMatched')} first={f and f['id']} B04 raster:bands={bands}")
    return " | ".join(out)


def probe_cog_window() -> str:
    """One COG point read from a Sentinel-2 scene found via STAC (SCL band)."""
    c = CFG["earth_search"]
    body = {"collections": [c["collections"]["primary"]], "intersects": {"type": "Point", "coordinates": [LON, LAT]},
            "datetime": "2023-05-01T00:00:00Z/2023-05-31T23:59:59Z", "limit": 1}
    f = client.post(c["url"] + "/search", json=body).json()["features"][0]
    return f"{f['id']} SCL: " + _sample_cog(f["assets"][c["assets"]["SCL"]]["href"], LON, LAT)


def probe_copernicus_dem() -> str:
    import math

    href = CFG["copernicus_dem"]["url_template"].format(lat=math.floor(LAT), lon=math.floor(LON))
    return _sample_cog(href, LON, LAT)


def probe_gugik_nmt_wcs() -> str:
    c = CFG["gugik_nmt_wcs"]
    r = client.get(c["url"], params=dict(SERVICE="WCS", REQUEST="GetCapabilities"))
    ids = re.findall(r"<wcs:CoverageId>([^<]+)", r.text)
    x, y = TO_2180.transform(LON, LAT)
    t = time.time()
    params = [("SERVICE", "WCS"), ("VERSION", c["wcs_version"]), ("REQUEST", "GetCoverage"),
              ("COVERAGEID", c["coverage_id"]), ("FORMAT", "image/tiff"),
              ("SUBSET", f"x({x - 25:.0f},{x + 25:.0f})"), ("SUBSET", f"y({y - 25:.0f},{y + 25:.0f})")]
    g = client.get(c["url"], params=params)
    return (f"coverages={ids} GetCoverage(50x50 m): {g.status_code} {g.headers.get('content-type')} "
            f"{len(g.content)} B in {time.time() - t:.1f} s")


def probe_mphp() -> str:
    c = CFG["mphp"]
    r = client.get(c["wms_url"], params=dict(SERVICE="WMS", REQUEST="GetCapabilities"))
    names = re.findall(r"<Name>\s*(\d+)\s*</Name>", r.text)
    return f"WMS caps {r.status_code}, {len(names)} numbered layers; expected water layers {list(c['layers'])}"


def probe_overpass() -> str:
    c = CFG["overpass"]
    ww = "|".join(c["tags"]["waterway"])
    q = f'[out:json][timeout:25];way(around:500,{LAT},{LON})[waterway~"^({ww})$"];out tags 50;'
    last = None
    for url in [c["url"], *c.get("mirrors", [])]:
        try:
            r = client.post(url, data={"data": q}, timeout=60)
            r.raise_for_status()
            els = r.json()["elements"]
            return f"{url}: {len(els)} waterways within 500 m: {sorted({e['tags'].get('waterway') for e in els})}"
        except Exception as exc:  # noqa: BLE001 - spike: report and try the next mirror
            last = f"{url}: {type(exc).__name__}"
    raise RuntimeError(f"all Overpass endpoints failed; last {last}")


def probe_worldcover() -> str:
    import math

    c = CFG["worldcover"]
    lat0, lon0 = 3 * math.floor(LAT / 3), 3 * math.floor(LON / 3)
    tile = f"{'N' if lat0 >= 0 else 'S'}{abs(lat0):02d}{'E' if lon0 >= 0 else 'W'}{abs(lon0):03d}"
    return f"tile {tile}: " + _sample_cog(c["url_template"].format(tile=tile), LON, LAT)


def probe_edo() -> str:
    c = CFG["edo"]
    r = client.get(c["wms_url"], params=dict(SERVICE="WMS", REQUEST="GetCapabilities", VERSION=c["wms_version"]))
    found = [n for n in c["layers"] if f"<Name>{n}</Name>" in r.text]
    w = c["wcs"]
    g = client.get(c["wcs_url"], params=[
        ("map", w["map_param"]), ("SERVICE", "WCS"), ("VERSION", w["version"]), ("REQUEST", "GetCoverage"),
        ("coverageID", "cdiad"), ("CRS", "EPSG:4326"), ("format", w["format"]),
        ("SUBSET", f"long({LON - 0.1},{LON + 0.1})")])
    return f"WMS layers present {found}/{list(c['layers'])}; WCS cdiad strip: {g.status_code} {len(g.content)} B"


def probe_imgw() -> str:
    c = CFG["imgw"]
    s = client.get(c["synop_url"]).json()
    w = client.get(c["warnings_hydro_url"]).json()
    missing = [k for k in c["synop_fields"] if k not in s[0]]
    events = sorted({x.get("zdarzenie", "")[:40] for x in w})
    return f"synop: {len(s)} stations, missing fields={missing}; warningshydro: {len(w)} warnings, events={events}"


PROBES: dict[str, Callable[[], str]] = {
    "uldk": probe_uldk,
    "soil_map": probe_soil_map,
    "soilgrids_rest": probe_soilgrids_rest,
    "soilgrids_files": probe_soilgrids_files,
    "earth_search": probe_earth_search,
    "cog_window": probe_cog_window,
    "copernicus_dem": probe_copernicus_dem,
    "gugik_nmt_wcs": probe_gugik_nmt_wcs,
    "mphp": probe_mphp,
    "overpass": probe_overpass,
    "worldcover": probe_worldcover,
    "edo": probe_edo,
    "imgw": probe_imgw,
}


def main(argv: list[str]) -> int:
    names = argv or list(PROBES)
    unknown = [n for n in names if n not in PROBES]
    if unknown:
        print(f"unknown probes {unknown}; available: {list(PROBES)}")
        return 2
    failed = 0
    for name in names:
        t = time.time()
        try:
            summary = PROBES[name]()
            print(f"[ OK ] {name:16} {time.time() - t:6.1f}s  {summary}")
        except Exception as exc:  # noqa: BLE001 - spike: keep going, report everything
            failed += 1
            print(f"[FAIL] {name:16} {time.time() - t:6.1f}s  {type(exc).__name__}: {exc}")
            if os.environ.get("SPIKE_TRACE"):
                traceback.print_exc()
    print(f"\n{len(names) - failed}/{len(names)} sources answered.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
