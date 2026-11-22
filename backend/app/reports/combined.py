"""Merge reports for several crops on one parcel into one document without repeating shared content.

Most of a report describes the parcel: weather and soil signals, landscape retention, data sources.
Only the KBW assessment, the history against the crop threshold and some evidence depend on the crop.
The combined document therefore has a general part, a part per crop and a shared appendix.
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from typing import TypeVar

from pydantic import BaseModel

from app.contracts.common import Provenance
from app.contracts.parcel import Parcel
from app.contracts.report import Cause, IrrigationAdvice, Metric, Recommendation, Reference, Report, Signal

T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True)
class CropDetail:
    """Values of a shared signal, cause or recommendation that differ for this crop."""

    title: str
    metrics: list[Metric]


@dataclass(frozen=True)
class CropPart:
    """Content specific to one crop."""

    report: Report
    map_png: bytes | None
    signals: list[Signal]
    causes: list[Cause]
    recommendations: list[Recommendation]
    irrigation: IrrigationAdvice | None
    details: list[CropDetail]


@dataclass(frozen=True)
class CombinedReport:
    parcel: Parcel
    analysis_date: date
    map_png: bytes | None
    # Shared by every crop. Evidence that differs between crops is listed once per crop.
    signals: list[Signal]
    causes: list[Cause]
    recommendations: list[Recommendation]
    irrigation: IrrigationAdvice | None
    crops: list[CropPart]
    # Shared items with values given per crop, as `kind:key` from `item_key`.
    varying: set[str]
    # Appendix, without duplicates.
    limitations: list[str]
    data_sources: list[Provenance]
    references: list[Reference]

    @property
    def crop_names(self) -> list[str]:
        return [part.report.crop_name_pl for part in self.crops]

    def has_crop_values(self, item: Signal | Cause | Recommendation) -> bool:
        return item_key(item) in self.varying


def item_key(item: Signal | Cause | Recommendation) -> str:
    if isinstance(item, Recommendation):
        return f"recommendation:{item.id}"
    return f"{'signal' if isinstance(item, Signal) else 'cause'}:{item.code}"


def _title(item: Signal | Cause | Recommendation) -> str:
    return item.summary_pl if isinstance(item, Signal) else item.title_pl


def _metric_key(metric: Metric) -> tuple[str, str]:
    return metric.code, metric.label_pl


def split_metrics(lists: Sequence[Sequence[Metric]], crops: Sequence[str]) -> tuple[list[Metric], list[list[Metric]]]:
    """Return metrics equal for every crop, and per crop the metrics that differ.

    A value that only repeats the crop name, such as the selected crop, is dropped: each crop part is
    titled with its name.
    """
    keys = list(dict.fromkeys(_metric_key(metric) for metrics in lists for metric in metrics))
    common: list[Metric] = []
    per_crop: list[list[Metric]] = [[] for _ in lists]
    for key in keys:
        found = [next((metric for metric in metrics if _metric_key(metric) == key), None) for metrics in lists]
        first = found[0]
        if first is not None and all(
            metric is not None and (metric.value, metric.unit) == (first.value, first.unit) for metric in found
        ):
            common.append(first)
            continue
        for index, (metric, crop) in enumerate(zip(found, crops)):
            if metric is not None and metric.value != crop:
                per_crop[index].append(metric)
    return common, per_crop


def _split(
    lists: Sequence[Sequence[T]], crops: Sequence[str], key: Callable[[T], str], same: Callable[[T, T], bool],
    metrics_field: str,
) -> tuple[list[T], list[list[T]], list[list[CropDetail]], set[str]]:
    """Split items into those shared by every crop and the rest per crop.

    Shared items keep the metrics common to all crops. Their differing metrics become per-crop details.
    """
    shared: list[T] = []
    shared_keys: set[str] = set()
    details: list[list[CropDetail]] = [[] for _ in lists]
    varying: set[str] = set()
    for item in lists[0]:
        found = [next((other for other in items if key(other) == key(item)), None) for items in lists]
        if not all(other is not None and same(other, item) for other in found):
            continue
        common, per_crop = split_metrics([getattr(other, metrics_field) for other in found], crops)
        shared.append(item.model_copy(update={metrics_field: common}))
        shared_keys.add(key(item))
        if any(per_crop):
            varying.add(item_key(item))
            for index, metrics in enumerate(per_crop):
                if metrics:
                    details[index].append(CropDetail(_title(item), metrics))
    rest = [[item for item in items if key(item) not in shared_keys] for items in lists]
    return shared, rest, details, varying


def _same_signal(first: Signal, second: Signal) -> bool:
    return (first.status, first.summary_pl) == (second.status, second.summary_pl)


def _same_cause(first: Cause, second: Cause) -> bool:
    return (first.title_pl, first.explanation_pl) == (second.title_pl, second.explanation_pl)


def _same_recommendation(first: Recommendation, second: Recommendation) -> bool:
    fields = ("category", "title_pl", "action_pl", "why_pl", "reference_ids", "geometry")
    return all(getattr(first, field) == getattr(second, field) for field in fields)


def _sources(reports: Sequence[Report]) -> list[Provenance]:
    """One entry per source description; the latest download time is kept."""
    latest: dict[tuple, Provenance] = {}
    for report in reports:
        for source in report.data_sources:
            key = (source.source_id, source.name, source.url, source.data_period, source.resolution,
                   source.licence, source.attribution_pl)
            if key not in latest or source.fetched_at > latest[key].fetched_at:
                latest[key] = source
    return list(latest.values())


def combine(items: Sequence[tuple[Report, bytes | None]]) -> CombinedReport | None:
    """Merge reports for one parcel and date. Returns None when they describe different parcels or dates."""
    if len(items) < 2:
        return None
    reports = [report for report, _ in items]
    first = reports[0]
    if any((report.parcel.parcel_id, report.analysis_date) != (first.parcel.parcel_id, first.analysis_date)
           for report in reports):
        return None
    crops = [report.crop_name_pl for report in reports]
    signals, crop_signals, signal_details, signal_varying = _split(
        [r.assessment.signals for r in reports], crops, lambda item: item.code, _same_signal, "metrics")
    causes, crop_causes, cause_details, cause_varying = _split(
        [r.causes for r in reports], crops, lambda item: item.code, _same_cause, "evidence")
    recommendations, crop_recommendations, recommendation_details, recommendation_varying = _split(
        [r.recommendations for r in reports], crops, lambda item: item.id, _same_recommendation, "evidence")
    shared_irrigation = all(report.irrigation == first.irrigation for report in reports)
    return CombinedReport(
        parcel=first.parcel,
        analysis_date=first.analysis_date,
        map_png=next((map_png for _, map_png in items if map_png), None),
        signals=signals,
        causes=causes,
        recommendations=recommendations,
        irrigation=first.irrigation if shared_irrigation else None,
        crops=[
            CropPart(report, map_png, crop_signals[index], crop_causes[index], crop_recommendations[index],
                     None if shared_irrigation else report.irrigation,
                     signal_details[index] + cause_details[index] + recommendation_details[index])
            for index, (report, map_png) in enumerate(items)
        ],
        varying=signal_varying | cause_varying | recommendation_varying,
        limitations=list(dict.fromkeys(note for report in reports for note in report.limitations_pl)),
        data_sources=_sources(reports),
        references=list({reference.id: reference for report in reports for reference in report.references}.values()),
    )
