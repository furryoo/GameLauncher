import os
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QFileDialog, QSizePolicy
)
from PySide6.QtCore import Qt, Signal
from qfluentwidgets import (
    CardWidget, LineEdit, PushButton, BodyLabel, CaptionLabel,
    SpinBox, SwitchButton, IconWidget, FluentIcon, ToolButton,
    ComboBox, StrongBodyLabel, InfoBadge, InfoLevel
)


class TaskCard(CardWidget):
    """单个任务卡片，支持拖拽排序"""
    changed = Signal()   # 配置变更时通知保存
    remove_requested = Signal(object)  # 请求删除自身

    def __init__(self, task_config, parent=None):
        super().__init__(parent)
        self.task = task_config
        self._status = "idle"  # idle / running / done / error
        self._setup_ui()
        self._load_from_config()

    def _setup_ui(self):
        self.setFixedHeight(180)
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(10)

        # --- 顶部行：名称 + 状态徽章 + 删除 ---
        top = QHBoxLayout()
        self.name_edit = LineEdit()
        self.name_edit.setPlaceholderText("任务名称")
        self.name_edit.setFixedWidth(160)
        self.name_edit.textChanged.connect(self._on_changed)

        self.status_badge = CaptionLabel("等待中")
        self.status_badge.setObjectName("statusBadge")

        self.enable_switch = SwitchButton()
        self.enable_switch.checkedChanged.connect(self._on_changed)

        self.remove_btn = ToolButton(FluentIcon.DELETE)
        self.remove_btn.setToolTip("删除此任务")
        self.remove_btn.clicked.connect(lambda: self.remove_requested.emit(self))

        top.addWidget(self.name_edit)
        top.addWidget(self.status_badge)
        top.addStretch()
        top.addWidget(CaptionLabel("启用"))
        top.addWidget(self.enable_switch)
        top.addWidget(self.remove_btn)

        # --- 路径行 ---
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

        # --- 超时行 ---
        timeout_row = QHBoxLayout()
        self.timeout_spin = SpinBox()
        self.timeout_spin.setRange(0, 86400)
        self.timeout_spin.setSuffix(" 秒  (0=不限制)")
        self.timeout_spin.setFixedWidth(200)
        self.timeout_spin.valueChanged.connect(self._on_changed)

        timeout_row.addWidget(BodyLabel("超时:"))
        timeout_row.addWidget(self.timeout_spin)
        timeout_row.addStretch()

        # --- 运行时间标签 ---
        self.elapsed_label = CaptionLabel("运行时间: --")

        root.addLayout(top)
        root.addLayout(path_row)
        root.addLayout(timeout_row)
        root.addWidget(self.elapsed_label)

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
        if text:
            self.task.process_name = os.path.basename(text)
        self.changed.emit()

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择程序", "", "可执行文件 (*.exe)"
        )
        if path:
            self.path_edit.setText(path)

    def set_status(self, status: str, elapsed_text: str = ""):
        self._status = status
        labels = {
            "idle":    ("等待中",  ""),
            "running": ("运行中",  "#2ecc71"),
            "done":    ("已完成",  "#3498db"),
            "error":   ("出错",    "#e74c3c"),
        }
        text, color = labels.get(status, ("等待中", ""))
        self.status_badge.setText(text)
        if color:
            self.status_badge.setStyleSheet(f"color: {color}; font-weight: bold;")
        else:
            self.status_badge.setStyleSheet("")
        if elapsed_text:
            self.elapsed_label.setText(f"运行时间: {elapsed_text}")
