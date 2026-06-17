from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TorqueRecord:
    round_no: int
    sequence_no: int
    program_no: int
    set_torque: float
    actual_torque: float
    actual_angle: float
    result: str
    operator_work_no: str
    operator_name: str
    tightened_at: str


@dataclass(frozen=True)
class WorkpieceSummary:
    line_code: str
    line_name: str
    workpiece_id: int
    base_barcode: str
    product_code: str
    product_name: str
    expected_count: int
    round2_ok: int
    round3_ok: int
    round2_completed_at: str | None
    round3_completed_at: str | None
    records: list[TorqueRecord]


@dataclass(frozen=True)
class CoatingRecordSummary:
    line_code: str
    line_name: str
    record_id: int
    plate_sn: str
    operator_work_no: str
    operator_name: str
    assistant_work_no: str
    assistant_name: str
    recorded_at: str
    note: str


@dataclass(frozen=True)
class MesPart:
    barcode: str
    code: str


@dataclass(frozen=True)
class MesProduct:
    serial_number: str
    finished_time: str | None
    parts: list[MesPart]


@dataclass(frozen=True)
class ReportResult:
    line_code: str
    base_barcode: str
    product_serial_no: str
    report_path: str
