from apscheduler.schedulers.qt import QtScheduler
from apscheduler.triggers.cron import CronTrigger


class AppScheduler:
    def __init__(self, callback):
        self.callback = callback
        self.scheduler = QtScheduler()
        self.scheduler.start()
        self._job = None

    def set_schedule(self, enabled: bool, time_str: str):
        """设置或取消定时任务，time_str 格式为 'HH:MM'"""
        if self._job:
            self._job.remove()
            self._job = None

        if enabled and time_str:
            hour, minute = map(int, time_str.split(":"))
            self._job = self.scheduler.add_job(
                self.callback,
                CronTrigger(hour=hour, minute=minute),
            )

    def shutdown(self):
        self.scheduler.shutdown(wait=False)
