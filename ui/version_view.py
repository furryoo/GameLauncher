import os
import subprocess
import sys
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout
from PySide6.QtWidgets import QApplication
from qfluentwidgets import (
    SubtitleLabel, PrimaryPushButton, PushButton, BodyLabel,
    CaptionLabel, CardWidget, ComboBox, InfoBar, InfoBarPosition,
    FluentIcon, StrongBodyLabel,
)
from core.updater import UpdateWorker, current_version, is_frozen


class VersionInterface(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("versionInterface")
        self.worker: UpdateWorker | None = None
        self._setup_ui()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 16, 24, 16)
        root.setSpacing(16)
        root.addWidget(SubtitleLabel("版本管理"))

        # ── 当前版本 ──────────────────────────────────────────
        cur_card = CardWidget()
        cur_row = QHBoxLayout(cur_card)
        cur_row.setContentsMargins(16, 12, 16, 12)
        cur_row.addWidget(StrongBodyLabel("当前版本:"))
        self.current_label = BodyLabel(current_version())
        cur_row.addWidget(self.current_label)
        cur_row.addStretch()
        root.addWidget(cur_card)

        # ── 更新到最新 ────────────────────────────────────────
        update_card = CardWidget()
        update_row = QHBoxLayout(update_card)
        update_row.setContentsMargins(16, 12, 16, 12)
        update_row.setSpacing(12)
        hint = "从 GitHub Releases 下载" if is_frozen() else "从 main 分支拉取最新代码"
        self.status_label = CaptionLabel(hint)
        update_row.addWidget(self.status_label)
        update_row.addStretch()
        self.update_btn = PrimaryPushButton(FluentIcon.UPDATE, "更新到最新")
        self.update_btn.clicked.connect(self._do_update)
        update_row.addWidget(self.update_btn)
        root.addWidget(update_card)

        # ── 切换到指定版本 ────────────────────────────────────
        switch_card = CardWidget()
        switch_row = QHBoxLayout(switch_card)
        switch_row.setContentsMargins(16, 12, 16, 12)
        switch_row.setSpacing(12)
        switch_row.addWidget(BodyLabel("切换版本:"))
        self.version_combo = ComboBox()
        self.version_combo.setMinimumWidth(180)
        self.version_combo.addItem("加载中...")
        switch_row.addWidget(self.version_combo)
        refresh_btn = PushButton(FluentIcon.SYNC, "刷新列表")
        refresh_btn.clicked.connect(self._do_fetch)
        switch_row.addWidget(refresh_btn)
        switch_row.addStretch()
        self.switch_btn = PushButton(FluentIcon.RETURN, "切换")
        self.switch_btn.clicked.connect(self._do_switch)
        switch_row.addWidget(self.switch_btn)
        root.addWidget(switch_card)

        # ── 重启提示（操作成功后显示）────────────────────────
        self.restart_card = CardWidget()
        restart_row = QHBoxLayout(self.restart_card)
        restart_row.setContentsMargins(16, 12, 16, 12)
        restart_row.setSpacing(12)
        restart_row.addWidget(BodyLabel("版本已切换，重启后生效"))
        restart_row.addStretch()
        restart_btn = PrimaryPushButton(FluentIcon.POWER_BUTTON, "立即重启")
        restart_btn.clicked.connect(self._restart)
        restart_row.addWidget(restart_btn)
        self.restart_card.hide()
        root.addWidget(self.restart_card)

        root.addStretch()

        # 启动时自动刷新版本列表
        self._do_fetch()

    # ── 操作 ─────────────────────────────────────────────────

    def _do_fetch(self):
        self._start_worker("fetch")

    def _do_update(self):
        self._start_worker("update")

    def _do_switch(self):
        ver = self.version_combo.currentText()
        if ver and ver != "加载中...":
            self._start_worker("switch", ver)

    def _start_worker(self, action: str, version: str = ""):
        if self.worker and self.worker.isRunning():
            return
        self.worker = UpdateWorker(action, version)
        self.worker.status.connect(self.status_label.setText)
        self.worker.versions_ready.connect(self._on_versions_ready)
        self.worker.done.connect(self._on_done)
        self.worker.start()
        self.update_btn.setEnabled(False)
        self.switch_btn.setEnabled(False)

    # ── 信号处理 ─────────────────────────────────────────────

    def _on_versions_ready(self, versions: list):
        self.version_combo.clear()
        self.version_combo.addItems(versions)

    def _on_done(self, success: bool, message: str):
        self.update_btn.setEnabled(True)
        self.switch_btn.setEnabled(True)
        self.status_label.setText(message)
        self.current_label.setText(current_version())
        if success and "重启" in message:
            self.restart_card.show()
        if success:
            InfoBar.success("成功", message, parent=self, position=InfoBarPosition.TOP)
        else:
            InfoBar.error("失败", message, parent=self, position=InfoBarPosition.TOP)

    def _restart(self):
        if is_frozen():
            bat = os.path.join(os.environ.get("TEMP", ""), "gl_updater.bat")
            subprocess.Popen(["cmd", "/c", bat], creationflags=subprocess.DETACHED_PROCESS)
            QApplication.instance().quit()
            return
        if sys.platform == "win32":
            import ctypes
            ctypes.windll.shell32.ShellExecuteW(
                None, "runas", sys.executable, " ".join(sys.argv), None, 1
            )
        else:
            subprocess.Popen([sys.executable] + sys.argv)
        QApplication.instance().quit()
