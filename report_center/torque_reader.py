from __future__ import annotations

from contextlib import contextmanager
import os
import shutil
import sqlite3
import tempfile

from report_center.config import LineConfig
from report_center.models import TorqueRecord, WorkpieceSummary


@contextmanager
def torque_connection(db_path: str, copy_before_read: bool):
    tmp_path = None
    read_path = db_path
    if copy_before_read:
        if not os.path.exists(db_path):
            raise FileNotFoundError(f"数据库不存在: {db_path}")
        fd, tmp_path = tempfile.mkstemp(prefix="torque_snapshot_", suffix=".db")
        os.close(fd)
        shutil.copy2(db_path, tmp_path)
        read_path = tmp_path

    uri = f"file:{read_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)


class TorqueDataReader:
    def read_workpiece_by_barcode(
        self,
        line: LineConfig,
        base_barcode: str,
        copy_before_read: bool = True,
    ) -> WorkpieceSummary | None:
        if not line.db_path:
            return None
        with torque_connection(line.db_path, copy_before_read) as conn:
            row = conn.execute(
                """
                SELECT
                    w.id,
                    w.base_barcode,
                    w.round2_completed_at,
                    w.round3_completed_at,
                    p.code AS product_code,
                    p.name AS product_name,
                    p.igbt_count,
                    p.screws_per_igbt,
                    (
                        SELECT COUNT(*) FROM tightening_records r
                        WHERE r.workpiece_id = w.id AND r.round_no = 2 AND r.result = 'OK'
                    ) AS round2_ok,
                    (
                        SELECT COUNT(*) FROM tightening_records r
                        WHERE r.workpiece_id = w.id AND r.round_no = 3 AND r.result = 'OK'
                    ) AS round3_ok
                FROM workpieces w
                JOIN product_types p ON p.id = w.product_type_id
                WHERE UPPER(TRIM(w.base_barcode)) = UPPER(TRIM(?))
                ORDER BY w.id DESC
                LIMIT 1
                """,
                (base_barcode,),
            ).fetchone()
            if not row:
                return None
            expected = int(row["igbt_count"]) * int(row["screws_per_igbt"])
            return WorkpieceSummary(
                line_code=line.code,
                line_name=line.name,
                workpiece_id=int(row["id"]),
                base_barcode=str(row["base_barcode"]),
                product_code=str(row["product_code"]),
                product_name=str(row["product_name"]),
                expected_count=expected,
                round2_ok=int(row["round2_ok"]),
                round3_ok=int(row["round3_ok"]),
                round2_completed_at=row["round2_completed_at"],
                round3_completed_at=row["round3_completed_at"],
                records=self._read_records(conn, int(row["id"])),
            )

    def read_completed_workpieces(
        self,
        line: LineConfig,
        copy_before_read: bool = True,
    ) -> list[WorkpieceSummary]:
        with torque_connection(line.db_path, copy_before_read) as conn:
            rows = conn.execute(
                """
                SELECT
                    w.id,
                    w.base_barcode,
                    w.round2_completed_at,
                    w.round3_completed_at,
                    p.code AS product_code,
                    p.name AS product_name,
                    p.igbt_count,
                    p.screws_per_igbt,
                    (
                        SELECT COUNT(*)
                        FROM tightening_records r
                        WHERE r.workpiece_id = w.id
                          AND r.round_no = 2
                          AND r.result = 'OK'
                    ) AS round2_ok,
                    (
                        SELECT COUNT(*)
                        FROM tightening_records r
                        WHERE r.workpiece_id = w.id
                          AND r.round_no = 3
                          AND r.result = 'OK'
                    ) AS round3_ok
                FROM workpieces w
                JOIN product_types p ON p.id = w.product_type_id
                WHERE w.round3_completed_at IS NOT NULL
                ORDER BY w.round3_completed_at DESC, w.id DESC
                """
            ).fetchall()

            result = []
            for row in rows:
                expected = int(row["igbt_count"]) * int(row["screws_per_igbt"])
                if int(row["round2_ok"]) < expected or int(row["round3_ok"]) < expected:
                    continue
                result.append(
                    WorkpieceSummary(
                        line_code=line.code,
                        line_name=line.name,
                        workpiece_id=int(row["id"]),
                        base_barcode=str(row["base_barcode"]),
                        product_code=str(row["product_code"]),
                        product_name=str(row["product_name"]),
                        expected_count=expected,
                        round2_ok=int(row["round2_ok"]),
                        round3_ok=int(row["round3_ok"]),
                        round2_completed_at=row["round2_completed_at"],
                        round3_completed_at=row["round3_completed_at"],
                        records=self._read_records(conn, int(row["id"])),
                    )
                )
            return result

    def _read_records(self, conn: sqlite3.Connection, workpiece_id: int) -> list[TorqueRecord]:
        rows = conn.execute(
            """
            SELECT
                r.round_no,
                r.sequence_no,
                r.program_no,
                r.set_torque,
                r.actual_torque,
                r.actual_angle,
                r.result,
                r.operator_work_no,
                COALESCE(NULLIF(u.name, ''), r.operator_work_no) AS operator_name,
                r.tightened_at
            FROM tightening_records r
            LEFT JOIN users u ON u.work_no = r.operator_work_no
            WHERE r.workpiece_id = ?
            ORDER BY r.round_no, r.sequence_no, r.tightened_at, r.id
            """,
            (workpiece_id,),
        ).fetchall()
        return [
            TorqueRecord(
                round_no=int(row["round_no"]),
                sequence_no=int(row["sequence_no"]),
                program_no=int(row["program_no"]),
                set_torque=float(row["set_torque"]),
                actual_torque=float(row["actual_torque"]),
                actual_angle=float(row["actual_angle"]),
                result=str(row["result"]),
                operator_work_no=str(row["operator_work_no"]),
                operator_name=str(row["operator_name"]),
                tightened_at=str(row["tightened_at"]),
            )
            for row in rows
        ]
