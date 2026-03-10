import datetime
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QFrame
from PySide6.QtCore import Qt, QTime
from qfluentwidgets import (
    FluentWindow, NavigationItemPosition, FluentIcon,
    PrimaryPushButton, PushButton, BodyLabel, StrongBodyLabel,
    CaptionLabel, CardWidget, SwitchButton, TimeEdit,
    PlainTextEdit, SubtitleLabel, InfoBar, InfoBarPosition,
    ScrollArea as FScrollArea, SmoothScrollArea,
)

from core.config import AppConfig, TaskConfig, load_config, save_config
from core.process_manager import TaskRunner
from core.scheduler import AppScheduler
from ui.task_list import DraggableTaskList


class MainInterface(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("mainInterface")
        self.config = load_config()
        self.runner: TaskRunner | None = None
        self._setup_ui()
        self._setup_scheduler()
        self._load_config_to_ui()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 16, 24, 16)
        root.setSpacing(16)

        # --- 标题区 ---
        title_row = QHBoxLayout()
        title_label = SubtitleLabel("Game Automation Launcher")
        self.status_label = CaptionLabel("就绪")
        title_row.addWidget(title_label)
        title_row.addStretch()
        title_row.addWidget(self.status_label)
        root.addLayout(title_row)

        # --- 任务列表（可滚动）---
        scroll = SmoothScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        self.task_list = DraggableTaskList()
        self.task_list.changed.connect(self._auto_save)
        scroll.setWidget(self.task_list)
        scroll.setMinimumHeight(300)
        root.addWidget(scroll, stretch=1)

        # --- 调度设置卡片 ---
        sched_card = CardWidget()
        sched_layout = QHBoxLayout(sched_card)
        sched_layout.setContentsMargins(16, 12, 16, 12)

        sched_layout.addWidget(BodyLabel("定时启动:"))
        self.sched_switch = SwitchButton()
        self.sched_switch.checkedChanged.connect(self._on_schedule_changed)
        sched_layout.addWidget(self.sched_switch)

        self.time_edit = TimeEdit()
        self.time_edit.setDisplayFormat("HH:mm")
        self.time_edit.timeChanged.connect(self._on_schedule_changed)
        sched_layout.addWidget(self.time_edit)

        sched_layout.addStretch()

        self.start_btn = PrimaryPushButton(FluentIcon.PLAY, "立即启动")
        self.start_btn.clicked.connect(self.start_runner)
        self.stop_btn = PushButton(FluentIcon.CLOSE, "停止")
        self.stop_btn.clicked.connect(self.stop_runner)
        self.stop_btn.setEnabled(False)

        sched_layout.addWidget(self.start_btn)
        sched_layout.addWidget(self.stop_btn)
        root.addWidget(sched_card)

        # --- 日志面板 ---
        log_header = QHBoxLayout()
        log_header.addWidget(StrongBodyLabel("运行日志"))
        log_header.addStretch()
        clear_btn = PushButton("清空")
        clear_btn.setFixedWidth(64)
        clear_btn.clicked.connect(self._clear_log)
        log_header.addWidget(clear_btn)
        root.addLayout(log_header)

        self.log_edit = PlainTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setFixedHeight(200)
        self.log_edit.setPlaceholderText("运行日志将显示在这里...")
        root.addWidget(self.log_edit)

    def _setup_scheduler(self):
        self.scheduler = AppScheduler(callback=self.start_runner)

    def _load_config_to_ui(self):
        self.task_list.load_tasks(self.config.tasks)
        sched = self.config.schedule
        self.sched_switch.setChecked(sched.enabled)
        if sched.time:
            h, m = map(int, sched.time.split(":"))
            self.time_edit.setTime(QTime(h, m))
        self._apply_schedule()

    def _auto_save(self):
        self.config.tasks = self.task_list.get_tasks()
        save_config(self.config)

    def _on_schedule_changed(self):
        self.config.schedule.enabled = self.sched_switch.isChecked()
        self.config.schedule.time = self.time_edit.time().toString("HH:mm")
        save_config(self.config)
        self._apply_schedule()

    def _apply_schedule(self):
        self.scheduler.set_schedule(
            self.config.schedule.enabled,
            self.config.schedule.time,
        )

    def start_runner(self):
        tasks = [t for t in self.task_list.get_tasks() if t.enabled and t.exe_path]
        if not tasks:
            InfoBar.warning("提示", "没有可运行的任务，请先配置路径", parent=self,
                            position=InfoBarPosition.TOP)
            return
        if self.runner and self.runner.isRunning():
            return

        self.task_list.reset_all_status()
        self.runner = TaskRunner(tasks)
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

    def _on_task_started(self, index, name):
        cards = self.task_list.get_cards()
        # 找到对应卡片（按任务名匹配）
        for card in cards:
            if card.task.name == name:
                card.set_status("running")

    def _on_task_finished(self, index, name, elapsed):
        cards = self.task_list.get_cards()
        mins, secs = divmod(elapsed, 60)
        hours, mins = divmod(mins, 60)
        duration = f"{hours}h {mins}m {secs}s" if hours else f"{mins}m {secs}s"
        for card in cards:
            if card.task.name == name:
                card.set_status("done", duration)

    def _on_task_failed(self, index, name, reason):
        cards = self.task_list.get_cards()
        for card in cards:
            if card.task.name == name:
                card.set_status("error")

    def _on_all_done(self):
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.status_label.setText("全部完成 ✓")
        InfoBar.success("完成", "所有任务已运行完毕", parent=self,
                        position=InfoBarPosition.TOP)

    def _append_log(self, text: str):
        now = datetime.datetime.now().strftime("%H:%M:%S")
        self.log_edit.appendPlainText(f"[{now}] {text}")

    def _clear_log(self):
        self.log_edit.clear()


class MainWindow(FluentWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Game Automation Launcher")
        self.resize(860, 720)

        self.main_interface = MainInterface()
        self.addSubInterface(
            self.main_interface,
            FluentIcon.PLAY,
            "启动器",
            NavigationItemPosition.TOP,
        )
        self.navigationInterface.setExpandWidth(180)
