"""Render reports to PDF with matplotlib alone.

WeasyPrint needs the native Pango libraries, which the Docker image provides but a plain Windows or
macOS Python install usually lacks. This renderer needs nothing beyond matplotlib, already a
dependency, so a PDF is always available. Its sections and wording follow templates/report.html.j2.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass
from functools import cache, lru_cache
from io import BytesIO

from matplotlib.backends.backend_agg import RendererAgg
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.figure import Figure
from matplotlib.font_manager import FontProperties
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle

from app.contracts.report import Metric, Report
from app.recommendations import texts_pl as text
from app.reports.charts import monthly_risk_png
from app.reports.formatting import display_value, source_time

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


@cache
def _font(size: float, bold: bool = False) -> FontProperties:
    # DejaVu Sans ships with matplotlib and covers Polish diacritics, as in report.css.
    return FontProperties(family="DejaVu Sans", size=size, weight="bold" if bold else "normal")


@cache
def _renderer() -> RendererAgg:
    # At 72 dpi one pixel equals one point, so measurements match the page coordinates.
    return RendererAgg(1, 1, 72)


@lru_cache(maxsize=8192)
def _width(value: str, font: FontProperties) -> float:
    return _renderer().get_text_width_height_descent(value, font, ismath=False)[0]


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
    space = _width(" ", font)
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
    boxed: bool = False  # Part of the shaded summary box.


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
    lead_w = _width(f"{lead} ", _font(size, True)) if lead else 0
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


def _metric_value(metric: Metric) -> str:
    return display_value(metric.value) + (f" {metric.unit}" if metric.unit else "")


def _pairs(items: Iterable[tuple[str, str]], size: float = 10, frame: Frame = BODY) -> list[Row]:
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
    return [_gap(1 * MM), *rows, _gap(2 * MM)] if rows else []


def _metrics(metrics: Iterable[Metric]) -> list[Row]:
    return _pairs((metric.label_pl, _metric_value(metric)) for metric in metrics)


def _bullets(items: Iterable[tuple[str, str | None]], size: float = 10) -> list[Row]:
    rows = []
    for value, url in items:
        item = _lines(value, size, indent=5 * MM, url=url, color=LINK if url else INK, after=1 * MM)
        bullet = item[0].draw

        def draw(figure: Figure, top: float, bullet=bullet) -> None:
            _text(figure, MARGIN_X + 1.2 * MM, top - size * 1.1, "•", _font(size), INK)
            bullet(figure, top)
        item[0] = Row(item[0].height, draw)
        rows.extend(item)
    return [*rows, _gap(2 * MM)] if rows else []


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


def _boxed(rows: list[Row]) -> list[Row]:
    return [Row(row.height, row.draw, row.gap, boxed=True) for row in rows]


@dataclass
class Block:
    rows: list[Row]
    keep: int = 0  # Number of leading rows that must share a page.


def _item(rows: list[Row]) -> Block:
    # `.item { break-inside: avoid; }` in report.css.
    return Block(rows, keep=len(rows))


def _section(heading: str, *blocks: Block | list[Row]) -> list[Block]:
    """A heading kept together with the start of its content, as `h2 { break-after: avoid; }`."""
    items = [block if isinstance(block, Block) else Block(block) for block in blocks]
    title = _heading(heading, 2)
    if not items:
        return [Block(title, keep=len(title))]
    first = items[0]
    lead = len(title) + (first.keep or min(len(first.rows), 3))
    return [Block(title + first.rows, keep=lead), *items[1:]]


def _report_blocks(report: Report, map_png: bytes | None) -> list[Block]:
    kbw = report.assessment.kbw
    history = report.assessment.vulnerability.metrics if report.assessment.vulnerability else []
    by_code = {metric.code: metric for metric in history}
    last_period, last_balance = by_code.get("kbw_last_period"), by_code.get("kbw_last_balance")
    show_last = last_period is not None and last_balance is not None

    blocks = [Block([
        *_lines("VEDRA", 8, bold=True, color=ACCENT, after=0),
        *_heading(TITLE, 1),
        *_pairs([
            ("Działka ewidencyjna", report.parcel.parcel_id),
            ("Obręb", display_value(report.parcel.region)),
            ("Uprawa", report.crop_name_pl),
            ("Data analizy", str(report.analysis_date)),
        ]),
    ])]

    summary = [_gap(1 * MM), *_heading("Sytuacja wodna działki", 2, SUMMARY)[1:], *_lines(report.summary, frame=SUMMARY)]
    if kbw.period:
        summary += _lines(f"Okres oceny: {kbw.period.start} – {kbw.period.end}", frame=SUMMARY)
    pairs = []
    if kbw.kbw_mm is not None or (kbw.period and kbw.verdict == "unavailable"):
        pairs.append(("Klimatyczny bilans wodny",
                      display_value(kbw.kbw_mm) + (" mm" if kbw.kbw_mm is not None else "")))
    if isinstance(kbw.threshold_mm, (int, float)) and not isinstance(kbw.threshold_mm, bool):
        pairs.append(("Próg dla uprawy i gleby", f"{display_value(kbw.threshold_mm)} mm"))
    if report.assessment.confidence:
        pairs.append(("Pewność oceny", text.PDF_CONFIDENCE_LABELS[report.assessment.confidence]))
    summary += _pairs(pairs, frame=SUMMARY)
    if show_last:
        summary += _heading("Ostatnia dostępna ocena KBW", 3, SUMMARY)
        summary += _pairs([("Okres oceny", display_value(last_period.value)),
                           ("Wynik", _metric_value(last_balance))], frame=SUMMARY)
    summary.append(_gap(2 * MM))
    blocks += [Block([_gap(4 * MM)]), Block(_boxed(summary), keep=min(len(summary), 8))]

    location = _image(map_png, MAP_MAX_H) if map_png else []
    blocks += _section("Położenie działki",
                       location or _lines("Mapa była niedostępna podczas tworzenia raportu."))

    blocks += _section("Wskaźniki", *(
        _item(_lines(signal.summary_pl, lead=f"{text.PDF_STATUS_LABELS[signal.status.value]}.")
              + _metrics(signal.metrics) + [_gap(1 * MM)])
        for signal in report.assessment.signals
    ))

    if report.assessment.vulnerability:
        chart = monthly_risk_png(report)
        shown = [metric for metric in history
                 if not show_last or metric.code not in {"kbw_last_period", "kbw_last_balance"}]
        blocks += _section("Podatność w poprzednich latach",
                           _lines(report.assessment.vulnerability.summary_pl),
                           Block(_image(chart, CHART_MAX_H) if chart else []),
                           _metrics(shown))

    if report.causes:
        blocks += _section("Przyczyny niedoboru wody", *(
            _item(_heading(cause.title_pl, 3) + _lines(cause.explanation_pl) + _metrics(cause.evidence))
            for cause in report.causes
        ))

    references = {reference.id: reference for reference in report.references}
    recommendations = []
    for item in report.recommendations:
        rows = _lines(text.PDF_CATEGORY_LABELS[item.category], 8, bold=True, color=ACCENT, after=0)
        rows += _heading(item.title_pl, 3) + _lines(item.action_pl) + _lines(item.why_pl) + _metrics(item.evidence)
        for reference_id in item.reference_ids:
            if reference := references.get(reference_id):
                rows += _lines(reference.title_pl, 8.5, color=LINK, url=reference.url, after=0)
        recommendations.append(_item(rows + [_gap(3 * MM)]))
    blocks += _section("Zalecane działania", *(
        recommendations or [_lines("Dostępne dane nie pozwalają wskazać działań dla działki.")]
    ))

    if report.irrigation:
        irrigation = _lines(report.irrigation.why_pl)
        if report.irrigation.suggested_date:
            irrigation += _lines(f"Szacowany termin: {report.irrigation.suggested_date}")
        if report.irrigation.net_dose_mm:
            irrigation += _lines(f"Dawka netto: {display_value(report.irrigation.net_dose_mm)} mm")
        blocks += _section("Ocena nawadniania", irrigation)

    if report.limitations_pl:
        blocks += _section("Ograniczenia oceny", _bullets((note, None) for note in report.limitations_pl))

    sources = []
    for source in report.data_sources:
        first = source.name + (f" · Okres danych: {source.data_period}" if source.data_period else "")
        second = f"Pobranie: {source_time(source.fetched_at)}" + (
            f" · Rozdzielczość: {source.resolution}" if source.resolution else "")
        third = f"Licencja: {source.licence}" + (f" · {source.attribution_pl}" if source.attribution_pl else "")
        sources.append(_item(_lines(first, 8.5, bold=True, color=LINK, url=source.url, after=0)
                             + _lines(second, 8.5, after=0) + _lines(third, 8.5, after=3 * MM)))
    blocks += _section("Źródła danych", *(
        sources or [_lines("Źródła danych przestrzennych i pogodowych były niedostępne.", 8.5)]
    ))
    blocks += _section("Odniesienia", _bullets(((ref.title_pl, ref.url) for ref in report.references), 8.5))
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
    boxed = [(row, top) for row, top in rows if row.boxed]
    if boxed:
        # `.summary` in report.css: a shaded box with an accent bar, split at page breaks.
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


def pages(items: Sequence[tuple[Report, bytes | None]]) -> Iterator[Figure]:
    """Lay out the reports, each from a new page, and yield one figure per A4 page."""
    layout = _Layout()
    for index, (report, map_png) in enumerate(items):
        if index:
            layout.new_page()
        for block in _report_blocks(report, map_png):
            layout.add(block)
    total = len(layout.pages)
    for number, rows in enumerate(layout.pages, start=1):
        figure = Figure(figsize=(PAGE_W / 72, PAGE_H / 72))
        _draw_page(figure, rows, number, total)
        yield figure


def render_many(items: Sequence[tuple[Report, bytes | None]]) -> bytes:
    """Render reports, each from a new page, into one PDF."""
    output = BytesIO()
    with PdfPages(output, metadata={"Title": f"Vedra | {TITLE}", "Creator": "Vedra"}) as document:
        for figure in pages(items):
            document.savefig(figure)
    return output.getvalue()


def render(report: Report, map_png: bytes | None = None) -> bytes:
    return render_many([(report, map_png)])
