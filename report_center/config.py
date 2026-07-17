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
    coating_db_path: str = r"\\LineServer\CoatingData\data\coating.db"
    enabled: bool = True


@dataclass
class MesTighteningRoundConfig:
    round_no: int = 1
    table_name: str = ""
    torque_field_prefix: str = ""
    time_field_prefix: str = ""
    target_torque: float | None = None


@dataclass
class MesTighteningProductConfig:
    material_no: str = ""
    station: str = "流水线组装工位"
    screw_count: int = 1
    rounds: list[MesTighteningRoundConfig] = field(default_factory=lambda: [MesTighteningRoundConfig()])


@dataclass
class ReportCenterConfig:
    poll_interval_seconds: int = 30
    copy_before_read: bool = True
    background_on_close: bool = True
    network_reconnect_enabled: bool = True
    network_reconnect_interval_seconds: int = 60
    staging_report_dir: str = "reports"
    report_dir: str = r"\\ReportServer\TorqueReports"
    state_db: str = "data/report_center.db"
    mes: MesConfig = field(default_factory=MesConfig)
    lines: list[LineConfig] = field(default_factory=lambda: [LineConfig()])
    mes_tightening_products: list[MesTighteningProductConfig] = field(default_factory=list)

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
        mes_tightening_raw = raw.get("mes_tightening_products") or []
        return cls(
            poll_interval_seconds=int(raw.get("poll_interval_seconds", 30)),
            copy_before_read=bool(raw.get("copy_before_read", True)),
            background_on_close=bool(raw.get("background_on_close", True)),
            network_reconnect_enabled=bool(raw.get("network_reconnect_enabled", True)),
            network_reconnect_interval_seconds=int(raw.get("network_reconnect_interval_seconds", 60)),
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
                    coating_db_path=str(item.get("coating_db_path", "")).strip(),
                    enabled=bool(item.get("enabled", True)),
                )
                for index, item in enumerate(lines_raw)
            ]
            or [LineConfig()],
            mes_tightening_products=[
                MesTighteningProductConfig(
                    material_no=str(item.get("material_no", "")).strip(),
                    station=str(item.get("station", "")).strip() or "流水线组装工位",
                    screw_count=max(1, int(item.get("screw_count", 1))),
                    rounds=[
                        MesTighteningRoundConfig(
                            round_no=max(1, int(round_item.get("round_no", index + 1))),
                            table_name=str(round_item.get("table_name", "")).strip(),
                            torque_field_prefix=str(round_item.get("torque_field_prefix", "")).strip(),
                            time_field_prefix=str(round_item.get("time_field_prefix", "")).strip(),
                            target_torque=(
                                float(round_item["target_torque"])
                                if round_item.get("target_torque") not in (None, "")
                                else None
                            ),
                        )
                        for index, round_item in enumerate(item.get("rounds") or [])
                    ]
                    or [MesTighteningRoundConfig()],
                )
                for item in mes_tightening_raw
                if str(item.get("material_no", "")).strip()
            ],
        )

    def mes_tightening_for_material(self, material_no: str) -> MesTighteningProductConfig | None:
        target = material_no.strip()
        return next((item for item in self.mes_tightening_products if item.material_no == target), None)

    def save(self, path: str = CONFIG_FILE) -> None:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as file:
            json.dump(asdict(self), file, ensure_ascii=False, indent=4)
