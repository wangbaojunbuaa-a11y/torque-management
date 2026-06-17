import os
import sys

from app.repositories.sqlite_repo import SQLiteRepository


class OfflineCheckService:
    def __init__(self, repo: SQLiteRepository, warning_sound: str = "") -> None:
        self.repo = repo
        self.warning_sound = warning_sound

    def check_barcode(self, barcode: str) -> dict:
        barcode = barcode.strip()
        if not barcode:
            raise ValueError("条码不能为空")

        workpiece = self.repo.fetch_one(
            """
            SELECT w.*, p.code AS product_code, p.name AS product_name,
                   p.igbt_count, p.screws_per_igbt
            FROM workpieces w
            JOIN product_types p ON p.id = w.product_type_id
            WHERE w.base_barcode = ?
            """,
            (barcode,),
        )
        if workpiece is None:
            return self._fail("未找到该水冷基板生产记录", barcode=barcode)

        expected = int(workpiece["igbt_count"]) * int(workpiece["screws_per_igbt"])
        round2_ok = self._count(workpiece["id"], 2, "OK")
        round3_ok = self._count(workpiece["id"], 3, "OK")
        problems = []
        if round2_ok < expected:
            problems.append(f"第二次OK数量不足：{round2_ok}/{expected}")
        if round3_ok < expected:
            problems.append(f"第三次OK数量不足：{round3_ok}/{expected}")

        if problems:
            return self._fail("；".join(problems), workpiece, barcode=barcode)

        return {
            "ok": True,
            "message": "下线检查通过，所有扭矩已完成且合格",
            "workpiece": workpiece,
            "barcode": barcode,
            "round2_ok": round2_ok,
            "round3_ok": round3_ok,
            "expected": expected,
        }

    def play_warning(self) -> None:
        try:
            if sys.platform.startswith("win"):
                import winsound

                if self.warning_sound and os.path.exists(self.warning_sound):
                    winsound.PlaySound(self.warning_sound, winsound.SND_FILENAME | winsound.SND_ASYNC)
                else:
                    winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        except Exception:
            pass

    def _count(self, workpiece_id: int, round_no: int, result: str) -> int:
        row = self.repo.fetch_one(
            """
            SELECT COUNT(*) AS cnt FROM tightening_records
            WHERE workpiece_id = ? AND round_no = ? AND result = ?
            """,
            (workpiece_id, round_no, result),
        )
        return int(row["cnt"])

    def _fail(self, message: str, workpiece=None, barcode: str = "") -> dict:
        return {"ok": False, "message": message, "workpiece": workpiece, "barcode": barcode}
