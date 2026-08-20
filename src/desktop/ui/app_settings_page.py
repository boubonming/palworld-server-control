import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QWidget,
)

from core import config_manager
from desktop.ui.page import Page


class AppSettingsPage(Page):
    def __init__(self):
        super().__init__("App Settings", "Configure the manager application")
        form = QFormLayout()
        container_backend = config_manager.is_container_backend()
        directory_value = (
            config_manager.CONFIG.get("docker_compose_dir", "")
            if config_manager.is_docker_backend()
            else config_manager.CONFIG.get("palworld_dir", "")
        )
        self.directory = QLineEdit(directory_value)
        self.directory.setReadOnly(container_backend)
        if not container_backend:
            self.directory.editingFinished.connect(self.save_directory)
        form.addRow(
            "Compose directory" if config_manager.is_docker_backend() else "Palworld directory",
            self.directory,
        )

        self.close_behavior = QCheckBox("Minimize to system tray when exit")
        self.close_behavior.setChecked(config_manager.get_gui_close_behavior() == "minimize")
        self.close_behavior.toggled.connect(self.save_close_behavior)
        form.addRow("Close behavior", self.close_behavior)

        self.auto_start = QCheckBox("Autostart in background")
        self.auto_start.setChecked(config_manager.get_auto_start())
        self.auto_start.toggled.connect(self.save_auto_start)
        if sys.platform == "win32":
            form.addRow("Startup behavior", self.auto_start)

        self.silent_server_launch = QCheckBox(
            "Run silently by bypassing the PalServer.exe wrapper"
        )
        self.silent_server_launch.setChecked(config_manager.get_silent_server_launch())
        self.silent_server_launch.toggled.connect(self.save_silent_server_launch)
        native_windows = (
            sys.platform == "win32" and not config_manager.is_container_backend()
        )
        if native_windows:
            form.addRow("Server launch", self.silent_server_launch)

        self.silent_launch_warning = QLabel(
            "Warning: Silent mode launches PalServer's internal executable directly. "
            "Disable it after a Palworld update if the server no longer starts correctly."
        )
        self.silent_launch_warning.setWordWrap(True)
        self.silent_launch_warning.setStyleSheet("color: #f0ad4e;")
        self.silent_launch_warning.setVisible(self.silent_server_launch.isChecked())
        if native_windows:
            form.addRow("", self.silent_launch_warning)

        self.auto_shutdown_enabled = QCheckBox("Enable idle shutdown")
        self.auto_shutdown_enabled.setChecked(config_manager.get_auto_shutdown_enabled())

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
        self.auto_shutdown_minutes.setEnabled(self.auto_shutdown_enabled.isChecked())
        self.auto_shutdown_enabled.toggled.connect(self.auto_shutdown_minutes.setEnabled)
        self.auto_shutdown_enabled.toggled.connect(self.save_auto_shutdown_enabled)
        self.auto_shutdown_minutes.valueChanged.connect(self.save_auto_shutdown_minutes)

        auto_shutdown_control = QWidget()
        auto_shutdown_layout = QHBoxLayout(auto_shutdown_control)
        auto_shutdown_layout.setContentsMargins(0, 0, 0, 0)
        auto_shutdown_layout.setSpacing(8)
        auto_shutdown_layout.addWidget(self.auto_shutdown_enabled)
        auto_shutdown_layout.addWidget(QLabel("after"))
        auto_shutdown_layout.addWidget(self.auto_shutdown_minutes)
        auto_shutdown_layout.addWidget(QLabel("empty minutes"))
        auto_shutdown_layout.addStretch()
        form.addRow("Idle shutdown", auto_shutdown_control)

        self.auto_backup_enabled = QCheckBox("Enable changed-only backups")
        self.auto_backup_enabled.setChecked(config_manager.get_auto_backup_enabled())

        self.auto_backup_minutes = QSpinBox()
        self.auto_backup_minutes.setRange(
            config_manager.MIN_AUTO_BACKUP_INTERVAL_MINUTES,
            config_manager.MAX_AUTO_BACKUP_INTERVAL_MINUTES,
        )
        self.auto_backup_minutes.setValue(
            config_manager.get_auto_backup_interval_minutes()
        )
        self.auto_backup_minutes.setFixedWidth(96)

        self.auto_backup_retention = QSpinBox()
        self.auto_backup_retention.setRange(
            config_manager.MIN_AUTO_BACKUP_RETENTION_COUNT,
            config_manager.MAX_AUTO_BACKUP_RETENTION_COUNT,
        )
        self.auto_backup_retention.setValue(
            config_manager.get_auto_backup_retention_count()
        )
        self.auto_backup_retention.setFixedWidth(72)

        backup_control = QWidget()
        backup_layout = QHBoxLayout(backup_control)
        backup_layout.setContentsMargins(0, 0, 0, 0)
        backup_layout.setSpacing(8)
        backup_layout.addWidget(self.auto_backup_enabled)
        backup_layout.addWidget(QLabel("every"))
        backup_layout.addWidget(self.auto_backup_minutes)
        backup_layout.addWidget(QLabel("minutes; keep"))
        backup_layout.addWidget(self.auto_backup_retention)
        backup_layout.addWidget(QLabel("changed backups"))
        backup_layout.addStretch()
        form.addRow("Automatic backups", backup_control)

        self.auto_backup_directory = QLineEdit(
            config_manager.get_auto_backup_directory()
        )
        self.auto_backup_directory.setPlaceholderText(
            "Default: Pal/Saved/Backups/PalworldServerControl"
        )
        self.auto_backup_directory.editingFinished.connect(
            self.save_auto_backup_directory
        )
        self.auto_backup_browse = QPushButton("Browse…")
        self.auto_backup_browse.setObjectName("secondaryAction")
        self.auto_backup_browse.clicked.connect(self.browse_auto_backup_directory)

        backup_directory_control = QWidget()
        backup_directory_layout = QHBoxLayout(backup_directory_control)
        backup_directory_layout.setContentsMargins(0, 0, 0, 0)
        backup_directory_layout.setSpacing(8)
        backup_directory_layout.addWidget(self.auto_backup_directory, 1)
        backup_directory_layout.addWidget(self.auto_backup_browse)
        form.addRow("Backup location", backup_directory_control)

        for control in (
            self.auto_backup_minutes,
            self.auto_backup_retention,
            self.auto_backup_directory,
            self.auto_backup_browse,
        ):
            control.setEnabled(self.auto_backup_enabled.isChecked())
            self.auto_backup_enabled.toggled.connect(control.setEnabled)
        self.auto_backup_enabled.toggled.connect(self.save_auto_backup_enabled)
        self.auto_backup_minutes.valueChanged.connect(
            self.save_auto_backup_interval
        )
        self.auto_backup_retention.valueChanged.connect(
            self.save_auto_backup_retention
        )

        self.content_layout.addLayout(form)
        self.content_layout.addStretch()

    def save_close_behavior(self, minimize):
        config_manager.set_gui_close_behavior("minimize" if minimize else "exit")

    def save_auto_start(self, enabled):
        if not config_manager.set_auto_start(enabled):
            self.auto_start.blockSignals(True)
            self.auto_start.setChecked(not enabled)
            self.auto_start.blockSignals(False)
            QMessageBox.warning(
                self,
                "Startup Setting",
                "Could not update Windows startup settings.",
            )

    def save_silent_server_launch(self, enabled):
        config_manager.set_silent_server_launch(enabled)
        self.silent_launch_warning.setVisible(enabled)

    def save_directory(self):
        config_manager.update_paths_from_dir(os.path.normpath(self.directory.text()))

    def save_auto_shutdown_enabled(self, enabled):
        config_manager.set_auto_shutdown_enabled(enabled)

    def save_auto_shutdown_minutes(self, minutes):
        config_manager.set_auto_shutdown_empty_minutes(minutes)

    def save_auto_backup_enabled(self, enabled):
        config_manager.set_auto_backup_enabled(enabled)

    def save_auto_backup_interval(self, minutes):
        config_manager.set_auto_backup_interval_minutes(minutes)

    def save_auto_backup_retention(self, count):
        config_manager.set_auto_backup_retention_count(count)

    def save_auto_backup_directory(self):
        config_manager.set_auto_backup_directory(
            os.path.normpath(self.auto_backup_directory.text())
            if self.auto_backup_directory.text().strip()
            else ""
        )
        self.auto_backup_directory.setText(
            config_manager.get_auto_backup_directory()
        )

    def browse_auto_backup_directory(self):
        selected = QFileDialog.getExistingDirectory(
            self,
            "Select Backup Location",
            self.auto_backup_directory.text()
            or config_manager.get_auto_backup_directory()
            or config_manager.CONFIG.get("palworld_dir", ""),
        )
        if selected:
            self.auto_backup_directory.setText(selected)
            self.save_auto_backup_directory()
