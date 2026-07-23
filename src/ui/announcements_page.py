import threading
import urllib.error

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPlainTextEdit, QPushButton

from core import api_client, config_manager
from shared.status import ServerState
from ui.page import Page


class AnnouncementsPage(Page):
    announcement_finished = Signal(bool, str)

    def __init__(self):
        super().__init__("Announcements", "Send a message to players on the server")
        self._server_running = config_manager.is_server_process_running()
        self._sending = False

        self.availability = QLabel()
        self.content_layout.addWidget(self.availability)

        self.content_layout.addWidget(QLabel("Announcement message"))
        self.message = QPlainTextEdit()
        self.message.setPlaceholderText("Type the message players will see in-game...")
        self.message.textChanged.connect(self._update_send_button)
        self.content_layout.addWidget(self.message)

        actions = QHBoxLayout()
        self.send_button = QPushButton("Send announcement")
        self.send_button.clicked.connect(self.send_announcement)
        actions.addWidget(self.send_button)
        self.feedback = QLabel()
        self.feedback.setWordWrap(True)
        actions.addWidget(self.feedback, 1)
        self.content_layout.addLayout(actions)

        self.announcement_finished.connect(self._finish_announcement)
        self._update_availability()
        self._update_send_button()

    def handle_server_status(self, status):
        self._server_running = status.state is ServerState.RUNNING
        self._update_availability()
        self._update_send_button()

    def send_announcement(self):
        text = self.message.toPlainText().strip()
        if not text or self._sending:
            return
        if not config_manager.is_server_process_running():
            self._server_running = False
            self._update_availability()
            self._update_send_button()
            return

        self._sending = True
        self.feedback.setText("Sending...")
        self._update_send_button()
        threading.Thread(
            target=self._send_announcement_request,
            args=(text,),
            daemon=True,
        ).start()

    def _send_announcement_request(self, text):
        try:
            status = api_client.announce_message(text)
            if status == 200:
                self.announcement_finished.emit(True, "Announcement sent.")
            else:
                self.announcement_finished.emit(
                    False, f"Server returned an unexpected status ({status})."
                )
        except urllib.error.HTTPError as exc:
            if exc.code == 400:
                message = "The server rejected the announcement."
            elif exc.code == 401:
                message = "The server rejected the configured API credentials."
            else:
                message = f"The server returned an error ({exc.code})."
            self.announcement_finished.emit(False, message)
        except urllib.error.URLError:
            self.announcement_finished.emit(False, "Could not reach the server API.")
        except Exception as exc:
            self.announcement_finished.emit(False, f"Failed to send announcement: {exc}")

    def _finish_announcement(self, succeeded, message):
        self._sending = False
        self.feedback.setText(message)
        if succeeded:
            self.message.clear()
        self._update_send_button()

    def _update_availability(self):
        if self._server_running:
            self.availability.setText("Server is online and ready for announcements.")
        else:
            self.availability.setText(
                "The server is offline. Start it before sending an announcement."
            )

    def _update_send_button(self):
        has_message = bool(self.message.toPlainText().strip())
        self.send_button.setEnabled(
            self._server_running and has_message and not self._sending
        )
