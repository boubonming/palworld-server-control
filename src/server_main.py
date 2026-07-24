"""Headless Linux controller and private-network web interface."""

import argparse
import getpass
import os
import secrets
import signal
import sys
import threading

from PySide6.QtCore import QCoreApplication
from waitress import serve
from werkzeug.security import generate_password_hash

from core import config_manager
from web.app import create_web_app
from web.runtime import HeadlessRuntime


def _arguments():
    parser = argparse.ArgumentParser(description="Palworld Linux controller")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", default=8080, type=int)
    parser.add_argument("--web-password")
    return parser.parse_args()


def _ensure_web_credentials(config, supplied_password=None):
    previous_backend = config.get("server_backend")
    password = supplied_password or os.environ.get("PALWORLD_CONTROL_WEB_PASSWORD")
    if password:
        if len(password) < 10:
            raise ValueError("The web password must be at least 10 characters.")
        config["web_password_hash"] = generate_password_hash(password)
    elif not config.get("web_password_hash"):
        if not sys.stdin.isatty():
            raise RuntimeError(
                "Set PALWORLD_CONTROL_WEB_PASSWORD or pass --web-password on first launch."
            )
        password = getpass.getpass("Create web interface password (10+ characters): ")
        if len(password) < 10:
            raise ValueError("The web password must be at least 10 characters.")
        config["web_password_hash"] = generate_password_hash(password)
    config.setdefault("web_secret_key", secrets.token_urlsafe(48))
    if config.get("palworld_api_host", "127.0.0.1") == "127.0.0.1":
        config["palworld_api_host"] = "palworld-server"
    if previous_backend != "socket_proxy":
        config["palworld_ini_path"] = "/palworld-config/PalWorldSettings.ini"
    config["server_backend"] = "socket_proxy"
    config_manager.save_config()


def main():
    args = _arguments()
    config = config_manager.load_config()
    _ensure_web_credentials(config, args.web_password)

    qt_app = QCoreApplication(sys.argv)
    runtime = HeadlessRuntime()
    web_app = create_web_app(runtime)
    runtime.start()

    server_thread = threading.Thread(
        target=serve,
        kwargs={
            "app": web_app,
            "host": args.host,
            "port": args.port,
            "threads": 8,
        },
        name="palworld-web",
        daemon=True,
    )
    server_thread.start()
    runtime.record(f"Web interface listening on {args.host}:{args.port}")

    signal.signal(signal.SIGINT, lambda *_args: qt_app.quit())
    signal.signal(signal.SIGTERM, lambda *_args: qt_app.quit())
    exit_code = qt_app.exec()
    runtime.stop()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
