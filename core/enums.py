from enum import StrEnum


class CardStatus(StrEnum):
    IDLE    = "idle"
    RUNNING = "running"
    DONE    = "done"
    ERROR   = "error"


class RunResult(StrEnum):
    SUCCESS = "success"
    FAILED  = "failed"
    TIMEOUT = "timeout"
    STOPPED = "stopped"
