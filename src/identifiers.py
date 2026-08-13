"""Shared validation for values interpolated into SQL identifiers and versions."""

from __future__ import annotations

import re

_IDENTIFIER = re.compile(r"[a-z][a-z0-9_]*")
_VERSION = re.compile(r"[0-9]+(?:\.[0-9]+)*")


def validate_identifier(value: str) -> str:
    """Return a safe lowercase SQL identifier or fail before interpolation."""
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise ValueError(f"invalid lowercase SQL identifier: {value!r}")
    return value


def validate_version(value: str) -> str:
    """Return a dotted numeric version or fail before interpolation."""
    if not isinstance(value, str) or _VERSION.fullmatch(value) is None:
        raise ValueError(f"invalid dotted numeric version: {value!r}")
    return value
