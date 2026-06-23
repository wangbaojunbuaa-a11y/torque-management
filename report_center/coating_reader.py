from __future__ import annotations

import sqlite3

from report_center.config import LineConfig
from report_center.models import CoatingRecordSummary
from report_center.torque_reader import torque_connection


class CoatingDataReader:
    def read_records(
        self,
        line: LineConfig,
        copy_before_read: bool = True,
    ) -> list[CoatingRecordSummary]:
        if not line.coating_db_path:
            return []
        with torque_connection(line.coating_db_path, copy_before_read) as conn:
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(coating_records)").fetchall()}
            grease_batch_sql = "grease_batch_no" if "grease_batch_no" in columns else "'' AS grease_batch_no"
            grease_open_sql = "grease_open_date" if "grease_open_date" in columns else "'' AS grease_open_date"
            coating_method_sql = "coating_method" if "coating_method" in columns else "'' AS coating_method"
            rows = conn.execute(
                f"""
                SELECT
                    id,
                    plate_sn,
                    operator_work_no,
                    operator_name,
                    assistant_work_no,
                    assistant_name,
                    recorded_at,
                    {grease_batch_sql},
                    {grease_open_sql},
                    {coating_method_sql},
                    note
                FROM coating_records
                ORDER BY recorded_at DESC, id DESC
                """
            ).fetchall()
        return [
            CoatingRecordSummary(
                line_code=line.code,
                line_name=line.name,
                record_id=int(row["id"]),
                plate_sn=str(row["plate_sn"]),
                operator_work_no=str(row["operator_work_no"]),
                operator_name=str(row["operator_name"]),
                assistant_work_no=str(row["assistant_work_no"] or ""),
                assistant_name=str(row["assistant_name"] or ""),
                recorded_at=str(row["recorded_at"]),
                note=str(row["note"] or ""),
                grease_batch_no=str(row["grease_batch_no"] or ""),
                grease_open_date=str(row["grease_open_date"] or ""),
                coating_method=str(row["coating_method"] or ""),
            )
            for row in rows
        ]
