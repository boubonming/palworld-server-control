"""Route registration grouped by web domain."""

from web.routes.auth import register_auth_routes
from web.routes.controller import register_controller_routes
from web.routes.server import register_server_routes
from web.routes.settings import register_settings_routes

__all__ = [
    "register_auth_routes",
    "register_controller_routes",
    "register_server_routes",
    "register_settings_routes",
]
