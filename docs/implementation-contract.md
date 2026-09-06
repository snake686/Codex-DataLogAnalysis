# MVP 实现契约

状态：实现前基线  
适用版本：Rule Schema `1.0`、Semantic Profile `core-temporal/1.0`

本文档把架构设计收敛为可直接编码的最小契约。若与其他文档冲突，时间行为以 `time-semantics.md` 为准，持久化结构以 `rule-schema.md` 为准；冲突本身必须先修正文档，不能由实现自行选择。

## 1. MVP 边界

MVP 支持：

- 每个 Analysis Session 一份 BLF 或 ASC Input、一组 DBC、一个 Rule Set；
- 多个 Session 作为 Batch 独立执行，不拼接 Timeline；
- Signal、Constant、GT/LT/EQ、AND/OR/NOT、RisingEdge、FallingEdge、ForAtLeast、Within、AtEvent、AssertNever 与 Expectation；
- Chunked Selective Decode、JSON Result、简单 HTML Report 和 CLI；
- Offline Strict-order Event，Late Data/Retraction 不在 MVP 内。

MVP 不支持 General Cycle、Variable Mutation、Arbitrary Custom Function、Unbounded Temporal Operator、Interpolation、Cross-rule State Sharing、Multi-log Time Merge 或 Dynamic Plugin Discovery。

## 2. Analysis Session

一个 Session 具有稳定 `session_id`，由 Input Artifact Hash、DBC Set Hash、Rule Set Execution Semantic Hash 和影响语义的 Analysis Configuration Hash 确定性派生。Path、Report Theme 等非语义字段不进入该 ID。

Session Timeline：

- Origin 为 Source Recording 的最早有效 Monotonic Timestamp；Runtime 可以保留 Absolute Source Time，但 Result 默认同时提供 `timestamp_ns` 和相对 `offset_ns`；
- Input Adapter 必须发出全序 Event 和 Final Watermark；
- Session 不跨文件延续 Held Value、Edge Baseline 或 Active Instance；
- 用户取消运行时，未完成 Instance 为 UNKNOWN/CANCELLED，不得当作 FAIL。

## 3. 中立 Ingestion Model

### RawFrame

Infrastructure 内部、但不依赖第三方库的不可变 Model：

```python
@dataclass(frozen=True, slots=True)
class RawFrame:
    timestamp_ns: int
    source_id: str
    frame_sequence: int
    channel: str
    arbitration_id: int
    is_extended_id: bool
    frame_kind: Literal["can", "can_fd"]
    dlc: int
    data: bytes
    direction: Literal["rx", "tx", "unknown"]
    is_error_frame: bool
    is_remote_frame: bool
    bitrate_switch: bool
    error_state_indicator: bool
    provenance_ref: str
```

`arbitration_id` 必须通过范围检查：Standard ID 为 0..0x7FF，Extended ID 为 0..0x1FFFFFFF。Classic CAN 与 CAN FD 的 DLC/Data Length 组合必须验证。Adapter 不得把 `python-can.Message` 存入 Provenance。

### Normalized Event

Core Runtime 接受以下 Discriminated Union：

- `SignalUpdate(event_id, timestamp_ns, source_id, transaction_id, transaction_sequence, item_index, source_key, value, value_type, unit_id, quality, provenance_ref)`；
- `QualityUpdate(..., source_key/scope, quality, reason_code)`；
- `GapStart(..., scope, reason_code)`；
- `GapEnd(..., scope)`；
- `Watermark(timestamp_ns)`；
- `EndOfStream(timestamp_ns, reason)`。

Value 仅允许 `bool | int | float | str` 以及带 Enum Domain ID 的 Scalar。Python 中 `bool` 是 `int` 子类，Validator/Decoder 必须先检查 Bool，禁止误归类为 Int。NaN/Infinity 默认映射为 `quality=INVALID`；除非未来 Block 明确支持，否则不得作为 Good Numeric Value。

一个 RawFrame 解码得到一个 Normalized Transaction，其中全部 SignalUpdate 原子生效。`transaction_sequence` 来自 `frame_sequence`，不能随 Selective Decode 的 Signal 数量改变；`item_index` 按 DBC 中稳定 Signal Order 分配。`source_id` 表示输入事件生产者/Artifact，不等于 CAN Channel，Channel 是独立字段。Synthetic/CSV Adapter 也必须明确 Transaction Boundary。同一 Transaction 中同一 `source_key` 出现两次是 Adapter Error。

DBC 默认输出经过 Scale/Offset 的 Physical Value。Enum 使用 `EnumValue(code, label, domain_id)`，其中 Code 是语义 Identity，Label 用于展示。DBC Minimum/Maximum 默认只作为 Metadata，不自动把超界值判为 INVALID；只有 Analysis Policy 明确启用 Range Validation 时才产生 `OUT_OF_RANGE`。

Multiplexed Signal 只在其 Branch Active 时产生 Good SignalUpdate。当同一 Message 的 Selector 明确切换到其他 Branch 时，Decoder 必须为已订阅且变为 Inactive 的 Signal 产生 `QualityUpdate(UNAVAILABLE, MULTIPLEX_INACTIVE)`，使 Held Value 与 Edge Baseline 立即失效；下一次 Branch Active 的 Good Sample 重新建立状态。不得把未激活 Branch 的 Bit 当成数值 Decode，也不得为未订阅 Signal 批量制造事件。

Quality 初始集合：`GOOD`、`MISSING`、`STALE`、`INVALID`、`DECODE_ERROR`、`OUT_OF_RANGE`、`UNAVAILABLE`。Quality 与 Reason Code 分离，便于扩展原因而不改变 Truth Table。

### Timestamp Conversion

- ASC Decimal Timestamp 应使用 Decimal/整数分解转换，禁止先转 Binary Float；
- 第三方 API 只能提供 Float 时，Adapter 使用 `Decimal(str(value))` 或等价的一次性十进制转换，再按明确策略舍入到 ns；
- MVP 默认 Midpoint Policy 为 `ROUND_HALF_EVEN`；原单位、原始文本/值和舍入 Policy 进入 Manifest；
- Timestamp Overflow、Negative Duration 或 Global Out-of-order 是 Fatal Diagnostic。

## 4. Signal Catalog 与 Binding

Compiler 只依赖中立 `SignalCatalog` Protocol。每个 Catalog Entry 至少提供：

```text
logical/source key
channel
CAN ID + extended flag
message name
signal name
value type / enum domain
canonical unit ID + original unit text
multiplexing selector/value
optional declared cycle time
```

Binding 的唯一键必须足以区分不同 Channel、Standard/Extended ID 和 Multiplex Variant。按 Name 匹配出现多个候选时 Validation Error，不得选择第一个。

DBC Declared Cycle Time 只能作为建议值。Rule/Analysis Configuration 没有明确允许时，不得自动把它变成 `max_age`。若启用派生，Policy 和派生公式必须写入 Manifest，例如 `max_age = cycle_time * factor + jitter_budget`。

## 5. MVP Block 精确契约

所有 Block Type ID 和 Version 属于持久化契约。以下未列为 Optional 的 Parameter 必须显式出现，或拥有唯一、文档化且由 Compiler 物化的 Default。

### `core.source.signal` v1

- Input：无；Output：`value: ValueStream<T,U>`。
- Required Parameter：`reference`。
- Type/Unit 由 Signal Reference 与 Catalog Binding 共同解析；冲突为 Validation Error。
- Sampling Policy 属于 Signal Reference，不属于 Runtime Node 的隐藏状态。

### `core.source.parameter` v1

- Input：无；Output：`value: ValueStream<T,U>`，在 Session 内恒定。
- Required Parameter：`reference`。
- Analysis Override 必须通过原 Definition 的 Type/Range/Unit Validation。

### `core.value.constant` v1

- Input：无；Output：`value: ValueStream<T,U>`，在 Session 内恒定。
- Required Parameter：`value`、`value_type`；Numeric Constant 还必须声明 `unit`，使用 `none` 表示无量纲。
- Float 必须有限。Enum Constant 必须携带 Domain ID。

### `core.compare.gt` / `lt` / `eq` v1

- Input：`left`、`right: ValueStream<T,U>`；Output：`result: TruthStream`。
- `gt/lt` 只接受同 Dimension Numeric；`eq` 接受相同 Scalar Type/Enum Domain。
- Required Parameter：`clock = on_left_input | on_right_input | on_any_input | strict_same_timestamp`。
- Operand Sampling/Freshness 来自 Source/Expression Metadata；任一不可用则 UNKNOWN。
- Float `eq` 使用 Python 有限数值的精确 Numeric Equality（因此 `-0.0 == 0.0`）；它不是带 Tolerance 的近似比较。Compiler 必须产生 `RULE_FLOAT_EXACT_EQUALITY` Warning。Approximate Comparison 不在 MVP。

### `core.logic.and` / `or` v1

- Input：Variadic `operands: TruthStream`，最少两个，使用连续 `slot=0..n-1`；Output：`result: TruthStream`。
- 按 Kleene Logic 求值。逻辑结果与 Operand 顺序无关，但 Slot 仍用于稳定 Hash/Diagnostic。
- Clock 为 `on_any_input`；每次 Operand Observation 后使用其他 Operand 的有效 Current Truth，Unavailable 为 UNKNOWN。

### `core.logic.not` v1

- Input：`operand: TruthStream`；Output：`result: TruthStream`。
- 使用规范三值 NOT，无 Parameter。

### `core.event.rising_edge` / `falling_edge` v1

- Input：`condition: TruthStream`；Output：`event: EventStream<EdgeEvidence>`。
- Required Parameter：`initialization`、`after_unknown`；MVP 支持 `require_baseline`/`assume_false|assume_true` 与 `require_rebaseline`。
- Gap、Stale 和 Invalid 使 Baseline 变为 UNKNOWN。Event Evidence 保存 Previous/Current Truth 与 Source Observation ID。

### `core.temporal.for_at_least` v1

- Input：`condition: TruthStream`；Output：`event: EventStream<DurationEvidence>`。
- Required Parameter：`duration`、`unknown=break`、`emit=once_per_true_interval`。
- `duration >= 0` 且必须可转换为 int64 ns。严格使用 `time-semantics.md` 的成熟 Phase。
- UI 可显示为 “Duration/持续至少”，但持久化 Type ID 不使用含糊的 `duration`。

### `core.temporal.within` v1

- Input：`trigger: EventStream<P>` 与以下二者之一：`condition: TruthStream` 或 `target_event: EventStream<Q>`；Output：`evaluation: EvaluationStream`。
- Required Parameter：`duration`、`satisfaction=is_true|becomes_true|event`、`lower_bound=open|closed`、`upper_bound=open|closed`、`overlap=independent`、`incomplete_status=unknown`。
- `becomes_true` 只允许 Truth Input，并 Lower 为带 `require_baseline` 的 RisingEdge；`event` 只允许 Event Input；`is_true` 只允许 Truth Input。
- `duration >= 0`。若 Duration 为零且任一 Bound Open，Window 为空，Validation Error。
- MVP 不提供 Target Consumption；一个 Target 可以满足所有包含它的 Independent Instance。

### `core.temporal.at_event` v1

- Input：`trigger: EventStream<P>`、`condition: TruthStream`；Output：`evaluation: EvaluationStream`。
- 在完整 Trigger Timestamp Batch 上读取对齐后的 Condition State。TRUE -> PASS，FALSE -> FAIL，UNKNOWN/Unavailable -> UNKNOWN。
- Required Parameter：`missing_status=unknown`。MVP 禁止配置 Missing -> PASS/FAIL。

### `core.result.assert_never` v1

- Input：`condition: TruthStream`；Output：无，Terminal Result Node。
- Required Parameter：`scope_semantics=observed_samples|continuous`、`true_status=fail`、`false_status=pass`、`unknown_status=unknown`、`message`。
- `observed_samples` 只评价有效 Observation；`continuous` 需要完整 Coverage，否则整体 UNKNOWN。

### `core.result.expectation` v1

- Input：`evaluation: EvaluationStream`；Output：无，Terminal Result Node。
- 显式映射 Satisfied/Violated/Timeout/Indeterminate/Error 到 Result Status。MVP 固定 Indeterminate -> UNKNOWN、Error -> ERROR，不允许映射成 PASS。
- Message 是 User-facing Template；Evidence/Reason 使用结构化字段，不从 Message 反向解析。

### Pass/Fail UI Block

MVP 不保存独立的 `core.result.pass` 或 `core.result.fail` Runtime Node。GUI 中的 Pass/Fail Block 是 Assertion/Expectation Outcome Mapping 的展示形式。这样可以避免“输入 TRUE 到底表示 PASS 还是触发 FAIL”的极性歧义。若未来需要独立 Sink，必须新增 Type ID 与 ADR。

## 6. Graph 与 Compiler Contract

- 每个 Rule 恰好一个 Terminal Result Node；所有 Semantic Node 必须位于通向该 Node 的 DAG 中。
- Edge 的 Source/Target Port 必须存在；非 Variadic Input 恰好连接一次；Optional Input 最多一次；Variadic Slot 连续且不重复。
- Compiler 只接受 Validation Success Object，普通 RuleDefinition 不能绕过 Validator 直接编译。
- IR Operator ID 由 Node ID 和 Lowering Suffix 确定性生成，例如 `response$target_edge`；不得使用运行时地址或随机数。
- Constant Fold、Dead Node Elimination 不得丢失 Source Map；任何 Diagnostic 都能回指 Rule/Node/Port。
- IR 只在同一 Engine Build 内使用。Debug Serialization 必须带 `ir_format_version` 和 Engine Version，并标注为非持久化接口。

## 7. Runtime State 与 Deadline

- Scheduler 当前处理时间和 Watermark 单调不减。
- Runtime Datum 必须区分 `last_observation` 与 `current_state_coverage`。`observe_only` 的上一条 Observation 可供 Edge Detector 与下一条 Observation 比较，但不能证明中间时段的 State；显式 Gap 会使 Edge Baseline 失效。
- Value/Truth State 至少记录 `observed_at_ns`、`valid_through_ns | session_invariant`、Quality 和 Provenance。Hold-last 在 `valid_through_ns` 端点仍有效；Constant/Parameter 标记为 Session-invariant，不使用伪造的 int64 最大时间。
- Freshness Expiry 即使没有新 Input 也必须触发 Derived UNKNOWN/State Recompute，使 ForAtLeast 等 Stateful Operator 能及时中断。Pure Comparison 的 Coverage 是所需 Operand Coverage 的交集；Boolean Logic 按 Kleene Dominating Value 计算结论，并在任一相关 Operand Expiry 时重新求值。
- Deadline Queue Entry 至少包含 Timestamp、Phase、Rule/Operator ID、Evaluation ID/State Key 和 Generation。Generation 防止 Restart/Cancel 后的旧 Timer 生效。
- Zero-duration Derived-timer Queue 按 IR Topology 与 Stable Occurrence ID 排序后排空；DAG 保证不会形成无限 Zero-time Feedback，Per-timestamp Resource Limit 仍必须生效。
- Stateful Operator State 使用明确 Dataclass/Tagged Union，不将任意 Dict 作为长期 State。
- Chunk 不得在同一 Timestamp 或 Transaction 中间结束；Reader 若无法保证，应由 Application 增加 Timestamp Lookahead。
- Deadline 复杂度目标为 O(log n) Insert/Remove 或摊销 O(1) Timing Wheel；MVP 优先使用 Heap，并通过 Benchmark 再决定优化。
- 达到 `max_active_instances_per_rule` 时，不创建缺失的 Instance；Rule 与 Run 产生 ERROR/RESOURCE_LIMIT，并记录被拒 Trigger Evidence。不得淘汰最旧 Instance 后继续。

## 8. Result 与 Reason Code

MVP Status：`PASS`、`FAIL`、`UNKNOWN`、`ERROR`、`NOT_EVALUATED`、`INVALID`、`SKIPPED`。

Python Domain Model 内部的 TimePoint/Duration 是 `int`，但公共 JSON Result/Manifest 将所有 `*_ns` 字段编码为十进制 String，并由 JSON Schema 使用 `pattern: '^-?(0|[1-9][0-9]*)$'` 约束。这样浏览器、JavaScript Report 和其他语言不会丢失 int64 精度。YAML Rule Authoring 仍使用 `500 ms` 等带单位文本。

初始稳定 Reason Code：

```text
SATISFIED
CONDITION_VIOLATED
TIMEOUT
DATA_MISSING
DATA_STALE
DATA_GAP
INCOMPLETE_WINDOW
NO_TRIGGER
RULE_INVALID
DECODE_ERROR
OUT_OF_ORDER
RESOURCE_LIMIT
CANCELLED
INTERNAL_ERROR
```

Reason Code 采用只增不改原则；显示文本可本地化。Result Schema 中不得只保存自由文本原因。

`RuleResult` 必须包含 Rule ID/Version/Semantic Hash、Overall Status、每类计数、Evaluation Result/Summary、Diagnostic 与 Manifest Reference。完整 Evaluation 数量过大时允许外部流式写出或分页，但 Summary Count 必须精确，且不能因 Report Limit 改变 Overall Status。

## 9. Canonicalization、Hash 与稳定 ID

所有 Content-derived ID 使用 `sha256:<64 lowercase hex>`。Hash Input 是 UTF-8 编码的 RFC 8785 JSON Canonicalization Scheme（JCS）Document。进入 JCS 前先经过 Typed Model Normalization：Duration/TimePoint 转为十进制整数字符串形式的 ns、Unit 转为 Canonical ID、Enum 使用 Code/Domain、String 保持原 Unicode Code Point（不做隐式大小写或 Unicode Normalization）。这样避免 JCS/JavaScript Number 无法精确表示完整 int64。Int Scalar 也使用带 Type Tag 的十进制字符串；Float 仅允许有限 IEEE-754 Binary64，并按 JCS Number 规则编码。

必须区分四种 Hash：

- **Artifact Hash：** 原始文件 Byte 的 SHA-256，用于证明输入文件完全相同；
- **Definition Hash：** 完整 Typed Rule Model 的 JCS Hash，包括用户可见 Metadata，但不包括 Loader 内部字段；
- **Rule Semantic Definition Hash：** 只包含 Graph、Parameter Definition/Default、Signal Reference、Definition-level Semantic Policy、Block Version 和 Semantic Profile；排除 `presentation`、Name、Description、Localized Message、文件路径和本次运行 Override。
- **Execution Semantic Hash：** 在 Rule Semantic Definition Projection 基础上加入 Effective Parameter Value、Resolved Binding Type/Unit、Effective Sampling/Gap/Aggregation Policy，以及所有影响结果的 Analysis Option。它标识真正执行的语义计划，用于 Evaluation ID 与 Result Cache。

稳定 ID Payload 使用带 Version 的 JSON Object，不使用字符串拼接：

```json
{"kind":"transaction-id/v1","input_artifact_hash":"sha256:...","source_id":"...","timestamp_ns":"123","transaction_sequence":"7"}
{"kind":"event-id/v1","input_artifact_hash":"sha256:...","source_id":"...","timestamp_ns":"123","transaction_sequence":"7","item_index":"2","binding_id":"..."}
{"kind":"evaluation-id/v1","execution_semantic_hash":"sha256:...","expectation_node_id":"response","trigger_event_id":"sha256:...","instance_key":null,"occurrence_index":"0"}
{"kind":"session-id/v1","input_artifact_hash":"sha256:...","dbc_set_hash":"sha256:...","ruleset_execution_hash":"sha256:...","semantic_config_hash":"sha256:..."}
```

Hash Algorithm、Payload Field 和 Canonicalization 发生变化时必须增加 `kind` Version，不能静默替换。Golden Test 必须固定至少一个完整向量。

## 10. 初始 Diagnostic Code Namespace

```text
SCHEMA_*       文件结构、版本、字段
GRAPH_*        Node/Edge/Port/Cycle/Reachability
BLOCK_*        Type/Version/Parameter
TYPE_*         Port 与 Scalar Type
UNIT_*         Dimension 与 Conversion
BINDING_*      Signal Catalog Resolution
TEMPORAL_*     Duration、Boundary、Coverage、Nesting
RUNTIME_*      Ordering、State、Internal Error
RESOURCE_*     Capacity Limit
ADAPTER_*      Parse/Decode/Timestamp
```

Diagnostic Code 一旦出现在用户 Result/Golden 中即视为兼容契约。Code 与结构化 Location 稳定，Message 可改进或本地化。

## 11. 实现就绪条件

开始 Task 2 业务编码前应满足：

- 本文档与三个 Example 的 Port Type/参数一致；
- `time-semantics.md` 的 Phase、Boundary、Gap、Freshness 通过 Table-driven Test Case 固化；
- Python 3.12 和 3.13 均进入 CI Matrix；
- Schema Model、Core Model、IR Model、Runtime State 的 Package Import Boundary 有自动检查；
- 第一批 Stable Diagnostic/Reason Code 以 Enum 或常量集中定义；
- JCS/SHA-256 的 Artifact、Definition、Semantic Hash 和稳定 ID Test Vector 已固定；
- 所有无法执行的语义都在 Validator 阶段拒绝，不把模糊配置推迟到 Runtime 猜测。
