from __future__ import annotations

import json
import os
import re
from datetime import datetime

from report_center.config import MesConfig, MesTighteningProductConfig
from report_center.models import MesPart, MesProduct, TorqueRecord, WorkpieceSummary


_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_TORQUE_VALUE_RE = re.compile(r"(?:^|;)\s*TOR\s*:\s*([^;]+)", re.IGNORECASE)
_ANGLE_VALUE_RE = re.compile(r"(?:^|;)\s*ANG\s*:\s*([^;]+)", re.IGNORECASE)


class MesClient:
    def __init__(self, config: MesConfig) -> None:
        self.config = config

    def load_recent_products(self) -> list[MesProduct]:
        if not self.config.enabled:
            return []
        if self.config.mock:
            return self._load_mock_products()
        return self._load_postgres_products()

    def load_product_by_serial(self, product_serial_no: str) -> MesProduct | None:
        if not self.config.enabled:
            return None
        target = product_serial_no.strip()
        if not target:
            return None
        if self.config.mock:
            return self._find_mock_product_by_serial(target)
        return self._load_postgres_product_by_serial(target)

    def load_tightening_workpiece(
        self,
        product_serial_no: str,
        base_barcode: str,
        line_code: str,
        line_name: str,
        rule: MesTighteningProductConfig,
    ) -> WorkpieceSummary:
        """Read configured MES tightening fields for one completed product."""
        if not self.config.enabled:
            raise RuntimeError("MES 未启用，无法读取流水线组装工位的拧紧数据")
        if self.config.mock:
            raise RuntimeError("MES 处于模拟模式，无法读取流水线组装工位的实际拧紧数据")
        serial = product_serial_no.strip()
        if not serial:
            raise ValueError("产品序列号为空，无法查询 MES 拧紧数据")
        records = self._load_postgres_tightening_records(serial, rule)
        if not records:
            raise RuntimeError(f"MES 未找到产品 {serial} 的拧紧数据")
        completed_at = self._latest_tightening_time(records)
        return WorkpieceSummary(
            line_code=line_code,
            line_name=line_name,
            workpiece_id=0,
            base_barcode=base_barcode,
            product_code=rule.material_no,
            product_name="",
            expected_count=rule.screw_count,
            round2_ok=0,
            round3_ok=0,
            round2_completed_at=None,
            round3_completed_at=completed_at,
            records=records,
            tightening_station=rule.station or "流水线组装工位",
        )

    def _load_mock_products(self) -> list[MesProduct]:
        if not os.path.exists(self.config.mock_file):
            os.makedirs(os.path.dirname(self.config.mock_file) or ".", exist_ok=True)
            with open(self.config.mock_file, "w", encoding="utf-8") as file:
                json.dump(
                    {
                        "products": [
                            {
                                "serial_number": "N%M%SN%ORD%",
                                "finished_time": "",
                                "parts": [
                                    {"barcode": "PLATE_01", "code": "999"},
                                    {"barcode": "IGBT_01", "code": "1303"},
                                ],
                            }
                        ]
                    },
                    file,
                    ensure_ascii=False,
                    indent=4,
                )

        with open(self.config.mock_file, "r", encoding="utf-8") as file:
            raw = json.load(file)

        products = []
        for item in raw.get("products", []):
            products.append(
                MesProduct(
                    serial_number=str(item.get("serial_number", "")).strip(),
                    finished_time=str(item.get("finished_time", "")).strip() or None,
                    parts=[
                        MesPart(
                            barcode=str(part.get("barcode", "")).strip(),
                            code=str(part.get("code", "")).strip(),
                        )
                        for part in item.get("parts", [])
                    ],
                )
            )
        return [item for item in products if item.serial_number]

    def _find_mock_product_by_serial(self, product_serial_no: str) -> MesProduct | None:
        target = product_serial_no.strip()
        target_trimmed = target.rstrip("%")
        for product in self._load_mock_products():
            serial = product.serial_number.strip()
            if serial == target or serial.rstrip("%") == target_trimmed:
                return product
        return None

    def _load_postgres_products(self) -> list[MesProduct]:
        try:
            import psycopg2
        except ImportError as exc:
            raise RuntimeError("缺少 psycopg2-binary 依赖，无法连接 MES PostgreSQL") from exc

        params = {
            "host": self.config.host,
            "port": self.config.port,
            "user": self.config.user,
            "password": self.config.password,
            "dbname": self.config.dbname,
        }
        products: list[MesProduct] = []
        with psycopg2.connect(**params) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT serial_number, finished_time
                    FROM plan_part
                    WHERE finished_time >= CURRENT_DATE - (%s * INTERVAL '1 day')
                      AND part_state = '完成生产'
                    ORDER BY finished_time DESC
                    """,
                    (int(self.config.lookback_days),),
                )
                serial_rows = cur.fetchall()
                for serial_number, finished_time in serial_rows:
                    cur.execute(
                        """
                        SELECT part_barcode, part_code
                        FROM doc_key_part_info
                        WHERE product_born_code = %s
                        """,
                        (serial_number,),
                    )
                    parts = [
                        MesPart(barcode=str(row[0]).strip(), code=str(row[1]).strip())
                        for row in cur.fetchall()
                    ]
                    products.append(
                        MesProduct(
                            serial_number=str(serial_number).strip(),
                            finished_time=str(finished_time) if finished_time else None,
                            parts=parts,
                        )
                    )
        return products

    def _load_postgres_product_by_serial(self, product_serial_no: str) -> MesProduct | None:
        try:
            import psycopg2
        except ImportError as exc:
            raise RuntimeError("缺少 psycopg2-binary 依赖，无法连接 MES PostgreSQL") from exc

        params = {
            "host": self.config.host,
            "port": self.config.port,
            "user": self.config.user,
            "password": self.config.password,
            "dbname": self.config.dbname,
        }
        candidates = self._serial_candidates(product_serial_no)
        with psycopg2.connect(**params) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT serial_number, finished_time
                    FROM plan_part
                    WHERE serial_number = ANY(%s)
                    ORDER BY finished_time DESC NULLS LAST
                    LIMIT 1
                    """,
                    (candidates,),
                )
                row = cur.fetchone()
                if not row:
                    return None
                serial_number, finished_time = row
                cur.execute(
                    """
                    SELECT part_barcode, part_code
                    FROM doc_key_part_info
                    WHERE product_born_code = %s
                    """,
                    (serial_number,),
                )
                parts = [
                    MesPart(barcode=str(item[0]).strip(), code=str(item[1]).strip())
                    for item in cur.fetchall()
                ]
                return MesProduct(
                    serial_number=str(serial_number).strip(),
                    finished_time=str(finished_time) if finished_time else None,
                    parts=parts,
                )

    def _load_postgres_tightening_records(
        self,
        product_serial_no: str,
        rule: MesTighteningProductConfig,
    ) -> list[TorqueRecord]:
        try:
            import psycopg2
            from psycopg2 import sql
        except ImportError as exc:
            raise RuntimeError("缺少 psycopg2-binary 依赖，无法连接 MES PostgreSQL") from exc

        params = {
            "host": self.config.host,
            "port": self.config.port,
            "user": self.config.user,
            "password": self.config.password,
            "dbname": self.config.dbname,
        }
        candidates = self._serial_candidates(product_serial_no)
        records: list[TorqueRecord] = []
        with psycopg2.connect(**params) as conn:
            with conn.cursor() as cur:
                for round_cfg in sorted(rule.rounds, key=lambda item: item.round_no):
                    self._validate_round_config(round_cfg.table_name, round_cfg.torque_field_prefix, round_cfg.time_field_prefix)
                    cur.execute(
                        sql.SQL("SELECT * FROM {} WHERE product_born_code = ANY(%s) LIMIT 1").format(
                            sql.Identifier(round_cfg.table_name)
                        ),
                        (candidates,),
                    )
                    row = cur.fetchone()
                    if row is None:
                        raise RuntimeError(
                            f"MES 表 {round_cfg.table_name} 未找到产品序列号 {product_serial_no} 的记录"
                        )
                    columns = [item.name for item in cur.description]
                    values = dict(zip(columns, row))
                    for sequence_no in range(1, rule.screw_count + 1):
                        suffix = f"{sequence_no:02d}"
                        torque_field = f"{round_cfg.torque_field_prefix}{suffix}"
                        time_field = f"{round_cfg.time_field_prefix}{suffix}"
                        raw_value = values.get(torque_field)
                        actual_torque, actual_angle = self._parse_torque_value(raw_value)
                        records.append(
                            TorqueRecord(
                                round_no=round_cfg.round_no,
                                sequence_no=sequence_no,
                                program_no=0,
                                set_torque=round_cfg.target_torque,
                                actual_torque=actual_torque,
                                actual_angle=actual_angle,
                                result="",
                                operator_work_no="",
                                operator_name="",
                                tightened_at=self._format_time(values.get(time_field)),
                            )
                        )
        return records

    @staticmethod
    def _validate_round_config(table_name: str, torque_prefix: str, time_prefix: str) -> None:
        for label, value in (("MES表名", table_name), ("扭矩字段前缀", torque_prefix), ("时间字段前缀", time_prefix)):
            if not _IDENTIFIER_RE.fullmatch(value):
                raise ValueError(f"{label}不合法: {value!r}。只能使用字母、数字和下划线，且不能以数字开头。")

    @staticmethod
    def _parse_torque_value(value) -> tuple[float | None, float | None]:
        text = str(value or "").strip()
        torque_match = _TORQUE_VALUE_RE.search(text)
        angle_match = _ANGLE_VALUE_RE.search(text)
        return (
            MesClient._to_float(torque_match.group(1) if torque_match else None),
            MesClient._to_float(angle_match.group(1) if angle_match else None),
        )

    @staticmethod
    def _to_float(value: str | None) -> float | None:
        try:
            return float(value) if value not in (None, "") else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _format_time(value) -> str:
        if value is None:
            return ""
        if isinstance(value, datetime):
            return value.strftime("%Y-%m-%d %H:%M:%S")
        return str(value).strip()

    @staticmethod
    def _latest_tightening_time(records: list[TorqueRecord]) -> str | None:
        values = [item.tightened_at for item in records if item.tightened_at]
        return max(values) if values else None

    def _serial_candidates(self, product_serial_no: str) -> list[str]:
        target = product_serial_no.strip()
        candidates = [target]
        trimmed = target.rstrip("%")
        if trimmed and trimmed not in candidates:
            candidates.append(trimmed)
        with_percent = f"{trimmed}%"
        if trimmed and with_percent not in candidates:
            candidates.append(with_percent)
        return candidates
