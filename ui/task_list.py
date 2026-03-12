import copy
import uuid
from PySide6.QtWidgets import QWidget, QVBoxLayout
from PySide6.QtCore import Signal
from qfluentwidgets import PrimaryPushButton, FluentIcon

from core.config import TaskConfig
from core.enums import CardStatus
from ui.task_card import TaskCard


class DraggableTaskList(QWidget):
    """任务列表，支持通过 ▲▼ 按钮调整顺序"""
    changed = Signal()
    run_single = Signal(object)  # emits TaskCard

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
        card.clone_requested.connect(self._clone_card)
        card.run_requested.connect(lambda c=card: self.run_single.emit(c))

    # ── 公开 API ─────────────────────────────────────────────

    def add_task(self, config: TaskConfig | None = None, *, _silent: bool = False) -> TaskCard:
        if config is None:
            config = TaskConfig(name=f"任务 {len(self._cards) + 1}")
        card = TaskCard(config)
        self._connect_card(card)
        self._cards.append(card)
        self._layout.insertWidget(len(self._cards) - 1, card)
        if not _silent:
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

    def _clone_card(self, card: TaskCard):
        i = self._cards.index(card)
        new_config = copy.deepcopy(card.task)
        new_config.id = uuid.uuid4().hex[:12]
        new_config.name = f"{new_config.name} 副本"
        new_card = TaskCard(new_config)
        self._connect_card(new_card)
        insert_pos = i + 1
        self._cards.insert(insert_pos, new_card)
        self._layout.insertWidget(insert_pos, new_card)
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
            self.add_task(config, _silent=True)

    def get_tasks(self) -> list[TaskConfig]:
        return [c.task for c in self._cards]

    def get_cards(self) -> list[TaskCard]:
        return list(self._cards)

    def get_card_by_name(self, name: str) -> TaskCard | None:
        return next((c for c in self._cards if c.task.name == name), None)

    def get_card_by_id(self, task_id: str) -> TaskCard | None:
        return next((c for c in self._cards if c.task.id == task_id), None)

    def reset_all_status(self):
        for card in self._cards:
            card.set_status(CardStatus.IDLE)
