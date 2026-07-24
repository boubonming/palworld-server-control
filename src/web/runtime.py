from collections import deque
from datetime import datetime
import threading

from core import config_manager
from core.auto_shutdown_monitor import AutoShutdownMonitor
from integrations import discord_bot


class HeadlessRuntime:
    """Owns the always-on monitor, Discord bot, and recent activity."""

    def __init__(self):
        self._activity = deque(maxlen=300)
        self._activity_lock = threading.Lock()
        self.monitor = AutoShutdownMonitor()
        self.monitor.status_changed.connect(discord_bot.update_server_presence)
        self.monitor.idle_shutdown.connect(discord_bot.notify_idle_shutdown)
        self.monitor.status_changed.connect(
            lambda status: self.record(f"Server status: {status.display}")
        )
        discord_bot.signals.bot_status_changed.connect(self.record)
        discord_bot.signals.discord_activity.connect(self.record)

    def record(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._activity_lock:
            self._activity.appendleft(f"[{timestamp}] {message}")

    def activity(self):
        with self._activity_lock:
            return list(self._activity)

    def start(self):
        self.record("Linux controller started")
        self.monitor.start()
        if config_manager.get_discord_bot_auto_start():
            discord_bot.run_discord_bot(
                config_manager.CONFIG.get("discord_bot_token", "")
            )

    def stop(self):
        self.monitor.stop()
        discord_bot.discord_manager.stop()

