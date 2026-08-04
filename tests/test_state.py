from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from xv2_prompt_fix.constants import BACKUP_PREFIX, STATE_FILE_NAME, STATE_SCHEMA_VERSION
from xv2_prompt_fix.errors import FixError
from xv2_prompt_fix.state import FixState, load_state, resolve_backup_path, save_state


class StateTests(unittest.TestCase):
    def test_state_round_trip_uses_relative_backup_name(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "cpk").mkdir()
            expected = FixState(
                app_version="0.4.0",
                active=True,
                backup_name=f"{BACKUP_PREFIX}test",
                original_sha256="a" * 64,
                patched_sha256="b" * 64,
            )

            save_state(root, expected)

            raw = json.loads((root / "cpk" / STATE_FILE_NAME).read_text())
            self.assertEqual(raw["schema_version"], STATE_SCHEMA_VERSION)
            self.assertNotIn("game_root", raw)
            self.assertNotIn("backup_path", raw)
            actual = load_state(root)
            self.assertIsNotNone(actual)
            if actual is None:
                self.fail("The state file could not be loaded.")
            self.assertTrue(actual.active)
            self.assertEqual(actual.backup_name, expected.backup_name)
            self.assertEqual(
                resolve_backup_path(root, actual), root / "cpk" / expected.backup_name
            )

    def test_rejects_unsupported_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cpk = root / "cpk"
            cpk.mkdir()
            (cpk / STATE_FILE_NAME).write_text(
                json.dumps({"schema_version": STATE_SCHEMA_VERSION + 1})
            )

            with self.assertRaises(FixError):
                load_state(root)

    def test_rejects_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cpk = root / "cpk"
            cpk.mkdir()
            data = {
                "schema_version": STATE_SCHEMA_VERSION,
                "backup_name": f"../{BACKUP_PREFIX}x",
            }
            (cpk / STATE_FILE_NAME).write_text(json.dumps(data))

            with self.assertRaises(FixError):
                load_state(root)

    def test_rejects_unknown_backup_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cpk = root / "cpk"
            cpk.mkdir()
            data = {
                "schema_version": STATE_SCHEMA_VERSION,
                "backup_name": "data1.cpk.backup-x",
            }
            (cpk / STATE_FILE_NAME).write_text(json.dumps(data))

            with self.assertRaises(FixError):
                load_state(root)


if __name__ == "__main__":
    unittest.main()
