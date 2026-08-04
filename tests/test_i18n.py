from __future__ import annotations

import unittest

from xv2_prompt_fix.i18n import (
    available_languages,
    get_language,
    language_from_name,
    language_name,
    set_language,
    tr,
)


class I18nTests(unittest.TestCase):
    def tearDown(self) -> None:
        set_language("ko")

    def test_korean_is_default_and_uses_external_catalog(self) -> None:
        set_language("ko")

        self.assertEqual(get_language(), "ko")
        self.assertEqual(
            tr("Ready").encode("unicode_escape"),
            b"\\ub300\\uae30 \\uc911",
        )

    def test_english_translation_and_formatting(self) -> None:
        set_language("en")

        self.assertEqual(
            tr(
                "Found {count} game installation candidates and selected the first one.",
                count=3,
            ),
            "Found 3 game installation candidates and selected the first one.",
        )

    def test_language_display_names_round_trip(self) -> None:
        self.assertEqual(available_languages(), ("ko", "en"))
        self.assertEqual(
            language_name("ko").encode("unicode_escape"),
            b"\\ud55c\\uad6d\\uc5b4",
        )
        self.assertEqual(language_from_name(language_name("ko")), "ko")
        self.assertEqual(language_from_name(language_name("en")), "en")

    def test_rejects_unknown_language(self) -> None:
        with self.assertRaises(ValueError):
            set_language("fr")  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            language_from_name("Unsupported")


if __name__ == "__main__":
    unittest.main()
