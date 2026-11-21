import pytest

from app.config import settings


@pytest.fixture(autouse=True)
def isolated_report_database(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "db_path", tmp_path / "vedra.sqlite")
