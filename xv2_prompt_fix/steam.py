from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

from .constants import (
    GAME_CPK_REL,
    GAME_EXE_REL,
    GAME_FOLDER_NAME,
    STEAM_MANIFEST_NAME,
)
from .errors import FixError
from .i18n import tr
from .utils import normalized_path, validate_cpk, windows_system_executable

_BUILD_ID_RE = re.compile(r'"buildid"\s+"(?P<id>\d+)"', re.IGNORECASE)
_LANGUAGE_RE = re.compile(r'"language"\s+"(?P<language>[^"]+)"', re.IGNORECASE)
_VDF_PATH_RE = re.compile(r'"path"\s+"(?P<path>(?:\\.|[^"])*)"', re.IGNORECASE)


def _unescape_vdf(value: str) -> str:
    return value.replace(r"\\", "\\").replace(r'\"', '"')


def parse_library_paths(vdf_text: str) -> list[Path]:
    paths: list[Path] = []
    for match in _VDF_PATH_RE.finditer(vdf_text):
        value = _unescape_vdf(match.group("path"))
        if value:
            paths.append(Path(value))
    return paths


def parse_build_id(manifest_text: str) -> str | None:
    match = _BUILD_ID_RE.search(manifest_text)
    return match.group("id") if match else None


def parse_installed_language(manifest_text: str) -> str | None:
    matches = [
        match.group("language").strip().casefold()
        for match in _LANGUAGE_RE.finditer(manifest_text)
        if match.group("language").strip()
    ]
    return matches[-1] if matches else None


def _registry_steam_roots() -> list[Path]:
    if sys.platform != "win32":
        return []
    try:
        import winreg
    except ImportError:
        return []

    roots: list[Path] = []
    keys = (
        (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam"),
    )
    for hive, key_name in keys:
        try:
            with winreg.OpenKey(hive, key_name) as key:
                for value_name in ("SteamPath", "InstallPath", "SteamExe"):
                    try:
                        raw, _ = winreg.QueryValueEx(key, value_name)
                    except OSError:
                        continue
                    path = Path(str(raw))
                    if value_name == "SteamExe":
                        path = path.parent
                    roots.append(path)
        except OSError:
            continue
    return roots


def candidate_steam_roots() -> list[Path]:
    candidates = _registry_steam_roots()
    env_candidates = (
        os.environ.get("PROGRAMFILES(X86)"),
        os.environ.get("PROGRAMFILES"),
    )
    for base in env_candidates:
        if base:
            candidates.append(Path(base) / "Steam")

    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = normalized_path(candidate)
        if key not in seen:
            seen.add(key)
            unique.append(candidate)
    return unique


def discover_steam_libraries() -> list[Path]:
    libraries: list[Path] = []
    for root in candidate_steam_roots():
        if root.exists():
            libraries.append(root)
        vdf = root / "steamapps" / "libraryfolders.vdf"
        try:
            text = vdf.read_text(encoding="utf-8-sig", errors="replace")
        except OSError:
            continue
        libraries.extend(parse_library_paths(text))

    unique: list[Path] = []
    seen: set[str] = set()
    for library in libraries:
        key = normalized_path(library)
        if key not in seen:
            seen.add(key)
            unique.append(library)
    return unique


def find_game_roots() -> list[Path]:
    roots: list[Path] = []
    for library in discover_steam_libraries():
        root = library / "steamapps" / "common" / GAME_FOLDER_NAME
        if (root / GAME_EXE_REL).is_file() and (root / GAME_CPK_REL).is_file():
            roots.append(root)
    return roots


def normalize_selected_root(path: Path) -> Path:
    path = path.expanduser()
    # Accept the game root, bin/cpk directory, executable, or data1.cpk itself.
    if path.is_file():
        if path.name.casefold() in {"dbxv2.exe", "data1.cpk"}:
            path = path.parent.parent
    elif path.name.casefold() in {"bin", "cpk"}:
        path = path.parent
    return path.resolve()


def validate_game_root(path: Path) -> tuple[Path, Path]:
    root = normalize_selected_root(path)
    exe = root / GAME_EXE_REL
    cpk = root / GAME_CPK_REL
    if not exe.is_file() or not cpk.is_file():
        raise FixError(
            tr(
                "This is not a Dragon Ball Xenoverse 2 installation folder. Both files must exist:\n- {exe}\n- {cpk}\n\nSelected path: {root}",
                exe=GAME_EXE_REL,
                cpk=GAME_CPK_REL,
                root=root,
            )
        )
    validate_cpk(cpk, label=tr("current data1.cpk"))
    return root, cpk


def find_appmanifest(game_root: Path) -> Path | None:
    # Resolve steamapps/appmanifest_454650.acf from a standard game directory.
    if game_root.parent.name.casefold() == "common":
        candidate = game_root.parent.parent / STEAM_MANIFEST_NAME
        if candidate.is_file():
            return candidate
    # Search a few parent levels to support nonstandard junction layouts.
    for parent in list(game_root.parents)[:4]:
        candidate = parent / STEAM_MANIFEST_NAME
        if candidate.is_file():
            return candidate
        candidate = parent / "steamapps" / STEAM_MANIFEST_NAME
        if candidate.is_file():
            return candidate
    return None


def read_installed_build_id(game_root: Path) -> str | None:
    manifest = find_appmanifest(game_root)
    if not manifest:
        return None
    try:
        text = manifest.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return None
    return parse_build_id(text)


def read_installed_language(game_root: Path) -> str | None:
    manifest = find_appmanifest(game_root)
    if not manifest:
        return None
    try:
        text = manifest.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return None
    return parse_installed_language(text)


def running_game_processes() -> list[str]:
    if sys.platform != "win32":
        return []
    process_names = ("DBXV2.exe",)
    found: list[str] = []
    for process_name in process_names:
        try:
            result = subprocess.run(
                [
                    str(windows_system_executable("tasklist.exe")),
                    "/FI",
                    f"IMAGENAME eq {process_name}",
                    "/FO",
                    "CSV",
                    "/NH",
                ],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, FixError):
            continue
        if process_name.casefold() in result.stdout.casefold():
            found.append(process_name)
    return found


def assert_game_not_running() -> None:
    processes = running_game_processes()
    if processes:
        raise FixError(
            tr(
                "The game is running. Close these processes and try again: {processes}",
                processes=", ".join(processes),
            )
        )
