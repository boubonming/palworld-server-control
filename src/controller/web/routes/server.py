"""Server lifecycle, setup, announcement, and activity endpoints."""

from flask import abort, flash, jsonify, redirect, render_template, request, url_for

from core import api_client, config_manager, server_readiness
from shared.status import ServerState, ServerStatus


def _runtime_flag(runtime, method_name):
    method = getattr(runtime, method_name, None)
    if not callable(method):
        return False
    return method() is True


def _display_status(runtime, configured):
    if not configured:
        return None
    if _runtime_flag(runtime, "is_server_stop_in_progress"):
        return ServerStatus(ServerState.STOPPING)
    return server_readiness.get_status()


def _socket_proxy_configured():
    return (
        config_manager.CONFIG.get("server_backend") == "socket_proxy"
        and config_manager.CONFIG.get("socket_proxy_configured", False)
    )


def register_server_routes(app, runtime):
    @app.get("/")
    def dashboard():
        configured = _socket_proxy_configured()
        server_status = _display_status(runtime, configured)
        return render_template(
            "dashboard.html",
            configured=configured,
            running=(
                server_status is not None
                and server_status.state is ServerState.RUNNING
            ),
            server_status=server_status,
            activity=runtime.activity()[:12],
            config=config_manager.CONFIG,
        )

    @app.get("/api/status")
    def status_api():
        configured = _socket_proxy_configured()
        server_status = _display_status(runtime, configured)
        stop_error = None
        error_getter = getattr(runtime, "server_stop_error", None)
        if callable(error_getter):
            candidate = error_getter()
            if isinstance(candidate, str):
                stop_error = candidate
        return jsonify(
            configured=configured,
            state=(
                server_status.state.value
                if server_status is not None
                else ServerState.STOPPED.value
            ),
            display=server_status.display if server_status is not None else "Stopped",
            stop_error=stop_error,
        )

    @app.get("/api/server/logs")
    def server_logs_api():
        try:
            tail = request.args.get("tail", 200, type=int)
            backend = config_manager.get_server_backend()
            if not hasattr(backend, "logs"):
                raise RuntimeError("Container logs are unavailable for this backend.")
            return jsonify(logs=backend.logs(tail=tail))
        except Exception as exc:
            return jsonify(error=str(exc)), 502

    @app.post("/server/<action>")
    def server_action(action):
        try:
            if action == "start":
                changed = config_manager.start_server()
                runtime.record("Server start requested from web")
                if changed:
                    runtime.monitor_server_startup()
                flash(
                    "Server start requested."
                    if changed
                    else "Server is already running."
                )
            elif action == "stop":
                if not config_manager.is_server_process_running():
                    flash("Server is already stopped.")
                elif runtime.request_server_stop():
                    runtime.record("Graceful server stop requested from web")
                    flash("Saving and stopping the server.")
                else:
                    flash("Server stop is already in progress.")
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
                flash(
                    "Socket Proxy connection and mounted Palworld settings verified."
                )
                runtime.record("Docker Socket Proxy backend configured")
                return redirect(url_for("dashboard"))
            except (OSError, RuntimeError, ValueError) as exc:
                flash(f"Setup failed: {exc}", "error")
        return render_template("setup.html", config=config_manager.CONFIG)
