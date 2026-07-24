"""Qt adapters for toolkit-neutral runtime events."""

from PySide6.QtCore import QObject, Signal

from core.auto_shutdown_monitor import AutoShutdownMonitor
from integrations import discord_bot


class DiscordSignalBridge(QObject):
    status_changed = Signal(object)
    bot_status_changed = Signal(str)
    discord_activity = Signal(str)
    discord_channel_info = Signal(str, str)

    def __init__(self):
        super().__init__()
        discord_bot.signals.status_changed.connect(self.status_changed.emit)
        discord_bot.signals.bot_status_changed.connect(self.bot_status_changed.emit)
        discord_bot.signals.discord_activity.connect(self.discord_activity.emit)
        discord_bot.signals.discord_channel_info.connect(
            self.discord_channel_info.emit
        )


class QtAutoShutdownMonitor(QObject):
    status_changed = Signal(object)
    idle_shutdown = Signal(int, object)

    def __init__(self, interval_seconds=60, parent=None):
        super().__init__(parent)
        self._monitor = AutoShutdownMonitor(interval_seconds)
        self._monitor.status_changed.connect(self.status_changed.emit)
        self._monitor.idle_shutdown.connect(self.idle_shutdown.emit)

    @property
    def is_running(self):
        return self._monitor.is_running

    def start(self):
        return self._monitor.start()

    def stop(self):
        return self._monitor.stop()


discord_signals = DiscordSignalBridge()
