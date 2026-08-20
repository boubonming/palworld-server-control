import unittest

from core.setting_editor import (
    describe_setting,
    serialize_multi_values,
    setting_display_name,
)


class SettingEditorTests(unittest.TestCase):
    def test_describes_boolean_as_checkbox(self):
        self.assertEqual(describe_setting("bIsPvP", "True")["kind"], "boolean")

    def test_describes_known_choice_as_select(self):
        setting = describe_setting("DeathPenalty", "All")

        self.assertEqual(setting["kind"], "choice")
        self.assertIn(("No drops", "None"), setting["choices"])

    def test_describes_crossplay_as_multi_select(self):
        setting = describe_setting("CrossplayPlatforms", "(Steam,Xbox)")

        self.assertEqual(setting["kind"], "multi")
        self.assertEqual(setting["selected"], ["Steam", "Xbox"])

    def test_describes_bounded_integer_as_slider(self):
        setting = describe_setting("BaseCampWorkerMaxNum", "15")

        self.assertEqual(setting["kind"], "integer")
        self.assertIsNotNone(setting["minimum"])
        self.assertIsNotNone(setting["maximum"])
        self.assertTrue(setting["slider"])

    def test_serializes_quoted_multi_values(self):
        self.assertEqual(
            serialize_multi_values(["TechA", "TechB"], quote_values=True),
            '("TechA","TechB")',
        )

    def test_setting_display_name_is_shared_by_both_editors(self):
        self.assertEqual(setting_display_name("bIsPvP"), "Is PvP")


if __name__ == "__main__":
    unittest.main()
