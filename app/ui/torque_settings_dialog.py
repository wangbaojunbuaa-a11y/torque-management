from __future__ import annotations

from tkinter import filedialog, messagebox

import ttkbootstrap as ttk
from ttkbootstrap.constants import BOTH, RIGHT

from app.config.app_config import AppConfig


class TorqueSettingsDialog(ttk.Toplevel):
    SOUND_OPTIONS = {
        "系统默认": 0,
        "严重停止": 16,
        "询问提示": 32,
        "感叹警告": 48,
        "信息提示": 64,
        "普通蜂鸣": -1,
    }

    def __init__(self, parent, config: AppConfig) -> None:
        super().__init__(parent)
        self.config = config
        self.title("扭矩管理设置")
        self.geometry("760x430")
        self.minsize(660, 360)
        self.transient(parent)
        self.grab_set()

        root = ttk.Frame(self, padding=14)
        root.pack(fill=BOTH, expand=True)
        root.columnconfigure(1, weight=1)

        self.report_dir_var = ttk.StringVar(value=config.report_dir)
        self.offline_warning_sound_var = ttk.StringVar(value=config.offline_warning_sound)
        self.success_sound_var = ttk.StringVar(value=self._label_for(config.sound_success))
        self.error_sound_var = ttk.StringVar(value=self._label_for(config.sound_error))
        self.sound_count_var = ttk.StringVar(value=str(config.sound_count))
        self.sound_interval_var = ttk.StringVar(value=str(config.sound_interval))

        ttk.Label(root, text="默认报表目录").grid(row=0, column=0, sticky="w", pady=6)
        ttk.Entry(root, textvariable=self.report_dir_var).grid(row=0, column=1, sticky="ew", pady=6)
        ttk.Button(root, text="选择", command=self.choose_report_dir).grid(row=0, column=2, padx=8)

        ttk.Label(root, text="下线禁用语音文件").grid(row=1, column=0, sticky="w", pady=6)
        ttk.Entry(root, textvariable=self.offline_warning_sound_var).grid(row=1, column=1, sticky="ew", pady=6)
        ttk.Button(root, text="选择", command=self.choose_warning_sound).grid(row=1, column=2, padx=8)

        ttk.Label(root, text="成功提示音").grid(row=2, column=0, sticky="w", pady=6)
        ttk.Combobox(
            root,
            textvariable=self.success_sound_var,
            values=list(self.SOUND_OPTIONS.keys()),
            state="readonly",
        ).grid(row=2, column=1, sticky="ew", pady=6)

        ttk.Label(root, text="错误提示音").grid(row=3, column=0, sticky="w", pady=6)
        ttk.Combobox(
            root,
            textvariable=self.error_sound_var,
            values=list(self.SOUND_OPTIONS.keys()),
            state="readonly",
        ).grid(row=3, column=1, sticky="ew", pady=6)

        ttk.Label(root, text="错误音重复次数").grid(row=4, column=0, sticky="w", pady=6)
        ttk.Entry(root, textvariable=self.sound_count_var, width=10).grid(
            row=4, column=1, sticky="w", pady=6
        )

        ttk.Label(root, text="播放间隔(秒)").grid(row=5, column=0, sticky="w", pady=6)
        ttk.Entry(root, textvariable=self.sound_interval_var, width=10).grid(
            row=5, column=1, sticky="w", pady=6
        )

        buttons = ttk.Frame(root)
        buttons.grid(row=6, column=0, columnspan=3, sticky="ew", pady=(18, 0))
        ttk.Button(buttons, text="保存", bootstyle="success", command=self.save).pack(side=RIGHT)
        ttk.Button(buttons, text="关闭", command=self.destroy).pack(side=RIGHT, padx=8)

    def _label_for(self, value: int) -> str:
        for label, option_value in self.SOUND_OPTIONS.items():
            if option_value == value:
                return label
        return "系统默认"

    def choose_report_dir(self) -> None:
        path = filedialog.askdirectory(parent=self)
        if path:
            self.report_dir_var.set(path)

    def choose_warning_sound(self) -> None:
        path = filedialog.askopenfilename(
            parent=self,
            title="选择语音提示文件",
            filetypes=[("Wave 文件", "*.wav"), ("所有文件", "*.*")],
        )
        if path:
            self.offline_warning_sound_var.set(path)

    def save(self) -> None:
        try:
            self.config.report_dir = self.report_dir_var.get().strip() or "reports"
            self.config.offline_warning_sound = self.offline_warning_sound_var.get().strip()
            self.config.sound_success = self.SOUND_OPTIONS[self.success_sound_var.get()]
            self.config.sound_error = self.SOUND_OPTIONS[self.error_sound_var.get()]
            self.config.sound_count = max(1, int(self.sound_count_var.get().strip()))
            self.config.sound_interval = max(0.0, float(self.sound_interval_var.get().strip()))
            self.config.save()
        except Exception as exc:
            messagebox.showerror("保存失败", str(exc), parent=self)
            return
        messagebox.showinfo("保存成功", "设置已保存", parent=self)
