import unittest
from unittest.mock import Mock, patch

from shared.status import ServerState, ServerStatus
from web.app import create_web_app


class WebFeatureTests(unittest.TestCase):
    def setUp(self):
        self.runtime = Mock()
        self.runtime.activity.return_value = []
        self.runtime.discord_status.return_value = "Discord bot is online"
        self.runtime.discord_channels.return_value = {
            "123": "Guild / #general",
            "456": "Guild / #admin",
        }
        self.config = {
            "web_secret_key": "test-secret",
            "server_backend": "socket_proxy",
            "socket_proxy_configured": True,
        }
        self.config_patch = patch("web.app.config_manager.CONFIG", self.config)
        self.config_patch.start()
        self.addCleanup(self.config_patch.stop)
        self.app = create_web_app(self.runtime)
        self.client = self.app.test_client()
        with self.client.session_transaction() as session:
            session["authenticated"] = True
            session["_csrf_token"] = "csrf"

    def test_status_api_reports_docker_starting_state(self):
        with patch(
            "web.routes.server.server_readiness.get_status",
            return_value=ServerStatus(ServerState.STARTING),
        ):
            response = self.client.get("/api/status")

        self.assertEqual(response.get_json()["state"], "starting")

    def test_settings_page_has_search_slider_choices_and_multi_select(self):
        values = {
            "BaseCampWorkerMaxNum": "15",
            "DeathPenalty": "All",
            "CrossplayPlatforms": "(Steam,Xbox)",
            "bIsPvP": "False",
        }
        with (
            patch(
                "web.app.config_manager.get_palworld_editor_settings",
                return_value=values,
            ),
            patch(
                "web.app.config_manager.is_server_process_running",
                return_value=False,
            ),
            patch(
                "web.app.config_manager.get_palworld_backup_path",
                return_value="",
            ),
        ):
            response = self.client.get("/settings")

        html = response.get_data(as_text=True)
        self.assertIn('id="settings-search"', html)
        self.assertIn('type="range"', html)
        self.assertIn("<select", html)
        self.assertIn("multiple", html)

    def test_settings_post_serializes_checkbox_and_multi_select(self):
        values = {
            "bIsPvP": "True",
            "CrossplayPlatforms": "(Steam)",
        }
        with (
            patch(
                "web.app.config_manager.get_palworld_editor_settings",
                return_value=values,
            ),
            patch(
                "web.app.config_manager.is_server_process_running",
                return_value=False,
            ),
            patch(
                "web.app.config_manager.update_palworld_ini_settings",
            ) as update,
        ):
            response = self.client.post(
                "/settings",
                data={
                    "_csrf_token": "csrf",
                    "present__bIsPvP": "1",
                    "setting__CrossplayPlatforms": ["Steam", "PS5"],
                },
            )

        self.assertEqual(response.status_code, 302)
        update.assert_called_once_with(
            {
                "bIsPvP": "False",
                "CrossplayPlatforms": "(Steam,PS5)",
            }
        )

    def test_controller_renders_multiple_editable_discord_channels(self):
        self.config.update(
            discord_bot_token="token",
            palworld_channel_ids=["123", "456"],
        )

        response = self.client.get("/controller")

        html = response.get_data(as_text=True)
        self.assertEqual(html.count('name="palworld_channel_ids"'), 2)
        self.assertIn("Guild / #general", html)
        self.assertIn("Guild / #admin", html)


if __name__ == "__main__":
    unittest.main()
