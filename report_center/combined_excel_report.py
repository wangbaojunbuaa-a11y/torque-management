from __future__ import annotations

from datetime import datetime
import os

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from report_center.excel_report import safe_filename
from report_center.models import CoatingRecordSummary, WorkpieceSummary


def split_product_serial(product_serial_no: str) -> tuple[str, str]:
    parts = product_serial_no.split("%")
    material_no = parts[1] if len(parts) > 2 else ""
    serial_no = parts[2] if len(parts) > 3 else product_serial_no.rstrip("%")
    return material_no, serial_no


class CombinedExcelReportWriter:
    def write(
        self,
        staging_report_dir: str,
        coating: CoatingRecordSummary,
        workpiece: WorkpieceSummary,
        product_serial_no: str,
    ) -> str:
        os.makedirs(staging_report_dir, exist_ok=True)
        out_path = os.path.join(
            staging_report_dir,
            f"{safe_filename(product_serial_no.rstrip('%'))}-涂敷拧紧记录表.xlsx",
        )

        wb = Workbook()
        coating_ws = wb.active
        coating_ws.title = "涂敷记录表"
        torque_ws = wb.create_sheet("拧紧记录表")

        self._write_coating_sheet(coating_ws, coating, product_serial_no)
        self._write_torque_sheet(torque_ws, workpiece, product_serial_no)

        wb.save(out_path)
        return out_path

    def _write_coating_sheet(
        self,
        ws,
        record: CoatingRecordSummary,
        product_serial_no: str,
    ) -> None:
        material_no, serial_no = split_product_serial(product_serial_no)
        ws.merge_cells("A1:H1")
        ws["A1"] = "涂敷记录表"
        self._title(ws["A1"])

        rows = [
            ("物料号", material_no, "序列号", serial_no),
            ("水冷基板条码", record.plate_sn, "作业人员", record.operator_name),
            ("协作人员", record.assistant_name, "涂敷/记录时间", record.recorded_at),
            ("导热硅脂已搅拌", "√", "硅脂批次号", self._value(record, "grease_batch_no")),
            ("硅脂启封日期", self._value(record, "grease_open_date"), "涂敷方式", self._value(record, "coating_method") or "机器涂敷/工装涂敷"),
        ]
        self._write_info_rows(ws, rows, start_row=3)
        self._format_sheet(ws)
        self._set_widths(ws, [18, 26, 18, 26, 18, 18, 18, 18])

    def _write_torque_sheet(
        self,
        ws,
        workpiece: WorkpieceSummary,
        product_serial_no: str,
    ) -> None:
        material_no, serial_no = split_product_serial(product_serial_no)
        ws.merge_cells("A1:H1")
        ws["A1"] = "拧紧记录表"
        self._title(ws["A1"])

        rows = [
            ("产品物料号", material_no, "产品序列号", serial_no),
            ("水冷基板条码", workpiece.base_barcode, "静置时间", self._rest_time(workpiece)),
            ("第1拧紧方式", "机械扭矩螺丝刀拧紧", "第1轮拧紧扭矩", "0.5Nm"),
            ("第一轮拧紧人员", self._first_round_operator(workpiece), "报表生成时间", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        ]
        self._write_info_rows(ws, rows, start_row=3)

        table_row = 10
        headers = [
            "序号",
            "轮次",
            "程序号",
            "目标扭矩",
            "拧紧扭矩",
            "拧紧角度",
            "拧紧时间",
            "作业人员姓名",
        ]
        for col, header in enumerate(headers, start=1):
            cell = ws.cell(table_row, col, header)
            self._header(cell, "4472C4")

        for index, record in enumerate(workpiece.records, start=1):
            row_no = table_row + index
            values = [
                record.sequence_no,
                f"第{record.round_no}次",
                record.program_no,
                record.set_torque,
                record.actual_torque,
                record.actual_angle,
                record.tightened_at,
                record.operator_name,
            ]
            for col, value in enumerate(values, start=1):
                ws.cell(row_no, col, value)

        self._format_sheet(ws)
        self._set_widths(ws, [10, 10, 10, 12, 12, 12, 22, 18])
        for col in ("D", "E", "F"):
            for cell in ws[col]:
                if isinstance(cell.value, (int, float)):
                    cell.number_format = "0.000"
        ws.freeze_panes = "A11"
        ws.auto_filter.ref = f"A10:H{max(10, ws.max_row)}"

    def _write_info_rows(self, ws, rows: list[tuple[object, object, object, object]], start_row: int) -> None:
        for offset, row in enumerate(rows):
            excel_row = start_row + offset
            ws.cell(excel_row, 1, row[0])
            ws.cell(excel_row, 2, row[1])
            ws.cell(excel_row, 4, row[2])
            ws.cell(excel_row, 5, row[3])
            ws.merge_cells(start_row=excel_row, start_column=2, end_row=excel_row, end_column=3)
            ws.merge_cells(start_row=excel_row, start_column=5, end_row=excel_row, end_column=8)
            for col in (1, 4):
                ws.cell(excel_row, col).font = Font(name="Microsoft YaHei", bold=True)

    def _rest_time(self, workpiece: WorkpieceSummary) -> str:
        if not workpiece.round2_completed_at or not workpiece.round3_completed_at:
            return ""
        try:
            start = datetime.fromisoformat(str(workpiece.round2_completed_at).replace(" ", "T"))
            end = datetime.fromisoformat(str(workpiece.round3_completed_at).replace(" ", "T"))
        except ValueError:
            return ""
        minutes = max(0, int((end - start).total_seconds() // 60))
        hours, remainder = divmod(minutes, 60)
        if hours:
            return f"{hours}小时{remainder}分钟"
        return f"{remainder}分钟"

    def _first_round_operator(self, workpiece: WorkpieceSummary) -> str:
        for record in workpiece.records:
            if record.round_no == 2 and record.operator_name:
                return record.operator_name
        for record in workpiece.records:
            if record.operator_name:
                return record.operator_name
        return ""

    def _value(self, record: CoatingRecordSummary, attr: str) -> str:
        return str(getattr(record, attr, "") or "")

    def _title(self, cell) -> None:
        cell.font = Font(name="Microsoft YaHei", size=16, bold=True)
        cell.alignment = Alignment(horizontal="center", vertical="center")

    def _header(self, cell, color: str) -> None:
        cell.font = Font(name="Microsoft YaHei", bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor=color)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    def _format_sheet(self, ws) -> None:
        thin = Side(style="thin", color="D9E2F3")
        border = Border(left=thin, right=thin, top=thin, bottom=thin)
        for row in ws.iter_rows():
            for cell in row:
                cell.font = cell.font.copy(name="Microsoft YaHei")
                cell.alignment = Alignment(
                    horizontal=cell.alignment.horizontal or "center",
                    vertical="center",
                    wrap_text=True,
                )
                cell.border = border
        for row in range(1, ws.max_row + 1):
            ws.row_dimensions[row].height = 24
        ws.row_dimensions[1].height = 30

    def _set_widths(self, ws, widths: list[int]) -> None:
        for index, width in enumerate(widths, start=1):
            ws.column_dimensions[get_column_letter(index)].width = width
