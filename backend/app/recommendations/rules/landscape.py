"""Landscape retention candidates tied to measured features."""
from app.analytics.models import AnalysisContext
from app.contracts.report import Metric, Recommendation
from app.recommendations import texts_pl as text


def evaluate(ctx: AnalysisContext, risk: list[Metric]) -> list[Recommendation]:
    results: list[Recommendation] = []
    terrain = ctx.geo.terrain
    if terrain.data is not None:
        source_ids = [item.source_id for item in terrain.provenance]
        for spot in terrain.data.retention_spots:
            title, action, why, reference = text.RETENTION_SPOT_TEXTS[spot.kind]
            if not spot.inside_parcel:
                action += f" {text.RETENTION_OUTSIDE_PARCEL}"
            evidence = [*risk, Metric(code="retention_site", label_pl=text.RETENTION_SITE_LABEL,
                                      value=title, source_ids=source_ids)]
            for code, label, value, unit in (
                ("retention_volume", text.RETENTION_VOLUME, spot.volume_m3, "m³"),
                ("retention_area", text.RETENTION_AREA, spot.area_m2, "m²"),
                ("retention_flow_area", text.CAUSE_FLOW_AREA, spot.upstream_area_ha, "ha"),
            ):
                if value is not None:
                    evidence.append(Metric(code=code, label_pl=label, value=value, unit=unit, source_ids=source_ids))
            results.append(Recommendation(
                id=f"retention_{spot.id}", category="landscape_retention", title_pl=title, action_pl=action,
                why_pl=why, evidence=evidence, reference_ids=[reference], geometry=spot.geometry,
            ))

    hydro = ctx.geo.hydro
    if hydro.data is not None and hydro.data.ditches_crossing_boundary > 0:
        ditch = next((item for item in hydro.data.features if item.kind == "ditch" and item.touches_parcel), None)
        evidence = Metric(code="crossing_ditches", label_pl=text.RETENTION_DITCH_COUNT,
                          value=hydro.data.ditches_crossing_boundary, source_ids=[item.source_id for item in hydro.provenance])
        results.append(Recommendation(
            id="review_drainage_ditch", category="landscape_retention", title_pl=text.RETENTION_DITCH_TITLE,
            action_pl=text.RETENTION_DITCH_ACTION, why_pl=text.RETENTION_DITCH_WHY,
            evidence=[*risk, evidence], reference_ids=["nwrm"], geometry=ditch.geometry if ditch else None,
        ))
    return results
