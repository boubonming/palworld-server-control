import asyncio
import subprocess
import urllib.error

import discord
from discord.ext import commands

from core import api_client, config_manager
from integrations import discord_bot as bot_module
from shared.discord_activity import bot_reply_activity, command_activity, configured_channel_ids
from shared.status import ServerState, ServerStatus


class ServerControl(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @property
    def config(self):
        return config_manager.CONFIG

    @property
    def allowed_channel_ids(self):
        return configured_channel_ids(self.config.get("palworld_channel_ids", []))

    def record_activity(self, ctx, result):
        command = getattr(ctx.command, "name", "unknown")
        bot_module.signals.discord_activity.emit(
            command_activity(ctx.channel, ctx.author, f"!{command}", result)
        )

    def track_replies(self, ctx):
        original_send = ctx.send

        async def tracked_send(*args, **kwargs):
            result = await original_send(*args, **kwargs)
            content = args[0] if args else kwargs.get("content")
            if content:
                reply = str(content)
            elif kwargs.get("embed"):
                reply = "[Embedded server settings]"
            else:
                reply = "[Message sent]"
            bot_module.signals.discord_activity.emit(bot_reply_activity(ctx.channel, reply))
            return result

        ctx.send = tracked_send

    def command_allowed(self, ctx):
        self.track_replies(ctx)
        allowed = self.allowed_channel_ids
        if not allowed:
            self.record_activity(ctx, "Ignored: no control channels configured")
            return False
        if ctx.channel.id not in allowed:
            self.record_activity(ctx, "Ignored: channel is not configured")
            return False
        return True

    @commands.command(name="help")
    async def show_help(self, ctx):
        if not self.command_allowed(ctx):
            return

        embed = discord.Embed(
            title="Palworld Server Commands",
            description="Available server-control commands",
            color=discord.Color.blue(),
        )
        embed.add_field(
            name="!start [minutes|off]",
            value=(
                "Start the server using the saved idle-shutdown setting, "
                "a session-specific duration, or no idle shutdown."
            ),
            inline=False,
        )
        embed.add_field(
            name="!stop",
            value="Save the world and gracefully shut down the server.",
            inline=False,
        )
        embed.add_field(
            name="!settings",
            value="Show live settings when online or saved settings when offline.",
            inline=False,
        )
        embed.add_field(
            name="!help",
            value="Show this command list.",
            inline=False,
        )
        await ctx.send(embed=embed)
        self.record_activity(ctx, "Command help sent")

    @commands.command(name="start")
    async def start_server(self, ctx, idle_shutdown=None):
        if not self.command_allowed(ctx):
            return

        idle_shutdown_override = None
        if idle_shutdown is not None:
            if idle_shutdown.lower() == "off":
                idle_shutdown_override = False
            else:
                try:
                    idle_shutdown_override = int(idle_shutdown)
                except ValueError:
                    idle_shutdown_override = 0
                if not (
                    config_manager.MIN_AUTO_SHUTDOWN_EMPTY_MINUTES
                    <= idle_shutdown_override
                    <= config_manager.MAX_AUTO_SHUTDOWN_EMPTY_MINUTES
                ):
                    await ctx.send(
                        "Usage: `!start`, `!start <minutes>`, or `!start off` "
                        f"(minutes: {config_manager.MIN_AUTO_SHUTDOWN_EMPTY_MINUTES}-"
                        f"{config_manager.MAX_AUTO_SHUTDOWN_EMPTY_MINUTES})."
                    )
                    self.record_activity(ctx, "Failed: invalid idle shutdown override")
                    return

        if await asyncio.to_thread(config_manager.is_server_process_running):
            await ctx.send("Server is already running on the host PC.")
            self.record_activity(ctx, "Server already running")
            return

        server_exe = self.config.get("palworld_exe_path")
        server_dir = self.config.get("palworld_dir")
        if not server_exe:
            await ctx.send("Server executable path is not configured in the manager GUI settings.")
            self.record_activity(ctx, "Failed: server executable is not configured")
            return

        try:
            subprocess.Popen(
                config_manager.get_server_launch_command(),
                cwd=server_dir if server_dir else None,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            config_manager.set_server_launch_source(
                ("discord", ctx.channel.id), idle_shutdown_override
            )
            await self.bot.change_presence(
                status=discord.Status.online,
                activity=discord.Game(name="Palworld Server (ONLINE)"),
            )
            bot_module.signals.status_changed.emit(ServerStatus(ServerState.RUNNING))
            if idle_shutdown_override is False:
                idle_policy = " Idle shutdown is disabled for this session."
            elif idle_shutdown_override is not None:
                idle_policy = (
                    f" Idle shutdown is set to {idle_shutdown_override} empty minutes "
                    "for this session."
                )
            else:
                idle_policy = ""
            await ctx.send(f"Game server started successfully.{idle_policy}")
            self.record_activity(ctx, f"Server started{idle_policy}")
        except Exception as exc:
            await ctx.send(f"Failed to launch executable: {exc}")
            self.record_activity(ctx, f"Failed to start server: {exc}")

    @commands.command(name="stop")
    async def stop_server(self, ctx):
        if not self.command_allowed(ctx):
            return

        if not await asyncio.to_thread(config_manager.is_server_process_running):
            await ctx.send("Cannot stop: the server is already offline.")
            self.record_activity(ctx, "Server already stopped")
            return

        try:
            await ctx.send("Saving world progress...")
            await asyncio.to_thread(api_client.call_palworld_api, "save")
            status = await asyncio.to_thread(
                api_client.call_palworld_api,
                "shutdown",
                payload={"waittime": 5, "message": "Server shutting down"},
            )
            if status in (200, 202):
                config_manager.clear_server_launch_source()
                await self.bot.change_presence(status=discord.Status.idle, activity=None)
                bot_module.signals.status_changed.emit(ServerStatus(ServerState.STOPPED))
                await ctx.send("Server saved and shut down safely.")
                self.record_activity(ctx, "Server stopped")
        except urllib.error.URLError:
            await ctx.send("Failed to reach the server API.")
            self.record_activity(ctx, "Failed: server API unavailable")

    @commands.command(name="settings")
    async def server_settings(self, ctx):
        if not self.command_allowed(ctx):
            return

        try:
            data = await asyncio.to_thread(config_manager.get_palworld_ini_settings)

            if not data:
                await ctx.send(
                    "Cannot read server settings. Check that the Palworld server "
                    "directory and PalWorldSettings.ini are configured."
                )
                self.record_activity(ctx, "Failed: no server settings available")
                return
            embed = discord.Embed(title="Palworld Server Configuration", color=discord.Color.blue())
            embed.add_field(name="Server Name", value=data.get("ServerName"), inline=False)
            embed.add_field(name="Difficulty", value=data.get("Difficulty"), inline=True)
            embed.add_field(name="Max Players", value=data.get("ServerPlayerMaxNum"), inline=True)
            embed.add_field(name="Is PVP", value=data.get("bIsPvP", False), inline=True)
            embed.add_field(
                name="Multipliers",
                value=(
                    f"XP Rate: {data.get('ExpRate', '1.0')}x\n"
                    f"Capture Rate: {data.get('PalCaptureRate', '1.0')}x"
                ),
                inline=False,
            )
            await ctx.send(embed=embed)
            self.record_activity(ctx, f"Server settings sent: {data.get('ServerName')}")
        except Exception as exc:
            await ctx.send(f"Error displaying settings: {exc}")
            self.record_activity(ctx, f"Failed to fetch settings: {exc}")


async def setup(bot):
    await bot.add_cog(ServerControl(bot))
