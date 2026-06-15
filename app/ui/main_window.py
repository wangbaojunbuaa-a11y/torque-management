from datetime import datetime, timedelta
from tkinter import messagebox

import ttkbootstrap as ttk
from ttkbootstrap.constants import BOTH, LEFT, RIGHT, X

from app.config.app_config import AppConfig
from app.devices.device_factory import create_wrench
from app.models.enums import STATUS_LABELS
from app.services.product_service import ProductService
from app.services.tightening_service import TighteningService
from app.ui.product_dialog import ProductDialog


class MainWindow(ttk.Toplevel):
    def __init__(
        self,
        parent,
        user,
        product_service: ProductService,
        tightening_service: TighteningService,
        config: AppConfig,
    ) -> None:
        super().__init__(parent)
        self.user = user
        self.product_service = product_service
        self.tightening_service = tightening_service
        self.config = config
        self.wrench = create_wrench(config)
        self.device_connected = False
        self._last_device_command = None

        self.products = []
        self.product_by_label = {}
        self.current_workpiece = None
        self.current_action = None

        self.title("IGBT扭矩管理")
        self.geometry("1280x760")
        self.minsize(1100, 680)
        self.protocol("WM_DELETE_WINDOW", self.close)

        self._build_ui()
        self.connect_device()
        self.reload_products()
        self.refresh_rest_queue()
        self.after(1000, self._tick)

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=12)
        root.pack(fill=BOTH, expand=True)

        top = ttk.Frame(root)
        top.pack(fill=X)
        ttk.Label(top, text=f"当前用户：{self.user['name']} ({self.user['work_no']})").pack(
            side=LEFT
        )
        self.device_var = ttk.StringVar(value=f"设备模式：{self.config.device_mode}")
        ttk.Label(top, textvariable=self.device_var).pack(side=LEFT, padx=(24, 0))
        ttk.Button(top, text="重连设备", command=self.connect_device).pack(side=RIGHT, padx=(8, 0))
        ttk.Button(top, text="产品维护", command=self.open_product_dialog).pack(side=RIGHT)

        scan_bar = ttk.Labelframe(root, text="上线扫码", padding=10)
        scan_bar.pack(fill=X, pady=(12, 8))
        ttk.Label(scan_bar, text="产品类型").pack(side=LEFT)
        self.product_var = ttk.StringVar()
        self.product_combo = ttk.Combobox(
            scan_bar, textvariable=self.product_var, state="readonly", width=34
        )
        self.product_combo.pack(side=LEFT, padx=(6, 16))
        ttk.Label(scan_bar, text="水冷基板条码").pack(side=LEFT)
        self.barcode_var = ttk.StringVar()
        barcode_entry = ttk.Entry(scan_bar, textvariable=self.barcode_var, width=42)
        barcode_entry.pack(side=LEFT, padx=(6, 10), fill=X, expand=True)
        barcode_entry.bind("<Return>", lambda _event: self.scan())
        ttk.Button(scan_bar, text="确认", bootstyle="primary", command=self.scan).pack(side=LEFT)

        body = ttk.Frame(root)
        body.pack(fill=BOTH, expand=True)
        left = ttk.Frame(body)
        left.pack(side=LEFT, fill=BOTH, expand=True, padx=(0, 8))
        right = ttk.Frame(body)
        right.pack(side=RIGHT, fill=BOTH, expand=True, padx=(8, 0))

        current = ttk.Labelframe(left, text="当前工件", padding=12)
        current.pack(fill=X)
        self.vars = {
            "barcode": ttk.StringVar(value="-"),
            "product": ttk.StringVar(value="-"),
            "status": ttk.StringVar(value="待扫码"),
            "round": ttk.StringVar(value="-"),
            "program": ttk.StringVar(value="-"),
            "set_torque": ttk.StringVar(value="-"),
            "count": ttk.StringVar(value="-"),
            "wrench": ttk.StringVar(value="未使能"),
            "last": ttk.StringVar(value="-"),
        }
        rows = [
            ("条码", "barcode"),
            ("产品", "product"),
            ("状态", "status"),
            ("轮次", "round"),
            ("程序号", "program"),
            ("设定扭矩", "set_torque"),
            ("数量", "count"),
            ("扳手", "wrench"),
            ("最近记录", "last"),
        ]
        for idx, (label, key) in enumerate(rows):
            ttk.Label(current, text=label).grid(row=idx, column=0, sticky="w", pady=4)
            ttk.Label(current, textvariable=self.vars[key], font=("Microsoft YaHei UI", 12)).grid(
                row=idx, column=1, sticky="w", pady=4, padx=(12, 0)
            )
        current.columnconfigure(1, weight=1)

        actions = ttk.Frame(left)
        actions.pack(fill=X, pady=10)
        self.mock_ok_button = ttk.Button(
            actions, text="模拟OK", bootstyle="success", command=lambda: self.mock_result("OK")
        )
        self.mock_ok_button.pack(
            side=LEFT, fill=X, expand=True, padx=(0, 6)
        )
        self.mock_ng_button = ttk.Button(
            actions, text="模拟NG", bootstyle="danger", command=lambda: self.mock_result("NG")
        )
        self.mock_ng_button.pack(
            side=LEFT, fill=X, expand=True, padx=(6, 0)
        )
        if self.config.device_mode.lower() != "mock":
            self.mock_ok_button.configure(state="disabled")
            self.mock_ng_button.configure(state="disabled")

        records_box = ttk.Labelframe(left, text="当前工件拧紧记录", padding=8)
        records_box.pack(fill=BOTH, expand=True)
        self.records_tree = ttk.Treeview(
            records_box,
            columns=("time", "round", "seq", "program", "set", "actual", "angle", "result", "op"),
            show="headings",
        )
        record_headings = {
            "time": "时间",
            "round": "轮次",
            "seq": "序号",
            "program": "程序",
            "set": "设定",
            "actual": "实际扭矩",
            "angle": "角度",
            "result": "结果",
            "op": "操作者",
        }
        for key, text in record_headings.items():
            self.records_tree.heading(key, text=text)
            self.records_tree.column(key, width=90, anchor="center")
        self.records_tree.column("time", width=150)
        self.records_tree.pack(fill=BOTH, expand=True)

        rest_box = ttk.Labelframe(right, text="静置/待第三次队列", padding=8)
        rest_box.pack(fill=BOTH, expand=True)
        self.rest_tree = ttk.Treeview(
            rest_box,
            columns=("barcode", "product", "status", "ready", "left"),
            show="headings",
        )
        for key, text in {
            "barcode": "条码",
            "product": "产品",
            "status": "状态",
            "ready": "可拧时间",
            "left": "剩余",
        }.items():
            self.rest_tree.heading(key, text=text)
            self.rest_tree.column(key, width=120, anchor="center")
        self.rest_tree.column("barcode", width=220)
        self.rest_tree.pack(fill=BOTH, expand=True)
        self.rest_tree.bind("<Double-1>", self.load_from_queue)

    def reload_products(self) -> None:
        self.products = self.product_service.list_active()
        labels = [f"{row['code']} - {row['name']}" for row in self.products]
        self.product_by_label = dict(zip(labels, self.products))
        self.product_combo["values"] = labels

    def open_product_dialog(self) -> None:
        ProductDialog(self, self.product_service, self.reload_products)

    def selected_product_id(self) -> int | None:
        row = self.product_by_label.get(self.product_var.get())
        return int(row["id"]) if row else None

    def connect_device(self) -> None:
        try:
            self.wrench.on_tightening_done(
                lambda payload: self.after(0, self.handle_wrench_result, payload)
            )
            self.wrench.connect()
        except Exception as exc:
            self.device_connected = False
            self.device_var.set(f"设备模式：{self.config.device_mode}，连接失败")
            messagebox.showerror("设备连接失败", str(exc))
            return

        self.device_connected = True
        self._last_device_command = None
        self.device_var.set(f"设备模式：{self.config.device_mode}，已连接")

    def scan(self) -> None:
        try:
            workpiece, action = self.tightening_service.scan_workpiece(
                self.barcode_var.get(), self.selected_product_id()
            )
        except Exception as exc:
            messagebox.showerror("扫码失败", str(exc))
            return
        if workpiece is None:
            messagebox.showwarning("需要选择产品", action["message"])
            return
        self.current_workpiece = workpiece
        self.current_action = action
        self.apply_action(action)
        self.load_records()
        self.refresh_rest_queue()
        self.barcode_var.set("")

    def apply_action(self, action: dict) -> None:
        workpiece = self.tightening_service.get_workpiece(self.current_workpiece["id"])
        self.current_workpiece = workpiece
        self.vars["barcode"].set(workpiece["base_barcode"])
        self.vars["product"].set(f"{workpiece['product_code']} - {workpiece['product_name']}")
        self.vars["status"].set(action["message"])

        if action["state"] in {"ROUND2", "ROUND3"}:
            self.command_wrench("enable", int(action["program_no"]))
            self.vars["round"].set(f"第{action['round_no']}次")
            self.vars["program"].set(str(action["program_no"]))
            self.vars["set_torque"].set(f"{action['set_torque']} N.m")
            self.vars["count"].set(f"{action['done']} / {action['expected']}")
            self.vars["wrench"].set("已使能" if self.device_connected else "设备未连接")
        else:
            self.command_wrench("disable", None)
            self.vars["round"].set("-")
            self.vars["program"].set("-")
            self.vars["set_torque"].set("-")
            if "done" in action:
                self.vars["count"].set(f"{action['done']} / {action['expected']}")
            self.vars["wrench"].set("已禁用" if self.device_connected else "设备未连接")

    def command_wrench(self, command: str, program_no: int | None) -> None:
        if not self.device_connected:
            return
        device_command = (command, program_no)
        if device_command == self._last_device_command:
            return
        try:
            if command == "enable":
                self.wrench.set_program(int(program_no))
                self.wrench.enable()
            else:
                self.wrench.disable()
        except Exception as exc:
            self.device_connected = False
            self.device_var.set(f"设备模式：{self.config.device_mode}，通信失败")
            messagebox.showerror("设备通信失败", str(exc))
            return
        self._last_device_command = device_command

    def mock_result(self, result: str) -> None:
        if not self.current_workpiece or not self.current_action:
            messagebox.showwarning("未扫码", "请先扫描水冷基板条码")
            return
        if not hasattr(self.wrench, "simulate"):
            messagebox.showwarning("不可用", "当前不是mock模式，结果由OPC UA自动采集")
            return
        try:
            set_torque = float(self.current_action.get("set_torque", 0))
            self.wrench.simulate(result, set_torque)
        except Exception as exc:
            messagebox.showerror("拧紧禁止", str(exc))
            return

    def handle_wrench_result(self, payload) -> None:
        if not self.current_workpiece or not self.current_action:
            return
        try:
            action = self.tightening_service.record_tightening(
                self.current_workpiece["id"],
                self.user["work_no"],
                payload.result,
                payload.actual_torque,
                payload.actual_angle,
            )
        except Exception as exc:
            messagebox.showerror("拧紧禁止", str(exc))
            return
        self.current_action = action
        self.vars["last"].set(
            f"{payload.result}  扭矩:{payload.actual_torque}  角度:{payload.actual_angle}"
        )
        self.apply_action(action)
        self.load_records()
        self.refresh_rest_queue()

    def load_records(self) -> None:
        self.records_tree.delete(*self.records_tree.get_children())
        if not self.current_workpiece:
            return
        for row in self.tightening_service.records_for_workpiece(self.current_workpiece["id"]):
            self.records_tree.insert(
                "",
                "end",
                values=(
                    row["tightened_at"],
                    row["round_no"],
                    row["sequence_no"],
                    row["program_no"],
                    row["set_torque"],
                    row["actual_torque"],
                    row["actual_angle"],
                    row["result"],
                    row["operator_work_no"],
                ),
            )

    def refresh_rest_queue(self) -> None:
        self.rest_tree.delete(*self.rest_tree.get_children())
        now = datetime.now()
        for row in self.tightening_service.rest_queue():
            status_label = STATUS_LABELS.get(row["status"], row["status"])
            ready = "-"
            left = "-"
            if row["round2_completed_at"]:
                ready_dt = datetime.fromisoformat(row["round2_completed_at"]) + timedelta(
                    minutes=int(row["rest_minutes"])
                )
                ready = ready_dt.strftime("%H:%M:%S")
                if ready_dt > now:
                    seconds = int((ready_dt - now).total_seconds())
                    left = f"{seconds // 60:02d}:{seconds % 60:02d}"
                else:
                    left = "可拧紧"
            self.rest_tree.insert(
                "",
                "end",
                iid=str(row["id"]),
                values=(row["base_barcode"], row["product_code"], status_label, ready, left),
            )

    def load_from_queue(self, _event=None) -> None:
        selected = self.rest_tree.selection()
        if not selected:
            return
        workpiece_id = int(selected[0])
        self.current_workpiece = self.tightening_service.get_workpiece(workpiece_id)
        self.current_action = self.tightening_service.decide_action(workpiece_id)
        self.apply_action(self.current_action)
        self.load_records()
        self.refresh_rest_queue()

    def _tick(self) -> None:
        self.refresh_rest_queue()
        if self.current_workpiece:
            self.current_action = self.tightening_service.decide_action(self.current_workpiece["id"])
            self.apply_action(self.current_action)
        self.after(1000, self._tick)

    def close(self) -> None:
        try:
            self.wrench.disconnect()
        except Exception:
            pass
        self.master.destroy()
