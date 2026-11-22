"""Small printable charts derived from report metrics."""
from io import StringIO

from app.contracts.report import Report
from app.contracts.scenario import ScenarioResult
from app.recommendations import texts_pl as text


def monthly_risk_svg(report: Report) -> str | None:
    history = report.assessment.vulnerability
    if history is None:
        return None
    values = [
        (int(metric.code.rsplit("_", maxsplit=1)[-1]), metric.value)
        for metric in history.metrics
        if metric.code.startswith("kbw_risk_month_") and isinstance(metric.value, (int, float))
    ]
    if not values:
        return None
    from matplotlib.backends.backend_svg import FigureCanvasSVG
    from matplotlib.figure import Figure

    months, risk = zip(*sorted(values))
    # The report stylesheet scales the chart to the width of its A4 text column.
    figure = Figure(figsize=(6.2, 2.4), layout="constrained")
    axis = figure.subplots()
    axis.bar([str(month) for month in months], risk, color="#28776d")
    axis.set_xlabel(text.PDF_MONTH_LABEL)
    axis.set_ylabel(text.PDF_RISK_LABEL)
    axis.set_ylim(0, 100)  # A percentage ranges from zero to one hundred.
    axis.set_axisbelow(True)
    axis.grid(axis="y", alpha=0.25)
    output = StringIO()
    FigureCanvasSVG(figure).print_svg(output)
    return output.getvalue()


def scenario_svg(baseline: ScenarioResult, custom: ScenarioResult | None) -> str | None:
    """Root-zone water reserve over the season: "do nothing" versus the farmer's variant."""
    if len(baseline.series) < 2:
        return None
    from matplotlib.backends.backend_svg import FigureCanvasSVG
    from matplotlib.figure import Figure

    figure = Figure(figsize=(6.2, 2.2), layout="constrained")
    axis = figure.subplots()
    axis.plot([p.day for p in baseline.series], [p.available_pct for p in baseline.series],
              color="#8a9894", linestyle="--", linewidth=1.4, label=baseline.title_pl)
    if custom is not None and custom.series:
        axis.plot([p.day for p in custom.series], [p.available_pct for p in custom.series],
                  color="#2f6fa8", linewidth=1.8, label=custom.title_pl)
    from matplotlib.dates import DateFormatter, MonthLocator

    axis.set_ylabel("Zapas wody w glebie (%)", fontsize=8)
    axis.set_ylim(0, 100)  # A percentage ranges from zero to one hundred.
    axis.grid(axis="y", alpha=0.25)
    axis.legend(loc="upper right", fontsize=8, frameon=False)
    axis.xaxis.set_major_locator(MonthLocator())
    axis.xaxis.set_major_formatter(DateFormatter("%d.%m"))
    axis.tick_params(labelsize=8)
    output = StringIO()
    FigureCanvasSVG(figure).print_svg(output)
    return output.getvalue()
