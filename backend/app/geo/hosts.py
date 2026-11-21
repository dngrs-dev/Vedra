"""Outbound hosts Part A may contact (SSRF allowlist, imported by app/core/http.py).

Each host is the host of a URL recorded in config/geo_sources.yaml (where its `source:` is cited);
tests/a/test_hosts.py keeps the two in sync. raster_io enforces the same set for GDAL /vsicurl/ reads.
"""

GEO_HOSTS: set[str] = {
    # parcels
    "uldk.gugik.gov.pl",
    # soil map WMS, NMT WCS (GUGiK geoportal)
    "mapy.geoportal.gov.pl",
    # SoilGrids
    "rest.isric.org",
    "files.isric.org",
    # Sentinel-2 STAC + assets, Copernicus DEM
    "earth-search.aws.element84.com",
    "e84-earth-search-sentinel-data.s3.us-west-2.amazonaws.com",
    "sentinel-cogs.s3.us-west-2.amazonaws.com",
    "copernicus-dem-30m.s3.amazonaws.com",
    # hydrology: MPHP (Wody Polskie), OpenStreetMap Overpass
    "wody.isok.gov.pl",
    "overpass-api.de",
    "overpass.kumi.systems",
    # land cover
    "esa-worldcover.s3.eu-central-1.amazonaws.com",
    # EDO
    "drought.emergency.copernicus.eu",
    # IMGW
    "danepubliczne.imgw.pl",
}
