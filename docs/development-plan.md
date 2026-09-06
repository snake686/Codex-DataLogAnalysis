# MVP 开发计划

本计划由可独立交付的小任务组成。前置依赖完成后，每项任务都可以单独交给 Codex Agent。任何任务都不得为了实现简单而削弱规范时间语义。

## Task 1 — 仓库与质量基础设施

**目标：** 建立最小 Python 3.12+ 项目和统一质量检查入口。

**范围：** Packaging、Test Layout、Lint/Type/Test 配置、CI Skeleton、Dependency Group 和 Import Boundary Rule；不实现业务逻辑。

**文件/模块：** `pyproject.toml`、`src/app_dataloganalysis/__init__.py`、`tests/`、CI 配置和贡献文档。

**验收条件：** Editable Install 可用；测试集和质量工具可运行；Python 3.12/3.13 CI Matrix 通过；Core Package 不能导入 Infrastructure/Report/UI；Runtime Dependency 保持最小，Adapter 使用 Optional Extra。

**测试：** Smoke Import；Architecture/Import Boundary Check。

**依赖：** 无。

## Task 2 — 中立领域基础类型

**目标：** 实现精确 Time、Typed Value、Quality、Normalized Event、Interval 和 Provenance。

**范围：** Frozen Model、精确 Duration Parser、Normalized Event/Transaction Discriminated Union、Quality/Reason 和确定性 Event ID；不涉及第三方 CAN Class 与 Runtime Scheduling。

**文件/模块：** `domain/time.py`、`domain/values.py`、`domain/events.py`、`domain/provenance.py`。

**验收条件：** int64 ns 范围检查、精确 Unit-duration Parsing、全序 Ordering Key、TruthValue/Quality 定义；Bool 不被归类为 Int；NaN/Infinity 为 INVALID；禁止导入 `python-can`/`cantools`。

**测试：** Duration Boundary、Overflow、Ordering、UNKNOWN Truth Table、Event Immutability。

**依赖：** Task 1。

## Task 3 — Rule Definition Model 与 Schema v1

**目标：** 加载和保存文档定义的 YAML/JSON 格式，不包含 Runtime Object。

**范围：** Pydantic Boundary Model、Canonical Serialization/Hash、Schema Version Dispatch 和初始 Migration Framework。

**文件/模块：** `rules/definition/models.py`、`serialization.py`、`migration.py`、公开 JSON Schema、`rule-schema.md` 的 Fixture。

**验收条件：** 三个示例均可加载并 Round-trip；Duration String 保持精确；Duplicate ID/Unknown Semantic Field 产生稳定 Diagnostic；只有显式选择时 Semantic Hash 才排除 Presentation。

**测试：** Schema Fixture、JSON/YAML 等价、Deterministic Hash、Unsupported Major Version。

**依赖：** Task 1–2。

## Task 4 — Block Registry 与 MVP Block Definition

**目标：** 建立强类型、版本化 Block 契约和显式 Registry。

**范围：** 按 `implementation-contract.md` 实现 Metadata、Port、Parameter、Registry；仅定义 Signal、Parameter、Constant、GT/LT/EQ、AND/OR/NOT、Rising/FallingEdge、ForAtLeast、Within、AtEvent 和 Result Assertion。

**文件/模块：** `rules/blocks/definitions.py`、`registry.py`、`blocks/builtin/`。

**验收条件：** 拒绝重复 Type/Version；提供 GUI 可读 Metadata；不自动发现；每项定义记录 UNKNOWN/Time 行为并声明 Statefulness。

**测试：** Registry Resolution、Parameter Constraint、Port Signature、Version Mismatch。

**依赖：** Task 2–3。

## Task 5 — 静态 Validator

**目标：** 在编译前拒绝结构或语义无效的 Graph。

**范围：** 与 Schema 实现解耦的 Diagnostic、Graph/Reachability/Cycle、Port/Cardinality/Type Inference、初步 Unit Check、Temporal/Policy Check 和 Catalog Binding Protocol。

**文件/模块：** `rules/validation/`。

**验收条件：** 检测 `rule-engine.md` 列出的全部问题；Diagnostic 指向 Rule/Node/Port；Warning 不阻止编译；Validator 仅依赖中立 Signal Catalog Interface。

**测试：** 每个 Diagnostic 一组聚焦 Fixture、Malformed Graph Matrix、三个示例在 Fake Catalog 下均有效。

**依赖：** Task 2–4。

## Task 6 — Compiler 与不可变 IR

**目标：** 将有效 Definition Lower 为确定、可检查的 Runtime IR。

**范围：** Binding Resolution、Type/Unit Normalization、Constant、Topological Order、显式 `becomes_true` Lowering、Subscription、Source Map 和私有 IR Debug Serializer。

**文件/模块：** `rules/compiler/`、`rules/ir/`。

**验收条件：** 相同语义 Definition 产生等价 IR；Presentation 变更不影响 IR；Subscription 最小；Default/Policy 显式；Invalid Input 无法绕过 Validation。

**测试：** Example A–C 的 IR Snapshot、Constant/Type/Unit Lowering、Stable Topology、Source Map、Subscription Extraction。

**依赖：** Task 5。

## Task 7 — Stateless Runtime 与 Timestamp Scheduler

**目标：** 跨 Chunk 确定性执行 Source、Constant、Comparison 和 Boolean Operator。

**范围：** RuntimeContext、完整 Timestamp Batch 收集、原子 Transaction Microstep、Source Slot、Alignment/Freshness/Coverage、Pure Propagation、分 Phase Timer、Watermark/End Lifecycle；暂不实现 Temporal Instance。

**文件/模块：** `rules/runtime/context.py`、`scheduler.py`、`operators.py`、`limits.py`。

**验收条件：** Chunk 划分不改变结果；同时间顺序符合 Profile；Missing/Stale Operand 产生 UNKNOWN；Out-of-order Event 产生 ERROR。

**测试：** Truth Table、Clock/Alignment、Same-time Multi-transition、同 Frame Atomic Update、Chunk Invariance、Freshness Closed Boundary、GapEnd Rebaseline、End/Watermark、Resource Counter。

**依赖：** Task 2、6。

## Task 8 — Edge 与 Duration Operator

**目标：** 实现符合 Profile 的 RisingEdge、FallingEdge 和 ForAtLeast。

**范围：** 显式 State Record、Timer Scheduling、Baseline 和 UNKNOWN/Gap 行为。

**文件/模块：** `rules/runtime/operators.py` 或聚焦的 `runtime/temporal/` 模块。

**验收条件：** 行为符合 `time-semantics.md` 全部相关规定；Deadline 没有 Source Sample 时 Timer 仍可触发；State 可隔离、可 Reset。

**测试：** Table-driven Temporal Conformance，包括 First Sample、Gap、Staleness、Zero Duration、Same Timestamp 和 Exact Deadline。

**依赖：** Task 7。

## Task 9 — Evaluation Instance、Within 与 Result Model

**目标：** 支持重复 Trigger，并产生标准化的逐 Instance 和聚合 Result。

**范围：** Independent Overlap、Deadline、AtEvent、`is_true`/`becomes_true`、Coverage/Incomplete Window、Deterministic Evaluation ID、Evidence、Status/Reason、Aggregation 和 Limit。

**文件/模块：** `rules/runtime/instances.py`、Temporal Operator、`results/models.py`、`results/aggregation.py`。

**验收条件：** 多 Trigger 产生稳定 Instance ID；Closed Deadline 上先满足再 Timeout；Incomplete/Gap Window 为 UNKNOWN；无 Trigger 为 NOT_EVALUATED；Limit Exhaustion 为 ERROR；不得导入 Report Package。

**测试：** Multi-trigger Matrix、Boundary/Gap/End、Aggregation Precedence、Bounded Evidence、10,000 Instance Performance Smoke Test。

**依赖：** Task 7–8。

## Task 10 — Ingestion Port 与 CAN/DBC Adapter

**目标：** 把 BLF/ASC + DBC 转换为标准化有序 Event，不泄漏第三方 Object。

**范围：** RawFrame Port/Model、python-can Reader Adapter、cantools Decoder Adapter、Selective Decode、Quality/Provenance/Watermark 和小型 Fixture。

**文件/模块：** `ingestion/`、`infrastructure/can/`、`infrastructure/dbc/`。

**验收条件：** Public/Core Model 不包含第三方 Instance；Required-signal Subscription 避免无关 Decode；Timestamp 只按记录的 Rounding Policy 转换一次为整数纳秒；Binding 唯一区分 Channel/ID/Extended/Multiplex；Decode Error 进入 Quality/Diagnostic；Chunk 保持 Timestamp Batch 完整。

**测试：** Fake-port Contract Suite、Generated ASC/BLF/DBC Integration、Channel/Multiplexing/Enum/Unit/Error、Object-leak Assertion。

**依赖：** Task 2、6；接口稳定后可与 Task 7–9 并行。

## Task 11 — Analysis Application Service 与可复现性

**目标：** 编排 Compile、Selective Ingestion、Execution 和 Manifest 创建。

**范围：** Analysis Configuration、Binding、File Hash、Version/Option、Cancellation/Progress Protocol 和 Run Service；不使用数据库。

**文件/模块：** `application/analyze.py`、`configuration.py`、`manifest.py`。

**验收条件：** 单次调用可执行完整 Vertical Slice；每个 Result 引用完整 Manifest；记录 Original/Migrated Rule Hash 与 Input/DBC Hash；Cancellation 安全 Finalize，不产生错误 FAIL。

**测试：** Fake Adapter End-to-end、Reproducible Manifest、Input/Config 变化会改变 Hash、Cancellation/Incomplete Behavior。

**依赖：** Task 6、9、10。

## Task 12 — JSON/HTML Report 与 CLI

**目标：** 在不耦合 Presentation 与 Runtime 内部实现的前提下开放 MVP 能力。

**范围：** 稳定 JSON Result Serialization、简单 Jinja2 HTML、CLI Analyze/Validate Command；Chart 可选且必须有界。

**文件/模块：** `reporting/`、`cli/`。

**验收条件：** Report 只接受 Result/Manifest Model；逐 Trigger Evidence/Window/Reason 可见；UNKNOWN/NOT_EVALUATED/INVALID 明确区分；CLI 可验证并执行示例；Output Path 显式。

**测试：** JSON Schema/Golden、HTML Escape、关键 Section Snapshot、CLI Success/Error Code。

**依赖：** Task 11。

## Task 13 — Golden Suite 与性能基线

**目标：** 在扩展功能前锁定语义并测量第一个 Vertical Slice。

**范围：** Example A–C 和边界场景的 Normalized Golden、少量完整 CAN Fixture、Deterministic Generator 和 Benchmark Report。

**文件/模块：** `tests/golden/`、`tests/performance/`、`examples/`。

**验收条件：** Golden 进入 CI；不同 Chunk Size 结果一致；记录代表性日志、1,000 Node、10,000 Instance 的吞吐与内存；识别瓶颈，不进行无依据重构。

**测试：** Golden/Benchmark Suite，以及防止 Compile/Dispatch 意外出现平方复杂度的 Guard。

**依赖：** Task 11–12。

## 交付顺序与评审门禁

关键路径为 1 -> 2 -> 3 -> 4 -> 5 -> 6 -> 7 -> 8 -> 9 -> 11 -> 12 -> 13。Task 10 在 Domain 和 Compiler Subscription Interface 稳定后开始。完成 Task 6 后，必须对实际 Type 和 Compiled IR 进行架构评审；声明 MVP 完成前，应评审 Golden Semantics 与性能证据，而不是只看 Feature 数量。
