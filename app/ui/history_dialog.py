from __future__ import annotations

from datetime import date
import tkinter as tk
from tkinter import filedialog, messagebox

import ttkbootstrap as ttk
from ttkbootstrap.constants import BOTH, END, LEFT, X

from app.config.app_config import AppConfig
from app.services.report_service import ReportService
from app.services.tightening_service import TighteningService
from app.ui.date_widgets import create_date_picker, date_value
from app.ui.scroll_helpers import grid_text_with_scrollbar, grid_tree_with_scrollbar


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

        tree_frame = ttk.Frame(body)
        tree_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(
            tree_frame,
            columns=("last_time", "base", "product", "status", "round2", "round3", "attempts", "operator"),
            show="headings",
        )
        headings = {
            "last_time": "最近拧紧时间",
            "base": "水冷基板条码",
            "product": "产品",
            "status": "状态",
            "round2": "第二轮OK",
            "round3": "第三轮OK",
            "attempts": "总记录数",
            "operator": "人员",
        }
        for key, text in headings.items():
            self.tree.heading(key, text=text)
            self.tree.column(key, width=100, anchor="center")
        self.tree.column("last_time", width=170)
        self.tree.column("base", width=220)
        self.tree.column("product", width=200, anchor="w")
        self.tree.column("operator", width=180, anchor="w")
        grid_tree_with_scrollbar(self.tree)
        self.tree.bind("<<TreeviewSelect>>", self.show_detail)

        detail = ttk.Labelframe(body, text="详细信息", padding=8)
        detail.grid(row=0, column=1, sticky="nsew")
        detail.columnconfigure(0, weight=1)
        detail.rowconfigure(0, weight=1)
        self.detail_text = tk.Text(detail, wrap="word", font=("Consolas", 12))
        grid_text_with_scrollbar(self.detail_text)

        self.search()

    def search(self) -> None:
        self.rows = self.tightening_service.search_workpiece_history(
            self.base_var.get(),
            self.igbt_var.get(),
            self.person_var.get(),
            date_value(self.start_var) or None,
            date_value(self.end_var) or None,
            self.product_var.get(),
        )
        self.tree.delete(*self.tree.get_children())
        for row in self.rows:
            expected = int(row["igbt_count"]) * int(row["screws_per_igbt"])
            self.tree.insert(
                "",
                END,
                iid=str(row["id"]),
                values=(
                    row["last_tightened_at"] or row["updated_at"],
                    row["base_barcode"],
                    f"{row['product_code']} - {row['product_name']}",
                    row["workpiece_status"],
                    f"{row['round2_ok'] or 0}/{expected}",
                    f"{row['round3_ok'] or 0}/{expected}",
                    row["total_attempts"] or 0,
                    row["operator_names"] or "",
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
        expected = int(row["igbt_count"]) * int(row["screws_per_igbt"])
        detail_rows = self.tightening_service.history_records_for_workpieces([record_id])
        lines = [
            f"水冷基板条码: {row['base_barcode']}",
            f"产品: {row['product_code']} - {row['product_name']}",
            f"工件状态: {row['workpiece_status']}",
            f"预计每轮OK数量: {expected}",
            f"第二轮OK: {row['round2_ok'] or 0}/{expected}",
            f"第三轮OK: {row['round3_ok'] or 0}/{expected}",
            f"第二次完成时间: {row['round2_completed_at'] or '-'}",
            f"第三次完成时间: {row['round3_completed_at'] or '-'}",
            "",
            "拧紧明细:",
        ]
        if not detail_rows:
            lines.append("无拧紧记录")
        for item in detail_rows:
            lines.append(
                "第{round_no}轮 #{sequence_no}  程序{program_no}  "
                "目标{set_torque}  实际{actual_torque}  角度{actual_angle}  "
                "{result}  {tightened_at}  {operator_name}({operator_work_no})".format(
                    round_no=item["round_no"],
                    sequence_no=item["sequence_no"],
                    program_no=item["program_no"],
                    set_torque=item["set_torque"],
                    actual_torque=item["actual_torque"],
                    actual_angle=item["actual_angle"],
                    result=item["result"],
                    tightened_at=item["tightened_at"],
                    operator_name=item["operator_name"],
                    operator_work_no=item["operator_work_no"],
                )
            )
        self.detail_text.insert("1.0", "\n".join(lines))

    def export(self) -> None:
        if not self.rows:
            messagebox.showwarning("提示", "没有可导出的查询结果", parent=self)
            return
        output_dir = filedialog.askdirectory(parent=self, initialdir=self.config.report_dir)
        if not output_dir:
            return
        try:
            workpiece_ids = [int(row["id"]) for row in self.rows]
            detail_rows = self.tightening_service.history_records_for_workpieces(workpiece_ids)
            if not detail_rows:
                messagebox.showwarning("提示", "查询结果没有可导出的拧紧明细", parent=self)
                return
            out_file = self.report_service.export_history_rows(detail_rows, output_dir)
        except Exception as exc:
            messagebox.showerror("导出失败", str(exc), parent=self)
            return
        messagebox.showinfo("导出完成", f"已生成：\n{out_file}", parent=self)
