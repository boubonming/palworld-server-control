from datetime import datetime
import urllib.error

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPlainTextEdit, QPushButton

from core import config_manager
from ui.page import Page
from shared.status import ServerState, ServerStatus, status_stylesheet


class ServerStatusPage(Page):
    status_changed = Signal(object)

    def __init__(self):
        super().__init__("Palworld Server", "Monitor and manage the local server")
        self.status_label = QLabel("Checking server status...")
        self.status_label.setObjectName("statusValue")
        self.content_layout.addWidget(self.status_label)

        actions = QHBoxLayout()
        self.start_button = QPushButton("Start")
        self.start_button.setEnabled(False)
        self.start_button.clicked.connect(self.start_server)
        self.stop_button = QPushButton("Stop")
        self.stop_button.setEnabled(False)
        self.stop_button.setObjectName("destructiveAction")
        self.stop_button.clicked.connect(self.stop_server)
        actions.addWidget(self.start_button)
        actions.addWidget(self.stop_button)
        actions.addStretch()
        self.content_layout.addLayout(actions)

        self.directory_label = QLabel()
        self.directory_label.setWordWrap(True)
        self.content_layout.addWidget(self.directory_label)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(1000)
        self.log.setPlaceholderText("Server activity will appear here.")
        self.content_layout.addWidget(self.log)
        self._last_logged_status = None
        self._status_updated_at = None
        self._current_status = None
        self._process_poll_timer = QTimer(self)
        self._process_poll_timer.setInterval(250)
        self._process_poll_timer.timeout.connect(self._poll_process_state)
        self.refresh(log_status=False)

    def refresh(self, log_status=False):
        directory = config_manager.CONFIG.get("palworld_dir", "Not configured")
        self.directory_label.setText(f"Server directory:\n{directory}")
        state = ServerState.RUNNING if config_manager.is_server_process_running() else ServerState.STOPPED
        self.update_status(ServerStatus(state), log_status=log_status)

    def update_status(self, status, log_status=True):
        status_changed = status.display != self._last_logged_status
        if status_changed or self._status_updated_at is None:
            self._status_updated_at = datetime.now()
        timestamp = self._status_updated_at.strftime("%Y-%m-%d %H:%M:%S")
        self.status_label.setText(f"Server status: {status.display} ({timestamp})")
        self.status_label.setStyleSheet(status_stylesheet(status))
        self.start_button.setEnabled(status.state is ServerState.STOPPED)
        self.stop_button.setEnabled(status.state is ServerState.RUNNING)
        if log_status and status_changed:
            self.log.appendPlainText(f"[{timestamp}] {status.display}")
        self._last_logged_status = status.display
        self._current_status = status
        self.status_changed.emit(status)

    def start_server(self):
        try:
            if config_manager.start_server():
                self.update_status(ServerStatus(ServerState.STARTING))
                self.log.appendPlainText("Server start requested")
                self._process_poll_timer.start()
            else:
                self.update_status(ServerStatus(ServerState.RUNNING))
                self.log.appendPlainText("Server is already running")
        except Exception as exc:
            self.update_status(ServerStatus(ServerState.STOPPED))
            self.log.appendPlainText(f"Failed to start server: {exc}")

    def stop_server(self):
        try:
            if config_manager.stop_server():
                config_manager.clear_server_launch_source()
                self.update_status(ServerStatus(ServerState.STOPPING))
                self.log.appendPlainText("Server shutdown requested")
                self._process_poll_timer.start()
            else:
                self.update_status(ServerStatus(ServerState.STOPPED))
                self.log.appendPlainText("Server is already stopped")
        except urllib.error.URLError:
            self._process_poll_timer.stop()
            self.update_status(ServerStatus(ServerState.RUNNING))
            self.log.appendPlainText("Failed to stop server: server API unavailable")
        except Exception as exc:
            self._process_poll_timer.stop()
            self.update_status(ServerStatus(ServerState.RUNNING))
            self.log.appendPlainText(f"Failed to stop server: {exc}")

    def _poll_process_state(self):
        if self._current_status is None:
            return

        running = config_manager.is_server_process_running()
        if self._current_status.state is ServerState.STARTING and running:
            self._process_poll_timer.stop()
            self.update_status(ServerStatus(ServerState.RUNNING))
        elif self._current_status.state is ServerState.STOPPING and not running:
            self._process_poll_timer.stop()
            self.update_status(ServerStatus(ServerState.STOPPED))
