"""Controller configuration and Discord lifecycle endpoints."""

from flask import abort, flash, jsonify, redirect, render_template, request, url_for
from werkzeug.security import generate_password_hash

from core import config_manager
from integrations import discord_bot


def _submitted_channel_ids():
    channel_values = []
    for raw_value in request.form.getlist("palworld_channel_ids"):
        channel_values.extend(raw_value.split(","))
    return list(dict.fromkeys(
        value.strip()
        for value in channel_values
        if value.strip().isdigit()
    ))


def register_controller_routes(app, runtime):
    @app.route("/controller", methods=["GET", "POST"])
    def controller_settings():
        if request.method == "POST":
            config_manager.CONFIG["discord_bot_token"] = request.form.get(
                "discord_bot_token", ""
            ).strip()
            config_manager.CONFIG["palworld_channel_ids"] = _submitted_channel_ids()
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
                    flash(
                        "The web password must be at least 10 characters.",
                        "error",
                    )
                    return redirect(url_for("controller_settings"))
                config_manager.CONFIG["web_password_hash"] = generate_password_hash(
                    new_password
                )
            config_manager.save_config()
            runtime.record("Controller configuration updated from web")
            flash(
                "Controller settings saved. "
                "Restart the Discord bot to apply a new token."
            )
            return redirect(url_for("controller_settings"))
        return render_template(
            "controller.html",
            config=config_manager.CONFIG,
            discord_state=discord_bot.discord_manager.state,
            discord_status=runtime.discord_status(),
            discord_channels=runtime.discord_channels(),
            discord_activity=runtime.activity()[:20],
        )

    @app.post("/discord/<action>")
    def discord_action(action):
        token = config_manager.CONFIG.get("discord_bot_token", "")
        if action == "start":
            changed = discord_bot.discord_manager.start(token)
        elif action == "stop":
            changed = discord_bot.discord_manager.stop()
        elif action == "restart":
            changed = discord_bot.discord_manager.restart(token)
        else:
            abort(404)
        runtime.record(f"Discord bot {action} requested from web")
        flash(
            f"Discord bot {action} requested."
            if changed
            else f"Discord bot could not {action} in its current state.",
            "" if changed else "error",
        )
        return redirect(url_for("controller_settings"))

    @app.get("/api/discord")
    def discord_status_api():
        return jsonify(
            state=discord_bot.discord_manager.state,
            display=runtime.discord_status(),
            channels=runtime.discord_channels(),
            activity=runtime.activity()[:20],
        )
