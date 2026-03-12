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


class PostAction(StrEnum):
    NONE     = "none"
    SHUTDOWN = "shutdown"
    HIBERNATE = "hibernate"


class RunIf(StrEnum):
    ALWAYS       = "always"        # 总是运行
    PREV_SUCCESS = "prev_success"  # 前置任务成功才运行
    PREV_FAIL    = "prev_fail"     # 前置任务失败才运行
