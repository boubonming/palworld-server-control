import hmac
import re
import secrets

from flask import (
    Flask,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from core import api_client, config_manager
from core.setting_categories import SETTING_CATEGORIES
from core.setting_metadata import get_setting_tooltip
from shared.status import ServerState


def _display_name(key):
    return re.sub(r"(?<!^)(?=[A-Z])", " ", key).replace("b ", "")


def _csrf_token():
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token


def create_web_app(runtime):
    app = Flask(__name__)
    app.secret_key = config_manager.CONFIG["web_secret_key"]
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Strict",
        MAX_CONTENT_LENGTH=2 * 1024 * 1024,
    )
    app.jinja_env.globals["csrf_token"] = _csrf_token

    @app.before_request
    def require_authentication():
        if request.endpoint in {"login", "static"}:
            return None
        if not session.get("authenticated"):
            return redirect(url_for("login", next=request.path))
        if request.method == "POST":
            supplied = request.form.get("_csrf_token", "")
            expected = session.get("_csrf_token", "")
            if not expected or not hmac.compare_digest(supplied, expected):
                abort(400, "Invalid form token.")
        return None

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            password_hash = config_manager.CONFIG.get("web_password_hash", "")
            if password_hash and check_password_hash(password_hash, request.form.get("password", "")):
                session.clear()
                session["authenticated"] = True
                next_path = request.args.get("next", "")
                return redirect(
                    next_path if next_path.startswith("/") and not next_path.startswith("//")
                    else url_for("dashboard")
                )
            flash("Incorrect password.", "error")
        return render_template("login.html")

    @app.post("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.get("/")
    def dashboard():
        configured = (
            config_manager.CONFIG.get("server_backend") == "socket_proxy"
            and config_manager.CONFIG.get("socket_proxy_configured", False)
        )
        running = config_manager.is_server_process_running() if configured else False
        return render_template(
            "dashboard.html",
            configured=configured,
            running=running,
            activity=runtime.activity()[:12],
            config=config_manager.CONFIG,
        )

    @app.get("/api/status")
    def status_api():
        configured = (
            config_manager.CONFIG.get("server_backend") == "socket_proxy"
            and config_manager.CONFIG.get("socket_proxy_configured", False)
        )
        running = config_manager.is_server_process_running() if configured else False
        return jsonify(
            configured=configured,
            state=ServerState.RUNNING.value if running else ServerState.STOPPED.value,
        )

    @app.post("/server/<action>")
    def server_action(action):
        try:
            if action == "start":
                changed = config_manager.start_server()
                runtime.record("Server start requested from web")
                flash("Server start requested." if changed else "Server is already running.")
            elif action == "stop":
                changed = config_manager.stop_server()
                config_manager.clear_server_launch_source()
                runtime.record("Graceful server stop requested from web")
                flash("Server stopped safely." if changed else "Server is already stopped.")
            else:
                abort(404)
        except Exception as exc:
            runtime.record(f"Server {action} failed: {exc}")
            flash(str(exc), "error")
        return redirect(url_for("dashboard"))

    @app.post("/announce")
    def announce():
        message = request.form.get("message", "").strip()
        if not message:
            flash("Enter an announcement.", "error")
        elif not config_manager.is_server_process_running():
            flash("Start the server before sending an announcement.", "error")
        else:
            try:
                api_client.announce_message(message)
                runtime.record("Announcement sent from web")
                flash("Announcement sent.")
            except Exception as exc:
                flash(f"Announcement failed: {exc}", "error")
        return redirect(url_for("dashboard"))

    @app.route("/setup", methods=["GET", "POST"])
    def setup():
        if request.method == "POST":
            try:
                config_manager.configure_socket_proxy_backend(
                    request.form.get("proxy_url", "http://socket-proxy:2375"),
                    request.form.get("container_name", "palworld-server"),
                    request.form.get(
                        "palworld_ini_path",
                        "/palworld-config/PalWorldSettings.ini",
                    ),
                    request.form.get("palworld_api_host", "palworld-server"),
                )
                flash("Socket Proxy connection and mounted Palworld settings verified.")
                runtime.record("Docker Socket Proxy backend configured")
                return redirect(url_for("dashboard"))
            except (OSError, RuntimeError, ValueError) as exc:
                flash(f"Setup failed: {exc}", "error")
        return render_template("setup.html", config=config_manager.CONFIG)

    @app.route("/settings", methods=["GET", "POST"])
    def settings():
        if not config_manager.CONFIG.get("socket_proxy_configured", False):
            flash("Configure Docker Socket Proxy before editing server settings.", "error")
            return redirect(url_for("setup"))
        if request.method == "POST":
            updates = {
                key.removeprefix("setting__"): value
                for key, value in request.form.items()
                if key.startswith("setting__")
            }
            try:
                config_manager.update_palworld_ini_settings(updates)
                runtime.record(f"Updated {len(updates)} Palworld settings")
                flash("Settings saved. They will be applied on the next container start.")
            except Exception as exc:
                flash(str(exc), "error")
            return redirect(url_for("settings"))

        values = config_manager.get_palworld_editor_settings()
        groups = {}
        for key, value in values.items():
            category = SETTING_CATEGORIES.get(key)
            category_name = category.value if category else "Other"
            groups.setdefault(category_name, []).append({
                "key": key,
                "name": _display_name(key),
                "value": value,
                "description": get_setting_tooltip(key),
                "secret": "password" in key.lower(),
            })
        for items in groups.values():
            items.sort(key=lambda item: item["name"].lower())
        return render_template(
            "settings.html",
            groups=sorted(groups.items()),
            running=config_manager.is_server_process_running(),
            backup_exists=bool(config_manager.get_palworld_backup_path()),
        )

    @app.post("/settings/revert")
    def revert_settings():
        try:
            config_manager.revert_to_palworld_backup()
            runtime.record("Reverted container environment settings backup")
            flash("Settings reverted. They will be applied at the next start.")
        except Exception as exc:
            flash(str(exc), "error")
        return redirect(url_for("settings"))

    @app.route("/controller", methods=["GET", "POST"])
    def controller_settings():
        if request.method == "POST":
            config_manager.CONFIG["discord_bot_token"] = request.form.get(
                "discord_bot_token", ""
            ).strip()
            config_manager.CONFIG["palworld_channel_ids"] = [
                value.strip()
                for value in request.form.get("palworld_channel_ids", "").split(",")
                if value.strip()
            ]
            config_manager.set_discord_bot_auto_start(
                request.form.get("discord_bot_auto_start") == "on"
            )
            config_manager.set_auto_shutdown_enabled(
                request.form.get("auto_shutdown_enabled") == "on"
            )
            config_manager.set_auto_shutdown_empty_minutes(
                request.form.get("auto_shutdown_empty_minutes", 5)
            )
            new_password = request.form.get("new_web_password", "")
            if new_password:
                if len(new_password) < 10:
                    flash("The web password must be at least 10 characters.", "error")
                    return redirect(url_for("controller_settings"))
                config_manager.CONFIG["web_password_hash"] = generate_password_hash(new_password)
            config_manager.save_config()
            runtime.record("Controller configuration updated from web")
            flash("Controller settings saved. Restart the controller to apply Discord changes.")
            return redirect(url_for("controller_settings"))
        return render_template("controller.html", config=config_manager.CONFIG)

    @app.get("/activity")
    def activity():
        return render_template("activity.html", activity=runtime.activity())

    return app
