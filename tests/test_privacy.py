from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from xv2_prompt_fix.utils import app_data_dir, prune_old_logs, sanitize_log_text


class PrivacyTests(unittest.TestCase):
    def test_app_data_directory_uses_generic_project_name(self) -> None:
        with (
            tempfile.TemporaryDirectory() as temp,
            patch.dict(os.environ, {"LOCALAPPDATA": temp}, clear=False),
        ):
            self.assertEqual(app_data_dir(), Path(temp) / "XV2PromptFix")

    def test_log_text_redacts_user_directories_case_insensitively(self) -> None:
        env = {
            "USERPROFILE": r"C:\Users\Alice",
            "LOCALAPPDATA": r"C:\Users\Alice\AppData\Local",
            "APPDATA": r"C:\Users\Alice\AppData\Roaming",
            "TEMP": r"C:\Users\Alice\AppData\Local\Temp",
        }
        text = (
            r"C:\Users\ALICE\AppData\Local\XV2PromptFix\logs\session.log "
            r"C:\Users\Alice\Documents\data1.cpk"
        )
        with patch.dict(os.environ, env, clear=False):
            sanitized = sanitize_log_text(text)
        self.assertNotIn("alice", sanitized.casefold())
        self.assertIn("%LOCALAPPDATA%", sanitized)
        self.assertIn("%USERPROFILE%", sanitized)

    def test_log_retention_limits_age_and_count(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            now = datetime.now().astimezone()
            for index in range(5):
                path = directory / f"session-{index}.log"
                path.write_text(str(index))
                age = timedelta(days=40 if index == 0 else index)
                timestamp = (now - age).timestamp()
                os.utime(path, (timestamp, timestamp))
            prune_old_logs(directory, max_files=3, max_age_days=30, now=now)
            remaining = sorted(path.name for path in directory.glob("*.log"))
            self.assertEqual(len(remaining), 3)
            self.assertNotIn("session-0.log", remaining)


if __name__ == "__main__":
    unittest.main()
