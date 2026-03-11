import os
from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QFileDialog
from PySide6.QtCore import Signal, QTimer
from qfluentwidgets import (
    CardWidget, LineEdit, PushButton, BodyLabel, CaptionLabel,
    SpinBox, SwitchButton, ToolButton, FluentIcon,
)
from core.enums import CardStatus


class TaskCard(CardWidget):
    changed = Signal()
    remove_requested = Signal(object)
    move_up_requested = Signal(object)
    move_down_requested = Signal(object)

    def __init__(self, task_config, parent=None):
        super().__init__(parent)
        self.task = task_config
        # 防抖定时器：路径验证 300ms 后触发，避免每次按键都调用 isfile
        self._path_timer = QTimer(self)
        self._path_timer.setSingleShot(True)
        self._path_timer.setInterval(300)
        self._path_timer.timeout.connect(self._validate_path)
        self._setup_ui()
        self._load_from_config()

    def _setup_ui(self):
        self.setFixedHeight(170)
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 10, 16, 10)
        root.setSpacing(8)

        # 顶部行
        top = QHBoxLayout()
        self.name_edit = LineEdit()
        self.name_edit.setPlaceholderText("任务名称")
        self.name_edit.setFixedWidth(160)
        self.name_edit.textChanged.connect(self._on_changed)

        self.status_label = CaptionLabel("等待中")
        self.enable_switch = SwitchButton()
        self.enable_switch.checkedChanged.connect(self._on_changed)

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

        top.addWidget(self.name_edit)
        top.addWidget(self.status_label)
        top.addStretch()
        top.addWidget(CaptionLabel("启用"))
        top.addWidget(self.enable_switch)
        top.addWidget(up_btn)
        top.addWidget(down_btn)
        top.addWidget(del_btn)

        # 路径行
        path_row = QHBoxLayout()
        self.path_edit = LineEdit()
        self.path_edit.setPlaceholderText("程序路径（.exe）")
        self.path_edit.textChanged.connect(self._on_path_changed)

        browse_btn = PushButton("浏览")
        browse_btn.setFixedWidth(64)
        browse_btn.clicked.connect(self._browse)

        path_row.addWidget(BodyLabel("路径:"))
        path_row.addWidget(self.path_edit)
        path_row.addWidget(browse_btn)

        # 超时 + 运行时间行
        bottom = QHBoxLayout()
        self.timeout_spin = SpinBox()
        self.timeout_spin.setRange(0, 86400)
        self.timeout_spin.setSuffix(" 秒  (0=不限制)")
        self.timeout_spin.setFixedWidth(210)
        self.timeout_spin.valueChanged.connect(self._on_changed)
        self.elapsed_label = CaptionLabel("运行时间: --")

        bottom.addWidget(BodyLabel("超时:"))
        bottom.addWidget(self.timeout_spin)
        bottom.addStretch()
        bottom.addWidget(self.elapsed_label)

        root.addLayout(top)
        root.addLayout(path_row)
        root.addLayout(bottom)

    def _load_from_config(self):
        self.name_edit.setText(self.task.name)
        self.path_edit.setText(self.task.exe_path)
        self.timeout_spin.setValue(self.task.timeout)
        self.enable_switch.setChecked(self.task.enabled)

    def _on_changed(self):
        self.task.name = self.name_edit.text()
        self.task.timeout = self.timeout_spin.value()
        self.task.enabled = self.enable_switch.isChecked()
        self.changed.emit()

    def _on_path_changed(self, text):
        self.task.exe_path = text
        self.task.process_name = os.path.basename(text) if text else ""
        self._path_timer.start()   # 防抖：300ms 后验证
        self.changed.emit()

    def _validate_path(self):
        text = self.task.exe_path
        invalid = bool(text) and not os.path.isfile(text)
        self.path_edit.setStyleSheet("border: 1px solid #e74c3c;" if invalid else "")

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择程序", "", "可执行文件 (*.exe)"
        )
        if path:
            self.path_edit.setText(path)

    def set_status(self, status: CardStatus | str, elapsed_text: str = ""):
        color_map = {
            CardStatus.IDLE:    ("等待中",    ""),
            CardStatus.RUNNING: ("运行中 ●", "#2ecc71"),
            CardStatus.DONE:    ("已完成 ✓", "#3498db"),
            CardStatus.ERROR:   ("出错 ✗",   "#e74c3c"),
        }
        text, color = color_map.get(CardStatus(status), ("等待中", ""))
        self.status_label.setText(text)
        self.status_label.setStyleSheet(
            f"color: {color}; font-weight: bold;" if color else ""
        )
        if elapsed_text:
            self.elapsed_label.setText(f"运行时间: {elapsed_text}")
        elif status == CardStatus.IDLE:
            self.elapsed_label.setText("运行时间: --")
