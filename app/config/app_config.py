from dataclasses import dataclass
import json
import os


@dataclass(frozen=True)
class AppConfig:
    app_name: str = "IGBT Torque Manager"
    db_path: str = "data/torque.db"
    device_mode: str = "mock"
    report_dir: str = "reports"
    offline_warning_sound: str = ""
    opcua_url: str = "opc.tcp://127.0.0.1:49320/Kepware.KEPServerEX.V6"
    opcua_poll_interval_seconds: float = 0.2

    opc_node_okng: str = "ns=2;s=通道 3.设备 1.OKNG"
    opc_node_angle: str = "ns=2;s=通道 3.设备 1.ANG"
    opc_node_torque: str = "ns=2;s=通道 3.设备 1.TOR"
    opc_node_rw: str = "ns=2;s=通道 3.设备 1.RW"
    opc_node_enable: str = "ns=2;s=通道 3.设备 1.ENABLE"
    opc_node_program: str = "ns=2;s=通道 3.设备 1.FN"

    @classmethod
    def load(cls, path: str = "config/settings.json") -> "AppConfig":
        values = {}
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as file:
                values = json.load(file)

        env_mode = os.getenv("TORQUE_DEVICE_MODE")
        if env_mode:
            values["device_mode"] = env_mode

        return cls(**{key: value for key, value in values.items() if key in cls.__annotations__})
