# 实现前架构审计记录

审计日期：2026-09-06  
范围：`README.md`、`AGENTS.md`、全部 Architecture/Rule/Schema/Testing/Plan 文档、ADR、`pyproject.toml` 与当前 Source Skeleton。

## 1. 已发现并修正的问题

| 编号 | 原问题 | 风险 | 修正 |
|---|---|---|---|
| AR-001 | Example B 将 `ValueStream<Bool>` 直接连接到 RisingEdge 的 `TruthStream` Input | 违反强类型 Port Contract，Compiler 无法实现 | 增加显式 Boolean Equality，先生成 TruthStream |
| AR-002 | Example B Schema 使用 Open Lower Bound，但 IR 写成 `lower_closed: true` | 同时间 Target 结果不一致 | IR 改为 `lower_closed: false` |
| AR-003 | Example A Schema 使用 `assert_never`，IR 却使用 `assert.always` | Rule 极性相反，可能把超温判 PASS | IR 统一为 `assert.never` 和对应 Status Mapping |
| AR-004 | Runtime 先合并整个 Timestamp Batch 再算 Edge，但规范要求保留同时间多次 Transition | 会丢失 0->1->0 等事件 | 引入 Timestamp Batch 内有序 Microstep，并在完整 Event Set 上做 Temporal Match |
| AR-005 | Closed Deadline 有时描述为 Watermark“到达”，有时描述为“越过” | 产生 1 ns 边界差异 | 明确 Batch 完成且 `watermark >= deadline` 后关闭 Closed Window |
| AR-006 | `observe_only` 被用于响应 Timeout，却没有定义窗口可观测性 | 报文缺失可能被误判为 FAIL | 定义 Coverage；Example B 改用有限 Hold-last，Coverage 不完整时 UNKNOWN |
| AR-007 | Unknown Unit 同时可能是 Compiler Diagnostic 和 Runtime UNKNOWN | 静态错误与数据缺失混淆 | Unit-sensitive Operation 无法证明兼容时 Validation Error/INVALID |
| AR-008 | `Quantity<dimension>` 与 `value_type=float + unit` 两套 Type 表达并存 | Schema 与 Port Type 难映射 | 统一为 Scalar Type 加 Compile-time Unit/Dimension Decoration |
| AR-009 | Aggregate Priority 只写“ERROR/INVALID 高于”，没有严格全序 | Report Generator 可能产生不同 Overall Status | 固定 `INVALID > ERROR > FAIL > UNKNOWN > PASS` |
| AR-010 | Scope Assertion 的 PASS/UNKNOWN/无 Sample 语义缺失 | Example A 无法确定 Overall Status | 定义 `observed_samples`/`continuous` 和精确聚合规则 |
| AR-011 | Python 文档为 3.12+，Package Metadata 限制为 3.13+ | 无意排除 Python 3.12 | `requires-python` 改为 `>=3.12`，3.13 作为开发版本 |
| AR-012 | Evaluation ID 与 Event ID 未定义稳定生成方式 | Golden/Reproducibility 不稳定 | 固定 Versioned JCS Payload 与完整 SHA-256 ID，并要求 Golden Vector |
| AR-013 | Gap Scope、GapEnd 与旧 Held Value 的关系未定义 | Gap 后可能错误沿用旧值 | Gap 必须声明 Scope；GapEnd 不恢复 Value，等待新 Good Sample |
| AR-014 | 每个 Rule 可有多少 Result Node 未定义 | Aggregation/GUI/Compiler 模型分叉 | MVP 固定每 Rule 恰好一个 Terminal Result Node |
| AR-015 | Pass/Fail 是 Block 还是 Status Mapping 不清晰 | Graph 极性含糊 | MVP 将其定义为 GUI 表现，持久化使用 Assertion/Expectation |
| AR-016 | 同一 Frame 解码出的 Signal 若逐条传播，会出现 Partial-update State | 可能制造不存在的 Comparison/Edge | 引入原子 Transaction；CAN 中一帧对应一个 Transaction，Frame 间仍保留顺序 |
| AR-017 | `observe_only` 的点状 Coverage 与 Edge Baseline 未区分 | 要么无法检测相邻 Sample Edge，要么错误声称中间状态连续 | 分离 Last Observation 和 Current State Coverage；Gap 使 Baseline 失效 |
| AR-018 | Float Equality 同时被称为 Bit-level，又引用 Python Numeric Semantics | `-0.0` 行为自相矛盾 | 定义为无 Tolerance 的有限 Numeric Equality，不宣称 Bit-level |
| AR-019 | YAML Loader 未规定 Duplicate Key 与 YAML 1.1 隐式类型行为 | Rule 可能被静默覆盖或误解析 | 要求 YAML 1.2 Core Schema、Duplicate Key Error 和禁用隐式对象构造 |
| AR-020 | 直接把 int64 ns 放入 JCS Number | 超过 JavaScript Safe Integer 时 Hash 跨语言不一致 | Canonical Projection 使用十进制字符串表示 Time/Duration/Int Scalar |
| AR-021 | Multiplex Branch 未激活时旧 Held Value 是否继续有效未定义 | Rule 可能读取当前 Frame 中并不存在的 Signal | Branch 切出时发出 UNAVAILABLE 并使 Held Value/Baseline 失效 |
| AR-022 | Rule Semantic Hash 混入本次运行的 Effective Parameter | Artifact Identity 与 Execution Identity 混淆 | 拆分 Rule Semantic Definition Hash 与 Execution Semantic Hash |
| AR-023 | Example C 的 Numeric Source/Constant 未声明 Unit | 无法区分无量纲与 Unit Metadata 缺失 | 对状态整数显式使用 `unit: none` |

## 2. 已固定的实现默认值

- 一份 Input Recording 对应一个 Analysis Session；Batch 不拼接 Timeline。
- 全局 Out-of-order 在 MVP 中属于 Fatal Run Error。
- 同一 Timestamp 内保留 Source Sequence；纯计算逐 Microstep 传播，Temporal Window 按时间集合匹配。
- Hold-last 在 `age <= max_age` 时有效，端点 Closed；之后变为 STALE。
- Target 成功可以在先前 Coverage 不完整时直接 PASS；没有 Target 时只有完整 Coverage 才能 FAIL。
- No Trigger 为 NOT_EVALUATED；Incomplete Window 为 UNKNOWN。
- 每 Rule 一个 Terminal Result；Rule Set 聚合多个 RuleResult。
- Float Exact Equality 可用但必须 Warning。
- Python 3.12 是兼容下限，3.13 是当前推荐开发解释器。

## 3. 仍需未来产品决策、但不阻塞 MVP 的问题

以下问题已有安全 Default，不影响开始编码；如果产品意图不同，应在对应功能进入实现前调整 ADR/Semantic Profile：

1. 是否需要让一个 Target Event 只能被一个 Trigger 消费（`consume_once`）。MVP：不消费，可满足多个窗口。
2. 是否需要 Restart/Merge/Ignore 等 Overlap Mode。MVP：仅 `independent`。
3. 是否把 DBC Cycle Time 自动派生为 Freshness。MVP：禁止隐式派生，只允许显式 Analysis Policy。
4. 是否支持 Approximate Float Equality。MVP：不支持，Exact Equality 产生 Warning。
5. Scope Rule 是否需要对 Sample 间状态作连续断言。MVP：Example A 使用 `observed_samples`；连续断言必须明确 Coverage。
6. Live CAN 的 Allowed Lateness 与 Retraction。MVP：不支持 Late Event。
7. Result 是否需要外部流式存储大量 Evaluation。MVP：模型允许分页/流式 Writer，但不引入数据库。

## 4. 实现风险排序

### 高风险

- Timestamp Phase 与边界：必须先以 Reference Interpreter/Table Test 固化，再优化 Scheduler。
- Coverage 与 Missing Data：如果只保存 Current Value 而不保存有效区间，将无法正确区分 FAIL 和 UNKNOWN。
- Active Instance Explosion：必须从第一版就实现 Hard Limit 和 Deadline Generation，不能事后补静默清理。

### 中风险

- Unit Normalization：小型 Registry 需要 Canonical ID 与 Offset Temperature Test。
- DBC Binding Uniqueness：多 Channel、Extended ID 与 Multiplexing 容易产生同名冲突。
- Result Size：大量 Trigger 的 Evidence 必须有界，同时保留精确 Summary。

### 低风险

- GUI、HTML Theme、Plotly：均位于标准化 Definition/Result 之外，可后续替换。
- BLF 与 ASC Reader：Adapter 复杂但不会改变 Core Contract，只需严格通过 Contract Test。

## 5. 审计结论

架构已经能够开始 Repository Bootstrap 和 Domain Primitive 实现。Task 2 之后，建议依次完成 Rule Definition、Block Registry、Validator 与 Compiler；在 Temporal Runtime 前先把 `time-semantics.md` 全部边界写成 Test Vector。任何实现若需要猜测本文档未定义的时间或 Missing Data 行为，应停止编码并先更新规范或 ADR。
