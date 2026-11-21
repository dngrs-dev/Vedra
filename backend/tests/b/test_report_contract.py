from pathlib import Path

from app.contracts.report import Report

SAMPLE_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "sample_report.json"


def test_frontend_sample_matches_report_schema():
    sample = Report.model_validate_json(SAMPLE_PATH.read_bytes())

    assert sample.assessment.kbw.verdict == "off_season"
    assert sample.assessment.kbw.kbw_mm is None
    assert sample.map_layers[0].geojson == sample.parcel.geometry_wgs84
    assert Report.model_validate_json(sample.model_dump_json()) == sample
