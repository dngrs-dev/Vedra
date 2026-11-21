"""Resolve references by stable identifier for report recommendations."""
from functools import cache

import yaml

from app.config import CONFIG_DIR
from app.contracts.report import Reference


@cache
def load() -> dict[str, Reference]:
    with (CONFIG_DIR / "references.yaml").open(encoding="utf-8") as source:
        return {key: Reference(id=key, **value) for key, value in yaml.safe_load(source).items()}
