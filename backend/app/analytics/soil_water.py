"""Root-zone water capacity and an organic-matter sensitivity scenario."""
from __future__ import annotations

from dataclasses import dataclass

from app.contracts.common import Range
from app.contracts.geo import SoilLayer

# SI conversions: a centimetre contains 10 mm, and a mass percent equals 10 g/kg.
MM_PER_CM = 10
GRAMS_PER_KG_PER_PERCENT = 10
# Conventional Van Bemmelen SOC-to-SOM conversion, reviewed by Pribyl (2010).
# https://doi.org/10.1016/j.geoderma.2010.02.003
SOC_TO_SOM = 1.724


@dataclass(frozen=True, slots=True)
class RootLayer:
    top_cm: float
    bottom_cm: float
    fc: Range
    wp: Range


def _texture(layer: SoilLayer) -> tuple[float, float, float] | None:
    if layer.sand_pct is None or layer.clay_pct is None or layer.soc_g_kg is None:
        return None
    sand = layer.sand_pct.mid / 100  # Mass percentages to fractions.
    clay = layer.clay_pct.mid / 100
    som = layer.soc_g_kg.mid / GRAMS_PER_KG_PER_PERCENT * SOC_TO_SOM
    if min(sand, clay, som) < 0 or sand + clay > 1:
        return None
    return sand, clay, som


def _saxton_rawls(sand: float, clay: float, som: float) -> tuple[float, float]:
    # Saxton & Rawls (2006), table 1, equations (1) and (2), θ at 1500 and 33 kPa.
    # https://doi.org/10.2136/sssaj2005.0117
    wp_t = -0.024 * sand + 0.487 * clay + 0.006 * som + 0.005 * sand * som - 0.013 * clay * som + 0.068 * sand * clay + 0.031
    fc_t = -0.251 * sand + 0.195 * clay + 0.011 * som + 0.006 * sand * som - 0.027 * clay * som + 0.452 * sand * clay + 0.299
    return fc_t + (1.283 * fc_t**2 - 0.374 * fc_t - 0.015), wp_t + (0.14 * wp_t - 0.02)


def _depth_segments(layers: list[SoilLayer], zr_cm: float):
    if zr_cm <= 0:
        return None
    segments = []
    covered = 0.0
    for layer in sorted(layers, key=lambda item: (item.top_cm, item.bottom_cm)):
        if layer.bottom_cm <= covered:
            continue
        if layer.top_cm > covered:
            return None
        bottom = min(zr_cm, layer.bottom_cm)
        segments.append((layer, covered, bottom))
        covered = bottom
        if covered == zr_cm:
            return segments
    return None


def root_profile(layers: list[SoilLayer], zr_cm: float) -> tuple[RootLayer, ...] | None:
    segments = _depth_segments(layers, zr_cm)
    if segments is None:
        return None
    result = []
    for layer, top, bottom in segments:
        fc, wp = layer.theta_fc, layer.theta_wp
        if fc is None or wp is None:
            inputs = _texture(layer)
            if inputs is None:
                return None
            fc_est, wp_est = _saxton_rawls(*inputs)
            fc = Range(mid=fc_est)
            wp = Range(mid=wp_est)
        if not 0 <= wp.mid < fc.mid <= 1:
            return None
        result.append(RootLayer(top, bottom, fc, wp))
    return tuple(result)


def profile_taw(profile: tuple[RootLayer, ...]) -> Range:
    # FAO-56, chapter 8, equation (82). Integrate water content over layer thickness in mm.
    total = low = high = 0.0
    has_low = has_high = True
    for part in profile:
        thickness = (part.bottom_cm - part.top_cm) * MM_PER_CM
        total += (part.fc.mid - part.wp.mid) * thickness
        if part.fc.low is not None and part.wp.high is not None:
            low += max(0.0, part.fc.low - part.wp.high) * thickness
        else:
            has_low = False
        if part.fc.high is not None and part.wp.low is not None:
            high += (part.fc.high - part.wp.low) * thickness
        else:
            has_high = False
    return Range(low=min(low, total) if has_low else None, mid=total, high=max(high, total) if has_high else None)


def taw_mm(layers: list[SoilLayer], zr_cm: float) -> Range | None:
    profile = root_profile(layers, zr_cm)
    return profile_taw(profile) if profile else None


def what_if_som(layers: list[SoilLayer], delta_som_pct: float, zr_cm: float | None = None) -> Range | None:
    """Return the change in available water for an explicit SOM percentage-point increase."""
    if not layers or delta_som_pct < 0:
        return None
    depth = zr_cm if zr_cm is not None else max(layer.bottom_cm for layer in layers)
    segments = _depth_segments(layers, depth)
    if segments is None:
        return None
    difference = 0.0
    for layer, top, bottom in segments:
        inputs = _texture(layer)
        if inputs is None:
            return None
        sand, clay, som = inputs
        fc, wp = _saxton_rawls(sand, clay, som)
        adjusted_fc, adjusted_wp = _saxton_rawls(sand, clay, som + delta_som_pct)
        if not (0 <= wp < fc <= 1 and 0 <= adjusted_wp < adjusted_fc <= 1):
            return None
        difference += ((adjusted_fc - adjusted_wp) - (fc - wp)) * (bottom - top) * MM_PER_CM
    return Range(mid=difference)
