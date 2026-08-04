from __future__ import annotations

import os
import struct
from dataclasses import dataclass
from pathlib import Path

from .errors import FixError
from .i18n import tr

CPK_PACKET_HEADER_SIZE = 16
UTF_HEADER_SIZE = 32
UTF_STORAGE_MASK = 0xF0
UTF_STORAGE_ZERO = 0x10
UTF_STORAGE_CONSTANT = 0x30
UTF_STORAGE_PER_ROW = 0x50
UTF_TYPE_MASK = 0x0F

_UTF_VALUE_SIZES = {
    0x00: 1,
    0x01: 1,
    0x02: 2,
    0x03: 2,
    0x04: 4,
    0x05: 4,
    0x06: 8,
    0x07: 8,
    0x08: 4,
    0x0A: 4,
    0x0B: 8,
}

_UTF_NUMERIC_FORMATS = {
    0x00: ">B",
    0x01: ">B",
    0x02: ">H",
    0x03: ">H",
    0x04: ">I",
    0x05: ">I",
    0x06: ">Q",
    0x07: ">Q",
    0x08: ">f",
}


@dataclass(frozen=True, slots=True)
class CpkHeaderGeometry:
    content_offset: int
    content_size: int
    expected_content_size: int
    align: int
    content_size_position: int
    content_size_type: int
    packet_size: int
    encrypted: bool

    @property
    def valid(self) -> bool:
        return self.content_size == self.expected_content_size


@dataclass(frozen=True, slots=True)
class _UtfColumn:
    name: str
    storage: int
    value_type: int
    constant_position: int | None = None


@dataclass(frozen=True, slots=True)
class _CpkPacket:
    packet: bytearray
    encrypted: bool
    packet_size: int


@dataclass(frozen=True, slots=True)
class _UtfValue:
    value: object
    position: int | None
    value_type: int


@dataclass(frozen=True, slots=True)
class CpkEntryStorage:
    internal_path: str
    file_offset: int
    file_size: int
    extract_size: int
    compressed: bool
    toc_offset: int
    toc_packet_size: int
    toc_encrypted: bool
    file_size_position: int
    file_size_type: int
    extract_size_position: int
    extract_size_type: int


def _crypt_utf(packet: bytes | bytearray) -> bytearray:
    result = bytearray(len(packet))
    multiplier = 0x0000655F
    for index, value in enumerate(packet):
        result[index] = value ^ (multiplier & 0xFF)
        multiplier = (multiplier * 0x00004115) & 0xFFFFFFFF
    return result


def _read_c_string(packet: bytes | bytearray, offset: int) -> str:
    if offset < 0 or offset >= len(packet):
        raise FixError(tr("The CPK UTF string offset is out of range: {offset}", offset=offset))
    try:
        end = packet.index(0, offset)
    except ValueError as exc:
        raise FixError(tr("The end of the CPK UTF string could not be found.")) from exc
    try:
        return bytes(packet[offset:end]).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FixError(tr("The CPK UTF string could not be decoded as UTF-8.")) from exc


def _value_size(value_type: int) -> int:
    try:
        return _UTF_VALUE_SIZES[value_type]
    except KeyError as exc:
        raise FixError(tr("Unsupported CPK UTF value type: 0x{value_type:02x}", value_type=value_type)) from exc


def _read_numeric(packet: bytes | bytearray, position: int, value_type: int) -> int:
    try:
        format_string = _UTF_NUMERIC_FORMATS[value_type]
    except KeyError as exc:
        raise FixError(
            tr(
                "Unsupported numeric field type in the CPK header: 0x{value_type:02x}",
                value_type=value_type,
            )
        ) from exc
    try:
        value = struct.unpack_from(format_string, packet, position)[0]
    except struct.error as exc:
        raise FixError(tr("The CPK UTF numeric field is outside the packet bounds.")) from exc
    if isinstance(value, float):
        raise FixError(tr("A required CPK header field is not an integer type."))
    return int(value)


def _write_numeric(
    packet: bytearray,
    position: int,
    value_type: int,
    value: int,
) -> None:
    try:
        format_string = _UTF_NUMERIC_FORMATS[value_type]
    except KeyError as exc:
        raise FixError(
            tr(
                "Unsupported numeric field type in the CPK header: 0x{value_type:02x}",
                value_type=value_type,
            )
        ) from exc
    if value_type == 0x08:
        raise FixError(tr("A CPK header size field cannot be written as a floating-point value."))
    try:
        struct.pack_into(format_string, packet, position, value)
    except (struct.error, OverflowError) as exc:
        raise FixError(tr("The CPK header size value cannot be written: {value}", value=value)) from exc


def _read_cpk_packet(path: Path) -> _CpkPacket:
    try:
        with path.open("rb") as stream:
            if stream.read(4) != b"CPK ":
                raise FixError(tr("The CPK header is invalid: {path}", path=path))
            fixed = stream.read(CPK_PACKET_HEADER_SIZE - 4)
            if len(fixed) != CPK_PACKET_HEADER_SIZE - 4:
                raise FixError(tr("The CPK packet header is truncated: {path}", path=path))
            packet_size = struct.unpack_from("<Q", fixed, 4)[0]
            if packet_size < UTF_HEADER_SIZE or packet_size > 16 * 1024 * 1024:
                raise FixError(tr("The CPK UTF packet size is invalid: {size}", size=packet_size))
            encoded = stream.read(packet_size)
    except OSError as exc:
        raise FixError(tr("The CPK header could not be read: {path}\n{error}", path=path, error=exc)) from exc

    if len(encoded) != packet_size:
        raise FixError(tr("The CPK UTF packet is truncated: {path}", path=path))
    encrypted = not encoded.startswith(b"@UTF")
    packet = _crypt_utf(encoded) if encrypted else bytearray(encoded)
    if not packet.startswith(b"@UTF"):
        raise FixError(tr("The CPK UTF packet signature is invalid: {path}", path=path))
    return _CpkPacket(packet, encrypted, packet_size)


def _read_utf_packet_at(
    path: Path,
    offset: int,
    *,
    signature: bytes,
) -> _CpkPacket:
    try:
        with path.open("rb") as stream:
            stream.seek(offset)
            if stream.read(4) != signature:
                raise FixError(
                    tr(
                        "The CPK chunk signature is invalid: {signature}",
                        signature=signature.decode("ascii", errors="replace"),
                    )
                )
            fixed = stream.read(CPK_PACKET_HEADER_SIZE - 4)
            if len(fixed) != CPK_PACKET_HEADER_SIZE - 4:
                raise FixError(
                    tr(
                        "The CPK chunk header is truncated: {path}",
                        path=path,
                    )
                )
            packet_size = struct.unpack_from("<Q", fixed, 4)[0]
            if packet_size < UTF_HEADER_SIZE or packet_size > 16 * 1024 * 1024:
                raise FixError(
                    tr(
                        "The CPK UTF packet size is invalid: {size}",
                        size=packet_size,
                    )
                )
            encoded = stream.read(packet_size)
    except OSError as exc:
        raise FixError(
            tr(
                "The CPK UTF chunk could not be read: {path}\n{error}",
                path=path,
                error=exc,
            )
        ) from exc

    if len(encoded) != packet_size:
        raise FixError(
            tr(
                "The CPK UTF packet is truncated: {path}",
                path=path,
            )
        )
    encrypted = not encoded.startswith(b"@UTF")
    packet = _crypt_utf(encoded) if encrypted else bytearray(encoded)
    if not packet.startswith(b"@UTF"):
        raise FixError(
            tr(
                "The CPK UTF packet signature is invalid: {path}",
                path=path,
            )
        )
    return _CpkPacket(packet, encrypted, packet_size)


def _read_utf_value(
    packet: bytearray,
    position: int,
    value_type: int,
    *,
    strings_offset: int,
) -> object:
    if value_type in _UTF_NUMERIC_FORMATS:
        return _read_numeric(packet, position, value_type)
    if value_type == 0x0A:
        try:
            relative = struct.unpack_from(">I", packet, position)[0]
        except struct.error as exc:
            raise FixError(
                tr(
                    "A CPK UTF string value is outside the packet bounds.",
                )
            ) from exc
        return _read_c_string(packet, strings_offset + relative)
    if value_type == 0x0B:
        try:
            return struct.unpack_from(">II", packet, position)
        except struct.error as exc:
            raise FixError(
                tr(
                    "A CPK UTF data value is outside the packet bounds.",
                )
            ) from exc
    raise FixError(
        tr(
            "Unsupported CPK UTF value type: 0x{value_type:02x}",
            value_type=value_type,
        )
    )


def _parse_utf_table(packet: bytearray) -> tuple[dict[str, _UtfValue], ...]:
    try:
        (
            signature,
            table_size,
            rows_offset_raw,
            strings_offset_raw,
            _data_offset_raw,
            _table_name,
            column_count,
            row_length,
            row_count,
        ) = struct.unpack_from(">4sIIIIIHHI", packet, 0)
    except struct.error as exc:
        raise FixError(
            tr("The CPK UTF header is truncated.")
        ) from exc

    if signature != b"@UTF":
        raise FixError(
            tr(
                "The CPK UTF packet signature is invalid.",
            )
        )
    if table_size + 8 > len(packet):
        raise FixError(
            tr(
                "The CPK UTF table size exceeds the packet bounds.",
            )
        )

    rows_offset = rows_offset_raw + 8
    strings_offset = strings_offset_raw + 8
    rows_end = rows_offset + row_length * row_count
    if not (
        UTF_HEADER_SIZE <= rows_offset <= rows_end <= strings_offset <= len(packet)
    ):
        raise FixError(
            tr(
                "The CPK UTF row/string offsets are invalid.",
            )
        )

    columns: list[_UtfColumn] = []
    cursor = UTF_HEADER_SIZE
    for _ in range(column_count):
        if cursor >= rows_offset:
            raise FixError(
                tr(
                    "The CPK UTF column definition overlaps the row area.",
                )
            )
        flags = packet[cursor]
        cursor += 1
        if flags == 0:
            if cursor + 4 > rows_offset:
                raise FixError(
                    tr(
                        "The extended CPK UTF column flag is truncated.",
                    )
                )
            cursor += 3
            flags = packet[cursor]
            cursor += 1
        if cursor + 4 > rows_offset:
            raise FixError(
                tr(
                    "The CPK UTF column-name offset is truncated.",
                )
            )
        name_offset = struct.unpack_from(">I", packet, cursor)[0]
        cursor += 4
        storage = flags & UTF_STORAGE_MASK
        value_type = flags & UTF_TYPE_MASK
        constant_position: int | None = None
        if storage == UTF_STORAGE_CONSTANT:
            constant_position = cursor
            cursor += _value_size(value_type)
            if cursor > rows_offset:
                raise FixError(
                    tr(
                        "The CPK UTF constant column value is truncated.",
                    )
                )
        columns.append(
            _UtfColumn(
                _read_c_string(packet, strings_offset + name_offset),
                storage,
                value_type,
                constant_position,
            )
        )

    rows: list[dict[str, _UtfValue]] = []
    for row_index in range(row_count):
        cursor = rows_offset + row_index * row_length
        row_end = cursor + row_length
        values: dict[str, _UtfValue] = {}
        for column in columns:
            if column.storage == UTF_STORAGE_ZERO:
                zero_value: object = 0
                if column.value_type == 0x0A:
                    zero_value = ""
                elif column.value_type == 0x0B:
                    zero_value = (0, 0)
                values[column.name] = _UtfValue(
                    zero_value, None, column.value_type
                )
                continue
            if column.storage == UTF_STORAGE_CONSTANT:
                if column.constant_position is None:
                    raise FixError(
                        tr(
                            "A UTF constant column position is missing.",
                        )
                    )
                values[column.name] = _UtfValue(
                    _read_utf_value(
                        packet,
                        column.constant_position,
                        column.value_type,
                        strings_offset=strings_offset,
                    ),
                    column.constant_position,
                    column.value_type,
                )
                continue
            if column.storage != UTF_STORAGE_PER_ROW:
                continue
            position = cursor
            values[column.name] = _UtfValue(
                _read_utf_value(
                    packet,
                    position,
                    column.value_type,
                    strings_offset=strings_offset,
                ),
                position,
                column.value_type,
            )
            cursor += _value_size(column.value_type)

        if cursor != row_end:
            raise FixError(
                tr(
                    "The CPK UTF row length does not match the column definition: expected={expected}, actual={actual}",
                    expected=row_end,
                    actual=cursor,
                )
            )
        rows.append(values)
    return tuple(rows)


def _parse_utf_row(packet: bytearray) -> dict[str, tuple[int, int | None, int]]:
    rows = _parse_utf_table(packet)
    if len(rows) != 1:
        raise FixError(
            tr(
                "Unexpected CPK header row count: {count}",
                count=len(rows),
            )
        )
    values: dict[str, tuple[int, int | None, int]] = {}
    for name, field in rows[0].items():
        if isinstance(field.value, int):
            values[name] = (field.value, field.position, field.value_type)
    return values


def _required_field(
    values: dict[str, tuple[int, int | None, int]],
    name: str,
) -> tuple[int, int, int]:
    field = values.get(name)
    if field is None:
        raise FixError(tr("A required field was not found in the CPK header: {name}", name=name))
    value, position, value_type = field
    if position is None:
        raise FixError(tr("The CPK header field uses a storage format that cannot be modified: {name}", name=name))
    return value, position, value_type


def _required_utf_value(
    values: dict[str, _UtfValue],
    name: str,
    *,
    expected_type: type,
) -> _UtfValue:
    field = values.get(name)
    if field is None or not isinstance(field.value, expected_type):
        raise FixError(
            tr(
                "A required field was not found in the CPK TOC: {name}",
                name=name,
            )
        )
    return field


def _normalize_internal_path(value: str) -> str:
    return value.strip().replace("\\", "/").lstrip("./")


def inspect_cpk_entry_storage(path: Path, internal_path: str) -> CpkEntryStorage:
    root_values = _parse_utf_row(_read_cpk_packet(path).packet)
    toc_offset, _, _ = _required_field(root_values, "TocOffset")
    content_offset, _, _ = _required_field(root_values, "ContentOffset")
    toc = _read_utf_packet_at(path, toc_offset, signature=b"TOC ")
    target = _normalize_internal_path(internal_path).casefold()
    matches: list[dict[str, _UtfValue]] = []
    for row in _parse_utf_table(toc.packet):
        directory = _required_utf_value(
            row, "DirName", expected_type=str
        ).value
        filename = _required_utf_value(
            row, "FileName", expected_type=str
        ).value
        combined = "/".join(
            part for part in (str(directory).strip("/"), str(filename)) if part
        )
        if _normalize_internal_path(combined).casefold() == target:
            matches.append(row)
    if len(matches) != 1:
        raise FixError(
            tr(
                "Exactly one target entry was not found in the CPK TOC: {path} (found {count})",
                path=internal_path,
                count=len(matches),
            )
        )

    row = matches[0]
    file_offset_field = _required_utf_value(
        row, "FileOffset", expected_type=int
    )
    file_size_field = _required_utf_value(row, "FileSize", expected_type=int)
    extract_size_field = _required_utf_value(
        row, "ExtractSize", expected_type=int
    )
    if file_size_field.position is None or extract_size_field.position is None:
        raise FixError(
            tr(
                "The target CPK entry uses non-editable size fields: {path}",
                path=internal_path,
            )
        )

    absolute_offset = int(file_offset_field.value) + min(
        toc_offset, content_offset
    )
    file_size = int(file_size_field.value)
    extract_size = int(extract_size_field.value)
    if (
        absolute_offset < 0
        or file_size <= 0
        or extract_size <= 0
        or absolute_offset + file_size > path.stat().st_size
    ):
        raise FixError(
            tr(
                "The storage range of the target CPK entry is invalid: {path}",
                path=internal_path,
            )
        )
    try:
        with path.open("rb") as stream:
            stream.seek(absolute_offset)
            signature = stream.read(8)
    except OSError as exc:
        raise FixError(
            tr(
                "The target CPK entry could not be read: {path}\n{error}",
                path=internal_path,
                error=exc,
            )
        ) from exc

    return CpkEntryStorage(
        internal_path=_normalize_internal_path(internal_path),
        file_offset=absolute_offset,
        file_size=file_size,
        extract_size=extract_size,
        compressed=signature == b"CRILAYLA",
        toc_offset=toc_offset,
        toc_packet_size=toc.packet_size,
        toc_encrypted=toc.encrypted,
        file_size_position=file_size_field.position,
        file_size_type=file_size_field.value_type,
        extract_size_position=extract_size_field.position,
        extract_size_type=extract_size_field.value_type,
    )


def update_cpk_entry_sizes(
    path: Path,
    internal_path: str,
    *,
    file_size: int,
    extract_size: int,
) -> tuple[CpkEntryStorage, CpkEntryStorage]:
    if file_size <= 0 or extract_size <= 0:
        raise FixError(
            tr(
                "CPK entry sizes must be greater than zero.",
            )
        )
    before = inspect_cpk_entry_storage(path, internal_path)
    toc = _read_utf_packet_at(path, before.toc_offset, signature=b"TOC ")
    if (
        toc.packet_size != before.toc_packet_size
        or toc.encrypted != before.toc_encrypted
    ):
        raise FixError(
            tr(
                "The CPK TOC could not be interpreted consistently.",
            )
        )
    _write_numeric(
        toc.packet,
        before.file_size_position,
        before.file_size_type,
        file_size,
    )
    _write_numeric(
        toc.packet,
        before.extract_size_position,
        before.extract_size_type,
        extract_size,
    )
    encoded = _crypt_utf(toc.packet) if toc.encrypted else toc.packet
    try:
        with path.open("r+b") as stream:
            stream.seek(before.toc_offset + CPK_PACKET_HEADER_SIZE)
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as exc:
        raise FixError(
            tr(
                "The CPK TOC entry sizes could not be updated: {path}\n{error}",
                path=path,
                error=exc,
            )
        ) from exc

    after = inspect_cpk_entry_storage(path, internal_path)
    if after.file_size != file_size or after.extract_size != extract_size:
        raise FixError(
            tr(
                "Verification of the CPK TOC entry size update failed: {path}",
                path=internal_path,
            )
        )
    return before, after


def _align_up(value: int, align: int) -> int:
    return ((value + align - 1) // align) * align


def inspect_cpk_header_geometry(path: Path) -> CpkHeaderGeometry:
    parsed = _read_cpk_packet(path)
    values = _parse_utf_row(parsed.packet)
    content_offset, _, _ = _required_field(values, "ContentOffset")
    content_size, content_size_position, content_size_type = _required_field(
        values, "ContentSize"
    )
    align, _, _ = _required_field(values, "Align")

    if align <= 0 or align > 1024 * 1024 or align & (align - 1):
        raise FixError(tr("The CPK alignment value is invalid: {align}", align=align))
    if content_offset <= 0 or content_offset >= path.stat().st_size:
        raise FixError(tr("The CPK content offset is invalid: {offset}", offset=content_offset))

    trailing_offsets: list[int] = []
    for name in ("EtocOffset", "GtocOffset", "HgtocOffset"):
        field = values.get(name)
        if field and field[0] > content_offset:
            trailing_offsets.append(field[0])
    content_end = (
        min(trailing_offsets)
        if trailing_offsets
        else _align_up(path.stat().st_size, align)
    )
    if content_end <= content_offset:
        raise FixError(
            tr(
                "The CPK content end position is before the start position: {end}",
                end=content_end,
            )
        )
    expected_content_size = content_end - content_offset
    return CpkHeaderGeometry(
        content_offset=content_offset,
        content_size=content_size,
        expected_content_size=expected_content_size,
        align=align,
        content_size_position=content_size_position,
        content_size_type=content_size_type,
        packet_size=parsed.packet_size,
        encrypted=parsed.encrypted,
    )


def assert_cpk_header_geometry(path: Path, *, label: str = "CPK") -> CpkHeaderGeometry:
    geometry = inspect_cpk_header_geometry(path)
    if not geometry.valid:
        raise FixError(
            tr(
                "The CPK ContentSize in {label} does not match the actual content area.\nHeader value: {header}\nActual value: {actual}\nFile: {path}",
                label=label,
                header=geometry.content_size,
                actual=geometry.expected_content_size,
                path=path,
            )
        )
    return geometry


def repair_cpk_header_geometry(path: Path) -> tuple[CpkHeaderGeometry, CpkHeaderGeometry]:
    before = inspect_cpk_header_geometry(path)
    if before.valid:
        return before, before

    parsed = _read_cpk_packet(path)
    values = _parse_utf_row(parsed.packet)
    _current, position, value_type = _required_field(values, "ContentSize")
    if position != before.content_size_position or value_type != before.content_size_type:
        raise FixError(tr("The CPK ContentSize location could not be resolved consistently."))
    _write_numeric(
        parsed.packet,
        before.content_size_position,
        before.content_size_type,
        before.expected_content_size,
    )
    encoded = _crypt_utf(parsed.packet) if parsed.encrypted else parsed.packet
    try:
        with path.open("r+b") as stream:
            stream.seek(CPK_PACKET_HEADER_SIZE)
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as exc:
        raise FixError(tr("The CPK ContentSize header could not be updated: {path}\n{error}", path=path, error=exc)) from exc

    after = assert_cpk_header_geometry(path, label=tr("CPK after header repair"))
    return before, after
