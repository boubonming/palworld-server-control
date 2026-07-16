import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QWidget,
)

from core import config_manager
from ui.page import Page


class AppSettingsPage(Page):
    def __init__(self):
        super().__init__("App Settings", "Configure the manager application")
        form = QFormLayout()
        self.directory = QLineEdit(config_manager.CONFIG.get("palworld_dir", ""))
        form.addRow("Palworld directory", self.directory)

        self.close_behavior = QCheckBox("Minimize to system tray when exit")
        self.close_behavior.setChecked(config_manager.get_gui_close_behavior() == "minimize")
        self.close_behavior.toggled.connect(self.save_close_behavior)
        form.addRow("Close behavior", self.close_behavior)

        self.auto_start = QCheckBox("Autostart in background")
        self.auto_start.setChecked(config_manager.get_auto_start())
        self.auto_start.toggled.connect(self.save_auto_start)
        form.addRow("Startup behavior", self.auto_start)

        self.auto_shutdown_minutes = QSpinBox()
        self.auto_shutdown_minutes.setRange(
            config_manager.MIN_AUTO_SHUTDOWN_EMPTY_MINUTES,
            config_manager.MAX_AUTO_SHUTDOWN_EMPTY_MINUTES,
        )
        self.auto_shutdown_minutes.setFixedWidth(96)
        self.auto_shutdown_minutes.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.auto_shutdown_minutes.lineEdit().setValidator(
            QIntValidator(
                config_manager.MIN_AUTO_SHUTDOWN_EMPTY_MINUTES,
                config_manager.MAX_AUTO_SHUTDOWN_EMPTY_MINUTES,
                self.auto_shutdown_minutes,
            )
        )
        self.auto_shutdown_minutes.setValue(config_manager.get_auto_shutdown_empty_minutes())

        auto_shutdown_control = QWidget()
        auto_shutdown_layout = QHBoxLayout(auto_shutdown_control)
        auto_shutdown_layout.setContentsMargins(0, 0, 0, 0)
        auto_shutdown_layout.setSpacing(8)
        auto_shutdown_layout.addWidget(self.auto_shutdown_minutes)
        auto_shutdown_layout.addWidget(QLabel("minutes"))
        auto_shutdown_layout.addStretch()
        form.addRow("Auto-stop after empty", auto_shutdown_control)

        self.content_layout.addLayout(form)
        save = QPushButton("Save manager settings")
        save.clicked.connect(self.save_manager_settings)
        self.content_layout.addWidget(save)
        self.feedback = QLabel()
        self.content_layout.addWidget(self.feedback)
        self.content_layout.addStretch()

    def save_close_behavior(self, minimize):
        config_manager.set_gui_close_behavior("minimize" if minimize else "exit")

    def save_auto_start(self, enabled):
        if not config_manager.set_auto_start(enabled):
            self.auto_start.blockSignals(True)
            self.auto_start.setChecked(not enabled)
            self.auto_start.blockSignals(False)
            self.feedback.setText("Could not update Windows startup settings.")

    def save_manager_settings(self):
        config_manager.update_paths_from_dir(os.path.normpath(self.directory.text()))
        config_manager.set_auto_shutdown_empty_minutes(self.auto_shutdown_minutes.value())
        self.feedback.setText("Manager settings saved.")
