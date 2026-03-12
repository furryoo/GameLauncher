import os
from contextlib import suppress
from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QFileDialog
from PySide6.QtCore import Signal, QTimer, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QPainter, QColor
from qfluentwidgets import (
    CardWidget, LineEdit, PushButton, BodyLabel, CaptionLabel,
    SpinBox, SwitchButton, ToolButton, FluentIcon, ComboBox,
    IndeterminateProgressBar,
)
from core.enums import CardStatus, RunIf
from ui.theme import (
    COLOR_SUCCESS, COLOR_INFO, COLOR_ERROR,
    COLOR_SUCCESS_CARD_BG, COLOR_INFO_CARD_BG, COLOR_ERROR_CARD_BG,
)

_RUN_IF_OPTIONS = [RunIf.ALWAYS, RunIf.PREV_SUCCESS, RunIf.PREV_FAIL]
_RUN_IF_LABELS  = ["总是运行", "前置成功才运行", "前置失败才运行"]

HEIGHT_COLLAPSED = 88
HEIGHT_EXPANDED  = 275


class TaskCard(CardWidget):
    changed = Signal()
    remove_requested    = Signal(object)
    move_up_requested   = Signal(object)
    move_down_requested = Signal(object)
    clone_requested     = Signal(object)
    run_requested       = Signal(object)

    def __init__(self, task_config, parent=None):
        super().__init__(parent)
        self.task = task_config
        self._path_timer = QTimer(self)
        self._path_timer.setSingleShot(True)
        self._path_timer.setInterval(300)
        self._path_timer.timeout.connect(self._validate_path)
        self._expanded = True
        self._overlay_color: QColor | None = None
        self._anim = QPropertyAnimation(self, b"maximumHeight")
        self._anim.setDuration(200)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._setup_ui()
        self._load_from_config()

    def _setup_ui(self):
        self.setMaximumHeight(HEIGHT_EXPANDED)
        self.setMinimumHeight(HEIGHT_COLLAPSED)
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 10, 16, 10)
        root.setSpacing(6)

        # ── 顶部行：名称 + 状态 + 启用 + 克隆 + 排序 + 删除 + 折叠 ──
        top = QHBoxLayout()
        self.name_edit = LineEdit()
        self.name_edit.setPlaceholderText("任务名称")
        self.name_edit.setFixedWidth(160)
        self.name_edit.textChanged.connect(self._on_changed)

        self.status_label = CaptionLabel("等待中")
        self.enable_switch = SwitchButton()
        self.enable_switch.checkedChanged.connect(self._on_changed)

        clone_btn = ToolButton(FluentIcon.COPY)
        clone_btn.setToolTip("克隆任务")
        clone_btn.setFixedSize(28, 28)
        clone_btn.clicked.connect(lambda: self.clone_requested.emit(self))

        up_btn = ToolButton(FluentIcon.UP)
        up_btn.setToolTip("上移")
        up_btn.setFixedSize(28, 28)
        up_btn.clicked.connect(lambda: self.move_up_requested.emit(self))

        down_btn = ToolButton(FluentIcon.DOWN)
        down_btn.setToolTip("下移")
        down_btn.setFixedSize(28, 28)
        down_btn.clicked.connect(lambda: self.move_down_requested.emit(self))

        del_btn = ToolButton(FluentIcon.DELETE)
        del_btn.setToolTip("删除")
        del_btn.setFixedSize(28, 28)
        del_btn.clicked.connect(lambda: self.remove_requested.emit(self))

        self.run_btn = ToolButton(FluentIcon.PLAY)
        self.run_btn.setToolTip("单独运行此任务")
        self.run_btn.setFixedSize(28, 28)
        self.run_btn.clicked.connect(lambda: self.run_requested.emit(self))

        self.expand_btn = ToolButton(FluentIcon.CHEVRON_UP)
        self.expand_btn.setFixedSize(28, 28)
        self.expand_btn.setToolTip("折叠/展开")
        self.expand_btn.clicked.connect(self._toggle_expand)

        top.addWidget(self.name_edit)
        top.addWidget(self.status_label)
        top.addStretch()
        top.addWidget(CaptionLabel("启用"))
        top.addWidget(self.enable_switch)
        top.addWidget(self.run_btn)
        top.addWidget(clone_btn)
        top.addWidget(up_btn)
        top.addWidget(down_btn)
        top.addWidget(del_btn)
        top.addWidget(self.expand_btn)

        # ── 路径行 ──
        path_row = QHBoxLayout()
        self.path_edit = LineEdit()
        self.path_edit.setPlaceholderText("程序路径（.exe），支持 %USERPROFILE% 等环境变量")
        self.path_edit.textChanged.connect(self._on_path_changed)
        browse_btn = PushButton("浏览")
        browse_btn.setFixedWidth(64)
        browse_btn.clicked.connect(self._browse)
        path_row.addWidget(BodyLabel("路径:"))
        path_row.addWidget(self.path_edit)
        path_row.addWidget(browse_btn)

        # ── 详情区（可折叠）──
        self._detail_widget = QWidget()
        detail_vbox = QVBoxLayout(self._detail_widget)
        detail_vbox.setContentsMargins(0, 0, 0, 0)
        detail_vbox.setSpacing(6)

        # 超时 + 运行时间行
        timeout_row = QHBoxLayout()
        self.timeout_spin = SpinBox()
        self.timeout_spin.setRange(0, 86400)
        self.timeout_spin.setSuffix(" 秒  (0=不限制)")
        self.timeout_spin.setFixedWidth(200)
        self.timeout_spin.valueChanged.connect(self._on_changed)
        self.elapsed_label = CaptionLabel("运行时间: --")
        timeout_row.addWidget(BodyLabel("超时:"))
        timeout_row.addWidget(self.timeout_spin)
        timeout_row.addStretch()
        timeout_row.addWidget(self.elapsed_label)

        # 重试 + 延迟行
        extra_row = QHBoxLayout()
        self.retry_spin = SpinBox()
        self.retry_spin.setRange(0, 5)
        self.retry_spin.setSuffix(" 次")
        self.retry_spin.setFixedWidth(90)
        self.retry_spin.setToolTip("异常退出后自动重试次数（0=不重试）")
        self.retry_spin.valueChanged.connect(self._on_changed)

        self.delay_spin = SpinBox()
        self.delay_spin.setRange(0, 300)
        self.delay_spin.setSuffix(" 秒")
        self.delay_spin.setFixedWidth(90)
        self.delay_spin.setToolTip("上一个任务结束后，等待多少秒再启动本任务")
        self.delay_spin.valueChanged.connect(self._on_changed)

        extra_row.addWidget(BodyLabel("失败重试:"))
        extra_row.addWidget(self.retry_spin)
        extra_row.addSpacing(16)
        extra_row.addWidget(BodyLabel("启动延迟:"))
        extra_row.addWidget(self.delay_spin)
        extra_row.addStretch()

        # 前置条件行
        cond_row = QHBoxLayout()
        self.run_if_combo = ComboBox()
        self.run_if_combo.addItems(_RUN_IF_LABELS)
        self.run_if_combo.setFixedWidth(140)
        self.run_if_combo.setToolTip("本任务的前置运行条件（基于上一个任务的结果）")
        self.run_if_combo.currentIndexChanged.connect(self._on_changed)
        cond_row.addWidget(BodyLabel("前置条件:"))
        cond_row.addWidget(self.run_if_combo)
        cond_row.addStretch()

        # 备注行
        self.notes_edit = LineEdit()
        self.notes_edit.setPlaceholderText("备注（可选）")
        font = self.notes_edit.font()
        font.setPointSize(font.pointSize() - 1)
        self.notes_edit.setFont(font)
        self.notes_edit.textChanged.connect(self._on_notes_changed)

        detail_vbox.addLayout(timeout_row)
        detail_vbox.addLayout(extra_row)
        detail_vbox.addLayout(cond_row)
        detail_vbox.addWidget(self.notes_edit)

        # 进度条（运行时可见）
        self.progress_bar = IndeterminateProgressBar()
        self.progress_bar.setVisible(False)

        root.addLayout(top)
        root.addLayout(path_row)
        root.addWidget(self._detail_widget)
        root.addWidget(self.progress_bar)

    def _load_from_config(self):
        self.name_edit.setText(self.task.name)
        self.path_edit.setText(self.task.exe_path)
        self.timeout_spin.setValue(self.task.timeout)
        self.enable_switch.setChecked(self.task.enabled)
        self.retry_spin.setValue(self.task.retry_count)
        self.delay_spin.setValue(self.task.delay_seconds)
        try:
            idx = _RUN_IF_OPTIONS.index(RunIf(self.task.run_if))
        except (ValueError, KeyError):
            idx = 0
        self.run_if_combo.setCurrentIndex(idx)
        self.notes_edit.setText(self.task.notes)
        self._update_run_btn()

    def _on_changed(self):
        self.task.name          = self.name_edit.text()
        self.task.timeout       = self.timeout_spin.value()
        self.task.enabled       = self.enable_switch.isChecked()
        self.task.retry_count   = self.retry_spin.value()
        self.task.delay_seconds = self.delay_spin.value()
        self.task.run_if        = _RUN_IF_OPTIONS[self.run_if_combo.currentIndex()]
        self._update_run_btn()
        self.changed.emit()

    def _on_notes_changed(self, text: str):
        self.task.notes = text
        self.changed.emit()

    def _update_run_btn(self):
        self.run_btn.setEnabled(bool(self.task.enabled and self.task.exe_path))

    def _on_path_changed(self, text):
        self.task.exe_path = text
        self._path_timer.start()
        self.changed.emit()

    def _validate_path(self):
        expanded = os.path.expandvars(self.task.exe_path)
        invalid = bool(self.task.exe_path) and not os.path.isfile(expanded)
        self.path_edit.setStyleSheet(f"border: 1px solid {COLOR_ERROR};" if invalid else "")

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择程序", "", "可执行文件 (*.exe)"
        )
        if path:
            self.path_edit.setText(path)

    def _toggle_expand(self):
        self._set_expanded(not self._expanded)

    def _set_expanded(self, expanded: bool, animated: bool = True):
        if self._expanded == expanded:
            return
        self._expanded = expanded
        self.expand_btn.setIcon(
            FluentIcon.CHEVRON_UP if expanded else FluentIcon.CHEVRON_DOWN
        )
        end = HEIGHT_EXPANDED if expanded else HEIGHT_COLLAPSED
        if animated:
            if expanded:
                self._detail_widget.setVisible(True)
            else:
                self._anim.finished.connect(self._on_collapse_done)
            self._anim.stop()
            self._anim.setStartValue(self.maximumHeight())
            self._anim.setEndValue(end)
            self._anim.start()
        else:
            self.setMaximumHeight(end)
            self._detail_widget.setVisible(expanded)

    def _on_collapse_done(self):
        self._detail_widget.setVisible(False)
        with suppress(RuntimeError):
            self._anim.finished.disconnect(self._on_collapse_done)

    def set_status(self, status: CardStatus | str, elapsed_text: str = ""):
        s = CardStatus(status)
        color_map = {
            CardStatus.IDLE:    ("等待中",    ""),
            CardStatus.RUNNING: ("运行中 ●", COLOR_SUCCESS),
            CardStatus.DONE:    ("已完成 ✓", COLOR_INFO),
            CardStatus.ERROR:   ("出错 ✗",   COLOR_ERROR),
        }
        text, color = color_map.get(s, ("等待中", ""))
        self.status_label.setText(text)
        self.status_label.setStyleSheet(
            f"color: {color}; font-weight: bold;" if color else ""
        )
        if elapsed_text:
            self.elapsed_label.setText(f"运行时间: {elapsed_text}")
        elif s == CardStatus.IDLE:
            self.elapsed_label.setText("运行时间: --")

        # 进度条
        if s == CardStatus.RUNNING:
            self.progress_bar.setVisible(True)
            self.progress_bar.start()
            self._set_expanded(True)
        else:
            self.progress_bar.stop()
            self.progress_bar.setVisible(False)

        # 背景染色
        overlay_map = {
            CardStatus.RUNNING: QColor(COLOR_SUCCESS_CARD_BG),
            CardStatus.DONE:    QColor(COLOR_INFO_CARD_BG),
            CardStatus.ERROR:   QColor(COLOR_ERROR_CARD_BG),
            CardStatus.IDLE:    None,
        }
        self._overlay_color = overlay_map.get(s)
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._overlay_color:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.fillRect(self.rect(), self._overlay_color)
            painter.end()
