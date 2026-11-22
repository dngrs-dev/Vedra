import html
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.contracts.common import Provenance
from app.contracts.report import Cause, Metric, Recommendation, Report, Vulnerability
from app.reports import pdf, pdf_basic
from app.reports.combined import combine, split_metrics
from app.reports.formatting import display_value

SAMPLE = Path(__file__).resolve().parents[1] / "fixtures" / "sample_report.json"


def _report() -> Report:
    return Report.model_validate_json(SAMPLE.read_bytes())


def _crop(report: Report, name: str, threshold: float) -> Report:
    kbw = report.assessment.kbw.model_copy(update={"threshold_mm": threshold})
    return report.model_copy(update={
        "report_id": name, "crop_name_pl": name,
        "assessment": report.assessment.model_copy(update={"kbw": kbw}),
    })


def test_values_equal_for_every_crop_stay_shared_and_the_rest_go_to_each_crop():
    rain = Metric(code="rain", label_pl="Suma opadów", value=124.2, unit="mm")
    crops = ["Ziemniaki", "Kukurydza"]
    common, per_crop = split_metrics([
        [rain, Metric(code="kc", label_pl="Kc", value=1.15), Metric(code="crop", label_pl="Uprawa", value="Ziemniaki")],
        [rain, Metric(code="kc", label_pl="Kc", value=1.2), Metric(code="crop", label_pl="Uprawa", value="Kukurydza")],
    ], crops)
    assert common == [rain]
    # A value repeating the crop name is dropped, as each crop part carries the name in its title.
    assert [[(metric.code, metric.value) for metric in metrics] for metrics in per_crop] == [[("kc", 1.15)], [("kc", 1.2)]]


def _cause(kc: float) -> Cause:
    return Cause(code="crop_water_demand", title_pl="Zapotrzebowanie uprawy na wodę", explanation_pl="Opis.",
                 evidence=[Metric(code="rain", label_pl="Suma opadów", value=124.2, unit="mm"),
                           Metric(code="kc", label_pl="Kc", value=kc)])


def _recommendation(identifier: str, title: str) -> Recommendation:
    return Recommendation(id=identifier, category="landscape_retention", title_pl=title, action_pl="Działanie.",
                          why_pl="Uzasadnienie.", evidence=[Metric(code="kbw", label_pl="KBW", value=-117.5)],
                          reference_ids=["kbw_regulation"])


def test_combined_report_keeps_shared_content_once_and_crop_content_per_crop():
    base = _report()
    shared = _recommendation("retention_Z1", "Zagłębienie")
    first = _crop(base, "Ziemniaki", -219).model_copy(update={"causes": [_cause(1.15)], "recommendations": [shared]})
    second = _crop(base, "Kukurydza", -156).model_copy(update={
        "causes": [_cause(1.2)], "recommendations": [shared, _recommendation("only_for_maize", "Tylko kukurydza")],
    })

    document = combine([(first, b"map"), (second, None)])

    assert document is not None and document.crop_names == ["Ziemniaki", "Kukurydza"]
    assert document.map_png == b"map"
    assert [item.id for item in document.recommendations] == ["retention_Z1"]
    assert document.crops[0].recommendations == []
    assert [item.id for item in document.crops[1].recommendations] == ["only_for_maize"]
    # The shared cause keeps its common evidence; the differing value is listed in each crop part.
    [cause] = document.causes
    assert document.has_crop_values(cause) and not document.has_crop_values(document.recommendations[0])
    assert [metric.code for metric in cause.evidence] == ["rain"]
    assert [[(value.metric.value, value.applies_to) for value in part.values] for part in document.crops] == [
        [(1.15, [cause.title_pl])], [(1.2, [cause.title_pl])]]
    assert [part.report.assessment.kbw.threshold_mm for part in document.crops] == [-219, -156]
    assert document.limitations == base.limitations_pl
    assert document.references == base.references


def test_sources_are_listed_once_with_the_latest_download():
    base = _report()
    source = Provenance(source_id="imgw", name="IMGW", url="https://example.org", licence="CC BY 4.0", live=True,
                        fetched_at=datetime(2026, 7, 15, tzinfo=timezone.utc))
    later = source.model_copy(update={"fetched_at": source.fetched_at + timedelta(minutes=5)})
    document = combine([(base.model_copy(update={"data_sources": [source]}), None),
                        (base.model_copy(update={"report_id": "b", "data_sources": [later]}), None)])
    assert document is not None and document.data_sources == [later]


def _site(label: str, capacity: float, drought_years: int, crop: str, lon: float, lat: float) -> Recommendation:
    return Recommendation(
        id=f"retention_{label}", category="landscape_retention", title_pl="Rozważ wykorzystanie zagłębienia",
        action_pl="Sprawdź w terenie zagłębienie.", why_pl="Model terenu wskazuje zagłębienie.",
        geometry={"type": "Point", "coordinates": [lon, lat]}, reference_ids=["kbw_regulation"],
        evidence=[Metric(code="drought_years", label_pl="Lata z bilansem poniżej progu suszy", value=drought_years),
                  Metric(code="feature", label_pl="Obiekt", value="Rozważ wykorzystanie zagłębienia"),
                  Metric(code="crop", label_pl="Wybrana uprawa", value=crop),
                  Metric(code="capacity", label_pl="Szacowana pojemność", value=capacity, unit="m³")])


def _rich_crop(base: Report, name: str, drought_years: int, years: list[int]) -> Report:
    report = _crop(base, name, -165)
    history = Vulnerability(summary_pl=f"Susza w {len(years)} latach.", years_assessed=[2020, 2021, 2022, 2023],
                            drought_years=years,
                            metrics=[Metric(code="kbw_risk_month_6", label_pl="Udział okresów w czerwcu",
                                            value=10.0 * drought_years, unit="%")])
    return report.model_copy(update={
        "assessment": report.assessment.model_copy(update={"vulnerability": history}),
        "recommendations": [_site("Z1", 527.3, drought_years, name, 19.2, 51.5),
                            _site("Z2", 490.1, drought_years, name, 19.21, 51.51)],
        "causes": [_cause(1.1 + drought_years / 100)],
    })


def _texts_of_basic_pdf(items) -> str:
    return " ".join(item.get_text() for page in pdf_basic.pages(items) for item in page.texts)


def _texts_of_html(items) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", pdf.render_many_html(items)))


@pytest.mark.parametrize("document_text", [_texts_of_basic_pdf, _texts_of_html], ids=["builtin", "weasyprint-html"])
def test_combined_pdf_keeps_every_fact_once(document_text):
    base = _report()
    first, second = _rich_crop(base, "Ziemniaki", 2, [2021, 2023]), _rich_crop(base, "Kukurydza", 3, [2020, 2021, 2023])
    content = re.sub(r"\s+", " ", document_text([(first, None), (second, None)]))

    parcel = base.parcel
    for fact in (parcel.parcel_id, parcel.commune, parcel.county, parcel.voivodeship, parcel.teryt,
                 parcel.parcel_number, f"{display_value(parcel.area_ha)} ha"):
        assert content.count(fact) >= 1, fact
    # Shared text once, crop values in their crop parts.
    assert content.count("Sprawdź w terenie zagłębienie.") == 1
    # Repeated sites are numbered as in the web report: one site table with coordinates, one field visit plan.
    assert content.count("51.500000, 19.200000") == content.count("51.510000, 19.210000") == 1
    assert content.count("Przesłanki i uwagi") == 1
    assert content.count("Plan wizji w terenie") == 1 and "Miejsca do sprawdzenia: 2." in content
    assert "527,3 m³" in content and "490,1 m³" in content
    assert content.count("Źródła danych") == 1
    # Limitations and sources appear as often as in a report for one crop (a note may also be an attribution).
    single = re.sub(r"\s+", " ", document_text([(first, None)]))
    for note in base.limitations_pl:
        assert content.count(note) == single.count(note) >= 1, note
    for crop, years in (("Ziemniaki", "2021, 2023"), ("Kukurydza", "2020, 2021, 2023")):
        assert crop in content and years in content
    assert content.count("Lata z bilansem poniżej progu suszy") == 2  # Once in each crop part.
    assert "wszystkie działania z części ogólnej" in content
    assert "Kc" in content and "1,12" in content and "1,13" in content
    # The selected crop and the terrain feature only repeat headings, so they are not listed as values.
    assert "Wybrana uprawa" not in content and "Obiekt" not in content


def test_reports_of_different_parcels_are_not_merged():
    base = _report()
    other = base.model_copy(update={"parcel": base.parcel.model_copy(update={"parcel_id": "other"})})
    assert combine([(base, None), (other, None)]) is None
    assert combine([(base, None)]) is None
