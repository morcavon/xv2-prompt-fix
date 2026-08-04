from __future__ import annotations

import tkinter as tk
import unittest
from unittest.mock import Mock, patch

from xv2_prompt_fix.app import MainWindow


class TkCompatibilityTests(unittest.TestCase):
    def test_main_window_does_not_shadow_tk_options(self) -> None:
        # Tkinter dialogs call master._options(options). A zero-argument
        # application helper using that name would break every standard dialog.
        self.assertNotIn("_options", MainWindow.__dict__)
        self.assertIs(MainWindow._options, tk.Misc._options)
        window = object.__new__(MainWindow)
        self.assertEqual(window._options({"title": "test"}), ("-title", "test"))

    def test_workflow_option_builder_has_non_reserved_name(self) -> None:
        self.assertIn("_workflow_options", MainWindow.__dict__)

    def test_public_source_ui_does_not_launch_game_directly(self) -> None:
        self.assertNotIn("_launch_game", MainWindow.__dict__)

    def test_language_switch_and_scope_notice_are_available(self) -> None:
        self.assertIn("_language_changed", MainWindow.__dict__)
        self.assertIn("_refresh_language", MainWindow.__dict__)
        self.assertIn("_confirm_patch_scope", MainWindow.__dict__)

    def test_language_switch_clears_stale_log_and_detaches_log_file(self) -> None:
        window = object.__new__(MainWindow)
        window.language_choice = Mock()
        window.language_choice.get.return_value = "English"
        window.current_log_path = object()
        window._clear_log = Mock()
        window._refresh_language = Mock()

        with patch("xv2_prompt_fix.app.set_language") as set_language:
            window._language_changed()

        set_language.assert_called_once_with("en")
        self.assertIsNone(window.current_log_path)
        window._clear_log.assert_called_once_with()
        window._refresh_language.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
