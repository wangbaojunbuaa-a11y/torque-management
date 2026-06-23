from __future__ import annotations

import os
import shutil

from report_center.state_repo import ReportStateRepository


def extract_order_from_report_name(filename: str) -> str:
    stem = filename.rsplit(".", 1)[0]
    serial = stem.split("-", 1)[0]
    return serial.split("%")[-1] if "%" in serial else ""


def extract_serial_from_report_name(filename: str) -> str:
    stem = filename.rsplit(".", 1)[0]
    return stem.split("-", 1)[0]


def report_type_from_name(filename: str) -> str:
    if "涂敷拧紧" in filename:
        return "combined"
    return "coating" if "涂敷" in filename else "torque"


class ReportArchiver:
    def archive_file(self, file_path: str, target_root: str) -> str | None:
        filename = os.path.basename(file_path)
        order = extract_order_from_report_name(filename)
        if not order:
            return None
        if not os.path.exists(target_root):
            raise FileNotFoundError(f"归档根目录不可达: {target_root}")

        for entry in os.scandir(target_root):
            if entry.is_dir() and order in entry.name:
                target_path = os.path.join(entry.path, filename)
                if os.path.abspath(file_path) == os.path.abspath(target_path):
                    return target_path
                shutil.move(file_path, target_path)
                return target_path
        return None

    def archive_pending(
        self,
        staging_report_dir: str,
        target_root: str,
        state_repo: ReportStateRepository,
    ) -> tuple[int, list[str]]:
        if not os.path.exists(staging_report_dir):
            return 0, []

        moved = 0
        errors: list[str] = []
        for filename in os.listdir(staging_report_dir):
            if not filename.endswith(".xlsx") or "-" not in filename:
                continue
            source_path = os.path.join(staging_report_dir, filename)
            if not os.path.isfile(source_path):
                continue
            try:
                archived_path = self.archive_file(source_path, target_root)
                if archived_path:
                    serial = extract_serial_from_report_name(filename)
                    state_repo.update_report_path_by_serial(
                        serial,
                        archived_path,
                        "已归档",
                        report_type=report_type_from_name(filename),
                    )
                    moved += 1
            except Exception as exc:
                errors.append(f"{filename}: {exc}")
        return moved, errors
