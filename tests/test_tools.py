from __future__ import annotations

import hashlib
import io
import struct
import tempfile
import unittest
import zipfile
from pathlib import Path
from typing import Self
from unittest.mock import patch

from xv2_prompt_fix.errors import FixError
from xv2_prompt_fix.tools import (
    ToolManager,
    ToolSpec,
    _validate_https_url,
    load_tool_specs,
)
from xv2_prompt_fix.utils import CancelToken


def make_pe(machine: int) -> bytes:
    data = bytearray(4096)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 0x3C, 0x80)
    data[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<H", data, 0x84, machine)
    return bytes(data)


def make_spec(data: bytes, *, machine: str = "x64") -> ToolSpec:
    digest = hashlib.sha256(data).hexdigest()
    return ToolSpec(
        key="test",
        display_name="TestTool",
        version="1",
        download_url="https://github.com/example/test/releases/download/1/test.exe",
        download_size=len(data),
        download_sha256=digest,
        archive_member="TestTool.exe",
        executable_name="TestTool.exe",
        executable_size=len(data),
        executable_sha256=digest,
        pe_machine=machine,
        license="MIT",
    )


class FakeResponse:
    def __init__(self, data: bytes, *, final_url: str) -> None:
        self._stream = io.BytesIO(data)
        self._final_url = final_url
        self.headers = {"Content-Length": str(len(data))}

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        self._stream.close()

    def read(self, size: int = -1) -> bytes:
        return self._stream.read(size)

    def geturl(self) -> str:
        return self._final_url


class ToolManagerTests(unittest.TestCase):
    def test_manifest_contains_pinned_tools(self) -> None:
        specs = load_tool_specs()
        self.assertEqual(set(specs), {"cripaktools", "depot_downloader"})
        for spec in specs.values():
            self.assertEqual(len(spec.download_sha256), 64)
            self.assertEqual(len(spec.executable_sha256), 64)
            self.assertTrue(spec.download_url.startswith("https://"))

    def test_archive_member_is_resolved_without_extractall(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            archive_path = Path(temp) / "sample.zip"
            data = make_pe(0x8664)
            spec = make_spec(data)
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("TestTool.exe", data)
            with zipfile.ZipFile(archive_path) as archive:
                member = ToolManager._resolve_archive_member(archive, spec)
            self.assertEqual(member.filename, "TestTool.exe")

    def test_archive_rejects_parent_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            archive_path = Path(temp) / "sample.zip"
            data = make_pe(0x8664)
            spec = make_spec(data)
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("../outside.exe", b"bad")
                archive.writestr("TestTool.exe", data)
            with (
                zipfile.ZipFile(archive_path) as archive,
                self.assertRaises(FixError),
            ):
                ToolManager._resolve_archive_member(archive, spec)

    def test_archive_rejects_duplicate_casefolded_member(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            archive_path = Path(temp) / "sample.zip"
            data = make_pe(0x8664)
            spec = make_spec(data)
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("TestTool.exe", data)
                archive.writestr("testtool.EXE", data)
            with (
                zipfile.ZipFile(archive_path) as archive,
                self.assertRaises(FixError),
            ):
                ToolManager._resolve_archive_member(archive, spec)

    def test_executable_verification_checks_hash_and_machine(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "TestTool.exe"
            data = make_pe(0x8664)
            path.write_bytes(data)
            manager = object.__new__(ToolManager)
            manager.cancel = CancelToken()
            manager._verify_executable(path, make_spec(data))
            path.write_bytes(data[:-1] + b"x")
            with self.assertRaises(FixError):
                manager._verify_executable(path, make_spec(data))

    def test_download_verifies_hash_and_removes_failed_partial(self) -> None:
        data = b"verified payload"
        spec = make_spec(make_pe(0x8664))
        spec = ToolSpec(
            key=spec.key,
            display_name=spec.display_name,
            version=spec.version,
            download_url=spec.download_url,
            download_size=len(data),
            download_sha256=hashlib.sha256(data).hexdigest(),
            archive_member=spec.archive_member,
            executable_name=spec.executable_name,
            executable_size=spec.executable_size,
            executable_sha256=spec.executable_sha256,
            pe_machine=spec.pe_machine,
            license=spec.license,
        )
        manager = object.__new__(ToolManager)
        manager.cancel = CancelToken()
        manager.progress = None
        manager.log = lambda _text: None
        with tempfile.TemporaryDirectory() as temp:
            destination = Path(temp) / "payload.bin"
            with patch(
                "xv2_prompt_fix.tools.urllib.request.urlopen",
                return_value=FakeResponse(data, final_url=spec.download_url),
            ):
                manager._download(spec, destination)
            self.assertEqual(destination.read_bytes(), data)

            bad_spec = ToolSpec(
                key=spec.key,
                display_name=spec.display_name,
                version=spec.version,
                download_url=spec.download_url,
                download_size=spec.download_size,
                download_sha256="0" * 64,
                archive_member=spec.archive_member,
                executable_name=spec.executable_name,
                executable_size=spec.executable_size,
                executable_sha256=spec.executable_sha256,
                pe_machine=spec.pe_machine,
                license=spec.license,
            )
            destination.unlink()
            with (
                patch(
                    "xv2_prompt_fix.tools.urllib.request.urlopen",
                    return_value=FakeResponse(data, final_url=spec.download_url),
                ),
                self.assertRaises(FixError),
            ):
                manager._download(bad_spec, destination)
            self.assertFalse(destination.exists())
            self.assertFalse(destination.with_suffix(".bin.part").exists())

    def test_download_rejects_unapproved_final_redirect(self) -> None:
        data = b"verified payload"
        base = make_spec(make_pe(0x8664))
        spec = ToolSpec(
            key=base.key,
            display_name=base.display_name,
            version=base.version,
            download_url=base.download_url,
            download_size=len(data),
            download_sha256=hashlib.sha256(data).hexdigest(),
            archive_member=base.archive_member,
            executable_name=base.executable_name,
            executable_size=base.executable_size,
            executable_sha256=base.executable_sha256,
            pe_machine=base.pe_machine,
            license=base.license,
        )
        manager = object.__new__(ToolManager)
        manager.cancel = CancelToken()
        manager.progress = None
        manager.log = lambda _text: None
        with tempfile.TemporaryDirectory() as temp:
            destination = Path(temp) / "payload.bin"
            with (
                patch(
                    "xv2_prompt_fix.tools.urllib.request.urlopen",
                    return_value=FakeResponse(data, final_url="https://example.com/payload"),
                ),
                self.assertRaises(FixError),
            ):
                manager._download(spec, destination)
            self.assertFalse(destination.exists())

    def test_non_https_or_unapproved_host_is_rejected(self) -> None:
        for url in (
            "http://github.com/example/tool.exe",
            "https://example.com/tool.exe",
            "https://user:pass" + "@github.com/tool.exe",
        ):
            with self.subTest(url=url), self.assertRaises(FixError):
                _validate_https_url(url)


if __name__ == "__main__":
    unittest.main()
