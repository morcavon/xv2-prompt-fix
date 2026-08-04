from __future__ import annotations

import io
import subprocess
import sys
import unittest
from contextlib import redirect_stderr
from unittest.mock import patch

from xv2_prompt_fix import __main__ as entrypoint
from xv2_prompt_fix.constants import APP_VERSION


class EntrypointTests(unittest.TestCase):
    def test_module_version_works_without_gui(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "xv2_prompt_fix", "--version"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(APP_VERSION, result.stdout)

    def test_python_version_error_is_printed_once(self) -> None:
        stderr = io.StringIO()
        with (
            patch.object(entrypoint.sys, "version_info", (3, 10, 9)),
            redirect_stderr(stderr),
        ):
            result = entrypoint.main([])

        self.assertEqual(result, 2)
        self.assertEqual(
            stderr.getvalue(),
            "Python 3.11 or newer is required. Current Python: 3.10.9\n",
        )

    def test_windows_requirement_error_is_printed_once(self) -> None:
        stderr = io.StringIO()
        with (
            patch.object(entrypoint.sys, "platform", "linux"),
            redirect_stderr(stderr),
        ):
            result = entrypoint.main([])

        self.assertEqual(result, 2)
        self.assertEqual(
            stderr.getvalue(),
            "This application can only run on Windows 10/11.\n",
        )

    def test_tkinter_error_is_printed_once(self) -> None:
        stderr = io.StringIO()
        missing_tk = ImportError("Tkinter is unavailable", name="_tkinter")
        with (
            patch.object(entrypoint, "_load_gui", side_effect=missing_tk),
            redirect_stderr(stderr),
        ):
            result = entrypoint.main([])

        self.assertEqual(result, 2)
        self.assertEqual(
            stderr.getvalue(),
            "Tkinter is unavailable. Install the Windows build of Python from python.org with Tcl/Tk support.\n",
        )


if __name__ == "__main__":
    unittest.main()
