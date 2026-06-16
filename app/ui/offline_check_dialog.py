import tkinter as tk
from datetime import datetime
import ttkbootstrap as ttk
from ttkbootstrap.constants import BOTH, LEFT, RIGHT, X

from app.ui.input_helpers import focus_scanner_entry, switch_to_english_input
from app.services.offline_check_service import OfflineCheckService


class OfflineCheckDialog(ttk.Toplevel):
    def __init__(self, parent, offline_check_service: OfflineCheckService) -> None:
        super().__init__(parent)
        self.offline_check_service = offline_check_service

        self.title("下线检查")
        self.geometry("900x520")
        self.minsize(760, 420)

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
        self.bind("<FocusIn>", lambda _event: self.after(50, self.focus_scanner))

        self.result_var = ttk.StringVar(value="请扫描水冷基板条码")
        ttk.Label(root, textvariable=self.result_var, font=("Microsoft YaHei UI", 18, "bold")).pack(
            anchor="w", pady=(18, 10)
        )

        content = ttk.Frame(root)
        content.pack(fill=BOTH, expand=True)

        passed_box = ttk.Labelframe(content, text="已下线产品水冷基板条码", padding=8)
        passed_box.pack(side=LEFT, fill=BOTH, expand=True, padx=(0, 8))
        self.passed_tree = ttk.Treeview(
            passed_box,
            columns=("time", "barcode", "product"),
            show="headings",
            height=12,
        )
        for key, text in {"time": "时间", "barcode": "水冷基板条码", "product": "产品"}.items():
            self.passed_tree.heading(key, text=text)
            self.passed_tree.column(key, width=120, anchor="center")
        self.passed_tree.column("barcode", width=220)
        self.passed_tree.pack(fill=BOTH, expand=True)

        rejected_box = ttk.Labelframe(content, text="禁止下线产品信息", padding=8)
        rejected_box.pack(side=RIGHT, fill=BOTH, expand=True, padx=(8, 0))
        self.reject_text = tk.Text(rejected_box, height=12)
        self.reject_text.pack(fill=BOTH, expand=True)
        self.focus_scanner()

    def focus_scanner(self) -> None:
        focus_scanner_entry(self.barcode_entry)

    def check(self) -> None:
        switch_to_english_input()
        barcode = self.barcode_var.get().strip()
        self.reject_text.delete("1.0", "end")
        try:
            result = self.offline_check_service.check_barcode(barcode)
        except Exception as exc:
            self.result_var.set("检查失败")
            self.reject_text.insert("end", f"条码：{barcode}\n错误：{exc}")
            self.focus_scanner()
            return

        if result["ok"]:
            self.result_var.set("允许下线")
            workpiece = result["workpiece"]
            now_text = datetime.now().strftime("%H:%M:%S")
            self.passed_tree.insert(
                "",
                "end",
                values=(
                    now_text,
                    workpiece["base_barcode"],
                    f"{workpiece['product_code']} - {workpiece['product_name']}",
                ),
            )
            self.reject_text.insert(
                "end",
                f"{result['message']}\n\n"
                f"水冷基板条码：{workpiece['base_barcode']}\n"
                f"产品：{workpiece['product_code']} - {workpiece['product_name']}\n"
                f"第二次OK：{result['round2_ok']}/{result['expected']}\n"
                f"第三次OK：{result['round3_ok']}/{result['expected']}\n",
            )
        else:
            self.result_var.set("禁止下线")
            workpiece = result.get("workpiece")
            display_barcode = result.get("barcode") or barcode
            self.reject_text.insert("end", f"水冷基板条码：{display_barcode}\n")
            if workpiece:
                self.reject_text.insert(
                    "end",
                    f"产品：{workpiece['product_code']} - {workpiece['product_name']}\n",
                )
            self.reject_text.insert("end", f"原因：{result['message']}")
        self.barcode_var.set("")
        self.focus_scanner()
