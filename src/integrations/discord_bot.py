import asyncio
import threading
import discord
from discord.ext import commands
from PySide6.QtCore import QObject, Signal
from core import config_manager
from shared.discord_activity import channel_context, command_activity, normalize_channel_id
from shared.status import ServerState, ServerStatus

# Thread bridge 
class BotSignals(QObject):
    status_changed = Signal(object)
    bot_status_changed = Signal(str)
    discord_activity = Signal(str)
    discord_channel_info = Signal(str, str)

signals = BotSignals()

intents = discord.Intents.default()
intents.message_content = True

def create_bot():
    class ManagedBot(commands.Bot):
        async def setup_hook(self):
            try:
                await self.load_extension("integrations.server_cog")
            except Exception as exc:
                print(f"Discord command module failed to load: {exc}")
                signals.bot_status_changed.emit(
                    f"Discord commands failed to load: {exc}"
                )

    bot_instance = ManagedBot(command_prefix="!", intents=intents)

    @bot_instance.event
    async def on_ready():
        print(f"🎉 Success! Bot is online as {bot_instance.user}")
        with discord_manager._lock:
            discord_manager._state = "running"
        signals.bot_status_changed.emit("Discord bot is online")

        if bot_instance.get_cog("ServerControl") is None:
            signals.bot_status_changed.emit(
                "Discord bot online, but Discord commands are unavailable"
            )

        if config_manager.is_server_process_running():
            await bot_instance.change_presence(
                status=discord.Status.online,
                activity=discord.Game(name="Palworld Server (ONLINE)"),
            )
            signals.status_changed.emit(ServerStatus(ServerState.RUNNING))
        else:
            await bot_instance.change_presence(status=discord.Status.idle, activity=None)
            signals.status_changed.emit(ServerStatus(ServerState.STOPPED))

        for raw_channel_id in config_manager.CONFIG.get("palworld_channel_ids", []):
            channel_id = normalize_channel_id(raw_channel_id)
            if channel_id is None:
                continue
            channel = bot_instance.get_channel(channel_id)
            if channel is None:
                try:
                    channel = await bot_instance.fetch_channel(channel_id)
                except Exception:
                    channel = None
            if channel is None:
                signals.discord_channel_info.emit(str(channel_id), "Unavailable - check the ID and bot access")
                continue
            signals.discord_channel_info.emit(str(channel_id), channel_context(channel))

    @bot_instance.event
    async def on_message(message):
        if message.author.bot:
            return
        if message.content.startswith("!"):
            command_name = message.content.split(maxsplit=1)[0]
            signals.discord_activity.emit(
                command_activity(message.channel, message.author, command_name, "Received")
            )
        await bot_instance.process_commands(message)

    @bot_instance.event
    async def on_command_error(ctx, error):
        if isinstance(error, commands.CommandNotFound):
            result = "Ignored: unknown command"
        else:
            result = f"Failed: {error}"
        command_name = getattr(ctx.command, "name", "unknown")
        signals.discord_activity.emit(
            command_activity(ctx.channel, ctx.author, f"!{command_name}", result)
        )

    return bot_instance


bot = None

class DiscordBotManager:
    """Owns the Discord bot thread and event loop for GUI lifecycle controls."""
    def __init__(self):
        self.thread = None
        self.loop = None
        self._lock = threading.Lock()
        self._state = "stopped"
        self._stop_requested = False
        self._loop_ready = threading.Event()

    @property
    def is_running(self):
        with self._lock:
            return self._state in {"starting", "running"}

    @property
    def state(self):
        with self._lock:
            return self._state

    def start(self, token: str):
        if not token:
            signals.bot_status_changed.emit("Discord bot cannot start: token is missing")
            return False
        with self._lock:
            if self._state != "stopped":
                return False
            self._state = "starting"
            self._stop_requested = False
            self._loop_ready.clear()
            global bot
            bot = create_bot()
            self.thread = threading.Thread(target=self._run, args=(token, bot), daemon=True)
            self.thread.start()
        signals.bot_status_changed.emit("Connecting Discord bot...")
        return True

    def _run(self, token: str, bot_instance):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self._loop_ready.set()
        with self._lock:
            stop_requested = self._stop_requested
        if stop_requested:
            self.loop.close()
            with self._lock:
                self.loop = None
                self._state = "stopped"
                self._stop_requested = False
            signals.bot_status_changed.emit("Discord bot stopped")
            return
        try:
            self.loop.run_until_complete(bot_instance.start(token))
        except Exception as exc:
            print(f"Discord bot stopped: {exc}")
            if not self._stop_requested:
                signals.bot_status_changed.emit("Discord bot failed to connect. Check the token and connection.")
        finally:
            self.loop.close()
            with self._lock:
                self.loop = None
                self._state = "stopped"
                stop_requested = self._stop_requested
                self._stop_requested = False
            if stop_requested:
                signals.bot_status_changed.emit("Discord bot stopped")

    def stop(self):
        with self._lock:
            if self._state not in {"starting", "running"}:
                return False
            self._state = "stopping"
            self._stop_requested = True
            loop = self.loop
        signals.bot_status_changed.emit("Stopping Discord bot...")
        if loop:
            threading.Thread(target=self._close_bot, args=(loop, bot), daemon=True).start()
        else:
            # Exit can be requested after start() changes the state but before
            # the worker has published its event loop. Wait for that handoff
            # so the bot is still closed and the GUI can finish exiting.
            threading.Thread(
                target=self._close_when_ready,
                args=(bot,),
                daemon=True,
            ).start()
        return True

    def _close_when_ready(self, bot_instance):
        if not self._loop_ready.wait(timeout=5):
            return
        loop = self.loop
        if loop:
            self._close_bot(loop, bot_instance)

    def _close_bot(self, loop, bot_instance):
        future = asyncio.run_coroutine_threadsafe(bot_instance.close(), loop)
        try:
            future.result(timeout=5)
        except TimeoutError:
            future.cancel()
            loop.call_soon_threadsafe(loop.stop)
            signals.bot_status_changed.emit(
                "Discord bot shutdown did not respond; forcing shutdown..."
            )
        except Exception as exc:
            print(f"Discord bot close warning: {exc}")
            loop.call_soon_threadsafe(loop.stop)
            signals.bot_status_changed.emit(
                "Discord bot shutdown failed; forcing shutdown..."
            )

    def restart(self, token: str):
        if not token:
            signals.bot_status_changed.emit("Discord bot cannot restart: token is missing")
            return False
        if self.state == "stopped":
            return self.start(token)
        if not self.stop():
            return False
        thread = self.thread
        threading.Thread(target=self._restart_after_stop, args=(thread, token), daemon=True).start()
        signals.bot_status_changed.emit("Restarting Discord bot after shutdown...")
        return True

    def _restart_after_stop(self, thread, token):
        if thread and thread is not threading.current_thread():
            thread.join(timeout=10)
        self.start(token)

    async def _broadcast_idle_shutdown(self, minutes, launch_source, bot_instance):
        if not launch_source or launch_source[0] != "discord":
            return
        message = (
            "Automated idle shutdown: the server was empty for "
            f"{minutes} minutes. Progress saved and server closed safely."
        )
        channel_id = normalize_channel_id(launch_source[1])
        if channel_id is None:
            return
        channel = bot_instance.get_channel(channel_id)
        if channel is None:
            try:
                channel = await bot_instance.fetch_channel(channel_id)
            except Exception as exc:
                print(f"Automated shutdown notification channel unavailable ({channel_id}): {exc}")
                return
        try:
            await channel.send(message)
        except Exception as exc:
            print(f"Automated shutdown notification failed for channel {channel_id}: {exc}")
        await bot_instance.change_presence(status=discord.Status.idle, activity=None)

    async def _update_server_presence(self, status, bot_instance):
        if status.state is ServerState.STOPPED:
            await bot_instance.change_presence(status=discord.Status.idle, activity=None)
            return
        await bot_instance.change_presence(
            status=discord.Status.online,
            activity=discord.Game(name=f"Palworld {status.display}"),
        )

    def notify_idle_shutdown(self, minutes, launch_source):
        """Best-effort notification for a Discord-launched server session."""
        with self._lock:
            loop = self.loop
            bot_instance = bot
            active = self._state in {"starting", "running"}
        if not active or loop is None or bot_instance is None:
            return False
        asyncio.run_coroutine_threadsafe(
            self._broadcast_idle_shutdown(minutes, launch_source, bot_instance),
            loop,
        )
        return True

    def update_server_presence(self, status):
        with self._lock:
            loop = self.loop
            bot_instance = bot
            active = self._state in {"starting", "running"}
        if not active or loop is None or bot_instance is None:
            return False
        asyncio.run_coroutine_threadsafe(
            self._update_server_presence(status, bot_instance),
            loop,
        )
        return True

discord_manager = DiscordBotManager()

def run_discord_bot(token: str):
    """Fires up the async bot loops inside the background thread."""
    discord_manager.start(token)


def notify_idle_shutdown(minutes, launch_source):
    return discord_manager.notify_idle_shutdown(minutes, launch_source)


def update_server_presence(status):
    return discord_manager.update_server_presence(status)
