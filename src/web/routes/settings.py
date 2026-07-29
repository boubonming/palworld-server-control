"""Palworld server-settings editor endpoints."""

import os

from flask import flash, redirect, render_template, request, url_for

from core import config_manager
from core.setting_categories import SETTING_CATEGORIES
from core.setting_editor import (
    describe_setting,
    serialize_multi_values,
    setting_display_name,
)
from core.setting_metadata import get_setting_tooltip


def _submitted_updates(current_values):
    updates = {}
    for key, value in current_values.items():
        field_name = f"setting__{key}"
        editor = describe_setting(key, value)
        if editor["kind"] == "boolean":
            if f"present__{key}" in request.form:
                updates[key] = (
                    "True" if request.form.get(field_name) == "True" else "False"
                )
        elif editor["kind"] == "multi":
            if field_name in request.form:
                updates[key] = serialize_multi_values(
                    request.form.getlist(field_name),
                    editor["quote_values"],
                )
        elif field_name in request.form:
            updates[key] = request.form.get(field_name, "")
    return updates


def _setting_groups(values):
    groups = {}
    for key, value in values.items():
        category = SETTING_CATEGORIES.get(key)
        category_name = category.value if category else "Other"
        groups.setdefault(category_name, []).append({
            "key": key,
            "name": setting_display_name(key),
            "value": value,
            "description": get_setting_tooltip(key),
            **describe_setting(key, value),
        })
    for items in groups.values():
        items.sort(key=lambda item: item["name"].lower())
    return sorted(groups.items())


def register_settings_routes(app, runtime):
    @app.route("/settings", methods=["GET", "POST"])
    def settings():
        if not config_manager.CONFIG.get("socket_proxy_configured", False):
            flash(
                "Configure Docker Socket Proxy before editing server settings.",
                "error",
            )
            return redirect(url_for("setup"))
        if request.method == "POST":
            if config_manager.is_server_process_running():
                flash("Stop the server before editing settings.", "error")
                return redirect(url_for("settings"))
            updates = _submitted_updates(
                config_manager.get_palworld_editor_settings()
            )
            try:
                config_manager.update_palworld_ini_settings(updates)
                runtime.record(f"Updated {len(updates)} Palworld settings")
                flash(
                    "Settings saved. They will be applied on the next container start."
                )
            except Exception as exc:
                flash(str(exc), "error")
            return redirect(url_for("settings"))

        values = config_manager.get_palworld_editor_settings()
        return render_template(
            "settings.html",
            groups=_setting_groups(values),
            running=config_manager.is_server_process_running(),
            backup_exists=os.path.isfile(
                config_manager.get_palworld_backup_path()
            ),
        )

    @app.post("/settings/reset")
    def reset_settings():
        if config_manager.is_server_process_running():
            flash("Stop the server before resetting settings.", "error")
        else:
            try:
                config_manager.reset_palworld_ini_settings()
                runtime.record("Reset Palworld settings to defaults")
                flash("Settings reset to Palworld defaults.")
            except Exception as exc:
                flash(str(exc), "error")
        return redirect(url_for("settings"))

    @app.route("/settings/revert", methods=["GET", "POST"])
    def revert_settings():
        if request.method == "GET":
            try:
                changes = config_manager.get_palworld_backup_changes()
            except Exception as exc:
                flash(str(exc), "error")
                return redirect(url_for("settings"))
            return render_template("revert_settings.html", changes=changes)
        if config_manager.is_server_process_running():
            flash("Stop the server before reverting settings.", "error")
            return redirect(url_for("settings"))
        try:
            config_manager.revert_to_palworld_backup()
            runtime.record("Reverted container environment settings backup")
            flash("Settings reverted. They will be applied at the next start.")
        except Exception as exc:
            flash(str(exc), "error")
        return redirect(url_for("settings"))
