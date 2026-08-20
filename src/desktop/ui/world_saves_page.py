from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from core import config_manager
from core.world_saves import get_active_world_id, list_world_saves, select_world_save
from desktop.ui.page import Page
from shared.status import is_active_status


class WorldSavesPage(Page):
    selected = Signal()

    def __init__(self):
        super().__init__("World Saves", "Choose which dedicated-server save loads next")
        self._running = config_manager.is_server_process_running()
        self.current_world = QLabel()
        self.current_world.setObjectName("statusValue")
        self.content_layout.addWidget(self.current_world)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.panel = QWidget()
        self.world_layout = QVBoxLayout(self.panel)
        self.scroll.setWidget(self.panel)
        self.content_layout.addWidget(self.scroll, 1)

        actions = QHBoxLayout()
        self.reload_button = QPushButton("Reload worlds")
        self.reload_button.setObjectName("secondaryAction")
        self.reload_button.clicked.connect(self.reload_worlds)
        actions.addWidget(self.reload_button)
        self.apply_button = QPushButton("Use selected world")
        self.apply_button.clicked.connect(self.apply_selection)
        actions.addWidget(self.apply_button)
        actions.addStretch()
        self.content_layout.addLayout(actions)

        self.world_buttons = QButtonGroup(self)
        self.reload_worlds()

    def reload_worlds(self):
        while self.world_layout.count():
            item = self.world_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.world_buttons.deleteLater()
        self.world_buttons = QButtonGroup(self)
        active_world = get_active_world_id()
        self.current_world.setText(f"Current world: {active_world or 'Not configured'}")
        worlds = list_world_saves()
        for world in worlds:
            button = QRadioButton(
                f"{world['id']}\nLevel.sav updated "
                f"{world['modified_at'].strftime('%Y-%m-%d %H:%M:%S %Z')}"
            )
            button.setProperty("world_id", world["id"])
            button.setChecked(world["active"])
            button.setEnabled(not self._running)
            self.world_buttons.addButton(button)
            self.world_layout.addWidget(button)
        if not worlds:
            self.world_layout.addWidget(
                QLabel(
                    "No world folders containing Level.sav were found under "
                    "SaveGames/0."
                )
            )
        self.world_layout.addStretch()
        self.apply_button.setEnabled(bool(worlds) and not self._running)

    def apply_selection(self):
        button = self.world_buttons.checkedButton()
        if button is None:
            QMessageBox.information(self, "World Saves", "Select a world first.")
            return
        try:
            changed = select_world_save(button.property("world_id"))
        except Exception as exc:
            QMessageBox.critical(self, "World Saves", str(exc))
            return
        QMessageBox.information(
            self,
            "World Saves",
            "Active world changed. It will load on the next server start."
            if changed
            else "That world is already active.",
        )
        self.reload_worlds()
        self.selected.emit()

    def handle_server_status(self, status):
        self._running = is_active_status(status)
        for button in self.world_buttons.buttons():
            button.setEnabled(not self._running)
        self.apply_button.setEnabled(
            bool(self.world_buttons.buttons()) and not self._running
        )
