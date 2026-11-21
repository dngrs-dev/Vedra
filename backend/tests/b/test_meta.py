from pathlib import Path
from unittest.mock import AsyncMock

from fastapi import status
from fastapi.testclient import TestClient

from app.api import routes_meta
from app.config import settings
from app.core import http
from app.main import app
from app.recommendations.texts_pl import CROP_CATALOG_UNAVAILABLE


def test_health_and_http_lifespan(monkeypatch):
    close = AsyncMock()
    monkeypatch.setattr(http, "close", close)

    with TestClient(app) as client:
        response = client.get("/api/health", headers={"Origin": settings.allowed_origins[0]})
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"status": "ok", "geo_provider": settings.geo_provider}
        assert response.headers["access-control-allow-origin"] == settings.allowed_origins[0]
        assert response.headers["x-content-type-options"] == "nosniff"
        close.assert_not_awaited()

    close.assert_awaited_once()


def test_crops_exposes_only_catalog_fields(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(routes_meta, "CONFIG_DIR", tmp_path)
    # The test fixture uses the plain Polish name for a wheat crop, with a sentinel private field.
    (tmp_path / "crops.yaml").write_text(
        'crops:\n  wheat:\n    name_pl: "Pszenica"\n    source: "test fixture"\n', encoding="utf-8"
    )

    with TestClient(app) as client:
        assert client.get("/api/crops").json() == [{"code": "wheat", "name_pl": "Pszenica"}]


def test_crops_reports_missing_catalog(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(routes_meta, "CONFIG_DIR", tmp_path)

    with TestClient(app) as client:
        response = client.get("/api/crops")

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert response.json() == {"detail": CROP_CATALOG_UNAVAILABLE}
