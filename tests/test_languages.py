from __future__ import annotations

import unittest

from xv2_prompt_fix.errors import FixError
from xv2_prompt_fix.languages import (
    discover_language_resource_sets,
    language_codes,
    resolve_patch_targets,
    resource_code_for_steam_language,
)


def resource_set(code: str) -> tuple[str, str, str]:
    suffix = f"_{code}" if code else ""
    return (
        f"data/system/iggy/sysfont01_ab{suffix}.iggy",
        f"data/system/iggy/sysfont01_ab{suffix}.iggytex",
        f"data/system/iggy/sysfont01_ab{suffix}.iggyted",
    )


class LanguageDiscoveryTests(unittest.TestCase):
    def test_discovers_complete_non_english_non_japanese_resource_sets(self) -> None:
        entries = [
            *resource_set(""),
            *resource_set("en"),
            *resource_set("jp"),
            *resource_set("de"),
            *resource_set("fr"),
        ]
        resource_sets = discover_language_resource_sets(entries)
        self.assertEqual(set(resource_sets), {"de", "fr"})

    def test_supports_compound_language_codes(self) -> None:
        resource_sets = discover_language_resource_sets(resource_set("pt_br"))
        self.assertEqual(set(resource_sets), {"pt_br"})

    def test_ignores_set_without_iggyted(self) -> None:
        entries = [*resource_set("de")[:2], *resource_set("fr")]
        resource_sets = discover_language_resource_sets(entries)
        self.assertEqual(set(resource_sets), {"fr"})

    def test_resolves_only_requested_code_present_in_both_archives(self) -> None:
        source = [*resource_set("de"), *resource_set("fr"), *resource_set("pl")]
        current = [*resource_set("de"), *resource_set("fr"), *resource_set("it")]
        targets = resolve_patch_targets(source, current, language_code="fr")
        self.assertEqual(language_codes(targets), ("fr",))
        self.assertEqual(len(targets), 3)
        self.assertTrue(targets[2].source_path.endswith("sysfont01_ab_fr.iggyted"))

    def test_preserves_archive_path_case(self) -> None:
        source = [
            "data/system/iggy/SysFont01_ab_fr.iggy",
            "data/system/iggy/SysFont01_ab_fr.iggytex",
            "data/system/iggy/SysFont01_ab_fr.iggyted",
        ]
        current = list(resource_set("fr"))
        targets = resolve_patch_targets(source, current, language_code="fr")
        self.assertTrue(targets[0].source_path.endswith("SysFont01_ab_fr.iggy"))
        self.assertTrue(targets[0].current_path.endswith("sysfont01_ab_fr.iggy"))
        self.assertTrue(targets[2].source_path.endswith("SysFont01_ab_fr.iggyted"))

    def test_raises_when_requested_resource_set_is_not_shared(self) -> None:
        with self.assertRaises(FixError):
            resolve_patch_targets(
                resource_set("fr"),
                resource_set("de"),
                language_code="fr",
            )

    def test_maps_named_steam_language_to_available_resource_code(self) -> None:
        self.assertEqual(
            resource_code_for_steam_language(
                "french",
                available_codes=("de", "fr", "it"),
            ),
            "fr",
        )

    def test_maps_compound_resource_code_alias(self) -> None:
        self.assertEqual(
            resource_code_for_steam_language(
                "brazilian",
                available_codes=("pt", "pt_br"),
            ),
            "pt_br",
        )

    def test_accepts_exact_resource_code_from_manifest(self) -> None:
        self.assertEqual(
            resource_code_for_steam_language("ru", available_codes=("fr", "ru")),
            "ru",
        )

    def test_rejects_ambiguous_resource_code_aliases(self) -> None:
        with self.assertRaises(FixError):
            resource_code_for_steam_language(
                "german",
                available_codes=("de", "ge"),
            )

    def test_rejects_unmapped_steam_language(self) -> None:
        with self.assertRaises(FixError):
            resource_code_for_steam_language(
                "unknown-language",
                available_codes=("de", "fr"),
            )


if __name__ == "__main__":
    unittest.main()
