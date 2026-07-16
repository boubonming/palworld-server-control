"""Application-owned monitor for Palworld idle shutdowns."""

import threading

from PySide6.QtCore import QObject, Signal

from core import api_client, config_manager
from shared.status import ServerState, ServerStatus


class AutoShutdownMonitor(QObject):
    """Polls Palworld independently of Discord and shuts down idle servers."""

    status_changed = Signal(object)
    idle_shutdown = Signal(int, object)

    def __init__(self, interval_seconds=60, parent=None):
        super().__init__(parent)
        self.interval_seconds = interval_seconds
        self.empty_minutes_counter = 0
        self._server_was_running = False
        self._server_process_id = None
        self._session_launch_source = None
        self._stop_event = threading.Event()
        self._thread = None

    @property
    def is_running(self):
        return self._thread is not None and self._thread.is_alive()

    def start(self):
        if self.is_running:
            return False
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="palworld-auto-shutdown",
            daemon=True,
        )
        self._thread.start()
        return True

    def stop(self):
        thread = self._thread
        if thread is None:
            return False
        self._stop_event.set()
        if thread is not threading.current_thread():
            thread.join(timeout=2)
        self._thread = None
        return True

    def _run(self):
        while not self._stop_event.wait(self.interval_seconds):
            self.check_once()

    def check_once(self):
        process_id = config_manager.get_server_process_id()
        if process_id is None:
            self.empty_minutes_counter = 0
            if self._server_was_running:
                self._server_was_running = False
                self._server_process_id = None
                self._session_launch_source = None
                config_manager.clear_server_launch_source()
                self.status_changed.emit(ServerStatus(ServerState.STOPPED))
            return

        if process_id != self._server_process_id:
            self.empty_minutes_counter = 0
            self._server_process_id = process_id
            self._session_launch_source = config_manager.get_server_launch_source()
        self._server_was_running = True

        try:
            data = api_client.call_palworld_api("players", method="GET")
            current_players = len(data.get("players", [])) if isinstance(data, dict) else 0
            max_players = 32

            if current_players > 0:
                self.empty_minutes_counter = 0
                self.status_changed.emit(
                    ServerStatus(ServerState.RUNNING, f"Running ({current_players}/{max_players})")
                )
                return

            self.empty_minutes_counter += 1
            self.status_changed.emit(ServerStatus(ServerState.RUNNING, "Running (0 Players)"))
            shutdown_minutes = config_manager.get_auto_shutdown_empty_minutes()
            if self.empty_minutes_counter < shutdown_minutes:
                return

            api_client.call_palworld_api("save")
            api_client.call_palworld_api(
                "shutdown",
                payload={"waittime": 5, "message": "Inactivity shutdown"},
            )
            self.empty_minutes_counter = 0
            self._server_was_running = False
            self.status_changed.emit(ServerStatus(ServerState.STOPPED))
            self.idle_shutdown.emit(shutdown_minutes, self._session_launch_source)
        except Exception:
            # A temporary API failure should not stop the monitor thread.
            pass
