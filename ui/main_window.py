import os
import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame,
    QSystemTrayIcon, QMenu, QApplication,
)
from PySide6.QtCore import QTime, Signal
from PySide6.QtGui import QAction
from qfluentwidgets import (
    FluentWindow, NavigationItemPosition, FluentIcon,
    PrimaryPushButton, PushButton, BodyLabel, StrongBodyLabel,
    CaptionLabel, CardWidget, SwitchButton, TimeEdit,
    PlainTextEdit, SubtitleLabel, InfoBar, InfoBarPosition,
    SmoothScrollArea, TableWidget, HeaderView, ComboBox, CheckBox, LineEdit,
)
from PySide6.QtWidgets import QTableWidgetItem

from core.config import load_config, save_config
from core.enums import CardStatus, RunResult, PostAction
from core.utils import format_duration
from core.process_manager import TaskRunner, execute_post_action
from core.scheduler import AppScheduler
from core import history, logger, notifier
from ui.task_list import DraggableTaskList
from ui.version_view import VersionInterface

_POST_ACTIONS = [PostAction.NONE, PostAction.SHUTDOWN, PostAction.HIBERNATE]


# ─────────────────────────────────────────────────────────────
# 启动器主界面
# ─────────────────────────────────────────────────────────────
class LauncherInterface(QWidget):
    notify = Signal(str, str)   # (title, message) → 由主窗口连接到托盘通知

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("launcherInterface")
        self.config = load_config()
        self.runner: TaskRunner | None = None
        self._log_file = None
        self._setup_ui()
        self._setup_scheduler()
        self._load_config_to_ui()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 16, 24, 16)
        root.setSpacing(16)

        # 标题 + 状态
        title_row = QHBoxLayout()
        title_row.addWidget(SubtitleLabel("Game Automation Launcher"))
        title_row.addStretch()
        self.status_label = CaptionLabel("就绪")
        title_row.addWidget(self.status_label)
        root.addLayout(title_row)

        # 任务列表
        scroll = SmoothScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.task_list = DraggableTaskList()
        self.task_list.changed.connect(self._auto_save)
        scroll.setWidget(self.task_list)
        scroll.setMinimumHeight(280)
        root.addWidget(scroll, stretch=1)

        # 调度 + 控制按钮
        sched_card = CardWidget()
        sched_vbox = QVBoxLayout(sched_card)
        sched_vbox.setContentsMargins(16, 12, 16, 12)
        sched_vbox.setSpacing(8)

        # 第一行：开关 / 时间 / 完成后 / 按钮
        row1 = QHBoxLayout()
        row1.setSpacing(10)
        row1.addWidget(BodyLabel("定时启动:"))
        self.sched_switch = SwitchButton()
        self.sched_switch.checkedChanged.connect(self._on_schedule_changed)
        row1.addWidget(self.sched_switch)

        self.time_edit = TimeEdit()
        self.time_edit.setDisplayFormat("HH:mm")
        self.time_edit.timeChanged.connect(self._on_schedule_changed)
        row1.addWidget(self.time_edit)

        row1.addSpacing(12)
        row1.addWidget(BodyLabel("完成后:"))
        self.post_action_combo = ComboBox()
        self.post_action_combo.addItems(["无", "关机", "休眠"])
        self.post_action_combo.currentIndexChanged.connect(self._on_schedule_changed)
        row1.addWidget(self.post_action_combo)
        row1.addStretch()

        self.start_btn = PrimaryPushButton(FluentIcon.PLAY, "立即启动")
        self.start_btn.clicked.connect(self.start_runner)
        self.stop_btn = PushButton(FluentIcon.CLOSE, "停止")
        self.stop_btn.clicked.connect(self.stop_runner)
        self.stop_btn.setEnabled(False)
        row1.addWidget(self.start_btn)
        row1.addWidget(self.stop_btn)

        # 第二行：星期选择
        row2 = QHBoxLayout()
        row2.setSpacing(4)
        row2.addWidget(CaptionLabel("重复:"))
        self.day_checks: list[CheckBox] = []
        for label in ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]:
            cb = CheckBox(label)
            cb.setChecked(True)
            cb.checkStateChanged.connect(self._on_schedule_changed)
            self.day_checks.append(cb)
            row2.addWidget(cb)
        row2.addStretch()

        sched_vbox.addLayout(row1)
        sched_vbox.addLayout(row2)
        root.addWidget(sched_card)

        # 通知设置
        notify_card = CardWidget()
        notify_layout = QHBoxLayout(notify_card)
        notify_layout.setContentsMargins(16, 10, 16, 10)
        notify_layout.setSpacing(10)
        notify_layout.addWidget(BodyLabel("Bark 推送:"))
        self.bark_edit = LineEdit()
        self.bark_edit.setPlaceholderText("https://api.day.app/your-key（留空则不推送）")
        self.bark_edit.textChanged.connect(self._on_notify_changed)
        notify_layout.addWidget(self.bark_edit)
        root.addWidget(notify_card)

        # 日志面板
        log_header = QHBoxLayout()
        log_header.addWidget(StrongBodyLabel("运行日志"))
        log_header.addStretch()
        open_log_btn = PushButton(FluentIcon.FOLDER, "日志文件夹")
        open_log_btn.clicked.connect(logger.open_logs_dir)
        log_header.addWidget(open_log_btn)
        clear_btn = PushButton("清空")
        clear_btn.setFixedWidth(64)
        clear_btn.clicked.connect(lambda: self.log_edit.clear())
        log_header.addWidget(clear_btn)
        root.addLayout(log_header)

        self.log_edit = PlainTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setFixedHeight(180)
        self.log_edit.setPlaceholderText("运行日志将在此显示...")
        root.addWidget(self.log_edit)

    def _setup_scheduler(self):
        self.scheduler = AppScheduler(callback=self.start_runner, parent=self)

    def _load_config_to_ui(self):
        self.task_list.load_tasks(self.config.tasks)
        sched = self.config.schedule
        self.sched_switch.setChecked(sched.enabled)
        if sched.time:
            h, m = map(int, sched.time.split(":"))
            self.time_edit.setTime(QTime(h, m))
        idx = _POST_ACTIONS.index(sched.post_action) if sched.post_action in _POST_ACTIONS else 0
        self.post_action_combo.setCurrentIndex(idx)
        for i, cb in enumerate(self.day_checks):
            cb.setChecked(i in sched.days)
        self.bark_edit.setText(self.config.notify.bark_url)
        self._apply_schedule()

    def _auto_save(self):
        self.config.tasks = self.task_list.get_tasks()
        save_config(self.config)

    def _on_schedule_changed(self):
        self.config.schedule.enabled = self.sched_switch.isChecked()
        self.config.schedule.time = self.time_edit.time().toString("HH:mm")
        self.config.schedule.post_action = _POST_ACTIONS[self.post_action_combo.currentIndex()]
        self.config.schedule.days = [i for i, cb in enumerate(self.day_checks) if cb.isChecked()]
        save_config(self.config)
        self._apply_schedule()

    def _on_notify_changed(self):
        self.config.notify.bark_url = self.bark_edit.text().strip()
        save_config(self.config)

    def _apply_schedule(self):
        self.scheduler.set_schedule(
            self.config.schedule.enabled,
            self.config.schedule.time,
            self.config.schedule.days,
        )

    # ── 运行控制 ──────────────────────────────────────────────

    def start_runner(self):
        tasks = [t for t in self.task_list.get_tasks() if t.enabled and t.exe_path]
        if not tasks:
            InfoBar.warning("提示", "没有可运行的任务，请先配置路径",
                            parent=self, position=InfoBarPosition.TOP)
            return
        if self.runner and self.runner.isRunning():
            return

        if self.runner:
            self.runner.log_signal.disconnect()
            self.runner.task_started.disconnect()
            self.runner.task_finished.disconnect()
            self.runner.task_failed.disconnect()
            self.runner.all_done.disconnect()

        if self._log_file:
            self._log_file.close()
        self._log_file = open(logger.new_log_path(), "w", encoding="utf-8")
        logger.cleanup_old_logs()

        self.task_list.reset_all_status()
        self.runner = TaskRunner(tasks, post_action=self.config.schedule.post_action)
        self.runner.log_signal.connect(self._append_log)
        self.runner.task_started.connect(self._on_task_started)
        self.runner.task_finished.connect(self._on_task_finished)
        self.runner.task_failed.connect(self._on_task_failed)
        self.runner.all_done.connect(self._on_all_done)
        self.runner.start()

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.status_label.setText("运行中...")

    def stop_runner(self):
        if self.runner:
            self.runner.stop()
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.status_label.setText("已停止")

    # ── Runner 信号处理 ───────────────────────────────────────

    def _on_task_started(self, _index: int, name: str):
        if card := self.task_list.get_card_by_name(name):
            card.set_status(CardStatus.RUNNING)

    def _on_task_finished(self, _index: int, name: str, elapsed: int):
        if card := self.task_list.get_card_by_name(name):
            card.set_status(CardStatus.DONE, format_duration(elapsed))
        history.add_record(name, RunResult.SUCCESS, elapsed)

    def _on_task_failed(self, _index: int, name: str, reason: str):
        if card := self.task_list.get_card_by_name(name):
            card.set_status(CardStatus.ERROR)
        history.add_record(name, RunResult.FAILED, 0)
        notifier.send_bark(self.config.notify.bark_url, "任务失败", f"{name}：{reason}")

    def _on_all_done(self, post_action: str):
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.status_label.setText("全部完成 ✓")
        InfoBar.success("完成", "所有任务已运行完毕",
                        parent=self, position=InfoBarPosition.TOP)
        self.notify.emit("Game Launcher", "所有任务已完成 ✓")
        notifier.send_bark(self.config.notify.bark_url, "Game Launcher", "所有任务已完成 ✓")
        execute_post_action(post_action, self._append_log)

    def _append_log(self, text: str):
        now = datetime.datetime.now().strftime("%H:%M:%S")
        line = f"[{now}] {text}"
        self.log_edit.appendPlainText(line)
        self.log_edit.ensureCursorVisible()
        if self._log_file:
            try:
                self._log_file.write(line + "\n")
                self._log_file.flush()
            except OSError:
                pass


# ─────────────────────────────────────────────────────────────
# 历史记录界面
# ─────────────────────────────────────────────────────────────
class HistoryInterface(QWidget):
    STATUS_TEXT = {
        RunResult.SUCCESS: "成功",
        RunResult.FAILED:  "失败",
        RunResult.TIMEOUT: "超时",
        RunResult.STOPPED: "已停止",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("historyInterface")
        self._setup_ui()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 16, 24, 16)
        root.setSpacing(12)

        header = QHBoxLayout()
        header.addWidget(SubtitleLabel("运行历史"))
        header.addStretch()
        refresh_btn = PushButton(FluentIcon.SYNC, "刷新")
        refresh_btn.clicked.connect(self.refresh)
        header.addWidget(refresh_btn)
        root.addLayout(header)

        self.table = TableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["时间", "任务", "状态", "时长"])
        self.table.horizontalHeader().setSectionResizeMode(
            0, HeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            1, HeaderView.ResizeMode.Stretch
        )
        self.table.setEditTriggers(TableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        root.addWidget(self.table)
        self.refresh()

    def refresh(self):
        records = history.get_records()
        self.table.setRowCount(len(records))
        for row, rec in enumerate(records):
            status_key = rec.get("status", "")
            status_label = self.STATUS_TEXT.get(status_key, status_key)
            secs = rec.get("duration", 0)
            self.table.setItem(row, 0, QTableWidgetItem(rec.get("time", "")))
            self.table.setItem(row, 1, QTableWidgetItem(rec.get("task", "")))
            self.table.setItem(row, 2, QTableWidgetItem(status_label))
            self.table.setItem(row, 3, QTableWidgetItem(format_duration(secs)))


# ─────────────────────────────────────────────────────────────
# 主窗口
# ─────────────────────────────────────────────────────────────
class MainWindow(FluentWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Game Automation Launcher")
        self.resize(900, 740)
        self._setup_interfaces()
        self._setup_tray()

    def _setup_interfaces(self):
        self.launcher = LauncherInterface()
        self.launcher.notify.connect(self._show_tray_message)   # 解耦托盘通知
        self.addSubInterface(
            self.launcher, FluentIcon.PLAY, "启动器",
            NavigationItemPosition.TOP,
        )
        self.history_view = HistoryInterface()
        self.addSubInterface(
            self.history_view, FluentIcon.HISTORY, "历史记录",
            NavigationItemPosition.TOP,
        )
        self.version_view = VersionInterface()
        self.addSubInterface(
            self.version_view, FluentIcon.UPDATE, "版本管理",
            NavigationItemPosition.BOTTOM,
        )
        self.navigationInterface.setExpandWidth(160)

    def _setup_tray(self):
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(self.style().standardIcon(
            self.style().StandardPixmap.SP_ComputerIcon
        ))
        tray_menu = QMenu()
        show_action = QAction("显示窗口", self)
        show_action.triggered.connect(self.show)
        quit_action = QAction("退出", self)
        quit_action.triggered.connect(self._quit)
        tray_menu.addAction(show_action)
        tray_menu.addSeparator()
        tray_menu.addAction(quit_action)
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()

    def _show_tray_message(self, title: str, message: str):
        if self.tray_icon.isVisible():
            self.tray_icon.showMessage(
                title, message, QSystemTrayIcon.MessageIcon.Information, 3000
            )

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show()
            self.raise_()

    def closeEvent(self, event):
        event.ignore()
        self.hide()
        self._show_tray_message("Game Launcher", "程序已最小化到托盘，双击图标可重新打开")

    def _quit(self):
        self.tray_icon.hide()
        if self.launcher.runner and self.launcher.runner.isRunning():
            self.launcher.runner.stop()
            self.launcher.runner.wait(3000)
        self.launcher.scheduler.shutdown()
        if self.launcher._log_file:
            self.launcher._log_file.close()
        QApplication.instance().quit()
