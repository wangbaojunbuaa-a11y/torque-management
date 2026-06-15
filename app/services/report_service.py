import os
from datetime import datetime

from app.repositories.sqlite_repo import SQLiteRepository


class ReportService:
    def __init__(self, repo: SQLiteRepository) -> None:
        self.repo = repo

    def export_product_report(self, product_id: int, output_dir: str) -> str:
        product = self.repo.fetch_one("SELECT * FROM product_types WHERE id = ?", (product_id,))
        if product is None:
            raise ValueError("产品不存在")

        rows = self.repo.fetch_all(
            """
            SELECT
                w.base_barcode,
                p.code AS product_code,
                p.name AS product_name,
                r.round_no,
                r.sequence_no,
                r.set_torque,
                r.actual_torque,
                r.actual_angle,
                r.tightened_at,
                r.operator_work_no,
                r.result
            FROM tightening_records r
            JOIN workpieces w ON w.id = r.workpiece_id
            JOIN product_types p ON p.id = w.product_type_id
            WHERE p.id = ?
            ORDER BY w.base_barcode, r.round_no, r.sequence_no, r.tightened_at
            """,
            (product_id,),
        )
        if not rows:
            raise ValueError("该产品暂无拧紧记录")

        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font

        os.makedirs(output_dir, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_code = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in product["code"])
        out_file = os.path.join(output_dir, f"{safe_code}_torque_report_{stamp}.xlsx")

        wb = Workbook()
        ws = wb.active
        ws.title = "拧紧记录"
        headers = [
            "水冷基板条码",
            "产品编码",
            "产品名称",
            "轮次",
            "序号",
            "目标扭矩",
            "拧紧扭矩",
            "拧紧角度",
            "拧紧时间",
            "作业人员工号",
            "结果",
        ]
        ws.append(headers)
        for cell in ws[1]:
            cell.font = Font(bold=True)
            cell.alignment = Alignment(horizontal="center")

        for row in rows:
            ws.append(
                [
                    row["base_barcode"],
                    row["product_code"],
                    row["product_name"],
                    row["round_no"],
                    row["sequence_no"],
                    row["set_torque"],
                    row["actual_torque"],
                    row["actual_angle"],
                    row["tightened_at"],
                    row["operator_work_no"],
                    row["result"],
                ]
            )

        widths = [24, 16, 22, 8, 8, 12, 12, 12, 22, 16, 8]
        for index, width in enumerate(widths, start=1):
            ws.column_dimensions[chr(64 + index)].width = width

        wb.save(out_file)
        return out_file
