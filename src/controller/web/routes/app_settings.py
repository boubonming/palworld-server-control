"""Controller-wide idle-shutdown and web-access settings."""

from flask import flash, redirect, render_template, request, url_for
from werkzeug.security import generate_password_hash

from core import config_manager


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

        return render_template("app_settings.html", config=config_manager.CONFIG)
