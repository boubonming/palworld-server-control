"""Backward-compatible page exports."""

from ui.app_settings_page import AppSettingsPage
from ui.announcements_page import AnnouncementsPage
from ui.discord_page import DiscordPage
from ui.server_settings_page import ServerSettingsPage
from ui.server_status_page import ServerStatusPage

__all__ = [
    "AppSettingsPage",
    "AnnouncementsPage",
    "DiscordPage",
    "ServerSettingsPage",
    "ServerStatusPage",
]
