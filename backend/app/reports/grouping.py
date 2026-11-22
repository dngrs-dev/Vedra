"""Group report content for printing so that every fact appears once, in a predictable place."""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.contracts.common import Provenance
from app.contracts.parcel import Parcel
from app.contracts.report import IrrigationAdvice, Metric, Recommendation, Report
from app.recommendations import texts_pl as text
from app.reports.formatting import display_value, source_time

# Retention recommendations are named after the site label drawn on the static map, e.g. "retention_Z1" -> "Z1".
MAP_LABEL_PREFIX = "retention_"


@dataclass(frozen=True)
class Site:
    """One place or variant of a recommendation that is repeated for several places."""

    label: str
    on_map: bool
    evidence: list[Metric]


@dataclass(frozen=True)
class ActionGroup:
    """Recommendations with the same title, action and justification, written once."""

    first: Recommendation
    evidence: list[Metric]  # Common to every place.
    sites: list[Site]  # Empty for a single recommendation.

    @property
    def map_label(self) -> str | None:
        return _map_label(self.first) if not self.sites else None


@dataclass(frozen=True)
class CategoryGroup:
    category: str
    title: str
    actions: list[ActionGroup]


def _map_label(item: Recommendation) -> str | None:
    if item.geometry is not None and item.id.startswith(MAP_LABEL_PREFIX):
        return item.id.removeprefix(MAP_LABEL_PREFIX)
    return None


def _same(first: Metric, second: Metric) -> bool:
    return (first.code, first.label_pl, first.value, first.unit) == (second.code, second.label_pl, second.value,
                                                                      second.unit)


def group_recommendations(items: Sequence[Recommendation]) -> list[CategoryGroup]:
    """Group by category in the order of the report, then merge recommendations that differ only by evidence."""
    groups: dict[tuple, list[Recommendation]] = {}
    for item in items:
        key = (item.category, item.title_pl, item.action_pl, item.why_pl, tuple(item.reference_ids))
        groups.setdefault(key, []).append(item)

    categories: dict[str, list[ActionGroup]] = {category: [] for category in text.PDF_CATEGORY_LABELS}
    for members in groups.values():
        first = members[0]
        # Evidence that only repeats the title, such as the terrain feature name, adds nothing.
        evidence = [[metric for metric in member.evidence if metric.value != first.title_pl] for member in members]
        common = [metric for metric in evidence[0]
                  if all(any(_same(metric, other) for other in rest) for rest in evidence[1:])]
        sites = []
        if len(members) > 1:
            for index, (member, metrics) in enumerate(zip(members, evidence), start=1):
                label = _map_label(member)
                sites.append(Site(label or str(index), label is not None,
                                  [metric for metric in metrics if not any(_same(metric, c) for c in common)]))
        categories.setdefault(first.category, []).append(ActionGroup(first, common, sites))
    return [CategoryGroup(category, text.PDF_CATEGORY_LABELS.get(category, category), actions)
            for category, actions in categories.items() if actions]


def site_heading(site: Site) -> str:
    return text.PDF_SITE_ON_MAP.format(label=site.label) if site.on_map else text.PDF_SITE_VARIANT.format(
        label=site.label)


def last_kbw(report: Report) -> tuple[Metric | None, Metric | None]:
    history = report.assessment.vulnerability.metrics if report.assessment.vulnerability else []
    by_code = {metric.code: metric for metric in history}
    return by_code.get("kbw_last_period"), by_code.get("kbw_last_balance")


def drought_years_summary(report: Report) -> str | None:
    history = report.assessment.vulnerability
    if history is None or not history.years_assessed:
        return None
    return f"{len(history.drought_years)} z {len(history.years_assessed)}"


# ---------- label and value rows shared by both PDF renderers ----------

def metric_text(metric: Metric) -> str:
    return display_value(metric.value) + (f" {metric.unit}" if metric.unit else "")


def numeric_threshold(report: Report) -> bool:
    threshold = report.assessment.kbw.threshold_mm
    return isinstance(threshold, (int, float)) and not isinstance(threshold, bool)


def parcel_rows(parcel: Parcel) -> list[tuple[str, str]]:
    """Every descriptive parcel field, as the parcel card of the web report."""
    return [
        ("Działka ewidencyjna", parcel.parcel_id),
        ("Numer działki", parcel.parcel_number),
        ("Obręb", display_value(parcel.region)),
        ("Gmina", parcel.commune),
        ("Powiat", parcel.county),
        ("Województwo", parcel.voivodeship),
        ("TERYT", parcel.teryt),
        ("Powierzchnia", f"{display_value(parcel.area_ha)} ha"),
        ("Środek działki (WGS84)", f"{parcel.centroid_lat:.5f}, {parcel.centroid_lon:.5f}".replace(".", ",")),
    ]


def assessment_rows(report: Report) -> list[tuple[str, str]]:
    """Every field of the KBW assessment that has a value."""
    kbw = report.assessment.kbw
    rows = []
    if kbw.period:
        rows.append(("Okres oceny", f"{kbw.period.start} – {kbw.period.end}"))
    if kbw.soil_category:
        rows.append(("Kategoria gleby", kbw.soil_category))
    if kbw.kbw_mm is not None or (kbw.period and kbw.verdict == "unavailable"):
        rows.append(("Klimatyczny bilans wodny", display_value(kbw.kbw_mm) + (" mm" if kbw.kbw_mm is not None else "")))
    if kbw.kbw_et0_mm is not None:
        rows.append(("KBW z ewapotranspiracji referencyjnej ET₀ (porównanie metod)",
                     f"{display_value(kbw.kbw_et0_mm)} mm"))
    if numeric_threshold(report):
        rows.append(("Próg dla uprawy i gleby", f"{display_value(kbw.threshold_mm)} mm"))
    elif kbw.threshold_mm in ("x", "-"):
        rows.append(("Próg dla uprawy i gleby", text.PDF_VERDICT_LABELS[kbw.verdict]))
    if kbw.distance_to_threshold_mm is not None:
        rows.append(("Odległość od progu KBW", f"{display_value(kbw.distance_to_threshold_mm)} mm"))
    if kbw.near_threshold is not None:
        rows.append(("Wynik na granicy progu", text.PDF_YES_NO[kbw.near_threshold]))
    if report.assessment.confidence:
        rows.append(("Pewność oceny", text.PDF_CONFIDENCE_LABELS[report.assessment.confidence]))
    return rows


def history_year_rows(report: Report) -> list[tuple[str, str]]:
    history = report.assessment.vulnerability
    if history is None or not history.years_assessed:
        return []
    return [("Lata objęte oceną", ", ".join(map(str, history.years_assessed))),
            ("Lata z suszą", ", ".join(map(str, history.drought_years)) or text.PDF_NO_DROUGHT_YEARS)]


def irrigation_rows(advice: IrrigationAdvice) -> list[tuple[str, str]]:
    rows = []
    if advice.justified is not None:
        rows.append(("Nawadnianie uzasadnione", text.PDF_YES_NO[advice.justified]))
    if advice.suggested_date:
        rows.append(("Szacowany termin", str(advice.suggested_date)))
    if advice.net_dose_mm:
        rows.append(("Dawka netto", f"{display_value(advice.net_dose_mm)} mm"))
    return rows


def source_lines(source: Provenance) -> tuple[str, str, str]:
    """Name and period, download, licence: one data source in three lines."""
    first = source.name + (f" · Okres danych: {source.data_period}" if source.data_period else "")
    second = f"Pobranie: {source_time(source.fetched_at)} · {text.PDF_SOURCE_LIVE[source.live]}" + (
        f" · Rozdzielczość: {source.resolution}" if source.resolution else "")
    third = f"Licencja: {source.licence}" + (f" · {source.attribution_pl}" if source.attribution_pl else "")
    return first, second, third


OVERVIEW_COLUMNS = [("Uprawa", 0.19, "left"), ("Ocena bieżąca", 0.2, "left"), ("KBW / próg", 0.19, "left"),
                    ("Ostatnia ocena KBW", 0.28, "left"), ("Lata z suszą", 0.14, "right")]


def overview_row(report: Report) -> list[str]:
    """A crop's current verdict, KBW against its threshold, the last assessed period and drought years."""
    kbw = report.assessment.kbw
    balance = "—"
    if kbw.kbw_mm is not None:
        balance = f"{display_value(kbw.kbw_mm)} mm"
        if numeric_threshold(report):
            balance += f" / próg {display_value(kbw.threshold_mm)} mm"
    last_period, last_balance = last_kbw(report)
    last = f"{display_value(last_period.value)}: {metric_text(last_balance)}" if last_period and last_balance else "—"
    return [report.crop_name_pl, text.PDF_VERDICT_LABELS[kbw.verdict], balance, last,
            drought_years_summary(report) or "—"]
