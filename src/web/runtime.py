from collections import deque
from datetime import datetime
import threading

from core import config_manager, server_readiness
from core.auto_shutdown_monitor import AutoShutdownMonitor
from integrations import discord_bot


class HeadlessRuntime:
    """Owns the always-on monitor, Discord bot, and recent activity."""

    def __init__(self):
        self._activity = deque(maxlen=300)
        self._activity_lock = threading.Lock()
        self._discord_status = "Discord bot is stopped"
        self._discord_channels = {}
        self._startup_thread = None
        self._stop_event = threading.Event()
        self.monitor = AutoShutdownMonitor()
        self.monitor.status_changed.connect(discord_bot.update_server_presence)
        self.monitor.idle_shutdown.connect(discord_bot.notify_idle_shutdown)
        self.monitor.status_changed.connect(
            lambda status: self.record(f"Server status: {status.display}")
        )
        discord_bot.signals.bot_status_changed.connect(self._record_discord_status)
        discord_bot.signals.discord_activity.connect(self.record)
        discord_bot.signals.discord_channel_info.connect(self._record_discord_channel)

    def record(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._activity_lock:
            self._activity.appendleft(f"[{timestamp}] {message}")

    def activity(self):
        with self._activity_lock:
            return list(self._activity)

    def _record_discord_status(self, message):
        self._discord_status = str(message)
        self.record(message)

    def _record_discord_channel(self, channel_id, label):
        self._discord_channels[str(channel_id)] = str(label)

    def discord_status(self):
        return self._discord_status

    def discord_channels(self):
        return dict(self._discord_channels)

    def monitor_server_startup(self):
        if self._startup_thread is not None and self._startup_thread.is_alive():
            return False
        self._startup_thread = threading.Thread(
            target=self._wait_for_server_startup,
            name="palworld-startup-health",
            daemon=True,
        )
        self._startup_thread.start()
        return True

    def _wait_for_server_startup(self):
        try:
            status = server_readiness.wait_until_ready(stop_event=self._stop_event)
            self.record("Server started and Docker health is ready")
            self.monitor.status_changed.emit(status)
        except Exception as exc:
            if not self._stop_event.is_set():
                self.record(f"Server startup failed: {exc}")

    def start(self):
        self._stop_event.clear()
        self.record("Linux controller started")
        self.monitor.start()
        if config_manager.get_discord_bot_auto_start():
            discord_bot.run_discord_bot(
                config_manager.CONFIG.get("discord_bot_token", "")
            )

    def stop(self):
        self._stop_event.set()
        self.monitor.stop()
        discord_bot.discord_manager.stop()
