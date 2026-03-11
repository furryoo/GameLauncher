from PySide6.QtCore import QObject, QTimer, QTime, QDate


class AppScheduler(QObject):
    """
    每 20 秒检查一次当前时间，匹配后在主线程直接调用 callback。
    比 APScheduler 轻量：无后台线程，无额外依赖。
    """

    def __init__(self, callback, parent=None):
        super().__init__(parent)
        self._callback = callback
        self._hour = -1
        self._minute = -1
        self._last_fired = ""   # "YYYY-MM-DD HH:MM"，防止同一分钟重复触发

        self._timer = QTimer(self)
        self._timer.setInterval(20_000)
        self._timer.timeout.connect(self._check)

    def set_schedule(self, enabled: bool, time_str: str):
        self._timer.stop()
        if enabled and time_str:
            try:
                self._hour, self._minute = map(int, time_str.split(":"))
                self._timer.start()
            except ValueError:
                pass

    def _check(self):
        now = QTime.currentTime()
        if now.hour() == self._hour and now.minute() == self._minute:
            key = f"{QDate.currentDate().toString('yyyy-MM-dd')} {self._hour:02d}:{self._minute:02d}"
            if self._last_fired != key:
                self._last_fired = key
                self._callback()

    def shutdown(self):
        self._timer.stop()
