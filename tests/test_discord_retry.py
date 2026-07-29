import unittest
from unittest.mock import Mock, patch

import discord

from integrations.discord_bot import (
    DiscordBotManager,
    retry_delay,
    should_retry_connection,
)


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


if __name__ == "__main__":
    unittest.main()
