"""Tests for neutral provenance metadata."""

from dataclasses import FrozenInstanceError
from typing import Any, cast

import pytest

from app_dataloganalysis.domain.provenance import Provenance, require_content_hash

ARTIFACT_HASH = "sha256:" + "a" * 64


def test_content_hash_contract_is_strict() -> None:
    assert require_content_hash(ARTIFACT_HASH) == ARTIFACT_HASH
    with pytest.raises(TypeError, match="must be a str"):
        require_content_hash(cast(Any, 1))
    with pytest.raises(ValueError, match="lowercase hex"):
        require_content_hash("sha256:" + "A" * 64)


def test_provenance_mapping_is_sorted_and_immutable() -> None:
    provenance = Provenance.from_mapping(
        reference="frame:7",
        input_artifact_hash=ARTIFACT_HASH,
        source_id="can0",
        source_offset=7,
        attributes={"z": "last", "a": "first"},
    )
    assert provenance.attributes == (("a", "first"), ("z", "last"))
    with pytest.raises(FrozenInstanceError):
        provenance.source_offset = 8  # type: ignore[misc]


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("reference", "", ValueError),
        ("reference", 1, TypeError),
        ("source_id", "", ValueError),
        ("source_id", 1, TypeError),
        ("source_offset", True, TypeError),
        ("source_offset", -1, ValueError),
    ],
)
def test_provenance_rejects_invalid_core_fields(
    field: str, value: object, error: type[Exception]
) -> None:
    arguments: dict[str, Any] = {
        "reference": "frame:7",
        "input_artifact_hash": ARTIFACT_HASH,
        "source_id": "can0",
        "source_offset": 7,
    }
    arguments[field] = value
    with pytest.raises(error):
        Provenance(**arguments)


@pytest.mark.parametrize(
    "attributes",
    [
        (("", "value"),),
        (("a", "1"), ("a", "2")),
        (("z", "1"), ("a", "2")),
    ],
)
def test_provenance_attributes_require_stable_keys(
    attributes: tuple[tuple[str, str], ...],
) -> None:
    with pytest.raises(ValueError):
        Provenance("frame:7", ARTIFACT_HASH, "can0", attributes=attributes)


def test_provenance_attributes_are_string_only() -> None:
    with pytest.raises(TypeError, match="two-item tuples"):
        Provenance(
            "frame:7",
            ARTIFACT_HASH,
            "can0",
            attributes=cast(Any, [("key", "value")]),
        )
    with pytest.raises(TypeError, match="two-item tuples"):
        Provenance(
            "frame:7",
            ARTIFACT_HASH,
            "can0",
            attributes=cast(Any, (("key",),)),
        )
    with pytest.raises(TypeError, match="must be strings"):
        Provenance(
            "frame:7",
            ARTIFACT_HASH,
            "can0",
            attributes=cast(Any, (("key", 1),)),
        )
