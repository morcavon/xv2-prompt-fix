from __future__ import annotations

import os
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path, PurePosixPath

from .cpk_header import inspect_cpk_entry_storage, update_cpk_entry_sizes
from .errors import FixError
from .i18n import tr
from .tools import ProcessController
from .utils import CancelToken, validate_cpk

LogCallback = Callable[[str], None]
FractionCallback = Callable[[float], None]
_COPY_CHUNK_BYTES = 8 * 1024 * 1024


def _normalize_entry(value: str) -> str:
    return value.strip().replace("\\", "/").lstrip("./")


def resolve_target_basenames(
    entries: Iterable[str], target_paths: Sequence[str]
) -> tuple[str, ...]:
    normalized_entries = [_normalize_entry(entry) for entry in entries]
    result: list[str] = []
    for target in target_paths:
        matches = [
            entry
            for entry in normalized_entries
            if entry.casefold() == _normalize_entry(target).casefold()
        ]
        if len(matches) != 1:
            raise FixError(
                tr(
                    "The target path could not be resolved to exactly one entry: {target} (found {count})",
                    target=target,
                    count=len(matches),
                )
            )
        result.append(PurePosixPath(matches[0]).name)
    return tuple(result)


def assert_target_layout_entries(
    entries: Sequence[str], target_paths: Sequence[str], *, label: str
) -> None:
    lower_entries = [entry.casefold() for entry in entries]
    for internal_path in target_paths:
        normalized = _normalize_entry(internal_path)
        lowered = normalized.casefold()
        if lowered not in lower_entries:
            raise FixError(
                tr(
                    "The target file was not found in {label}: {path}",
                    label=label,
                    path=internal_path,
                )
            )
        basename = PurePosixPath(normalized).name.casefold()
        same_name = [
            entry
            for entry in entries
            if PurePosixPath(entry).name.casefold() == basename
        ]
        if len(same_name) != 1:
            joined = "\n".join(f"- {item}" for item in same_name[:20])
            raise FixError(
                tr(
                    "CriPakTools matches replacement targets by filename only, so duplicate filenames cannot be handled safely.\n"
                    "Target: {basename}\nFound: {count}\n{entries}",
                    basename=basename,
                    count=len(same_name),
                    entries=joined,
                )
            )


def assert_raw_replacement_paths_supported(target_paths: Sequence[str]) -> None:
    unsupported = [
        _normalize_entry(path)
        for path in target_paths
        if PurePosixPath(_normalize_entry(path)).suffix.casefold() != ".iggyted"
    ]
    if not unsupported:
        return
    details = "\n".join(f"- {path}" for path in unsupported)
    raise FixError(
        tr(
            "The raw compressed-entry transplant contains unsupported resources. The original CPK was not modified.\n{paths}",
            paths=details,
        )
    )


class CpkTool:
    def __init__(
        self,
        executable: Path,
        *,
        runner: ProcessController,
        cancel: CancelToken,
        log: LogCallback,
    ) -> None:
        self.executable = executable
        self.runner = runner
        self.cancel = cancel
        self.log = log

    def list_entries(self, cpk: Path) -> list[str]:
        self.cancel.check()
        output = self.runner.run_hidden([self.executable, cpk], cwd=cpk.parent)
        entries: list[str] = []
        for raw_line in output.splitlines():
            line = _normalize_entry(raw_line)
            if not line:
                continue
            lowered = line.casefold()
            if lowered.startswith(("cripaktools", "based off")):
                continue
            if "insertion code by" in lowered:
                continue
            entries.append(line)
        return entries

    def assert_target_layout(
        self, cpk: Path, target_paths: Sequence[str], *, label: str
    ) -> list[str]:
        self.log(
            tr(
                "Inspecting the internal file list of {label}",
                label=label,
            )
        )
        entries = self.list_entries(cpk)
        assert_target_layout_entries(entries, target_paths, label=label)
        return entries

    def extract(self, cpk: Path, internal_path: str, destination_root: Path) -> Path:
        self.cancel.check()
        destination_root.mkdir(parents=True, exist_ok=True)
        expected = destination_root.joinpath(*_normalize_entry(internal_path).split("/"))
        expected.unlink(missing_ok=True)
        self.log(tr("Extracting: {path}", path=internal_path))
        output = self.runner.run_hidden(
            [self.executable, cpk, _normalize_entry(internal_path)],
            cwd=destination_root,
        )
        if not expected.is_file():
            basename = PurePosixPath(_normalize_entry(internal_path)).name
            matches = [p for p in destination_root.rglob(basename) if p.is_file()]
            if len(matches) == 1:
                expected = matches[0]
            else:
                tail = "\n".join(output.splitlines()[-20:])
                raise FixError(
                    tr(
                        "The file could not be extracted from the CPK: {path}\n\n{tail}",
                        path=internal_path,
                        tail=tail,
                    )
                )
        if expected.stat().st_size == 0:
            raise FixError(
                tr(
                    "The extracted file is empty: {path}",
                    path=expected,
                )
            )
        return expected

    def replace(
        self,
        input_cpk: Path,
        target_basename: str,
        replacement: Path,
        output_cpk: Path,
        *,
        progress: FractionCallback | None = None,
    ) -> None:
        self.cancel.check()
        if input_cpk.parent.resolve() != output_cpk.parent.resolve():
            raise FixError(
                tr(
                    "CriPakTools output must be created in the same directory as the input CPK.",
                )
            )
        if any(separator in output_cpk.name for separator in ("/", "\\")):
            raise FixError(
                tr(
                    "The CPK output filename cannot contain path separators.",
                )
            )
        output_cpk.unlink(missing_ok=True)
        self.log(
            tr(
                "Replacing CPK entry: {target} → {replacement}",
                target=target_basename,
                replacement=replacement.name,
            )
        )
        self.runner.run_hidden(
            [
                self.executable,
                input_cpk,
                target_basename,
                replacement,
                output_cpk.name,
            ],
            cwd=input_cpk.parent,
            monitor_path=output_cpk,
            expected_bytes=input_cpk.stat().st_size,
            progress=progress,
        )
        validate_cpk(
            output_cpk,
            label=tr(
                "generated {name}", name=output_cpk.name
            ),
        )

    def replace_raw_compressed_entry(
        self,
        input_cpk: Path,
        target_internal_path: str,
        source_cpk: Path,
        source_internal_path: str,
        output_cpk: Path,
        *,
        progress: FractionCallback | None = None,
    ) -> None:
        self.cancel.check()
        if input_cpk.parent.resolve() != output_cpk.parent.resolve():
            raise FixError(
                tr(
                    "The raw CPK replacement must be created beside the input CPK.",
                )
            )
        resolved_input = input_cpk.resolve()
        resolved_source = source_cpk.resolve()
        resolved_output = output_cpk.resolve()
        if resolved_output in {resolved_input, resolved_source}:
            raise FixError(
                tr(
                    "The raw CPK replacement output path matches an input or reference CPK.",
                )
            )

        target = inspect_cpk_entry_storage(input_cpk, target_internal_path)
        source = inspect_cpk_entry_storage(source_cpk, source_internal_path)
        if not target.compressed or not source.compressed:
            raise FixError(
                tr(
                    "The target .iggyted entry is not CRILAYLA-compressed in both CPK files. The original was not modified.",
                )
            )
        if source.file_size > target.file_size:
            raise FixError(
                tr(
                    "The reference raw compressed entry is larger than the current storage capacity: source={source}, capacity={capacity}",
                    source=source.file_size,
                    capacity=target.file_size,
                )
            )

        output_cpk.unlink(missing_ok=True)
        total = input_cpk.stat().st_size
        copied = 0
        try:
            with input_cpk.open("rb") as input_stream, output_cpk.open(
                "xb"
            ) as output_stream:
                while True:
                    self.cancel.check()
                    chunk = input_stream.read(_COPY_CHUNK_BYTES)
                    if not chunk:
                        break
                    output_stream.write(chunk)
                    copied += len(chunk)
                    if progress and total:
                        progress(min(copied / total, 1.0) * 0.95)
                output_stream.flush()
                os.fsync(output_stream.fileno())

            self.cancel.check()
            with source_cpk.open("rb") as source_stream, output_cpk.open(
                "r+b"
            ) as output_stream:
                source_stream.seek(source.file_offset)
                output_stream.seek(target.file_offset)
                remaining = source.file_size
                while remaining:
                    self.cancel.check()
                    chunk = source_stream.read(min(_COPY_CHUNK_BYTES, remaining))
                    if not chunk:
                        raise FixError(
                            tr(
                                "The raw compressed entry in the reference CPK is truncated.",
                            )
                        )
                    output_stream.write(chunk)
                    remaining -= len(chunk)
                padding = target.file_size - source.file_size
                zeroes = b"\0" * min(_COPY_CHUNK_BYTES, max(padding, 1))
                while padding:
                    count = min(len(zeroes), padding)
                    output_stream.write(zeroes[:count])
                    padding -= count
                output_stream.flush()
                os.fsync(output_stream.fileno())

            before, after = update_cpk_entry_sizes(
                output_cpk,
                target_internal_path,
                file_size=source.file_size,
                extract_size=source.extract_size,
            )
            if (
                before.file_offset != target.file_offset
                or after.file_offset != target.file_offset
                or output_cpk.stat().st_size != total
            ):
                raise FixError(
                    tr(
                        "The CPK storage geometry changed after the raw compressed-entry transplant.",
                    )
                )
            if progress:
                progress(1.0)
            validate_cpk(
                output_cpk,
                label=tr(
                    "generated {name}", name=output_cpk.name
                ),
            )
        except Exception:
            output_cpk.unlink(missing_ok=True)
            raise
