"""Read the evidence thresholds and their references."""
from functools import cache

import yaml

from app.config import CONFIG_DIR


@cache
def load() -> dict:
    with (CONFIG_DIR / "thresholds.yaml").open(encoding="utf-8") as source:
        return yaml.safe_load(source)
