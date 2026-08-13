"""Deterministic golden identifier construction shared by engine and stewards."""

from __future__ import annotations

import hashlib


def mint_spine_id(entity: str, source: str, source_id: str) -> str:
    """Mint the auditable identifier defined by the registry origination contract."""
    if not all(isinstance(value, str) and value for value in (entity, source, source_id)):
        raise ValueError("entity, source, and source_id must be non-empty strings")
    payload = f"spine|{entity}|{source}|{source_id}"
    return "sp-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]
