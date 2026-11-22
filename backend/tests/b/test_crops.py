import csv
import re
from itertools import product

from app.analytics.crops import load, threshold
from app.config import CONFIG_DIR


def test_statutory_threshold_table_contains_every_crop_category_and_period():
    # The annex to Dz.U. 2019 poz. 739 lists 14 crops, categories I-IV, and 14 periods.
    catalog = load()
    assert len(catalog) == 14
    expected = set(product(catalog, ("I", "II", "III", "IV"), range(1, 15)))

    with (CONFIG_DIR / "kbw_thresholds.csv").open(encoding="utf-8", newline="") as table:
        rows = list(csv.DictReader(table))

    assert len(rows) == len(expected)
    assert {(row["crop_code"], row["soil_category"], int(row["period_idx"])) for row in rows} == expected
    for row in rows:
        raw = row["threshold_mm"]
        assert re.fullmatch(r"-\d+|x|-", raw)
        assert row["source"] in {f"{catalog[row['crop_code']].source}#page={page}" for page in (2, 3)}


def test_threshold_lookup_preserves_values_and_annex_markers():
    # Representative cells from pages 2 and 3 of the annex to Dz.U. 2019 poz. 739.
    assert threshold("winter_cereals", "I", 1) == -129.0
    assert threshold("winter_cereals", "IV", 9) == -306.0
    assert threshold("winter_cereals", "IV", 10) == "x"
    assert threshold("sugar_beet", "I", 14) == "-"
    assert threshold("legumes", "IV", 14) == -249.0


def test_crop_parameters_have_sources():
    for crop in load().values():
        assert crop.name_pl and crop.source
        assert crop.kc.source and crop.zr_m.source and crop.p.source
        # Root depth is positive and FAO-56 defines p as a fraction of available water.
        assert 0 < crop.zr_m.low <= crop.zr_m.high
        assert 0 < crop.p.value < 1
