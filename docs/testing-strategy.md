# 测试策略

Rule Engine 必须作为确定性的纯逻辑时间系统进行测试。测试通过构造带 Timestamp 的 Event 并推进 Watermark 驱动执行，禁止使用 `sleep()` 或机器时钟。

## 1. 测试层级

### Block 单元测试

每个 Block Definition/Operator 都应测试：

- 正常的 Truth/Value/Event 行为；
- 所有支持的 Input Type 以及应拒绝的不兼容类型；
- UNKNOWN、Invalid Quality、Stale Value 及恢复行为；
- Stateful Block 的初始化、Reset 和 Finalize；
- 相同 Timestamp Update 和精确边界值；
- Parameter Validation 和 Block Version Resolution。

每个新 Block 都必须提供上述测试，以及适用的时间语义 Truth Table 或示例。

### Schema 与 Migration 测试

- JSON 与 YAML 往返后得到同一 Canonical Model；
- Unknown Field、Duplicate ID、Invalid Duration 和 Unsupported Version；
- Canonical Hash 确定且稳定；
- 每个受支持 Schema Migration 都有 Fixture；
- 旧 Rule 在其声明的 Semantic Profile 下迁移前后行为等价。

### Validator/Compiler 测试

- Missing/Extra/Duplicate Port 和非法 Connection；
- Type/Unit Inference、Conversion 和 Enum Domain Mismatch；
- Cycle、不可达 Result、Orphan Node 和错误 Binding；
- Constant Folding 与 Source Subscription Extraction；
- 稳定 Diagnostic Code 和 Source Map；
- Authoring Graph 能编译为规范化 IR Snapshot。

IR Snapshot 应比较语义结构，不比较不稳定的 Python `repr` 或自动生成 Object ID。

### Runtime 测试

- Timestamp Batch Phase Order 和确定性 Tie-breaking；
- 同一 Signal 在同一 Timestamp 的多次 Transition 不因 Batch 合并丢失；
- 同一 CAN Frame 的多个 Signal 原子更新，不产生 Partial-update Transient Edge；
- Chunk Boundary 不改变结果；
- State 跨 Chunk 保留，同时在 Run/Rule 之间隔离；
- Watermark/Deadline 顺序和 End-of-stream Completion；
- Coverage、Freshness Closed Endpoint、GapEnd 后重新建立 Baseline；
- Overlapping Trigger Instance 与 Aggregation；
- Resource Limit 产生 ERROR，不得静默丢失；
- Evidence Limit 仅截断展示证据，不改变 Status。

### Temporal Conformance 测试

针对 `time-semantics.md` 的每项规范编写 Table-driven Case：

- Lower/Upper Open 与 Closed Bound；
- Target 出现在 Trigger 时、Deadline 前 1 ns、恰好 Deadline、Deadline 后 1 ns；
- First-sample Edge Initialization；
- Edge 或 Duration 前后的 UNKNOWN/Gap/Staleness；
- Timer Deadline 上没有 Sample；
- Zero-duration Timer Chain 在同一 Timestamp 按 Topology 排空且不递归溢出；
- 同一 Timestamp 多次 Transition；
- Out-of-order Input；
- 日志在 Deadline 前、恰好 Deadline 和 Deadline 后结束；
- 多 Trigger 共享或分别命中 Target Event。
- Target 出现时可直接 PASS，以及 Target 缺失但 Coverage 不完整时必须 UNKNOWN；
- `assert_never` 的 observed-samples/continuous Scope Aggregation；
- 确定性 Event/Evaluation ID。

逻辑时间 Fixture 示例：

```python
events = [
    sample("ChargeEnable", "0 ms", False),
    sample("ChargeEnable", "100 ms", True),
    sample("PackCurrent", "400 ms", 0.0, unit="A"),
    sample("PackCurrent", "600 ms", 1.0, unit="A"),
    watermark("600 ms"),
    end_of_stream("600 ms"),
]
```

对于 Strict-after 且 Closed-deadline 的 500 ms Rule，600 ms 的 Target 应 PASS；改为 600 ms + 1 ns 后，Watermark 推进时应 FAIL。整个测试不涉及墙上时间。

### Integration 测试

- Synthetic RawFrame -> Fake Decoder -> Normalized Event -> Engine -> Result；
- 使用少量合法生成的 ASC/BLF Fixture 通过真实 Adapter；
- DBC Enum/Unit/Scale、多 Channel、Multiplexing、Invalid Frame 和 Decode Error；
- Multiplex Branch 切换使旧 Held Value 立即 UNAVAILABLE，重新激活后必须 Rebaseline；
- JSON/HTML Report 只消费标准化 Result；
- Selective Decode 与 Full Decode 结果一致。

Adapter Integration Test 可以依赖 `python-can`/`cantools`；Core Test 不得依赖它们。

### 端到端 Golden Test

```text
tests/golden/charge_current_response/
  rule.yaml
  analysis.yaml
  input.csv                 # 标准化且便于人工检查的规范输入
  expected.result.json
  README.md                 # 场景和语义意图
```

多数 Golden 使用标准化 CSV，避免 Parser 变更伪装为 Engine 变更；另保留一小组 BLF/ASC/DBC Fixture 覆盖完整 Pipeline。

Golden Output 应归一化 Run ID、绝对路径、与分析无关的时间戳以及 Build Metadata。Status、Reason、Window、由稳定输入派生的 Evaluation ID、Evidence、Diagnostic 和 Semantic Hash 必须精确比较。更新 Golden 时必须说明预期行为变化；如果涉及语义，还需要 ADR 或 Profile Version 决策。

## 2. Property 与 Metamorphic 测试

第一个 Vertical Slice 完成后，使用 Hypothesis 一类工具测试高价值不变量：

- 添加无关 Source Event 不改变结果；
- 将输入任意拆分为 Chunk 不改变结果；
- 整体平移 Monotonic Time 会等量平移所有 Result Time，但不改变 Status；
- 常量 Unit Conversion 不改变 Comparison 语义；
- 相同输入重复执行会生成字节等价的规范语义结果；
- No-late-data Profile 下，已发布 Terminal Instance 不再改变；
- Active Instance 数量等于 Trigger 数减去 Terminal/Cancelled Instance 数。

Model-based Test 可以将 `Within` 和 `ForAtLeast` 与小型、明显正确的 Reference Interpreter 对比。

## 3. 性能与 Soak Test

性能测试应与普通 Unit CI 分开，持续记录：

- Selective Decode 的 Frame/s 与 Normalized Event/s；
- 每个 Input Event 触发的 Operator Evaluation 数；
- 对有界规则而言，Peak Memory 不随 Log Length 增长；
- 10、1,000 和 10,000 个 Active Instance 下的成本；
- 1,000 Node Graph 的 Compile 和 Propagation 时间；
- Report/Evidence 内存。

使用固定 Seed 的 Generated Stream，并记录 Hardware/Runtime。性能预算应在第一个可运行 Vertical Slice 后依据实测制定，不要预先虚构指标。CI 仍需包含小型 Regression Guard，防止意外引入平方复杂度。

## 4. 质量门禁

Implementation Task 只有满足以下条件才算完成：

- 相关 Unit、Compiler、Temporal、Integration 和 Golden Test 通过；
- 逻辑时间测试不使用 `sleep()`；
- 新行为已文档化，并对 Diagnostic 进行断言；
- 项目配置的 Static Type/Lint 检查通过；
- Dependency Boundary 已检查；
- 最终 Diff 不包含无关变更。

工具完成配置后，建议的初始命令为：

```text
pytest
python -m mypy src
ruff check .
ruff format --check .
```

具体工具集应在 Bootstrap Task 中确定，并最终收敛为一条 Contributor Command。
