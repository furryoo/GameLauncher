from PySide6.QtCore import QObject, QTimer, QTime, QDate


class AppScheduler(QObject):
    """
    每 20 秒检查一次当前时间，匹配后在主线程直接调用 callback。
    支持指定星期几触发（days 为空列表或 None 表示每天）。
    """

    def __init__(self, callback, parent=None):
        super().__init__(parent)
        self._callback = callback
        self._hour = -1
        self._minute = -1
        self._days: set[int] = set(range(7))   # 0=周一…6=周日
        self._last_fired = ""                   # "YYYY-MM-DD HH:MM"

        self._timer = QTimer(self)
        self._timer.setInterval(20_000)
        self._timer.timeout.connect(self._check)

    def set_schedule(self, enabled: bool, time_str: str, days: list[int] | None = None):
        self._timer.stop()
        self._days = set(days) if days is not None else set(range(7))
        if enabled and time_str:
            try:
                self._hour, self._minute = map(int, time_str.split(":"))
                self._timer.start()
            except ValueError:
                pass

    def _check(self):
        now = QTime.currentTime()
        if now.hour() != self._hour or now.minute() != self._minute:
            return
        today = (QDate.currentDate().dayOfWeek() - 1) % 7   # Qt: 1=Mon,7=Sun → 0=Mon,6=Sun
        if today not in self._days:
            return
        key = f"{QDate.currentDate().toString('yyyy-MM-dd')} {self._hour:02d}:{self._minute:02d}"
        if self._last_fired != key:
            self._last_fired = key
            self._callback()

    def shutdown(self):
        self._timer.stop()
