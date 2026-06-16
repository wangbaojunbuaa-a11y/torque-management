import ttkbootstrap as ttk
from ttkbootstrap.constants import BOTH, LEFT, RIGHT, X
from tkinter import filedialog, messagebox

from app.config.app_config import AppConfig
from app.services.product_service import ProductService
from app.services.report_service import ReportService


class ReportDialog(ttk.Toplevel):
    def __init__(
        self,
        parent,
        product_service: ProductService,
        report_service: ReportService,
        config: AppConfig,
    ) -> None:
        super().__init__(parent)
        self.product_service = product_service
        self.report_service = report_service
        self.config = config
        self.product_by_label = {}

        self.title("报表生成")
        self.geometry("820x330")
        self.resizable(True, False)

        root = ttk.Frame(self, padding=18)
        root.pack(fill=BOTH, expand=True)

        ttk.Label(root, text="按产品导出拧紧记录.xlsx", font=("Microsoft YaHei UI", 15, "bold")).pack(
            anchor="w", pady=(0, 16)
        )

        row1 = ttk.Frame(root)
        row1.pack(fill=X, pady=(0, 12))
        ttk.Label(row1, text="产品").pack(side=LEFT)
        self.product_var = ttk.StringVar()
        self.product_combo = ttk.Combobox(row1, textvariable=self.product_var, state="readonly")
        self.product_combo.pack(side=LEFT, padx=(8, 0), fill=X, expand=True)

        row2 = ttk.Frame(root)
        row2.pack(fill=X, pady=(0, 16))
        ttk.Label(row2, text="目录").pack(side=LEFT)
        self.output_dir_var = ttk.StringVar(value=config.report_dir)
        ttk.Entry(row2, textvariable=self.output_dir_var).pack(side=LEFT, padx=(8, 8), fill=X, expand=True)
        ttk.Button(row2, text="选择", command=self.choose_dir).pack(side=LEFT)

        self.status_var = ttk.StringVar(value="报表列包含：序号、目标扭矩、拧紧扭矩、角度、时间、工号")
        ttk.Label(root, textvariable=self.status_var, bootstyle="secondary").pack(anchor="w")

        buttons = ttk.Frame(root)
        buttons.pack(fill=X, pady=(18, 0))
        ttk.Button(buttons, text="生成报表", bootstyle="primary", command=self.export).pack(side=LEFT)
        ttk.Button(buttons, text="关闭", command=self.destroy).pack(side=RIGHT)

        self.reload_products()

    def reload_products(self) -> None:
        labels = []
        for row in self.product_service.list_active():
            label = f"{row['code']} - {row['name']}"
            labels.append(label)
            self.product_by_label[label] = row
        self.product_combo["values"] = labels
        if labels:
            self.product_var.set(labels[0])

    def choose_dir(self) -> None:
        directory = filedialog.askdirectory(initialdir=self.output_dir_var.get() or ".")
        if directory:
            self.output_dir_var.set(directory)

    def export(self) -> None:
        product = self.product_by_label.get(self.product_var.get())
        if not product:
            messagebox.showwarning("未选择产品", "请选择产品")
            return
        try:
            out_file = self.report_service.export_product_report(
                int(product["id"]), self.output_dir_var.get()
            )
        except Exception as exc:
            messagebox.showerror("导出失败", str(exc))
            return
        self.status_var.set(f"已生成：{out_file}")
        messagebox.showinfo("导出成功", out_file)
