"""Controller-wide idle-shutdown and web-access settings."""

import os

from flask import flash, redirect, render_template, request, url_for
from werkzeug.security import generate_password_hash

from core import config_manager
from core.auto_backup import backup_service, get_backup_directory, list_backups


def _format_file_size(size):
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024


def register_app_settings_routes(app, runtime):
    @app.route("/app-settings", methods=["GET", "POST"])
    def app_settings():
        if request.method == "POST":
            new_password = request.form.get("new_web_password", "")
            if new_password and len(new_password) < 10:
                flash("The web password must be at least 10 characters.", "error")
                return redirect(url_for("app_settings"))

            config_manager.set_auto_shutdown_enabled(
                request.form.get("auto_shutdown_enabled") == "on"
            )
            config_manager.set_auto_shutdown_empty_minutes(
                request.form.get("auto_shutdown_empty_minutes", 5)
            )
            config_manager.set_auto_backup_enabled(
                request.form.get("auto_backup_enabled") == "on"
            )
            config_manager.set_auto_backup_interval_minutes(
                request.form.get("auto_backup_interval_minutes", 30)
            )
            config_manager.set_auto_backup_retention_count(
                request.form.get("auto_backup_retention_count", 24)
            )
            config_manager.set_auto_backup_directory(
                request.form.get("auto_backup_directory", "")
            )
            if new_password:
                config_manager.CONFIG["web_password_hash"] = generate_password_hash(
                    new_password
                )
            config_manager.save_config()
            runtime.record("Application settings updated from web")
            flash("Application settings saved.")
            return redirect(url_for("app_settings"))

        backup_directory = get_backup_directory()
        backups = list_backups(backup_directory)
        return render_template(
            "app_settings.html",
            config=config_manager.CONFIG,
            backup_directory=backup_directory,
            backups=backups,
            backup_count=len(backups),
            format_file_size=_format_file_size,
        )

    @app.post("/app-settings/backups/create")
    def create_backup_now():
        server_running = config_manager.is_server_process_running()
        try:
            archive_path = backup_service.create_backup(request_save=server_running)
            if archive_path:
                archive_name = os.path.basename(archive_path)
                runtime.record(f"Manual backup created: {archive_name}")
                flash(f"Backup created: {archive_name}")
            else:
                runtime.record("Manual backup skipped because save data is unchanged")
                flash("No backup was created because the save data is unchanged.")
        except Exception as exc:
            runtime.record(f"Manual backup failed: {exc}")
            flash(f"Backup failed: {exc}", "error")
        return redirect(url_for("app_settings"))
