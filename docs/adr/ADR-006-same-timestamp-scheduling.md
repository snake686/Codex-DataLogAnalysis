# ADR-006：同 Timestamp 使用 Microstep 与分阶段 Temporal Matching

- 状态：MVP 已接受
- 日期：2026-09-06

## 背景（Context）

同一 Timestamp 可能包含同一 Signal 的多次 Transition，也可能同时包含 Trigger、Target 和 Deadline。一个 CAN Frame 还会同时更新多个 Signal。如果先把 Batch 合并为最终 Source Value，会丢失 Edge；如果逐 Signal 传播，会产生“新 A + 旧 B”的虚假中间状态；如果完全逐 Event 立即匹配，则 Closed Lower Bound 的结果会依赖 Source Arrival Sequence。

## 决策（Decision）

Runtime 必须先收集完整 Timestamp Batch，再按稳定 Source Transaction Sequence 执行 Dataflow Microstep。一个 Transaction 的全部 Source Update 先原子写入，再传播一次 Dataflow；CAN 中通常一帧对应一个 Transaction。Derived Trigger/Target 在完整 Timestamp Event Set 上进行 Temporal Matching，随后关闭同时间 Within Deadline。仅依赖此前区间历史的 Duration/After Maturity Timer 在 Input Microstep 前执行；Microstep 新产生的 Zero-duration Timer 在 Matching 前的独立 Queue 中执行。详细 Phase 以 `rule-engine.md` 和 `time-semantics.md` 为准。

## 备选方案（Alternatives）

- Batch 只保留最终值：简单，但会丢失同时间 Transition。
- 逐 Signal Update 传播：可保留 Transition，但会为同 Frame Signal 制造虚假中间状态。
- 所有逻辑逐 Event 立即执行：保留 Transition，但 Time-based Rule 会不必要地依赖 Arrival Sequence。
- 人为给 Timestamp 加 1 ns：修改原始事实，破坏可复现性和边界语义。
- 固定 Source Priority 决定业务结果：虽然确定，但把 Adapter 顺序误当成时间语义。

## 影响（Consequences）

Reader 必须提供 Timestamp Lookahead，Chunk 不能拆开 Batch 或 Transaction。Adapter 必须声明 Transaction Boundary。Scheduler 需要区分 Maturity、Transaction Microstep、Temporal Match、Deadline 和 Freshness Phase。要求 Arrival Order 的规则未来必须使用显式 Sequence Constraint，而不能借用相同 Timestamp 的处理顺序。
