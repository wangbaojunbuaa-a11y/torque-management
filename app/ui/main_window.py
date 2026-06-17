from dataclasses import replace
from datetime import datetime, timedelta
import time
from tkinter import messagebox

import ttkbootstrap as ttk
from ttkbootstrap.constants import BOTH, LEFT, RIGHT, X

from app.config.app_config import AppConfig
from app.devices.device_factory import create_wrench
from app.models.enums import STATUS_LABELS
from app.services.offline_check_service import OfflineCheckService
from app.services.product_service import ProductService
from app.services.report_service import ReportService
from app.services.tightening_service import TighteningService
from app.services.user_service import UserService
from app.ui.input_helpers import focus_scanner_entry, switch_to_english_input
from app.ui.offline_check_dialog import OfflineCheckDialog
from app.ui.product_dialog import ProductDialog
from app.ui.report_dialog import ReportDialog
from app.ui.torque_settings_dialog import TorqueSettingsDialog
from app.ui.user_dialog import UserDialog


class MainWindow(ttk.Toplevel):
    def __init__(
        self,
        parent,
        user,
        user_service: UserService,
        product_service: ProductService,
        tightening_service: TighteningService,
        report_service: ReportService,
        offline_check_service: OfflineCheckService,
        config: AppConfig,
    ) -> None:
        super().__init__(parent)
        self.user = user
        self.user_service = user_service
        self.product_service = product_service
        self.tightening_service = tightening_service
        self.report_service = report_service
        self.offline_check_service = offline_check_service
        self.config = config
        self.wrench = None
        self.device_connected = False
        self._last_device_command = None

        self.products = []
        self.product_by_label = {}
        self.current_workpiece = None
        self.current_action = None

        self.title("IGBT扭矩管理")
        self.geometry("1600x900")
        self.minsize(1280, 720)
        self.protocol("WM_DELETE_WINDOW", self.close)

        self._configure_fonts()
        self._build_ui()
        self.connect_device()
        self.reload_products()
        self.refresh_rest_queue()
        self.after(200, self.focus_main_scanner)
        self.after(1000, self._tick)

    def _configure_fonts(self) -> None:
        self.option_add("*Font", ("Microsoft YaHei UI", 12))
        style = ttk.Style()
        style.configure(".", font=("Microsoft YaHei UI", 12))
        style.configure("TButton", font=("Microsoft YaHei UI", 12))
        style.configure("Treeview", font=("Microsoft YaHei UI", 12), rowheight=30)
        style.configure("Treeview.Heading", font=("Microsoft YaHei UI", 12, "bold"))
        style.configure("TLabelframe.Label", font=("Microsoft YaHei UI", 12, "bold"))

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=12)
        root.pack(fill=BOTH, expand=True)

        top = ttk.Frame(root)
        top.pack(fill=X)
        ttk.Label(top, text=f"当前用户：{self.user['name']} ({self.user['work_no']})").pack(
            side=LEFT
        )
        ttk.Label(top, text="设备").pack(side=LEFT, padx=(24, 4))
        self.device_mode_var = ttk.StringVar(value=self.config.device_mode.lower())
        self.device_mode_combo = ttk.Combobox(
            top,
            textvariable=self.device_mode_var,
            values=("mock", "opcua"),
            state="readonly",
            width=8,
        )
        self.device_mode_combo.pack(side=LEFT)
        self.device_status_var = ttk.StringVar(value="未连接")
        ttk.Label(top, textvariable=self.device_status_var).pack(side=LEFT, padx=(8, 0))
        ttk.Button(top, text="连接/重连", command=self.connect_device).pack(side=RIGHT, padx=(8, 0))
        ttk.Button(top, text="设置", command=self.open_settings_dialog).pack(side=RIGHT, padx=(8, 0))
        ttk.Button(top, text="下线检查", command=self.open_offline_check).pack(side=RIGHT, padx=(8, 0))
        ttk.Button(top, text="报表生成", command=self.open_report_dialog).pack(side=RIGHT, padx=(8, 0))
        ttk.Button(top, text="用户管理", command=self.open_user_dialog).pack(side=RIGHT, padx=(8, 0))
        ttk.Button(top, text="产品维护", command=self.open_product_dialog).pack(side=RIGHT)

        scan_bar = ttk.Labelframe(root, text="上线扫码", padding=10)
        scan_bar.pack(fill=X, pady=(12, 8))
        ttk.Label(scan_bar, text="产品类型").pack(side=LEFT)
        self.product_var = ttk.StringVar()
        self.product_combo = ttk.Combobox(
            scan_bar, textvariable=self.product_var, state="readonly", width=34
        )
        self.product_combo.pack(side=LEFT, padx=(6, 16))
        self.product_combo.bind("<<ComboboxSelected>>", lambda _event: self.after(100, self.focus_main_scanner))
        ttk.Label(scan_bar, text="水冷基板条码").pack(side=LEFT)
        self.barcode_var = ttk.StringVar()
        self.barcode_entry = ttk.Entry(scan_bar, textvariable=self.barcode_var, width=42)
        self.barcode_entry.pack(side=LEFT, padx=(6, 10), fill=X, expand=True)
        self.barcode_entry.bind("<FocusIn>", lambda _event: switch_to_english_input())
        self.barcode_entry.bind("<Return>", lambda _event: self.scan())
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
        self.value_labels = {}
        for idx, (label, key) in enumerate(rows):
            ttk.Label(current, text=label).grid(row=idx, column=0, sticky="w", pady=4)
            value_label = ttk.Label(current, textvariable=self.vars[key], font=("Microsoft YaHei UI", 14))
            value_label.grid(
                row=idx, column=1, sticky="w", pady=4, padx=(12, 0)
            )
            self.value_labels[key] = value_label
        current.columnconfigure(1, weight=1)

        actions = ttk.Frame(left)
        actions.pack(fill=X, pady=10)
        self.manual_mode_var = ttk.BooleanVar(value=False)
        ttk.Checkbutton(actions, text="手动模式", variable=self.manual_mode_var).pack(
            side=LEFT, padx=(0, 8)
        )
        self.manual_program_var = ttk.StringVar(value="1")
        self.manual_program_combo = ttk.Combobox(
            actions,
            textvariable=self.manual_program_var,
            values=("1", "2", "3"),
            state="readonly",
            width=5,
        )
        self.manual_program_combo.pack(side=LEFT, padx=(0, 8))
        ttk.Button(actions, text="手动使能", bootstyle="warning", command=self.manual_enable).pack(
            side=LEFT, padx=(0, 8)
        )
        ttk.Button(actions, text="手动禁用", command=self.manual_disable).pack(
            side=LEFT, padx=(0, 12)
        )
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
        self.records_tree.tag_configure("OK", foreground="#198754")
        self.records_tree.tag_configure("NG", foreground="#dc3545")
        self.records_tree.pack(fill=BOTH, expand=True)

        rest_box = ttk.Labelframe(right, text="生产队列：待第二次/静置/待第三次", padding=8)
        rest_box.pack(fill=BOTH, expand=True)
        self.rest_tree = ttk.Treeview(
            rest_box,
            columns=("barcode", "product", "stage", "progress", "ready", "left"),
            show="headings",
        )
        for key, text in {
            "barcode": "条码",
            "product": "产品",
            "stage": "阶段",
            "progress": "进度",
            "ready": "可拧时间",
            "left": "剩余",
        }.items():
            self.rest_tree.heading(key, text=text)
            self.rest_tree.column(key, width=120, anchor="center")
        self.rest_tree.column("barcode", width=220)
        self.rest_tree.column("progress", width=150)
        self.rest_tree.pack(fill=BOTH, expand=True)
        self.rest_tree.bind("<Double-1>", self.load_from_queue)
        queue_buttons = ttk.Frame(rest_box)
        queue_buttons.pack(fill=X, pady=(8, 0))
        ttk.Button(
            queue_buttons,
            text="删除所选未完成工件",
            bootstyle="danger",
            command=self.delete_selected_queue_item,
        ).pack(side=RIGHT)

    def reload_products(self) -> None:
        self.products = self.product_service.list_active()
        labels = [f"{row['code']} - {row['name']}" for row in self.products]
        self.product_by_label = dict(zip(labels, self.products))
        self.product_combo["values"] = labels

    def open_product_dialog(self) -> None:
        ProductDialog(self, self.product_service, self.reload_products)

    def open_user_dialog(self) -> None:
        UserDialog(self, self.user_service)

    def open_report_dialog(self) -> None:
        ReportDialog(self, self.product_service, self.report_service, self.config)

    def open_offline_check(self) -> None:
        OfflineCheckDialog(self, self.offline_check_service, self.config)

    def open_settings_dialog(self) -> None:
        TorqueSettingsDialog(self, self.config)

    def selected_product_id(self) -> int | None:
        row = self.product_by_label.get(self.product_var.get())
        return int(row["id"]) if row else None

    def focus_main_scanner(self) -> None:
        if hasattr(self, "barcode_entry"):
            focus_scanner_entry(self.barcode_entry)

    def connect_device(self) -> None:
        selected_mode = self.device_mode_var.get().strip().lower()
        if selected_mode not in {"mock", "opcua"}:
            messagebox.showerror("设备模式错误", f"不支持的设备模式：{selected_mode}")
            return

        if self.wrench is not None:
            try:
                self.wrench.disconnect()
            except Exception:
                pass

        self.config = replace(self.config, device_mode=selected_mode)
        self.wrench = create_wrench(self.config)
        self.device_connected = False
        self._last_device_command = None
        self._update_mock_buttons()

        try:
            self.wrench.on_tightening_done(
                lambda payload: self.after(0, self.handle_wrench_result, payload)
            )
            self.wrench.connect()
        except Exception as exc:
            self.device_connected = False
            self.device_status_var.set(f"{selected_mode} 连接失败")
            self._update_mock_buttons()
            messagebox.showerror("设备连接失败", str(exc))
            return

        self.device_connected = True
        self._last_device_command = None
        self.device_status_var.set(f"{selected_mode} 已连接")
        self._update_mock_buttons()
        if self.current_action:
            self.apply_action(self.current_action)

    def _update_mock_buttons(self) -> None:
        if not hasattr(self, "mock_ok_button"):
            return
        state = "normal" if self.config.device_mode.lower() == "mock" and self.device_connected else "disabled"
        self.mock_ok_button.configure(state=state)
        self.mock_ng_button.configure(state=state)

    def manual_enable(self) -> None:
        if not self.device_connected or self.wrench is None:
            self.play_sound("error")
            messagebox.showwarning("设备未连接", "请先连接扳手设备")
            return
        try:
            program_no = int(self.manual_program_var.get())
            self.command_wrench("enable", program_no)
        except Exception as exc:
            self.play_sound("error")
            messagebox.showerror("手动使能失败", str(exc))
            return
        self.manual_mode_var.set(True)
        self.current_workpiece = None
        self.current_action = None
        self.clear_current_panel(status=f"手动模式：程序 {program_no} 已使能", wrench="已使能")
        self.set_status_color("warning")

    def manual_disable(self) -> None:
        try:
            self.command_wrench("disable", None)
        except Exception:
            pass
        self.manual_mode_var.set(False)
        self.clear_current_panel(status="待扫码", wrench="已禁用" if self.device_connected else "设备未连接")

    def scan(self) -> None:
        switch_to_english_input()
        try:
            workpiece, action = self.tightening_service.scan_workpiece(
                self.barcode_var.get(), self.selected_product_id()
            )
        except Exception as exc:
            self.set_status_color("danger")
            self.play_sound("error")
            messagebox.showerror("扫码失败", str(exc))
            self.focus_main_scanner()
            return
        if workpiece is None:
            self.set_status_color("warning")
            self.play_sound("error")
            messagebox.showwarning("需要选择产品", action["message"])
            self.focus_main_scanner()
            return
        self.current_workpiece = workpiece
        self.current_action = action
        self.apply_action(action)
        self.load_records()
        self.refresh_rest_queue()
        self.barcode_var.set("")
        self.focus_main_scanner()

    def apply_action(self, action: dict) -> None:
        workpiece = self.tightening_service.get_workpiece(self.current_workpiece["id"])
        self.current_workpiece = workpiece
        self.vars["barcode"].set(workpiece["base_barcode"])
        self.vars["product"].set(f"{workpiece['product_code']} - {workpiece['product_name']}")
        self.vars["status"].set(action["message"])
        self.set_status_color(self._style_for_action(action))

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
        if not self.device_connected or self.wrench is None:
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
            self.device_status_var.set(f"{self.config.device_mode} 通信失败")
            self._update_mock_buttons()
            messagebox.showerror("设备通信失败", str(exc))
            return
        self._last_device_command = device_command

    def mock_result(self, result: str) -> None:
        if not self.current_workpiece or not self.current_action:
            self.play_sound("error")
            messagebox.showwarning("未扫码", "请先扫描水冷基板条码")
            self.focus_main_scanner()
            return
        if self.wrench is None or not hasattr(self.wrench, "simulate"):
            self.play_sound("error")
            messagebox.showwarning("不可用", "当前不是mock模式，结果由OPC UA自动采集")
            self.focus_main_scanner()
            return
        try:
            set_torque = float(self.current_action.get("set_torque", 0))
            self.wrench.simulate(result, set_torque)
        except Exception as exc:
            self.play_sound("error")
            messagebox.showerror("拧紧禁止", str(exc))
            self.focus_main_scanner()
            return

    def handle_wrench_result(self, payload) -> None:
        if self.manual_mode_var.get():
            self.vars["last"].set(
                f"手动 {payload.result}  扭矩:{payload.actual_torque}  角度:{payload.actual_angle}"
            )
            self.play_sound("success" if payload.result == "OK" else "error")
            return
        if not self.current_workpiece or not self.current_action:
            return
        previous_action = dict(self.current_action)
        try:
            action = self.tightening_service.record_tightening(
                self.current_workpiece["id"],
                self.user["work_no"],
                payload.result,
                payload.actual_torque,
                payload.actual_angle,
            )
        except Exception as exc:
            self.set_status_color("danger")
            self.play_sound("error")
            messagebox.showerror("拧紧禁止", str(exc))
            return
        self.play_sound("success" if payload.result == "OK" else "error")
        self.current_action = action
        self.vars["last"].set(
            f"{payload.result}  扭矩:{payload.actual_torque}  角度:{payload.actual_angle}"
        )
        stage_completed = (
            previous_action.get("state") == "ROUND2" and action.get("state") == "RESTING"
        ) or (
            previous_action.get("state") == "ROUND3" and action.get("state") == "FINISHED"
        )
        if stage_completed:
            self.command_wrench("disable", None)
            self.load_records()
            self.refresh_rest_queue()
            self.clear_current_panel()
            return
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
                tags=(row["result"],),
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
        for row in self.tightening_service.production_queue():
            ready = row["ready_at"].strftime("%H:%M:%S") if row["ready_at"] else "-"
            progress = f"二次 {row['round2_ok']}/{row['expected']}  三次 {row['round3_ok']}/{row['expected']}"
            self.rest_tree.insert(
                "",
                "end",
                iid=str(row["id"]),
                values=(
                    row["base_barcode"],
                    row["product_code"],
                    row["stage"],
                    progress,
                    ready,
                    row["left"],
                ),
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
        self.focus_main_scanner()

    def delete_selected_queue_item(self) -> None:
        selected = self.rest_tree.selection()
        if not selected:
            messagebox.showwarning("未选择", "请先选择生产队列中的一行")
            return
        workpiece_id = int(selected[0])
        workpiece = self.tightening_service.get_workpiece(workpiece_id)
        if workpiece is None:
            self.refresh_rest_queue()
            return
        if not messagebox.askyesno(
            "确认删除",
            f"确定删除未完成工件？\n\n水冷基板条码：{workpiece['base_barcode']}\n产品：{workpiece['product_code']} - {workpiece['product_name']}\n\n相关拧紧记录也会删除。",
        ):
            return
        try:
            self.tightening_service.delete_unfinished_workpiece(workpiece_id)
        except Exception as exc:
            self.play_sound("error")
            messagebox.showerror("删除失败", str(exc))
            return
        if self.current_workpiece and int(self.current_workpiece["id"]) == workpiece_id:
            self.clear_current_panel()
        self.refresh_rest_queue()

    def _tick(self) -> None:
        self.refresh_rest_queue()
        if self.current_workpiece:
            self.current_action = self.tightening_service.decide_action(self.current_workpiece["id"])
            self.apply_action(self.current_action)
        self.after(1000, self._tick)

    def clear_current_panel(self, status: str = "待扫码", wrench: str = "未使能") -> None:
        self.current_workpiece = None
        self.current_action = None
        self.vars["barcode"].set("-")
        self.vars["product"].set("-")
        self.vars["status"].set(status)
        self.vars["round"].set("-")
        self.vars["program"].set("-")
        self.vars["set_torque"].set("-")
        self.vars["count"].set("-")
        self.vars["wrench"].set(wrench)
        self.vars["last"].set("-")
        self.records_tree.delete(*self.records_tree.get_children())
        self.set_status_color("secondary")
        self.focus_main_scanner()

    def _style_for_action(self, action: dict) -> str:
        state = action.get("state")
        if state in {"ROUND2", "ROUND3"}:
            return "success"
        if state == "RESTING":
            return "warning"
        if state == "FINISHED":
            return "info"
        return "secondary"

    def set_status_color(self, style: str) -> None:
        label = getattr(self, "value_labels", {}).get("status")
        if label is not None:
            label.configure(bootstyle=style)

    def play_sound(self, sound_type: str) -> None:
        try:
            import winsound
        except Exception:
            return
        value = self.config.sound_success if sound_type == "success" else self.config.sound_error
        count = 1 if sound_type == "success" else max(1, int(self.config.sound_count))
        interval = max(0.0, float(self.config.sound_interval))
        for index in range(count):
            try:
                if value == -1:
                    winsound.Beep(1000, 160)
                else:
                    winsound.MessageBeep(int(value))
            except Exception:
                pass
            if index + 1 < count and interval:
                time.sleep(interval)

    def close(self) -> None:
        try:
            if self.wrench is not None:
                self.wrench.disconnect()
        except Exception:
            pass
        self.master.destroy()
