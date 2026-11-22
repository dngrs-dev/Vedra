"""Group report content for printing so that every fact appears once, in a predictable place."""
from __future__ import annotations

from base64 import b64encode
from collections.abc import Sequence
from dataclasses import dataclass

from app.contracts.common import Provenance
from app.contracts.parcel import Parcel
from app.contracts.report import IrrigationAdvice, Metric, Recommendation, Report
from app.recommendations import texts_pl as text
from app.reports import site_maps
from app.reports.formatting import display_value, source_time
from app.reports.recommendation_groups import Action, Site, group_actions

LANDSCAPE_RETENTION = "landscape_retention"


@dataclass(frozen=True)
class PlannedAction:
    """A grouped action (recommendation_groups.Action) with its printable site map.

    ``site_map`` is an SVG data URL for the HTML template or PNG bytes for the built-in renderer;
    ``coordinates`` maps a site number to "lat, lon" for the sites drawn on that map.
    """

    action: Action
    anchor: str
    site_map: str | bytes | None
    coordinates: dict[int, str]

    @property
    def recommendation(self) -> Recommendation:
        return self.action.recommendation

    @property
    def field_check(self) -> bool:
        """Retention sites get a "checked in the field" box, as in the web report."""
        return self.action.recommendation.category == LANDSCAPE_RETENTION


@dataclass(frozen=True)
class CategoryGroup:
    category: str
    title: str
    actions: list[PlannedAction]


@dataclass(frozen=True)
class FieldPlan:
    """Where to start the field visit: the first retention site, preferring one without a caution."""

    action: PlannedAction
    site: Site
    count: int


def _without_title_repeats(item: Recommendation) -> Recommendation:
    # Evidence that only repeats the title, such as the terrain feature name, adds nothing.
    evidence = [metric for metric in item.evidence if metric.value != item.title_pl]
    return item if len(evidence) == len(item.evidence) else item.model_copy(update={"evidence": evidence})


def _svg_url(svg: str) -> str:
    return f"data:image/svg+xml;base64,{b64encode(svg.encode()).decode('ascii')}"


def plan_actions(items: Sequence[Recommendation], parcel_geojson: dict | None, *, png: bool = False,
                 anchor_prefix: str = "") -> list[CategoryGroup]:
    """Recommendations grouped as in the web report (recommendation_groups.group_actions), by PDF category.

    Repeated location-specific actions are written once, with numbered sites, a site map and coordinates.
    Both PDF renderers print these groups, so they show the same content.
    """
    categories: dict[str, list[PlannedAction]] = {category: [] for category in text.PDF_CATEGORY_LABELS}
    for action in group_actions([_without_title_repeats(item) for item in items]):
        site_map, coordinates = None, {}
        if action.sites and parcel_geojson is not None:
            if png:
                site_map, coordinates = site_maps.render_png(parcel_geojson, action.sites)
            else:
                svg, coordinates = site_maps.render(parcel_geojson, action.sites)
                site_map = _svg_url(svg) if svg else None
        planned = PlannedAction(action, f"zalecenie-{anchor_prefix}{action.recommendation.id}", site_map,
                                coordinates)
        categories.setdefault(action.recommendation.category, []).append(planned)
    return [CategoryGroup(category, text.PDF_CATEGORY_LABELS.get(category, category), actions)
            for category, actions in categories.items() if actions]


def field_plan(*groups: Sequence[CategoryGroup]) -> FieldPlan | None:
    """The field visit start over all printed parts, in their order; only sites drawn on a map count."""
    sites = [(planned, site) for part in groups for category in part for planned in category.actions
             if planned.field_check for site in planned.action.sites if site.number in planned.coordinates]
    if not sites:
        return None
    # Keep the report's action order and prefer a site without an access caution.
    start = next((entry for entry in sites if not entry[1].note_pl), sites[0])
    return FieldPlan(start[0], start[1], len(sites))


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
