"""Static PNG map for the PDF report: hillshade, parcel, water, flow lines, numbered retention spots.

Drawn in EPSG:2180 (metres) with matplotlib (Agg). Hillshade: standard formula with the conventional light source
azimuth 315 deg, altitude 45 deg - the defaults of GDAL `gdaldem hillshade` (https://gdal.org/programs/gdaldem.html).
Labels are Polish (user-facing).
"""
from __future__ import annotations

import asyncio
import io
import math
import textwrap

import numpy as np
from shapely.geometry import shape

from app.contracts.geo import GeoBundle
from app.contracts.parcel import Parcel
from app.geo import dem as dem_mod
from app.geo import geometry

HILLSHADE_AZIMUTH_DEG = 315.0   # gdaldem hillshade default
HILLSHADE_ALTITUDE_DEG = 45.0   # gdaldem hillshade default
MAP_MARGIN_M = 150              # OUR CHOICE: context around the parcel on the map
DEM_BUDGET_S = 2.0              # CONTRACTS.md: render_static_map <= 3 s; only a preprocessed/cached DEM fits

_KIND_PL = {"depression": "Zagłębienie terenu", "flow_concentration": "Koncentracja spływu",
            "ditch_outlet": "Wylot rowu"}
_KIND_STYLE = {"depression": ("o", "#d95f02"), "flow_concentration": ("v", "#7570b3"), "ditch_outlet": ("s", "#1b9e77")}


def hillshade(z: np.ndarray, res: float, azimuth_deg: float = HILLSHADE_AZIMUTH_DEG,
              altitude_deg: float = HILLSHADE_ALTITUDE_DEG) -> np.ndarray:
    """0..1 shaded relief (row 0 = north)."""
    gy, gx = np.gradient(z, res)
    slope = np.arctan(np.hypot(gx, gy))
    aspect = np.arctan2(-gx, gy)
    az, alt = math.radians(azimuth_deg), math.radians(altitude_deg)
    shaded = np.sin(alt) * np.cos(slope) + np.cos(alt) * np.sin(slope) * np.cos(az - aspect)
    return np.clip(np.nan_to_num(shaded, nan=1.0), 0, 1)


def _nice_length(span_m: float) -> float:
    for v in (10, 20, 50, 100, 200, 250, 500, 1000, 2000, 5000):
        if v >= span_m / 5:
            return float(v)
    return 10_000.0


def _attribution(bundle: GeoBundle) -> str:
    names = []
    for _, res in bundle:
        for p in res.provenance:
            if p.source_id in ("soil_map", "soilgrids_rest", "edo", "imgw", "earth_search"):
                continue  # not drawn on the map
            label = p.attribution_pl or p.name
            if label not in names:
                names.append(label)
    return "Źródła: ULDK GUGiK" + ("; " + "; ".join(names) if names else "")


def render_png(parcel: Parcel, bundle: GeoBundle, width_px: int, dem=None) -> bytes:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    g = geometry.parcel_geom_2180(parcel)
    minx, miny, maxx, maxy = g.buffer(MAP_MARGIN_M).bounds
    aspect = (maxy - miny) / (maxx - minx)
    dpi = 100
    fig = plt.figure(figsize=(width_px / dpi, width_px * min(max(aspect, 0.5), 1.5) / dpi), dpi=dpi)
    ax = fig.add_axes((0, 0.07, 1, 0.93))
    ax.set_xlim(minx, maxx)
    ax.set_ylim(miny, maxy)
    ax.set_aspect("equal")
    ax.set_axis_off()
    if dem is not None:
        hs = hillshade(dem.z, dem.res)
        h, w = hs.shape
        ax.imshow(hs, cmap="gray", vmin=0, vmax=1, alpha=0.6, interpolation="bilinear",
                  extent=(dem.origin[0], dem.origin[0] + w * dem.res, dem.origin[1] - h * dem.res, dem.origin[1]))
    else:
        ax.set_facecolor("#f4f1ea")

    def draw(geom4326, **kw):
        g2180 = geometry.to_2180(shape(geom4326))
        for part in getattr(g2180, "geoms", [g2180]):
            if part.geom_type == "Polygon":
                ax.fill(*part.exterior.xy, **kw)
            elif part.geom_type == "LineString":
                ax.plot(*part.xy, **{k: v for k, v in kw.items() if k not in ("facecolor", "edgecolor")})
            elif part.geom_type == "Point":
                ax.plot(part.x, part.y, **kw)

    if bundle.hydro.data:
        for f in bundle.hydro.data.features:
            draw(f.geometry, facecolor="#2b8cbe", edgecolor="#2b8cbe", color="#2b8cbe", linewidth=1.5, zorder=3)
    if bundle.terrain.data:
        for fl in bundle.terrain.data.flow_lines:
            lw = 0.8 + min(fl.upstream_area_ha, 50) / 15
            draw(fl.geometry, color="#08519c", linewidth=lw, linestyle="--", alpha=0.8, zorder=4)
        for s in bundle.terrain.data.retention_spots:
            marker, colour = _KIND_STYLE[s.kind]
            geom = geometry.to_2180(shape(s.geometry))
            if geom.geom_type in ("Polygon", "MultiPolygon"):
                draw(s.geometry, facecolor=colour, edgecolor=colour, alpha=0.35, zorder=5)
            p = geom.representative_point()
            ax.plot(p.x, p.y, marker=marker, color=colour, markersize=9, markeredgecolor="white", zorder=6)
            ax.annotate(s.id, (p.x, p.y), xytext=(6, 6), textcoords="offset points", fontsize=9, weight="bold",
                        color="black", zorder=7, bbox=dict(boxstyle="round,pad=0.15", fc="white", alpha=0.8, lw=0))
    for part in getattr(g, "geoms", [g]):
        ax.plot(*part.exterior.xy, color="#e31a1c", linewidth=2.5, zorder=8)

    # scale bar and north arrow (EPSG:2180 grid north; convergence in Poland is a few degrees at most)
    span = maxx - minx
    bar = _nice_length(span)
    x0, y0 = minx + span * 0.05, miny + (maxy - miny) * 0.05
    ax.plot([x0, x0 + bar], [y0, y0], color="black", linewidth=4, solid_capstyle="butt", zorder=9)
    ax.text(x0 + bar / 2, y0 + (maxy - miny) * 0.015, f"{bar:g} m", ha="center", va="bottom", fontsize=9, zorder=9)
    ax.annotate("N", xy=(0.95, 0.95), xytext=(0.95, 0.85), xycoords="axes fraction", ha="center", fontsize=12,
                weight="bold", arrowprops=dict(arrowstyle="-|>", color="black", lw=2), zorder=9)

    handles = [Line2D([], [], color="#e31a1c", lw=2.5, label="Granica działki")]
    if bundle.hydro.data and bundle.hydro.data.features:
        handles.append(Line2D([], [], color="#2b8cbe", lw=2, label="Cieki, rowy i wody"))
    if bundle.terrain.data and bundle.terrain.data.flow_lines:
        handles.append(Line2D([], [], color="#08519c", lw=1.5, ls="--", label="Linie spływu wody"))
    for kind, (marker, colour) in _KIND_STYLE.items():
        if bundle.terrain.data and any(s.kind == kind for s in bundle.terrain.data.retention_spots):
            handles.append(Line2D([], [], marker=marker, color=colour, lw=0, markersize=8, label=_KIND_PL[kind]))
    ax.legend(handles=handles, loc="upper left", fontsize=8, framealpha=0.85)
    caption = f"Działka {parcel.parcel_id}. {_attribution(bundle)}"
    # ~5.3 px per character at 7 pt / 100 dpi (DejaVu Sans) -> wrap to the image width
    fig.text(0.01, 0.005, textwrap.fill(caption, width=max(int(width_px / 5.3), 40)), fontsize=7, ha="left",
             va="bottom")
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi)
    plt.close(fig)
    return buf.getvalue()


async def render(parcel: Parcel, bundle: GeoBundle, width_px: int = 1200) -> bytes:
    try:
        dem, _ = await asyncio.wait_for(dem_mod.fetch_dem(parcel, DEM_BUDGET_S), timeout=DEM_BUDGET_S + 0.2)
    except Exception:  # noqa: BLE001 - map without relief background
        dem = None
    return await asyncio.to_thread(render_png, parcel, bundle, width_px, dem)
