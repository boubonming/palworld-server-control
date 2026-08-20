import asyncio
import unittest
from unittest.mock import Mock, patch

import discord

from integrations.discord_bot import (
    DiscordBotManager,
    retry_delay,
    should_retry_connection,
)


class FakeChannel:
    def __init__(self):
        self.messages = []

    async def send(self, message):
        self.messages.append(message)


class FakeBot:
    def __init__(self, channels):
        self.channels = channels

    def get_channel(self, channel_id):
        return self.channels.get(channel_id)

    async def fetch_channel(self, channel_id):
        return self.channels.get(channel_id)


class DiscordRetryTests(unittest.TestCase):
    def test_transient_connection_errors_are_retried(self):
        self.assertTrue(should_retry_connection(OSError("network unavailable")))

    def test_invalid_token_is_not_retried(self):
        self.assertFalse(should_retry_connection(discord.LoginFailure("bad token")))

    def test_retry_delay_caps_at_one_minute(self):
        self.assertEqual([retry_delay(i) for i in range(6)], [5, 10, 20, 40, 60, 60])

    def test_manager_recreates_bot_after_transient_start_failure(self):
        manager = DiscordBotManager()
        first_loop = Mock()
        first_loop.run_until_complete.side_effect = OSError("network unavailable")
        second_loop = Mock()
        first_bot = Mock()
        first_bot.start.return_value = object()
        first_bot.is_closed.return_value = True
        second_bot = Mock()
        second_bot.start.return_value = object()
        second_bot.is_closed.return_value = True

        with (
            patch(
                "integrations.discord_bot.asyncio.new_event_loop",
                side_effect=[first_loop, second_loop],
            ),
            patch("integrations.discord_bot.asyncio.set_event_loop"),
            patch(
                "integrations.discord_bot.create_bot",
                side_effect=[first_bot, second_bot],
            ) as create,
            patch("integrations.discord_bot.retry_delay", return_value=0),
        ):
            manager._run("token", retry=True)

        self.assertEqual(create.call_count, 2)
        self.assertEqual(manager.state, "stopped")

    def test_update_notifications_target_launch_channel(self):
        manager = DiscordBotManager()
        launch_channel = FakeChannel()
        other_channel = FakeChannel()
        bot = FakeBot({111: launch_channel, 222: other_channel})

        with patch(
            "integrations.discord_bot.config_manager.CONFIG",
            {"palworld_channel_ids": [111, 222]},
        ):
            asyncio.run(
                manager._broadcast_control_message(
                    "update detected",
                    "Server update detected",
                    bot,
                    ("discord", 111),
                )
            )

        self.assertEqual(launch_channel.messages, ["update detected"])
        self.assertEqual(other_channel.messages, [])

    def test_update_notifications_are_skipped_when_discord_did_not_start_server(self):
        manager = DiscordBotManager()
        first_channel = FakeChannel()
        second_channel = FakeChannel()
        bot = FakeBot({111: first_channel, 222: second_channel})

        with patch(
            "integrations.discord_bot.config_manager.CONFIG",
            {"palworld_channel_ids": [111, 222]},
        ):
            asyncio.run(
                manager._broadcast_control_message(
                    "update detected",
                    "Server update detected",
                    bot,
                    "app",
                )
            )

        self.assertEqual(first_channel.messages, [])
        self.assertEqual(second_channel.messages, [])


if __name__ == "__main__":
    unittest.main()
