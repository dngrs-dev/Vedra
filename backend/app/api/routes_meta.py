"""Backend health and crop catalog endpoints."""
from __future__ import annotations

import yaml
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.config import CONFIG_DIR, settings
from app.recommendations.texts_pl import CROP_CATALOG_UNAVAILABLE, CROPS_SUMMARY, HEALTH_SUMMARY

router = APIRouter(prefix="/api")


class CropListItem(BaseModel):
    code: str
    name_pl: str


@router.get("/health", summary=HEALTH_SUMMARY)
def health() -> dict[str, str]:
    return {"status": "ok", "geo_provider": settings.geo_provider}


@router.get("/crops", summary=CROPS_SUMMARY)
def crops() -> list[CropListItem]:
    try:
        with (CONFIG_DIR / "crops.yaml").open(encoding="utf-8") as config:
            catalog = yaml.safe_load(config)["crops"]
    except FileNotFoundError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, CROP_CATALOG_UNAVAILABLE) from exc

    return [CropListItem(code=code, name_pl=crop["name_pl"]) for code, crop in catalog.items()]
