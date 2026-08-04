from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .constants import BACKUP_PREFIX, STATE_FILE_NAME, STATE_SCHEMA_VERSION
from .errors import FixError
from .i18n import tr
from .utils import atomic_write_json, read_json


@dataclass(slots=True)
class FixState:
    schema_version: int = STATE_SCHEMA_VERSION
    app_version: str = ""
    game_build_id: str | None = None
    source_manifest_id: str = ""
    applied_at: str | None = None
    restored_at: str | None = None
    active: bool = False
    backup_name: str | None = None
    original_sha256: str = ""
    original_size: int = 0
    patched_sha256: str = ""
    patched_size: int = 0
    source_target_sha256: dict[str, str] = field(default_factory=dict)
    original_target_sha256: dict[str, str] = field(default_factory=dict)
    tool_sha256: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FixState:
        schema = data.get("schema_version")
        if schema != STATE_SCHEMA_VERSION:
            raise FixError(
                tr(
                    "Unsupported state file version: {schema} (supported: {current})",
                    schema=schema,
                    current=STATE_SCHEMA_VERSION,
                )
            )

        allowed = {
            item.name
            for item in cls.__dataclass_fields__.values()  # type: ignore[attr-defined]
        }
        filtered = {key: value for key, value in data.items() if key in allowed}
        filtered["backup_name"] = _validate_backup_name(data.get("backup_name"))
        return cls(**filtered)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["schema_version"] = STATE_SCHEMA_VERSION
        return data


def _validate_backup_name(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise FixError(
            tr(
                "The backup filename in the state file is invalid.",
            )
        )
    path = Path(value)
    if path.name != value or any(char in value for char in ("/", "\\", ":")):
        raise FixError(
            tr(
                "The backup path in the state file is unsafe.",
            )
        )
    if not value.startswith(BACKUP_PREFIX):
        raise FixError(
            tr(
                "The backup filename format in the state file is invalid.",
            )
        )
    return value


def state_path(game_root: Path) -> Path:
    return game_root / "cpk" / STATE_FILE_NAME


def resolve_backup_path(game_root: Path, state: FixState) -> Path | None:
    name = _validate_backup_name(state.backup_name)
    if name is None:
        return None
    cpk_dir = (game_root / "cpk").resolve(strict=False)
    candidate = (cpk_dir / name).resolve(strict=False)
    if candidate.parent != cpk_dir:
        raise FixError(
            tr(
                "The backup path in the state file escapes the CPK folder.",
            )
        )
    return candidate


def load_state(game_root: Path) -> FixState | None:
    path = state_path(game_root)
    if not path.is_file():
        return None
    return FixState.from_dict(read_json(path))


def save_state(game_root: Path, state: FixState) -> None:
    state.schema_version = STATE_SCHEMA_VERSION
    atomic_write_json(state_path(game_root), state.to_dict())
