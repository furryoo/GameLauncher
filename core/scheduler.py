from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from PySide6.QtCore import QObject, Signal


class AppScheduler(QObject):
    """
    用 BackgroundScheduler（后台线程）触发定时任务。
    通过 Qt Signal 将回调安全地派发到主线程。
    """
    _trigger = Signal()

    def __init__(self, callback, parent=None):
        super().__init__(parent)
        self._trigger.connect(callback)          # callback 在主线程中执行
        self.scheduler = BackgroundScheduler()
        self.scheduler.start()
        self._job = None

    def set_schedule(self, enabled: bool, time_str: str):
        """设置或取消定时任务，time_str 格式为 'HH:MM'"""
        if self._job:
            self._job.remove()
            self._job = None

        if enabled and time_str:
            try:
                hour, minute = map(int, time_str.split(":"))
                self._job = self.scheduler.add_job(
                    self._trigger.emit,
                    CronTrigger(hour=hour, minute=minute),
                )
            except Exception:
                pass

    def shutdown(self):
        self.scheduler.shutdown(wait=False)
