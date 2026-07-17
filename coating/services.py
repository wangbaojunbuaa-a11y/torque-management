from __future__ import annotations

from datetime import datetime
import sqlite3

from coating.repository import CoatingRepository


class CoatingRecordService:
    def __init__(self, repo: CoatingRepository) -> None:
        self.repo = repo

    def record_scan(
        self,
        plate_sn: str,
        operator,
        assistant_work_no: str = "",
        note: str = "",
        grease_batch_no: str = "",
        grease_open_date: str = "",
        coating_method: str = "",
    ):
        plate_sn = plate_sn.strip().upper()
        if not plate_sn:
            raise ValueError("水冷基板条码不能为空")
        grease_batch_no = grease_batch_no.strip()
        grease_open_date = grease_open_date.strip()
        coating_method = coating_method.strip()
        if not grease_open_date or not coating_method:
            raise ValueError("请先录入导热硅脂启封日期和涂敷方式")

        existing = self.find_by_plate(plate_sn)
        if existing:
            raise ValueError(
                f"该水冷基板已记录：{existing['recorded_at']}，{existing['operator_name']}"
            )

        assistant = None
        assistant_work_no = assistant_work_no.strip()
        if assistant_work_no:
            assistant = self.repo.fetch_one(
                "SELECT * FROM users WHERE work_no = ? AND active = 1",
                (assistant_work_no,),
            )
            if assistant is None:
                raise ValueError("协作人员工号不存在或未启用")
            if assistant["work_no"] == operator["work_no"]:
                raise ValueError("协作人员不能与当前登录人员相同")

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            record_id = self.repo.execute(
                """
                INSERT INTO coating_records(
                    plate_sn, operator_work_no, operator_name,
                    assistant_work_no, assistant_name, recorded_at,
                    grease_batch_no, grease_open_date, coating_method, note
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    plate_sn,
                    operator["work_no"],
                    operator["name"],
                    assistant["work_no"] if assistant else "",
                    assistant["name"] if assistant else "",
                    now,
                    grease_batch_no,
                    grease_open_date,
                    coating_method,
                    note.strip(),
                ),
            )
        except sqlite3.IntegrityError as exc:
            existing = self.find_by_plate(plate_sn)
            if existing:
                raise ValueError(
                    f"该水冷基板已记录：{existing['recorded_at']}，{existing['operator_name']}"
                ) from exc
            raise

        self.repo.log("INFO", f"涂敷记录: {plate_sn}")
        return self.get(record_id)

    def get(self, record_id: int):
        return self.repo.fetch_one(
            """
            SELECT * FROM coating_records
            WHERE id = ?
            """,
            (record_id,),
        )

    def find_by_plate(self, plate_sn: str):
        return self.repo.fetch_one(
            """
            SELECT * FROM coating_records
            WHERE UPPER(TRIM(plate_sn)) = UPPER(TRIM(?))
            ORDER BY recorded_at DESC, id DESC
            """,
            (plate_sn.strip(),),
        )

    def recent_records(self, limit: int = 200):
        return self.repo.fetch_all(
            """
            SELECT * FROM coating_records
            ORDER BY recorded_at DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        )

    def records_between(self, start_date: str | None, end_date: str | None):
        where = []
        params = []
        if start_date:
            where.append("date(recorded_at) >= date(?)")
            params.append(start_date)
        if end_date:
            where.append("date(recorded_at) <= date(?)")
            params.append(end_date)
        sql = "SELECT * FROM coating_records"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY recorded_at, id"
        return self.repo.fetch_all(sql, params)

    def search_records(
        self,
        plate_sn: str = "",
        person: str = "",
        start_date: str | None = None,
        end_date: str | None = None,
        keyword: str = "",
    ):
        where = []
        params = []
        if plate_sn.strip():
            where.append("UPPER(plate_sn) LIKE UPPER(?)")
            params.append(f"%{plate_sn.strip()}%")
        if person.strip():
            where.append(
                """
                (
                    operator_name LIKE ? OR operator_work_no LIKE ?
                    OR assistant_name LIKE ? OR assistant_work_no LIKE ?
                )
                """
            )
            value = f"%{person.strip()}%"
            params.extend([value, value, value, value])
        if start_date:
            where.append("date(recorded_at) >= date(?)")
            params.append(start_date)
        if end_date:
            where.append("date(recorded_at) <= date(?)")
            params.append(end_date)
        if keyword.strip():
            where.append(
                """
                (
                    note LIKE ? OR grease_batch_no LIKE ?
                    OR coating_method LIKE ?
                )
                """
            )
            value = f"%{keyword.strip()}%"
            params.extend([value, value, value])
        sql = "SELECT * FROM coating_records"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY recorded_at DESC, id DESC LIMIT 1000"
        return self.repo.fetch_all(sql, params)

    def delete_record(self, record_id: int) -> None:
        record = self.get(record_id)
        if record is None:
            raise ValueError("涂敷记录不存在")
        deleted = self.delete_records_by_plate(record["plate_sn"])
        self.repo.log("INFO", f"删除涂敷记录: {record['plate_sn']}，数量 {deleted}")

    def delete_records_by_plate(self, plate_sn: str) -> int:
        plate_sn = plate_sn.strip()
        if not plate_sn:
            raise ValueError("水冷基板条码不能为空")
        deleted = self.repo.execute(
            """
            DELETE FROM coating_records
            WHERE UPPER(TRIM(plate_sn)) = UPPER(TRIM(?))
            """,
            (plate_sn,),
        )
        self.repo.log("INFO", f"按条码删除涂敷记录: {plate_sn}，数量 {deleted}")
        return deleted
