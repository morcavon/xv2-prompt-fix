from __future__ import annotations

import unittest

from xv2_prompt_fix.errors import FixError
from xv2_prompt_fix.workflow import _select_resource_patch_paths


class ResourceSetSelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.iggy = "data/system/iggy/sysfont01_ab_fr.iggy"
        self.iggytex = "data/system/iggy/sysfont01_ab_fr.iggytex"
        self.iggyted = "data/system/iggy/sysfont01_ab_fr.iggyted"
        self.paths = (self.iggy, self.iggytex, self.iggyted)
        self.source = {
            self.iggy: "source-iggy",
            self.iggytex: "same-iggytex",
            self.iggyted: "source-iggyted",
        }

    def test_selects_matching_iggy_and_iggyted_files_in_order(self) -> None:
        current = {
            self.iggy: "current-iggy",
            self.iggytex: "same-iggytex",
            self.iggyted: "current-iggyted",
        }

        changed, raw = _select_resource_patch_paths(
            self.paths, self.source, current
        )

        self.assertEqual(changed, (self.iggy, self.iggyted))
        self.assertEqual(raw, (self.iggyted,))

    def test_accepts_already_fixed_complete_set(self) -> None:
        changed, raw = _select_resource_patch_paths(
            self.paths, self.source, dict(self.source)
        )

        self.assertEqual(changed, ())
        self.assertEqual(raw, ())

    def test_rejects_iggyted_only_partial_set(self) -> None:
        current = {
            self.iggy: "source-iggy",
            self.iggytex: "same-iggytex",
            self.iggyted: "current-iggyted",
        }

        with self.assertRaises(FixError):
            _select_resource_patch_paths(self.paths, self.source, current)

    def test_rejects_iggy_only_partial_set(self) -> None:
        current = {
            self.iggy: "current-iggy",
            self.iggytex: "same-iggytex",
            self.iggyted: "source-iggyted",
        }

        with self.assertRaises(FixError):
            _select_resource_patch_paths(self.paths, self.source, current)

    def test_rejects_changed_iggytex(self) -> None:
        current = {
            self.iggy: "current-iggy",
            self.iggytex: "current-iggytex",
            self.iggyted: "current-iggyted",
        }

        with self.assertRaises(FixError):
            _select_resource_patch_paths(self.paths, self.source, current)


if __name__ == "__main__":
    unittest.main()
