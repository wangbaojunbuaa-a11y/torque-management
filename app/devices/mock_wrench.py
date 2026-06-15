import random
from typing import Callable

from app.devices.torque_wrench_base import WrenchResult


class MockWrench:
    def __init__(self) -> None:
        self.connected = False
        self.enabled = False
        self.program_no = 0
        self._callback: Callable[[WrenchResult], None] | None = None

    def connect(self) -> None:
        self.connected = True

    def disconnect(self) -> None:
        self.connected = False
        self.enabled = False

    def set_program(self, program_no: int) -> None:
        self.program_no = program_no

    def enable(self) -> None:
        if not self.connected:
            raise RuntimeError("扳手未连接")
        self.enabled = True

    def disable(self) -> None:
        self.enabled = False

    def on_tightening_done(self, callback: Callable[[WrenchResult], None]) -> None:
        self._callback = callback

    def simulate(self, result: str = "OK", set_torque: float = 5.0) -> WrenchResult:
        if not self.enabled:
            raise RuntimeError("扳手未使能")
        payload = WrenchResult(
            result=result,
            actual_torque=round(set_torque + random.uniform(-0.08, 0.08), 3),
            actual_angle=round(random.uniform(20.0, 80.0), 3),
        )
        if self._callback:
            self._callback(payload)
        return payload
