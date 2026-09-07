"""Typed scalar, quality, reason, and three-valued truth primitives."""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum


class TruthValue(StrEnum):
    TRUE = "true"
    FALSE = "false"
    UNKNOWN = "unknown"


class Quality(StrEnum):
    GOOD = "good"
    MISSING = "missing"
    STALE = "stale"
    INVALID = "invalid"
    DECODE_ERROR = "decode_error"
    OUT_OF_RANGE = "out_of_range"
    UNAVAILABLE = "unavailable"


class ReasonCode(StrEnum):
    SATISFIED = "SATISFIED"
    CONDITION_VIOLATED = "CONDITION_VIOLATED"
    TIMEOUT = "TIMEOUT"
    DATA_MISSING = "DATA_MISSING"
    DATA_STALE = "DATA_STALE"
    DATA_GAP = "DATA_GAP"
    INCOMPLETE_WINDOW = "INCOMPLETE_WINDOW"
    NO_TRIGGER = "NO_TRIGGER"
    RULE_INVALID = "RULE_INVALID"
    DECODE_ERROR = "DECODE_ERROR"
    OUT_OF_ORDER = "OUT_OF_ORDER"
    RESOURCE_LIMIT = "RESOURCE_LIMIT"
    CANCELLED = "CANCELLED"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    OUT_OF_RANGE = "OUT_OF_RANGE"
    MULTIPLEX_INACTIVE = "MULTIPLEX_INACTIVE"
    INVALID_VALUE = "INVALID_VALUE"


class ValueType(StrEnum):
    BOOL = "bool"
    INT = "int"
    FLOAT = "float"
    STRING = "string"
    ENUM = "enum"


@dataclass(frozen=True, slots=True, kw_only=True)
class EnumValue:
    code: int
    domain_id: str
    label: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.code, bool) or not isinstance(self.code, int):
            raise TypeError("enum code must be an int")
        if not isinstance(self.domain_id, str):
            raise TypeError("enum domain_id must be a str")
        if not self.domain_id:
            raise ValueError("enum domain_id must not be empty")
        if self.label is not None and not isinstance(self.label, str):
            raise TypeError("enum label must be a str or None")


type ScalarValue = bool | int | float | str | EnumValue


@dataclass(frozen=True, slots=True)
class Reason:
    code: ReasonCode
    details: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.code, ReasonCode):
            raise TypeError("reason code must be a ReasonCode")
        if not isinstance(self.details, tuple) or any(
            not isinstance(detail, tuple) or len(detail) != 2 for detail in self.details
        ):
            raise TypeError("reason details must be two-item tuples")
        details_are_strings = all(
            isinstance(key, str) and isinstance(value, str) for key, value in self.details
        )
        if not details_are_strings:
            raise TypeError("reason detail keys and values must be strings")
        keys = tuple(key for key, _ in self.details)
        if any(not key for key in keys):
            raise ValueError("reason detail keys must not be empty")
        if len(keys) != len(set(keys)):
            raise ValueError("reason detail keys must be unique")
        if self.details != tuple(sorted(self.details)):
            raise ValueError("reason details must use deterministic key order")

    @classmethod
    def from_mapping(cls, code: ReasonCode, details: Mapping[str, str]) -> Reason:
        return cls(code=code, details=tuple(sorted(details.items())))


def classify_scalar(value: ScalarValue) -> ValueType:
    """Classify Python scalar values without treating bool as int."""
    if isinstance(value, bool):
        return ValueType.BOOL
    if isinstance(value, EnumValue):
        return ValueType.ENUM
    if isinstance(value, int):
        return ValueType.INT
    if isinstance(value, float):
        return ValueType.FLOAT
    if isinstance(value, str):
        return ValueType.STRING
    raise TypeError(f"unsupported scalar type: {type(value).__name__}")


@dataclass(frozen=True, slots=True)
class TypedValue:
    value: ScalarValue | None
    value_type: ValueType
    quality: Quality

    def __post_init__(self) -> None:
        if not isinstance(self.value_type, ValueType):
            raise TypeError("value_type must be a ValueType")
        if not isinstance(self.quality, Quality):
            raise TypeError("quality must be a Quality")
        if self.value is None:
            if self.quality is Quality.GOOD:
                raise ValueError("GOOD typed values must contain a value")
            return
        if isinstance(self.value, float) and not math.isfinite(self.value):
            raise ValueError("typed values must not retain NaN or infinity")
        if classify_scalar(self.value) is not self.value_type:
            raise TypeError("value does not match the declared value_type")

    @classmethod
    def from_raw(
        cls,
        value: ScalarValue | None,
        *,
        value_type: ValueType | None = None,
        quality: Quality = Quality.GOOD,
    ) -> TypedValue:
        """Normalize raw scalar input, mapping non-finite floats to INVALID."""
        if isinstance(value, float) and not math.isfinite(value):
            if value_type not in (None, ValueType.FLOAT):
                raise TypeError("non-finite float conflicts with the declared value_type")
            return cls(value=None, value_type=ValueType.FLOAT, quality=Quality.INVALID)
        if value is None:
            if value_type is None:
                raise TypeError("value_type is required when value is absent")
            return cls(value=None, value_type=value_type, quality=quality)

        inferred_type = classify_scalar(value)
        if value_type is not None and value_type is not inferred_type:
            raise TypeError("value does not match the declared value_type")
        return cls(value=value, value_type=inferred_type, quality=quality)


def truth_not(value: TruthValue) -> TruthValue:
    if not isinstance(value, TruthValue):
        raise TypeError("truth operand must be a TruthValue")
    if value is TruthValue.TRUE:
        return TruthValue.FALSE
    if value is TruthValue.FALSE:
        return TruthValue.TRUE
    return TruthValue.UNKNOWN


def _validated_truth_values(values: Iterable[TruthValue]) -> tuple[TruthValue, ...]:
    operands = tuple(values)
    if any(not isinstance(value, TruthValue) for value in operands):
        raise TypeError("truth operands must be TruthValue values")
    return operands


def truth_and(values: Iterable[TruthValue]) -> TruthValue:
    has_unknown = False
    for value in _validated_truth_values(values):
        if value is TruthValue.FALSE:
            return TruthValue.FALSE
        if value is TruthValue.UNKNOWN:
            has_unknown = True
    return TruthValue.UNKNOWN if has_unknown else TruthValue.TRUE


def truth_or(values: Iterable[TruthValue]) -> TruthValue:
    has_unknown = False
    for value in _validated_truth_values(values):
        if value is TruthValue.TRUE:
            return TruthValue.TRUE
        if value is TruthValue.UNKNOWN:
            has_unknown = True
    return TruthValue.UNKNOWN if has_unknown else TruthValue.FALSE
