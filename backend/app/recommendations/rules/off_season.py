"""Planning advice for the next monitoring season."""
from app.contracts.report import Metric, Recommendation
from app.recommendations import texts_pl as text


def evaluate(risk: list[Metric]) -> Recommendation:
    return Recommendation(
        id="plan_retention_before_season", category="landscape_retention", title_pl=text.OFF_SEASON_RETENTION_TITLE,
        action_pl=text.OFF_SEASON_RETENTION_ACTION, why_pl=text.OFF_SEASON_RETENTION_WHY,
        evidence=risk, reference_ids=["nwrm"],
    )
