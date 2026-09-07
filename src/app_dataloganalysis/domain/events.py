"""Immutable normalized events and atomic transaction boundaries."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Literal

from app_dataloganalysis.domain.provenance import require_content_hash
from app_dataloganalysis.domain.time import TimestampNs, timestamp_ns
from app_dataloganalysis.domain.values import (
    Quality,
    Reason,
    ReasonCode,
    ScalarValue,
    TypedValue,
    ValueType,
)


def _require_non_negative_int(value: int, *, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an int")
    if value < 0:
        raise ValueError(f"{name} must be non-negative")
    return value


def _require_text(value: str, *, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a str")
    if not value:
        raise ValueError(f"{name} must not be empty")
    return value


def _content_id(payload: dict[str, object]) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(canonical).hexdigest()}"


def transaction_id(
    *,
    input_artifact_hash: str,
    source_id: str,
    timestamp: TimestampNs,
    transaction_sequence: int,
) -> str:
    """Derive the contract's transaction-id/v1 content identity."""
    require_content_hash(input_artifact_hash, name="input_artifact_hash")
    _require_text(source_id, name="source_id")
    checked_timestamp = timestamp_ns(timestamp)
    checked_sequence = _require_non_negative_int(
        transaction_sequence,
        name="transaction_sequence",
    )
    return _content_id(
        {
            "input_artifact_hash": input_artifact_hash,
            "kind": "transaction-id/v1",
            "source_id": source_id,
            "timestamp_ns": str(checked_timestamp),
            "transaction_sequence": str(checked_sequence),
        }
    )


def event_id(
    *,
    input_artifact_hash: str,
    source_id: str,
    timestamp: TimestampNs,
    transaction_sequence: int,
    item_index: int,
    binding_id: str,
) -> str:
    """Derive the contract's event-id/v1 content identity."""
    require_content_hash(input_artifact_hash, name="input_artifact_hash")
    _require_text(source_id, name="source_id")
    _require_text(binding_id, name="binding_id")
    checked_timestamp = timestamp_ns(timestamp)
    checked_sequence = _require_non_negative_int(
        transaction_sequence,
        name="transaction_sequence",
    )
    checked_item_index = _require_non_negative_int(item_index, name="item_index")
    return _content_id(
        {
            "binding_id": binding_id,
            "input_artifact_hash": input_artifact_hash,
            "item_index": str(checked_item_index),
            "kind": "event-id/v1",
            "source_id": source_id,
            "timestamp_ns": str(checked_timestamp),
            "transaction_sequence": str(checked_sequence),
        }
    )


@dataclass(frozen=True, slots=True, order=True)
class TransactionOrderingKey:
    timestamp_ns: TimestampNs
    source_id: str
    transaction_sequence: int

    def __post_init__(self) -> None:
        timestamp_ns(self.timestamp_ns)
        _require_text(self.source_id, name="source_id")
        _require_non_negative_int(self.transaction_sequence, name="transaction_sequence")


@dataclass(frozen=True, slots=True, order=True)
class EventOrderingKey:
    timestamp_ns: TimestampNs
    source_id: str
    transaction_sequence: int
    item_index: int

    def __post_init__(self) -> None:
        timestamp_ns(self.timestamp_ns)
        _require_text(self.source_id, name="source_id")
        _require_non_negative_int(self.transaction_sequence, name="transaction_sequence")
        _require_non_negative_int(self.item_index, name="item_index")


@dataclass(frozen=True, slots=True)
class DataScope:
    """An explicit source-key, channel, or whole-input data scope."""

    whole_input: bool = False
    channel: str | None = None
    source_keys: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.whole_input, bool):
            raise TypeError("whole_input must be a bool")
        if not isinstance(self.source_keys, tuple):
            raise TypeError("data scope source_keys must be a tuple")
        has_channel = self.channel is not None
        has_source_keys = bool(self.source_keys)
        selectors = int(self.whole_input) + int(has_channel) + int(has_source_keys)
        if selectors != 1:
            raise ValueError("data scope must select exactly one scope kind")
        if self.channel is not None and not isinstance(self.channel, str):
            raise TypeError("data scope channel must be a str or None")
        if self.channel == "":
            raise ValueError("data scope channel must not be empty")
        if any(not isinstance(source_key, str) for source_key in self.source_keys):
            raise TypeError("data scope source keys must be strings")
        if any(not source_key for source_key in self.source_keys):
            raise ValueError("data scope source keys must not be empty")
        if len(self.source_keys) != len(set(self.source_keys)):
            raise ValueError("data scope source keys must be unique")
        if self.source_keys != tuple(sorted(self.source_keys)):
            raise ValueError("data scope source keys must use deterministic order")

    @classmethod
    def for_source_keys(cls, *source_keys: str) -> DataScope:
        return cls(source_keys=tuple(sorted(source_keys)))

    def canonical_projection(self) -> dict[str, object]:
        """Return the versioned scope projection used by control-event identity."""
        if self.whole_input:
            return {"kind": "whole_input"}
        if self.channel is not None:
            return {"channel": self.channel, "kind": "channel"}
        return {"kind": "source_keys", "source_keys": list(self.source_keys)}


type ControlEventKind = Literal["quality_update", "gap_start", "gap_end"]


def control_binding_id(*, event_kind: ControlEventKind, scope: DataScope) -> str:
    """Derive a stable binding ID from a control-event kind and canonical scope."""
    if event_kind not in ("quality_update", "gap_start", "gap_end"):
        raise ValueError("unsupported control event kind")
    if not isinstance(scope, DataScope):
        raise TypeError("control event scope must be a DataScope")
    return _content_id(
        {
            "event_kind": event_kind,
            "kind": "control-binding-id/v1",
            "scope": scope.canonical_projection(),
        }
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class TransactionEvent:
    event_id: str
    timestamp_ns: TimestampNs
    source_id: str
    transaction_id: str
    transaction_sequence: int
    item_index: int
    provenance_ref: str

    def __post_init__(self) -> None:
        require_content_hash(self.event_id, name="event_id")
        timestamp_ns(self.timestamp_ns)
        _require_text(self.source_id, name="source_id")
        require_content_hash(self.transaction_id, name="transaction_id")
        _require_non_negative_int(self.transaction_sequence, name="transaction_sequence")
        _require_non_negative_int(self.item_index, name="item_index")
        _require_text(self.provenance_ref, name="provenance_ref")

    @property
    def ordering_key(self) -> EventOrderingKey:
        return EventOrderingKey(
            self.timestamp_ns,
            self.source_id,
            self.transaction_sequence,
            self.item_index,
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class SignalUpdate(TransactionEvent):
    kind: Literal["signal_update"] = field(default="signal_update", init=False)
    source_key: str
    value: ScalarValue | None
    value_type: ValueType
    unit_id: str
    quality: Quality

    def __post_init__(self) -> None:
        TransactionEvent.__post_init__(self)
        _require_text(self.source_key, name="source_key")
        _require_text(self.unit_id, name="unit_id")
        TypedValue(value=self.value, value_type=self.value_type, quality=self.quality)

    @classmethod
    def from_raw(
        cls,
        *,
        input_artifact_hash: str,
        timestamp: TimestampNs,
        source_id: str,
        transaction_sequence: int,
        item_index: int,
        binding_id: str,
        source_key: str,
        value: ScalarValue | None,
        value_type: ValueType | None = None,
        unit_id: str,
        quality: Quality = Quality.GOOD,
        provenance_ref: str,
    ) -> SignalUpdate:
        return TransactionItemFactory(
            input_artifact_hash=input_artifact_hash,
            timestamp=timestamp,
            source_id=source_id,
            transaction_sequence=transaction_sequence,
            provenance_ref=provenance_ref,
        ).signal_update(
            item_index=item_index,
            binding_id=binding_id,
            source_key=source_key,
            value=value,
            value_type=value_type,
            unit_id=unit_id,
            quality=quality,
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class QualityUpdate(TransactionEvent):
    kind: Literal["quality_update"] = field(default="quality_update", init=False)
    scope: DataScope
    quality: Quality
    reason: Reason

    def __post_init__(self) -> None:
        TransactionEvent.__post_init__(self)
        if not isinstance(self.scope, DataScope):
            raise TypeError("quality update scope must be a DataScope")
        if not isinstance(self.quality, Quality):
            raise TypeError("quality update quality must be a Quality")
        if not isinstance(self.reason, Reason):
            raise TypeError("quality update reason must be a Reason")
        expected_reason = {
            Quality.MISSING: ReasonCode.DATA_MISSING,
            Quality.STALE: ReasonCode.DATA_STALE,
            Quality.INVALID: ReasonCode.INVALID_VALUE,
            Quality.DECODE_ERROR: ReasonCode.DECODE_ERROR,
            Quality.OUT_OF_RANGE: ReasonCode.OUT_OF_RANGE,
            Quality.UNAVAILABLE: ReasonCode.MULTIPLEX_INACTIVE,
        }.get(self.quality)
        if expected_reason is None:
            raise ValueError("GOOD quality must be restored by a SignalUpdate or GapEnd")
        if self.reason.code is not expected_reason:
            raise ValueError("quality and reason code are inconsistent")


@dataclass(frozen=True, slots=True, kw_only=True)
class GapStart(TransactionEvent):
    kind: Literal["gap_start"] = field(default="gap_start", init=False)
    scope: DataScope
    reason: Reason

    def __post_init__(self) -> None:
        TransactionEvent.__post_init__(self)
        if not isinstance(self.scope, DataScope):
            raise TypeError("gap start scope must be a DataScope")
        if not isinstance(self.reason, Reason):
            raise TypeError("gap start reason must be a Reason")
        if self.reason.code is not ReasonCode.DATA_GAP:
            raise ValueError("gap start reason must be DATA_GAP")


@dataclass(frozen=True, slots=True, kw_only=True)
class GapEnd(TransactionEvent):
    kind: Literal["gap_end"] = field(default="gap_end", init=False)
    scope: DataScope

    def __post_init__(self) -> None:
        TransactionEvent.__post_init__(self)
        if not isinstance(self.scope, DataScope):
            raise TypeError("gap end scope must be a DataScope")


@dataclass(frozen=True, slots=True, kw_only=True)
class TransactionItemFactory:
    """Official deterministic construction path for every transaction item."""

    input_artifact_hash: str
    timestamp: TimestampNs
    source_id: str
    transaction_sequence: int
    provenance_ref: str

    def __post_init__(self) -> None:
        transaction_id(
            input_artifact_hash=self.input_artifact_hash,
            source_id=self.source_id,
            timestamp=self.timestamp,
            transaction_sequence=self.transaction_sequence,
        )
        _require_text(self.provenance_ref, name="provenance_ref")

    @property
    def derived_transaction_id(self) -> str:
        return transaction_id(
            input_artifact_hash=self.input_artifact_hash,
            source_id=self.source_id,
            timestamp=self.timestamp,
            transaction_sequence=self.transaction_sequence,
        )

    def _event_id(self, *, item_index: int, binding_id: str) -> str:
        return event_id(
            input_artifact_hash=self.input_artifact_hash,
            source_id=self.source_id,
            timestamp=self.timestamp,
            transaction_sequence=self.transaction_sequence,
            item_index=item_index,
            binding_id=binding_id,
        )

    def signal_update(
        self,
        *,
        item_index: int,
        binding_id: str,
        source_key: str,
        value: ScalarValue | None,
        value_type: ValueType | None = None,
        unit_id: str,
        quality: Quality = Quality.GOOD,
    ) -> SignalUpdate:
        normalized = TypedValue.from_raw(value, value_type=value_type, quality=quality)
        return SignalUpdate(
            event_id=self._event_id(item_index=item_index, binding_id=binding_id),
            timestamp_ns=self.timestamp,
            source_id=self.source_id,
            transaction_id=self.derived_transaction_id,
            transaction_sequence=self.transaction_sequence,
            item_index=item_index,
            provenance_ref=self.provenance_ref,
            source_key=source_key,
            value=normalized.value,
            value_type=normalized.value_type,
            unit_id=unit_id,
            quality=normalized.quality,
        )

    def quality_update(
        self,
        *,
        item_index: int,
        scope: DataScope,
        quality: Quality,
        reason: Reason,
    ) -> QualityUpdate:
        binding_id = control_binding_id(event_kind="quality_update", scope=scope)
        return QualityUpdate(
            event_id=self._event_id(item_index=item_index, binding_id=binding_id),
            timestamp_ns=self.timestamp,
            source_id=self.source_id,
            transaction_id=self.derived_transaction_id,
            transaction_sequence=self.transaction_sequence,
            item_index=item_index,
            provenance_ref=self.provenance_ref,
            scope=scope,
            quality=quality,
            reason=reason,
        )

    def gap_start(
        self,
        *,
        item_index: int,
        scope: DataScope,
        reason: Reason,
    ) -> GapStart:
        binding_id = control_binding_id(event_kind="gap_start", scope=scope)
        return GapStart(
            event_id=self._event_id(item_index=item_index, binding_id=binding_id),
            timestamp_ns=self.timestamp,
            source_id=self.source_id,
            transaction_id=self.derived_transaction_id,
            transaction_sequence=self.transaction_sequence,
            item_index=item_index,
            provenance_ref=self.provenance_ref,
            scope=scope,
            reason=reason,
        )

    def gap_end(self, *, item_index: int, scope: DataScope) -> GapEnd:
        binding_id = control_binding_id(event_kind="gap_end", scope=scope)
        return GapEnd(
            event_id=self._event_id(item_index=item_index, binding_id=binding_id),
            timestamp_ns=self.timestamp,
            source_id=self.source_id,
            transaction_id=self.derived_transaction_id,
            transaction_sequence=self.transaction_sequence,
            item_index=item_index,
            provenance_ref=self.provenance_ref,
            scope=scope,
        )


type TransactionItem = SignalUpdate | QualityUpdate | GapStart | GapEnd


@dataclass(frozen=True, slots=True)
class NormalizedTransaction:
    timestamp_ns: TimestampNs
    source_id: str
    transaction_id: str
    transaction_sequence: int
    items: tuple[TransactionItem, ...]
    kind: Literal["transaction"] = field(default="transaction", init=False)

    def __post_init__(self) -> None:
        timestamp_ns(self.timestamp_ns)
        _require_text(self.source_id, name="source_id")
        require_content_hash(self.transaction_id, name="transaction_id")
        _require_non_negative_int(self.transaction_sequence, name="transaction_sequence")
        if not isinstance(self.items, tuple):
            raise TypeError("normalized transaction items must be a tuple")
        if not self.items:
            raise ValueError("normalized transaction must contain at least one item")
        if any(
            not isinstance(item, (SignalUpdate, QualityUpdate, GapStart, GapEnd))
            for item in self.items
        ):
            raise TypeError("normalized transaction contains an unsupported item")
        for item in self.items:
            expected = (
                self.timestamp_ns,
                self.source_id,
                self.transaction_id,
                self.transaction_sequence,
            )
            actual = (
                item.timestamp_ns,
                item.source_id,
                item.transaction_id,
                item.transaction_sequence,
            )
            if actual != expected:
                raise ValueError("transaction item envelope does not match its transaction")
        item_indexes = tuple(item.item_index for item in self.items)
        if len(item_indexes) != len(set(item_indexes)):
            raise ValueError("transaction item_index values must be unique")
        if item_indexes != tuple(sorted(item_indexes)):
            raise ValueError("transaction items must use deterministic item_index order")

        gap_items = tuple(item for item in self.items if isinstance(item, (GapStart, GapEnd)))
        if gap_items and len(self.items) != 1:
            raise ValueError("gap events must be the only item in their transaction")
        broad_quality_items = tuple(
            item
            for item in self.items
            if isinstance(item, QualityUpdate) and not item.scope.source_keys
        )
        if broad_quality_items and len(self.items) != 1:
            raise ValueError(
                "whole-input and channel quality updates must use a control transaction"
            )

        updated_source_keys: set[str] = set()
        for item in self.items:
            item_source_keys: tuple[str, ...] = ()
            if isinstance(item, SignalUpdate):
                item_source_keys = (item.source_key,)
            elif isinstance(item, QualityUpdate):
                item_source_keys = item.scope.source_keys
            if updated_source_keys.intersection(item_source_keys):
                raise ValueError("a transaction cannot assign a source_key more than once")
            updated_source_keys.update(item_source_keys)

    @property
    def ordering_key(self) -> TransactionOrderingKey:
        return TransactionOrderingKey(
            self.timestamp_ns,
            self.source_id,
            self.transaction_sequence,
        )


@dataclass(frozen=True, slots=True)
class Watermark:
    timestamp_ns: TimestampNs
    kind: Literal["watermark"] = field(default="watermark", init=False)

    def __post_init__(self) -> None:
        timestamp_ns(self.timestamp_ns)


@dataclass(frozen=True, slots=True)
class EndOfStream:
    timestamp_ns: TimestampNs
    reason: str
    kind: Literal["end_of_stream"] = field(default="end_of_stream", init=False)

    def __post_init__(self) -> None:
        timestamp_ns(self.timestamp_ns)
        _require_text(self.reason, name="reason")


type NormalizedStreamEvent = NormalizedTransaction | Watermark | EndOfStream
