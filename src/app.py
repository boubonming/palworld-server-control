import os
import sys
import tempfile

from PySide6.QtCore import QLockFile
from PySide6.QtWidgets import (
    QApplication,
    QMenu,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QStyle

from core import config_manager
from core.auto_shutdown_monitor import AutoShutdownMonitor
from integrations import discord_bot
from ui.pages import AppSettingsPage, DiscordPage, ServerSettingsPage, ServerStatusPage
from shared.status import ServerState, ServerStatus


def get_app_icon_path():
    base_dir = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(__file__)))
    return os.path.join(base_dir, "assets", "app_icon.ico")


def acquire_single_instance_lock():
    lock_path = os.path.join(tempfile.gettempdir(), "palworld-server-manager.lock")
    lock = QLockFile(lock_path)
    if not lock.tryLock(100):
        return None
    return lock


class PalworldFolderDialog(QDialog):
    def __init__(self, initial_dir="", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Set Palworld folder")
        self.setModal(True)
        self.resize(520, 160)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "Select the Palworld server folder containing PalServer.exe to continue."
        ))

        path_layout = QHBoxLayout()
        self.path = QLineEdit(initial_dir)
        self.path.setPlaceholderText("Path to your Palworld server folder")
        path_layout.addWidget(self.path)
        browse = QPushButton("Browse...")
        browse.clicked.connect(self.browse)
        path_layout.addWidget(browse)
        layout.addLayout(path_layout)

        self.error = QLabel()
        self.error.setStyleSheet("color: #ff6b6b;")
        self.error.setWordWrap(True)
        layout.addWidget(self.error)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def browse(self):
        chosen_dir = QFileDialog.getExistingDirectory(
            self, "Select Palworld server folder", self.path.text().strip()
        )
        if chosen_dir:
            self.path.setText(chosen_dir)

    def validate_and_accept(self):
        chosen_dir = os.path.normpath(self.path.text().strip())
        if not os.path.isdir(chosen_dir):
            self.error.setText("Select an existing folder.")
            return
        if not os.path.isfile(os.path.join(chosen_dir, "PalServer.exe")):
            self.error.setText("That folder does not contain PalServer.exe.")
            return
        self.path.setText(chosen_dir)
        self.accept()

    def selected_dir(self):
        return self.path.text().strip()


def ensure_palworld_folder(config):
    configured_dir = config.get("palworld_dir", "")
    if os.path.isdir(configured_dir) and os.path.isfile(os.path.join(configured_dir, "PalServer.exe")):
        return True

    dialog = PalworldFolderDialog(configured_dir)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return False
    config_manager.update_paths_from_dir(dialog.selected_dir())
    return True


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._exit_requested = False
        self.setWindowTitle("Palworld Server Manager")
        self.setWindowIcon(QIcon(get_app_icon_path()))
        self.resize(1200, 800)

        self.navigation = QListWidget()
        self.navigation.setFixedWidth(180)
        self.navigation.addItems(["Server Status", "Server Settings", "Discord", "App Settings"])

        self.pages = QStackedWidget()
        self.server_status = ServerStatusPage()
        self.server_settings = ServerSettingsPage()
        self.discord = DiscordPage()
        self.app_settings = AppSettingsPage()
        self.auto_shutdown_monitor = AutoShutdownMonitor(parent=self)
        self.auto_shutdown_monitor.status_changed.connect(self.server_status.update_status)
        self.auto_shutdown_monitor.status_changed.connect(self.server_settings.handle_server_status)
        self.auto_shutdown_monitor.idle_shutdown.connect(discord_bot.notify_idle_shutdown)
        self.server_status.status_changed.connect(discord_bot.update_server_presence)
        self.auto_shutdown_monitor.start()
        for page in (self.server_status, self.server_settings, self.discord, self.app_settings):
            self.pages.addWidget(page)
        self.navigation.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.server_settings.saved.connect(self.server_status.refresh)
        discord_bot.signals.bot_status_changed.connect(self._finish_exit)

        shell = QWidget()
        layout = QHBoxLayout(shell)
        layout.addWidget(self.navigation)
        layout.addWidget(self.pages, 1)
        self.setCentralWidget(shell)
        self.navigation.setCurrentRow(0)
        discord_bot.signals.status_changed.connect(self.server_status.update_status)
        discord_bot.signals.status_changed.connect(self.server_settings.handle_server_status)

        self.setStyleSheet("""
            QMainWindow, QWidget { background: #1f2024; color: #eeeeee; }
            QListWidget { background: #292a2f; border: 0; padding: 8px; }
            QListWidget::item { padding: 12px 8px; color: #a7a7ad; }
            QListWidget::item:selected { background: #3a3b42; color: #ffffff; border-radius: 4px; }
            QLineEdit, QComboBox, QPlainTextEdit { background: #2b2c31; border: 1px solid #44454d; border-radius: 6px; padding: 8px; color: #eeeeee; }
            QToolButton { background: #2b2c31; border: 0; border-radius: 6px; padding: 10px; text-align: left; font-weight: 600; color: #ffffff; }
            QToolButton:hover { background: #36373e; }
            QToolButton#passwordToggle { background: transparent; border: 0; padding: 0; color: #a7c7ff; font-size: 11px; }
            QToolButton#passwordToggle:hover { color: #ffffff; }
            QPushButton { background: #3e7bfa; border: 0; border-radius: 6px; padding: 9px 16px; color: white; }
            QPushButton:hover { background: #5790ff; }
            QPushButton#secondaryAction { background: #2b2c31; border: 1px solid #555761; color: #eeeeee; }
            QPushButton#secondaryAction:hover { background: #36373e; border-color: #70727d; }
            QPushButton#destructiveAction { background: #a63d4a; color: white; }
            QPushButton#destructiveAction:hover { background: #c24d5b; }
            QPushButton#destructiveAction:disabled { background: #3a3b42; color: #777981; }
            QPushButton:disabled { background: #3a3b42; color: #777981; }
            #pageTitle { font-size: 25px; font-weight: 600; }
            #pageSubtitle { color: #9c9da5; padding-bottom: 10px; }
            #statusValue { font-size: 18px; padding: 12px 0; }
        """)
        self.setup_system_tray()

    def setup_system_tray(self):
        self.tray_icon = None
        self.tray_available = QSystemTrayIcon.isSystemTrayAvailable()
        if not self.tray_available:
            return

        icon = QIcon(get_app_icon_path())
        if icon.isNull():
            icon = self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)

        self.tray_icon = QSystemTrayIcon(icon, self)
        self.tray_icon.setToolTip("Palworld Server Manager")
        self.tray_icon.activated.connect(self.handle_tray_activation)

        menu = QMenu(self)
        open_action = QAction("Open", self)
        open_action.triggered.connect(self.restore_from_tray)
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.exit_application)
        menu.addAction(open_action)
        menu.addSeparator()
        menu.addAction(exit_action)
        self.tray_icon.setContextMenu(menu)
        self.tray_icon.show()

    def handle_tray_activation(self, reason):
        if reason in {
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        }:
            self.restore_from_tray()

    def restore_from_tray(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh_server_state()

    def refresh_server_state(self):
        running = config_manager.is_server_process_running()
        status = ServerStatus(ServerState.RUNNING if running else ServerState.STOPPED)
        self.server_status.update_status(status, log_status=False)
        self.server_settings.handle_server_status(status)

    def exit_application(self):
        self._exit_requested = True
        if self.tray_icon:
            self.tray_icon.hide()
        self.close()

    def _finish_exit(self, status):
        if self._exit_requested and status == "Discord bot stopped":
            self.close()

    def closeEvent(self, event):
        if (
            config_manager.get_gui_close_behavior() == "minimize"
            and not self._exit_requested
            and not self.isMinimized()
        ):
            event.ignore()
            if self.tray_available:
                self.hide()
            else:
                self.showMinimized()
            return
        if self.tray_icon:
            self.tray_icon.hide()
        self.auto_shutdown_monitor.stop()
        config_manager.shutdown_server_for_exit()
        if discord_bot.discord_manager.state != "stopped":
            self._exit_requested = True
            discord_bot.discord_manager.stop()
            event.ignore()
            return
        event.accept()


def main():
    config = config_manager.load_config()
    config_manager.ensure_auto_start_registration()
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(get_app_icon_path()))
    instance_lock = acquire_single_instance_lock()
    if instance_lock is None:
        QMessageBox.information(
            None,
            "Palworld Server Manager",
            "Palworld Server Manager is already running.",
        )
        sys.exit(0)
    if not ensure_palworld_folder(config):
        sys.exit(0)
    window = MainWindow()
    if "--background" in sys.argv:
        if window.tray_available:
            window.hide()
        else:
            window.showMinimized()
    else:
        window.show()
    if config_manager.get_discord_bot_auto_start():
        discord_bot.run_discord_bot(config.get("discord_bot_token"))
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
