"""Mapa glebowo-rolnicza (GUGiK WMS) GetFeatureInfo.

Layer, format and attribute names come from config/geo_sources.yaml `soil_map` (spike 2026-11-21).
The IUNG «Podatność gleb na susze» WMS named in PART_A_DATA_GEO.md as a fallback has no public URL that we
could find (geo_sources.yaml `iung_drought_susceptibility_wms.status: not_found`), so it is not queried.
"""
from __future__ import annotations

import asyncio
import re
from collections import Counter
from dataclasses import dataclass, field

from app.contracts.parcel import Parcel
from app.core import cache, http
from app.geo import geometry
from app.geo.sources import source, soil_categories

_ATTR_RE = re.compile(r'(\w+)="([^"]*)"')


@dataclass
class SoilMapHit:
    texture_layers: list[str] = field(default_factory=list)   # PODLOZE1..5 (top first)
    alluvial_texture: list[str] = field(default_factory=list)  # GATUNEKMADY1..5
    rendzina_texture: list[str] = field(default_factory=list)  # GATUNEKREDZINY1..5
    organic_kind: list[str] = field(default_factory=list)      # RODZAJGLEBYORGANICZNEJ1..5
    complex: str | None = None                                  # KOMPLEKS
    type_subtype: str | None = None                             # TYPPODTYP
    source_map: str | None = None                               # ZRODLO
    currency_date: str | None = None                            # AKTUALNOSC_NR (ISO date)

    @property
    def primary_code(self) -> str | None:
        """Surface texture code used for the KBW category (our choice, see config/soil_categories.yaml)."""
        for seq in (self.texture_layers, self.alluvial_texture, self.rendzina_texture):
            if seq:
                return seq[0]
        return None


@dataclass
class DominantSoil:
    hit: SoilMapHit
    code: str | None
    share: float          # share of sampled points with the majority code
    points_with_data: int
    points_sampled: int


def parse_feature_info(xml: str) -> SoilMapHit | None:
    """Parses the ESRI FeatureInfoResponse (<FIELDS a="..." .../>). None when no feature."""
    if "<FIELDS" not in xml:
        return None
    attrs = dict(_ATTR_RE.findall(xml.split("<FIELDS", 1)[1].split(">", 1)[0]))
    cfg = source("soil_map")
    a, nulls = cfg["attributes"], set(cfg["null_values"])

    def one(key: str) -> str | None:
        v = attrs.get(a[key])
        return None if v in (None, *nulls) or not v.strip() else v.strip()

    def many(key: str) -> list[str]:
        return [attrs[k].strip() for k in a[key] if attrs.get(k) not in (None, *nulls) and attrs[k].strip()]

    return SoilMapHit(
        texture_layers=many("texture_layers"),
        alluvial_texture=many("alluvial_texture"),
        rendzina_texture=many("rendzina_texture"),
        organic_kind=many("organic_kind"),
        complex=one("complex"),
        type_subtype=one("type_subtype"),
        source_map=one("source_map"),
        currency_date=one("currency_date"),
    )


async def soil_type_at_2180(x: float, y: float) -> SoilMapHit | None:
    cfg = source("soil_map")
    # WMS 1.3.0 with EPSG:2180: BBOX axis order is (northing, easting) - see geo_sources.yaml
    params = dict(SERVICE="WMS", VERSION=cfg["wms_version"], REQUEST="GetFeatureInfo",
                  LAYERS=cfg["query_layer"], QUERY_LAYERS=cfg["query_layer"], CRS=cfg["crs"],
                  BBOX=f"{y - 50},{x - 50},{y + 50},{x + 50}", WIDTH="101", HEIGHT="101", I="50", J="50",
                  INFO_FORMAT=cfg["info_format"], STYLES="")
    key = cache.make_key("geo.soilmap", x=round(x, 1), y=round(y, 1))
    xml = cache.get(key)
    if xml is None:
        resp = await http.get(cfg["url"], params=params, timeout=8.0)
        xml = resp.content.decode("utf-8", errors="replace")  # service answers UTF-8 (spike)
        cache.set(key, xml, expire_s=30 * 24 * 3600)  # map updates are rare; refresh monthly (our choice)
    return parse_feature_info(xml)


async def soil_type_at(lat: float, lon: float) -> SoilMapHit | None:
    x, y = geometry.lonlat_to_2180(lon, lat)
    return await soil_type_at_2180(x, y)


async def dominant_soil_type(parcel: Parcel) -> DominantSoil | None:
    """Majority vote of the surface texture code over sample points inside the parcel."""
    n = int(soil_categories()["soil_map_sample_points"])
    pts = geometry.sample_points(geometry.parcel_geom_2180(parcel), n)
    results = await asyncio.gather(*(soil_type_at_2180(p.x, p.y) for p in pts), return_exceptions=True)
    hits = [r for r in results if isinstance(r, SoilMapHit)]
    if not hits:
        errors = [r for r in results if isinstance(r, BaseException)]
        if errors and len(errors) == len(results):
            raise errors[0]
        return None
    votes = Counter(h.primary_code for h in hits)
    code, count = votes.most_common(1)[0]
    hit = next(h for h in hits if h.primary_code == code)
    return DominantSoil(hit=hit, code=code, share=count / len(pts), points_with_data=len(hits),
                        points_sampled=len(pts))
