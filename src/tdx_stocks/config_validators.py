from __future__ import annotations

ALLOWED_COMPRESSION = {"ZSTD", "SNAPPY", "GZIP", "UNCOMPRESSED"}


def validate_compression(value: object) -> str:
    cleaned = str(value).strip().upper()
    if cleaned not in ALLOWED_COMPRESSION:
        raise ValueError(f"invalid compression: {value}")
    return cleaned


def optional_str(value: object) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None
