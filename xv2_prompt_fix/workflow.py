from __future__ import annotations

import os
import shutil
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal

from .constants import (
    APP_VERSION,
    BACKUP_PREFIX,
    DEPOT_DOWNLOADER_VERSION,
    DISK_MARGIN_BYTES,
    KNOWN_BROKEN_BUILD_IDS,
    RESTORE_TEMP_PREFIX,
    SOURCE_CACHE_DIR_NAME,
    SOURCE_MANIFEST_ID,
    STEAM_APP_ID,
    STEAM_DEPOT_ID,
    WORK_DIR_PREFIX,
)
from .cpk import (
    CpkTool,
    assert_raw_replacement_paths_supported,
    assert_target_layout_entries,
)
from .cpk_header import (
    assert_cpk_header_geometry,
    repair_cpk_header_geometry,
)
from .errors import FixError
from .i18n import tr
from .languages import (
    discover_language_resource_sets,
    language_codes,
    resolve_patch_targets,
    resource_code_for_steam_language,
)
from .state import FixState, load_state, resolve_backup_path, save_state
from .steam import (
    assert_game_not_running,
    read_installed_build_id,
    read_installed_language,
    validate_game_root,
)
from .tools import ProcessController, ToolManager
from .utils import (
    CancelToken,
    ensure_writable_directory,
    format_bytes,
    iso_now,
    safe_rmtree,
    sha256_file,
    timestamp,
    validate_cpk,
)

LogCallback = Callable[[str], None]
StatusCallback = Callable[[str], None]
ProgressCallback = Callable[[float | None, str], None]


@dataclass(slots=True)
class WorkflowOptions:
    game_root: Path
    local_source_cpk: Path | None = None
    allow_third_party_steam_auth: bool = False
    allow_unknown_build: bool = False
    keep_downloaded_source: bool = False
    force_restore: bool = False


@dataclass(slots=True)
class WorkflowResult:
    kind: Literal["applied", "already_applied", "already_fixed", "restored"]
    message: str
    backup_path: Path | None = None


def _select_resource_patch_paths(
    target_paths: Sequence[str],
    source_hashes: Mapping[str, str],
    current_hashes: Mapping[str, str],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    by_suffix: dict[str, list[str]] = {}
    for path in target_paths:
        by_suffix.setdefault(PurePosixPath(path).suffix.casefold(), []).append(path)

    expected_suffixes = {".iggy", ".iggytex", ".iggyted"}
    if set(by_suffix) != expected_suffixes or any(
        len(by_suffix[suffix]) != 1 for suffix in expected_suffixes
    ):
        raise FixError(
            tr(
                "The input-prompt resources do not match the validated three-file layout. The original was not modified.",
            )
        )

    changed_paths = tuple(
        path for path in target_paths if source_hashes[path] != current_hashes[path]
    )
    if not changed_paths:
        return (), ()
    changed_suffixes = {
        PurePosixPath(path).suffix.casefold() for path in changed_paths
    }
    if changed_suffixes != {".iggy", ".iggyted"} or len(changed_paths) != 2:
        statuses = "\n".join(
            tr(
                "- {suffix}: {status}",
                suffix=suffix,
                status=(
                    tr("different")
                    if any(
                        source_hashes[path] != current_hashes[path]
                        for path in by_suffix[suffix]
                    )
                    else tr("identical")
                ),
            )
            for suffix in sorted(expected_suffixes)
        )
        raise FixError(
            tr(
                "The current and reference resources do not match the validated replacement conditions. The `.iggy` and its matching `.iggyted` must both differ, while `.iggytex` must be identical. The original was not modified.\n{statuses}",
                statuses=statuses,
            )
        )

    raw_paths = tuple(
        path
        for path in changed_paths
        if PurePosixPath(path).suffix.casefold() == ".iggyted"
    )
    return changed_paths, raw_paths


class Workflow:
    def __init__(
        self,
        *,
        options: WorkflowOptions,
        cancel: CancelToken,
        log: LogCallback,
        status: StatusCallback,
        progress: ProgressCallback,
    ) -> None:
        self.options = options
        self.cancel = cancel
        self.log = log
        self.status = status
        self.progress = progress
        self.runner = ProcessController(cancel)

    def cancel_active(self) -> None:
        self.runner.terminate_active()

    def _phase(self, value: float | None, text: str) -> None:
        self.cancel.check()
        self.status(text)
        self.progress(value, text)
        self.log(text)

    def _hash(
        self,
        path: Path,
        *,
        label: str,
        start: float,
        end: float,
    ) -> str:
        hash_text = tr("Calculating SHA-256: {label}", label=label)
        self._phase(start, hash_text)
        return sha256_file(
            path,
            cancel=self.cancel,
            progress=lambda fraction: self.progress(
                start + (end - start) * fraction,
                hash_text,
            ),
        )

    def _disk_preflight(self, cpk: Path) -> None:
        usage = shutil.disk_usage(cpk.parent)
        multiplier = 3 if self.options.keep_downloaded_source else 2
        required = cpk.stat().st_size * multiplier + DISK_MARGIN_BYTES
        if usage.free < required:
            raise FixError(
                tr(
                    "There is not enough working space.\nRequired free space: about {required}\nCurrent free space: {free}\nTarget drive: {drive}",
                    required=format_bytes(required),
                    free=format_bytes(usage.free),
                    drive=cpk.parent.anchor,
                )
            )
        self.log(
            tr(
                "Disk space verified: {free} free (about {required} required)",
                free=format_bytes(usage.free),
                required=format_bytes(required),
            )
        )

    def _download_source(
        self,
        *,
        depot_exe: Path | None,
        work: Path,
        current_cpk_size: int,
    ) -> Path:
        download_dir = work / "source-download"
        download_dir.mkdir(parents=True, exist_ok=True)
        filelist = work / "depot-filelist.txt"
        filelist.write_text("cpk/data1.cpk\n", encoding="ascii")
        expected = download_dir / "cpk" / "data1.cpk"
        self._phase(
            None,
            tr(
                "Scan the QR code in the Steam authentication window and approve the login.",
            ),
        )
        if depot_exe is None:
            raise FixError(
                tr(
                    "The DepotDownloader executable path is missing.",
                )
            )
        args: list[str] = [
            str(depot_exe),
            "-app",
            STEAM_APP_ID,
            "-depot",
            STEAM_DEPOT_ID,
            "-manifest",
            SOURCE_MANIFEST_ID,
            "-qr",
            "-os",
            "windows",
            "-osarch",
            "64",
            "-filelist",
            str(filelist),
            "-dir",
            str(download_dir),
            "-max-downloads",
            "8",
        ]
        self.runner.run_new_console(
            args,
            cwd=depot_exe.parent,
            monitor_path=expected,
            expected_bytes=current_cpk_size,
            progress=lambda fraction: self.progress(
                12.0 + 30.0 * fraction,
                tr(
                    "Downloading the reference data1.cpk",
                ),
            ),
        )
        candidates = [p for p in download_dir.rglob("data1.cpk") if p.is_file()]
        if len(candidates) != 1:
            raise FixError(
                tr(
                    "Exactly one data1.cpk was not found after DepotDownloader completed.\nSearch location: {path}\nFound: {count}",
                    path=download_dir,
                    count=len(candidates),
                )
            )
        validate_cpk(
            candidates[0],
            label=tr("downloaded reference data1.cpk"),
        )
        return candidates[0]

    def _choose_source(
        self,
        *,
        game_root: Path,
        depot_exe: Path | None,
        work: Path,
        current_cpk_size: int,
    ) -> tuple[Path, bool]:
        if self.options.local_source_cpk:
            source = self.options.local_source_cpk.expanduser().resolve()
            validate_cpk(
                source,
                label=tr("selected reference data1.cpk"),
            )
            self.log(
                tr(
                    "Using local reference CPK: {name} ({size})",
                    name=source.name,
                    size=format_bytes(source.stat().st_size),
                )
            )
            return source, False

        persistent = (
            game_root
            / "cpk"
            / SOURCE_CACHE_DIR_NAME
            / SOURCE_MANIFEST_ID
            / "data1.cpk"
        )
        if persistent.is_file():
            try:
                validate_cpk(
                    persistent,
                    label=tr("cached reference data1.cpk"),
                )
                self.log(tr("Reusing cached reference CPK"))
                return persistent, False
            except FixError as exc:
                self.log(
                    tr(
                        "The cached reference is invalid and will be downloaded again: {error}",
                        error=exc,
                    )
                )
                persistent.unlink(missing_ok=True)

        if depot_exe is None:
            raise FixError(
                tr(
                    "DepotDownloader is required but was not prepared.",
                )
            )
        source = self._download_source(
            depot_exe=depot_exe,
            work=work,
            current_cpk_size=current_cpk_size,
        )
        return source, True

    def apply(self) -> WorkflowResult:
        if os.name != "nt":
            raise FixError(
                tr("This application is for Windows only.")
            )
        game_root, current_cpk = validate_game_root(self.options.game_root)
        assert_game_not_running()
        ensure_writable_directory(current_cpk.parent)
        self._phase(
            1.0,
            tr("Game installation structure verified"),
        )
        build_id = read_installed_build_id(game_root)
        self.log(
            tr(
                "Installed Steam build ID: {build}",
                build=build_id or tr("[unknown]"),
            )
        )

        prior_state = load_state(game_root)
        if prior_state and prior_state.active and prior_state.patched_sha256:
            if current_cpk.stat().st_size == prior_state.patched_size:
                current_hash = self._hash(
                    current_cpk,
                    label=tr("verifying the existing applied state"),
                    start=1.0,
                    end=2.0,
                )
                if current_hash == prior_state.patched_sha256:
                    assert_cpk_header_geometry(
                        current_cpk,
                        label=tr("existing patched CPK"),
                    )
                    return WorkflowResult(
                        "already_applied",
                        tr(
                            "A data1.cpk already patched by this application is currently applied.",
                        ),
                        resolve_backup_path(game_root, prior_state),
                    )
            raise FixError(
                tr(
                    "The patch state is active, but the current data1.cpk differs from the recorded patched file.\nReapplying after a Steam update or another mod changed the file could lose backup tracking, so the operation was stopped.\nUse 'Restore original' first, or verify the game files in Steam and then clean up the state file and backup manually.",
                )
            )

        if build_id not in KNOWN_BROKEN_BUILD_IDS and not self.options.allow_unknown_build:
            known = ", ".join(sorted(KNOWN_BROKEN_BUILD_IDS))
            raise FixError(
                tr(
                    "This Steam build has not been verified for automatic patching.\nCurrent build ID: {current}\nVerified build ID: {known}\n\nAn official update may already have fixed the issue, or the file structure may have changed. Enable 'Allow unknown build' in advanced settings only if you intend to continue.",
                    current=build_id or tr("[unknown]"),
                    known=known,
                )
            )

        steam_language = read_installed_language(game_root)
        self.log(
            tr(
                "Installed Steam language: {language}",
                language=steam_language or tr("[unknown]"),
            )
        )

        self._disk_preflight(current_cpk)
        original_stat = current_cpk.stat()
        work = current_cpk.parent / f"{WORK_DIR_PREFIX}{timestamp()}"
        work.mkdir(parents=True, exist_ok=False)
        self.log(
            tr(
                "Created an isolated temporary work directory in the game CPK folder",
            )
        )

        downloaded_source = False
        source_cpk: Path | None = None
        try:
            self._phase(
                3.0,
                tr("Checking required external tools"),
            )
            tool_manager = ToolManager(
                cancel=self.cancel,
                log=self.log,
                progress=lambda fraction: self.progress(
                    3.0 + 6.0 * fraction,
                    tr("Preparing external tools"),
                ),
            )
            cripa_exe = tool_manager.ensure_cripaktools()
            self.log(
                tr(
                    "Pinned CriPakTools integrity verified",
                )
            )

            persistent_source = (
                game_root
                / "cpk"
                / SOURCE_CACHE_DIR_NAME
                / SOURCE_MANIFEST_ID
                / "data1.cpk"
            )
            needs_depot = self.options.local_source_cpk is None
            if needs_depot and persistent_source.is_file():
                try:
                    validate_cpk(
                        persistent_source,
                        label=tr("cached reference data1.cpk"),
                    )
                    needs_depot = False
                except FixError:
                    persistent_source.unlink(missing_ok=True)
                    needs_depot = True
            if needs_depot and not self.options.allow_third_party_steam_auth:
                raise FixError(
                    tr(
                        "Steam automatic download requires explicit consent for DepotDownloader QR authentication. Review the notice in the GUI or select a local reference data1.cpk.",
                    )
                )
            depot_exe = tool_manager.ensure_depot_downloader() if needs_depot else None
            if depot_exe:
                self.log(
                    tr(
                        "Pinned DepotDownloader {version} integrity verified",
                        version=DEPOT_DOWNLOADER_VERSION,
                    )
                )

            source_cpk, downloaded_source = self._choose_source(
                game_root=game_root,
                depot_exe=depot_exe,
                work=work,
                current_cpk_size=current_cpk.stat().st_size,
            )
            self._phase(
                43.0,
                tr(
                    "Inspecting the CPK structure and installed Steam language resources",
                ),
            )
            cpk_tool = CpkTool(
                cripa_exe,
                runner=self.runner,
                cancel=self.cancel,
                log=self.log,
            )
            source_entries = cpk_tool.list_entries(source_cpk)
            current_entries = cpk_tool.list_entries(current_cpk)
            source_codes = discover_language_resource_sets(source_entries)
            current_codes = discover_language_resource_sets(current_entries)
            available_codes = tuple(sorted(set(source_codes) & set(current_codes)))
            resource_code = resource_code_for_steam_language(
                steam_language,
                available_codes=available_codes,
            )
            targets = resolve_patch_targets(
                source_entries,
                current_entries,
                language_code=resource_code,
            )
            detected_codes = language_codes(targets)
            source_target_paths = tuple(target.source_path for target in targets)
            current_target_paths = tuple(target.current_path for target in targets)
            assert_target_layout_entries(
                source_entries,
                source_target_paths,
                label=tr("reference CPK"),
            )
            assert_target_layout_entries(
                current_entries,
                current_target_paths,
                label=tr("current CPK"),
            )
            self.log(
                tr(
                    "Installed Steam language and patch target: {language} → {codes}",
                    language=steam_language or tr("[unknown]"),
                    codes=", ".join(detected_codes),
                )
            )
            current_geometry = assert_cpk_header_geometry(
                current_cpk,
                label=tr("current CPK"),
            )
            self.log(
                tr(
                    "Current CPK header geometry verified: ContentOffset={offset}, ContentSize={size}, Align={align}",
                    offset=current_geometry.content_offset,
                    size=current_geometry.content_size,
                    align=current_geometry.align,
                )
            )
            old_extract = work / "old-targets"
            current_extract = work / "current-targets"
            self._phase(
                47.0,
                tr(
                    "Extracting language resources from the reference and current CPK files",
                ),
            )
            old_files: dict[str, Path] = {}
            current_files: dict[str, Path] = {}
            for target in targets:
                old_files[target.current_path] = cpk_tool.extract(
                    source_cpk, target.source_path, old_extract
                )
                current_files[target.current_path] = cpk_tool.extract(
                    current_cpk, target.current_path, current_extract
                )

            self._phase(
                51.0,
                tr("Comparing target resource hashes"),
            )
            source_target_hashes = {
                path: sha256_file(file, cancel=self.cancel)
                for path, file in old_files.items()
            }
            original_target_hashes = {
                path: sha256_file(file, cancel=self.cancel)
                for path, file in current_files.items()
            }
            for path in current_target_paths:
                self.log(
                    tr(
                        "{path}\n  reference: {source}\n  current  : {current}",
                        path=path,
                        source=source_target_hashes[path],
                        current=original_target_hashes[path],
                    )
                )
            changed_paths, raw_replacement_paths = _select_resource_patch_paths(
                current_target_paths,
                source_target_hashes,
                original_target_hashes,
            )
            assert_raw_replacement_paths_supported(raw_replacement_paths)
            if downloaded_source:
                if self.options.keep_downloaded_source:
                    persistent = (
                        game_root
                        / "cpk"
                        / SOURCE_CACHE_DIR_NAME
                        / SOURCE_MANIFEST_ID
                        / "data1.cpk"
                    )
                    persistent.parent.mkdir(parents=True, exist_ok=True)
                    persistent.unlink(missing_ok=True)
                    os.replace(source_cpk, persistent)
                    source_cpk = persistent
                    self.log(
                        tr("Reference CPK cached successfully")
                    )

            if not changed_paths:
                if downloaded_source and not self.options.keep_downloaded_source:
                    source_cpk.unlink(missing_ok=True)
                    self.log(
                        tr(
                            "Deleted the downloaded reference CPK after verification",
                        )
                    )
                return WorkflowResult(
                    "already_fixed",
                    tr(
                        "The input-prompt resources for the installed Steam language already match the reference version. No changes were made.",
                    ),
                )

            original_hash = self._hash(
                current_cpk,
                label=tr("current original data1.cpk"),
                start=54.0,
                end=60.0,
            )

            source_path_by_current = {
                target.current_path: target.source_path for target in targets
            }
            for path in current_target_paths:
                if path in changed_paths:
                    continue
                self.log(
                    tr(
                        "Keeping the current file because both versions match: {path}",
                        path=path,
                    )
                )

            stage_input = current_cpk
            stage2: Path | None = None
            phase_width = 26.0 / len(changed_paths)
            for index, internal_path in enumerate(changed_paths, start=1):
                phase_start = 61.0 + phase_width * (index - 1)
                phase_end = 61.0 + phase_width * index
                stage_output = current_cpk.parent / f"{work.name}-stage{index}.cpk"
                label = tr(
                    "Creating patched CPK {index}/{total}: {name}",
                    index=index,
                    total=len(changed_paths),
                    name=PurePosixPath(internal_path).name,
                )
                self._phase(phase_start, label)

                def stage_progress(
                    fraction: float,
                    *,
                    start: float = phase_start,
                    end: float = phase_end,
                    text: str = label,
                ) -> None:
                    self.progress(start + (end - start) * fraction, text)

                suffix = PurePosixPath(internal_path).suffix.casefold()
                if suffix == ".iggy":
                    cpk_tool.replace(
                        stage_input,
                        PurePosixPath(internal_path).name,
                        old_files[internal_path],
                        stage_output,
                        progress=stage_progress,
                    )
                elif suffix == ".iggyted":
                    cpk_tool.replace_raw_compressed_entry(
                        stage_input,
                        internal_path,
                        source_cpk,
                        source_path_by_current[internal_path],
                        stage_output,
                        progress=stage_progress,
                    )
                else:
                    raise FixError(
                        tr(
                            "Unsupported replacement target: {path}",
                            path=internal_path,
                        )
                    )
                if stage_input != current_cpk:
                    stage_input.unlink(missing_ok=True)
                stage_input = stage_output
                stage2 = stage_output
            if downloaded_source and not self.options.keep_downloaded_source:
                source_cpk.unlink(missing_ok=True)
                self.log(
                    tr(
                        "Deleted the downloaded reference CPK after replacing the input-prompt resource set",
                    )
                )
            if stage2 is None:
                raise FixError(
                    tr(
                        "No target resources requiring replacement could be determined.",
                    )
                )

            self._phase(
                87.0,
                tr(
                    "Verifying the CPK ContentSize header",
                ),
            )
            before_geometry, after_geometry = repair_cpk_header_geometry(stage2)
            self.log(
                tr(
                    "CPK ContentSize header verified: {before} → {after}",
                    before=before_geometry.content_size,
                    after=after_geometry.content_size,
                )
            )

            self._phase(
                87.5,
                tr("Verifying the patched CPK by re-extraction"),
            )
            verify_root = work / "verify-targets"
            verified_hashes: dict[str, str] = {}
            expected_target_hashes = dict(original_target_hashes)
            for internal_path in changed_paths:
                expected_target_hashes[internal_path] = source_target_hashes[
                    internal_path
                ]
            stage_entries = cpk_tool.assert_target_layout(
                stage2,
                current_target_paths,
                label=tr("generated patched CPK"),
            )
            current_layout = Counter(entry.casefold() for entry in current_entries)
            stage_layout = Counter(entry.casefold() for entry in stage_entries)
            if current_layout != stage_layout:
                missing = list((current_layout - stage_layout).elements())[:20]
                added = list((stage_layout - current_layout).elements())[:20]
                raise FixError(
                    tr(
                        "The patched CPK file list differs from the original. The original was not changed.\nMissing examples: {missing}\nAdded examples: {added}",
                        missing=missing,
                        added=added,
                    )
                )
            self.log(
                tr(
                    "CPK entry set verified: {count} entries",
                    count=len(stage_entries),
                )
            )
            for internal_path in current_target_paths:
                extracted = cpk_tool.extract(stage2, internal_path, verify_root)
                verified_hashes[internal_path] = sha256_file(
                    extracted, cancel=self.cancel
                )
            if verified_hashes != expected_target_hashes:
                details = "\n".join(
                    f"{path}: expected={expected_target_hashes[path]}, actual={verified_hashes.get(path)}"
                    for path in current_target_paths
                )
                raise FixError(
                    tr(
                        "Re-extraction verification of the patched CPK failed. The original was not changed.\n{details}",
                        details=details,
                    )
                )

            patched_hash = self._hash(
                stage2,
                label=tr("verified patched data1.cpk"),
                start=91.0,
                end=97.0,
            )
            current_stat_now = current_cpk.stat()
            if (
                current_stat_now.st_size != original_stat.st_size
                or current_stat_now.st_mtime_ns != original_stat.st_mtime_ns
            ):
                raise FixError(
                    tr(
                        "The current data1.cpk was changed by another program during processing. The patch was not applied. Check for a Steam update or file verification operation.",
                    )
                )

            backup = current_cpk.parent / f"{BACKUP_PREFIX}{timestamp()}"
            while backup.exists():
                backup = backup.with_name(backup.name + "-1")
            state = FixState(
                app_version=APP_VERSION,
                game_build_id=build_id,
                source_manifest_id=SOURCE_MANIFEST_ID,
                applied_at=iso_now(),
                active=False,
                backup_name=backup.name,
                original_sha256=original_hash,
                original_size=current_cpk.stat().st_size,
                patched_sha256=patched_hash,
                patched_size=stage2.stat().st_size,
                source_target_sha256=source_target_hashes,
                original_target_sha256=original_target_hashes,
                tool_sha256={
                    "CriPakTools.exe": sha256_file(cripa_exe, cancel=self.cancel),
                    **(
                        {"DepotDownloader.exe": sha256_file(depot_exe, cancel=self.cancel)}
                        if depot_exe is not None
                        else {}
                    ),
                },
            )
            save_state(game_root, state)

            self.cancel.check()
            self._phase(
                98.0,
                tr("Applying the verified patched CPK"),
            )
            os.replace(current_cpk, backup)
            try:
                os.replace(stage2, current_cpk)
            except Exception:
                os.replace(backup, current_cpk)
                raise
            try:
                state.active = True
                save_state(game_root, state)
            except Exception:
                failed_copy = current_cpk.parent / f"{stage2.name}.state-failed"
                try:
                    os.replace(current_cpk, failed_copy)
                    os.replace(backup, current_cpk)
                    failed_copy.unlink(missing_ok=True)
                finally:
                    pass
                raise

            self._phase(100.0, tr("Patch completed"))
            return WorkflowResult(
                "applied",
                tr(
                    "The input-prompt resources for the installed Steam language were replaced successfully. Processed language code: {codes}",
                    codes=", ".join(detected_codes),
                ),
                backup,
            )
        finally:
            # CriPakTools requires stage files to be created beside the input CPK.
            for candidate in current_cpk.parent.glob(f"{work.name}-stage*.cpk"):
                try:
                    candidate.unlink()
                except OSError:
                    pass
            safe_rmtree(work)

    def restore(self) -> WorkflowResult:
        if os.name != "nt":
            raise FixError(
                tr("This application is for Windows only.")
            )
        game_root, current_cpk = validate_game_root(self.options.game_root)
        assert_game_not_running()
        ensure_writable_directory(current_cpk.parent)
        state = load_state(game_root)
        if not state or not state.active:
            raise FixError(
                tr(
                    "No active backup state created by this application was found.",
                )
            )
        backup = resolve_backup_path(game_root, state)
        if backup is None:
            raise FixError(
                tr(
                    "The original backup information created by this application was not found.",
                )
            )
        backup_label = tr("original backup CPK")
        validate_cpk(backup, label=backup_label)
        assert_cpk_header_geometry(backup, label=backup_label)

        current_hash = self._hash(
            current_cpk,
            label=tr("verifying the current patched CPK"),
            start=5.0,
            end=40.0,
        )
        if current_hash != state.patched_sha256 and not self.options.force_restore:
            raise FixError(
                tr(
                    "The current data1.cpk differs from the patched file applied by this application.\nA Steam update or another mod may have changed it, so automatic restoration was stopped.\nYou may use force restore in advanced settings, but this can replace a newer official file with an older backup.",
                )
            )

        backup_hash = self._hash(
            backup,
            label=tr("verifying original backup integrity"),
            start=40.0,
            end=75.0,
        )
        if backup_hash != state.original_sha256:
            raise FixError(
                tr(
                    "The original backup SHA-256 differs from the value recorded when the patch was applied. Restoration was not performed because the backup may be damaged.",
                )
            )

        self.cancel.check()
        temp = current_cpk.parent / f"{RESTORE_TEMP_PREFIX}{timestamp()}"
        self._phase(80.0, tr("Restoring the original backup"))
        os.replace(current_cpk, temp)
        try:
            os.replace(backup, current_cpk)
        except Exception:
            os.replace(temp, current_cpk)
            raise
        try:
            restored_hash = self._hash(
                current_cpk,
                label=tr("verifying the restored CPK"),
                start=82.0,
                end=98.0,
            )
            if restored_hash != state.original_sha256:
                raise FixError(
                    tr(
                        "SHA-256 verification failed after restoration.",
                    )
                )
            assert_cpk_header_geometry(
                current_cpk,
                label=tr("restored original CPK"),
            )
            state.active = False
            state.restored_at = iso_now()
            state.backup_name = None
            save_state(game_root, state)
        except Exception:
            # Return both CPK files to their exact pre-restore locations.
            # The patched CPK returns to the active path and the original returns to the backup path.
            try:
                os.replace(current_cpk, backup)
                os.replace(temp, current_cpk)
            finally:
                pass
            raise
        temp.unlink(missing_ok=True)
        self._phase(100.0, tr("Original restoration completed"))
        return WorkflowResult(
            "restored",
            tr(
                "The original data1.cpk from before the patch was restored.",
            ),
        )
