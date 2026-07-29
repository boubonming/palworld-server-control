import unittest
from unittest.mock import Mock, patch

from shared.status import ServerState, ServerStatus
from web.app import create_web_app
from web.routes.settings import _setting_groups


class WebFeatureTests(unittest.TestCase):
    def setUp(self):
        self.runtime = Mock()
        self.runtime.activity.return_value = []
        self.runtime.discord_status.return_value = "Discord bot is online"
        self.runtime.discord_activity.return_value = [
            "[2026-07-29 12:00:00] Discord command received"
        ]
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

    def test_settings_page_has_search_slider_choices_and_checkbox_picker(self):
        values = {
            "BaseCampWorkerMaxNum": "15",
            "DeathPenalty": "All",
            "CrossplayPlatforms": "(Steam,Xbox)",
            "DenyTechnologyList": '("AIcore")',
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
        self.assertIn('class="multi-picker"', html)
        self.assertIn('value="AIcore"', html)
        self.assertIn("AI Core", html)
        self.assertNotIn("Hold Ctrl/Cmd", html)

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
                    "present__CrossplayPlatforms": "1",
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

    def test_settings_post_can_clear_a_multi_select(self):
        values = {"CrossplayPlatforms": "(Steam,Xbox)"}
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
            self.client.post(
                "/settings",
                data={
                    "_csrf_token": "csrf",
                    "present__CrossplayPlatforms": "1",
                },
            )

        update.assert_called_once_with({"CrossplayPlatforms": "()"})

    def test_discord_page_renders_understandable_channel_cards(self):
        self.config.update(
            discord_bot_token="token",
            palworld_channel_ids=["123", "456"],
        )

        response = self.client.get("/discord")

        html = response.get_data(as_text=True)
        self.assertEqual(html.count('value="123"'), 1)
        self.assertEqual(html.count('value="456"'), 1)
        self.assertIn("Discord", html)
        self.assertIn("Channel ID", html)
        self.assertIn("Commands are accepted only in these channels", html)
        self.assertIn("Save channels", html)
        self.assertIn("Guild / #general", html)
        self.assertIn("Guild / #admin", html)
        self.assertIn("Discord command received", html)

    def test_navigation_separates_discord_and_app_settings(self):
        response = self.client.get("/discord")
        html = response.get_data(as_text=True)

        self.assertIn(">Discord<", html)
        self.assertIn(">App Settings<", html)
        self.assertNotIn(">Controller<", html)
        self.assertNotIn(">Activity<", html)

    def test_app_settings_owns_idle_shutdown_and_web_password(self):
        response = self.client.get("/app-settings")
        html = response.get_data(as_text=True)

        self.assertIn("Idle shutdown", html)
        self.assertIn("Web access", html)
        self.assertNotIn("Control channels", html)

    def test_channel_form_saves_only_valid_unique_ids(self):
        self.config["palworld_channel_ids"] = ["old"]
        with patch("web.routes.discord.config_manager.save_config") as save:
            response = self.client.post(
                "/discord/channels",
                data={
                    "_csrf_token": "csrf",
                    "palworld_channel_ids": ["123", "invalid", "123", "456"],
                },
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.config["palworld_channel_ids"], ["123", "456"])
        save.assert_called_once()

    def test_old_controller_url_redirects_to_discord(self):
        response = self.client.get("/controller")

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/discord"))

    def test_settings_use_desktop_category_and_priority_order(self):
        groups = _setting_groups({
            "BaseCampWorkerMaxNum": "15",
            "DayTimeSpeedRate": "1.0",
            "Difficulty": "None",
        })

        self.assertEqual(
            [category for category, _items in groups],
            ["General, World & Events", "Building, Bases & Guilds"],
        )
        self.assertEqual(
            [item["key"] for item in groups[0][1]],
            ["Difficulty", "DayTimeSpeedRate"],
        )

    def test_settings_render_category_navigation(self):
        values = {
            "Difficulty": "None",
            "BaseCampWorkerMaxNum": "15",
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
        self.assertIn('class="settings-category-nav"', html)
        self.assertIn('class="settings-category-button active"', html)
        self.assertIn('class="settings-category-panel active"', html)


if __name__ == "__main__":
    unittest.main()
