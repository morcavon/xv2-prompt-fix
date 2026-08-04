from __future__ import annotations

import tempfile
import unittest
from collections.abc import Sequence
from pathlib import Path
from unittest.mock import patch

from cpk_fixture import write_test_cpk_with_entry

from xv2_prompt_fix.constants import MIN_CPK_BYTES
from xv2_prompt_fix.cpk import (
    CpkTool,
    assert_raw_replacement_paths_supported,
    resolve_target_basenames,
)
from xv2_prompt_fix.errors import FixError
from xv2_prompt_fix.cpk_header import inspect_cpk_entry_storage
from xv2_prompt_fix.utils import CancelToken

TARGET_PATHS = (
    "data/system/iggy/sysfont01_ab_fr.iggy",
    "data/system/iggy/sysfont01_ab_fr.iggytex",
)
IGGYTED_PATH = "data/system/iggy/sysfont01_ab_fr.iggyted"


class FakeRunner:
    def __init__(self, listing: str = "") -> None:
        self.listing = listing
        self.commands: list[list[str]] = []

    def run_hidden(
        self,
        args: Sequence[object],
        *,
        cwd: Path,
        monitor_path: Path | None = None,
        expected_bytes: int | None = None,
        progress=None,
    ) -> str:
        command = [str(value) for value in args]
        self.commands.append(command)
        if len(command) == 2:
            return self.listing
        if len(command) == 3:
            internal = command[2].replace("\\", "/")
            output = cwd.joinpath(*internal.split("/"))
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(b"target-data")
            return f"Extracting: {internal}\n"
        if len(command) == 5:
            output = Path(command[1]).parent / command[4]
            with output.open("wb") as stream:
                stream.write(b"CPK ")
                stream.seek(MIN_CPK_BYTES - 1)
                stream.write(b"\0")
            if progress:
                progress(1.0)
            return ""
        raise AssertionError(command)


class CpkToolTests(unittest.TestCase):
    def _tool(self, runner: FakeRunner) -> CpkTool:
        return CpkTool(
            Path("CriPakTools.exe"),
            runner=runner,  # type: ignore[arg-type]
            cancel=CancelToken(),
            log=lambda _text: None,
        )

    def test_target_layout_accepts_unique_paths(self) -> None:
        listing = "CriPakTools\n" + "\n".join(TARGET_PATHS) + "\n"
        tool = self._tool(FakeRunner(listing))
        tool.assert_target_layout(Path("data1.cpk"), TARGET_PATHS, label="test")

    def test_target_layout_rejects_duplicate_basename(self) -> None:
        listing = "\n".join(
            [
                *TARGET_PATHS,
                "other/place/sysfont01_ab_fr.iggy",
            ]
        )
        tool = self._tool(FakeRunner(listing))
        with self.assertRaises(FixError):
            tool.assert_target_layout(Path("data1.cpk"), TARGET_PATHS, label="test")

    def test_resolve_target_basenames_preserves_archive_case(self) -> None:
        entries = [
            TARGET_PATHS[0].replace("sysfont", "SysFont"),
            TARGET_PATHS[1].replace("sysfont", "SysFont"),
        ]
        self.assertEqual(
            resolve_target_basenames(entries, TARGET_PATHS),
            ("SysFont01_ab_fr.iggy", "SysFont01_ab_fr.iggytex"),
        )

    def test_raw_replacement_allows_iggyted_only(self) -> None:
        assert_raw_replacement_paths_supported((IGGYTED_PATH,))

    def test_raw_replacement_rejects_iggy(self) -> None:
        with self.assertRaises(FixError):
            assert_raw_replacement_paths_supported((TARGET_PATHS[0],))

    def test_extract_uses_internal_path(self) -> None:
        runner = FakeRunner()
        tool = self._tool(runner)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            output = tool.extract(Path("data1.cpk"), TARGET_PATHS[0], root)
            self.assertEqual(output.read_bytes(), b"target-data")
            self.assertEqual(runner.commands[-1][2], TARGET_PATHS[0])

    def test_replace_creates_and_validates_output(self) -> None:
        runner = FakeRunner()
        tool = self._tool(runner)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            input_cpk = root / "input.cpk"
            replacement = root / "replacement.bin"
            output_cpk = root / "output.cpk"
            input_cpk.write_bytes(b"input")
            replacement.write_bytes(b"replacement")
            tool.replace(
                input_cpk,
                "sysfont01_ab_fr.iggy",
                replacement,
                output_cpk,
            )
            self.assertTrue(output_cpk.is_file())
            self.assertEqual(runner.commands[-1][-1], "output.cpk")

    def test_raw_replacement_preserves_compression_and_archive_size(self) -> None:
        tool = self._tool(FakeRunner())
        target_raw = b"CRILAYLA" + b"target" * 20
        source_raw = b"CRILAYLA" + b"source" * 10
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            input_cpk = root / "input.cpk"
            source_cpk = root / "source.cpk"
            output_cpk = root / "output.cpk"
            write_test_cpk_with_entry(
                input_cpk,
                internal_path=IGGYTED_PATH,
                raw_payload=target_raw,
                extract_size=900,
            )
            write_test_cpk_with_entry(
                source_cpk,
                internal_path=IGGYTED_PATH,
                raw_payload=source_raw,
                extract_size=700,
            )
            original_size = input_cpk.stat().st_size

            with patch("xv2_prompt_fix.cpk.validate_cpk"):
                tool.replace_raw_compressed_entry(
                    input_cpk,
                    IGGYTED_PATH,
                    source_cpk,
                    IGGYTED_PATH,
                    output_cpk,
                )

            output_entry = inspect_cpk_entry_storage(output_cpk, IGGYTED_PATH)
            self.assertTrue(output_entry.compressed)
            self.assertEqual(output_entry.file_size, len(source_raw))
            self.assertEqual(output_entry.extract_size, 700)
            self.assertEqual(output_cpk.stat().st_size, original_size)
            with output_cpk.open("rb") as stream:
                stream.seek(output_entry.file_offset)
                self.assertEqual(stream.read(len(source_raw)), source_raw)
                self.assertEqual(
                    stream.read(len(target_raw) - len(source_raw)),
                    b"\0" * (len(target_raw) - len(source_raw)),
                )


if __name__ == "__main__":
    unittest.main()
