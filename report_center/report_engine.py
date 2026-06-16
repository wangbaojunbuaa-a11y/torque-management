from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import os

from report_center.archive import ReportArchiver
from report_center.config import ReportCenterConfig
from report_center.excel_report import ExcelReportWriter
from report_center.mes_client import MesClient
from report_center.models import MesPart, MesProduct, ReportResult, WorkpieceSummary
from report_center.state_repo import ReportStateRepository
from report_center.torque_reader import TorqueDataReader


@dataclass(frozen=True)
class PollSummary:
    scanned_lines: int
    completed_workpieces: int
    matched_workpieces: int
    generated_reports: int
    archived_reports: int
    errors: list[str]
    generated: list[ReportResult]


class ReportEngine:
    def __init__(
        self,
        config: ReportCenterConfig,
        state_repo: ReportStateRepository,
    ) -> None:
        self.config = config
        self.state_repo = state_repo
        self.reader = TorqueDataReader()
        self.writer = ExcelReportWriter()
        self.archiver = ReportArchiver()

    def poll_once(self) -> PollSummary:
        self.state_repo.initialize()
        errors: list[str] = []
        generated: list[ReportResult] = []
        completed_count = 0
        matched_count = 0
        archived_count, archive_errors = self.archiver.archive_pending(
            self.config.staging_report_dir,
            self.config.report_dir,
            self.state_repo,
        )
        errors.extend(archive_errors)

        products = MesClient(self.config.mes).load_recent_products()
        product_index = self._index_products(products)

        enabled_lines = [line for line in self.config.lines if line.enabled]
        for line in enabled_lines:
            try:
                workpieces = self.reader.read_completed_workpieces(
                    line,
                    copy_before_read=self.config.copy_before_read,
                )
            except Exception as exc:
                message = f"{line.code} 读取失败: {exc}"
                errors.append(message)
                self.state_repo.mark_status(line.code, "-", "读取失败", last_error=str(exc))
                continue

            completed_count += len(workpieces)
            for workpiece in workpieces:
                try:
                    result = self._process_workpiece(workpiece, product_index)
                    if result:
                        generated.append(result)
                        matched_count += 1
                        if not self._is_in_staging(result.report_path):
                            archived_count += 1
                    else:
                        serial = product_index.get(workpiece.base_barcode, (None, []))[0]
                        if serial:
                            matched_count += 1
                except Exception as exc:
                    errors.append(f"{line.code} {workpiece.base_barcode}: {exc}")
                    self.state_repo.mark_status(
                        line.code,
                        workpiece.base_barcode,
                        "生成失败",
                        last_error=str(exc),
                    )

        return PollSummary(
            scanned_lines=len(enabled_lines),
            completed_workpieces=completed_count,
            matched_workpieces=matched_count,
            generated_reports=len(generated),
            archived_reports=archived_count,
            errors=errors,
            generated=generated,
        )

    def _process_workpiece(
        self,
        workpiece: WorkpieceSummary,
        product_index: dict[str, tuple[str, list[MesPart]]],
    ) -> ReportResult | None:
        match = product_index.get(workpiece.base_barcode)
        if not match:
            self.state_repo.mark_status(
                workpiece.line_code,
                workpiece.base_barcode,
                "等待MES匹配",
            )
            return None

        serial_number, igbt_parts = match
        if self.state_repo.has_generated(serial_number):
            report = self.state_repo.report_by_serial(serial_number)
            status = "已生成/待归档"
            report_path = report["report_path"] if report else None
            if report_path and self._is_in_staging(str(report_path)):
                try:
                    archived_path = self.archiver.archive_file(str(report_path), self.config.report_dir)
                    if archived_path:
                        report_path = archived_path
                        status = "已归档"
                        self.state_repo.update_report_path_by_serial(serial_number, archived_path, "已归档")
                except Exception:
                    pass
            elif report_path:
                status = "已归档"
            self.state_repo.mark_status(
                workpiece.line_code,
                workpiece.base_barcode,
                status,
                product_serial_no=serial_number,
                report_path=report_path,
            )
            return None

        report_path = self.writer.write(
            self.config.staging_report_dir,
            workpiece,
            serial_number,
            igbt_parts,
        )
        status = "已生成/待归档"
        final_path = report_path
        try:
            archived_path = self.archiver.archive_file(report_path, self.config.report_dir)
            if archived_path:
                status = "已归档"
                final_path = archived_path
        except Exception:
            pass
        self.state_repo.mark_generated(
            serial_number,
            workpiece.line_code,
            workpiece.base_barcode,
            final_path,
            status,
        )
        return ReportResult(
            line_code=workpiece.line_code,
            base_barcode=workpiece.base_barcode,
            product_serial_no=serial_number,
            report_path=final_path,
        )

    def _index_products(
        self,
        products: list[MesProduct],
    ) -> dict[str, tuple[str, list[MesPart]]]:
        index: dict[str, tuple[str, list[MesPart]]] = {}
        rules = [rule.strip() for rule in self.config.mes.igbt_filter_rules if rule.strip()]
        for product in products:
            igbt_parts = [
                part for part in product.parts if any(part.code.startswith(rule) for rule in rules)
            ]
            for part in product.parts:
                if part.barcode and part.barcode not in index:
                    index[part.barcode] = (product.serial_number, igbt_parts)
        return index

    def _is_in_staging(self, report_path: str) -> bool:
        try:
            staging = os.path.abspath(self.config.staging_report_dir)
            path = os.path.abspath(report_path)
            return os.path.commonpath([staging, path]) == staging
        except ValueError:
            return False


def format_poll_summary(summary: PollSummary) -> str:
    now = datetime.now().strftime("%H:%M:%S")
    return (
        f"{now} 产线 {summary.scanned_lines} 条，完成工件 {summary.completed_workpieces} 个，"
        f"MES匹配 {summary.matched_workpieces} 个，新生成 {summary.generated_reports} 份，"
        f"归档 {summary.archived_reports} 份"
    )
