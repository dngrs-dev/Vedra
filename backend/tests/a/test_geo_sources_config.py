"""config/geo_sources.yaml: every source cites where its values come from (Part A rule: no invented data)."""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

import pytest
import yaml

BACKEND = Path(__file__).resolve().parents[2]
CFG = yaml.safe_load((BACKEND / "config" / "geo_sources.yaml").read_text(encoding="utf-8"))
SOURCES = {k: v for k, v in CFG.items() if k != "spike"}
URL_KEYS = ("url", "wms_url", "wcs_url", "synop_url", "warnings_hydro_url", "url_template")


def _urls(entry: dict) -> list[str]:
    urls = [entry[k] for k in URL_KEYS if entry.get(k)]
    return urls + list(entry.get("mirrors") or [])


@pytest.mark.parametrize("name", sorted(SOURCES))
def test_every_source_names_its_origin(name: str) -> None:
    entry = SOURCES[name]
    assert entry.get("name"), f"{name}: missing display name"
    assert entry.get("source"), f"{name}: missing `source:`"


@pytest.mark.parametrize("name", sorted(SOURCES))
def test_urls_are_https(name: str) -> None:
    for url in _urls(SOURCES[name]):
        assert urlparse(url).scheme == "https", f"{name}: {url}"


@pytest.mark.parametrize("name", sorted(n for n, e in SOURCES.items() if e.get("status") != "not_found" and _urls(e)))
def test_licence_status_is_explicit(name: str) -> None:
    entry = SOURCES[name]
    # Either the service-declared licence was recorded, or the entry says the licence is still unverified.
    assert "licence_declared" in entry or "licence_verified" in entry, name


def test_not_found_sources_have_no_url() -> None:
    for name, entry in SOURCES.items():
        if entry.get("status") == "not_found":
            assert not _urls(entry), f"{name}: marked not_found but has a URL"
