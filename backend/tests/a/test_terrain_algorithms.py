"""terrain.py algorithms on synthetic grids (PART_A_DATA_GEO.md CP3: bowl with known volume; flat plane)."""
from __future__ import annotations

import numpy as np
import pytest

from app.geo import terrain


def bowl(n=41, res=1.0, depth=2.0, radius=15.0, base=100.0) -> np.ndarray:
    """Plane at `base` with a paraboloid pit of given depth and radius (closed rim)."""
    y, x = np.mgrid[0:n, 0:n] * res
    c = (n - 1) * res / 2
    r2 = (x - c) ** 2 + (y - c) ** 2
    pit = np.where(r2 < radius ** 2, depth * (1 - r2 / radius ** 2), 0.0)
    return base - pit


def test_bowl_volume_matches_analytic():
    res, depth, radius = 1.0, 2.0, 15.0
    z = bowl(res=res, depth=depth, radius=radius)
    filled = terrain.priority_flood(z)
    deps = terrain.depressions(z, filled, res, min_area_m2=10)
    assert len(deps) == 1
    # paraboloid volume = pi * R^2 * h / 2
    assert deps[0].volume_m3 == pytest.approx(np.pi * radius ** 2 * depth / 2, rel=0.03)
    assert deps[0].max_depth_m == pytest.approx(depth, abs=0.01)
    assert deps[0].area_m2 == pytest.approx(np.pi * radius ** 2, rel=0.05)
    assert deps[0].deepest == (20, 20)


def test_flat_plane_has_no_depressions():
    z = np.full((30, 30), 100.0)
    assert terrain.depressions(z, terrain.priority_flood(z), 1.0, min_area_m2=1) == []


def test_tilted_plane_no_depressions_and_slope():
    y, x = np.mgrid[0:20, 0:20].astype(float)
    z = 100 + 0.05 * x                      # 5 % slope, rising east
    assert terrain.depressions(z, terrain.priority_flood(z), 1.0, min_area_m2=1) == []
    assert np.allclose(terrain.slope_pct(z, 1.0), 5.0)


def test_min_area_filters_small_pits():
    z = np.full((20, 20), 10.0)
    z[5, 5] = 9.0                           # 1 cell pit
    deps = terrain.depressions(z, terrain.priority_flood(z), 2.0, min_area_m2=5)
    assert deps == []                       # 4 m2 < 5 m2
    assert len(terrain.depressions(z, terrain.priority_flood(z), 2.0, min_area_m2=4)) == 1


def test_epsilon_fill_drains_everything_and_accumulates_to_outlet():
    z = bowl(n=21, radius=6.0)
    z[10, 0] = 90.0                         # outlet on the west edge
    fe = terrain.priority_flood(z, epsilon=1e-4)
    dirs = terrain.d8(fe)
    interior = np.zeros_like(dirs, bool)
    interior[1:-1, 1:-1] = True
    assert (dirs[interior] >= 0).all()      # every interior cell drains somewhere
    acc = terrain.flow_accumulation(dirs, fe)
    assert acc.max() <= z.size and acc.min() >= 1


def test_trace_lines_follow_valley():
    y, x = np.mgrid[0:30, 0:30].astype(float)
    z = 100 - 0.05 * y + 0.2 * np.abs(x - 15)   # V-shaped valley along column 15 (sides steeper than floor)
    fe = terrain.priority_flood(z, epsilon=1e-4)
    dirs = terrain.d8(fe)
    acc = terrain.flow_accumulation(dirs, fe)
    lines = terrain.trace_lines(acc, dirs, 1.0, min_upstream_ha=0.002)   # 20 cells
    assert lines
    valley = max(lines, key=lambda ln: acc[ln[-1]])        # the line carrying the most water
    assert all(abs(c - 15) <= 1 for _, c in valley[len(valley) // 2:])
    assert valley[-1][0] >= 28


def test_twi_higher_in_valley():
    y, x = np.mgrid[0:30, 0:30].astype(float)
    z = 100 - 0.05 * y + 0.2 * np.abs(x - 15)
    fe = terrain.priority_flood(z, epsilon=1e-4)
    dirs = terrain.d8(fe)
    acc = terrain.flow_accumulation(dirs, fe)
    t = terrain.twi(acc, terrain.slope_pct(z, 1.0), 1.0)
    assert np.nanmean(t[25:28, 15]) > np.nanmean(t[25:28, 3])
