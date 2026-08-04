from __future__ import annotations

import hashlib
import os
import shutil
import stat
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .constants import (
    APP_VERSION,
    DOWNLOAD_CHUNK_BYTES,
    EXTERNAL_TOOLS_MANIFEST,
)
from .errors import CancelledError, FixError
from .i18n import tr
from .utils import (
    CancelToken,
    app_data_dir,
    atomic_write_json,
    format_bytes,
    iso_now,
    read_json,
    sanitize_log_text,
    sha256_file,
    validate_pe,
    windows_system_executable,
)

LogCallback = Callable[[str], None]
FractionCallback = Callable[[float], None]
_HEX_DIGITS = frozenset("0123456789abcdef")
_ALLOWED_DOWNLOAD_HOSTS = frozenset({"github.com", "raw.githubusercontent.com"})


@dataclass(frozen=True, slots=True)
class ToolSpec:
    key: str
    display_name: str
    version: str
    download_url: str
    download_size: int
    download_sha256: str
    archive_member: str | None
    executable_name: str
    executable_size: int
    executable_sha256: str
    pe_machine: str
    license: str


class ProcessController:
    def __init__(self, cancel: CancelToken) -> None:
        self.cancel = cancel
        self._lock = threading.Lock()
        self._active: subprocess.Popen[bytes] | subprocess.Popen[str] | None = None

    def _set_active(self, proc: subprocess.Popen[bytes] | subprocess.Popen[str] | None) -> None:
        with self._lock:
            self._active = proc

    def terminate_active(self) -> None:
        self.cancel.cancel()
        with self._lock:
            proc = self._active
        if proc is None or proc.poll() is not None:
            return
        if os.name == "nt":
            try:
                subprocess.run(
                    [str(windows_system_executable("taskkill.exe")), "/PID", str(proc.pid), "/T", "/F"],
                    check=False,
                    capture_output=True,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                return
            except (OSError, FixError):
                pass
        try:
            proc.terminate()
        except OSError:
            pass

    def run_hidden(
        self,
        args: Sequence[str | os.PathLike[str]],
        *,
        cwd: Path,
        monitor_path: Path | None = None,
        expected_bytes: int | None = None,
        progress: FractionCallback | None = None,
    ) -> str:
        self.cancel.check()
        command = [str(arg) for arg in args]
        if not command:
            raise FixError(tr("The external tool command is empty."))
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        with tempfile.TemporaryFile(mode="w+b") as output:
            try:
                proc = subprocess.Popen(
                    command,
                    cwd=str(cwd),
                    stdin=subprocess.DEVNULL,
                    stdout=output,
                    stderr=subprocess.STDOUT,
                    creationflags=creationflags,
                )
            except OSError as exc:
                raise FixError(
                    tr(
                        "The external tool could not be started: {tool}\n{error}",
                        tool=Path(command[0]).name,
                        error=exc,
                    )
                ) from exc
            self._set_active(proc)
            try:
                while proc.poll() is None:
                    if self.cancel.cancelled:
                        self.terminate_active()
                        raise CancelledError(tr("The operation was cancelled by the user."))
                    if monitor_path and expected_bytes and progress:
                        try:
                            ratio = monitor_path.stat().st_size / expected_bytes
                        except OSError:
                            ratio = 0.0
                        progress(max(0.0, min(ratio, 0.99)))
                    time.sleep(0.4)
                return_code = proc.returncode
            finally:
                self._set_active(None)
            output.seek(0)
            text = output.read().decode("utf-8", errors="replace")
        if progress:
            progress(1.0)
        if return_code != 0:
            tail = sanitize_log_text("\n".join(text.splitlines()[-30:]))
            raise FixError(
                tr(
                    "The external tool exited with error code {code}.\nTool: {tool}\n\n{tail}",
                    code=return_code,
                    tool=Path(command[0]).name,
                    tail=tail,
                )
            )
        return text

    def run_new_console(
        self,
        args: Sequence[str | os.PathLike[str]],
        *,
        cwd: Path,
        monitor_path: Path | None = None,
        expected_bytes: int | None = None,
        progress: FractionCallback | None = None,
    ) -> None:
        self.cancel.check()
        if os.name != "nt":
            raise FixError(tr("Steam QR download can only run on Windows."))
        command = [str(arg) for arg in args]
        if not command:
            raise FixError(tr("The DepotDownloader command is empty."))
        flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0) | getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0
        )
        try:
            proc = subprocess.Popen(command, cwd=str(cwd), creationflags=flags)
        except OSError as exc:
            raise FixError(tr("DepotDownloader could not be started.\n{error}", error=exc)) from exc
        self._set_active(proc)
        try:
            while proc.poll() is None:
                if self.cancel.cancelled:
                    self.terminate_active()
                    raise CancelledError(tr("The operation was cancelled by the user."))
                if monitor_path and expected_bytes and progress:
                    try:
                        ratio = monitor_path.stat().st_size / expected_bytes
                    except OSError:
                        ratio = 0.0
                    progress(max(0.0, min(ratio, 0.99)))
                time.sleep(0.5)
            return_code = proc.returncode
        finally:
            self._set_active(None)
        if progress:
            progress(1.0)
        if return_code != 0:
            raise FixError(
                tr(
                    "DepotDownloader did not complete successfully. Exit code: {code}\nCheck whether QR approval was cancelled, the Steam account does not own the game, or access to the older manifest is blocked.",
                    code=return_code,
                )
            )


class ToolManager:
    def __init__(
        self,
        *,
        cancel: CancelToken,
        log: LogCallback,
        progress: FractionCallback | None = None,
    ) -> None:
        self.cancel = cancel
        self.log = log
        self.progress = progress
        self.root = app_data_dir() / "tools"
        self.root.mkdir(parents=True, exist_ok=True)
        self.specs = load_tool_specs()

    def _download(self, spec: ToolSpec, destination: Path) -> None:
        self.cancel.check()
        _validate_https_url(spec.download_url)
        destination.parent.mkdir(parents=True, exist_ok=True)
        part = destination.with_suffix(destination.suffix + ".part")
        part.unlink(missing_ok=True)
        request = urllib.request.Request(
            spec.download_url,
            headers={
                "User-Agent": f"XV2PromptFix/{APP_VERSION} (+source-only-local-tool)",
                "Accept": "*/*",
            },
        )
        self.log(tr("Downloading pinned official {tool}", tool=spec.display_name))
        digest = hashlib.sha256()
        done = 0
        try:
            # URL host/scheme are validated before the request and after redirects.
            with (
                urllib.request.urlopen(request, timeout=45) as response,  # nosec B310
                part.open("wb") as out,
            ):
                final_url = response.geturl()
                _validate_https_url(final_url)
                length_header = response.headers.get("Content-Length")
                if length_header and length_header.isdigit():
                    reported = int(length_header)
                    if reported != spec.download_size:
                        raise FixError(
                            tr(
                                "The {tool} download size differs from the pinned value: expected={expected}, reported={reported}",
                                tool=spec.display_name,
                                expected=spec.download_size,
                                reported=reported,
                            )
                        )
                while True:
                    self.cancel.check()
                    chunk = response.read(DOWNLOAD_CHUNK_BYTES)
                    if not chunk:
                        break
                    done += len(chunk)
                    if done > spec.download_size:
                        raise FixError(
                            tr(
                                "The {tool} download exceeded the expected size.",
                                tool=spec.display_name,
                            )
                        )
                    digest.update(chunk)
                    out.write(chunk)
                    if self.progress and spec.download_size:
                        self.progress(min(done / spec.download_size, 1.0))
        except CancelledError:
            part.unlink(missing_ok=True)
            raise
        except FixError:
            part.unlink(missing_ok=True)
            raise
        except (OSError, urllib.error.URLError) as exc:
            part.unlink(missing_ok=True)
            raise FixError(tr("The {tool} download failed.\n{error}", tool=spec.display_name, error=exc)) from exc

        actual_hash = digest.hexdigest()
        if done != spec.download_size or actual_hash != spec.download_sha256:
            part.unlink(missing_ok=True)
            raise FixError(
                tr(
                    "The {tool} download failed integrity verification.\nexpected_size={expected_size}, actual_size={actual_size}\nexpected_sha256={expected_hash}\nactual_sha256={actual_hash}",
                    tool=spec.display_name,
                    expected_size=spec.download_size,
                    actual_size=done,
                    expected_hash=spec.download_sha256,
                    actual_hash=actual_hash,
                )
            )
        os.replace(part, destination)
        if self.progress:
            self.progress(1.0)
        self.log(
            tr(
                "{tool} download verified: {size}, SHA-256={hash}",
                tool=spec.display_name,
                size=format_bytes(done),
                hash=actual_hash,
            )
        )

    def ensure_cripaktools(self) -> Path:
        spec = self.specs["cripaktools"]
        target = self.root / "cripaktools" / spec.executable_name
        if target.is_file():
            try:
                self._verify_executable(target, spec)
                return target
            except FixError as exc:
                self.log(tr("CriPakTools cache verification failed; downloading again: {error}", error=exc))
                target.unlink(missing_ok=True)
        self._download(spec, target)
        self._verify_executable(target, spec)
        self._write_metadata(target.parent, spec)
        return target

    def ensure_depot_downloader(self) -> Path:
        spec = self.specs["depot_downloader"]
        folder = self.root / f"depotdownloader-{spec.version}"
        target = folder / spec.executable_name
        if target.is_file():
            try:
                self._verify_executable(target, spec)
                return target
            except FixError as exc:
                self.log(tr("DepotDownloader cache verification failed; downloading again: {error}", error=exc))
                shutil.rmtree(folder, ignore_errors=True)

        archive_path = self.root / f"DepotDownloader-{spec.version}.zip"
        self._download(spec, archive_path)
        temp_folder = folder.with_name(folder.name + ".extracting")
        shutil.rmtree(temp_folder, ignore_errors=True)
        temp_folder.mkdir(parents=True, exist_ok=False)
        try:
            with zipfile.ZipFile(archive_path) as archive:
                bad = archive.testzip()
                if bad:
                    raise FixError(tr("The DepotDownloader ZIP is corrupted: {entry}", entry=bad))
                member = self._resolve_archive_member(archive, spec)
                output = temp_folder / spec.executable_name
                with archive.open(member, "r") as source, output.open("wb") as destination:
                    shutil.copyfileobj(source, destination, length=DOWNLOAD_CHUNK_BYTES)
                self._verify_executable(output, spec)
            if folder.exists():
                shutil.rmtree(folder, ignore_errors=True)
            os.replace(temp_folder, folder)
        except CancelledError:
            raise
        except FixError:
            raise
        except (OSError, zipfile.BadZipFile) as exc:
            raise FixError(tr("Failed to extract the DepotDownloader ZIP.\n{error}", error=exc)) from exc
        finally:
            archive_path.unlink(missing_ok=True)
            if temp_folder.exists():
                shutil.rmtree(temp_folder, ignore_errors=True)

        self._verify_executable(target, spec)
        self._write_metadata(folder, spec)
        return target

    def _verify_executable(self, path: Path, spec: ToolSpec) -> None:
        if not path.is_file():
            raise FixError(tr("The {tool} executable was not found.", tool=spec.display_name))
        actual_size = path.stat().st_size
        if actual_size != spec.executable_size:
            raise FixError(
                tr(
                    "The {tool} executable size differs from the expected value: expected={expected}, actual={actual}",
                    tool=spec.display_name,
                    expected=spec.executable_size,
                    actual=actual_size,
                )
            )
        actual_hash = sha256_file(path, cancel=self.cancel)
        if actual_hash != spec.executable_sha256:
            raise FixError(
                tr(
                    "The {tool} executable SHA-256 differs from the expected value: expected={expected}, actual={actual}",
                    tool=spec.display_name,
                    expected=spec.executable_sha256,
                    actual=actual_hash,
                )
            )
        validate_pe(path, label=spec.display_name, expected_machine=spec.pe_machine)

    @staticmethod
    def _resolve_archive_member(archive: zipfile.ZipFile, spec: ToolSpec) -> zipfile.ZipInfo:
        if spec.archive_member is None:
            raise FixError(tr("The executable member is not configured for the {tool} ZIP.", tool=spec.display_name))
        expected = PurePosixPath(spec.archive_member).as_posix().casefold()
        matches: list[zipfile.ZipInfo] = []
        for member in archive.infolist():
            normalized = PurePosixPath(member.filename.replace("\\", "/"))
            has_drive_prefix = bool(normalized.parts and normalized.parts[0].endswith(":"))
            if normalized.is_absolute() or has_drive_prefix or ".." in normalized.parts:
                raise FixError(tr("The {tool} ZIP contains an unsafe path: {name}", tool=spec.display_name, name=member.filename))
            if "\x00" in member.filename or ":" in member.filename:
                raise FixError(tr("The {tool} ZIP contains a disallowed filename: {name}", tool=spec.display_name, name=member.filename))
            mode = (member.external_attr >> 16) & 0xFFFF
            if stat.S_ISLNK(mode):
                raise FixError(tr("The {tool} ZIP contains a symbolic link: {name}", tool=spec.display_name, name=member.filename))
            if normalized.as_posix().casefold() == expected:
                matches.append(member)
        if len(matches) != 1:
            raise FixError(
                tr(
                    "Exactly one executable was not found in the {tool} ZIP: {member} (found {count})",
                    tool=spec.display_name,
                    member=spec.archive_member,
                    count=len(matches),
                )
            )
        return matches[0]

    def _write_metadata(self, directory: Path, spec: ToolSpec) -> None:
        try:
            metadata = {
                "tool": spec.display_name,
                "version": spec.version,
                "source_url": spec.download_url,
                "size": spec.executable_size,
                "expected_sha256": spec.executable_sha256,
                "actual_sha256": spec.executable_sha256,
                "verified_at": iso_now(),
            }
            atomic_write_json(directory / "download-metadata.json", metadata)
        except (OSError, TypeError, ValueError) as exc:
            self.log(tr("Tool metadata save warning: {error}", error=exc))


def load_tool_specs() -> dict[str, ToolSpec]:
    manifest_path = Path(__file__).with_name(EXTERNAL_TOOLS_MANIFEST)
    data = read_json(manifest_path)
    if data.get("schema_version") != 1 or not isinstance(data.get("tools"), dict):
        raise FixError(tr("The external tool manifest format is invalid."))
    specs: dict[str, ToolSpec] = {}
    for key, raw in data["tools"].items():
        if not isinstance(key, str) or not isinstance(raw, dict):
            raise FixError(tr("An external tool manifest entry has an invalid format."))
        try:
            spec = ToolSpec(key=key, **raw)
        except TypeError as exc:
            raise FixError(tr("The external tool manifest fields are invalid: {key}", key=key)) from exc
        _validate_tool_spec(spec)
        specs[key] = spec
    required = {"cripaktools", "depot_downloader"}
    if set(specs) != required:
        raise FixError(tr("The external tool manifest entries differ from the expected set: {items}", items=sorted(specs)))
    return specs


def _validate_tool_spec(spec: ToolSpec) -> None:
    _validate_https_url(spec.download_url)
    if spec.download_size < 1 or spec.executable_size < 4096:
        raise FixError(tr("The {tool} size configuration is invalid.", tool=spec.display_name))
    for label, value in (
        ("download_sha256", spec.download_sha256),
        ("executable_sha256", spec.executable_sha256),
    ):
        if len(value) != 64 or any(char not in _HEX_DIGITS for char in value.casefold()):
            raise FixError(tr("The {tool} {label} configuration is invalid.", tool=spec.display_name, label=label))
    if spec.pe_machine not in {"x86", "x64"}:
        raise FixError(tr("The {tool} PE architecture configuration is invalid.", tool=spec.display_name))
    if Path(spec.executable_name).name != spec.executable_name:
        raise FixError(tr("The {tool} executable filename is unsafe.", tool=spec.display_name))


def _validate_https_url(url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    hostname = (parsed.hostname or "").casefold()
    allowed_host = hostname in _ALLOWED_DOWNLOAD_HOSTS or hostname.endswith(
        ".githubusercontent.com"
    )
    if parsed.scheme.casefold() != "https" or not allowed_host or parsed.username or parsed.password:
        raise FixError(tr("This external tool URL is not allowed: {url}", url=url))
