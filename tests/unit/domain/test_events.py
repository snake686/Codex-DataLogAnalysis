"""Tests for deterministic normalized events and transactions."""

from dataclasses import FrozenInstanceError, asdict, replace
from typing import Any, cast

import pytest

from app_dataloganalysis.domain.events import (
    DataScope,
    EndOfStream,
    EventOrderingKey,
    NormalizedStreamEvent,
    NormalizedTransaction,
    SignalUpdate,
    TransactionItemFactory,
    TransactionOrderingKey,
    Watermark,
    control_binding_id,
    event_id,
    transaction_id,
)
from app_dataloganalysis.domain.time import INT64_MAX, TimeValueError, timestamp_ns
from app_dataloganalysis.domain.values import Quality, Reason, ReasonCode, ValueType

ARTIFACT_HASH = "sha256:" + "a" * 64
EVENT_HASH = "sha256:" + "b" * 64
TRANSACTION_HASH = "sha256:" + "c" * 64


def make_signal(
    *,
    timestamp: int = 123,
    source_id: str = "source-A",
    sequence: int = 7,
    item_index: int = 2,
    source_key: str = "vehicle.signal",
    value: int = 42,
) -> SignalUpdate:
    return SignalUpdate.from_raw(
        input_artifact_hash=ARTIFACT_HASH,
        timestamp=timestamp_ns(timestamp),
        source_id=source_id,
        transaction_sequence=sequence,
        item_index=item_index,
        binding_id=source_key,
        source_key=source_key,
        value=value,
        unit_id="unit:none",
        provenance_ref="frame:7",
    )


def make_factory() -> TransactionItemFactory:
    return TransactionItemFactory(
        input_artifact_hash=ARTIFACT_HASH,
        timestamp=timestamp_ns(123),
        source_id="source-A",
        transaction_sequence=7,
        provenance_ref="frame:7",
    )


def test_stable_identity_vectors_match_the_normative_payload() -> None:
    derived_transaction = transaction_id(
        input_artifact_hash=ARTIFACT_HASH,
        source_id="source-A",
        timestamp=timestamp_ns(123),
        transaction_sequence=7,
    )
    derived_event = event_id(
        input_artifact_hash=ARTIFACT_HASH,
        source_id="source-A",
        timestamp=timestamp_ns(123),
        transaction_sequence=7,
        item_index=2,
        binding_id="vehicle.signal",
    )
    assert derived_transaction == (
        "sha256:817cc1f7bfe85d92ca68db332276e5461543f29b41bd66670d4bea04c277f1f1"
    )
    assert derived_event == (
        "sha256:79feb1ce1dc1884674296872d0b64f91efc7907479558f6996864dbb58ae6d71"
    )


@pytest.mark.parametrize(
    ("function", "arguments", "error"),
    [
        (transaction_id, {"source_id": ""}, ValueError),
        (transaction_id, {"source_id": 1}, TypeError),
        (transaction_id, {"transaction_sequence": -1}, ValueError),
        (transaction_id, {"transaction_sequence": True}, TypeError),
        (event_id, {"binding_id": ""}, ValueError),
        (event_id, {"item_index": -1}, ValueError),
        (event_id, {"item_index": True}, TypeError),
    ],
)
def test_identity_inputs_are_validated(
    function: Any, arguments: dict[str, object], error: type[Exception]
) -> None:
    base: dict[str, Any] = {
        "input_artifact_hash": ARTIFACT_HASH,
        "source_id": "source-A",
        "timestamp": timestamp_ns(123),
        "transaction_sequence": 7,
    }
    if function is event_id:
        base.update(item_index=2, binding_id="vehicle.signal")
    base.update(arguments)
    with pytest.raises(error):
        function(**base)


def test_ordering_keys_define_total_deterministic_order() -> None:
    transaction_keys = [
        TransactionOrderingKey(timestamp_ns(2), "a", 0),
        TransactionOrderingKey(timestamp_ns(1), "z", 0),
        TransactionOrderingKey(timestamp_ns(1), "a", 1),
        TransactionOrderingKey(timestamp_ns(1), "a", 0),
    ]
    assert sorted(transaction_keys) == [
        TransactionOrderingKey(timestamp_ns(1), "a", 0),
        TransactionOrderingKey(timestamp_ns(1), "a", 1),
        TransactionOrderingKey(timestamp_ns(1), "z", 0),
        TransactionOrderingKey(timestamp_ns(2), "a", 0),
    ]
    assert EventOrderingKey(timestamp_ns(1), "a", 0, 0) < EventOrderingKey(
        timestamp_ns(1), "a", 0, 1
    )

    with pytest.raises(ValueError, match="source_id"):
        TransactionOrderingKey(timestamp_ns(1), "", 0)
    with pytest.raises(ValueError, match="non-negative"):
        EventOrderingKey(timestamp_ns(1), "a", 0, -1)


def test_data_scope_is_explicit_and_canonical() -> None:
    assert DataScope(whole_input=True).whole_input
    assert DataScope(channel="can0").channel == "can0"
    assert DataScope.for_source_keys("z", "a").source_keys == ("a", "z")

    with pytest.raises(TypeError, match="whole_input"):
        DataScope(whole_input=cast(Any, 1))
    with pytest.raises(TypeError, match="must be a tuple"):
        DataScope(source_keys=cast(Any, ["a"]))
    with pytest.raises(ValueError, match="exactly one"):
        DataScope()
    with pytest.raises(ValueError, match="exactly one"):
        DataScope(whole_input=True, channel="can0")
    with pytest.raises(TypeError, match="channel"):
        DataScope(channel=cast(Any, 1))
    with pytest.raises(ValueError, match="channel"):
        DataScope(channel="")
    with pytest.raises(TypeError, match="source keys"):
        DataScope(source_keys=cast(Any, (1,)))
    with pytest.raises(ValueError, match="must not be empty"):
        DataScope(source_keys=("",))
    with pytest.raises(ValueError, match="unique"):
        DataScope(source_keys=("a", "a"))
    with pytest.raises(ValueError, match="deterministic"):
        DataScope(source_keys=("z", "a"))


def test_control_binding_identity_uses_kind_and_canonical_scope() -> None:
    whole = DataScope(whole_input=True)
    channel = DataScope(channel="can0")
    keys = DataScope.for_source_keys("z", "a")

    assert whole.canonical_projection() == {"kind": "whole_input"}
    assert channel.canonical_projection() == {"channel": "can0", "kind": "channel"}
    assert keys.canonical_projection() == {"kind": "source_keys", "source_keys": ["a", "z"]}
    assert control_binding_id(event_kind="gap_start", scope=whole) == (
        "sha256:c55e535707ec5b703adf6a586afd33c0a8b36a98f9e116fc722cd28ee004e0e6"
    )
    with pytest.raises(ValueError, match="unsupported"):
        control_binding_id(event_kind=cast(Any, "signal_update"), scope=whole)
    with pytest.raises(TypeError, match="DataScope"):
        control_binding_id(event_kind="gap_end", scope=cast(Any, "all"))


def test_signal_update_is_normalized_flat_immutable_and_discriminated() -> None:
    signal = make_signal()
    assert signal.value == 42
    assert signal.value_type is ValueType.INT
    assert signal.quality is Quality.GOOD
    assert signal.ordering_key == EventOrderingKey(timestamp_ns(123), "source-A", 7, 2)
    assert asdict(signal)["kind"] == "signal_update"
    with pytest.raises(FrozenInstanceError):
        signal.value = 43  # type: ignore[misc]

    invalid = SignalUpdate.from_raw(
        input_artifact_hash=ARTIFACT_HASH,
        timestamp=timestamp_ns(1),
        source_id="source-A",
        transaction_sequence=0,
        item_index=0,
        binding_id="vehicle.signal",
        source_key="vehicle.signal",
        value=float("nan"),
        unit_id="unit:none",
        provenance_ref="frame:1",
    )
    assert invalid.value is None
    assert invalid.quality is Quality.INVALID


def test_transaction_item_variants_share_a_validated_envelope() -> None:
    factory = make_factory()
    signal = factory.signal_update(
        item_index=0,
        binding_id="vehicle.signal",
        source_key="vehicle.signal",
        value=42,
        unit_id="unit:none",
    )
    quality = factory.quality_update(
        item_index=1,
        scope=DataScope.for_source_keys("vehicle.quality"),
        quality=Quality.MISSING,
        reason=Reason(ReasonCode.DATA_MISSING),
    )
    gap_start = factory.gap_start(
        item_index=2,
        scope=DataScope(whole_input=True),
        reason=Reason(ReasonCode.DATA_GAP),
    )
    gap_end = factory.gap_end(item_index=3, scope=DataScope(channel="can0"))

    assert [quality.kind, gap_start.kind, gap_end.kind] == [
        "quality_update",
        "gap_start",
        "gap_end",
    ]
    assert [signal.event_id, quality.event_id, gap_start.event_id, gap_end.event_id] == [
        "sha256:189991b2fa309dcc4e5a60b82f97c542a32d1acc41432af96deb2d2f38f5c2b2",
        "sha256:012f2a412d9f268d84f4d4d074ec2e2df8eea9a65e70bbfc32be362412223107",
        "sha256:031d7640b13e7888455ea2857c8b97b8c4c015df68abd1c48f9183967302a436",
        "sha256:c29239a563610346be9ede75bf9c752b86eb4f86a75a62cb8999e636f885532d",
    ]
    assert factory == make_factory()
    assert factory.derived_transaction_id == signal.transaction_id
    transaction = NormalizedTransaction(
        signal.timestamp_ns,
        signal.source_id,
        signal.transaction_id,
        signal.transaction_sequence,
        (signal, quality),
    )
    assert transaction.ordering_key == TransactionOrderingKey(timestamp_ns(123), "source-A", 7)
    assert asdict(transaction)["kind"] == "transaction"

    with pytest.raises(TypeError, match="quality update scope"):
        replace(quality, scope=cast(Any, "all"))
    with pytest.raises(TypeError, match="quality update quality"):
        replace(quality, quality=cast(Any, "missing"))
    with pytest.raises(TypeError, match="quality update reason"):
        replace(quality, reason=cast(Any, "gap"))
    with pytest.raises(TypeError, match="gap start scope"):
        replace(gap_start, scope=cast(Any, "all"))
    with pytest.raises(TypeError, match="gap start reason"):
        replace(gap_start, reason=cast(Any, "gap"))
    with pytest.raises(TypeError, match="gap end scope"):
        replace(gap_end, scope=cast(Any, "all"))


def test_transaction_rejects_empty_mismatched_and_duplicate_items() -> None:
    signal = make_signal(item_index=0)
    with pytest.raises(TypeError, match="must be a tuple"):
        NormalizedTransaction(
            signal.timestamp_ns,
            signal.source_id,
            signal.transaction_id,
            signal.transaction_sequence,
            cast(Any, [signal]),
        )
    with pytest.raises(ValueError, match="at least one"):
        NormalizedTransaction(timestamp_ns(1), "source-A", TRANSACTION_HASH, 0, ())
    with pytest.raises(TypeError, match="unsupported item"):
        NormalizedTransaction(
            signal.timestamp_ns,
            signal.source_id,
            signal.transaction_id,
            signal.transaction_sequence,
            cast(Any, ("signal",)),
        )
    with pytest.raises(ValueError, match="envelope"):
        NormalizedTransaction(
            timestamp_ns(124),
            signal.source_id,
            signal.transaction_id,
            signal.transaction_sequence,
            (signal,),
        )
    with pytest.raises(ValueError, match="item_index"):
        NormalizedTransaction(
            signal.timestamp_ns,
            signal.source_id,
            signal.transaction_id,
            signal.transaction_sequence,
            (signal, replace(signal, source_key="vehicle.other")),
        )
    with pytest.raises(ValueError, match="source_key"):
        NormalizedTransaction(
            signal.timestamp_ns,
            signal.source_id,
            signal.transaction_id,
            signal.transaction_sequence,
            (signal, replace(signal, item_index=1, event_id=EVENT_HASH)),
        )
    with pytest.raises(ValueError, match="deterministic item_index"):
        NormalizedTransaction(
            signal.timestamp_ns,
            signal.source_id,
            signal.transaction_id,
            signal.transaction_sequence,
            (
                replace(signal, item_index=1, event_id=EVENT_HASH),
                replace(signal, source_key="vehicle.other"),
            ),
        )


def test_transaction_rejects_ambiguous_final_source_state() -> None:
    factory = make_factory()
    signal = factory.signal_update(
        item_index=0,
        binding_id="vehicle.signal",
        source_key="vehicle.signal",
        value=42,
        unit_id="unit:none",
    )
    quality = factory.quality_update(
        item_index=1,
        scope=DataScope.for_source_keys("vehicle.signal"),
        quality=Quality.MISSING,
        reason=Reason(ReasonCode.DATA_MISSING),
    )
    broad_quality = factory.quality_update(
        item_index=1,
        scope=DataScope(channel="can0"),
        quality=Quality.MISSING,
        reason=Reason(ReasonCode.DATA_MISSING),
    )
    gap = factory.gap_start(
        item_index=1,
        scope=DataScope(whole_input=True),
        reason=Reason(ReasonCode.DATA_GAP),
    )
    quality_with_overlap = factory.quality_update(
        item_index=2,
        scope=DataScope.for_source_keys("vehicle.other", "vehicle.signal"),
        quality=Quality.STALE,
        reason=Reason(ReasonCode.DATA_STALE),
    )

    envelope = (
        signal.timestamp_ns,
        signal.source_id,
        signal.transaction_id,
        signal.transaction_sequence,
    )
    with pytest.raises(ValueError, match="assign a source_key"):
        NormalizedTransaction(*envelope, (signal, quality))
    with pytest.raises(ValueError, match="assign a source_key"):
        NormalizedTransaction(*envelope, (quality, quality_with_overlap))
    with pytest.raises(ValueError, match="control transaction"):
        NormalizedTransaction(*envelope, (signal, broad_quality))
    with pytest.raises(ValueError, match="only item"):
        NormalizedTransaction(*envelope, (signal, gap))

    assert NormalizedTransaction(*envelope, (broad_quality,)).items == (broad_quality,)
    assert NormalizedTransaction(*envelope, (gap,)).items == (gap,)


@pytest.mark.parametrize(
    ("quality", "reason_code"),
    [
        (Quality.MISSING, ReasonCode.DATA_MISSING),
        (Quality.STALE, ReasonCode.DATA_STALE),
        (Quality.INVALID, ReasonCode.INVALID_VALUE),
        (Quality.DECODE_ERROR, ReasonCode.DECODE_ERROR),
        (Quality.OUT_OF_RANGE, ReasonCode.OUT_OF_RANGE),
        (Quality.UNAVAILABLE, ReasonCode.MULTIPLEX_INACTIVE),
    ],
)
def test_quality_update_requires_a_semantically_matching_reason(
    quality: Quality, reason_code: ReasonCode
) -> None:
    factory = make_factory()
    update = factory.quality_update(
        item_index=0,
        scope=DataScope.for_source_keys("vehicle.signal"),
        quality=quality,
        reason=Reason(reason_code),
    )
    assert update.quality is quality

    with pytest.raises(ValueError, match="inconsistent"):
        replace(update, reason=Reason(ReasonCode.DATA_GAP))


def test_good_quality_and_non_gap_reason_require_unambiguous_event_kinds() -> None:
    factory = make_factory()
    with pytest.raises(ValueError, match="restored"):
        factory.quality_update(
            item_index=0,
            scope=DataScope.for_source_keys("vehicle.signal"),
            quality=Quality.GOOD,
            reason=Reason(ReasonCode.SATISFIED),
        )
    with pytest.raises(ValueError, match="DATA_GAP"):
        factory.gap_start(
            item_index=0,
            scope=DataScope(whole_input=True),
            reason=Reason(ReasonCode.DATA_MISSING),
        )


def test_stream_control_events_are_discriminated_and_validated() -> None:
    events: tuple[NormalizedStreamEvent, ...] = (
        Watermark(timestamp_ns(10)),
        EndOfStream(timestamp_ns(20), "input exhausted"),
    )
    assert [asdict(event)["kind"] for event in events] == ["watermark", "end_of_stream"]
    with pytest.raises(ValueError, match="reason"):
        EndOfStream(timestamp_ns(20), "")
    with pytest.raises(TypeError, match="timestamp_ns"):
        Watermark(cast(Any, True))


def test_event_envelope_and_signal_fields_are_validated() -> None:
    signal = make_signal()
    with pytest.raises(ValueError, match="event_id"):
        replace(signal, event_id="not-a-hash")
    with pytest.raises(ValueError, match="source_id"):
        replace(signal, source_id="")
    with pytest.raises(ValueError, match="transaction_id"):
        replace(signal, transaction_id="not-a-hash")
    with pytest.raises(ValueError, match="non-negative"):
        replace(signal, transaction_sequence=-1)
    with pytest.raises(ValueError, match="non-negative"):
        replace(signal, item_index=-1)
    with pytest.raises(ValueError, match="provenance_ref"):
        replace(signal, provenance_ref="")
    with pytest.raises(ValueError, match="source_key"):
        replace(signal, source_key="")
    with pytest.raises(ValueError, match="unit_id"):
        replace(signal, unit_id="")
    with pytest.raises(TypeError, match="unit_id"):
        replace(signal, unit_id=cast(Any, 1))
    with pytest.raises(TimeValueError, match="int64"):
        make_signal(timestamp=INT64_MAX + 1)
