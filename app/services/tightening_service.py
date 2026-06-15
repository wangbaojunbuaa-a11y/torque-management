from datetime import datetime, timedelta

from app.models.enums import WorkpieceStatus
from app.repositories.sqlite_repo import SQLiteRepository


class TighteningService:
    def __init__(self, repo: SQLiteRepository) -> None:
        self.repo = repo

    def scan_workpiece(self, barcode: str, selected_product_id: int | None):
        barcode = barcode.strip()
        if not barcode:
            raise ValueError("条码不能为空")

        existing = self.repo.fetch_one(
            """
            SELECT w.*, p.code AS product_code, p.name AS product_name
            FROM workpieces w
            JOIN product_types p ON p.id = w.product_type_id
            WHERE w.base_barcode = ?
            """,
            (barcode,),
        )
        if existing:
            return existing, self.decide_action(existing["id"])

        if selected_product_id is None:
            return None, {"state": "NEED_PRODUCT", "message": "新条码未选择产品类型"}

        now = datetime.now().isoformat(timespec="seconds")
        workpiece_id = self.repo.execute(
            """
            INSERT INTO workpieces(
                base_barcode, product_type_id, status, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                barcode,
                selected_product_id,
                WorkpieceStatus.ROUND2_IN_PROGRESS.value,
                now,
                now,
            ),
        )
        self.repo.log("INFO", f"新工件上线: {barcode}")
        workpiece = self.get_workpiece(workpiece_id)
        return workpiece, self.decide_action(workpiece_id)

    def get_workpiece(self, workpiece_id: int):
        return self.repo.fetch_one(
            """
            SELECT w.*, p.code AS product_code, p.name AS product_name,
                   p.igbt_count, p.screws_per_igbt, p.round2_program_no,
                   p.round3_program_no, p.round2_set_torque, p.round3_set_torque,
                   p.rest_minutes
            FROM workpieces w
            JOIN product_types p ON p.id = w.product_type_id
            WHERE w.id = ?
            """,
            (workpiece_id,),
        )

    def count_ok(self, workpiece_id: int, round_no: int) -> int:
        row = self.repo.fetch_one(
            """
            SELECT COUNT(*) AS cnt FROM tightening_records
            WHERE workpiece_id = ? AND round_no = ? AND result = 'OK'
            """,
            (workpiece_id, round_no),
        )
        return int(row["cnt"])

    def count_attempts(self, workpiece_id: int, round_no: int) -> int:
        row = self.repo.fetch_one(
            """
            SELECT COUNT(*) AS cnt FROM tightening_records
            WHERE workpiece_id = ? AND round_no = ?
            """,
            (workpiece_id, round_no),
        )
        return int(row["cnt"])

    def expected_count(self, workpiece) -> int:
        return int(workpiece["igbt_count"]) * int(workpiece["screws_per_igbt"])

    def decide_action(self, workpiece_id: int) -> dict:
        workpiece = self.get_workpiece(workpiece_id)
        expected = self.expected_count(workpiece)
        round2_ok = self.count_ok(workpiece_id, 2)
        round3_ok = self.count_ok(workpiece_id, 3)

        if round3_ok >= expected:
            self._set_status(workpiece_id, WorkpieceStatus.FINISHED.value, round3_completed=True)
            return {"state": "FINISHED", "enabled": False, "message": "该工件已完成"}

        if round2_ok < expected:
            self._set_status(workpiece_id, WorkpieceStatus.ROUND2_IN_PROGRESS.value)
            return {
                "state": "ROUND2",
                "round_no": 2,
                "program_no": int(workpiece["round2_program_no"]),
                "set_torque": float(workpiece["round2_set_torque"]),
                "done": round2_ok,
                "expected": expected,
                "enabled": True,
                "message": "进行第二次拧紧",
            }

        if not workpiece["round2_completed_at"]:
            self._set_status(workpiece_id, WorkpieceStatus.RESTING.value, round2_completed=True)
            workpiece = self.get_workpiece(workpiece_id)

        completed_at = datetime.fromisoformat(workpiece["round2_completed_at"])
        ready_at = completed_at + timedelta(minutes=int(workpiece["rest_minutes"]))
        now = datetime.now()
        if now < ready_at:
            self._set_status(workpiece_id, WorkpieceStatus.RESTING.value)
            return {
                "state": "RESTING",
                "enabled": False,
                "ready_at": ready_at,
                "remaining": ready_at - now,
                "done": round2_ok,
                "expected": expected,
                "message": "静置时间不足",
            }

        self._set_status(workpiece_id, WorkpieceStatus.ROUND3_IN_PROGRESS.value)
        return {
            "state": "ROUND3",
            "round_no": 3,
            "program_no": int(workpiece["round3_program_no"]),
            "set_torque": float(workpiece["round3_set_torque"]),
            "done": round3_ok,
            "expected": expected,
            "enabled": True,
            "message": "进行第三次拧紧",
        }

    def record_tightening(
        self,
        workpiece_id: int,
        operator_work_no: str,
        result: str,
        actual_torque: float,
        actual_angle: float,
    ) -> dict:
        action = self.decide_action(workpiece_id)
        if action["state"] not in {"ROUND2", "ROUND3"}:
            raise RuntimeError(action["message"])

        if action["done"] >= action["expected"]:
            raise RuntimeError("当前轮次拧紧数量已满，禁止继续拧紧")

        sequence_no = self.count_attempts(workpiece_id, int(action["round_no"])) + 1
        now = datetime.now().isoformat(timespec="seconds")
        self.repo.execute(
            """
            INSERT INTO tightening_records(
                workpiece_id, round_no, sequence_no, program_no,
                set_torque, actual_torque, actual_angle, result,
                operator_work_no, tightened_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                workpiece_id,
                int(action["round_no"]),
                sequence_no,
                int(action["program_no"]),
                float(action["set_torque"]),
                float(actual_torque),
                float(actual_angle),
                result,
                operator_work_no,
                now,
            ),
        )
        self.repo.log(
            "INFO",
            f"拧紧记录: workpiece={workpiece_id}, round={action['round_no']}, seq={sequence_no}, result={result}",
        )
        return self.decide_action(workpiece_id)

    def records_for_workpiece(self, workpiece_id: int):
        return self.repo.fetch_all(
            """
            SELECT * FROM tightening_records
            WHERE workpiece_id = ?
            ORDER BY tightened_at DESC, id DESC
            """,
            (workpiece_id,),
        )

    def rest_queue(self):
        return self.repo.fetch_all(
            """
            SELECT w.*, p.code AS product_code, p.name AS product_name, p.rest_minutes
            FROM workpieces w
            JOIN product_types p ON p.id = w.product_type_id
            WHERE w.status IN ('RESTING', 'READY_ROUND3', 'ROUND3_IN_PROGRESS')
              AND w.round3_completed_at IS NULL
            ORDER BY w.round2_completed_at ASC
            """
        )

    def _set_status(
        self,
        workpiece_id: int,
        status: str,
        round2_completed: bool = False,
        round3_completed: bool = False,
    ) -> None:
        fields = ["status = ?", "updated_at = ?"]
        params = [status, datetime.now().isoformat(timespec="seconds")]
        if round2_completed:
            fields.append("round2_completed_at = COALESCE(round2_completed_at, ?)")
            params.append(datetime.now().isoformat(timespec="seconds"))
        if round3_completed:
            fields.append("round3_completed_at = COALESCE(round3_completed_at, ?)")
            params.append(datetime.now().isoformat(timespec="seconds"))
        params.append(workpiece_id)
        self.repo.execute(
            f"UPDATE workpieces SET {', '.join(fields)} WHERE id = ?", params
        )
