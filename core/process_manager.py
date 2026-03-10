import subprocess
import time
import psutil
from PySide6.QtCore import QThread, Signal


class TaskRunner(QThread):
    """在后台线程中按顺序运行所有任务"""
    log_signal = Signal(str)           # 日志消息
    task_started = Signal(int, str)    # (index, name) 任务开始
    task_finished = Signal(int, str, int)  # (index, name, elapsed_seconds) 任务完成
    task_failed = Signal(int, str, str)    # (index, name, reason) 任务失败
    all_done = Signal()                # 所有任务完成

    def __init__(self, tasks, parent=None):
        super().__init__(parent)
        self.tasks = tasks  # List[TaskConfig]
        self._stop_flag = False

    def stop(self):
        self._stop_flag = True

    def run(self):
        for i, task in enumerate(self.tasks):
            if self._stop_flag:
                self.log_signal.emit("已手动停止")
                return
            if not task.enabled:
                self.log_signal.emit(f"跳过 {task.name}（已禁用）")
                continue

            self.log_signal.emit(f"▶ 正在启动 {task.name}...")
            self.task_started.emit(i, task.name)

            try:
                proc = subprocess.Popen(
                    task.exe_path,
                    cwd=str(psutil.Process().cwd()) if False else None,
                )
            except Exception as e:
                reason = f"启动失败: {e}"
                self.log_signal.emit(f"✗ {task.name} {reason}")
                self.task_failed.emit(i, task.name, reason)
                continue

            start_time = time.time()
            timeout = task.timeout if task.timeout > 0 else None

            # 等待进程退出
            while True:
                if self._stop_flag:
                    try:
                        psutil.Process(proc.pid).kill()
                    except Exception:
                        pass
                    self.log_signal.emit("已手动停止")
                    return

                ret = proc.poll()
                if ret is not None:
                    break  # 进程已退出

                elapsed = int(time.time() - start_time)
                if timeout and elapsed >= timeout:
                    try:
                        psutil.Process(proc.pid).kill()
                    except Exception:
                        pass
                    self.log_signal.emit(f"⚠ {task.name} 超时（{timeout}秒），已强制结束")
                    break

                time.sleep(2)

            elapsed = int(time.time() - start_time)
            mins, secs = divmod(elapsed, 60)
            hours, mins = divmod(mins, 60)
            duration = f"{hours}h {mins}m {secs}s" if hours else f"{mins}m {secs}s"
            self.log_signal.emit(f"✓ {task.name} 已完成（运行 {duration}）")
            self.task_finished.emit(i, task.name, elapsed)

        self.log_signal.emit("✅ 所有任务已完成")
        self.all_done.emit()
