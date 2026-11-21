"""Shared utilities for the two offline geo providers."""
from __future__ import annotations

import re
from io import BytesIO

from app.contracts.common import SourceResult, SourceStatus
from app.contracts.errors import InvalidParcelQuery
from app.contracts.geo import GeoBundle
from app.contracts.parcel import Parcel
from app.recommendations.texts_pl import PARCEL_OUTLINE_TITLE

# The full ID and region/number formats are described in docs/PART_A_DATA_GEO.md.
PARCEL_ID = re.compile(r"\d{6}_\d\.\d{4}\.(?:AR_\d+\.)?[0-9A-Za-z/]+", re.IGNORECASE)
REGION_AND_NUMBER = re.compile(r".+\s+[0-9][0-9A-Za-z/]*")


def validate_point(lat: float, lon: float) -> None:
    # WGS84 latitude and longitude limits (RFC 7946 §3.1.1 and §5.3).
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise InvalidParcelQuery("Coordinates outside WGS84 bounds")


def parse_query(query: str) -> str | tuple[float, float]:
    query = " ".join(query.split())
    if "," in query:
        try:
            lat, lon = map(float, query.split(","))
        except ValueError as exc:
            raise InvalidParcelQuery("Expected a latitude and longitude") from exc
        validate_point(lat, lon)
        return lat, lon
    if PARCEL_ID.fullmatch(query) or REGION_AND_NUMBER.fullmatch(query):
        return query
    raise InvalidParcelQuery("Expected a parcel ID, a region and number, or coordinates")


def bundle_with_missing_sources(note_pl: str, error: str | None = None, **sources: SourceResult) -> GeoBundle:
    missing = {"status": SourceStatus.MISSING, "notes_pl": [note_pl], "error": error}
    return GeoBundle.model_validate({name: sources.get(name, missing) for name in GeoBundle.model_fields})


def render_parcel_outline(parcel: Parcel, width_px: int) -> bytes:
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure
    from shapely import from_wkt

    polygon = from_wkt(parcel.geometry_2180_wkt)
    parts = polygon.geoms if polygon.geom_type == "MultiPolygon" else (polygon,)
    figure = Figure(layout="tight")
    figure.set_size_inches(width_px / figure.dpi, width_px / figure.dpi)
    axis = figure.subplots()
    for part in parts:
        axis.plot(*part.exterior.xy, color="black")
        for ring in part.interiors:
            axis.plot(*ring.xy, color="black")
    axis.set_aspect("equal")
    axis.set_axis_off()
    axis.set_title(PARCEL_OUTLINE_TITLE)
    output = BytesIO()
    FigureCanvasAgg(figure).print_png(output)
    return output.getvalue()
