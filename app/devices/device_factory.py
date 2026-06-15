from app.config.app_config import AppConfig
from app.devices.mock_wrench import MockWrench
from app.devices.opcua_wrench import OpcUaWrench


def create_wrench(config: AppConfig):
    mode = config.device_mode.lower().strip()
    if mode == "mock":
        return MockWrench()
    if mode == "opcua":
        return OpcUaWrench(config)
    raise ValueError(f"不支持的设备模式: {config.device_mode}")
