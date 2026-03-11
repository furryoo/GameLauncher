import os
import datetime

LOGS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
_MAX_LOGS = 30


def new_log_path() -> str:
    """创建本次运行的日志文件路径（同时确保 logs/ 目录存在）"""
    os.makedirs(LOGS_DIR, exist_ok=True)
    name = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M") + ".log"
    return os.path.join(LOGS_DIR, name)


def cleanup_old_logs():
    """保留最新 30 个日志文件，删除更早的"""
    if not os.path.isdir(LOGS_DIR):
        return
    files = sorted(
        (f for f in os.listdir(LOGS_DIR) if f.endswith(".log")),
        reverse=True,
    )
    for old in files[_MAX_LOGS:]:
        try:
            os.remove(os.path.join(LOGS_DIR, old))
        except OSError:
            pass


def open_logs_dir():
    os.makedirs(LOGS_DIR, exist_ok=True)
    if os.name == "nt":
        os.startfile(LOGS_DIR)
