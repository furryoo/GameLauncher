import threading
import time
import psutil


class ProcessWatchdog:
    """每 interval 秒采样一次 CPU，连续 threshold 次为 0% 则判定进程卡死"""

    def __init__(self, pid: int, interval: int = 60, threshold: int = 3):
        self.pid = pid
        self.interval = interval
        self.threshold = threshold
        self._stop = threading.Event()
        self._frozen = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop.set()

    def is_frozen(self) -> bool:
        return self._frozen.is_set()

    def _run(self):
        zero_count = 0
        try:
            proc = psutil.Process(self.pid)
        except psutil.Error:
            return

        while not self._stop.wait(timeout=self.interval):
            try:
                cpu = proc.cpu_percent(interval=1)
            except psutil.Error:
                return
            if cpu == 0.0:
                zero_count += 1
                if zero_count >= self.threshold:
                    self._frozen.set()
                    return
            else:
                zero_count = 0
