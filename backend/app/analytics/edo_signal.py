"""Present Copernicus CDI evidence from Part A's bundle."""
from __future__ import annotations

from datetime import date

from app.contracts.common import SourceResult, SourceStatus
from app.contracts.geo import EdoData
from app.contracts.report import Metric, Signal
from app.recommendations import texts_pl as text

# Copernicus EDO CDI v4, table 1. Both legend strings and codes are part of the product.
# https://drought.emergency.copernicus.eu/data/factsheets/factsheet_combinedDroughtIndicator_v4.pdf
CDI_LEVELS = {
    "no drought": (0, text.CDI_NORMAL),
    "watch": (1, text.CDI_WATCH),
    "warning": (2, text.CDI_WARNING),
    "alert": (3, text.CDI_ALERT),
    "recovery": (4, text.CDI_RECOVERY),
    "temporary soil moisture recovery": (5, text.CDI_SOIL_RECOVERY),
    "temporary vegetation recovery": (6, text.CDI_VEG_RECOVERY),
}
CDI_BY_CODE = dict(CDI_LEVELS.values())


def interpret(source: SourceResult[EdoData], analysis_date: date) -> Signal:
    data = source.data
    missing = Signal(code="edo", status=SourceStatus.MISSING, summary_pl=text.CDI_UNAVAILABLE)
    if data is None or data.date_used > analysis_date:
        return missing

    name = " ".join((data.cdi_class or "").casefold().split())
    cdi_label = CDI_LEVELS.get(name, (None, None))[1] or CDI_BY_CODE.get(data.cdi_value)
    ids = [item.source_id for item in source.provenance]
    metrics = [Metric(code="edo_date", label_pl=text.OBSERVATION_DATE, value=data.date_used.isoformat(), source_ids=ids)]
    for code, label, value in (
        ("cdi", text.CDI_LABEL, cdi_label),
        ("edo_sma", text.CDI_SMA, data.sma),
        ("edo_fapar", text.CDI_FAPAR, data.fapar_anomaly),
        ("edo_spi3", "SPI-3 (EDO)", data.spi3),
    ):
        if value is not None:
            metrics.append(Metric(code=code, label_pl=label, value=value, source_ids=ids))
    summary = text.CDI_SUMMARY.format(label=cdi_label) if cdi_label else text.CDI_PARTIAL
    status = source.status if cdi_label else SourceStatus.PARTIAL
    return Signal(code="edo", status=status, summary_pl=summary, metrics=metrics)
