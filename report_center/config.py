from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import os
from typing import Any


CONFIG_FILE = "report_center_config.json"


@dataclass
class MesConfig:
    enabled: bool = True
    mock: bool = True
    host: str = "127.0.0.1"
    port: str = "5432"
    user: str = "postgres"
    password: str = "sasa"
    dbname: str = "lean_mes_glmk"
    lookback_days: int = 7
    igbt_filter_rules: list[str] = field(default_factory=lambda: ["1303", "1304"])
    mock_file: str = "data/mock_mes_products.json"


@dataclass
class LineConfig:
    code: str = "LINE_A"
    name: str = "一号产线"
    db_path: str = r"\\LineServer\TorqueData\data\torque.db"
    enabled: bool = True


@dataclass
class ReportCenterConfig:
    poll_interval_seconds: int = 30
    copy_before_read: bool = True
    staging_report_dir: str = "reports"
    report_dir: str = r"\\ReportServer\TorqueReports"
    state_db: str = "data/report_center.db"
    mes: MesConfig = field(default_factory=MesConfig)
    lines: list[LineConfig] = field(default_factory=lambda: [LineConfig()])

    @classmethod
    def load(cls, path: str = CONFIG_FILE) -> "ReportCenterConfig":
        if not os.path.exists(path):
            cfg = cls()
            cfg.save(path)
            return cfg

        with open(path, "r", encoding="utf-8") as file:
            raw = json.load(file)
        return cls.from_dict(raw)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "ReportCenterConfig":
        mes_raw = raw.get("mes") or {}
        lines_raw = raw.get("lines") or []
        return cls(
            poll_interval_seconds=int(raw.get("poll_interval_seconds", 30)),
            copy_before_read=bool(raw.get("copy_before_read", True)),
            staging_report_dir=str(raw.get("staging_report_dir", "reports")),
            report_dir=str(raw.get("report_dir", r"\\ReportServer\TorqueReports")),
            state_db=str(raw.get("state_db", "data/report_center.db")),
            mes=MesConfig(
                enabled=bool(mes_raw.get("enabled", True)),
                mock=bool(mes_raw.get("mock", True)),
                host=str(mes_raw.get("host", "127.0.0.1")),
                port=str(mes_raw.get("port", "5432")),
                user=str(mes_raw.get("user", "postgres")),
                password=str(mes_raw.get("password", "sasa")),
                dbname=str(mes_raw.get("dbname", "lean_mes_glmk")),
                lookback_days=int(mes_raw.get("lookback_days", 7)),
                igbt_filter_rules=list(mes_raw.get("igbt_filter_rules") or ["1303", "1304"]),
                mock_file=str(mes_raw.get("mock_file", "data/mock_mes_products.json")),
            ),
            lines=[
                LineConfig(
                    code=str(item.get("code", "")).strip() or f"LINE_{index + 1}",
                    name=str(item.get("name", "")).strip() or f"产线{index + 1}",
                    db_path=str(item.get("db_path", "")).strip(),
                    enabled=bool(item.get("enabled", True)),
                )
                for index, item in enumerate(lines_raw)
            ]
            or [LineConfig()],
        )

    def save(self, path: str = CONFIG_FILE) -> None:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as file:
            json.dump(asdict(self), file, ensure_ascii=False, indent=4)
