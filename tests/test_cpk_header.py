from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cpk_fixture import write_test_cpk, write_test_cpk_with_entry

from xv2_prompt_fix.cpk_header import (
    assert_cpk_header_geometry,
    inspect_cpk_entry_storage,
    inspect_cpk_header_geometry,
    repair_cpk_header_geometry,
    update_cpk_entry_sizes,
)
from xv2_prompt_fix.errors import FixError


class CpkHeaderGeometryTests(unittest.TestCase):
    def test_valid_encrypted_header_matches_archive_geometry(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "valid.cpk"
            write_test_cpk(path, content_size=0x2000)

            geometry = assert_cpk_header_geometry(path, label="test CPK")

            self.assertTrue(geometry.valid)
            self.assertTrue(geometry.encrypted)
            self.assertEqual(geometry.content_offset, 0x1000)
            self.assertEqual(geometry.content_size, 0x2000)
            self.assertEqual(geometry.expected_content_size, 0x2000)
            self.assertEqual(geometry.align, 0x800)

    def test_repair_updates_only_stale_content_size_value(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "stale.cpk"
            write_test_cpk(path, content_size=0x1800)
            original = path.read_bytes()

            before, after = repair_cpk_header_geometry(path)

            self.assertFalse(before.valid)
            self.assertEqual(before.content_size, 0x1800)
            self.assertTrue(after.valid)
            self.assertEqual(after.content_size, 0x2000)
            repaired = path.read_bytes()
            changed = [
                index
                for index, (old, new) in enumerate(zip(original, repaired))
                if old != new
            ]
            expected_positions = set(
                range(
                    16 + before.content_size_position,
                    16 + before.content_size_position + 8,
                )
            )
            self.assertTrue(changed)
            self.assertTrue(set(changed).issubset(expected_positions))

    def test_unencrypted_header_is_supported(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "plain.cpk"
            write_test_cpk(path, content_size=0x2000, encrypted=False)

            geometry = inspect_cpk_header_geometry(path)

            self.assertTrue(geometry.valid)
            self.assertFalse(geometry.encrypted)

    def test_assert_rejects_stale_content_size(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "stale.cpk"
            write_test_cpk(path, content_size=0x1800)

            with self.assertRaisesRegex(FixError, "ContentSize"):
                assert_cpk_header_geometry(path, label="test CPK")

    def test_rejects_invalid_utf_packet(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "invalid.cpk"
            path.write_bytes(b"CPK " + b"\0" * 4 + (32).to_bytes(8, "little") + b"x" * 64)

            with self.assertRaises(FixError):
                inspect_cpk_header_geometry(path)

    def test_inspects_and_updates_compressed_toc_entry_sizes(self) -> None:
        internal_path = "data/system/iggy/sysfont01_ab_fr.iggyted"
        raw = b"CRILAYLA" + b"x" * 40
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "entry.cpk"
            write_test_cpk_with_entry(
                path,
                internal_path=internal_path,
                raw_payload=raw,
                extract_size=400,
            )

            entry = inspect_cpk_entry_storage(path, internal_path)

            self.assertTrue(entry.compressed)
            self.assertEqual(entry.file_offset, 0x1000)
            self.assertEqual(entry.file_size, len(raw))
            self.assertEqual(entry.extract_size, 400)

            before, after = update_cpk_entry_sizes(
                path,
                internal_path,
                file_size=len(raw) - 8,
                extract_size=320,
            )

            self.assertEqual(before.file_size, len(raw))
            self.assertEqual(after.file_size, len(raw) - 8)
            self.assertEqual(after.extract_size, 320)


if __name__ == "__main__":
    unittest.main()
