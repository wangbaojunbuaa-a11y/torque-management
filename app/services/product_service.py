from datetime import datetime
import sqlite3

from app.repositories.sqlite_repo import SQLiteRepository


class ProductService:
    def __init__(self, repo: SQLiteRepository) -> None:
        self.repo = repo

    def list_active(self):
        return self.repo.fetch_all(
            "SELECT * FROM product_types WHERE active = 1 ORDER BY code"
        )

    def get(self, product_id: int):
        return self.repo.fetch_one("SELECT * FROM product_types WHERE id = ?", (product_id,))

    def expected_screw_count(self, product) -> int:
        return int(product["igbt_count"]) * int(product["screws_per_igbt"])

    def save(self, values: dict) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        self._validate(values)
        params = (
            values["code"].strip(),
            values["name"].strip(),
            int(values["igbt_count"]),
            int(values["screws_per_igbt"]),
            int(values["round2_program_no"]),
            int(values["round3_program_no"]),
            float(values["round2_set_torque"]),
            float(values["round3_set_torque"]),
            int(values["rest_minutes"]),
            now,
        )
        if values.get("id"):
            try:
                self.repo.execute(
                    """
                    UPDATE product_types
                    SET code=?, name=?, igbt_count=?, screws_per_igbt=?,
                        round2_program_no=?, round3_program_no=?,
                        round2_set_torque=?, round3_set_torque=?,
                        rest_minutes=?, updated_at=?
                    WHERE id=?
                    """,
                    params + (int(values["id"]),),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("产品编码已存在") from exc
        else:
            try:
                self.repo.execute(
                    """
                    INSERT INTO product_types(
                        code, name, igbt_count, screws_per_igbt,
                        round2_program_no, round3_program_no,
                        round2_set_torque, round3_set_torque,
                        rest_minutes, active, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                    """,
                    params + (now,),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("产品编码已存在") from exc

    def _validate(self, values: dict) -> None:
        if not values["code"].strip():
            raise ValueError("产品编码不能为空")
        if not values["name"].strip():
            raise ValueError("产品名称不能为空")

        positive_int_fields = {
            "igbt_count": "IGBT数量",
            "screws_per_igbt": "每个IGBT螺钉数量",
            "round2_program_no": "第二次程序号",
            "round3_program_no": "第三次程序号",
        }
        for key, label in positive_int_fields.items():
            try:
                value = int(values[key])
            except ValueError as exc:
                raise ValueError(f"{label}必须是整数") from exc
            if value <= 0:
                raise ValueError(f"{label}必须大于0")

        for key, label in {
            "round2_set_torque": "第二次设定扭矩",
            "round3_set_torque": "第三次设定扭矩",
        }.items():
            try:
                value = float(values[key])
            except ValueError as exc:
                raise ValueError(f"{label}必须是数字") from exc
            if value <= 0:
                raise ValueError(f"{label}必须大于0")

        try:
            rest_minutes = int(values["rest_minutes"])
        except ValueError as exc:
            raise ValueError("静置时间必须是整数分钟") from exc
        if rest_minutes < 0:
            raise ValueError("静置时间不能小于0")
