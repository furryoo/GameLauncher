import os
import subprocess
import time
import psutil
from PySide6.QtCore import QThread, Signal


def _format_duration(seconds: int) -> str:
    mins, secs = divmod(seconds, 60)
    hours, mins = divmod(mins, 60)
    return f"{hours}h {mins}m {secs}s" if hours else f"{mins}m {secs}s"


class TaskRunner(QThread):
    """在后台线程中按顺序运行所有任务"""
    log_signal = Signal(str)
    task_started = Signal(int, str)
    task_finished = Signal(int, str, int)   # (index, name, elapsed_seconds)
    task_failed = Signal(int, str, str)     # (index, name, reason)
    all_done = Signal()

    def __init__(self, tasks, parent=None):
        super().__init__(parent)
        self.tasks = tasks
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

            # 启动前检查路径
            if not os.path.isfile(task.exe_path):
                reason = f"路径不存在: {task.exe_path}"
                self.log_signal.emit(f"✗ {task.name} {reason}")
                self.task_failed.emit(i, task.name, reason)
                continue

            self.log_signal.emit(f"▶ 正在启动 {task.name}...")
            self.task_started.emit(i, task.name)

            # 以 exe 所在目录作为工作目录
            work_dir = os.path.dirname(task.exe_path)

            try:
                proc = subprocess.Popen(task.exe_path, cwd=work_dir)
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
                    # 检测异常退出（非0返回码视为异常）
                    if ret != 0:
                        self.log_signal.emit(
                            f"⚠ {task.name} 异常退出（退出码: {ret}），继续下一任务"
                        )
                    break

                elapsed = int(time.time() - start_time)
                if timeout and elapsed >= timeout:
                    try:
                        psutil.Process(proc.pid).kill()
                    except Exception:
                        pass
                    self.log_signal.emit(
                        f"⚠ {task.name} 超时（{timeout}秒），已强制结束"
                    )
                    break

                time.sleep(2)

            elapsed = int(time.time() - start_time)
            duration = _format_duration(elapsed)
            self.log_signal.emit(f"✓ {task.name} 已完成（运行 {duration}）")
            self.task_finished.emit(i, task.name, elapsed)

        self.log_signal.emit("✅ 所有任务已完成")
        self.all_done.emit()
