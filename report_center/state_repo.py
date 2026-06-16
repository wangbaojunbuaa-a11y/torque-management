from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
import os
import sqlite3
from typing import Iterable


class ReportStateRepository:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def initialize(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS report_jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    line_code TEXT NOT NULL,
                    base_barcode TEXT NOT NULL,
                    product_serial_no TEXT,
                    status TEXT NOT NULL,
                    report_path TEXT,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(line_code, base_barcode)
                );

                CREATE TABLE IF NOT EXISTS generated_reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_serial_no TEXT NOT NULL UNIQUE,
                    line_code TEXT NOT NULL,
                    base_barcode TEXT NOT NULL,
                    report_path TEXT NOT NULL,
                    generated_at TEXT NOT NULL
                );
                """
            )

    def has_generated(self, product_serial_no: str) -> bool:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM generated_reports WHERE product_serial_no = ?",
                (product_serial_no,),
            ).fetchone()
            return row is not None

    def mark_status(
        self,
        line_code: str,
        base_barcode: str,
        status: str,
        product_serial_no: str | None = None,
        report_path: str | None = None,
        last_error: str | None = None,
    ) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO report_jobs(
                    line_code, base_barcode, product_serial_no, status,
                    report_path, last_error, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(line_code, base_barcode) DO UPDATE SET
                    product_serial_no = excluded.product_serial_no,
                    status = excluded.status,
                    report_path = excluded.report_path,
                    last_error = excluded.last_error,
                    updated_at = excluded.updated_at
                """,
                (
                    line_code,
                    base_barcode,
                    product_serial_no,
                    status,
                    report_path,
                    last_error,
                    now,
                    now,
                ),
            )

    def mark_generated(
        self,
        product_serial_no: str,
        line_code: str,
        base_barcode: str,
        report_path: str,
    ) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO generated_reports(
                    product_serial_no, line_code, base_barcode, report_path, generated_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (product_serial_no, line_code, base_barcode, report_path, now),
            )
        self.mark_status(line_code, base_barcode, "已生成", product_serial_no, report_path)

    def recent_jobs(self, limit: int = 200) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT * FROM report_jobs
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

    def generated_serials(self) -> set[str]:
        with self.connect() as conn:
            rows = conn.execute("SELECT product_serial_no FROM generated_reports").fetchall()
            return {str(row["product_serial_no"]) for row in rows}
