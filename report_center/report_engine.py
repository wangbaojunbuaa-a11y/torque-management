from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import os

from report_center.archive import ReportArchiver
from report_center.coating_reader import CoatingDataReader
from report_center.combined_excel_report import CombinedExcelReportWriter
from report_center.config import ReportCenterConfig
from report_center.mes_client import MesClient
from report_center.models import CoatingRecordSummary, MesPart, MesProduct, ReportResult, WorkpieceSummary
from report_center.network_paths import NetworkPathReconnector
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


@dataclass(frozen=True)
class MatchAllSummary:
    total: int
    generated_reports: int
    skipped: int
    errors: list[str]
    generated: list[ReportResult]


class ReportPrerequisiteMissing(Exception):
    def __init__(self, status: str, message: str) -> None:
        super().__init__(message)
        self.status = status


class ReportEngine:
    def __init__(
        self,
        config: ReportCenterConfig,
        state_repo: ReportStateRepository,
    ) -> None:
        self.config = config
        self.state_repo = state_repo
        self.reader = TorqueDataReader()
        self.coating_reader = CoatingDataReader()
        self.writer = CombinedExcelReportWriter()
        self.archiver = ReportArchiver()
        self.reconnector = NetworkPathReconnector(
            config.network_reconnect_enabled,
            config.network_reconnect_interval_seconds,
        )

    def poll_once(self) -> PollSummary:
        self.state_repo.initialize()
        errors: list[str] = []
        generated: list[ReportResult] = []
        completed_count = 0
        matched_count = 0
        errors.extend(self.reconnector.ensure_paths(self._network_paths()))
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
            torque_result = self._process_torque_line(line, product_index)
            completed_count += torque_result[0]
            matched_count += torque_result[1]
            archived_count += torque_result[2]
            generated.extend(torque_result[3])
            errors.extend(torque_result[4])

            coating_result = self._process_coating_line(line, product_index)
            completed_count += coating_result[0]
            matched_count += coating_result[1]
            archived_count += coating_result[2]
            generated.extend(coating_result[3])
            errors.extend(coating_result[4])

        return PollSummary(
            scanned_lines=len(enabled_lines),
            completed_workpieces=completed_count,
            matched_workpieces=matched_count,
            generated_reports=len(generated),
            archived_reports=archived_count,
            errors=errors,
            generated=generated,
        )

    def diagnose_job(self, job_id: int, product_serial_no: str | None = None) -> str:
        job = self.state_repo.job_by_id(job_id)
        if not job:
            return "任务不存在，可能已经被删除。"

        report_type = str(job["report_type"])
        line_code = str(job["line_code"])
        barcode = str(job["base_barcode"])
        lines = [
            "任务信息",
            f"  类型: {self._report_type_label(report_type)}",
            f"  产线: {line_code}",
            f"  水冷基板条码: {barcode}",
            f"  产品序列号: {job['product_serial_no'] or '-'}",
            f"  状态: {job['status']}",
            f"  报表路径: {job['report_path'] or '-'}",
            f"  错误: {job['last_error'] or '-'}",
            f"  更新时间: {job['updated_at']}",
            "",
        ]

        generated = self.state_repo.generated_by_job(report_type, line_code, barcode)
        if not generated and report_type != "combined":
            generated = self.state_repo.generated_by_job("combined", line_code, barcode)
        lines.append("已生成记录")
        if generated:
            lines.extend(
                [
                    f"  产品序列号: {generated['product_serial_no']}",
                    f"  报表路径: {generated['report_path']}",
                    f"  生成时间: {generated['generated_at']}",
                ]
            )
        else:
            lines.append("  未找到同条码已生成记录")
        lines.append("")

        line = self._line_by_code(line_code)
        lines.append("本地数据源")
        if not line:
            lines.append("  未在配置中找到该产线")
        elif report_type == "coating":
            lines.append(f"  涂敷库: {line.coating_db_path or '-'}")
            record = self._find_coating_record(line, barcode)
            if record:
                lines.extend(
                    [
                        "  本地涂敷记录: 已找到",
                        f"  记录ID: {record.record_id}",
                        f"  涂敷时间: {record.recorded_at}",
                        f"  作业人员: {record.operator_name} ({record.operator_work_no})",
                    ]
                )
            else:
                lines.append("  本地涂敷记录: 未找到，或数据库不可读")
        elif report_type == "combined":
            lines.append(f"  涂敷库: {line.coating_db_path or '-'}")
            record = self._find_coating_record(line, barcode)
            lines.append(f"  本地涂敷记录: {'已找到' if record else '未找到，或数据库不可读'}")
            lines.append(f"  拧紧库: {line.db_path or '-'}")
            workpiece = self._find_workpiece(line, barcode)
            lines.append(f"  本地拧紧记录: {'已找到且第二/三次OK数量满足' if workpiece else '未找到，或未满足第二/三次OK数量'}")
        else:
            lines.append(f"  拧紧库: {line.db_path or '-'}")
            workpiece = self._find_workpiece(line, barcode)
            if workpiece:
                lines.extend(
                    [
                        "  本地拧紧记录: 已找到且第二/三次OK数量满足",
                        f"  工件ID: {workpiece.workpiece_id}",
                        f"  产品类型: {workpiece.product_code} {workpiece.product_name}",
                        f"  要求OK数量/轮: {workpiece.expected_count}",
                        f"  第二次OK/完成时间: {workpiece.round2_ok} / {workpiece.round2_completed_at or '-'}",
                        f"  第三次OK/完成时间: {workpiece.round3_ok} / {workpiece.round3_completed_at or '-'}",
                    ]
                )
            else:
                lines.append("  本地拧紧记录: 未找到，或未满足第二/三次OK数量")
        lines.append("")

        lines.append("MES匹配")
        try:
            products = MesClient(self.config.mes).load_recent_products()
            product_index = self._index_products(products)
            exact_matches = [
                product.serial_number
                for product in products
                for part in product.parts
                if part.barcode == barcode
            ]
            case_matches = [
                product.serial_number
                for product in products
                for part in product.parts
                if part.barcode and part.barcode.lower() == barcode.lower() and part.barcode != barcode
            ]
            active_match = self._match_product(product_index, barcode)
            lines.extend(
                [
                    f"  MES启用: {'是' if self.config.mes.enabled else '否'}",
                    f"  模拟模式: {'是' if self.config.mes.mock else '否'}",
                    f"  追溯天数: {self.config.mes.lookback_days}",
                    f"  近期完成产品数: {len(products)}",
                    f"  精确条码匹配: {', '.join(exact_matches[:5]) if exact_matches else '无'}",
                    f"  大小写兼容匹配: {', '.join(case_matches[:5]) if case_matches else '无'}",
                    f"  当前引擎匹配结果: {active_match[0] if active_match else '无'}",
                ]
            )
            serial_to_check = (product_serial_no or "").strip() or (str(job["product_serial_no"]) if job["product_serial_no"] else "")
            if serial_to_check:
                product = self._load_product_by_serial(serial_to_check)
                lines.append(f"  按输入序列号直接查询MES: {'已找到' if product else '未找到'}")
                if product:
                    lines.append(f"  MES实际序列号: {product.serial_number}")
                    lines.append(f"  MES完成时间: {product.finished_time or '-'}")
                    lines.append(f"  MES零件数量: {len(product.parts)}")
        except Exception as exc:
            lines.append(f"  MES查询失败: {exc}")
        return "\n".join(lines)

    def manual_generate(self, job_id: int, product_serial_no: str) -> ReportResult:
        product_serial_no = product_serial_no.strip()
        if not product_serial_no:
            raise ValueError("请输入产品序列号")

        job = self.state_repo.job_by_id(job_id)
        if not job:
            raise ValueError("任务不存在，可能已经被删除")

        report_type = str(job["report_type"])
        line_code = str(job["line_code"])
        barcode = str(job["base_barcode"])
        line = self._line_by_code(line_code)
        if not line:
            raise ValueError(f"未在配置中找到产线: {line_code}")

        product = self._load_product_by_serial(product_serial_no)
        if not product:
            raise ValueError(f"MES数据库中未找到产品序列号: {product_serial_no}")
        serial_number = product.serial_number
        igbt_parts = self._igbt_parts(product)
        if self.state_repo.has_generated(serial_number, report_type="combined"):
            raise ValueError(f"该产品序列号已经生成过涂敷拧紧记录表: {serial_number}")

        return self._generate_for_job(report_type, line, barcode, serial_number, igbt_parts)

    def match_waiting_jobs(self) -> MatchAllSummary:
        self.state_repo.initialize()
        jobs = self.state_repo.waiting_jobs()
        if not jobs:
            return MatchAllSummary(0, 0, 0, [], [])

        products = MesClient(self.config.mes).load_recent_products()
        product_index = self._index_products(products)
        generated: list[ReportResult] = []
        errors: list[str] = []
        skipped = 0

        for job in jobs:
            report_type = str(job["report_type"])
            line_code = str(job["line_code"])
            barcode = str(job["base_barcode"])
            try:
                line = self._line_by_code(line_code)
                if not line:
                    raise ValueError(f"未在配置中找到产线: {line_code}")
                match = self._match_product(product_index, barcode)
                if not match:
                    skipped += 1
                    continue
                serial_number, igbt_parts = match
                if self.state_repo.has_generated(serial_number, report_type="combined"):
                    report = self.state_repo.report_by_serial(serial_number, report_type="combined")
                    self.state_repo.mark_status(
                        line_code,
                        barcode,
                        "已归档" if report and report["report_path"] and not self._is_in_staging(str(report["report_path"])) else "已生成/待归档",
                        product_serial_no=serial_number,
                        report_path=report["report_path"] if report else None,
                        report_type=report_type,
                    )
                    skipped += 1
                    continue
                generated.append(self._generate_for_job(report_type, line, barcode, serial_number, igbt_parts))
            except ReportPrerequisiteMissing as exc:
                skipped += 1
                self.state_repo.mark_status(
                    line_code,
                    barcode,
                    exc.status,
                    last_error=str(exc),
                    report_type=report_type,
                )
            except Exception as exc:
                errors.append(f"{line_code} {barcode}: {exc}")
                self.state_repo.mark_status(
                    line_code,
                    barcode,
                    "生成失败",
                    last_error=str(exc),
                    report_type=report_type,
                )

        return MatchAllSummary(
            total=len(jobs),
            generated_reports=len(generated),
            skipped=skipped,
            errors=errors,
            generated=generated,
        )

    def _generate_for_job(
        self,
        report_type: str,
        line,
        barcode: str,
        serial_number: str,
        igbt_parts: list[MesPart],
    ) -> ReportResult:
        record = self._find_coating_record(line, barcode)
        if not record:
            raise ReportPrerequisiteMissing("等待涂敷记录", f"本地涂敷库未找到水冷基板条码: {barcode}")
        workpiece = self._find_workpiece(line, barcode)
        if not workpiece:
            raise ReportPrerequisiteMissing("等待拧紧记录", f"本地拧紧库未找到已完成且OK数量满足的水冷基板条码: {barcode}")

        report_path = self.writer.write(
            self.config.staging_report_dir,
            record,
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
            line.code,
            barcode,
            final_path,
            status,
            report_type="combined",
        )
        self.state_repo.mark_status(line.code, barcode, status, serial_number, final_path, report_type="torque")
        self.state_repo.mark_status(line.code, barcode, status, serial_number, final_path, report_type="coating")
        return ReportResult(
            line_code=line.code,
            base_barcode=barcode,
            product_serial_no=serial_number,
            report_path=final_path,
        )

    def _process_torque_line(
        self,
        line,
        product_index: dict[str, tuple[str, list[MesPart]]],
    ) -> tuple[int, int, int, list[ReportResult], list[str]]:
        if not line.db_path:
            return 0, 0, 0, [], []
        errors: list[str] = []
        generated: list[ReportResult] = []
        matched_count = 0
        archived_count = 0
        try:
            workpieces = self.reader.read_completed_workpieces(
                line,
                copy_before_read=self.config.copy_before_read,
            )
        except Exception as exc:
            message = f"{line.code} 拧紧库读取失败: {exc}"
            errors.append(message)
            self.state_repo.mark_status(line.code, "-", "读取失败", last_error=str(exc), report_type="torque")
            return 0, 0, 0, [], errors

        for workpiece in workpieces:
            try:
                result = self._process_workpiece(workpiece, product_index)
                if result:
                    generated.append(result)
                    matched_count += 1
                    if not self._is_in_staging(result.report_path):
                        archived_count += 1
                else:
                    serial = (self._match_product(product_index, workpiece.base_barcode) or (None, []))[0]
                    if serial:
                        matched_count += 1
            except ReportPrerequisiteMissing as exc:
                self.state_repo.mark_status(
                    line.code,
                    workpiece.base_barcode,
                    exc.status,
                    last_error=str(exc),
                    report_type="torque",
                )
            except Exception as exc:
                errors.append(f"{line.code} 拧紧 {workpiece.base_barcode}: {exc}")
                self.state_repo.mark_status(
                    line.code,
                    workpiece.base_barcode,
                    "生成失败",
                    last_error=str(exc),
                    report_type="torque",
                )
        return len(workpieces), matched_count, archived_count, generated, errors

    def _process_coating_line(
        self,
        line,
        product_index: dict[str, tuple[str, list[MesPart]]],
    ) -> tuple[int, int, int, list[ReportResult], list[str]]:
        if not line.coating_db_path:
            return 0, 0, 0, [], []
        errors: list[str] = []
        generated: list[ReportResult] = []
        matched_count = 0
        archived_count = 0
        try:
            records = self.coating_reader.read_records(
                line,
                copy_before_read=self.config.copy_before_read,
            )
        except Exception as exc:
            message = f"{line.code} 涂敷库读取失败: {exc}"
            errors.append(message)
            self.state_repo.mark_status(line.code, "-", "读取失败", last_error=str(exc), report_type="coating")
            return 0, 0, 0, [], errors

        for record in records:
            try:
                result = self._process_coating_record(record, product_index)
                if result:
                    generated.append(result)
                    matched_count += 1
                    if not self._is_in_staging(result.report_path):
                        archived_count += 1
                else:
                    serial = (self._match_product(product_index, record.plate_sn) or (None, []))[0]
                    if serial:
                        matched_count += 1
            except ReportPrerequisiteMissing as exc:
                self.state_repo.mark_status(
                    record.line_code,
                    record.plate_sn,
                    exc.status,
                    last_error=str(exc),
                    report_type="coating",
                )
            except Exception as exc:
                errors.append(f"{record.line_code} 涂敷 {record.plate_sn}: {exc}")
                self.state_repo.mark_status(
                    record.line_code,
                    record.plate_sn,
                    "生成失败",
                    last_error=str(exc),
                    report_type="coating",
                )
        return len(records), matched_count, archived_count, generated, errors

    def _process_workpiece(
        self,
        workpiece: WorkpieceSummary,
        product_index: dict[str, tuple[str, list[MesPart]]],
    ) -> ReportResult | None:
        match = self._match_product(product_index, workpiece.base_barcode)
        if not match:
            generated = self.state_repo.generated_by_job("combined", workpiece.line_code, workpiece.base_barcode)
            if generated:
                self.state_repo.mark_status(
                    workpiece.line_code,
                    workpiece.base_barcode,
                    "已归档" if generated["report_path"] and not self._is_in_staging(str(generated["report_path"])) else "已生成/待归档",
                    product_serial_no=generated["product_serial_no"],
                    report_path=generated["report_path"],
                    report_type="torque",
                )
                return None
            self.state_repo.mark_status(
                workpiece.line_code,
                workpiece.base_barcode,
                "等待MES匹配",
                report_type="torque",
            )
            return None

        serial_number, igbt_parts = match
        if self.state_repo.has_generated(serial_number, report_type="combined"):
            report = self.state_repo.report_by_serial(serial_number, report_type="combined")
            status = "已生成/待归档"
            report_path = report["report_path"] if report else None
            if report_path and self._is_in_staging(str(report_path)):
                try:
                    archived_path = self.archiver.archive_file(str(report_path), self.config.report_dir)
                    if archived_path:
                        report_path = archived_path
                        status = "已归档"
                        self.state_repo.update_report_path_by_serial(
                            serial_number,
                            archived_path,
                            "已归档",
                            report_type="combined",
                        )
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
                report_type="torque",
            )
            return None

        line = self._line_by_code(workpiece.line_code)
        if not line:
            raise ValueError(f"未在配置中找到产线: {workpiece.line_code}")
        return self._generate_for_job("torque", line, workpiece.base_barcode, serial_number, igbt_parts)

    def _process_coating_record(
        self,
        record: CoatingRecordSummary,
        product_index: dict[str, tuple[str, list[MesPart]]],
    ) -> ReportResult | None:
        match = self._match_product(product_index, record.plate_sn)
        if not match:
            generated = self.state_repo.generated_by_job("combined", record.line_code, record.plate_sn)
            if generated:
                self.state_repo.mark_status(
                    record.line_code,
                    record.plate_sn,
                    "已归档" if generated["report_path"] and not self._is_in_staging(str(generated["report_path"])) else "已生成/待归档",
                    product_serial_no=generated["product_serial_no"],
                    report_path=generated["report_path"],
                    report_type="coating",
                )
                return None
            self.state_repo.mark_status(
                record.line_code,
                record.plate_sn,
                "等待MES匹配",
                report_type="coating",
            )
            return None

        serial_number, igbt_parts = match
        if self.state_repo.has_generated(serial_number, report_type="combined"):
            report = self.state_repo.report_by_serial(serial_number, report_type="combined")
            status = "已生成/待归档"
            report_path = report["report_path"] if report else None
            if report_path and self._is_in_staging(str(report_path)):
                try:
                    archived_path = self.archiver.archive_file(str(report_path), self.config.report_dir)
                    if archived_path:
                        report_path = archived_path
                        status = "已归档"
                        self.state_repo.update_report_path_by_serial(
                            serial_number,
                            archived_path,
                            "已归档",
                            report_type="combined",
                        )
                except Exception:
                    pass
            elif report_path:
                status = "已归档"
            self.state_repo.mark_status(
                record.line_code,
                record.plate_sn,
                status,
                product_serial_no=serial_number,
                report_path=report_path,
                report_type="coating",
            )
            return None

        line = self._line_by_code(record.line_code)
        if not line:
            raise ValueError(f"未在配置中找到产线: {record.line_code}")
        return self._generate_for_job("coating", line, record.plate_sn, serial_number, igbt_parts)

    def _index_products(
        self,
        products: list[MesProduct],
    ) -> dict[str, tuple[str, list[MesPart]]]:
        index: dict[str, tuple[str, list[MesPart]]] = {}
        exact_keys: set[str] = set()
        rules = [rule.strip() for rule in self.config.mes.igbt_filter_rules if rule.strip()]
        for product in products:
            igbt_parts = self._igbt_parts(product, rules)
            for part in product.parts:
                value = str(part.barcode or "").strip()
                if not value:
                    continue
                if value not in exact_keys:
                    index[value] = (product.serial_number, igbt_parts)
                    exact_keys.add(value)
                for key in self._barcode_keys(value)[1:]:
                    if key not in exact_keys:
                        index.setdefault(key, (product.serial_number, igbt_parts))
        return index

    def _match_product(
        self,
        product_index: dict[str, tuple[str, list[MesPart]]],
        barcode: str,
    ) -> tuple[str, list[MesPart]] | None:
        for key in self._barcode_keys(barcode):
            match = product_index.get(key)
            if match:
                return match
        return None

    def _barcode_keys(self, barcode: str) -> list[str]:
        value = str(barcode or "").strip()
        if not value:
            return []
        keys = [value, value.upper(), value.lower()]
        deduped: list[str] = []
        for key in keys:
            if key and key not in deduped:
                deduped.append(key)
        return deduped

    def _igbt_parts(self, product: MesProduct, rules: list[str] | None = None) -> list[MesPart]:
        active_rules = rules
        if active_rules is None:
            active_rules = [rule.strip() for rule in self.config.mes.igbt_filter_rules if rule.strip()]
        return [
            part for part in product.parts if any(part.code.startswith(rule) for rule in active_rules)
        ]

    def _product_by_serial(self, products: list[MesProduct], product_serial_no: str) -> MesProduct | None:
        target = product_serial_no.strip()
        target_trimmed = target.rstrip("%")
        for product in products:
            serial = product.serial_number.strip()
            if serial == target or serial.rstrip("%") == target_trimmed:
                return product
        return None

    def _load_product_by_serial(self, product_serial_no: str) -> MesProduct | None:
        return MesClient(self.config.mes).load_product_by_serial(product_serial_no)

    def _report_type_label(self, report_type: str) -> str:
        if report_type == "coating":
            return "涂敷"
        if report_type == "combined":
            return "合并"
        return "拧紧"

    def _line_by_code(self, line_code: str):
        for line in self.config.lines:
            if line.code == line_code:
                return line
        return None

    def _find_workpiece(self, line, base_barcode: str) -> WorkpieceSummary | None:
        if not line.db_path:
            return None
        workpieces = self.reader.read_completed_workpieces(
            line,
            copy_before_read=self.config.copy_before_read,
        )
        target = base_barcode.strip().lower()
        for workpiece in workpieces:
            if workpiece.base_barcode.strip().lower() == target:
                return workpiece
        return None

    def _find_coating_record(self, line, plate_sn: str) -> CoatingRecordSummary | None:
        if not line.coating_db_path:
            return None
        records = self.coating_reader.read_records(
            line,
            copy_before_read=self.config.copy_before_read,
        )
        target = plate_sn.strip().lower()
        for record in records:
            if record.plate_sn.strip().lower() == target:
                return record
        return None

    def _is_in_staging(self, report_path: str) -> bool:
        try:
            staging = os.path.abspath(self.config.staging_report_dir)
            path = os.path.abspath(report_path)
            return os.path.commonpath([staging, path]) == staging
        except ValueError:
            return False

    def _network_paths(self) -> list[str]:
        paths = [self.config.report_dir, self.config.staging_report_dir]
        for line in self.config.lines:
            if line.enabled:
                paths.extend([line.db_path, line.coating_db_path])
        return paths


def format_poll_summary(summary: PollSummary) -> str:
    now = datetime.now().strftime("%H:%M:%S")
    return (
        f"{now} 产线 {summary.scanned_lines} 条，已完成记录 {summary.completed_workpieces} 个，"
        f"MES匹配 {summary.matched_workpieces} 个，新生成 {summary.generated_reports} 份，"
        f"归档 {summary.archived_reports} 份"
    )
