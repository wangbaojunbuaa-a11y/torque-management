from __future__ import annotations

from datetime import date
import tkinter as tk
from tkinter import filedialog, messagebox

import ttkbootstrap as ttk
from ttkbootstrap.constants import BOTH, END, LEFT, RIGHT, X

from app.config.app_config import AppConfig
from app.services.report_service import ReportService
from app.services.tightening_service import TighteningService
from app.ui.date_widgets import create_date_picker, date_value


class TorqueHistoryDialog(ttk.Toplevel):
    def __init__(
        self,
        parent,
        tightening_service: TighteningService,
        report_service: ReportService,
        config: AppConfig,
    ) -> None:
        super().__init__(parent)
        self.tightening_service = tightening_service
        self.report_service = report_service
        self.config = config
        self.rows = []
        self.title("拧紧历史查询")
        self.geometry("1260x760")
        self.minsize(1040, 640)
        self.transient(parent)

        root = ttk.Frame(self, padding=12)
        root.pack(fill=BOTH, expand=True)

        filters = ttk.Labelframe(root, text="查询条件", padding=10)
        filters.pack(fill=X)
        for col in (1, 3, 5, 7):
            filters.columnconfigure(col, weight=1)

        today = date.today().isoformat()
        self.base_var = ttk.StringVar()
        self.igbt_var = ttk.StringVar()
        self.person_var = ttk.StringVar()
        self.start_var = ttk.StringVar(value=today)
        self.end_var = ttk.StringVar(value=today)
        self.product_var = ttk.StringVar()
        fields = [
            ("水冷基板条码", self.base_var),
            ("IGBT条码", self.igbt_var),
            ("人员姓名/工号", self.person_var),
            ("开始日期", self.start_var),
            ("结束日期", self.end_var),
            ("型号/产品", self.product_var),
        ]
        for index, (label, var) in enumerate(fields):
            row = index // 4
            col = (index % 4) * 2
            ttk.Label(filters, text=label).grid(row=row, column=col, sticky="w", padx=(0, 6), pady=4)
            if label in {"开始日期", "结束日期"}:
                create_date_picker(filters, var).grid(row=row, column=col + 1, sticky="ew", padx=(0, 12), pady=4)
            else:
                ttk.Entry(filters, textvariable=var).grid(row=row, column=col + 1, sticky="ew", padx=(0, 12), pady=4)

        buttons = ttk.Frame(filters)
        buttons.grid(row=1, column=4, columnspan=4, sticky="e", pady=4)
        ttk.Button(buttons, text="查询", bootstyle="primary", command=self.search).pack(side=LEFT, padx=(0, 8))
        ttk.Button(buttons, text="导出结果", command=self.export).pack(side=LEFT)

        body = ttk.Frame(root)
        body.pack(fill=BOTH, expand=True, pady=(10, 0))
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(0, weight=1)

        self.tree = ttk.Treeview(
            body,
            columns=("time", "base", "product", "round", "seq", "set", "actual", "angle", "operator", "result"),
            show="headings",
        )
        headings = {
            "time": "拧紧时间",
            "base": "水冷基板条码",
            "product": "产品",
            "round": "轮次",
            "seq": "序号",
            "set": "目标扭矩",
            "actual": "实际扭矩",
            "angle": "角度",
            "operator": "人员",
            "result": "结果",
        }
        for key, text in headings.items():
            self.tree.heading(key, text=text)
            self.tree.column(key, width=100, anchor="center")
        self.tree.column("time", width=170)
        self.tree.column("base", width=220)
        self.tree.column("product", width=200, anchor="w")
        self.tree.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self.tree.bind("<<TreeviewSelect>>", self.show_detail)

        detail = ttk.Labelframe(body, text="详细信息", padding=8)
        detail.grid(row=0, column=1, sticky="nsew")
        detail.columnconfigure(0, weight=1)
        detail.rowconfigure(0, weight=1)
        self.detail_text = tk.Text(detail, wrap="word", font=("Consolas", 12))
        self.detail_text.grid(row=0, column=0, sticky="nsew")

        self.search()

    def search(self) -> None:
        self.rows = self.tightening_service.search_history(
            self.base_var.get(),
            self.igbt_var.get(),
            self.person_var.get(),
            date_value(self.start_var) or None,
            date_value(self.end_var) or None,
            self.product_var.get(),
        )
        self.tree.delete(*self.tree.get_children())
        for row in self.rows:
            self.tree.insert(
                "",
                END,
                iid=str(row["id"]),
                values=(
                    row["tightened_at"],
                    row["base_barcode"],
                    f"{row['product_code']} - {row['product_name']}",
                    row["round_no"],
                    row["sequence_no"],
                    row["set_torque"],
                    row["actual_torque"],
                    row["actual_angle"],
                    row["operator_name"],
                    row["result"],
                ),
            )

    def show_detail(self, _event=None) -> None:
        selected = self.tree.selection()
        self.detail_text.delete("1.0", END)
        if not selected:
            return
        record_id = int(selected[0])
        row = next((item for item in self.rows if int(item["id"]) == record_id), None)
        if not row:
            return
        lines = [
            f"水冷基板条码: {row['base_barcode']}",
            f"产品: {row['product_code']} - {row['product_name']}",
            f"轮次/序号: 第{row['round_no']}轮 / {row['sequence_no']}",
            f"程序号: {row['program_no']}",
            f"目标扭矩: {row['set_torque']}",
            f"实际扭矩: {row['actual_torque']}",
            f"实际角度: {row['actual_angle']}",
            f"结果: {row['result']}",
            f"拧紧时间: {row['tightened_at']}",
            f"作业人员: {row['operator_name']} ({row['operator_work_no']})",
            f"工件状态: {row['workpiece_status']}",
            f"第二次完成时间: {row['round2_completed_at'] or '-'}",
            f"第三次完成时间: {row['round3_completed_at'] or '-'}",
        ]
        self.detail_text.insert("1.0", "\n".join(lines))

    def export(self) -> None:
        if not self.rows:
            messagebox.showwarning("提示", "没有可导出的查询结果", parent=self)
            return
        output_dir = filedialog.askdirectory(parent=self, initialdir=self.config.report_dir)
        if not output_dir:
            return
        try:
            out_file = self.report_service.export_history_rows(self.rows, output_dir)
        except Exception as exc:
            messagebox.showerror("导出失败", str(exc), parent=self)
            return
        messagebox.showinfo("导出完成", f"已生成：\n{out_file}", parent=self)
