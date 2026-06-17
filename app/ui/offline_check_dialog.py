from datetime import datetime
import os
import time
import ttkbootstrap as ttk
from ttkbootstrap.constants import BOTH, LEFT, RIGHT, X

from app.config.app_config import AppConfig
from app.ui.input_helpers import focus_scanner_entry, switch_to_english_input
from app.services.offline_check_service import OfflineCheckService


class OfflineCheckDialog(ttk.Toplevel):
    def __init__(
        self,
        parent,
        offline_check_service: OfflineCheckService,
        config: AppConfig,
    ) -> None:
        super().__init__(parent)
        self.offline_check_service = offline_check_service
        self.config = config

        self.title("下线检查")
        self.geometry("1200x680")
        self.minsize(980, 560)

        root = ttk.Frame(self, padding=16)
        root.pack(fill=BOTH, expand=True)

        scan = ttk.Labelframe(root, text="扫描水冷基板条码", padding=10)
        scan.pack(fill=X)
        self.barcode_var = ttk.StringVar()
        self.barcode_entry = ttk.Entry(scan, textvariable=self.barcode_var, font=("Microsoft YaHei UI", 14))
        self.barcode_entry.pack(side=LEFT, fill=X, expand=True, padx=(0, 8))
        self.barcode_entry.bind("<FocusIn>", lambda _event: switch_to_english_input())
        self.barcode_entry.bind("<Return>", lambda _event: self.check())
        ttk.Button(scan, text="检查", bootstyle="primary", command=self.check).pack(side=LEFT)

        self.result_var = ttk.StringVar(value="请扫描水冷基板条码")
        self.result_label = ttk.Label(
            root,
            textvariable=self.result_var,
            font=("Microsoft YaHei UI", 18, "bold"),
            bootstyle="secondary",
        )
        self.result_label.pack(
            anchor="w", pady=(18, 10)
        )

        content = ttk.Frame(root)
        content.pack(fill=BOTH, expand=True)

        passed_box = ttk.Labelframe(content, text="允许下线产品信息", padding=8)
        passed_box.pack(side=LEFT, fill=BOTH, expand=True, padx=(0, 8))
        self.passed_tree = ttk.Treeview(
            passed_box,
            columns=("time", "barcode", "product", "progress"),
            show="headings",
            height=12,
        )
        for key, text in {
            "time": "时间",
            "barcode": "水冷基板条码",
            "product": "产品",
            "progress": "OK数量",
        }.items():
            self.passed_tree.heading(key, text=text)
            self.passed_tree.column(key, width=120, anchor="center")
        self.passed_tree.column("barcode", width=220)
        self.passed_tree.column("product", width=180)
        self.passed_tree.column("progress", width=150)
        self.passed_tree.tag_configure("ok", foreground="#198754")
        self.passed_tree.pack(fill=BOTH, expand=True)

        rejected_box = ttk.Labelframe(content, text="禁止下线产品信息", padding=8)
        rejected_box.pack(side=RIGHT, fill=BOTH, expand=True, padx=(8, 0))
        self.rejected_tree = ttk.Treeview(
            rejected_box,
            columns=("time", "barcode", "product", "reason"),
            show="headings",
            height=12,
        )
        for key, text in {
            "time": "时间",
            "barcode": "水冷基板条码",
            "product": "产品",
            "reason": "原因",
        }.items():
            self.rejected_tree.heading(key, text=text)
            self.rejected_tree.column(key, width=120, anchor="center")
        self.rejected_tree.column("barcode", width=220)
        self.rejected_tree.column("product", width=180)
        self.rejected_tree.column("reason", width=260, anchor="w")
        self.rejected_tree.tag_configure("reject", foreground="#dc3545")
        self.rejected_tree.pack(fill=BOTH, expand=True)
        self.focus_scanner()

    def focus_scanner(self) -> None:
        focus_scanner_entry(self.barcode_entry)

    def check(self) -> None:
        switch_to_english_input()
        barcode = self.barcode_var.get().strip()
        now_text = datetime.now().strftime("%H:%M:%S")
        try:
            result = self.offline_check_service.check_barcode(barcode)
        except Exception as exc:
            self.result_var.set("检查失败")
            self.result_label.configure(bootstyle="danger")
            self.play_sound("error")
            self.rejected_tree.insert(
                "",
                "end",
                tags=("reject",),
                values=(now_text, barcode, "-", str(exc)),
            )
            self.focus_scanner()
            return

        if result["ok"]:
            self.result_var.set("允许下线")
            self.result_label.configure(bootstyle="success")
            self.play_sound("success")
            workpiece = result["workpiece"]
            self.passed_tree.insert(
                "",
                "end",
                tags=("ok",),
                values=(
                    now_text,
                    workpiece["base_barcode"],
                    f"{workpiece['product_code']} - {workpiece['product_name']}",
                    f"二次 {result['round2_ok']}/{result['expected']}  三次 {result['round3_ok']}/{result['expected']}",
                ),
            )
        else:
            self.result_var.set("禁止下线")
            self.result_label.configure(bootstyle="danger")
            self.play_sound("error", prefer_warning_file=True)
            workpiece = result.get("workpiece")
            display_barcode = result.get("barcode") or barcode
            product_text = "-"
            if workpiece:
                product_text = f"{workpiece['product_code']} - {workpiece['product_name']}"
            self.rejected_tree.insert(
                "",
                "end",
                tags=("reject",),
                values=(now_text, display_barcode, product_text, result["message"]),
            )
        self.barcode_var.set("")
        self.focus_scanner()

    def play_sound(self, sound_type: str, prefer_warning_file: bool = False) -> None:
        try:
            import winsound
        except Exception:
            return
        if (
            prefer_warning_file
            and self.config.offline_warning_sound
            and os.path.exists(self.config.offline_warning_sound)
        ):
            try:
                winsound.PlaySound(
                    self.config.offline_warning_sound,
                    winsound.SND_FILENAME | winsound.SND_ASYNC,
                )
                return
            except Exception:
                pass
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
