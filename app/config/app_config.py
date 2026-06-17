from dataclasses import asdict, dataclass
import json
import os


@dataclass
class AppConfig:
    app_name: str = "IGBT Torque Manager"
    db_path: str = "data/torque.db"
    device_mode: str = "mock"
    report_dir: str = "reports"
    offline_warning_sound: str = ""
    last_login_work_no: str = "admin"
    sound_success: int = 0
    sound_error: int = 16
    sound_count: int = 1
    sound_interval: float = 0.1
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

    def save(self, path: str = "config/settings.json") -> None:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as file:
            json.dump(asdict(self), file, ensure_ascii=False, indent=4)
