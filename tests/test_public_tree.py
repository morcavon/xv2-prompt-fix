from __future__ import annotations

import unittest
from pathlib import Path

from scripts.check_public_tree import DISALLOWED_SUFFIXES


ROOT = Path(__file__).resolve().parents[1]


class PublicTreePolicyTests(unittest.TestCase):
    def test_iggyted_game_resource_is_ignored_and_disallowed(self) -> None:
        ignore_rules = {
            line.strip()
            for line in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        }

        self.assertIn("*.iggyted", ignore_rules)
        self.assertIn(".iggyted", DISALLOWED_SUFFIXES)


if __name__ == "__main__":
    unittest.main()
