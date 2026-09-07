"""Exact, range-checked time primitives for the analysis timeline."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, localcontext
from enum import StrEnum
from typing import NewType

INT64_MIN = -(2**63)
INT64_MAX = 2**63 - 1

TimestampNs = NewType("TimestampNs", int)
DurationNs = NewType("DurationNs", int)
# Domain vocabulary aliases. The ``*Ns`` names remain useful at field boundaries.
TimePoint = TimestampNs
Duration = DurationNs

_DURATION_PATTERN = re.compile(
    r"^(?P<value>[+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*"
    r"(?P<unit>ns|us|µs|μs|ms|s|min)$"
)
_UNIT_TO_NS = {
    "ns": 1,
    "us": 1_000,
    "µs": 1_000,
    "μs": 1_000,
    "ms": 1_000_000,
    "s": 1_000_000_000,
    "min": 60_000_000_000,
}


class TimeValueError(ValueError):
    """Raised when a time value cannot be represented by the domain model."""


class DurationParseError(TimeValueError):
    """Raised when duration text is malformed or not exact to one nanosecond."""


class IntervalBound(StrEnum):
    OPEN = "open"
    CLOSED = "closed"


def _require_plain_int(value: int, *, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an int, not {type(value).__name__}")
    return value


def _require_int64(value: int, *, name: str) -> int:
    checked = _require_plain_int(value, name=name)
    if checked < INT64_MIN or checked > INT64_MAX:
        raise TimeValueError(f"{name} is outside the signed int64 range")
    return checked


def timestamp_ns(value: int) -> TimestampNs:
    """Create a checked timestamp on the monotonic analysis timeline."""
    return TimestampNs(_require_int64(value, name="timestamp_ns"))


def duration_ns(value: int, *, allow_negative: bool = False) -> DurationNs:
    """Create a checked duration, rejecting negative values by default."""
    checked = _require_int64(value, name="duration_ns")
    if checked < 0 and not allow_negative:
        raise TimeValueError("duration_ns must be non-negative")
    return DurationNs(checked)


def parse_duration(text: str, *, allow_negative: bool = False) -> DurationNs:
    """Parse unit-bearing decimal text exactly into integer nanoseconds."""
    if not isinstance(text, str):
        raise TypeError(f"duration text must be str, not {type(text).__name__}")

    match = _DURATION_PATTERN.fullmatch(text.strip())
    if match is None:
        raise DurationParseError(f"invalid duration: {text!r}")

    try:
        value = Decimal(match.group("value"))
    except InvalidOperation as error:  # pragma: no cover - guarded by the regular expression
        raise DurationParseError(f"invalid duration: {text!r}") from error

    unit_nanoseconds = _UNIT_TO_NS[match.group("unit")]
    # Decimal arithmetic follows a precision context. Expand it from the parsed
    # coefficient so no sub-nanosecond tail can be rounded away before validation.
    required_precision = len(value.as_tuple().digits) + len(str(unit_nanoseconds))
    with localcontext() as context:
        context.prec = max(context.prec, required_precision)
        nanoseconds = value * unit_nanoseconds
    integral_nanoseconds = nanoseconds.to_integral_value()
    if nanoseconds != integral_nanoseconds:
        raise DurationParseError("duration cannot be represented as an exact integer nanosecond")

    try:
        return duration_ns(int(integral_nanoseconds), allow_negative=allow_negative)
    except TimeValueError as error:
        raise DurationParseError(str(error)) from error


def add_duration(point: TimestampNs, duration: DurationNs) -> TimestampNs:
    """Add time values with signed int64 overflow checking."""
    point_value = _require_int64(point, name="timestamp_ns")
    duration_value = _require_int64(duration, name="duration_ns")
    return timestamp_ns(point_value + duration_value)


@dataclass(frozen=True, slots=True)
class TimeInterval:
    """An absolute interval with explicit lower and upper boundaries."""

    start_ns: TimestampNs
    end_ns: TimestampNs
    lower_bound: IntervalBound
    upper_bound: IntervalBound

    def __post_init__(self) -> None:
        _require_int64(self.start_ns, name="start_ns")
        _require_int64(self.end_ns, name="end_ns")
        if not isinstance(self.lower_bound, IntervalBound) or not isinstance(
            self.upper_bound, IntervalBound
        ):
            raise TypeError("interval bounds must be IntervalBound values")
        if self.end_ns < self.start_ns:
            raise TimeValueError("end_ns must not precede start_ns")

    @property
    def is_empty(self) -> bool:
        """Return whether the chosen bounds contain no time point."""
        return self.start_ns == self.end_ns and (
            self.lower_bound is IntervalBound.OPEN or self.upper_bound is IntervalBound.OPEN
        )

    def contains(self, point: TimestampNs) -> bool:
        """Test membership using the interval's explicit endpoint policy."""
        checked = timestamp_ns(point)
        lower_matches = (
            checked >= self.start_ns
            if self.lower_bound is IntervalBound.CLOSED
            else checked > self.start_ns
        )
        upper_matches = (
            checked <= self.end_ns
            if self.upper_bound is IntervalBound.CLOSED
            else checked < self.end_ns
        )
        return lower_matches and upper_matches
