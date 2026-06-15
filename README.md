# IGBT Torque Manager

Python + ttkbootstrap 工位上位机原型，用于控制电动扭矩扳手完成 IGBT 螺钉第二次、第三次线上拧紧，并记录过程数据。

## 已实现

- 用户登录，默认账号 `admin`，密码 `admin123`
- 产品类型维护
- 水冷基板条码扫码上线
- 已生产条码自动恢复产品和拧紧状态
- 第二次、第三次拧紧状态机
- 第二次完成后的静置时间防错
- 拧紧数量防错，达到当前轮次数量后自动禁用扳手
- 拧紧记录保存：时间、程序号、设定扭矩、实际扭矩、实际角度、结果、操作者
- 静置/待第三次队列
- Mock 扳手调试入口
- 按旧程序节点配置实现的 OPC UA 扳手通信适配器

## 本地运行

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

Linux/macOS 调试时激活命令为：

```bash
source .venv/bin/activate
```

## 数据库

默认使用本地 SQLite：

```text
data/torque.db
```

首次启动会自动建表，并创建一个示例产品。

## 设备通信配置

程序默认使用 `mock` 模式，方便在普通电脑上调试。无需配置文件也能启动。

如需显式配置，复制示例文件：

```bash
copy config\settings.example.json config\settings.json
```

普通电脑调试：

```json
{
  "device_mode": "mock"
}
```

工控机连接真实扭矩扳手：

```json
{
  "device_mode": "opcua",
  "opcua_url": "opc.tcp://127.0.0.1:49320/Kepware.KEPServerEX.V6",
  "opc_node_okng": "ns=2;s=通道 3.设备 1.OKNG",
  "opc_node_angle": "ns=2;s=通道 3.设备 1.ANG",
  "opc_node_torque": "ns=2;s=通道 3.设备 1.TOR",
  "opc_node_rw": "ns=2;s=通道 3.设备 1.RW",
  "opc_node_enable": "ns=2;s=通道 3.设备 1.ENABLE",
  "opc_node_program": "ns=2;s=通道 3.设备 1.FN"
}
```

也可以临时用环境变量覆盖：

```bash
set TORQUE_DEVICE_MODE=opcua
python main.py
```

OPC UA 逻辑与旧程序一致：写 `FN` 切换程序号，写 `ENABLE` 控制扳手使能；轮询 `RW`，当 `RW=1` 时读取 `OKNG/TOR/ANG`，记录完成后将 `RW` 写回 `0`。

## 打包

本地 Windows 可执行：

```bash
pyinstaller -F -w main.py --name IGBT_Torque_Manager
```

GitHub Actions 工作流已放在 `.github/workflows/build-windows.yml`，推送后可在 Actions 页面手动运行。

## 后续接真实扳手

真实设备适配入口在：

```text
app/devices/opcua_wrench.py
```

当前 UI 已经通过 `device_mode` 自动切换 `MockWrench` / `OpcUaWrench`。
