"""Flask application bootstrap and shared request policy."""

import hmac
import secrets

from flask import Flask, abort, redirect, request, session, url_for

from core import config_manager
from web.routes import (
    register_app_settings_routes,
    register_auth_routes,
    register_discord_routes,
    register_server_routes,
    register_settings_routes,
)


def _csrf_token():
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token


def _register_request_policy(app):
    @app.before_request
    def require_authentication():
        if request.endpoint in {"health", "login", "static"}:
            return None
        if not session.get("authenticated"):
            return redirect(url_for("login", next=request.path))
        if request.method == "POST":
            supplied = request.form.get("_csrf_token", "")
            expected = session.get("_csrf_token", "")
            if not expected or not hmac.compare_digest(supplied, expected):
                abort(400, "Invalid form token.")
        return None


def create_web_app(runtime):
    app = Flask(__name__)
    app.secret_key = config_manager.CONFIG["web_secret_key"]
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Strict",
        MAX_CONTENT_LENGTH=2 * 1024 * 1024,
    )
    app.jinja_env.globals["csrf_token"] = _csrf_token

    _register_request_policy(app)
    register_auth_routes(app)
    register_server_routes(app, runtime)
    register_settings_routes(app, runtime)
    register_discord_routes(app, runtime)
    register_app_settings_routes(app, runtime)
    return app
