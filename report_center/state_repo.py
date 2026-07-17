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
            self._migrate_old_tables(conn)
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS report_jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    report_type TEXT NOT NULL DEFAULT 'torque',
                    line_code TEXT NOT NULL,
                    base_barcode TEXT NOT NULL,
                    product_serial_no TEXT,
                    status TEXT NOT NULL,
                    report_path TEXT,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(report_type, line_code, base_barcode)
                );

                CREATE TABLE IF NOT EXISTS generated_reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    report_type TEXT NOT NULL DEFAULT 'torque',
                    product_serial_no TEXT NOT NULL,
                    line_code TEXT NOT NULL,
                    base_barcode TEXT NOT NULL,
                    report_path TEXT NOT NULL,
                    generated_at TEXT NOT NULL,
                    UNIQUE(report_type, product_serial_no)
                );
                """
            )

    def _migrate_old_tables(self, conn: sqlite3.Connection) -> None:
        self._migrate_table_if_missing_report_type(
            conn,
            "report_jobs",
            """
            CREATE TABLE report_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_type TEXT NOT NULL DEFAULT 'torque',
                line_code TEXT NOT NULL,
                base_barcode TEXT NOT NULL,
                product_serial_no TEXT,
                status TEXT NOT NULL,
                report_path TEXT,
                last_error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(report_type, line_code, base_barcode)
            )
            """,
            """
            INSERT INTO report_jobs(
                id, report_type, line_code, base_barcode, product_serial_no,
                status, report_path, last_error, created_at, updated_at
            )
            SELECT id, 'torque', line_code, base_barcode, product_serial_no,
                   status, report_path, last_error, created_at, updated_at
            FROM report_jobs_old
            """,
        )
        self._migrate_table_if_missing_report_type(
            conn,
            "generated_reports",
            """
            CREATE TABLE generated_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_type TEXT NOT NULL DEFAULT 'torque',
                product_serial_no TEXT NOT NULL,
                line_code TEXT NOT NULL,
                base_barcode TEXT NOT NULL,
                report_path TEXT NOT NULL,
                generated_at TEXT NOT NULL,
                UNIQUE(report_type, product_serial_no)
            )
            """,
            """
            INSERT INTO generated_reports(
                id, report_type, product_serial_no, line_code,
                base_barcode, report_path, generated_at
            )
            SELECT id, 'torque', product_serial_no, line_code,
                   base_barcode, report_path, generated_at
            FROM generated_reports_old
            """,
        )

    def _migrate_table_if_missing_report_type(
        self,
        conn: sqlite3.Connection,
        table_name: str,
        create_sql: str,
        copy_sql: str,
    ) -> None:
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table_name,),
        ).fetchone()
        if not exists:
            return
        columns = [row["name"] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()]
        if "report_type" in columns:
            return
        conn.execute(f"ALTER TABLE {table_name} RENAME TO {table_name}_old")
        conn.execute(create_sql)
        conn.execute(copy_sql)
        conn.execute(f"DROP TABLE {table_name}_old")

    def has_generated(self, product_serial_no: str, report_type: str = "torque") -> bool:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT 1 FROM generated_reports
                WHERE product_serial_no = ? AND report_type = ?
                """,
                (product_serial_no, report_type),
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
        report_type: str = "torque",
    ) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO report_jobs(
                    report_type, line_code, base_barcode, product_serial_no, status,
                    report_path, last_error, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(report_type, line_code, base_barcode) DO UPDATE SET
                    product_serial_no = excluded.product_serial_no,
                    status = excluded.status,
                    report_path = excluded.report_path,
                    last_error = excluded.last_error,
                    updated_at = excluded.updated_at
                """,
                (
                    report_type,
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
        status: str = "已生成",
        report_type: str = "torque",
    ) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO generated_reports(
                    report_type, product_serial_no, line_code, base_barcode, report_path, generated_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (report_type, product_serial_no, line_code, base_barcode, report_path, now),
            )
        self.mark_status(line_code, base_barcode, status, product_serial_no, report_path, report_type=report_type)

    def report_by_serial(self, product_serial_no: str, report_type: str = "torque") -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT * FROM generated_reports
                WHERE product_serial_no = ? AND report_type = ?
                """,
                (product_serial_no, report_type),
            ).fetchone()

    def generated_by_job(
        self,
        report_type: str,
        line_code: str,
        base_barcode: str,
    ) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT * FROM generated_reports
                WHERE report_type = ? AND line_code = ? AND base_barcode = ?
                ORDER BY generated_at DESC
                LIMIT 1
                """,
                (report_type, line_code, base_barcode),
            ).fetchone()

    def job_by_id(self, job_id: int) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM report_jobs WHERE id = ?",
                (job_id,),
            ).fetchone()

    def delete_job(self, job_id: int, delete_generated: bool = True) -> sqlite3.Row | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM report_jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
            if not row:
                return None
            conn.execute("DELETE FROM report_jobs WHERE id = ?", (job_id,))
            if delete_generated and row["product_serial_no"]:
                conn.execute(
                    """
                    DELETE FROM generated_reports
                    WHERE product_serial_no = ?
                    """,
                    (row["product_serial_no"],),
                )
            return row

    def update_report_path_by_serial(
        self,
        product_serial_no: str,
        report_path: str,
        status: str,
        report_type: str = "torque",
    ) -> None:
        candidates = [product_serial_no]
        if not product_serial_no.endswith("%"):
            candidates.append(f"{product_serial_no}%")
        with self.connect() as conn:
            row = None
            matched_serial = product_serial_no
            for candidate in candidates:
                row = conn.execute(
                    """
                    SELECT product_serial_no, line_code, base_barcode
                    FROM generated_reports
                    WHERE product_serial_no = ? AND report_type = ?
                    """,
                    (candidate, report_type),
                ).fetchone()
                if row:
                    matched_serial = row["product_serial_no"]
                    break
            conn.execute(
                """
                UPDATE generated_reports
                SET report_path = ?
                WHERE product_serial_no = ? AND report_type = ?
                """,
                (report_path, matched_serial, report_type),
            )
        if row:
            self.mark_status(
                row["line_code"],
                row["base_barcode"],
                status,
                matched_serial,
                report_path,
                report_type=report_type,
            )
            if report_type == "combined":
                for related_type in ("torque", "coating"):
                    self.mark_status(
                        row["line_code"],
                        row["base_barcode"],
                        status,
                        matched_serial,
                        report_path,
                        report_type=related_type,
                    )

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

    def waiting_jobs(self, limit: int = 500) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT * FROM report_jobs
                WHERE status = '等待MES匹配'
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

    def search_jobs(
        self,
        base_barcode: str = "",
        product_serial_no: str = "",
        material_no: str = "",
        report_type: str = "",
        status: str = "",
        start_date: str | None = None,
        end_date: str | None = None,
        keyword: str = "",
        limit: int = 2000,
    ) -> list[sqlite3.Row]:
        where = []
        params = []
        if base_barcode.strip():
            where.append("UPPER(base_barcode) LIKE UPPER(?)")
            params.append(f"%{base_barcode.strip()}%")
        if product_serial_no.strip():
            where.append("UPPER(COALESCE(product_serial_no, '')) LIKE UPPER(?)")
            params.append(f"%{product_serial_no.strip()}%")
        if material_no.strip():
            where.append("UPPER(COALESCE(product_serial_no, '')) LIKE UPPER(?)")
            params.append(f"%{material_no.strip()}%")
        if report_type.strip():
            where.append("report_type = ?")
            params.append(report_type.strip())
        if status.strip():
            where.append("status LIKE ?")
            params.append(f"%{status.strip()}%")
        if start_date:
            where.append("date(updated_at) >= date(?)")
            params.append(start_date)
        if end_date:
            where.append("date(updated_at) <= date(?)")
            params.append(end_date)
        if keyword.strip():
            where.append(
                """
                (
                    line_code LIKE ? OR report_path LIKE ?
                    OR last_error LIKE ?
                )
                """
            )
            value = f"%{keyword.strip()}%"
            params.extend([value, value, value])
        sql = "SELECT * FROM report_jobs"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)
        with self.connect() as conn:
            return conn.execute(sql, tuple(params)).fetchall()

    def generated_serials(self) -> set[str]:
        with self.connect() as conn:
            rows = conn.execute("SELECT product_serial_no FROM generated_reports").fetchall()
            return {str(row["product_serial_no"]) for row in rows}
