"""Persist completed analyses and their report artifacts in SQLite."""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from tempfile import NamedTemporaryFile

from app.contracts.geo import GeoBundle
from app.contracts.report import Report


@dataclass(frozen=True, slots=True)
class StoredReport:
    report: Report
    analysis_id: str
    progress: list[str]
    bundle: GeoBundle | None


class ReportStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.pdf_dir = self.db_path.with_suffix(".reports")
        with closing(sqlite3.connect(self.db_path)) as connection, connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS reports (
                    report_id TEXT PRIMARY KEY,
                    analysis_id TEXT NOT NULL UNIQUE,
                    report_json TEXT NOT NULL,
                    progress_json TEXT NOT NULL,
                    geo_json TEXT
                )
            """)

    def save_report(self, report: Report, analysis_id: str, progress: list[str], bundle: GeoBundle | None) -> None:
        with closing(sqlite3.connect(self.db_path)) as connection, connection:
            connection.execute("""
                INSERT INTO reports (report_id, analysis_id, report_json, progress_json, geo_json)
                VALUES (?, ?, ?, ?, ?)
            """, (report.report_id, analysis_id, report.model_dump_json(), json.dumps(progress, ensure_ascii=False),
                  bundle.model_dump_json() if bundle is not None else None))

    def _select(self, sql: str, identifier: str) -> StoredReport | None:
        with closing(sqlite3.connect(self.db_path)) as connection:
            row = connection.execute(sql, (identifier,)).fetchone()
        if row is None:
            return None
        report_json, analysis_id, progress_json, geo_json = row
        return StoredReport(
            Report.model_validate_json(report_json), analysis_id, json.loads(progress_json),
            GeoBundle.model_validate_json(geo_json) if geo_json else None,
        )

    def get_report(self, report_id: str) -> StoredReport | None:
        return self._select(
            "SELECT report_json, analysis_id, progress_json, geo_json FROM reports WHERE report_id = ?", report_id
        )

    def by_analysis(self, analysis_id: str) -> StoredReport | None:
        return self._select(
            "SELECT report_json, analysis_id, progress_json, geo_json FROM reports WHERE analysis_id = ?", analysis_id
        )

    def _pdf_path(self, report_id: str) -> Path:
        return self.pdf_dir / f"{sha256(report_id.encode()).hexdigest()}.pdf"

    def get_pdf(self, report_id: str) -> bytes | None:
        try:
            return self._pdf_path(report_id).read_bytes()
        except FileNotFoundError:
            return None

    def save_pdf(self, report_id: str, pdf: bytes) -> None:
        self.pdf_dir.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(dir=self.pdf_dir, suffix=".pdf.tmp", delete=False) as stream:
            temporary = Path(stream.name)
            try:
                stream.write(pdf)
            except BaseException:
                stream.close()
                temporary.unlink(missing_ok=True)
                raise
        try:
            temporary.replace(self._pdf_path(report_id))
        finally:
            temporary.unlink(missing_ok=True)
