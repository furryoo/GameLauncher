import json
import os
import datetime
from collections import defaultdict
from contextlib import suppress
from dataclasses import asdict
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame,
    QSystemTrayIcon, QMenu, QApplication, QInputDialog, QFileDialog, QToolTip,
)
from PySide6.QtCore import QTime, Signal, Qt, QRect
from PySide6.QtGui import QAction, QPainter, QColor, QFont
from qfluentwidgets import (
    FluentWindow, NavigationItemPosition, FluentIcon,
    PrimaryPushButton, PushButton, BodyLabel, StrongBodyLabel,
    CaptionLabel, CardWidget, SwitchButton, TimeEdit,
    PlainTextEdit, SubtitleLabel, InfoBar, InfoBarPosition,
    SmoothScrollArea, TableWidget, HeaderView, ComboBox, CheckBox, LineEdit,
    MessageBox, ToolButton,
)
from PySide6.QtWidgets import QTableWidgetItem

from core.config import TaskConfig, load_config, save_config, _filter_fields
from core.enums import CardStatus, RunResult, PostAction
from core.utils import format_duration
from core.process_manager import TaskRunner, execute_post_action
from core.scheduler import AppScheduler
from core import history, logger, notifier
from ui.task_list import DraggableTaskList
from ui.theme import CHART_BAR_COLOR, CHART_AXIS_COLOR, CHART_LABEL_COLOR
from ui.version_view import VersionInterface

_POST_ACTIONS = [PostAction.NONE, PostAction.SHUTDOWN, PostAction.HIBERNATE]


# ─────────────────────────────────────────────────────────────
# 每日统计柱状图
# ─────────────────────────────────────────────────────────────
class DailyBarChart(QWidget):
    """过去 N 天每日运行总时长柱状图（QPainter 实现，无额外依赖）"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(180)
        self._data: list[tuple[str, int]] = []  # [(MM-DD, seconds)]
        self._bar_rects: list[tuple[QRect, str, int]] = []
        self._hovered_idx: int = -1
        self.setMouseTracking(True)

    def set_data(self, data: list[tuple[str, int]]):
        self._data = data
        self.update()

    def paintEvent(self, event):
        if not self._data:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        margin_l, margin_r, margin_t, margin_b = 48, 12, 8, 28
        chart_w = w - margin_l - margin_r
        chart_h = h - margin_t - margin_b

        max_val = max(v for _, v in self._data) or 1
        n = len(self._data)
        slot_w = chart_w // n
        bar_w = max(6, slot_w - 6)

        bar_color   = QColor(CHART_BAR_COLOR)
        axis_color  = QColor(CHART_AXIS_COLOR)
        label_color = QColor(CHART_LABEL_COLOR)

        font = QFont()
        font.setPointSize(7)
        painter.setFont(font)
        painter.setPen(axis_color)

        # 坐标轴
        painter.drawLine(margin_l, margin_t, margin_l, margin_t + chart_h)
        painter.drawLine(margin_l, margin_t + chart_h,
                         margin_l + chart_w, margin_t + chart_h)

        # Y 轴刻度（最大值）
        painter.setPen(label_color)
        max_label = format_duration(max_val)
        painter.drawText(0, margin_t + 8, margin_l - 4, 16,
                         Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                         max_label)

        # Y 轴分段网格线（3条刻度）
        tick_count = 3
        for ti in range(1, tick_count + 1):
            ty = margin_t + chart_h - int(chart_h * ti / tick_count)
            grid_color = QColor(CHART_AXIS_COLOR)
            grid_color.setAlpha(50)
            painter.setPen(grid_color)
            painter.drawLine(margin_l, ty, margin_l + chart_w, ty)
            painter.setPen(label_color)
            tick_val = int(max_val * ti / tick_count)
            painter.drawText(0, ty - 8, margin_l - 4, 16,
                             Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                             format_duration(tick_val))

        self._bar_rects = []
        for i, (label, val) in enumerate(self._data):
            x = margin_l + i * slot_w + (slot_w - bar_w) // 2
            bar_h = int(val / max_val * (chart_h - 4))
            y = margin_t + chart_h - bar_h

            painter.fillRect(x, y, bar_w, bar_h, bar_color)
            self._bar_rects.append((QRect(x, y, bar_w, bar_h), label, val))

            # X 轴日期标签
            painter.setPen(label_color)
            painter.drawText(x - 4, margin_t + chart_h + 4, bar_w + 8, 20,
                             Qt.AlignmentFlag.AlignHCenter, label)

        painter.end()

    def mouseMoveEvent(self, event):
        pos = event.position().toPoint()
        for idx, (rect, label, val) in enumerate(self._bar_rects):
            if rect.contains(pos):
                if self._hovered_idx != idx:
                    self._hovered_idx = idx
                    QToolTip.showText(
                        event.globalPosition().toPoint(),
                        f"{label}  {format_duration(val)}",
                        self
                    )
                return
        self._hovered_idx = -1
        QToolTip.hideText()


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

        # ── 标题行 ──
        title_row = QHBoxLayout()
        title_row.addWidget(SubtitleLabel("Game Automation Launcher"))
        title_row.addStretch()
        self.status_label = CaptionLabel("就绪")
        title_row.addWidget(self.status_label)
        root.addLayout(title_row)

        # ── 场景（Profile）行 ──
        profile_card = CardWidget()
        profile_layout = QHBoxLayout(profile_card)
        profile_layout.setContentsMargins(16, 12, 16, 12)
        profile_layout.setSpacing(8)

        profile_layout.addWidget(BodyLabel("场景:"))
        self.profile_combo = ComboBox()
        self.profile_combo.setMinimumWidth(120)
        self.profile_combo.currentTextChanged.connect(self._on_profile_changed)
        profile_layout.addWidget(self.profile_combo)

        add_profile_btn = ToolButton(FluentIcon.ADD)
        add_profile_btn.setFixedSize(28, 28)
        add_profile_btn.setToolTip("新建场景")
        add_profile_btn.clicked.connect(self._add_profile)
        profile_layout.addWidget(add_profile_btn)

        del_profile_btn = ToolButton(FluentIcon.DELETE)
        del_profile_btn.setFixedSize(28, 28)
        del_profile_btn.setToolTip("删除当前场景")
        del_profile_btn.clicked.connect(self._delete_profile)
        profile_layout.addWidget(del_profile_btn)

        profile_layout.addStretch()

        export_btn = PushButton(FluentIcon.SHARE, "导出")
        export_btn.setFixedWidth(72)
        export_btn.setToolTip("导出配置为 JSON 文件")
        export_btn.clicked.connect(self._export_config)
        profile_layout.addWidget(export_btn)

        import_btn = PushButton(FluentIcon.DOWNLOAD, "导入")
        import_btn.setFixedWidth(72)
        import_btn.setToolTip("从 JSON 文件导入配置")
        import_btn.clicked.connect(self._import_config)
        profile_layout.addWidget(import_btn)

        root.addWidget(profile_card)

        # ── 任务列表 ──
        scroll = SmoothScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.task_list = DraggableTaskList()
        self.task_list.changed.connect(self._auto_save)
        self.task_list.run_single.connect(self._start_single_task)
        scroll.setWidget(self.task_list)
        scroll.setMinimumHeight(280)
        root.addWidget(scroll, stretch=1)

        # ── 调度 + 控制按钮 ──
        sched_card = CardWidget()
        sched_vbox = QVBoxLayout(sched_card)
        sched_vbox.setContentsMargins(16, 12, 16, 12)
        sched_vbox.setSpacing(8)

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

        # ── 通知设置 ──
        notify_card = CardWidget()
        notify_layout = QHBoxLayout(notify_card)
        notify_layout.setContentsMargins(16, 12, 16, 12)
        notify_layout.setSpacing(10)
        notify_layout.addWidget(BodyLabel("Bark 推送:"))
        self.bark_edit = LineEdit()
        self.bark_edit.setPlaceholderText("https://api.day.app/your-key（留空则不推送）")
        self.bark_edit.textChanged.connect(self._on_notify_changed)
        notify_layout.addWidget(self.bark_edit)
        root.addWidget(notify_card)

        # ── 日志面板 ──
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
        self.log_edit.setMinimumHeight(150)
        self.log_edit.setPlaceholderText("运行日志将在此显示...")
        root.addWidget(self.log_edit)

    def _setup_scheduler(self):
        self.scheduler = AppScheduler(callback=self.start_runner, parent=self)

    def _load_config_to_ui(self):
        # ── 场景列表 ──
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        for name in self.config.profiles:
            self.profile_combo.addItem(name)
        self.profile_combo.setCurrentText(self.config.active_profile)
        self.profile_combo.blockSignals(False)

        self.task_list.load_tasks(
            self.config.profiles.get(self.config.active_profile, [])
        )

        # ── 调度设置 ──
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

    # ── 场景管理 ──────────────────────────────────────────────

    def _on_profile_changed(self, new_name: str):
        if not new_name or new_name == self.config.active_profile:
            return
        # 保存当前场景任务
        self.config.profiles[self.config.active_profile] = self.task_list.get_tasks()
        self.config.active_profile = new_name
        self.task_list.load_tasks(self.config.profiles.get(new_name, []))
        save_config(self.config)

    def _add_profile(self):
        name, ok = QInputDialog.getText(self, "新建场景", "场景名称:")
        if not ok or not name.strip():
            return
        name = name.strip()
        if name in self.config.profiles:
            InfoBar.warning("提示", f"场景 '{name}' 已存在",
                            parent=self, position=InfoBarPosition.TOP)
            return
        self.config.profiles[name] = []
        self.profile_combo.blockSignals(True)
        self.profile_combo.addItem(name)
        self.profile_combo.blockSignals(False)
        # 保存当前场景再切换
        self.config.profiles[self.config.active_profile] = self.task_list.get_tasks()
        self.config.active_profile = name
        self.profile_combo.setCurrentText(name)
        self.task_list.load_tasks([])
        save_config(self.config)

    def _delete_profile(self):
        if len(self.config.profiles) <= 1:
            InfoBar.warning("提示", "至少保留一个场景",
                            parent=self, position=InfoBarPosition.TOP)
            return
        current = self.config.active_profile
        box = MessageBox("确认删除", f"删除场景 '{current}'？此操作不可撤销。", self)
        if not box.exec():
            return
        del self.config.profiles[current]
        self.profile_combo.blockSignals(True)
        idx = self.profile_combo.findText(current)
        self.profile_combo.removeItem(idx)
        self.profile_combo.blockSignals(False)
        self.config.active_profile = self.profile_combo.currentText()
        self.task_list.load_tasks(self.config.profiles[self.config.active_profile])
        save_config(self.config)

    # ── 导入 / 导出 ───────────────────────────────────────────

    def _export_config(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "导出配置", "game_launcher_config.json", "JSON (*.json)"
        )
        if not path:
            return
        data = {
            "profiles": {
                name: [asdict(t) for t in tasks]
                for name, tasks in self.config.profiles.items()
            },
            "active_profile": self.config.active_profile,
            "schedule": asdict(self.config.schedule),
            "notify": asdict(self.config.notify),
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        InfoBar.success("成功", "配置已导出", parent=self, position=InfoBarPosition.TOP)

    def _import_config(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "导入配置", "", "JSON (*.json)"
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            raw_profiles = data.get("profiles", {})
            profiles = {
                name: [TaskConfig(**_filter_fields(t, TaskConfig)) for t in (ptasks or [])]
                for name, ptasks in raw_profiles.items()
            }
            if not profiles:
                profiles = {"默认": []}
            self.config.profiles = profiles
            self.config.active_profile = data.get("active_profile", next(iter(profiles)))
            if self.config.active_profile not in profiles:
                self.config.active_profile = next(iter(profiles))
            self._load_config_to_ui()
            save_config(self.config)
            InfoBar.success("成功", "配置已导入", parent=self, position=InfoBarPosition.TOP)
        except Exception as e:
            InfoBar.error("导入失败", str(e), parent=self, position=InfoBarPosition.TOP)

    # ── 自动保存 & 调度 ───────────────────────────────────────

    def _auto_save(self):
        self.config.profiles[self.config.active_profile] = self.task_list.get_tasks()
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

    def _setup_runner(self, tasks, post_action, status_text):
        if self.runner:
            self.runner.log_signal.disconnect(self._append_log)
            self.runner.task_started.disconnect(self._on_task_started)
            self.runner.task_finished.disconnect(self._on_task_finished)
            self.runner.task_failed.disconnect(self._on_task_failed)
            self.runner.all_done.disconnect(self._on_all_done)
            self.runner.deleteLater()

        if self._log_file:
            self._log_file.close()
            self._log_file = None
        try:
            self._log_file = open(logger.new_log_path(), "w", encoding="utf-8")
        except OSError:
            pass
        logger.cleanup_old_logs()

        self.task_list.reset_all_status()
        self.runner = TaskRunner(tasks, post_action=post_action)
        self.runner.log_signal.connect(self._append_log)
        self.runner.task_started.connect(self._on_task_started)
        self.runner.task_finished.connect(self._on_task_finished)
        self.runner.task_failed.connect(self._on_task_failed)
        self.runner.all_done.connect(self._on_all_done)
        self.runner.start()

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.status_label.setText(status_text)

    def start_runner(self):
        tasks = [t for t in self.task_list.get_tasks() if t.enabled and t.exe_path]
        if not tasks:
            InfoBar.warning("提示", "没有可运行的任务，请先配置路径",
                            parent=self, position=InfoBarPosition.TOP)
            return
        if self.runner and self.runner.isRunning():
            return

        task_names = "\n".join(f"  • {t.name}" for t in tasks)
        box = MessageBox("确认启动", f"即将运行以下 {len(tasks)} 个任务：\n\n{task_names}", self)
        if not box.exec():
            return

        self._setup_runner(tasks, self.config.schedule.post_action, "运行中...")

    def _start_single_task(self, card):
        task = card.task
        if not task.enabled or not task.exe_path:
            return
        if self.runner and self.runner.isRunning():
            InfoBar.warning("提示", "当前有任务正在运行，请等待完成后再单跑",
                            parent=self, position=InfoBarPosition.TOP)
            return

        self._setup_runner([task], PostAction.NONE, f"单跑: {task.name}")

    def stop_runner(self):
        if self.runner:
            self.runner.stop()
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.status_label.setText("已停止")

    # ── Runner 信号处理 ───────────────────────────────────────

    def _on_task_started(self, _index: int, task_id: str):
        if card := self.task_list.get_card_by_id(task_id):
            card.set_status(CardStatus.RUNNING)

    def _on_task_finished(self, _index: int, task_id: str, elapsed: int):
        card = self.task_list.get_card_by_id(task_id)
        if card:
            card.set_status(CardStatus.DONE, format_duration(elapsed))
            history.add_record(card.task.name, RunResult.SUCCESS, elapsed)

    def _on_task_failed(self, _index: int, task_id: str, reason: str):
        card = self.task_list.get_card_by_id(task_id)
        if card:
            card.set_status(CardStatus.ERROR)
            history.add_record(card.task.name, RunResult.FAILED, 0)
            notifier.send_bark(self.config.notify.bark_url, "任务失败",
                               f"{card.task.name}：{reason}")

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
                with suppress(Exception): self._log_file.close()
                self._log_file = None


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
    _FILTER_OPTIONS = [("全部", None), ("成功", RunResult.SUCCESS),
                       ("失败", RunResult.FAILED), ("超时", RunResult.TIMEOUT),
                       ("已停止", RunResult.STOPPED)]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("historyInterface")
        self._all_records: list[dict] = []
        self._setup_ui()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 16, 24, 16)
        root.setSpacing(16)

        # ── 顶部工具栏 ──
        header = QHBoxLayout()
        header.addWidget(SubtitleLabel("运行历史"))
        header.addStretch()
        header.addWidget(CaptionLabel("筛选:"))
        self.filter_combo = ComboBox()
        self.filter_combo.addItems([label for label, _ in self._FILTER_OPTIONS])
        self.filter_combo.currentIndexChanged.connect(self._apply_filter)
        header.addWidget(self.filter_combo)
        refresh_btn = PushButton(FluentIcon.SYNC, "刷新")
        refresh_btn.clicked.connect(self.refresh)
        header.addWidget(refresh_btn)
        root.addLayout(header)

        # ── 每日运行时长图表 ──
        chart_card = CardWidget()
        chart_layout = QVBoxLayout(chart_card)
        chart_layout.setContentsMargins(16, 12, 16, 12)
        chart_layout.setSpacing(8)
        chart_layout.addWidget(CaptionLabel("最近 14 天每日运行时长"))
        self.bar_chart = DailyBarChart()
        chart_layout.addWidget(self.bar_chart)
        root.addWidget(chart_card)

        # ── 任务统计表格 ──
        stats_card = CardWidget()
        stats_vbox = QVBoxLayout(stats_card)
        stats_vbox.setContentsMargins(16, 12, 16, 12)
        stats_vbox.setSpacing(8)
        stats_vbox.addWidget(CaptionLabel("任务统计"))
        self.stats_table = TableWidget()
        self.stats_table.setColumnCount(4)
        self.stats_table.setHorizontalHeaderLabels(["任务", "总次数", "成功率", "平均时长"])
        self.stats_table.horizontalHeader().setSectionResizeMode(
            0, HeaderView.ResizeMode.Stretch
        )
        self.stats_table.setEditTriggers(TableWidget.EditTrigger.NoEditTriggers)
        self.stats_table.setAlternatingRowColors(True)
        self.stats_table.setMinimumHeight(160)
        stats_vbox.addWidget(self.stats_table)
        root.addWidget(stats_card)

        # ── 历史表格 ──
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
        self.table.setSortingEnabled(True)
        root.addWidget(self.table)
        self.refresh()

    def refresh(self):
        self._all_records, stats = history.get_records_and_stats()
        self._update_chart()
        self._update_stats(stats)
        self._apply_filter()

    def _update_stats(self, stats=None):
        if stats is None:
            stats = history.get_task_stats()
        stats = stats[:10]
        self.stats_table.setSortingEnabled(False)
        self.stats_table.setRowCount(len(stats))
        for row, s in enumerate(stats):
            total = s["total"]
            success_rate = f"{s['success'] / total * 100:.0f}%" if total else "—"
            self.stats_table.setItem(row, 0, QTableWidgetItem(s["task"]))
            self.stats_table.setItem(row, 1, QTableWidgetItem(str(total)))
            self.stats_table.setItem(row, 2, QTableWidgetItem(success_rate))
            self.stats_table.setItem(row, 3, QTableWidgetItem(format_duration(s["avg_sec"])))
        self.stats_table.setSortingEnabled(True)

    def _update_chart(self):
        """统计最近 14 天每日运行总时长"""
        daily: dict[str, int] = defaultdict(int)
        for rec in self._all_records:
            date = rec.get("time", "")[:10]  # YYYY-MM-DD
            if date:
                daily[date] += rec.get("duration", 0)

        today = datetime.date.today()
        data = []
        for i in range(13, -1, -1):
            d = today - datetime.timedelta(days=i)
            key = d.strftime("%Y-%m-%d")
            label = d.strftime("%m/%d")
            data.append((label, daily.get(key, 0)))

        self.bar_chart.set_data(data)

    def _apply_filter(self):
        idx = self.filter_combo.currentIndex()
        _, status_filter = self._FILTER_OPTIONS[idx]
        if status_filter is None:
            records = self._all_records
        else:
            records = [r for r in self._all_records if r.get("status") == status_filter]

        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(records))
        for row, rec in enumerate(records):
            status_key = rec.get("status", "")
            status_label = self.STATUS_TEXT.get(status_key, status_key)
            secs = rec.get("duration", 0)
            self.table.setItem(row, 0, QTableWidgetItem(rec.get("time", "")))
            self.table.setItem(row, 1, QTableWidgetItem(rec.get("task", "")))
            self.table.setItem(row, 2, QTableWidgetItem(status_label))
            self.table.setItem(row, 3, QTableWidgetItem(format_duration(secs)))
        self.table.setSortingEnabled(True)


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
        self.launcher.notify.connect(self._show_tray_message)
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
