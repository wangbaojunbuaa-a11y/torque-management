import asyncio
import threading
from concurrent.futures import Future
from typing import Callable

from app.config.app_config import AppConfig
from app.devices.torque_wrench_base import WrenchResult


class OpcUaWrench:
    """OPC UA adapter for the electric torque wrench through Kepware.

    This follows the old WinForms communication model:
    - FN: tightening program number
    - ENABLE: wrench enable
    - RW: PLC/wrench result-ready flag, host resets it to 0 after reading
    - OKNG: tightening result, 1 means OK
    - TOR: actual torque
    - ANG: actual angle
    """

    def __init__(self, config: AppConfig | None = None) -> None:
        self.config = config or AppConfig()
        self._callback: Callable[[WrenchResult], None] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._client = None
        self._nodes = {}
        self._poll_task = None
        self._connected = False
        self._ua = None

    @property
    def connected(self) -> bool:
        return self._connected

    def connect(self) -> None:
        if self._connected:
            return
        self._start_loop()
        self._run(self._connect())

    def disconnect(self) -> None:
        if self._loop is None:
            return
        try:
            self._run(self._disconnect())
        finally:
            if self._loop.is_running():
                self._loop.call_soon_threadsafe(self._loop.stop)
            if self._thread:
                self._thread.join(timeout=2)
            self._loop = None
            self._thread = None
            self._connected = False

    def set_program(self, program_no: int) -> None:
        self._require_connected()
        self._run(self._write_program(program_no))

    def enable(self) -> None:
        self._require_connected()
        self._run(self._write_enable(True))

    def disable(self) -> None:
        if not self._connected:
            return
        self._run(self._write_enable(False))

    def on_tightening_done(self, callback: Callable[[WrenchResult], None]) -> None:
        self._callback = callback

    def _start_loop(self) -> None:
        if self._loop is not None:
            return
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def _run_loop(self) -> None:
        assert self._loop is not None
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def _run(self, coro) -> None:
        if self._loop is None:
            raise RuntimeError("OPC UA事件循环未启动")
        future: Future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=10)

    def _require_connected(self) -> None:
        if not self._connected:
            raise RuntimeError("OPC UA扳手未连接")

    async def _connect(self) -> None:
        try:
            from asyncua import Client, ua
        except ImportError as exc:
            raise RuntimeError("缺少 asyncua 依赖，请先安装 requirements.txt") from exc

        self._ua = ua
        self._client = Client(url=self.config.opcua_url)
        await self._client.connect()
        self._nodes = {
            "okng": self._client.get_node(self.config.opc_node_okng),
            "angle": self._client.get_node(self.config.opc_node_angle),
            "torque": self._client.get_node(self.config.opc_node_torque),
            "rw": self._client.get_node(self.config.opc_node_rw),
            "enable": self._client.get_node(self.config.opc_node_enable),
            "program": self._client.get_node(self.config.opc_node_program),
        }
        self._connected = True
        self._poll_task = asyncio.create_task(self._poll_rw())

    async def _disconnect(self) -> None:
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
            self._poll_task = None
        if self._client is not None:
            try:
                await self._write_enable(False)
            finally:
                await self._client.disconnect()
        self._client = None
        self._nodes = {}
        self._connected = False

    async def _poll_rw(self) -> None:
        while self._connected:
            try:
                rw = await self._nodes["rw"].read_value()
                if self._is_ready(rw):
                    payload = await self._read_result()
                    if self._callback:
                        self._callback(payload)
                    await self._write_rw(0)
            except asyncio.CancelledError:
                raise
            except Exception:
                await asyncio.sleep(1.0)
                continue
            await asyncio.sleep(float(self.config.opcua_poll_interval_seconds))

    async def _read_result(self) -> WrenchResult:
        okng = await self._nodes["okng"].read_value()
        angle = await self._nodes["angle"].read_value()
        torque = await self._nodes["torque"].read_value()
        return WrenchResult(
            result="OK" if self._is_ok(okng) else "NG",
            actual_torque=round(float(torque), 3),
            actual_angle=round(float(angle), 3),
        )

    async def _write_program(self, program_no: int) -> None:
        try:
            await self._write_value_only(
                self._nodes["program"], int(program_no), self._ua.VariantType.Int16
            )
        except Exception as exc:
            raise RuntimeError(f"写入FN程序号失败: {exc}") from exc

    async def _write_enable(self, enabled: bool) -> None:
        try:
            await self._write_value_only(
                self._nodes["enable"], bool(enabled), self._ua.VariantType.Boolean
            )
        except Exception as exc:
            raise RuntimeError(f"写入ENABLE使能失败: {exc}") from exc

    async def _write_rw(self, value: int) -> None:
        try:
            await self._write_value_only(
                self._nodes["rw"], int(value), self._ua.VariantType.Int16
            )
        except Exception as exc:
            raise RuntimeError(f"写入RW复位失败: {exc}") from exc

    async def _write_value_only(self, node, value, variant_type) -> None:
        """Write only the Value attribute.

        Some Kepware/PLC nodes reject writes that include status or timestamps
        and return BadWriteSupport. Build a DataValue whose encoding contains
        only the Variant value.
        """
        data_value = self._ua.DataValue()
        data_value.Value = self._ua.Variant(value, variant_type)

        for attr in (
            "StatusCode",
            "SourceTimestamp",
            "ServerTimestamp",
            "SourcePicoseconds",
            "ServerPicoseconds",
        ):
            if hasattr(data_value, attr):
                setattr(data_value, attr, None)

        await node.write_attribute(self._ua.AttributeIds.Value, data_value)

    @staticmethod
    def _is_ready(value) -> bool:
        try:
            return int(value) == 1
        except (TypeError, ValueError):
            return str(value).strip().lower() in {"true", "1"}

    @staticmethod
    def _is_ok(value) -> bool:
        try:
            return int(value) == 1
        except (TypeError, ValueError):
            return str(value).strip().lower() in {"true", "ok", "1"}
