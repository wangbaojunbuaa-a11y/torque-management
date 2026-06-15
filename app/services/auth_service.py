from app.repositories.sqlite_repo import SQLiteRepository
from app.services.passwords import verify_password


class AuthService:
    def __init__(self, repo: SQLiteRepository) -> None:
        self.repo = repo

    def login(self, work_no: str, password: str):
        user = self.repo.fetch_one(
            "SELECT * FROM users WHERE work_no = ? AND active = 1", (work_no.strip(),)
        )
        if user is None:
            return None
        if not verify_password(password, user["password_hash"]):
            return None
        self.repo.log("INFO", f"用户 {work_no} 登录")
        return user
