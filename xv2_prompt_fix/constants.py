from __future__ import annotations

from pathlib import Path

APP_NAME = "XV2 Input Prompt Fix"
APP_DATA_DIR_NAME = "XV2PromptFix"
APP_VERSION = "0.4.0"
STATE_SCHEMA_VERSION = 1

STEAM_APP_ID = "454650"
STEAM_DEPOT_ID = "454651"
# Last known public depot manifest before the multilingual input prompt regression.
SOURCE_MANIFEST_ID = "7238901667150908628"
KNOWN_BROKEN_BUILD_IDS = frozenset({"23988437"})

GAME_FOLDER_NAME = "DB Xenoverse 2"
GAME_EXE_REL = Path("bin") / "DBXV2.exe"
GAME_CPK_REL = Path("cpk") / "data1.cpk"
STEAM_MANIFEST_NAME = f"appmanifest_{STEAM_APP_ID}.acf"

DEPOT_DOWNLOADER_VERSION = "3.4.0"
DEPOT_DOWNLOADER_REPO = "https://github.com/SteamRE/DepotDownloader"
CRIPAKTOOLS_COMMIT = "0dbd2229f7c3b519c67d65e89055fd4e610d6dca"
CRIPAKTOOLS_REPO = "https://github.com/esperknight/CriPakTools"
EXTERNAL_TOOLS_MANIFEST = "external_tools.json"

MIN_CPK_BYTES = 512 * 1024 * 1024
HASH_CHUNK_BYTES = 8 * 1024 * 1024
DOWNLOAD_CHUNK_BYTES = 1024 * 1024
DISK_MARGIN_BYTES = 1024 * 1024 * 1024

LOG_MAX_FILES = 20
LOG_MAX_AGE_DAYS = 30

STATE_FILE_NAME = ".xv2promptfix-state.json"
SOURCE_CACHE_DIR_NAME = ".xv2promptfix-source"
WORK_DIR_PREFIX = ".xv2promptfix-work-"
BACKUP_PREFIX = "data1.cpk.xv2promptfix-backup-"
RESTORE_TEMP_PREFIX = "data1.cpk.xv2promptfix-before-restore-"
