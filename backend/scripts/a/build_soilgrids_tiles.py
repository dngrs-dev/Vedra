"""Build data/a/soilgrids_tiles.json: the SoilGrids 2.0 tile index for Poland (+ data/a/manifest.json).

Usage (from backend/): python -m scripts.a.build_soilgrids_tiles

Every SoilGrids layer on files.isric.org is a ~6 MB VRT listing ~13 000 GeoTIFF tiles of 450 x 450 px (250 m,
Interrupted Goode Homolosine). Opening the VRT per point read is too slow. The tiling differs between properties
(2026-11-21: tileSG-006-049_2-4 exists for sand but not for bdod) but not between depths / quantiles of one property,
so the index of the tiles covering Poland is stored once per property and app/geo/soilgrids_files.py reads single
pixels straight from the tiles. For each property the layout is checked against a second depth / quantile.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone

import httpx
from pyproj import Transformer

from app.geo.sources import DATA_DIR, source

OUT = DATA_DIR / "soilgrids_tiles.json"
MANIFEST = DATA_DIR / "manifest.json"
POLAND_BBOX = (14.0, 48.9, 24.2, 54.95)   # lon/lat envelope of Poland with a margin (our choice)
PROPERTIES = ("sand", "silt", "clay", "soc", "bdod")   # = app.geo.soilgrids_files.PROPERTIES
REFERENCE = ("0-5cm", "Q0.5")
CHECK = ("100-200cm", "Q0.95")

_SRC_RE = re.compile(r'<SourceFilename relativeToVRT="1">\./[^/]+/([^<]+)\.tif</SourceFilename>.*?'
                     r'<DstRect xOff="(\d+)" yOff="(\d+)" xSize="(\d+)" ySize="(\d+)"', re.S)


def vrt_url(prop: str, depth: str, value: str) -> str:
    return source("soilgrids_files")["url"] + f"{prop}/{prop}_{depth}_{value}.vrt"


def fetch(c: httpx.Client, url: str, tries: int = 3) -> str:
    for i in range(tries):
        try:
            return c.get(url).text
        except httpx.HTTPError:          # files.isric.org sometimes cuts the 6 MB body (2026-11-21)
            if i == tries - 1:
                raise
    raise AssertionError


def parse(text: str) -> tuple[list[float], str, list[tuple[str, int, int, int, int]]]:
    gt = [float(v) for v in re.search(r"<GeoTransform>([^<]+)</GeoTransform>", text).group(1).split(",")]
    srs = re.search(r"<SRS[^>]*>([^<]+)</SRS>", text).group(1)
    tiles = [(m.group(1), *(int(m.group(i)) for i in range(2, 6))) for m in _SRC_RE.finditer(text)]
    return gt, srs, tiles


def poland_window(gt: list[float], srs: str) -> tuple[int, int, int, int]:
    """Pixel window (col0, row0, col1, row1) of the Poland envelope in the VRT grid."""
    tr = Transformer.from_crs("EPSG:4326", srs, always_xy=True)
    lo0, la0, lo1, la1 = POLAND_BBOX
    pts = [(lo0 + (lo1 - lo0) * i / 20, la0 + (la1 - la0) * j / 20) for i in range(21) for j in range(21)]
    xs, ys = tr.transform([p[0] for p in pts], [p[1] for p in pts])
    cols = [(x - gt[0]) / gt[1] for x in xs]
    rows = [(y - gt[3]) / gt[5] for y in ys]
    return int(min(cols)), int(min(rows)), int(max(cols)) + 1, int(max(rows)) + 1


def projected(gt: list[float], tiles) -> dict[str, tuple[float, float, int, int]]:
    """tile path -> (x_left, y_top, width_px, height_px) in metres; the VRT origins differ between layers by a few
    pixels (sand vs soc: -19949750 vs -19949000), the tiles' own georeferencing does not."""
    return {t[0]: (gt[0] + t[1] * gt[1], gt[3] + t[2] * gt[5], t[3], t[4]) for t in tiles}


def property_index(c: httpx.Client, prop: str) -> tuple[str, float, dict[str, tuple[float, float, int, int]]]:
    gt, srs, tiles = parse(fetch(c, vrt_url(prop, *REFERENCE)))
    gt2, _, check_tiles = parse(fetch(c, vrt_url(prop, *CHECK)))
    c0, r0, c1, r1 = poland_window(gt, srs)
    names = {t[0] for t in tiles if t[1] < c1 and t[1] + t[3] > c0 and t[2] < r1 and t[2] + t[4] > r0}
    # t[0] is the tile path below the layer folder, e.g. "tileSG-018-027/tileSG-018-027_2-4"
    ref = {k: v for k, v in projected(gt, tiles).items() if k in names}
    chk = {k: v for k, v in projected(gt2, check_tiles).items() if k in ref}
    # Same tiles, same columns. Edge tiles may be cropped to a different height per layer (2026-11-21:
    # tileSG-005-049_4-3, 308 vs 304 rows), so the reader takes the pixel from each tile's own georeferencing and
    # uses this index only to pick the tile.
    if set(ref) != set(chk) or any(ref[k][0] != chk[k][0] or ref[k][2] != chk[k][2] for k in ref):
        raise SystemExit(f"{prop}: tile layout differs between {REFERENCE} and {CHECK}")
    cropped = [k for k in ref if ref[k] != chk[k]]
    print(f"{prop}: {len(ref)} tiles of {len(tiles)}" + (f"; edge tiles cropped differently: {cropped}" if cropped else ""))
    return srs, gt[1], ref


def main() -> int:
    out: dict = {"tiles": {}}
    with httpx.Client(timeout=120, follow_redirects=True) as c:
        for prop in PROPERTIES:
            srs, res, ref = property_index(c, prop)
            out.update(crs_wkt=srs, res_m=res)
            out["tiles"][prop] = [[k, *v] for k, v in sorted(ref.items())]
    OUT.write_text(json.dumps(out) + "\n", encoding="utf-8")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {}
    manifest["soilgrids_tiles.json"] = {
        "url": source("soilgrids_files")["url"] + "{prop}/{prop}_0-5cm_Q0.5.vrt for " + ", ".join(PROPERTIES)
               + " (layout checked against {prop}_100-200cm_Q0.95.vrt)",
        "downloaded": datetime.now(timezone.utc).date().isoformat(),
        "licence": source("soilgrids_files")["licence"],
        "content": f"per property, the SoilGrids 2.0 tiles (450 x 450 px, 250 m, Homolosine) covering lon/lat "
                   f"{POLAND_BBOX}: tile path, projected origin (m) and size (px)",
        "script": "scripts/a/build_soilgrids_tiles.py",
    }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"-> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
