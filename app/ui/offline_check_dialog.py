import tkinter as tk
import ttkbootstrap as ttk
from ttkbootstrap.constants import BOTH, LEFT, X

from app.services.offline_check_service import OfflineCheckService


class OfflineCheckDialog(ttk.Toplevel):
    def __init__(self, parent, offline_check_service: OfflineCheckService) -> None:
        super().__init__(parent)
        self.offline_check_service = offline_check_service

        self.title("下线检查")
        self.geometry("760x420")
        self.minsize(680, 360)

        root = ttk.Frame(self, padding=16)
        root.pack(fill=BOTH, expand=True)

        scan = ttk.Labelframe(root, text="扫描水冷基板条码", padding=10)
        scan.pack(fill=X)
        self.barcode_var = ttk.StringVar()
        entry = ttk.Entry(scan, textvariable=self.barcode_var, font=("Microsoft YaHei UI", 14))
        entry.pack(side=LEFT, fill=X, expand=True, padx=(0, 8))
        entry.bind("<Return>", lambda _event: self.check())
        ttk.Button(scan, text="检查", bootstyle="primary", command=self.check).pack(side=LEFT)

        self.result_var = ttk.StringVar(value="请扫描水冷基板条码")
        ttk.Label(root, textvariable=self.result_var, font=("Microsoft YaHei UI", 18, "bold")).pack(
            anchor="w", pady=(18, 10)
        )

        self.detail_text = tk.Text(root, height=10)
        self.detail_text.pack(fill=BOTH, expand=True)
        entry.focus_set()

    def check(self) -> None:
        self.detail_text.delete("1.0", "end")
        try:
            result = self.offline_check_service.check_barcode(self.barcode_var.get())
        except Exception as exc:
            self.result_var.set("检查失败")
            self.detail_text.insert("end", str(exc))
            return

        if result["ok"]:
            self.result_var.set("允许下线")
            workpiece = result["workpiece"]
            self.detail_text.insert(
                "end",
                f"{result['message']}\n"
                f"条码：{workpiece['base_barcode']}\n"
                f"产品：{workpiece['product_code']} - {workpiece['product_name']}\n"
                f"第二次OK：{result['round2_ok']}/{result['expected']}\n"
                f"第三次OK：{result['round3_ok']}/{result['expected']}\n",
            )
        else:
            self.result_var.set("禁止下线")
            self.detail_text.insert("end", result["message"])
        self.barcode_var.set("")
