from datetime import datetime

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
        else:
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
