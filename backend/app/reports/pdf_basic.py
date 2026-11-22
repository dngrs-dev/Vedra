"""Render reports to PDF with matplotlib alone.

WeasyPrint needs the native Pango libraries, which the Docker image provides but a plain Windows or
macOS Python install usually lacks. This renderer needs nothing beyond matplotlib, already a
dependency, so a PDF is always available. Its sections and wording follow templates/report.html.j2.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass
from functools import cache, lru_cache
from itertools import count
from io import BytesIO

from matplotlib.backends.backend_agg import RendererAgg
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.figure import Figure
from matplotlib.font_manager import FontProperties
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle

from app.contracts.common import Provenance
from app.contracts.scenario import ScenarioReport
from app.contracts.report import (
    Cause, IrrigationAdvice, Metric, Recommendation, Reference, Report, Signal,
)
from app.recommendations import texts_pl as text
from app.reports.charts import monthly_risk_png, scenario_png
from app.reports.combined import CombinedReport, CropValue, combine
from app.reports.grouping import (
    OVERVIEW_COLUMNS, CategoryGroup, FieldPlan, PlannedAction, assessment_rows, field_plan, history_year_rows,
    SCENARIO_COLUMNS, irrigation_rows, last_kbw, metric_text, overview_row, parcel_rows, plan_actions,
    scenario_budget_rows, scenario_custom, scenario_levers_text, scenario_variant_rows, source_lines,
)
from app.reports.formatting import display_value

# A4 in PostScript points (ISO 216) and the margins from report.css (16 / 17 / 18 mm).
PAGE_W, PAGE_H = 595.28, 841.89
MARGIN_X, MARGIN_TOP, MARGIN_BOTTOM = 48.2, 45.4, 51.0
TEXT_W = PAGE_W - 2 * MARGIN_X
CONTENT_H = PAGE_H - MARGIN_TOP - MARGIN_BOTTOM
LINE_HEIGHT = 1.45  # report.css body line-height
MM = 72 / 25.4

# Colours from report.css.
INK, HEADING, ACCENT, MUTED, LINK = "#172b29", "#154c43", "#28776d", "#43605c", "#175d57"
RULE, RULE_LIGHT, LABEL, SUMMARY_BG = "#c5d9d4", "#e4eeeb", "#334f4b", "#eef7f3"

TITLE = "Raport gospodarowania wodą"
FOOTER = "Vedra · Raport gospodarowania wodą"
MAP_MAX_H = 56 * MM  # .map max-height in report.css
CHART_MAX_H = 80 * MM
MEASURE_DPI = 720  # text measurement resolution, see _renderer
SCENARIO_CHART_MAX_H = 60 * MM
SITE_MAP_MAX_H = 52 * MM  # .site-map img max-height in report.css


@cache
def _font(size: float, bold: bool = False) -> FontProperties:
    # DejaVu Sans ships with matplotlib and covers Polish diacritics, as in report.css.
    return FontProperties(family="DejaVu Sans", size=size, weight="bold" if bold else "normal")


@cache
def _renderer() -> RendererAgg:
    # Measured at 720 dpi: at 72 dpi Agg hints glyphs and reads about 2 % narrower than the PDF backend draws
    # (488 vs 498 pt for a full line), so long lines ran past the right margin.
    return RendererAgg(1, 1, MEASURE_DPI)


@lru_cache(maxsize=8192)
def _width(value: str, font: FontProperties) -> float:
    """Width in points, as drawn by the PDF backend."""
    return _renderer().get_text_width_height_descent(value, font, ismath=False)[0] * 72 / MEASURE_DPI


@lru_cache(maxsize=64)
def _space(font: FontProperties) -> float:
    # A lone or trailing space measures as zero, so take the advance between two characters.
    return _width("a a", font) - _width("aa", font)


def _split_word(word: str, font: FontProperties, width: float) -> list[str]:
    """Break a word wider than the column, such as a long URL, into fitting pieces."""
    pieces = []
    while word and _width(word, font) > width:
        low, high = 1, len(word)
        while low < high:
            middle = (low + high + 1) // 2
            if _width(word[:middle], font) <= width:
                low = middle
            else:
                high = middle - 1
        pieces.append(word[:low])
        word = word[low:]
    return [*pieces, word] if word else pieces


def _wrap(value: str, font: FontProperties, width: float, first_width: float | None = None) -> list[str]:
    # Line widths are summed from cached word widths, so each word is measured once per document.
    space = _space(font)
    lines: list[str] = []
    for paragraph in value.splitlines() or [""]:
        line, line_w = "", 0.0
        for word in paragraph.split():
            limit = first_width if first_width is not None and not lines else width
            word_w = _width(word, font)
            if line and line_w + space + word_w <= limit:
                line, line_w = f"{line} {word}", line_w + space + word_w
                continue
            if not line and word_w <= limit:
                line, line_w = word, word_w
                continue
            if line:
                lines.append(line)
                limit = width
            *full, line = _split_word(word, font, limit) or [""]
            lines.extend(full)
            line_w = _width(line, font)
        lines.append(line)
    return lines


Draw = Callable[[Figure, float], None]


@dataclass(frozen=True)
class Frame:
    """The horizontal extent text is wrapped and drawn in."""

    x: float = MARGIN_X
    width: float = TEXT_W

    @property
    def right(self) -> float:
        return self.x + self.width


BODY = Frame()
# `.summary { padding: 1mm 4mm 3mm; }` in report.css.
SUMMARY = Frame(MARGIN_X + 4 * MM, TEXT_W - 8 * MM)


@dataclass
class Row:
    """An unbreakable horizontal strip of the page; ``draw`` receives the strip's top edge."""

    height: float
    draw: Draw | None = None
    gap: bool = False  # Vertical space, dropped at the top of a page.
    boxed: int = 0  # Id of the shaded box (.summary, .field-plan) the row belongs to; 0 = none.


def _text(figure: Figure, x: float, y: float, value: str, font: FontProperties, color: str = INK,
          ha: str = "left", url: str | None = None) -> None:
    figure.text(x / PAGE_W, y / PAGE_H, value, fontproperties=font, color=color, ha=ha, va="baseline",
                parse_math=False, url=url)


def _gap(height: float) -> Row:
    return Row(height, gap=True)


def _lines(value: str, size: float = 10, bold: bool = False, color: str = INK, indent: float = 0,
           url: str | None = None, lead: str | None = None, after: float = 2 * MM, frame: Frame = BODY) -> list[Row]:
    """A wrapped paragraph; ``lead`` is a bold prefix such as a status label."""
    font, line_h = _font(size, bold), size * LINE_HEIGHT
    width = frame.width - indent
    lead_w = _width(lead, _font(size, True)) + _space(font) if lead else 0
    lines = _wrap(value, font, width, first_width=width - lead_w if lead else None)
    rows = []
    for index, line in enumerate(lines):
        def draw(figure: Figure, top: float, line=line, first=index == 0) -> None:
            baseline = top - size * 1.1
            x = frame.x + indent
            if first and lead:
                _text(figure, x, baseline, lead, _font(size, True), color)
                x += lead_w
            _text(figure, x, baseline, line, font, color, url=url)
        rows.append(Row(line_h, draw))
    return [*rows, _gap(after)] if after else rows


def _heading(value: str, level: int, frame: Frame = BODY) -> list[Row]:
    size = {1: 23, 2: 14, 3: 11}[level]
    font = _font(size, True)
    before, after = {1: (1 * MM, 5 * MM), 2: (6 * MM, 2 * MM), 3: (1 * MM, 1 * MM)}[level]
    rows = [_gap(before)]
    lines = _wrap(value, font, frame.width)
    for index, line in enumerate(lines):
        def draw(figure: Figure, top: float, line=line, last=index == len(lines) - 1) -> None:
            baseline = top - size * 1.0
            _text(figure, frame.x, baseline, line, font, HEADING)
            if level == 2 and last:
                figure.add_artist(_rule(baseline - 1.5 * MM, RULE, frame))
        rows.append(Row(size * 1.2 + (1.5 * MM if level == 2 and index == len(lines) - 1 else 0), draw))
    return [*rows, _gap(after)]


def _rule(y: float, color: str, frame: Frame = BODY) -> Line2D:
    return Line2D([frame.x / PAGE_W, frame.right / PAGE_W], [y / PAGE_H, y / PAGE_H], color=color, linewidth=0.75)


def _pairs(items: Iterable[tuple[str, str]], size: float = 10, frame: Frame = BODY,
           after: float = 2 * MM) -> list[Row]:
    """Label and value rows, as the ``.metrics`` definition lists in report.css."""
    rows = []
    label_font, value_font, line_h = _font(size), _font(size, True), size * LINE_HEIGHT
    for label, value in items:
        # Short values keep one line and leave the rest of the row to the label, as the flex row in report.css.
        value_w = min(_width(value, value_font), frame.width * 0.45)
        values = _wrap(value, value_font, max(value_w, frame.width * 0.2))
        labels = _wrap(label, label_font, frame.width - value_w - 3 * MM)
        height = max(len(labels), len(values)) * line_h + 1.2 * MM

        def draw(figure: Figure, top: float, labels=labels, values=values) -> None:
            for index, line in enumerate(labels):
                _text(figure, frame.x, top - 0.5 * MM - size * 1.1 - index * line_h, line, label_font, LABEL)
            for index, line in enumerate(values):
                _text(figure, frame.right, top - 0.5 * MM - size * 1.1 - index * line_h, line, value_font,
                      INK, ha="right")
            figure.add_artist(_rule(top - height + 0.3, RULE_LIGHT, frame))
        rows.append(Row(height, draw))
    return [_gap(1 * MM), *rows, *([_gap(after)] if after else [])] if rows else []


def _metrics(metrics: Iterable[Metric]) -> list[Row]:
    return _pairs((metric.label_pl, metric_text(metric)) for metric in metrics)


def _bullets(items: Iterable[tuple[str, str | None]], size: float = 10) -> list[Block]:
    """A bulleted list; each entry is kept on one page."""
    blocks = []
    for value, url in items:
        item = _lines(value, size, indent=5 * MM, url=url, color=LINK if url else INK, after=1 * MM)
        bullet = item[0].draw

        def draw(figure: Figure, top: float, bullet=bullet) -> None:
            _text(figure, MARGIN_X + 1.2 * MM, top - size * 1.1, "•", _font(size), INK)
            bullet(figure, top)
        item[0] = Row(item[0].height, draw)
        blocks.append(Block(item, keep=len(item)))
    return [*blocks, Block([_gap(2 * MM)])] if blocks else []


def _image(png: bytes, max_height: float) -> list[Row]:
    from matplotlib.image import imread

    try:
        pixels = imread(BytesIO(png), format="png")
    except Exception:  # A broken image leaves the section text in place.
        return []
    pixel_h, pixel_w = pixels.shape[:2]
    width = TEXT_W
    height = width * pixel_h / pixel_w
    if height > max_height:
        width, height = width * max_height / height, max_height

    def draw(figure: Figure, top: float) -> None:
        left = MARGIN_X + (TEXT_W - width) / 2
        axis = figure.add_axes((left / PAGE_W, (top - height) / PAGE_H, width / PAGE_W, height / PAGE_H))
        axis.imshow(pixels, interpolation="lanczos")
        axis.set_axis_off()
    return [Row(height, draw), _gap(3 * MM)]


_box_ids = count(1)


def _boxed(rows: list[Row]) -> list[Row]:
    """Rows of one shaded box; each box has its own id, so two boxes on a page are drawn separately."""
    box = next(_box_ids)
    return [Row(row.height, row.draw, row.gap, boxed=box) for row in rows]


@dataclass
class Block:
    rows: list[Row]
    keep: int = 0  # Number of leading rows that must share a page.
    new_page: bool = False


PAGE_BREAK = Block([], new_page=True)


def _item(rows: list[Row]) -> Block:
    # `.item { break-inside: avoid; }` in report.css.
    return Block(rows, keep=len(rows))


def _section(heading: str, *blocks: Block | list[Row]) -> list[Block]:
    """A heading kept together with the start of its content, as `h2 { break-after: avoid; }`."""
    items = [block if isinstance(block, Block) else Block(block) for block in blocks if block]
    title = _heading(heading, 2)
    if not items:
        return [Block(title, keep=len(title))]
    first = items[0]
    lead = len(title) + (first.keep or min(len(first.rows), 3))
    return [Block(title + first.rows, keep=lead), *items[1:]]


def _masthead(title: str, identity: Iterable[tuple[str, str]], overline: str = "VEDRA") -> Block:
    return Block([*_lines(overline, 8, bold=True, color=ACCENT, after=0), *_heading(title, 1), *_pairs(identity)])


def _assessment(report: Report, heading: str) -> list[Block]:
    """The full KBW assessment for a crop in the shaded summary box."""
    kbw = report.assessment.kbw
    last_period, last_balance = last_kbw(report)
    summary = [_gap(1 * MM), *_heading(heading, 2, SUMMARY)[1:],
               *_lines(text.PDF_VERDICT_LABELS[kbw.verdict], bold=True, frame=SUMMARY, after=1 * MM),
               *_lines(report.summary, frame=SUMMARY)]
    if kbw.explanation_pl != report.summary:
        summary += _lines(kbw.explanation_pl, frame=SUMMARY)
    summary += _lines(text.PDF_KBW_DEFINITION, 8.5, color=MUTED, frame=SUMMARY)
    summary += _pairs(assessment_rows(report), frame=SUMMARY)
    if last_period and last_balance:
        summary += _heading("Ostatnia dostępna ocena KBW", 3, SUMMARY)
        summary += _pairs([("Okres oceny", display_value(last_period.value)),
                           ("Wynik", metric_text(last_balance))], frame=SUMMARY)
    summary.append(_gap(2 * MM))
    return [Block([_gap(4 * MM)]), Block(_boxed(summary), keep=min(len(summary), 8))]


def _map(map_png: bytes | None) -> list[Block]:
    location = _image(map_png, MAP_MAX_H) if map_png else []
    return _section("Położenie działki", location or _lines("Mapa była niedostępna podczas tworzenia raportu."))


Varies = Callable[[Signal | Cause | Recommendation], bool]


def _never(_: Signal | Cause | Recommendation) -> bool:
    return False


def _crop_values_note(items: Iterable[Signal | Cause | Recommendation], varies: Varies) -> list[Row]:
    """Said once per section: values that differ by crop are given in each crop part."""
    return _lines(text.PDF_CROP_VALUES_NOTE, 8.5, color=MUTED, after=2 * MM) if any(map(varies, items)) else []


def _signals(signals: Sequence[Signal], heading: str = "Wskaźniki", varies: Varies = _never) -> list[Block]:
    if not signals:
        return []
    return _section(heading, _crop_values_note(signals, varies), *(
        _item(_lines(signal.summary_pl, lead=f"{text.PDF_STATUS_LABELS[signal.status.value]}.")
              + _metrics(signal.metrics) + [_gap(1 * MM)])
        for signal in signals
    ))


def _vulnerability(report: Report) -> list[Block]:
    history = report.assessment.vulnerability
    if not history:
        return []
    last_period, last_balance = last_kbw(report)
    hidden = {"kbw_last_period", "kbw_last_balance"} if last_period and last_balance else set()
    chart = monthly_risk_png(report)
    years = _pairs(history_year_rows(report))
    return _section("Podatność w poprzednich latach",
                    _lines(history.summary_pl) + years,
                    Block(_image(chart, CHART_MAX_H) if chart else []),
                    _metrics(metric for metric in history.metrics if metric.code not in hidden))


def _causes(causes: Sequence[Cause], heading: str = "Przyczyny niedoboru wody", varies: Varies = _never) -> list[Block]:
    if not causes:
        return []
    return _section(heading, _crop_values_note(causes, varies), *(
        _item(_heading(cause.title_pl, 3) + _lines(cause.explanation_pl) + _metrics(cause.evidence))
        for cause in causes
    ))


def _recommendations(groups: Sequence[CategoryGroup], items: Sequence[Recommendation],
                     references: Sequence[Reference], heading: str, empty: str | None,
                     varies: Varies = _never) -> list[Block]:
    """Actions grouped by category (grouping.plan_actions, as the web report); a repeated location-specific
    action is written once, then its site map and the numbered site table."""
    by_id = {reference.id: reference for reference in references}
    blocks: list[Block | list[Row]] = []
    for category in groups:
        title = _lines(category.title.upper(), 8.5, bold=True, color=ACCENT, after=1 * MM)
        for index, planned in enumerate(category.actions):
            action, item = planned.action, planned.recommendation
            rows = (title if index == 0 else []) + _heading(item.title_pl, 3) + _lines(action.action_pl)
            rows += _lines(item.why_pl)
            rows += _metrics(action.evidence)
            for reference_id in item.reference_ids:
                if reference := by_id.get(reference_id):
                    rows += _lines(reference.title_pl, 8.5, color=LINK, url=reference.url, after=0)
            if not action.sites:
                blocks.append(_item(rows + [_gap(3 * MM)]))
                continue
            blocks.append(_item(rows + [_gap(1 * MM)]))
            if isinstance(planned.site_map, bytes):
                figure = _image(planned.site_map, SITE_MAP_MAX_H)
                if figure:
                    blocks.append(_item(figure[:1] + _lines(text.PDF_SITE_MAP_CAPTION, 8.5, color=MUTED,
                                                            after=2 * MM)))
            blocks += _site_table(planned)
            blocks.append([_gap(3 * MM)])
    if not blocks:
        return [] if empty is None else _section(heading, _lines(empty))
    return _section(heading, _crop_values_note(items, varies), *blocks)


def _site_table(planned: PlannedAction) -> list[Block]:
    """`.site-table` in report.css: number and coordinates, notes and evidence, and a box to tick for
    retention sites drawn on the map."""
    size, pad = 8.5, 1.5 * MM
    line_h = size * LINE_HEIGHT
    shares = (0.26, 0.6, 0.14) if planned.field_check else (0.26, 0.74)
    widths = [share * TEXT_W for share in shares]
    lefts = [MARGIN_X + sum(widths[:index]) for index in range(len(widths))]
    regular, bold = _font(size), _font(size, True)

    def wrap(parts: Sequence[tuple[str, FontProperties]], width: float) -> list[tuple[str, FontProperties]]:
        return [(line, font) for value, font in parts if value for line in _wrap(value, font, width - 2 * pad)]

    def row(cells: Sequence[Sequence[tuple[str, FontProperties]]], header: bool = False,
            checkbox: bool = False) -> Row:
        wrapped = [wrap(cell, width) for cell, width in zip(cells, widths)]
        height = max(1, *(len(lines) for lines in wrapped)) * line_h + 2 * MM

        def draw(figure: Figure, top: float) -> None:
            if header:
                figure.add_artist(Rectangle((MARGIN_X / PAGE_W, (top - height) / PAGE_H), TEXT_W / PAGE_W,
                                            height / PAGE_H, facecolor=SUMMARY_BG, edgecolor="none", zorder=-1))
            for lines, left in zip(wrapped, lefts):
                for index, (line, font) in enumerate(lines):
                    _text(figure, left + pad, top - 1 * MM - size * 1.1 - index * line_h, line, font,
                          MUTED if header else INK)
            if checkbox:
                side = 3 * MM
                x = lefts[-1] + widths[-1] / 2 - side / 2
                figure.add_artist(Rectangle((x / PAGE_W, (top - 1.4 * MM - side) / PAGE_H), side / PAGE_W,
                                            side / PAGE_H, facecolor="none", edgecolor=MUTED, linewidth=0.75))
            figure.add_artist(_rule(top - height + 0.3, RULE if header else RULE_LIGHT))
        return Row(height, draw)

    header = row([[(name, bold)] for name in text.PDF_SITE_COLUMNS[:len(shares)]], header=True)
    rows = []
    for site in planned.action.sites:
        on_map = site.number in planned.coordinates
        place = [(str(site.number), bold), (planned.coordinates.get(site.number, text.PDF_SITE_NOT_ON_MAP), regular)]
        evidence = " · ".join(f"{metric.label_pl}: {metric_text(metric)}" for metric in site.evidence)
        notes = [(site.note_pl, regular), (evidence, regular)]
        if not site.evidence and not site.note_pl:
            notes = [(text.PDF_SITE_SHARED_EVIDENCE, regular)]
        rows.append(row([place, notes, []][:len(shares)], checkbox=planned.field_check and on_map))
    first, *others = rows
    return [Block([_gap(1 * MM), header, first], keep=3), *(Block([item], keep=1) for item in others)]


def _field_plan(plan: FieldPlan | None) -> list[Block]:
    """`.field-plan` in report.css: where to start the field visit, in a shaded box."""
    if plan is None:
        return []
    item = plan.action.recommendation
    rows = [_gap(1 * MM), *_heading(text.PDF_FIELD_PLAN_HEADING, 2, SUMMARY)[1:],
            *_lines(f"{item.title_pl} · Miejsce {plan.site.number}", lead=text.PDF_FIELD_PLAN_START,
                    frame=SUMMARY, after=1 * MM),
            *_lines(item.why_pl, frame=SUMMARY, after=1 * MM)]
    if plan.site.note_pl:
        rows += _lines(plan.site.note_pl, frame=SUMMARY, after=1 * MM)
    rows += _lines(text.PDF_FIELD_PLAN_COUNT.format(count=plan.count), 8.5, color=MUTED, frame=SUMMARY, after=0)
    rows.append(_gap(2 * MM))
    return [Block([_gap(4 * MM)]), Block(_boxed(rows), keep=len(rows))]


def _irrigation(irrigation: IrrigationAdvice | None) -> list[Block]:
    if not irrigation:
        return []
    return _section("Ocena nawadniania", _lines(irrigation.why_pl) + _pairs(irrigation_rows(irrigation)))


def _scenarios(scenarios: ScenarioReport | None) -> list[Block]:
    """"Co jeśli?" scenario simulation, as the `scenarios` macro in _parts.html.j2."""
    if scenarios is None:
        return []
    custom = scenario_custom(scenarios)
    note = scenarios.window_note_pl.lower().replace(".", "")
    intro = ("Jak zmieniłyby się stres wodny uprawy i bilans wody na polu przy różnych działaniach. "
             f"Okres: {scenarios.window_start} - {scenarios.window_end} ({note}).")
    rows = _lines(intro, after=1 * MM if custom else 2 * MM)
    if custom:
        rows += _lines(f"Twój wariant: {scenario_levers_text(custom.levers)}.")
    variants = scenario_variant_rows(scenarios)
    shares = (0.32, 0.18, 0.16, 0.18, 0.16)
    table = _table([(name, share, "left" if index == 0 else "right")
                    for index, (name, share) in enumerate(zip(SCENARIO_COLUMNS, shares))],
                   [cells for _, cells in variants], size=8.5, strong=[strong for strong, _ in variants])
    chart = scenario_png(scenarios.baseline, custom)
    budget_columns = [("Bilans wody (mm)", 0.5, "left"), ("Bez działań", 0.25, "right")]
    if custom:
        budget_columns.append(("Twój wariant", 0.25, "right"))
    budget = _table(budget_columns, scenario_budget_rows(scenarios), size=8.5)
    blocks: list[Block | list[Row]] = [rows, Block(table, keep=len(table))]
    if chart:
        blocks.append(Block(_image(chart, SCENARIO_CHART_MAX_H)))
    blocks += [Block(budget, keep=len(budget)), _lines(scenarios.kbw_note_pl, 8.5, color=MUTED),
               Block(_heading("Założenia modelu", 3))]
    blocks += _bullets(((item, None) for item in scenarios.assumptions_pl), 8.5)
    return _section("Co jeśli? Symulacja działań", *blocks)


def _appendix(limitations: Sequence[str], sources: Sequence[Provenance],
              references: Sequence[Reference]) -> list[Block]:
    blocks = _section("Ograniczenia oceny", *_bullets((note, None) for note in limitations)) if limitations else []
    items = []
    for source in sources:
        first, second, third = source_lines(source)
        items.append(_item(_lines(first, 8.5, bold=True, color=LINK, url=source.url, after=0)
                           + _lines(second, 8.5, after=0) + _lines(third, 8.5, after=3 * MM)))
    blocks += _section("Źródła danych", *(
        items or [_lines("Źródła danych przestrzennych i pogodowych były niedostępne.", 8.5)]
    ))
    blocks += _section("Odniesienia", *_bullets(((ref.title_pl, ref.url) for ref in references), 8.5))
    return blocks


def _report_blocks(report: Report, map_png: bytes | None, anchor_prefix: str = "",
                   scenarios: ScenarioReport | None = None) -> list[Block]:
    groups = plan_actions(report.recommendations, report.parcel.geometry_wgs84, png=True,
                          anchor_prefix=anchor_prefix)
    return [
        _masthead(TITLE, [*parcel_rows(report.parcel), ("Uprawa", report.crop_name_pl),
                          ("Data analizy", str(report.analysis_date))]),
        *_assessment(report, "Sytuacja wodna działki"),
        *_map(map_png),
        *_signals(report.assessment.signals),
        *_vulnerability(report),
        *_causes(report.causes),
        *_field_plan(field_plan(groups)),
        *_recommendations(groups, report.recommendations, report.references, "Zalecane działania",
                          "Dostępne dane nie pozwalają wskazać działań dla działki."),
        *_irrigation(report.irrigation),
        *_scenarios(scenarios),
        *_appendix(report.limitations_pl, report.data_sources, report.references),
    ]


def _table(columns: Sequence[tuple[str, float, str]], rows: Sequence[Sequence[str]], size: float = 9,
           strong: Sequence[bool] = ()) -> list[Row]:
    """A simple table: ``columns`` are (header, share of the text width, horizontal alignment);
    rows flagged in ``strong`` are bold on a light background, as `.table tr.strong` in report.css."""
    pad = 2 * MM
    widths = [share * TEXT_W for _, share, _ in columns]
    lefts = [MARGIN_X + sum(widths[:index]) for index in range(len(widths))]
    line_h = size * LINE_HEIGHT

    def row(cells: Sequence[str], font: FontProperties, color: str, rule: str, shade: bool = False) -> Row:
        wrapped = [_wrap(cell, font, width - pad) for cell, width in zip(cells, widths)]
        height = max(len(lines) for lines in wrapped) * line_h + 1.6 * MM

        def draw(figure: Figure, top: float) -> None:
            if shade:
                figure.add_artist(Rectangle((MARGIN_X / PAGE_W, (top - height) / PAGE_H), TEXT_W / PAGE_W,
                                            height / PAGE_H, facecolor="#f2f8f6", edgecolor="none", zorder=-1))
            for lines, left, width, (_, _, align) in zip(wrapped, lefts, widths, columns):
                x = left + width - pad / 2 if align == "right" else left
                for index, line in enumerate(lines):
                    _text(figure, x, top - 0.8 * MM - size * 1.1 - index * line_h, line, font, color, ha=align)
            figure.add_artist(_rule(top - height + 0.3, rule))
        return Row(height, draw)

    header = row([name for name, _, _ in columns], _font(size - 1, True), MUTED, RULE)
    flags = [*strong, *[False] * (len(rows) - len(strong))]
    body = [row(cells, _font(size, bold), INK, RULE_LIGHT, shade=bold) for cells, bold in zip(rows, flags)]
    return [_gap(1 * MM), header, *body, _gap(3 * MM)]


def _overview(document: CombinedReport) -> list[Row]:
    return _table(OVERVIEW_COLUMNS, [overview_row(part.report) for part in document.crops])


def _crop_values(values: Sequence[CropValue]) -> list[Block]:
    if not values:
        return []
    return _section(text.PDF_CROP_VALUES_HEADING, _lines(text.PDF_CROP_VALUES_INTRO), *(
        _item(_pairs([(value.metric.label_pl, metric_text(value.metric))], after=0)
              + _lines(text.PDF_CROP_VALUES_APPLIES.format(items=", ".join(value.applies_to)), 8.5, color=MUTED,
                       after=2 * MM))
        for value in values
    ))


def _part_title(overline: str, title: str) -> Block:
    rows = [*_lines(overline, 8, bold=True, color=ACCENT, after=0), *_heading(title, 1)]
    return Block(rows, keep=len(rows))


def _combined_blocks(document: CombinedReport) -> list[Block]:
    """General part, one part per crop from a new page, then the shared appendix."""
    crops = document.crop_names
    parcel = document.parcel.geometry_wgs84
    shared = plan_actions(document.recommendations, parcel, png=True, anchor_prefix="wspolne-")
    crop_groups = [plan_actions(part.recommendations, parcel, png=True, anchor_prefix=f"uprawa-{index}-")
                   for index, part in enumerate(document.crops, start=1)]
    blocks = [
        _masthead(TITLE, [*parcel_rows(document.parcel), ("Uprawy", ", ".join(crops)),
                          ("Data analizy", str(document.analysis_date))],
                  overline=f"VEDRA · {text.PDF_PART_GENERAL.upper()}"),
        *_section("Podsumowanie dla upraw", _lines(text.PDF_COMBINED_OVERVIEW), _overview(document)),
        *_map(document.map_png),
        *_signals(document.signals, "Wskaźniki dla działki", document.has_crop_values),
        *_causes(document.causes, "Przyczyny niedoboru wody wspólne dla upraw", document.has_crop_values),
        # One field visit plan for the parcel, over shared and crop actions (as in combined.html.j2).
        *_field_plan(field_plan(shared, *crop_groups)),
        *_recommendations(shared, document.recommendations, document.references,
                          "Działania zalecane dla wszystkich upraw", None, document.has_crop_values),
        *_irrigation(document.irrigation),
    ]
    for index, (part, groups) in enumerate(zip(document.crops, crop_groups), start=1):
        blocks += [PAGE_BREAK, _part_title(f"VEDRA · UPRAWA {index} Z {len(crops)}", part.report.crop_name_pl)]
        blocks += _assessment(part.report, "Ocena dla uprawy")
        blocks += _vulnerability(part.report)
        blocks += _crop_values(part.values)
        blocks += _signals(part.signals, "Wskaźniki dla uprawy")
        blocks += _causes(part.causes, "Przyczyny dotyczące uprawy")
        blocks += _recommendations(groups, part.recommendations, document.references, "Działania dla uprawy",
                                   text.PDF_CROP_NO_EXTRA_ACTIONS)
        blocks += _irrigation(part.irrigation)
    blocks += [PAGE_BREAK, _part_title(f"VEDRA · {text.PDF_PART_APPENDIX.upper()}", text.PDF_PART_APPENDIX)]
    blocks += _appendix(document.limitations, document.data_sources, document.references)
    return blocks


class _Layout:
    """Flow rows onto A4 pages, top to bottom."""

    def __init__(self) -> None:
        self.pages: list[list[tuple[Row, float]]] = []
        self.new_page()

    def new_page(self) -> None:
        self.pages.append([])
        self.y = PAGE_H - MARGIN_TOP

    @property
    def at_top(self) -> bool:
        return not self.pages[-1]

    def _fits(self, height: float) -> bool:
        return height <= self.y - MARGIN_BOTTOM + 0.01

    def add(self, block: Block) -> None:
        if block.new_page:
            if not self.at_top:
                self.new_page()
            return
        keep = sum(row.height for row in block.rows[:block.keep])
        if block.keep and not self._fits(keep) and not self.at_top and keep <= CONTENT_H:
            self.new_page()
        for row in block.rows:
            if not self._fits(row.height) and not self.at_top:
                self.new_page()
            if row.gap and self.at_top:
                continue  # No leading space at the top of a page.
            self.pages[-1].append((row, self.y))
            self.y -= row.height


def _draw_page(figure: Figure, rows: list[tuple[Row, float]], number: int, total: int) -> None:
    for box in sorted({row.boxed for row, _ in rows if row.boxed}):
        boxed = [(row, top) for row, top in rows if row.boxed == box]
        # `.summary` / `.field-plan` in report.css: a shaded box with an accent bar, split at page breaks.
        top = max(top for _, top in boxed)
        bottom = min(top - row.height for row, top in boxed)
        figure.add_artist(Rectangle((MARGIN_X / PAGE_W, bottom / PAGE_H), TEXT_W / PAGE_W, (top - bottom) / PAGE_H,
                                    facecolor=SUMMARY_BG, edgecolor="none", zorder=-2))
        figure.add_artist(Rectangle((MARGIN_X / PAGE_W, bottom / PAGE_H), 1.1 * MM / PAGE_W, (top - bottom) / PAGE_H,
                                    facecolor=ACCENT, edgecolor="none", zorder=-1))
    for row, top in rows:
        if row.draw is not None:
            row.draw(figure, top)
    footer_y = MARGIN_BOTTOM - 9 * MM
    _text(figure, MARGIN_X, footer_y, FOOTER, _font(8), MUTED)
    _text(figure, MARGIN_X + TEXT_W, footer_y, f"{number} / {total}", _font(8), MUTED, ha="right")


def _document_blocks(items: Sequence[tuple[Report, bytes | None]],
                     scenarios: ScenarioReport | None = None) -> list[Block]:
    document = combine(items)
    if document is not None:
        return _combined_blocks(document)
    # Reports of different parcels or dates are kept whole, each from a new page.
    blocks: list[Block] = []
    for index, (report, map_png) in enumerate(items):
        blocks += [PAGE_BREAK] if index else []
        # "Co jeśli?" belongs to a single report; the API offers it only for one analysis.
        blocks += _report_blocks(report, map_png, f"{index}-" if len(items) > 1 else "",
                                 scenarios if len(items) == 1 else None)
    return blocks


def pages(items: Sequence[tuple[Report, bytes | None]],
          scenarios: ScenarioReport | None = None) -> Iterator[Figure]:
    """Lay out the reports and yield one figure per A4 page."""
    layout = _Layout()
    for block in _document_blocks(items, scenarios):
        layout.add(block)
    total = len(layout.pages)
    for number, rows in enumerate(layout.pages, start=1):
        figure = Figure(figsize=(PAGE_W / 72, PAGE_H / 72))
        _draw_page(figure, rows, number, total)
        yield figure


def render_many(items: Sequence[tuple[Report, bytes | None]], scenarios: ScenarioReport | None = None) -> bytes:
    """Render reports into one PDF; several crops of one parcel share the general part and appendix."""
    output = BytesIO()
    with PdfPages(output, metadata={"Title": f"Vedra | {TITLE}", "Creator": "Vedra"}) as document:
        for figure in pages(items, scenarios):
            document.savefig(figure)
    return output.getvalue()


def render(report: Report, map_png: bytes | None = None, scenarios: ScenarioReport | None = None) -> bytes:
    return render_many([(report, map_png)], scenarios)
