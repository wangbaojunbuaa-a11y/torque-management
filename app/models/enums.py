from enum import Enum


class WorkpieceStatus(str, Enum):
    ROUND2_IN_PROGRESS = "ROUND2_IN_PROGRESS"
    RESTING = "RESTING"
    READY_ROUND3 = "READY_ROUND3"
    ROUND3_IN_PROGRESS = "ROUND3_IN_PROGRESS"
    FINISHED = "FINISHED"
    LOCKED_ERROR = "LOCKED_ERROR"


class TighteningResult(str, Enum):
    OK = "OK"
    NG = "NG"


STATUS_LABELS = {
    WorkpieceStatus.ROUND2_IN_PROGRESS.value: "第二次拧紧中",
    WorkpieceStatus.RESTING.value: "静置中",
    WorkpieceStatus.READY_ROUND3.value: "可第三次拧紧",
    WorkpieceStatus.ROUND3_IN_PROGRESS.value: "第三次拧紧中",
    WorkpieceStatus.FINISHED.value: "已完成",
    WorkpieceStatus.LOCKED_ERROR.value: "异常锁定",
}
