from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.contracts.common import Provenance
from app.contracts.report import Cause, Metric, Recommendation, Report
from app.reports.combined import combine, split_metrics

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
    assert [(detail.title, [metric.value for metric in detail.metrics]) for part in document.crops
            for detail in part.details] == [(cause.title_pl, [1.15]), (cause.title_pl, [1.2])]
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


def test_reports_of_different_parcels_are_not_merged():
    base = _report()
    other = base.model_copy(update={"parcel": base.parcel.model_copy(update={"parcel_id": "other"})})
    assert combine([(base, None), (other, None)]) is None
    assert combine([(base, None)]) is None
