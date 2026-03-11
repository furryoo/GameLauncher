from PySide6.QtWidgets import QWidget, QVBoxLayout
from PySide6.QtCore import Signal
from qfluentwidgets import PrimaryPushButton, FluentIcon

from core.config import TaskConfig
from ui.task_card import TaskCard


class DraggableTaskList(QWidget):
    """任务列表，支持通过 ▲▼ 按钮调整顺序"""
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cards: list[TaskCard] = []

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(8)

        add_btn = PrimaryPushButton(FluentIcon.ADD, "添加任务")
        add_btn.clicked.connect(lambda: self.add_task())
        self._layout.addWidget(add_btn)
        self._layout.addStretch()

    # ── 内部工具 ────────────────────────────────────────────

    def _connect_card(self, card: TaskCard):
        card.changed.connect(self.changed)
        card.remove_requested.connect(self.remove_card)
        card.move_up_requested.connect(self._move_up)
        card.move_down_requested.connect(self._move_down)

    # ── 公开 API ─────────────────────────────────────────────

    def add_task(self, config: TaskConfig | None = None) -> TaskCard:
        if config is None:
            config = TaskConfig(name=f"任务 {len(self._cards) + 1}")
        card = TaskCard(config)
        self._connect_card(card)
        idx = len(self._cards)
        self._cards.append(card)
        self._layout.insertWidget(idx, card)
        self.changed.emit()
        return card

    def remove_card(self, card: TaskCard):
        if card in self._cards:
            self._cards.remove(card)
            self._layout.removeWidget(card)
            card.deleteLater()
            self.changed.emit()

    def _move_up(self, card: TaskCard):
        i = self._cards.index(card)
        if i > 0:
            self._cards[i], self._cards[i - 1] = self._cards[i - 1], self._cards[i]
            self._layout.insertWidget(i - 1, card)   # Qt 自动从旧位置移除再插入
            self.changed.emit()

    def _move_down(self, card: TaskCard):
        i = self._cards.index(card)
        if i < len(self._cards) - 1:
            self._cards[i], self._cards[i + 1] = self._cards[i + 1], self._cards[i]
            self._layout.insertWidget(i + 1, card)
            self.changed.emit()

    def _clear(self):
        """静默清空所有卡片，不触发 changed 信号"""
        for card in self._cards:
            self._layout.removeWidget(card)
            card.deleteLater()
        self._cards.clear()

    def load_tasks(self, task_configs: list[TaskConfig]):
        self._clear()
        for config in task_configs:
            self.add_task(config)

    def get_tasks(self) -> list[TaskConfig]:
        return [c.task for c in self._cards]

    def get_cards(self) -> list[TaskCard]:
        return list(self._cards)

    def get_card_by_name(self, name: str) -> TaskCard | None:
        return next((c for c in self._cards if c.task.name == name), None)

    def reset_all_status(self):
        for card in self._cards:
            card.set_status("idle")
