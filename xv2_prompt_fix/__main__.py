from __future__ import annotations

import argparse
import sys
from collections.abc import Callable

from .constants import APP_NAME, APP_VERSION

MIN_PYTHON = (3, 11)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m xv2_prompt_fix", description=APP_NAME)
    parser.add_argument(
        "--version",
        action="version",
        version=f"{APP_NAME} {APP_VERSION}",
    )
    return parser


def _load_gui() -> Callable[[], None]:
    from .app import run

    return run


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    parser.parse_args(argv)

    if sys.version_info < MIN_PYTHON:
        current = ".".join(str(part) for part in sys.version_info[:3])
        print(
            f"Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} or newer is required. Current Python: {current}",
            file=sys.stderr,
        )
        return 2
    if sys.platform != "win32":
        print(
            "This application can only run on Windows 10/11.",
            file=sys.stderr,
        )
        return 2

    try:
        run = _load_gui()
    except ImportError as exc:
        if exc.name in {"tkinter", "_tkinter"}:
            print(
                "Tkinter is unavailable. Install the Windows build of Python from python.org with Tcl/Tk support.",
                file=sys.stderr,
            )
            return 2
        raise

    run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
