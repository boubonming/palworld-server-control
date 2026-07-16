"""Backward-compatible page exports."""

from ui.app_settings_page import AppSettingsPage
from ui.discord_page import DiscordPage
from ui.server_settings_page import ServerSettingsPage
from ui.server_status_page import ServerStatusPage

__all__ = [
    "AppSettingsPage",
    "DiscordPage",
    "ServerSettingsPage",
    "ServerStatusPage",
]
