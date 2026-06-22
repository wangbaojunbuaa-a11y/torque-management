from __future__ import annotations

import json
import os

from report_center.config import MesConfig
from report_center.models import MesPart, MesProduct


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
