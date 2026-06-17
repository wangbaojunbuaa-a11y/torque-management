from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
import os
import sqlite3
from typing import Any, Iterable

from app.services.passwords import hash_password


class CoatingRepository:
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
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    work_no TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    name TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'operator',
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS coating_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    plate_sn TEXT NOT NULL UNIQUE,
                    operator_work_no TEXT NOT NULL,
                    operator_name TEXT NOT NULL,
                    assistant_work_no TEXT,
                    assistant_name TEXT,
                    recorded_at TEXT NOT NULL,
                    note TEXT NOT NULL DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS operation_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    level TEXT NOT NULL,
                    message TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )

    def seed_defaults(self) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        with self.connect() as conn:
            user_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            if user_count == 0:
                conn.execute(
                    """
                    INSERT INTO users(work_no, password_hash, name, role, active, created_at)
                    VALUES (?, ?, ?, ?, 1, ?)
                    """,
                    ("admin", hash_password("admin123"), "管理员", "admin", now),
                )

    def fetch_one(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute(sql, tuple(params)).fetchone()

    def fetch_all(self, sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(sql, tuple(params)).fetchall()

    def execute(self, sql: str, params: Iterable[Any] = ()) -> int:
        with self.connect() as conn:
            cur = conn.execute(sql, tuple(params))
            return int(cur.lastrowid or cur.rowcount)

    def log(self, level: str, message: str) -> None:
        self.execute(
            "INSERT INTO operation_logs(level, message, created_at) VALUES (?, ?, ?)",
            (level, message, datetime.now().isoformat(timespec="seconds")),
        )
