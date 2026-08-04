import tempfile
import unittest
from pathlib import Path

from xv2_prompt_fix.constants import GAME_CPK_REL, GAME_EXE_REL
from xv2_prompt_fix.errors import FixError
from xv2_prompt_fix.steam import (
    parse_build_id,
    parse_installed_language,
    parse_library_paths,
    validate_game_root,
)


class SteamParsingTests(unittest.TestCase):
    def test_parse_build_id(self) -> None:
        text = '"AppState"\n{\n  "buildid"  "23988437"\n}'
        self.assertEqual(parse_build_id(text), "23988437")

    def test_parse_installed_language_prefers_mounted_config(self) -> None:
        text = '''
        "UserConfig" { "language" "english" }
        "MountedConfig" { "language" "french" }
        '''
        self.assertEqual(parse_installed_language(text), "french")

    def test_parse_installed_language_returns_none_when_missing(self) -> None:
        self.assertIsNone(parse_installed_language('"AppState" { }'))

    def test_parse_library_paths(self) -> None:
        text = r'''
        "libraryfolders"
        {
          "0" { "path" "C:\\Program Files (x86)\\Steam" }
          "1" { "path" "D:\\SteamLibrary" }
        }
        '''
        self.assertEqual(
            parse_library_paths(text),
            [Path(r"C:\Program Files (x86)\Steam"), Path(r"D:\SteamLibrary")],
        )

    def test_validate_game_root_accepts_cpk_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "DB Xenoverse 2"
            (root / GAME_EXE_REL).parent.mkdir(parents=True)
            (root / GAME_EXE_REL).write_bytes(b"MZ")
            cpk = root / GAME_CPK_REL
            cpk.parent.mkdir(parents=True, exist_ok=True)
            # Validation requires a realistic minimum size, so use a sparse file.
            with cpk.open("wb") as stream:
                stream.write(b"CPK ")
                stream.seek(512 * 1024 * 1024 - 1)
                stream.write(b"\0")
            validated_root, validated_cpk = validate_game_root(cpk)
            self.assertEqual(validated_root, root.resolve())
            self.assertEqual(validated_cpk, cpk.resolve())

    def test_validate_game_root_rejects_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as temp, self.assertRaises(FixError):
            validate_game_root(Path(temp))


if __name__ == "__main__":
    unittest.main()
