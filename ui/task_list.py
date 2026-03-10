from PySide6.QtWidgets import QWidget, QVBoxLayout, QFrame
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

    def _insert_card(self, card: TaskCard, index: int):
        """将卡片插入布局的指定位置（0-based，不含底部 add_btn + stretch）"""
        card.changed.connect(self.changed)
        card.remove_requested.connect(self.remove_card)
        card.move_up_requested.connect(self._move_up)
        card.move_down_requested.connect(self._move_down)
        self._cards.insert(index, card)
        # 布局顺序：[card0, card1, ..., add_btn, stretch]
        self._layout.insertWidget(index, card)

    def _rebuild_layout(self):
        """把所有卡片按 _cards 列表顺序重新放入布局"""
        for card in self._cards:
            self._layout.removeWidget(card)
        for i, card in enumerate(self._cards):
            self._layout.insertWidget(i, card)

    # ── 公开 API ─────────────────────────────────────────────

    def add_task(self, config: TaskConfig | None = None) -> TaskCard:
        if config is None:
            config = TaskConfig(name=f"任务 {len(self._cards) + 1}")
        card = TaskCard(config)
        self._insert_card(card, len(self._cards))
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
            self._rebuild_layout()
            self.changed.emit()

    def _move_down(self, card: TaskCard):
        i = self._cards.index(card)
        if i < len(self._cards) - 1:
            self._cards[i], self._cards[i + 1] = self._cards[i + 1], self._cards[i]
            self._rebuild_layout()
            self.changed.emit()

    def load_tasks(self, task_configs: list[TaskConfig]):
        for card in list(self._cards):
            self.remove_card(card)
        for config in task_configs:
            self.add_task(config)

    def get_tasks(self) -> list[TaskConfig]:
        return [c.task for c in self._cards]

    def get_cards(self) -> list[TaskCard]:
        return list(self._cards)

    def reset_all_status(self):
        for card in self._cards:
            card.set_status("idle")
