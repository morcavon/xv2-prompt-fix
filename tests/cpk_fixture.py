from __future__ import annotations

import struct
from pathlib import Path


def _crypt_utf(packet: bytes) -> bytes:
    result = bytearray(len(packet))
    multiplier = 0x0000655F
    for index, value in enumerate(packet):
        result[index] = value ^ (multiplier & 0xFF)
        multiplier = (multiplier * 0x00004115) & 0xFFFFFFFF
    return bytes(result)


def write_test_cpk(
    path: Path,
    *,
    content_size: int,
    encrypted: bool = True,
    file_size: int = 0x3000,
) -> None:
    content_offset = 0x1000
    align = 0x800
    strings = b"CpkHeader\0ContentOffset\0ContentSize\0Align\0"
    name_offsets = {
        "ContentOffset": strings.index(b"ContentOffset"),
        "ContentSize": strings.index(b"ContentSize"),
        "Align": strings.index(b"Align"),
    }
    columns = b"".join(
        (
            struct.pack(">BI", 0x56, name_offsets["ContentOffset"]),
            struct.pack(">BI", 0x56, name_offsets["ContentSize"]),
            struct.pack(">BI", 0x52, name_offsets["Align"]),
        )
    )
    row = struct.pack(">QQH", content_offset, content_size, align)
    rows_offset = 32 + len(columns)
    strings_offset = rows_offset + len(row)
    packet_size = strings_offset + len(strings)
    packet = bytearray(packet_size)
    struct.pack_into(
        ">4sIIIIIHHI",
        packet,
        0,
        b"@UTF",
        packet_size - 8,
        rows_offset - 8,
        strings_offset - 8,
        packet_size - 8,
        0,
        3,
        len(row),
        1,
    )
    packet[32:rows_offset] = columns
    packet[rows_offset:strings_offset] = row
    packet[strings_offset:] = strings
    encoded = _crypt_utf(bytes(packet)) if encrypted else bytes(packet)
    prefix = b"CPK " + struct.pack("<IQ", 0, len(encoded)) + encoded
    if len(prefix) >= file_size:
        raise AssertionError("The test CPK is too small.")
    path.write_bytes(prefix + b"\0" * (file_size - len(prefix)))


def _string_table(*values: str) -> tuple[bytes, dict[str, int]]:
    data = bytearray()
    offsets: dict[str, int] = {}
    for value in values:
        offsets[value] = len(data)
        data.extend(value.encode("utf-8"))
        data.append(0)
    return bytes(data), offsets


def _utf_packet(
    *,
    table_name: str,
    columns: tuple[tuple[str, int], ...],
    row: bytes,
    strings: bytes,
    string_offsets: dict[str, int],
) -> bytes:
    column_data = b"".join(
        struct.pack(">BI", flags, string_offsets[name]) for name, flags in columns
    )
    rows_offset = 32 + len(column_data)
    strings_offset = rows_offset + len(row)
    packet_size = strings_offset + len(strings)
    packet = bytearray(packet_size)
    struct.pack_into(
        ">4sIIIIIHHI",
        packet,
        0,
        b"@UTF",
        packet_size - 8,
        rows_offset - 8,
        strings_offset - 8,
        packet_size - 8,
        string_offsets[table_name],
        len(columns),
        len(row),
        1,
    )
    packet[32:rows_offset] = column_data
    packet[rows_offset:strings_offset] = row
    packet[strings_offset:] = strings
    return bytes(packet)


def write_test_cpk_with_entry(
    path: Path,
    *,
    internal_path: str,
    raw_payload: bytes,
    extract_size: int,
    encrypted: bool = True,
) -> None:
    toc_offset = 0x800
    content_offset = 0x1000
    align = 0x800
    file_size = 0x5000
    if len(raw_payload) > align:
        raise AssertionError("The raw test entry is too large.")

    root_strings, root_offsets = _string_table(
        "CpkHeader",
        "TocOffset",
        "ContentOffset",
        "ContentSize",
        "Align",
    )
    root_packet = _utf_packet(
        table_name="CpkHeader",
        columns=(
            ("TocOffset", 0x56),
            ("ContentOffset", 0x56),
            ("ContentSize", 0x56),
            ("Align", 0x52),
        ),
        row=struct.pack(
            ">QQQH",
            toc_offset,
            content_offset,
            file_size - content_offset,
            align,
        ),
        strings=root_strings,
        string_offsets=root_offsets,
    )

    normalized = internal_path.replace("\\", "/").strip("/")
    directory, filename = normalized.rsplit("/", 1)
    toc_strings, toc_offsets = _string_table(
        "CpkTocInfo",
        "DirName",
        "FileName",
        "FileSize",
        "ExtractSize",
        "FileOffset",
        "ID",
        "UserString",
        directory,
        filename,
        "<NULL>",
    )
    toc_packet = _utf_packet(
        table_name="CpkTocInfo",
        columns=(
            ("DirName", 0x5A),
            ("FileName", 0x5A),
            ("FileSize", 0x54),
            ("ExtractSize", 0x54),
            ("FileOffset", 0x56),
            ("ID", 0x54),
            ("UserString", 0x5A),
        ),
        row=struct.pack(
            ">IIIIQII",
            toc_offsets[directory],
            toc_offsets[filename],
            len(raw_payload),
            extract_size,
            content_offset - toc_offset,
            1,
            toc_offsets["<NULL>"],
        ),
        strings=toc_strings,
        string_offsets=toc_offsets,
    )

    root_encoded = _crypt_utf(root_packet) if encrypted else root_packet
    toc_encoded = _crypt_utf(toc_packet) if encrypted else toc_packet
    output = bytearray(file_size)
    root_chunk = b"CPK " + struct.pack("<IQ", 0, len(root_encoded)) + root_encoded
    toc_chunk = b"TOC " + struct.pack("<IQ", 0, len(toc_encoded)) + toc_encoded
    output[: len(root_chunk)] = root_chunk
    output[toc_offset : toc_offset + len(toc_chunk)] = toc_chunk
    output[content_offset : content_offset + len(raw_payload)] = raw_payload
    path.write_bytes(output)
