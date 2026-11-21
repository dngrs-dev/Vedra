"""Part A - data & geo. Public entry point: RealGeoProvider.

Exported lazily: app.core.http imports app.geo.hosts, and an eager import of the provider here would make
that import pull in modules which themselves import app.core.http (circular import).
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.geo.provider import RealGeoProvider

__all__ = ["RealGeoProvider"]


def __getattr__(name: str) -> Any:
    if name == "RealGeoProvider":
        from app.geo.provider import RealGeoProvider

        return RealGeoProvider
    raise AttributeError(name)
