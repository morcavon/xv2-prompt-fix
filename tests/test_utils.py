import tempfile
import unittest
from pathlib import Path

from xv2_prompt_fix.errors import CancelledError
from xv2_prompt_fix.utils import CancelToken, format_bytes, sha256_file


class UtilsTests(unittest.TestCase):
    def test_format_bytes(self) -> None:
        self.assertEqual(format_bytes(1024), "1.00 KiB")
        self.assertEqual(format_bytes(1024**3), "1.00 GiB")

    def test_sha256(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "sample.bin"
            path.write_bytes(b"abc")
            self.assertEqual(
                sha256_file(path),
                "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
            )

    def test_cancel_token(self) -> None:
        token = CancelToken()
        token.cancel()
        with self.assertRaises(CancelledError):
            token.check()


if __name__ == "__main__":
    unittest.main()
