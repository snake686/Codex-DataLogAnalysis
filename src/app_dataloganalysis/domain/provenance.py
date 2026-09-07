"""Neutral, immutable provenance references for normalized observations."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

CONTENT_HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


def require_content_hash(value: str, *, name: str = "content_hash") -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a str")
    if not CONTENT_HASH_PATTERN.fullmatch(value):
        raise ValueError(f"{name} must be sha256:<64 lowercase hex>")
    return value


@dataclass(frozen=True, slots=True)
class Provenance:
    """Source metadata that contains no parser or vendor-library objects."""

    reference: str
    input_artifact_hash: str
    source_id: str
    source_offset: int | None = None
    attributes: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.reference, str):
            raise TypeError("provenance reference must be a str")
        if not self.reference:
            raise ValueError("provenance reference must not be empty")
        require_content_hash(self.input_artifact_hash, name="input_artifact_hash")
        if not isinstance(self.source_id, str):
            raise TypeError("provenance source_id must be a str")
        if not self.source_id:
            raise ValueError("provenance source_id must not be empty")
        if self.source_offset is not None:
            if isinstance(self.source_offset, bool) or not isinstance(self.source_offset, int):
                raise TypeError("source_offset must be an int")
            if self.source_offset < 0:
                raise ValueError("source_offset must be non-negative")
        if not isinstance(self.attributes, tuple):
            raise TypeError("provenance attributes must be two-item tuples")
        for attribute in self.attributes:
            if not isinstance(attribute, tuple) or len(attribute) != 2:
                raise TypeError("provenance attributes must be two-item tuples")
        attributes_are_strings = all(
            isinstance(key, str) and isinstance(value, str) for key, value in self.attributes
        )
        if not attributes_are_strings:
            raise TypeError("provenance attribute keys and values must be strings")
        keys = tuple(key for key, _ in self.attributes)
        if any(not key for key in keys):
            raise ValueError("provenance attribute keys must not be empty")
        if len(keys) != len(set(keys)):
            raise ValueError("provenance attribute keys must be unique")
        if self.attributes != tuple(sorted(self.attributes)):
            raise ValueError("provenance attributes must use deterministic key order")

    @classmethod
    def from_mapping(
        cls,
        *,
        reference: str,
        input_artifact_hash: str,
        source_id: str,
        source_offset: int | None = None,
        attributes: Mapping[str, str],
    ) -> Provenance:
        return cls(
            reference=reference,
            input_artifact_hash=input_artifact_hash,
            source_id=source_id,
            source_offset=source_offset,
            attributes=tuple(sorted(attributes.items())),
        )
