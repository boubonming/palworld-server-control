"""Route registration grouped by web domain."""

from controller.web.routes.auth import register_auth_routes
from controller.web.routes.app_settings import register_app_settings_routes
from controller.web.routes.discord import register_discord_routes
from controller.web.routes.server import register_server_routes
from controller.web.routes.settings import register_settings_routes
from controller.web.routes.world_saves import register_world_save_routes

__all__ = [
    "register_auth_routes",
    "register_app_settings_routes",
    "register_discord_routes",
    "register_server_routes",
    "register_settings_routes",
    "register_world_save_routes",
]
