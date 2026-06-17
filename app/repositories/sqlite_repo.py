import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Iterable

from app.services.passwords import hash_password


class SQLiteRepository:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
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

                CREATE TABLE IF NOT EXISTS product_types (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    igbt_count INTEGER NOT NULL,
                    screws_per_igbt INTEGER NOT NULL,
                    round2_program_no INTEGER NOT NULL,
                    round3_program_no INTEGER NOT NULL,
                    round2_set_torque REAL NOT NULL,
                    round3_set_torque REAL NOT NULL,
                    rest_minutes INTEGER NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS workpieces (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    base_barcode TEXT NOT NULL UNIQUE,
                    product_type_id INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    round2_completed_at TEXT,
                    round3_completed_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(product_type_id) REFERENCES product_types(id)
                );

                CREATE TABLE IF NOT EXISTS tightening_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    workpiece_id INTEGER NOT NULL,
                    round_no INTEGER NOT NULL,
                    sequence_no INTEGER NOT NULL,
                    program_no INTEGER NOT NULL,
                    set_torque REAL NOT NULL,
                    actual_torque REAL NOT NULL,
                    actual_angle REAL NOT NULL,
                    result TEXT NOT NULL,
                    operator_work_no TEXT NOT NULL,
                    tightened_at TEXT NOT NULL,
                    FOREIGN KEY(workpiece_id) REFERENCES workpieces(id)
                );

                CREATE TABLE IF NOT EXISTS operation_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    level TEXT NOT NULL,
                    message TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS offline_checks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    workpiece_id INTEGER NOT NULL UNIQUE,
                    checked_at TEXT NOT NULL,
                    FOREIGN KEY(workpiece_id) REFERENCES workpieces(id)
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

            product_count = conn.execute("SELECT COUNT(*) FROM product_types").fetchone()[0]
            if product_count == 0:
                conn.execute(
                    """
                    INSERT INTO product_types(
                        code, name, igbt_count, screws_per_igbt,
                        round2_program_no, round3_program_no,
                        round2_set_torque, round3_set_torque,
                        rest_minutes, active, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                    """,
                    ("DEMO-IGBT", "示例IGBT模块", 4, 6, 2, 3, 3.5, 5.0, 30, now, now),
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
