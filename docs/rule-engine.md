# Rule Engine 架构

本文档定义 Rule 的逻辑编译与执行模型。时间 Operator 以 `time-semantics.md` 为规范，持久化格式以 `rule-schema.md` 为规范。

## 1. 端到端模型

```text
RuleDefinition
  -> Schema Load/Migration
  -> Structural/Semantic Validation
  -> Binding/Type/Unit Analysis
  -> Compiler/Lowering
  -> Immutable CompiledRule IR
  -> RuleRuntime + Normalized Event Stream
  -> EvaluationInstances
 -> RuleResult
```

以上各层都需要保留；Load/Migration 属于 Definition Boundary，而不是 Semantic Compiler。

编译单位是单个 Rule；Rule Set Compiler 只负责逐 Rule 编译并汇总 Source Subscription。MVP 不做跨 Rule Common-subexpression Sharing。每个 Input Recording 创建独立 Analysis Session；批量任务产生多个互不影响的 Session Result。

### 为什么需要 Compiler 与 IR

Authoring Graph 优先考虑可读性和持久化稳定性，Runtime Object 优先考虑确定执行和紧凑状态。Compiler 统一负责解析 Block Version 与 Signal Binding、推断和检查 Type/Unit、规范化 Default、拒绝歧义、折叠常量、计算 Subscription、生成 Topology/Schedule，并附加诊断 Source Map。

IR 将 Runtime 实现变化与保存文件隔离，也阻止 GUI Layout 进入执行语义。IR 不可变，可以输出 Debug Representation，但 MVP 不承诺把它作为长期兼容的存储格式。

Rule Definition、IR 与 Runtime Object 必须彻底分离。保存的 Definition 不得包含可变 Timer、Cached Sample、Python Callable Reference 或第三方库 Object。

## 2. Validation 阶段

Diagnostic 必须具有稳定 Code、Severity、Message、Rule/Node/Port Location 和建议修复方式。

1. **Schema：** 检查 Schema/Semantic Version、Required Field、Unique ID、Duration String 和 Parameter Shape。
2. **Graph：** 检查 Endpoint、Required Input Cardinality、Output Fan-out、Result/Assertion Reachability、Orphan Semantic Node 以及 MVP Cycle。
3. **Block Resolution：** `(type, version)` 必须存在，Parameter 必须有效。
4. **Type：** 检查 Port Compatibility、Generic Binding，以及 Value、Truth、Event 的区分。
5. **Binding：** Source Reference 必须能在 Data Catalog 中唯一解析，Unit/Value Type 必须一致。
6. **Temporal：** 检查 Interval Bound/Duration、Trigger/Target Mode、Unbounded Retention、Nesting 和 Completion Behavior。
7. **Policy：** Hold-last 必须有有限 Freshness；Aggregation、No-trigger、Resource Limit 必须有效。
8. **Reachability/Cost：** 对 Unused Node、Float Exact Equality、Duplicate Assertion、潜在 Instance Explosion 和高 Fan-out 给出 Warning。

Error 阻止编译。Warning 必须进入 Run Manifest 和 Result。

## 3. 强类型 Port System

初始 Type Lattice 应保持精简：

```text
Scalar = Bool | Int | Float | String | Enum<domain>
ValueStream<T, Unit>           # Unitless、Known Dimension 或 Unknown
TruthStream                    # TRUE | FALSE | UNKNOWN Observation
EventStream<TPayload>
Duration
Timestamp
EvaluationStream
```

`Number` 是 Compile-time Constraint，可由 Int 或 Float 满足，并非 Runtime Value。物理量由 Numeric Scalar 与 Compile-time Unit/Dimension 共同表示，不要求 Runtime 包装为特殊 Quantity Object。UI 中的 `Signal<float, degC>` 在 Binding 后对应 `ValueStream<Float, Temperature>`。Generic Inference 后，只有 Output Type 可赋给 Input Type 时 Edge 才合法。ValueStream、TruthStream 和 EventStream 之间不得隐式转换。

```text
GreaterThan<T:Number,U>: (left: ValueStream<T,U>, right: ValueStream<T,U>) -> TruthStream
RisingEdge:            (condition: TruthStream) -> EventStream<Edge>
Within:                (trigger: EventStream, condition: TruthStream) -> EvaluationStream
Max<T:Number>:         (values: ValueStream<T>...) -> ValueStream<T>
```

Compiler 将 Constant 提升为 Time-invariant ValueStream。即使 GUI 隐藏转换细节，允许的 Unit Conversion 也必须在 IR 中表现为显式 Operator。

## 4. Block 模型

### 分类方式

原始 UI Category 适合搜索，但不应决定执行方式。Block Library 应按输出流类型和语义职责组织：

1. **Source/Literal：** Signal、Parameter、Constant。Variable 在 Mutation/Scope 语义明确前暂不支持。
2. **Value Transform/Aggregate：** Arithmetic、ABS、MIN/MAX/AVG、Delta、Rate 和 Filter；输出 ValueStream，并声明 Clock/Alignment/Window Policy。
3. **Predicate：** Comparison 与 Boolean Logic；输出 TruthStream，必须显式处理 UNKNOWN。
4. **Event Detector：** RisingEdge、FallingEdge、Changed、EnterRange、ExitRange；把 Observation 变为离散 EventStream。
5. **Temporal Coordinator/Monitor：** ForAtLeast、Within、After、Before、Timeout、Until；它们是 Stateful，并输出 Event 或 EvaluationStream。
6. **Sequence/State Construct：** Then、Repeat、Optional、AnyOf/AllOf、State Transition；属于 Compiler Construct，Lower 为带 Key 的 Temporal State Machine，而不是任意 Graph Cycle。
7. **Assertion/Sink：** Expectation、AssertAlways/Never、Record、Metric。PASS/FAIL/Warning 是 Outcome Mapping/Severity，不是普通 Boolean Operator。

Statefulness、Purity、Retention Horizon 与 Trigger Cardinality 是跨 Category 的 Metadata 维度。例如 MovingAverage 属于 Value Transform，但仍是 Stateful。这种分类避免 UI Taxonomy 渗透 Scheduler。

### BlockDefinition

由 Library 所有的不可变 Metadata：

- 稳定 Type ID（如 `core.compare.gt`）和整数 Definition Version；
- Display Metadata、Category、Documentation、Deprecation State；
- 命名 Input/Output Port Specification、Cardinality 和 Type Expression；
- Parameter Specification、Constraint 和 Default；
- Purity/Statefulness 与 Runtime Capability；
- Validator 与 Compiler/Lowering Hook；
- Block 支持的 Semantic Version Range。

### BlockInstance

属于 Rule 的保存配置：Node ID、Block Type/Version、Parameter Value、可选 Label 和非语义 Presentation。它不复制 Library Port，也不包含 Runtime State。

### Port 与 Edge

Port 包含稳定 Name、Direction、Type Expression、Cardinality 和 Optionality。Edge 连接 `from.node/port` 与 `to.node/port`；Variadic Input 顺序使用 `to.slot`，不得依赖 YAML Array Order 猜测。

### RuntimeOperator

由 Compiler 创建的可执行行为，包含稳定 Operator ID 和 Source Map。Operator 分为 Pure/Stateless 与 Stateful。Temporal State 不得隐匿在 Scheduler 中。

### Registry 与扩展

MVP 使用由 Application Composition Root 构造的显式 In-process `BlockRegistry`：

```python
registry.register(my_block_definition)
```

重复注册 `(type_id, version)` 必须失败。新增 Block 的步骤：

1. 选择带 Namespace 的稳定 Type ID 和 Version；
2. 定义 Port、Parameter、Invariant 和语义文档；
3. 实现 Validation/Lowering 与 Runtime Operator；
4. 添加 Block Unit、Compiler、UNKNOWN、Ordering、Serialization 以及适用的 Golden Test；
5. 注册到 Built-in Library 或显式配置的 Extension Module。

MVP 不进行环境自动扫描，也不允许任意 Python Custom Function。这些功能会引入 Reproducibility、Security、Dependency 和 Version Resolution 问题。未来 Plugin Manifest 应固定 Package Hash 和 Block Version。

## 5. IR 设计

IR 保存已经解析的概念：

- Canonical Rule Identity 与 Semantic Profile；
- Typed Source Slot 和 Binding ID；
- 规范 Base Value/Unit 的 Constant；
- 按拓扑排序的 Pure Operator；
- Edge、Duration、Window 和 Assertion Operator 的 State-machine Specification；
- 显式 Alignment、Freshness、Gap、Boundary、Overlap、Completion 和 Aggregation Policy；
- Source Subscription Set；
- Deadline Schedule Requirement 和 Memory/Resource Estimate；
- 从 IR Operator 到 Rule Node/Port 的 Source Map。

以下是说明性 IR，不是持久化契约：

```yaml
# A：CellTemp > 70 degC
sources:
  s0: {binding: vehicle.CellTemp, type: quantity.temperature, unit: degC}
constants:
  c0: {value: 70, unit: degC}
operators:
  - {id: o0, op: compare.gt, inputs: [s0, c0], output: q0,
     clock: on_left_input, alignment: {kind: observe_only}}
assertions:
  - {id: a0, op: assert.never, condition: q0, true_status: FAIL,
     false_status: PASS, unknown_status: UNKNOWN, scope_semantics: observed_samples}
```

```yaml
# B：ChargeEnable 每次上升沿后，PackCurrent 必须在 500 ms 内变为正值
sources:
  s0: {binding: ChargeEnable, sampling: {kind: observe_only}}
  s1: {binding: PackCurrent, sampling: {kind: hold_last, max_age_ns: 150000000}}
constants:
  c_true: {value: true, type: bool}
  c_zero: {value: 0.0, type: float, unit: A}
operators:
  - {id: o_enable, op: compare.eq, inputs: [s0, c_true], output: q_enable}
  - {id: o0, op: compare.gt, inputs: [s1, c_zero], output: q0}
  - {id: o1, op: edge.rising, input: q_enable, output: e0, initialization: require_baseline}
  - {id: o2, op: edge.rising, input: q0, output: e1, initialization: require_baseline}
evaluations:
  - {id: x0, op: expect.within, trigger: e0, satisfaction_event: e1,
     interval_ns: {lower: 0, upper: 500000000, lower_closed: false, upper_closed: true},
     overlap: independent, incomplete: UNKNOWN}
```

```yaml
# C：SignalA == 1 连续两秒后，SignalB 必须为 1
sources:
  s0: {binding: SignalA, type: int, unit: none}
  s1: {binding: SignalB, type: int, unit: none}
constants:
  c_one: {value: 1, type: int, unit: none}
operators:
  - {id: o0, op: compare.eq, inputs: [s0, c_one], output: q0}
  - {id: o1, op: temporal.for_at_least, input: q0, duration_ns: 2000000000, output: e0}
  - {id: o2, op: compare.eq, inputs: [s1, c_one], output: q1}
evaluations:
  - {id: x0, op: expect.at_event, trigger: e0, condition: q1,
     alignment: {kind: hold_last, max_age_ns: 250000000}, unknown: UNKNOWN}
```

## 6. Runtime 模型

### Event

Runtime 接受有序的 `NormalizedTransaction | Watermark | EndOfStream` 流。`NormalizedTransaction` 原子包含 `SignalUpdate | QualityUpdate | GapStart | GapEnd` Transaction Item；Runtime 不接受脱离 Transaction Envelope 的单个 Item。Data Source 细节只保存在 Provenance。

### RuntimeContext

保存 Immutable Compiled Rule、Current Time/Watermark、带 Age/Quality 的 Typed Source Slot、Operator State Table、Active Evaluation、Deadline Queue、Bounded Evidence Recorder、Diagnostic Sink 和 Resource Counter。它按 Analysis Partition/Run 创建，不序列化进 Rule File。

### Operator Protocol

```python
class Operator(Protocol):
    def initialize(self, ctx: RuntimeContext) -> None: ...
    def on_batch(self, batch: TimestampBatch, ctx: RuntimeContext) -> None: ...
    def on_watermark(self, watermark_ns: int, ctx: RuntimeContext) -> None: ...
    def finalize(self, end: EndOfStream, ctx: RuntimeContext) -> None: ...

class StatefulOperator(Operator, Protocol):
    def reset(self, scope: ResetScope, ctx: RuntimeContext) -> None: ...
```

Pure Operator 除 Scheduler 管理的 Current Output 外，不保存跨 Batch Mutable State。Stateful Operator 使用显式、可检查的 State Record。`finalize` 只根据 Semantic Profile 处理可确定结果，不得将不完整 Evidence 变为 FAIL。

### Timestamp Batch 处理顺序

同一 Timestamp 内可能存在同一 Signal 的多次 Transition，同时一个 CAN Frame 解码出的多个 Signal 必须原子更新。因此既不能把整个 Batch 合并成“最终值”，也不能把同一 Frame 拆成会产生中间状态的独立求值。每个 Timestamp `t` 依次执行：

1. 收集全部 Normalized Input Transaction，并按 `(source_id, transaction_sequence)` 稳定排序；完整 Batch 未收齐前不执行语义计算。CAN Adapter 通常令一个 RawFrame 对应一个 Transaction。
2. 先处理在 `[start,t)` 上已经成熟的 Duration/After Timer。它们只依赖 `t` 之前的历史；例如 TRUE 在 `t` 恰好转为 FALSE，长度正好为 `d` 的区间仍满足 ForAtLeast。
3. 逐个 Transaction 执行 Microstep：先原子写入该 Transaction 的全部 Source Update，再按 Topological Order 传播 Dirty Pure Operator，更新 Edge/Duration State，并收集 Trigger、Target 和 Truth Observation。同一 Frame 的 Signal 不会产生“部分新、部分旧”的瞬时状态；不同 Frame 的同时间 Transition 仍被保留。Microstep 新调度的 `After(0)`/`ForAtLeast(0)` 放入本 Timestamp 的 Derived-timer Queue，在所有 Input Transaction 完成后、Temporal Matching 前按 Topology 排空；禁止递归立即调用。由于 Definition 是 DAG，每个 Operator 在该轮最多因每个上游 Occurrence 触发一次，且仍受 Per-timestamp Resource Limit 约束。
4. 在完整 Timestamp Event Set 上执行 Temporal Matching。只要 Lower Bound Closed，同时间 Target 即使在 Trigger 的 Sequence 之前出现也可参与匹配；需要 Arrival Order 的 Rule 必须使用显式 Sequence Constraint。
5. 处理 Gap/Quality 对窗口可观测性的影响，并在处理完同时间 Target 后关闭 Within Deadline。Closed Upper Bound 因而真正包含端点。
6. 处理在 `t` 之后生效的 Freshness Expiry，记录 Bounded Evidence，发布 Terminal Evaluation。
7. 只有 Source 明确提供 Watermark 时才推进它。

Offline Chunk Boundary 对语义不可见，Timestamp Batch 不得跨 Chunk 拆分。默认 Out-of-order Event 在改变状态前触发 Run-level Fatal ERROR；MVP 停止本次执行，防止部分错误状态继续传播。

### EvaluationInstance

每个 Trigger 都创建带稳定 `evaluation_id`、Trigger Time/Event、Key、Allowed Window、Current State、Deadline、Target Observation、Evidence Reference 和 Terminal Status 的 Instance。默认 Overlap Policy 为 `independent`。未来可增加 `restart`、`ignore_while_active`、`single_per_key`、`merge`，但必须显式声明。

Bounded Expectation 状态变化：

```text
PENDING -> SATISFIED（窗口内命中 Target） -> PASS
        -> EXPIRED（同时间 Batch 完成且 Watermark 到达闭合 Deadline） -> FAIL
        -> INDETERMINATE（Missing/Gap/窗口不完整） -> UNKNOWN
        -> ABORTED（Engine/Resource Fault） -> ERROR
```

Terminal Result 发布后不可变。未来 Live Late Data 所需的 Correction/Retraction 需要新的 Runtime Protocol Version。

`evaluation_id` 必须确定性派生，不能使用随机 UUID。输入为 Execution Semantic Hash、Expectation Node ID、Trigger Event ID、Instance Key 和同一 Trigger 的 Occurrence Index；因此 Parameter Override 或有效 Binding 改变时 ID 也会改变。Normalized Event ID 由 Input Artifact ID、Source ID、Timestamp、Transaction Sequence、Transaction 内稳定 Item Index 与 Decode Binding ID 派生。所有 Payload、JCS/SHA-256 算法和版本以 `implementation-contract.md` 为准，并由 Golden Test 固定。

### 可观测性与 Missing Coverage

“没有 Target Event”只有在整个相关窗口可观测时才能证明。Runtime 为每个 Truth/Event Dependency 维护 Coverage：

- Known Value 在 `hold_last(max_age)` 有效期内提供连续 Coverage，并在新 Sample 到来时刷新。
- `observe_only` 只在 Observation Time 提供点状 Coverage，不能单独证明两个 Sample 之间的连续状态；但 Edge Detector 可以比较没有显式 Gap 分隔的相邻 Observation。
- `GapStart` 立即终止受影响 Source/Channel 的 Coverage；`GapEnd` 只表示传输恢复，不恢复旧 Value，必须等待新的 Good Sample 重新建立状态。
- Gap Event 必须携带影响范围（Source Key 集合、Channel 或整个 Input）。无法确定范围时按整个 Input 处理。
- 对 `becomes_true`，成功 Edge 可以直接得出 PASS；未出现 Edge 时，只有 Baseline 已知且整个 Window Coverage 完整，Timeout 才是 FAIL，否则为 UNKNOWN。
- 对 `is_true`，任意有效 TRUE 可以得出 PASS；没有 TRUE 时，同样需要完整 Coverage 才能 FAIL。

Freshness 的有效区间为闭区间 `[sample_time, sample_time + max_age]`。恰好在 Max Age 时 Value 仍有效；该 Timestamp 的全部语义处理完成后，后续时间才视为 STALE。`max_age` 必须来自 Rule/Analysis Configuration 或明确的通信矩阵 Metadata，不能根据相邻 Sample 自动猜测。

Runtime 必须分别保存 Last Observation 与 Current State Coverage。Freshness 到期即使没有新 Source Sample 也会生成 Derived UNKNOWN/Recompute；否则 Duration 会错误地跨越 Stale 区间。

### RuleRuntime Lifecycle

```text
build(compiled_rule, run_config)
initialize()
accept(timestamp_batch)*
advance_watermark()*
finalize(end_of_stream)
result()
close()
```

MVP 中每个有序 Partition 使用单线程 Runtime。只有证明 Merge 确定性后，才可在独立 File/Ruleset 之间并行。

## 7. Truth 与 Missing Data

Condition 使用 Kleene 三值逻辑：

| A | NOT A |
|---|---|
| TRUE | FALSE |
| FALSE | TRUE |
| UNKNOWN | UNKNOWN |

AND 中 FALSE 优先；没有 FALSE 时 UNKNOWN 优先，只有双方 TRUE 才为 TRUE。OR 中 TRUE 优先；没有 TRUE 时 UNKNOWN 优先，只有双方 FALSE 才为 FALSE。逻辑原语在应用短路规则前必须验证全部 Operand 均为 `TruthValue`；其他对象属于编程错误，不得转换成 TRUE、FALSE 或 UNKNOWN。Operand 缺失、过期、无效或类型不兼容时，应由 Comparison 显式产生 UNKNOWN。

UNKNOWN 是 Logical Observation；`DATA_MISSING`、`INVALID`、`NOT_EVALUATED` 等是 Evaluation/Rule Level 的 Classification 或 Reason。Adapter 禁止用 Numeric Default 替换 Bad Data。Policy 可以显式映射 UNKNOWN，但该映射必须保存并写入报告。

## 8. Result 模型

- `PASS`：能够确定 Expectation 已满足。
- `FAIL`：有效 Evidence 能够确定违反 Expectation，或完整 Deadline 到期。
- `UNKNOWN`：数据或分析范围不足以证明 Pass/Fail。
- `ERROR`：Evaluation 未能正确执行。
- `NOT_EVALUATED`：没有适用的 Trigger/Scope。
- `INVALID`：Rule Load/Validation/Compilation 失败，通常为 Pre-run Result。
- `SKIPPED`：由显式 Filter/Configuration 排除。

`DATA_MISSING` 通常是与 UNKNOWN 配套的 Reason Code，不是与 Status 冲突的顶层 Truth Value。

Aggregation 必须显式。MVP 的 `worst_conclusive_then_unknown` 使用严格顺序：`INVALID > ERROR > FAIL > UNKNOWN > PASS`。`NOT_EVALUATED` 只在没有任何可评估 Instance/Scope Observation 时产生；`SKIPPED` 只在整个 Rule 被显式排除时产生，不参与普通聚合。Severity（info/warning/error/critical）独立于 Status。

Scope-based Assertion 的精确聚合：

- `assert_never(condition)`：任一 TRUE -> FAIL；否则任一 UNKNOWN/不可观测区间 -> UNKNOWN；至少一条有效 FALSE 且 Scope Coverage 完整 -> PASS；没有有效 Observation -> NOT_EVALUATED。
- `assert_always(condition)`：任一 FALSE -> FAIL；否则任一 UNKNOWN/不可观测区间 -> UNKNOWN；至少一条有效 TRUE 且 Scope Coverage 完整 -> PASS；没有有效 Observation -> NOT_EVALUATED。
- Scope 默认是完整 Analysis Session。若 Rule 声明 Triggered/State Scope，Compiler 必须 Lower 为显式 Evaluation Instance，不能只修改 Aggregator。

“Scope Coverage 完整”依赖 Source Availability 与 Sampling Policy。`observe_only` 的离散 Sample Rule 可以声明 `scope_semantics: observed_samples`，表示只对实际 Observation 断言；否则无法证明 Sample 之间的连续 Always/Never，结果应为 UNKNOWN。Example A 使用 `observed_samples`，语义是“所有已记录 CellTemp Sample 均不得超过 70 °C”，而不是对 Sample 之间的物理温度作连续证明。

`EvaluationResult` 包含 Trigger、Window、Terminal/Failure Time、Expectation Summary、Actual Observation、Duration、Reason Code、Message Key/Argument、Violation 和 Bounded Evidence。`RuleResult` 包含 Rule Identity/Version、Aggregate Status、Count、Evaluation Result 或 Summary、Diagnostic 与 Reproducibility Manifest Reference。

Evidence 应优先保存 Typed Observation 与 Source Reference，而不是 Rendered Prose。Report Generator 在不了解 Operator 内部实现的情况下完成本地化和格式化。

## 9. 核心模型草图

以下代码只表达 Ownership 与 Type，不要求实现时原样照搬：

```python
from dataclasses import dataclass
from enum import Enum
from typing import Generic, Mapping, TypeVar

TimestampNs = int
DurationNs = int
T = TypeVar("T")

class TruthValue(Enum):
    TRUE = "true"
    FALSE = "false"
    UNKNOWN = "unknown"

class Quality(Enum):
    GOOD = "good"
    MISSING = "missing"
    STALE = "stale"
    INVALID = "invalid"
    DECODE_ERROR = "decode_error"

@dataclass(frozen=True)
class SignalSample(Generic[T]):
    timestamp_ns: TimestampNs
    source_key: str
    value: T | None
    value_type: str
    unit: str | None
    quality: Quality
    source_id: str
    transaction_id: str
    transaction_sequence: int
    item_index: int
    provenance: Mapping[str, str]

@dataclass(frozen=True)
class TimeWindow:
    start_ns: TimestampNs
    end_ns: TimestampNs
    start_closed: bool
    end_closed: bool

@dataclass(frozen=True)
class PortRef:
    node_id: str
    port: str
    slot: int | None = None

@dataclass(frozen=True)
class EdgeDefinition:
    id: str
    source: PortRef
    target: PortRef

@dataclass(frozen=True)
class BlockInstance:
    id: str
    type_id: str
    version: int
    parameters: Mapping[str, object]

@dataclass(frozen=True)
class RuleDefinition:
    id: str
    version: str
    name: str
    severity: str
    nodes: tuple[BlockInstance, ...]
    edges: tuple[EdgeDefinition, ...]
```

Persistence-facing `RuleDefinition` 很可能使用 Pydantic，并编译为独立 Frozen IR Dataclass。Runtime Instance State 是可变的，但不得被前两者引用。

```python
class EvaluationStatus(Enum):
    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"
    ERROR = "error"
    NOT_EVALUATED = "not_evaluated"
    INVALID = "invalid"
    SKIPPED = "skipped"

@dataclass(frozen=True)
class Evidence:
    timestamp_ns: TimestampNs
    kind: str
    source_key: str | None
    value: object | None
    unit: str | None
    quality: Quality | None
    provenance_ref: str | None

@dataclass(frozen=True)
class Violation:
    code: str
    expected: str
    actual: object | None
    window: TimeWindow | None
    message_args: Mapping[str, object]

@dataclass(frozen=True)
class EvaluationResult:
    evaluation_id: str
    status: EvaluationStatus
    reason_code: str
    trigger_ns: TimestampNs | None
    terminal_ns: TimestampNs | None
    window: TimeWindow | None
    violation: Violation | None
    evidence: tuple[Evidence, ...]
    evidence_truncated: bool

@dataclass(frozen=True)
class RuleResult:
    rule_id: str
    rule_version: str
    name: str
    overall_status: EvaluationStatus
    evaluations: tuple[EvaluationResult, ...]
    manifest_ref: str
```

Normalized Control Event、Compiled IR、Runtime Context 和 Operator Protocol 即使字段相似，也必须使用独立 Type。

## 10. 安全与容量 Policy

Run Configuration 必须限制 Graph Node、每 Rule/Key 的 Active Instance、Deadline Entry、Retained History Horizon、Evidence Item/Byte、Diagnostic 数量，并可限制每 Timestamp 的 Operation 数。达到上限时，受影响 Evaluation 产生 ERROR 和 Resource-limit Reason，Run Manifest 必须记录。只有非语义 Display Evidence 可以被静默截断，但必须设置 `evidence_truncated=true`。
