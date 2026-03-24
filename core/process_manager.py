import os
import subprocess
import sys
import threading
import time
import psutil
from PySide6.QtCore import QThread, Signal

from core.enums import RunResult, PostAction, RunIf
from core.utils import format_duration
from core.watchdog import ProcessWatchdog

_SIGTERM_TIMEOUT = 3       # SIGTERM 后等待秒数，超时则 SIGKILL
_RETRY_DELAY = 30          # 重试间隔秒数
_POLL_INTERVAL = 2         # proc.wait() 轮询间隔秒数
_MONITOR_INTERVAL = 30     # 资源采样间隔秒数


def _kill(proc: subprocess.Popen):
    """先 SIGTERM，等待后超时再强制 kill"""
    try:
        proc.terminate()
        try:
            proc.wait(timeout=_SIGTERM_TIMEOUT)
        except subprocess.TimeoutExpired:
            proc.kill()
    except OSError:
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
    task_started  = Signal(int, str)        # (index, task_id)
    task_finished = Signal(int, str, int)   # (index, task_id, elapsed_seconds)
    task_failed   = Signal(int, str, str)   # (index, task_id, reason)
    all_done      = Signal(str)             # post_action

    def __init__(self, tasks, post_action: str = PostAction.NONE, parent=None):
        super().__init__(parent)
        self.tasks = tasks
        self.post_action = post_action
        self._stop_flag = threading.Event()

    def stop(self):
        self._stop_flag.set()

    def run(self):
        prev_result: RunResult | None = None  # 上一任务的运行结果

        for i, task in enumerate(self.tasks):
            if self._stop_flag.is_set():
                self.log_signal.emit("已手动停止")
                return

            if not task.enabled:
                self.log_signal.emit(f"跳过 {task.name}（已禁用）")
                continue

            # ── 前置条件检查 ────────────────────────────────────
            if prev_result is not None and task.run_if != RunIf.ALWAYS:
                if task.run_if == RunIf.PREV_SUCCESS and prev_result != RunResult.SUCCESS:
                    self.log_signal.emit(f"⏭ 跳过 {task.name}（前置任务未成功）")
                    continue
                if task.run_if == RunIf.PREV_FAIL and prev_result == RunResult.SUCCESS:
                    self.log_signal.emit(f"⏭ 跳过 {task.name}（前置任务已成功）")
                    continue

            exe_path = os.path.expandvars(task.exe_path)
            if not os.path.isfile(exe_path):
                reason = f"路径不存在: {task.exe_path}"
                self.log_signal.emit(f"✗ {task.name} {reason}")
                self.task_failed.emit(i, task.id, reason)
                prev_result = RunResult.FAILED
                continue

            # ── 冲突检查：目标进程已在运行则跳过 ─────────────────
            proc_name = os.path.basename(exe_path).lower()
            if any(p.name().lower() == proc_name
                   for p in psutil.process_iter(["name"])):
                self.log_signal.emit(f"⚠ {task.name} 进程已在运行，跳过")
                continue

            # ── 启动前延迟 ──────────────────────────────────────
            if task.delay_seconds > 0:
                self.log_signal.emit(
                    f"⏳ {task.name} 等待 {task.delay_seconds} 秒后启动..."
                )
                for _ in range(task.delay_seconds):
                    if self._stop_flag.wait(1):
                        self.log_signal.emit("已手动停止")
                        return

            # ── 重试循环 ─────────────────────────────────────────
            max_attempts = 1 + max(0, task.retry_count)

            for attempt in range(max_attempts):
                if self._stop_flag.is_set():
                    self.log_signal.emit("已手动停止")
                    return

                if attempt > 0:
                    self.log_signal.emit(
                        f"🔄 {task.name} 第 {attempt}/{task.retry_count} 次重试（{_RETRY_DELAY}秒后启动）..."
                    )
                    for _ in range(_RETRY_DELAY):
                        if self._stop_flag.wait(1):
                            self.log_signal.emit("已手动停止")
                            return

                self.log_signal.emit(
                    f"▶ 正在启动 {task.name}"
                    + (f"（第{attempt+1}次尝试）" if max_attempts > 1 else "") + "..."
                )
                if attempt == 0:
                    self.task_started.emit(i, task.id)

                try:
                    proc = subprocess.Popen(
                        exe_path,
                        cwd=os.path.dirname(exe_path),
                    )
                except OSError as e:
                    reason = f"启动失败: {e}"
                    self.log_signal.emit(f"✗ {task.name} {reason}")
                    continue  # 触发重试

                watchdog = ProcessWatchdog(proc.pid)
                watchdog.start()
                start_time = time.time()
                last_monitor = start_time
                timeout = task.timeout if task.timeout > 0 else None
                abnormal = False

                try:
                    while True:
                        if self._stop_flag.is_set():
                            _kill(proc)
                            self.log_signal.emit("已手动停止")
                            return

                        if watchdog.is_frozen():
                            _kill(proc)
                            self.log_signal.emit(
                                f"⚠ {task.name} 进程卡死（CPU持续为0%），已强制结束"
                            )
                            abnormal = True
                            break

                        try:
                            ret = proc.wait(timeout=_POLL_INTERVAL)
                            if ret != 0:
                                self.log_signal.emit(
                                    f"⚠ {task.name} 异常退出（退出码: {ret}）"
                                )
                                abnormal = True
                            break
                        except subprocess.TimeoutExpired:
                            pass

                        if timeout and int(time.time() - start_time) >= timeout:
                            _kill(proc)
                            self.log_signal.emit(
                                f"⚠ {task.name} 超时（{timeout}秒），已强制结束"
                            )
                            abnormal = True
                            break

                        now = time.time()
                        if now - last_monitor >= _MONITOR_INTERVAL:
                            try:
                                p = psutil.Process(proc.pid)
                                cpu = p.cpu_percent(interval=None)
                                mem_mb = p.memory_info().rss / 1024 / 1024
                                self.log_signal.emit(
                                    f"  📊 {task.name}  CPU {cpu:.1f}%  内存 {mem_mb:.0f} MB"
                                )
                            except psutil.Error:
                                pass
                            last_monitor = now
                finally:
                    watchdog.stop()

                elapsed = int(time.time() - start_time)

                if not abnormal:
                    duration = format_duration(elapsed)
                    self.log_signal.emit(f"✓ {task.name} 已完成（运行 {duration}）")
                    self.task_finished.emit(i, task.id, elapsed)
                    prev_result = RunResult.SUCCESS
                    break  # 成功，不再重试
                elif attempt < max_attempts - 1:
                    self.log_signal.emit(f"  将进行第 {attempt+1}/{task.retry_count} 次重试...")
                else:
                    # 最后一次重试也失败
                    reason = "异常退出，重试耗尽" if task.retry_count > 0 else "异常退出"
                    self.log_signal.emit(f"✗ {task.name} {reason}")
                    self.task_failed.emit(i, task.id, reason)
                    prev_result = RunResult.FAILED

        self.log_signal.emit("✅ 所有任务已完成")
        self.all_done.emit(self.post_action)
