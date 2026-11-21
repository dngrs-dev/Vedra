"""GEO_HOSTS == hosts of the URLs in config/geo_sources.yaml (no missing host, no unexplained extra)."""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

import yaml

from app.geo.hosts import GEO_HOSTS

BACKEND = Path(__file__).resolve().parents[2]
CFG = yaml.safe_load((BACKEND / "config" / "geo_sources.yaml").read_text(encoding="utf-8"))
URL_KEYS = ("url", "wms_url", "wcs_url", "synop_url", "warnings_hydro_url", "url_template")


def _config_hosts() -> set[str]:
    hosts = set()
    for name, entry in CFG.items():
        if name == "spike":
            continue
        urls = [entry[k] for k in URL_KEYS if entry.get(k)]
        urls += list(entry.get("mirrors") or []) + list(entry.get("asset_hosts") or [])
        hosts |= {urlparse(u).hostname for u in urls}
    return hosts


def test_allowlist_matches_config() -> None:
    cfg = _config_hosts()
    assert cfg - GEO_HOSTS == set(), "hosts used in config but not allowed"
    assert GEO_HOSTS - cfg == set(), "allowed hosts not backed by a config entry"


def test_core_http_sees_geo_hosts() -> None:
    from app.core.http import allowed_hosts

    assert GEO_HOSTS <= allowed_hosts()
