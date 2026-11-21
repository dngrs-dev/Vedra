"""Compare separate forms of evidence and collect source limitations."""
from __future__ import annotations

from typing import Literal

from app.analytics import thresholds
from app.analytics.models import AnalysisContext
from app.contracts.common import SourceStatus
from app.contracts.report import Signal
from app.recommendations import texts_pl as text

Confidence = Literal["low", "medium", "high"]


def _metric_value(signal: Signal, code: str) -> float | int | str | None:
    return next((metric.value for metric in signal.metrics if metric.code == code), None)


def _votes(signals: list[Signal]) -> list[bool]:
    limits = thresholds.load()
    votes = []
    for signal in signals:
        if signal.status is not SourceStatus.OK:
            continue
        if signal.code == "soil_moisture":
            value = _metric_value(signal, "soil_percentile_28_to_100cm")
            if isinstance(value, (int, float)):
                votes.append(value < limits["soil_moisture"]["dry_percentile"])
        elif signal.code == "vegetation":
            value = _metric_value(signal, "vci")
            if isinstance(value, (int, float)):
                if value < limits["vegetation"]["vci_stress_below"]:
                    votes.append(True)
                elif value > limits["vegetation"]["vci_favorable_above"]:
                    votes.append(False)
    return votes


def assess(ctx: AnalysisContext) -> tuple[Confidence | None, list[str]]:
    limitations = [text.KBW_ESTIMATE_NOTE]
    sources = ((text.SOURCE_WEATHER, ctx.weather), *(
        (label, getattr(ctx.geo, field)) for field, label in text.GEO_SOURCE_LABELS.items()
    ))
    for label, source in sources:
        limitations.extend(source.notes_pl)
        if source.status is SourceStatus.MISSING:
            limitations.append(text.SOURCE_MISSING.format(source=label))
        for item in source.provenance:
            if item.resolution:
                limitations.append(text.SOURCE_RESOLUTION.format(source=item.name, resolution=item.resolution))
    for signal in ctx.signals:
        if signal.status is not SourceStatus.OK and signal.summary_pl:
            limitations.append(signal.summary_pl)
        if signal.code == "vegetation":
            count = _metric_value(signal, "clear_scenes")
            if isinstance(count, int):
                limitations.append(text.VEG_CLEAR_LIMITATION.format(count=count))

    verdict = ctx.assessment.verdict
    confidence = None
    if verdict in {"drought", "no_drought"}:
        expected = verdict == "drought"
        votes = _votes(ctx.signals)
        agreed = votes.count(expected)
        disagreed = votes.count(not expected)
        required = thresholds.load()["confidence"]["corroborating_signals"]
        confidence = "low"
        if disagreed:
            limitations.append(text.SIGNALS_DISAGREE)
        elif agreed >= required and not ctx.assessment.near_threshold:
            confidence = "high"
        elif agreed:
            confidence = "medium"
        if agreed < required:
            limitations.append(text.SIGNALS_INSUFFICIENT)
        for signal in ctx.signals:
            if signal.code == "edo":
                label = _metric_value(signal, "cdi")
                if label in (text.CDI_WATCH, text.CDI_WARNING, text.CDI_ALERT, text.CDI_NORMAL):
                    same = (label != text.CDI_NORMAL) == expected
                    summary = text.CDI_AGREES if same else text.CDI_DIFFERS
                    limitations.append(summary)
    return confidence, list(dict.fromkeys(limitations))
