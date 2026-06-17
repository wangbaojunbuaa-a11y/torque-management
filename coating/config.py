from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os


@dataclass
class CoatingConfig:
    app_name: str = "水冷基板涂敷记录"
    db_path: str = "data/coating.db"
    report_dir: str = "reports"
    sound_success: int = 0
    sound_error: int = 16
    sound_count: int = 1
    sound_interval: float = 0.1

    @classmethod
    def load(cls, path: str = "config/coating_settings.json") -> "CoatingConfig":
        values = {}
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as file:
                values = json.load(file)
        return cls(**{key: value for key, value in values.items() if key in cls.__annotations__})

    def save(self, path: str = "config/coating_settings.json") -> None:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as file:
            json.dump(asdict(self), file, ensure_ascii=False, indent=4)
