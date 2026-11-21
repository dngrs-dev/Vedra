"""Part A test setup: make `app` and `scripts` importable when running `pytest tests/a` from backend/."""
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
