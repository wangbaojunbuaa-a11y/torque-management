from __future__ import annotations

from datetime import date
import time
import tkinter as tk
from tkinter import filedialog, messagebox

import ttkbootstrap as ttk
from ttkbootstrap.constants import BOTH, END, LEFT, RIGHT, X

from app.services.auth_service import AuthService
from app.services.user_service import UserService
from app.ui.input_helpers import focus_scanner_entry, switch_to_english_input
from app.ui.user_dialog import UserDialog
from coating.config import CoatingConfig
from coating.report_service import CoatingReportService
from coating.services import CoatingRecordService


class CoatingLoginWindow(ttk.Window):
    def __init__(
        self,
        auth_service: AuthService,
        user_service: UserService,
        record_service: CoatingRecordService,
        report_service: CoatingReportService,
        config: CoatingConfig,
    ) -> None:
        super().__init__(themename="flatly")
        self.auth_service = auth_service
        self.user_service = user_service
        self.record_service = record_service
        self.report_service = report_service
        self.config = config

        self.title("水冷基板涂敷记录 - 登录")
        self.geometry("680x440")
        self.minsize(560, 380)
        self.resizable(True, True)

        frame = ttk.Frame(self, padding=32)
        frame.pack(fill=BOTH, expand=True)

        ttk.Label(frame, text="水冷基板涂敷记录", font=("Microsoft YaHei UI", 24, "bold")).pack(
            anchor="w", pady=(0, 26)
        )

        ttk.Label(frame, text="工号").pack(anchor="w")
        user_options = self._work_no_options()
        default_work_no = self._default_work_no(user_options)
        self.work_no_var = ttk.StringVar(value=default_work_no)
        ttk.Combobox(
            frame,
            textvariable=self.work_no_var,
            values=user_options,
            state="readonly",
            font=("Microsoft YaHei UI", 12),
        ).pack(
            fill=X, pady=(4, 12)
        )

        ttk.Label(frame, text="密码").pack(anchor="w")
        self.password_var = ttk.StringVar(value="")
        password_entry = ttk.Entry(
            frame, textvariable=self.password_var, show="*", font=("Microsoft YaHei UI", 12)
        )
        password_entry.pack(fill=X, pady=(4, 18))
        password_entry.bind("<Return>", lambda _event: self.login())

        ttk.Button(frame, text="登录", bootstyle="primary", command=self.login).pack(fill=X)

    def _work_no_options(self) -> list[str]:
        rows = self.user_service.list_users()
        values = [row["work_no"] for row in rows if row["active"]]
        return values or ["admin"]

    def _default_work_no(self, options: list[str]) -> str:
        last = self.config.last_login_work_no or ""
        if last in options:
            return last
        if "admin" in options:
            return "admin"
        return options[0]

    def login(self) -> None:
        user = self.auth_service.login(self.work_no_var.get(), self.password_var.get())
        if user is None:
            messagebox.showerror("登录失败", "工号或密码错误", parent=self)
            return
        self.config.last_login_work_no = user["work_no"]
        self.config.save()
        self.withdraw()
        CoatingModeWindow(
            self,
            user,
            self.user_service,
            self.record_service,
            self.report_service,
            self.config,
        )


class CoatingModeWindow(ttk.Toplevel):
    def __init__(
        self,
        parent,
        user,
        user_service: UserService,
        record_service: CoatingRecordService,
        report_service: CoatingReportService,
        config: CoatingConfig,
    ) -> None:
        super().__init__(parent)
        self.parent = parent
        self.user = user
        self.user_service = user_service
        self.record_service = record_service
        self.report_service = report_service
        self.config = config
        self.users = [row for row in user_service.list_users() if row["active"]]
        self.user_by_label = {
            f"{row['name']} ({row['work_no']})": row
            for row in self.users
            if row["work_no"] != user["work_no"]
        }

        self.title("选择涂敷作业模式")
        self.geometry("760x460")
        self.minsize(640, 380)
        self.protocol("WM_DELETE_WINDOW", self.close)

        root = ttk.Frame(self, padding=32)
        root.pack(fill=BOTH, expand=True)
        ttk.Label(root, text="选择涂敷作业模式", font=("Microsoft YaHei UI", 22, "bold")).pack(
            anchor="w", pady=(0, 18)
        )
        ttk.Label(root, text=f"当前用户：{user['name']} ({user['work_no']})").pack(anchor="w")

        card = ttk.Labelframe(root, text="作业模式", padding=16)
        card.pack(fill=X, pady=18)
        self.mode_var = ttk.StringVar(value="single")
        ttk.Radiobutton(card, text="单人独立涂敷", value="single", variable=self.mode_var, command=self._sync_mode).pack(
            anchor="w", pady=4
        )
        ttk.Radiobutton(card, text="双人协作涂敷", value="double", variable=self.mode_var, command=self._sync_mode).pack(
            anchor="w", pady=4
        )

        row = ttk.Frame(card)
        row.pack(fill=X, pady=(12, 0))
        ttk.Label(row, text="协作人员").pack(side=LEFT)
        self.assistant_var = ttk.StringVar()
        self.assistant_combo = ttk.Combobox(
            row,
            textvariable=self.assistant_var,
            values=list(self.user_by_label.keys()),
            state="disabled",
            width=32,
        )
        self.assistant_combo.pack(side=LEFT, padx=(8, 0))

        buttons = ttk.Frame(root)
        buttons.pack(fill=X)
        ttk.Button(buttons, text="开始作业", bootstyle="primary", command=self.start).pack(
            side=LEFT, fill=X, expand=True, padx=(0, 8)
        )
        ttk.Button(buttons, text="退出登录", command=self.logout).pack(side=LEFT, fill=X, expand=True)

    def _sync_mode(self) -> None:
        state = "readonly" if self.mode_var.get() == "double" else "disabled"
        self.assistant_combo.configure(state=state)
        if state == "disabled":
            self.assistant_var.set("")

    def start(self) -> None:
        assistant = None
        if self.mode_var.get() == "double":
            assistant = self.user_by_label.get(self.assistant_var.get())
            if assistant is None:
                messagebox.showwarning("提示", "请选择协作人员", parent=self)
                return
        self.withdraw()
        CoatingMainWindow(
            self,
            self.user,
            self.user_service,
            self.record_service,
            self.report_service,
            self.config,
            assistant,
        )

    def logout(self) -> None:
        mode_window = self.parent
        login_window = mode_window.parent
        self.destroy()
        mode_window.destroy()
        login_window.deiconify()

    def close(self) -> None:
        self.destroy()
        self.parent.destroy()


class CoatingMainWindow(ttk.Toplevel):
    def __init__(
        self,
        parent,
        user,
        user_service: UserService,
        record_service: CoatingRecordService,
        report_service: CoatingReportService,
        config: CoatingConfig,
        assistant=None,
    ) -> None:
        super().__init__(parent)
        self.parent = parent
        self.user = user
        self.user_service = user_service
        self.record_service = record_service
        self.report_service = report_service
        self.config = config
        self.assistant = assistant
        self.show_today_only = True

        self.title("水冷基板涂敷记录")
        self.geometry("1400x820")
        self.minsize(1100, 680)
        self.protocol("WM_DELETE_WINDOW", self.close)

        self._build_ui()
        self.reload_records()
        self.after(200, self.focus_scanner)

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=12)
        root.pack(fill=BOTH, expand=True)

        top = ttk.Frame(root)
        top.pack(fill=X)
        ttk.Label(top, text=f"当前用户：{self.user['name']} ({self.user['work_no']})").pack(
            side=LEFT
        )
        mode_text = (
            f"双人协作：{self.assistant['name']} ({self.assistant['work_no']})"
            if self.assistant
            else "单人独立作业"
        )
        ttk.Label(top, text=mode_text).pack(side=LEFT, padx=(24, 0))
        ttk.Button(top, text="退出登录", command=self.logout).pack(side=RIGHT, padx=(8, 0))
        ttk.Button(top, text="设置", command=self.open_settings_dialog).pack(side=RIGHT, padx=(8, 0))
        ttk.Button(top, text="用户管理", command=self.open_user_dialog).pack(side=RIGHT, padx=(8, 0))
        ttk.Button(top, text="手动导出", bootstyle="primary", command=self.open_export_dialog).pack(
            side=RIGHT
        )

        scan_box = ttk.Labelframe(root, text="涂敷扫码", padding=10)
        scan_box.pack(fill=X, pady=(12, 8))
        ttk.Label(scan_box, text="水冷基板条码").pack(side=LEFT)
        self.plate_var = ttk.StringVar()
        self.plate_entry = ttk.Entry(scan_box, textvariable=self.plate_var, width=46)
        self.plate_entry.pack(side=LEFT, fill=X, expand=True, padx=(8, 12))
        self.plate_entry.bind("<FocusIn>", lambda _event: switch_to_english_input())
        self.plate_entry.bind("<Return>", lambda _event: self.save_record())
        ttk.Button(scan_box, text="记录", bootstyle="success", command=self.save_record).pack(
            side=LEFT
        )

        note_box = ttk.Frame(root)
        note_box.pack(fill=X, pady=(0, 8))
        ttk.Label(note_box, text="备注").pack(side=LEFT)
        self.note_var = ttk.StringVar()
        ttk.Entry(note_box, textvariable=self.note_var).pack(side=LEFT, fill=X, expand=True, padx=(8, 0))

        status_box = ttk.Labelframe(root, text="状态", padding=10)
        status_box.pack(fill=X, pady=(0, 8))
        self.status_var = ttk.StringVar(value="请扫描水冷基板条码")
        ttk.Label(status_box, textvariable=self.status_var, font=("Microsoft YaHei UI", 13)).pack(
            anchor="w"
        )

        log_box = ttk.Labelframe(root, text="扫码日志", padding=8)
        log_box.pack(fill=X, pady=(0, 8))
        self.log_text = tk.Text(
            log_box,
            height=6,
            font=("Consolas", 11),
            relief=tk.FLAT,
            wrap="none",
        )
        self.log_text.pack(fill=X)
        self.log_text.tag_config("ok", foreground="#198754")
        self.log_text.tag_config("error", foreground="#dc3545")
        self.log_text.tag_config("info", foreground="#6c757d")

        records_box = ttk.Labelframe(root, text="涂敷记录", padding=8)
        records_box.pack(fill=BOTH, expand=True)
        toolbar = ttk.Frame(records_box)
        toolbar.pack(fill=X, pady=(0, 8))
        self.today_var = ttk.BooleanVar(value=True)
        ttk.Checkbutton(
            toolbar,
            text="仅显示今日记录",
            variable=self.today_var,
            command=self.reload_records,
        ).pack(side=LEFT)
        ttk.Button(toolbar, text="刷新", command=self.reload_records).pack(side=RIGHT)
        self.records_tree = ttk.Treeview(
            records_box,
            columns=("time", "plate", "operator", "work_no", "assistant", "assistant_no", "note"),
            show="headings",
        )
        headings = {
            "time": "时间",
            "plate": "水冷基板条码",
            "operator": "作业人员",
            "work_no": "工号",
            "assistant": "协作人员",
            "assistant_no": "协作工号",
            "note": "备注",
        }
        for key, text in headings.items():
            self.records_tree.heading(key, text=text)
            self.records_tree.column(key, width=120, anchor="center")
        self.records_tree.column("time", width=170)
        self.records_tree.column("plate", width=280)
        self.records_tree.column("note", width=260, anchor="w")
        self.records_tree.pack(fill=BOTH, expand=True)

    def save_record(self) -> None:
        try:
            record = self.record_service.record_scan(
                self.plate_var.get(),
                self.user,
                self.assistant["work_no"] if self.assistant else "",
                self.note_var.get(),
            )
        except Exception as exc:
            self.status_var.set(str(exc))
            self.play_sound("error")
            self.add_log("ERROR", str(exc), "error")
            messagebox.showerror("记录失败", str(exc), parent=self)
            self.after(100, self.focus_scanner)
            return
        self.status_var.set(f"已记录：{record['plate_sn']}，{record['recorded_at']}")
        self.play_sound("success")
        self.add_log("SUCCESS", f"录入条码: {record['plate_sn']}", "ok")
        self.plate_var.set("")
        self.note_var.set("")
        self.reload_records()
        self.after(100, self.focus_scanner)

    def reload_records(self) -> None:
        self.records_tree.delete(*self.records_tree.get_children())
        rows = (
            self.record_service.records_between(date.today().isoformat(), date.today().isoformat())
            if self.today_var.get()
            else self.record_service.recent_records()
        )
        for row in rows:
            self.records_tree.insert(
                "",
                END,
                iid=str(row["id"]),
                values=(
                    row["recorded_at"],
                    row["plate_sn"],
                    row["operator_name"],
                    row["operator_work_no"],
                    row["assistant_name"] or "",
                    row["assistant_work_no"] or "",
                    row["note"] or "",
                ),
            )

    def open_user_dialog(self) -> None:
        UserDialog(self, self.user_service)

    def open_export_dialog(self) -> None:
        CoatingExportDialog(self, self.report_service, self.config.report_dir)

    def open_settings_dialog(self) -> None:
        CoatingSettingsDialog(self, self.config)

    def focus_scanner(self) -> None:
        focus_scanner_entry(self.plate_entry)

    def add_log(self, level: str, message: str, tag: str) -> None:
        ts = time.strftime("%H:%M:%S")
        self.log_text.insert("1.0", f"[{ts}] {level:<7} {message}\n", tag)

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

    def logout(self) -> None:
        self.destroy()
        self.parent.deiconify()

    def close(self) -> None:
        self.destroy()
        self.parent.close()


class CoatingExportDialog(ttk.Toplevel):
    def __init__(
        self,
        parent,
        report_service: CoatingReportService,
        default_report_dir: str,
    ) -> None:
        super().__init__(parent)
        self.report_service = report_service
        self.title("手动导出涂敷记录")
        self.geometry("640x280")
        self.minsize(560, 240)
        self.transient(parent)
        self.grab_set()

        root = ttk.Frame(self, padding=14)
        root.pack(fill=BOTH, expand=True)
        root.columnconfigure(1, weight=1)

        today = date.today().isoformat()
        self.start_var = ttk.StringVar(value=today)
        self.end_var = ttk.StringVar(value=today)
        self.output_var = ttk.StringVar(value=default_report_dir)

        ttk.Label(root, text="开始日期").grid(row=0, column=0, sticky="w", pady=6)
        ttk.Entry(root, textvariable=self.start_var).grid(row=0, column=1, sticky="ew", pady=6)
        ttk.Label(root, text="结束日期").grid(row=1, column=0, sticky="w", pady=6)
        ttk.Entry(root, textvariable=self.end_var).grid(row=1, column=1, sticky="ew", pady=6)
        ttk.Label(root, text="导出目录").grid(row=2, column=0, sticky="w", pady=6)
        ttk.Entry(root, textvariable=self.output_var).grid(row=2, column=1, sticky="ew", pady=6)
        ttk.Button(root, text="选择", command=self.choose_dir).grid(row=2, column=2, padx=8)

        buttons = ttk.Frame(root)
        buttons.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(18, 0))
        ttk.Button(buttons, text="导出", bootstyle="primary", command=self.export).pack(side=RIGHT)
        ttk.Button(buttons, text="关闭", command=self.destroy).pack(side=RIGHT, padx=8)

    def choose_dir(self) -> None:
        path = filedialog.askdirectory(parent=self)
        if path:
            self.output_var.set(path)

    def export(self) -> None:
        try:
            out_file = self.report_service.export_records(
                self.output_var.get().strip(),
                self.start_var.get().strip() or None,
                self.end_var.get().strip() or None,
            )
        except Exception as exc:
            messagebox.showerror("导出失败", str(exc), parent=self)
            return
        messagebox.showinfo("导出完成", f"已生成：\n{out_file}", parent=self)


class CoatingSettingsDialog(ttk.Toplevel):
    SOUND_OPTIONS = {
        "系统默认": 0,
        "严重停止": 16,
        "询问提示": 32,
        "感叹警告": 48,
        "信息提示": 64,
        "普通蜂鸣": -1,
    }

    def __init__(self, parent, config: CoatingConfig) -> None:
        super().__init__(parent)
        self.config = config
        self.title("涂敷记录设置")
        self.geometry("700x360")
        self.minsize(620, 320)
        self.transient(parent)
        self.grab_set()

        root = ttk.Frame(self, padding=14)
        root.pack(fill=BOTH, expand=True)
        root.columnconfigure(1, weight=1)

        self.report_dir_var = ttk.StringVar(value=config.report_dir)
        self.success_sound_var = ttk.StringVar(value=self._label_for(config.sound_success))
        self.error_sound_var = ttk.StringVar(value=self._label_for(config.sound_error))
        self.sound_count_var = ttk.StringVar(value=str(config.sound_count))
        self.sound_interval_var = ttk.StringVar(value=str(config.sound_interval))

        ttk.Label(root, text="默认导出目录").grid(row=0, column=0, sticky="w", pady=6)
        ttk.Entry(root, textvariable=self.report_dir_var).grid(row=0, column=1, sticky="ew", pady=6)
        ttk.Button(root, text="选择", command=self.choose_dir).grid(row=0, column=2, padx=8)

        ttk.Label(root, text="成功提示音").grid(row=1, column=0, sticky="w", pady=6)
        ttk.Combobox(
            root,
            textvariable=self.success_sound_var,
            values=list(self.SOUND_OPTIONS.keys()),
            state="readonly",
        ).grid(row=1, column=1, sticky="ew", pady=6)

        ttk.Label(root, text="错误提示音").grid(row=2, column=0, sticky="w", pady=6)
        ttk.Combobox(
            root,
            textvariable=self.error_sound_var,
            values=list(self.SOUND_OPTIONS.keys()),
            state="readonly",
        ).grid(row=2, column=1, sticky="ew", pady=6)

        ttk.Label(root, text="错误音重复次数").grid(row=3, column=0, sticky="w", pady=6)
        ttk.Entry(root, textvariable=self.sound_count_var, width=10).grid(
            row=3, column=1, sticky="w", pady=6
        )

        ttk.Label(root, text="播放间隔(秒)").grid(row=4, column=0, sticky="w", pady=6)
        ttk.Entry(root, textvariable=self.sound_interval_var, width=10).grid(
            row=4, column=1, sticky="w", pady=6
        )

        buttons = ttk.Frame(root)
        buttons.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(18, 0))
        ttk.Button(buttons, text="保存", bootstyle="success", command=self.save).pack(side=RIGHT)
        ttk.Button(buttons, text="关闭", command=self.destroy).pack(side=RIGHT, padx=8)

    def _label_for(self, value: int) -> str:
        for label, option_value in self.SOUND_OPTIONS.items():
            if option_value == value:
                return label
        return "系统默认"

    def choose_dir(self) -> None:
        path = filedialog.askdirectory(parent=self)
        if path:
            self.report_dir_var.set(path)

    def save(self) -> None:
        try:
            self.config.report_dir = self.report_dir_var.get().strip() or "reports"
            self.config.sound_success = self.SOUND_OPTIONS[self.success_sound_var.get()]
            self.config.sound_error = self.SOUND_OPTIONS[self.error_sound_var.get()]
            self.config.sound_count = max(1, int(self.sound_count_var.get().strip()))
            self.config.sound_interval = max(0.0, float(self.sound_interval_var.get().strip()))
            self.config.save()
        except Exception as exc:
            messagebox.showerror("保存失败", str(exc), parent=self)
            return
        messagebox.showinfo("保存成功", "设置已保存", parent=self)
