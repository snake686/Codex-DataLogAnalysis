"""Tests for typed values, quality, reasons, and three-valued truth."""

from dataclasses import FrozenInstanceError
from itertools import product
from typing import Any, cast

import pytest

from app_dataloganalysis.domain.values import (
    EnumValue,
    Quality,
    Reason,
    ReasonCode,
    TruthValue,
    TypedValue,
    ValueType,
    classify_scalar,
    truth_and,
    truth_not,
    truth_or,
)


def test_bool_is_classified_before_int_and_scalar_types_are_explicit() -> None:
    assert classify_scalar(True) is ValueType.BOOL
    assert classify_scalar(1) is ValueType.INT
    assert classify_scalar(1.0) is ValueType.FLOAT
    assert classify_scalar("one") is ValueType.STRING
    assert classify_scalar(EnumValue(code=1, domain_id="gear")) is ValueType.ENUM

    with pytest.raises(TypeError, match="unsupported scalar"):
        classify_scalar(cast(Any, object()))


def test_enum_values_validate_code_and_domain() -> None:
    assert EnumValue(code=1, domain_id="gear", label="drive").label == "drive"
    with pytest.raises(TypeError, match="positional"):
        EnumValue(1, "gear")  # type: ignore[misc]
    with pytest.raises(TypeError, match="code"):
        EnumValue(code=cast(Any, True), domain_id="gear")
    with pytest.raises(TypeError, match="domain_id"):
        EnumValue(code=1, domain_id=cast(Any, 7))
    with pytest.raises(ValueError, match="domain_id"):
        EnumValue(code=1, domain_id="")
    with pytest.raises(TypeError, match="label"):
        EnumValue(code=1, domain_id="gear", label=cast(Any, 7))


def test_reason_details_are_stable_and_immutable() -> None:
    reason = Reason.from_mapping(ReasonCode.DATA_MISSING, {"z": "last", "a": "first"})
    assert reason.details == (("a", "first"), ("z", "last"))
    with pytest.raises(FrozenInstanceError):
        reason.code = ReasonCode.SATISFIED  # type: ignore[misc]
    with pytest.raises(TypeError, match="ReasonCode"):
        Reason(cast(Any, "DATA_MISSING"))
    with pytest.raises(TypeError, match="two-item tuples"):
        Reason(ReasonCode.DATA_MISSING, cast(Any, [("key", "value")]))
    with pytest.raises(TypeError, match="must be strings"):
        Reason(ReasonCode.DATA_MISSING, cast(Any, (("key", 1),)))
    with pytest.raises(ValueError, match="empty"):
        Reason(ReasonCode.DATA_MISSING, (("", "value"),))
    with pytest.raises(ValueError, match="unique"):
        Reason(ReasonCode.DATA_MISSING, (("a", "1"), ("a", "2")))
    with pytest.raises(ValueError, match="deterministic"):
        Reason(ReasonCode.DATA_MISSING, (("z", "1"), ("a", "2")))


def test_typed_value_inference_and_validation() -> None:
    value = TypedValue.from_raw(True)
    assert value == TypedValue(True, ValueType.BOOL, Quality.GOOD)
    assert TypedValue.from_raw(1, value_type=ValueType.INT).value_type is ValueType.INT
    missing = TypedValue.from_raw(None, value_type=ValueType.INT, quality=Quality.MISSING)
    assert missing.value is None

    with pytest.raises(ValueError, match="must contain"):
        TypedValue(None, ValueType.INT, Quality.GOOD)
    with pytest.raises(TypeError, match="value_type is required"):
        TypedValue.from_raw(None)
    with pytest.raises(TypeError, match="does not match"):
        TypedValue.from_raw(1, value_type=ValueType.BOOL)
    with pytest.raises(TypeError, match="does not match"):
        TypedValue(1, ValueType.BOOL, Quality.GOOD)
    with pytest.raises(TypeError, match="ValueType"):
        TypedValue(1, cast(Any, "int"), Quality.GOOD)
    with pytest.raises(TypeError, match="Quality"):
        TypedValue(1, ValueType.INT, cast(Any, "good"))
    with pytest.raises(FrozenInstanceError):
        value.quality = Quality.INVALID  # type: ignore[misc]


@pytest.mark.parametrize("non_finite", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_float_is_invalid_and_never_retained(non_finite: float) -> None:
    normalized = TypedValue.from_raw(non_finite)
    assert normalized == TypedValue(None, ValueType.FLOAT, Quality.INVALID)

    with pytest.raises(ValueError, match="must not retain"):
        TypedValue(non_finite, ValueType.FLOAT, Quality.INVALID)
    with pytest.raises(TypeError, match="conflicts"):
        TypedValue.from_raw(non_finite, value_type=ValueType.INT)


def test_kleene_truth_tables_are_complete() -> None:
    expected_and = {
        (TruthValue.TRUE, TruthValue.TRUE): TruthValue.TRUE,
        (TruthValue.TRUE, TruthValue.FALSE): TruthValue.FALSE,
        (TruthValue.TRUE, TruthValue.UNKNOWN): TruthValue.UNKNOWN,
        (TruthValue.FALSE, TruthValue.TRUE): TruthValue.FALSE,
        (TruthValue.FALSE, TruthValue.FALSE): TruthValue.FALSE,
        (TruthValue.FALSE, TruthValue.UNKNOWN): TruthValue.FALSE,
        (TruthValue.UNKNOWN, TruthValue.TRUE): TruthValue.UNKNOWN,
        (TruthValue.UNKNOWN, TruthValue.FALSE): TruthValue.FALSE,
        (TruthValue.UNKNOWN, TruthValue.UNKNOWN): TruthValue.UNKNOWN,
    }
    expected_or = {
        (TruthValue.TRUE, TruthValue.TRUE): TruthValue.TRUE,
        (TruthValue.TRUE, TruthValue.FALSE): TruthValue.TRUE,
        (TruthValue.TRUE, TruthValue.UNKNOWN): TruthValue.TRUE,
        (TruthValue.FALSE, TruthValue.TRUE): TruthValue.TRUE,
        (TruthValue.FALSE, TruthValue.FALSE): TruthValue.FALSE,
        (TruthValue.FALSE, TruthValue.UNKNOWN): TruthValue.UNKNOWN,
        (TruthValue.UNKNOWN, TruthValue.TRUE): TruthValue.TRUE,
        (TruthValue.UNKNOWN, TruthValue.FALSE): TruthValue.UNKNOWN,
        (TruthValue.UNKNOWN, TruthValue.UNKNOWN): TruthValue.UNKNOWN,
    }
    for left, right in product(TruthValue, repeat=2):
        assert truth_and((left, right)) is expected_and[(left, right)]
        assert truth_or((left, right)) is expected_or[(left, right)]

    assert truth_and(()) is TruthValue.TRUE
    assert truth_or(()) is TruthValue.FALSE
    assert truth_not(TruthValue.TRUE) is TruthValue.FALSE
    assert truth_not(TruthValue.FALSE) is TruthValue.TRUE
    assert truth_not(TruthValue.UNKNOWN) is TruthValue.UNKNOWN


def test_truth_operations_reject_every_invalid_operand_before_evaluation() -> None:
    with pytest.raises(TypeError, match="TruthValue"):
        truth_not(cast(Any, None))
    with pytest.raises(TypeError, match="TruthValue"):
        truth_and(cast(Any, (TruthValue.TRUE, "unknown")))
    with pytest.raises(TypeError, match="TruthValue"):
        truth_or(cast(Any, (object(),)))

    def operands_with_invalid_middle() -> Any:
        yield TruthValue.FALSE
        yield "unknown"
        yield TruthValue.TRUE

    with pytest.raises(TypeError, match="TruthValue"):
        truth_and(operands_with_invalid_middle())
