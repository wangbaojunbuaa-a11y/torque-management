import sqlite3
from datetime import datetime

from app.repositories.sqlite_repo import SQLiteRepository
from app.services.passwords import hash_password


class UserService:
    def __init__(self, repo: SQLiteRepository) -> None:
        self.repo = repo

    def list_users(self):
        return self.repo.fetch_all(
            """
            SELECT id, work_no, name, role, active, created_at
            FROM users
            ORDER BY active DESC, work_no
            """
        )

    def save(self, values: dict) -> None:
        self._validate(values)
        now = datetime.now().isoformat(timespec="seconds")
        active = 1 if values.get("active", True) else 0
        role = values.get("role") or "operator"
        user_id = values.get("id")

        try:
            if user_id:
                params = [
                    values["work_no"].strip(),
                    values["name"].strip(),
                    role,
                    active,
                    int(user_id),
                ]
                self.repo.execute(
                    """
                    UPDATE users
                    SET work_no = ?, name = ?, role = ?, active = ?
                    WHERE id = ?
                    """,
                    params,
                )
                if values.get("password"):
                    self.repo.execute(
                        "UPDATE users SET password_hash = ? WHERE id = ?",
                        (hash_password(values["password"]), int(user_id)),
                    )
            else:
                if not values.get("password"):
                    raise ValueError("新增用户必须填写密码")
                self.repo.execute(
                    """
                    INSERT INTO users(work_no, password_hash, name, role, active, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        values["work_no"].strip(),
                        hash_password(values["password"]),
                        values["name"].strip(),
                        role,
                        active,
                        now,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError("工号已存在") from exc

    def set_active(self, user_id: int, active: bool) -> None:
        self.repo.execute(
            "UPDATE users SET active = ? WHERE id = ?",
            (1 if active else 0, int(user_id)),
        )

    def _validate(self, values: dict) -> None:
        if not values.get("work_no", "").strip():
            raise ValueError("工号不能为空")
        if not values.get("name", "").strip():
            raise ValueError("姓名不能为空")
        password = values.get("password") or ""
        if password and len(password) < 4:
            raise ValueError("密码至少4位")
