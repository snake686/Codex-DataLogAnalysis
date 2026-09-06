# 规范性时间语义

本文档是时间相关 Block 的语义权威。规则文件必须声明 `semantic_profile`；MVP 使用 `core-temporal/1.0`。任何对区间边界、排序、UNKNOWN 传播或完成条件的行为变更，都必须发布新的 Profile Version。

## 1. 时间模型

- `TimePoint` 和 `Duration` 使用有符号 64 位整数纳秒。
- 分析时间是单调时间，通常相对于 Recording/Session 起点。墙上 UTC 时间如存在，只作为 Provenance。
- `500 ms` 等 Duration 文本必须精确解析为整数纳秒。只有可以精确表示为整数纳秒的小数单位才合法，否则验证失败。
- 除非某个 Operator 明确接受 Lookback，否则负 Duration 非法。
- Operator 只比较整数。浮点秒不得参与 Deadline 计算。

int64 纳秒可表示约 292 年，足够覆盖分析 Session。Adapter 将浮点 Timestamp 转换为整数时只能舍入一次，且必须记录舍入方法。

## 2. 顺序、Timestamp 与 Watermark

输入 Transaction 顺序键为 `(timestamp_ns, source_id, transaction_sequence)`。同一 Source 内的 `transaction_sequence` 必须稳定。一个 Transaction 中的 Source Update 原子生效；CAN Adapter 通常令一帧对应一个 Transaction。Transaction 内的 `item_index` 只用于稳定 Identity/Evidence，不决定中间业务状态。Runtime 按 `rule-engine.md` 定义，以 Timestamp Batch 为单位计算。

在时间 `t`，系统按照 `rule-engine.md` 的规范 Phase 顺序处理：先处理仅依赖 `[start,t)` 历史而成熟的 Timer，再逐 Transaction 执行同时间 Microstep，然后在完整 Timestamp Event Set 上匹配 Target，最后关闭 Within Deadline。因此 Target 恰好出现在闭合的 500 ms Deadline 时判定 PASS；开放上界则不通过。同一 Signal 在同一时间的多次 Transition 不得因 Batch 合并而丢失，同一 Transaction 内也不得产生 Partial-update State。

Watermark `w` 表示未来不会再接受 `timestamp <= w` 的 Event。Offline Reader 通常在有序 Chunk 后推进 Watermark，并最终发出 Final Watermark 与 End Event。无论 Upper Bound 开闭，Timeout 都在 Deadline Timestamp Batch 完成且 `w >= deadline` 时可最终确定；区别只在于 Deadline 上的 Target 对 Closed Bound 有效、对 Open Bound 无效。实现不得混用“到达”与“越过”造成一纳秒差异。

默认 Out-of-order Policy 为 `reject`：产生 ERROR，且违规 Event 不得修改 Runtime State。Decoder 可以在有界 Chunk 内排序，但必须检测全局乱序。未来 Live Mode 可显式配置 Allowed-lateness Buffer；Late Event Retraction 不属于 Profile 1.0。

## 3. 区间表示

每个时间窗口都由 Lower/Upper Offset 以及 `lower_closed`、`upper_closed` 表示，不存在隐藏的边界约定。

Trigger Time 为 `t0` 时，常见的 500 ms 响应区间为 `[t0, t0 + 500 ms]`。若要求严格发生在 Trigger 之后，则使用 `(t0, t0 + 500 ms]`。

## 4. Edge Operator

### RisingEdge

输入：`TruthStream`，或经显式 Comparison 转换的离散 Scalar。  
输出：`EventStream<Edge>`。

当上一条有效 Observation 为 FALSE，当前 `t` 时刻的新 Observation 为 TRUE 时产生 Rising Edge。连续 TRUE 不重复发出 Event。UNKNOWN 不等于 FALSE，因此不产生 Edge。

必须声明初始化策略：

- `require_baseline`（默认）：第一条 Known Observation 只建立 Baseline，不得产生 Edge。
- `assume_false`：初始 TRUE 会产生 Edge；仅在领域能够保证 Session 前状态时使用。

经过 UNKNOWN 后，默认 `require_rebaseline`：下一条 Known Value 仅重新建立 Baseline，不产生 Edge，从而避免数据间隙伪造边沿。输入超过 Max Age 或进入 Gap 时，同样可以使 Baseline 失效。

### FallingEdge

语义对称：上一条有效 Observation 为 TRUE，新值为 FALSE。默认初始化和 UNKNOWN 行为与 RisingEdge 相同。

如果同一 Input 在同一 Timestamp 的不同 Transaction 有多条 Observation，则按稳定 Transaction Sequence 处理，并允许在同一时间产生多个 Edge。Adapter 应保留这些 Transition，不得合并。一个 Transaction 内同一 Source Key 出现多次属于 Adapter Error；跨 Signal Consumer 视其时间相同，但 Evidence 保留 Transaction Identity 以便复现。

## 5. Duration / ForAtLeast

`ForAtLeast(condition, d)` 观察 TruthStream，在 Condition 已连续为 TRUE 至少 `d` 时发出一次 Event。

- `t` 时刻出现 FALSE，当前 True Interval 在 `t` 结束。
- `t0` 时刻出现 TRUE，且当前没有 Candidate，则新的 Candidate Interval 开始。
- 若可证明 Condition 一直为 TRUE，则 Scheduler/Watermark 到达 `t0 + d` 时恰好发出 Event；该时刻不需要存在 Sample。
- 如果 Condition 在 `t0 + d` 恰好由 TRUE 转为 FALSE，则此前半开区间 `[t0,t0+d)` 的长度正好为 `d`，仍应先发出 ForAtLeast Event，再结束该 True Interval。
- 默认情况下 UNKNOWN 会中断连续性证明并清除 Candidate。MVP 不提供 `pause` Policy，因为它会改变物理时间含义。
- `d = 0` 时在 TRUE Observation 时刻发出 Event。
- 每个最大连续 TRUE Interval 只发出一次；只有经历 FALSE 或 UNKNOWN 后重新建立 TRUE，才能再次发出。

Hold-last 只有在配置的 `max_age` 内才能证明连续性。有效区间为 `[sample_time, sample_time + max_age]`；恰好在 Max Age 的 Deadline 仍可使用该值，之后才变为 STALE。如果保留值在 Duration Deadline 之前过期，则 Truth 变为 UNKNOWN，不得发出成功 Event。

如果 `Duration` 被用作测量 Block，则可以输出已结束 TRUE Interval 的长度。为避免歧义，持久化格式使用不同 Type ID：`core.temporal.for_at_least` 和未来的 `core.temporal.measure_duration`；UI 可根据上下文显示相似名称。

## 6. Within

规范 Expectation 形式：

```text
Within(trigger: EventStream, target, interval, satisfaction_mode)
    -> EvaluationStream
```

每个 `t0` 时刻的 Trigger 都会创建独立 Evaluation Instance。若所选 Target Satisfaction 落在配置区间内，则 PASS；如果完整区间结束仍未满足，则 FAIL。

Target Satisfaction Mode：

- `is_true`：区间中存在有效 TRUE Condition Observation/State。Held Value 只有在 Alignment/Freshness Policy 认定它在该时刻有效时才计入。
- `becomes_true`：Target Condition 的 RisingEdge Event 落在区间中。推荐用于“响应”语义。
- `event`：显式 Target Event 落在区间中。
- `true_throughout`：Condition 在整个区间持续 TRUE；MVP 应编译为独立 Monitor，不得重载普通 Within。

因此，“SignalB == 1 within 500 ms” 在选择 Mode 和 Bound 之前是无效定义。响应规则使用 `becomes_true`，通常选择 `(t0, t0+500ms]`；“已经为真或在窗口内变真”使用 `is_true` 和 `[t0, t0+500ms]`。

在闭合 Deadline 上先处理 Target Data。完整窗口中能够确定未满足时，结果为 FAIL/TIMEOUT。如果 Gap/Staleness 或不完整 Coverage 使任一必要区间无法判断，并且没有已确定的 Satisfaction，则为 UNKNOWN/DATA_MISSING。`observe_only` 只提供点状 Coverage；要证明连续窗口内未发生响应，应使用带有限 `max_age` 的 Hold-last 或其他明确 Availability Contract。日志在 Deadline 前结束时为 UNKNOWN/INCOMPLETE_WINDOW。

## 7. After

`After(event, d)` 在 `event.timestamp + d` 调度一个 Derived Timer Event。它不采样 Condition，也不表示模糊的“稍后某时”。Runtime Progress 到达该时间时即发出 Event，不要求存在 Data Sample。

- `d = 0` 时放入同一 Timestamp 的 Derived-timer Queue，在 Input Transaction 完成后、Temporal Matching 前发出，避免递归组合执行。
- 除非显式 Overlap Policy 另有规定，每个 Input Event 独立调度一个 Output Event。
- End-of-stream 早于计划时间时不发出 Event，依赖它的未完成 Expectation 变为 UNKNOWN。

“B 在 A 后 100–500 ms 发生”应编译为 `Within(A, B, [100ms,500ms])`，而不是一元 After。

## 8. Wait

`Wait(d)` 是 Sequence Authoring Construct：在 `t0` 收到 Sequence Token 后，于 `t0+d` 释放该 Token。它编译为带 Evaluation Instance Key 的 `After` Timer。它不延迟或重放 Signal Value。

用于移动 Value Observation 的 `Delay(ValueStream,d)` 是另一种 Operator，MVP 暂不支持。UI 不得混用 “Wait” 与 “Delay”。

## 9. Before

规范的 Bounded Lookback 形式：

```text
Before(candidate: EventStream, anchor: EventStream,
       interval=[min_offset,max_offset]) -> EvaluationStream
```

每个 Anchor Time `ta` 到达时，若存在 Candidate `tc` 满足 `ta-max_offset <= tc <= ta-min_offset`，则 PASS；Endpoint 是否包含由参数显式指定。默认要求 `min_offset >= 0` 且 `max_offset >= min_offset`。“严格在之前”通常使用 `[ta-max, ta-min)`。

系统在 Anchor 到达时使用有界历史求值。如果缺失或 Gap History 阻碍结论，则为 UNKNOWN。MVP 拒绝 Unbounded Before。一元 “Before 500 ms” 因缺少 Anchor 和 Candidate 而非法。

## 10. Timeout

`Timeout(trigger, d)` 仅在关联 Expectation 尚未满足或取消时，于 `t0+d` 产生 Timeout Event。它是 Control Event/Reason，并不自动等于 FAIL。Assertion 可以将它映射为 FAIL、WARNING、Record 或其他配置结果。

Closed Deadline 上，同时间的 Satisfaction 优先于 Timeout。如果窗口不完整，或数据质量使“未满足”无法确定，则 Timeout Classification 为 UNKNOWN；只有显式的 Data Availability Rule 才可把数据不可用判为失败。

## 11. 示例

### 恰好在 Deadline 响应

```text
100 ms  ChargeEnable: 0
200 ms  ChargeEnable: 1  -> RisingEdge Trigger
700 ms  PackCurrent: 1 A -> Target becomes true
```

对于 `(200ms,700ms]`，结果为 PASS。若 Upper Bound 为 Open，则 Watermark 越过 700 ms 后结果为 FAIL。

### Target 在 Trigger 前已经满足

```text
100 ms  PackCurrent > 0 becomes TRUE
200 ms  ChargeEnable RisingEdge
```

在 Hold-last 仍有效时，`is_true` 可以在 200 ms PASS；`becomes_true` 不会 PASS，而会等待新的 FALSE 到 TRUE Transition。

### Duration 与稀疏采样

```text
0 ms     HV_Ready == TRUE
2000 ms  （没有 Sample）
```

若 Hold-last `max_age >= 2000 ms` 且 Watermark 到达 2000 ms，ForAtLeast 在 2000 ms 发出 Event。若 `max_age = 500 ms`，Truth 在 500 ms 变为 UNKNOWN，不能证明 Duration 成立。

### 数据间隙

```text
0 ms     A TRUE
400 ms   GapStart
900 ms   GapEnd
1000 ms  A TRUE
```

默认 Gap Policy 下，`ForAtLeast(A,1s)` 不会在 1 s PASS。Gap 中断连续性证明，必须在 1 s 或之后收到新的 Good Sample 才能重新建立 Baseline；`GapEnd` 本身不恢复 Gap 前的 Held Value。

### 相同 Timestamp

如果 Trigger 和 `is_true` Target 在 100 ms 均有效，且 Lower Bound Closed，则 Instance 可在 100 ms PASS。对于 `becomes_true`，Target Edge 必须在该时刻实际产生；Evidence 保留确定性的 Source Sequence。如果产品需求依赖同时间 Frame 的到达先后，必须使用 Sequence-aware Event Constraint，不能只依赖 Time Bound。

## 12. 多 Trigger 与结束行为

默认 Overlap Policy 为 `independent`；100 个 Trigger Event 会创建 100 个 Instance。一个 Target Event 如果同时落在多个 Active Window 内，可以满足多个 Instance。`consume_once` 等消费语义必须显式定义，MVP 暂不支持。

`EndOfStream(t_end)` 关闭本次 Run，但不会假装时间已推进到未完成 Deadline 之后。Deadline 晚于 `t_end` 的 Instance 变为 UNKNOWN/INCOMPLETE_WINDOW；已经过期且完整可观测的窗口可以正常 Finalize。
