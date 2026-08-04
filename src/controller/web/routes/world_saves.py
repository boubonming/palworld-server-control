"""World-save selection endpoints."""

from flask import flash, redirect, render_template, request, url_for

from core import config_manager
from core.world_saves import (
    get_active_world_id,
    get_game_user_settings_path,
    list_world_saves,
    select_world_save,
)


def register_world_save_routes(app, runtime):
    @app.route("/world-saves", methods=["GET", "POST"])
    def world_saves():
        if request.method == "POST":
            try:
                selected = request.form.get("world_id", "")
                changed = select_world_save(selected)
                if changed:
                    runtime.record(f"Selected Palworld world save {selected}")
                    flash("Active world changed. It will load on the next server start.")
                else:
                    flash("That world is already active.")
            except Exception as exc:
                flash(str(exc), "error")
            return redirect(url_for("world_saves"))

        return render_template(
            "world_saves.html",
            worlds=list_world_saves(),
            active_world_id=get_active_world_id(),
            settings_path=get_game_user_settings_path(),
            running=config_manager.is_server_process_running(),
        )
