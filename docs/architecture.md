# 汽车规则分析平台架构

状态：MVP 架构基线  
读者：维护者、Rule Author、GUI/CLI、Parser 开发者  
配套规范：`rule-engine.md`、`time-semantics.md`、`rule-schema.md`、`implementation-contract.md`  
审计记录：`architecture-review.md`

## 1. 架构目标

产品对按时间排序的标准化数据执行可持久保存、由用户定义的规则。CAN 是第一种 Data Source，而不是 Rule Engine Domain。系统的核心资产是一套确定、强类型、可解释的 Temporal Rule Engine，它既能处理 Offline Replay，也能支持未来 Live Stream。

MVP 需要打通：

```text
BLF / ASC -> RawFrame -> DBC Adapter -> Normalized Event
          -> Rule Validation/Compilation -> Rule Runtime
          -> Standardized Result -> JSON / HTML Report
```

MVP 明确排除完整 GUI、用户系统、云服务、数据库、分布式执行、AI 诊断和 Plugin Marketplace。

## 2. 需求分析

### 2.1 核心需求

- Rule 必须是独立于 GUI、Parser、Report Format 和 Runtime Object 的可移植 Artifact。
- Rule 可组合 Value、Condition、Event、Temporal Expectation、Sequence 和 Outcome。
- 时间行为必须明确 Interval、Boundary、Missing Data、Ordering 与 End-of-input Semantics。
- 一个 Rule 可以创建零个、一个或多个 Evaluation Instance。
- Result 必须保留 Evidence 与 Provenance，并区分行为失败和无法评估。
- Engine 只接收 Normalized Event Stream，不依赖 CAN Library 或文件格式。

### 2.2 功能需求

- MVP 读取 BLF/ASC，通过 DBC Decode 后输出标准化 Signal Update。
- 验证 Graph Rule Definition，编译为 Executable IR 并确定性执行。
- MVP Block：Signal、Constant、Comparison、Boolean Logic、RisingEdge、Duration、Within 与 Result Assertion；FallingEdge 成本较低，一并纳入语义基线。
- 从毫秒到分钟的时间窗口全程使用整数 Duration，不进行浮点时间运算。
- 输出逐 Trigger Evaluation 和聚合 Rule Status，并生成 JSON/HTML。
- 保存 Schema/Semantic Version，并显式迁移旧 Rule Definition。

### 2.3 非功能需求

- Correctness、Determinism、Explainability、Testability、Backward Compatibility 优先于功能数量。
- 内存占用不得随输入日志大小无限增长；允许随 Active Window 和 Evidence 配置增长。
- Core Package 不依赖 `python-can`、`cantools`、Plotly、Jinja2 或 GUI Toolkit。
- 行为变更必须有自动测试；时间测试只使用逻辑 Timestamp，禁止依赖墙上时间。
- Report 必须记录 Input、DBC、Ruleset、Semantic Profile、Compiler/Engine 与配置 Identity。

### 2.4 隐含需求

- 相同 Timestamp 的 Sample 需要确定性 Tie-breaker。
- Completion 与 Timeout 需要 Watermark/End-of-input，而不能只看最后 Sample。
- Signal Comparison 必须有显式 Alignment/Freshness Policy。
- Unit、Enum、Multiplexing、Invalid Raw Value 和 DBC Decode Failure 必须进入 Quality/Provenance，不能丢失。
- Rule Aggregation Policy 独立于单次 Trigger Outcome；没有 Trigger 不自动等于 PASS。
- 必须限制 Trigger Instance、Window、State 和 Evidence 等资源。
- 保存文件不得包含 Python Class Name 或可执行代码。
- 每个 Rule 在 MVP 中恰好有一个 Terminal Result Node，Rule Set 负责跨 Rule 聚合。

### 2.5 未来扩展需求

- MDF/MF4、CSV、Parquet、Simulation、FlexRay、Ethernet 与 Live Source 通过 Adapter 接入。
- 在不修改 Scheduler Core 的前提下增加 Temporal/Sequence/State/Filter Operator。
- PySide6 或 Web Editor 根据 Block Metadata 生成编辑界面。
- Batch Optimization、Selective/Lazy Decode，以及 Stateless Expression Island 的 Vectorization。

### 2.6 必须显式配置或决策的模糊点

| 问题 | 架构基线 |
|---|---|
| `Within 500 ms` 是否包含 Trigger 与 Deadline？ | 必须显式选择边界。Response 示例使用 `(start,end]`；已为真或变为真使用 `[start,end]`。Deadline Data 先于 Timeout。 |
| Target 必须“变为真”还是只需“为真”？ | 显式 `satisfaction` Mode。Response 使用 `becomes_true`，State 使用 `is_true`。 |
| 没有 Trigger 怎么处理？ | Evaluation Status 为 `NOT_EVALUATED`，由 Aggregation Policy 决定展示。 |
| 日志在 Deadline 前结束？ | `UNKNOWN/INCOMPLETE_WINDOW`，禁止隐式 FAIL。 |
| 不同 Signal Rate 如何对齐？ | 每个 Input 显式配置 Sampling Policy；MVP 可用带有限 Freshness 的 Hold-last。 |
| 什么是 Data Gap？ | 由 Adapter Gap Event 和/或 Max Age 定义，不猜测统一阈值。 |
| 是否允许 Overlapping Trigger？ | 默认允许并创建独立 Instance，同时受 Resource Policy 限制。 |
| `Duration` 遇到 UNKNOWN？ | 默认中断连续性证明；其他策略必须显式定义。 |
| Duplicate Timestamp 如何处理？ | 使用稳定 `(timestamp_ns, source_id, transaction_sequence)`；Transaction 内 Signal 原子更新，Timestamp Batch 内按 Transaction 执行 Microstep。 |
| 是否允许 Cycle？ | MVP 不允许。未来只能引入 Compiler 可识别的显式 State/Delay Feedback。 |
| Unit 是否自动转换？ | Known Unit 做 Dimension Check；只允许小型受控 Registry 转换；Unit-sensitive Operation 遇到 Unknown Unit 时 Validation Error/INVALID。 |
| Float Equality 是否精确？ | 允许 Exact Equality 但产生 Warning；未来增加 Approximate Comparison。 |

## 3. Domain 分析

Engine 使用与数据源无关的 Stream Concept；CAN Signal 只是其中一种 Binding Source。

- **TimePoint：** 同一 Monotonic Analysis Timeline 上的 int64 纳秒。
- **DataEvent：** 在 TimePoint 上有序的标准化 Update 或 Control Event。
- **ValueStream<T>：** 带 Timestamp、Type 与 Quality 的值 Observation。
- **TruthStream：** 三值逻辑 Observation：TRUE、FALSE、UNKNOWN。
- **EventStream<E>：** 离散事件；没有 Event 不等于 FALSE。
- **SignalReference：** Logical Binding Key 与预期 Type/Unit，不持有 DBC Object。
- **Condition：** 输出 TruthStream 的表达式。
- **Trigger：** 创建 EvaluationInstance 的 Event Occurrence。
- **RuleDefinition：** 保存的用户 Graph、Metadata 和 Policy。
- **BlockDefinition：** Block Type 的 Versioned Port/Parameter/Constraint/Compiler Specification。
- **BlockInstance：** 保存规则中的已配置 Node。
- **Port/Edge：** Block Instance 之间的强类型连接。
- **RuleGraph：** Authoring DAG。
- **CompiledRule/IR：** 已解析 Type、Binding、Policy、Topology、Operator 和 Subscription。
- **RuleRuntime：** Compiled Rule 的 Scheduler 与 Operator State。
- **EvaluationInstance：** 单次 Trigger 的 Window、State、Evidence 和 Terminal Status。
- **TimeWindow：** 带显式 Lower/Upper Bound 的区间。
- **Violation：** 对未满足 Expectation 的结构化说明。
- **Evidence：** 支持 Outcome 的有界 Reference/Snapshot。
- **RuleResult：** Aggregate Metadata 与 Evaluation Result/Summary。

```text
RuleDefinition 1 -> many BlockInstances 1 -> Ports
BlockInstances many -> Edges -> many BlockInstances
RuleDefinition -> Compiler -> CompiledRule
CompiledRule -> RuleRuntime -> many EvaluationInstances
EvaluationInstance -> 0..many Evidence
EvaluationInstance -> 0..1 Violation
RuleRuntime -> RuleResult
```

## 4. Rule Representation 对比

| 模型 | 优点 | 本项目局限 | 决策 |
|---|---|---|---|
| Expression Tree | 简单，易 Type Check | 无法自然共享子表达式或多分支 | 仅作为 Pure Expression 的内部形式 |
| AST | 适合稳定 Text DSL | Visual Graph 共享 Node 还需额外 Identity/Edge | 未来增加 Text DSL 时使用 |
| DAG | 适合可视化、共享 Node、拓扑验证 | Edge 本身不能表达 Temporal State | **保存 Rule Definition** |
| General Graph | 可表达 Feedback | Cycle 的调度与时间语义复杂且危险 | MVP 拒绝；未来只允许受控反馈 |
| State Machine | 擅长 Protocol/Sequence Lifecycle | Arithmetic/Boolean Dataflow 不自然，组合易状态爆炸 | Temporal Operator/Instance 编译为状态机 |
| Event Stream | 统一 Offline/Live，适合 Sparse CAN | 必须显式 Retention、Watermark、Alignment | **Runtime Input Model** |
| Reactive/Dataflow Graph | 增量计算、可裁剪 Subscription | 朴素传播可能依赖顺序或保留过多 State | **结合 Timestamp Batch 使用** |
| Temporal Logic | 数学语义精确 | 完整 LTL/MTL 难编辑、难诊断、难增量实现 | 借用有界语义，不直接暴露完整逻辑 |
| CEP/Rule Network | Multi-pattern Match 效率高 | Framework 过重且语义不透明 | 在真实多规则负载出现后再评估 |

### 推荐组合架构

1. 使用 Strongly Typed DAG 作为持久化 Authoring Representation。
2. Compiler 将其 Lower 为规范化 Operator IR。
3. Timestamp-batched Event-stream Runtime 执行 Stateless Dataflow Operator 和 Temporal State Machine。
4. Bounded Temporal Operator 借鉴 Metric Temporal Logic 的区间语义，但 MVP 不暴露通用定理语言。

这种组合让 GUI 保持直观，但不把 GUI Topology 直接变成 Runtime Contract，同时为 Schema Migration 与优化保留 Compiler Boundary。

## 5. 数据接入架构

```text
Infrastructure Adapter                        Core Boundary

BLFReader ----\
               -> RawFrame -> DbcDecoder -> NormalizedEventSink -> DataEvent
ASCReader ----/                         |             |
                                        + Quality     + Watermark/Gap/End
```

`RawFrame` 是内部 Ingestion Model，不是 `python-can.Message`。`DbcDecoder` 封装 DBC 实现并输出中立 `SignalUpdate`。Engine 只看 Source Key、Typed Value、Timestamp、Quality 和 Provenance。

Adapter 负责：

- 将 Source Timestamp 转为单调 `timestamp_ns`，避免浮点累积误差；
- 分配稳定 `source_id`、`transaction_id`、`transaction_sequence` 和 Transaction 内 `item_index`；CAN 中通常一帧对应一个 Transaction；
- 将 Channel/Message/Signal 信息保留为 Provenance；
- 将 Invalid、Unavailable、Decode Error 和 Gap 映射为 Quality/Control Event；
- 发出 Watermark 和 End-of-stream。

编译前，Application 使用 DBC Catalog 解析 Logical Signal Binding。Compiler 接收中立 Binding Table；任何 cantools Object 都不得越过边界。

## 6. Sampling 与 Alignment

规范 Engine 是 Event-driven，不对整份日志重采样。每个 Value Input 使用显式 Policy：

- `observe_only`：仅在该 Source Update 时求值，只提供点状 Coverage；
- `hold_last(max_age)`：在有限 Age 内保留上一条 Good Observation；
- `strict_same_timestamp`：所有 Operand 必须在当前 Timestamp Batch 出现；
- `nearest`、`interpolate`：Offline Preprocessing Policy，不是 MVP Runtime Default。

对 `A > B` 还必须声明 Evaluation Clock，通常为 `on_any_input` 或 `on_left_input`。Required Operand 没有可接受 Observation 时输出 UNKNOWN。没有 Sample 不自动表示值保持不变；若规则需要证明窗口内的连续状态，必须使用带有限 `max_age` 的 Hold-last 或显式 Availability Contract。Fixed-grid Resampling 仅作为真正需要它的算法的 Application Preprocessing；Method 与 Interval 必须进入 Reproducibility Metadata。

## 7. 性能架构

### 方案分析

- **Whole-log DataFrame：** 便于探索，但会复制 Decode Data、内存不可控，并掩盖 Sparse Temporal Semantics。
- **逐 Sample Stream：** 内存有界、支持 Live，但 Python Dispatch 开销较大。
- **Chunked Stream：** 批量 I/O/Decode，同时跨 Chunk 保留 Event Order 与 State。
- **Lazy/Selective Decode：** 只 Decode Compiled Rule Subscription 所需 Signal。
- **Signal Index：** 便于 Offline Targeted Scan，但需要额外 Preprocessing/Storage，MVP 非必需。

### MVP 决策

Frame 与 Decode 按 Chunk 处理，然后将有序 Timestamp Batch 输入 Persistent Streaming Runtime。Runtime 不要求完整日志驻留内存。读取前先编译 Ruleset 并提取 Message/Signal Subscription，避免 Decode 无关 Frame。Evidence 使用 Bounded Ring Buffer 和 Source Offset Reference。

10 GB Log 的瓶颈主要是 Parsing/Decode，而不是内存。未来可选择构建按 Source/Time Range 索引的 Parquet/Cache，但这是 Application Optimization，不得改变 Engine Semantics。

必须限制 Active Instance、Retained History、Evidence Byte 和 Per-rule Work。达到限制产生 `ERROR/RESOURCE_LIMIT`，禁止静默淘汰。未来可融合跨 Rule 的共享 Pure Subgraph，并对 Stateless Expression Island 向量化。

## 8. Unit System 决策

仅保存 Unit String 成本低，但会允许 Ampere 与 Degree Celsius 等无意义比较，并使未来强制检查成为 Breaking Change；完整 Unit Algebra 则会过早引入 Alias、Offset Unit、Compound Dimension、Dependency 和 Migration 问题。

MVP 采用“从一开始检查，但能力保持有限”的折中方案：

- Numeric Source/Constant 必须携带 Canonical Unit，或显式声明 `unit: none`/`unit: unknown`；
- Comparison、Add/Subtract 要求 Known Dimension 相同；
- Application-owned 小型 Registry 处理 MVP 所需 Automotive Unit 和显式 Conversion，包括 Offset-aware Temperature；
- Multiply/Divide Derived Unit Algebra 与任意 User-defined Unit 延后；
- Unknown Unit 在 Unit-sensitive Operation 中无法证明兼容时产生 Validation Error，使 Rule 为 INVALID；运行期 UNKNOWN 只用于数据值或质量未知，不能掩盖静态 Unit 错误；
- Original DBC Unit Text 与 Normalized Unit Identity 都进入 Provenance。

只有在 Pint 等 Library 的 Serialization、Offset Temperature、Performance 和长期 Identifier 行为经过真实 DBC 验证后，才考虑采用。

## 9. 依赖方向

```text
      PySide/Web UI       CLI        JSON/HTML Report
            \              |              /
             +------ Application/Use Cases ------+
                         |          ^
                         v          |
              Rule Definition/Compiler/Result
                         |
                         v
              Domain + Rule Runtime Core
                         ^
                         |
       Infrastructure Adapter（BLF/ASC/DBC/Live/Cache）
```

Dependency 一律向内。Infrastructure 实现 Core/Application Protocol。Domain/Runtime 不导入 UI、Report、CAN Library、File Reader、Pydantic Serialization Model 或 Application Orchestration。Pydantic 适合 File/API Boundary；Core 优先使用 Frozen Dataclass 等显式类型。

## 10. 推荐目录结构

```text
src/app_dataloganalysis/
  domain/
    time.py                 # TimePoint、Duration、Interval Bound
    values.py               # Typed Value、TruthValue、Quality
    events.py               # 中立 Data/Control Event
    provenance.py
  rules/
    definition/             # Persistence Model、Serialization、Migration
    blocks/                 # Definition、Builtin、Registry
    validation/             # Graph、Type、Unit、Diagnostic
    compiler/               # Compiler、Lowering、Binding
    ir/                     # 私有 IR Model 与 Debug Serialization
    runtime/                # Scheduler、Context、Operator、Instance、Limit
  ingestion/
    ports.py                 # Frame/Event Source Protocol
    models.py                # RawFrame，不依赖 Vendor Object
  application/
    analyze.py
    configuration.py
    manifest.py
  infrastructure/
    can/                     # BLF/ASC/python-can Adapter
    dbc/                     # cantools Adapter
    cache/
  results/
    models.py
    aggregation.py
  reporting/
    json_report.py
    html_report.py
    templates/
  cli/
    main.py
tests/
  unit/
  compiler/
  runtime/
  temporal/
  integration/
  golden/
examples/
docs/adr/
```

实际 Distribution Name 可以调整，但 Package Boundary 是架构决策。`ingestion` 定义 Port/Model，`infrastructure` 实现它们。Report 只消费 `results`。

## 11. Reproducibility Manifest

每次 Analysis Run 输出：

- 每个 Input Log/DBC 的 Content Hash、Size 与 Stable Identity；
- 每个 Rule/Ruleset 的 Artifact、Definition、Rule Semantic Definition 与 Execution Semantic Hash，以及声明 Version；
- Original Rule Schema Version 和 Migration Chain；
- Semantic Profile、Engine、Compiler、Block Library、Python 和 Adapter Version；
- Time Origin、Ordering、Gap/Alignment、Aggregation、Resource 和 Evidence Policy；
- Start/End Timestamp 与 Warning/Diagnostic。

File Path 可便于查看，但不能作为 Identity。Secret 与 Machine-specific Path 必须可脱敏。

## 12. 技术选择

- **Python 3.12+：** 项目兼容下限为 3.12；`.python-version` 可以固定开发环境使用 3.13。Python 适合 Adapter 生态、快速迭代、Typing 和测试；Hot Loop 必须可测，为未来 Native/Vectorized Optimization 保留边界。
- **Pydantic：** 用于 Rule Definition、Configuration 和 Report Serialization Boundary，不进入 Runtime Operator。
- **PyYAML：** 使用 Safe Load，把 YAML 与 JSON 解析到同一 Schema Model。
- **python-can/cantools：** 仅存在于 Infrastructure Adapter。
- **pytest：** 主要 Test Runner；Core Semantics 稳定后再加入 Hypothesis。
- **Jinja2：** HTML Report Adapter；Plotly 可选，不能成为 Result/Core Test 依赖。
- **PySide6：** 延后的 UI Adapter，消费 Block Metadata 与 Application Service。

MVP 不选择 Reactive/CEP Framework。需要的 Scheduler 足够小，可以自行控制，避免外部 Framework 的 Time/Missing Semantics 变成产品契约。

## 13. 架构自我审查

### 最可能失败的地方

Temporal Operator 名称仍可能让用户带入未编码的含义。应通过 Typed Port、显式 Parameter、Compiler Diagnostic、示例和规范文档降低风险。第二大风险是高频 Trigger 与长窗口造成 Active Instance Explosion；在大规模部署前必须提供 Limit、Compact State、Deadline Structure 和 Overlap/Key Policy。

### 可能过度设计的部分

Generic Plugin Discovery、完整 Temporal Logic、Runtime Cycle、Cross-rule Optimization、Persistent Index、完整 Unit Algebra 和 Public Serializable IR 都属于过早设计。MVP 只应实现 In-process Registry、小型 Type Lattice、有界 Temporal Primitive 与 Private IR。

### 未来最难修改的部分

Time Boundary、UNKNOWN Propagation、Alignment Default 和 No-trigger Aggregation 的改变会使历史结果失效，因此必须属于 Named Semantic Profile，并在变更时增加 Major Semantic Version。Saved Node ID 和 Block Type/Version Resolution 同样难改；Migration 必须保留它们。

### 压力场景

- **10 GB Log：** Chunked Selective Decode 保持内存有界；只有 Profiling 证明必要时才增加 Columnar Signal Cache。
- **1,000 Block Rule：** Validation/Topological Compile 复杂度为 O(V+E)，但 Per-event Fan-out 可能很高。需要 Subscription Pruning、Dirty-node Propagation、Constant Folding、Profiling 和 Configurable Graph Limit。
- **10,000 Active Trigger：** State/Evidence 成为主要成本。使用 Compact Instance、Deadline Heap/Timing Wheel、Evidence Reference、Overlap/Key Policy 和 Hard Limit；禁止静默丢弃。
- **Live CAN：** 同一 Event API 可复用，但 Adapter 必须提供基于 Allowed Lateness 的 Watermark。Live Mode 还需 Backpressure、Bounded Lateness、Reconnect/Gap 与 Provisional Result，MVP 不伪造这些能力。
- **PySide GUI：** 读取 Block Metadata 并编辑 RuleDefinition；与 CLI 共用 Application Validation Service；Layout 仅保存到非语义 `presentation`。
- **三年前保存的 Rule：** Loader 选择 Migration Chain，保留 Original Artifact/Hash，报告变化，并使用声明的 Semantic Profile 编译。缺少所需 Block Version 时返回 INVALID，不得猜测。

## 14. MVP 之后再决策

- 完整 Statechart/Sequence Language 与受控 Feedback Cycle；
- Offline Interpolation 与 Vectorized Execution；
- Cross-rule Common-subexpression Sharing；
- Dynamic Third-party Discovery 或 Sandboxed Custom Code；
- 完整 Physical Unit Algebra；
- Live-stream Allowed-lateness 与 Retraction Protocol；
- Database/Cache Format 和 Distributed Partitioning。
