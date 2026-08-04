from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import struct
import tempfile
import threading
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .constants import APP_DATA_DIR_NAME, HASH_CHUNK_BYTES, MIN_CPK_BYTES
from .errors import CancelledError, FixError
from .i18n import tr

ProgressCallback = Callable[[float], None]
PE_MACHINE_TYPES = {"x86": 0x014C, "x64": 0x8664}


class CancelToken:
    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def check(self) -> None:
        if self.cancelled:
            raise CancelledError(
                tr("The operation was cancelled by the user.")
            )


def app_data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base) / APP_DATA_DIR_NAME
    return Path.home() / ".xv2_prompt_fix"


def timestamp() -> str:
    return datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")


def iso_now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def format_bytes(value: int) -> str:
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    size = float(value)
    for unit in units:
        if abs(size) < 1024.0 or unit == units[-1]:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} TiB"


def sha256_file(
    path: Path,
    *,
    cancel: CancelToken | None = None,
    progress: ProgressCallback | None = None,
) -> str:
    total = path.stat().st_size
    done = 0
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            if cancel:
                cancel.check()
            chunk = stream.read(HASH_CHUNK_BYTES)
            if not chunk:
                break
            digest.update(chunk)
            done += len(chunk)
            if progress and total:
                progress(min(done / total, 1.0))
    if progress:
        progress(1.0)
    return digest.hexdigest()


def validate_cpk(path: Path, *, label: str = "CPK") -> None:
    if not path.is_file():
        raise FixError(
            tr(
                "The {label} file was not found: {path}",
                label=label,
                path=path,
            )
        )
    size = path.stat().st_size
    if size < MIN_CPK_BYTES:
        raise FixError(
            tr(
                "The {label} file is unexpectedly small: {size} ({name})",
                label=label,
                size=format_bytes(size),
                name=path.name,
            )
        )
    with path.open("rb") as stream:
        magic = stream.read(4)
    if magic != b"CPK ":
        raise FixError(
            tr(
                "The {label} header does not match the CPK format: {magic!r} ({name})",
                label=label,
                magic=magic,
                name=path.name,
            )
        )


def validate_pe(path: Path, *, label: str, expected_machine: str | None = None) -> None:
    if not path.is_file() or path.stat().st_size < 4096:
        raise FixError(
            tr(
                "The downloaded {label} file is invalid: {name}",
                label=label,
                name=path.name,
            )
        )
    try:
        with path.open("rb") as stream:
            if stream.read(2) != b"MZ":
                raise FixError(
                    tr(
                        "The {label} file is not a Windows executable.",
                        label=label,
                    )
                )
            stream.seek(0x3C)
            raw_offset = stream.read(4)
            if len(raw_offset) != 4:
                raise FixError(
                    tr(
                        "The {label} PE header offset could not be read.",
                        label=label,
                    )
                )
            pe_offset = struct.unpack("<I", raw_offset)[0]
            if pe_offset < 0x40 or pe_offset > path.stat().st_size - 24:
                raise FixError(
                    tr(
                        "The {label} PE header offset is invalid.",
                        label=label,
                    )
                )
            stream.seek(pe_offset)
            if stream.read(4) != b"PE\0\0":
                raise FixError(
                    tr(
                        "The {label} PE header signature is invalid.",
                        label=label,
                    )
                )
            raw_machine = stream.read(2)
            if len(raw_machine) != 2:
                raise FixError(
                    tr(
                        "The {label} PE architecture could not be read.",
                        label=label,
                    )
                )
            machine = struct.unpack("<H", raw_machine)[0]
    except OSError as exc:
        raise FixError(
            tr(
                "The {label} executable could not be inspected: {error}",
                label=label,
                error=exc,
            )
        ) from exc

    if expected_machine is not None:
        expected = PE_MACHINE_TYPES.get(expected_machine)
        if expected is None:
            raise FixError(
                tr(
                    "Unsupported PE architecture setting: {machine}",
                    machine=expected_machine,
                )
            )
        if machine != expected:
            raise FixError(
                tr(
                    "The {label} PE architecture differs from the expected value: expected={expected}, actual=0x{actual:04x}",
                    label=label,
                    expected=expected_machine,
                    actual=machine,
                )
            )


def atomic_write_json(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def read_json(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as stream:
            data = json.load(stream)
    except FileNotFoundError:
        raise
    except (OSError, json.JSONDecodeError) as exc:
        raise FixError(
            tr(
                "The JSON file could not be read: {name}\n{error}",
                name=path.name,
                error=exc,
            )
        ) from exc
    if not isinstance(data, dict):
        raise FixError(
            tr(
                "The JSON file format is invalid: {name}",
                name=path.name,
            )
        )
    return data


def safe_rmtree(path: Path) -> None:
    if not path.exists():
        return

    def onerror(func: object, target: str, exc_info: object) -> None:
        try:
            os.chmod(target, 0o700)
            func(target)  # type: ignore[misc,operator]
        except (OSError, TypeError):
            return

    shutil.rmtree(path, onerror=onerror)


def ensure_writable_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    try:
        fd, temp_name = tempfile.mkstemp(prefix=".xv2promptfix-write-test-", dir=str(path))
        os.close(fd)
        os.unlink(temp_name)
    except OSError as exc:
        raise FixError(
            tr(
                "The game CPK folder is not writable. Check the Steam library permissions.",
            )
        ) from exc


def normalized_path(path: Path) -> str:
    try:
        return str(path.resolve()).casefold()
    except OSError:
        return str(path.absolute()).casefold()


def windows_system_executable(name: str) -> Path:
    if os.name != "nt":
        return Path(name)
    system_root = os.environ.get("SystemRoot")
    if not system_root:
        raise FixError(
            tr(
                "The Windows SystemRoot environment variable was not found.",
            )
        )
    candidate = Path(system_root) / "System32" / name
    if not candidate.is_file():
        raise FixError(
            tr(
                "The Windows system executable was not found: {name}",
                name=name,
            )
        )
    return candidate


def sanitize_log_text(text: str) -> str:
    replacements: list[tuple[str, str]] = []
    for env_name, token in (
        ("LOCALAPPDATA", "%LOCALAPPDATA%"),
        ("APPDATA", "%APPDATA%"),
        ("USERPROFILE", "%USERPROFILE%"),
        ("TEMP", "%TEMP%"),
        ("TMP", "%TEMP%"),
    ):
        value = os.environ.get(env_name)
        if value:
            replacements.append((value, token))
    try:
        replacements.append((str(Path.home()), "%USERPROFILE%"))
    except RuntimeError:
        pass

    sanitized = text
    for raw, token in sorted(replacements, key=lambda item: len(item[0]), reverse=True):
        if not raw:
            continue
        sanitized = re.sub(re.escape(raw), token, sanitized, flags=re.IGNORECASE)
    return sanitized


def prune_old_logs(
    directory: Path,
    *,
    max_files: int,
    max_age_days: int,
    now: datetime | None = None,
) -> None:
    if max_files < 1 or max_age_days < 1:
        raise ValueError(
            tr(
                "Log retention limits must be at least 1.",
            )
        )
    directory.mkdir(parents=True, exist_ok=True)
    current = now or datetime.now().astimezone()
    cutoff = current - timedelta(days=max_age_days)
    files = sorted(
        (item for item in directory.glob("session-*.log") if item.is_file()),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    for index, item in enumerate(files):
        try:
            modified = datetime.fromtimestamp(item.stat().st_mtime, tz=current.tzinfo)
            if index >= max_files or modified < cutoff:
                item.unlink()
        except OSError:
            continue
