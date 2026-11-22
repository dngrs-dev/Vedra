"""Draw the reported locations on printable maps without a network tile service."""
from __future__ import annotations

from io import BytesIO, StringIO
from math import cos, pi, sin

import numpy as np
from pyproj import Transformer
from shapely import transform
from shapely.errors import ShapelyError
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry

from app.reports.recommendation_groups import Site

# The report contract uses WGS84 and the Polish national plane EPSG:2180.
_PROJECT = Transformer.from_crs(4326, 2180, always_xy=True)


def _geometry(data: dict) -> BaseGeometry | None:
    try:
        geometry = shape(data)
        if geometry.is_empty or not geometry.is_valid:
            return None
        west, south, east, north = geometry.bounds
        if -180 <= west <= east <= 180 and -90 <= south <= north <= 90:
            return geometry
    except (AttributeError, KeyError, ShapelyError, TypeError, ValueError):
        pass
    return None


def _outline(axis, geometry: BaseGeometry, color: str) -> None:
    if geometry.geom_type == "Polygon":
        for ring in [geometry.exterior, *geometry.interiors]:
            axis.plot(*ring.xy, color=color, linewidth=1)
    elif geometry.geom_type == "LineString":
        axis.plot(*geometry.xy, color=color, linewidth=1)
    elif hasattr(geometry, "geoms"):
        for part in geometry.geoms:
            _outline(axis, part, color)


def _project(geometry: BaseGeometry) -> BaseGeometry:
    return transform(geometry, lambda coordinates: np.column_stack(_PROJECT.transform(*coordinates.T)))


def _label_sites(figure, axis, points: list[tuple[int, float, float]]) -> None:
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.transforms import Bbox

    # Work in typographic points so adjacent labels can move without changing the mapped positions.
    FigureCanvasAgg(figure).draw()
    anchors = [axis.transData.transform((x, y)) for _, x, y in points]
    occupied = [Bbox.from_bounds(x - 2, y - 2, 4, 4) for x, y in anchors]
    for (number, x, y), (left, bottom) in zip(points, anchors):
        width = len(str(number)) * 6 + 2
        offsets = (
            (radius * cos(direction * pi / 4), radius * sin(direction * pi / 4))
            for radius in (8, 15, 23, 32, 42, 54) for direction in range(8)
        )
        offset = (4.0, 6.0)
        for dx, dy in offsets:
            label = Bbox.from_bounds(left + dx - width / 2, bottom + dy - 6, width, 12)
            if (figure.bbox.contains(label.x0, label.y0) and figure.bbox.contains(label.x1, label.y1)
                    and not any(label.overlaps(other) for other in occupied)):
                occupied.append(label)
                offset = (dx, dy)
                break
        label = axis.annotate(str(number), (x, y), xytext=offset, textcoords="offset points",
                              ha="center", va="center", fontsize=9, color="#713917", annotation_clip=False,
                              bbox={"facecolor": "white", "edgecolor": "none", "pad": .4},
                              arrowprops={"arrowstyle": "-", "color": "#a35528", "linewidth": .55})
        label.set_in_layout(False)


# Raster resolution for the built-in renderer, which embeds the map as an image (as charts.PNG_DPI).
PNG_DPI = 200


def _figure(parcel_geojson: dict, sites: list[Site]):
    """The site map figure and "lat, lon" per drawn site, or (None, {}) when no site has a usable geometry."""
    locations = [(site.number, _geometry(site.geometry)) for site in sites]
    locations = [(number, geometry) for number, geometry in locations if geometry is not None]
    if not locations:
        return None, {}

    from matplotlib.figure import Figure

    # Match the A4 chart column and leave room for a site table below the map.
    figure = Figure(figsize=(6.2, 2.6), dpi=72, layout="constrained")
    axis = figure.subplots()
    axis.set_aspect("equal")
    axis.set_axis_off()
    parcel = _geometry(parcel_geojson)
    if parcel is not None:
        _outline(axis, _project(parcel), "#28776d")

    coordinates = {}
    points = []
    for number, geometry in locations:
        _outline(axis, _project(geometry), "#a35528")
        point = geometry.representative_point()
        x, y = _PROJECT.transform(point.x, point.y)
        axis.scatter(x, y, color="#a35528", s=9)
        points.append((number, x, y))
        # Geographic coordinates use the same display precision as GUGiK's parcel lookup.
        coordinates[number] = f"{point.y:.6f}, {point.x:.6f}"

    _label_sites(figure, axis, points)
    return figure, coordinates


def render(parcel_geojson: dict, sites: list[Site]) -> tuple[str | None, dict[int, str]]:
    """SVG site map for the HTML report (WeasyPrint)."""
    figure, coordinates = _figure(parcel_geojson, sites)
    if figure is None:
        return None, {}
    from matplotlib.backends.backend_svg import FigureCanvasSVG

    output = StringIO()
    FigureCanvasSVG(figure).print_svg(output)
    return output.getvalue(), coordinates


def render_png(parcel_geojson: dict, sites: list[Site]) -> tuple[bytes | None, dict[int, str]]:
    """The same map as PNG, for the built-in matplotlib PDF renderer (pdf_basic)."""
    figure, coordinates = _figure(parcel_geojson, sites)
    if figure is None:
        return None, {}
    from matplotlib.backends.backend_agg import FigureCanvasAgg

    output = BytesIO()
    FigureCanvasAgg(figure)
    figure.savefig(output, format="png", dpi=PNG_DPI)
    return output.getvalue(), coordinates
