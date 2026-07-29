"""Discord configuration, channel access, and bot lifecycle endpoints."""

from flask import abort, flash, jsonify, redirect, render_template, request, url_for

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


def register_discord_routes(app, runtime):
    @app.get("/discord")
    def discord_settings():
        return render_template(
            "discord.html",
            config=config_manager.CONFIG,
            discord_state=discord_bot.discord_manager.state,
            discord_status=runtime.discord_status(),
            discord_channels=runtime.discord_channels(),
            discord_activity=runtime.discord_activity()[:20],
        )

    @app.get("/controller")
    def legacy_controller_settings():
        return redirect(url_for("discord_settings"))

    @app.post("/discord/settings")
    def save_discord_settings():
        config_manager.CONFIG["discord_bot_token"] = request.form.get(
            "discord_bot_token", ""
        ).strip()
        config_manager.set_discord_bot_auto_start(
            request.form.get("discord_bot_auto_start") == "on"
        )
        config_manager.save_config()
        runtime.record_discord("Discord connection settings updated from web")
        flash(
            "Discord settings saved. Restart the bot to apply a new token."
        )
        return redirect(url_for("discord_settings"))

    @app.post("/discord/channels")
    def save_discord_channels():
        config_manager.CONFIG["palworld_channel_ids"] = _submitted_channel_ids()
        config_manager.save_config()
        runtime.record_discord("Discord control channels updated from web")
        flash("Discord control channels saved.")
        return redirect(url_for("discord_settings"))

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
        runtime.record_discord(f"Discord bot {action} requested from web")
        flash(
            f"Discord bot {action} requested."
            if changed
            else f"Discord bot could not {action} in its current state.",
            "" if changed else "error",
        )
        return redirect(url_for("discord_settings"))

    @app.get("/api/discord")
    def discord_status_api():
        return jsonify(
            state=discord_bot.discord_manager.state,
            display=runtime.discord_status(),
            channels=runtime.discord_channels(),
            activity=runtime.discord_activity()[:20],
        )
