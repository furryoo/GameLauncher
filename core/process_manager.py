import os
import subprocess
import sys
import time
import psutil
from PySide6.QtCore import QThread, Signal

from core.enums import RunResult, PostAction
from core.utils import format_duration


def _kill(pid: int):
    try:
        psutil.Process(pid).kill()
    except Exception:
        pass


def execute_post_action(action: str, log_fn):
    """执行完成后操作（关机/休眠），仅 Windows 生效"""
    if action == PostAction.SHUTDOWN:
        log_fn("💤 60秒后关机，在任务栏运行 'shutdown /a' 可取消")
        if sys.platform == "win32":
            os.system("shutdown /s /t 60")
    elif action == PostAction.HIBERNATE:
        log_fn("💤 正在休眠...")
        if sys.platform == "win32":
            os.system("shutdown /h")


class TaskRunner(QThread):
    """在后台线程中按顺序运行所有任务"""
    log_signal    = Signal(str)
    task_started  = Signal(int, str)
    task_finished = Signal(int, str, int)        # (index, name, elapsed_seconds)
    task_failed   = Signal(int, str, str)        # (index, name, reason)
    all_done      = Signal(str)                  # post_action

    def __init__(self, tasks, post_action: str = PostAction.NONE, parent=None):
        super().__init__(parent)
        self.tasks = tasks
        self.post_action = post_action
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

            if not os.path.isfile(task.exe_path):
                reason = f"路径不存在: {task.exe_path}"
                self.log_signal.emit(f"✗ {task.name} {reason}")
                self.task_failed.emit(i, task.name, reason)
                continue

            # ── 启动前延迟 ──────────────────────────────────────
            if task.delay_seconds > 0:
                self.log_signal.emit(
                    f"⏳ {task.name} 等待 {task.delay_seconds} 秒后启动..."
                )
                for _ in range(task.delay_seconds):
                    if self._stop_flag:
                        self.log_signal.emit("已手动停止")
                        return
                    time.sleep(1)

            # ── 重试循环 ─────────────────────────────────────────
            max_attempts = 1 + max(0, task.retry_count)
            succeeded = False

            for attempt in range(max_attempts):
                if self._stop_flag:
                    self.log_signal.emit("已手动停止")
                    return

                if attempt > 0:
                    self.log_signal.emit(
                        f"🔄 {task.name} 第 {attempt}/{task.retry_count} 次重试（30秒后启动）..."
                    )
                    for _ in range(30):
                        if self._stop_flag:
                            self.log_signal.emit("已手动停止")
                            return
                        time.sleep(1)

                self.log_signal.emit(
                    f"▶ 正在启动 {task.name}"
                    + (f"（第{attempt+1}次尝试）" if max_attempts > 1 else "") + "..."
                )
                if attempt == 0:
                    self.task_started.emit(i, task.name)

                try:
                    proc = subprocess.Popen(
                        task.exe_path,
                        cwd=os.path.dirname(task.exe_path),
                    )
                except Exception as e:
                    reason = f"启动失败: {e}"
                    self.log_signal.emit(f"✗ {task.name} {reason}")
                    continue  # 触发重试

                start_time = time.time()
                timeout = task.timeout if task.timeout > 0 else None
                abnormal = False

                while True:
                    if self._stop_flag:
                        _kill(proc.pid)
                        self.log_signal.emit("已手动停止")
                        return

                    try:
                        ret = proc.wait(timeout=2)
                        if ret != 0:
                            self.log_signal.emit(
                                f"⚠ {task.name} 异常退出（退出码: {ret}）"
                            )
                            abnormal = True
                        break
                    except subprocess.TimeoutExpired:
                        pass

                    if timeout and int(time.time() - start_time) >= timeout:
                        _kill(proc.pid)
                        self.log_signal.emit(
                            f"⚠ {task.name} 超时（{timeout}秒），已强制结束"
                        )
                        abnormal = True
                        break

                elapsed = int(time.time() - start_time)

                if not abnormal:
                    succeeded = True
                    duration = format_duration(elapsed)
                    self.log_signal.emit(f"✓ {task.name} 已完成（运行 {duration}）")
                    self.task_finished.emit(i, task.name, elapsed)
                    break  # 成功，不再重试
                elif attempt < max_attempts - 1:
                    self.log_signal.emit(f"  将进行第 {attempt+1}/{task.retry_count} 次重试...")
                else:
                    # 最后一次重试也失败
                    reason = "异常退出，重试耗尽" if task.retry_count > 0 else "异常退出"
                    self.log_signal.emit(f"✗ {task.name} {reason}")
                    self.task_failed.emit(i, task.name, reason)

        self.log_signal.emit("✅ 所有任务已完成")
        self.all_done.emit(self.post_action)
