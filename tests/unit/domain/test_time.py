"""Tests for exact nanosecond time primitives."""

from dataclasses import FrozenInstanceError
from typing import Any, cast

import pytest

from app_dataloganalysis.domain.time import (
    INT64_MAX,
    INT64_MIN,
    Duration,
    DurationParseError,
    IntervalBound,
    TimeInterval,
    TimePoint,
    TimeValueError,
    add_duration,
    duration_ns,
    parse_duration,
    timestamp_ns,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1 ns", 1),
        ("1 us", 1_000),
        ("1 µs", 1_000),
        ("1 μs", 1_000),
        ("500 ms", 500_000_000),
        ("1.25 s", 1_250_000_000),
        (".5 min", 30_000_000_000),
        (" 1. ns ", 1),
    ],
)
def test_parse_duration_exact_units(text: str, expected: int) -> None:
    assert parse_duration(text) == expected


@pytest.mark.parametrize("text", ["", "1", "1 hour", "nan ms", "1e3 ns"])
def test_parse_duration_rejects_malformed_text(text: str) -> None:
    with pytest.raises(DurationParseError, match="invalid duration"):
        parse_duration(text)


def test_parse_duration_requires_text_and_exact_nanoseconds() -> None:
    with pytest.raises(TypeError, match="duration text must be str"):
        parse_duration(cast(Any, 1))
    with pytest.raises(DurationParseError, match="exact integer nanosecond"):
        parse_duration("0.1 ns")
    with pytest.raises(DurationParseError, match="exact integer nanosecond"):
        parse_duration("1.0000000000000000000000000001 s")


def test_duration_sign_and_int64_boundaries_are_explicit() -> None:
    assert duration_ns(0) == 0
    assert duration_ns(INT64_MIN, allow_negative=True) == INT64_MIN
    assert parse_duration("-1 ns", allow_negative=True) == -1

    with pytest.raises(TimeValueError, match="non-negative"):
        duration_ns(-1)
    with pytest.raises(DurationParseError, match="non-negative"):
        parse_duration("-1 ns")
    with pytest.raises(DurationParseError, match="int64"):
        parse_duration(f"{INT64_MAX + 1} ns")


@pytest.mark.parametrize("value", [True, 1.0])
def test_time_values_require_plain_integers(value: object) -> None:
    with pytest.raises(TypeError, match="must be an int"):
        timestamp_ns(cast(Any, value))


def test_timestamp_and_addition_check_signed_int64_range() -> None:
    assert TimePoint(1) == timestamp_ns(1)
    assert Duration(1) == duration_ns(1)
    assert timestamp_ns(INT64_MIN) == INT64_MIN
    assert timestamp_ns(INT64_MAX) == INT64_MAX
    assert add_duration(timestamp_ns(10), duration_ns(5)) == 15
    assert add_duration(timestamp_ns(10), duration_ns(-5, allow_negative=True)) == 5

    with pytest.raises(TimeValueError, match="int64"):
        timestamp_ns(INT64_MAX + 1)
    with pytest.raises(TimeValueError, match="int64"):
        add_duration(timestamp_ns(INT64_MAX), duration_ns(1))


def test_interval_boundary_policy_and_empty_interval() -> None:
    closed = TimeInterval(
        timestamp_ns(10),
        timestamp_ns(20),
        IntervalBound.CLOSED,
        IntervalBound.CLOSED,
    )
    open_interval = TimeInterval(
        timestamp_ns(10),
        timestamp_ns(20),
        IntervalBound.OPEN,
        IntervalBound.OPEN,
    )

    assert closed.contains(timestamp_ns(10))
    assert closed.contains(timestamp_ns(20))
    assert not closed.contains(timestamp_ns(9))
    assert not closed.contains(timestamp_ns(21))
    assert not open_interval.contains(timestamp_ns(10))
    assert open_interval.contains(timestamp_ns(15))
    assert not open_interval.contains(timestamp_ns(20))
    assert not closed.is_empty
    assert TimeInterval(
        timestamp_ns(10),
        timestamp_ns(10),
        IntervalBound.OPEN,
        IntervalBound.CLOSED,
    ).is_empty
    assert not TimeInterval(
        timestamp_ns(10),
        timestamp_ns(10),
        IntervalBound.CLOSED,
        IntervalBound.CLOSED,
    ).is_empty


def test_interval_validates_order_bounds_and_is_immutable() -> None:
    with pytest.raises(TimeValueError, match="must not precede"):
        TimeInterval(timestamp_ns(2), timestamp_ns(1), IntervalBound.CLOSED, IntervalBound.OPEN)
    with pytest.raises(TypeError, match="IntervalBound"):
        TimeInterval(
            timestamp_ns(1),
            timestamp_ns(2),
            cast(Any, "closed"),
            IntervalBound.OPEN,
        )

    interval = TimeInterval(
        timestamp_ns(1), timestamp_ns(2), IntervalBound.CLOSED, IntervalBound.OPEN
    )
    with pytest.raises(FrozenInstanceError):
        interval.end_ns = timestamp_ns(3)  # type: ignore[misc]
