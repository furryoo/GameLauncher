from PySide6.QtWidgets import QWidget, QVBoxLayout, QScrollArea, QAbstractItemView
from PySide6.QtCore import Qt, Signal, QMimeData, QPoint
from PySide6.QtGui import QDrag
from qfluentwidgets import PrimaryPushButton, FluentIcon

from core.config import TaskConfig
from ui.task_card import TaskCard


class DraggableTaskList(QWidget):
    """支持拖拽排序的任务列表"""
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cards: list[TaskCard] = []
        self._drag_start_pos: QPoint | None = None
        self._dragging_card: TaskCard | None = None

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(8)
        self._layout.addStretch()

        add_btn = PrimaryPushButton(FluentIcon.ADD, "添加任务")
        add_btn.clicked.connect(self.add_task)
        self._layout.addWidget(add_btn)

    def add_task(self, config: TaskConfig | None = None):
        if config is None:
            config = TaskConfig(name=f"任务 {len(self._cards) + 1}")
        card = TaskCard(config)
        card.changed.connect(self.changed)
        card.remove_requested.connect(self.remove_card)
        self._cards.append(card)
        # 在 stretch 和按钮之前插入
        insert_pos = self._layout.count() - 2
        self._layout.insertWidget(insert_pos, card)
        self.changed.emit()
        return card

    def remove_card(self, card: TaskCard):
        self._cards.remove(card)
        self._layout.removeWidget(card)
        card.deleteLater()
        self.changed.emit()

    def get_tasks(self) -> list[TaskConfig]:
        return [c.task for c in self._cards]

    def load_tasks(self, task_configs: list[TaskConfig]):
        for card in list(self._cards):
            self.remove_card(card)
        for config in task_configs:
            self.add_task(config)

    def get_cards(self) -> list[TaskCard]:
        return self._cards

    def reset_all_status(self):
        for card in self._cards:
            card.set_status("idle")
